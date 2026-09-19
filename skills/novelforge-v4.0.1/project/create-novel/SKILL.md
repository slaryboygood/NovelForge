---
name: novelforge-v4.0.1.project.create-novel
description: 在 NovelForge V4.0.1 里创建一个新的作品（novel）档案，可选题材模板；不生成任何蓝图内容。
---

# create-novel

- **Skill ID**: `novelforge-v4.0.1.project.create-novel`
- **Version**: 1（baseline `V4.0.1`）
- **Capability Module**: `project`
- **Product owner**: `src/novelforge/application/services/project.py::ProjectService.create_novel`

## Purpose

建立一个作品身份（NovelProfile），使后续 Blueprint / Quality / Delivery 有一个隔离的
`novel_id` 作用域。创建本身**不**产生蓝图节点、不调用模型。

## Use when

- 作者要开一本新书，需要 `novel_id`。
- Agent / 机器客户端需要在开始生成前建立作用域。

## Do not use when

- 该作品已存在，只想继续工作 → 用 `inspect-novels`。
- 想"删除再重建" → 先 `archive-novel`（可恢复），不要用新建覆盖身份。
- 想直接生成前提 / 世界 → 先 `create-novel`，再 `generate-premise`。

## Preconditions

```text
· 已知 project_root（服务端不猜）
· 已确认 novel_id 未占用（重复创建返回 PROFILE_EXISTS，409）
```

## Required inputs

| 输入 | 必填 | 约束 |
| --- | --- | --- |
| `novel_id` | 是 | `^[A-Za-z0-9][A-Za-z0-9_-]{2,95}$` |
| `title` | 否 | ≤120 字（作者可见名字） |
| `genre` | 否 | ≤64 字 |
| `content_pack_id` | 否 | 已存在的内容包 id |
| `template_id` | 否 | 题材模板 id（`story_engine.templates.list_templates()` 可列出） |

## Authoritative interfaces

```text
UI           Studio Landing →「新建作品」（studioApi.createNovel）
REST         POST /api/story-builder/novels            → 201 {"novel": {...}}
Application  ProjectService.create_novel(novel_id, *, title, genre, content_pack_id, template_id)
MCP          N/A（MCP 不提供作品创建；工具均为 per-novel 能力）
```

## Procedure

```text
1 resolve project_root（环境/宿主已提供；MCP 用 NOVELFORGE_PROJECT_ROOT）
2 choose novel_id：小写字母 / 数字 / - / _，≥3 字符；不要用中文标题当 id
3 call create：REST POST /novels 或 ProjectService.create_novel(...)
4 if template_id given → 服务内部 apply_template(profile, template_id)
5 verify：GET /api/story-builder/novels/{novel_id} 返回同一 novel_id
6 next：generate-premise（skill novelforge-v4.0.1.generation.generate-premise）
```

## Expected result

```json
{"novel": {"novel_id": "novel_alpha", "title": "…", "genre": "…", "updated_at": "…"}}
```

REST 返回 201；Application 返回 profile 字典。作品目录按 `novel_id` 隔离，之后所有
artifact 都落在该作用域内。

## Verification

```text
· GET /novels 列表包含新 novel_id
· GET /novels/{novel_id} 返回 200 且 novel_id 一致
· 重复 create 同一 novel_id → 409 PROFILE_EXISTS（这才是覆盖风险被挡住）
```

## Common failures

| 现象 | 原因 | 处理 |
| --- | --- | --- |
| 409 `PROFILE_EXISTS` | id 已占用 | 换 id 或改用 `inspect-novels` 继续该作品 |
| 422 `NOVEL_ID_INVALID` | id 格式不合规 | 改成 `[A-Za-z0-9_-]{3,96}` |
| 404 on 后续调用 | 用错 novel_id | 用 `inspect-novels` 重新确认 |

## Safety / invariants

```text
不猜测"当前作品"；每次调用显式 novel_id
不在创建阶段写入 Canon / StoryState / Blueprint 内容（配置 ≠ 事实）
不手工写 profile 文件 —— 只走 ProjectService
```

## Side effects

创建 `novel/authoring/**/profiles` 记录与作品作用域目录；无模型调用。

## Related skills

`inspect-novels`、`rename-novel`、`archive-novel`、
`novelforge-v4.0.1.generation.generate-premise`

## Source references

```text
src/novelforge/application/services/project.py
src/novelforge/api/project_routes.py
src/novelforge/story_engine/profile.py
src/novelforge/story_engine/templates.py
src/novelforge/persistence/paths.py（novel_id 校验 / 路径 SSOT）
tests/acceptance/test_final_integration.py
docs/v4/V4_ARCHITECTURE.md
```
