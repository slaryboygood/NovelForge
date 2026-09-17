"""V2 Runtime Driver：把 Story Engine 的既有能力串成可循环推进的一条链（Pilot-01 最小修复）。

职责边界（只做 orchestration）：

    load → candidates → choose → resolve → consequences → world/events
         → director → writer → persist → next candidates

本模块**不实现**任何规则：

- 行动合法性 / 成本：`generate_candidates` + `ActionResolver`（同一套 Condition）
- 延迟后果：`delayed.settle_delayed`
- 世界推进 / NPC 自主行动 / 世界事件：`world.run_world_tick` / `world.run_world_events`
- 事件触发：`events.EventTriggerEngine`
- 导演：`director.decide`（只对已合法事件排序）
- 表现：`writer.build_writer_package` + `writer.render_scene`
- 持久化：调用方提供的 `StoryStateRepository`

旧 `Adventure` / `JourneyRuntime` 继续作为兼容适配层存在；本驱动不依赖 revision 场景路由。
"""

from __future__ import annotations

from typing import Any, Callable

from pydantic import Field

from novelforge.models import StrictModel

from .actions import ActionCatalog
from .candidates import ActionCandidate, generate_candidates
from .content import ContentPack
from .delayed import settle_delayed
from .director import DirectorDecision, decide, weights_from_config
from .entities import EffectRecord
from .effects import EffectSpec, apply_effects
from .events import EventCardCatalog, EventTriggerEngine
from .linkage import FuturePlan, plot_tracks, replan_with_plots, sync_plots
from .narrative import build_route, replan_long_line
from .resolver import ActionResolver
from .state import StoryState
from .world import run_world_events, run_world_tick
from .writer import WriterPackage, WriterResult, build_writer_package, render_scene

BLOCKED_NO_ACTIONS = "no_available_actions"
BLOCKED_UNKNOWN_ACTION = "action_not_in_catalog"
BLOCKED_ACTION_NOT_AVAILABLE = "action_not_available"
BLOCKED_STALE_REVISION = "stale_revision"

# 会被视为“足以影响未来”的状态变化（用于决定是否触发未来重规划）。
REPLAN_EFFECT_OPS = ("change_relationship", "add_knowledge", "add_identity", "remove_identity",
                     "grant_ability", "revoke_ability", "create_promise", "resolve_promise",
                     "update_faction", "update_location", "update_plot", "advance_time")


class AdvanceResult(StrictModel):
    """一次推进的结构化结果；不复制 StoryState，只给摘要与候选。"""

    ok: bool = True
    blocked: str = ""
    terminal: bool = False
    revision: int = 0
    tick: int = 0
    executed_action: str = ""
    outcome: str = ""
    code: str = ""
    message: str = ""
    effects: list[dict[str, Any]] = Field(default_factory=list)
    settled_delayed: list[str] = Field(default_factory=list)
    delayed_failures: list[dict[str, Any]] = Field(default_factory=list)
    world_actions: list[dict[str, Any]] = Field(default_factory=list)
    world_events: list[str] = Field(default_factory=list)
    triggered_events: list[str] = Field(default_factory=list)
    director_decision: dict[str, Any] = Field(default_factory=dict)
    writer_result: dict[str, Any] = Field(default_factory=dict)
    current_state_summary: dict[str, Any] = Field(default_factory=dict)
    next_candidates: list[dict[str, Any]] = Field(default_factory=list)
    available_actions: list[str] = Field(default_factory=list)
    diagnostics: list[dict[str, Any]] = Field(default_factory=list)
    plot_transitions: list[dict[str, Any]] = Field(default_factory=list)
    future_plan_changed: bool = False
    replan_reason: str = ""
    old_future_summary: list[dict[str, Any]] = Field(default_factory=list)
    new_future_summary: list[dict[str, Any]] = Field(default_factory=list)
    future_plan: list[dict[str, Any]] = Field(default_factory=list)
    state: StoryState

    def as_dict(self) -> dict[str, Any]:
        payload = self.model_dump(mode="json")
        payload.pop("state", None)
        return payload


def story_revision(state: StoryState) -> int:
    """运行态 revision：已发生选择 / 行动的数量（不依赖 Journey 的 revision 场景路由）。"""

    return len([item for item in state.effect_log if item.op in ("choice", "runtime_action")])


def _action_catalog(pack: ContentPack) -> ActionCatalog:
    return ActionCatalog(catalog_id=f"{pack.pack_id}_actions", actions=list(pack.actions))


def event_catalog(pack: ContentPack) -> EventCardCatalog:
    return EventCardCatalog(catalog_id=f"{pack.pack_id}_events", cards=list(pack.events))


def runtime_action_ids(pack: ContentPack) -> list[str]:
    """驱动层可执行的全部行动：内容包声明的全部 Action。"""

    return [item.id for item in pack.actions]


def _summarize(state: StoryState) -> dict[str, Any]:
    return {
        "revision": story_revision(state),
        "tick": state.timeline.tick,
        "current_time": state.timeline.current_time,
        "location": state.location.current,
        "characters": sorted(state.characters),
        "resources": {key: value.amount for key, value in state.resources.items()},
        "abilities": sorted(state.abilities),
        "identities": {key: list(value) for key, value in state.identities.items()},
        "flags": {key: value for key, value in state.flags.items() if key != "ui_preview"},
        "knowledge": [item.id for item in state.knowledge],
        "active_events": [item.id for item in state.active_events],
        "plots": {key: value.get("status", "") for key, value in state.plots.items()},
        "effect_log": len(state.effect_log),
        "delayed_effects": [str(item.get("id", "")) for item in state.delayed_effects],
    }


def _candidate_rows(rows: list[ActionCandidate]) -> list[dict[str, Any]]:
    return [item.as_dict() for item in rows]


def candidates_for(state: StoryState, pack: ContentPack, *, actor: str = "",
                   action_ids: list[str] | None = None) -> list[ActionCandidate]:
    """当前状态下由引擎生成的候选行动；驱动层与 UI 共用同一条生成路径。"""

    return generate_candidates(state, _action_catalog(pack),
                               list(action_ids) if action_ids else runtime_action_ids(pack),
                               actor=actor)


def _settle(state: StoryState, *, actor: str) -> tuple[StoryState, list[str], list[dict[str, Any]]]:
    outcome = settle_delayed(state, actor=actor)
    return outcome.state, list(outcome.settled), list(outcome.failures)


def _advance_time(state: StoryState, *, ticks: int, actor: str) -> StoryState:
    """一个运行回合让世界时间前进一格；复用既有 advance_time 效果，不另写时间规则。"""

    if ticks <= 0:
        return state
    outcome = apply_effects(state, [EffectSpec(op="advance_time", value=ticks)],
                            actor=actor, source="runtime_turn")
    return outcome.state if outcome.ok else state


def _plot_rows(state: StoryState) -> list[dict[str, Any]]:
    return [{"id": item.id, "status": item.status, "progress": item.progress,
             "priority": item.priority, "updated_tick": item.updated_tick}
            for item in sorted(plot_tracks(state), key=lambda row: row.id)]


def _sync_plots(state: StoryState, *, before: list[dict[str, Any]],
                diagnostics: list[dict[str, Any]]) -> tuple[StoryState, list[dict[str, Any]]]:
    """世界状态满足条件的支线自动激活（复用既有 sync_plots），并记录状态流转。"""

    working = sync_plots(state)
    after = _plot_rows(working)
    previous = {item["id"]: item for item in before}
    transitions = []
    for row in after:
        old = previous.get(row["id"])
        if old is None:
            transitions.append({"plot": row["id"], "from": "", "to": row["status"],
                                "progress": row["progress"]})
            continue
        if old["status"] != row["status"] or old["progress"] != row["progress"]:
            transitions.append({"plot": row["id"], "from": old["status"], "to": row["status"],
                                "progress": row["progress"]})
    if transitions:
        diagnostics.append({"code": "PLOT_TRANSITIONS", "count": len(transitions),
                            "items": transitions})
    return working, transitions


def _future_plan_payload(plan: FuturePlan) -> list[dict[str, Any]]:
    return [{"id": stage.id, "title": stage.title, "goal": stage.goal,
             "status": stage.status, "note": stage.note} for stage in plan.stages]


def _maybe_replan(state: StoryState, plan: FuturePlan, *, effects: list[dict[str, Any]],
                  plot_transitions: list[dict[str, Any]], triggered_events: list[str],
                  world_events: list[str]
                  ) -> tuple[FuturePlan, bool, str, list[dict[str, Any]], list[dict[str, Any]]]:
    """只在“足以影响未来”的关键变化发生时重规划未来；happened 必须保持不变。"""

    reasons: list[str] = []
    if plot_transitions:
        reasons.append("plot_transition:" + "、".join(
            f"{item['plot']}->{item['to']}" for item in plot_transitions))
    impactful = sorted({str(item.get("op", "")) for item in effects
                        if str(item.get("op", "")) in REPLAN_EFFECT_OPS
                        and item.get("op") in ("change_relationship", "add_knowledge",
                                               "add_identity", "grant_ability", "create_promise",
                                               "update_faction", "update_plot")})
    if impactful:
        reasons.append("state_change:" + "、".join(impactful))
    if triggered_events:
        reasons.append("event:" + "、".join(sorted(set(triggered_events))))
    if world_events:
        reasons.append("world_event:" + "、".join(sorted(set(world_events))))
    old_summary = _future_plan_payload(plan)
    if not reasons or not plan.stages:
        return plan, False, "", old_summary, old_summary
    package = build_route(state, plan=plan)
    updated, replanned = replan_long_line(plan, state, package,
                                          changed_stage="", note="；".join(reasons))
    new_summary = _future_plan_payload(updated)
    changed = old_summary != new_summary or replanned.happened != package.happened
    return updated, changed, "；".join(reasons), old_summary, new_summary


def _run_world(state: StoryState, pack: ContentPack, catalog: EventCardCatalog, *,
               actor: str, limit_events: int, diagnostics: list[dict[str, Any]]
) -> tuple[StoryState, list[dict[str, Any]], list[str]]:
    """世界推进：NPC / 势力自主行动 + 世界事件；全部复用既有实现。"""

    world_rows: list[dict[str, Any]] = []
    if not pack.autonomous_rules:
        diagnostics.append({"code": "WORLD_RULES_EMPTY"})
    else:
        from .world import AutonomousRule

        rules = [AutonomousRule.model_validate(item) for item in pack.autonomous_rules]
        ticked = run_world_tick(state, pack, rules, actor_id="world")
        state = ticked.state
        world_rows.extend({
            "order": record.order,
            "actor": record.entity,
            "action": record.target,
            "label": str((record.data or {}).get("label", "")),
            "source": record.source,
        } for record in ticked.records if record.op == "world_action")
    fired = run_world_events(state, catalog, actor="world", limit=limit_events,
                             min_tick_gap=int(getattr(pack, "world_event_gap", 0) or 0))
    state = fired.state
    if fired.skipped:
        diagnostics.append({"code": "WORLD_EVENTS_SKIPPED",
                            "count": len(fired.skipped),
                            "sample": [item.get("code", "") for item in fired.skipped[:3]]})
    return state, world_rows, list(fired.fired)


def _fire_requested(state: StoryState, catalog: EventCardCatalog, event_ids: list[str], *,
                    actor: str, diagnostics: list[dict[str, Any]]
) -> tuple[StoryState, list[str]]:
    """触发被明确请求的已注册事件（例如导演推荐的 chosen）；不请求就不触发。"""

    engine = EventTriggerEngine(catalog)
    fired: list[str] = []
    for event_id in event_ids:
        if not event_id:
            continue
        if all(card.event_id != event_id for card in catalog.cards):
            diagnostics.append({"code": "EVENT_NOT_REGISTERED", "event": event_id})
            continue
        outcome = engine.fire(state, event_id, actor=actor)
        if not outcome.ok:
            diagnostics.append({"code": outcome.code or "EVENT_NOT_FIRED",
                                "event": event_id, "message": outcome.message})
            continue
        state = outcome.state
        fired.append(event_id)
        for followup in outcome.activated_followups:
            follow = engine.fire(state, followup, actor=actor)
            if follow.ok:
                state = follow.state
                fired.append(followup)
    return state, fired


def _director_view(state: StoryState, catalog: EventCardCatalog, pack: ContentPack, *,
                   actor: str, last_choice: str, limit: int) -> DirectorDecision:
    weights = weights_from_config(None)
    return decide(catalog, state, weights=weights, actor=actor, last_choice=last_choice, limit=limit)


def _writer_view(state: StoryState, pack: ContentPack, *,
                 required_results: list[str], generator: Callable[[WriterPackage], Any] | None,
                 actor: str) -> tuple[WriterResult, WriterPackage]:
    package = build_writer_package(state, None, required_results=required_results or None,
                                  style=dict(pack.text.scene_texts) if pack.text.scene_texts else None)
    result = render_scene(state, package, generator, catalog=_action_catalog(pack),
                          event_catalog=event_catalog(pack), actor=actor)
    return result, package


def advance_story(
    state: StoryState,
    pack: ContentPack,
    *,
    action_id: str = "",
    actor: str = "",
    expected_revision: int | None = None,
    world_tick: bool = True,
    fire_events: list[str] | None = None,
    limit_events: int = 3,
    director_limit: int = 3,
    writer_generator: Callable[[WriterPackage], Any] | None = None,
    required_results: list[str] | None = None,
    future_plan: FuturePlan | None = None,
    diagnostics: list[dict[str, Any]] | None = None,
) -> AdvanceResult:
    """推进一轮故事。state 视为只读；新的 StoryState 只出现在返回值里，由调用方持久化。"""

    notes: list[dict[str, Any]] = list(diagnostics or [])
    catalog = event_catalog(pack)
    current_revision = story_revision(state)
    working = state

    if expected_revision is not None and expected_revision != current_revision:
        return AdvanceResult(
            ok=False, blocked=BLOCKED_STALE_REVISION, revision=current_revision,
            tick=working.timeline.tick, state=working,
            message=f"当前进度是 {current_revision}，请求基于 {expected_revision}；请重新载入后重试。",
            next_candidates=_candidate_rows(candidates_for(working, pack, actor=actor)),
            current_state_summary=_summarize(working), diagnostics=notes)

    rows = candidates_for(working, pack, actor=actor)
    available = {item.action_id for item in rows if item.available}

    if action_id:
        if all(action.id != action_id for action in pack.actions):
            return AdvanceResult(
                ok=False, blocked=BLOCKED_UNKNOWN_ACTION, revision=current_revision,
                tick=working.timeline.tick, executed_action=action_id, state=working,
                message="内容包里没有这个行动。",
                next_candidates=_candidate_rows(rows),
                current_state_summary=_summarize(working), diagnostics=notes)
        if action_id not in available:
            blocked = next((item for item in rows if item.action_id == action_id), None)
            return AdvanceResult(
                ok=False, blocked=BLOCKED_ACTION_NOT_AVAILABLE, revision=current_revision,
                tick=working.timeline.tick, executed_action=action_id, state=working,
                code=blocked.code if blocked else "",
                message=(blocked.reason if blocked else "") or "当前状态不能执行这个行动。",
                next_candidates=_candidate_rows(rows),
                current_state_summary=_summarize(working), diagnostics=notes)
        resolved = ActionResolver().resolve(_action_catalog(pack).by_id(action_id), working, actor=actor)
        if not resolved.ok:
            return AdvanceResult(
                ok=False, blocked=resolved.code or "ACTION_BLOCKED", outcome=resolved.outcome,
                revision=current_revision, tick=working.timeline.tick,
                executed_action=action_id, message=resolved.message, state=working,
                next_candidates=_candidate_rows(rows),
                current_state_summary=_summarize(working), diagnostics=notes)
        working = resolved.state
        record = EffectRecord(id=f"runtime_action:{action_id}:{len(working.effect_log) + 1}",
                              op="runtime_action", entity=resolved.action_id,
                              target=resolved.action_id, source=f"runtime:{action_id}",
                              order=len(working.effect_log) + 1,
                              data={"outcome": resolved.outcome})
        working.effect_log.append(record)
        result_action, outcome_name, message = action_id, resolved.outcome, resolved.message
        effects = [item.model_dump(mode="json") for item in resolved.records]
    else:
        if not available:
            reasons = [{"action": item.action_id, "code": item.code, "reason": item.reason}
                       for item in rows if not item.available][:5]
            return AdvanceResult(
                ok=False, blocked=BLOCKED_NO_ACTIONS, revision=current_revision,
                tick=working.timeline.tick, state=working,
                message="当前状态下没有可用行动；可以用 runtime tick 推进世界后再看。",
                next_candidates=_candidate_rows(rows), current_state_summary=_summarize(working),
                diagnostics=notes + [{"code": "NO_AVAILABLE_ACTIONS", "reasons": reasons}])
        return AdvanceResult(
            ok=False, blocked="action_required", revision=current_revision,
            tick=working.timeline.tick, state=working,
            message="请从候选行动中选择一个 action_id。",
            next_candidates=_candidate_rows(rows), current_state_summary=_summarize(working),
            diagnostics=notes)

    working, settled, delayed_failures = _settle(working, actor=actor)
    world_actions: list[dict[str, Any]] = []
    world_events: list[str] = []
    if world_tick:
        working = _advance_time(working, ticks=1, actor=actor)
        working, world_actions, world_events = _run_world(
            working, pack, catalog, actor=actor, limit_events=limit_events, diagnostics=notes)
    working, triggered = _fire_requested(working, catalog, list(fire_events or []),
                                         actor=actor, diagnostics=notes)

    # 支线：世界状态满足触发条件时自动激活（复用既有 sync_plots）。
    plots_before = _plot_rows(working)
    working, plot_transitions = _sync_plots(working, before=_plot_rows(state),
                                             diagnostics=notes)
    del plots_before
    plan_in = future_plan or FuturePlan()
    plan_out, plan_changed, plan_reason, old_plan, new_plan = _maybe_replan(
        working, plan_in, effects=effects, plot_transitions=plot_transitions,
        triggered_events=triggered, world_events=world_events)

    last_choice = action_id
    decision = _director_view(working, catalog, pack, actor=actor, last_choice=last_choice,
                             limit=director_limit)
    writer_result, package = _writer_view(working, pack, required_results=list(required_results or []),
                                          generator=writer_generator, actor=actor)

    next_rows = candidates_for(working, pack, actor=actor)
    available_next = [item.action_id for item in next_rows if item.available]
    terminal = not available_next
    if terminal:
        notes.append({"code": "NO_AVAILABLE_ACTIONS"})

    return AdvanceResult(
        ok=True, blocked="", terminal=terminal,
        revision=story_revision(working), tick=working.timeline.tick,
        executed_action=result_action, outcome=outcome_name, message=message,
        effects=effects, settled_delayed=settled, delayed_failures=delayed_failures,
        world_actions=world_actions, world_events=world_events, triggered_events=triggered,
        director_decision=decision.as_dict(),
        writer_result=writer_result.as_dict(),
        current_state_summary=_summarize(working),
        next_candidates=_candidate_rows(next_rows), available_actions=available_next,
        diagnostics=notes, plot_transitions=plot_transitions,
        future_plan_changed=plan_changed, replan_reason=plan_reason,
        old_future_summary=old_plan, new_future_summary=new_plan,
        future_plan=new_plan, state=working)


def runtime_tick(
    state: StoryState,
    pack: ContentPack,
    *,
    actor: str = "",
    expected_revision: int | None = None,
    limit_events: int = 3,
    future_plan: FuturePlan | None = None,
    diagnostics: list[dict[str, Any]] | None = None,
) -> AdvanceResult:
    """主角不行动时的明确推进：世界 tick → 自主行动 → 世界事件 → 延迟结算 → 重新计算候选。

    这不产生任何“凭空兜底选项”：世界推进只由内容包声明的规则决定。
    """

    notes: list[dict[str, Any]] = list(diagnostics or [])
    catalog = event_catalog(pack)
    current_revision = story_revision(state)
    if expected_revision is not None and expected_revision != current_revision:
        return AdvanceResult(
            ok=False, blocked=BLOCKED_STALE_REVISION, revision=current_revision,
            tick=state.timeline.tick, state=state,
            message=f"当前进度是 {current_revision}，请求基于 {expected_revision}；请重新载入后重试。",
            next_candidates=_candidate_rows(candidates_for(state, pack, actor=actor)),
            current_state_summary=_summarize(state), diagnostics=notes)
    working = state
    working = _advance_time(working, ticks=1, actor=actor)
    working, world_actions, world_events = _run_world(
        working, pack, catalog, actor=actor, limit_events=limit_events, diagnostics=notes)
    working, settled, delayed_failures = _settle(working, actor=actor)
    working, plot_transitions = _sync_plots(working, before=_plot_rows(state), diagnostics=notes)
    plan_in = future_plan or FuturePlan()
    plan_out, plan_changed, plan_reason, old_plan, new_plan = _maybe_replan(
        working, plan_in, effects=[], plot_transitions=plot_transitions,
        triggered_events=[], world_events=world_events)
    del plan_out
    next_rows = candidates_for(working, pack, actor=actor)
    available_next = [item.action_id for item in next_rows if item.available]
    if not available_next:
        notes.append({"code": "NO_AVAILABLE_ACTIONS"})
    return AdvanceResult(
        ok=True, blocked="", terminal=not available_next,
        revision=story_revision(working), tick=working.timeline.tick,
        executed_action="", outcome="world_tick", message="世界推进一格。",
        settled_delayed=settled, delayed_failures=delayed_failures,
        world_actions=world_actions, world_events=world_events,
        current_state_summary=_summarize(working),
        next_candidates=_candidate_rows(next_rows), available_actions=available_next,
        diagnostics=notes, plot_transitions=plot_transitions,
        future_plan_changed=plan_changed, replan_reason=plan_reason,
        old_future_summary=old_plan, new_future_summary=new_plan,
        future_plan=new_plan, state=working)


def runtime_candidates(state: StoryState, pack: ContentPack, *, actor: str = "",
                       action_ids: list[str] | None = None) -> dict[str, Any]:
    """只读：当前运行态摘要 + 合法候选行动。"""

    rows = candidates_for(state, pack, actor=actor, action_ids=action_ids)
    return {
        "revision": story_revision(state),
        "tick": state.timeline.tick,
        "summary": _summarize(state),
        "candidates": _candidate_rows(rows),
        "available": [item.action_id for item in rows if item.available],
        "blocked": [] if any(item.available for item in rows) else [BLOCKED_NO_ACTIONS],
    }
