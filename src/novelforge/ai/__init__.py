"""NovelForge `ai` —— 唯一正式 LLM boundary（V4-02）。

Public Contract（业务层只允许依赖这些符号）：

```text
LLMGateway / LLMResult            唯一模型入口与统一结果
LLMProvider / LLMRequest / ProviderResponse   provider 协议与归一化请求/响应
LLMContract / PromptSpec / ValidationPolicy / ContractRegistry   版本化任务契约
ModelPolicy / ModelRoute / ModelRouter         路由策略与结果
UsageRecord / TraceRecord / TraceSink          观测契约
CacheKey / InMemoryCache / build_cache_key     缓存契约
LLMError 及其子类                               稳定错误模型
```

内部实现（`ai/_internal/*`、`ai/providers/*`）不得被业务模块直接依赖；
provider SDK / HTTP client 只允许出现在 `ai/providers/`。
"""

from .cache import CacheKey, InMemoryCache, build_cache_key, cache_allowed
from .config import (
    KNOWN_CAPABILITIES,
    ModelSpec,
    ProviderConfig,
    ProviderRegistry,
    load_provider_configs,
    redact_secrets,
    resolve_secret,
)
from .contracts import (
    DEFAULT_CONTRACTS,
    ContractRegistry,
    GenerationMode,
    LLMContract,
    PromptSpec,
    ValidationPolicy,
    resolve_contract,
)
from .errors import (
    AuthenticationError,
    InvalidRequestError,
    LLMError,
    ModelUnavailableError,
    ProviderConfigurationError,
    ProviderUnavailableError,
    RateLimitError,
    RequestTimeoutError,
    RetryExhaustedError,
    StructuredOutputError,
)
from .factory import (
    build_gateway,
    build_gateway_from_configs,
    build_provider,
    build_providers,
)
from .gateway import LLMGateway, LLMResult
from .legacy_support import (
    GatewayStructuredProvider,
    build_gateway_structured_provider,
    chat_completion_via_gateway,
    default_structured_provider,
    map_legacy_error_code,
)
from .provider import LLMProvider, LLMRequest, ProviderResponse
from .retry import RetryPolicy, run_with_retry, should_retry
from .router import ModelPolicy, ModelRoute, ModelRouter
from .structured_output import parse_and_validate, parse_json_text, strip_json_fence
from .trace import NullTraceSink, TraceRecord, TraceSink
from .usage import ModelPricing, UsageRecord

__all__ = [
    # gateway
    "LLMGateway", "LLMResult",
    "build_gateway", "build_gateway_from_configs", "build_provider",
    "build_providers",
    "chat_completion_via_gateway", "map_legacy_error_code",
    "GatewayStructuredProvider", "build_gateway_structured_provider",
    "default_structured_provider",
    # provider
    "LLMProvider", "LLMRequest", "ProviderResponse",
    "ProviderConfig", "ProviderRegistry", "ModelSpec", "KNOWN_CAPABILITIES",
    "load_provider_configs", "resolve_secret", "redact_secrets",
    # contract
    "LLMContract", "PromptSpec", "ValidationPolicy", "ContractRegistry",
    "DEFAULT_CONTRACTS", "GenerationMode", "resolve_contract",
    # routing
    "ModelPolicy", "ModelRoute", "ModelRouter",
    # structured output
    "parse_and_validate", "parse_json_text", "strip_json_fence",
    # retry
    "RetryPolicy", "run_with_retry", "should_retry",
    # usage / trace
    "UsageRecord", "ModelPricing", "TraceRecord", "TraceSink", "NullTraceSink",
    # cache
    "CacheKey", "InMemoryCache", "build_cache_key", "cache_allowed",
    # errors
    "LLMError", "ProviderConfigurationError", "AuthenticationError",
    "InvalidRequestError", "ModelUnavailableError", "RateLimitError",
    "ProviderUnavailableError", "RequestTimeoutError", "StructuredOutputError",
    "RetryExhaustedError",
]
