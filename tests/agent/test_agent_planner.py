"""V4-11 §24–§31、§75–§77：intent 解析、计划结构、安全校验、模型 Planner。"""

from __future__ import annotations

from typing import Any, Mapping, Sequence

import pytest

from novelforge.agent import (
    AgentContextSnapshot,
    AgentGoal,
    AgentPlan,
    AgentPlanInvalid,
    AgentPolicy,
    AgentRevisionConflict,
    AgentScope,
    AgentStep,
    HeuristicPlanner,
    ModelPlanner,
    parse_intent,
    validate_plan,
)


def _snapshot() -> AgentContextSnapshot:
    return AgentContextSnapshot(
        novel_id="alpha",
        blueprint_revisions={"premise": 1, "world": 1, "story_arc": 2, "unit_01": 1,
                             "ch_001": 3, "sc_001_01": 2, "character_01": 4},
        node_types={"premise": "premise", "world": "world", "story_arc": "story_arc",
                    "unit_01": "structural_unit", "ch_001": "chapter",
                    "sc_001_01": "scene", "character_01": "character"},
        node_status={"premise": "accepted", "world": "accepted",
                     "story_arc": "accepted", "unit_01": "accepted",
                     "ch_001": "accepted", "sc_001_01": "proposed",
                     "character_01": "accepted"},
        parent_ids={"ch_001": "unit_01", "sc_001_01": "ch_001"},
        accepted_nodes=("ch_001", "character_01", "premise", "story_arc", "unit_01",
                        "world"),
        quality_summary={"status": "passed", "issues": 0}, open_issues=(),
        delivery_readiness={"snapshots": 0}, review_state={})


def _goal(instruction: str, *, scope: AgentScope | None = None) -> AgentGoal:
    return AgentGoal(novel_id="alpha", instruction=instruction,
                     scope=scope or AgentScope(kind="structural_unit",
                                               unit_id="unit_01"))


def test_intent_parsing_is_deterministic() -> None:
    snapshot = _snapshot()
    intent = parse_intent(
        _goal("把第一幕扩展到 3 个章节，每章至少有 2 个场景，"
              "运行质量检查并修复可以自动安全修复的问题，不要自动接受"),
        snapshot)
    assert intent.target_chapters == 3
    assert intent.min_scenes_per_chapter == 2
    assert intent.run_quality is True and intent.repair is True
    assert intent.request_accept is False        # “不要自动接受”
    assert intent.delivery is False
    # 明确要求交付时才进入 delivery
    delivery = parse_intent(_goal("完成后交付 nfpack 包"), snapshot)
    assert delivery.delivery is True
    # 重写高层节点（protected）
    rewrite = parse_intent(_goal("重写已接受的 Story Arc 高潮"), snapshot)
    assert rewrite.rewrite_node_id == "story_arc"
    assert rewrite.rewrite_fields == ("climax",)


def test_heuristic_plan_is_bounded_and_ordered() -> None:
    snapshot = _snapshot()
    policy = AgentPolicy()
    goal = _goal("扩展到 3 个章节，每章至少有 2 个场景，运行质量检查并修复"
                 "可以自动安全修复的问题，不要自动接受")
    plan = HeuristicPlanner().plan(goal, snapshot, policy)
    actions = [step.action for step in plan.steps]
    assert actions[0] == "inspect_blueprint"
    chapter_steps = [s for s in plan.steps if s.action == "generate_node"
                     and s.inputs.get("task") == "chapter"]
    scene_steps = [s for s in plan.steps if s.action == "generate_node"
                   and s.inputs.get("task") == "scene"]
    assert len(chapter_steps) == 2                      # 已有 1 章 → 补 2 章
    assert len(scene_steps) == 1                        # ch_001 只有 1 场 → 补 1 场
    assert "evaluate" in actions and "repair" in actions
    assert "accept_revision" not in actions             # 默认不自动接受
    assert "deliver" not in actions
    assert plan.estimated_mutations == len([s for s in plan.steps if s.mutation])
    assert plan.snapshot_digest == snapshot.digest


def test_plan_validation_rejects_unknown_and_forbidden_actions() -> None:
    snapshot, policy, goal = _snapshot(), AgentPolicy(), _goal("扩展章节")
    with pytest.raises(AgentPlanInvalid):
        validate_plan(AgentPlan(novel_id="alpha", goal_id=goal.goal_id,
                                steps=(AgentStep(action="run_shell",
                                                 target={"kind": "novel"}),)),
                      goal=goal, policy=policy, snapshot=snapshot)
    with pytest.raises(AgentPlanInvalid):
        validate_plan(AgentPlan(novel_id="alpha", goal_id=goal.goal_id,
                                steps=(AgentStep(action="not_a_real_action",
                                                 target={"kind": "novel"}),)),
                      goal=goal, policy=policy, snapshot=snapshot)


def test_plan_validation_enforces_revision_policy_and_scope() -> None:
    snapshot, policy = _snapshot(), AgentPolicy()
    goal = _goal("修改章节")
    # 缺少 expected_revision
    with pytest.raises(AgentPlanInvalid):
        validate_plan(AgentPlan(novel_id="alpha", goal_id=goal.goal_id, steps=(
            AgentStep(action="patch_node", target={"kind": "node",
                                                   "node_id": "ch_001"},
                      inputs={"changes": {"hook": "x"}}, mutation=True),)),
            goal=goal, policy=policy, snapshot=snapshot)
    # revision 冲突
    with pytest.raises(AgentRevisionConflict):
        validate_plan(AgentPlan(novel_id="alpha", goal_id=goal.goal_id, steps=(
            AgentStep(action="patch_node", target={"kind": "node",
                                                   "node_id": "ch_001"},
                      inputs={"changes": {"hook": "x"}}, mutation=True,
                      expected_revision=1),)),
            goal=goal, policy=policy, snapshot=snapshot)
    # policy 关闭 edit
    with pytest.raises(Exception):
        HeuristicPlanner().plan(
            _goal("重写已接受的 Story Arc 高潮"), snapshot,
            AgentPolicy(allow_edit=False))
    # scope 外目标（scene scope 不能改 story_arc）
    scope_goal = _goal("重写故事弧", scope=AgentScope(kind="scene",
                                                    unit_id="sc_001_01"))
    with pytest.raises(Exception):
        validate_plan(AgentPlan(novel_id="alpha", goal_id=scope_goal.goal_id, steps=(
            AgentStep(action="rewrite_node",
                      target={"kind": "node", "node_id": "story_arc",
                              "node_type": "story_arc"},
                      inputs={"target_fields": ["climax"], "instruction": "重写"},
                      mutation=True, expected_revision=2),)),
            goal=scope_goal, policy=policy, snapshot=snapshot)


def test_plan_validation_respects_max_steps_and_mutations() -> None:
    snapshot = _snapshot()
    goal = _goal("扩展到 6 个章节")
    with pytest.raises(AgentPlanInvalid):
        HeuristicPlanner().plan(goal, snapshot, AgentPolicy(max_steps=2))


def test_protected_action_requires_approval_flag() -> None:
    snapshot = _snapshot()
    # 重写高层已接受节点属于 novel 级决定：scope=novel（Agent 仍必须请求批准）
    goal = _goal("重写已接受的 Story Arc 高潮", scope=AgentScope(kind="novel"))
    plan = HeuristicPlanner().plan(goal, snapshot, AgentPolicy())
    rewrite_steps = [step for step in plan.steps if step.action == "rewrite_node"]
    assert rewrite_steps and rewrite_steps[0].requires_approval is True
    assert rewrite_steps[0].step_id in plan.required_approvals
    assert "story_arc" in plan.protected_nodes


class _StubModel:
    """可选模型 Planner 的 stub（§25）：返回结构化候选步骤。"""

    def __init__(self, steps: Sequence[Mapping[str, Any]]) -> None:
        self.steps = list(steps)
        self.calls = 0

    def propose_plan(self, *, goal: Mapping[str, Any], snapshot: Mapping[str, Any],
                     policy: Mapping[str, Any],
                     action_catalog: Sequence[str]) -> Mapping[str, Any]:
        self.calls += 1
        return {"steps": list(self.steps), "estimated_model_calls": 1}


def test_model_planner_output_is_validated_like_deterministic_plan() -> None:
    snapshot, policy = _snapshot(), AgentPolicy()
    goal = _goal("扩展章节")
    good = _StubModel([{"action": "inspect_blueprint",
                        "target": {"kind": "novel", "novel_id": "alpha"},
                        "sequence": 1}])
    plan = ModelPlanner(good).plan(goal, snapshot, policy)
    assert plan.planner_version == "model-v1"
    assert [step.action for step in plan.steps] == ["inspect_blueprint"]

    forbidden = _StubModel([{"action": "run_python", "target": {"kind": "novel"}}])
    with pytest.raises(AgentPlanInvalid):
        ModelPlanner(forbidden).plan(goal, snapshot, policy)

    unknown_args = _StubModel([{"action": "patch_node",
                                "target": {"kind": "node", "node_id": "ch_001"},
                                "inputs": {"sql": "drop table"}}])
    with pytest.raises(AgentPlanInvalid):
        ModelPlanner(unknown_args).plan(goal, snapshot, policy)
