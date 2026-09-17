"""Repair Contract（V4-05 §6、§29–§31、§35–§38、§58）。

四个对象：

```text
RepairContract    一条 issue 的修复边界（preserve / allow_change / must_resolve / max_scope）
RepairStep        一个最小修复动作（节点 + 任务 + expected_revision + 契约）
RepairPlan        Planner 的输出（步骤 + 顺序 + blast radius + dry_run）
RepairResult      Executor 的结果（新 revision / usage / 是否 replay）
VerificationResult Verifier 的结果（resolved / remaining / new / regression）
```

铁律（§30 / §35 / §36 / §47）：

```text
· preserve 是硬约束：canon / 人物 id / source_ids / 已接受事实永不进入 allow_change
· 任何修复都产生**新 revision**（append-only），accepted 节点不被静默覆盖
· 修复不得产生新的 Canon 事实，不得修改 Canon / StoryState
· 模型不决定 scope / preserve：这些由 RepairPlanner 依据结构关系决定（§54）
```
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Mapping, Sequence

from novelforge.core.ids import digest_payload

from ..contracts import QualityScope, utc_now
from ..errors import RepairPlanError

if TYPE_CHECKING:  # pragma: no cover - 仅类型标注（避免循环 import）
    from .blast_radius import RepairBlastRadius

REPAIR_STRATEGIES: tuple[str, ...] = ("targeted", "scope_regenerate", "manual_only")
PLAN_STATUSES: tuple[str, ...] = ("planned", "empty", "conflict", "needs_human_review")
RESULT_STATUSES: tuple[str, ...] = ("planned", "applied", "idempotent_replay",
                                    "partial", "needs_human_review", "empty")
VERIFICATION_STATUSES: tuple[str, ...] = ("resolved", "partial", "unresolved",
                                          "regression")


def _sorted_unique(values: Sequence[str]) -> tuple[str, ...]:
    return tuple(sorted({str(value) for value in values if str(value)}))


@dataclass(frozen=True)
class RepairContract:
    """一次（可合并的）修复边界。"""

    issue_ids: tuple[str, ...]
    scope: QualityScope
    node_ids: tuple[str, ...] = ()
    preserve: tuple[str, ...] = ()
    allow_change: tuple[str, ...] = ()
    must_resolve: tuple[str, ...] = ()
    constraints: tuple[str, ...] = ()
    max_scope: tuple[str, ...] = ()
    strategy: str = "targeted"
    requires_human_review: bool = False
    reason: str = ""

    def __post_init__(self) -> None:
        if self.strategy not in REPAIR_STRATEGIES:
            raise RepairPlanError(f"未知 repair strategy：{self.strategy}")
        if not self.issue_ids:
            raise RepairPlanError("RepairContract 必须绑定至少一个 issue_id")
        overlap = set(self.allow_change) & set(self.preserve)
        if overlap:
            raise RepairPlanError(
                f"allow_change 与 preserve 冲突：{sorted(overlap)}",
                details={"node_ids": list(self.node_ids)})

    @property
    def contract_id(self) -> str:
        return "RC_" + digest_payload(
            {"issues": sorted(self.issue_ids), "nodes": list(self.node_ids),
             "preserve": list(self.preserve),
             "allow_change": list(self.allow_change)})[:12]

    def as_dict(self) -> dict[str, Any]:
        return {"contract_id": self.contract_id,
                "issue_ids": list(self.issue_ids),
                "scope": self.scope.as_dict(), "node_ids": list(self.node_ids),
                "preserve": list(self.preserve),
                "allow_change": list(self.allow_change),
                "must_resolve": list(self.must_resolve),
                "constraints": list(self.constraints),
                "max_scope": list(self.max_scope),
                "strategy": self.strategy,
                "requires_human_review": self.requires_human_review,
                "reason": self.reason}


@dataclass(frozen=True)
class RepairStep:
    """一个最小修复动作（一个节点 → 一个 Generation 任务）。"""

    step_id: str
    order: int
    node_id: str
    node_type: str
    task: str
    gate: str
    expected_revision: int
    issue_ids: tuple[str, ...]
    contract: RepairContract
    preserve: tuple[str, ...] = ()
    allow_change: tuple[str, ...] = ()
    reason: str = ""
    requires_human_review: bool = False
    constraints: tuple[str, ...] = ()

    @property
    def must_resolve(self) -> tuple[str, ...]:
        return tuple(self.contract.must_resolve or self.issue_ids)

    def as_dict(self) -> dict[str, Any]:
        return {"step_id": self.step_id, "order": self.order,
                "node_id": self.node_id, "node_type": self.node_type,
                "task": self.task, "gate": self.gate,
                "expected_revision": self.expected_revision,
                "issue_ids": list(self.issue_ids),
                "preserve": list(self.preserve),
                "allow_change": list(self.allow_change),
                "constraints": list(self.constraints),
                "reason": self.reason,
                "requires_human_review": self.requires_human_review,
                "contract": self.contract.as_dict(), "dry_run": False}


@dataclass(frozen=True)
class RepairPlan:
    """RepairPlanner 的输出：**不写任何 revision**（§31 / §58）。"""

    plan_id: str
    novel_id: str
    scope: QualityScope
    status: str = "planned"
    steps: tuple[RepairStep, ...] = ()
    contracts: tuple[RepairContract, ...] = ()
    blast_radius: "RepairBlastRadius | None" = None
    conflicts: tuple[str, ...] = ()
    human_review_reasons: tuple[str, ...] = ()
    notes: tuple[str, ...] = ()
    dry_run: bool = True
    issue_ids: tuple[str, ...] = ()
    created_at: str = ""

    def __post_init__(self) -> None:
        if self.status not in PLAN_STATUSES:
            raise RepairPlanError(f"未知 plan status：{self.status}")
        if not self.created_at:
            object.__setattr__(self, "created_at", utc_now())

    @property
    def estimated_model_calls(self) -> int:
        return len([step for step in self.steps
                    if not step.requires_human_review])

    @property
    def target_node_ids(self) -> tuple[str, ...]:
        return _sorted_unique([step.node_id for step in self.steps])

    @property
    def needs_human_review(self) -> bool:
        return self.status in ("conflict", "needs_human_review")

    def as_dict(self) -> dict[str, Any]:
        return {"plan_id": self.plan_id, "novel_id": self.novel_id,
                "status": self.status, "dry_run": self.dry_run,
                "scope": self.scope.as_dict(),
                "issue_ids": list(self.issue_ids),
                "target_node_ids": list(self.target_node_ids),
                "steps": [step.as_dict() for step in self.steps],
                "contracts": [row.as_dict() for row in self.contracts],
                "blast_radius": (self.blast_radius.as_dict()
                                 if self.blast_radius is not None else {}),
                "conflicts": list(self.conflicts),
                "human_review_reasons": list(self.human_review_reasons),
                "notes": list(self.notes),
                "estimated_model_calls": self.estimated_model_calls,
                "created_at": self.created_at}


@dataclass(frozen=True)
class RepairResult:
    """RepairExecutor 的输出（新 revision / usage / replay 标记）。"""

    plan_id: str
    novel_id: str
    status: str
    dry_run: bool = False
    applied_steps: tuple[Mapping[str, Any], ...] = ()
    replayed_steps: tuple[Mapping[str, Any], ...] = ()
    blocked_steps: tuple[Mapping[str, Any], ...] = ()
    before_revisions: Mapping[str, int] = field(default_factory=dict)
    after_revisions: Mapping[str, int] = field(default_factory=dict)
    resolved_issue_ids: tuple[str, ...] = ()
    usage: Mapping[str, Any] = field(default_factory=dict)
    notes: tuple[str, ...] = ()
    created_at: str = ""

    def __post_init__(self) -> None:
        if self.status not in RESULT_STATUSES:
            raise RepairPlanError(f"未知 repair result status：{self.status}")
        if not self.created_at:
            object.__setattr__(self, "created_at", utc_now())

    @property
    def revisions(self) -> dict[str, int]:
        return dict(self.after_revisions)

    @property
    def model_calls(self) -> int:
        return sum(int(row.get("model_calls") or 0) for row in self.applied_steps)

    def as_dict(self) -> dict[str, Any]:
        return {"plan_id": self.plan_id, "novel_id": self.novel_id,
                "status": self.status, "dry_run": self.dry_run,
                "applied_steps": [dict(row) for row in self.applied_steps],
                "replayed_steps": [dict(row) for row in self.replayed_steps],
                "blocked_steps": [dict(row) for row in self.blocked_steps],
                "before_revisions": dict(self.before_revisions),
                "after_revisions": dict(self.after_revisions),
                "resolved_issue_ids": list(self.resolved_issue_ids),
                "usage": dict(self.usage), "notes": list(self.notes),
                "model_calls": self.model_calls, "created_at": self.created_at}


@dataclass(frozen=True)
class VerificationResult:
    """RepairVerifier 的输出（§38）：修复是否真的解决了问题。"""

    novel_id: str
    status: str
    original_issue_ids: tuple[str, ...] = ()
    resolved_issue_ids: tuple[str, ...] = ()
    remaining_issue_ids: tuple[str, ...] = ()
    new_issue_ids: tuple[str, ...] = ()
    before_revisions: Mapping[str, int] = field(default_factory=dict)
    after_revisions: Mapping[str, int] = field(default_factory=dict)
    gates_rechecked: tuple[str, ...] = ()
    before_report_id: str = ""
    after_report_id: str = ""
    quality_status: str = ""
    usage: Mapping[str, Any] = field(default_factory=dict)
    notes: tuple[str, ...] = ()
    created_at: str = ""
    #: 复核后的 QualityReport（进程内句柄；`as_dict()` 只暴露 report_id，不序列化全量）
    report: Any = None

    def __post_init__(self) -> None:
        if self.status not in VERIFICATION_STATUSES:
            raise RepairPlanError(f"未知 verification status：{self.status}")
        if not self.created_at:
            object.__setattr__(self, "created_at", utc_now())

    @property
    def ok(self) -> bool:
        return self.status == "resolved"

    @property
    def revisions_changed(self) -> dict[str, dict[str, int]]:
        return {node_id: {"before": int(self.before_revisions.get(node_id) or 0),
                          "after": int(self.after_revisions.get(node_id) or 0)}
                for node_id in sorted(set(self.before_revisions)
                                      | set(self.after_revisions))}

    def as_dict(self) -> dict[str, Any]:
        return {"novel_id": self.novel_id, "status": self.status,
                "original_issue_ids": list(self.original_issue_ids),
                "resolved_issue_ids": list(self.resolved_issue_ids),
                "remaining_issue_ids": list(self.remaining_issue_ids),
                "new_issue_ids": list(self.new_issue_ids),
                "before_revisions": dict(self.before_revisions),
                "after_revisions": dict(self.after_revisions),
                "revisions_changed": self.revisions_changed,
                "gates_rechecked": list(self.gates_rechecked),
                "before_report_id": self.before_report_id,
                "after_report_id": self.after_report_id,
                "quality_status": self.quality_status,
                "usage": dict(self.usage), "notes": list(self.notes),
                "created_at": self.created_at}


__all__ = [
    "PLAN_STATUSES", "REPAIR_STRATEGIES", "RESULT_STATUSES",
    "VERIFICATION_STATUSES", "RepairContract", "RepairPlan", "RepairResult",
    "RepairStep", "VerificationResult",
]
