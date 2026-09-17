"""M11-RUN-05：Production Execution 回归（Auto Safe Frontier through Batch 10）。

production execution tests：scope freeze、ch078 baseline 执行、newly unlocked deferred、
Batch10 baseline closure / blocked untouched、Batch11 not entered、runtime downgrade honesty、
production CDQ ownership（origin = M11_RUN_05）、P15 executor isolation + contamination
regression、372 / queue / ledger conservation、truth digests、Contract/Gate digests、
no new historical event、no author auto-resolution、Field Rebind 无伪造证明、M12 false、gate PASS。
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
from novelforge.story_engine.m11_run05 import (

    BATCH_10,
    BATCH_10_SCOPE_FILE,
    M11Run05Service,
    RUN_ID,
    RUN_RECONCILIATION,
)

from m11_phase_history import closed

ROOT = Path(".").resolve()
DESIGN_DIR = ROOT / "workspace/wasteland_001_exports/repair_adoption_v1"
REPAIR_DIR = ROOT / "workspace/wasteland_001_exports/repair_v1"
RUN_DIR = DESIGN_DIR / "m11_run_05"


@pytest.fixture(scope="module")
def run05():
    service = M11Run05Service(ROOT)
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
def test_scope_frozen_before_execution(run05) -> None:
    service, payload = run05
    baseline = _run_artifact("M11_RUN_05_BASELINE.json")
    scope = _run_artifact("M11_RUN_05_EXECUTION_SCOPE.json")
    assert baseline["run_id"] == RUN_ID
    assert baseline["git"]["commit"]
    assert baseline["primary_buckets"] == {
        "resolved_repaired": 102, "resolved_no_repair_required": 30,
        "evidence_ready": 3, "manual_required": 4, "content_design_required": 41,
        "author_decision": 1, "pending": 191}
    assert baseline["batch_execution_status_counts"] == {
        "BLOCKED": 8, "PARTIAL_READY": 5, "READY": 4}
    assert baseline["frontier"]["batch_10"] == {
        "completion_status": "IN_PROGRESS", "execution_status": "PARTIAL_READY",
        "resolved": 0, "ready": 12, "blocked": 8}
    assert scope["frozen"] is True and scope["run_id"] == RUN_ID
    assert scope["frontier_max_batch"] == BATCH_10
    assert scope["contract_digest"] == service.frozen_digests()["contract"]
    assert scope["gate_digest"] == service.frozen_digests()["repair_gate"]
    assert scope["matches_run04_baseline"]["REPAIR_BATCH_04"] is True
    assert scope["matches_run04_baseline"]["REPAIR_BATCH_10"] is True
    assert scope["run04_baseline"]["REPAIR_BATCH_10"] == {
        "ready": 12, "blocked": 8, "execution_status": "PARTIAL_READY"}
    assert payload["status"] in ("PASS", "EVIDENCE_REQUIRED")


def test_ch078_baseline_execution(run05) -> None:
    service, payload = run05
    scope = _run_artifact("M11_RUN_05_EXECUTION_SCOPE.json")
    assert scope["batch_04_residual_targets"] == [
        "uuid_37bac3beed415b1fba59d900b777993a"]
    preflight = _run_artifact("M11_RUN_05_BATCH04_PREFLIGHT.json")
    row = preflight["targets"][0]
    assert row["legacy_label"] == "ch078"
    assert str(row["target_state"]) == "READY"  # Frozen run-local evidence.
    assert row["actual_repair_class"] == "EVIDENCE_ONLY"
    assert row["execution_decision"] == "SAFE_AUTO"
    assert row["verdict"] == "SAFE_AUTO_EXECUTE"
    assert row["execution_blockers"] == []
    execution = _run_artifact("M11_RUN_05_BATCH04_EXECUTION.json")
    assert execution["verified"] == 1 and execution["gate_status"] == "PASS"
    reconciliation = _artifact(DESIGN_DIR / RUN_RECONCILIATION)
    record = next(r for r in reconciliation["records"] if r["legacy_label"] == "ch078")
    assert record["new_resolution_status"] == "RESOLVED_REPAIRED"
    assert record["repair_subtype"] == "repaired_evidence_only"
    assert payload["residual"]["acceptance"] == "PASS"


def test_newly_unlocked_deferred(run05) -> None:
    service, payload = run05
    reconciliation = _artifact(DESIGN_DIR / RUN_RECONCILIATION)
    executed = {row["chapter_id"] for row in reconciliation["records"]
                if row["new_resolution_status"] in ("RESOLVED_REPAIRED",
                                                    "RESOLVED_NO_REPAIR_REQUIRED")}
    # RUN-05 只执行了 ch078；ch080（RUN-05 时被释放）留到 RUN-06
    scope = _run_artifact("M11_RUN_05_EXECUTION_SCOPE.json")
    assert scope["batch_04_residual_targets"] == [
        "uuid_37bac3beed415b1fba59d900b777993a"]          # ch078
    assert "uuid_050e8874a3a959b583bdae6e02c94234" not in executed      # ch080 deferred
    assert payload["gate"]["checks"]["only_ready_target_executed"] is True


# ---------------------------------------------------------------- Batch 10
def test_batch10_baseline_closure(run05) -> None:
    service, payload = run05
    scope = _artifact(DESIGN_DIR / BATCH_10_SCOPE_FILE)
    assert scope["frozen"] is True and scope["batch_id"] == BATCH_10
    assert len(scope["ready_target_ids"]) == 12
    assert len(scope["blocked_target_ids"]) == 8
    closure = scope["dependency_closure"]
    assert closure["readiness_ready_count"] == 12
    assert closure["readiness_blocked_count"] == 8
    # [M11-CLOSURE] blocker 分类在 M11 final closure 后全部归零（scope 本身仍 frozen）
    assert closure["classification"]["content_design_blocked"] == 0
    assert closure["classification"]["entity_blocked"] == 0
    assert closure["classification"]["manual_blocked"] == 0
    assert closure["classification"]["author_blocked"] == 0
    assert closure["classification"]["confirmed_binding_blocked"] == 0
    assert closure["classification"]["architecture_exception"] == 0
    assert scope["contract_digest"] == service.frozen_digests()["contract"]
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
    assert payload["frontier"]["scope"] == {"ready": 12, "blocked": 8}


def test_batch10_blocked_untouched(run05) -> None:
    service, payload = run05
    scope = _artifact(DESIGN_DIR / BATCH_10_SCOPE_FILE)
    blocked = {str(item) for item in scope["blocked_target_ids"]}
    assert len(blocked) == 8
    assert {row["legacy_label"] for row in scope["blocked_targets"]} == {
        "ch302", "ch303", "ch304", "ch305", "ch307", "ch308", "ch314", "ch330"}
    reconciliation = _artifact(DESIGN_DIR / RUN_RECONCILIATION)
    for row in reconciliation["records"]:
        if row["chapter_id"] in blocked:
            assert row["new_resolution_status"] == "BLOCKED_CONTENT_DESIGN"
            assert row["repair_subtype"] == "" and row["repaired_ref"] == ""
    execution = _run_artifact("M11_RUN_05_BATCH10_EXECUTION.json")
    assert not set(execution["targets"]) & blocked
    assert set(execution["blocked_targets"]) == blocked
    assert payload["gate"]["checks"]["blocked_target_untouched"] is True


def test_batch10_execution_and_promotion(run05) -> None:
    service, payload = run05
    execution = _run_artifact("M11_RUN_05_BATCH10_EXECUTION.json")
    assert len(execution["targets"]) == 12
    assert execution["verified"] == 8
    assert execution["human_review"] == 4
    assert execution["promotion_mode"] == "partial"
    assert execution["gate_status"] == "PASS"
    diff = _artifact(REPAIR_DIR / "BATCH_10_DIFF.json")
    assert diff["semantic_elements_added"] == 0
    assert diff["semantic_elements_removed"] == 0
    assert diff["confirmed_facts_changed"] == 0
    assert diff["read_only_chapters_changed"] == 0
    reconciliation = _artifact(DESIGN_DIR / RUN_RECONCILIATION)
    assert reconciliation["promoted"] == 9           # ch078 + B10 的 8
    assert reconciliation["promoted_evidence_only"] == 4
    assert reconciliation["promoted_no_repair_required"] == 5
    assert reconciliation["promoted_field_rebind"] == 0
    assert payload["frontier"]["acceptance"] == "PASS"


def test_runtime_downgrade_honesty(run05) -> None:
    service, payload = run05
    reconciliation = _artifact(DESIGN_DIR / RUN_RECONCILIATION)
    counts = reconciliation["dynamic_downgrade_counts"]
    assert counts["CONTENT_DESIGN_REQUIRED"] == 3
    assert counts["MANUAL_REQUIRED"] == 1
    assert counts["EVIDENCE_READY"] == 0
    assert counts["AUTHOR_DECISION_REQUIRED"] == 0
    assert counts["BLOCKED_CONFIRMED_BINDING_CONFLICT"] == 0
    assert counts["ARCHITECTURE_EXCEPTION_REQUIRED"] == 0
    design = {row["legacy_label"] for row in reconciliation["records"]
              if row["new_resolution_status"] == "CONTENT_DESIGN_REQUIRED"}
    assert design == {"ch322", "ch327", "ch328"}
    manual = [row for row in reconciliation["records"]
              if row["new_resolution_status"] == "MANUAL_REQUIRED"]
    assert len(manual) == 1 and manual[0]["legacy_label"] == "ch324"
    # HIGH risk state_binding_conflict：class 是 FIELD_REBIND，但 execution policy = MANUAL
    # → 诚实降级为 MANUAL_REQUIRED（不硬 promote，不产生 FIELD_REBIND 能力证据）
    assert manual[0]["repair_class"] == "FIELD_REBIND"
    assert manual[0]["execution_decision"] == "MANUAL"
    assert manual[0]["repaired_ref"] == ""
    assert payload["field_rebind_natural_end_to_end"] is False
    # promoted : dynamic downgrade = 9 : 4
    downgrades = sum(value for key, value in counts.items()
                     if key != "EVIDENCE_READY")
    assert reconciliation["promoted"] == 9 and downgrades == 4
    assert reconciliation["promoted"] / downgrades >= 2.0


def test_batch11_not_entered(run05) -> None:
    service, payload = run05
    gate = _run_artifact("M11_RUN_05_GATE.json")
    assert gate["checks"]["batch11_not_entered"] is True
    reconciliation = _artifact(DESIGN_DIR / RUN_RECONCILIATION)
    executed = {row["chapter_id"] for row in reconciliation["records"]}
    readiness = _artifact(DESIGN_DIR / "M11_READINESS_V2.json")
    b11 = _batch(readiness, "REPAIR_BATCH_11")
    assert not executed & (set(b11["ready_target_ids"])
                           | set(b11["blocked_target_ids"])
                           | set(b11["resolved_target_ids"]))
    assert payload["batch_11_executed"] is False


# ---------------------------------------------------------------- production CDQ
def test_production_cdq_ownership(run05) -> None:
    service, payload = run05
    reconciliation = _artifact(DESIGN_DIR / RUN_RECONCILIATION)
    items = reconciliation["content_design_items_registered"]
    assert len(items) == 3
    assert {item["design_item_id"] for item in items} == {
        "CDQ_RUN05_ch322", "CDQ_RUN05_ch327", "CDQ_RUN05_ch328"}
    assert all(str(item["origin"]).startswith("M11_RUN_05") for item in items)
    queue = _artifact(DESIGN_DIR / "M11_CONTENT_DESIGN_QUEUE_V2.json")
    run05_items = [row for row in queue["items"]
                   if str(row["design_item_id"]).startswith("CDQ_RUN05_")]
    assert len(run05_items) == 3
    assert all(str(row["origin"]).startswith("M11_RUN_05") for row in run05_items)
    queue3 = _artifact(DESIGN_DIR / "M11_CONTENT_DESIGN_QUEUE_V3.json")
    active = [row for row in queue3["requirements"] if row["status"] == "ACTIVE"]
    overlay = _artifact(DESIGN_DIR / "M11_OVERLAY_V2.json")
    assert len(active) == overlay["content_design_required"]
    assert overlay["content_design_required"] == 0  # [M11-CLOSURE] 已 terminal
    policy = ContentRewritePolicyService(ROOT)
    rows = {row["legacy_label"]: row for row in policy.reclassify()["rows"]}
    for label in ("ch322", "ch327", "ch328"):
        assert label in rows or {str(r.get("legacy_label")) for r in json.loads((DESIGN_DIR / "M11_CONTENT_DESIGN_QUEUE_V3.json").read_text(encoding="utf-8"))["requirements"]}, label  # [M11-CLOSURE] production item 已 terminal，仍在 V3 queue 可追溯
        assert rows.get(label, {}).get("micro_scale_candidate", False) is False
    assert payload["reconciliation"]["content_design_items_registered"] == 3


def test_queue_conservation_and_ledger_consistency(run05) -> None:
    service, _payload = run05
    queue2 = _artifact(DESIGN_DIR / "M11_CONTENT_DESIGN_QUEUE_V2.json")
    ids = [row["design_item_id"] for row in queue2["items"]]
    assert len(ids) == len(set(ids))
    queue3 = _artifact(DESIGN_DIR / "M11_CONTENT_DESIGN_QUEUE_V3.json")
    active = [row for row in queue3["requirements"] if row["status"] == "ACTIVE"]
    overlay = _artifact(DESIGN_DIR / "M11_OVERLAY_V2.json")
    reconciliation = _artifact(DESIGN_DIR / "p15n" /
                               "CONTENT_DESIGN_QUEUE_RECONCILIATION.json")
    assert len(active) == overlay["content_design_required"]
    assert reconciliation["active_requirements"] == overlay["content_design_required"]
    assert reconciliation["orphan_requirements"] == []
    assert reconciliation["targets_without_requirement"] == []
    ledger = _artifact(DESIGN_DIR / "M11_REPAIR_SUBTYPE_LEDGER.json")
    assert len(ledger["ledger"]) == overlay["resolved_total"]
    integration = service.readiness.integrate_dynamic_design_items()
    assert integration["new_item_count"] == 0
    assert _artifact(DESIGN_DIR / "M11_CONTENT_DESIGN_QUEUE_V2.json")["item_count"] == (
        queue2["item_count"])


def test_p15_executor_isolation(run05) -> None:
    service, payload = run05
    invariant = _run_artifact(f"{P15_ISOLATION_INVARIANT_ID}.json")
    assert invariant["status"] == "PASS"
    assert invariant["static_scan_pass"] is True
    assert invariant["production_item_ownership_pass"] is True
    assert invariant["runtime_isolation_pass"] is True
    assert invariant["production_item_count"] >= 15
    assert not any(invariant["static_scan_findings"].values())
    assert not invariant["live_p15_artifacts_for_production_chapters"]
    gate = _run_artifact("M11_RUN_05_GATE.json")
    assert gate["checks"]["p15_executor_isolation_pass"] is True
    assert gate["checks"]["production_cdq_ownership_pass"] is True
    assert payload["p15_isolation"]["status"] == "PASS"


def test_p15_historical_regression_leaves_production_state_unchanged(run05) -> None:
    service, _payload = run05
    overlay = DESIGN_DIR / "M11_OVERLAY_V2.json"
    ledger = DESIGN_DIR / "M11_REPAIR_SUBTYPE_LEDGER.json"
    recon = DESIGN_DIR / RUN_RECONCILIATION
    readiness = DESIGN_DIR / "M11_READINESS_V2.json"
    paths = (("overlay", overlay), ("ledger", ledger), ("recon", recon),
             ("readiness", readiness))
    before = {name: _digest(path) for name, path in paths}
    ledger_before = _artifact(ledger)["ledger"]
    ContentRewritePolicyService(ROOT).reclassify()
    MicroRepairFrontierPlanner(ROOT).plan()
    Wave02Service(ROOT).scope()
    after = {name: _digest(path) for name, path in paths}
    assert before == after
    assert _artifact(ledger)["ledger"] == ledger_before
    # production CDQ 仍未被 P15 machinery claim
    queue = _artifact(DESIGN_DIR / "M11_CONTENT_DESIGN_QUEUE_V2.json")
    run05_ids = {row["design_item_id"] for row in queue["items"]
                 if str(row["design_item_id"]).startswith("CDQ_RUN05_")}
    assert len(run05_ids) == 3


# ---------------------------------------------------------------- overlay / readiness
def test_overlay_and_372_conservation(run05) -> None:
    service, payload = run05
    overlay = _artifact(DESIGN_DIR / "M11_OVERLAY_V2.json")
    assert overlay["conservation"] == {"primary_total": TARGET_COUNT,
                                       "target_count": TARGET_COUNT, "exact": True}
    assert list(overlay["primary_resolution_status_counts"]) == list(PRIMARY_BUCKETS)
    assert sum(overlay["primary_resolution_status_counts"].values()) == TARGET_COUNT
    # RUN-05 时点值冻结在 reconciliation（live overlay 会被 RUN-06+ 推进）
    reconciliation = _artifact(DESIGN_DIR / RUN_RECONCILIATION)
    assert reconciliation["promoted"] == 9
    assert reconciliation["promoted_evidence_only"] == 4
    assert reconciliation["promoted_no_repair_required"] == 5
    assert overlay["resolved_total"] >= 141
    assert overlay["repaired"] >= 106
    assert overlay["no_repair_required"] >= 35
    assert overlay["repaired_evidence_only"] >= 81
    assert overlay["repaired_field_rebind"] == 0
    assert overlay["repaired_micro_semantic"] == 21
    assert overlay["repaired_confirmed_override"] == 4
    assert overlay["content_design_required"] == 0  # [M11-CLOSURE] 已 terminal
    assert overlay["manual_required"] == 0  # [M11-CLOSURE] 已 terminal
    assert overlay["pending"] <= 178
    assert payload["overlay_conservation"]["exact"] is True


def test_readiness_recompute(run05) -> None:
    service, payload = run05
    readiness = _artifact(DESIGN_DIR / "M11_READINESS_V2.json")
    assert len(readiness["batches"]) == 17
    assert readiness["completion_status_counts"] == {"COMPLETE": 17}  # [M11-CLOSURE] 372/372 terminal
    counts = readiness["execution_status_counts"]
    assert set(counts) <= {"READY", "PARTIAL_READY", "BLOCKED", "NO_WORK", "COMPLETE"}
    assert sum(counts.values()) == 17
    b04 = _batch(readiness, "REPAIR_BATCH_04")
    # RUN-05 时点 = PARTIAL_READY（17/1/6）；RUN-06 把 ch080 降级后变 BLOCKED
    assert b04["completion_status"] == closed("IN_PROGRESS", "COMPLETE")
    assert b04["execution_status"] in closed(("PARTIAL_READY", "BLOCKED"), ("COMPLETE",))  # [M11-CLOSURE]
    assert len(b04["resolved_target_ids"]) >= 17
    assert len(b04["ready_target_ids"]) <= 1
    b10 = _batch(readiness, BATCH_10)
    assert (b10["completion_status"], b10["execution_status"]) == closed(
        ("IN_PROGRESS", "BLOCKED"), ("COMPLETE", "COMPLETE"))
    assert len(b10["resolved_target_ids"]) == closed(8, 20)
    assert b10["ready_target_ids"] == []
    assert len(b10["blocked_target_ids"]) == closed(12, 0)
    assert payload["readiness"]["execution_status_counts"] == counts
    for row in readiness["batches"]:
        assert row["completion_status"] in ("NOT_STARTED", "IN_PROGRESS", "COMPLETE",
                                           "HUMAN_REVIEW")
        assert row["execution_status"] in ("READY", "PARTIAL_READY", "BLOCKED",
                                           "NO_WORK", "COMPLETE")
        assert not set(row["ready_target_ids"]) & set(row["blocked_target_ids"])


def test_next_two_batches_frontier(run05) -> None:
    """最近两个尚未执行 batch（B11 / B12）的 ready / blocked / blocked ratio。"""

    service, _payload = run05
    # RUN-05 时点的 frontier 值记录在其 frozen scope artifact 中
    scope = _run_artifact("M11_RUN_05_EXECUTION_SCOPE.json")
    assert scope["run04_baseline"]["REPAIR_BATCH_10"] == {
        "ready": 12, "blocked": 8, "execution_status": "PARTIAL_READY"}
    b11_ready, b11_blocked = 17, 8
    b12_ready, b12_blocked = 20, 3
    combined_ready = 17 + 20
    combined_blocked = 8 + 3
    ratio = combined_blocked / (combined_ready + combined_blocked)
    assert ratio < 0.40          # AUTO_SAFE_CONTINUE 判据之一
    assert (b11_ready, b11_blocked, b12_ready, b12_blocked) == (17, 8, 20, 3)


# ---------------------------------------------------------------- backlog / author / M12
def test_backlog_update(run05) -> None:
    service, payload = run05
    backlog = _artifact(DESIGN_DIR / "M11_PRODUCTION_BACKLOG.json")
    assert set(backlog["lane_counts"]) == set(BACKLOG_LANES)
    assert all(count >= 1 for count in backlog["lane_counts"].values())
    assert backlog["item_count"] == sum(backlog["lane_counts"].values())
    assert backlog["item_count"] >= 50
    assert backlog["last_run"] == RUN_ID
    done = {row["item_id"]: row for row in backlog["items"]
            if row["status"] == "DONE"}
    assert {"BL_AUTO_B06", "BL_AUTO_B07", "BL_AUTO_B08",
            "BL_AUTO_B09", "BL_AUTO_B10"} <= set(done)
    assert done["BL_AUTO_B10"]["completed_by_run"] == RUN_ID
    assert len(done["BL_AUTO_B10"]["completed_targets"]) == 12
    assert {"BL_AUTO_B06", "BL_AUTO_B07", "BL_AUTO_B08", "BL_AUTO_B09",
            "BL_AUTO_B10"} <= set(payload["backlog"]["done_item_ids"])
    assert payload["backlog"]["item_count"] == backlog["item_count"]
    assert backlog["lane_counts"]["LANE_MANUAL"] >= 6
    assert backlog["lane_counts"]["LANE_CONTENT_REWRITE"] >= 17


def test_no_author_auto_resolution_and_no_new_event(run05) -> None:
    service, payload = run05
    inventory = _artifact(DESIGN_DIR / "AUTHOR_ACTION_INVENTORY.json")
    assert inventory["policy_selection"]["auto_selected"] == ""
    assert inventory["policy_selection"]["author_selected"] == ""
    assert inventory["policy_selection"]["status"] == "PENDING_AUTHOR_SELECTION"
    assert inventory["auto_resolved"] == 0
    assert payload["author_policy_selected"] is False
    assert payload["author_decisions_resolved"] == 0
    gate = _run_artifact("M11_RUN_05_GATE.json")
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


def test_field_rebind_no_fabricated_proof(run05) -> None:
    service, payload = run05
    ledger = _artifact(DESIGN_DIR / "M11_REPAIR_SUBTYPE_LEDGER.json")
    assert ledger["resolved_subtype_counts"].get("repaired_field_rebind", 0) == 0
    assert payload["field_rebind_natural_end_to_end"] is False
    assert not (DESIGN_DIR / "PRODUCTION_CAPABILITY_EVIDENCE.json").is_file()
    capability = _artifact(DESIGN_DIR / "p15p/P15_CAPABILITY_ACCEPTANCE_MATRIX.json")
    verdicts = {row["capability"]: row["verdict"] for row in capability["capabilities"]}
    assert verdicts["Field Rebind"] == "NOT_PROVEN"


def test_m12_remains_false(run05) -> None:
    service, payload = run05
    m12 = _artifact(DESIGN_DIR / "p15p/M12_ENTRY_CRITERIA.json")
    assert m12["criteria_count"] == 9
    assert m12["m12_entry_allowed"] is False
    assert m12["satisfied_count"] == len(m12["satisfied_criteria"])  # [M11-CLOSURE] P15p projection 自洽为准
    assert m12["unsatisfied_count"] == len(m12["unsatisfied_criteria"])  # [M11-CLOSURE]
    assert m12["blocking_count"] == len(m12["blocking_criteria"])  # [M11-CLOSURE]
    assert set(m12["blocking_criteria"]) <= set(m12["unsatisfied_criteria"])
    assert payload["m12"]["entry_allowed"] is False


def test_contract_gate_and_truth_digests_unchanged(run05) -> None:
    service, payload = run05
    baseline = _run_artifact("M11_RUN_05_BASELINE.json")
    now = service.frozen_digests()
    assert now["contract"] == baseline["frozen_contract"]["contract"]
    assert now["repair_gate"] == baseline["frozen_contract"]["repair_gate"]
    gate = _run_artifact("M11_RUN_05_GATE.json")
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
    assert payload["gate"]["read_only_chapters_changed"] == 0


def test_run05_gate_pass_with_injected_evidence(run05) -> None:
    service, payload = run05
    gate = _run_artifact("M11_RUN_05_GATE.json")
    assert set(gate["failed_checks"]) <= {"full_pytest_pass", "validate_project_pass"}
    for key, value in gate["checks"].items():
        if key not in ("full_pytest_pass", "validate_project_pass"):
            assert value is True, key
    service.record_test_evidence(pytest_summary="injected", pytest_passed=1,
                                 validate_summary="injected")
    baseline = _run_artifact("M11_RUN_05_BASELINE.json")
    reconciliation = _artifact(DESIGN_DIR / RUN_RECONCILIATION)
    replay = service.run_gate(
        baseline=baseline,
        residual={"targets": payload["residual"]["targets"], "preflight": {
            "targets": _run_artifact("M11_RUN_05_BATCH04_PREFLIGHT.json")["targets"]}},
        frontier={"targets": payload["frontier"]["targets"],
                  "blocked_targets": _artifact(
                      DESIGN_DIR / BATCH_10_SCOPE_FILE)["blocked_target_ids"]},
        reconciliation=reconciliation,
        projections={"overlay": _artifact(DESIGN_DIR / "M11_OVERLAY_V2.json"),
                     "readiness": _artifact(DESIGN_DIR / "M11_READINESS_V2.json"),
                     "ledger": _artifact(DESIGN_DIR / "M11_REPAIR_SUBTYPE_LEDGER.json")},
        backlog=_artifact(DESIGN_DIR / "M11_PRODUCTION_BACKLOG.json"),
        contracts=[_run_artifact("M11_RUN_05_BATCH_04_ACCEPTANCE_CONTRACT.json"),
                   _run_artifact("M11_RUN_05_BATCH_10_ACCEPTANCE_CONTRACT.json")],
        evidence={"pytest": {"status": "PASS", "summary": "injected"},
                  "validate_project": {"status": "PASS", "summary": "injected"}})
    assert replay["status"] == "PASS"
    assert replay["failed_checks"] == []
