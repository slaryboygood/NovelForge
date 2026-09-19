# Module: `repair` — 定向修复与复核

```text
Module purpose     对质量 issue 做最小范围修复：plan → execute → verify
Authoritative owner src/novelforge/quality/repair/{planner,executor,verifier,blast_radius}.py
Owned skills       plan-repair / apply-repair / verify-repair / understand-repair-contract
Truth ownership    通过 Editor 写 Blueprint 新 revision；Quality Store 记录 issue 状态变化
Public interfaces  UI「检查」；REST /studio/quality/{repair,verify}；
                   Application EditorService.plan_repair/repair/verify_repair、ReviewService.repair_issue；
                   MCP tools plan_repair / repair_issue / verify_repair
Dependencies       quality（issue / code registry）、editor（写入）、generation（改写契约）
Forbidden          silent overwrite accepted Blueprint、扩大修复范围、绕过 verifier 宣称解决
Related modules    quality（发现）、editor（作者改动）、delivery（复核后再交付）
```

## 闭环

```text
issue → plan（dry-run，0 mutation）→ execute（新 revision + repair 记录）→ verify（复核）→
  resolved   → 可以继续（接受 / 交付）
  remaining  → 可再修（受 max_repair_rounds 限制）
  regressed  → 出现新问题，需作者介入
  needs_human_review → 停止自动修复，交作者决定
```

## 不变量

```text
MINIMAL_SCOPE：只改 contract 声明的 allow_change 字段
PRESERVE_HARD：preserve 字段必须逐字保持（违反 → REPAIR_CONTRACT_CONFLICT）
NEW_REVISION_ONLY：修复产生新 revision，历史永不删除
VERIFIED_NOT_CLAIMED：只有 verifier 确认才算 resolved
M11_FROZEN_SEPARATE：历史 570 章 Repair（story_engine/repair.py）与 V4 Repair 不是同一能力
```
