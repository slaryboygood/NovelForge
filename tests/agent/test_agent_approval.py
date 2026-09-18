"""V4-11 §16、§48–§51、§81：protected action 的审批、过期审批、拒绝。"""

from __future__ import annotations

from pathlib import Path

import pytest

from agent_support import agent_for, goal_for, seed
from novelforge.agent import AgentApprovalStale, AgentScope


def test_protected_action_stops_for_approval(tmp_path: Path) -> None:
    stack = seed(tmp_path, accept=("story_arc",))
    agent = agent_for(stack)
    goal = goal_for(stack, instruction="重写已接受的 Story Arc 高潮",
                    scope=AgentScope(kind="novel"))
    preview = agent.plan(goal)
    protected = [row for row in preview["preview"] if row["requires_approval"]]
    assert protected, preview["preview"]

    started = agent.start(preview["session_id"], max_batch_steps=20)
    assert started["status"] == "awaiting_approval"
    assert started["errors"] and started["errors"][0]["code"] == "AGENT_APPROVAL_REQUIRED"
    assert list(started["changed_nodes"]) == []      # 0 mutation
    # 高层 accepted 节点 revision 未变
    story_arc = stack["services"].editor.get_node("story_arc")["node"]
    assert story_arc["status"] == "accepted"
    accepted_revision = story_arc["revision"]

    status = agent.status(preview["session_id"])
    pending = status["pending_approvals"]
    assert pending and pending[0]["step_id"] in preview["plan"]["required_approvals"]
    assert pending[0]["revision_refs"] == {"story_arc": accepted_revision}

    approved = agent.approve(preview["session_id"], pending[0]["approval_id"])
    assert approved["status"] in ("completed", "paused", "failed")
    decisions = agent.status(preview["session_id"])["session"]["decisions"]
    assert decisions and decisions[-1]["decision"] == "approved"


def test_stale_approval_is_rejected(tmp_path: Path) -> None:
    stack = seed(tmp_path, accept=("story_arc",))
    agent = agent_for(stack)
    goal = goal_for(stack, instruction="重写已接受的 Story Arc 高潮",
                    scope=AgentScope(kind="novel"))
    session_id = agent.plan(goal)["session_id"]
    agent.start(session_id, max_batch_steps=20)
    approval_id = agent.status(session_id)["pending_approvals"][0]["approval_id"]

    # 作者在批准之前自己改了 story_arc → approval 绑定的 revision 过期
    services = stack["services"]
    current = stack["services"].editor.get_node("story_arc")["node"]["revision"]
    services.editor.patch("story_arc", {"resolution": "作者手动改写的结局"},
                          expected_revision=current, reason="author edit")
    with pytest.raises(AgentApprovalStale):
        agent.approve(session_id, approval_id)
    session = agent.status(session_id)["session"]
    assert session["error_code"] == "AGENT_APPROVAL_STALE"
    assert session["status"] == "needs_human_review"


def test_rejected_approval_pauses_without_mutation(tmp_path: Path) -> None:
    stack = seed(tmp_path, accept=("story_arc",))
    agent = agent_for(stack)
    goal = goal_for(stack, instruction="重写已接受的 Story Arc 高潮",
                    scope=AgentScope(kind="novel"))
    session_id = agent.plan(goal)["session_id"]
    agent.start(session_id, max_batch_steps=20)
    approval_id = agent.status(session_id)["pending_approvals"][0]["approval_id"]
    result = agent.reject(session_id, approval_id, reason="先不要改")
    assert result["status"] == "paused"
    assert list(result["changed_nodes"]) == []
    story_arc = stack["services"].editor.get_node("story_arc")["node"]
    assert story_arc["status"] == "accepted"


def test_accept_requires_policy_and_approval(tmp_path: Path) -> None:
    """§17、§71：即使作者要求接受，Agent 也只能发起审批（默认不自动接受）。"""

    stack = seed(tmp_path)
    agent = agent_for(stack)
    goal = goal_for(stack, instruction="扩展章节并接受结果")
    preview = agent.plan(goal)
    accept_steps = [row for row in preview["preview"]
                    if row["action"] == "accept_revision"]
    assert accept_steps and all(row["requires_approval"] for row in accept_steps)
    result = agent.start(preview["session_id"], max_batch_steps=20)
    assert result["status"] in ("awaiting_approval", "paused", "completed")
    if result["status"] != "completed":
        assert result["errors"][0]["code"] in ("AGENT_APPROVAL_REQUIRED",
                                              "AGENT_MAX_STEPS_REACHED")
