---
name: novelforge-v4.0.1.editor.restore-revision
description: 把历史 revision 的内容恢复成一个新的 revision（历史不删除，带 restored_from 记录）。
---

# restore-revision

- **Skill ID**: `novelforge-v4.0.1.editor.restore-revision`
- **Version**: 1（baseline `V4.0.1`）
- **Capability Module**: `editor`
- **Product owner**: `src/novelforge/application/services/editor.py::EditorService.restore` +
  `src/novelforge/editor/history.py`

## Purpose

回退内容而不改写历史：把旧 revision 的内容作为**新** revision 写回，并记录来源。
（`undo` 等于 restore 到 parent_revision。）

## Use when

- 某次改动 / 修复让节点变差，要回到上一个好版本。
- 修复引入回归时的安全回退。

## Do not use when

- 想删除某个 revision → 不可能。
- 想恢复整本书 → 逐个节点处理（没有"整本回滚"接口）。

## Preconditions

```text
node_id 存在；from_revision 存在且 < 当前 revision（或至少是一个历史 revision）
```

## Required inputs

| 输入 | 必填 | 说明 |
| --- | --- | --- |
| `novel_id` | 是 | 目标作品 |
| `node_id` | 是 | 目标节点 |
| `from_revision` | 是 | 要恢复的历史 revision |
| `expected_revision` | 建议 | 并发保护 |
| `reason` | 建议 | 审计原因 |

## Authoritative interfaces

```text
UI           节点抽屉「恢复」
REST         POST /api/story-builder/editor/nodes/{node_id}/restore
Application  EditorService.restore(node_id, from_revision=…)
MCP          tool restore_revision
```

## Procedure

```text
1 inspect-revisions → 选 from_revision（并用 diff-revisions 确认差异）
2 POST /restore {novel_id, node_id, from_revision, expected_revision, reason}
3 读返回：restored_from / before_revision / revision / status / changed_fields
4 复验：新 revision 的 payload 与 from_revision 一致（除 revision / 时间等 metadata）
5 复验：新 revision status == proposed、quality_status == unevaluated
6 next：evaluate-blueprint → 需要时 accept-revision
```

## Expected result

```json
{"node_id":"sc_003_2","operation":"restore","restored_from":2,"before_revision":4,
 "revision":5,"status":"proposed","changed_fields":["conflict","turn"]}
```

## Verification

```text
· restored_from == 请求的 revision；revision == before_revision + 1
· diff(from_revision → 新 revision) 的 payload 差异为空（只有 metadata 变化）
· 历史 revision 仍可读（from_revision 仍在）
```

## Common failures

| 现象 | 原因 | 处理 |
| --- | --- | --- |
| 404 / 422 | from_revision 不存在 | 用 inspect-revisions 取合法值 |
| 409 冲突 | 期间有新写入 | 重新确认当前 revision |
| 想恢复后直接交付 | 新 revision 未 accepted | 重新 accept |

## Safety / invariants

```text
RESTORE_CREATES_NEW_REVISION：历史永不删除（ADR-023）
结构关系也要通过校验（恢复不能产生结构非法节点）
dry-run 不适用：本操作本身总是 append 一个 revision
```

## Side effects

写 Blueprint 新 revision（+ editor operation 记录）。

## Related skills

`inspect-revisions`、`diff-revisions`、`accept-revision`、`novelforge-v4.0.1.repair.verify-repair`

## Source references

```text
src/novelforge/editor/history.py
src/novelforge/application/services/editor.py::restore
src/novelforge/api/editor_routes.py::restore_node
tests/editor/test_restore.py
docs/v4/adr/ADR-023-restore-creates-a-new-revision.md
```
