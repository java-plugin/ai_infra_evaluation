"""Agent 的知识检索入口。

优先查书籍向量索引（正文 + 表格三粒度块）；索引尚未构建时，回退到
``data/knowledge/cards.yaml`` 的精编卡片，保证离线也有内容可答。
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from ..config import get_settings
from ..rag.search import search_knowledge as _vector_search


@dataclass(frozen=True)
class Card:
    id: str
    title: str
    tags: list[str]
    body: str
    source: str


def _cards_path() -> Path:
    return get_settings().data_dir / "knowledge" / "cards.yaml"


@lru_cache(maxsize=1)
def load_cards() -> list[Card]:
    path = _cards_path()
    if not path.is_file():
        return []
    with path.open("r", encoding="utf-8") as f:
        raw = yaml.safe_load(f) or []
    return [Card(**item) for item in raw]


def _tokens(text: str) -> set[str]:
    text = text.lower()
    ascii_tokens = re.findall(r"[a-z0-9_+.-]+", text)
    tokens = set(ascii_tokens)
    for run in re.findall(r"[\u4e00-\u9fff]+", text):
        for i in range(len(run) - 1):
            tokens.add(run[i : i + 2])
    return tokens


def search_cards(query: str, top_k: int = 5) -> list[dict[str, Any]]:
    """卡片关键词检索，输出结构与向量检索的 SearchHit 保持一致。"""

    q_tokens = _tokens(query)
    scored: list[tuple[float, Card]] = []
    for card in load_cards():
        title_tokens = _tokens(card.title)
        tag_tokens = _tokens(" ".join(card.tags))
        body_tokens = _tokens(card.body)
        score = (
            len(q_tokens & title_tokens) * 6
            + len(q_tokens & tag_tokens) * 4
            + len(q_tokens & body_tokens) * 1
        )
        if score > 0:
            scored.append((float(score), card))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [
        {
            "chunk_id": f"card-{c.id}",
            "doc_type": "text",
            "chapter": "知识卡片",
            "section": "",
            "title": c.title,
            "text": c.body.strip(),
            "score": score,
            "vector_score": 0.0,
            "keyword_score": score,
            "page": None,
            "source": c.source,
            "row": None,
            "table": None,
        }
        for score, c in scored[:top_k]
    ]


def search_knowledge(
    query: str,
    top_k: int = 5,
    *,
    mode: str = "hybrid",
    doc_type: str | None = None,
    chapter: str | None = None,
) -> list[dict[str, Any]]:
    """优先向量检索，索引缺失或无命中时回退卡片。"""

    hits = _vector_search(
        query, top_k, mode=mode, doc_type=doc_type, chapter=chapter
    )
    if hits:
        return hits
    return search_cards(query, top_k)
