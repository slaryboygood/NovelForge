"""M8B：Long Outline Autonomous Batch Compiler / Checkpoint-Resume / Progressive Elaboration。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from novelforge.story_engine.planning import (
    CompilationScope,
    OutlineBatchCompiler,
    OutlineBatchError,
    OutlineBatchFailure,
    OutlineBatchStore,
    OutlineCompiler,
    PlanningRepository,
    PromotionPolicy,
    SegmentationProfile,
    WarningPolicy,
    CompilerConfig,
    StoryPlanningContextBuilder,
    check_detail_target,
    plan_batch_scopes,
    project_batch_session,
    project_elaboration_progress,
    project_planning_completeness,
    project_revision_chain,
    validate_planning_ir,
)
from novelforge.story_engine.planning.findings import PlanningFinding

FIXTURES = Path("tests/fixtures/planning_ir")
URBAN = "URBAN_GROWTH_EXAMPLE.json"
BATCH_DIR = Path("src/novelforge/story_engine/planning")


def _raw(name: str = URBAN) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def _spine_ready(name: str = URBAN) -> dict:
    """把 fixture 的卷降到 spine 深度，让 M8B 有工作可做。"""

    raw = _raw(name)
    for volume in raw.get("volumes") or []:
        volume["detail_level"] = "spine"
    if raw.get("intent"):
        # 小 fixture 的 target_words 要和结构规模匹配，否则会得到"结构太薄"的 review
        raw["intent"]["target_words"] = max(40_000, len(raw.get("plot_nodes") or []) * 11_111)
    return raw


def _long_book_raw(volume_count: int = 6, per_volume: int = 18) -> dict:
    """100+ PlotNode / 6+ 卷长篇合成计划（M4/M5/M6 各域齐全，边界每卷只有一个 hard signal）。"""

    def node_id(v: int, i: int) -> str:
        return f"NODE_V{v:02d}_{i:02d}"

    def volume_id(v: int) -> str:
        return f"VOL_V{v:02d}"

    def vid(v: int) -> int:
        """把固定卷号夹到当前卷数内，方便用同一份生成器跑 2–6 卷。"""

        return min(v, volume_count - 1)

    characters = [f"CHAR_{index}" for index in range(6)]
    factions = [f"FACTION_{index}" for index in range(3)]
    locations = [f"LOC_V{index:02d}" for index in range(volume_count)]
    node_rows: list[dict] = []
    edges: list[dict] = []
    previous = ""
    for v in range(volume_count):
        for i in range(per_volume):
            current = node_id(v, i)
            row: dict = {
                "node_id": current,
                "purpose": f"第 {v + 1} 卷节点 {i} 的用途",
                "conflict": f"冲突 {v}-{i}",
                "state_change": f"状态 {v}-{i}",
                "location_id": locations[v],
                "participants": [characters[(v + i) % len(characters)]],
                "importance": ("core" if i % 6 == 0
                               else "major" if i % 3 == 0 else "minor"),
                "prerequisites": [previous] if previous else [],
                "scheduled_volume_id": volume_id(v),
                "character_arc_refs": [f"CARCH_{i % 3}"] if i % 2 == 0 else [],
                "conflict_chain_ref": f"CONFLICT_V{v:02d}" if i % 3 == 0 else "",
            }
            if i % 4 == 0:
                row["must_happen"] = True
            if i % 11 == 5 and not row.get("must_happen"):
                row["optional"] = True
            if i % 4 == 2:
                row["cost"] = f"代价 {v}-{i}"
            if i % 5 == 3:
                row["payoff"] = f"回报 {v}-{i}"
            if i == 5:
                row["major_choice"] = f"抉择 {v}-{i}"
            if i == 10:
                row["resource_flow_refs"] = [f"RFLOW_{v:02d}"]
            if i == 11:
                row["equipment_refs"] = ["EQ_TOOL_MAIN"]
            if i == 12:
                row["map_expansion_refs"] = [f"MAPMILE_KNOWN_{v:02d}"]
            if i == 9:
                row["reward_refs"] = ["REWARD_MAIN"]
            node_rows.append(row)
            if previous:
                edges.append({"from_node_id": previous, "to_node_id": current,
                              "relation": "causes"})
            previous = current
    information_arcs = [
        {"arc_id": f"INFO_{index:02d}",
         "truths": [{"truth_id": f"TRUTH_{index:02d}_{slot}",
                     "statement": f"真相 {index}-{slot}",
                     "character_knows": [characters[index]],
                     "provenance": "generated"} for slot in range(2)],
         "moves": [
             {"move_id": f"IMOVE_{index:02d}_PLANT", "truth_id": f"TRUTH_{index:02d}_0",
              "move_type": "plant", "node_id": node_id(vid(index * 2), 4),
              "holder_ids": [characters[index]], "provenance": "generated"},
             {"move_id": f"IMOVE_{index:02d}_HINT", "truth_id": f"TRUTH_{index:02d}_0",
              "move_type": "hint", "node_id": node_id(vid(index * 2 + 2), 4),
              "holder_ids": [characters[(index + 1) % len(characters)]],
              "provenance": "generated"},
             {"move_id": f"IMOVE_{index:02d}_REVEAL", "truth_id": f"TRUTH_{index:02d}_0",
              "move_type": "reveal", "node_id": node_id(vid(index * 2 + 4), 4),
              "holder_ids": [characters[index]], "provenance": "generated"},
             {"move_id": f"IMOVE_{index:02d}_PAYOFF", "truth_id": f"TRUTH_{index:02d}_1",
              "move_type": "reveal", "node_id": node_id(vid(index + 1), 4),
              "holder_ids": [characters[index]], "provenance": "generated"},
         ],
         "provenance": "generated"}
        for index in range(2)]
    foreshadow_plans = [
        {"foreshadow_id": f"FSP_{index:02d}", "subject": f"伏笔 {index}",
         "intended_payoff": f"回收 {index}",
         "moves": [
             {"move_id": f"FSMOVE_{index:02d}_PLANT", "move_type": "plant",
              "node_id": node_id(index, 6), "description": "埋设", "provenance": "generated"},
             {"move_id": f"FSMOVE_{index:02d}_REINFORCE", "move_type": "reinforce",
              "node_id": node_id(vid(index + 2), 6), "description": "强化",
              "provenance": "generated"},
             {"move_id": f"FSMOVE_{index:02d}_PAYOFF", "move_type": "payoff",
              "node_id": node_id(vid(index + 4), 6), "description": "回收",
              "provenance": "generated"}],
         "plant_node_id": node_id(index, 6),
         "payoff_node_id": node_id(vid(index + 4), 6),
         "provenance": "generated"}
        for index in range(2)]
    for v in range(volume_count):
        for i in (4, 6):
            for row in node_rows:
                if row["node_id"] != node_id(v, i):
                    continue
                if i == 4:
                    row["information_move_refs"] = [
                        move["move_id"] for arc in information_arcs
                        for move in arc["moves"] if move["node_id"] == row["node_id"]]
                else:
                    row["foreshadow_move_refs"] = [
                        move["move_id"] for plan_row in foreshadow_plans
                        for move in plan_row["moves"] if move["node_id"] == row["node_id"]]
    progression_tracks = [
        {"track_id": f"TRACK_{index:02d}", "category": "ability",
         "label": f"成长线 {index}", "start_state": "起点",
         "milestones": [
             {"milestone_id": f"TRACKMILE_{index:02d}_{slot}",
              "label": f"里程碑 {index}-{slot}", "cost": f"代价 {slot}",
              "node_id": node_id(vid(slot * 2), 8),
              "provenance": "generated"}
             for slot in range(3)],
         "provenance": "generated"}
        for index in range(2)]
    for row in node_rows:
        labels = [milestone["milestone_id"] for track in progression_tracks
                  for milestone in track["milestones"] if milestone["node_id"] == row["node_id"]]
        if labels:
            row["progression_milestone_refs"] = labels
    reward_plans = [{
        "reward_plan_id": "REWARD_PLAN_MAIN", "provenance": "generated",
        "events": [
            {"reward_id": "REWARD_MAIN", "reward_type": "status", "magnitude": "minor",
             "scope": "scene", "trigger_node_id": node_id(0, 3),
             "recipient_ref": characters[0], "provenance": "generated"},
            {"reward_id": "REWARD_ARC", "reward_type": "resource", "magnitude": "medium",
             "scope": "arc", "trigger_node_id": node_id(1, 3),
             "recipient_ref": characters[0], "provenance": "generated"},
            {"reward_id": "REWARD_CLIMAX", "reward_type": "territory", "magnitude": "climax",
             "scope": "volume", "trigger_node_id": node_id(min(3, volume_count - 1), 0),
             "recipient_ref": characters[0], "provenance": "generated"}]}]
    map_expansions = [{
        "expansion_id": "MAPEXP_MAIN", "scope_note": "全地图", "provenance": "generated",
        "milestones": ([
            {"milestone_id": f"MAPMILE_KNOWN_{v:02d}", "location_ref": locations[v],
             "from_stage": "unknown", "to_stage": "known", "trigger_node_id": node_id(v, 0),
             "provenance": "generated"} for v in range(volume_count)]
            + [{"milestone_id": f"MAPMILE_REACH_{v:02d}", "location_ref": locations[v],
                "from_stage": "known", "to_stage": "reachable",
                "trigger_node_id": node_id(v, 1), "provenance": "generated"}
               for v in range(volume_count)]
            + [{"milestone_id": f"MAPMILE_CTRL_{v:02d}", "location_ref": locations[v],
                "from_stage": "reachable", "to_stage": "controlled",
                "trigger_node_id": node_id(v, 0), "provenance": "generated"}
               for v in (2, 4) if v < volume_count])}]
    conflict_chains = [
        {"conflict_id": f"CONFLICT_V{v:02d}", "title": f"第 {v + 1} 卷冲突",
         "related_node_ids": [node_id(v, 0), node_id(v, 1), node_id(v, per_volume // 2)],
         "stages": [
             {"stage_id": f"CSTAGE_V{v:02d}_MACRO", "conflict_id": f"CONFLICT_V{v:02d}",
              "scope": "macro", "trigger_node_id": node_id(v, 0),
              "stakes": "卷级升级", "provenance": "generated"},
             {"stage_id": f"CSTAGE_V{v:02d}_LOCAL", "conflict_id": f"CONFLICT_V{v:02d}",
              "scope": "local", "trigger_node_id": node_id(v, 1),
              "stakes": "局部冲突", "provenance": "generated"},
             {"stage_id": f"CSTAGE_V{v:02d}_VOLUME", "conflict_id": f"CONFLICT_V{v:02d}",
              "scope": "volume", "trigger_node_id": node_id(v, per_volume // 2),
              "constraint_change": "卷级约束变化", "provenance": "generated"}],
         "provenance": "generated"}
        for v in range(volume_count)]
    relationship_arcs = [
        {"arc_id": f"RELARC_{index:02d}", "participants": [characters[index], characters[index + 1]],
         "start_state": "试探", "relationship_change": "从试探到对立再合作",
         "stages": [
             {"stage_id": f"RSTAGE_{index:02d}_A", "label": "试探",
              "trigger_node_id": node_id(0, 2), "state": "合作一次"},
             {"stage_id": f"RSTAGE_{index:02d}_B", "label": "决裂",
              "trigger_node_id": node_id(min(2, volume_count - 1), 2), "state": "各自为战",
              "irreversible": True},
             {"stage_id": f"RSTAGE_{index:02d}_C", "label": "再合作",
              "trigger_node_id": node_id(min(4, volume_count - 1), 2), "state": "共享标准"}],
         "irreversible_node": node_id(min(2, volume_count - 1), 2),
         "provenance": "generated"}
        for index in range(2)]
    faction_arcs = [
        {"arc_id": f"FARC_{index:02d}", "faction_id": factions[index],
         "start_state": "观望", "end_state": "被迫接受独立标准",
         "stages": [
             {"stage_id": f"FSTAGE_{index:02d}_A", "label": "开价",
              "strategy": "以订单换标准", "trigger_node_id": node_id(vid(index + 1), 1),
              "expected_state": "合作开始"},
             {"stage_id": f"FSTAGE_{index:02d}_B", "label": "施压",
              "strategy": "断供", "trigger_node_id": node_id(vid(index + 3), 1),
              "expected_state": "供应紧张"}],
         "provenance": "generated"}
        for index in range(2)]
    character_arcs = [
        {"arc_id": f"CARCH_{index}", "character_id": characters[index],
         "start_state": "独行", "end_state": "承担组织责任",
         "major_choices": [{"node_id": node_id(min(index * 2, volume_count - 1), 5),
                            "choice": "接下责任", "provenance": "generated"}],
         "provenance": "supplied"}
        for index in range(3)]
    return {
        "planning_id": "PLAN_LONGBOOK", "novel_id": "demo_longbook",
        "intent": {"intent_id": "INTENT_LONG", "novel_id": "demo_longbook",
                   "target_words": per_volume * volume_count * 11_111,
                   "provenance": "supplied"},
        "theme": {"theme_id": "THEME_LONG", "dramatic_question": "能不能守住独立标准",
                  "final_answer_direction": "守住但付出代价", "provenance": "supplied"},
        "world": {"world_id": "WORLD_LONG", "economy": "供应链是主要压力",
                  "provenance": "supplied",
                  "world_rules": [{"rule_id": "RULE_PERMIT", "rule_type": "hard_rule",
                                   "statement": "接商单必须有执照", "scope": "全城",
                                   "provenance": "supplied"}]},
        "characters": [{"character_id": characters[index],
                        "display_name": f"角色 {index}",
                        "entity_ref": "ENTITY_PROTAGONIST" if index == 0 else "",
                        "provenance": "supplied"} for index in range(6)],
        "character_arcs": character_arcs,
        "factions": [{"faction_id": factions[index], "display_name": f"势力 {index}",
                      "provenance": "supplied"} for index in range(3)],
        "faction_arcs": faction_arcs,
        "faction_relations": [
            {"relation_id": f"FREL_{index:02d}", "relation_type": "competition",
             "from_faction_id": factions[index % 3],
             "to_faction_id": factions[(index + 1) % 3], "state": "争夺同一市场",
             "trigger_node_id": node_id(vid(index + 1), 3), "provenance": "generated"}
            for index in range(2)],
        "locations": [{"location_id": locations[v], "display_name": f"区域 {v}",
                       "provenance": "supplied"} for v in range(volume_count)],
        "location_graph": {
            "graph_id": "LOCGRAPH_LONG",
            "location_ids": locations,
            "edges": [{"from_location_id": locations[v], "to_location_id": locations[v + 1],
                       "route": "路径", "provenance": "generated"}
                      for v in range(volume_count - 1)],
            "provenance": "generated"},
        "relationship_arcs": relationship_arcs,
        "information_arcs": information_arcs,
        "foreshadow_plans": foreshadow_plans,
        "progression_tracks": progression_tracks,
        "unit_defs": [{"unit_id": "UNIT_COUNT", "unit_kind": "count", "label": "件",
                       "provenance": "supplied"},
                      {"unit_id": "UNIT_CREDIT", "unit_kind": "currency", "label": "信用点",
                       "provenance": "supplied"}],
        "resource_plans": [
            {"resource_plan_id": "RPLAN_CREDIT", "resource_id": "RES_CREDIT",
             "unit_id": "UNIT_CREDIT", "category": "currency", "scarcity": "common",
             "renewable": True, "provenance": "supplied"},
            {"resource_plan_id": "RPLAN_MATERIAL", "planned_resource_id": "PLANNED_MATERIAL_1",
             "unit_id": "UNIT_COUNT", "category": "material", "scarcity": "scarce",
             "storage_limit": 500, "renewable": False, "provenance": "generated"}],
        "resource_flows": [
            {"flow_id": f"RFLOW_{v:02d}", "planned_resource_id": "PLANNED_MATERIAL_1",
             "flow_type": "acquire" if v % 2 == 0 else "consume",
             "amount": 120 if v % 2 == 0 else 40, "unit_id": "UNIT_COUNT",
             "target_ref": "BASE_MAIN", "trigger_node_id": node_id(v, 10),
             "repeatability": "repeatable" if v % 2 == 0 else "once",
             "provenance": "generated"}
            for v in range(volume_count)],
        "equipment_plans": [
            {"equipment_id": "EQ_TOOL_MAIN", "equipment_ref": "ITEM_TOOL",
             "display_name": "主力工具", "owner_ref": characters[0],
             "acquisition_node": node_id(0, 0), "damage_nodes": [node_id(vid(1), 0)],
             "repair_nodes": [node_id(vid(2), 0)], "unique": True,
             "story_function": "手艺标准的象征", "provenance": "supplied",
             "lifecycle": [
                 {"step_id": "EQSTEP_A", "state": "acquired", "node_id": node_id(0, 0),
                  "detail": "开箱"},
                 {"step_id": "EQSTEP_B", "state": "damaged", "node_id": node_id(vid(1), 0),
                  "detail": "摔伤"},
                 {"step_id": "EQSTEP_C", "state": "repaired", "node_id": node_id(vid(2), 0),
                  "detail": "校准"}]}],
        "base_progressions": [{
            "base_id": "BASE_MAIN", "base_ref": locations[0], "display_name": "据点",
            "story_function": "主角据点", "provenance": "supplied",
            "start_stage_id": "BASESTAGE_A", "end_stage_id": "BASESTAGE_B",
            "stages": [
                {"stage_id": "BASESTAGE_A", "label": "单工位", "capacity": "1 工位",
                 "unlock_node": node_id(0, 0), "provenance": "supplied"},
                {"stage_id": "BASESTAGE_B", "label": "带学徒", "capacity": "3 工位",
                 "unlock_node": node_id(min(2, volume_count - 1), 0),
                 "requirements": {"operator": "all", "requirements": [
                     {"requirement_id": "REQ_BASE_B", "kind": "progression",
                      "ref_id": "TRACKMILE_00_1", "description": "资金与标准",
                      "provenance": "generated"}]},
                 "provenance": "generated"}]}],
        "map_expansions": map_expansions,
        "reward_plans": reward_plans,
        "autonomous_actions": [
            {"action_id": f"ACT_{index:02d}", "actor_ref": factions[index],
             "goal": "逼工作室接受统一标准", "trigger_ref": node_id(vid(index + 1), 3),
             "location_ref": locations[min(index + 1, volume_count - 1)],
             "target_refs": [characters[0], "BASE_MAIN"],
             "planned_action": "断供关键零件", "expected_consequence": "现金流承压",
             "visibility": "faction_internal", "provenance": "generated"}
            for index in range(2)],
        "plot_nodes": node_rows,
        "spine": {"spine_id": "SPINE_LONG", "novel_id": "demo_longbook",
                  "nodes": [row["node_id"] for row in node_rows], "edges": edges,
                  "entry_node_ids": [node_rows[0]["node_id"]],
                  "terminal_node_ids": [node_rows[-1]["node_id"]],
                  "provenance": "generated"},
        "conflict_chains": conflict_chains,
        "volumes": [
            {"volume_id": volume_id(v), "index": v + 1, "title": f"第 {v + 1} 卷",
             "volume_goal": f"完成第 {v + 1} 卷目标",
             "opening_state": f"第 {v + 1} 卷开局", "major_conflict": f"第 {v + 1} 卷主冲突",
             "location_expansion": [locations[v]],
             "major_nodes": [node_id(v, i) for i in range(per_volume)],
             "climax_node_id": node_id(v, per_volume - 1),
             "ending_state": f"第 {v + 1} 卷收束",
             "detail_level": "spine" if v % 2 == 0 else "volume",
             "provenance": "supplied"}
            for v in range(volume_count)],
        "arcs": [],
        "pacing": {"pacing_id": "PACE_LONG", "template_id": "TEMPLATE_NEUTRAL",
                   "strategy": "逐卷升级", "provenance": "generated",
                   "bands": [{"volume_id": volume_id(v),
                              "intensity": {"conflict": 0.2 + 0.1 * v}}
                             for v in range(volume_count)]},
    }


class _ScriptedCompiler(OutlineCompiler):
    """按 batch 注入 retryable failure / human review 的确定性编译器（测试专用）。"""

    def __init__(self, *, transient_failures: dict[str, int] | None = None,
                 review_batches: set[str] | None = None, **kwargs) -> None:
        super().__init__(**kwargs)
        self.transient_failures = dict(transient_failures or {})
        self.review_batches = set(review_batches or [])
        self.calls: list[str] = []
        self.reviewed: set[str] = set()

    def compile(self, plan, *, revision_id: str = "", scope=None, inventory=None,
                route_provenance=None):
        batch = str((route_provenance or {}).get("batch_id", ""))
        self.calls.append(batch)
        pending = self.transient_failures.get(batch, 0)
        if pending > 0:
            self.transient_failures[batch] = pending - 1
            raise OutlineBatchFailure("NETWORK", "simulated provider timeout")
        candidate = super().compile(plan, revision_id=revision_id, scope=scope,
                                    inventory=inventory, route_provenance=route_provenance)
        if batch in self.review_batches and batch not in self.reviewed:
            self.reviewed.add(batch)
            node = (scope.node_ids[0] if scope and scope.node_ids else "")
            findings = list(candidate.validation_findings) + [PlanningFinding(
                code="UNALLOCATED_MUST_HAPPEN_NODE", severity="ERROR", domain="outline",
                source_id=node, message="simulated human decision required")]
            return candidate.model_copy(update={"validation_findings": findings,
                                                "status": "blocked"})
        return candidate


def _session(tmp_path: Path, raw: dict | None = None, *, mode: str = "safe_auto",
             compiler: OutlineCompiler | None = None, scope_kind: str = "full_book",
             config: CompilerConfig | None = None):
    plan = validate_planning_ir(raw or _spine_ready())
    repo = PlanningRepository(tmp_path, plan.novel_id)
    repo.create(plan, revision_id="PREV_B0")
    batch_compiler = OutlineBatchCompiler(repo, compiler=compiler)
    session = batch_compiler.create_session(
        scope=CompilationScope(kind=scope_kind),
        promotion_policy=PromotionPolicy(mode=mode), config=config)
    return repo, batch_compiler, session


# ---------------------------------------------------------------- 批次计划
def test_plan_batch_scopes_targets_each_volume_once(tmp_path: Path) -> None:
    repo, compiler, session = _session(tmp_path, _long_book_raw(volume_count=4, per_volume=12))
    assert [task.batch_id for task in session.tasks] == [
        "BATCH_001", "BATCH_002", "BATCH_003", "BATCH_004"]
    assert [task.scope.note for task in session.tasks] == [
        "VOL_V00", "VOL_V01", "VOL_V02", "VOL_V03"]
    assert session.tasks[0].dependency_batch_ids == []
    assert session.tasks[1].dependency_batch_ids == ["BATCH_001"]
    assert all(task.target_detail_level == "arc" for task in session.tasks)
    assert all(task.status == "pending" for task in session.tasks)


def test_next_volume_scope_only_plans_one_batch(tmp_path: Path) -> None:
    repo, compiler, session = _session(tmp_path, _long_book_raw(volume_count=4, per_volume=12),
                                       scope_kind="next_volume")
    assert len(session.tasks) == 1
    assert session.tasks[0].scope.note == "VOL_V00"
    session = compiler.run_session(session.session_id)
    assert session.scope_complete is True
    assert len(session.completed_batch_ids) == 1
    # 其余卷仍然停在原深度：partial session 不等于全书完成
    record = repo.load(session.final_revision_id)
    levels = {volume.detail_level for volume in record.plan.volumes}
    assert "arc" in levels and len(record.plan.volumes) > 1


def test_scope_planner_skips_volumes_already_at_target(tmp_path: Path) -> None:
    raw = _long_book_raw(volume_count=3, per_volume=12)
    raw["volumes"][0]["detail_level"] = "arc"
    plan = validate_planning_ir(raw)
    repo = PlanningRepository(tmp_path, plan.novel_id)
    repo.create(plan, revision_id="PREV_B0")
    session = OutlineBatchCompiler(repo).create_session(
        scope=CompilationScope(kind="full_book"), promotion_policy=PromotionPolicy(mode="safe_auto"))
    assert [task.scope.note for task in session.tasks] == ["VOL_V01", "VOL_V02"]


def test_chapter_ready_requires_m9() -> None:
    with pytest.raises(OutlineBatchError) as excinfo:
        check_detail_target("chapter_ready")
    assert excinfo.value.code == "DETAIL_LEVEL_REQUIRES_M9"
    with pytest.raises(OutlineBatchError) as excinfo:
        check_detail_target("unknown_level")
    assert excinfo.value.code == "DETAIL_LEVEL_UNKNOWN"
    check_detail_target("arc")


def test_create_session_rejects_chapter_ready(tmp_path: Path) -> None:
    plan = validate_planning_ir(_spine_ready())
    repo = PlanningRepository(tmp_path, plan.novel_id)
    repo.create(plan, revision_id="PREV_B0")
    with pytest.raises(OutlineBatchError) as excinfo:
        OutlineBatchCompiler(repo).create_session(target_detail_level="chapter_ready")
    assert excinfo.value.code == "DETAIL_LEVEL_REQUIRES_M9"


# ---------------------------------------------------------------- promote / chain
def test_safe_auto_session_promotes_and_chains_revisions(tmp_path: Path) -> None:
    repo, compiler, session = _session(tmp_path)
    done = compiler.run_session(session.session_id)
    assert done.status == "promoted" and done.scope_complete is True
    assert done.final_revision_id and done.final_revision_id != done.root_planning_revision_id
    record = repo.load(done.final_revision_id)
    assert record.parent_revision_id == done.root_planning_revision_id
    assert record.plan.volumes and all(volume.detail_level == "arc"
                                       for volume in record.plan.volumes)
    assert record.plan.arcs and all(arc.chapter_budget > 0 for arc in record.plan.arcs)
    assert len(repo.list_revisions()) == 2


def test_manual_policy_pauses_until_author_approves(tmp_path: Path) -> None:
    repo, compiler, session = _session(tmp_path, mode="manual")
    paused = compiler.run_session(session.session_id)
    assert paused.status == "validated"
    assert len(repo.list_revisions()) == 1        # 还没有 promote
    task, checkpoint = compiler.approve_batch(session.session_id, "BATCH_001")
    assert task.status == "promoted"
    assert checkpoint.status == "promoted" and checkpoint.completed_steps[-1] == "promote"
    assert len(repo.list_revisions()) == 2


def test_idempotent_compile_same_digest_and_single_promotion(tmp_path: Path) -> None:
    repo, compiler, session = _session(tmp_path, mode="manual")
    first_task, first = compiler.run_batch(session.session_id, "BATCH_001")
    second_task, second = compiler.run_batch(session.session_id, "BATCH_001")
    assert first.candidate_digest == second.candidate_digest
    assert first_task.candidate_id == second_task.candidate_id
    assert len(repo.list_revisions()) == 1
    promoted_task, promoted = compiler.approve_batch(session.session_id, "BATCH_001")
    assert promoted.status == "promoted"
    again_task, again = compiler.run_batch(session.session_id, "BATCH_001")
    assert again.status == "promoted"
    assert again.promoted_revision_id == promoted.promoted_revision_id
    assert again_task.promoted_revision_id == promoted_task.promoted_revision_id
    assert len(repo.list_revisions()) == 2        # promotion 只发生一次


def test_crash_after_promotion_recovers_without_duplicate_revision(tmp_path: Path) -> None:
    repo, compiler, session = _session(tmp_path, _long_book_raw(volume_count=3, per_volume=12))
    store = compiler.store
    compiler.run_batch(session.session_id, "BATCH_001")
    snapshot = store.load_session(session.session_id)     # batch 01 已完整 checkpoint
    task_two, checkpoint_two = compiler.run_batch(session.session_id, "BATCH_002")
    assert task_two.status == "promoted"
    store.save_session(snapshot)                          # 模拟：session 还没写就被中断
    store.path(session.session_id, "checkpoint_BATCH_002.json").unlink()
    revisions_after_crash = len(repo.list_revisions())
    repaired = compiler.repair_session(session.session_id)
    assert repaired.current_revision_id == checkpoint_two.promoted_revision_id
    recovered = store.load_checkpoint(session.session_id, "BATCH_002")
    assert recovered is not None and recovered.status == "promoted"
    assert recovered.promoted_revision_id == task_two.promoted_revision_id
    assert recovered.resume_state.get("recovered") is True
    assert len(repo.list_revisions()) == revisions_after_crash   # 绝不重复 promote
    done = compiler.resume_batch_session(session.session_id)
    assert done.status == "promoted" and done.scope_complete is True
    assert len(repo.list_revisions()) == revisions_after_crash + 1  # 只剩缺失的下一批


def test_stale_branch_head_blocks_resume_with_options(tmp_path: Path) -> None:
    repo, compiler, session = _session(tmp_path, _long_book_raw(volume_count=2, per_volume=12))
    compiler.run_batch(session.session_id, "BATCH_001")
    head = repo.load(session.root_planning_revision_id)
    repo.create(head.plan, revision_id="PREV_EXTERNAL")     # 外部推进 branch head
    with pytest.raises(OutlineBatchError) as excinfo:
        compiler.resume_batch_session(session.session_id)
    assert excinfo.value.code == "STALE_BATCH_SESSION"
    assert "restart_batch_session" in excinfo.value.message
    restarted = compiler.restart_batch_session(session.session_id)
    assert restarted.current_revision_id == "PREV_EXTERNAL"
    assert restarted.batch_policy.get("restarted_from") == session.session_id
    assert compiler.store.load_session(session.session_id).status == "superseded"


def test_config_change_since_checkpoint_detected(tmp_path: Path) -> None:
    repo, compiler, session = _session(tmp_path)
    compiler.run_batch(session.session_id, "BATCH_001", approve=False)
    stored = compiler.store.load_session(session.session_id)
    config = dict(stored.batch_policy["config"])
    config["segmentation"] = {**config["segmentation"], "chapter_target_words": 4200}
    compiler.store.save_session(stored.model_copy(update={
        "batch_policy": {**stored.batch_policy, "config": config}}))
    with pytest.raises(OutlineBatchError) as excinfo:
        compiler.run_batch(session.session_id, "BATCH_001", approve=True)
    assert excinfo.value.code == "CONFIG_CHANGED_SINCE_CHECKPOINT"


# ---------------------------------------------------------------- failure taxonomy
def test_retryable_failure_is_retried_then_promoted(tmp_path: Path) -> None:
    scripted = _ScriptedCompiler(transient_failures={"BATCH_002": 1})
    repo, compiler, session = _session(tmp_path, _long_book_raw(volume_count=3, per_volume=12),
                                       compiler=scripted)
    done = compiler.run_session(session.session_id)
    assert done.status == "promoted" and done.scope_complete is True
    assert scripted.calls.count("BATCH_002") == 2
    checkpoint = compiler.store.load_checkpoint(session.session_id, "BATCH_002")
    assert checkpoint.status == "promoted" and checkpoint.attempt_count == 2
    manifest = compiler.manifest(session.session_id)
    assert manifest.retry_count == 1
    assert len(repo.list_revisions()) == 4


def test_structural_error_is_not_retried(tmp_path: Path) -> None:
    class _AlwaysInvalid(OutlineCompiler):
        def __init__(self) -> None:
            super().__init__()
            self.calls = 0

        def compile(self, *args, **kwargs):
            self.calls += 1
            raise ValueError("candidate 结构错误（不应重试）")

    scripted = _AlwaysInvalid()
    repo, compiler, session = _session(tmp_path, compiler=scripted)
    stopped = compiler.run_session(session.session_id)
    assert scripted.calls == 1                       # VALIDATION 不重试
    assert stopped.status == "blocked"
    assert stopped.failed_batch_ids == ["BATCH_001"]
    assert len(repo.list_revisions()) == 1
    checkpoint = compiler.store.load_checkpoint(session.session_id, "BATCH_001")
    assert checkpoint.status == "failed" and checkpoint.error_class == "VALIDATION"
    assert checkpoint.next_retry_at is None


def test_human_review_stops_unattended_run_and_resumes_after_resolution(tmp_path: Path) -> None:
    scripted = _ScriptedCompiler(review_batches={"BATCH_002"})
    repo, compiler, session = _session(tmp_path, _long_book_raw(volume_count=3, per_volume=12),
                                       compiler=scripted)
    stopped = compiler.run_session(session.session_id)
    assert stopped.status == "human_review"
    assert stopped.review_required_batch_ids == ["BATCH_002"]
    assert len(repo.list_revisions()) == 2           # 只有 batch 01 被 promote
    checkpoint = compiler.store.load_checkpoint(session.session_id, "BATCH_002")
    assert checkpoint.status == "human_review"
    assert [item.code for item in checkpoint.review_findings] \
        == ["UNALLOCATED_MUST_HAPPEN_NODE"]
    resolved = compiler.resume_batch_session(session.session_id, retry_review=True)
    assert resolved.status == "promoted" and resolved.scope_complete is True
    assert len(repo.list_revisions()) == 4


def test_warning_policy_can_route_warning_to_review_or_block(tmp_path: Path) -> None:
    review_config = CompilerConfig(author_overrides={
        "warning_policy": {"review_codes": ["CLIMAX_WITHOUT_ESCALATION"]}})
    repo, compiler, session = _session(tmp_path, config=review_config)
    task, checkpoint = compiler.run_batch(session.session_id, "BATCH_001")
    assert task.status == "human_review"
    assert [item.code for item in checkpoint.review_findings] \
        == ["CLIMAX_WITHOUT_ESCALATION"]
    assert len(repo.list_revisions()) == 1

    blocking_config = CompilerConfig(author_overrides={
        "warning_policy": {"promotion_blocking_codes": ["CLIMAX_WITHOUT_ESCALATION"]}})
    repo2, compiler2, session2 = _session(tmp_path / "blocking", config=blocking_config)
    task2, checkpoint2 = compiler2.run_batch(session2.session_id, "BATCH_001")
    assert task2.status == "blocked"
    assert checkpoint2.review_findings == []
    assert "CLIMAX_WITHOUT_ESCALATION" in {item.code for item in checkpoint2.findings}
    assert "CLIMAX_WITHOUT_ESCALATION" not in {
        item.code for item in checkpoint2.findings if item.severity == "ERROR"}


# ---------------------------------------------------------------- carryover / 跨批
def test_carryover_chain_advances_and_warns_long_running_pressure(tmp_path: Path) -> None:
    raw = _long_book_raw(volume_count=3, per_volume=12)
    plan = validate_planning_ir(raw)
    repo = PlanningRepository(tmp_path, plan.novel_id)
    repo.create(plan, revision_id="PREV_B0")
    from novelforge.story_engine.planning import build_plot_pressure_inventory
    inventory = build_plot_pressure_inventory(plan, revision_id="PREV_B0")
    deferred = next(item for item in inventory.pressures if item.state == "deferred")
    compiler = OutlineBatchCompiler(repo)
    session = compiler.create_session(
        scope=CompilationScope(kind="full_book"),
        promotion_policy=PromotionPolicy(mode="safe_auto"),
        config=CompilerConfig(segmentation=SegmentationProfile(carryover_tolerance=1)))
    seeded = dict(session.batch_policy["carry_registry"])
    seeded[deferred.pressure_id] = {
        "pressure_id": deferred.pressure_id, "origin_volume": "VOL_V00",
        "last_seen_volume": "VOL_V00", "to_volume": "VOL_V00", "carry_count": 1,
        "reason": "prior_node_consequence", "status": "deferred"}
    compiler.store.save_session(session.model_copy(update={
        "batch_policy": {**session.batch_policy, "carry_registry": seeded}}))
    task, checkpoint = compiler.run_batch(session.session_id, "BATCH_001")
    assert task.status == "promoted"
    assert "LONG_RUNNING_PRESSURE" in {item.code for item in checkpoint.findings}
    registry = compiler.store.load_session(session.session_id).batch_policy["carry_registry"]
    assert registry[deferred.pressure_id]["carry_count"] == 2
    assert registry[deferred.pressure_id]["last_seen_volume"] == "VOL_B001_01"
    assert registry[deferred.pressure_id]["to_volume"] == "VOL_V01"
    assert registry[deferred.pressure_id]["origin_volume"] == "VOL_V00"


def test_pressure_lost_at_batch_boundary_is_error(tmp_path: Path) -> None:
    repo, compiler, session = _session(tmp_path, _long_book_raw(volume_count=2, per_volume=12))
    seeded = dict(session.batch_policy["carry_registry"])
    seeded["PRESS_9999"] = {"pressure_id": "PRESS_9999", "origin_volume": "VOL_V00",
                            "last_seen_volume": "VOL_V00", "to_volume": "VOL_V00",
                            "carry_count": 1, "reason": "custom", "status": "blocked"}
    compiler.store.save_session(session.model_copy(update={
        "batch_policy": {**session.batch_policy, "carry_registry": seeded}}))
    task, checkpoint = compiler.run_batch(session.session_id, "BATCH_001")
    assert task.status == "blocked"
    assert "PRESSURE_LOST_AT_BATCH_BOUNDARY" in {item.code for item in checkpoint.findings}
    assert len(repo.list_revisions()) == 1


def test_partial_overlap_and_duplicate_allocation_are_blocking(tmp_path: Path) -> None:
    repo, compiler, session = _session(tmp_path, _long_book_raw(volume_count=2, per_volume=12))
    compiler.run_batch(session.session_id, "BATCH_001")
    scope = CompilationScope(kind="spine_segment",
                             node_ids=["NODE_V00_05", "NODE_V00_06", "NODE_V01_00"])
    updated = compiler.recompile_scope(session.session_id, scope)
    task, checkpoint = compiler.run_batch(updated.session_id, updated.tasks[-1].batch_id)
    codes = {item.code for item in checkpoint.findings}
    assert "BOUNDARY_REVISION_REQUIRED" in codes
    assert "CROSS_BATCH_DUPLICATE_EXECUTION_NODE" in codes
    assert task.status == "human_review"
    assert task.batch_id in compiler.store.load_session(session.session_id).review_required_batch_ids
    assert len(repo.list_revisions()) == 2


def test_recompile_scope_keeps_history_and_supersedes_batches(tmp_path: Path) -> None:
    repo, compiler, session = _session(tmp_path, _long_book_raw(volume_count=3, per_volume=12))
    done = compiler.run_session(session.session_id)
    assert len(repo.list_revisions()) == 4
    scope = CompilationScope(kind="volume_range",
                             node_ids=[f"NODE_V01_{index:02d}" for index in range(12)],
                             note="VOL_V01")
    updated = compiler.recompile_scope(done.session_id, scope)
    statuses = {task.batch_id: task.status for task in updated.tasks}
    assert statuses["BATCH_002"] == "superseded"
    new_task = updated.tasks[-1]
    assert new_task.supersedes_batch_ids == ["BATCH_002"]
    assert new_task.source_revision_id == done.final_revision_id
    assert len(repo.list_revisions()) == 4        # 历史 revision 没有被改写
    task, checkpoint = compiler.run_batch(updated.session_id, new_task.batch_id)
    assert task.status == "promoted"
    record = repo.load(task.promoted_revision_id)
    assert record.parent_revision_id == done.final_revision_id
    assert len(repo.list_revisions()) == 5


def test_invalidation_analysis_finds_downstream_batches(tmp_path: Path) -> None:
    repo, compiler, session = _session(tmp_path, _long_book_raw(volume_count=3, per_volume=12))
    plan = repo.load(session.root_planning_revision_id).plan
    analysis = compiler.invalidation_analysis(plan, ["NODE_V00_00"])
    assert analysis["scope"] == ["full"] or analysis["volumes"]
    assert "NODE_V00_01" in analysis["downstream"]
    scoped = compiler.invalidation_for_session(session.session_id, ["NODE_V01_00"])
    assert "BATCH_002" in scoped["stale_batch_ids"]


# ---------------------------------------------------------------- gate / manifest / projection
def test_session_gate_manifest_and_diffs(tmp_path: Path) -> None:
    repo, compiler, session = _session(tmp_path, _long_book_raw(volume_count=3, per_volume=12))
    done = compiler.run_session(session.session_id)
    gate = compiler.session_gate(session.session_id)
    assert gate["ok"] is True
    assert all(gate["checks"].values())
    assert gate["summary"]["blocking"] == []
    manifest = compiler.manifest(session.session_id)
    assert manifest.status == "promoted" and manifest.scope_complete is True
    assert len(manifest.revision_chain) == 3
    assert manifest.detail_changes and manifest.carryover
    assert manifest.retry_count == 0 and manifest.human_reviews == []
    for row in manifest.revision_chain:
        assert repo.exists(row["promoted"]) and row["digest"]
    diff = compiler.batch_diff(session.root_planning_revision_id, done.final_revision_id)
    assert diff.volumes_added and diff.detail_level_changes
    assert diff.findings_changes["volumes_after"] >= diff.findings_changes["volumes_before"]
    assert diff.findings_changes["arcs_after"] > 0
    session_diff = compiler.session_diff(session.session_id)
    assert session_diff.before_revision == session.root_planning_revision_id
    assert session_diff.after_revision == done.final_revision_id


def test_projection_is_read_only_and_discrete(tmp_path: Path) -> None:
    repo, compiler, session = _session(tmp_path, _long_book_raw(volume_count=3, per_volume=12))
    done = compiler.run_session(session.session_id)
    plan = repo.load(done.current_revision_id).plan
    checkpoints = {task.batch_id: compiler.store.load_checkpoint(done.session_id, task.batch_id)
                   for task in done.tasks}
    snapshot = project_batch_session(done, checkpoints=checkpoints, plan=plan)
    assert snapshot.read_only is True and snapshot.non_authoritative is True
    assert snapshot.batches_completed == snapshot.batches_total == 3
    assert snapshot.detail_level_counts.get("arc") == len(plan.volumes)
    assert snapshot.final_revision_id == done.final_revision_id
    assert snapshot.resume_required is False
    assert not hasattr(snapshot, "save")
    text = json.dumps(snapshot.model_dump(mode="json"), ensure_ascii=False)
    assert "percent" not in text.lower()
    assert all(task.read_only for task in snapshot.tasks)
    progress = project_elaboration_progress(done, plan)
    assert progress.read_only is True
    assert progress.remaining_object_ids == []
    assert progress.detail_level_counts.get("arc") == len(plan.volumes)
    chain = project_revision_chain(done)
    assert chain.contiguous is True and len(chain.rows) == 3
    assert chain.root_revision_id == session.root_planning_revision_id
    completeness = project_planning_completeness(plan, revision_id=done.current_revision_id)
    assert completeness.arc_coverage == len(plan.volumes)
    assert completeness.remaining_elaboration_scopes == []


def test_batch_context_purposes_scope_payload(tmp_path: Path) -> None:
    plan = validate_planning_ir(_long_book_raw(volume_count=3, per_volume=12))
    builder = StoryPlanningContextBuilder(plan, revision_id="PREV_B0")
    for purpose in ("batch_compile", "batch_review", "batch_resume"):
        context = builder.build(purpose, ids=["VOL_V01"])
        assert {"scope", "plot_nodes", "volumes", "arcs", "spine_edges",
                "upstream_dependencies", "carryover_pressures"} <= set(context.payload)
        scoped = set(context.payload["scope"]["node_ids"])
        assert scoped and len(scoped) < len(plan.plot_nodes)
        assert all(node["node_id"] in scoped for node in context.payload["plot_nodes"])
        assert context.boundary == "planning_future_not_happened"


def test_batch_compile_output_has_no_chapter_ir(tmp_path: Path) -> None:
    repo, compiler, session = _session(tmp_path, _long_book_raw(volume_count=2, per_volume=12))
    done = compiler.run_session(session.session_id)
    record = repo.load(done.final_revision_id)
    text = json.dumps(record.plan.model_dump(mode="json"), ensure_ascii=False)
    for term in ("chapter_uuid", "CH001", "ChapterEventFrame", "ChapterStateTransition"):
        assert term not in text
    assert {arc.detail_level for arc in record.plan.arcs} == {"arc"}
    assert {volume.detail_level for volume in record.plan.volumes} == {"arc"}
    # checkpoint 不是第二套 truth：只存 refs / digests
    checkpoint = compiler.store.load_checkpoint(session.session_id, "BATCH_001")
    payload = checkpoint.model_dump(mode="json")
    assert "volume_plans" not in payload and "arc_plans" not in payload
    assert payload["promoted_revision_id"] and payload["candidate_digest"]


def test_no_fixed_volume_or_arc_count(tmp_path: Path) -> None:
    small_repo, small_compiler, small_session = _session(
        tmp_path / "small", _long_book_raw(volume_count=2, per_volume=12))
    big_repo, big_compiler, big_session = _session(
        tmp_path / "big", _long_book_raw(volume_count=5, per_volume=12))
    small_done = small_compiler.run_session(small_session.session_id)
    big_done = big_compiler.run_session(big_session.session_id)
    small_plan = small_repo.load(small_done.final_revision_id).plan
    big_plan = big_repo.load(big_done.final_revision_id).plan
    assert len(big_plan.volumes) > len(small_plan.volumes)
    arc_counts = sorted(len(volume.arc_ids) for volume in big_plan.volumes)
    assert len(set(arc_counts)) > 1          # Arc 数由结构决定，不是固定值


# ---------------------------------------------------------------- long-book E2E
def test_long_book_end_to_end_with_retry_and_review(tmp_path: Path) -> None:
    scripted = _ScriptedCompiler(transient_failures={"BATCH_002": 1},
                                 review_batches={"BATCH_003"})
    config = CompilerConfig(target_words=1_200_000,
                            segmentation=SegmentationProfile(carryover_tolerance=2))
    repo, compiler, session = _session(tmp_path, _long_book_raw(), compiler=scripted,
                                       config=config)
    plan = repo.load(session.root_planning_revision_id).plan
    assert len(plan.plot_nodes) >= 100 and len(plan.volumes) >= 6
    stopped = compiler.run_session(session.session_id, max_batches=12)
    assert stopped.status == "human_review"
    assert stopped.review_required_batch_ids == ["BATCH_003"]
    assert len(repo.list_revisions()) == 3          # root + batch 01 + batch 02
    resumed = compiler.resume_batch_session(session.session_id, retry_review=True)
    assert resumed.status == "promoted" and resumed.scope_complete is True
    gate = compiler.session_gate(session.session_id)
    assert gate["ok"] is True and all(gate["checks"].values())
    record = repo.load(resumed.final_revision_id)
    assert len(record.plan.volumes) >= 6
    assert all(volume.detail_level == "arc" for volume in record.plan.volumes)
    executions: dict[str, set[str]] = {}
    for volume in record.plan.volumes:
        for node_id in volume.major_nodes:
            executions.setdefault(node_id, set()).add(volume.volume_id)
    assert all(len(volumes) == 1 for volumes in executions.values())
    allocated = set(executions)
    assert {node.node_id for node in record.plan.plot_nodes if node.must_happen} <= allocated
    assert len({len(volume.arc_ids) for volume in record.plan.volumes}) > 1
    manifest = compiler.manifest(session.session_id)
    # 1 次 provider retry + 1 次 human review 后重试
    assert manifest.retry_count == 2
    assert manifest.human_reviews == ["BATCH_003"]
    assert len(manifest.revision_chain) == len(session.tasks) == 6
    previous = session.root_planning_revision_id
    for row in manifest.revision_chain:
        assert repo.load(row["promoted"]).parent_revision_id == previous
        previous = row["promoted"]
    assert previous == resumed.final_revision_id
    for task in resumed.tasks:
        checkpoint = compiler.store.load_checkpoint(session.session_id, task.batch_id)
        assert checkpoint.status == "promoted"
    registry = resumed.batch_policy["carry_registry"]
    assert registry, "未解决 pressure 必须在 carry registry 里继续可见"


def test_cross_genre_sessions_are_neutral(tmp_path: Path) -> None:
    for index, name in enumerate(("URBAN_GROWTH_EXAMPLE.json", "MODERN_CITY_EXAMPLE.json",
                                  "FANTASY_EXAMPLE.json", "ONE_SENTENCE_EXAMPLE.json")):
        repo, compiler, session = _session(tmp_path / f"genre_{index}", _spine_ready(name))
        done = compiler.run_session(session.session_id)
        assert done.status == "promoted", name
        assert done.scope_complete is True, name
        record = repo.load(done.final_revision_id)
        assert record.plan.volumes, name
        assert all(volume.detail_level == "arc" for volume in record.plan.volumes), name


def test_batch_modules_have_no_genre_or_wasteland_hardcoding() -> None:
    offenders: list[str] = []
    for name in ("outline_batch.py", "outline_batch_projection.py"):
        text = (BATCH_DIR / name).read_text(encoding="utf-8")
        for term in ("wasteland", "废土", "xianxia", "修仙", "爽文", "BEAT_LADDER",
                     "FuturePlan", "if genre ==", "WASTELAND"):
            if term in text:
                offenders.append(f"{name}: {term}")
    assert offenders == []
