"""V2-H：StoryState → 路线 → 大纲 → 卷 / 篇章 / 章节。"""

from __future__ import annotations

from pathlib import Path

import pytest

from novelforge.story_engine import (
    EffectSpec,
    FuturePlan,
    JourneyDesign,
    JourneyRuntime,
    PlotTrack,
    StageGoal,
    StoryState,
    apply_effects,
    build_route,
    initial_journey_state,
    load_content_pack,
    outline_items_from_route,
    replan_long_line,
    set_plot_status,
    split_long_line,
    upsert_plot,
    verify_outline_sources,
    advance_plot,
    record_choice,
)


ROOT = Path(__file__).resolve().parents[1]
PACK = load_content_pack(ROOT / "novel" / "config" / "story_engine" / "journey_v1.json")
DESIGN = JourneyDesign(selected_options={"opening_pattern": "opening_debt"},
                       section_options=["world_cultivation_realms"])


def long_state(steps: int = 20) -> StoryState:
    runtime = JourneyRuntime(PACK)
    state = initial_journey_state(PACK, novel_id="novel_h")
    state = upsert_plot(state, PlotTrack(id="ledger", title="账册疑云", status="active", priority=3,
                                         characters=["protagonist"], source="scene:start"))
    plan = ["journey_clue", "journey_wait", "journey_leave", "followup_continue_trace",
            "followup_honor_partner", "followup_seek_receipt", "followup_verify_order"]
    for index in range(steps):
        choice = plan[index % len(plan)]
        result = runtime.choose(state, DESIGN, choice)
        state = result.state if result.ok else state
        # 引擎确认过的结果继续写入路线（模拟长线推进，不依赖场景是否仍有可选行动）。
        state = record_choice(state, choice, result=f"第 {index + 1} 次确认结果",
                              rules=PACK.recompute, actor="protagonist")
    return state


def test_route_only_contains_happened_facts() -> None:
    state = long_state(9)
    plan = FuturePlan(stages=[StageGoal(id="stage_1", title="阶段一", goal="查清来源")])
    package = build_route(state, plan=plan, suggested_events=["sect_inquiry"])
    assert package.happened and all(item.kind == "happened" for item in package.happened)
    assert all(item.source for item in package.happened)
    assert [item.id for item in package.planned] == ["planned_stage_1"]
    assert [item.result for item in package.suggested] == ["sect_inquiry"]
    # 计划与建议不会混进 happened
    assert all(item.origin in ("action", "event", "world_event", "effect", "plot")
               for item in package.happened)
    assert all("planned" not in item.id and "suggested" not in item.id for item in package.happened)


def test_long_line_splits_into_volumes_arcs_chapters_with_sources() -> None:
    state = long_state(20)
    package = build_route(state)
    plan = split_long_line(package, chapters_per_arc=4, arcs_per_volume=2)
    assert len(plan.chapters) >= 20
    assert len(plan.arcs) >= 5
    assert len(plan.volumes) >= 3
    chapter_sources = {item["source"] for item in plan.chapters}
    happened_ids = {item.id for item in package.happened}
    assert chapter_sources <= happened_ids
    assert all(item["sources"] for item in plan.volumes)
    items = outline_items_from_route(package)
    trace = verify_outline_sources(items, package)
    assert trace.unsourced == []
    assert len(trace.verified) == len(items)


def test_replan_only_touches_future_and_keeps_history() -> None:
    state = long_state(12)
    package = build_route(state)
    plan = FuturePlan(stages=[StageGoal(id="stage_1", title="阶段一", goal="查清来源"),
                              StageGoal(id="stage_2", title="阶段二", goal="公开证据")])
    updated, replanned = replan_long_line(plan, state, package, changed_stage="stage_1",
                                          note="玩家选择先救人")
    assert updated.revision == 1 and updated.stages[0].status == "changed"
    assert replanned.happened == package.happened  # 历史不变
    assert len(replanned.planned) == 2
    # 没有来源的大纲条目会被标记为 unresolved，而不是伪装成事实。
    broken_items = outline_items_from_route(package)
    broken_items.append({"item_id": "invented_001", "must_keep": ["来源：作者想象"]})
    trace = verify_outline_sources(broken_items, package)
    assert trace.unsourced and trace.unsourced[0]["mark"] == "unresolved"


def test_plot_completion_becomes_history_and_keeps_source() -> None:
    state = long_state(6)
    for _ in range(3):
        state = advance_plot(state, "ledger")
    state = set_plot_status(state, "ledger", "completed", note="账册公开")
    package = build_route(state)
    plots = [item for item in package.happened if item.origin == "plot"]
    assert plots and plots[0].source and plots[0].result.endswith("completed")
    assert any(record.origin == "action" for record in package.happened)


def test_narrative_layer_has_no_genre_branching() -> None:
    source = (ROOT / "src" / "novelforge" / "story_engine" / "narrative.py").read_text(encoding="utf-8")
    for pattern in ("if genre ==", "if world_type ==", "if novel_id ==", "修仙", "科幻"):
        assert pattern not in source, pattern
