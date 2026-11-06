"""KV Cache 计算器。

KV_bytes = 2 × L × H_kv × d_head × S × B × dtype_bytes × (1 + page_overhead)

max_concurrency = (HBM_gpu - weights_gpu - activations_gpu - workspace_gpu) / KV_per_request_gpu
"""

from __future__ import annotations

from ..catalog import CatalogError, get_model
from ..models import CalcResult, KVCacheInput, SourceRef

_DTYPE_BYTES = {"fp16": 2, "bf16": 2, "fp8": 1, "int8": 1}


def calc_kv_cache(params: KVCacheInput, n_gpus: int = 1) -> CalcResult:
    assumptions: list[str] = []
    warnings: list[str] = []
    provenance: list[SourceRef] = []

    try:
        model = get_model(params.model_id)
    except CatalogError as exc:
        return CalcResult(
            value={}, assumptions=assumptions, warnings=[f"查找失败: {exc}"], provenance=provenance
        )

    provenance.append(
        SourceRef(
            source=f"data/models.yaml#{model.id}", as_of=model.as_of, confidence=model.confidence
        )
    )

    L = model.num_layers
    H_kv = params.kv_heads or model.num_kv_heads or model.num_attention_heads
    head_dim = params.head_dim or (model.hidden_size // model.num_attention_heads)
    S = params.seq_len
    B = params.batch
    dtype_bytes = _DTYPE_BYTES.get(params.dtype, 2)
    overhead = params.page_overhead_pct / 100.0

    # 单 token KV
    kv_per_token = 2 * L * H_kv * head_dim * dtype_bytes * (1 + overhead)
    # 单请求 (整个序列)
    kv_per_request = kv_per_token * S
    # batch 总 KV
    kv_total = kv_per_request * B
    # 单卡分摊
    kv_per_gpu = kv_total / n_gpus

    assumptions.extend(
        [
            f"模型: {model.id}, L={L}, H_kv={H_kv}, head_dim={head_dim}",
            f"dtype={params.dtype} ({dtype_bytes} B/elem), page_overhead={overhead * 100:.0f}%",
            f"n_gpus={n_gpus}, seq_len={S}, batch={B}",
            "不含权重、激活、workspace；仅 KV Cache",
        ]
    )

    if H_kv != model.num_attention_heads:
        assumptions.append(
            f"GQA/MQA: KV heads={H_kv} < attention heads={model.num_attention_heads}, 节省 KV {model.num_attention_heads / H_kv:.1f}×"
        )

    return CalcResult(
        value={
            "summary": {
                "kv_per_token_bytes": round(kv_per_token, 2),
                "kv_per_request_mb": round(kv_per_request / 1024 / 1024, 2),
                "kv_total_gb": round(kv_total / 1024 / 1024 / 1024, 3),
                "kv_per_gpu_gb": round(kv_per_gpu / 1024 / 1024 / 1024, 3),
            },
            "breakdown": {
                "L": L,
                "H_kv": H_kv,
                "head_dim": head_dim,
                "seq_len": S,
                "batch": B,
                "dtype_bytes": dtype_bytes,
            },
        },
        assumptions=assumptions,
        warnings=warnings,
        provenance=provenance,
    )
