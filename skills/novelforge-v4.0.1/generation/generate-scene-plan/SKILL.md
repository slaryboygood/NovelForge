---
name: novelforge-v4.0.1.generation.generate-scene-plan
description: 生成场景卡（scene）：这场戏为什么存在、冲突、升级、转折、结果、信息揭示与钩子。
---

# generate-scene-plan

- **Skill ID**: `novelforge-v4.0.1.generation.generate-scene-plan`
- **Version**: 1（baseline `V4.0.1`）
- **Capability Module**: `generation`
- **Product owner**: `src/novelforge/generation/tasks/scene.py::scene_spec`（contract `blueprint.scene.v1`）

## Purpose

生成最接近"可写作"的粒度：每场戏必须有功能与变化（否则 Q7 会判定"删掉也不损失"）。

## Use when

- 章节已存在，需要拆成场景。
- 场景语义重复 / 无功能，需要重做（Q6 / Q7）。

## Do not use when

- 章节还没定 → `generate-chapter-plan`。
- 需要 setup / payoff 节点 → 见 GAP-002（当前无对外入口）。

## Preconditions

```text
父 chapter 存在（requires_parent = true）
provider enabled
```

## Required inputs

| 输入 | 必填 | 说明 |
| --- | --- | --- |
| `novel_id` | 是 | 目标作品 |
| `task` / `node_type` | 是 | `scene` |
| `parent_id` | 是 | 目标章节（例如 `ch_003`） |
| `sequence` | 否 | 本章内第几场（决定 `sc_<chapter_index>_<seq>`）；缺省自动计算 |

## Authoritative interfaces

```text
UI           「场景」→ 生成场景
REST         POST /studio/generate {"task":"scene","parent_id":"ch_003","sequence":2}
Application  BlueprintService.generate_task("scene", …)
MCP          tool generate_scene_plan
```

## Procedure

```text
1 选父章节（inspect-blueprint?node_type=chapter）
2 决定 sequence（本章已有场景数 + 1）
3 POST /studio/generate {novel_id, task:"scene", parent_id, sequence}
   REST 会从 parent_id（ch_007 → 7）推导 chapter_index 生成 sc_007_2
4 校验 node_id 形如 sc_<chapter_index>_<seq>、parent 类型 == chapter、status == proposed
5 读 payload.{scene_purpose, location, time, conflict, escalation, turn, outcome,
  information_reveal, character_change, relationship_change, next_hook, story_function}
6 与上一场比较：story_function 不应完全相同（Q6 SCENE_SEMANTIC_REPETITION）
7 next：evaluate-blueprint（Q0–Q9）
```

## Expected result

一个场景卡节点（proposed），`chapter_id` 与 `parent_id` 一致。

## Verification

```text
· payload.chapter_id == parent_id（系统覆盖模型输出，防错挂）
· 场景在同一章内 sequence 连续、不重复
· scene_purpose 是一句可执行的话（不是"推进剧情"这类空话 → Q8）
```

## Common failures

| 现象 | 原因 | 处理 |
| --- | --- | --- |
| 报"必须声明 chapter_id" | 父章节缺失或不是 chapter | 给正确 parent_id |
| 第二场覆盖第一场 | 未给 sequence | 给 sequence 或让 REST 自动推导 |
| 场景功能重复 / 无功能 | 上下文不足或模型泛化 | `plan-repair`（Q6/Q7）或 `patch-node` |

## Safety / invariants

```text
scene 必须属于一章（结构 identity）
proposal only：不写 Canon / StoryState；不产生正文
dry_run 未实现（GAP-001）：调用即产生 revision
```

## Side effects

新节点 revision + 模型调用（provider 启用时）。

## Related skills

`generate-chapter-plan`、`inspect-scene-cards`、
`novelforge-v4.0.1.quality.evaluate-blueprint`、`novelforge-v4.0.1.repair.apply-repair`

## Source references

```text
src/novelforge/generation/tasks/scene.py
src/novelforge/blueprint/validation.py（SCENE_CHAPTER_REQUIRED）
src/novelforge/api/studio_routes.py::_chapter_ordinal
tests/generation/test_generation_service.py
```
