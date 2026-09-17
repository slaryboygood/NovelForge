"""M11 approved-event production path 回归（user-authorized architecture extension）。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from novelforge.story_engine.m11_approved_event import (
    AUTHORIZATION_FILE,
    GATE_CHECK_NAMES,
    GATE_FILE,
    GATE_RESULT_FILE,
    M11ApprovedEventService,
    RECONCILIATION_FILE,
    SUBTYPE,
)

from m11_phase_history import closed

ROOT = Path(".").resolve()
DESIGN_DIR = ROOT / "workspace/wasteland_001_exports/repair_adoption_v1"


@pytest.fixture(scope="module")
def approved_event():
    service = M11ApprovedEventService(ROOT)
    payload = service.run(wave_size=20)
    return service, payload


def _artifact(name: str):
    return json.loads((DESIGN_DIR / name).read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def historical_context(approved_event):
    """从 frozen approved-event 证据重建历史 root / decision 上下文。

    M11 closure 已合法推进 live state：`ROOT_BLOCKER_CANONICAL_INVENTORY` 中不再有
    CONTENT_DESIGN family root，`AUTHOR_CONTENT_CANONICAL_DECISIONS` 中 11 个已消费
    decision 也已清空。因此历史 root / decision（含历史 allowed_options）只能从
    frozen reconciliation + frozen repaired artifact + frozen approved scope 重建，
    不得用 current live state 反推。live scope 仅用于 identity 对齐断言。
    """
    service, _ = approved_event
    scope = _artifact("APPROVED_CONTENT_RESOLUTION_SCOPE.json")
    inputs = _artifact("AUTHOR_CONTENT_DECISIONS.json")
    approvals = {row["decision_id"]: row for row in inputs["decisions"]}
    assert scope["scope_frozen"] is True
    assert scope["approved_root_count"] == 55
    assert len(scope["approved_decisions"]) == 11
    decisions: dict[str, dict] = {}
    for row in scope["approved_decisions"]:
        approval = approvals[row["decision_id"]]
        assert approval["approved_by"] == "AUTHOR"
        assert approval["decision_source"] == "CURRENT_USER_INSTRUCTION"
        for root_id in row["canonical_root_ids"]:
            decisions[str(root_id)] = {
                "decision_id": row["decision_id"],
                "canonical_root_ids": list(row["canonical_root_ids"]),
                "selected_option": row["selected_option"],
                "approved_by": approval["approved_by"],
                "decision_source": approval["decision_source"],
                "decision_timestamp": approval["decision_timestamp"],
                "allowed_options": [],       # 由 frozen repaired artifact 填入
            }
    records = _artifact(RECONCILIATION_FILE)["records"]
    assert len(records) == 55
    roots: dict[str, dict] = {}
    option_ids: dict[str, list[str]] = {}
    for row in records:
        payload = _artifact(row["repaired_ref"])
        event = payload["approved_event"]
        assert payload["gate"]["status"] == "PASS"
        root_id = row["canonical_root_id"]
        decision = decisions[root_id]
        assert event["canonical_root_id"] == root_id
        assert event["chapter_id"] == row["chapter_id"]
        assert event["author_decision_ref"] == decision["decision_id"]
        assert event["selected_option"] == decision["selected_option"]
        assert event["selected_option"] in event["authorized_options"], root_id
        options = list(event["authorized_options"])
        # 同一 decision 的历史 allowed_options 必须一致，否则 decision 重建有歧义。
        assert option_ids.setdefault(decision["decision_id"], options) == options, root_id
        decision["allowed_options"] = [{"option_id": option} for option in options]
        assert root_id not in roots
        roots[root_id] = {"canonical_root_id": root_id,
                          "artifact_refs": event["artifact_refs"],
                          "chapter_id": event["chapter_id"],
                          "all_affected_targets": event["downstream_targets"]}
    assert set(roots) == service.approved_root_ids
    return roots, decisions


def _historical(historical_context, index: int = 0):
    roots, decisions = historical_context
    root_id = sorted(roots)[index]
    return root_id, roots[root_id], decisions[root_id]


def test_authorization_artifact_shape() -> None:
    payload = _artifact(AUTHORIZATION_FILE)
    assert payload["authorized_by"] == "USER"
    assert payload["authorization_source"] == "CURRENT_USER_INSTRUCTION"
    assert payload["safe_auto_relaxed"] is False
    assert payload["p15_reopened"] is False
    assert payload["truth_boundary_relaxed"] is False
    assert payload["allowed_operation"] == "ADD_SEMANTIC_ELEMENT"
    assert payload["max_new_event_per_root"] == 1
    assert payload["requires_explicit_author_approval"] is True


def test_gate_definition_has_22_checks() -> None:
    gate = _artifact(GATE_FILE)
    assert gate["check_count"] == 22
    assert tuple(gate["checks"]) == GATE_CHECK_NAMES
    assert "SAFE_AUTO / P15 / legacy run gate 语义不变" in gate["semantics"]


def test_validator_rejects_unapproved_new_event(approved_event) -> None:
    service, _payload = approved_event
    decision = {"decision_id": "X", "canonical_root_ids": ["CDQ_X"],
                "selected_option": "A", "allowed_options": [{"option_id": "A"}],
                "approved_by": "", "decision_source": ""}
    root = {"canonical_root_id": "CDQ_X"}
    event = {"canonical_root_id": "CDQ_X", "authorized_options": ["A"],
             "new_event_count": 1, "actor": "a", "action": "b", "object": "c",
             "immediate_consequence": "LOCAL_STRATEGY",
             "consequence_type": "LOCAL_STRATEGY",
             "missing_semantic_type": "TURN",
             "temporal_placement": "chapter_local", "new_knowledge": False,
             "knowledge_owner": "chapter_local_participant", "new_entity": False,
             "entity_refs": [], "inventory_delta": 0, "canon_change": False,
             "story_state_change": False, "confirmed_facts_changed": 0,
             "affected_chapter_ids": ["c1"], "chapter_id": "c1",
             "downstream_targets": [], "dependency_refs": [],
             "artifact_refs": ["CDQ_X"], "author_decision_ref": "X",
             "approval_ref": "AUTHOR_CONTENT_APPROVAL",
             "source_evidence": ["s"], "parent_source_digest": "d"}
    result = service.validator.validate(decision=decision, root=root, event=event,
                                        evidence={}, executed_roots=[])
    assert result["status"] == "FAIL"
    assert "author_decision_exists" in result["failed_checks"]
    assert "root_inside_frozen_scope" in result["failed_checks"]


def test_validator_rejects_multiple_new_events(approved_event, historical_context) -> None:
    service, _payload = approved_event
    _root_id, root, decision = _historical(historical_context)
    evidence = service.evidence_builder.evidence_for(root)
    event = service.builder.build(root=root, decision=decision, evidence=evidence)
    event["new_event_count"] = 2
    result = service.validator.validate(decision=decision, root=root, event=event,
                                        evidence=evidence, executed_roots=[])
    assert "one_new_event_max" in result["failed_checks"]
    assert result["status"] == "FAIL"


def test_validator_rejects_alias_double_execution(approved_event, historical_context) -> None:
    service, _payload = approved_event
    root_id, root, decision = _historical(historical_context)
    evidence = service.evidence_builder.evidence_for(root)
    event = service.builder.build(root=root, decision=decision, evidence=evidence)
    result = service.validator.validate(decision=decision, root=root, event=event,
                                        evidence=evidence,
                                        executed_roots=[root_id])
    assert "canonical_root_unique" in result["failed_checks"]
    assert result["status"] == "FAIL"


def test_all_historical_events_pass_all_checks(approved_event, historical_context) -> None:
    """55 个 frozen approved-event root 全部通过 22 项 gate，且 identity 可复现。"""

    service, _payload = approved_event
    roots, decisions = historical_context
    records = {row["canonical_root_id"]: row
               for row in _artifact(RECONCILIATION_FILE)["records"]}
    executed: list[str] = []
    for root_id in sorted(roots):
        root, decision = roots[root_id], decisions[root_id]
        evidence = service.evidence_builder.evidence_for(root)
        event = service.builder.build(root=root, decision=decision, evidence=evidence)
        frozen_event = _artifact(records[root_id]["repaired_ref"])["approved_event"]
        assert event["event_id"] == frozen_event["event_id"], root_id
        assert event["canonical_root_id"] == frozen_event["canonical_root_id"]
        assert event["selected_option"] == frozen_event["selected_option"]
        assert event["author_decision_ref"] == frozen_event["author_decision_ref"]
        result = service.validator.validate(decision=decision, root=root, event=event,
                                            evidence=evidence,
                                            executed_roots=executed)
        assert result["failed_checks"] == [], (root_id, result["failed_checks"])
        assert result["status"] == "PASS", root_id
        executed.append(root_id)


def test_real_run_results(approved_event) -> None:
    service, payload = approved_event
    assert payload["resolved_root_count"] == 55
    assert payload["failure_count"] == 0
    assert payload["subtype"] == SUBTYPE
    assert payload["overlay_resolved_total"] >= 276
    reconciliation = _artifact(RECONCILIATION_FILE)
    assert reconciliation["record_count"] == 55
    roots = [row["canonical_root_id"] for row in reconciliation["records"]]
    assert len(roots) == len(set(roots)) == 55
    for row in reconciliation["records"]:
        assert row["repair_subtype"] == SUBTYPE
        assert row["new_event_count"] == 1
        assert row["gate_result"] == "PASS"
        assert row["approval_ref"] == "AUTHOR_CONTENT_APPROVAL"


def test_repairs_written_and_lineage(approved_event, historical_context) -> None:
    service, _payload = approved_event
    roots, decisions = historical_context
    for root_id in sorted(roots)[:5]:
        root = roots[root_id]
        evidence = service.evidence_builder.evidence_for(root)
        path = DESIGN_DIR / "m11_approved_event" / "repaired" / f"{evidence['target_id']}.json"
        assert path.is_file()
        payload = json.loads(path.read_text(encoding="utf-8"))
        assert payload["resolution_mode"] == "AUTHOR_APPROVED_NEW_EVENT"
        assert payload["approved_event"]["author_decision_ref"]


def test_ledger_and_subtype(approved_event) -> None:
    ledger = _artifact("M11_REPAIR_SUBTYPE_LEDGER.json")
    overlay = _artifact("M11_OVERLAY_V2.json")
    assert _artifact(RECONCILIATION_FILE)["record_count"] == 55
    assert ledger["resolved_subtype_counts"][SUBTYPE] == closed(55, 81)
    assert overlay["repaired_semantic_addition"] == closed(55, 81)
    # 2 个 approved roots（CDQ_ch012 / CDQ_ch056）对应 target 在 P15 时代已 resolved，
    # 其 requirement resolution 不增加 overlay resolved 计数 → ledger 比 overlay 多 2，
    # 记为 pre-existing queue/overlay reconciliation anomaly（后续 closure 修复）。
    delta = sum(ledger["resolved_subtype_counts"].values()) - overlay["resolved_total"]
    assert delta == closed(2, 0)
    assert len(ledger["ledger"]) == overlay["resolved_total"] + delta


def test_gate_result_and_isolation(approved_event) -> None:
    result = _artifact(GATE_RESULT_FILE)
    assert result["gate_check_count"] == 22
    assert result["failure_count"] == 0
    authorization = _artifact(AUTHORIZATION_FILE)
    assert "P15_MICRO_EXECUTOR" in authorization["isolated_from"]
    assert "SAFE_AUTO" in authorization["isolated_from"]
