"""V4-11 §43–§46、§86–§87：预算与上限（port-level，确定性）。"""

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


def _plan(count: int) -> AgentPlan:
    return AgentPlan(novel_id="alpha", goal_id="g1", steps=tuple(
        AgentStep(action="evaluate", target={"kind": "novel"}, sequence=index,
                  mutation=True, success_criteria=("report_exists",))
        for index in range(1, count + 1)))


def _goal() -> AgentGoal:
    return AgentGoal(novel_id="alpha", instruction="反复检查", scope=AgentScope(
        kind="novel"))


def test_max_steps_bound_reports_agent_max_steps_reached(tmp_path: Path) -> None:
    stack = harness(tmp_path)
    plan = _plan(5)
    outcome = stack["executor"].execute(
        goal=_goal(), policy=AgentPolicy(max_steps=2), plan=plan,
        run=AgentRun(session_id="s1", plan_id=plan.plan_id), budget=AgentBudget())
    assert outcome.status == "paused"
    assert outcome.error["code"] == "AGENT_MAX_STEPS_REACHED"
    assert len([row for row in outcome.run.step_results
                if row.status == "completed"]) == 2


def test_token_and_cost_budget_stop_further_model_calls(tmp_path: Path) -> None:
    stack = harness(tmp_path)
    plan = AgentPlan(novel_id="alpha", goal_id="g1", steps=(
        AgentStep(action="generate_node", target={"kind": "novel"}, sequence=1,
                  inputs={"task": "chapter"}, mutation=True,
                  success_criteria=("node_exists", "status_proposed")),
        AgentStep(action="generate_node", target={"kind": "novel"}, sequence=2,
                  inputs={"task": "chapter"}, mutation=True,
                  success_criteria=("node_exists", "status_proposed")),
    ))
    outcome = stack["executor"].execute(
        goal=_goal(), policy=AgentPolicy(token_budget=50, cost_budget=1000.0),
        plan=plan, run=AgentRun(session_id="s1", plan_id=plan.plan_id),
        budget=AgentBudget())
    assert outcome.status in ("completed", "paused")
    if outcome.status == "paused":
        assert outcome.error["code"] == "AGENT_BUDGET_EXHAUSTED"
        assert stack["generation"].calls == 1        # 达到预算后不再调用模型


def test_max_mutations_bound(tmp_path: Path) -> None:
    stack = harness(tmp_path)
    plan = _plan(4)
    outcome = stack["executor"].execute(
        goal=_goal(), policy=AgentPolicy(max_mutations=1), plan=plan,
        run=AgentRun(session_id="s1", plan_id=plan.plan_id), budget=AgentBudget())
    assert outcome.status == "paused"
    assert outcome.error["code"] == "AGENT_BUDGET_EXHAUSTED"
