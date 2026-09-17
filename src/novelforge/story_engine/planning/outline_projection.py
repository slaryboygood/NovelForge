"""M8A：Outline 只读 projection（供 M13 UI / M16 Export / M8B 批量推进使用）。"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import Field

from novelforge.models import StrictModel

from .outline_budget import ChapterBudgetEstimate
from .outline_compiler import (
    NodeAllocation,
    OutlineCompilationCandidate,
    OutlineCoverageReport,
    PressureCarryover,
)


class VolumePlanProjection(StrictModel):
    volume_id: str = Field(default="", max_length=64)
    index: int = 0
    title: str = Field(default="", max_length=120)
    detail_level: str = Field(default="volume", max_length=32)
    arc_ids: list[str] = Field(default_factory=list)
    major_nodes: list[str] = Field(default_factory=list)
    climax_node_id: str = Field(default="", max_length=64)
    chapter_budget: int = 0
    boundary_reason: str = Field(default="", max_length=300)
    non_authoritative: bool = True


class ArcPlanProjection(StrictModel):
    arc_id: str = Field(default="", max_length=64)
    volume_id: str = Field(default="", max_length=64)
    index: int = 0
    title: str = Field(default="", max_length=120)
    plot_nodes: list[str] = Field(default_factory=list)
    decision_count: int = 0
    chapter_budget: int = 0
    note: str = Field(default="", max_length=200)
    non_authoritative: bool = True


class NodeAllocationProjection(StrictModel):
    node_id: str = Field(default="", max_length=64)
    execution_volume_id: str = Field(default="", max_length=64)
    primary_arc_id: str = Field(default="", max_length=64)
    role: str = Field(default="execution", max_length=32)
    complexity_band: str = Field(default="small", max_length=16)
    structural_weight: float = 0.0
    chapter_range: list[int] = Field(default_factory=list)
    non_authoritative: bool = True


class BudgetProjection(StrictModel):
    plan_budget: ChapterBudgetEstimate = Field(default_factory=ChapterBudgetEstimate)
    segments: list[dict[str, Any]] = Field(default_factory=list)
    chapter_independent: bool = True
    non_authoritative: bool = True


class PressureCarryoverProjection(StrictModel):
    rows: list[PressureCarryover] = Field(default_factory=list)
    ignored_pressure_ids: list[str] = Field(default_factory=list)
    non_authoritative: bool = True


class OutlineStructureProjection(StrictModel):
    candidate_id: str = Field(default="", max_length=64)
    source_revision: str = Field(default="", max_length=64)
    source_digest: str = Field(default="", max_length=64)
    scope: str = Field(default="full_book", max_length=32)
    status: str = Field(default="valid", max_length=24)
    volumes: list[VolumePlanProjection] = Field(default_factory=list)
    arcs: list[ArcPlanProjection] = Field(default_factory=list)
    allocations: list[NodeAllocationProjection] = Field(default_factory=list)
    budget: BudgetProjection = Field(default_factory=BudgetProjection)
    carryover: PressureCarryoverProjection = Field(
        default_factory=PressureCarryoverProjection)
    coverage: OutlineCoverageReport = Field(default_factory=OutlineCoverageReport)
    findings: list[str] = Field(default_factory=list)
    route_provenance: dict[str, Any] = Field(default_factory=dict)
    read_only: Literal[True] = True
    non_authoritative: Literal[True] = True


def project_outline(candidate: OutlineCompilationCandidate
                    ) -> OutlineStructureProjection:
    """把编译候选折成只读结构投影（UI / export 直接消费）。"""

    allocations = []
    for row in candidate.node_allocations:
        estimation = row.budget_estimate
        allocations.append(NodeAllocationProjection(
            node_id=row.node_id, execution_volume_id=row.execution_volume_id,
            primary_arc_id=row.primary_arc_id, role=row.role,
            complexity_band=(estimation.complexity_band if estimation else "small"),
            structural_weight=(estimation.structural_weight if estimation else 0.0),
            chapter_range=([estimation.estimate.minimum, estimation.estimate.preferred,
                            estimation.estimate.maximum] if estimation else [])))
    return OutlineStructureProjection(
        candidate_id=candidate.candidate_id, source_revision=candidate.source_revision_id,
        source_digest=candidate.source_digest, scope=candidate.scope.kind,
        status=candidate.status,
        volumes=[VolumePlanProjection(
            volume_id=item.volume_id, index=item.index, title=item.title,
            detail_level=item.detail_level, arc_ids=list(item.arc_ids),
            major_nodes=list(item.major_nodes), climax_node_id=item.climax_node_id,
            chapter_budget=item.chapter_budget,
            boundary_reason=candidate.boundary_reasons.get(item.volume_id, ""))
            for item in candidate.volume_plans],
        arcs=[ArcPlanProjection(
            arc_id=item.arc_id, volume_id=item.volume_id, index=item.index,
            title=item.title, plot_nodes=list(item.plot_nodes),
            decision_count=len(item.decision_chain), chapter_budget=item.chapter_budget,
            note=item.note) for item in candidate.arc_plans],
        allocations=allocations,
        budget=BudgetProjection(
            plan_budget=candidate.plan_budget,
            segments=[{"segment_id": item.segment_id, "nodes": len(item.node_ids),
                       "weight": item.budget_weight,
                       "range": [item.estimate.minimum, item.estimate.preferred,
                                 item.estimate.maximum]}
                      for item in candidate.budget_estimates]),
        carryover=PressureCarryoverProjection(
            rows=list(candidate.carryover_pressures),
            ignored_pressure_ids=list(candidate.ignored_pressure_ids)),
        coverage=candidate.coverage,
        findings=[item.code for item in candidate.validation_findings],
        route_provenance=dict(candidate.route_provenance))


def project_allocation(rows: list[NodeAllocation]) -> list[NodeAllocationProjection]:
    return [NodeAllocationProjection(
        node_id=row.node_id, execution_volume_id=row.execution_volume_id,
        primary_arc_id=row.primary_arc_id, role=row.role,
        complexity_band=(row.budget_estimate.complexity_band if row.budget_estimate
                         else "small"),
        structural_weight=(row.budget_estimate.structural_weight if row.budget_estimate
                           else 0.0)) for row in rows]


__all__ = [
    "ArcPlanProjection",
    "BudgetProjection",
    "NodeAllocationProjection",
    "OutlineStructureProjection",
    "PressureCarryoverProjection",
    "VolumePlanProjection",
    "project_allocation",
    "project_outline",
]
