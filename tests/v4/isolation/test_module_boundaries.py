"""永久守卫：模块依赖边界（V4-01，`docs/v4/V4_MODULE_BOUNDARIES.md` §4）。

用 import 图（AST）机械检查依赖方向。**存量例外以显式白名单登记**：
白名单只允许缩小，不允许新增（新增即违反模块边界）。
"""

from __future__ import annotations

from _guard_utils import ROOT, imports_matching, python_files

#: interface 层不得直接依赖 domain —— 存量例外（V4-01 记录，后续只减不增）
INTERFACE_TO_DOMAIN_ALLOWLIST = {
    "src/novelforge/api/story_builder_routes.py",
    "src/novelforge/api/canon_routes.py",
    "src/novelforge/api/app.py",
}

#: application 层允许临时包装 V3 application（story_builder），但不允许依赖 interface
APPLICATION_FORBIDDEN_PREFIXES = ("novelforge.api", "fastapi", "starlette")

DOMAIN_FORBIDDEN_PREFIXES = (
    "fastapi", "starlette", "mcp", "httpx", "requests",
    "openai", "anthropic",
)


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

