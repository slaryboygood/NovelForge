"""M9：cross-genre golden + NEW NOVEL E2E（一句话 → … → Detailed Chapter Outline）。"""

from __future__ import annotations

import json
from pathlib import Path

from novelforge.story_engine.chapter_ir.validator import ChapterIRValidator
from novelforge.story_engine.planning import (
    ArcChapterBatchCompiler,
    ChapterCompiler,
    CompilationScope,
    OutlineBatchCompiler,
    PlanningRouteLabService,
    PlanningRepository,
    PromotionPolicy,
    StaticPlotCandidateProvider,
    StaticRouteCandidateProvider,
    StoryPlanningContextBuilder,
    build_planning_state_registry,
    propose_candidates,
    project_detailed_outline,
    promote_candidate,
    validate_planning_ir,
)
from novelforge.story_engine.spec import NovelSpec, NovelSpecCompiler

FIXTURES = Path("tests/fixtures/planning_ir")
CHAPTER_DIR = Path("src/novelforge/story_engine/planning")


def _fixture(name: str):
    return validate_planning_ir(json.loads((FIXTURES / name).read_text(encoding="utf-8")))


def test_cross_genre_arc_golden_uses_chapter_ir_only() -> None:
    """现实 / 都市 / 奇幻三种题材的 Arc 都编译成同一套 Chapter Semantic IR。"""

    for name in ("MODERN_CITY_EXAMPLE.json", "URBAN_GROWTH_EXAMPLE.json",
                 "FANTASY_EXAMPLE.json"):
        plan = _fixture(name)
        arc = plan.arcs[0]
        candidate = ChapterCompiler().compile(plan, revision_id="PREV_CG", arc_id=arc.arc_id)
        assert candidate.chapter_irs, name
        assert not [item for item in candidate.validation_findings
                    if item.severity == "ERROR"], (name, [item.code for item in
                                                          candidate.validation_findings])
        assert candidate.coverage.plot_nodes_anchored == candidate.coverage.plot_nodes_total
        validator = ChapterIRValidator(registry=build_planning_state_registry(plan))
        for ir in candidate.chapter_irs:
            report = validator.validate(ir)
            assert report.state_findings == [], (name, report.state_findings)
        outlines = project_detailed_outline(candidate, plan, revision_id="PREV_CG")
        assert outlines and outlines[0].location_ids
        assert {item.field_name for item in outlines[0].fields} >= {"decision", "turn"}


def _spine_payload(plan) -> dict:
    payload = plan.model_dump(mode="json")
    location_id = plan.locations[0].location_id if plan.locations else ""
    participant_id = plan.characters[0].character_id if plan.characters else ""
    nodes = []
    edges = []
    for index in range(10):
        node_id = f"NODE_E2E_{index:02d}"
        nodes.append({
            "node_id": node_id, "purpose": f"第 {index} 步：推进主线",
            "conflict": f"阻碍 {index}", "state_change": f"状态推进 {index}",
            "location_id": location_id,
            "participants": [participant_id] if participant_id else [],
            "importance": "core" if index % 3 == 0 else "major",
            "must_happen": index % 4 == 0,
            "payoff": f"回报 {index}" if index % 5 == 4 else "",
            "cost": f"代价 {index}" if index % 3 == 1 else "",
            "major_choice": f"抉择 {index}" if index == 5 else "",
            "prerequisites": [] if index == 0 else [f"NODE_E2E_{index - 1:02d}"],
            "provenance": "generated"})
        if index:
            edges.append({"from_node_id": f"NODE_E2E_{index - 1:02d}", "to_node_id": node_id,
                          "relation": "causes"})
    payload["plot_nodes"] = nodes
    payload["spine"] = {"spine_id": "SPINE_E2E", "novel_id": plan.novel_id,
                        "nodes": [item["node_id"] for item in nodes], "edges": edges,
                        "entry_node_ids": ["NODE_E2E_00"], "terminal_node_ids": ["NODE_E2E_09"],
                        "provenance": "generated"}
    if location_id:
        payload["location_graph"] = {
            "graph_id": "LOCGRAPH_E2E", "location_ids": [location_id], "edges": [],
            "provenance": "generated"}
    payload["conflict_chains"] = [{
        "conflict_id": "CONFLICT_E2E", "title": "主线冲突",
        "related_node_ids": ["NODE_E2E_00", "NODE_E2E_05"],
        "stages": [
            {"stage_id": "CSTAGE_E2E_A", "conflict_id": "CONFLICT_E2E", "scope": "macro",
             "trigger_node_id": "NODE_E2E_00", "stakes": "全局压力", "provenance": "generated"},
            {"stage_id": "CSTAGE_E2E_B", "conflict_id": "CONFLICT_E2E", "scope": "volume",
             "trigger_node_id": "NODE_E2E_05", "constraint_change": "约束加码",
             "provenance": "generated"}],
        "provenance": "generated"}]
    return payload


def test_new_novel_e2e_from_one_sentence_to_detailed_outline(tmp_path: Path) -> None:
    """一句话 concept → NOVEL_SPEC → Planning IR → PlotNode/Spine → Volume/Arc → Chapter
    Semantic IR → Detailed Chapter Outline（deterministic，不调用 LLM / 不写正文）。"""

    spec = NovelSpec(
        spec_id="SPEC_E2E", novel_id="demo_e2e",
        logline="一个修理工想把断掉的桥重新接上，并查出桥为什么塌。",
        tone="克制", pace_strategy="压力前置",
        characters_seed=[{"seed_id": "lin", "display_name": "林工", "role": "主角",
                          "entity_ref": "ENTITY_PROTAGONIST", "external_goal": "让桥通车",
                          "internal_need": "被信任", "fear": "再塌一次"}],
        world_seed=[{"seed_id": "bridge", "statement": "桥的承重有上限",
                     "rule_type": "hard_rule"}],
        locations_seed=[{"seed_id": "bridge_loc", "display_name": "断桥",
                         "story_function": "主线舞台"}])
    compiler = NovelSpecCompiler(novel_id="demo_e2e", known_entity_ids=["ENTITY_PROTAGONIST"])
    result = compiler.compile(spec)
    assert result.validation_ok is True and result.plan is not None
    repo = PlanningRepository(tmp_path, "demo_e2e")
    base = repo.create(result.plan, revision_id="PREV_E2E_SPEC")
    # PlotNode / StorySpine（deterministic；等价于 M6 static provider 的产物）
    plan = validate_planning_ir(_spine_payload(result.plan))
    spine_revision = repo.create(plan, revision_id="PREV_E2E_SPINE")
    assert spine_revision.parent_revision_id == base.revision_id
    # Volume / Arc（M8B batch compiler）
    outline = OutlineBatchCompiler(repo)
    outline_session = outline.create_session(
        scope=CompilationScope(kind="full_book"),
        promotion_policy=PromotionPolicy(mode="safe_auto"))
    outline_done = outline.run_session(outline_session.session_id)
    assert outline_done.status == "promoted"
    arc_plan = repo.load(outline_done.final_revision_id).plan
    assert arc_plan.volumes and arc_plan.arcs
    # Chapter Semantic IR（M9 batch compiler：一个 Arc 一批）
    chapters = ArcChapterBatchCompiler(repo)
    chapter_session = chapters.create_session(
        promotion_policy=PromotionPolicy(mode="safe_auto"))
    chapter_done = chapters.run_session(chapter_session.session_id)
    assert chapter_done.status == "promoted", chapter_done.validation_summary
    final = repo.load(chapter_done.final_revision_id)
    assert all(arc.detail_level == "chapter_ready" for arc in final.plan.arcs)
    total_chapters = sum(len(arc.chapter_refs) for arc in final.plan.arcs)
    assert total_chapters >= len(final.plan.arcs)
    # Detailed Chapter Outline（writer-visible projection，不是 prose）
    first_arc = final.plan.arcs[0]
    document = chapters.chapter_store.load_arc_in_lineage(
        repo, chapter_done.final_revision_id, first_arc.arc_id)
    assert document is not None and document.planning_revision_id
    assert document.chapter_ir_digest == first_arc.chapter_ir_digest
    checklist = {task.batch_id: chapters.chapter_store.staged_candidate(
        chapters.store.load_checkpoint(chapter_session.session_id, task.batch_id).candidate_id)
        for task in chapter_done.tasks}
    first_candidate = next(item for item in checklist.values() if item is not None
                           and item.arc_id == first_arc.arc_id)
    outlines = project_detailed_outline(first_candidate, final.plan,
                                        revision_id=chapter_done.final_revision_id)
    assert outlines and outlines[0].goal and outlines[0].events
    assert all(len(item.text) <= 400 for outline in outlines for item in outline.fields)
    assert "prose" not in json.dumps([item.model_dump(mode="json") for item in outlines])
    # Context：M9 purpose 只给当前 Arc
    context = StoryPlanningContextBuilder(final.plan,
                                          revision_id=chapter_done.final_revision_id).build(
        "chapter_review", ids=[first_arc.arc_id])
    assert context.payload["scope"]["arc_ids"] == [first_arc.arc_id]
    assert len(context.payload["plot_nodes"]) == len(first_arc.plot_nodes)


def test_m9_modules_have_no_genre_or_fixed_count_hardcoding() -> None:
    offenders: list[str] = []
    for name in ("chapter_units.py", "chapter_compiler.py", "chapter_ir_store.py",
                 "chapter_projection.py", "chapter_batch.py"):
        text = (CHAPTER_DIR / name).read_text(encoding="utf-8")
        for term in ("wasteland", "WASTELAND", "废土", "xianxia", "修仙", "爽文",
                     "BEAT_LADDER", "if genre ==", "ChapterPlanV2", "ChapterBlueprint2"):
            if term in text:
                offenders.append(f"{name}: {term}")
    assert offenders == []


def _route_node(node_id: str, anchor: str, location_id: str, participant: str) -> dict:
    return {"node_id": node_id, "purpose": f"{node_id} 的用途", "conflict": "路线分歧",
            "state_change": f"{node_id} 的状态推进", "cost": "路线代价",
            "payoff": f"{node_id} 的回报", "pressure_kinds": ["custom"],
            "location_id": location_id, "participants": [participant],
            "importance": "major", "prerequisites": [anchor]}


def test_full_route_e2e_concept_spec_m6_m7_m8_m9(tmp_path: Path) -> None:
    """一句话 → Spec → Planning → M6 候选 promote → StorySpine → M7 路线比较 + 作者 approve
    → 新 immutable revision → M8 Volume/Arc → M9 Chapter IR → Detailed Outline。"""

    spec = NovelSpec(
        spec_id="SPEC_ROUTE", novel_id="demo_route",
        logline="桥塌之后，修理工必须在两条路里选一条。", tone="克制",
        characters_seed=[{"seed_id": "lin", "display_name": "林工", "role": "主角",
                          "entity_ref": "ENTITY_PROTAGONIST", "external_goal": "让桥通车",
                          "internal_need": "被信任", "fear": "再塌一次"}],
        world_seed=[{"seed_id": "load", "statement": "桥的承重有上限",
                     "rule_type": "hard_rule"}],
        locations_seed=[{"seed_id": "bridge_loc", "display_name": "断桥",
                         "story_function": "主线舞台"}])
    result = NovelSpecCompiler(novel_id="demo_route",
                              known_entity_ids=["ENTITY_PROTAGONIST"]).compile(spec)
    repo = PlanningRepository(tmp_path, "demo_route")
    spec_revision = repo.create(result.plan, revision_id="PREV_ROUTE_R1")
    spine_plan = validate_planning_ir(_spine_payload(result.plan))
    spine_revision = repo.create(spine_plan, revision_id="PREV_ROUTE_R2")
    assert spine_revision.parent_revision_id == spec_revision.revision_id
    anchor_node = "NODE_E2E_05"
    participant = spine_plan.characters[0].character_id
    # ---- M6：pressure → PlotNodeCandidate → validate → explicit promote（候选本身不写 truth）
    m6_candidate_payload = {
        "candidate_id": "CAND_M6_CRISIS",
        "proposed_node": {"node_id": "NODE_M6_CRISIS", "purpose": "材料断供",
                          "conflict": "断供", "state_change": "现金流见底",
                          "cost": "谈判成本", "payoff": "独立标准",
                          "pressure_kinds": ["resource_deficit"],
                          "location_id": result.plan.locations[0].location_id,
                          "participants": [participant], "importance": "major",
                          "prerequisites": [anchor_node]},
        "proposed_edges": [{"from_node_id": anchor_node, "to_node_id": "NODE_M6_CRISIS",
                            "relation": "causes"}],
        "reasoning_summary": "把资源缺口变成剧情压力"}
    proposal = propose_candidates(spine_plan, StaticPlotCandidateProvider([m6_candidate_payload]),
                                  revision_id=spine_revision.revision_id)
    m6_candidate = proposal.candidates[0]
    assert m6_candidate.approved is False
    assert len(repo.list_revisions()) == 2                 # candidate ≠ truth
    m6_candidate.approved = True
    m6_revision = promote_candidate(repo, spine_revision.revision_id, m6_candidate,
                                    revision_id="PREV_ROUTE_R3")
    assert m6_revision.parent_revision_id == spine_revision.revision_id
    assert "NODE_M6_CRISIS" in {node.node_id for node in m6_revision.plan.plot_nodes}
    # ---- M7：两个 route candidate → deterministic comparison → 作者 approve A → promote
    service = PlanningRouteLabService(repo)
    provider = StaticRouteCandidateProvider([
        {"candidate_id": "CAND_ROUTE_A", "title": "加固旧桥", "scope": "spine_segment",
         "patch": {"add_nodes": [_route_node("NODE_ROUTE_A", anchor_node,
                                             result.plan.locations[0].location_id,
                                             participant)],
                   "add_edges": [{"from_node_id": anchor_node, "to_node_id": "NODE_ROUTE_A",
                                  "relation": "causes"}]}},
        {"candidate_id": "CAND_ROUTE_B", "title": "绕行改道", "scope": "spine_segment",
         "patch": {"add_nodes": [_route_node("NODE_ROUTE_B", anchor_node,
                                             result.plan.locations[0].location_id,
                                             participant)],
                   "add_edges": [{"from_node_id": anchor_node, "to_node_id": "NODE_ROUTE_B",
                                  "relation": "causes"}]}}])
    raw = provider.propose({}, source_revision=m6_revision.revision_id,
                           source_digest=m6_revision.content_digest)
    stored = [service.add_candidate(item) for item in raw]
    assert all(item.non_authoritative is True for item in stored)
    assert len(repo.list_revisions()) == 3                 # route candidate ≠ truth
    comparison = service.compare([item.candidate_id for item in stored])
    assert comparison is not None
    route_revision = service.promote("CAND_ROUTE_A", approved=True,
                                     revision_id="PREV_ROUTE_R4",
                                     author_confirmation_ref="AUTHOR_APPROVED_A")
    assert route_revision.parent_revision_id == m6_revision.revision_id
    routed_plan = repo.load(route_revision.revision_id).plan
    routed_nodes = {node.node_id for node in routed_plan.plot_nodes}
    assert "NODE_ROUTE_A" in routed_nodes
    assert "NODE_ROUTE_B" not in routed_nodes              # 未选候选没有进入正式 revision
    assert repo.load(m6_revision.revision_id).content_digest == m6_revision.content_digest
    # ---- M8A/M8B：Volume / Arc
    outline = OutlineBatchCompiler(repo)
    outline_session = outline.create_session(
        scope=CompilationScope(kind="full_book"),
        promotion_policy=PromotionPolicy(mode="safe_auto"))
    outline_done = outline.run_session(outline_session.session_id)
    assert outline_done.status == "promoted"
    # ---- M9：Arc → Chapter Semantic IR → Detailed Outline
    chapters = ArcChapterBatchCompiler(repo)
    chapter_session = chapters.create_session(
        promotion_policy=PromotionPolicy(mode="safe_auto"))
    chapter_done = chapters.run_session(chapter_session.session_id)
    assert chapter_done.status == "promoted", chapter_done.validation_summary
    final_plan = repo.load(chapter_done.final_revision_id).plan
    route_arcs = [arc for arc in final_plan.arcs if "NODE_ROUTE_A" in arc.plot_nodes]
    assert route_arcs and all(arc.detail_level == "chapter_ready" for arc in route_arcs)
    # route provenance 追到 Volume / Arc / Chapter
    assert route_arcs[0].volume_id in {volume.volume_id for volume in final_plan.volumes}
    assert route_arcs[0].chapter_refs
    candidate = chapters.chapter_store.staged_candidate(
        chapters.store.load_checkpoint(chapter_session.session_id,
                                       next(task.batch_id for task in chapter_done.tasks
                                            if task.scope.note == route_arcs[0].arc_id)
                                       ).candidate_id)
    assert candidate is not None
    assert any("NODE_ROUTE_A" in ir.source_refs for ir in candidate.chapter_irs)
    outline_rows = project_detailed_outline(candidate, final_plan,
                                            revision_id=chapter_done.final_revision_id)
    assert any("NODE_ROUTE_A" in row.source_refs for row in outline_rows)
    assert all(len(item.text) <= 400 for row in outline_rows for item in row.fields)
    # Canon / StoryState 未被写：只创建了 planning 目录
    story_engine_root = tmp_path / "novel" / "authoring" / "story_engine"
    assert not (story_engine_root / "canon").exists()
    assert not (story_engine_root / "state").exists()
