---
name: novelforge-v4.0.1.project.rename-novel
description: 修改 NovelForge V4.0.1 作品的作者可见名字（只改 profile.title，不动任何事实）。
---

# rename-novel

- **Skill ID**: `novelforge-v4.0.1.project.rename-novel`
- **Version**: 1（baseline `V4.0.1`）
- **Capability Module**: `project`
- **Product owner**: `src/novelforge/application/services/novel_admin.py::rename_novel`

## Purpose

只改作者可见的作品名。`novel_id`、Blueprint、Canon、StoryState、交付物一律不变。

## Use when

- 书名改了 / 写错了。

## Do not use when

- 想改 `novel_id` → **不支持**（身份不可变；要换身份请新建 + 重新生成）。
- 想改题材 / 内容包 → 走 Blueprint 节点编辑（`patch-node`）。

## Preconditions

```text
作品存在（否则 404 PROFILE_NOT_FOUND）
```

## Required inputs

| 输入 | 必填 | 约束 |
| --- | --- | --- |
| `novel_id` | 是 | 已存在 |
| `title` | 是 | 去空白后非空、≤120 字 |

## Authoritative interfaces

```text
UI           Studio 头部（作品名）
REST         PATCH /api/story-builder/novels/{novel_id}   body {"title": "…"}
Application  ProjectService.rename_novel(novel_id, title)
MCP          N/A
```

## Procedure

```text
1 确认目标作品：inspect-novels
2 PATCH /novels/{novel_id} {"title": "<新名字>"}
3 检查返回 {"novel_id","title","updated_at","read_only":false}
4 再 GET /novels/{novel_id} 确认 title 已更新，且其它字段（genre / content_pack_id）未变
```

## Expected result

```json
{"novel_id": "novel_alpha", "title": "新名字", "updated_at": "…", "read_only": false}
```

## Verification

```text
· GET /novels/{novel_id}.title == 新名字
· Blueprint digest / quality report / delivery snapshot 数量不变（改名不影响真相）
```

## Common failures

| 现象 | 原因 | 处理 |
| --- | --- | --- |
| 422 `NOVEL_TITLE_EMPTY` | 空 / 全空白 | 提供有效标题 |
| 422 `NOVEL_TITLE_TOO_LONG` | >120 字 | 缩短 |
| 404 `PROFILE_NOT_FOUND` | novel_id 不存在 | `inspect-novels` |

## Safety / invariants

```text
只改 title；不改 novel_id、不改 Blueprint payload、不写 Canon / StoryState
不把改名当成"改作品事实"
```

## Side effects

profile 的 `updated_at` 变化。

## Related skills

`inspect-novels`、`archive-novel`

## Source references

```text
src/novelforge/application/services/novel_admin.py
src/novelforge/api/project_routes.py
```
