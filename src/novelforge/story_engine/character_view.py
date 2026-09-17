"""角色面板视图（V2-I-02）。

把角色自身的 StoryState 数据投影成只读视图：目标 / 记忆 / 多维关系 / 人物弧 /
最近自主行动 / 反应理由。

- 只读：不写入 StoryState，也不复制一份角色状态。
- 目标、记忆、弧都在角色自己的 data 里（characters.py / linkage.py 的对象），这里只读取与解释。
- 反应理由来自 `suggest_reactions`（同一套角色决策评分），前端不重新算分。
"""

from __future__ import annotations

from typing import Any

from .actions import Action
from .characters import (
    active_goals,
    build_decision_context,
    character_goals,
    character_memories,
    load_arc,
    select_goal,
    suggest_reactions,
)
from .content import ContentPack
from .linkage import arc_summary
from .state import StoryState
from .world_view import action_ids

DEFAULT_REACTION_LIMIT = 5
GOAL_SCOPES = ("long_term", "stage", "current")


def _goal_row(goal) -> dict[str, Any]:
    return {
        "id": goal.id,
        "scope": goal.scope,
        "title": goal.title,
        "description": goal.description,
        "priority": goal.priority,
        "weight": goal.weight,
        "score": goal.score(),
        "status": goal.status,
        "source": goal.source,
        "updated_tick": goal.updated_tick,
        "has_condition": goal.when is not None,
        "note": (goal.data or {}).get("note", ""),
    }


def _memory_row(memory) -> dict[str, Any]:
    return {
        "id": memory.id,
        "summary": memory.summary,
        "source": memory.source,
        "tick": memory.tick,
        "participants": list(memory.participants),
        "emotion": list(memory.emotion),
    }


def _relationship_rows(state: StoryState, character_id: str) -> list[dict[str, Any]]:
    rows = []
    for item in state.relationships:
        if item.source_id != character_id and item.target_id != character_id:
            continue
        other = item.target_id if item.source_id == character_id else item.source_id
        other_entry = state.characters.get(other)
        rows.append({
            "other_id": other,
            "other_label": (other_entry.name or other) if other_entry is not None else other,
            "direction": "outgoing" if item.source_id == character_id else "incoming",
            "dimensions": {key: float(value) for key, value in item.dimensions.items()},
            "tags": list(item.tags),
            "stage": (item.data or {}).get("stage", ""),
            "data": dict(item.data or {}),
        })
    return sorted(rows, key=lambda item: (item["direction"], item["other_id"]))


def _knowledge_rows(state: StoryState, character_id: str) -> list[dict[str, Any]]:
    return [
        {"id": item.id, "certainty": item.certainty, "source": item.source,
         "tick": item.tick, "reader_visible": item.reader_visible}
        for item in state.knowledge if character_id in item.holders
    ]


def _recent_actions(state: StoryState, character_id: str, pack: ContentPack | None,
                    *, limit: int = 8) -> list[dict[str, Any]]:
    """角色自己的行动痕迹：世界自主行动 + 该角色做出的选择。"""

    rows: list[dict[str, Any]] = []
    for record in reversed(state.effect_log):
        if record.op == "world_action" and record.entity == character_id:
            label = ""
            if pack is not None:
                try:
                    label = pack.action(record.target).name
                except Exception:  # noqa: BLE001 - 内容包缺行动时只显示编号
                    label = ""
            rows.append({"kind": "autonomous", "order": record.order, "target": record.target,
                         "label": label or record.target, "source": record.source,
                         "reason": (record.data or {}).get("label", ""),
                         "tick": int((record.data or {}).get("tick", 0) or 0)})
        elif record.op == "choice" and record.entity == character_id:
            rows.append({"kind": "choice", "order": record.order, "target": record.target,
                         "label": record.target, "source": record.source,
                         "reason": str((record.data or {}).get("result", "")),
                         "tick": int((record.data or {}).get("tick", 0) or 0)})
        if len(rows) >= limit:
            break
    return rows


def _reaction_rows(context, state: StoryState, pack: ContentPack | None,
                   *, limit: int = DEFAULT_REACTION_LIMIT) -> list[dict[str, Any]]:
    if pack is None:
        return []
    actions: list[Action] = [pack.action(action_id) for action_id in action_ids(pack)]
    if not actions:
        return []
    suggestions = suggest_reactions(context, actions, state)
    rows = []
    for item in suggestions[:limit]:
        try:
            action = pack.action(item.action_id)
            name = action.name or action.id
            kind = action.kind
        except Exception:  # noqa: BLE001
            name, kind = item.action_id, ""
        rows.append({"action_id": item.action_id, "name": name, "kind": kind,
                     "score": item.score, "reason": item.reason, "source": item.source})
    return rows


def character_summary(state: StoryState) -> list[dict[str, Any]]:
    rows = []
    for character_id in sorted(state.characters):
        entry = state.characters[character_id]
        rows.append({
            "id": entry.id,
            "name": entry.name or entry.id,
            "kind": entry.kind,
            "status": entry.status,
            "tags": list(entry.tags),
            "is_player": entry.kind == "player" or entry.id == "protagonist",
            "active_goals": len(active_goals(state, character_id)),
            "memories": len(character_memories(state, character_id)),
        })
    return rows


def character_snapshot(context, character_id: str, *,
                       include_reactions: bool = True) -> dict[str, Any]:
    """单个角色的完整视图；角色不存在时返回空视图，不编造数据。"""

    state = context.state
    entry = state.characters.get(character_id)
    goals = character_goals(state, character_id)
    by_scope = {scope: [_goal_row(item) for item in goals if item.scope == scope]
                for scope in GOAL_SCOPES}
    current_goal = select_goal(state, character_id)
    arc = load_arc(state, character_id)
    context_bundle = build_decision_context(state, character_id)
    return {
        "id": character_id,
        "name": (entry.name or entry.id) if entry is not None else character_id,
        "kind": entry.kind if entry is not None else "",
        "status": entry.status if entry is not None else "",
        "tags": list(entry.tags) if entry is not None else [],
        "exists": entry is not None,
        "current_goal": _goal_row(current_goal) if current_goal is not None else None,
        "goals": {
            "long_term": by_scope["long_term"],
            "stage": by_scope["stage"],
            "current": by_scope["current"],
            "active": [_goal_row(item) for item in active_goals(state, character_id)],
        },
        "memories": [_memory_row(item) for item in character_memories(state, character_id)],
        "relationships": _relationship_rows(state, character_id),
        "arc": arc_summary(arc) if arc is not None else None,
        "knowledge": _knowledge_rows(state, character_id),
        "drives": {
            "goal": context_bundle.goal,
            "desire": context_bundle.desire,
            "fear": context_bundle.fear,
            "personality": list(context_bundle.personality),
            "bottom_line": list(context_bundle.bottom_line),
            "current_pressure": context_bundle.current_pressure,
        },
        "recent_actions": _recent_actions(state, character_id, context.pack),
        "reactions": _reaction_rows(context_bundle, state, context.pack) if include_reactions else [],
    }


def character_snapshot_payload(context, character_id: str = "", *,
                               include_reactions: bool = True) -> dict[str, Any]:
    """角色面板数据：小说元信息 + 角色清单 + 选定角色详情。"""

    selected = character_id or _default_character(context.state)
    return {
        "meta": context.meta(),
        "characters": character_summary(context.state),
        "selected": selected,
        "detail": character_snapshot(context, selected, include_reactions=include_reactions) if selected else None,
    }


def _default_character(state: StoryState) -> str:
    for character_id, entry in state.characters.items():
        if entry.kind == "player":
            return character_id
    if "protagonist" in state.characters:
        return "protagonist"
    return next(iter(state.characters), "")

