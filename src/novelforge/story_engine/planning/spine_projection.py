"""M6：StorySpine / PlotNode / Conflict / Pressure 只读 projection（供 M13 / M14 / M7）。

全部 read_only + non_authoritative，带 revision_id / content_digest / source_planning_ids；
投影不保存 truth，M14 的 Story DAG 可以直接消费。
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import Field

from novelforge.models import StrictModel

from .findings import AnalysisReport, PlanningFinding
from .models import StoryPlanningIR
from .plot_pressure import PlotPressureInventory, build_plot_pressure_inventory
from .spine_analysis import (
    StorySpineCoverageReport,
    build_coverage_report,
    root_nodes,
    terminal_nodes,
    topological_order,
)
from .versioning import planning_digest


class PlotNodeProjection(StrictModel):
    id: str = Field(min_length=3, max_length=64)
    purpose: str = Field(default="", max_length=300)
    importance: str = Field(default="major", max_length=16)
    detail_level: str = Field(default="spine", max_length=32)
    participants: list[str] = Field(default_factory=list)
    location_id: str = Field(default="", max_length=64)
    must_happen: bool = False
    optional: bool = False
    pressure_kinds: list[str] = Field(default_factory=list)
    refs: list[str] = Field(default_factory=list)
    source_planning_ids: list[str] = Field(default_factory=list)


class SpineEdgeProjection(StrictModel):
    source_id: str = Field(min_length=3, max_length=64)
    target_id: str = Field(min_length=3, max_length=64)
    relation: str = Field(default="requires", max_length=16)
    non_authoritative: Literal[True] = True


class ConflictChainProjection(StrictModel):
    conflict_id: str = Field(min_length=9, max_length=64)
    title: str = Field(default="", max_length=160)
    stages: list[dict[str, Any]] = Field(default_factory=list)


class PressureCoverageProjection(StrictModel):
    open_pressures: list[dict[str, Any]] = Field(default_factory=list)
    blocked_pressures: list[dict[str, Any]] = Field(default_factory=list)
    scheduled_pressures: list[dict[str, Any]] = Field(default_factory=list)
    resolved_pressures: list[dict[str, Any]] = Field(default_factory=list)
    unaddressed: list[str] = Field(default_factory=list)


class StorySpineProjection(StrictModel):
    revision_id: str = Field(default="", max_length=64)
    content_digest: str = Field(default="", max_length=64)
    plan_node_count: int = 0
    nodes: list[PlotNodeProjection] = Field(default_factory=list)
    edges: list[SpineEdgeProjection] = Field(default_factory=list)
    roots: list[str] = Field(default_factory=list)
    terminals: list[str] = Field(default_factory=list)
    topological_order: list[str] = Field(default_factory=list)
    conflicts: list[ConflictChainProjection] = Field(default_factory=list)
    pressure_coverage: PressureCoverageProjection = Field(
        default_factory=PressureCoverageProjection)
    coverage: StorySpineCoverageReport | None = None
    findings: list[PlanningFinding] = Field(default_factory=list)
    read_only: Literal[True] = True
    non_authoritative: Literal[True] = True


def project_story_spine(plan: StoryPlanningIR, *, revision_id: str = "",
                        inventory: PlotPressureInventory | None = None,
                        report: AnalysisReport | None = None,
                        coverage: StorySpineCoverageReport | None = None
                        ) -> StorySpineProjection:
    inventory = inventory or build_plot_pressure_inventory(plan, revision_id=revision_id)
    coverage = coverage or build_coverage_report(plan, revision_id=revision_id,
                                                inventory=inventory)
    nodes = []
    for node in plan.plot_nodes:
        refs = (node.character_arc_refs + node.relationship_arc_refs + node.faction_arc_refs
                + node.information_move_refs + node.foreshadow_move_refs
                + node.progression_milestone_refs + node.resource_flow_refs
                + node.equipment_refs + node.base_progression_refs + node.map_expansion_refs
                + node.reward_refs + node.autonomous_action_refs + node.faction_relation_refs)
        nodes.append(PlotNodeProjection(
            id=node.node_id, purpose=node.purpose, importance=node.importance,
            detail_level=node.detail_level, participants=list(node.participants),
            location_id=node.location_id, must_happen=node.must_happen,
            optional=node.optional, pressure_kinds=list(node.pressure_kinds),
            refs=sorted(set(refs)), source_planning_ids=[node.node_id]))
    edges = [SpineEdgeProjection(source_id=edge.from_node_id, target_id=edge.to_node_id,
                                 relation=edge.relation)
             for edge in (plan.spine.edges if plan.spine else [])]
    conflicts = [ConflictChainProjection(
        conflict_id=chain.conflict_id, title=chain.title,
        stages=[{"stage_id": stage.stage_id, "scope": stage.scope,
                 "trigger_node_id": stage.trigger_node_id,
                 "signals": stage.escalation_signals()} for stage in chain.stages])
        for chain in plan.conflict_chains]
    pressure_coverage = PressureCoverageProjection(
        open_pressures=[item.model_dump(mode="json") for item in inventory.open()],
        blocked_pressures=[item.model_dump(mode="json") for item in inventory.blocked()],
        scheduled_pressures=[item.model_dump(mode="json") for item in inventory.scheduled()],
        resolved_pressures=[item.model_dump(mode="json") for item in inventory.resolved()],
        unaddressed=coverage.unaddressed_pressures)
    return StorySpineProjection(
        revision_id=revision_id, content_digest=planning_digest(plan),
        plan_node_count=len(plan.plot_nodes), nodes=nodes, edges=edges,
        roots=root_nodes(plan), terminals=terminal_nodes(plan),
        topological_order=topological_order(plan), conflicts=conflicts,
        pressure_coverage=pressure_coverage, coverage=coverage,
        findings=list(report.findings) if report is not None else [])


__all__ = [
    "ConflictChainProjection",
    "PlotNodeProjection",
    "PressureCoverageProjection",
    "SpineEdgeProjection",
    "StorySpineProjection",
    "project_story_spine",
]
