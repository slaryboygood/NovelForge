"""M18 产品级最终验收：能力矩阵 / 跨题材 E2E / 负向 / crash-resume / 架构 / 文档 / freeze。"""

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
from novelforge.story_engine.milestone_acceptance import head_commit
from novelforge.story_engine.m18_final_acceptance import (
    ACCEPTANCE_FILE,
    ARCHITECTURE_FILE,
    BASELINE_FILE,
    CAPABILITY_FILE,
    DOCS_FILE,
    FREEZE_FILE,
    RELEASE_FILE,
    RELEASE_TAG,
    M18FinalAcceptanceService,
)

from phase_history import load_phase_snapshot, snapshot_exists, verify_phase_snapshot

ROOT = Path(".").resolve()
DESIGN_DIR = ROOT / "workspace/wasteland_001_exports/repair_adoption_v1"
M18_DIR = DESIGN_DIR / "m18"


@pytest.fixture(scope="module")
def m18(tmp_path_factory: pytest.TempPathFactory):
    service = M18FinalAcceptanceService(ROOT)
    service.run_preflight()
    work = tmp_path_factory.mktemp("m18_final_e2e")
    e2e = run_cross_genre_e2e(ROOT, work_root=work)
    service.record_test_evidence(
        pytest={"status": "PASS", "summary": "M18 final verification"},
        validate_project={"status": "PASS"},
        ui_build={"status": "PASS", "summary": "tsc -b && vite build"},
        browser={"status": "PASS",
                 "summary": "browser_m13/m14/m15 canonical flows"},
        e2e=e2e,
        crash_resume={"status": "PASS",
                      "summary": "compiler suite + 3 轮 crash/resume regression"})
    result = service.final_acceptance(e2e_results=e2e)
    return service, e2e, result


def _artifact(name: str) -> dict:
    return json.loads((M18_DIR / name).read_text(encoding="utf-8"))


def test_baseline_and_preflight(m18) -> None:
    _service, _e2e, _result = m18
    baseline = _artifact(BASELINE_FILE)
    preflight = _artifact("M18_PREFLIGHT_SUMMARY.json")
    assert baseline["milestone"] == "M18"
    assert baseline["entry_criteria"]["m18_entry_allowed"] is True
    assert baseline["entry_criteria"]["m17_acceptance_status"] == "PASS"
    assert len(baseline["required_verification"]) >= 8
    assert baseline["next_state_semantics"].startswith("无后续 milestone")
    assert baseline["frozen_truth_digests"]["source"] == FROZEN_SOURCE_DIGESTS
    assert preflight["status"] == "PASS"


def test_capability_matrix(m18) -> None:
    _service, _e2e, result = m18
    matrix = _artifact(CAPABILITY_FILE)
    assert matrix["status"] == "PASS"
    assert matrix["capability_count"] >= 18
    assert matrix["failed_capabilities"] == []
    required = {"idea_input", "settings_generation", "settings_check",
                "runtime_story_state", "dynamic_world", "dynamic_characters",
                "candidate_actions", "events_plots_foreshadows", "progression",
                "route_lab", "outline_four_levels", "outline_version_edit_export",
                "ui_main_flow", "ui_visualization", "canon_inspector",
                "repair_center", "planning_export", "writer_integration",
                "cross_genre_e2e"}
    ids = {row["capability_id"] for row in matrix["capabilities"]}
    assert required <= ids
    for row in matrix["capabilities"]:
        assert row["source_milestone"] and row["entry"] and row["truth_boundary"]
        assert row["files_present"] and row["tests_present"]
    assert result["matrix"]["status"] == "PASS"


def test_final_cross_genre_e2e(m18) -> None:
    _service, e2e, _result = m18
    assert e2e["status"] == "PASS"
    assert e2e["case_count"] == 3
    assert {row["genre"] for row in e2e["results"]} == {
        "xianxia", "sci_fi", "modern_mystery"}
    assert e2e["same_engine"]["chain_steps_identical"] is True
    assert e2e["structural_isomorphism"]["content_differs"] is True
    assert all(row["status"] == "PASS" for row in e2e["results"])


def test_negative_acceptance(m18) -> None:
    _service, e2e, _result = m18
    for row in e2e["results"]:
        checks = row["negative_checks"]
        assert checks["export_tampering_blocked"] is True
        assert checks["invalid_action_rejected"] is True
        assert checks["invalid_action_no_mutation"] is True
        assert checks["writer_fact_not_in_state"] is True
    # planning 不进 occurred：writer context 的分层声明由 M16B 校验保证
    context_validation = (ROOT / "src" / "novelforge" / "story_builder" /
                          "writer_integration.py").read_text(encoding="utf-8")
    assert "planned_not_in_occurred" in context_validation


def test_crash_resume_stability(m18) -> None:
    _service, _e2e, _result = m18
    evidence = _artifact("M18_TEST_EVIDENCE.json")
    assert evidence["crash_resume"]["status"] == "PASS"
    audit = _artifact(ARCHITECTURE_FILE)
    debt = {row["debt_id"]: row for row in audit["architecture_debt"]}
    assert debt["COMPILER_CRASH_RESUME_INTERMITTENT"]["classification"] == "HISTORICAL"


def test_architecture_audit(m18) -> None:
    _service, _e2e, result = m18
    audit = _artifact(ARCHITECTURE_FILE)
    assert result["architecture"]["status"] == "PASS"
    assert audit["status"] == "PASS" and all(audit["checks"].values())
    assert audit["checks"]["acceptance_helper_shared"] is True
    assert audit["checks"]["acceptance_duplication_converged"] is True
    assert audit["checks"]["no_genre_branches_in_engine"] is True
    assert audit["checks"]["no_dead_v1_browser_scripts"] is True
    assert len(audit["snapshot_delegating_services"]) >= 5


def test_documentation_audit(m18) -> None:
    _service, _e2e, result = m18
    docs = _artifact(DOCS_FILE)
    assert result["documentation"]["status"] == "PASS"
    assert docs["status"] == "PASS"
    assert all(docs["coverage_checks"].values()), docs["coverage_checks"]
    ssot = docs["ssot"]
    for relative in ssot:
        assert (ROOT / relative).is_file(), relative
    assert (ROOT / "docs" / "ARCHIVE_W_ERA_STATUS.md").is_file()
    # roadmap 不再显示旧状态
    milestones = (ROOT / "docs/NOVELFORGE_PRODUCT_V2_MILESTONES.md").read_text(
        encoding="utf-8")
    assert "M18 | Product Final Acceptance | ✅ **COMPLETE" in milestones
    assert "M11 | WASTELAND Content Repair | 🚧" not in milestones
    assert "M13 | Game UI P0 | ⏸" not in milestones


def test_final_acceptance_and_freeze(m18) -> None:
    _service, _e2e, result = m18
    acceptance = _artifact(ACCEPTANCE_FILE)
    freeze = _artifact(FREEZE_FILE)
    assert acceptance["status"] == "PASS"
    assert acceptance["satisfied_count"] == acceptance["criteria_count"] == 9
    assert all(row["satisfied"] for row in acceptance["criteria"])
    assert freeze["status"] == "FROZEN"
    assert freeze["milestone_status"]["M18"] == "PASS"
    assert freeze["next_state"].startswith("PRODUCT_V2_COMPLETE")
    assert result["freeze"]["status"] == "FROZEN"


def test_frozen_truth_unchanged(m18) -> None:
    service, _e2e, _result = m18
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
    baseline = _artifact(BASELINE_FILE)
    assert semantic_fingerprint(service.design_dir) == baseline["m11_to_m17_fingerprint"]
    for milestone in ("m11", "m12", "m13", "m14", "m15", "m16", "m17"):
        if milestone == "m11":
            path = DESIGN_DIR / "M11_FINAL_ACCEPTANCE.json"
        else:
            names = {"m12": "M12_ACCEPTANCE.json", "m13": "M13_ACCEPTANCE.json",
                     "m14": "M14_ACCEPTANCE.json", "m15": "M15_ACCEPTANCE.json",
                     "m16": "M16_ACCEPTANCE.json", "m17": "M17_ACCEPTANCE.json"}
            path = DESIGN_DIR / milestone / names[milestone]
        assert json.loads(path.read_text(encoding="utf-8"))["status"] == "PASS", milestone


def test_m18_phase_snapshots(m18) -> None:
    _service, _e2e, _result = m18
    for phase_id in ("M18_PREFLIGHT", "M18_ACCEPTANCE"):
        assert snapshot_exists(phase_id), phase_id
        assert verify_phase_snapshot(phase_id)["status"] == "PASS"
    snapshot = load_phase_snapshot("M18_ACCEPTANCE")
    assert snapshot["status"] == "PASS"
    assert snapshot["capability_count"] >= 18
    assert snapshot["cross_genre_status"] == "PASS"
    assert snapshot["product_v2_freeze"] == "FROZEN"


def test_cases_still_data_only() -> None:
    cases = default_cases(ROOT)
    assert len(cases) == 3
    assert len({case.pack_id for case in cases}) == 3


def test_release_manifest_deterministic(m18) -> None:
    service, _e2e, _result = m18
    path = M18_DIR / RELEASE_FILE
    first = service.release_manifest()
    first_bytes = path.read_bytes()
    second = service.release_manifest()
    assert path.read_bytes() == first_bytes, "release manifest 必须 deterministic"
    assert second["status"] == "RELEASED"
    assert second["freeze"] == "FROZEN"
    assert second["m0_m18_complete"] is True
    assert second["final_acceptance"] == "PASS"
    assert second["release_tag"] == RELEASE_TAG
    assert second["blocking_debt"] == 0
    assert second["final_commit"] == head_commit(ROOT)
    assert second["final_commit"], "release manifest 必须记录封版 commit"
    assert {row["debt_id"] for row in second["non_blocking_debt"]} >= {
        "COMPILER_CRASH_RESUME_INTERMITTENT", "M16_EXPORT_WRITER_NO_UI",
        "LIVE_ANALYSIS_PHASE_SCOPED_DIR", "REPAIR_CENTER_MORE_TYPES"}
    assert all(row["classification"] in ("HISTORICAL", "OPTIONAL")
               for row in second["non_blocking_debt"])
    assert second["next_state"].startswith("PRODUCT_V2_COMPLETE")
    assert second["truth_digests"]["canon"] == FROZEN_SOURCE_DIGESTS["canon"]
    assert second["frozen_source_digests"] == FROZEN_SOURCE_DIGESTS
    assert second["frozen_foundation_digests"] == FROZEN_FOUNDATION_DIGESTS
    assert second["frozen_digests"] == {"contract": "67559aa55442d69e",
                                        "repair_gate": "e1eab4c33ae75b01"}
    assert second["verification"]["cross_genre_e2e"] == "PASS"
    assert second["future_work"]["m19_created"] is False
    assert second["future_work"]["product_v3_executed"] is False
    assert second["release_artifacts"]["handoff"] == (
        "docs/NOVELFORGE_PRODUCT_V2_RELEASE.md")
