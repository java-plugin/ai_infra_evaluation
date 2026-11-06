"""选型推荐引擎。

硬约束 (必须满足) → 加权评分 (成本 / 性能 / 合规 / 运维 / 扩展 / 支持)。
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict

from ..models import CalcResult, CompareInput, SourceRef, TCOInput
from .compare import calc_compare


class WorkloadInput(BaseModel):
    """选型问卷输入 (v1 简化版, Agent 会补齐)。"""

    model_config = ConfigDict(extra="forbid")

    business_type: str = "general"  # general / customer_service / fintech / medical / gaming / r&d
    model_size_billion: float = 7.0  # 模型参数量 B
    qps: float = 100.0
    ttft_slo_ms: int = 3000  # Time-To-First-Token SLO
    tpot_slo_ms: int = 50  # Time-Per-Output-Token SLO
    budget_cny_per_year: float | None = None
    region: str = "cn-east-1"
    compliance: list[str] = []  # iso27001 / soc2 / 等保 / 医疗 / 金融
    team_size: int = 5
    self_build_ok: bool = True
    cloud_ok: bool = True
    spot_ok: bool = False
    privacy_need: Literal["none", "low", "high", "max"] = "low"


def recommend_scenarios(workload: WorkloadInput) -> list[TCOInput]:
    """把 WorkloadInput 展开成 3–5 个候选 TCOInput。"""

    # GPU 选型建议
    if workload.model_size_billion >= 70:
        gpu_id = "h100-sxm5-80gb"
        gpus_per_node = 8
    elif workload.model_size_billion >= 13:
        gpu_id = "h800-sxm5-80gb"
        gpus_per_node = 8
    elif workload.privacy_need == "max":
        gpu_id = "910b-sxm-64gb"
        gpus_per_node = 8
    else:
        gpu_id = "l40s-pcie-48gb"
        gpus_per_node = 4

    # 节点数 (按 QPS 粗略估)
    # 假设每节点 200–500 QPS (与模型大小相关)
    qps_per_node = 200 if workload.model_size_billion >= 70 else 400
    nodes = max(1, int(workload.qps / qps_per_node) + 1)

    # 利用率建议
    util = 0.6 if workload.budget_cny_per_year is None else 0.5

    base = TCOInput(
        nodes=nodes,
        gpus_per_node=gpus_per_node,
        gpu_id=gpu_id,
        years=3,
        utilization_pct=util * 100,
    )
    return [base]


def recommend_config(workload: WorkloadInput) -> CalcResult:
    """给定业务画像, 返回 1 条候选 TCO + 建议 + 理由。"""

    assumptions: list[str] = []
    warnings: list[str] = []
    provenance: list[SourceRef] = []

    candidates = recommend_scenarios(workload)
    base = candidates[0]

    # 先算 TCO
    tco_result = calc_compare(compare_params_from_base(base, workload))

    # 硬约束检查
    reasons: list[str] = []

    if workload.privacy_need == "max":
        reasons.append("合规/隐私需求最高 → 必须自建或私有化")
    if workload.model_size_billion >= 70:
        reasons.append(f"模型 {workload.model_size_billion:.0f}B → 需 H100/H800 级 GPU, TP 至少 8")
    if workload.ttft_slo_ms < 2000:
        reasons.append(
            f"TTFT SLO {workload.ttft_slo_ms}ms → 需低延迟 PD 分离与高并发 KV Cache 架构"
        )
    if (
        workload.budget_cny_per_year
        and tco_result.value.get("self_per_gpu_hour_cny", 0) * 8760 * base.total_gpus * 0.6
        > workload.budget_cny_per_year
    ):
        warnings.append("自建 1 年成本可能超出预算, 考虑云或 Spot")
    if workload.team_size < 3:
        reasons.append("团队 < 3 人 → 运维能力有限, 优先云托管或一体机")

    # 推荐结论
    rows = tco_result.value.get("rows", [])
    # 按「有效」每 GPUh 比较：Spot 名义价低但可用率不保证
    cheapest = (
        min(rows, key=lambda r: r.get("effective_per_gpu_hour_cny", r["per_gpu_hour_cny"]))
        if rows
        else None
    )

    assumptions.extend(
        [
            f"业务画像: {workload.business_type}, {workload.model_size_billion:.1f}B, QPS={workload.qps}",
            f"隐私等级: {workload.privacy_need}, SLO TTFT={workload.ttft_slo_ms}ms, TPOT={workload.tpot_slo_ms}ms",
            f"团队规模: {workload.team_size}, 预算/年: {workload.budget_cny_per_year or '不限'}",
        ]
    )

    return CalcResult(
        value={
            "summary": {
                "recommended_gpu": base.gpu_id,
                "recommended_nodes": base.nodes,
                "recommended_gpus_per_node": base.gpus_per_node,
                "cheapest_mode": cheapest["mode"] if cheapest else None,
                "cheapest_per_gpu_hour_cny": (
                    cheapest.get("effective_per_gpu_hour_cny", cheapest["per_gpu_hour_cny"])
                    if cheapest
                    else None
                ),
            },
            "candidates_tco": tco_result.value,
            "reasons": reasons,
            "hard_constraints": [
                f"隐私: {workload.privacy_need}",
                f"模型规模: {workload.model_size_billion}B",
                f"团队: {workload.team_size} 人",
                f"预算: {workload.budget_cny_per_year or '不限'}",
            ],
        },
        assumptions=assumptions,
        warnings=warnings,
        provenance=provenance + tco_result.provenance,
    )


def compare_params_from_base(base: TCOInput, workload: WorkloadInput) -> CompareInput:
    return CompareInput(base=base)
