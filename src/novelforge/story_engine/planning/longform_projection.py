"""M5：长线规划只读 projection（给 M13 / M14 与 M6 消费）。

所有 summary 都是 read_only + non_authoritative，并带 revision_id / content_digest；
它们不保存 truth，数据仍在 StoryPlanningIR。
"""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from novelforge.models import StrictModel

from .equipment_planning import equipment_lifecycle_order
from .health import PlanningHealthReport, analyze_planning_health
from .models import StoryPlanningIR
from .ordering import node_sequence_order
from .resource_planning import build_resource_ledger
from .rewards import reward_cadence_rows
from .versioning import planning_digest


class ProgressionSummary(StrictModel):
    track_count: int = 0
    milestone_count: int = 0
    tracks_without_cost: list[str] = Field(default_factory=list)
    categories: list[str] = Field(default_factory=list)


class ResourceSummary(StrictModel):
    resource_count: int = 0
    flow_count: int = 0
    unit_count: int = 0
    planning_only_resources: list[str] = Field(default_factory=list)
    deficits: list[str] = Field(default_factory=list)


class EquipmentSummary(StrictModel):
    equipment_count: int = 0
    consumable_count: int = 0
    unique_count: int = 0
    lifecycle_coverage: float = 0.0


class BaseSummary(StrictModel):
    base_count: int = 0
    stage_count: int = 0
    bases: list[str] = Field(default_factory=list)


class MapExpansionSummary(StrictModel):
    expansion_count: int = 0
    milestone_count: int = 0
    max_stage: str = ""
    locations: list[str] = Field(default_factory=list)


class InformationArcSummary(StrictModel):
    arc_count: int = 0
    truth_count: int = 0
    move_count: int = 0
    truths_without_plant: list[str] = Field(default_factory=list)


class ForeshadowSummary(StrictModel):
    foreshadow_count: int = 0
    move_count: int = 0
    without_payoff: list[str] = Field(default_factory=list)


class RewardCadenceSummary(StrictModel):
    reward_count: int = 0
    by_magnitude: dict[str, int] = Field(default_factory=dict)
    by_type: dict[str, int] = Field(default_factory=dict)
    timeline: list[dict[str, object]] = Field(default_factory=list)


class AutonomousActionSummary(StrictModel):
    action_count: int = 0
    protagonist_dependent_count: int = 0
    actors: list[str] = Field(default_factory=list)


class FactionRelationSummary(StrictModel):
    relation_count: int = 0
    by_type: dict[str, int] = Field(default_factory=dict)
    asymmetric_count: int = 0


class LongformSummaries(StrictModel):
    revision_id: str = Field(default="", max_length=64)
    content_digest: str = Field(default="", max_length=64)
    progression: ProgressionSummary = Field(default_factory=ProgressionSummary)
    resources: ResourceSummary = Field(default_factory=ResourceSummary)
    equipment: EquipmentSummary = Field(default_factory=EquipmentSummary)
    base: BaseSummary = Field(default_factory=BaseSummary)
    map_expansion: MapExpansionSummary = Field(default_factory=MapExpansionSummary)
    information: InformationArcSummary = Field(default_factory=InformationArcSummary)
    foreshadow: ForeshadowSummary = Field(default_factory=ForeshadowSummary)
    reward: RewardCadenceSummary = Field(default_factory=RewardCadenceSummary)
    autonomous: AutonomousActionSummary = Field(default_factory=AutonomousActionSummary)
    faction_relation: FactionRelationSummary = Field(default_factory=FactionRelationSummary)
    health: PlanningHealthReport | None = None
    read_only: Literal[True] = True
    non_authoritative: Literal[True] = True


def summarize_longform(plan: StoryPlanningIR, *, revision_id: str = "",
                       content_digest: str = "", with_health: bool = False
                       ) -> LongformSummaries:
    ledger = build_resource_ledger(plan, revision_id=revision_id)
    progression = ProgressionSummary(
        track_count=len(plan.progression_tracks),
        milestone_count=sum(len(track.milestones) for track in plan.progression_tracks),
        tracks_without_cost=[track.track_id for track in plan.progression_tracks
                             if track.milestones
                             and all(not item.cost and not item.requirement
                                     for item in track.milestones)],
        categories=sorted({track.category for track in plan.progression_tracks}))
    resources = ResourceSummary(
        resource_count=len(plan.resource_plans), flow_count=len(plan.resource_flows),
        unit_count=len(plan.unit_defs),
        planning_only_resources=[item.resource_id for item in ledger.rows
                                 if item.planning_only],
        deficits=[item.resource_id for item in ledger.rows if item.impossible_consumption])
    equipment = EquipmentSummary(
        equipment_count=len(plan.equipment_plans),
        consumable_count=len([item for item in plan.equipment_plans if item.consumable]),
        unique_count=len([item for item in plan.equipment_plans if item.unique]),
        lifecycle_coverage=round(
            len([item for item in plan.equipment_plans
                 if equipment_lifecycle_order(item, plan)]) / len(plan.equipment_plans), 4)
        if plan.equipment_plans else 0.0)
    base = BaseSummary(base_count=len(plan.base_progressions),
                       stage_count=sum(len(item.stages) for item in plan.base_progressions),
                       bases=sorted(item.base_id for item in plan.base_progressions))
    milestones = [item for expansion in plan.map_expansions
                  for item in expansion.milestones]
    map_summary = MapExpansionSummary(
        expansion_count=len(plan.map_expansions), milestone_count=len(milestones),
        max_stage=(max((item.to_stage for item in milestones),
                       key=lambda stage: ["unknown", "known", "reachable", "surveyed",
                                          "controlled", "secured"].index(stage))
                   if milestones else ""),
        locations=sorted({item.location_ref for item in milestones}))
    information = InformationArcSummary(
        arc_count=len(plan.information_arcs),
        truth_count=sum(len(arc.truths) for arc in plan.information_arcs),
        move_count=sum(len(arc.moves) for arc in plan.information_arcs),
        truths_without_plant=[truth.truth_id for arc in plan.information_arcs
                              for truth in arc.truths
                              if not any(move.move_type == "plant"
                                         and move.truth_id == truth.truth_id
                                         for move in arc.moves)])
    foreshadow = ForeshadowSummary(
        foreshadow_count=len(plan.foreshadow_plans),
        move_count=sum(len(item.moves) for item in plan.foreshadow_plans),
        without_payoff=[item.foreshadow_id for item in plan.foreshadow_plans
                        if not any(move.move_type == "payoff" for move in item.moves)])
    rows = reward_cadence_rows(plan)
    reward = RewardCadenceSummary(
        reward_count=len(rows),
        by_magnitude=_counts(row["magnitude"] for row in rows),
        by_type=_counts(row["reward_type"] for row in rows), timeline=rows)
    autonomous = AutonomousActionSummary(
        action_count=len(plan.autonomous_actions),
        protagonist_dependent_count=len([item for item in plan.autonomous_actions
                                         if item.requires_protagonist_presence]),
        actors=sorted({item.actor_ref for item in plan.autonomous_actions}))
    relations = FactionRelationSummary(
        relation_count=len(plan.faction_relations),
        by_type=_counts(item.relation_type for item in plan.faction_relations),
        asymmetric_count=len([item for item in plan.faction_relations if not item.symmetric]))
    health = analyze_planning_health(plan, revision_id=revision_id) if with_health else None
    return LongformSummaries(
        revision_id=revision_id, content_digest=content_digest or planning_digest(plan),
        progression=progression, resources=resources, equipment=equipment, base=base,
        map_expansion=map_summary, information=information, foreshadow=foreshadow,
        reward=reward, autonomous=autonomous, faction_relation=relations, health=health)


def node_orders(plan: StoryPlanningIR) -> dict[str, int]:
    """只读：节点 → timeline sequence_order（UI / M6 常用）。"""

    return node_sequence_order(plan)


def _counts(values) -> dict[str, int]:
    rows: dict[str, int] = {}
    for value in values:
        rows[str(value)] = rows.get(str(value), 0) + 1
    return dict(sorted(rows.items()))


__all__ = [
    "AutonomousActionSummary",
    "BaseSummary",
    "EquipmentSummary",
    "FactionRelationSummary",
    "ForeshadowSummary",
    "InformationArcSummary",
    "LongformSummaries",
    "MapExpansionSummary",
    "ProgressionSummary",
    "ResourceSummary",
    "RewardCadenceSummary",
    "node_orders",
    "summarize_longform",
]
