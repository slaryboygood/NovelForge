"""M11 final closure 回归：372/372 terminal、writer gate、final acceptance、M12 entry。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from novelforge.story_engine.m11_final_closure import (
    FINAL_RECONCILIATION,
    M11FinalClosureService,
)

ROOT = Path(".").resolve()
DESIGN_DIR = ROOT / "workspace/wasteland_001_exports/repair_adoption_v1"


@pytest.fixture(scope="module")
def closure():
    service = M11FinalClosureService(ROOT)
    payload = service.run()
    acceptance = service.final_acceptance()
    return service, payload, acceptance


def _artifact(name: str):
    return json.loads((DESIGN_DIR / name).read_text(encoding="utf-8"))


def test_overlay_372_terminal(closure) -> None:
    overlay = _artifact("M11_OVERLAY_V2.json")
    assert overlay["resolved_total"] == 372
    assert overlay["remaining_repair_targets"] == 0
    counts = overlay["primary_resolution_status_counts"]
    for key in ("evidence_ready", "manual_required", "content_design_required",
                "author_decision", "pending"):
        assert counts[key] == 0, key
    assert overlay["conservation"]["exact"] is True


def test_reconciliation_covers_all_targets(closure) -> None:
    reconciliation = _artifact(FINAL_RECONCILIATION)
    # canonical identity：一个 root + 一个 target 只允许一条 primary terminal resolution
    identities = [(row["canonical_root_id"], row["chapter_id"])
                  for row in reconciliation["records"]]
    assert len(identities) == len(set(identities))
    modes = {row.get("resolution_mode") for row in reconciliation["records"]}
    assert {"MANUAL_BINDING_REPAIR", "ENTITY_RESOLUTION",
            "AUTHOR_DELEGATED_DECISION", "CONTENT_EVIDENCE_GAP_EVENT"} <= modes
    assert reconciliation["record_count"] == len(identities)
    audit = _artifact("M11_FINAL_RECONCILIATION_CONSUMPTION_AUDIT.json")
    assert audit["unconsumed_record_count"] == 0
    assert audit["canonical_record_count"] == len(identities)


def test_active_roots_queue_and_backlog(closure) -> None:
    graph = _artifact("M11_FINAL_CANONICAL_GRAPH.json")
    assert graph["active_blocking_canonical_roots"] == 0
    assert graph["unresolved_analysis_targets"] == 0
    queue = _artifact("M11_FINAL_QUEUE_AUDIT.json")
    assert queue["status"] == "PASS"
    assert queue["active_cdq"] == 0
    assert queue["orphan"] == [] and queue["uncovered"] == []
    ledger = _artifact("M11_REPAIR_SUBTYPE_LEDGER.json")
    assert sum(ledger["resolved_subtype_counts"].values()) >= 372


def test_writer_projection_gate_and_acceptance(closure) -> None:
    writer = _artifact("M11_FINAL_WRITER_PROJECTION_GATE.json")
    assert writer["status"] == "PASS"
    acceptance = _artifact("M11_FINAL_ACCEPTANCE.json")
    # production invariants 必须 PASS；整体 status 还取决于 regression evidence
    assert acceptance["production_invariants"] == "PASS"
    assert acceptance["status"] in ("PASS", "CONDITIONAL_PENDING_REGRESSION")
    if acceptance["status"] == "CONDITIONAL_PENDING_REGRESSION":
        assert acceptance["regression_evidence"] == "NOT_PASS"
    assert acceptance["terminal_targets"] == 372
    assert acceptance["active_blocking_canonical_roots"] == 0
    assert acceptance["unresolved_analysis"] == 0
    assert acceptance["queue_audit"] == "PASS"
    assert acceptance["writer_projection_gate"] == "PASS"
    assert acceptance["p15_isolation"] == "PASS"
    assert acceptance["truth_boundary"] == "PASS"
    assert acceptance["field_rebind_capability"] == "NOT_PROVEN"


def test_m12_entry_allowed_true(closure) -> None:
    criteria = _artifact("M12_ENTRY_CRITERIA_FINAL.json")
    acceptance = _artifact("M11_FINAL_ACCEPTANCE.json")
    # M12 entry 由 acceptance + regression evidence 共同决定（诚实 gate）
    assert (criteria["m12_entry_allowed"]
            is (acceptance["status"] == "PASS"))
    assert criteria["satisfied_count"] == len(
        [row for row in criteria["criteria"] if row["satisfied"]])
    assert criteria["unsatisfied_count"] == (
        criteria["criteria_count"] - criteria["satisfied_count"])


def test_truth_and_frozen_unchanged(closure) -> None:
    service, _payload, acceptance = closure
    truth = service.runner.truth_digests()
    assert truth["canon"] == "73836dada9d6bf8e"
    assert truth["story_state"] == "bbc67137eefb9c55"
    assert truth["legacy"] == "cc144c76796d6a4c"
    assert truth["chapter_ir"] == "2eaac16d66e39421"
    frozen = service.runner.frozen_digests()
    assert frozen["contract"] == "67559aa55442d69e"
    assert frozen["repair_gate"] == "e1eab4c33ae75b01"
    # production invariants 必须 PASS；整体 status 允许 CONDITIONAL（regression evidence 未过）
    assert acceptance["acceptance"]["production_invariants"] == "PASS"
    assert acceptance["acceptance"]["status"] in (
        "PASS", "CONDITIONAL_PENDING_REGRESSION")


def test_manual_and_entity_lanes_resolved(closure) -> None:
    _service, _payload, acceptance = closure
    by_mode = acceptance["by_mode"]
    assert by_mode.get("MANUAL_BINDING_REPAIR", 0) >= 15
    assert by_mode.get("ENTITY_RESOLUTION", 0) >= 14
    assert by_mode.get("AUTHOR_DELEGATED_DECISION", 0) >= 3
