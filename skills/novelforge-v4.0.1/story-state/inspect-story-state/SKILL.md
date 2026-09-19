---
name: novelforge-v4.0.1.story-state.inspect-story-state
description: 只读读取某本作品的 StoryState 摘要（时间线 / 位置 / 角色 / 资源 / 关系 / 未完成承诺）。
---

# inspect-story-state

- **Skill ID**: `novelforge-v4.0.1.story-state.inspect-story-state`
- **Version**: 1（baseline `V4.0.1`）
- **Capability Module**: `story-state`
- **Product owner**: `src/novelforge/story_engine/context.py::resolve_novel_context`

## Purpose

用 canonical 入口确认"故事现在处在什么状态"，作为生成上下文的解释依据（不写入）。

## Use when

- 需要解释为什么生成时上下文里有某个状态。
- 需要确认某个作品是否真的有 StoryState（而不是空状态）。

## Do not use when

- 想改状态 → 不允许（见 `understand-story-state-boundary`）。

## Preconditions

```text
project_root + novel_id；只读
```

## Required inputs

| 输入 | 必填 | 说明 |
| --- | --- | --- |
| `novel_id` | 是 | 目标作品 |

## Authoritative interfaces

```text
UI           N/A（间接：生成上下文）
REST         N/A
Application  novelforge.story_engine.context.resolve_novel_context(project_root, novel_id)
MCP          N/A
```

## Procedure

```text
1 from novelforge.story_engine.context import resolve_novel_context
2 ctx = resolve_novel_context(project_root, novel_id)
3 读 ctx.persisted（是否存在真实 state）、ctx.title / ctx.meta
4 读 state.timeline.{current_time,tick}、state.location.current、
  len(state.characters) / state.resources / state.relationships
5 读未完成项：state.promises（status=open）、state.plots（active / paused）
6 记录结论（只读证据），不要写回任何文件
```

## Expected result

```json
{"novel_id":"novel_alpha","persisted":true,
 "timeline":{"current_time":"…","tick":12},"location":"loc_alpha",
 "characters":3,"resources":5,"relationships":4,"open_promises":1}
```

## Verification

```text
· persisted=true 时 state 与该作品 story_state 记录一致
· 无任何写入（对照 storage 目录 mtime / effect_log 长度不变）
· 与 memory 的 story_state 投影一致（revision = len(effect_log)）
```

## Common failures

| 现象 | 原因 | 处理 |
| --- | --- | --- |
| `NovelContextError` / persisted=false | 还没有 state / novel_id 错 | 确认 novel_id；不要手工造 state 文件 |
| 记忆投影与 state 不一致 | 记忆过期 | `refresh_staleness` |

## Safety / invariants

```text
只读；不改 state、不手工解析 / 拼路径
不需要"当前作品"推断：novel_id 必须显式
```

## Side effects

无。

## Related skills

`understand-story-state-boundary`、`novelforge-v4.0.1.memory.inspect-derived-memory`

## Source references

```text
src/novelforge/story_engine/context.py、state.py、storage.py
src/novelforge/memory/sources/story_state.py
tests/test_canon_context.py、tests/memory/test_story_state_retrieval.py
```
