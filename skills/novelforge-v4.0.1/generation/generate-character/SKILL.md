---
name: novelforge-v4.0.1.generation.generate-character
description: 生成人物卡（character）节点：目标、动机、需求、恐惧、错误信念、长处、缺陷与人物关系。
---

# generate-character

- **Skill ID**: `novelforge-v4.0.1.generation.generate-character`
- **Version**: 1（baseline `V4.0.1`）
- **Capability Module**: `generation`
- **Product owner**: `src/novelforge/generation/tasks/characters.py::character_spec`（contract `blueprint.character.v1`）

## Purpose

把"谁在这本书里做事、为什么"变成结构化人物卡，供人物弧与场景卡引用。

## Use when

- 需要一个新人物（主角 / 对手 / 配角）。
- 人物卡需要重做（重生成，保留节点身份）。

## Do not use when

- 需要人物弧 → 先有人物，再 `generate-character-arc`。
- 要改单个字段（例如 fear）→ `patch-node`。

## Preconditions

```text
作品 + premise 存在；建议已有 world；provider enabled
```

## Required inputs

| 输入 | 必填 | 说明 |
| --- | --- | --- |
| `novel_id` | 是 | 目标作品 |
| `task` / `node_type` | 是 | `character` |
| `parent_id` | 否 | premise 或 world |
| `index` | 否 | 兄弟序号；缺省由 REST 自动取"该父节点下同类型子节点数 + 1" |
| `instruction` | 否 | 角色定位说明 |

## Authoritative interfaces

```text
UI           「人物」→ 新增人物
REST         POST /studio/generate {"task":"character","parent_id":"world","index":2}
Application  BlueprintService.generate_task("character", …)
MCP          tool generate_character
```

## Procedure

```text
1 确定父节点与序号（同一父节点下第几个人物 → index）
2 POST /studio/generate {novel_id, task:"character", parent_id, index, instruction?}
3 校验 node.node_id 形如 char_<NN>_<slug|digest>、node_type == character、status == proposed
4 读 payload.{name, role, kind, goal, motivation, need, fear, misbelief, strength, flaw,
  conflict_source, relationships, story_function, constraints}
5 next：generate-character-arc（父节点 = 这个人物）
```

## Expected result

一个新的 `character` 节点（r1，proposed），带关系与缺陷（不是"完美主角"）。

## Verification

```text
· node_id 前缀 char_，且同父节点下序号不重复（不会覆盖已有角色）
· 每个 character 的 parent 类型合法（premise / world / 无）
· relationships 引用的角色存在（REFERENCE_BROKEN 检查属于 Q0）
```

## Common failures

| 现象 | 原因 | 处理 |
| --- | --- | --- |
| 第二个角色覆盖了第一个 | 没给 index / sequence，id 相同 | 重新生成时给 `index` 或用 `inspect-blueprint` 确认现有序号 |
| 422 `GENERATION_UNAVAILABLE` | 未配置 provider | 配置 provider |
| 关系指向不存在的人 | 模型自造引用 | Q0 `REFERENCE_BROKEN` → `patch-node` 修正 |

## Safety / invariants

```text
系统分配 node id；模型不得自造 character_id
人物卡是计划：不写 Canon / StoryState；人物能力 ≠ 当前拥有装备
```

## Side effects

新节点 revision + 模型调用（provider 启用时）。

## Related skills

`generate-world`、`generate-character-arc`、`inspect-blueprint`、
`novelforge-v4.0.1.editor.patch-node`

## Source references

```text
src/novelforge/generation/tasks/characters.py
src/novelforge/api/studio_routes.py（SIBLING_TASKS / _sibling_ordinal）
src/novelforge/blueprint/contracts.py（CharacterPayload / NODE_ID_PREFIX）
tests/generation/test_generation_validation.py
```
