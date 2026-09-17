"""V2-C-03 / C-04 / C-05：支线轨道、世界联动与只重规划未来。"""

from __future__ import annotations

from novelforge.story_engine import (
    Condition,
    DelayedEffectSpec,
    EffectSpec,
    FuturePlan,
    PlotTrack,
    StageGoal,
    StoryState,
    advance_plot,
    plot_tracks,
    replan_with_plots,
    schedule_plots,
    set_plot_status,
    settle_delayed,
    story_state_from_payload,
    sync_plots,
    upsert_plot,
)


def state() -> StoryState:
    return StoryState(characters={"hero": {"id": "hero", "kind": "character"}})


def test_multiple_plots_coexist_and_do_not_pollute_each_other() -> None:
    current = upsert_plot(state(), PlotTrack(id="ledger", title="账册疑云", status="active", priority=3,
                                             characters=["hero"], locations=["gate"]))
    current = upsert_plot(current, PlotTrack(id="sister", title="寻找妹妹", status="active", priority=5))
    assert {item.id for item in plot_tracks(current)} == {"ledger", "sister"}
    advanced = advance_plot(current, "ledger")
    rows = {item.id: item for item in plot_tracks(advanced)}
    assert rows["ledger"].progress == 1 and rows["sister"].progress == 0  # 互不污染
    paused = set_plot_status(advanced, "sister", "paused", note="线索断了")
    assert {item.id: item.status for item in plot_tracks(paused)}["sister"] == "paused"
    resumed = set_plot_status(paused, "sister", "active")
    finished = set_plot_status(resumed, "ledger", "completed", note="账册公开")
    assert {item.id: item.status for item in plot_tracks(finished)}["ledger"] == "completed"
    assert StoryState.model_validate_json(finished.model_dump_json()) == finished


def test_world_changes_activate_plots_and_scheduler_prevents_pileup() -> None:
    current = upsert_plot(state(), PlotTrack(id="gate_case", title="闸口封锁", priority=1,
                                             trigger=Condition(op="flag", key="gate_locked", value=True)))
    current = upsert_plot(current, PlotTrack(id="market", title="市集重开", priority=9))
    current = upsert_plot(current, PlotTrack(id="refugee", title="流民安置", priority=8))
    current = upsert_plot(current, PlotTrack(id="rumor", title="流言", priority=2))
    for track in plot_tracks(current):
        if track.status == "inactive":
            current = set_plot_status(current, track.id, "active")
    current.flags["gate_locked"] = True
    activated = sync_plots(current)
    assert {item.id for item in plot_tracks(activated) if item.status == "active"} >= {
        "market", "refugee", "rumor"}
    scheduled, demoted = schedule_plots(activated, max_active=3)
    active = [item for item in plot_tracks(scheduled) if item.status == "active"]
    assert len(active) == 3
    assert demoted and all(item.priority <= 2 for item in plot_tracks(scheduled)
                           if item.id in demoted)


def test_future_replan_only_touches_future_and_respects_history() -> None:
    current = upsert_plot(state(), PlotTrack(id="ledger", title="账册疑云", status="active", priority=2))
    current.timeline.tick = 4
    plan = FuturePlan(stages=[StageGoal(id="stage_1", title="阶段一", goal="查清来源"),
                              StageGoal(id="stage_2", title="阶段二", goal="公开证据")])
    updated = replan_with_plots(plan, current, changed_stage="stage_1", note="玩家选择先救人")
    assert updated.revision == 1
    assert updated.stages[0].status == "changed" and updated.stages[0].note == "玩家选择先救人"
    assert updated.stages[1].status == "active" and "支线影响" in updated.stages[1].note


def test_delayed_consequences_cooperate_with_plots_and_events() -> None:
    current = upsert_plot(state(), PlotTrack(id="debt", title="欠债", status="active", priority=1))
    action_state = current.model_copy(deep=True)
    action_state.delayed_effects.append(DelayedEffectSpec(
        id="creditor_call", source="borrow",
        trigger=Condition(op="flag", key="debt_due", value=True),
        effects=[EffectSpec(id="plot_step", op="set_flag", key="creditor_arrived", value=True)]).model_dump(mode="json"))
    pending = settle_delayed(action_state, actor="hero")
    assert pending.pending == ["creditor_call"]
    ready = action_state.model_copy(deep=True)
    ready.flags["debt_due"] = True
    settled = settle_delayed(ready, actor="hero")
    assert settled.settled == ["creditor_call"]
    assert settled.state.flags["creditor_arrived"] is True
    assert {item.id for item in plot_tracks(settled.state)} == {"debt"}  # 支线不被延迟后果破坏


def test_v4_payload_upgrades_to_v5_with_empty_plots() -> None:
    legacy = StoryState(schema_version=4)
    upgraded = story_state_from_payload(legacy.model_dump(mode="json"))
    assert upgraded.schema_version >= 5 and upgraded.plots == {}
