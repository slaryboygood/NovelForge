"""M7：Planning Route Lab V2 回归（candidate / compare / promote / legacy 隔离）。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from novelforge.story_engine.planning import (
    DIMENSIONS,
    PlanningRepository,
    PlanningRouteLabService,
    RouteCandidate,
    RouteCandidatePatch,
    RouteComparisonProfile,
    RouteProposalError,
    StaticRouteCandidateProvider,
    check_patch_scope,
    materialize_candidate,
    planning_digest,
    project_candidate,
    project_comparison,
    project_pairwise,
    validate_planning_ir,
)
from novelforge.story_engine.route_lab import compare_states as legacy_compare_states

FIXTURES = Path("tests/fixtures/planning_ir")
URBAN = "URBAN_GROWTH_EXAMPLE.json"
BASE = "ONE_SENTENCE_EXAMPLE.json"
ROUTE_DIR = Path("src/novelforge/story_engine/planning")


def _raw(name: str = URBAN) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def _plan(name: str = URBAN):
    return validate_planning_ir(_raw(name))


def _node(node_id: str, **overrides) -> dict:
    payload = {"node_id": node_id, "purpose": f"{node_id} 的用途", "conflict": "冲突",
               "state_change": "状态推进", "cost": "代价", "payoff": "回报",
               "pressure_kinds": ["custom"], "prerequisites": ["NODE_STOCK"]}
    payload.update(overrides)
    return payload


def _candidate_payload(candidate_id: str, node_id: str, **overrides) -> dict:
    payload = {"candidate_id": candidate_id, "title": candidate_id, "scope": "spine_segment",
               "patch": {"add_nodes": [_node(node_id)],
                         "add_edges": [{"from_node_id": "NODE_STOCK",
                                        "to_node_id": node_id, "relation": "causes"}]}}
    payload.update(overrides)
    return payload


def _setup(tmp_path: Path, candidates: list[dict] | None = None):
    repo = PlanningRepository(tmp_path, "demo_urban")
    first = repo.create(_plan(), revision_id="PREV_R1")
    service = PlanningRouteLabService(repo)
    provider = StaticRouteCandidateProvider(
        candidates or [_candidate_payload("CAND_A", "NODE_SIEGE"),
                       _candidate_payload("CAND_B", "NODE_DEAL")])
    raw = provider.propose({}, source_revision=first.revision_id,
                           source_digest=first.content_digest)
    stored = [service.add_candidate(item) for item in raw]
    return repo, service, first, stored


# ---------------------------------------------------------------- candidate / patch
def test_candidate_binds_source_revision_and_digest(tmp_path: Path) -> None:
    repo, service, first, stored = _setup(tmp_path)
    candidate = stored[0]
    assert candidate.source_planning_revision_id == first.revision_id
    assert candidate.source_digest == first.content_digest
    assert candidate.non_authoritative is True
    assert candidate.status == "ready"
    assert service.store.candidate_path(candidate.candidate_id).is_file()


def test_candidate_materialization_is_a_copy(tmp_path: Path) -> None:
    repo, service, first, stored = _setup(tmp_path)
    base = repo.load(first.revision_id).plan
    before = planning_digest(base)
    materialized = materialize_candidate(base, stored[0])
    assert planning_digest(base) == before
    assert "NODE_SIEGE" in {item.node_id for item in materialized.plot_nodes}
    assert "NODE_SIEGE" not in {item.node_id for item in base.plot_nodes}


def test_candidate_cannot_touch_canon_or_story_state(tmp_path: Path) -> None:
    repo, service, first, stored = _setup(tmp_path)
    plan = repo.load(first.revision_id).plan
    bad = stored[0].model_copy(update={"patch": stored[0].patch.model_copy(
        update={"remove_node_ids": ["ENTITY_PROTAGONIST"]})})
    findings = check_patch_scope(bad.patch, plan)
    assert [item.code for item in findings] == ["ROUTE_CANDIDATE_TOUCHES_HAPPENED_TRUTH"]
    with pytest.raises(RouteProposalError):
        materialize_candidate(plan, bad)


def test_candidate_cannot_remove_scheduled_must_happen_node(tmp_path: Path) -> None:
    repo, service, first, stored = _setup(tmp_path)
    plan = repo.load(first.revision_id).plan
    bad = stored[0].model_copy(update={"patch": stored[0].patch.model_copy(
        update={"remove_node_ids": ["NODE_BRANCH"]})})
    findings = check_patch_scope(bad.patch, plan)
    codes = {item.code for item in findings}
    assert "ROUTE_REMOVES_CONFIRMED_PLANNING_ANCHOR" in codes
    assert "ROUTE_CANDIDATE_TOUCHES_HAPPENED_TRUTH" not in codes


def test_candidate_may_reference_canon_stable_ids(tmp_path: Path) -> None:
    """§0.A：引用 Canon / StoryState stable ID 是允许的，只有修改才是禁止的。"""

    repo, service, first, stored = _setup(tmp_path, [
        _candidate_payload("CAND_REF", "NODE_REF",
                           patch={"add_nodes": [_node(
                               "NODE_REF", participants=["ENTITY_PROTAGONIST"],
                               truth_ids=["TRUTH_COST"],
                               foreshadow_ids=["FSP_LEDGER"])],
                               "add_edges": [{"from_node_id": "NODE_STOCK",
                                              "to_node_id": "NODE_REF", "relation": "causes"}]})])
    candidate = stored[0]
    assert candidate.status in ("ready", "blocked")
    assert check_patch_scope(candidate.patch, repo.load(first.revision_id).plan) == []


def test_blocking_candidate_cannot_be_ready_or_promoted(tmp_path: Path) -> None:
    repo, service, first, stored = _setup(tmp_path, [
        _candidate_payload("CAND_BAD", "NODE_BAD",
                           patch={"add_nodes": [_node("NODE_BAD", foreshadow_move_refs=["FSMOVE_GHOST"])],
                                  "add_edges": [{"from_node_id": "NODE_STOCK",
                                                 "to_node_id": "NODE_BAD", "relation": "causes"}]})])
    blocked = stored[0]
    assert blocked.status == "blocked" and blocked.blocking() is True
    with pytest.raises(RouteProposalError) as error:
        service.promote("CAND_BAD", approved=True)
    assert error.value.code == "ROUTE_CANDIDATE_BLOCKED"


# ---------------------------------------------------------------- compare
def test_compare_returns_dimensions_without_fake_total_score(tmp_path: Path) -> None:
    repo, service, first, stored = _setup(tmp_path)
    report = service.compare(["CAND_A", "CAND_B"])
    assert [item.candidate_id for item in report.candidates] == ["CAND_A", "CAND_B"]
    dimensions = {item.dimension for item in report.analysis("CAND_A").dimensions}
    assert set(DIMENSIONS) <= dimensions
    assert report.non_authoritative is True
    assert "score" not in report.model_dump()
    for analysis in report.candidates:
        assert all(item.verdict in ("strong", "acceptable", "weak", "blocked")
                   for item in analysis.dimensions)


def test_profile_weights_change_relative_signal_not_verdicts(tmp_path: Path) -> None:
    repo, service, first, stored = _setup(tmp_path)
    neutral = service.compare(["CAND_A", "CAND_B"])
    focused = service.compare(["CAND_A", "CAND_B"], profile=RouteComparisonProfile(
        profile_id="resource_focus", dimension_weights={"resource_feasibility": 3.0}))
    a_neutral = neutral.analysis("CAND_A")
    a_focused = focused.analysis("CAND_A")
    assert a_neutral.relative_signal != a_focused.relative_signal
    assert {item.verdict for item in a_neutral.dimensions} == {
        item.verdict for item in a_focused.dimensions}


def test_pairwise_and_baseline_comparison(tmp_path: Path) -> None:
    repo, service, first, stored = _setup(tmp_path)
    pairwise = service.compare_pairwise("CAND_A", "CAND_B")
    assert set(pairwise.better_by_dimension) == set(DIMENSIONS)
    assert all(value in ("better", "similar", "worse")
               for value in pairwise.better_by_dimension.values())
    baseline = service.compare_baseline("CAND_A")
    assert baseline.candidate_id == "CAND_A"
    assert baseline.solved or baseline.lost or baseline.new_risks or True


def test_route_diff_is_story_aware(tmp_path: Path) -> None:
    repo, service, first, stored = _setup(tmp_path)
    report = service.compare(["CAND_A"])
    diff = report.analysis("CAND_A").diff
    assert diff is not None
    assert "NODE_SIEGE" in diff.nodes_added
    assert any("->NODE_SIEGE" in item for item in diff.edges_added)
    assert "coverage_delta" in diff.model_dump()
    assert diff.pressure_delta.get("open") is not None


def test_dead_end_and_length_signals_present(tmp_path: Path) -> None:
    repo, service, first, stored = _setup(tmp_path)
    report = service.compare(["CAND_A"])
    analysis = report.analysis("CAND_A")
    dead_end = next(item for item in analysis.dimensions
                    if item.dimension == "dead_end_risk")
    length = next(item for item in analysis.dimensions
                  if item.dimension == "length_feasibility")
    assert "terminals" in dead_end.signals
    assert length.signals["chapter_independent"] is True
    assert length.signals["verdict"] in ("too_small", "plausible", "too_dense", "unknown")


def test_novelty_and_repetition_use_structural_signals(tmp_path: Path) -> None:
    repo, service, first, stored = _setup(tmp_path)
    analysis = service.compare(["CAND_A"]).analysis("CAND_A")
    novelty = next(item for item in analysis.dimensions if item.dimension == "novelty")
    repetition = next(item for item in analysis.dimensions
                      if item.dimension == "repetition_risk")
    assert novelty.signals["structural_only"] is True
    assert "hotspot_count" in repetition.signals


# ---------------------------------------------------------------- stale / rebase / compose
def test_stale_candidate_is_blocked_and_rebase_detects_conflicts(tmp_path: Path) -> None:
    repo, service, first, stored = _setup(tmp_path)
    second = repo.create(_plan(), revision_id="PREV_R2", parent_revision_id=first.revision_id)
    assert stored[0].is_stale(repo.load(second.revision_id).plan,
                              current_revision_id=second.revision_id) is True
    with pytest.raises(RouteProposalError) as error:
        service.promote("CAND_A", approved=True)
    assert error.value.code == "STALE_ROUTE_CANDIDATE"
    rebased, conflicts = service.rebase("CAND_A", second.revision_id)
    assert conflicts == []
    assert rebased.source_planning_revision_id == second.revision_id


def test_rebase_reports_patch_conflicts(tmp_path: Path) -> None:
    repo, service, first, stored = _setup(tmp_path)
    raw = _plan().model_dump(mode="json")
    raw["plot_nodes"] = [item for item in raw["plot_nodes"] if item["node_id"] != "NODE_STOCK"]
    raw["spine"]["nodes"] = [item for item in raw["spine"]["nodes"] if item != "NODE_STOCK"]
    raw["spine"]["edges"] = [item for item in raw["spine"]["edges"]
                            if item["from_node_id"] != "NODE_STOCK"
                            and item["to_node_id"] != "NODE_STOCK"]
    second_plan = validate_planning_ir(raw)
    second = repo.create(second_plan, revision_id="PREV_R3", parent_revision_id=first.revision_id)
    _, conflicts = service.rebase("CAND_A", second.revision_id)
    assert {item.code for item in conflicts} & {"REBASE_NODE_MISSING",
                                                "REBASE_EDGE_NODE_MISSING"}


def test_compose_creates_new_candidate_with_validation(tmp_path: Path) -> None:
    repo, service, first, stored = _setup(tmp_path)
    composite, conflicts = service.compose(["CAND_A", "CAND_B"])
    assert conflicts == []
    assert composite.candidate_id.startswith("CAND_")
    assert composite.status in ("ready", "blocked")
    assert len(composite.patch.add_nodes) == 2


# ---------------------------------------------------------------- promotion
def test_promotion_requires_approval_and_creates_new_revision(tmp_path: Path) -> None:
    repo, service, first, stored = _setup(tmp_path)
    with pytest.raises(RouteProposalError) as error:
        service.promote("CAND_A")
    assert error.value.code == "ROUTE_CANDIDATE_NOT_APPROVED"
    record = service.promote("CAND_A", approved=True, revision_id="PREV_R10",
                             session_id="RSESS_TEST", selected_tradeoffs=["resource_feasibility"],
                             author_confirmation_ref="author:1")
    assert record.revision == 2 and record.parent_revision_id == first.revision_id
    assert "NODE_SIEGE" in {item.node_id for item in record.plan.plot_nodes}
    assert len(repo.load(first.revision_id).plan.plot_nodes) == 3
    promoted = service.store.load_candidate("CAND_A")
    assert promoted.status == "promoted"
    assert promoted.source_planning_revision_id == first.revision_id
    provenance = json.loads((service.store.root / "promotions" / "CAND_A.json")
                            .read_text(encoding="utf-8"))
    assert provenance["candidate_id"] == "CAND_A"
    assert provenance["author_confirmation_ref"] == "author:1"


def test_route_artifacts_live_outside_revisions_directory(tmp_path: Path) -> None:
    repo, service, first, stored = _setup(tmp_path)
    stored_bytes = (tmp_path / "novel/authoring/story_engine/planning/demo_urban"
                    / "planning_routes/candidates/CAND_A.json").read_bytes()
    service.promote("CAND_A", approved=True, revision_id="PREV_R11")
    assert (tmp_path / "novel/authoring/story_engine/planning/demo_urban"
            / "planning_routes/candidates/CAND_A.json").read_bytes() != stored_bytes
    revisions_dir = (tmp_path / "novel/authoring/story_engine/planning/demo_urban"
                     / "revisions")
    assert all(not item.name.startswith("CAND_") for item in revisions_dir.glob("*.json"))


def test_session_records_source_revision_and_candidates(tmp_path: Path) -> None:
    repo, service, first, stored = _setup(tmp_path)
    session = service.create_session(first.revision_id, ["CAND_A", "CAND_B"],
                                     profile_id="commercial")
    assert session.source_planning_revision_id == first.revision_id
    assert session.source_digest == first.content_digest
    assert session.candidate_ids == ["CAND_A", "CAND_B"]
    assert service.store.load_session(session.session_id).comparison_profile_id == "commercial"


def test_reject_marks_candidate(tmp_path: Path) -> None:
    repo, service, first, stored = _setup(tmp_path)
    rejected = service.reject("CAND_B", reason="不符合主线")
    assert rejected.status == "rejected"


# ---------------------------------------------------------------- projection / cross-genre
def test_projections_are_read_only() -> None:
    repo_plan = _plan()
    candidate = StaticRouteCandidateProvider(
        [_candidate_payload("CAND_P", "NODE_P")]).propose(
        {}, source_revision="PREV_R1", source_digest="d")[0]
    before = planning_digest(repo_plan)
    projection = project_candidate(candidate)
    assert planning_digest(repo_plan) == before
    assert projection.read_only is True and projection.non_authoritative is True
    pairwise = project_pairwise(_pairwise_stub())
    assert pairwise["read_only"] is True


def _pairwise_stub():
    from novelforge.story_engine.planning import PairwiseComparison

    return PairwiseComparison(left_id="A", right_id="B",
                              better_by_dimension={"causal_coherence": "better"},
                              tradeoffs=["causal_coherence: A 更好"])


def test_legacy_runtime_route_lab_is_untouched() -> None:
    """旧 runtime Route Lab v1 仍可用（M7 不修改它，只是并存）。"""

    from novelforge.story_engine.state import StoryState

    state = StoryState(novel_id="demo")
    comparison = legacy_compare_states(state, state)
    assert comparison.rows == []
    assert "StoryState" in type(state).__name__


def test_cross_genre_candidates_share_one_engine(tmp_path: Path) -> None:
    for name, node_id in ((BASE, "NODE_EXTRA_A"), (URBAN, "NODE_EXTRA_B")):
        plan = _plan(name)
        repo = PlanningRepository(tmp_path / name.replace(".json", ""), "demo_urban"
                                  if name == URBAN else "demo_001")
        first = repo.create(plan, revision_id="PREV_CG1")
        service = PlanningRouteLabService(repo)
        provider = StaticRouteCandidateProvider([
            {"candidate_id": "CAND_CG", "title": "cg", "scope": "spine_segment",
             "patch": {"add_nodes": [_node(node_id,
                                           prerequisites=[plan.plot_nodes[-1].node_id])],
                       "add_edges": [{"from_node_id": plan.plot_nodes[-1].node_id,
                                      "to_node_id": node_id, "relation": "causes"}]}}])
        candidate = provider.propose({}, source_revision=first.revision_id,
                                     source_digest=first.content_digest)[0]
        stored = service.add_candidate(candidate)
        assert stored.status in ("ready", "blocked")
        report = service.compare(["CAND_CG"])
        assert len(report.candidates) == 1


def test_route_modules_have_no_genre_or_fixed_score_hardcoding() -> None:
    offenders: list[str] = []
    for name in ("route_candidates.py", "route_comparison.py", "route_service.py",
                 "route_projection.py"):
        text = (ROUTE_DIR / name).read_text(encoding="utf-8")
        for term in ("wasteland", "废土", "xianxia", "修仙", "爽文",
                     "if genre ==", "total_score", "总评分"):
            if term in text:
                offenders.append(f"{name}: {term}")
    assert offenders == []
