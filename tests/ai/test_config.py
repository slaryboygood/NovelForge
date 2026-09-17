"""Provider 配置测试（V4-02 §9、§29）。"""

from __future__ import annotations

import pytest

from novelforge.ai import (
    ModelSpec,
    ProviderConfig,
    ProviderConfigurationError,
    ProviderRegistry,
    load_provider_configs,
    redact_secrets,
    resolve_secret,
)


def _payload(**overrides) -> dict:
    payload = {
        "provider_id": "demo",
        "kind": "openai_compatible",
        "base_url": "https://api.example.com/v1",
        "api_key_env": "DEMO_API_KEY",
        "enabled": True,
        "default_model": "demo-model",
        "models": [{"model_id": "demo-model", "capabilities": ["utility"],
                    "cost_tier": 2, "speed_tier": 2}],
    }
    payload.update(overrides)
    return {"providers": [payload]}


def test_valid_configuration_loads() -> None:
    registry = load_provider_configs(payload=_payload(), env={})
    assert registry.ids() == ("demo",)
    assert registry.get("demo").models[0].model_id == "demo-model"


def test_missing_api_key_is_reported_at_resolve_time() -> None:
    with pytest.raises(ProviderConfigurationError) as exc:
        resolve_secret("DEMO_API_KEY", env={})
    assert "DEMO_API_KEY" in exc.value.message
    assert resolve_secret("DEMO_API_KEY", env={"DEMO_API_KEY": "sk-secret"}) == "sk-secret"


def test_invalid_base_url_rejected() -> None:
    with pytest.raises(ProviderConfigurationError):
        load_provider_configs(payload=_payload(base_url="ftp://nope"), env={})
    with pytest.raises(ProviderConfigurationError):
        load_provider_configs(payload=_payload(base_url="not-a-url"), env={})


def test_enabled_provider_requires_key_env_and_base_url() -> None:
    with pytest.raises(ProviderConfigurationError):
        load_provider_configs(payload=_payload(api_key_env=""), env={})
    with pytest.raises(ProviderConfigurationError):
        load_provider_configs(payload=_payload(base_url=""), env={})


def test_disabled_provider_may_omit_url_and_key() -> None:
    registry = load_provider_configs(
        payload=_payload(enabled=False, base_url="", api_key_env=""), env={})
    assert registry.enabled() == ()
    assert registry.ids() == ("demo",)


def test_unknown_provider_kind_and_id_are_rejected() -> None:
    with pytest.raises(ProviderConfigurationError):
        load_provider_configs(payload=_payload(kind="mystery"), env={})
    with pytest.raises(ProviderConfigurationError):
        load_provider_configs(payload=_payload(provider_id="Bad Id"), env={})


def test_duplicate_provider_id_is_rejected() -> None:
    payload = {"providers": [_payload()["providers"][0], _payload()["providers"][0]]}
    with pytest.raises(ProviderConfigurationError) as exc:
        load_provider_configs(payload=payload, env={})
    assert "重复" in exc.value.message


def test_unknown_model_and_default_model_must_be_declared() -> None:
    registry = load_provider_configs(payload=_payload(), env={})
    with pytest.raises(ProviderConfigurationError):
        registry.resolve_model("demo", "unknown-model")
    with pytest.raises(ProviderConfigurationError):
        load_provider_configs(payload=_payload(default_model="ghost"), env={})


def test_invalid_timeout_and_retry_count_rejected() -> None:
    with pytest.raises(ProviderConfigurationError):
        load_provider_configs(payload=_payload(timeout_s=0), env={})
    with pytest.raises(ProviderConfigurationError):
        load_provider_configs(payload=_payload(connect_timeout_s=-1), env={})
    with pytest.raises(ProviderConfigurationError):
        load_provider_configs(payload=_payload(max_retries=99), env={})
    with pytest.raises(ProviderConfigurationError):
        load_provider_configs(payload=_payload(max_retries=-1), env={})


def test_unknown_capability_and_bad_tier_rejected() -> None:
    bad_capability = _payload(models=[{"model_id": "m", "capabilities": ["story_magic"]}])
    with pytest.raises(ProviderConfigurationError):
        load_provider_configs(payload=bad_capability, env={})
    bad_tier = _payload(models=[{"model_id": "m", "cost_tier": 9}])
    with pytest.raises(ProviderConfigurationError):
        load_provider_configs(payload=bad_tier, env={})


def test_env_json_configuration_source() -> None:
    import json

    env = {"NOVELFORGE_LLM_PROVIDERS": json.dumps(_payload())}
    registry = load_provider_configs(env=env)
    assert registry.ids() == ("demo",)
    with pytest.raises(ProviderConfigurationError):
        load_provider_configs(env={"NOVELFORGE_LLM_PROVIDERS": "{not json"})


def test_no_configuration_yields_empty_registry_not_crash() -> None:
    registry = load_provider_configs(env={})
    assert registry.ids() == ()
    assert registry.enabled() == ()


def test_secret_is_redacted_from_text() -> None:
    text = "Authorization: Bearer sk-abcdef123456 failed"
    assert "sk-abcdef123456" not in redact_secrets(text, ["sk-abcdef123456"])
    assert "***" in redact_secrets(text, ["sk-abcdef123456"])
    short = "key=abc"
    assert redact_secrets(short, ["abc"]) == short, "过短的 secret 不做替换以免误伤"


def test_provider_registry_duplicate_registration_rejected() -> None:
    config = ProviderConfig(provider_id="dup", base_url="http://x/v1",
                            api_key_env="K", enabled=True, default_model="m",
                            models=(ModelSpec(model_id="m"),))
    registry = ProviderRegistry([config])
    with pytest.raises(ProviderConfigurationError):
        registry.register(config)


def test_repository_provider_config_is_valid_and_disabled_by_default() -> None:
    """仓库内的示例配置必须合法，且**不启用任何 provider**（防止静默上号）。"""

    from pathlib import Path

    root = Path(__file__).resolve().parents[2]
    path = root / "novel" / "config" / "ai" / "providers.json"
    assert path.is_file(), "必须提供 provider 配置示例（不含 secret）"

    registry = load_provider_configs(config_path=path, env={})
    assert registry.ids() == ("local_example", "openai_compatible_example")
    assert registry.enabled() == (), "示例配置不得默认启用任何 provider"

    text = path.read_text(encoding="utf-8")
    for token in ("sk-", "Bearer "):
        assert token not in text, "配置示例不得包含 secret"
