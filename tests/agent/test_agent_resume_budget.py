"""V4-11 §43–§46、§55–§56、§84–§87：上限 / 取消 / resume / revision drift。"""

from __future__ import annotations

from pathlib import Path

from agent_support import agent_for, goal_for, seed
import pytest

from novelforge.agent import AgentCancelled, AgentPolicy


def test_max_steps_stops_execution(tmp_path: Path) -> None:
    stack = seed(tmp_path)
    agent = agent_for(stack)
    session_id = agent.plan(goal_for(stack))["session_id"]
    result = agent.start(session_id, policy=AgentPolicy(max_steps=2),
                         max_batch_steps=20)
    assert result["status"] == "paused"
    assert result["errors"][0]["code"] == "AGENT_MAX_STEPS_REACHED"
    assert len(result["completed_steps"]) == 2
    assert result["pending_steps"]
    checkpoint = agent.status(session_id)["checkpoint"]
    assert checkpoint["next_step_sequence"] == 3


def test_cancel_uses_honest_semantics(tmp_path: Path) -> None:
    stack = seed(tmp_path)
    agent = agent_for(stack)
    session_id = agent.plan(goal_for(stack))["session_id"]
    first = agent.start(session_id, max_batch_steps=1)
    assert len(first["completed_steps"]) == 1
    cancelled = agent.cancel(session_id, reason="作者中止")
    assert cancelled["status"] == "cancelled"
    assert "当前步骤结束后停止" in cancelled["semantics"]
    assert "已物理中止" not in cancelled["semantics"]
    # 取消是终态：resume 不会悄悄复活（必须重新 plan）
    with pytest.raises(AgentCancelled):
        agent.resume(session_id)


def test_resume_from_checkpoint_in_new_service_instance(tmp_path: Path) -> None:
    stack = seed(tmp_path)
    agent = agent_for(stack)
    session_id = agent.plan(goal_for(stack))["session_id"]
    first = agent.start(session_id, max_batch_steps=2)
    assert first["status"] == "paused"
    done_first = len(first["completed_steps"])
    assert agent.status(session_id)["checkpoint"]["next_step_sequence"] == 3

    fresh = agent_for(stack)                      # 模拟进程重启
    resumed = fresh.resume(session_id, max_batch_steps=20)
    assert resumed["status"] == "completed", (resumed["stop_reason"], resumed["errors"])
    assert len(resumed["completed_steps"]) > done_first


def test_resume_with_revision_drift_is_refused(tmp_path: Path) -> None:
    stack = seed(tmp_path)
    agent = agent_for(stack)
    session_id = agent.plan(goal_for(stack))["session_id"]
    agent.start(session_id, max_batch_steps=2)
    checkpoint = agent.status(session_id)["checkpoint"]
    target = next(iter(checkpoint["revision_refs"]), "")
    assert target, checkpoint

    services = stack["services"]
    revision = services.editor.get_node(target)["node"]["revision"]
    services.editor.patch(target, {"hook": "作者手动加的钩子"},
                          expected_revision=revision, reason="author edit")

    resumed = agent_for(stack).resume(session_id, max_batch_steps=20)
    assert resumed["status"] == "paused"
    assert resumed["errors"][0]["code"] == "AGENT_REVISION_CONFLICT"
    drift = resumed["details"]["drift"][target]
    assert drift["expected"] != drift["current"]


def test_budget_exhaustion_does_not_exceed_policy(tmp_path: Path) -> None:
    stack = seed(tmp_path)
    agent = agent_for(stack)
    session_id = agent.plan(goal_for(stack))["session_id"]
    result = agent.start(session_id,
                         policy=AgentPolicy(token_budget=1, cost_budget=0.000001),
                         max_batch_steps=20)
    assert result["status"] in ("paused", "completed")
    if result["status"] == "paused":
        assert result["errors"][0]["code"] == "AGENT_BUDGET_EXHAUSTED"
    calls_after = stack["agent_provider"].calls
    agent.resume(session_id, max_batch_steps=5)
    assert stack["agent_provider"].calls >= calls_after
