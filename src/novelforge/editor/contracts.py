"""Editor 契约（V4-06 §6、§9、§12、§13、§19、§41、§42、§47、§73）。

Public Contract 只暴露这些对象；`PatchApplier` / `DiffWalker` 之类的内部实现不公开。

```text
EditRequest / EditResult                 手工字段级修改
BatchEditRequest / BatchEditResult       多节点（transaction-like）修改
RewriteRequest / RewriteResult           AI 只改指定字段
DiffRequest / BlueprintDiff              结构化比较（diff 见 diff.py）
ApprovalResult                           accept / reject
RestoreResult                            restore / undo（产生新 revision）
ChangeImpact                             修改影响面（不自动改下游）
RevisionView / RevisionHistory           revision 导航
EditorOperationRecord / ReviewDecision   审计（editor metadata，不是 story truth）
EditorSession                            轻量会话（内存，不持久化）
MoveNodeRequest                          结构移动（独立契约，不走 patch）
```
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

from novelforge.core.ids import new_request_id

from .errors import EditorValidationError

#: 操作类型（写入 EditorOperationRecord.operation）
OPERATION_KINDS: tuple[str, ...] = (
    "manual_patch", "batch_patch", "ai_rewrite", "ai_regenerate", "accept", "reject",
    "restore", "undo", "move", "quality_repair", "system",
)

#: 作者身份（§12：至少可区分这些来源）
AUTHOR_KINDS: tuple[str, ...] = (
    "human", "ai_generation", "ai_repair", "ai_rewrite", "restore", "system",
)

#: 结果状态
EDIT_STATUSES: tuple[str, ...] = ("applied", "dry_run", "rejected", "conflict",
                                  "partial")
REVIEW_DECISIONS: tuple[str, ...] = ("accepted", "rejected")
#: 批量策略（§38）
BATCH_POLICIES: tuple[str, ...] = ("all_or_rollback", "partial")


def _require(value: Any, message: str, **details: Any) -> None:
    if not str(value or "").strip():
        raise EditorValidationError(message, details=details)


@dataclass(frozen=True)
class EditRequest:
    """字段级 patch（§9）：不接收整节点覆盖。"""

    novel_id: str
    node_id: str
    expected_revision: int | None
    changes: Mapping[str, Any]
    actor: str = "human"
    reason: str = ""
    idempotency_key: str = ""
    request_id: str = ""
    dry_run: bool = False

    def __post_init__(self) -> None:
        _require(self.novel_id, "EditRequest 需要显式 novel_id")
        _require(self.node_id, "EditRequest 需要 node_id")
        if not isinstance(self.changes, Mapping) or not self.changes:
            raise EditorValidationError("EditRequest.changes 必须是非空字段字典",
                                        details={"node_id": self.node_id})
        if self.actor not in AUTHOR_KINDS:
            raise EditorValidationError(f"未知 actor：{self.actor}")
        if not self.request_id:
            object.__setattr__(self, "request_id", new_request_id("edit"))

    def as_dict(self) -> dict[str, Any]:
        return {"novel_id": self.novel_id, "node_id": self.node_id,
                "expected_revision": self.expected_revision,
                "changes": dict(self.changes), "actor": self.actor,
                "reason": self.reason, "idempotency_key": self.idempotency_key,
                "request_id": self.request_id, "dry_run": self.dry_run}


@dataclass(frozen=True)
class EditResult:
    node_id: str
    novel_id: str
    status: str
    before_revision: int = 0
    revision: int = 0
    changed_fields: tuple[str, ...] = ()
    unchanged_fields: tuple[str, ...] = ()
    dry_run: bool = False
    operation_id: str = ""
    request_id: str = ""
    diff: Any = None
    impact: Any = None
    quality_status: str = "unevaluated"
    notes: tuple[str, ...] = ()
    rejected_reason: str = ""

    def __post_init__(self) -> None:
        if self.status not in EDIT_STATUSES:
            raise EditorValidationError(f"未知 edit status：{self.status}")

    @property
    def ok(self) -> bool:
        return self.status in ("applied", "dry_run")

    def as_dict(self) -> dict[str, Any]:
        return {"node_id": self.node_id, "novel_id": self.novel_id,
                "status": self.status, "ok": self.ok, "dry_run": self.dry_run,
                "before_revision": self.before_revision,
                "revision": self.revision,
                "changed_fields": list(self.changed_fields),
                "unchanged_fields": list(self.unchanged_fields),
                "quality_status": self.quality_status,
                "operation_id": self.operation_id, "request_id": self.request_id,
                "diff": self.diff.as_dict() if self.diff is not None else None,
                "impact": self.impact.as_dict() if self.impact is not None else None,
                "notes": list(self.notes), "rejected_reason": self.rejected_reason}


@dataclass(frozen=True)
class BatchEditRequest:
    """多节点修改（§38）：默认 all_or_rollback（先全量校验，不写一半）。"""

    novel_id: str
    requests: tuple[EditRequest, ...]
    actor: str = "human"
    reason: str = ""
    idempotency_key: str = ""
    policy: str = "all_or_rollback"
    dry_run: bool = False

    def __post_init__(self) -> None:
        _require(self.novel_id, "BatchEditRequest 需要显式 novel_id")
        if not self.requests:
            raise EditorValidationError("BatchEditRequest 至少需要一个 EditRequest")
        if self.policy not in BATCH_POLICIES:
            raise EditorValidationError(f"未知 batch policy：{self.policy}")
        for row in self.requests:
            if row.novel_id != self.novel_id:
                raise EditorValidationError(
                    "批量请求中包含其他作品的节点",
                    details={"expected": self.novel_id, "found": row.novel_id})

    def as_dict(self) -> dict[str, Any]:
        return {"novel_id": self.novel_id,
                "requests": [row.as_dict() for row in self.requests],
                "actor": self.actor, "reason": self.reason,
                "idempotency_key": self.idempotency_key, "policy": self.policy,
                "dry_run": self.dry_run}


@dataclass(frozen=True)
class BatchEditResult:
    novel_id: str
    status: str
    results: tuple[EditResult, ...] = ()
    applied_node_ids: tuple[str, ...] = ()
    rejected_node_ids: tuple[str, ...] = ()
    conflict_node_ids: tuple[str, ...] = ()
    notes: tuple[str, ...] = ()

    @property
    def ok(self) -> bool:
        return self.status in ("applied", "dry_run")

    def as_dict(self) -> dict[str, Any]:
        return {"novel_id": self.novel_id, "status": self.status,
                "ok": self.ok,
                "results": [row.as_dict() for row in self.results],
                "applied_node_ids": list(self.applied_node_ids),
                "rejected_node_ids": list(self.rejected_node_ids),
                "conflict_node_ids": list(self.conflict_node_ids),
                "notes": list(self.notes)}


@dataclass(frozen=True)
class RewriteRequest:
    """AI 只改指定字段（§19）：默认不改整节点。"""

    novel_id: str
    node_id: str
    expected_revision: int | None
    target_fields: tuple[str, ...]
    instruction: str
    preserve_fields: tuple[str, ...] = ()
    quality_issue_ids: tuple[str, ...] = ()
    idempotency_key: str = ""
    request_id: str = ""
    dry_run: bool = False
    actor: str = "ai_rewrite"
    model_policy: Any = None

    def __post_init__(self) -> None:
        _require(self.novel_id, "RewriteRequest 需要显式 novel_id")
        _require(self.node_id, "RewriteRequest 需要 node_id")
        if not self.target_fields:
            raise EditorValidationError("RewriteRequest 必须显式声明 target_fields",
                                        details={"node_id": self.node_id})
        if not str(self.instruction or "").strip():
            raise EditorValidationError("RewriteRequest 需要 instruction")
        if not self.request_id:
            object.__setattr__(self, "request_id", new_request_id("rewrite"))

    def as_dict(self) -> dict[str, Any]:
        return {"novel_id": self.novel_id, "node_id": self.node_id,
                "expected_revision": self.expected_revision,
                "target_fields": list(self.target_fields),
                "preserve_fields": list(self.preserve_fields),
                "quality_issue_ids": list(self.quality_issue_ids),
                "instruction": self.instruction,
                "idempotency_key": self.idempotency_key,
                "request_id": self.request_id, "dry_run": self.dry_run,
                "actor": self.actor}


@dataclass(frozen=True)
class RewriteResult:
    node_id: str
    novel_id: str
    status: str
    target_fields: tuple[str, ...] = ()
    before_revision: int = 0
    revision: int = 0
    changed_fields: tuple[str, ...] = ()
    violations: tuple[str, ...] = ()
    dry_run: bool = False
    operation_id: str = ""
    request_id: str = ""
    diff: Any = None
    impact: Any = None
    usage: Mapping[str, Any] = field(default_factory=dict)
    model: str = ""
    provider: str = ""
    contract_id: str = ""
    notes: tuple[str, ...] = ()

    @property
    def ok(self) -> bool:
        return self.status in ("applied", "dry_run")

    def as_dict(self) -> dict[str, Any]:
        return {"node_id": self.node_id, "novel_id": self.novel_id,
                "status": self.status, "ok": self.ok, "dry_run": self.dry_run,
                "target_fields": list(self.target_fields),
                "before_revision": self.before_revision,
                "revision": self.revision,
                "changed_fields": list(self.changed_fields),
                "violations": list(self.violations),
                "operation_id": self.operation_id, "request_id": self.request_id,
                "diff": self.diff.as_dict() if self.diff is not None else None,
                "impact": self.impact.as_dict() if self.impact is not None else None,
                "usage": dict(self.usage), "model": self.model,
                "provider": self.provider, "contract_id": self.contract_id,
                "notes": list(self.notes)}


@dataclass(frozen=True)
class DiffRequest:
    novel_id: str
    node_id: str
    from_revision: int
    to_revision: int | None = None

    def __post_init__(self) -> None:
        _require(self.novel_id, "DiffRequest 需要显式 novel_id")
        _require(self.node_id, "DiffRequest 需要 node_id")
        if int(self.from_revision) < 1:
            raise EditorValidationError("from_revision 必须 >= 1")


@dataclass(frozen=True)
class ApprovalResult:
    """accept / reject 结果（§22–§23）。"""

    node_id: str
    novel_id: str
    decision: str
    reviewed_revision: int = 0
    revision: int = 0
    status: str = ""
    quality_status: str = ""
    review_note: str = ""
    operation_id: str = ""
    idempotent: bool = False
    previous_status: str = ""
    notes: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.decision not in REVIEW_DECISIONS:
            raise EditorValidationError(f"未知 review decision：{self.decision}")

    @property
    def ok(self) -> bool:
        return self.status in ("applied", "recorded")

    def as_dict(self) -> dict[str, Any]:
        return {"node_id": self.node_id, "novel_id": self.novel_id,
                "decision": self.decision, "ok": self.ok, "status": self.status,
                "reviewed_revision": self.reviewed_revision,
                "revision": self.revision,
                "previous_status": self.previous_status,
                "quality_status": self.quality_status,
                "review_note": self.review_note, "operation_id": self.operation_id,
                "idempotent": self.idempotent, "notes": list(self.notes)}


@dataclass(frozen=True)
class RestoreResult:
    """restore / undo 结果（§25–§26、§60）。"""

    node_id: str
    novel_id: str
    operation: str
    restored_from: int
    before_revision: int = 0
    revision: int = 0
    status: str = ""
    changed_fields: tuple[str, ...] = ()
    operation_id: str = ""
    diff: Any = None
    impact: Any = None
    notes: tuple[str, ...] = ()

    @property
    def ok(self) -> bool:
        return self.status == "applied"

    def as_dict(self) -> dict[str, Any]:
        return {"node_id": self.node_id, "novel_id": self.novel_id,
                "operation": self.operation, "ok": self.ok,
                "status": self.status, "restored_from": self.restored_from,
                "before_revision": self.before_revision,
                "revision": self.revision,
                "changed_fields": list(self.changed_fields),
                "operation_id": self.operation_id,
                "diff": self.diff.as_dict() if self.diff is not None else None,
                "impact": self.impact.as_dict() if self.impact is not None else None,
                "notes": list(self.notes)}


@dataclass(frozen=True)
class ChangeImpact:
    """修改影响面（§71–§73）：只报告，不自动修改下游。"""

    novel_id: str
    node_id: str
    revision: int
    changed_fields: tuple[str, ...] = ()
    dependent_nodes: tuple[str, ...] = ()
    quality_invalidations: tuple[str, ...] = ()
    reasons: Mapping[str, tuple[str, ...]] = field(default_factory=dict)
    summary: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {"novel_id": self.novel_id, "node_id": self.node_id,
                "revision": self.revision,
                "changed_fields": list(self.changed_fields),
                "dependent_nodes": list(self.dependent_nodes),
                "quality_invalidations": list(self.quality_invalidations),
                "reasons": {key: list(value)
                            for key, value in sorted(self.reasons.items())},
                "summary": self.summary,
                "auto_modified": False}


@dataclass(frozen=True)
class RevisionView:
    """一个 revision 的编辑视图（§12）。"""

    node_id: str
    novel_id: str
    node_type: str
    revision: int
    parent_revision: int = 0
    status: str = ""
    quality_status: str = ""
    created_at: str = ""
    updated_at: str = ""
    source: str = ""
    author: str = "system"
    operation: str = ""
    request_id: str = ""
    summary: str = ""
    changed_fields: tuple[str, ...] = ()
    source_ids: tuple[str, ...] = ()
    generation_contract: str = ""
    restored_from: int | None = None
    review_status: str = "pending"
    review_note: str = ""
    is_current: bool = False
    quality_revision_stale: bool = False

    def as_dict(self) -> dict[str, Any]:
        return {"node_id": self.node_id, "novel_id": self.novel_id,
                "node_type": self.node_type, "revision": self.revision,
                "parent_revision": self.parent_revision, "status": self.status,
                "quality_status": self.quality_status,
                "created_at": self.created_at, "updated_at": self.updated_at,
                "source": self.source, "author": self.author,
                "operation": self.operation, "request_id": self.request_id,
                "summary": self.summary,
                "changed_fields": list(self.changed_fields),
                "source_ids": list(self.source_ids),
                "generation_contract": self.generation_contract,
                "restored_from": self.restored_from,
                "review_status": self.review_status,
                "review_note": self.review_note, "is_current": self.is_current,
                "quality_revision_stale": self.quality_revision_stale}


@dataclass(frozen=True)
class RevisionHistory:
    novel_id: str
    node_id: str
    current_revision: int = 0
    revisions: tuple[RevisionView, ...] = ()
    operations: tuple[Mapping[str, Any], ...] = ()

    def as_dict(self) -> dict[str, Any]:
        return {"novel_id": self.novel_id, "node_id": self.node_id,
                "current_revision": self.current_revision,
                "revision_count": len(self.revisions),
                "revisions": [row.as_dict() for row in self.revisions],
                "operations": [dict(row) for row in self.operations]}


@dataclass(frozen=True)
class EditorOperationRecord:
    """审计记录（§13、§47）：属于 editor metadata，不是 Blueprint payload。"""

    novel_id: str
    operation: str
    node_id: str
    operation_id: str = ""
    actor: str = "human"
    request_id: str = ""
    source_revision: int = 0
    result_revision: int = 0
    changed_fields: tuple[str, ...] = ()
    reason: str = ""
    status: str = "applied"
    idempotency_key: str = ""
    created_at: str = ""
    ai: Mapping[str, Any] = field(default_factory=dict)
    impact: Mapping[str, Any] = field(default_factory=dict)
    extra: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.operation not in OPERATION_KINDS:
            raise EditorValidationError(f"未知 operation：{self.operation}")
        if not self.operation_id:
            object.__setattr__(self, "operation_id", new_request_id("EO"))

    def as_dict(self) -> dict[str, Any]:
        return {"operation_id": self.operation_id, "novel_id": self.novel_id,
                "operation": self.operation, "node_id": self.node_id,
                "actor": self.actor, "request_id": self.request_id,
                "source_revision": self.source_revision,
                "result_revision": self.result_revision,
                "changed_fields": list(self.changed_fields),
                "reason": self.reason, "status": self.status,
                "idempotency_key": self.idempotency_key,
                "created_at": self.created_at, "ai": dict(self.ai),
                "impact": dict(self.impact), "extra": dict(self.extra)}


@dataclass(frozen=True)
class ReviewDecision:
    """accept / reject 的 review 记录（§22–§23、§68）。"""

    node_id: str
    novel_id: str
    revision: int
    decision: str
    actor: str = "human"
    reason: str = ""
    operation_id: str = ""
    created_at: str = ""
    resulting_revision: int = 0

    def __post_init__(self) -> None:
        if self.decision not in REVIEW_DECISIONS:
            raise EditorValidationError(f"未知 review decision：{self.decision}")

    def as_dict(self) -> dict[str, Any]:
        return {"node_id": self.node_id, "novel_id": self.novel_id,
                "revision": self.revision, "decision": self.decision,
                "actor": self.actor, "reason": self.reason,
                "operation_id": self.operation_id,
                "resulting_revision": self.resulting_revision,
                "created_at": self.created_at}


@dataclass(frozen=True)
class EditorSession:
    """轻量会话（§42）：内存对象，本阶段不持久化，不做多人协同。"""

    session_id: str
    novel_id: str
    actor: str = "human"
    opened_node: str = ""
    base_revision: int = 0
    created_at: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {"session_id": self.session_id, "novel_id": self.novel_id,
                "actor": self.actor, "opened_node": self.opened_node,
                "base_revision": self.base_revision,
                "created_at": self.created_at, "persisted": False}


@dataclass(frozen=True)
class MoveNodeRequest:
    """结构移动（§39）：独立契约，不允许通过 patch 改 parent / sequence。"""

    novel_id: str
    node_id: str
    expected_revision: int | None
    parent_id: str | None = None
    sequence: int | None = None
    actor: str = "human"
    reason: str = ""
    idempotency_key: str = ""
    request_id: str = ""

    def __post_init__(self) -> None:
        _require(self.novel_id, "MoveNodeRequest 需要显式 novel_id")
        _require(self.node_id, "MoveNodeRequest 需要 node_id")
        if self.parent_id is None and self.sequence is None:
            raise EditorValidationError("MoveNodeRequest 至少要改 parent_id 或 sequence")
        if not self.request_id:
            object.__setattr__(self, "request_id", new_request_id("move"))


def sequence_of(values: Sequence[str]) -> str:
    return ",".join(str(value) for value in values)


__all__ = [
    "AUTHOR_KINDS", "BATCH_POLICIES", "EDIT_STATUSES", "OPERATION_KINDS",
    "REVIEW_DECISIONS", "ApprovalResult", "BatchEditRequest", "BatchEditResult",
    "ChangeImpact", "DiffRequest", "EditRequest", "EditResult", "EditorOperationRecord",
    "EditorSession", "MoveNodeRequest", "RestoreResult", "ReviewDecision",
    "RevisionHistory", "RevisionView", "RewriteRequest", "RewriteResult",
    "sequence_of",
]
