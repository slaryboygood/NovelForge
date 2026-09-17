"""M2B：Validation / Builder / Context / Projection / Proposal 服务回归。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from novelforge.story_engine.planning import (
    CONTEXT_PURPOSES,
    PlanningProposalError,
    PlanningRepository,
    PlanningValidationService,
    StoryPlanningBuilder,
    StoryPlanningContextBuilder,
    assert_no_future_content,
    build_canon_bootstrap_proposal,
    build_story_state_init_proposal,
    planning_digest,
    summarize_plan,
    validate_planning_ir,
)

FIXTURE = Path("tests/fixtures/planning_ir/ONE_SENTENCE_EXAMPLE.json")


def _raw() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def _plan(**overrides):
    raw = _raw()
    raw.update(overrides)
    return validate_planning_ir(raw)


def _repo_with_revision(tmp_path: Path, plan=None):
    repo = PlanningRepository(tmp_path, "demo_001")
    record = repo.create(plan or _plan(), status="proposed")
    return repo, record


def _service(repo: PlanningRepository) -> PlanningValidationService:
    return PlanningValidationService(repo, known_entity_ids=["ENTITY_PROTAGONIST"])


# ---------------------------------------------------------------- validation
def test_validation_service_accepts_clean_revision(tmp_path: Path) -> None:
    repo, record = _repo_with_revision(tmp_path)
    report = _service(repo).validate_revision(record.revision_id)
    assert report.ok(), report.findings
    assert report.digest_ok is True
    assert report.planning_id == record.planning_id
    assert report.codes() == []


def test_validation_service_reports_broken_refs_and_spine_cycle(tmp_path: Path) -> None:
    raw = _raw()
    raw["arcs"][0]["plot_nodes"].append("NODE_GHOST")
    raw["spine"]["edges"].append({"from_node_id": "NODE_CLIMAX", "to_node_id": "NODE_ACCEPT",
                                  "relation": "causes"})
    repo, record = _repo_with_revision(tmp_path, validate_planning_ir(raw))
    codes = _service(repo).validate_revision(record.revision_id).codes()
    assert "PLANNING_REF_UNKNOWN" in codes
    assert "SPINE_CYCLE" in codes


def test_validation_service_reports_detail_level_and_execution_volume(tmp_path: Path) -> None:
    raw = _raw()
    raw["arcs"][0]["detail_level"] = "chapter_ready"
    raw["arcs"][0]["decision_chain"] = []
    raw["volumes"].append({"volume_id": "VOL_TWO", "index": 2, "title": "第二卷",
                           "major_nodes": ["NODE_FAIL"], "chapter_budget": 40})
    raw["plot_nodes"][1]["scheduled_volume_id"] = "VOL_BRIDGE"
    repo, record = _repo_with_revision(tmp_path, validate_planning_ir(raw))
    codes = _service(repo).validate_revision(record.revision_id).codes()
    assert "ARC_DETAIL_LEVEL_INCOMPLETE" in codes
    assert "PLOT_NODE_EXECUTION_VOLUME_AMBIGUOUS" in codes


def test_validation_service_detects_missing_branch_head(tmp_path: Path) -> None:
    repo, record = _repo_with_revision(tmp_path)
    payload = json.loads(repo.index_path.read_text(encoding="utf-8"))
    payload["branches"] = {}
    repo.index_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    codes = _service(repo).validate_revision(record.revision_id).codes()
    assert "BRANCH_HEAD_UNKNOWN" in codes


def test_validation_service_detects_tampered_content(tmp_path: Path) -> None:
    repo, record = _repo_with_revision(tmp_path)
    path = repo.revision_path(record.revision_id)
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["revision"]["plan"]["title"] = "手改标题"
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    report = _service(repo).validate_revision(record.revision_id)
    assert report.digest_ok is False
    assert "PLANNING_CONTENT_DIGEST_MISMATCH" in report.codes()


def test_validation_service_checks_lineage_against_previous(tmp_path: Path) -> None:
    repo, first = _repo_with_revision(tmp_path)
    second = repo.create(_plan(logline="第二版"), status="proposed")
    report = _service(repo).validate_revision(second.revision_id,
                                              previous_revision_id=first.revision_id)
    assert report.ok(), report.findings
    assert [row.revision for row in repo.lineage(second.revision_id)] == [1, 2]


# ---------------------------------------------------------------- builder
def test_builder_assembles_spine_defaults_and_revision(tmp_path: Path) -> None:
    source = _plan()
    builder = StoryPlanningBuilder(novel_id="demo_001", title="装配测试",
                                   logline="确定性装配")
    builder.with_plot_nodes(source.plot_nodes).with_volumes(source.volumes) \
        .with_arcs(source.arcs).with_timeline(source.timeline).with_pacing(source.pacing) \
        .with_characters(source.characters).with_character_arcs(source.character_arcs) \
        .with_relationship_arcs(source.relationship_arcs).with_factions(source.factions) \
        .with_faction_arcs(source.faction_arcs).with_locations(source.locations) \
        .with_location_graph(source.location_graph) \
        .with_information_arcs(source.information_arcs) \
        .with_foreshadow_plans(source.foreshadow_plans) \
        .with_progression_tracks(source.progression_tracks)
    builder.apply_defaults()
    assert builder.spine is not None
    assert {edge.relation for edge in builder.spine.edges} == {"requires"}
    assert builder.volumes[0].arc_ids == ["ARC_BRIDGE"]
    assert [entry.sequence_order for entry in builder.timeline.story_timeline] == [0, 1]
    repo = PlanningRepository(tmp_path, "demo_001")
    record = builder.build_revision(repo, status="draft", note="builder")
    report = _service(repo).validate_revision(record.revision_id)
    assert report.ok(), report.findings
    assert record.plan.planning_id.startswith("PLAN_")


def test_builder_keeps_author_ids_and_provenance() -> None:
    source = _plan()
    builder = StoryPlanningBuilder(novel_id="demo_001", planning_id=source.planning_id)
    builder.with_intent(source.intent).with_characters(source.characters)
    plan = builder.build()
    assert plan.planning_id == source.planning_id
    assert plan.characters[0].provenance == "supplied"
    assert plan.characters[0].character_id == "CHAR_LIN"


# ---------------------------------------------------------------- context
def test_context_slices_only_the_needed_objects(tmp_path: Path) -> None:
    repo, record = _repo_with_revision(tmp_path)
    builder = StoryPlanningContextBuilder(record.plan, revision_id=record.revision_id,
                                          content_digest=record.content_digest)
    world = builder.build("world")
    assert set(world.payload) == {"intent", "theme", "world"}
    plot = builder.build("plot")
    assert set(plot.payload) == {"intent", "theme", "plot_nodes", "spine"}
    character = builder.build("character", ids=["CHAR_LIN"])
    assert [item["character_id"] for item in character.payload["characters"]] == ["CHAR_LIN"]
    arc = builder.build("arc", ids=["ARC_BRIDGE"])
    assert arc.payload["arcs"][0]["arc_id"] == "ARC_BRIDGE"
    assert {node["node_id"] for node in arc.payload["plot_nodes"]} >= {"NODE_ACCEPT", "NODE_FAIL"}
    chapter = builder.build("chapter_planning")
    assert chapter.payload["planning_gaps"]
    assert set(builder.build_many(CONTEXT_PURPOSES)) == set(CONTEXT_PURPOSES)


def test_context_declares_boundary_and_provenance(tmp_path: Path) -> None:
    repo, record = _repo_with_revision(tmp_path)
    context = StoryPlanningContextBuilder(record.plan, revision_id=record.revision_id,
                                          content_digest=record.content_digest).build("timeline")
    assert context.boundary == "planning_future_not_happened"
    assert context.provenance == "planning"
    assert context.planning_revision_id == record.revision_id
    assert context.content_digest == record.content_digest
    assert context.canon_snapshot_digest == record.plan.canon_snapshot_digest
    assert "plot" in context.excluded_domains
    assert context.included_ids
    with pytest.raises(ValueError):
        StoryPlanningContextBuilder(record.plan).build("unknown_purpose")


# ---------------------------------------------------------------- projection
def test_projection_is_read_only_and_does_not_change_plan(tmp_path: Path) -> None:
    repo, record = _repo_with_revision(tmp_path)
    before = planning_digest(record.plan)
    summary = summarize_plan(record.plan, revision_id=record.revision_id,
                             content_digest=record.content_digest)
    assert planning_digest(record.plan) == before
    assert summary.read_only is True
    assert summary.spine.node_count == 3
    assert summary.spine.edge_count == 2
    assert summary.location_graph.location_count == 2
    assert summary.coverage["arcs"] == 1
    assert summary.completeness["spine_causal"] == 1.0
    assert not hasattr(summary, "save")


# ---------------------------------------------------------------- proposals
def test_canon_bootstrap_proposal_contains_only_baseline(tmp_path: Path) -> None:
    repo, record = _repo_with_revision(tmp_path)
    proposal = build_canon_bootstrap_proposal(record.plan, revision_id=record.revision_id)
    payload = proposal.model_dump(mode="json")
    assert proposal.require_confirmation is True
    assert proposal.applied is False
    assert proposal.planning_revision_id == record.revision_id
    assert "RULE_RUMOR" in proposal.excluded_non_baseline
    assert proposal.future_refs_excluded
    assert_all_future_excluded(proposal.future_refs_excluded, payload)
    assert_no_future_content("CanonBootstrapProposal", payload)
    strict = build_canon_bootstrap_proposal(record.plan, require_confirmed=True)
    assert strict.facts == []
    assert strict.entities == []


def test_story_state_init_proposal_has_no_future_and_no_inventory(tmp_path: Path) -> None:
    repo, record = _repo_with_revision(tmp_path)
    proposal = build_story_state_init_proposal(record.plan, revision_id=record.revision_id,
                                               starting_location_ids=["LOC_TOWN"])
    payload = proposal.model_dump(mode="json")
    assert proposal.resources == []
    assert proposal.location_ids == ["LOC_TOWN"]
    assert [item.character_id for item in proposal.characters] == ["CHAR_LIN", "CHAR_MA"]
    assert proposal.knowledge == []
    assert proposal.future_refs_excluded
    assert_all_future_excluded(proposal.future_refs_excluded, payload)
    assert_no_future_content("StoryStateInitProposal", payload)


def test_proposal_guard_rejects_future_payload() -> None:
    with pytest.raises(PlanningProposalError) as error:
        assert_no_future_content("X", {"plot_nodes": ["NODE_A"]})
    assert error.value.code == "FUTURE_IN_PROPOSAL"


def assert_all_future_excluded(future_ids: list[str], payload: dict) -> None:
    """proposal payload 里不得出现任何未来对象的 stable id。"""

    body = {key: value for key, value in payload.items() if key != "future_refs_excluded"}
    blob = json.dumps(body, ensure_ascii=False)
    leaked = [identifier for identifier in future_ids if identifier in blob]
    assert leaked == [], leaked
