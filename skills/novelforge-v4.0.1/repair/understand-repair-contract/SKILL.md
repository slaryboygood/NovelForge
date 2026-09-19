---
name: novelforge-v4.0.1.repair.understand-repair-contract
description: 掌握 V4 Repair Contract：minimal scope、preserve 硬约束、revision 语义、预算与 M11 frozen 边界。
---

# understand-repair-contract

- **Skill ID**: `novelforge-v4.0.1.repair.understand-repair-contract`
- **Version**: 1（baseline `V4.0.1`）
- **Capability Module**: `repair`
- **Product owner**: `src/novelforge/quality/repair/contracts.py` + `docs/v4/V4_REPAIR_CONTRACT.md`

## Purpose

理解"修复为什么不能随便改"：契约把可改动范围写死，冲突就必须停下来找作者。

## Use when

- 需要解释某次修复为什么被拒绝。
- 设计新的 issue code（要同时给出 preserve / allow_change）。
- 判断某问题是否应该由 repair 处理，还是应该由作者改。

## Do not use when

- 只是执行修复 → `plan-repair` / `apply-repair`。

## Preconditions

```text
无
```

## Required inputs

```text
无
```

## Authoritative interfaces

```text
UI           N/A
REST         N/A
Application  novelforge.quality.repair（RepairContract / RepairPlan / RepairExecutor / RepairVerifier）
MCP          N/A
```

## Procedure（读法顺序）

```text
1 issue.code → 注册表里的 preserve / allow_change（codes.py::ISSUE_CODES）
2 RepairContract：target node + allow_change（白名单）+ preserve（硬约束）+ verification gates
3 blast radius：改动会影响哪些下游节点（只报告，不自动改）
4 冲突处理：契约无法同时满足 → 不修，标记 needs_human_review
5 预算：max_repair_rounds（policy）+ usage / model 调用预算
6 结果语义：executor 产生新 revision；verifier 决定 resolved / remaining / regressed
7 边界：M11 历史 570 章 Repair（story_engine/repair.py + REPAIR_GATE_V1）是 frozen 的另一套能力，
   V4 Repair 不得复用它，也不得修改它
```

## Expected result

能正确回答：

```text
· 为什么不能"顺手"改 title？（title 不在该 code 的 allow_change 里）
· preserve 冲突时怎么办？（停止自动修复 → 作者决定）
· 修复后是否自动 accepted？（不会，仍需作者 accept）
```

## Verification

```text
· 交叉核对 src/novelforge/quality/repair/contracts.py 与 codes.py
· 交叉核对 docs/v4/V4_REPAIR_CONTRACT.md §3、§4、§9、§10
· 交叉核对 tests/test_acceptance_repair_regressions.py（回归门禁）
```

## Common failures

| 现象 | 原因 | 处理 |
| --- | --- | --- |
| 期望修复改结构字段 | 结构 identity 不在 allow_change | 用 move / restore 或作者手工改 |
| 反复修不好 | 问题其实是上游结构错误 | 回到 generation / editor 修正上游 |
| 想看 M11 修复能力 | 已 frozen 且与 V4 不同 | 不要复活；按 frozen 边界处理 |

## Safety / invariants

```text
不得修改 frozen Repair Contract / REPAIR_GATE_V1 / Truth Boundary
不得通过降低 preserve 或跳过 verifier 让修复"通过"
```

## Side effects

无。

## Related skills

`plan-repair`、`apply-repair`、`verify-repair`、`novelforge-v4.0.1.quality.understand-quality-gates`

## Source references

```text
src/novelforge/quality/repair/*
docs/v4/V4_REPAIR_CONTRACT.md
docs/v4/adr/ADR-019-repair-is-minimal-scope-and-revisioned.md
```
