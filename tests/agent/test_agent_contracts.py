"""V4-11 §11–§23、§72：Agent 契约、动作白名单与错误码。"""

from __future__ import annotations

import pytest

from novelforge.agent import (
    AGENT_SCHEMA_VERSION,
    AGENT_STATUSES,
    AGENT_TRANSITIONS,
    FORBIDDEN_ACTIONS,
    PROTECTED_ACTIONS,
    SCOPE_KINDS,
    AgentApprovalRequest,
    AgentBudget,
    AgentError,
    AgentGoal,
    AgentPlan,
    AgentPlanInvalid,
    AgentPolicy,
    AgentRun,
    AgentScope,
    AgentStep,
    AgentStepResult,
    action_spec,
    allowlisted_actions,
)


def test_statuses_and_transitions_are_closed_sets() -> None:
    assert AGENT_SCHEMA_VERSION == 1
    assert AGENT_STATUSES == ("created", "planning", "awaiting_approval", "executing",
                              "verifying", "paused", "completed", "failed",
                              "cancelled", "needs_human_review")
    for status, targets in AGENT_TRANSITIONS.items():
        assert status in AGENT_STATUSES
        assert all(target in AGENT_STATUSES for target in targets)
    assert AGENT_TRANSITIONS["completed"] == ()
    assert "executing" in AGENT_TRANSITIONS["awaiting_approval"]


def test_goal_requires_explicit_novel_and_instruction() -> None:
    with pytest.raises(AgentPlanInvalid):
        AgentGoal(novel_id="", instruction="做点什么")
    with pytest.raises(AgentPlanInvalid):
        AgentGoal(novel_id="alpha", instruction="   ")
    goal = AgentGoal(novel_id="alpha", instruction="扩展第一幕")
    assert goal.goal_id and goal.request_id
    assert AgentGoal.from_dict(goal.as_dict()).instruction == "扩展第一幕"


def test_scope_must_be_explicit() -> None:
    assert set(SCOPE_KINDS) == {"novel", "structural_unit", "chapter", "scene", "nodes"}
    with pytest.raises(AgentPlanInvalid):
        AgentScope(kind="nodes")
    with pytest.raises(AgentPlanInvalid):
        AgentScope(kind="chapter")
    with pytest.raises(AgentPlanInvalid):
        AgentScope(kind="everything")
    assert AgentScope(kind="chapter", unit_id="ch_001").is_whole_novel is False
    assert AgentScope(kind="novel").is_whole_novel is True


def test_default_policy_is_conservative() -> None:
    policy = AgentPolicy()
    assert policy.allow_auto_accept is False
    assert policy.allow_delivery is False
    assert policy.max_steps == 20 and policy.max_mutations == 10
    assert set(PROTECTED_ACTIONS) <= set(policy.require_approval_for)
    assert policy.allow_generation and policy.allow_edit and policy.allow_quality
    with pytest.raises(AgentPlanInvalid):
        AgentPolicy(max_steps=0)
    assert AgentPolicy.from_dict(policy.as_dict()).max_steps == policy.max_steps


def test_action_registry_has_no_arbitrary_actions() -> None:
    actions = allowlisted_actions()
    assert "generate_node" in actions and "accept_revision" in actions
    assert "inspect_blueprint" in actions
    for forbidden in FORBIDDEN_ACTIONS:
        assert forbidden not in actions
        with pytest.raises(AgentPlanInvalid):
            action_spec(forbidden)
    with pytest.raises(AgentPlanInvalid):
        action_spec("delete_everything")
    # protected action 必须在注册表里标记
    for action in PROTECTED_ACTIONS:
        assert action_spec(action).protected is True


def test_steps_and_plans_have_stable_ids() -> None:
    first = AgentStep(action="inspect_blueprint", sequence=1)
    second = AgentStep(action="inspect_blueprint", sequence=1)
    assert first.step_id != second.step_id          # 不是 list index
    assert first.idempotency_key.startswith("agent:inspect_blueprint:")
    plan = AgentPlan(novel_id="alpha", goal_id="g1", steps=(first,))
    assert plan.plan_revision == 1
    assert plan.next_revision().plan_revision == 2
    assert AgentPlan.from_dict(plan.as_dict()).steps[0].action == \
        "inspect_blueprint"


def test_approval_request_is_revision_aware() -> None:
    request = AgentApprovalRequest(action="accept_revision",
                                   target={"kind": "node", "node_id": "ch_001"},
                                   revision_refs={"ch_001": 4})
    assert request.is_stale(revisions={"ch_001": 5}) is True
    assert request.is_stale(revisions={"ch_001": 4}) is False
    stale = AgentApprovalRequest(action="accept_revision", target={},
                                 revision_refs={},
                                 expires_if_revision_changes=False)
    assert stale.is_stale(revisions={}) is False


def test_run_and_budget_are_serializable() -> None:
    run = AgentRun(session_id="s1", plan_id="p1")
    run.step_results.append(AgentStepResult(step_id="st1", status="completed",
                                            revision_before=1, revision_after=2,
                                            changed_nodes=("ch_001",)))
    assert run.mutations == 1 and run.changed_nodes == ("ch_001",)
    payload = run.as_dict()
    assert payload["run_id"] == run.run_id and payload["mutations"] == 1
    budget = AgentBudget(steps=2, mutations=1)
    assert budget.as_dict()["steps"] == 2


def test_error_codes_are_stable() -> None:
    from novelforge.agent import (
        AgentApprovalRequired,
        AgentApprovalStale,
        AgentBudgetExhausted,
        AgentCancelled,
        AgentMaxStepsReached,
        AgentNeedsHumanReview,
        AgentPolicyDenied,
        AgentRevisionConflict,
        AgentStepFailed,
    )

    expected = {
        AgentPlanInvalid: "AGENT_PLAN_INVALID",
        AgentPolicyDenied: "AGENT_POLICY_DENIED",
        AgentStepFailed: "AGENT_STEP_FAILED",
        AgentRevisionConflict: "AGENT_REVISION_CONFLICT",
        AgentApprovalRequired: "AGENT_APPROVAL_REQUIRED",
        AgentApprovalStale: "AGENT_APPROVAL_STALE",
        AgentBudgetExhausted: "AGENT_BUDGET_EXHAUSTED",
        AgentMaxStepsReached: "AGENT_MAX_STEPS_REACHED",
        AgentCancelled: "AGENT_CANCELLED",
        AgentNeedsHumanReview: "AGENT_NEEDS_HUMAN_REVIEW",
    }
    for klass, code in expected.items():
        assert klass.code == code
        assert klass("boom", session_id="s1").as_dict()["code"] == code
        assert issubclass(klass, AgentError)


def test_public_contract_is_small() -> None:
    import novelforge.agent as agent

    exported = set(agent.__all__)
    required = {"AgentGoal", "AgentScope", "AgentPolicy", "AgentPlan", "AgentStep",
                "AgentResult", "AgentRun", "AgentSessionRecord", "AgentCheckpoint",
                "AgentApprovalRequest", "AgentApprovalDecision", "AgentError",
                "AgentExecutor", "AgentVerifier", "CheckpointStore", "AgentBudget"}
    assert required <= exported
    assert not [name for name in exported if name.startswith("_")]
    # 内部实现不进入公开契约
    assert "AgentService" not in exported          # 在 application 层
    assert "ApplicationReadPort" not in exported
