"""§66/§51：docs 的 interface map / catalog 里的 REST 引用同样必须真实。"""

from __future__ import annotations

from pathlib import Path

import pytest

from ._skill_lib import ROOT, load_validator

INTERFACE_DOCS = (
    "docs/v4/V4_0_1_INTERFACE_MAP.md",
    "docs/v4/V4_0_1_FEATURE_USAGE_CATALOG.md",
    "docs/v4/V4_0_1_USER_FEATURE_GUIDE.md",
)

#: module id → 文档里使用的能力名（feature catalog / interface map 的口径）
MODULE_DISPLAY_NAMES = {
    "project": ("Project", "作品"),
    "studio": ("Studio", "Story Studio"),
    "blueprint": ("Blueprint", "蓝图"),
    "generation": ("Generation", "生成"),
    "memory": ("Memory", "记忆"),
    "quality": ("Quality", "质量"),
    "repair": ("Repair", "修复"),
    "editor": ("Editor", "编辑"),
    "delivery": ("Delivery", "交付"),
    "canon": ("Canon",),
    "story-state": ("StoryState", "Story State"),
    "plugins": ("Plugins", "Plugin"),
    "agent": ("Agent",),
    "mcp": ("MCP",),
    "ai": ("AI",),
}


@pytest.fixture(scope="module")
def validator():
    return load_validator()


@pytest.mark.parametrize("doc", INTERFACE_DOCS)
def test_doc_rest_references_exist(validator, doc):
    routes = validator.real_routes()
    text = (ROOT / Path(doc)).read_text(encoding="utf-8")
    for method, raw in validator.REST_RE.findall(text):
        assert validator._normalise_route(method, raw) in routes, \
            f"{doc}：REST 引用不存在 → {method} {raw}"


def test_feature_catalog_covers_every_module(validator):
    text = (ROOT / "docs/v4/V4_0_1_FEATURE_USAGE_CATALOG.md").read_text(encoding="utf-8")
    for module, names in MODULE_DISPLAY_NAMES.items():
        assert any(name in text for name in names), f"feature catalog 未覆盖 module：{module}"


def test_interface_map_module_rows_match_catalog(validator):
    """interface map 与 skill catalog 必须指向同一组 module（避免文档漂移）。"""

    catalog = validator.read_text(validator.SKILL_ROOT / "SKILL_CATALOG.md")
    interface_map = (ROOT / "docs/v4/V4_0_1_INTERFACE_MAP.md").read_text(encoding="utf-8")
    for module, names in MODULE_DISPLAY_NAMES.items():
        assert any(name in interface_map for name in names), \
            f"interface map 未覆盖 module：{module}"
        assert module in catalog
