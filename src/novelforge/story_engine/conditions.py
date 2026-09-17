"""通用条件判断器（主计划 T07b）。

条件是数据，不是代码：Action 的 requirements 由内容包写成通用结构，
引擎只负责求值与给出清晰原因，不认识“金丹”“义体”等具体名词。

支持：
- 组合：all / any / not
- 数值条件：numeric（点号路径，如 flags.reputation）
- 布尔 flag：flag
- 角色知识：knowledge（必须是 holder 已知）
- 关系阈值：relationship（trust / respect 等维度）
- 资源数量：resource
- 身份：identity
- 地点：location
- 时间：time（markers 数量或 current_time）
- 前置事件：prior_event
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import Field, model_validator

from novelforge.models import StrictModel

from .state import StoryState

Comparator = Literal["==", "!=", ">", ">=", "<", "<="]
ConditionOp = Literal["all", "any", "not", "numeric", "flag", "knowledge", "relationship",
                      "resource", "identity", "location", "time", "prior_event"]

LEAF_OPS = ("numeric", "flag", "knowledge", "relationship", "resource", "identity", "location",
            "time", "prior_event")


class ConditionResult(StrictModel):
    ok: bool
    code: str = ""
    message: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {"ok": self.ok, "code": self.code, "message": self.message}


class Condition(StrictModel):
    op: ConditionOp
    entity: str = Field(default="", max_length=128)
    key: str = Field(default="", max_length=128)
    target: str = Field(default="", max_length=128)
    value: Any = None
    comparator: Comparator = "=="
    conditions: list["Condition"] = Field(default_factory=list)

    @model_validator(mode="after")
    def valid_shape(self) -> "Condition":
        if self.op in ("all", "any") and not self.conditions:
            raise ValueError("all / any conditions require at least one child condition")
        if self.op == "not" and len(self.conditions) != 1:
            raise ValueError("not requires exactly one child condition")
        if self.op in LEAF_OPS and self.conditions:
            raise ValueError("leaf conditions cannot contain child conditions")
        if self.op in ("knowledge", "prior_event") and not self.target:
            raise ValueError(f"{self.op} requires target")
        if self.op in ("numeric", "flag", "relationship", "resource", "time") and not self.key:
            raise ValueError(f"{self.op} requires key")
        return self


def _compare(actual: Any, expected: Any, comparator: Comparator) -> bool:
    if comparator in (">", ">=", "<", "<="):
        try:
            left, right = float(actual), float(expected)
        except (TypeError, ValueError):
            return False
        return {">": left > right, ">=": left >= right, "<": left < right, "<=": left <= right}[comparator]
    if comparator == "==":
        return actual == expected
    return actual != expected


def _describe(actual: Any, expected: Any, comparator: Comparator, unit: str = "") -> str:
    return f"{comparator} {expected}{unit}（当前 {actual}）"


def resolve_path(state: StoryState, path: str) -> Any:
    """按点号路径读取状态，例如 flags.reputation 或 resources.energy.amount。"""

    node: Any = state.model_dump(mode="python")
    for part in path.split("."):
        if not part:
            return None
        if isinstance(node, dict):
            node = node.get(part)
        elif isinstance(node, list):
            try:
                node = node[int(part)]
            except (ValueError, IndexError):
                return None
        else:
            return None
    return node


def _resource(state: StoryState, entity: str, resource_id: str) -> tuple[float, str]:
    stock = state.resources.get(resource_id)
    if stock is None:
        return 0.0, ""
    if entity and stock.holders and entity not in stock.holders:
        return 0.0, stock.unit
    return float(stock.amount), stock.unit


def _relationship(state: StoryState, source: str, target: str, dimension: str) -> float:
    for item in state.relationships:
        if item.source_id == source and item.target_id == target:
            return float(item.dimensions.get(dimension, 0))
    return 0.0


def _knowledge_holder(state: StoryState, entity: str, knowledge_id: str) -> bool:
    for item in state.knowledge:
        if item.id != knowledge_id:
            continue
        if not entity:
            return bool(item.holders)
        return entity in item.holders
    return False


def evaluate(condition: Condition, state: StoryState, *, actor: str = "") -> ConditionResult:
    entity = condition.entity or actor
    if condition.op == "all":
        for child in condition.conditions:
            result = evaluate(child, state, actor=actor)
            if not result.ok:
                return result
        return ConditionResult(ok=True)
    if condition.op == "any":
        reasons = []
        for child in condition.conditions:
            result = evaluate(child, state, actor=actor)
            if result.ok:
                return ConditionResult(ok=True)
            reasons.append(result.message or result.code)
        return ConditionResult(ok=False, code="ANY_NOT_SATISFIED",
                               message="至少需要满足其一：" + "；".join(reasons))
    if condition.op == "not":
        result = evaluate(condition.conditions[0], state, actor=actor)
        if result.ok:
            return ConditionResult(ok=False, code="NOT_VIOLATED",
                                   message="不能同时满足：" + (result.message or result.code or "该条件"))
        return ConditionResult(ok=True)

    if condition.op == "numeric":
        actual = resolve_path(state, condition.key)
        ok = _compare(actual, condition.value, condition.comparator)
        return ConditionResult(ok=ok, code="" if ok else "NUMERIC_NOT_SATISFIED",
                               message="" if ok else f"需要 {condition.key} {_describe(actual, condition.value, condition.comparator)}")
    if condition.op == "flag":
        actual = state.flags.get(condition.key)
        expected = True if condition.value is None else condition.value
        ok = _compare(actual, expected, condition.comparator)
        return ConditionResult(ok=ok, code="" if ok else "FLAG_NOT_SATISFIED",
                               message="" if ok else f"需要标记 {condition.key} {_describe(actual, expected, condition.comparator)}")
    if condition.op == "knowledge":
        ok = _knowledge_holder(state, entity, condition.target)
        return ConditionResult(ok=ok, code="" if ok else "KNOWLEDGE_MISSING",
                               message="" if ok else f"需要 {entity or '相关角色'} 已知 {condition.target}")
    if condition.op == "relationship":
        target = condition.target or actor
        actual = _relationship(state, entity, target, condition.key)
        ok = _compare(actual, condition.value, condition.comparator)
        return ConditionResult(ok=ok, code="" if ok else "RELATIONSHIP_NOT_SATISFIED",
                               message="" if ok else f"需要 {entity}→{target} 的 {condition.key} {_describe(actual, condition.value, condition.comparator)}")
    if condition.op == "resource":
        actual, unit = _resource(state, entity, condition.key)
        ok = _compare(actual, condition.value, condition.comparator)
        return ConditionResult(ok=ok, code="" if ok else "RESOURCE_NOT_ENOUGH",
                               message="" if ok else f"需要 {entity or '持有者'} 的 {condition.key} {_describe(actual, condition.value, condition.comparator, unit)}")
    if condition.op == "identity":
        owned = state.identities.get(entity, [])
        ok = _compare(condition.value in owned, True, condition.comparator)
        return ConditionResult(ok=ok, code="" if ok else "IDENTITY_MISSING",
                               message="" if ok else f"需要 {entity or '相关角色'} 具备身份 {condition.value}")
    if condition.op == "location":
        actual = state.location.current
        ok = _compare(actual, condition.value, condition.comparator)
        return ConditionResult(ok=ok, code="" if ok else "LOCATION_MISMATCH",
                               message="" if ok else f"需要位于 {condition.value}（当前 {actual}）")
    if condition.op == "time":
        actual = len(state.timeline.markers) if condition.key == "markers" else resolve_path(state, "timeline." + condition.key)
        ok = _compare(actual, condition.value, condition.comparator)
        return ConditionResult(ok=ok, code="" if ok else "TIME_NOT_REACHED",
                               message="" if ok else f"需要时间条件 timeline.{condition.key} {_describe(actual, condition.value, condition.comparator)}")
    if condition.op == "prior_event":
        ok = any(item.id == condition.target for item in state.resolved_events)
        return ConditionResult(ok=ok, code="" if ok else "EVENT_NOT_RESOLVED",
                               message="" if ok else f"需要此前已经发生 {condition.target}")
    return ConditionResult(ok=False, code="CONDITION_UNKNOWN", message=f"未知条件类型 {condition.op}")


def evaluate_all(conditions: list[Condition], state: StoryState, *, actor: str = "") -> ConditionResult:
    for condition in conditions:
        result = evaluate(condition, state, actor=actor)
        if not result.ok:
            return result
    return ConditionResult(ok=True)
