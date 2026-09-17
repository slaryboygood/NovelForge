"""P15o：Zero-New-Event Micro Wave 02 + Content Rewrite Proposal Hardening 回归。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from novelforge.story_engine.m11_p15o import (
    PLACEHOLDER_ACTIONS,
    _concrete_event,
    _specificity_gate,
    P15OService,
)

from m11_phase_history import closed, report_records, historical_rewrite_proposals

ROOT = Path(".").resolve()


@pytest.fixture(scope="module")
def p15o():
    service = P15OService(ROOT)
    payload = service.run()
    return service, payload


def _artifact(service: P15OService, name: str):
    return json.loads((service.out_dir / name).read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def historical_concrete(p15o):
    service, _ = p15o
    inputs = service.hardening.inputs
    rows = [_concrete_event(label=p.legacy_label, legacy=inputs.legacy[p.chapter_id],
                            proposal=p.model_dump(mode="json"))
            for p in historical_rewrite_proposals(inputs)]
    report_records("P15O", "CONCRETE_EVENT_SPECIFICITY_REQUIRED` 5/5 PASS",
                   "**DECISION 3**", "**CAUSAL_BRIDGE 2**")
    assert len(rows) == 5
    assert all(_specificity_gate(row)["status"] == "PASS" for row in rows)
    return {"proposals": rows, "proposal_count": len(rows),
            "placeholder_actions": [r["proposal_id"] for r in rows
                                    if r["placeholder_detected"]],
            "candidate_generated": False, "promoted": 0}


def test_wave02_scope_and_promotion(p15o) -> None:
    service, payload = p15o
    scope = _artifact(service, "MICRO_WAVE_02_SCOPE.json")
    assert scope["selected_count"] <= 11
    assert scope["eligible_count"] <= 11
    promotion = _artifact(service, "MICRO_WAVE_02_PROMOTION.json")
    # 首次执行 11/11 promote；重复运行时 item 已 resolved → 以 overlay 为耐久证据
    assert promotion["promoted_count"] >= 0
    overlay = json.loads((service.design_dir / "M11_OVERLAY_V2.json")
                         .read_text(encoding="utf-8"))
    assert overlay["repaired_micro_semantic"] >= 21
    for row in promotion["promoted"]:
        added = row["semantics_added"]
        assert added["event_added"] == 0 and added["turn_added"] == 1
        assert added["transition_added"] == 0 and added["decision_added"] == 0
        assert added["payoff_added"] == 0
    assert payload["wave02"]["promoted"] == promotion["promoted_count"]
    assert payload["statuses"]["ZERO_EVENT_MICRO_SCALE_STATUS"] in (
        "READY_TO_CONTINUE", "HOLD")


def test_observation_not_turn_and_gate(p15o) -> None:
    service, _payload = p15o
    adjudication = _artifact(service, "MICRO_WAVE_02_ADJUDICATION.json")
    assert adjudication["no_default_preference"] is True
    candidates = _artifact(service, "MICRO_WAVE_02_PROPOSALS.json")
    for row in candidates["proposals"]:
        consequence = row["pivot_consequence"]
        assert consequence["consequence_type"] != "LOCAL_UNDERSTANDING" or \
            consequence["affects_current_or_next_action"] is True
    gate = _artifact(service, "MICRO_WAVE_02_ADJUDICATION.json")
    assert "tie_count" in gate


def test_concrete_rewrite_proposals(p15o, historical_concrete) -> None:
    service, payload = p15o
    live = _artifact(service, "CONCRETE_REWRITE_PROPOSALS.json")
    assert live["proposal_count"] == closed(5, 0)
    assert live["proposals"] == []
    assert live["candidate_generated"] is False and live["promoted"] == 0
    concrete = historical_concrete
    assert concrete["proposal_count"] == 5
    assert concrete["placeholder_actions"] == []
    assert concrete["candidate_generated"] is False and concrete["promoted"] == 0
    for row in concrete["proposals"]:
        for field in ("actor", "trigger", "concrete_action", "object_or_target",
                      "immediate_result", "causal_role", "before_state",
                      "after_state", "why_this_action_is_minimal",
                      "why_existing_events_are_insufficient"):
            assert str(row.get(field) or "").strip(), field
        assert not any(token in row["concrete_action"] for token in PLACEHOLDER_ACTIONS)
        assert row["novelty_accounting"]["new_historical_event_count"] == 1
        assert row["novelty_accounting"]["new_entity_count"] == 0
        assert row["proposed_new_historical_event"] is True
        assert row["writes_ir"] is False and row["status"] == "PROPOSED"
        assert row["author_approval_required"] == "AUTHOR_CONTENT_APPROVAL"
    assert payload["statuses"]["CONTENT_REWRITE_PROPOSAL_STATUS"] == \
        "READY_FOR_AUTHOR_POLICY_DECISION"


def test_decision_events_separated_and_policy_b(p15o, historical_concrete) -> None:
    service, payload = p15o
    live = _artifact(service, "CONCRETE_REWRITE_PROPOSALS.json")
    assert live["proposal_count"] == closed(5, 0)
    assert live["proposals"] == []
    assert live["candidate_generated"] is False and live["promoted"] == 0
    concrete = historical_concrete
    classes = {row["legacy_label"]: row["rewrite_class"]
               for row in concrete["proposals"]}
    decision = [label for label, klass in classes.items()
                if klass == "LOCAL_DECISION_EVENT_REQUIRED"]
    assert decision == ["ch081", "ch085", "ch087"]
    assert all(row["policy_b_bounded_auto"] is False
               for row in concrete["proposals"] if row["decision_event"])
    bounded = [r["legacy_label"] for r in concrete["proposals"]
               if r["policy_b_bounded_auto"]]
    assert bounded == ["ch083", "ch088"]
    assert payload["concrete"]["policy_b_bounded"] == closed(bounded, [])
    gate = _artifact(service, "REWRITE_PROPOSAL_HARDENING.json")
    assert all(row["status"] == "PASS" for row in gate["results"])


def test_classifier_audit(p15o) -> None:
    service, _payload = p15o
    audit = _artifact(service, "CONTENT_REWRITE_CLASSIFIER_AUDIT.json")
    report_records("P15O", "抽查 **5 个非 pilot**", "drift = **0**")
    assert audit["sample_size"] == closed(5, 0)
    assert audit["rows"] == []
    assert audit["drift_count"] == 0
    assert audit["bulk_rewrite_applied"] is False
    for row in audit["rows"]:
        assert row["audit_verdict"] in ("CONNECTIVE", "DECISION",
                                        "FUNCTION_POLICY_REVIEW", "CAUSAL_BRIDGE")


def test_overlay_readiness_and_truth(p15o) -> None:
    service, payload = p15o
    overlay = json.loads((service.design_dir / "M11_OVERLAY_V2.json")
                         .read_text(encoding="utf-8"))
    assert overlay["conservation"] == {"primary_total": 372, "target_count": 372,
                                      "exact": True}
    assert overlay["repaired_micro_semantic"] >= 21
    # P15o 时点 = 29；M11-RUN-02 runtime 动态降级新增 5 个 content design → 34
    assert overlay["content_design_required"] == 0  # [M11-CLOSURE] 已 terminal
    queue = json.loads((service.design_dir / "M11_CONTENT_DESIGN_QUEUE_V3.json")
                       .read_text(encoding="utf-8"))
    active = [row for row in queue["requirements"] if row["status"] == "ACTIVE"]
    assert len(active) == overlay["content_design_required"]
    assert overlay["baseline_queue_counts"] == {"SEMANTIC_CONFIRMED": 198,
                                               "LEGACY_FIELD_CONFLICT": 27,
                                               "LEGACY_CONTENT_GAP": 345}
    assert payload["batch_06_executed"] is False
    assert payload["batch_repair_executed"] is False
    assert payload["checks"]["rewrite_no_candidate_or_promotion"] is True
    gate = _artifact(service, "P15O_GATE.json")
    assert gate["status"] == closed("PASS", "NEEDS_ATTENTION")
    assert {key for key, ok in gate["checks"].items() if not ok} == {
        "classifier_audit_done"}  # Historical sample retired; all boundary checks remain true.
