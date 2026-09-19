---
name: novelforge-v4.0.1.editor.accept-revision
description: 由作者接受某个节点 revision（status → accepted，产生新 revision）；质量通过不等于已接受。
---

# accept-revision

- **Skill ID**: `novelforge-v4.0.1.editor.accept-revision`
- **Version**: 1（baseline `V4.0.1`）
- **Capability Module**: `editor`
- **Product owner**: `src/novelforge/application/services/editor.py::EditorService.accept` +
  `src/novelforge/blueprint/lifecycle.py`

## Purpose

把作者的决定固化成 lifecycle 状态：只有 accepted 的节点才会进入默认交付选择。

## Use when

- 作者确认某个 revision 可以定稿。
- 交付前把需要的节点 accept。

## Do not use when

- 想让 Agent 自动接受 → **默认禁止**（Agent policy：`allow_auto_accept=false`；accept 是 protected action）。
- 质量未通过但想"先接受再说" → 需要作者明确决定并记录原因。

## Preconditions

```text
node_id + 目标 revision 已确认（inspect-node / inspect-revisions）
作者已就这个 revision 做出决定（这是 approval boundary）
```

## Required inputs

| 输入 | 必填 | 说明 |
| --- | --- | --- |
| `novel_id` | 是 | 目标作品 |
| `node_id` | 是 | 目标节点 |
| `revision` | 否 | 要接受的 revision（缺省 = 当前） |
| `expected_revision` | 否 | 并发保护（accept 有 concurrency 语义） |
| `reason` | 否 | 审计原因 |

## Authoritative interfaces

```text
UI           节点抽屉「接受」
REST         POST /api/story-builder/editor/nodes/{node_id}/accept
Application  EditorService.accept(node_id, revision=…, expected_revision=…, reason=…)
MCP          tool accept_revision
```

## Procedure

```text
1 确认要接受的 revision（inspect-revisions；避免接受了一个已被取代的版本）
2 记录该 revision 的质量状态（inspect-node）作为接受依据
3 POST /accept {novel_id, node_id, revision, expected_revision, reason}
4 读返回：decision="accepted" / reviewed_revision / revision / status / previous_status
   （注意：返回体里的 `status` 是**操作状态**（成功时 `"applied"`），不是节点 lifecycle；
    节点 lifecycle 要看 `GET /editor/nodes/{node_id}` 的 node.status == "accepted"）
5 复验：inspect-node 显示 status == accepted；inspect-blueprint?mode=accepted 包含该节点
6 next：其它节点同样处理，或 delivery.validate-delivery
```

## Expected result

```json
{"node_id":"ch_003","decision":"accepted","reviewed_revision":3,"revision":4,
 "status":"accepted","previous_status":"proposed","idempotent":false}
```

## Verification

```text
· status == accepted；review 记录里出现该 revision（resource .../review）
· 质量结论没有被"接受"改写（quality_status 仍是它自己的投影值）
· 重复 accept 同一 revision：不会产生第二个 revision，但**也不是** idempotent=true ——
  实际返回 422 EDITOR_OPERATION_REJECTED（"当前状态不允许接受：accepted"）。
  想再确认状态请用 `GET /editor/nodes/{node_id}`，不要把它当作幂等重放。
```

## Common failures

| 现象 | 原因 | 处理 |
| --- | --- | --- |
| 409 revision 冲突 | 期间有新的写入 | 重新查看当前 revision 并再次确认 |
| 接受后交付仍被拦 | 其它必需节点未 accepted 或质量未通过 | `inspect-quality-report` + 逐个 accept |
| 想撤销接受 | 用 `reject-revision`（记录决定）或 `restore-revision`（回到旧内容 + 新 revision） | 历史永久保留 |

## Safety / invariants

```text
accept 是作者决定（protected）：Agent / 自动化不得静默执行
accepted 不是质量冻结（ADR-022/ADR-025）：后续编辑仍会产生新 revision 并需要重新接受
不修改 payload 内容（accept 只改生命周期状态）
```

## Side effects

写 Blueprint 新 revision（状态流转）+ editor review 记录。

## Related skills

`reject-revision`、`restore-revision`、`novelforge-v4.0.1.delivery.validate-delivery`

## Source references

```text
src/novelforge/application/services/editor.py::accept
src/novelforge/blueprint/lifecycle.py
src/novelforge/interfaces/mcp/tools/editor.py
tests/editor/test_accept_reject.py
docs/v4/adr/ADR-022-quality-pass-does-not-mean-author-accepted.md
```
