"""P15g：Historical IR foundation 接入 M11 repair pipeline 回归。

覆盖：substrate 优先级 / shadow fallback 不得 promote / obsolete·applies-cleanly
reconciliation / resolved 语义 / 6 evidence-only refresh / ch063 manual / ch036 author /
36 content-design queue / micro-major / 62 ambiguous entity impact / 10 M1 golden delta /
跨章 confirmed fact 优先 / dependency gate / overlay 聚合 / baseline·Canon·StoryState 不变。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from novelforge.story_engine.historical_adoption import (
    M11FoundationAdoptionService,
)
from novelforge.story_engine.repair import (
    SUBSTRATE_FULL,
    SUBSTRATE_SHADOW,
    M11ExecutionPolicy,
    WastelandRepairService,
)

ROOT = Path(".").resolve()
REPAIR_DIR = ROOT / "workspace/wasteland_001_exports/repair_v1"


@pytest.fixture(scope="module")
def adoption(tmp_path_factory: pytest.TempPathFactory):
    service = M11FoundationAdoptionService(ROOT)
    payload = service.run()
    return service, payload


def _artifact(service: M11FoundationAdoptionService, name: str):
    return json.loads((service.adoption_dir / name).read_text(encoding="utf-8"))


def test_repair_engine_prefers_full_ir(adoption) -> None:
    service, _payload = adoption
    repair = WastelandRepairService(ROOT, repair_dir=str(REPAIR_DIR))
    inputs = repair.load()
    assert inputs.foundation_rows, "foundation substrate 必须被加载"
    row = repair.foundation_row("uuid_c4b238be82e5544fac10701d4f276088")
    assert row["evidence_substrate"] in (SUBSTRATE_FULL, "HISTORICAL_FULL_IR_PARTIAL")
    assert row["verified"] is True and row["chapter_ir_digest"]
    substrate = service.verify_substrate()
    assert substrate["artifact_count"] == 570 and substrate["mismatch_count"] == 0
    assert substrate["substrate_default"] == SUBSTRATE_FULL


def test_shadow_fallback_cannot_safe_auto(tmp_path: Path) -> None:
    policy = M11ExecutionPolicy()
    assert policy.decide("EVIDENCE_ONLY", "MEDIUM", substrate=SUBSTRATE_FULL) == "SAFE_AUTO"
    assert policy.decide("EVIDENCE_ONLY", "MEDIUM",
                         substrate=SUBSTRATE_SHADOW) == "MANUAL"
    # 空 foundation store：全部 candidate 落到 SHADOW_FALLBACK，不得 promote
    empty = tmp_path / "empty_foundation"
    empty.mkdir()
    service = WastelandRepairService(ROOT, repair_dir=str(tmp_path / "repair_v1"),
                                     foundation_dir=str(empty))
    inputs = service.load()
    candidates, _sampling = service.build_candidates(inputs)
    assert all(row.evidence_substrate == SUBSTRATE_SHADOW for row in candidates)
    assert all(row.refinement.execution_decision != "SAFE_AUTO" for row in candidates)


def test_obsolete_and_applies_cleanly_reconciliation(adoption) -> None:
    service, _payload = adoption
    reconciliation = _artifact(service, "REPAIR_RECONCILIATION.json")
    assert reconciliation["record_count"] == 64
    assert reconciliation["records_modified"] is False
    rows = {row["legacy_label"]: row for row in reconciliation["records"]}
    obsolete = [row for row in rows.values()
                if row["replay_status"] == "OBSOLETE_REPAIR"]
    assert len(obsolete) == 7
    assert {row["legacy_label"] for row in obsolete} == {
        "ch029", "ch039", "ch047", "ch048", "ch055", "ch058", "ch064"}
    assert all(row["new_resolution_status"] == "RESOLVED_NO_REPAIR_REQUIRED"
               and row["resolved"] is True for row in obsolete)
    assert all("OBSOLETE_AFTER_FOUNDATION" in row["reason"] for row in obsolete)
    clean = [row for row in rows.values() if row["replay_status"] == "APPLIES_CLEANLY"]
    assert len(clean) == 13
    assert all(row["new_resolution_status"] == "RESOLVED_REPAIRED" for row in clean)
    assert all(row["old_patch_digest"] and row["foundation_artifact_digest"]
               for row in reconciliation["records"])


def test_resolution_semantics_and_overlay_aggregation(adoption) -> None:
    service, payload = adoption
    projection = _artifact(service, "M11_RESOLUTION_PROJECTION.json")
    assert projection["repaired"] == 18          # 13 applies-cleanly + 5 evidence-only
    assert projection["no_repair_required"] == 7
    assert projection["resolved_total"] == 25
    assert projection["evidence_ready"] == 1     # ch027（ambiguous entity，未 promote）
    assert projection["manual"] == 1 and projection["content_design_required"] == 36
    assert projection["author_decision"] == 1
    assert projection["pending"] == 372 - 25 - 1 - 1 - 36 - 1     # 308
    assert projection["resolved_total"] + projection["evidence_ready"] \
        + projection["manual"] + projection["content_design_required"] \
        + projection["author_decision"] + projection["pending"] == 372
    assert projection["baseline_queue_counts"] == {
        "SEMANTIC_CONFIRMED": 198, "LEGACY_FIELD_CONFLICT": 27, "LEGACY_CONTENT_GAP": 345}
    official = json.loads((REPAIR_DIR / "M11_OVERLAY.json").read_text(encoding="utf-8"))
    # P15i 之后 official overlay 由更新阶段维护（本测试只要求 P15g 结果不被回退）
    assert official["resolved_total"] >= 25 and official["baseline_queue_counts"] == {
        "SEMANTIC_CONFIRMED": 198, "LEGACY_FIELD_CONFLICT": 27, "LEGACY_CONTENT_GAP": 345}
    assert official["per_batch"]["REPAIR_BATCH_01"]["resolved_repaired"] >= 8
    assert official["per_batch"]["REPAIR_BATCH_01"]["content_design_required"] <= 15
    assert payload["overlay"]["resolution_semantics"]


def test_evidence_only_refresh_outcome(adoption) -> None:
    service, _payload = adoption
    refresh = _artifact(service, "EVIDENCE_ONLY_REFRESH.json")
    # refresh 覆盖 6 个 evidence-only + ch063（field rebind，保持 manual）
    assert refresh["refreshed"] == 7 and refresh["promoted_count"] == 5
    outcomes = {row["legacy_label"]: row for row in refresh["outcomes"]}
    assert outcomes["ch027"]["promoted"] is False
    assert outcomes["ch027"]["checks"]["ambiguity_ok"] is False
    for label in ("ch008", "ch014", "ch043", "ch049", "ch059"):
        assert outcomes[label]["safe_auto_allowed"] is True
        assert outcomes[label]["evidence_substrate"] == SUBSTRATE_FULL
        assert all(outcomes[label]["checks"][key] is True for key in
                   ("risk_ok", "validators_ok", "forbidden_ok", "evidence_ok",
                    "substrate_is_full_ir"))
    assert refresh["semantics_added"] == 0
    repaired = sorted(path.name for path in (service.adoption_dir / "repaired").glob("*.json"))
    assert len(repaired) == 5


def test_ch063_manual_and_ch036_author_decision(adoption) -> None:
    service, _payload = adoption
    manual = _artifact(service, "MANUAL_CANDIDATE_CH063.json")
    assert manual["auto_safe_auto"] is False
    assert manual["state_domain_unique"] is False
    assert manual["resolution"] in ("MANUAL_REQUIRED", "MANUAL_READY")
    assert "关键词规则" in manual["rule_artifact_note"]
    assert manual["before_state_binding"]["legacy_world_state_change"]
    author = _artifact(service, "AUTHOR_DECISION_STATUS.json")
    ch036 = next(row for row in author["items"] if row["legacy_label"] == "ch036")
    assert ch036["status"] == "AWAITING_AUTHOR" and ch036["auto_closed"] is False
    assert ch036["proposal"] in ("AUTHOR_DECISION_STILL_REQUIRED",
                                 "AUTHOR_DECISION_NO_LONGER_REQUIRED")
    assert author["auto_closed"] == 0
    assert ch036["full_ir_evidence_note"]


def test_content_design_queue_micro_vs_major(adoption) -> None:
    service, _payload = adoption
    queue = _artifact(service, "M11_CONTENT_DESIGN_QUEUE.json")
    assert queue["item_count"] == 36
    assert queue["micro_major_counts"] == {"micro": 34, "major": 2}
    assert queue["author_design_required"] == 2
    assert queue["content_generated"] is False
    assert sum(queue["subtype_counts"].values()) == 36
    presence = queue["subtype_presence_counts"]
    assert presence["MICRO_PIVOT_REQUIRED"] == 34
    assert presence["MAJOR_PIVOT_REQUIRED"] == 2
    assert presence["DECISION_REQUIRED"] == 22
    for item in queue["items"]:
        assert item["status"] in ("PENDING_DESIGN", "PENDING_AUTHOR_DESIGN")
        assert item["confirmed_facts"] and item["candidate_space"]
        assert item["author_decision_required"] is (
            item["design_subtype"] == "MAJOR_PIVOT_REQUIRED")
    requirement = queue["requirements"][0]
    assert requirement["policy_source"] and requirement["why_required"]
    assert requirement["recommended_repair_mode"] in (
        "REPAIR_DESIGN_PROPOSAL_THEN_MANUAL_APPROVAL", "AUTHOR_DESIGN_REQUIRED")


def test_ambiguous_entity_impact(adoption) -> None:
    service, _payload = adoption
    impact = _artifact(service, "AMBIGUOUS_ENTITY_IMPACT.json")
    assert impact["ambiguous_chapter_count"] == 62
    assert impact["mutable_target_count"] + impact["not_in_batch_count"] + \
        impact["read_only_dependency_count"] == 62
    assert impact["future_repair_target_impact"] > 0
    assert impact["entities_resolved_this_round"] == 0
    mutable = [row for row in impact["rows"] if row["mutability"] == "mutable"]
    assert mutable and all(row["repair_safe"] is False for row in mutable)
    assert all(row["author_resolution_required"] is True for row in impact["rows"])


def test_m1_golden_delta_reconciliation(adoption) -> None:
    service, _payload = adoption
    golden = _artifact(service, "M1_GOLDEN_DELTA_RECONCILIATION.json")
    assert golden["delta_count"] == 10
    assert golden["old_llm_proposal_auto_adopted"] is False
    decisions = {row["legacy_label"]: row["decision"] for row in golden["rows"]}
    assert decisions["ch559"] == "AUTHOR_REVIEW"
    assert all(value == "REINSTATE_M1_BINDING"
               for label, value in decisions.items() if label != "ch559")
    for row in golden["rows"]:
        assert row["m10_story_map_value"] is not None
        assert row["current_historical_interpretation"]
        assert row["confirmed_truth_priority"] is True


def test_known_cross_chapter_facts_preserved(adoption) -> None:
    service, _payload = adoption
    facts = _artifact(service, "CROSS_CHAPTER_FACT_CHECKS.json")
    assert facts["known_confirmed_facts_preserved"] is True
    assert facts["erasure_risk_count"] == 0
    assert facts["chapter_count"] == 14
    labels = {row["legacy_label"] for row in facts["rows"]}
    assert {"ch271", "ch325", "ch350", "ch379", "ch389", "ch436", "ch437", "ch438",
            "ch449", "ch502", "ch504", "ch515", "ch526", "ch559"} <= labels
    for row in facts["rows"]:
        assert row["confirmed_truth_priority"] is True
        assert row["action"]


def test_dependency_gate_and_partial_ready(adoption) -> None:
    service, _payload = adoption
    readiness = _artifact(service, "M11_READINESS_RECOMPUTED.json")
    assert readiness["batch_count"] == 17
    counts = readiness["status_counts"]
    assert counts.get("BLOCKED_CONTENT_DESIGN", 0) >= 1
    assert counts.get("PARTIAL_READY", 0) >= 1
    batches = {row["batch_id"]: row for row in readiness["batches"]}
    batch_04 = batches["REPAIR_BATCH_04"]
    assert batch_04["status"] == "PARTIAL_READY"
    assert batch_04["ready_target_ids"] and batch_04["blocked_target_ids"]
    reasons = " ".join(batch_04["block_reasons"].values())
    assert "ch06" in reasons or "ch05" in reasons     # 上游未决语义来自 Batch 03
    assert "dependency_semantics" in readiness
    assert readiness["next_ready_batch"] == "REPAIR_BATCH_04"


def test_adoption_gate_and_truth_boundary(adoption) -> None:
    service, payload = adoption
    gate = _artifact(service, "M11_FOUNDATION_ADOPTION_GATE.json")
    assert gate["status"] == "PASS"
    assert all(gate["checks"].values()), [k for k, v in gate["checks"].items() if not v]
    assert gate["batch_04_not_executed"] is True and gate["llm_used"] is False
    assert gate["foundation_digests"]
    foundation_gate = json.loads(
        (service.foundation_dir / "HISTORICAL_IR_FOUNDATION_GATE.json")
        .read_text(encoding="utf-8"))
    assert foundation_gate["status"] == "READY"
    assert foundation_gate["source_digests"]["before"] == \
        foundation_gate["source_digests"]["after"]
    assert payload["status"] == "PASS"
    assert payload["batch_04_executed"] is False
    assert payload["content_generated"] is False
    baseline = payload["overlay"]["baseline_queue_counts"]
    assert baseline == {"SEMANTIC_CONFIRMED": 198, "LEGACY_FIELD_CONFLICT": 27,
                        "LEGACY_CONTENT_GAP": 345}
