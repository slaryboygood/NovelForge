---
name: novelforge-v4.0.1.generation.generate-story-arc
description: 生成故事弧（story_arc）：初始状态、触发事件、递进复杂化、主要转折、中点、危机、高潮与收束。
---

# generate-story-arc

- **Skill ID**: `novelforge-v4.0.1.generation.generate-story-arc`
- **Version**: 1（baseline `V4.0.1`）
- **Capability Module**: `generation`
- **Product owner**: `src/novelforge/generation/tasks/story.py::story_arc_spec`（contract `blueprint.story_arc.v1`）

## Purpose

建立整本书的主干弧线，作为结构单元 / 章节 / 场景的上游约束（Q7 Narrative 的判定依据）。

## Use when

- 世界与人物已就位，需要整体骨架。
- 弧线需要重做（重生成，保留 `story_arc` 单例 id）。

## Do not use when

- 需要拆成章节 / 场景 → 先 story_arc，再 `generate-structural-unit` / `generate-chapter-plan`。

## Preconditions

```text
premise / theme / world / character 已存在（弧线需要它们作为上下文）
provider enabled（本任务要求 large_context 能力）
```

## Required inputs

| 输入 | 必填 | 说明 |
| --- | --- | --- |
| `novel_id` | 是 | 目标作品 |
| `task` / `node_type` | 是 | `story_arc` |
| `parent_id` | 否 | 可挂 premise |
| `instruction` | 否 | 结构偏好（例如三幕 / 五幕） |

## Authoritative interfaces

```text
UI           「故事」
REST         POST /studio/generate {"task":"story_arc"}
Application  BlueprintService.generate_task("story_arc", …)
MCP          tool generate_story_arc
```

## Procedure

```text
1 确认上游节点齐备：inspect-blueprint（premise / theme / world / character）
2 POST /studio/generate {novel_id, task:"story_arc", parent_id?:"premise", instruction?}
3 校验 node_id == "story_arc"、status == proposed
4 读 payload.{initial_state, inciting_incident, progressive_complications, major_turns,
  midpoint, crisis, climax, resolution}
5 交叉检查人物弧：每个主要人物的 key_turns 是否落在 major_turns / crisis 附近
6 next：generate-structural-unit
```

## Expected result

`story_arc` 单例节点（新 revision），含可拆解的结构骨架。

## Verification

```text
· inspect-blueprint?node_type=story_arc 恰好 1 条
· resolution 覆盖 premise.central_conflict（否则 Q7 RESOLUTION_INCOMPLETE）
· climax 有前置积累（否则 Q7 CLIMAX_UNPREPARED）
```

## Common failures

| 现象 | 原因 | 处理 |
| --- | --- | --- |
| 422 `GENERATION_UNAVAILABLE` | provider 未启用 / 缺 large_context 模型 | 配置支持该能力的模型 |
| 弧线与人物弧互相矛盾 | 上游人物弧过强或过弱 | 先修人物弧（patch / 重生成），再重做 story_arc |
| 结构空泛 | 模型输出泛化 | Q7 / Q8 → `plan-repair` |

## Safety / invariants

```text
单例 id = story_arc；重生成不产生第二个主编
proposal only；不写 Canon / StoryState
结构骨架不是已发生剧情（PLANNING != OCCURRED TRUTH）
```

## Side effects

新 revision + 模型调用（provider 启用时）。

## Related skills

`generate-character-arc`、`generate-structural-unit`、`generate-chapter-plan`、
`novelforge-v4.0.1.quality.evaluate-blueprint`

## Source references

```text
src/novelforge/generation/tasks/story.py
src/novelforge/blueprint/contracts.py（StoryArcPayload）
docs/v4/V4_QUALITY_CONTRACT.md §3（Q7）
```
