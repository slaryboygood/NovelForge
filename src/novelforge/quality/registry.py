"""Evaluator Registry（V4-05 §23–§24）。

每个 evaluator 声明：evaluator_id / version / gate / 支持的节点类型 /
deterministic 或 llm_assisted / 需要什么上下文。QualityService 不硬编码
`if gate == ...`，而是从 registry 取 evaluator。

Evaluator 是**只读**的：不得修改 Blueprint / Canon / StoryState，也不得调用 Repair。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Protocol, Sequence

from .contracts import GATES, QualityIssue, QualityPolicy
from .errors import QualityPolicyError


@dataclass(frozen=True)
class EvaluatorSpec:
    evaluator_id: str
    version: int
    gate: str
    kind: str                      # deterministic | hybrid | llm_assisted
    supported_node_types: tuple[str, ...] = ()
    required_context: tuple[str, ...] = ()
    description: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {"evaluator_id": self.evaluator_id, "version": self.version,
                "gate": self.gate, "kind": self.kind,
                "supported_node_types": list(self.supported_node_types),
                "required_context": list(self.required_context),
                "description": self.description}


class Evaluator(Protocol):
    spec: EvaluatorSpec

    def evaluate(self, context: Any) -> Sequence[QualityIssue]: ...


@dataclass
class EvaluatorRegistration:
    spec: EvaluatorSpec
    fn: Callable[[Any], Sequence[QualityIssue]]


class EvaluatorRegistry:
    """evaluator 注册表（确定性顺序，可查询、可测试）。"""

    def __init__(self) -> None:
        self._rows: dict[str, EvaluatorRegistration] = {}

    def register(self, spec: EvaluatorSpec,
                 fn: Callable[[Any], Sequence[QualityIssue]]) -> EvaluatorSpec:
        if spec.gate not in GATES:
            raise QualityPolicyError(f"未知 gate：{spec.gate}")
        if spec.kind not in ("deterministic", "hybrid", "llm_assisted"):
            raise QualityPolicyError(f"未知 evaluator kind：{spec.kind}")
        self._rows[spec.evaluator_id] = EvaluatorRegistration(spec=spec, fn=fn)
        return spec

    def for_gate(self, gate: str, *, policy: QualityPolicy | None = None
                 ) -> tuple[EvaluatorRegistration, ...]:
        rows = [row for row in self._rows.values() if row.spec.gate == gate]
        if policy is not None and not policy.enable_llm_evaluators:
            rows = [row for row in rows if row.spec.kind == "deterministic"]
        return tuple(sorted(rows, key=lambda row: (row.spec.evaluator_id,
                                                   row.spec.version)))

    def gates(self) -> tuple[str, ...]:
        return tuple(sorted({row.spec.gate for row in self._rows.values()}))

    def evaluators(self) -> tuple[EvaluatorSpec, ...]:
        return tuple(sorted((row.spec for row in self._rows.values()),
                            key=lambda spec: (spec.gate, spec.evaluator_id)))

    def get(self, evaluator_id: str) -> EvaluatorRegistration:
        row = self._rows.get(evaluator_id)
        if row is None:
            raise QualityPolicyError(f"未知 evaluator：{evaluator_id}")
        return row

    def __len__(self) -> int:
        return len(self._rows)


def build_default_registry() -> EvaluatorRegistry:
    """装配默认 evaluator 集合（Q0–Q9 的 deterministic / hybrid 部分）。"""

    from .evaluators import (
        canon_gate,
        causality_gate,
        character_gate,
        continuity_gate,
        delivery_gate,
        integrity_gate,
        narrative_gate,
        schema_gate,
        semantic_gate,
        style_gate,
    )

    registry = EvaluatorRegistry()
    for module in (schema_gate, integrity_gate, canon_gate, continuity_gate,
                   character_gate, causality_gate, semantic_gate, narrative_gate,
                   style_gate, delivery_gate):
        module.register(registry)
    return registry


__all__ = ["Evaluator", "EvaluatorRegistration", "EvaluatorRegistry",
           "EvaluatorSpec", "build_default_registry"]

