"""LLM 错误模型（V4-02，见 `docs/v4/V4_LLM_CONTRACT.md` §6）。

要求：稳定 / 结构化 / 可测试 / 不泄露 secret。

分类决定重试行为（`retryable`）：

```text
retryable      : RequestTimeoutError / RateLimitError / ProviderUnavailableError
non-retryable  : ProviderConfigurationError / AuthenticationError /
                 InvalidRequestError / ModelUnavailableError
policy-driven  : StructuredOutputError（由 contract policy 决定）
terminal       : RetryExhaustedError（包装最后一次错误，本身不再重试）
```
"""

from __future__ import annotations

from typing import Any, Mapping


class LLMError(RuntimeError):
    """所有 LLM 相关错误的基类（不包含 secret，`details` 必须可安全序列化）。"""

    code = "LLM_ERROR"
    retryable = False

    def __init__(self, message: str, *, details: Mapping[str, Any] | None = None,
                 provider: str = "", model: str = "") -> None:
        self.message = str(message)
        self.details: dict[str, Any] = dict(details or {})
        self.provider = provider
        self.model = model
        super().__init__(self.message)

    def as_dict(self) -> dict[str, Any]:
        return {"code": self.code, "message": self.message,
                "retryable": self.retryable,
                "provider": self.provider, "model": self.model,
                "details": dict(self.details)}


class ProviderConfigurationError(LLMError):
    """provider / model / 配置缺失或非法（配置阶段就应发现，不重试）。"""

    code = "LLM_PROVIDER_CONFIGURATION_ERROR"


class AuthenticationError(LLMError):
    """鉴权失败（401 / 403 / key 缺失），不重试。"""

    code = "LLM_AUTHENTICATION_ERROR"


class InvalidRequestError(LLMError):
    """请求本身非法（400 / 422 / schema 配置错误），不重试。"""

    code = "LLM_INVALID_REQUEST"


class ModelUnavailableError(LLMError):
    """模型不存在 / 不受支持 / 被禁用，不重试。"""

    code = "LLM_MODEL_UNAVAILABLE"


class RateLimitError(LLMError):
    """429，可重试（更长退避）。"""

    code = "LLM_RATE_LIMIT"
    retryable = True


class ProviderUnavailableError(LLMError):
    """5xx / 连接重置 / 暂时不可用，可重试。"""

    code = "LLM_PROVIDER_UNAVAILABLE"
    retryable = True


class RequestTimeoutError(LLMError):
    """超时（connect / read / 总 deadline），可重试。"""

    code = "LLM_REQUEST_TIMEOUT"
    retryable = True


class StructuredOutputError(LLMError):
    """结构化输出失败（空响应 / 非 JSON / schema 不符）。

    是否重试由 contract 的 validation policy 决定（`retryable` 仅为默认值）。
    """

    code = "LLM_STRUCTURED_OUTPUT_ERROR"

    def __init__(self, message: str, *, reason: str = "", **kwargs: Any) -> None:
        super().__init__(message, **kwargs)
        self.reason = reason
        self.details.setdefault("reason", reason)


class RetryExhaustedError(LLMError):
    """重试次数耗尽（包装最后一次真实错误）。"""

    code = "LLM_RETRY_EXHAUSTED"

    def __init__(self, message: str, *, last_error: LLMError | None = None,
                 attempts: int = 0) -> None:
        super().__init__(message, provider=getattr(last_error, "provider", ""),
                         model=getattr(last_error, "model", ""))
        self.last_error = last_error
        self.attempts = attempts
        self.details.setdefault("attempts", attempts)
        if last_error is not None:
            self.details.setdefault("last_error_code", last_error.code)


__all__ = [
    "AuthenticationError", "InvalidRequestError", "LLMError",
    "ModelUnavailableError", "ProviderConfigurationError",
    "ProviderUnavailableError", "RateLimitError", "RequestTimeoutError",
    "RetryExhaustedError", "StructuredOutputError",
]

