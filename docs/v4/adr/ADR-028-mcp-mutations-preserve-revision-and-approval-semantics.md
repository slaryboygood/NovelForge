# ADR-028 — MCP Mutations Preserve Revision And Approval Semantics

```
Status    : Accepted（V4-08 实施完成）
Date      : 2026-09-18
Context   : V4-08 MCP Server & Machine Interface
Related   : ADR-006（revision model）；ADR-019（repair is revisioned）；
            ADR-022（quality pass ≠ accepted）；ADR-024（delivery is revision-pinned）；
            V4_MCP_CONTRACT.md §8–§9
```

## Context

把能力暴露给外部 Agent 后，最容易被"简化"掉的就是约束：

```text
· Agent 图方便 → 默认导出 current（可能 proposed / unevaluated）
· 重试 → 产生第二个 revision / 第二份 package
· 冲突 → 直接覆盖（静默丢作者内容）
· 生成完成 → 顺手 accept（绕过作者审批）
· repair 不收敛 → MCP 扩大 scope 自己去改更多节点
```

## Decision

1. **`expected_revision` 必须透传**：所有针对已有节点的 mutation tool 都要求它
   （新建顶层节点除外，但要求 `idempotency_key` 作为等价并发契约）。
   冲突返回 `MCP_REVISION_CONFLICT`，并保留业务层的 `conflict_diff`；**不自动 merge**。
2. **`idempotency_key` 必须透传**：generate / patch / rewrite / repair / accept /
   restore / deliver 全部支持；重试不产生第二个 revision 或 package。
3. **`preserve` 是硬约束**：MCP 不提供任何绕过路径；违反 → `MCP_PRESERVE_VIOLATION`，
   且不发生写入。
4. **审批独立**：`accept_revision` / `reject_revision` 只能显式调用；
   `quality pass ≠ accepted`；任何 tool 都不会自动接受；reject 只记录评审决定。
5. **human review 原样返回**：`needs_human_review` / 无法自动修复 →
   `MCP_OPERATION_REQUIRES_REVIEW`，MCP 不扩大 repair scope、不重新设计故事结构。
6. **交付默认 accepted 且 revision-pinned**：`deliver_blueprint` 默认
   `selection_mode="accepted"`，产出由 DeliverySnapshot 钉住；
   dry-run 支持且 0 LLM 调用。

## Consequences

正面：

* Agent 无法通过协议层削弱作者控制权（审批 / 冲突 / preserve）；
* 重试安全（幂等），并发安全（revision 冲突显式）；
* 交付物仍可自证来源（V4-07 的 snapshot / manifest 语义在 MCP 下不变）。

代价：

* 客户端需要携带 `expected_revision` / `idempotency_key`（多两个必填/推荐参数）；
* 需要显式 accept 才能进入 accepted（这正是设计意图）。

## Alternatives considered

| 方案 | 为什么不选 |
| --- | --- |
| MCP 自动 accept 生成结果 | 违反 ADR-022；作者失去最终决定权 |
| 冲突时自动重放（用最新 revision 重试） | 静默覆盖作者/其他 Agent 的改动（ADR-021） |
| 默认导出 current | 可能包含 proposed / unevaluated / rejected（ADR-024） |
| repair 不收敛时自动扩大 scope | 违反 §24；会改动未授权节点 |

## Evidence

```text
src/novelforge/interfaces/mcp/tools/editor.py     patch/rewrite/restore 要求 expected_revision
src/novelforge/interfaces/mcp/tools/delivery.py   默认 accepted；dry_run 透传
src/novelforge/interfaces/mcp/tools/quality.py    repair 不收敛 → MCP_OPERATION_REQUIRES_REVIEW
src/novelforge/interfaces/mcp/dispatch.py         cause 保留业务 code（不丢约束语义）
tests/mcp/test_mcp_tools.py                       冲突 / 幂等 / preserve / dry_run / 审批
tests/mcp/test_mcp_server.py                      SDK in-process 全链路（含 delivery pinning）
```

