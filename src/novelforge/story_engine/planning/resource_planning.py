"""M5：ResourceLedger / ResourceFlow —— 规划层资源守恒分析。

边界：

- `ResourcePlan` 只描述"这种资源怎么运作"（单位、稀缺度、可再生、存储上限）；
- `ResourceFlow` 描述计划中的流动（produce / acquire / consume / store / transfer / lose /
  destroy / recover）；
- `ResourceLedger` 是**派生分析投影**（planned_balance / deficit / surplus /
  capacity_violation / impossible_consumption / 重复不可逆消耗），不是第二 truth source；
- 真实库存永远在 StoryState.ResourceStock：本模块不读也不写 StoryState。
"""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from novelforge.models import StrictModel

from .findings import AnalysisReport, PlanningFinding, add_finding
from .models import StoryPlanningIR
from .ordering import order_of

PRODUCE_TYPES = ("produce", "acquire", "recover")
CONSUME_TYPES = ("consume", "lose", "destroy")


class ResourceLedgerRow(StrictModel):
    resource_id: str = Field(default="", max_length=160)
    unit_id: str = Field(default="", max_length=64)
    planned_balance: float = 0.0
    produced: float = 0.0
    consumed: float = 0.0
    transferred_in: float = 0.0
    transferred_out: float = 0.0
    stored: float = 0.0
    deficit: float = 0.0
    surplus: float = 0.0
    capacity_violation: bool = False
    impossible_consumption: bool = False
    duplicate_irreversible: list[str] = Field(default_factory=list)
    planning_only: bool = False


class ResourceLedger(StrictModel):
    """派生 projection：read_only + 不写任何 truth。"""

    novel_id: str = Field(default="", max_length=96)
    revision_id: str = Field(default="", max_length=64)
    rows: list[ResourceLedgerRow] = Field(default_factory=list)
    read_only: Literal[True] = True
    non_authoritative: Literal[True] = True

    def row(self, resource_id: str) -> ResourceLedgerRow | None:
        return next((item for item in self.rows if item.resource_id == resource_id), None)


def build_resource_ledger(plan: StoryPlanningIR, *, revision_id: str = "") -> ResourceLedger:
    plans = {item.identity(): item for item in plan.resource_plans}
    rows: dict[str, ResourceLedgerRow] = {}
    for identity, resource_plan in plans.items():
        rows[identity] = ResourceLedgerRow(
            resource_id=identity, unit_id=resource_plan.unit_id,
            planning_only=resource_plan.is_planning_only())
    for flow in plan.resource_flows:
        identity = flow.identity()
        row = rows.setdefault(identity, ResourceLedgerRow(
            resource_id=identity, unit_id=flow.unit_id,
            planning_only=not flow.resource_id))
        if flow.flow_type in PRODUCE_TYPES:
            row.produced += flow.amount
        elif flow.flow_type in CONSUME_TYPES:
            row.consumed += flow.amount
        elif flow.flow_type == "store":
            row.stored += flow.amount
        elif flow.flow_type == "transfer":
            row.transferred_out += flow.amount
            row.transferred_in += flow.amount
        if flow.irreversible and flow.flow_type in CONSUME_TYPES:
            row.duplicate_irreversible.append(flow.flow_id)
    for identity, row in rows.items():
        resource_plan = plans.get(identity)
        row.planned_balance = round(row.produced + row.transferred_in - row.consumed, 6)
        row.deficit = round(max(0.0, row.consumed - row.produced - row.transferred_in), 6)
        row.surplus = round(max(0.0, row.produced - row.consumed), 6)
        row.impossible_consumption = row.deficit > 0
        if resource_plan is not None and resource_plan.storage_limit is not None:
            row.capacity_violation = row.stored > resource_plan.storage_limit
    return ResourceLedger(novel_id=plan.novel_id, revision_id=revision_id,
                          rows=sorted(rows.values(), key=lambda item: item.resource_id))


def validate_resources(plan: StoryPlanningIR, *, revision_id: str = "") -> AnalysisReport:
    report = AnalysisReport(novel_id=plan.novel_id, planning_id=plan.planning_id,
                            revision_id=revision_id)
    findings: list[PlanningFinding] = []
    units = {item.unit_id: item for item in plan.unit_defs}
    plans = {item.identity(): item for item in plan.resource_plans}
    known_resources = set(plans)
    for resource_plan in plan.resource_plans:
        if resource_plan.unit_id and resource_plan.unit_id not in units:
            add_finding(findings, "RESOURCE_UNIT_UNKNOWN", "ERROR", "resource",
                        resource_plan.resource_plan_id,
                        "resource plan 引用了未定义的单位", related=(resource_plan.unit_id,))
    ledger = build_resource_ledger(plan, revision_id=revision_id)
    seen_consumption: dict[tuple[str, str], str] = {}
    for flow in plan.resource_flows:
        identity = flow.identity()
        if identity not in known_resources:
            add_finding(findings, "RESOURCE_UNKNOWN", "ERROR", "resource", flow.flow_id,
                        "flow 引用了没有 ResourcePlan 的资源", related=(identity,))
        resource_plan = plans.get(identity)
        expected_unit = (resource_plan.unit_id if resource_plan else "")
        if expected_unit and flow.unit_id and flow.unit_id != expected_unit:
            add_finding(findings, "RESOURCE_UNIT_MISMATCH", "ERROR", "resource", flow.flow_id,
                        "flow 的单位与 resource plan 不一致",
                        related=(flow.unit_id, expected_unit))
        if flow.unit_id and flow.unit_id not in units:
            add_finding(findings, "RESOURCE_UNIT_UNKNOWN", "ERROR", "resource", flow.flow_id,
                        "flow 引用了未定义的单位", related=(flow.unit_id,))
        if flow.trigger_node_id and flow.trigger_node_id not in {n.node_id
                                                                for n in plan.plot_nodes}:
            add_finding(findings, "RESOURCE_TRIGGER_UNKNOWN", "ERROR", "resource",
                        flow.flow_id, "flow 的触发节点不存在",
                        related=(flow.trigger_node_id,))
        if flow.flow_type in CONSUME_TYPES and flow.irreversible:
            key = (identity, flow.flow_id)
            seen_consumption[key] = flow.flow_id
    for row in ledger.rows:
        if len(row.duplicate_irreversible) > 1:
            add_finding(findings, "RESOURCE_DUPLICATE_IRREVERSIBLE", "ERROR", "resource",
                        row.resource_id, "同一资源出现多次不可逆消耗",
                        related=tuple(row.duplicate_irreversible),
                        count=len(row.duplicate_irreversible))
    for flow in plan.resource_flows:
        if flow.flow_type not in CONSUME_TYPES:
            continue
        identity = flow.identity()
        consume_order = order_of(plan, flow.trigger_node_id) if flow.trigger_node_id else None
        acquire_orders = [order_of(plan, item.trigger_node_id)
                          for item in plan.resource_flows
                          if item.identity() == identity and item.flow_type in PRODUCE_TYPES
                          and item.trigger_node_id]
        known_orders = [value for value in acquire_orders if value is not None]
        if consume_order is not None and known_orders and consume_order < max(known_orders):
            add_finding(findings, "RESOURCE_CONSUME_BEFORE_ACQUIRE", "ERROR", "resource",
                        flow.flow_id, "先消耗后获得（timeline 顺序倒置）",
                        related=(identity,), consume_order=consume_order,
                        acquire_order=max(known_orders))
    for resource_plan in plan.resource_plans:
        if not resource_plan.renewable:
            unbounded = [flow for flow in plan.resource_flows
                         if flow.identity() == resource_plan.identity()
                         and flow.flow_type in PRODUCE_TYPES
                         and flow.repeatability == "unbounded"]
            if unbounded:
                add_finding(findings, "RESOURCE_NONRENEWABLE_INFINITE", "ERROR", "resource",
                            resource_plan.resource_plan_id,
                            "不可再生资源出现 unbounded 产出",
                            related=tuple(flow.flow_id for flow in unbounded))
    for row in ledger.rows:
        if row.impossible_consumption:
            add_finding(findings, "RESOURCE_NEGATIVE_BALANCE", "ERROR", "resource",
                        row.resource_id, "计划消耗超过计划获得（planned deficit）",
                        deficit=row.deficit)
        if row.capacity_violation:
            add_finding(findings, "RESOURCE_STORAGE_OVERFLOW", "ERROR", "resource",
                        row.resource_id, "计划存储超过 storage_limit", stored=row.stored)
        if row.planning_only:
            add_finding(findings, "RESOURCE_PLANNING_ONLY_IDENTITY", "INFO", "resource",
                        row.resource_id,
                        "该资源尚未有 confirmed ResourceDefinition（planning-only）")
    report.findings.extend(findings)
    return report


__all__ = [
    "ResourceLedger",
    "ResourceLedgerRow",
    "build_resource_ledger",
    "validate_resources",
]
