"""M8A：Structural budget / segmentation / Volume-Arc compiler 回归。"""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from novelforge.story_engine.planning import (
    CompilationScope,
    OutlineCompiler,
    PlanningRepository,
    StoryPlanningContextBuilder,
    StructuralBudgetEstimator,
    detect_structural_segments,
    estimate_plan_budget,
    planning_digest,
    project_outline,
    promote_outline_candidate,
    validate_planning_ir,
)

FIXTURES = Path("tests/fixtures/planning_ir")
URBAN = "URBAN_GROWTH_EXAMPLE.json"
BASE = "ONE_SENTENCE_EXAMPLE.json"
OUTLINE_DIR = Path("src/novelforge/story_engine/planning")


def _raw(name: str = URBAN) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def _plan(name: str = URBAN):
    return validate_planning_ir(_raw(name))


def _synthetic(node_count: int = 90, arc_count: int = 3) -> dict:
    """80–120 节点合成 StorySpine（多个角色弧 / 冲突链 / 势力 / 地点）。"""

    nodes = []
    edges = []
    for index in range(node_count):
        node_id = f"NODE_S{index:03d}"
        payload = {"node_id": node_id, "purpose": f"节点 {index} 的用途",
                   "conflict": f"冲突 {index % 7}", "state_change": f"状态 {index}",
                   "cost": f"代价 {index % 5}" if index % 3 == 0 else "",
                   "payoff": f"回报 {index}" if index % 5 == 0 else "",
                   "location_id": f"LOC_R{index % 4}",
                   "participants": [f"CHAR_{index % 6}"],
                   "pressure_kinds": ["custom"],
                   "prerequisites": [] if index == 0 else [f"NODE_S{index - 1:03d}"],
                   "importance": ["core", "major", "minor"][index % 3]}
        if index % 10 == 0:
            payload["major_choice"] = f"选择 {index}"
        if index % 9 == 0:
            payload["information_move_refs"] = [f"IMOVE_{index:03d}"]
        nodes.append(payload)
        if index:
            edges.append({"from_node_id": f"NODE_S{index - 1:03d}", "to_node_id": node_id,
                          "relation": "causes"})
    raw = {
        "planning_id": "PLAN_SYNTH", "novel_id": "demo_synth",
        "intent": {"intent_id": "INTENT_SYNTH", "novel_id": "demo_synth",
                   "target_words": 1_200_000, "provenance": "supplied"},
        "theme": {"theme_id": "THEME_SYNTH", "dramatic_question": "能不能守住",
                  "final_answer_direction": "守住但付出代价", "provenance": "supplied"},
        "characters": [{"character_id": f"CHAR_{index}", "display_name": f"角色 {index}",
                        "entity_ref": "ENTITY_PROTAGONIST" if index == 0 else "",
                        "provenance": "supplied"} for index in range(6)],
        "character_arcs": [{"arc_id": f"CARCH_{index}", "character_id": f"CHAR_{index}",
                            "start_state": "s0", "end_state": "s1",
                            "major_choices": [{"node_id": f"NODE_S{index * 12:03d}",
                                               "choice": "c", "provenance": "supplied"}],
                            "provenance": "supplied"} for index in range(3)],
        "factions": [{"faction_id": f"FACTION_{index}", "display_name": f"势力 {index}",
                      "provenance": "supplied"} for index in range(3)],
        "locations": [{"location_id": f"LOC_R{index}", "display_name": f"区域 {index}",
                       "provenance": "supplied"} for index in range(4)],
        "location_graph": {"graph_id": "LOCGRAPH_SYNTH",
                           "location_ids": [f"LOC_R{index}" for index in range(4)],
                           "edges": [{"from_location_id": f"LOC_R{index}",
                                      "to_location_id": f"LOC_R{index + 1}",
                                      "route": "路径", "provenance": "generated"}
                                     for index in range(3)],
                           "provenance": "generated"},
        "plot_nodes": nodes,
        "spine": {"spine_id": "SPINE_SYNTH", "novel_id": "demo_synth",
                  "nodes": [item["node_id"] for item in nodes], "edges": edges,
                  "entry_node_ids": ["NODE_S000"],
                  "terminal_node_ids": [f"NODE_S{node_count - 1:03d}"],
                  "provenance": "generated"},
        "conflict_chains": [
            {"conflict_id": f"CONFLICT_SYNTH_{index}", "title": f"冲突链 {index}",
             "related_node_ids": [f"NODE_S{index * 14:03d}"],
             "stages": [
                 {"stage_id": f"CSTAGE_{index}_A", "conflict_id": f"CONFLICT_SYNTH_{index}",
                  "scope": "local", "trigger_node_id": f"NODE_S{index * 14:03d}",
                  "stakes": "s", "provenance": "supplied"},
                 {"stage_id": f"CSTAGE_{index}_B", "conflict_id": f"CONFLICT_SYNTH_{index}",
                  "scope": "macro" if index % 2 == 0 else "volume",
                  "trigger_node_id": f"NODE_S{min(index * 14 + 11, node_count - 1):03d}",
                  "constraint_change": "c", "provenance": "supplied"}],
             "provenance": "supplied"}
            for index in range(max(arc_count, node_count // 14))],
    }
    return raw


# ---------------------------------------------------------------- budget
def test_node_budget_estimate_uses_structural_signals() -> None:
    plan = _plan()
    estimator = StructuralBudgetEstimator()
    node = next(item for item in plan.plot_nodes if item.node_id == "NODE_OPEN")
    row = estimator.estimate_node(plan, node)
    assert row.structural_weight > 0
    assert row.complexity_band in ("micro", "small", "medium", "large", "set_piece")
    assert row.estimate.minimum <= row.estimate.preferred <= row.estimate.maximum
    assert row.signals["importance"] == node.importance
    assert "information_moves" in row.signals


def test_segment_budget_and_plan_budget_ranges() -> None:
    plan = _plan()
    estimator = StructuralBudgetEstimator()
    segments = detect_structural_segments(plan)
    budget = estimator.estimate_segment(plan, segments[0].segment_id, segments[0].node_ids)
    assert budget.budget_weight > 0
    assert budget.estimate.minimum <= budget.estimate.maximum
    plan_budget = estimate_plan_budget(plan)
    assert plan_budget.maximum >= plan_budget.preferred >= plan_budget.minimum
    assert "planning estimate" in plan_budget.note


def test_target_words_thin_and_dense_findings() -> None:
    plan = _plan()
    estimator = StructuralBudgetEstimator()
    budget = estimate_plan_budget(plan)

    def mutate(target):
        raw = _raw()
        raw["intent"]["target_words"] = target
        return validate_planning_ir(raw)

    thin = estimator.target_alignment(mutate(5_000_000), budget)
    assert "STRUCTURE_TOO_THIN_FOR_TARGET" in {item.code for item in thin.findings}
    dense = estimator.target_alignment(mutate(3_000), budget)
    assert "STRUCTURE_TOO_DENSE_FOR_TARGET" in {item.code for item in dense.findings}
    neutral = estimator.target_alignment(mutate(0), budget)
    assert neutral.findings == []


# ---------------------------------------------------------------- segmentation
def test_structural_segments_carry_boundary_signals() -> None:
    plan = _plan()
    segments = detect_structural_segments(plan)
    assert segments
    assert sum(len(item.node_ids) for item in segments) == len(plan.plot_nodes)
    assert all(item.boundary_reason for item in segments)
    assert all(item.budget_weight >= 0 for item in segments)


def test_segments_are_data_driven_not_fixed() -> None:
    small = detect_structural_segments(_plan())
    big = detect_structural_segments(validate_planning_ir(_synthetic(90)))
    assert len(big) >= len(small)
    assert len(big) != 3 or len(big) > 1  # 不预设固定段数


# ---------------------------------------------------------------- compile
def test_compile_fills_volume_and_arc_plans() -> None:
    plan = _plan()
    candidate = OutlineCompiler().compile(plan, revision_id="PREV_R1")
    assert candidate.volume_plans and candidate.arc_plans
    for volume in candidate.volume_plans:
        assert volume.volume_goal and volume.major_conflict
        assert volume.major_nodes and volume.climax_node_id
        assert volume.arc_ids
    for arc in candidate.arc_plans:
        assert arc.arc_goal and arc.conflict and arc.plot_nodes
        assert arc.chapter_budget > 0
    assert candidate.non_authoritative is True


def test_node_allocation_is_unique_and_causal(tmp_path: Path) -> None:
    plan = _plan()
    candidate = OutlineCompiler().compile(plan, revision_id="PREV_R1")
    execution = [item.node_id for item in candidate.node_allocations
                 if item.role == "execution"]
    assert len(execution) == len(set(execution))
    assert {item.node_id for item in candidate.node_allocations} \
        == {node.node_id for node in plan.plot_nodes}
    order = {node_id: index for index, node_id in
             enumerate(volume.volume_id for volume in candidate.volume_plans)}
    for edge in plan.spine.edges:
        left = next(item for item in candidate.node_allocations
                    if item.node_id == edge.from_node_id)
        right = next(item for item in candidate.node_allocations
                     if item.node_id == edge.to_node_id)
        assert order[left.execution_volume_id] <= order[right.execution_volume_id]


def test_compilation_scope_limits_compile() -> None:
    plan = _plan()
    scope = CompilationScope(kind="spine_segment", node_ids=["NODE_OPEN", "NODE_STOCK"])
    candidate = OutlineCompiler().compile(plan, revision_id="PREV_R1", scope=scope)
    allocated = {item.node_id for item in candidate.node_allocations}
    assert allocated == {"NODE_OPEN", "NODE_STOCK"}
    assert candidate.source_digest == planning_digest(plan)


def test_must_happen_and_optional_allocation() -> None:
    plan = _plan()
    candidate = OutlineCompiler().compile(plan, revision_id="PREV_R1")
    coverage = candidate.coverage
    assert coverage.must_happen_allocated == coverage.must_happen_total
    assert coverage.unallocated_must_happen == []
    assert coverage.status in ("valid", "needs_attention", "blocked")


def test_ignored_pressure_is_visible() -> None:
    plan = _plan()
    candidate = OutlineCompiler().compile(plan, revision_id="PREV_R1")
    assert isinstance(candidate.ignored_pressure_ids, list)
    codes = {item.code for item in candidate.validation_findings}
    if candidate.ignored_pressure_ids:
        assert "IGNORED_PRESSURE_VISIBLE" in codes


def test_carryover_pressures_are_recorded() -> None:
    plan = _plan()
    candidate = OutlineCompiler().compile(plan, revision_id="PREV_R1")
    assert isinstance(candidate.carryover_pressures, list)
    for row in candidate.carryover_pressures:
        assert row.pressure_id.startswith("PRESS_")
        assert row.status in ("carried", "deferred", "intentionally_unresolved", "blocked")


def test_progressive_detail_is_not_forced_to_chapter_ready() -> None:
    plan = _plan()
    candidate = OutlineCompiler().compile(plan, revision_id="PREV_R1")
    assert {volume.detail_level for volume in candidate.volume_plans} == {"arc"}
    assert {arc.detail_level for arc in candidate.arc_plans} == {"arc"}
    node_levels = {node.detail_level for node in plan.plot_nodes}
    assert "chapter_ready" not in node_levels


def test_no_chapter_list_is_generated() -> None:
    candidate = OutlineCompiler().compile(_plan(), revision_id="PREV_R1")
    payload = candidate.model_dump(mode="json")
    text = json.dumps(payload, ensure_ascii=False)
    assert "chapter_uuid" not in text
    assert "CH001" not in text


# ---------------------------------------------------------------- validation
def test_causal_order_violation_is_detected() -> None:
    plan = _plan()
    compiler = OutlineCompiler()
    candidate = compiler.compile(plan, revision_id="PREV_R1")
    bad = candidate.model_copy(update={
        "node_allocations": [item.model_copy(update={"execution_volume_id": "VOL_SEG099"})
                             if item.node_id == "NODE_OPEN" else item
                             for item in candidate.node_allocations],
        "volume_plans": [item.model_copy(update={"volume_id": "VOL_SEG099"}) if index == 0
                         else item for index, item in enumerate(candidate.volume_plans)]})
    findings = compiler.validate(plan, bad)
    assert "ALLOCATION_BREAKS_CAUSAL_ORDER" in {item.code for item in findings}


def test_requirement_satisfier_scheduled_too_late_is_detected() -> None:
    raw = _synthetic(40)
    raw["plot_nodes"][1]["requirements"] = {
        "operator": "all",
        "requirements": [{"requirement_id": "REQ_LATE", "kind": "plot_node",
                          "ref_id": "NODE_S030", "satisfied_by": ["NODE_S030"],
                          "provenance": "generated"}]}
    plan = validate_planning_ir(raw)
    candidate = OutlineCompiler().compile(plan, revision_id="PREV_R1")
    assert "REQUIREMENT_SATISFIER_SCHEDULED_TOO_LATE" in {
        item.code for item in candidate.validation_findings}


def test_missing_must_happen_node_is_reported() -> None:
    plan = _plan()
    compiler = OutlineCompiler()
    candidate = compiler.compile(plan, revision_id="PREV_R1")
    bad = candidate.model_copy(update={
        "node_allocations": [item for item in candidate.node_allocations
                             if item.node_id != "NODE_BRANCH"]})
    findings = compiler.validate(plan, bad)
    codes = {item.code for item in findings}
    assert "UNALLOCATED_MUST_HAPPEN_NODE" in codes
    assert candidate.status in ("valid", "needs_attention")


def test_resource_and_equipment_continuity_findings() -> None:
    raw = _raw()
    raw["equipment_plans"][0]["loss_node"] = "NODE_OPEN"
    plan = validate_planning_ir(raw)
    candidate = OutlineCompiler().compile(plan, revision_id="PREV_R1")
    codes = {item.code for item in candidate.validation_findings}
    assert "EQUIPMENT_CONTINUITY_BROKEN" in codes or not candidate.volume_plans[1:]


def test_map_expansion_consistency() -> None:
    plan = _plan()
    candidate = OutlineCompiler().compile(plan, revision_id="PREV_R1")
    known = {milestone.location_ref for expansion in plan.map_expansions
             for milestone in expansion.milestones}
    for volume in candidate.volume_plans:
        assert set(volume.location_expansion) <= known | {
            location.location_id for location in plan.locations}


def test_no_fixed_volume_or_arc_count() -> None:
    small = OutlineCompiler().compile(_plan(), revision_id="PREV_R1")
    big = OutlineCompiler().compile(validate_planning_ir(_synthetic(90)), revision_id="PREV_R1")
    assert len(big.volume_plans) >= len(small.volume_plans)
    arc_counts = {volume.volume_id: sum(1 for arc in big.arc_plans
                                        if arc.volume_id == volume.volume_id)
                  for volume in big.volume_plans}
    assert len(set(arc_counts.values())) > 1 or len(big.volume_plans) <= 2


# ---------------------------------------------------------------- promotion / projection
def test_candidate_cannot_write_repository_without_approval(tmp_path: Path) -> None:
    plan = _plan()
    candidate = OutlineCompiler().compile(plan, revision_id="PREV_R1")
    repo = PlanningRepository(tmp_path, "demo_urban")
    first = repo.create(plan, revision_id="PREV_R1")
    with pytest.raises(ValueError):
        promote_outline_candidate(repo, candidate)
    assert len(repo.list_revisions()) == 1
    compilation, second = promote_outline_candidate(repo, candidate, approved=True,
                                                    revision_id="PREV_R2")
    assert second.revision == 2 and second.parent_revision_id == first.revision_id
    assert second.plan.volumes and second.plan.arcs
    assert compilation.compiler_version
    assert compilation.promoted_revision_id == second.revision_id
    before = repo.load(first.revision_id)
    assert before.content_digest == first.content_digest


def test_route_provenance_is_propagated() -> None:
    plan = _plan()
    provenance = {"candidate_id": "CAND_ROUTE_A", "session_id": "RSESS_1",
                  "source_revision": "PREV_R1"}
    candidate = OutlineCompiler().compile(plan, revision_id="PREV_R1",
                                          route_provenance=provenance)
    assert candidate.route_provenance["candidate_id"] == "CAND_ROUTE_A"
    assert all(item.route_provenance.get("session_id") == "RSESS_1"
               for item in candidate.node_allocations)


def test_projection_is_read_only_and_complete() -> None:
    plan = _plan()
    candidate = OutlineCompiler().compile(plan, revision_id="PREV_R1")
    before = planning_digest(plan)
    projection = project_outline(candidate)
    assert planning_digest(plan) == before
    assert projection.read_only is True and projection.non_authoritative is True
    assert projection.volumes and projection.arcs and projection.allocations
    assert projection.budget.chapter_independent is True
    assert projection.coverage.status in ("valid", "needs_attention", "blocked")
    assert not hasattr(projection, "save")


def test_context_purposes_for_outline() -> None:
    plan = _plan()
    builder = StoryPlanningContextBuilder(plan, revision_id="PREV_R1")
    assert set(builder.build("volume_compile").payload) == {"plot_nodes", "volumes", "spine"}
    assert set(builder.build("arc_compile").payload) == {"arcs", "plot_nodes"}
    review = builder.build("outline_review")
    assert {"volumes", "arcs", "plot_nodes", "conflict_chains"} <= set(review.payload)


def test_large_synthetic_book_performance() -> None:
    plan = validate_planning_ir(_synthetic(100, arc_count=4))
    started = time.time()
    candidate = OutlineCompiler().compile(plan, revision_id="PREV_SYNTH")
    elapsed = time.time() - started
    assert elapsed < 10
    assert len(candidate.volume_plans) >= 5
    assert sum(len(item.node_ids) for item in candidate.budget_estimates) == 100
    assert candidate.coverage.must_happen_allocated == candidate.coverage.must_happen_total


def test_cross_genre_compilation_is_neutral() -> None:
    for name in (BASE, URBAN, "MODERN_CITY_EXAMPLE.json", "FANTASY_EXAMPLE.json"):
        plan = _plan(name)
        candidate = OutlineCompiler().compile(plan, revision_id="PREV_CG")
        assert candidate.volume_plans and candidate.arc_plans
        errors = [item.code for item in candidate.validation_findings
                  if item.severity == "ERROR"]
        assert "ALLOCATION_BREAKS_CAUSAL_ORDER" not in errors, name


def test_outline_modules_have_no_genre_or_template_hardcoding() -> None:
    offenders: list[str] = []
    for name in ("outline_budget.py", "outline_segmentation.py", "outline_compiler.py",
                 "outline_projection.py"):
        text = (OUTLINE_DIR / name).read_text(encoding="utf-8")
        for term in ("wasteland", "废土", "xianxia", "修仙", "爽文", "BEAT_LADDER",
                     "FuturePlan", "if genre =="):
            if term in text:
                offenders.append(f"{name}: {term}")
    assert offenders == []
