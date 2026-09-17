"""M6：StorySpineBuilder —— 组装 approved PlotNode → 因果 DAG（不生成节点、不分章）。

职责：assemble / validate / topological order / root-terminal 分析 / coverage；
产出新的 Planning revision（不修改旧 revision）。
"""

from __future__ import annotations

from typing import Iterable

from .findings import AnalysisReport
from .models import (
    PlotNode,
    SpineEdge,
    StoryPlanningIR,
    StorySpine,
    new_planning_id,
)
from .plot_pressure import PlotPressureInventory, build_plot_pressure_inventory
from .repository import PlanningRepository, PlanningRevisionRecord
from .schemas import validate_planning_ir
from .spine_analysis import (
    StorySpineCoverageReport,
    analyze_story_spine,
    build_coverage_report,
    root_nodes,
    terminal_nodes,
    topological_order,
)


class StorySpineBuilder:
    """把节点与边组装成 StorySpine；缺边时按 prerequisites 推导 requires 边。"""

    def __init__(self, *, novel_id: str) -> None:
        self.novel_id = novel_id
        self.nodes: list[PlotNode] = []
        self.edges: list[SpineEdge] = []
        self.existing: StorySpine | None = None

    def with_nodes(self, nodes: Iterable[PlotNode]) -> "StorySpineBuilder":
        self.nodes.extend(nodes)
        return self

    def with_edges(self, edges: Iterable[SpineEdge]) -> "StorySpineBuilder":
        self.edges.extend(edges)
        return self

    def with_existing_spine(self, spine: StorySpine | None) -> "StorySpineBuilder":
        self.existing = spine
        return self

    # ---------------------------------------------------------------- build
    def build(self) -> StorySpine:
        node_ids = [item.node_id for item in self.nodes]
        if not node_ids and self.existing is not None:
            node_ids = list(self.existing.nodes)
        edges = list(self.edges)
        known_pairs = {(edge.from_node_id, edge.to_node_id, edge.relation) for edge in edges}
        for node in self.nodes:
            for prerequisite in node.prerequisites:
                key = (prerequisite, node.node_id, "requires")
                if key not in known_pairs:
                    edges.append(SpineEdge(from_node_id=prerequisite, to_node_id=node.node_id,
                                           relation="requires"))
                    known_pairs.add(key)
        incoming = {node_id for _, node_id, _ in known_pairs}
        outgoing = {source for source, _, _ in known_pairs}
        entries = [node_id for node_id in node_ids if node_id not in incoming]
        terminals = [node_id for node_id in node_ids if node_id not in outgoing]
        return StorySpine(
            spine_id=(self.existing.spine_id if self.existing is not None
                      else new_planning_id("spine")),
            novel_id=self.novel_id, nodes=sorted(set(node_ids)),
            edges=sorted(edges, key=lambda item: (item.from_node_id, item.to_node_id,
                                                  item.relation)),
            entry_node_ids=entries or (self.existing.entry_node_ids
                                       if self.existing is not None else []),
            terminal_node_ids=terminals or (self.existing.terminal_node_ids
                                            if self.existing is not None else []),
            provenance="generated", source="spine_builder")

    def build_plan(self, plan: StoryPlanningIR, *, nodes: Iterable[PlotNode] = (),
                   edges: Iterable[SpineEdge] = ()) -> StoryPlanningIR:
        """在**副本**上组装节点与 spine（旧 plan / 旧 revision 不变）。"""

        payload = plan.model_dump(mode="json")
        merged = {item.node_id: item for item in plan.plot_nodes}
        for node in list(self.nodes) + list(nodes):
            merged[node.node_id] = node
        payload["plot_nodes"] = [item.model_dump(mode="json") for item in merged.values()]
        builder = StorySpineBuilder(novel_id=plan.novel_id)
        builder.with_nodes(list(merged.values())).with_existing_spine(plan.spine)
        builder.with_edges(list(plan.spine.edges) if plan.spine else [])
        builder.with_edges(list(edges))
        spine = builder.build()
        payload["spine"] = spine.model_dump(mode="json")
        return validate_planning_ir(payload)

    def build_revision(self, plan: StoryPlanningIR, repository: PlanningRepository, *,
                       note: str = "", source: str = "planner",
                       revision_id: str = "") -> PlanningRevisionRecord:
        return repository.create(self.build_plan(plan), status="proposed",
                                 source=source,  # type: ignore[arg-type]
                                 note=note or "story spine assembly", revision_id=revision_id)

    # ---------------------------------------------------------------- analysis
    def validate(self, plan: StoryPlanningIR, *, revision_id: str = "",
                 inventory: PlotPressureInventory | None = None,
                 available_requirements: tuple[str, ...] = ()) -> AnalysisReport:
        return analyze_story_spine(plan, revision_id=revision_id, inventory=inventory,
                                   available_requirements=available_requirements)

    def coverage(self, plan: StoryPlanningIR, *, revision_id: str = "",
                 inventory: PlotPressureInventory | None = None
                 ) -> StorySpineCoverageReport:
        return build_coverage_report(plan, revision_id=revision_id, inventory=inventory)

    def pressure_inventory(self, plan: StoryPlanningIR, *, revision_id: str = ""
                           ) -> PlotPressureInventory:
        return build_plot_pressure_inventory(plan, revision_id=revision_id)

    @staticmethod
    def causal_order(plan: StoryPlanningIR) -> list[str]:
        return topological_order(plan)

    @staticmethod
    def roots(plan: StoryPlanningIR) -> list[str]:
        return root_nodes(plan)

    @staticmethod
    def terminals(plan: StoryPlanningIR) -> list[str]:
        return terminal_nodes(plan)


__all__ = ["StorySpineBuilder"]
