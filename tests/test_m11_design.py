"""P15h：M11 Content Design & Decision Preparation + Entity Triage + Readiness Hardening。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from novelforge.story_engine.m11_design import (
    ESCALATION_FORBIDDEN,
    M11DesignDecisionService,
    RepairDesignProposal,
    _escalation_gate,
    confirmed_binding_guard,
)
from novelforge.story_engine.repair import (
    ChapterRepairCandidate,
    RepairOp,
    WastelandRepairService,
)

ROOT = Path(".").resolve()


@pytest.fixture(scope="module")
def design(tmp_path_factory: pytest.TempPathFactory):
    service = M11DesignDecisionService(ROOT)
    payload = service.run()
    return service, payload


def _artifact(service: M11DesignDecisionService, name: str):
    return json.loads((service.design_dir / name).read_text(encoding="utf-8"))


def test_design_requirements_36(design) -> None:
    service, _payload = design
    payload = _artifact(service, "REPAIR_DESIGN_REQUIREMENTS.json")
    assert payload["requirement_count"] == 36
    assert payload["micro_count"] == 34 and payload["major_count"] == 2
    assert payload["content_generated"] is False
    row = payload["requirements"][0]
    for key in ("why_required", "policy_requirement", "existing_events",
                "confirmed_facts", "must_preserve", "must_not_introduce",
                "available_design_space", "foundation_artifact_ref",
                "knowledge_constraints", "relationship_constraints",
                "resource_constraints", "progression_constraints",
                "location_constraints", "information_constraints",
                "foreshadow_constraints"):
        assert key in row
    assert "新世界规则" in row["must_not_introduce"]
    assert row["author_design_required"] in (True, False)


def test_micro_proposals_cover_34_items(design) -> None:
    service, _payload = design
    payload = _artifact(service, "MICRO_REPAIR_DESIGN_PROPOSALS.json")
    assert payload["item_count"] == 34
    assert payload["proposal_count"] == 102
    assert payload["escalation_gate"] == "PASS"
    assert payload["writes_ir"] is False and payload["content_generated"] is False
    for row in payload["proposals"]:
        assert row["non_authoritative"] is True and row["writes_ir"] is False
        assert row["confirmed_facts_preserved"] is True
        assert row["forbidden_changes_checked"] is True
        assert row["escalation_gate"] == "PASS"
        assert row["proposal_type"].startswith("LOCAL_") or \
            row["proposal_type"] in ("CAUSAL_BRIDGE", "DECISION_BINDING")
    assert all(1 <= value <= 3 for value in payload["proposals_per_item"].values())


def test_micro_proposal_cannot_escalate_to_major() -> None:
    ok = RepairDesignProposal(proposal_id="x", design_item_id="d", chapter_id="c",
                              semantic_change="绑定既有信息变化",
                              relationship_effect="LOCAL")
    assert _escalation_gate(ok) == ("PASS", [])
    bad = RepairDesignProposal(proposal_id="y", design_item_id="d", chapter_id="c",
                               semantic_change="新增一名新敌人并永久改变路线",
                               relationship_effect=ESCALATION_FORBIDDEN[0])
    status, violations = _escalation_gate(bad)
    assert status == "FAIL" and violations


def test_major_briefs_require_author_design(design) -> None:
    service, _payload = design
    payload = _artifact(service, "MAJOR_AUTHOR_DESIGN_BRIEFS.json")
    assert payload["brief_count"] == 2
    assert payload["auto_design_generated"] is False
    labels = {row["legacy_label"] for row in payload["briefs"]}
    assert labels == {"ch012", "ch056"}
    for row in payload["briefs"]:
        assert row["what_author_must_decide"] and row["possible_directions"]
        assert len(row["possible_directions"]) >= 2
        assert row["tradeoffs"] and row["blocking_scope"] and row["non_authoritative"]


def test_ch036_brief_preserved(design) -> None:
    service, _payload = design
    brief = _artifact(service, "AUTHOR_DECISION_BRIEF_ch036.json")
    assert brief["legacy_label"] == "ch036" and brief["auto_closed"] is False
    assert [option["option_id"] for option in brief["options"]] == ["A", "B"]
    assert brief["ambiguity_type"]
    assert all(option["changes_happened_fact"] is False for option in brief["options"])
    assert brief["recommended_default"] and brief["why_still_not_automatic"]


def test_ch559_brief_sources_and_conflict(design) -> None:
    service, _payload = design
    brief = _artifact(service, "AUTHOR_DECISION_BRIEF_ch559.json")
    assert brief["auto_closed"] is False and len(brief["sources"]) >= 3
    sources = " ".join(str(row["source"]) for row in brief["sources"])
    assert "M1 golden" in sources and "M10 story map" in sources
    assert "common_rules_status" in json.dumps(brief, ensure_ascii=False)
    assert brief["options"][0]["fits_existing_evidence"]


def test_ch063_manual_brief(design) -> None:
    service, _payload = design
    brief = _artifact(service, "MANUAL_REPAIR_BRIEF_ch063.json")
    assert brief["status"] == "MANUAL_REQUIRED"
    assert brief["legacy_world_state_change"]
    assert brief["foundation_transition"] and brief["candidate_domains"]
    salt = next(row for row in brief["candidate_domains"]
                if row["domain"] == "salt_route_control")
    assert salt["adoptable_automatically"] is False and salt["contradicting_evidence"]
    assert "关键词规则" in brief["why_foundation_domain_not_automatic"]
    assert brief["safe_representation_operations"] and brief["forbidden_operations"]


def test_entity_clustering_covers_62(design) -> None:
    service, _payload = design
    queue = _artifact(service, "M11_ENTITY_RESOLUTION_QUEUE.json")
    assert queue["chapter_count"] == 62
    assert 0 < queue["cluster_count"] <= 62
    assert queue["entity_truth_modified"] is False
    counts = queue["status_counts"]
    assert sum(counts.values()) == queue["cluster_count"]
    assert counts.get("AUTHOR_ENTITY_DECISION_REQUIRED", 0) == 0
    assert counts.get("NON_BLOCKING_GENERIC_REFERENCE", 0) >= 1
    assert counts.get("CONTEXT_RESOLVABLE_PROPOSAL", 0) >= 1


def test_generic_ambiguity_does_not_block(design) -> None:
    service, _payload = design
    queue = _artifact(service, "M11_ENTITY_RESOLUTION_QUEUE.json")
    readiness = _artifact(service, "M11_READINESS_HARDENED.json")
    reasons = {chapter_id: reason for row in readiness["batches"]
               for chapter_id, reason in (row["block_reason_by_target"] or {}).items()}
    blocked_entity = {chapter_id for chapter_id, reason in reasons.items()
                      if "BLOCKED_ENTITY" in reason}
    for cluster in queue["clusters"]:
        if cluster["resolution_status"] != "NON_BLOCKING_GENERIC_REFERENCE":
            continue
        assert cluster["repair_can_proceed_without_identity"] is True
        assert cluster["requires_exact_identity"] is False
        # 该 cluster 自身不因 identity 阻塞；chapter 若有 blocker 必须是其它原因
        # （例如 ch027 的 P15g evidence-ready 状态）
        for chapter_id in set(cluster["chapter_ids"]) & blocked_entity:
            assert "evidence-ready" in reasons.get(chapter_id, "")


def test_identity_required_ambiguity_blocks(design) -> None:
    service, _payload = design
    queue = _artifact(service, "M11_ENTITY_RESOLUTION_QUEUE.json")
    readiness = _artifact(service, "M11_READINESS_HARDENED.json")
    blocked_entity = {chapter_id for row in readiness["batches"]
                      for chapter_id, reason in (row["block_reason_by_target"] or {}).items()
                      if reason.startswith("BLOCKED_ENTITY_AMBIGUITY")}
    targeted = [cluster for cluster in queue["clusters"]
                if cluster["resolution_status"] == "CONTEXT_RESOLVABLE_PROPOSAL"]
    assert targeted and blocked_entity
    affected = {chapter_id for cluster in targeted
                for chapter_id in cluster["affected_repair_targets"]}
    assert affected <= blocked_entity
    assert all(cluster["requires_exact_identity"] for cluster in targeted)


def test_confirmed_binding_precedence_records(design) -> None:
    service, _payload = design
    payload = _artifact(service, "CONFIRMED_BINDING_RESOLUTION.json")
    assert payload["override_chapter_count"] == 9
    assert payload["override_count"] >= 9
    assert payload["author_review_count"] == 1
    assert payload["new_truth_created"] is False
    assert payload["guard_code"] == "CONFIRMED_HISTORICAL_BINDING_VIOLATION"
    assert payload["guard_severity"] == "ERROR"
    for row in payload["resolutions"]:
        assert row["status"] == "CONFIRMED_OVERRIDE_ACTIVE"
        assert row["value_pointer"] and row["value_refs"] and row["value_digest"]
        assert row["display_value_authoritative"] is False
    guarded_labels = {row["legacy_label"] for row in payload["guarded_bindings"]}
    assert len(guarded_labels) == 14


def test_repair_engine_confirmed_binding_guard(design) -> None:
    service, _payload = design
    repair = WastelandRepairService(ROOT)
    guards = repair.confirmed_binding_guards()
    assert "ch379" in guards and "primary_transition" in guards["ch379"]["aspects"]
    candidate = ChapterRepairCandidate(
        candidate_id="T1", chapter_id="x", legacy_label="ch379",
        proposed_patch=[RepairOp(op="REBIND_STATE_REFERENCE",
                                 field_name="world_state_change",
                                 reason="test")])
    violations = repair.confirmed_binding_violations([candidate])
    assert violations and "ch379" in violations[0]
    safe = ChapterRepairCandidate(
        candidate_id="T2", chapter_id="x", legacy_label="ch379",
        proposed_patch=[RepairOp(op="REBIND_EVIDENCE", field_name="turn", reason="t")])
    assert repair.confirmed_binding_violations([safe]) == []
    direct = confirmed_binding_guard(label="ch271", changed_fields=["state_transition"],
                                     design_dir=str(service.design_dir))
    assert direct and "ch271" in direct[0]


def test_readiness_hardening_and_batch_04(design) -> None:
    service, _payload = design
    readiness = _artifact(service, "M11_READINESS_HARDENED.json")
    # P15i 执行 Batch 04 后，live readiness 会前移；P15h 的 projection 快照保留在
    # M11_READINESS_HARDENED_PRE_BATCH04.json（本测试以快照为准）
    snapshot = json.loads((service.design_dir /
                           "M11_READINESS_HARDENED_PRE_BATCH04.json")
                          .read_text(encoding="utf-8")) \
        if (service.design_dir / "M11_READINESS_HARDENED_PRE_BATCH04.json").is_file() \
        else readiness
    assert len(readiness["batches"]) == 17
    counts = snapshot["target_status_counts"]
    assert counts["RESOLVED"] == 25 and counts["READY"] > 0
    assert counts["BLOCKED_CONTENT_DESIGN"] == 42
    assert counts["BLOCKED_ENTITY_AMBIGUITY"] == 17
    assert counts["BLOCKED_AUTHOR_DECISION"] == 1
    assert counts["BLOCKED_MANUAL_REPAIR"] == 1
    assert counts["BLOCKED_CONFIRMED_BINDING_CONFLICT"] >= 1
    batch_04 = snapshot["batch_04"]
    assert batch_04["status"] == "PARTIAL_READY"
    assert len(batch_04["ready_target_ids"]) == 18
    assert len(batch_04["blocked_target_ids"]) == 6
    assert batch_04["blocker_counts"] == {"BLOCKED_CONTENT_DESIGN": 6}
    assert not [reason for reason in batch_04["block_reason_by_target"].values()
                if "ENTITY" in reason]
    later = next(row for row in snapshot["batches"]
                 if row["batch_id"] == "REPAIR_BATCH_08")
    assert any("ENTITY" in reason for reason in
               later["block_reason_by_target"].values())


def test_next_action_plan_localized(design) -> None:
    service, payload = design
    plan = _artifact(service, "M11_NEXT_ACTION_PLAN.json")
    assert plan["execution_order"][0] == "author_decisions"
    assert plan["author_decision_count"] == 4
    kinds = [row["kind"] for row in plan["author_decisions"]]
    assert kinds == ["AUTHOR_DECISION", "AUTHOR_DECISION", "AUTHOR_DESIGN",
                     "MANUAL_REPAIR"]
    assert plan["micro_design_approvals"]["item_count"] == 34
    assert plan["micro_design_approvals"]["proposal_count"] == 102
    assert plan["safe_targets"][0]["ready_target_ids"]
    assert plan["batch_04_executed"] is False and plan["content_generated"] is False
    assert payload["next_action_count"] == 4


def test_no_content_generation_and_gate_pass(design) -> None:
    service, payload = design
    gate = _artifact(service, "P15H_GATE.json")
    assert gate["status"] == "PASS"
    assert all(gate["checks"].values()), [k for k, v in gate["checks"].items() if not v]
    assert gate["digests_before"] == gate["digests_after"]
    assert payload["content_generated"] is False and payload["repair_promoted"] is False
    assert payload["batch_04_executed"] is False
    assert payload["status"] == "PASS"
