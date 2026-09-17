"""M6：StorySpine 因果骨架分析（DAG 硬门 + requirement closure + arc anchors + coverage）。

StorySpine 是 PlotNode 之间的 causal DAG，不是章节顺序 / 卷目录 / beat ladder。
本模块只输出 findings 与 coverage report，不写任何 truth、不生成节点。
"""

from __future__ import annotations

from collections import deque
from typing import Iterable

from pydantic import Field

from novelforge.models import StrictModel

from .findings import AnalysisReport, PlanningFinding, add_finding
from .graphs import declared_access, entry_locations, reachable_locations
from .models import PlotNode, RequirementGroup, StoryPlanningIR
from .ordering import node_sequence_order, order_of
from .plot_pressure import PlotPressureInventory, build_plot_pressure_inventory
from .requirements import evaluate_requirements
from .resource_planning import build_resource_ledger


class StorySpineCoverageReport(StrictModel):
    """结构化覆盖统计（不给假精确总分）。"""

    revision_id: str = Field(default="", max_length=64)
    plot_node_count: int = 0
    must_happen_count: int = 0
    optional_count: int = 0
    root_count: int = 0
    terminal_count: int = 0
    open_pressure_count: int = 0
    blocked_pressure_count: int = 0
    scheduled_pressure_count: int = 0
    resolved_pressure_count: int = 0
    deferred_pressure_count: int = 0
    character_arc_coverage: int = 0
    relationship_arc_coverage: int = 0
    faction_arc_coverage: int = 0
    information_coverage: int = 0
    foreshadow_coverage: int = 0
    progression_coverage: int = 0
    reward_coverage: int = 0
    requirement_closure: int = 0
    requirement_total: int = 0
    conflict_escalation_coverage: int = 0
    unaddressed_pressures: list[str] = Field(default_factory=list)
    read_only: bool = True


# ---------------------------------------------------------------- graph helpers
def adjacency(plan: StoryPlanningIR) -> dict[str, set[str]]:
    rows: dict[str, set[str]] = {node.node_id: set() for node in plan.plot_nodes}
    if plan.spine is None:
        return rows
    for edge in plan.spine.edges:
        rows.setdefault(edge.from_node_id, set()).add(edge.to_node_id)
        rows.setdefault(edge.to_node_id, set())
    return rows


def reverse_adjacency(plan: StoryPlanningIR) -> dict[str, set[str]]:
    rows: dict[str, set[str]] = {node.node_id: set() for node in plan.plot_nodes}
    if plan.spine is None:
        return rows
    for edge in plan.spine.edges:
        rows.setdefault(edge.to_node_id, set()).add(edge.from_node_id)
        rows.setdefault(edge.from_node_id, set())
    return rows


def topological_order(plan: StoryPlanningIR) -> list[str]:
    """Kahn 拓扑排序；有环时返回已排序部分（环由 findings 报出）。"""

    graph = adjacency(plan)
    indegree = {node_id: 0 for node_id in graph}
    for targets in graph.values():
        for target in targets:
            indegree[target] = indegree.get(target, 0) + 1
    queue = deque(sorted(node_id for node_id, value in indegree.items() if value == 0))
    rows: list[str] = []
    while queue:
        current = queue.popleft()
        rows.append(current)
        for target in sorted(graph.get(current, ())):
            indegree[target] -= 1
            if indegree[target] == 0:
                queue.append(target)
    return rows


def upstream_of(plan: StoryPlanningIR, node_id: str) -> set[str]:
    reverse = reverse_adjacency(plan)
    seen: set[str] = set()
    queue = deque(sorted(reverse.get(node_id, ())))
    while queue:
        current = queue.popleft()
        if current in seen:
            continue
        seen.add(current)
        queue.extend(sorted(reverse.get(current, ())))
    return seen


def root_nodes(plan: StoryPlanningIR) -> list[str]:
    reverse = reverse_adjacency(plan)
    return sorted(node_id for node_id, sources in reverse.items() if not sources)


def terminal_nodes(plan: StoryPlanningIR) -> list[str]:
    graph = adjacency(plan)
    return sorted(node_id for node_id, targets in graph.items() if not targets)


def components(plan: StoryPlanningIR) -> list[list[str]]:
    graph = adjacency(plan)
    seen: set[str] = set()
    rows: list[list[str]] = []
    for node_id in sorted(graph):
        if node_id in seen:
            continue
        group: list[str] = []
        queue = deque([node_id])
        seen.add(node_id)
        while queue:
            current = queue.popleft()
            group.append(current)
            neighbours = graph.get(current, set()) | reverse_adjacency(plan).get(current, set())
            for neighbour in sorted(neighbours):
                if neighbour not in seen:
                    seen.add(neighbour)
                    queue.append(neighbour)
        rows.append(sorted(group))
    return rows


# ---------------------------------------------------------------- analysis
def analyze_story_spine(plan: StoryPlanningIR, *, revision_id: str = "",
                        known_entity_ids: tuple[str, ...] = (),
                        available_requirements: tuple[str, ...] = (),
                        inventory: PlotPressureInventory | None = None,
                        strict_conflict: bool = False) -> AnalysisReport:
    report = AnalysisReport(novel_id=plan.novel_id, planning_id=plan.planning_id,
                            revision_id=revision_id)
    findings: list[PlanningFinding] = []
    spine = plan.spine
    node_ids = {node.node_id for node in plan.plot_nodes}
    nodes_by_id = {node.node_id: node for node in plan.plot_nodes}
    if spine is None:
        add_finding(findings, "SPINE_MISSING", "WARNING", "spine", plan.planning_id,
                    "Planning IR 没有 StorySpine")
        report.findings.extend(findings)
        return report
    listed = set(spine.nodes)
    for node_id in spine.nodes:
        if node_id not in node_ids:
            add_finding(findings, "SPINE_DANGLING_NODE", "ERROR", "spine", node_id,
                        "spine 引用不存在的 PlotNode")
    edge_keys: set[tuple[str, str, str]] = set()
    for edge in spine.edges:
        for endpoint in (edge.from_node_id, edge.to_node_id):
            if endpoint not in listed:
                add_finding(findings, "SPINE_DANGLING_EDGE", "ERROR", "spine", endpoint,
                            "spine 边的端点不在 spine.nodes 里",
                            related=(edge.from_node_id, edge.to_node_id))
        if edge.from_node_id == edge.to_node_id:
            add_finding(findings, "SPINE_SELF_DEPENDENCY", "ERROR", "spine",
                        edge.from_node_id, "节点依赖自身")
        key = (edge.from_node_id, edge.to_node_id, edge.relation)
        if key in edge_keys:
            add_finding(findings, "SPINE_DUPLICATE_EDGE", "WARNING", "spine",
                        f"{edge.from_node_id}->{edge.to_node_id}",
                        "重复的 spine 边", related=(edge.relation,))
        edge_keys.add(key)
    order = topological_order(plan)
    if len(order) != len(adjacency(plan)):
        add_finding(findings, "SPINE_CYCLE", "ERROR", "spine", plan.planning_id,
                    "StorySpine 存在环（不是 DAG）")
    roots = root_nodes(plan)
    terminals = terminal_nodes(plan)
    if not roots:
        add_finding(findings, "SPINE_NO_ROOT", "ERROR", "spine", plan.planning_id,
                    "没有有效开端（root node）")
    if not terminals:
        add_finding(findings, "SPINE_NO_TERMINAL", "ERROR", "spine", plan.planning_id,
                    "没有有效终点方向（terminal node）")
    groups = components(plan)
    if len(groups) > 1:
        optional_only = all(
            all(nodes_by_id.get(node_id) is not None and nodes_by_id[node_id].optional
                for node_id in group)
            for group in groups[1:])
        if not optional_only:
            add_finding(findings, "SPINE_DISCONNECTED_SEGMENTS", "ERROR", "spine",
                        plan.planning_id, "存在多条互不相连的主线片段",
                        related=tuple(group[0] for group in groups))
    reachable_from_root: set[str] = set()
    can_reach_terminal: set[str] = set()
    graph = adjacency(plan)
    for root in roots:
        seen: set[str] = set()
        queue = deque([root])
        while queue:
            current = queue.popleft()
            if current in seen:
                continue
            seen.add(current)
            queue.extend(sorted(graph.get(current, ())))
        reachable_from_root |= seen
    reverse = reverse_adjacency(plan)
    for terminal in terminals:
        seen = set()
        queue = deque([terminal])
        while queue:
            current = queue.popleft()
            if current in seen:
                continue
            seen.add(current)
            queue.extend(sorted(reverse.get(current, ())))
        can_reach_terminal |= seen
    for node in plan.plot_nodes:
        if node.must_happen and node.node_id not in listed:
            add_finding(findings, "MUST_HAPPEN_NODE_OUTSIDE_SPINE", "ERROR", "spine",
                        node.node_id, "must_happen 节点没有进入 StorySpine")
            continue
        if node.must_happen and node.node_id not in reachable_from_root:
            add_finding(findings, "MUST_HAPPEN_NODE_OUTSIDE_SPINE", "ERROR", "spine",
                        node.node_id, "must_happen 节点不在 root → terminal 因果路径上")
        elif node.must_happen and node.node_id not in can_reach_terminal:
            add_finding(findings, "MUST_HAPPEN_NODE_OUTSIDE_SPINE", "ERROR", "spine",
                        node.node_id, "must_happen 节点无法到达任何 terminal 方向")
        elif node.node_id in listed and node.node_id not in reachable_from_root:
            severity = "WARNING" if node.optional else "ERROR"
            add_finding(findings, "ORPHAN_CRITICAL_NODE" if not node.optional
                        else "SPINE_ORPHAN_NODE", severity, "spine", node.node_id,
                        "节点不在任何 root → terminal 路径上")
        if node.importance == "core" and node.node_id not in listed:
            add_finding(findings, "ORPHAN_CRITICAL_NODE", "WARNING", "spine", node.node_id,
                        "core 节点没有进入 StorySpine")
    # ---- structured refs + requirement closure
    targets = _reference_targets(plan)
    for node in plan.plot_nodes:
        for ref in _node_refs(node):
            if ref not in targets:
                add_finding(findings, "PLOT_NODE_REF_UNKNOWN", "ERROR", "plot", node.node_id,
                            "PlotNode 结构化引用无法解析", related=(ref,))
        if node.conflict_chain_ref and node.conflict_chain_ref not in {
                chain.conflict_id for chain in plan.conflict_chains}:
            add_finding(findings, "PLOT_NODE_REF_UNKNOWN", "ERROR", "plot", node.node_id,
                        "conflict_chain_ref 不存在", related=(node.conflict_chain_ref,))
        if node.requirements is not None:
            _check_requirement_closure(plan, node, findings, available_requirements)
        incoming = reverse_adjacency(plan).get(node.node_id) or set()
        if not node.is_empty_beat() and not node.pressure_refs and not node.pressure_kinds \
                and not incoming:
            # root 节点的来源允许是"开场处境"（trigger / conflict / major_choice）；
            # 其余孤立节点必须给出结构化 pressure / opportunity 来源
            opening_source = bool(node.trigger or node.conflict or node.major_choice)
            if not (node.node_id in set(root_nodes(plan)) and opening_source):
                add_finding(findings, "PLOT_NODE_NO_PRESSURE_SOURCE", "ERROR", "plot",
                            node.node_id,
                            "非平凡节点没有 pressure / opportunity 来源，也没有上游因果")
        if not _has_outcome(node):
            add_finding(findings, "PLOT_NODE_NO_OUTCOME", "WARNING", "plot", node.node_id,
                        "节点没有声明任何结构化 outcome（只写'局势变化'不够）")
        optional_alternatives = [item for item in node.alternatives if item in node_ids]
        if node.must_happen and len(optional_alternatives) > 1:
            add_finding(findings, "PLOT_NODE_ALTERNATIVE_CONFLICT", "ERROR", "plot",
                        node.node_id, "must_happen 节点带有多个 alternative（语义冲突）",
                        related=tuple(optional_alternatives))
    # ---- arc anchors
    for arc in plan.character_arcs:
        anchored = [choice for choice in arc.major_choices
                    if choice.node_id and choice.node_id in node_ids]
        if not anchored and arc.major_choices:
            severity = "ERROR" if any(
                nodes_by_id.get(choice.node_id) is not None
                and nodes_by_id[choice.node_id].must_happen
                for choice in arc.major_choices) else "WARNING"
            add_finding(findings, "CHARACTER_ARC_CHOICE_UNANCHORED", severity, "plot",
                        arc.arc_id, "角色弧的重大选择没有 PlotNode 承载",
                        related=tuple(choice.node_id for choice in arc.major_choices))
    for arc in plan.relationship_arcs:
        for stage in arc.stages:
            if stage.trigger_node_id and stage.trigger_node_id not in node_ids:
                add_finding(findings, "RELATIONSHIP_STAGE_TRIGGER_UNANCHORED", "ERROR",
                            "plot", arc.arc_id, "关系阶段绑定的 trigger_node_id 不存在",
                            related=(stage.trigger_node_id,))
    for arc in plan.faction_arcs:
        for stage in arc.stages:
            if stage.trigger_node_id and stage.trigger_node_id not in node_ids:
                add_finding(findings, "FACTION_STAGE_TRIGGER_UNANCHORED", "ERROR", "plot",
                            arc.arc_id, "势力阶段绑定的 trigger_node_id 不存在",
                            related=(stage.trigger_node_id,))
    _check_information_causality(plan, findings)
    _check_foreshadow_causality(plan, findings)
    _check_resource_and_equipment(plan, findings)
    _check_locations(plan, findings, available_requirements)
    _check_reward_linkage(plan, findings)
    _check_theme_linkage(plan, findings, terminals, nodes_by_id)
    _check_repetition(plan, findings, order)
    report.findings.extend(findings)
    return report


# ---------------------------------------------------------------- helpers
def _node_refs(node: PlotNode) -> list[str]:
    return (node.character_arc_refs + node.relationship_arc_refs + node.faction_arc_refs
            + node.information_move_refs + node.foreshadow_move_refs
            + node.progression_milestone_refs + node.resource_flow_refs
            + node.equipment_refs + node.base_progression_refs + node.map_expansion_refs
            + node.reward_refs + node.autonomous_action_refs + node.faction_relation_refs
            + node.stage_trigger_refs)


def _reference_targets(plan: StoryPlanningIR) -> set[str]:
    rows: set[str] = set()
    rows |= {item.arc_id for item in plan.character_arcs}
    rows |= {item.arc_id for item in plan.relationship_arcs}
    rows |= {item.arc_id for item in plan.faction_arcs}
    rows |= {move.move_id for arc in plan.information_arcs for move in arc.moves}
    rows |= {move.move_id for item in plan.foreshadow_plans for move in item.moves}
    rows |= {item.milestone_id for track in plan.progression_tracks
             for item in track.milestones}
    rows |= {item.flow_id for item in plan.resource_flows}
    rows |= {item.equipment_id for item in plan.equipment_plans}
    rows |= {item.base_id for item in plan.base_progressions}
    rows |= {item.expansion_id for item in plan.map_expansions}
    rows |= {event.reward_id for item in plan.reward_plans for event in item.events}
    rows |= {item.action_id for item in plan.autonomous_actions}
    rows |= {item.relation_id for item in plan.faction_relations}
    rows |= {item.stage_id or item.label for arc in plan.relationship_arcs
             for item in arc.stages}
    rows |= {item.stage_id for arc in plan.faction_arcs for item in arc.stages}
    rows |= {item.node_id for item in plan.plot_nodes}
    return rows


def _has_outcome(node: PlotNode) -> bool:
    return bool(node.state_change or node.character_change or node.relationship_change
                or node.information_change or node.progression_change or node.cost
                or node.payoff or node.reward_refs or node.resource_flow_refs
                or node.equipment_refs or node.map_expansion_refs
                or node.progression_milestone_refs or node.information_move_refs
                or node.foreshadow_move_refs or node.base_progression_refs)


def _check_requirement_closure(plan: StoryPlanningIR, node: PlotNode,
                               findings: list[PlanningFinding],
                               available_requirements: Iterable[str]) -> None:
    graph = adjacency(plan)
    node_ids = {item.node_id for item in plan.plot_nodes}
    for ref in node.requirements.requirements:
        if ref.satisfied_by:
            satisfiers = [item for item in ref.satisfied_by if item]
            unknown = [item for item in satisfiers if item not in node_ids
                       and item not in _reference_targets(plan)]
            if unknown:
                add_finding(findings, "REQUIREMENT_SATISFIER_UNKNOWN", "ERROR", "requirement",
                            ref.requirement_id, "satisfied_by 指向不存在的对象",
                            related=tuple(unknown))
                continue
            node_satisfiers = [item for item in satisfiers if item in node_ids]
            upstream = upstream_of(plan, node.node_id)
            missing = [item for item in node_satisfiers if item not in upstream]
            if missing:
                add_finding(findings, "REQUIREMENT_SATISFIER_NOT_UPSTREAM", "ERROR",
                            "requirement", ref.requirement_id,
                            "requirement 的 satisfied_by 节点不在该节点上游",
                            related=tuple(missing))
            continue
        evaluation = evaluate_requirements(
            RequirementGroup(operator="all", requirements=[ref]),
            available=tuple(available_requirements))
        if not evaluation.satisfied:
            add_finding(findings, "REQUIREMENT_WITHOUT_CLOSURE", "ERROR", "requirement",
                        ref.requirement_id,
                        "requirement 既没有 starting condition，也没有 satisfied_by 节点",
                        related=(node.node_id,))
    # requirement causal cycle（沿 satisfied_by 的节点链）
    visit: dict[str, int] = {}

    def walk(node_id: str, stack: list[str]) -> None:
        visit[node_id] = 1
        current = next((item for item in plan.plot_nodes if item.node_id == node_id), None)
        if current is not None and current.requirements is not None:
            for ref in current.requirements.requirements:
                for satisfier in ref.satisfied_by:
                    if satisfier not in node_ids:
                        continue
                    if visit.get(satisfier, 0) == 1:
                        chain = stack[stack.index(satisfier):] + [satisfier]
                        add_finding(findings, "REQUIREMENT_CAUSAL_CYCLE", "ERROR",
                                    "requirement", ref.requirement_id,
                                    "requirement satisfied_by 形成循环",
                                    related=tuple(chain))
                    elif visit.get(satisfier, 0) == 0:
                        walk(satisfier, stack + [satisfier])
        visit[node_id] = 2

    for node in plan.plot_nodes:
        if visit.get(node.node_id, 0) == 0:
            walk(node.node_id, [node.node_id])


def _check_information_causality(plan: StoryPlanningIR,
                                 findings: list[PlanningFinding]) -> None:
    node_ids = {item.node_id for item in plan.plot_nodes}
    for arc in plan.information_arcs:
        for move in arc.moves:
            if move.move_type not in ("reveal", "payoff") or not move.node_id:
                continue
            upstream = upstream_of(plan, move.node_id)
            prior = [item for item in arc.moves
                     if item.truth_id == move.truth_id
                     and item.move_type in ("plant", "hint")
                     and item.node_id in upstream]
            if not prior and move.node_id in node_ids:
                add_finding(findings, "INFORMATION_REVEAL_NOT_UPSTREAM", "ERROR",
                            "information", move.move_id,
                            "揭示 / 回收之前没有上游的 plant / hint",
                            related=(move.node_id,))


def _check_foreshadow_causality(plan: StoryPlanningIR,
                                findings: list[PlanningFinding]) -> None:
    for foreshadow in plan.foreshadow_plans:
        payoff_moves = [item for item in foreshadow.moves if item.move_type == "payoff"]
        if not payoff_moves:
            continue
        for payoff in payoff_moves:
            if not payoff.node_id:
                continue
            upstream = upstream_of(plan, payoff.node_id)
            prior = [item for item in foreshadow.moves
                     if item.move_type in ("plant", "reinforce", "reveal", "misdirect")
                     and item.node_id in upstream]
            if not prior:
                add_finding(findings, "FORESHADOW_PAYOFF_NOT_UPSTREAM", "ERROR",
                            "foreshadow", _foreshadow_move_ref(payoff, foreshadow),
                            "回收节点之前没有上游的埋设 / 强化",
                            related=(payoff.node_id,))


def _foreshadow_move_ref(move, foreshadow) -> str:
    return f"{foreshadow.foreshadow_id}::{move.move_id}"


def _check_resource_and_equipment(plan: StoryPlanningIR,
                                  findings: list[PlanningFinding]) -> None:
    ledger = build_resource_ledger(plan)
    deficits = {row.resource_id for row in ledger.rows if row.impossible_consumption}
    for node in plan.plot_nodes:
        consumed_flows = [flow for flow in plan.resource_flows
                          if flow.flow_id in node.resource_flow_refs]
        for flow in consumed_flows:
            if flow.identity() in deficits:
                add_finding(findings, "RESOURCE_UNSUPPORTED_NODE", "ERROR", "plot",
                            node.node_id, "节点依赖的资源在计划中入不敷出",
                            related=(flow.identity(),))
        for equipment_id in node.equipment_refs:
            equipment = next((item for item in plan.equipment_plans
                              if item.equipment_id == equipment_id), None)
            if equipment is None or not equipment.loss_node:
                continue
            loss_order = order_of(plan, equipment.loss_node)
            node_order = order_of(plan, node.node_id)
            if loss_order is not None and node_order is not None and node_order > loss_order:
                add_finding(findings, "EQUIPMENT_USE_AFTER_LOSS_NODE", "ERROR", "plot",
                            node.node_id, "节点使用了已经丢失的装备",
                            related=(equipment_id, equipment.loss_node))


def _check_locations(plan: StoryPlanningIR, findings: list[PlanningFinding],
                     available_requirements: Iterable[str]) -> None:
    declared, availability = declared_access(plan)
    reachable: set[str] = set()
    for entry in entry_locations(plan):
        reachable.update(reachable_locations(
            plan, entry, available_requirements=declared,
            available_availability=availability).reachable)
    gated: set[str] = set()
    for entry in entry_locations(plan):
        gated.update(reachable_locations(
            plan, entry, available_requirements=available_requirements,
            available_availability=availability).reachable)
    for node in plan.plot_nodes:
        if not node.location_id:
            continue
        if node.location_id not in {item.location_id for item in plan.locations}:
            add_finding(findings, "LOCATION_UNREACHABLE_NODE", "ERROR", "plot", node.node_id,
                        "节点地点不存在", related=(node.location_id,))
        elif node.location_id not in reachable:
            add_finding(findings, "LOCATION_UNREACHABLE_NODE", "ERROR", "plot", node.node_id,
                        "节点地点结构上不可达", related=(node.location_id,))
        elif node.location_id not in gated:
            add_finding(findings, "LOCATION_BLOCKED_NODE", "WARNING", "plot", node.node_id,
                        "节点地点尚未解锁（需要上游节点满足 requirement）",
                        related=(node.location_id,))


def _check_reward_linkage(plan: StoryPlanningIR,
                          findings: list[PlanningFinding]) -> None:
    if not plan.reward_plans:
        return
    rewarded = {node.node_id for node in plan.plot_nodes if node.reward_refs}
    for volume in plan.volumes:
        if not volume.climax_node_id:
            continue
        if volume.climax_node_id not in rewarded:
            add_finding(findings, "CLIMAX_REWARD_LINKAGE_MISSING", "WARNING", "spine",
                        volume.climax_node_id, "卷高潮节点没有引用任何 RewardEvent",
                        related=(volume.volume_id,))


def _check_theme_linkage(plan: StoryPlanningIR, findings: list[PlanningFinding],
                         terminals: list[str], nodes_by_id: dict[str, PlotNode]) -> None:
    if plan.theme is None:
        return
    themed = [node.node_id for node in plan.plot_nodes if node.theme_refs]
    if not themed:
        add_finding(findings, "THEME_LINKAGE_MISSING", "WARNING", "spine",
                    plan.theme.theme_id, "没有任何 PlotNode 连接到 central theme / 戏剧问题")
        return
    if plan.theme.final_answer_direction:
        terminal_themed = [node_id for node_id in terminals
                           if nodes_by_id.get(node_id) is not None
                           and nodes_by_id[node_id].theme_refs]
        if not terminal_themed:
            add_finding(findings, "MACRO_ENDING_PLAN_MISSING", "WARNING", "spine",
                        plan.theme.theme_id, "terminal 方向没有任何节点连接主题答案",
                        related=tuple(themed))


def _check_repetition(plan: StoryPlanningIR, findings: list[PlanningFinding],
                      order: list[str]) -> None:
    nodes_by_id = {node.node_id: node for node in plan.plot_nodes}
    signatures: list[tuple[str, tuple]] = []
    for node_id in order:
        node = nodes_by_id.get(node_id)
        if node is None:
            continue
        signature = (node.location_id, tuple(sorted(node.participants)),
                     node.purpose.strip()[:24], node.conflict.strip()[:24],
                     tuple(node.pressure_kinds))
        signatures.append((node_id, signature))
    for index in range(len(signatures) - 1):
        first_id, first = signatures[index]
        second_id, second = signatures[index + 1]
        if first == second and first[2]:
            add_finding(findings, "PLOT_NODE_PATTERN_REPETITION", "WARNING", "plot",
                        second_id, "相邻节点的 purpose / 参与者 / 地点 / 冲突高度重复",
                        related=(first_id,))


def build_coverage_report(plan: StoryPlanningIR, *, revision_id: str = "",
                          inventory: PlotPressureInventory | None = None
                          ) -> StorySpineCoverageReport:
    inventory = inventory or build_plot_pressure_inventory(plan, revision_id=revision_id)
    nodes_by_id = {node.node_id: node for node in plan.plot_nodes}
    covered: set[str] = set()
    for node in plan.plot_nodes:
        covered |= set(_node_refs(node))
    requirement_total = 0
    requirement_closed = 0
    for group in plan.requirement_groups():
        for ref in group.requirements:
            requirement_total += 1
            if ref.satisfied_by:
                requirement_closed += 1
    open_pressures = [item for item in inventory.pressures
                      if item.state in ("open", "blocked")]
    unaddressed = [item.pressure_id for item in open_pressures
                   if not any(item.source_ref in set(_node_refs(node))
                              for node in plan.plot_nodes)]
    return StorySpineCoverageReport(
        revision_id=revision_id, plot_node_count=len(plan.plot_nodes),
        must_happen_count=len([node for node in plan.plot_nodes if node.must_happen]),
        optional_count=len([node for node in plan.plot_nodes if node.optional]),
        root_count=len(root_nodes(plan)), terminal_count=len(terminal_nodes(plan)),
        open_pressure_count=len([item for item in inventory.pressures
                                 if item.state == "open"]),
        blocked_pressure_count=len(inventory.blocked()),
        scheduled_pressure_count=len(inventory.scheduled()),
        resolved_pressure_count=len(inventory.resolved()),
        deferred_pressure_count=len([item for item in inventory.pressures
                                     if item.state == "deferred"]),
        character_arc_coverage=len([arc for arc in plan.character_arcs
                                    if arc.arc_id in covered]),
        relationship_arc_coverage=len([arc for arc in plan.relationship_arcs
                                       if arc.arc_id in covered]),
        faction_arc_coverage=len([arc for arc in plan.faction_arcs
                                  if arc.arc_id in covered]),
        information_coverage=len([move for arc in plan.information_arcs for move in arc.moves
                                  if move.move_id in covered]),
        foreshadow_coverage=len([move for item in plan.foreshadow_plans
                                 for move in item.moves if move.move_id in covered]),
        progression_coverage=len([item for track in plan.progression_tracks
                                  for item in track.milestones
                                  if item.milestone_id in covered]),
        reward_coverage=len([event for item in plan.reward_plans
                             for event in item.events if event.reward_id in covered]),
        requirement_closure=requirement_closed, requirement_total=requirement_total,
        conflict_escalation_coverage=len([chain for chain in plan.conflict_chains
                                          if set(chain.related_node_ids) & set(nodes_by_id)]),
        unaddressed_pressures=sorted(unaddressed))


__all__ = [
    "StorySpineCoverageReport",
    "adjacency",
    "analyze_story_spine",
    "build_coverage_report",
    "components",
    "reverse_adjacency",
    "root_nodes",
    "terminal_nodes",
    "topological_order",
    "upstream_of",
]
