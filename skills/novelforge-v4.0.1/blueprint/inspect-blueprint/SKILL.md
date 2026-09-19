---
name: novelforge-v4.0.1.blueprint.inspect-blueprint
description: 读取某本作品的 Story Blueprint 有序节点视图（visible 字段 + 状态 + 质量摘要）。
---

# inspect-blueprint

- **Skill ID**: `novelforge-v4.0.1.blueprint.inspect-blueprint`
- **Version**: 1（baseline `V4.0.1`）
- **Capability Module**: `blueprint`
- **Product owner**: `src/novelforge/blueprint/repository.py` +
  `src/novelforge/application/services/export.py::ExportService.blueprint_view`

## Purpose

用唯一顺序（node_type order → parent → sequence → node_id）读出这本书的计划真相：
有哪些节点、属于谁、什么状态、什么质量。

## Use when

- 需要节点清单（按类型过滤，例如只看章节 / 场景 / 人物）。
- 需要一个可对比的 `digest`（revision 级一致性证据）。

## Do not use when

- 需要单节点可编辑字段 → `inspect-node`。
- 需要交付表示（Markdown / DOCX 内容）→ `deliver-blueprint`。

## Preconditions

```text
novel_id 已确认；只读
```

## Required inputs

| 输入 | 必填 | 默认 | 说明 |
| --- | --- | --- | --- |
| `novel_id` | 是 | — | 目标作品 |
| `node_type` | 否 | 全部 | 12 类节点之一（`scene` 等价于场景卡视图） |
| `mode` | 否 | `current` | `accepted` / `current` / `explicit_revisions` |

## Authoritative interfaces

```text
UI           「世界 / 人物 / 故事 / 场景」页
REST         GET /api/story-builder/studio/blueprint?novel_id=&node_type=&mode=
Application  ExportService.blueprint_view()（→ DeliveryService.machine_representation）
MCP          resources novelforge://novels/{novel_id}/blueprint、.../scenes（分页 limit/cursor）
```

## Procedure

```text
1 call GET /studio/blueprint?novel_id=<id>[&node_type=scene][&mode=accepted]
2 读 ordering（唯一类型顺序）与 count
3 对每个 node 读 node_id / node_type / revision / status / visible / review_status / quality
4 需要与总览对齐时比较 digest 与 /studio/overview 的 blueprint.digest
5 需要过滤 accepted：mode=accepted（未 accepted 的节点会出现在 excluded）
6 next：inspect-node（看某节点可编辑字段）/ evaluate-blueprint（跑质量）
```

## Expected result

```json
{"novel_id":"novel_alpha","selection_mode":"current","node_type":"scene","count":7,
 "nodes":[{"node_id":"sc_001_1","node_type":"scene","revision":1,"status":"proposed",
           "visible":{"scene_purpose":"…","conflict":"…"},"quality":{"status":"unevaluated"}}],
 "excluded":[],"read_only":true}
```

## Verification

```text
· count == len(nodes)；ordering 顺序稳定（同输入同输出）
· 每个 node 的 visible 字段属于该类型的 VISIBLE_FIELDS
· 同 mode 下 digest 与 /studio/overview 一致
```

## Common failures

| 现象 | 原因 | 处理 |
| --- | --- | --- |
| count = 0 | 还没生成任何节点 | `generate-premise` |
| 节点都在 `excluded` | mode=accepted 但还没 accept | `accept-revision` 或改用 mode=current |
| 400 `STUDIO_VALIDATION_FAILED` | novel_id 过短 / node_type 非法 | 用 12 类之一，并确认 novel_id |

## Safety / invariants

```text
只读；不产生 revision、不调用模型
Blueprint 是计划，不是已发生事实；不要把节点当 Canon 引用
```

## Side effects

无。

## Related skills

`inspect-node`、`inspect-scene-cards`、`understand-blueprint-model`、
`novelforge-v4.0.1.quality.evaluate-blueprint`

## Source references

```text
src/novelforge/api/studio_routes.py::blueprint
src/novelforge/application/services/export.py::blueprint_view
src/novelforge/delivery/compiler.py（NODE_TYPE_ORDER / VISIBLE_FIELDS）
tests/studio/test_studio_api.py
docs/v4/V4_BLUEPRINT_CONTRACT.md
```
