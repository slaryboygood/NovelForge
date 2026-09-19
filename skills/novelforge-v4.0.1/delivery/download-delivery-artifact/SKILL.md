---
name: novelforge-v4.0.1.delivery.download-delivery-artifact
description: 下载某次交付中已登记的 artifact（json / markdown / docx / nfpack / 插件格式）。
---

# download-delivery-artifact

- **Skill ID**: `novelforge-v4.0.1.delivery.download-delivery-artifact`
- **Version**: 1（baseline `V4.0.1`）
- **Capability Module**: `delivery`
- **Product owner**: `src/novelforge/application/services/export.py::ExportService.delivery_artifact`

## Purpose

取回交付物本身（不是重新生成），并保证取到的是 snapshot 里登记的那份。

## Use when

- 作者 / 客户端要拿到文件。
- 需要把 artifact 交给外部流程（例如转 EPUB，由未来插件承担）。

## Do not use when

- 需要重新生成交付 → `deliver-blueprint`（会产生新快照，不等于修订旧文件）。

## Preconditions

```text
snapshot_id + artifact_path 已知（inspect-delivery-manifest 提供）
```

## Required inputs

| 输入 | 必填 | 说明 |
| --- | --- | --- |
| `novel_id` | 是 | 目标作品 |
| `snapshot_id` | 是 | 目标快照 |
| `artifact_path` | 是 | manifest 里登记的相对路径 |

## Authoritative interfaces

```text
UI           「下载」（deliveryArtifactUrl）
REST         GET /api/story-builder/delivery/{snapshot_id}/artifacts/{artifact_path}?novel_id=
Application  ExportService.delivery_artifact(snapshot_id, relative_path) → bytes
MCP          resource .../delivery/{snapshot_id}/artifacts/{artifact_path}
```

## Procedure

```text
1 inspect-delivery-manifest → 取 artifacts[].path（不要自己拼路径）
2 GET /delivery/{snapshot_id}/artifacts/<path>?novel_id=<id>
3 检查响应 Content-Type 与 manifest 的 mime_type 一致、Content-Disposition 文件名正确
4 校验文件大小 / checksum 与 manifest 一致
5 next：交付完成；若要新版本 → 改内容 → 重新 validate → 重新 deliver
```

## Expected result

二进制 / 文本响应（json / md / docx / nfpack），文件名取自 artifact path。

## Verification

```text
· 返回字节数与 manifest.size 一致
· MIME 与 manifest.mime_type 一致
· 非法路径（../、绝对路径、盘符）被拒绝
```

## Common failures

| 现象 | 原因 | 处理 |
| --- | --- | --- |
| 404 | snapshot / artifact 不存在 | 用 manifest 重新取路径 |
| 403 | artifact 属于其它作品 | 统一 novel_id |
| 文件损坏 | 手工改过磁盘文件 | 重新交付 |

## Safety / invariants

```text
只读已登记 artifact；不接受任意路径
不修改交付物（要新版本就重新交付）
```

## Side effects

无（除客户端落盘）。

## Related skills

`inspect-delivery-manifest`、`deliver-blueprint`

## Source references

```text
src/novelforge/api/delivery_routes.py::get_artifact
src/novelforge/application/services/export.py::delivery_artifact
tests/delivery/test_export_facade_and_api.py
docs/v4/V4_DELIVERY_CONTRACT.md §12
```
