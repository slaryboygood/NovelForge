"""M8A：Structural Segment Detection —— 从 StorySpine 因果序推导结构段候选。

卷 / Arc 边界来自结构信号（macro 冲突阶段、关键 payoff、人物 / 关系 / 势力阶段、
地图扩张、重大揭示、成长突破、资源格局变化、主题转折…），**不是每 N 个节点切一段**。
"""

from __future__ import annotations

from typing import Any

from pydantic import Field

from novelforge.models import StrictModel

from .models import StoryPlanningIR
from .ordering import node_sequence_order
from .plot_pressure import PlotPressureInventory, build_plot_pressure_inventory
from .spine_analysis import topological_order

HARD_SIGNALS: tuple[str, ...] = ("macro_conflict_stage", "map_region_locked",
                                 "irreversible_point", "climax_reward", "major_reveal",
                                 "progression_breakthrough")
SOFT_SIGNALS: tuple[str, ...] = ("volume_conflict_stage", "major_payoff", "faction_stage",
                                 "relationship_stage", "information_payoff",
                                 "progression_milestone", "resource_regime_change",
                                 "theme_shift", "temporary_equilibrium")


class SegmentCandidate(StrictModel):
    segment_id: str = Field(default="", max_length=64)
    node_ids: list[str] = Field(default_factory=list)
    entry_pressures: list[str] = Field(default_factory=list)
    exit_pressures: list[str] = Field(default_factory=list)
    dominant_conflict: str = Field(default="", max_length=300)
    character_arc_refs: list[str] = Field(default_factory=list)
    relationship_arc_refs: list[str] = Field(default_factory=list)
    faction_arc_refs: list[str] = Field(default_factory=list)
    information_refs: list[str] = Field(default_factory=list)
    progression_refs: list[str] = Field(default_factory=list)
    location_scope: list[str] = Field(default_factory=list)
    budget_weight: float = 0.0
    boundary_signals: list[str] = Field(default_factory=list)
    boundary_reason: str = Field(default="", max_length=300)
    non_authoritative: bool = True


def node_boundary_signals(plan: StoryPlanningIR) -> dict[str, list[str]]:
    """每个 PlotNode 上的结构化边界信号（供应卷 / Arc 边界使用）。"""

    rows: dict[str, list[str]] = {node.node_id: [] for node in plan.plot_nodes}

    def add(node_id: str, signal: str) -> None:
        if node_id and node_id in rows and signal not in rows[node_id]:
            rows[node_id].append(signal)

    for chain in plan.conflict_chains:
        for stage in chain.stages:
            if stage.scope == "macro":
                add(stage.trigger_node_id, "macro_conflict_stage")
            elif stage.scope == "volume":
                add(stage.trigger_node_id, "volume_conflict_stage")
            elif stage.scope == "arc":
                add(stage.trigger_node_id, "arc_conflict_stage")
    for expansion in plan.map_expansions:
        for milestone in expansion.milestones:
            if milestone.to_stage in ("controlled", "secured"):
                add(milestone.trigger_node_id, "map_region_locked")
            elif milestone.to_stage in ("surveyed", "reachable"):
                add(milestone.trigger_node_id, "map_expansion")
    for arc in plan.relationship_arcs:
        for stage in arc.stages:
            add(stage.trigger_node_id, "relationship_stage")
            if stage.irreversible:
                add(stage.trigger_node_id, "irreversible_point")
    for arc in plan.faction_arcs:
        for stage in arc.stages:
            add(stage.trigger_node_id, "faction_stage")
    for arc in plan.information_arcs:
        for move in arc.moves:
            if move.move_type in ("reveal", "reinterpretation"):
                add(move.node_id, "major_reveal")
            elif move.move_type == "payoff":
                add(move.node_id, "information_payoff")
    for item in plan.foreshadow_plans:
        for move in item.moves:
            if move.move_type == "payoff":
                add(move.node_id, "major_payoff")
    for track in plan.progression_tracks:
        for milestone in track.milestones:
            add(milestone.node_id, "progression_milestone")
    for plan_row in plan.reward_plans:
        for event in plan_row.events:
            if event.magnitude in ("major", "climax"):
                add(event.trigger_node_id, "climax_reward")
            else:
                add(event.trigger_node_id, "reward")
    for node in plan.plot_nodes:
        if node.theme_refs:
            add(node.node_id, "theme_shift")
        if node.importance == "core" and node.payoff:
            add(node.node_id, "major_payoff")
    return rows


def detect_structural_segments(plan: StoryPlanningIR, *,
                               inventory: PlotPressureInventory | None = None,
                               scope_node_ids: list[str] | None = None
                               ) -> list[SegmentCandidate]:
    """按拓扑序扫描，遇到 hard signal 且当前段已有结构质量时切段（数据驱动，无固定段数）。"""

    inventory = inventory or build_plot_pressure_inventory(plan)
    signals_by_node = node_boundary_signals(plan)
    order = topological_order(plan)
    if scope_node_ids:
        wanted = set(scope_node_ids)
        order = [node_id for node_id in order if node_id in wanted]
    if not order:
        return []
    nodes_by_id = {node.node_id: node for node in plan.plot_nodes}
    weights = {node_id: _weight(nodes_by_id[node_id], signals_by_node[node_id])
               for node_id in order}
    weights_sorted = sorted(weights.values())
    median = weights_sorted[len(weights_sorted) // 2] if weights_sorted else 1.0
    threshold = max(1.0, median * 2.0)
    segments: list[list[str]] = [[]]
    accumulated = 0.0
    boundary_reason: dict[int, str] = {}
    for node_id in order:
        node_signals = signals_by_node.get(node_id, [])
        hard = [item for item in node_signals if item in HARD_SIGNALS]
        if segments[-1] and hard and accumulated >= threshold:
            boundary_reason[len(segments)] = ", ".join(sorted(hard))
            segments.append([])
            accumulated = 0.0
        segments[-1].append(node_id)
        accumulated += weights[node_id]
    order_map = node_sequence_order(plan)
    rows: list[SegmentCandidate] = []
    for index, node_ids in enumerate(segments, start=1):
        if not node_ids:
            continue
        node_rows = [nodes_by_id[item] for item in node_ids]
        signals = sorted({signal for item in node_ids
                          for signal in signals_by_node.get(item, [])})
        pressures_in = [item.pressure_id for item in inventory.pressures
                        if item.available_after and _order_value(item.available_after)
                        and node_ids and _order_value(item.available_after)
                        >= (order_map.get(node_ids[0]) or 0)]
        rows.append(SegmentCandidate(
            segment_id=f"SEG_{index:03d}", node_ids=node_ids,
            entry_pressures=pressures_in[:5],
            exit_pressures=[item.pressure_id for item in inventory.open()
                            if item.source_ref in {node.node_id for node in node_rows}][:5],
            dominant_conflict=next((node.conflict for node in node_rows if node.conflict), ""),
            character_arc_refs=sorted({ref for node in node_rows
                                       for ref in node.character_arc_refs}),
            relationship_arc_refs=sorted({ref for node in node_rows
                                          for ref in node.relationship_arc_refs}),
            faction_arc_refs=sorted({ref for node in node_rows
                                     for ref in node.faction_arc_refs}),
            information_refs=sorted({ref for node in node_rows
                                     for ref in node.information_move_refs}),
            progression_refs=sorted({ref for node in node_rows
                                     for ref in node.progression_milestone_refs}),
            location_scope=sorted({node.location_id for node in node_rows if node.location_id}),
            budget_weight=round(sum(weights[item] for item in node_ids), 4),
            boundary_signals=signals,
            boundary_reason=boundary_reason.get(index - 1, "opening segment")))
    return rows


def _weight(node, signals: list[str]) -> float:
    base = {"core": 3.0, "major": 2.0, "minor": 1.0}.get(node.importance, 1.0)
    base += 0.5 * len([item for item in signals if item in HARD_SIGNALS])
    base += 0.25 * len([item for item in signals if item in SOFT_SIGNALS])
    if node.must_happen:
        base += 0.5
    return round(base, 4)


def _order_value(text: str) -> int | None:
    if text.startswith("order:"):
        try:
            return int(text.split(":", 1)[1])
        except ValueError:
            return None
    return None


__all__ = [
    "HARD_SIGNALS",
    "SOFT_SIGNALS",
    "SegmentCandidate",
    "detect_structural_segments",
    "node_boundary_signals",
]
