"""M5：Equipment / Item Lifecycle —— 装备与物品的计划生命周期。

`EquipmentPlan` 表达 planned lifecycle（planned / acquired / equipped / damaged / repaired /
upgraded / transferred / lost / consumed），**不是 happened state**；真实持有情况属于
StoryState / Canon。
"""

from __future__ import annotations

from .findings import AnalysisReport, PlanningFinding, add_finding
from .models import StoryPlanningIR
from .ordering import order_of


def analyze_equipment(plan: StoryPlanningIR, *, revision_id: str = "") -> AnalysisReport:
    report = AnalysisReport(novel_id=plan.novel_id, planning_id=plan.planning_id,
                            revision_id=revision_id)
    findings: list[PlanningFinding] = []
    node_ids = {item.node_id for item in plan.plot_nodes}
    for equipment in plan.equipment_plans:
        for node_id in equipment.nodes():
            if node_id not in node_ids:
                add_finding(findings, "EQUIPMENT_UNKNOWN_NODE", "ERROR", "equipment",
                            equipment.equipment_id, "生命周期节点不是已知 PlotNode",
                            related=(node_id,))
        acquisition = order_of(plan, equipment.acquisition_node)
        for node_id in equipment.upgrade_nodes:
            order = order_of(plan, node_id)
            if acquisition is None:
                add_finding(findings, "EQUIPMENT_UPGRADE_BEFORE_ACQUIRE", "ERROR", "equipment",
                            equipment.equipment_id, "没有获取节点的升级计划",
                            related=(node_id,))
            elif order is not None and order < acquisition:
                add_finding(findings, "EQUIPMENT_UPGRADE_BEFORE_ACQUIRE", "ERROR", "equipment",
                            equipment.equipment_id, "升级早于获取（timeline 顺序倒置）",
                            related=(node_id, equipment.acquisition_node))
        damage_orders = [order_of(plan, node_id) for node_id in equipment.damage_nodes]
        damage_orders = [value for value in damage_orders if value is not None]
        for node_id in equipment.repair_nodes:
            order = order_of(plan, node_id)
            if not damage_orders:
                add_finding(findings, "EQUIPMENT_REPAIR_BEFORE_DAMAGE", "ERROR", "equipment",
                            equipment.equipment_id, "维修计划没有任何损坏节点",
                            related=(node_id,))
            elif order is not None and order < min(damage_orders):
                add_finding(findings, "EQUIPMENT_REPAIR_BEFORE_DAMAGE", "ERROR", "equipment",
                            equipment.equipment_id, "维修早于损坏（timeline 顺序倒置）",
                            related=(node_id,))
        loss = order_of(plan, equipment.loss_node)
        if loss is not None:
            reuse = [node_id for node_id in equipment.upgrade_nodes + equipment.repair_nodes
                     + equipment.transfer_nodes
                     if (order_of(plan, node_id) or 0) > loss]
            if reuse or (equipment.consume_node
                         and (order_of(plan, equipment.consume_node) or 0) > loss):
                add_finding(findings, "EQUIPMENT_USE_AFTER_LOSS", "ERROR", "equipment",
                            equipment.equipment_id, "丢失之后仍然被使用 / 升级 / 转移",
                            related=tuple(reuse + [equipment.loss_node]))
        if equipment.transfer_nodes and not equipment.owner_ref:
            add_finding(findings, "EQUIPMENT_TRANSFER_WITHOUT_OWNERSHIP", "ERROR", "equipment",
                        equipment.equipment_id, "有转移节点但没有 owner_ref",
                        related=tuple(equipment.transfer_nodes))
        if equipment.consumable and equipment.consume_node:
            after = [node_id for node_id in equipment.upgrade_nodes + equipment.transfer_nodes
                     if (order_of(plan, node_id) or 0)
                     > (order_of(plan, equipment.consume_node) or 0)]
            if after:
                add_finding(findings, "EQUIPMENT_CONSUME_THEN_REUSE", "ERROR", "equipment",
                            equipment.equipment_id, "消耗品在消耗之后仍被使用",
                            related=tuple(after))
        if not equipment.owner_ref and (equipment.acquisition_node or equipment.transfer_nodes):
            add_finding(findings, "EQUIPMENT_NO_OWNER", "WARNING", "equipment",
                        equipment.equipment_id, "装备计划没有 owner_ref")
    # 唯一物品 / 同一物品的归属冲突
    by_ref: dict[str, list] = {}
    for equipment in plan.equipment_plans:
        key = equipment.equipment_ref or equipment.equipment_id
        by_ref.setdefault(key, []).append(equipment)
    for key, rows in sorted(by_ref.items()):
        owners = {row.owner_ref for row in rows if row.owner_ref}
        if len(owners) > 1:
            add_finding(findings, "EQUIPMENT_DOUBLE_OWNERSHIP", "ERROR", "equipment",
                        key, "同一装备被计划给多个 owner",
                        related=tuple(sorted(owners)))
        if len(rows) > 1 and all(row.unique for row in rows):
            add_finding(findings, "EQUIPMENT_DUPLICATE_UNIQUE", "ERROR", "equipment",
                        key, "唯一物品出现重复计划",
                        related=tuple(row.equipment_id for row in rows))
    report.findings.extend(findings)
    return report


def equipment_lifecycle_order(equipment, plan: StoryPlanningIR) -> list[dict[str, object]]:
    """只读：按 timeline 顺序给出该装备的计划生命周期（供 M6 / M14 使用）。"""

    rows = [{"state": step.state, "node_id": step.node_id,
             "order": order_of(plan, step.node_id), "detail": step.detail}
            for step in equipment.lifecycle]
    if not rows:
        for state, node_id in (("acquired", equipment.acquisition_node),
                               ("damaged", equipment.damage_nodes[0] if equipment.damage_nodes else ""),
                               ("upgraded", equipment.upgrade_nodes[0] if equipment.upgrade_nodes else ""),
                               ("lost", equipment.loss_node),
                               ("consumed", equipment.consume_node)):
            if node_id:
                rows.append({"state": state, "node_id": node_id,
                             "order": order_of(plan, node_id), "detail": ""})
    return sorted(rows, key=lambda row: (row["order"] is None, row["order"] or 0))


__all__ = ["analyze_equipment", "equipment_lifecycle_order"]
