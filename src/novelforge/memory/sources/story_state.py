"""StoryState retrieval view（V4-03 §6）。

StoryState Memory ≠ StoryState source of truth：只投影当前状态，不维护第二套状态。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Sequence

from ..contracts import MemoryItem, MemorySource, memory_id_for
from ..errors import MemorySourceError


class StoryStateMemorySource:
    """从 StoryState（经 creator context + view 投影）生成只读检索条目。"""

    source_prefix = "story_state"

    def __init__(self, project_root: Path | str, *, revision: int | None = None) -> None:
        self.project_root = Path(project_root)
        self.revision = revision

    def _context(self, novel_id: str):
        from novelforge.story_engine.context import (
            NovelContextError,
            resolve_novel_context,
        )

        try:
            return resolve_novel_context(self.project_root, novel_id)
        except NovelContextError as exc:
            raise MemorySourceError(f"StoryState 解析失败：{exc.message}",
                                    details={"novel_id": novel_id}) from exc

    def revision_of(self, novel_id: str) -> int | None:
        context = self._context(novel_id)
        state = context.state
        if not context.persisted:
            return None
        effects = len(getattr(state, "effect_log", []) or [])
        return effects

    def provide(self, novel_id: str) -> Sequence[MemoryItem]:
        from novelforge.story_engine.world_view import world_snapshot

        context = self._context(novel_id)
        state = context.state
        world = world_snapshot(context)
        revision = self.revision if self.revision is not None else len(
            getattr(state, "effect_log", []) or [])
        revision_key = f"story_state:{novel_id}"
        rows: list[MemoryItem] = []

        def add(source_id: str, text: str, *, metadata: dict[str, Any]) -> None:
            rows.append(MemoryItem(
                memory_id=memory_id_for("story_state", source_id),
                memory_type="story_state", text=text,
                source=MemorySource(source_type="story_state", source_id=source_id,
                                    revision=revision,
                                    label=str(metadata.get("label") or source_id),
                                    metadata={"revision_key": revision_key}),
                metadata={**metadata, "revision_key": revision_key}))

        timeline = world["timeline"]
        add("timeline", f"当前时间：{timeline['current_time'] or '未指定'}"
                        f"（tick {timeline['tick']}）",
            metadata={"label": "时间线", "kind": "timeline",
                      "revision": revision})
        location = world["location"]
        add("location.current",
            f"当前位置：{location['name'] or location['current'] or '未指定'}",
            metadata={"label": "当前位置", "kind": "location",
                      "locations": [location["current"]] if location["current"] else []})

        for character_id, character in sorted(state.characters.items()):
            flags = []
            if character_id in getattr(state, "identities", {}):
                flags.append("身份：" + ",".join(state.identities[character_id]))
            add(f"character.{character_id}",
                f"{character.name or character_id}（{character.kind}）"
                + ("；" + "；".join(flags) if flags else ""),
                metadata={"label": character.name or character_id,
                          "kind": "character", "entities": [character_id]})

        for resource_id, stock in sorted(state.resources.items()):
            add(f"resource.{resource_id}",
                f"资源 {resource_id}：{stock.amount}{stock.unit or ''}",
                metadata={"label": resource_id, "kind": "resource",
                          "entities": [resource_id]})

        for relationship in sorted(state.relationships,
                                   key=lambda item: (item.source_id, item.target_id)):
            dimensions = ", ".join(f"{key}={value}"
                                   for key, value in sorted(relationship.dimensions.items()))
            if not dimensions:
                continue
            add(f"relationship.{relationship.source_id}.{relationship.target_id}",
                f"关系 {relationship.source_id} → {relationship.target_id}：{dimensions}",
                metadata={"label": f"{relationship.source_id}→{relationship.target_id}",
                          "kind": "relationship",
                          "entities": [relationship.source_id, relationship.target_id]})

        from novelforge.story_engine.memory import (
            outstanding_promises,
            unresolved_conflicts,
        )

        for promise in outstanding_promises(state):
            add(f"promise.{promise.id}",
                f"未完成承诺：{promise.description}"
                + (f"（{promise.debtor} → {promise.creditor}）"
                   if promise.debtor or promise.creditor else ""),
                metadata={"label": promise.id, "kind": "promise",
                          "open": True,
                          "entities": [value for value in
                                       (promise.debtor, promise.creditor) if value]})

        for conflict in unresolved_conflicts(state):
            add(f"conflict.{conflict.kind}.{conflict.id}",
                f"未解决冲突：{conflict.title or conflict.id}"
                f"（{conflict.kind}，pressure {conflict.pressure}）",
                metadata={"label": conflict.id, "kind": "conflict", "open": True,
                          "entities": list(conflict.participants)})
        return rows

    def episodes(self, novel_id: str, *, limit: int = 50) -> Sequence[Any]:
        """从 StoryState 确定性推导 episode（episodic memory 的 canonical 来源）。

        注意：来源是 StoryState effects / events，不是正文；`novel/final` 已删除，
        历史 570 章不再存在。
        """

        from ..episodic import derive_episodes

        context = self._context(novel_id)
        revision = self.revision if self.revision is not None else len(
            getattr(context.state, "effect_log", []) or [])
        return derive_episodes(context.state, revision=revision, limit=limit)


__all__ = ["StoryStateMemorySource"]
