"""M9：ArcPlan → Chapter Semantic IR → Detailed Chapter Outline 回归。"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from novelforge.story_engine.chapter_ir.models import ChapterSemanticIR
from novelforge.story_engine.chapter_ir.function_policy import FUNCTION_REQUIREMENTS
from novelforge.story_engine.chapter_ir.validator import ChapterIRValidator
from novelforge.story_engine.planning import (
    ArcChapterBatchCompiler,
    ChapterDecompositionPolicy,
    ChapterCompilationProfile,
    ChapterCompiler,
    ChapterIRStore,
    CompilationScope,
    OutlineBatchCompiler,
    PlanningRepository,
    PromotionPolicy,
    StoryPlanningContextBuilder,
    build_planning_state_registry,
    chapter_ir_digest,
    plan_arc_batch_scopes,
    project_arc_pacing,
    project_chapter_ir,
    project_chapter_tree,
    project_compilation_progress,
    project_detailed_outline,
    project_writer_context,
    promote_chapter_candidate,
    stable_chapter_id,
    validate_planning_ir,
)

sys.path.insert(0, str(Path(__file__).parent))
from test_story_planning_outline_batch import _long_book_raw  # noqa: E402

FIXTURES = Path("tests/fixtures/planning_ir")
CHAPTER_DIR = Path("src/novelforge/story_engine/planning")


def _single_arc_raw(per_volume: int = 12, budget: int = 10) -> dict:
    """把合成长书的 1 卷压成一个包含全部 signal 域的 Arc（M9 long-arc fixture）。"""

    raw = _long_book_raw(volume_count=1, per_volume=per_volume)
    node_ids = [f"NODE_V00_{index:02d}" for index in range(per_volume)]
    for node in raw["plot_nodes"]:
        node["scheduled_volume_id"] = "VOL_M9"
    # 制造一次有叙事功能的地点转移（后半段在另一个区域 + 目标区域有伏笔动作）
    raw["locations"].append({"location_id": "LOC_V01", "display_name": "外圈",
                             "provenance": "supplied"})
    raw["location_graph"]["location_ids"].append("LOC_V01")
    raw["location_graph"]["edges"].append({
        "from_location_id": "LOC_V00", "to_location_id": "LOC_V01",
        "route": "外圈通道", "provenance": "generated"})
    for node in raw["plot_nodes"]:
        if int(node["node_id"].rsplit("_", 1)[-1]) >= per_volume // 2:
            node["location_id"] = "LOC_V01"
    raw["map_expansions"][0]["milestones"].append({
        "milestone_id": "MAPMILE_OUTER_KNOWN", "location_ref": "LOC_V01",
        "from_stage": "unknown", "to_stage": "known",
        "trigger_node_id": node_ids[per_volume // 2], "provenance": "generated"})
    raw["volumes"] = [{
        "volume_id": "VOL_M9", "index": 1, "title": "第一卷 完整信号",
        "volume_goal": "跑完一条完整的 Arc 结构", "opening_state": "起点",
        "major_conflict": "资源与立场", "location_expansion": ["LOC_V00"],
        "major_nodes": node_ids, "climax_node_id": node_ids[-1],
        "ending_state": "完成目标并付出代价", "detail_level": "arc",
        "chapter_budget": budget, "arc_ids": ["ARC_M9"], "provenance": "supplied"}]
    raw["arcs"] = [{
        "arc_id": "ARC_M9", "volume_id": "VOL_M9", "index": 1, "detail_level": "arc",
        "title": "完整结构", "arc_goal": "跑完一条完整的 Arc 结构",
        "opening_state": "起点", "participants": ["CHAR_0", "CHAR_1"],
        "location_scope": ["LOC_V00", "LOC_V01"], "conflict": "资源与立场",
        "decision_chain": [
            {"node_id": "NODE_V00_05", "decision_owner_ref": "ENTITY_PROTAGONIST",
             "choice": "选择承担", "consequence": "路径改变", "provenance": "supplied"}],
        "turns": ["材料问题变成责任问题"], "payoff": "完成目标",
        "cost": "付出代价", "ending_state": "完成目标并付出代价",
        "plot_nodes": node_ids, "chapter_budget": budget, "provenance": "generated"}]
    return raw


def _plan(per_volume: int = 12, budget: int = 10):
    return validate_planning_ir(_single_arc_raw(per_volume=per_volume, budget=budget))


def _repo(tmp_path: Path, plan, revision_id: str = "PREV_M9_1"):
    repo = PlanningRepository(tmp_path, plan.novel_id)
    repo.create(plan, revision_id=revision_id)
    return repo


# ---------------------------------------------------------------- semantic split（no beat ladder）
def test_band_only_caps_capacity_and_never_invents_semantics() -> None:
    """complexity band 只提供展开空间；没有信号就不准生成 setup / escalation / choice。"""

    from novelforge.story_engine.planning.chapter_units import _slots
    from novelforge.story_engine.planning.models import PlotNode

    bare = PlotNode(node_id="NODE_BARE_01", purpose="普通节点")
    empty = {"decision_refs": [], "conflict_refs": [], "information_refs": [],
             "foreshadow_refs": [], "relationship_refs": [], "faction_refs": [],
             "progression_refs": [], "resource_refs": [], "equipment_refs": [],
             "map_refs": [], "reward_refs": [], "autonomous_refs": []}
    for band in ("micro", "medium", "large", "set_piece"):
        assert _slots(bare, empty, band) == ["execution"], band
    # 只有 state change 的大节点：允许一个 consequence，但不得凭空多出 setup/escalation/choice
    with_state = bare.model_copy(update={"state_change": "状态推进"})
    assert _slots(with_state, empty, "set_piece") == ["consequence"]
    assert _slots(with_state, empty, "large") == ["consequence"]
    # 有 major choice 才有 choice；band 只决定还能多展开几个 setup/escalation
    with_choice = bare.model_copy(update={"major_choice": "做出选择"})
    assert _slots(with_choice, empty, "micro") == ["choice"]


def test_semantic_units_are_backed_by_real_signals() -> None:
    plan = _plan()
    candidate = ChapterCompiler().compile(plan, revision_id="PREV_M9_1", arc_id="ARC_M9")
    nodes = {node.node_id: node for node in plan.plot_nodes}
    order = [node.node_id for node in plan.plot_nodes]
    previous_location: dict[str, str] = {}
    for index, node_id in enumerate(order):
        previous_location[node_id] = order[index - 1] if index else ""
    for unit in candidate.decomposition.chapter_units:
        node = nodes[unit.primary_plot_node_id]
        if unit.unit_kind == "choice":
            assert node.major_choice or unit.decision_refs, unit.unit_id
        elif unit.unit_kind == "consequence":
            assert node.payoff or node.cost or node.state_change or unit.reward_refs \
                or unit.progression_refs, unit.unit_id
        elif unit.unit_kind == "setup":
            predecessor = nodes.get(previous_location.get(node.node_id, ""))
            moved = bool(predecessor is not None and predecessor.location_id
                         and node.location_id
                         and predecessor.location_id != node.location_id)
            assert node.prerequisites or moved \
                or (node.requirements and node.requirements.requirements) \
                or unit.information_refs or unit.foreshadow_refs or unit.resource_refs \
                or unit.equipment_refs, unit.unit_id
        elif unit.unit_kind == "escalation":
            assert unit.conflict_refs or unit.faction_refs or unit.autonomous_refs \
                or unit.pressure_refs, unit.unit_id
        elif unit.unit_kind == "execution":
            assert not any(node.major_choice or node.payoff or node.cost
                           or node.information_move_refs or node.foreshadow_move_refs
                           or node.conflict_chain_ref for _ in [0]), unit.unit_id
    # 两个独立 decision/payoff 允许自然拆成多章（不是"每节点一章"）
    choices = [allocation for allocation in candidate.chapter_allocations
               if allocation.chapter_function in ("conflict", "climax", "negotiation")]
    assert len(candidate.chapter_irs) > len({unit.primary_plot_node_id
                                             for unit in candidate.decomposition.chapter_units})
    assert len(candidate.chapter_irs) >= 8 and choices is not None


def test_stable_ids_survive_prepending_a_new_semantic_unit() -> None:
    """在 Arc 前部插入新 unit 后，既有 chapter 不应因为 order shift 被洗 ID。"""

    plan = _plan()
    before = ChapterCompiler().compile(plan, revision_id="PREV_M9_1", arc_id="ARC_M9")
    before_ids = {ir.chapter_uuid for ir in before.chapter_irs}
    payload = plan.model_dump(mode="json")
    new_node_id = "NODE_V00_98"
    payload["plot_nodes"].insert(0, {
        "node_id": new_node_id, "purpose": "新插入的前置节点", "conflict": "插入的阻碍",
        "state_change": "插入的推进", "location_id": "LOC_V00",
        "participants": ["CHAR_0"], "importance": "minor", "optional": True,
        "scheduled_volume_id": "VOL_M9", "provenance": "generated"})
    payload["spine"]["nodes"].insert(0, new_node_id)
    payload["spine"]["edges"].insert(0, {"from_node_id": new_node_id,
                                         "to_node_id": "NODE_V00_00", "relation": "causes"})
    payload["volumes"][0]["major_nodes"].insert(0, new_node_id)
    payload["arcs"][0]["plot_nodes"].insert(0, new_node_id)
    for node in payload["plot_nodes"]:
        if node["node_id"] == "NODE_V00_00":
            node["prerequisites"] = [new_node_id]
    edited = validate_planning_ir(payload)
    after = ChapterCompiler().compile(edited, revision_id="PREV_M9_1", arc_id="ARC_M9")
    after_ids = {ir.chapter_uuid for ir in after.chapter_irs}
    assert before_ids <= after_ids, sorted(before_ids - after_ids)
    assert len(after.chapter_irs) > len(before.chapter_irs)
    assert after.decomposition.proposed_chapter_count == len(after.chapter_irs)


# ---------------------------------------------------------------- decomposition
def test_long_arc_decomposition_is_semantic_not_budget_quota() -> None:
    plan = _plan()
    arc = plan.arcs[0]
    compiler = ChapterCompiler()
    first = compiler.compile(plan, revision_id="PREV_M9_1", arc_id=arc.arc_id)
    assert len(first.chapter_irs) >= 8
    assert first.decomposition.proposed_chapter_count == len(first.chapter_irs)
    assert len(first.decomposition.chapter_units) >= len(first.chapter_irs)
    cheap = compiler.compile(plan, revision_id="PREV_M9_1", arc_id=arc.arc_id,
                             budget=first.decomposition.budget_range.model_copy(
                                 update={"preferred": 4}))
    assert len(cheap.chapter_irs) == len(first.chapter_irs)   # preferred 不是 quota
    assert not any(item.severity == "ERROR" for item in first.validation_findings)
    coverage = first.coverage
    assert coverage.plot_nodes_anchored == coverage.plot_nodes_total
    assert coverage.must_happen_unanchored == []
    assert coverage.plot_nodes_duplicated == []
    assert coverage.goal_anchored is True
    assert coverage.knowledge_gate_pass is True
    completions = [node_id for allocation in first.chapter_allocations
                   for node_id in allocation.completed_plot_node_ids]
    assert len(completions) == len(set(completions))


def test_chapters_use_existing_chapter_semantic_ir_only() -> None:
    plan = _plan()
    candidate = ChapterCompiler().compile(plan, revision_id="PREV_M9_1",
                                          arc_id=plan.arcs[0].arc_id)
    registry = build_planning_state_registry(plan)
    validator = ChapterIRValidator(registry=registry)
    compiler = ChapterCompiler()
    required_ok = True
    for ir in candidate.chapter_irs:
        assert isinstance(ir, ChapterSemanticIR)
        report = validator.validate(ir)
        assert set(report.codes()) <= {"FIELD_WITHOUT_EVIDENCE"}, report.codes()
        assert report.state_findings == []
        function = next(item.chapter_function for item in candidate.chapter_allocations
                       if item.chapter_id == ir.chapter_uuid)
        requirements = FUNCTION_REQUIREMENTS[function]
        bound = {item.field_name for item in ir.field_evidence}
        required = {name for name, level in requirements.items() if level == "required"}
        if function == "setup":
            required = set()
        if not required <= bound:
            required_ok = False
    assert required_ok, "ChapterFunctionPolicy 要求的字段必须有 evidence"
    assert not [item for item in compiler.validate(plan, candidate)
                if item.severity == "ERROR"]
    assert all(ir.arc_id == plan.arcs[0].arc_id for ir in candidate.chapter_irs)
    assert all(ir.provenance == "planner" for ir in candidate.chapter_irs)
    # 没有第二套 chapter 模型
    assert not hasattr(ChapterCompiler, "ChapterPlanV2")
    payload = candidate.model_dump(mode="json")
    assert "ChapterPlanV2" not in json.dumps(payload)


def test_chapter_ids_are_stable_across_recompiles() -> None:
    plan = _plan()
    compiler = ChapterCompiler()
    first = compiler.compile(plan, revision_id="PREV_M9_1", arc_id="ARC_M9")
    second = compiler.compile(plan, revision_id="PREV_M9_1", arc_id="ARC_M9")
    assert [ir.chapter_uuid for ir in first.chapter_irs] \
        == [ir.chapter_uuid for ir in second.chapter_irs]
    assert chapter_ir_digest(first.chapter_irs) == chapter_ir_digest(second.chapter_irs)
    assert first.candidate_id == second.candidate_id
    assert all(item.chapter_uuid.startswith("CHIR_") for item in first.chapter_irs)
    assert stable_chapter_id("ARC_M9", first.decomposition.chapter_units[0]) \
        == first.chapter_irs[0].chapter_uuid


def test_knowledge_gates_catch_leaks_and_early_reveals() -> None:
    plan = _plan()
    compiler = ChapterCompiler()
    candidate = compiler.compile(plan, revision_id="PREV_M9_1", arc_id="ARC_M9")
    assert candidate.coverage.knowledge_gate_pass is True
    release_chapter = next(item for item in candidate.chapter_allocations
                           if item.reader_release)
    leaked = candidate.model_copy(update={
        "chapter_allocations": [
            allocation.model_copy(update={
                "reader_release": list(allocation.reader_release) + ["TRUTH_00_0"]})
            if allocation.chapter_id == candidate.chapter_allocations[0].chapter_id
            and not allocation.reader_release else allocation
            for allocation in candidate.chapter_allocations]})
    findings = compiler.validate(plan, leaked)
    assert "READER_REVEAL_TOO_EARLY" in {item.code for item in findings}
    assert release_chapter.reader_release  # 生成时确实有合法揭示


def test_bridge_chapter_requires_narrative_function() -> None:
    plan = _plan()
    candidate = ChapterCompiler().compile(plan, revision_id="PREV_M9_1", arc_id="ARC_M9")
    bridges = [allocation for allocation in candidate.chapter_allocations
               if allocation.is_bridge]
    assert bridges, "跨地点且带叙事功能的节点应该产生 bridge chapter"
    for allocation in bridges:
        assert allocation.chapter_function in ("transition", "exploration")
        assert "BRIDGE_WITHOUT_NARRATIVE_FUNCTION" not in {
            item.code for item in candidate.validation_findings}


# ---------------------------------------------------------------- promotion
def test_candidate_cannot_write_repository_without_approval(tmp_path: Path) -> None:
    plan = _plan()
    repo = _repo(tmp_path, plan)
    store = ChapterIRStore(tmp_path, plan.novel_id)
    candidate = ChapterCompiler().compile(plan, revision_id="PREV_M9_1", arc_id="ARC_M9")
    with pytest.raises(ValueError):
        promote_chapter_candidate(repo, store, candidate)
    assert len(repo.list_revisions()) == 1
    compilation, record = promote_chapter_candidate(repo, store, candidate, approved=True,
                                                    revision_id="PREV_M9_2")
    assert record.parent_revision_id == "PREV_M9_1"
    assert compilation.chapter_ids == [ir.chapter_uuid for ir in candidate.chapter_irs]
    arc = [item for item in record.plan.arcs if item.arc_id == "ARC_M9"][0]
    assert arc.detail_level == "chapter_ready"
    assert arc.chapter_refs == compilation.chapter_ids
    assert arc.chapter_ir_digest == chapter_ir_digest(candidate.chapter_irs)
    assert repo.load("PREV_M9_1").plan.arcs[0].detail_level == "arc"   # 旧 revision 不变
    integrity = store.verify(repo, "PREV_M9_2")
    assert integrity.ok is True and integrity.missing_arc_ids == []


def test_artifact_repair_restores_missing_official_document(tmp_path: Path) -> None:
    plan = _plan()
    repo = _repo(tmp_path, plan)
    store = ChapterIRStore(tmp_path, plan.novel_id)
    candidate = ChapterCompiler().compile(plan, revision_id="PREV_M9_1", arc_id="ARC_M9")
    _, record = promote_chapter_candidate(repo, store, candidate, approved=True,
                                          revision_id="PREV_M9_2")
    store.arc_path(record.revision_id, "ARC_M9").unlink()      # 模拟 official 文档丢失
    broken = store.verify(repo, record.revision_id)
    assert broken.ok is False and broken.missing_arc_ids == ["ARC_M9"]
    repaired = store.repair(repo, record.revision_id)
    assert repaired.repaired_arc_ids == ["ARC_M9"]
    assert repaired.ok is True
    assert len(repo.list_revisions()) == 2                     # 不新建 revision


def test_detailed_outline_and_writer_context(tmp_path: Path) -> None:
    plan = _plan()
    repo = _repo(tmp_path, plan)
    candidate = ChapterCompiler().compile(plan, revision_id="PREV_M9_1", arc_id="ARC_M9")
    outlines = project_detailed_outline(candidate, plan, revision_id="PREV_M9_1")
    assert len(outlines) == len(candidate.chapter_irs)
    first = outlines[0]
    assert first.chapter_id and first.display_number >= 1 and first.chapter_function
    assert first.location_ids and first.participants
    names = {item.field_name for item in first.fields}
    assert {"decision", "turn", "payoff", "world_state_change"} <= names
    assert first.read_only is True and first.non_authoritative is True
    assert not hasattr(first, "save")
    context = project_writer_context(candidate, plan, revision_id="PREV_M9_1")
    assert context.chapter_ids == [item.chapter_id for item in outlines]
    assert context.read_only is True
    assert context.knowledge_boundaries          # 谁知道哪些 truth（chapter 级推演）
    assert isinstance(context.forbidden_reveals, list)
    inspector = project_chapter_ir(candidate.chapter_irs[0],
                                   candidate.validation_findings,
                                   candidate.chapter_allocations[0])
    assert inspector.read_only is True and inspector.event_ids
    pacing = project_arc_pacing(candidate)
    assert set(pacing.values) == set(pacing.dimensions)
    assert all(len(values) == len(candidate.chapter_irs)
               for values in pacing.values.values())


def test_chapter_context_purposes_scope_to_one_arc() -> None:
    plan = _plan()
    builder = StoryPlanningContextBuilder(plan, revision_id="PREV_M9_1")
    for purpose in ("chapter_compile", "chapter_review", "chapter_resume"):
        context = builder.build(purpose, ids=["ARC_M9"])
        assert {"scope", "arcs", "plot_nodes", "information_arcs",
                "pressure_carryover"} <= set(context.payload)
        assert context.payload["scope"]["arc_ids"] == ["ARC_M9"]
        assert context.boundary == "planning_future_not_happened"


# ---------------------------------------------------------------- batch / resume
def _m8b_ready_repo(tmp_path: Path, volume_count: int = 3, per_volume: int = 10):
    plan = validate_planning_ir(_long_book_raw(volume_count=volume_count,
                                               per_volume=per_volume))
    repo = PlanningRepository(tmp_path, plan.novel_id)
    repo.create(plan, revision_id="PREV_M9_B0")
    outline = OutlineBatchCompiler(repo)
    session = outline.create_session(scope=CompilationScope(kind="full_book"),
                                     promotion_policy=PromotionPolicy(mode="safe_auto"))
    done = outline.run_session(session.session_id)
    assert done.status == "promoted"
    return repo, done.final_revision_id


def test_arc_batch_promotes_each_arc_and_survives_crash(tmp_path: Path) -> None:
    repo, head = _m8b_ready_repo(tmp_path)
    plan = repo.load(head).plan
    assert len(plan.arcs) >= 3
    compiler = ArcChapterBatchCompiler(repo)
    session = compiler.create_session(promotion_policy=PromotionPolicy(mode="safe_auto"),
                                      session_id="CHBATCH_CRASH")
    assert [task.scope.note for task in session.tasks] == [arc.arc_id for arc in plan.arcs]
    assert all(task.target_detail_level == "chapter_ready" for task in session.tasks)
    compiler.run_batch("CHBATCH_CRASH", "BATCH_001")
    snapshot = compiler.store.load_session("CHBATCH_CRASH")
    task_two, checkpoint_two = compiler.run_batch("CHBATCH_CRASH", "BATCH_002")
    assert task_two.status == "promoted"
    compiler.store.save_session(snapshot)                    # 模拟 session 未写就崩溃
    compiler.store.path("CHBATCH_CRASH", "checkpoint_BATCH_002.json").unlink()
    revisions = len(repo.list_revisions())
    repaired = compiler.repair_session("CHBATCH_CRASH")
    assert repaired.current_revision_id == checkpoint_two.promoted_revision_id
    assert len(repo.list_revisions()) == revisions           # 不重复 promote
    final = compiler.resume_batch_session("CHBATCH_CRASH")
    assert final.status == "promoted" and final.scope_complete is True, \
        final.validation_summary
    assert final.validation_summary["checks"]["chapter_artifacts_bound"] is True
    assert final.validation_summary["checks"]["knowledge_gates_pass"] is True
    record = repo.load(final.final_revision_id)
    assert all(arc.detail_level == "chapter_ready" for arc in record.plan.arcs)
    chapter_ids = [chapter_id for arc in record.plan.arcs for chapter_id in arc.chapter_refs]
    assert len(chapter_ids) == len(set(chapter_ids))
    tree = project_chapter_tree(record.plan, revision_id=final.final_revision_id)
    assert tree.chapter_total == len(chapter_ids)
    progress = project_compilation_progress(
        final, candidates={task.batch_id: compiler.chapter_store.staged_candidate(
            compiler.store.load_checkpoint("CHBATCH_CRASH", task.batch_id).candidate_id)
            for task in final.tasks if task.status == "promoted"})
    assert progress.arcs_completed == progress.arcs_total == len(final.tasks)
    assert progress.chapters_planned == len(chapter_ids)


def test_recompile_one_arc_keeps_other_arc_chapter_ids(tmp_path: Path) -> None:
    repo, head = _m8b_ready_repo(tmp_path, volume_count=3, per_volume=10)
    compiler = ArcChapterBatchCompiler(repo)
    compiler.create_session(promotion_policy=PromotionPolicy(mode="safe_auto"),
                            session_id="CHBATCH_REC")
    final = compiler.run_session("CHBATCH_REC")
    record = repo.load(final.final_revision_id)
    first_arc, second_arc = record.plan.arcs[0], record.plan.arcs[1]
    before_first = list(first_arc.chapter_refs)
    before_second = list(second_arc.chapter_refs)
    # 只改 Arc 2 的一个 optional node：Arc 1 的 chapter ids 必须完全不变
    payload = record.plan.model_dump(mode="json")
    for node in payload["plot_nodes"]:
        if node["node_id"] == second_arc.plot_nodes[0]:
            node["optional"] = True
            node["must_happen"] = False
            node["payoff"] = "（重编后调整的回报）"
    edited = repo.create(validate_planning_ir(payload), revision_id="PREV_M9_EDIT")
    compiler2 = ArcChapterBatchCompiler(repo)
    compiler2.create_session(promotion_policy=PromotionPolicy(mode="safe_auto"),
                            session_id="CHBATCH_REC2", root_revision_id=edited.revision_id)
    compiler2.recompile_arc("CHBATCH_REC2", second_arc.arc_id)
    edited_final = compiler2.run_session("CHBATCH_REC2")
    assert edited_final.status == "promoted"
    updated = repo.load(edited_final.final_revision_id)
    assert [arc.chapter_refs for arc in updated.plan.arcs
            if arc.arc_id == first_arc.arc_id][0] == before_first
    changed_second = [arc for arc in updated.plan.arcs
                      if arc.arc_id == second_arc.arc_id][0]
    assert set(changed_second.chapter_refs) == set(before_second)   # anchor 匹配：ID 不洗牌
    assert changed_second.chapter_ir_digest != second_arc.chapter_ir_digest  # 内容确实变了


def test_arc_batch_human_review_on_impossible_budget(tmp_path: Path) -> None:
    """budget mismatch 的 severity 由 policy 决定，chapter decomposition 本身不变。"""

    repo, head = _m8b_ready_repo(tmp_path, volume_count=2, per_volume=10)
    plan = repo.load(head).plan
    arc = plan.arcs[0]
    default = ChapterCompiler()
    candidate_a = default.compile(plan, revision_id=head, arc_id=arc.arc_id)
    mismatches_a = {item.code: item.severity for item in candidate_a.validation_findings
                    if item.code in ("ARC_TOO_DENSE_FOR_CHAPTER_BUDGET",
                                     "ARC_TOO_THIN_FOR_CHAPTER_BUDGET")}
    assert set(mismatches_a.values()) <= {"WARNING"}          # 中性默认：只是 WARNING
    assert mismatches_a, "这个 fixture 的 Arc 结构本来就与 node estimate range 不匹配"
    strict_compiler = ChapterCompiler(profile=ChapterCompilationProfile(
        policy=ChapterDecompositionPolicy(dense_review_tolerance=0.0,
                                          thin_review_tolerance=0.0)))
    candidate_b = strict_compiler.compile(plan, revision_id=head, arc_id=arc.arc_id)
    # policy 只改 review severity：structure / chapter ids 完全一致
    assert [ir.chapter_uuid for ir in candidate_b.chapter_irs] \
        == [ir.chapter_uuid for ir in candidate_a.chapter_irs]
    assert len(candidate_b.decomposition.chapter_units) \
        == len(candidate_a.decomposition.chapter_units)
    codes_b = {item.code: item.severity for item in candidate_b.validation_findings
               if item.code in ("ARC_TOO_DENSE_FOR_CHAPTER_BUDGET",
                                "ARC_TOO_THIN_FOR_CHAPTER_BUDGET")}
    assert set(codes_b.values()) == {"ERROR"}
    # batch 层用严格 policy：会停下来找作者，而不是偷偷 promote
    strict = ArcChapterBatchCompiler(repo, profile=ChapterCompilationProfile(
        policy=ChapterDecompositionPolicy(dense_review_tolerance=0.0,
                                          thin_review_tolerance=0.0)))
    strict.create_session(promotion_policy=PromotionPolicy(mode="safe_auto"),
                          session_id="CHBATCH_POLICY_STRICT")
    revisions_before = len(repo.list_revisions())
    task_b, checkpoint_b = strict.run_batch("CHBATCH_POLICY_STRICT", "BATCH_001")
    assert task_b.scope.note == arc.arc_id
    assert task_b.status == "human_review"
    assert task_b.batch_id in strict.store.load_session(
        "CHBATCH_POLICY_STRICT").review_required_batch_ids
    assert len(repo.list_revisions()) == revisions_before       # review 时不写新结构
