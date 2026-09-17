"""M11-RUN-10：Production Execution 回归（Auto Safe Frontier through Batch 15）。"""

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
from novelforge.story_engine.m11_run10 import (
    BATCH_15,
    BATCH_15_SCOPE_FILE,
    M11Run10Service,
    RUN_ID,
    RUN_RECONCILIATION,
)

from m11_phase_history import closed
ROOT = Path(".").resolve()
DESIGN_DIR = ROOT / "workspace/wasteland_001_exports/repair_adoption_v1"
REPAIR_DIR = ROOT / "workspace/wasteland_001_exports/repair_v1"
RUN_DIR = DESIGN_DIR / "m11_run_10"
EXECUTED_BATCHES = {f"REPAIR_BATCH_{index:02d}" for index in range(1, 16)}


@pytest.fixture(scope="module")
def run10():
    service = M11Run10Service(ROOT)
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
def test_scope_frozen_before_execution(run10) -> None:
    service, payload = run10
    baseline = _run_artifact("M11_RUN_10_BASELINE.json")
    scope = _run_artifact("M11_RUN_10_EXECUTION_SCOPE.json")
    assert baseline["run_id"] == RUN_ID
    assert baseline["primary_buckets"] == {
        "resolved_repaired": 140, "resolved_no_repair_required": 49,
        "evidence_ready": 3, "manual_required": 10, "content_design_required": 53,
        "author_decision": 2, "pending": 115}
    assert baseline["batch_execution_status_counts"] == {
        "BLOCKED": 14, "PARTIAL_READY": 1, "READY": 2}
    assert baseline["frontier"]["batch_15"] == {
        "completion_status": "IN_PROGRESS", "execution_status": "PARTIAL_READY",
        "resolved": 2, "ready": 12, "blocked": 7}
    assert scope["frozen"] is True and scope["run_id"] == RUN_ID
    assert scope["frontier_max_batch"] == BATCH_15
    assert scope["contract_digest"] == service.frozen_digests()["contract"]
    assert scope["gate_digest"] == service.frozen_digests()["repair_gate"]
    assert scope["matches_run09_baseline"]["REPAIR_BATCH_15"] is True
    assert scope["run09_baseline"]["REPAIR_BATCH_15"] == {
        "ready": 12, "blocked": 7, "execution_status": "PARTIAL_READY"}
    assert payload["status"] in ("PASS", "EVIDENCE_REQUIRED")


def test_no_residual_auto_safe_target_before_batch15(run10) -> None:
    service, payload = run10
    scope = _run_artifact("M11_RUN_10_EXECUTION_SCOPE.json")
    assert scope["batch_04_residual_targets"] == []
    readiness = _artifact(DESIGN_DIR / "M11_READINESS_V2.json")
    for index in range(1, 15):
        assert _batch(readiness, f"REPAIR_BATCH_{index:02d}")["ready_target_ids"] == []
    assert payload["residual"]["preflight_verdict"] == "NO_READY_TARGET"
    assert payload["residual"]["acceptance"] == "PASS"


def test_batch15_baseline_recomputed_and_closure(run10) -> None:
    service, payload = run10
    scope = _artifact(DESIGN_DIR / BATCH_15_SCOPE_FILE)
    assert scope["frozen"] is True and scope["batch_id"] == BATCH_15
    assert len(scope["ready_target_ids"]) == 12
    assert len(scope["blocked_target_ids"]) == 7
    closure = scope["dependency_closure"]
    assert closure["readiness_ready_count"] == 12
    assert closure["readiness_blocked_count"] == 7
    # [M11-CLOSURE] blocker 分类在 M11 final closure 后全部归零（scope 本身仍 frozen）
    assert closure["classification"]["content_design_blocked"] == 0
    assert closure["classification"]["entity_blocked"] == 0
    assert closure["classification"]["manual_blocked"] == 0
    assert closure["classification"]["author_blocked"] == 0
    assert closure["classification"]["confirmed_binding_blocked"] == 0
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
    assert payload["frontier"]["scope"] == {"ready": 12, "blocked": 7}


def test_batch15_blocked_untouched(run10) -> None:
    service, payload = run10
    scope = _artifact(DESIGN_DIR / BATCH_15_SCOPE_FILE)
    blocked = {str(item) for item in scope["blocked_target_ids"]}
    assert len(blocked) == 7
    assert {row["legacy_label"] for row in scope["blocked_targets"]} == {
        "ch483", "ch484", "ch485", "ch489", "ch490", "ch491", "ch492"}
    reconciliation = _artifact(DESIGN_DIR / RUN_RECONCILIATION)
    for row in reconciliation["records"]:
        if row["chapter_id"] in blocked:
            assert row["new_resolution_status"] == "BLOCKED_CONTENT_DESIGN"
            assert row["repair_subtype"] == "" and row["repaired_ref"] == ""
    execution = _run_artifact("M11_RUN_10_BATCH15_EXECUTION.json")
    assert not set(execution["targets"]) & blocked
    assert set(execution["blocked_targets"]) == blocked
    assert payload["gate"]["checks"]["blocked_target_untouched"] is True


def test_batch15_execution_and_promotion(run10) -> None:
    service, payload = run10
    execution = _run_artifact("M11_RUN_10_BATCH15_EXECUTION.json")
    assert len(execution["targets"]) == 12
    assert execution["verified"] == 10
    assert execution["human_review"] == 2
    assert execution["promotion_mode"] == "partial"
    assert execution["gate_status"] == "PASS"
    diff = _artifact(REPAIR_DIR / "BATCH_15_DIFF.json")
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


def test_dynamic_downgrade_honesty(run10) -> None:
    service, payload = run10
    reconciliation = _artifact(DESIGN_DIR / RUN_RECONCILIATION)
    counts = reconciliation["dynamic_downgrade_counts"]
    assert counts["MANUAL_REQUIRED"] == 2          # ch498 / ch504（HIGH risk）
    assert counts["CONTENT_DESIGN_REQUIRED"] == 0
    assert counts["EVIDENCE_ONLY"] if "EVIDENCE_ONLY" in counts else True
    assert counts["AUTHOR_DECISION_REQUIRED"] == 0
    assert counts["BLOCKED_CONFIRMED_BINDING_CONFLICT"] == 0
    assert counts["ARCHITECTURE_EXCEPTION_REQUIRED"] == 0
    manual = {row["legacy_label"]: row for row in reconciliation["records"]
              if row["new_resolution_status"] == "MANUAL_REQUIRED"}
    assert set(manual) == {"ch498", "ch504"}
    assert manual["ch498"]["repair_class"] == "FIELD_REBIND"
    assert manual["ch504"]["repair_class"] == "NO_REPAIR_REQUIRED"
    for row in manual.values():
        assert row["execution_decision"] == "MANUAL"
        assert row["repaired_ref"] == ""
    # promoted : dynamic downgrade = 10 : 2 = 5.0 : 1
    downgrades = sum(value for key, value in counts.items() if key != "EVIDENCE_READY")
    assert reconciliation["promoted"] == 10 and downgrades == 2
    assert reconciliation["promoted"] / downgrades >= 2.0
    assert payload["frontier"]["verified"] == 10


def test_event_added_cannot_safe_auto(run10) -> None:
    service, payload = run10
    reconciliation = _artifact(DESIGN_DIR / RUN_RECONCILIATION)
    promoted = [row for row in reconciliation["records"]
                if row["new_resolution_status"] in ("RESOLVED_REPAIRED",
                                                    "RESOLVED_NO_REPAIR_REQUIRED")]
    allowed_ops = {"REBIND_EVIDENCE", "MARK_NOT_APPLICABLE", "RECLASSIFY_FUNCTION",
                   "REBIND_STATE_REFERENCE"}
    assert all(op in allowed_ops for row in promoted for op in row["patch_ops"])
    gate = _run_artifact("M11_RUN_10_GATE.json")
    assert gate["checks"]["no_new_historical_event_promoted"] is True
    assert payload["gate"]["new_historical_events"] == 0


def test_unsafe_field_rebind_cannot_promote(run10) -> None:
    """ch498 是 FIELD_REBIND + HIGH risk → MANUAL；capability 仍 NOT_PROVEN。"""

    service, payload = run10
    reconciliation = _artifact(DESIGN_DIR / RUN_RECONCILIATION)
    assert reconciliation["promoted_field_rebind"] == 0
    ledger = _artifact(DESIGN_DIR / "M11_REPAIR_SUBTYPE_LEDGER.json")
    assert ledger["resolved_subtype_counts"].get("repaired_field_rebind", 0) == 0
    assert payload["field_rebind_natural_end_to_end"] is False
    assert not (DESIGN_DIR / "PRODUCTION_CAPABILITY_EVIDENCE.json").is_file()
    capability = _artifact(DESIGN_DIR / "p15p/P15_CAPABILITY_ACCEPTANCE_MATRIX.json")
    verdicts = {row["capability"]: row["verdict"] for row in capability["capabilities"]}
    assert verdicts["Field Rebind"] == "NOT_PROVEN"
    # 累计 4 个自然 FIELD_REBIND classification（ch324 / ch425 / ch445 / ch498）全部未 promote
    field_rebind_total = 0
    for index in range(5, 11):
        records = _artifact(DESIGN_DIR / f"M11_RUN_{index:02d}_RECONCILIATION.json"
                            )["records"]
        for row in records:
            if row["repair_class"] == "FIELD_REBIND":
                field_rebind_total += 1
                assert row["new_resolution_status"] != "RESOLVED_REPAIRED"
    assert field_rebind_total == 4


# ---------------------------------------------------------------- production CDQ
def test_production_cdq_ownership_and_queue_id_reconciliation(run10) -> None:
    service, payload = run10
    # 本轮无 content-design 降级 → 新 CDQ = 0，且 V2 ID 集合保持不变
    reconciliation = _artifact(DESIGN_DIR / RUN_RECONCILIATION)
    assert reconciliation["content_design_items_registered"] == []
    queue2 = _artifact(DESIGN_DIR / "M11_CONTENT_DESIGN_QUEUE_V2.json")
    ids = [row["design_item_id"] for row in queue2["items"]]
    assert len(ids) == len(set(ids)) >= 67
    assert not [item for item in ids if str(item).startswith("CDQ_RUN10_")]
    registered: list[str] = []
    for index in range(2, 11):
        path = DESIGN_DIR / f"M11_RUN_{index:02d}_RECONCILIATION.json"
        if not path.is_file():
            continue
        for row in _artifact(path).get("content_design_items_registered") or []:
            registered.append(str(row["design_item_id"]))
    assert registered and set(registered) <= set(ids)
    assert len(registered) == len(set(registered))        # duplicate ownership = 0
    queue3 = _artifact(DESIGN_DIR / "M11_CONTENT_DESIGN_QUEUE_V3.json")
    active = [row for row in queue3["requirements"] if row["status"] == "ACTIVE"]
    overlay = _artifact(DESIGN_DIR / "M11_OVERLAY_V2.json")
    queue_recon = _artifact(DESIGN_DIR / "p15n" /
                            "CONTENT_DESIGN_QUEUE_RECONCILIATION.json")
    # RUN-10 时点 = 53；RUN-11+ 会继续登记 production CDQ → 只保证守恒
    assert len(active) == overlay["content_design_required"] == 0  # [M11-CLOSURE]
    assert queue_recon["active_requirements"] == overlay["content_design_required"]
    assert queue_recon["orphan_requirements"] == []
    assert queue_recon["targets_without_requirement"] == []
    integration = service.readiness.integrate_dynamic_design_items()
    assert integration["new_item_count"] == 0
    invariant = _run_artifact(f"{P15_ISOLATION_INVARIANT_ID}.json")
    assert invariant["production_item_count"] >= 24
    assert invariant["production_item_ownership_pass"] is True
    assert payload["reconciliation"]["content_design_items_registered"] == 0


def test_p15_executor_isolation_and_regression(run10) -> None:
    service, payload = run10
    invariant = _run_artifact(f"{P15_ISOLATION_INVARIANT_ID}.json")
    assert invariant["status"] == "PASS"
    assert invariant["static_scan_pass"] is True
    assert invariant["runtime_isolation_pass"] is True
    assert not any(invariant["static_scan_findings"].values())
    assert not invariant["live_p15_artifacts_for_production_chapters"]
    gate = _run_artifact("M11_RUN_10_GATE.json")
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


def test_batch16_not_entered(run10) -> None:
    service, payload = run10
    gate = _run_artifact("M11_RUN_10_GATE.json")
    assert gate["checks"]["batch16_not_entered"] is True
    reconciliation = _artifact(DESIGN_DIR / RUN_RECONCILIATION)
    executed = {row["chapter_id"] for row in reconciliation["records"]}
    readiness = _artifact(DESIGN_DIR / "M11_READINESS_V2.json")
    b16 = _batch(readiness, "REPAIR_BATCH_16")
    assert not executed & (set(b16["ready_target_ids"])
                           | set(b16["blocked_target_ids"])
                           | set(b16["resolved_target_ids"]))
    assert payload["batch_16_executed"] is False


# ---------------------------------------------------------------- overlay / readiness
def test_overlay_and_372_conservation(run10) -> None:
    service, payload = run10
    overlay = _artifact(DESIGN_DIR / "M11_OVERLAY_V2.json")
    assert overlay["conservation"] == {"primary_total": TARGET_COUNT,
                                       "target_count": TARGET_COUNT, "exact": True}
    assert list(overlay["primary_resolution_status_counts"]) == list(PRIMARY_BUCKETS)
    assert sum(overlay["primary_resolution_status_counts"].values()) == TARGET_COUNT
    # RUN-10 时点 = 199 / 146 / 53 / 121；后续 RUN 会推进，只保留下界与守恒
    assert overlay["resolved_total"] >= 199
    assert overlay["repaired"] >= 146
    assert overlay["no_repair_required"] >= 53
    assert overlay["repaired_evidence_only"] >= 121
    assert overlay["repaired_field_rebind"] == 0
    assert overlay["repaired_micro_semantic"] == 21
    assert overlay["repaired_confirmed_override"] == 4
    assert overlay["content_design_required"] == 0  # [M11-CLOSURE] 已 terminal
    assert overlay["manual_required"] == 0  # [M11-CLOSURE] 已 terminal
    assert overlay["author_decision"] == 0  # [M11-CLOSURE] author lane 已 terminal
    assert overlay["pending"] <= 103
    ledger = _artifact(DESIGN_DIR / "M11_REPAIR_SUBTYPE_LEDGER.json")
    assert len(ledger["ledger"]) == overlay["resolved_total"]
    assert payload["overlay_conservation"]["exact"] is True


def test_readiness_recompute(run10) -> None:
    service, payload = run10
    readiness = _artifact(DESIGN_DIR / "M11_READINESS_V2.json")
    assert len(readiness["batches"]) == 17
    assert readiness["completion_status_counts"] == {"COMPLETE": 17}  # [M11-CLOSURE] 372/372 terminal
    counts = readiness["execution_status_counts"]
    assert set(counts) <= {"READY", "PARTIAL_READY", "BLOCKED", "NO_WORK", "COMPLETE"}
    assert sum(counts.values()) == 17
    b15 = _batch(readiness, BATCH_15)
    assert (b15["completion_status"], b15["execution_status"]) == closed(
        ("IN_PROGRESS", "BLOCKED"), ("COMPLETE", "COMPLETE"))
    assert len(b15["resolved_target_ids"]) == closed(12, 21)
    assert b15["ready_target_ids"] == []
    assert len(b15["blocked_target_ids"]) == closed(9, 0)
    assert payload["readiness"]["execution_status_counts"] == counts
    for row in readiness["batches"]:
        assert row["completion_status"] in ("NOT_STARTED", "IN_PROGRESS", "COMPLETE",
                                           "HUMAN_REVIEW")
        assert row["execution_status"] in ("READY", "PARTIAL_READY", "BLOCKED",
                                           "NO_WORK", "COMPLETE")
        assert not set(row["ready_target_ids"]) & set(row["blocked_target_ids"])


def test_latest_two_unexecuted_batches_metric(run10) -> None:
    """§11：post-run 状态动态寻找（不得继续使用 Batch15 + Batch16）。"""

    service, _payload = run10
    readiness = _artifact(DESIGN_DIR / "M11_READINESS_V2.json")
    pending = _two_most_recent_unexecuted(readiness)
    assert [row["batch_id"] for row in pending] == ["REPAIR_BATCH_16",
                                                    "REPAIR_BATCH_17"]
    b16, b17 = pending
    # RUN-10 时点 = B16 23/0 + B17 13/0；后续 RUN 会推进这些数字，
    # 因此只断言 metric 构造（post-run 状态、非硬编码 batch 号）。
    assert b16["mutable_target_count"] == 24
    assert b17["mutable_target_count"] == 13
    combined_ready = len(b16["ready_target_ids"]) + len(b17["ready_target_ids"])
    combined_blocked = len(b16["blocked_target_ids"]) + len(b17["blocked_target_ids"])
    assert combined_ready + combined_blocked <= 37


# ---------------------------------------------------------------- backlog / author / M12
def test_backlog_update(run10) -> None:
    service, payload = run10
    backlog = _artifact(DESIGN_DIR / "M11_PRODUCTION_BACKLOG.json")
    assert set(backlog["lane_counts"]) == set(BACKLOG_LANES)
    assert all(count >= 1 for count in backlog["lane_counts"].values())
    assert backlog["item_count"] == sum(backlog["lane_counts"].values()) >= 66
    assert backlog["last_run"] == RUN_ID
    done = {row["item_id"]: row for row in backlog["items"]
            if row["status"] == "DONE"}
    assert done["BL_AUTO_B15"]["completed_by_run"] == RUN_ID
    assert len(done["BL_AUTO_B15"]["completed_targets"]) == 12
    assert set(payload["backlog"]["done_item_ids"]) == set(done)
    assert backlog["lane_counts"]["LANE_MANUAL"] >= 13
    assert backlog["lane_counts"]["LANE_CONTENT_REWRITE"] >= 26


def test_no_author_auto_resolution(run10) -> None:
    service, payload = run10
    inventory = _artifact(DESIGN_DIR / "AUTHOR_ACTION_INVENTORY.json")
    assert inventory["policy_selection"]["auto_selected"] == ""
    assert inventory["policy_selection"]["author_selected"] == ""
    assert inventory["auto_resolved"] == 0
    assert payload["author_policy_selected"] is False
    assert payload["author_decisions_resolved"] == 0
    gate = _run_artifact("M11_RUN_10_GATE.json")
    assert gate["checks"]["no_author_policy_auto_selected"] is True
    assert gate["checks"]["no_author_decision_auto_resolved"] is True


def test_m12_remains_false(run10) -> None:
    service, payload = run10
    m12 = _artifact(DESIGN_DIR / "p15p/M12_ENTRY_CRITERIA.json")
    assert m12["criteria_count"] == 9
    assert m12["m12_entry_allowed"] is False
    assert m12["satisfied_count"] == len(m12["satisfied_criteria"])  # [M11-CLOSURE] P15p projection 自洽为准
    assert m12["unsatisfied_count"] == len(m12["unsatisfied_criteria"])  # [M11-CLOSURE]
    assert m12["blocking_count"] == len(m12["blocking_criteria"])  # [M11-CLOSURE]
    assert payload["m12"]["entry_allowed"] is False


def test_contract_gate_truth_and_foundation_digests_unchanged(run10) -> None:
    service, payload = run10
    baseline = _run_artifact("M11_RUN_10_BASELINE.json")
    now = service.frozen_digests()
    assert now["contract"] == baseline["frozen_contract"]["contract"]
    assert now["repair_gate"] == baseline["frozen_contract"]["repair_gate"]
    gate = _run_artifact("M11_RUN_10_GATE.json")
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


def test_run10_gate_pass_with_injected_evidence(run10) -> None:
    service, payload = run10
    gate = _run_artifact("M11_RUN_10_GATE.json")
    assert set(gate["failed_checks"]) <= {"full_pytest_pass", "validate_project_pass"}
    for key, value in gate["checks"].items():
        if key not in ("full_pytest_pass", "validate_project_pass"):
            assert value is True, key
    service.record_test_evidence(pytest_summary="injected", pytest_passed=1,
                                 validate_summary="injected")
    baseline = _run_artifact("M11_RUN_10_BASELINE.json")
    reconciliation = _artifact(DESIGN_DIR / RUN_RECONCILIATION)
    replay = service.run_gate(
        baseline=baseline,
        residual={"targets": payload["residual"]["targets"], "preflight": {
            "targets": _run_artifact("M11_RUN_10_BATCH04_PREFLIGHT.json")["targets"]}},
        frontier={"targets": payload["frontier"]["targets"],
                  "blocked_targets": _artifact(
                      DESIGN_DIR / BATCH_15_SCOPE_FILE)["blocked_target_ids"]},
        reconciliation=reconciliation,
        projections={"overlay": _artifact(DESIGN_DIR / "M11_OVERLAY_V2.json"),
                     "readiness": _artifact(DESIGN_DIR / "M11_READINESS_V2.json"),
                     "ledger": _artifact(DESIGN_DIR / "M11_REPAIR_SUBTYPE_LEDGER.json")},
        backlog=_artifact(DESIGN_DIR / "M11_PRODUCTION_BACKLOG.json"),
        contracts=[_run_artifact("M11_RUN_10_BATCH_04_ACCEPTANCE_CONTRACT.json"),
                   _run_artifact("M11_RUN_10_BATCH_15_ACCEPTANCE_CONTRACT.json")],
        evidence={"pytest": {"status": "PASS", "summary": "injected"},
                  "validate_project": {"status": "PASS", "summary": "injected"}})
    assert replay["status"] == "PASS"
    assert replay["failed_checks"] == []
