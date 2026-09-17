"""P15e：REPAIR_BATCH_03 + Repair Evidence Sufficiency Audit 回归。"""

from __future__ import annotations

import json
from pathlib import Path

from novelforge.story_engine.repair import (
    M11ExecutionPolicy,
    WastelandRepairService,
)

ROOT = Path(".").resolve()
BATCH = "REPAIR_BATCH_03"


def _run_all(tmp_path: Path):
    root = str(tmp_path / "repair_v1")
    first = WastelandRepairService(ROOT, repair_dir=root).run(approved=True)
    second = WastelandRepairService(ROOT, repair_dir=root,
                                    batch_id="REPAIR_BATCH_02").run(
        approved=True, allow_partial_blocked=True)
    third = WastelandRepairService(ROOT, repair_dir=root, batch_id=BATCH).run(
        approved=True, allow_partial_blocked=True)
    return first, second, third


def _artifact(service_root: Path, name: str):
    return json.loads((service_root / name).read_text(encoding="utf-8"))


def test_batch03_preflight_dependency_safety(tmp_path: Path) -> None:
    first, second, third = _run_all(tmp_path)
    assert first.gate.status == "PASS" and second.gate.status == "PASS"
    assert third.gate.status == "PASS" and third.gate.promotion_mode == "partial"
    checks = third.gate.checks
    assert checks["readiness_ready"] is True and checks["dependencies_satisfied"] is True
    service = WastelandRepairService(ROOT, repair_dir=str(tmp_path / "repair_v1"),
                                     batch_id=BATCH)
    readiness = service.recompute_readiness()
    rows = {row["batch_id"]: row for row in readiness["batches"]}
    assert rows["REPAIR_BATCH_01"]["status"] == "COMPLETE"
    assert rows["REPAIR_BATCH_02"]["status"] == "COMPLETE"
    assert rows["REPAIR_BATCH_03"]["status"] == "COMPLETE"
    assert readiness["next_ready_batch"] == "REPAIR_BATCH_04"


def test_batch03_scope_and_field_conflicts(tmp_path: Path) -> None:
    _first, _second, third = _run_all(tmp_path)
    service = WastelandRepairService(ROOT, repair_dir=str(tmp_path / "repair_v1"),
                                     batch_id=BATCH)
    batch = service.batch(service.load())
    assert len(batch["arc_refs"]) == 3 and len(batch["chapter_ids"]) == 20
    assert len(batch["read_only_dependency_chapter_ids"]) == 15
    conflicts = {row.legacy_label: row.refinement.original_subtype
                 for row in third.candidates
                 if "conflict" in (row.refinement.original_subtype or "")}
    assert conflicts == {"ch048": "payoff_conflict", "ch055": "turn_conflict",
                         "ch063": "state_binding_conflict"}
    by_label = {row.legacy_label: row for row in third.candidates}
    assert by_label["ch048"].refinement.actual_repair_class == "NO_REPAIR_REQUIRED"
    assert by_label["ch055"].refinement.actual_repair_type == "ADD_TURN_EVIDENCE"
    assert by_label["ch063"].status == "human_review"          # state_domain 不唯一 → 不猜
    _ = third


def test_batch03_split_and_no_semantic_addition(tmp_path: Path) -> None:
    _first, _second, third = _run_all(tmp_path)
    classes: dict[str, int] = {}
    decisions: dict[str, int] = {}
    for row in third.candidates:
        ref = row.refinement
        classes[ref.actual_repair_class] = classes.get(ref.actual_repair_class, 0) + 1
        decisions[ref.execution_decision] = decisions.get(ref.execution_decision, 0) + 1
    assert classes.get("NO_REPAIR_REQUIRED") == 3
    assert classes.get("EVIDENCE_ONLY") == 9          # P15g：2 章从 human_review 转 evidence-only
    assert classes.get("FIELD_REBIND") == 1
    assert classes.get("SEMANTIC_ADDITION_REQUIRED") == 7   # full IR 证明的内容缺口
    assert decisions == {"SAFE_AUTO": 12, "MANUAL": 1, "HUMAN_REVIEW": 7}
    manual = [row for row in third.candidates
              if row.refinement.execution_decision == "MANUAL"]
    assert [row.legacy_label for row in manual] == ["ch063"]   # HIGH risk → manual
    assert manual[0].status == "human_review"                  # promote_manual=False
    assert third.closeout.status_counts["verified"] == 12
    assert third.closeout.status_counts["human_review"] == 8
    assert len(third.overlays) == 12
    blanket = third.closeout.blanket_tag_audit
    assert blanket["both"] == 17 and blanket["turn_only"] == 1
    assert blanket["payoff_only"] == 1 and blanket["neither"] == 1
    assert sum(blanket.values()) == 20


def test_evidence_sufficiency_report(tmp_path: Path) -> None:
    _run_all(tmp_path)
    service = WastelandRepairService(ROOT, repair_dir=str(tmp_path / "repair_v1"))
    report = service.build_evidence_sufficiency_report()
    counters = report["counters"]
    assert counters["total"] == 64          # Batch 01 + 02 + 03
    # P15g：Historical Full IR 已成为 M11 substrate → 64/64 有 full IR body
    assert counters["full_ir_available"] == 64 and counters["shadow_only"] == 0
    assert counters["true_missing_pivot"] == 36
    assert counters["source_insufficient_pivot"] == 0
    assert counters["author_ambiguity"] == 1
    assert report["M11_EVIDENCE_FOUNDATION_STATUS"] == "SUFFICIENT_TO_CONTINUE"
    assert set(report["per_batch"]) == {"REPAIR_BATCH_01", "REPAIR_BATCH_02",
                                        "REPAIR_BATCH_03"}
    assert report["per_batch"]["REPAIR_BATCH_01"]["verified"] == 8
    assert report["per_batch"]["REPAIR_BATCH_03"]["verified"] == 12
    assert all(row["full_ir_body"] is True for row in report["rows"])
    assert "Historical Full Chapter IR Materialization" in report["note"]


def test_no_pivot_does_not_imply_truly_missing(tmp_path: Path) -> None:
    _run_all(tmp_path)
    service = WastelandRepairService(ROOT, repair_dir=str(tmp_path / "repair_v1"))
    report = service.build_evidence_sufficiency_report()
    for row in report["rows"]:
        if row["human_review_reason"] == "NO_PIVOT_EVIDENCE":
            # P15g：full IR body 已落盘 → absence proof 成立，才允许判 NO_PIVOT_EVIDENCE
            assert row["evidence_sufficiency"] == "SUFFICIENT"
            assert row["full_ir_body"] is True
            assert row["actual_semantic_status"] == "TRULY_MISSING"
        if row["human_review_reason"] == "SOURCE_IR_INSUFFICIENT":
            assert row["evidence_sufficiency"] in ("PARTIAL", "INSUFFICIENT")
            assert row["full_ir_body"] is False
    statuses = {row["actual_semantic_status"] for row in report["rows"]}
    assert "SOURCE_EVIDENCE_INSUFFICIENT" not in statuses
    assert "TRULY_MISSING" in statuses


def test_safe_auto_requires_sufficient_evidence(tmp_path: Path) -> None:
    policy = M11ExecutionPolicy()
    assert policy.decide("EVIDENCE_ONLY", "MEDIUM", evidence_sufficient=True) == "SAFE_AUTO"
    assert policy.decide("EVIDENCE_ONLY", "MEDIUM", evidence_sufficient=False) == "MANUAL"
    assert policy.decide("HUMAN_DECISION_REQUIRED", "MEDIUM",
                         evidence_sufficient=False) == "HUMAN_REVIEW"
    _first, _second, third = _run_all(tmp_path)
    for row in third.candidates:
        if row.status == "candidate_ready":
            assert row.refinement.evidence_sufficiency == "SUFFICIENT"
            assert row.refinement.execution_decision == "SAFE_AUTO"


def test_overlay_and_readiness_after_batch03(tmp_path: Path) -> None:
    _run_all(tmp_path)
    service = WastelandRepairService(ROOT, repair_dir=str(tmp_path / "repair_v1"))
    overlay = _artifact(service.repair_dir, "M11_OVERLAY.json")
    assert overlay["verified"] == 25          # P15g：20 + 5 evidence-only promote
    assert overlay["human_review"] == 39
    assert overlay["blocked"] == 0
    assert overlay["remaining_repair_targets"] == 372 - 25
    assert overlay["baseline_queue_counts"] == {"SEMANTIC_CONFIRMED": 198,
                                                "LEGACY_FIELD_CONFLICT": 27,
                                                "LEGACY_CONTENT_GAP": 345}
    assert service.recompute_readiness()["next_ready_batch"] == "REPAIR_BATCH_04"
    assert (service.repair_dir / "REPAIR_EVIDENCE_SUFFICIENCY.json").is_file()


def test_truth_digests_unchanged_after_batch03(tmp_path: Path) -> None:
    first, _second, third = _run_all(tmp_path)
    service = WastelandRepairService(ROOT, repair_dir=str(tmp_path / "repair_v1"),
                                     batch_id=BATCH)
    before = first.baseline
    after = service.baseline_lock(service.load())
    assert before.happened_digests() == after.happened_digests()
    assert after.queue_snapshot == {"SEMANTIC_CONFIRMED": 198,
                                    "LEGACY_FIELD_CONFLICT": 27,
                                    "LEGACY_CONTENT_GAP": 345}
    gate = _artifact(service.repair_dir, "BATCH_03_GATE.json")
    assert gate["status"] == "PASS"
    assert gate["checks"]["forbidden_changes_violations"] is True
    assert gate["checks"]["read_only_dependencies_changed"] is True
    assert gate["checks"]["confirmed_chapters_changed"] is True
    assert all(value == "PASS" for value in gate["acceptance_contract"].values())
    _ = third
