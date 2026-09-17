"""V4-05 §6–§10、§27–§28：Quality 契约对象、severity / status 语义、稳定 issue identity。"""

from __future__ import annotations

import pytest

from novelforge.quality import (
    CODE_REGISTRY,
    GATES,
    ISSUE_STATUSES,
    QUALITY_STATUSES,
    SEVERITIES,
    QualityEvidence,
    QualityIssue,
    QualityPolicy,
    QualityPolicyError,
    QualityScope,
    QualityScopeError,
    code_spec,
    codes_for_gate,
    decide_status,
    is_registered,
    issue_id_for,
    make_issue,
)


def _scope(revision: int | None = None) -> QualityScope:
    return QualityScope(novel_id="novel_alpha", node_ids=("sc_001_01",),
                        node_types=("scene",), revision=revision)


def _evidence() -> QualityEvidence:
    return QualityEvidence(evidence_id="ev_1", kind="node_field",
                           explanation="scene_purpose 为空",
                           node_ids=("sc_001_01",), revision=1)


def test_contract_enums_are_fixed() -> None:
    assert SEVERITIES == ("info", "minor", "major", "blocker")
    assert GATES == ("Q0", "Q1", "Q2", "Q3", "Q4", "Q5", "Q6", "Q7", "Q8", "Q9")
    assert "needs_human_review" in QUALITY_STATUSES
    assert "accepted_risk" in ISSUE_STATUSES


def test_scope_requires_explicit_novel_id() -> None:
    with pytest.raises(QualityScopeError):
        QualityScope(novel_id="")


def test_issue_requires_registered_code_and_evidence() -> None:
    with pytest.raises(QualityPolicyError):
        make_issue(code="NOT_A_REAL_CODE", novel_id="novel_alpha", scope=_scope(),
                   reason="x", evidence=[_evidence()], evaluator_id="t")
    with pytest.raises(QualityPolicyError):
        make_issue(code="CAUSAL_GAP", novel_id="novel_alpha", scope=_scope(),
                   reason="没有证据", evidence=[], evaluator_id="t")


def test_issue_id_is_stable_across_revisions() -> None:
    """§28 / §44：同一问题的 issue_id 不因 revision 变化而漂移。"""

    first = issue_id_for("CAUSAL_GAP", _scope(revision=1))
    second = issue_id_for("CAUSAL_GAP", _scope(revision=7))
    assert first == second
    assert first != issue_id_for("CAUSAL_GAP",
                                 QualityScope(novel_id="novel_alpha",
                                              node_ids=("sc_001_02",),
                                              node_types=("scene",)))


def test_issue_severity_and_gate_come_from_registry() -> None:
    issue = make_issue(code="CANON_CONTRADICTION", novel_id="novel_alpha",
                       scope=_scope(), reason="与 Canon 冲突",
                       evidence=[_evidence()], evaluator_id="quality.canon.v1")
    assert issue.gate == "Q2"
    assert issue.severity == "blocker"
    assert issue.repairable is True
    assert "source_ids" in issue.preserve_fields
    assert "goal" in issue.allow_change_fields
    assert issue.as_dict()["repairable"] is True


def test_issue_round_trip_from_store_payload() -> None:
    issue = make_issue(code="CAUSAL_GAP", novel_id="novel_alpha", scope=_scope(),
                       reason="关键结果缺少原因", evidence=[_evidence()],
                       evaluator_id="quality.causality.v1")
    restored = QualityIssue.from_dict(issue.as_dict())
    assert restored.issue_id == issue.issue_id
    assert restored.scope.node_ids == ("sc_001_01",)
    assert restored.evidence[0].explanation == "scene_purpose 为空"


def test_pass_fail_is_gate_based_not_score_based() -> None:
    """§10：平均分不能抵消 blocker。"""

    policy = QualityPolicy(required_gates=("Q0", "Q2", "Q7"))
    blocker = make_issue(code="CANON_CONTRADICTION", novel_id="novel_alpha",
                         scope=_scope(), reason="canon", evidence=[_evidence()],
                         evaluator_id="t")
    info = make_issue(code="PACING_STAGNATION", novel_id="novel_alpha",
                      scope=_scope(), reason="pacing",
                      evidence=[_evidence()], evaluator_id="t",
                      severity="info")
    assert decide_status([blocker, info], policy,
                         gates_run=("Q0", "Q2", "Q7")) == "blocked"
    assert decide_status([info], policy, gates_run=("Q0", "Q2", "Q7")) == "passed"
    # 未评估的 required gate → 不能判 passed
    assert decide_status([info], policy, gates_run=("Q0", "Q2")) == "failed"


def test_policy_blocks_configured_severities() -> None:
    policy = QualityPolicy(required_gates=("Q0",),
                           blocking_severities=("blocker",))
    major = make_issue(code="CAUSAL_GAP", novel_id="novel_alpha", scope=_scope(),
                       reason="gap", evidence=[_evidence()], evaluator_id="t")
    assert policy.blocks("major") is False
    assert decide_status([major], policy, gates_run=("Q0",)) == "passed"


def test_code_registry_is_stable_and_gate_scoped() -> None:
    assert is_registered("SCENE_NO_NARRATIVE_FUNCTION")
    assert not is_registered("llm_invented_code")
    assert code_spec("CANON_CONTRADICTION").gate == "Q2"
    assert "CAUSAL_GAP" in codes_for_gate("Q5")
    assert all(spec.gate in GATES for spec in CODE_REGISTRY.values())


def test_policy_rejects_unknown_gate_and_severity() -> None:
    with pytest.raises(QualityPolicyError):
        QualityPolicy(required_gates=("Q0", "Q99"))
    with pytest.raises(QualityPolicyError):
        QualityPolicy(blocking_severities=("catastrophic",))
