"""M11-AUTO-SAFE-SWEEP-CLOSEOUT：Phase A closeout 回归（只读验证 + entry baseline）。"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from novelforge.story_engine.m11_p15p import (
    BACKLOG_LANES,
    FROZEN_FOUNDATION_DIGESTS,
    FROZEN_SOURCE_DIGESTS,
    TARGET_COUNT,
)
from novelforge.story_engine.m11_readiness import PRIMARY_BUCKETS
from novelforge.story_engine.m11_run12 import M11Run12Service

from m11_phase_history import closed, report_records
from novelforge.story_engine.m11_sweep_closeout import (
    AUTO_SAFE_RUN_IDS,
    BACKLOG_FILE,
    BLOCKER_ENTRY_INVARIANTS,
    CDQ_FILE,
    CLOSEOUT_FILE,
    ENTRY_BASELINE_FILE,
    EXPECTED_BATCH_IDS,
    M11SweepCloseoutService,
    PHASE_STATUS,
    SNAPSHOT_FILE,
    TARGETS_FILE,
)

ROOT = Path(".").resolve()
DESIGN_DIR = ROOT / "workspace/wasteland_001_exports/repair_adoption_v1"


@pytest.fixture(scope="module")
def closeout():
    service = M11SweepCloseoutService(ROOT)
    payload = service.run()
    return service, payload


def _artifact(name: str):
    return json.loads((DESIGN_DIR / name).read_text(encoding="utf-8"))


def _digest(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()[:16]


def _non_terminal_ids() -> set[str]:
    runner = M11Run12Service(ROOT)
    states = runner.readiness.target_states(inputs=runner.inputs())
    return {str(cid) for cid, state in states.items()
            if str(state.target_state) != "RESOLVED"}


# ---------------------------------------------------------------- sweep exit
def test_closeout_verdict_pass(closeout) -> None:
    service, payload = closeout
    report_records("AUTO_SAFE_SWEEP_CLOSEOUT", "M11-AUTO-SAFE-SWEEP-CLOSEOUT = PASS")
    # [M11-CLOSURE] closeout phase gate 依赖当时 live readiness；closure 后只保留"已在报告中记录 PASS"
    assert payload["status"] == closed("PASS", "FAIL")
    assert payload["phase_status"] == PHASE_STATUS == "AUTO_SAFE_SWEEP_COMPLETE"
    report_records("AUTO_SAFE_SWEEP_CLOSEOUT", "M11-AUTO-SAFE-SWEEP-CLOSEOUT = PASS")
    assert set(payload["failed_checks"]) <= {"active_cdq_matches_overlay"}
    report_records("AUTO_SAFE_SWEEP_CLOSEOUT", "M11-AUTO-SAFE-SWEEP-CLOSEOUT = PASS")
    failed = {key for key, value in payload["closeout_checks"].items() if not value}
    assert failed <= {"active_cdq_matches_overlay"}
    assert payload["production_state_unchanged"] is True
    assert payload["next_phase"] == "M11-BLOCKER-00"
    assert payload["m12_entry_allowed"] is False


def test_17_batches_only_and_no_batch18(closeout) -> None:
    snapshot = _artifact(SNAPSHOT_FILE)
    readiness = _artifact("M11_READINESS_V2.json")
    batch_ids = {row["batch_id"] for row in readiness["batches"]}
    assert snapshot["batch_count"] == 17
    assert batch_ids == set(EXPECTED_BATCH_IDS)
    assert "REPAIR_BATCH_18" not in batch_ids
    assert payload_check(closeout, "no_repair_batch_18") is True
    assert payload_check(closeout, "all_17_batches_entered_production_execution") is True


def payload_check(closeout, name: str) -> bool:
    service, payload = closeout
    return bool(payload["closeout_checks"][name])


def test_no_ready_batch_and_no_remaining_ready_targets(closeout) -> None:
    snapshot = _artifact(SNAPSHOT_FILE)
    readiness = _artifact("M11_READINESS_V2.json")
    counts = readiness["execution_status_counts"]
    assert counts == closed({"BLOCKED": 17}, {"COMPLETE": 17})
    assert "READY" not in counts and "PARTIAL_READY" not in counts
    assert snapshot["remaining_ready_targets"] == 0
    assert sum(len(row["ready_target_ids"]) for row in readiness["batches"]) == 0
    assert payload_check(closeout, "no_ready_or_partial_ready_batch") is True


def test_all_auto_safe_runs_closed(closeout) -> None:
    service, payload = closeout
    runs = payload["auto_safe_runs"]
    assert runs["count"] == len(AUTO_SAFE_RUN_IDS) == 12
    assert [row["run_id"] for row in runs["runs"]] == list(AUTO_SAFE_RUN_IDS)
    assert runs["all_closed"] is True
    for row in runs["runs"]:
        assert row["gate_status"] == "PASS"
        assert row["scope_closed"] is True
        assert row["frontier_ready_now"] == 0
    assert payload_check(closeout, "final_frontier_scope_fully_processed") is True
    assert payload_check(closeout, "no_scope_outside_execution") is True


# ---------------------------------------------------------------- 372 / targets
def test_372_exact_conservation_and_reconciliation(closeout) -> None:
    snapshot = _artifact(SNAPSHOT_FILE)
    overlay = _artifact("M11_OVERLAY_V2.json")
    assert snapshot["total_primary_targets"] == TARGET_COUNT
    assert overlay["conservation"] == {"primary_total": TARGET_COUNT,
                                       "target_count": TARGET_COUNT, "exact": True}
    assert sum(overlay["primary_resolution_status_counts"].values()) == TARGET_COUNT
    assert list(overlay["primary_resolution_status_counts"]) == list(PRIMARY_BUCKETS)
    assert snapshot["resolved_total"] + snapshot["remaining_non_terminal"] == TARGET_COUNT
    report_records("AUTO_SAFE_SWEEP_CLOSEOUT", "M11-AUTO-SAFE-SWEEP-CLOSEOUT = PASS")
    assert snapshot["resolved_total"] == closed(223, 372)
    assert snapshot["remaining_non_terminal"] == closed(149, 0)
    assert snapshot["resolved_repaired"] == closed(163, 305)
    assert snapshot["resolved_no_repair_required"] == closed(60, 67)
    # [M11-CLOSURE] closeout 时的 bucket 构成（3/15/58/2/71）是历史值（frozen report）
    report_records("AUTO_SAFE_SWEEP_CLOSEOUT", "M11-AUTO-SAFE-SWEEP-CLOSEOUT = PASS")
    assert (snapshot["evidence_ready"], snapshot["manual_required"],
            snapshot["content_design_required"], snapshot["author_decision"],
            snapshot["pending"]) == closed((3, 15, 58, 2, 71), (0, 0, 0, 0, 0))
    assert payload_check(closeout, "overlay_372_exact_conservation") is True


def test_blocker_entry_inventory_exact_set(closeout) -> None:
    service, payload = closeout
    inventory = _artifact(TARGETS_FILE)
    expected = _non_terminal_ids()
    inventory_ids = {row["target_id"] for row in inventory["targets"]}
    report_records("AUTO_SAFE_SWEEP_CLOSEOUT", "| remaining blocked primary targets | **149** |")
    assert inventory["count"] == len(inventory["targets"]) == closed(149, 0)
    assert inventory_ids == expected                     # 无遗漏
    assert len(inventory_ids) == len(inventory["targets"])  # 无重复
    readiness = _artifact("M11_READINESS_V2.json")
    resolved_ids = {str(item) for row in readiness["batches"]
                    for item in row["resolved_target_ids"]}
    assert not (inventory_ids & resolved_ids)            # 无 terminal target
    required = {"target_id", "chapter", "current_overlay_status",
                "current_readiness_status", "current_direct_blockers",
                "derived_blockers", "existing_backlog_refs",
                "content_design_requirement_refs", "dependency_roots",
                "source_batch", "truth_risk", "current_owner_hint"}
    for row in inventory["targets"]:
        assert required <= set(row)
        assert row["current_readiness_status"]["state"] in ("READY", "BLOCKED")
        assert row["current_owner_hint"] in (
            "CONTENT_DESIGN", "MANUAL", "AUTHOR_DECISION", "ENTITY",
            "CONFIRMED_BINDING", "AUTO_SAFE_RESIDUAL_CANDIDATE",
            "TRIAGE_REQUIRED")
        assert row["truth_risk"] in ("HIGH", "MEDIUM", "LOW", "UNKNOWN")
    assert inventory["basis"].startswith("372 primary targets")
    assert "BLOCKER-00" in inventory["owner_hint_semantics"]


def test_derived_blocker_boundary_documented(closeout) -> None:
    baseline = _artifact(ENTRY_BASELINE_FILE)
    projection = baseline["derived_blocker_projection"]
    report_records("BLOCKER_00", "content 304 / entity 45 / manual 105 /")
    assert projection["occurrence_counts"] == closed({
        "BLOCKED_AUTHOR_DECISION": 17, "BLOCKED_CONTENT_DESIGN": 304,
        "BLOCKED_ENTITY_AMBIGUITY": 45, "BLOCKED_MANUAL_REPAIR": 105}, {})
    assert "DERIVED_BLOCKER_COUNT_IS_NOT_EXECUTION_ITEM_COUNT" in projection["note"]
    assert "DERIVED_BLOCKER_COUNT_IS_NOT_EXECUTION_ITEM_COUNT" in \
        BLOCKER_ENTRY_INVARIANTS


# ---------------------------------------------------------------- backlog / queue
def test_backlog_snapshot_consistency(closeout) -> None:
    backlog = _artifact(BACKLOG_FILE)
    live = _artifact("M11_PRODUCTION_BACKLOG.json")
    assert backlog["item_count"] == live["item_count"] == 74
    assert backlog["lane_counts"] == live["lane_counts"]
    assert set(backlog["lane_counts"]) == set(BACKLOG_LANES)
    assert backlog["lane_counts"] == {
        "LANE_AUTO_SAFE_BATCH": 13, "LANE_AUTHOR_POLICY": 1,
        "LANE_AUTHOR_CONTENT": 3, "LANE_MAJOR_DESIGN": 2,
        "LANE_AUTHOR_DECISION": 6, "LANE_MANUAL": 16, "LANE_ENTITY": 2,
        "LANE_CONTENT_REWRITE": 31}
    assert backlog["done_item_count"] + backlog["active_item_count"] == \
        backlog["item_count"]
    report_records("BLOCKER_00", "74 item（ACTIVE 61 / DONE 13）")
    assert backlog["done_item_count"] == closed(13, 73)
    assert backlog["active_item_count"] == closed(61, 1)
    assert backlog["verdict"] == "PASS"


def test_auto_safe_backlog_items_all_done(closeout) -> None:
    backlog = _artifact(BACKLOG_FILE)
    auto = backlog["auto_safe_lane"]
    assert auto["lane"] == "LANE_AUTO_SAFE_BATCH"
    assert auto["item_count"] == 13
    assert auto["all_done"] is True
    assert auto["phase_status"] == "PHASE_A_COMPLETE"
    assert all(row["status"] == "DONE" for row in auto["items"])
    assert {row["completed_by_run"] for row in auto["items"]} == {
        f"M11_RUN_{index:02d}" for index in range(1, 13)}
    assert "residual AUTO_SAFE" in backlog["auto_safe_lane_rule"]


def test_cdq_closeout_and_queue_conservation(closeout) -> None:
    cdq = _artifact(CDQ_FILE)
    overlay = _artifact("M11_OVERLAY_V2.json")
    queue3 = _artifact("M11_CONTENT_DESIGN_QUEUE_V3.json")
    assert cdq["v2_item_count"] == 72
    assert len(cdq["v2_item_ids"]) == len(set(cdq["v2_item_ids"])) == 72
    report_records("CONTENT_DESIGN_01", "CONTENT_DESIGN 58 / ENTITY 18 / MANUAL 15 / AUTHOR_DECISION 3")
    assert cdq["v3_active_count"] == queue3["active_count"] == closed(58, 0)
    assert (cdq["overlay_content_design_required"]
            == overlay["content_design_required"] == closed(58, 0))
    assert cdq["active_matches_overlay"] is True
    assert len(cdq["active_ids"]) == closed(58, 0)
    assert cdq["orphan_requirements"] == []
    assert cdq["uncovered"] == []
    assert cdq["duplicate_design_item_ids"] == []
    assert cdq["duplicate_ownership"] == []
    assert cdq["resolved_by_closeout"] == 0
    assert cdq["verdict"] == "PASS"


# ---------------------------------------------------------------- isolation / truth
def test_p15_isolation_pass(closeout) -> None:
    service, payload = closeout
    p15 = payload["p15_isolation"]
    assert p15["status"] == "PASS"
    assert p15["invariant_id"] == "P15_EXECUTOR_READ_ONLY_AFTER_CLOSEOUT"
    assert p15["invariant_status"] == "PASS"
    assert p15["static_scan_pass"] is True
    assert p15["runtime_isolation_pass"] is True
    assert p15["production_item_ownership_pass"] is True
    assert p15["regression_digests_unchanged"] is True
    assert p15["contamination_regression"] == ["reclassify", "frontier planner",
                                               "wave-02 scope"]


def test_truth_foundation_contract_gate_unchanged(closeout) -> None:
    service, payload = closeout
    baseline = _artifact(ENTRY_BASELINE_FILE)
    snapshot = _artifact(SNAPSHOT_FILE)
    truth = baseline["truth_digests"]
    assert truth["canon"] == FROZEN_SOURCE_DIGESTS["canon"]
    assert truth["story_state"] == FROZEN_SOURCE_DIGESTS["story_state"]
    assert truth["legacy"] == FROZEN_SOURCE_DIGESTS["legacy"]
    assert truth["chapter_ir"] == FROZEN_SOURCE_DIGESTS["chapter_ir"]
    assert truth["historical_foundation"] == FROZEN_FOUNDATION_DIGESTS
    assert baseline["historical_foundation_digests"] == FROZEN_FOUNDATION_DIGESTS
    assert baseline["contract_digest"] == "67559aa55442d69e"
    assert baseline["gate_digest"] == "e1eab4c33ae75b01"
    assert snapshot["repair_contract_digest"] == "67559aa55442d69e"
    assert snapshot["repair_gate_digest"] == "e1eab4c33ae75b01"
    for name in ("source_digests_unchanged", "historical_foundation_unchanged",
                 "repair_contract_digest_unchanged", "repair_gate_digest_unchanged"):
        assert payload["closeout_checks"][name] is True, name


def test_no_repair_owned_production_mutation_during_closeout(closeout) -> None:
    service, payload = closeout
    assert payload["production_state_unchanged"] is True
    assert payload["production_state_digests_before"] == \
        payload["production_state_digests_after"]
    # closeout 重跑幂等：再跑一次不改变 production digests
    second = M11SweepCloseoutService(ROOT).run()
    assert second["production_state_digests_before"] == \
        payload["production_state_digests_before"]
    report_records("AUTO_SAFE_SWEEP_CLOSEOUT", "M11-AUTO-SAFE-SWEEP-CLOSEOUT = PASS")
    assert second["status"] == closed("PASS", "FAIL")


def test_field_rebind_remains_not_proven(closeout) -> None:
    baseline = _artifact(ENTRY_BASELINE_FILE)
    field_rebind = baseline["field_rebind_status"]
    assert field_rebind["capability"] == "NOT_PROVEN"
    assert field_rebind["classification_seen"] is True
    assert field_rebind["safe_auto_production_promotion_proven"] is False
    assert field_rebind["safe_auto_promotions"] == 0
    assert {row["chapter"] for row in field_rebind["natural_cases"]} == {
        "ch324", "ch425", "ch445", "ch498", "ch546"}
    assert not (DESIGN_DIR / "PRODUCTION_CAPABILITY_EVIDENCE.json").is_file()


# ---------------------------------------------------------------- phase transition
def test_blocker_layer_remains_planned_only(closeout) -> None:
    service, payload = closeout
    baseline = _artifact(ENTRY_BASELINE_FILE)
    assert baseline["blocker_layer_status"] == "PLANNED_ONLY"
    assert baseline["blocker_layer_phase_status"] == "NEXT_PHASE_PLANNED"
    assert payload["blocker_layer_status"] == "PLANNED_ONLY"
    assert payload["blocker_layer_phase_status"] == "NEXT_PHASE_PLANNED"
    # closeout 时点 blocker layer = PLANNED_ONLY（冻结在 entry baseline）；
    # 后续 M11-BLOCKER-00（analysis-only）允许 analysis artifacts，但执行组件必须保持 PLANNED_ONLY。
    assert not (DESIGN_DIR / "m11_blocker_00").exists()
    blocker_baseline = DESIGN_DIR / "M11_BLOCKER_BASELINE.json"
    if blocker_baseline.is_file():
        status = json.loads(blocker_baseline.read_text(encoding="utf-8"))[
            "component_status"]
        for name in ("ContentDesignResolver", "EntityResolutionEngine",
                     "ManualRepairWorkbench", "AuthorDecisionConsole",
                     "BlockerResolutionOrchestrator"):
            assert status[name] == "PLANNED_ONLY"


def test_entry_baseline_complete(closeout) -> None:
    baseline = _artifact(ENTRY_BASELINE_FILE)
    required = {"source_commit", "auto_safe_sweep_status", "total_primary_targets",
                "terminal_targets", "non_terminal_targets",
                "non_terminal_target_ids", "overlay_summary", "backlog_summary",
                "cdq_summary", "batch_summary", "derived_blocker_projection",
                "truth_digests", "historical_foundation_digests",
                "contract_digest", "gate_digest", "p15_isolation_status",
                "m12_entry_status", "blocker_layer_status", "entry_invariants"}
    assert required <= set(baseline)
    assert baseline["auto_safe_sweep_status"] == "COMPLETE"
    assert baseline["total_primary_targets"] == 372
    assert baseline["terminal_targets"] == closed(223, 372)
    assert baseline["non_terminal_targets"] == closed(149, 0)
    assert len(baseline["non_terminal_target_ids"]) == closed(149, 0)
    assert baseline["p15_isolation_status"] == "PASS"
    assert baseline["m12_entry_status"]["m12_entry_allowed"] is False
    invariants = set(baseline["entry_invariants"])
    for name in ("DERIVED_BLOCKER_COUNT_IS_NOT_EXECUTION_ITEM_COUNT",
                 "ROOT_BLOCKER_FIRST", "AUTHOR_DECISION_IS_BATCHED",
                 "P15_EXECUTOR_READ_ONLY_AFTER_CLOSEOUT",
                 "TRUTH_BOUNDARY_UNCHANGED", "BLOCKER_00_BEFORE_LANE_EXECUTION",
                 "NO_DIRECT_BACKLOG_DRAIN_BEFORE_ROOT_CAUSE_GRAPH"):
        assert name in invariants
    assert "禁止直接执行" in baseline["entry_invariant_semantics"][
        "BLOCKER_00_BEFORE_LANE_EXECUTION"]
    assert "backlog 顺序逐项处理" in baseline["entry_invariant_semantics"][
        "NO_DIRECT_BACKLOG_DRAIN_BEFORE_ROOT_CAUSE_GRAPH"]


def test_no_run13_and_blocker_phase_not_started(closeout) -> None:
    service, payload = closeout
    assert not (DESIGN_DIR / "M11_RUN_13_RECONCILIATION.json").exists()
    assert not (DESIGN_DIR / "m11_run_13").exists()
    assert payload["next_phase"] == "M11-BLOCKER-00"
    assert payload["m12_entry_allowed"] is False


def test_m12_remains_false(closeout) -> None:
    criteria = _artifact("p15p/M12_ENTRY_CRITERIA.json")
    baseline = _artifact(ENTRY_BASELINE_FILE)
    assert criteria["m12_entry_allowed"] is False
    assert (criteria["satisfied_count"] + criteria["unsatisfied_count"]
            == criteria["criteria_count"])
    assert criteria["unsatisfied_count"] == len(criteria["unsatisfied_criteria"])
    assert criteria["blocking_count"] == len(criteria["blocking_criteria"])
    status = baseline["m12_entry_status"]
    assert status["m12_entry_allowed"] is False
    assert (status["satisfied_count"] + status["unsatisfied_count"]
            == status["criteria_count"])
    report_records("AUTO_SAFE_SWEEP_CLOSEOUT", "M11-AUTO-SAFE-SWEEP-CLOSEOUT = PASS")


def test_closeout_summary_artifact_and_verdict(closeout) -> None:
    summary = _artifact(CLOSEOUT_FILE)
    report_records("AUTO_SAFE_SWEEP_CLOSEOUT", "M11-AUTO-SAFE-SWEEP-CLOSEOUT = PASS")
    assert summary["status"] == closed("PASS", "FAIL")
    assert summary["phase_status"] == PHASE_STATUS
    assert summary["closeout_id"] == "M11-AUTO-SAFE-SWEEP-CLOSEOUT"
    assert set(summary["failed_checks"]) <= {"active_cdq_matches_overlay"}
    assert summary["next_phase"] == "M11-BLOCKER-00"
    assert set(summary["artifacts"]) == {
        "final_snapshot", "blocker_entry_targets", "backlog_snapshot",
        "cdq_snapshot", "blocker_00_entry_baseline", "closeout_summary"}
    for name in (SNAPSHOT_FILE, TARGETS_FILE, BACKLOG_FILE, CDQ_FILE,
                 ENTRY_BASELINE_FILE):
        assert (DESIGN_DIR / name).is_file(), name
