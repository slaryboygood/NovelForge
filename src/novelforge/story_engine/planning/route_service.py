"""M7：PlanningRouteLabService —— session / candidate / validate / compare / promote。

持久化：候选与 session 存在 `planning_routes/`（与 `revisions/` 明确分离）；
候选是 proposal artifact（带 source_revision / source_digest / non_authoritative），
promote 只通过 repository 产生新的 Planning revision（旧 revision 不可变）。
"""

from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path

from pydantic import Field

from novelforge.models import StrictModel

from .models import SpineEdge, StoryPlanningIR
from .repository import PlanningRepository, PlanningRepositoryError, PlanningRevisionRecord
from .route_candidates import (
    RouteCandidate,
    RouteCandidateConflict,
    RouteCandidatePatch,
    RouteProposalError,
    check_patch_scope,
    materialize_candidate,
    new_candidate_id,
)
from .route_comparison import (
    BaselineComparison,
    PairwiseComparison,
    RouteComparisonProfile,
    RouteComparisonReport,
    compare_candidates,
    compare_pairwise,
    compare_with_baseline,
)
from .spine_analysis import analyze_story_spine
from .versioning import planning_digest

DEFAULT_ROUTE_ROOT = Path("novel/authoring/story_engine/planning")
SESSION_STATUSES = ("open", "decided", "closed")


class RouteComparisonSession(StrictModel):
    session_id: str = Field(min_length=6, max_length=64)
    novel_id: str = Field(default="", max_length=96)
    source_planning_revision_id: str = Field(default="", max_length=64)
    source_digest: str = Field(default="", max_length=64)
    candidate_ids: list[str] = Field(default_factory=list)
    comparison_profile_id: str = Field(default="neutral", max_length=64)
    status: str = Field(default="open", max_length=16)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    non_authoritative: bool = True


class RoutePromotionRecord(StrictModel):
    """promotion provenance（存在候选 artifact 里，不污染 StoryPlanningIR）。"""

    candidate_id: str = Field(default="", max_length=64)
    session_id: str = Field(default="", max_length=64)
    revision_id: str = Field(default="", max_length=64)
    source_revision_id: str = Field(default="", max_length=64)
    selected_tradeoffs: list[str] = Field(default_factory=list)
    author_confirmation_ref: str = Field(default="", max_length=120)
    promoted_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class RouteCandidateStore:
    """候选 / session 的独立持久化（不复用 revisions/ 目录）。"""

    def __init__(self, project_root: Path, novel_id: str, *,
                 root: Path | str = DEFAULT_ROUTE_ROOT) -> None:
        base = (Path(root).resolve() if Path(root).is_absolute()
                else (project_root / Path(root)).resolve())
        self.root = base / novel_id / "planning_routes"
        self.candidates_dir = self.root / "candidates"
        self.sessions_dir = self.root / "sessions"

    def candidate_path(self, candidate_id: str) -> Path:
        return self.candidates_dir / f"{candidate_id}.json"

    def save_candidate(self, candidate: RouteCandidate) -> RouteCandidate:
        self._atomic_write(self.candidate_path(candidate.candidate_id),
                           candidate.model_dump(mode="json"))
        return candidate

    def load_candidate(self, candidate_id: str) -> RouteCandidate:
        path = self.candidate_path(candidate_id)
        if not path.is_file():
            raise RouteProposalError("ROUTE_CANDIDATE_NOT_FOUND", candidate_id)
        return RouteCandidate.model_validate(json.loads(path.read_text(encoding="utf-8")))

    def list_candidates(self) -> list[RouteCandidate]:
        if not self.candidates_dir.is_dir():
            return []
        rows = []
        for path in sorted(self.candidates_dir.glob("*.json")):
            try:
                rows.append(RouteCandidate.model_validate(
                    json.loads(path.read_text(encoding="utf-8"))))
            except Exception:  # noqa: BLE001 - 坏文件不阻塞列表
                continue
        return rows

    def save_session(self, session: RouteComparisonSession) -> RouteComparisonSession:
        self._atomic_write(self.sessions_dir / f"{session.session_id}.json",
                           session.model_dump(mode="json"))
        return session

    def load_session(self, session_id: str) -> RouteComparisonSession:
        path = self.sessions_dir / f"{session_id}.json"
        if not path.is_file():
            raise RouteProposalError("ROUTE_SESSION_NOT_FOUND", session_id)
        return RouteComparisonSession.model_validate(
            json.loads(path.read_text(encoding="utf-8")))

    def save_promotion(self, record: RoutePromotionRecord) -> RoutePromotionRecord:
        self._atomic_write(self.root / "promotions" / f"{record.candidate_id}.json",
                           record.model_dump(mode="json"))
        return record

    @staticmethod
    def _atomic_write(path: Path, payload: dict) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
        body = json.dumps(payload, ensure_ascii=False, indent=1) + "\n"
        try:
            with temporary.open("w", encoding="utf-8", newline="\n") as handle:
                handle.write(body)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, path)
        finally:
            temporary.unlink(missing_ok=True)


class PlanningRouteLabService:
    """UI / M8 只通过本 service 操作 route candidate，不直接碰 repository internals。"""

    def __init__(self, repository: PlanningRepository,
                 store: RouteCandidateStore | None = None) -> None:
        self.repository = repository
        self.store = store or RouteCandidateStore(repository.project_root, repository.novel_id)

    # ---------------------------------------------------------------- session
    def create_session(self, revision_id: str, candidate_ids: list[str], *,
                       profile_id: str = "neutral") -> RouteComparisonSession:
        base = self.repository.load(revision_id)
        session = RouteComparisonSession(
            session_id=f"RSESS_{uuid.uuid4().hex[:10].upper()}", novel_id=base.novel_id,
            source_planning_revision_id=revision_id, source_digest=base.content_digest,
            candidate_ids=list(candidate_ids), comparison_profile_id=profile_id)
        return self.store.save_session(session)

    def add_candidate(self, candidate: RouteCandidate) -> RouteCandidate:
        if not candidate.source_planning_revision_id:
            raise RouteProposalError("ROUTE_CANDIDATE_SOURCE_REQUIRED",
                                     "candidate 必须绑定 source_planning_revision_id")
        validated = self.validate_candidate(candidate)
        return self.store.save_candidate(validated)

    def validate_candidate(self, candidate: RouteCandidate) -> RouteCandidate:
        base = self.repository.load(candidate.source_planning_revision_id)
        if candidate.source_digest and candidate.source_digest != base.content_digest:
            return candidate.model_copy(update={
                "status": "blocked",
                "validation_findings": [*(candidate.validation_findings),
                                        _finding("STALE_ROUTE_CANDIDATE", "ERROR",
                                                 candidate.candidate_id,
                                                 "candidate 的 source_digest 与 revision 不一致")]})
        scope_findings = check_patch_scope(candidate.patch, base.plan)
        if scope_findings:
            return candidate.model_copy(update={"status": "blocked",
                                                "validation_findings": scope_findings})
        plan = materialize_candidate(base.plan, candidate)
        report = analyze_story_spine(plan)
        findings = list(report.findings)
        status = "blocked" if any(item.severity == "ERROR" for item in findings) \
            else "ready"
        return candidate.model_copy(update={"status": status,
                                            "validation_findings": findings,
                                            "source_digest": base.content_digest})

    # ---------------------------------------------------------------- compare
    def compare(self, candidate_ids: list[str], *,
                profile: RouteComparisonProfile | None = None,
                session_id: str = "") -> RouteComparisonReport:
        plans: list[tuple[str, StoryPlanningIR]] = []
        for candidate_id in candidate_ids:
            candidate = self.store.load_candidate(candidate_id)
            base = self.repository.load(candidate.source_planning_revision_id)
            plans.append((candidate_id, materialize_candidate(base.plan, candidate)))
        source = self.repository.load(self.store.load_candidate(candidate_ids[0])
                                      .source_planning_revision_id)
        return compare_candidates(source.plan, plans, session_id=session_id,
                                  revision_id=source.revision_id, profile=profile)

    def compare_pairwise(self, left_id: str, right_id: str, *,
                         profile: RouteComparisonProfile | None = None
                         ) -> PairwiseComparison:
        left, left_plan = self._materialize(left_id)
        right, right_plan = self._materialize(right_id)
        return compare_pairwise(left, left_id, left_plan, right_id, right_plan, profile=profile)

    def compare_baseline(self, candidate_id: str, *,
                         profile: RouteComparisonProfile | None = None
                         ) -> BaselineComparison:
        base, candidate_plan = self._materialize(candidate_id)
        return compare_with_baseline(base, candidate_plan, candidate_id=candidate_id,
                                     profile=profile)

    def reject(self, candidate_id: str, *, reason: str = "") -> RouteCandidate:
        candidate = self.store.load_candidate(candidate_id)
        rejected = candidate.model_copy(update={"status": "rejected", "summary": reason or
                                                candidate.summary})
        return self.store.save_candidate(rejected)

    # ---------------------------------------------------------------- rebase / compose
    def rebase(self, candidate_id: str, new_revision_id: str
               ) -> tuple[RouteCandidate, list[RouteCandidateConflict]]:
        """最小 rebase：只检测 patch 冲突，不做自动 merge。"""

        candidate = self.store.load_candidate(candidate_id)
        base = self.repository.load(new_revision_id)
        conflicts = self._patch_conflicts(candidate.patch, base.plan)
        rebased = candidate.model_copy(update={
            "source_planning_revision_id": new_revision_id,
            "source_digest": base.content_digest, "status": "draft"})
        if not conflicts:
            rebased = self.validate_candidate(rebased)
        return self.store.save_candidate(rebased), conflicts

    def compose(self, candidate_ids: list[str], *, selections: dict[str, list[str]] | None = None
                ) -> tuple[RouteCandidate, list[RouteCandidateConflict]]:
        """组合候选（例如 A 的 faction path + B 的 relationship path），仍只是 candidate。"""

        selections = selections or {}
        candidates = [self.store.load_candidate(item) for item in candidate_ids]
        if not candidates:
            raise RouteProposalError("ROUTE_COMPOSE_EMPTY", "没有可组合的 candidate")
        source_id = candidates[0].source_planning_revision_id
        base = self.repository.load(source_id)
        patch = RouteCandidatePatch()
        conflicts: list[RouteCandidateConflict] = []
        for candidate in candidates:
            keep = set(selections.get(candidate.candidate_id, []))
            for node in candidate.patch.add_nodes:
                if keep and node.node_id not in keep:
                    continue
                patch.add_nodes.append(node)
            for node in candidate.patch.modify_nodes:
                if keep and node.node_id not in keep:
                    continue
                patch.modify_nodes.append(node)
            patch.add_edges.extend(candidate.patch.add_edges)
            patch.remove_edges.extend(candidate.patch.remove_edges)
            patch.requirement_bindings.update(candidate.patch.requirement_bindings)
        conflicts.extend(self._patch_conflicts(patch, base.plan))
        composite = RouteCandidate(
            candidate_id=new_candidate_id("COMPOSITE"),
            source_planning_revision_id=source_id, source_digest=base.content_digest,
            title="composite route", summary=" + ".join(item.candidate_id for item in candidates),
            scope=candidates[0].scope, patch=patch,
            reasoning_summary="组合多个候选的选择项，需重新完整 validation")
        if not conflicts:
            composite = self.validate_candidate(composite)
        return self.store.save_candidate(composite), conflicts

    # ---------------------------------------------------------------- promote
    def promote(self, candidate_id: str, *, approved: bool = False,
                session_id: str = "", selected_tradeoffs: list[str] | None = None,
                author_confirmation_ref: str = "", revision_id: str = "",
                force_on_source_branch: bool = False) -> PlanningRevisionRecord:
        candidate = self.store.load_candidate(candidate_id)
        if not approved:
            raise RouteProposalError("ROUTE_CANDIDATE_NOT_APPROVED",
                                     "promote 需要作者显式 approve")
        base = self.repository.load(candidate.source_planning_revision_id)
        if candidate.source_digest and candidate.source_digest != base.content_digest:
            raise RouteProposalError("STALE_ROUTE_CANDIDATE",
                                     "candidate 基于旧 digest，请先 rebase")
        head = self.repository.resolve_branch_head(base.branch_id)
        if head is not None and head.revision_id != base.revision_id \
                and not force_on_source_branch:
            raise RouteProposalError(
                "STALE_ROUTE_CANDIDATE",
                "branch head 已前进；请 rebase 或显式 force-on-source-branch")
        validated = self.validate_candidate(candidate)
        if validated.blocking():
            raise RouteProposalError("ROUTE_CANDIDATE_BLOCKED",
                                     "candidate 存在 blocking ERROR，不能 promote")
        plan = materialize_candidate(base.plan, candidate)
        record = self.repository.create(
            plan, branch_id=base.branch_id, status="proposed",
            note=f"route candidate {candidate.candidate_id}",
            parent_revision_id=base.revision_id, source_revision=base.revision_id,
            revision_id=revision_id)
        promoted = candidate.model_copy(update={"status": "promoted", "approved": True})
        self.store.save_candidate(promoted)
        self.store.save_promotion(RoutePromotionRecord(
            candidate_id=candidate.candidate_id, session_id=session_id,
            revision_id=record.revision_id, source_revision_id=base.revision_id,
            selected_tradeoffs=list(selected_tradeoffs or []),
            author_confirmation_ref=author_confirmation_ref))
        return record

    # ---------------------------------------------------------------- helpers
    def _materialize(self, candidate_id: str):
        candidate = self.store.load_candidate(candidate_id)
        base = self.repository.load(candidate.source_planning_revision_id)
        return base.plan, materialize_candidate(base.plan, candidate)

    def _patch_conflicts(self, patch: RouteCandidatePatch, plan: StoryPlanningIR
                         ) -> list[RouteCandidateConflict]:
        conflicts: list[RouteCandidateConflict] = []
        nodes_by_id = {node.node_id: node for node in plan.plot_nodes}
        effective_nodes = set(nodes_by_id) | {node.node_id for node in patch.add_nodes}
        for node in patch.modify_nodes:
            if node.node_id not in nodes_by_id:
                conflicts.append(RouteCandidateConflict(
                    code="REBASE_NODE_MISSING", node_id=node.node_id,
                    message="patch 要修改的节点已不存在"))
        for node_id in patch.remove_node_ids:
            if node_id not in nodes_by_id:
                conflicts.append(RouteCandidateConflict(
                    code="REBASE_NODE_MISSING", node_id=node_id,
                    message="patch 要删除的节点已不存在"))
        existing = {(edge.from_node_id, edge.to_node_id, edge.relation)
                    for edge in (plan.spine.edges if plan.spine else [])}
        for edge in patch.add_edges:
            if edge.from_node_id not in effective_nodes \
                    or edge.to_node_id not in effective_nodes:
                conflicts.append(RouteCandidateConflict(
                    code="REBASE_EDGE_NODE_MISSING",
                    message=f"{edge.from_node_id}->{edge.to_node_id} 端点不存在"))
            elif (edge.from_node_id, edge.to_node_id, edge.relation) in existing:
                conflicts.append(RouteCandidateConflict(
                    code="REBASE_EDGE_EXISTS",
                    message=f"{edge.from_node_id}->{edge.to_node_id} 已存在"))
        for edge in patch.remove_edges:
            if (edge.from_node_id, edge.to_node_id, edge.relation) not in existing:
                conflicts.append(RouteCandidateConflict(
                    code="REBASE_EDGE_MISSING",
                    message=f"{edge.from_node_id}->{edge.to_node_id} 已不存在"))
        return conflicts


def _finding(code: str, severity: str, source_id: str, message: str):
    from .findings import PlanningFinding

    return PlanningFinding(code=code, severity=severity, domain="route",  # type: ignore[arg-type]
                           source_id=source_id, message=message)


__all__ = [
    "DEFAULT_ROUTE_ROOT",
    "PlanningRouteLabService",
    "RouteCandidateStore",
    "RouteComparisonSession",
    "RoutePromotionRecord",
]
