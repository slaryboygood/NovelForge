"""Legacy chat 兼容桥（V4-02 §24）。

历史模块（`story_engine/spec/llm.py`、`planning/plot_synthesis.py`、
`planning/route_candidates.py`）原来各自手写 HTTP 调用模型 API，并各自写死
`https://api.deepseek.com/chat/completions` 与 `deepseek-chat`。

V4-02 起它们**只能**通过本函数调用模型：

```text
legacy provider（保留自身 chat 注入 seam 与错误码）
        ↓
chat_completion_via_gateway（本模块）
        ↓
LLMGateway → ModelRouter → Provider Adapter
```

本函数是**通用**的（messages → text），不包含任何故事语义；
它属于 `ai` 的 public contract，是"legacy → Gateway"的唯一桥。
"""

from __future__ import annotations

import os
from typing import Any, Mapping, Sequence

from .contracts import ContractRegistry, LLMContract, PromptSpec, ValidationPolicy
from .errors import LLMError, ProviderConfigurationError
from .factory import build_gateway_from_configs
from .gateway import LLMGateway
from .config import ModelSpec, ProviderConfig, ProviderConfigurationError
from .factory import build_gateway
from .router import ModelPolicy

DEFAULT_KEY_ENVS: tuple[str, ...] = ("DEEPSEEK_API_KEY", "ARK_API_KEY")


def _last_user_message(messages: Sequence[Mapping[str, str]]) -> str:
    for item in reversed(list(messages)):
        if str(item.get("role")) == "user":
            return str(item.get("content") or "")
    return ""


def _system_message(messages: Sequence[Mapping[str, str]], fallback: str) -> str:
    for item in messages:
        if str(item.get("role")) == "system":
            return str(item.get("content") or fallback)
    return fallback


def _strip_endpoint_suffix(base_url: str) -> str:
    cleaned = base_url.strip().rstrip("/")
    for suffix in ("/chat/completions",):
        if cleaned.endswith(suffix):
            cleaned = cleaned[: -len(suffix)]
    return cleaned


def chat_completion_via_gateway(
        messages: Sequence[Mapping[str, str]], *,
        model: str,
        base_url: str = "",
        api_key: str = "",
        timeout_s: float = 150.0,
        max_output_tokens: int = 2000,
        operation: str = "legacy_chat",
        provider_id: str = "legacy_chat",
        key_envs: Sequence[str] = DEFAULT_KEY_ENVS,
        model_env: str = "",
        base_url_env: str = "",
        env: Mapping[str, str] | None = None,
        system_prompt: str = "",
        gateway: LLMGateway | None = None,
        trace_sink: Any | None = None) -> str:
    """调用模型并返回文本（timeout / retry / usage / trace 全部由 Gateway 负责）。

    配置缺失时抛 `ProviderConfigurationError`（调用方负责映射回自己的 legacy 错误码）；
    调用失败时抛 `LLMError` 子类。
    """

    environment = dict(env or {})
    resolved_model = str(model or "").strip()
    if not resolved_model and model_env:
        resolved_model = str(environment.get(model_env, "") or "").strip()
    if not resolved_model:
        raise ProviderConfigurationError(
            "缺少模型名"
            + (f"（请显式传入 model 或设置 {model_env}）" if model_env else ""))

    resolved_base_url = _strip_endpoint_suffix(
        base_url or (environment.get(base_url_env, "") if base_url_env else ""))
    if not resolved_base_url:
        raise ProviderConfigurationError(
            "缺少 base_url"
            + (f"（请显式传入 base_url 或设置 {base_url_env}）" if base_url_env else ""))

    resolved_key = str(api_key or "").strip()
    key_env_name = "NOVELFORGE_LEGACY_LLM_KEY"
    if not resolved_key:
        for name in key_envs:
            if environment.get(name):
                resolved_key = str(environment[name]).strip()
                key_env_name = name
                break
    if not resolved_key:
        raise ProviderConfigurationError(
            "缺少 API key"
            + (f"（请设置 {' / '.join(key_envs)}）" if key_envs else ""),
            details={"key_envs": list(key_envs)})

    system = _system_message(messages, system_prompt)
    user = _last_user_message(messages)
    contract = LLMContract(
        contract_id=f"{operation}.v1", version=1,
        prompt=PromptSpec(system=system, user_template="{prompt}"),
        generation_mode="text", temperature_policy="deterministic",
        max_output_tokens=int(max_output_tokens), timeout_s=float(timeout_s),
        max_attempts=1, cacheable=False,
        validation=ValidationPolicy(require_json=False,
                                    retry_on_structured_output=False))
    policy = ModelPolicy(profile="explicit_model",
                         explicit_provider_id=provider_id,
                         explicit_model_id=resolved_model)

    if gateway is None:
        config = ProviderConfig(provider_id=provider_id, kind="openai_compatible",
                                base_url=resolved_base_url,
                                api_key_env=key_env_name,
                                models=(ModelSpec(model_id=resolved_model,
                                                  capabilities=("utility",),
                                                  cost_tier=3, speed_tier=3),),
                                default_model=resolved_model,
                                timeout_s=float(timeout_s), enabled=True)
        gateway = build_gateway_from_configs(
            (config,), contracts=ContractRegistry(), trace_sink=trace_sink,
            env={**environment, key_env_name: resolved_key})
    else:
        if trace_sink is not None:
            gateway.trace_sink = trace_sink
        gateway.registry.register(contract)

    result = gateway.generate(contract=contract, context={"prompt": user},
                              model_policy=policy, operation=operation)
    return str(result.output or "")


def map_legacy_error_code(error: LLMError, *,
                          http_code: str = "LEGACY_HTTP_FAILURE",
                          network_code: str = "LEGACY_NETWORK_FAILURE",
                          unavailable_code: str = "BLOCKED_REAL_LLM_PROPOSER_UNAVAILABLE"
                          ) -> str:
    """把 Gateway 错误映射为 legacy 模块自己的错误码（保持既有可观测行为）。"""

    effective = str((error.details or {}).get("last_error_code") or error.code)
    if effective == "LLM_PROVIDER_CONFIGURATION_ERROR":
        return unavailable_code
    if effective in {"LLM_AUTHENTICATION_ERROR", "LLM_RATE_LIMIT",
                     "LLM_PROVIDER_UNAVAILABLE", "LLM_INVALID_REQUEST",
                     "LLM_MODEL_UNAVAILABLE", "LLM_REQUEST_TIMEOUT"}:
        return http_code
    return network_code


__all__ = [
    "DEFAULT_KEY_ENVS", "GatewayStructuredProvider", "build_gateway_structured_provider",
    "chat_completion_via_gateway", "default_structured_provider",
    "map_legacy_error_code",
]


# ---------------------------------------------------------------- structured 桥
class GatewayStructuredProvider:
    """鸭子类型 `generate_structured(...)` 的 Gateway 实现（V4-04 §14）。

    历史模块（creative / settings_gen / ai_recommendations / outline_forge）使用
    `provider.generate_structured(chapter_id=…, stage=…, skill_name=…, prompt=…,
    context=…, output_model=…, workspace=…) -> (meta, draft)` 这种鸭子接口。

    本类保持**完全相同的形状**，但内部只经 `novelforge.ai` 调用模型。
    调用方仍然自己决定"哪些 id 合法 / 如何合并回规则结果"，
    因此没有把业务耦合搬进 ai（§14 禁止的正是"只改参数名、耦合照旧"）。
    """

    provider_id = "gateway_structured"

    def __init__(self, gateway: LLMGateway, *,
                 capabilities: Sequence[str] = ("structured_output",),
                 profile: str = "quality_first", model_id: str = "",
                 provider_hint: str = "", operation_prefix: str = "legacy") -> None:
        self.gateway = gateway
        self.capabilities = tuple(capabilities)
        self.profile = profile
        self.model_id = str(model_id or "")
        self.provider_hint = str(provider_hint or "")
        self.operation_prefix = str(operation_prefix or "legacy")
        self.calls = 0

    def _contract(self, *, stage: str, prompt: str, output_model: Any) -> LLMContract:
        system = ("你是 NovelForge 的结构化补全助手。只输出合法 JSON，"
                  "不得新增调用方未允许的结构 id，不得写小说正文。")
        return LLMContract(
            contract_id=f"{self.operation_prefix}.{stage or 'structured'}.v1",
            version=1,
            prompt=PromptSpec(system=system, user_template="{prompt}\n\n只输出 JSON。"),
            output_model=output_model, generation_mode="structured_json",
            temperature_policy="deterministic", max_output_tokens=2000,
            timeout_s=120.0, max_attempts=2, cacheable=False,
            validation=ValidationPolicy(require_json=True,
                                        retry_on_structured_output=True,
                                        strict=False),
            required_capabilities=self.capabilities)

    def _policy(self) -> ModelPolicy:
        if self.model_id:
            return ModelPolicy(profile="explicit_model",
                               explicit_provider_id=self.provider_hint,
                               explicit_model_id=self.model_id)
        return ModelPolicy(profile=self.profile,  # type: ignore[arg-type]
                           required_capabilities=self.capabilities)

    def generate_structured(self, *, chapter_id: str = "", stage: str = "",
                            skill_name: Any = None, prompt: str = "",
                            context: Mapping[str, Any] | None = None,
                            output_model: Any = None, workspace: Any = None,
                            **kwargs: Any) -> tuple[Any, Any]:
        contract = self._contract(stage=str(stage or chapter_id or "structured"),
                                  prompt=str(prompt or ""), output_model=output_model)
        result = self.gateway.generate(
            contract=contract, context={"prompt": str(prompt or "")},
            model_policy=self._policy(),
            operation=f"{self.operation_prefix}.{stage or chapter_id or 'structured'}")
        self.calls += 1
        return None, result.output


def build_gateway_structured_provider(*, gateway: LLMGateway,
                                      **kwargs: Any) -> GatewayStructuredProvider:
    """构建鸭子类型 structured provider（显式传入 gateway）。"""

    return GatewayStructuredProvider(gateway, **kwargs)


_DEFAULT_PROVIDER_CACHE: dict[str, Any] = {}


def default_structured_provider(*, config_path: Any = None,
                                env: Mapping[str, str] | None = None) -> Any:
    """按环境配置返回鸭子类型 structured provider；没有 enabled provider → None。

    这样 legacy 模块在"未配置模型"时保持 V3 的确定性行为；
    一旦配置了 provider，就**只有** Gateway 这一条调用路径（§13/§14）。
    """

    from .config import load_provider_configs

    environment = dict(os.environ if env is None else env)
    key = f"{config_path}|{sorted(environment.items())}"
    if key in _DEFAULT_PROVIDER_CACHE:
        return _DEFAULT_PROVIDER_CACHE[key]
    try:
        registry = load_provider_configs(env=environment, config_path=config_path)
    except ProviderConfigurationError:
        _DEFAULT_PROVIDER_CACHE[key] = None
        return None
    if not registry.enabled():
        _DEFAULT_PROVIDER_CACHE[key] = None
        return None
    gateway = build_gateway(registry, env=environment)
    provider = GatewayStructuredProvider(gateway)
    _DEFAULT_PROVIDER_CACHE[key] = provider
    return provider
