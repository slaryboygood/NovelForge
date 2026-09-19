---
name: novelforge-v4.0.1.generation.generate-world
description: 生成世界设定（world）节点：规则、地点、势力、资源、技术/魔法与冲突来源。
---

# generate-world

- **Skill ID**: `novelforge-v4.0.1.generation.generate-world`
- **Version**: 1（baseline `V4.0.1`）
- **Capability Module**: `generation`
- **Product owner**: `src/novelforge/generation/tasks/world.py::world_spec`（contract `blueprint.world.v1`）

## Purpose

建立故事世界的约束面：什么可能、什么不可能、冲突从哪里来。后续场景卡必须尊重这些规则。

## Use when

- 「世界」页需要内容。
- 世界规则随剧情需要收紧 / 放宽（重生成或 `patch-node`）。

## Do not use when

- 要改 Canon 里**已发生**的世界事实 → 那是 Canon 边界（本 skill 不写事实）。

## Preconditions

```text
作品 + premise 存在；provider enabled
```

## Required inputs

| 输入 | 必填 | 说明 |
| --- | --- | --- |
| `novel_id` | 是 | 目标作品 |
| `task` / `node_type` | 是 | `world` |
| `parent_id` | 否 | 可挂 premise |
| `instruction` | 否 | 题材 / 风格方向 |

## Authoritative interfaces

```text
UI           「世界」
REST         POST /studio/generate {"task":"world"}
Application  BlueprintService.generate_task("world", …)
MCP          tool generate_world
```

## Procedure

```text
1 POST /studio/generate {novel_id, task:"world", parent_id?:"premise", instruction?}
2 校验 node.node_id == "world"、status == proposed
3 读 payload.{rules, locations, factions, resources, technology_or_magic,
  social_constraints, conflict_sources, story_relevant_history}
4 与 premise 对齐：world 规则不能推翻 central_conflict
5 next：generate-character（人物挂在 world / premise 下）
```

## Expected result

`world` 单例节点（新 revision），含规则 / 地点 / 势力 / 资源列表。

## Verification

```text
· inspect-blueprint?node_type=world 恰好 1 条
· 每条规则的表述是可判定的（不是"很复杂"这类空话 → Q8）
· 未被自动接受
```

## Common failures

| 现象 | 原因 | 处理 |
| --- | --- | --- |
| 422 `GENERATION_UNAVAILABLE` | 未配置 provider | 配置 provider |
| 规则与 Canon 冲突 | 世界里已有已发生事实 | 交给 Q2（CANON_CONTRADICTION）→ `plan-repair`，不要改 Canon |
| 生成内容泛化 | 模型输出空泛 | Q8 → `plan-repair` |

## Safety / invariants

```text
世界设定是计划，不是已发生事实；不写 Canon / StoryState
配置 ≠ 拥有：rules / resources 不等于角色已经掌握（CONFIG != POSSESSION）
```

## Side effects

新 revision + 模型调用（provider 启用时）。

## Related skills

`generate-premise`、`generate-character`、
`novelforge-v4.0.1.quality.evaluate-blueprint`、`novelforge-v4.0.1.repair.plan-repair`

## Source references

```text
src/novelforge/generation/tasks/world.py
src/novelforge/blueprint/contracts.py（WorldPayload）
docs/v4/V4_04_GENERATION_INVENTORY.md
```
