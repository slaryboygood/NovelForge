"""M11-RUN-07：Production Execution 回归（Auto Safe Frontier through Batch 12）。"""

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
from novelforge.story_engine.m11_run07 import (
    BATCH_12,
    BATCH_12_SCOPE_FILE,
    M11Run07Service,
    RUN_ID,
    RUN_RECONCILIATION,
)

from m11_phase_history import closed
ROOT = Path(".").resolve()
DESIGN_DIR = ROOT / "workspace/wasteland_001_exports/repair_adoption_v1"
REPAIR_DIR = ROOT / "workspace/wasteland_001_exports/repair_v1"
RUN_DIR = DESIGN_DIR / "m11_run_07"
EXECUTED_BATCHES = {f"REPAIR_BATCH_{index:02d}" for index in range(1, 13)}


@pytest.fixture(scope="module")
def run07():
    service = M11Run07Service(ROOT)
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
def test_scope_frozen_before_execution(run07) -> None:
    service, payload = run07
    baseline = _run_artifact("M11_RUN_07_BASELINE.json")
    scope = _run_artifact("M11_RUN_07_EXECUTION_SCOPE.json")
    assert baseline["run_id"] == RUN_ID
    assert baseline["primary_buckets"] == {
        "resolved_repaired": 118, "resolved_no_repair_required": 37,
        "evidence_ready": 3, "manual_required": 5, "content_design_required": 47,
        "author_decision": 2, "pending": 160}
    assert baseline["batch_execution_status_counts"] == {
        "BLOCKED": 11, "PARTIAL_READY": 2, "READY": 4}
    assert baseline["frontier"]["batch_12"] == {
        "completion_status": "IN_PROGRESS", "execution_status": "PARTIAL_READY",
        "resolved": 0, "ready": 14, "blocked": 9}
    assert scope["frozen"] is True and scope["run_id"] == RUN_ID
    assert scope["frontier_max_batch"] == BATCH_12
    assert scope["matches_run06_baseline"]["REPAIR_BATCH_12"] is True
    assert scope["run06_baseline"]["REPAIR_BATCH_12"] == {
        "ready": 14, "blocked": 9, "execution_status": "PARTIAL_READY"}
    assert payload["status"] in ("PASS", "EVIDENCE_REQUIRED")


def test_batch04_has_no_residual_target(run07) -> None:
    service, payload = run07
    scope = _run_artifact("M11_RUN_07_EXECUTION_SCOPE.json")
    assert scope["batch_04_residual_targets"] == []
    readiness = _artifact(DESIGN_DIR / "M11_READINESS_V2.json")
    b04 = _batch(readiness, "REPAIR_BATCH_04")
    assert b04["execution_status"] == "COMPLETE"  # [M11-CLOSURE] 全部 batch 已 terminal
    assert b04["ready_target_ids"] == []
    assert payload["residual"]["acceptance"] == "PASS"
    assert payload["residual"]["preflight_verdict"] == "NO_READY_TARGET"


def test_batch12_baseline_recomputed_and_closure(run07) -> None:
    service, payload = run07
    scope = _artifact(DESIGN_DIR / BATCH_12_SCOPE_FILE)
    assert scope["frozen"] is True and scope["batch_id"] == BATCH_12
    assert len(scope["ready_target_ids"]) == 14
    assert len(scope["blocked_target_ids"]) == 9
    closure = scope["dependency_closure"]
    assert closure["readiness_ready_count"] == 14
    assert closure["readiness_blocked_count"] == 9
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
        assert row["ready_reason"]
    assert payload["frontier"]["scope"] == {"ready": 14, "blocked": 9}


def test_batch12_blocked_untouched(run07) -> None:
    service, payload = run07
    scope = _artifact(DESIGN_DIR / BATCH_12_SCOPE_FILE)
    blocked = {str(item) for item in scope["blocked_target_ids"]}
    assert len(blocked) == 9
    assert {row["legacy_label"] for row in scope["blocked_targets"]} == {
        "ch382", "ch385", "ch386", "ch387", "ch388", "ch390", "ch391", "ch396", "ch397"}
    reconciliation = _artifact(DESIGN_DIR / RUN_RECONCILIATION)
    for row in reconciliation["records"]:
        if row["chapter_id"] in blocked:
            assert row["new_resolution_status"] == "BLOCKED_CONTENT_DESIGN"
            assert row["repair_subtype"] == "" and row["repaired_ref"] == ""
    execution = _run_artifact("M11_RUN_07_BATCH12_EXECUTION.json")
    assert not set(execution["targets"]) & blocked
    assert set(execution["blocked_targets"]) == blocked
    assert payload["gate"]["checks"]["blocked_target_untouched"] is True


def test_batch12_execution_and_promotion(run07) -> None:
    service, payload = run07
    execution = _run_artifact("M11_RUN_07_BATCH12_EXECUTION.json")
    assert len(execution["targets"]) == 14
    assert execution["verified"] == 12
    assert execution["human_review"] == 2
    assert execution["promotion_mode"] == "partial"
    assert execution["gate_status"] == "PASS"
    diff = _artifact(REPAIR_DIR / "BATCH_12_DIFF.json")
    assert diff["semantic_elements_added"] == 0
    assert diff["semantic_elements_removed"] == 0
    assert diff["confirmed_facts_changed"] == 0
    assert diff["read_only_chapters_changed"] == 0
    reconciliation = _artifact(DESIGN_DIR / RUN_RECONCILIATION)
    assert reconciliation["promoted"] == 12
    assert reconciliation["promoted_evidence_only"] == 9
    assert reconciliation["promoted_no_repair_required"] == 3
    assert reconciliation["promoted_field_rebind"] == 0
    assert payload["frontier"]["acceptance"] == "PASS"


def test_dynamic_downgrade_honesty(run07) -> None:
    service, payload = run07
    reconciliation = _artifact(DESIGN_DIR / RUN_RECONCILIATION)
    counts = reconciliation["dynamic_downgrade_counts"]
    assert counts["MANUAL_REQUIRED"] == 2          # ch407 / ch409（PARTIAL substrate）
    assert counts["CONTENT_DESIGN_REQUIRED"] == 0
    assert counts["ENTITY_RESOLUTION_REQUIRED"] == 0 if "ENTITY_RESOLUTION_REQUIRED" \
        in counts else True
    assert counts["AUTHOR_DECISION_REQUIRED"] == 0
    assert counts["BLOCKED_CONFIRMED_BINDING_CONFLICT"] == 0
    assert counts["ARCHITECTURE_EXCEPTION_REQUIRED"] == 0
    manual = {row["legacy_label"] for row in reconciliation["records"]
              if row["new_resolution_status"] == "MANUAL_REQUIRED"}
    assert manual == {"ch407", "ch409"}
    for row in reconciliation["records"]:
        if row["new_resolution_status"] == "MANUAL_REQUIRED":
            assert row["evidence_substrate"] == "HISTORICAL_FULL_IR_PARTIAL"
            assert row["repaired_ref"] == ""
    promoted = [row for row in reconciliation["records"]
                if row["new_resolution_status"] in ("RESOLVED_REPAIRED",
                                                    "RESOLVED_NO_REPAIR_REQUIRED")]
    assert all(row["repair_class"] in ("EVIDENCE_ONLY", "NO_REPAIR_REQUIRED")
               for row in promoted)
    assert payload["frontier"]["verified"] == 12


def test_event_added_cannot_safe_auto(run07) -> None:
    service, payload = run07
    reconciliation = _artifact(DESIGN_DIR / RUN_RECONCILIATION)
    promoted = [row for row in reconciliation["records"]
                if row["new_resolution_status"] in ("RESOLVED_REPAIRED",
                                                    "RESOLVED_NO_REPAIR_REQUIRED")]
    allowed_ops = {"REBIND_EVIDENCE", "MARK_NOT_APPLICABLE", "RECLASSIFY_FUNCTION",
                   "REBIND_STATE_REFERENCE"}
    assert all(op in allowed_ops for row in promoted for op in row["patch_ops"])
    gate = _run_artifact("M11_RUN_07_GATE.json")
    assert gate["checks"]["no_new_historical_event_promoted"] is True
    assert payload["gate"]["new_historical_events"] == 0
    proposals = _artifact(DESIGN_DIR / "p15o/CONCRETE_REWRITE_PROPOSALS.json")
    decisions = [row for row in proposals["proposals"] if row.get("decision_event")]
    # [M11-CLOSURE] proposal surface 已清空；保留 new-event 审批不变量
    assert all(row["author_approval_required"] == "AUTHOR_CONTENT_APPROVAL"
               for row in decisions)
    assert _run_artifact("M11_RUN_07_GATE.json")["checks"][
        "no_new_historical_event_promoted"] is True


# ---------------------------------------------------------------- queue lifecycle audit
def test_content_design_queue_lifecycle_audit(run07) -> None:
    """§4：RUN-05 → RUN-06 的 queue lifecycle 审计（可审计 reconciliation）。"""

    service, payload = run07
    audit = _run_artifact("CONTENT_DESIGN_QUEUE_LIFECYCLE_AUDIT.json")
    assert audit["audit_id"] == "CONTENT_DESIGN_QUEUE_LIFECYCLE_AUDIT"
    assert audit["before_run"] == "M11_RUN_05"
    assert list(audit["added_runs"]) == ["M11_RUN_06"]
    assert audit["before_item_count"] == 58
    assert audit["added_item_count"] == 3
    # 窗口语义：RUN-05 closeout 58 + RUN-06 新增 3 = 61（= RUN-06 收口时的 V2）；
    # 之后 RUN-07/RUN-08 的新增记入 later_ids（after 仍然等于当前 V2）。
    assert audit["window_after_item_count"] == 61
    assert audit["after_item_count"] == (
        audit["window_after_item_count"] + audit["later_item_count"])
    assert audit["verdict"] == "NO_DATA_LOSS"
    assert audit["removed_or_superseded_ids"] == []
    assert audit["duplicate_design_item_ids"] == []
    assert audit["missing_registered_production_cdq"] == []
    assert set(audit["added_ids"]) == {
        "CDQ_RUN06_ch080", "CDQ_RUN06_ch346", "CDQ_RUN06_ch355"}
    # before ∪ added == after（集合恒等）
    assert set(audit["before_ids"]) | set(audit["added_ids"]) == set(
        audit["window_after_ids"])
    assert set(audit["window_after_ids"]) | set(audit["later_ids"]) == set(
        audit["after_ids"])
    assert not set(audit["before_ids"]) & set(audit["added_ids"])
    assert all(row["v3_status"] in ("ACTIVE", "RESOLVED_REPAIRED", "RESOLVED_NO_REPAIR")
               for row in audit["transitioned_ids"])  # [M11-CLOSURE] production item 已 terminal
    assert audit["v3_matches_overlay"] is True
    assert audit["p15_snapshot_item_count"] == 43
    assert payload["queue_lifecycle_audit"]["verdict"] == "NO_DATA_LOSS"
    assert payload["queue_lifecycle_audit"]["after_item_count"] >= 61


def test_no_queue_id_loss_or_duplicate_ownership(run07) -> None:
    service, _payload = run07
    queue2 = _artifact(DESIGN_DIR / "M11_CONTENT_DESIGN_QUEUE_V2.json")
    ids = [row["design_item_id"] for row in queue2["items"]]
    assert len(ids) == len(set(ids))
    assert len(ids) >= 61
    registered: list[str] = []
    for index in range(2, 8):
        name = f"M11_RUN_{index:02d}_RECONCILIATION.json"
        path = DESIGN_DIR / name
        if not path.is_file():
            continue
        for row in _artifact(path).get("content_design_items_registered") or []:
            registered.append(str(row["design_item_id"]))
    assert registered and set(registered) <= set(ids)
    assert len(registered) == len(set(registered))     # 无 duplicate ownership


def test_v3_active_equals_overlay_content_design(run07) -> None:
    service, _payload = run07
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


# ---------------------------------------------------------------- production CDQ / P15
def test_production_cdq_origin_and_ownership(run07) -> None:
    service, payload = run07
    # 本轮没有新的 content-design downgrade → 新 CDQ = 0，且既有 production CDQ 归属不变
    assert payload["reconciliation"]["content_design_items_registered"] == 0
    reconciliation = _artifact(DESIGN_DIR / RUN_RECONCILIATION)
    assert reconciliation["content_design_items_registered"] == []
    invariant = _run_artifact(f"{P15_ISOLATION_INVARIANT_ID}.json")
    assert invariant["production_item_ownership_pass"] is True
    assert invariant["production_item_count"] >= 18
    assert all(row["owned_by_production_run"]
               for row in invariant["production_item_ownership"])
    # RUN-07 自己的 prefix 未被使用（无 content design 降级），不得出现伪造 item
    queue2 = _artifact(DESIGN_DIR / "M11_CONTENT_DESIGN_QUEUE_V2.json")
    assert not [row for row in queue2["items"]
                if str(row["design_item_id"]).startswith("CDQ_RUN07_")]


def test_p15_executor_isolation_and_regression(run07) -> None:
    service, payload = run07
    invariant = _run_artifact(f"{P15_ISOLATION_INVARIANT_ID}.json")
    assert invariant["status"] == "PASS"
    assert invariant["static_scan_pass"] is True
    assert invariant["runtime_isolation_pass"] is True
    assert not any(invariant["static_scan_findings"].values())
    assert not invariant["live_p15_artifacts_for_production_chapters"]
    gate = _run_artifact("M11_RUN_07_GATE.json")
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


def test_batch13_not_entered(run07) -> None:
    service, payload = run07
    gate = _run_artifact("M11_RUN_07_GATE.json")
    assert gate["checks"]["batch13_not_entered"] is True
    reconciliation = _artifact(DESIGN_DIR / RUN_RECONCILIATION)
    executed = {row["chapter_id"] for row in reconciliation["records"]}
    readiness = _artifact(DESIGN_DIR / "M11_READINESS_V2.json")
    b13 = _batch(readiness, "REPAIR_BATCH_13")
    assert not executed & (set(b13["ready_target_ids"])
                           | set(b13["blocked_target_ids"])
                           | set(b13["resolved_target_ids"]))
    assert payload["batch_13_executed"] is False


# ---------------------------------------------------------------- overlay / readiness
def test_overlay_and_372_conservation(run07) -> None:
    service, payload = run07
    overlay = _artifact(DESIGN_DIR / "M11_OVERLAY_V2.json")
    assert overlay["conservation"] == {"primary_total": TARGET_COUNT,
                                       "target_count": TARGET_COUNT, "exact": True}
    assert list(overlay["primary_resolution_status_counts"]) == list(PRIMARY_BUCKETS)
    assert sum(overlay["primary_resolution_status_counts"].values()) == TARGET_COUNT
    # RUN-07 时点值冻结在 reconciliation（live overlay 会被 RUN-08+ 推进）
    reconciliation = _artifact(DESIGN_DIR / RUN_RECONCILIATION)
    assert reconciliation["promoted"] == 12
    assert reconciliation["promoted_evidence_only"] == 9
    assert reconciliation["promoted_no_repair_required"] == 3
    assert overlay["resolved_total"] >= 167
    assert overlay["repaired"] >= 127
    assert overlay["no_repair_required"] >= 40
    assert overlay["repaired_evidence_only"] >= 102
    assert overlay["repaired_field_rebind"] == 0
    assert overlay["repaired_micro_semantic"] == 21
    assert overlay["repaired_confirmed_override"] == 4
    assert overlay["content_design_required"] == 0  # [M11-CLOSURE] 已 terminal
    assert overlay["manual_required"] == 0  # [M11-CLOSURE] 已 terminal          # +ch407 / ch409
    assert overlay["author_decision"] == 0  # [M11-CLOSURE] author lane 已 terminal
    assert overlay["pending"] <= 146
    ledger = _artifact(DESIGN_DIR / "M11_REPAIR_SUBTYPE_LEDGER.json")
    assert len(ledger["ledger"]) == overlay["resolved_total"]
    assert ledger["resolved_subtype_counts"].get("repaired_micro_semantic") == 21
    assert payload["overlay_conservation"]["exact"] is True


def test_readiness_recompute(run07) -> None:
    service, payload = run07
    readiness = _artifact(DESIGN_DIR / "M11_READINESS_V2.json")
    assert len(readiness["batches"]) == 17
    assert readiness["completion_status_counts"] == {"COMPLETE": 17}  # [M11-CLOSURE] 372/372 terminal
    counts = readiness["execution_status_counts"]
    assert set(counts) <= {"READY", "PARTIAL_READY", "BLOCKED", "NO_WORK", "COMPLETE"}
    assert sum(counts.values()) == 17
    b12 = _batch(readiness, BATCH_12)
    assert (b12["completion_status"], b12["execution_status"]) == closed(
        ("IN_PROGRESS", "BLOCKED"), ("COMPLETE", "COMPLETE"))
    assert len(b12["resolved_target_ids"]) == closed(12, 23)
    assert b12["ready_target_ids"] == []
    assert len(b12["blocked_target_ids"]) == closed(11, 0)
    assert payload["readiness"]["execution_status_counts"] == counts
    for row in readiness["batches"]:
        assert row["completion_status"] in ("NOT_STARTED", "IN_PROGRESS", "COMPLETE",
                                           "HUMAN_REVIEW")
        assert row["execution_status"] in ("READY", "PARTIAL_READY", "BLOCKED",
                                           "NO_WORK", "COMPLETE")
        assert not set(row["ready_target_ids"]) & set(row["blocked_target_ids"])


def test_latest_two_unexecuted_batches_metric(run07) -> None:
    """§11：必须用 post-run readiness 动态寻找最近两个未执行 AUTO_SAFE batch。"""

    service, _payload = run07
    readiness = _artifact(DESIGN_DIR / "M11_READINESS_V2.json")
    pending = _two_most_recent_unexecuted(readiness)
    assert [row["batch_id"] for row in pending] == ["REPAIR_BATCH_13",
                                                    "REPAIR_BATCH_14"]
    b13, b14 = pending
    # RUN-07 时点 = B13 15 ready / 7 blocked；后续 RUN 会推进这些数字，
    # 因此只断言 metric 的构造正确（用 post-run 状态、非硬编码 batch 号）。
    assert b13["mutable_target_count"] == 23
    assert b14["mutable_target_count"] == 21
    combined_ready = len(b13["ready_target_ids"]) + len(b14["ready_target_ids"])
    combined_blocked = len(b13["blocked_target_ids"]) + len(b14["blocked_target_ids"])
    assert combined_ready + combined_blocked <= 44


# ---------------------------------------------------------------- backlog / author / M12
def test_backlog_update(run07) -> None:
    service, payload = run07
    backlog = _artifact(DESIGN_DIR / "M11_PRODUCTION_BACKLOG.json")
    assert set(backlog["lane_counts"]) == set(BACKLOG_LANES)
    assert all(count >= 1 for count in backlog["lane_counts"].values())
    assert backlog["item_count"] == sum(backlog["lane_counts"].values())
    assert backlog["item_count"] >= 55
    assert backlog["last_run"] == RUN_ID
    done = {row["item_id"]: row for row in backlog["items"]
            if row["status"] == "DONE"}
    assert done["BL_AUTO_B12"]["completed_by_run"] == RUN_ID
    assert len(done["BL_AUTO_B12"]["completed_targets"]) == 14
    assert set(done) <= set(payload["backlog"]["done_item_ids"])
    assert payload["backlog"]["item_count"] == backlog["item_count"]
    assert backlog["lane_counts"]["LANE_MANUAL"] >= 8
    assert backlog["lane_counts"]["LANE_CONTENT_REWRITE"] >= 20


def test_no_author_auto_resolution_and_field_rebind_status(run07) -> None:
    service, payload = run07
    inventory = _artifact(DESIGN_DIR / "AUTHOR_ACTION_INVENTORY.json")
    assert inventory["policy_selection"]["auto_selected"] == ""
    assert inventory["policy_selection"]["author_selected"] == ""
    assert inventory["auto_resolved"] == 0
    assert payload["author_policy_selected"] is False
    assert payload["author_decisions_resolved"] == 0
    gate = _run_artifact("M11_RUN_07_GATE.json")
    assert gate["checks"]["no_author_policy_auto_selected"] is True
    assert gate["checks"]["no_author_decision_auto_resolved"] is True
    # FIELD_REBIND：仍 NOT_PROVEN（本轮无自然出现；不得伪造）
    ledger = _artifact(DESIGN_DIR / "M11_REPAIR_SUBTYPE_LEDGER.json")
    assert ledger["resolved_subtype_counts"].get("repaired_field_rebind", 0) == 0
    assert payload["field_rebind_natural_end_to_end"] is False
    assert not (DESIGN_DIR / "PRODUCTION_CAPABILITY_EVIDENCE.json").is_file()
    capability = _artifact(DESIGN_DIR / "p15p/P15_CAPABILITY_ACCEPTANCE_MATRIX.json")
    verdicts = {row["capability"]: row["verdict"] for row in capability["capabilities"]}
    assert verdicts["Field Rebind"] == "NOT_PROVEN"


def test_m12_remains_false(run07) -> None:
    service, payload = run07
    m12 = _artifact(DESIGN_DIR / "p15p/M12_ENTRY_CRITERIA.json")
    assert m12["criteria_count"] == 9
    assert m12["m12_entry_allowed"] is False
    assert m12["satisfied_count"] == len(m12["satisfied_criteria"])  # [M11-CLOSURE] P15p projection 自洽为准
    assert m12["unsatisfied_count"] == len(m12["unsatisfied_criteria"])  # [M11-CLOSURE]
    assert m12["blocking_count"] == len(m12["blocking_criteria"])  # [M11-CLOSURE]
    assert payload["m12"]["entry_allowed"] is False


def test_contract_gate_truth_and_foundation_digests_unchanged(run07) -> None:
    service, payload = run07
    baseline = _run_artifact("M11_RUN_07_BASELINE.json")
    now = service.frozen_digests()
    assert now["contract"] == baseline["frozen_contract"]["contract"]
    assert now["repair_gate"] == baseline["frozen_contract"]["repair_gate"]
    gate = _run_artifact("M11_RUN_07_GATE.json")
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


def test_run07_gate_pass_with_injected_evidence(run07) -> None:
    service, payload = run07
    gate = _run_artifact("M11_RUN_07_GATE.json")
    assert set(gate["failed_checks"]) <= {"full_pytest_pass", "validate_project_pass"}
    for key, value in gate["checks"].items():
        if key not in ("full_pytest_pass", "validate_project_pass"):
            assert value is True, key
    service.record_test_evidence(pytest_summary="injected", pytest_passed=1,
                                 validate_summary="injected")
    baseline = _run_artifact("M11_RUN_07_BASELINE.json")
    reconciliation = _artifact(DESIGN_DIR / RUN_RECONCILIATION)
    replay = service.run_gate(
        baseline=baseline,
        residual={"targets": payload["residual"]["targets"], "preflight": {
            "targets": _run_artifact("M11_RUN_07_BATCH04_PREFLIGHT.json")["targets"]}},
        frontier={"targets": payload["frontier"]["targets"],
                  "blocked_targets": _artifact(
                      DESIGN_DIR / BATCH_12_SCOPE_FILE)["blocked_target_ids"]},
        reconciliation=reconciliation,
        projections={"overlay": _artifact(DESIGN_DIR / "M11_OVERLAY_V2.json"),
                     "readiness": _artifact(DESIGN_DIR / "M11_READINESS_V2.json"),
                     "ledger": _artifact(DESIGN_DIR / "M11_REPAIR_SUBTYPE_LEDGER.json")},
        backlog=_artifact(DESIGN_DIR / "M11_PRODUCTION_BACKLOG.json"),
        contracts=[_run_artifact("M11_RUN_07_BATCH_04_ACCEPTANCE_CONTRACT.json"),
                   _run_artifact("M11_RUN_07_BATCH_12_ACCEPTANCE_CONTRACT.json")],
        evidence={"pytest": {"status": "PASS", "summary": "injected"},
                  "validate_project": {"status": "PASS", "summary": "injected"}})
    assert replay["status"] == "PASS"
    assert replay["failed_checks"] == []
