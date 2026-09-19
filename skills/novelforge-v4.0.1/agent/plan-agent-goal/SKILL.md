---
name: novelforge-v4.0.1.agent.plan-agent-goal
description: 把一个目标变成 Agent 计划预览（0 mutation），看清步骤、动作是否 protected、预算与 scope。
---

# plan-agent-goal

- **Skill ID**: `novelforge-v4.0.1.agent.plan-agent-goal`
- **Version**: 1（baseline `V4.0.1`）
- **Capability Module**: `agent`
- **Product owner**: `src/novelforge/agent/planner.py` +
  `src/novelforge/application/services/agent.py::AgentService.plan`

## Purpose

在让 Agent 动任何东西之前，先得到可审阅的计划：它打算做哪几步、哪几步需要你批准。

## Use when

- 第一次让 Agent 处理某本书 / 某个范围。
- 需要向作者展示"Agent 会做什么"。

## Do not use when

- 目标本身还不清楚（先明确作品 / 节点范围）。
- 只想要单一原子操作 → 直接用对应 skill（不必启动 Agent）。

## Preconditions

```text
novel_id 已知；scope 明确（novel / unit / node 集合）
```

## Required inputs

| 输入 | 必填 | 默认 | 说明 |
| --- | --- | --- | --- |
| `novel_id` | 是 | — | 目标作品 |
| `instruction` | 是 | — | 目标（1..600 字） |
| `scope_kind` / `scope_unit_id` / `scope_node_ids` | 否 | novel | 作用域 |
| `constraints` / `success_criteria` | 否 | 空 | 约束与成功判据 |
| `policy` | 否 | 默认保守 policy | 预算 / allow_* 开关 |
| `dry_run` | 否 | true | 计划预览 |

## Authoritative interfaces

```text
UI           「Agent」→ 计划
REST         POST /api/story-builder/agent/plan
Application  AgentService.plan(goal, policy=…, dry_run=True)
MCP          N/A
```

## Procedure

```text
1 resolve novel_id（inspect-novels）；建议先用 inspect-overview 看现状
2 POST /agent/plan {novel_id, instruction, scope_kind:"novel", policy?}
3 读返回 session_id / status（应为 awaiting_approval 或 created，且 0 mutation）/ plan.steps[]
4 对每个 step 读 action / target / mutation / protected / reason
5 确认 scope 与约束符合预期；必要时调整 instruction / constraints 后重新 plan
6 next：start-agent-session（执行）或放弃
```

## Expected result

```json
{"session_id":"ags_…","status":"awaiting_approval","dry_run":true,
 "plan":{"steps":[{"action":"inspect_blueprint","mutation":false,"protected":false},
                  {"action":"generate_node","mutation":true,"protected":false},
                  {"action":"accept_revision","mutation":true,"protected":true},
                  {"action":"deliver","mutation":true,"protected":true}]},
 "policy":{"allow_auto_accept":false,"allow_delivery":false,"max_steps":20}}
```

## Verification

```text
· dry_run 下 0 mutation：Blueprint revision / Quality Store / delivery 全不变
· 每个 step.action 都在 ACTION_REGISTRY 内（13 个）
· protected action 被标记，且要求 approval
```

## Common failures

| 现象 | 原因 | 处理 |
| --- | --- | --- |
| 422 `AGENT_PLAN_INVALID` | 引用了未注册 / 禁止 action | 重新表述目标（不要请求 shell / 文件操作） |
| 403 `AGENT_POLICY_DENIED` | 目标需要被禁用的能力（例如交付） | 显式改 policy 并理解后果 |
| steps 超出预期范围 | scope 太宽 | 缩小 scope（unit / node 集合） |

## Safety / invariants

```text
计划本身 0 mutation；不得把"计划里出现"当成"已执行"
protected step 必须显式批准；Agent 不得替作者决定
```

## Side effects

写 agent session 记录（状态 / 计划 / 审计），不改故事内容。

## Related skills

`start-agent-session`、`inspect-agent-session`、`approve-agent-run`

## Source references

```text
src/novelforge/agent/planner.py、registry.py、policy.py
src/novelforge/api/agent_routes.py::plan
tests/agent/test_agent_planner.py、tests/agent/test_agent_contracts.py
docs/v4/V4_AGENT_CONTRACT.md §4–§6
```
