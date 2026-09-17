"""Retry / Timeout 策略（V4-02 §15–16）。

分类（与 `errors.py` 一致）：

```text
可重试    : RequestTimeoutError / RateLimitError / ProviderUnavailableError
不可重试  : ProviderConfigurationError / AuthenticationError /
            InvalidRequestError / ModelUnavailableError
contract  : StructuredOutputError（由 contract.validation.retry_on_structured_output 决定）
上限      : max_attempts <= 5，禁止无限重试
```
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, TypeVar

from .errors import LLMError, RetryExhaustedError, StructuredOutputError

MAX_ALLOWED_ATTEMPTS = 5

T = TypeVar("T")


@dataclass(frozen=True)
class RetryPolicy:
    max_attempts: int = 3
    backoff_s: tuple[float, ...] = (0.5, 1.5, 4.0)
    retry_on_structured_output: bool = True
    respect_provider_max_retries: int | None = None

    def __post_init__(self) -> None:
        if self.max_attempts < 1:
            raise ValueError("max_attempts 必须 >= 1")
        if self.max_attempts > MAX_ALLOWED_ATTEMPTS:
            raise ValueError(f"max_attempts 不得超过 {MAX_ALLOWED_ATTEMPTS}")
        if any(item < 0 for item in self.backoff_s):
            raise ValueError("backoff 不能为负")

    def effective_attempts(self) -> int:
        if self.respect_provider_max_retries is None:
            return self.max_attempts
        return max(1, min(self.max_attempts, int(self.respect_provider_max_retries) + 1))

    def wait_s(self, attempt: int) -> float:
        """第 `attempt` 次失败后的等待时间（attempt 从 1 开始）。"""

        if not self.backoff_s:
            return 0.0
        index = min(max(attempt - 1, 0), len(self.backoff_s) - 1)
        return float(self.backoff_s[index])


def should_retry(error: LLMError, policy: RetryPolicy, *, attempt: int) -> bool:
    if attempt >= policy.effective_attempts():
        return False
    if isinstance(error, StructuredOutputError):
        return bool(policy.retry_on_structured_output)
    return bool(error.retryable)


def run_with_retry(call: Callable[[int], T], policy: RetryPolicy, *,
                   sleep: Callable[[float], None] | None = None,
                   on_retry: Callable[[int, LLMError], None] | None = None) -> T:
    """执行 `call(attempt)`，按 policy 重试（`sleep` 可注入以便测试）。"""

    do_sleep = sleep or (lambda _seconds: None)
    attempts = policy.effective_attempts()
    last_error: LLMError | None = None
    for attempt in range(1, attempts + 1):
        try:
            return call(attempt)
        except LLMError as error:
            last_error = error
            if not should_retry(error, policy, attempt=attempt):
                if error.retryable:
                    # 可重试错误但次数已耗尽 → 统一为 RetryExhaustedError（§23）
                    raise RetryExhaustedError(
                        f"重试 {attempt} 次后仍失败：{error.message}",
                        last_error=error, attempts=attempt) from error
                raise
            if on_retry is not None:
                on_retry(attempt, error)
            do_sleep(policy.wait_s(attempt))
    assert last_error is not None  # pragma: no cover - 循环必然 return 或 raise
    raise RetryExhaustedError(
        f"重试 {attempts} 次后仍失败：{last_error.message}",
        last_error=last_error, attempts=attempts)


__all__ = ["MAX_ALLOWED_ATTEMPTS", "RetryPolicy", "run_with_retry", "should_retry"]
