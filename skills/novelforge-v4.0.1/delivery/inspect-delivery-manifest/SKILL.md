---
name: novelforge-v4.0.1.delivery.inspect-delivery-manifest
description: 读取某次交付的 manifest：钉住的 revision、artifact 清单、checksum 与格式版本。
---

# inspect-delivery-manifest

- **Skill ID**: `novelforge-v4.0.1.delivery.inspect-delivery-manifest`
- **Version**: 1（baseline `V4.0.1`）
- **Capability Module**: `delivery`
- **Product owner**: `src/novelforge/delivery/manifest.py` +
  `src/novelforge/application/services/export.py::ExportService.delivery_manifest`

## Purpose

回答"这份交付物到底是哪一版、包含什么、能不能验证"。

## Use when

- 交付后审计 / 复现。
- 需要确认某个 artifact 的格式版本（exporter id + version）。

## Do not use when

- 要下载文件 → `download-delivery-artifact`。

## Preconditions

```text
snapshot_id 已知（list-delivery-snapshots）
```

## Required inputs

| 输入 | 必填 | 说明 |
| --- | --- | --- |
| `novel_id` | 是 | 目标作品 |
| `snapshot_id` | 是 | 目标快照 |

## Authoritative interfaces

```text
UI           「交付」快照详情
REST         GET /api/story-builder/delivery/{snapshot_id}/manifest?novel_id=
Application  ExportService.delivery_manifest(snapshot_id)
MCP          resource novelforge://novels/{novel_id}/delivery/{snapshot_id}/manifest
```

## Procedure

```text
1 GET /delivery/snapshots?novel_id=<id> → 取 snapshot_id
2 GET /delivery/{snapshot_id}/manifest?novel_id=<id>
3 读 manifest_id / snapshot_id / selected_revisions / formats / profile / selection_mode
4 读 artifacts[]：format / filename / path / size / checksum / mime_type /
  exporter_id / exporter_version
5 把 checksum 与下载后的文件对比（复现性检查）
6 next：download-delivery-artifact
```

## Expected result

```json
{"manifest_id":"dm_…","snapshot_id":"ds_…","selection_mode":"accepted","profile":"author",
 "selected_revisions":{"ch_003":4},"formats":["json","markdown"],
 "artifacts":[{"format":"json","path":"…","size":3210,"checksum":"…",
               "exporter_id":"delivery.json.v1","exporter_version":1}]}
```

## Verification

```text
· selected_revisions 全为该作品的节点（无跨作品条目）
· 每个 artifact 的 checksum 与下载内容一致
· 只包含已登记路径（拒绝 ../ / 绝对路径 / 盘符）
```

## Common failures

| 现象 | 原因 | 处理 |
| --- | --- | --- |
| 404 | snapshot_id 不存在或属于别的作品 | 用 list 重新取 |
| checksum 不一致 | 文件被外部修改 | 重新交付（不要手改交付物） |

## Safety / invariants

```text
manifest 是交付的可复现凭据：不要手工编辑
artifact 只按登记路径读取（路径穿越被拒绝）
```

## Side effects

无。

## Related skills

`list-delivery-snapshots`、`download-delivery-artifact`

## Source references

```text
src/novelforge/delivery/manifest.py、store.py
src/novelforge/api/delivery_routes.py::get_manifest
tests/delivery/test_delivery_contracts.py
docs/v4/V4_DELIVERY_CONTRACT.md §10
```
