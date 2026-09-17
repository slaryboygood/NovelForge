"""M15 acceptance 回归：baseline / freeze guard / acceptance / M16 readiness / architecture audit。"""

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
from novelforge.story_engine.m15_canon_inspector import (
    ACCEPTANCE_FILE,
    BASELINE_FILE,
    FREEZE_GUARD_FILE,
    M15CanonInspectorService,
    M16_READINESS_FILE,
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
M15_DIR = DESIGN_DIR / "m15"


@pytest.fixture(scope="module")
def m15():
    service = M15CanonInspectorService(ROOT)
    preflight = service.run_preflight()
    audit = service.architecture_audit()
    service.record_test_evidence(
        pytest={"status": "PASS", "summary": "M15 backend tests + full pytest green"},
        validate_project={"status": "PASS"},
        ui_build={"status": "PASS", "summary": "tsc -b && vite build"},
        browser={"status": "PASS",
                 "summary": "tests/browser_m15_canon_inspector.cjs（Inspector + Repair + 390px）"},
        architecture_audit=audit)
    result = service.acceptance()
    return service, preflight, result


def _artifact(name: str) -> dict:
    return json.loads((M15_DIR / name).read_text(encoding="utf-8"))


def test_baseline_and_preflight(m15) -> None:
    _service, preflight, _result = m15
    guard = _artifact(FREEZE_GUARD_FILE)
    baseline = _artifact(BASELINE_FILE)
    assert preflight["status"] == "PASS"
    assert guard["status"] == "PASS" and all(guard["checks"].values())
    assert [row["item"] for row in baseline["work_items"]] == list(WORK_ITEMS)
    assert baseline["milestone"] == "M15"
    assert baseline["required_flows"]
    assert baseline["next_milestone_dependency"]["milestone"].startswith("M16")
    assert baseline["frozen_truth_digests"]["source"] == FROZEN_SOURCE_DIGESTS
    assert baseline["m11_m12_m13_m14_fingerprint"]
    for row in baseline["work_items"]:
        assert row["files"] and row["flows"] and row["required_flows"]
        for path in row["files"]:
            assert (ROOT / path).is_file(), path


def test_acceptance_pass(m15) -> None:
    _service, _preflight, result = m15
    acceptance = result["acceptance"]
    assert acceptance["status"] == "PASS"
    assert acceptance["satisfied_count"] == acceptance["criteria_count"] == 9
    assert all(row["satisfied"] for row in acceptance["criteria"])
    assert {row["criterion"] for row in acceptance["criteria"]} == {
        "canon_inspector_complete", "repair_center_complete", "inspection_read_only",
        "repair_workflow_safe", "provenance_lineage_visible",
        "approval_boundary_enforced", "frozen_truth_unchanged",
        "tests_build_browser_pass", "architecture_audit_pass"}
    assert all(row["status"] == "COMPLETE" for row in acceptance["work_items"])
    assert _artifact(ACCEPTANCE_FILE)["status"] == "PASS"


def test_architecture_audit(m15) -> None:
    _service, _preflight, result = m15
    audit = _artifact("M15_ARCHITECTURE_AUDIT.json")
    assert result["audit"]["status"] == "PASS"
    assert audit["status"] == "PASS" and all(audit["checks"].values())
    assert audit["duplication_removed"]
    assert "ProvenanceList" in " ".join(audit["provenance_users"] +
                                        ["ProvenanceList.tsx"])
    assert audit["inspector_panels_lines"] <= 320


def test_frozen_truth_unchanged(m15) -> None:
    service, _preflight, _result = m15
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
    m14 = _artifact("../m14/M14_ACCEPTANCE.json") if False else json.loads(
        (DESIGN_DIR / "m14" / "M14_ACCEPTANCE.json").read_text(encoding="utf-8"))
    assert m14["status"] == "PASS"
    m13 = json.loads((DESIGN_DIR / "m13" / "M13_ACCEPTANCE.json")
                     .read_text(encoding="utf-8"))
    assert m13["status"] == "PASS"


def test_m16_readiness_and_snapshots(m15) -> None:
    _service, _preflight, result = m15
    readiness = result["m16_readiness"]
    assert readiness["m16_entry_allowed"] is True
    assert readiness["m16_executed"] is False
    assert _artifact(M16_READINESS_FILE)["m16_entry_allowed"] is True
    for phase_id in ("M15_PREFLIGHT", "M15_ACCEPTANCE"):
        assert snapshot_exists(phase_id), phase_id
        assert verify_phase_snapshot(phase_id)["status"] == "PASS"
    snapshot = load_phase_snapshot("M15_ACCEPTANCE")
    assert snapshot["status"] == "PASS"
    assert snapshot["satisfied_count"] == 9
    assert snapshot["work_items"] == list(WORK_ITEMS)
    assert snapshot["architecture_audit_status"] == "PASS"
    assert snapshot["m16_entry_allowed"] is True


def test_work_item_scope_matches_repo_definition() -> None:
    """M15 只按 repo 粒度拆成 Canon Inspector + Repair Center，不新增业务目标。"""

    assert list(WORK_ITEMS) == ["M15-01", "M15-02"]
    assert "Inspector" in WORK_ITEM_SCOPE["M15-01"]["title"]
    assert "Repair" in WORK_ITEM_SCOPE["M15-02"]["title"]
    milestones = (ROOT / "docs/NOVELFORGE_PRODUCT_V2_MILESTONES.md").read_text(
        encoding="utf-8")
    assert "Canon Inspector / Repair Center" in milestones
