"""M11-RUN-04：Production Execution 回归（Auto Safe Frontier through Batch 09）。

production execution tests：scope freeze、ch077 baseline 执行、新释放 deferred、
Batch09 closure、blocked untouched、Batch10 not entered、dynamic downgrade honesty、
production CDQ ownership、P15 executor isolation、372 / queue conservation、
truth digests、Contract/Gate digests、no new event、no author auto-resolution、M12 false。
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from novelforge.story_engine.m11_content_rewrite import ContentRewritePolicyService
from novelforge.story_engine.m11_micro_wave import MicroRepairFrontierPlanner
from novelforge.story_engine.m11_p15o import Wave02Service
from novelforge.story_engine.m11_p15p import (
    BACKLOG_LANES,
    FROZEN_FOUNDATION_DIGESTS,
    FROZEN_SOURCE_DIGESTS,
    TARGET_COUNT,
)
from novelforge.story_engine.m11_readiness import PRIMARY_BUCKETS
from novelforge.story_engine.m11_run01 import P15_ISOLATION_INVARIANT_ID
from novelforge.story_engine.m11_run04 import (

    BATCH_09,
    BATCH_09_SCOPE_FILE,
    M11Run04Service,
    RUN_ID,
    RUN_RECONCILIATION,
)

from m11_phase_history import closed

ROOT = Path(".").resolve()
DESIGN_DIR = ROOT / "workspace/wasteland_001_exports/repair_adoption_v1"
REPAIR_DIR = ROOT / "workspace/wasteland_001_exports/repair_v1"
RUN_DIR = DESIGN_DIR / "m11_run_04"


@pytest.fixture(scope="module")
def run04():
    service = M11Run04Service(ROOT)
    payload = service.run()
    return service, payload


def _artifact(path: Path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _run_artifact(name: str):
    return _artifact(RUN_DIR / name)


def _digest(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()[:16]


def _batch(readiness: dict, batch_id: str) -> dict:
    return next(row for row in readiness["batches"] if row["batch_id"] == batch_id)


# ---------------------------------------------------------------- scope freeze
def test_scope_frozen_before_execution(run04) -> None:
    service, payload = run04
    baseline = _run_artifact("M11_RUN_04_BASELINE.json")
    scope = _run_artifact("M11_RUN_04_EXECUTION_SCOPE.json")
    assert baseline["run_id"] == RUN_ID
    assert baseline["git"]["commit"]
    assert baseline["primary_buckets"] == {
        "resolved_repaired": 93, "resolved_no_repair_required": 26,
        "evidence_ready": 3, "manual_required": 4, "content_design_required": 39,
        "author_decision": 1, "pending": 206}
    assert baseline["batch_execution_status_counts"] == {
        "BLOCKED": 7, "PARTIAL_READY": 6, "READY": 4}
    assert baseline["frontier"]["batch_09"] == {
        "completion_status": "IN_PROGRESS", "execution_status": "PARTIAL_READY",
        "resolved": 0, "ready": 14, "blocked": 6}
    assert scope["frozen"] is True and scope["run_id"] == RUN_ID
    assert scope["frontier_max_batch"] == BATCH_09
    assert scope["contract_digest"] == service.frozen_digests()["contract"]
    assert scope["gate_digest"] == service.frozen_digests()["repair_gate"]
    assert scope["matches_run03_baseline"]["REPAIR_BATCH_04"] is True
    assert scope["matches_run03_baseline"]["REPAIR_BATCH_09"] is True
    assert scope["run03_baseline"]["REPAIR_BATCH_09"] == {
        "ready": 14, "blocked": 6, "execution_status": "PARTIAL_READY"}
    assert payload["status"] in ("PASS", "EVIDENCE_REQUIRED")


def test_ch077_baseline_execution(run04) -> None:
    service, payload = run04
    scope = _run_artifact("M11_RUN_04_EXECUTION_SCOPE.json")
    assert scope["batch_04_residual_targets"] == [
        "uuid_8bea0d910dab5815bb84a71e72ee4fd2"]
    preflight = _run_artifact("M11_RUN_04_BATCH04_PREFLIGHT.json")
    row = preflight["targets"][0]
    assert row["legacy_label"] == "ch077"
    assert str(row["target_state"]) == "READY"  # Frozen run-local evidence.
    assert row["actual_repair_class"] == "EVIDENCE_ONLY"
    assert row["execution_decision"] == "SAFE_AUTO"
    assert row["verdict"] == "SAFE_AUTO_EXECUTE"
    assert row["foundation"]["evidence_substrate"] == "HISTORICAL_FULL_IR"
    assert row["foundation"]["digest_match"] is True
    assert row["execution_blockers"] == []
    execution = _run_artifact("M11_RUN_04_BATCH04_EXECUTION.json")
    assert execution["verified"] == 1 and execution["gate_status"] == "PASS"
    reconciliation = _artifact(DESIGN_DIR / RUN_RECONCILIATION)
    record = next(r for r in reconciliation["records"] if r["legacy_label"] == "ch077")
    assert record["new_resolution_status"] == "RESOLVED_REPAIRED"
    assert record["repair_subtype"] == "repaired_evidence_only"
    assert payload["residual"]["acceptance"] == "PASS"


def test_newly_unlocked_deferred(run04) -> None:
    service, payload = run04
    reconciliation = _artifact(DESIGN_DIR / RUN_RECONCILIATION)
    executed = {row["chapter_id"] for row in reconciliation["records"]
                if row["new_resolution_status"] in ("RESOLVED_REPAIRED",
                                                    "RESOLVED_NO_REPAIR_REQUIRED")}
    # RUN-04 只执行了 ch077；ch078（RUN-04 时被释放）留到 RUN-05
    scope = _run_artifact("M11_RUN_04_EXECUTION_SCOPE.json")
    assert scope["batch_04_residual_targets"] == [
        "uuid_8bea0d910dab5815bb84a71e72ee4fd2"]          # ch077
    assert "uuid_37bac3beed415b1fba59d900b777993a" not in executed      # ch078 deferred
    assert payload["gate"]["checks"]["only_ready_target_executed"] is True


# ---------------------------------------------------------------- Batch 09
def test_batch09_baseline_closure(run04) -> None:
    service, payload = run04
    scope = _artifact(DESIGN_DIR / BATCH_09_SCOPE_FILE)
    assert scope["frozen"] is True and scope["batch_id"] == BATCH_09
    assert len(scope["ready_target_ids"]) == 14
    assert len(scope["blocked_target_ids"]) == 6
    closure = scope["dependency_closure"]
    assert closure["readiness_ready_count"] == 14
    assert closure["readiness_blocked_count"] == 6
    # [M11-CLOSURE] blocker 分类在 M11 final closure 后全部归零（scope 本身仍 frozen）
    assert closure["classification"]["content_design_blocked"] == 0
    assert closure["classification"]["entity_blocked"] == 0
    assert closure["classification"]["manual_blocked"] == 0
    assert closure["classification"]["author_blocked"] == 0
    assert closure["classification"]["confirmed_binding_blocked"] == 0
    assert closure["classification"]["architecture_exception"] == 0
    assert scope["contract_digest"] == service.frozen_digests()["contract"]
    assert scope["gate_digest"] == service.frozen_digests()["repair_gate"]
    assert scope["baseline_truth_digests"]["canon"] == FROZEN_SOURCE_DIGESTS["canon"]
    history = _artifact(DESIGN_DIR / RUN_RECONCILIATION)
    historical = {r["chapter_id"]: r for r in history["records"]}
    live = _artifact(DESIGN_DIR / "M11_READINESS_V2.json")
    resolved = {cid for b in live["batches"] for cid in b["resolved_target_ids"]}
    for row in scope["targets"]:
        # Scope rows mix retained preflight and recomputed fields; use run history.
        assert historical[row["chapter_id"]]["old_status"] == "not_processed"
        assert row["chapter_id"] in resolved
        assert row["execution_blockers"] == []
        assert row["ready_reason"]
    assert payload["frontier"]["scope"] == {"ready": 14, "blocked": 6}


def test_blocked_targets_untouched(run04) -> None:
    service, payload = run04
    scope = _artifact(DESIGN_DIR / BATCH_09_SCOPE_FILE)
    blocked = {str(item) for item in scope["blocked_target_ids"]}
    assert len(blocked) == 6
    assert {row["legacy_label"] for row in scope["blocked_targets"]} == {
        "ch261", "ch264", "ch265", "ch266", "ch267", "ch297"}
    reconciliation = _artifact(DESIGN_DIR / RUN_RECONCILIATION)
    for row in reconciliation["records"]:
        if row["chapter_id"] in blocked:
            assert row["new_resolution_status"] == "BLOCKED_CONTENT_DESIGN"
            assert row["repair_subtype"] == "" and row["repaired_ref"] == ""
    execution = _run_artifact("M11_RUN_04_BATCH09_EXECUTION.json")
    assert not set(execution["targets"]) & blocked
    assert set(execution["blocked_targets"]) == blocked
    assert payload["gate"]["checks"]["blocked_target_untouched"] is True


def test_batch09_execution_and_promotion(run04) -> None:
    service, payload = run04
    execution = _run_artifact("M11_RUN_04_BATCH09_EXECUTION.json")
    assert len(execution["targets"]) == 14
    assert execution["verified"] == 12
    assert execution["human_review"] == 2
    assert execution["promotion_mode"] == "partial"
    assert execution["gate_status"] == "PASS"
    diff = _artifact(REPAIR_DIR / "BATCH_09_DIFF.json")
    assert diff["semantic_elements_added"] == 0
    assert diff["semantic_elements_removed"] == 0
    assert diff["confirmed_facts_changed"] == 0
    assert diff["read_only_chapters_changed"] == 0
    reconciliation = _artifact(DESIGN_DIR / RUN_RECONCILIATION)
    assert reconciliation["promoted"] == 13          # ch077 + B09 的 12
    assert reconciliation["promoted_evidence_only"] == 9
    assert reconciliation["promoted_no_repair_required"] == 4
    assert reconciliation["promoted_field_rebind"] == 0
    assert payload["frontier"]["acceptance"] == "PASS"


def test_dynamic_downgrade_honesty(run04) -> None:
    service, payload = run04
    reconciliation = _artifact(DESIGN_DIR / RUN_RECONCILIATION)
    counts = reconciliation["dynamic_downgrade_counts"]
    assert counts["CONTENT_DESIGN_REQUIRED"] == 2
    assert counts["MANUAL_REQUIRED"] == 0
    assert counts["EVIDENCE_READY"] == 0
    assert counts["AUTHOR_DECISION_REQUIRED"] == 0
    assert counts["BLOCKED_CONFIRMED_BINDING_CONFLICT"] == 0
    assert counts["ARCHITECTURE_EXCEPTION_REQUIRED"] == 0
    design = {row["legacy_label"] for row in reconciliation["records"]
              if row["new_resolution_status"] == "CONTENT_DESIGN_REQUIRED"}
    assert design == {"ch284", "ch293"}
    # promoted : dynamic downgrade = 13 : 2（诚实比例，不硬 promote）
    assert reconciliation["promoted"] > sum(
        value for key, value in counts.items() if key != "EVIDENCE_READY")
    assert payload["frontier"]["verified"] == 12


def test_batch10_not_entered(run04) -> None:
    service, payload = run04
    gate = _run_artifact("M11_RUN_04_GATE.json")
    assert gate["checks"]["batch10_not_entered"] is True
    reconciliation = _artifact(DESIGN_DIR / RUN_RECONCILIATION)
    executed = {row["chapter_id"] for row in reconciliation["records"]}
    readiness = _artifact(DESIGN_DIR / "M11_READINESS_V2.json")
    batch_10 = _batch(readiness, "REPAIR_BATCH_10")
    assert not executed & (set(batch_10["ready_target_ids"])
                           | set(batch_10["blocked_target_ids"])
                           | set(batch_10["resolved_target_ids"]))
    assert payload["batch_10_executed"] is False


# ---------------------------------------------------------------- production CDQ
def test_production_cdq_ownership(run04) -> None:
    service, payload = run04
    reconciliation = _artifact(DESIGN_DIR / RUN_RECONCILIATION)
    items = reconciliation["content_design_items_registered"]
    assert len(items) == 2
    assert {item["design_item_id"] for item in items} == {
        "CDQ_RUN04_ch284", "CDQ_RUN04_ch293"}
    assert all(str(item["origin"]).startswith("M11_RUN_04") for item in items)
    queue = _artifact(DESIGN_DIR / "M11_CONTENT_DESIGN_QUEUE_V2.json")
    run04_items = [row for row in queue["items"]
                   if str(row["design_item_id"]).startswith("CDQ_RUN04_")]
    assert len(run04_items) == 2
    assert all(str(row["origin"]).startswith("M11_RUN_04") for row in run04_items)
    queue3 = _artifact(DESIGN_DIR / "M11_CONTENT_DESIGN_QUEUE_V3.json")
    active = [row for row in queue3["requirements"] if row["status"] == "ACTIVE"]
    overlay = _artifact(DESIGN_DIR / "M11_OVERLAY_V2.json")
    assert len(active) == overlay["content_design_required"]
    assert overlay["content_design_required"] == 0  # [M11-CLOSURE] 已 terminal
    policy = ContentRewritePolicyService(ROOT)
    rows = {row["legacy_label"]: row for row in policy.reclassify()["rows"]}
    for label in ("ch284", "ch293"):
        queue_row = next(r for r in queue3["requirements"]
                         if r["legacy_label"] == label)
        assert queue_row["status"] == "RESOLVED_REPAIRED"
        assert queue_row["design_item_id"] == f"CDQ_RUN04_{label}"
        assert queue_row["origin"] == "M11_RUN_04 dynamic downgrade"
        assert rows.get(label, {}).get("micro_scale_candidate", False) is False
    assert payload["reconciliation"]["content_design_items_registered"] == 2


def test_p15_executor_isolation(run04) -> None:
    service, payload = run04
    invariant = _run_artifact(f"{P15_ISOLATION_INVARIANT_ID}.json")
    assert invariant["status"] == "PASS"
    assert invariant["static_scan_pass"] is True
    assert invariant["production_item_ownership_pass"] is True
    assert invariant["runtime_isolation_pass"] is True
    assert invariant["production_item_count"] >= 12
    assert not any(invariant["static_scan_findings"].values())
    gate = _run_artifact("M11_RUN_04_GATE.json")
    assert gate["checks"]["p15_executor_isolation_pass"] is True
    assert gate["checks"]["production_cdq_ownership_pass"] is True
    # P15 historical regression 不得 reclaim / 改变 production state
    overlay = DESIGN_DIR / "M11_OVERLAY_V2.json"
    ledger = DESIGN_DIR / "M11_REPAIR_SUBTYPE_LEDGER.json"
    recon = DESIGN_DIR / RUN_RECONCILIATION
    before = {name: _digest(path) for name, path in (
        ("overlay", overlay), ("ledger", ledger), ("recon", recon))}
    ContentRewritePolicyService(ROOT).reclassify()
    MicroRepairFrontierPlanner(ROOT).plan()
    Wave02Service(ROOT).scope()
    after = {name: _digest(path) for name, path in (
        ("overlay", overlay), ("ledger", ledger), ("recon", recon))}
    assert before == after
    assert payload["p15_isolation"]["status"] == "PASS"


# ---------------------------------------------------------------- overlay / readiness
def test_overlay_and_372_conservation(run04) -> None:
    service, payload = run04
    overlay = _artifact(DESIGN_DIR / "M11_OVERLAY_V2.json")
    assert overlay["conservation"] == {"primary_total": TARGET_COUNT,
                                       "target_count": TARGET_COUNT, "exact": True}
    assert list(overlay["primary_resolution_status_counts"]) == list(PRIMARY_BUCKETS)
    assert sum(overlay["primary_resolution_status_counts"].values()) == TARGET_COUNT
    # RUN-04 时点值冻结在 reconciliation（live overlay 会被 RUN-05+ 推进）
    reconciliation = _artifact(DESIGN_DIR / RUN_RECONCILIATION)
    assert reconciliation["promoted"] == 13
    assert reconciliation["promoted_evidence_only"] == 9
    assert reconciliation["promoted_no_repair_required"] == 4
    assert overlay["resolved_total"] >= 132
    assert overlay["repaired"] >= 102
    assert overlay["no_repair_required"] >= 30
    assert overlay["repaired_evidence_only"] >= 77
    assert overlay["repaired_field_rebind"] == 0
    assert overlay["repaired_micro_semantic"] == 21
    assert overlay["repaired_confirmed_override"] == 4
    assert overlay["content_design_required"] == 0  # [M11-CLOSURE] 已 terminal
    assert overlay["manual_required"] == 0  # [M11-CLOSURE] 已 terminal
    assert overlay["pending"] <= 191
    ledger = _artifact(DESIGN_DIR / "M11_REPAIR_SUBTYPE_LEDGER.json")
    assert len(ledger["ledger"]) == overlay["resolved_total"]
    assert ledger["resolved_subtype_counts"].get("repaired_micro_semantic") == 21
    assert payload["overlay_conservation"]["exact"] is True


def test_queue_conservation(run04) -> None:
    service, _payload = run04
    queue3 = _artifact(DESIGN_DIR / "M11_CONTENT_DESIGN_QUEUE_V3.json")
    active = [row for row in queue3["requirements"] if row["status"] == "ACTIVE"]
    overlay = _artifact(DESIGN_DIR / "M11_OVERLAY_V2.json")
    reconciliation = _artifact(DESIGN_DIR / "p15n" /
                               "CONTENT_DESIGN_QUEUE_RECONCILIATION.json")
    assert len(active) == overlay["content_design_required"]
    assert reconciliation["active_requirements"] == overlay["content_design_required"]
    assert reconciliation["orphan_requirements"] == []
    assert reconciliation["targets_without_requirement"] == []
    queue2 = _artifact(DESIGN_DIR / "M11_CONTENT_DESIGN_QUEUE_V2.json")
    ids = [row["design_item_id"] for row in queue2["items"]]
    assert len(ids) == len(set(ids))
    integration = service.readiness.integrate_dynamic_design_items()
    assert integration["new_item_count"] == 0
    assert _artifact(DESIGN_DIR / "M11_CONTENT_DESIGN_QUEUE_V2.json")["item_count"] == (
        queue2["item_count"])


def test_readiness_recompute(run04) -> None:
    service, payload = run04
    readiness = _artifact(DESIGN_DIR / "M11_READINESS_V2.json")
    assert len(readiness["batches"]) == 17
    assert readiness["completion_status_counts"] == {"COMPLETE": 17}  # [M11-CLOSURE] 372/372 terminal
    counts = readiness["execution_status_counts"]
    assert set(counts) <= {"READY", "PARTIAL_READY", "BLOCKED", "NO_WORK", "COMPLETE"}
    assert sum(counts.values()) == 17
    b04 = _batch(readiness, "REPAIR_BATCH_04")
    # 该 run 时点 = PARTIAL_READY；后续 run 会把 B04 推到 BLOCKED（frontier 前移）
    assert b04["completion_status"] == closed("IN_PROGRESS", "COMPLETE")
    assert b04["execution_status"] in closed(("PARTIAL_READY", "BLOCKED"), ("COMPLETE",))  # [M11-CLOSURE]
    # RUN-04 时点 = 16 resolved；后续 production run 会继续推进
    assert len(b04["resolved_target_ids"]) >= 16
    # RUN-04 时点 = 1（ch078 释放 ch080）；后续 run 继续推进 → 允许 0
    assert len(b04["ready_target_ids"]) <= 1
    assert len(b04["blocked_target_ids"]) <= 7
    b09 = _batch(readiness, BATCH_09)
    assert (b09["completion_status"], b09["execution_status"]) == closed(
        ("IN_PROGRESS", "BLOCKED"), ("COMPLETE", "COMPLETE"))
    assert len(b09["resolved_target_ids"]) == closed(12, 20)
    assert b09["ready_target_ids"] == []
    assert len(b09["blocked_target_ids"]) == closed(8, 0)
    assert payload["readiness"]["execution_status_counts"] == counts
    for row in readiness["batches"]:
        assert row["completion_status"] in ("NOT_STARTED", "IN_PROGRESS", "COMPLETE",
                                           "HUMAN_REVIEW")
        assert row["execution_status"] in ("READY", "PARTIAL_READY", "BLOCKED",
                                           "NO_WORK", "COMPLETE")
        assert not set(row["ready_target_ids"]) & set(row["blocked_target_ids"])


# ---------------------------------------------------------------- backlog / author / M12
def test_backlog_update(run04) -> None:
    service, payload = run04
    backlog = _artifact(DESIGN_DIR / "M11_PRODUCTION_BACKLOG.json")
    assert set(backlog["lane_counts"]) == set(BACKLOG_LANES)
    assert all(count >= 1 for count in backlog["lane_counts"].values())
    assert backlog["item_count"] == sum(backlog["lane_counts"].values())
    assert backlog["item_count"] >= 46
    assert backlog["last_run"] == RUN_ID
    done = {row["item_id"]: row for row in backlog["items"]
            if row["status"] == "DONE"}
    assert {"BL_AUTO_B06", "BL_AUTO_B07", "BL_AUTO_B08",
            "BL_AUTO_B09"} <= set(done)
    assert done["BL_AUTO_B09"]["completed_by_run"] == RUN_ID
    assert len(done["BL_AUTO_B09"]["completed_targets"]) == 14
    assert {"BL_AUTO_B06", "BL_AUTO_B07", "BL_AUTO_B08",
            "BL_AUTO_B09"} <= set(payload["backlog"]["done_item_ids"])
    assert payload["backlog"]["item_count"] == backlog["item_count"]


def test_no_author_auto_resolution_and_no_new_event(run04) -> None:
    service, payload = run04
    inventory = _artifact(DESIGN_DIR / "AUTHOR_ACTION_INVENTORY.json")
    assert inventory["policy_selection"]["auto_selected"] == ""
    assert inventory["policy_selection"]["author_selected"] == ""
    assert inventory["auto_resolved"] == 0
    assert payload["author_policy_selected"] is False
    assert payload["author_decisions_resolved"] == 0
    gate = _run_artifact("M11_RUN_04_GATE.json")
    assert gate["checks"]["no_author_policy_auto_selected"] is True
    assert gate["checks"]["no_author_decision_auto_resolved"] is True
    assert gate["checks"]["no_new_historical_event_promoted"] is True
    reconciliation = _artifact(DESIGN_DIR / RUN_RECONCILIATION)
    promoted = [row for row in reconciliation["records"]
                if row["new_resolution_status"] in ("RESOLVED_REPAIRED",
                                                    "RESOLVED_NO_REPAIR_REQUIRED")]
    assert all(row["repair_class"] in ("EVIDENCE_ONLY", "NO_REPAIR_REQUIRED")
               for row in promoted)
    assert payload["gate"]["new_historical_events"] == 0


def test_m12_remains_false(run04) -> None:
    service, payload = run04
    m12 = _artifact(DESIGN_DIR / "p15p/M12_ENTRY_CRITERIA.json")
    assert m12["criteria_count"] == 9
    assert m12["m12_entry_allowed"] is False
    assert m12["satisfied_count"] == len(m12["satisfied_criteria"])  # [M11-CLOSURE] P15p projection 自洽为准
    assert m12["unsatisfied_count"] == len(m12["unsatisfied_criteria"])  # [M11-CLOSURE]
    assert m12["blocking_count"] == len(m12["blocking_criteria"])  # [M11-CLOSURE]
    assert set(m12["blocking_criteria"]) <= set(m12["unsatisfied_criteria"])
    assert payload["m12"]["entry_allowed"] is False


def test_contract_gate_and_truth_digests_unchanged(run04) -> None:
    service, payload = run04
    baseline = _run_artifact("M11_RUN_04_BASELINE.json")
    now = service.frozen_digests()
    assert now["contract"] == baseline["frozen_contract"]["contract"]
    assert now["repair_gate"] == baseline["frozen_contract"]["repair_gate"]
    gate = _run_artifact("M11_RUN_04_GATE.json")
    assert gate["checks"]["frozen_contract_unchanged"] is True
    assert gate["checks"]["frozen_repair_gate_unchanged"] is True
    truth = service.truth_digests()
    assert truth["canon"] == FROZEN_SOURCE_DIGESTS["canon"]
    assert truth["story_state"] == FROZEN_SOURCE_DIGESTS["story_state"]
    assert truth["legacy"] == FROZEN_SOURCE_DIGESTS["legacy"]
    assert truth["chapter_ir"] == FROZEN_SOURCE_DIGESTS["chapter_ir"]
    assert truth["historical_foundation"] == FROZEN_FOUNDATION_DIGESTS
    assert gate["checks"]["truth_digests_unchanged"] is True
    assert gate["checks"]["confirmed_facts_changed_zero"] is True
    assert payload["gate"]["confirmed_facts_changed"] == 0


def test_field_rebind_not_manufactured(run04) -> None:
    service, payload = run04
    ledger = _artifact(DESIGN_DIR / "M11_REPAIR_SUBTYPE_LEDGER.json")
    field_rebind = ledger["resolved_subtype_counts"].get("repaired_field_rebind", 0)
    evidence_path = DESIGN_DIR / "PRODUCTION_CAPABILITY_EVIDENCE.json"
    if field_rebind:
        assert evidence_path.is_file()
        assert _artifact(evidence_path)["FIELD_REBIND"] == "PROVEN_BY_M11_RUN_04"
    else:
        assert payload["field_rebind_natural_end_to_end"] is False
        assert not evidence_path.is_file()


def test_run04_gate_pass_with_injected_evidence(run04) -> None:
    service, payload = run04
    gate = _run_artifact("M11_RUN_04_GATE.json")
    assert set(gate["failed_checks"]) <= {"full_pytest_pass", "validate_project_pass"}
    for key, value in gate["checks"].items():
        if key not in ("full_pytest_pass", "validate_project_pass"):
            assert value is True, key
    service.record_test_evidence(pytest_summary="injected", pytest_passed=1,
                                 validate_summary="injected")
    baseline = _run_artifact("M11_RUN_04_BASELINE.json")
    reconciliation = _artifact(DESIGN_DIR / RUN_RECONCILIATION)
    replay = service.run_gate(
        baseline=baseline,
        residual={"targets": payload["residual"]["targets"], "preflight": {
            "targets": _run_artifact("M11_RUN_04_BATCH04_PREFLIGHT.json")["targets"]}},
        frontier={"targets": payload["frontier"]["targets"],
                  "blocked_targets": _artifact(
                      DESIGN_DIR / BATCH_09_SCOPE_FILE)["blocked_target_ids"]},
        reconciliation=reconciliation,
        projections={"overlay": _artifact(DESIGN_DIR / "M11_OVERLAY_V2.json"),
                     "readiness": _artifact(DESIGN_DIR / "M11_READINESS_V2.json"),
                     "ledger": _artifact(DESIGN_DIR / "M11_REPAIR_SUBTYPE_LEDGER.json")},
        backlog=_artifact(DESIGN_DIR / "M11_PRODUCTION_BACKLOG.json"),
        contracts=[_run_artifact("M11_RUN_04_BATCH_04_ACCEPTANCE_CONTRACT.json"),
                   _run_artifact("M11_RUN_04_BATCH_09_ACCEPTANCE_CONTRACT.json")],
        evidence={"pytest": {"status": "PASS", "summary": "injected"},
                  "validate_project": {"status": "PASS", "summary": "injected"}})
    assert replay["status"] == "PASS"
    assert replay["failed_checks"] == []
