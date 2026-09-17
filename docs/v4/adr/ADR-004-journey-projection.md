# ADR-004 — JourneyProjection as the Single Progress Source

```
Status   : Proposed
Date     : 2026-09-17
Context  : V4-00 Architecture
Related  : V4_ARCHITECTURE.md §6；V4_DELETION_PLAN.md（ui_flow 第二套公式）
```

## Context

V3 在验收中修过一次同类问题（NF-005：Landing 与 Command Center 的阶段 / 进度 / 下一步必须一致），
做法是把公式收敛到 `story_builder/v3_projection.py::_journey_projection()`：
Landing 卡片（`novel_card`）与 Command Center 都只消费它。

但仍然存在第二套推导：

```text
v3_projection.V3_STAGES          creation / world / characters / story / simulation / outline / review / export
ui_flow.py  STAGE_LABELS         design / occurred / output / governance（+ 独立 next_step 计算）
story_builder.models.StoryStep   十步目录（design tree）
```

这三者粒度不同（V3 阶段 / 页签分组 / 设计步骤），但**都由各自代码独立推导状态**。
Agent 与 MCP 接入后，任何一处不一致都会被外部观察到。

## Decision

`JourneyProjection`（由 `application/services/journey_service` 提供）是**唯一的**进度与下一步来源：

```text
Landing 卡片          ┐
Command Center        │
REST /guided-flow     ├→ journey_service（唯一公式）
MCP journey resource  │
UI 页签状态提示        ┘
```

* 页签分组（design / occurred / output / governance）与十步目录属于**展示层分类**，可以保留，
  但它们的「是否完成 / 下一步是什么」必须来自 JourneyProjection。
* 完成度只来自真实 state / validation / deterministic rules；LLM 不参与判定。

## Consequences

正面：Landing / Command Center / guided-flow / MCP 天然一致；性能问题只需优化一处。

代价：`ui_flow` 需要改为消费 journey_service（返回值形状保持不变，避免 UI 大改）。

## Alternatives considered

| 方案 | 为什么不选 |
| --- | --- |
| 每个入口各算一次 | 已经出过 NF-005，重复必然再次漂移 |
| 用 LLM 生成「下一步建议」 | 原则 1.3：完成度与下一步不由 LLM 决定 |

## Evidence

```text
src/novelforge/story_builder/v3_projection.py:1418  _journey_projection()（唯一入口，注释明确写 NF-005 要求）
src/novelforge/story_builder/v3_projection.py:1822  NF-005 修复注释：不再自己算，只裁剪 journey 投影
src/novelforge/story_builder/ui_flow.py:301/309     独立 stage_label / next_step 计算
src/novelforge/story_builder/v3_projection.py:67    V3_STAGES（第二套阶段词表）
```

