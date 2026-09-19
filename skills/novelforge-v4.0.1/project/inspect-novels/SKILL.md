---
name: novelforge-v4.0.1.project.inspect-novels
description: 列出或读取 NovelForge V4.0.1 的作品档案，确认 novel_id 与当前进度，不做任何修改。
---

# inspect-novels

- **Skill ID**: `novelforge-v4.0.1.project.inspect-novels`
- **Version**: 1（baseline `V4.0.1`）
- **Capability Module**: `project`
- **Product owner**: `src/novelforge/application/services/project.py::ProjectService.list_novels/get_novel`

## Purpose

在动手之前确认「用哪个 novel_id、这本书现在有什么」。这是所有其它 skill 的
**resolve 步骤**（禁止猜当前作品）。

## Use when

- 需要确认 novel_id 是否存在 / 拼写正确。
- 需要看作品标题、题材、cast / factions 计数。
- Agent 在计划里需要先读只读快照。

## Do not use when

- 需要蓝图节点、质量、交付的细节 → `inspect-blueprint` / `inspect-quality-report` / `list-delivery-snapshots`。

## Preconditions

```text
project_root 已知；只读调用
```

## Required inputs

| 输入 | 必填 | 说明 |
| --- | --- | --- |
| `novel_id`（单作品） | 单作品读取时必填 | 不传则只列全部作品 |

## Authoritative interfaces

```text
UI           Studio Landing 作品卡 / Studio 头部
REST         GET /api/story-builder/novels              → {"novels": [...]}
             GET /api/story-builder/novels/{novel_id}   → {"novel": {...}}
Application  ProjectService.list_novels() / get_novel(novel_id)
MCP          resource novelforge://novels/{novel_id}（作品摘要；由 ApplicationServices.summary 组合）
```

## Procedure

```text
1 call GET /novels（或 ProjectService.list_novels）
2 locate row with novel_id == 目标 id
3 需要细节时 call GET /novels/{novel_id} → profile（title / genre / content_pack_id / cast / factions）
4 记录 novel_id + updated_at 作为后续调用的作用域证据
5 next：inspect-blueprint（看这本书现在有什么蓝图）或 create-novel（不存在时）
```

## Expected result

```json
{"novels": [{"novel_id": "novel_alpha", "title": "…", "genre": "…", "cast": 3, "factions": 2}]}
```

## Verification

```text
· 返回的 novel_id 与请求一致（MCP 摘要 resource 同样检查 novel_id 字段）
· 只读调用后 git status / artifact 计数不变
```

## Common failures

| 现象 | 原因 | 处理 |
| --- | --- | --- |
| 404 `PROFILE_NOT_FOUND` | novel_id 不存在 | 用列表确认，或先 `create-novel` |
| 列表为空 | 该项目根下还没有作品 | 走 `create-novel` |
| MCP `MCP_OWNERSHIP_MISMATCH` | resource 的 novel_id 与工具作用域不一致 | 统一 novel_id 后重试 |

## Safety / invariants

```text
只读；不产生 revision、不改质量状态、不写任何 artifact
不把 profile 里的配置当作"角色已经拥有"的事实（CONFIG != POSSESSION）
```

## Side effects

无（除服务端读盘）。

## Related skills

`create-novel`、`rename-novel`、`archive-novel`、`novelforge-v4.0.1.studio.inspect-overview`

## Source references

```text
src/novelforge/application/services/project.py
src/novelforge/api/project_routes.py
src/novelforge/application/services/facade.py（ApplicationServices.summary）
tests/acceptance/test_final_integration.py
```
