"""M8A：StorySpine → Volume / Arc Compiler（deterministic，proposal-only）。

流程：topological order → structural segmentation → budget estimation →
volume/arc boundary → node allocation → coverage/continuity/causal validation →
pacing 与 budget 输出；结果只是 OutlineCompilationCandidate，必须显式 promote
才写入新的 Planning revision。不生成章节列表（M8B / M9）。
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import Field

from novelforge.models import StrictModel

from .findings import PlanningFinding, add_finding
from .models import ArcPlan, DecisionStep, StoryPlanningIR, VolumePlan, new_planning_id
from .outline_budget import (
    ChapterBudgetEstimate,
    NodeBudgetEstimate,
    SegmentBudgetEstimate,
    StructuralBudgetEstimator,
)
from .outline_segmentation import SegmentCandidate, detect_structural_segments
from .plot_pressure import PlotPressureInventory, build_plot_pressure_inventory
from .repository import PlanningRepository, PlanningRevisionRecord
from .requirements import validate_requirements
from .resource_planning import build_resource_ledger
from .spine_analysis import topological_order
from .versioning import planning_digest

COMPILER_VERSION = "m8a-1"
CompileScopeKind = Literal["full_book", "volume_range", "spine_segment", "around_node",
                           "next_volume", "next_arc", "arc_range"]
CompilationStatus = Literal["valid", "needs_attention", "blocked"]
ARC_FUNCTIONS: tuple[str, ...] = ("setup", "exploration", "investigation", "conflict",
                                  "relationship", "progression", "reveal", "transition",
                                  "climax", "resolution", "mixed")


class CompilationScope(StrictModel):
    kind: CompileScopeKind = "full_book"
    node_ids: list[str] = Field(default_factory=list)
    volume_indexes: list[int] = Field(default_factory=list)
    note: str = Field(default="", max_length=200)


class NodeAllocation(StrictModel):
    node_id: str = Field(default="", max_length=64)
    execution_volume_id: str = Field(default="", max_length=64)
    primary_arc_id: str = Field(default="", max_length=64)
    supporting_arc_ids: list[str] = Field(default_factory=list)
    role: str = Field(default="execution", max_length=32)
    budget_estimate: NodeBudgetEstimate | None = None
    allocation_reason: str = Field(default="", max_length=300)
    route_provenance: dict[str, Any] = Field(default_factory=dict)
    non_authoritative: bool = True


class PressureCarryover(StrictModel):
    pressure_id: str = Field(default="", max_length=64)
    from_volume: str = Field(default="", max_length=64)
    to_volume: str = Field(default="", max_length=64)
    reason: str = Field(default="", max_length=300)
    status: str = Field(default="carried", max_length=32)
    author_intent_ref: str = Field(default="", max_length=120)


class OutlineCoverageReport(StrictModel):
    volumes: int = 0
    arcs: int = 0
    allocated_nodes: int = 0
    must_happen_total: int = 0
    must_happen_allocated: int = 0
    optional_deferred: list[str] = Field(default_factory=list)
    unallocated_must_happen: list[str] = Field(default_factory=list)
    pressure_carryover: int = 0
    ignored_pressures: list[str] = Field(default_factory=list)
    character_arc_distribution: dict[str, int] = Field(default_factory=dict)
    relationship_distribution: dict[str, int] = Field(default_factory=dict)
    faction_distribution: dict[str, int] = Field(default_factory=dict)
    information_distribution: dict[str, int] = Field(default_factory=dict)
    foreshadow_distribution: dict[str, int] = Field(default_factory=dict)
    progression_distribution: dict[str, int] = Field(default_factory=dict)
    reward_distribution: dict[str, int] = Field(default_factory=dict)
    conflict_escalation_distribution: dict[str, int] = Field(default_factory=dict)
    resource_feasibility: str = Field(default="unknown", max_length=32)
    requirement_closure: dict[str, int] = Field(default_factory=dict)
    status: CompilationStatus = "valid"
    read_only: bool = True


class OutlineCompilationCandidate(StrictModel):
    candidate_id: str = Field(default="", max_length=64)
    source_revision_id: str = Field(default="", max_length=64)
    source_digest: str = Field(default="", max_length=64)
    scope: CompilationScope = Field(default_factory=CompilationScope)
    volume_plans: list[VolumePlan] = Field(default_factory=list)
    arc_plans: list[ArcPlan] = Field(default_factory=list)
    node_allocations: list[NodeAllocation] = Field(default_factory=list)
    budget_estimates: list[SegmentBudgetEstimate] = Field(default_factory=list)
    plan_budget: ChapterBudgetEstimate = Field(default_factory=ChapterBudgetEstimate)
    boundary_reasons: dict[str, str] = Field(default_factory=dict)
    carryover_pressures: list[PressureCarryover] = Field(default_factory=list)
    ignored_pressure_ids: list[str] = Field(default_factory=list)
    route_provenance: dict[str, Any] = Field(default_factory=dict)
    coverage: OutlineCoverageReport = Field(default_factory=OutlineCoverageReport)
    validation_findings: list[PlanningFinding] = Field(default_factory=list)
    status: CompilationStatus = "valid"
    non_authoritative: bool = True

    def blocking(self) -> bool:
        return any(item.severity == "ERROR" for item in self.validation_findings)


class OutlineCompilationRecord(StrictModel):
    source_revision: str = Field(default="", max_length=64)
    source_digest: str = Field(default="", max_length=64)
    compiler_version: str = Field(default=COMPILER_VERSION, max_length=32)
    scope: CompilationScope = Field(default_factory=CompilationScope)
    route_promotion_ref: str = Field(default="", max_length=120)
    candidate_id: str = Field(default="", max_length=64)
    promoted_revision_id: str = Field(default="", max_length=64)
    validation_digest: str = Field(default="", max_length=64)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    non_authoritative: bool = True


class OutlineCompiler:
    """同一 revision + scope 必然得到同一 candidate（无随机成分）。"""

    def __init__(self, *, average_chapter_words: int = 3000,
                 estimator: StructuralBudgetEstimator | None = None) -> None:
        self.estimator = estimator or StructuralBudgetEstimator(
            average_chapter_words=average_chapter_words)

    def compile(self, plan: StoryPlanningIR, *, revision_id: str = "",
                scope: CompilationScope | None = None,
                inventory: PlotPressureInventory | None = None,
                route_provenance: dict[str, Any] | None = None
                ) -> OutlineCompilationCandidate:
        scope = scope or CompilationScope()
        inventory = inventory or build_plot_pressure_inventory(plan,
                                                               revision_id=revision_id)
        segments = detect_structural_segments(plan, inventory=inventory,
                                              scope_node_ids=scope.node_ids or None)
        volumes: list[VolumePlan] = []
        arcs: list[ArcPlan] = []
        allocations: list[NodeAllocation] = []
        budgets: list[SegmentBudgetEstimate] = []
        boundary_reasons: dict[str, str] = {}
        order_index = {node_id: index
                       for index, node_id in enumerate(topological_order(plan))}
        nodes_by_id = {node.node_id: node for node in plan.plot_nodes}
        for segment_index, segment in enumerate(segments, start=1):
            budget = self.estimator.estimate_segment(plan, segment.segment_id,
                                                     segment.node_ids, inventory)
            budgets.append(budget)
            volume_id = f"VOL_SEG{segment_index:03d}"
            arc_splits = self._split_arcs(plan, segment, budget)
            arc_ids: list[str] = []
            for arc_index, arc_nodes in enumerate(arc_splits, start=1):
                arc_id = f"ARC_SEG{segment_index:03d}_{arc_index:02d}"
                arc_ids.append(arc_id)
                arc_budget = self.estimator.estimate_segment(plan, arc_id, arc_nodes,
                                                             inventory)
                arcs.append(self._arc(plan, arc_id, volume_id, arc_nodes, arc_budget,
                                      arc_index, segment))
                for node_id in arc_nodes:
                    allocations.append(NodeAllocation(
                        node_id=node_id, execution_volume_id=volume_id,
                        primary_arc_id=arc_id,
                        supporting_arc_ids=[],
                        role=self._role(nodes_by_id[node_id]),
                        budget_estimate=next((row for row in budget.node_estimates
                                              if row.node_id == node_id), None),
                        allocation_reason=segment.boundary_reason or "segment allocation",
                        route_provenance=dict(route_provenance or {})))
            volumes.append(self._volume(plan, volume_id, segment, arc_ids, budget,
                                        segment_index))
            boundary_reasons[volume_id] = segment.boundary_reason or "structural segment"
        carryover = self._carryover(plan, inventory, volumes)
        ignored = [item.pressure_id for item in inventory.pressures
                   if item.state == "ignored"]
        plan_budget = ChapterBudgetEstimate(
            minimum=sum(item.estimate.minimum for item in budgets),
            preferred=sum(item.estimate.preferred for item in budgets),
            maximum=sum(item.estimate.maximum for item in budgets))
        candidate = OutlineCompilationCandidate(
            candidate_id=new_planning_id("candidate", f"OUTLINECOMPILE{len(segments)}"),
            source_revision_id=revision_id, source_digest=planning_digest(plan),
            scope=scope, volume_plans=volumes, arc_plans=arcs,
            node_allocations=allocations, budget_estimates=budgets,
            plan_budget=plan_budget, boundary_reasons=boundary_reasons,
            carryover_pressures=carryover, ignored_pressure_ids=ignored,
            route_provenance=dict(route_provenance or {}))
        findings = self.validate(plan, candidate, inventory=inventory)
        coverage = self._coverage(plan, candidate, inventory, len(segments), len(arcs),
                                  findings)
        status = ("blocked" if any(item.severity == "ERROR" for item in findings)
                  else "needs_attention" if any(item.severity == "WARNING"
                                                for item in findings) else "valid")
        return candidate.model_copy(update={"validation_findings": findings,
                                            "coverage": coverage, "status": status})

    # ---------------------------------------------------------------- validate
    def validate(self, plan: StoryPlanningIR, candidate: OutlineCompilationCandidate, *,
                 inventory: PlotPressureInventory | None = None) -> list[PlanningFinding]:
        findings: list[PlanningFinding] = []
        inventory = inventory or build_plot_pressure_inventory(plan)
        order_index = {node_id: index
                       for index, node_id in enumerate(topological_order(plan))}
        allocation = {item.node_id: item for item in candidate.node_allocations}
        volume_index = {volume.volume_id: index
                        for index, volume in enumerate(candidate.volume_plans, start=1)}
        nodes_by_id = {node.node_id: node for node in plan.plot_nodes}
        if not candidate.volume_plans:
            add_finding(findings, "OUTLINE_NO_VOLUME", "ERROR", "outline",
                        candidate.candidate_id, "编译结果没有任何 VolumePlan")
        if not candidate.arc_plans:
            add_finding(findings, "OUTLINE_NO_ARC", "ERROR", "outline",
                        candidate.candidate_id, "编译结果没有任何 ArcPlan")
        for edge in (plan.spine.edges if plan.spine else []):
            left = allocation.get(edge.from_node_id)
            right = allocation.get(edge.to_node_id)
            if left is None or right is None:
                continue
            if volume_index.get(left.execution_volume_id, 0) \
                    > volume_index.get(right.execution_volume_id, 0):
                add_finding(findings, "ALLOCATION_BREAKS_CAUSAL_ORDER", "ERROR", "outline",
                            edge.to_node_id, "依赖节点被分到更早的 Volume",
                            related=(edge.from_node_id, edge.to_node_id),
                            relation=edge.relation)
        for node in plan.plot_nodes:
            if node.node_id in allocation:
                continue
            if node.must_happen:
                add_finding(findings, "UNALLOCATED_MUST_HAPPEN_NODE", "ERROR", "outline",
                            node.node_id, "must_happen 节点没有被分配")
            elif node.optional:
                add_finding(findings, "UNALLOCATED_OPTIONAL_NODE", "INFO", "outline",
                            node.node_id,
                            "optional 节点未分配（需要显式 deferred / dropped 理由）")
        for node in plan.plot_nodes:
            if node.requirements is None or node.node_id not in allocation:
                continue
            for ref in node.requirements.requirements:
                for satisfier in ref.satisfied_by:
                    left = allocation.get(satisfier)
                    right = allocation.get(node.node_id)
                    if left is None or right is None:
                        continue
                    if volume_index.get(left.execution_volume_id, 0) \
                            > volume_index.get(right.execution_volume_id, 0):
                        add_finding(findings, "REQUIREMENT_SATISFIER_SCHEDULED_TOO_LATE",
                                    "ERROR", "outline", ref.requirement_id,
                                    "满足 requirement 的节点被安排在门之后",
                                    related=(satisfier, node.node_id))
        for arc in plan.information_arcs:
            for move in arc.moves:
                if move.move_type not in ("reveal", "payoff") or not move.node_id:
                    continue
                right = allocation.get(move.node_id)
                if right is None:
                    continue
                for prior in arc.moves:
                    if prior.truth_id != move.truth_id \
                            or prior.move_type not in ("plant", "hint") or not prior.node_id:
                        continue
                    left = allocation.get(prior.node_id)
                    if left is None:
                        continue
                    if volume_index.get(left.execution_volume_id, 0) \
                            > volume_index.get(right.execution_volume_id, 0):
                        add_finding(findings, "OUTLINE_INFORMATION_ORDER_BROKEN", "ERROR",
                                    "outline", move.move_id,
                                    "plant / hint 被安排到 reveal 之后",
                                    related=(prior.move_id, move.move_id))
        for foreshadow in plan.foreshadow_plans:
            for payoff in [item for item in foreshadow.moves if item.move_type == "payoff"]:
                right = allocation.get(payoff.node_id)
                if right is None:
                    continue
                for prior in foreshadow.moves:
                    if prior.move_type not in ("plant", "reinforce", "reveal",
                                               "misdirect") or not prior.node_id:
                        continue
                    left = allocation.get(prior.node_id)
                    if left is None:
                        continue
                    if volume_index.get(left.execution_volume_id, 0) \
                            > volume_index.get(right.execution_volume_id, 0):
                        add_finding(findings, "OUTLINE_FORESHADOW_ORDER_BROKEN", "ERROR",
                                    "outline", foreshadow.foreshadow_id,
                                    "伏笔回收被安排到埋设 / 强化之前",
                                    related=(prior.move_id, payoff.move_id))
        node_ids = {node.node_id for node in plan.plot_nodes}
        for volume in candidate.volume_plans:
            if not volume.climax_node_id or volume.climax_node_id not in node_ids:
                add_finding(findings, "OUTLINE_CLIMAX_NOT_REAL_NODE", "ERROR", "outline",
                            volume.volume_id, "卷高潮不是真实 PlotNode",
                            related=(volume.climax_node_id,))
        for track in plan.progression_tracks:
            volumes_used = {volume_index.get(allocation[item.node_id].execution_volume_id, 0)
                            for item in track.milestones if item.node_id in allocation}
            if len(volumes_used) == 1 and len(track.milestones) >= 3:
                add_finding(findings, "PROGRESSION_CLUSTERED", "WARNING", "outline",
                            track.track_id, "成长里程碑全部集中在同一卷")
        for arc in plan.relationship_arcs:
            for stage in arc.stages:
                if stage.irreversible and stage.trigger_node_id in allocation:
                    row = allocation[stage.trigger_node_id]
                    if volume_index.get(row.execution_volume_id, 1) == 1 \
                            and len(candidate.volume_plans) > 1:
                        add_finding(findings, "RELATIONSHIP_IRREVERSIBLE_TOO_EARLY",
                                    "WARNING", "outline", arc.arc_id,
                                    "关系不可逆点出现在第一卷",
                                    related=(stage.stage_id,))
        for chain in plan.conflict_chains:
            volumes_used = {volume_index.get(allocation[stage.trigger_node_id]
                                             .execution_volume_id, 0)
                            for stage in chain.stages if stage.trigger_node_id in allocation}
            if len(volumes_used) == 1 and len(chain.stages) >= 3:
                add_finding(findings, "CONFLICT_ESCALATION_CLUSTERED", "WARNING",
                            "outline", chain.conflict_id,
                            "整条冲突升级链被压在同一个卷")
        for volume in candidate.volume_plans:
            volume_nodes = {item.node_id for item in candidate.node_allocations
                            if item.execution_volume_id == volume.volume_id}
            stages = [stage for chain in plan.conflict_chains for stage in chain.stages
                      if stage.trigger_node_id in volume_nodes]
            if volume.climax_node_id and not stages:
                add_finding(findings, "CLIMAX_WITHOUT_ESCALATION", "WARNING", "outline",
                            volume.volume_id, "卷高潮之前没有任何冲突升级阶段")
        ledger = build_resource_ledger(plan)
        deficits = {row.resource_id for row in ledger.rows if row.impossible_consumption}
        for volume in candidate.volume_plans:
            volume_nodes = {item.node_id for item in candidate.node_allocations
                            if item.execution_volume_id == volume.volume_id}
            consumed = {flow.identity() for flow in plan.resource_flows
                        if flow.trigger_node_id in volume_nodes}
            if consumed & deficits:
                add_finding(findings, "VOLUME_RESOURCE_DEFICIT", "WARNING", "outline",
                            volume.volume_id, "该卷依赖的资源在全局预算里入不敷出",
                            related=tuple(sorted(consumed & deficits)))
        for equipment in plan.equipment_plans:
            loss_volume = (volume_index.get(allocation[equipment.loss_node]
                                            .execution_volume_id, 0)
                           if equipment.loss_node in allocation else 0)
            for node_id in equipment.nodes():
                row = allocation.get(node_id)
                if row is None or not loss_volume:
                    continue
                if volume_index.get(row.execution_volume_id, 0) > loss_volume:
                    add_finding(findings, "EQUIPMENT_CONTINUITY_BROKEN", "ERROR", "outline",
                                node_id, "装备丢失之后仍被后续卷使用",
                                related=(equipment.equipment_id,))
        ordered = sorted([item for item in candidate.node_allocations
                          if item.node_id in order_index],
                         key=lambda item: order_index[item.node_id])
        for index in range(len(ordered) - 1):
            left = nodes_by_id.get(ordered[index].node_id)
            right = nodes_by_id.get(ordered[index + 1].node_id)
            if left is None or right is None or not left.location_id or not right.location_id:
                continue
            if left.location_id != right.location_id \
                    and ordered[index].execution_volume_id \
                    == ordered[index + 1].execution_volume_id \
                    and not right.map_expansion_refs:
                add_finding(findings, "LOCATION_CONTINUITY_WARNING", "WARNING", "outline",
                            right.node_id, "同卷内跨地点但没有 travel / map setup",
                            related=(left.location_id, right.location_id))
        known_expansion = {item.location_ref for expansion in plan.map_expansions
                           for item in expansion.milestones}
        # 卷可以扩张到 MapExpansionPlan 里声明过的地点，也可以是 plan.locations 已声明的地点；
        # 只有"完全没在任何地方声明过"的地点才算结构不一致（与 M8A 测试的语义一致）。
        known_expansion |= {location.location_id for location in plan.locations}
        for volume in candidate.volume_plans:
            planned = set(volume.location_expansion)
            if planned - known_expansion:
                add_finding(findings, "MAP_EXPANSION_INCONSISTENT", "ERROR", "outline",
                            volume.volume_id, "卷的地图扩张不是来自 MapExpansionPlan",
                            related=tuple(sorted(planned - known_expansion)))
        findings.extend(self.estimator.target_alignment(plan, candidate.plan_budget).findings)
        functions = [self._arc_function(plan, arc) for arc in candidate.arc_plans]
        for index in range(len(functions) - 2):
            window = functions[index:index + 3]
            if len(set(window)) == 1 and window[0] not in ("mixed", ""):
                add_finding(findings, "ARC_FUNCTION_REPETITION", "WARNING", "outline",
                            candidate.arc_plans[index + 2].arc_id,
                            f"连续三个 Arc 功能相同：{window[0]}")
        if candidate.carryover_pressures:
            add_finding(findings, "PRESSURE_CARRYOVER", "INFO", "outline",
                        candidate.candidate_id,
                        "存在跨卷保留的压力（intentionally_deferred / unresolved）",
                        count=len(candidate.carryover_pressures))
        if candidate.ignored_pressure_ids:
            add_finding(findings, "IGNORED_PRESSURE_VISIBLE", "INFO", "outline",
                        candidate.candidate_id,
                        "存在被标记 ignored 的压力（不允许静默消失）",
                        related=tuple(candidate.ignored_pressure_ids))
        return findings

    # ---------------------------------------------------------------- pieces
    def _split_arcs(self, plan: StoryPlanningIR, segment: SegmentCandidate,
                    budget: SegmentBudgetEstimate) -> list[list[str]]:
        per_node = {item.node_id: item for item in budget.node_estimates}
        weights = [per_node[item].structural_weight for item in segment.node_ids]
        if not weights:
            return []
        median = sorted(weights)[len(weights) // 2]
        threshold = max(2.0, median * 2.0)
        nodes_by_id = {node.node_id: node for node in plan.plot_nodes}
        rows: list[list[str]] = [[]]
        accumulated = 0.0
        for node_id in segment.node_ids:
            node = nodes_by_id[node_id]
            arc_signal = bool(node.major_choice or node.payoff
                              or node.information_move_refs or node.conflict_chain_ref)
            if rows[-1] and arc_signal and accumulated >= threshold:
                rows.append([])
                accumulated = 0.0
            rows[-1].append(node_id)
            accumulated += per_node[node_id].structural_weight
        return [row for row in rows if row]

    def _volume(self, plan: StoryPlanningIR, volume_id: str, segment: SegmentCandidate,
                arc_ids: list[str], budget: SegmentBudgetEstimate,
                index: int) -> VolumePlan:
        nodes = [node for node in plan.plot_nodes if node.node_id in set(segment.node_ids)]
        climax = max(nodes, key=lambda node: (node.importance == "core",
                                              bool(node.payoff), node.node_id))
        expansions = [milestone.location_ref for expansion in plan.map_expansions
                      for milestone in expansion.milestones
                      if milestone.trigger_node_id in set(segment.node_ids)]
        return VolumePlan(
            volume_id=volume_id, index=index, detail_level="arc",
            title=f"{segment.segment_id} {segment.dominant_conflict[:40]}".strip(),
            volume_goal=segment.dominant_conflict or (nodes[0].purpose if nodes else ""),
            opening_state=(nodes[0].state_change or nodes[0].purpose) if nodes else "",
            major_conflict=segment.dominant_conflict,
            character_arc_stage=", ".join(segment.character_arc_refs[:3]),
            faction_state=", ".join(segment.faction_arc_refs[:3]),
            location_expansion=sorted(set(expansions)) or list(segment.location_scope[:2]),
            progression_goal=", ".join(segment.progression_refs[:3]),
            information_goal=", ".join(segment.information_refs[:3]),
            major_nodes=list(segment.node_ids), climax_node_id=climax.node_id,
            climax=climax.purpose, cost=climax.cost or "",
            ending_state=climax.state_change or climax.payoff,
            next_volume_pressure="; ".join(segment.exit_pressures[:3]),
            arc_ids=arc_ids, chapter_budget=budget.estimate.preferred,
            provenance="generated", source="outline_compiler",
            note=f"boundary: {segment.boundary_reason}")

    def _arc(self, plan: StoryPlanningIR, arc_id: str, volume_id: str,
             node_ids: list[str], budget: SegmentBudgetEstimate, index: int,
             segment: SegmentCandidate) -> ArcPlan:
        nodes = [node for node in plan.plot_nodes if node.node_id in set(node_ids)]
        decisions = [DecisionStep(node_id=node.node_id,
                                  decision_owner_ref=node.decision_owner_ref,
                                  choice=node.major_choice, consequence=node.payoff,
                                  provenance="generated")
                     for node in nodes if node.major_choice]
        return ArcPlan(
            arc_id=arc_id, volume_id=volume_id, index=index, detail_level="arc",
            title=(f"{arc_id} {nodes[0].conflict[:30]}".strip() if nodes else arc_id),
            arc_goal=nodes[0].purpose if nodes else segment.dominant_conflict,
            opening_state=(nodes[0].state_change or nodes[0].purpose) if nodes else "",
            participants=sorted({participant for node in nodes
                                 for participant in node.participants}),
            location_scope=sorted({node.location_id for node in nodes if node.location_id}),
            conflict=next((node.conflict for node in nodes if node.conflict), ""),
            decision_chain=decisions,
            turns=[node.state_change for node in nodes if node.state_change][:5],
            payoff=next((node.payoff for node in reversed(nodes) if node.payoff), ""),
            cost=next((node.cost for node in reversed(nodes) if node.cost), ""),
            ending_state=next((node.state_change for node in reversed(nodes)
                               if node.state_change), ""),
            plot_nodes=list(node_ids), chapter_budget=budget.estimate.preferred,
            provenance="generated", source="outline_compiler",
            note=f"arc function {self._arc_function(plan, None, node_ids)}")

    def _arc_function(self, plan: StoryPlanningIR, arc: ArcPlan | None,
                      node_ids: list[str] | None = None) -> str:
        selected = node_ids or (arc.plot_nodes if arc else [])
        nodes = [node for node in plan.plot_nodes if node.node_id in set(selected)]
        if any(node.importance == "core" and node.payoff for node in nodes):
            return "climax"
        if any(node.information_move_refs for node in nodes):
            return "reveal"
        if any(node.progression_milestone_refs for node in nodes):
            return "progression"
        if any(node.relationship_change for node in nodes):
            return "relationship"
        if any(node.conflict for node in nodes):
            return "conflict"
        return "mixed"

    def _role(self, node) -> str:
        if node.optional:
            return "optional"
        if node.foreshadow_ids and not node.must_happen:
            return "foreshadow"
        if node.autonomous_action_refs:
            return "background_pressure"
        return "execution"

    def _carryover(self, plan: StoryPlanningIR, inventory: PlotPressureInventory,
                   volumes: list[VolumePlan]) -> list[PressureCarryover]:
        volume_of_node: dict[str, str] = {}
        for volume in volumes:
            for node_id in volume.major_nodes:
                volume_of_node[node_id] = volume.volume_id
        volume_ids = [volume.volume_id for volume in volumes]
        rows: list[PressureCarryover] = []
        for pressure in inventory.pressures:
            if pressure.state not in ("deferred", "intentionally_unresolved", "blocked"):
                continue
            source_volume = volume_of_node.get(pressure.source_ref, "")
            if not source_volume:
                continue
            index = volume_ids.index(source_volume)
            rows.append(PressureCarryover(
                pressure_id=pressure.pressure_id, from_volume=source_volume,
                to_volume=volume_ids[index + 1] if index + 1 < len(volume_ids) else "",
                reason=pressure.kind, status=pressure.state))
        return rows

    def _coverage(self, plan: StoryPlanningIR, candidate: OutlineCompilationCandidate,
                  inventory: PlotPressureInventory, volumes: int, arcs: int,
                  findings: list[PlanningFinding]) -> OutlineCoverageReport:
        allocated = {item.node_id for item in candidate.node_allocations}
        must_happen = {node.node_id for node in plan.plot_nodes if node.must_happen}
        optional = {node.node_id for node in plan.plot_nodes if node.optional}
        ledger = build_resource_ledger(plan)
        deficits = [row for row in ledger.rows if row.impossible_consumption]
        requirement_report = validate_requirements(plan)
        distribution: dict[str, dict[str, int]] = {key: {} for key in (
            "character", "relationship", "faction", "information", "foreshadow",
            "progression", "reward", "conflict")}

        def bump(bucket: str, key: str) -> None:
            rows = distribution[bucket]
            rows[key] = rows.get(key, 0) + 1

        nodes_by_id = {node.node_id: node for node in plan.plot_nodes}
        for row in candidate.node_allocations:
            node = nodes_by_id.get(row.node_id)
            if node is None:
                continue
            for ref in node.character_arc_refs:
                bump("character", ref)
            for ref in node.relationship_arc_refs:
                bump("relationship", ref)
            for ref in node.faction_arc_refs:
                bump("faction", ref)
            for ref in node.information_move_refs:
                bump("information", ref)
            for ref in node.foreshadow_move_refs:
                bump("foreshadow", ref)
            for ref in node.progression_milestone_refs:
                bump("progression", ref)
            for ref in node.reward_refs:
                bump("reward", ref)
            if node.conflict_chain_ref:
                bump("conflict", node.conflict_chain_ref)
        status: CompilationStatus = ("blocked" if any(item.severity == "ERROR"
                                                      for item in findings)
                                     else "needs_attention"
                                     if any(item.severity == "WARNING"
                                            for item in findings) else "valid")
        return OutlineCoverageReport(
            volumes=volumes, arcs=arcs, allocated_nodes=len(allocated),
            must_happen_total=len(must_happen),
            must_happen_allocated=len(must_happen & allocated),
            optional_deferred=sorted(optional - allocated),
            unallocated_must_happen=sorted(must_happen - allocated),
            pressure_carryover=len(candidate.carryover_pressures),
            ignored_pressures=list(candidate.ignored_pressure_ids),
            character_arc_distribution=distribution["character"],
            relationship_distribution=distribution["relationship"],
            faction_distribution=distribution["faction"],
            information_distribution=distribution["information"],
            foreshadow_distribution=distribution["foreshadow"],
            progression_distribution=distribution["progression"],
            reward_distribution=distribution["reward"],
            conflict_escalation_distribution=distribution["conflict"],
            resource_feasibility=("blocked" if deficits else
                                  "valid" if requirement_report.ok() else "needs_attention"),
            requirement_closure={"problems": len(requirement_report.findings)},
            status=status)


def promote_outline_candidate(repository: PlanningRepository,
                              candidate: OutlineCompilationCandidate, *,
                              approved: bool = False, revision_id: str = "",
                              note: str = ""
                              ) -> tuple[OutlineCompilationRecord, PlanningRevisionRecord]:
    """把编译结果写入**新的** Planning revision（旧 revision 内容不变）。"""

    if not approved:
        raise ValueError("OUTLINE_CANDIDATE_NOT_APPROVED: promote 需要显式 approve")
    if candidate.blocking():
        raise ValueError("OUTLINE_CANDIDATE_BLOCKED: 存在 blocking ERROR，不能 promote")
    base = repository.load(candidate.source_revision_id)
    payload = base.plan.model_dump(mode="json")
    payload["volumes"] = [item.model_dump(mode="json") for item in candidate.volume_plans]
    payload["arcs"] = [item.model_dump(mode="json") for item in candidate.arc_plans]
    record = repository.create(
        type(base.plan).model_validate(payload), branch_id=base.branch_id,
        status="proposed", note=note or f"outline compilation {candidate.candidate_id}",
        parent_revision_id=base.revision_id, source_revision=base.revision_id,
        revision_id=revision_id)
    compilation = OutlineCompilationRecord(
        source_revision=base.revision_id, source_digest=base.content_digest,
        scope=candidate.scope,
        route_promotion_ref=str(candidate.route_provenance.get("candidate_id", "")),
        candidate_id=candidate.candidate_id, promoted_revision_id=record.revision_id,
        validation_digest=planning_digest(
            [item.model_dump(mode="json") for item in candidate.validation_findings]))
    return compilation, record


__all__ = [
    "ARC_FUNCTIONS",
    "COMPILER_VERSION",
    "CompilationScope",
    "CompilationStatus",
    "NodeAllocation",
    "OutlineCompilationCandidate",
    "OutlineCompilationRecord",
    "OutlineCompiler",
    "OutlineCoverageReport",
    "PressureCarryover",
    "promote_outline_candidate",
]
