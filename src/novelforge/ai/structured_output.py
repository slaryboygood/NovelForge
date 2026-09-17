"""Structured Output（V4-02 §11–12）。

```text
Raw Provider Response → 有限清洗（JSON fence 剥离）→ strict JSON 解析 → schema 校验 → typed result
```

允许：JSON fence stripping / provider-native structured output / strict JSON parsing /
schema validation。**不建立大型"自动修 JSON"黑魔法**：格式错误就返回明确的
`StructuredOutputError`。
"""

from __future__ import annotations

import json
from typing import Any

from pydantic import BaseModel, ValidationError

from .errors import StructuredOutputError

_FENCE_PREFIXES = ("```json", "```JSON", "```")


def strip_json_fence(text: str) -> str:
    """只做最小清洗：剥掉整体包裹的 markdown code fence。"""

    cleaned = str(text or "").strip()
    if not cleaned.startswith("```"):
        return cleaned
    for prefix in _FENCE_PREFIXES:
        if cleaned.startswith(prefix):
            cleaned = cleaned[len(prefix):]
            break
    if cleaned.endswith("```"):
        cleaned = cleaned[:-3]
    return cleaned.strip()


def parse_json_text(text: str) -> Any:
    """strict JSON 解析（失败 → StructuredOutputError）。"""

    raw = str(text or "")
    if not raw.strip():
        raise StructuredOutputError("模型返回空内容", reason="EMPTY_RESPONSE")
    cleaned = strip_json_fence(raw)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError as exc:
        raise StructuredOutputError(
            f"模型输出不是合法 JSON：{exc.msg}",
            reason="JSON_INVALID",
            details={"error": str(exc)[:200], "position": exc.pos}) from exc


def validate_structured(payload: Any, model: type[BaseModel], *,
                        strict: bool = True) -> BaseModel:
    """schema 校验（失败 → StructuredOutputError，不尝试自动修补）。"""

    if not isinstance(payload, dict):
        raise StructuredOutputError(
            f"结构化输出必须是 JSON 对象，实际是 {type(payload).__name__}",
            reason="SHAPE_INVALID")
    try:
        return model.model_validate(payload, strict=strict)
    except ValidationError as exc:
        raise StructuredOutputError(
            "结构化输出未通过 schema 校验",
            reason="SCHEMA_MISMATCH",
            details={"errors": json.loads(exc.json())[:5],
                     "schema": getattr(model, "__name__", str(model))}) from exc


def parse_and_validate(text: str, model: type[BaseModel] | None, *,
                       strict: bool = True) -> Any:
    """完整结构化输出链；`model=None` 时返回已解析的 JSON 对象。"""

    payload = parse_json_text(text)
    if model is None:
        return payload
    return validate_structured(payload, model, strict=strict)


__all__ = ["parse_and_validate", "parse_json_text", "strip_json_fence",
           "validate_structured"]

