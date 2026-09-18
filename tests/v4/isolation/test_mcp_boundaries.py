"""永久守卫：V4-08 interfaces/mcp 模块边界（`docs/v4/V4_MODULE_BOUNDARIES.md` §3.15）。

```text
interfaces.mcp → application.services（唯一业务依赖）+ core（ids/errors）+ MCP SDK
禁止           → blueprint / generation / quality / editor / delivery / memory / ai /
                 persistence / story_engine / api / 自行 HTTP
禁止           → application / domain / 各业务模块反向 import interfaces.mcp
```
"""

from __future__ import annotations

from _guard_utils import (
    ROOT,
    identifier_names,
    imports_matching,
    iter_imports,
    module_level_imports,
    python_files,
    string_literals,
)

MCP_ALLOWED_NOVELFORGE_PREFIXES = (
    "novelforge.application", "novelforge.interfaces", "novelforge.core",
)

MCP_FORBIDDEN_PREFIXES = (
    "novelforge.blueprint", "novelforge.generation", "novelforge.quality",
    "novelforge.editor", "novelforge.delivery", "novelforge.memory",
    "novelforge.ai", "novelforge.persistence", "novelforge.story_engine",
    "novelforge.story_builder", "novelforge.api", "novelforge.models",
    "httpx", "requests", "aiohttp", "fastapi", "starlette",
    # urllib.parse 只做 URI 解析（协议层职责）；HTTP client 仍然禁止（§61）
    "urllib.request", "urllib.error",
)

#: 反向依赖：这些包不得 import interfaces（含 mcp）
MCP_CONSUMERS_FORBIDDEN = (
    "core", "persistence", "story_engine", "story_builder", "ai", "memory",
    "blueprint", "generation", "quality", "editor", "delivery", "api",
    "application", "legacy", "observability",
)

#: MCP 层不得自行构造下层对象 / 执行业务规则
FORBIDDEN_IDENTIFIERS = (
    "BlueprintRepository", "QualityStore", "EditorStore", "DeliveryStore",
    "RepairPlanner", "RepairExecutor", "RepairVerifier", "BlueprintCompiler",
    "DeliveryService", "QualityService", "BlueprintGenerationService",
    "ContextBuilder", "MemoryService", "QualityPolicy", "DeliveryPolicy",
)


def _relative(path) -> str:
    return str(path.relative_to(ROOT)).replace("\\", "/")


def _mcp_files():
    return python_files("interfaces")


def test_mcp_only_depends_on_application_and_core() -> None:
    offenders: list[str] = []
    for path in _mcp_files():
        for name, line in iter_imports(path):
            if not name.startswith("novelforge."):
                continue
            if not name.startswith(MCP_ALLOWED_NOVELFORGE_PREFIXES):
                offenders.append(f"{_relative(path)}:{line} → {name}")
    assert offenders == [], (
        "MCP 只能依赖 application.services / core：\n" + "\n".join(offenders))


def test_mcp_does_not_import_lower_layers_or_http_clients() -> None:
    offenders: list[str] = []
    for path in _mcp_files():
        for name, line in iter_imports(path):
            if name.startswith(MCP_FORBIDDEN_PREFIXES):
                offenders.append(f"{_relative(path)}:{line} → {name}")
    assert offenders == [], (
        "MCP 不得依赖业务模块 / REST 框架 / HTTP client：\n" + "\n".join(offenders))


def test_mcp_does_not_build_artifact_paths_or_read_files() -> None:
    offenders: list[str] = []
    for path in _mcp_files():
        for value, line in string_literals(path):
            lowered = value.lower()
            if lowered.startswith(("novel/", "novel\\", "workspace/",
                                   "workspace\\")) or "authoring/" in lowered:
                offenders.append(f"{_relative(path)}:{line} → {value!r}")
        text = path.read_text(encoding="utf-8")
        for token in ("open(", 'Path("', "Path('", "read_text(", "read_bytes("):
            if token in text:
                offenders.append(f"{_relative(path)} → {token}")
    assert offenders == [], (
        "MCP 不得自行拼路径 / 直接读文件（§43、§67）：\n" + "\n".join(offenders))


def test_mcp_tools_do_not_construct_business_objects() -> None:
    """§2 / §86：tool 实现只调用 Application Service，不构造业务对象。"""

    offenders: list[str] = []
    for path in python_files("interfaces/mcp/tools") + \
            python_files("interfaces/mcp/resources"):
        names = {name for name, _line in identifier_names(path)}
        hits = sorted(names & set(FORBIDDEN_IDENTIFIERS))
        if hits:
            offenders.append(f"{_relative(path)} → {hits}")
    assert offenders == [], (
        "MCP tool / resource 只能通过 Application Service 访问能力：\n"
        + "\n".join(offenders))


def test_mcp_tool_handlers_stay_thin() -> None:
    """§2：tool 实现应保持薄封装（不做业务流程编排）。"""

    offenders: list[str] = []
    for path in python_files("interfaces/mcp/tools"):
        text = path.read_text(encoding="utf-8")
        for marker in ("for issue in", "while ", "if gate ==", "retry(",
                       "except Exception as exc:\n        # 业务规则"):
            if marker in text:
                offenders.append(f"{_relative(path)} → {marker}")
    assert offenders == [], (
        "MCP tool 内不得出现业务流程编排：\n" + "\n".join(offenders))


def test_layers_do_not_import_mcp_interface() -> None:
    offenders: list[str] = []
    for package in MCP_CONSUMERS_FORBIDDEN:
        for path in python_files(package):
            for name, line in iter_imports(path):
                if name.startswith("novelforge.interfaces"):
                    offenders.append(f"{_relative(path)}:{line} → {name}")
    assert offenders == [], (
        "Application / 业务模块不得依赖 interfaces.mcp（§59）：\n"
        + "\n".join(offenders))


def test_mcp_module_level_imports_are_light() -> None:
    offenders: list[str] = []
    for path in _mcp_files():
        for name, line in module_level_imports(path):
            if name.startswith(("novelforge.blueprint", "novelforge.delivery",
                                "novelforge.editor", "novelforge.quality",
                                "novelforge.generation", "novelforge.memory",
                                "novelforge.ai", "novelforge.persistence")):
                offenders.append(f"{_relative(path)}:{line} 模块级 → {name}")
    assert offenders == [], (
        "MCP 顶层不得 import 业务模块：\n" + "\n".join(offenders))


def test_mcp_public_contract_is_small() -> None:
    import novelforge.interfaces.mcp as mcp

    exported = set(mcp.__all__)
    assert {"MCPDispatcher", "create_mcp_server", "MCPToolRegistry",
            "MCPResourceRegistry", "ToolSpec", "ResourceSpec", "ToolResult",
            "MCP_INTERFACE_VERSION", "parse_uri", "map_error"} <= exported
    assert not [name for name in exported if name.startswith("_")]
    # 具体 resource / tool 模块不导出
    assert not [name for name in exported
                if name in ("blueprint", "quality", "delivery", "editor", "tools",
                            "resources", "server")]


def test_interface_layer_never_calls_own_rest_api() -> None:
    """§8 / §61：MCP 与 REST 是平级 adapter，不得通过 HTTP 调自己的 API。"""

    offenders: list[str] = []
    for path in _mcp_files():
        text = path.read_text(encoding="utf-8")
        for marker in ("/api/story-builder", "localhost:", "127.0.0.1"):
            if marker in text:
                offenders.append(f"{_relative(path)} → {marker}")
    assert offenders == [], (
        "MCP 不得调用自己的 REST API：\n" + "\n".join(offenders))


def test_requirements_records_mcp_sdk() -> None:
    text = (ROOT / "requirements.txt").read_text(encoding="utf-8")
    assert "mcp" in text
    assert "starlette<0.47" in text or "starlette <0.47" in text
