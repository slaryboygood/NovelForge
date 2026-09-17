"""Provider Contract 测试（V4-02 §7、§28）。"""

from __future__ import annotations

import pytest
from fake_provider import FakeProvider

from novelforge.ai import (
    AuthenticationError,
    InvalidRequestError,
    LLMRequest,
    ModelUnavailableError,
    ProviderConfig,
    ProviderResponse,
    ProviderUnavailableError,
    RateLimitError,
    RequestTimeoutError,
    build_provider,
)


def Impl(config, *, transport=None, env=None):
    """通过 Public Contract 工厂构建 provider（内部实现位于 ai/providers/）。"""

    return build_provider(config, transport=transport, env=env)


def _config() -> ProviderConfig:
    from novelforge.ai import ModelSpec

    return ProviderConfig(provider_id="compat", kind="openai_compatible",
                          base_url="https://api.example.com/v1",
                          api_key_env="COMPAT_KEY", enabled=True,
                          default_model="compat-model",
                          models=(ModelSpec(model_id="compat-model",
                                            capabilities=("utility",)),))


def _request() -> LLMRequest:
    return LLMRequest(request_id="req_1", operation="demo", model="compat-model",
                      system="sys", user="usr", temperature=0.0,
                      max_output_tokens=64, timeout_s=5.0, expect_json=True)


def _transport(status: int, body: str):
    calls: list[dict] = []

    def transport(url, headers, payload, *, timeout_s, connect_timeout_s=None):
        calls.append({"url": url, "headers": dict(headers), "payload": dict(payload),
                      "timeout_s": timeout_s, "connect_timeout_s": connect_timeout_s})
        return status, body

    transport.calls = calls  # type: ignore[attr-defined]
    return transport


def test_provider_receives_normalized_request_and_returns_normalized_result() -> None:
    transport = _transport(200, '{"model": "compat-model", "id": "resp_1",'
                                ' "choices": [{"message": {"content": "hello"},'
                                ' "finish_reason": "stop"}],'
                                ' "usage": {"prompt_tokens": 3, "completion_tokens": 2}}')
    provider = Impl(_config(), transport=transport,
                    env={"COMPAT_KEY": "sk-secret-value"})
    response = provider.complete(_request())

    assert isinstance(response, ProviderResponse)
    assert response.text == "hello"
    assert response.usage_raw == {"prompt_tokens": 3, "completion_tokens": 2}
    assert response.finish_reason == "stop"
    assert response.raw_safe == {"id": "resp_1"}

    call = transport.calls[0]  # type: ignore[attr-defined]
    assert call["url"] == "https://api.example.com/v1/chat/completions"
    assert call["payload"]["model"] == "compat-model"
    assert call["payload"]["messages"][0] == {"role": "system", "content": "sys"}
    assert call["payload"]["temperature"] == 0.0
    assert call["payload"]["response_format"] == {"type": "json_object"}
    assert call["timeout_s"] == 5.0
    assert call["headers"]["Authorization"] == "Bearer sk-secret-value"


def test_provider_extracts_fenced_content_and_token_usage() -> None:
    transport = _transport(200, '{"choices": [{"message": {"content": "```json\\n{\\"a\\":1}\\n```"}}],'
                                ' "usage": {"input_tokens": 5, "output_tokens": 7, "total_tokens": 12}}')
    provider = Impl(_config(), transport=transport, env={"COMPAT_KEY": "sk-x-1234"})
    response = provider.complete(_request())
    assert response.text.startswith("```json")
    assert response.usage_raw["total_tokens"] == 12


@pytest.mark.parametrize("status,expected", [
    (401, AuthenticationError),
    (403, AuthenticationError),
    (429, RateLimitError),
    (500, ProviderUnavailableError),
    (503, ProviderUnavailableError),
    (400, InvalidRequestError),
    (422, InvalidRequestError),
    (404, ModelUnavailableError),
])
def test_http_errors_are_normalized(status, expected) -> None:
    transport = _transport(status, '{"error": "boom"}')
    provider = Impl(_config(), transport=transport, env={"COMPAT_KEY": "sk-x-1234"})
    with pytest.raises(expected) as exc:
        provider.complete(_request())
    assert exc.value.details["status"] == status
    assert exc.value.provider == "compat"


def test_transport_timeout_is_normalized() -> None:
    def transport(*_args, **_kwargs):
        raise TimeoutError("read timeout")

    provider = Impl(_config(), transport=transport, env={"COMPAT_KEY": "sk-x-1234"})
    with pytest.raises(RequestTimeoutError):
        provider.complete(_request())


def test_connection_error_is_normalized() -> None:
    def transport(*_args, **_kwargs):
        raise OSError("connection reset by peer")

    provider = Impl(_config(), transport=transport, env={"COMPAT_KEY": "sk-x-1234"})
    with pytest.raises(ProviderUnavailableError) as exc:
        provider.complete(_request())
    assert "connection reset" in exc.value.message


def test_secret_is_redacted_from_provider_error() -> None:
    transport = _transport(500, "upstream failure for sk-secret-value (leaked)")
    provider = Impl(_config(), transport=transport,
                    env={"COMPAT_KEY": "sk-secret-value"})
    with pytest.raises(ProviderUnavailableError) as exc:
        provider.complete(_request())
    assert "sk-secret-value" not in str(exc.value.as_dict())
    assert "***" in exc.value.details["body"]


def test_secret_is_redacted_from_transport_exception() -> None:
    def transport(*_args, **_kwargs):
        raise OSError("auth failed with sk-secret-value")

    provider = Impl(_config(), transport=transport,
                    env={"COMPAT_KEY": "sk-secret-value"})
    with pytest.raises(ProviderUnavailableError) as exc:
        provider.complete(_request())
    assert "sk-secret-value" not in exc.value.message


def test_missing_key_is_configuration_error_not_network_call() -> None:
    from novelforge.ai import ProviderConfigurationError

    transport = _transport(200, "{}")
    provider = Impl(_config(), transport=transport, env={})
    with pytest.raises(ProviderConfigurationError):
        provider.complete(_request())
    assert transport.calls == []  # type: ignore[attr-defined]


def test_fake_provider_records_normalized_requests() -> None:
    provider = FakeProvider(script=['{"ok": true}'])
    response = provider.complete(_request())
    assert response.text == '{"ok": true}'
    assert provider.requests[0].operation == "demo"
    assert provider.requests[0].messages()[1]["role"] == "user"
