"""M12-PREFLIGHT 回归：snapshot 补齐 / M11 freeze guard / input projection / boundary audit。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from novelforge.story_engine.m12_acceptance import (
    BOUNDARY_AUDIT_FILE,
    DELEGATION,
    EXECUTION_BASELINE_FILE,
    INPUT_PROJECTION_FILE,
    M11_FROZEN_INPUT_FILE,
    M12_PHASE_IDS,
    M12PreflightService,
    TARGET_COUNT,
    semantic_fingerprint,
)
from novelforge.story_engine.m11_p15p import (
    FROZEN_FOUNDATION_DIGESTS,
    FROZEN_SOURCE_DIGESTS,
)

from m12_phase_history import load_phase_snapshot, snapshot_exists, verify_phase_snapshot

M11_PHASE_IDS: tuple[str, ...] = (
    "BLOCKER_00", "BLOCKER_00A", "CONTENT_DESIGN_01", "AUTHOR_CONTENT_01",
    "AUTO_SAFE_SWEEP_CLOSEOUT", "P15O", "P15P", "CONTENT_REWRITE",
    "APPROVED_EVENT", "BATCH05", "MICRO_PILOT", "READINESS_V2",
    *(f"M11_RUN_{index:02d}" for index in range(1, 13)))

ROOT = Path(".").resolve()
DESIGN_DIR = ROOT / "workspace/wasteland_001_exports/repair_adoption_v1"
M12_DIR = DESIGN_DIR / "m12"


@pytest.fixture(scope="module")
def preflight():
    service = M12PreflightService(ROOT)
    payload = service.run()
    return service, payload


def _artifact(name: str) -> dict:
    return json.loads((M12_DIR / name).read_text(encoding="utf-8"))


def _digest(path: Path) -> str:
    import hashlib

    return hashlib.sha256(path.read_bytes()).hexdigest()[:16]


# ---------------------------------------------------------------- snapshot preflight
def test_phase_snapshot_verification_api() -> None:
    """ANALYSIS_SNAPSHOT_NOT_WRITE_ONCE preflight：历史证据可被 digest 校验。"""

    checked = 0
    for phase_id in M11_PHASE_IDS:
        if not snapshot_exists(phase_id):
            continue
        result = verify_phase_snapshot(phase_id)
        assert result["status"] == "PASS", (phase_id, result)
        assert result["checks"]["payload_digest_matches_manifest"] is True
        assert result["checks"]["artifact_digests_match_manifest"] is True
        assert result["snapshot_digest"] == result["manifest_digest"]
        checked += 1
    assert checked >= 20


def test_snapshot_write_once_semantics() -> None:
    from novelforge.story_engine.phase_snapshot import PhaseSnapshotExists
    from novelforge.story_engine import phase_snapshot as store

    phase_id = "_ARCH_TEST_WRITE_ONCE"
    assert snapshot_exists(phase_id)
    with pytest.raises(PhaseSnapshotExists):
        store.write_phase_snapshot(ROOT, phase_id, {"value": 999})
    assert load_phase_snapshot(phase_id)["value"] == 1
    assert verify_phase_snapshot(phase_id)["status"] == "PASS"


# ---------------------------------------------------------------- freeze guard
def test_m11_frozen_input_guard(preflight) -> None:
    _service, payload = preflight
    guard = _artifact(M11_FROZEN_INPUT_FILE)
    assert payload["m11_frozen_input_status"] == "PASS"
    assert guard["status"] == "PASS"
    assert all(guard["checks"].values()), guard["checks"]
    fingerprint = guard["semantic_fingerprint"]
    assert fingerprint["terminal_targets"] == TARGET_COUNT
    assert fingerprint["remaining_repair_targets"] == 0
    assert fingerprint["ledger_target_count"] == TARGET_COUNT
    assert fingerprint["reconciliation_identity_digest"]
    assert fingerprint["overlay_conservation"] == {
        "primary_total": 372, "target_count": 372, "exact": True}
    assert guard["m11_final_acceptance_status"] == "PASS"
    assert guard["phase_snapshot_immutability"]
    assert all(status == "PASS"
               for status in guard["phase_snapshot_immutability"].values())


def test_m11_frozen_artifacts_unchanged(preflight) -> None:
    _service, _payload = preflight
    guard = _artifact(M11_FROZEN_INPUT_FILE)
    for name, digest in guard["m11_frozen_artifacts"].items():
        assert _digest(DESIGN_DIR / name) == digest, name


def test_production_mutation_during_preflight_is_none(preflight) -> None:
    service, _payload = preflight
    guard = _artifact(M11_FROZEN_INPUT_FILE)
    assert semantic_fingerprint(service.design_dir) == guard["semantic_fingerprint"]


# ---------------------------------------------------------------- projection
def test_input_projection_frozen_truth(preflight) -> None:
    _service, payload = preflight
    projection = _artifact(INPUT_PROJECTION_FILE)
    assert payload["input_projection_status"] == "PASS"
    assert all(projection["checks"].values()), projection["checks"]
    truth = projection["truth_digests"]
    assert truth["canon"] == FROZEN_SOURCE_DIGESTS["canon"]
    assert truth["story_state"] == FROZEN_SOURCE_DIGESTS["story_state"]
    assert truth["legacy"] == FROZEN_SOURCE_DIGESTS["legacy"]
    assert truth["chapter_ir"] == FROZEN_SOURCE_DIGESTS["chapter_ir"]
    assert truth["historical_foundation"] == FROZEN_FOUNDATION_DIGESTS
    assert projection["chapter_ir"]["chapter_count"] == 570
    assert projection["chapter_ir"]["materialization_status_counts"] == {
        "FULL": 508, "PARTIAL": 62}
    assert projection["planning"]["planning_revision"]
    assert projection["writer_projection_gate"] == "PASS"


def test_boundary_audit_invariants(preflight) -> None:
    _service, payload = preflight
    boundary = _artifact(BOUNDARY_AUDIT_FILE)
    assert payload["boundary_audit_status"] == "PASS"
    assert all(boundary["checks"].values()), boundary["checks"]
    assert boundary["invariants"] == {
        "historical_repair_truth_is_not_canon_source": True,
        "future_planning_is_not_occurred_history": True,
        "m11_repaired_events_are_consumable_and_non_polluting": True}
    evidence = boundary["evidence"]
    assert evidence["canon_digest"] == FROZEN_SOURCE_DIGESTS["canon"]
    assert evidence["story_state_digest"] == FROZEN_SOURCE_DIGESTS["story_state"]
    assert evidence["chapter_ir_digest"] == FROZEN_SOURCE_DIGESTS["chapter_ir"]


def test_execution_baseline_scope(preflight) -> None:
    _service, _payload = preflight
    baseline = _artifact(EXECUTION_BASELINE_FILE)
    assert baseline["milestone"] == "M12"
    assert "全书审计" in baseline["goal"] and "freeze" in baseline["goal"]
    entry = baseline["entry_criteria"]
    assert entry["criteria_count"] == 9 and entry["m12_entry_allowed"] is True
    assert len(baseline["acceptance_criteria"]) == 9
    assert {"criterion", "definition"} <= set(baseline["acceptance_criteria"][0])
    assert len(baseline["required_components"]) == 4
    assert baseline["m13_entry_dependency"]["milestone"].startswith("M13")
    assert baseline["preflight_status"] == {
        "frozen_input": "PASS", "input_projection": "PASS",
        "boundary_audit": "PASS"}


# ---------------------------------------------------------------- historical snapshot
def test_preflight_snapshot_is_frozen_and_consistent(preflight) -> None:
    _service, payload = preflight
    assert payload["status"] == "PASS"
    assert snapshot_exists("M12_PREFLIGHT")
    verification = verify_phase_snapshot("M12_PREFLIGHT")
    assert verification["status"] == "PASS"
    snapshot = load_phase_snapshot("M12_PREFLIGHT")
    assert snapshot["phase_id"] == "M12_PREFLIGHT"
    assert snapshot["m11_final_acceptance_status"] == "PASS"
    assert snapshot["m11_frozen_input_status"] == "PASS"
    assert snapshot["input_projection_status"] == "PASS"
    assert snapshot["boundary_audit_status"] == "PASS"
    assert snapshot["terminal_targets"] == TARGET_COUNT
    assert snapshot["chapter_ir_chapter_count"] == 570
    assert snapshot["delegation"] == DELEGATION
