# ADR-017 — Generated Content Is Proposal Until Promoted

```
Status    : Accepted（V4-04 实施完成）
Date      : 2026-09-17
Context   : V4-04 Structured Story Blueprint Generation
Related   : ADR-014（Memory is derived / Canon authoritative）；ADR-016（Blueprint node graph）；
            V4_BLUEPRINT_CONTRACT.md §5
```

## Context

V4-04 是 V4 第一次**真正生成核心内容**。这带来一个直接风险：

```text
LLM 说"这个角色死了"
   → 如果生成结果被当作事实
   → Canon / StoryState 被无声改写
```

项目已经有一条硬边界：`LLM is not the database`（ADR-002）、`design intent != canon fact`
（AGENTS.md §15）。V4-03 又把 Memory 定为派生层。因此必须明确：**生成结果的地位是什么**。

## Decision

1. 生成结果一律是 **proposal**：`BlueprintNode.status` 默认 `"proposed"`，
   只有作者/显式业务规则可以把它变成 `"accepted"`（`status` 允许
   `proposed → draft → accepted → superseded`，`accepted` 不可回退）。
2. 生成**永不**写入 Canon / StoryState：`Scene Card` 里的
   `state_transition_intent` 只表达「计划中的状态变化」，不是已发生事实；
   promotion 由未来 execution 层 + 业务规则决定（V4-05 之后）。
3. 生成结果必须可追溯：每个节点带 `generation_contract`(+version)、`context_digest`、
   `source_ids`、`provenance`（model / provider / context blocks / parent revision）。
4. provider 不可用时**明确失败**（`GenerationUnavailableError`），
   不生成低质量硬编码创意来"兜底"（§42）；V3 的确定性规则生成器降级为
   compatibility（登记移除条件）。

## Consequences

正面：

* Canon / StoryState 的权威性在 V4 首次引入生成能力时保持不变；
* 质量闭环（V4-05）可以放心评估 proposal，而不必担心污染事实；
* 作者拥有明确的接受/拒绝点（V4-06 的 Blueprint Editor 会消费它）。

代价：

* 需要显式的 promotion 流程（本阶段只提供 `accept()` API）；
* 生成结果不能直接驱动 StoryState 变化，需要 execution 层（后续阶段）。

## Alternatives considered

| 方案 | 为什么不选 |
| --- | --- |
| 生成即事实（直接写 StoryState） | 违反 AGENTS.md §15 与 ADR-002/014；一次幻觉就污染作品事实 |
| 生成结果只存自由文本，由作者手工搬运 | 无法校验 / 无法修订 / 无法被 MCP 与 Agent 消费 |
| 用 quality_status 代替 status | 质量结论与生命周期是两件事（V4-05 才不会退化成"分数即事实"） |

## Evidence

```text
src/novelforge/blueprint/contracts.py   NodeStatus 默认 proposed；quality_status 独立字段
src/novelforge/blueprint/lifecycle.py   状态流转表（accepted → superseded 单向）
src/novelforge/generation/service.py    accept() 是唯一的接受入口；不写 Canon / StoryState
src/novelforge/generation/errors.py     GenerationUnavailableError（明确失败，不降级创作）
tests/generation/test_context_integration.py  Canon DB fingerprint 前后不变
tests/generation/test_generation_service.py   accept 后的状态与 revision 历史
```

