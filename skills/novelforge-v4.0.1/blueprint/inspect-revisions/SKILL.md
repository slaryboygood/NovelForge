---
name: novelforge-v4.0.1.blueprint.inspect-revisions
description: 读取某个 Blueprint 节点的 revision 历史、评审记录与 editor operation，理解它怎么走到现在。
---

# inspect-revisions

- **Skill ID**: `novelforge-v4.0.1.blueprint.inspect-revisions`
- **Version**: 1（baseline `V4.0.1`）
- **Capability Module**: `blueprint`
- **Product owner**: `src/novelforge/application/services/editor.py::EditorService.get_history`

## Purpose

回答「这个节点被谁、因为什么改过几次」，并给出 `operations`（editor 审计）与
`reviews`（作者接受 / 拒绝决定）证据。

## Use when

- 恢复历史之前（`restore-revision`）。
- 理解为什么 `quality_status` 与当前 revision 不匹配。
- 审计：谁在哪个 revision 上做了 accept / reject。

## Do not use when

- 需要字段级差异 → `diff-revisions`。

## Preconditions

```text
novel_id + node_id 已知；只读
```

## Required inputs

| 输入 | 必填 | 说明 |
| --- | --- | --- |
| `novel_id` | 是 | 目标作品 |
| `node_id` | 是 | 目标节点 |

## Authoritative interfaces

```text
UI           节点抽屉「历史」
REST         GET /api/story-builder/editor/nodes/{node_id}/revisions?novel_id=
Application  EditorService.get_history(node_id)（内含 revisions / operations / reviews）
MCP          resource .../blueprint/nodes/{node_id}/revisions/{revision}、
             resource .../review
```

## Procedure

```text
1 GET /editor/nodes/{node_id}/revisions?novel_id=<id>
2 读 current_revision / revision_count / revisions[]（每条：revision / status / author /
  operation / created_at / changed_fields / review_status / summary）
3 读 operations[]（patch / rewrite / repair / restore 的审计行）
4 读 quality（若有）与 repair_preview（若有）
5 next：diff-revisions（比较两版）/ restore-revision（把旧内容写成新 revision）
```

## Expected result

```json
{"node_id":"ch_003","current_revision":3,"revision_count":3,
 "revisions":[{"revision":3,"status":"proposed","author":"author","operation":"patch",
               "changed_fields":["goal"],"review_status":"none"}],
 "operations":[{"operation":"patch","revision":3,"reason":"…"}],
 "quality":{…},"repair_preview":null}
```

## Verification

```text
· revision_count == len(revisions)；current_revision 是最大值
· 最新 revision 的 status 与 inspect-node 一致
· 被 accept 过的 revision 在 reviews / review_status 里能找到对应记录
```

## Common failures

| 现象 | 原因 | 处理 |
| --- | --- | --- |
| 404 | node_id 不存在 | 用 `inspect-blueprint` 取 id |
| revisions 里缺 v1 | 读错作品（跨作品隔离） | 检查 novel_id |
| review_status 全为 none | 还没 accept / reject 过 | 这是正常状态 |

## Safety / invariants

```text
只读；历史不可改写（append-only）
rejection 不是 lifecycle 状态，只在 review 记录里（ADR-021 / §3.2）
```

## Side effects

无。

## Related skills

`inspect-node`、`novelforge-v4.0.1.editor.diff-revisions`、
`novelforge-v4.0.1.editor.restore-revision`

## Source references

```text
src/novelforge/api/editor_routes.py
src/novelforge/application/services/editor.py
src/novelforge/editor/history.py
tests/editor/test_revision_history.py
docs/v4/V4_EDITOR_CONTRACT.md §4
```
