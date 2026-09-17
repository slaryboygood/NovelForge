"""M11-RUN-08：Production Execution 回归（Auto Safe Frontier through Batch 13）。"""

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
from novelforge.story_engine.m11_run08 import (
    BATCH_13,
    BATCH_13_SCOPE_FILE,
    M11Run08Service,
    RUN_ID,
    RUN_RECONCILIATION,
)

from m11_phase_history import closed
ROOT = Path(".").resolve()
DESIGN_DIR = ROOT / "workspace/wasteland_001_exports/repair_adoption_v1"
REPAIR_DIR = ROOT / "workspace/wasteland_001_exports/repair_v1"
RUN_DIR = DESIGN_DIR / "m11_run_08"
EXECUTED_BATCHES = {f"REPAIR_BATCH_{index:02d}" for index in range(1, 14)}


@pytest.fixture(scope="module")
def run08():
    service = M11Run08Service(ROOT)
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


def _two_most_recent_unexecuted(readiness: dict) -> list[dict]:
    return [row for row in readiness["batches"]
            if row["batch_id"] not in EXECUTED_BATCHES][:2]


# ---------------------------------------------------------------- scope freeze
def test_scope_frozen_before_execution(run08) -> None:
    service, payload = run08
    baseline = _run_artifact("M11_RUN_08_BASELINE.json")
    scope = _run_artifact("M11_RUN_08_EXECUTION_SCOPE.json")
    assert baseline["run_id"] == RUN_ID
    assert baseline["primary_buckets"] == {
        "resolved_repaired": 127, "resolved_no_repair_required": 40,
        "evidence_ready": 3, "manual_required": 7, "content_design_required": 47,
        "author_decision": 2, "pending": 146}
    assert baseline["batch_execution_status_counts"] == {
        "BLOCKED": 12, "PARTIAL_READY": 1, "READY": 4}
    assert baseline["frontier"]["batch_13"] == {
        "completion_status": "IN_PROGRESS", "execution_status": "PARTIAL_READY",
        "resolved": 1, "ready": 15, "blocked": 7}
    assert scope["frozen"] is True and scope["run_id"] == RUN_ID
    assert scope["frontier_max_batch"] == BATCH_13
    assert scope["contract_digest"] == service.frozen_digests()["contract"]
    assert scope["gate_digest"] == service.frozen_digests()["repair_gate"]
    assert scope["matches_run07_baseline"]["REPAIR_BATCH_13"] is True
    assert scope["run07_baseline"]["REPAIR_BATCH_13"] == {
        "ready": 15, "blocked": 7, "execution_status": "PARTIAL_READY"}
    assert payload["status"] in ("PASS", "EVIDENCE_REQUIRED")


def test_no_residual_auto_safe_target_before_batch13(run08) -> None:
    service, payload = run08
    scope = _run_artifact("M11_RUN_08_EXECUTION_SCOPE.json")
    assert scope["batch_04_residual_targets"] == []
    readiness = _artifact(DESIGN_DIR / "M11_READINESS_V2.json")
    for index in range(1, 13):
        row = _batch(readiness, f"REPAIR_BATCH_{index:02d}")
        assert row["ready_target_ids"] == []
    assert payload["residual"]["preflight_verdict"] == "NO_READY_TARGET"
    assert payload["residual"]["acceptance"] == "PASS"


def test_batch13_baseline_recomputed_and_closure(run08) -> None:
    service, payload = run08
    scope = _artifact(DESIGN_DIR / BATCH_13_SCOPE_FILE)
    assert scope["frozen"] is True and scope["batch_id"] == BATCH_13
    assert len(scope["ready_target_ids"]) == 15
    assert len(scope["blocked_target_ids"]) == 7
    closure = scope["dependency_closure"]
    assert closure["readiness_ready_count"] == 15
    assert closure["readiness_blocked_count"] == 7
    assert closure["classification"]["safe_executable"] == 15
    assert closure["classification"]["manual_blocked"] == 0  # [M11-CLOSURE]
    assert closure["classification"]["entity_blocked"] == 0  # [M11-CLOSURE]
    assert closure["classification"]["architecture_exception"] == 0
    assert scope["baseline_truth_digests"]["canon"] == FROZEN_SOURCE_DIGESTS["canon"]
    history = _artifact(DESIGN_DIR / RUN_RECONCILIATION)
    historical = {r["chapter_id"]: r for r in history["records"]}
    live = _artifact(DESIGN_DIR / "M11_READINESS_V2.json")
    resolved = {cid for b in live["batches"] for cid in b["resolved_target_ids"]}
    for row in scope["targets"]:
        # Scope rows mix retained preflight and recomputed fields; use run history.
        assert historical[row["chapter_id"]]["old_status"] == "not_processed"
        assert row["chapter_id"] in resolved
        assert row["ready_reason"]
    assert payload["frontier"]["scope"] == {"ready": 15, "blocked": 7}


def test_batch13_blocked_untouched(run08) -> None:
    service, payload = run08
    scope = _artifact(DESIGN_DIR / BATCH_13_SCOPE_FILE)
    blocked = {str(item) for item in scope["blocked_target_ids"]}
    assert len(blocked) == 7
    assert {row["legacy_label"] for row in scope["blocked_targets"]} == {
        "ch414", "ch415", "ch416", "ch417", "ch418", "ch420", "ch430"}
    reconciliation = _artifact(DESIGN_DIR / RUN_RECONCILIATION)
    for row in reconciliation["records"]:
        if row["chapter_id"] in blocked:
            assert row["new_resolution_status"] == "BLOCKED_CONTENT_DESIGN"
            assert row["repair_subtype"] == "" and row["repaired_ref"] == ""
    execution = _run_artifact("M11_RUN_08_BATCH13_EXECUTION.json")
    assert not set(execution["targets"]) & blocked
    assert set(execution["blocked_targets"]) == blocked
    assert payload["gate"]["checks"]["blocked_target_untouched"] is True


def test_batch13_execution_and_promotion(run08) -> None:
    service, payload = run08
    execution = _run_artifact("M11_RUN_08_BATCH13_EXECUTION.json")
    assert len(execution["targets"]) == 15
    assert execution["verified"] == 10
    assert execution["human_review"] == 5
    assert execution["promotion_mode"] == "partial"
    assert execution["gate_status"] == "PASS"
    diff = _artifact(REPAIR_DIR / "BATCH_13_DIFF.json")
    assert diff["semantic_elements_added"] == 0
    assert diff["semantic_elements_removed"] == 0
    assert diff["confirmed_facts_changed"] == 0
    assert diff["read_only_chapters_changed"] == 0
    reconciliation = _artifact(DESIGN_DIR / RUN_RECONCILIATION)
    assert reconciliation["promoted"] == 10
    assert reconciliation["promoted_evidence_only"] == 6
    assert reconciliation["promoted_no_repair_required"] == 4
    assert reconciliation["promoted_field_rebind"] == 0
    assert payload["frontier"]["acceptance"] == "PASS"


def test_dynamic_downgrade_honesty(run08) -> None:
    service, payload = run08
    reconciliation = _artifact(DESIGN_DIR / RUN_RECONCILIATION)
    counts = reconciliation["dynamic_downgrade_counts"]
    assert counts["CONTENT_DESIGN_REQUIRED"] == 2          # ch424 / ch427
    assert counts["MANUAL_REQUIRED"] == 3                  # ch425 / ch445 / ch446
    assert counts["EVIDENCE_READY"] == 0
    assert counts["AUTHOR_DECISION_REQUIRED"] == 0
    assert counts["BLOCKED_CONFIRMED_BINDING_CONFLICT"] == 0
    assert counts["ARCHITECTURE_EXCEPTION_REQUIRED"] == 0
    design = {row["legacy_label"] for row in reconciliation["records"]
              if row["new_resolution_status"] == "CONTENT_DESIGN_REQUIRED"}
    assert design == {"ch424", "ch427"}
    manual = {row["legacy_label"] for row in reconciliation["records"]
              if row["new_resolution_status"] == "MANUAL_REQUIRED"}
    assert manual == {"ch425", "ch445", "ch446"}
    # promoted : dynamic downgrade = 10 : 5 = 2.0 : 1（恰在阈值上）
    downgrades = sum(value for key, value in counts.items() if key != "EVIDENCE_READY")
    assert reconciliation["promoted"] == 10 and downgrades == 5
    assert reconciliation["promoted"] / downgrades >= 2.0
    assert payload["frontier"]["verified"] == 10


def test_unsafe_field_rebind_cannot_promote(run08) -> None:
    """ch425 / ch445：class = FIELD_REBIND 但 risk = HIGH → MANUAL，不得 promote。"""

    service, payload = run08
    reconciliation = _artifact(DESIGN_DIR / RUN_RECONCILIATION)
    unsafe = [row for row in reconciliation["records"]
              if row["legacy_label"] in ("ch425", "ch445")]
    assert len(unsafe) == 2
    for row in unsafe:
        assert row["new_resolution_status"] == "MANUAL_REQUIRED"
        assert row["repair_class"] == "FIELD_REBIND"
        assert row["execution_decision"] == "MANUAL"
        assert row["repaired_ref"] == ""
    # 没有 SAFE_AUTO promotion 携带 FIELD_REBIND → capability 仍 NOT_PROVEN
    assert reconciliation["promoted_field_rebind"] == 0
    ledger = _artifact(DESIGN_DIR / "M11_REPAIR_SUBTYPE_LEDGER.json")
    assert ledger["resolved_subtype_counts"].get("repaired_field_rebind", 0) == 0
    assert payload["field_rebind_natural_end_to_end"] is False
    assert not (DESIGN_DIR / "PRODUCTION_CAPABILITY_EVIDENCE.json").is_file()
    capability = _artifact(DESIGN_DIR / "p15p/P15_CAPABILITY_ACCEPTANCE_MATRIX.json")
    verdicts = {row["capability"]: row["verdict"] for row in capability["capabilities"]}
    assert verdicts["Field Rebind"] == "NOT_PROVEN"


def test_event_added_cannot_safe_auto(run08) -> None:
    service, payload = run08
    reconciliation = _artifact(DESIGN_DIR / RUN_RECONCILIATION)
    promoted = [row for row in reconciliation["records"]
                if row["new_resolution_status"] in ("RESOLVED_REPAIRED",
                                                    "RESOLVED_NO_REPAIR_REQUIRED")]
    allowed_ops = {"REBIND_EVIDENCE", "MARK_NOT_APPLICABLE", "RECLASSIFY_FUNCTION",
                   "REBIND_STATE_REFERENCE"}
    assert all(op in allowed_ops for row in promoted for op in row["patch_ops"])
    gate = _run_artifact("M11_RUN_08_GATE.json")
    assert gate["checks"]["no_new_historical_event_promoted"] is True
    assert payload["gate"]["new_historical_events"] == 0


# ---------------------------------------------------------------- production CDQ
def test_production_cdq_origin_and_ownership(run08) -> None:
    service, payload = run08
    reconciliation = _artifact(DESIGN_DIR / RUN_RECONCILIATION)
    items = reconciliation["content_design_items_registered"]
    assert {item["design_item_id"] for item in items} == {
        "CDQ_RUN08_ch424", "CDQ_RUN08_ch427"}
    assert all(str(item["origin"]).startswith("M11_RUN_08") for item in items)
    queue = _artifact(DESIGN_DIR / "M11_CONTENT_DESIGN_QUEUE_V2.json")
    run08_items = [row for row in queue["items"]
                   if str(row["design_item_id"]).startswith("CDQ_RUN08_")]
    assert len(run08_items) == 2
    assert all(str(row["origin"]).startswith("M11_RUN_08") for row in run08_items)
    policy = ContentRewritePolicyService(ROOT)
    rows = {row["legacy_label"]: row for row in policy.reclassify()["rows"]}
    queue_status = {str(row.get("legacy_label")): str(row.get("status"))
                    for row in _artifact(
                        DESIGN_DIR / "M11_CONTENT_DESIGN_QUEUE_V3.json")["requirements"]}
    for label in ("ch424", "ch427"):
        # [M11-CLOSURE] production CDQ item 已 terminal（从 active reclassification 视图移出）；
        # 仍必须在 production CDQ queue 中可追溯
        assert str(queue_status.get(label, "")).startswith("RESOLVED"), label
        assert rows.get(label, {}).get("micro_scale_candidate", False) is False
    invariant = _run_artifact(f"{P15_ISOLATION_INVARIANT_ID}.json")
    assert invariant["production_item_ownership_pass"] is True
    assert invariant["production_item_count"] >= 20
    assert payload["reconciliation"]["content_design_items_registered"] == 2


def test_queue_conservation_and_ledger_consistency(run08) -> None:
    service, _payload = run08
    queue2 = _artifact(DESIGN_DIR / "M11_CONTENT_DESIGN_QUEUE_V2.json")
    ids = [row["design_item_id"] for row in queue2["items"]]
    assert len(ids) == len(set(ids))
    assert len(ids) >= 63
    # RUN-07 的 61 → RUN-08 的 63：+2，且旧 ID 无丢失
    run08_ids = {row["design_item_id"] for row in queue2["items"]
                 if str(row["design_item_id"]).startswith("CDQ_RUN08_")}
    assert run08_ids == {"CDQ_RUN08_ch424", "CDQ_RUN08_ch427"}
    assert len(ids) - len(run08_ids) >= 61
    queue3 = _artifact(DESIGN_DIR / "M11_CONTENT_DESIGN_QUEUE_V3.json")
    active = [row for row in queue3["requirements"] if row["status"] == "ACTIVE"]
    overlay = _artifact(DESIGN_DIR / "M11_OVERLAY_V2.json")
    reconciliation = _artifact(DESIGN_DIR / "p15n" /
                               "CONTENT_DESIGN_QUEUE_RECONCILIATION.json")
    assert len(active) == overlay["content_design_required"]
    assert overlay["content_design_required"] == 0  # [M11-CLOSURE] 已 terminal
    assert reconciliation["active_requirements"] == overlay["content_design_required"]
    assert reconciliation["orphan_requirements"] == []
    assert reconciliation["targets_without_requirement"] == []
    integration = service.readiness.integrate_dynamic_design_items()
    assert integration["new_item_count"] == 0
    ledger = _artifact(DESIGN_DIR / "M11_REPAIR_SUBTYPE_LEDGER.json")
    assert len(ledger["ledger"]) == overlay["resolved_total"]
    assert overlay["resolved_total"] >= 177


def test_p15_executor_isolation_and_regression(run08) -> None:
    service, payload = run08
    invariant = _run_artifact(f"{P15_ISOLATION_INVARIANT_ID}.json")
    assert invariant["status"] == "PASS"
    assert invariant["static_scan_pass"] is True
    assert invariant["runtime_isolation_pass"] is True
    assert not any(invariant["static_scan_findings"].values())
    assert not invariant["live_p15_artifacts_for_production_chapters"]
    gate = _run_artifact("M11_RUN_08_GATE.json")
    assert gate["checks"]["p15_executor_isolation_pass"] is True
    assert gate["checks"]["production_cdq_ownership_pass"] is True
    overlay = DESIGN_DIR / "M11_OVERLAY_V2.json"
    readiness = DESIGN_DIR / "M11_READINESS_V2.json"
    ledger = DESIGN_DIR / "M11_REPAIR_SUBTYPE_LEDGER.json"
    recon = DESIGN_DIR / RUN_RECONCILIATION
    paths = (("overlay", overlay), ("readiness", readiness), ("ledger", ledger),
             ("recon", recon))
    before = {name: _digest(path) for name, path in paths}
    ContentRewritePolicyService(ROOT).reclassify()
    MicroRepairFrontierPlanner(ROOT).plan()
    Wave02Service(ROOT).scope()
    after = {name: _digest(path) for name, path in paths}
    assert before == after
    assert payload["p15_isolation"]["status"] == "PASS"


def test_batch14_not_entered(run08) -> None:
    service, payload = run08
    gate = _run_artifact("M11_RUN_08_GATE.json")
    assert gate["checks"]["batch14_not_entered"] is True
    reconciliation = _artifact(DESIGN_DIR / RUN_RECONCILIATION)
    executed = {row["chapter_id"] for row in reconciliation["records"]}
    readiness = _artifact(DESIGN_DIR / "M11_READINESS_V2.json")
    b14 = _batch(readiness, "REPAIR_BATCH_14")
    assert not executed & (set(b14["ready_target_ids"])
                           | set(b14["blocked_target_ids"])
                           | set(b14["resolved_target_ids"]))
    assert payload["batch_14_executed"] is False


# ---------------------------------------------------------------- overlay / readiness
def test_overlay_and_372_conservation(run08) -> None:
    service, payload = run08
    overlay = _artifact(DESIGN_DIR / "M11_OVERLAY_V2.json")
    assert overlay["conservation"] == {"primary_total": TARGET_COUNT,
                                       "target_count": TARGET_COUNT, "exact": True}
    assert list(overlay["primary_resolution_status_counts"]) == list(PRIMARY_BUCKETS)
    assert sum(overlay["primary_resolution_status_counts"].values()) == TARGET_COUNT
    # RUN-08 时点值冻结在 reconciliation（live overlay 会被 RUN-09+ 推进）
    reconciliation = _artifact(DESIGN_DIR / RUN_RECONCILIATION)
    assert reconciliation["promoted"] == 10
    assert reconciliation["promoted_evidence_only"] == 6
    assert reconciliation["promoted_no_repair_required"] == 4
    assert overlay["resolved_total"] >= 177
    assert overlay["repaired"] >= 133
    assert overlay["no_repair_required"] >= 44
    assert overlay["repaired_evidence_only"] >= 108
    assert overlay["repaired_field_rebind"] == 0
    assert overlay["repaired_micro_semantic"] == 21
    assert overlay["repaired_confirmed_override"] == 4
    assert overlay["content_design_required"] == 0  # [M11-CLOSURE] 已 terminal
    assert overlay["manual_required"] == 0  # [M11-CLOSURE] 已 terminal
    assert overlay["author_decision"] == 0  # [M11-CLOSURE] author lane 已 terminal
    assert overlay["pending"] <= 131
    assert payload["overlay_conservation"]["exact"] is True


def test_readiness_recompute(run08) -> None:
    service, payload = run08
    readiness = _artifact(DESIGN_DIR / "M11_READINESS_V2.json")
    assert len(readiness["batches"]) == 17
    assert readiness["completion_status_counts"] == {"COMPLETE": 17}  # [M11-CLOSURE] 372/372 terminal
    counts = readiness["execution_status_counts"]
    assert set(counts) <= {"READY", "PARTIAL_READY", "BLOCKED", "NO_WORK", "COMPLETE"}
    assert sum(counts.values()) == 17
    b13 = _batch(readiness, BATCH_13)
    assert (b13["completion_status"], b13["execution_status"]) == closed(
        ("IN_PROGRESS", "BLOCKED"), ("COMPLETE", "COMPLETE"))
    assert len(b13["resolved_target_ids"]) == closed(11, 23)
    assert b13["ready_target_ids"] == []
    assert len(b13["blocked_target_ids"]) == closed(12, 0)
    assert payload["readiness"]["execution_status_counts"] == counts
    for row in readiness["batches"]:
        assert row["completion_status"] in ("NOT_STARTED", "IN_PROGRESS", "COMPLETE",
                                           "HUMAN_REVIEW")
        assert row["execution_status"] in ("READY", "PARTIAL_READY", "BLOCKED",
                                           "NO_WORK", "COMPLETE")
        assert not set(row["ready_target_ids"]) & set(row["blocked_target_ids"])


def test_latest_two_unexecuted_batches_metric(run08) -> None:
    """§11：post-run 状态动态寻找最近两个未执行 AUTO_SAFE batch（不硬编码）。"""

    service, _payload = run08
    readiness = _artifact(DESIGN_DIR / "M11_READINESS_V2.json")
    pending = _two_most_recent_unexecuted(readiness)
    assert [row["batch_id"] for row in pending] == ["REPAIR_BATCH_14",
                                                    "REPAIR_BATCH_15"]
    b14, b15 = pending
    # RUN-08 时点 = B14 16/5 + B15 19/0；后续 RUN 会推进这些数字，
    # 因此只断言 metric 构造（post-run 状态、非硬编码 batch 号）。
    assert b14["mutable_target_count"] == 21
    assert b15["mutable_target_count"] == 21
    combined_ready = len(b14["ready_target_ids"]) + len(b15["ready_target_ids"])
    combined_blocked = len(b14["blocked_target_ids"]) + len(b15["blocked_target_ids"])
    assert combined_ready + combined_blocked <= 42


# ---------------------------------------------------------------- backlog / author / M12
def test_backlog_update(run08) -> None:
    service, payload = run08
    backlog = _artifact(DESIGN_DIR / "M11_PRODUCTION_BACKLOG.json")
    assert set(backlog["lane_counts"]) == set(BACKLOG_LANES)
    assert all(count >= 1 for count in backlog["lane_counts"].values())
    assert backlog["item_count"] == sum(backlog["lane_counts"].values())
    assert backlog["item_count"] >= 60
    assert backlog["last_run"] == RUN_ID
    done = {row["item_id"]: row for row in backlog["items"]
            if row["status"] == "DONE"}
    assert done["BL_AUTO_B13"]["completed_by_run"] == RUN_ID
    assert len(done["BL_AUTO_B13"]["completed_targets"]) == 15
    assert set(payload["backlog"]["done_item_ids"]) == set(done)
    assert backlog["lane_counts"]["LANE_MANUAL"] >= 11
    assert backlog["lane_counts"]["LANE_CONTENT_REWRITE"] >= 22


def test_no_author_auto_resolution_and_field_rebind_not_manufactured(run08) -> None:
    service, payload = run08
    inventory = _artifact(DESIGN_DIR / "AUTHOR_ACTION_INVENTORY.json")
    assert inventory["policy_selection"]["auto_selected"] == ""
    assert inventory["policy_selection"]["author_selected"] == ""
    assert inventory["auto_resolved"] == 0
    assert payload["author_policy_selected"] is False
    assert payload["author_decisions_resolved"] == 0
    gate = _run_artifact("M11_RUN_08_GATE.json")
    assert gate["checks"]["no_author_policy_auto_selected"] is True
    assert gate["checks"]["no_author_decision_auto_resolved"] is True
    assert payload["field_rebind_natural_end_to_end"] is False
    assert not (DESIGN_DIR / "PRODUCTION_CAPABILITY_EVIDENCE.json").is_file()


def test_m12_remains_false(run08) -> None:
    service, payload = run08
    m12 = _artifact(DESIGN_DIR / "p15p/M12_ENTRY_CRITERIA.json")
    assert m12["criteria_count"] == 9
    assert m12["m12_entry_allowed"] is False
    assert m12["satisfied_count"] == len(m12["satisfied_criteria"])  # [M11-CLOSURE] P15p projection 自洽为准
    assert m12["unsatisfied_count"] == len(m12["unsatisfied_criteria"])  # [M11-CLOSURE]
    assert m12["blocking_count"] == len(m12["blocking_criteria"])  # [M11-CLOSURE]
    assert payload["m12"]["entry_allowed"] is False


def test_contract_gate_truth_and_foundation_digests_unchanged(run08) -> None:
    service, payload = run08
    baseline = _run_artifact("M11_RUN_08_BASELINE.json")
    now = service.frozen_digests()
    assert now["contract"] == baseline["frozen_contract"]["contract"]
    assert now["repair_gate"] == baseline["frozen_contract"]["repair_gate"]
    gate = _run_artifact("M11_RUN_08_GATE.json")
    assert gate["checks"]["frozen_contract_unchanged"] is True
    assert gate["checks"]["frozen_repair_gate_unchanged"] is True
    truth = service.truth_digests()
    assert truth["canon"] == FROZEN_SOURCE_DIGESTS["canon"]
    assert truth["story_state"] == FROZEN_SOURCE_DIGESTS["story_state"]
    assert truth["legacy"] == FROZEN_SOURCE_DIGESTS["legacy"]
    assert truth["chapter_ir"] == FROZEN_SOURCE_DIGESTS["chapter_ir"]
    assert truth["historical_foundation"] == FROZEN_FOUNDATION_DIGESTS
    assert gate["checks"]["truth_digests_unchanged"] is True
    assert payload["gate"]["confirmed_facts_changed"] == 0
    assert payload["gate"]["read_only_chapters_changed"] == 0


def test_run08_gate_pass_with_injected_evidence(run08) -> None:
    service, payload = run08
    gate = _run_artifact("M11_RUN_08_GATE.json")
    assert set(gate["failed_checks"]) <= {"full_pytest_pass", "validate_project_pass"}
    for key, value in gate["checks"].items():
        if key not in ("full_pytest_pass", "validate_project_pass"):
            assert value is True, key
    service.record_test_evidence(pytest_summary="injected", pytest_passed=1,
                                 validate_summary="injected")
    baseline = _run_artifact("M11_RUN_08_BASELINE.json")
    reconciliation = _artifact(DESIGN_DIR / RUN_RECONCILIATION)
    replay = service.run_gate(
        baseline=baseline,
        residual={"targets": payload["residual"]["targets"], "preflight": {
            "targets": _run_artifact("M11_RUN_08_BATCH04_PREFLIGHT.json")["targets"]}},
        frontier={"targets": payload["frontier"]["targets"],
                  "blocked_targets": _artifact(
                      DESIGN_DIR / BATCH_13_SCOPE_FILE)["blocked_target_ids"]},
        reconciliation=reconciliation,
        projections={"overlay": _artifact(DESIGN_DIR / "M11_OVERLAY_V2.json"),
                     "readiness": _artifact(DESIGN_DIR / "M11_READINESS_V2.json"),
                     "ledger": _artifact(DESIGN_DIR / "M11_REPAIR_SUBTYPE_LEDGER.json")},
        backlog=_artifact(DESIGN_DIR / "M11_PRODUCTION_BACKLOG.json"),
        contracts=[_run_artifact("M11_RUN_08_BATCH_04_ACCEPTANCE_CONTRACT.json"),
                   _run_artifact("M11_RUN_08_BATCH_13_ACCEPTANCE_CONTRACT.json")],
        evidence={"pytest": {"status": "PASS", "summary": "injected"},
                  "validate_project": {"status": "PASS", "summary": "injected"}})
    assert replay["status"] == "PASS"
    assert replay["failed_checks"] == []
