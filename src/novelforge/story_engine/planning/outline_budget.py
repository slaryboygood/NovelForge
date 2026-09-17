"""M8A：Structural Budget Estimator —— 结构复杂度 → 章节预算估计。

- 严禁 `node_count × 固定章数`；预算由 importance / 参与者 / 地点转换 / 选择 /
  信息与伏笔动作 / 成长 / 资源与装备后果 / 地图扩张 / reward 级别 / 冲突升级 /
  requirement 复杂度 / 自主行动碰撞等结构化信号推导；
- 输出 structural_weight + complexity_band + estimated_chapter_range（min/preferred/max），
  这是 **Planning estimate**，不是真相；
- 平均章幅来自参数（NovelSpec / Genre Template / author config）；Core 只提供中性默认值，
  不做任何题材分支。
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import Field

from novelforge.models import StrictModel

from .findings import AnalysisReport, PlanningFinding, add_finding
from .models import PlotNode, StoryPlanningIR
from .plot_pressure import PlotPressureInventory, build_plot_pressure_inventory

ComplexityBand = Literal["micro", "small", "medium", "large", "set_piece"]
IMPORTANCE_WEIGHT: dict[str, float] = {"core": 3.0, "major": 2.0, "minor": 1.0}
BAND_RANGE: dict[str, tuple[int, int, int]] = {
    "micro": (1, 1, 2), "small": (1, 2, 3), "medium": (2, 4, 6),
    "large": (4, 6, 9), "set_piece": (6, 9, 14),
}
DEFAULT_AVERAGE_CHAPTER_WORDS = 3000


class ChapterBudgetEstimate(StrictModel):
    minimum: int = Field(default=1, ge=0)
    preferred: int = Field(default=1, ge=0)
    maximum: int = Field(default=2, ge=0)
    note: str = Field(default="planning estimate，不是固定章数", max_length=120)


class NodeBudgetEstimate(StrictModel):
    node_id: str = Field(default="", max_length=64)
    structural_weight: float = 0.0
    complexity_band: ComplexityBand = "small"
    signals: dict[str, Any] = Field(default_factory=dict)
    estimate: ChapterBudgetEstimate = Field(default_factory=ChapterBudgetEstimate)
    non_authoritative: bool = True


class SegmentBudgetEstimate(StrictModel):
    segment_id: str = Field(default="", max_length=64)
    node_ids: list[str] = Field(default_factory=list)
    budget_weight: float = 0.0
    estimate: ChapterBudgetEstimate = Field(default_factory=ChapterBudgetEstimate)
    node_estimates: list[NodeBudgetEstimate] = Field(default_factory=list)
    non_authoritative: bool = True


class StructuralBudgetEstimator:
    def __init__(self, *, average_chapter_words: int = DEFAULT_AVERAGE_CHAPTER_WORDS,
                 source: str = "neutral_default") -> None:
        self.average_chapter_words = max(500, int(average_chapter_words))
        self.source = source

    # ---------------------------------------------------------------- node
    def estimate_node(self, plan: StoryPlanningIR, node: PlotNode,
                      inventory: PlotPressureInventory | None = None) -> NodeBudgetEstimate:
        signals: dict[str, Any] = {
            "importance": node.importance,
            "participants": len(node.participants),
            "location": bool(node.location_id),
            "major_choice": bool(node.major_choice),
            "relationship_change": bool(node.relationship_change),
            "faction_change": bool(node.faction_arc_refs or node.faction_relation_refs),
            "information_moves": len(node.information_move_refs),
            "foreshadow_moves": len(node.foreshadow_move_refs),
            "progression": len(node.progression_milestone_refs),
            "resource_flows": len(node.resource_flow_refs),
            "equipment": len(node.equipment_refs),
            "map_expansion": len(node.map_expansion_refs),
            "rewards": len(node.reward_refs),
            "requirements": (len(node.requirements.requirements)
                             if node.requirements is not None else 0),
            "autonomous_actions": len(node.autonomous_action_refs),
            "conflict_chain": bool(node.conflict_chain_ref),
        }
        weight = IMPORTANCE_WEIGHT.get(node.importance, 1.0)
        weight += min(signals["participants"], 5) * 0.35
        weight += min(signals["information_moves"] + signals["foreshadow_moves"], 6) * 0.4
        weight += min(signals["resource_flows"] + signals["equipment"], 4) * 0.3
        weight += min(signals["progression"], 3) * 0.4
        weight += min(signals["map_expansion"], 3) * 0.4
        weight += min(signals["rewards"], 3) * 0.3
        weight += min(signals["requirements"], 4) * 0.25
        weight += min(signals["autonomous_actions"], 3) * 0.2
        if signals["major_choice"]:
            weight += 0.6
        if signals["relationship_change"]:
            weight += 0.4
        if signals["conflict_chain"]:
            weight += 0.5
        if node.must_happen:
            weight += 0.5
        band = self._band(weight)
        minimum, preferred, maximum = BAND_RANGE[band]
        return NodeBudgetEstimate(
            node_id=node.node_id, structural_weight=round(weight, 4),
            complexity_band=band, signals=signals,
            estimate=ChapterBudgetEstimate(minimum=minimum, preferred=preferred,
                                           maximum=maximum))

    def _band(self, weight: float) -> ComplexityBand:
        if weight < 1.5:
            return "micro"
        if weight < 2.5:
            return "small"
        if weight < 4.0:
            return "medium"
        if weight < 6.0:
            return "large"
        return "set_piece"

    # ---------------------------------------------------------------- segment
    def estimate_segment(self, plan: StoryPlanningIR, segment_id: str,
                         node_ids: list[str],
                         inventory: PlotPressureInventory | None = None
                         ) -> SegmentBudgetEstimate:
        rows = [self.estimate_node(plan, node, inventory)
                for node in plan.plot_nodes if node.node_id in set(node_ids)]
        weight = round(sum(item.structural_weight for item in rows), 4)
        minimum = sum(item.estimate.minimum for item in rows)
        preferred = sum(item.estimate.preferred for item in rows)
        maximum = sum(item.estimate.maximum for item in rows)
        return SegmentBudgetEstimate(
            segment_id=segment_id, node_ids=list(node_ids), budget_weight=weight,
            estimate=ChapterBudgetEstimate(minimum=minimum, preferred=preferred,
                                           maximum=maximum),
            node_estimates=rows)

    # ---------------------------------------------------------------- target
    def target_alignment(self, plan: StoryPlanningIR,
                         total: ChapterBudgetEstimate) -> AnalysisReport:
        """target_words → rough chapter capacity；结构不足 / 过密只给 findings。"""

        report = AnalysisReport(novel_id=plan.novel_id, planning_id=plan.planning_id)
        findings: list[PlanningFinding] = []
        target_words = plan.intent.target_words if plan.intent else 0
        if target_words <= 0:
            return report
        capacity_min = max(1, target_words // max(1, self.average_chapter_words * 2))
        capacity_max = max(1, target_words // max(1, self.average_chapter_words // 2))
        if total.maximum < capacity_min:
            add_finding(findings, "STRUCTURE_TOO_THIN_FOR_TARGET",
                        "WARNING" if capacity_min - total.maximum < capacity_min * 0.3
                        else "ERROR", "outline", plan.planning_id,
                        "StorySpine 结构不足以支撑 target_words（禁止靠重复剧情凑字数）",
                        target_words=target_words, structure_max=total.maximum,
                        capacity_min=capacity_min)
        elif total.minimum > capacity_max:
            add_finding(findings, "STRUCTURE_TOO_DENSE_FOR_TARGET", "WARNING", "outline",
                        plan.planning_id, "结构密度远超 target_words 能承载的容量",
                        target_words=target_words, structure_min=total.minimum,
                        capacity_max=capacity_max)
        report.findings.extend(findings)
        return report


def estimate_plan_budget(plan: StoryPlanningIR, *,
                         estimator: StructuralBudgetEstimator | None = None,
                         inventory: PlotPressureInventory | None = None
                         ) -> ChapterBudgetEstimate:
    """整份 Planning 的结构预算（不输出"必须 N 章"）。"""

    estimator = estimator or StructuralBudgetEstimator()
    inventory = inventory or build_plot_pressure_inventory(plan)
    rows = [estimator.estimate_node(plan, node, inventory) for node in plan.plot_nodes]
    return ChapterBudgetEstimate(
        minimum=sum(item.estimate.minimum for item in rows),
        preferred=sum(item.estimate.preferred for item in rows),
        maximum=sum(item.estimate.maximum for item in rows),
        note="planning estimate（含 min/preferred/max range）")


__all__ = [
    "BAND_RANGE",
    "ChapterBudgetEstimate",
    "ComplexityBand",
    "DEFAULT_AVERAGE_CHAPTER_WORDS",
    "NodeBudgetEstimate",
    "SegmentBudgetEstimate",
    "StructuralBudgetEstimator",
    "estimate_plan_budget",
]
