---
name: novelforge-v4.0.1.project.archive-novel
description: 把 NovelForge V4.0.1 的某个作品整体归档（删除按钮语义：可恢复、不留孤儿），需要显式二次确认。
---

# archive-novel

- **Skill ID**: `novelforge-v4.0.1.project.archive-novel`
- **Version**: 1（baseline `V4.0.1`）
- **Capability Module**: `project`
- **Product owner**: `src/novelforge/application/services/novel_admin.py::archive_novel`

## Purpose

「删除作品」在 V4 的真实语义是**整体归档**：把该书所有产物移动到
`workspace/archived_novels/<novel_id>_<UTC 时间戳>/`，并写
`ARCHIVE_MANIFEST.json`。它是可恢复的，不是不可逆删除。

## Use when

- 作者明确要求移除某本书。
- 测试 / 演示环境需要清理某个作品。

## Do not use when

- 只是想停止使用某个作品 → 什么都不用做（没有"当前作品"状态）。
- 想删除单个节点 / revision → 走 Editor（reject / restore），不要归档整本作品。
- 目的是腾空间但之后要恢复 → 也可以，但必须记录 archive_dir。

## Preconditions

```text
作者已显式确认（destructive 动作，必须有确认，不可由 Agent 自动决定）
作品存在且至少有一个可归档产物（否则 NOVEL_ARTIFACTS_MISSING）
```

## Required inputs

| 输入 | 必填 | 说明 |
| --- | --- | --- |
| `novel_id` | 是 | 目标作品 |
| `confirm=true` | 是（REST） | 缺失 → 409 `NOVEL_DELETE_UNCONFIRMED` |
| `reason` | 否 | ≤200 字，写进 manifest |

## Authoritative interfaces

```text
UI           Studio「删除」+ 二次确认
REST         DELETE /api/story-builder/novels/{novel_id}?confirm=true&reason=…
Application  ProjectService.archive_novel(novel_id, reason=…)
MCP          N/A（MCP 明确不提供作品归档）
```

## Procedure

```text
1 确认目标与影响范围：inspect-novels + 记录当前 delivery snapshot 数（作为回滚参照）
2 向作者取得显式确认（这是 destructive action 的批准边界）
3 call DELETE /novels/{novel_id}?confirm=true&reason=…
4 读取返回 manifest：archive_dir / moved[] / recoverable=true
5 复验：GET /novels 不再包含该 novel_id；archive_dir 下存在 ARCHIVE_MANIFEST.json
6 记录 archive_dir 到会话结果（恢复路径）
```

## Expected result

```json
{"novel_id":"novel_alpha","archive_dir":"workspace/archived_novels/novel_alpha_20260919T010203Z",
 "moved":[{"from":"novel/authoring/...","to":"...","kind":"dir"}],
 "recoverable":true,"reason":"…"}
```

覆盖的产物包括：profiles / canon db / blueprint / quality / editor / delivery / agent /
memory / story_state / 内容包 / 插件 state（见 `novel_artifact_paths`）。

## Verification

```text
· GET /novels 不再列出该 novel_id（GET /novels/{id} → 404 PROFILE_NOT_FOUND）
· archive_dir/ARCHIVE_MANIFEST.json 存在且 moved 列表非空
· 原路径全部消失（不留孤儿目录；这正是 NF-011 修复过的缺陷）
· recoverable == true（可把移动项移回原位恢复）
```

## Common failures

| 现象 | 原因 | 处理 |
| --- | --- | --- |
| 409 `NOVEL_DELETE_UNCONFIRMED` | 缺少 confirm=true | 取得作者确认后重试 |
| 422 `NOVEL_ARTIFACTS_MISSING` | 没有任何可归档产物 | 确认 novel_id 是否正确 |
| 422 `NOVEL_ARCHIVE_EXISTS` | 同一秒的归档目录已存在 | 稍后重试或使用新时间戳 |
| 404 `PROFILE_NOT_FOUND` | 作品不存在 | `inspect-novels` |

## Safety / invariants

```text
destructive：必须有作者显式确认（Agent 不得自动归档）
scope：只归档指定 novel_id，绝不触碰其它作品
rollback：整体移动 + ARCHIVE_MANIFEST.json 记录 from/to，可按 manifest 移回
不修改 frozen truth（Canon / StoryState 文件被"移动"，不被改写）
```

## Side effects

文件系统移动（作品作用域目录整体迁移）+ 写 `ARCHIVE_MANIFEST.json`。

## Related skills

`inspect-novels`、`create-novel`、`novelforge-v4.0.1.delivery.list-delivery-snapshots`

## Source references

```text
src/novelforge/application/services/novel_admin.py（novel_artifact_paths / archive_novel）
src/novelforge/api/project_routes.py
tests/acceptance/test_final_release.py
docs/v4/V4_0_1_SKILL_GAPS.md（GAP-008 之外的归档完整性说明）
```
