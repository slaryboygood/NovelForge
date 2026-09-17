"""V4-05 §22–§24：Evaluator Registry 与 deterministic / hybrid / LLM 矩阵。"""

from __future__ import annotations

import pytest

from novelforge.quality import (
    EvaluatorRegistry,
    EvaluatorSpec,
    QualityPolicy,
    QualityPolicyError,
    build_default_registry,
)


def test_default_registry_covers_all_gates() -> None:
    registry = build_default_registry()
    assert registry.gates() == ("Q0", "Q1", "Q2", "Q3", "Q4", "Q5", "Q6", "Q7",
                                "Q8", "Q9")
    assert len(registry) >= 11


def test_every_evaluator_declares_kind_and_gate() -> None:
    registry = build_default_registry()
    for spec in registry.evaluators():
        assert spec.kind in ("deterministic", "hybrid", "llm_assisted")
        assert spec.version >= 1
        assert spec.evaluator_id.startswith("quality.")
        assert spec.gate in ("Q0", "Q1", "Q2", "Q3", "Q4", "Q5", "Q6", "Q7",
                             "Q8", "Q9")


def test_deterministic_first_is_the_default() -> None:
    """默认策略下 LLM evaluator 不参与（§42）。"""

    registry = build_default_registry()
    default_policy = QualityPolicy()
    for gate in registry.gates():
        rows = registry.for_gate(gate, policy=default_policy)
        assert rows, f"{gate} 必须有 deterministic evaluator"
        assert all(row.spec.kind == "deterministic" for row in rows)
    enabled = registry.for_gate("Q2", policy=QualityPolicy(
        enable_llm_evaluators=True))
    assert {row.spec.kind for row in enabled} == {"deterministic", "llm_assisted"}


def test_registry_rejects_unknown_gate_or_kind() -> None:
    registry = EvaluatorRegistry()
    with pytest.raises(QualityPolicyError):
        registry.register(EvaluatorSpec(evaluator_id="x", version=1, gate="Q99",
                                        kind="deterministic"), lambda ctx: ())
    with pytest.raises(QualityPolicyError):
        registry.register(EvaluatorSpec(evaluator_id="x", version=1, gate="Q0",
                                        kind="vibes"), lambda ctx: ())


def test_registry_lookup_is_deterministic() -> None:
    registry = build_default_registry()
    first = [row.spec.evaluator_id for row in registry.for_gate("Q5")]
    second = [row.spec.evaluator_id for row in registry.for_gate("Q5")]
    assert first == second == sorted(first)
    with pytest.raises(QualityPolicyError):
        registry.get("quality.does_not_exist.v1")
