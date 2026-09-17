"""M6：Plot pressure / PlotNode synthesis / StorySpine / ConflictEscalation 回归。"""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from novelforge.story_engine.planning import (
    PlanningRepository,
    PlotProposalError,
    StaticPlotCandidateProvider,
    StoryPlanningContextBuilder,
    StorySpineBuilder,
    analyze_conflict_chains,
    analyze_story_spine,
    build_coverage_report,
    build_plot_pressure_inventory,
    parse_candidates,
    planning_digest,
    promote_candidate,
    propose_candidates,
    project_story_spine,
    root_nodes,
    terminal_nodes,
    topological_order,
    upstream_of,
    validate_planning_ir,
)

FIXTURES = Path("tests/fixtures/planning_ir")
URBAN = "URBAN_GROWTH_EXAMPLE.json"
BASE = "ONE_SENTENCE_EXAMPLE.json"
SPINE_DIR = Path("src/novelforge/story_engine/planning")


def _raw(name: str = URBAN) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def _plan(name: str = URBAN):
    return validate_planning_ir(_raw(name))


def _mutated(mutator, name: str = URBAN):
    raw = _raw(name)
    mutator(raw)
    return validate_planning_ir(raw)


def _codes(report) -> set[str]:
    return set(report.codes())


def _severity(report, code: str) -> list[str]:
    return [item.severity for item in report.findings if item.code == code]


def _node(**overrides) -> dict:
    payload = {"node_id": "NODE_CRISIS", "purpose": "供应链断裂", "importance": "major",
               "location_id": "LOC_MARKET", "participants": ["CHAR_CHEN"],
               "prerequisites": ["NODE_STOCK"], "conflict": "断供",
               "state_change": "现金流见底", "cost": "谈判", "payoff": "独立标准",
               "pressure_kinds": ["resource_deficit"]}
    payload.update(overrides)
    return payload


def _candidate(node: dict | None = None, **overrides) -> dict:
    payload = {"candidate_id": "CAND_TEST_1", "proposed_node": node or _node(),
               "proposed_edges": [], "reasoning_summary": "把资源缺口变成剧情压力"}
    payload.update(overrides)
    return payload


# ---------------------------------------------------------------- pressure inventory
def test_pressure_inventory_covers_m4_and_m5_signals() -> None:
    plan = _plan()
    inventory = build_plot_pressure_inventory(plan, revision_id="PREV_P")
    assert inventory.read_only is True
    kinds = inventory.by_kind()
    for kind in ("character_arc_pressure", "relationship_pressure", "faction_pressure",
                 "information_due", "foreshadow_due", "progression_due", "reward_drought",
                 "autonomous_action", "requirement_unlock"):
        assert kind in kinds, kind
    assert inventory.open() and inventory.scheduled()
    assert all(item.non_authoritative is True for item in inventory.pressures)
    assert all(item.pressure_id.startswith("PRESS_") for item in inventory.pressures)


def test_pressure_inventory_marks_blocked_from_error_findings() -> None:
    from novelforge.story_engine.planning import validate_resources

    def break_resources(data):
        data["resource_flows"][0]["unit_id"] = "UNIT_COUNT"
    plan = _mutated(break_resources)
    report = validate_resources(plan)
    inventory = build_plot_pressure_inventory(plan, analysis={"resource": report})
    assert inventory.blocked()
    assert any(item.evidence.get("code") == "RESOURCE_UNIT_MISMATCH"
               for item in inventory.blocked())


# ---------------------------------------------------------------- requirement closure
def test_node_requirement_with_upstream_satisfier_is_closed() -> None:
    def mutate(data):
        data["plot_nodes"][2]["requirements"] = {
            "operator": "all",
            "requirements": [{"requirement_id": "REQ_BRANCH", "kind": "plot_node",
                              "ref_id": "NODE_STOCK", "satisfied_by": ["NODE_STOCK"],
                              "provenance": "supplied"}]}
    report = analyze_story_spine(_mutated(mutate))
    assert "REQUIREMENT_WITHOUT_CLOSURE" not in _codes(report)
    assert "REQUIREMENT_SATISFIER_NOT_UPSTREAM" not in _codes(report)


def test_requirement_without_closure_is_an_error() -> None:
    def mutate(data):
        data["plot_nodes"][2]["requirements"] = {
            "operator": "all",
            "requirements": [{"requirement_id": "REQ_ORPHAN", "kind": "custom",
                              "description": "没有任何来源的要求",
                              "provenance": "generated"}]}
    report = analyze_story_spine(_mutated(mutate))
    assert _severity(report, "REQUIREMENT_WITHOUT_CLOSURE") == ["ERROR"]


def test_requirement_satisfier_must_be_upstream() -> None:
    def mutate(data):
        data["plot_nodes"][0]["requirements"] = {
            "operator": "all",
            "requirements": [{"requirement_id": "REQ_LATE", "kind": "plot_node",
                              "ref_id": "NODE_BRANCH", "satisfied_by": ["NODE_BRANCH"],
                              "provenance": "generated"}]}
    report = analyze_story_spine(_mutated(mutate))
    assert _severity(report, "REQUIREMENT_SATISFIER_NOT_UPSTREAM") == ["ERROR"]


def test_requirement_causal_cycle_is_detected() -> None:
    def mutate(data):
        data["plot_nodes"][1]["requirements"] = {
            "operator": "all",
            "requirements": [{"requirement_id": "REQ_A", "kind": "plot_node",
                              "ref_id": "NODE_BRANCH", "satisfied_by": ["NODE_BRANCH"],
                              "provenance": "generated"}]}
        data["plot_nodes"][2]["requirements"] = {
            "operator": "all",
            "requirements": [{"requirement_id": "REQ_B", "kind": "plot_node",
                              "ref_id": "NODE_STOCK", "satisfied_by": ["NODE_STOCK"],
                              "provenance": "generated"}]}
    report = analyze_story_spine(_mutated(mutate))
    assert "REQUIREMENT_CAUSAL_CYCLE" in _codes(report)
    assert set(_severity(report, "REQUIREMENT_CAUSAL_CYCLE")) == {"ERROR"}


def test_requirement_satisfier_unknown_is_an_error() -> None:
    def mutate(data):
        data["plot_nodes"][2]["requirements"] = {
            "operator": "all",
            "requirements": [{"requirement_id": "REQ_GHOST", "kind": "plot_node",
                              "ref_id": "NODE_GHOST", "satisfied_by": ["NODE_GHOST"],
                              "provenance": "generated"}]}
    assert "REQUIREMENT_SATISFIER_UNKNOWN" in _codes(analyze_story_spine(_mutated(mutate)))


# ---------------------------------------------------------------- node refs / pressure / outcome
def test_plot_node_structured_refs_are_validated() -> None:
    def mutate(data):
        data["plot_nodes"][1]["foreshadow_move_refs"] = ["FSMOVE_GHOST"]
        data["plot_nodes"][1]["reward_refs"] = ["REWARD_GHOST"]
    report = analyze_story_spine(_mutated(mutate))
    assert _severity(report, "PLOT_NODE_REF_UNKNOWN") == ["ERROR", "ERROR"]


def test_plot_node_without_pressure_source_is_an_error() -> None:
    def mutate(data):
        floating = _node(node_id="NODE_FLOATING", prerequisites=[], pressure_kinds=[])
        floating.pop("conflict")
        data["plot_nodes"].append(floating)
        data["spine"]["nodes"].append("NODE_FLOATING")
    report = analyze_story_spine(_mutated(mutate))
    assert "PLOT_NODE_NO_PRESSURE_SOURCE" in _codes(report)


def test_plot_node_without_outcome_is_a_warning() -> None:
    def mutate(data):
        node = _node(node_id="NODE_THIN", state_change="", cost="", payoff="")
        data["plot_nodes"].append(node)
        data["spine"]["nodes"].append("NODE_THIN")
        data["spine"]["edges"].append({"from_node_id": "NODE_STOCK",
                                       "to_node_id": "NODE_THIN", "relation": "causes"})
    report = analyze_story_spine(_mutated(mutate))
    assert _severity(report, "PLOT_NODE_NO_OUTCOME") == ["WARNING"]


# ---------------------------------------------------------------- arc anchors
def test_character_arc_choice_must_be_anchored() -> None:
    def mutate(data):
        data["character_arcs"][0]["major_choices"][0]["node_id"] = ""
        data["character_arcs"][0]["major_choices"][1]["node_id"] = ""
    report = analyze_story_spine(_mutated(mutate))
    assert "CHARACTER_ARC_CHOICE_UNANCHORED" in _codes(report)


def test_stage_trigger_nodes_are_checked() -> None:
    def relationship(data):
        data["relationship_arcs"][0]["stages"][0]["trigger_node_id"] = "NODE_GHOST"
    assert "RELATIONSHIP_STAGE_TRIGGER_UNANCHORED" in _codes(
        analyze_story_spine(_mutated(relationship)))

    def faction(data):
        data["faction_arcs"][0]["stages"][0]["trigger_node_id"] = "NODE_GHOST"
    assert "FACTION_STAGE_TRIGGER_UNANCHORED" in _codes(
        analyze_story_spine(_mutated(faction)))


# ---------------------------------------------------------------- resource / equipment / location
def test_resource_unsupported_node_is_an_error() -> None:
    def mutate(data):
        data["resource_flows"] = [flow for flow in data["resource_flows"]
                                  if flow["flow_id"] not in ("RFLOW_REFILL", "RFLOW_BUY")]
        data["plot_nodes"][1]["resource_flow_refs"] = ["RFLOW_USE"]
    report = analyze_story_spine(_mutated(mutate))
    assert _severity(report, "RESOURCE_UNSUPPORTED_NODE") == ["ERROR"]


def test_equipment_use_after_loss_in_node_is_an_error() -> None:
    def mutate(data):
        data["equipment_plans"][0]["loss_node"] = "NODE_OPEN"
        data["plot_nodes"][2]["equipment_refs"] = ["EQ_CALIPER"]
    report = analyze_story_spine(_mutated(mutate))
    assert "EQUIPMENT_USE_AFTER_LOSS_NODE" in _codes(report)


def test_location_unreachable_and_blocked_nodes() -> None:
    def unreachable(data):
        data["location_graph"]["edges"] = []
    report = analyze_story_spine(_mutated(unreachable))
    assert "LOCATION_UNREACHABLE_NODE" in _codes(report)
    assert set(_severity(report, "LOCATION_UNREACHABLE_NODE")) == {"ERROR"}
    report = analyze_story_spine(_plan())
    assert set(_severity(report, "LOCATION_BLOCKED_NODE")) == {"WARNING"}


# ---------------------------------------------------------------- information / foreshadow / reward
def test_information_reveal_must_be_downstream_of_plant() -> None:
    def mutate(data):
        for move in data["information_arcs"][0]["moves"]:
            if move["move_type"] in ("plant", "hint"):
                move["node_id"] = "NODE_BRANCH"
    report = analyze_story_spine(_mutated(mutate))
    assert "INFORMATION_REVEAL_NOT_UPSTREAM" in _codes(report)


def test_foreshadow_payoff_must_be_downstream_of_plant() -> None:
    def mutate(data):
        for move in data["foreshadow_plans"][0]["moves"]:
            if move["move_type"] in ("plant", "reinforce"):
                move["node_id"] = "NODE_BRANCH"
    report = analyze_story_spine(_mutated(mutate))
    assert _severity(report, "FORESHADOW_PAYOFF_NOT_UPSTREAM") == ["ERROR"]


def test_climax_reward_linkage_warning() -> None:
    def mutate(data):
        data["plot_nodes"][2]["reward_refs"] = []
    report = analyze_story_spine(_mutated(mutate))
    assert _severity(report, "CLIMAX_REWARD_LINKAGE_MISSING") == ["WARNING"]


# ---------------------------------------------------------------- spine DAG gates
def test_spine_topology_roots_and_terminals() -> None:
    plan = _plan()
    assert topological_order(plan) == ["NODE_OPEN", "NODE_STOCK", "NODE_BRANCH"]
    assert root_nodes(plan) == ["NODE_OPEN"]
    assert terminal_nodes(plan) == ["NODE_BRANCH"]
    assert upstream_of(plan, "NODE_BRANCH") == {"NODE_OPEN", "NODE_STOCK"}


def test_dangling_edge_and_self_dependency() -> None:
    def dangling(data):
        data["spine"]["edges"].append({"from_node_id": "NODE_OPEN",
                                       "to_node_id": "NODE_GHOST"})
    assert "SPINE_DANGLING_EDGE" in _codes(analyze_story_spine(_mutated(dangling)))

    def self_dep(data):
        data["spine"]["edges"].append({"from_node_id": "NODE_STOCK",
                                       "to_node_id": "NODE_STOCK"})
    report = analyze_story_spine(_mutated(self_dep))
    assert "SPINE_SELF_DEPENDENCY" in _codes(report)
    assert "SPINE_CYCLE" in _codes(report)


def test_must_happen_node_outside_spine_is_an_error() -> None:
    def mutate(data):
        data["plot_nodes"].append({
            "node_id": "NODE_ISOLATED", "purpose": "孤立但必须发生的节点",
            "conflict": "无人推动", "state_change": "状态变化",
            "must_happen": True, "pressure_kinds": ["custom"]})
    report = analyze_story_spine(_mutated(mutate))
    assert _severity(report, "MUST_HAPPEN_NODE_OUTSIDE_SPINE") == ["ERROR"]


def test_optional_node_outside_path_is_warning_not_error() -> None:
    def mutate(data):
        data["plot_nodes"].append({
            "node_id": "NODE_SIDE", "purpose": "可选支线", "conflict": "支线冲突",
            "state_change": "支线变化", "optional": True, "pressure_kinds": ["custom"]})
        data["spine"]["nodes"].append("NODE_SIDE")
    report = analyze_story_spine(_mutated(mutate))
    assert "MUST_HAPPEN_NODE_OUTSIDE_SPINE" not in _codes(report)
    assert [item.code for item in report.findings if item.severity == "ERROR"] == []


def test_alternative_conflict_on_must_happen_node() -> None:
    def mutate(data):
        node = data["plot_nodes"][0]
        node["must_happen"] = True
        node["alternatives"] = ["NODE_STOCK", "NODE_BRANCH"]
    assert _severity(analyze_story_spine(_mutated(mutate)),
                     "PLOT_NODE_ALTERNATIVE_CONFLICT") == ["ERROR"]


# ---------------------------------------------------------------- conflict escalation
def _conflict_stage(index: int, **overrides) -> dict:
    payload = {"stage_id": f"CSTAGE_{index:04d}", "conflict_id": "CONFLICT_CHAIN_1",
               "scope": ["local", "arc", "volume", "macro"][min(index, 3)],
               "trigger_node_id": "NODE_STOCK", "actor_refs": ["FACTION_CHAIN"],
               "target_refs": ["CHAR_CHEN"], "location_refs": ["LOC_MARKET"],
               "stakes": f"第 {index} 阶段的赌注", "expected_consequence": "压力升级",
               "provenance": "supplied"}
    payload.update(overrides)
    return payload


def _with_conflict(stages: list[dict]):
    def mutate(data):
        data["conflict_chains"] = [{"conflict_id": "CONFLICT_CHAIN_1", "title": "断供冲突",
                                    "stages": stages, "provenance": "supplied"}]
    return mutate


def test_conflict_escalation_with_causal_change_passes() -> None:
    plan = _mutated(_with_conflict([
        _conflict_stage(0),
        _conflict_stage(1, stakes="", constraint_change="执照被吊销",
                        faction_relation_refs=["FREL_CHAIN_SUPPLIER"],
                        resource_refs=["PLAN_RFLOW"], pressure_refs=["REQ_BRANCH"])],
        ))
    report = analyze_conflict_chains(plan, revision_id="PREV_C")
    assert "CONFLICT_ESCALATION_WITHOUT_CAUSAL_CHANGE" not in _codes(report)


def test_conflict_escalation_without_causal_change_is_flagged() -> None:
    plan = _mutated(_with_conflict([
        _conflict_stage(0),
        _conflict_stage(1, stakes="", expected_consequence="")]))
    report = analyze_conflict_chains(plan)
    assert set(_severity(report, "CONFLICT_ESCALATION_WITHOUT_CAUSAL_CHANGE")) == {"WARNING"}
    strict = analyze_conflict_chains(plan, strict=True)
    assert set(_severity(strict, "CONFLICT_ESCALATION_WITHOUT_CAUSAL_CHANGE")) == {"ERROR"}


def test_conflict_escalation_without_structural_support_is_flagged() -> None:
    plan = _mutated(_with_conflict([
        _conflict_stage(0),
        _conflict_stage(1, stakes="赌注变大", constraint_change="",
                        expected_consequence="")]))
    report = analyze_conflict_chains(plan)
    assert _severity(report, "CONFLICT_ESCALATION_UNSUPPORTED") == ["WARNING"]


def test_conflict_stage_reference_and_scope_checks() -> None:
    plan = _mutated(_with_conflict([
        _conflict_stage(0, scope="macro"),
        _conflict_stage(1, scope="local", trigger_node_id="NODE_GHOST",
                        faction_relation_refs=["FREL_GHOST"])]))
    report = analyze_conflict_chains(plan)
    assert "CONFLICT_STAGE_TRIGGER_UNKNOWN" in _codes(report)
    assert "CONFLICT_STAGE_RELATION_UNKNOWN" in _codes(report)
    assert "CONFLICT_SCOPE_REGRESSION" in _codes(report)


# ---------------------------------------------------------------- coverage / projection
def test_spine_coverage_report_counts() -> None:
    plan = _plan()
    coverage = build_coverage_report(plan, revision_id="PREV_C")
    assert coverage.plot_node_count == 3
    assert coverage.must_happen_count == 3
    assert coverage.root_count == 1 and coverage.terminal_count == 1
    assert coverage.requirement_total > 0
    assert coverage.unaddressed_pressures
    assert coverage.read_only is True


def test_character_arc_and_reward_coverage() -> None:
    def mutate(data):
        data["plot_nodes"][2]["character_arc_refs"] = ["CARCH_CHEN"]
        data["plot_nodes"][2]["reward_refs"] = ["REWARD_BRANCH_OPEN"]
    coverage = build_coverage_report(_mutated(mutate))
    assert coverage.character_arc_coverage == 1
    assert coverage.reward_coverage >= 1


def test_repetition_and_theme_warnings() -> None:
    def repeat(data):
        first = data["plot_nodes"][0]
        second = data["plot_nodes"][1]
        second["location_id"] = first["location_id"]
        second["participants"] = list(first["participants"])
        second["purpose"] = first["purpose"]
        second["conflict"] = first["conflict"]
    report = analyze_story_spine(_mutated(repeat))
    assert "PLOT_NODE_PATTERN_REPETITION" in _codes(report)
    assert "THEME_LINKAGE_MISSING" in _codes(analyze_story_spine(_plan()))

    def themed(data):
        data["plot_nodes"][2]["theme_refs"] = ["THEME_URBAN"]
    assert "THEME_LINKAGE_MISSING" not in _codes(analyze_story_spine(_mutated(themed)))


def test_projection_is_read_only_and_digest_unchanged() -> None:
    plan = _plan()
    before = planning_digest(plan)
    projection = project_story_spine(plan, revision_id="PREV_6")
    assert planning_digest(plan) == before
    assert projection.read_only is True and projection.non_authoritative is True
    assert projection.revision_id == "PREV_6"
    assert projection.content_digest == before
    assert [node.id for node in projection.nodes][:3] == ["NODE_OPEN", "NODE_STOCK",
                                                          "NODE_BRANCH"]
    assert all(edge.non_authoritative is True for edge in projection.edges)
    assert projection.coverage is not None
    assert projection.pressure_coverage.open_pressures
    assert not hasattr(projection, "save")


# ---------------------------------------------------------------- synthesis / promotion
def test_candidate_validation_and_no_repository_write() -> None:
    plan = _plan()
    provider = StaticPlotCandidateProvider([_candidate()])
    proposal = propose_candidates(plan, provider, revision_id="PREV_SYN")
    assert proposal.candidates
    candidate = proposal.candidates[0]
    assert candidate.validation_findings is not None
    assert candidate.approved is False
    assert candidate.blocking() is False


def test_candidate_with_unknown_refs_is_blocking() -> None:
    node = _node(foreshadow_move_refs=["FSMOVE_GHOST"])
    provider = StaticPlotCandidateProvider([_candidate(node)])
    proposal = propose_candidates(_plan(), provider, revision_id="PREV_SYN")
    candidate = proposal.candidates[0]
    assert candidate.blocking() is True


def test_promotion_requires_approval_and_creates_new_revision(tmp_path: Path) -> None:
    plan = _plan()
    provider = StaticPlotCandidateProvider([_candidate()])
    candidate = propose_candidates(plan, provider, revision_id="PREV_SYN").candidates[0]
    repo = PlanningRepository(tmp_path, "demo_urban")
    first = repo.create(plan, revision_id="PREV_M6_R1")
    with pytest.raises(PlotProposalError) as error:
        promote_candidate(repo, first.revision_id, candidate)
    assert error.value.code == "CANDIDATE_NOT_APPROVED"
    assert len(repo.list_revisions()) == 1
    candidate.approved = True
    second = promote_candidate(repo, first.revision_id, candidate,
                               revision_id="PREV_M6_R2")
    assert second.revision == 2 and second.parent_revision_id == first.revision_id
    assert "NODE_CRISIS" in {item.node_id for item in second.plan.plot_nodes}
    assert "NODE_CRISIS" not in {item.node_id
                                 for item in repo.load(first.revision_id).plan.plot_nodes}
    with pytest.raises(PlotProposalError):
        promote_candidate(repo, first.revision_id, candidate.model_copy(
            update={"validation_findings": [{"code": "X", "severity": "ERROR"}]}))


def test_parse_candidates_rejects_invalid_payloads() -> None:
    with pytest.raises(PlotProposalError) as broken:
        parse_candidates("{not json", source_revision="PREV", provider="llm", model="m")
    assert broken.value.code == "PLOT_PROPOSAL_JSON_INVALID"
    with pytest.raises(PlotProposalError) as shape:
        parse_candidates(json.dumps({"candidates": "nope"}), source_revision="PREV",
                         provider="llm", model="m")
    assert shape.value.code == "PLOT_PROPOSAL_SHAPE_INVALID"
    with pytest.raises(PlotProposalError) as schema:
        parse_candidates(json.dumps({"candidates": [{"candidate_id": "CAND_X"}]}),
                         source_revision="PREV", provider="llm", model="m")
    assert schema.value.code == "PLOT_CANDIDATE_SCHEMA_INVALID"


def test_spine_builder_assembles_and_keeps_old_revision(tmp_path: Path) -> None:
    plan = _plan()
    builder = StorySpineBuilder(novel_id="demo_urban")
    from novelforge.story_engine.planning import PlotNode
    extra = PlotNode.model_validate(_node(node_id="NODE_AFTER",
                                          prerequisites=["NODE_BRANCH"]))
    new_plan = builder.build_plan(plan, nodes=[extra])
    assert "NODE_AFTER" in new_plan.spine.nodes
    assert terminal_nodes(new_plan) == ["NODE_AFTER"]
    assert "NODE_AFTER" not in {item.node_id for item in plan.plot_nodes}
    repo = PlanningRepository(tmp_path, "demo_urban")
    first = repo.create(plan, revision_id="PREV_M6_A")
    second = builder.build_revision(plan, repo, revision_id="PREV_M6_B")
    assert second.revision == 2
    assert len(repo.load(first.revision_id).plan.plot_nodes) == 3


def test_long_spine_scale_and_performance() -> None:
    """§44：几十到几百 PlotNode 的构建 / 拓扑 / coverage 不应退化。"""

    nodes = []
    edges = []
    for index in range(60):
        node_id = f"NODE_STEP_{index:03d}"
        nodes.append({"node_id": node_id, "purpose": f"第 {index} 个节点",
                      "conflict": "阶段冲突", "state_change": "状态推进",
                      "pressure_kinds": ["custom"],
                      "prerequisites": [] if index == 0 else [f"NODE_STEP_{index - 1:03d}"]})
        if index:
            edges.append({"from_node_id": f"NODE_STEP_{index - 1:03d}",
                          "to_node_id": node_id, "relation": "causes"})
    raw = {"planning_id": "PLAN_SCALE", "novel_id": "demo_scale", "plot_nodes": nodes,
           "spine": {"spine_id": "SPINE_SCALE", "novel_id": "demo_scale",
                     "nodes": [item["node_id"] for item in nodes], "edges": edges,
                     "entry_node_ids": ["NODE_STEP_000"],
                     "terminal_node_ids": ["NODE_STEP_059"],
                     "provenance": "generated"}}
    plan = validate_planning_ir(raw)
    order = topological_order(plan)
    assert len(order) == 60
    report = analyze_story_spine(plan, revision_id="PREV_SCALE")
    assert [item.code for item in report.findings if item.severity == "ERROR"] == []
    coverage = build_coverage_report(plan, revision_id="PREV_SCALE")
    assert coverage.plot_node_count == 60
    assert coverage.root_count == 1 and coverage.terminal_count == 1


def test_cross_genre_spines_have_no_errors() -> None:
    for name in (BASE, "MODERN_CITY_EXAMPLE.json", URBAN, "FANTASY_EXAMPLE.json"):
        plan = _plan(name)
        report = analyze_story_spine(plan, revision_id="PREV_CG")
        errors = [item.code for item in report.findings if item.severity == "ERROR"]
        assert errors == [], (name, errors)
        conflicts = analyze_conflict_chains(plan, revision_id="PREV_CG")
        assert [item.code for item in conflicts.findings
                if item.severity == "ERROR"] == []


def test_spine_modules_have_no_genre_or_beat_ladder_hardcoding() -> None:
    offenders: list[str] = []
    for name in ("plot_pressure.py", "plot_synthesis.py", "spine_builder.py",
                 "spine_analysis.py", "conflict_escalation.py", "spine_projection.py"):
        text = (SPINE_DIR / name).read_text(encoding="utf-8")
        for term in ("wasteland", "废土", "xianxia", "修仙", "爽文",
                     "BEAT_LADDER", "beat_ladder", "每 5 章", "固定卷数"):
            if term in text:
                offenders.append(f"{name}: {term}")
    assert offenders == []
