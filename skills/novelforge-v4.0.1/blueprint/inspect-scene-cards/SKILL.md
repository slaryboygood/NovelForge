---
name: novelforge-v4.0.1.blueprint.inspect-scene-cards
description: 读取场景卡视图，快速回答「这场戏为什么存在」以及它属于哪一章、承担什么叙事功能。
---

# inspect-scene-cards

- **Skill ID**: `novelforge-v4.0.1.blueprint.inspect-scene-cards`
- **Version**: 1（baseline `V4.0.1`）
- **Capability Module**: `blueprint`
- **Product owner**: `src/novelforge/blueprint/contracts.py::SceneCardPayload` +
  `ExportService.blueprint_view`

## Purpose

场景卡是 Blueprint 里最接近"可写作"的粒度：它声明 purpose / conflict / turn / outcome /
information_reveal / story_function。本 skill 用一份视图检查整条场景线是否成立。

## Use when

- 检查节奏（连续场景是否重复、是否升级）。
- Q6 / Q7 相关问题定位（语义重复、无叙事功能）。
- 交付前的场景完整性预检。

## Do not use when

- 需要章节层视角 → `inspect-blueprint?node_type=chapter`。

## Preconditions

```text
novel_id 已知；至少已生成 chapter + scene 节点
```

## Required inputs

| 输入 | 必填 | 说明 |
| --- | --- | --- |
| `novel_id` | 是 | 目标作品 |
| `mode` | 否 | 默认 `current`；`accepted` 只看已接受 |

## Authoritative interfaces

```text
UI           「场景」页
REST         GET /api/story-builder/studio/blueprint?novel_id=&node_type=scene&mode=
Application  ExportService.blueprint_view（visible 字段）
MCP          resource novelforge://novels/{novel_id}/scenes（分页）
```

## Procedure

```text
1 GET /studio/blueprint?novel_id=<id>&node_type=scene
2 对每个场景读 visible.{scene_purpose, location, time, conflict, escalation, turn,
  outcome, information_reveal, character_change, relationship_change, next_hook, story_function}
3 按 parent_id（chapter）+ sequence 排序阅读：是否有连续重复（Q6）或没有功能（Q7）
4 与 setup / payoff 对照：埋设是否有人回收（Q5）
5 next：严重问题 → plan-repair（按 issue），或直接 patch-node 改场景卡
```

## Expected result

每个场景都有一句可执行的 `scene_purpose`，并且 `story_function` 是注册枚举之一：

```text
advance_plot / reveal_information / escalate_conflict / character_change /
relationship_change / setup / payoff / decision / reversal / transition
```

## Verification

```text
· 每个 scene 的 parent_id 指向存在的 chapter，且 visible.location 等字段非模板化占位
· 连续场景的 story_function 不全部相同（Q6/Q7 的 deterministic 检查会给出 issue）
· 场景数与该章 chapter.hook 的声明一致（无孤儿场景）
```

## Common failures

| 现象 | 原因 | 处理 |
| --- | --- | --- |
| 场景全部落在同一章 | 生成时未指定正确 parent | `generate-scene-plan` 时给 chapter parent |
| purpose 千篇一律 | 模型输出泛化 | `evaluate-blueprint`（Q8 BLUEPRINT_VAGUE_CONTENT）→ `plan-repair` |
| 有 setup 没有 payoff | 因果链步骤未执行 | 见 `V4_0_1_SKILL_GAPS.md` GAP-002 |

## Safety / invariants

```text
只读；不修改场景卡
场景必须属于一章（scene.chapter_id 与 parent_id 一致，禁止孤儿）
```

## Side effects

无。

## Related skills

`inspect-blueprint`、`generate-scene-plan`、`novelforge-v4.0.1.quality.evaluate-blueprint`、
`novelforge-v4.0.1.repair.plan-repair`

## Source references

```text
src/novelforge/blueprint/contracts.py（SceneCardPayload / SceneFunction）
src/novelforge/blueprint/validation.py（SCENE_CHAPTER_REQUIRED）
docs/v4/V4_BLUEPRINT_CONTRACT.md §2
```
