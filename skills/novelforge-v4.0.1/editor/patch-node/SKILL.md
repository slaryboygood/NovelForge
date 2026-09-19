---
name: novelforge-v4.0.1.editor.patch-node
description: 对 Blueprint 节点做字段级手工修改（patch），产生新 revision，受保护字段一律拒绝。
---

# patch-node

- **Skill ID**: `novelforge-v4.0.1.editor.patch-node`
- **Version**: 1（baseline `V4.0.1`）
- **Capability Module**: `editor`
- **Product owner**: `src/novelforge/editor/patch.py` +
  `src/novelforge/application/services/editor.py::EditorService.patch`

## Purpose

让作者精确改一个字段（而不是重生成整节点），并且让每次改动都留下可追溯的 revision。

## Use when

- 生成结果大体可用，只有某几处措辞 / 目标需要调整。
- 修复预览显示某问题更适合手工改。

## Do not use when

- 需要整节点重做 → `regenerate`（generation 模块）。
- 想改 `parent_id` / `sequence` / `status` → 结构关系与生命周期有专门契约，patch 会拒绝。

## Preconditions

```text
node_id 存在；已读当前 revision（inspect-node）与 editable_fields
```

## Required inputs

| 输入 | 必填 | 说明 |
| --- | --- | --- |
| `novel_id` | 是 | 目标作品 |
| `node_id` | 是 | 目标节点 |
| `changes` | 是 | 字段字典（只能含 payload 白名单字段） |
| `expected_revision` | 强烈建议 | 并发保护 |
| `reason` | 否 | 审计原因（≤400） |
| `idempotency_key` | 否 | 重试保护 |
| `dry_run` | 否 | true 时只校验、不写入 |

## Authoritative interfaces

```text
UI           节点抽屉编辑
REST         PATCH /api/story-builder/editor/nodes/{node_id}
             body {"novel_id","changes":{…},"expected_revision","reason","idempotency_key","dry_run"}
Application  EditorService.patch(node_id, changes, expected_revision=…, reason=…, dry_run=…)
MCP          tool patch_blueprint_node（支持 dry_run）
```

## Procedure

```text
1 inspect-node → 记下 revision 与 editable_fields
2 判断要改的字段是否在 editable_fields（不在 → 换用 rewrite / move / restore / accept）
3 建议先 dry_run=true 验证：changes 合法、无受保护字段
4 dry_run=false 执行：带 expected_revision + reason + idempotency_key
5 读返回：before_revision / revision / changed_fields / diff / impact / quality_status
6 确认 quality_status == unevaluated（编辑后需要重新评估）
7 next：evaluate-blueprint（重新评估）或 accept-revision（内容已满意）
```

## Expected result

```json
{"node_id":"ch_003","status":"edited","before_revision":2,"revision":3,
 "changed_fields":["goal"],"quality_status":"unevaluated","dry_run":false,
 "diff":{"revision_before":2,"revision_after":3,"field_changes":[{"field":"goal","kind":"changed"}]},
 "impact":{"dependent_nodes":["sc_003_1"],"quality_invalidations":["Q6"]}}
```

## Verification

```text
· revision == before_revision + 1；status == proposed；quality_status == unevaluated
· 只有 changes 里的字段发生变化（diff.changed_fields 与之一致）
· 历史 revision 仍可读（inspect-revisions 包含旧版本）
· 其它节点 revision 未变（最小影响）
```

## Common failures

| 现象 | 原因 | 处理 |
| --- | --- | --- |
| 409 `EDITOR_REVISION_CONFLICT` | expected_revision 过期 | 重新读 revision 后重试 |
| 409 `EDITOR_PRESERVE_VIOLATION` | 改了受保护字段 | 只改 payload 字段；结构改动走专门契约 |
| 422 `EDITOR_VALIDATION_FAILED` | 未知字段 / 类型不合法 | 查 editable_fields 与 payload schema |
| 422 `EDITOR_OPERATION_REJECTED` | 业务规则拒绝该改动 | 读 notes，通常是结构自洽问题 |

## Safety / invariants

```text
append-only：不覆盖历史；不直接写节点文件
编辑不等于评估：新 revision 的 quality_status 回到 unevaluated
不要为了通过校验改结构 identity（那是绕过契约）
```

## Side effects

写 Blueprint 新 revision + editor operation 审计记录。

## Related skills

`inspect-node`、`rewrite-node`、`diff-revisions`、`accept-revision`、
`novelforge-v4.0.1.quality.evaluate-blueprint`

## Source references

```text
src/novelforge/editor/patch.py（PROTECTED_FIELDS / editable_fields / build_edited_node）
src/novelforge/api/editor_routes.py::patch_node
src/novelforge/application/services/editor.py::patch
tests/editor/test_manual_edit.py、tests/editor/test_preserve.py
docs/v4/V4_EDITOR_CONTRACT.md §3
```
