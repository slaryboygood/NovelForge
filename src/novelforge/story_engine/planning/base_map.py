"""M5：Base / Settlement Progression 与 Map Expansion Plan。

- `BaseProgressionPlan`：基地 / 据点 / 城市 / 领地 / 组织根据地的阶段升级（题材无关：
  都市题材可以是公司 / 工作室，奇幻可以是领地 / 城堡 / 宗门）；
- `MapExpansionPlan`：基于 M4 `LocationGraph` 与 `reachable_locations()` 的扩张里程碑
  （unknown → known → reachable → surveyed → controlled → secured）。
"""

from __future__ import annotations

from .enums import MAP_EXPANSION_ORDER
from .findings import AnalysisReport, PlanningFinding, add_finding
from .graphs import declared_access, entry_locations, reachable_locations
from .models import StoryPlanningIR
from .ordering import order_of
from .requirements import evaluate_requirements, validate_requirements


def analyze_base_progression(plan: StoryPlanningIR, *, revision_id: str = "") -> AnalysisReport:
    report = AnalysisReport(novel_id=plan.novel_id, planning_id=plan.planning_id,
                            revision_id=revision_id)
    findings: list[PlanningFinding] = []
    location_ids = {item.location_id for item in plan.locations}
    node_ids = {item.node_id for item in plan.plot_nodes}
    resource_ids = {item.identity() for item in plan.resource_plans}
    for base in plan.base_progressions:
        if not base.stages:
            add_finding(findings, "BASE_NO_STAGE", "WARNING", "base", base.base_id,
                        "据点计划没有任何阶段")
            continue
        labels = [stage.label for stage in base.stages if stage.label]
        duplicates = sorted({label for label in labels if labels.count(label) > 1})
        if duplicates:
            add_finding(findings, "BASE_STAGE_ORDER", "ERROR", "base", base.base_id,
                        "据点阶段标签重复（无法确定顺序）", related=tuple(duplicates))
        stage_ids = {stage.stage_id for stage in base.stages}
        for field, value in (("start_stage_id", base.start_stage_id),
                             ("end_stage_id", base.end_stage_id)):
            if value and value not in stage_ids:
                add_finding(findings, "BASE_STAGE_UNKNOWN", "ERROR", "base", base.base_id,
                            f"{field} 不在 stages 里", related=(value,))
        for stage in base.stages:
            if stage.unlock_node and stage.unlock_node not in node_ids:
                add_finding(findings, "BASE_UNLOCK_NODE_UNKNOWN", "ERROR", "base",
                            stage.stage_id, "阶段的 unlock_node 不是已知 PlotNode",
                            related=(stage.unlock_node,))
            for territory in stage.territory:
                if territory not in location_ids:
                    add_finding(findings, "BASE_TERRITORY_DANGLING", "ERROR", "base",
                                stage.stage_id, "阶段领土不是 planning 地点",
                                related=(territory,))
            for cost in stage.cost_refs:
                if cost.startswith(("RPLAN_", "RFLOW_")) and cost not in resource_ids:
                    add_finding(findings, "BASE_COST_REF_UNKNOWN", "WARNING", "base",
                                stage.stage_id, "阶段成本引用了未知资源", related=(cost,))
            if stage.production and not any(flow.target_ref == base.base_ref
                                            or flow.source_ref == base.base_ref
                                            for flow in plan.resource_flows):
                add_finding(findings, "BASE_PRODUCTION_WITHOUT_FLOW", "WARNING", "base",
                            stage.stage_id,
                            "阶段声明了 production，但没有任何 ResourceFlow 关联该据点")
    report.findings.extend(findings)
    report.extend(validate_requirements(plan, revision_id=revision_id).findings)
    return report


def analyze_map_expansion(plan: StoryPlanningIR, *, revision_id: str = "",
                          available_requirements: tuple[str, ...] = ()) -> AnalysisReport:
    report = AnalysisReport(novel_id=plan.novel_id, planning_id=plan.planning_id,
                            revision_id=revision_id)
    findings: list[PlanningFinding] = []
    location_ids = {item.location_id for item in plan.locations}
    node_ids = {item.node_id for item in plan.plot_nodes}
    declared, availability = declared_access(plan)
    reachable: set[str] = set()
    for entry in entry_locations(plan) or sorted(location_ids):
        reachable.update(reachable_locations(
            plan, entry, available_requirements=declared, available_availability=availability
        ).reachable)
    for expansion in plan.map_expansions:
        for milestone in expansion.milestones:
            if milestone.location_ref not in location_ids:
                add_finding(findings, "MAP_EXPANSION_UNKNOWN_LOCATION", "ERROR",
                            "map", milestone.milestone_id,
                            "扩张目标地点不存在", related=(milestone.location_ref,))
                continue
            from_order = MAP_EXPANSION_ORDER[milestone.from_stage]
            to_order = MAP_EXPANSION_ORDER[milestone.to_stage]
            if to_order <= from_order:
                add_finding(findings, "MAP_EXPANSION_STAGE_ORDER", "ERROR", "map",
                            milestone.milestone_id, "扩张阶段没有前进",
                            related=(milestone.location_ref,))
            if milestone.trigger_node_id and milestone.trigger_node_id not in node_ids:
                add_finding(findings, "MAP_EXPANSION_TRIGGER_UNKNOWN", "ERROR", "map",
                            milestone.milestone_id, "扩张触发节点不是已知 PlotNode",
                            related=(milestone.trigger_node_id,))
            if to_order >= MAP_EXPANSION_ORDER["surveyed"] \
                    and milestone.location_ref not in reachable:
                add_finding(findings, "MAP_EXPANSION_NO_STRUCTURAL_PATH", "ERROR", "map",
                            milestone.milestone_id,
                            "计划勘察 / 控制 / 固守，但结构上不可达",
                            related=(milestone.location_ref,))
            if to_order >= MAP_EXPANSION_ORDER["controlled"]:
                stage_history = {item.to_stage for item in expansion.milestones
                                 if item.location_ref == milestone.location_ref
                                 and MAP_EXPANSION_ORDER[item.to_stage] < to_order}
                if not (stage_history & {"reachable", "surveyed"}):
                    add_finding(findings, "MAP_EXPANSION_CONTROLLED_BEFORE_REACHABLE", "ERROR",
                                "map", milestone.milestone_id,
                                "未先计划 reachable / surveyed 就直接控制 / 固守",
                                related=(milestone.location_ref,))
            if to_order - from_order > 2 and milestone.requirements is None \
                    and not milestone.trigger_node_id:
                add_finding(findings, "MAP_EXPANSION_STAGE_JUMP", "WARNING", "map",
                            milestone.milestone_id,
                            "一次跨越多个扩张阶段，但没有条件或触发节点",
                            related=(milestone.location_ref,),
                            from_stage=milestone.from_stage, to_stage=milestone.to_stage)
            if milestone.requirements is not None:
                evaluation = evaluate_requirements(milestone.requirements,
                                                   available=available_requirements)
                if evaluation.missing():
                    add_finding(findings, "MAP_EXPANSION_UNSATISFIED_REQUIREMENT", "WARNING",
                                "map", milestone.milestone_id,
                                "扩张要求在当前（supplied）context 下未满足",
                                related=tuple(evaluation.missing()))
    # 扩张速度异常：同一触发节点上出现多个地区跃迁（相对判断，不用固定章数阈值）
    by_trigger: dict[str, list[str]] = {}
    for expansion in plan.map_expansions:
        for milestone in expansion.milestones:
            if milestone.trigger_node_id:
                by_trigger.setdefault(milestone.trigger_node_id, []).append(
                    milestone.milestone_id)
    for trigger, milestone_ids in sorted(by_trigger.items()):
        if len(milestone_ids) > 2:
            add_finding(findings, "MAP_EXPANSION_RATE_ANOMALY", "WARNING", "map", trigger,
                        "同一个触发节点上出现多个地区跃迁",
                        related=tuple(sorted(milestone_ids)))
    report.findings.extend(findings)
    return report


def base_stage_order(plan: StoryPlanningIR, base_id: str) -> list[dict[str, object]]:
    """只读：按 unlock_node 的 timeline 顺序返回据点阶段（无锚点者排在最后）。"""

    base = next((item for item in plan.base_progressions if item.base_id == base_id), None)
    if base is None:
        return []
    rows = [{"stage_id": stage.stage_id, "label": stage.label,
             "order": order_of(plan, stage.unlock_node)} for stage in base.stages]
    return sorted(rows, key=lambda row: (row["order"] is None, row["order"] or 0))


__all__ = ["analyze_base_progression", "analyze_map_expansion", "base_stage_order"]
