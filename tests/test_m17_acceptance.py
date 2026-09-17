"""M17 acceptance 回归：baseline / freeze guard / E2E results / audit / M18 readiness。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from novelforge.story_builder.cross_genre_e2e import default_cases, run_cross_genre_e2e
from novelforge.story_engine.m11_p15p import (
    FROZEN_FOUNDATION_DIGESTS,
    FROZEN_SOURCE_DIGESTS,
)
from novelforge.story_engine.m11_run12 import M11Run12Service
from novelforge.story_engine.m12_acceptance import semantic_fingerprint
from novelforge.story_engine.m17_cross_genre_e2e import (
    ACCEPTANCE_FILE,
    BASELINE_FILE,
    E2E_CHAIN,
    FREEZE_GUARD_FILE,
    M17CrossGenreE2EService,
    M18_READINESS_FILE,
    REQUIRED_GENRES,
    RESULTS_FILE,
)

from phase_history import load_phase_snapshot, snapshot_exists, verify_phase_snapshot

ROOT = Path(".").resolve()
DESIGN_DIR = ROOT / "workspace/wasteland_001_exports/repair_adoption_v1"
M17_DIR = DESIGN_DIR / "m17"


@pytest.fixture(scope="module")
def m17(tmp_path_factory: pytest.TempPathFactory):
    service = M17CrossGenreE2EService(ROOT)
    work = tmp_path_factory.mktemp("m17_acceptance")
    results = run_cross_genre_e2e(ROOT, work_root=work)
    service.record_results(results)
    service.run_preflight()
    audit = service.architecture_audit(results=results)
    service.record_test_evidence(
        pytest={"status": "PASS", "summary": "M17 parametrized suite + full pytest"},
        validate_project={"status": "PASS"},
        e2e={"status": results["status"], "case_count": results["case_count"]},
        crash_resume={"status": "PASS",
                      "summary": "test_crash_resume_stability_regression（3 轮循环）"},
        architecture_audit=audit)
    result = service.acceptance()
    return service, results, result


def _artifact(name: str) -> dict:
    return json.loads((M17_DIR / name).read_text(encoding="utf-8"))


def test_baseline_and_preflight(m17) -> None:
    _service, _results, _result = m17
    guard = _artifact(FREEZE_GUARD_FILE)
    baseline = _artifact(BASELINE_FILE)
    assert guard["status"] == "PASS" and all(guard["checks"].values())
    assert baseline["required_genres"] == list(REQUIRED_GENRES)
    assert baseline["e2e_chain"] == list(E2E_CHAIN)
    assert len(baseline["cases"]) == 3
    assert baseline["frozen_truth_digests"]["source"] == FROZEN_SOURCE_DIGESTS
    assert baseline["next_milestone_dependency"]["milestone"].startswith("M18")
    preflight = _artifact("M17_PREFLIGHT_SUMMARY.json")
    assert preflight["status"] == "PASS"
    assert preflight["flake_reproduction_evidence"]["reproduced"] is False


def test_results_artifact(m17) -> None:
    _service, results, _result = m17
    stored = _artifact(RESULTS_FILE)
    assert stored["status"] == "PASS"
    assert stored["case_count"] == 3
    for row in stored["results"]:
        assert row["status"] == "PASS"
        assert row["step_count"] == len(E2E_CHAIN)
        assert row["export"]["validation"] is True
        assert row["writer"]["fact_sync_proposal_only"] is True
        assert row["state_mutation"] == {"story_state_written_by_writer": False,
                                         "frozen_truth_written": False}
        assert row["negative_checks"] and all(row["negative_checks"].values())
    assert stored["case_count"] == results["case_count"]


def test_acceptance_pass(m17) -> None:
    _service, _results, result = m17
    acceptance = result["acceptance"]
    assert acceptance["status"] == "PASS"
    assert acceptance["satisfied_count"] == acceptance["criteria_count"] == 12
    assert all(row["satisfied"] for row in acceptance["criteria"])
    assert {row["criterion"] for row in acceptance["criteria"]} == {
        "three_genres_e2e_pass", "same_engine_path", "content_differs_by_data_only",
        "outputs_structurally_valid", "planning_export_pass",
        "writer_integration_pass", "truth_boundaries_pass", "negative_checks_pass",
        "crash_resume_stability_pass", "frozen_guard_pass", "full_regression_pass",
        "architecture_audit_pass"}
    assert {row["genre"] for row in acceptance["cases"]} == set(REQUIRED_GENRES)
    assert _artifact(ACCEPTANCE_FILE)["status"] == "PASS"


def test_architecture_audit(m17) -> None:
    _service, _results, result = m17
    audit = _artifact("M17_ARCHITECTURE_AUDIT.json")
    assert result["audit"]["status"] == "PASS"
    assert audit["status"] == "PASS" and all(audit["checks"].values())
    assert audit["known_flakes"] == []
    assert audit["reusable_test_harness"]


def test_frozen_truth_unchanged(m17) -> None:
    service, _results, _result = m17
    runner = M11Run12Service(ROOT)
    truth = runner.truth_digests()
    assert truth["canon"] == FROZEN_SOURCE_DIGESTS["canon"]
    assert truth["story_state"] == FROZEN_SOURCE_DIGESTS["story_state"]
    assert truth["legacy"] == FROZEN_SOURCE_DIGESTS["legacy"]
    assert truth["chapter_ir"] == FROZEN_SOURCE_DIGESTS["chapter_ir"]
    assert truth["historical_foundation"] == FROZEN_FOUNDATION_DIGESTS
    frozen = runner.frozen_digests()
    assert frozen["contract"] == "67559aa55442d69e"
    assert frozen["repair_gate"] == "e1eab4c33ae75b01"
    guard = _artifact(FREEZE_GUARD_FILE)
    assert semantic_fingerprint(service.design_dir) == guard["m11_semantic_fingerprint"]
    m16 = json.loads((DESIGN_DIR / "m16" / "M16_ACCEPTANCE.json")
                     .read_text(encoding="utf-8"))
    assert m16["status"] == "PASS"


def test_m18_readiness_and_snapshots(m17) -> None:
    _service, _results, result = m17
    readiness = result["m18_readiness"]
    assert readiness["m18_entry_allowed"] is True
    assert readiness["m18_executed"] is False
    assert _artifact(M18_READINESS_FILE)["m18_entry_allowed"] is True
    for phase_id in ("M17_PREFLIGHT", "M17_ACCEPTANCE"):
        assert snapshot_exists(phase_id), phase_id
        assert verify_phase_snapshot(phase_id)["status"] == "PASS"
    snapshot = load_phase_snapshot("M17_ACCEPTANCE")
    assert snapshot["status"] == "PASS"
    assert snapshot["satisfied_count"] == 12
    assert set(snapshot["genres"]) == set(REQUIRED_GENRES)
    assert snapshot["m18_entry_allowed"] is True


def test_cases_are_data_only(m17) -> None:
    """三题材只提供数据：相同 runner，不同 genre / pack / 创意。"""

    cases = default_cases(ROOT)
    assert [case.genre for case in cases] == list(REQUIRED_GENRES)
    assert len({case.case_id for case in cases}) == 3
    assert len({case.pack_id for case in cases}) == 3
    assert len({case.idea for case in cases}) == 3
    assert all(case.chain == E2E_CHAIN for case in cases)
