---
name: novelforge-v4.0.1.agent.approve-agent-run
description: 对 Agent 的 protected 步骤给出批准或拒绝（作者决定，不得由 Agent 自行批准）。
---

# approve-agent-run

- **Skill ID**: `novelforge-v4.0.1.agent.approve-agent-run`
- **Version**: 1（baseline `V4.0.1`）
- **Capability Module**: `agent`
- **Product owner**: `src/novelforge/application/services/agent.py::AgentService.approve/reject`

## Purpose

把"是否允许 Agent 做敏感动作"变成一条显式、可审计的决定：
例如接受某个 revision（accept_revision）或正式交付（deliver）。

## Use when

- session 状态为 `awaiting_approval`。
- 需要拒绝某个 protected step 并让 Agent 停止 / 重规划。

## Do not use when

- 没有待批准项 → 先 `inspect-agent-session`。
- 想整体停止 → `cancel-agent-session`。

## Preconditions

```text
存在 approval_id（来自 start / status）；operator 已看清目标 revision / selection
```

## Required inputs

| 输入 | 必填 | 说明 |
| --- | --- | --- |
| `session_id` | 是 | 目标 session |
| `approval_id` | 是 | 待批项 |
| `actor` | 否 | 默认 `author` |
| `reason` | 否 | 决定原因（≤400） |

## Authoritative interfaces

```text
UI           「Agent」→ 批准 / 拒绝
REST         POST /api/story-builder/agent/{session_id}/approve
             POST /api/story-builder/agent/{session_id}/reject
Application  AgentService.approve(session_id, approval_id, actor=…, reason=…)
             AgentService.reject(session_id, approval_id, actor=…, reason=…)
MCP          N/A
```

## Procedure

```text
1 inspect-agent-session → 读 approval.action / target（哪个节点 / 哪个 revision / 哪个 selection）
2 独立复核该动作的影响：accept → inspect-node / inspect-revisions；deliver → validate-delivery
3 approve：POST /{session_id}/approve {approval_id, actor:"author", reason}
   reject ：POST /{session_id}/reject  {approval_id, actor:"author", reason}
4 读返回状态：approved → 继续执行；rejected → 停止 / 重规划
5 复验：审批记录进入 audit（谁、何时、为什么）
6 next：resume-agent-session（继续）或 inspect-agent-session
```

## Expected result

```json
{"session_id":"ags_…","status":"executing","approval":{"approval_id":"apr_…",
 "decision":"approved","actor":"author","reason":"…"}}
```

## Verification

```text
· approve 后对应 mutation 才真正发生（之前 0 mutation）
· 拒绝后该 mutation 不发生，session 停止 / 等待重规划
· 过期 approval（revision 已变）→ AGENT_APPROVAL_STALE，必须重新批准
```

## Common failures

| 现象 | 原因 | 处理 |
| --- | --- | --- |
| 409 `AGENT_APPROVAL_STALE` | 目标 revision 已变化 | 重新 plan / 重新审批 |
| 409 `AGENT_APPROVAL_REQUIRED` | 还有其它 protected 步骤 | 逐个审阅 |
| 想批准但没看清内容 | 流程错误 | 先读节点 / 交付预检结果 |

## Safety / invariants

```text
approval 是作者决定：Agent 或自动化不得自行批准
批准必须绑定具体 revision / selection（stale 即失效）
approve 只授权该步，不隐含后续步骤
```

## Side effects

授权后由 session 执行对应 mutation + 写审计记录。

## Related skills

`inspect-agent-session`、`resume-agent-session`、`cancel-agent-session`

## Source references

```text
src/novelforge/application/services/agent.py::approve/reject/_decide
src/novelforge/agent/policy.py（PROTECTED_ACTIONS）
src/novelforge/api/agent_routes.py::approve/reject
tests/agent/test_agent_approval.py
docs/v4/adr/ADR-035-agent-autonomy-is-bounded-by-policy-revision-budget-and-approval.md
```
