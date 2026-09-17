"""C04：Canon 依赖图（NetworkX）+ 时序/因果校验。

时间优先级：StoryState tick > explicit narrative order > display chapter number（仅 fallback）。
只对 temporal / prerequisite / causal 子图要求有序，不强迫整张图是 DAG。
"""

from __future__ import annotations

from typing import Any

import networkx as nx

TEMPORAL_RELATIONS = {"CAUSES", "REQUIRES"}


class CanonGraph:
    def __init__(self) -> None:
        self.graph = nx.MultiDiGraph()

    # ---- 构建 -------------------------------------------------------------
    def add_node(self, node_id: str, kind: str, *, order: int | None = None,
                 display_number: int | None = None, **data: Any) -> None:
        self.graph.add_node(node_id, kind=kind, order=order, display_number=display_number,
                            **data)

    def add_edge(self, from_id: str, to_id: str, relation: str, **data: Any) -> None:
        self.graph.add_edge(from_id, to_id, key=relation, relation=relation, **data)

    def time_of(self, node_id: str) -> int | None:
        """排序键：tick / explicit order 优先，display number 仅最后 fallback。"""

        node = self.graph.nodes.get(node_id) or {}
        for key in ("tick", "order"):
            value = node.get(key)
            if value is not None:
                return int(value)
        value = node.get("display_number")
        return int(value) if value is not None else None

    # ---- 便捷构造 ---------------------------------------------------------
    @classmethod
    def from_records(cls, facts: list[dict[str, Any]] | None = None,
                     events: list[dict[str, Any]] | None = None,
                     knowledge: list[dict[str, Any]] | None = None,
                     foreshadows: list[dict[str, Any]] | None = None,
                     entities: list[dict[str, Any]] | None = None,
                     dependencies: list[dict[str, Any]] | None = None) -> "CanonGraph":
        graph = cls()
        for row in facts or []:
            graph.add_node(row["fact_id"], "fact", order=row.get("order"), tick=row.get("tick"),
                           display_number=row.get("display_number"))
        for row in events or []:
            graph.add_node(row["event_id"], "event", order=row.get("order"), tick=row.get("tick"),
                           display_number=row.get("display_number"), **{
                               k: row.get(k) for k in
                               ("status", "canonical_event_id", "prerequisites", "location",
                                "participants", "requires_abilities", "requires_identities")})
        for row in knowledge or []:
            graph.add_node(row["knowledge_id"], "knowledge", order=row.get("order"),
                           tick=row.get("tick"), holder=row.get("holder_id"),
                           state=row.get("state"), learned_from=row.get("learned_from", ""),
                           source_event_id=row.get("source_event_id", ""))
            graph.add_edge(row["knowledge_id"], row["fact_id"], "KNOWS")
        for row in foreshadows or []:
            graph.add_node(row["foreshadow_id"], "foreshadow", order=row.get("order"),
                           plant_order=row.get("plant_order"), reveal_order=row.get("reveal_order"),
                           payoff_order=row.get("payoff_order"), status=row.get("status"))
            if row.get("plant_fact_id"):
                graph.add_edge(row["foreshadow_id"], row["plant_fact_id"], "PLANTED_BY")
            if row.get("payoff_fact_id"):
                graph.add_edge(row["foreshadow_id"], row["payoff_fact_id"], "PAID_OFF_BY")
        for row in entities or []:
            graph.add_node(row["entity_id"], "entity", order=row.get("order"),
                           dead_at=row.get("dead_at"), locations=row.get("locations"))
        for edge in dependencies or []:
            graph.add_edge(edge["from_id"], edge["to_id"], edge["relation"])
        return graph

    @classmethod
    def from_repository(cls, repository: Any, novel_id: str) -> "CanonGraph":
        """Canon DB → 校验图（唯一转换入口）。

        C11 加固：facts / prerequisites / dependencies 必须进入图，否则
        `knowledge_before_fact` / `prerequisite_missing` / `causal_cycle` 永远不可达。
        时间优先级仍是 tick > order > display_number（不是章节号）。
        """

        def _display(ref: Any) -> int | None:
            return getattr(ref, "display_number", None) if ref is not None else None

        return cls.from_records(
            facts=[{"fact_id": f.fact_id,
                    "order": _display(f.first_occurrence_ref),
                    "status": f.status} for f in repository.facts(novel_id)],
            events=[{"event_id": e.event_id, "order": e.temporal_position,
                     "status": e.status, "canonical_event_id": e.canonical_event_id,
                     "prerequisites": list(e.prerequisites), "location": e.location}
                    for e in repository.events(novel_id)],
            knowledge=[{"knowledge_id": k.knowledge_id, "fact_id": k.fact_id,
                        "order": k.learned_at, "state": k.state,
                        "learned_from": k.learned_from,
                        "source_event_id": k.source_event_id}
                       for k in repository.knowledge(novel_id)],
            foreshadows=[{"foreshadow_id": f.foreshadow_id,
                          "plant_order": _display(f.plant_ref),
                          "reveal_order": _display(f.reveal_ref),
                          "payoff_order": _display(f.payoff_ref),
                          "status": f.status, "plant_fact_id": f.planted_fact_id}
                         for f in repository.foreshadows(novel_id)],
            entities=[{"entity_id": e.entity_id, "dead_at": (e.data or {}).get("dead_at"),
                       "locations": (e.data or {}).get("locations")}
                      for e in repository.entities(novel_id)],
            dependencies=[{"from_id": d.from_id, "to_id": d.to_id, "relation": d.relation}
                          for d in repository.dependencies(novel_id)])


class CanonGraphValidator:
    def __init__(self, graph: CanonGraph) -> None:
        self.graph = graph

    # ---- 校验 -------------------------------------------------------------
    def run(self) -> list[dict[str, Any]]:
        findings: list[dict[str, Any]] = []
        for check in (self.causal_cycle, self.future_fact_dependency, self.reveal_before_plant,
                      self.payoff_before_reveal, self.knowledge_before_fact, self.knowledge_leak,
                      self.prerequisite_missing, self.resolved_event_reopened,
                      self.dead_character_action, self.ability_before_unlock,
                      self.identity_before_acquired, self.location_impossibility):
            findings.extend(check())
        return findings

    def _temporal_edges(self):
        for from_id, to_id, key in self.graph.graph.edges(keys=True):
            if key in TEMPORAL_RELATIONS:
                yield from_id, to_id, key

    def causal_cycle(self) -> list[dict[str, Any]]:
        sub = nx.DiGraph()
        for from_id, to_id, _ in self._temporal_edges():
            sub.add_edge(from_id, to_id)
        if sub.number_of_edges() == 0:
            return []
        try:
            cycle = nx.find_cycle(sub)
        except nx.NetworkXNoCycle:
            return []
        return [{"code": "CAUSAL_CYCLE", "nodes": [u for u, _ in cycle]}]

    def future_fact_dependency(self) -> list[dict[str, Any]]:
        findings = []
        for from_id, to_id, relation in self._temporal_edges():
            left, right = self.graph.time_of(from_id), self.graph.time_of(to_id)
            if left is None or right is None:
                continue
            if right < left:
                findings.append({"code": "FUTURE_FACT_DEPENDENCY", "relation": relation,
                                 "from": from_id, "to": to_id, "from_order": left, "to_order": right})
        return findings

    def reveal_before_plant(self) -> list[dict[str, Any]]:
        findings = []
        for node_id, data in self.graph.graph.nodes(data=True):
            if data.get("kind") != "foreshadow":
                continue
            plant, reveal = data.get("plant_order"), data.get("reveal_order")
            if plant is not None and reveal is not None and reveal < plant:
                findings.append({"code": "REVEAL_BEFORE_PLANT", "foreshadow": node_id})
        return findings

    def payoff_before_reveal(self) -> list[dict[str, Any]]:
        findings = []
        for node_id, data in self.graph.graph.nodes(data=True):
            if data.get("kind") != "foreshadow":
                continue
            reveal, payoff = data.get("reveal_order"), data.get("payoff_order")
            if payoff is not None and (reveal is None or payoff < reveal):
                findings.append({"code": "PAYOFF_BEFORE_REVEAL", "foreshadow": node_id})
        return findings

    def knowledge_before_fact(self) -> list[dict[str, Any]]:
        findings = []
        for knowledge_id, fact_id, key in self.graph.graph.edges(keys=True):
            if key != "KNOWS":
                continue
            known_at, fact_at = self.graph.time_of(knowledge_id), self.graph.time_of(fact_id)
            if known_at is None or fact_at is None:
                continue
            if known_at < fact_at:
                findings.append({"code": "KNOWLEDGE_BEFORE_FACT", "knowledge": knowledge_id,
                                 "fact": fact_id, "known_at": known_at, "fact_at": fact_at})
        return findings

    def knowledge_leak(self) -> list[dict[str, Any]]:
        findings = []
        for node_id, data in self.graph.graph.nodes(data=True):
            if data.get("kind") != "knowledge":
                continue
            if data.get("state") in ("known", "confirmed") and not (
                    data.get("learned_from") or data.get("source_event_id")):
                findings.append({"code": "KNOWLEDGE_LEAK", "knowledge": node_id,
                                 "holder": data.get("holder", "")})
        return findings

    def prerequisite_missing(self) -> list[dict[str, Any]]:
        findings = []
        nodes = set(self.graph.graph.nodes)
        for node_id, data in self.graph.graph.nodes(data=True):
            for prerequisite in data.get("prerequisites") or []:
                if prerequisite not in nodes:
                    findings.append({"code": "PREREQUISITE_MISSING", "node": node_id,
                                     "missing": prerequisite})
        return findings

    def resolved_event_reopened(self) -> list[dict[str, Any]]:
        findings = []
        by_track: dict[str, list[tuple[str, dict[str, Any]]]] = {}
        for node_id, data in self.graph.graph.nodes(data=True):
            if data.get("kind") != "event":
                continue
            track = data.get("canonical_event_id") or node_id
            by_track.setdefault(track, []).append((node_id, data))
        for track, rows in by_track.items():
            resolved_orders = [self.graph.time_of(node_id) for node_id, data in rows
                               if data.get("status") == "resolved"]
            if not resolved_orders:
                continue
            first_resolved = min(order for order in resolved_orders if order is not None)
            for node_id, data in rows:
                order = self.graph.time_of(node_id)
                if data.get("status") in ("planned", "ongoing") and order is not None \
                        and order > first_resolved:
                    findings.append({"code": "RESOLVED_EVENT_REOPENED", "track": track,
                                     "event": node_id, "resolved_at": first_resolved,
                                     "reopened_at": order})
        return findings

    def dead_character_action(self) -> list[dict[str, Any]]:
        findings = []
        for from_id, to_id, key in self.graph.graph.edges(keys=True):
            if key != "PARTICIPATES_IN":
                continue
            dead_at = (self.graph.graph.nodes.get(from_id) or {}).get("dead_at")
            order = self.graph.time_of(to_id)
            if dead_at is not None and order is not None and order > int(dead_at):
                findings.append({"code": "DEAD_CHARACTER_ACTION", "character": from_id,
                                 "event": to_id})
        return findings

    def ability_before_unlock(self) -> list[dict[str, Any]]:
        findings = []
        for node_id, data in self.graph.graph.nodes(data=True):
            for ability in data.get("requires_abilities") or []:
                ability_order = self.graph.time_of(ability) if ability in self.graph.graph else None
                node_order = self.graph.time_of(node_id)
                if ability_order is None or node_order is None:
                    continue
                if node_order < ability_order:
                    findings.append({"code": "ABILITY_BEFORE_UNLOCK", "node": node_id,
                                     "ability": ability})
        return findings

    def identity_before_acquired(self) -> list[dict[str, Any]]:
        findings = []
        for node_id, data in self.graph.graph.nodes(data=True):
            for identity in data.get("requires_identities") or []:
                identity_order = self.graph.time_of(identity) if identity in self.graph.graph else None
                node_order = self.graph.time_of(node_id)
                if identity_order is None or node_order is None:
                    continue
                if node_order < identity_order:
                    findings.append({"code": "IDENTITY_BEFORE_ACQUIRED", "node": node_id,
                                     "identity": identity})
        return findings

    def location_impossibility(self) -> list[dict[str, Any]]:
        findings = []
        for node_id, data in self.graph.graph.nodes(data=True):
            if data.get("kind") != "event":
                continue
            location = data.get("location")
            participants = data.get("participants") or []
            if not location or not participants:
                continue
            for participant in participants:
                node = self.graph.graph.nodes.get(participant) or {}
                allowed = node.get("locations")
                if allowed is not None and location not in allowed:
                    findings.append({"code": "LOCATION_IMPOSSIBILITY", "event": node_id,
                                     "character": participant, "location": location})
        return findings
