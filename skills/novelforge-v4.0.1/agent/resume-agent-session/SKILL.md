---
name: novelforge-v4.0.1.agent.resume-agent-session
description: 从检查点继续一个暂停或待批准的 Agent session（按批执行到下一个边界）。
---

# resume-agent-session

- **Skill ID**: `novelforge-v4.0.1.agent.resume-agent-session`
- **Version**: 1（baseline `V4.0.1`）
- **Capability Module**: `agent`
- **Product owner**: `src/novelforge/agent/checkpoint.py` +
  `src/novelforge/application/services/agent.py::AgentService.resume`

## Purpose

让长任务可以分批推进：每批有上限，边界处可停下来检查。

## Use when

- session 处于 `paused` 或已批准 pending step。
- 想继续但只推进有限步数。

## Do not use when

- 还没批准 protected step → `approve-agent-run`。
- 状态是 completed / cancelled → 不能 resume（需要新 plan）。

## Preconditions

```text
session 存在且状态允许 resume（paused / awaiting_approval→已批准）
checkpoint 存在
```

## Required inputs

| 输入 | 必填 | 说明 |
| --- | --- | --- |
| `session_id` | 是 | 目标 session |
| `max_batch_steps` | 否 | 本批上限（1..64） |
| `reason` | 否 | 记录原因 |

## Authoritative interfaces

```text
UI           「Agent」→ 恢复
REST         POST /api/story-builder/agent/{session_id}/resume
Application  AgentService.resume(session_id, max_batch_steps=…)
MCP          N/A
```

## Procedure

```text
1 inspect-agent-session → 确认当前状态与 checkpoint
2 POST /{session_id}/resume {session_id, max_batch_steps}
3 读返回状态与本次执行步数
4 若又命中 protected / 预算上限 → 重复 approve / resume（或 cancel）
5 复验：审计记录连续（没有跳步 / 没有重复执行同一步）
6 next：completed → 复核结果（质量 / 交付）；否则继续 resume
```

## Expected result

```json
{"session_id":"ags_…","status":"paused","steps_run":5,
 "checkpoint":{"last_step":"generate_node","revision_refs":{"ch_003":3}}}
```

## Verification

```text
· resume 从 checkpoint 继续，不重复已完成的 mutation
· 预算计数跨批次累计（不因 resume 重置）
· revision 漂移 → 停止并标记 needs_human_review
```

## Common failures

| 现象 | 原因 | 处理 |
| --- | --- | --- |
| 409 `AGENT_MAX_STEPS_REACHED` | 达到 policy 上限 | 显式提高 max_steps 或缩小 scope |
| 409 `AGENT_REVISION_CONFLICT` | 期间有人改了目标节点 | 重新 plan |
| 409 `AGENT_BUDGET_EXHAUSTED` | token / cost / time 超限 | 与作者确认后再放宽 |

## Safety / invariants

```text
resume 不会绕过 approval 或预算
不静默扩大 scope
checkpoint / audit 必须保持一致（不得手工改）
```

## Side effects

继续执行后续步骤（既有 Application 能力）+ 更新 checkpoint / audit。

## Related skills

`approve-agent-run`、`inspect-agent-session`、`cancel-agent-session`

## Source references

```text
src/novelforge/agent/checkpoint.py、executor.py
src/novelforge/application/services/agent.py::resume
tests/agent/test_agent_resume_budget.py
docs/v4/adr/ADR-036-agent-plans-and-execution-are-auditable-and-resumable.md
```
