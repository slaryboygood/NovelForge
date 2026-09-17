"""M8B：Batch / Checkpoint / Progressive Elaboration 只读 projection（供 M13 Compile Center）。

原则与 M8A projection 完全相同：

- 只读、non_authoritative，不写任何 store，不复制 story truth；
- 进度不显示"完成度百分比"，而是 batches completed/total、各 detail level 计数、
  blocked / human_review / retrying、final revision 这类离散事实；
- 所有对象都带 source ids / digests，UI 可以据此判断数据是否过期。
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal, Mapping

from pydantic import Field

from novelforge.models import StrictModel

from .models import StoryPlanningIR
from .outline_batch import (
    CLOSED_CARRY_STATES,
    DETAIL_ORDER,
    ElaborationStatus,
    OutlineBatchCheckpoint,
    OutlineBatchDiff,
    OutlineBatchSession,
    OutlineBatchTask,
    plan_elaboration_status,
)


class BatchTaskProjection(StrictModel):
    batch_id: str = Field(default="", max_length=64)
    sequence: int = 0
    status: str = Field(default="pending", max_length=24)
    scope_kind: str = Field(default="", max_length=32)
    scope_note: str = Field(default="", max_length=200)
    scope_node_count: int = 0
    source_detail_level: str = Field(default="", max_length=24)
    target_detail_level: str = Field(default="", max_length=24)
    source_revision_id: str = Field(default="", max_length=64)
    promoted_revision_id: str = Field(default="", max_length=64)
    candidate_id: str = Field(default="", max_length=64)
    dependency_batch_ids: list[str] = Field(default_factory=list)
    supersedes_batch_ids: list[str] = Field(default_factory=list)
    attempt_count: int = 0
    error_class: str = Field(default="", max_length=32)
    error_summary: str = Field(default="", max_length=300)
    read_only: Literal[True] = True
    non_authoritative: Literal[True] = True


class CheckpointProjection(StrictModel):
    batch_id: str = Field(default="", max_length=64)
    status: str = Field(default="", max_length=24)
    schema_version: int = 0
    source_revision_id: str = Field(default="", max_length=64)
    source_digest: str = Field(default="", max_length=64)
    candidate_id: str = Field(default="", max_length=64)
    candidate_digest: str = Field(default="", max_length=64)
    validation_digest: str = Field(default="", max_length=64)
    promoted_revision_id: str = Field(default="", max_length=64)
    promoted_digest: str = Field(default="", max_length=64)
    config_digest: str = Field(default="", max_length=64)
    attempt_count: int = 0
    completed_steps: list[str] = Field(default_factory=list)
    pending_steps: list[str] = Field(default_factory=list)
    finding_codes: dict[str, int] = Field(default_factory=dict)
    blocking_count: int = 0
    review_codes: list[str] = Field(default_factory=list)
    error_class: str = Field(default="", max_length=32)
    next_retry_at: datetime | None = None
    updated_at: datetime | None = None
    read_only: Literal[True] = True
    non_authoritative: Literal[True] = True


class RevisionChainRow(StrictModel):
    batch_id: str = Field(default="", max_length=64)
    source_revision_id: str = Field(default="", max_length=64)
    promoted_revision_id: str = Field(default="", max_length=64)
    promoted_digest: str = Field(default="", max_length=64)
    recovered: bool = False
    read_only: Literal[True] = True
    non_authoritative: Literal[True] = True


class RevisionChainProjection(StrictModel):
    session_id: str = Field(default="", max_length=64)
    root_revision_id: str = Field(default="", max_length=64)
    final_revision_id: str = Field(default="", max_length=64)
    current_revision_id: str = Field(default="", max_length=64)
    contiguous: bool = False
    rows: list[RevisionChainRow] = Field(default_factory=list)
    read_only: Literal[True] = True
    non_authoritative: Literal[True] = True


class BatchSessionProjection(StrictModel):
    """M13 Compile Center 需要的最小 backend state。"""

    session_id: str = Field(default="", max_length=64)
    novel_id: str = Field(default="", max_length=96)
    status: str = Field(default="pending", max_length=24)
    scope_complete: bool = False
    target_detail_level: str = Field(default="arc", max_length=24)
    target_scope_kind: str = Field(default="", max_length=32)
    promotion_mode: str = Field(default="manual", max_length=24)
    root_revision_id: str = Field(default="", max_length=64)
    current_revision_id: str = Field(default="", max_length=64)
    current_digest: str = Field(default="", max_length=64)
    final_revision_id: str = Field(default="", max_length=64)
    config_digest: str = Field(default="", max_length=64)
    batches_completed: int = 0
    batches_total: int = 0
    running_batch_id: str = Field(default="", max_length=64)
    next_batch_id: str = Field(default="", max_length=64)
    running_scope_note: str = Field(default="", max_length=200)
    blocked_batch_ids: list[str] = Field(default_factory=list)
    human_review_batch_ids: list[str] = Field(default_factory=list)
    retrying_batch_ids: list[str] = Field(default_factory=list)
    failed_batch_ids: list[str] = Field(default_factory=list)
    last_validation_status: str = Field(default="", max_length=24)
    last_warning_codes: list[str] = Field(default_factory=list)
    last_blocking_codes: list[str] = Field(default_factory=list)
    resume_required: bool = False
    detail_level_counts: dict[str, int] = Field(default_factory=dict)
    tasks: list[BatchTaskProjection] = Field(default_factory=list)
    checkpoints: list[CheckpointProjection] = Field(default_factory=list)
    read_only: Literal[True] = True
    non_authoritative: Literal[True] = True


class ElaborationProgressProjection(StrictModel):
    rows: list[ElaborationStatus] = Field(default_factory=list)
    detail_level_counts: dict[str, int] = Field(default_factory=dict)
    remaining_object_ids: list[str] = Field(default_factory=list)
    blocked_object_ids: list[str] = Field(default_factory=list)
    source_revision_id: str = Field(default="", max_length=64)
    read_only: Literal[True] = True
    non_authoritative: Literal[True] = True


class BatchDiffProjection(StrictModel):
    before_revision: str = Field(default="", max_length=64)
    after_revision: str = Field(default="", max_length=64)
    volumes_added: list[str] = Field(default_factory=list)
    volumes_modified: list[str] = Field(default_factory=list)
    arcs_added: list[str] = Field(default_factory=list)
    arcs_modified: list[str] = Field(default_factory=list)
    allocations_changed: list[str] = Field(default_factory=list)
    budget_changes: dict[str, list[int]] = Field(default_factory=dict)
    boundary_changes: list[str] = Field(default_factory=list)
    carryover_changes: list[str] = Field(default_factory=list)
    detail_level_changes: list[str] = Field(default_factory=list)
    findings_changes: dict[str, int] = Field(default_factory=dict)
    read_only: Literal[True] = True
    non_authoritative: Literal[True] = True


class PlanningCompletenessProjection(StrictModel):
    """按 detail level / scope 显示 planning 目前到底做到了哪一层（只读）。"""

    revision_id: str = Field(default="", max_length=64)
    content_digest: str = Field(default="", max_length=64)
    volumes_total: int = 0
    volumes_by_level: dict[str, int] = Field(default_factory=dict)
    arcs_total: int = 0
    arcs_by_level: dict[str, int] = Field(default_factory=dict)
    spine_coverage: int = 0
    volume_coverage: int = 0
    arc_coverage: int = 0
    chapter_ready_coverage: int = 0
    remaining_elaboration_scopes: list[str] = Field(default_factory=list)
    read_only: Literal[True] = True
    non_authoritative: Literal[True] = True


def project_batch_task(task: OutlineBatchTask) -> BatchTaskProjection:
    return BatchTaskProjection(
        batch_id=task.batch_id, sequence=task.sequence, status=task.status,
        scope_kind=task.scope.kind, scope_note=task.scope.note,
        scope_node_count=len(task.scope.node_ids),
        source_detail_level=task.source_detail_level,
        target_detail_level=task.target_detail_level,
        source_revision_id=task.source_revision_id,
        promoted_revision_id=task.promoted_revision_id, candidate_id=task.candidate_id,
        dependency_batch_ids=list(task.dependency_batch_ids),
        supersedes_batch_ids=list(task.supersedes_batch_ids),
        attempt_count=task.attempt_count, error_class=task.error_class or "",
        error_summary=task.error_summary)


def project_checkpoint(checkpoint: OutlineBatchCheckpoint) -> CheckpointProjection:
    codes: dict[str, int] = {}
    for finding in checkpoint.findings:
        codes[finding.code] = codes.get(finding.code, 0) + 1
    return CheckpointProjection(
        batch_id=checkpoint.batch_id, status=checkpoint.status,
        schema_version=checkpoint.schema_version,
        source_revision_id=checkpoint.source_revision_id,
        source_digest=checkpoint.source_digest, candidate_id=checkpoint.candidate_id,
        candidate_digest=checkpoint.candidate_digest,
        validation_digest=checkpoint.validation_digest,
        promoted_revision_id=checkpoint.promoted_revision_id,
        promoted_digest=checkpoint.promoted_digest, config_digest=checkpoint.config_digest,
        attempt_count=checkpoint.attempt_count,
        completed_steps=list(checkpoint.completed_steps),
        pending_steps=list(checkpoint.pending_steps), finding_codes=codes,
        blocking_count=len([item for item in checkpoint.findings
                            if item.severity == "ERROR"]),
        review_codes=sorted({item.code for item in checkpoint.review_findings}),
        error_class=checkpoint.error_class or "", next_retry_at=checkpoint.next_retry_at,
        updated_at=checkpoint.updated_at)


def project_revision_chain(
        session: OutlineBatchSession,
        *, digests: Mapping[str, str] | None = None) -> RevisionChainProjection:
    rows: list[RevisionChainRow] = []
    previous = session.root_planning_revision_id
    contiguous = True
    for task in sorted(session.tasks, key=lambda item: item.sequence):
        if not task.promoted_revision_id:
            continue
        rows.append(RevisionChainRow(
            batch_id=task.batch_id, source_revision_id=task.source_revision_id,
            promoted_revision_id=task.promoted_revision_id,
            promoted_digest=str((digests or {}).get(task.promoted_revision_id, ""))))
        if task.source_revision_id != previous:
            contiguous = False
        previous = task.promoted_revision_id
    return RevisionChainProjection(
        session_id=session.session_id, root_revision_id=session.root_planning_revision_id,
        final_revision_id=session.final_revision_id,
        current_revision_id=session.current_revision_id, contiguous=contiguous, rows=rows)


def project_batch_session(
        session: OutlineBatchSession, *,
        checkpoints: Mapping[str, OutlineBatchCheckpoint] | None = None,
        plan: StoryPlanningIR | None = None) -> BatchSessionProjection:
    checkpoints = dict(checkpoints or {})
    tasks = sorted(session.tasks, key=lambda item: item.sequence)
    completed = [task for task in tasks if task.status in ("promoted", "skipped")]
    running = next((task for task in tasks
                    if task.status in ("running", "compiled", "validated")), None)
    next_batch = next((task for task in tasks
                       if task.status in ("pending", "ready")), None)
    pending_checkpoints = [checkpoints[task.batch_id] for task in tasks
                           if task.batch_id in checkpoints]
    last = pending_checkpoints[-1] if pending_checkpoints else None
    detail_counts: dict[str, int] = {}
    if plan is not None:
        for volume in plan.volumes:
            detail_counts[volume.detail_level] = detail_counts.get(volume.detail_level, 0) + 1
    return BatchSessionProjection(
        session_id=session.session_id, novel_id=session.novel_id, status=session.status,
        scope_complete=session.scope_complete,
        target_detail_level=session.target_detail_level,
        target_scope_kind=session.target_scope.kind,
        promotion_mode=session.promotion_policy.mode,
        root_revision_id=session.root_planning_revision_id,
        current_revision_id=session.current_revision_id,
        current_digest=session.current_digest,
        final_revision_id=session.final_revision_id, config_digest=session.config_digest,
        batches_completed=len(completed), batches_total=len(tasks),
        running_batch_id=running.batch_id if running else "",
        next_batch_id=next_batch.batch_id if next_batch else "",
        running_scope_note=(running or next_batch).scope.note if (running or next_batch) else "",
        blocked_batch_ids=[task.batch_id for task in tasks if task.status == "blocked"],
        human_review_batch_ids=[task.batch_id for task in tasks
                                if task.status == "human_review"],
        retrying_batch_ids=[task.batch_id for task in tasks
                            if task.status == "retryable_failed"],
        failed_batch_ids=[task.batch_id for task in tasks if task.status == "failed"],
        last_validation_status=(last.status if last else ""),
        last_warning_codes=sorted({item.code for item in (last.findings if last else [])
                                   if item.severity == "WARNING"}),
        last_blocking_codes=sorted({item.code for item in (last.findings if last else [])
                                    if item.severity == "ERROR"}),
        resume_required=any(task.status in ("retryable_failed", "failed", "human_review")
                            or task.status == "validated" for task in tasks),
        detail_level_counts=detail_counts,
        tasks=[project_batch_task(task) for task in tasks],
        checkpoints=[project_checkpoint(item) for item in pending_checkpoints])


def project_elaboration_progress(session: OutlineBatchSession, plan: StoryPlanningIR
                                 ) -> ElaborationProgressProjection:
    rows = plan_elaboration_status(plan, target=session.target_detail_level,
                                   revision_id=session.current_revision_id)
    promoted: dict[str, str] = {}
    for task in session.tasks:
        if task.promoted_revision_id and task.scope.note:
            promoted[task.scope.note] = task.promoted_revision_id
    rows = [row.model_copy(update={"last_compiled_revision": promoted.get(row.object_id, "")})
            for row in rows]
    counts: dict[str, int] = {}
    for row in rows:
        counts[row.current_detail_level] = counts.get(row.current_detail_level, 0) + 1
    return ElaborationProgressProjection(
        rows=rows, detail_level_counts=counts,
        remaining_object_ids=[row.object_id for row in rows if not row.ready],
        blocked_object_ids=sorted({task.batch_id for task in session.tasks
                                   if task.status in ("blocked", "human_review")}),
        source_revision_id=session.current_revision_id)


def project_batch_diff(diff: OutlineBatchDiff) -> BatchDiffProjection:
    return BatchDiffProjection(**diff.model_dump(mode="json"))


def project_planning_completeness(plan: StoryPlanningIR, *, target: str = "arc",
                                  revision_id: str = "") -> PlanningCompletenessProjection:
    volume_levels: dict[str, int] = {}
    for volume in plan.volumes:
        volume_levels[volume.detail_level] = volume_levels.get(volume.detail_level, 0) + 1
    arc_levels: dict[str, int] = {}
    for arc in plan.arcs:
        arc_levels[arc.detail_level] = arc_levels.get(arc.detail_level, 0) + 1
    target_rank = DETAIL_ORDER.get(target, 3)

    def reached(level: str) -> int:
        return int(DETAIL_ORDER.get(level, 0) >= target_rank)

    remaining = [volume.volume_id for volume in plan.volumes
                 if DETAIL_ORDER.get(volume.detail_level, 0) < target_rank]
    return PlanningCompletenessProjection(
        revision_id=revision_id, content_digest=_digest(plan),
        volumes_total=len(plan.volumes), volumes_by_level=volume_levels,
        arcs_total=len(plan.arcs), arcs_by_level=arc_levels,
        spine_coverage=int(DETAIL_ORDER.get(target, 3) >= DETAIL_ORDER["spine"]),
        volume_coverage=sum(reached(volume.detail_level) for volume in plan.volumes),
        arc_coverage=sum(1 for volume in plan.volumes
                         if DETAIL_ORDER.get(volume.detail_level, 0)
                         >= DETAIL_ORDER["arc"]),
        chapter_ready_coverage=sum(1 for arc in plan.arcs
                                   if arc.detail_level == "chapter_ready"),
        remaining_elaboration_scopes=remaining)


def _digest(plan: StoryPlanningIR) -> str:
    from .versioning import planning_digest
    return planning_digest(plan)


def batch_session_snapshot(session: OutlineBatchSession, *, plan: StoryPlanningIR | None = None,
                           checkpoints: Mapping[str, OutlineBatchCheckpoint] | None = None
                           ) -> dict[str, Any]:
    """一个扁平的 JSON-ready 视图（UI 轮询 / 日志友好）。"""

    projection = project_batch_session(session, checkpoints=checkpoints, plan=plan)
    return projection.model_dump(mode="json")


__all__ = [
    "BatchDiffProjection",
    "BatchSessionProjection",
    "BatchTaskProjection",
    "CheckpointProjection",
    "ElaborationProgressProjection",
    "PlanningCompletenessProjection",
    "RevisionChainProjection",
    "RevisionChainRow",
    "batch_session_snapshot",
    "project_batch_diff",
    "project_batch_session",
    "project_batch_task",
    "project_checkpoint",
    "project_elaboration_progress",
    "project_planning_completeness",
    "project_revision_chain",
]
