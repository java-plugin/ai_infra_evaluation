"""Golden tests for TCO.

基准场景: 8 节点 × 8 H100 = 64 GPU, 3 年, 60% 利用率, 电价 ¥0.8, PUE 1.2

手动基准计算说明 (用于对齐):
    GPU 单价 = (200k + 250k) / 2 = 225k
    GPU CapEx = 64 × 225k = 14,400,000
    网络 CapEx = 8k × 64 = 512,000
    存储 CapEx = 150k × 8 = 1,200,000
    CapEx 合计 = 16,112,000

    GPU TDP = 700W, node_power = 700*8 + 500 = 6100W = 6.1kW
    facility_power = 6.1 * 8 * 1.2 = 58.56 kW
    electricity/year = 58.56 * 8760 * 0.8 = 410,402
    labor/year = 60k * 8 = 480,000
    software/year = 30k * 8 = 240,000
    colocation/year = 0 (未给)
    OpEx/year = 1,130,402
    OpEx 3 年 = 3,391,206

    hidden = 16,112,000 * 0.03 = 483,360
    residual = 16,112,000 * 0.05 * 1.0 = 805,600 (默认 residual_value_pct=5, years=3)

    TCO ≈ 16,112,000 + 3,391,206 + 483,360 - 805,600 ≈ 19,180,966

    total GPUh = 64 * 8760 * 3 * 0.6 = 1,013,760
    per_gpu_hour ≈ 19,180,966 / 1,013,760 ≈ ¥18.92
"""

from __future__ import annotations

from ai_infra.calculators.tco import calc_tco
from ai_infra.models import TCOInput


def test_tco_8x8_h100_3y_60pct() -> None:
    params = TCOInput(
        nodes=8,
        gpus_per_node=8,
        gpu_id="h100-sxm5-80gb",
        years=3,
        utilization_pct=60.0,
        electricity_cny_per_kwh=0.8,
        pue=1.2,
        residual_value_pct=5.0,
    )
    result = calc_tco(params)

    assert result.value, "计算不应返回空"
    s = result.value["summary"]

    assert s["gpu_count"] == 64
    assert s["gpu_model"] == "h100-sxm5-80gb"
    assert s["years"] == 3

    # 基准: TCO ~19.2M, 误差 ±3%
    assert 18_600_000 <= s["tco_total_cny"] <= 19_800_000, f"TCO 偏离: {s['tco_total_cny']:,.0f}"
    assert 18.0 <= s["per_gpu_hour_cny"] <= 19.8, f"per_gpu_hour 偏离: {s['per_gpu_hour_cny']}"

    # 必须有假设和 provenance
    assert result.assumptions, "缺少 assumptions"
    assert result.provenance, "缺少 provenance"
    assert any("h100-sxm5-80gb" in p.source for p in result.provenance)

    # cost structure 加起来约 100%
    structure = result.value["cost_structure_pct"]
    # 去掉负残值项后加起来
    total_pct = sum(v for k, v in structure.items() if v > 0)
    assert abs(total_pct - 100.0) < 1.0, f"成本结构占比之和偏离 100%: {total_pct}"


def test_tco_utilization_monotone() -> None:
    """利用率越高, 每 GPUh 成本应该越低 (属性测试)."""
    base_kwargs = dict(
        nodes=4,
        gpus_per_node=8,
        gpu_id="h100-sxm5-80gb",
        years=3,
        electricity_cny_per_kwh=0.8,
        pue=1.2,
        residual_value_pct=5.0,
    )
    prev = float("inf")
    for util in (20, 40, 60, 80, 100):
        r = calc_tco(TCOInput(**base_kwargs, utilization_pct=float(util)))
        cur = r.value["per_gpu_hour_cny"]
        assert cur <= prev + 1e-6, f"利用率 {util}% 反而更贵: {cur} vs {prev}"
        prev = cur
