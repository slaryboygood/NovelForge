"""M5：RewardPlan / RewardEvent 与 RewardCadenceAnalyzer。

目标：回答长篇最常见的两个商业问题——"长期没有兑现"与"每次都是小兑现导致失效"。

硬边界：

- magnitude 只用 ordinal level（minor / medium / major / climax），**不用"爽点=87"**；
- Core 不写"每 N 章必须爽一次"这类固定阈值：所有节奏判断都用**相对量**
  （时间线跨度比例 / 相邻间隔分位数），Genre Template 以后可以提供推荐阈值；
- 只输出 findings，不写 Canon / StoryState。
"""

from __future__ import annotations

from .enums import REWARD_MAGNITUDE_ORDER
from .findings import AnalysisReport, PlanningFinding, add_finding
from .models import RewardEvent, StoryPlanningIR
from .ordering import node_sequence_order, order_of, timeline_entries


def reward_events(plan: StoryPlanningIR) -> list[RewardEvent]:
    return [event for plan_row in plan.reward_plans for event in plan_row.events]


def analyze_reward_cadence(plan: StoryPlanningIR, *, revision_id: str = "",
                           drought_tolerance: float | None = None) -> AnalysisReport:
    report = AnalysisReport(novel_id=plan.novel_id, planning_id=plan.planning_id,
                            revision_id=revision_id)
    findings: list[PlanningFinding] = []
    events = reward_events(plan)
    if not plan.reward_plans:
        # 该题材 / 该阶段没有使用 reward domain：不是错误，也不产出节奏 findings
        return report
    node_ids = {item.node_id for item in plan.plot_nodes}
    foreshadows = {item.foreshadow_id: item for item in plan.foreshadow_plans}
    for event in events:
        if event.trigger_node_id and event.trigger_node_id not in node_ids:
            add_finding(findings, "REWARD_TRIGGER_UNKNOWN", "ERROR", "reward",
                        event.reward_id, "回报触发节点不是已知 PlotNode",
                        related=(event.trigger_node_id,))
        if event.payoff_ref and event.payoff_ref not in node_ids \
                and event.payoff_ref not in foreshadows:
            add_finding(findings, "REWARD_PAYOFF_REF_UNKNOWN", "ERROR", "reward",
                        event.reward_id, "回报的 payoff_ref 既不是 PlotNode 也不是伏笔",
                        related=(event.payoff_ref,))
        if REWARD_MAGNITUDE_ORDER[event.magnitude] >= REWARD_MAGNITUDE_ORDER["major"]:
            setup = bool(event.payoff_ref) or bool(event.delayed) or bool(event.cost_ref) \
                or bool(event.description)
            if not setup:
                add_finding(findings, "MAJOR_REWARD_WITHOUT_SETUP", "WARNING", "reward",
                            event.reward_id, "重大回报没有任何铺垫 / 代价 / 延迟标记")
        if not event.cost_ref and not event.delayed:
            add_finding(findings, "REWARD_WITHOUT_COST_OR_PRESSURE", "WARNING", "reward",
                        event.reward_id, "回报既没有代价也没有延迟（缺少压力）")
    ordered = sorted([(order_of(plan, event.trigger_node_id), event) for event in events],
                     key=lambda row: (row[0] is None, row[0] or 0))
    ordered = [(order, event) for order, event in ordered if order is not None]
    spans = [entry.sequence_order for entry in timeline_entries(plan)]
    span = (max(spans) - min(spans)) if spans else 0
    if spans and ordered:
        span_min, span_max = min(spans), max(spans)
        orders_only = [order for order, _ in ordered]
        gaps = [orders_only[index + 1] - orders_only[index]
                for index in range(len(orders_only) - 1)]
        head = orders_only[0] - span_min
        tail = span_max - orders_only[-1]
        tolerance = drought_tolerance if drought_tolerance is not None \
            else max(2.0, 2.0 * _median(gaps))
        for index, gap in enumerate(gaps):
            if gap > tolerance:
                add_finding(findings, "REWARD_LONG_DROUGHT", "WARNING", "reward",
                            ordered[index + 1][1].reward_id,
                            "相邻回报之间间隔过长（相对判断，非固定章数）",
                            gap=gap, tolerance=tolerance)
        if head > tolerance:
            add_finding(findings, "REWARD_LONG_DROUGHT", "WARNING", "reward",
                        ordered[0][1].reward_id, "开场很久之后才有第一个回报",
                        gap=head, tolerance=tolerance)
        if tail > tolerance:
            add_finding(findings, "REWARD_LONG_DROUGHT", "WARNING", "reward",
                        ordered[-1][1].reward_id, "最后的回报之后长期没有兑现",
                        gap=tail, tolerance=tolerance)
    elif span > 0 and not ordered:
        add_finding(findings, "REWARD_DROUGHT", "WARNING", "reward", plan.planning_id,
                    "整份规划没有任何回报事件")
    by_node: dict[str, list[RewardEvent]] = {}
    for order, event in ordered:
        if event.trigger_node_id:
            by_node.setdefault(event.trigger_node_id, []).append(event)
    for node_id, rows in sorted(by_node.items()):
        if len(rows) > 1:
            add_finding(findings, "REWARD_CLUSTERING", "WARNING", "reward", node_id,
                        "同一个节点上堆叠了多个回报",
                        related=tuple(row.reward_id for row in rows))
    consecutive: list[str] = []
    for _, event in ordered:
        if consecutive and consecutive[-1] == event.reward_type:
            consecutive.append(event.reward_type)
        else:
            consecutive = [event.reward_type]
        if len(consecutive) >= 3:
            add_finding(findings, "REPETITIVE_REWARD_TYPE", "WARNING", "reward",
                        event.reward_id, "连续多个回报是同一类型",
                        related=(event.reward_type,), streak=len(consecutive))
            consecutive = []
    for volume in plan.volumes:
        if not volume.climax_node_id:
            continue
        if not any(event.trigger_node_id == volume.climax_node_id for _, event in ordered):
            add_finding(findings, "CLIMAX_REWARD_MISSING", "WARNING", "reward",
                        volume.volume_id, "卷高潮节点没有任何回报事件",
                        related=(volume.climax_node_id,))
    report.findings.extend(findings)
    return report


def reward_cadence_rows(plan: StoryPlanningIR) -> list[dict[str, object]]:
    """只读：按 timeline 顺序列出回报（供 M6 / M14 使用）。"""

    orders = node_sequence_order(plan)
    rows = [{"reward_id": event.reward_id, "reward_type": event.reward_type,
             "magnitude": event.magnitude, "scope": event.scope,
             "trigger_node_id": event.trigger_node_id,
             "order": orders.get(event.trigger_node_id)}
            for event in reward_events(plan)]
    return sorted(rows, key=lambda row: (row["order"] is None, row["order"] or 0))


def _median(values: list[float]) -> float:
    if not values:
        return 0.0
    rows = sorted(values)
    middle = len(rows) // 2
    if len(rows) % 2:
        return float(rows[middle])
    return (rows[middle - 1] + rows[middle]) / 2.0


__all__ = ["analyze_reward_cadence", "reward_cadence_rows", "reward_events"]
