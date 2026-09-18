"""Agent 契约（V4-11 §11–§23、§27–§43、§48–§58）。

```text
AgentGoal / AgentScope / AgentPolicy
AgentStep / AgentPlan / AgentContextSnapshot
AgentApprovalRequest / AgentApprovalDecision
AgentStepResult / AgentResult
AgentSession / AgentRun / AgentCheckpoint / AgentAuditRecord
AGENT_STATUSES / AGENT_TRANSITIONS / AGENT_SCHEMA_VERSION
```

Agent 只编排已有能力：本模块不 import 任何业务模块（repository / store / provider /
api / mcp），也不拼 artifact 路径。
"""

from __future__ import annotations

import datetime as _dt
from dataclasses import dataclass, field, replace
from typing import Any, Mapping, Sequence

from novelforge.core.ids import digest_payload, new_request_id

from .errors import AgentPlanInvalid

AGENT_SCHEMA_VERSION = 1

#: 会话 / 运行状态（§18：不允许任意字符串）
AGENT_STATUSES: tuple[str, ...] = (
    "created", "planning", "awaiting_approval", "executing", "verifying", "paused",
    "completed", "failed", "cancelled", "needs_human_review",
)

AGENT_TRANSITIONS: Mapping[str, tuple[str, ...]] = {
    "created": ("planning", "cancelled", "failed"),
    "planning": ("awaiting_approval", "executing", "paused", "cancelled", "failed",
                 "needs_human_review"),
    "awaiting_approval": ("executing", "paused", "cancelled", "failed",
                          "needs_human_review"),
    "executing": ("verifying", "awaiting_approval", "paused", "completed", "failed",
                  "cancelled", "needs_human_review"),
    "verifying": ("executing", "paused", "completed", "failed", "cancelled",
                  "needs_human_review"),
    "paused": ("executing", "planning", "cancelled", "failed"),
    "needs_human_review": ("planning", "paused", "cancelled"),
    "completed": (),
    "failed": ("paused",),
    "cancelled": (),
}

#: 步骤状态
STEP_STATUSES: tuple[str, ...] = (
    "pending", "running", "completed", "failed", "skipped", "stale",
    "awaiting_approval", "cancelled",
)

#: 目标 scope 种类（§13：必须显式，不允许“整个作品随便改”）
SCOPE_KINDS: tuple[str, ...] = ("novel", "structural_unit", "chapter", "scene", "nodes")

#: 需要显式批准的 protected actions（§16）
PROTECTED_ACTIONS: tuple[str, ...] = (
    "accept_revision", "deliver", "request_accept",
)


def utc_now() -> str:
    return _dt.datetime.now(_dt.timezone.utc).isoformat()


@dataclass(frozen=True)
class AgentScope:
    """目标作用范围（§13）。"""

    kind: str = "novel"
    unit_id: str = ""
    node_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if str(self.kind) not in SCOPE_KINDS:
            raise AgentPlanInvalid(f"未知 scope kind：{self.kind}",
                                   details={"known": list(SCOPE_KINDS)})
        if self.kind == "nodes" and not self.node_ids:
            raise AgentPlanInvalid("scope=node_ids 时必须显式给出 node_ids")
        if self.kind in ("structural_unit", "chapter", "scene") and not self.unit_id:
            raise AgentPlanInvalid(f"scope={self.kind} 时必须显式给出 unit_id")

    @property
    def is_whole_novel(self) -> bool:
        return self.kind == "novel"

    def as_dict(self) -> dict[str, Any]:
        return {"kind": self.kind, "unit_id": self.unit_id,
                "node_ids": list(self.node_ids)}


@dataclass(frozen=True)
class AgentGoal:
    """作者目标（§12）。"""

    novel_id: str
    instruction: str
    scope: AgentScope = field(default_factory=AgentScope)
    constraints: tuple[str, ...] = ()
    success_criteria: tuple[str, ...] = ()
    goal_id: str = ""
    request_id: str = ""

    def __post_init__(self) -> None:
        if not str(self.novel_id or "").strip():
            raise AgentPlanInvalid("AgentGoal 需要显式 novel_id")
        if not str(self.instruction or "").strip():
            raise AgentPlanInvalid("AgentGoal 需要 instruction（作者目标）")
        if not self.goal_id:
            object.__setattr__(self, "goal_id", new_request_id("goal"))
        if not self.request_id:
            object.__setattr__(self, "request_id", new_request_id("agentreq"))

    @property
    def digest(self) -> str:
        return digest_payload(self.as_dict())

    def as_dict(self) -> dict[str, Any]:
        return {"goal_id": self.goal_id, "novel_id": self.novel_id,
                "instruction": self.instruction, "scope": self.scope.as_dict(),
                "constraints": list(self.constraints),
                "success_criteria": list(self.success_criteria),
                "request_id": self.request_id}

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> "AgentGoal":
        row = dict(raw or {})
        scope_raw = dict(row.get("scope") or {})
        return cls(novel_id=str(row.get("novel_id") or ""),
                   instruction=str(row.get("instruction") or ""),
                   scope=AgentScope(kind=str(scope_raw.get("kind") or "novel"),
                                    unit_id=str(scope_raw.get("unit_id") or ""),
                                    node_ids=tuple(str(value) for value in
                                                   (scope_raw.get("node_ids") or ()))),
                   constraints=tuple(str(value) for value in
                                     (row.get("constraints") or ())),
                   success_criteria=tuple(str(value) for value in
                                          (row.get("success_criteria") or ())),
                   goal_id=str(row.get("goal_id") or ""),
                   request_id=str(row.get("request_id") or ""))


@dataclass(frozen=True)
class AgentPolicy:
    """自治边界（§14–§17）：默认保守。"""

    max_steps: int = 20
    max_mutations: int = 10
    max_repair_rounds: int = 2
    max_batch_steps: int = 8
    token_budget: int | None = None
    cost_budget: float | None = None
    time_budget_s: float | None = None
    allow_generation: bool = True
    allow_edit: bool = True
    allow_quality: bool = True
    allow_repair: bool = True
    allow_auto_accept: bool = False
    allow_delivery: bool = False
    require_approval_for: tuple[str, ...] = PROTECTED_ACTIONS

    def __post_init__(self) -> None:
        for name in ("max_steps", "max_mutations", "max_repair_rounds",
                     "max_batch_steps"):
            if int(getattr(self, name)) < 0:
                raise AgentPlanInvalid(f"{name} 不能为负")
        if int(self.max_steps) < 1:
            raise AgentPlanInvalid("max_steps 必须 >= 1")

    def as_dict(self) -> dict[str, Any]:
        return {"max_steps": int(self.max_steps),
                "max_mutations": int(self.max_mutations),
                "max_repair_rounds": int(self.max_repair_rounds),
                "max_batch_steps": int(self.max_batch_steps),
                "token_budget": self.token_budget, "cost_budget": self.cost_budget,
                "time_budget_s": self.time_budget_s,
                "allow_generation": bool(self.allow_generation),
                "allow_edit": bool(self.allow_edit),
                "allow_quality": bool(self.allow_quality),
                "allow_repair": bool(self.allow_repair),
                "allow_auto_accept": bool(self.allow_auto_accept),
                "allow_delivery": bool(self.allow_delivery),
                "require_approval_for": list(self.require_approval_for)}

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any] | None) -> "AgentPolicy":
        row = dict(raw or {})
        known = {name: row[name] for name in row if name in cls.__dataclass_fields__}
        policy = cls(**known)
        if row.get("require_approval_for") is not None:
            policy = replace(policy, require_approval_for=tuple(
                str(value) for value in row["require_approval_for"]))
        return policy


@dataclass(frozen=True)
class AgentContextSnapshot:
    """规划输入状态（§27）：证明 Plan 是基于什么状态产生的。"""

    novel_id: str
    blueprint_revisions: Mapping[str, int] = field(default_factory=dict)
    node_types: Mapping[str, str] = field(default_factory=dict)
    node_status: Mapping[str, str] = field(default_factory=dict)
    parent_ids: Mapping[str, str] = field(default_factory=dict)
    accepted_nodes: tuple[str, ...] = ()
    quality_summary: Mapping[str, Any] = field(default_factory=dict)
    open_issues: tuple[Mapping[str, Any], ...] = ()
    delivery_readiness: Mapping[str, Any] = field(default_factory=dict)
    review_state: Mapping[str, Any] = field(default_factory=dict)
    created_at: str = ""

    def __post_init__(self) -> None:
        if not self.created_at:
            object.__setattr__(self, "created_at", utc_now())

    def revision_of(self, node_id: str) -> int:
        return int(dict(self.blueprint_revisions).get(str(node_id)) or 0)

    def nodes_of_type(self, node_type: str) -> tuple[str, ...]:
        return tuple(sorted(node_id for node_id, kind
                            in dict(self.node_types).items() if kind == node_type))

    def children_of(self, parent_id: str, node_type: str = "") -> tuple[str, ...]:
        rows = [node_id for node_id, parent in dict(self.parent_ids).items()
                if parent == str(parent_id)
                and (not node_type or dict(self.node_types).get(node_id) == node_type)]
        return tuple(sorted(rows))

    @property
    def digest(self) -> str:
        return digest_payload({"novel_id": self.novel_id,
                               "revisions": dict(sorted(self.blueprint_revisions.items())),
                               "status": dict(sorted(self.node_status.items()))})

    def as_dict(self) -> dict[str, Any]:
        return {"novel_id": self.novel_id,
                "blueprint_revisions": {key: int(value) for key, value
                                        in sorted(self.blueprint_revisions.items())},
                "node_types": dict(sorted(self.node_types.items())),
                "node_status": dict(sorted(self.node_status.items())),
                "parent_ids": dict(sorted(self.parent_ids.items())),
                "accepted_nodes": list(self.accepted_nodes),
                "quality_summary": dict(self.quality_summary),
                "open_issues": [dict(row) for row in self.open_issues],
                "delivery_readiness": dict(self.delivery_readiness),
                "review_state": dict(self.review_state),
                "created_at": self.created_at}


@dataclass(frozen=True)
class AgentStep:
    """计划中的一步（§21）：稳定 step_id，不用 list index 作为身份（§37）。"""

    action: str
    target: Mapping[str, Any] = field(default_factory=dict)
    inputs: Mapping[str, Any] = field(default_factory=dict)
    sequence: int = 0
    step_id: str = ""
    preconditions: tuple[str, ...] = ()
    expected_revision: int | None = None
    idempotency_key: str = ""
    mutation: bool = False
    requires_approval: bool = False
    success_criteria: tuple[str, ...] = ()
    verification: str = ""

    def __post_init__(self) -> None:
        if not str(self.action or "").strip():
            raise AgentPlanInvalid("AgentStep 需要 action")
        if not self.step_id:
            object.__setattr__(self, "step_id", new_request_id("step"))
        if not self.idempotency_key:
            object.__setattr__(self, "idempotency_key", f"agent:{self.action}:{self.step_id}")

    def as_dict(self) -> dict[str, Any]:
        return {"step_id": self.step_id, "sequence": int(self.sequence),
                "action": self.action, "target": dict(self.target),
                "inputs": dict(self.inputs), "preconditions": list(self.preconditions),
                "expected_revision": self.expected_revision,
                "idempotency_key": self.idempotency_key,
                "mutation": bool(self.mutation),
                "requires_approval": bool(self.requires_approval),
                "success_criteria": list(self.success_criteria),
                "verification": self.verification}

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> "AgentStep":
        row = dict(raw or {})
        return cls(action=str(row.get("action") or ""),
                   target=dict(row.get("target") or {}),
                   inputs=dict(row.get("inputs") or {}),
                   sequence=int(row.get("sequence") or 0),
                   step_id=str(row.get("step_id") or ""),
                   preconditions=tuple(str(value) for value in
                                       (row.get("preconditions") or ())),
                   expected_revision=(int(row["expected_revision"])
                                      if row.get("expected_revision") is not None
                                      else None),
                   idempotency_key=str(row.get("idempotency_key") or ""),
                   mutation=bool(row.get("mutation")),
                   requires_approval=bool(row.get("requires_approval")),
                   success_criteria=tuple(str(value) for value in
                                          (row.get("success_criteria") or ())),
                   verification=str(row.get("verification") or ""))


@dataclass(frozen=True)
class AgentPlan:
    """结构化计划（§20、§31）：可版本化，replan 不修改旧 plan。"""

    novel_id: str
    goal_id: str
    steps: tuple[AgentStep, ...] = ()
    plan_id: str = ""
    plan_revision: int = 1
    estimated_mutations: int = 0
    estimated_model_calls: int = 0
    affected_nodes: tuple[str, ...] = ()
    protected_nodes: tuple[str, ...] = ()
    required_approvals: tuple[str, ...] = ()
    budget_estimate: Mapping[str, Any] = field(default_factory=dict)
    planner_version: str = "deterministic-v1"
    snapshot_digest: str = ""
    created_at: str = ""

    def __post_init__(self) -> None:
        if not self.plan_id:
            object.__setattr__(self, "plan_id", new_request_id("plan"))
        if not self.created_at:
            object.__setattr__(self, "created_at", utc_now())
        if int(self.plan_revision) < 1:
            raise AgentPlanInvalid("plan_revision 必须 >= 1")

    @property
    def mutations(self) -> int:
        return sum(1 for step in self.steps if step.mutation)

    def next_revision(self) -> "AgentPlan":
        return replace(self, plan_revision=int(self.plan_revision) + 1,
                       created_at=utc_now())

    def as_dict(self) -> dict[str, Any]:
        return {"plan_id": self.plan_id, "goal_id": self.goal_id,
                "novel_id": self.novel_id, "plan_revision": int(self.plan_revision),
                "steps": [step.as_dict() for step in self.steps],
                "estimated_mutations": int(self.estimated_mutations),
                "estimated_model_calls": int(self.estimated_model_calls),
                "affected_nodes": list(self.affected_nodes),
                "protected_nodes": list(self.protected_nodes),
                "required_approvals": list(self.required_approvals),
                "budget_estimate": dict(self.budget_estimate),
                "planner_version": self.planner_version,
                "snapshot_digest": self.snapshot_digest,
                "created_at": self.created_at}

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> "AgentPlan":
        row = dict(raw or {})
        return cls(novel_id=str(row.get("novel_id") or ""),
                   goal_id=str(row.get("goal_id") or ""),
                   steps=tuple(AgentStep.from_dict(item)
                               for item in (row.get("steps") or ())),
                   plan_id=str(row.get("plan_id") or ""),
                   plan_revision=int(row.get("plan_revision") or 1),
                   estimated_mutations=int(row.get("estimated_mutations") or 0),
                   estimated_model_calls=int(row.get("estimated_model_calls") or 0),
                   affected_nodes=tuple(str(value) for value in
                                        (row.get("affected_nodes") or ())),
                   protected_nodes=tuple(str(value) for value in
                                         (row.get("protected_nodes") or ())),
                   required_approvals=tuple(str(value) for value in
                                            (row.get("required_approvals") or ())),
                   budget_estimate=dict(row.get("budget_estimate") or {}),
                   planner_version=str(row.get("planner_version") or "deterministic-v1"),
                   snapshot_digest=str(row.get("snapshot_digest") or ""),
                   created_at=str(row.get("created_at") or ""))


@dataclass(frozen=True)
class AgentApprovalRequest:
    """approval 请求（§48–§49）：revision-aware，过期即 stale。"""

    action: str
    target: Mapping[str, Any]
    reason: str = ""
    before: Mapping[str, Any] = field(default_factory=dict)
    proposed_after: Mapping[str, Any] = field(default_factory=dict)
    affected_nodes: tuple[str, ...] = ()
    quality_summary: Mapping[str, Any] = field(default_factory=dict)
    risk: str = "structural"
    revision_refs: Mapping[str, int] = field(default_factory=dict)
    approval_id: str = ""
    session_id: str = ""
    plan_id: str = ""
    plan_revision: int = 1
    step_id: str = ""
    expires_if_revision_changes: bool = True
    created_at: str = ""

    def __post_init__(self) -> None:
        if not self.approval_id:
            object.__setattr__(self, "approval_id", new_request_id("approval"))
        if not self.created_at:
            object.__setattr__(self, "created_at", utc_now())

    def is_stale(self, *, revisions: Mapping[str, int]) -> bool:
        """绑定 revision 变了就过期（§49）。"""

        if not self.expires_if_revision_changes:
            return False
        for node_id, revision in dict(self.revision_refs).items():
            if int(dict(revisions).get(str(node_id)) or 0) != int(revision):
                return True
        return False

    def as_dict(self) -> dict[str, Any]:
        return {"approval_id": self.approval_id, "session_id": self.session_id,
                "plan_id": self.plan_id, "plan_revision": int(self.plan_revision),
                "step_id": self.step_id, "action": self.action,
                "target": dict(self.target), "reason": self.reason,
                "before": dict(self.before),
                "proposed_after": dict(self.proposed_after),
                "affected_nodes": list(self.affected_nodes),
                "quality_summary": dict(self.quality_summary), "risk": self.risk,
                "revision_refs": {key: int(value) for key, value
                                  in sorted(self.revision_refs.items())},
                "expires_if_revision_changes": bool(self.expires_if_revision_changes),
                "created_at": self.created_at}

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> "AgentApprovalRequest":
        row = dict(raw or {})
        return cls(action=str(row.get("action") or ""),
                   target=dict(row.get("target") or {}),
                   reason=str(row.get("reason") or ""),
                   before=dict(row.get("before") or {}),
                   proposed_after=dict(row.get("proposed_after") or {}),
                   affected_nodes=tuple(str(value) for value in
                                        (row.get("affected_nodes") or ())),
                   quality_summary=dict(row.get("quality_summary") or {}),
                   risk=str(row.get("risk") or "structural"),
                   revision_refs={str(key): int(value) for key, value
                                  in dict(row.get("revision_refs") or {}).items()},
                   approval_id=str(row.get("approval_id") or ""),
                   session_id=str(row.get("session_id") or ""),
                   plan_id=str(row.get("plan_id") or ""),
                   plan_revision=int(row.get("plan_revision") or 1),
                   step_id=str(row.get("step_id") or ""),
                   expires_if_revision_changes=bool(
                       row.get("expires_if_revision_changes", True)),
                   created_at=str(row.get("created_at") or ""))


@dataclass(frozen=True)
class AgentApprovalDecision:
    approval_id: str
    decision: str                      # approved | rejected | modified
    actor: str = "author"
    reason: str = ""
    created_at: str = ""

    def __post_init__(self) -> None:
        if self.decision not in ("approved", "rejected", "modified"):
            raise AgentPlanInvalid(f"未知 approval decision：{self.decision}")
        if not self.created_at:
            object.__setattr__(self, "created_at", utc_now())

    def as_dict(self) -> dict[str, Any]:
        return {"approval_id": self.approval_id, "decision": self.decision,
                "actor": self.actor, "reason": self.reason,
                "created_at": self.created_at}


@dataclass(frozen=True)
class AgentStepResult:
    """单步执行结果（§38）。"""

    step_id: str
    status: str
    action: str = ""
    started_at: str = ""
    finished_at: str = ""
    request_id: str = ""
    idempotency_key: str = ""
    revision_before: int = 0
    revision_after: int = 0
    result_refs: Mapping[str, Any] = field(default_factory=dict)
    issues: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    usage: Mapping[str, Any] = field(default_factory=dict)
    changed_nodes: tuple[str, ...] = ()
    error_code: str = ""
    message: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {"step_id": self.step_id, "status": self.status, "action": self.action,
                "started_at": self.started_at, "finished_at": self.finished_at,
                "request_id": self.request_id,
                "idempotency_key": self.idempotency_key,
                "revision_before": int(self.revision_before),
                "revision_after": int(self.revision_after),
                "result_refs": dict(self.result_refs),
                "issues": list(self.issues), "warnings": list(self.warnings),
                "usage": dict(self.usage),
                "changed_nodes": list(self.changed_nodes),
                "error_code": self.error_code, "message": self.message}


@dataclass
class AgentRun:
    """一次实际执行尝试（§19）：重试不覆盖历史。"""

    session_id: str
    plan_id: str
    plan_revision: int = 1
    run_id: str = ""
    status: str = "created"
    started_at: str = ""
    finished_at: str = ""
    step_results: list[AgentStepResult] = field(default_factory=list)
    stop_reason: str = ""
    cancel_requested: bool = False
    usage: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.run_id:
            self.run_id = new_request_id("run")
        if not self.started_at:
            self.started_at = utc_now()

    @property
    def mutations(self) -> int:
        return sum(1 for row in self.step_results
                   if row.status == "completed" and row.revision_after
                   and row.revision_after != row.revision_before)

    @property
    def changed_nodes(self) -> tuple[str, ...]:
        rows: set[str] = set()
        for result in self.step_results:
            rows.update(result.changed_nodes)
        return tuple(sorted(rows))

    def as_dict(self) -> dict[str, Any]:
        return {"run_id": self.run_id, "session_id": self.session_id,
                "plan_id": self.plan_id, "plan_revision": int(self.plan_revision),
                "status": self.status, "started_at": self.started_at,
                "finished_at": self.finished_at, "stop_reason": self.stop_reason,
                "cancel_requested": bool(self.cancel_requested),
                "mutations": self.mutations,
                "step_results": [row.as_dict() for row in self.step_results],
                "usage": dict(self.usage)}


@dataclass
class AgentResult:
    """统一结果（§73）：接口层只消费它（不接触内部 Plan 执行细节）。"""

    session_id: str
    run_id: str = ""
    status: str = "created"
    ok: bool = False
    goal: Mapping[str, Any] = field(default_factory=dict)
    plan: Mapping[str, Any] = field(default_factory=dict)
    completed_steps: tuple[str, ...] = ()
    pending_steps: tuple[str, ...] = ()
    changed_nodes: tuple[str, ...] = ()
    new_revisions: Mapping[str, int] = field(default_factory=dict)
    quality_summary: Mapping[str, Any] = field(default_factory=dict)
    approvals_required: tuple[Mapping[str, Any], ...] = ()
    usage: Mapping[str, Any] = field(default_factory=dict)
    warnings: tuple[str, ...] = ()
    errors: tuple[Mapping[str, Any], ...] = ()
    stop_reason: str = ""
    needs_human_review: bool = False
    step_results: tuple[Mapping[str, Any], ...] = ()

    def as_dict(self) -> dict[str, Any]:
        return {"ok": bool(self.ok), "status": self.status,
                "session_id": self.session_id, "run_id": self.run_id,
                "goal": dict(self.goal), "plan": dict(self.plan),
                "completed_steps": list(self.completed_steps),
                "pending_steps": list(self.pending_steps),
                "changed_nodes": list(self.changed_nodes),
                "new_revisions": {key: int(value) for key, value
                                  in sorted(self.new_revisions.items())},
                "quality_summary": dict(self.quality_summary),
                "approvals_required": [dict(row) for row in self.approvals_required],
                "usage": dict(self.usage), "warnings": list(self.warnings),
                "errors": [dict(row) for row in self.errors],
                "stop_reason": self.stop_reason,
                "needs_human_review": bool(self.needs_human_review),
                "steps": [dict(row) for row in self.step_results]}
