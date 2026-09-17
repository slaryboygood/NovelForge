"""T14：实际路线 → 大纲、未来计划可调整、角色弧不强制。"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from novelforge.story_engine import (
    CharacterArc,
    FuturePlan,
    HistoryImmutableError,
    JourneyDesign,
    JourneyRuntime,
    StageGoal,
    apply_arc_outcome,
    arc_summary,
    assert_history_immutable,
    initial_journey_state,
    load_content_pack,
    replan,
    route_facts,
)
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PACK = load_content_pack(ROOT / "novel" / "config" / "story_engine" / "journey_v1.json")
DESIGN = JourneyDesign(selected_options={"opening_pattern": "opening_debt"},
                       section_options=["world_cultivation_realms"])


def advanced_state():
    runtime = JourneyRuntime(PACK)
    state = initial_journey_state(PACK, novel_id="novel_a")
    for choice in ["clue", "wait", "leave"]:
        result = runtime.choose(state, DESIGN, choice)
        assert result.ok
        state = result.state
    return state


def test_facts_come_only_from_actual_route_and_stay_immutable() -> None:
    state = advanced_state()
    facts = route_facts(state)
    assert [item.action_id for item in facts] == ["journey_clue", "journey_wait", "journey_leave"]
    assert all(item.result for item in facts)
    assert_history_immutable(state, state.model_copy(deep=True))
    tampered = state.model_copy(deep=True)
    index = next(i for i, record in enumerate(tampered.effect_log) if record.op == "choice")
    tampered.effect_log[index] = tampered.effect_log[index].model_copy(
        update={"data": {"result": "改写过的结果"}})
    with pytest.raises(HistoryImmutableError):
        assert_history_immutable(state, tampered)
    # 未来规划不会写进事实来源。
    plan = FuturePlan(stages=[StageGoal(id="stage_1", title="阶段一", goal="查清来源")])
    assert "stage_1" not in [item.action_id for item in route_facts(state)]
    with pytest.raises(ValidationError):
        FuturePlan(stages=[StageGoal(id="bad", goal="被当成事实", is_goal=False)])
    assert plan.stages[0].is_goal is True


def test_replan_keeps_history_and_marks_changed_stage() -> None:
    state = advanced_state()
    plan = FuturePlan(stages=[StageGoal(id="stage_1", title="阶段一", goal="查清来源"),
                              StageGoal(id="stage_2", title="阶段二", goal="公开证据")])
    replanned = replan(plan, state, changed_stage="stage_1", note="玩家选择了先救人")
    assert replanned.revision == 1
    assert replanned.stages[0].status == "changed" and replanned.stages[0].note == "玩家选择了先救人"
    assert replanned.stages[1].status == "active"
    assert_history_immutable(state, state)  # 重规划不改变历史


def test_character_arc_outcomes_do_not_force_progress() -> None:
    arc = CharacterArc(character_id="hero",
                       stages=[{"id": "guarded", "title": "戒备"},
                               {"id": "trusting", "title": "愿意合作"},
                               {"id": "steady", "title": "稳定互信"}])
    advanced = apply_arc_outcome(arc, "advance", note="共同经历了一次危机")
    assert advanced.current_index == 1 and arc_summary(advanced)["stage"] == "愿意合作"
    delayed = apply_arc_outcome(advanced, "delay", note="同伴选择隐瞒")
    assert delayed.current_index == 1 and delayed.outcome == "delay"
    reversed_arc = apply_arc_outcome(delayed, "reverse", note="信任被利用")
    assert reversed_arc.current_index == 0
    failed = apply_arc_outcome(advanced, "fail", note="合作破裂")
    assert failed.current_index == 1 and failed.outcome == "fail"
    assert arc_summary(failed)["is_forced"] is False
