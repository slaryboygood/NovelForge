"""M4：Graph Projection —— 给 M13 / M14 UI 与 M5 / M6 / M7 用的只读 DTO。

投影不保存 truth：`GraphProjection` 里的每个节点 / 边都带 `source_planning_ids`，
真正的数据仍在 StoryPlanningIR；投影只做稳定的读模型（含 findings、revision、digest）。
"""

from __future__ import annotations

from typing import Any, Iterable, Literal

from pydantic import Field

from novelforge.models import StrictModel

from .graph_validator import GraphFinding, GraphReport, PlanningGraphValidator
from .graphs import (
    GraphDomain,
    PlanningGraph,
    PlanningGraphBundle,
    build_planning_graphs,
)
from .models import StoryPlanningIR
from .versioning import planning_digest


class GraphNodeProjection(StrictModel):
    id: str = Field(min_length=3, max_length=160)
    kind: str = Field(default="external_entity", max_length=32)
    label: str = Field(default="", max_length=120)
    ref: str = Field(default="", max_length=160)
    metadata: dict[str, Any] = Field(default_factory=dict)
    source_planning_ids: list[str] = Field(default_factory=list)


class GraphEdgeProjection(StrictModel):
    id: str = Field(min_length=3, max_length=200)
    kind: str = Field(default="route", max_length=32)
    source_id: str = Field(min_length=3, max_length=160)
    target_id: str = Field(min_length=3, max_length=160)
    label: str = Field(default="", max_length=120)
    participants: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    source_planning_ids: list[str] = Field(default_factory=list)
    non_authoritative: Literal[True] = True


class GraphProjection(StrictModel):
    graph_id: str = Field(min_length=5, max_length=64)
    domain: GraphDomain = "combined"
    revision_id: str = Field(default="", max_length=64)
    content_digest: str = Field(default="", max_length=64)
    nodes: list[GraphNodeProjection] = Field(default_factory=list)
    edges: list[GraphEdgeProjection] = Field(default_factory=list)
    findings: list[GraphFinding] = Field(default_factory=list)
    read_only: Literal[True] = True

    def node_ids(self) -> list[str]:
        return [item.id for item in self.nodes]

    def node(self, node_id: str) -> GraphNodeProjection | None:
        return next((item for item in self.nodes if item.id == node_id), None)

    def to_context_slice(self) -> dict[str, Any]:
        """给 LLM / compiler 的最小切片：只带 id / kind / label / 元数据。"""

        return {"graph_id": self.graph_id, "domain": self.domain,
                "revision_id": self.revision_id, "content_digest": self.content_digest,
                "nodes": [item.model_dump(mode="json") for item in self.nodes],
                "edges": [item.model_dump(mode="json") for item in self.edges],
                "findings": [item.model_dump(mode="json") for item in self.findings],
                "read_only": True}


class PlanningGraphSummary(StrictModel):
    """回答"地图 / 关系 / 势力 / 跨图"四类问题的最小摘要。"""

    location_count: int = 0
    route_count: int = 0
    reachable_regions: int = 0
    isolated_regions: int = 0
    relationship_count: int = 0
    relationship_stage_risks: int = 0
    faction_count: int = 0
    alliance_edges: int = 0
    hostility_edges: int = 0
    territorial_overlaps: int = 0
    cross_graph_findings: int = 0
    severity_counts: dict[str, int] = Field(default_factory=dict)
    read_only: Literal[True] = True


def project_graph(graph: PlanningGraph, *, revision_id: str = "", content_digest: str = "",
                  findings: Iterable[GraphFinding] = (),
                  node_ids: Iterable[str] = ()) -> GraphProjection:
    """把派生图折成只读 projection；可按 node_ids 过滤（context slice 用）。"""

    wanted = set(node_ids)
    nodes = [node for node in graph.nodes if not wanted or node.node_id in wanted]
    kept = {node.node_id for node in nodes}
    edges = [edge for edge in graph.edges
             if (not wanted or (edge.source_id in kept and edge.target_id in kept))]
    return GraphProjection(
        graph_id=graph.graph_id, domain=graph.domain, revision_id=revision_id,
        content_digest=content_digest,
        nodes=[GraphNodeProjection(id=node.node_id, kind=node.kind, label=node.label,
                                   ref=node.node_id, metadata=dict(node.metadata),
                                   source_planning_ids=list(node.source_planning_ids))
               for node in nodes],
        edges=[GraphEdgeProjection(id=edge.edge_id, kind=edge.kind, source_id=edge.source_id,
                                   target_id=edge.target_id, label=edge.label,
                                   participants=list(edge.participants),
                                   metadata=dict(edge.metadata),
                                   source_planning_ids=list(edge.source_planning_ids))
               for edge in edges],
        findings=[item for item in findings
                  if not wanted or item.source_id in kept
                  or set(item.related_ids) & kept])


def project_bundle(bundle: PlanningGraphBundle, *,
                   report: GraphReport | None = None) -> dict[str, GraphProjection]:
    findings = report.findings if report is not None else []
    return {domain: project_graph(bundle.graph(domain), revision_id=bundle.revision_id,
                                  content_digest=bundle.content_digest, findings=findings)
            for domain in ("location", "relationship", "faction", "combined")}


def summarize_graphs(plan: StoryPlanningIR, *, revision_id: str = "",
                     content_digest: str = "", report: GraphReport | None = None,
                     available_requirements: Iterable[str] = ()) -> PlanningGraphSummary:
    """只读摘要；不写文件、不改 plan。"""

    bundle = build_planning_graphs(plan, revision_id=revision_id,
                                   content_digest=content_digest)
    if report is None:
        report = PlanningGraphValidator().validate(
            plan, revision_id=revision_id, available_requirements=available_requirements)
    findings = report.findings
    from .graphs import declared_access, reachable_locations
    requirements, availability = declared_access(plan)
    reachable: set[str] = set()
    for entry in _entry_locations(plan):
        allowed = set(available_requirements) | requirements
        reachable.update(reachable_locations(
            plan, entry, available_requirements=allowed,
            available_availability=availability).reachable)
    location_ids = {item.location_id for item in plan.locations}
    return PlanningGraphSummary(
        location_count=len(plan.locations),
        route_count=len(bundle.location.edges),
        reachable_regions=len(reachable & location_ids),
        isolated_regions=len([item for item in bundle.location.isolated()
                              if item in location_ids]),
        relationship_count=len(plan.relationship_arcs),
        relationship_stage_risks=len([item for item in findings
                                      if item.domain == "relationship"
                                      and item.severity in ("ERROR", "WARNING")]),
        faction_count=len(plan.factions),
        alliance_edges=len([item for item in bundle.faction.edges
                            if item.kind == "alliance"]),
        hostility_edges=len([item for item in bundle.faction.edges
                             if item.kind == "hostility"]),
        territorial_overlaps=len([item for item in findings
                                  if item.code == "FACTION_TERRITORY_OVERLAP"]),
        cross_graph_findings=len([item for item in findings if item.domain == "cross"]),
        severity_counts=report.by_severity())


def _entry_locations(plan: StoryPlanningIR) -> list[str]:
    from .graphs import entry_locations
    return entry_locations(plan)


__all__ = [
    "GraphEdgeProjection",
    "GraphNodeProjection",
    "GraphProjection",
    "PlanningGraphSummary",
    "project_bundle",
    "project_graph",
    "summarize_graphs",
]
