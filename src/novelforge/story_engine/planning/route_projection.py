"""M7：Route projection —— 只读 DTO（供 M13 / M14 的 A/B 路线卡与对比视图）。"""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from novelforge.models import StrictModel

from .findings import PlanningFinding
from .route_candidates import RouteCandidate, candidate_summary
from .route_comparison import (
    PairwiseComparison,
    RouteCandidateAnalysis,
    RouteComparisonReport,
    RouteDiff,
)


class RouteDiffProjection(StrictModel):
    candidate_id: str = Field(default="", max_length=64)
    source_revision: str = Field(default="", max_length=64)
    nodes_added: list[str] = Field(default_factory=list)
    nodes_removed: list[str] = Field(default_factory=list)
    nodes_modified: list[str] = Field(default_factory=list)
    edges_added: list[str] = Field(default_factory=list)
    edges_removed: list[str] = Field(default_factory=list)
    pressure_delta: dict[str, int] = Field(default_factory=dict)
    coverage_delta: dict[str, int] = Field(default_factory=dict)
    requirement_delta: dict[str, int] = Field(default_factory=dict)
    conflict_delta: dict[str, int] = Field(default_factory=dict)
    resource_delta: dict[str, int] = Field(default_factory=dict)
    information_delta: dict[str, int] = Field(default_factory=dict)
    reward_delta: dict[str, int] = Field(default_factory=dict)
    findings: list[PlanningFinding] = Field(default_factory=list)
    read_only: Literal[True] = True
    non_authoritative: Literal[True] = True


class RouteCandidateProjection(StrictModel):
    candidate_id: str = Field(default="", max_length=64)
    title: str = Field(default="", max_length=120)
    status: str = Field(default="draft", max_length=16)
    scope: str = Field(default="spine_segment", max_length=32)
    source_revision: str = Field(default="", max_length=64)
    blocking: bool = False
    findings: list[PlanningFinding] = Field(default_factory=list)
    diff: RouteDiffProjection | None = None
    dimension_verdicts: dict[str, str] = Field(default_factory=dict)
    strengths: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    tradeoffs: list[str] = Field(default_factory=list)
    read_only: Literal[True] = True
    non_authoritative: Literal[True] = True


class RouteComparisonProjection(StrictModel):
    session_id: str = Field(default="", max_length=64)
    source_revision: str = Field(default="", max_length=64)
    source_digest: str = Field(default="", max_length=64)
    profile_id: str = Field(default="neutral", max_length=64)
    candidates: list[RouteCandidateProjection] = Field(default_factory=list)
    recommended_candidate_id: str = Field(default="", max_length=64)
    recommendation_why: list[str] = Field(default_factory=list)
    tradeoff_summary: list[str] = Field(default_factory=list)
    read_only: Literal[True] = True
    non_authoritative: Literal[True] = True


def project_candidate(candidate: RouteCandidate, *,
                      analysis: RouteCandidateAnalysis | None = None
                      ) -> RouteCandidateProjection:
    diff = None
    if analysis is not None and analysis.diff is not None:
        source: RouteDiff = analysis.diff
        diff = RouteDiffProjection(
            candidate_id=source.candidate_id, source_revision=candidate
            .source_planning_revision_id, nodes_added=source.nodes_added,
            nodes_removed=source.nodes_removed, nodes_modified=source.nodes_modified,
            edges_added=source.edges_added, edges_removed=source.edges_removed,
            pressure_delta=source.pressure_delta, coverage_delta=source.coverage_delta,
            requirement_delta=source.requirement_delta, conflict_delta=source.conflict_delta,
            resource_delta=source.resource_delta, information_delta=source.information_delta,
            reward_delta=source.reward_delta, findings=analysis.blocking_findings)
    summary = candidate_summary(candidate)
    return RouteCandidateProjection(
        candidate_id=candidate.candidate_id, title=candidate.title or summary["title"],
        status=candidate.status, scope=candidate.scope,
        source_revision=candidate.source_planning_revision_id,
        blocking=bool(analysis.blocking_findings) if analysis else candidate.blocking(),
        findings=candidate.validation_findings,
        diff=diff,
        dimension_verdicts=({item.dimension: item.verdict for item in analysis.dimensions}
                            if analysis else {}),
        strengths=list(analysis.strengths) if analysis else [],
        risks=list(analysis.risks) if analysis else [],
        tradeoffs=list(analysis.tradeoffs) if analysis else [])


def project_comparison(report: RouteComparisonReport, *, candidates: dict[str, RouteCandidate]
                       ) -> RouteComparisonProjection:
    rows = []
    for analysis in report.candidates:
        candidate = candidates.get(analysis.candidate_id)
        if candidate is None:
            continue
        rows.append(project_candidate(candidate, analysis=analysis))
    return RouteComparisonProjection(
        session_id=report.session_id, source_revision=report.source_revision,
        source_digest=report.source_digest, profile_id=report.profile_id,
        candidates=rows, recommended_candidate_id=report.recommended_candidate_id,
        recommendation_why=list(report.recommendation_why),
        tradeoff_summary=list(report.tradeoff_summary))


def project_pairwise(pairwise: PairwiseComparison) -> dict[str, object]:
    """A/B 路线卡数据（better_by_dimension 直接可渲染）。"""

    return {"left_id": pairwise.left_id, "right_id": pairwise.right_id,
            "better_by_dimension": pairwise.better_by_dimension,
            "tradeoffs": list(pairwise.tradeoffs),
            "read_only": True, "non_authoritative": True}


__all__ = [
    "RouteCandidateProjection",
    "RouteComparisonProjection",
    "RouteDiffProjection",
    "project_candidate",
    "project_comparison",
    "project_pairwise",
]
