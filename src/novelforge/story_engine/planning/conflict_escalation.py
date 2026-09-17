"""M6：ConflictEscalationChain 分析 —— 冲突升级必须"有理由、有结构支撑"。

规则（§18 / §19）：

- 每进入下一阶段，至少改变一个维度（stakes / constraint / resource / information /
  relationship cost / faction involvement / location scope / irreversibility /
  time pressure / authority / consequence），否则报
  `CONFLICT_ESCALATION_WITHOUT_CAUSAL_CHANGE`（WARNING；`strict=True` 时 ERROR）；
- 阶段必须引用已有压力 / 资源 / 势力关系 / 自主行动 / 需求，不能是凭空的新事件，
  否则报 `CONFLICT_ESCALATION_UNSUPPORTED`（WARNING）；
- scope 只能前进或保持，不能回退（`CONFLICT_SCOPE_REGRESSION`，WARNING）；
- 不要求所有冲突走满 local → arc → volume → macro（§17）。
"""

from __future__ import annotations

from .enums import ConflictScope
from .findings import AnalysisReport, PlanningFinding, add_finding
from .models import StoryPlanningIR
from .requirements import validate_requirements

SCOPE_ORDER: dict[str, int] = {"local": 0, "arc": 1, "volume": 2, "macro": 3, "custom": -1}


def analyze_conflict_chains(plan: StoryPlanningIR, *, revision_id: str = "",
                            strict: bool = False) -> AnalysisReport:
    report = AnalysisReport(novel_id=plan.novel_id, planning_id=plan.planning_id,
                            revision_id=revision_id)
    findings: list[PlanningFinding] = []
    node_ids = {item.node_id for item in plan.plot_nodes}
    known_pressures = {ref.requirement_id for group in plan.requirement_groups()
                       for ref in group.requirements}
    resource_ids = {item.identity() for item in plan.resource_plans}
    relation_ids = {item.relation_id for item in plan.faction_relations}
    action_ids = {item.action_id for item in plan.autonomous_actions}
    for chain in plan.conflict_chains:
        seen_stages: dict[str, str] = {}
        previous_scope: int | None = None
        previous_stage_id = ""
        for index, stage in enumerate(chain.stages):
            path = f"conflict_chains[{chain.conflict_id}].stages[{stage.stage_id}]"
            if stage.stage_id in seen_stages:
                add_finding(findings, "CONFLICT_CHAIN_DUPLICATE_STAGE", "ERROR", "conflict",
                            stage.stage_id, "同一冲突链里出现重复阶段 ID",
                            related=(seen_stages[stage.stage_id],))
            seen_stages[stage.stage_id] = stage.stage_id
            if index > 0 and stage.previous_stage_id \
                    and stage.previous_stage_id != previous_stage_id:
                add_finding(findings, "CONFLICT_CHAIN_ORDER", "ERROR", "conflict",
                            stage.stage_id, "previous_stage_id 与实际顺序不一致",
                            related=(stage.previous_stage_id, previous_stage_id))
            previous_stage_id = stage.stage_id
            if stage.trigger_node_id and stage.trigger_node_id not in node_ids:
                add_finding(findings, "CONFLICT_STAGE_TRIGGER_UNKNOWN", "ERROR", "conflict",
                            stage.stage_id, "冲突阶段触发节点不是已知 PlotNode",
                            related=(stage.trigger_node_id,))
            for actor in stage.actor_refs:
                if actor not in {item.character_id for item in plan.characters} \
                        and actor not in {item.faction_id for item in plan.factions}:
                    add_finding(findings, "CONFLICT_STAGE_ACTOR_UNKNOWN", "ERROR", "conflict",
                                stage.stage_id, "冲突阶段行动者不是已知人物 / 势力",
                                related=(actor,))
            for location in stage.location_refs:
                if location not in {item.location_id for item in plan.locations}:
                    add_finding(findings, "CONFLICT_STAGE_LOCATION_UNKNOWN", "ERROR",
                                "conflict", stage.stage_id,
                                "冲突阶段地点不存在", related=(location,))
            for item in stage.resource_refs:
                if item not in resource_ids and not item.startswith(("RFLOW_", "RPLAN_")):
                    add_finding(findings, "CONFLICT_STAGE_RESOURCE_UNKNOWN", "ERROR",
                                "conflict", stage.stage_id,
                                "冲突阶段引用了未知资源", related=(item,))
            for item in stage.faction_relation_refs:
                if item not in relation_ids:
                    add_finding(findings, "CONFLICT_STAGE_RELATION_UNKNOWN", "ERROR",
                                "conflict", stage.stage_id,
                                "冲突阶段引用了未知势力关系", related=(item,))
            for item in stage.autonomous_action_refs:
                if item not in action_ids:
                    add_finding(findings, "CONFLICT_STAGE_ACTION_UNKNOWN", "ERROR",
                                "conflict", stage.stage_id,
                                "冲突阶段引用了未知自主行动", related=(item,))
            for item in stage.pressure_refs:
                if item not in known_pressures and not item.startswith(("PRESS_", "REQ_")):
                    add_finding(findings, "CONFLICT_STAGE_PRESSURE_UNKNOWN", "WARNING",
                                "conflict", stage.stage_id,
                                "冲突阶段引用的压力不在 requirement / 压力清单里",
                                related=(item,))
            scope = SCOPE_ORDER.get(stage.scope, -1)
            if previous_scope is not None and scope >= 0 and scope < previous_scope:
                add_finding(findings, "CONFLICT_SCOPE_REGRESSION", "WARNING", "conflict",
                            stage.stage_id, "冲突 scope 比上一阶段更小",
                            related=(chain.conflict_id,))
            if scope >= 0:
                previous_scope = scope
            if index > 0:
                signals = stage.escalation_signals()
                if not signals:
                    add_finding(findings, "CONFLICT_ESCALATION_WITHOUT_CAUSAL_CHANGE",
                                "ERROR" if strict else "WARNING", "conflict", stage.stage_id,
                                "升级阶段没有改变任何结构化维度（只是变得更强）",
                                related=(chain.conflict_id,), stage_scope=stage.scope)
                supported = bool(stage.pressure_refs or stage.resource_refs
                                 or stage.faction_relation_refs
                                 or stage.autonomous_action_refs or stage.requirement_refs)
                if not supported:
                    add_finding(findings, "CONFLICT_ESCALATION_UNSUPPORTED",
                                "ERROR" if strict else "WARNING", "conflict", stage.stage_id,
                                "升级阶段没有引用任何已有压力 / 资源 / 势力关系作为支撑",
                                related=(chain.conflict_id,))
            if stage.resolution_requirement is not None:
                known_pressures |= {ref.requirement_id
                                    for ref in stage.resolution_requirement.requirements}
        for node_id in chain.related_node_ids:
            if node_id not in node_ids:
                add_finding(findings, "CONFLICT_RELATED_NODE_UNKNOWN", "ERROR", "conflict",
                            chain.conflict_id, "冲突链引用不存在的 PlotNode",
                            related=(node_id,))
    report.findings.extend(findings)
    report.extend(validate_requirements(plan, revision_id=revision_id).findings)
    return report


def escalation_summary(plan: StoryPlanningIR) -> list[dict[str, object]]:
    """只读：每条冲突链的阶段 scope / signals（供 M7 / M14 使用）。"""

    rows: list[dict[str, object]] = []
    for chain in plan.conflict_chains:
        rows.append({
            "conflict_id": chain.conflict_id, "title": chain.title,
            "stages": [{"stage_id": stage.stage_id, "scope": stage.scope,
                        "trigger_node_id": stage.trigger_node_id,
                        "signals": stage.escalation_signals()} for stage in chain.stages]})
    return rows


__all__ = ["SCOPE_ORDER", "analyze_conflict_chains", "escalation_summary"]
