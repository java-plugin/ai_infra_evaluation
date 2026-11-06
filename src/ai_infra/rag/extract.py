"""从书籍 PDF 抽取结构化语料。

只产出派生数据（章节正文 + 表格 JSON），原始 PDF 不进入仓库：
``ai-infra rag extract --pdf <path>`` 生成 ``data/knowledge/corpus/``，
之后 ``rag build`` 只依赖这些 JSON/JSONL。
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .schema import TableData
from .text import clean_line, normalize

BOOK_TITLE = "《AI Infra 全栈实战》"

_CHAPTER_RE = re.compile(r"^第\s*(\d{1,3})\s*章[ 　]*(.{0,60})$")
_SECTION_RE = re.compile(r"^(\d{1,2}(?:\.\d{1,2}){1,2})\s+([^\s。，,].{1,40})$")
_FIGURE_RE = re.compile(r"^图\s*(\d{1,2})[-–—.](\d{1,2})\s*(.{0,50})$")


@dataclass
class _State:
    chapter: str = "前言"
    chapter_no: int = 0
    section: str = ""
    section_no: str = ""
    buffer: list[str] = field(default_factory=list)
    last_line: str = ""
    page_from: int = 1
    pending_chapter_title: bool = False
    sections: list[dict[str, Any]] = field(default_factory=list)
    tables: list[TableData] = field(default_factory=list)
    figures: list[dict[str, Any]] = field(default_factory=list)

    def flush(self, page_to: int) -> None:
        text = normalize("".join(self.buffer))
        if text:
            self.sections.append(
                {
                    "chapter_no": self.chapter_no,
                    "chapter": self.chapter,
                    "section_no": self.section_no,
                    "section": self.section or self.chapter,
                    "text": text,
                    "page_from": self.page_from,
                    "page_to": page_to,
                }
            )
        self.buffer = []
        self.page_from = max(page_to, self.page_from)


def _page_items(page: Any, page_no: int) -> Iterator[tuple[str, Any]]:
    """把一页拆成有序的 heading / text / table / figure 元素。"""

    lines = page.extract_text_lines() or []
    tables: list[Any] = []
    try:
        tables = page.find_tables() or []
    except Exception:  # noqa: BLE001 - 版式异常不应中断整本书
        tables = []

    boxes = [t.bbox for t in tables]
    items: list[tuple[float, str, Any]] = []
    for line in lines:
        top = float(line.get("top", 0))
        if any(b[1] - 2 <= top <= b[3] + 2 for b in boxes):
            continue
        items.append((top, "line", str(line.get("text", ""))))
    for table in tables:
        items.append((float(table.bbox[1]), "table", table))
    items.sort(key=lambda x: (x[0], 0 if x[1] == "table" else 1))
    for _, kind, payload in items:
        yield kind, payload


def _clean_table(raw: list[list[str | None]], table_id: str, chapter: str, section: str,
                 title: str, page: int) -> TableData | None:
    grid: list[list[str]] = []
    for row in raw:
        cells = [normalize(str(c or "")).replace("|", "/") for c in row]
        if any(cells):
            grid.append(cells)
    if len(grid) < 2:
        return None

    width = max(len(r) for r in grid)
    grid = [r + [""] * (width - len(r)) for r in grid]
    keep = [i for i in range(width) if any(r[i] for r in grid)]
    if len(keep) < 2:
        return None
    grid = [[r[i] for i in keep] for r in grid]

    headers = grid[0]
    if not any(headers):
        return None
    headers = [h or f"列{i + 1}" for i, h in enumerate(headers)]
    rows: list[dict[str, str]] = []
    for r in grid[1:]:
        if r == headers:  # 跨页重复表头
            continue
        if not any(r):
            continue
        rows.append(dict(zip(headers, r, strict=False)))
    if not rows:
        return None
    return TableData(
        table_id=table_id,
        chapter=chapter,
        section=section,
        title=title,
        headers=headers,
        rows=rows,
        page=page,
        source=f"{BOOK_TITLE}{chapter} {section}".strip(),
    )


def _table_title(caption: str, section_title: str) -> str:
    """表题优先用表格前的引导句，但剔除「如下：」「当前…」这类句子，回退到小节标题。"""

    candidate = normalize(caption).lstrip("。，、；:：").rstrip("：:。；")
    weak = ("以下", "如下", "当前", "常见", "主要", "典型", "具体", "数据", "例如")
    if 2 <= len(candidate) <= 26 and not candidate.startswith(weak):
        return candidate
    return section_title


def _read_toc_titles(pdf: Any, max_pages: int = 8) -> dict[int, str]:
    """从目录页读出完整章标题。

    正文里的章标题行会被排版截断（如「…与 C」），目录页是完整版；同章号取最长的一条。
    """

    titles: dict[int, str] = {}
    for page in pdf.pages[:max_pages]:
        for line in (page.extract_text() or "").splitlines():
            cleaned = clean_line(line)
            match = _CHAPTER_RE.match(cleaned)
            if not match:
                continue
            number = int(match.group(1))
            title = match.group(2).strip()
            if title and len(title) > len(titles.get(number, "")):
                titles[number] = title
    return titles


def extract_pdf(pdf_path: Path, out_dir: Path) -> dict[str, Any]:
    """抽取整本书，写出 ``chapters.jsonl`` / ``tables.json`` / ``figures.json``。"""

    import pdfplumber

    state = _State()
    out_dir.mkdir(parents=True, exist_ok=True)
    table_seq = 0

    with pdfplumber.open(pdf_path) as pdf:
        toc_titles = _read_toc_titles(pdf)
        for page_no, page in enumerate(pdf.pages, start=1):
            for kind, payload in _page_items(page, page_no):
                if kind == "table":
                    raw = payload.extract()
                    section_title = state.section or state.chapter
                    table_seq += 1
                    table = _clean_table(
                        raw,
                        table_id=f"t{state.chapter_no:02d}-{table_seq:03d}",
                        chapter=state.chapter,
                        section=state.section,
                        title=_table_title(state.last_line, section_title),
                        page=page_no,
                    )
                    if table:
                        state.tables.append(table)
                    continue

                line = clean_line(payload)
                if not line:
                    continue

                chapter = _CHAPTER_RE.match(line)
                if chapter:
                    state.flush(page_no)
                    state.chapter_no = int(chapter.group(1))
                    title = toc_titles.get(state.chapter_no, "") or chapter.group(2).strip()
                    state.chapter = f"第{state.chapter_no}章 {title}".strip()
                    state.pending_chapter_title = not title
                    state.section = ""
                    state.section_no = ""
                    state.page_from = page_no
                    state.last_line = line
                    continue

                if state.pending_chapter_title:
                    # 章节号与标题被排版拆成两行时，把下一行补成章标题
                    if len(line) <= 40 and "。" not in line:
                        state.chapter = f"第{state.chapter_no}章 {line}"
                        state.last_line = line
                        state.pending_chapter_title = False
                        continue
                    state.pending_chapter_title = False

                section = _SECTION_RE.match(line)
                if section:
                    state.flush(page_no)
                    state.section_no = section.group(1)
                    state.section = f"{state.section_no} {section.group(2).strip()}"
                    state.page_from = page_no
                    state.last_line = line
                    continue

                figure = _FIGURE_RE.match(line)
                if figure:
                    state.figures.append(
                        {
                            "chapter": state.chapter,
                            "section": state.section,
                            "caption": normalize(line),
                            "page": page_no,
                        }
                    )

                if not state.buffer:
                    state.page_from = page_no
                state.buffer.append(line)
                state.last_line = line

        state.flush(len(pdf.pages))

    with (out_dir / "chapters.jsonl").open("w", encoding="utf-8") as f:
        for item in state.sections:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")
    (out_dir / "tables.json").write_text(
        json.dumps([t.model_dump() for t in state.tables], ensure_ascii=False, indent=1),
        encoding="utf-8",
    )
    (out_dir / "figures.json").write_text(
        json.dumps(state.figures, ensure_ascii=False, indent=1), encoding="utf-8"
    )

    return {
        "sections": len(state.sections),
        "tables": len(state.tables),
        "figures": len(state.figures),
        "text_chars": sum(len(s["text"]) for s in state.sections),
    }


def load_tables(corpus_dir: Path) -> list[TableData]:
    path = corpus_dir / "tables.json"
    if not path.is_file():
        return []
    raw = json.loads(path.read_text(encoding="utf-8"))
    return [TableData.model_validate(item) for item in raw]


def load_sections(corpus_dir: Path) -> list[dict[str, Any]]:
    path = corpus_dir / "chapters.jsonl"
    if not path.is_file():
        return []
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
