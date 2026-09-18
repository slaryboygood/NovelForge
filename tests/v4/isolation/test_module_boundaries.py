"""永久守卫：模块依赖边界（V4-01，`docs/v4/V4_MODULE_BOUNDARIES.md` §4）。

用 import 图（AST）机械检查依赖方向。**存量例外以显式白名单登记**：
白名单只允许缩小，不允许新增（新增即违反模块边界）。
"""

from __future__ import annotations

from _guard_utils import (
    ROOT,
    imports_matching,
    iter_imports,
    module_level_imports,
    python_files,
)

#: interface 层不得直接依赖 domain —— 存量例外（V4-01 记录，后续只减不增）
#: post-release cleanup 之后只剩 canon_routes / app 两个存量例外：
#: `story_builder_routes.py`（1,317 行 God router）已删除，
#: `/novels` 现在只经 `application.services`（api/project_routes.py）。
INTERFACE_TO_DOMAIN_ALLOWLIST = {
    "src/novelforge/api/canon_routes.py",
}

#: application 层不允许依赖 interface
APPLICATION_FORBIDDEN_PREFIXES = ("novelforge.api", "fastapi", "starlette")

DOMAIN_FORBIDDEN_PREFIXES = (
    "fastapi", "starlette", "mcp", "httpx", "requests",
    "openai", "anthropic",
)

#: V4-02：ai 包禁止依赖任何业务层 / 接口层
AI_FORBIDDEN_PREFIXES = (
    "novelforge.story_engine", "novelforge.story_builder", "novelforge.persistence",
    "novelforge.application", "novelforge.api", "novelforge.observability",
    "novelforge.legacy",
    "fastapi", "starlette", "mcp",
)

#: V4-02：HTTP / provider SDK 只允许出现在 ai/providers/
HTTP_CLIENT_PREFIXES = ("httpx", "requests", "urllib", "aiohttp", "openai",
                        "anthropic")

#: V4-03：memory 禁止依赖 interface / application / provider 实现
MEMORY_FORBIDDEN_PREFIXES = (
    "novelforge.api", "novelforge.application", "novelforge.ai.providers",
    "fastapi", "starlette", "mcp", "httpx", "requests", "urllib", "openai",
    "anthropic",
)

#: V4-02 允许的 legacy 适配器：**只能在函数内**惰性 import novelforge.ai。
#: post-release cleanup：7 个 legacy 适配器全部随 V2 后端退休 → 白名单清空
#: （domain 现在完全不得 import ai）。
DOMAIN_AI_IMPORT_ALLOWLIST: set[str] = set()


def _relative(path) -> str:
    return str(path.relative_to(ROOT)).replace("\\", "/")


def test_domain_has_no_adapter_or_provider_dependency() -> None:
    offenders: list[str] = []
    for path in python_files("story_engine"):
        for name, line in imports_matching(path, DOMAIN_FORBIDDEN_PREFIXES):
            offenders.append(f"{_relative(path)}:{line} → {name}")
    assert offenders == [], (
        "domain（story_engine）不得依赖 interface / provider：\n" + "\n".join(offenders))


def test_domain_does_not_import_persistence_paths() -> None:
    offenders: list[str] = []
    for path in python_files("story_engine"):
        for name, line in imports_matching(path, ("novelforge.persistence",)):
            offenders.append(f"{_relative(path)}:{line} → {name}")
    assert offenders == [], (
        "domain 不得依赖 persistence（路径解析属于 persistence 层）：\n"
        + "\n".join(offenders))


def test_interface_layer_does_not_add_new_domain_imports() -> None:
    offenders: list[str] = []
    for path in python_files("api"):
        if _relative(path) in INTERFACE_TO_DOMAIN_ALLOWLIST:
            continue
        for name, line in imports_matching(path, ("novelforge.story_engine",
                                                 "novelforge.story_builder")):
            offenders.append(f"{_relative(path)}:{line} → {name}")
    assert offenders == [], (
        "api 层只能通过 application.services 使用业务能力；"
        "若确需例外，必须先在 V4_MODULE_BOUNDARIES.md 登记：\n"
        + "\n".join(offenders))


def test_application_services_do_not_depend_on_interfaces() -> None:
    offenders: list[str] = []
    for path in python_files("application"):
        for name, line in imports_matching(path, APPLICATION_FORBIDDEN_PREFIXES):
            offenders.append(f"{_relative(path)}:{line} → {name}")
    assert offenders == [], (
        "application 层不得依赖 interface / web framework：\n" + "\n".join(offenders))


def test_persistence_does_not_depend_on_application_or_interfaces() -> None:
    offenders: list[str] = []
    for path in python_files("persistence"):
        for name, line in imports_matching(path, ("novelforge.application",
                                                 "novelforge.api",
                                                 "novelforge.story_builder")):
            offenders.append(f"{_relative(path)}:{line} → {name}")
    assert offenders == [], (
        "persistence 只允许依赖 core / domain：\n" + "\n".join(offenders))


def test_ui_does_not_import_python_modules() -> None:
    """UI 只能通过 HTTP 消费后端（源码守卫）。"""

    ui_src = ROOT / "ui" / "src"
    offenders: list[str] = []
    for path in sorted(ui_src.rglob("*.ts*")):
        text = path.read_text(encoding="utf-8")
        if "novelforge.story_engine" in text or "novelforge.story_builder" in text:
            offenders.append(_relative(path))
    assert offenders == [], (
        "UI 不得引用后端 Python 模块（只能走 HTTP API）：\n" + "\n".join(offenders))


# ---------------------------------------------------------------- V4-02（ai）
def test_ai_does_not_depend_on_business_or_interface_layers() -> None:
    """ai 是叶子模块：不得依赖 domain / application / persistence / interface。"""

    offenders: list[str] = []
    for path in python_files("ai"):
        for name, line in imports_matching(path, AI_FORBIDDEN_PREFIXES):
            offenders.append(f"{_relative(path)}:{line} → {name}")
    assert offenders == [], (
        "ai 不得依赖业务层 / 接口层：\n" + "\n".join(offenders))


def test_http_clients_and_provider_sdks_live_only_in_ai_providers() -> None:
    """provider SDK / HTTP client 只允许出现在 ai/providers/。"""

    offenders: list[str] = []
    for path in python_files("ai", "story_engine", "api", "application",
                             "persistence", "observability"):
        relative = _relative(path)
        if relative.startswith("src/novelforge/ai/providers/"):
            continue
        for name, line in imports_matching(path, HTTP_CLIENT_PREFIXES):
            offenders.append(f"{relative}:{line} → {name}")
    assert offenders == [], (
        "HTTP client / provider SDK 只能出现在 ai/providers/：\n" + "\n".join(offenders))


def test_domain_does_not_import_ai_module_level() -> None:
    """domain 不得在模块顶层依赖 ai；legacy 适配器只允许函数内惰性 import。"""

    offenders: list[str] = []
    for path in python_files("story_engine"):
        relative = _relative(path)
        for name, line in module_level_imports(path):
            if name.startswith("novelforge.ai"):
                offenders.append(f"{relative}:{line} 模块级 → {name}")
        if relative in DOMAIN_AI_IMPORT_ALLOWLIST:
            continue
        for name, line in iter_imports(path):
            if name.startswith("novelforge.ai"):
                offenders.append(f"{relative}:{line} 惰性 → {name}")
    assert offenders == [], (
        "domain 只能在 allowlist 的 legacy 适配器中惰性 import ai：\n"
        + "\n".join(offenders))


def test_legacy_llm_adapters_are_retired() -> None:
    """V4-02 登记的 legacy LLM 适配器随 V2 后端整体退休（不再有 domain → ai 的桥）。

    post-release cleanup 之前，domain 里有一批 legacy structured provider 通过
    函数内惰性 import `novelforge.ai` 调用模型；这些模块（spec/llm、
    planning/plot_synthesis、planning/route_candidates、creative、settings_gen、
    outline_forge、ai_recommendations）已经全部删除，因此 allowlist 只剩空集：
    domain 现在**完全不得** import ai。
    """

    offenders: list[str] = []
    for path in python_files("story_engine"):
        relative = _relative(path)
        for name, line in iter_imports(path):
            if name.startswith("novelforge.ai"):
                offenders.append(f"{relative}:{line} → {name}")
    assert offenders == [], (
        "domain 不得再 import ai（legacy 适配器已退休）：\n" + "\n".join(offenders))


# ---------------------------------------------------------------- V4-03（memory）
def test_memory_does_not_depend_on_interface_or_application() -> None:
    offenders: list[str] = []
    for path in python_files("memory"):
        for name, line in imports_matching(path, MEMORY_FORBIDDEN_PREFIXES):
            offenders.append(f"{_relative(path)}:{line} → {name}")
    assert offenders == [], (
        "memory 不得依赖 interface / application / provider 实现：\n"
        + "\n".join(offenders))


def test_domain_and_ai_do_not_import_memory() -> None:
    offenders: list[str] = []
    for package in ("story_engine", "story_builder", "ai", "core", "persistence"):
        for path in python_files(package):
            for name, line in iter_imports(path):
                if name.startswith("novelforge.memory"):
                    offenders.append(f"{_relative(path)}:{line} → {name}")
    assert offenders == [], (
        "依赖方向必须是 memory → domain / ai（不得反向）：\n" + "\n".join(offenders))


# ---------------------------------------------------------------- V4-04（generation）
GENERATION_FORBIDDEN_PREFIXES = (
    "novelforge.api", "novelforge.ai.providers", "fastapi", "starlette", "mcp",
    "httpx", "requests", "urllib", "openai", "anthropic",
)


def test_generation_module_boundaries() -> None:
    offenders: list[str] = []
    for path in python_files("generation"):
        for name, line in iter_imports(path):
            if name.startswith(GENERATION_FORBIDDEN_PREFIXES):
                offenders.append(f"{_relative(path)}:{line} → {name}")
    assert offenders == [], (
        "generation 不得依赖 interface / provider 实现 / HTTP client：\n"
        + "\n".join(offenders))


def test_layers_do_not_import_generation() -> None:
    offenders: list[str] = []
    for package in ("story_engine", "story_builder", "ai", "memory", "blueprint",
                    "core", "persistence"):
        for path in python_files(package):
            for name, line in iter_imports(path):
                if name.startswith("novelforge.generation"):
                    offenders.append(f"{_relative(path)}:{line} → {name}")
    assert offenders == [], (
        "generation 是上层消费者；domain / ai / memory / blueprint 不得依赖它：\n"
        + "\n".join(offenders))
