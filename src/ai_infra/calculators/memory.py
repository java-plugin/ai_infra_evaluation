"""显存计算器。

训练显存 (单卡):
    权重      = params × bytes / tp
    梯度      = params × bytes / tp   (与权重同精度)
    优化器    = params × bytes × 2 / tp (AdamW: fp32 master + fp32 m + fp32 v)
    激活      ≈ L × batch × hidden × seq × bytes × 2  (训练前向+反向)
    KV Cache  = (推理模式不计)
    workspace ≈ 2–4 GB

推理显存 (单卡):
    权重      = params × bytes / tp
    KV Cache  = 2 × L × H_kv × d_head × seq × batch × kv_bytes / tp
    workspace ≈ 2–4 GB

LoRA: 权重部分只训练 LoRA 参数 (~rank × hidden × layers × 2), 仅影响梯度和优化器。
"""

from __future__ import annotations

from ..catalog import CatalogError, get_gpu, get_model
from ..models import CalcResult, MemoryInput, SourceRef

_DTYPE_BYTES = {"fp32": 4, "fp16": 2, "bf16": 2, "fp8": 1, "int8": 1}


def calc_memory(params: MemoryInput) -> CalcResult:
    assumptions: list[str] = []
    warnings: list[str] = []
    provenance: list[SourceRef] = []

    try:
        gpu = get_gpu(params.gpu_id)
        model = get_model(params.model_id)
    except CatalogError as exc:
        return CalcResult(
            value={}, assumptions=assumptions, warnings=[f"查找失败: {exc}"], provenance=provenance
        )

    provenance.append(
        SourceRef(source=f"data/gpus.yaml#{gpu.id}", as_of=gpu.as_of, confidence=gpu.confidence)
    )
    provenance.append(
        SourceRef(
            source=f"data/models.yaml#{model.id}", as_of=model.as_of, confidence=model.confidence
        )
    )

    weight_bytes = _DTYPE_BYTES[params.weight_dtype]
    kv_bytes = _DTYPE_BYTES[params.kv_dtype]

    total_params = model.params_billion * 1e9
    tp = params.tp
    L = model.num_layers
    hidden = model.hidden_size
    H_kv = model.num_kv_heads or model.num_attention_heads
    head_dim = hidden // model.num_attention_heads

    # 权重 (单卡)
    if params.use_lora:
        # LoRA 只训 B=A×rank → 训练部分 ≈ L × (hidden × rank + hidden × rank) × 2 bytes
        lora_params = float(L * hidden * params.lora_rank * 2)
        weight_per_gpu = total_params * weight_bytes / tp  # base model 冻结，仍占显存
        train_params: float = lora_params
    else:
        weight_per_gpu = total_params * weight_bytes / tp
        train_params = total_params

    weight_gb = weight_per_gpu / 1024**3

    if params.mode == "training":
        # 梯度: 与训练部分同精度
        grad_bytes = 2 if params.weight_dtype in ("fp16", "bf16") else 4
        grad_per_gpu = train_params * grad_bytes / tp
        grad_gb = grad_per_gpu / 1024**3

        # 优化器 AdamW: fp32 master + fp32 m + fp32 v ≈ 3× train_params × 4 bytes
        if params.use_lora:
            opt_per_gpu = lora_params * 3 * 4 / tp
        else:
            if params.optimizer == "adamw":
                opt_per_gpu = train_params * 3 * 4 / tp
            elif params.optimizer == "sgd":
                opt_per_gpu = 0.0
            else:  # lamb
                opt_per_gpu = train_params * 4 * 4 / tp
        opt_gb = opt_per_gpu / 1024**3

        # ZeRO: 把优化器 / 梯度 / 权重分到 DP
        if params.zero_stage == "1":
            opt_gb /= 1  # zero 1 不分权重，仅优化器
        elif params.zero_stage == "2":
            opt_gb = opt_gb  # 默认已经是 train_params/tp，此处留给 DP；简化处理
            grad_gb = grad_gb
        elif params.zero_stage == "3":
            weight_gb /= 1  # 同上；简化处理
            opt_gb /= 1
            grad_gb /= 1

        # 激活 (近似)
        act_bytes = 2 if params.weight_dtype in ("fp16", "bf16") else 4
        act_per_step = float(L * params.batch * params.seq_len * hidden * act_bytes * 2)  # fwd+bwd
        if params.gradient_checkpointing:
            act_per_step *= 0.25
        act_gb = act_per_step / 1024**3

        kv_gb = 0.0  # 训练中不计推理 KV
        total_gb = weight_gb + grad_gb + opt_gb + act_gb + kv_gb + 3.0  # +3 workspace
        breakdown = {
            "权重_gb": round(weight_gb, 2),
            "梯度_gb": round(grad_gb, 2),
            "优化器_gb": round(opt_gb, 2),
            "激活_gb": round(act_gb, 2),
            "KV_gb": 0.0,
            "workspace_gb": 3.0,
        }
    else:
        # 推理
        grad_gb = 0.0
        opt_gb = 0.0
        act_gb = 0.5  # 推理激活很小
        kv_per_token = 2 * L * H_kv * head_dim * kv_bytes
        kv_per_request = kv_per_token * params.seq_len
        kv_total = kv_per_request * params.batch / tp
        kv_gb = kv_total / 1024**3
        total_gb = weight_gb + kv_gb + act_gb + 2.0  # +2 workspace
        breakdown = {
            "权重_gb": round(weight_gb, 2),
            "KV_gb": round(kv_gb, 2),
            "激活_gb": act_gb,
            "workspace_gb": 2.0,
            "梯度_gb": 0.0,
            "优化器_gb": 0.0,
        }

    utilization_pct = total_gb / (gpu.memory_gb) * 100
    oom_risk = total_gb > gpu.memory_gb * 0.95

    assumptions.extend(
        [
            f"GPU: {gpu.id} ({gpu.memory_gb} GB)",
            f"模型: {model.id} ({model.params_billion:.1f}B), TP={tp}",
            f"mode={params.mode}, weight_dtype={params.weight_dtype}",
            "workspace 估算: 训练 3 GB / 推理 2 GB",
            "不含 CUDA context、Fragmentation、CUDA Graph 等额外开销",
        ]
    )
    if params.use_lora:
        assumptions.append(f"LoRA rank={params.lora_rank}: base 模型冻结，仅 LoRA 参数训练")
    if params.gradient_checkpointing:
        assumptions.append("gradient_checkpointing=True: 激活估算 ×0.25")
    if oom_risk:
        warnings.append(
            f"估算显存 {total_gb:.1f} GB > {gpu.memory_gb} GB × 95%，OOM 风险较高；可增大 TP 或降低 batch"
        )

    return CalcResult(
        value={
            "summary": {
                "total_gb": round(total_gb, 2),
                "hbm_gb": gpu.memory_gb,
                "utilization_pct": round(utilization_pct, 2),
                "oom_risk": oom_risk,
            },
            "breakdown": breakdown,
        },
        assumptions=assumptions,
        warnings=warnings,
        provenance=provenance,
    )
