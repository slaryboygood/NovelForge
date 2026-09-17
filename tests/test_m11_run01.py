"""M11-RUN-01：Production Execution 回归（Auto Safe Frontier，Batch 04 residual + Batch 06）。

这些是 production execution tests（不是 architecture experiment）：
验证本轮只执行 ready target、blocked target 未触碰、frozen contract / gate 未变、
truth digests 未变、overlay 372 守恒、backlog / M12 projection 正确。
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from novelforge.story_engine.m11_p15p import (
    FROZEN_FOUNDATION_DIGESTS,
    FROZEN_SOURCE_DIGESTS,
    BACKLOG_LANES,
    TARGET_COUNT,
)
from novelforge.story_engine.m11_readiness import PRIMARY_BUCKETS
from novelforge.story_engine.m11_run01 import (

    ARCHITECTURE_EXCEPTION,
    BATCH_04,
    BATCH_06,
    BATCH_06_SCOPE_FILE,
    M11Run01Service,
    RUN_ID,
    RUN_RECONCILIATION,
)

from m11_phase_history import closed

ROOT = Path(".").resolve()
DESIGN_DIR = ROOT / "workspace/wasteland_001_exports/repair_adoption_v1"
REPAIR_DIR = ROOT / "workspace/wasteland_001_exports/repair_v1"
RUN_DIR = DESIGN_DIR / "m11_run_01"


@pytest.fixture(scope="module")
def run01():
    service = M11Run01Service(ROOT)
    payload = service.run()
    return service, payload


def _artifact(path: Path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _run_artifact(name: str):
    return _artifact(RUN_DIR / name)


# ---------------------------------------------------------------- baseline
def test_baseline_and_frozen_digests(run01) -> None:
    _service, payload = run01
    baseline = _run_artifact("M11_RUN_01_BASELINE.json")
    assert baseline["run_id"] == RUN_ID
    assert baseline["git"]["commit"]
    assert baseline["git"]["branch"]
    assert baseline["frozen_contract"]["contract"]
    assert baseline["frozen_contract"]["repair_gate"]
    assert baseline["frozen_contract"]["overlay_v2"]
    assert baseline["frozen_contract"]["readiness_v2"]
    assert baseline["primary_buckets"] == {
        "resolved_repaired": 62, "resolved_no_repair_required": 15,
        "evidence_ready": 3, "manual_required": 1, "content_design_required": 29,
        "author_decision": 1, "pending": 261}
    assert baseline["conservation"]["exact"] is True
    assert len(baseline["batch_status"]) == 17
    assert baseline["batch_execution_status_counts"] == {
        "BLOCKED": 4, "PARTIAL_READY": 9, "READY": 4}
    assert baseline["frontier"]["batch_06"]["ready"] == 16
    assert payload["status"] in ("PASS", "EVIDENCE_REQUIRED")


def test_frozen_contract_and_gate_digest_unchanged(run01) -> None:
    service, payload = run01
    baseline = _run_artifact("M11_RUN_01_BASELINE.json")
    now = service.frozen_digests()
    assert now["contract"] == baseline["frozen_contract"]["contract"]
    assert now["repair_gate"] == baseline["frozen_contract"]["repair_gate"]
    gate = _run_artifact("M11_RUN_01_GATE.json")
    assert gate["checks"]["frozen_contract_unchanged"] is True
    assert gate["checks"]["frozen_repair_gate_unchanged"] is True
    assert gate["checks"]["no_new_repair_taxonomy"] is True
    contract = _artifact(DESIGN_DIR / "M11_REPAIR_SYSTEM_CONTRACT_V1.json")
    assert len(contract["primary_repair_classes"]) == 13
    assert contract["repair_evidence_substrate"]["digest_mismatch"] == "BLOCK"


# ---------------------------------------------------------------- Batch 04
def test_batch04_residual_scope_and_preflight(run01) -> None:
    service, payload = run01
    scope = _run_artifact("M11_RUN_01_EXECUTION_SCOPE.json")
    assert scope["frozen"] is True
    assert len(scope["batch_04_residual_targets"]) == 1
    assert scope["batch_04_residual_targets"] == [payload["residual"]["targets"][0]]
    assert scope["matches_p15p_baseline"]["REPAIR_BATCH_04"] is True
    preflight = _run_artifact("M11_RUN_01_BATCH04_PREFLIGHT.json")
    assert preflight["target_count"] == 1
    row = preflight["targets"][0]
    assert row["legacy_label"] == "ch074"
    assert str(row["target_state"]) == "READY"  # Frozen run-local evidence.
    assert row["primary_resolution_status"] == "pending"
    assert row["actual_repair_class"] == "NO_REPAIR_REQUIRED"
    assert row["execution_decision"] == "SAFE_AUTO"
    assert row["verdict"] == "SAFE_AUTO_EXECUTE"
    assert row["architecture_exception"] is False
    assert row["foundation"]["evidence_substrate"] == "HISTORICAL_FULL_IR"
    assert row["foundation"]["digest_match"] is True
    assert row["dependency_closure_safe"] is True
    assert not row["transitive_dependency_targets"]
    assert not row["content_design_dependencies"]
    assert not row["manual_dependencies"]
    assert not row["confirmed_binding_dependencies"]
    execution = _run_artifact("M11_RUN_01_BATCH04_EXECUTION.json")
    assert execution["verified"] == 1
    assert execution["gate_status"] == "PASS"
    assert payload["residual"]["acceptance"] == "PASS"


# ---------------------------------------------------------------- Batch 06
def test_batch06_dependency_closure_and_scope(run01) -> None:
    service, payload = run01
    scope = _artifact(DESIGN_DIR / BATCH_06_SCOPE_FILE)
    assert scope["frozen"] is True
    assert scope["batch_id"] == BATCH_06
    assert len(scope["ready_target_ids"]) == 16
    assert len(scope["blocked_target_ids"]) == 5
    closure = scope["dependency_closure"]
    assert closure["continuity_ready_count"] == 15  # [M11-CLOSURE] 1 个 target 已由后续 run terminal
    assert closure["continuity_blocked_count"] == closed(5, 0)
    assert closure["readiness_ready_count"] == 16
    assert closure["readiness_blocked_count"] == 5
    assert closure["classification"]["content_design_blocked"] == closed(5, 0)
    assert closure["classification"]["entity_blocked"] == 0
    assert closure["classification"]["safe_executable"] == 16
    assert scope["contract_digest"] == service.frozen_digests()["contract"]
    assert scope["gate_digest"] == service.frozen_digests()["repair_gate"]
    assert scope["baseline_truth_digests"]["canon"] == FROZEN_SOURCE_DIGESTS["canon"]
    # Batch 06 的 read-only dependency chapters（上一 batch 的 continuity 上下文，只读）
    assert len(scope["read_only_dependency_chapters"]) == 14
    assert all(row["read_only_dependency_chapters"]
               == scope["read_only_dependency_chapters"] for row in scope["targets"])
    frozen_run_scope = _run_artifact("M11_RUN_01_EXECUTION_SCOPE.json")
    assert frozen_run_scope["matches_p15p_baseline"]["REPAIR_BATCH_06"] is True
    assert frozen_run_scope["p15p_baseline"]["REPAIR_BATCH_06"] == {
        "ready": 16, "blocked": 5, "execution_status": "PARTIAL_READY"}
    blocked_labels = {row["legacy_label"] for row in scope["blocked_targets"]}
    assert blocked_labels == {"ch145", "ch149", "ch150", "ch151", "ch152"}
    verdicts = {row["legacy_label"]: row["verdict"] for row in scope["targets"]}
    assert set(verdicts) == {row["legacy_label"] for row in scope["targets"]}
    assert all(value in ("SAFE_AUTO_EXECUTE", "DYNAMIC_DOWNGRADE_MANUAL",
                         "DYNAMIC_DOWNGRADE_CONTENT_DESIGN",
                         "DYNAMIC_DOWNGRADE_AUTHOR_DECISION",
                         ARCHITECTURE_EXCEPTION)
               for value in verdicts.values())
    assert payload["frontier"]["scope"] == {"ready": 16, "blocked": 5}


def test_batch06_execution_counts(run01) -> None:
    service, payload = run01
    execution = _run_artifact("M11_RUN_01_BATCH06_EXECUTION.json")
    assert len(execution["targets"]) == 16
    assert execution["verified"] == 15
    assert execution["human_review"] == 1
    assert execution["promotion_mode"] == "partial"
    assert execution["gate_status"] == "PASS"
    diff = _artifact(REPAIR_DIR / "BATCH_06_DIFF.json")
    assert diff["semantic_elements_added"] == 0
    assert diff["semantic_elements_removed"] == 0
    assert diff["confirmed_facts_changed"] == 0
    assert diff["read_only_chapters_changed"] == 0
    assert diff["evidence_only_repairs"] == 15
    reconciliation = _artifact(DESIGN_DIR / RUN_RECONCILIATION)
    assert reconciliation["promoted"] == 16
    assert reconciliation["promoted_evidence_only"] == 11
    assert reconciliation["promoted_no_repair_required"] == 5
    assert reconciliation["promoted_field_rebind"] == 0
    assert payload["frontier"]["acceptance"] == "PASS"


# ---------------------------------------------------------------- blocked / downgrade
def test_blocked_targets_untouched(run01) -> None:
    service, payload = run01
    execution = _run_artifact("M11_RUN_01_BATCH06_EXECUTION.json")
    blocked = set(execution["blocked_targets"])
    assert len(blocked) == 5
    reconciliation = _artifact(DESIGN_DIR / RUN_RECONCILIATION)
    blocked_records = [row for row in reconciliation["records"]
                       if row["chapter_id"] in blocked]
    assert blocked_records
    for row in blocked_records:
        assert row["new_resolution_status"] == "BLOCKED_CONTENT_DESIGN"
        assert row["repair_subtype"] == ""
        assert row["patch_ops"] == []
        assert row["repaired_ref"] == ""
    assert not set(execution["targets"]) & blocked
    gate = _run_artifact("M11_RUN_01_GATE.json")
    assert gate["checks"]["blocked_target_untouched"] is True
    assert gate["checks"]["only_ready_target_executed"] is True


def test_dynamic_downgrade_manual(run01) -> None:
    service, payload = run01
    reconciliation = _artifact(DESIGN_DIR / RUN_RECONCILIATION)
    manual = [row for row in reconciliation["records"]
              if row["new_resolution_status"] == "MANUAL_REQUIRED"]
    assert len(manual) == 1
    assert manual[0]["legacy_label"] == "ch166"
    assert manual[0]["batch_id"] == BATCH_06
    assert manual[0]["evidence_substrate"] == "HISTORICAL_FULL_IR_PARTIAL"
    assert manual[0]["repair_class"] == "EVIDENCE_ONLY"
    assert manual[0]["execution_decision"] == "MANUAL"
    counts = reconciliation["dynamic_downgrade_counts"]
    assert counts["MANUAL_REQUIRED"] == 1
    assert counts["CONTENT_DESIGN_REQUIRED"] == 0
    assert counts["AUTHOR_DECISION_REQUIRED"] == 0
    assert counts["BLOCKED_CONFIRMED_BINDING_CONFLICT"] == 0
    assert counts[ARCHITECTURE_EXCEPTION] == 0
    backlog = _artifact(DESIGN_DIR / "M11_PRODUCTION_BACKLOG.json")
    manual_item = next(row for row in backlog["items"]
                       if row["item_id"] == "BL_MANUAL_ch166")
    assert manual_item["lane"] == "LANE_MANUAL"
    assert manual_item["status"] == "DONE"  # [M11-CLOSURE] final closure 已关闭该 item
    assert payload["reconciliation"]["dynamic_downgrade_counts"]["MANUAL_REQUIRED"] == 1


def test_downgrade_status_mapping() -> None:
    """frozen contract 必须能表达所有 runtime downgrade（不新造 repair class）。"""

    def candidate(*, klass: str, substrate: str, decision: str = "MANUAL", status: str
                  = "human_review") -> SimpleNamespace:
        return SimpleNamespace(
            chapter_id="uuid_test", legacy_label="chTEST", status=status,
            evidence_substrate=substrate,
            proposed_patch=[SimpleNamespace(op="REBIND_EVIDENCE")],
            refinement=SimpleNamespace(actual_repair_class=klass,
                                       execution_decision=decision))

    assert M11Run01Service.downgrade_status(candidate(
        klass="SEMANTIC_ADDITION_REQUIRED", substrate="HISTORICAL_FULL_IR"))[0] == (
            "CONTENT_DESIGN_REQUIRED")
    assert M11Run01Service.downgrade_status(candidate(
        klass="HUMAN_DECISION_REQUIRED", substrate="HISTORICAL_FULL_IR"))[0] == (
            "AUTHOR_DECISION_REQUIRED")
    assert M11Run01Service.downgrade_status(candidate(
        klass="EVIDENCE_ONLY", substrate="HISTORICAL_FULL_IR_PARTIAL"))[0] == (
            "MANUAL_REQUIRED")
    assert M11Run01Service.downgrade_status(candidate(
        klass="EVIDENCE_ONLY", substrate="HISTORICAL_FULL_IR", status="blocked"))[0] == (
            "BLOCKED_CONTENT_DESIGN")
    assert M11Run01Service.repair_subtype(candidate(
        klass="NO_REPAIR_REQUIRED", substrate="HISTORICAL_FULL_IR")) == (
            "no_repair_required")
    assert M11Run01Service.repair_subtype(candidate(
        klass="EVIDENCE_ONLY", substrate="HISTORICAL_FULL_IR")) == (
            "repaired_evidence_only")


# ---------------------------------------------------------------- author / manual / entity
def test_author_policy_and_decisions_untouched(run01) -> None:
    service, payload = run01
    inventory = _artifact(DESIGN_DIR / "AUTHOR_ACTION_INVENTORY.json")
    assert inventory["policy_selection"]["auto_selected"] == ""
    assert inventory["policy_selection"]["author_selected"] == ""
    assert inventory["policy_selection"]["status"] == "PENDING_AUTHOR_SELECTION"
    assert inventory["auto_resolved"] == 0
    assert inventory["unresolved"] is True
    assert payload["author_policy_selected"] is False
    assert payload["author_decisions_resolved"] == 0
    gate = _run_artifact("M11_RUN_01_GATE.json")
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
                  "ch088", "ch559"):
        assert label in inventory_labels or label in closed_labels, label


def test_event_added_proposals_cannot_promote(run01) -> None:
    service, payload = run01
    proposals = _artifact(DESIGN_DIR / "p15o/CONCRETE_REWRITE_PROPOSALS.json")
    decision_events = [row for row in proposals["proposals"] if row.get("decision_event")]
    # [M11-CLOSURE] p15o proposal surface 已随 targets terminal 清空；保留 new-event 审批不变量
    assert all(row.get("author_approval_required") == "AUTHOR_CONTENT_APPROVAL"
               for row in decision_events)
    assert _run_artifact("M11_RUN_01_GATE.json")["checks"][
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
    assert payload["gate"]["confirmed_facts_changed"] == 0


def test_manual_and_entity_untouched(run01) -> None:
    service, payload = run01
    inventory = _artifact(DESIGN_DIR / "p15p/M11_ENTITY_MANUAL_INVENTORY.json")
    assert inventory["entity"]["cluster_count"] == 47
    assert inventory["entity"]["context_resolvable_cluster_count"] == 13
    assert inventory["entity"]["entity_truth_modified"] is False
    assert {row["legacy_label"] for row in inventory["entity"]["specific_pending_items"]} == {
        "ch093", "ch120"}
    reconciliation = _artifact(DESIGN_DIR / RUN_RECONCILIATION)
    resolved_labels = {row["legacy_label"] for row in reconciliation["records"]
                       if row["new_resolution_status"] in (
                           "RESOLVED_REPAIRED", "RESOLVED_NO_REPAIR_REQUIRED")}
    assert "ch063" not in resolved_labels
    assert "ch143" not in resolved_labels
    assert "ch093" not in resolved_labels
    assert "ch120" not in resolved_labels
    overlay = _artifact(DESIGN_DIR / "M11_OVERLAY_V2.json")
    assert overlay["evidence_ready"] == 0  # [M11-CLOSURE] evidence lane 已 terminal


# ---------------------------------------------------------------- overlay / readiness
def test_overlay_372_exact_conservation(run01) -> None:
    service, payload = run01
    overlay = _artifact(DESIGN_DIR / "M11_OVERLAY_V2.json")
    assert overlay["conservation"] == {"primary_total": TARGET_COUNT,
                                       "target_count": TARGET_COUNT, "exact": True}
    assert list(overlay["primary_resolution_status_counts"]) == list(PRIMARY_BUCKETS)
    assert sum(overlay["primary_resolution_status_counts"].values()) == TARGET_COUNT
    # RUN-01 的 scope 与 reconciliation 计数是稳定的（frozen scope 决定）；
    # live overlay / readiness 会被后续 production run（M11-RUN-02 …）继续推进。
    summary = _run_artifact("M11_RUN_01_SUMMARY.json")
    assert summary["residual"]["targets"] == ["uuid_8c5b092052be57eb85bd8d6705cf071b"]
    assert summary["frontier"]["scope"] == {"ready": 16, "blocked": 5}
    assert summary["reconciliation"]["promoted"] == 16
    assert summary["reconciliation"]["promoted_evidence_only"] == 11
    assert summary["reconciliation"]["promoted_no_repair_required"] == 5
    # live 值只增不减（后续 run 只会推进 resolved / content design）
    assert overlay["resolved_total"] >= 93
    assert overlay["repaired_field_rebind"] == 0
    assert overlay["repaired_micro_semantic"] == 21
    assert overlay["repaired_confirmed_override"] == 4
    assert overlay["manual_required"] == 0  # [M11-CLOSURE] manual lane 已 terminal
    assert overlay["content_design_required"] == 0  # [M11-CLOSURE] 已 terminal
    assert overlay["pending"] <= 244
    ledger = _artifact(DESIGN_DIR / "M11_REPAIR_SUBTYPE_LEDGER.json")
    assert len(ledger["ledger"]) == overlay["resolved_total"]
    assert payload["overlay_conservation"]["exact"] is True


def test_readiness_recompute_after_run(run01) -> None:
    service, payload = run01
    readiness = _artifact(DESIGN_DIR / "M11_READINESS_V2.json")
    assert len(readiness["batches"]) == 17
    assert readiness["completion_status_counts"] == {"COMPLETE": 17}  # [M11-CLOSURE] 372/372 terminal
    counts = readiness["execution_status_counts"]
    assert set(counts) <= {"READY", "PARTIAL_READY", "BLOCKED", "NO_WORK", "COMPLETE"}
    assert sum(counts.values()) == 17
    assert payload["readiness"]["execution_status_counts"] == counts
    batches = {row["batch_id"]: row for row in readiness["batches"]}
    assert batches[BATCH_04]["completion_status"] == closed("IN_PROGRESS", "COMPLETE")
    # RUN-01 时点 = PARTIAL_READY；后续 run 会把 B04 推到 BLOCKED（frontier 前移）
    assert batches[BATCH_04]["execution_status"] in closed(("PARTIAL_READY", "BLOCKED"), ("COMPLETE",))  # [M11-CLOSURE]
    # RUN-01 时点 = 13 resolved；后续 production run 会继续推进（ch075/ch076...）
    assert len(batches[BATCH_04]["resolved_target_ids"]) >= 13
    # RUN-01 时点 B04 还有 1 个 ready；后续 run 会把它推进为 blocked（frontier 前移）
    assert len(batches[BATCH_04]["ready_target_ids"]) <= 1
    assert batches[BATCH_06]["execution_status"] == closed("BLOCKED", "COMPLETE")
    assert len(batches[BATCH_06]["resolved_target_ids"]) == closed(15, 21)
    assert batches[BATCH_06]["ready_target_ids"] == []
    assert len(batches[BATCH_06]["blocked_target_ids"]) == closed(6, 0)
    assert batches["REPAIR_BATCH_07"]["execution_status"] in closed(("PARTIAL_READY", "BLOCKED"), ("COMPLETE",))  # [M11-CLOSURE]
    assert payload["readiness"]["execution_status_counts"] == (
        readiness["execution_status_counts"])
    for row in readiness["batches"]:
        assert row["completion_status"] in ("NOT_STARTED", "IN_PROGRESS", "COMPLETE",
                                           "HUMAN_REVIEW")
        assert row["execution_status"] in ("READY", "PARTIAL_READY", "BLOCKED",
                                           "NO_WORK", "COMPLETE")
        assert not set(row["ready_target_ids"]) & set(row["blocked_target_ids"])


def test_batch07_not_entered(run01) -> None:
    service, payload = run01
    gate = _run_artifact("M11_RUN_01_GATE.json")
    assert gate["checks"]["batch07_not_entered"] is True
    reconciliation = _artifact(DESIGN_DIR / RUN_RECONCILIATION)
    batch7 = _artifact(DESIGN_DIR / BATCH_06_SCOPE_FILE)
    assert batch7["batch_id"] == BATCH_06
    executed = {row["chapter_id"] for row in reconciliation["records"]
                if row["new_resolution_status"] in ("RESOLVED_REPAIRED",
                                                    "RESOLVED_NO_REPAIR_REQUIRED")}
    readiness = _artifact(DESIGN_DIR / "M11_READINESS_V2.json")
    batch_07 = next(row for row in readiness["batches"]
                    if row["batch_id"] == "REPAIR_BATCH_07")
    assert not executed & set(batch_07["resolved_target_ids"])
    assert payload["batch_07_executed"] is False


# ---------------------------------------------------------------- backlog / M12
def test_production_backlog_status_tracking(run01) -> None:
    service, payload = run01
    backlog = _artifact(DESIGN_DIR / "M11_PRODUCTION_BACKLOG.json")
    assert set(backlog["lane_counts"]) == set(BACKLOG_LANES)
    assert all(count >= 1 for count in backlog["lane_counts"].values())
    assert backlog["item_count"] == sum(backlog["lane_counts"].values())
    assert backlog["last_run"] == RUN_ID
    for row in backlog["items"]:
        for field in ("item_id", "lane", "target_ids", "blocking_batches", "priority",
                      "dependencies", "required_actor", "next_action",
                      "current_artifact_ref"):
            assert field in row, field
    done = [row for row in backlog["items"] if row["status"] == "DONE"]
    done_ids = {row["item_id"] for row in done}
    assert "BL_AUTO_B06" in done_ids
    b06 = next(row for row in done if row["item_id"] == "BL_AUTO_B06")
    assert b06["completed_by_run"] == RUN_ID
    assert len(b06["completed_targets"]) == 16
    assert any(row["item_id"] == "BL_AUTO_B04" for row in backlog["items"])
    assert backlog["history_item_count"] >= 1
    assert payload["backlog"]["item_count"] == backlog["item_count"]


def test_m12_entry_still_not_allowed(run01) -> None:
    service, payload = run01
    m12 = _artifact(DESIGN_DIR / "p15p/M12_ENTRY_CRITERIA.json")
    assert m12["criteria_count"] == 9
    assert m12["m12_entry_allowed"] is False
    assert m12["satisfied_count"] == len(m12["satisfied_criteria"])  # [M11-CLOSURE] P15p projection 自洽为准
    assert m12["unsatisfied_count"] == len(m12["unsatisfied_criteria"])  # [M11-CLOSURE]
    assert m12["blocking_count"] == len(m12["blocking_criteria"])  # [M11-CLOSURE]
    assert len(m12["satisfied_criteria"]) == m12["satisfied_count"]
    assert set(m12["blocking_criteria"]) <= set(m12["unsatisfied_criteria"])
    assert not set(m12["satisfied_criteria"]) & set(m12["unsatisfied_criteria"])
    assert all(row["satisfied"] is False or row["blocking"] is False
               for row in m12["criteria"])
    assert payload["m12"]["entry_allowed"] is False


# ---------------------------------------------------------------- truth / capability
def test_truth_digests_unchanged(run01) -> None:
    service, payload = run01
    now = service.truth_digests()
    assert now["canon"] == FROZEN_SOURCE_DIGESTS["canon"]
    assert now["story_state"] == FROZEN_SOURCE_DIGESTS["story_state"]
    assert now["legacy"] == FROZEN_SOURCE_DIGESTS["legacy"]
    assert now["chapter_ir"] == FROZEN_SOURCE_DIGESTS["chapter_ir"]
    assert now["historical_foundation"] == FROZEN_FOUNDATION_DIGESTS
    gate = _run_artifact("M11_RUN_01_GATE.json")
    assert gate["checks"]["truth_digests_unchanged"] is True
    assert gate["checks"]["confirmed_facts_changed_zero"] is True


def test_field_rebind_stays_not_proven(run01) -> None:
    service, payload = run01
    ledger = _artifact(DESIGN_DIR / "M11_REPAIR_SUBTYPE_LEDGER.json")
    assert ledger["resolved_subtype_counts"].get("repaired_field_rebind", 0) == 0
    assert payload["field_rebind_natural_end_to_end"] is False
    evidence = DESIGN_DIR / "PRODUCTION_CAPABILITY_EVIDENCE.json"
    assert not evidence.is_file()
    capability = _artifact(DESIGN_DIR / "p15p/P15_CAPABILITY_ACCEPTANCE_MATRIX.json")
    verdicts = {row["capability"]: row["verdict"] for row in capability["capabilities"]}
    assert verdicts["Field Rebind"] == "NOT_PROVEN"


def test_architecture_exception_behavior(run01) -> None:
    service, payload = run01
    gate = _run_artifact("M11_RUN_01_GATE.json")
    assert gate["architecture_exceptions"] == []
    assert gate["checks"]["architecture_exception_recorded"] is True
    preflight = _run_artifact("M11_RUN_01_BATCH04_PREFLIGHT.json")
    assert all(row["architecture_exception"] is False for row in preflight["targets"])
    assert payload["architecture_exceptions"] == []
    contract = _artifact(DESIGN_DIR / "M11_REPAIR_SYSTEM_CONTRACT_V1.json")
    assert ARCHITECTURE_EXCEPTION not in contract["primary_repair_classes"]


def test_run01_gate_pass_with_injected_evidence(run01) -> None:
    service, payload = run01
    gate = _run_artifact("M11_RUN_01_GATE.json")
    # 唯一允许的未通过项是 test evidence（pytest / validate_project）
    assert set(gate["failed_checks"]) <= {"full_pytest_pass", "validate_project_pass"}
    assert gate["status"] in ("EVIDENCE_REQUIRED", "PASS")
    for key, value in gate["checks"].items():
        if key not in ("full_pytest_pass", "validate_project_pass"):
            assert value is True, key
    service.record_test_evidence(pytest_summary="injected", pytest_passed=1,
                                 validate_summary="injected")
    baseline = _run_artifact("M11_RUN_01_BASELINE.json")
    reconciliation = _artifact(DESIGN_DIR / RUN_RECONCILIATION)
    replay = service.run_gate(
        baseline=baseline,
        residual={"targets": payload["residual"]["targets"], "preflight": {
            "targets": _run_artifact("M11_RUN_01_BATCH04_PREFLIGHT.json")["targets"]}},
        frontier={"targets": payload["frontier"]["targets"],
                 "blocked_targets": _artifact(
                     DESIGN_DIR / BATCH_06_SCOPE_FILE)["blocked_target_ids"]},
        reconciliation=reconciliation,
        projections={"overlay": _artifact(DESIGN_DIR / "M11_OVERLAY_V2.json"),
                     "readiness": _artifact(DESIGN_DIR / "M11_READINESS_V2.json"),
                     "ledger": _artifact(DESIGN_DIR / "M11_REPAIR_SUBTYPE_LEDGER.json")},
        backlog=_artifact(DESIGN_DIR / "M11_PRODUCTION_BACKLOG.json"),
        contracts=[_run_artifact("M11_RUN_01_BATCH_04_ACCEPTANCE_CONTRACT.json"),
                   _run_artifact("M11_RUN_01_BATCH_06_ACCEPTANCE_CONTRACT.json")],
        evidence={"pytest": {"status": "PASS", "summary": "injected"},
                  "validate_project": {"status": "PASS", "summary": "injected"}})
    assert replay["status"] == "PASS"
    assert replay["failed_checks"] == []
