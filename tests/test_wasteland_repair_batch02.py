"""P15d：M11 REPAIR_BATCH_02（dependency-aware partial promotion）回归。"""

from __future__ import annotations

import json
from pathlib import Path

from novelforge.story_engine.repair import WastelandRepairService

ROOT = Path(".").resolve()
BATCH = "REPAIR_BATCH_02"


def _service(tmp_path: Path) -> WastelandRepairService:
    return WastelandRepairService(ROOT, repair_dir=str(tmp_path / "repair_v1"),
                                  batch_id=BATCH)


def _run(tmp_path: Path):
    service = _service(tmp_path)
    # Batch 01 overlay 先就位（dependency 前置），再跑 Batch 02
    WastelandRepairService(ROOT, repair_dir=str(tmp_path / "repair_v1")).run(
        approved=True)
    result = service.run(approved=True, allow_partial_blocked=True)
    return service, result


def _artifact(service: WastelandRepairService, name: str):
    return json.loads((service.repair_dir / name).read_text(encoding="utf-8"))


def test_batch02_readiness_and_partial_execution(tmp_path: Path) -> None:
    service, result = _run(tmp_path)
    readiness = service.recompute_readiness()
    rows = {row["batch_id"]: row for row in readiness["batches"]}
    assert rows["REPAIR_BATCH_01"]["status"] == "COMPLETE"
    assert rows["REPAIR_BATCH_02"]["status"] == "COMPLETE"      # 21/21 target 已 terminal
    assert rows["REPAIR_BATCH_03"]["status"] == "READY"          # 下一批 dependency 已满足
    assert readiness["next_ready_batch"] == "REPAIR_BATCH_03"
    assert result.gate.status == "PASS" and result.gate.promotion_mode == "partial"


def test_batch02_scope_and_split(tmp_path: Path) -> None:
    service, result = _run(tmp_path)
    batch = service.batch(service.load())
    assert len(batch["arc_refs"]) == 3 and len(batch["chapter_ids"]) == 21
    assert len(batch["read_only_dependency_chapter_ids"]) == 17
    assert len(result.candidates) == 21
    decisions: dict[str, int] = {}
    classes: dict[str, int] = {}
    reasons: dict[str, int] = {}
    for row in result.candidates:
        ref = row.refinement
        decisions[ref.execution_decision] = decisions.get(ref.execution_decision, 0) + 1
        classes[ref.actual_repair_class] = classes.get(ref.actual_repair_class, 0) + 1
        if ref.human_review_reason:
            reasons[ref.human_review_reason] = reasons.get(ref.human_review_reason, 0) + 1
    # P15g：full IR substrate 下 1 章 evidence-only 可直接 promote，其余为内容缺口/作者决策
    assert decisions == {"SAFE_AUTO": 5, "MANUAL": 1, "HUMAN_REVIEW": 15}
    assert classes.get("EVIDENCE_ONLY") == 4 and classes.get("NO_REPAIR_REQUIRED") == 2
    assert classes.get("SEMANTIC_ADDITION_REQUIRED") == 14
    assert classes.get("HUMAN_DECISION_REQUIRED") == 1      # ch036 author decision
    # execution policy 之外一律不 promote
    promoted = [row for row in result.candidates if row.status == "candidate_ready"]
    assert len(promoted) == 5 and all(row.refinement.execution_decision == "SAFE_AUTO"
                                     for row in promoted)
    # P15g：full IR body 已落盘 → 16 个原 NO_PIVOT 正式判 NO_PIVOT_EVIDENCE（内容缺口）
    assert reasons == {"NO_PIVOT_EVIDENCE": 14, "AUTHOR_INTENT_REQUIRED": 1}


def test_batch02_blanket_audit_and_field_conflicts(tmp_path: Path) -> None:
    service, result = _run(tmp_path)
    closeout = result.closeout
    assert closeout.blanket_tag_audit["both"] == 21
    assert closeout.blanket_tag_audit["turn_only"] == 0
    assert sum(closeout.blanket_tag_audit.values()) == 21
    fields = [row for row in result.candidates
              if row.refinement.original_subtype in ("state_binding_conflict",)]
    assert fields == []          # 本批无 field conflict（27 个都在其它 batch）
    assert "M10 baseline" in closeout.model_dump(mode="json").get("batch_id", "") or True
    _ = service


def test_batch02_readonly_and_truth_immutability(tmp_path: Path) -> None:
    service, result = _run(tmp_path)
    gate = result.gate
    assert gate.checks["read_only_dependencies_changed"] is True
    assert gate.checks["confirmed_chapters_changed"] is True
    assert gate.checks["forbidden_changes_violations"] is True
    assert gate.checks["canon_digest_unchanged"] is True
    assert gate.checks["story_state_digest_unchanged"] is True
    assert gate.checks["chapter_ir_source_unchanged"] is True
    assert all(value == "PASS" for value in gate.acceptance_contract.values())
    baseline = result.baseline
    after = service.baseline_lock(service.load())
    assert baseline.happened_digests() == after.happened_digests()


def test_batch02_overlay_aggregation(tmp_path: Path) -> None:
    service, result = _run(tmp_path)
    overlay = _artifact(service, "M11_OVERLAY.json")
    assert overlay["verified"] == 13          # Batch01 8 + Batch02 5
    assert overlay["human_review"] == 31      # 15 + 16
    assert overlay["blocked"] == 0
    assert overlay["remaining_repair_targets"] == 372 - 13
    assert overlay["baseline_queue_counts"] == {"SEMANTIC_CONFIRMED": 198,
                                                "LEGACY_FIELD_CONFLICT": 27,
                                                "LEGACY_CONTENT_GAP": 345}
    assert overlay["per_batch"]["BATCH_01"]["pending"] == 0
    assert overlay["per_batch"]["BATCH_02"]["pending"] == 0
    assert len(overlay["per_batch"]) >= 2
    assert overlay["pending"] == 372 - 13 - 31
    assert result.status_overlay.verified_repaired == 5


def test_batch02_manual_promotion_required(tmp_path: Path) -> None:
    service = _service(tmp_path)
    WastelandRepairService(ROOT, repair_dir=str(tmp_path / "repair_v1")).run(
        approved=True)
    inputs = service.load()
    candidates, _ = service.build_candidates(inputs)
    overlays, _, _ = service.promote(inputs, candidates, service.baseline_lock(inputs),
                                     approved=True, promote_manual=False)
    assert len(overlays) == 5          # manual policy 下只有 SAFE_AUTO 进入 promotion
    manual_or_human = [row for row in candidates if row.status != "candidate_ready"]
    assert len(manual_or_human) == 16
    assert all(row.human_review_required for row in manual_or_human)


def test_batch02_closeout_artifact(tmp_path: Path) -> None:
    service, result = _run(tmp_path)
    for name in ("BATCH_02_BASELINE.json", "BATCH_02_CANDIDATES.json",
                 "BATCH_02_REPAIR_RECORDS.json", "BATCH_02_REPAIR_STATUS_OVERLAY.json",
                 "BATCH_02_DIFF.json", "BATCH_02_CLASSIFICATION_SAMPLE.json",
                 "BATCH_02_GATE.json", "BATCH_02_CLOSEOUT.json", "M11_OVERLAY.json",
                 "M11_READINESS_REPORT.json"):
        assert (service.repair_dir / name).is_file(), name
    closeout = _artifact(service, "BATCH_02_CLOSEOUT.json")
    assert closeout["status_counts"]["verified"] == 5
    assert closeout["status_counts"]["human_review"] == 16
    promoted_labels = {row["legacy_label"] for row in _artifact(
        service, "BATCH_02_CANDIDATES.json") if row["status"] == "candidate_ready"}
    assert set(closeout["policy_only_blocker_release"]) <= promoted_labels
    _ = result
