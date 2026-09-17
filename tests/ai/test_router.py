"""ModelRouter 测试（V4-02 §13、§28）。"""

from __future__ import annotations

import pytest
from fake_provider import build_provider_config

from novelforge.ai import (
    ModelPolicy,
    ModelRouter,
    ModelSpec,
    ModelUnavailableError,
    ProviderConfig,
    ProviderConfigurationError,
    ProviderRegistry,
)


def _registry() -> ProviderRegistry:
    cheap = ProviderConfig(
        provider_id="cheap", kind="openai_compatible", base_url="http://cheap/v1",
        api_key_env="CHEAP_KEY", enabled=True, default_model="cheap-small",
        models=(ModelSpec(model_id="cheap-small", cost_tier=1, speed_tier=1,
                          capabilities=("utility", "structured_output")),))
    strong = ProviderConfig(
        provider_id="strong", kind="openai_compatible", base_url="http://strong/v1",
        api_key_env="STRONG_KEY", enabled=True, default_model="strong-large",
        models=(ModelSpec(model_id="strong-large", cost_tier=5, speed_tier=3,
                          capabilities=("creative", "critic", "structured_output"),
                          context_tokens=200_000),))
    fast = ProviderConfig(
        provider_id="fast", kind="openai_compatible", base_url="http://fast/v1",
        api_key_env="FAST_KEY", enabled=True, default_model="fast-mid",
        models=(ModelSpec(model_id="fast-mid", cost_tier=3, speed_tier=1,
                          capabilities=("utility", "structured_output")),))
    disabled = build_provider_config(provider_id="disabled", enabled=False,
                                     model_id="disabled-model")
    return ProviderRegistry([cheap, strong, fast, disabled])


def test_quality_first_prefers_strongest() -> None:
    route = ModelRouter(_registry()).route(ModelPolicy(profile="quality_first"))
    assert route.model_id == "strong-large"
    assert route.reason == "quality_first"


def test_cost_first_prefers_cheapest() -> None:
    route = ModelRouter(_registry()).route(ModelPolicy(profile="cost_first"))
    assert route.model_id == "cheap-small"


def test_speed_first_prefers_fastest() -> None:
    route = ModelRouter(_registry()).route(ModelPolicy(profile="speed_first"))
    assert route.model_id in {"cheap-small", "fast-mid"}
    assert route.reason == "speed_first"


def test_capability_filter_excludes_incompatible_models() -> None:
    route = ModelRouter(_registry()).route(
        ModelPolicy(profile="cost_first", required_capabilities=("creative",)))
    assert route.model_id == "strong-large", "只有 strong 声明了 creative"


def test_explicit_model_by_id_and_provider() -> None:
    router = ModelRouter(_registry())
    route = router.route(ModelPolicy(profile="explicit_model",
                                     explicit_model_id="fast-mid"))
    assert (route.provider_id, route.model_id) == ("fast", "fast-mid")
    pinned = router.route(ModelPolicy(profile="explicit_model",
                                      explicit_provider_id="strong",
                                      explicit_model_id="strong-large"))
    assert pinned.reason == "explicit_model (provider pinned)"


def test_disabled_provider_is_never_selected() -> None:
    router = ModelRouter(_registry())
    for profile in ("quality_first", "cost_first", "speed_first"):
        assert router.route(ModelPolicy(profile=profile)).provider_id != "disabled"


def test_unknown_model_and_provider_raise() -> None:
    router = ModelRouter(_registry())
    with pytest.raises(ModelUnavailableError):
        router.route(ModelPolicy(profile="explicit_model",
                                 explicit_model_id="does-not-exist"))
    with pytest.raises(ProviderConfigurationError) as exc:
        router.route(ModelPolicy(profile="explicit_model",
                                 explicit_provider_id="nope",
                                 explicit_model_id="cheap-small"))
    assert exc.value.code == "LLM_PROVIDER_CONFIGURATION_ERROR"


def test_no_enabled_provider_is_configuration_error() -> None:
    registry = ProviderRegistry([build_provider_config(provider_id="off",
                                                      enabled=False)])
    with pytest.raises(ProviderConfigurationError):
        ModelRouter(registry).route(ModelPolicy())


def test_routing_is_deterministic() -> None:
    router = ModelRouter(_registry())
    first = [router.route(ModelPolicy(profile="cost_first")).as_dict()
             for _ in range(5)]
    assert all(item == first[0] for item in first)


def test_local_first_prefers_local_model() -> None:
    local = ProviderConfig(
        provider_id="local", kind="openai_compatible", base_url="http://local/v1",
        api_key_env="LOCAL_KEY", enabled=True, default_model="local-m",
        models=(ModelSpec(model_id="local-m", cost_tier=4, speed_tier=4, local=True,
                          capabilities=("structured_output",)),))
    registry = ProviderRegistry([*_registry().all(), local])
    route = ModelRouter(registry).route(ModelPolicy(profile="local_first"))
    assert route.model_id == "local-m"

