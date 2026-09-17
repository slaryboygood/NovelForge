"""M12 全书审计回归：570 章 historical IR + M11 repair lineage 消费审计。"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from novelforge.story_engine.m11_p15p import (
    FROZEN_FOUNDATION_DIGESTS,
    FROZEN_SOURCE_DIGESTS,
)
from novelforge.story_engine.m12_acceptance import (
    CHAPTER_COUNT,
    FULL_BOOK_AUDIT_FILE,
    FULL_BOOK_AUDIT_GATE_FILE,
    M11_FROZEN_INPUT_FILE,
    M12FullBookAuditService,
    M12PreflightService,
    TARGET_COUNT,
)

from m12_phase_history import load_phase_snapshot, snapshot_exists, verify_phase_snapshot

ROOT = Path(".").resolve()
DESIGN_DIR = ROOT / "workspace/wasteland_001_exports/repair_adoption_v1"
M12_DIR = DESIGN_DIR / "m12"


@pytest.fixture(scope="module")
def book_audit():
    M12PreflightService(ROOT).run()
    service = M12FullBookAuditService(ROOT)
    payload = service.run()
    return service, payload


def _artifact(name: str) -> dict:
    return json.loads((M12_DIR / name).read_text(encoding="utf-8"))


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()[:16]


# ---------------------------------------------------------------- chapters
def test_chapter_coverage_and_checks(book_audit) -> None:
    _service, payload = book_audit
    audit = payload["audit"]["chapter_audit"]
    assert audit["chapter_count"] == CHAPTER_COUNT
    assert audit["failure_count"] == 0
    assert all(audit["checks_passed"].values()), audit["checks_passed"]
    assert audit["materialization_status_counts"] == {"FULL": 508, "PARTIAL": 62}
    assert audit["coverage_status_counts"] == {"PARTIAL": 570}
    assert audit["volume_counts"] and len(audit["volume_counts"]) == 10
    assert audit["chapters_with_unresolved_fields"] > 0
    assert audit["chapters"][0]["display_number"] == 1
    assert audit["chapters"][-1]["display_number"] == CHAPTER_COUNT


def test_chapter_truth_boundary(book_audit) -> None:
    _service, payload = book_audit
    for row in payload["audit"]["chapter_audit"]["chapters"]:
        assert row["checks"]["truth_boundary_ok"] is True, row["legacy_label"]
        assert row["chapter_ir_digest"], row["legacy_label"]


# ---------------------------------------------------------------- repair layer
def test_repair_lineage_conservation(book_audit) -> None:
    _service, payload = book_audit
    lineage = payload["audit"]["repair_lineage"]
    assert lineage["status"] == "PASS"
    assert all(lineage["checks"].values()), lineage["checks"]
    assert lineage["ledger_target_count"] == TARGET_COUNT
    assert lineage["overlay_resolved_total"] == TARGET_COUNT
    counts = lineage["resolved_subtype_counts"]
    assert sum(counts.values()) == TARGET_COUNT
    assert counts["no_repair_required"] == 67
    assert lineage["reconciliation_record_count"] == 97
    assert lineage["missing_repaired_refs"] == []
    assert lineage["duplicate_canonical_identity"] == []


def test_repair_lineage_matches_live_artifacts(book_audit) -> None:
    _service, _payload = book_audit
    overlay = _read("M11_OVERLAY_V2.json")
    ledger = _read("M11_REPAIR_SUBTYPE_LEDGER.json")
    assert overlay["resolved_total"] == len(ledger["ledger"]) == TARGET_COUNT
    assert overlay["repaired"] == sum(
        value for key, value in ledger["resolved_subtype_counts"].items()
        if key != "no_repair_required")
    assert overlay["no_repair_required"] == ledger["resolved_subtype_counts"][
        "no_repair_required"]


# ---------------------------------------------------------------- continuity / gate
def test_continuity_audit(book_audit) -> None:
    _service, payload = book_audit
    continuity = payload["audit"]["continuity"]
    assert continuity["status"] == "PASS"
    assert continuity["checks"] == {
        "chronological_order": True, "stable_chapter_identity": True,
        "no_neighbor_continuity_failure": True, "no_erasure_risk": True}
    assert continuity["cross_chapter_fact_checks"]["erasure_risk_count"] == 0
    assert continuity["cross_chapter_fact_checks"]["confirmed_truth_priority"] is True


def test_full_book_audit_gate(book_audit) -> None:
    _service, payload = book_audit
    gate = payload["gate"]
    assert payload["audit"]["status"] == "PASS"
    assert gate["status"] == "PASS"
    assert gate["failed_checks"] == []
    assert all(gate["checks"].values())
    assert gate["chapter_count"] == CHAPTER_COUNT
    assert _artifact(FULL_BOOK_AUDIT_GATE_FILE)["status"] == "PASS"


# ---------------------------------------------------------------- frozen boundary
def test_frozen_truth_unchanged_by_audit(book_audit) -> None:
    service, _payload = book_audit
    truth = service.store.load_artifacts()
    assert len(truth) == CHAPTER_COUNT
    guard = _artifact(M11_FROZEN_INPUT_FILE)
    for name, digest in guard["m11_frozen_artifacts"].items():
        assert _digest(DESIGN_DIR / name) == digest, name
    from novelforge.story_engine.m11_run12 import M11Run12Service

    digests = M11Run12Service(ROOT).truth_digests()
    assert digests["canon"] == FROZEN_SOURCE_DIGESTS["canon"]
    assert digests["story_state"] == FROZEN_SOURCE_DIGESTS["story_state"]
    assert digests["legacy"] == FROZEN_SOURCE_DIGESTS["legacy"]
    assert digests["chapter_ir"] == FROZEN_SOURCE_DIGESTS["chapter_ir"]
    assert digests["historical_foundation"] == FROZEN_FOUNDATION_DIGESTS


# ---------------------------------------------------------------- historical snapshot
def test_full_book_audit_snapshot_frozen(book_audit) -> None:
    _service, payload = book_audit
    assert snapshot_exists("M12_FULL_BOOK_AUDIT")
    assert verify_phase_snapshot("M12_FULL_BOOK_AUDIT")["status"] == "PASS"
    snapshot = load_phase_snapshot("M12_FULL_BOOK_AUDIT")
    assert snapshot["status"] == "PASS"
    assert snapshot["gate_status"] == "PASS"
    assert snapshot["chapter_count"] == CHAPTER_COUNT
    assert snapshot["chapter_failure_count"] == 0
    assert snapshot["ledger_target_count"] == TARGET_COUNT
    assert snapshot["reconciliation_record_count"] == 97
    assert snapshot["continuity_status"] == "PASS"
    assert payload["snapshot"]["snapshot_id"] == "M12_FULL_BOOK_AUDIT"


def _read(name: str) -> dict:
    return json.loads((DESIGN_DIR / name).read_text(encoding="utf-8"))
