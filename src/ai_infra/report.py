"""选型报告生成器（Markdown + PDF）。

Markdown 用于审阅与二次编辑；PDF 复用同一份 Markdown 排版，保证两种格式内容一致。
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from pydantic import BaseModel

from .calculators.compare import calc_compare
from .calculators.kv_cache import calc_kv_cache
from .calculators.memory import calc_memory
from .calculators.mfu import calc_mfu
from .calculators.tco import calc_tco
from .config import get_settings
from .models import CompareInput, KVCacheInput, MemoryInput, MFUInput, TCOInput
from .pdf_export import export_markdown_pdf


class ReportRequest(BaseModel):
    tco: TCOInput
    model_id: str | None = None
    tokens_per_sec: float | None = None


def _fmt_cny(v: float) -> str:
    if v >= 1e8:
        return f"¥{v / 1e8:.2f} 亿"
    if v >= 1e4:
        return f"¥{v / 1e4:,.1f} 万"
    return f"¥{v:,.0f}"


def generate_report(req: ReportRequest) -> tuple[str, Path]:
    tco = calc_tco(req.tco, tokens_per_sec=req.tokens_per_sec)
    compare = calc_compare(CompareInput(base=req.tco))

    if not tco.value:
        raise ValueError("TCO 计算失败: " + "; ".join(tco.warnings))

    s = tco.value["summary"]
    rows = compare.value.get("rows", [])
    structure = tco.value.get("cost_structure_pct", {})

    lines: list[str] = []
    lines.append(f"# AI Infra 选型与成本报告：{s['gpu_count']} × {s['gpu_model']}")
    lines.append("")
    lines.append(f"> 生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M')}  ")
    lines.append("> 本报告由 AI Infra Advisor 生成，所有数字来自确定性计算引擎，可按附录回放。")
    lines.append("")

    lines.append("## 1. 执行摘要")
    lines.append("")
    lines.append(
        f"- 集群规模：**{req.tco.nodes} 节点 × {req.tco.gpus_per_node} GPU = {s['gpu_count']} 张 {s['gpu_model']}**"
    )
    lines.append(f"- 使用年限：**{s['years']} 年**，利用率 **{s['utilization_pct']}%**")
    lines.append(f"- 三年 TCO：**{_fmt_cny(s['tco_total_cny'])}**")
    lines.append(f"- 每 GPU 小时成本：**¥{s['per_gpu_hour_cny']:.2f}**")
    if s.get("per_million_tokens_cny"):
        lines.append(f"- 每百万 token 成本：**¥{s['per_million_tokens_cny']:.2f}**")
    if rows:
        cheapest = min(
            rows,
            key=lambda r: r.get("effective_per_gpu_hour_cny", r["per_gpu_hour_cny"]),
        )
        lines.append(
            f"- 最低有效成本模式：**{cheapest['mode']}（¥{cheapest.get('effective_per_gpu_hour_cny', cheapest['per_gpu_hour_cny']):.2f}/GPUh）**"
        )
    lines.append("")

    lines.append("## 2. 现状与目标")
    lines.append("")
    lines.append(
        "本报告面向「自建 vs 云」的算力投入决策。目标是在给定模型规模、业务负载和预算约束下，"
        "选择总拥有成本最低、且满足性能与合规要求的部署方式。"
    )
    lines.append("")

    lines.append("## 3. 关键假设")
    lines.append("")
    for a in tco.assumptions:
        lines.append(f"- {a}")
    lines.append("")

    lines.append("## 4. 方案对比")
    lines.append("")
    if rows:
        lines.append("| 模式 | 名义每 GPU 小时 | 有效每 GPU 小时 | 总成本 | 说明 |")
        lines.append("|---|---:|---:|---:|---|")
        for r in rows:
            lines.append(
                f"| {r['mode']} | ¥{r['per_gpu_hour_cny']:.2f} | "
                f"¥{r.get('effective_per_gpu_hour_cny', r['per_gpu_hour_cny']):.2f} | "
                f"{_fmt_cny(r['tco_cny'])} | {r.get('notes', '') or '—'} |"
            )
        lines.append("")
        be = compare.value.get("break_even_util_pct", {})
        if be:
            lines.append("**盈亏平衡利用率**（自建成本 ≤ 云成本时）：")
            lines.append("")
            for mode, u in be.items():
                if isinstance(u, float) and u == u:  # 排除 NaN
                    lines.append(f"- {mode}: **{u:.0f}%**")
            lines.append("")
    else:
        lines.append("_无可对比的云方案数据。_")
        lines.append("")

    lines.append("## 5. 成本分析")
    lines.append("")
    lines.append("| 成本项 | 占比 |")
    lines.append("|---|---:|")
    for name, pct in structure.items():
        if pct > 0:
            lines.append(f"| {name} | {pct:.1f}% |")
    lines.append("")
    if tco.warnings:
        lines.append("**计算警告：**")
        lines.append("")
        for w in tco.warnings:
            lines.append(f"- {w}")
        lines.append("")

    lines.append("## 6. 性能与容量")
    lines.append("")
    if req.model_id:
        mem = calc_memory(
            MemoryInput(
                model_id=req.model_id,
                gpu_id=req.tco.gpu_id,
                mode="inference",
                tp=req.tco.gpus_per_node,
                seq_len=4096,
                batch=1,
            )
        )
        kv = calc_kv_cache(
            KVCacheInput(model_id=req.model_id, seq_len=4096, batch=1),
            n_gpus=req.tco.gpus_per_node,
        )
        mfu = calc_mfu(
            MFUInput(
                model_id=req.model_id,
                gpu_id=req.tco.gpu_id,
                n_gpus=req.tco.total_gpus,
                tp=req.tco.gpus_per_node,
                pp=1,
                dp=req.tco.nodes,
                mode="inference",
                seq_len=4096,
                batch_per_gpu=1,
            )
        )
        if mem.value:
            lines.append(
                f"- 单卡显存估算：**{mem.value['summary']['total_gb']:.1f} GB / {mem.value['summary']['hbm_gb']} GB**"
            )
        if kv.value:
            lines.append(
                f"- 单请求 KV Cache（4K）：**{kv.value['summary']['kv_per_request_mb']:.1f} MB**"
            )
        if mfu.value:
            lines.append(
                f"- 估算 MFU：**{mfu.value['summary']['mfu_pct']:.1f}%**（未实测，仅供容量规划参考）"
            )
    else:
        lines.append("_本报告未指定模型，性能与容量部分从略。_")
    lines.append("")

    lines.append("## 7. 风险与避坑")
    lines.append("")
    lines.append("- **价格波动**：GPU 与云价格随供需变化，落地前需重新询价。")
    lines.append("- **利用率风险**：自建优势依赖利用率；低于 40% 时通常不如按需云。")
    lines.append("- **口径风险**：务必区分节点数与 GPU 数；托管费含电时不要重复计电费。")
    lines.append("- **运维风险**：需要 SRE、备件、监控与故障演练；团队小于 3 人时优先云托管。")
    lines.append("- **合规风险**：医疗、金融、国央企场景需确认数据驻留与等保要求。")
    lines.append("")

    lines.append("## 8. 实施路线")
    lines.append("")
    lines.append("| 阶段 | 动作 | 验收 |")
    lines.append("|---|---|---|")
    lines.append("| Phase 0 | 明确模型、QPS、SLO、合规约束 | 需求签字 |")
    lines.append("| Phase 1 | 小规模试点（8–16 卡） | 压测达标、成本可接受 |")
    lines.append("| Phase 2 | 生产集群交付 | 利用率 ≥ 50%，故障演练通过 |")
    lines.append("| Phase 3 | 成本优化（混部/量化/Spot） | 每百万 token 成本下降 20% |")
    lines.append("| Phase 4 | 扩容或云 bursting | 峰谷弹性验证 |")
    lines.append("")

    lines.append("## 附录：数据来源")
    lines.append("")
    for p in tco.provenance + compare.provenance:
        lines.append(f"- `{p.source}`（as_of {p.as_of}，置信度 {p.confidence}）")
    lines.append("")
    lines.append("> 复算说明：本报告使用统一口径重新计算，不直接引用原书表格数字。")
    lines.append("")

    md = "\n".join(lines)
    report_dir = get_settings().report_dir
    report_dir.mkdir(parents=True, exist_ok=True)
    path = report_dir / f"report-{datetime.now().strftime('%Y%m%d-%H%M%S')}.md"
    path.write_text(md, encoding="utf-8")
    return md, path


def generate_report_pdf(markdown: str, md_path: Path, req: ReportRequest) -> Path:
    """把已生成的报告 Markdown 排版为 PDF，并返回 PDF 路径。"""

    tco = req.tco
    meta_items = [
        ("报告编号", md_path.stem),
        (
            "集群规模",
            f"{tco.nodes} 节点 × {tco.gpus_per_node} GPU = {tco.total_gpus} 张 {tco.gpu_id}",
        ),
        ("使用年限 / 利用率", f"{tco.years} 年 / {tco.utilization_pct:g}%"),
        ("目标模型", req.model_id or "未指定"),
        ("生成时间", datetime.now().strftime("%Y-%m-%d %H:%M")),
        ("数据口径", "统一口径 v1，价格 as_of 见附录"),
    ]
    return export_markdown_pdf(
        markdown,
        md_path.with_suffix(".pdf"),
        subtitle="自建 vs 云：成本结构、性能容量与实施路线",
        meta_items=meta_items,
        abstract="本报告面向「自建还是上云」的算力投入决策，用统一口径复算 TCO、每 GPU 小时成本、"
        "成本结构与部署模式差异，并给出盈亏平衡利用率与实施路线。",
    )
