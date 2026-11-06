"""构建知识库索引。

入口只依赖已抽取好的语料（``corpus/`` 下的 JSON / JSONL），
因此仓库里放派生语料即可复现，不需要原书 PDF。
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from ..config import get_settings
from .chunker import figure_chunks, section_chunks, table_chunks
from .embedding import Embedder, get_embedder
from .extract import load_sections, load_tables
from .schema import Chunk, IndexStats
from .store import VectorStore

BATCH = 128


def knowledge_dir() -> Path:
    return get_settings().data_dir / "knowledge"


def corpus_dir() -> Path:
    return knowledge_dir() / "corpus"


def index_path() -> Path:
    return knowledge_dir() / "index.db"


def collect_chunks() -> tuple[list[Chunk], list[Any]]:
    sections = load_sections(corpus_dir())
    tables = load_tables(corpus_dir())

    chunks: list[Chunk] = []
    for section in sections:
        chapter_no = int(section.get("chapter_no") or 0)
        existing = sum(1 for c in chunks if c.chunk_id.startswith(f"txt-{chapter_no:02d}-"))
        chunks.extend(section_chunks(section, seq_start=existing))

    for table in tables:
        chunks.extend(table_chunks(table))

    figure_path = corpus_dir() / "figures.json"
    if figure_path.is_file():
        for figure in json.loads(figure_path.read_text(encoding="utf-8")):
            chunks.extend(figure_chunks(figure))

    return chunks, tables


def build_index(
    *,
    db_path: Path | None = None,
    embedder: Embedder | None = None,
) -> IndexStats:
    db_path = db_path or index_path()
    chunks, tables = collect_chunks()
    if not chunks:
        raise FileNotFoundError(f"语料为空，请先执行 rag extract：{corpus_dir()}")

    embedder = embedder or get_embedder()
    vectors = []
    for start in range(0, len(chunks), BATCH):
        vectors.extend(embedder.embed([c.embed_text for c in chunks[start : start + BATCH]]))
    dim = len(vectors[0])

    tmp = db_path.with_suffix(".db.tmp")
    if tmp.exists():
        tmp.unlink()
    store = VectorStore(tmp)
    try:
        store.create(dim, embedder.name)
        store.add_tables(tables)
        store.add_chunks(chunks, vectors)
        store.set_meta("built_at", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        store.set_meta("corpus_dir", str(corpus_dir()))
        store.commit()
        stats = store.stats()
    finally:
        store.close()

    tmp.replace(db_path)
    return stats
