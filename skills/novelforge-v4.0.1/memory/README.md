# Module: `memory` — 派生记忆与上下文装配

```text
Module purpose     按预算 / scope 装配"这次生成需要看什么"；记忆是派生且可重建的
Authoritative owner src/novelforge/memory/{service,contracts,context/*}.py
Owned skills       inspect-derived-memory / build-generation-context / understand-truth-precedence
Truth ownership    无。Memory 不是 Canon、不是 StoryState、不是数据库（ADR-014）
Public interfaces  Python public API（MemoryService / ContextBuilder）；
                   UI / REST / MCP = N/A（DEFER，见 V4_0_1_SKILL_GAPS.md GAP-004）
Dependencies       story_engine（Canon / StoryState / NovelContext）、core、ai（可选 compressor）
Forbidden          用 memory 覆盖 Canon、把检索结果当事实、绕过 ContextBuilder 另建一套上下文
Related modules    generation（唯一消费者）、quality / delivery（都不读 memory）
```

## 权威层级（唯一口径）

```text
Canon / StoryState / Blueprint   = 真相（写入边界受保护）
Memory（派生视图）               = 只读投影，必须可重建、可失效、可追溯 source_ids / revision
ContextBundle                    = 某次调用的上下文选择结果（含 digest，是生成 evidence 的一部分）
```

## 公开契约要点

| 对象 | 关键字段 |
| --- | --- |
| `MemoryQuery` | `novel_id`, `top_k`, `token_budget`, `required_source_ids`, `policy(RetrievalPolicy)` |
| `MemoryItem` / `MemorySource` | `text`, `memory_type`, `source.{source_type, source_id, revision, metadata}` |
| `MemoryService` | `search` / `rebuild` / `stats` / `stale_report` / `refresh_staleness` |
| `ContextRequest` / `ContextBundle` | `novel_id`, `revision`, `operation`, blocks(`required/recent/relevant/preference`) |
| 版本 | `MEMORY_SCHEMA_VERSION = 1`、`CONTEXT_BUNDLE_SCHEMA_VERSION = 1` |
