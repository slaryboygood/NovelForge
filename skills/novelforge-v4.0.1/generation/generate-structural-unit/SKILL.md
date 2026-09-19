---
name: novelforge-v4.0.1.generation.generate-structural-unit
description: 生成结构单元（structural_unit：幕 / 部 / 篇），把故事弧拆成可承载章节的中层结构。
---

# generate-structural-unit

- **Skill ID**: `novelforge-v4.0.1.generation.generate-structural-unit`
- **Version**: 1（baseline `V4.0.1`）
- **Capability Module**: `generation`
- **Product owner**: `src/novelforge/generation/tasks/story.py::structural_unit_spec`
  （contract `blueprint.structural_unit.v1`）

## Purpose

在 story_arc 与 chapter 之间建立可计数的结构层（例如 act_1 / act_2），让"这一章为什么在这里"
有答案。

## Use when

- story_arc 已就位，需要分幕 / 分部。
- 需要追加一个单元（同一父节点下的第 N 个）。

## Do not use when

- 想直接出章节 → 也可以（chapter 允许挂 story_arc），但会失去中层节奏信息。

## Preconditions

```text
story_arc 存在（本任务 requires_parent = true；缺省父节点取 story_arc）
provider enabled
```

## Required inputs

| 输入 | 必填 | 说明 |
| --- | --- | --- |
| `novel_id` | 是 | 目标作品 |
| `task` / `node_type` | 是 | `structural_unit` |
| `parent_id` | 否 | 缺省 = story_arc |
| `unit_type` | 是 | 单元类型（例如 `act` / `part` / `volume`） |
| `index` | 否 | 兄弟序号（决定 `unit_<unit_type>_<index>`）；缺省自动计算 |

## Authoritative interfaces

```text
UI           「故事」→ 结构单元
REST         POST /studio/generate {"task":"structural_unit","unit_type":"act","index":1}
Application  BlueprintService.generate_task("structural_unit", …)
MCP          tool generate_structural_unit
```

## Procedure

```text
1 确认 story_arc 存在
2 决定 unit_type 与 index（第 N 幕）
3 POST /studio/generate {novel_id, task:"structural_unit", unit_type, index}
4 校验 node_id 形如 unit_<unit_type>_<index>、parent 类型 ∈ {story_arc, structural_unit}
5 读 payload.{unit_type, title, goal, conflict, turn, outcome}
6 next：generate-chapter-plan（父节点 = 这个单元）
```

## Expected result

一个新的 `structural_unit` 节点（proposed），带目标 / 冲突 / 转折 / 结果。

## Verification

```text
· 同一父节点下 (unit_type, index) 不重复（否则 id 冲突）
· unit.goal 与 story_arc 对应段落一致
· 章节稍后能挂到本单元（parent 允许 structural_unit）
```

## Common failures

| 现象 | 原因 | 处理 |
| --- | --- | --- |
| id 冲突 | 同 unit_type + index 已存在 | 换 index 或直接编辑已有单元 |
| parent 报错 | parent 不是 story_arc / structural_unit | 修正 parent_id |
| 单元目标与主角弧无关 | 上游上下文不足 | 重生成或 `patch-node` |

## Safety / invariants

```text
requires_parent：单元必须属于故事弧或另一个单元
单元不是章节：不要在 unit 上写章节级字段（用 chapter 节点）
```

## Side effects

新节点 revision + 模型调用（provider 启用时）。

## Related skills

`generate-story-arc`、`generate-chapter-plan`、`inspect-blueprint`

## Source references

```text
src/novelforge/generation/tasks/story.py
src/novelforge/blueprint/contracts.py（StructuralUnitPayload / ALLOWED_PARENT_TYPES）
src/novelforge/api/studio_routes.py（SIBLING_TASKS）
```
