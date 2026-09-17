"""Event Card 事件引擎（主计划 T08a / T08b）。

事件卡只描述结构：触发条件、参与者、场景目标、冲突、可用行动、后果、
后续事件、优先级、冷却与是否只发生一次。小说文本由 Writer 负责，
引擎不在这里写 prose。

触发完全由 StoryState 计算，因此不同选择会得到不同的事件池；
once_only 与 cooldown 由引擎记录，避免同一事件反复触发。
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from pydantic import Field, model_validator

from novelforge.models import StrictModel

from .conditions import Condition, evaluate
from .effects import EffectSpec, apply_effects
from .entities import EffectRecord
from .state import StoryState


class EventCard(StrictModel):
    event_id: str = Field(pattern=r"^[a-z][a-z0-9_]{2,95}$")
    title: str = Field(default="", max_length=120)
    kind: str = Field(default="", max_length=64)
    trigger: Condition
    participants: list[str] = Field(default_factory=list)
    scene_goal: str = Field(default="", max_length=300)
    conflict: str = Field(default="", max_length=300)
    available_actions: list[str] = Field(default_factory=list)
    consequences: list[EffectSpec] = Field(default_factory=list)
    followups: list[str] = Field(default_factory=list)
    priority: int = Field(default=0, ge=-100, le=100)
    cooldown: int = Field(default=0, ge=0, le=1000)
    once_only: bool = True
    # 事件范围：scene = 主角场景事件；world = 世界事件（主角可以不参与、事后才得知）。
    scope: str = Field(default="scene", max_length=32)
    # 世界事件产生的知识：默认不交给任何角色；只有合法来源才能让角色获得。
    knowledge_id: str = Field(default="", max_length=128)
    reader_visible: bool = False
    data: dict[str, Any] = Field(default_factory=dict)


class EventCardCatalog(StrictModel):
    schema_version: int = 1
    catalog_id: str = Field(default="events", max_length=96)
    cards: list[EventCard] = Field(default_factory=list)

    @model_validator(mode="after")
    def unique_event_ids(self) -> "EventCardCatalog":
        ids = [item.event_id for item in self.cards]
        if len(ids) != len(set(ids)):
            raise ValueError("event ids must be unique")
        return self

    def by_id(self, event_id: str) -> EventCard:
        for item in self.cards:
            if item.event_id == event_id:
                return item
        raise KeyError(event_id)


def event_catalog_from_payload(payload: Mapping[str, Any]) -> EventCardCatalog:
    return EventCardCatalog.model_validate(dict(payload))


class EventAvailability(StrictModel):
    event_id: str
    available: bool
    priority: int = 0
    code: str = ""
    reason: str = ""

    def as_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json")


class EventFireResult(StrictModel):
    ok: bool
    event_id: str
    code: str = ""
    message: str = ""
    state: StoryState
    records: list[EffectRecord] = Field(default_factory=list)
    activated_followups: list[str] = Field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {"ok": self.ok, "event_id": self.event_id, "code": self.code, "message": self.message,
                "records": [item.model_dump(mode="json") for item in self.records],
                "activated_followups": list(self.activated_followups)}


class EventTriggerEngine:
    """根据 StoryState 计算可触发事件，并记录触发历史。"""

    def __init__(self, catalog: EventCardCatalog) -> None:
        self.catalog = catalog

    def _occurrences(self, state: StoryState, event_id: str) -> list[int]:
        return [record.order for record in state.effect_log if record.op == "fire_event" and record.target == event_id]

    def _blocked_reason(self, card: EventCard, state: StoryState, actor: str) -> tuple[bool, str, str]:
        fired = self._occurrences(state, card.event_id)
        if card.once_only and (fired or any(item.id == card.event_id for item in state.active_events + state.resolved_events)):
            return False, "EVENT_ALREADY_FIRED", "该事件已经发生过"
        if card.cooldown and fired:
            progress = len(state.effect_log) - fired[-1]
            if progress < card.cooldown:
                return False, "EVENT_COOLDOWN", f"事件冷却中（{progress}/{card.cooldown}）"
        result = evaluate(card.trigger, state, actor=actor)
        if not result.ok:
            return False, result.code or "EVENT_TRIGGER_NOT_SATISFIED", result.message or "触发条件不满足"
        return True, "", ""

    def availability(self, state: StoryState, *, actor: str = "") -> list[EventAvailability]:
        rows = []
        for card in self.catalog.cards:
            ok, code, reason = self._blocked_reason(card, state, actor)
            rows.append(EventAvailability(event_id=card.event_id, available=ok, priority=card.priority,
                                          code=code, reason=reason))
        return sorted(rows, key=lambda item: (-item.priority, item.event_id))

    def available(self, state: StoryState, *, actor: str = "") -> list[EventAvailability]:
        return [item for item in self.availability(state, actor=actor) if item.available]

    def fire(self, state: StoryState, event_id: str, *, actor: str = "") -> EventFireResult:
        try:
            card = self.catalog.by_id(event_id)
        except KeyError:
            return EventFireResult(ok=False, event_id=event_id, code="EVENT_NOT_FOUND",
                                   message="找不到这个事件", state=state)
        ok, code, reason = self._blocked_reason(card, state, actor)
        if not ok:
            return EventFireResult(ok=False, event_id=event_id, code=code, message=reason, state=state)
        applied = apply_effects(state, card.consequences, actor=actor, source=f"event:{event_id}")
        if not applied.ok:
            return EventFireResult(ok=False, event_id=event_id, code=applied.code,
                                   message=applied.message, state=state)
        working = applied.state
        if all(item.id != event_id for item in working.active_events + working.resolved_events):
            from .entities import EventRecord
            working.active_events.append(EventRecord(id=event_id, status="active",
                                                     source=f"event:{event_id}",
                                                     participants=list(card.participants)))
        record = EffectRecord(id=f"fire:{event_id}:{len(working.effect_log) + 1}", op="fire_event",
                              entity=actor, target=event_id, source=f"event:{event_id}",
                              order=len(working.effect_log) + 1)
        working.effect_log.append(record)
        followups = [item for item in card.followups if item]
        return EventFireResult(ok=True, event_id=event_id, state=working,
                               records=applied.records + [record], activated_followups=followups,
                               message="事件已触发")
