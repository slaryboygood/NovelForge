"""M5：Progression / Information / Foreshadow 的长期一致性分析。

三个 analyzer 都只输出 findings，不改任何 truth：

- `analyze_progression`：里程碑顺序、前置、代价、cap、plateau / jump / regression、重复升级；
- `analyze_information`：揭示顺序、持有者一致性、reveal before plant、payoff before reveal、
  false belief、knowledge leak；
- `analyze_foreshadow`：reveal without plant、payoff without reveal、重复 payoff、
  长期无动作、过早回收、过密提示。

所有节奏类阈值都是**相对判断**（相对时间线跨度 / 相邻间隔），M5 Core 不写"每 N 章"这类固定阈值。
"""

from __future__ import annotations

from .findings import AnalysisReport, PlanningFinding, add_finding
from .models import StoryPlanningIR
from .ordering import node_sequence_order, order_of, timeline_entries


def analyze_progression(plan: StoryPlanningIR, *, revision_id: str = "") -> AnalysisReport:
    report = AnalysisReport(novel_id=plan.novel_id, planning_id=plan.planning_id,
                            revision_id=revision_id)
    findings: list[PlanningFinding] = []
    node_ids = {item.node_id for item in plan.plot_nodes}
    orders = node_sequence_order(plan)
    for track in plan.progression_tracks:
        seen_nodes: dict[str, str] = {}
        previous_order: int | None = None
        previous_label = ""
        for milestone in track.milestones:
            if milestone.node_id and milestone.node_id not in node_ids:
                add_finding(findings, "PROGRESSION_NODE_UNKNOWN", "ERROR", "progression",
                            milestone.milestone_id, "里程碑引用不存在的 PlotNode",
                            related=(milestone.node_id,))
            if milestone.node_id:
                if milestone.node_id in seen_nodes:
                    add_finding(findings, "PROGRESSION_DUPLICATE_UPGRADE", "ERROR",
                                "progression", track.track_id,
                                "同一个节点被两个里程碑重复升级",
                                related=(seen_nodes[milestone.node_id],
                                         milestone.milestone_id))
                seen_nodes[milestone.node_id] = milestone.milestone_id
            order = orders.get(milestone.node_id) if milestone.node_id else None
            if order is not None and previous_order is not None and order < previous_order:
                add_finding(findings, "PROGRESSION_ORDER_REGRESSION", "WARNING", "progression",
                            milestone.milestone_id,
                            "里程碑的 timeline 顺序早于前一个里程碑（可能出现回退）",
                            related=(previous_label,), order=order,
                            previous_order=previous_order)
            if order is not None:
                previous_order = order
            previous_label = milestone.label or milestone.milestone_id
            if not milestone.requirement and not milestone.cost:
                severity = "WARNING"
                add_finding(findings, "PROGRESSION_MAJOR_WITHOUT_COST", severity,
                            "progression", milestone.milestone_id,
                            "里程碑既没有条件也没有代价（成长不能无成本）")
            if milestone.cap and not milestone.unlock:
                add_finding(findings, "PROGRESSION_CAP_WITHOUT_UNLOCK", "INFO", "progression",
                            milestone.milestone_id, "声明了 cap 但没有说明 unlock 收益")
        if len(track.milestones) >= 2 and all(not item.cost and not item.requirement
                                               for item in track.milestones):
            add_finding(findings, "PROGRESSION_PLATEAU", "WARNING", "progression",
                        track.track_id, "整条成长轨道没有任何条件或代价（成长停滞风险）")
        first = track.milestones[0] if track.milestones else None
        if first is not None and track.start_state and first.requirement \
                and len(track.milestones) > 2 and not track.requirements:
            add_finding(findings, "PROGRESSION_JUMP", "WARNING", "progression",
                        track.track_id, "首个里程碑就有额外要求，但轨道没有声明整体前置")
    report.findings.extend(findings)
    return report


def analyze_information(plan: StoryPlanningIR, *, revision_id: str = "") -> AnalysisReport:
    report = AnalysisReport(novel_id=plan.novel_id, planning_id=plan.planning_id,
                            revision_id=revision_id)
    findings: list[PlanningFinding] = []
    node_ids = {item.node_id for item in plan.plot_nodes}
    character_ids = {item.character_id for item in plan.characters}
    faction_ids = {item.faction_id for item in plan.factions}
    entity_refs = {item.entity_ref for item in plan.characters if item.entity_ref}
    orders = node_sequence_order(plan)
    for arc in plan.information_arcs:
        for move in arc.moves:
            if move.node_id and move.node_id not in node_ids:
                add_finding(findings, "INFORMATION_NODE_UNKNOWN", "ERROR", "information",
                            move.move_id, "信息动作引用不存在的 PlotNode",
                            related=(move.node_id,))
            for holder in move.holder_ids:
                if holder in character_ids or holder in faction_ids or holder in entity_refs:
                    continue
                add_finding(findings, "INFORMATION_HOLDER_UNKNOWN", "ERROR", "information",
                            move.move_id, "信息持有者不是已知人物 / 势力 / 实体",
                            related=(holder,))
        for truth in arc.truths:
            moves = [move for move in arc.moves if move.truth_id == truth.truth_id]
            by_type = {move.move_type: move for move in moves}
            plant_order = orders.get(by_type["plant"].node_id) \
                if "plant" in by_type else None
            reveal_order = orders.get(by_type["reveal"].node_id) \
                if "reveal" in by_type else None
            payoff_order = orders.get(by_type["payoff"].node_id) \
                if "payoff" in by_type else None
            if reveal_order is not None and plant_order is not None \
                    and reveal_order < plant_order:
                add_finding(findings, "INFORMATION_REVEAL_BEFORE_PLANT", "ERROR",
                            "information", truth.truth_id,
                            "揭示早于埋设（timeline 顺序倒置）",
                            related=(by_type["plant"].move_id, by_type["reveal"].move_id))
            if reveal_order is not None and plant_order is None:
                add_finding(findings, "INFORMATION_REVEAL_WITHOUT_PLANT", "ERROR",
                            "information", truth.truth_id, "有揭示动作但没有埋设动作",
                            related=(by_type["reveal"].move_id,))
            if payoff_order is not None and reveal_order is None:
                add_finding(findings, "INFORMATION_PAYOFF_BEFORE_REVEAL", "ERROR",
                            "information", truth.truth_id, "回收之前没有揭示",
                            related=(by_type["payoff"].move_id,))
            if payoff_order is not None and reveal_order is not None \
                    and payoff_order < reveal_order:
                add_finding(findings, "INFORMATION_PAYOFF_BEFORE_REVEAL", "ERROR",
                            "information", truth.truth_id, "回收早于揭示（timeline 顺序倒置）")
            belief_order = orders.get(by_type["false_belief"].node_id) \
                if "false_belief" in by_type else None
            overturned = "reveal" in by_type and (
                reveal_order is None or belief_order is None
                or reveal_order >= belief_order)
            if "false_belief" in by_type and not overturned:
                add_finding(findings, "INFORMATION_FALSE_BELIEF_WITHOUT_REVEAL", "WARNING",
                            "information", truth.truth_id,
                            "建立了错误信念但没有推翻它的揭示动作",
                            related=(by_type["false_belief"].move_id,))
            holders = set(truth.character_knows) | set(truth.faction_knows)
            if truth.protagonist_knows:
                holders.add("ENTITY_PROTAGONIST")
            if holders and not moves:
                add_finding(findings, "INFORMATION_KNOWLEDGE_LEAK", "ERROR", "information",
                            truth.truth_id, "声明了知情者，但没有任何信息动作解释他们如何知道",
                            related=tuple(sorted(holders)))
            if truth.reader_knows and "reveal" not in by_type:
                add_finding(findings, "INFORMATION_READER_WITHOUT_REVEAL", "WARNING",
                            "information", truth.truth_id,
                            "读者已经知道，但没有计划中的揭示动作")
    report.findings.extend(findings)
    return report


def analyze_foreshadow(plan: StoryPlanningIR, *, revision_id: str = "",
                       require_reveal_before_payoff: bool = False) -> AnalysisReport:
    """`require_reveal_before_payoff=False` 时，"先回收后揭示"只算 WARNING（文学选择）。"""

    report = AnalysisReport(novel_id=plan.novel_id, planning_id=plan.planning_id,
                            revision_id=revision_id)
    findings: list[PlanningFinding] = []
    node_ids = {item.node_id for item in plan.plot_nodes}
    orders = node_sequence_order(plan)
    spans = [entry.sequence_order for entry in timeline_entries(plan)]
    span = (max(spans) - min(spans)) if spans else 0
    for foreshadow in plan.foreshadow_plans:
        by_node: dict[str, list[str]] = {}
        moves = {move.move_type: move for move in foreshadow.moves}
        for move in foreshadow.moves:
            if move.node_id and move.node_id not in node_ids:
                add_finding(findings, "FORESHADOW_NODE_UNKNOWN", "ERROR", "foreshadow",
                            move.move_id, "伏笔动作引用不存在的 PlotNode",
                            related=(move.node_id,))
            if move.node_id:
                by_node.setdefault(move.node_id, []).append(move.move_id)
        plant = moves.get("plant")
        reveal = moves.get("reveal")
        payoff = moves.get("payoff")
        if reveal and not plant:
            add_finding(findings, "FORESHADOW_REVEAL_WITHOUT_PLANT", "ERROR", "foreshadow",
                        foreshadow.foreshadow_id, "有揭示但没有埋设")
        if payoff and not reveal:
            add_finding(findings, "FORESHADOW_PAYOFF_WITHOUT_REVEAL",
                        "ERROR" if require_reveal_before_payoff else "WARNING",
                        "foreshadow", foreshadow.foreshadow_id,
                        "有回收但没有揭示动作",
                        require_reveal_before_payoff=require_reveal_before_payoff)
        if len([move for move in foreshadow.moves if move.move_type == "payoff"]) > 1:
            add_finding(findings, "FORESHADOW_DUPLICATE_PAYOFF", "ERROR", "foreshadow",
                        foreshadow.foreshadow_id, "同一伏笔出现多次 payoff")
        plant_order = orders.get(plant.node_id) if plant and plant.node_id else None
        payoff_order = orders.get(payoff.node_id) if payoff and payoff.node_id else None
        if plant_order is not None and payoff_order is not None:
            gap = payoff_order - plant_order
            if span >= 4 and gap >= 0.5 * span:
                add_finding(findings, "FORESHADOW_LONG_DORMANT", "WARNING", "foreshadow",
                            foreshadow.foreshadow_id,
                            "从埋设到回收跨越了大部分时间线（长期无动作风险）",
                            gap=gap, span=span)
            if gap <= 1 and "reinforce" not in moves and "misdirect" not in moves:
                add_finding(findings, "FORESHADOW_EARLY_PAYOFF", "WARNING", "foreshadow",
                            foreshadow.foreshadow_id,
                            "埋设后立刻回收，没有任何强化 / 误导（过早回收风险）")
        for node_id, move_ids in sorted(by_node.items()):
            if len(move_ids) >= 3:
                add_finding(findings, "FORESHADOW_DENSE_HINTS", "WARNING", "foreshadow",
                            foreshadow.foreshadow_id, "同一节点上堆叠了多个伏笔动作",
                            related=tuple(sorted(move_ids)))
        if plant and not foreshadow.intended_payoff and not payoff:
            add_finding(findings, "FORESHADOW_WITHOUT_PAYOFF", "WARNING", "foreshadow",
                        foreshadow.foreshadow_id, "没有预期回收，也没有 payoff 动作")
    report.findings.extend(findings)
    return report


__all__ = ["analyze_foreshadow", "analyze_information", "analyze_progression"]
