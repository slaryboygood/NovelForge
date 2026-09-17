"""ModelRouter（V4-02 §13–14）。

输入是 `ModelPolicy`（路由策略），**不是**业务语义（不允许传入"这是第 32 章"）。
输出是 `ModelRoute(provider_id, model_id, reason)`，要求 deterministic / testable / observable。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from .config import ModelSpec, ProviderConfig, ProviderRegistry
from .errors import ModelUnavailableError, ProviderConfigurationError

RoutingProfile = Literal["quality_first", "cost_first", "speed_first", "local_first",
                         "explicit_model"]


@dataclass(frozen=True)
class ModelPolicy:
    profile: RoutingProfile = "quality_first"
    required_capabilities: tuple[str, ...] = ()
    explicit_provider_id: str = ""
    explicit_model_id: str = ""
    allow_downgrade: bool = False

    def __post_init__(self) -> None:
        if self.profile not in ("quality_first", "cost_first", "speed_first",
                                "local_first", "explicit_model"):
            raise ProviderConfigurationError(f"未知 routing profile：{self.profile}")
        if self.profile == "explicit_model" and not self.explicit_model_id:
            raise ProviderConfigurationError(
                "explicit_model 策略必须提供 explicit_model_id")

    def as_dict(self) -> dict[str, object]:
        return {"profile": self.profile,
                "required_capabilities": list(self.required_capabilities),
                "explicit_provider_id": self.explicit_provider_id,
                "explicit_model_id": self.explicit_model_id,
                "allow_downgrade": self.allow_downgrade}


@dataclass(frozen=True)
class ModelRoute:
    provider_id: str
    model_id: str
    reason: str
    profile: str = ""
    spec: ModelSpec | None = None

    def as_dict(self) -> dict[str, object]:
        return {"provider_id": self.provider_id, "model_id": self.model_id,
                "reason": self.reason, "profile": self.profile}


def _rank_candidates(profile: str, candidates: list[tuple[ProviderConfig, ModelSpec]]
                     ) -> list[tuple[ProviderConfig, ModelSpec]]:
    """确定性排序（同分时按 provider_id / model_id 排序，保证可复现）。"""

    if profile == "cost_first":
        key = lambda item: (item[1].cost_tier, item[1].speed_tier,  # noqa: E731
                            item[0].provider_id, item[1].model_id)
    elif profile == "speed_first":
        key = lambda item: (item[1].speed_tier, item[1].cost_tier,  # noqa: E731
                            item[0].provider_id, item[1].model_id)
    elif profile == "local_first":
        key = lambda item: (not item[1].local, item[1].cost_tier,  # noqa: E731
                            item[0].provider_id, item[1].model_id)
    else:  # quality_first：成本档位高（更贵通常更强）+ 上下文更大
        key = lambda item: (-item[1].cost_tier, -item[1].context_tokens,  # noqa: E731
                            item[0].provider_id, item[1].model_id)
    return sorted(candidates, key=key)


class ModelRouter:
    """按 policy 选 (provider, model)；纯函数式，无副作用。"""

    def __init__(self, registry: ProviderRegistry) -> None:
        self.registry = registry

    def candidates(self, policy: ModelPolicy) -> list[tuple[ProviderConfig, ModelSpec]]:
        required = set(policy.required_capabilities)
        rows: list[tuple[ProviderConfig, ModelSpec]] = []
        for config in self.registry.enabled():
            for spec in config.models:
                if required and not required <= set(spec.capabilities):
                    continue
                rows.append((config, spec))
        return rows

    def route(self, policy: ModelPolicy) -> ModelRoute:
        if not self.registry.enabled():
            raise ProviderConfigurationError(
                "没有任何 enabled provider（配置必须显式启用；见 V4_LLM_CONTRACT.md §11）")

        if policy.profile == "explicit_model":
            return self._route_explicit(policy)

        candidates = self.candidates(policy)
        if not candidates:
            raise ModelUnavailableError(
                "没有满足 capability 要求的 enabled model",
                details={"required_capabilities": list(policy.required_capabilities),
                         "enabled_providers": list(self.registry.ids())})
        config, spec = _rank_candidates(policy.profile, candidates)[0]
        return ModelRoute(provider_id=config.provider_id, model_id=spec.model_id,
                          reason=(f"{policy.profile}"
                                  + (f" + capability {sorted(policy.required_capabilities)}"
                                     if policy.required_capabilities else "")),
                          profile=policy.profile, spec=spec)

    def _route_explicit(self, policy: ModelPolicy) -> ModelRoute:
        model_id = policy.explicit_model_id
        if policy.explicit_provider_id:
            config, spec = self.registry.resolve_model(policy.explicit_provider_id,
                                                       model_id)
            return ModelRoute(provider_id=config.provider_id, model_id=spec.model_id,
                              reason="explicit_model (provider pinned)",
                              profile=policy.profile, spec=spec)
        matches = [(config, spec) for config, spec in self.candidates(policy)
                   if spec.model_id == model_id]
        if not matches:
            raise ModelUnavailableError(
                f"指定模型不可用：{model_id}",
                details={"explicit_model_id": model_id,
                         "enabled_providers": list(self.registry.ids())})
        config, spec = sorted(matches, key=lambda item: item[0].provider_id)[0]
        return ModelRoute(provider_id=config.provider_id, model_id=spec.model_id,
                          reason="explicit_model", profile=policy.profile, spec=spec)


__all__ = ["ModelPolicy", "ModelRoute", "ModelRouter", "RoutingProfile"]

