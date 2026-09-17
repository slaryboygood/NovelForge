"""M9：Arc → Chapter batch orchestration（复用 M8B session / checkpoint / resume / retry）。

batch unit = 一个 Arc：compile → validate → safe_auto promote → checkpoint → next；
不另造第二套 checkpoint/resume 基础设施，只把 M8B 的 orchestration 换成
chapter 编译器 + chapter artifact promotion + M9 gates。
"""

from __future__ import annotations

import hashlib
import uuid
from datetime import datetime, timezone
from typing import Any

from .chapter_compiler import (
    M9_HUMAN_REVIEW_CODES,
    ChapterCompilationCandidate,
    ChapterCompiler,
    ChapterCompilationProfile,
    promote_chapter_candidate,
)
from .chapter_ir_store import ChapterIRStore
from .findings import PlanningFinding, add_finding
from .models import StoryPlanningIR
from .outline_batch import (
    CompilerConfig,
    DETAIL_ORDER,
    BatchReviewFinding,
    CompilationScope,
    OutlineBatchCheckpoint,
    OutlineBatchCompiler,
    OutlineBatchError,
    OutlineBatchSession,
    OutlineBatchStore,
    OutlineBatchTask,
    PromotionPolicy,
)
from .repository import PlanningRepository

M9_MAX_DETAIL = "chapter_ready"


class _ChapterCompileAdapter:
    """把 ChapterCompiler 适配成 M8B run_batch 需要的 compiler 接口。"""

    def __init__(self, compiler: ChapterCompiler) -> None:
        self.compiler = compiler

    def compile(self, plan: StoryPlanningIR, *, revision_id: str = "",
                scope: Any | None = None, inventory: Any | None = None,
                route_provenance: dict[str, Any] | None = None
                ) -> ChapterCompilationCandidate:
        arc_id = (getattr(scope, "note", "") if scope is not None else "") or ""
        return self.compiler.compile(plan, revision_id=revision_id, scope=scope,
                                     arc_id=arc_id, route_provenance=route_provenance)


def plan_arc_batch_scopes(session: OutlineBatchSession, plan: StoryPlanningIR
                          ) -> list[OutlineBatchTask]:
    """按 arc 生成待办 batch（只排尚未 chapter_ready 的 Arc，不做 full_book）。"""

    scope = session.target_scope
    scope_nodes = set(scope.node_ids)
    if scope.note:
        scope_nodes.add(scope.note)
    volume_ids = {item.volume_id for item in plan.volumes
                  if not scope_nodes or item.volume_id in scope_nodes}
    pending = []
    for arc in sorted(plan.arcs, key=lambda item: (item.volume_id, item.index)):
        if scope.kind != "full_book" and scope_nodes \
                and arc.volume_id not in volume_ids and arc.arc_id not in scope_nodes:
            continue
        if DETAIL_ORDER.get(arc.detail_level, 0) >= DETAIL_ORDER[M9_MAX_DETAIL]:
            continue
        pending.append(arc)
    tasks: list[OutlineBatchTask] = []
    for sequence, arc in enumerate(pending, start=1):
        tasks.append(OutlineBatchTask(
            batch_id=f"BATCH_{sequence:03d}", sequence=sequence,
            source_revision_id=session.current_revision_id,
            source_digest=session.current_digest,
            scope=CompilationScope(kind="arc_range", node_ids=list(arc.plot_nodes),
                                   note=arc.arc_id),
            source_detail_level=arc.detail_level, target_detail_level="chapter_ready",
            dependency_batch_ids=[f"BATCH_{sequence - 1:03d}"] if sequence > 1 else []))
    return tasks


class ArcChapterBatchCompiler(OutlineBatchCompiler):
    """M9 batch orchestrator：一个 Arc 一批，复用 M8B 的 checkpoint / resume / retry。"""

    def __init__(self, repository: PlanningRepository, *,
                 store: OutlineBatchStore | None = None,
                 compiler: ChapterCompiler | None = None,
                 profile: ChapterCompilationProfile | None = None) -> None:
        super().__init__(repository, store=store)
        self.chapter_compiler = compiler or ChapterCompiler(profile=profile)
        self.chapter_store = ChapterIRStore(repository.project_root, repository.novel_id)

    # ---------------------------------------------------------------- session
    def create_session(self, *, target_detail_level: str = M9_MAX_DETAIL,
                       scope: CompilationScope | None = None,
                       promotion_policy: PromotionPolicy | None = None,
                       config: Any | None = None,
                       root_revision_id: str = "", session_id: str = ""
                       ) -> OutlineBatchSession:
        if target_detail_level != M9_MAX_DETAIL:
            raise OutlineBatchError("M9_TARGET_LEVEL_INVALID",
                                    f"M9 只提升到 {M9_MAX_DETAIL}，收到 {target_detail_level}")
        head = (self.repository.load(root_revision_id) if root_revision_id
                else self.repository.resolve_branch_head())
        if head is None:
            raise OutlineBatchError("BATCH_SESSION_NO_HEAD", "repository 没有 revision")
        if not head.plan.arcs:
            raise OutlineBatchError("M9_NO_ARC", "plan 还没有 Arc，先完成 M8A/M8B")
        policy = promotion_policy or PromotionPolicy(mode="manual")
        config = CompilerConfig(
            compiler_version="m9-1",
            target_words=head.plan.intent.target_words if head.plan.intent else 0)
        session = OutlineBatchSession(
            session_id=session_id or f"CHBATCH_{uuid.uuid4().hex[:10].upper()}",
            novel_id=head.novel_id, root_planning_revision_id=head.revision_id,
            root_digest=head.content_digest, current_revision_id=head.revision_id,
            current_digest=head.content_digest,
            target_scope=scope or CompilationScope(kind="full_book"),
            target_detail_level=M9_MAX_DETAIL,
            batch_policy={"max_attempts": policy.max_attempts,
                          "config": config.model_dump(mode="json"),
                          "compiler_version": "m9-1", "chapter_registry": {}},
            promotion_policy=policy, config_digest=config.digest(),
            status="pending")
        session.tasks = plan_arc_batch_scopes(session, head.plan)
        session.pending_batch_ids = [task.batch_id for task in session.tasks]
        return self.store.save_session(session)

    def extend_plan(self, session_id: str) -> OutlineBatchSession:
        session = self.store.load_session(session_id)
        head = self.repository.load(session.current_revision_id)
        block = plan_arc_batch_scopes(session, head.plan)
        covered = {task.scope.note for task in session.tasks
                   if task.status not in ("superseded", "skipped") and task.scope.note}
        offset = max([task.sequence for task in session.tasks] or [0])
        previous = ""
        renamed: list[OutlineBatchTask] = []
        for task in block:
            if task.scope.note and task.scope.note in covered:
                continue
            batch_id = f"BATCH_{offset + len(renamed) + 1:03d}"
            renamed.append(task.model_copy(update={
                "batch_id": batch_id, "sequence": offset + len(renamed) + 1,
                "source_revision_id": head.revision_id, "source_digest": head.content_digest,
                "dependency_batch_ids": [previous] if previous else []}))
            previous = renamed[-1].batch_id
        if not renamed:
            return session
        tasks = list(session.tasks) + renamed
        return self.store.save_session(session.model_copy(update={
            "tasks": tasks,
            "pending_batch_ids": [task.batch_id for task in tasks
                                  if task.status in ("pending", "ready", "retryable_failed")],
            "updated_at": datetime.now(timezone.utc)}))

    def recompile_arc(self, session_id: str, arc_id: str) -> OutlineBatchSession:
        """显式重编一个 Arc（旧 batch 标 superseded；chapter ids 由 anchor 匹配保持不变）。"""

        session = self.store.load_session(session_id)
        arc = next((item for item in self.repository.load(
            session.current_revision_id).plan.arcs if item.arc_id == arc_id), None)
        if arc is None:
            raise OutlineBatchError("ARC_NOT_FOUND", arc_id)
        tasks = [task.model_copy(update={"status": "superseded"})
                 if task.scope.note == arc_id else task for task in session.tasks]
        self.store.save_session(session.model_copy(update={"tasks": tasks}))
        return self.recompile_scope(
            session_id,
            CompilationScope(kind="arc_range", node_ids=list(arc.plot_nodes), note=arc_id),
            supersedes_batch_ids=[task.batch_id for task in tasks
                                  if task.scope.note == arc_id]
            or [f"ARC_REBUILD:{arc_id}"])

    def recompile_scope(self, session_id: str, scope: CompilationScope, *,
                        supersedes_batch_ids: list[str] | None = None
                        ) -> OutlineBatchSession:
        session = super().recompile_scope(session_id, scope)
        if not supersedes_batch_ids:
            return session
        tasks = [task.model_copy(update={"supersedes_batch_ids": list(supersedes_batch_ids)})
                 if task.scope.note == scope.note
                 and task.status in ("pending", "ready") else task
                 for task in session.tasks]
        return self.store.save_session(session.model_copy(update={"tasks": tasks}))

    # ---------------------------------------------------------------- hooks
    def repair_session(self, session_id: str) -> OutlineBatchSession:
        """崩溃补记：从 revision note 里补回 candidate id（M9 需要它定位 staged artifact）。"""

        session = super().repair_session(session_id)
        changed = False
        for task in session.tasks:
            checkpoint = self.store.load_checkpoint(session_id, task.batch_id)
            if checkpoint is None or checkpoint.status != "promoted" or checkpoint.candidate_id:
                continue
            record = self.repository.load(checkpoint.promoted_revision_id)
            note = record.note or ""
            token = note.split("candidate ", 1)[1].strip().split()[0] \
                if "candidate " in note else ""
            if token:
                self.store.save_checkpoint(checkpoint.model_copy(
                    update={"candidate_id": token}))
                changed = True
        if changed:
            session = self._rebuild_registries(self.store.load_session(session_id))
        return session

    def _compiler_for(self, config: Any) -> Any:      # noqa: D401 - adapter
        return _ChapterCompileAdapter(self.chapter_compiler)

    def _retag_candidate(self, candidate: ChapterCompilationCandidate,
                         session: OutlineBatchSession, task: OutlineBatchTask,
                         plan: StoryPlanningIR) -> ChapterCompilationCandidate:
        """M9 candidate id 已经是确定性派生；这里只补 batch / session provenance。"""

        seed = "|".join([session.session_id, task.batch_id, candidate.source_digest,
                         candidate.arc_id])
        digest = hashlib.sha256(seed.encode("utf-8")).hexdigest()[:10].upper()
        return candidate.model_copy(update={
            "candidate_id": f"CAND_CHBATCH_{digest}",
            "route_provenance": {**dict(candidate.route_provenance),
                                 "session_id": session.session_id,
                                 "batch_id": task.batch_id}})

    def _scope_findings(self, candidate: ChapterCompilationCandidate,
                        task: OutlineBatchTask, **kwargs: Any) -> list[PlanningFinding]:
        return list(candidate.validation_findings)

    def _cross_batch_check(self, session: OutlineBatchSession, plan: StoryPlanningIR,
                           task: OutlineBatchTask, candidate: ChapterCompilationCandidate,
                           config: Any) -> list[PlanningFinding]:
        findings: list[PlanningFinding] = []
        arc = next((item for item in plan.arcs if item.arc_id == candidate.arc_id), None)
        if arc is not None and arc.detail_level == "chapter_ready" \
                and not task.supersedes_batch_ids:
            add_finding(findings, "ARC_ALREADY_CHAPTER_READY", "ERROR", "chapter",
                        candidate.arc_id, "该 Arc 已经是 chapter_ready，重编必须显式 recompile_arc",
                        related=(candidate.arc_id,))
        existing = {chapter_id for row in plan.arcs if row.arc_id != candidate.arc_id
                    for chapter_id in row.chapter_refs}
        for ir in candidate.chapter_irs:
            if ir.chapter_uuid in existing:
                add_finding(findings, "CHAPTER_ID_COLLISION", "ERROR", "chapter",
                            ir.chapter_uuid, "chapter id 与已 promote 的章节冲突",
                            related=(ir.chapter_uuid,))
        if any(item.severity == "ERROR" and item.code in M9_HUMAN_REVIEW_CODES
               for item in candidate.validation_findings):
            review_codes = sorted({item.code for item in candidate.validation_findings
                                   if item.severity == "ERROR"
                                   and item.code in M9_HUMAN_REVIEW_CODES})
            add_finding(findings, "CHAPTER_HUMAN_REVIEW_REQUIRED", "ERROR", "chapter",
                        candidate.arc_id, f"需要作者裁决：{', '.join(review_codes)}",
                        related=(candidate.arc_id,))
        return findings

    def _classify(self, findings: list[PlanningFinding], config: Any
                  ) -> tuple[Any, list[BatchReviewFinding]]:
        errors = [item for item in findings if item.severity == "ERROR"]
        review_codes = sorted({item.code for item in errors
                               if item.code in M9_HUMAN_REVIEW_CODES
                               or item.code == "CHAPTER_HUMAN_REVIEW_REQUIRED"})
        if review_codes:
            return "human_review", [BatchReviewFinding(
                code=code, message=f"M9 需要作者裁决：{code}") for code in review_codes]
        if errors:
            return "blocked", []
        return "validated", []

    def _promote(self, session: OutlineBatchSession, task: OutlineBatchTask,
                 candidate: ChapterCompilationCandidate, findings: list[PlanningFinding],
                 checkpoint: OutlineBatchCheckpoint, *, config: Any,
                 review: list[BatchReviewFinding]
                 ) -> tuple[OutlineBatchTask, OutlineBatchCheckpoint]:
        base = self.repository.load(candidate.source_revision_id)
        record = None
        try:
            _, record = promote_chapter_candidate(
                self.repository, self.chapter_store, candidate, approved=True,
                note=f"M9 {session.session_id} {task.batch_id} arc {candidate.arc_id} "
                     f"candidate {candidate.candidate_id}")
        except ValueError as exc:
            return self._halt(session, task, "failed", "VALIDATION", str(exc)[:200])
        promoted = task.model_copy(update={
            "status": "promoted", "promoted_revision_id": record.revision_id,
            "candidate_id": candidate.candidate_id,
            "completed_at": datetime.now(timezone.utc)})
        checkpoint = self._checkpoint(session, promoted, candidate, findings,
                                      status="promoted", config=config,
                                      attempt=promoted.attempt_count, review=review,
                                      promoted=record)
        checkpoint = checkpoint.model_copy(update={
            "resume_state": {"recovered": False, "promoted_note": record.note,
                             "arc_id": candidate.arc_id,
                             "chapter_ids": [item.chapter_uuid
                                             for item in candidate.chapter_irs]}})
        self.store.save_checkpoint(checkpoint)
        session = self._update_session(session, promoted)
        session = self._apply_registries(session, task, candidate)
        _ = base
        self.store.save_manifest(self.manifest(session.session_id))
        return promoted, checkpoint

    def _apply_registries(self, session: OutlineBatchSession, task: OutlineBatchTask,
                          candidate: ChapterCompilationCandidate) -> OutlineBatchSession:
        registry = dict(session.batch_policy.get("chapter_registry") or {})
        registry[task.batch_id] = {
            "arc_id": candidate.arc_id, "candidate_id": candidate.candidate_id,
            "chapter_ids": [item.chapter_uuid for item in candidate.chapter_irs],
            "chapter_count": len(candidate.chapter_irs)}
        return self.store.save_session(session.model_copy(update={
            "batch_policy": {**session.batch_policy, "chapter_registry": registry},
            "updated_at": datetime.now(timezone.utc)}))

    def _rebuild_registries(self, session: OutlineBatchSession) -> OutlineBatchSession:
        registry: dict[str, Any] = {}
        for task in sorted(session.tasks, key=lambda item: item.sequence):
            checkpoint = self.store.load_checkpoint(session.session_id, task.batch_id)
            if checkpoint is None or checkpoint.status != "promoted":
                continue
            staged = self.chapter_store.load_staged(checkpoint.candidate_id)
            if not staged:
                continue
            registry[task.batch_id] = {
                "arc_id": staged.get("arc_id"),
                "candidate_id": checkpoint.candidate_id,
                "chapter_ids": [item.get("chapter_uuid") for item in
                                staged.get("chapter_irs") or []],
                "chapter_count": len(staged.get("chapter_irs") or [])}
        return self.store.save_session(session.model_copy(update={
            "batch_policy": {**session.batch_policy, "chapter_registry": registry}}))

    # ---------------------------------------------------------------- gate
    def session_gate(self, session_id: str) -> dict[str, Any]:
        session = self.store.load_session(session_id)
        plan = self.repository.load(session.current_revision_id).plan
        checks: dict[str, bool] = {}
        checks["all_batches_promoted"] = bool(session.tasks) and all(
            task.status in ("promoted", "skipped", "superseded") for task in session.tasks)
        checks["no_unresolved_retryable"] = not any(
            task.status == "retryable_failed" for task in session.tasks)
        checks["no_human_review_pending"] = not any(
            task.status == "human_review" for task in session.tasks)
        previous = session.root_planning_revision_id
        chain_ok = True
        chain: list[tuple[str, str]] = []
        for task in sorted(session.tasks, key=lambda item: item.sequence):
            if not task.promoted_revision_id:
                continue
            if not self.repository.exists(task.promoted_revision_id):
                chain_ok = False
                continue
            record = self.repository.load(task.promoted_revision_id)
            if record.parent_revision_id != previous:
                chain_ok = False
            previous = record.revision_id
            chain.append((task.batch_id, record.revision_id))
        checks["revision_chain_valid"] = chain_ok and bool(chain)
        checks["final_revision_matches"] = (
            not session.final_revision_id or previous == session.final_revision_id)
        integrity = self.chapter_store.verify(self.repository, session.current_revision_id)
        checks["chapter_artifacts_bound"] = integrity.ok
        chapter_ids = [chapter_id for row in plan.arcs for chapter_id in row.chapter_refs]
        checks["no_duplicate_chapter_ids"] = len(chapter_ids) == len(set(chapter_ids))
        scope_arcs = [arc for arc in plan.arcs
                      if not session.target_scope.node_ids
                      or arc.volume_id in set(session.target_scope.node_ids)
                      or arc.arc_id in set(session.target_scope.node_ids)
                      or session.target_scope.kind == "full_book"]
        checks["detail_targets_achieved"] = bool(scope_arcs) and all(
            DETAIL_ORDER.get(arc.detail_level, 0) >= DETAIL_ORDER[M9_MAX_DETAIL]
            for arc in scope_arcs)
        covered_refs: set[str] = set()
        for arc in plan.arcs:
            if arc.detail_level != "chapter_ready":
                continue
            document = self.chapter_store.load_arc_in_lineage(
                self.repository, session.current_revision_id, arc.arc_id)
            if document is not None:
                for chapter in document.chapters:
                    covered_refs.update(chapter.source_refs)
        candidates: list[ChapterCompilationCandidate] = []
        for task in session.tasks:
            checkpoint = self.store.load_checkpoint(session.session_id, task.batch_id)
            if checkpoint is None or checkpoint.status != "promoted":
                continue
            staged = self.chapter_store.staged_candidate(checkpoint.candidate_id)
            if staged is not None:
                candidates.append(staged)
        arc_node_ids = {node_id for arc in plan.arcs for node_id in arc.plot_nodes}
        uncovered = sorted(node.node_id for node in plan.plot_nodes
                           if node.must_happen and node.node_id in arc_node_ids
                           and node.node_id not in covered_refs)
        checks["must_happen_covered"] = not uncovered
        revalidation: list[PlanningFinding] = []
        for candidate in candidates:
            revalidation.extend(self.chapter_compiler.validate(plan, candidate))
        checks["knowledge_gates_pass"] = not [item for item in revalidation
                                              if item.severity == "ERROR"
                                              and item.code in (
                                                  "CHARACTER_KNOWLEDGE_LEAK",
                                                  "READER_REVEAL_TOO_EARLY",
                                                  "INFORMATION_REVEAL_MISSING")]
        checks["chapter_semantics_pass"] = not [item for item in revalidation
                                                if item.severity == "ERROR"]
        summary = {"checks": checks,
                   "chapter_total": len(chapter_ids),
                   "arc_total": len(plan.arcs),
                   "arcs_chapter_ready": len([arc for arc in plan.arcs
                                              if arc.detail_level == "chapter_ready"]),
                   "artifact_findings": [item.code for item in integrity.findings],
                   "uncovered_must_happen": uncovered,
                   "revalidation_codes": sorted({item.code for item in revalidation}),
                   "revision_chain": chain}
        return {"session_id": session_id, "ok": all(checks.values()), "checks": checks,
                "summary": summary, "blocking_findings": integrity.findings,
                "deferred_scope_findings": []}


__all__ = [
    "M9_MAX_DETAIL",
    "ArcChapterBatchCompiler",
    "plan_arc_batch_scopes",
]
