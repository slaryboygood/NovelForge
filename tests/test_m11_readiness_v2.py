"""P15j：readiness 语义（completion / execution 分离）+ CDQ 并入 + overlay V2 回归。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from novelforge.story_engine.m11_readiness import (
    ReadinessV2Service,
    completion_status_for,
    execution_status_for,
)

from m11_phase_history import closed

ROOT = Path(".").resolve()


@pytest.fixture(scope="module")
def readiness():
    service = ReadinessV2Service(ROOT)
    payload = service.run()
    return service, payload


def _artifact(service: ReadinessV2Service, name: str):
    return json.loads((service.design_dir / name).read_text(encoding="utf-8"))


def test_execution_status_rules() -> None:
    assert execution_status_for(ready_count=26, blocked_count=0,
                                completion_status="IN_PROGRESS") == "READY"
    assert execution_status_for(ready_count=18, blocked_count=6,
                                completion_status="IN_PROGRESS") == "PARTIAL_READY"
    assert execution_status_for(ready_count=0, blocked_count=14,
                                completion_status="IN_PROGRESS") == "BLOCKED"
    assert execution_status_for(ready_count=0, blocked_count=0,
                                completion_status="NOT_STARTED") == "NO_WORK"
    assert execution_status_for(ready_count=0, blocked_count=0,
                                completion_status="COMPLETE") == "COMPLETE"


def test_completion_status_independent_from_execution() -> None:
    assert completion_status_for(resolved_count=26, ready_count=0, blocked_count=0,
                                 total=26) == "COMPLETE"
    assert completion_status_for(resolved_count=17, ready_count=0, blocked_count=9,
                                 total=26) == "IN_PROGRESS"
    assert completion_status_for(resolved_count=0, ready_count=0, blocked_count=20,
                                 total=20) == "HUMAN_REVIEW"
    assert completion_status_for(resolved_count=0, ready_count=0, blocked_count=0,
                                 total=24) == "NOT_STARTED"
    # 同一个 execution_status 可以对应不同 completion_status（语义已分离）
    assert execution_status_for(ready_count=0, blocked_count=9,
                                completion_status="IN_PROGRESS") == "BLOCKED"
    assert execution_status_for(ready_count=0, blocked_count=9,
                                completion_status="HUMAN_REVIEW") == "BLOCKED"


def test_readiness_v2_all_batches_have_both_statuses(readiness) -> None:
    service, payload = readiness
    v2 = _artifact(service, "M11_READINESS_V2.json")
    assert v2["batch_count"] == 17
    for row in v2["batches"]:
        assert row["completion_status"] in ("NOT_STARTED", "IN_PROGRESS", "COMPLETE",
                                            "HUMAN_REVIEW")
        assert row["execution_status"] in ("READY", "PARTIAL_READY", "BLOCKED",
                                           "NO_WORK", "COMPLETE")
        assert len(row["resolved_target_ids"]) + len(row["ready_target_ids"]) + \
            len(row["blocked_target_ids"]) == row["mutable_target_count"]
    assert set(payload["completion_status_counts"]) <= {
        "NOT_STARTED", "IN_PROGRESS", "COMPLETE", "HUMAN_REVIEW"}
    assert set(payload["execution_status_counts"]) <= {
        "READY", "PARTIAL_READY", "BLOCKED", "NO_WORK", "COMPLETE"}


def test_batch05_was_ready_26_0_before_execution(readiness) -> None:
    service, _payload = readiness
    scope = _artifact(service, "BATCH_05_EXECUTION_SCOPE.json")
    assert scope["frozen"] is True
    assert len(scope["ready_target_ids"]) == 26
    assert scope["blocked_target_ids"] == []
    closure = _artifact(service, "REPAIR_BATCH_05_DEPENDENCY_CLOSURE.json")
    if closure.get("ready_count") != 26:
        closure = _artifact(service,
                            "REPAIR_BATCH_05_DEPENDENCY_CLOSURE_PRE_EXECUTION.json")
    assert closure["ready_count"] == 26 and closure["blocked_count"] == 0
    assert closure["hard_rule"]


def test_batch04_residual_false_ready_fixed(readiness) -> None:
    service, payload = readiness
    residual = _artifact(service, "BATCH04_RESIDUAL_READY_PROVENANCE.json")
    assert residual["ready_target_count"] == 1
    row = residual["provenance"][0]
    assert row["legacy_label"] == "ch081"
    assert row["previous_status"] == "CONTENT_DESIGN_REQUIRED"
    assert row["involves"]["content_design"] is True
    assert residual["executed"] is False
    assert residual["readiness_projection_fixed"] is True
    assert row["v2_disposition"] == closed("BLOCKED", "RESOLVED")
    assert payload["batch_04_residual"] == 1


def test_dynamic_cdq_integration_dedup(readiness) -> None:
    service, payload = readiness
    integration = _artifact(service, "M11_DYNAMIC_CDQ_INTEGRATION.json")
    assert integration["dynamic_candidate_count"] == 7
    # 幂等：7 个 B04 dynamic item 在首次 integration 后已在 queue V2 里 →
    # 重跑必须识别为 duplicate（不得重复登记，也不得从快照重建丢掉生产轮次新增项）。
    assert integration["new_item_count"] + integration["duplicate_count"] == 7
    assert integration["merged_item_count"] == (
        integration["existing_item_count"] + integration["new_item_count"])
    assert integration["content_generated"] is False
    assert integration["proposals_generated"] is False
    for row in integration["new_items"]:
        assert row["design_item_id"].startswith("CDQ_B04_")
        assert row["status"] == "PENDING_DESIGN"
    queue = _artifact(service, "M11_CONTENT_DESIGN_QUEUE_V2.json")
    assert queue["item_count"] == integration["merged_item_count"]
    queue_ids = {str(row["design_item_id"]) for row in queue["items"]}
    assert {f"CDQ_B04_{label}" for label in
            ("ch081", "ch082", "ch083", "ch084", "ch085", "ch087",
             "ch088")} <= queue_ids
    # M11-RUN-02 登记的 runtime ContentDesignRequirement 必须保留（不被快照重建清掉）
    assert {f"CDQ_RUN02_{label}" for label in
            ("ch198", "ch207", "ch210", "ch215", "ch218")} <= queue_ids
    requirements = _artifact(service, "REPAIR_DESIGN_REQUIREMENTS_V2.json")
    assert requirements["requirement_count"] == (
        36 + len(integration["new_requirements"]))
    assert requirements["requirement_count"] >= 36
    assert payload["cdq_integration"]["new"] == integration["new_item_count"]


def test_overlay_v2_primary_conservation(readiness) -> None:
    service, payload = readiness
    overlay = _artifact(service, "M11_OVERLAY_V2.json")
    primary = overlay["primary_resolution_status_counts"]
    assert sum(primary.values()) == 372
    assert overlay["conservation"] == {"primary_total": 372, "target_count": 372,
                                      "exact": True}
    assert overlay["resolved_total"] == primary["resolved_repaired"] + \
        primary["resolved_no_repair_required"]
    assert overlay["blocked"] == sum(overlay["execution_blocker_counts"].values())
    assert overlay["blocked_target_count"] <= 372
    assert overlay["baseline_queue_counts"] == {"SEMANTIC_CONFIRMED": 198,
                                               "LEGACY_FIELD_CONFLICT": 27,
                                               "LEGACY_CONTENT_GAP": 345}
    assert "不参与 372 primary 守恒" in overlay["blocked_semantics"]
    for key in ("resolved_total", "repaired", "no_repair_required", "evidence_ready",
                "manual_required", "content_design_required", "author_decision",
                "entity_ambiguity", "confirmed_binding_blocked", "pending", "blocked"):
        assert key in overlay
    assert payload["overlay"]["resolved_total"] == overlay["resolved_total"]


def test_dependency_closure_unresolved_upstream_blocks(readiness) -> None:
    service, _payload = readiness
    v2 = _artifact(service, "M11_READINESS_V2.json")
    for row in v2["batches"]:
        for chapter_id, reason in row["block_reason_by_target"].items():
            assert reason.startswith("blocked:")
            assert chapter_id not in row["ready_target_ids"]
    # 无依赖未决的 target 仍可 ready（localized blocking）
    ready_batches = [row for row in v2["batches"] if row["ready_target_ids"]]
    assert ready_batches
    for row in ready_batches:
        assert not (set(row["ready_target_ids"]) & set(row["blocked_target_ids"]))
