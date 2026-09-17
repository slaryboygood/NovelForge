"""M4：Planning Graph 回归（三张图 + 跨图校验 + 可达性 + projection + context 集成）。"""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from novelforge.story_engine.planning import (
    StoryPlanningContextBuilder,
    build_faction_graph,
    build_location_graph,
    build_planning_graphs,
    build_relationship_graph,
    entry_locations,
    faction_pressure_candidates,
    location_path,
    planning_digest,
    reachable_locations,
    summarize_graphs,
    summarize_plan,
    validate_planning_ir,
)
from novelforge.story_engine.planning.graph_projection import project_bundle, project_graph
from novelforge.story_engine.planning.graph_validator import PlanningGraphValidator
from novelforge.story_engine.planning.graphs import reachable_locations as reach

FIXTURES = Path("tests/fixtures/planning_ir")
BASE = "ONE_SENTENCE_EXAMPLE.json"
GRAPH_DIR = Path("src/novelforge/story_engine/planning")


def _raw(name: str = BASE) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def _plan(name: str = BASE, **mutations):
    raw = _raw(name)
    raw.update(mutations)
    return validate_planning_ir(raw)


def _mutated(mutator) -> dict:
    raw = _raw()
    mutator(raw)
    return raw


def _report(plan, *, requirements=()):
    return PlanningGraphValidator(known_entity_ids=["ENTITY_PROTAGONIST"]).validate(
        plan, revision_id="PREV_GRAPH_TEST", available_requirements=requirements)


def _codes(plan, **kwargs) -> set[str]:
    return set(_report(plan, **kwargs).codes())


# ---------------------------------------------------------------- build
def test_location_graph_builds_nodes_and_route_metadata() -> None:
    plan = _plan()
    graph = build_location_graph(plan)
    assert graph.domain == "location"
    assert [node.node_id for node in graph.nodes] == ["LOC_BRIDGE", "LOC_TOWN"]
    assert len(graph.edges) == 1
    edge = graph.edges[0]
    assert edge.kind == "route"
    assert edge.source_id == "LOC_TOWN" and edge.target_id == "LOC_BRIDGE"
    assert edge.metadata["distance"] == 12.5
    assert edge.metadata["travel_time"] == "半天"
    assert edge.metadata["requirement"] == "无"   # 原始值保留；"无" 被视作无门槛
    assert edge.source_planning_ids == ["LOC_TOWN", "LOC_BRIDGE"]


def test_relationship_graph_keeps_full_participant_set() -> None:
    plan = _plan()
    graph = build_relationship_graph(plan)
    assert {node.kind for node in graph.nodes} == {"character"}
    edge = graph.edges[0]
    assert edge.kind == "relationship"
    assert edge.participants == ["CHAR_LIN", "CHAR_MA"]
    assert edge.metadata["non_authoritative"] is True
    assert edge.metadata["irreversible_node"] == "NODE_FAIL"
    assert "trust" not in edge.metadata


def test_faction_graph_projects_alliance_hostility_and_territory() -> None:
    raw = _mutated(lambda data: data["factions"][0].update(
        {"allies": ["FACTION_OTHER"], "enemies": ["FACTION_ENEMY"],
         "territory": ["LOC_TOWN"]}))
    raw["factions"].append({"faction_id": "FACTION_OTHER", "display_name": "另一势力",
                            "territory": ["LOC_BRIDGE"]})
    raw["factions"].append({"faction_id": "FACTION_ENEMY", "display_name": "敌对势力"})
    graph = build_faction_graph(validate_planning_ir(raw))
    kinds = sorted(edge.kind for edge in graph.edges)
    assert kinds == ["alliance", "hostility", "territory", "territory"]
    assert {node.node_id for node in graph.nodes} >= {"FACTION_TOWN", "FACTION_OTHER",
                                                      "FACTION_ENEMY"}


def test_graph_build_is_deterministic_and_carries_revision_provenance() -> None:
    plan = _plan()
    first = build_planning_graphs(plan, revision_id="PREV_1", content_digest="digest-1")
    second = build_planning_graphs(plan, revision_id="PREV_1", content_digest="digest-1")
    assert first.model_dump_json() == second.model_dump_json()
    assert first.revision_id == "PREV_1"
    assert first.content_digest == "digest-1"
    report = _report(plan)
    assert report.revision_id == "PREV_GRAPH_TEST"
    assert report.content_digest == planning_digest(plan)
    for finding in report.findings:
        assert finding.evidence.get("revision_id") == "PREV_GRAPH_TEST"


# ---------------------------------------------------------------- reachability
def test_reachability_distinguishes_gated_from_unreachable() -> None:
    plan = _plan()
    assert entry_locations(plan) == ["LOC_TOWN"]
    blocked = reachable_locations(plan, "LOC_TOWN")
    assert blocked.reachable == ["LOC_TOWN"]
    assert "LOC_BRIDGE" in blocked.blocked
    assert "entry requirement" in blocked.blocked["LOC_BRIDGE"]
    allowed = reach(plan, "LOC_TOWN", available_requirements=["需要镇务会放行"],
                    available_availability=["白天"])
    assert allowed.reachable == ["LOC_BRIDGE", "LOC_TOWN"]
    assert location_path(plan, "LOC_TOWN", "LOC_BRIDGE",
                         available_requirements=["需要镇务会放行"]) == ["LOC_TOWN", "LOC_BRIDGE"]
    assert location_path(plan, "LOC_TOWN", "LOC_TOWN") == ["LOC_TOWN"]


def test_unknown_start_location_is_reported_as_unreachable() -> None:
    plan = _plan()
    result = reachable_locations(plan, "LOC_GHOST")
    assert result.reachable == []
    assert result.unreachable == ["LOC_BRIDGE", "LOC_TOWN"]


# ---------------------------------------------------------------- location findings
def test_dangling_location_reference_is_an_error() -> None:
    raw = _mutated(lambda data: data["location_graph"]["edges"].append(
        {"from_location_id": "LOC_TOWN", "to_location_id": "LOC_GHOST", "route": "废弃支线",
         "distance": 2.0, "travel_time": "10 分钟"}))
    report = _report(validate_planning_ir(raw))
    assert "LOCATION_DANGLING_REF" in report.codes()
    assert any(item.severity == "ERROR" and item.source_id == "LOC_GHOST"
               for item in report.findings)


def test_unreachable_required_location_is_an_error() -> None:
    raw = _mutated(lambda data: data["location_graph"].update({"edges": []}))
    report = _report(validate_planning_ir(raw))
    codes = set(report.codes())
    assert "LOCATION_UNREACHABLE" in codes
    assert "LOCATION_UNREACHABLE_REQUIRED_NODE" in codes
    assert report.ok() is False
    finding = next(item for item in report.findings
                   if item.code == "LOCATION_UNREACHABLE_REQUIRED_NODE")
    assert set(finding.related_ids) >= {"NODE_FAIL", "NODE_CLIMAX"}


def test_location_risk_rules_are_warnings_or_info() -> None:
    raw = _mutated(lambda data: data["location_graph"]["edges"].append(
        {"from_location_id": "LOC_TOWN", "to_location_id": "LOC_BRIDGE", "route": "旧道",
         "distance": 12.5, "travel_time": "半天", "availability": "仅在暴雨后",
         "requirement": "RULE_GHOST"}))
    report = _report(validate_planning_ir(raw))
    codes = set(report.codes())
    assert "LOCATION_DUPLICATE_ROUTE" in codes
    assert "LOCATION_CONTRADICTORY_AVAILABILITY" in codes
    assert "LOCATION_IMPOSSIBLE_REQUIREMENT" in codes
    severity = {item.code: item.severity for item in report.findings}
    assert severity["LOCATION_DUPLICATE_ROUTE"] == "WARNING"
    assert severity["LOCATION_IMPOSSIBLE_REQUIREMENT"] == "ERROR"


# ---------------------------------------------------------------- relationship findings
def test_relationship_dangling_participant_is_an_error() -> None:
    raw = _mutated(lambda data: data["relationship_arcs"][0].update(
        {"participants": ["CHAR_LIN", "CHAR_GHOST"]}))
    report = _report(validate_planning_ir(raw))
    assert "RELATIONSHIP_DANGLING_PARTICIPANT" in report.codes()
    assert "CROSS_GRAPH_PARTICIPANT_DANGLING" in report.codes()


def test_relationship_stage_duplicate_label_is_an_error() -> None:
    raw = _mutated(lambda data: data["relationship_arcs"][0]["stages"].append(
        {"stage_id": "STAGE_DUP", "label": "试探", "trigger": "再次试探",
         "state": "仍未决定"}))
    report = _report(validate_planning_ir(raw))
    assert "RELATIONSHIP_STAGE_DUPLICATE_LABEL" in report.codes()


def test_relationship_irreversible_regression_is_an_error() -> None:
    def mutate(data):
        arc = data["relationship_arcs"][0]
        arc["stages"] = [
            {"stage_id": "S1", "label": "试探", "trigger": "第一次合作", "state": "互不信任"},
            {"stage_id": "S2", "label": "摊牌", "trigger": "失败后追责", "state": "有人让出署名",
             "irreversible": True},
            {"stage_id": "S3", "label": "回退", "trigger": "误会让步", "state": "互不信任"}]
    raw = _mutated(mutate)
    report = _report(validate_planning_ir(raw))
    assert "RELATIONSHIP_IRREVERSIBLE_REGRESSION" in report.codes()

    def unknown_node(data):
        data["relationship_arcs"][0]["irreversible_node"] = "NODE_GHOST"
    assert "RELATIONSHIP_IRREVERSIBLE_UNKNOWN_NODE" in _codes(validate_planning_ir(
        _mutated(unknown_node)))


def test_relationship_trigger_unknown_node_is_a_warning() -> None:
    raw = _mutated(lambda data: data["relationship_arcs"][0]["stages"][0].update(
        {"trigger": "在 NODE_GHOST 发生的事"}))
    report = _report(validate_planning_ir(raw))
    assert "RELATIONSHIP_TRIGGER_UNKNOWN_NODE" in report.codes()
    assert [item.severity for item in report.findings
            if item.code == "RELATIONSHIP_TRIGGER_UNKNOWN_NODE"] == ["WARNING"]


def test_stage_trigger_before_irreversible_is_a_timeline_warning() -> None:
    """§21：用 timeline 的 sequence_order 抓明显前后倒置。"""

    def mutate(data):
        arc = data["relationship_arcs"][0]
        arc["stages"][0]["irreversible"] = True
        arc["stages"].append({"stage_id": "STAGE_LATE", "label": "回归",
                              "trigger": "重新回到 NODE_ACCEPT 谈判", "state": "回到起点"})
    report = _report(validate_planning_ir(_mutated(mutate)))
    code = "RELATIONSHIP_STAGE_TRIGGER_BEFORE_IRREVERSIBLE"
    assert code in report.codes()
    finding = next(item for item in report.findings if item.code == code)
    assert finding.severity == "WARNING"
    assert finding.evidence["irreversible_order"] == 1
    assert finding.evidence["sequence_order"] == 0


# ---------------------------------------------------------------- faction findings
def test_faction_ally_and_enemy_conflict_needs_explanation() -> None:
    raw = _mutated(lambda data: (data["factions"][0].update(
        {"allies": ["FACTION_OTHER"], "enemies": ["FACTION_OTHER"]}),
        data["factions"].append({"faction_id": "FACTION_OTHER", "display_name": "两面派"})))
    report = _report(validate_planning_ir(raw))
    assert "FACTION_ALLY_AND_ENEMY" in report.codes()
    assert [item.severity for item in report.findings
            if item.code == "FACTION_ALLY_AND_ENEMY"] == ["ERROR"]
    raw = _mutated(lambda data: (data["factions"][0].update(
        {"allies": ["FACTION_OTHER"], "enemies": ["FACTION_OTHER"],
         "note": "表面结盟、暗中敌对，已在剧情里解释"}),
        data["factions"].append({"faction_id": "FACTION_OTHER", "display_name": "两面派"})))
    severity = [item.severity for item in _report(validate_planning_ir(raw)).findings
                if item.code == "FACTION_ALLY_AND_ENEMY"]
    assert severity == ["WARNING"]


def test_faction_territory_and_stage_rules() -> None:
    raw = _mutated(lambda data: data["factions"][0].update({"territory": ["LOC_GHOST"]}))
    report = _report(validate_planning_ir(raw))
    assert "FACTION_TERRITORY_DANGLING" in report.codes()
    assert "CROSS_GRAPH_TERRITORY_DANGLING" in report.codes()

    def duplicate_stage(data):
        data["faction_arcs"].append({"arc_id": "FARC_TOWN", "faction_id": "FACTION_TOWN",
                                     "stages": [
                                         {"stage_id": "F1", "label": "施压", "trigger": "期限临近"},
                                         {"stage_id": "F2", "label": "施压", "trigger": "再次施压"}]})
    assert "FACTION_STAGE_DUPLICATE_LABEL" in _codes(validate_planning_ir(
        _mutated(duplicate_stage)))


def test_faction_territory_overlap_is_info_not_error() -> None:
    raw = _mutated(lambda data: (
        data["factions"][0].update({"territory": ["LOC_TOWN"]}),
        data["factions"].append({"faction_id": "FACTION_OTHER", "display_name": "另一势力",
                                 "territory": ["LOC_TOWN"]})))
    report = _report(validate_planning_ir(raw))
    overlap = [item for item in report.findings if item.code == "FACTION_TERRITORY_OVERLAP"]
    assert overlap and overlap[0].severity == "INFO"
    assert "FACTION_TERRITORY_OVERLAP" not in {item.code for item in report.errors()}


def test_faction_without_pressure_path_is_a_warning() -> None:
    raw = _mutated(lambda data: data["factions"].append(
        {"faction_id": "FACTION_QUIET", "display_name": "沉默势力"}))
    severity = {item.code: item.severity for item in
                _report(validate_planning_ir(raw)).findings}
    assert severity.get("FACTION_NO_PRESSURE_PATH") == "WARNING"


# ---------------------------------------------------------------- cross graph
def test_cross_graph_dangling_location_is_an_error() -> None:
    raw = _mutated(lambda data: data["plot_nodes"][1].update({"location_id": "LOC_GHOST"}))
    report = _report(validate_planning_ir(raw))
    assert "CROSS_GRAPH_DANGLING_LOCATION" in report.codes()
    assert report.ok() is False


def test_clean_fixtures_have_no_graph_errors() -> None:
    for name in (BASE, "MODERN_CITY_EXAMPLE.json", "FANTASY_EXAMPLE.json"):
        report = _report(_plan(name))
        assert report.errors() == [], (name, report.errors())


# ---------------------------------------------------------------- projection
def test_projection_is_read_only_and_keeps_source_ids() -> None:
    plan = _plan()
    bundle = build_planning_graphs(plan, revision_id="PREV_2", content_digest="digest-2")
    report = _report(plan)
    before = planning_digest(plan)
    projections = project_bundle(bundle, report=report)
    assert planning_digest(plan) == before
    assert set(projections) == {"location", "relationship", "faction", "combined"}
    location = projections["location"]
    assert location.read_only is True
    assert location.revision_id == "PREV_2"
    assert location.content_digest == "digest-2"
    assert all(node.source_planning_ids for node in location.nodes)
    assert all(edge.non_authoritative is True for edge in location.edges)
    assert location.findings
    sliced = project_graph(bundle.location, node_ids=["LOC_TOWN"])
    assert [node.id for node in sliced.nodes] == ["LOC_TOWN"]
    assert sliced.edges == []
    assert not hasattr(location, "save")


def test_graph_summary_answers_counts_and_risks() -> None:
    plan = _plan()
    summary = summarize_graphs(plan, revision_id="PREV_3")
    assert summary.location_count == 2
    assert summary.route_count == 1
    assert summary.reachable_regions == 2
    assert summary.isolated_regions == 0
    assert summary.relationship_count == 1
    assert summary.faction_count == 1
    assert summary.severity_counts["ERROR"] == 0
    assert summary.read_only is True
    combined = summarize_plan(plan, revision_id="PREV_3", with_graph=True)
    assert combined.graph is not None and combined.graph.location_count == 2
    assert summarize_plan(plan).graph is None


def test_faction_pressure_query_is_read_only() -> None:
    raw = _mutated(lambda data: (
        data["factions"][0].update({"territory": ["LOC_BRIDGE"], "enemies": []}),
        data["plot_nodes"][1].update({"participants": ["CHAR_LIN", "FACTION_TOWN"]})))
    plan = validate_planning_ir(raw)
    rows = faction_pressure_candidates(plan, "LOC_BRIDGE")
    assert [row["faction_id"] for row in rows] == ["FACTION_TOWN"]
    assert "territory" in rows[0]["reasons"]
    assert rows[0]["non_authoritative"] is True
    assert faction_pressure_candidates(plan, "LOC_UNKNOWN") == []


# ---------------------------------------------------------------- context integration
def test_context_graph_slices_only_include_needed_nodes() -> None:
    plan = _plan()
    bundle = build_planning_graphs(plan, revision_id="PREV_4", content_digest="digest-4")
    builder = StoryPlanningContextBuilder(plan, revision_id="PREV_4",
                                          content_digest="digest-4", graphs=bundle)
    location = builder.build("location")
    assert {node["id"] for node in location.payload["graph"]["nodes"]} == {"LOC_BRIDGE",
                                                                          "LOC_TOWN"}
    faction = builder.build("faction")
    assert [node["id"] for node in faction.payload["graph"]["nodes"]] == ["FACTION_TOWN"]
    plot = builder.build("plot")
    assert plot.payload["graph"]["nodes"]
    assert all(node["id"].startswith(("LOC_", "CHAR_", "FACTION_"))
               for node in plot.payload["graph"]["nodes"])
    assert "graph" not in builder.build("chapter_planning").payload
    assert "graph" not in StoryPlanningContextBuilder(plan).build("location").payload


def test_graph_modules_have_no_genre_or_wasteland_hardcoding() -> None:
    offenders: list[str] = []
    for name in ("graphs.py", "graph_validator.py", "graph_projection.py"):
        text = (GRAPH_DIR / name).read_text(encoding="utf-8")
        for term in ("wasteland", "废土", "xianxia", "修仙", "爽文", "if novel_id =="):
            if term in text:
                offenders.append(f"{name}: {term}")
    assert offenders == []
