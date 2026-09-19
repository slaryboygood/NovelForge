---
name: novelforge-v4.0.1.repair.verify-repair
description: 复核修复结果：确认 issue 真的解决、没有回归，或明确标出需要作者决定的部分。
---

# verify-repair

- **Skill ID**: `novelforge-v4.0.1.repair.verify-repair`
- **Version**: 1（baseline `V4.0.1`）
- **Capability Module**: `repair`
- **Product owner**: `src/novelforge/quality/repair/verifier.py` +
  `src/novelforge/application/services/editor.py::EditorService.verify_repair`

## Purpose

防止"改了就宣称修好了"：用 before / after 报告对比，确认 resolved / remaining / regressed。

## Use when

- 每次 `apply-repair` 之后（强制）。
- 需要判断还能不能继续自动修。

## Do not use when

- 还没执行修复。

## Preconditions

```text
存在 before 报告（修复前）与 after 报告（修复后）或可重新评估
```

## Required inputs

| 输入 | 必填 | 说明 |
| --- | --- | --- |
| `novel_id` | 是 | 目标作品 |
| `issue_ids` | 是 | 被修复的 issue |

## Authoritative interfaces

```text
UI           「检查」→ 复核
REST         POST /api/story-builder/studio/quality/verify {"novel_id","issue_ids"}
Application  EditorService.verify_repair(issue_ids=…) → RepairVerifier
MCP          tool verify_repair
```

## Procedure

```text
1 POST /studio/quality/verify {novel_id, issue_ids}
2 读 status / resolved_issue_ids / remaining_issue_ids / regressed_issue_ids / reasons
3 读 needs_human_review：true 表示必须由作者决定（不要再自动修）
4 若有 regressed：检查是否引入新 blocker（必要时 restore 到修复前 revision）
5 next：全部 resolved → 重新 evaluate（可选）→ accept-revision 或交付；
  remaining → 可再 plan-repair（仍在 round 预算内）
```

## Expected result

```json
{"status":"verified","resolved_issue_ids":["qi_7f…"],"remaining_issue_ids":[],
 "regressed_issue_ids":[],"needs_human_review":false,"report":{"status":"passed"}}
```

## Verification

```text
· resolved 的 issue 在 Quality Store 中状态为 resolved（而不是被忽略）
· remaining/regressed 与重新评估的结果一致（同一 revision 口径）
· verifier 只读：复核本身不产生新 revision
```

## Common failures

| 现象 | 原因 | 处理 |
| --- | --- | --- |
| `needs_human_review=true` | 冲突 / 无法自动判定 | 交作者决定，不扩大修复范围 |
| issue 又出现（regressed） | 修复引入新问题 | 重新 plan 或 restore |
| 全部 remaining | 模型没真正改到点 | 调整 plan（更明确的 instruction）或手工 patch |

## Safety / invariants

```text
VERIFIED_NOT_CLAIMED：没有 verify 就不能说"已解决"
不改写 before 报告（对比证据必须保留）
needs_human_review 不得被自动忽略
```

## Side effects

更新 Quality Store 的 issue 状态与复核记录；不产生新 revision。

## Related skills

`apply-repair`、`plan-repair`、`novelforge-v4.0.1.quality.inspect-quality-report`

## Source references

```text
src/novelforge/quality/repair/verifier.py
src/novelforge/application/services/editor.py::verify_repair
tests/quality/repair/test_verifier.py
docs/v4/V4_REPAIR_CONTRACT.md §7
```
