"""M2A：Story Planning IR Validator。

只做**结构与引用**一致性，不判断剧情好坏、不写任何 truth：

- 稳定 ID 唯一；
- 所有 graph / timeline / node / volume / arc / participants 引用必须解析；
- StorySpine 必须是因果 DAG，不能是 beat ladder；
- Planning 不能声明 happened，不能写入 Canon / StoryState 状态；
- provenance：confirmed 必须有 service 引用；generated / inferred 不得覆盖 supplied。
"""

from __future__ import annotations

from typing import Any, Iterable

from pydantic import Field

from novelforge.models import StrictModel

from .enums import (
    CONFIRMED_TIMELINE_STATUS,
    NON_FACT_RULE_TYPES,
    NON_FACT_TIMELINE_STATUSES,
    SPINE_CAUSAL_RELATIONS,
)
from .models import (
    StoryPlanningIR,
    claims_happened,
    entry_id,
    iter_planning_entries,
)

FORBIDDEN_STATUS_KEYS = ("happened", "occurred", "immutable", "canon_status",
                         "story_state_applied")


class PlanningFinding(StrictModel):
    code: str = Field(min_length=3, max_length=64)
    severity: str = Field(default="error", max_length=16)
    path: str = Field(default="", max_length=200)
    message: str = Field(default="", max_length=300)
    detail: str = Field(default="", max_length=400)


class PlanningReport(StrictModel):
    novel_id: str = Field(default="", max_length=96)
    findings: list[PlanningFinding] = Field(default_factory=list)

    def errors(self) -> list[PlanningFinding]:
        return [item for item in self.findings if item.severity == "error"]

    def warnings(self) -> list[PlanningFinding]:
        return [item for item in self.findings if item.severity != "error"]

    def ok(self) -> bool:
        return not self.errors()

    def codes(self) -> list[str]:
        return sorted({item.code for item in self.findings})


class PlanningValidator:
    """跨引用校验器。外部 Canon / StoryState / Chapter IR ID 通过白名单传入。"""

    def __init__(self, *, known_entity_ids: Iterable[str] | None = None,
                 known_canon_ids: Iterable[str] | None = None,
                 known_chapter_ir_ids: Iterable[str] | None = None,
                 allow_external_refs: bool = True) -> None:
        self.known_entity_ids = set(known_entity_ids or ())
        self.known_canon_ids = set(known_canon_ids or ())
        self.known_chapter_ir_ids = set(known_chapter_ir_ids or ())
        self.allow_external_refs = allow_external_refs
        self._plan: StoryPlanningIR | None = None
        self._report = PlanningReport()

    # ------------------------------------------------------------------ 入口
    def validate(self, plan: StoryPlanningIR,
                 previous: StoryPlanningIR | None = None) -> PlanningReport:
        self._plan = plan
        self._report = PlanningReport(novel_id=plan.novel_id)
        self._check_unique_ids()
        self._check_arcs_and_volumes()
        self._check_spine()
        self._check_nodes()
        self._check_characters()
        self._check_relationships()
        self._check_factions()
        self._check_locations()
        self._check_timeline()
        self._check_information()
        self._check_foreshadows()
        self._check_progression()
        self._check_detail_levels()
        self._check_scheduling()
        self._check_boundaries(plan)
        self._check_pacing()
        if previous is not None:
            self._check_supplied_preserved(previous, plan)
        return self._report

    def validate_raw(self, raw: dict[str, Any]) -> PlanningReport:
        """在模型校验之前先看原始 JSON：Planning 不得携带 Canon / StoryState 状态字段。"""

        self._plan = None
        self._report = PlanningReport(novel_id=str(raw.get("novel_id", "")))
        for path, value in _walk(raw):
            key = _leaf_key(path)
            if key in FORBIDDEN_STATUS_KEYS and value not in ("", None, False):
                self._add("PLANNING_WRITES_TRUTH_STATUS", path,
                          "Planning 不得携带 Canon / StoryState 状态字段",
                          f"{path} = {value}")
            # 关系弧不得把数值评分当权威真相（UI / analysis 层只能标 derived）
            if "relationship_arc" in path and isinstance(value, (int, float)) \
                    and not isinstance(value, bool) \
                    and not key.endswith(("_derived", "_non_authoritative", "_score")):
                self._add("RELATIONSHIP_NUMERIC_AUTHORITATIVE", path,
                          "关系弧不使用数值真相；数值只能出现在 derived / analysis 层",
                          f"{key} = {value}")
        return self._report

    # ------------------------------------------------------------------ 工具
    def _add(self, code: str, path: str, message: str, detail: str = "",
             severity: str = "error") -> None:
        self._report.findings.append(PlanningFinding(
            code=code, severity=severity, path=path[:200], message=message[:300],
            detail=str(detail)[:400]))

    def _external_ok(self, ref: str) -> bool:
        if not ref:
            return True
        if ref in self.known_entity_ids or ref in self.known_canon_ids \
                or ref in self.known_chapter_ir_ids:
            return True
        return self.allow_external_refs and ref.split("_", 1)[0] in ("ENTITY", "FACT",
                                                                     "EVENT", "KNW", "REL",
                                                                     "FS", "CON", "uuid")

    # ------------------------------------------------------------------ 规则
    def _check_unique_ids(self) -> None:
        plan = self._require_plan()
        seen: dict[str, str] = {}
        for identifier, kind in plan.planning_ids():
            if identifier in seen:
                self._add("DUPLICATE_PLANNING_ID", kind, "planning 稳定 ID 重复",
                          f"{identifier} 同时出现在 {seen[identifier]} 与 {kind}")
            seen[identifier] = kind

    def _check_arcs_and_volumes(self) -> None:
        plan = self._require_plan()
        volume_ids = {volume.volume_id for volume in plan.volumes}
        arc_ids = {arc.arc_id for arc in plan.arcs}
        for volume in plan.volumes:
            for arc_id in volume.arc_ids:
                if arc_id not in arc_ids:
                    self._add("PLANNING_REF_UNKNOWN", f"volumes[{volume.volume_id}].arc_ids",
                              "卷引用了不存在的 arc", arc_id)
            declared = {arc.arc_id for arc in plan.arcs
                        if arc.volume_id == volume.volume_id}
            missing = sorted(declared - set(volume.arc_ids))
            extra = sorted(set(volume.arc_ids) - declared)
            if extra:
                self._add("VOLUME_ARC_LIST_MISMATCH", f"volumes[{volume.volume_id}].arc_ids",
                          "卷里列出的 arc 不属于这一卷", ", ".join(extra))
            if missing:
                self._add("VOLUME_ARC_LIST_MISMATCH", f"volumes[{volume.volume_id}].arc_ids",
                          "属于这一卷的 arc 没有登记进卷", ", ".join(missing))
            if volume.climax_node_id and volume.climax_node_id not in _node_ids(plan):
                self._add("PLANNING_REF_UNKNOWN", f"volumes[{volume.volume_id}].climax_node_id",
                          "卷高潮节点不存在", volume.climax_node_id)
            for node_id in volume.major_nodes:
                if node_id not in _node_ids(plan):
                    self._add("PLANNING_REF_UNKNOWN", f"volumes[{volume.volume_id}].major_nodes",
                              "卷引用不存在的 PlotNode", node_id)
            budget = sum(arc.chapter_budget for arc in plan.arcs
                         if arc.volume_id == volume.volume_id)
            if volume.chapter_budget and budget and budget != volume.chapter_budget:
                self._add("VOLUME_ARC_BUDGET_MISMATCH",
                          f"volumes[{volume.volume_id}].chapter_budget",
                          "卷章数预算与 arc 预算之和不一致",
                          f"volume={volume.chapter_budget} arcs={budget}", severity="warning")
        for arc in plan.arcs:
            if arc.volume_id not in volume_ids:
                self._add("PLANNING_REF_UNKNOWN", f"arcs[{arc.arc_id}].volume_id",
                          "arc 指向不存在的卷", arc.volume_id)
            for node_id in arc.plot_nodes:
                if node_id not in _node_ids(plan):
                    self._add("PLANNING_REF_UNKNOWN", f"arcs[{arc.arc_id}].plot_nodes",
                              "arc 引用不存在的 PlotNode", node_id)
            for step in arc.decision_chain:
                if step.node_id not in _node_ids(plan):
                    self._add("PLANNING_REF_UNKNOWN",
                              f"arcs[{arc.arc_id}].decision_chain",
                              "决策链引用不存在的 PlotNode", step.node_id)
            if arc.chapter_budget <= 0:
                self._add("ARC_BUDGET_MISSING", f"arcs[{arc.arc_id}].chapter_budget",
                          "arc 没有章数预算（Arc 是 Chapter IR 的直接上游）",
                          severity="warning")

    def _check_spine(self) -> None:
        plan = self._require_plan()
        spine = plan.spine
        if spine is None:
            self._add("SPINE_MISSING", "spine", "Planning IR 没有 StorySpine",
                      severity="warning")
            return
        node_ids = _node_ids(plan)
        listed = set(spine.nodes)
        for node_id in spine.nodes:
            if node_id not in node_ids:
                self._add("PLANNING_REF_UNKNOWN", "spine.nodes",
                          "spine 引用不存在的 PlotNode", node_id)
        for node_id in spine.entry_node_ids + spine.terminal_node_ids:
            if node_id not in listed:
                self._add("PLANNING_REF_UNKNOWN", "spine.entry_node_ids",
                          "spine 端点不在节点列表里", node_id)
        adjacency: dict[str, set[str]] = {node_id: set() for node_id in spine.nodes}
        causal_incoming: dict[str, int] = {node_id: 0 for node_id in spine.nodes}
        for edge in spine.edges:
            if edge.from_node_id not in listed or edge.to_node_id not in listed:
                self._add("SPINE_EDGE_NODE_NOT_IN_SPINE", "spine.edges",
                          "spine 边的端点不在 spine.nodes 里",
                          f"{edge.from_node_id}->{edge.to_node_id}")
                continue
            adjacency[edge.from_node_id].add(edge.to_node_id)
            if edge.relation in SPINE_CAUSAL_RELATIONS:
                causal_incoming[edge.to_node_id] += 1
        cycle = _find_cycle(adjacency)
        if cycle:
            self._add("SPINE_CYCLE", "spine.edges", "StorySpine 不是 DAG（存在环）",
                      " -> ".join(cycle))
        if not spine.edges:
            self._add("SPINE_IS_BEAT_LADDER", "spine.edges",
                      "StorySpine 只有节点顺序、没有因果关系")
        entries = set(spine.entry_node_ids) or {node for node in listed
                                                if not any(edge.to_node_id == node
                                                           for edge in spine.edges)}
        for node_id in spine.nodes:
            if node_id in entries:
                continue
            if causal_incoming.get(node_id, 0) == 0:
                self._add("SPINE_NODE_WITHOUT_CAUSE", f"spine.nodes[{node_id}]",
                          "节点没有任何因果入边（beat ladder 特征）")
        if len(spine.nodes) >= 4 and _is_simple_chain(spine):
            self._add("SPINE_IS_BEAT_LADDER", "spine",
                      "spine 是一条无分支的固定链条，看起来像 beat ladder",
                      " -> ".join(spine.nodes), severity="warning")

    def _check_nodes(self) -> None:
        plan = self._require_plan()
        location_ids = {item.location_id for item in plan.locations}
        character_ids = {item.character_id for item in plan.characters}
        faction_ids = {item.faction_id for item in plan.factions}
        foreshadow_ids = {item.foreshadow_id for item in plan.foreshadow_plans}
        truth_ids = {truth.truth_id for arc in plan.information_arcs for truth in arc.truths}
        track_ids = {item.track_id for item in plan.progression_tracks}
        node_ids = _node_ids(plan)
        for node in plan.plot_nodes:
            path = f"plot_nodes[{node.node_id}]"
            if node.is_empty_beat():
                self._add("PLOT_NODE_EMPTY_BEAT", path,
                          "节点没有任何语义内容（只剩排序位置）")
            if node.location_id and node.location_id not in location_ids:
                self._add("PLANNING_REF_UNKNOWN", f"{path}.location_id",
                          "节点地点不存在", node.location_id)
            for participant in node.participants:
                if participant in character_ids or participant in faction_ids:
                    continue
                if not self._external_ok(participant):
                    self._add("PLANNING_REF_UNKNOWN", f"{path}.participants",
                              "节点参与者既不是 planning 人物 / 势力，也不是已知实体",
                              participant)
            for prerequisite in node.prerequisites:
                if prerequisite not in node_ids:
                    self._add("PLANNING_REF_UNKNOWN", f"{path}.prerequisites",
                              "前置节点不存在", prerequisite)
                if prerequisite == node.node_id:
                    self._add("PLANNING_SELF_REFERENCE", f"{path}.prerequisites",
                              "节点不能把自己作为前置", prerequisite)
            for foreshadow_id in node.foreshadow_ids:
                if foreshadow_id not in foreshadow_ids:
                    self._add("PLANNING_REF_UNKNOWN", f"{path}.foreshadow_ids",
                              "节点引用不存在的伏笔计划", foreshadow_id)
            for truth_id in node.truth_ids:
                if truth_id not in truth_ids:
                    self._add("PLANNING_REF_UNKNOWN", f"{path}.truth_ids",
                              "节点引用不存在的信息真相", truth_id)
            for track_id in node.track_ids:
                if track_id not in track_ids:
                    self._add("PLANNING_REF_UNKNOWN", f"{path}.track_ids",
                              "节点引用不存在的成长轨道", track_id)

    def _check_characters(self) -> None:
        plan = self._require_plan()
        character_ids = {item.character_id for item in plan.characters}
        arc_ids = {item.arc_id for item in plan.character_arcs}
        node_ids = _node_ids(plan)
        for character in plan.characters:
            path = f"characters[{character.character_id}]"
            if character.character_arc_id and character.character_arc_id not in arc_ids:
                self._add("PLANNING_REF_UNKNOWN", f"{path}.character_arc_id",
                          "人物指向不存在的角色弧", character.character_arc_id)
            if character.entity_ref and not self._external_ok(character.entity_ref):
                self._add("PLANNING_REF_UNKNOWN", f"{path}.entity_ref",
                          "人物引用了未知的 Canon / StoryState 实体", character.entity_ref)
        for arc in plan.character_arcs:
            path = f"character_arcs[{arc.arc_id}]"
            if arc.character_id not in character_ids:
                self._add("PLANNING_REF_UNKNOWN", f"{path}.character_id",
                          "角色弧指向不存在的人物规划", arc.character_id)
            for choice in arc.major_choices:
                if choice.node_id and choice.node_id not in node_ids:
                    self._add("PLANNING_REF_UNKNOWN", f"{path}.major_choices",
                              "重大选择引用不存在的 PlotNode", choice.node_id)
                if choice.node_id and not choice.has_alternative:
                    self._add("ARC_CHOICE_WITHOUT_ALTERNATIVE", f"{path}.major_choices",
                              "没有替代方案的选择不能下沉成章节 decision",
                              choice.node_id, severity="warning")

    def _check_relationships(self) -> None:
        plan = self._require_plan()
        character_ids = {item.character_id for item in plan.characters}
        faction_ids = {item.faction_id for item in plan.factions}
        node_ids = _node_ids(plan)
        for arc in plan.relationship_arcs:
            path = f"relationship_arcs[{arc.arc_id}]"
            for participant in arc.participants:
                if participant in character_ids or participant in faction_ids:
                    continue
                if not self._external_ok(participant):
                    self._add("PLANNING_REF_UNKNOWN", f"{path}.participants",
                              "关系参与者既不是 planning 人物 / 势力，也不是已知实体",
                              participant)
            if arc.irreversible_node and arc.irreversible_node not in node_ids:
                self._add("PLANNING_REF_UNKNOWN", f"{path}.irreversible_node",
                          "关系不可逆点不是已知 PlotNode", arc.irreversible_node)

    def _check_factions(self) -> None:
        plan = self._require_plan()
        faction_ids = {item.faction_id for item in plan.factions}
        arc_ids = {item.arc_id for item in plan.faction_arcs}
        for faction in plan.factions:
            path = f"factions[{faction.faction_id}]"
            if faction.faction_arc_id and faction.faction_arc_id not in arc_ids:
                self._add("PLANNING_REF_UNKNOWN", f"{path}.faction_arc_id",
                          "势力指向不存在的势力弧", faction.faction_arc_id)
            for other in faction.allies + faction.enemies:
                if other not in faction_ids:
                    self._add("PLANNING_REF_UNKNOWN", f"{path}.allies",
                              "势力结盟 / 敌对关系指向不存在的势力规划", other)
            if faction.faction_id in (faction.allies + faction.enemies):
                self._add("FACTION_SELF_REFERENCE", path, "势力不能与自己结盟或敌对")
            if faction.entity_ref and not self._external_ok(faction.entity_ref):
                self._add("PLANNING_REF_UNKNOWN", f"{path}.entity_ref",
                          "势力引用了未知的 Canon / StoryState 实体", faction.entity_ref)
        for arc in plan.faction_arcs:
            if arc.faction_id not in faction_ids:
                self._add("PLANNING_REF_UNKNOWN", f"faction_arcs[{arc.arc_id}].faction_id",
                          "势力弧指向不存在的势力规划", arc.faction_id)

    def _check_locations(self) -> None:
        plan = self._require_plan()
        location_ids = {item.location_id for item in plan.locations}
        graph = plan.location_graph
        if graph is None:
            return
        for location_id in graph.location_ids:
            if location_id not in location_ids:
                self._add("PLANNING_REF_UNKNOWN", "location_graph.location_ids",
                          "地图引用了不存在的地点", location_id)
        missing = sorted(location_ids - set(graph.location_ids))
        if missing:
            self._add("LOCATION_GRAPH_INCOMPLETE", "location_graph.location_ids",
                      "有地点没有登记进地图", ", ".join(missing), severity="warning")
        for edge in graph.edges:
            for endpoint in (edge.from_location_id, edge.to_location_id):
                if endpoint not in location_ids:
                    self._add("PLANNING_REF_UNKNOWN", "location_graph.edges",
                              "地图边引用了不存在的地点", endpoint)
            if edge.from_location_id == edge.to_location_id:
                self._add("LOCATION_EDGE_SELF_LOOP", "location_graph.edges",
                          "地图边不能自环", edge.from_location_id)
        for location in plan.locations:
            if location.parent_region and location.parent_region not in location_ids:
                self._add("PLANNING_REF_UNKNOWN",
                          f"locations[{location.location_id}].parent_region",
                          "上级区域不是已登记地点", location.parent_region,
                          severity="warning")

    def _check_timeline(self) -> None:
        plan = self._require_plan()
        timeline = plan.timeline
        if timeline is None:
            return
        node_ids = _node_ids(plan)
        entry_ids: set[str] = set()
        groups = {"world_history": timeline.world_history,
                  "story_timeline": timeline.story_timeline}
        groups.update({f"character_timeline[{key}]": value
                       for key, value in timeline.character_timeline.items()})
        for group_name, entries in groups.items():
            for entry in entries:
                path = f"timeline.{group_name}[{entry.entry_id}]"
                if entry.entry_id in entry_ids:
                    self._add("DUPLICATE_PLANNING_ID", path, "时间线条目 ID 重复",
                              entry.entry_id)
                entry_ids.add(entry.entry_id)
                if entry.anchor_node_id and entry.anchor_node_id not in node_ids:
                    self._add("PLANNING_REF_UNKNOWN", f"{path}.anchor_node_id",
                              "时间线锚点不是已知 PlotNode", entry.anchor_node_id)
                if entry.estimated_chapter is not None and not entry.anchor_node_id \
                        and not entry.relative_to:
                    self._add("TIMELINE_CHAPTER_AS_TRUTH", path,
                              "章节号不能作为唯一时间真相（需要 order / anchor / relative_to）",
                              f"estimated_chapter={entry.estimated_chapter}")
                has_canon_ref = bool(entry.canon_event_ref or entry.canon_fact_ref)
                if entry.status == CONFIRMED_TIMELINE_STATUS and not has_canon_ref:
                    self._add("CONFIRMED_TIMELINE_WITHOUT_CANON_REF", path,
                              "已确认的历史必须引用 Canon event / fact 稳定 ID")
                if entry.status in NON_FACT_TIMELINE_STATUSES and has_canon_ref:
                    self._add("NON_FACT_TIMELINE_AS_CANON", path,
                              "假说 / 传说不能直接引用为 Canon 事实",
                              entry.canon_event_ref or entry.canon_fact_ref)
                if entry.status in NON_FACT_TIMELINE_STATUSES and entry.provenance == "confirmed":
                    self._add("NON_FACT_TIMELINE_AS_CANON", path,
                              "假说 / 传说不能标成 confirmed provenance")
                for relative in entry.relative_to:
                    if relative not in _all_entry_ids(timeline):
                        self._add("PLANNING_REF_UNKNOWN", f"{path}.relative_to",
                                  "时间线相对引用不存在", relative)

    def _check_information(self) -> None:
        plan = self._require_plan()
        node_ids = _node_ids(plan)
        character_ids = {item.character_id for item in plan.characters}
        faction_ids = {item.faction_id for item in plan.factions}
        for arc in plan.information_arcs:
            path = f"information_arcs[{arc.arc_id}]"
            truth_ids = {truth.truth_id for truth in arc.truths}
            for move in arc.moves:
                if move.truth_id not in truth_ids:
                    self._add("PLANNING_REF_UNKNOWN", f"{path}.moves[{move.move_id}]",
                              "信息动作指向本弧之外的真相", move.truth_id)
                if move.node_id and move.node_id not in node_ids:
                    self._add("PLANNING_REF_UNKNOWN", f"{path}.moves[{move.move_id}].node_id",
                              "信息动作引用不存在的 PlotNode", move.node_id)
                for holder in move.holder_ids:
                    if holder in character_ids or holder in faction_ids:
                        continue
                    if not self._external_ok(holder):
                        self._add("PLANNING_REF_UNKNOWN",
                                  f"{path}.moves[{move.move_id}].holder_ids",
                                  "知识持有者既不是 planning 人物 / 势力，也不是已知实体",
                                  holder)
                if move.move_type in ("reveal", "payoff") and not move.holder_ids:
                    self._add("INFORMATION_REVEAL_WITHOUT_HOLDER",
                              f"{path}.moves[{move.move_id}]",
                              "reveal / payoff 必须说明谁获得了信息", move.move_id)
            for truth in arc.truths:
                if truth.canon_fact_ref and not self._external_ok(truth.canon_fact_ref):
                    self._add("PLANNING_REF_UNKNOWN", f"{path}.truths[{truth.truth_id}]",
                              "真相引用了未知的 Canon fact", truth.canon_fact_ref)

    def _check_foreshadows(self) -> None:
        plan = self._require_plan()
        node_ids = _node_ids(plan)
        for foreshadow in plan.foreshadow_plans:
            path = f"foreshadow_plans[{foreshadow.foreshadow_id}]"
            if foreshadow.plan_status != "planned":
                self._add("PLANNING_CLAIMS_FORESHADOW_PROGRESS", path,
                          "伏笔计划只能停在 planned",
                          foreshadow.plan_status)
            for node_id in (foreshadow.plant_node_id, foreshadow.payoff_node_id):
                if node_id and node_id not in node_ids:
                    self._add("PLANNING_REF_UNKNOWN", path, "伏笔引用不存在的 PlotNode",
                              node_id)
            for move in foreshadow.moves:
                if move.node_id and move.node_id not in node_ids:
                    self._add("PLANNING_REF_UNKNOWN", f"{path}.moves[{move.move_id}]",
                              "伏笔动作引用不存在的 PlotNode", move.node_id)
            types = {move.move_type for move in foreshadow.moves}
            if foreshadow.moves and "plant" not in types:
                self._add("FORESHADOW_WITHOUT_PLANT", path, "伏笔计划没有 plant 动作",
                          severity="warning")
            if foreshadow.moves and "payoff" not in types and not foreshadow.intended_payoff:
                self._add("FORESHADOW_WITHOUT_PAYOFF", path,
                          "伏笔计划既没有 payoff 动作也没有预期回收", severity="warning")
            if foreshadow.canon_foreshadow_ref \
                    and not self._external_ok(foreshadow.canon_foreshadow_ref):
                self._add("PLANNING_REF_UNKNOWN", f"{path}.canon_foreshadow_ref",
                          "伏笔引用了未知的 Canon foreshadow", foreshadow.canon_foreshadow_ref)

    def _check_progression(self) -> None:
        plan = self._require_plan()
        node_ids = _node_ids(plan)
        for track in plan.progression_tracks:
            path = f"progression_tracks[{track.track_id}]"
            for milestone in track.milestones:
                if milestone.node_id and milestone.node_id not in node_ids:
                    self._add("PLANNING_REF_UNKNOWN",
                              f"{path}.milestones[{milestone.milestone_id}]",
                              "成长里程碑引用不存在的 PlotNode", milestone.node_id)
                if not milestone.requirement and not milestone.cost:
                    self._add("PROGRESSION_MILESTONE_WITHOUT_PRICE",
                              f"{path}.milestones[{milestone.milestone_id}]",
                              "里程碑既没有条件也没有代价（成长不能无成本）",
                              severity="warning")

    def _check_detail_levels(self) -> None:
        """Progressive Elaboration：深度只能声明自己真的具备的结构，不强制远期对象提前细化。"""

        plan = self._require_plan()
        for arc in plan.arcs:
            if arc.detail_level != "chapter_ready":
                continue
            path = f"arcs[{arc.arc_id}]"
            if not arc.decision_chain:
                self._add("ARC_DETAIL_LEVEL_INCOMPLETE", path,
                          "声明 chapter_ready 的 arc 必须有 decision_chain")
            if arc.chapter_budget <= 0:
                self._add("ARC_DETAIL_LEVEL_INCOMPLETE", path,
                          "声明 chapter_ready 的 arc 必须有章数预算")
            if not arc.plot_nodes:
                self._add("ARC_DETAIL_LEVEL_INCOMPLETE", path,
                          "声明 chapter_ready 的 arc 必须有 plot_nodes")
        for volume in plan.volumes:
            if volume.detail_level not in ("arc", "chapter_ready"):
                continue
            path = f"volumes[{volume.volume_id}]"
            if not volume.arc_ids:
                self._add("VOLUME_DETAIL_LEVEL_INCOMPLETE", path,
                          "声明 arc 及以上深度的卷必须列出 arc_ids")
            if not volume.major_nodes:
                self._add("VOLUME_DETAIL_LEVEL_INCOMPLETE", path,
                          "声明 arc 及以上深度的卷必须列出 major_nodes")
            if not volume.climax_node_id:
                self._add("VOLUME_DETAIL_LEVEL_INCOMPLETE", path,
                          "声明 arc 及以上深度的卷必须有 climax_node_id",
                          severity="warning")

    def _check_scheduling(self) -> None:
        """PlotNode 可以长期 unscheduled；一旦排期，execution volume 必须唯一。"""

        plan = self._require_plan()
        volume_ids = {volume.volume_id for volume in plan.volumes}
        execution_volumes: dict[str, set[str]] = {}
        reference_volumes: dict[str, set[str]] = {}
        for volume in plan.volumes:
            for node_id in volume.major_nodes:
                execution_volumes.setdefault(node_id, set()).add(volume.volume_id)
            if volume.climax_node_id:
                execution_volumes.setdefault(volume.climax_node_id, set()).add(
                    volume.volume_id)
        for arc in plan.arcs:
            for node_id in arc.plot_nodes:
                reference_volumes.setdefault(node_id, set()).add(arc.volume_id)
        for node in plan.plot_nodes:
            path = f"plot_nodes[{node.node_id}]"
            scheduled = node.scheduled_volume_id
            if scheduled and scheduled not in volume_ids:
                self._add("SCHEDULED_NODE_UNKNOWN_VOLUME", f"{path}.scheduled_volume_id",
                          "排期卷不存在", scheduled)
                continue
            executions = execution_volumes.get(node.node_id, set())
            if scheduled:
                if not executions and node.node_id not in {
                        item for arc in plan.arcs if arc.volume_id == scheduled
                        for item in arc.plot_nodes}:
                    self._add("SCHEDULED_NODE_NOT_IN_VOLUME", f"{path}.scheduled_volume_id",
                              "排期卷既没有把这个节点列为 major_node，也没有所属 arc 引用它",
                              scheduled)
                elif executions and executions != {scheduled}:
                    self._add("PLOT_NODE_EXECUTION_VOLUME_AMBIGUOUS",
                              f"{path}.scheduled_volume_id",
                              "同一个 PlotNode 只能有一个 execution volume",
                              f"scheduled={scheduled} major_nodes={sorted(executions)}")
            elif len(executions) > 1:
                self._add("PLOT_NODE_UNSCHEDULED_MULTI_VOLUME", f"{path}.scheduled_volume_id",
                          "节点被多个卷列为 major_node 却没有排期",
                          ", ".join(sorted(executions)), severity="warning")
            cross = sorted(reference_volumes.get(node.node_id, set())
                           - ({scheduled} if scheduled else set()) - executions)
            if cross:
                self._add("PLOT_NODE_CROSS_VOLUME_REFERENCE", path,
                          "其它卷通过 arc 引用了该节点：只能是 foreshadow / consequence 引用，"
                          "不能重复执行",
                          ", ".join(cross), severity="warning")

    def _check_boundaries(self, plan: StoryPlanningIR) -> None:
        for rule in (plan.world.world_rules if plan.world else []):
            if rule.rule_type in NON_FACT_RULE_TYPES and rule.canon_fact_ref:
                self._add("BELIEF_AS_CANON_FACT", f"world.world_rules[{rule.rule_id}]",
                          "belief / rumor 不能直接引用为 Canon fact", rule.canon_fact_ref)
        for model_path, model in _models_with_provenance(plan):
            # PacingBand 这类嵌套条目没有 provenance 字段（只有外壳才有）
            if getattr(model, "provenance", "") == "confirmed" \
                    and not getattr(model, "confirmation_ref", ""):
                self._add("UNCONFIRMED_PROVENANCE_WITHOUT_SERVICE_REF", model_path,
                          "confirmed 必须带正式 service 的 confirmation_ref")
        for path, text in _future_texts(plan):
            if claims_happened(text):
                self._add("HAPPENED_CLAIM_IN_PLANNING", path,
                          "Planning 文本声称已经发生（future / happened 越界）",
                          text[:120], severity="warning")

    def _check_pacing(self) -> None:
        plan = self._require_plan()
        pacing = plan.pacing
        if pacing is None:
            return
        if (pacing.intensity or pacing.target_distribution) and not pacing.template_id:
            self._add("PACING_TEMPLATE_NOT_DECLARED", "pacing.intensity",
                      "节奏强度必须声明来自哪个 genre template（Core 不硬编码题材）",
                      severity="warning")
        volume_ids = {volume.volume_id for volume in plan.volumes}
        for band in pacing.bands:
            if band.volume_id not in volume_ids:
                self._add("PLANNING_REF_UNKNOWN", "pacing.bands",
                          "节奏带引用了不存在的卷", band.volume_id)

    def _check_supplied_preserved(self, previous: StoryPlanningIR,
                                  current: StoryPlanningIR) -> None:
        """generated / inferred 不得覆盖 supplied（同 ID 条目的值发生了变化）。"""

        base = {path: (value, provenance) for path, value, provenance
                in _entries_with_provenance(previous)}
        for path, value, provenance in _entries_with_provenance(current):
            row = base.get(path)
            if row is None:
                continue
            before, before_provenance = row
            if before_provenance == "supplied" and provenance not in ("supplied", "confirmed") \
                    and before != value:
                self._add("PROVENANCE_SUPPLIED_OVERWRITTEN", path,
                          "generated / inferred 覆盖了作者 supplied 的内容",
                          f"provenance supplied -> {provenance}")

    def _require_plan(self) -> StoryPlanningIR:
        assert self._plan is not None
        return self._plan


# ---------------------------------------------------------------------- 辅助
def _node_ids(plan: StoryPlanningIR) -> set[str]:
    return {node.node_id for node in plan.plot_nodes}


def _all_entry_ids(plan) -> set[str]:
    ids: set[str] = set()
    for items in (plan.world_history, plan.story_timeline):
        ids.update(item.entry_id for item in items)
    for entries in plan.character_timeline.values():
        ids.update(item.entry_id for item in entries)
    return ids


def _find_cycle(adjacency: dict[str, set[str]]) -> list[str]:
    state: dict[str, int] = {}
    stack: list[str] = []

    def visit(node: str) -> list[str]:
        state[node] = 1
        stack.append(node)
        for neighbour in sorted(adjacency.get(node, ())):
            if state.get(neighbour, 0) == 1:
                return stack[stack.index(neighbour):] + [neighbour]
            if state.get(neighbour, 0) == 0:
                found = visit(neighbour)
                if found:
                    return found
        stack.pop()
        state[node] = 2
        return []

    for node in sorted(adjacency):
        if state.get(node, 0) == 0:
            found = visit(node)
            if found:
                return found
    return []


def _is_simple_chain(spine) -> bool:
    nodes = list(spine.nodes)
    if len(spine.edges) != len(nodes) - 1:
        return False
    pairs = {(edge.from_node_id, edge.to_node_id) for edge in spine.edges}
    expected = {(nodes[index], nodes[index + 1]) for index in range(len(nodes) - 1)}
    return pairs == expected


def _walk(payload: Any, prefix: str = ""):
    if isinstance(payload, dict):
        for key, value in payload.items():
            path = f"{prefix}.{key}" if prefix else str(key)
            yield from _walk(value, path)
    elif isinstance(payload, list):
        for index, value in enumerate(payload):
            yield from _walk(value, f"{prefix}[{index}]")
    else:
        yield prefix, payload


def _leaf_key(path: str) -> str:
    return path.rsplit(".", 1)[-1].lower()


def _models_with_provenance(plan: StoryPlanningIR):
    """遍历所有带 provenance 的 planning 条目（与 versioning 共用同一套遍历）。"""

    for kind, model in iter_planning_entries(plan):
        identifier = entry_id(kind, model)
        yield (f"{kind}[{identifier}]" if identifier else kind), model


def _all_entries(timeline):
    rows = list(timeline.world_history) + list(timeline.story_timeline)
    for entries in timeline.character_timeline.values():
        rows.extend(entries)
    return rows


def _entries_with_provenance(plan: StoryPlanningIR):
    """(stable_key, 值, provenance)：用于 supplied 保护检查。"""

    models = dict(_models_with_provenance(plan))
    for path, model in models.items():
        yield path, model.model_dump(mode="json"), getattr(model, "provenance", "")


def _future_texts(plan: StoryPlanningIR):
    for node in plan.plot_nodes:
        yield f"plot_nodes[{node.node_id}].state_change", node.state_change
        yield f"plot_nodes[{node.node_id}].payoff", node.payoff
    for foreshadow in plan.foreshadow_plans:
        yield f"foreshadow_plans[{foreshadow.foreshadow_id}].intended_payoff", \
            foreshadow.intended_payoff
    for volume in plan.volumes:
        yield f"volumes[{volume.volume_id}].ending_state", volume.ending_state
    for arc in plan.arcs:
        yield f"arcs[{arc.arc_id}].ending_state", arc.ending_state
    for information in plan.information_arcs:
        for truth in information.truths:
            yield f"information_arcs[{information.arc_id}].truths[{truth.truth_id}]", \
                truth.statement


__all__ = ["PlanningFinding", "PlanningReport", "PlanningValidator"]
