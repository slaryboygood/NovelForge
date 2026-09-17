"""世界面板视图（V2-I-01）。

把 StoryState 里的世界事实投影成只读视图：时间 / 地点 / 势力 / 世界事件 / 自主行动。

- 只读：不写入 StoryState，也不缓存第二份世界状态。
- 文案来源：地点名、势力名、事件标题全部来自 StoryState 与内容包数据，
  引擎不写死任何题材名词。
- 世界事件与自主行动都从 `effect_log` 追溯，保证 UI 显示的内容和事实一致。
"""

from __future__ import annotations

from typing import Any

from .content import ContentPack
from .entities import EffectRecord
from .events import EventCard, EventCardCatalog, EventTriggerEngine
from .linkage import plot_tracks
from .state import StoryState

DEFAULT_FEED_LIMIT = 8
ACTION_NOT_FOUND = "ACTION_NOT_FOUND"


def _entity_label(state: StoryState, actor_id: str) -> tuple[str, str]:
    """返回 (显示名, 类别)；类别只表达通用实体类型，不代表题材。"""

    if not actor_id:
        return "", "world"
    character = state.characters.get(actor_id)
    if character is not None:
        return character.name or actor_id, "character"
    faction = state.factions.get(actor_id)
    if faction is not None:
        return faction.name or actor_id, "faction"
    for track in plot_tracks(state):
        if track.id == actor_id:
            return track.title or actor_id, "plot"
    if actor_id == "world":
        return "世界", "world"
    return actor_id, "world"


def _location_label(state: StoryState, location_id: str) -> str:
    if not location_id:
        return ""
    entry = state.location.known.get(location_id)
    return (entry.name or entry.id) if entry is not None else location_id


def _world_tick_records(state: StoryState) -> list[EffectRecord]:
    return [item for item in state.effect_log if item.op == "world_tick"]


def _history_of(state: StoryState, event_id: str, op: str) -> list[EffectRecord]:
    return [item for item in state.effect_log if item.op == op and item.target == event_id]


def recent_world_events(state: StoryState, catalog: EventCardCatalog | None, *,
                        limit: int = DEFAULT_FEED_LIMIT) -> list[dict[str, Any]]:
    """已发生的世界事件（从 effect_log 追溯，不含尚未发生的事件）。"""

    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for record in reversed(state.effect_log):
        if record.op != "world_event" or record.target in seen:
            continue
        seen.add(record.target)
        card = _card(catalog, record.target)
        data = dict(record.data or {})
        history = _history_of(state, record.target, "world_event")
        rows.append({
            "event_id": record.target,
            "title": (card.title if card is not None else "") or data.get("label", "") or record.target,
            "kind": card.kind if card is not None else "",
            "scope": card.scope if card is not None else "world",
            "order": record.order,
            "tick": int(data.get("tick", 0) or 0),
            "source": record.source,
            "actor": record.entity,
            "actor_label": _entity_label(state, record.entity)[0],
            "occurrences": len(history),
            "knowledge_id": data.get("knowledge_id", "") or (card.knowledge_id if card is not None else ""),
        })
        if len(rows) >= limit:
            break
    return rows


def recent_autonomous_actions(state: StoryState, pack: ContentPack | None, *,
                              limit: int = DEFAULT_FEED_LIMIT) -> list[dict[str, Any]]:
    """NPC / 势力自主行动：来自 world_tick 的行动记录，主角不参与也会发生。"""

    rows: list[dict[str, Any]] = []
    seen: set[tuple[str, str, int]] = set()
    for record in reversed(state.effect_log):
        if record.op != "world_action":
            continue
        key = (record.entity, record.target, record.order)
        if key in seen:
            continue
        seen.add(key)
        label, kind = _entity_label(state, record.entity)
        action_label = ""
        if pack is not None:
            try:
                action = pack.action(record.target)
                action_label = action.name or action.id
            except Exception:  # noqa: BLE001 - 内容包缺少行动时只显示编号
                action_label = ""
        data = dict(record.data or {})
        rows.append({
            "order": record.order,
            "tick": int(data.get("tick", 0) or 0),
            "actor_id": record.entity,
            "actor_label": label,
            "actor_kind": kind,
            "action_id": record.target,
            "action_label": action_label or data.get("label", "") or record.target,
            "source": record.source,
            "reason": data.get("label", "") or record.source,
        })
        if len(rows) >= limit:
            break
    return rows


def _event_row(state: StoryState, card: EventCard, availability) -> dict[str, Any]:
    history = _history_of(state, card.event_id, "fire_event") + _history_of(state, card.event_id, "world_event")
    data = dict(card.data or {})
    return {
        "event_id": card.event_id,
        "title": card.title or card.event_id,
        "kind": card.kind,
        "scope": card.scope,
        "priority": card.priority,
        "available": availability.available,
        "code": availability.code,
        "reason": availability.reason,
        "occurrences": len(history),
        "foreshadow": bool(data.get("foreshadow")),
        "main_line": bool(data.get("main_line")),
    }


def _available_events(state: StoryState, catalog: EventCardCatalog | None) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for event_id in (item.id for item in state.active_events if item.id):
        if event_id in seen:
            continue
        seen.add(event_id)
        card = _card(catalog, event_id)
        rows.append({"event_id": event_id, "title": card.title if card is not None else event_id,
                     "kind": card.kind if card is not None else "",
                     "scope": card.scope if card is not None else "scene",
                     "priority": card.priority if card is not None else 0,
                     "source": "active_event"})
    if catalog is not None:
        engine = EventTriggerEngine(catalog)
        for availability in engine.available(state):
            if availability.event_id in seen:
                continue
            seen.add(availability.event_id)
            try:
                card = catalog.by_id(availability.event_id)
            except KeyError:
                continue
            rows.append({"event_id": card.event_id, "title": card.title or card.event_id,
                         "kind": card.kind, "scope": card.scope, "priority": card.priority,
                         "source": "available"})
    return sorted(rows, key=lambda item: (-int(item["priority"]), str(item["event_id"])))


def _faction_rows(state: StoryState) -> list[dict[str, Any]]:
    rows = []
    for faction_id in sorted(state.factions):
        entry = state.factions[faction_id]
        data = dict(entry.data or {})
        rows.append({
            "id": entry.id,
            "name": entry.name or entry.id,
            "kind": entry.kind,
            "tags": list(entry.tags),
            "stance": entry.stance,
            "influence": data.get("influence"),
            "resources": data.get("resources"),
            "internal_conflicts": data.get("internal_conflicts") or data.get("conflicts") or [],
            "active_plots": [item.id for item in plot_tracks(state)
                             if item.status == "active" and faction_id in item.factions],
            "data": data,
        })
    return rows


def action_ids(pack: ContentPack | None) -> list[str]:
    """内容包声明的全部行动 id：选择集 + 事件可用行动，保持稳定顺序。"""

    if pack is None:
        return []
    ids: list[str] = []
    for rules in pack.choice_sets.values():
        for rule in sorted(rules, key=lambda item: (item.order, item.action_id)):
            if rule.action_id not in ids:
                ids.append(rule.action_id)
    for card in pack.events:
        for action_id in card.available_actions:
            if action_id not in ids:
                ids.append(action_id)
    for action in pack.actions:
        if action.id not in ids:
            ids.append(action.id)
    return ids


def _location_rows(state: StoryState) -> list[dict[str, Any]]:
    rows = []
    for location_id in sorted(state.location.known):
        entry = state.location.known[location_id]
        data = dict(entry.data or {})
        rows.append({
            "id": entry.id,
            "name": entry.name or entry.id,
            "kind": entry.kind,
            "tags": list(entry.tags),
            "access": entry.access,
            "control": data.get("control", ""),
            "danger": data.get("danger", data.get("danger_level")),
            "current": location_id == state.location.current,
            "visited": location_id in state.location.visited,
            "data": data,
        })
    return rows


def _last_effect(state: StoryState, ops: tuple[str, ...]) -> dict[str, Any] | None:
    for record in reversed(state.effect_log):
        if record.op not in ops:
            continue
        data = dict(record.data or {})
        return {"op": record.op, "entity": record.entity, "target": record.target,
                "source": record.source, "order": record.order,
                "tick": int(data.get("tick", 0) or 0)}
    return None


def world_snapshot(context, *, feed_limit: int = DEFAULT_FEED_LIMIT) -> dict[str, Any]:
    """世界面板数据：全部来自 StoryState 与内容包，前端不再自行计算。"""

    state = context.state
    catalog = _catalog(context.pack)
    timeline = state.timeline
    current = state.location.current
    location_entry = state.location.known.get(current) if current else None
    location_data = dict(location_entry.data) if location_entry is not None else {}
    flags = {key: value for key, value in state.flags.items() if key not in ("ui_preview", "journey_revision")}
    known_events = {item.id: item for item in state.active_events + state.resolved_events}
    data = {
        "meta": context.meta(),
        "timeline": {
            "tick": timeline.tick,
            "current_time": timeline.current_time,
            "elapsed": timeline.elapsed,
            "markers": list(timeline.markers),
            "world_ticks": len(_world_tick_records(state)),
        },
        "location": {
            "current": current,
            "name": (location_entry.name or location_entry.id) if location_entry is not None else "",
            "kind": location_entry.kind if location_entry is not None else "",
            "access": location_entry.access if location_entry is not None else "",
            "control": location_data.get("control", ""),
            "danger": location_data.get("danger", location_data.get("danger_level")),
            "status": location_data.get("status", ""),
            "visited": list(state.location.visited),
            "visited_labels": [_location_label(state, item) for item in state.location.visited],
            "known": _location_rows(state),
        },
        "factions": _faction_rows(state),
        "recent_world_events": recent_world_events(state, catalog, limit=feed_limit),
        "recent_autonomous_actions": recent_autonomous_actions(state, context.pack, limit=feed_limit),
        "available_events": _available_events(state, catalog),
        "active_plots": [
            {"id": item.id, "title": item.title or item.id, "status": item.status,
             "progress": item.progress, "priority": item.priority,
             "characters": list(item.characters), "factions": list(item.factions),
             "locations": list(item.locations), "updated_tick": item.updated_tick}
            for item in sorted(plot_tracks(state), key=lambda item: (-item.priority, item.id))
        ],
        "world_flags": flags,
        "resources": [
            {"id": item.id, "amount": item.amount, "unit": item.unit, "holders": list(item.holders)}
            for item in sorted(state.resources.values(), key=lambda item: item.id)
        ],
        "event_records": [
            {"id": item.id, "status": item.status, "source": item.source,
             "participants": list(item.participants),
             "title": (_card(catalog, item.id).title if _card(catalog, item.id) is not None else item.id)}
            for item in sorted(known_events.values(), key=lambda item: item.id)
        ],
        "last_change": _last_effect(state, ("update_location", "update_faction", "advance_time",
                                            "change_location", "world_action", "world_event")),
    }
    return data


def _card(catalog: EventCardCatalog | None, event_id: str) -> EventCard | None:
    if catalog is None or not event_id:
        return None
    try:
        return catalog.by_id(event_id)
    except KeyError:
        return None


def _catalog(pack: ContentPack | None) -> EventCardCatalog | None:
    if pack is None:
        return None
    return EventCardCatalog(catalog_id=f"{pack.pack_id}_events", cards=list(pack.events))
