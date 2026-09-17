"""M4：Planning Graph —— 从 StoryPlanningIR **派生**的 Location / Relationship / Faction 图。

定位（硬边界）：

- 输入 = StoryPlanningIR（future planning truth），输出 = 派生图 + findings + read-only projection；
- 图是 projection / analysis structure，**不是第二 truth source**：本模块不落盘任何
  authoritative graph，也不写 Canon / StoryState；
- 复用 networkx 的图遍历 / 环检测 / 可达性思路（与 `canon/graph.py` 一致），不引入图数据库。

可达性是 **Planning reachability**（"按计划能不能走到"），不是 StoryState 当前真实可达性。
"""

from __future__ import annotations

from collections import deque
from typing import Any, Iterable, Literal

import networkx as nx
from pydantic import Field

from novelforge.models import StrictModel

from .models import StoryPlanningIR
from .versioning import planning_digest

GraphDomain = Literal["location", "relationship", "faction", "combined"]
NodeKind = Literal["location", "character", "faction", "external_entity"]
EdgeKind = Literal["route", "relationship", "alliance", "hostility", "territory", "pressure"]


class GraphNode(StrictModel):
    node_id: str = Field(min_length=3, max_length=160)
    kind: NodeKind = "external_entity"
    label: str = Field(default="", max_length=120)
    metadata: dict[str, Any] = Field(default_factory=dict)
    source_planning_ids: list[str] = Field(default_factory=list)


class GraphEdge(StrictModel):
    edge_id: str = Field(min_length=3, max_length=200)
    kind: EdgeKind = "route"
    source_id: str = Field(min_length=3, max_length=160)
    target_id: str = Field(min_length=3, max_length=160)
    label: str = Field(default="", max_length=120)
    # hyperedge metadata：关系弧可能多于两方，pairwise 投影也不能丢掉完整 participant set
    participants: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    source_planning_ids: list[str] = Field(default_factory=list)


class PlanningGraph(StrictModel):
    graph_id: str = Field(min_length=5, max_length=64)
    domain: GraphDomain = "combined"
    nodes: list[GraphNode] = Field(default_factory=list)
    edges: list[GraphEdge] = Field(default_factory=list)

    def node(self, node_id: str) -> GraphNode | None:
        return next((item for item in self.nodes if item.node_id == node_id), None)

    def node_ids(self) -> list[str]:
        return [item.node_id for item in self.nodes]

    def degree(self) -> dict[str, int]:
        rows = {node_id: 0 for node_id in self.node_ids()}
        for edge in self.edges:
            for endpoint in (edge.source_id, edge.target_id):
                rows[endpoint] = rows.get(endpoint, 0) + 1
        return rows

    def isolated(self) -> list[str]:
        degree = self.degree()
        return sorted(node_id for node_id, value in degree.items() if value == 0)

    def neighbours(self, node_id: str) -> list[str]:
        rows: set[str] = set()
        for edge in self.edges:
            if edge.source_id == node_id:
                rows.add(edge.target_id)
            if edge.target_id == node_id:
                rows.add(edge.source_id)
        return sorted(rows)

    def to_networkx(self) -> nx.MultiDiGraph:
        """派生结构，仅供分析；调用方不得把它当作 truth 保存。"""

        graph = nx.MultiDiGraph()
        for node in self.nodes:
            graph.add_node(node.node_id, kind=node.kind, label=node.label)
        for edge in self.edges:
            graph.add_edge(edge.source_id, edge.target_id, key=edge.edge_id, kind=edge.kind)
        return graph

    def cycles(self) -> list[list[str]]:
        graph = nx.DiGraph()
        for edge in self.edges:
            graph.add_edge(edge.source_id, edge.target_id)
        return [list(cycle) for cycle in nx.simple_cycles(graph)]


class PlanningGraphBundle(StrictModel):
    novel_id: str = Field(default="", max_length=96)
    planning_id: str = Field(default="", max_length=64)
    revision_id: str = Field(default="", max_length=64)
    content_digest: str = Field(default="", max_length=64)
    location: PlanningGraph = Field(default_factory=lambda: PlanningGraph(
        graph_id="LOCGRAPH_DERIVED", domain="location"))
    relationship: PlanningGraph = Field(default_factory=lambda: PlanningGraph(
        graph_id="RELGRAPH_DERIVED", domain="relationship"))
    faction: PlanningGraph = Field(default_factory=lambda: PlanningGraph(
        graph_id="FACTGRAPH_DERIVED", domain="faction"))
    combined: PlanningGraph = Field(default_factory=lambda: PlanningGraph(
        graph_id="PLANNINGGRAPH_DERIVED", domain="combined"))

    def graph(self, domain: GraphDomain) -> PlanningGraph:
        return {"location": self.location, "relationship": self.relationship,
                "faction": self.faction, "combined": self.combined}[domain]


# ---------------------------------------------------------------------- builders
def build_location_graph(plan: StoryPlanningIR) -> PlanningGraph:
    nodes = [GraphNode(node_id=item.location_id, kind="location", label=item.display_name,
                       metadata={"parent_region": item.parent_region,
                                 "environment": item.environment,
                                 "story_function": item.story_function,
                                 "discoverability": item.discoverability},
                       source_planning_ids=[item.location_id])
             for item in plan.locations]
    known = {item.location_id for item in plan.locations}
    edges: list[GraphEdge] = []
    graph = plan.location_graph
    if graph is not None:
        for index, edge in enumerate(graph.edges):
            edges.append(GraphEdge(
                edge_id=f"ROUTE_{index:03d}_{edge.from_location_id}__{edge.to_location_id}",
                kind="route", source_id=edge.from_location_id, target_id=edge.to_location_id,
                label=edge.route,
                metadata={"route": edge.route, "distance": edge.distance,
                          "travel_time": edge.travel_time, "risk": edge.risk,
                          "requirement": edge.requirement, "availability": edge.availability},
                source_planning_ids=[edge.from_location_id, edge.to_location_id]))
            for endpoint in (edge.from_location_id, edge.to_location_id):
                if endpoint not in known:
                    nodes.append(GraphNode(node_id=endpoint, kind="location",
                                           label=endpoint, metadata={"dangling": True}))
    return _sorted_graph("LOCGRAPH_DERIVED", "location", nodes, edges)


def build_relationship_graph(plan: StoryPlanningIR) -> PlanningGraph:
    character_ids = {item.character_id for item in plan.characters}
    faction_ids = {item.faction_id for item in plan.factions}
    nodes: dict[str, GraphNode] = {}
    edges: list[GraphEdge] = []
    for arc in plan.relationship_arcs:
        for participant in arc.participants:
            kind: NodeKind = ("character" if participant in character_ids
                              else "faction" if participant in faction_ids
                              else "external_entity")
            nodes.setdefault(participant, GraphNode(
                node_id=participant, kind=kind, label=_label_for(plan, participant),
                metadata={"in_planning": participant in character_ids or participant in faction_ids}))
        # pairwise 投影（按声明顺序，确定性），但 participants 保留完整 set
        ordered = list(arc.participants)
        for index in range(len(ordered) - 1):
            edges.append(GraphEdge(
                edge_id=f"{arc.arc_id}::{index}",
                kind="relationship", source_id=ordered[index], target_id=ordered[index + 1],
                label=arc.relationship_change or arc.start_state,
                participants=list(arc.participants),
                metadata={"start_state": arc.start_state,
                          "stages": [stage.label or stage.stage_id for stage in arc.stages],
                          "irreversible_node": arc.irreversible_node,
                          "future_payoff": arc.future_payoff,
                          "non_authoritative": True},
                source_planning_ids=[arc.arc_id]))
    return _sorted_graph("RELGRAPH_DERIVED", "relationship", list(nodes.values()), edges)


def build_faction_graph(plan: StoryPlanningIR) -> PlanningGraph:
    faction_ids = {item.faction_id for item in plan.factions}
    location_ids = {item.location_id for item in plan.locations}
    nodes: dict[str, GraphNode] = {}
    for faction in plan.factions:
        nodes[faction.faction_id] = GraphNode(
            node_id=faction.faction_id, kind="faction", label=faction.display_name,
            metadata={"goal": faction.goal, "public_goal": faction.public_goal,
                      "hidden_goal": faction.hidden_goal, "red_line": faction.red_line},
            source_planning_ids=[faction.faction_id])
    edges: list[GraphEdge] = []
    for faction in plan.factions:
        for ally in faction.allies:
            edges.append(GraphEdge(edge_id=f"{faction.faction_id}::ally::{ally}",
                                   kind="alliance", source_id=faction.faction_id,
                                   target_id=ally, label="alliance",
                                   metadata={"explained": bool(faction.note)},
                                   source_planning_ids=[faction.faction_id]))
            if ally not in faction_ids:
                nodes.setdefault(ally, GraphNode(node_id=ally, kind="external_entity",
                                                 label=ally, metadata={"dangling": True}))
        for enemy in faction.enemies:
            edges.append(GraphEdge(edge_id=f"{faction.faction_id}::enemy::{enemy}",
                                   kind="hostility", source_id=faction.faction_id,
                                   target_id=enemy, label="hostility",
                                   metadata={"explained": bool(faction.note)},
                                   source_planning_ids=[faction.faction_id]))
            if enemy not in faction_ids:
                nodes.setdefault(enemy, GraphNode(node_id=enemy, kind="external_entity",
                                                  label=enemy, metadata={"dangling": True}))
        for territory in faction.territory:
            edges.append(GraphEdge(edge_id=f"{faction.faction_id}::territory::{territory}",
                                   kind="territory", source_id=faction.faction_id,
                                   target_id=territory, label="territory",
                                   metadata={"in_graph": territory in location_ids},
                                   source_planning_ids=[faction.faction_id]))
            if territory not in location_ids:
                nodes.setdefault(territory, GraphNode(node_id=territory, kind="location",
                                                      label=territory,
                                                      metadata={"dangling": True}))
    # M5：FactionRelation（dependency / trade / influence / vassalage / competition …）
    for relation in plan.faction_relations:
        kind: EdgeKind = ("alliance" if relation.relation_type == "alliance"
                          else "hostility" if relation.relation_type == "hostility"
                          else "pressure")
        edges.append(GraphEdge(
            edge_id=f"relation::{relation.relation_id}", kind=kind,
            source_id=relation.from_faction_id, target_id=relation.to_faction_id,
            label=relation.state or relation.relation_type,
            metadata={"relation_type": relation.relation_type,
                      "symmetric": relation.symmetric, "public": relation.public,
                      "non_authoritative": True},
            source_planning_ids=[relation.relation_id]))
        for endpoint in (relation.from_faction_id, relation.to_faction_id):
            if endpoint not in faction_ids:
                nodes.setdefault(endpoint, GraphNode(node_id=endpoint, kind="external_entity",
                                                     label=endpoint,
                                                     metadata={"dangling": True}))
    return _sorted_graph("FACTGRAPH_DERIVED", "faction", list(nodes.values()), edges)


def build_planning_graphs(plan: StoryPlanningIR, *, revision_id: str = "",
                          content_digest: str = "") -> PlanningGraphBundle:
    """三张图 + 一张合并图（跨图校验用）；同一输入必然得到同一输出。"""

    location = build_location_graph(plan)
    relationship = build_relationship_graph(plan)
    faction = build_faction_graph(plan)
    combined = _sorted_graph(
        "PLANNINGGRAPH_DERIVED", "combined",
        location.nodes + relationship.nodes + faction.nodes,
        location.edges + relationship.edges + faction.edges)
    return PlanningGraphBundle(novel_id=plan.novel_id, planning_id=plan.planning_id,
                               revision_id=revision_id,
                               content_digest=content_digest or planning_digest(plan),
                               location=location, relationship=relationship,
                               faction=faction, combined=combined)


# ---------------------------------------------------------------------- reachability
class ReachabilityResult(StrictModel):
    """Planning reachability：按计划能不能走到（不写 StoryState）。"""

    from_location_id: str = Field(default="", max_length=64)
    reachable: list[str] = Field(default_factory=list)
    blocked: dict[str, str] = Field(default_factory=dict)
    unreachable: list[str] = Field(default_factory=list)
    paths: dict[str, list[str]] = Field(default_factory=dict)


def entry_locations(plan: StoryPlanningIR) -> list[str]:
    """无 entry_requirement 的地点 = 计划的自然入口。"""

    return sorted(item.location_id for item in plan.locations if not item.entry_requirement)


def declared_access(plan: StoryPlanningIR) -> tuple[set[str], set[str]]:
    """计划里声明过的 (requirements, availability)。

    用于区分"结构上没有路"（应报 ERROR）与"有计划中的门"（只是需要解锁）。
    """

    requirements: set[str] = set()
    availability: set[str] = set()
    graph = plan.location_graph
    if graph is not None:
        for edge in graph.edges:
            if not _is_open(edge.requirement):
                requirements.add(edge.requirement)
            if not _is_open(edge.availability):
                availability.add(edge.availability)
    for location in plan.locations:
        if not _is_open(location.entry_requirement):
            requirements.add(location.entry_requirement)
    return requirements, availability


def reachable_locations(plan: StoryPlanningIR, from_location_id: str, *,
                        available_requirements: Iterable[str] = (),
                        available_availability: Iterable[str] = ()
                        ) -> ReachabilityResult:
    """BFS：route.requirement / target.entry_requirement / availability 未满足时算 blocked。"""

    requirements = set(available_requirements)
    availability = set(available_availability)
    graph = plan.location_graph
    location_ids = sorted({item.location_id for item in plan.locations})
    result = ReachabilityResult(from_location_id=from_location_id)
    if graph is None or from_location_id not in location_ids:
        result.unreachable = location_ids
        result.blocked = {item: "入口地点不在 Planning 地点表里" for item in location_ids}
        return result
    entry_by_location = {item.location_id: item.entry_requirement for item in plan.locations}
    adjacency: dict[str, list[Any]] = {}
    for edge in graph.edges:
        adjacency.setdefault(edge.from_location_id, []).append(edge)
    queue: deque[str] = deque([from_location_id])
    seen = {from_location_id}
    result.paths[from_location_id] = [from_location_id]
    while queue:
        current = queue.popleft()
        for edge in adjacency.get(current, []):
            target = edge.to_location_id
            reason = _blocked_reason(edge, entry_by_location.get(target, ""),
                                     requirements, availability,
                                     check_availability=bool(availability))
            if reason:
                result.blocked.setdefault(target, reason)
                continue
            if target in seen:
                continue
            seen.add(target)
            result.paths[target] = result.paths[current] + [target]
            queue.append(target)
    result.reachable = sorted(seen)
    result.unreachable = sorted(set(location_ids) - seen)
    return result


def location_path(plan: StoryPlanningIR, from_location_id: str, to_location_id: str, *,
                  available_requirements: Iterable[str] = (),
                  available_availability: Iterable[str] = ()) -> list[str]:
    result = reachable_locations(plan, from_location_id,
                                 available_requirements=available_requirements,
                                 available_availability=available_availability)
    return result.paths.get(to_location_id, [])


def faction_pressure_candidates(plan: StoryPlanningIR, target_id: str) -> list[dict[str, Any]]:
    """哪些 faction 能对某个 location / character / faction 产生 planned pressure（只读）。"""

    rows: list[dict[str, Any]] = []
    for faction in plan.factions:
        reasons: list[str] = []
        if target_id in faction.territory:
            reasons.append("territory")
        if target_id in faction.allies:
            reasons.append("alliance_interest")
        if target_id in faction.enemies:
            reasons.append("hostility")
        for arc in plan.relationship_arcs:
            if faction.faction_id in arc.participants and target_id in arc.participants:
                reasons.append(f"relationship_arc:{arc.arc_id}")
        if reasons:
            rows.append({"faction_id": faction.faction_id, "target_id": target_id,
                         "reasons": sorted(set(reasons)), "goal": faction.goal,
                         "red_line": faction.red_line, "non_authoritative": True})
    return sorted(rows, key=lambda row: row["faction_id"])


# ---------------------------------------------------------------------- helpers
def _blocked_reason(edge, entry_requirement: str, requirements: set[str],
                    availability: set[str], *, check_availability: bool) -> str:
    if not _is_open(edge.requirement) and edge.requirement not in requirements:
        return f"route requirement 未满足：{edge.requirement}"
    # availability（白天 / 夜间 / 雨季）是时间窗口：只有调用方显式给窗口时才校验
    if check_availability and not _is_open(edge.availability) \
            and edge.availability not in availability:
        return f"route availability 未满足：{edge.availability}"
    if not _is_open(entry_requirement) and entry_requirement not in requirements:
        return f"entry requirement 未满足：{entry_requirement}"
    return ""


OPEN_GATE_VALUES: tuple[str, ...] = ("", "无", "none", "n/a", "na", "-", "不适用")


def _is_open(value: str | None) -> bool:
    """作者常写 "无" / "none" 表示没有门槛；这些不算 requirement。"""

    return (value or "").strip().lower() in OPEN_GATE_VALUES


def _label_for(plan: StoryPlanningIR, identifier: str) -> str:
    for item in plan.characters:
        if item.character_id == identifier:
            return item.display_name or identifier
    for item in plan.factions:
        if item.faction_id == identifier:
            return item.display_name or identifier
    return identifier


def _sorted_graph(graph_id: str, domain: GraphDomain, nodes: list[GraphNode],
                  edges: list[GraphEdge]) -> PlanningGraph:
    unique: dict[str, GraphNode] = {}
    for node in nodes:
        existing = unique.get(node.node_id)
        if existing is None or (existing.metadata.get("dangling") and
                                not node.metadata.get("dangling")):
            unique[node.node_id] = node
    return PlanningGraph(
        graph_id=graph_id, domain=domain,
        nodes=sorted(unique.values(), key=lambda item: item.node_id),
        edges=sorted(edges, key=lambda item: (item.kind, item.source_id, item.target_id,
                                              item.edge_id)))


__all__ = [
    "EdgeKind",
    "GraphDomain",
    "GraphEdge",
    "GraphNode",
    "NodeKind",
    "PlanningGraph",
    "PlanningGraphBundle",
    "ReachabilityResult",
    "build_faction_graph",
    "build_location_graph",
    "build_planning_graphs",
    "build_relationship_graph",
    "entry_locations",
    "faction_pressure_candidates",
    "location_path",
    "reachable_locations",
]
