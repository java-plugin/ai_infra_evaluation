"""嵌入模型。

默认是确定性的中文哈希嵌入（无模型下载、可离线、结果可复现）；
配置了 OpenAI-compatible embedding 服务时自动切换为真实语义向量（如 bge-m3）。
"""

from __future__ import annotations

import math
import os
from collections.abc import Sequence
from typing import Protocol

import httpx

from .text import hash_token, tokens

DEFAULT_DIM = 512


class Embedder(Protocol):
    name: str
    dim: int

    def embed(self, texts: Sequence[str]) -> list[list[float]]: ...


class HashingEmbedder:
    """词袋 + 哈希技巧（hashing trick）。

    细粒度 token（汉字 bigram）让「显存」「利用率」「私有化门槛」这类术语能整词命中；
    L2 归一化后等价于余弦相似度。
    """

    def __init__(self, dim: int = DEFAULT_DIM) -> None:
        self.dim = dim
        self.name = f"hashing-{dim}"

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        return [self._one(t) for t in texts]

    def _one(self, text: str) -> list[float]:
        vec = [0.0] * self.dim
        for token in tokens(text):
            bucket, sign = hash_token(token)
            vec[bucket % self.dim] += sign
        norm = math.sqrt(sum(v * v for v in vec)) or 1.0
        return [v / norm for v in vec]


class ApiEmbedder:
    """OpenAI-compatible ``POST /embeddings``。"""

    def __init__(self, base_url: str, api_key: str, model: str, dim: int = 1024) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.name = f"api:{model}"
        self.dim = dim

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        vectors: list[list[float]] = []
        batch = 32
        with httpx.Client(timeout=60.0) as client:
            for start in range(0, len(texts), batch):
                part = list(texts[start : start + batch])
                resp = client.post(
                    f"{self.base_url}/embeddings",
                    headers={"Authorization": f"Bearer {self.api_key}"},
                    json={"model": self.model, "input": part},
                )
                resp.raise_for_status()
                data = sorted(resp.json()["data"], key=lambda d: d["index"])
                vectors.extend([list(map(float, d["embedding"])) for d in data])
        if vectors:
            self.dim = len(vectors[0])
        return vectors


def get_embedder() -> Embedder:
    """按环境变量选择嵌入后端，默认离线哈希。"""

    base_url = os.environ.get("AI_INFRA_EMBED_BASE_URL", "").strip()
    api_key = os.environ.get("AI_INFRA_EMBED_API_KEY", "").strip()
    model = os.environ.get("AI_INFRA_EMBED_MODEL", "bge-m3").strip()
    if base_url and api_key:
        return ApiEmbedder(base_url, api_key, model)
    return HashingEmbedder()
