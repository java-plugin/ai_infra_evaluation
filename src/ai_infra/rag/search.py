"""混合检索：向量召回 + BM25，用 RRF 融合。

为什么不是纯向量：表格里的「2,048 张」「50-80 万元」这类精确值，
哈希/通用语义向量都容易漏；BM25 对同词命中非常敏感。
为什么不是纯 BM25：用户问「哪家私有化门槛最低」时，原文写的是「私有化部署最低门槛」，
只有语义向量能把「门槛」对齐到「部署门槛」。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .build import index_path
from .embedding import get_embedder
from .schema import Chunk, SearchHit, TableData
from .store import VectorStore
from .text import normalize_query, tokens

RRF_K = 60
VECTOR_WEIGHT = 1.0
KEYWORD_WEIGHT = 0.9
# 候选池要比 top_k 宽得多：正确行可能只在某一路排到 10 名开外，
# 池子太小会直接把它截掉，融合时只剩单路分数。
CANDIDATES = 8
MIN_CANDIDATES = 40

# 表格是这本书的「事实层」，同一问题往往表格块更精确；给一点固定加成，
# 但用词面覆盖率兜底，避免纯表格把语义类问题挤掉。
TYPE_WEIGHT = {
    "table_row": 1.55,
    "table_summary": 1.2,
    "table_group": 1.25,
    "figure": 1.1,
    "text": 1.0,
}

# 表题/小节标题里常出现「四大厂商」「选型指南」这类概括词，而表内单元格只写具体数值。
# 查询词能对上章标题时，说明问题问的正是这一章的「主题」，给一点加成。
CHAPTER_BOOST = 1.2
CHAPTER_COVERAGE_MIN = 0.4


def search_knowledge(
    query: str,
    top_k: int = 5,
    *,
    mode: str = "hybrid",
    doc_type: str | None = None,
    chapter: str | None = None,
    db_path: Path | None = None,
) -> list[dict[str, Any]]:
    path = db_path or index_path()
    if not path.is_file():
        return []

    store = VectorStore(path)
    try:
        if int(store.get_meta("dim") or 0) == 0:
            return []
        query = normalize_query(query)
        resolved = _resolve_chapter(store, chapter)
        if chapter is not None and resolved is None:
            # 传了章节但一个都对不上：宁可返回空，也不要悄悄忽略过滤条件
            return []
        fused = _fuse(store, query, top_k, mode, doc_type, resolved)
        return [_hit(store, chunk, score, vec, key) for chunk, score, vec, key in fused]
    finally:
        store.close()


def knowledge_stats(db_path: Path | None = None) -> dict[str, Any] | None:
    """索引概览：类型分布、章节列表、嵌入模型。索引导出未构建时返回 None。"""

    path = db_path or index_path()
    if not path.is_file():
        return None
    store = VectorStore(path)
    try:
        stats = store.stats()
        return {**stats.model_dump(), "meta": store.meta()}
    finally:
        store.close()


def get_table(table_id: str, db_path: Path | None = None) -> dict[str, Any] | None:
    path = db_path or index_path()
    if not path.is_file():
        return None
    store = VectorStore(path)
    try:
        table = store.get_table(table_id)
        return table.model_dump() if table else None
    finally:
        store.close()


def _resolve_chapter(store: VectorStore, chapter: str | None) -> str | None:
    """把「第12章」这种前缀解析成完整章节名；vec0 的元数据过滤只支持等值匹配。"""

    if not chapter:
        return None
    chapters = store.stats().chapters
    if chapter in chapters:
        return chapter
    matched = [c for c in chapters if c.startswith(chapter) or chapter in c]
    return matched[0] if matched else None


def _fuse(
    store: VectorStore,
    query: str,
    top_k: int,
    mode: str,
    doc_type: str | None,
    chapter: str | None,
) -> list[tuple[Chunk, float, float, float]]:
    limit = max(top_k * CANDIDATES, MIN_CANDIDATES)
    ranks: dict[str, dict[str, float]] = {}

    if mode in {"hybrid", "vector"}:
        vector = get_embedder().embed([query])[0]
        if len(vector) == int(store.get_meta("dim") or 0):
            for rank, (chunk_id, distance) in enumerate(
                store.search_vector(vector, limit, doc_type=doc_type, chapter=chapter)
            ):
                similarity = max(0.0, 1.0 - distance * distance / 2.0)
                ranks.setdefault(chunk_id, {})["vector"] = similarity
                ranks[chunk_id]["_vrank"] = rank

    if mode in {"hybrid", "keyword"}:
        for rank, (chunk_id, score) in enumerate(
            store.search_keyword(query, limit, doc_type=doc_type, chapter=chapter)
        ):
            ranks.setdefault(chunk_id, {})["keyword"] = score
            ranks[chunk_id]["_krank"] = rank

    fused: list[tuple[Chunk, float, float, float]] = []
    chunks = store.get_chunks(list(ranks))
    query_tokens = set(tokens(query))
    for chunk_id, parts in ranks.items():
        chunk = chunks.get(chunk_id)
        if chunk is None:
            continue
        value = 0.0
        if "vector" in parts:
            value += VECTOR_WEIGHT / (RRF_K + parts.get("_vrank", 0) + 1)
        if "keyword" in parts:
            value += KEYWORD_WEIGHT / (RRF_K + parts.get("_krank", 0) + 1)
        coverage = _coverage(query_tokens, f"{chunk.title} {chunk.text}")
        value *= TYPE_WEIGHT.get(chunk.doc_type, 1.0) * (0.55 + 0.45 * coverage)
        if _coverage(query_tokens, chunk.chapter) >= CHAPTER_COVERAGE_MIN:
            value *= CHAPTER_BOOST
        fused.append((chunk, value, parts.get("vector", 0.0), parts.get("keyword", 0.0)))

    fused.sort(key=lambda item: item[1], reverse=True)
    return fused[:top_k]


def _coverage(query_tokens: set[str], text: str) -> float:
    """查询词在文本里的覆盖率：正确的表格行往往能把厂商、指标、数值全命中。"""

    if not query_tokens:
        return 0.0
    chunk_tokens = set(tokens(text))
    return len(query_tokens & chunk_tokens) / len(query_tokens)


def _hit(
    store: VectorStore, chunk: Chunk, score: float, vector_score: float, keyword_score: float
) -> dict[str, Any]:
    table: TableData | None = None
    if chunk.table_id:
        table = store.get_table(chunk.table_id)
    hit = SearchHit(
        chunk_id=chunk.chunk_id,
        doc_type=chunk.doc_type,
        chapter=chunk.chapter,
        section=chunk.section,
        title=chunk.title,
        text=chunk.text,
        score=round(score * 100, 3),
        vector_score=round(vector_score, 4),
        keyword_score=round(keyword_score, 4),
        source=chunk.source,
        page=chunk.page,
        row=table.rows[chunk.row_index] if table and chunk.row_index is not None else None,
        table=table,
    )
    return hit.model_dump()
