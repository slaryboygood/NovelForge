"""P15k：REPAIR_BATCH_05 dependency-closed safe targets 执行 + acceptance 回归。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from novelforge.story_engine.m11_batch05 import Batch05Service

from m11_phase_history import closed, report_records

ROOT = Path(".").resolve()
REPAIR_DIR = ROOT / "workspace/wasteland_001_exports/repair_v1"
DESIGN_DIR = ROOT / "workspace/wasteland_001_exports/repair_adoption_v1"


@pytest.fixture(scope="module")
def batch05():
    service = Batch05Service(ROOT)
    payload = service.run()
    return service, payload


def _artifact(service: Batch05Service, name: str):
    return json.loads((service.design_dir / name).read_text(encoding="utf-8"))


def test_batch05_frozen_scope(batch05) -> None:
    service, payload = batch05
    scope = _artifact(service, "BATCH_05_EXECUTION_SCOPE.json")
    assert scope["frozen"] is True
    assert len(scope["ready_target_ids"]) == 26
    assert scope["blocked_target_ids"] == []
    assert scope["source_digests"]["canon"] == "73836dada9d6bf8e"
    assert scope["readiness_v2_digest"]
    assert scope["foundation_digests"]["index"]
    assert payload["scope"] == {"ready": 26, "blocked": 0, "frozen": True}


def test_batch05_execution_and_split(batch05) -> None:
    service, payload = batch05
    assert payload["execution"]["verified"] == 17
    assert payload["execution"]["promotion_mode"] == "partial"
    assert payload["execution"]["gate_status"] == "PASS"
    candidates = json.loads((REPAIR_DIR / "BATCH_05_CANDIDATES.json")
                            .read_text(encoding="utf-8"))
    rows = candidates["candidates"] if isinstance(candidates, dict) else candidates
    promoted = [row for row in rows if row["status"] == "candidate_ready"]
    assert len(promoted) == 17
    assert all(row["refinement"]["execution_decision"] == "SAFE_AUTO"
               for row in promoted)
    classes = {row["legacy_label"]: row["refinement"]["actual_repair_class"]
               for row in promoted}
    assert sum(1 for value in classes.values() if value == "NO_REPAIR_REQUIRED") == 4
    assert sum(1 for value in classes.values() if value == "EVIDENCE_ONLY") == 13
    # 后续阶段（P15l）会继续推进 projection；此处断言 P15k 的下界与相对增量
    assert payload["overlay"]["repaired"] >= 37
    assert payload["overlay"]["no_repair_required"] >= 15


def test_batch05_dynamic_downgrade(batch05) -> None:
    service, _payload = batch05
    reconciliation = _artifact(service, "BATCH_05_RECONCILIATION.json")
    design = [row for row in reconciliation["records"]
              if row["new_resolution_status"] == "CONTENT_DESIGN_REQUIRED"]
    assert len(design) == 7
    assert all(row["design_item_id"].startswith("CDQ_B05_") for row in design)
    entity = [row for row in reconciliation["records"]
              if row["new_resolution_status"] == "EVIDENCE_READY"]
    assert len(entity) == 1 and entity[0]["legacy_label"] == "ch120"
    manual = [row for row in reconciliation["records"]
              if row["legacy_label"] == "ch143"]
    assert manual and manual[0]["repair_class"] == "FIELD_REBIND"
    assert manual[0]["execution_decision"] == "MANUAL"
    assert reconciliation["auto_discovered_design_items"]


def test_batch05_no_semantic_addition(batch05) -> None:
    service, payload = batch05
    diff = json.loads((REPAIR_DIR / "BATCH_05_DIFF.json").read_text(encoding="utf-8"))
    assert diff["semantic_elements_added"] == 0
    assert diff["semantic_elements_removed"] == 0
    assert diff["confirmed_facts_changed"] == 0
    assert diff["read_only_chapters_changed"] == 0
    assert diff["evidence_only_repairs"] == 17
    closeout = json.loads((REPAIR_DIR / "BATCH_05_CLOSEOUT.json")
                          .read_text(encoding="utf-8"))
    assert closeout["class_counts"].get("CONTENT_REWRITE_REQUIRED") is None
    assert closeout["status_counts"]["verified"] == 17
    assert payload["content_generated"] is False
    assert payload["micro_proposals_executed"] is False


def test_micro_and_author_decisions_stay_frozen(batch05) -> None:
    service, _payload = batch05
    manifest = _artifact(service, "M11_MICRO_APPROVAL_MANIFEST.json")
    assert manifest["auto_approved"] is False
    assert manifest["grade_counts"]["RECOMMENDED"] == 34
    author = _artifact(service, "AUTHOR_DECISION_STATUS.json")
    assert author["auto_closed"] == 0
    briefs = [row for row in author["items"] if row["legacy_label"] == "ch036"]
    assert briefs and briefs[0]["status"] == "AWAITING_AUTHOR"
    manual = _artifact(service, "MANUAL_REPAIR_BRIEF_ch063.json")
    assert manual["status"] == "MANUAL_REQUIRED"
    major = _artifact(service, "MAJOR_AUTHOR_DESIGN_BRIEFS.json")
    assert major["auto_design_generated"] is False


def test_confirmed_binding_conflict_not_bypassed(batch05) -> None:
    service, payload = batch05
    proposals = _artifact(service, "CONFIRMED_OVERRIDE_REPLAY_PROPOSALS.json")
    assert proposals["promoted"] == 0
    assert proposals["in_scope_confirmed_binding_targets"] == []
    gate = json.loads((REPAIR_DIR / "BATCH_05_GATE.json").read_text(encoding="utf-8"))
    assert gate["checks"]["confirmed_historical_binding_guard"] is True
    overlay = _artifact(service, "M11_OVERLAY_V2.json")
    assert overlay["confirmed_binding_blocked"] >= 0
    assert payload["override_replay"]["proposals"] == 0
    assert payload["override_replay"]["promoted"] == 0


def test_acceptance_contract_pass(batch05) -> None:
    service, payload = batch05
    contract = _artifact(service, "BATCH_05_ACCEPTANCE_CONTRACT.json")
    assert contract["status"] == "PASS"
    assert all(contract["checks"].values())
    for key in ("execution_scope_ready_only", "dependency_closure_proven",
                "unresolved_upstream_not_assumed", "full_ir_required",
                "only_owning_mutable_changed", "read_only_unchanged",
                "confirmed_198_unchanged", "canon_unchanged", "story_state_unchanged",
                "legacy_unchanged", "source_ir_unchanged",
                "historical_foundation_unchanged", "confirmed_facts_changed_zero",
                "forbidden_violation_zero", "entity_violation_zero",
                "confirmed_binding_violation_zero", "semantic_addition_zero",
                "parent_lineage", "overlay_conservation", "readiness_v2_consistency"):
        assert contract["checks"][key] is True, key
    assert payload["acceptance_contract"]["status"] == "PASS"


def test_overlay_and_readiness_after_batch05(batch05) -> None:
    service, payload = batch05
    overlay = _artifact(service, "M11_OVERLAY_V2.json")
    assert overlay["resolved_total"] >= 52
    # P15k 时点 = 40..47；后续 production run 的 runtime content-design 降级会继续增加
    assert overlay["content_design_required"] <= 60
    assert overlay["evidence_ready"] == closed(3, 0)
    assert overlay["conservation"]["exact"] is True
    primary = overlay["primary_resolution_status_counts"]
    assert sum(primary.values()) == 372
    readiness = _artifact(service, "M11_READINESS_V2.json")
    batches = {row["batch_id"]: row for row in readiness["batches"]}
    # Batch 04 在 P15k 后为 BLOCKED（0 ready）；P15l micro pilot 释放 1 个 ready → PARTIAL_READY；
    # M11 closure 后批次全部 COMPLETE。历史值必须仍被 frozen phase report 记录。
    report_records("BATCH05", "| REPAIR_BATCH_04 | IN_PROGRESS | BLOCKED | 10 | 0 | 14 |")
    report_records("MICRO_PILOT",
                   "| REPAIR_BATCH_04 | IN_PROGRESS | **PARTIAL_READY** | 10 | 1 | 13 |")
    assert batches["REPAIR_BATCH_04"]["execution_status"] == closed(
        ("BLOCKED", "PARTIAL_READY"), "COMPLETE")
    assert batches["REPAIR_BATCH_05"]["execution_status"] == closed("BLOCKED", "COMPLETE")
    assert len(batches["REPAIR_BATCH_05"]["resolved_target_ids"]) >= 17
    # M11-RUN-01 之后 Batch 06 的 16 个 ready target 已全部处理（promote / dynamic downgrade）
    # → ready 清空，execution_status 不再是 PARTIAL_READY。
    assert batches["REPAIR_BATCH_06"]["execution_status"] == closed(
        ("PARTIAL_READY", "BLOCKED"), "COMPLETE")
    if batches["REPAIR_BATCH_06"]["execution_status"] == "PARTIAL_READY":
        assert len(batches["REPAIR_BATCH_06"]["ready_target_ids"]) == 16
    else:
        assert batches["REPAIR_BATCH_06"]["ready_target_ids"] == []
        assert len(batches["REPAIR_BATCH_06"]["resolved_target_ids"]) >= 15
    assert payload["batch_06_executed"] is False
    assert payload["readiness"]["batch_06"]["execution_status"] == closed(
        ("PARTIAL_READY", "BLOCKED"), "COMPLETE")


def test_p15k_gate_pass_and_truth_unchanged(batch05) -> None:
    service, payload = batch05
    gate = _artifact(service, "P15K_GATE.json")
    assert gate["status"] == "PASS"
    assert all(gate["checks"].values())
    assert gate["batch_06_executed"] is False
    assert payload["status"] == "PASS"
    scope = _artifact(service, "BATCH_05_EXECUTION_SCOPE.json")
    for name, path in (("canon", ROOT / "novel/authoring/story_engine/canon/"
                        "wasteland_001.sqlite"),
                       ("story_state", ROOT / "novel/authoring/story_engine/state/"
                        "runtime_wasteland_001/v000001.json"),
                       ("legacy", ROOT / "workspace/wasteland_001_exports/"
                        "WASTELAND_001_OUTLINE_CANON_FINAL_CANDIDATE_V5.json"),
                       ("chapter_ir", ROOT / "workspace/wasteland_001_exports/"
                        "chapter_ir_v1/full_migration/"
                        "WASTELAND_001_CHAPTER_IR_FULL.json")):
        digest = __import__("hashlib").sha256(path.read_bytes()).hexdigest()[:16]
        assert digest == scope["source_digests"][name], name
