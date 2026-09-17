"""M11-RUN-11：Production Execution 回归（Auto Safe Frontier through Batch 16）。"""

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
from novelforge.story_engine.m11_run11 import (
    BATCH_16,
    BATCH_16_SCOPE_COMPAT_FILE,
    BATCH_16_SCOPE_FILE,
    M11Run11Service,
    RUN_ID,
    RUN_RECONCILIATION,
)

from m11_phase_history import closed, assert_m12_projection
ROOT = Path(".").resolve()
DESIGN_DIR = ROOT / "workspace/wasteland_001_exports/repair_adoption_v1"
REPAIR_DIR = ROOT / "workspace/wasteland_001_exports/repair_v1"
RUN_DIR = DESIGN_DIR / "m11_run_11"
EXECUTED_BATCHES = {f"REPAIR_BATCH_{index:02d}" for index in range(1, 17)}


@pytest.fixture(scope="module")
def run11():
    service = M11Run11Service(ROOT)
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


def _remaining_unexecuted(readiness: dict) -> list[dict]:
    return [row for row in readiness["batches"]
            if row["batch_id"] not in EXECUTED_BATCHES]


# ---------------------------------------------------------------- scope freeze
def test_scope_frozen_before_execution(run11) -> None:
    service, payload = run11
    scope = _run_artifact("M11_RUN_11_EXECUTION_SCOPE.json")
    assert scope["frozen"] is True and scope["run_id"] == RUN_ID
    assert scope["contract_digest"] == "67559aa55442d69e"
    assert scope["gate_digest"] == "e1eab4c33ae75b01"
    assert payload["execution_scope"]["frozen"] is True
    baseline = _run_artifact("M11_RUN_11_BASELINE.json")
    assert baseline["frozen_contract"]["contract"] == "67559aa55442d69e"
    assert baseline["frozen_contract"]["repair_gate"] == "e1eab4c33ae75b01"
    assert baseline["primary_buckets"] == {
        "resolved_repaired": 146, "resolved_no_repair_required": 53,
        "evidence_ready": 3, "manual_required": 12,
        "content_design_required": 53, "author_decision": 2, "pending": 103}
    assert baseline["batch_execution_status_counts"] == {"BLOCKED": 15, "READY": 2}
    assert payload["reconciliation"]["promoted"] + sum(
        payload["reconciliation"]["dynamic_downgrade_counts"].values()) == 23


def test_planning_commit_did_not_mutate_production_state(run11) -> None:
    """planning-only commit 后，RUN-11 baseline 必须仍是 RUN-10 收口状态。"""

    service, payload = run11
    baseline = _run_artifact("M11_RUN_11_BASELINE.json")
    assert baseline["git"]["commit"].startswith("9a3951c")
    assert baseline["truth_digests"]["canon"] == FROZEN_SOURCE_DIGESTS["canon"]
    assert baseline["truth_digests"]["historical_foundation"] == FROZEN_FOUNDATION_DIGESTS
    # RUN-10 收口数值原样进入 RUN-11 baseline（planning commit 未改 production state）
    assert baseline["primary_buckets"]["resolved_repaired"] == 146
    assert baseline["primary_buckets"]["pending"] == 103
    assert baseline["batch_status"]["REPAIR_BATCH_16"]["ready"] == 23
    # freeze-then-execute：baseline 记录的是执行前 overlay digest，执行后必须已变化
    assert baseline["frozen_contract"]["overlay_v2"] != service.frozen_digests()[
        "overlay_v2"]


# ---------------------------------------------------------------- Batch 16
def test_batch16_baseline_recomputed_and_closure(run11) -> None:
    service, payload = run11
    scope = _artifact(DESIGN_DIR / BATCH_16_SCOPE_FILE)
    assert scope["frozen"] is True and scope["batch_id"] == BATCH_16
    assert len(scope["ready_target_ids"]) == 23
    assert scope["blocked_target_ids"] == []
    closure = scope["dependency_closure"]
    assert closure["readiness_ready_count"] == 23
    assert closure["readiness_blocked_count"] == 0
    assert closure["continuity_ready_count"] == 18  # [M11-CLOSURE] 已由后续 run terminal
    # [M11-CLOSURE] blocker 分类在 M11 final closure 后全部归零（scope 本身仍 frozen）
    assert closure["classification"]["content_design_blocked"] == 0
    assert closure["classification"]["entity_blocked"] == 0
    assert closure["classification"]["manual_blocked"] == 0
    assert closure["classification"]["author_blocked"] == 0
    assert closure["classification"]["confirmed_binding_blocked"] == 0
    assert closure["classification"]["architecture_exception"] == 0
    assert (DESIGN_DIR / BATCH_16_SCOPE_COMPAT_FILE).is_file()
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
    assert payload["frontier"]["scope"] == {"ready": 23, "blocked": 0}
    assert payload["frontier"]["scope_frozen"] is True


def test_only_baseline_ready_executed(run11) -> None:
    service, payload = run11
    scope = _run_artifact("M11_RUN_11_EXECUTION_SCOPE.json")
    ready = {str(item) for item in scope["batch_16_ready_targets"]}
    reconciliation = _artifact(DESIGN_DIR / RUN_RECONCILIATION)
    executed = {row["chapter_id"] for row in reconciliation["records"]}
    assert executed == ready
    execution = _run_artifact("M11_RUN_11_BATCH16_EXECUTION.json")
    assert {str(item) for item in execution["targets"]} == ready
    assert execution["execution_kind"] == "AUTO_SAFE_FRONTIER"
    assert payload["gate"]["checks"]["only_ready_target_executed"] is True


def test_blocked_targets_untouched(run11) -> None:
    service, payload = run11
    scope = _run_artifact("M11_RUN_11_EXECUTION_SCOPE.json")
    assert scope["batch_04_blocked_targets"] and scope["batch_16_blocked_targets"] == []
    reconciliation = _artifact(DESIGN_DIR / RUN_RECONCILIATION)
    executed = {row["chapter_id"] for row in reconciliation["records"]}
    readiness = _artifact(DESIGN_DIR / "M11_READINESS_V2.json")
    frozen_blocked: set[str] = set()
    for row in readiness["batches"]:
        if row["batch_id"] == "REPAIR_BATCH_16":
            continue
        frozen_blocked |= {str(item) for item in row["blocked_target_ids"]}
    assert executed & frozen_blocked == set()
    execution = _run_artifact("M11_RUN_11_BATCH16_EXECUTION.json")
    assert execution["blocked_targets"] == []
    assert payload["gate"]["checks"]["blocked_target_untouched"] is True
    assert payload["gate"]["blocked_target_ids"] == []


def test_batch17_not_entered(run11) -> None:
    service, payload = run11
    gate = _run_artifact("M11_RUN_11_GATE.json")
    assert gate["checks"]["batch17_not_entered"] is True
    reconciliation = _artifact(DESIGN_DIR / RUN_RECONCILIATION)
    executed = {row["chapter_id"] for row in reconciliation["records"]}
    readiness = _artifact(DESIGN_DIR / "M11_READINESS_V2.json")
    b17 = _batch(readiness, "REPAIR_BATCH_17")
    assert not executed & (set(b17["ready_target_ids"])
                           | set(b17["blocked_target_ids"])
                           | set(b17["resolved_target_ids"]))
    assert payload["batch_17_executed"] is False


def test_runtime_newly_unlocked_deferred(run11) -> None:
    """Batch 17 的 READY 是 RUN-11 后新投影，必须 deferred 到 RUN-12（不得被 RUN-11 触碰）。"""

    service, payload = run11
    readiness = _artifact(DESIGN_DIR / "M11_READINESS_V2.json")
    b17 = _batch(readiness, "REPAIR_BATCH_17")
    reconciliation = _artifact(DESIGN_DIR / RUN_RECONCILIATION)
    executed = {row["chapter_id"] for row in reconciliation["records"]}
    b17_targets = {str(item) for item in b17["ready_target_ids"] + b17["blocked_target_ids"]
                   + b17["resolved_target_ids"]}
    assert len(b17_targets) == b17["mutable_target_count"] == 13
    assert not executed & b17_targets


def test_batch16_execution_and_promotion(run11) -> None:
    service, payload = run11
    execution = _run_artifact("M11_RUN_11_BATCH16_EXECUTION.json")
    assert execution["verified"] == 18
    assert execution["human_review"] == 5
    assert execution["promotion_mode"] == "partial"
    assert execution["gate_status"] == "PASS"
    diff = execution["diff"]
    assert diff["semantic_elements_added"] == 0
    assert diff["semantic_elements_removed"] == 0
    assert diff["confirmed_facts_changed"] == 0
    assert diff["read_only_chapters_changed"] == 0
    reconciliation = _artifact(DESIGN_DIR / RUN_RECONCILIATION)
    assert reconciliation["record_count"] == 23
    assert reconciliation["promoted"] == 18
    assert reconciliation["promoted_evidence_only"] == 13
    assert reconciliation["promoted_no_repair_required"] == 5
    assert reconciliation["promoted_field_rebind"] == 0
    assert reconciliation["records_modified"] is False
    assert payload["frontier"]["acceptance"] == "PASS"


def test_dynamic_downgrade_honesty(run11) -> None:
    service, payload = run11
    reconciliation = _artifact(DESIGN_DIR / RUN_RECONCILIATION)
    counts = reconciliation["dynamic_downgrade_counts"]
    assert counts["CONTENT_DESIGN_REQUIRED"] == 3      # ch516 / ch518 / ch519
    assert counts["MANUAL_REQUIRED"] == 2              # ch545 / ch546
    assert counts["EVIDENCE_READY"] == 0
    assert counts["AUTHOR_DECISION_REQUIRED"] == 0
    assert counts["BLOCKED_CONFIRMED_BINDING_CONFLICT"] == 0
    assert counts["ARCHITECTURE_EXCEPTION_REQUIRED"] == 0
    manual = {row["legacy_label"]: row for row in reconciliation["records"]
              if row["new_resolution_status"] == "MANUAL_REQUIRED"}
    assert set(manual) == {"ch545", "ch546"}
    assert manual["ch546"]["repair_class"] == "FIELD_REBIND"
    assert manual["ch545"]["repair_class"] == "EVIDENCE_ONLY"
    assert "HISTORICAL_FULL_IR_PARTIAL" in manual["ch545"]["reason"]
    for row in manual.values():
        assert row["execution_decision"] == "MANUAL" and row["repaired_ref"] == ""
    content = {row["legacy_label"]: row for row in reconciliation["records"]
               if row["new_resolution_status"] == "CONTENT_DESIGN_REQUIRED"}
    assert set(content) == {"ch516", "ch518", "ch519"}
    for row in content.values():
        assert row["repair_class"] == "SEMANTIC_ADDITION_REQUIRED"
        assert row["design_item_id"] == f"CDQ_RUN11_{row['legacy_label']}"
        assert row["repaired_ref"] == ""
    downgrades = sum(value for key, value in counts.items() if key != "EVIDENCE_READY")
    assert reconciliation["promoted"] == 18 and downgrades == 5
    assert reconciliation["promoted"] / downgrades >= 2.0
    assert payload["frontier"]["verified"] == 18


def test_event_added_cannot_safe_auto(run11) -> None:
    service, payload = run11
    reconciliation = _artifact(DESIGN_DIR / RUN_RECONCILIATION)
    promoted = [row for row in reconciliation["records"]
                if row["new_resolution_status"] in ("RESOLVED_REPAIRED",
                                                    "RESOLVED_NO_REPAIR_REQUIRED")]
    allowed_ops = {"REBIND_EVIDENCE", "MARK_NOT_APPLICABLE", "RECLASSIFY_FUNCTION",
                   "REBIND_STATE_REFERENCE"}
    assert all(op in allowed_ops for row in promoted for op in row["patch_ops"])
    gate = _run_artifact("M11_RUN_11_GATE.json")
    assert gate["checks"]["no_new_historical_event_promoted"] is True
    assert payload["gate"]["new_historical_events"] == 0


def test_unsafe_field_rebind_cannot_promote(run11) -> None:
    """ch546 是第 5 个自然 FIELD_REBIND（decision = MANUAL）→ 不 promote。"""

    service, payload = run11
    reconciliation = _artifact(DESIGN_DIR / RUN_RECONCILIATION)
    assert reconciliation["promoted_field_rebind"] == 0
    ledger = _artifact(DESIGN_DIR / "M11_REPAIR_SUBTYPE_LEDGER.json")
    assert ledger["resolved_subtype_counts"].get("repaired_field_rebind", 0) == 0
    assert payload["field_rebind_natural_end_to_end"] is False
    assert not (DESIGN_DIR / "PRODUCTION_CAPABILITY_EVIDENCE.json").is_file()
    capability = _artifact(DESIGN_DIR / "p15p/P15_CAPABILITY_ACCEPTANCE_MATRIX.json")
    verdicts = {row["capability"]: row["verdict"] for row in capability["capabilities"]}
    assert verdicts["Field Rebind"] == "NOT_PROVEN"
    field_rebind_total = 0
    for index in range(5, 12):
        records = _artifact(DESIGN_DIR / f"M11_RUN_{index:02d}_RECONCILIATION.json"
                            )["records"]
        for row in records:
            if row["repair_class"] == "FIELD_REBIND":
                field_rebind_total += 1
                assert row["new_resolution_status"] != "RESOLVED_REPAIRED"
    # ch324（RUN-05）/ ch425 / ch445（RUN-08）/ ch498（RUN-10）/ ch546（RUN-11）
    assert field_rebind_total == 5


def test_safe_field_rebind_requires_all_frozen_gates(run11) -> None:
    service, payload = run11
    manifest = _artifact(DESIGN_DIR / "M11_REPAIR_SYSTEM_CONTRACT_V1.json")
    assert "FIELD_REBIND" in str(manifest).upper()
    reconciliation = _artifact(DESIGN_DIR / RUN_RECONCILIATION)
    promoted = [row for row in reconciliation["records"]
                if row["new_resolution_status"] in ("RESOLVED_REPAIRED",
                                                    "RESOLVED_NO_REPAIR_REQUIRED")]
    assert not [row for row in promoted if row["repair_class"] == "FIELD_REBIND"]
    # 本轮没有 safe FIELD_REBIND 样本：门禁未通过时必须保持 downgrade
    ch546 = next(row for row in reconciliation["records"]
                 if row["legacy_label"] == "ch546")
    assert ch546["execution_decision"] == "MANUAL"
    assert ch546["new_resolution_status"] == "MANUAL_REQUIRED"
    assert payload["gate"]["checks"]["no_new_repair_taxonomy"] is True


# ---------------------------------------------------------------- production CDQ
def test_production_cdq_registration_and_origin(run11) -> None:
    service, payload = run11
    reconciliation = _artifact(DESIGN_DIR / RUN_RECONCILIATION)
    registered = reconciliation["content_design_items_registered"]
    assert len(registered) == 3
    assert {row["design_item_id"] for row in registered} == {
        "CDQ_RUN11_ch516", "CDQ_RUN11_ch518", "CDQ_RUN11_ch519"}
    for row in registered:
        assert row["origin"] == "M11_RUN_11_DYNAMIC_DOWNGRADE"
        assert str(row["design_item_id"]).startswith("CDQ_RUN11_")
        assert row["status"] == "PENDING_DESIGN"
    queue2 = _artifact(DESIGN_DIR / "M11_CONTENT_DESIGN_QUEUE_V2.json")
    items = {row["design_item_id"]: row for row in queue2["items"]}
    for item_id in ("CDQ_RUN11_ch516", "CDQ_RUN11_ch518", "CDQ_RUN11_ch519"):
        assert items[item_id]["origin"] == "M11_RUN_11 dynamic downgrade"
    # production_run_item = true（P15 micro machinery 不得认领）
    ContentRewritePolicyService(ROOT).reclassify()
    reclassification = _artifact(
        DESIGN_DIR / "p15n" / "CONTENT_REPAIR_RECLASSIFICATION.json")
    rows = {row["legacy_label"]: row for row in reclassification["rows"]
            if row.get("production_run_item")}
    queue_status = {str(row.get("legacy_label")): str(row.get("status"))
                    for row in _artifact(
                        DESIGN_DIR / "M11_CONTENT_DESIGN_QUEUE_V3.json")["requirements"]}
    for label in ("ch516", "ch518", "ch519"):
        # [M11-CLOSURE] production CDQ item 已 terminal（从 active reclassification 视图移出）；
        # 仍必须在 production CDQ queue 中可追溯
        assert str(queue_status.get(label, "")).startswith("RESOLVED"), label
        assert rows.get(label, {}).get("micro_scale_candidate", False) is False
    assert payload["reconciliation"]["content_design_items_registered"] == 3


def test_content_design_queue_id_reconciliation(run11) -> None:
    """§7：V2 lifecycle 必须按 ID reconciliation（不只是比较数字）。"""

    service, _payload = run11
    audit = _run_artifact("CONTENT_DESIGN_QUEUE_LIFECYCLE_AUDIT.json")
    assert audit["before_run"] == "M11_RUN_10"
    assert audit["added_runs"] == ["M11_RUN_11"]
    assert audit["before_item_count"] == 67
    assert audit["added_item_count"] == 3
    # RUN-11 时点 window = 70；后续 RUN 新增进入 later_ids，after 继续增长
    assert audit["window_after_item_count"] == 70
    assert audit["after_item_count"] >= 70 and audit["later_item_count"] >= 0
    assert audit["added_ids"] == ["CDQ_RUN11_ch516", "CDQ_RUN11_ch518",
                                  "CDQ_RUN11_ch519"]
    assert audit["removed_or_superseded_ids"] == []
    assert audit["duplicate_design_item_ids"] == []
    assert audit["verdict"] == "NO_DATA_LOSS"
    queue2 = _artifact(DESIGN_DIR / "M11_CONTENT_DESIGN_QUEUE_V2.json")
    ids = [row["design_item_id"] for row in queue2["items"]]
    assert len(ids) == len(set(ids)) >= 70
    assert len(ids) == audit["after_item_count"]
    assert set(audit["added_ids"]) <= set(ids)
    registered: list[str] = []
    for index in range(2, 12):
        path = DESIGN_DIR / f"M11_RUN_{index:02d}_RECONCILIATION.json"
        if not path.is_file():
            continue
        for row in _artifact(path).get("content_design_items_registered") or []:
            registered.append(str(row["design_item_id"]))
    assert registered and set(registered) <= set(ids)
    assert len(registered) == len(set(registered))        # duplicate ownership = 0


def test_active_cdq_matches_overlay_and_no_orphans(run11) -> None:
    service, payload = run11
    queue3 = _artifact(DESIGN_DIR / "M11_CONTENT_DESIGN_QUEUE_V3.json")
    active = [row for row in queue3["requirements"] if row["status"] == "ACTIVE"]
    overlay = _artifact(DESIGN_DIR / "M11_OVERLAY_V2.json")
    queue_recon = _artifact(DESIGN_DIR / "p15n" /
                            "CONTENT_DESIGN_QUEUE_RECONCILIATION.json")
    assert len(active) == queue3["active_count"] == 0  # [M11-CLOSURE]
    assert len(active) == overlay["content_design_required"] == closed(56, 0)
    assert queue_recon["active_requirements"] == overlay["content_design_required"]
    assert queue_recon["snapshot_items"] >= 70
    assert queue_recon["orphan_requirements"] == []
    assert queue_recon["targets_without_requirement"] == []
    integration = service.readiness.integrate_dynamic_design_items()
    assert integration["new_item_count"] == 0
    assert integration["merged_item_count"] >= 70


# ---------------------------------------------------------------- P15 isolation
def test_p15_executor_isolation_and_regression(run11) -> None:
    service, payload = run11
    invariant = _run_artifact(f"{P15_ISOLATION_INVARIANT_ID}.json")
    assert invariant["status"] == "PASS"
    assert invariant["static_scan_pass"] is True
    assert invariant["runtime_isolation_pass"] is True
    assert invariant["production_item_ownership_pass"] is True
    assert invariant["production_item_count"] >= 27
    assert not any(invariant["static_scan_findings"].values())
    assert not invariant["live_p15_artifacts_for_production_chapters"]
    gate = _run_artifact("M11_RUN_11_GATE.json")
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
def test_overlay_and_372_conservation(run11) -> None:
    service, payload = run11
    overlay = _artifact(DESIGN_DIR / "M11_OVERLAY_V2.json")
    assert overlay["conservation"] == {"primary_total": TARGET_COUNT,
                                       "target_count": TARGET_COUNT, "exact": True}
    assert list(overlay["primary_resolution_status_counts"]) == list(PRIMARY_BUCKETS)
    assert sum(overlay["primary_resolution_status_counts"].values()) == TARGET_COUNT
    # RUN-11 时点 = 217 / 159 / 58 / 134；后续 RUN 会推进，只保留下界与守恒
    assert overlay["resolved_total"] >= 217
    assert overlay["repaired"] >= 159
    assert overlay["no_repair_required"] >= 58
    assert overlay["repaired_evidence_only"] >= 134
    assert overlay["repaired_field_rebind"] == 0
    assert overlay["repaired_micro_semantic"] == 21
    assert overlay["repaired_confirmed_override"] == 4
    assert overlay["evidence_ready"] >= 0
    assert overlay["content_design_required"] == 0  # [M11-CLOSURE] 已 terminal
    assert overlay["manual_required"] == 0  # [M11-CLOSURE] 已 terminal
    assert overlay["author_decision"] == 0  # [M11-CLOSURE] author lane 已 terminal
    assert overlay["pending"] <= 80
    assert payload["overlay_conservation"]["exact"] is True


def test_subtype_ledger_consistency(run11) -> None:
    service, _payload = run11
    overlay = _artifact(DESIGN_DIR / "M11_OVERLAY_V2.json")
    ledger = _artifact(DESIGN_DIR / "M11_REPAIR_SUBTYPE_LEDGER.json")
    counts = ledger["resolved_subtype_counts"]
    assert len(ledger["ledger"]) == overlay["resolved_total"] >= 217
    assert sum(counts.values()) == overlay["resolved_total"]
    assert counts["repaired_evidence_only"] >= 134
    assert counts["no_repair_required"] >= 58
    assert counts["repaired_micro_semantic"] == 21
    assert counts["repaired_confirmed_override"] == 4
    assert counts.get("repaired_field_rebind", 0) == 0


def test_readiness_recompute(run11) -> None:
    service, payload = run11
    readiness = _artifact(DESIGN_DIR / "M11_READINESS_V2.json")
    assert len(readiness["batches"]) == 17
    assert readiness["completion_status_counts"] == {"COMPLETE": 17}  # [M11-CLOSURE] 372/372 terminal
    counts = readiness["execution_status_counts"]
    assert set(counts) <= {"READY", "PARTIAL_READY", "BLOCKED", "NO_WORK", "COMPLETE"}
    assert sum(counts.values()) == 17
    b16 = _batch(readiness, BATCH_16)
    assert (b16["completion_status"], b16["execution_status"]) == closed(
        ("IN_PROGRESS", "BLOCKED"), ("COMPLETE", "COMPLETE"))
    assert len(b16["resolved_target_ids"]) == closed(19, 24)
    assert b16["ready_target_ids"] == []
    assert len(b16["blocked_target_ids"]) == closed(5, 0)
    assert b16["blocker_counts"] == closed(
        {"BLOCKED_CONTENT_DESIGN": 3, "BLOCKED_MANUAL_REPAIR": 2}, {})
    assert payload["readiness"]["execution_status_counts"] == counts
    for row in readiness["batches"]:
        assert row["completion_status"] in ("NOT_STARTED", "IN_PROGRESS", "COMPLETE",
                                           "HUMAN_REVIEW")
        assert row["execution_status"] in ("READY", "PARTIAL_READY", "BLOCKED",
                                           "NO_WORK", "COMPLETE")
        assert not set(row["ready_target_ids"]) & set(row["blocked_target_ids"])


def test_batch17_latest_frontier_metric(run11) -> None:
    """§11/§17：RUN-11 后诊断 Batch 17；后续 RUN 会推进这些数字。"""

    service, _payload = run11
    readiness = _artifact(DESIGN_DIR / "M11_READINESS_V2.json")
    pending = _remaining_unexecuted(readiness)
    assert [row["batch_id"] for row in pending] == ["REPAIR_BATCH_17"]
    b17 = pending[0]
    assert b17["mutable_target_count"] == 13
    combined = (len(b17["ready_target_ids"]) + len(b17["blocked_target_ids"])
                + len(b17["resolved_target_ids"]))
    assert combined == 13
    # RUN-11 自身结果（timepoint）冻结在本轮 artifacts
    execution = _run_artifact("M11_RUN_11_BATCH16_EXECUTION.json")
    assert execution["verified"] == 18 and execution["human_review"] == 5


def test_backlog_update(run11) -> None:
    service, payload = run11
    backlog = _artifact(DESIGN_DIR / "M11_PRODUCTION_BACKLOG.json")
    assert set(backlog["lane_counts"]) == set(BACKLOG_LANES)
    assert all(count >= 1 for count in backlog["lane_counts"].values())
    assert backlog["item_count"] == sum(backlog["lane_counts"].values()) >= 71
    assert backlog["last_run"] == RUN_ID
    assert backlog["lane_counts"]["LANE_MANUAL"] >= 15
    assert backlog["lane_counts"]["LANE_CONTENT_REWRITE"] >= 29
    items = {row["item_id"]: row for row in backlog["items"]}
    assert items["BL_AUTO_B16"]["status"] == "DONE"
    assert items["BL_AUTO_B16"]["completed_by_run"] == RUN_ID
    assert set(items["BL_AUTO_B16"]["completed_targets"]) >= set(
        row["chapter_id"] for row in _artifact(DESIGN_DIR / RUN_RECONCILIATION
                                               )["records"])
    assert items["BL_MANUAL_ch545"]["lane"] == "LANE_MANUAL"
    assert items["BL_MANUAL_ch546"]["lane"] == "LANE_MANUAL"
    assert items["BL_CONTENT_DESIGN_ch516"]["lane"] == "LANE_CONTENT_REWRITE"
    assert set(payload["backlog"]["done_item_ids"]) >= {"BL_AUTO_B16"}
    assert payload["backlog"]["item_count"] == backlog["item_count"]


def test_no_author_auto_resolution(run11) -> None:
    service, payload = run11
    inventory = _artifact(DESIGN_DIR / "AUTHOR_ACTION_INVENTORY.json")
    assert inventory["policy_selection"]["auto_selected"] == ""
    assert inventory["policy_selection"]["author_selected"] == ""
    assert inventory["auto_resolved"] == 0
    assert payload["author_policy_selected"] is False
    assert payload["author_decisions_resolved"] == 0
    reconciliation = _artifact(DESIGN_DIR / RUN_RECONCILIATION)
    assert not [row for row in reconciliation["records"]
                if row["new_resolution_status"] == "AUTHOR_DECISION_REQUIRED"]


def test_m12_remains_false(run11) -> None:
    service, payload = run11
    criteria = _artifact(DESIGN_DIR / "p15p" / "M12_ENTRY_CRITERIA.json")
    assert criteria["m12_entry_allowed"] is False
    assert criteria["satisfied_count"] == len(criteria["satisfied_criteria"])  # [M11-CLOSURE]
    assert criteria["unsatisfied_count"] == len(criteria["unsatisfied_criteria"])
    assert criteria["blocking_count"] == len(criteria["blocking_criteria"])
    assert payload["m12"]["entry_allowed"] is False
    assert (payload["m12"]["satisfied_count"] + payload["m12"]["unsatisfied_count"]
            == payload["m12"]["criteria_count"])
    assert_m12_projection(payload["m12"], criteria)
    gate = _run_artifact("M11_RUN_11_GATE.json")
    assert gate["checks"]["m12_not_entered"] is True


def test_contract_gate_truth_and_foundation_digests_unchanged(run11) -> None:
    service, payload = run11
    baseline = _run_artifact("M11_RUN_11_BASELINE.json")
    gate = _run_artifact("M11_RUN_11_GATE.json")
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


def test_blocker_layer_planning_invariants_referenced(run11) -> None:
    """§15：roadmap 必须保持 blocker invariants；analysis artifacts 允许存在。"""

    plan = (ROOT / "docs/M11_BLOCKER_RESOLUTION_PLAN.md").read_text(encoding="utf-8")
    assert "DERIVED_BLOCKER_COUNT_IS_NOT_EXECUTION_ITEM_COUNT" in plan
    assert "ROOT_BLOCKER_FIRST" in plan
    assert "AUTHOR_DECISION_IS_BATCHED" in plan
    master = (ROOT / "docs/NOVELFORGE_PRODUCT_V2_MASTER_PLAN.md").read_text(
        encoding="utf-8")
    assert "M11_BLOCKER_RESOLUTION_PLAN.md" in master
    assert not (DESIGN_DIR / "m11_blocker_00").exists()
    baseline_path = DESIGN_DIR / "M11_BLOCKER_BASELINE.json"
    if baseline_path.is_file():
        status = json.loads(baseline_path.read_text(encoding="utf-8"))[
            "component_status"]
        for name in ("ContentDesignResolver", "EntityResolutionEngine",
                     "ManualRepairWorkbench", "AuthorDecisionConsole"):
            assert status[name] == "PLANNED_ONLY"


def test_run11_gate_pass_with_injected_evidence(run11) -> None:
    service, payload = run11
    gate = _run_artifact("M11_RUN_11_GATE.json")
    assert set(gate["failed_checks"]) <= {"full_pytest_pass", "validate_project_pass"}
    for key, value in gate["checks"].items():
        if key not in ("full_pytest_pass", "validate_project_pass"):
            assert value is True, key
    service.record_test_evidence(pytest_summary="injected", pytest_passed=1,
                                 validate_summary="injected")
    baseline = _run_artifact("M11_RUN_11_BASELINE.json")
    reconciliation = _artifact(DESIGN_DIR / RUN_RECONCILIATION)
    replay = service.run_gate(
        baseline=baseline,
        residual={"targets": payload["residual"]["targets"], "preflight": {
            "targets": _run_artifact("M11_RUN_11_BATCH04_PREFLIGHT.json")["targets"]}},
        frontier={"targets": payload["frontier"]["targets"],
                  "blocked_targets": _artifact(
                      DESIGN_DIR / BATCH_16_SCOPE_FILE)["blocked_target_ids"]},
        reconciliation=reconciliation,
        projections={"overlay": _artifact(DESIGN_DIR / "M11_OVERLAY_V2.json"),
                     "readiness": _artifact(DESIGN_DIR / "M11_READINESS_V2.json"),
                     "ledger": _artifact(DESIGN_DIR / "M11_REPAIR_SUBTYPE_LEDGER.json")},
        backlog=_artifact(DESIGN_DIR / "M11_PRODUCTION_BACKLOG.json"),
        contracts=[_run_artifact("M11_RUN_11_BATCH_04_ACCEPTANCE_CONTRACT.json"),
                   _run_artifact("M11_RUN_11_BATCH_16_ACCEPTANCE_CONTRACT.json")],
        evidence={"pytest": {"status": "PASS", "summary": "injected"},
                  "validate_project": {"status": "PASS", "summary": "injected"}})
    assert replay["status"] == "PASS"
    assert replay["failed_checks"] == []
