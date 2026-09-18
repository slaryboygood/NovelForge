# ADR-036 Agent Plans And Execution Are Auditable And Resumable

> 状态：**Accepted**（V4-11 实施完成）　日期：2026-09-18　阶段：V4-11 Agent Mode
> 相关：ADR-021（editor mutation 是 append-only revision）、`docs/v4/V4_AGENT_CONTRACT.md`

## 决策

```text
· AgentPlan 版本化（plan_revision + plan_history）；replan 不修改旧 plan
· 稳定 step_id（不是 list index）；plan → execution → mutation → verification 可关联
· 每步记录 AgentStepResult（status / revision before-after / result_refs / usage / warnings）
· AgentAuditRecord（session→run→plan→step→operation→business refs）与 EditorOperationRecord 分离
· AgentCheckpoint（session / plan / next step / completed / budget / revision refs）持久化
· resume 前必须重新校验 revision：drift → AGENT_REVISION_CONFLICT（不允许盲目继续）
· 持久化只经 persistence.paths；Agent 数据不是 story truth；不写 secret / prompt
```

## 后果

```text
正面：进程重启 / 审批等待 / 暂停都可安全恢复；任何一次修改都能回答"哪一步、为什么、
      基于哪个 revision、结果如何"；重试不产生重复 revision
负面：编排元数据需要持久化与清理策略；checkpoint 会随步骤数量增长（当前按 session 单文件）
```
