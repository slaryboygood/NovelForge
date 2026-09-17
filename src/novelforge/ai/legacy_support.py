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

from typing import Any, Mapping, Sequence

from .contracts import ContractRegistry, LLMContract, PromptSpec, ValidationPolicy
from .errors import LLMError, ProviderConfigurationError
from .factory import build_gateway_from_configs
from .gateway import LLMGateway
from .config import ModelSpec, ProviderConfig
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


__all__ = ["DEFAULT_KEY_ENVS", "chat_completion_via_gateway", "map_legacy_error_code"]
