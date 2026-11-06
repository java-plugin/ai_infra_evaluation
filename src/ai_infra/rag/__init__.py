"""向量化知识库。

流程：书籍 PDF → 结构化语料（章节正文 + 表格 JSON）→ 分块 → 嵌入 → sqlite-vec。
检索层同时跑向量召回与 BM25，用 RRF 融合，表格块命中后回取整表 JSON。
"""

from .build import build_index
from .search import get_table, knowledge_stats, search_knowledge

__all__ = ["build_index", "get_table", "knowledge_stats", "search_knowledge"]
