"""世界运行层（V2-A）：时间、地点、势力、NPC 自主行动。

全部题材无关：世界如何推进由内容包给出的 AutonomousRule 数据决定，
引擎只按“条件满足 → 执行行动 → 记录来源”的通用流程运行。
"""

from __future__ import annotations

from typing import Any

from pydantic import Field

from novelforge.models import StrictModel

from .actions import Action
from .content import ContentPack
from .effects import apply_effects
from .entities import EffectRecord, KnowledgeEntry
from .events import EventCardCatalog, EventTriggerEngine
from .state import StoryState


class AutonomousRule(StrictModel):
    """一个 NPC / 势力的自主行动规则：满足条件时执行某个行动。"""

    actor_id: str = Field(min_length=1, max_length=128)
    action_id: str = Field(min_length=1, max_length=128)
    label: str = Field(default="", max_length=120)
    priority: int = Field(default=0, ge=-100, le=100)
    once: bool = False
    data: dict[str, Any] = Field(default_factory=dict)


class WorldTickResult(StrictModel):
    ok: bool = True
    state: StoryState
    acted: list[str] = Field(default_factory=list)
    skipped: list[dict[str, Any]] = Field(default_factory=list)
    records: list[EffectRecord] = Field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {"ok": self.ok, "acted": list(self.acted), "skipped": list(self.skipped),
                "records": [item.model_dump(mode="json") for item in self.records]}


def _already_acted(state: StoryState, actor_id: str, action_id: str) -> bool:
    return any(record.op == "world_action" and record.entity == actor_id and record.target == action_id
               for record in state.effect_log)


def run_world_tick(state: StoryState, pack: ContentPack, rules: list[AutonomousRule], *,
                   actor_id: str = "world") -> WorldTickResult:
    """按规则让世界推进一格：主角不参与，也能发生行动与状态变化。"""

    working = state.model_copy(deep=True)
    acted: list[str] = []
    skipped: list[dict[str, Any]] = []
    records: list[EffectRecord] = []
    for rule in sorted(rules, key=lambda item: (-item.priority, item.actor_id, item.action_id)):
        if rule.once and _already_acted(working, rule.actor_id, rule.action_id):
            skipped.append({"actor": rule.actor_id, "action": rule.action_id, "code": "ALREADY_ACTED"})
            continue
        try:
            action: Action = pack.action(rule.action_id)
        except Exception:  # noqa: BLE001 - 内容包缺少行动时跳过并记录
            skipped.append({"actor": rule.actor_id, "action": rule.action_id, "code": "ACTION_NOT_FOUND"})
            continue
        for requirement in action.requirements:
            from .conditions import evaluate

            result = evaluate(requirement, working, actor=rule.actor_id)
            if not result.ok:
                skipped.append({"actor": rule.actor_id, "action": rule.action_id,
                                "code": result.code or "REQUIREMENT_NOT_SATISFIED",
                                "message": result.message})
                break
        else:
            outcome = apply_effects(working, action.costs + action.immediate_effects,
                                    actor=rule.actor_id, source=f"world:{rule.actor_id}:{rule.action_id}")
            if not outcome.ok:
                skipped.append({"actor": rule.actor_id, "action": rule.action_id,
                                "code": outcome.code, "message": outcome.message})
                continue
            working = outcome.state
            record = EffectRecord(id=f"world:{rule.actor_id}:{rule.action_id}:{len(working.effect_log) + 1}",
                                  op="world_action", entity=rule.actor_id, target=rule.action_id,
                                  source=f"world_tick:{rule.label or rule.actor_id}",
                                  order=len(working.effect_log) + 1,
                                  data={"label": rule.label, **(rule.data or {})})
            working.effect_log.append(record)
            records.extend(outcome.records + [record])
            acted.append(f"{rule.actor_id}:{rule.action_id}")
            continue
        continue
    # 记录一次世界推进：effect_log 里能看到“世界用哪条规则推进过”。
    marker = EffectRecord(id=f"world_tick:{len(working.effect_log) + 1}", op="world_tick",
                          entity=actor_id, target="",
                          source="world_tick", order=len(working.effect_log) + 1,
                          data={"acted": list(acted),
                                "skipped": [item.get("code", "") for item in skipped]})
    working.effect_log.append(marker)
    records.append(marker)
    return WorldTickResult(state=working, acted=acted, skipped=skipped, records=records)


class WorldEventResult(StrictModel):
    ok: bool = True
    state: StoryState
    fired: list[str] = Field(default_factory=list)
    skipped: list[dict[str, Any]] = Field(default_factory=list)
    records: list[EffectRecord] = Field(default_factory=list)
    unclaimed_knowledge: list[str] = Field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {"ok": self.ok, "fired": list(self.fired), "skipped": list(self.skipped),
                "unclaimed_knowledge": list(self.unclaimed_knowledge),
                "records": [item.model_dump(mode="json") for item in self.records]}


def run_world_events(state: StoryState, catalog: EventCardCatalog, *, actor: str = "world",
                     limit: int = 3, min_tick_gap: int = 0) -> WorldEventResult:
    """触发世界事件：主角不参与也能发生；知识默认不交给任何角色。

    事件本身仍由 EventCard + EventTriggerEngine 负责，这里只做世界视角的调度与知识登记。
    `min_tick_gap` 是内容包声明的密度调节：两次世界事件之间至少间隔多少个 tick。
    """

    engine = EventTriggerEngine(catalog)
    working = state.model_copy(deep=True)
    fired: list[str] = []
    skipped: list[dict[str, Any]] = []
    records: list[EffectRecord] = []
    unclaimed: list[str] = []
    for card in catalog.cards:
        if card.scope != "world" or len(fired) >= limit:
            continue
        if min_tick_gap > 0 and _last_world_event_tick(working, card.event_id) >= 0:
            last_tick = _last_world_event_tick(working, card.event_id)
            if working.timeline.tick - last_tick < min_tick_gap:
                skipped.append({"event": card.event_id, "code": "WORLD_EVENT_GAP",
                                "message": f"距离上次触发只有 {working.timeline.tick - last_tick} tick"})
                continue
        outcome = engine.fire(working, card.event_id, actor=actor)
        if not outcome.ok:
            skipped.append({"event": card.event_id, "code": outcome.code, "message": outcome.message})
            continue
        working = outcome.state
        records.extend(outcome.records)
        fired.append(card.event_id)
        if card.knowledge_id:
            existing = next((item for item in working.knowledge if item.id == card.knowledge_id), None)
            if existing is None:
                working.knowledge.append(KnowledgeEntry(id=card.knowledge_id, holders=[],
                                                        source=f"world_event:{card.event_id}",
                                                        reader_visible=card.reader_visible))
                unclaimed.append(card.knowledge_id)
        records.append(EffectRecord(id=f"world_event:{card.event_id}:{len(working.effect_log) + 1}",
                                    op="world_event", entity=actor, target=card.event_id,
                                    source=f"world_event:{card.event_id}",
                                    order=len(working.effect_log) + 1,
                                    data={"knowledge_id": card.knowledge_id,
                                          "tick": working.timeline.tick}))
        working.effect_log.append(records[-1])
    return WorldEventResult(state=working, fired=fired, skipped=skipped, records=records,
                            unclaimed_knowledge=unclaimed)


def _last_world_event_tick(state: StoryState, event_id: str) -> int:
    """该世界事件上一次触发的 tick（从未触发返回 -1）。"""

    rows = [int((item.data or {}).get("tick", 0) or 0) for item in state.effect_log
            if item.op == "world_event" and item.target == event_id]
    return max(rows) if rows else -1


def world_event_density(state: StoryState) -> list[dict[str, Any]]:
    """世界事件密度：每个世界事件最近一次触发的 tick 与间隔（只读）。"""

    rows: dict[str, list[int]] = {}
    for item in state.effect_log:
        if item.op == "world_event" and item.target:
            rows.setdefault(item.target, []).append(int((item.data or {}).get("tick", 0) or 0))
    return [{"event_id": event_id, "fired": len(ticks), "last_tick": max(ticks),
             "gap": state.timeline.tick - max(ticks)}
            for event_id, ticks in sorted(rows.items())]


def claim_world_knowledge(state: StoryState, knowledge_id: str, holder: str) -> tuple[StoryState, bool]:
    """合法来源：把世界事件的知识交给某个角色（例如亲眼见到、被人告知）。"""

    working = state.model_copy(deep=True)
    for index, item in enumerate(working.knowledge):
        if item.id != knowledge_id:
            continue
        if holder in item.holders:
            return working, False
        working.knowledge[index] = item.model_copy(update={"holders": item.holders + [holder]})
        return working, True
    return state, False
