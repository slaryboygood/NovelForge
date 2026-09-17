"""Semantic Memory（V4-03 §8）。

先定义统一 Retrieval Contract，底层可以是 metadata filter / keyword / structured index /
embedding / hybrid；**调用方不知道底层实现**。

V4-03 的默认底层是"结构化 metadata + 关键词"，embedding 为可选加成（默认关闭）。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping, Sequence

from novelforge.core.ids import digest_payload

from ..contracts import MemoryItem, MemorySource, memory_id_for
from ..embedding import EmbeddingProvider, NullEmbeddingProvider, cosine
from ..errors import MemoryError
from ..scoring import tokenize


@dataclass(frozen=True)
class SemanticEntry:
    entry_id: str
    novel_id: str
    text: str
    entities: tuple[str, ...] = ()
    keywords: tuple[str, ...] = ()
    source: MemorySource | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)
    embedding: tuple[float, ...] = ()

    def __post_init__(self) -> None:
        if not str(self.entry_id or "").strip():
            raise MemoryError("SemanticEntry 需要 entry_id")
        if not str(self.novel_id or "").strip():
            raise MemoryError("SemanticEntry 需要 novel_id（跨作品隔离）")

    def to_item(self) -> MemoryItem:
        """semantic 条目对外表现为 semantic memory，origin 保留在 metadata（§29）。"""

        origin = self.source.as_dict() if self.source is not None else {}
        source = MemorySource(source_type="semantic", source_id=self.entry_id,
                              revision=(self.source.revision
                                        if self.source is not None else None),
                              label=str(self.metadata.get("label") or self.entry_id),
                              metadata={"origin": origin})
        return MemoryItem(memory_id=memory_id_for("semantic", self.entry_id),
                          memory_type="semantic", text=self.text, source=source,
                          metadata={"entities": list(self.entities),
                                    "keywords": list(self.keywords),
                                    "origin_source": origin,
                                    **dict(self.metadata)})


class SemanticIndex:
    """按 novel_id 分区的语义检索索引（结构化 + 可选 embedding）。"""

    def __init__(self, *, embedder: EmbeddingProvider | None = None) -> None:
        self.embedder: EmbeddingProvider = embedder or NullEmbeddingProvider()
        self._entries: dict[str, dict[str, SemanticEntry]] = {}

    # ------------------------------------------------------------------ 写入
    def add(self, entry: SemanticEntry) -> SemanticEntry:
        if not entry.embedding and self.embedder.dimensions:
            embedding = self.embedder.embed([entry.text])[0]
            entry = SemanticEntry(**{**entry.__dict__, "embedding": embedding})
        self._entries.setdefault(entry.novel_id, {})[entry.entry_id] = entry
        return entry

    def extend(self, entries: Iterable[SemanticEntry]) -> int:
        return sum(1 for entry in entries if self.add(entry))

    def from_items(self, novel_id: str, items: Iterable[MemoryItem]) -> int:
        rows = []
        for item in items:
            rows.append(SemanticEntry(
                entry_id=item.memory_id, novel_id=novel_id, text=item.text,
                entities=tuple(str(value) for value in
                               (item.metadata.get("entities") or ())),
                keywords=tokenize(item.text), source=item.source,
                metadata={key: value for key, value in item.metadata.items()
                          if key not in ("entities", "keywords")}))
        return self.extend(rows)

    # ------------------------------------------------------------------ 读取
    def entries(self, novel_id: str) -> list[SemanticEntry]:
        return sorted(self._entries.get(novel_id, {}).values(),
                      key=lambda item: item.entry_id)

    def count(self, novel_id: str = "") -> int:
        if novel_id:
            return len(self._entries.get(novel_id, {}))
        return sum(len(rows) for rows in self._entries.values())

    def digest(self, novel_id: str) -> str:
        return digest_payload([entry.entry_id for entry in self.entries(novel_id)])

    def search(self, novel_id: str, *, task: str = "",
               entities: Sequence[str] = (), top_k: int = 8,
               allow_embeddings: bool = False) -> list[tuple[SemanticEntry, float, str]]:
        """确定性检索：结构化命中 + 关键词重叠（+ 可选 embedding）。"""

        wanted_tokens = set(tokenize(task))
        wanted_entities = {str(value) for value in entities if str(value)}
        rows: list[tuple[SemanticEntry, float, str]] = []
        for entry in self.entries(novel_id):
            reasons: list[str] = []
            score = 0.0
            matched_entities = wanted_entities & set(entry.entities)
            if matched_entities:
                score += min(0.4 * len(matched_entities), 0.6)
                reasons.append("entity_match:" + ",".join(sorted(matched_entities)))
            if wanted_tokens:
                indexes = set(entry.keywords)
                overlap = wanted_tokens & indexes
                if not overlap:
                    overlap = {token for token in wanted_tokens
                               if any(token in candidate or candidate in token
                                      for candidate in indexes if len(candidate) >= 2)}
                if overlap:
                    score += min(0.1 * len(overlap), 0.4)
                    reasons.append(f"keyword_overlap={len(overlap)}")
            if allow_embeddings and self.embedder.dimensions and entry.embedding:
                query_vector = self.embedder.embed([task])[0] if task else ()
                similarity = cosine(query_vector, entry.embedding)
                if similarity:
                    score += 0.2 * max(0.0, similarity)
                    reasons.append(f"embedding_similarity={similarity}")
            if score <= 0:
                continue
            rows.append((entry, round(min(1.0, score), 6),
                         ";".join(reasons) or "structured_match"))
        rows.sort(key=lambda row: (-row[1], row[0].entry_id))
        return rows[: max(1, int(top_k))]


__all__ = ["SemanticEntry", "SemanticIndex"]
