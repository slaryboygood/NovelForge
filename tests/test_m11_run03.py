"""M11-RUN-03：Production Execution 回归（Auto Safe Frontier through Batch 08）
+ P15 executor 只读不变量（P15_EXECUTOR_READ_ONLY_AFTER_CLOSEOUT）。

production execution tests（不是 architecture experiment）：
scope freeze、只执行 baseline ready target、新释放 deferred、blocked untouched、
dynamic downgrade 隔离、production CDQ ownership、P15 machinery 不得 reclaim、
overlay / readiness / backlog / M12 / truth digests 正确。
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
from novelforge.story_engine.m11_run03 import (

    BATCH_08,
    BATCH_08_SCOPE_FILE,
    M11Run03Service,
    RUN_ID,
    RUN_RECONCILIATION,
)

from m11_phase_history import closed

ROOT = Path(".").resolve()
DESIGN_DIR = ROOT / "workspace/wasteland_001_exports/repair_adoption_v1"
REPAIR_DIR = ROOT / "workspace/wasteland_001_exports/repair_v1"
RUN_DIR = DESIGN_DIR / "m11_run_03"


@pytest.fixture(scope="module")
def run03():
    service = M11Run03Service(ROOT)
    payload = service.run()
    return service, payload


def _artifact(path: Path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _run_artifact(name: str):
    return _artifact(RUN_DIR / name)


def _digest(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()[:16]


# ---------------------------------------------------------------- baseline / scope
def test_scope_frozen_before_execution(run03) -> None:
    service, payload = run03
    baseline = _run_artifact("M11_RUN_03_BASELINE.json")
    scope = _run_artifact("M11_RUN_03_EXECUTION_SCOPE.json")
    assert baseline["run_id"] == RUN_ID
    assert baseline["git"]["commit"]
    assert baseline["primary_buckets"] == {
        "resolved_repaired": 86, "resolved_no_repair_required": 23,
        "evidence_ready": 3, "manual_required": 3, "content_design_required": 34,
        "author_decision": 1, "pending": 222}
    assert baseline["batch_execution_status_counts"] == {
        "BLOCKED": 6, "PARTIAL_READY": 7, "READY": 4}
    assert baseline["frontier"]["batch_08"] == {
        "completion_status": "IN_PROGRESS", "execution_status": "PARTIAL_READY",
        "resolved": 0, "ready": 15, "blocked": 9}
    assert scope["frozen"] is True and scope["run_id"] == RUN_ID
    assert scope["frontier_max_batch"] == BATCH_08
    assert scope["contract_digest"] == service.frozen_digests()["contract"]
    assert scope["gate_digest"] == service.frozen_digests()["repair_gate"]
    assert scope["matches_run02_baseline"]["REPAIR_BATCH_04"] is True
    assert scope["matches_run02_baseline"]["REPAIR_BATCH_08"] is True
    assert scope["run02_baseline"]["REPAIR_BATCH_08"] == {
        "ready": 15, "blocked": 9, "execution_status": "PARTIAL_READY"}
    assert payload["status"] in ("PASS", "EVIDENCE_REQUIRED")


def test_batch04_baseline_target(run03) -> None:
    service, payload = run03
    scope = _run_artifact("M11_RUN_03_EXECUTION_SCOPE.json")
    assert len(scope["batch_04_residual_targets"]) == 1
    assert scope["batch_04_residual_targets"] == [payload["residual"]["targets"][0]]
    preflight = _run_artifact("M11_RUN_03_BATCH04_PREFLIGHT.json")
    row = preflight["targets"][0]
    assert row["legacy_label"] == "ch076"
    assert str(row["target_state"]) == "READY"  # Frozen run-local evidence.
    assert row["actual_repair_class"] == "NO_REPAIR_REQUIRED"
    assert row["execution_decision"] == "SAFE_AUTO"
    assert row["verdict"] == "SAFE_AUTO_EXECUTE"
    assert row["foundation"]["evidence_substrate"] == "HISTORICAL_FULL_IR"
    assert row["foundation"]["digest_match"] is True
    assert row["execution_blockers"] == []
    execution = _run_artifact("M11_RUN_03_BATCH04_EXECUTION.json")
    assert execution["verified"] == 1 and execution["gate_status"] == "PASS"
    reconciliation = _artifact(DESIGN_DIR / RUN_RECONCILIATION)
    record = next(r for r in reconciliation["records"] if r["legacy_label"] == "ch076")
    assert record["new_resolution_status"] == "RESOLVED_NO_REPAIR_REQUIRED"
    assert record["repair_subtype"] == "no_repair_required"
    assert payload["residual"]["acceptance"] == "PASS"


def test_batch04_newly_unlocked_deferred(run03) -> None:
    service, payload = run03
    reconciliation = _artifact(DESIGN_DIR / RUN_RECONCILIATION)
    executed = {row["chapter_id"] for row in reconciliation["records"]
                if row["new_resolution_status"] in ("RESOLVED_REPAIRED",
                                                    "RESOLVED_NO_REPAIR_REQUIRED")}
    # RUN-03 只执行了 ch076；ch077（RUN-03 时被释放）留到 RUN-04
    scope = _run_artifact("M11_RUN_03_EXECUTION_SCOPE.json")
    assert scope["batch_04_residual_targets"] == [
        "uuid_498668ad6941517788e2059ad31d19a7"]          # ch076
    assert "uuid_8bea0d910dab5815bb84a71e72ee4fd2" not in executed      # ch077 deferred
    assert payload["gate"]["checks"]["only_ready_target_executed"] is True


# ---------------------------------------------------------------- Batch 08
def test_batch08_closure(run03) -> None:
    service, payload = run03
    scope = _artifact(DESIGN_DIR / BATCH_08_SCOPE_FILE)
    assert scope["frozen"] is True and scope["batch_id"] == BATCH_08
    assert len(scope["ready_target_ids"]) == 15
    assert len(scope["blocked_target_ids"]) == 9
    closure = scope["dependency_closure"]
    assert closure["readiness_ready_count"] == 15
    assert closure["readiness_blocked_count"] == 9
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
    assert payload["frontier"]["scope"] == {"ready": 15, "blocked": 9}


def test_batch08_blocked_untouched(run03) -> None:
    service, payload = run03
    scope = _artifact(DESIGN_DIR / BATCH_08_SCOPE_FILE)
    blocked = {str(item) for item in scope["blocked_target_ids"]}
    assert len(blocked) == 9
    assert {row["legacy_label"] for row in scope["blocked_targets"]} == {
        "ch225", "ch230", "ch231", "ch232", "ch233", "ch235", "ch237", "ch238", "ch249"}
    for row in scope["blocked_targets"]:
        assert row["verdict"] == "BLOCKED_READ_ONLY_CONTEXT"
    reconciliation = _artifact(DESIGN_DIR / RUN_RECONCILIATION)
    for row in reconciliation["records"]:
        if row["chapter_id"] in blocked:
            assert row["new_resolution_status"] == "BLOCKED_CONTENT_DESIGN"
            assert row["repair_subtype"] == "" and row["repaired_ref"] == ""
    execution = _run_artifact("M11_RUN_03_BATCH08_EXECUTION.json")
    assert not set(execution["targets"]) & blocked
    assert set(execution["blocked_targets"]) == blocked
    assert payload["gate"]["checks"]["blocked_target_untouched"] is True


def test_batch08_execution_and_promotion(run03) -> None:
    service, payload = run03
    execution = _run_artifact("M11_RUN_03_BATCH08_EXECUTION.json")
    assert len(execution["targets"]) == 15
    assert execution["verified"] == 9
    assert execution["human_review"] == 6
    assert execution["promotion_mode"] == "partial"
    assert execution["gate_status"] == "PASS"
    diff = _artifact(REPAIR_DIR / "BATCH_08_DIFF.json")
    assert diff["semantic_elements_added"] == 0
    assert diff["semantic_elements_removed"] == 0
    assert diff["confirmed_facts_changed"] == 0
    assert diff["read_only_chapters_changed"] == 0
    reconciliation = _artifact(DESIGN_DIR / RUN_RECONCILIATION)
    assert reconciliation["promoted"] == 10          # ch076 + B08 的 9
    assert reconciliation["promoted_evidence_only"] == 7
    assert reconciliation["promoted_no_repair_required"] == 3
    assert reconciliation["promoted_field_rebind"] == 0
    assert run03[1]["frontier"]["acceptance"] == "PASS"


def test_dynamic_downgrade(run03) -> None:
    service, payload = run03
    reconciliation = _artifact(DESIGN_DIR / RUN_RECONCILIATION)
    counts = reconciliation["dynamic_downgrade_counts"]
    assert counts["CONTENT_DESIGN_REQUIRED"] == 5
    assert counts["MANUAL_REQUIRED"] == 1
    assert counts["EVIDENCE_READY"] == 0
    assert counts["AUTHOR_DECISION_REQUIRED"] == 0
    assert counts["BLOCKED_CONFIRMED_BINDING_CONFLICT"] == 0
    assert counts["ARCHITECTURE_EXCEPTION_REQUIRED"] == 0
    design = {row["legacy_label"] for row in reconciliation["records"]
              if row["new_resolution_status"] == "CONTENT_DESIGN_REQUIRED"}
    assert design == {"ch246", "ch250", "ch253", "ch254", "ch258"}
    manual = [row for row in reconciliation["records"]
              if row["new_resolution_status"] == "MANUAL_REQUIRED"]
    assert len(manual) == 1 and manual[0]["legacy_label"] == "ch245"
    assert manual[0]["evidence_substrate"] == "HISTORICAL_FULL_IR_PARTIAL"
    # target A 的 downgrade 不影响同 batch 的 safe target
    assert payload["frontier"]["verified"] == 9


# ---------------------------------------------------------------- production CDQ
def test_production_cdq_origin_and_queue(run03) -> None:
    service, payload = run03
    reconciliation = _artifact(DESIGN_DIR / RUN_RECONCILIATION)
    design_items = reconciliation["content_design_items_registered"]
    assert len(design_items) == 5
    assert all(str(item["design_item_id"]).startswith("CDQ_RUN03_")
               for item in design_items)
    assert all(str(item["origin"]).startswith("M11_RUN_03") for item in design_items)
    queue = _artifact(DESIGN_DIR / "M11_CONTENT_DESIGN_QUEUE_V2.json")
    run03_items = [row for row in queue["items"]
                   if str(row["design_item_id"]).startswith("CDQ_RUN03_")]
    assert len(run03_items) == 5
    assert all(str(row["origin"]).startswith("M11_RUN_03") for row in run03_items)
    queue3 = _artifact(DESIGN_DIR / "M11_CONTENT_DESIGN_QUEUE_V3.json")
    active = [row for row in queue3["requirements"] if row["status"] == "ACTIVE"]
    overlay = _artifact(DESIGN_DIR / "M11_OVERLAY_V2.json")
    assert len(active) == overlay["content_design_required"]
    assert overlay["content_design_required"] == 0  # [M11-CLOSURE] 已 terminal
    assert payload["reconciliation"]["content_design_items_registered"] == 5


def test_production_cdq_not_p15_micro_candidate(run03) -> None:
    service, _payload = run03
    policy = ContentRewritePolicyService(ROOT)
    reclassification = policy.reclassify()
    rows = {row["legacy_label"]: row for row in reclassification["rows"]}
    queue_status = {str(row.get("legacy_label")): str(row.get("status"))
                    for row in _artifact(
                        DESIGN_DIR / "M11_CONTENT_DESIGN_QUEUE_V3.json")["requirements"]}
    for label in ("ch198", "ch207", "ch210", "ch215", "ch218",
                  "ch246", "ch250", "ch253", "ch254", "ch258"):
        # [M11-CLOSURE] production item 已 terminal；不得被 P15 micro executor 重新 claim
        assert str(queue_status.get(label, "")).startswith("RESOLVED"), label
        assert rows.get(label, {}).get("micro_scale_candidate", False) is False
    assert reclassification["zero_new_event_micro_candidates"] == 0


def test_p15m_executor_cannot_reclaim_production_item(run03) -> None:
    service, _payload = run03
    planner = MicroRepairFrontierPlanner(ROOT)
    scope = planner.plan()
    selected = {row["legacy_label"] for row in scope["selected"]}
    production_labels = {f"ch{n}" for n in
                         ("198", "207", "210", "215", "218",
                          "246", "250", "253", "254", "258")}
    assert not selected & production_labels
    ineligible = {row["legacy_label"]: row for row in scope["ineligible"]}
    for label in sorted(production_labels):
        assert "not_production_run_item" in ineligible[label]["ineligible_reason"]


def test_p15o_executor_cannot_reclaim_production_item(run03) -> None:
    service, _payload = run03
    wave02 = Wave02Service(ROOT)
    scope = wave02.scope()
    production_labels = {"ch198", "ch207", "ch210", "ch215", "ch218",
                         "ch246", "ch250", "ch253", "ch254", "ch258"}
    # wave-02 scope 只从 micro_scale_candidate 派生；production CDQ 不是 candidate →
    # 完全不出现在 selected / ineligible（不会被 P15o 重新 claim）。
    selected = {row["legacy_label"] for row in scope["selected"]}
    ineligible = {row["legacy_label"] for row in scope["ineligible"]}
    assert not selected & production_labels
    assert not ineligible & production_labels
    assert scope["selected_count"] == len(scope["selected"])
    rows = scope["selected"] + scope["ineligible"]
    assert all(row["eligible"] is (row in scope["selected"]) for row in rows)


# ---------------------------------------------------------------- P15 isolation regression
def test_p15_isolation_invariant_pass(run03) -> None:
    service, payload = run03
    invariant = _run_artifact(f"{P15_ISOLATION_INVARIANT_ID}.json")
    assert invariant["invariant_id"] == P15_ISOLATION_INVARIANT_ID
    assert invariant["status"] == "PASS"
    assert invariant["static_scan_pass"] is True
    assert invariant["production_item_ownership_pass"] is True
    assert invariant["runtime_isolation_pass"] is True
    assert invariant["production_item_count"] >= 10
    assert not any(invariant["static_scan_findings"].values())
    assert not invariant["live_p15_artifacts_for_production_chapters"]
    assert all(row["owned_by_production_run"]
               for row in invariant["production_item_ownership"])
    gate = _run_artifact("M11_RUN_03_GATE.json")
    assert gate["checks"]["p15_executor_isolation_pass"] is True
    assert gate["checks"]["production_cdq_ownership_pass"] is True
    assert payload["p15_isolation"]["status"] == "PASS"


def test_p15_historical_regression_leaves_production_state_unchanged(run03) -> None:
    """§20：跑 P15 historical regression 后，production primary resolution / subtype /
    overlay / production reconciliation 必须不变。"""

    service, _payload = run03
    overlay_path = DESIGN_DIR / "M11_OVERLAY_V2.json"
    readiness_path = DESIGN_DIR / "M11_READINESS_V2.json"
    ledger_path = DESIGN_DIR / "M11_REPAIR_SUBTYPE_LEDGER.json"
    run02_recon = DESIGN_DIR / "M11_RUN_02_RECONCILIATION.json"
    run03_recon = DESIGN_DIR / RUN_RECONCILIATION
    before = {name: _digest(path) for name, path in (
        ("overlay", overlay_path), ("readiness", readiness_path),
        ("ledger", ledger_path), ("run02_recon", run02_recon),
        ("run03_recon", run03_recon))}
    ledger_before = _artifact(ledger_path)["ledger"]

    # P15 historical regression：reclassify + wave planner + wave-02 scope（只做 projection）
    ContentRewritePolicyService(ROOT).reclassify()
    MicroRepairFrontierPlanner(ROOT).plan()
    Wave02Service(ROOT).scope()

    after = {name: _digest(path) for name, path in (
        ("overlay", overlay_path), ("readiness", readiness_path),
        ("ledger", ledger_path), ("run02_recon", run02_recon),
        ("run03_recon", run03_recon))}
    assert before == after
    assert _artifact(ledger_path)["ledger"] == ledger_before
    overlay = _artifact(overlay_path)
    assert overlay["conservation"]["exact"] is True
    readiness = _artifact(readiness_path)
    batch_by_id = {row["batch_id"]: row for row in readiness["batches"]}
    # production content-design target 仍是 blocked（primary resolution 不变）
    run02_records = {row["legacy_label"]: row for row in _artifact(
        DESIGN_DIR / "M11_RUN_02_RECONCILIATION.json")["records"]}
    run03_records = {row["legacy_label"]: row for row in _artifact(
        DESIGN_DIR / RUN_RECONCILIATION)["records"]}
    # [M11-CLOSURE] live readiness 已全部 terminal；改用 frozen scope artifact 证明
    # 该 target 在执行时确实处于 blocked 状态（历史 timepoint 证据，不随 closure 改变）
    assert (run02_records["ch198"]["new_resolution_status"]
            == "CONTENT_DESIGN_REQUIRED")   # [M11-CLOSURE] run-local reconciliation
    assert (run03_records["ch246"]["new_resolution_status"]
            == "CONTENT_DESIGN_REQUIRED")   # [M11-CLOSURE] run-local reconciliation


def test_ledger_last_record_wins(run03) -> None:
    service, _payload = run03
    ledger = _artifact(DESIGN_DIR / "M11_REPAIR_SUBTYPE_LEDGER.json")
    reconciliation = _artifact(DESIGN_DIR / RUN_RECONCILIATION)
    production_design = [row for row in reconciliation["records"]
                         if row["new_resolution_status"] == "CONTENT_DESIGN_REQUIRED"]
    for row in production_design:
        # [M11-CLOSURE] 该 target 已由 M11 final closure terminal：
        # 一份 primary target 只能对应一份 terminal ledger entry（不再缺席）
        assert row["chapter_id"] in ledger["ledger"]
    assert ledger["resolved_subtype_counts"].get("repaired_micro_semantic") == 21
    assert len(ledger["ledger"]) == _artifact(
        DESIGN_DIR / "M11_OVERLAY_V2.json")["resolved_total"]


def test_idempotent_dynamic_queue_merge(run03) -> None:
    service, _payload = run03
    queue_before = _artifact(DESIGN_DIR / "M11_CONTENT_DESIGN_QUEUE_V2.json")
    integration = service.readiness.integrate_dynamic_design_items()
    queue_after = _artifact(DESIGN_DIR / "M11_CONTENT_DESIGN_QUEUE_V2.json")
    assert integration["new_item_count"] == 0
    assert integration["duplicate_count"] == 7
    assert integration["merged_item_count"] == queue_before["item_count"]
    assert queue_after["item_count"] == queue_before["item_count"]
    ids = [row["design_item_id"] for row in queue_after["items"]]
    assert len(ids) == len(set(ids))


# ---------------------------------------------------------------- manual / entity / author
def test_manual_dependency_preserved(run03) -> None:
    service, payload = run03
    backlog = _artifact(DESIGN_DIR / "M11_PRODUCTION_BACKLOG.json")
    manual_items = {row["item_id"] for row in backlog["items"]
                    if row["lane"] == "LANE_MANUAL"}
    assert {"BL_MANUAL_ch166", "BL_MANUAL_ch199", "BL_MANUAL_ch245"} <= manual_items
    reconciliation = _artifact(DESIGN_DIR / RUN_RECONCILIATION)
    resolved = {row["legacy_label"] for row in reconciliation["records"]
                if row["new_resolution_status"] in ("RESOLVED_REPAIRED",
                                                    "RESOLVED_NO_REPAIR_REQUIRED")}
    assert not {"ch166", "ch199", "ch245"} & resolved
    readiness = _artifact(DESIGN_DIR / "M11_READINESS_V2.json")
    batch_08 = next(row for row in readiness["batches"]
                    if row["batch_id"] == BATCH_08)
    manual_blocked = [row for row in batch_08["blocked_target_ids"]
                      if "BLOCKED_MANUAL_REPAIR"
                      in batch_08["block_reason_by_target"].get(row, "")]
    assert not manual_blocked  # [M11-CLOSURE] manual lane 已由 final closure 解决
    assert payload["gate"]["checks"]["blocked_target_untouched"] is True


def test_entity_dependency_preserved(run03) -> None:
    service, payload = run03
    inventory = _artifact(DESIGN_DIR / "p15p/M11_ENTITY_MANUAL_INVENTORY.json")
    assert inventory["entity"]["cluster_count"] == 47
    assert inventory["entity"]["context_resolvable_cluster_count"] == 13
    assert inventory["entity"]["entity_truth_modified"] is False
    assert {row["legacy_label"] for row in
            inventory["entity"]["specific_pending_items"]} == {"ch093", "ch120"}
    overlay = _artifact(DESIGN_DIR / "M11_OVERLAY_V2.json")
    assert overlay["evidence_ready"] == 0  # [M11-CLOSURE] evidence lane 已 terminal
    reconciliation = _artifact(DESIGN_DIR / RUN_RECONCILIATION)
    entity_blocked_labels = {row["legacy_label"] for row in reconciliation["records"]
                             if row["new_resolution_status"] == "BLOCKED_CONTENT_DESIGN"}
    assert {"ch235", "ch237", "ch238", "ch249"} <= entity_blocked_labels
    assert payload["p15_isolation"]["runtime_isolation_pass"] is True


def test_author_policy_blank_and_new_event_cannot_promote(run03) -> None:
    service, payload = run03
    inventory = _artifact(DESIGN_DIR / "AUTHOR_ACTION_INVENTORY.json")
    assert inventory["policy_selection"]["auto_selected"] == ""
    assert inventory["policy_selection"]["author_selected"] == ""
    assert inventory["policy_selection"]["status"] == "PENDING_AUTHOR_SELECTION"
    assert inventory["auto_resolved"] == 0
    assert payload["author_policy_selected"] is False
    assert payload["author_decisions_resolved"] == 0
    gate = _run_artifact("M11_RUN_03_GATE.json")
    assert gate["checks"]["no_author_policy_auto_selected"] is True
    assert gate["checks"]["no_author_decision_auto_resolved"] is True
    proposals = _artifact(DESIGN_DIR / "p15o/CONCRETE_REWRITE_PROPOSALS.json")
    decisions = [row for row in proposals["proposals"] if row.get("decision_event")]
    assert all(row["author_approval_required"] == "AUTHOR_CONTENT_APPROVAL"
                             for row in decisions)
    reconciliation = _artifact(DESIGN_DIR / RUN_RECONCILIATION)
    promoted = [row for row in reconciliation["records"]
                if row["new_resolution_status"] in ("RESOLVED_REPAIRED",
                                                    "RESOLVED_NO_REPAIR_REQUIRED")]
    assert all(row["repair_class"] in ("EVIDENCE_ONLY", "NO_REPAIR_REQUIRED")
               for row in promoted)
    assert payload["gate"]["new_historical_events"] == 0


# ---------------------------------------------------------------- overlay / readiness
def test_overlay_conservation(run03) -> None:
    service, payload = run03
    overlay = _artifact(DESIGN_DIR / "M11_OVERLAY_V2.json")
    assert overlay["conservation"] == {"primary_total": TARGET_COUNT,
                                       "target_count": TARGET_COUNT, "exact": True}
    assert list(overlay["primary_resolution_status_counts"]) == list(PRIMARY_BUCKETS)
    assert sum(overlay["primary_resolution_status_counts"].values()) == TARGET_COUNT
    # RUN-03 时点值冻结在 reconciliation（live overlay 会被 RUN-04+ 继续推进）
    reconciliation = _artifact(DESIGN_DIR / RUN_RECONCILIATION)
    assert reconciliation["promoted"] == 10
    assert reconciliation["promoted_evidence_only"] == 7
    assert reconciliation["promoted_no_repair_required"] == 3
    assert overlay["resolved_total"] >= 119
    assert overlay["repaired"] >= 93
    assert overlay["no_repair_required"] >= 26
    assert overlay["repaired_evidence_only"] >= 68
    assert overlay["repaired_field_rebind"] == 0
    assert overlay["repaired_micro_semantic"] == 21
    assert overlay["repaired_confirmed_override"] == 4
    assert overlay["content_design_required"] == 0  # [M11-CLOSURE] 已 terminal
    assert overlay["manual_required"] == 0  # [M11-CLOSURE] 已 terminal
    assert overlay["pending"] <= 206
    assert payload["overlay_conservation"]["exact"] is True


def test_readiness_recompute(run03) -> None:
    service, payload = run03
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
    assert len(b04["resolved_target_ids"]) >= 15
    # RUN-03 时点 = 1（ch077 释放 ch078）；后续 run 继续推进 → 允许 0
    assert len(b04["ready_target_ids"]) <= 1
    assert len(b04["blocked_target_ids"]) <= 8
    b08 = batches[BATCH_08]
    assert (b08["completion_status"], b08["execution_status"]) == closed(
        ("IN_PROGRESS", "BLOCKED"), ("COMPLETE", "COMPLETE"))
    assert len(b08["resolved_target_ids"]) == closed(9, 24)
    assert b08["ready_target_ids"] == []
    assert len(b08["blocked_target_ids"]) == closed(15, 0)
    b09 = batches["REPAIR_BATCH_09"]
    # RUN-03 时 B09 = PARTIAL_READY（14 ready / 6 blocked）；RUN-04 执行后变 BLOCKED
    assert b09["completion_status"] == closed("IN_PROGRESS", "COMPLETE")
    assert b09["execution_status"] in closed(("PARTIAL_READY", "BLOCKED"), ("COMPLETE",))  # [M11-CLOSURE]
    if b09["execution_status"] == "PARTIAL_READY":
        assert len(b09["ready_target_ids"]) == 14
        assert len(b09["blocked_target_ids"]) == 6
    else:
        assert b09["ready_target_ids"] == []
        assert len(b09["resolved_target_ids"]) >= 12
    assert payload["readiness"]["execution_status_counts"] == (
        readiness["execution_status_counts"])
    for row in readiness["batches"]:
        assert row["completion_status"] in ("NOT_STARTED", "IN_PROGRESS", "COMPLETE",
                                           "HUMAN_REVIEW")
        assert row["execution_status"] in ("READY", "PARTIAL_READY", "BLOCKED",
                                           "NO_WORK", "COMPLETE")
        assert not set(row["ready_target_ids"]) & set(row["blocked_target_ids"])


def test_batch09_not_executed(run03) -> None:
    service, payload = run03
    gate = _run_artifact("M11_RUN_03_GATE.json")
    assert gate["checks"]["batch09_not_entered"] is True
    reconciliation = _artifact(DESIGN_DIR / RUN_RECONCILIATION)
    executed = {row["chapter_id"] for row in reconciliation["records"]}
    readiness = _artifact(DESIGN_DIR / "M11_READINESS_V2.json")
    batch_09 = next(row for row in readiness["batches"]
                    if row["batch_id"] == "REPAIR_BATCH_09")
    assert not executed & (set(batch_09["ready_target_ids"])
                           | set(batch_09["blocked_target_ids"]))
    assert payload["batch_09_executed"] is False


# ---------------------------------------------------------------- backlog / M12
def test_backlog_update(run03) -> None:
    service, payload = run03
    backlog = _artifact(DESIGN_DIR / "M11_PRODUCTION_BACKLOG.json")
    assert set(backlog["lane_counts"]) == set(BACKLOG_LANES)
    assert all(count >= 1 for count in backlog["lane_counts"].values())
    assert backlog["item_count"] == sum(backlog["lane_counts"].values())
    assert backlog["item_count"] >= 44
    assert backlog["last_run"] == RUN_ID
    done = {row["item_id"]: row for row in backlog["items"]
            if row["status"] == "DONE"}
    assert {"BL_AUTO_B06", "BL_AUTO_B07", "BL_AUTO_B08"} <= set(done)
    assert done["BL_AUTO_B08"]["completed_by_run"] == RUN_ID
    assert len(done["BL_AUTO_B08"]["completed_targets"]) == 15
    assert {"BL_AUTO_B06", "BL_AUTO_B07", "BL_AUTO_B08"} <= set(
        payload["backlog"]["done_item_ids"])
    assert payload["backlog"]["item_count"] == backlog["item_count"]


def test_m12_remains_blocked(run03) -> None:
    service, payload = run03
    m12 = _artifact(DESIGN_DIR / "p15p/M12_ENTRY_CRITERIA.json")
    assert m12["criteria_count"] == 9
    assert m12["m12_entry_allowed"] is False
    assert m12["satisfied_count"] == len(m12["satisfied_criteria"])  # [M11-CLOSURE] P15p projection 自洽为准
    assert m12["unsatisfied_count"] == len(m12["unsatisfied_criteria"])  # [M11-CLOSURE]
    assert m12["blocking_count"] == len(m12["blocking_criteria"])  # [M11-CLOSURE]
    assert set(m12["blocking_criteria"]) <= set(m12["unsatisfied_criteria"])
    assert payload["m12"]["entry_allowed"] is False


# ---------------------------------------------------------------- truth / capability
def test_contract_gate_and_truth_digests_unchanged(run03) -> None:
    service, payload = run03
    baseline = _run_artifact("M11_RUN_03_BASELINE.json")
    now = service.frozen_digests()
    assert now["contract"] == baseline["frozen_contract"]["contract"]
    assert now["repair_gate"] == baseline["frozen_contract"]["repair_gate"]
    gate = _run_artifact("M11_RUN_03_GATE.json")
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


def test_field_rebind_production_evidence(run03) -> None:
    service, payload = run03
    ledger = _artifact(DESIGN_DIR / "M11_REPAIR_SUBTYPE_LEDGER.json")
    field_rebind = ledger["resolved_subtype_counts"].get("repaired_field_rebind", 0)
    evidence_path = DESIGN_DIR / "PRODUCTION_CAPABILITY_EVIDENCE.json"
    if field_rebind:
        assert evidence_path.is_file()
        evidence = _artifact(evidence_path)
        assert evidence["FIELD_REBIND"] == "PROVEN_BY_M11_RUN_03"
    else:
        assert payload["field_rebind_natural_end_to_end"] is False
        assert not evidence_path.is_file()


def test_run03_gate_pass_with_injected_evidence(run03) -> None:
    service, payload = run03
    gate = _run_artifact("M11_RUN_03_GATE.json")
    assert set(gate["failed_checks"]) <= {"full_pytest_pass", "validate_project_pass"}
    for key, value in gate["checks"].items():
        if key not in ("full_pytest_pass", "validate_project_pass"):
            assert value is True, key
    service.record_test_evidence(pytest_summary="injected", pytest_passed=1,
                                 validate_summary="injected")
    baseline = _run_artifact("M11_RUN_03_BASELINE.json")
    reconciliation = _artifact(DESIGN_DIR / RUN_RECONCILIATION)
    replay = service.run_gate(
        baseline=baseline,
        residual={"targets": payload["residual"]["targets"], "preflight": {
            "targets": _run_artifact("M11_RUN_03_BATCH04_PREFLIGHT.json")["targets"]}},
        frontier={"targets": payload["frontier"]["targets"],
                  "blocked_targets": _artifact(
                      DESIGN_DIR / BATCH_08_SCOPE_FILE)["blocked_target_ids"]},
        reconciliation=reconciliation,
        projections={"overlay": _artifact(DESIGN_DIR / "M11_OVERLAY_V2.json"),
                     "readiness": _artifact(DESIGN_DIR / "M11_READINESS_V2.json"),
                     "ledger": _artifact(DESIGN_DIR / "M11_REPAIR_SUBTYPE_LEDGER.json")},
        backlog=_artifact(DESIGN_DIR / "M11_PRODUCTION_BACKLOG.json"),
        contracts=[_run_artifact("M11_RUN_03_BATCH_04_ACCEPTANCE_CONTRACT.json"),
                   _run_artifact("M11_RUN_03_BATCH_08_ACCEPTANCE_CONTRACT.json")],
        evidence={"pytest": {"status": "PASS", "summary": "injected"},
                  "validate_project": {"status": "PASS", "summary": "injected"}})
    assert replay["status"] == "PASS"
    assert replay["failed_checks"] == []
