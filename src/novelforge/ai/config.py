"""Provider 配置与 secret 边界（V4-02 §9、§29）。

规则：

```text
· 核心实现不得出现固定生产 model / base_url / api_key
· provider / model 由配置注入；api_key 只能从 environment 读取
· api_key 不写入 repository / trace / log / cache key / API 响应
· 配置阶段就要报错：缺 key、非法 base_url、未启用、未知 provider/model、
  重复 provider id、非法 timeout、非法 retry 次数
```
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Mapping

from .errors import ProviderConfigurationError

#: provider 支持的能力标签（routing metadata，不含业务语义）
KNOWN_CAPABILITIES = frozenset({
    "structured_output", "large_context", "creative", "critic", "repair", "utility",
})

PROVIDER_KINDS = frozenset({"openai_compatible"})
_ENV_NAME_RE = re.compile(r"^[A-Z][A-Z0-9_]*$")


@dataclass(frozen=True)
class ModelSpec:
    """一个可用模型及其路由元数据（capability / 成本 / 速度 / 上下文）。"""

    model_id: str
    capabilities: tuple[str, ...] = ()
    context_tokens: int = 0
    cost_tier: int = 3          # 1 = 最便宜，5 = 最贵（配置提供，不猜价格）
    speed_tier: int = 3         # 1 = 最快
    local: bool = False
    supports_json_mode: bool = True
    pricing_input_per_1k: float | None = None
    pricing_output_per_1k: float | None = None
    pricing_currency: str = "USD"
    pricing_version: str = ""

    def __post_init__(self) -> None:
        if not str(self.model_id or "").strip():
            raise ProviderConfigurationError("model_id 不能为空")
        unknown = [item for item in self.capabilities if item not in KNOWN_CAPABILITIES]
        if unknown:
            raise ProviderConfigurationError(
                f"未知 capability：{unknown}",
                details={"model_id": self.model_id, "unknown": unknown})
        for name in ("cost_tier", "speed_tier"):
            value = getattr(self, name)
            if not 1 <= int(value) <= 5:
                raise ProviderConfigurationError(
                    f"{name} 必须在 1..5 之间（实际 {value}）",
                    details={"model_id": self.model_id})
        if self.context_tokens < 0:
            raise ProviderConfigurationError("context_tokens 不能为负")
        for value in (self.pricing_input_per_1k, self.pricing_output_per_1k):
            if value is not None and value < 0:
                raise ProviderConfigurationError("pricing 不能为负")

    @property
    def has_pricing(self) -> bool:
        return (self.pricing_input_per_1k is not None
                and self.pricing_output_per_1k is not None)


@dataclass(frozen=True)
class ProviderConfig:
    provider_id: str
    kind: str = "openai_compatible"
    base_url: str = ""
    api_key_env: str = ""
    models: tuple[ModelSpec, ...] = ()
    default_model: str = ""
    timeout_s: float = 60.0
    connect_timeout_s: float | None = None
    max_retries: int = 2
    enabled: bool = False
    extra_headers_env: str = ""

    def __post_init__(self) -> None:
        if not re.fullmatch(r"[a-z][a-z0-9_\-]{1,63}", str(self.provider_id or "")):
            raise ProviderConfigurationError(
                f"provider_id 非法：{self.provider_id!r}（要求小写字母/数字/下划线）")
        if self.kind not in PROVIDER_KINDS:
            raise ProviderConfigurationError(
                f"未知 provider kind：{self.kind}",
                details={"provider_id": self.provider_id,
                         "allowed": sorted(PROVIDER_KINDS)})
        if self.enabled and not self.base_url:
            raise ProviderConfigurationError(
                "enabled provider 必须提供 base_url",
                details={"provider_id": self.provider_id})
        if self.base_url and not re.match(r"^https?://[^\s]+$", self.base_url):
            raise ProviderConfigurationError(
                f"base_url 非法：{self.base_url!r}",
                details={"provider_id": self.provider_id})
        if self.api_key_env and not _ENV_NAME_RE.match(self.api_key_env):
            raise ProviderConfigurationError(
                f"api_key_env 必须是环境变量名（全大写）：{self.api_key_env!r}")
        if self.enabled and not self.api_key_env:
            raise ProviderConfigurationError(
                "enabled provider 必须声明 api_key_env（key 只从 environment 读取）",
                details={"provider_id": self.provider_id})
        if self.timeout_s <= 0:
            raise ProviderConfigurationError(
                f"timeout_s 必须 > 0（实际 {self.timeout_s}）")
        if self.connect_timeout_s is not None and self.connect_timeout_s <= 0:
            raise ProviderConfigurationError("connect_timeout_s 必须 > 0")
        if not 0 <= int(self.max_retries) <= 5:
            raise ProviderConfigurationError(
                f"max_retries 必须在 0..5 之间（实际 {self.max_retries}）")
        if not self.models:
            raise ProviderConfigurationError(
                "provider 必须至少声明一个 model",
                details={"provider_id": self.provider_id})
        ids = [item.model_id for item in self.models]
        if len(ids) != len(set(ids)):
            raise ProviderConfigurationError(
                "同一 provider 内 model_id 不得重复",
                details={"provider_id": self.provider_id})
        if self.default_model and self.default_model not in ids:
            raise ProviderConfigurationError(
                f"default_model 未在 models 中声明：{self.default_model}",
                details={"provider_id": self.provider_id})

    def model(self, model_id: str = "") -> ModelSpec | None:
        target = model_id or self.default_model
        if not target:
            return None
        for item in self.models:
            if item.model_id == target:
                return item
        return None

    @property
    def model_ids(self) -> tuple[str, ...]:
        return tuple(item.model_id for item in self.models)


class ProviderRegistry:
    """已校验的 provider 集合（确定性顺序）。"""

    def __init__(self, configs: Iterable[ProviderConfig] = ()) -> None:
        self._configs: dict[str, ProviderConfig] = {}
        for config in configs:
            self.register(config)

    def register(self, config: ProviderConfig) -> ProviderConfig:
        if config.provider_id in self._configs:
            raise ProviderConfigurationError(
                f"provider_id 重复：{config.provider_id}",
                details={"provider_id": config.provider_id})
        self._configs[config.provider_id] = config
        return config

    def get(self, provider_id: str) -> ProviderConfig:
        config = self._configs.get(provider_id)
        if config is None:
            raise ProviderConfigurationError(
                f"未知 provider：{provider_id}",
                details={"provider_id": provider_id,
                         "known": sorted(self._configs)})
        return config

    def enabled(self) -> tuple[ProviderConfig, ...]:
        return tuple(config for _, config in sorted(self._configs.items())
                     if config.enabled)

    def all(self) -> tuple[ProviderConfig, ...]:
        return tuple(config for _, config in sorted(self._configs.items()))

    def ids(self) -> tuple[str, ...]:
        return tuple(sorted(self._configs))

    def resolve_model(self, provider_id: str, model_id: str = "") -> tuple[ProviderConfig,
                                                                          ModelSpec]:
        config = self.get(provider_id)
        if not config.enabled:
            raise ProviderConfigurationError(
                f"provider 未启用：{provider_id}",
                details={"provider_id": provider_id})
        spec = config.model(model_id)
        if spec is None:
            raise ProviderConfigurationError(
                f"provider {provider_id} 未声明模型：{model_id or config.default_model}",
                details={"provider_id": provider_id,
                         "known_models": list(config.model_ids)})
        return config, spec

    def __len__(self) -> int:
        return len(self._configs)


def model_spec_from_payload(payload: Mapping[str, Any]) -> ModelSpec:
    return ModelSpec(
        model_id=str(payload.get("model_id") or payload.get("id") or ""),
        capabilities=tuple(str(item) for item in (payload.get("capabilities") or [])),
        context_tokens=int(payload.get("context_tokens") or 0),
        cost_tier=int(payload.get("cost_tier") or 3),
        speed_tier=int(payload.get("speed_tier") or 3),
        local=bool(payload.get("local") or False),
        supports_json_mode=bool(payload.get("supports_json_mode", True)),
        pricing_input_per_1k=payload.get("pricing_input_per_1k"),
        pricing_output_per_1k=payload.get("pricing_output_per_1k"),
        pricing_currency=str(payload.get("pricing_currency") or "USD"),
        pricing_version=str(payload.get("pricing_version") or ""))


def provider_config_from_payload(payload: Mapping[str, Any]) -> ProviderConfig:
    models = tuple(model_spec_from_payload(item) for item in (payload.get("models") or []))

    def _number(key: str, default: float) -> float:
        value = payload.get(key)
        return default if value is None else float(value)

    return ProviderConfig(
        provider_id=str(payload.get("provider_id") or ""),
        kind=str(payload.get("kind") or "openai_compatible"),
        base_url=str(payload.get("base_url") or ""),
        api_key_env=str(payload.get("api_key_env") or ""),
        models=models,
        default_model=str(payload.get("default_model") or ""),
        timeout_s=_number("timeout_s", 60.0),
        connect_timeout_s=(float(payload["connect_timeout_s"])
                           if payload.get("connect_timeout_s") is not None else None),
        max_retries=int(payload.get("max_retries") if payload.get("max_retries")
                        is not None else 2),
        enabled=bool(payload.get("enabled") or False),
        extra_headers_env=str(payload.get("extra_headers_env") or ""))


def load_provider_configs(*, payload: Mapping[str, Any] | None = None,
                          env: Mapping[str, str] | None = None,
                          config_path: Path | str | None = None) -> ProviderRegistry:
    """按优先级加载 provider 配置：显式 payload → env JSON → 配置文件。

    默认**不启用任何 provider**（enabled=false），避免"悄悄开始调用真实模型"。
    """

    source: Mapping[str, Any] | None = payload
    environment = dict(os.environ if env is None else env)

    if source is None:
        raw = environment.get("NOVELFORGE_LLM_PROVIDERS", "")
        if raw.strip():
            try:
                source = json.loads(raw)
            except json.JSONDecodeError as exc:
                raise ProviderConfigurationError(
                    "NOVELFORGE_LLM_PROVIDERS 不是合法 JSON",
                    details={"error": str(exc)[:200]}) from exc

    if source is None and config_path is not None:
        path = Path(config_path)
        if path.is_file():
            try:
                source = json.loads(path.read_text(encoding="utf-8"))
            except json.JSONDecodeError as exc:
                raise ProviderConfigurationError(
                    f"provider 配置文件不是合法 JSON：{path}",
                    details={"error": str(exc)[:200]}) from exc

    if not source:
        return ProviderRegistry()

    providers = source.get("providers") if isinstance(source, Mapping) else None
    if not isinstance(providers, list):
        raise ProviderConfigurationError(
            "provider 配置必须是 {\"providers\": [ ... ]} 结构")
    return ProviderRegistry(provider_config_from_payload(item) for item in providers)


def resolve_secret(env_name: str, *, env: Mapping[str, str] | None = None) -> str:
    """从 environment 解析 secret；缺失 → AuthenticationError 语义的配置错误。

    返回的字符串只用于请求头，调用方不得写入 trace / log / cache / 响应。
    """

    if not env_name:
        raise ProviderConfigurationError("provider 未声明 api_key_env")
    environment = os.environ if env is None else env
    value = str(environment.get(env_name, "") or "").strip()
    if not value:
        raise ProviderConfigurationError(
            f"缺少 API key：环境变量 {env_name} 未设置",
            details={"api_key_env": env_name})
    return value


def redact_secrets(text: str, secrets: Iterable[str]) -> str:
    """把出现的 secret 替换成 `***`（用于任何可能外泄的错误 / 日志文本）。"""

    redacted = str(text)
    for secret in secrets:
        if secret and len(secret) >= 4:
            redacted = redacted.replace(secret, "***")
    return redacted


__all__ = [
    "KNOWN_CAPABILITIES", "ModelSpec", "PROVIDER_KINDS", "ProviderConfig",
    "ProviderRegistry", "load_provider_configs", "model_spec_from_payload",
    "provider_config_from_payload", "redact_secrets", "resolve_secret",
]
