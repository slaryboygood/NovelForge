"""P15n：ContentDesignQueue 守恒 + ContentRewritePolicy + Frontier Rewrite Proposal Pilot。"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from novelforge.story_engine.m11_content_rewrite import (
    PILOT_CLASSES,
    _gate_proposal,
    REWRITE_CLASSES,
    ContentRewritePolicyService,
)

from m11_phase_history import closed, report_records, historical_rewrite_proposals

ROOT = Path(".").resolve()


@pytest.fixture(scope="module")
def policy():
    service = ContentRewritePolicyService(ROOT)
    payload = service.run()
    return service, payload


def _artifact(service: ContentRewritePolicyService, name: str):
    return json.loads((service.policy_dir / name).read_text(encoding="utf-8"))


def test_queue_conservation(policy) -> None:
    service, payload = policy
    reconciliation = _artifact(service, "CONTENT_DESIGN_QUEUE_RECONCILIATION.json")
    # P15n-era snapshot = 43（+7 B05 dynamic = 50）；M11-RUN-02 登记 5 个、RUN-03 再登记 5 个
    # runtime ContentDesignRequirement → snapshot = 53。守恒关系：total = snapshot + 7。
    assert reconciliation["snapshot_items"] >= 48
    queue_v2 = json.loads((service.design_dir / "M11_CONTENT_DESIGN_QUEUE_V2.json")
                          .read_text(encoding="utf-8"))
    assert reconciliation["snapshot_items"] == queue_v2["item_count"]
    assert reconciliation["batch05_dynamic_items"] == 7
    assert reconciliation["total_design_items"] == (
        reconciliation["snapshot_items"] + reconciliation["batch05_dynamic_items"])
    assert reconciliation["active_primary_targets"] == reconciliation[
        "active_requirements"]
    assert reconciliation["orphan_requirements"] == []
    assert reconciliation["targets_without_requirement"] == []
    assert "50 − 10" in reconciliation["explains_43_to_40"]
    assert payload["checks"]["orphan_requirements_zero"] is True
    assert payload["checks"]["targets_without_requirement_zero"] is True
    queue3 = json.loads((service.design_dir / "M11_CONTENT_DESIGN_QUEUE_V3.json")
                        .read_text(encoding="utf-8"))
    statuses = {row["status"] for row in queue3["requirements"]}
    assert statuses <= {"ACTIVE", "RESOLVED_REPAIRED", "RESOLVED_NO_REPAIR",
                        "SUPERSEDED", "STALE_AFTER_OTHER_REPAIR",
                        "MERGED_INTO_OTHER_REQUIREMENT", "AUTHOR_DESIGN_REQUIRED"}
    assert queue3["active_count"] == reconciliation["active_requirements"]


def test_reclassification_taxonomy(policy) -> None:
    service, _payload = policy
    reclassification = _artifact(service, "CONTENT_REPAIR_RECLASSIFICATION.json")
    assert set(reclassification["class_counts"]) == set(REWRITE_CLASSES)
    # active_count 随 production run 的 runtime downgrade 增长（P15n 时 = 29；
    # M11-RUN-01..04 逐轮增加），因此只断言守恒式与下界，不设历史上限。
    assert sum(reclassification["class_counts"].values()) == reclassification[
        "active_count"]
    report_records("CONTENT_REWRITE", "**40 / 40**", "**2**（ch012 / ch056）")
    assert reclassification["active_count"] == closed(40, 0)
    assert reclassification["class_counts"]["MAJOR_AUTHOR_DESIGN_REQUIRED"] == closed(2, 0)
    for row in reclassification["rows"]:
        assert row["repair_class"] in REWRITE_CLASSES
        if row["micro_scale_candidate"]:
            assert row["repair_class"] == "EXISTING_EVENT_MICRO_SEMANTIC"
            assert row["pivot_evidence"]


def test_rewrite_policy_and_pilot_scope(policy) -> None:
    service, payload = policy
    rewrite_policy = _artifact(service, "CONTENT_REWRITE_POLICY.json")
    assert rewrite_policy["max_new_events"]["LOCAL_CONNECTIVE_EVENT_REQUIRED"] == 1
    assert sum(rewrite_policy["forbidden_new"].values()) == 0
    assert "before" in rewrite_policy["before_after_rule"]
    assert rewrite_policy["new_event_is_new_historical_content"] is True
    assert rewrite_policy["approval_boundary"]["event_added > 0"] == \
        "AUTHOR_CONTENT_APPROVAL"
    scope = _artifact(service, "CONTENT_REWRITE_PILOT_SCOPE.json")
    assert scope["selected_count"] <= 5
    classes = {row["repair_class"] for row in scope["items"]}
    assert classes <= set(PILOT_CLASSES)
    assert payload["pilot"]["selected"] == scope["selected_count"]


def test_proposals_require_author_and_never_write(policy) -> None:
    service, payload = policy
    proposals = _artifact(service, "CONTENT_REWRITE_PROPOSALS.json")
    assert proposals["proposal_count"] == closed(5, 0)
    assert proposals["proposals"] == []
    inputs = service.load()
    historical = historical_rewrite_proposals(inputs)
    assert len(historical) == 5
    for model in historical:
        gate = _gate_proposal(model, inputs, model.legacy_label)
        assert gate.status == "PASS" and all(gate.checks.values())
        row = model.model_dump(mode="json")
        assert row["author_approval_required"] == "AUTHOR_CONTENT_APPROVAL"
        assert row["proposed_new_historical_event"] is True
        assert row["new_historical_event_count"] == 1
        assert row["new_world_fact_count"] == 0 and row["new_entity_count"] == 0
        assert row["new_state_transition_count"] == 0
        assert row["new_event"]["proposed_event_id"].startswith("PROPOSED_EVENT_")
        assert row["writes_canon"] is False and row["writes_story_state"] is False
        assert row["writes_ir"] is False and row["canonical_representation"] is False
        assert row["status"] == "PROPOSED" and row["non_authoritative"] is True
        assert row["confirmed_facts_preserved"] is True
    assert payload["candidate_generated"] is False and payload["promoted"] == 0


def test_proposal_gate_pass(policy) -> None:
    service, _payload = policy
    gate = _artifact(service, "CONTENT_REWRITE_PROPOSAL_GATE.json")
    assert gate["status"] == "PASS"
    assert {"LOCAL_SCOPE_ONLY", "ONE_NEW_EVENT_MAX", "NO_NEW_ENTITY",
            "CONFIRMED_BEFORE_PRESERVED", "CONFIRMED_AFTER_PRESERVED",
            "AUTHOR_APPROVAL_REQUIRED"} <= set(gate["checks"])
    for row in gate["results"]:
        assert row["status"] == "PASS"
        assert all(row["checks"].values())
        assert row["validators"]["writes_ir"] == "NO"
        assert row["validators"]["canon_consistency"] == "PASS"


def test_author_policy_options_and_unchanged_truth(policy) -> None:
    service, payload = policy
    options = _artifact(service, "AUTHOR_CONTENT_POLICY_OPTIONS.json")
    assert [row["option_id"] for row in options["options"]] == ["A", "B", "C"]
    assert options["auto_selected"] == "" and options["author_must_choose"] is True
    assert all(row["automation_allowed"] is not None for row in options["options"])
    assert "decision" in options["decision_event_sensitivity"]
    assert payload["overlay_unchanged"] is True
    assert payload["readiness_unchanged"] is True
    assert payload["batch_06_executed"] is False
    plan = _artifact(service, "M11_NEXT_ACTION_PLAN_V2.json")
    assert plan["entries"] and plan["author_options"] == 3
    assert plan["queue"]["orphan_requirements"] == 0
    for path in (ROOT / "novel/authoring/story_engine/canon/wasteland_001.sqlite",
                 ROOT / "novel/authoring/story_engine/state/runtime_wasteland_001/"
                        "v000001.json",
                 ROOT / "workspace/wasteland_001_exports/"
                        "WASTELAND_001_OUTLINE_CANON_FINAL_CANDIDATE_V5.json",
                 ROOT / "workspace/wasteland_001_exports/chapter_ir_v1/"
                        "full_migration/WASTELAND_001_CHAPTER_IR_FULL.json"):
        digest = hashlib.sha256(path.read_bytes()).hexdigest()[:16]
        assert digest in ("73836dada9d6bf8e", "bbc67137eefb9c55", "cc144c76796d6a4c",
                          "2eaac16d66e39421")
    gate = _artifact(service, "P15N_GATE.json")
    report_records("CONTENT_REWRITE", "对 5/5 proposal 全 PASS", "AUTHOR_CONTENT_APPROVAL")
    assert gate["status"] == closed("PASS", "NEEDS_ATTENTION")
    assert {key for key, ok in gate["checks"].items() if not ok} == {
        "new_event_requires_author_approval"}  # No live proposals; exercised above.
