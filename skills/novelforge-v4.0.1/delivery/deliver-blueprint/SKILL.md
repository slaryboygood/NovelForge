---
name: novelforge-v4.0.1.delivery.deliver-blueprint
description: 执行一次正式交付：preflight → revision 钉住 → 编译导出 → manifest/checksum → 原子发布。
---

# deliver-blueprint

- **Skill ID**: `novelforge-v4.0.1.delivery.deliver-blueprint`
- **Version**: 1（baseline `V4.0.1`）
- **Capability Module**: `delivery`
- **Product owner**: `src/novelforge/application/services/export.py::ExportService.deliver` +
  `src/novelforge/delivery/service.py::DeliveryService`

## Purpose

一条命令得到可下载的交付物（默认 accepted + author profile），并把它记录为可审计快照。
支持 JSON / Markdown / DOCX / `.nfpack`（以及插件 exporter 格式）。

## Use when

- 作者要把成果导出给别人看 / 存档。
- 需要 `.nfpack` 打包（含 manifest 与选中节点文件）。

## Do not use when

- 只是想看内容 → `inspect-blueprint`（不要用交付绕过质量）。
- 还没 accept / 质量未过 → 先 `validate-delivery` 看 blocking_reason。

## Preconditions

```text
preflight 通过（或作者显式放宽 policy 并承担后果）
formats 来自 GET /studio/delivery/formats
```

## Required inputs

| 输入 | 必填 | 默认 | 说明 |
| --- | --- | --- | --- |
| `novel_id` | 是 | — | 目标作品 |
| `formats` | 否 | `["json","markdown"]` | 可含 `docx` / `nfpack` |
| `selection_mode` | 否 | `accepted` | 建议保持 accepted |
| `profile` | 否 | `author` | reader / author / machine / audit |
| `dry_run` | 否 | false | true = 只预检 |
| `idempotency_key` | 建议 | — | 重试保护 |

## Authoritative interfaces

```text
UI           「交付」→ 交付 → 下载（deliveryArtifactUrl）
REST         POST /api/story-builder/delivery
Application  ExportService.deliver(selection, idempotency_key=…, dry_run=…)
MCP          tool deliver_blueprint（默认 accepted；支持 dry_run）
```

## Procedure

```text
1 GET /studio/delivery/formats → 确认可用格式（含插件 exporter owner_type）
2 validate-delivery（dry_run:true）
3 POST /delivery {novel_id, formats, selection_mode:"accepted", profile:"author",
  idempotency_key}
4 读 snapshot_id / manifest.artifacts[]（format / filename / size / checksum / mime_type）
5 复验：manifest.selected_revisions 与交付前 accepted 节点 revision 一致
6 next：download-delivery-artifact（每个格式一个 URL）
```

## Expected result

```json
{"status":"delivered","ok":true,"snapshot_id":"ds_…",
 "artifacts":[{"format":"docx","filename":"novel_alpha.docx","size":20480,
               "checksum":"…","mime_type":"application/vnd.openxmlformats-…",
               "exporter_id":"delivery.docx.v1","exporter_version":1}],
 "manifest":{"selected_revisions":{…},"formats":["docx"]},"idempotent":false}
```

## Verification

```text
· 每个 artifact 非空（size > 0）且 checksum 与文件内容一致
· Markdown / DOCX 里不出现 internal 字段（node_id / status / provenance）
· 未 accepted 节点不出现在交付物里（默认 policy）
· 同一 idempotency_key 重放 → 同一 snapshot（不重复导出）
```

## Common failures

| 现象 | 原因 | 处理 |
| --- | --- | --- |
| `DELIVERY_VALIDATION_FAILED` | 未 accepted / 质量 blocker | 修质量或 accept |
| 只有 docx 没有内容 | 节点 visible 字段为空 | 检查节点内容（不是模板占位） |
| 插件格式不可用 | 插件未启用 / 未批准 | 见 plugins 模块；不要绕过 Host |

## Safety / invariants

```text
revision-pinned + 原子发布 + secret scan
不导出未钉住状态；不因为方便改成 current
delivery 不调用模型、不修 issue、不改真相
```

## Side effects

写交付快照 / manifest / artifact 文件。

## Related skills

`validate-delivery`、`download-delivery-artifact`、`inspect-delivery-manifest`、
`novelforge-v4.0.1.workflows.prepare-final-delivery`

## Source references

```text
src/novelforge/delivery/service.py、exporters/*
src/novelforge/api/delivery_routes.py
src/novelforge/interfaces/mcp/tools/delivery.py
tests/delivery/test_exporters.py、tests/browser_v4_studio_golden.cjs
docs/v4/V4_DELIVERY_CONTRACT.md §1、§9–§11
```
