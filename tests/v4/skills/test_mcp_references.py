"""§67 MCP Reference：skill 声明的 tool / resource 必须在真实 registry 里；并检查覆盖率。"""

from __future__ import annotations

import pytest

from ._skill_lib import load_validator


@pytest.fixture(scope="module")
def validator():
    return load_validator()


def test_mcp_references_exist_and_cover_all_tools(validator):
    tools, resources = validator.real_mcp_surface()
    validator.check_mcp_references(tools, resources)


def test_core_baseline_counts(validator):
    """V4.0.1 Core 基线：23 tools / 13 resources（插件只追加）。"""

    tools, resources = validator.real_mcp_surface()
    assert len(tools) == 23
    assert len(resources) == 13


def test_mcp_module_readme_states_baseline(validator):
    text = validator.read_text(validator.SKILL_ROOT / "mcp" / "README.md")
    assert "23 tools" in text and "13 resources" in text


def test_plugin_resource_namespace_is_documented_but_not_core(validator):
    """插件资源 namespace 由 Host 运行时注册，不属于 Core 静态 registry。"""

    _, resources = validator.real_mcp_surface()
    assert validator._normalise_uri("novelforge://plugins/acme/thing") not in resources
