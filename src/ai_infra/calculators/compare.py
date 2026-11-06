"""部署模式对比。

自建 vs 云按需 / 1 年预留 / 3 年预留 / Spot / 租赁。

盈亏平衡利用率 U*: 使自建每 GPUh 等于云每 GPUh 的利用率。
"""

from __future__ import annotations

from ..models import CalcResult, CompareInput, DeploymentMode, SourceRef
from .tco import calc_tco

# 默认云参考价 (CNY / GPU-hour / GPU-month)
# 单位: 每 GPUh (for on-demand/reserved/spot) 或 每 GPU/月 (for rental)
_DEFAULT_CLOUD_PRICES: dict[str, float] = {
    "cloud_ondemand": 30.0,  # H100 按需 ~ ¥30/GPUh
    "cloud_1y_reserved": 18.0,  # 1 年预留 ~ ¥18/GPUh
    "cloud_3y_reserved": 12.0,  # 3 年预留 ~ ¥12/GPUh
    "cloud_spot": 8.0,  # Spot 均价
    "rental_per_gpu_per_month": 4000.0,  # 按月租赁
}

CLOUD_AS_OF = "2025-06"
CLOUD_SOURCE = "公开渠道价, 随供需波动"


def _cloud_mode_prices(inputs: CompareInput) -> dict[DeploymentMode, float | None]:
    return {
        "on_prem": None,
        "cloud_ondemand": inputs.cloud_ondemand_cny_per_gpu_hour
        or _DEFAULT_CLOUD_PRICES["cloud_ondemand"],
        "cloud_1y_reserved": inputs.cloud_1y_reserved_cny_per_gpu_hour
        or _DEFAULT_CLOUD_PRICES["cloud_1y_reserved"],
        "cloud_3y_reserved": inputs.cloud_3y_reserved_cny_per_gpu_hour
        or _DEFAULT_CLOUD_PRICES["cloud_3y_reserved"],
        "cloud_spot": inputs.cloud_spot_cny_per_gpu_hour or _DEFAULT_CLOUD_PRICES["cloud_spot"],
        "rental": None,
        "hybrid": None,
    }


def calc_compare(params: CompareInput) -> CalcResult:
    assumptions: list[str] = []
    warnings: list[str] = []
    provenance: list[SourceRef] = [
        SourceRef(source=CLOUD_SOURCE, as_of=CLOUD_AS_OF, confidence="medium")
    ]

    # 自建
    self_build = calc_tco(params.base)
    if not self_build.value:
        return self_build  # GPU 查找失败等
    self_per_gpu_hour = self_build.value["per_gpu_hour_cny"]
    total_gpus = params.base.total_gpus
    years = params.base.years

    # 云方案
    prices = _cloud_mode_prices(params)
    total_gpu_hours = total_gpus * 8760.0 * years * (params.base.utilization_pct / 100.0)

    rows: list[dict[str, float | str]] = []
    rows.append(
        {
            "mode": "自建 (on-prem)",
            "per_gpu_hour_cny": round(self_per_gpu_hour, 2),
            "effective_per_gpu_hour_cny": round(self_per_gpu_hour, 2),
            "tco_cny": round(self_build.value["tco_total_cny"], 0),
            "notes": "含 CapEx + OpEx + 隐藏成本 - 残值",
        }
    )

    for mode, price in prices.items():
        if mode == "on_prem" or price is None:
            continue
        if mode == "rental":
            # 租赁: 每 GPU/月 × 12 × 年 × GPU 数
            rental = (
                params.rental_cny_per_gpu_per_month
                or _DEFAULT_CLOUD_PRICES["rental_per_gpu_per_month"]
            )
            total = rental * 12 * years * total_gpus
            per_hour = total / total_gpu_hours if total_gpu_hours > 0 else float("inf")
            rows.append(
                {
                    "mode": "按月租赁",
                    "per_gpu_hour_cny": round(per_hour, 2),
                    "effective_per_gpu_hour_cny": round(per_hour, 2),
                    "tco_cny": round(total, 0),
                    "notes": f"¥{rental:,.0f}/GPU/月",
                }
            )
        elif mode == "cloud_spot":
            # Spot: 只有 30% 时间可用；名义单价低，但折算到「保证可用」的每 GPUh 更贵
            spot_available_hours = total_gpus * 8760.0 * years * 0.30
            total = price * spot_available_hours
            effective = price / 0.30
            rows.append(
                {
                    "mode": "云 Spot",
                    "per_gpu_hour_cny": round(price, 2),
                    "effective_per_gpu_hour_cny": round(effective, 2),
                    "tco_cny": round(total, 0),
                    "notes": "可用率 ~30%，不保证；按有效可用率折算",
                }
            )
        else:
            total = price * total_gpu_hours
            label = {
                "cloud_ondemand": "云按需",
                "cloud_1y_reserved": "云 1 年预留",
                "cloud_3y_reserved": "云 3 年预留",
            }[mode]
            rows.append(
                {
                    "mode": label,
                    "per_gpu_hour_cny": round(price, 2),
                    "effective_per_gpu_hour_cny": round(price, 2),
                    "tco_cny": round(total, 0),
                    "notes": "",
                }
            )

    # 盈亏平衡利用率 U*
    # 把自建作为固定 CapEx + OpEx，利用率变化 → 自建每 GPUh 变化
    # 简化: 直接用 calc_tco 对不同利用率重算
    Ustar_by_mode: dict[str, float] = {}
    for mode, price in prices.items():
        if mode in ("on_prem", "hybrid", "rental") or price is None:
            continue
        if mode == "cloud_spot":
            continue
        best_U = None
        for U in [u / 100.0 for u in range(5, 101, 1)]:
            p = params.base.model_copy(update={"utilization_pct": U * 100})
            r = calc_tco(p)
            if r.value and r.value["per_gpu_hour_cny"] <= price:
                best_U = U
                break
        if best_U is None:
            Ustar_by_mode[mode] = float("nan")
        else:
            Ustar_by_mode[mode] = round(best_U * 100, 1)

    assumptions.append(
        f"云价格参考 {CLOUD_AS_OF}: {prices['cloud_ondemand']:.0f}/{prices['cloud_1y_reserved']:.0f}/{prices['cloud_3y_reserved']:.0f} CNY/GPUh"
    )
    assumptions.append("Spot 按 30% 可用率估算; 盈亏平衡 U* 用 5% 步长搜索")

    return CalcResult(
        value={
            "summary": {
                "self_per_gpu_hour_cny": round(self_per_gpu_hour, 2),
                "total_gpus": total_gpus,
                "years": years,
                "utilization_pct": params.base.utilization_pct,
            },
            "rows": rows,
            "break_even_util_pct": Ustar_by_mode,
        },
        assumptions=assumptions,
        warnings=warnings,
        provenance=provenance + self_build.provenance,
    )
