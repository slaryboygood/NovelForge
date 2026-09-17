"""Gateway / Provider 装配工厂（V4-02 Public Contract 的一部分）。

业务侧不应该 import `ai.providers.*`（那是内部实现）。需要真实 provider 时，
从配置构建：

```python
registry = load_provider_configs(config_path="novel/config/ai/providers.json")
gateway  = build_gateway(registry)
```

测试可以注入 `transport` / `env` / `providers`，完全离线。
"""

from __future__ import annotations

from typing import Callable, Mapping, Sequence

from .cache import InMemoryCache
from .config import ProviderConfig, ProviderRegistry
from .contracts import ContractRegistry
from .errors import ProviderConfigurationError
from .gateway import LLMGateway
from .provider import LLMProvider
from .router import ModelRouter
from .trace import TraceSink


def build_provider(config: ProviderConfig, *,
                   transport: Callable[..., tuple[int, str]] | None = None,
                   env: Mapping[str, str] | None = None) -> LLMProvider:
    """按 config.kind 构建 provider（当前只有 openai_compatible）。"""

    if config.kind == "openai_compatible":
        from .providers.openai_compatible import OpenAICompatibleProvider

        return OpenAICompatibleProvider(config, transport=transport, env=env)
    raise ProviderConfigurationError(
        f"无法构建 provider：未知 kind {config.kind}",
        details={"provider_id": config.provider_id})


def build_providers(registry: ProviderRegistry, *,
                    transports: Mapping[str, Callable[..., tuple[int, str]]] | None = None,
                    env: Mapping[str, str] | None = None
                    ) -> dict[str, LLMProvider]:
    """为所有 provider 构建 adapter（未启用的也会构建，但路由不会选中）。"""

    transports = dict(transports or {})
    return {config.provider_id: build_provider(config,
                                               transport=transports.get(config.provider_id),
                                               env=env)
            for config in registry.all()}


def build_gateway(registry: ProviderRegistry, *,
                  providers: Mapping[str, LLMProvider] | None = None,
                  contracts: ContractRegistry | None = None,
                  cache: InMemoryCache | None = None,
                  trace_sink: TraceSink | None = None,
                  transports: Mapping[str, Callable[..., tuple[int, str]]] | None = None,
                  env: Mapping[str, str] | None = None,
                  sleep: Callable[[float], None] | None = None,
                  clock: Callable[[], float] | None = None) -> LLMGateway:
    """构建唯一 LLMGateway。"""

    resolved = dict(providers) if providers is not None else build_providers(
        registry, transports=transports, env=env)
    return LLMGateway(resolved, registry=contracts, router=ModelRouter(registry),
                      cache=cache, trace_sink=trace_sink, sleep=sleep, clock=clock)


def build_gateway_from_configs(configs: Sequence[ProviderConfig], **kwargs) -> LLMGateway:
    """便捷入口：直接由 ProviderConfig 列表构建。"""

    return build_gateway(ProviderRegistry(configs), **kwargs)


__all__ = ["build_gateway", "build_gateway_from_configs", "build_provider",
           "build_providers"]

