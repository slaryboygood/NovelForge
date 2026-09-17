"""M2B：Planning Projection —— 只读摘要。

给未来 UI / Route Lab / compiler 用：把 Planning IR 折成可展示的摘要，
但**不是 truth source**：projection 不写任何文件，也不改变 plan。
"""

from __future__ import annotations

from typing import Iterable, Literal

from pydantic import Field

from novelforge.models import StrictModel

from .models import StoryPlanningIR
from .graph_projection import PlanningGraphSummary, summarize_graphs
from .versioning import planning_digest


class CharacterArcSummary(StrictModel):
    character_id: str = Field(default="", max_length=64)
    display_name: str = Field(default="", max_length=80)
    entity_ref: str = Field(default="", max_length=160)
    arc_state: str = Field(default="", max_length=300)
    detail_level: str = Field(default="concept", max_length=32)


class RelationshipSummary(StrictModel):
    arc_id: str = Field(default="", max_length=64)
    participants: list[str] = Field(default_factory=list)
    stage_count: int = 0
    irreversible_node: str = Field(default="", max_length=64)
    future_payoff: str = Field(default="", max_length=300)


class LocationGraphSummary(StrictModel):
    location_count: int = 0
    edge_count: int = 0
    hazard_count: int = 0


class SpineSummary(StrictModel):
    node_count: int = 0
    edge_count: int = 0
    entry_count: int = 0
    terminal_count: int = 0
    unscheduled_count: int = 0


class VolumeCoverage(StrictModel):
    volume_id: str = Field(default="", max_length=64)
    title: str = Field(default="", max_length=120)
    detail_level: str = Field(default="volume", max_length=32)
    arc_count: int = 0
    major_node_count: int = 0
    chapter_budget: int = 0
    climax_node_id: str = Field(default="", max_length=64)


class ArcCoverage(StrictModel):
    arc_id: str = Field(default="", max_length=64)
    volume_id: str = Field(default="", max_length=64)
    title: str = Field(default="", max_length=120)
    detail_level: str = Field(default="arc", max_length=32)
    chapter_budget: int = 0
    node_count: int = 0
    decision_count: int = 0


class PlanningSummary(StrictModel):
    planning_id: str = Field(default="", max_length=64)
    planning_revision_id: str = Field(default="", max_length=64)
    content_digest: str = Field(default="", max_length=64)
    novel_id: str = Field(default="", max_length=96)
    title: str = Field(default="", max_length=160)
    logline: str = Field(default="", max_length=400)
    intent_summary: str = Field(default="", max_length=300)
    theme_summary: str = Field(default="", max_length=300)
    world_summary: str = Field(default="", max_length=300)
    character_arcs: list[CharacterArcSummary] = Field(default_factory=list)
    relationships: list[RelationshipSummary] = Field(default_factory=list)
    location_graph: LocationGraphSummary = Field(default_factory=LocationGraphSummary)
    spine: SpineSummary = Field(default_factory=SpineSummary)
    volumes: list[VolumeCoverage] = Field(default_factory=list)
    arcs: list[ArcCoverage] = Field(default_factory=list)
    coverage: dict[str, int] = Field(default_factory=dict)
    completeness: dict[str, float] = Field(default_factory=dict)
    graph: PlanningGraphSummary | None = None
    read_only: Literal[True] = True


def summarize_plan(plan: StoryPlanningIR, *, revision_id: str = "",
                   content_digest: str = "", with_graph: bool = False,
                   available_requirements: Iterable[str] = ()) -> PlanningSummary:
    """只读投影：不写文件、不改 plan，只为展示与路由比较提供摘要。"""

    arcs = {arc.arc_id: arc for arc in plan.arcs}
    character_arcs = [
        CharacterArcSummary(
            character_id=character.character_id, display_name=character.display_name,
            entity_ref=character.entity_ref,
            arc_state=next((item.end_state for item in plan.character_arcs
                            if item.character_id == character.character_id), ""),
            detail_level=character.detail_level)
        for character in plan.characters]
    relationships = [RelationshipSummary(
        arc_id=arc.arc_id, participants=list(arc.participants), stage_count=len(arc.stages),
        irreversible_node=arc.irreversible_node, future_payoff=arc.future_payoff)
        for arc in plan.relationship_arcs]
    graph = plan.location_graph
    location_summary = LocationGraphSummary(
        location_count=len(plan.locations), edge_count=len(graph.edges) if graph else 0,
        hazard_count=sum(len(item.hazards) for item in plan.locations))
    spine = plan.spine
    spine_summary = SpineSummary(
        node_count=len(plan.plot_nodes), edge_count=len(spine.edges) if spine else 0,
        entry_count=len(spine.entry_node_ids) if spine else 0,
        terminal_count=len(spine.terminal_node_ids) if spine else 0,
        unscheduled_count=sum(1 for node in plan.plot_nodes if not node.scheduled_volume_id))
    volumes = [VolumeCoverage(
        volume_id=volume.volume_id, title=volume.title, detail_level=volume.detail_level,
        arc_count=len(volume.arc_ids), major_node_count=len(volume.major_nodes),
        chapter_budget=volume.chapter_budget, climax_node_id=volume.climax_node_id)
        for volume in plan.volumes]
    arc_rows = [ArcCoverage(
        arc_id=arc.arc_id, volume_id=arc.volume_id, title=arc.title,
        detail_level=arc.detail_level, chapter_budget=arc.chapter_budget,
        node_count=len(arc.plot_nodes), decision_count=len(arc.decision_chain))
        for arc in plan.arcs]
    chapter_ready = sum(1 for arc in plan.arcs if arc.detail_level == "chapter_ready")
    coverage = {
        "characters": len(plan.characters), "character_arcs": len(plan.character_arcs),
        "relationship_arcs": len(plan.relationship_arcs), "factions": len(plan.factions),
        "locations": len(plan.locations), "plot_nodes": len(plan.plot_nodes),
        "scheduled_nodes": sum(1 for node in plan.plot_nodes if node.scheduled_volume_id),
        "volumes": len(plan.volumes), "arcs": len(plan.arcs),
        "chapter_ready_arcs": chapter_ready,
        "information_arcs": len(plan.information_arcs),
        "foreshadow_plans": len(plan.foreshadow_plans),
        "progression_tracks": len(plan.progression_tracks),
        "timeline_entries": _timeline_count(plan),
    }
    completeness = {
        "volume_arc_linked": _ratio(sum(1 for volume in plan.volumes if volume.arc_ids),
                                    len(plan.volumes)),
        "arc_budgeted": _ratio(sum(1 for arc in plan.arcs if arc.chapter_budget),
                               len(plan.arcs)),
        "arc_chapter_ready": _ratio(chapter_ready, len(plan.arcs)),
        "node_scheduled": _ratio(coverage["scheduled_nodes"], len(plan.plot_nodes)),
        "spine_causal": _ratio(len(spine.edges) if spine else 0,
                               max(1, len(plan.plot_nodes) - 1)),
    }
    return PlanningSummary(
        planning_id=plan.planning_id, planning_revision_id=revision_id,
        content_digest=content_digest or planning_digest(plan), novel_id=plan.novel_id,
        title=plan.title, logline=plan.logline,
        intent_summary=(plan.intent.commercial_promise if plan.intent else ""),
        theme_summary=(plan.theme.dramatic_question if plan.theme else ""),
        world_summary=(plan.world.history[:300] if plan.world else ""),
        character_arcs=character_arcs, relationships=relationships,
        location_graph=location_summary, spine=spine_summary, volumes=volumes,
        arcs=arc_rows, coverage=coverage, completeness=completeness,
        graph=(summarize_graphs(plan, revision_id=revision_id,
                                content_digest=content_digest,
                                available_requirements=available_requirements)
               if with_graph else None))


def _timeline_count(plan: StoryPlanningIR) -> int:
    timeline = plan.timeline
    if timeline is None:
        return 0
    return (len(timeline.world_history) + len(timeline.story_timeline)
            + sum(len(entries) for entries in timeline.character_timeline.values()))


def _ratio(part: int, total: int) -> float:
    if total <= 0:
        return 1.0
    return round(part / total, 4)


__all__ = [
    "ArcCoverage",
    "CharacterArcSummary",
    "LocationGraphSummary",
    "PlanningSummary",
    "RelationshipSummary",
    "SpineSummary",
    "VolumeCoverage",
    "summarize_plan",
]
