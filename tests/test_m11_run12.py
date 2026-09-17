"""M11-RUN-12：Production Execution 回归（Final Auto Safe Frontier — Batch 17）。"""

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
from novelforge.story_engine.m11_run12 import (

    BATCH_17,
    BATCH_17_SCOPE_COMPAT_FILE,
    BATCH_17_SCOPE_FILE,
    NEXT_BATCH_ID,
    M11Run12Service,
    RUN_ID,
    RUN_RECONCILIATION,
)

from m11_phase_history import closed, assert_m12_projection

ROOT = Path(".").resolve()
DESIGN_DIR = ROOT / "workspace/wasteland_001_exports/repair_adoption_v1"
REPAIR_DIR = ROOT / "workspace/wasteland_001_exports/repair_v1"
RUN_DIR = DESIGN_DIR / "m11_run_12"
EXECUTED_BATCHES = {f"REPAIR_BATCH_{index:02d}" for index in range(1, 18)}


@pytest.fixture(scope="module")
def run12():
    service = M11Run12Service(ROOT)
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
def test_scope_frozen_before_execution(run12) -> None:
    service, payload = run12
    scope = _run_artifact("M11_RUN_12_EXECUTION_SCOPE.json")
    assert scope["frozen"] is True and scope["run_id"] == RUN_ID
    assert scope["contract_digest"] == "67559aa55442d69e"
    assert scope["gate_digest"] == "e1eab4c33ae75b01"
    assert payload["execution_scope"]["frozen"] is True
    baseline = _run_artifact("M11_RUN_12_BASELINE.json")
    assert baseline["frozen_contract"]["contract"] == "67559aa55442d69e"
    assert baseline["frozen_contract"]["repair_gate"] == "e1eab4c33ae75b01"
    # RUN-11 收口状态原样进入 RUN-12 baseline（freeze 在 repair 之前）
    assert baseline["primary_buckets"] == {
        "resolved_repaired": 159, "resolved_no_repair_required": 58,
        "evidence_ready": 3, "manual_required": 14,
        "content_design_required": 56, "author_decision": 2, "pending": 80}
    assert baseline["batch_execution_status_counts"] == {"BLOCKED": 16,
                                                         "PARTIAL_READY": 1}
    assert baseline["frozen_contract"]["overlay_v2"] != service.frozen_digests()[
        "overlay_v2"]                                        # freeze-then-execute
    assert payload["reconciliation"]["promoted"] + sum(
        payload["reconciliation"]["dynamic_downgrade_counts"].values()) == 9


def test_batch17_baseline_recomputed_and_closure(run12) -> None:
    service, payload = run12
    scope = _artifact(DESIGN_DIR / BATCH_17_SCOPE_FILE)
    assert scope["frozen"] is True and scope["batch_id"] == BATCH_17
    assert len(scope["ready_target_ids"]) == 9
    assert len(scope["blocked_target_ids"]) == 4
    closure = scope["dependency_closure"]
    assert closure["readiness_ready_count"] == 9
    assert closure["readiness_blocked_count"] == 4
    assert closure["continuity_ready_count"] == 6  # [M11-CLOSURE] 已由 final closure terminal
    assert closure["continuity_blocked_count"] == closed(4, 0)
    # [M11-CLOSURE] blocker 分类在 M11 final closure 后全部归零（scope 本身仍 frozen）
    assert closure["classification"]["content_design_blocked"] == 0
    assert closure["classification"]["entity_blocked"] == 0
    assert closure["classification"]["manual_blocked"] == 0
    assert closure["classification"]["author_blocked"] == 0
    assert closure["classification"]["confirmed_binding_blocked"] == 0
    assert closure["classification"]["architecture_exception"] == 0
    assert closure["blocker_counts"] == closed({"BLOCKED_MANUAL_REPAIR": 4}, {})
    assert (DESIGN_DIR / BATCH_17_SCOPE_COMPAT_FILE).is_file()
    assert scope["baseline_truth_digests"]["canon"] == FROZEN_SOURCE_DIGESTS["canon"]
    assert payload["frontier"]["scope"] == {"ready": 9, "blocked": 4}
    assert payload["frontier"]["scope_frozen"] is True
    labels = service.labels(service.inputs())
    assert {labels[item] for item in scope["ready_target_ids"]} == {
        "ch560", "ch562", "ch563", "ch564", "ch566", "ch567", "ch568", "ch569",
        "ch570"}
    assert {labels[item] for item in scope["blocked_target_ids"]} == {
        "ch549", "ch551", "ch552", "ch554"}


def test_only_baseline_ready_executed(run12) -> None:
    service, payload = run12
    scope = _run_artifact("M11_RUN_12_EXECUTION_SCOPE.json")
    ready = {str(item) for item in scope["batch_17_ready_targets"]}
    reconciliation = _artifact(DESIGN_DIR / RUN_RECONCILIATION)
    executed = {row["chapter_id"] for row in reconciliation["records"]
                if row["old_status"] == "not_processed"
                and row["new_resolution_status"] not in (
                    "BLOCKED_CONTENT_DESIGN", "BLOCKED_MANUAL_REPAIR")}
    assert executed == ready
    execution = _run_artifact("M11_RUN_12_BATCH17_EXECUTION.json")
    assert {str(item) for item in execution["targets"]} == ready
    assert execution["execution_kind"] == "AUTO_SAFE_FRONTIER"
    assert payload["gate"]["checks"]["only_ready_target_executed"] is True


def test_baseline_blocked_targets_untouched(run12) -> None:
    service, payload = run12
    scope = _run_artifact("M11_RUN_12_EXECUTION_SCOPE.json")
    blocked = {str(item) for item in scope["batch_17_blocked_targets"]}
    assert len(blocked) == 4
    reconciliation = _artifact(DESIGN_DIR / RUN_RECONCILIATION)
    for row in reconciliation["records"]:
        if row["chapter_id"] in blocked:
            assert row["old_status"] == "blocked_out_of_scope"
            assert str(row["new_resolution_status"]).startswith("BLOCKED_")
            assert row["repaired_ref"] == "" and row["patch_ops"] == []
            assert row["execution_decision"] == ""
    execution = _run_artifact("M11_RUN_12_BATCH17_EXECUTION.json")
    assert set(execution["blocked_targets"]) == blocked
    assert not set(execution["targets"]) & blocked
    assert payload["gate"]["checks"]["blocked_target_untouched"] is True
    assert {str(item) for item in payload["gate"]["blocked_target_ids"]} == blocked


def test_runtime_newly_unlocked_deferred(run12) -> None:
    """执行后不得存在被偷偷追加执行的 target：scope closed 且无 READY。"""

    service, payload = run12
    readiness = _artifact(DESIGN_DIR / "M11_READINESS_V2.json")
    total_ready = sum(len(row["ready_target_ids"]) for row in readiness["batches"])
    assert total_ready == 0
    b17 = _batch(readiness, BATCH_17)
    assert b17["execution_status"] == "COMPLETE"  # [M11-CLOSURE] 全部 batch 已 terminal
    assert b17["ready_target_ids"] == []
    scope = _run_artifact("M11_RUN_12_EXECUTION_SCOPE.json")
    reconciliation = _artifact(DESIGN_DIR / RUN_RECONCILIATION)
    executed = {row["chapter_id"] for row in reconciliation["records"]
                if row["old_status"] == "not_processed"
                and not str(row["new_resolution_status"]).startswith("BLOCKED_")}
    assert executed == {str(item) for item in scope["batch_17_ready_targets"]}


def test_no_hidden_batch18_or_fabricated_next_batch(run12) -> None:
    service, payload = run12
    readiness = _artifact(DESIGN_DIR / "M11_READINESS_V2.json")
    batch_ids = {row["batch_id"] for row in readiness["batches"]}
    assert len(readiness["batches"]) == 17
    assert NEXT_BATCH_ID not in batch_ids
    assert not any(str(item).startswith("REPAIR_BATCH_18") for item in batch_ids)
    gate = _run_artifact("M11_RUN_12_GATE.json")
    assert gate["checks"]["batch18_not_entered"] is True
    assert payload["batch_18_executed"] is False


def test_batch17_execution_and_promotion(run12) -> None:
    service, payload = run12
    execution = _run_artifact("M11_RUN_12_BATCH17_EXECUTION.json")
    assert execution["verified"] == 6
    assert execution["human_review"] == 3
    assert execution["promotion_mode"] == "partial"
    assert execution["gate_status"] == "PASS"
    diff = execution["diff"]
    assert diff["semantic_elements_added"] == 0
    assert diff["semantic_elements_removed"] == 0
    assert diff["confirmed_facts_changed"] == 0
    assert diff["read_only_chapters_changed"] == 0
    reconciliation = _artifact(DESIGN_DIR / RUN_RECONCILIATION)
    assert reconciliation["record_count"] == 13          # 9 executed + 4 blocked
    assert reconciliation["promoted"] == 6
    assert reconciliation["promoted_evidence_only"] == 4
    assert reconciliation["promoted_no_repair_required"] == 2
    assert reconciliation["promoted_field_rebind"] == 0
    assert reconciliation["records_modified"] is False
    assert payload["frontier"]["acceptance"] == "PASS"


def test_dynamic_downgrade_honesty(run12) -> None:
    service, payload = run12
    reconciliation = _artifact(DESIGN_DIR / RUN_RECONCILIATION)
    counts = reconciliation["dynamic_downgrade_counts"]
    assert counts["CONTENT_DESIGN_REQUIRED"] == 2       # ch560 / ch570
    assert counts["MANUAL_REQUIRED"] == 1               # ch563（substrate partial）
    assert counts["EVIDENCE_READY"] == 0
    assert counts["AUTHOR_DECISION_REQUIRED"] == 0
    assert counts["BLOCKED_CONFIRMED_BINDING_CONFLICT"] == 0
    assert counts["ARCHITECTURE_EXCEPTION_REQUIRED"] == 0
    manual = {row["legacy_label"]: row for row in reconciliation["records"]
              if row["new_resolution_status"] == "MANUAL_REQUIRED"}
    assert set(manual) == {"ch563"}
    assert manual["ch563"]["repair_class"] == "EVIDENCE_ONLY"
    assert "HISTORICAL_FULL_IR_PARTIAL" in manual["ch563"]["reason"]
    assert manual["ch563"]["execution_decision"] == "MANUAL"
    assert manual["ch563"]["repaired_ref"] == ""
    content = {row["legacy_label"]: row for row in reconciliation["records"]
               if row["new_resolution_status"] == "CONTENT_DESIGN_REQUIRED"}
    assert set(content) == {"ch560", "ch570"}
    for row in content.values():
        assert row["repair_class"] == "SEMANTIC_ADDITION_REQUIRED"
        assert row["design_item_id"] == f"CDQ_RUN12_{row['legacy_label']}"
        assert row["repaired_ref"] == ""
    downgrades = sum(value for key, value in counts.items() if key != "EVIDENCE_READY")
    assert reconciliation["promoted"] == 6 and downgrades == 3
    assert reconciliation["promoted"] / downgrades >= 2.0
    assert payload["frontier"]["verified"] == 6


def test_event_added_cannot_safe_auto(run12) -> None:
    service, payload = run12
    reconciliation = _artifact(DESIGN_DIR / RUN_RECONCILIATION)
    promoted = [row for row in reconciliation["records"]
                if row["new_resolution_status"] in ("RESOLVED_REPAIRED",
                                                    "RESOLVED_NO_REPAIR_REQUIRED")]
    allowed_ops = {"REBIND_EVIDENCE", "MARK_NOT_APPLICABLE", "RECLASSIFY_FUNCTION",
                   "REBIND_STATE_REFERENCE"}
    assert all(op in allowed_ops for row in promoted for op in row["patch_ops"])
    gate = _run_artifact("M11_RUN_12_GATE.json")
    assert gate["checks"]["no_new_historical_event_promoted"] is True
    assert payload["gate"]["new_historical_events"] == 0


def test_unsafe_field_rebind_cannot_promote(run12) -> None:
    service, payload = run12
    reconciliation = _artifact(DESIGN_DIR / RUN_RECONCILIATION)
    assert reconciliation["promoted_field_rebind"] == 0
    ledger = _artifact(DESIGN_DIR / "M11_REPAIR_SUBTYPE_LEDGER.json")
    assert ledger["resolved_subtype_counts"].get("repaired_field_rebind", 0) == 0
    assert payload["field_rebind_natural_end_to_end"] is False
    assert not (DESIGN_DIR / "PRODUCTION_CAPABILITY_EVIDENCE.json").is_file()
    capability = _artifact(DESIGN_DIR / "p15p/P15_CAPABILITY_ACCEPTANCE_MATRIX.json")
    verdicts = {row["capability"]: row["verdict"] for row in capability["capabilities"]}
    assert verdicts["Field Rebind"] == "NOT_PROVEN"
    # 累计 5 个自然 FIELD_REBIND classification（ch324/425/445/498/546）全部未 promote
    field_rebind_total = 0
    for index in range(5, 13):
        records = _artifact(DESIGN_DIR / f"M11_RUN_{index:02d}_RECONCILIATION.json"
                            )["records"]
        for row in records:
            if row["repair_class"] == "FIELD_REBIND":
                field_rebind_total += 1
                assert row["new_resolution_status"] != "RESOLVED_REPAIRED"
    assert field_rebind_total == 5


def test_safe_field_rebind_requires_all_frozen_gates(run12) -> None:
    service, payload = run12
    # 本轮 Batch 17 未出现 FIELD_REBIND classification；不存在被强制 promote 的样本
    reconciliation = _artifact(DESIGN_DIR / RUN_RECONCILIATION)
    assert not [row for row in reconciliation["records"]
                if row["repair_class"] == "FIELD_REBIND"]
    promoted = [row for row in reconciliation["records"]
                if row["new_resolution_status"] in ("RESOLVED_REPAIRED",
                                                    "RESOLVED_NO_REPAIR_REQUIRED")]
    assert not [row for row in promoted if row["repair_class"] == "FIELD_REBIND"]
    assert payload["gate"]["checks"]["no_new_repair_taxonomy"] is True
    assert payload["gate"]["checks"]["readiness_consistent"] is True


# ---------------------------------------------------------------- production CDQ
def test_production_cdq_registration_and_origin(run12) -> None:
    service, payload = run12
    reconciliation = _artifact(DESIGN_DIR / RUN_RECONCILIATION)
    registered = reconciliation["content_design_items_registered"]
    assert len(registered) == 2
    assert {row["design_item_id"] for row in registered} == {
        "CDQ_RUN12_ch560", "CDQ_RUN12_ch570"}
    for row in registered:
        assert row["origin"] == "M11_RUN_12_DYNAMIC_DOWNGRADE"
        assert str(row["design_item_id"]).startswith("CDQ_RUN12_")
        assert row["status"] == "PENDING_DESIGN"
    queue2 = _artifact(DESIGN_DIR / "M11_CONTENT_DESIGN_QUEUE_V2.json")
    items = {row["design_item_id"]: row for row in queue2["items"]}
    for item_id in ("CDQ_RUN12_ch560", "CDQ_RUN12_ch570"):
        assert items[item_id]["origin"] == "M11_RUN_12 dynamic downgrade"
    ContentRewritePolicyService(ROOT).reclassify()
    reclassification = _artifact(
        DESIGN_DIR / "p15n" / "CONTENT_REPAIR_RECLASSIFICATION.json")
    rows = {row["legacy_label"]: row for row in reclassification["rows"]
            if row.get("production_run_item")}
    queue_status = {str(row.get("legacy_label")): str(row.get("status"))
                    for row in _artifact(
                        DESIGN_DIR / "M11_CONTENT_DESIGN_QUEUE_V3.json")["requirements"]}
    for label in ("ch560", "ch570"):
        # [M11-CLOSURE] production CDQ item 已 terminal（从 active reclassification 视图移出）；
        # 仍必须在 production CDQ queue 中可追溯
        assert str(queue_status.get(label, "")).startswith("RESOLVED"), label
        assert rows.get(label, {}).get("micro_scale_candidate", False) is False
    assert payload["reconciliation"]["content_design_items_registered"] == 2


def test_content_design_queue_id_reconciliation(run12) -> None:
    """§8：V2 lifecycle 必须按 ID reconciliation（不只是比较数字）。"""

    service, _payload = run12
    audit = _run_artifact("CONTENT_DESIGN_QUEUE_LIFECYCLE_AUDIT.json")
    assert audit["before_run"] == "M11_RUN_11"
    assert audit["added_runs"] == ["M11_RUN_12"]
    assert audit["before_item_count"] == 70
    assert audit["added_item_count"] == 2
    assert audit["window_after_item_count"] == audit["after_item_count"] == 72
    assert audit["later_item_count"] == 0
    assert audit["added_ids"] == ["CDQ_RUN12_ch560", "CDQ_RUN12_ch570"]
    assert audit["removed_or_superseded_ids"] == []
    assert audit["duplicate_design_item_ids"] == []
    assert audit["verdict"] == "NO_DATA_LOSS"
    queue2 = _artifact(DESIGN_DIR / "M11_CONTENT_DESIGN_QUEUE_V2.json")
    ids = [row["design_item_id"] for row in queue2["items"]]
    assert len(ids) == len(set(ids)) == 72
    assert set(audit["added_ids"]) <= set(ids)
    registered: list[str] = []
    for index in range(2, 13):
        path = DESIGN_DIR / f"M11_RUN_{index:02d}_RECONCILIATION.json"
        if not path.is_file():
            continue
        for row in _artifact(path).get("content_design_items_registered") or []:
            registered.append(str(row["design_item_id"]))
    assert registered and set(registered) <= set(ids)
    assert len(registered) == len(set(registered))        # duplicate ownership = 0


def test_active_cdq_matches_overlay_and_no_orphans(run12) -> None:
    service, payload = run12
    queue3 = _artifact(DESIGN_DIR / "M11_CONTENT_DESIGN_QUEUE_V3.json")
    active = [row for row in queue3["requirements"] if row["status"] == "ACTIVE"]
    overlay = _artifact(DESIGN_DIR / "M11_OVERLAY_V2.json")
    queue_recon = _artifact(DESIGN_DIR / "p15n" /
                            "CONTENT_DESIGN_QUEUE_RECONCILIATION.json")
    assert len(active) == queue3["active_count"] == 0  # [M11-CLOSURE]
    assert len(active) == overlay["content_design_required"] == closed(58, 0)
    assert queue_recon["active_requirements"] == closed(58, 0)
    assert queue_recon["snapshot_items"] == 72
    assert queue_recon["orphan_requirements"] == []
    assert queue_recon["targets_without_requirement"] == []
    audit = _run_artifact("CONTENT_DESIGN_QUEUE_LIFECYCLE_AUDIT.json")
    assert audit["v3_matches_overlay"] is True
    integration = service.readiness.integrate_dynamic_design_items()
    assert integration["new_item_count"] == 0
    assert integration["merged_item_count"] == 72


# ---------------------------------------------------------------- P15 isolation
def test_p15_executor_isolation_and_regression(run12) -> None:
    service, payload = run12
    invariant = _run_artifact(f"{P15_ISOLATION_INVARIANT_ID}.json")
    assert invariant["status"] == "PASS"
    assert invariant["static_scan_pass"] is True
    assert invariant["runtime_isolation_pass"] is True
    assert invariant["production_item_ownership_pass"] is True
    assert invariant["production_item_count"] == 29
    assert not any(invariant["static_scan_findings"].values())
    assert not invariant["live_p15_artifacts_for_production_chapters"]
    gate = _run_artifact("M11_RUN_12_GATE.json")
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


# ---------------------------------------------------------------- overlay / readiness
def test_overlay_and_372_conservation(run12) -> None:
    service, payload = run12
    overlay = _artifact(DESIGN_DIR / "M11_OVERLAY_V2.json")
    assert overlay["conservation"] == {"primary_total": TARGET_COUNT,
                                       "target_count": TARGET_COUNT, "exact": True}
    assert list(overlay["primary_resolution_status_counts"]) == list(PRIMARY_BUCKETS)
    assert sum(overlay["primary_resolution_status_counts"].values()) == TARGET_COUNT
    assert overlay["resolved_total"] == 372  # [M11-CLOSURE] 372/372 terminal
    assert overlay["repaired"] == closed(163, 305)
    assert overlay["no_repair_required"] == closed(60, 67)
    assert overlay["repaired_evidence_only"] == closed(138, 164)
    assert overlay["repaired_field_rebind"] == 0
    assert overlay["repaired_micro_semantic"] == 21
    assert overlay["repaired_confirmed_override"] == 4
    assert overlay["evidence_ready"] == 0  # [M11-CLOSURE] evidence lane 已 terminal
    assert overlay["content_design_required"] == closed(58, 0)
    assert overlay["manual_required"] == closed(15, 0)
    assert overlay["author_decision"] == closed(2, 0)
    assert overlay["pending"] == closed(71, 0)
    assert payload["overlay_conservation"]["exact"] is True


def test_subtype_ledger_consistency(run12) -> None:
    service, _payload = run12
    overlay = _artifact(DESIGN_DIR / "M11_OVERLAY_V2.json")
    ledger = _artifact(DESIGN_DIR / "M11_REPAIR_SUBTYPE_LEDGER.json")
    counts = ledger["resolved_subtype_counts"]
    assert len(ledger["ledger"]) == overlay["resolved_total"] == 372  # [M11-CLOSURE]
    assert sum(counts.values()) == overlay["resolved_total"]
    assert counts["repaired_evidence_only"] == closed(138, 164)
    assert counts["no_repair_required"] == closed(60, 67)
    assert counts["repaired_micro_semantic"] == 21
    assert counts["repaired_confirmed_override"] == 4
    assert counts.get("repaired_field_rebind", 0) == 0


def test_readiness_final_state(run12) -> None:
    service, payload = run12
    readiness = _artifact(DESIGN_DIR / "M11_READINESS_V2.json")
    assert len(readiness["batches"]) == 17
    assert readiness["completion_status_counts"] == {"COMPLETE": 17}  # [M11-CLOSURE] 372/372 terminal
    counts = readiness["execution_status_counts"]
    assert counts == closed({"BLOCKED": 17}, {"COMPLETE": 17})
    total_ready = sum(len(row["ready_target_ids"]) for row in readiness["batches"])
    total_blocked = sum(len(row["blocked_target_ids"]) for row in readiness["batches"])
    total_resolved = sum(len(row["resolved_target_ids"]) for row in readiness["batches"])
    assert total_ready == 0
    assert total_resolved == payload["overlay"]["resolved_total"]
    assert total_resolved + total_blocked == TARGET_COUNT
    b17 = _batch(readiness, BATCH_17)
    assert (b17["completion_status"], b17["execution_status"]) == closed(
        ("IN_PROGRESS", "BLOCKED"), ("COMPLETE", "COMPLETE"))
    assert len(b17["resolved_target_ids"]) == closed(6, 13)
    assert b17["ready_target_ids"] == []
    assert len(b17["blocked_target_ids"]) == closed(7, 0)
    assert payload["readiness"]["execution_status_counts"] == counts
    for row in readiness["batches"]:
        assert row["completion_status"] in ("NOT_STARTED", "IN_PROGRESS", "COMPLETE",
                                           "HUMAN_REVIEW")
        assert row["execution_status"] in ("READY", "PARTIAL_READY", "BLOCKED",
                                           "NO_WORK", "COMPLETE")
        assert not set(row["ready_target_ids"]) & set(row["blocked_target_ids"])


def test_backlog_update(run12) -> None:
    service, payload = run12
    backlog = _artifact(DESIGN_DIR / "M11_PRODUCTION_BACKLOG.json")
    assert set(backlog["lane_counts"]) == set(BACKLOG_LANES)
    assert all(count >= 1 for count in backlog["lane_counts"].values())
    assert backlog["item_count"] == sum(backlog["lane_counts"].values()) == 74
    assert backlog["last_run"] == RUN_ID
    assert backlog["lane_counts"]["LANE_MANUAL"] == 16
    assert backlog["lane_counts"]["LANE_CONTENT_REWRITE"] == 31
    items = {row["item_id"]: row for row in backlog["items"]}
    assert items["BL_AUTO_B17"]["status"] == "DONE"
    assert items["BL_AUTO_B17"]["completed_by_run"] == RUN_ID
    assert items["BL_MANUAL_ch563"]["lane"] == "LANE_MANUAL"
    assert items["BL_CONTENT_DESIGN_ch560"]["lane"] == "LANE_CONTENT_REWRITE"
    assert items["BL_CONTENT_DESIGN_ch570"]["lane"] == "LANE_CONTENT_REWRITE"
    assert set(payload["backlog"]["done_item_ids"]) >= {"BL_AUTO_B17"}
    assert payload["backlog"]["item_count"] == backlog["item_count"]


def test_no_author_auto_resolution(run12) -> None:
    service, payload = run12
    inventory = _artifact(DESIGN_DIR / "AUTHOR_ACTION_INVENTORY.json")
    assert inventory["policy_selection"]["auto_selected"] == ""
    assert inventory["policy_selection"]["author_selected"] == ""
    assert inventory["auto_resolved"] == 0
    assert payload["author_policy_selected"] is False
    assert payload["author_decisions_resolved"] == 0
    reconciliation = _artifact(DESIGN_DIR / RUN_RECONCILIATION)
    assert not [row for row in reconciliation["records"]
                if row["new_resolution_status"] == "AUTHOR_DECISION_REQUIRED"]


def test_auto_safe_sweep_complete_exit_conditions(run12) -> None:
    """§12：AUTO_SAFE_SWEEP_COMPLETE 的 9 条 exit conditions 必须逐条成立。"""

    service, payload = run12
    scope = _run_artifact("M11_RUN_12_EXECUTION_SCOPE.json")
    readiness = _artifact(DESIGN_DIR / "M11_READINESS_V2.json")
    # 1. Batch 17（最后一个已知 AUTO_SAFE frontier）已执行完 frozen baseline
    assert scope["batch_17_ready_targets"] and len(scope["batch_17_ready_targets"]) == 9
    # 2. 不存在另一个尚未执行的既知 AUTO_SAFE batch
    assert {row["batch_id"] for row in readiness["batches"]} == EXECUTED_BATCHES
    assert set(readiness["execution_status_counts"]) == {"COMPLETE"}  # [M11-CLOSURE]
    # 3. 本轮 scope closed（B17 ready 0）
    b17 = _batch(readiness, BATCH_17)
    assert b17["ready_target_ids"] == []
    # 4. executed == frozen scope（没有偷偷追加执行）
    reconciliation = _artifact(DESIGN_DIR / RUN_RECONCILIATION)
    executed = {row["chapter_id"] for row in reconciliation["records"]
                if row["old_status"] == "not_processed"
                and not str(row["new_resolution_status"]).startswith("BLOCKED_")}
    assert executed == {str(item) for item in scope["batch_17_ready_targets"]}
    # 5. P15 isolation PASS
    assert payload["p15_isolation"]["status"] == "PASS"
    # 6. truth boundary unchanged
    baseline = _run_artifact("M11_RUN_12_BASELINE.json")
    assert baseline["truth_digests"] == service.truth_digests()
    # 7. Repair Contract / Gate unchanged
    assert baseline["frozen_contract"]["contract"] == "67559aa55442d69e"
    assert baseline["frozen_contract"]["repair_gate"] == "e1eab4c33ae75b01"
    # 8. overlay conservation PASS
    assert payload["overlay_conservation"] == {"primary_total": TARGET_COUNT,
                                               "target_count": TARGET_COUNT,
                                               "exact": True}
    # 9. queue conservation PASS
    audit = _run_artifact("CONTENT_DESIGN_QUEUE_LIFECYCLE_AUDIT.json")
    assert audit["verdict"] == "NO_DATA_LOSS" and audit["v3_matches_overlay"] is True
    # sweep complete ≠ M11 complete ≠ M12 entry
    assert payload["m12"]["entry_allowed"] is False


def test_m12_remains_false(run12) -> None:
    service, payload = run12
    criteria = _artifact(DESIGN_DIR / "p15p" / "M12_ENTRY_CRITERIA.json")
    assert criteria["m12_entry_allowed"] is False
    assert criteria["satisfied_count"] == len(criteria["satisfied_criteria"])  # [M11-CLOSURE]
    assert criteria["unsatisfied_count"] == len(criteria["unsatisfied_criteria"])
    assert criteria["blocking_count"] == len(criteria["blocking_criteria"])
    assert_m12_projection(payload["m12"], criteria)
    gate = _run_artifact("M11_RUN_12_GATE.json")
    assert gate["checks"]["m12_not_entered"] is True


def test_contract_gate_truth_and_foundation_digests_unchanged(run12) -> None:
    service, payload = run12
    baseline = _run_artifact("M11_RUN_12_BASELINE.json")
    gate = _run_artifact("M11_RUN_12_GATE.json")
    assert baseline["frozen_contract"]["contract"] == "67559aa55442d69e"
    assert baseline["frozen_contract"]["repair_gate"] == "e1eab4c33ae75b01"
    assert gate["frozen_contract"]["contract"] == "67559aa55442d69e"
    assert gate["frozen_contract"]["repair_gate"] == "e1eab4c33ae75b01"
    truth = baseline["truth_digests"]
    assert truth["canon"] == FROZEN_SOURCE_DIGESTS["canon"]
    assert truth["story_state"] == FROZEN_SOURCE_DIGESTS["story_state"]
    assert truth["legacy"] == FROZEN_SOURCE_DIGESTS["legacy"]
    assert truth["chapter_ir"] == FROZEN_SOURCE_DIGESTS["chapter_ir"]
    assert truth["historical_foundation"] == FROZEN_FOUNDATION_DIGESTS
    assert gate["checks"]["truth_digests_unchanged"] is True
    assert gate["checks"]["frozen_contract_unchanged"] is True
    assert gate["checks"]["frozen_repair_gate_unchanged"] is True
    assert payload["gate"]["confirmed_facts_changed"] == 0
    assert payload["gate"]["read_only_chapters_changed"] == 0


def test_blocker_layer_remains_planning_only(run12) -> None:
    service, payload = run12
    plan = (ROOT / "docs/M11_BLOCKER_RESOLUTION_PLAN.md").read_text(encoding="utf-8")
    assert "DERIVED_BLOCKER_COUNT_IS_NOT_EXECUTION_ITEM_COUNT" in plan
    assert "ROOT_BLOCKER_FIRST" in plan
    assert "AUTHOR_DECISION_IS_BATCHED" in plan
    assert "M11-BLOCKER-00" in plan
    # RUN-12 时点 blocker layer = planning only；后续 M11-BLOCKER-00（analysis-only）
    # 允许出现 analysis artifacts，但执行组件必须保持 PLANNED_ONLY。
    baseline_path = DESIGN_DIR / "M11_BLOCKER_BASELINE.json"
    if baseline_path.is_file():
        status = json.loads(baseline_path.read_text(encoding="utf-8"))["component_status"]
        for name in ("ContentDesignResolver", "EntityResolutionEngine",
                     "ManualRepairWorkbench", "AuthorDecisionConsole",
                     "BlockerResolutionOrchestrator"):
            assert status[name] == "PLANNED_ONLY"
    assert not (DESIGN_DIR / "m11_blocker_00").exists()
    gate = _run_artifact("M11_RUN_12_GATE.json")
    assert gate["checks"]["architecture_exception_recorded"] is True
    assert payload["architecture_exceptions"] == []


def test_run12_gate_pass_with_injected_evidence(run12) -> None:
    service, payload = run12
    gate = _run_artifact("M11_RUN_12_GATE.json")
    assert set(gate["failed_checks"]) <= {"full_pytest_pass", "validate_project_pass"}
    for key, value in gate["checks"].items():
        if key not in ("full_pytest_pass", "validate_project_pass"):
            assert value is True, key
    service.record_test_evidence(pytest_summary="injected", pytest_passed=1,
                                 validate_summary="injected")
    baseline = _run_artifact("M11_RUN_12_BASELINE.json")
    reconciliation = _artifact(DESIGN_DIR / RUN_RECONCILIATION)
    replay = service.run_gate(
        baseline=baseline,
        residual={"targets": payload["residual"]["targets"], "preflight": {
            "targets": _run_artifact("M11_RUN_12_BATCH04_PREFLIGHT.json")["targets"]}},
        frontier={"targets": payload["frontier"]["targets"],
                  "blocked_targets": _artifact(
                      DESIGN_DIR / BATCH_17_SCOPE_FILE)["blocked_target_ids"]},
        reconciliation=reconciliation,
        projections={"overlay": _artifact(DESIGN_DIR / "M11_OVERLAY_V2.json"),
                     "readiness": _artifact(DESIGN_DIR / "M11_READINESS_V2.json"),
                     "ledger": _artifact(DESIGN_DIR / "M11_REPAIR_SUBTYPE_LEDGER.json")},
        backlog=_artifact(DESIGN_DIR / "M11_PRODUCTION_BACKLOG.json"),
        contracts=[_run_artifact("M11_RUN_12_BATCH_04_ACCEPTANCE_CONTRACT.json"),
                   _run_artifact("M11_RUN_12_BATCH_17_ACCEPTANCE_CONTRACT.json")],
        evidence={"pytest": {"status": "PASS", "summary": "injected"},
                  "validate_project": {"status": "PASS", "summary": "injected"}})
    assert replay["status"] == "PASS"
    assert replay["failed_checks"] == []
