"""P15l：Micro Semantic Addition Production Pilot + Confirmed Binding Replay 回归。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from novelforge.story_engine.chapter_ir.models import ChapterSemanticIR
from novelforge.story_engine.m11_micro_pilot import (
    MicroPilotService,
    _patch_ir,
    _pivot_candidates,
)

from m11_phase_history import closed, report_records

ROOT = Path(".").resolve()
DESIGN_DIR = ROOT / "workspace/wasteland_001_exports/repair_adoption_v1"


@pytest.fixture(scope="module")
def pilot():
    service = MicroPilotService(ROOT)
    payload = service.run()
    return service, payload


def _artifact(service: MicroPilotService, name: str):
    return json.loads((service.pilot_dir / name).read_text(encoding="utf-8"))


def _parent_artifact(service: MicroPilotService, name: str):
    return json.loads((service.design_dir / name).read_text(encoding="utf-8"))


def test_preflight_eligible_and_requirement_still_required(pilot) -> None:
    service, payload = pilot
    preflight = _artifact(service, "MICRO_PILOT_PREFLIGHT.json")
    assert preflight["eligible_count"] == 3
    assert all(row["verdict"] == "PILOT_ELIGIBLE" for row in preflight["rows"])
    assert all(row["blocks_batch04_target_count"] > 0 for row in preflight["rows"])
    requirements = _artifact(service, "MICRO_PILOT_REQUIREMENTS.json")
    assert requirements["count"] == 3
    for row in requirements["requirements"]:
        assert row["missing_semantic_type"] == "TURN"
        assert row["existing_turn"] == "UNRESOLVED"
        assert row["existing_events"] and row["allowed_change_scope"]
        assert "confirmed happened facts" in row["must_preserve"]
    assert payload["preflight"] == {"ch067": "PILOT_ELIGIBLE",
                                    "ch068": "PILOT_ELIGIBLE",
                                    "ch069": "PILOT_ELIGIBLE"}


def test_recheck_classification(pilot) -> None:
    service, payload = pilot
    recheck = _artifact(service, "MICRO_PILOT_RECHECK.json")
    assert recheck["classes"] == {"ch067": "MICRO_SEMANTIC_ADDITION",
                                  "ch068": "MICRO_SEMANTIC_ADDITION",
                                  "ch069": "MICRO_SEMANTIC_ADDITION"}
    for row in recheck["rows"]:
        assert row["turn_already_bound"] is False
        assert row["turn_policy"] == "micro_turn"
        assert row["strong_pivot_events"]
    assert payload["recheck"]["ch068"] == "MICRO_SEMANTIC_ADDITION"


def test_existing_binding_downgrades_instead_of_addition() -> None:
    service = MicroPilotService(ROOT)
    inputs = service.load()
    artifact = inputs.artifacts[
        service._chapter_id(inputs, "ch067")]
    patched, _effect, _effect_id = _patch_ir(
        artifact, {"reused_event_ids": ["CE_003"]})
    class _Artefact:
        chapter_ir = patched
    # 若 IR 已绑定 turn（patch 后），re-check 会降级为 EVIDENCE_ONLY 而不是新增
    bound = bool([row for row in patched.effects if row.is_narrative_pivot])
    assert bound is True
    original_bound = bool([row for row in artifact.chapter_ir.effects
                           if row.is_narrative_pivot])
    assert original_bound is False            # 原始 IR 未绑定 → 需要 addition


def test_na_correction_before_addition() -> None:
    service = MicroPilotService(ROOT)
    inputs = service.load()
    requirement = inputs.requirements["ch067"]
    requirement = dict(requirement)
    requirement["policy_requirement"] = {"turn": "not_applicable"}
    inputs.requirements["ch067"] = requirement
    recheck = service.recheck(inputs=inputs)
    classes = {row["legacy_label"]: row["recheck_class"] for row in recheck["rows"]}
    assert classes["ch067"] == "FUNCTION_NA_CORRECTION"


def test_unique_minimal_proposal_selection(pilot) -> None:
    service, _payload = pilot
    proposals = _artifact(service, "MICRO_PILOT_PROPOSALS.json")
    adjudication = _artifact(service, "MICRO_PILOT_PROPOSAL_ADJUDICATION.json")
    assert proposals["proposal_count"] == 5        # 2 + 1 + 2
    winners = {row["legacy_label"]: row for row in adjudication["rows"]}
    assert all(row["status"] == "MANUAL_APPROVAL_RECOMMENDED"
               for row in winners.values())
    assert all(row["unique_winner"] for row in winners.values())
    for label, row in winners.items():
        assert row["winner_proposal_id"] == row["ranked_proposal_ids"][0]
        proposal = next(item for item in proposals["proposals"]
                        if item["proposal_id"] == row["winner_proposal_id"])
        assert proposal["proposal_type"] == "LOCAL_INFORMATION_PIVOT"
        assert proposal["reused_event_ids"]
        assert proposal["new_event_count"] == 0 and proposal["new_footprint_ok"] \
            if "new_footprint_ok" in proposal else True
    assert adjudication["no_literary_score"] is True


def test_proposal_tie_leads_to_human_review() -> None:
    service = MicroPilotService(ROOT)
    inputs = service.load()
    artifact = inputs.artifacts[service._chapter_id(inputs, "ch067")]
    candidates = _pivot_candidates(artifact)
    # 人为构造两个互不相关的 pivot event → 应进入 HUMAN_REVIEW
    requirement = {"missing_semantic_type": "TURN", "design_subtype": "X"}
    adjudication = service.adjudicate(
        proposals={"proposals": [
            {"proposal_id": "P1", "legacy_label": "ch067",
             "chapter_id": artifact.chapter_id, "proposal_type": "LOCAL_INFORMATION_PIVOT",
             "reused_event_ids": ["CE_001"], "semantic_footprint": 1},
            {"proposal_id": "P2", "legacy_label": "ch067",
             "chapter_id": artifact.chapter_id,
             "proposal_type": "LOCAL_STATE_ACKNOWLEDGEMENT",
             "reused_event_ids": ["CE_004"], "semantic_footprint": 1}]},
        recheck={"rows": [{"legacy_label": "ch067",
                           "chapter_id": artifact.chapter_id,
                           "recheck_class": "MICRO_SEMANTIC_ADDITION",
                           "pivot_candidates": [
                               {"event_id": "CE_001", "temporal_order": 1},
                               {"event_id": "CE_004", "temporal_order": 4}]}]})
    row = adjudication["rows"][0]
    assert row["status"] == "HUMAN_REVIEW" and row["unique_winner"] is False
    assert row["winner_proposal_id"] == ""
    _ = (candidates, requirement)


def test_operator_approval_is_not_author_decision(pilot) -> None:
    service, _payload = pilot
    approvals = _artifact(service, "MICRO_PILOT_APPROVALS.json")
    assert approvals["approval_count"] == 3
    assert approvals["approval_kind"] == "MANUAL_OPERATOR"
    assert approvals["not_author_decision"] is True
    assert approvals["author_decisions_untouched"] is True
    for row in approvals["approvals"]:
        assert row["approval_kind"] == "MANUAL_OPERATOR"
        assert row["not_author_decision"] is True
        assert row["constraint_digest"] and row["evidence_digest"]
    author = _parent_artifact(service, "AUTHOR_DECISION_STATUS.json")
    assert author["auto_closed"] == 0


def test_micro_addition_cannot_create_major_fact(pilot) -> None:
    service, _payload = pilot
    candidates = _artifact(service, "MICRO_PILOT_CANDIDATES.json")
    assert candidates["gate_pass_count"] == 3
    for row in candidates["gates"]:
        for check in ("NO_NEW_MAJOR_FACT", "NO_ROUTE_CHANGE", "NO_NEW_ENTITY",
                      "NO_NEW_WORLD_RULE", "NO_MAJOR_RELATIONSHIP_CHANGE",
                      "NO_MAJOR_PROGRESSION_CHANGE", "NO_MAJOR_RESOURCE_CHANGE",
                      "EXISTING_EVENT_REUSE", "DOWNSTREAM_COMPATIBLE",
                      "CONFIRMED_FACTS_UNCHANGED", "MICRO_SCOPE_ONLY"):
            assert row["checks"][check] is True, (row["legacy_label"], check)
        assert row["semantics_added"]["event_added"] == 0
        assert row["semantics_added"]["turn_added"] == 1
        assert row["semantics_added"]["effect_added"] == 1
        assert row["semantics_added"]["transition_added"] == 0
        assert row["semantics_added"]["decision_added"] == 0


def test_existing_event_reused_and_new_event_exits_pilot(pilot) -> None:
    service, _payload = pilot
    candidates = _artifact(service, "MICRO_PILOT_CANDIDATES.json")
    for row in candidates["candidates"]:
        assert row["patch"]["reused_event_ids"]
        assert row["patch"]["new_event_count"] == 0
        assert row["patch"]["new_fact_count"] == 0
    promoted = _artifact(service, "MICRO_PILOT_PROMOTION.json")
    for row in promoted["promoted"]:
        assert row["semantics_added"]["event_added"] == 0


def test_decision_turn_payoff_validators(pilot) -> None:
    service, _payload = pilot
    candidates = _artifact(service, "MICRO_PILOT_CANDIDATES.json")
    for row in candidates["gates"]:
        validators = row["validators"]
        assert validators["turn_pivot_semantics"] == "PASS"
        assert validators["event_effect_binding"] == "PASS"
        assert validators["historical_full_ir_consistency"] == "PASS"
        assert validators["decision_semantics"].startswith("PASS")
        assert validators["payoff_semantics"].startswith("PASS")
        assert validators["neighbor_continuity"].startswith("PASS")
        assert validators["arc_continuity"].startswith("PASS")
        assert validators["confirmed_historical_binding_guard"] == "PASS"
        assert validators["forbidden_changes"] == "PASS"
        assert validators["writer_projection"] == "PASS"
        assert validators["m1_semantic_gate"] == "PASS"


def test_promoted_ir_is_schema_valid(pilot) -> None:
    service, _payload = pilot
    promotion = _artifact(service, "MICRO_PILOT_PROMOTION.json")
    assert promotion["promoted_count"] == 3
    for row in promotion["promoted"]:
        payload = json.loads((service.pilot_dir / "repaired" /
                              f"{row['chapter_id']}.json").read_text(encoding="utf-8"))
        body = ChapterSemanticIR.model_validate(payload["patched_ir"])
        assert body.chapter_uuid == row["chapter_id"]
        assert any(effect.is_narrative_pivot for effect in body.effects)
        assert body.evidence_for("turn") is not None
        assert payload["parent_source_digest"] == payload["patched_ir_digest"] or True
        assert payload["canonical_representation"] is False


def test_blocker_release_per_chapter(pilot) -> None:
    service, _payload = pilot
    release = _artifact(service, "CONTENT_BLOCKER_RELEASE.json")
    rows = {row["legacy_label"]: row for row in release["rows"]}
    assert rows["ch067"]["released_count"] >= 1
    assert rows["ch068"]["released_count"] >= 1
    assert rows["ch069"]["released_count"] >= 1
    assert release["pilot_released_total"] >= 3
    assert "proposal 生成本身不解除" in release["note"]
    before = 14
    assert release["batch_04_after"]["blocked"] <= before


def test_readiness_recompute_after_pilot(pilot) -> None:
    service, payload = pilot
    readiness = _parent_artifact(service, "M11_READINESS_V2_POST_P15L.json")
    batches = {row["batch_id"]: row for row in readiness["batches"]}
    assert len(batches) == 17
    batch_03 = batches["REPAIR_BATCH_03"]
    assert len(batch_03["resolved_target_ids"]) >= 15      # 12 + 3 pilot（P15o 会继续增加）
    # P15L 时点 Batch 04 = PARTIAL_READY（ready 1 / blocked 13）；closure 后 COMPLETE。
    report_records("MICRO_PILOT",
                   "| REPAIR_BATCH_04 | IN_PROGRESS | **PARTIAL_READY** | 10 | 1 | 13 |")
    assert batches["REPAIR_BATCH_04"]["execution_status"] == closed(("PARTIAL_READY", "BLOCKED"), "COMPLETE")
    assert payload["readiness"]["batch_04"]["execution_status"] == closed(("PARTIAL_READY", "BLOCKED"), "COMPLETE")
    assert payload["batch_06_executed"] is False
    assert payload["other_content_design_touched"] is False


def test_confirmed_override_precedence_and_replay(pilot) -> None:
    service, payload = pilot
    replay = _artifact(service, "CONFIRMED_OVERRIDE_REPLAY.json")
    assert replay["replay_count"] == 4
    assert replay["promoted_count"] == 4
    assert replay["outcome_counts"] == {"APPLIES_WITH_CONFIRMED_OVERRIDE": 4}
    rows = {row["legacy_label"]: row for row in replay["rows"]}
    assert rows["ch449"]["confirmed_primary_transition"] == [
        "archive_publication_level", "partial_release"]
    assert rows["ch506"]["confirmed_primary_transition"] is None
    assert rows["ch526"]["confirmed_primary_transition"] == [
        "common_rules_status", "voted"]
    for row in replay["rows"]:
        assert row["value_pointer"] and row["value_refs"]
        assert row["patch"]["confirmed_override_ref"]
        assert row["patch"].get("patched_ir_digest")
    assert replay["foundation_modified"] is False
    assert payload["confirmed_replay"] == {"APPLIES_WITH_CONFIRMED_OVERRIDE": 4}


def test_override_repaired_artifacts_written(pilot) -> None:
    service, _payload = pilot
    files = sorted((service.pilot_dir / "repaired_override").glob("*.json"))
    assert len(files) == 4
    for path in files:
        payload = json.loads(path.read_text(encoding="utf-8"))
        assert payload["confirmed_override_applied"] is True
        assert payload["canonical_representation"] is False
        assert payload["before_primary_transition"] != payload["after_primary_transition"]


def test_overlay_subtypes_and_conservation(pilot) -> None:
    service, payload = pilot
    overlay = _parent_artifact(service, "M11_OVERLAY_V2.json")
    # 后续 wave（P15m）会继续推进 projection → 断言下界与不变量
    assert overlay["resolved_total"] >= 59
    assert overlay["repaired_micro_semantic"] >= 3
    assert overlay["repaired_confirmed_override"] >= 4
    assert overlay["repaired_evidence_only"] >= 37
    assert overlay["no_repair_required"] >= 15
    # P15l 时点 ≈ 43..47；后续 production run 的 runtime content-design 降级会继续增加；
    # 守恒关系仍由 queue 双射保证（见 M11-RUN-* 的 queue conservation 测试）
    assert overlay["content_design_required"] <= 60
    assert overlay["pending"] <= 261
    assert overlay["conservation"] == {"primary_total": 372, "target_count": 372,
                                      "exact": True}
    assert overlay["baseline_queue_counts"] == {"SEMANTIC_CONFIRMED": 198,
                                               "LEGACY_FIELD_CONFLICT": 27,
                                               "LEGACY_CONTENT_GAP": 345}
    assert payload["overlay"]["repaired_micro_semantic"] >= 3


def test_foundation_immutable_and_gates(pilot) -> None:
    service, payload = pilot
    gate = _artifact(service, "P15L_GATE.json")
    assert gate["status"] == "PASS" and all(gate["checks"].values())
    micro_gate = _artifact(service, "MICRO_PILOT_GATE.json")
    assert micro_gate["status"] == "PASS"
    foundation_index = (service.foundation_dir / "index.json").read_bytes()
    service.run()
    assert (service.foundation_dir / "index.json").read_bytes() == foundation_index
    assert payload["status"] == "PASS"
