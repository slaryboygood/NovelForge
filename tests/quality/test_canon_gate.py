"""V4-05 §14：Q2 Canon —— deterministic 结构化比较 + 可选 critic（默认关闭）。"""

from __future__ import annotations

from pathlib import Path

import pytest

from novelforge.quality import QualityPolicy, QualityPolicyError, QualityService
from novelforge.quality.evaluators.canon_gate import (
    CRITIC_EVALUATOR_ID,
    EVALUATOR_ID,
    _prohibition_keywords,
)

from quality_support import (
    WEAPON_RULE_TEXT,
    build_novel,
    codes,
    isolated_gate,
    scene,
    service_for,
    stub_gateway,
)


def test_prohibition_keywords_drop_projection_metadata() -> None:
    """canon 投影会追加「（event，happened）」，不得把元数据当成关键词。"""

    assert _prohibition_keywords("主角不会使用枪械（event，happened）") == ["使用枪械"]


def test_deterministic_canon_contradiction(tmp_path: Path) -> None:
    issues, _quality = isolated_gate(
        tmp_path,
        [scene("sc_001_01", outcome="主角直接使用枪械压住混乱")],
        "Q2", fact_text=WEAPON_RULE_TEXT)
    assert codes(issues) == ["CANON_CONTRADICTION"]
    assert issues[0].severity == "blocker"
    assert issues[0].gate == "Q2"
    assert issues[0].evidence[0].comparison["keyword"] == "使用枪械"
    assert issues[0].evaluator_id == EVALUATOR_ID


def test_no_contradiction_when_blueprint_respects_canon(tmp_path: Path) -> None:
    issues, _quality = isolated_gate(
        tmp_path, [scene("sc_001_01", outcome="主角用绝缘手套接上了旧电网")],
        "Q2", fact_text=WEAPON_RULE_TEXT)
    assert codes(issues) == []


def test_critic_evaluator_is_llm_assisted_and_off_by_default(tmp_path: Path) -> None:
    from novelforge.quality import build_default_registry

    registry = build_default_registry()
    spec = registry.get(CRITIC_EVALUATOR_ID).spec
    assert spec.gate == "Q2" and spec.kind == "llm_assisted"
    assert CRITIC_EVALUATOR_ID not in [
        row.spec.evaluator_id
        for row in registry.for_gate("Q2", policy=QualityPolicy())]


def _critic_service(tmp_path: Path, script: list[object]) -> tuple[QualityService, object]:
    from novelforge.blueprint import BlueprintRepository

    build_novel(tmp_path, "novel_alpha", title="阿尔法计划",
                fact_text=WEAPON_RULE_TEXT)
    repository = BlueprintRepository(tmp_path, "novel_alpha")
    repository.save_revision(scene("sc_001_01"), expected_revision=None)
    memory = service_for(tmp_path, "novel_alpha")
    gateway, provider = stub_gateway(
        script, capabilities=("critic", "structured_output"))
    service = QualityService(tmp_path, "novel_alpha", memory=memory,
                             repository=repository, critic=gateway)
    return service, provider


def test_critic_can_propose_canon_candidate_when_enabled(tmp_path: Path) -> None:
    script = [{"candidates": [{"code": "CANON_CONTRADICTION",
                               "node_id": "sc_001_01",
                               "reason": "与 Canon 的身份设定冲突",
                               "excerpt": "主角直接公开了身份"}]}]
    service, provider = _critic_service(tmp_path, script)
    report = service.evaluate(
        gates=("Q2",),
        policy=QualityPolicy(required_gates=("Q2",), enable_llm_evaluators=True))
    assert provider.calls == 1
    assert "CANON_CONTRADICTION" in codes(report.issues)
    critic_issue = [row for row in report.issues
                    if row.evaluator_id == CRITIC_EVALUATOR_ID][0]
    assert critic_issue.provenance["contract_id"] == "quality.canon.critic.v1"
    assert "prompt" not in critic_issue.provenance  # §60：不保存完整 prompt
    assert report.usage["evaluation"]["calls"] == 1


def test_critic_cannot_invent_issue_code(tmp_path: Path) -> None:
    script = [{"candidates": [{"code": "LLM_MADE_THIS_UP",
                               "node_id": "sc_001_01", "reason": "x"}]}]
    service, _provider = _critic_service(tmp_path, script)
    with pytest.raises(QualityPolicyError):
        service.evaluate(
            gates=("Q2",),
            policy=QualityPolicy(required_gates=("Q2",),
                                 enable_llm_evaluators=True))
