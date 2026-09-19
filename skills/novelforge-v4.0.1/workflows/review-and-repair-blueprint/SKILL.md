---
name: novelforge-v4.0.1.workflows.review-and-repair-blueprint
description: 端到端流程：检查 → 定位 issue → 修复预览 → 执行 → 复核 → 作者接受（或改成手工编辑）。
---

# review-and-repair-blueprint

- **Skill ID**: `novelforge-v4.0.1.workflows.review-and-repair-blueprint`
- **Version**: 1（baseline `V4.0.1`）
- **Capability Module**: `workflows`（组合层）
- **Product owner**: 无

## Purpose

把"质量有问题"变成一条闭环：**发现 → 计划 → 执行 → 复核 → 作者决定**，
并且任何冲突都停下来找作者。

## Use when

- 质量报告有 issue（尤其 blocker / major）。
- 修复后需要复核。

## Do not use when

- 只是想知道当前状态 → `inspect-quality-report`。
- issue 属结构非法（repairable=false）→ 需要作者 / 手工编辑，不要强行自动修。

## Preconditions

```text
Blueprint 至少有内容；要执行 AI 修复时 provider 已启用
```

## Required inputs

| 输入 | 必填 | 说明 |
| --- | --- | --- |
| `novel_id` | 是 | 目标作品 |
| `gate` / `status` | 否 | 过滤 issue |
| `issue_ids` | 是（执行时） | 选定的 open issue |

## Authoritative interfaces

```text
见各步骤 skill
```

## Procedure（只引用 skill ID）

```text
Step 1 novelforge-v4.0.1.quality.evaluate-blueprint        → 运行 Q0–Q9
Step 2 novelforge-v4.0.1.quality.inspect-quality-report    → 看 gate 结论与 blocker 数
Step 3 novelforge-v4.0.1.quality.list-quality-issues       → 取 issue_ids + evidence + repairable
Step 4 novelforge-v4.0.1.repair.plan-repair                → dry-run 预览（0 mutation）
Step 5 若预览显示冲突 → 停止（needs human review），转 Step 8
Step 6 novelforge-v4.0.1.repair.apply-repair               → 执行（新 revision）
Step 7 novelforge-v4.0.1.repair.verify-repair              → resolved / remaining / regressed
Step 8 仍不满意 → novelforge-v4.0.1.editor.patch-node 或
       novelforge-v4.0.1.editor.rewrite-node（作者掌控）
Step 9 想回退 → novelforge-v4.0.1.editor.restore-revision
Step 10 满意 → novelforge-v4.0.1.editor.accept-revision（作者决定）
Step 11 需要交付 → novelforge-v4.0.1.workflows.prepare-final-delivery
```

## Expected result

issue 有明确归宿：resolved（verifier 确认）或标记为需要作者决定；
被修改的节点产生新 revision 且未自动接受。

## Verification

```text
· 每次 apply 后必须有 verify（不允许"改完就宣称解决"）
· 修复后 preserve 字段逐字未变；其它节点 revision 未变
· accept 步骤由作者发起（Agent 需 approval）
· 达到 max_repair_rounds 仍失败 → 停下来找作者（不要放宽约束）
```

## Common failures

| 现象 | 原因 | 处理 |
| --- | --- | --- |
| `REPAIR_NOT_ALLOWED` | code 不可自动修 | 转手工编辑 / 作者决定 |
| `REPAIR_CONTRACT_CONFLICT` | preserve 与 allow_change 冲突 | 停止自动修复 |
| 反复 remaining | 上游结构问题 | 回到 generation / patch 修上游 |

## Safety / invariants

```text
VERIFIED_NOT_CLAIMED；冲突即停；不扩大范围
不因为"想清空 issue"而 ignore / accepted_risk（那是作者决定）
```

## Side effects

与各步骤相同（Blueprint 新 revision + Quality Store 记录）。

## Related skills

`create-new-story-blueprint`、`prepare-final-delivery`

## Source references

```text
skills/novelforge-v4.0.1/{quality,repair,editor}/*
docs/v4/V4_REPAIR_CONTRACT.md §8
```
