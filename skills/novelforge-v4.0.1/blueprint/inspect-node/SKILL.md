---
name: novelforge-v4.0.1.blueprint.inspect-node
description: 读取某个 Blueprint 节点的当前（或指定）revision，含可编辑字段、受保护字段与质量状态。
---

# inspect-node

- **Skill ID**: `novelforge-v4.0.1.blueprint.inspect-node`
- **Version**: 1（baseline `V4.0.1`）
- **Capability Module**: `blueprint`
- **Product owner**: `src/novelforge/application/services/editor.py::EditorService.get_node`

## Purpose

在编辑之前确认：这一版节点长什么样、哪些字段能改、哪些字段被保护、质量问题是什么。

## Use when

- 准备 `patch-node` / `rewrite-node` / `accept-revision` 之前的必读步骤。
- 需要 `expected_revision` 的当前值。

## Do not use when

- 只想看整本书的清单 → `inspect-blueprint`。

## Preconditions

```text
novel_id + node_id 已知；node_id 可以来自 inspect-blueprint 的结果
```

## Required inputs

| 输入 | 必填 | 说明 |
| --- | --- | --- |
| `novel_id` | 是 | 目标作品 |
| `node_id` | 是 | 例如 `sc_001_2` / `ch_003` / `char_01_lin` |
| `revision` | 否 | 缺省 = 当前 revision |

## Authoritative interfaces

```text
UI           节点抽屉（NodeDrawer）
REST         GET /api/story-builder/editor/nodes/{node_id}?novel_id=&revision=
Application  EditorService.get_node(node_id, revision)
MCP          resource novelforge://novels/{novel_id}/blueprint/nodes/{node_id}
```

## Procedure

```text
1 resolve node_id（inspect-blueprint → 选行）
2 GET /editor/nodes/{node_id}?novel_id=<id>[&revision=<n>]
3 读 node.revision（后续 mutation 的 expected_revision）
4 读 editable_fields / protected_fields（patch 只能动前者）
5 读 quality_status / quality.issues / quality.blocking_codes
6 next：patch-node / rewrite-node / accept-revision / 或先 plan-repair
```

## Expected result

```json
{"novel_id":"novel_alpha",
 "node":{"node_id":"ch_003","node_type":"chapter","revision":2,"status":"proposed",
         "payload":{"title":"…","goal":"…"},"visible":{"title":"…"}},
 "editable_fields":["title","goal","conflict","turn","outcome","hook","location"],
 "protected_fields":["node_id","novel_id","node_type","parent_id","sequence","status",…],
 "quality_status":"passed_with_issues",
 "quality":{"issues":[…],"blocking_codes":[]}}
```

## Verification

```text
· 返回 node.revision 与 /editor/nodes/{id}/revisions 的 current_revision 一致
· editable_fields ∩ protected_fields == ∅
· 跨作品访问（novel_id 与节点归属不一致）→ 404 / 403，不返回内容
```

## Common failures

| 现象 | 原因 | 处理 |
| --- | --- | --- |
| 404 `EDITOR_NODE_NOT_FOUND` | node_id 不存在或属于别的作品 | 用 `inspect-blueprint` 重新取 id |
| quality 字段为空 | 还没评估过 | `evaluate-blueprint` |
| `revision` 参数过期 | 节点已被再次修改 | 重新读取后再写 |

## Safety / invariants

```text
只读；不修改 payload / status / 质量
不要手工改节点落盘文件来"看效果"（revision 链会断裂）
```

## Side effects

无。

## Related skills

`inspect-blueprint`、`inspect-revisions`、`novelforge-v4.0.1.editor.patch-node`、
`novelforge-v4.0.1.editor.rewrite-node`、`novelforge-v4.0.1.repair.plan-repair`

## Source references

```text
src/novelforge/api/editor_routes.py
src/novelforge/application/services/editor.py
src/novelforge/editor/patch.py（PROTECTED_FIELDS / editable_fields）
tests/editor/test_manual_edit.py
```
