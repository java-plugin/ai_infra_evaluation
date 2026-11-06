"""TCO 计算器。

所有计算都带显式假设、警告、数据来源；任何数字可回放。

关键公式见 PROJECT_PLAN.md §5.1。
"""

from __future__ import annotations

from typing import Any

from ..catalog import CatalogError, get_gpu
from ..models import CalcResult, SourceRef, TCOBreakdown, TCOInput

# ---------------------------------------------------------------------------
# 成本系数常量 (单位: CNY)
# 标注来源; 实际值来自原书第 6 章公开区间。
# ---------------------------------------------------------------------------

NETWORK_COST_PER_GPU_CNY = 8_000  # InfiniBand / RoCE 交换机 + 网卡分摊
STORAGE_COST_PER_NODE_CNY = 150_000  # NVMe + HDD 分摊
LABOR_CNY_PER_YEAR_PER_NODE = 60_000  # SRE + 运维分摊 (含值班)
SOFTWARE_CNY_PER_YEAR_PER_NODE = 30_000  # CUDA 许可 + 平台软件分摊
HIDDEN_COST_PCT = 0.03  # 迁移/调试/备件

GPU_HOURS_PER_YEAR = 8_760.0
TOKEN_FLIPS_THRESHOLD = 1e9  # 1B tokens ≈ 多少 GPUh，用于粗略每百万 token 成本


def _gpu_power_kw(gpu_tdp_w: float) -> float:
    """GPU 功耗 kW。"""
    return gpu_tdp_w / 1000.0


def calc_tco(params: TCOInput, tokens_per_sec: float | None = None) -> CalcResult:
    """计算 TCO 及其派生指标。

    Args:
        params: TCO 输入参数。
        tokens_per_sec: 可选，用于算每百万 token 成本；若不传，该项为 None。
    """

    assumptions: list[str] = []
    warnings: list[str] = []
    provenance: list[SourceRef] = []

    # ---- 取 GPU ----
    try:
        gpu = get_gpu(params.gpu_id)
    except CatalogError as exc:
        return CalcResult(
            value={},
            assumptions=assumptions,
            warnings=[f"GPU 查找失败: {exc}"],
            provenance=provenance,
        )

    provenance.append(
        SourceRef(source=f"data/gpus.yaml#{gpu.id}", as_of=gpu.as_of, confidence=gpu.confidence)
    )

    # ---- GPU 单价 ----
    if params.gpu_price_cny is not None:
        gpu_price = params.gpu_price_cny
        assumptions.append(f"手动覆盖 GPU 单价: ¥{gpu_price:,.0f}")
    else:
        gpu_price = gpu.price_cny or 0.0
        if gpu.price_cny_min and gpu.price_cny_max:
            warnings.append(
                f"GPU 价格取中位数 ¥{gpu_price:,.0f} (区间 ¥{gpu.price_cny_min:,.0f} – ¥{gpu.price_cny_max:,.0f})"
            )

    total_gpus = params.total_gpus

    # ---- CapEx ----
    gpu_capex = gpu_price * total_gpus
    network_capex = NETWORK_COST_PER_GPU_CNY * total_gpus if params.include_network else 0.0
    storage_capex = STORAGE_COST_PER_NODE_CNY * params.nodes if params.include_storage else 0.0
    capex_total = gpu_capex + network_capex + storage_capex

    # ---- OpEx ----
    # 电力: GPU TDP * 每节点卡数 * 节点数 * 8760 * 电价 * PUE
    gpu_power_kw = _gpu_power_kw(gpu.tdp_w)
    node_power_kw = gpu_power_kw * params.gpus_per_node + 0.5  # +0.5kW 主板/内存/存储
    it_power_kw = node_power_kw * params.nodes
    facility_power_kw = it_power_kw * params.pue
    electricity_per_year = facility_power_kw * GPU_HOURS_PER_YEAR * params.electricity_cny_per_kwh

    # 托管费 (含电时电力为 0，避免重复)
    colocation_per_year = params.colocation_fee_cny_per_node_per_month * params.nodes * 12
    if params.colocation_includes_power and colocation_per_year > 0:
        electricity_per_year = 0.0
        warnings.append("colocation_includes_power=True: 电费不再单独计入")

    labor_per_year = LABOR_CNY_PER_YEAR_PER_NODE * params.nodes if params.include_labor else 0.0
    software_per_year = (
        SOFTWARE_CNY_PER_YEAR_PER_NODE * params.nodes if params.include_software else 0.0
    )
    opex_per_year = electricity_per_year + colocation_per_year + labor_per_year + software_per_year
    opex_total = opex_per_year * params.years

    # ---- 残值 ----
    residual = (
        capex_total * (params.residual_value_pct / 100.0) * (1.0 if params.years >= 3 else 0.7)
    )

    # ---- 隐藏成本 ----
    hidden = capex_total * HIDDEN_COST_PCT

    # ---- TCO 汇总 ----
    tco = capex_total + opex_total + hidden - residual

    # ---- 关键派生 ----
    utilization = params.utilization_pct / 100.0
    total_gpu_hours = total_gpus * GPU_HOURS_PER_YEAR * params.years * utilization
    per_gpu_hour = tco / total_gpu_hours if total_gpu_hours > 0 else float("inf")

    per_million_tokens = None
    if tokens_per_sec is not None and tokens_per_sec > 0:
        total_tokens = tokens_per_sec * 3600 * GPU_HOURS_PER_YEAR * params.years * utilization / 1e6
        per_million_tokens = tco / total_tokens

    # ---- 成本结构 ----
    structure = {
        "GPU": gpu_capex,
        "网络": network_capex,
        "存储": storage_capex,
        "电力_年": electricity_per_year * params.years,
        "托管_年": colocation_per_year * params.years,
        "人力_年": labor_per_year * params.years,
        "软件_年": software_per_year * params.years,
        "隐藏": hidden,
        "-残值": -residual,
    }
    total_nonnegative = sum(v for v in structure.values() if v > 0)
    structure_pct = {
        k: (v / total_nonnegative * 100.0 if v > 0 else 0.0) for k, v in structure.items()
    }

    # ---- 假设/警告补齐 ----
    assumptions.extend(
        [
            f"GPU: {gpu.id} ({gpu.memory_gb} GB, TDP {gpu.tdp_w} W)",
            f"规模: {params.nodes} 节点 × {params.gpus_per_node} GPU = {total_gpus} GPU",
            f"年限: {params.years} 年, 利用率 {params.utilization_pct:.1f}%, PUE {params.pue}",
            f"电价: ¥{params.electricity_cny_per_kwh}/kWh",
            f"CapEx 分摊: 网络 ¥{NETWORK_COST_PER_GPU_CNY:,}/GPU, 存储 ¥{STORAGE_COST_PER_NODE_CNY:,}/节点",
            f"OpEx 分摊: 人力 ¥{LABOR_CNY_PER_YEAR_PER_NODE:,}/节点/年, 软件 ¥{SOFTWARE_CNY_PER_YEAR_PER_NODE:,}/节点/年",
            f"隐藏成本: {HIDDEN_COST_PCT * 100:.0f}% CapEx",
        ]
    )
    if not params.include_network:
        warnings.append("include_network=False: 未计入网络 CapEx")
    if not params.include_storage:
        warnings.append("include_storage=False: 未计入存储 CapEx")
    if not params.include_labor:
        warnings.append("include_labor=False: 未计入人力 OpEx")
    if not params.include_software:
        warnings.append("include_software=False: 未计入软件 OpEx")
    if utilization < 0.4:
        warnings.append(f"利用率 {params.utilization_pct:.0f}% 偏低, 自建可能不划算")

    breakdown = TCOBreakdown(
        gpu_capex_cny=gpu_capex,
        network_capex_cny=network_capex,
        storage_capex_cny=storage_capex,
        capex_total_cny=capex_total,
        electricity_cny_per_year=electricity_per_year,
        colocation_cny_per_year=colocation_per_year,
        labor_cny_per_year=labor_per_year,
        software_cny_per_year=software_per_year,
        opex_total_cny_per_year=opex_per_year,
        opex_total_cny=opex_total,
        residual_cny=residual,
        hidden_cny=hidden,
        tco_total_cny=tco,
        per_gpu_hour_cny=per_gpu_hour,
        per_million_tokens_cny=per_million_tokens,
        cost_structure_pct=structure_pct,
    )

    value: dict[str, Any] = {
        **breakdown.model_dump(),
        "summary": {
            "tco_total_cny": round(tco, 2),
            "per_gpu_hour_cny": round(per_gpu_hour, 4),
            "per_million_tokens_cny": round(per_million_tokens, 4) if per_million_tokens else None,
            "gpu_count": total_gpus,
            "gpu_model": gpu.id,
            "years": params.years,
            "utilization_pct": params.utilization_pct,
        },
    }

    return CalcResult(
        value=value,
        assumptions=assumptions,
        warnings=warnings,
        provenance=provenance,
    )
