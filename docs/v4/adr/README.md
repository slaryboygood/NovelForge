# V4 Architecture Decision Records

> 阶段：**V4-00 Architecture**
> 状态约定：`Proposed`（已提出，未开工）/ `Accepted`（已批准，可在对应阶段实施）/ `Superseded`（被后续 ADR 取代）
> 规则：V4-00 期间所有 ADR 都是 `Proposed`；**批准发生在阶段开工时，而不是本文档写作时**。

| ADR | 标题 | Status | 关联阶段 |
| --- | --- | --- | --- |
| [ADR-001](ADR-001-canonical-service-layer.md) | Canonical Service Layer | Proposed | V4-01 |
| [ADR-002](ADR-002-llm-gateway-boundary.md) | LLM Gateway Boundary | Proposed | V4-02 |
| [ADR-003](ADR-003-canonical-writer-store.md) | Canonical Writer Store | Proposed | V4-06 |
| [ADR-004](ADR-004-journey-projection.md) | JourneyProjection | Proposed | V4-01 |
| [ADR-005](ADR-005-quality-contract.md) | Quality Contract | Proposed | V4-05 |
| [ADR-006](ADR-006-revision-model.md) | Revision Model | Proposed | V4-01 |
| [ADR-007](ADR-007-artifact-ownership.md) | Artifact Ownership | Proposed | V4-01 / V4-07 |
| [ADR-008](ADR-008-mcp-as-interface.md) | MCP as Interface | Proposed | V4-08 |
| [ADR-009](ADR-009-plugin-db-isolation.md) | Plugin DB Isolation | Proposed | V4-09 |
| [ADR-010](ADR-010-structured-generation.md) | Structured Generation | Proposed | V4-04 |

## 需要作者/产品决策的 ADR

| ADR | 待决内容 | 阻塞对象 |
| --- | --- | --- |
| ADR-003 | `novel/final/**`（69 个 tracked 正文文件）是否导入为 revision 0 | V4-06、V4-07 |
| ADR-007 | `project_id` 与 `novel_id` 的最终层级关系 | V4-01、V4-08 |

