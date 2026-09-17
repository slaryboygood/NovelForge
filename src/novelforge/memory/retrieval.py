"""检索装配辅助（V4-03 §8 的"统一 Retrieval Contract"装配点）。

调用方只需要 `MemoryService`；本模块提供的是**索引装配**的便利函数，
不暴露底层 store / scorer 细节。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable, Sequence

from .contracts import MemoryItem, MemorySource
from .semantic import SemanticEntry, SemanticIndex


def index_items_into_semantic(semantic: SemanticIndex, novel_id: str,
                              items: Iterable[MemoryItem]) -> int:
    """把检索条目投影进语义索引（结构化 metadata + 关键词）。"""

    return semantic.from_items(novel_id, items)


def semantic_entries_from_items(novel_id: str,
                                items: Sequence[MemoryItem]) -> list[SemanticEntry]:
    from .scoring import tokenize

    rows: list[SemanticEntry] = []
    for item in items:
        rows.append(SemanticEntry(
            entry_id=item.memory_id, novel_id=novel_id, text=item.text,
            entities=tuple(str(value) for value in
                           (item.metadata.get("entities") or ())),
            keywords=tokenize(item.text), source=item.source,
            metadata={key: value for key, value in item.metadata.items()
                      if key not in ("entities", "keywords")}))
    return rows


def static_items(novel_id: str, rows: Sequence[dict[str, Any]]) -> list[MemoryItem]:
    """测试 / fixture 用：从简单 dict 构造 MemoryItem（仍走同一契约）。"""

    items: list[MemoryItem] = []
    for row in rows:
        source = MemorySource(source_type=str(row.get("source_type") or "semantic"),
                              source_id=str(row.get("source_id") or ""),
                              revision=row.get("revision"),
                              label=str(row.get("label") or ""))
        items.append(MemoryItem(memory_id=str(row.get("memory_id")
                                              or f"{source.source_type}:{source.source_id}"),
                                memory_type=str(row.get("memory_type") or
                                                source.memory_type),
                                text=str(row.get("text") or ""), source=source,
                                metadata=dict(row.get("metadata") or {})))
    return items


def project_root_of(service: Any) -> Path | None:
    return getattr(service, "project_root", None)


__all__ = ["index_items_into_semantic", "project_root_of",
           "semantic_entries_from_items", "static_items"]

