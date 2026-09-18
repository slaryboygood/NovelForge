"""V4-11 §42、§52、§71、§90：needs_human_review 与交付保护。"""

from __future__ import annotations

from pathlib import Path

from port_harness import harness
from novelforge.agent import (
    AgentBudget,
    AgentGoal,
    AgentPlan,
    AgentPolicy,
    AgentRun,
    AgentScope,
    AgentStep,
)


def _plan(steps: list[AgentStep]) -> AgentPlan:
    return AgentPlan(novel_id="alpha", goal_id="g1", steps=tuple(steps))


def test_repair_needs_human_review_stops_with_stable_code(tmp_path: Path) -> None:
    stack = harness(tmp_path)
    stack["quality"].needs_human = True
    plan = _plan([
        AgentStep(action="evaluate", target={"kind": "novel"}, sequence=1,
                  mutation=True, success_criteria=("report_exists",)),
        AgentStep(action="plan_repair", target={"kind": "novel"}, sequence=2,
                  inputs={"issue_ids": ["QI_1"]}, success_criteria=("plan_exists",)),
        AgentStep(action="repair", target={"kind": "issues"}, sequence=3,
                  inputs={"issue_ids": ["QI_1"]}, mutation=True,
                  success_criteria=("verification_status",)),
    ])
    goal = AgentGoal(novel_id="alpha", instruction="修复未回收的伏笔",
                     scope=AgentScope(kind="novel"))
    outcome = stack["executor"].execute(
        goal=goal, policy=AgentPolicy(), plan=plan,
        run=AgentRun(session_id="s1", plan_id=plan.plan_id), budget=AgentBudget())
    assert outcome.status == "needs_human_review"
    assert outcome.error["code"] == "AGENT_NEEDS_HUMAN_REVIEW"
    assert outcome.needs_human_review is True
    # 只调用既有 Repair Loop，不自动创建剧情性 payoff，也不交付
    assert stack["quality"].repair_calls == 1
    assert stack["delivery"].deliver_calls == 0


def test_delivery_requires_policy_and_approval(tmp_path: Path) -> None:
    stack = harness(tmp_path)
    stack["quality"].status = "passed"
    plan = _plan([AgentStep(action="deliver", target={"kind": "novel"}, sequence=1,
                           inputs={"formats": ["json"]}, mutation=True,
                           requires_approval=True,
                           success_criteria=("manifest_exists",))])
    goal = AgentGoal(novel_id="alpha", instruction="交付", scope=AgentScope(kind="novel"))
    # 未批准 → 停在 awaiting_approval，0 mutation
    blocked = stack["executor"].execute(
        goal=goal, policy=AgentPolicy(allow_delivery=True), plan=plan,
        run=AgentRun(session_id="s1", plan_id=plan.plan_id), budget=AgentBudget())
    assert blocked.status == "awaiting_approval"
    assert stack["delivery"].deliver_calls == 0
    # 已批准 + policy 允许 → 真的交付，并且 manifest 存在
    step_id = plan.steps[0].step_id
    done = stack["executor"].execute(
        goal=goal, policy=AgentPolicy(allow_delivery=True), plan=plan,
        run=AgentRun(session_id="s1", plan_id=plan.plan_id), budget=AgentBudget(),
        approved_steps=(step_id,))
    assert done.status == "completed"
    assert stack["delivery"].deliver_calls == 1
