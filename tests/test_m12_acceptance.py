"""M12 final acceptance 回归：criteria / freeze / M13 readiness / frozen truth 不变。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from novelforge.story_engine.m11_p15p import (
    FROZEN_FOUNDATION_DIGESTS,
    FROZEN_SOURCE_DIGESTS,
)
from novelforge.story_engine.m11_run12 import M11Run12Service
from novelforge.story_engine.m12_acceptance import (
    ACCEPTANCE_FILE,
    CHAPTER_COUNT,
    FREEZE_FILE,
    M13_READINESS_FILE,
    M12AcceptanceService,
    M12FullBookAuditService,
    M12PreflightService,
    M12SampleReviewService,
    SAMPLE_SIZE,
    TARGET_COUNT,
    semantic_fingerprint,
)

from m12_phase_history import (
    PHASE_IDS,
    load_phase_snapshot,
    report_records,
    snapshot_exists,
    verify_phase_snapshot,
)

ROOT = Path(".").resolve()
DESIGN_DIR = ROOT / "workspace/wasteland_001_exports/repair_adoption_v1"
M12_DIR = DESIGN_DIR / "m12"


@pytest.fixture(scope="module")
def acceptance():
    M12PreflightService(ROOT).run()
    M12FullBookAuditService(ROOT).run()
    M12SampleReviewService(ROOT).run()
    service = M12AcceptanceService(ROOT)
    payload = service.run()
    return service, payload


def _artifact(name: str) -> dict:
    return json.loads((M12_DIR / name).read_text(encoding="utf-8"))


def _design_artifact(name: str) -> dict:
    return json.loads((DESIGN_DIR / name).read_text(encoding="utf-8"))


# ---------------------------------------------------------------- acceptance
def test_acceptance_criteria_all_satisfied(acceptance) -> None:
    _service, payload = acceptance
    result = payload["acceptance"]
    assert result["status"] == "PASS"
    assert result["criteria_count"] == 9
    assert result["satisfied_count"] == 9
    assert result["unsatisfied_count"] == 0
    assert result["blocking_count"] == 0
    assert result["replay_status"] == "PASS"
    assert all(row["satisfied"] for row in result["criteria"]["criteria"])
    assert {row["criterion"] for row in result["criteria"]["criteria"]} == {
        "book_audit_complete", "truth_separation", "repair_lineage_conservation",
        "sample_review_complete", "frozen_inputs_unchanged",
        "writer_projection_gate_pass", "freeze_manifest_written",
        "m12_replay_idempotent", "m13_readiness"}


def test_acceptance_summary_scope(acceptance) -> None:
    _service, payload = acceptance
    result = payload["acceptance"]
    assert result["book_audit"]["chapter_count"] == CHAPTER_COUNT
    assert result["book_audit"]["chapter_failures"] == 0
    assert result["book_audit"]["gate"] == "PASS"
    assert result["sample_review"]["sample_size"] == SAMPLE_SIZE
    assert result["sample_review"]["status"] == "PASS"
    assert result["m11_read_only_during_m12"] is True
    assert _artifact(ACCEPTANCE_FILE)["status"] == "PASS"


# ---------------------------------------------------------------- freeze
def test_freeze_manifest(acceptance) -> None:
    _service, payload = acceptance
    freeze = payload["freeze"]
    assert freeze["status"] == "FROZEN"
    assert freeze["freeze_id"] == "WASTELAND_001_M12_FREEZE_V1"
    assert freeze["truth_digests"]["canon"] == FROZEN_SOURCE_DIGESTS["canon"]
    assert freeze["truth_digests"]["story_state"] == FROZEN_SOURCE_DIGESTS["story_state"]
    assert freeze["truth_digests"]["legacy"] == FROZEN_SOURCE_DIGESTS["legacy"]
    assert freeze["truth_digests"]["chapter_ir"] == FROZEN_SOURCE_DIGESTS["chapter_ir"]
    assert freeze["truth_digests"]["historical_foundation"] == FROZEN_FOUNDATION_DIGESTS
    assert freeze["frozen_digests"] == {
        "contract": "67559aa55442d69e", "repair_gate": "e1eab4c33ae75b01"}
    assert freeze["historical_ir_index_digest"]
    assert freeze["immutability"]["write_once"] is True
    assert freeze["immutability"]["m11_production_state"] == "READ_ONLY"
    assert freeze["author_override"]["allowed"] is True
    assert _artifact(FREEZE_FILE)["status"] == "FROZEN"


def test_m13_readiness(acceptance) -> None:
    _service, payload = acceptance
    readiness = payload["m13_readiness"]
    assert readiness["m13_entry_allowed"] is True
    assert readiness["m13_executed"] is False
    assert readiness["m12_acceptance_status"] == "PASS"
    assert readiness["next_milestone"].startswith("M13")
    assert _artifact(M13_READINESS_FILE)["m13_entry_allowed"] is True


# ---------------------------------------------------------------- frozen truth
def test_frozen_truth_and_m11_state_unchanged(acceptance) -> None:
    service, payload = acceptance
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
    guard = _artifact("M11_FROZEN_INPUT.json")
    assert semantic_fingerprint(service.design_dir) == guard["semantic_fingerprint"]
    assert payload["acceptance"]["satisfied_count"] == 9


def test_m11_acceptance_and_writer_gate_unchanged(acceptance) -> None:
    _service, _payload = acceptance
    m11 = _design_artifact("M11_FINAL_ACCEPTANCE.json")
    assert m11["status"] == "PASS"
    assert m11["terminal_targets"] == TARGET_COUNT
    assert m11["writer_projection_gate"] == "PASS"
    assert m11["p15_isolation"] == "PASS"
    assert m11["field_rebind_capability"] == "NOT_PROVEN"
    writer = _design_artifact("M11_FINAL_WRITER_PROJECTION_GATE.json")
    assert writer["status"] == "PASS"


# ---------------------------------------------------------------- snapshot
def test_acceptance_snapshot_frozen(acceptance) -> None:
    _service, payload = acceptance
    assert verify_phase_snapshot("M12_ACCEPTANCE")["status"] == "PASS"
    snapshot = load_phase_snapshot("M12_ACCEPTANCE")
    assert snapshot["status"] == "PASS"
    assert snapshot["satisfied_count"] == 9
    assert snapshot["criteria_count"] == 9
    assert snapshot["chapter_count"] == CHAPTER_COUNT
    assert snapshot["sample_size"] == SAMPLE_SIZE
    assert snapshot["freeze_status"] == "FROZEN"
    assert snapshot["m13_entry_allowed"] is True
    assert snapshot["replay_status"] == "PASS"
    assert payload["acceptance"]["snapshot"]["snapshot_id"] == "M12_ACCEPTANCE"


def test_all_m12_phase_snapshots_frozen() -> None:
    for phase_id in PHASE_IDS:
        assert snapshot_exists(phase_id), phase_id
        assert verify_phase_snapshot(phase_id)["status"] == "PASS", phase_id


def test_acceptance_report_records_frozen_evidence() -> None:
    """M12 的历史值必须仍被 acceptance report 记录（本文件即 frozen 叙述证据）。"""

    report_records("M12_PREFLIGHT", "M12-PREFLIGHT", "M11_FROZEN_INPUT")
    report_records("M12_FULL_BOOK_AUDIT", "570 / 570", "372", "97")
    report_records("M12_SAMPLE_REVIEW", "40 章", "author_override_recommended")
    report_records("M12_ACCEPTANCE", "M12_FINAL_ACCEPTANCE = PASS", "FROZEN",
                   "m13_entry_allowed = true")
