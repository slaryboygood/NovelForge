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
| [ADR-012](ADR-012-unified-llm-gateway.md) | Unified LLM Gateway | **Accepted**（V4-02 实施完成） | V4-02 起 |
| [ADR-013](ADR-013-provider-config-and-secret-boundary.md) | Provider Configuration And Secret Boundary | **Accepted**（V4-02 实施完成） | V4-02 起 |
| [ADR-014](ADR-014-memory-is-derived-canon-remains-authoritative.md) | Memory Is Derived, Canon Remains Authoritative | **Accepted**（V4-03 实施完成） | V4-03 起 |
| [ADR-015](ADR-015-context-builder-owns-model-context-selection.md) | Context Builder Owns Model Context Selection | **Accepted**（V4-03 实施完成） | V4-03 起 |
| [ADR-016](ADR-016-story-blueprint-is-a-revisioned-node-graph.md) | Story Blueprint Is A Revisioned Node Graph | **Accepted**（V4-04 实施完成） | V4-04 起 |
| [ADR-017](ADR-017-generated-content-is-proposal-until-promoted.md) | Generated Content Is Proposal Until Promoted | **Accepted**（V4-04 实施完成） | V4-04 起 |
| [ADR-018](ADR-018-quality-is-gate-based-not-score-based.md) | Quality Is Gate-Based, Not Score-Based | **Accepted**（V4-05 实施完成） | V4-05 起 |
| [ADR-019](ADR-019-repair-is-minimal-scope-and-revisioned.md) | Repair Is Minimal-Scope And Revisioned | **Accepted**（V4-05 实施完成） | V4-05 起 |
| [ADR-020](ADR-020-quality-evidence-is-separate-from-story-truth.md) | Quality Evidence Is Separate From Story Truth | **Accepted**（V4-05 实施完成） | V4-05 起 |
| [ADR-021](ADR-021-editor-mutations-are-append-only-revisions.md) | Editor Mutations Are Append-Only Revisions | **Accepted**（V4-06 实施完成） | V4-06 起 |
| [ADR-022](ADR-022-quality-pass-does-not-mean-author-accepted.md) | Quality Pass Does Not Mean Author Accepted | **Accepted**（V4-06 实施完成） | V4-06 起 |
| [ADR-023](ADR-023-restore-creates-a-new-revision.md) | Restore Creates A New Revision | **Accepted**（V4-06 实施完成） | V4-06 起 |
| [ADR-024](ADR-024-delivery-is-revision-pinned.md) | Delivery Is Revision-Pinned | **Accepted**（V4-07 实施完成） | V4-07 起 |
| [ADR-025](ADR-025-accepted-and-quality-passed-are-independent-delivery-requirements.md) | Accepted And Quality-Passed Are Independent Delivery Requirements | **Accepted**（V4-07 实施完成） | V4-07 起 |
| [ADR-026](ADR-026-novelforge-package-is-a-selected-artifact-not-a-repository-backup.md) | NovelForge Package Is A Selected Artifact, Not A Repository Backup | **Accepted**（V4-07 实施完成） | V4-07 起 |
| [ADR-027](ADR-027-mcp-is-an-interface-adapter-not-a-business-layer.md) | MCP Is An Interface Adapter, Not A Business Layer | **Accepted**（V4-08 实施完成） | V4-08 起 |
| [ADR-028](ADR-028-mcp-mutations-preserve-revision-and-approval-semantics.md) | MCP Mutations Preserve Revision And Approval Semantics | **Accepted**（V4-08 实施完成） | V4-08 起 |

## 已被作者裁定的决策（原待决项）

| ADR | 待决内容 | 阻塞对象 |
| --- | --- | --- |
| ADR-003 / ADR-011 | `novel/final/**` 是否导入为正文 revision 0 | **已裁定：DELETE（不迁移、不归档、不导入）** |
| ADR-003 / ADR-011 | V4 的 canonical creative artifact 是什么 | **已裁定：Story Blueprint** |

## 仍待产品决定的 ADR

| ADR | 待决内容 | 阻塞对象 |
| --- | --- | --- |
| ADR-007 | `project_id` 与 `novel_id` 的最终层级关系 | V4-08 |
