---
name: novelforge-v4.0.1.delivery.create-delivery-snapshot
description: 建立一个交付快照：钉住每个节点 revision 并生成 manifest（可在不导出全部格式时单独使用）。
---

# create-delivery-snapshot

- **Skill ID**: `novelforge-v4.0.1.delivery.create-delivery-snapshot`
- **Version**: 1（baseline `V4.0.1`）
- **Capability Module**: `delivery`
- **Product owner**: `src/novelforge/delivery/store.py` +
  `src/novelforge/application/services/export.py::ExportService.create_snapshot`

## Purpose

把"这次交付用了哪些 revision"固定下来，使交付物可复现、可审计。

## Use when

- 需要先钉 revision，再分多次导出 / 分发。
- 审计场景：需要一份稳定的 selected_revisions 记录。

## Do not use when

- 只要产物文件 → `deliver-blueprint`（快照 + 导出一次完成）。

## Preconditions

```text
preflight 通过（validate-delivery）
```

## Required inputs

| 输入 | 必填 | 说明 |
| --- | --- | --- |
| `novel_id` | 是 | 目标作品 |
| `selection_mode` / `profile` / `formats` | 是（选择语义） | 与预检一致 |
| `explicit_revisions` | 当 mode=`explicit_revisions` | `node_id → revision` 映射 |
| `idempotency_key` | 建议 | 重试不产生第二个快照 |

## Authoritative interfaces

```text
UI           「交付」（建立交付）
REST         POST /api/story-builder/delivery（dry_run=false）
Application  ExportService.create_snapshot(selection)
MCP          tool create_delivery_snapshot
```

## Procedure

```text
1 validate-delivery（确认 ok）
2 POST /delivery {novel_id, selection_mode, profile, formats, idempotency_key, dry_run:false}
3 读返回 snapshot_id / manifest{manifest_id, selected_revisions, artifacts[]}
4 复验：GET /delivery/snapshots 包含该 snapshot_id
5 复验：selected_revisions 覆盖所有应有节点，且没有跨作品记录
6 next：download-delivery-artifact / inspect-delivery-manifest
```

## Expected result

```json
{"snapshot_id":"ds_…","novel_id":"novel_alpha","selection_mode":"accepted",
 "manifest":{"manifest_id":"dm_…","selected_revisions":{"ch_003":4,"sc_003_1":2},
             "formats":["json","markdown"],
             "artifacts":[{"format":"markdown","path":"…","checksum":"…","size":1234}]}}
```

## Verification

```text
· snapshot 记录 selected_revisions（revision-pinned），不是"当前状态快照"
· artifact 的 checksum 与 manifest 一致
· 相同 idempotency_key → 返回同一 snapshot（不重复发布）
```

## Common failures

| 现象 | 原因 | 处理 |
| --- | --- | --- |
| `DELIVERY_EXPORT_FAILED` | 导出中途失败 | 检查 blocking_reason；重试用同 idempotency_key |
| 快照缺少某节点 | 该节点未 accepted / 质量未过 | 处理后再交付 |
| `DELIVERY_OWNERSHIP_MISMATCH` | novel_id 与 selection 不一致 | 统一 novel_id |

## Safety / invariants

```text
ATOMIC：失败不留半个交付物（回滚或标记失败）
REVISION_PINNED：快照一旦建立，后续节点改动不影响该快照
NO_SECRET：交付物经 secret scan，不含 key / Authorization / 内部绝对路径
```

## Side effects

写 delivery snapshot + manifest + artifacts 到该书作用域。

## Related skills

`validate-delivery`、`deliver-blueprint`、`inspect-delivery-manifest`

## Source references

```text
src/novelforge/delivery/store.py、manifest.py、compiler.py
src/novelforge/application/services/export.py
tests/delivery/test_delivery_service.py、tests/delivery/test_package.py
docs/v4/V4_DELIVERY_CONTRACT.md §7
```
