"""P15p：M11 Repair System Final Closeout 回归（contract / freeze / backlog / gate）。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from novelforge.story_engine.m11_p15p import (
    APPROVAL_CLASSES,
    AUTHOR_ACTION_GROUPS,
    BACKLOG_LANES,
    CAPABILITIES,
    FROZEN_FOUNDATION_DIGESTS,
    FROZEN_SOURCE_DIGESTS,
    M12_ENTRY_CRITERIA,
    P15_STATUS_MATRIX,
    REPAIR_CLASSES,
    REPAIR_GATE_V1,
    TARGET_COUNT,
    P15CloseoutService,
    approval_for,
)
from novelforge.story_engine.m11_readiness import PRIMARY_BUCKETS

from m11_phase_history import closed, report_records

ROOT = Path(".").resolve()


@pytest.fixture(scope="module")
def closeout():
    service = P15CloseoutService(ROOT)
    payload = service.run()
    return service, payload


def _artifact(service: P15CloseoutService, name: str):
    path = service.design_dir / "p15p" / name
    return json.loads(path.read_text(encoding="utf-8"))


def test_contract_schema_and_gate_ownership(closeout) -> None:
    service, _payload = closeout
    contract = json.loads((service.design_dir /
                           "M11_REPAIR_SYSTEM_CONTRACT_V1.json").read_text(
        encoding="utf-8"))
    assert contract["contract_id"] == "M11_REPAIR_SYSTEM_CONTRACT_V1"
    assert len(contract["primary_repair_classes"]) == 13
    assert tuple(contract["primary_repair_classes"]) == REPAIR_CLASSES
    assert tuple(contract["approval_classes"]) == APPROVAL_CLASSES
    assert contract["truth_precedence"] == [
        "Canon / StoryState",
        "ConfirmedHistoricalBindingGuard / ConfirmedBindingResolution",
        "Historical Full Chapter IR", "shadow fallback"]
    assert contract["repair_evidence_substrate"]["primary"] == "HISTORICAL_FULL_IR"
    assert contract["repair_evidence_substrate"]["digest_mismatch"] == "BLOCK"
    assert contract["queue_lifecycle"] == [
        "ACTIVE", "RESOLVED_REPAIRED", "RESOLVED_NO_REPAIR", "SUPERSEDED",
        "STALE_AFTER_OTHER_REPAIR", "MERGED_INTO_OTHER_REQUIREMENT",
        "AUTHOR_DESIGN_REQUIRED"]
    assert contract["overlay_semantics"]["primary_buckets"] == list(PRIMARY_BUCKETS)
    assert "author_content_rewrite" in contract["overlay_semantics"]["repair_subtypes"]
    gate = json.loads((service.design_dir / "REPAIR_GATE_V1.json").read_text(
        encoding="utf-8"))
    assert gate["check_count"] == len(REPAIR_GATE_V1)
    generic = [row["check"] for row in gate["checks"]
               if row["ownership"] == "generic"]
    adapter = [row["check"] for row in gate["checks"]
               if row["ownership"] == "adapter"]
    assert adapter == ["confirmed_historical_binding_guard"]
    assert "韩彻" not in " ".join(generic)
    assert "confirmed_historical_binding_guard" not in generic


def test_approval_boundary_rules(closeout) -> None:
    service, _payload = closeout
    contract = json.loads((service.design_dir /
                           "M11_REPAIR_SYSTEM_CONTRACT_V1.json").read_text(
        encoding="utf-8"))
    rules = {row["rule_id"]: row for row in contract["approval_boundary_rules"]}
    assert sorted(rules) == ["A", "B", "C", "D", "E"]
    assert rules["A"]["allowed_approvals"] == ["SAFE_AUTO",
                                               "MANUAL_OPERATOR_APPROVAL"]
    assert rules["B"]["default_approval"] == "AUTHOR_CONTENT_APPROVAL"
    assert rules["B"]["proposed_new_historical_event"] is True
    assert rules["C"]["requires_author_policy"] == "B"
    assert rules["D"]["allowed_approvals"] == ["AUTHOR_CONTENT_APPROVAL"]
    assert rules["D"]["policy_b_exempt"] is False
    assert rules["E"]["allowed_approvals"] == ["AUTHOR_DESIGN"]
    assert rules["E"]["policy_b_exempt"] is False


def test_approval_for_boundaries() -> None:
    assert approval_for(event_added=0, repair_class="EVIDENCE_ONLY") == "SAFE_AUTO"
    assert approval_for(event_added=0, repair_class="FIELD_REBIND") == "SAFE_AUTO"
    assert approval_for(event_added=1, repair_class="LOCAL_CONNECTIVE_EVENT_REQUIRED",
                        policy="") == "AUTHOR_CONTENT_APPROVAL"
    assert approval_for(event_added=1, repair_class="LOCAL_CAUSAL_BRIDGE_REQUIRED",
                        policy="B") == "MANUAL_OPERATOR_APPROVAL"
    # decision event：即使 Policy B 也必须作者内容审批
    assert approval_for(event_added=1, repair_class="LOCAL_DECISION_EVENT_REQUIRED",
                        policy="B") == "AUTHOR_CONTENT_APPROVAL"
    # 全部 hard gate 未 PASS 或超过 one-event 限制 → 不允许 Policy B 自动化
    assert approval_for(event_added=1, repair_class="LOCAL_CAUSAL_BRIDGE_REQUIRED",
                        policy="B", hard_gates_pass=False
                        ) == "AUTHOR_CONTENT_APPROVAL"
    assert approval_for(event_added=1, repair_class="LOCAL_CAUSAL_BRIDGE_REQUIRED",
                        policy="B", one_new_event_max=False
                        ) == "AUTHOR_CONTENT_APPROVAL"
    assert approval_for(event_added=2, repair_class="LOCAL_CAUSAL_BRIDGE_REQUIRED",
                        policy="B") == "AUTHOR_CONTENT_APPROVAL"
    assert approval_for(event_added=1, repair_class="MAJOR_AUTHOR_DESIGN_REQUIRED",
                        policy="B") == "AUTHOR_DECISION"


def test_readiness_enums_frozen(closeout) -> None:
    service, payload = closeout
    contract = json.loads((service.design_dir /
                           "M11_REPAIR_SYSTEM_CONTRACT_V1.json").read_text(
        encoding="utf-8"))
    semantics = contract["readiness_semantics"]
    assert semantics["completion_status"] == ["NOT_STARTED", "IN_PROGRESS",
                                             "COMPLETE", "HUMAN_REVIEW"]
    assert semantics["execution_status"] == ["READY", "PARTIAL_READY", "BLOCKED",
                                             "NO_WORK", "COMPLETE"]
    assert "target-level semantic dependency closure" in semantics["dependency"]
    assert semantics["no_additional_batch_status"] is True
    readiness = json.loads((service.design_dir / "M11_READINESS_V2.json").read_text(
        encoding="utf-8"))
    assert len(readiness["batches"]) == 17
    assert set(readiness["execution_status_counts"]) <= {
        "READY", "PARTIAL_READY", "BLOCKED", "NO_WORK", "COMPLETE"}
    assert payload["batch_matrix"]["batch_count"] == 17


def test_overlay_and_queue_conservation(closeout) -> None:
    service, payload = closeout
    overlay = json.loads((service.design_dir / "M11_OVERLAY_V2.json").read_text(
        encoding="utf-8"))
    assert overlay["conservation"] == {"primary_total": TARGET_COUNT,
                                       "target_count": TARGET_COUNT, "exact": True}
    assert list(overlay["primary_resolution_status_counts"]) == list(PRIMARY_BUCKETS)
    assert sum(overlay["primary_resolution_status_counts"].values()) == TARGET_COUNT
    queue = json.loads((service.design_dir /
                        "M11_CONTENT_DESIGN_QUEUE_V3.json").read_text(
        encoding="utf-8"))
    active = [row for row in queue["requirements"] if row["status"] == "ACTIVE"]
    assert len(active) == overlay["content_design_required"]
    assert len(active) == payload["content_design"]["active"]
    assert payload["content_design"]["total_design_items"] == (
        payload["content_design"]["active"] + payload["content_design"]["resolved"])
    assert payload["overlay_changed_by_recompute"] is False
    assert payload["overlay"]["resolved_total"] >= 77
    assert payload["overlay_subtypes"]["repaired_micro_semantic"] >= 21


def test_author_action_inventory_dedup(closeout) -> None:
    service, payload = closeout
    inventory = json.loads((service.design_dir /
                            "AUTHOR_ACTION_INVENTORY.json").read_text(
        encoding="utf-8"))
    assert inventory["item_count"] == sum(inventory["group_counts"].values())
    assert list(inventory["group_counts"]) == list(AUTHOR_ACTION_GROUPS)
    assert inventory["dedup"]["invariant_ok"] is True
    assert inventory["dedup"]["violations"] == []
    seen: set[tuple[str, str]] = set()
    for row in inventory["items"]:
        for label in row["legacy_labels"]:
            key = (row["group"], label)
            assert key not in seen, f"duplicate author action {key}"
            seen.add(key)
        assert row["author_input_needed"] is True and row["resolved"] is False
    assert inventory["unresolved"] is True and inventory["auto_resolved"] == 0
    assert inventory["policy_selection"]["status"] == "PENDING_AUTHOR_SELECTION"
    assert inventory["policy_selection"]["auto_selected"] == ""
    assert inventory["policy_selection"]["author_selected"] == ""
    assert payload["author_inventory"]["item_count"] == inventory["item_count"]
    labels = {label for row in inventory["items"] for label in row["legacy_labels"]}
    for label in ("ch012", "ch036", "ch056", "ch063", "ch081", "ch083", "ch085",
                  "ch087", "ch088", "ch559"):
        if label in ("ch081", "ch083", "ch085", "ch087", "ch088"):
            report_records("P15P", "ch081/083/085/087/088")
            queue = json.loads((service.design_dir / "M11_CONTENT_DESIGN_QUEUE_V3.json")
                               .read_text(encoding="utf-8"))
            row = next(r for r in queue["requirements"] if r["legacy_label"] == label)
            assert row["status"] == "RESOLVED_REPAIRED"
        else:
            assert label in labels


def test_entity_manual_inventory(closeout) -> None:
    service, payload = closeout
    inventory = _artifact(service, "M11_ENTITY_MANUAL_INVENTORY.json")
    entity = inventory["entity"]
    assert entity["cluster_count"] == 47
    assert entity["context_resolvable_cluster_count"] == 13
    assert entity["status_counts"]["CONTEXT_RESOLVABLE_PROPOSAL"] == 13
    assert {row["legacy_label"] for row in entity["specific_pending_items"]} == {
        "ch093", "ch120"}
    assert entity["entity_truth_modified"] is False
    manual = inventory["manual"]
    assert manual["item_count"] == 2
    assert {row["legacy_label"] for row in manual["items"]} == {"ch063", "ch143"}
    assert inventory["resolved_in_this_phase"] == 0
    assert inventory["new_entity_pilot"] is False
    assert payload["entity_manual"] == {"entity_items": 13, "manual_items": 2}


def test_production_backlog_lane_coverage(closeout) -> None:
    service, payload = closeout
    backlog = json.loads((service.design_dir /
                          "M11_PRODUCTION_BACKLOG.json").read_text(
        encoding="utf-8"))
    assert set(backlog["lane_counts"]) == set(BACKLOG_LANES)
    assert all(count >= 1 for count in backlog["lane_counts"].values())
    assert backlog["item_count"] == sum(backlog["lane_counts"].values())
    required = ("item_id", "lane", "target_ids", "blocking_batches", "priority",
                "dependencies", "required_actor", "next_action",
                "current_artifact_ref")
    for row in backlog["items"]:
        for field in required:
            assert field in row, field
        assert row["lane"] in BACKLOG_LANES
        assert isinstance(row["priority"], int) and row["priority"] >= 1
        assert row["next_action"] and row["required_actor"]
    assert backlog["execution_mode"].startswith("M11 Production Execution")
    assert "P15q" in backlog["p15_forbidden_successors"]
    assert payload["backlog"]["item_count"] == backlog["item_count"]


def test_capability_matrix_complete(closeout) -> None:
    service, payload = closeout
    matrix = _artifact(service, "P15_CAPABILITY_ACCEPTANCE_MATRIX.json")
    assert matrix["capability_count"] == len(CAPABILITIES) == 21
    assert [row["capability"] for row in matrix["capabilities"]] == list(CAPABILITIES)
    verdicts = {row["capability"]: row["verdict"] for row in matrix["capabilities"]}
    assert all(value in ("PROVEN", "PARTIAL", "NOT_PROVEN", "DEFERRED")
               for value in verdicts.values())
    assert verdicts["Field Rebind"] == "NOT_PROVEN"
    assert verdicts["Entity Blocking"] == "PARTIAL"
    assert verdicts["Manual Blocking"] == "PARTIAL"
    assert sum(matrix["verdict_counts"].values()) == 21
    assert payload["capabilities"] == matrix["verdict_counts"]


def test_batch_matrix_and_m11_status(closeout) -> None:
    service, payload = closeout
    batches = _artifact(service, "P15_BATCH_STATUS_MATRIX.json")
    assert batches["batch_count"] == 17
    assert {row["batch_id"] for row in batches["batches"]} == {
        f"REPAIR_BATCH_{index:02d}" for index in range(1, 18)}
    for row in batches["batches"]:
        assert row["completion_status"] in ("NOT_STARTED", "IN_PROGRESS",
                                            "COMPLETE", "HUMAN_REVIEW")
        assert row["execution_status"] in ("READY", "PARTIAL_READY", "BLOCKED",
                                           "NO_WORK", "COMPLETE")
        assert row["resolved"] + row["ready"] + row["blocked"] >= 1
        assert row["ready"] + row["blocked"] <= 40
    # P15p 时点存在 executable frontier；M11-RUN-12 完成 AUTO_SAFE sweep 后
    # 17 batch 全部 BLOCKED（executable_batches 允许为空），但 live 投影必须一致。
    assert isinstance(batches["executable_batches"], list)
    assert batches["executable_batches"] == [
        row["batch_id"] for row in batches["batches"]
        if row["execution_status"] in ("READY", "PARTIAL_READY")]
    if batches["executable_batches"]:
        assert batches["next_ready_batch"] in batches["executable_batches"]
    else:
        assert batches["next_ready_batch"] == ""
    # P15p 之后 M11 Production Execution（M11-RUN-01）会继续推进 projection：
    # 该矩阵是 live projection，因此与最新 readiness V2 保持一致，而不是冻结在 P15p 时点。
    live_readiness = json.loads((service.design_dir /
                                 "M11_READINESS_V2.json").read_text(encoding="utf-8"))
    live = {row["batch_id"]: row for row in live_readiness["batches"]}
    for batch_id in ("REPAIR_BATCH_04", "REPAIR_BATCH_06"):
        highlighted = batches["highlighted"][batch_id]
        assert highlighted["execution_status"] == live[batch_id]["execution_status"]
        assert highlighted["resolved"] == len(live[batch_id]["resolved_target_ids"])
        assert highlighted["ready"] == len(live[batch_id]["ready_target_ids"])
        assert highlighted["blocked"] == len(live[batch_id]["blocked_target_ids"])
    assert batches["highlighted"]["REPAIR_BATCH_04"]["execution_status"] in (
        "READY", "PARTIAL_READY", "BLOCKED", "NO_WORK", "COMPLETE")
    assert batches["batch_executed_in_this_phase"] is False
    status = _artifact(service, "P15_STATUS_MATRIX.json")
    assert status["status_matrix"] == P15_STATUS_MATRIX
    assert status["status_matrix"]["P15_REPAIR_SYSTEM_BUILD"] == "COMPLETE"
    assert status["status_matrix"]["M11_REPAIR_EXECUTION"] == "IN_PROGRESS"
    assert status["status_matrix"]["M11_AUTHOR_POLICY"] == "PENDING_AUTHOR_SELECTION"
    assert status["m11_overall"] == "IN_PROGRESS"
    assert "P15q" in status["forbidden_successors"]
    assert payload["repair_executed"] is False
    assert payload["batch_06_executed"] is False
    assert payload["author_policy_selected"] is False


def test_closeout_matrix_and_derived_blockers(closeout) -> None:
    service, _payload = closeout
    matrix = _artifact(service, "P15_CLOSEOUT_MATRIX.json")
    assert matrix["total"] == TARGET_COUNT and matrix["exact_conservation"] is True
    assert matrix["resolved_repaired"] >= 62
    assert matrix["resolved_no_repair_required"] >= 15
    report_records("P15O", "**40 → 29**")
    assert matrix["content_design_required"] == closed(29, 0)
    assert set(matrix["derived_blockers"]) == {"content", "entity", "author",
                                              "manual", "confirmed_binding"}
    assert matrix["derived_blockers"]["content"] >= matrix["content_design_required"]
    assert sum(matrix["derived_blockers"].values()) == matrix[
        "blocked_occurrence_count"]
    assert matrix["blocked_occurrence_count"] >= matrix["blocked_target_count"]


def test_roadmap_documents_frozen_m11_in_progress() -> None:
    milestones = (ROOT / "docs/NOVELFORGE_PRODUCT_V2_MILESTONES.md").read_text(
        encoding="utf-8")
    audit = (ROOT / "docs/NOVELFORGE_PRODUCT_V2_PROGRESS_AUDIT.md").read_text(
        encoding="utf-8")
    master = (ROOT / "docs/NOVELFORGE_PRODUCT_V2_MASTER_PLAN.md").read_text(
        encoding="utf-8")
    for text in (milestones, audit, master):
        assert "P15" in text
        assert "M11" in text
        assert "Production Execution" in text
        # The P15-era status belongs to its frozen closeout, not the evolving roadmap.
        report_records("P15P", "M11 = IN_PROGRESS", "P15_REPAIR_SYSTEM_BUILD = COMPLETE")
    assert "P15 Repair System Build" in milestones
    acceptance = json.loads((ROOT / "workspace/wasteland_001_exports/repair_adoption_v1/"
                             "M11_FINAL_ACCEPTANCE.json").read_text(encoding="utf-8"))
    if acceptance["status"] == "PASS":
        assert "M11 = COMPLETE" in milestones
        assert "M11 = COMPLETE" in master
    else:
        assert acceptance["status"] == "CONDITIONAL_PENDING_REGRESSION"
    assert (ROOT / "docs/NOVELFORGE_P15_REPAIR_SYSTEM_FINAL_CLOSEOUT.md").is_file()


def test_m12_entry_criteria_projection_and_gate(closeout) -> None:
    service, payload = closeout
    criteria = _artifact(service, "M12_ENTRY_CRITERIA.json")
    assert criteria["criteria_count"] == len(M12_ENTRY_CRITERIA)
    assert criteria["m12_entry_allowed"] is False
    # §12：entry_allowed = false ≠ 9 项全部未满足 → satisfied / unsatisfied / blocking 必须分开
    assert criteria["satisfied_count"] == len(criteria["satisfied_criteria"])
    assert criteria["unsatisfied_count"] == len(criteria["unsatisfied_criteria"])
    assert criteria["blocking_count"] == len(criteria["blocking_criteria"])
    assert criteria["satisfied_count"] + criteria["unsatisfied_count"] == len(
        M12_ENTRY_CRITERIA)
    assert criteria["satisfied_count"] >= 4
    assert set(criteria["blocking_criteria"]) <= set(criteria["unsatisfied_criteria"])
    assert not set(criteria["satisfied_criteria"]) & set(criteria["unsatisfied_criteria"])
    assert criteria["blocking_count"] >= 1
    for row in criteria["criteria"]:
        assert isinstance(row["satisfied"], bool)
        assert isinstance(row["blocking"], bool)
        if row["satisfied"]:
            assert row["blocking"] is False
        assert row["current_state"]
    assert payload["m12"]["satisfied_count"] == criteria["satisfied_count"]
    assert payload["m12"]["entry_allowed"] is False


def test_truth_digests_and_closeout_gate(closeout) -> None:
    service, payload = closeout
    gate = _artifact(service, "P15_FINAL_CLOSEOUT_GATE.json")
    assert gate["source_digests"]["canon"] == FROZEN_SOURCE_DIGESTS["canon"]
    assert gate["source_digests"]["story_state"] == FROZEN_SOURCE_DIGESTS[
        "story_state"]
    assert gate["source_digests"]["legacy"] == FROZEN_SOURCE_DIGESTS["legacy"]
    assert gate["source_digests"]["chapter_ir"] == FROZEN_SOURCE_DIGESTS[
        "chapter_ir"]
    for name, digest in FROZEN_FOUNDATION_DIGESTS.items():
        assert gate["foundation_digests"][name] == digest
    retired = {"rewrite_proposal_model_proven", "decision_causal_separation_proven"}
    report_records("P15O", "CONCRETE_EVENT_SPECIFICITY_REQUIRED` 5/5 PASS",
                   "**DECISION 3**", "**CAUSAL_BRIDGE 2**")
    for key in ("canon_unchanged", "story_state_unchanged", "legacy_unchanged",
                "source_ir_unchanged", "historical_foundation_unchanged",
                "primary_conservation_372_exact", "overlay_v2_conserved",
                "content_queue_conserved", "zero_event_micro_exhausted",
                "micro_scale_proven", "rewrite_proposal_model_proven",
                "decision_causal_separation_proven",
                "author_policy_pending_explicit",
                "author_action_inventory_complete",
                "production_backlog_complete", "approval_boundary_frozen",
                "truth_precedence_frozen", "readiness_v2_frozen",
                "foundation_ready", "repair_substrate_adopted"):
        assert gate["checks"][key] is (closed(True, False) if key in retired else True), key
    assert gate["status"] == closed("PASS", "NEEDS_ATTENTION")
    assert set(gate["failed_checks"]) == retired
    assert gate["batch_executed_in_this_phase"] is False
    assert gate["author_decisions_resolved_in_this_phase"] == 0
    # Regression evidence cannot recreate the retired proposal surface.
    replay = service.closeout_gate(
        overlay=json.loads((service.design_dir / "M11_OVERLAY_V2.json").read_text(
            encoding="utf-8")),
        readiness=json.loads((service.design_dir /
                              "M11_READINESS_V2.json").read_text(encoding="utf-8")),
        contract=json.loads((service.design_dir /
                             "M11_REPAIR_SYSTEM_CONTRACT_V1.json").read_text(
            encoding="utf-8")),
        reconciliation=json.loads((service.design_dir /
                                   "p15n/CONTENT_DESIGN_QUEUE_RECONCILIATION.json"
                                   ).read_text(encoding="utf-8")),
        reclassification=json.loads((service.design_dir /
                                     "p15n/CONTENT_REPAIR_RECLASSIFICATION.json"
                                     ).read_text(encoding="utf-8")),
        matrix=_artifact(service, "P15_CLOSEOUT_MATRIX.json"),
        capabilities=_artifact(service, "P15_CAPABILITY_ACCEPTANCE_MATRIX.json"),
        author_inventory=json.loads((service.design_dir /
                                     "AUTHOR_ACTION_INVENTORY.json").read_text(
            encoding="utf-8")),
        backlog=json.loads((service.design_dir /
                            "M11_PRODUCTION_BACKLOG.json").read_text(
            encoding="utf-8")),
        entity_manual=_artifact(service, "M11_ENTITY_MANUAL_INVENTORY.json"),
        evidence={"pytest": {"status": "PASS", "summary": "injected"},
                  "validate_project": {"status": "PASS", "summary": "injected"}})
    assert replay["status"] == closed("PASS", "NEEDS_ATTENTION")
    assert set(replay["failed_checks"]) == retired
    assert payload["closeout_gate"]["check_count"] == 22
