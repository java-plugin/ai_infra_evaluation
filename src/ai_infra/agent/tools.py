"""Agent 可调用的确定性工具。

原则：LLM 只决定「调用哪个工具、传什么参数」，所有数字由这些函数产生。
"""

from __future__ import annotations

from typing import Any

from ..calculators.compare import calc_compare
from ..calculators.kv_cache import calc_kv_cache
from ..calculators.memory import calc_memory
from ..calculators.mfu import calc_mfu
from ..calculators.recommender import WorkloadInput, recommend_config
from ..calculators.tco import calc_tco
from ..catalog import load_gpus, load_models
from ..models import (
    CalcResult,
    CompareInput,
    KVCacheInput,
    MemoryInput,
    MFUInput,
    TCOInput,
)
from .rag import search_knowledge


def _gpu_ids() -> list[str]:
    return list(load_gpus().keys())


def _model_ids() -> list[str]:
    return list(load_models().keys())


_GPU_ALIASES = {
    "h100": "h100-sxm5-80gb",
    "h100-sxm5": "h100-sxm5-80gb",
    "h800": "h800-sxm5-80gb",
    "a100": "a100-sxm4-80gb",
    "a800": "a100-sxm4-80gb",
    "l40s": "l40s-pcie-48gb",
    "l40": "l40s-pcie-48gb",
    "910b": "910b-sxm-64gb",
    "ascend": "910b-sxm-64gb",
}

_MODEL_ALIASES = {
    "llama3-70b": "llama3-70b",
    "llama-3-70b": "llama3-70b",
    "70b": "llama3-70b",
    "llama3-8b": "llama3-8b",
    "llama-3-8b": "llama3-8b",
    "8b": "llama3-8b",
    "deepseek-v3": "deepseek-v3-671b",
    "deepseek": "deepseek-v3-671b",
    "671b": "deepseek-v3-671b",
}


def normalize_gpu(value: str) -> str:
    raw = (value or "").strip().lower().replace(" ", "-")
    gpus = _gpu_ids()
    if raw in gpus:
        return raw
    for key, target in _GPU_ALIASES.items():
        if key in raw and target in gpus:
            return target
    raise ValueError(f"未知 GPU {value!r}。可用: {gpus}")


def normalize_model(value: str) -> str:
    raw = (value or "").strip().lower().replace(" ", "-")
    models = _model_ids()
    if raw in models:
        return raw
    # 先匹配更具体的 70b，再 8b
    for key in (
        "llama3-70b",
        "llama-3-70b",
        "70b",
        "llama3-8b",
        "llama-3-8b",
        "8b",
        "deepseek-v3",
        "deepseek",
        "671b",
    ):
        if key in raw:
            target = _MODEL_ALIASES[key]
            if target in models:
                return target
    raise ValueError(f"未知模型 {value!r}。可用: {models}")


def _compact(result: CalcResult) -> dict[str, Any]:
    value = result.value or {}
    return {
        "summary": value.get("summary"),
        "rows": value.get("rows"),
        "reasons": value.get("reasons"),
        "breakdown": value.get("breakdown"),
        "assumptions": result.assumptions,
        "warnings": result.warnings,
        "provenance": [p.model_dump() for p in result.provenance],
    }


def _tco_input(args: dict[str, Any]) -> TCOInput:
    return TCOInput(
        nodes=int(args.get("nodes", 8)),
        gpus_per_node=int(args.get("gpus_per_node", 8)),
        gpu_id=normalize_gpu(str(args.get("gpu_id", "h100-sxm5-80gb"))),
        years=int(args.get("years", 3)),
        utilization_pct=float(args.get("utilization_pct", 60.0)),
        electricity_cny_per_kwh=float(args.get("electricity_cny_per_kwh", 0.8)),
        pue=float(args.get("pue", 1.2)),
        residual_value_pct=float(args.get("residual_value_pct", 0.0)),
    )


def _knowledge_result(hits: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """给 LLM 的知识结果：正文 + 命中行 + 整表 JSON（表格题必须能引用完整行列）。"""

    out: list[dict[str, Any]] = []
    for h in hits:
        item: dict[str, Any] = {
            "doc_type": h.get("doc_type"),
            "chapter": h.get("chapter"),
            "section": h.get("section"),
            "title": h.get("title"),
            "text": h.get("text"),
            "page": h.get("page"),
            "source": h.get("source"),
            "score": h.get("score"),
        }
        table = h.get("table")
        if table:
            item["table"] = {
                "title": table.get("title"),
                "headers": table.get("headers"),
                "rows": table.get("rows"),
            }
            item["matched_row"] = h.get("row")
        out.append(item)
    return out


def _dispatch(name: str, args: dict[str, Any]) -> dict[str, Any]:
    if name == "calc_tco":
        return _compact(calc_tco(_tco_input(args)))

    if name == "calc_compare":
        return _compact(calc_compare(CompareInput(base=_tco_input(args))))

    if name == "calc_mfu":
        return _compact(
            calc_mfu(
                MFUInput(
                    model_id=normalize_model(str(args.get("model_id", "llama3-70b"))),
                    gpu_id=normalize_gpu(str(args.get("gpu_id", "h100-sxm5-80gb"))),
                    n_gpus=int(args.get("n_gpus", 64)),
                    tp=int(args.get("tp", 8)),
                    pp=int(args.get("pp", 1)),
                    dp=int(args.get("dp", 8)),
                    mode=str(args.get("mode", "training")),
                    batch_per_gpu=int(args.get("batch_per_gpu", 1)),
                    seq_len=int(args.get("seq_len", 4096)),
                    step_time_s=args.get("step_time_s"),
                    tokens_per_sec=args.get("tokens_per_sec"),
                )
            )
        )

    if name == "calc_kv_cache":
        return _compact(
            calc_kv_cache(
                KVCacheInput(
                    model_id=normalize_model(str(args.get("model_id", "llama3-70b"))),
                    seq_len=int(args.get("seq_len", 4096)),
                    batch=int(args.get("batch", 1)),
                    dtype=str(args.get("dtype", "bf16")),
                ),
                n_gpus=int(args.get("n_gpus", 1)),
            )
        )

    if name == "calc_memory":
        return _compact(
            calc_memory(
                MemoryInput(
                    model_id=normalize_model(str(args.get("model_id", "llama3-70b"))),
                    gpu_id=normalize_gpu(str(args.get("gpu_id", "h100-sxm5-80gb"))),
                    mode=str(args.get("mode", "inference")),
                    tp=int(args.get("tp", 8)),
                    seq_len=int(args.get("seq_len", 4096)),
                    batch=int(args.get("batch", 1)),
                    use_lora=bool(args.get("use_lora", False)),
                )
            )
        )

    if name == "recommend_config":
        return _compact(
            recommend_config(
                WorkloadInput(
                    business_type=str(args.get("business_type", "general")),
                    model_size_billion=float(args.get("model_size_billion", 7.0)),
                    qps=float(args.get("qps", 100.0)),
                    ttft_slo_ms=int(args.get("ttft_slo_ms", 3000)),
                    tpot_slo_ms=int(args.get("tpot_slo_ms", 50)),
                    privacy_need=str(args.get("privacy_need", "low")),
                    team_size=int(args.get("team_size", 5)),
                )
            )
        )

    if name == "search_knowledge":
        doc_type = str(args.get("doc_type") or "").strip() or None
        chapter = str(args.get("chapter") or "").strip() or None
        query = str(args.get("query", ""))
        hits = search_knowledge(
            query, int(args.get("top_k", 4)), doc_type=doc_type, chapter=chapter
        )
        return {"query": query, "results": _knowledge_result(hits)}

    raise ValueError(f"未知工具 {name}")


def dispatch_tool(name: str, args: dict[str, Any]) -> dict[str, Any]:
    """执行工具，永远返回 dict（错误也包装成 dict，方便模型自我修正）。"""

    try:
        return {"ok": True, "result": _dispatch(name, args)}
    except Exception as exc:  # noqa: BLE001 - 工具边界必须兜住
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}


TOOL_SCHEMAS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "calc_tco",
            "description": "计算自建集群的 TCO、每 GPU 小时成本、每百万 token 成本。数字由确定性引擎产生。",
            "parameters": {
                "type": "object",
                "properties": {
                    "nodes": {"type": "integer", "description": "节点数，8 卡机填 8"},
                    "gpus_per_node": {"type": "integer", "description": "每节点 GPU 数，通常 8"},
                    "gpu_id": {
                        "type": "string",
                        "description": "GPU 型号，如 h100-sxm5-80gb / h800-sxm5-80gb / a100-sxm4-80gb / l40s-pcie-48gb / 910b-sxm-64gb",
                    },
                    "years": {"type": "integer", "description": "使用年限"},
                    "utilization_pct": {"type": "number", "description": "利用率百分比 5-100"},
                    "electricity_cny_per_kwh": {"type": "number", "description": "电价，默认 0.8"},
                    "pue": {"type": "number", "description": "PUE，默认 1.2"},
                },
                "required": ["nodes", "gpus_per_node", "gpu_id", "years", "utilization_pct"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "calc_compare",
            "description": "对比自建与云按需/1年预留/3年预留/Spot/租赁的每 GPU 小时成本，并给出盈亏平衡利用率。",
            "parameters": {
                "type": "object",
                "properties": {
                    "nodes": {"type": "integer"},
                    "gpus_per_node": {"type": "integer"},
                    "gpu_id": {"type": "string"},
                    "years": {"type": "integer"},
                    "utilization_pct": {"type": "number"},
                },
                "required": ["nodes", "gpus_per_node", "gpu_id", "years", "utilization_pct"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "calc_mfu",
            "description": "计算训练或推理的 MFU、tokens/s、step time。Dense 与 MoE 均支持。",
            "parameters": {
                "type": "object",
                "properties": {
                    "model_id": {
                        "type": "string",
                        "description": "llama3-8b / llama3-70b / deepseek-v3-671b",
                    },
                    "gpu_id": {"type": "string"},
                    "n_gpus": {"type": "integer"},
                    "tp": {"type": "integer"},
                    "pp": {"type": "integer"},
                    "dp": {"type": "integer"},
                    "mode": {"type": "string", "enum": ["training", "inference"]},
                    "batch_per_gpu": {"type": "integer"},
                    "seq_len": {"type": "integer"},
                    "step_time_s": {"type": "number", "description": "可选，实测 step time"},
                },
                "required": ["model_id", "gpu_id", "n_gpus"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "calc_kv_cache",
            "description": "计算 KV Cache 显存占用：每 token、每请求、总占用。",
            "parameters": {
                "type": "object",
                "properties": {
                    "model_id": {"type": "string"},
                    "seq_len": {"type": "integer"},
                    "batch": {"type": "integer"},
                    "dtype": {"type": "string", "enum": ["fp16", "bf16", "fp8", "int8"]},
                    "n_gpus": {"type": "integer"},
                },
                "required": ["model_id", "seq_len"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "calc_memory",
            "description": "计算训练/推理的单卡显存构成与 OOM 风险。",
            "parameters": {
                "type": "object",
                "properties": {
                    "model_id": {"type": "string"},
                    "gpu_id": {"type": "string"},
                    "mode": {"type": "string", "enum": ["training", "inference"]},
                    "tp": {"type": "integer"},
                    "seq_len": {"type": "integer"},
                    "batch": {"type": "integer"},
                    "use_lora": {"type": "boolean"},
                },
                "required": ["model_id", "gpu_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "recommend_config",
            "description": "根据业务类型、模型规模、QPS、SLO、隐私要求、团队规模给出可解释的选型建议。",
            "parameters": {
                "type": "object",
                "properties": {
                    "business_type": {"type": "string"},
                    "model_size_billion": {"type": "number"},
                    "qps": {"type": "number"},
                    "ttft_slo_ms": {"type": "integer"},
                    "tpot_slo_ms": {"type": "integer"},
                    "privacy_need": {"type": "string", "enum": ["none", "low", "high", "max"]},
                    "team_size": {"type": "integer"},
                },
                "required": ["business_type", "model_size_billion", "qps"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_knowledge",
            "description": (
                "检索《AI Infra 全栈实战》书籍知识库（正文 + 表格 + 图表），"
                "用于查询厂商架构、集群规模、价格、选型对照等事实。"
                "返回命中片段的章节、页码，表格类命中还会带回完整表头与行 JSON。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "检索问题，尽量带上厂商名和指标，如「字节跳动最大集群规模」",
                    },
                    "top_k": {"type": "integer", "default": 4},
                    "doc_type": {
                        "type": "string",
                        "enum": ["text", "table_row", "table_summary", "table_group", "figure"],
                        "description": "可选，限定片段类型；查具体数值可用 table_row",
                    },
                    "chapter": {
                        "type": "string",
                        "description": "可选，限定章节，如「第12章」",
                    },
                },
                "required": ["query"],
            },
        },
    },
]
