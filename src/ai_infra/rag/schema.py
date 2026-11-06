"""知识库数据结构。

表格是本项目的重点：一张表会被拆成「整表摘要 / 单行 / 行组」三种块，
但每一块都保留表标题与表头字段名，检索命中后可按 ``table_id`` 回取整表。
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

DocType = Literal["text", "table_summary", "table_row", "table_group", "figure"]


class TableData(BaseModel):
    """一张完整的表：headers + rows，是向量库里唯一的结构化表格副本。"""

    table_id: str
    chapter: str
    section: str
    title: str
    headers: list[str] = Field(default_factory=list)
    rows: list[dict[str, str]] = Field(default_factory=list)
    page: int = 0
    source: str = ""

    @property
    def row_labels(self) -> list[str]:
        if not self.rows or not self.headers:
            return []
        first = self.headers[0]
        return [r.get(first, "") for r in self.rows]


class Chunk(BaseModel):
    """向量库中的最小检索单元。"""

    chunk_id: str
    doc_type: DocType
    chapter: str
    section: str
    title: str
    text: str
    embed_text: str
    table_id: str | None = None
    row_index: int | None = None
    page: int = 0
    source: str = ""
    meta: dict[str, Any] = Field(default_factory=dict)


class SearchHit(BaseModel):
    """一次检索命中的完整结果，含可回取的整表 JSON。"""

    chunk_id: str
    doc_type: DocType
    chapter: str
    section: str
    title: str
    text: str
    score: float
    vector_score: float = 0.0
    keyword_score: float = 0.0
    source: str = ""
    page: int = 0
    row: dict[str, str] | None = None
    table: TableData | None = None


class IndexStats(BaseModel):
    doc_type_counts: dict[str, int] = Field(default_factory=dict)
    chapters: list[str] = Field(default_factory=list)
    tables: int = 0
    chunks: int = 0
    embedding: str = ""
    dim: int = 0
