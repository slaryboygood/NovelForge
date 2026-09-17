# ADR-014 — Memory Is Derived, Canon Remains Authoritative

```
Status    : Accepted（V4-03 实施完成）
Date      : 2026-09-17
Context   : V4-03 Story Memory & Context Builder
Related   : V4_MEMORY_ARCHITECTURE.md；ADR-011（Story Blueprint）；ADR-015（Context Builder）
```

## Context

V4 要引入 Story Memory，但项目已经有两条硬边界：

```text
LLM is not the database.      （ADR-002 / V4_ARCHITECTURE.md §1.1）
planning != occurred truth.   （AGENTS.md §15、docs/DATA_MODEL.md）
```

同时代码里已有一个同名但不同义的历史模块：

```text
src/novelforge/story_engine/memory.py —— V2-E「三视角知识」（author / reader / character）
                                        查询层，属于 domain 事实，不是 V4 Story Memory
```

如果 Memory 层被允许写 Canon / StoryState，或者被当成第二套事实来源，
那么 V4 会立刻失去「事实唯一」这一基础不变量。

## Decision

1. `novelforge.memory` 是**派生检索层**：只做索引 / 摘要 / 检索 / 关联 / 压缩 / 上下文选择。
2. 权威事实仍是 Canon / StoryState / Story Blueprint / domain entities / revisioned artifacts；
   Memory **不拥有**其中任何一个。
3. 每个派生条目必须携带 `source_ids` + `source_revision` + `created_at` +
   `memory_schema_version`；canonical revision 变化时旧条目 `stale`（不静默当真）。
4. `story_engine/memory.py` **保持原义不改名、不覆盖**（V4-00 分类为 KEEP）；
   V4 的 Story Memory 使用新的 `src/novelforge/memory/` 命名空间。
5. Memory 丢失 / 删除目录不得导致任何小说事实丢失（可重建）。
6. 模型生成的 summary / tags / relationship interpretation 只能成为 derived memory，
   不得自动升级为 Canon / StoryState / Blueprint truth。

## Consequences

正面：

* V4-04 生成与 V4-05 质量检查可以放心检索，不必担心"检索结果被当成事实写回"。
* 记忆可以随时重建（`MemoryService.rebuild()`），失败可恢复。
* 与既有 `tests/v4/isolation/test_ownership_isolation.py` 的 ownership 约定一致。

代价：

* 每次检索都要处理 revision / stale 语义（比"直接读一份缓存"复杂）。
* 需要显式重建流程（`rebuild()`），而不是"读到什么用什么"。

## Alternatives considered

| 方案 | 为什么不选 |
| --- | --- |
| 让 Memory 缓存一份"当前状态"，读时直接用 | 会产生第二套 StoryState；revision 漂移后无人负责 |
| 把 `story_engine/memory.py` 改名给 V4 用 | 它是 domain 事实查询层，改名会破坏既有语义与测试（§28） |
| 直接把 embedding 当记忆主体 | 需要模型/网络，且无法解释 provenance，与 §44 的可解释性要求冲突 |

## Evidence

```text
src/novelforge/memory/contracts.py      MemorySource / MemoryItem / revision 字段
src/novelforge/memory/index.py          stale / apply_revision_check / rebuild 幂等
src/novelforge/memory/service.py        rebuild / stale_report / 不写 truth
src/novelforge/story_engine/memory.py   保持原义（V2-E 三视角知识）
tests/memory/test_invalidation.py       revision 漂移 → stale → 排除 / 重建恢复
tests/v4/isolation/test_memory_ownership.py  跨作品隔离 + 边界守卫
```

