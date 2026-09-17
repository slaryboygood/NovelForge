"""Structured Output 测试（V4-02 §11–12、§28）。"""

from __future__ import annotations

import pytest
from fake_provider import build_harness
from pydantic import BaseModel, ConfigDict

from novelforge.ai import (
    StructuredOutputError,
    parse_and_validate,
    parse_json_text,
    strip_json_fence,
)


class Labels(BaseModel):
    model_config = ConfigDict(extra="forbid")
    labels: list[str]


# ---------------------------------------------------------------- 纯解析层
def test_valid_json_and_schema_validation() -> None:
    assert parse_json_text('{"a": 1}') == {"a": 1}
    result = parse_and_validate('{"labels": ["x"]}', Labels)
    assert result.labels == ["x"]


def test_json_fence_is_stripped_but_not_repaired() -> None:
    assert strip_json_fence('```json\n{"a": 1}\n```') == '{"a": 1}'
    assert parse_and_validate('```json\n{"labels": []}\n```', Labels).labels == []


def test_invalid_json_raises_structured_output_error() -> None:
    with pytest.raises(StructuredOutputError) as exc:
        parse_json_text("这不是 JSON")
    assert exc.value.code == "LLM_STRUCTURED_OUTPUT_ERROR"
    assert exc.value.details["reason"] == "JSON_INVALID"
    assert exc.value.retryable is False, "结构化输出失败默认不可重试（由 contract 决定）"


def test_empty_response_has_distinct_reason() -> None:
    with pytest.raises(StructuredOutputError) as exc:
        parse_json_text("   ")
    assert exc.value.details["reason"] == "EMPTY_RESPONSE"


def test_schema_mismatch_is_reported_without_guessing() -> None:
    with pytest.raises(StructuredOutputError) as exc:
        parse_and_validate('{"labels": "not-a-list"}', Labels)
    assert exc.value.details["reason"] == "SCHEMA_MISMATCH"
    with pytest.raises(StructuredOutputError):
        parse_and_validate('["not", "an", "object"]', Labels)


# ---------------------------------------------------------------- Gateway 集成
def test_gateway_returns_typed_output() -> None:
    harness = build_harness(script=['{"labels": ["a", "b"]}'], output_model=Labels)
    result = harness.generate()
    assert isinstance(result.output, Labels)
    assert result.output.labels == ["a", "b"]


def test_gateway_retries_structured_output_when_policy_allows() -> None:
    harness = build_harness(script=["not json", '{"labels": ["ok"]}'],
                            output_model=Labels, retry_on_structured_output=True)
    result = harness.generate()
    assert result.output.labels == ["ok"]
    assert harness.provider.call_count == 2
    assert harness.sleeps, "重试之间必须等待（可注入）"


def test_gateway_does_not_retry_structured_output_when_policy_forbids() -> None:
    harness = build_harness(script=["not json", '{"labels": ["ok"]}'],
                            output_model=Labels, retry_on_structured_output=False)
    with pytest.raises(StructuredOutputError):
        harness.generate()
    assert harness.provider.call_count == 1

