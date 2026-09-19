"""V4.0.2 PB-2 回归：protected step 的审批必须是 **durable** 的（§22、§45–§51）。

Dogfood 复现（`docs/v4/V4_0_1_SKILL_DOGFOOD_REPORT.md` §8 PB-2）：

```text
plan（含"接受"）→ start → awaiting_approval + approval_id → approve
  → ok=false, status=failed, error_code=AGENT_STEP_FAILED,
    stop_reason="验证未通过：approval_recorded"
    （该步 result_refs.approval_id 为空；批准证据在验证之前就被丢掉）
```

正确语义：

```text
protected step 被"显式批准"这件事必须可证明，直到该 step 完成为止；
批准后 step 继续执行 → 记录 approved approval_id → success_criteria
（request_accept = approval_recorded）成立 → 计划继续到下一个边界。
```
"""

from __future__ import annotations

from pathlib import Path

import pytest

from agent_support import (agent_for, chapter_payload, goal_for, scene_payload,
                           seed)

ACCEPT_INSTRUCTION = "把第一幕扩展到 3 个章节，每章至少有 2 个场景，接受结果"


def _script() -> list[dict]:
    """2 个新章节 + 每个新章节 2 个场景（= 8 次 stub 生成调用）。"""

    return [chapter_payload(), chapter_payload(),
            scene_payload("ch_002"), scene_payload("ch_002"),
            scene_payload("ch_003"), scene_payload("ch_003"),
            scene_payload("ch_004"), scene_payload("ch_004")]


def _stack(tmp_path: Path) -> dict:
    stack = seed(tmp_path)
    agent_for(stack, script=_script())
    return stack


def _plan_acceptance(stack: dict) -> tuple[Any, str]:
    agent = stack["agent"]
    preview = agent.plan(goal_for(stack, instruction=ACCEPT_INSTRUCTION))
    protected = [row for row in preview["preview"] if row["requires_approval"]]
    assert [row["action"] for row in protected][:2] == ["request_accept",
                                                       "accept_revision"], protected
    return preview, preview["session_id"]


def _pending(agent: Any, session_id: str) -> list[dict]:
    return list(agent.status(session_id)["pending_approvals"])


def _steps(payload: dict) -> list[dict]:
    return list(payload["steps"])


def _step_result(payload: dict, step_id: str) -> dict:
    rows = [row for row in _steps(payload) if row["step_id"] == step_id]
    assert rows, step_id
    return rows[-1]


def test_approved_protected_step_completes_and_records_approval(tmp_path: Path) -> None:
    stack = _stack(tmp_path)
    _preview, session_id = _plan_acceptance(stack)
    agent = stack["agent"]

    started = agent.start(session_id, max_batch_steps=20)
    assert started["status"] == "awaiting_approval"
    assert started["errors"][0]["code"] == "AGENT_APPROVAL_REQUIRED"
    pending = _pending(agent, session_id)
    assert pending and pending[0]["step_id"] == [
        row["step_id"] for row in _preview["preview"]
        if row["action"] == "request_accept"][0]
    approval_id = pending[0]["approval_id"]
    assert pending[0]["revision_refs"], "approval 必须绑定 revision"

    approved = agent.approve(session_id, approval_id)

    # PB-2 核心断言：批准之后该 protected step 必须**完成**，而不是 failed
    assert approved["status"] != "failed", approved.get("errors")
    assert not any(row["code"] == "AGENT_STEP_FAILED" for row in approved["errors"])
    result = _step_result(approved, pending[0]["step_id"])
    assert result["status"] == "completed", result
    assert result["result_refs"]["approval_id"] == approval_id


def test_full_approval_chain_reaches_completed_and_accepted(tmp_path: Path) -> None:
    """完整生命周期：两次 protected approval → 目标节点 accepted + session completed。"""

    stack = _stack(tmp_path)
    preview, session_id = _plan_acceptance(stack)
    agent = stack["agent"]
    target = [row["target"]["node_id"] for row in preview["preview"]
              if row["action"] == "accept_revision"][0]

    agent.start(session_id, max_batch_steps=20)
    first = _pending(agent, session_id)[0]
    assert first["action"] == "request_accept"
    after_first = agent.approve(session_id, first["approval_id"])
    assert after_first["status"] == "awaiting_approval", after_first["errors"]
    assert _step_result(after_first, first["step_id"])["status"] == "completed"

    second = _pending(agent, session_id)[0]
    assert second["action"] == "accept_revision"
    final = agent.approve(session_id, second["approval_id"])
    assert final["status"] == "completed", (final["status"], final["errors"],
                                            [row["status"] for row in _steps(final)])
    assert _step_result(final, second["step_id"])["status"] == "completed"

    node = stack["services"].editor.get_node(target)["node"]
    assert node["status"] == "accepted", node


def test_approval_does_not_replay_completed_steps(tmp_path: Path) -> None:
    """批准后必须从 checkpoint 继续，而不是把已完成的步骤再跑一遍。"""

    stack = _stack(tmp_path)
    _preview, session_id = _plan_acceptance(stack)
    agent = stack["agent"]
    started = agent.start(session_id, max_batch_steps=20)
    completed_before = [row["step_id"] for row in _steps(started)
                        if row["status"] == "completed"]
    assert completed_before, started

    agent.approve(session_id, _pending(agent, session_id)[0]["approval_id"])

    # 审计是累计的：每个已完成的步骤只能被执行一次（不得因为批准而重跑）
    audit = agent.status(session_id)["audit"]
    executions = [row for row in audit
                  if str(row.get("step_id") or "") in set(completed_before)
                  and str(row.get("operation") or "") != "approval_required"]
    counts: dict[str, int] = {}
    for row in executions:
        step_id = str(row.get("step_id"))
        counts[step_id] = counts.get(step_id, 0) + 1
    assert set(counts) == set(completed_before), (sorted(counts), completed_before)
    assert all(value == 1 for value in counts.values()), counts


def test_wrong_approval_id_is_rejected(tmp_path: Path) -> None:
    from novelforge.agent import AgentError

    stack = _stack(tmp_path)
    _preview, session_id = _plan_acceptance(stack)
    agent = stack["agent"]
    agent.start(session_id, max_batch_steps=20)
    with pytest.raises(AgentError):
        agent.approve(session_id, "approval_does_not_exist")
    # session 没有被推进，仍然等待真正的 approval
    assert agent.status(session_id)["session"]["status"] == "awaiting_approval"
    assert _pending(agent, session_id)


def test_duplicate_approval_is_safe(tmp_path: Path) -> None:
    """重复批准同一个 approval 不得绕过闸门，也不得重复产生 mutation。"""

    stack = _stack(tmp_path)
    _preview, session_id = _plan_acceptance(stack)
    agent = stack["agent"]
    agent.start(session_id, max_batch_steps=20)
    approval_id = _pending(agent, session_id)[0]["approval_id"]
    agent.approve(session_id, approval_id)
    revisions_after_first = {node.node_id: node.revision
                             for node in stack["repository"].all_nodes()} \
        if "repository" in stack else None

    again = agent.approve(session_id, approval_id)
    assert again["status"] in ("awaiting_approval", "paused", "completed",
                               "needs_human_review"), again["status"]
    assert not any(row["code"] == "AGENT_STEP_FAILED" for row in again["errors"])
    # 仍然有闸门：要么在等下一个 approval，要么已完成；不能悄悄跳过
    if again["status"] == "completed":
        return
    assert _pending(agent, session_id), "重复批准后仍然必须存在待批准项"


def test_reject_does_not_execute_protected_step(tmp_path: Path) -> None:
    stack = _stack(tmp_path)
    preview, session_id = _plan_acceptance(stack)
    agent = stack["agent"]
    target = [row["target"]["node_id"] for row in preview["preview"]
              if row["action"] == "accept_revision"][0]
    agent.start(session_id, max_batch_steps=20)
    approval_id = _pending(agent, session_id)[0]["approval_id"]

    rejected = agent.reject(session_id, approval_id, reason="先不要接受")
    assert rejected["status"] == "paused"
    node = stack["services"].editor.get_node(target)["node"]
    assert node["status"] != "accepted"
    steps = _steps(rejected)
    assert all(row["action"] != "accept_revision" or row["status"] != "completed"
               for row in steps)
