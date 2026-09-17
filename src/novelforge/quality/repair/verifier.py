"""Repair Verifier（V4-05 §37–§38、§44、§64）。

```text
new revision → 重新执行受影响 Gate → 确认原 issue 消失 → 确认没有产生 blocker regression
```

模型说"修好了"不算数：只有**重新评估过**才算数。
Verifier 只复核 blast radius 覆盖的 scope + gates（§43：不是整个 Blueprint）。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from novelforge.blueprint import BlueprintRepository

from ..aggregation import build_usage
from ..contracts import QualityIssue, QualityPolicy, QualityReport
from ..errors import QualityScopeError
from ..store import QualityStore
from .contracts import RepairPlan, VerificationResult


class RepairVerifier:
    """对修复结果做事后验证（不写 Blueprint，只写 quality store 的 issue 状态）。"""

    def __init__(self, quality: Any, *, project_root: Path | str | None = None,
                 novel_id: str = "", repository: BlueprintRepository | None = None,
                 store: QualityStore | None = None) -> None:
        self.quality = quality
        self.novel_id = str(novel_id or getattr(quality, "novel_id", "") or "")
        if not self.novel_id:
            raise QualityScopeError("RepairVerifier 需要显式 novel_id")
        self.project_root = Path(project_root or getattr(quality, "project_root", "."))
        self.repository = repository or getattr(quality, "repository", None) or \
            BlueprintRepository(self.project_root, self.novel_id)
        self.store = store or getattr(quality, "store", None) or \
            QualityStore(self.project_root, self.novel_id)

    # ------------------------------------------------------------------ 验证
    def verify(self, *, before_report: QualityReport,
               plan: RepairPlan | None = None,
               issue_ids: Iterable[str] = (), gates: Iterable[str] = (),
               node_ids: Iterable[str] = (), before_revisions: Mapping[str, int] | None = None,
               policy: QualityPolicy | None = None,
               use_cache: bool = False) -> VerificationResult:
        if before_report.novel_id != self.novel_id:
            raise QualityScopeError(
                f"拒绝跨作品验证：{before_report.novel_id} != {self.novel_id}")

        original = self._original_issue_ids(before_report, plan, issue_ids)
        resolved_policy = policy or QualityPolicy()
        # 复核 = blast radius gates ∪ policy 要求评估的 gate（否则无法判定 passed）
        resolved_gates = tuple(dict.fromkeys(
            list(gates)
            or list(plan.blast_radius.gates if plan and plan.blast_radius else ())
            or [issue.gate for issue in before_report.issues]
            or ["Q0"]))
        resolved_gates = tuple(dict.fromkeys(
            [*resolved_gates, *resolved_policy.required_gates]))
        resolved_nodes = tuple(node_ids) or (plan.blast_radius.scope
                                             if plan and plan.blast_radius else ())

        scope = (self.quality.build_scope(node_ids=resolved_nodes, kind="changed")
                 if resolved_nodes else
                 self.quality.build_scope(node_ids=original_nodes(before_report),
                                          kind="changed"))
        after = self.quality.evaluate(scope, policy=policy, gates=resolved_gates,
                                      use_cache=use_cache)

        after_ids = {issue.issue_id for issue in after.issues}
        before_ids = {issue.issue_id for issue in before_report.issues}
        remaining = tuple(sorted(set(original) & after_ids))
        resolved = tuple(sorted(set(original) - after_ids))
        # regression 只统计"修复前完全不存在"的 issue（避免把既存问题误判为回归）
        new_ids = tuple(sorted(after_ids - before_ids))
        new_blocking = tuple(issue.issue_id for issue in after.issues
                             if issue.issue_id in set(new_ids)
                             and (issue.severity == "blocker"
                                  or resolved_policy.blocks(issue.severity)))
        if new_blocking:
            status = "regression"
        elif remaining:
            status = "partial"
        elif not original:
            status = "unresolved"
        else:
            status = "resolved"

        before_rev = dict(before_revisions or {})
        if not before_rev and plan is not None:
            before_rev = {step.node_id: step.expected_revision
                          for step in plan.steps}
        after_rev = {node_id: int(self.repository.current_revision(node_id) or 0)
                     for node_id in before_rev}
        self._sync_issue_status(before_report, after, resolved=resolved,
                                remaining=remaining)
        return VerificationResult(
            novel_id=self.novel_id, status=status,
            original_issue_ids=tuple(sorted(original)),
            resolved_issue_ids=resolved, remaining_issue_ids=remaining,
            new_issue_ids=new_ids, before_revisions=dict(sorted(before_rev.items())),
            after_revisions=dict(sorted(after_rev.items())),
            gates_rechecked=tuple(resolved_gates),
            before_report_id=before_report.report_id,
            after_report_id=after.report_id, quality_status=after.status,
            usage=build_usage(verification=after.usage.get("evaluation")),
            notes=((f"new_blocking={sorted(new_blocking)}",) if new_blocking else ()),
            report=after)

    # ------------------------------------------------------------------ 内部
    @staticmethod
    def _original_issue_ids(before_report: QualityReport, plan: RepairPlan | None,
                            issue_ids: Iterable[str]) -> tuple[str, ...]:
        explicit = tuple(str(value) for value in issue_ids if value)
        if explicit:
            return explicit
        if plan is not None and plan.issue_ids:
            return tuple(sorted(set(plan.issue_ids)))
        return tuple(sorted({issue.issue_id for issue in before_report.issues
                             if issue.status in ("open", "repairing")}))

    def _sync_issue_status(self, before: QualityReport, after: QualityReport,
                           *, resolved: Sequence[str],
                           remaining: Sequence[str]) -> None:
        for issue_id in resolved:
            self.store.update_issue_status(issue_id, "resolved",
                                           note="repair verified")
        for issue_id in remaining:
            self.store.update_issue_status(issue_id, "open", note="repair failed")


def original_nodes(report: QualityReport) -> tuple[str, ...]:
    """before report 里被判定过问题的节点（用于无 plan 时的复核 scope）。"""

    return tuple(sorted({node_id for issue in report.issues
                         for node_id in issue.scope.node_ids if node_id}))


def issues_by_id(issues: Iterable[QualityIssue]) -> dict[str, QualityIssue]:
    return {issue.issue_id: issue for issue in issues}


__all__ = ["RepairVerifier", "issues_by_id", "original_nodes"]
