---
name: novelforge-v4.0.1.canon.rebuild-canon
description: 受控重建 Canon DB（operator 操作）：从 state / content pack / profile 重新引导，失败保留原 DB。
---

# rebuild-canon

- **Skill ID**: `novelforge-v4.0.1.canon.rebuild-canon`
- **Version**: 1（baseline `V4.0.1`）
- **Capability Module**: `canon`
- **Product owner**: `src/novelforge/story_engine/canon/bootstrap.py::CanonBootstrap.rebuild`

## Purpose

当 Canon DB 缺失 / 需要从既有 state / 内容包重新引导时，用一条受控路径重建，
而不是手工拼 SQL。

## Use when

- 新环境 / 迁移后 Canon DB 需要重建（operator 场景）。
- 已在别处确认 state / content pack / profile 是权威输入。

## Do not use when

- 想"修正"某条事实 → 不是重建能解决的问题（属作者决定）。
- 不确定输入是否权威 → 先 `inspect-canon-truth` + 与作者确认，不要重建。

## Preconditions

```text
作者 / operator 明确要求重建，并确认 state / content_pack / profile 输入
Canon 属受保护边界：这是一次显式的 production mutation
```

## Required inputs

| 输入 | 必填 | 说明 |
| --- | --- | --- |
| `novel_id` | 是 | 目标作品 |
| `state` | 否 | StoryState payload（缺省用现有） |
| `content_pack` | 否 | 内容包 payload |
| `profile` | 否 | 作品档案 payload |

## Authoritative interfaces

```text
UI           N/A
REST         POST /api/story-builder/canon/rebuild?novel_id=<id>
             （novel_id 是 **query 参数**；放在 body 里会 422 extra_forbidden）
Application  CanonBootstrap(repository).rebuild(novel_id, state=…, content_pack=…, profile=…)
MCP          N/A
```

## Procedure

```text
1 先备份 / 记录当前 canon db 路径（persistence.paths.canon_db_path）
2 先只读检查现状：GET /canon/validate（记录 before 状态作为对照）
3 POST /canon/rebuild?novel_id=<id> {state?, content_pack?, profile?}
4 读返回（重建结果摘要）
5 复验：GET /canon/validate 与 GET /canon/facts 与预期一致
6 与作者确认 before / after 差异（重建会改变 Canon 内容）
```

## Expected result

重建结果摘要（重建后的 Canon 记录集）；失败时返回 422 `REBUILD_FAILED` 且**保留原 DB**。

## Verification

```text
· 成功：/canon/validate 返回可解释结果；facts / events 可按 novel_id 查询
· 失败：原 DB 未被破坏（仍可 GET /canon/facts）
· 重建不触碰其它作品（novel_id 作用域隔离）
```

## Common failures

| 现象 | 原因 | 处理 |
| --- | --- | --- |
| 422 `REBUILD_FAILED` | 输入不合法 / 引导失败 | 读 message，修正输入；原 DB 仍在 |
| 重建后事实变少 | 输入 state / pack 不完整 | 与作者确认权威输入，必要时重做 |

## Safety / invariants

```text
destructive：属于受保护边界，必须 operator / 作者显式发起（Agent 不得自动执行）
scope：仅指定 novel_id
rollback：失败保留原 DB；成功后如需回退，请从备份恢复（不要手工改 SQL）
不得借此修改 frozen Repair Contract / Gate / truth precedence
```

## Side effects

重写该作品的 Canon DB（production mutation）。

## Related skills

`inspect-canon-truth`、`validate-canon-integrity`

## Source references

```text
src/novelforge/story_engine/canon/bootstrap.py
src/novelforge/api/canon_routes.py::rebuild_canon
tests/test_canon_bootstrap_api.py
```
