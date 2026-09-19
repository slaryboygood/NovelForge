---
name: novelforge-v4.0.1.agent.cancel-agent-session
description: 取消一个 Agent session，停止后续执行并保留已完成步骤的审计记录。
---

# cancel-agent-session

- **Skill ID**: `novelforge-v4.0.1.agent.cancel-agent-session`
- **Version**: 1（baseline `V4.0.1`）
- **Capability Module**: `agent`
- **Product owner**: `src/novelforge/application/services/agent.py::AgentService.cancel`

## Purpose

安全地中止：不再执行后续步骤，但保留已经发生的 mutation 与审计记录（不假装没发生）。

## Use when

- 计划不再需要 / 结果不对 / 需要作者重新决定。
- 预算或风险不可接受。

## Do not use when

- 只是想暂停 → 等它自然 paused，或先不 resume。
- 想撤销已完成的 mutation → 用 Editor（restore / reject），cancel 不回滚内容。

## Preconditions

```text
session 未处于 completed / cancelled
```

## Required inputs

| 输入 | 必填 | 说明 |
| --- | --- | --- |
| `session_id` | 是 | 目标 session |
| `reason` | 否 | 取消原因（默认 `author cancel`） |

## Authoritative interfaces

```text
UI           「Agent」→ 取消
REST         POST /api/story-builder/agent/{session_id}/cancel
Application  AgentService.cancel(session_id, reason=…)
MCP          N/A
```

## Procedure

```text
1 记录取消前状态与已发生的 mutation（inspect-agent-session + audit）
2 POST /{session_id}/cancel {session_id, reason}
3 读返回 status == cancelled
4 复验：后续步骤不再执行（再 resume 应被拒绝或需新 plan）
5 检查已完成 mutation 是否要保留：要回退 → restore-revision / reject-revision
6 next：如仍需要该目标 → 重新 plan-agent-goal
```

## Expected result

```json
{"session_id":"ags_…","status":"cancelled","stop_reason":"author cancel",
 "steps_run":3,"mutations":2}
```

## Verification

```text
· status == cancelled；之后 resume 不再推进
· audit 保留完整历史（含取消原因）
· 已完成的 mutation 仍在（cancel 不回滚）—— 需要回退时显式 restore
```

## Common failures

| 现象 | 原因 | 处理 |
| --- | --- | --- |
| 以为取消会回滚内容 | 语义误解 | 用 restore-revision 显式回退 |
| 404 `AGENT_NOT_FOUND` | session_id 错 | 用列表重新取 |

## Safety / invariants

```text
destructive-adjacent（影响后续自动化）：必须由作者 / operator 发起
不删除审计记录、不伪造"未执行"
取消不等于回滚：回滚是 Editor 的动作
```

## Side effects

写 session 状态与审计记录；不改故事内容。

## Related skills

`inspect-agent-session`、`novelforge-v4.0.1.editor.restore-revision`、`plan-agent-goal`

## Source references

```text
src/novelforge/application/services/agent.py::cancel
src/novelforge/api/agent_routes.py::cancel
tests/agent/test_agent_execution.py
```
