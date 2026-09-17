"""M4：Planning Graph Validator —— 图级 + **跨图**一致性校验。

统一 findings 结构（code / severity / domain / source_id / related_ids / message / evidence），
供后续 Repair Center（M15）直接消费。severity 只分三档：

- ERROR：结构不可能、悬空引用、硬冲突；
- WARNING：潜在叙事风险（孤立地点、阶段跳跃、长期无互动势力）；
- INFO：分析提示（例如势力领土重叠）。

文学选择不会被判 ERROR：例如 public_goal 与 hidden_goal 不同、势力之间有双向敌意、
地点危险度高，这些都是允许的。
"""

from __future__ import annotations

import re
from typing import Iterable, Literal

from pydantic import Field

from novelforge.models import StrictModel

from .findings import AnalysisReport, PlanningFinding, Severity
from .graphs import (
    PlanningGraphBundle,
    build_planning_graphs,
    declared_access,
    entry_locations,
    reachable_locations,
)
from .models import StoryPlanningIR
from .versioning import planning_digest

NODE_TOKEN = re.compile(r"\b(NODE_[A-Z0-9_]+)\b")

# M4 的 finding / report 结构 = M5 的通用 PlanningFinding / AnalysisReport（向后兼容别名）
GraphFinding = PlanningFinding
GraphReport = AnalysisReport


class PlanningGraphValidator:
    """输入 Planning IR，输出 findings；不写任何 truth。"""

    def __init__(self, *, known_entity_ids: Iterable[str] = (),
                 known_canon_ids: Iterable[str] = (),
                 known_chapter_ir_ids: Iterable[str] = (),
                 allow_external_refs: bool = True) -> None:
        self.known_entity_ids = set(known_entity_ids)
        self.known_canon_ids = set(known_canon_ids)
        self.known_chapter_ir_ids = set(known_chapter_ir_ids)
        self.allow_external_refs = allow_external_refs
        self._plan: StoryPlanningIR | None = None
        self._report = GraphReport()
        self._graphs: PlanningGraphBundle | None = None

    # ---------------------------------------------------------------- 入口
    def validate(self, plan: StoryPlanningIR, *, revision_id: str = "",
                 available_requirements: Iterable[str] = ()) -> GraphReport:
        self._plan = plan
        self._graphs = build_planning_graphs(plan, revision_id=revision_id)
        self._report = GraphReport(novel_id=plan.novel_id, planning_id=plan.planning_id,
                                   revision_id=revision_id,
                                   content_digest=planning_digest(plan))
        self._check_locations(available_requirements)
        self._check_relationships()
        self._check_factions()
        self._check_cross_graph()
        for finding in self._report.findings:
            if isinstance(finding.evidence, dict):
                finding.evidence.setdefault("revision_id", revision_id)
        return self._report

    # ---------------------------------------------------------------- 工具
    def _add(self, code: str, severity: Severity, domain: str, source_id: str,
             message: str, *, related: Iterable[str] = (), **evidence: object) -> None:
        self._report.findings.append(GraphFinding(
            code=code, severity=severity, domain=domain, source_id=source_id,
            related_ids=sorted({item for item in related if item}), message=message[:300],
            evidence={key: value for key, value in evidence.items() if value is not None}))

    def _external_ok(self, ref: str) -> bool:
        if not ref:
            return True
        if ref in self.known_entity_ids or ref in self.known_canon_ids \
                or ref in self.known_chapter_ir_ids:
            return True
        return self.allow_external_refs and ref.split("_", 1)[0] in (
            "ENTITY", "FACT", "EVENT", "KNW", "REL", "FS", "CON", "uuid")

    # ---------------------------------------------------------------- location
    def _check_locations(self, available_requirements: Iterable[str]) -> None:
        plan = self._require_plan()
        graph = self._require_graphs().location
        location_ids = {item.location_id for item in plan.locations}
        for node in graph.nodes:
            if node.node_id not in location_ids:
                self._add("LOCATION_DANGLING_REF", "ERROR", "location", node.node_id,
                          "地图引用了不存在的地点", related=[node.node_id])
        pairs: dict[tuple[str, str], list] = {}
        seen_routes: set[tuple[str, str, str]] = set()
        for edge in graph.edges:
            meta = edge.metadata
            if edge.source_id == edge.target_id:
                self._add("LOCATION_SELF_LOOP", "WARNING", "location", edge.edge_id,
                          "路线自环：需要语义理由（例如巡逻 / 返回同一地点）",
                          related=[edge.source_id])
            key = (edge.source_id, edge.target_id)
            pairs.setdefault(key, []).append(edge)
            route_key = (edge.source_id, edge.target_id, str(meta.get("route", "")))
            if route_key in seen_routes and route_key[2]:
                self._add("LOCATION_DUPLICATE_ROUTE", "WARNING", "location", edge.edge_id,
                          "同一对地点出现重复路线", related=[edge.source_id, edge.target_id],
                          route=route_key[2])
            seen_routes.add(route_key)
            distance = float(meta.get("distance") or 0)
            travel = str(meta.get("travel_time") or "")
            if distance > 0 and not travel:
                self._add("LOCATION_INVALID_TRAVEL", "WARNING", "location", edge.edge_id,
                          "有距离却没有 travel_time", related=[edge.source_id, edge.target_id],
                          distance=distance)
            requirement = str(meta.get("requirement") or "")
            if requirement and not self._requirement_known(requirement):
                self._add("LOCATION_IMPOSSIBLE_REQUIREMENT", "ERROR", "location",
                          edge.edge_id, "路线要求引用了不存在的规则 / 成长 / 事实",
                          related=[edge.source_id, edge.target_id], requirement=requirement)
        for (source, target), edges in sorted(pairs.items()):
            if source == target:
                continue
            values = sorted({str(edge.metadata.get("availability") or "") for edge in edges
                             if edge.metadata.get("availability")})
            if len(values) > 1:
                self._add("LOCATION_CONTRADICTORY_AVAILABILITY", "WARNING", "location",
                          f"{source}->{target}", "同一路线出现互斥的可用时间",
                          related=[source, target], availability=values)
            requirements = sorted({str(edge.metadata.get("requirement") or "") for edge in edges
                                   if edge.metadata.get("requirement")})
            entry_requirement = next((item.entry_requirement for item in plan.locations
                                      if item.location_id == target), "")
            if requirements and entry_requirement \
                    and entry_requirement in requirements and len(requirements) > 1:
                self._add("LOCATION_ENTRY_ROUTE_CONFLICT", "WARNING", "location",
                          f"{source}->{target}",
                          "进入条件与路线条件叠加，可能永远进不去",
                          related=[source, target], entry_requirement=entry_requirement,
                          route_requirements=requirements)
        for location_id in graph.isolated():
            self._add("LOCATION_ISOLATED", "WARNING", "location", location_id,
                      "地点没有任何路线连接", related=[location_id])
        entries = entry_locations(plan) or sorted(location_ids)
        structural_requirements, declared_availability = _structural_access(plan)
        reachable = _reachable_from(plan, entries,
                                    available_requirements=structural_requirements,
                                    available_availability=declared_availability)
        # availability（白天 / 雨季）是时间窗口，不是解锁条件：默认视为可满足
        gated = _reachable_from(plan, entries,
                                available_requirements=available_requirements,
                                available_availability=declared_availability)
        for location in plan.locations:
            if location.location_id not in reachable:
                self._add("LOCATION_UNREACHABLE", "WARNING", "location", location.location_id,
                          "从任何入口都不可达（检查 entry_requirement / route requirement）",
                          related=[location.location_id],
                          entry_requirement=location.entry_requirement)
            elif location.location_id not in gated:
                self._add("LOCATION_GATED", "INFO", "location", location.location_id,
                          "结构上可达，但需要先满足计划条件才开放",
                          related=[location.location_id],
                          entry_requirement=location.entry_requirement)
        required_nodes: dict[str, list[str]] = {}
        for node in plan.plot_nodes:
            if node.location_id and node.location_id in location_ids:
                required_nodes.setdefault(node.location_id, []).append(node.node_id)
        for location_id, node_ids in sorted(required_nodes.items()):
            if location_id not in reachable:
                self._add("LOCATION_UNREACHABLE_REQUIRED_NODE", "ERROR", "location",
                          location_id,
                          "PlotNode 需要的地点结构上不可达（不存在任何合法路径）",
                          related=sorted(node_ids))
            elif location_id not in gated:
                self._add("LOCATION_REQUIRED_NODE_GATED", "WARNING", "location", location_id,
                          "PlotNode 需要的地点目前被计划条件锁住，需要先解锁",
                          related=sorted(node_ids))
        expansion = sorted({location_id for volume in plan.volumes
                            for location_id in volume.location_expansion})
        for location_id in expansion:
            if location_id not in location_ids:
                self._add("LOCATION_EXPANSION_DANGLING", "ERROR", "location", location_id,
                          "卷的地图扩张引用了不存在的地点", related=[location_id])
            elif location_id not in reachable:
                self._add("LOCATION_EXPANSION_UNREACHABLE", "WARNING", "location",
                          location_id, "计划扩张的地点当前不可达", related=[location_id])

    def _requirement_known(self, requirement: str) -> bool:
        plan = self._require_plan()
        tokens = [token for token in re.split(r"[^A-Za-z0-9_]+", requirement) if token]
        known = {item.rule_id for item in (plan.world.world_rules if plan.world else [])}
        known |= {item.track_id for item in plan.progression_tracks}
        known |= {item.milestone_id for track in plan.progression_tracks
                  for item in track.milestones}
        known |= {item.node_id for item in plan.plot_nodes}
        known |= {item.truth_id for arc in plan.information_arcs for item in arc.truths}
        candidates = [token for token in tokens
                      if token.split("_", 1)[0] in ("RULE", "TRACK", "TRACKMILE", "NODE",
                                                    "TRUTH", "FACT", "EVENT", "CON", "KNW")]
        return all(token in known or self._external_ok(token) for token in candidates)

    # ---------------------------------------------------------------- relationship
    def _check_relationships(self) -> None:
        plan = self._require_plan()
        character_ids = {item.character_id for item in plan.characters}
        faction_ids = {item.faction_id for item in plan.factions}
        node_ids = {item.node_id for item in plan.plot_nodes}
        seen_identity: dict[tuple[str, ...], str] = {}
        for arc in plan.relationship_arcs:
            for participant in arc.participants:
                if participant in character_ids or participant in faction_ids:
                    continue
                if not self._external_ok(participant):
                    self._add("RELATIONSHIP_DANGLING_PARTICIPANT", "ERROR", "relationship",
                              arc.arc_id, "关系参与者既不是 planning 人物 / 势力，也不是已知实体",
                              related=[participant])
            identity = tuple(sorted(arc.participants))
            if identity in seen_identity:
                self._add("RELATIONSHIP_REPEATED_IDENTITY", "ERROR", "relationship",
                          arc.arc_id, "同一组参与者出现重复关系身份",
                          related=[seen_identity[identity]])
            seen_identity[identity] = arc.arc_id
            labels = [stage.label for stage in arc.stages if stage.label]
            duplicates = sorted({label for label in labels if labels.count(label) > 1})
            if duplicates:
                self._add("RELATIONSHIP_STAGE_DUPLICATE_LABEL", "ERROR", "relationship",
                          arc.arc_id, "关系阶段标签重复（阶段顺序无法区分）",
                          related=duplicates)
            for index, stage in enumerate(arc.stages):
                if not stage.label and not stage.stage_id:
                    self._add("RELATIONSHIP_STAGE_WITHOUT_LABEL", "WARNING", "relationship",
                              f"{arc.arc_id}::stage{index}", "关系阶段没有 label / stage_id")
                if not stage.trigger and not stage.trigger_node_id:
                    self._add("RELATIONSHIP_STAGE_WITHOUT_TRIGGER", "WARNING", "relationship",
                              f"{arc.arc_id}::stage{index}",
                              "关系阶段没有触发条件（可能推进不动）", related=[arc.arc_id])
                if stage.trigger_node_id and stage.trigger_node_id not in node_ids:
                    self._add("STAGE_TRIGGER_NODE_UNKNOWN", "ERROR", "relationship",
                              f"{arc.arc_id}::stage{index}",
                              "显式 trigger_node_id 不是已有 PlotNode",
                              related=[stage.trigger_node_id])
            # legacy fallback：没有显式 trigger_node_id 时才解析 trigger 文本
            legacy_stages = [stage for stage in arc.stages if not stage.trigger_node_id]
            for token in _node_tokens([stage.trigger for stage in legacy_stages]):
                if token not in node_ids:
                    self._add("RELATIONSHIP_TRIGGER_UNKNOWN_NODE", "WARNING", "relationship",
                              arc.arc_id, "关系阶段触发引用了不存在的 PlotNode",
                              related=[token])
            if arc.irreversible_node:
                if arc.irreversible_node not in node_ids:
                    self._add("RELATIONSHIP_IRREVERSIBLE_UNKNOWN_NODE", "ERROR",
                              "relationship", arc.arc_id,
                              "不可逆节点不是已知 PlotNode",
                              related=[arc.irreversible_node])
                self._check_stage_timeline(arc, node_ids)
                if not any(stage.irreversible for stage in arc.stages):
                    self._add("RELATIONSHIP_IRREVERSIBLE_NOT_DECLARED", "WARNING",
                              "relationship", arc.arc_id,
                              "声明了 irreversible_node，但没有任何阶段标 irreversible")
                break_index = next((index for index, stage in enumerate(arc.stages)
                                    if stage.irreversible), None)
                if break_index is not None:
                    before = {stage.state for stage in arc.stages[:break_index] if stage.state}
                    for stage in arc.stages[break_index + 1:]:
                        if stage.state and stage.state in before:
                            self._add("RELATIONSHIP_IRREVERSIBLE_REGRESSION", "ERROR",
                                      "relationship", arc.arc_id,
                                      "不可逆阶段之后回到更早的关系状态",
                                      related=[stage.stage_id], state=stage.state)
                        if not stage.state:
                            self._add("RELATIONSHIP_STAGE_AFTER_IRREVERSIBLE_EMPTY", "ERROR",
                                      "relationship", arc.arc_id,
                                      "不可逆之后的状态不能为空", related=[stage.stage_id])

    def _check_stage_timeline(self, arc, node_ids: set[str]) -> None:
        """用 timeline 的 sequence_order 抓明显倒置：阶段触发的节点早于不可逆点。"""

        plan = self._require_plan()
        orders = _node_sequence_order(plan)
        cutoff = orders.get(arc.irreversible_node)
        if cutoff is None:
            return
        for stage in arc.stages:
            tokens = [stage.trigger_node_id] if stage.trigger_node_id \
                else NODE_TOKEN.findall(stage.trigger or "")
            for token in tokens:
                order = orders.get(token)
                if token in node_ids and order is not None and order < cutoff:
                    self._add("RELATIONSHIP_STAGE_TRIGGER_BEFORE_IRREVERSIBLE", "WARNING",
                              "relationship", arc.arc_id,
                              "关系阶段引用了早于不可逆点的节点（时间线倒置）",
                              related=[token, arc.irreversible_node],
                              sequence_order=order, irreversible_order=cutoff)

    # ---------------------------------------------------------------- faction
    def _check_factions(self) -> None:
        plan = self._require_plan()
        faction_ids = {item.faction_id for item in plan.factions}
        location_ids = {item.location_id for item in plan.locations}
        node_ids = {item.node_id for item in plan.plot_nodes}
        territory_claims: dict[str, list[str]] = {}
        for faction in plan.factions:
            for ally in faction.allies:
                if ally == faction.faction_id:
                    self._add("FACTION_SELF_ALIGNMENT", "ERROR", "faction", faction.faction_id,
                              "势力不能与自己结盟")
                if ally in faction.enemies:
                    severity: Severity = "WARNING" if faction.note else "ERROR"
                    self._add("FACTION_ALLY_AND_ENEMY", severity, "faction",
                              faction.faction_id, "同一势力同时是盟友与敌人（需要解释）",
                              related=[ally])
            for enemy in faction.enemies:
                if enemy == faction.faction_id:
                    self._add("FACTION_SELF_ALIGNMENT", "ERROR", "faction",
                              faction.faction_id, "势力不能与自己敌对")
                if enemy not in faction_ids and not self._external_ok(enemy):
                    self._add("FACTION_DANGLING_REF", "ERROR", "faction", faction.faction_id,
                              "敌对目标既不是 planning 势力，也不是已知实体", related=[enemy])
            for ally in faction.allies:
                if ally not in faction_ids and not self._external_ok(ally):
                    self._add("FACTION_DANGLING_REF", "ERROR", "faction", faction.faction_id,
                              "结盟对象既不是 planning 势力，也不是已知实体", related=[ally])
            for territory in faction.territory:
                territory_claims.setdefault(territory, []).append(faction.faction_id)
                if territory not in location_ids:
                    self._add("FACTION_TERRITORY_DANGLING", "ERROR", "faction",
                              faction.faction_id, "势力领土不是 planning 地点",
                              related=[territory])
            if not faction.territory and not faction.allies and not faction.enemies \
                    and not any(arc.faction_id == faction.faction_id
                                for arc in plan.faction_arcs) \
                    and not any(faction.faction_id in arc.participants
                                for arc in plan.relationship_arcs):
                self._add("FACTION_NO_PRESSURE_PATH", "WARNING", "faction",
                          faction.faction_id,
                          "势力没有任何领土 / 结盟 / 敌对 / 关系弧：无法产生 autonomous pressure")
            if faction.public_goal and faction.hidden_goal \
                    and faction.public_goal != faction.hidden_goal:
                self._add("FACTION_GOAL_DIVERGENCE", "INFO", "faction", faction.faction_id,
                          "公开目标与隐藏目标不同（允许，可用于叙事张力）",
                          public_goal=faction.public_goal, hidden_goal=faction.hidden_goal)
        for location_id, factions in sorted(territory_claims.items()):
            if len(factions) > 1:
                self._add("FACTION_TERRITORY_OVERLAP", "INFO", "faction", location_id,
                          "多个势力声称同一地点（领土重叠，需剧情解释）",
                          related=factions)
        for arc in plan.faction_arcs:
            labels = [stage.label for stage in arc.stages if stage.label]
            duplicates = sorted({label for label in labels if labels.count(label) > 1})
            if duplicates:
                self._add("FACTION_STAGE_DUPLICATE_LABEL", "WARNING", "faction",
                          arc.arc_id, "势力阶段标签重复", related=duplicates)
            for index, stage in enumerate(arc.stages):
                if not stage.trigger and not stage.trigger_node_id:
                    self._add("FACTION_STAGE_WITHOUT_TRIGGER", "WARNING", "faction",
                              f"{arc.arc_id}::stage{index}",
                              "势力阶段没有触发条件", related=[arc.faction_id])
                if stage.trigger_node_id and stage.trigger_node_id not in node_ids:
                    self._add("FACTION_STAGE_TRIGGER_NODE_UNKNOWN", "ERROR", "faction",
                              f"{arc.arc_id}::stage{index}",
                              "显式 trigger_node_id 不是已有 PlotNode",
                              related=[stage.trigger_node_id])

    # ---------------------------------------------------------------- cross-graph
    def _check_cross_graph(self) -> None:
        plan = self._require_plan()
        location_ids = {item.location_id for item in plan.locations}
        character_ids = {item.character_id for item in plan.characters}
        faction_ids = {item.faction_id for item in plan.factions}
        for node in plan.plot_nodes:
            if node.location_id and node.location_id not in location_ids:
                self._add("CROSS_GRAPH_DANGLING_LOCATION", "ERROR", "cross", node.node_id,
                          "PlotNode 的地点不存在（location graph 与 plot graph 悬空）",
                          related=[node.location_id])
            for participant in node.participants:
                if participant in character_ids or participant in faction_ids:
                    continue
                if not self._external_ok(participant):
                    self._add("CROSS_GRAPH_DANGLING_PARTICIPANT", "ERROR", "cross",
                              node.node_id,
                              "PlotNode 参与者既不是 planning 人物 / 势力，也不是已知实体",
                              related=[participant])
        for faction in plan.factions:
            for territory in faction.territory:
                if territory and territory not in location_ids:
                    self._add("CROSS_GRAPH_TERRITORY_DANGLING", "ERROR", "cross",
                              faction.faction_id, "势力领土在地点图中不存在",
                              related=[territory])
        for arc in plan.relationship_arcs:
            for participant in arc.participants:
                if participant in character_ids or participant in faction_ids:
                    continue
                if not self._external_ok(participant):
                    self._add("CROSS_GRAPH_PARTICIPANT_DANGLING", "ERROR", "cross",
                              arc.arc_id, "关系参与者未解析到人物 / 势力稳定 ID",
                              related=[participant])
        for location in plan.locations:
            requirement = location.entry_requirement
            if requirement and not self._requirement_known(requirement):
                self._add("CROSS_GRAPH_ENTRY_REQUIREMENT_DANGLING", "ERROR", "cross",
                          location.location_id, "地点进入条件引用了不存在的规则 / 成长 / 事实",
                          related=[requirement])

    # ---------------------------------------------------------------- helpers
    def _require_plan(self) -> StoryPlanningIR:
        assert self._plan is not None
        return self._plan

    def _require_graphs(self) -> PlanningGraphBundle:
        assert self._graphs is not None
        return self._graphs


def _node_tokens(texts: Iterable[str]) -> list[str]:
    rows: list[str] = []
    for text in texts:
        rows.extend(NODE_TOKEN.findall(text or ""))
    return sorted(set(rows))


def _node_sequence_order(plan: StoryPlanningIR) -> dict[str, int]:
    """PlotNode → timeline sequence_order（同一节点取最早锚点）。"""

    rows: dict[str, int] = {}
    timeline = plan.timeline
    if timeline is None:
        return rows
    entries = list(timeline.world_history) + list(timeline.story_timeline)
    for items in timeline.character_timeline.values():
        entries.extend(items)
    for entry in entries:
        if not entry.anchor_node_id:
            continue
        current = rows.get(entry.anchor_node_id)
        if current is None or entry.sequence_order < current:
            rows[entry.anchor_node_id] = entry.sequence_order
    return rows


def _structural_access(plan: StoryPlanningIR) -> tuple[set[str], set[str]]:
    """(requirements, availability)：结构可达时把计划里声明过的条件都视为可满足。"""

    return declared_access(plan)


def _reachable_from(plan: StoryPlanningIR, entries: Iterable[str], *,
                    available_requirements: Iterable[str],
                    available_availability: Iterable[str] = ()) -> set[str]:
    allowed = set(available_requirements)
    windows = set(available_availability)
    rows: set[str] = set()
    for entry in entries:
        rows.update(reachable_locations(plan, entry, available_requirements=allowed,
                                        available_availability=windows).reachable)
    return rows


__all__ = ["GraphFinding", "GraphReport", "PlanningGraphValidator", "Severity"]
