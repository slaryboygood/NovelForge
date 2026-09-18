"""StoryState retrieval view（V4-03 §6）。

StoryState Memory ≠ StoryState source of truth：只投影当前状态，不维护第二套状态。

post-release cleanup：本模块不再经 V2 `world_view` / `story_engine.memory` 取数，
直接读 `NovelContext.state`（StoryState 是它的 canonical owner），
因此 memory → domain 的依赖只剩 context / state / entities。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Sequence

from ..contracts import MemoryItem, MemorySource, memory_id_for
from ..errors import MemorySourceError


class StoryStateMemorySource:
    """从 StoryState 生成只读检索条目（canonical owner 是 StoryState 本身）。"""

    source_prefix = "story_state"

    def __init__(self, project_root: Path | str, *, revision: int | None = None) -> None:
        self.project_root = Path(project_root)
        self.revision = revision

    def _context(self, novel_id: str):
        from novelforge.story_engine.context import NovelContextError, resolve_novel_context

        try:
            return resolve_novel_context(self.project_root, novel_id)
        except NovelContextError as exc:
            raise MemorySourceError(f"StoryState 解析失败：{exc.message}",
                                    details={"novel_id": novel_id}) from exc

    def revision_of(self, novel_id: str) -> int | None:
        context = self._context(novel_id)
        if not context.persisted:
            return None
        return len(getattr(context.state, "effect_log", []) or [])

    def provide(self, novel_id: str) -> Sequence[MemoryItem]:
        context = self._context(novel_id)
        state = context.state
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

        timeline = state.timeline
        add("timeline", f"当前时间：{timeline.current_time or '未指定'}"
                        f"（第 {timeline.tick} 回合）",
            metadata={"label": "时间线", "kind": "timeline",
                      "revision": revision})
        current_location = state.location.current
        entry = state.location.known.get(current_location) if current_location else None
        add("location.current",
            f"当前位置：{(entry.name if entry is not None else '') or current_location or '未指定'}",
            metadata={"label": "当前位置", "kind": "location",
                      "locations": [current_location] if current_location else []})

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

        for promise in _open_promises(state):
            add(f"promise.{promise.id}",
                f"未完成承诺：{promise.description}"
                + (f"（{promise.debtor} → {promise.creditor}）"
                   if promise.debtor or promise.creditor else ""),
                metadata={"label": promise.id, "kind": "promise",
                          "open": True,
                          "entities": [value for value in
                                       (promise.debtor, promise.creditor) if value]})

        for conflict in _unresolved_conflicts(state):
            add(f"conflict.{conflict['kind']}.{conflict['id']}",
                f"未解决冲突：{conflict['title'] or conflict['id']}"
                f"（{conflict['kind']}，pressure {conflict['pressure']}）",
                metadata={"label": conflict["id"], "kind": "conflict", "open": True,
                          "entities": list(conflict["participants"])})
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


def _open_promises(state: Any) -> list[Any]:
    """未完成承诺（open），按到期 / 创建顺序排序（确定性）。"""

    rows = [item for item in state.promises if item.status == "open"]
    return sorted(rows, key=lambda item: (item.due_tick or 10 ** 6,
                                          item.created_tick, item.id))


def _unresolved_conflicts(state: Any) -> list[dict[str, Any]]:
    """未解决冲突：从支线 / 承诺 / 关系推导，**不新存一份**。"""

    rows: list[dict[str, Any]] = []
    for plot in state.plots.values():
        status = str(plot.get("status") or "")
        if status not in ("active", "paused"):
            continue
        data = plot.get("data") or {}
        rows.append({"kind": "plot", "id": str(plot.get("id", "")),
                     "title": str(plot.get("title", "")),
                     "participants": list(data.get("participants", [])),
                     "pressure": float(data.get("pressure", 0))})
    for promise in _open_promises(state):
        rows.append({"kind": "promise", "id": promise.id,
                     "title": promise.description,
                     "participants": [value for value in
                                      (promise.debtor, promise.creditor) if value],
                     "pressure": 1.0 if (promise.due_tick
                                         and promise.due_tick <= state.timeline.tick)
                     else 0.5})
    for relationship in state.relationships:
        hostility = relationship.dimensions.get("hostility", 0)
        if hostility > 0:
            rows.append({"kind": "relationship",
                         "id": f"{relationship.source_id}->{relationship.target_id}",
                         "title": "敌意",
                         "participants": [relationship.source_id,
                                          relationship.target_id],
                         "pressure": float(hostility)})
    return sorted(rows, key=lambda item: (-item["pressure"], item["kind"], item["id"]))


__all__ = ["StoryStateMemorySource"]
