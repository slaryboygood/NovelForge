---
name: novelforge-v4.0.1.agent.inspect-agent-session
description: 查看 Agent session 的状态、计划进度、审批请求与审计记录（只读）。
---

# inspect-agent-session

- **Skill ID**: `novelforge-v4.0.1.agent.inspect-agent-session`
- **Version**: 1（baseline `V4.0.1`）
- **Capability Module**: `agent`
- **Product owner**: `src/novelforge/application/services/agent.py::AgentService.status/history/audit_records`

## Purpose

随时回答"Agent 现在到哪一步、改了什么、还在等谁"。

## Use when

- 执行前后审计。
- 需要决定 approve / resume / cancel 之前。

## Do not use when

- 需要推进执行 → `start-agent-session` / `resume-agent-session`。

## Preconditions

```text
novel_id 已知（session 列表需要）；session_id 已知（详情需要）
```

## Required inputs

| 输入 | 必填 | 说明 |
| --- | --- | --- |
| `novel_id` | 是（列表） | 目标作品 |
| `session_id` | 是（详情） | 目标 session |

## Authoritative interfaces

```text
UI           「Agent」列表 / 详情
REST         GET /api/story-builder/agent/sessions?novel_id=
             GET /api/story-builder/agent/{session_id}?novel_id=
Application  AgentService.history(limit=…) / status(session_id) / audit_records(session_id)
MCP          N/A
```

## Procedure

```text
1 GET /agent/sessions?novel_id=<id> → 取 session_id 与最新状态
2 GET /agent/{session_id}?novel_id=<id> → 返回 {session, runs, checkpoint,
  pending_approvals, audit}：状态/计划/决策在 `session`，逐步结果在 `runs[].step_results`，
  断点与预算在 `checkpoint`，待批在 `pending_approvals`，时间线在 `audit`
3 读 audit[]：每步 operation / status / step_id / target / business_result_refs
   （没有 revision 前后对照字段，revision 变化看 runs[].step_results[]）
4 对照 policy：mutations / tokens / cost / elapsed 是否接近上限
5 next：待审批 → approve-agent-run；paused → resume-agent-session；异常 → cancel-agent-session
```

## Expected result

```json
{"session":{"session_id":"session_…","status":"awaiting_approval","stop_reason":"…",
            "checkpoint":{…},"budget":{…}},
 "runs":[{"run_id":"run_…","status":"awaiting_approval","step_results":[…]}],
 "checkpoint":{"completed_steps":[…],"next_step_sequence":2,"budget_used":{…}},
 "pending_approvals":[{"approval_id":"approval_…","action":"accept_revision"}],
 "audit":[{"operation":"approval_required","status":"awaiting_approval"}]}
```

## Verification

```text
· status ∈ AGENT_STATUSES（created/planning/awaiting_approval/executing/verifying/
  paused/completed/failed/cancelled/needs_human_review）
· audit 里的 mutation 次数与 Blueprint / Quality Store 实际变化一致
· 只读：调用不改变 session 状态
```

## Common failures

| 现象 | 原因 | 处理 |
| --- | --- | --- |
| 404 `AGENT_NOT_FOUND` | session_id 不存在 | 用列表重新取 |
| 状态与会话认知不一致 | 记错 session | 用 audit 时间线核对 |

## Safety / invariants

```text
只读；不触发执行
审计记录不得被改写（它是 Agent 行为的凭据）
```

## Side effects

无。

## Related skills

`plan-agent-goal`、`approve-agent-run`、`resume-agent-session`、`cancel-agent-session`

## Source references

```text
src/novelforge/agent/audit.py、contracts.py
src/novelforge/api/agent_routes.py::sessions/status
tests/agent/test_agent_resume_budget.py
```
