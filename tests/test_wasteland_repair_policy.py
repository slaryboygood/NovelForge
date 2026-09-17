"""P15c：M11 repair policy refinement + Batch 01 closeout 回归。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from novelforge.story_engine.repair import (
    DEFAULT_BATCH,
    M11ExecutionPolicy,
    RepairAlternativePolicy,
    RepairPreflightError,
    WastelandRepairService,
)

ROOT = Path(".").resolve()


def _service(tmp_path: Path) -> WastelandRepairService:
    return WastelandRepairService(ROOT, repair_dir=str(tmp_path / "repair_v1"))


def _closeout(tmp_path: Path):
    service = _service(tmp_path)
    result = service.run(approved=True)
    return service, result


def test_conservative_substitution_only(tmp_path: Path) -> None:
    policy = RepairAlternativePolicy()
    actual, reason, rule = policy.substitute(["ADD_MISSING_TURN"], "ADD_TURN_EVIDENCE")
    assert actual == "ADD_TURN_EVIDENCE" and "conservative" in reason
    assert rule == "CONSERVATIVE_SUBSTITUTION:ADD_MISSING_TURN->ADD_TURN_EVIDENCE"
    actual, _, rule = policy.substitute(["ADD_MISSING_PAYOFF"], "FIELD_REBIND")
    assert actual == "FIELD_REBIND"
    actual, _, rule = policy.substitute(["FIELD_REBIND"], "ADD_TURN_EVIDENCE")
    assert rule.startswith("CONSERVATIVE_INVASIVENESS")     # 更保守的同级替代
    with pytest.raises(RepairPreflightError) as upgrade:
        policy.substitute(["FIELD_REBIND"], "ADD_MISSING_TURN")   # 禁止升级
    assert upgrade.value.code == "REPAIR_TYPE_NOT_ALLOWED"
    with pytest.raises(RepairPreflightError) as direct:
        policy.assert_no_upgrade("FIELD_REBIND", "CONTENT_REWRITE_REQUIRED")
    assert direct.value.code == "REPAIR_INVASIVENESS_UPGRADE_FORBIDDEN"
    _ = tmp_path


def test_execution_policy_boundaries() -> None:
    policy = M11ExecutionPolicy()
    assert policy.decide("EVIDENCE_ONLY", "MEDIUM") == "SAFE_AUTO"
    assert policy.decide("FIELD_REBIND", "LOW") == "SAFE_AUTO"
    assert policy.decide("FUNCTION_NA_CORRECTION", "MEDIUM") == "SAFE_AUTO"
    assert policy.decide("SEMANTIC_ADDITION_REQUIRED", "MEDIUM") == "MANUAL"
    assert policy.decide("CONTENT_REWRITE_REQUIRED", "LOW") == "MANUAL"
    assert policy.decide("EVIDENCE_ONLY", "HIGH") == "MANUAL"
    assert policy.decide("EVIDENCE_ONLY", "MEDIUM", human_review_required=True) \
        == "HUMAN_REVIEW"
    assert policy.decide("HUMAN_DECISION_REQUIRED", "MEDIUM") == "HUMAN_REVIEW"
    assert policy.decide("EVIDENCE_ONLY", "MEDIUM", forbidden_violation=True) \
        == "HUMAN_REVIEW"


def test_batch01_closeout_releases_policy_only_blockers(tmp_path: Path) -> None:
    service, result = _closeout(tmp_path)
    assert result.gate.status == "PASS"
    released = set(result.closeout.policy_only_blocker_release)
    assert {"ch002", "ch004", "ch013"} <= released
    # P15g：full IR substrate 下 evidence-only 可直接 promote（6 → 8），
    # 其余 15 章从 HUMAN_DECISION 正式落到 SEMANTIC_ADDITION_REQUIRED（内容缺口）
    assert result.status_overlay.verified_repaired == 8
    assert result.status_overlay.human_review == 15
    rules = {row.legacy_label: row.refinement.policy_rule_id
             for row in result.candidates if row.refinement}
    assert rules["ch002"].startswith("CONSERVATIVE")
    assert rules["ch013"].startswith("CONSERVATIVE")
    closeout = json.loads(
        (service.repair_dir / "BATCH_01_CLOSEOUT.json").read_text(encoding="utf-8"))
    assert closeout["class_counts"]["EVIDENCE_ONLY"] == 5
    assert closeout["class_counts"]["FUNCTION_NA_CORRECTION"] == 3
    assert closeout["class_counts"]["SEMANTIC_ADDITION_REQUIRED"] == 15
    assert closeout["baseline_queue_counts"] == {
        "SEMANTIC_CONFIRMED": 198, "LEGACY_FIELD_CONFLICT": 27,
        "LEGACY_CONTENT_GAP": 345}


def test_blanket_tagging_refined_and_baseline_untouched(tmp_path: Path) -> None:
    service, result = _closeout(tmp_path)
    audit = result.closeout.blanket_tag_audit
    assert audit["both"] > 0 and audit["both"] + audit["turn_only"] \
        + audit["payoff_only"] + audit["neither"] == len(result.refinements)
    # 每个 refinement 都记录 M10 原始分类（不被回写）
    for row in result.refinements:
        assert row.original_allowed_repair_types is not None
        assert row.actual_semantic_status in (
            "PRESENT_AND_BOUND", "PRESENT_BUT_UNBOUND", "NOT_APPLICABLE",
            "TRULY_MISSING", "AMBIGUOUS", "SOURCE_EVIDENCE_INSUFFICIENT")
        assert row.actual_repair_class in (
            "EVIDENCE_ONLY", "FIELD_REBIND", "FUNCTION_NA_CORRECTION",
            "SEMANTIC_ADDITION_REQUIRED", "CONTENT_REWRITE_REQUIRED",
            "HUMAN_DECISION_REQUIRED", "NO_REPAIR_REQUIRED")
        assert row.non_authoritative is True
    m10_targets = json.loads((ROOT / "workspace/wasteland_001_exports/reconstruction_v2"
                              / "LEGACY_TARGET_ALIGNMENT.json").read_text(encoding="utf-8"))
    assert len(m10_targets["targets"]) == 372
    _ = service


def test_na_correction_and_human_review_reasons(tmp_path: Path) -> None:
    service, result = _closeout(tmp_path)
    na_rows = [row for row in result.candidates if row.refinement
               and row.refinement.actual_repair_class == "FUNCTION_NA_CORRECTION"]
    assert na_rows, "存在 N/A correction"
    for row in na_rows:
        assert "NOT_APPLICABLE" in row.refinement.field_status.values()
        assert any(op.op == "MARK_NOT_APPLICABLE" for op in row.proposed_patch)
        assert row.refinement.execution_decision in ("SAFE_AUTO", "MANUAL")
    humans = [row for row in result.candidates if row.human_review_required]
    assert humans and all(row.refinement.human_review_reason in (
        "NO_PIVOT_EVIDENCE", "SOURCE_IR_INSUFFICIENT", "AMBIGUOUS_FUNCTION",
        "AUTHOR_INTENT_REQUIRED", "STATE_DOMAIN_AMBIGUOUS",
        "MULTIPLE_VALID_INTERPRETATIONS", "OTHER") for row in humans)
    reasons = {row.refinement.human_review_reason for row in humans}
    # P15g：full IR body 已落盘 → 具备 absence proof，可以正式判 NO_PIVOT_EVIDENCE；
    # 不再使用 SOURCE_IR_INSUFFICIENT（那表示"看不到 IR body"）
    assert "NO_PIVOT_EVIDENCE" in reasons
    assert "SOURCE_IR_INSUFFICIENT" not in reasons
    assert all(row.evidence_substrate in ("HISTORICAL_FULL_IR",
                                          "HISTORICAL_FULL_IR_PARTIAL")
               for row in humans)
    assert "SHADOW_FALLBACK" not in {row.evidence_substrate for row in result.candidates}
    assert all(row.refinement.evidence_sufficiency in ("SUFFICIENT", "PARTIAL",
                                                       "INSUFFICIENT")
               for row in humans)
    _ = service


def test_readiness_recompute_after_batch01(tmp_path: Path) -> None:
    service, result = _closeout(tmp_path)
    readiness = service.recompute_readiness()
    rows = {row["batch_id"]: row for row in readiness["batches"]}
    assert rows["REPAIR_BATCH_01"]["status"] == "COMPLETE"
    assert rows["REPAIR_BATCH_02"]["status"] == "BLOCKED_AUTHOR_DECISION"
    assert rows["REPAIR_BATCH_02"]["partial_allowed"] is True
    assert rows["REPAIR_BATCH_02"]["blocked_targets"] == 1
    assert rows["REPAIR_BATCH_03"]["status"] == "BLOCKED_DEPENDENCY"
    assert readiness["next_ready_batch"] == "REPAIR_BATCH_02"
    # Batch 01 的 preflight 在 closeout 后仍然可用（幂等复用 overlay）
    assert service.preflight(service.load())["readiness_ready"] is True
    _ = result


def test_source_digests_and_baseline_unchanged(tmp_path: Path) -> None:
    service, result = _closeout(tmp_path)
    before = result.baseline
    after = service.baseline_lock(service.load())
    assert before.happened_digests() == after.happened_digests()
    assert after.queue_snapshot == {"SEMANTIC_CONFIRMED": 198,
                                    "LEGACY_FIELD_CONFLICT": 27,
                                    "LEGACY_CONTENT_GAP": 345}
    gate = json.loads((service.repair_dir / "BATCH_01_GATE.json").read_text(
        encoding="utf-8"))
    assert gate["checks"]["confirmed_chapters_changed"] is True
    assert gate["checks"]["read_only_dependencies_changed"] is True
    assert gate["status"] == "PASS" and gate["promotion_mode"] == "partial"
    assert DEFAULT_BATCH == "REPAIR_BATCH_01"
