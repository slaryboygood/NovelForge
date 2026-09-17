"""记忆面板视图（V2-I-05）。

三视角知识差异与未解决项：

- author  ：StoryState.author_knowledge（作者安排、真相、计划）
- reader  ：StoryState.knowledge 中 reader_visible=True
- character：StoryState.knowledge 中 holders 含该角色

承诺 / 债务 / 人情、仇恨来源、未解决冲突、未回收伏笔全部由既有查询函数推导，
不复制数据；伏笔定义来自内容包或 Novel Profile，是否回收仍以 Foreshadow 状态为准。
"""

from __future__ import annotations

from typing import Any

from .foreshadow import Foreshadow, foreshadow_timeline, payoff_ready
from .memory import (
    ConflictRow,
    author_only,
    hostility_sources,
    holders_of,
    open_foreshadows,
    outstanding_promises,
    overdue_promises,
    reader_only_states,
    unresolved_conflicts,
)
from .state import StoryState

OBLIGATION_QUERIES = ("promise", "debt", "favor")


def _knowledge_row(item) -> dict[str, Any]:
    return {
        "id": item.id,
        "certainty": item.certainty,
        "holders": list(item.holders),
        "source": item.source,
        "source_event": item.source_event,
        "tick": item.tick,
        "reader_visible": item.reader_visible,
    }


def _promise_row(item, state: StoryState) -> dict[str, Any]:
    overdue = bool(item.due_tick and item.due_tick <= state.timeline.tick
                   and item.status == "open")
    return {
        "id": item.id,
        "kind": str((item.data or {}).get("obligation_type", "promise")),
        "debtor": item.debtor,
        "creditor": item.creditor,
        "description": item.description,
        "status": item.status,
        "source": item.source,
        "created_tick": item.created_tick,
        "due_tick": item.due_tick,
        "settled_tick": item.settled_tick,
        "overdue": overdue,
        "note": (item.data or {}).get("note", ""),
    }


def _conflict_row(item: ConflictRow) -> dict[str, Any]:
    return item.as_dict()


def foreshadow_rows(pack_foreshadows: list[Foreshadow], state: StoryState) -> list[dict[str, Any]]:
    runtime = state.flags.get("foreshadows", {}) or {}
    rows = []
    for item in pack_foreshadows:
        entry = dict(runtime.get(item.id, {}) or {}) if isinstance(runtime, dict) else {}
        ready = False
        ready_reason = ""
        if item.payoff_condition is not None:
            ready, ready_reason = payoff_ready(item, state)
        elif item.payoff_options:
            results = [payoff_ready(item, state, choice=name) for name in item.payoff_options]
            ready = any(flag for flag, _ in results)
            ready_reason = next((reason for flag, reason in results if flag), "")
        rows.append({
            "id": item.id,
            "title": item.title or item.id,
            # 运行时状态优先（StoryState.flags["foreshadows"]），否则回落内容包定义。
            "status": str(entry.get("status", "") or item.status),
            "planted_in": item.planted_in,
            "payoff_in": item.payoff_in,
            "has_payoff_condition": item.payoff_condition is not None or bool(item.payoff_options),
            "payoff_ready": ready,
            "payoff_reason": ready_reason,
            "transformed_into": item.transformed_into,
            "author_note": item.author_note,
            "planted_tick": int((item.data or {}).get("planted_tick", 0) or 0),
            "reinforce_count": int(entry.get("reinforce_count", 0) or 0),
            "runtime_source": str(entry.get("source", "") or ""),
            "runtime_tick": int(entry.get("tick", 0) or 0),
            "runtime_reason": str(entry.get("reason", "") or ""),
        })
    return rows


def foreshadow_source(context) -> list[Foreshadow]:
    if context.pack is not None and context.pack.foreshadows:
        return list(context.pack.foreshadows)
    payload = context.profile.world_profile.get("foreshadows")
    if isinstance(payload, list):
        rows = []
        for item in payload:
            try:
                rows.append(Foreshadow.model_validate(item))
            except Exception:  # noqa: BLE001 - 单条格式错误不影响其他伏笔
                continue
        return rows
    return []


def memory_snapshot(context) -> dict[str, Any]:
    """记忆面板数据；三视角与未解决项全部来自 StoryState 与内容包。"""

    state = context.state
    characters = sorted(state.characters)
    obligations = [_promise_row(item, state) for item in state.promises]
    outstanding = [_promise_row(item, state) for item in outstanding_promises(state)]
    overdue = [_promise_row(item, state) for item in overdue_promises(state)]
    by_kind = {kind: [item for item in obligations if item["kind"] == kind]
               for kind in OBLIGATION_QUERIES}
    conflicts = [_conflict_row(item) for item in unresolved_conflicts(state)]
    conflicts_by_kind: dict[str, list[dict[str, Any]]] = {}
    for row in conflicts:
        conflicts_by_kind.setdefault(row["kind"], []).append(row)
    hostility = []
    for item in state.relationships:
        degree = item.dimensions.get("hostility", 0)
        if degree <= 0:
            continue
        sources = hostility_sources(state, item.source_id, item.target_id)
        hostility.append({
            "source_id": item.source_id, "target_id": item.target_id,
            "hostility": float(degree),
            "sources": sources,
            "latest_reason": sources[-1]["reason"] if sources else "",
            "latest_tick": sources[-1]["tick"] if sources else 0,
        })
    all_foreshadows = foreshadow_source(context)
    open_rows = foreshadow_rows(open_foreshadows(all_foreshadows), state)
    return {
        "meta": context.meta(),
        "characters": characters,
        "author": {
            "entries": [_knowledge_row(item) for item in state.author_knowledge],
            "author_only": author_only(state),
        },
        "reader": {
            "entries": [_knowledge_row(item) for item in state.knowledge if item.reader_visible],
        },
        "character_knowledge": {name: [_knowledge_row(item) for item in state.knowledge
                                       if name in item.holders]
                                for name in characters},
        "knowledge_index": [_knowledge_row(item) for item in
                            (state.knowledge + state.author_knowledge)],
        "holders": {item.id: holders_of(state, item.id) for item in state.knowledge},
        "reader_only": {name: reader_only_states(state, name) for name in characters},
        "obligations": {
            "all": obligations,
            "by_kind": by_kind,
            "outstanding": outstanding,
            "overdue": overdue,
        },
        "hostility": hostility,
        "conflicts": conflicts,
        "conflicts_by_kind": conflicts_by_kind,
        "foreshadows": foreshadow_rows(all_foreshadows, state),
        "foreshadow_timeline": foreshadow_timeline(state),
        "open_foreshadows": open_rows,
        "counts": {
            "author": len(state.author_knowledge),
            "reader": len([item for item in state.knowledge if item.reader_visible]),
            "character": len(state.knowledge),
            "obligations": len(obligations),
            "outstanding": len(outstanding),
            "overdue": len(overdue),
            "conflicts": len(conflicts),
            "foreshadows": len(all_foreshadows),
            "open_foreshadows": len(open_rows),
        },
    }
