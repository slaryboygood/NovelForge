---
name: novelforge-v4.0.1.memory.understand-truth-precedence
description: 掌握 NovelForge 的真相优先级：Canon / StoryState / Blueprint 是真相，Memory 只是派生视图，禁止倒置。
---

# understand-truth-precedence

- **Skill ID**: `novelforge-v4.0.1.memory.understand-truth-precedence`
- **Version**: 1（baseline `V4.0.1`）
- **Capability Module**: `memory`
- **Product owner**: `src/novelforge/memory/__init__.py`（Public Contract）+ ADR-014

## Purpose

防止最常见的一类结构错误：把派生记忆当成事实来源，或在多处维护"同一份真相"。

## Use when

- 需要判断某个数据能不能写、能不能当作"已经发生"。
- 审查某个流程是否偷偷建立了第二套 truth。

## Do not use when

- 只是想读数据 → 用对应模块的 inspect skill。

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
Application  novelforge.memory Public Contract（MemoryService / ContextBuilder）
MCP          N/A
```

## Procedure

```text
1 判断数据属于哪一层：
   Canon / StoryState          → 已发生事实（frozen 边界，V4 只读）
   Story Blueprint             → 计划真相（作者可改，append-only revision）
   Memory / ContextBundle      → 派生视图（可重建、可失效）
   Quality / Delivery          → 结论与产物（各有 owner，均不反向写真相）
2 写入前问：这个操作会不会制造第二份真相？会 → 停止，改为引用 + 派生
3 引用时带 source_id + revision（可追溯），不带 → 不合格
4 如果发现真相层级被违反，记录到 docs/v4/V4_0_1_SKILL_GAPS.md（不要顺手改 runtime）
```

## Expected result

能正确回答：

```text
· 能不能用 memory 改设定？不能（派生视图，ADR-014）
· 能不能把 future planning 写成 Canon？不能（PLANNING != OCCURRED TRUTH）
· 能不能让 quality 结论直接改节点内容？不能（evaluator 只读，修复走 Repair Contract）
· 能不能让 delivery 反推 revision？不能（delivery 只读 + revision-pinned）
```

## Verification

```text
· 交叉核对 docs/v4/adr/ADR-014、ADR-017、ADR-019、ADR-020、ADR-024
· 交叉核对 tests/v4/isolation/test_memory_ownership.py（真相归属守卫）
· 交叉核对 tests/memory/test_invalidation.py（记忆可失效 / 可重建）
```

## Common failures

| 现象 | 原因 | 处理 |
| --- | --- | --- |
| 同一概念出现两份不同数据 | 建立第二套 truth | 收敛到 canonical owner，另一个改为派生 |
| 生成结果引用了不存在的事实 | 把 proposal 当事实 | 检查是否越界写 Canon / StoryState |
| 记忆与当前 revision 不一致 | 未刷新 | `refresh_staleness` / `rebuild` |

## Safety / invariants

```text
TRUTH_PRECEDENCE 不可倒置
任何"为了让流程跑通"的真相捷径都属于 architecture exception，必须显式报告
```

## Side effects

无。

## Related skills

`inspect-derived-memory`、`build-generation-context`、
`novelforge-v4.0.1.canon.understand-canon-boundary`（若存在）、
`novelforge-v4.0.1.story-state.understand-story-state-boundary`

## Source references

```text
docs/v4/adr/ADR-014-memory-is-derived-canon-remains-authoritative.md
docs/v4/adr/ADR-015-context-builder-owns-model-context-selection.md
docs/v4/V4_MEMORY_ARCHITECTURE.md §2
tests/v4/isolation/test_memory_ownership.py
```
