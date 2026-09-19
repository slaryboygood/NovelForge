---
name: novelforge-v4.0.1.delivery.list-delivery-snapshots
description: 列出某本作品已产生的交付快照（时间、格式、selection mode、profile、状态）。
---

# list-delivery-snapshots

- **Skill ID**: `novelforge-v4.0.1.delivery.list-delivery-snapshots`
- **Version**: 1（baseline `V4.0.1`）
- **Capability Module**: `delivery`
- **Product owner**: `src/novelforge/application/services/export.py::ExportService.delivery_snapshots`

## Purpose

回答"这本书交付过几次、最近一次是哪份"，并给出快照 id 供审计与下载。

## Use when

- 交付前确认历史（避免重复交付 / 便于对比）。
- 交付后回溯。

## Do not use when

- 需要单个快照内容 → `inspect-delivery-manifest`。

## Preconditions

```text
novel_id 已知；只读
```

## Required inputs

| 输入 | 必填 | 说明 |
| --- | --- | --- |
| `novel_id` | 是 | 目标作品 |

## Authoritative interfaces

```text
UI           「交付」列表（总览里也显示最近一次）
REST         GET /api/story-builder/delivery/snapshots?novel_id=
Application  ExportService.delivery_snapshots()
MCP          resource novelforge://novels/{novel_id}/delivery（分页）
```

## Procedure

```text
1 GET /delivery/snapshots?novel_id=<id>
2 对每行读 snapshot_id / created_at / formats / selection_mode / profile / status / manifest_id
3 交叉核对 /studio/overview 的 delivery.{snapshots,last}
4 next：inspect-delivery-manifest（选定某个快照）
```

## Expected result

```json
{"novel_id":"novel_alpha","snapshots":[
  {"snapshot_id":"ds_…","created_at":"…","formats":["json","markdown"],
   "selection_mode":"accepted","profile":"author","manifest_id":"dm_…"}]}
```

## Verification

```text
· 列表只含本作品快照（跨作品隔离）
· 数量与 /studio/overview.delivery.snapshots 一致
· 每个 snapshot 都能取到 manifest（无孤儿快照）
```

## Common failures

| 现象 | 原因 | 处理 |
| --- | --- | --- |
| 列表为空 | 还没交付过 | `validate-delivery` → `deliver-blueprint` |
| 与总览计数不一致 | 交付中途失败 / 手工删文件 | 记录到 GAPS，重新交付 |

## Safety / invariants

```text
只读；不清理、不改写历史交付物
已发布的快照是审计凭据：不要删除文件来"重做"
```

## Side effects

无。

## Related skills

`inspect-delivery-manifest`、`download-delivery-artifact`、`deliver-blueprint`

## Source references

```text
src/novelforge/application/services/export.py
src/novelforge/api/delivery_routes.py::list_snapshots
src/novelforge/interfaces/mcp/resources/delivery.py
tests/delivery/test_delivery_service.py
```
