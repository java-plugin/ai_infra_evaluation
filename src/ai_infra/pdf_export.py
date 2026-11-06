"""PDF 导出：把报告与 Agent 问答排版成 A4 技术方案。

设计原则：
- PDF 只负责排版，不产生任何数字；内容全部来自确定性计算器或已生成的 Markdown。
- 中文字体优先使用系统字体（Windows / macOS / Linux 常见路径），
  找不到时回退到 reportlab 内置的 STSong-Light CID 字体，保证跨平台可用。
"""

from __future__ import annotations

import html
import json
import re
import sys
from collections.abc import Sequence
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from typing import Any

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas as pdf_canvas
from reportlab.platypus import (
    BaseDocTemplate,
    Flowable,
    Frame,
    HRFlowable,
    NextPageTemplate,
    PageBreak,
    PageTemplate,
    Paragraph,
    Preformatted,
    Spacer,
    Table,
    TableStyle,
)

from .agent.trace import TraceStep

# ---------------------------------------------------------------------------
# 版式常量
# ---------------------------------------------------------------------------

PAGE_W, PAGE_H = A4
MARGIN_L = 20 * mm
MARGIN_R = 20 * mm
MARGIN_T = 24 * mm
MARGIN_B = 22 * mm
CONTENT_W = PAGE_W - MARGIN_L - MARGIN_R

INK = colors.HexColor("#0F172A")
MUTED = colors.HexColor("#5B6B82")
ACCENT = colors.HexColor("#1D4ED8")
ACCENT_SOFT = colors.HexColor("#E8EFFC")
LINE = colors.HexColor("#CBD5E1")
SOFT = colors.HexColor("#F5F8FD")
INFO_BG = colors.HexColor("#EFF6FF")
INFO_BAR = colors.HexColor("#2563EB")
WARN_BG = colors.HexColor("#FEF2F2")
WARN_BAR = colors.HexColor("#DC2626")

DOC_NAME = "AI Infra Advisor"
DOC_FOOTER = (
    "本文档由 AI Infra Advisor 生成：数字来自可测试的确定性计算模块，附带假设 / 警告 / provenance。"
)

# ---------------------------------------------------------------------------
# 字体
# ---------------------------------------------------------------------------

_REGULAR_FONTS: tuple[tuple[str, int], ...] = (
    ("C:/Windows/Fonts/msyh.ttc", 0),
    ("C:/Windows/Fonts/Deng.ttf", 0),
    ("C:/Windows/Fonts/simhei.ttf", 0),
    ("/System/Library/Fonts/PingFang.ttc", 0),
    ("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc", 0),
    ("/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc", 0),
    ("/usr/share/fonts/noto-cjk/NotoSansCJK-Regular.ttc", 0),
)

_BOLD_FONTS: tuple[tuple[str, int], ...] = (
    ("C:/Windows/Fonts/msyhbd.ttc", 0),
    ("/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc", 0),
    ("/usr/share/fonts/truetype/noto/NotoSansCJK-Bold.ttc", 0),
)


def _register_ttf(name: str, path: str, index: int) -> bool:
    file = Path(path)
    if not file.is_file():
        return False
    try:
        pdfmetrics.registerFont(TTFont(name, str(file), subfontIndex=index))
    except Exception:  # noqa: BLE001 - 字体文件可能损坏或格式不支持
        return False
    return True


@lru_cache(maxsize=1)
def fonts() -> tuple[str, str]:
    """返回 (正文字体, 粗体字体) 名称。"""

    regular = ""
    for path, index in _REGULAR_FONTS:
        if _register_ttf("CJK-Regular", path, index):
            regular = "CJK-Regular"
            break

    bold = ""
    if regular:
        for path, index in _BOLD_FONTS:
            if _register_ttf("CJK-Bold", path, index):
                bold = "CJK-Bold"
                break

    if not regular:
        pdfmetrics.registerFont(UnicodeCIDFont("STSong-Light"))
        regular = bold = "STSong-Light"
    elif not bold:
        bold = regular

    pdfmetrics.registerFontFamily(
        regular, normal=regular, bold=bold, italic=regular, boldItalic=bold
    )
    return regular, bold


def _styles() -> dict[str, ParagraphStyle]:
    reg, bold = fonts()
    base = ParagraphStyle(
        "body",
        fontName=reg,
        fontSize=10.5,
        leading=18,
        textColor=INK,
        wordWrap="CJK",
        spaceAfter=6,
    )
    return {
        "body": base,
        "kicker": ParagraphStyle(
            "kicker", fontName=bold, fontSize=9, leading=12, textColor=ACCENT, spaceAfter=2
        ),
        "cover_title": ParagraphStyle(
            "cover_title",
            fontName=bold,
            fontSize=25,
            leading=34,
            textColor=INK,
            wordWrap="CJK",
            spaceAfter=6,
        ),
        "cover_sub": ParagraphStyle(
            "cover_sub",
            fontName=reg,
            fontSize=12,
            leading=20,
            textColor=MUTED,
            wordWrap="CJK",
            spaceAfter=4,
        ),
        "meta_key": ParagraphStyle(
            "meta_key", fontName=reg, fontSize=9.5, leading=15, textColor=MUTED
        ),
        "meta_val": ParagraphStyle(
            "meta_val",
            fontName=bold,
            fontSize=9.5,
            leading=15,
            textColor=INK,
            wordWrap="CJK",
        ),
        "note": ParagraphStyle(
            "note",
            fontName=reg,
            fontSize=8.8,
            leading=14,
            textColor=MUTED,
            wordWrap="CJK",
        ),
        "h1": ParagraphStyle(
            "h1",
            fontName=bold,
            fontSize=14.5,
            leading=22,
            textColor=INK,
            wordWrap="CJK",
            spaceBefore=6,
            spaceAfter=2,
        ),
        "h2": ParagraphStyle(
            "h2",
            fontName=bold,
            fontSize=11.5,
            leading=19,
            textColor=ACCENT,
            wordWrap="CJK",
            spaceBefore=6,
            spaceAfter=2,
        ),
        "h3": ParagraphStyle(
            "h3",
            fontName=bold,
            fontSize=10.5,
            leading=17,
            textColor=INK,
            wordWrap="CJK",
            spaceBefore=4,
            spaceAfter=1,
        ),
        "bullet": ParagraphStyle(
            "bullet",
            parent=base,
            leftIndent=14,
            bulletIndent=0,
            spaceAfter=2,
        ),
        "cell": ParagraphStyle(
            "cell", fontName=reg, fontSize=8.6, leading=12.5, textColor=INK, wordWrap="CJK"
        ),
        "cell_head": ParagraphStyle(
            "cell_head",
            fontName=bold,
            fontSize=8.6,
            leading=12.5,
            textColor=INK,
            wordWrap="CJK",
        ),
        "callout": ParagraphStyle(
            "callout",
            fontName=reg,
            fontSize=9.2,
            leading=15,
            textColor=INK,
            wordWrap="CJK",
        ),
        "code": ParagraphStyle(
            "code",
            fontName=reg,
            fontSize=7.6,
            leading=10.5,
            textColor=colors.HexColor("#334155"),
        ),
        "code_note": ParagraphStyle(
            "code_note",
            fontName=reg,
            fontSize=8,
            leading=12,
            textColor=MUTED,
            wordWrap="CJK",
        ),
    }


# ---------------------------------------------------------------------------
# 页面装饰
# ---------------------------------------------------------------------------


def _draw_cover_bg(canvas: Any, doc: Any) -> None:
    canvas.saveState()
    canvas.setFillColor(ACCENT)
    canvas.rect(0, PAGE_H - 10 * mm, PAGE_W, 10 * mm, stroke=0, fill=1)
    canvas.setFillColor(INK)
    canvas.rect(0, 0, PAGE_W, 6 * mm, stroke=0, fill=1)
    canvas.setStrokeColor(ACCENT_SOFT)
    canvas.setLineWidth(0.6)
    canvas.line(MARGIN_L, 14 * mm, PAGE_W - MARGIN_R, 14 * mm)
    canvas.setFont(fonts()[1], 8)
    canvas.setFillColor(MUTED)
    canvas.drawString(MARGIN_L, 9.5 * mm, f"{DOC_NAME}  ·  CONFIDENTIAL / 内部技术方案")
    canvas.restoreState()


def _draw_page_header(canvas: Any, doc: Any) -> None:
    if getattr(doc, "page", 1) <= 1:
        return
    reg, _ = fonts()
    canvas.saveState()
    canvas.setFont(reg, 8)
    canvas.setFillColor(MUTED)
    canvas.drawString(MARGIN_L, PAGE_H - 14 * mm, f"{DOC_NAME} · 技术方案")
    canvas.drawRightString(PAGE_W - MARGIN_R, PAGE_H - 14 * mm, doc.title if doc.title else "")
    canvas.setStrokeColor(LINE)
    canvas.setLineWidth(0.4)
    canvas.line(MARGIN_L, PAGE_H - 16 * mm, PAGE_W - MARGIN_R, PAGE_H - 16 * mm)
    canvas.restoreState()


class _NumberedCanvas(pdf_canvas.Canvas):  # type: ignore[misc]
    """两遍绘制，支持「第 N 页 / 共 M 页」。"""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._saved_states: list[dict[str, Any]] = []

    def showPage(self) -> None:  # noqa: N802 - 覆写 reportlab Canvas 接口
        self._saved_states.append(dict(self.__dict__))
        self._startPage()

    def save(self) -> None:
        total = len(self._saved_states)
        reg, _ = fonts()
        for state in self._saved_states:
            self.__dict__.update(state)
            page_no = self._pageNumber
            if page_no > 1:
                self.setFont(reg, 7.6)
                self.setFillColor(MUTED)
                self.drawString(MARGIN_L, 11 * mm, DOC_FOOTER)
                self.drawRightString(PAGE_W - MARGIN_R, 11 * mm, f"第 {page_no} 页 / 共 {total} 页")
            super().showPage()
        super().save()


def _doc(path: Path, title: str) -> BaseDocTemplate:
    doc = BaseDocTemplate(
        str(path),
        pagesize=A4,
        leftMargin=MARGIN_L,
        rightMargin=MARGIN_R,
        topMargin=MARGIN_T,
        bottomMargin=MARGIN_B,
        title=title,
        author=DOC_NAME,
        subject="AI Infrastructure Technical Proposal",
        creator=DOC_NAME,
    )
    frame_box = Frame(
        MARGIN_L,
        MARGIN_B,
        CONTENT_W,
        PAGE_H - MARGIN_T - MARGIN_B,
        id="body",
        leftPadding=0,
        rightPadding=0,
        topPadding=0,
        bottomPadding=0,
    )
    doc.addPageTemplates(
        [
            PageTemplate(id="cover", frames=[frame_box], onPage=_draw_cover_bg),
            PageTemplate(id="body", frames=[frame_box], onPage=_draw_page_header),
        ]
    )
    return doc


# ---------------------------------------------------------------------------
# 基础构件
# ---------------------------------------------------------------------------


def _inline(text: str) -> str:
    """把一行 Markdown 行内语法转成 reportlab 段落标记。"""

    s = html.escape(text, quote=False)

    def _code(match: re.Match[str]) -> str:
        token = match.group(1)
        face = "Courier" if token.isascii() else fonts()[0]
        return f'<font face="{face}" size="8.6">{token}</font>'

    s = re.sub(r"`([^`]+)`", _code, s)
    s = re.sub(r"\*\*([^*]+)\*\*", r"<b>\1</b>", s)
    return s


def _visual_len(text: str) -> int:
    """粗估显示宽度：中文按 2 个字符计。"""

    width = 0
    for ch in text:
        width += 2 if "\u4e00" <= ch <= "\u9fff" or ch in "，。：；、（）【】“”" else 1
    return width


def _clip(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _section_title(numbered: str) -> list[Flowable]:
    st = _styles()
    return [
        Spacer(1, 3 * mm),
        Paragraph(_inline(numbered), st["h1"]),
        HRFlowable(width="100%", thickness=0.8, color=LINE, spaceBefore=1, spaceAfter=4),
    ]


def _callout(text: str, kind: str) -> Table:
    st = _styles()
    bg, bar = (INFO_BG, INFO_BAR) if kind == "info" else (WARN_BG, WARN_BAR)
    table = Table([[Paragraph(_inline(text), st["callout"])]], colWidths=[CONTENT_W])
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), bg),
                ("LINEBEFORE", (0, 0), (0, -1), 3, bar),
                ("BOX", (0, 0), (-1, -1), 0.4, LINE),
                ("LEFTPADDING", (0, 0), (-1, -1), 9),
                ("RIGHTPADDING", (0, 0), (-1, -1), 9),
                ("TOPPADDING", (0, 0), (-1, -1), 8),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
            ]
        )
    )
    return table


def _table(headers: Sequence[str], rows: Sequence[Sequence[str]]) -> Table:
    st = _styles()
    data: list[list[Any]] = [[Paragraph(_inline(h), st["cell_head"]) for h in headers]]
    for row in rows:
        cells = list(row) + [""] * (len(headers) - len(row))
        data.append([Paragraph(_inline(c), st["cell"]) for c in cells[: len(headers)]])

    weights: list[float] = []
    for idx in range(len(headers)):
        longest = max(
            [_visual_len(headers[idx])] + [_visual_len(row[idx]) for row in rows if idx < len(row)]
        )
        weights.append(max(70.0, min(float(longest), 620.0)))
    total = sum(weights)
    col_widths = [CONTENT_W * w / total for w in weights]

    table = Table(data, colWidths=col_widths, repeatRows=1, hAlign="LEFT")
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), ACCENT_SOFT),
                ("GRID", (0, 0), (-1, -1), 0.4, LINE),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, SOFT]),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    return table


def _code_block(text: str) -> Table:
    st = _styles()
    clipped = "\n".join(_clip(line, 104) for line in text.splitlines())
    table = Table([[Preformatted(clipped, st["code"])]], colWidths=[CONTENT_W])
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#F8FAFC")),
                ("BOX", (0, 0), (-1, -1), 0.4, LINE),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    return table


# ---------------------------------------------------------------------------
# Markdown → Flowable
# ---------------------------------------------------------------------------

_TABLE_SEP = re.compile(r"^\s*\|?\s*:?-{3,}")


def _split_row(line: str) -> list[str]:
    row = line.strip()
    if row.startswith("|"):
        row = row[1:]
    if row.endswith("|"):
        row = row[:-1]
    return [cell.strip() for cell in row.split("|")]


def _starts_block(line: str) -> bool:
    s = line.strip()
    return bool(
        s.startswith("|")
        or s.startswith("```")
        or s.startswith(">")
        or re.match(r"^#{1,4}\s+", s)
        or re.match(r"^[-*]\s+", s)
        or re.fullmatch(r"(---|___|\*\*\*)", s)
    )


def md_to_flowables(
    md: str, *, skip_first_title: bool = True, heading_offset: int = 0
) -> list[Flowable]:
    """把受限 Markdown（标题 / 列表 / 表格 / 引用 / 代码块）转成排版元素。

    ``heading_offset`` 用于把嵌入的 Markdown（如 Agent 回答）整体降一级，
    避免其二级标题和文档本身的章节标题抢同一层级。
    """

    st = _styles()
    lines = md.splitlines()
    flow: list[Flowable] = []
    skipped_title = False
    i = 0

    while i < len(lines):
        raw = lines[i]
        s = raw.strip()
        if not s:
            i += 1
            continue

        if s.startswith("```"):
            i += 1
            buffer: list[str] = []
            while i < len(lines) and not lines[i].strip().startswith("```"):
                buffer.append(lines[i])
                i += 1
            i += 1
            flow.append(_code_block("\n".join(buffer)))
            flow.append(Spacer(1, 3 * mm))
            continue

        if s.startswith("|") and i + 1 < len(lines) and _TABLE_SEP.match(lines[i + 1].strip()):
            headers = _split_row(s)
            i += 2
            rows: list[list[str]] = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                rows.append(_split_row(lines[i]))
                i += 1
            flow.append(_table(headers, rows))
            flow.append(Spacer(1, 4 * mm))
            continue

        heading = re.match(r"^(#{1,4})\s+(.*)$", s)
        if heading:
            level = len(heading.group(1))
            text = heading.group(2).strip()
            if level == 1 and not skipped_title and skip_first_title:
                skipped_title = True
                i += 1
                continue
            effective = min(level + heading_offset, 4)
            if effective <= 2:
                flow.extend(_section_title(text))
            elif effective == 3:
                flow.append(Paragraph(_inline(text), st["h2"]))
            else:
                flow.append(Paragraph(_inline(text), st["h3"]))
            i += 1
            continue

        if re.match(r"^[-*]\s+", s):
            while i < len(lines) and re.match(r"^[-*]\s+", lines[i].strip()):
                text = re.sub(r"^[-*]\s+", "", lines[i].strip())
                flow.append(Paragraph(_inline(text), st["bullet"], bulletText="·"))
                i += 1
            flow.append(Spacer(1, 2 * mm))
            continue

        if s.startswith(">"):
            buffer = []
            while i < len(lines) and lines[i].strip().startswith(">"):
                buffer.append(lines[i].strip().lstrip(">").strip())
                i += 1
            flow.append(_callout(" ".join(buffer), "info"))
            flow.append(Spacer(1, 3 * mm))
            continue

        if re.fullmatch(r"(---|___|\*\*\*)", s):
            flow.append(
                HRFlowable(width="100%", thickness=0.5, color=LINE, spaceBefore=2, spaceAfter=2)
            )
            i += 1
            continue

        buffer = []
        while i < len(lines) and lines[i].strip() and not _starts_block(lines[i]):
            buffer.append(lines[i].strip())
            i += 1
        flow.append(Paragraph(_inline(" ".join(buffer)), st["body"]))

    return flow


# ---------------------------------------------------------------------------
# 封面
# ---------------------------------------------------------------------------


def _cover(
    *,
    title: str,
    subtitle: str,
    meta_items: Sequence[tuple[str, str]],
    abstract: str,
) -> list[Flowable]:
    st = _styles()
    title_html = _inline(title)
    if _visual_len(title) > 40 and "：" in title:
        head, _, tail = title.partition("：")
        title_html = f"{_inline(head)}：<br/>{_inline(tail)}"
    story: list[Flowable] = [
        Spacer(1, 24 * mm),
        Paragraph("TECHNICAL PROPOSAL  ·  技术方案", st["kicker"]),
        Spacer(1, 2 * mm),
        Paragraph(title_html, st["cover_title"]),
        Spacer(1, 3 * mm),
        Paragraph(_inline(subtitle), st["cover_sub"]),
        Spacer(1, 7 * mm),
        HRFlowable(width="100%", thickness=2, color=ACCENT, spaceBefore=0, spaceAfter=10),
        Spacer(1, 2 * mm),
    ]

    meta_rows = [
        [Paragraph(_inline(k), st["meta_key"]), Paragraph(_inline(v), st["meta_val"])]
        for k, v in meta_items
    ]
    meta_table = Table(meta_rows, colWidths=[34 * mm, CONTENT_W - 34 * mm], hAlign="LEFT")
    meta_table.setStyle(
        TableStyle(
            [
                ("LINEBELOW", (0, 0), (-1, -1), 0.4, LINE),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ]
        )
    )
    story.append(meta_table)
    story.append(Spacer(1, 10 * mm))
    if abstract:
        story.append(_callout(abstract, "info"))
        story.append(Spacer(1, 6 * mm))
    story.append(Spacer(1, 8 * mm))
    story.append(
        Paragraph(
            "本文档用于 AI 基础设施的投入决策。所有容量、性能与成本数字均由确定性计算引擎产生，"
            "并附带计算假设、风险提示与数据来源（provenance）；在相同输入下可完全复算。",
            st["note"],
        )
    )
    story.extend([NextPageTemplate("body"), PageBreak()])
    return story


# ---------------------------------------------------------------------------
# 对外入口
# ---------------------------------------------------------------------------


def export_markdown_pdf(
    markdown: str,
    out_path: Path,
    *,
    subtitle: str,
    meta_items: Sequence[tuple[str, str]],
    abstract: str = "",
) -> Path:
    """把选型报告 Markdown 渲染为 PDF。"""

    title = "AI Infra 选型与成本技术方案"
    first = markdown.strip().splitlines()[0] if markdown.strip() else ""
    if first.startswith("# "):
        title = first[2:].strip()

    story = _cover(
        title=title,
        subtitle=subtitle,
        meta_items=meta_items,
        abstract=abstract,
    )
    story.extend(md_to_flowables(markdown))

    out_path.parent.mkdir(parents=True, exist_ok=True)
    doc = _doc(out_path, title)
    doc.build(story, canvasmaker=_NumberedCanvas)
    return out_path


def _args_brief(args: dict[str, Any], limit: int = 44) -> str:
    if not args:
        return "—"
    parts = [f"{k}={v}" for k, v in args.items() if v not in (None, "", [])]
    return _clip("，".join(parts), limit)


def _collect_assumptions(trace: Sequence[TraceStep]) -> list[str]:
    seen: list[str] = []
    for step in trace:
        if step.type != "tool" or not isinstance(step.output, dict):
            continue
        result = step.output.get("result")
        if not isinstance(result, dict):
            continue
        for item in result.get("assumptions") or []:
            text = str(item)
            if text not in seen:
                seen.append(text)
    return seen


def _collect_provenance(trace: Sequence[TraceStep]) -> list[tuple[str, str, str]]:
    seen: list[tuple[str, str, str]] = []
    for step in trace:
        if step.type != "tool" or not isinstance(step.output, dict):
            continue
        result = step.output.get("result")
        if not isinstance(result, dict):
            continue
        for item in result.get("provenance") or []:
            if not isinstance(item, dict):
                continue
            row = (
                str(item.get("source", "")),
                str(item.get("as_of", "")),
                str(item.get("confidence", "")),
            )
            if row not in seen:
                seen.append(row)
    return seen


def export_agent_pdf(
    *,
    question: str,
    answer: str,
    trace: Sequence[TraceStep],
    out_path: Path,
    model: str = "",
    elapsed_ms: int = 0,
    trace_id: str | None = None,
) -> Path:
    """把一次 Agent 问答导出为技术方案：问题 / 结论 / 计算过程 / 假设 / 附录。"""

    st = _styles()
    tool_steps = [s for s in trace if s.type == "tool"]

    meta_items = [
        ("生成时间", datetime.now().strftime("%Y-%m-%d %H:%M")),
        ("推理模型", model or "offline（规则兜底）"),
        ("端到端耗时", f"{elapsed_ms} ms"),
        ("工具调用", f"{len(tool_steps)} 次 / 轨迹 {len(trace)} 步"),
        ("计算口径", "统一口径 v1（假设 / 警告 / provenance 全量记录）"),
    ]
    if trace_id:
        meta_items.append(("追踪 ID", trace_id))

    story = _cover(
        title="AI Infra 技术方案（Agent 问答）",
        subtitle="LLM 负责理解与编排，全部数字由确定性工具计算，可逐步回放",
        meta_items=meta_items,
        abstract="本方案由 AI Infra Advisor 的问答智能体生成：模型只负责意图识别、参数补全与解释，"
        "TCO、MFU、显存、KV Cache 等数字均来自可测试的计算工具，避免任何心算或估算。",
    )

    story.extend(_section_title("一、问题背景"))
    story.append(Paragraph(_inline(question), st["body"]))
    story.append(Spacer(1, 3 * mm))

    story.extend(_section_title("二、结论与建议"))
    story.extend(md_to_flowables(answer, skip_first_title=False, heading_offset=1))

    story.extend(_section_title("三、计算过程与工具调用"))
    if trace:
        story.append(
            Paragraph(
                "下表按执行顺序记录本次问答的决策与工具调用；参数与输出可在附录 A 中回放核对。",
                st["body"],
            )
        )
        rows: list[list[str]] = []
        for idx, step in enumerate(trace, 1):
            kind = {"tool": "工具", "llm": "模型", "error": "异常"}.get(step.type, step.type)
            detail = step.error if step.type == "error" and step.error else _args_brief(step.args)
            rows.append([str(idx), kind, step.name, detail, f"{step.duration_ms} ms"])
        story.append(_table(["序号", "类型", "工具 / 模型", "关键参数", "耗时"], rows))
        story.append(Spacer(1, 4 * mm))
    else:
        story.append(
            _callout(
                "本次回答未触发工具调用（可能是纯概念解释），因此没有可回放的计算过程。", "info"
            )
        )
        story.append(Spacer(1, 3 * mm))

    assumptions = _collect_assumptions(trace)
    provenance = _collect_provenance(trace)

    story.extend(_section_title("四、关键假设与复算说明"))
    bullets = assumptions or ["本次问答未产生新的计算假设。"]
    for item in bullets:
        story.append(Paragraph(_inline(item), st["bullet"], bulletText="·"))
    story.append(Spacer(1, 2 * mm))
    story.append(
        Paragraph(
            "复算方法：使用相同参数调用后端同名工具（calc_tco / calc_compare / calc_mfu / "
            "calc_memory / calc_kv_cache / recommend_config），即可得到与本文档完全一致的数值；"
            "价格类数据以数据目录中的 as_of 为准，落地前需重新询价。",
            st["body"],
        )
    )
    story.append(Spacer(1, 3 * mm))

    if provenance:
        story.append(Paragraph("数据来源", st["h3"]))
        story.append(
            _table(
                ["来源", "数据截止", "置信度"],
                [[src, as_of, conf] for src, as_of, conf in provenance],
            )
        )
        story.append(Spacer(1, 4 * mm))

    story.extend(_section_title("五、风险与边界"))
    risk_bullets = [
        "价格随供需波动，GPU 与云报价需以签约时为准。",
        "自建优势依赖利用率；低于 40% 时通常不如按需云。",
        "口径上必须区分「节点数」与「GPU 数」，托管费含电时不要重复计电费。",
        "运维需要 SRE、备件与故障演练；团队规模小于 3 人时优先云托管。",
        "医疗、金融、国央企场景需确认数据驻留与等保 / 合规要求。",
    ]
    for item in risk_bullets:
        story.append(Paragraph(_inline(item), st["bullet"], bulletText="·"))
    story.append(Spacer(1, 3 * mm))
    if tool_steps:
        story.extend(_section_title("附录 A：工具输出明细"))
        for idx, step in enumerate(tool_steps, 1):
            story.append(Paragraph(f"A.{idx}  {_inline(step.name)}", st["h3"]))
            payload = json.dumps(step.output, ensure_ascii=False, indent=2, default=str)
            story.append(_code_block(_clip(payload, 1600)))
            story.append(Spacer(1, 4 * mm))
    else:
        story.extend(_section_title("附录 A：工具输出明细"))
        story.append(Paragraph("无工具调用记录。", st["body"]))

    out_path.parent.mkdir(parents=True, exist_ok=True)
    doc = _doc(out_path, "AI Infra 技术方案（Agent 问答）")
    doc.build(story, canvasmaker=_NumberedCanvas)
    return out_path


def platform_font_info() -> str:
    """用于自检/日志：当前平台与选中的字体。"""

    reg, bold = fonts()
    return f"{sys.platform} → {reg} / {bold}"
