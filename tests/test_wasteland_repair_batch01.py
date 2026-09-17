"""M11：REPAIR_BATCH_01 Production Pilot 回归（只修 representation / evidence）。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from novelforge.story_engine.repair import (
    CONFIRMED,
    DEFAULT_BATCH,
    RepairPreflightError,
    WastelandRepairService,
)

ROOT = Path(".").resolve()


def _service(tmp_path: Path, batch_id: str = DEFAULT_BATCH) -> WastelandRepairService:
    return WastelandRepairService(
        ROOT, batch_id=batch_id,
        repair_dir=str(tmp_path / f"repair_{batch_id}"))


def _artifact(service: WastelandRepairService, name: str):
    return json.loads((service.repair_dir / name).read_text(encoding="utf-8"))


def test_preflight_requires_ready_batch_and_approval(tmp_path: Path) -> None:
    service = _service(tmp_path)
    inputs = service.load()
    checks = service.preflight(inputs)
    assert all(checks.values()) and checks["readiness_ready"] is True
    batch = service.batch(inputs)
    assert len(batch["arc_refs"]) == 3 and len(batch["chapter_ids"]) == 23
    assert len(batch["read_only_dependency_chapter_ids"]) == 6
    with pytest.raises(RepairPreflightError) as not_ready:
        _service(tmp_path, "REPAIR_BATCH_02").preflight(
            _service(tmp_path, "REPAIR_BATCH_02").load())
    assert not_ready.value.code == "REPAIR_BATCH_NOT_READY"
    with pytest.raises(RepairPreflightError) as approval:
        service.run(approved=False)
    assert approval.value.code == "REPAIR_PROMOTION_NOT_APPROVED"


def test_baseline_lock_matches_m10_plan(tmp_path: Path) -> None:
    service = _service(tmp_path)
    inputs = service.load()
    baseline = service.baseline_lock(inputs)
    batch = service.batch(inputs)
    assert baseline.batch_id == DEFAULT_BATCH
    assert baseline.mutable_chapter_ids == batch["chapter_ids"]
    assert baseline.read_only_dependency_chapter_ids \
        == batch["read_only_dependency_chapter_ids"]
    assert baseline.target_alignment_digest == batch["target_alignment_digest"]
    assert baseline.confirmed_facts_digest == batch["confirmed_facts_digest"]
    assert all(len(item) == 16 for item in baseline.happened_digests().values())
    assert baseline.queue_snapshot == {CONFIRMED: 198, "LEGACY_FIELD_CONFLICT": 27,
                                       "LEGACY_CONTENT_GAP": 345}


def test_candidates_only_touch_mutable_targets(tmp_path: Path) -> None:
    service = _service(tmp_path)
    inputs = service.load()
    candidates, sampling = service.build_candidates(inputs)
    mutable = set(service.batch(inputs)["chapter_ids"])
    read_only = set(service.batch(inputs)["read_only_dependency_chapter_ids"])
    assert {row.chapter_id for row in candidates} == mutable
    assert not {row.chapter_id for row in candidates} & read_only
    for row in candidates:
        assert row.batch_id == DEFAULT_BATCH and row.non_authoritative is True
        assert row.status in ("candidate_ready", "human_review", "blocked")
        assert row.forbidden_changes or row.required_context
        if row.status == "candidate_ready":
            allowed = [str(item) for item in
                       (inputs.targets[row.chapter_id]["allowed_repair_types"])]
            assert row.proposed_patch
            assert all(op.policy_approved or service.op_allowed(op, allowed)
                       for op in row.proposed_patch)
            assert row.evidence_refs
            assert row.refinement is not None
            assert row.refinement.execution_decision in ("SAFE_AUTO", "MANUAL")
            assert row.validator_results["forbidden_change_diff"] == "PASS"
        else:
            assert row.human_review_required is True
    assert set(sampling.per_chapter) == mutable


def test_classification_sampling_flags_blanket_tagging(tmp_path: Path) -> None:
    service = _service(tmp_path)
    inputs = service.load()
    candidates, sampling = service.build_candidates(inputs)
    total = (sampling.evidence_only + sampling.na_correction + sampling.semantic_addition
             + sampling.state_rebinding + sampling.human_review)
    assert total == len(candidates) == 23
    # P15g：full IR substrate 下"缺 pivot"不再停在 SOURCE_IR_INSUFFICIENT/HUMAN_DECISION，
    # 而是正式落到 SEMANTIC_ADDITION_REQUIRED（内容缺口，manual-only，不自动补语义）
    assert sampling.semantic_addition == 15
    assert sampling.human_review == 0
    assert all(row.refinement.actual_semantic_status == "TRULY_MISSING"
               for row in candidates
               if row.refinement.actual_repair_class == "SEMANTIC_ADDITION_REQUIRED")
    assert sampling.evidence_only == 5 and sampling.na_correction == 3
    assert sampling.multi_label_blanket_suspected is True
    assert "M10 baseline" in sampling.blanket_note
    assert "multi-label" in sampling.blanket_note


def test_promotion_overlay_records_and_gate(tmp_path: Path) -> None:
    service = _service(tmp_path)
    result = service.run(approved=True)
    gate = result.gate
    assert gate.status == "PASS" and gate.ok() is True
    assert all(gate.checks.values())
    assert all(value == "PASS" for value in gate.acceptance_contract.values())
    assert result.overlays and result.records
    for artifact in result.overlays:
        assert artifact.parent_source_digest or artifact.candidate_id
        assert artifact.canonical_representation is False
        assert artifact.batch_id == DEFAULT_BATCH
    for record in result.records:
        assert record.before_after_semantic_diff["confirmed_facts_changed"] == 0
        assert record.forbidden_change_check["violations"] == 0
    overlay = result.status_overlay
    assert overlay.verified_repaired == len(result.overlays)
    assert overlay.human_review == len(gate.human_review_chapters)
    assert overlay.baseline_queue_counts == {CONFIRMED: 198, "LEGACY_FIELD_CONFLICT": 27,
                                             "LEGACY_CONTENT_GAP": 345}
    assert overlay.remaining_repair_targets == 372 - overlay.verified_repaired
    diff = result.diff
    assert diff.chapters_touched == len(result.overlays)
    assert diff.confirmed_facts_changed == 0 and diff.read_only_chapters_changed == 0
    assert diff.human_review == overlay.human_review and diff.blocked == 0
    for name in ("BATCH_01_BASELINE.json", "BATCH_01_CANDIDATES.json",
                 "BATCH_01_REPAIR_RECORDS.json", "BATCH_01_REPAIR_STATUS_OVERLAY.json",
                 "BATCH_01_DIFF.json", "BATCH_01_CLASSIFICATION_SAMPLE.json",
                 "BATCH_01_GATE.json"):
        assert (service.repair_dir / name).is_file(), name


def test_repeated_run_resumes_without_duplicate_overlay(tmp_path: Path) -> None:
    service = _service(tmp_path)
    first = service.run(approved=True)
    files_before = sorted(path.name for path in
                          (service.repair_dir / DEFAULT_BATCH / "repaired").glob("*.json"))
    second = service.run(approved=True)
    files_after = sorted(path.name for path in
                         (service.repair_dir / DEFAULT_BATCH / "repaired").glob("*.json"))
    assert files_before == files_after
    assert len(second.overlays) == len(first.overlays)
    assert "REPAIR_BATCH_RESUMED_FROM_OVERLAY" in {item.code for item in
                                                   second.gate.findings}
    assert second.gate.status == "PASS"


def test_acceptance_contract_sources_and_happened_truth(tmp_path: Path) -> None:
    service = _service(tmp_path)
    result = service.run(approved=True)
    contract = result.gate.acceptance_contract
    for gate_name in ("chapter_ir_validator", "canon_consistency",
                      "story_state_boundary", "resource_continuity",
                      "knowledge_boundary", "relationship_continuity",
                      "information_order", "foreshadow_order", "causality",
                      "writer_projection", "m1_semantic_gate"):
        assert contract.get(gate_name) == "PASS", gate_name
    baseline = result.baseline
    after = service.baseline_lock(service.load())
    assert baseline.happened_digests() == after.happened_digests()
    assert _artifact(service, "BATCH_01_REPAIR_STATUS_OVERLAY.json")["read_only"] is True
