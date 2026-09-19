---
name: novelforge-v4.0.1.generation.generate-chapter-plan
description: 生成章节卡（chapter）：本章目标、冲突、转折、结果、钩子与地点。
---

# generate-chapter-plan

- **Skill ID**: `novelforge-v4.0.1.generation.generate-chapter-plan`
- **Version**: 1（baseline `V4.0.1`）
- **Capability Module**: `generation`
- **Product owner**: `src/novelforge/generation/tasks/chapter.py::chapter_spec`（contract `blueprint.chapter.v1`）

## Purpose

把结构单元拆成有明确目标的章节卡，作为场景卡的上游。

## Use when

- 需要第 N 章。
- 章节目标重复 / 空泛，需要重做（Q6 CHAPTER_GOAL_REPETITION）。

## Do not use when

- 需要场景级细节 → `generate-scene-plan`（父节点 = 本章）。

## Preconditions

```text
unit 或 story_arc 存在（requires_parent = true；缺省父节点取第一个 structural_unit）
provider enabled
```

## Required inputs

| 输入 | 必填 | 说明 |
| --- | --- | --- |
| `novel_id` | 是 | 目标作品 |
| `task` / `node_type` | 是 | `chapter` |
| `parent_id` | 否 | 缺省 = 第一个结构单元 |
| `index` | 否 | 章节序号（决定 `ch_<index:03d>`）；缺省自动计算 |
| `instruction` | 否 | 本章任务说明 |

## Authoritative interfaces

```text
UI           「故事」→ 章节卡
REST         POST /studio/generate {"task":"chapter","parent_id":"act_01","index":3}
Application  BlueprintService.generate_task("chapter", …)
MCP          tool generate_chapter_plan
```

## Procedure

```text
1 选择父单元（inspect-blueprint?node_type=structural_unit；结构单元 id 形如 `act_01`）
2 决定章节序号 index（不要与已有章节重复）
3 POST /studio/generate {novel_id, task:"chapter", parent_id, index, instruction?}
4 校验 node_id == ch_<index:03d>、parent ∈ {structural_unit, story_arc}、status == proposed
5 读 payload.{title, goal, conflict, turn, outcome, hook, location}
6 next：generate-scene-plan（父节点 = 本章）
```

## Expected result

`ch_003` 这类节点（proposed），带目标 / 转折 / 钩子。

## Verification

```text
· 章节序号连续且不重复（id 唯一）
· goal 与其他章节不同（Q6 CHAPTER_GOAL_REPETITION）
· hook 非空（否则 Q7 PACING / Q9 交付就绪度会提意见）
```

## Common failures

| 现象 | 原因 | 处理 |
| --- | --- | --- |
| 第二章覆盖第一章 | 未给 index | 给 `index`，或让 REST 自动推导（同父节点已有章节数 + 1） |
| 目标重复 | 上游单元目标重复 | 先修单元（patch），再重生成该章 |
| 报缺父节点 | 还没建结构单元 | `generate-structural-unit` 或显式给 `parent_id` |

## Safety / invariants

```text
系统分配 ch_<index>；一章一节点
章节卡是计划，不是正文（V4 不生成正文）
```

## Side effects

新节点 revision + 模型调用（provider 启用时）。

## Related skills

`generate-structural-unit`、`generate-scene-plan`、`inspect-scene-cards`、
`novelforge-v4.0.1.quality.list-quality-issues`

## Source references

```text
src/novelforge/generation/tasks/chapter.py
src/novelforge/api/studio_routes.py::generate（index / sequence 推导）
tests/generation/test_generation_pipeline.py
```
