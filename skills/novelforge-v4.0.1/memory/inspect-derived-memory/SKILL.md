---
name: novelforge-v4.0.1.memory.inspect-derived-memory
description: 用 MemoryService 只读检索派生记忆，查看某次生成会用到哪些 Canon / StoryState 片段及其 revision。
---

# inspect-derived-memory

- **Skill ID**: `novelforge-v4.0.1.memory.inspect-derived-memory`
- **Version**: 1（baseline `V4.0.1`）
- **Capability Module**: `memory`
- **Product owner**: `src/novelforge/memory/service.py::MemoryService`

## Purpose

回答「这次生成读了什么」：给出检索条目、来源类型、source_id 与 revision，并给出
记忆层的新鲜度 / 统计。

## Use when

- 需要解释生成结果为什么引用某条设定。
- 需要确认记忆是否过期（`stale_report`）。

## Do not use when

- 需要真相本体 → Canon / StoryState / Blueprint 各自的 skill。
- 想"通过 memory 改设定" → **禁止**（memory 是派生视图）。

## Preconditions

```text
novel_id 已知；只读（search / stats / stale_report 都不改真相）
```

## Required inputs

| 输入 | 必填 | 说明 |
| --- | --- | --- |
| `novel_id` | 是 | 目标作品 |
| `query` / 关键词 | 否 | 检索意图（不传则按 policy 取默认集合） |
| `top_k` / `token_budget` | 否 | 预算控制（默认 `top_k=8`） |

## Authoritative interfaces

```text
UI           N/A
REST         N/A（DEFER）
Application  memory.build_default_service(novel_id, project_root) → MemoryService.search(...)
MCP          N/A
```

## Procedure

```text
1 from novelforge.memory import build_default_service, MemoryQuery, RetrievalPolicy
2 service = build_default_service(novel_id, project_root)
3 result = service.search(MemoryQuery(novel_id=novel_id, task="scene",
                                     entities=("char_01",), locations=("station",), top_k=8))
   注意：`MemoryQuery` **没有** `text` / `query` 字段（传 text= 会 TypeError）。可用检索维度是
   `task` / `entities` / `locations` / `source_types` / `time_range` / `revision` /
   `top_k` / `token_budget` / `required_source_ids` / `policy`。
4 对每条 item 读 source.source_type / source_id / revision / relevance / selection_reason
5 service.stale_report() 检查是否基于过期 revision
6 记录结论（供生成 / 质量解释使用），不要写入任何 artifact
```

## Expected result

```json
{"items":[{"memory_id":"canon_fact:FACT_ab12","memory_type":"canon",
           "text":"…","source":{"source_type":"canon_fact","source_id":"FACT_ab12",
           "revision":3},"relevance":0.82}],
 "stats":{"…":"…"}}
```

## Verification

```text
· 每条 item 都带 source_id + revision（无法追溯 = 不合格的记忆）
· 跨作品检索被拒绝（MemoryIsolationError）
· 只读：调用后 Blueprint / 质量 / 交付产物数量不变
```

## Common failures

| 现象 | 原因 | 处理 |
| --- | --- | --- |
| 返回为空 | 这本书还没有 Canon / StoryState / 内容 | 正常；生成会得到较少上下文 |
| `StaleMemoryError` | 记忆基于旧 revision | `service.refresh_staleness()` 或 `rebuild()` |
| `MemoryIsolationError` | novel_id 不一致 | 统一 novel_id |

## Safety / invariants

```text
记忆是派生数据（ADR-014）：不得作为事实写入、不得覆盖 Canon / StoryState
禁止把检索结果直接当"故事已经发生"的证据
```

## Side effects

无（`rebuild` / `refresh_staleness` 只重建派生索引，不改真相）。

## Related skills

`build-generation-context`、`understand-truth-precedence`、
`novelforge-v4.0.1.canon.inspect-canon-truth`

## Source references

```text
src/novelforge/memory/service.py、contracts.py
src/novelforge/memory/sources/{canon,story_state}.py
tests/memory/test_retrieval_contract.py、tests/memory/test_invalidation.py
docs/v4/adr/ADR-014-memory-is-derived-canon-remains-authoritative.md
```
