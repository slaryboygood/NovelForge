---
name: novelforge-v4.0.1.canon.inspect-canon-truth
description: 只读查看 Canon 事实 / 事件 / 实体 / 知识 / 伏笔，确认"哪些已经发生、哪些只是 planned"。
---

# inspect-canon-truth

- **Skill ID**: `novelforge-v4.0.1.canon.inspect-canon-truth`
- **Version**: 1（baseline `V4.0.1`）
- **Capability Module**: `canon`
- **Product owner**: `src/novelforge/story_engine/canon/repository.py::CanonRepository`

## Purpose

区分 **planned**（规划）与 **happened / occurred**（已发生）。这是所有"AI 不能倒灌事实"
判断的证据来源。

## Use when

- 需要确认某设定是否已经是事实。
- 排查 Q2（Canon）issue 时提供依据。

## Do not use when

- 想改 Canon → 不允许（需要作者审批边界）。
- 想查故事状态 → `story-state/inspect-story-state`。

## Preconditions

```text
novel_id 已知；canon db 存在（否则返回空列表而不是报错）
```

## Required inputs

| 输入 | 必填 | 默认 | 说明 |
| --- | --- | --- | --- |
| `novel_id` | 否 | `novel_project` | 目标作品（显式传递更安全） |
| `status` / `role` | 否 | 全部 | facts.status（planned/happened）、events.role |
| `limit` / `offset` | 否 | 50 / 0 | 分页（1..500） |

## Authoritative interfaces

```text
UI           N/A（当前无 Canon 界面）
REST         GET /api/story-builder/canon/facts?novel_id=&status=&limit=&offset=
             GET /api/story-builder/canon/events?novel_id=&role=
             GET /api/story-builder/canon/entities?novel_id=
             GET /api/story-builder/canon/knowledge?novel_id=&holder_id=
             GET /api/story-builder/canon/foreshadows?novel_id=
Application  CanonRepository（canonical 模块，api 层直连）
MCP          N/A
```

## Procedure

```text
1 GET /canon/facts?novel_id=<id>&status=happened  → 已发生事实
2 GET /canon/events?novel_id=<id>                 → 事件（planned / occurred）
3 GET /canon/entities / knowledge / foreshadows   → 实体 / 谁知道什么 / 伏笔
4 对每条记录读 id / status / provenance / source refs
5 结论口径：planned ≠ 已发生；knowledge 是"谁知道"，不是"读者知道"
6 next：inspect-canon-graph（看依赖）或 validate-canon-integrity（看一致性）
```

## Expected result

```json
{"novel_id":"novel_alpha","total":12,
 "items":[{"fact_id":"FACT_ab12","status":"happened","canonical_description":"…",
           "immutable":true}]}
```

## Verification

```text
· total 与 items 长度关系符合分页约定（items = rows[offset:offset+limit]）
· happened 事实的 immutable 标记为真（V4 不得修改）
· 只读：调用后 canon db 内容不变
```

## Common failures

| 现象 | 原因 | 处理 |
| --- | --- | --- |
| 返回空 | 该书还没有 Canon / novel_id 写错 | 确认 novel_id（默认值与实际作品可能不同） |
| 想改一条 happened 事实 | 被设计禁止 | 用新事实 + SUPERSEDES（需要作者决定） |

## Safety / invariants

```text
只读；不得直接编辑 canon db / 文件
不得把 planned 当 occurred（PLANNING != OCCURRED TRUTH）
跨作品读取必须被隔离（novel_id 显式）
```

## Side effects

无。

## Related skills

`inspect-canon-graph`、`validate-canon-integrity`、
`novelforge-v4.0.1.story-state.inspect-story-state`

## Source references

```text
src/novelforge/api/canon_routes.py
src/novelforge/story_engine/canon/repository.py、models.py、service.py
src/novelforge/persistence/paths.py::canon_db_path
tests/test_canon_repository.py
```
