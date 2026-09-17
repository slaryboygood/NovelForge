"""Retry 测试（V4-02 §15、§28）。"""

from __future__ import annotations

import pytest
from fake_provider import (
    rate_limit_error,
    server_error,
    timeout_error,
    build_harness,
)

from novelforge.ai import (
    AuthenticationError,
    InvalidRequestError,
    LLMError,
    ModelUnavailableError,
    RetryExhaustedError,
    RetryPolicy,
    should_retry,
)


@pytest.mark.parametrize("error_factory", [timeout_error, rate_limit_error,
                                           server_error])
def test_retryable_errors_are_retried_then_succeed(error_factory) -> None:
    harness = build_harness(script=[error_factory(), '{"ok": true}'])
    result = harness.generate()
    assert result.output == {"ok": True}
    assert harness.provider.call_count == 2
    assert harness.sleeps and harness.sleeps[0] > 0


def test_authentication_error_is_not_retried() -> None:
    harness = build_harness(script=[AuthenticationError("bad key"),
                                    '{"ok": true}'])
    with pytest.raises(AuthenticationError):
        harness.generate()
    assert harness.provider.call_count == 1
    assert harness.sleeps == []


def test_invalid_request_and_model_unavailable_are_not_retried() -> None:
    for error in (InvalidRequestError("bad request"),
                  ModelUnavailableError("no model")):
        harness = build_harness(script=[error, '{"ok": true}'])
        with pytest.raises(LLMError):
            harness.generate()
        assert harness.provider.call_count == 1


def test_retry_exhaustion_raises_with_attempt_count() -> None:
    harness = build_harness(script=[timeout_error(), timeout_error(),
                                    timeout_error()], max_attempts=3)
    with pytest.raises(RetryExhaustedError) as exc:
        harness.generate()
    assert exc.value.attempts == 3
    assert harness.provider.call_count == 3
    assert len(harness.sleeps) == 2, "最后一次失败后不再等待"


def test_retry_policy_bounds_and_backoff() -> None:
    with pytest.raises(ValueError):
        RetryPolicy(max_attempts=0)
    with pytest.raises(ValueError):
        RetryPolicy(max_attempts=99)
    policy = RetryPolicy(max_attempts=2, backoff_s=(0.25,))
    assert policy.wait_s(1) == 0.25
    assert policy.wait_s(5) == 0.25, "超出 backoff 长度时取最后一个值"
    assert policy.effective_attempts() == 2
    assert should_retry(timeout_error(), policy, attempt=1) is True
    assert should_retry(timeout_error(), policy, attempt=2) is False


def test_provider_max_retries_can_tighten_contract_attempts() -> None:
    policy = RetryPolicy(max_attempts=5, respect_provider_max_retries=1)
    assert policy.effective_attempts() == 2

