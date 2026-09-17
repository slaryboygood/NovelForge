"""测试用 Fake / Stub Provider（V4-02 §26）。

单元测试**绝不**调用真实模型 API。FakeProvider 可以模拟：

```text
success / timeout / 429 / 500 / invalid json / schema mismatch / token usage / multiple attempts
```
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

from pydantic import BaseModel

from novelforge.ai import (
    InMemoryCache,
    LLMContract,
    LLMGateway,
    LLMRequest,
    ModelPolicy,
    ModelRouter,
    ModelSpec,
    PromptSpec,
    ProviderConfig,
    ProviderRegistry,
    ProviderResponse,
    ProviderUnavailableError,
    RateLimitError,
    RequestTimeoutError,
)

DEFAULT_MODEL = "fake-model"


class FakeProvider:
    """按脚本返回响应的 provider；记录收到的归一化请求。"""

    def __init__(self, *, provider_id: str = "fake",
                 script: Sequence[Any] = (), default_text: str = "{}") -> None:
        self.provider_id = provider_id
        self.script = list(script)
        self.default_text = default_text
        self.requests: list[LLMRequest] = []

    @property
    def call_count(self) -> int:
        return len(self.requests)

    def complete(self, request: LLMRequest) -> ProviderResponse:
        self.requests.append(request)
        item = self.script.pop(0) if self.script else self.default_text
        if isinstance(item, Exception):
            raise item
        if isinstance(item, ProviderResponse):
            return item
        if isinstance(item, Mapping):
            text = json.dumps(item, ensure_ascii=False)
        else:
            text = str(item)
        return ProviderResponse(text=text, model=request.model,
                                usage_raw={"prompt_tokens": 11, "completion_tokens": 7},
                                finish_reason="stop")


@dataclass
class GatewayHarness:
    gateway: LLMGateway
    provider: FakeProvider
    contract: LLMContract
    cache: InMemoryCache
    trace: Any
    sleeps: list[float] = field(default_factory=list)

    def generate(self, context: Mapping[str, Any] | None = None,
                 policy: ModelPolicy | None = None, **kwargs: Any):
        return self.gateway.generate(contract=self.contract, context=context or {"text": "hi"},
                                     model_policy=policy, **kwargs)


def build_provider_config(*, provider_id: str = "fake", enabled: bool = True,
                          cost_tier: int = 2, speed_tier: int = 2,
                          capabilities: Sequence[str] = ("utility", "structured_output"),
                          local: bool = False, model_id: str = DEFAULT_MODEL,
                          default_model: str = "") -> ProviderConfig:
    specs = (ModelSpec(model_id=model_id, capabilities=tuple(capabilities),
                       cost_tier=cost_tier, speed_tier=speed_tier, local=local,
                       context_tokens=8000),)
    return ProviderConfig(provider_id=provider_id, kind="openai_compatible",
                          base_url="http://fake.local/v1", api_key_env="FAKE_LLM_KEY",
                          models=specs, default_model=default_model or model_id,
                          enabled=enabled)


def build_harness(*, script: Sequence[Any] = (), contract: LLMContract | None = None,
                  provider_id: str = "fake", cost_tier: int = 2,
                  speed_tier: int = 2, local: bool = False,
                  cacheable: bool = False, max_attempts: int = 3,
                  output_model: type[BaseModel] | None = None,
                  retry_on_structured_output: bool = True,
                  extra_providers: Sequence[ProviderConfig] = (),
                  with_cache: bool = True) -> GatewayHarness:
    from novelforge.observability import InMemoryModelTraceStore

    calls: list[float] = []
    model_id = f"{provider_id}-model"
    config = build_provider_config(provider_id=provider_id, cost_tier=cost_tier,
                                   speed_tier=speed_tier, local=local,
                                   model_id=model_id)
    registry = ProviderRegistry([config, *extra_providers])
    provider = FakeProvider(provider_id=provider_id, script=script)
    cache = InMemoryCache()
    trace = InMemoryModelTraceStore(max_records=50)
    gateway = LLMGateway({provider_id: provider}, router=ModelRouter(registry),
                         cache=cache, trace_sink=trace,
                         sleep=lambda seconds: calls.append(seconds),
                         clock=lambda: 0.0)
    resolved_contract = contract or LLMContract(
        contract_id="demo.utility.v1", version=1,
        prompt=PromptSpec(system="系统提示", user_template="处理：{text}"),
        output_model=output_model, generation_mode="structured_json",
        max_attempts=max_attempts, cacheable=cacheable,
        validation=_validation(retry_on_structured_output))
    harness = GatewayHarness(gateway=gateway, provider=provider,
                             contract=resolved_contract, cache=cache, trace=trace,
                             sleeps=calls)
    return harness


def _validation(retry_on_structured_output: bool):
    from novelforge.ai import ValidationPolicy

    return ValidationPolicy(require_json=True,
                            retry_on_structured_output=retry_on_structured_output)


def timeout_error() -> RequestTimeoutError:
    return RequestTimeoutError("超时", provider="fake", model=DEFAULT_MODEL)


def rate_limit_error() -> RateLimitError:
    return RateLimitError("限流", provider="fake", model=DEFAULT_MODEL)


def server_error() -> ProviderUnavailableError:
    return ProviderUnavailableError("500", provider="fake", model=DEFAULT_MODEL)


__all__ = [
    "DEFAULT_MODEL", "FakeProvider", "GatewayHarness", "build_harness",
    "build_provider_config", "rate_limit_error", "server_error", "timeout_error",
]

