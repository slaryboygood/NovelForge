"""Provider 抽象（V4-02 §7）。

Provider 负责：请求序列化 / 鉴权 / API 调用 / 超时 / 错误归一化 / 响应抽取 / token usage 抽取。
Provider 不负责：业务 prompt、故事逻辑、质量评分、记忆检索、业务模型选择。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Protocol, runtime_checkable


@dataclass(frozen=True)
class LLMRequest:
    """归一化的 provider 请求（provider 只看得到这些通用字段）。"""

    request_id: str
    operation: str
    model: str
    system: str
    user: str
    temperature: float
    max_output_tokens: int
    timeout_s: float
    expect_json: bool = False
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def messages(self) -> list[dict[str, str]]:
        return [{"role": "system", "content": self.system},
                {"role": "user", "content": self.user}]


@dataclass(frozen=True)
class ProviderResponse:
    """归一化的 provider 响应。

    `raw_safe` 只允许放**安全子集**（例如 finish_reason / id），不得含 secret 或完整 prompt。
    """

    text: str
    model: str = ""
    usage_raw: Mapping[str, Any] = field(default_factory=dict)
    finish_reason: str = ""
    raw_safe: Mapping[str, Any] = field(default_factory=dict)


@runtime_checkable
class LLMProvider(Protocol):
    """Provider 协议（结构化输出由 Gateway 负责，Provider 只回文本 + usage）。"""

    provider_id: str

    def complete(self, request: LLMRequest) -> ProviderResponse: ...


__all__ = ["LLMProvider", "LLMRequest", "ProviderResponse"]

