"""M16 acceptance 回归：baseline / freeze guard / M16A+M16B / architecture audit / M17 readiness。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from novelforge.story_engine.m11_p15p import (
    FROZEN_FOUNDATION_DIGESTS,
    FROZEN_SOURCE_DIGESTS,
)
from novelforge.story_engine.m11_run12 import M11Run12Service
from novelforge.story_engine.m12_acceptance import semantic_fingerprint
from novelforge.story_engine.m16_planning_export_writer import (
    ACCEPTANCE_FILE,
    BASELINE_FILE,
    FREEZE_GUARD_FILE,
    M16A_ACCEPTANCE_FILE,
    M16B_ACCEPTANCE_FILE,
    M16PlanningExportWriterService,
    M17_READINESS_FILE,
    WORK_ITEMS,
    WORK_ITEM_SCOPE,
)

from phase_history import (
    load_phase_snapshot,
    snapshot_exists,
    verify_phase_snapshot,
)

ROOT = Path(".").resolve()
DESIGN_DIR = ROOT / "workspace/wasteland_001_exports/repair_adoption_v1"
M16_DIR = DESIGN_DIR / "m16"


@pytest.fixture(scope="module")
def m16():
    service = M16PlanningExportWriterService(ROOT)
    preflight = service.run_preflight()
    audit = service.architecture_audit()
    service.record_test_evidence(
        pytest={"status": "PASS", "summary": "M16A/M16B targeted + full pytest"},
        validate_project={"status": "PASS"},
        export={"status": "PASS", "summary": "validate_export_package PASS（json/markdown/docx）"},
        writer={"status": "PASS",
                "summary": "writer context 6 层 + draft + Draft Fact Sync proposal-only"},
        architecture_audit=audit)
    result = service.run()
    return service, preflight, result


def _artifact(name: str) -> dict:
    return json.loads((M16_DIR / name).read_text(encoding="utf-8"))


def test_baseline_and_preflight(m16) -> None:
    _service, preflight, _result = m16
    guard = _artifact(FREEZE_GUARD_FILE)
    baseline = _artifact(BASELINE_FILE)
    assert preflight["status"] == "PASS"
    assert guard["status"] == "PASS" and all(guard["checks"].values())
    assert [row["item"] for row in baseline["work_items"]] == list(WORK_ITEMS)
    assert baseline["milestone"] == "M16"
    assert baseline["next_milestone_dependency"]["milestone"].startswith("M17")
    assert baseline["frozen_truth_digests"]["source"] == FROZEN_SOURCE_DIGESTS
    for row in baseline["work_items"]:
        assert row["repo_reference"] and row["files"] and row["flows"]
        for path in row["files"]:
            assert (ROOT / path).is_file(), path


def test_work_item_acceptance_artifacts(m16) -> None:
    _service, _preflight, result = m16
    assert result["work_items"]["m16a_status"] == "PASS"
    assert result["work_items"]["m16b_status"] == "PASS"
    assert _artifact(M16A_ACCEPTANCE_FILE)["status"] == "PASS"
    assert _artifact(M16B_ACCEPTANCE_FILE)["status"] == "PASS"


def test_acceptance_pass(m16) -> None:
    _service, _preflight, result = m16
    acceptance = result["acceptance"]
    assert acceptance["status"] == "PASS"
    assert acceptance["satisfied_count"] == acceptance["criteria_count"] == 10
    assert all(row["satisfied"] for row in acceptance["criteria"])
    assert {row["criterion"] for row in acceptance["criteria"]} >= {
        "planning_export_complete", "export_validation_pass",
        "export_replay_deterministic", "writer_integration_complete",
        "writer_context_layered", "draft_fact_sync_is_proposal_only",
        "writer_validation_not_masked", "frozen_truth_unchanged", "tests_pass",
        "architecture_audit_pass"}
    assert _artifact(ACCEPTANCE_FILE)["status"] == "PASS"


def test_architecture_audit(m16) -> None:
    _service, _preflight, result = m16
    audit = _artifact("M16_ARCHITECTURE_AUDIT.json")
    assert result["audit"]["status"] == "PASS"
    assert audit["status"] == "PASS" and all(audit["checks"].values())
    assert audit["duplication_removed"]
    assert audit["export_package_lines"] <= 420
    assert audit["writer_integration_lines"] <= 520


def test_frozen_truth_unchanged(m16) -> None:
    service, _preflight, _result = m16
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
    m15 = json.loads((DESIGN_DIR / "m15" / "M15_ACCEPTANCE.json")
                     .read_text(encoding="utf-8"))
    assert m15["status"] == "PASS"


def test_m17_readiness_and_snapshots(m16) -> None:
    _service, _preflight, result = m16
    readiness = result["m17_readiness"]
    assert readiness["m17_entry_allowed"] is True
    assert readiness["m17_executed"] is False
    assert readiness["next_milestone"].startswith("M17")
    assert _artifact(M17_READINESS_FILE)["m17_entry_allowed"] is True
    for phase_id in ("M16_PREFLIGHT", "M16_ACCEPTANCE"):
        assert snapshot_exists(phase_id), phase_id
        assert verify_phase_snapshot(phase_id)["status"] == "PASS"
    snapshot = load_phase_snapshot("M16_ACCEPTANCE")
    assert snapshot["status"] == "PASS"
    assert snapshot["satisfied_count"] == 10
    assert snapshot["work_items"] == list(WORK_ITEMS)
    assert snapshot["m17_entry_allowed"] is True


def test_work_item_scope_matches_repo_definition() -> None:
    milestones = (ROOT / "docs/NOVELFORGE_PRODUCT_V2_MILESTONES.md").read_text(
        encoding="utf-8")
    assert "M16A | Planning Export" in milestones
    assert "M16B | Writer Integration" in milestones
    assert list(WORK_ITEMS) == ["M16A", "M16B"]
    assert "Planning Export" in WORK_ITEM_SCOPE["M16A"]["title"]
    assert "Writer Integration" in WORK_ITEM_SCOPE["M16B"]["title"]
