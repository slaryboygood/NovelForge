"""M2B：StoryPlanningContextBuilder —— 按 purpose 构建 Planning context slice。

不把整本 Planning JSON 每次全塞给下游：每个 purpose 只包含当前任务需要的对象，
并且**必须声明边界**：planning_revision_id / canon_snapshot_digest / scope /
included_ids / excluded_domains / provenance，避免下游把 Planning future 当成 happened。
"""

from __future__ import annotations

from typing import Any, Iterable, Literal

from pydantic import Field

from novelforge.models import StrictModel

from .models import (
    ArcPlan,
    ForeshadowPlan,
    InformationArc,
    PlotNode,
    ProgressionTrack,
    RelationshipArc,
    StoryPlanningIR,
    TimelineEntry,
)
from .graphs import PlanningGraphBundle
from .graph_projection import project_graph
from .versioning import planning_digest

CONTEXT_PURPOSES: tuple[str, ...] = (
    "world", "character", "relationship", "faction", "location", "timeline",
    "information", "progression", "plot", "volume", "arc", "chapter_planning",
    # M5 long-form planning
    "resource", "equipment", "base", "map", "autonomous_action", "reward",
    # M6 plot synthesis / story spine
    "plot_synthesis", "story_spine", "conflict_escalation",
    # M8A outline compilation
    "volume_compile", "arc_compile", "outline_review",
    # M8B autonomous batch compiler
    "batch_compile", "batch_review", "batch_resume",
    # M9 arc → chapter compiler
    "chapter_compile", "chapter_review", "chapter_resume",
)

DOMAINS: dict[str, str] = {
    "intent": "intent", "theme": "theme", "world": "world", "character": "character",
    "relationship": "relationship", "faction": "faction", "location": "location",
    "timeline": "timeline", "information": "information", "foreshadow": "foreshadow",
    "progression": "progression", "plot": "plot", "volume": "volume", "arc": "arc",
    "pacing": "pacing",
    # M5
    "resource": "resource", "equipment": "equipment", "base": "base", "map": "map",
    "autonomous": "autonomous", "reward": "reward",
    "plot_synthesis": "plot", "story_spine": "spine", "conflict": "conflict",
    "volume": "volume", "outline": "outline",
}


class PlanningContext(StrictModel):
    """一份带边界声明的 context slice（future planning truth，不是 happened）。"""

    purpose: str = Field(min_length=2, max_length=32)
    planning_id: str = Field(default="", max_length=64)
    planning_revision_id: str = Field(default="", max_length=64)
    content_digest: str = Field(default="", max_length=64)
    canon_snapshot_digest: str = Field(default="", max_length=64)
    scope: str = Field(default="", max_length=200)
    included_ids: list[str] = Field(default_factory=list)
    detail_levels: dict[str, str] = Field(default_factory=dict)
    excluded_domains: list[str] = Field(default_factory=list)
    boundary: Literal["planning_future_not_happened"] = "planning_future_not_happened"
    provenance: Literal["planning"] = "planning"
    payload: dict[str, Any] = Field(default_factory=dict)


class StoryPlanningContextBuilder:
    def __init__(self, plan: StoryPlanningIR, *, revision_id: str = "",
                 content_digest: str = "", graphs: PlanningGraphBundle | None = None) -> None:
        self.plan = plan
        self.revision_id = revision_id
        self.content_digest = content_digest or planning_digest(plan)
        self.graphs = graphs

    # ---------------------------------------------------------------- 入口
    def build(self, purpose: str, *, ids: Iterable[str] = (),
              limits: dict[str, int] | None = None) -> PlanningContext:
        if purpose not in CONTEXT_PURPOSES:
            raise ValueError(f"未知 context purpose：{purpose}")
        selected = set(ids)
        limits = limits or {}
        payload, included, domains = self._slice(purpose, selected, limits)
        return PlanningContext(
            purpose=purpose, planning_id=self.plan.planning_id,
            planning_revision_id=self.revision_id, content_digest=self.content_digest,
            canon_snapshot_digest=self.plan.canon_snapshot_digest,
            scope=self._scope(purpose, selected), included_ids=sorted(included),
            detail_levels=self._detail_levels(included),
            excluded_domains=sorted(set(DOMAINS.values()) - domains - {"intent", "theme"}),
            payload=payload)

    def build_many(self, purposes: Iterable[str], *,
                   ids: Iterable[str] = ()) -> dict[str, PlanningContext]:
        return {purpose: self.build(purpose, ids=ids) for purpose in purposes}

    # ---------------------------------------------------------------- slice
    def _slice(self, purpose: str, selected: set[str], limits: dict[str, int]
               ) -> tuple[dict[str, Any], set[str], set[str]]:
        plan = self.plan
        included: set[str] = set()
        domains: set[str] = set()
        payload: dict[str, Any] = {}
        spine_slice = self._spine_slice(purpose, selected, limits)
        if spine_slice is not None:
            payload.update(spine_slice["payload"])
            included.update(spine_slice["ids"])
            domains.add(spine_slice["domain"])
            return payload, included, domains
        batch_slice = self._batch_slice(purpose, selected, limits)
        if batch_slice is not None:
            payload.update(batch_slice["payload"])
            included.update(batch_slice["ids"])
            domains.add(batch_slice["domain"])
            return payload, included, domains
        chapter_slice = self._chapter_slice(purpose, selected, limits)
        if chapter_slice is not None:
            payload.update(chapter_slice["payload"])
            included.update(chapter_slice["ids"])
            domains.add(chapter_slice["domain"])
            return payload, included, domains
        longform = self._longform_slice(purpose, selected)
        if longform is not None:
            payload.update(longform["payload"])
            included.update(longform["ids"])
            domains.add(longform["domain"])
            return payload, included, domains
        if plan.intent is not None:
            payload["intent"] = plan.intent.model_dump(mode="json")
            included.add(plan.intent.intent_id)
        if plan.theme is not None:
            payload["theme"] = plan.theme.model_dump(mode="json")
            included.add(plan.theme.theme_id)
        if purpose == "world":
            domains.add("world")
            if plan.world is not None:
                payload["world"] = plan.world.model_dump(mode="json")
                included.add(plan.world.world_id)
                included.update(rule.rule_id for rule in plan.world.world_rules)
        elif purpose == "character":
            domains.add("character")
            characters = [item for item in plan.characters
                          if not selected or item.character_id in selected]
            arc_ids = {item.character_arc_id for item in characters if item.character_arc_id}
            payload["characters"] = [item.model_dump(mode="json") for item in characters]
            payload["character_arcs"] = [
                item.model_dump(mode="json") for item in plan.character_arcs
                if item.arc_id in arc_ids or item.character_id in selected]
            included.update(item.character_id for item in characters)
            included.update(item["arc_id"] for item in payload["character_arcs"])
            if selected:
                relationships = [item for item in plan.relationship_arcs
                                 if selected & set(item.participants)]
                payload["relationship_arcs"] = [item.model_dump(mode="json")
                                                for item in relationships]
                included.update(item.arc_id for item in relationships)
        elif purpose == "relationship":
            domains.add("relationship")
            arcs = [item for item in plan.relationship_arcs
                    if not selected or item.arc_id in selected]
            payload["relationship_arcs"] = [item.model_dump(mode="json") for item in arcs]
            included.update(item.arc_id for item in arcs)
            participant_ids = {participant for item in arcs for participant in item.participants}
            payload["participants"] = [_character_summary(plan, participant)
                                       for participant in sorted(participant_ids)]
            included.update(participant_ids)
        elif purpose == "faction":
            domains.add("faction")
            factions = [item for item in plan.factions
                        if not selected or item.faction_id in selected]
            payload["factions"] = [item.model_dump(mode="json") for item in factions]
            payload["faction_arcs"] = [
                item.model_dump(mode="json") for item in plan.faction_arcs
                if not selected or item.faction_id in selected]
            included.update(item.faction_id for item in factions)
            included.update(item["arc_id"] for item in payload["faction_arcs"])
        elif purpose == "location":
            domains.add("location")
            locations = [item for item in plan.locations
                         if not selected or item.location_id in selected]
            payload["locations"] = [item.model_dump(mode="json") for item in locations]
            included.update(item.location_id for item in locations)
            graph = plan.location_graph
            if graph is not None:
                edges = [edge for edge in graph.edges
                         if not selected or (edge.from_location_id in selected
                                             and edge.to_location_id in selected)]
                payload["location_graph"] = {
                    "graph_id": graph.graph_id,
                    "location_ids": [item.location_id for item in locations],
                    "edges": [edge.model_dump(mode="json") for edge in edges]}
                included.add(graph.graph_id)
        elif purpose == "timeline":
            domains.add("timeline")
            if plan.timeline is not None:
                entries = _timeline_entries(plan)
                if selected:
                    entries = [entry for entry in entries
                               if entry.entry_id in selected
                               or selected & set(entry.participants)]
                payload["timeline"] = {
                    "timeline_id": plan.timeline.timeline_id,
                    "entries": [entry.model_dump(mode="json") for entry in entries]}
                included.add(plan.timeline.timeline_id)
                included.update(entry.entry_id for entry in entries)
        elif purpose == "information":
            domains.add("information")
            arcs = [item for item in plan.information_arcs
                    if not selected or item.arc_id in selected]
            payload["information_arcs"] = [item.model_dump(mode="json") for item in arcs]
            for arc in arcs:
                included.add(arc.arc_id)
                included.update(truth.truth_id for truth in arc.truths)
                included.update(move.move_id for move in arc.moves)
            payload["referenced_nodes"] = _node_summaries(
                plan, {move.node_id for arc in arcs for move in arc.moves if move.node_id})
        elif purpose == "progression":
            domains.add("progression")
            tracks = [item for item in plan.progression_tracks
                      if not selected or item.track_id in selected]
            payload["progression_tracks"] = [item.model_dump(mode="json") for item in tracks]
            for track in tracks:
                included.add(track.track_id)
                included.update(item.milestone_id for item in track.milestones)
            payload["referenced_nodes"] = _node_summaries(
                plan, {item.node_id for track in tracks for item in track.milestones
                       if item.node_id})
        elif purpose == "plot":
            domains.add("plot")
            nodes = [item for item in plan.plot_nodes
                     if not selected or item.node_id in selected]
            payload["plot_nodes"] = [item.model_dump(mode="json") for item in nodes]
            included.update(item.node_id for item in nodes)
            if plan.spine is not None:
                edges = [edge for edge in plan.spine.edges
                         if not selected or (edge.from_node_id in included
                                             and edge.to_node_id in included)]
                payload["spine"] = {"spine_id": plan.spine.spine_id,
                                    "nodes": [item.node_id for item in nodes],
                                    "edges": [edge.model_dump(mode="json") for edge in edges]}
                included.add(plan.spine.spine_id)
        elif purpose in ("volume", "arc"):
            domains.add(purpose)
            if purpose == "volume":
                volumes = [item for item in plan.volumes
                           if not selected or item.volume_id in selected]
                payload["volumes"] = [item.model_dump(mode="json") for item in volumes]
                payload["arcs"] = [_arc_summary(plan, item) for item in plan.arcs
                                   if not selected
                                   or item.volume_id in {v.volume_id for v in volumes}]
                included.update(item.volume_id for item in volumes)
                included.update(item["arc_id"] for item in payload["arcs"])
            else:
                arcs = [item for item in plan.arcs if not selected or item.arc_id in selected]
                payload["arcs"] = [item.model_dump(mode="json") for item in arcs]
                included.update(item.arc_id for item in arcs)
                node_ids = {node_id for item in arcs for node_id in item.plot_nodes}
                node_ids.update(step.node_id for item in arcs for step in item.decision_chain)
                if limits.get("node_limit"):
                    node_ids = set(sorted(node_ids)[:limits["node_limit"]])
                payload["plot_nodes"] = [node.model_dump(mode="json")
                                         for node in plan.plot_nodes
                                         if node.node_id in node_ids]
                included.update(node_ids)
            if limits.get("volume_limit") and purpose == "volume":
                payload["volumes"] = payload["volumes"][:limits["volume_limit"]]
        elif purpose == "chapter_planning":
            domains.update({"arc", "plot", "information", "foreshadow", "progression"})
            arcs = [item for item in plan.arcs
                    if not selected
                    or item.arc_id in selected
                    or item.detail_level == "chapter_ready"]
            payload["arcs"] = [item.model_dump(mode="json") for item in arcs]
            included.update(item.arc_id for item in arcs)
            node_ids = {node_id for item in arcs for node_id in item.plot_nodes}
            node_ids.update(step.node_id for item in arcs for step in item.decision_chain)
            payload["plot_nodes"] = [node.model_dump(mode="json") for node in plan.plot_nodes
                                     if node.node_id in node_ids]
            included.update(node_ids)
            related_truths = {truth_id for node in plan.plot_nodes
                              if node.node_id in node_ids for truth_id in node.truth_ids}
            related_foreshadows = {foreshadow_id for node in plan.plot_nodes
                                   if node.node_id in node_ids
                                   for foreshadow_id in node.foreshadow_ids}
            related_tracks = {track_id for node in plan.plot_nodes
                              if node.node_id in node_ids for track_id in node.track_ids}
            payload["information_arcs"] = [item.model_dump(mode="json")
                                           for item in plan.information_arcs
                                           if related_truths
                                           & {truth.truth_id for truth in item.truths}]
            payload["foreshadow_plans"] = [item.model_dump(mode="json")
                                           for item in plan.foreshadow_plans
                                           if item.foreshadow_id in related_foreshadows]
            payload["progression_tracks"] = [item.model_dump(mode="json")
                                             for item in plan.progression_tracks
                                             if item.track_id in related_tracks]
            included.update(related_truths | related_foreshadows | related_tracks)
            payload["planning_gaps"] = _planning_gaps(plan, arcs)
        if plan.pacing is not None and purpose in ("volume", "arc", "chapter_planning"):
            payload["pacing"] = plan.pacing.model_dump(mode="json")
            included.add(plan.pacing.pacing_id)
            domains.add("pacing")
        graph_slice = self._graph_slice(purpose, included)
        if graph_slice is not None:
            payload["graph"] = graph_slice["payload"]
            included.update(graph_slice["ids"])
            domains.add(graph_slice["domain"])
        return payload, included, domains

    # ---------------------------------------------------------------- graph slice
    def _spine_slice(self, purpose: str, selected: set[str], limits: dict[str, int]
                     ) -> dict[str, Any] | None:
        """M6 purpose：按目标 pressure / node 切片，不把整本 Planning 塞出去。"""

        if purpose in ("volume_compile", "arc_compile", "outline_review"):
            focus = set(selected)
            if purpose == "volume_compile":
                nodes = [node for node in self.plan.plot_nodes
                         if not focus or node.node_id in focus
                         or node.scheduled_volume_id in focus]
                ids = {node.node_id for node in nodes} | focus
                return {"domain": "volume",
                        "payload": {"plot_nodes": [node.model_dump(mode="json")
                                                   for node in nodes],
                                    "volumes": [item.model_dump(mode="json")
                                                for item in self.plan.volumes
                                                if not focus or item.volume_id in focus],
                                    "spine": (self.plan.spine.model_dump(mode="json")
                                              if self.plan.spine else None)},
                        "ids": ids}
            if purpose == "arc_compile":
                arcs = [item for item in self.plan.arcs
                        if not focus or item.arc_id in focus or item.volume_id in focus]
                node_ids = {node_id for arc in arcs for node_id in arc.plot_nodes}
                ids = {arc.arc_id for arc in arcs} | node_ids | focus
                return {"domain": "volume",
                        "payload": {"arcs": [item.model_dump(mode="json") for item in arcs],
                                    "plot_nodes": [node.model_dump(mode="json")
                                                   for node in self.plan.plot_nodes
                                                   if node.node_id in node_ids]},
                        "ids": ids}
            ids = {item.volume_id for item in self.plan.volumes}
            ids |= {item.arc_id for item in self.plan.arcs}
            ids |= {node.node_id for node in self.plan.plot_nodes}
            return {"domain": "outline",
                    "payload": {"volumes": [item.model_dump(mode="json")
                                            for item in self.plan.volumes],
                                "arcs": [item.model_dump(mode="json")
                                         for item in self.plan.arcs],
                                "plot_nodes": [node.model_dump(mode="json")
                                               for node in self.plan.plot_nodes],
                                "conflict_chains": [chain.model_dump(mode="json")
                                                    for chain in self.plan.conflict_chains]},
                    "ids": ids}
        if purpose not in ("plot_synthesis", "story_spine", "conflict_escalation"):
            return None
        from .plot_pressure import build_plot_pressure_inventory
        from .spine_analysis import build_coverage_report, root_nodes, terminal_nodes

        plan = self.plan
        inventory = build_plot_pressure_inventory(plan, revision_id=self.revision_id)
        if purpose == "plot_synthesis":
            limit = limits.get("pressure_limit", 12)
            pressures = [item for item in inventory.pressures
                         if item.state in ("open", "blocked")][:limit]
            focus = {item.source_ref for item in pressures}
            focus.update(ref for item in pressures for ref in item.affected_refs)
            if selected:
                focus &= selected
            nodes = [node for node in plan.plot_nodes
                     if not focus or node.node_id in focus
                     or set(node.participants) & focus
                     or node.location_id in focus
                     or set(node.foreshadow_ids) & focus or set(node.truth_ids) & focus]
            ids = {node.node_id for node in nodes} | focus
            return {"domain": "plot",
                    "payload": {"pressures": [item.model_dump(mode="json")
                                              for item in pressures],
                                "plot_nodes": [node.model_dump(mode="json")
                                               for node in nodes],
                                "spine": (plan.spine.model_dump(mode="json")
                                          if plan.spine else None)},
                    "ids": ids}
        if purpose == "story_spine":
            coverage = build_coverage_report(plan, revision_id=self.revision_id,
                                             inventory=inventory)
            ids = {node.node_id for node in plan.plot_nodes}
            return {"domain": "spine",
                    "payload": {"plot_nodes": [node.model_dump(mode="json")
                                               for node in plan.plot_nodes],
                                "spine": (plan.spine.model_dump(mode="json")
                                          if plan.spine else None),
                                "roots": root_nodes(plan), "terminals": terminal_nodes(plan),
                                "coverage": coverage.model_dump(mode="json")},
                    "ids": ids}
        chains = [chain for chain in plan.conflict_chains
                  if not selected or chain.conflict_id in selected
                  or set(chain.related_node_ids) & selected]
        ids = {chain.conflict_id for chain in chains}
        ids.update(stage.stage_id for chain in chains for stage in chain.stages)
        ids.update(chain.related_node_ids[i] for chain in chains
                   for i in range(len(chain.related_node_ids)))
        return {"domain": "conflict",
                "payload": {"conflict_chains": [chain.model_dump(mode="json")
                                                for chain in chains],
                            "plot_nodes": [node.model_dump(mode="json")
                                           for node in plan.plot_nodes
                                           if not selected or node.node_id in selected
                                           or node.conflict_chain_ref in ids]},
                "ids": ids}

    def _chapter_slice(self, purpose: str, selected: set[str], limits: dict[str, int]
                       ) -> dict[str, Any] | None:
        """M9 purpose：一个 Arc 的 chapter 编译上下文（不发送整本书）。"""

        if purpose not in ("chapter_compile", "chapter_review", "chapter_resume"):
            return None
        from .plot_pressure import build_plot_pressure_inventory

        plan = self.plan
        focus = set(selected)
        arcs = [arc for arc in plan.arcs if not focus or arc.arc_id in focus]
        if not arcs:
            return None
        node_ids = {node_id for arc in arcs for node_id in arc.plot_nodes}
        nodes = [node for node in plan.plot_nodes if node.node_id in node_ids]
        volume_ids = {arc.volume_id for arc in arcs}
        volumes = [item for item in plan.volumes if item.volume_id in volume_ids]
        arcs_rows = [item for item in plan.arcs if item.arc_id in {a.arc_id for a in arcs}]
        edges = [edge for edge in (plan.spine.edges if plan.spine else [])
                 if edge.to_node_id in node_ids]
        upstream = sorted({edge.from_node_id for edge in edges} - node_ids)
        information = [item for item in plan.information_arcs
                       if any(move.node_id in node_ids for move in item.moves)]
        foreshadow = [item for item in plan.foreshadow_plans
                      if any(move.node_id in node_ids for move in item.moves)]
        progression = [item for item in plan.progression_tracks
                       if any(milestone.node_id in node_ids for milestone in item.milestones)]
        resource = [item for item in plan.resource_flows if item.trigger_node_id in node_ids]
        equipment = [item for item in plan.equipment_plans if set(item.nodes()) & node_ids]
        maps = [item for expansion in plan.map_expansions for item in expansion.milestones
                if item.trigger_node_id in node_ids]
        rewards = [event for row in plan.reward_plans for event in row.events
                   if event.trigger_node_id in node_ids]
        autonomous = [item for item in plan.autonomous_actions
                      if item.trigger_ref in node_ids]
        relationships = [item for arc in plan.relationship_arcs for item in arc.stages
                         if item.trigger_node_id in node_ids]
        inventory = build_plot_pressure_inventory(plan, revision_id=self.revision_id)
        pressures = [item for item in inventory.pressures
                     if item.source_ref in node_ids
                     or (set(item.affected_refs) & focus)][:limits.get("pressure_limit", 12)]
        ids = node_ids | {arc.arc_id for arc in arcs} | volume_ids | focus
        ids.update(move.move_id for info in information for move in info.moves)
        ids.update(item.foreshadow_id for item in foreshadow)
        ids.update(item.track_id for item in progression)
        ids.update(item.flow_id for item in resource)
        ids.update(item.equipment_id for item in equipment)
        ids.update(item.milestone_id for item in maps)
        ids.update(item.reward_id for item in rewards)
        ids.update(item.action_id for item in autonomous)
        ids.update(item.pressure_id for item in pressures)
        payload = {
            "scope": {"kind": "arc", "arc_ids": [item.arc_id for item in arcs_rows],
                      "node_ids": sorted(node_ids)},
            "arcs": [item.model_dump(mode="json") for item in arcs_rows],
            "volumes": [item.model_dump(mode="json") for item in volumes],
            "plot_nodes": [item.model_dump(mode="json") for item in nodes],
            "spine_edges": [item.model_dump(mode="json") for item in edges],
            "upstream_dependencies": _node_summaries(plan, upstream),
            "information_arcs": [item.model_dump(mode="json") for item in information],
            "foreshadow_plans": [item.model_dump(mode="json") for item in foreshadow],
            "progression_tracks": [item.model_dump(mode="json") for item in progression],
            "resource_flows": [item.model_dump(mode="json") for item in resource],
            "equipment_plans": [item.model_dump(mode="json") for item in equipment],
            "map_milestones": [item.model_dump(mode="json") for item in maps],
            "reward_events": [item.model_dump(mode="json") for item in rewards],
            "autonomous_actions": [item.model_dump(mode="json") for item in autonomous],
            "relationship_stages": [item.model_dump(mode="json") for item in relationships],
            "pressure_carryover": [item.model_dump(mode="json") for item in pressures],
        }
        return {"domain": "chapter", "payload": payload, "ids": ids}

    def _batch_slice(self, purpose: str, selected: set[str], limits: dict[str, int]
                     ) -> dict[str, Any] | None:
        """M8B purpose：只给当前 scope + 上游依赖 + carryover + 相关 M4/M5/M6 切片。"""

        if purpose not in ("batch_compile", "batch_review", "batch_resume"):
            return None
        from .plot_pressure import build_plot_pressure_inventory

        plan = self.plan
        focus = set(selected)
        node_limit = limits.get("node_limit", 60)
        pressure_limit = limits.get("pressure_limit", 12)
        nodes = [node for node in plan.plot_nodes
                 if not focus or node.node_id in focus
                 or node.scheduled_volume_id in focus]
        node_ids = {node.node_id for node in nodes}
        volumes = [volume for volume in plan.volumes
                   if not focus or volume.volume_id in focus
                   or set(volume.major_nodes) & node_ids]
        volume_ids = {volume.volume_id for volume in volumes}
        arcs = [arc for arc in plan.arcs if arc.volume_id in volume_ids]
        arc_ids = {arc.arc_id for arc in arcs}
        edges = [edge for edge in (plan.spine.edges if plan.spine else [])
                 if edge.to_node_id in node_ids]
        upstream = sorted({edge.from_node_id for edge in edges} - node_ids)
        truths = {truth_id for node in nodes for truth_id in node.truth_ids}
        foreshadows = {item for node in nodes for item in node.foreshadow_ids}
        tracks = {item for node in nodes for item in node.track_ids}
        inventory = build_plot_pressure_inventory(plan, revision_id=self.revision_id)
        carryover = [item for item in inventory.pressures
                     if item.pressure_id in focus
                     or item.source_ref in (node_ids | volume_ids | arc_ids)
                     or (set(item.affected_refs) & focus)][:pressure_limit]
        information = [item for item in plan.information_arcs
                       if truths & {truth.truth_id for truth in item.truths}]
        foreshadow_rows = [item for item in plan.foreshadow_plans
                           if item.foreshadow_id in foreshadows]
        progression = [item for item in plan.progression_tracks
                       if item.track_id in tracks]
        resource_flows = [item for item in plan.resource_flows
                          if item.trigger_node_id in node_ids]
        equipment = [item for item in plan.equipment_plans
                     if node_ids & set(item.nodes())]
        map_milestones = [milestone for expansion in plan.map_expansions
                          for milestone in expansion.milestones
                          if milestone.trigger_node_id in node_ids]
        chains = [chain for chain in plan.conflict_chains
                  if set(chain.related_node_ids) & node_ids
                  or any(stage.trigger_node_id in node_ids for stage in chain.stages)]
        ids = set(node_ids) | volume_ids | arc_ids | focus
        ids.update(truth.truth_id for item in information for truth in item.truths)
        ids.update(item.foreshadow_id for item in foreshadow_rows)
        ids.update(item.track_id for item in progression)
        ids.update(item.flow_id for item in resource_flows)
        ids.update(item.equipment_id for item in equipment)
        ids.update(milestone.milestone_id for milestone in map_milestones)
        ids.update(chain.conflict_id for chain in chains)
        ids.update(item.pressure_id for item in carryover)
        payload = {
            "scope": {"kind": "batch", "volume_ids": sorted(volume_ids),
                      "arc_ids": sorted(arc_ids), "node_ids": sorted(node_ids)},
            "plot_nodes": [node.model_dump(mode="json") for node in nodes[:node_limit]],
            "volumes": [item.model_dump(mode="json") for item in volumes],
            "arcs": [item.model_dump(mode="json") for item in arcs],
            "spine_edges": [edge.model_dump(mode="json") for edge in edges],
            "upstream_dependencies": _node_summaries(plan, upstream),
            "carryover_pressures": [item.model_dump(mode="json") for item in carryover],
            "information_arcs": [item.model_dump(mode="json") for item in information],
            "foreshadow_plans": [item.model_dump(mode="json") for item in foreshadow_rows],
            "progression_tracks": [item.model_dump(mode="json") for item in progression],
            "resource_flows": [item.model_dump(mode="json") for item in resource_flows],
            "equipment_plans": [item.model_dump(mode="json") for item in equipment],
            "map_milestones": [item.model_dump(mode="json") for item in map_milestones],
            "conflict_chains": [item.model_dump(mode="json") for item in chains],
        }
        return {"domain": "outline", "payload": payload, "ids": ids}

    def _longform_slice(self, purpose: str, selected: set[str]) -> dict[str, Any] | None:
        """M5 专用 purpose：只给相关集合，不把整份 Planning IR 塞出去。"""

        plan = self.plan
        if purpose == "resource":
            units = [item for item in plan.unit_defs
                     if not selected or item.unit_id in selected]
            plans = [item for item in plan.resource_plans
                     if not selected or item.identity() in selected]
            flows = [item for item in plan.resource_flows
                     if not selected or item.identity() in selected]
            ids = {item.unit_id for item in units} | {item.identity() for item in plans} \
                | {item.flow_id for item in flows}
            return {"domain": "resource",
                    "payload": {"unit_defs": [item.model_dump(mode="json") for item in units],
                                "resource_plans": [item.model_dump(mode="json")
                                                   for item in plans],
                                "resource_flows": [item.model_dump(mode="json")
                                                   for item in flows]},
                    "ids": ids}
        if purpose == "equipment":
            rows = [item for item in plan.equipment_plans
                    if not selected or item.equipment_id in selected
                    or item.equipment_ref in selected]
            return {"domain": "equipment",
                    "payload": {"equipment_plans": [item.model_dump(mode="json")
                                                    for item in rows]},
                    "ids": {item.equipment_id for item in rows}}
        if purpose == "base":
            rows = [item for item in plan.base_progressions
                    if not selected or item.base_id in selected or item.base_ref in selected]
            ids = {item.base_id for item in rows}
            ids.update(stage.stage_id for item in rows for stage in item.stages)
            return {"domain": "base",
                    "payload": {"base_progressions": [item.model_dump(mode="json")
                                                      for item in rows]},
                    "ids": ids}
        if purpose == "map":
            rows = [item for item in plan.map_expansions
                    if not selected or item.expansion_id in selected
                    or any(milestone.location_ref in selected for milestone in item.milestones)]
            ids = {item.expansion_id for item in rows}
            ids.update(milestone.milestone_id for item in rows for milestone in item.milestones)
            ids.update(milestone.location_ref for item in rows for milestone in item.milestones)
            payload: dict[str, Any] = {"map_expansions": [item.model_dump(mode="json")
                                                          for item in rows]}
            if self.graphs is not None:
                focus = {milestone.location_ref for item in rows
                         for milestone in item.milestones}
                projection = project_graph(self.graphs.location,
                                           revision_id=self.graphs.revision_id,
                                           content_digest=self.graphs.content_digest,
                                           node_ids=focus)
                if projection.nodes:
                    payload["graph"] = projection.to_context_slice()
                    ids.update(projection.node_ids())
            return {"domain": "map", "payload": payload, "ids": ids}
        if purpose == "autonomous_action":
            rows = [item for item in plan.autonomous_actions
                    if not selected or item.action_id in selected
                    or item.actor_ref in selected]
            relations = [item for item in plan.faction_relations
                         if not selected or item.relation_id in selected
                         or item.from_faction_id in selected
                         or item.to_faction_id in selected]
            ids = {item.action_id for item in rows} | {item.relation_id for item in relations}
            ids.update(item.actor_ref for item in rows)
            return {"domain": "autonomous",
                    "payload": {"autonomous_actions": [item.model_dump(mode="json")
                                                       for item in rows],
                                "faction_relations": [item.model_dump(mode="json")
                                                      for item in relations]},
                    "ids": ids}
        if purpose == "reward":
            rows = [item for item in plan.reward_plans
                    if not selected or item.reward_plan_id in selected]
            ids = {item.reward_plan_id for item in rows}
            ids.update(event.reward_id for item in rows for event in item.events)
            return {"domain": "reward",
                    "payload": {"reward_plans": [item.model_dump(mode="json")
                                                 for item in rows]},
                    "ids": ids}
        return None

    def _graph_slice(self, purpose: str, included: set[str]) -> dict[str, Any] | None:
        """location / relationship / faction / plot 只带需要的那张图的切片。"""

        if self.graphs is None or purpose not in ("location", "relationship", "faction", "plot"):
            return None
        plan = self.plan
        if purpose == "plot":
            focus: set[str] = set()
            for node in plan.plot_nodes:
                if node.node_id in included:
                    focus.add(node.location_id)
                    focus.update(node.participants)
            focus.discard("")
            if not focus:
                return None
            projection = project_graph(self.graphs.combined,
                                       revision_id=self.graphs.revision_id,
                                       content_digest=self.graphs.content_digest,
                                       node_ids=focus)
            return {"domain": "combined", "payload": projection.to_context_slice(),
                    "ids": projection.node_ids()}
        domain = purpose  # location / relationship / faction
        projection = project_graph(self.graphs.graph(domain),  # type: ignore[arg-type]
                                   revision_id=self.graphs.revision_id,
                                   content_digest=self.graphs.content_digest,
                                   node_ids=included)
        if not projection.nodes:
            return None
        return {"domain": domain, "payload": projection.to_context_slice(),
                "ids": projection.node_ids()}

    def _scope(self, purpose: str, selected: set[str]) -> str:
        if not selected:
            return f"whole_plan:{purpose}"
        rows = sorted(selected)
        head = ",".join(rows[:12])
        suffix = f"…(+{len(rows) - 12})" if len(rows) > 12 else ""
        return (f"{purpose}:{head}{suffix}")[:200]

    def _detail_levels(self, included: set[str]) -> dict[str, str]:
        rows = {}
        for kind, model in _entries(self.plan):
            identifier = _entry_id(kind, model)
            if identifier and identifier in included:
                rows[identifier] = getattr(model, "detail_level", "concept")
        return rows


# ---------------------------------------------------------------------- 辅助
def _entries(plan: StoryPlanningIR):
    from .models import iter_planning_entries
    return iter_planning_entries(plan)


def _entry_id(kind: str, model) -> str:
    from .models import entry_id
    return entry_id(kind, model)


def _character_summary(plan: StoryPlanningIR, character_id: str) -> dict[str, Any]:
    character = next((item for item in plan.characters
                      if item.character_id == character_id), None)
    if character is None:
        faction = next((item for item in plan.factions
                        if item.faction_id == character_id), None)
        if faction is not None:
            return {"participant_id": faction.faction_id, "kind": "faction",
                    "display_name": faction.display_name, "entity_ref": faction.entity_ref}
        return {"participant_id": character_id, "kind": "external", "display_name": "",
                "entity_ref": character_id}
    return {"participant_id": character.character_id, "kind": "character",
            "display_name": character.display_name, "entity_ref": character.entity_ref,
            "story_function": character.story_function,
            "external_goal": character.external_goal, "fear": character.fear}


def _node_summaries(plan: StoryPlanningIR, node_ids: Iterable[str]) -> list[dict[str, Any]]:
    wanted = set(node_ids)
    return [{"node_id": node.node_id, "purpose": node.purpose, "importance": node.importance,
             "detail_level": node.detail_level, "scheduled_volume_id": node.scheduled_volume_id}
            for node in plan.plot_nodes if node.node_id in wanted]


def _arc_summary(plan: StoryPlanningIR, arc: ArcPlan) -> dict[str, Any]:
    return {"arc_id": arc.arc_id, "volume_id": arc.volume_id, "title": arc.title,
            "arc_goal": arc.arc_goal, "detail_level": arc.detail_level,
            "chapter_budget": arc.chapter_budget, "plot_nodes": list(arc.plot_nodes)}


def _timeline_entries(plan: StoryPlanningIR) -> list[TimelineEntry]:
    timeline = plan.timeline
    if timeline is None:
        return []
    rows = list(timeline.world_history) + list(timeline.story_timeline)
    for entries in timeline.character_timeline.values():
        rows.extend(entries)
    return rows


def _planning_gaps(plan: StoryPlanningIR, arcs: list[ArcPlan]) -> list[dict[str, str]]:
    """还没到 chapter_ready 的结构（Progressive Elaboration 的剩余工作）。"""

    gaps: list[dict[str, str]] = []
    for arc in arcs:
        if arc.detail_level != "chapter_ready":
            gaps.append({"kind": "arc", "id": arc.arc_id,
                         "reason": f"detail_level={arc.detail_level}"})
        if not arc.decision_chain:
            gaps.append({"kind": "arc", "id": arc.arc_id, "reason": "缺少 decision_chain"})
    for node in plan.plot_nodes:
        if not node.scheduled_volume_id:
            gaps.append({"kind": "plot_node", "id": node.node_id, "reason": "unscheduled"})
    for volume in plan.volumes:
        if volume.detail_level not in ("arc", "chapter_ready"):
            gaps.append({"kind": "volume", "id": volume.volume_id,
                         "reason": f"detail_level={volume.detail_level}"})
    return gaps


__all__ = ["CONTEXT_PURPOSES", "DOMAINS", "PlanningContext", "StoryPlanningContextBuilder"]
