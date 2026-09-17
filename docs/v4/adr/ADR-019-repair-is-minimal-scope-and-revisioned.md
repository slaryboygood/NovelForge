# ADR-019 — Repair Is Minimal-Scope And Revisioned

```
Status    : Accepted（V4-05 实施完成）
Date      : 2026-09-17
Context   : V4-05 Quality Closed Loop & Targeted Repair
Related   : ADR-006（revision model）；ADR-016（Blueprint node graph）；
            ADR-017（generated content is proposal）；ADR-018（quality is gate-based）；
            V4_REPAIR_CONTRACT.md
```

## Context

发现问题之后，最自然的"修复"是：

```text
发现标题重复 → 让模型重写前三章
```

这与项目的两条既有边界直接冲突：

```text
ADR-017  生成结果是 proposal，不能静默覆盖
AGENTS.md §12  AI 修改绝不静默覆盖作者内容
```

而且 `R-15 Writer overwrite` / `R-14 Quality infinite repair loop` 已经把这个风险登记在案。

## Decision

1. **修复必须是最小范围的**：`RepairPlanner` 依据 issue 的 scope + Blueprint 结构关系
   决定 `minimal scope`；模型**不**参与决定改哪里（§54）。
2. **修复必须产生新 revision**（append-only）：`accepted` 节点被修复时产生一个新的
   `proposed` revision，旧 revision 永久可读，绝不原地覆盖（§35–§36）。
3. **preserve 是硬约束**：`node_id` / `source_ids` / `canon` 以及结构 identity 字段
   （scene 的 `chapter_id`、chapter 的 `characters`、arc 的 `character_id`、
   payoff 的 `resolves_setup_ids`）永不允许改动；执行后逐字段比对，违反即上报
   `REPAIR_PRESERVE_VIOLATION`（§30）。
4. **修复经 Generation Public Contract**：`repair → generation.regenerate(...)`，
   修复层不自己实现 LLM 生成（§33）；`generation` 绝不反向依赖 `quality`。
5. **冲突与预算必须显式停止**：`expected_revision` 冲突在**任何模型调用之前**抛出
   `RevisionConflict`；同一 `idempotency_key` 重放不产生第二个 revision；
   超过 `max_repair_rounds` / token / cost 预算 → `needs_human_review`（§39 / §41 / §65–§66）。
6. **修复必须被验证**：模型返回成功 ≠ 问题解决。`RepairVerifier` 重新执行受影响 gate
   （blast radius），确认原 issue 消失且没有引入新的 blocking issue（§37–§38）。

## Consequences

正面：

* 作者 accepted 的内容不可能被 AI 静默改写（可审计的新 revision）；
* 修复成本与影响面可控（一个节点一个任务；blast radius 决定复核范围）；
* 幂等 / 冲突语义与 V4-01 的 revision 契约一致，不与 M11 frozen repair 混淆。

代价：

* 某些问题无法自动修复（例如"未回收 setup"需要新增 payoff 节点，属于结构变更）→
  明确进入 `needs_human_review`，不做含糊的半修复；
* 每个修复都要一次完整 re-evaluate（只复核 blast radius 内的 gate 与 scope）。

## Alternatives considered

| 方案 | 为什么不选 |
| --- | --- |
| 就地覆盖节点 payload | 违反 ADR-017 / AGENTS.md §12；丢失作者已接受内容 |
| 发现问题就整体重生成 | 违反"最小范围"；成本失控；会改动无关节点 |
| 让模型决定修复范围 | 与 §54 冲突："最好重写前三章"会变成实际的大范围改写 |
| 复用 M11 frozen repair | M11 是 570 章历史内容修复（`REPAIR_GATE_V1`、已 closeout 只读），对象与 gate 完全不同（V4_ARCHITECTURE CHALLENGE-03） |

## Evidence

```text
src/novelforge/quality/repair/planner.py    minimal scope / preserve / allow_change / 冲突检测
src/novelforge/quality/repair/blast_radius.py  direct + dependent + verification gates
src/novelforge/quality/repair/executor.py   新 revision / 预检 / 幂等 / preserve 校验
src/novelforge/quality/repair/verifier.py   重新评估受影响 gate + resolved/remaining/new
tests/quality/repair/test_executor.py       新 revision、accepted 不覆盖、冲突 0 次模型调用、幂等
tests/quality/repair/test_verifier.py       resolved / partial / regression
tests/quality/repair/test_loop.py           §64 计划外节点 byte-for-byte 不变
```

