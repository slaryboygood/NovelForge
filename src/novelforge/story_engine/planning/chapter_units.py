"""M9：Arc → Chapter Semantic Unit（派生 proposal artifact，不是新 truth）。

ArcPlan + PlotNode + M4/M5/M6 结构化信号 → 不能继续合理合并的叙事执行单元；
再把 unit 合并 / 拆分编成 `ChapterDecompositionPlan`：章数由语义决定，
`preferred` 只是 hint（禁止为凑 preferred 生成 filler chapter）。
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import Field

from novelforge.models import StrictModel

from .models import ArcPlan, PlotNode, StoryPlanningIR
from .outline_budget import ChapterBudgetEstimate, StructuralBudgetEstimator
from .plot_pressure import build_plot_pressure_inventory
from .spine_analysis import topological_order

UnitKind = Literal["setup", "escalation", "choice", "consequence", "execution", "bridge",
                   "aftermath"]
SLOT_ORDER: tuple[UnitKind, ...] = ("setup", "escalation", "choice", "consequence")
BAND_SLOT_CAP: dict[str, int] = {"micro": 1, "small": 1, "medium": 2, "large": 3,
                                 "set_piece": 4}
BAND_WEIGHT: dict[str, float] = {"micro": 1.0, "small": 1.5, "medium": 2.5, "large": 4.0,
                                 "set_piece": 6.0}
# 合并上限：两个 unit 合并后的复杂度超过它就不再合（避免把两个重场压成一章）
MERGE_WEIGHT_LIMIT = 4.0


class ChapterSemanticUnit(StrictModel):
    """一个不能继续合理合并的叙事执行单元（Arc 内部的语义 unit）。"""

    unit_id: str = Field(min_length=5, max_length=64)
    arc_id: str = Field(default="", max_length=64)
    unit_kind: UnitKind = "execution"
    slot_index: int = Field(default=0, ge=0)
    primary_plot_node_id: str = Field(default="", max_length=64)
    plot_node_refs: list[str] = Field(default_factory=list)
    completes_plot_node_ids: list[str] = Field(default_factory=list)
    setup_node_refs: list[str] = Field(default_factory=list)
    foreshadow_node_refs: list[str] = Field(default_factory=list)
    consequence_node_refs: list[str] = Field(default_factory=list)
    decision_refs: list[str] = Field(default_factory=list)
    conflict_refs: list[str] = Field(default_factory=list)
    information_refs: list[str] = Field(default_factory=list)
    foreshadow_refs: list[str] = Field(default_factory=list)
    relationship_refs: list[str] = Field(default_factory=list)
    faction_refs: list[str] = Field(default_factory=list)
    progression_refs: list[str] = Field(default_factory=list)
    resource_refs: list[str] = Field(default_factory=list)
    equipment_refs: list[str] = Field(default_factory=list)
    map_refs: list[str] = Field(default_factory=list)
    reward_refs: list[str] = Field(default_factory=list)
    autonomous_refs: list[str] = Field(default_factory=list)
    pressure_refs: list[str] = Field(default_factory=list)
    location_id: str = Field(default="", max_length=64)
    participant_ids: list[str] = Field(default_factory=list)
    complexity_band: str = Field(default="small", max_length=16)
    structural_weight: float = 0.0
    is_bridge: bool = False
    bridge_reason: str = Field(default="", max_length=200)
    source_ids: list[str] = Field(default_factory=list)
    non_authoritative: bool = True

    def weight(self) -> float:
        return round(self.structural_weight or BAND_WEIGHT.get(self.complexity_band, 1.5), 4)

    def has_decision(self) -> bool:
        return bool(self.decision_refs)

    def has_payoff(self) -> bool:
        return bool(self.reward_refs or self.progression_refs or self.map_refs
                    or self.relationship_refs or self.faction_refs)

    def signal_domains(self) -> list[str]:
        rows = ("decision_refs", "conflict_refs", "information_refs", "foreshadow_refs",
                "relationship_refs", "faction_refs", "progression_refs", "resource_refs",
                "equipment_refs", "map_refs", "reward_refs", "autonomous_refs")
        return [name for name in rows if getattr(self, name)]


class ChapterDecompositionPlan(StrictModel):
    """Arc → chapter 数量的正式 proposal（章数由语义决定，preferred 只是 hint）。"""

    arc_id: str = Field(default="", max_length=64)
    source_revision_id: str = Field(default="", max_length=64)
    source_digest: str = Field(default="", max_length=64)
    budget_range: ChapterBudgetEstimate = Field(default_factory=ChapterBudgetEstimate)
    proposed_chapter_count: int = Field(default=0, ge=0)
    decomposition_reason: str = Field(default="", max_length=400)
    chapter_units: list[ChapterSemanticUnit] = Field(default_factory=list)
    chapter_groups: list[list[str]] = Field(default_factory=list)
    split_node_ids: list[str] = Field(default_factory=list)
    bridge_unit_ids: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    status: Literal["valid", "needs_attention"] = "valid"
    non_authoritative: bool = True


def _signals(plan: StoryPlanningIR, node: PlotNode) -> dict[str, list[str]]:
    rows: dict[str, list[str]] = {
        "decision_refs": list([node.node_id] if node.major_choice else []),
        "conflict_refs": [node.conflict_chain_ref] if node.conflict_chain_ref else [],
        "information_refs": list(node.information_move_refs),
        "foreshadow_refs": list(node.foreshadow_move_refs),
        "relationship_refs": [],
        "faction_refs": [],
        "progression_refs": list(node.progression_milestone_refs),
        "resource_refs": list(node.resource_flow_refs),
        "equipment_refs": list(node.equipment_refs),
        "map_refs": list(node.map_expansion_refs),
        "reward_refs": list(node.reward_refs),
        "autonomous_refs": list(node.autonomous_action_refs),
    }
    for arc in plan.relationship_arcs:
        for stage in arc.stages:
            if stage.trigger_node_id == node.node_id:
                rows["relationship_refs"].append(stage.stage_id or f"{arc.arc_id}_stage")
    for arc in plan.faction_arcs:
        for stage in arc.stages:
            if stage.trigger_node_id == node.node_id:
                rows["faction_refs"].append(stage.stage_id or f"{arc.arc_id}_stage")
    for relation in plan.faction_relations:
        if relation.trigger_node_id == node.node_id:
            rows["faction_refs"].append(relation.relation_id)
    for expansion in plan.map_expansions:
        for milestone in expansion.milestones:
            if milestone.trigger_node_id == node.node_id \
                    and milestone.milestone_id not in rows["map_refs"]:
                rows["map_refs"].append(milestone.milestone_id)
    for plan_row in plan.reward_plans:
        for event in plan_row.events:
            if event.trigger_node_id == node.node_id and event.reward_id not in rows["reward_refs"]:
                rows["reward_refs"].append(event.reward_id)
    for action in plan.autonomous_actions:
        if action.trigger_ref == node.node_id and action.action_id not in rows["autonomous_refs"]:
            rows["autonomous_refs"].append(action.action_id)
    for equipment in plan.equipment_plans:
        if node.node_id in equipment.nodes() and equipment.equipment_id not in rows["equipment_refs"]:
            rows["equipment_refs"].append(equipment.equipment_id)
    for track in plan.progression_tracks:
        for milestone in track.milestones:
            if milestone.node_id == node.node_id \
                    and milestone.milestone_id not in rows["progression_refs"]:
                rows["progression_refs"].append(milestone.milestone_id)
    for chain in plan.conflict_chains:
        for stage in chain.stages:
            if stage.trigger_node_id == node.node_id \
                    and chain.conflict_id not in rows["conflict_refs"]:
                rows["conflict_refs"].append(chain.conflict_id)
    return {key: sorted(dict.fromkeys(value)) for key, value in rows.items()}


def _setup_required(node: PlotNode, signals: dict[str, list[str]],
                    previous_location: str) -> bool:
    """setup unit 只在真有准备工作时出现（prerequisite / requirement / 转场 / 信息铺垫）。"""

    if node.prerequisites:
        return True
    if node.requirements is not None and node.requirements.requirements:
        return True
    if previous_location and node.location_id and node.location_id != previous_location:
        return True
    return bool(signals["foreshadow_refs"] or signals["information_refs"]
                or signals["equipment_refs"] or signals["resource_refs"])


def _escalation_required(signals: dict[str, list[str]], pressures: list[str]) -> bool:
    """escalation unit 只在真有升级压力时出现（冲突链 / 对立行动 / 势力动作 / 未解决压力）。"""

    return bool(signals["conflict_refs"] or signals["autonomous_refs"]
                or signals["faction_refs"] or pressures)


def _slots(node: PlotNode, signals: dict[str, list[str]], band: str, *,
           previous_location: str = "", pressures: tuple[str, ...] = ()
           ) -> list[UnitKind]:
    """complexity band 只表示 split capacity（展开空间），不制造不存在的语义。

    - choice：必须有 major_choice / decision 证据；
    - consequence：必须有独立 outcome / payoff / cost / state consequence；
    - setup / escalation：必须有对应的结构信号，且受 band capacity 限制（可被裁掉，
      因为它们本来就是"展开空间"，不是必需阶段）。
    """

    capacity = BAND_SLOT_CAP.get(band, 1)
    mandatory: list[UnitKind] = []
    if node.major_choice or signals["decision_refs"]:
        mandatory.append("choice")
    if node.payoff or node.cost or node.state_change or signals["reward_refs"] \
            or signals["progression_refs"]:
        mandatory.append("consequence")
    optional: list[UnitKind] = []
    if _setup_required(node, signals, previous_location):
        optional.append("setup")
    if _escalation_required(signals, list(pressures)):
        optional.append("escalation")
    room = max(0, capacity - len(mandatory))
    slots = optional[:room] + mandatory
    return slots or ["execution"]


def _bridge_has_function(plan: StoryPlanningIR, node: PlotNode,
                         signals: dict[str, list[str]]) -> tuple[bool, str]:
    """§17/§18：只有带叙事功能的移动才升级成 bridge chapter。"""

    if node.requirements is not None and node.requirements.requirements:
        return True, "requirement 门"
    for name, label in (("information_refs", "信息移动"), ("relationship_refs", "关系变化"),
                        ("faction_refs", "势力动作"), ("resource_refs", "资源代价"),
                        ("autonomous_refs", "自主行动"), ("conflict_refs", "冲突升级"),
                        ("progression_refs", "成长里程碑"), ("map_refs", "地图推进"),
                        ("foreshadow_refs", "伏笔动作")):
        if signals[name]:
            return True, label
    return False, ""


def build_semantic_units(plan: StoryPlanningIR, arc: ArcPlan, *,
                         estimator: StructuralBudgetEstimator | None = None,
                         inventory: Any | None = None) -> list[ChapterSemanticUnit]:
    """把 ArcPlan 展开成语义 unit 序列（确定性；同输入同输出）。"""

    estimator = estimator or StructuralBudgetEstimator()
    inventory = inventory or build_plot_pressure_inventory(plan)
    pressure_by_node: dict[str, list[str]] = {}
    for pressure in inventory.pressures:
        pressure_by_node.setdefault(pressure.source_ref, []).append(pressure.pressure_id)
    order = {node_id: index for index, node_id in enumerate(topological_order(plan))}
    nodes = sorted([node for node in plan.plot_nodes if node.node_id in set(arc.plot_nodes)],
                   key=lambda item: order.get(item.node_id, 0))
    units: list[ChapterSemanticUnit] = []
    previous_location = ""
    for node in nodes:
        signals = _signals(plan, node)
        estimate = estimator.estimate_node(plan, node, inventory)
        band = estimate.complexity_band
        if previous_location and node.location_id and node.location_id != previous_location:
            needed, reason = _bridge_has_function(plan, node, signals)
            if needed:
                units.append(ChapterSemanticUnit(
                    unit_id=f"UNIT_{arc.arc_id}_{len(units) + 1:03d}",
                    arc_id=arc.arc_id, unit_kind="bridge", slot_index=0,
                    primary_plot_node_id=node.node_id, plot_node_refs=[node.node_id],
                    information_refs=signals["information_refs"],
                    foreshadow_refs=signals["foreshadow_refs"],
                    relationship_refs=signals["relationship_refs"],
                    faction_refs=signals["faction_refs"],
                    progression_refs=signals["progression_refs"],
                    resource_refs=signals["resource_refs"],
                    map_refs=signals["map_refs"],
                    location_id=node.location_id, participant_ids=list(node.participants),
                    complexity_band="small", structural_weight=1.0, is_bridge=True,
                    bridge_reason=f"{previous_location}→{node.location_id}：{reason}",
                    pressure_refs=sorted(pressure_by_node.get(node.node_id, [])),
                    source_ids=sorted({node.node_id,
                                       *[item for values in signals.values()
                                         for item in values]})))
        slots = _slots(node, signals, band, previous_location=previous_location,
                       pressures=tuple(pressure_by_node.get(node.node_id, [])))
        weight = round(estimate.structural_weight / max(1, len(slots)), 4)
        node_moves = [move for arc_row in plan.information_arcs for move in arc_row.moves
                      if move.node_id == node.node_id]
        early_moves = [move.move_id for move in node_moves
                       if move.move_type in ("plant", "hint", "reinforce", "misdirect")]
        late_moves = [move.move_id for move in node_moves
                      if move.move_type in ("reveal", "payoff", "reinterpretation")]
        for slot_index, slot in enumerate(slots):
            if len(slots) == 1:
                slot_info = [move.move_id for move in node_moves]
            else:
                slot_info = (early_moves if slot_index == 0 else []) \
                    + (late_moves if slot_index == len(slots) - 1 else [])
            if slot_info:
                slot_info = sorted(dict.fromkeys(slot_info))
            units.append(ChapterSemanticUnit(
                unit_id=f"UNIT_{arc.arc_id}_{len(units) + 1:03d}",
                arc_id=arc.arc_id, unit_kind=slot, slot_index=slot_index,
                primary_plot_node_id=node.node_id, plot_node_refs=[node.node_id],
                completes_plot_node_ids=[node.node_id] if slot == slots[-1] else [],
                setup_node_refs=[node.node_id] if slot in ("setup", "escalation") else [],
                consequence_node_refs=[node.node_id] if slot == "consequence" else [],
                foreshadow_node_refs=[node.node_id] if signals["foreshadow_refs"] else [],
                decision_refs=signals["decision_refs"] if slot == "choice" else [],
                conflict_refs=signals["conflict_refs"], information_refs=slot_info,
                foreshadow_refs=signals["foreshadow_refs"],
                relationship_refs=signals["relationship_refs"],
                faction_refs=signals["faction_refs"], progression_refs=signals["progression_refs"],
                resource_refs=signals["resource_refs"], equipment_refs=signals["equipment_refs"],
                map_refs=signals["map_refs"], reward_refs=signals["reward_refs"],
                autonomous_refs=signals["autonomous_refs"],
                pressure_refs=sorted(pressure_by_node.get(node.node_id, [])),
                location_id=node.location_id, participant_ids=list(node.participants),
                complexity_band=band, structural_weight=weight,
                source_ids=sorted({node.node_id,
                                   *[item for values in signals.values() for item in values]})))
        previous_location = node.location_id or previous_location
    return units


def arc_budget_range(plan: StoryPlanningIR, arc: ArcPlan, *,
                     estimator: StructuralBudgetEstimator | None = None,
                     budget: ChapterBudgetEstimate | None = None) -> ChapterBudgetEstimate:
    """Arc 的 chapter budget range（优先采用 M8 产物，否则确定性重算）。"""

    if budget is not None and budget.maximum > 0:
        return budget
    estimator = estimator or StructuralBudgetEstimator()
    rows = [estimator.estimate_node(plan, node) for node in plan.plot_nodes
            if node.node_id in set(arc.plot_nodes)]
    estimate_min = sum(item.estimate.minimum for item in rows) or 1
    estimate_preferred = sum(item.estimate.preferred for item in rows) or 1
    estimate_max = sum(item.estimate.maximum for item in rows) or 2
    # range 由节点结构复杂度推导（min/max 是结构地板与上限）；
    # arc.chapter_budget 只作为作者/M8A 的 preferred hint（可能来自旧数据，不作为硬地板）。
    preferred = int(arc.chapter_budget) if arc.chapter_budget and arc.chapter_budget > 0 \
        else estimate_preferred
    return ChapterBudgetEstimate(
        minimum=estimate_min, preferred=preferred, maximum=estimate_max,
        note="M9 arc chapter budget range（node estimate 推导；preferred 只是 hint）")


def _can_merge(group: list[ChapterSemanticUnit], unit: ChapterSemanticUnit) -> bool:
    last = group[-1]
    # bridge / transition chapter 独立成章：它必须自己承担叙事功能（§17/§18）
    if unit.is_bridge or last.is_bridge:
        return False
    # setup / escalation 是为**自己那个 PlotNode** 做的准备：跨节点合并会让 anchor 漂移
    if last.primary_plot_node_id != unit.primary_plot_node_id \
            and (unit.unit_kind in ("setup", "escalation")
                 or last.unit_kind in ("setup", "escalation")):
        return False
    if last.unit_kind == "choice" or unit.unit_kind == "choice":
        return False
    if last.has_decision() and unit.has_decision():
        return False
    if last.has_payoff() and unit.has_payoff():
        return False
    if last.location_id and unit.location_id and last.location_id != unit.location_id:
        return False
    if last.participant_ids and unit.participant_ids \
            and not set(last.participant_ids) & set(unit.participant_ids):
        return False
    total = sum(item.weight() for item in group) + unit.weight()
    return total <= MERGE_WEIGHT_LIMIT


def plan_chapter_decomposition(plan: StoryPlanningIR, arc: ArcPlan, *,
                               revision_id: str = "",
                               estimator: StructuralBudgetEstimator | None = None,
                               inventory: Any | None = None,
                               budget: ChapterBudgetEstimate | None = None
                               ) -> ChapterDecompositionPlan:
    """Arc → 章节数量 proposal：先 unit，再 merge/split，最后记录 budget 对照。"""

    units = build_semantic_units(plan, arc, estimator=estimator, inventory=inventory)
    groups: list[list[ChapterSemanticUnit]] = []
    for unit in units:
        if groups and _can_merge(groups[-1], unit):
            groups[-1].append(unit)
        else:
            groups.append([unit])
    budget_range = arc_budget_range(plan, arc, estimator=estimator, budget=budget)
    count = len(groups)
    split_nodes = sorted({unit.primary_plot_node_id for unit in units
                          if sum(1 for item in units
                                 if item.primary_plot_node_id == unit.primary_plot_node_id) > 1})
    bridge_ids = [unit.unit_id for unit in units if unit.is_bridge]
    warnings: list[str] = []
    reasons = [f"units={len(units)}", f"chapters={count}",
               f"budget=[{budget_range.minimum},{budget_range.maximum}]"]
    if count > budget_range.maximum:
        reasons.append("超出 max：语义需要更多章，不压缩")
    elif count < budget_range.minimum:
        reasons.append("低于 min：结构确实只需要这些章，不注水")
    else:
        reasons.append("落在 budget range 内")
    status: Literal["valid", "needs_attention"] = (
        "valid" if budget_range.minimum <= count <= budget_range.maximum else "needs_attention")
    return ChapterDecompositionPlan(
        arc_id=arc.arc_id, source_revision_id=revision_id,
        source_digest=_digest(plan), budget_range=budget_range,
        proposed_chapter_count=count,
        decomposition_reason=f"{arc.arc_id}: " + "；".join(reasons),
        chapter_units=units, chapter_groups=[[unit.unit_id for unit in group] for group in groups],
        split_node_ids=split_nodes, bridge_unit_ids=bridge_ids, warnings=warnings,
        status=status)


def _digest(plan: StoryPlanningIR) -> str:
    from .versioning import planning_digest
    return planning_digest(plan)


__all__ = [
    "BAND_SLOT_CAP",
    "BAND_WEIGHT",
    "MERGE_WEIGHT_LIMIT",
    "SLOT_ORDER",
    "ChapterDecompositionPlan",
    "ChapterSemanticUnit",
    "UnitKind",
    "arc_budget_range",
    "build_semantic_units",
    "plan_chapter_decomposition",
]
