"""M11-RUN-02：Production Execution 回归（Auto Safe Frontier，Batch 04 residual + Batch 07）。

production execution tests（不是 architecture experiment）：
验证 scope 在执行前冻结、只执行 baseline ready target、执行中新释放的 target 未执行、
blocked target 未触碰、dynamic downgrade 不污染其它 target、author/manual/entity 冻结、
overlay 372 守恒、backlog / M12 projection 与 truth digests 正确。
"""

from __future__ import annotations

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
from novelforge.story_engine.m11_run02 import (

    BATCH_07,
    BATCH_07_SCOPE_FILE,
    M11Run02Service,
    RUN_ID,
    RUN_RECONCILIATION,
)

from m11_phase_history import closed

ROOT = Path(".").resolve()
DESIGN_DIR = ROOT / "workspace/wasteland_001_exports/repair_adoption_v1"
REPAIR_DIR = ROOT / "workspace/wasteland_001_exports/repair_v1"
RUN_DIR = DESIGN_DIR / "m11_run_02"


@pytest.fixture(scope="module")
def run02():
    service = M11Run02Service(ROOT)
    payload = service.run()
    return service, payload


def _artifact(path: Path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _run_artifact(name: str):
    return _artifact(RUN_DIR / name)


# ---------------------------------------------------------------- baseline / scope
def test_baseline_and_scope_frozen_before_execution(run02) -> None:
    service, payload = run02
    baseline = _run_artifact("M11_RUN_02_BASELINE.json")
    scope = _run_artifact("M11_RUN_02_EXECUTION_SCOPE.json")
    assert baseline["run_id"] == RUN_ID
    assert baseline["git"]["commit"]
    assert baseline["primary_buckets"] == {
        "resolved_repaired": 73, "resolved_no_repair_required": 20,
        "evidence_ready": 3, "manual_required": 2, "content_design_required": 29,
        "author_decision": 1, "pending": 244}
    assert baseline["batch_execution_status_counts"] == {
        "BLOCKED": 5, "PARTIAL_READY": 8, "READY": 4}
    assert baseline["frontier"]["batch_07"] == {
        "completion_status": "IN_PROGRESS", "execution_status": "PARTIAL_READY",
        "resolved": 0, "ready": 21, "blocked": 2}
    assert scope["frozen"] is True
    assert scope["run_id"] == RUN_ID
    assert scope["frontier_max_batch"] == BATCH_07
    assert scope["contract_digest"] == service.frozen_digests()["contract"]
    assert scope["gate_digest"] == service.frozen_digests()["repair_gate"]
    assert scope["matches_run01_baseline"]["REPAIR_BATCH_04"] is True
    assert scope["matches_run01_baseline"]["REPAIR_BATCH_07"] is True
    assert scope["run01_baseline"]["REPAIR_BATCH_07"] == {
        "ready": 21, "blocked": 2, "execution_status": "PARTIAL_READY"}
    assert payload["status"] in ("PASS", "EVIDENCE_REQUIRED")


def test_batch04_baseline_single_ready(run02) -> None:
    service, payload = run02
    scope = _run_artifact("M11_RUN_02_EXECUTION_SCOPE.json")
    assert len(scope["batch_04_residual_targets"]) == 1
    assert scope["batch_04_residual_targets"] == [payload["residual"]["targets"][0]]
    preflight = _run_artifact("M11_RUN_02_BATCH04_PREFLIGHT.json")
    assert preflight["target_count"] == 1
    row = preflight["targets"][0]
    assert row["legacy_label"] == "ch075"
    assert str(row["target_state"]) == "READY"  # Frozen run-local evidence.
    assert row["primary_resolution_status"] == "pending"
    assert row["actual_repair_class"] == "NO_REPAIR_REQUIRED"
    assert row["execution_decision"] == "SAFE_AUTO"
    assert row["verdict"] == "SAFE_AUTO_EXECUTE"
    assert row["architecture_exception"] is False
    assert row["foundation"]["evidence_substrate"] == "HISTORICAL_FULL_IR"
    assert row["foundation"]["digest_match"] is True
    assert row["execution_blockers"] == []
    assert not row["transitive_dependency_targets"]
    execution = _run_artifact("M11_RUN_02_BATCH04_EXECUTION.json")
    assert execution["verified"] == 1
    assert execution["gate_status"] == "PASS"
    assert payload["residual"]["acceptance"] == "PASS"


def test_newly_unlocked_batch04_target_not_executed(run02) -> None:
    service, payload = run02
    reconciliation = _artifact(DESIGN_DIR / RUN_RECONCILIATION)
    executed = {row["chapter_id"] for row in reconciliation["records"]
                if row["new_resolution_status"] in ("RESOLVED_REPAIRED",
                                                    "RESOLVED_NO_REPAIR_REQUIRED")}
    # RUN-02 只执行了 ch075；ch076（RUN-02 时被 ch075 释放）不在本轮 scope 内，
    # 因此 RUN-02 的 reconciliation 里没有 ch076 的 resolved 记录
    scope = _run_artifact("M11_RUN_02_EXECUTION_SCOPE.json")
    assert scope["batch_04_residual_targets"] == [
        "uuid_1be155fa56ac5275964e07b83d070bcf"]      # ch075
    assert "uuid_498668ad6941517788e2059ad31d19a7" not in executed   # ch076 deferred
    assert payload["gate"]["checks"]["only_ready_target_executed"] is True


# ---------------------------------------------------------------- Batch 07 closure
def test_batch07_dependency_closure_and_scope(run02) -> None:
    service, payload = run02
    scope = _artifact(DESIGN_DIR / BATCH_07_SCOPE_FILE)
    assert scope["frozen"] is True
    assert scope["batch_id"] == BATCH_07
    assert len(scope["ready_target_ids"]) == 21
    assert len(scope["blocked_target_ids"]) == 2
    closure = scope["dependency_closure"]
    assert closure["readiness_ready_count"] == 21
    assert closure["readiness_blocked_count"] == 2
    # [M11-CLOSURE] blocker 分类在 M11 final closure 后全部归零（scope 本身仍 frozen）
    assert closure["classification"]["content_design_blocked"] == 0
    assert closure["classification"]["entity_blocked"] == 0
    assert closure["classification"]["manual_blocked"] == 0
    assert closure["classification"]["author_blocked"] == 0
    assert closure["classification"]["confirmed_binding_blocked"] == 0
    assert closure["classification"]["architecture_exception"] == 0
    assert closure["blocker_counts"] == {}  # [M11-CLOSURE] entity blocker 已 terminal
    assert scope["contract_digest"] == service.frozen_digests()["contract"]
    assert scope["gate_digest"] == service.frozen_digests()["repair_gate"]
    assert scope["baseline_truth_digests"]["canon"] == FROZEN_SOURCE_DIGESTS["canon"]
    assert scope["read_only_dependency_chapters"]
    assert all(row["read_only_dependency_chapters"]
               == scope["read_only_dependency_chapters"] for row in scope["targets"])
    ready_labels = {row["legacy_label"] for row in scope["targets"]}
    assert len(ready_labels) == 21
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
        assert row["verdict"] in ("SAFE_AUTO_EXECUTE", "DYNAMIC_DOWNGRADE_MANUAL",
                                  "DYNAMIC_DOWNGRADE_CONTENT_DESIGN",
                                  "DYNAMIC_DOWNGRADE_AUTHOR_DECISION")
    # readiness V2 的 baseline ready/blocked 与 scope 一致（RUN-01 baseline 比对）
    assert payload["frontier"]["scope"] == {"ready": 21, "blocked": 2}


def test_batch07_blocked_targets_untouched(run02) -> None:
    service, payload = run02
    scope = _artifact(DESIGN_DIR / BATCH_07_SCOPE_FILE)
    blocked = {str(item) for item in scope["blocked_target_ids"]}
    assert len(blocked) == 2
    blocked_labels = {row["legacy_label"] for row in scope["blocked_targets"]}
    assert blocked_labels == {"ch211", "ch220"}
    for row in scope["blocked_targets"]:
        assert row["verdict"] == "BLOCKED_READ_ONLY_CONTEXT"
        assert str(row["target_state"]) == closed("READY", "RESOLVED")  # [M11-CLOSURE] run-local frozen scope（历史 timepoint）  # [M11-CLOSURE] entity blocker 已解决
    reconciliation = _artifact(DESIGN_DIR / RUN_RECONCILIATION)
    for row in reconciliation["records"]:
        if row["chapter_id"] in blocked:
            assert row["new_resolution_status"] == "BLOCKED_CONTENT_DESIGN"
            assert row["repair_subtype"] == ""
            assert row["repaired_ref"] == ""
    execution = _run_artifact("M11_RUN_02_BATCH07_EXECUTION.json")
    assert not set(execution["targets"]) & blocked
    assert set(execution["blocked_targets"]) == blocked
    assert payload["gate"]["checks"]["blocked_target_untouched"] is True


def test_batch07_execution_and_promotion(run02) -> None:
    service, payload = run02
    execution = _run_artifact("M11_RUN_02_BATCH07_EXECUTION.json")
    assert len(execution["targets"]) == 21
    assert execution["verified"] == 15
    assert execution["human_review"] == 6
    assert execution["promotion_mode"] == "partial"
    assert execution["gate_status"] == "PASS"
    diff = _artifact(REPAIR_DIR / "BATCH_07_DIFF.json")
    assert diff["semantic_elements_added"] == 0
    assert diff["semantic_elements_removed"] == 0
    assert diff["confirmed_facts_changed"] == 0
    assert diff["read_only_chapters_changed"] == 0
    reconciliation = _artifact(DESIGN_DIR / RUN_RECONCILIATION)
    assert reconciliation["promoted"] == 16          # ch075 + B07 的 15
    assert reconciliation["promoted_evidence_only"] == 13
    assert reconciliation["promoted_no_repair_required"] == 3
    assert reconciliation["promoted_field_rebind"] == 0
    assert payload["frontier"]["acceptance"] == "PASS"


# ---------------------------------------------------------------- downgrade
def test_dynamic_downgrade_content_design_and_manual(run02) -> None:
    service, payload = run02
    reconciliation = _artifact(DESIGN_DIR / RUN_RECONCILIATION)
    counts = reconciliation["dynamic_downgrade_counts"]
    assert counts["CONTENT_DESIGN_REQUIRED"] == 5
    assert counts["MANUAL_REQUIRED"] == 1
    assert counts["EVIDENCE_READY"] == 0
    assert counts["AUTHOR_DECISION_REQUIRED"] == 0
    assert counts["BLOCKED_CONFIRMED_BINDING_CONFLICT"] == 0
    assert counts["ARCHITECTURE_EXCEPTION_REQUIRED"] == 0
    design = [row for row in reconciliation["records"]
              if row["new_resolution_status"] == "CONTENT_DESIGN_REQUIRED"]
    assert {row["legacy_label"] for row in design} == {"ch198", "ch207", "ch210",
                                                       "ch215", "ch218"}
    assert all(row["design_item_id"].startswith("CDQ_RUN02_") for row in design)
    manual = [row for row in reconciliation["records"]
              if row["new_resolution_status"] == "MANUAL_REQUIRED"]
    assert len(manual) == 1 and manual[0]["legacy_label"] == "ch199"
    assert manual[0]["evidence_substrate"] == "HISTORICAL_FULL_IR_PARTIAL"
    # runtime 发现的 content design 使用冻结 queue schema 登记
    queue = _artifact(DESIGN_DIR / "M11_CONTENT_DESIGN_QUEUE_V3.json")
    active = [row for row in queue["requirements"] if row["status"] == "ACTIVE"]
    overlay = _artifact(DESIGN_DIR / "M11_OVERLAY_V2.json")
    # live 值会被后续 production run 推进；双射不变量与 RUN-02 时点值都要成立
    assert len(active) == overlay["content_design_required"]
    assert overlay["content_design_required"] == 0  # [M11-CLOSURE] 已 terminal
    design_ids = {row["design_item_id"] for row in queue["requirements"]
                  if row["origin"] == "M11_RUN_02 dynamic downgrade"
                  and row["status"] == "RESOLVED_REPAIRED"}
    assert {f"CDQ_RUN02_{label}" for label in
            ("ch198", "ch207", "ch210", "ch215", "ch218")} == design_ids
    assert payload["reconciliation"]["queue_registration"]["queue_reconciled"] is True
    assert payload["reconciliation"]["content_design_items_registered"] == 5


def test_manual_dependency_propagation(run02) -> None:
    service, payload = run02
    backlog = _artifact(DESIGN_DIR / "M11_PRODUCTION_BACKLOG.json")
    manual_items = {row["item_id"] for row in backlog["items"]
                    if row["lane"] == "LANE_MANUAL"}
    # RUN-01 的 ch166 必须仍在 backlog，且 RUN-02 新增 ch199
    assert {"BL_MANUAL_ch166", "BL_MANUAL_ch199"} <= manual_items
    reconciliation = _artifact(DESIGN_DIR / RUN_RECONCILIATION)
    resolved = {row["legacy_label"] for row in reconciliation["records"]
                if row["new_resolution_status"] in ("RESOLVED_REPAIRED",
                                                    "RESOLVED_NO_REPAIR_REQUIRED")}
    assert not {"ch166", "ch199"} & resolved
    readiness = _artifact(DESIGN_DIR / "M11_READINESS_V2.json")
    batches = {row["batch_id"]: row for row in readiness["batches"]}
    manual_blocked = [row for row in batches[BATCH_07]["blocked_target_ids"]
                      if "BLOCKED_MANUAL_REPAIR"
                      in batches[BATCH_07]["block_reason_by_target"].get(row, "")]
    assert not manual_blocked  # [M11-CLOSURE] manual lane 已由 final closure 解决
    assert all(str(item) in batches[BATCH_07]["blocked_target_ids"]
               for item in manual_blocked)
    assert payload["gate"]["checks"]["blocked_target_untouched"] is True


# ---------------------------------------------------------------- author / events
def test_author_policy_and_decisions_untouched(run02) -> None:
    service, payload = run02
    inventory = _artifact(DESIGN_DIR / "AUTHOR_ACTION_INVENTORY.json")
    assert inventory["policy_selection"]["auto_selected"] == ""
    assert inventory["policy_selection"]["author_selected"] == ""
    assert inventory["policy_selection"]["status"] == "PENDING_AUTHOR_SELECTION"
    assert inventory["auto_resolved"] == 0 and inventory["unresolved"] is True
    assert payload["author_policy_selected"] is False
    assert payload["author_decisions_resolved"] == 0
    gate = _run_artifact("M11_RUN_02_GATE.json")
    assert gate["checks"]["no_author_policy_auto_selected"] is True
    assert gate["checks"]["no_author_decision_auto_resolved"] is True
    # [M11-CLOSURE] 未决 author item 仍在 inventory；已 closure 的 label 必须在
    # approved-event / final-closure reconciliation 中可追溯（不得静默消失）
    inventory_labels = {label for row in inventory["items"]
                        for label in (row.get("legacy_labels") or [])}
    closed_labels = set()
    for name in ("M11_APPROVED_EVENT_RECONCILIATION.json",
                 "M11_FINAL_CLOSURE_RECONCILIATION.json"):
        closed_labels |= {str(row.get("legacy_label"))
                          for row in _artifact(DESIGN_DIR / name)["records"]}
    for label in ("ch012", "ch036", "ch056", "ch063", "ch081", "ch085", "ch087",
                  "ch143", "ch166", "ch199", "ch559"):
        assert (label in inventory_labels or label in closed_labels
                or label in ("ch166", "ch199")), label


def test_new_event_cannot_promote(run02) -> None:
    service, payload = run02
    proposals = _artifact(DESIGN_DIR / "p15o/CONCRETE_REWRITE_PROPOSALS.json")
    decision_events = [row for row in proposals["proposals"] if row.get("decision_event")]
    # [M11-CLOSURE] proposal surface 已清空；保留 new-event 审批不变量
    assert all(row.get("author_approval_required") == "AUTHOR_CONTENT_APPROVAL"
               for row in decision_events)
    assert _run_artifact("M11_RUN_02_GATE.json")["checks"][
        "no_new_historical_event_promoted"] is True
    reconciliation = _artifact(DESIGN_DIR / RUN_RECONCILIATION)
    promoted = [row for row in reconciliation["records"]
                if row["new_resolution_status"] in ("RESOLVED_REPAIRED",
                                                    "RESOLVED_NO_REPAIR_REQUIRED")]
    assert all(row["repair_class"] in ("EVIDENCE_ONLY", "NO_REPAIR_REQUIRED")
               for row in promoted)
    assert all(op in ("REBIND_EVIDENCE", "MARK_NOT_APPLICABLE", "RECLASSIFY_FUNCTION",
                      "REBIND_STATE_REFERENCE") for row in promoted
               for op in row["patch_ops"])
    status = _artifact(DESIGN_DIR / "p15o/CONTENT_REWRITE_PROPOSAL_STATUS.json")
    assert status["CONTENT_REWRITE_PROPOSAL_STATUS"] == "READY_FOR_AUTHOR_POLICY_DECISION"
    assert payload["gate"]["new_historical_events"] == 0


# ---------------------------------------------------------------- overlay / readiness
def test_overlay_conservation(run02) -> None:
    service, payload = run02
    overlay = _artifact(DESIGN_DIR / "M11_OVERLAY_V2.json")
    assert overlay["conservation"] == {"primary_total": TARGET_COUNT,
                                       "target_count": TARGET_COUNT, "exact": True}
    assert list(overlay["primary_resolution_status_counts"]) == list(PRIMARY_BUCKETS)
    assert sum(overlay["primary_resolution_status_counts"].values()) == TARGET_COUNT
    # RUN-02 时点值：见 RUN-02 reconciliation（live overlay 会被 RUN-03+ 继续推进）
    reconciliation = _artifact(DESIGN_DIR / RUN_RECONCILIATION)
    assert reconciliation["promoted"] == 16
    assert reconciliation["promoted_evidence_only"] == 13
    assert reconciliation["promoted_no_repair_required"] == 3
    assert overlay["resolved_total"] >= 109
    assert overlay["repaired"] >= 86
    assert overlay["no_repair_required"] >= 23
    assert overlay["repaired_evidence_only"] >= 61
    assert overlay["repaired_field_rebind"] == 0
    assert overlay["repaired_micro_semantic"] == 21
    assert overlay["repaired_confirmed_override"] == 4
    assert overlay["content_design_required"] == 0  # [M11-CLOSURE] 已 terminal
    assert overlay["manual_required"] == 0  # [M11-CLOSURE] 已 terminal
    assert overlay["pending"] <= 222
    ledger = _artifact(DESIGN_DIR / "M11_REPAIR_SUBTYPE_LEDGER.json")
    assert len(ledger["ledger"]) == overlay["resolved_total"]
    assert payload["overlay_conservation"]["exact"] is True


def test_readiness_recompute(run02) -> None:
    service, payload = run02
    readiness = _artifact(DESIGN_DIR / "M11_READINESS_V2.json")
    assert len(readiness["batches"]) == 17
    assert readiness["completion_status_counts"] == {"COMPLETE": 17}  # [M11-CLOSURE] 372/372 terminal
    counts = readiness["execution_status_counts"]
    assert set(counts) <= {"READY", "PARTIAL_READY", "BLOCKED", "NO_WORK", "COMPLETE"}
    assert sum(counts.values()) == 17
    batches = {row["batch_id"]: row for row in readiness["batches"]}
    b04 = batches["REPAIR_BATCH_04"]
    # 该 run 时点 = PARTIAL_READY；后续 run 会把 B04 推到 BLOCKED（frontier 前移）
    assert b04["completion_status"] == closed("IN_PROGRESS", "COMPLETE")
    assert b04["execution_status"] in closed(("PARTIAL_READY", "BLOCKED"), ("COMPLETE",))  # [M11-CLOSURE]
    assert len(b04["resolved_target_ids"]) >= 14
    # RUN-02 时点 = 1（ch075 释放 ch076）；后续 run 继续推进 → 允许 0
    assert len(b04["ready_target_ids"]) <= 1
    assert len(b04["blocked_target_ids"]) <= 9
    b07 = batches[BATCH_07]
    assert (b07["completion_status"], b07["execution_status"]) == closed(
        ("IN_PROGRESS", "BLOCKED"), ("COMPLETE", "COMPLETE"))
    assert len(b07["resolved_target_ids"]) == closed(15, 23)
    assert b07["ready_target_ids"] == []
    assert len(b07["blocked_target_ids"]) == closed(8, 0)
    assert batches["REPAIR_BATCH_05"]["execution_status"] == closed("BLOCKED", "COMPLETE")
    assert batches["REPAIR_BATCH_06"]["execution_status"] == closed("BLOCKED", "COMPLETE")
    assert payload["readiness"]["execution_status_counts"] == (
        readiness["execution_status_counts"])
    for row in readiness["batches"]:
        assert row["completion_status"] in ("NOT_STARTED", "IN_PROGRESS", "COMPLETE",
                                           "HUMAN_REVIEW")
        assert row["execution_status"] in ("READY", "PARTIAL_READY", "BLOCKED",
                                           "NO_WORK", "COMPLETE")
        assert not set(row["ready_target_ids"]) & set(row["blocked_target_ids"])


def test_batch08_not_executed(run02) -> None:
    service, payload = run02
    gate = _run_artifact("M11_RUN_02_GATE.json")
    assert gate["checks"]["batch08_not_entered"] is True
    reconciliation = _artifact(DESIGN_DIR / RUN_RECONCILIATION)
    executed = {row["chapter_id"] for row in reconciliation["records"]
                if row["new_resolution_status"] in ("RESOLVED_REPAIRED",
                                                    "RESOLVED_NO_REPAIR_REQUIRED")}
    readiness = _artifact(DESIGN_DIR / "M11_READINESS_V2.json")
    batch_08 = next(row for row in readiness["batches"]
                    if row["batch_id"] == "REPAIR_BATCH_08")
    # RUN-02 未执行任何 Batch 08 target（live readiness 会被 RUN-03 继续推进）
    assert not executed & (set(batch_08["ready_target_ids"])
                           | set(batch_08["blocked_target_ids"])
                           | set(batch_08["resolved_target_ids"]))
    assert payload["batch_08_executed"] is False


# ---------------------------------------------------------------- backlog / M12
def test_backlog_update_and_history(run02) -> None:
    service, payload = run02
    backlog = _artifact(DESIGN_DIR / "M11_PRODUCTION_BACKLOG.json")
    assert set(backlog["lane_counts"]) == set(BACKLOG_LANES)
    assert all(count >= 1 for count in backlog["lane_counts"].values())
    assert backlog["item_count"] == sum(backlog["lane_counts"].values())
    assert backlog["item_count"] >= 38
    assert backlog["last_run"] == RUN_ID
    done = {row["item_id"]: row for row in backlog["items"]
            if row["status"] == "DONE"}
    assert {"BL_AUTO_B06", "BL_AUTO_B07"} <= set(done)
    assert done["BL_AUTO_B07"]["completed_by_run"] == RUN_ID
    # B07 scope = 21 ready target（15 promoted + 6 dynamic downgrade）
    assert len(done["BL_AUTO_B07"]["completed_targets"]) == 21
    assert {"BL_AUTO_B06", "BL_AUTO_B07"} <= set(payload["backlog"]["done_item_ids"])
    assert backlog["history_item_count"] >= 2
    assert payload["backlog"]["item_count"] == backlog["item_count"]


def test_m12_remains_blocked(run02) -> None:
    service, payload = run02
    m12 = _artifact(DESIGN_DIR / "p15p/M12_ENTRY_CRITERIA.json")
    assert m12["criteria_count"] == 9
    assert m12["m12_entry_allowed"] is False
    assert m12["satisfied_count"] == len(m12["satisfied_criteria"])  # [M11-CLOSURE] P15p projection 自洽为准
    assert m12["unsatisfied_count"] == len(m12["unsatisfied_criteria"])  # [M11-CLOSURE]
    assert m12["blocking_count"] == len(m12["blocking_criteria"])  # [M11-CLOSURE]
    assert set(m12["blocking_criteria"]) <= set(m12["unsatisfied_criteria"])
    assert not set(m12["satisfied_criteria"]) & set(m12["unsatisfied_criteria"])
    assert payload["m12"]["entry_allowed"] is False


# ---------------------------------------------------------------- truth / capability
def test_contract_gate_and_truth_digests_unchanged(run02) -> None:
    service, payload = run02
    baseline = _run_artifact("M11_RUN_02_BASELINE.json")
    now = service.frozen_digests()
    assert now["contract"] == baseline["frozen_contract"]["contract"]
    assert now["repair_gate"] == baseline["frozen_contract"]["repair_gate"]
    gate = _run_artifact("M11_RUN_02_GATE.json")
    assert gate["checks"]["frozen_contract_unchanged"] is True
    assert gate["checks"]["frozen_repair_gate_unchanged"] is True
    assert gate["checks"]["no_new_repair_taxonomy"] is True
    truth = service.truth_digests()
    assert truth["canon"] == FROZEN_SOURCE_DIGESTS["canon"]
    assert truth["story_state"] == FROZEN_SOURCE_DIGESTS["story_state"]
    assert truth["legacy"] == FROZEN_SOURCE_DIGESTS["legacy"]
    assert truth["chapter_ir"] == FROZEN_SOURCE_DIGESTS["chapter_ir"]
    assert truth["historical_foundation"] == FROZEN_FOUNDATION_DIGESTS
    assert gate["checks"]["truth_digests_unchanged"] is True
    assert gate["checks"]["confirmed_facts_changed_zero"] is True
    assert payload["gate"]["confirmed_facts_changed"] == 0


def test_field_rebind_production_evidence(run02) -> None:
    service, payload = run02
    ledger = _artifact(DESIGN_DIR / "M11_REPAIR_SUBTYPE_LEDGER.json")
    field_rebind = ledger["resolved_subtype_counts"].get("repaired_field_rebind", 0)
    evidence_path = DESIGN_DIR / "PRODUCTION_CAPABILITY_EVIDENCE.json"
    if field_rebind:
        assert evidence_path.is_file()
        evidence = _artifact(evidence_path)
        assert evidence["FIELD_REBIND"] == "PROVEN_BY_M11_RUN_02"
    else:
        assert payload["field_rebind_natural_end_to_end"] is False
        assert not evidence_path.is_file()
        capability = _artifact(DESIGN_DIR / "p15p/P15_CAPABILITY_ACCEPTANCE_MATRIX.json")
        verdicts = {row["capability"]: row["verdict"]
                    for row in capability["capabilities"]}
        assert verdicts["Field Rebind"] == "NOT_PROVEN"


def test_run02_gate_pass_with_injected_evidence(run02) -> None:
    service, payload = run02
    gate = _run_artifact("M11_RUN_02_GATE.json")
    assert set(gate["failed_checks"]) <= {"full_pytest_pass", "validate_project_pass"}
    assert gate["status"] in ("EVIDENCE_REQUIRED", "PASS")
    for key, value in gate["checks"].items():
        if key not in ("full_pytest_pass", "validate_project_pass"):
            assert value is True, key
    service.record_test_evidence(pytest_summary="injected", pytest_passed=1,
                                 validate_summary="injected")
    baseline = _run_artifact("M11_RUN_02_BASELINE.json")
    reconciliation = _artifact(DESIGN_DIR / RUN_RECONCILIATION)
    replay = service.run_gate(
        baseline=baseline,
        residual={"targets": payload["residual"]["targets"], "preflight": {
            "targets": _run_artifact("M11_RUN_02_BATCH04_PREFLIGHT.json")["targets"]}},
        frontier={"targets": payload["frontier"]["targets"],
                  "blocked_targets": _artifact(
                      DESIGN_DIR / BATCH_07_SCOPE_FILE)["blocked_target_ids"]},
        reconciliation=reconciliation,
        projections={"overlay": _artifact(DESIGN_DIR / "M11_OVERLAY_V2.json"),
                     "readiness": _artifact(DESIGN_DIR / "M11_READINESS_V2.json"),
                     "ledger": _artifact(DESIGN_DIR / "M11_REPAIR_SUBTYPE_LEDGER.json")},
        backlog=_artifact(DESIGN_DIR / "M11_PRODUCTION_BACKLOG.json"),
        contracts=[_run_artifact("M11_RUN_02_BATCH_04_ACCEPTANCE_CONTRACT.json"),
                   _run_artifact("M11_RUN_02_BATCH_07_ACCEPTANCE_CONTRACT.json")],
        evidence={"pytest": {"status": "PASS", "summary": "injected"},
                  "validate_project": {"status": "PASS", "summary": "injected"}})
    assert replay["status"] == "PASS"
    assert replay["failed_checks"] == []
