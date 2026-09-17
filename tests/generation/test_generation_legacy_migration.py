"""四处 legacy provider 的 Gateway 迁移（V4-04 §14、§41–§42）。"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from novelforge.ai import GatewayStructuredProvider, default_structured_provider
from gen_support import stub_gateway

LEGACY_MODULES = (
    "src/novelforge/story_engine/creative.py",
    "src/novelforge/story_engine/settings_gen.py",
    "src/novelforge/story_builder/ai_recommendations.py",
    "src/novelforge/story_engine/outline_forge.py",
)
ROOT = Path(__file__).resolve().parents[2]


def _http_imports(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    found: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.split(".")[0] in {"urllib", "httpx", "requests",
                                                "openai", "anthropic"}:
                    found.append(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if (node.module or "").split(".")[0] in {"urllib", "httpx", "requests",
                                                     "openai", "anthropic"}:
                found.append(node.module or "")
    return found


@pytest.mark.parametrize("relative", LEGACY_MODULES)
def test_legacy_modules_have_no_http_client(relative: str) -> None:
    assert _http_imports(ROOT / relative) == [], f"{relative} 不得自带 HTTP 调用"


@pytest.mark.parametrize("relative", LEGACY_MODULES)
def test_legacy_modules_route_default_provider_through_gateway(relative: str) -> None:
    text = (ROOT / relative).read_text(encoding="utf-8")
    assert "default_structured_provider" in text, (
        f"{relative} 必须在 provider 为空时使用 Gateway 桥")
    assert "novelforge.ai" in text, "必须显式说明依赖 ai 的 Public Contract"


def test_gateway_structured_provider_implements_duck_interface() -> None:
    gateway, provider = stub_gateway([{"ok": True}])
    bridge = GatewayStructuredProvider(gateway)
    meta, draft = bridge.generate_structured(
        chapter_id="creative_brief", stage="creative_brief_suggestions",
        skill_name=None, prompt="给出候选", context={"idea": "x"},
        output_model=None, workspace=None)
    assert meta is None
    assert draft == {"ok": True}
    assert provider.calls == 1


def test_gateway_structured_provider_validates_with_output_model() -> None:
    from novelforge.blueprint import PremisePayload

    gateway, _provider = stub_gateway([{"premise": "结构化前提",
                                        "central_conflict": "冲突"}])
    bridge = GatewayStructuredProvider(gateway)
    _meta, draft = bridge.generate_structured(
        stage="legacy_premise", prompt="x", context={},
        output_model=PremisePayload)
    assert isinstance(draft, PremisePayload)
    assert draft.premise == "结构化前提"


def test_default_provider_is_none_without_configuration() -> None:
    assert default_structured_provider(env={}) is None, (
        "未配置 provider 时必须返回 None（保持 V3 确定性行为，§42）")


def test_legacy_modules_accept_injected_gateway_provider() -> None:
    from novelforge.story_engine.creative import CreativeIdeaProvider
    from novelforge.story_engine.settings_gen import SettingsProvider

    gateway, provider = stub_gateway([{"genre_candidates": [], "tone_candidates": [],
                                       "selling_point_candidates": []}])
    bridge = GatewayStructuredProvider(gateway)
    assert CreativeIdeaProvider(bridge).provider is bridge
    assert SettingsProvider(bridge).provider is bridge
    assert provider.calls == 0, "构造 provider 不应触发模型调用"

