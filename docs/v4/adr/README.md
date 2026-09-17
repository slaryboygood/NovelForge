# V4 Architecture Decision Records

> 阶段：**V4-00 Architecture** → 已进入 **V4-01 Boundary Foundation**（ADR-003 被 ADR-011 取代）
> 状态约定：`Proposed`（已提出，未开工）/ `Accepted`（已批准，可在对应阶段实施）/ `Superseded`（被后续 ADR 取代）
> 规则：ADR 在对应阶段开工时由作者批准；**批准后才可实施**。

| ADR | 标题 | Status | 关联阶段 |
| --- | --- | --- | --- |
| [ADR-001](ADR-001-canonical-service-layer.md) | Canonical Service Layer | Proposed | V4-01 |
| [ADR-002](ADR-002-llm-gateway-boundary.md) | LLM Gateway Boundary | Proposed | V4-02 |
| [ADR-003](ADR-003-canonical-writer-store.md) | ~~Canonical Writer Store~~ | **Superseded by ADR-011** | — |
| [ADR-004](ADR-004-journey-projection.md) | JourneyProjection | Proposed | V4-01 |
| [ADR-005](ADR-005-quality-contract.md) | Quality Contract | Proposed | V4-05 |
| [ADR-006](ADR-006-revision-model.md) | Revision Model | Proposed | V4-01 |
| [ADR-007](ADR-007-artifact-ownership.md) | Artifact Ownership | Proposed | V4-01 / V4-07 |
| [ADR-008](ADR-008-mcp-as-interface.md) | MCP as Interface | Proposed | V4-08 |
| [ADR-009](ADR-009-plugin-db-isolation.md) | Plugin DB Isolation | Proposed | V4-09 |
| [ADR-010](ADR-010-structured-generation.md) | Structured Generation | Proposed | V4-04 |
| [ADR-011](ADR-011-story-blueprint-primary-artifact.md) | Story Blueprint Is The Primary Creative Artifact | **Accepted**（V4-01 作者决策） | V4-01 起 |

## 已被作者裁定的决策（原待决项）

| ADR | 待决内容 | 阻塞对象 |
| --- | --- | --- |
| ADR-003 / ADR-011 | `novel/final/**` 是否导入为正文 revision 0 | **已裁定：DELETE（不迁移、不归档、不导入）** |
| ADR-003 / ADR-011 | V4 的 canonical creative artifact 是什么 | **已裁定：Story Blueprint** |

## 仍待产品决定的 ADR

| ADR | 待决内容 | 阻塞对象 |
| --- | --- | --- |
| ADR-007 | `project_id` 与 `novel_id` 的最终层级关系 | V4-08 |
