"""Quality Contract（V4-05 §6–§10、§27、§40）。

统一对象：QualityScope / QualityEvidence / QualityIssue / QualityGateResult /
QualityReport / QualityPolicy。业务层与未来的 REST / MCP / UI 都消费这些类型。
"""

from __future__ import annotations

import datetime as _dt
from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

from novelforge.core.ids import digest_payload

from .codes import code_spec, is_registered
from .errors import QualityPolicyError, QualityScopeError

QUALITY_SCHEMA_VERSION = 1

GateId = str          # Q0 … Q9
Severity = str        # info / minor / major / blocker
IssueStatus = str     # open / repairing / resolved / accepted_risk / ignored
QualityStatus = str   # unevaluated / evaluating / passed / failed / blocked /
                      # needs_human_review

SEVERITIES: tuple[str, ...] = ("info", "minor", "major", "blocker")
SEVERITY_ORDER: dict[str, int] = {name: index for index, name in enumerate(SEVERITIES)}

ISSUE_STATUSES: tuple[str, ...] = ("open", "repairing", "resolved",
                                   "accepted_risk", "ignored")
QUALITY_STATUSES: tuple[str, ...] = ("unevaluated", "evaluating", "passed", "failed",
                                     "blocked", "needs_human_review")
GATES: tuple[str, ...] = ("Q0", "Q1", "Q2", "Q3", "Q4", "Q5", "Q6", "Q7", "Q8", "Q9")


def utc_now() -> str:
    return _dt.datetime.now(_dt.timezone.utc).isoformat()


@dataclass(frozen=True)
class QualityScope:
    novel_id: str
    node_ids: tuple[str, ...] = ()
    node_types: tuple[str, ...] = ()
    revision: int | None = None
    kind: str = "nodes"          # nodes / subtree / chapter / unit / blueprint / changed
    gates: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not str(self.novel_id or "").strip():
            raise QualityScopeError("QualityScope 必须显式携带 novel_id")

    @property
    def digest(self) -> str:
        return digest_payload({"novel_id": self.novel_id,
                               "nodes": sorted(self.node_ids),
                               "types": sorted(self.node_types),
                               "kind": self.kind, "revision": self.revision})

    @property
    def identity(self) -> str:
        """**revision 无关**的语义 identity（§28 / §44）。

        `issue_id` 必须跨 revision 稳定：修复一个节点后，如果同一问题仍然存在，
        它必须仍是**同一个** issue（否则 verifier 会把"没修好"误判成"已解决 + 新问题"）。
        因此 issue identity 只由 code + novel + 目标节点 + kind 决定；
        `revision` 只作为 evidence / provenance 的一部分保留。
        """

        return digest_payload({"novel_id": self.novel_id,
                               "nodes": sorted(self.node_ids),
                               "types": sorted(self.node_types),
                               "kind": self.kind})

    def as_dict(self) -> dict[str, Any]:
        return {"novel_id": self.novel_id, "node_ids": list(self.node_ids),
                "node_types": list(self.node_types), "revision": self.revision,
                "kind": self.kind, "gates": list(self.gates)}


@dataclass(frozen=True)
class QualityEvidence:
    """Evidence 是一等对象（§27）：不是一句「感觉不合理」。"""

    evidence_id: str
    kind: str                     # node_field / comparison / metric / graph / retrieval
    explanation: str
    source_ids: tuple[str, ...] = ()
    node_ids: tuple[str, ...] = ()
    revision: int | None = None
    excerpt: str = ""
    comparison: Mapping[str, Any] = field(default_factory=dict)
    metric: Mapping[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {"evidence_id": self.evidence_id, "kind": self.kind,
                "explanation": self.explanation,
                "source_ids": list(self.source_ids),
                "node_ids": list(self.node_ids), "revision": self.revision,
                "excerpt": self.excerpt, "comparison": dict(self.comparison),
                "metric": dict(self.metric)}

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> "QualityEvidence":
        row = dict(raw or {})
        return cls(evidence_id=str(row.get("evidence_id") or ""),
                   kind=str(row.get("kind") or "node_field"),
                   explanation=str(row.get("explanation") or ""),
                   source_ids=tuple(str(value) for value in
                                    (row.get("source_ids") or ())),
                   node_ids=tuple(str(value) for value in
                                  (row.get("node_ids") or ())),
                   revision=(int(row["revision"])
                             if row.get("revision") is not None else None),
                   excerpt=str(row.get("excerpt") or ""),
                   comparison=dict(row.get("comparison") or {}),
                   metric=dict(row.get("metric") or {}))


@dataclass(frozen=True)
class QualityIssue:
    issue_id: str
    code: str
    gate: str
    severity: str
    novel_id: str
    scope: QualityScope
    reason: str
    status: str = "open"
    evidence: tuple[QualityEvidence, ...] = ()
    repair_contract: Mapping[str, Any] = field(default_factory=dict)
    detected_at: str = ""
    evaluator_id: str = ""
    evaluator_version: int = 1
    provenance: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not is_registered(self.code):
            raise QualityPolicyError(
                f"未注册的 issue code：{self.code}（LLM 不得自造 code）",
                details={"code": self.code})
        if self.gate not in GATES:
            raise QualityPolicyError(f"未知 gate：{self.gate}")
        if self.severity not in SEVERITIES:
            raise QualityPolicyError(f"未知 severity：{self.severity}")
        if self.status not in ISSUE_STATUSES:
            raise QualityPolicyError(f"未知 issue status：{self.status}")
        if not str(self.novel_id or "").strip():
            raise QualityScopeError("QualityIssue 需要显式 novel_id")
        if self.scope.novel_id != self.novel_id:
            raise QualityScopeError("issue 的 scope 与 novel_id 不一致")
        if not self.detected_at:
            object.__setattr__(self, "detected_at", utc_now())
        if not self.evidence:
            raise QualityPolicyError(
                f"issue {self.issue_id} 缺少 evidence（不允许无证据判定）")

    @property
    def gate_spec(self):
        return code_spec(self.code)

    @property
    def repairable(self) -> bool:
        return bool(self.gate_spec.repairable)

    @property
    def preserve_fields(self) -> tuple[str, ...]:
        return tuple(str(value) for value in
                     (self.repair_contract.get("preserve") or ()))

    @property
    def allow_change_fields(self) -> tuple[str, ...]:
        return tuple(str(value) for value in
                     (self.repair_contract.get("allow_change") or ()))

    def as_dict(self) -> dict[str, Any]:
        return {"issue_id": self.issue_id, "code": self.code, "gate": self.gate,
                "severity": self.severity, "status": self.status,
                "novel_id": self.novel_id, "scope": self.scope.as_dict(),
                "reason": self.reason,
                "evidence": [row.as_dict() for row in self.evidence],
                "repair_contract": dict(self.repair_contract),
                "detected_at": self.detected_at,
                "evaluator_id": self.evaluator_id,
                "evaluator_version": self.evaluator_version,
                "provenance": dict(self.provenance),
                "repairable": self.repairable}

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> "QualityIssue":
        """从 Quality Store 读回 issue（Application / MCP 只读消费）。"""

        row = dict(raw or {})
        return cls(issue_id=str(row.get("issue_id") or ""),
                   code=str(row.get("code") or ""),
                   gate=str(row.get("gate") or ""),
                   severity=str(row.get("severity") or "minor"),
                   novel_id=str(row.get("novel_id") or ""),
                   scope=scope_from_dict(row.get("scope") or {}),
                   reason=str(row.get("reason") or ""),
                   status=str(row.get("status") or "open"),
                   evidence=tuple(QualityEvidence.from_dict(item)
                                  for item in (row.get("evidence") or ())),
                   repair_contract=dict(row.get("repair_contract") or {}),
                   detected_at=str(row.get("detected_at") or ""),
                   evaluator_id=str(row.get("evaluator_id") or ""),
                   evaluator_version=int(row.get("evaluator_version") or 1),
                   provenance=dict(row.get("provenance") or {}))


def issue_id_for(code: str, scope: QualityScope, suffix: str = "") -> str:
    """稳定 issue id（同一 scope + code + suffix → 同一 id，便于去重与追踪）。"""

    digest = digest_payload({"code": code, "scope": scope.identity, "suffix": suffix})
    return f"QI_{code}_{digest[:10]}"


def scope_from_dict(raw: Mapping[str, Any]) -> QualityScope:
    row = dict(raw or {})
    return QualityScope(novel_id=str(row.get("novel_id") or ""),
                        node_ids=tuple(str(value) for value in
                                       (row.get("node_ids") or ())),
                        node_types=tuple(str(value) for value in
                                         (row.get("node_types") or ())),
                        revision=(int(row["revision"])
                                  if row.get("revision") is not None else None),
                        kind=str(row.get("kind") or "nodes"),
                        gates=tuple(str(value) for value in (row.get("gates") or ())))


def make_issue(*, code: str, novel_id: str, scope: QualityScope, reason: str,
               evidence: Sequence[QualityEvidence], evaluator_id: str,
               evaluator_version: int = 1, severity: str = "",
               repair_contract: Mapping[str, Any] | None = None,
               provenance: Mapping[str, Any] | None = None,
               suffix: str = "") -> QualityIssue:
    """按 code registry 生成 issue（severity 与默认 repair contract 来自 registry）。"""

    if not is_registered(code):
        raise QualityPolicyError(
            f"未注册的 issue code：{code}（LLM / evaluator 不得自造 code）",
            details={"code": code})
    spec = code_spec(code)
    contract = dict(repair_contract or {})
    if not contract:
        contract = {"scope": scope.as_dict(), "preserve": list(spec.preserve),
                    "allow_change": list(spec.allow_change),
                    "must_resolve": [], "constraints": [],
                    "max_scope": list(scope.node_ids), "repairable": spec.repairable}
    return QualityIssue(
        issue_id=issue_id_for(code, scope, suffix),
        code=code, gate=spec.gate, severity=severity or spec.severity,
        novel_id=novel_id, scope=scope, reason=reason, evidence=tuple(evidence),
        repair_contract=contract, evaluator_id=evaluator_id,
        evaluator_version=evaluator_version, provenance=dict(provenance or {}))


@dataclass(frozen=True)
class QualityGateResult:
    gate: str
    status: str                 # passed / failed / blocked / skipped
    issues: tuple[QualityIssue, ...] = ()
    evaluator_ids: tuple[str, ...] = ()
    duration_ms: int = 0
    usage: Mapping[str, Any] = field(default_factory=dict)
    skipped_reason: str = ""

    @property
    def blocker_count(self) -> int:
        return sum(1 for row in self.issues if row.severity == "blocker")

    def as_dict(self) -> dict[str, Any]:
        return {"gate": self.gate, "status": self.status,
                "issue_count": len(self.issues),
                "issue_ids": [row.issue_id for row in self.issues],
                "evaluator_ids": list(self.evaluator_ids),
                "duration_ms": self.duration_ms, "usage": dict(self.usage),
                "skipped_reason": self.skipped_reason}


@dataclass(frozen=True)
class QualityReport:
    report_id: str
    novel_id: str
    scope: QualityScope
    status: str
    gate_results: tuple[QualityGateResult, ...] = ()
    issues: tuple[QualityIssue, ...] = ()
    usage: Mapping[str, Any] = field(default_factory=dict)
    policy: Mapping[str, Any] = field(default_factory=dict)
    generated_at: str = ""
    schema_version: int = QUALITY_SCHEMA_VERSION
    digest: str = ""
    #: 本次评估实际覆盖的节点 revision（V4-07 §12–§13：交付必须能证明
    #: "质量结论针对的就是这些 revision"）。缺失时视为未记录。
    node_revisions: Mapping[str, int] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.generated_at:
            object.__setattr__(self, "generated_at", utc_now())
        if not self.digest:
            object.__setattr__(self, "digest", digest_payload(
                {"novel": self.novel_id, "scope": self.scope.as_dict(),
                 "status": self.status,
                 "issues": [row.issue_id for row in self.issues]}))

    @property
    def blockers(self) -> tuple[QualityIssue, ...]:
        return tuple(row for row in self.issues if row.severity == "blocker")

    @property
    def majors(self) -> tuple[QualityIssue, ...]:
        return tuple(row for row in self.issues if row.severity == "major")

    def issues_for_gate(self, gate: str) -> tuple[QualityIssue, ...]:
        return tuple(row for row in self.issues if row.gate == gate)

    def as_dict(self) -> dict[str, Any]:
        return {"report_id": self.report_id, "novel_id": self.novel_id,
                "scope": self.scope.as_dict(), "status": self.status,
                "gates": [row.as_dict() for row in self.gate_results],
                "issues": [row.as_dict() for row in self.issues],
                "usage": dict(self.usage), "policy": dict(self.policy),
                "generated_at": self.generated_at,
                "schema_version": self.schema_version, "digest": self.digest,
                "node_revisions": {str(key): int(value) for key, value
                                   in dict(self.node_revisions).items()}}


@dataclass(frozen=True)
class QualityPolicy:
    """生产策略只能来自 policy，不写死在 evaluator 里（§40）。"""

    required_gates: tuple[str, ...] = ("Q0", "Q1", "Q2", "Q3", "Q5", "Q6", "Q7", "Q8")
    blocking_severities: tuple[str, ...] = ("blocker", "major")
    max_repair_rounds: int = 3
    enable_llm_evaluators: bool = False
    cost_limit: float | None = None
    token_limit: int | None = None
    stop_on_blocker: bool = True
    gate_thresholds: Mapping[str, int] = field(default_factory=dict)
    max_issues_per_gate: int = 50
    #: V4-09 §78–§79：第三方（plugin）evaluator 只有显式列出才参与；
    #: 默认不参与，且即使参与也默认 non-blocking（不因安装插件阻断交付）
    plugin_evaluator_ids: tuple[str, ...] = ()
    plugin_blocking: bool = False

    def __post_init__(self) -> None:
        unknown = [gate for gate in self.required_gates if gate not in GATES]
        if unknown:
            raise QualityPolicyError(f"未知 required gate：{unknown}")
        if int(self.max_repair_rounds) < 0:
            raise QualityPolicyError("max_repair_rounds 不能为负")
        for severity in self.blocking_severities:
            if severity not in SEVERITIES:
                raise QualityPolicyError(f"未知 blocking severity：{severity}")

    def blocks(self, severity: str) -> bool:
        return severity in self.blocking_severities

    def as_dict(self) -> dict[str, Any]:
        return {"required_gates": list(self.required_gates),
                "blocking_severities": list(self.blocking_severities),
                "max_repair_rounds": self.max_repair_rounds,
                "enable_llm_evaluators": self.enable_llm_evaluators,
                "cost_limit": self.cost_limit, "token_limit": self.token_limit,
                "stop_on_blocker": self.stop_on_blocker,
                "gate_thresholds": dict(self.gate_thresholds),
                "max_issues_per_gate": self.max_issues_per_gate,
                "plugin_evaluator_ids": list(self.plugin_evaluator_ids),
                "plugin_blocking": bool(self.plugin_blocking)}


def decide_status(issues: Sequence[QualityIssue], policy: QualityPolicy, *,
                  gates_run: Sequence[str]) -> str:
    """PASS / FAIL 由 Gate + Severity + policy 决定，**不是**平均分（§10）。"""

    if any(row.severity == "blocker" for row in issues):
        return "blocked"
    if any(policy.blocks(row.severity) for row in issues):
        return "failed"
    missing = [gate for gate in policy.required_gates if gate not in set(gates_run)]
    if missing:
        return "failed"
    return "passed"


__all__ = [
    "GATES", "ISSUE_STATUSES", "QUALITY_SCHEMA_VERSION", "QUALITY_STATUSES",
    "SEVERITIES", "SEVERITY_ORDER", "GateId", "IssueStatus", "QualityEvidence",
    "QualityGateResult", "QualityIssue", "QualityPolicy", "QualityReport",
    "QualityScope", "QualityStatus", "Severity", "decide_status", "issue_id_for",
    "make_issue", "scope_from_dict", "utc_now",
]
