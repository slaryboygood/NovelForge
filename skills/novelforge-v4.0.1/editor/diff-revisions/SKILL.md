---
name: novelforge-v4.0.1.editor.diff-revisions
description: 结构化比较同一节点的两个 revision（字段级 + 列表级），并给出质量 issue 变化。
---

# diff-revisions

- **Skill ID**: `novelforge-v4.0.1.editor.diff-revisions`
- **Version**: 1（baseline `V4.0.1`）
- **Capability Module**: `editor`
- **Product owner**: `src/novelforge/editor/diff.py` +
  `src/novelforge/application/services/editor.py::EditorService.diff`

## Purpose

回答"这次改动到底改了什么"，并且把结果的确定性与模型调用解耦（零模型、可复现）。

## Use when

- 检查 patch / rewrite / repair / restore 的结果。
- 比较两个 accept 候选，决定保留哪一版。

## Do not use when

- 只需要当前内容 → `inspect-node`。

## Preconditions

```text
node_id 存在；from_revision 合法
```

## Required inputs

| 输入 | 必填 | 说明 |
| --- | --- | --- |
| `novel_id` | 是 | 目标作品 |
| `node_id` | 是 | 目标节点 |
| `from_revision` | 是 | 比较起点 |
| `to_revision` | 否 | 缺省 = 当前 revision |

## Authoritative interfaces

```text
UI           节点抽屉 diff
REST         GET /api/story-builder/editor/nodes/{node_id}/diff?novel_id=&from_revision=&to_revision=
Application  EditorService.diff(node_id, from_revision=…, to_revision=…)
MCP          tool diff_revisions（read-only）
```

## Procedure

```text
1 决定 from_revision / to_revision（inspect-revisions）
2 GET /diff?novel_id=<id>&node_id=<id>&from_revision=2&to_revision=3
3 读 field_changes[]（field / kind / before / after）与 list_changes[]（added / removed）
4 读 unchanged_fields / status_before / status_after / quality_status_before / after
5 读 quality.{before_issue_ids, after_issue_ids, resolved_issue_ids, new_issue_ids}
6 next：满意 → accept-revision；变差 → restore-revision；仍有问题 → plan-repair
```

## Expected result

```json
{"node_id":"sc_003_2","revision_before":2,"revision_after":3,
 "field_changes":[{"field":"turn","kind":"changed","before":"…","after":"…"}],
 "list_changes":[],"unchanged_fields":["location","time"],
 "quality":{"resolved_issue_ids":["qi_…"],"new_issue_ids":[]},"digest":"…"}
```

## Verification

```text
· 同一对 revision 多次调用结果一致（deterministic，零模型）
· field_changes 与 inspect-revisions 里记录的 changed_fields 一致
· 变更字段不包含被保护字段（若包含说明有越权写入）
```

## Common failures

| 现象 | 原因 | 处理 |
| --- | --- | --- |
| 404 | revision 不存在 | 检查 from/to 值 |
| 与自己比较为空 | from == to | 选不同 revision |
| 期望看到正文差异 | diff 只针对 Blueprint payload | 正文不在 V4 Core 范围 |

## Safety / invariants

```text
只读、零模型、确定性
不做业务判断（"哪版更好"是作者决定）
```

## Side effects

无。

## Related skills

`inspect-revisions`、`accept-revision`、`restore-revision`

## Source references

```text
src/novelforge/editor/diff.py
src/novelforge/api/editor_routes.py::get_diff
src/novelforge/interfaces/mcp/tools/editor.py（diff_revisions）
tests/editor/test_diff.py
docs/v4/V4_EDITOR_CONTRACT.md §5
```
