"""M5：NPC / Faction Autonomous Action 与 FactionRelation。

原则：默认 `requires_protagonist_presence = False`——世界不只在主角出现时运转。
分析只输出 findings：actor / trigger / 信息依赖 / 可达性 / "永远依赖主角"。
"""

from __future__ import annotations

from .findings import AnalysisReport, PlanningFinding, add_finding
from .graphs import (
    declared_access,
    entry_locations,
    faction_pressure_candidates,
    reachable_locations,
)
from .models import StoryPlanningIR
from .ordering import order_of
from .requirements import stage_trigger_node, validate_requirements


def analyze_autonomous_actions(plan: StoryPlanningIR, *, revision_id: str = "") -> AnalysisReport:
    report = AnalysisReport(novel_id=plan.novel_id, planning_id=plan.planning_id,
                            revision_id=revision_id)
    findings: list[PlanningFinding] = []
    character_ids = {item.character_id for item in plan.characters}
    faction_ids = {item.faction_id for item in plan.factions}
    entity_refs = {item.entity_ref for item in plan.characters if item.entity_ref}
    location_ids = {item.location_id for item in plan.locations}
    node_ids = {item.node_id for item in plan.plot_nodes}
    truth_holders: dict[str, set[str]] = {}
    for arc in plan.information_arcs:
        for truth in arc.truths:
            holders = set(truth.character_knows) | set(truth.faction_knows)
            if truth.protagonist_knows:
                holders.add("ENTITY_PROTAGONIST")
            truth_holders[truth.truth_id] = holders
    other_targets = {item.base_id for item in plan.base_progressions}
    other_targets |= {item.identity() for item in plan.resource_plans}
    other_targets |= {item.equipment_id for item in plan.equipment_plans}
    other_targets |= {item.requirement_id for group in plan.requirement_groups()
                      for item in group.requirements}
    requirements, availability = declared_access(plan)
    reachable: set[str] = set()
    for entry in entry_locations(plan) or sorted(location_ids):
        reachable.update(reachable_locations(
            plan, entry, available_requirements=requirements,
            available_availability=availability).reachable)
    for action in plan.autonomous_actions:
        if action.actor_ref not in character_ids and action.actor_ref not in faction_ids \
                and action.actor_ref not in entity_refs:
            add_finding(findings, "AUTONOMOUS_ACTOR_UNKNOWN", "ERROR", "autonomous",
                        action.action_id, "行动主体不是 planning 人物 / 势力 / 已知实体",
                        related=(action.actor_ref,))
        if not action.goal:
            add_finding(findings, "AUTONOMOUS_GOAL_EMPTY", "WARNING", "autonomous",
                        action.action_id, "自主行动没有目标")
        if action.trigger_ref and action.trigger_ref not in node_ids \
                and action.trigger_ref not in truth_holders:
            add_finding(findings, "AUTONOMOUS_TRIGGER_UNKNOWN", "ERROR", "autonomous",
                        action.action_id, "触发引用既不是 PlotNode 也不是真相",
                        related=(action.trigger_ref,))
        for dependency in action.information_dependency:
            if dependency not in truth_holders:
                add_finding(findings, "AUTONOMOUS_INFORMATION_DEPENDENCY_UNKNOWN", "ERROR",
                            "autonomous", action.action_id,
                            "信息依赖不是已知真相", related=(dependency,))
                continue
            if action.actor_ref not in truth_holders[dependency]:
                add_finding(findings, "AUTONOMOUS_ACTOR_NOT_INFORMED", "ERROR", "autonomous",
                            action.action_id, "行动主体并不知道所依赖的信息",
                            related=(dependency, action.actor_ref))
        if action.location_ref:
            if action.location_ref not in location_ids:
                add_finding(findings, "AUTONOMOUS_LOCATION_UNKNOWN", "ERROR", "autonomous",
                            action.action_id, "行动地点不是 planning 地点",
                            related=(action.location_ref,))
            elif action.location_ref not in reachable:
                add_finding(findings, "AUTONOMOUS_LOCATION_UNREACHABLE", "ERROR",
                            "autonomous", action.action_id,
                            "行动地点结构上不可达", related=(action.location_ref,))
        for target in action.target_refs:
            if target in character_ids or target in faction_ids or target in entity_refs \
                    or target in location_ids or target in truth_holders \
                    or target in other_targets:
                continue
            add_finding(findings, "AUTONOMOUS_TARGET_UNKNOWN", "WARNING", "autonomous",
                        action.action_id, "行动目标无法解析", related=(target,))
        if order_of(plan, action.trigger_ref) is None and action.trigger_ref.startswith("NODE_"):
            add_finding(findings, "AUTONOMOUS_TRIGGER_NOT_ANCHORED", "WARNING", "autonomous",
                        action.action_id,
                        "触发节点没有 timeline 锚点，无法判断先后顺序",
                        related=(action.trigger_ref,))
    if plan.autonomous_actions and all(action.requires_protagonist_presence
                                       for action in plan.autonomous_actions):
        add_finding(findings, "AUTONOMOUS_ALWAYS_PROTAGONIST_DEPENDENT", "WARNING",
                    "autonomous", plan.planning_id,
                    "所有自主行动都要求主角在场（世界会显得静止）")
    report.findings.extend(findings)
    report.extend(validate_requirements(plan, revision_id=revision_id).findings)
    return report


def analyze_faction_relations(plan: StoryPlanningIR, *, revision_id: str = "") -> AnalysisReport:
    report = AnalysisReport(novel_id=plan.novel_id, planning_id=plan.planning_id,
                            revision_id=revision_id)
    findings: list[PlanningFinding] = []
    faction_ids = {item.faction_id for item in plan.factions}
    node_ids = {item.node_id for item in plan.plot_nodes}
    seen: dict[tuple[str, str, str], str] = {}
    declared: dict[tuple[str, str], set[str]] = {}
    for faction in plan.factions:
        for ally in faction.allies:
            declared.setdefault((faction.faction_id, ally), set()).add("alliance")
        for enemy in faction.enemies:
            declared.setdefault((faction.faction_id, enemy), set()).add("hostility")
    for relation in plan.faction_relations:
        for endpoint in (relation.from_faction_id, relation.to_faction_id):
            if endpoint not in faction_ids:
                add_finding(findings, "FACTION_RELATION_UNKNOWN_FACTION", "ERROR",
                            "faction", relation.relation_id,
                            "势力关系指向不存在的势力规划", related=(endpoint,))
        key = (relation.from_faction_id, relation.to_faction_id, relation.relation_type)
        if key in seen:
            add_finding(findings, "FACTION_RELATION_DUPLICATE", "ERROR", "faction",
                        relation.relation_id, "同一对势力出现重复关系",
                        related=(seen[key],))
        seen[key] = relation.relation_id
        if relation.trigger_node_id and relation.trigger_node_id not in node_ids:
            add_finding(findings, "FACTION_RELATION_TRIGGER_UNKNOWN", "ERROR", "faction",
                        relation.relation_id, "势力关系触发节点不存在",
                        related=(relation.trigger_node_id,))
        existing = declared.get((relation.from_faction_id, relation.to_faction_id), set())
        if relation.relation_type == "hostility" and "alliance" in existing:
            add_finding(findings, "FACTION_RELATION_CONTRADICTION", "ERROR", "faction",
                        relation.relation_id,
                        "FactionPlan allies 与 hostility 关系互相矛盾",
                        related=(relation.from_faction_id, relation.to_faction_id))
        if relation.relation_type == "alliance" and "hostility" in existing:
            add_finding(findings, "FACTION_RELATION_CONTRADICTION", "ERROR", "faction",
                        relation.relation_id,
                        "FactionPlan enemies 与 alliance 关系互相矛盾",
                        related=(relation.from_faction_id, relation.to_faction_id))
        if relation.symmetric:
            reverse = next((item for item in plan.faction_relations
                            if item.from_faction_id == relation.to_faction_id
                            and item.to_faction_id == relation.from_faction_id
                            and item.relation_type != relation.relation_type), None)
            if reverse is not None:
                add_finding(findings, "FACTION_RELATION_ASYMMETRY_UNDECLARED", "WARNING",
                            "faction", relation.relation_id,
                            "声明为对称关系，但反向存在不同类型的关系",
                            related=(reverse.relation_id,))
    report.findings.extend(findings)
    return report


def faction_relation_edges(plan: StoryPlanningIR) -> list[dict[str, object]]:
    """只读投影：给 M4 faction graph 用的派生边（Planning relation 才是 truth）。"""

    return [{"edge_id": relation.relation_id, "kind": relation.relation_type,
             "source_id": relation.from_faction_id, "target_id": relation.to_faction_id,
             "label": relation.state, "symmetric": relation.symmetric,
             "public": relation.public, "non_authoritative": True,
             "source_planning_ids": [relation.relation_id]}
            for relation in plan.faction_relations]


def pressure_report(plan: StoryPlanningIR, target_id: str) -> list[dict[str, object]]:
    """只读：谁能对某个目标施压（M4 查询 + 自主行动 + 势力关系）。"""

    rows = faction_pressure_candidates(plan, target_id)
    for action in plan.autonomous_actions:
        if target_id in action.target_refs or action.location_ref == target_id:
            rows.append({"faction_id": action.actor_ref, "target_id": target_id,
                         "reasons": [f"autonomous_action:{action.action_id}"],
                         "goal": action.goal, "red_line": "",
                         "non_authoritative": True})
    for relation in plan.faction_relations:
        if target_id in (relation.from_faction_id, relation.to_faction_id) \
                and relation.relation_type in ("hostility", "competition", "influence"):
            other = (relation.to_faction_id if relation.from_faction_id == target_id
                     else relation.from_faction_id)
            rows.append({"faction_id": other, "target_id": target_id,
                         "reasons": [f"faction_relation:{relation.relation_type}"],
                         "goal": "", "red_line": "", "non_authoritative": True})
    return sorted(rows, key=lambda row: (row["faction_id"], row["reasons"]))


__all__ = [
    "analyze_autonomous_actions",
    "analyze_faction_relations",
    "faction_relation_edges",
    "pressure_report",
    "stage_trigger_node",
]
