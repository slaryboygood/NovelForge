"""永久守卫：V4-09 plugins 模块边界（`docs/v4/V4_MODULE_BOUNDARIES.md` §3.16）。

```text
plugins（平台）      → core / quality registry / delivery registry / interfaces.mcp registry
plugins            ✗ api / ui / ai.providers / BlueprintRepository / QualityStore /
                     DeliveryStore / 自行拼 story artifact path
plugins.host        composition root：额外允许 application.services +
                     interfaces.mcp 装配（唯一例外，且不构造业务对象）
core/domain/ai/memory/blueprint/generation/quality/editor/delivery/api
                   ✗ import novelforge.plugins（Core 不依赖具体插件）
fixture plugin     → 只允许 novelforge.plugins(.sdk) + Python stdlib（§89）
```
"""

from __future__ import annotations

from pathlib import Path

from _guard_utils import (
    ROOT,
    identifier_names,
    imports_matching,
    iter_imports,
    module_level_imports,
    python_files,
    string_literals,
)

PLUGINS_FORBIDDEN_PREFIXES = (
    "novelforge.api", "novelforge.ui", "novelforge.ai.providers",
    "novelforge.blueprint", "novelforge.quality.store", "novelforge.delivery.store",
    "fastapi", "starlette", "httpx", "requests", "openai", "anthropic",
    "urllib.request",
)

#: 反向依赖：这些模块不得 import plugins（平台不是它们的依赖）
PLUGIN_CONSUMERS_FORBIDDEN = (
    "core", "persistence", "story_engine", "story_builder", "ai", "memory",
    "blueprint", "generation", "quality", "editor", "delivery", "api",
    "legacy", "observability",
)

#: plugins 内不得构造的下层业务对象
FORBIDDEN_IDENTIFIERS = (
    "BlueprintRepository", "QualityStore", "EditorStore", "DeliveryStore",
    "RepairPlanner", "RepairExecutor", "RepairVerifier", "CanonStore",
)

#: 唯一允许接触 application / interfaces 的 composition root
COMPOSITION_ROOT = "src/novelforge/plugins/host.py"
APPLICATION_FORBIDDEN_PREFIXES = (
    "novelforge.application", "novelforge.blueprint", "novelforge.generation",
    "novelforge.editor", "novelforge.memory", "novelforge.story_engine",
    "novelforge.api", "novelforge.story_builder",
)
HOST_FORBIDDEN_PREFIXES = (
    "novelforge.blueprint", "novelforge.generation", "novelforge.editor",
    "novelforge.memory", "novelforge.story_engine", "novelforge.persistence",
    "novelforge.api", "novelforge.story_builder",
)

FIXTURES = ROOT / "tests" / "plugins" / "fixtures"
SDK_ALLOWED = ("novelforge.plugins", "novelforge.plugins.sdk")


def _relative(path: Path) -> str:
    return str(path.relative_to(ROOT)).replace("\\", "/")


def _plugin_files() -> list[Path]:
    return python_files("plugins")


def test_plugins_do_not_import_forbidden_layers() -> None:
    offenders: list[str] = []
    for path in _plugin_files():
        for name, line in iter_imports(path):
            if name.startswith(PLUGINS_FORBIDDEN_PREFIXES):
                offenders.append(f"{_relative(path)}:{line} → {name}")
    assert offenders == [], (
        "plugins 不得穿透业务内部模块 / adapter（§88）：\n" + "\n".join(offenders))


def test_plugins_only_touch_application_in_composition_root() -> None:
    offenders: list[str] = []
    for path in _plugin_files():
        if _relative(path) == COMPOSITION_ROOT:
            continue
        for name, line in imports_matching(path, APPLICATION_FORBIDDEN_PREFIXES):
            offenders.append(f"{_relative(path)}:{line} → {name}")
    assert offenders == [], (
        "只有 plugins/host.py（composition root）可以接触 application 层：\n"
        + "\n".join(offenders))


def test_composition_root_does_not_build_business_objects() -> None:
    offenders: list[str] = []
    path = ROOT / COMPOSITION_ROOT
    names = {name for name, _line in identifier_names(path)}
    hits = sorted(names & set(FORBIDDEN_IDENTIFIERS))
    if hits:
        offenders.append(f"{_relative(path)} → {hits}")
    for name, line in imports_matching(path, HOST_FORBIDDEN_PREFIXES):
        offenders.append(f"{_relative(path)}:{line} → {name}")
    assert offenders == [], (
        "composition root 只负责装配 registry，不构造业务对象：\n"
        + "\n".join(offenders))


def test_plugins_do_not_construct_lower_layer_objects() -> None:
    offenders: list[str] = []
    for path in _plugin_files():
        names = {name for name, _line in identifier_names(path)}
        hits = sorted(names & set(FORBIDDEN_IDENTIFIERS))
        if hits:
            offenders.append(f"{_relative(path)} → {hits}")
    assert offenders == [], (
        "plugins 不得直接构造 repository / store：\n" + "\n".join(offenders))


def test_plugins_do_not_build_story_artifact_paths() -> None:
    offenders: list[str] = []
    for path in _plugin_files():
        for value, line in string_literals(path):
            lowered = value.lower()
            if lowered.startswith(("novel/", "novel\\", "workspace/",
                                   "workspace\\")) or "authoring/" in lowered:
                offenders.append(f"{_relative(path)}:{line} → {value!r}")
        text = path.read_text(encoding="utf-8")
        for token in ('Path("novel', "Path('novel", "project_root /"):
            if token in text:
                offenders.append(f"{_relative(path)} → {token}")
    assert offenders == [], (
        "插件状态 / 路径只能经 persistence.paths（§28）：\n" + "\n".join(offenders))


def test_layers_do_not_import_plugins() -> None:
    offenders: list[str] = []
    for package in PLUGIN_CONSUMERS_FORBIDDEN:
        for path in python_files(package):
            for name, line in iter_imports(path):
                if name == "novelforge.plugins" or \
                        name.startswith("novelforge.plugins."):
                    offenders.append(f"{_relative(path)}:{line} → {name}")
    assert offenders == [], (
        "Core / 业务模块不得依赖插件平台（§7、§88）：\n" + "\n".join(offenders))


def test_interfaces_do_not_import_plugins() -> None:
    """MCP / REST 只拿到注入的 registry，不 import 插件平台（§38）。"""

    offenders: list[str] = []
    for path in python_files("interfaces"):
        for name, line in iter_imports(path):
            if name == "novelforge.plugins" or \
                    name.startswith("novelforge.plugins."):
                offenders.append(f"{_relative(path)}:{line} → {name}")
    assert offenders == [], (
        "interfaces 只使用注入的 registry（不得 import plugins）：\n"
        + "\n".join(offenders))


def test_plugins_module_level_imports_are_light() -> None:
    offenders: list[str] = []
    for path in _plugin_files():
        if _relative(path) == COMPOSITION_ROOT:
            continue
        for name, line in module_level_imports(path):
            if name.startswith(("novelforge.application", "novelforge.blueprint",
                                "novelforge.delivery", "novelforge.quality",
                                "novelforge.editor", "novelforge.generation",
                                "novelforge.interfaces", "novelforge.memory",
                                "novelforge.ai")):
                offenders.append(f"{_relative(path)}:{line} 模块级 → {name}")
    assert offenders == [], (
        "plugins 顶层只允许协议契约（registry 通过函数内惰性 import 装配）：\n"
        + "\n".join(offenders))


# --------------------------------------------------------------------- SDK
def test_fixture_plugins_only_import_sdk_and_stdlib() -> None:
    """§89：第三方 test plugin 只能 import novelforge.plugins.sdk + stdlib。"""

    files = sorted(FIXTURES.rglob("*.py"))
    assert files, "缺少 plugin fixture"
    offenders: list[str] = []
    for path in files:
        for name, line in iter_imports(path):
            if not name.startswith("novelforge"):
                continue
            if name == "novelforge.plugins" or name == "novelforge.plugins.sdk" \
                    or name.startswith("novelforge.plugins.sdk."):
                continue
            offenders.append(f"{_relative(path)}:{line} → {name}")
    assert offenders == [], (
        "fixture 插件只能依赖 novelforge.plugins(.sdk)：\n" + "\n".join(offenders))


def test_sdk_is_the_stable_plugin_boundary() -> None:
    import novelforge.plugins.sdk as sdk

    exported = set(sdk.__all__)
    assert {"Contribution", "PluginContext", "PluginAIClient", "PERMISSIONS",
            "PLUGIN_SDK_VERSION", "exporter_contribution", "quality_contribution",
            "mcp_tool_contribution", "mcp_resource_contribution",
            "quality_issue"} <= exported
    # SDK 不得暴露 repository / store / provider / persistence
    forbidden = ("Repository", "Store", "Provider", "ApplicationServices",
                 "PluginManager", "PluginHost")
    assert not [name for name in exported
                if any(token in name for token in forbidden)]
    for path in python_files("plugins/sdk"):
        for name, line in iter_imports(path):
            if name.startswith(("novelforge.blueprint", "novelforge.delivery",
                                "novelforge.quality.store", "novelforge.editor",
                                "novelforge.ai.providers", "novelforge.persistence",
                                "novelforge.application", "novelforge.memory")):
                raise AssertionError(f"{_relative(path)}:{line} → {name}")
