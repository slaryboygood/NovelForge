"""Phase snapshot architecture 回归：write-once / 历史与 live 分离 / 永久 invariant。"""

from __future__ import annotations

import pytest

from m11_phase_history import (
    PhaseSnapshotExists,
    load_current_state,
    load_phase_snapshot,
    load_snapshot_manifest,
    snapshot_exists,
    write_phase_snapshot,
)


def test_snapshot_is_write_once() -> None:
    phase_id = "_ARCH_TEST_WRITE_ONCE"
    if snapshot_exists(phase_id):
        pytest.skip("临时 snapshot 已存在（上一轮未清理）")
    manifest = write_phase_snapshot(phase_id, {"value": 1},
                                    source_commit="test", evidence_sources=["test"])
    assert manifest["schema_version"] == "M11_PHASE_SNAPSHOT_V1"
    assert load_phase_snapshot(phase_id)["value"] == 1
    with pytest.raises(PhaseSnapshotExists):
        write_phase_snapshot(phase_id, {"value": 2})
    assert load_phase_snapshot(phase_id)["value"] == 1     # 未被覆盖


def test_snapshot_digest_and_provenance() -> None:
    manifest = load_snapshot_manifest("BLOCKER_00")
    assert manifest["phase_id"] == "BLOCKER_00"
    assert manifest["snapshot_digest"]
    assert manifest["evidence_sources"]
    assert manifest["reconstructed"] is True
    assert manifest["read_only"] is True


def test_historical_and_live_values_can_differ() -> None:
    historical = load_phase_snapshot("BLOCKER_00")
    live = load_current_state()
    # 历史：BLOCKER-00 时 127 artifact roots / 149 non-terminal；current：0 active
    assert historical["historical_root_blocker_count"] == 127
    assert historical["entry_non_terminal_targets"] == 149
    assert historical["current_active_root_blockers_at_snapshot"] == 0
    assert live["terminal_targets"] == 372
    assert live["overlay_buckets"]["content_design_required"] == 0


def test_live_state_is_closure_state() -> None:
    live = load_current_state()
    assert live["terminal_targets"] == 372
    assert live["non_terminal_targets"] == 0
    assert live["ledger_entries"] == live["ledger_resolved"] == 372
    assert live["cdq_active"] == 0
    assert live["overlay_conservation"]["exact"] is True


def test_phase_snapshots_exist_for_historical_suites() -> None:
    for phase_id in ("BLOCKER_00", "BLOCKER_00A", "P15P", "P15O",
                     "CONTENT_REWRITE", "APPROVED_EVENT", "BATCH05",
                     "MICRO_PILOT", "READINESS_V2",
                     "M11_RUN_01", "M11_RUN_12"):
        assert snapshot_exists(phase_id), phase_id
