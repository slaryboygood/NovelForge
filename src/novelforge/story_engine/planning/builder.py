"""M2B：StoryPlanningBuilder —— deterministic assembly builder。

职责：把作者已经给出的 component（NovelIntent / WorldPlan / CharacterPlan / PlotNode …）
**组装**成完整 `StoryPlanningIR`，补默认结构、建立 refs、过 strict gate、产出 revision。

不做的事（留给 M3 / M2B 之后）：

- 不调用 LLM、不自动创造世界 / 人物 / 剧情；
- 不生成 StorySpine 的“创意内容”（只把作者给的节点与 prerequisites 变成结构化 DAG）；
- 不写 Canon / StoryState。
"""

from __future__ import annotations

from typing import Any, Iterable

from .enums import PLANNING_SCHEMA_VERSION, Provenance, RevisionSource, RevisionStatus
from .models import (
    ArcPlan,
    CharacterArc,
    CharacterPlan,
    FactionArc,
    FactionPlan,
    ForeshadowPlan,
    InformationArc,
    LocationGraph,
    LocationPlan,
    NovelIntent,
    PacingPlan,
    PlotNode,
    ProgressionTrack,
    RelationshipArc,
    SpineEdge,
    StoryPlanningIR,
    StorySpine,
    ThemePlan,
    TimelinePlan,
    VolumePlan,
    WorldPlan,
    new_planning_id,
)
from .repository import PlanningRepository, PlanningRevisionRecord
from .schemas import validate_planning_ir


class StoryPlanningBuilder:
    """确定性装配器：同一组输入永远产出同一个 plan（除了自动分配的随机 ID）。"""

    def __init__(self, *, novel_id: str, planning_id: str = "", title: str = "",
                 logline: str = "", canon_snapshot_digest: str = "",
                 source: str = "author", provenance: Provenance = "supplied") -> None:
        self.novel_id = novel_id
        self.planning_id = planning_id
        self.title = title
        self.logline = logline
        self.canon_snapshot_digest = canon_snapshot_digest
        self.source = source
        self.provenance = provenance
        self.intent: NovelIntent | None = None
        self.theme: ThemePlan | None = None
        self.world: WorldPlan | None = None
        self.characters: list[CharacterPlan] = []
        self.character_arcs: list[CharacterArc] = []
        self.relationship_arcs: list[RelationshipArc] = []
        self.factions: list[FactionPlan] = []
        self.faction_arcs: list[FactionArc] = []
        self.locations: list[LocationPlan] = []
        self.location_graph: LocationGraph | None = None
        self.timeline: TimelinePlan | None = None
        self.information_arcs: list[InformationArc] = []
        self.foreshadow_plans: list[ForeshadowPlan] = []
        self.progression_tracks: list[ProgressionTrack] = []
        self.pacing: PacingPlan | None = None
        self.plot_nodes: list[PlotNode] = []
        self.volumes: list[VolumePlan] = []
        self.arcs: list[ArcPlan] = []
        self.spine: StorySpine | None = None
        self.extra: dict[str, Any] = {}

    # ---------------------------------------------------------------- components
    def with_intent(self, intent: NovelIntent) -> "StoryPlanningBuilder":
        self.intent = intent
        return self

    def with_theme(self, theme: ThemePlan) -> "StoryPlanningBuilder":
        self.theme = theme
        return self

    def with_world(self, world: WorldPlan) -> "StoryPlanningBuilder":
        self.world = world
        return self

    def with_characters(self, characters: Iterable[CharacterPlan]) -> "StoryPlanningBuilder":
        self.characters.extend(characters)
        return self

    def with_character_arcs(self, arcs: Iterable[CharacterArc]) -> "StoryPlanningBuilder":
        self.character_arcs.extend(arcs)
        return self

    def with_relationship_arcs(self, arcs: Iterable[RelationshipArc]) -> "StoryPlanningBuilder":
        self.relationship_arcs.extend(arcs)
        return self

    def with_factions(self, factions: Iterable[FactionPlan]) -> "StoryPlanningBuilder":
        self.factions.extend(factions)
        return self

    def with_faction_arcs(self, arcs: Iterable[FactionArc]) -> "StoryPlanningBuilder":
        self.faction_arcs.extend(arcs)
        return self

    def with_locations(self, locations: Iterable[LocationPlan]) -> "StoryPlanningBuilder":
        self.locations.extend(locations)
        return self

    def with_location_graph(self, graph: LocationGraph) -> "StoryPlanningBuilder":
        self.location_graph = graph
        return self

    def with_timeline(self, timeline: TimelinePlan) -> "StoryPlanningBuilder":
        self.timeline = timeline
        return self

    def with_information_arcs(self, arcs: Iterable[InformationArc]) -> "StoryPlanningBuilder":
        self.information_arcs.extend(arcs)
        return self

    def with_foreshadow_plans(self, plans: Iterable[ForeshadowPlan]) -> "StoryPlanningBuilder":
        self.foreshadow_plans.extend(plans)
        return self

    def with_progression_tracks(self, tracks: Iterable[ProgressionTrack]
                                ) -> "StoryPlanningBuilder":
        self.progression_tracks.extend(tracks)
        return self

    def with_pacing(self, pacing: PacingPlan) -> "StoryPlanningBuilder":
        self.pacing = pacing
        return self

    def with_plot_nodes(self, nodes: Iterable[PlotNode]) -> "StoryPlanningBuilder":
        self.plot_nodes.extend(nodes)
        return self

    def with_volumes(self, volumes: Iterable[VolumePlan]) -> "StoryPlanningBuilder":
        self.volumes.extend(volumes)
        return self

    def with_arcs(self, arcs: Iterable[ArcPlan]) -> "StoryPlanningBuilder":
        self.arcs.extend(arcs)
        return self

    def with_spine(self, spine: StorySpine) -> "StoryPlanningBuilder":
        self.spine = spine
        return self

    # ---------------------------------------------------------------- defaults
    def apply_defaults(self) -> "StoryPlanningBuilder":
        """补默认结构 + 建立 refs（全部确定性，可重复调用）。"""

        self._default_spine()
        self._default_arc_nodes()
        self._default_volume_arcs()
        self._default_timeline_order()
        return self

    def _default_spine(self) -> None:
        if not self.plot_nodes:
            return
        node_ids = [node.node_id for node in self.plot_nodes]
        edges: list[SpineEdge] = []
        if self.spine is not None:
            known = set(self.spine.nodes) | set(node_ids)
            for edge in self.spine.edges:
                if edge.from_node_id in known and edge.to_node_id in known:
                    edges.append(edge)
        already = {(edge.from_node_id, edge.to_node_id) for edge in edges}
        for node in self.plot_nodes:
            for prerequisite in node.prerequisites:
                pair = (prerequisite, node.node_id)
                if pair not in already:
                    edges.append(SpineEdge(from_node_id=prerequisite, to_node_id=node.node_id,
                                           relation="requires"))
                    already.add(pair)
        required = {node_id for _, node_id in already}
        entries = [node_id for node_id in node_ids if node_id not in required]
        terminals = [node_id for node_id in node_ids
                     if not any(source == node_id for source, _ in already)]
        if self.spine is None:
            self.spine = StorySpine(
                spine_id=new_planning_id("spine"), novel_id=self.novel_id, nodes=node_ids,
                edges=edges, entry_node_ids=entries, terminal_node_ids=terminals,
                provenance=self.provenance, source=self.source)
            return
        nodes = list(self.spine.nodes)
        for node_id in node_ids:
            if node_id not in nodes:
                nodes.append(node_id)
        payload = self.spine.model_dump(mode="json")
        payload.update({"nodes": nodes,
                        "edges": [edge.model_dump(mode="json") for edge in edges],
                        "entry_node_ids": list(self.spine.entry_node_ids) or entries,
                        "terminal_node_ids": list(self.spine.terminal_node_ids) or terminals})
        self.spine = StorySpine.model_validate(payload)

    def _default_arc_nodes(self) -> None:
        for index, arc in enumerate(self.arcs):
            if arc.plot_nodes:
                continue
            node_ids = [step.node_id for step in arc.decision_chain if step.node_id]
            self.arcs[index] = arc.model_copy(update={"plot_nodes": node_ids})

    def _default_volume_arcs(self) -> None:
        for index, volume in enumerate(self.volumes):
            if volume.arc_ids:
                continue
            arc_ids = [arc.arc_id for arc in self.arcs if arc.volume_id == volume.volume_id]
            self.volumes[index] = volume.model_copy(update={"arc_ids": arc_ids})

    def _default_timeline_order(self) -> None:
        if self.timeline is None:
            return
        payload = self.timeline.model_dump(mode="json")
        for field in ("world_history", "story_timeline"):
            payload[field] = _index_order(payload.get(field) or [])
        for key, entries in (payload.get("character_timeline") or {}).items():
            payload["character_timeline"][key] = _index_order(entries)
        self.timeline = TimelinePlan.model_validate(payload)

    # ---------------------------------------------------------------- build
    def build(self) -> StoryPlanningIR:
        self.apply_defaults()
        payload: dict[str, Any] = {
            "schema_version": PLANNING_SCHEMA_VERSION,
            "planning_id": self.planning_id or new_planning_id("plan"),
            "novel_id": self.novel_id,
            "title": self.title,
            "logline": self.logline,
            "canon_snapshot_digest": self.canon_snapshot_digest,
            "provenance": self.provenance,
            "source": self.source,
            "intent": self.intent.model_dump(mode="json") if self.intent else None,
            "theme": self.theme.model_dump(mode="json") if self.theme else None,
            "world": self.world.model_dump(mode="json") if self.world else None,
            "characters": [item.model_dump(mode="json") for item in self.characters],
            "character_arcs": [item.model_dump(mode="json") for item in self.character_arcs],
            "relationship_arcs": [item.model_dump(mode="json")
                                  for item in self.relationship_arcs],
            "factions": [item.model_dump(mode="json") for item in self.factions],
            "faction_arcs": [item.model_dump(mode="json") for item in self.faction_arcs],
            "locations": [item.model_dump(mode="json") for item in self.locations],
            "location_graph": (self.location_graph.model_dump(mode="json")
                               if self.location_graph else None),
            "timeline": self.timeline.model_dump(mode="json") if self.timeline else None,
            "information_arcs": [item.model_dump(mode="json") for item in self.information_arcs],
            "foreshadow_plans": [item.model_dump(mode="json")
                                 for item in self.foreshadow_plans],
            "progression_tracks": [item.model_dump(mode="json")
                                   for item in self.progression_tracks],
            "pacing": self.pacing.model_dump(mode="json") if self.pacing else None,
            "plot_nodes": [item.model_dump(mode="json") for item in self.plot_nodes],
            "volumes": [item.model_dump(mode="json") for item in self.volumes],
            "arcs": [item.model_dump(mode="json") for item in self.arcs],
            "spine": self.spine.model_dump(mode="json") if self.spine else None,
        }
        payload.update(self.extra)
        return validate_planning_ir(payload)

    def build_revision(self, repository: PlanningRepository, *, branch_id: str = "main",
                       status: RevisionStatus = "draft", note: str = "",
                       source: RevisionSource | None = None) -> PlanningRevisionRecord:
        return repository.create(self.build(), branch_id=branch_id,
                                 source=source or ("planner" if self.provenance == "generated"
                                                   else "author"),
                                 status=status, note=note)


def _index_order(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """当一组时间线的 sequence_order 全是 0 时，按声明顺序补齐（确定性）。"""

    if not entries or any(int(entry.get("sequence_order") or 0) for entry in entries):
        return entries
    rows = []
    for index, entry in enumerate(entries):
        payload = dict(entry)
        payload["sequence_order"] = index
        rows.append(payload)
    return rows


__all__ = ["StoryPlanningBuilder"]
