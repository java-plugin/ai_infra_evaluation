"""分块策略。

正文：按章节归属 + 句边界切分，块内保留「书名 / 章节」上下文前缀，避免脱离语境。
表格：同一张表生成三种粒度——
  * ``table_summary``：表名 + 表头 + 前几行，负责语义召回；
  * ``table_row``：单行，但**每一行都带着表头字段名**，负责精确值召回；
  * ``table_group``：连续 3 行，负责跨行对比。
三者共享 ``table_id``，命中后回取整表 JSON。
"""

from __future__ import annotations

import zlib
from collections.abc import Iterator
from typing import Any

from .extract import BOOK_TITLE
from .schema import Chunk, TableData
from .text import normalize, split_sentences, truncate

TEXT_SIZE = 360
TEXT_OVERLAP = 70
GROUP_SIZE = 3
SUMMARY_SAMPLE_ROWS = 3
SUMMARY_LABELS = 8


def _split_text(text: str) -> list[str]:
    sentences = split_sentences(text)
    if not sentences:
        return []
    pieces: list[str] = []
    buf: list[str] = []
    length = 0
    for sentence in sentences:
        if buf and length + len(sentence) > TEXT_SIZE:
            pieces.append("".join(buf))
            keep: list[str] = []
            kept = 0
            for prev in reversed(buf):
                if kept + len(prev) > TEXT_OVERLAP:
                    break
                keep.insert(0, prev)
                kept += len(prev)
            buf, length = keep, kept
        buf.append(sentence)
        length += len(sentence)
    if buf:
        pieces.append("".join(buf))
    return [p.strip() for p in pieces if p.strip()]


def section_chunks(section: dict[str, Any], seq_start: int = 0) -> list[Chunk]:
    chapter = str(section["chapter"])
    title = str(section["section"] or chapter)
    chapter_no = int(section["chapter_no"] or 0)
    page = int(section["page_from"] or 0)
    context = f"{BOOK_TITLE}{chapter} {title}".strip()
    text = normalize(str(section["text"]))
    chunks: list[Chunk] = []
    for offset, piece in enumerate(_split_text(text)):
        chunks.append(
            Chunk(
                chunk_id=f"txt-{chapter_no:02d}-{seq_start + offset:04d}",
                doc_type="text",
                chapter=chapter,
                section=title,
                title=title,
                text=piece,
                embed_text=f"{context}｜{piece}",
                page=page,
                source=context,
            )
        )
    return chunks


def _cell(value: str) -> str:
    value = normalize(value)
    return truncate(value, 60)


def _row_text(table: TableData, row: dict[str, str]) -> str:
    pairs = [f"{h}: {_cell(v)}" for h, v in row.items() if _cell(v)]
    return "｜".join(pairs)


def table_chunks(table: TableData) -> list[Chunk]:
    if not table.rows:
        return []
    context = f"{BOOK_TITLE}{table.chapter} {table.section}".strip()
    base = f"{table.title}"
    chunks: list[Chunk] = []

    labels = [x for x in table.row_labels[:SUMMARY_LABELS] if x]
    preview = "；".join(_row_text(table, r) for r in table.rows[:SUMMARY_SAMPLE_ROWS])
    summary = (
        f"{base}｜表头: {'、'.join(table.headers)}"
        f"｜共 {len(table.rows)} 行：{'、'.join(labels)}｜示例: {preview}"
    )
    chunks.append(
        Chunk(
            chunk_id=f"{table.table_id}-s",
            doc_type="table_summary",
            chapter=table.chapter,
            section=table.section,
            title=table.title,
            text=summary,
            embed_text=f"{context}｜{summary}",
            table_id=table.table_id,
            page=table.page,
            source=table.source,
            meta={"rows": len(table.rows), "headers": table.headers},
        )
    )

    for index, row in enumerate(table.rows):
        body = _row_text(table, row)
        if not body:
            continue
        chunks.append(
            Chunk(
                chunk_id=f"{table.table_id}-r{index:02d}",
                doc_type="table_row",
                chapter=table.chapter,
                section=table.section,
                title=table.title,
                text=f"{base}｜{body}",
                embed_text=f"{context}｜{base}｜{body}",
                table_id=table.table_id,
                row_index=index,
                page=table.page,
                source=table.source,
                meta={"headers": table.headers},
            )
        )

    for start in range(0, len(table.rows), GROUP_SIZE):
        group = table.rows[start : start + GROUP_SIZE]
        body = "；".join(_row_text(table, r) for r in group)
        chunks.append(
            Chunk(
                chunk_id=f"{table.table_id}-g{start // GROUP_SIZE:02d}",
                doc_type="table_group",
                chapter=table.chapter,
                section=table.section,
                title=table.title,
                text=f"{base}｜表头: {'、'.join(table.headers)}｜{body}",
                embed_text=f"{context}｜{base}｜{'、'.join(table.headers)}｜{body}",
                table_id=table.table_id,
                page=table.page,
                source=table.source,
                meta={"row_start": start, "headers": table.headers},
            )
        )
    return chunks


def figure_chunks(figure: dict[str, Any]) -> Iterator[Chunk]:
    caption = normalize(str(figure.get("caption", "")))
    if not caption:
        return
    chapter = str(figure.get("chapter", ""))
    section = str(figure.get("section", ""))
    context = f"{BOOK_TITLE}{chapter} {section}".strip()
    yield Chunk(
        chunk_id=f"fig-{zlib.crc32(caption.encode('utf-8')):08d}",
        doc_type="figure",
        chapter=chapter,
        section=section,
        title=caption,
        text=f"{caption}（原书图表，此处为图注文本）",
        embed_text=f"{context}｜{caption}",
        page=int(figure.get("page") or 0),
        source=context,
    )
