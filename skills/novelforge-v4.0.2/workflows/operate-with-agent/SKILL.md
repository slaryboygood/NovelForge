---
name: novelforge-v4.0.2.workflows.operate-with-agent
description: 端到端流程：用有界 Agent 推进一本书——计划预览 → 执行 → 审批（逐个 protected step）→ 恢复 → 审计 → 收尾。
---

# operate-with-agent

- **Skill ID**: `novelforge-v4.0.2.workflows.operate-with-agent`
- **Version**: 1（baseline `V4.0.2`；继承 V4.0.1 同名 workflow）
- **Capability Module**: `workflows`（组合层）
- **Product owner**: 无

## Purpose

把"让 Agent 帮我推进这本书"变成受控流程：每步可见、敏感动作要批准、随时能停。

## Use when

- 目标需要多步（生成 → 评估 → 修复 → 待接受）。
- 希望在自动化与掌控之间取得平衡。

## Do not use when

- 单一原子操作 → 直接用对应 skill（Agent 过度设计）。
- 需要无人值守自动接受 / 交付 → **默认不允许**（policy 显式关闭）。

## Preconditions

```text
novel_id 确定；scope 明确；如涉及生成，provider 已启用
```

## Required inputs

| 输入 | 必填 | 说明 |
| --- | --- | --- |
| `novel_id` | 是 | 目标作品 |
| `instruction` | 是 | 目标 |
| `scope_kind` | 否 | novel / unit / nodes |
| `policy` | 否 | 预算与 allow_* 开关（默认保守） |

## Authoritative interfaces

```text
见各步骤 skill（UI / REST / Application；MCP 不提供编排）
```

## Procedure（只引用 skill ID）

```text
Step 1 novelforge-v4.0.1.studio.inspect-overview           → 先看现状
Step 2 novelforge-v4.0.1.agent.plan-agent-goal             → 计划预览（0 mutation）
Step 3 审阅步骤：protected / mutation / scope 是否符合预期
Step 4 novelforge-v4.0.1.agent.start-agent-session         → 有界执行（batch 边界会 paused）
Step 5 novelforge-v4.0.2.agent.approve-agent-run           → 逐个批准 protected step
       （批准前先自己复核：accept → inspect-node；deliver → validate-delivery）
Step 6 novelforge-v4.0.1.agent.resume-agent-session        → 预算 / 批量边界继续
Step 7 novelforge-v4.0.1.agent.cancel-agent-session        → 目标不再需要时取消
Step 8 novelforge-v4.0.1.agent.inspect-agent-session       → 审计每一步与预算使用
Step 9 收尾：novelforge-v4.0.1.quality.evaluate-blueprint → 需要时
       novelforge-v4.0.2.workflows.prepare-final-delivery
```

## Expected result

session 以 completed / paused / cancelled 收敛；每步有 audit；
作者只批准了它真正同意的动作（一次批准只授权一个 protected step）。

## Verification

```text
· plan 阶段 0 mutation；approve 之前 protected action 不发生
· 批准后该 protected step 完成，且 result_refs.approval_id == 被批准的 approval_id
· mutation 计数与 Blueprint / Quality Store 变化一致
· 审计 + checkpoint 连续（无跳步、无重复执行）
· 默认未自动接受、未自动交付
```

V4.0.2 实测（PB-2 closure，公开接口，目标「接受当前章节与场景的结果」）：

```text
plan → steps=3，protected=[request_accept, accept_revision]
start → awaiting_approval
approve(request_accept) → awaiting_approval（下一步 accept_revision 需要单独批准），
                          request_accept step = completed 且 approval_id 已记录
approve(accept_revision) → completed，errors=[]
session → completed，approvals=2，decisions=2；目标场景 status=accepted
浏览器门禁（tests/browser_v4_11_agent.cjs）真实验证同一路径：approvals >= 1 且最终完成
```

## Common failures

| 现象 | 原因 | 处理 |
| --- | --- | --- |
| `AGENT_REVISION_CONFLICT` | 目标节点被改动 | 重新 plan |
| `AGENT_BUDGET_EXHAUSTED` / `reached batch limit` | 预算 / 批量上限 | `resume-agent-session` 或显式提高预算 |
| 需要 Agent 做 shell / 文件操作 | 不在 action 注册表 | 明确不支持（也不要加） |

## Safety / invariants

```text
Agent 只用注册的 13 个 action；永不 run_shell / read_file / import_module
protected action 必须作者批准；approve 绑定 revision，stale 即失效
取消不回滚：内容回退用 editor.restore-revision
```

## Side effects

与各步骤相同 + agent session / audit / checkpoint 写入。

## Related skills

`use-novelforge-through-mcp`、`review-and-repair-blueprint`、`prepare-final-delivery`、
`novelforge-v4.0.2.agent.approve-agent-run`

## Source references

```text
skills/novelforge-v4.0.1/agent/*（继承）+ skills/novelforge-v4.0.2/agent/*
src/novelforge/agent/**、src/novelforge/application/services/agent.py
tests/agent/test_agent_approval_lifecycle.py、tests/browser_v4_11_agent.cjs
docs/v4/V4_AGENT_CONTRACT.md §3–§9
docs/v4/V4_0_2_STABILIZATION_REPORT.md
```
