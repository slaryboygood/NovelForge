"""MemoryIndex —— 按 novel_id 分区的派生记忆索引（V4-03 §13–§14、§31）。

规则：

```text
1. 每个条目都属于一个 novel_id 分区；跨分区读取在索引层就被拒绝（早于排序）
2. 每个条目记录 source.revision；canonical revision 变化 → 条目 stale（不静默当真）
3. 索引必须可重建：rebuild 后 digest 应稳定
4. 去重：同一 (source_type, source_id) 只保留一条（后写覆盖，并记录 replaced）
```
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping, Sequence

from novelforge.core.ids import digest_payload

from .contracts import MemoryItem
from .errors import MemoryIsolationError


@dataclass
class IndexEntry:
    item: MemoryItem
    indexed_at: str = ""
    stale: bool = False
    stale_reason: str = ""
    provenance_revision: int | None = None

    def as_dict(self) -> dict[str, Any]:
        return {"item": self.item.as_dict(), "indexed_at": self.indexed_at,
                "stale": self.stale, "stale_reason": self.stale_reason,
                "provenance_revision": self.provenance_revision}


@dataclass
class MemoryIndex:
    """进程内索引（可重建；当前不落盘，落盘由 persistence 适配层负责）。"""

    _partitions: dict[str, dict[str, IndexEntry]] = field(
        default_factory=lambda: defaultdict(dict))
    replaced: list[dict[str, str]] = field(default_factory=list)

    # ------------------------------------------------------------------ 写入
    def upsert(self, novel_id: str, items: Iterable[MemoryItem]) -> int:
        if not str(novel_id or "").strip():
            raise MemoryIsolationError("MemoryIndex.upsert 需要显式 novel_id")
        partition = self._partitions.setdefault(novel_id, {})
        written = 0
        for item in items:
            existing = partition.get(item.memory_id)
            if existing is not None:
                self.replaced.append({"novel_id": novel_id,
                                      "memory_id": item.memory_id,
                                      "reason": "duplicate_source_identity"})
            partition[item.memory_id] = IndexEntry(
                item=item, provenance_revision=item.source.revision)
            written += 1
        return written

    def clear(self, novel_id: str = "") -> None:
        if novel_id:
            self._partitions.pop(novel_id, None)
            return
        self._partitions.clear()

    # ------------------------------------------------------------------ 读取
    def items(self, novel_id: str, *, source_types: Sequence[str] = (),
              include_stale: bool = False) -> list[MemoryItem]:
        if not str(novel_id or "").strip():
            raise MemoryIsolationError("MemoryIndex.items 需要显式 novel_id")
        partition = self._partitions.get(novel_id, {})
        allowed = {str(value) for value in source_types}
        rows: list[MemoryItem] = []
        for entry in partition.values():
            if allowed and entry.item.source.source_type not in allowed:
                continue
            if entry.stale and not include_stale:
                continue
            rows.append(self._with_stale_flag(entry) if entry.stale else entry.item)
        return rows

    @staticmethod
    def _with_stale_flag(entry: IndexEntry) -> MemoryItem:
        from dataclasses import replace

        return replace(entry.item, stale=True)

    def entries(self, novel_id: str) -> list[IndexEntry]:
        return list(self._partitions.get(novel_id, {}).values())

    def count(self, novel_id: str = "") -> int:
        if novel_id:
            return len(self._partitions.get(novel_id, {}))
        return sum(len(partition) for partition in self._partitions.values())

    def novel_ids(self) -> tuple[str, ...]:
        return tuple(sorted(self._partitions))

    def digest(self, novel_id: str) -> str:
        rows = sorted(entry.item.memory_id for entry in self.entries(novel_id))
        return digest_payload({"novel_id": novel_id, "items": rows})

    # ------------------------------------------------------------ 失效 (§14)
    def mark_stale(self, novel_id: str, *, memory_id: str = "",
                   source_id: str = "", reason: str = "source_revision_changed") -> int:
        """标记失效：可精确到 memory_id，也可按 source_id 批量。"""

        if not str(novel_id or "").strip():
            raise MemoryIsolationError("MemoryIndex.mark_stale 需要显式 novel_id")
        marked = 0
        for entry in self._partitions.get(novel_id, {}).values():
            if memory_id and entry.item.memory_id != memory_id:
                continue
            if source_id and entry.item.source.source_id != source_id:
                continue
            entry.stale = True
            entry.stale_reason = reason
            marked += 1
        return marked

    def stale_report(self, novel_id: str,
                     current_revisions: Mapping[str, int]) -> list[dict[str, Any]]:
        """对照 canonical 当前 revision，报告失效条目（§13）。"""

        rows: list[dict[str, Any]] = []
        for entry in self._partitions.get(novel_id, {}).values():
            source_id = entry.item.source.source_id
            indexed = entry.item.source.revision
            current = current_revisions.get(self.revision_key(entry))
            if current is None or indexed is None or int(current) == int(indexed):
                if entry.stale:
                    rows.append({"memory_id": entry.item.memory_id,
                                 "source_id": source_id,
                                 "indexed_revision": indexed,
                                 "current_revision": current,
                                 "reason": entry.stale_reason or "marked_stale"})
                continue
            rows.append({"memory_id": entry.item.memory_id, "source_id": source_id,
                         "indexed_revision": indexed, "current_revision": current,
                         "reason": "source_revision_changed"})
        return sorted(rows, key=lambda row: (row["source_id"], row["memory_id"]))

    def apply_revision_check(self, novel_id: str,
                             current_revisions: Mapping[str, int]) -> int:
        """按当前 revision 自动把漂移条目置为 stale（返回新标记数量）。"""

        marked = 0
        for entry in self._partitions.get(novel_id, {}).values():
            current = current_revisions.get(self.revision_key(entry))
            if (current is not None and entry.item.source.revision is not None
                    and int(current) != int(entry.item.source.revision)
                    and not entry.stale):
                entry.stale = True
                entry.stale_reason = "source_revision_changed"
                marked += 1
        return marked

    @staticmethod
    def revision_key(entry: IndexEntry) -> str:
        """条目的 revision 归属键：优先 metadata.revision_key，其次 source_id。"""

        metadata = entry.item.source.metadata or {}
        return str(metadata.get("revision_key")
                   or entry.item.metadata.get("revision_key")
                   or entry.item.source.source_id)


__all__ = ["IndexEntry", "MemoryIndex"]
