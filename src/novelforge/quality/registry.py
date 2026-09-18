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
    #: V4-09 §75：注册归属（core | plugin + owner_id）
    owner_type: str = "core"
    owner_id: str = "novelforge"

    def as_dict(self) -> dict[str, Any]:
        return {"evaluator_id": self.evaluator_id, "version": self.version,
                "gate": self.gate, "kind": self.kind,
                "supported_node_types": list(self.supported_node_types),
                "required_context": list(self.required_context),
                "description": self.description,
                "owner_type": self.owner_type, "owner_id": self.owner_id}


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
        existing = self._rows.get(spec.evaluator_id)
        if existing is not None and (
                existing.spec.owner_type != spec.owner_type
                or existing.spec.owner_id != spec.owner_id):
            # V4-09 §78 / §90：第三方 evaluator 只能追加，不能覆盖 Core 注册
            raise QualityPolicyError(
                f"evaluator 重复注册且 owner 不同：{spec.evaluator_id}",
                details={"evaluator_id": spec.evaluator_id,
                         "existing_owner": existing.spec.owner_id,
                         "incoming_owner": spec.owner_id})
        self._rows[spec.evaluator_id] = EvaluatorRegistration(spec=spec, fn=fn)
        return spec

    def for_gate(self, gate: str, *, policy: QualityPolicy | None = None
                 ) -> tuple[EvaluatorRegistration, ...]:
        rows = [row for row in self._rows.values() if row.spec.gate == gate]
        if policy is not None:
            if not policy.enable_llm_evaluators:
                rows = [row for row in rows if row.spec.kind == "deterministic"]
            # V4-09 §78：插件 evaluator 只有被 policy 显式启用时才参与
            enabled_plugins = set(getattr(policy, "plugin_evaluator_ids", ()) or ())
            rows = [row for row in rows
                    if row.spec.owner_type != "plugin"
                    or row.spec.owner_id in enabled_plugins]
        return tuple(sorted(rows, key=lambda row: (row.spec.evaluator_id,
                                                   row.spec.version)))

    def unregister_owner(self, owner_id: str) -> int:
        """按 owner 卸载（Core owner 不允许卸载，§74）。"""

        before = len(self._rows)
        self._rows = {key: value for key, value in self._rows.items()
                      if value.spec.owner_id != str(owner_id)
                      or value.spec.owner_type == "core"}
        return before - len(self._rows)

    def owners(self) -> dict[str, tuple[str, ...]]:
        result: dict[str, list[str]] = {}
        for row in self._rows.values():
            result.setdefault(row.spec.owner_id, []).append(row.spec.evaluator_id)
        return {key: tuple(sorted(value)) for key, value in sorted(result.items())}

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
