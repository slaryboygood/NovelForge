"""application → ai 集成路径测试（V4-02 §25）。"""

from __future__ import annotations

from fake_provider import build_harness

from novelforge.ai import ModelPolicy
from novelforge.application.services import UtilityService


def test_application_service_uses_gateway_only() -> None:
    harness = build_harness(script=['{"labels": ["悬疑", "不存在的标签"]}'],
                            provider_id="fake", cost_tier=1)
    service = UtilityService(harness.gateway,
                             model_policy=ModelPolicy(profile="cost_first"))

    payload = service.extract_labels(text="一段用于归类的文本",
                                     candidates=["悬疑", "科幻"])
    assert payload["labels"] == ["悬疑"], "越界标签必须被过滤"
    assert payload["dropped_out_of_catalog"] == ["不存在的标签"]
    assert payload["provider"] == "fake"
    assert payload["usage"]["input_tokens"] == 11
    assert payload["read_only"] is True


def test_application_service_gets_cache_hit_for_utility_contract() -> None:
    harness = build_harness(script=['{"labels": ["悬疑"]}'], provider_id="fake",
                            cost_tier=1)
    service = UtilityService(harness.gateway,
                             model_policy=ModelPolicy(profile="cost_first"))
    first = service.extract_labels(text="同样的文本", candidates=["悬疑"])
    second = service.extract_labels(text="同样的文本", candidates=["悬疑"])
    assert first["cache"]["hit"] is False
    assert second["cache"]["hit"] is True
    assert harness.provider.call_count == 1


def test_application_service_validates_input() -> None:
    harness = build_harness(script=['{"labels": []}'], provider_id="fake")
    service = UtilityService(harness.gateway)
    for kwargs in ({"text": "  ", "candidates": ["a"]},
                   {"text": "x", "candidates": []}):
        try:
            service.extract_labels(**kwargs)
        except ValueError:
            continue
        raise AssertionError("非法输入必须被拒绝")


def test_ai_does_not_depend_on_application() -> None:
    """源码守卫：ai 包不得 import application（§6 边界）。"""

    import ast
    from pathlib import Path

    root = Path(__file__).resolve().parents[2] / "src" / "novelforge" / "ai"
    offenders: list[str] = []
    for path in sorted(root.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and (node.module or "").startswith(
                    "novelforge.application"):
                offenders.append(str(path.relative_to(root)))
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name.startswith("novelforge.application"):
                        offenders.append(str(path.relative_to(root)))
    assert offenders == [], f"ai 不得依赖 application：{offenders}"

