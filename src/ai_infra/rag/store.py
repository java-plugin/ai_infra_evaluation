"""SQLite 向量库：sqlite-vec 负责向量召回，FTS5 负责 BM25 关键词召回。

单文件、无服务、可离线；元数据（章节 / 块类型）直接作为 vec0 的过滤列。
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterable, Sequence
from pathlib import Path
from typing import Any

import sqlite_vec

from .schema import Chunk, IndexStats, TableData
from .text import fts_query, fts_text

METADATA_COLUMNS = ("doc_type", "chapter")


def connect(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(path, check_same_thread=False)
    con.row_factory = sqlite3.Row
    con.enable_load_extension(True)
    sqlite_vec.load(con)
    con.enable_load_extension(False)
    return con


class VectorStore:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.con = connect(path)

    # ------------------------------------------------------------------ 写入

    def create(self, dim: int, embedding_name: str) -> None:
        self.con.executescript(
            f"""
            DROP TABLE IF EXISTS chunks;
            DROP TABLE IF EXISTS tables;
            DROP TABLE IF EXISTS meta;
            DROP TABLE IF EXISTS chunk_fts;
            DROP TABLE IF EXISTS chunk_vec;
            CREATE TABLE chunks(
                chunk_id TEXT PRIMARY KEY, doc_type TEXT, chapter TEXT, section TEXT,
                title TEXT, text TEXT, embed_text TEXT, table_id TEXT, row_index INTEGER,
                page INTEGER, source TEXT
            );
            CREATE TABLE tables(table_id TEXT PRIMARY KEY, payload TEXT);
            CREATE TABLE meta(key TEXT PRIMARY KEY, value TEXT);
            CREATE VIRTUAL TABLE chunk_fts USING fts5(chunk_id UNINDEXED, body);
            CREATE VIRTUAL TABLE chunk_vec USING vec0(
                chunk_id TEXT PRIMARY KEY, doc_type TEXT, chapter TEXT, embedding float[{dim}]
            );
            """
        )
        self.set_meta("dim", str(dim))
        self.set_meta("embedding", embedding_name)

    def set_meta(self, key: str, value: str) -> None:
        self.con.execute(
            "INSERT INTO meta(key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, value),
        )

    def get_meta(self, key: str) -> str | None:
        row = self.con.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
        return str(row["value"]) if row else None

    def add_chunks(self, chunks: Sequence[Chunk], vectors: Sequence[Sequence[float]]) -> None:
        rows = [
            (
                c.chunk_id,
                c.doc_type,
                c.chapter,
                c.section,
                c.title,
                c.text,
                c.embed_text,
                c.table_id,
                c.row_index,
                c.page,
                c.source,
            )
            for c in chunks
        ]
        self.con.executemany(
            "INSERT OR REPLACE INTO chunks VALUES (?,?,?,?,?,?,?,?,?,?,?)", rows
        )
        self.con.executemany(
            "INSERT INTO chunk_fts(chunk_id, body) VALUES (?, ?)",
            [
                # 表格块把章标题带上：像「四大厂商」这种只在章名出现的说法也能命中表格
                (c.chunk_id, fts_text(f"{c.chapter} {c.text}" if c.table_id else c.text))
                for c in chunks
            ],
        )
        self.con.executemany(
            "INSERT OR REPLACE INTO chunk_vec(chunk_id, doc_type, chapter, embedding) VALUES (?,?,?,?)",
            [
                (c.chunk_id, c.doc_type, c.chapter, _pack(v))
                for c, v in zip(chunks, vectors, strict=True)
            ],
        )

    def add_tables(self, tables: Iterable[TableData]) -> None:
        self.con.executemany(
            "INSERT OR REPLACE INTO tables(table_id, payload) VALUES (?, ?)",
            [(t.table_id, t.model_dump_json()) for t in tables],
        )

    def commit(self) -> None:
        self.con.commit()

    def close(self) -> None:
        self.con.close()

    # ------------------------------------------------------------------ 查询

    def search_vector(
        self,
        vector: Sequence[float],
        k: int,
        *,
        doc_type: str | None = None,
        chapter: str | None = None,
    ) -> list[tuple[str, float]]:
        where, params = _filters(doc_type, chapter)
        sql = f"SELECT chunk_id, distance FROM chunk_vec WHERE embedding MATCH ? AND k = ?{where}"
        rows = self.con.execute(sql, (_pack(vector), k, *params)).fetchall()
        return [(str(r["chunk_id"]), float(r["distance"])) for r in rows]

    def search_keyword(
        self,
        query: str,
        k: int,
        *,
        doc_type: str | None = None,
        chapter: str | None = None,
    ) -> list[tuple[str, float]]:
        terms = fts_query(query)
        if not terms:
            return []
        where, params = _filters(doc_type, chapter)
        sql = (
            "SELECT f.chunk_id AS chunk_id, bm25(chunk_fts) AS score "
            f"FROM chunk_fts f JOIN chunks c ON c.chunk_id = f.chunk_id "
            f"WHERE chunk_fts MATCH ?{where} ORDER BY score LIMIT ?"
        )
        rows = self.con.execute(sql, (terms, *params, k)).fetchall()
        return [(str(r["chunk_id"]), -float(r["score"])) for r in rows]

    def get_chunks(self, ids: Sequence[str]) -> dict[str, Chunk]:
        if not ids:
            return {}
        marks = ",".join("?" for _ in ids)
        rows = self.con.execute(
            f"SELECT * FROM chunks WHERE chunk_id IN ({marks})", list(ids)
        ).fetchall()
        out: dict[str, Chunk] = {}
        for r in rows:
            out[str(r["chunk_id"])] = Chunk(
                chunk_id=str(r["chunk_id"]),
                doc_type=r["doc_type"],
                chapter=r["chapter"],
                section=r["section"],
                title=r["title"],
                text=r["text"],
                embed_text=r["embed_text"],
                table_id=r["table_id"],
                row_index=r["row_index"],
                page=int(r["page"] or 0),
                source=r["source"],
            )
        return out

    def get_table(self, table_id: str) -> TableData | None:
        row = self.con.execute(
            "SELECT payload FROM tables WHERE table_id = ?", (table_id,)
        ).fetchone()
        return TableData.model_validate(json.loads(row["payload"])) if row else None

    def stats(self) -> IndexStats:
        counts: dict[str, int] = {}
        for r in self.con.execute("SELECT doc_type, COUNT(*) AS n FROM chunks GROUP BY doc_type"):
            counts[str(r["doc_type"])] = int(r["n"])
        chapters = [
            str(r["chapter"])
            for r in self.con.execute("SELECT DISTINCT chapter FROM chunks ORDER BY chapter")
        ]
        tables = int(self.con.execute("SELECT COUNT(*) AS n FROM tables").fetchone()["n"])
        return IndexStats(
            doc_type_counts=counts,
            chapters=chapters,
            tables=tables,
            chunks=sum(counts.values()),
            embedding=str(self.get_meta("embedding") or ""),
            dim=int(self.get_meta("dim") or 0),
        )

    def meta(self) -> dict[str, Any]:
        return {str(r["key"]): str(r["value"]) for r in self.con.execute("SELECT * FROM meta")}


def _filters(doc_type: str | None, chapter: str | None) -> tuple[str, list[Any]]:
    clauses: list[str] = []
    params: list[Any] = []
    if doc_type:
        clauses.append("doc_type = ?")
        params.append(doc_type)
    if chapter:
        clauses.append("chapter = ?")
        params.append(chapter)
    # FTS 侧用别名 c，向量侧直接列名，两边靠同一份条件再套用前缀
    return "".join(f" AND {c}" for c in clauses), params


def _pack(vector: Sequence[float]) -> bytes:
    packed: bytes = sqlite_vec.serialize_float32(list(vector))
    return packed
