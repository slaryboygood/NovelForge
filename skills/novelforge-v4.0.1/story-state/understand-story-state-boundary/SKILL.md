---
name: novelforge-v4.0.1.story-state.understand-story-state-boundary
description: 掌握 StoryState 的真相地位与读写边界：它是已发生事实的 runtime 状态，V4 只读消费。
---

# understand-story-state-boundary

- **Skill ID**: `novelforge-v4.0.1.story-state.understand-story-state-boundary`
- **Version**: 1（baseline `V4.0.1`）
- **Capability Module**: `story-state`
- **Product owner**: `src/novelforge/story_engine/state.py` + `context.py`

## Purpose

避免把"设计意图 / 未来规划"写进已发生事实，也避免把 StoryState 当成可随手修改的运行缓存。

## Use when

- 需要判断某内容该写 Blueprint 还是 StoryState。
- 审查流程是否在偷偷改事实状态。

## Do not use when

- 只是想读状态 → `inspect-story-state`。

## Preconditions

```text
无
```

## Required inputs

```text
无
```

## Authoritative interfaces

```text
UI           N/A
REST         N/A
Application  novelforge.story_engine.context.resolve_novel_context / state.StoryState
MCP          N/A
```

## Procedure（判断顺序）

```text
1 这是"计划"还是"已发生"？
   计划 → Blueprint（可改、proposal→accepted）
   已发生 → StoryState / Canon（受保护，作者审批边界）
2 V4 生成只读 StoryState；生成结果不写 state（PLANNING != OCCURRED TRUTH）
3 StoryState 的变化必须由作者 / 引擎侧受控流程产生，且需要审批边界（AGENTS.md §12.2）
4 读取只能经 resolve_novel_context（canonical owner），不要手工解析 state JSON
5 发现越界写入 → 记录到 docs/v4/V4_0_1_SKILL_GAPS.md，不顺手改 runtime
```

## Expected result

能正确回答：

```text
· 生成一个"角色获得新武器"的场景卡，算不算角色已经拥有？（不算，属计划）
· 能不能通过 editor patch 改 StoryState？（不能，Editor 只改 Blueprint）
· memory 里的 story_state 条目是不是新的状态源？（不是，是只读投影）
```

## Verification

```text
· 交叉核对 src/novelforge/story_engine/state.py（StoryState 字段）与 context.py（读取入口）
· 交叉核对 src/novelforge/memory/sources/story_state.py（只读投影 + revision）
· 交叉核对 tests/v4/isolation/test_memory_ownership.py 与 docs/DATA_MODEL.md（truth 分层）
```

## Common failures

| 现象 | 原因 | 处理 |
| --- | --- | --- |
| 生成结果被误当事实 | 没有区分 planning vs occurred | 回到 Blueprint proposal + accept 流程 |
| 出现两份状态 | 复制了 StoryState | 收敛到 canonical owner |

## Safety / invariants

```text
PLANNING != OCCURRED TRUTH；CONFIG != POSSESSION；DESIGN INTENT != CANON FACT
StoryState 写入不属于本 Skill Library 的范围（需要作者审批边界）
```

## Side effects

无。

## Related skills

`inspect-story-state`、`novelforge-v4.0.1.canon.inspect-canon-truth`、
`novelforge-v4.0.1.memory.understand-truth-precedence`

## Source references

```text
src/novelforge/story_engine/state.py、context.py、storage.py
docs/DATA_MODEL.md
AGENTS.md §15（数据原则）、§12.2（必须停止的情况）
```
