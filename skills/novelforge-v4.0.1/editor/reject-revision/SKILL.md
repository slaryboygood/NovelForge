---
name: novelforge-v4.0.1.editor.reject-revision
description: 记录作者对某个 revision 的拒绝决定（只写 review 记录，不改变节点内容与 lifecycle 状态）。
---

# reject-revision

- **Skill ID**: `novelforge-v4.0.1.editor.reject-revision`
- **Version**: 1（baseline `V4.0.1`）
- **Capability Module**: `editor`
- **Product owner**: `src/novelforge/application/services/editor.py::EditorService.reject`

## Purpose

让"不接受这一版"成为一个可审计的事实，而不是靠沉默表达。

## Use when

- 某个生成的 revision 不合格，作者决定不要。
- 想撤销之前的 accept 决定（记录拒绝）。

## Do not use when

- 想删除历史 revision → 不可能（append-only）。
- 想回到旧内容 → `restore-revision`。

## Preconditions

```text
node_id + 被拒 revision 已知
```

## Required inputs

| 输入 | 必填 | 说明 |
| --- | --- | --- |
| `novel_id` | 是 | 目标作品 |
| `node_id` | 是 | 目标节点 |
| `revision` | 否 | 被拒 revision（缺省 = 当前） |
| `reason` | 建议 | 拒绝原因（写进 review） |

## Authoritative interfaces

```text
UI           节点抽屉「拒绝」
REST         POST /api/story-builder/editor/nodes/{node_id}/reject
Application  EditorService.reject(node_id, revision=…, reason=…)
MCP          tool reject_revision
```

## Procedure

```text
1 inspect-node / inspect-revisions 确认要拒绝的 revision
2 POST /reject {novel_id, node_id, revision, reason}
3 读返回 decision="rejected" 与 review_note
4 复验：节点内容与 revision 号不变；review_status 记录为 rejected
5 next：改内容（patch / rewrite / regenerate），再重新评估与接受
```

## Expected result

```json
{"node_id":"ch_003","decision":"rejected","reviewed_revision":3,"revision":3,
 "status":"proposed","review_note":"…"}
```

## Verification

```text
· revision 号没有增加（拒绝不写内容）
· node.status 不是 "rejected"（lifecycle 没有该状态）
· resource .../review 中能看到该拒绝记录
```

## Common failures

| 现象 | 原因 | 处理 |
| --- | --- | --- |
| 以为拒绝会回滚内容 | 语义误解 | 内容不变；要回滚用 restore |
| 没有 review 记录 | 用了别的接口（例如直接改 status） | 只通过 reject 接口记录决定 |

## Safety / invariants

```text
REJECTION_IS_METADATA：不改变内容、不改变 lifecycle enum（ADR-021 / §3.2）
不删除历史 revision
```

## Side effects

写 editor review 记录。

## Related skills

`accept-revision`、`restore-revision`、`inspect-revisions`

## Source references

```text
src/novelforge/application/services/editor.py::reject
src/novelforge/editor/operations.py
tests/editor/test_accept_reject.py
docs/v4/V4_EDITOR_CONTRACT.md §7
```
