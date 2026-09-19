---
name: novelforge-v4.0.1.repair.apply-repair
description: 按已确认的修复计划执行定向修复，产生新 revision 与 repair 记录（preserve 硬约束）。
---

# apply-repair

- **Skill ID**: `novelforge-v4.0.1.repair.apply-repair`
- **Version**: 1（baseline `V4.0.1`）
- **Capability Module**: `repair`
- **Product owner**: `src/novelforge/quality/repair/executor.py` +
  `src/novelforge/application/services/editor.py::EditorService.repair`

## Purpose

把计划变成一次受控写入：只改允许的字段，其余逐字保持，产生新 revision，并留下 repair 记录。

## Use when

- `plan-repair` 的预览已确认。
- 作者（或 Agent，按 policy）批准执行修复。

## Do not use when

- 还没 plan → 先 `plan-repair`。
- 想手工精修某个字段 → 用 `patch-node`（不涉及 repair 契约）。

## Preconditions

```text
issue 仍为 open 且 repairable；plan 的 target revisions 未过期
若要 AI 改写：provider 已启用
```

## Required inputs

| 输入 | 必填 | 说明 |
| --- | --- | --- |
| `novel_id` | 是 | 目标作品 |
| `issue_ids` | 是 | 要修的 issue |
| `idempotency_key` | 建议 | 重试不产生第二个 revision |
| `dry_run` | — | 必须是 false 才会写入 |

## Authoritative interfaces

```text
UI           「检查」→ 执行修复
REST         POST /studio/quality/repair {"novel_id","issue_ids","dry_run":false,"idempotency_key"}
Application  EditorService.repair(issue_ids, dry_run=False) → ReviewService.repair_issue
MCP          tool repair_issue
```

## Procedure

```text
1 plan-repair 确认 scope / preserve
2 POST /studio/quality/repair {novel_id, issue_ids, dry_run:false, idempotency_key}
3 读 outcome：status / preview / result（新 revision）/ verification（初判）
4 对每个被修改节点读 inspect-node，确认 revision 递增且 preserve 字段未变
5 读 issue 状态变化：open → repairing → resolved（需 verifier 确认）
6 next：verify-repair（必须）
```

## Expected result

```json
{"status":"repaired","result":{"nodes":{"sc_003_2":{"before_revision":2,"revision":3}}},
 "verification":{"status":"pending"}}
```

## Verification

```text
· 新 revision 存在且 status == proposed（修复不会自动接受）
· preserve 字段逐字不变（否则必须失败：EDITOR_PRESERVE_VIOLATION）
· 同一 idempotency_key 重放 → 不产生第二个 revision
· Blueprint 其它节点 revision 不变（最小范围）
```

## Common failures

| 现象 | 原因 | 处理 |
| --- | --- | --- |
| 409 `REPAIR_CONTRACT_CONFLICT` | preserve 与 allow_change 冲突 | 不要强修；记录 needs human review |
| 409 `REPAIR_ROUND_LIMIT` | 超过 `max_repair_rounds` | 停止自动修复，交作者决定 |
| 409 `REVISION_CONFLICT` | 节点在 plan 后被改过 | 重新 plan |
| 422 `REPAIR_NOT_ALLOWED` | code 不可自动修 | 作者决定 |

## Safety / invariants

```text
append-only：不覆盖历史 revision，不静默覆盖 accepted 内容
不自动 accept：修复后仍需作者接受（quality pass ≠ accepted）
冲突即停：不扩大范围、不降低 preserve
```

## Side effects

写 Blueprint 新 revision + Repair 历史记录（`quality/repair` 路径）+ 可能的模型调用。

## Related skills

`plan-repair`、`verify-repair`、`novelforge-v4.0.1.editor.restore-revision`（回退手段）

## Source references

```text
src/novelforge/quality/repair/executor.py
src/novelforge/application/services/editor.py::repair
src/novelforge/interfaces/mcp/tools/quality.py
tests/quality/repair/test_executor.py、tests/quality/repair/test_loop.py
docs/v4/V4_REPAIR_CONTRACT.md §6、§8
```
