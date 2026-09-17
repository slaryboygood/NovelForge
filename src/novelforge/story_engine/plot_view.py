"""剧情面板视图（V2-I-03）。

投影动态剧情数据：候选行动（available / unavailable + 原因 + 成本 + 风险）、
当前事件、活跃支线、事件连锁、世界变化对剧情的影响。

- 候选行动来自 `generate_candidates`（与真实执行同一套 Condition / 成本判定），
  前端不自己判断可用性。
- 当前事件与事件连锁从 StoryState.active_events / effect_log 追溯，不复制事件系统。
- 世界影响来自候选行动的条件引用了哪些世界状态，以及最近一次世界变化。
"""

from __future__ import annotations

from typing import Any

from .candidates import generate_candidates
from .content import ContentPack
from .events import EventCard, EventCardCatalog, EventTriggerEngine
from .journey import actor_for
from .linkage import plot_tracks
from .state import StoryState
from .world_view import action_ids

WORLD_OPS = ("update_location", "update_faction", "advance_time", "change_location",
             "world_action", "world_event", "set_flag", "increment_flag")
WINDOW_OPS = ("fire_event", "world_event", "world_action")


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


def _event_row(state: StoryState, catalog: EventCardCatalog | None, event_id: str,
               *, status: str) -> dict[str, Any]:
    card = _card(catalog, event_id)
    fired = [item for item in state.effect_log
             if item.op in ("fire_event", "world_event") and item.target == event_id]
    tracks = plot_tracks(state)
    def _plot_row(item) -> dict[str, Any]:
        return {
            "id": item.id, "title": item.title or item.id, "status": item.status,
            "progress": item.progress, "priority": item.priority,
            "characters": list(item.characters), "factions": list(item.factions),
            "locations": list(item.locations), "foreshadows": list(item.foreshadows),
            "updated_tick": item.updated_tick, "source": item.source,
            "has_trigger": item.trigger is not None,
        }

    def _plots_with_status(*statuses: str) -> list[dict[str, Any]]:
        return [_plot_row(item) for item in sorted(tracks, key=lambda row: (-row.priority, row.id))
                if item.status in statuses]

    return {
        "event_id": event_id,
        "title": (card.title if card is not None else "") or event_id,
        "kind": card.kind if card is not None else "",
        "scope": card.scope if card is not None else "scene",
        "priority": card.priority if card is not None else 0,
        "status": status,
        "scene_goal": card.scene_goal if card is not None else "",
        "conflict": card.conflict if card is not None else "",
        "participants": list(card.participants) if card is not None else [],
        "available_actions": list(card.available_actions) if card is not None else [],
        "followups": list(card.followups) if card is not None else [],
        "occurrences": len(fired),
        "last_order": max((item.order for item in fired), default=0),
    }


def current_events(state: StoryState, catalog: EventCardCatalog | None) -> list[dict[str, Any]]:
    """进行中的事件；没有进行中事件时退回最近触发的事件。"""

    rows = [_event_row(state, catalog, item.id, status="active") for item in state.active_events if item.id]
    if rows:
        return sorted(rows, key=lambda item: (-item["priority"], item["event_id"]))
    latest: list[dict[str, Any]] = []
    seen: set[str] = set()
    for record in reversed(state.effect_log):
        if record.op not in ("fire_event", "world_event") or record.target in seen:
            continue
        seen.add(record.target)
        latest.append(_event_row(state, catalog, record.target, status="resolved"))
        if len(latest) >= 3:
            break
    return latest


def event_chain(state: StoryState, catalog: EventCardCatalog | None, *,
                limit: int = 12) -> list[dict[str, Any]]:
    """事件连锁：按 effect_log 顺序还原“一个事件触发了什么、又引出什么”。"""

    rows: list[dict[str, Any]] = []
    for record in state.effect_log:
        if record.op not in ("fire_event", "world_event"):
            continue
        card = _card(catalog, record.target)
        rows.append({
            "order": record.order,
            "event_id": record.target,
            "title": (card.title if card is not None else "") or record.target,
            "scope": card.scope if card is not None else "",
            "actor": record.entity,
            "source": record.source,
            "followups": list(card.followups) if card is not None else [],
        })
    return rows[-limit:]


def world_impacts(state: StoryState, candidates: list[Any]) -> list[dict[str, Any]]:
    """世界变化对剧情的影响：候选行动的条件引用了哪些世界状态。

    入参是候选行动的行数据（dict），因此这里只读 requirements 的通用字段，
    不依赖具体模型类型，也不会重新判定条件。
    """

    by_key: dict[str, dict[str, Any]] = {}
    for candidate in candidates:
        action_id = str(candidate.get("action_id", ""))
        available = bool(candidate.get("available"))
        block_code = str(candidate.get("code", ""))
        requirements = list(candidate.get("requirements") or [])
        for requirement in requirements:
            op = str(requirement.get("op", ""))
            key = str(requirement.get("key", "") or requirement.get("target", ""))
            if not key:
                continue
            entry = by_key.setdefault(key, {"key": key, "ops": [], "actions": [],
                                            "available_actions": [], "unavailable_actions": [],
                                            "cost_actions": [], "blocked_by_this_key": []})
            if op and op not in entry["ops"]:
                entry["ops"].append(op)
            if action_id not in entry["actions"]:
                entry["actions"].append(action_id)
            bucket = "available_actions" if available else "unavailable_actions"
            if action_id not in entry[bucket]:
                entry[bucket].append(action_id)
            # 候选行动不可用时，只有真正没通过的那条条件才算“被它挡住”。
            if op == "resource" and any(str(cost.get("target", "")) == key
                                        for cost in candidate.get("costs") or []):
                if action_id not in entry["cost_actions"]:
                    entry["cost_actions"].append(action_id)
            blocked_here = not available and key == _blocking_key(candidate, block_code)
            if blocked_here and action_id not in entry["blocked_by_this_key"]:
                entry["blocked_by_this_key"].append(action_id)
    rows = []
    for entry in by_key.values():
        impacted = bool(entry["blocked_by_this_key"])
        rows.append({**entry, "impacts_availability": impacted})
    return sorted(rows, key=lambda item: (not item["impacts_availability"], item["key"]))


def _blocking_key(candidate: dict[str, Any], block_code: str) -> str:
    """候选行动被挡下时，导致失败的条件 key / target（没有则空字符串）。"""

    if not block_code:
        return ""
    requirements = list(candidate.get("requirements") or [])
    if block_code == "RESOURCE_NOT_ENOUGH":
        paid = _first_requirement_key(requirements, "resource")
        if paid:
            return paid
        for cost in candidate.get("costs") or []:
            target = str(cost.get("target", "") or cost.get("key", ""))
            if target:
                return target
        return ""
    return _first_requirement_key(requirements, "")


def _first_requirement_key(requirements: list[dict[str, Any]], op_filter: str) -> str:
    for requirement in requirements:
        op = str(requirement.get("op", ""))
        if op_filter and op != op_filter:
            continue
        key = str(requirement.get("key", "") or requirement.get("target", ""))
        if key:
            return key
    return ""


def _last_world_change(state: StoryState) -> dict[str, Any] | None:
    for record in reversed(state.effect_log):
        if record.op not in WORLD_OPS:
            continue
        return {"op": record.op, "entity": record.entity, "target": record.target,
                "source": record.source, "order": record.order,
                "label": str((record.data or {}).get("label", ""))}
    return None


def _world_flag_row(key: str, state: StoryState, impacts: list[dict[str, Any]]) -> dict[str, Any]:
    entry = next((item for item in impacts if item["key"] == key), None)
    return {"key": key, "value": state.flags.get(key), "referenced_by": entry["actions"] if entry else [],
            "impacts_availability": bool(entry and entry["impacts_availability"])}


def plot_snapshot(context, *, actor: str = "") -> dict[str, Any]:
    """剧情面板数据；全部来自 StoryState 与内容包。"""

    state = context.state
    catalog = _catalog(context.pack)
    resolved_actor = actor or actor_for(state)
    ids = action_ids(context.pack)
    candidates = (generate_candidates(state, _action_catalog(context.pack), ids, actor=resolved_actor)
                  if context.pack is not None else [])
    payload_candidates = [item.as_dict() for item in candidates]
    impacts = world_impacts(state, payload_candidates)
    events = current_events(state, catalog)
    tracks = plot_tracks(state)

    def _plot_row(item: Any) -> dict[str, Any]:
        return {
            "id": item.id, "title": item.title or item.id, "status": item.status,
            "progress": item.progress, "priority": item.priority,
            "characters": list(item.characters), "factions": list(item.factions),
            "locations": list(item.locations), "foreshadows": list(item.foreshadows),
            "updated_tick": item.updated_tick, "source": item.source,
            "has_trigger": item.trigger is not None,
        }

    def _plots_with_status(*statuses: str) -> list[dict[str, Any]]:
        return [_plot_row(item)
                for item in sorted(tracks, key=lambda row: (-row.priority, row.id))
                if item.status in statuses]

    return {
        "meta": context.meta(),
        "actor": resolved_actor,
        "candidates": payload_candidates,
        "available": [item["action_id"] for item in payload_candidates if item["available"]],
        "unavailable": [item["action_id"] for item in payload_candidates if not item["available"]],
        "current_events": events,
        "event_chain": event_chain(state, catalog),
        "plots": [_plot_row(item) for item in sorted(tracks, key=lambda row: (-row.priority, row.id))],
        "active_plots": _plots_with_status("active", "paused"),
        "resolved_plots": _plots_with_status("completed", "failed", "abandoned"),
        "timeline": {"tick": state.timeline.tick, "current_time": state.timeline.current_time},
        "last_world_change": _last_world_change(state),
        "world_impacts": impacts,
        "world_flags": [_world_flag_row(key, state, impacts) for key in sorted(state.flags)
                        if key not in ("ui_preview", "journey_revision")],
        "event_history": [
            {"order": record.order, "op": record.op, "target": record.target,
             "title": (_card(catalog, record.target).title if _card(catalog, record.target) is not None
                       else record.target),
             "source": record.source}
            for record in state.effect_log if record.op in WINDOW_OPS
        ][-10:],
        "triggerable_events": [
            {"event_id": item.event_id, "available": item.available, "priority": item.priority,
             "code": item.code, "reason": item.reason,
             "title": (_card(catalog, item.event_id).title if _card(catalog, item.event_id) is not None
                       else item.event_id),
             "scope": (_card(catalog, item.event_id).scope if _card(catalog, item.event_id) is not None
                       else "")}
            for item in (EventTriggerEngine(catalog).availability(state, actor=resolved_actor)
                         if catalog is not None else [])
        ],
    }


def _action_catalog(pack: ContentPack):
    from .actions import ActionCatalog

    return ActionCatalog(catalog_id=f"{pack.pack_id}_actions", actions=list(pack.actions))
