"""ReviewService / QualityLoopService —— Quality Closed Loop 的业务入口（V4-05 §55–§58）。

```text
ReviewService       统一暴露 evaluate / list_issues / repair_issue / verify_repair
QualityLoopService  Evaluate → Plan → Repair → Verify 的闭环编排（受 max_repair_rounds 限制）
```

接口层（REST / MCP / Agent / UI）**只**调用本服务；不得 import evaluator / repair internals。

边界（§34）：

```text
application.services.review → quality（Public Contract）+ generation（Public Contract）
```

编排只发生在应用层：`quality` 与 `generation` 互不依赖。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from novelforge.blueprint import BlueprintRepository
from novelforge.quality import (
    QualityIssue,
    QualityPolicy,
    QualityReport,
    QualityScope,
    QualityService,
    RepairExecutor,
    RepairPlan,
    RepairPlanner,
    RepairResult,
    RepairVerifier,
    VerificationResult,
    build_usage,
    merge_usage,
    summarize_report,
    usage_totals,
)
from novelforge.quality.store import QualityStore

#: 闭环终态
LOOP_STATUSES: tuple[str, ...] = ("passed", "planned", "repaired",
                                  "needs_human_review")


@dataclass(frozen=True)
class RepairOutcome:
    """一次 repair 请求的完整结果（plan → 可选 execute → 可选 verify）。"""

    plan: RepairPlan
    result: RepairResult | None = None
    verification: VerificationResult | None = None

    @property
    def status(self) -> str:
        if self.plan.dry_run or self.result is None:
            return "planned"
        if self.verification is not None:
            return self.verification.status
        return self.result.status

    def as_dict(self) -> dict[str, Any]:
        return {"status": self.status, "plan": self.plan.as_dict(),
                "result": self.result.as_dict() if self.result else None,
                "verification": (self.verification.as_dict()
                                 if self.verification else None)}


@dataclass(frozen=True)
class QualityLoopResult:
    """闭环编排结果。"""

    novel_id: str
    status: str
    rounds: int
    report: QualityReport
    plans: tuple[RepairPlan, ...] = ()
    results: tuple[RepairResult, ...] = ()
    verification: VerificationResult | None = None
    usage: Mapping[str, Any] = field(default_factory=dict)
    needs_human_review: bool = False
    reasons: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        return {"novel_id": self.novel_id, "status": self.status,
                "rounds": self.rounds,
                "needs_human_review": self.needs_human_review,
                "reasons": list(self.reasons),
                "report": summarize_report(self.report),
                "plans": [plan.as_dict() for plan in self.plans],
                "results": [result.as_dict() for result in self.results],
                "verification": (self.verification.as_dict()
                                 if self.verification else None),
                "usage": dict(self.usage)}


class ReviewService:
    """质量评审 + 定向修复的业务入口（Application Service）。"""

    def __init__(self, project_root: Path | str, novel_id: str, *,
                 quality: QualityService, generation: Any = None,
                 repository: BlueprintRepository | None = None,
                 store: QualityStore | None = None,
                 planner: RepairPlanner | None = None,
                 executor: RepairExecutor | None = None,
                 verifier: RepairVerifier | None = None,
                 policy: QualityPolicy | None = None) -> None:
        self.project_root = Path(project_root)
        self.novel_id = str(novel_id)
        self.quality = quality
        self.generation = generation
        self.repository = repository or getattr(quality, "repository", None) or \
            BlueprintRepository(self.project_root, self.novel_id)
        self.store = store or getattr(quality, "store", None) or \
            QualityStore(self.project_root, self.novel_id)
        self.policy = policy or QualityPolicy()
        self.planner = planner or RepairPlanner(self.project_root, self.novel_id,
                                                repository=self.repository)
        self.executor = executor or (RepairExecutor(
            self.project_root, self.novel_id, generation=generation,
            repository=self.repository, store=self.store)
            if generation is not None else None)
        self.verifier = verifier or RepairVerifier(
            quality, project_root=self.project_root, novel_id=self.novel_id,
            repository=self.repository, store=self.store)

    # ------------------------------------------------------------------ 评估
    def evaluate(self, scope: QualityScope | None = None, *,
                 policy: QualityPolicy | None = None,
                 gates: Sequence[str] | None = None,
                 node_ids: Iterable[str] = (), kind: str = "",
                 prior_issues: Sequence[QualityIssue] = (),
                 use_cache: bool = True) -> QualityReport:
        resolved_scope = scope
        if resolved_scope is None and node_ids:
            resolved_scope = self.quality.build_scope(node_ids=node_ids,
                                                      kind=kind or "changed")
        return self.quality.evaluate(resolved_scope, policy=policy or self.policy,
                                     gates=gates, prior_issues=prior_issues,
                                     use_cache=use_cache)

    def list_issues(self, *, status: str = "", gate: str = "") -> list[dict[str, Any]]:
        return self.quality.list_issues(status=status, gate=gate)

    def issues_for_node(self, node_id: str) -> list[dict[str, Any]]:
        return self.quality.issues_for_node(node_id)

    def latest_report(self) -> dict[str, Any]:
        return self.quality.latest_report()

    def stats(self) -> dict[str, Any]:
        return self.quality.stats()

    def project_quality_status(self, *, node_ids: Iterable[str] = (),
                               report: QualityReport | None = None
                               ) -> dict[str, str]:
        return self.quality.project_quality_status(report, node_ids=node_ids)

    def registered_gates(self) -> tuple[str, ...]:
        return self.quality.registry.gates()

    # ------------------------------------------------------------------ 修复
    def plan_repair(self, issues: Sequence[QualityIssue] | None = None, *,
                    policy: QualityPolicy | None = None, dry_run: bool = True,
                    strict: bool = False,
                    expected_revisions: Mapping[str, int] | None = None
                    ) -> RepairPlan:
        resolved = list(issues) if issues is not None else \
            list(self.store.issue_objects(status="open"))
        return self.planner.plan(resolved, dry_run=dry_run,
                                 expected_revisions=expected_revisions,
                                 strict=strict)

    def execute_repair(self, plan: RepairPlan, *,
                       expected_revisions: Mapping[str, int] | None = None,
                       idempotency_key: str = "", model_policy: Any = None,
                       dry_run: bool | None = None) -> RepairResult:
        if self.executor is None:
            raise RuntimeError(
                "ReviewService 未注入 generation：repair 必须经 generation Public Contract")
        return self.executor.execute(plan, expected_revisions=expected_revisions,
                                     idempotency_key=idempotency_key,
                                     model_policy=model_policy, dry_run=dry_run)

    def verify_repair(self, *, before_report: QualityReport,
                      plan: RepairPlan | None = None,
                      issue_ids: Iterable[str] = (),
                      gates: Iterable[str] = (),
                      node_ids: Iterable[str] = (),
                      policy: QualityPolicy | None = None,
                      before_revisions: Mapping[str, int] | None = None
                      ) -> VerificationResult:
        return self.verifier.verify(before_report=before_report, plan=plan,
                                    issue_ids=issue_ids, gates=gates,
                                    node_ids=node_ids, policy=policy,
                                    before_revisions=before_revisions)

    def repair_issue(self, issue_ids: Iterable[str], *,
                     before_report: QualityReport | None = None,
                     policy: QualityPolicy | None = None, dry_run: bool = True,
                     strict: bool = False, idempotency_key: str = "",
                     model_policy: Any = None,
                     expected_revisions: Mapping[str, int] | None = None
                     ) -> RepairOutcome:
        """对指定 issue 执行「计划（可选 dry-run）→ 执行 → 验证」。"""

        wanted = tuple(str(value) for value in issue_ids if value)
        issues = self._resolve_issues(wanted, before_report)
        plan = self.planner.plan(issues, dry_run=dry_run,
                                 expected_revisions=expected_revisions,
                                 strict=strict)
        if dry_run or plan.status != "planned":
            return RepairOutcome(plan=plan)
        baseline = before_report or self.evaluate(
            node_ids=plan.blast_radius.scope or plan.target_node_ids,
            kind="changed", policy=policy)
        result = self.execute_repair(plan, expected_revisions=expected_revisions,
                                     idempotency_key=idempotency_key,
                                     model_policy=model_policy, dry_run=False)
        if result.status not in ("applied", "idempotent_replay", "partial"):
            return RepairOutcome(plan=plan, result=result)
        verification = self.verify_repair(
            before_report=baseline, plan=plan, policy=policy,
            before_revisions=result.before_revisions or None)
        return RepairOutcome(plan=plan, result=result, verification=verification)

    # ------------------------------------------------------------------ 闭环
    def evaluate_and_repair(self, scope: QualityScope | None = None, *,
                            policy: QualityPolicy | None = None,
                            gates: Sequence[str] | None = None,
                            node_ids: Iterable[str] = (), kind: str = "",
                            dry_run: bool = False,
                            issue_ids: Iterable[str] = (),
                            max_rounds: int | None = None) -> QualityLoopResult:
        loop = QualityLoopService(self, policy=policy or self.policy)
        return loop.run(scope, policy=policy, gates=gates, node_ids=node_ids,
                        kind=kind, dry_run=dry_run, issue_ids=issue_ids,
                        max_rounds=max_rounds)

    # ------------------------------------------------------------------ 内部
    def _resolve_issues(self, issue_ids: Sequence[str],
                        before_report: QualityReport | None) -> list[QualityIssue]:
        if before_report is not None and issue_ids:
            wanted = set(issue_ids)
            rows = [issue for issue in before_report.issues
                    if issue.issue_id in wanted]
            if rows:
                return rows
        if issue_ids:
            by_id = {issue.issue_id: issue
                     for issue in self.store.issue_objects()}
            return [by_id[value] for value in issue_ids if value in by_id]
        if before_report is not None:
            return [issue for issue in before_report.issues
                    if issue.status in ("open", "repairing")]
        return list(self.store.issue_objects(status="open"))


class QualityLoopService:
    """Evaluate → Plan → Repair → Verify 的闭环编排（§56）。"""

    def __init__(self, review: ReviewService, *,
                 policy: QualityPolicy | None = None,
                 max_repair_rounds: int | None = None) -> None:
        self.review = review
        self.policy = policy or review.policy
        self.max_repair_rounds = max_repair_rounds

    def run(self, scope: QualityScope | None = None, *,
            policy: QualityPolicy | None = None,
            gates: Sequence[str] | None = None,
            node_ids: Iterable[str] = (), kind: str = "",
            dry_run: bool = False, issue_ids: Iterable[str] = (),
            max_rounds: int | None = None) -> QualityLoopResult:
        resolved_policy = policy or self.policy
        limit = (max_rounds if max_rounds is not None else self.max_repair_rounds)
        if limit is None:
            limit = resolved_policy.max_repair_rounds
        wanted = {str(value) for value in issue_ids if value}

        report = self.review.evaluate(scope, policy=resolved_policy, gates=gates,
                                      node_ids=node_ids, kind=kind)
        plans: list[RepairPlan] = []
        results: list[RepairResult] = []
        reasons: list[str] = []
        verification: VerificationResult | None = None
        usage = build_usage(evaluation=report.usage.get("evaluation"))

        if report.status == "passed":
            return QualityLoopResult(novel_id=self.review.novel_id, status="passed",
                                     rounds=0, report=report, usage=usage)

        rounds = 0
        while rounds < max(0, int(limit)):
            open_issues = [issue for issue in report.issues
                           if issue.status in ("open", "repairing")
                           and (not wanted or issue.issue_id in wanted)]
            if not open_issues:
                reasons.append("没有可自动修复的 open issue（其余需人工决定）")
                break
            plan = self.review.planner.plan(open_issues, dry_run=dry_run)
            plans.append(plan)
            if dry_run:
                return QualityLoopResult(
                    novel_id=self.review.novel_id, status="planned", rounds=rounds,
                    report=report, plans=tuple(plans), usage=usage,
                    reasons=("dry run：未写入任何 revision",))
            if plan.status != "planned":
                reasons.extend([f"plan status={plan.status}",
                                *plan.conflicts, *plan.human_review_reasons])
                break
            result = self.review.execute_repair(plan, dry_run=False)
            results.append(result)
            usage = build_usage(evaluation=usage.get("evaluation"),
                                repair=merge_usage(usage.get("repair"), result.usage),
                                verification=usage.get("verification"))
            if result.status not in ("applied", "idempotent_replay"):
                reasons.extend([f"repair result status={result.status}",
                                *[str(row.get("message") or row.get("error") or "")
                                  for row in result.blocked_steps]])
                break
            verification = self.review.verify_repair(
                before_report=report, plan=plan, policy=resolved_policy,
                before_revisions=result.before_revisions or None)
            usage = build_usage(
                evaluation=usage.get("evaluation"), repair=usage.get("repair"),
                verification=merge_usage(
                    usage.get("verification"),
                    (verification.usage or {}).get("verification")))
            report = verification.report or report
            rounds += 1

            goal_met = (verification.status == "resolved"
                        and (not wanted
                             or wanted <= set(verification.resolved_issue_ids)))
            if report.status == "passed":
                return QualityLoopResult(novel_id=self.review.novel_id,
                                         status="passed", rounds=rounds,
                                         report=report, plans=tuple(plans),
                                         results=tuple(results), verification=verification,
                                         usage=usage)
            if goal_met:
                remaining_blocking = sorted(
                    f"{issue.code}({issue.gate})" for issue in report.issues
                    if resolved_policy.blocks(issue.severity)
                    and issue.issue_id not in set(verification.resolved_issue_ids))
                return QualityLoopResult(
                    novel_id=self.review.novel_id, status="repaired", rounds=rounds,
                    report=report, plans=tuple(plans), results=tuple(results),
                    verification=verification, usage=usage,
                    needs_human_review=bool(remaining_blocking),
                    reasons=tuple(
                        ["目标 issue 已全部解决并复核通过",
                         f"仍有未解决的 blocking issue：{remaining_blocking}"]
                        if remaining_blocking else
                        ["目标 issue 已全部解决并复核通过"]))
            if not verification.resolved_issue_ids:
                reasons.append(
                    f"verification status={verification.status}：本轮没有解决任何 issue")
                break
            budget_reason = self._budget_reason(resolved_policy, usage)
            if budget_reason:
                reasons.append(budget_reason)
                break

        if not reasons:
            reasons.append(f"达到 max_repair_rounds={limit} 仍未被判定为 passed")
        return QualityLoopResult(
            novel_id=self.review.novel_id, status="needs_human_review",
            rounds=rounds, report=report, plans=tuple(plans),
            results=tuple(results), verification=verification, usage=usage,
            needs_human_review=True, reasons=tuple(reason for reason in reasons if reason))

    @staticmethod
    def _budget_reason(policy: QualityPolicy,
                       usage: Mapping[str, Any]) -> str:
        tokens, cost = usage_totals(usage.get("total"))
        if policy.token_limit is not None and tokens > int(policy.token_limit):
            return f"token budget 用尽：{tokens} > {policy.token_limit}"
        if policy.cost_limit is not None and cost > float(policy.cost_limit):
            return f"cost budget 用尽：{cost} > {policy.cost_limit}"
        return ""


def review_service(project_root: Path | str, novel_id: str, *,
                   quality: QualityService, generation: Any = None,
                   **kwargs: Any) -> ReviewService:
    return ReviewService(project_root, novel_id, quality=quality,
                         generation=generation, **kwargs)


__all__ = ["LOOP_STATUSES", "QualityLoopResult", "QualityLoopService",
           "RepairOutcome", "ReviewService", "review_service"]
