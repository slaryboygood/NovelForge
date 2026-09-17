# ADR-016 — Story Blueprint Is A Revisioned Node Graph

```
Status    : Accepted（V4-04 实施完成）
Date      : 2026-09-17
Context   : V4-04 Structured Story Blueprint Generation
Related   : ADR-011（Story Blueprint is the primary artifact）；ADR-006（Revision）；
            V4_BLUEPRINT_CONTRACT.md；ADR-017（proposal until promoted）
```

## Context

ADR-011 把 canonical creative artifact 定为 Story Blueprint，但没有说清它的**形态**。
两条路可选：

```text
(a) 一个 JSON blob（整本蓝图一次生成 / 一次保存）
(b) 一组可独立 revision 的节点
```

V3 的教训支持 (b)：

* `outline_forge` 一次性生成整条四级大纲 → 任何局部问题（例如一章标题语义重复，NF-003）
  都只能整条重锻；
* `story_builder_routes.py` 的整包导出/版本机制说明「按节点独立版本」在实现上完全可行；
* V4-05 的 Targeted Repair 明确要求「Scene 有问题只改 Scene」。

## Decision

Story Blueprint 是**节点图**（`src/novelforge/blueprint/`）：

```text
BlueprintRoot（隐含：整个 novel 的节点集合，由 repository 索引表达）
├── premise / theme
├── world
├── character ── character_arc
├── story_arc ── structural_unit(act|volume|arc) ── chapter ── scene
├── causal_link（节点之间的因果/回收关系）
└── setup / payoff
```

规则：

1. 每个节点独立 `revision`（append-only），独立 `validate`，独立 `regenerate`；
2. 节点带 `parent_id` / `parent_revision` / `sequence`；父子与顺序是**结构化字段**，
   不靠文件名或标题排序；
3. canonical store 是 `BlueprintRepository`（`novel/authoring/story_engine/blueprint/<novel_id>/`），
   路径经 `persistence.paths`；带 `BLUEPRINT_SCHEMA_VERSION`；
4. 禁止默认流程「一次生成整本大纲」（§6）：生成按 `premise → world/characters → arcs →
   story arc → units → chapters → scenes → links` 逐级进行；
5. 生成任务是版本化 contract（`blueprint.<task>.v1`），不复用 `generic_story_generator`。

## Consequences

正面：

* 局部重生成（一个 Character Arc / 一个 Chapter Card / 一个 Scene Card）与
  `expected_revision` 冲突检测天然成立；
* V4-05 的 Targeted Repair 有明确的 scope 单位与 preserve 边界；
* 导出 / MCP / Agent 可以按节点寻址（`node_id@revision`）。

代价：

* 需要维护索引（current revision / children 顺序 / idempotency）；
* 生成一层结构需要更多次模型调用（换取可控性与可修订性）；
* 节点之间的引用必须显式校验（否则会退化回"文本里互相提到"）。

## Alternatives considered

| 方案 | 为什么不选 |
| --- | --- |
| 单一 JSON blob | 无法局部重生成；一次失败全部重来；repair 只能整本重写 |
| 复用 `OutlinePackage` 作为唯一载体 | 它只有"大纲条目"概念，缺少 causal / setup-payoff / state transition intent 等结构 |
| 把节点存在 Memory 层 | Memory 是派生层（ADR-014）；Blueprint 是 canonical truth，必须有自己的 store |

## Evidence

```text
src/novelforge/blueprint/contracts.py    节点与 12 类 payload（严格模型）
src/novelforge/blueprint/repository.py   append-only revision + index + idempotency
src/novelforge/blueprint/validation.py   schema / parent / 引用 / ownership / sequence
src/novelforge/generation/service.py     逐级生成 + 局部重生成 + accept
tests/generation/test_generation_pipeline.py  golden 蓝图（parent-child / sequence / links）
tests/generation/test_blueprint_repository.py revision / idempotency / 状态流转
```

