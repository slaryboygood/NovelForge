"""GenerationService：单节点生成 / revision / 幂等 / 局部重生成（V4-04 §11–§13、§35–§39）。"""

from __future__ import annotations

from pathlib import Path

import pytest

from novelforge.core.revision import RevisionConflict
from novelforge.generation import GenerationRequest
from gen_support import blueprint_service, build_novel, premise_payload, theme_payload


def _service(tmp_path: Path, script: list):
    build_novel(tmp_path, "novel_alpha", title="阿尔法计划", fact_text="主角不会使用枪械")
    return blueprint_service(tmp_path, "novel_alpha", script)


def test_generate_returns_full_result_envelope(tmp_path: Path) -> None:
    service, provider = _service(tmp_path, [premise_payload()])
    result = service.generate_task("premise")
    assert result.ok is True
    assert result.operation == "premise"
    assert result.revision == 1
    assert result.contract == "blueprint.premise.v1"
    assert result.model and result.provider == "stub"
    assert result.context_digest and result.source_ids
    assert provider.calls == 1
    payload = result.as_dict()
    for key in ("ok", "operation", "request_id", "novel_id", "node", "revision",
                "contract", "model", "context_digest", "source_ids", "usage",
                "trace", "validation", "evidence"):
        assert key in payload
    assert "raw" not in payload, "不得泄露 provider 原始响应"


def test_generation_evidence_is_traceable(tmp_path: Path) -> None:
    service, _ = _service(tmp_path, [premise_payload()])
    result = service.generate_task("premise")
    evidence = result.evidence
    assert evidence["contract_id"] == "blueprint.premise.v1"
    assert evidence["contract_version"] == 1
    assert evidence["context_digest"] == result.context_digest
    assert evidence["model"] and evidence["request_id"]
    assert evidence["context_blocks"][0] == "required.canon"
    assert "prompt" not in str(evidence).lower()


def test_regeneration_requires_expected_revision(tmp_path: Path) -> None:
    service, _ = _service(tmp_path, [premise_payload(), premise_payload(premise="新前提")])
    service.generate_task("premise")
    with pytest.raises(RevisionConflict):
        service.regenerate(task="premise", node_id="premise", expected_revision=99)
    result = service.regenerate(task="premise", node_id="premise", expected_revision=1)
    assert result.revision == 2
    assert result.node["payload"]["premise"] == "新前提"
    assert service.revisions("premise") == [1, 2]


def test_regeneration_preserves_previous_revision(tmp_path: Path) -> None:
    service, _ = _service(tmp_path, [premise_payload(), premise_payload(premise="新前提")])
    first = service.generate_task("premise")
    service.regenerate(task="premise", node_id="premise", expected_revision=1)
    assert service.read("premise")["payload"]["premise"] == "新前提"
    assert first.node["payload"]["premise"] == "一个关于修复与代价的故事"


def test_partial_regeneration_only_touches_one_node(tmp_path: Path) -> None:
    service, _ = _service(tmp_path, [premise_payload(), theme_payload(),
                                    theme_payload(theme="新主题")])
    service.generate_task("premise")
    service.generate_task("theme")
    before = service.read("premise")
    result = service.regenerate(task="theme", node_id="theme", expected_revision=1)
    assert result.node["node_id"] == "theme" and result.revision == 2
    assert service.read("premise") == before, "局部重生成不得改动其他节点"


def test_idempotency_key_does_not_create_extra_revision(tmp_path: Path) -> None:
    service, provider = _service(tmp_path, [premise_payload(), premise_payload()])
    first = service.generate(GenerationRequest(novel_id="novel_alpha", task="premise",
                                              idempotency_key="same_key"))
    second = service.generate(GenerationRequest(novel_id="novel_alpha", task="premise",
                                               idempotency_key="same_key"))
    assert first.revision == second.revision == 1
    assert service.revisions("premise") == [1]
    assert provider.calls == 1, "幂等命中时不应再次调用模型"


def test_accept_marks_node_and_keeps_history(tmp_path: Path) -> None:
    service, _ = _service(tmp_path, [premise_payload()])
    service.generate_task("premise")
    accepted = service.accept("premise", expected_revision=1)
    assert accepted.status == "accepted"
    assert service.revisions("premise") == [1, 2]
    assert service.read("premise")["status"] == "accepted"


def test_generation_rejects_other_novel(tmp_path: Path) -> None:
    service, _ = _service(tmp_path, [premise_payload()])
    with pytest.raises(Exception):
        service.generate(GenerationRequest(novel_id="novel_beta", task="premise"))


def test_unknown_task_is_rejected(tmp_path: Path) -> None:
    service, _ = _service(tmp_path, [premise_payload()])
    with pytest.raises(Exception):
        service.generate_task("write_whole_novel")

