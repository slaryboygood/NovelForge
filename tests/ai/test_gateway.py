"""Gateway 端到端（假 provider）测试（V4-02 §3、§22、§28）。"""

from __future__ import annotations

import pytest
from fake_provider import (
    DEFAULT_MODEL,
    build_harness,
    build_provider_config,
    server_error,
)
from pydantic import BaseModel, ConfigDict

from novelforge.ai import (
    LLMContract,
    ModelPolicy,
    PromptSpec,
    ProviderConfigurationError,
)


class Labels(BaseModel):
    model_config = ConfigDict(extra="forbid")
    labels: list[str]


def test_gateway_selects_route_invokes_provider_and_returns_envelope() -> None:
    harness = build_harness(script=['{"labels": ["a"]}'], output_model=Labels,
                            provider_id="fake", cost_tier=1)
    result = harness.generate(policy=ModelPolicy(profile="cost_first"))

    assert result.provider == "fake"
    assert result.model == "fake-model"
    assert result.contract_id == "demo.utility.v1"
    assert result.contract_version == 1
    assert result.output.labels == ["a"]
    assert result.request_id.startswith("llm_")

    payload = result.as_dict()
    assert set(payload) >= {"request_id", "provider", "model", "contract_id",
                            "contract_version", "operation", "output", "usage",
                            "trace", "cache", "raw_metadata"}
    assert payload["usage"]["input_tokens"] == 11
    assert payload["usage"]["output_tokens"] == 7
    assert payload["usage"]["total_tokens"] == 18
    assert payload["usage"]["estimated_cost"] is None, "没有价格配置时不得猜成本"
    assert payload["usage"]["request_id"] == result.request_id
    assert payload["raw_metadata"]["route_reason"] == "cost_first"


def test_gateway_records_usage_and_trace() -> None:
    harness = build_harness(script=['{"labels": ["a"]}'], output_model=Labels)
    result = harness.generate()
    trace = harness.trace.recent(1)[0]
    assert trace["request_id"] == result.request_id
    assert trace["status"] == "ok"
    assert trace["attempt_count"] == 1
    assert trace["contract_id"] == "demo.utility.v1"
    assert trace["schema_id"] == "Labels"
    assert trace["context_digest"] and trace["context_size"] > 0
    assert trace["timeout_s"] == harness.contract.timeout_s


def test_trace_never_contains_prompt_or_secret() -> None:
    harness = build_harness(script=['{"labels": []}'], output_model=Labels)
    harness.generate(context={"text": "绝密正文内容"})
    blob = str(harness.trace.recent(5))
    assert "绝密正文内容" not in blob
    assert "系统提示" not in blob
    assert "处理：" not in blob


def test_gateway_records_trace_on_error() -> None:
    harness = build_harness(script=[server_error(), server_error(),
                                    server_error()], max_attempts=3)
    with pytest.raises(Exception):
        harness.generate()
    trace = harness.trace.recent(1)[0]
    assert trace["status"] == "error"
    assert trace["error_code"] == "LLM_RETRY_EXHAUSTED"
    assert trace["error_chain"] == "LLM_PROVIDER_UNAVAILABLE", "必须保留根因错误码"
    assert trace["attempt_count"] == 3


def test_gateway_rejects_unregistered_provider() -> None:
    harness = build_harness(script=['{"labels": []}'], output_model=Labels)
    harness.gateway.providers.clear()
    with pytest.raises(ProviderConfigurationError):
        harness.generate()


def test_gateway_requires_all_context_keys() -> None:
    harness = build_harness(script=['{"labels": []}'], output_model=Labels)
    with pytest.raises(ProviderConfigurationError) as exc:
        harness.gateway.generate(contract=harness.contract, context={},
                                 model_policy=ModelPolicy())
    assert exc.value.details.get("missing_context_key") == "text"


def test_gateway_accepts_contract_id_string_via_registry() -> None:
    harness = build_harness(script=['{"labels": ["a"]}'], output_model=Labels)
    harness.gateway.registry.register(harness.contract)
    result = harness.gateway.generate(contract="demo.utility.v1",
                                      context={"text": "x"},
                                      model_policy=ModelPolicy())
    assert result.output.labels == ["a"]
    assert harness.contract.contract_version if False else result.contract_version == 1


def test_request_id_is_stable_when_supplied() -> None:
    harness = build_harness(script=['{"labels": []}'], output_model=Labels)
    result = harness.generate(request_id="req_fixed_1")
    assert result.request_id == "req_fixed_1"
    assert harness.trace.recent(1)[0]["request_id"] == "req_fixed_1"


def test_gateway_does_not_know_business_concepts() -> None:
    """Gateway 只接受 contract / context / policy + 通用元数据。"""

    import inspect

    from novelforge.ai import LLMGateway

    signature = inspect.signature(LLMGateway.generate)
    assert set(signature.parameters) == {
        "self", "contract", "context", "model_policy", "operation", "request_id",
        "revision", "contract_version"}
    for name in signature.parameters:
        assert not any(token in name for token in ("novel", "chapter", "scene",
                                                   "canon", "blueprint"))


def test_multiple_providers_are_ranked_by_policy() -> None:
    strong = build_provider_config(provider_id="strong", cost_tier=5, speed_tier=3,
                                   model_id="strong-model",
                                   capabilities=("utility", "structured_output"))
    harness = build_harness(script=['{"labels": ["x"]}'], output_model=Labels,
                            provider_id="cheap", cost_tier=1,
                            extra_providers=[strong])
    cheap_route = harness.generate(policy=ModelPolicy(profile="cost_first"))
    assert cheap_route.provider == "cheap"


def test_contract_requires_valid_configuration() -> None:
    with pytest.raises(ProviderConfigurationError):
        LLMContract(contract_id="", version=1, prompt=PromptSpec("s", "u"))
    with pytest.raises(ProviderConfigurationError):
        LLMContract(contract_id="c", version=0, prompt=PromptSpec("s", "u"))
    with pytest.raises(ProviderConfigurationError):
        LLMContract(contract_id="c", version=1, prompt=PromptSpec("s", "u"),
                    max_attempts=0)
    with pytest.raises(ProviderConfigurationError):
        LLMContract(contract_id="c", version=1, prompt=PromptSpec("s", "u"),
                    timeout_s=0)
