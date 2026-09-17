"""LLMGateway —— 唯一正式模型入口（V4-02）。

调用形态（`docs/v4/V4_LLM_CONTRACT.md` §3）：

```python
llm.generate(contract=..., context=..., model_policy=...)
```

链路：

```text
Application / Generation Service
        ↓
LLMGateway（本模块：contract 解析 / cache / retry / usage / trace）
        ↓
ModelRouter（policy → provider + model）
        ↓
Provider Adapter（ai/providers/*）
        ↓
Structured Output Validation
        ↓
LLMResult
```

边界（§6）：Gateway **不认识** novel_id / chapter / scene / canon / StoryState 等业务概念；
它只处理 contract、context（不透明 mapping）、model policy 与请求元数据。
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Callable, Mapping

from novelforge.core.ids import new_request_id

from .cache import InMemoryCache, build_cache_key, cache_allowed
from .contracts import ContractRegistry, DEFAULT_CONTRACTS, LLMContract, resolve_contract
from .errors import LLMError, ProviderConfigurationError, RetryExhaustedError
from .provider import LLMProvider, LLMRequest, ProviderResponse
from .retry import RetryPolicy, run_with_retry
from .router import ModelPolicy, ModelRoute, ModelRouter
from .structured_output import parse_and_validate
from .trace import NullTraceSink, TraceRecord, TraceSink, context_digest, context_size
from .usage import build_usage


@dataclass(frozen=True)
class LLMResult:
    request_id: str
    provider: str
    model: str
    contract_id: str
    contract_version: int
    operation: str
    output: Any
    usage: Mapping[str, Any] = field(default_factory=dict)
    trace: Mapping[str, Any] = field(default_factory=dict)
    cache: Mapping[str, Any] = field(default_factory=dict)
    raw_metadata: Mapping[str, Any] = field(default_factory=dict)
    degraded: bool = False
    warnings: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        return {"request_id": self.request_id, "provider": self.provider,
                "model": self.model, "contract_id": self.contract_id,
                "contract_version": self.contract_version,
                "operation": self.operation, "output": self.output,
                "usage": dict(self.usage), "trace": dict(self.trace),
                "cache": dict(self.cache), "raw_metadata": dict(self.raw_metadata),
                "degraded": self.degraded, "warnings": list(self.warnings)}


class LLMGateway:
    """唯一模型入口。业务层只允许依赖本类（以及 `novelforge.ai` 的公开契约）。"""

    def __init__(self, providers: Mapping[str, LLMProvider], *,
                 registry: ContractRegistry | None = None,
                 router: ModelRouter | None = None,
                 cache: InMemoryCache | None = None,
                 trace_sink: TraceSink | None = None,
                 sleep: Callable[[float], None] | None = None,
                 clock: Callable[[], float] | None = None) -> None:
        self.providers = dict(providers)
        self.registry = registry or DEFAULT_CONTRACTS
        # 注意：不能用 `or`（空 trace store / 空 cache 的 truthiness 可能为假）
        self.cache = cache if cache is not None else InMemoryCache()
        self.trace_sink = trace_sink if trace_sink is not None else NullTraceSink()
        self._sleep = sleep if sleep is not None else time.sleep
        self._clock = clock if clock is not None else time.monotonic
        if router is not None:
            self.router = router
        else:
            from .config import ProviderRegistry

            self.router = ModelRouter(ProviderRegistry())

    # ------------------------------------------------------------------ 内部
    def _provider(self, provider_id: str) -> LLMProvider:
        provider = self.providers.get(provider_id)
        if provider is None:
            raise ProviderConfigurationError(
                f"provider 未注册到 gateway：{provider_id}",
                details={"provider_id": provider_id,
                         "registered": sorted(self.providers)})
        return provider

    @staticmethod
    def _policy_fields(model_policy: ModelPolicy) -> dict[str, Any]:
        return {"profile": model_policy.profile,
                "required_capabilities": list(model_policy.required_capabilities),
                "explicit_provider_id": model_policy.explicit_provider_id,
                "explicit_model_id": model_policy.explicit_model_id}

    def _retry_policy(self, contract: LLMContract, route: ModelRoute) -> RetryPolicy:
        max_retries = None
        if route.spec is not None:
            # provider 配置的 retry 上限会收紧（不会放宽）contract 的 attempts
            max_retries = None
        return RetryPolicy(max_attempts=min(contract.max_attempts, 5),
                           retry_on_structured_output=(
                               contract.validation.retry_on_structured_output),
                           respect_provider_max_retries=max_retries)

    # ------------------------------------------------------------------ 主入口
    def generate(self, *, contract: LLMContract | str,
                 context: Mapping[str, Any] | None = None,
                 model_policy: ModelPolicy | None = None,
                 operation: str = "", request_id: str = "",
                 revision: int | None = None,
                 contract_version: int | None = None) -> LLMResult:
        resolved = resolve_contract(contract, registry=self.registry,
                                    version=contract_version)
        policy = model_policy or ModelPolicy(
            required_capabilities=resolved.required_capabilities)
        context_payload: dict[str, Any] = dict(context or {})
        request_id = request_id or new_request_id("llm")
        operation = operation or resolved.contract_id

        route = self.router.route(policy)
        provider = self._provider(route.provider_id)
        key = build_cache_key(provider=route.provider_id, model=route.model_id,
                              contract_id=resolved.contract_id,
                              contract_version=resolved.version,
                              context=context_payload,
                              policy_fields=self._policy_fields(policy),
                              revision=revision)
        allow_cache = cache_allowed(contract_cacheable=resolved.cacheable,
                                   generation_mode=resolved.generation_mode)
        cache_meta: dict[str, Any] = {"hit": False, "allowed": allow_cache,
                                      "key": key.as_string() if allow_cache else ""}
        if allow_cache:
            cached = self.cache.get(key)
            if cached is not None:
                trace = self._record_trace(
                    request_id=request_id, operation=operation, route=route,
                    contract=resolved, status="cache_hit", latency_ms=0,
                    attempt_count=0, usage={}, error_code="",
                    context=context_payload, cache_key=key.as_string())
                return LLMResult(request_id=request_id, provider=route.provider_id,
                                 model=route.model_id,
                                 contract_id=resolved.contract_id,
                                 contract_version=resolved.version,
                                 operation=operation, output=cached,
                                 usage={"cache": "hit"}, trace=trace,
                                 cache={**cache_meta, "hit": True},
                                 raw_metadata={"route_reason": route.reason},
                                 warnings=("CACHE_HIT",))

        system, user = resolved.prompt.render(context_payload)
        request = LLMRequest(request_id=request_id, operation=operation,
                             model=route.model_id, system=system, user=user,
                             temperature=resolved.temperature,
                             max_output_tokens=resolved.max_output_tokens,
                             timeout_s=resolved.timeout_s,
                             expect_json=(resolved.generation_mode == "structured_json"))

        started = self._clock()
        attempts = {"count": 0}

        def _attempt(_attempt_index: int) -> tuple[ProviderResponse, Any]:
            attempts["count"] += 1
            response = provider.complete(request)
            if resolved.generation_mode == "structured_json" or resolved.validation.require_json:
                parsed = parse_and_validate(response.text, resolved.output_model,
                                           strict=resolved.validation.strict)
            else:
                parsed = response.text
            return response, parsed

        retry_policy = self._retry_policy(resolved, route)
        try:
            response, output = run_with_retry(_attempt, retry_policy, sleep=self._sleep)
        except LLMError as error:
            root_code = str((error.details or {}).get("last_error_code") or "")
            self._record_trace(request_id=request_id, operation=operation, route=route,
                               contract=resolved, status="error",
                               latency_ms=int((self._clock() - started) * 1000),
                               attempt_count=attempts["count"], usage={},
                               error_code=error.code, error_chain=root_code,
                               context=context_payload,
                               cache_key=key.as_string() if allow_cache else "")
            raise
        latency_ms = int((self._clock() - started) * 1000)

        usage = build_usage(provider=route.provider_id, model=route.model_id,
                            raw_usage=response.usage_raw, request_id=request_id,
                            operation=operation, contract_id=resolved.contract_id,
                            contract_version=resolved.version,
                            pricing=(None if route.spec is None
                                     or not route.spec.has_pricing else
                                     _pricing_from_spec(route.spec)))
        trace = self._record_trace(request_id=request_id, operation=operation,
                                   route=route, contract=resolved, status="ok",
                                   latency_ms=latency_ms,
                                   attempt_count=attempts["count"],
                                   usage=usage.as_dict(), error_code="",
                                   context=context_payload,
                                   cache_key=key.as_string() if allow_cache else "")
        if allow_cache:
            self.cache.put(key, output)

        return LLMResult(request_id=request_id, provider=route.provider_id,
                         model=route.model_id, contract_id=resolved.contract_id,
                         contract_version=resolved.version, operation=operation,
                         output=output, usage=usage.as_dict(), trace=trace,
                         cache=cache_meta,
                         raw_metadata={"route_reason": route.reason,
                                       "finish_reason": response.finish_reason,
                                       "provider_model": response.model})

    # ------------------------------------------------------------------ trace
    def _record_trace(self, *, request_id: str, operation: str, route: ModelRoute,
                      contract: LLMContract, status: str, latency_ms: int,
                      attempt_count: int, usage: Mapping[str, Any], error_code: str,
                      context: Mapping[str, Any], cache_key: str,
                      error_chain: str = "") -> dict[str, Any]:
        record = TraceRecord(
            request_id=request_id, operation=operation,
            provider=route.provider_id, model=route.model_id,
            contract_id=contract.contract_id, contract_version=contract.version,
            status=status, latency_ms=latency_ms, attempt_count=attempt_count,
            timeout_s=contract.timeout_s, usage=dict(usage), error_code=error_code,
            error_chain=error_chain,
            context_digest=context_digest(context), context_size=context_size(context),
            schema_id=contract.schema_id, cache_key=cache_key)
        self.trace_sink.record(record)
        return record.as_dict()


def _pricing_from_spec(spec: Any) -> Any:
    from .usage import ModelPricing

    return ModelPricing(input_per_1k=float(spec.pricing_input_per_1k),
                        output_per_1k=float(spec.pricing_output_per_1k),
                        currency=spec.pricing_currency,
                        pricing_version=spec.pricing_version)


__all__ = ["LLMGateway", "LLMResult"]
