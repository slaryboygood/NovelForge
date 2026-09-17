# ADR-022 — Quality Pass Does Not Mean Author Accepted

```
Status    : Accepted（V4-06 实施完成）
Date      : 2026-09-18
Context   : V4-06 Blueprint Editor & Revision Workflow
Related   : ADR-017（generated content is proposal until promoted）；
            ADR-018（quality is gate-based）；ADR-019（repair is revisioned）；
            V4_EDITOR_CONTRACT.md §7、§10
```

## Context

有了 Quality Gate 之后，最自然的偷懒实现是：

```text
quality_status = passed  →  自动把节点标记为 accepted
```

这条路的后果很具体：

1. 作者失去最终决定权（AI 生成 + 自动通过 = 静默接受）；
2. Canon / 世界规则允许但作者不喜欢的方案会被固化；
3. 质量结论变化（上游 revision 变化 → stale）会让"已接受"变得自相矛盾。

## Decision

1. **两条事实互相独立**：

   ```text
   quality_status ∈ unevaluated / passed / passed_with_issues / failed / blocked
   BlueprintNode.status ∈ proposed / draft / accepted / superseded
   ```

   质量通过不能写 `accepted`；`accepted` 也不代表质量永久通过。
2. **Accept / Reject 由 Editor / Application 层拥有**（`EditorService.accept` / `reject`），
   Quality 只说"有没有 issue"，不决定作者接不接受。
3. **编辑或 AI 改写产生的新 revision 一律 `proposed` + `quality_status=unevaluated`**，
   需要作者显式 `accept` 才进入 `accepted`。
4. **Reject 是 review 决定，不是 lifecycle 状态**（见 ADR-021 与
   `V4_EDITOR_CONTRACT.md` §7 的评估结论）：revision 保留，Blueprint status 不变。

## Consequences

正面：

* 作者始终是最终决定者；AI 只能提议；
* 质量结论可以独立演进（上游变化 → stale / failed）而不破坏审批语义；
* 审计清楚区分"系统判定"与"作者决定"。

代价：

* 需要显式的接受动作（UI 属 V4-10）；
* `accepted` 节点仍可能需要重新评估质量（不是冻结）。

## Alternatives considered

| 方案 | 为什么不选 |
| --- | --- |
| quality passed → 自动 accepted | 静默接受；违反 ADR-017 的 proposal 语义 |
| 把 quality_status 直接当审批字段 | 两种语义混在一个字段，无法同时表达"质量"与"作者决定" |
| accepted 时冻结质量 | 上游 revision 变化会让冻结结论失真（§70） |

## Evidence

```text
src/novelforge/editor/service.py       accept 走 repository.set_status；不改 quality_status
src/novelforge/editor/service.py       rewrite / patch 新 revision：proposed + unevaluated
src/novelforge/editor/service.py       reject 只写 ReviewDecision（status="recorded"）
src/novelforge/application/services/editor.py  AcceptanceResult.acceptance_note
tests/editor/test_accept_reject.py     quality pass ≠ accepted；accepted 不被静默覆盖
tests/editor/test_quality_integration.py  编辑后 quality_status=unevaluated
```

