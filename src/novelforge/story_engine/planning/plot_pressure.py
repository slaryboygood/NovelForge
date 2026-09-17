"""M6：Plot Pressure / Opportunity Inventory（派生分析，不是 Planning truth）。

把 M4（graph）与 M5（long-form analysis）已经能回答的问题整理成统一压力清单，
供 PlotNode synthesis 使用：每个压力都带 source_ref / affected_refs / urgency /
available_after / evidence，并明确 open / blocked / scheduled / resolved 状态。
"""

from __future__ import annotations

from typing import Any

from pydantic import Field

from novelforge.models import StrictModel

from .findings import AnalysisReport
from .graphs import declared_access, entry_locations, reachable_locations
from .models import PlotPressure, StoryPlanningIR
from .ordering import node_sequence_order, order_of, timeline_entries
from .requirements import evaluate_requirements
from .resource_planning import build_resource_ledger
from .versioning import planning_digest


class PlotPressureInventory(StrictModel):
    novel_id: str = Field(default="", max_length=96)
    planning_id: str = Field(default="", max_length=64)
    revision_id: str = Field(default="", max_length=64)
    content_digest: str = Field(default="", max_length=64)
    pressures: list[PlotPressure] = Field(default_factory=list)
    read_only: bool = True

    def open(self) -> list[PlotPressure]:
        return [item for item in self.pressures if item.state == "open"]

    def blocked(self) -> list[PlotPressure]:
        return [item for item in self.pressures if item.state == "blocked"]

    def scheduled(self) -> list[PlotPressure]:
        return [item for item in self.pressures if item.state == "scheduled"]

    def resolved(self) -> list[PlotPressure]:
        return [item for item in self.pressures if item.state == "resolved"]

    def by_kind(self) -> dict[str, int]:
        rows: dict[str, int] = {}
        for item in self.pressures:
            rows[item.kind] = rows.get(item.kind, 0) + 1
        return dict(sorted(rows.items()))

    def by_id(self, pressure_id: str) -> PlotPressure | None:
        return next((item for item in self.pressures if item.pressure_id == pressure_id), None)


def build_plot_pressure_inventory(plan: StoryPlanningIR, *, revision_id: str = "",
                                  analysis: dict[str, AnalysisReport] | None = None,
                                  available_requirements: tuple[str, ...] = ()
                                  ) -> PlotPressureInventory:
    """整合 M4 / M5 的结构化信号，产出统一压力清单（只读）。"""

    findings = analysis or {}
    node_ids = {item.node_id for item in plan.plot_nodes}
    nodes_by_id = {item.node_id: item for item in plan.plot_nodes}
    referenced: dict[str, set[str]] = {}
    for node in plan.plot_nodes:
        for ref in (node.character_arc_refs + node.relationship_arc_refs
                    + node.faction_arc_refs + node.information_move_refs
                    + node.foreshadow_move_refs + node.progression_milestone_refs
                    + node.resource_flow_refs + node.equipment_refs
                    + node.base_progression_refs + node.map_expansion_refs
                    + node.reward_refs + node.autonomous_action_refs
                    + node.faction_relation_refs + node.stage_trigger_refs):
            referenced.setdefault(ref, set()).add(node.node_id)
    orders = node_sequence_order(plan)
    pressures: list[PlotPressure] = []
    counter = {"value": 0}

    def add(kind: str, state: str, source_ref: str, affected: list[str], urgency: str,
            *, available_after: str = "", suggested: tuple[str, ...] = (),
            **evidence: Any) -> None:
        counter["value"] += 1
        pressures.append(PlotPressure(
            pressure_id=f"PRESS_{counter['value']:04d}", kind=kind,  # type: ignore[arg-type]
            state=state,  # type: ignore[arg-type]
            source_ref=source_ref, affected_refs=sorted({item for item in affected if item}),
            urgency=urgency, available_after=available_after,
            suggested_resolution_types=list(suggested),
            evidence={key: value for key, value in evidence.items() if value is not None}))

    # ---- character arc pressure
    for arc in plan.character_arcs:
        anchors = referenced.get(arc.arc_id, set())
        choices_without_node = [choice for choice in arc.major_choices
                                if not choice.node_id or choice.node_id not in node_ids]
        if not anchors:
            add("character_arc_pressure", "open", arc.arc_id, [arc.character_id], "high",
                suggested=("new_node", "arc_turn"))
        elif choices_without_node:
            add("character_arc_pressure", "open", arc.arc_id,
                [arc.character_id] + [choice.node_id for choice in choices_without_node],
                "medium", suggested=("anchor_choice",))
        else:
            add("character_arc_pressure", "scheduled", arc.arc_id, [arc.character_id],
                "low")
    # ---- relationship / faction arc anchors
    for arc in plan.relationship_arcs:
        unanchored = [stage.stage_id or stage.label for stage in arc.stages
                      if not stage.trigger_node_id]
        if unanchored:
            add("relationship_pressure", "open", arc.arc_id, list(arc.participants), "medium",
                suggested=("bind_stage_to_node",), unanchored_stages=unanchored)
        elif arc.irreversible_node in node_ids:
            add("relationship_pressure", "scheduled", arc.arc_id, list(arc.participants), "low")
    for arc in plan.faction_arcs:
        unanchored = [stage.stage_id for stage in arc.stages if not stage.trigger_node_id]
        if unanchored:
            add("faction_pressure", "open", arc.arc_id, [arc.faction_id], "medium",
                suggested=("bind_stage_to_node",), unanchored_stages=unanchored)
    # ---- faction pressure（M4 查询：谁还没被剧情消费）
    for faction in plan.factions:
        if referenced.get(faction.faction_id):
            continue
        if faction.territory or faction.allies or faction.enemies or faction.hidden_goal:
            add("faction_pressure", "open", faction.faction_id, [faction.faction_id],
                "high" if faction.hidden_goal else "medium",
                suggested=("new_node", "faction_move"))
    # ---- resource deficit
    ledger = build_resource_ledger(plan, revision_id=revision_id)
    for row in ledger.rows:
        if row.impossible_consumption:
            state = "blocked" if not referenced.get(row.resource_id) else "open"
            add("resource_deficit", state, row.resource_id, sorted(referenced.get(
                row.resource_id, set())) or [row.resource_id], "high",
                suggested=("acquire_flow", "reduce_consumption"), deficit=row.deficit)
        elif row.capacity_violation:
            add("resource_deficit", "blocked", row.resource_id, [row.resource_id], "medium",
                suggested=("expand_storage",), stored=row.stored)
    # ---- information due
    for arc in plan.information_arcs:
        for truth in arc.truths:
            moves = [move for move in arc.moves if move.truth_id == truth.truth_id]
            types = {move.move_type for move in moves}
            reveal_orders = [orders.get(move.node_id) for move in moves
                             if move.move_type in ("reveal", "payoff")]
            reveal_orders = [value for value in reveal_orders if value is not None]
            if "reveal" not in types and "payoff" not in types:
                add("information_due", "open", truth.truth_id,
                    sorted({*truth.character_knows, *truth.faction_knows}), "medium",
                    suggested=("reveal_node",))
            elif reveal_orders:
                add("information_due", "scheduled", truth.truth_id, [truth.truth_id], "low",
                    available_after=f"order:{min(reveal_orders)}")
            else:
                add("information_due", "resolved", truth.truth_id, [truth.truth_id], "low")
    # ---- foreshadow due
    for foreshadow in plan.foreshadow_plans:
        moves = {move.move_type for move in foreshadow.moves}
        if "payoff" not in moves:
            add("foreshadow_due", "open", foreshadow.foreshadow_id,
                [move.move_id for move in foreshadow.moves], "medium",
                suggested=("payoff_node",))
        else:
            add("foreshadow_due", "resolved", foreshadow.foreshadow_id,
                [foreshadow.foreshadow_id], "low")
    # ---- progression due
    for track in plan.progression_tracks:
        for milestone in track.milestones:
            if not milestone.node_id or milestone.node_id not in node_ids:
                add("progression_due", "open", milestone.milestone_id, [track.track_id],
                    "high" if milestone.cost else "medium",
                    suggested=("milestone_node",))
            else:
                add("progression_due", "scheduled", milestone.milestone_id,
                    [milestone.node_id], "low",
                    available_after=f"order:{orders.get(milestone.node_id)}")
    # ---- map unlock / location reachability
    declared, availability = declared_access(plan)
    reachable: set[str] = set()
    for entry in entry_locations(plan):
        reachable.update(reachable_locations(
            plan, entry, available_requirements=declared | set(available_requirements),
            available_availability=availability).reachable)
    for expansion in plan.map_expansions:
        for milestone in expansion.milestones:
            if milestone.location_ref not in reachable:
                evaluation = evaluate_requirements(milestone.requirements,
                                                   available=available_requirements)
                add("map_unlock", "blocked" if evaluation.satisfied else "open",
                    milestone.milestone_id, [milestone.location_ref], "medium",
                    suggested=("unlock_node",), missing=evaluation.missing())
    # ---- equipment need
    for equipment in plan.equipment_plans:
        if referenced.get(equipment.equipment_id) or referenced.get(equipment.equipment_ref):
            continue
        add("equipment_need", "open", equipment.equipment_id, [equipment.equipment_id],
            "medium", suggested=("equipment_node",))
    # ---- base need
    for base in plan.base_progressions:
        unanchored = [stage.stage_id for stage in base.stages
                      if not stage.unlock_node or stage.unlock_node not in node_ids]
        if unanchored:
            add("base_need", "open", base.base_id, [base.base_id], "medium",
                suggested=("base_upgrade_node",), unanchored_stages=unanchored)
    # ---- autonomous action / faction relation
    for action in plan.autonomous_actions:
        if referenced.get(action.action_id):
            continue
        add("autonomous_action", "open", action.action_id,
            [action.actor_ref] + list(action.target_refs), "medium",
            suggested=("node_reaction",), goal=action.goal)
    for relation in plan.faction_relations:
        if referenced.get(relation.relation_id):
            continue
        add("faction_pressure", "open", relation.relation_id,
            [relation.from_faction_id, relation.to_faction_id], "medium",
            suggested=("relation_turn",), relation_type=relation.relation_type)
    # ---- reward drought / climax linkage
    climax_nodes = {volume.climax_node_id for volume in plan.volumes if volume.climax_node_id}
    for node_id in sorted(climax_nodes):
        node = nodes_by_id.get(node_id)
        if node is None or node.reward_refs:
            continue
        add("reward_drought", "open", node_id, [node_id], "high",
            suggested=("reward_ref", "payoff_node"))
    # ---- requirement closure
    for group in plan.requirement_groups():
        for ref in group.requirements:
            if ref.satisfied_by:
                continue
            add("requirement_unlock", "open", ref.requirement_id,
                [ref.ref_id] if ref.ref_id else [], "medium",
                suggested=("satisfier_node",))
    # ---- theme pressure
    if plan.theme is not None and plan.theme.final_answer_direction:
        themed = [node.node_id for node in plan.plot_nodes if node.theme_refs]
        add("theme_pressure", "scheduled" if themed else "open",
            plan.theme.theme_id, themed or [plan.theme.theme_id], "medium",
            suggested=("theme_linked_node",))
    # ---- prior node consequence（payoff 已声明但没有下游消费）
    for node in plan.plot_nodes:
        if not (node.payoff or node.state_change):
            continue
        if any(edge.from_node_id == node.node_id
               for edge in (plan.spine.edges if plan.spine else [])):
            continue
        add("prior_node_consequence", "deferred", node.node_id, [node.node_id], "low",
            suggested=("downstream_node",))
    # ---- findings 汇总（M5 / M4 已报的问题在这里形成压力）
    for domain, report in sorted(findings.items()):
        for finding in report.findings:
            if finding.severity != "ERROR":
                continue
            add("custom", "blocked", finding.source_id or domain,
                list(finding.related_ids), "high",
                suggested=("fix_finding",), code=finding.code, domain=domain)
    return PlotPressureInventory(
        novel_id=plan.novel_id, planning_id=plan.planning_id, revision_id=revision_id,
        content_digest=planning_digest(plan), pressures=pressures)


def pressure_signature(pressure: PlotPressure) -> str:
    """稳定签名（供测试 / 缓存使用，不参与 truth）。"""

    return f"{pressure.kind}:{pressure.source_ref}:{pressure.state}"


__all__ = [
    "PlotPressureInventory",
    "build_plot_pressure_inventory",
    "order_of",
    "pressure_signature",
    "timeline_entries",
]
