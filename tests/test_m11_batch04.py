"""P15i：REPAIR_BATCH_04 hardened READY targets 执行 + readiness closeout 回归。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from novelforge.story_engine.m11_batch04 import Batch04Service
from novelforge.story_engine.repair import (
    RepairPreflightError,
    WastelandRepairService,
)

ROOT = Path(".").resolve()
REPAIR_DIR = ROOT / "workspace/wasteland_001_exports/repair_v1"


@pytest.fixture(scope="module")
def batch04():
    service = Batch04Service(ROOT)
    payload = service.run()
    return service, payload


def _artifact(service: Batch04Service, name: str):
    return json.loads((service.design_dir / name).read_text(encoding="utf-8"))


def test_batch04_uses_hardened_ready_scope(batch04) -> None:
    service, payload = batch04
    scope = _artifact(service, "BATCH_04_EXECUTION_SCOPE.json")
    assert scope["frozen"] is True
    assert len(scope["ready_target_ids"]) == 18
    assert len(scope["blocked_target_ids"]) == 6
    assert payload["execution"]["ready"] == 18 and payload["execution"]["blocked"] == 6
    # scope 之外的 batch target 不得进入 execution
    repair = WastelandRepairService(ROOT, batch_id="REPAIR_BATCH_04",
                                    target_scope=scope["ready_target_ids"])
    inputs = repair.load()
    assert repair.execution_targets(inputs) == scope["ready_target_ids"]
    with pytest.raises(RepairPreflightError):
        WastelandRepairService(ROOT, batch_id="REPAIR_BATCH_04",
                               target_scope=["uuid_not_in_batch"]).execution_targets(
            inputs)


def test_blocked_content_design_target_cannot_execute(batch04) -> None:
    service, payload = batch04
    scope = _artifact(service, "BATCH_04_EXECUTION_SCOPE.json")
    gate = _artifact(service, "P15I_GATE.json")
    assert gate["checks"]["blocked_targets_not_modified"] is True
    candidates = json.loads((REPAIR_DIR / "BATCH_04_CANDIDATES.json")
                            .read_text(encoding="utf-8"))
    rows = candidates["candidates"] if isinstance(candidates, dict) else candidates
    executed = {row["chapter_id"] for row in rows}
    assert not (executed & set(scope["blocked_target_ids"]))
    closeout = json.loads((REPAIR_DIR / "BATCH_04_CLOSEOUT.json")
                          .read_text(encoding="utf-8"))
    assert closeout["status_counts"]["blocked"] == 6
    _ = payload


def test_blocker_provenance_path(batch04) -> None:
    service, payload = batch04
    provenance = _artifact(service, "BATCH_04_BLOCKER_PROVENANCE.json")
    assert provenance["blocked_count"] == 6
    assert provenance["direct_blocker_histogram"] == {"ch067": 6, "ch068": 6, "ch069": 6}
    for row in provenance["rows"]:
        assert row["blocker_type"] == "BLOCKED_CONTENT_DESIGN"
        assert row["direct_blocker_chapter"] == ["ch067", "ch068", "ch069"]
        assert row["design_item_ids"] == ["CDQ_ch067", "CDQ_ch068", "CDQ_ch069"]
        assert row["dependency_path"][0] == row["legacy_label"]
    assert payload["blocker_provenance"]["author_decision_impact"] == {"ch036": 0,
                                                                      "ch559": 0}
    assert payload["blocker_provenance"]["manual_impact"] == {"ch063": 0}


def test_ch056_ch063_are_not_batch04_blockers(batch04) -> None:
    service, payload = batch04
    provenance = _artifact(service, "BATCH_04_BLOCKER_PROVENANCE.json")
    histogram = provenance["direct_blocker_histogram"]
    assert "ch056" not in histogram and "ch063" not in histogram
    assert histogram.get("ch056", 0) == 0 and histogram.get("ch063", 0) == 0
    pack = (ROOT / "docs/WASTELAND_001_M11_AUTHOR_DECISION_PACK.md") \
        .read_text(encoding="utf-8")
    assert "ch067 / ch068 / ch069" in pack
    assert "ch056 + ch063" not in pack
    _ = payload


def test_micro_manifest_validation_only(batch04) -> None:
    service, payload = batch04
    manifest = _artifact(service, "M11_MICRO_APPROVAL_MANIFEST.json")
    assert manifest["item_count"] == 34
    assert manifest["grade_counts"] == {"RECOMMENDED": 34, "ACCEPTABLE": 68,
                                        "REJECTED": 0}
    assert manifest["auto_approved"] is False and manifest["content_generated"] is False
    assert manifest["no_literary_score"] is True
    for item in manifest["items"]:
        assert item["approval_required"] is True
        assert item["recommended_proposal_id"]
        assert len(item["alternate_proposal_ids"]) == 2
        assert item["non_authoritative"] is True
        grades = [row["grade"] for row in item["ranked"]]
        assert grades[0] == "RECOMMENDED"
    assert payload["micro_manifest"]["grades"]["REJECTED"] == 0


def test_micro_proposals_cannot_promote(batch04) -> None:
    service, _payload = batch04
    proposals = _artifact(service, "MICRO_REPAIR_DESIGN_PROPOSALS.json")
    assert all(row["writes_ir"] is False and row["status"] == "PROPOSED"
               for row in proposals["proposals"])
    reconciliation = _artifact(service, "BATCH_04_RECONCILIATION.json")
    promoted = [row for row in reconciliation["records"]
                if row["new_resolution_status"] in ("RESOLVED_REPAIRED",
                                                    "RESOLVED_NO_REPAIR_REQUIRED")]
    assert promoted and all(row["design_item_id"] == "" for row in promoted)


def test_full_ir_required_and_partial_entity_gate(batch04) -> None:
    service, payload = batch04
    candidates = json.loads((REPAIR_DIR / "BATCH_04_CANDIDATES.json")
                            .read_text(encoding="utf-8"))
    rows = candidates["candidates"] if isinstance(candidates, dict) else candidates
    substrates = {row["evidence_substrate"] for row in rows}
    assert substrates <= {"HISTORICAL_FULL_IR", "HISTORICAL_FULL_IR_PARTIAL"}
    assert "SHADOW_FALLBACK" not in substrates
    partial = [row for row in rows
               if row["evidence_substrate"] == "HISTORICAL_FULL_IR_PARTIAL"]
    assert partial and all(row["status"] != "candidate_ready" for row in partial)
    assert payload["execution"]["human_review"] == 8


def test_confirmed_binding_priority_and_grid(batch04) -> None:
    service, _payload = batch04
    gate = _artifact(service, "P15I_GATE.json")
    assert gate["checks"]["confirmed_binding_guard_zero_violations"] is True
    assert gate["checks"]["entity_exact_binding_violations_zero"] is True
    batch_gate = json.loads((REPAIR_DIR / "BATCH_04_GATE.json")
                            .read_text(encoding="utf-8"))
    assert batch_gate["checks"]["confirmed_historical_binding_guard"] is True
    assert not [item for item in batch_gate["findings"]
                if item["code"] == "CONFIRMED_HISTORICAL_BINDING_VIOLATION"]
    overrides = _artifact(service, "CONFIRMED_BINDING_RESOLUTION.json")
    assert overrides["override_chapter_count"] == 9
    for row in overrides["resolutions"]:
        assert row["status"] == "CONFIRMED_OVERRIDE_ACTIVE"


def test_dynamic_ready_to_blocked_downgrade(batch04) -> None:
    service, _payload = batch04
    reconciliation = _artifact(service, "BATCH_04_RECONCILIATION.json")
    downgraded = [row for row in reconciliation["records"]
                  if row["new_resolution_status"] in ("CONTENT_DESIGN_REQUIRED",
                                                      "EVIDENCE_READY")
                  and row["old_status"] == "not_processed"]
    assert len(downgraded) == 8
    design = [row for row in downgraded
              if row["new_resolution_status"] == "CONTENT_DESIGN_REQUIRED"]
    assert len(design) == 7 and all(row["design_item_id"].startswith("CDQ_B04_")
                                    for row in design)
    entity = [row for row in downgraded
              if row["new_resolution_status"] == "EVIDENCE_READY"]
    assert len(entity) == 1
    assert reconciliation["auto_discovered_design_items"]


def test_partial_promotion_and_overlay(batch04) -> None:
    service, payload = batch04
    overlay = json.loads((REPAIR_DIR / "M11_OVERLAY.json").read_text(encoding="utf-8"))
    assert overlay["resolved_total"] == 35
    assert overlay["repaired"] == 24 and overlay["no_repair_required"] == 11
    assert overlay["evidence_ready"] == 2 and overlay["manual_required"] == 1
    assert overlay["content_design_required"] == 43 and overlay["author_decision"] == 1
    assert overlay["blocked"] == 6 and overlay["pending"] == 284
    assert overlay["baseline_queue_counts"] == {"SEMANTIC_CONFIRMED": 198,
                                               "LEGACY_FIELD_CONFLICT": 27,
                                               "LEGACY_CONTENT_GAP": 345}
    assert overlay["resolved_total"] + overlay["evidence_ready"] + \
        overlay["manual_required"] + overlay["content_design_required"] + \
        overlay["author_decision"] + overlay["blocked"] + overlay["pending"] == 372
    assert payload["execution"]["promotion_mode"] == "partial"
    diff = json.loads((REPAIR_DIR / "BATCH_04_DIFF.json").read_text(encoding="utf-8"))
    assert diff["semantic_elements_added"] == 0 and diff["confirmed_facts_changed"] == 0
    assert diff["read_only_chapters_changed"] == 0


def test_readiness_recompute_and_batch05(batch04) -> None:
    service, payload = batch04
    readiness = _artifact(service, "M11_READINESS_HARDENED.json")
    assert len(readiness["batches"]) == 17
    batch_04 = next(row for row in readiness["batches"]
                    if row["batch_id"] == "REPAIR_BATCH_04")
    assert batch_04["status"] == "PARTIAL_READY"
    assert len(batch_04["blocked_target_ids"]) == 13
    assert batch_04["blocker_counts"] == {"BLOCKED_CONTENT_DESIGN": 12,
                                         "BLOCKED_ENTITY_AMBIGUITY": 1}
    batch_05 = next(row for row in readiness["batches"]
                    if row["batch_id"] == "REPAIR_BATCH_05")
    assert batch_05["status"] == "PARTIAL_READY"
    assert len(batch_05["ready_target_ids"]) == 26
    assert payload["readiness"]["batch_05"] == "PARTIAL_READY"
    report = json.loads((REPAIR_DIR / "M11_READINESS_REPORT.json")
                        .read_text(encoding="utf-8"))
    assert report["after_batch_04"] is True


def test_p15i_gate_pass_and_truth_unchanged(batch04) -> None:
    service, payload = batch04
    gate = _artifact(service, "P15I_GATE.json")
    assert gate["status"] == "PASS"
    assert all(gate["checks"].values()), [k for k, v in gate["checks"].items() if not v]
    for key in ("canon", "story_state", "legacy", "chapter_ir", "foundation_index"):
        assert gate["digests_before"][key] == gate["digests_after"][key]
    assert gate["batch_05_executed"] is False
    assert gate["content_design_executed"] is False
    assert payload["status"] == "PASS"
    assert payload["batch_05_executed"] is False
    assert payload["content_design_executed"] is False
