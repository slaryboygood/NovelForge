"""Embedding Provider Contract（V4-03 §23–§24）。

V4-03 **不**引入向量数据库，也**不**让 memory 直接发 HTTP：

```text
EmbeddingProvider（协议）
├── NullEmbeddingProvider   默认：不产生向量（纯结构化 / 关键词检索）
└── LocalHashEmbedding      离线确定性伪向量：只用于验证 hybrid 打分管道与 tie-break
```

真正走模型/服务商的 embedding 必须经 `novelforge.ai`（HostedEmbeddingProvider 属于
V4-04/V4-05，待 Gateway 增加 embedding contract 后接入），memory 不得 import provider 实现。
"""

from __future__ import annotations

import hashlib
import math
from typing import Protocol, Sequence, runtime_checkable


@runtime_checkable
class EmbeddingProvider(Protocol):
    provider_id: str
    dimensions: int

    def embed(self, texts: Sequence[str]) -> list[tuple[float, ...]]: ...


class NullEmbeddingProvider:
    """默认实现：返回空向量（调用方据此退化到结构化 / 关键词检索）。"""

    provider_id = "null"
    dimensions = 0

    def embed(self, texts: Sequence[str]) -> list[tuple[float, ...]]:
        return [() for _ in texts]


class LocalHashEmbedding:
    """确定性本地伪向量（sha256 展开）。

    **不是语义 embedding**：只保证"同文本同向量、不同文本大概率不同"，
    用于在没有模型的情况下验证 hybrid 检索管道、deterministic tie-break 与缓存键。
    """

    provider_id = "local_hash"

    def __init__(self, dimensions: int = 32) -> None:
        if dimensions < 4:
            raise ValueError("dimensions 必须 >= 4")
        self.dimensions = int(dimensions)

    def _vector(self, text: str) -> tuple[float, ...]:
        digest = hashlib.sha256(str(text or "").encode("utf-8")).digest()
        raw = [(byte - 127.5) / 127.5 for byte in digest]
        while len(raw) < self.dimensions:
            digest = hashlib.sha256(digest).digest()
            raw.extend((byte - 127.5) / 127.5 for byte in digest)
        vector = raw[: self.dimensions]
        norm = math.sqrt(sum(value * value for value in vector)) or 1.0
        return tuple(round(value / norm, 6) for value in vector)

    def embed(self, texts: Sequence[str]) -> list[tuple[float, ...]]:
        return [self._vector(text) for text in texts]


def cosine(left: Sequence[float], right: Sequence[float]) -> float:
    if not left or not right or len(left) != len(right):
        return 0.0
    dot = sum(a * b for a, b in zip(left, right))
    left_norm = math.sqrt(sum(a * a for a in left)) or 1.0
    right_norm = math.sqrt(sum(b * b for b in right)) or 1.0
    return round(dot / (left_norm * right_norm), 6)


__all__ = ["EmbeddingProvider", "LocalHashEmbedding", "NullEmbeddingProvider",
           "cosine"]

