"""Usage 记录（V4-02 §17）。

没有可靠价格配置时 `estimated_cost` 必须为 `null` —— 不猜模型价格。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping


@dataclass(frozen=True)
class ModelPricing:
    """per 1K tokens 的价格（由配置提供，不由代码内置）。"""

    input_per_1k: float
    output_per_1k: float
    currency: str = "USD"
    pricing_version: str = ""


@dataclass(frozen=True)
class UsageRecord:
    provider: str
    model: str
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    request_id: str = ""
    operation: str = ""
    contract_id: str = ""
    contract_version: int = 0
    estimated_cost: float | None = None
    currency: str = ""
    pricing_version: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {"provider": self.provider, "model": self.model,
                "input_tokens": self.input_tokens,
                "output_tokens": self.output_tokens,
                "total_tokens": self.total_tokens,
                "request_id": self.request_id, "operation": self.operation,
                "contract_id": self.contract_id,
                "contract_version": self.contract_version,
                "estimated_cost": self.estimated_cost,
                "currency": self.currency,
                "pricing_version": self.pricing_version}


def build_usage(*, provider: str, model: str, raw_usage: Mapping[str, Any] | None,
                request_id: str, operation: str, contract_id: str,
                contract_version: int, pricing: ModelPricing | None = None
                ) -> UsageRecord:
    """把 provider 原始 usage 归一化为 `UsageRecord`。

    兼容 OpenAI 风格的 `prompt_tokens` / `completion_tokens` / `total_tokens`
    与 `input_tokens` / `output_tokens` 两种命名。
    """

    raw = dict(raw_usage or {})

    def _int(*keys: str) -> int:
        for key in keys:
            value = raw.get(key)
            if isinstance(value, (int, float)):
                return int(value)
        return 0

    input_tokens = _int("prompt_tokens", "input_tokens")
    output_tokens = _int("completion_tokens", "output_tokens")
    total_tokens = _int("total_tokens") or (input_tokens + output_tokens)

    estimated: float | None = None
    currency = ""
    pricing_version = ""
    if pricing is not None:
        estimated = round((input_tokens / 1000.0) * pricing.input_per_1k
                          + (output_tokens / 1000.0) * pricing.output_per_1k, 6)
        currency = pricing.currency
        pricing_version = pricing.pricing_version

    return UsageRecord(provider=provider, model=model, input_tokens=input_tokens,
                       output_tokens=output_tokens, total_tokens=total_tokens,
                       request_id=request_id, operation=operation,
                       contract_id=contract_id, contract_version=contract_version,
                       estimated_cost=estimated, currency=currency,
                       pricing_version=pricing_version)


__all__ = ["ModelPricing", "UsageRecord", "build_usage"]

