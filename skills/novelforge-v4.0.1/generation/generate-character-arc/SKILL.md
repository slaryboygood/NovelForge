---
name: novelforge-v4.0.1.generation.generate-character-arc
description: 生成某个人物的人物弧（character_arc）：起点状态、内在冲突、关键转折、中点变化、危机与高潮选择。
---

# generate-character-arc

- **Skill ID**: `novelforge-v4.0.1.generation.generate-character-arc`
- **Version**: 1（baseline `V4.0.1`）
- **Capability Module**: `generation`
- **Product owner**: `src/novelforge/generation/tasks/characters.py::character_arc_spec`
  （contract `blueprint.character_arc.v1`）

## Purpose

把人物卡从"静态设定"变成"这本书里他会怎么变"，供 Q4（Character）检查与场景设计对齐。

## Use when

- 人物已存在，需要他的成长 / 崩塌曲线。
- 需要重做弧线（重生成，保留 `arc_<character_id>` 身份）。

## Do not use when

- 人物还没有 → `generate-character`。
- 想改单个转折 → `patch-node`（key_turns 等是 payload 字段）。

## Preconditions

```text
父 character 节点存在（本任务 requires_parent = true）
provider enabled
```

## Required inputs

| 输入 | 必填 | 说明 |
| --- | --- | --- |
| `novel_id` | 是 | 目标作品 |
| `task` / `node_type` | 是 | `character_arc` |
| `parent_id` | 是 | 目标人物节点 id |
| `instruction` | 否 | 成长方向（例如"从自保到承担"） |

## Authoritative interfaces

```text
UI           「人物」→ 人物弧
REST         POST /studio/generate {"task":"character_arc","parent_id":"char_01_lin"}
Application  BlueprintService.generate_task("character_arc", …)
MCP          tool generate_character_arc
```

## Procedure

```text
1 取人物节点 id（inspect-blueprint?node_type=character）
2 POST /studio/generate {novel_id, task:"character_arc", parent_id:<character>, instruction?}
3 校验 node.node_id == arc_<character_id>、父节点类型 == character
4 读 payload.{character_id, start_state, internal_conflict, external_pressure, key_turns,
  midpoint_change, crisis, climax_choice, end_state}
  注意：contract `blueprint.character_arc.v1` 要求 payload **必须带 character_id**
  （非空字符串）。系统随后用父节点 id 覆盖它，但模型输出里缺这个字段会直接得到
  422（结构化输出未通过 schema 校验）。stub / 本地 provider 也必须返回它。
5 校验 character_id 与父节点一致（系统覆盖模型输出的 id）
6 next：generate-story-arc，或 evaluate-blueprint 看 Q4
```

## Expected result

`arc_<character_id>` 节点（proposed），弧线关键点可被场景支撑。

## Verification

```text
· node.parent_id == 目标人物；payload.character_id == 同一 id
· key_turns 非空且能在后续 scene 中找到对应（Q4 CHARACTER_ARC_UNSUPPORTED_TURN 会检查）
· start_state != end_state（否则弧线没有变化）
```

## Common failures

| 现象 | 原因 | 处理 |
| --- | --- | --- |
| 报"任务需要存在的父节点" | parent_id 缺失 / 不存在 | 先建人物或修正 parent_id |
| 弧线停滞 | 关键点过少 | Q4 `CHARACTER_ARC_STALL` → `plan-repair` |
| character_id 与父节点不符 | 手工构造 payload | 交给系统分配，不要手写 id |
| 422 且 message 是"结构化输出未通过 schema 校验" | 模型输出缺 `character_id` 等必填字段 | 让 provider / stub 返回该字段（值会被系统覆盖） |

## Safety / invariants

```text
requires_parent：没有人物就没有人物弧
character_id 由系统分配（模型的 id 被覆盖，防止结构错挂）
弧线是计划，不是已发生事实
```

## Side effects

新节点 revision + 模型调用（provider 启用时）。

## Related skills

`generate-character`、`generate-story-arc`、`inspect-node`、
`novelforge-v4.0.1.quality.list-quality-issues`

## Source references

```text
src/novelforge/generation/tasks/characters.py
src/novelforge/generation/service.py::_enforce_system_ids
src/novelforge/blueprint/contracts.py（CharacterArcPayload / ALLOWED_PARENT_TYPES）
tests/generation/test_generation_validation.py
```
