"""QualityService（V4-05 §23、§42–§44）：唯一评估入口。

```text
evaluate(scope, policy)
   ↓ deterministic first：Q0/Q1 先跑；出现 blocker 且 policy.stop_on_blocker → 跳过昂贵的下游 gate
   ↓ 每个 gate 从 EvaluatorRegistry 取 evaluator（不硬编码 if gate == ...）
   ↓ 汇总 issue → 写入 QualityStore → 返回 QualityReport
```

不变量：

* 只读：不修改 Blueprint / Canon / StoryState（§24）
* PASS/FAIL 由 Gate + Severity + Policy 决定，不是平均分（§10）
* incremental：node revision 未变 → 允许复用上一轮评估（§44）
* ownership：scope 必须显式 novel_id；节点归属不符会被 Q1 报出（§67）
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from novelforge.blueprint import BlueprintRepository
from novelforge.core.ids import digest_payload, new_request_id

from .contracts import (
    GATES,
    QualityGateResult,
    QualityIssue,
    QualityPolicy,
    QualityReport,
    QualityScope,
    decide_status,
)
from .aggregation import build_usage, merge_issues
from .evaluators.base import EvaluationContext
from .registry import EvaluatorRegistry, build_default_registry
from .store import QualityStore


class QualityService:
    """按 novel_id 绑定的质量评估服务。"""

    def __init__(self, project_root: Path | str, novel_id: str, *,
                 repository: BlueprintRepository | None = None,
                 memory: Any = None, context_builder: Any = None,
                 critic: Any = None, registry: EvaluatorRegistry | None = None,
                 store: QualityStore | None = None) -> None:
        from .errors import QualityScopeError

        if not str(novel_id or "").strip():
            raise QualityScopeError("QualityService 需要显式 novel_id")
        self.project_root = Path(project_root)
        self.novel_id = str(novel_id)
        self.repository = repository or BlueprintRepository(self.project_root,
                                                            self.novel_id)
        self.memory = memory
        self.context_builder = context_builder
        self.critic = critic
        self.registry = registry or build_default_registry()
        self.store = store or QualityStore(self.project_root, self.novel_id)
        self._cache: dict[str, tuple[QualityIssue, ...]] = {}

    # ------------------------------------------------------------------ 上下文
    def _context(self, scope: QualityScope, policy: QualityPolicy,
                 extra: Mapping[str, Any] | None = None) -> EvaluationContext:
        nodes = {node.node_id: node for node in self.repository.all_nodes()}
        return EvaluationContext(novel_id=self.novel_id, scope=scope, nodes=nodes,
                                 policy=policy, repository=self.repository,
                                 memory=self.memory,
                                 context_builder=self.context_builder,
                                 critic=self.critic, extra=dict(extra or {}))

    def build_scope(self, *, node_ids: Iterable[str] = (), node_types: Iterable[str] = (),
                    kind: str = "", gates: Iterable[str] = ()) -> QualityScope:
        ids = tuple(sorted(str(value) for value in node_ids if str(value)))
        if not ids and not kind:
            kind = "blueprint"
        if kind == "blueprint" and not ids:
            ids = tuple(sorted(node.node_id for node in self.repository.all_nodes()))
            node_types = tuple(sorted({node.node_type
                                       for node in self.repository.all_nodes()}))
        return QualityScope(novel_id=self.novel_id, node_ids=ids,
                            node_types=tuple(sorted(str(value) for value in node_types
                                                    if str(value))),
                            kind=kind or "nodes",
                            gates=tuple(str(value) for value in gates))

    # ------------------------------------------------------------------ 评估
    def evaluate(self, scope: QualityScope | None = None, *,
                 policy: QualityPolicy | None = None,
                 gates: Sequence[str] | None = None,
                 prior_issues: Sequence[QualityIssue] = (),
                 use_cache: bool = True) -> QualityReport:
        resolved_policy = policy or QualityPolicy()
        resolved_scope = scope or self.build_scope(kind="blueprint")
        if resolved_scope.novel_id != self.novel_id:
            from .errors import QualityScopeError

            raise QualityScopeError(
                f"拒绝跨作品评估：{resolved_scope.novel_id} != {self.novel_id}")
        requested = tuple(gates or resolved_scope.gates or GATES)
        context = self._context(resolved_scope, resolved_policy,
                                {"prior_issues": tuple(prior_issues)})

        gate_results: list[QualityGateResult] = []
        all_issues: list[QualityIssue] = []
        blocked_early = False

        for gate in requested:
            if gate not in GATES:
                continue
            if blocked_early and gate not in ("Q0", "Q1"):
                gate_results.append(QualityGateResult(
                    gate=gate, status="skipped",
                    skipped_reason="upstream_blocker（Q0/Q1 已阻止继续）"))
                continue
            issues = self._evaluate_gate(gate, context, resolved_policy,
                                         use_cache=use_cache)
            issues = list(merge_issues(issues))[
                : max(1, resolved_policy.max_issues_per_gate)]
            all_issues.extend(issues)
            deciding = self._deciding_issues(issues, resolved_policy)
            status = "blocked" if any(row.severity == "blocker" for row in deciding) \
                else "failed" if any(resolved_policy.blocks(row.severity)
                                     for row in deciding) else "passed"
            gate_results.append(QualityGateResult(
                gate=gate, status=status, issues=tuple(issues),
                evaluator_ids=tuple(row.spec.evaluator_id for row in
                                    self.registry.for_gate(gate,
                                                           policy=resolved_policy))))
            if (resolved_policy.stop_on_blocker
                    and any(row.severity == "blocker" for row in deciding
                            if row.gate in ("Q0", "Q1"))):
                blocked_early = True

        all_issues = list(merge_issues(all_issues))
        gates_run = [row.gate for row in gate_results if row.status != "skipped"]
        # V4-09 §79：插件 evaluator 的 issue 默认 non-blocking（除非 policy 显式提升）
        status = decide_status(self._deciding_issues(all_issues, resolved_policy),
                               resolved_policy, gates_run=gates_run)
        usage = build_usage(evaluation=context.usage.get("total"))
        report_id = f"QR_{new_request_id('report').split('_', 1)[1][:12]}"
        node_revisions = {node_id: int(context.nodes[node_id].revision)
                          for node_id in sorted(context.nodes)
                          if node_id in context.nodes}
        report = QualityReport(
            report_id=report_id, novel_id=self.novel_id, scope=resolved_scope,
            status=status, gate_results=tuple(gate_results),
            issues=tuple(all_issues), usage=usage, policy=resolved_policy.as_dict(),
            node_revisions=node_revisions)
        self.store.save_issues(all_issues)
        self.store.save_report(report)
        return report

    def _evaluate_gate(self, gate: str, context: EvaluationContext,
                       policy: QualityPolicy, *, use_cache: bool
                       ) -> Sequence[QualityIssue]:
        issues: list[QualityIssue] = []
        for registration in self.registry.for_gate(gate, policy=policy):
            spec = registration.spec
            key = self._cache_key(gate, context, spec.evaluator_id, spec.version)
            if use_cache and key in self._cache:
                issues.extend(self._tag_owner(issue, spec)
                              for issue in self._cache[key]
                              if issue.novel_id == self.novel_id)
                continue
            produced = tuple(self._tag_owner(issue, spec)
                             for issue in registration.fn(context))
            if use_cache:
                self._cache[key] = produced
            issues.extend(produced)
        return issues

    @staticmethod
    def _tag_owner(issue: QualityIssue, spec: Any) -> QualityIssue:
        """把 evaluator 归属写进 issue provenance（V4-09 §55、§80、§96）。"""

        if getattr(spec, "owner_type", "core") != "plugin":
            return issue
        from dataclasses import replace

        return replace(issue, provenance={
            **dict(issue.provenance), "owner_type": "plugin",
            "plugin_id": str(getattr(spec, "owner_id", "")),
            "plugin_evaluator_version": int(getattr(spec, "version", 1))})

    @staticmethod
    def _deciding_issues(issues: Sequence[QualityIssue],
                         policy: QualityPolicy) -> list[QualityIssue]:
        """判定 PASS/FAIL 时使用的 issue 集合。

        V4-09 §78–§79：插件 evaluator 的 issue 默认不参与 blocking 判定
        （仍会出现在 report / store 里，且带 plugin_id provenance）。
        """

        if bool(getattr(policy, "plugin_blocking", False)):
            return list(issues)
        return [row for row in issues
                if str(dict(row.provenance).get("owner_type") or "") != "plugin"]

    def _cache_key(self, gate: str, context: EvaluationContext, evaluator_id: str,
                   version: int) -> str:
        revisions = {node_id: context.nodes[node_id].revision
                     for node_id in sorted(context.scope.node_ids)
                     if node_id in context.nodes}
        return digest_payload({"novel": self.novel_id, "gate": gate,
                               "evaluator": evaluator_id, "version": version,
                               "scope": context.scope.digest,
                               "revisions": revisions})

    def clear_cache(self) -> None:
        self._cache.clear()

    # ------------------------------------------------------------------ 只读
    def list_issues(self, *, status: str = "", gate: str = "") -> list[dict[str, Any]]:
        return self.store.list_issues(status=status, gate=gate)

    def issues_for_node(self, node_id: str) -> list[dict[str, Any]]:
        return [row for row in self.store.list_issues()
                if node_id in (row.get("scope") or {}).get("node_ids", [])]

    def latest_report(self) -> dict[str, Any]:
        return self.store.latest_report()

    def stats(self) -> dict[str, Any]:
        return self.store.stats()

    # ------------------------------------------------------- Blueprint 投影
    def project_quality_status(self, report: QualityReport | None = None,
                               *, node_ids: Iterable[str] = ()) -> dict[str, str]:
        """把质量结果投影成节点 `quality_status`（§46：store 是 owner，节点只是投影）。

        返回 {node_id: status}；调用方（Application Service）决定是否写回节点。
        """

        resolved = report or None
        ids = tuple(sorted(str(value) for value in node_ids))
        if resolved is None and not ids:
            return {}
        projection: dict[str, str] = {}
        for node_id in ids:
            rows = self.issues_for_node(node_id)
            if any(row.get("severity") == "blocker" for row in rows):
                projection[node_id] = "blocked"
            elif any(row.get("severity") == "major" for row in rows):
                projection[node_id] = "failed"
            elif rows:
                projection[node_id] = "passed_with_issues"
            else:
                projection[node_id] = "passed"
        return projection


def quality_service(project_root: Path | str, novel_id: str, **kwargs: Any
                    ) -> QualityService:
    return QualityService(project_root, novel_id, **kwargs)


__all__ = ["QualityService", "quality_service"]
