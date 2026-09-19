---
name: novelforge-v4.0.1.agent.start-agent-session
description: 启动一个有界 Agent session（按批执行到上限或遇到 protected action 为止）。
---

# start-agent-session

- **Skill ID**: `novelforge-v4.0.1.agent.start-agent-session`
- **Version**: 1（baseline `V4.0.1`）
- **Capability Module**: `agent`
- **Product owner**: `src/novelforge/agent/executor.py` +
  `src/novelforge/application/services/agent.py::AgentService.start`

## Purpose

让已审阅的计划开始执行：每步经 policy / 预算检查，遇到需要批准的动作就停下等作者。

## Use when

- 计划已审阅通过。
- 需要分步推进（不希望一次跑完）。

## Do not use when

- 计划还没看 → 先 `plan-agent-goal`。
- 需要恢复已暂停 / 待批准的 session → `resume-agent-session`。

## Preconditions

```text
存在已创建的 session（plan）；session 内的动作都在注册表内
```

## Required inputs

| 输入 | 必填 | 说明 |
| --- | --- | --- |
| `session_id` | 是 | plan 返回的 session |
| `max_batch_steps` | 否 | 本次最多执行多少步（1..64，缺省用 policy） |
| `policy` | 否 | 覆盖 policy（会记录） |

## Authoritative interfaces

```text
UI           「Agent」→ 执行
REST         POST /api/story-builder/agent/start
Application  AgentService.start(session_id, max_batch_steps=…, policy=…)
MCP          N/A
```

## Procedure

```text
1 确认 session 状态（inspect-agent-session）：应为 created / paused / awaiting_approval
2 POST /agent/start {session_id, max_batch_steps}
3 读返回字段（实测）：ok / status / session_id / run_id / goal / plan / completed_steps /
  pending_steps / changed_nodes / new_revisions / quality_summary / approvals_required /
  usage / warnings / errors / stop_reason / needs_human_review / steps / pending_approvals
  （**没有** steps_run / mutations 顶层字段；步数看 steps[]，受影响节点看 changed_nodes）
4 读每一步的结果与 mutation 计数（对照 policy.max_mutations）
   注意：planner 可能生成 `repair` 步骤但 `inputs.issue_ids` 为空，执行时该步会被
   标成 `skipped`；这不等于修复失败，而是"没有可修 issue"。
5 出现 approval 请求 → approve-agent-run；出现 revision 漂移 → 由作者决定（needs_human_review）
6 next：resume-agent-session（继续）或 inspect-agent-session（审计）
```

## Expected result

```json
{"session_id":"session_…","status":"awaiting_approval","stop_reason":"approval required for allow",
 "approvals_required":[{"approval_id":"approval_…","action":"accept_revision",
 "target":{"kind":"node","node_id":"ch_003","revision":3}}]}
```

## Verification

```text
· 执行的每个 action 都在注册表内；未注册 action 会以 AGENT_PLAN_INVALID 失败
· mutation 计数 ≤ policy.max_mutations；steps ≤ max_steps / max_batch_steps
· protected action 不会被执行：只产生 approval 请求
· 每步都有 audit 记录与 checkpoint
```

## Common failures

| 现象 | 原因 | 处理 |
| --- | --- | --- |
| 409 `AGENT_APPROVAL_REQUIRED` | 命中 protected action | `approve-agent-run` |
| 409 `AGENT_REVISION_CONFLICT` | 目标 revision 被改动（漂移） | 重新 plan |
| 409 `AGENT_BUDGET_EXHAUSTED` | 超出 steps / mutations / token / cost / time | 提高预算（显式）或缩小 scope |
| 409 `AGENT_NEEDS_HUMAN_REVIEW` | 需要作者判断 | 停止自动推进 |

## Safety / invariants

```text
Agent 不自动接受、不自动交付（默认 policy）
不扩大 scope；revision 漂移即停（不强制覆盖）
每一步都通过 Application Service（不绕过业务语义）
```

## Side effects

执行计划中的 mutation（每步都是既有 Application 能力）+ 写 checkpoint / audit。

## Related skills

`plan-agent-goal`、`approve-agent-run`、`resume-agent-session`、`cancel-agent-session`

## Source references

```text
src/novelforge/agent/executor.py、verifier.py、checkpoint.py
src/novelforge/application/services/agent.py::start/_execute
tests/agent/test_agent_execution.py、tests/agent/test_agent_budget_ports.py
docs/v4/V4_AGENT_CONTRACT.md §7
```
