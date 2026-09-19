---
name: novelforge-v4.0.1.editor.rewrite-node
description: 对 Blueprint 节点做 AI 字段级改写：只允许改 target_fields，越界即整体拒绝写入。
---

# rewrite-node

- **Skill ID**: `novelforge-v4.0.1.editor.rewrite-node`
- **Version**: 1（baseline `V4.0.1`）
- **Capability Module**: `editor`
- **Product owner**: `src/novelforge/generation/rewrite.py` +
  `src/novelforge/application/services/editor.py::EditorService.rewrite`

## Purpose

在保留节点其它一切内容的前提下，用模型改进指定字段（例如"只重写 conflict 与 turn"）。

## Use when

- 某个字段需要更好的表达，但不想重生成整节点。
- 质量 issue 指向具体字段（allow_change 与 target_fields 对齐）。

## Do not use when

- 没配置模型 provider（会返回不可用错误，而不是静默降级）。
- 要改多个不同节点 → 逐个调用（一次一个节点）。

## Preconditions

```text
node_id 存在；provider enabled；revision 已确认
target_fields ⊂ 该节点类型的 payload 字段且不是结构 identity
```

## Required inputs

| 输入 | 必填 | 说明 |
| --- | --- | --- |
| `novel_id` | 是 | 目标作品 |
| `node_id` | 是 | 目标节点 |
| `target_fields` | 是 | 1..12 个字段 |
| `instruction` | 是 | 1..600 字，说明要改成什么样 |
| `preserve_fields` | 否 | 额外必须保持的字段 |
| `quality_issue_ids` | 否 | 关联的 issue（让改写有依据） |
| `expected_revision` | 强烈建议 | revision 冲突在模型调用前就会失败 |
| `dry_run` | 否 | true 时 0 model call / 0 revision（按契约语义） |

## Authoritative interfaces

```text
UI           节点抽屉「AI 改写」
REST         POST /api/story-builder/editor/nodes/{node_id}/rewrite
Application  EditorService.rewrite(node_id, target_fields, instruction, preserve_fields=…)
MCP          tool rewrite_blueprint_node
```

## Procedure

```text
1 inspect-node → 取 revision 与 editable_fields
2 选定 target_fields（尽量小范围）与 preserve_fields
3 POST /rewrite {novel_id, node_id, target_fields, instruction, preserve_fields,
  quality_issue_ids, expected_revision, idempotency_key}
4 读返回：target_fields / changed_fields / violations / revision / model
5 校验：changed_fields ⊆ target_fields；未授权字段未变
6 next：evaluate-blueprint（看是否解决 issue）或 accept-revision
```

## Expected result

```json
{"node_id":"sc_003_2","status":"rewritten","before_revision":2,"revision":3,
 "target_fields":["conflict","turn"],"changed_fields":["conflict","turn"],
 "violations":[],"quality_status":"unevaluated","model":"…"}
```

## Verification

```text
· changed_fields ⊆ target_fields（否则必须已失败且未写入）
· preserve 字段逐字不变
· 新 revision status == proposed、quality_status == unevaluated
· 同一 idempotency_key 重放不产生第二个 revision
```

## Common failures

| 现象 | 原因 | 处理 |
| --- | --- | --- |
| `EDITOR_PRESERVE_VIOLATION`（越界） | 模型改到未授权字段 | 不要放宽；缩小 target_fields 或改用手工 patch |
| 422 生成不可用 | provider 未启用 | 配置 provider |
| 409 `EDITOR_REVISION_CONFLICT` | revision 过期 | 重新读后再试 |
| 改写后 issue 依旧 | 指令不清 / 上下文不足 | 给更具体的 instruction 或改用手工 patch |

## Safety / invariants

```text
ONLY_TARGET_FIELDS_CHANGE：违反即拒绝写入（不写半个 revision）
proposal only：改写结果不会被自动接受
不改结构 identity、不写 Canon / StoryState
```

## Side effects

写 Blueprint 新 revision（+ 模型调用）。

## Related skills

`patch-node`、`diff-revisions`、`novelforge-v4.0.1.repair.plan-repair`

## Source references

```text
src/novelforge/generation/rewrite.py（assert_rewrite_allowed / changed_outside_target）
src/novelforge/generation/service.py::rewrite_fields
src/novelforge/api/editor_routes.py::rewrite_node
tests/editor/test_ai_rewrite.py
docs/v4/V4_EDITOR_CONTRACT.md §6
```
