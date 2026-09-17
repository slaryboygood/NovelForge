"""Episodic Memory（V4-03 §7）。

来源**必须**是 Story Blueprint revision / Scene·Chapter Card / StoryState effects /
confirmed events —— **不是** `novel/final` 正文、不是 570 章历史、不是长篇 prose。

V4-03 的落地方式：

```text
1. derive_episodes(state)：从 StoryState.effect_log 按 source（行动/事件）分组，
   确定性地推导 episode（可重建、零 LLM、零网络）
2. EpisodicStore.add(...)：接受来自未来 Blueprint revision 的 episode（同契约）
```

每条 episode 都带 source_ids + source_revision + created_at + memory_schema_version。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping, Sequence

from novelforge.core.ids import digest_payload

from ..contracts import (
    MEMORY_SCHEMA_VERSION,
    MemoryItem,
    MemorySource,
    memory_id_for,
    utc_now,
)
from ..errors import MemoryError


@dataclass(frozen=True)
class EpisodeEntry:
    episode_id: str
    novel_id: str
    revision: int | None = None
    source_ids: tuple[str, ...] = ()
    chapter_id: str = ""
    scene_id: str = ""
    what_happened: str = ""
    who_acted: tuple[str, ...] = ()
    who_knows: tuple[str, ...] = ()
    state_changes: tuple[str, ...] = ()
    relationship_changes: tuple[str, ...] = ()
    new_information: tuple[str, ...] = ()
    setup: tuple[str, ...] = ()
    payoff: tuple[str, ...] = ()
    unresolved: tuple[str, ...] = ()
    tick: int = 0
    source_type: str = "story_state"
    created_at: str = ""
    memory_schema_version: int = MEMORY_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if not str(self.episode_id or "").strip():
            raise MemoryError("EpisodeEntry 需要 episode_id")
        if not str(self.novel_id or "").strip():
            raise MemoryError("EpisodeEntry 需要 novel_id")
        if not self.created_at:
            object.__setattr__(self, "created_at", utc_now())

    def as_dict(self) -> dict[str, Any]:
        return {"episode_id": self.episode_id, "novel_id": self.novel_id,
                "revision": self.revision, "source_ids": list(self.source_ids),
                "chapter_id": self.chapter_id, "scene_id": self.scene_id,
                "what_happened": self.what_happened,
                "who_acted": list(self.who_acted), "who_knows": list(self.who_knows),
                "state_changes": list(self.state_changes),
                "relationship_changes": list(self.relationship_changes),
                "new_information": list(self.new_information),
                "setup": list(self.setup), "payoff": list(self.payoff),
                "unresolved": list(self.unresolved), "tick": self.tick,
                "source_type": self.source_type, "created_at": self.created_at,
                "memory_schema_version": self.memory_schema_version}

    def to_item(self) -> MemoryItem:
        parts = [self.what_happened or self.episode_id]
        if self.who_acted:
            parts.append("参与：" + "、".join(self.who_acted))
        if self.state_changes:
            parts.append("状态变化：" + "；".join(self.state_changes))
        if self.new_information:
            parts.append("新信息：" + "；".join(self.new_information))
        if self.unresolved:
            parts.append("未决：" + "；".join(self.unresolved))
        revision_key = self.metadata_revision_key()
        return MemoryItem(
            memory_id=memory_id_for("episode", self.episode_id),
            memory_type="episodic", text="｜".join(parts),
            source=MemorySource(source_type="episode", source_id=self.episode_id,
                                revision=self.revision if self.revision is not None
                                else self.tick,
                                label=self.chapter_id or self.scene_id or "episode",
                                metadata={"source_ids": list(self.source_ids),
                                          "revision_key": revision_key}),
            token_estimate=0,
            metadata={"entities": list(self.who_acted),
                      "tick": self.tick, "chapter_id": self.chapter_id,
                      "scene_id": self.scene_id, "open": bool(self.unresolved)})

    def metadata_revision_key(self) -> str:
        """episode 的 revision 归属键（与 EpisodicStore.current_revisions 对应）。"""

        return f"episodes:{self.novel_id}"


def derive_episodes(state: Any, *, revision: int | None = None,
                    limit: int = 50, created_at: str = "") -> list[EpisodeEntry]:
    """从 StoryState.effect_log 确定性推导 episode（零 LLM，可重建）。

    传入 `created_at` 时整个结果是纯函数（便于"重建后内容完全一致"的断言）。
    """

    novel_id = str(getattr(state, "novel_id", "") or "")
    if not novel_id:
        return []
    grouped: dict[str, list[Any]] = {}
    for record in list(getattr(state, "effect_log", []) or []):
        key = str(getattr(record, "source", "") or "unspecified")
        grouped.setdefault(key, []).append(record)

    resolved_events = {item.id: item for item in
                       (getattr(state, "resolved_events", []) or [])}
    active_events = {item.id: item for item in
                     (getattr(state, "active_events", []) or [])}

    episodes: list[EpisodeEntry] = []
    for source_id, records in grouped.items():
        state_changes: list[str] = []
        relationships: list[str] = []
        information: list[str] = []
        actors: list[str] = []
        for record in records:
            op = str(getattr(record, "op", ""))
            entity = str(getattr(record, "entity", "") or "")
            target = str(getattr(record, "target", "") or "")
            value = getattr(record, "value", None)
            if entity and entity not in actors:
                actors.append(entity)
            if op == "change_relationship":
                relationships.append(f"{entity}→{target}={value}")
            elif op == "add_knowledge":
                information.append(f"{entity} 获得 {target}")
            else:
                state_changes.append(f"{op} {entity}{'→' + target if target else ''}"
                                     + (f"={value}" if value is not None else ""))
        event = resolved_events.get(source_id) or active_events.get(source_id)
        title = ""
        if event is not None:
            title = str(getattr(event, "title", "") or getattr(event, "id", ""))
        ticks = [int((getattr(record, "data", {}) or {}).get("tick", 0) or 0)
                 for record in records]
        knowledge_holders: set[str] = set()
        for row in (getattr(state, "knowledge", []) or []):
            if source_id in str(getattr(row, "source_event", "") or ""):
                knowledge_holders.update(str(value) for value in
                                         (getattr(row, "holders", []) or []))
        episodes.append(EpisodeEntry(
            episode_id=f"ep_{source_id}",
            novel_id=novel_id,
            revision=revision,
            source_ids=tuple([source_id, *(str(getattr(record, "order", ""))
                                          for record in records)]),
            what_happened=title or f"围绕 {source_id} 的一组已发生效果",
            who_acted=tuple(actors),
            who_knows=tuple(sorted(knowledge_holders)),
            state_changes=tuple(state_changes),
            relationship_changes=tuple(relationships),
            new_information=tuple(information),
            tick=max(ticks) if ticks else int(getattr(state.timeline, "tick", 0) or 0),
            source_type="story_state", created_at=created_at))
    episodes.sort(key=lambda item: (item.tick, item.episode_id))
    if limit:
        episodes = episodes[-int(limit):]
    return episodes


@dataclass
class EpisodicStore:
    """派生 episode 存储（可按 novel_id 重建；不写入任何 truth）。"""

    _episodes: dict[str, dict[str, EpisodeEntry]] = field(default_factory=dict)

    def add(self, entry: EpisodeEntry) -> EpisodeEntry:
        self._episodes.setdefault(entry.novel_id, {})[entry.episode_id] = entry
        return entry

    def extend(self, entries: Iterable[EpisodeEntry]) -> int:
        return sum(1 for entry in entries if self.add(entry))

    def for_novel(self, novel_id: str) -> list[EpisodeEntry]:
        rows = list(self._episodes.get(novel_id, {}).values())
        return sorted(rows, key=lambda item: (item.tick, item.episode_id))

    def replace_from_state(self, state: Any, *, revision: int | None = None,
                           limit: int = 50, created_at: str = "") -> list[EpisodeEntry]:
        entries = derive_episodes(state, revision=revision, limit=limit,
                                  created_at=created_at)
        self._episodes[entries[0].novel_id if entries
                       else str(getattr(state, "novel_id", "") or "")] = {
            entry.episode_id: entry for entry in entries}
        return entries

    def current_revisions(self, novel_id: str) -> dict[str, int]:
        """episode 的 source revision：用该 novel 的 episode 条数作为稳定版本标识。"""

        return {f"episodes:{novel_id}": len(self.for_novel(novel_id))}

    def to_items(self, novel_id: str) -> list[MemoryItem]:
        return [entry.to_item() for entry in self.for_novel(novel_id)]

    def digest(self, novel_id: str) -> str:
        return digest_payload([entry.as_dict() for entry in self.for_novel(novel_id)])

    def digest_rows(self, novel_id: str) -> list[dict[str, Any]]:
        """重建等价性断言用：episode 的全部字段（含 created_at）。"""

        return [entry.as_dict() for entry in self.for_novel(novel_id)]

    def count(self, novel_id: str = "") -> int:
        if novel_id:
            return len(self._episodes.get(novel_id, {}))
        return sum(len(rows) for rows in self._episodes.values())


__all__ = ["EpisodeEntry", "EpisodicStore", "derive_episodes"]
