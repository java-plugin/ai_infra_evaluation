"""Pydantic 输入 / 输出协议。

字段命名规则: **所有带物理量的字段必须带单位后缀**，避免裸数字。
示例: ``price_cny``, ``tdp_w``, ``memory_gb``, ``bandwidth_gbps``,
``tflops_bf16``, ``utilization_pct``。
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

# ---------------------------------------------------------------------------
# 通用元信息
# ---------------------------------------------------------------------------


Confidence = Literal["high", "medium", "low"]


class SourceRef(BaseModel):
    """一条可追溯的数据来源。

    ``source`` 自由文本，建议写成 ``<path>#<id>`` 便于定位，例如
    ``data/gpus.yaml#h100-sxm5-80gb``。
    """

    source: str
    as_of: str = Field(..., description="数据截止日期，YYYY-MM 或 YYYY-MM-DD")
    confidence: Confidence = "medium"
    note: str | None = None

    @field_validator("as_of")
    @classmethod
    def _validate_as_of(cls, v: str) -> str:
        # 宽松校验: YYYY-MM 或 YYYY-MM-DD 都允许；非法值抛错。
        for fmt in ("%Y-%m-%d", "%Y-%m"):
            try:
                datetime.strptime(v, fmt)
                return v
            except ValueError:
                continue
        raise ValueError(f"as_of must be YYYY-MM or YYYY-MM-DD, got {v!r}")


class CalcResult(BaseModel):
    """所有计算器的统一返回。

    任何一个数字都必须能追溯到 ``provenance`` 里的某条 SourceRef，
    任何一个计算都必须显式写出 ``assumptions``。
    """

    model_config = ConfigDict(extra="forbid")

    value: dict[str, Any]
    assumptions: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    provenance: list[SourceRef] = Field(default_factory=list)
    trace_id: str = Field(default_factory=lambda: f"tr_{uuid.uuid4().hex[:12]}")


# ---------------------------------------------------------------------------
# GPU / 数据目录里的条目
# ---------------------------------------------------------------------------


class GPU(BaseModel):
    """一条 GPU 规格记录 (来自 data/gpus.yaml)。"""

    model_config = ConfigDict(extra="allow")  # 允许后续扩展字段

    id: str
    vendor: str
    memory_gb: float
    memory_type: str
    bf16_tflops_dense: float | None = None
    bf16_tflops_sparse: float | None = None
    fp16_tflops_dense: float | None = None
    fp16_tflops_sparse: float | None = None
    tdp_w: float
    price_cny_min: float | None = None
    price_cny_max: float | None = None
    price_cny: float | None = None  # 便捷字段，取 min/max 中位数
    as_of: str
    source: str
    confidence: Confidence = "medium"


class Model(BaseModel):
    """一条模型结构记录 (来自 data/models.yaml)。"""

    model_config = ConfigDict(extra="allow")

    id: str
    family: str
    params_billion: float  # 总参数量
    active_params_billion: float | None = None  # MoE 激活参数量；Dense 等于 params_billion
    num_layers: int
    hidden_size: int
    num_attention_heads: int
    num_kv_heads: int | None = None  # GQA/MQA 专用；None 表示等于 num_attention_heads
    head_dim: int | None = None
    vocab_size: int | None = None
    # GQA / MLA 标记
    is_moe: bool = False
    num_experts: int | None = None
    top_k: int | None = None
    # 默认精度 / 上下文
    default_dtype: Literal["fp16", "bf16", "fp8"] = "bf16"
    max_seq_len: int = 4096
    as_of: str
    source: str
    confidence: Confidence = "medium"


# ---------------------------------------------------------------------------
# TCO
# ---------------------------------------------------------------------------


class TCOInput(BaseModel):
    """TCO 计算器输入。

    强 schema 强制区分 ``nodes`` 与 ``gpus_per_node``，避免原书中
    「64 台 DGX」与「64 张卡」混用。
    """

    model_config = ConfigDict(extra="forbid")

    # 规模
    nodes: int = Field(..., ge=1, description="物理节点数")
    gpus_per_node: int = Field(..., ge=1, description="每节点 GPU 数")
    gpu_id: str = Field(..., description="GPU 型号 id, 对应 data/gpus.yaml")

    # 时间与利用率
    years: int = Field(3, ge=1, le=10)
    utilization_pct: float = Field(60.0, ge=5.0, le=100.0)

    # 电价与 PUE
    electricity_cny_per_kwh: float = Field(0.8, gt=0.0)
    pue: float = Field(1.2, ge=1.0, le=2.5)

    # 可选成本项开关
    include_network: bool = True
    include_storage: bool = True
    include_labor: bool = True
    include_software: bool = True

    # 托管费与电费互斥
    colocation_fee_cny_per_node_per_month: float = 0.0
    colocation_includes_power: bool = Field(
        False,
        description="为 True 时 electricity 不再单独计费，避免重复。",
    )

    # 残值 (0 表示不考虑)
    residual_value_pct: float = Field(0.0, ge=0.0, le=90.0)

    # 可选: 手动覆盖 GPU 单价
    gpu_price_cny: float | None = None

    @property
    def total_gpus(self) -> int:
        return self.nodes * self.gpus_per_node


class TCOBreakdown(BaseModel):
    """TCO 分项结果。"""

    model_config = ConfigDict(extra="forbid")

    # CapEx (一次性)
    gpu_capex_cny: float
    network_capex_cny: float
    storage_capex_cny: float
    capex_total_cny: float

    # OpEx (每年)
    electricity_cny_per_year: float
    colocation_cny_per_year: float
    labor_cny_per_year: float
    software_cny_per_year: float
    opex_total_cny_per_year: float

    # 汇总
    opex_total_cny: float  # OpEx × years
    residual_cny: float
    hidden_cny: float  # 预留 3% 隐藏成本 (迁移、调试、备件)
    tco_total_cny: float

    # 关键派生指标
    per_gpu_hour_cny: float
    per_million_tokens_cny: float | None = None  # 依赖 tokens/s 估算
    cost_structure_pct: dict[str, float]  # 各项占比


# ---------------------------------------------------------------------------
# MFU
# ---------------------------------------------------------------------------


class MFUInput(BaseModel):
    """MFU 计算器输入。"""

    model_config = ConfigDict(extra="forbid")

    model_id: str
    gpu_id: str
    n_gpus: int = Field(..., ge=1)

    # 并行配置
    tp: int = Field(1, ge=1)
    pp: int = Field(1, ge=1)
    dp: int = Field(1, ge=1)
    ep: int = Field(1, ge=1)  # MoE expert parallel

    # 推理或训练
    mode: Literal["training", "inference"] = "training"

    # batch / seq
    batch_per_gpu: int = 1
    seq_len: int = 4096
    micro_batch: int | None = None  # 训练可用; None 时用 batch_per_gpu

    # 二选一: 实测或估算
    step_time_s: float | None = None
    tokens_per_sec: float | None = None


# ---------------------------------------------------------------------------
# KV Cache
# ---------------------------------------------------------------------------


class KVCacheInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    model_id: str
    seq_len: int = Field(4096, ge=1)
    batch: int = Field(1, ge=1)
    dtype: Literal["fp16", "bf16", "fp8", "int8"] = "bf16"
    # 可选覆盖; 若给则忽略 model_id 里的默认值
    kv_heads: int | None = None
    head_dim: int | None = None
    # 页式 KV 开销估算 (vLLM 等框架)
    page_size: int = 16
    page_overhead_pct: float = 5.0


# ---------------------------------------------------------------------------
# Memory
# ---------------------------------------------------------------------------


class MemoryInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    model_id: str
    gpu_id: str
    mode: Literal["training", "inference"] = "inference"

    # 训练专用
    optimizer: Literal["adamw", "sgd", "lamb"] = "adamw"
    zero_stage: Literal["none", "1", "2", "3"] = "none"
    use_lora: bool = False
    lora_rank: int = 8

    # 精度 / 并行
    weight_dtype: Literal["fp32", "fp16", "bf16", "int8"] = "bf16"
    tp: int = 1
    gradient_checkpointing: bool = False

    # 推理专用
    kv_dtype: Literal["fp16", "bf16", "fp8", "int8"] = "bf16"
    seq_len: int = 4096
    batch: int = 1


# ---------------------------------------------------------------------------
# 部署模式
# ---------------------------------------------------------------------------


DeploymentMode = Literal[
    "on_prem",  # 自建
    "cloud_ondemand",  # 云按需
    "cloud_1y_reserved",
    "cloud_3y_reserved",
    "cloud_spot",
    "hybrid",  # 混合
    "rental",  # 租赁
]


class CompareInput(BaseModel):
    """自建 vs 各种云模式的对比输入。"""

    model_config = ConfigDict(extra="forbid")

    base: TCOInput
    # 可选: 手动覆盖云价格 (默认从 data/cloud_prices.yaml 取)
    cloud_ondemand_cny_per_gpu_hour: float | None = None
    cloud_1y_reserved_cny_per_gpu_hour: float | None = None
    cloud_3y_reserved_cny_per_gpu_hour: float | None = None
    cloud_spot_cny_per_gpu_hour: float | None = None
    rental_cny_per_gpu_per_month: float | None = None
