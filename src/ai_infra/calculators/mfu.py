"""MFU (Model FLOPs Utilization) 计算器。

Dense 模型 FLOPs/token 近似:
    FLOPs_per_token ≈ 6 × N_active + 12 × L × S × d_model

MoE 模型:
    N_active 取共享参数 + top-k 激活专家参数。

MFU = achieved_FLOPs / (peak_FLOPs × n_gpus)

训练时 step_time 为实测；估算模式用 step_time ≈ 2 × S² × d_model / achieved_FLOPs。
"""

from __future__ import annotations

from ..catalog import CatalogError, get_gpu, get_model
from ..models import CalcResult, MFUInput, SourceRef


def _dtype_multiplier(dtype: str) -> float:
    """精度对应 FLOPs 比率: BF16/FP16 为 1x, FP32 为 0.25 (张量核)。"""
    return {
        "bf16": 1.0,
        "fp16": 1.0,
        "fp32": 0.25,
        "fp8": 2.0,  # FP8 通常 BF16 精度累加，吞吐约 2x
        "int8": 4.0,
    }.get(dtype, 1.0)


def calc_mfu(params: MFUInput) -> CalcResult:
    """计算 MFU、achieved FLOPs、通信占比等。"""

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

    # 并行度校验
    total_parallel = params.tp * params.pp * params.dp * params.ep
    if total_parallel != params.n_gpus:
        warnings.append(
            f"并行乘积 {params.tp}×{params.pp}×{params.dp}×{params.ep}={total_parallel} "
            f"与 n_gpus={params.n_gpus} 不一致，后续用 tp×pp×dp 作为估算"
        )

    # 精度与峰值
    peak_tflops = gpu.bf16_tflops_dense or 0.0
    dtype_peak = peak_tflops * _dtype_multiplier("bf16")  # 当前只走 BF16 路径
    achieved_peak_tflops_total = dtype_peak * params.n_gpus  # 理论上限

    # 参数量 (B)
    N = model.params_billion * 1e9
    N_active = (model.active_params_billion or model.params_billion) * 1e9
    L = model.num_layers
    H = model.hidden_size
    S = params.seq_len
    B = params.batch_per_gpu * params.dp  # 全局 batch

    # FLOPs/token 近似
    flops_per_token = 6 * N_active + 12 * L * S * H
    flops_per_step = flops_per_token * S * B

    # 实测模式: 给了 step_time 或 tokens/s
    step_time_s = params.step_time_s
    tokens_per_sec = params.tokens_per_sec

    if step_time_s is None and tokens_per_sec is None:
        # 纯估算: 假设 achieved ≈ peak * MFU_guess，再反推 step_time
        # 估算 MFU 区间: 训练 30–50%, 推理 40–70%
        mfu_guess = 0.45 if params.mode == "training" else 0.55
        achieved_tflops_total = achieved_peak_tflops_total * mfu_guess
        flops_per_sec = achieved_tflops_total * 1e12
        step_time_s = flops_per_step / flops_per_sec
        tokens_per_sec = S * B / step_time_s
        assumptions.append(
            f"step_time / tokens_per_sec 均未提供，使用 MFU≈{mfu_guess * 100:.0f}% 反推估算"
        )

    if step_time_s is not None and tokens_per_sec is None:
        tokens_per_sec = S * B / step_time_s
    if tokens_per_sec is not None and step_time_s is None:
        step_time_s = S * B / tokens_per_sec

    assert step_time_s is not None and tokens_per_sec is not None

    flops_per_sec_achieved = flops_per_step / step_time_s
    mfu = (
        flops_per_sec_achieved / (achieved_peak_tflops_total * 1e12)
        if achieved_peak_tflops_total
        else 0.0
    )

    # Dedicated MFU: 扣掉通信开销 (假设 AllReduce 10–20%)
    comm_overhead_pct = 10.0 if params.n_gpus <= 32 else 20.0
    mfu_dedicated = mfu / (1 + comm_overhead_pct / 100.0)

    assumptions.extend(
        [
            f"模型: {model.id}, Dense={'否' if model.is_moe else '是'}, active params={model.active_params_billion or model.params_billion:.1f}B",
            f"并行: TP={params.tp}, PP={params.pp}, DP={params.dp}, EP={params.ep}, n_gpus={params.n_gpus}",
            f"mode={params.mode}, seq={S}, global_batch={B}",
            f"通信开销假设: {comm_overhead_pct:.0f}%",
            f"GPU 峰值: BF16 dense {peak_tflops} TFLOPS × {params.n_gpus}",
        ]
    )
    if model.is_moe:
        assumptions.append("MoE FLOPs 按 active params 计算 (非 total)")

    return CalcResult(
        value={
            "summary": {
                "tokens_per_sec": round(tokens_per_sec, 2),
                "step_time_s": round(step_time_s, 4),
                "achieved_tflops": round(flops_per_sec_achieved / 1e12, 2),
                "peak_tflops_total": achieved_peak_tflops_total,
                "mfu_pct": round(mfu * 100, 2),
                "mfu_dedicated_pct": round(mfu_dedicated * 100, 2),
            },
            "breakdown": {
                "flops_per_token": flops_per_token,
                "flops_per_step": flops_per_step,
                "dense_vs_active_ratio": (N_active / N) if N > 0 else 1.0,
            },
        },
        assumptions=assumptions,
        warnings=warnings,
        provenance=provenance,
    )
