"""MCP Server（V4-08 §39–§42、§54）：官方 MCP Python SDK 的薄适配层。

```python
server = create_mcp_server(project_root, services_factory=application_services)
```

```text
· 依赖注入：project_root / services_factory / gateway（不在 import 时扫描项目或打开模型）
· 惰性：每次调用按 novel_id 构造 Application 能力束（§42）
· 协议：官方 SDK（`mcp`）负责 JSON-RPC / stdio framing / tool & resource 协商（§40）
· 本模块只做协议转换；业务能力全部来自 `application.services`（§2、§7）
```

工具结果以 **JSON 文本块**返回统一 Result Envelope；失败时 `isError=True`
且文本仍是同一个 envelope（`ok=false` + `errors[code]`），SDK 1.x 无 structuredContent。
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Sequence

from .contracts import MCP_INTERFACE_VERSION, MCP_SERVER_NAME
from .dispatch import MCPDispatcher
from .errors import MCPError
from .serialization import content_blocks

try:  # pragma: no cover - 依赖可选安装（requirements.txt 记录 mcp）
    from mcp.server import Server
    from mcp.server.models import InitializationOptions
    from mcp.server.stdio import stdio_server
    import mcp.types as types

    MCP_SDK_AVAILABLE = True
except Exception:  # noqa: BLE001 - SDK 未安装时给出明确错误
    MCP_SDK_AVAILABLE = False
    Server = None  # type: ignore[assignment]
    types = None  # type: ignore[assignment]
    InitializationOptions = None  # type: ignore[assignment]
    stdio_server = None  # type: ignore[assignment]


class MCPSdkUnavailable(RuntimeError):
    code = "MCP_SDK_UNAVAILABLE"


class MCPToolFailure(MCPError):
    """工具失败（SDK 适配层用它把 envelope 原样返回并标记 isError=True）。"""

    code = "MCP_TOOL_FAILED"


def default_services_factory() -> Callable[..., Any]:
    """默认的 Application 能力束工厂（MCP 只认识 application.services，§7）。"""

    from novelforge.application.services.facade import application_services

    return application_services


def create_dispatcher(project_root: Path | str, *,
                      services_factory: Callable[..., Any] | None = None,
                      gateway: Any = None, memory: Any = None
                      ) -> MCPDispatcher:
    """构造协议无关的 dispatcher（in-process 测试与 server 共用）。"""

    resolved_factory = services_factory or default_services_factory()

    def factory(root: Any, novel_id: str, **kwargs: Any) -> Any:
        return resolved_factory(root, novel_id, gateway=gateway, memory=memory,
                                **kwargs)

    return MCPDispatcher(project_root, services_factory=factory)


def _require_sdk() -> None:
    if not MCP_SDK_AVAILABLE:
        raise MCPSdkUnavailable(
            "未安装官方 MCP SDK：请先安装 `mcp`（requirements.txt 记录版本区间），"
            "再启动 stdio server。")


def create_mcp_server(project_root: Path | str, *,
                      services_factory: Callable[..., Any] | None = None,
                      gateway: Any = None, memory: Any = None,
                      dispatcher: MCPDispatcher | None = None,
                      name: str = MCP_SERVER_NAME) -> Any:
    """构造 MCP Server（低层 SDK + 本模块注册表）。"""

    _require_sdk()
    resolved = dispatcher or create_dispatcher(project_root,
                                               services_factory=services_factory,
                                               gateway=gateway, memory=memory)
    server = Server(name, version=str(MCP_INTERFACE_VERSION))

    @server.list_tools()
    async def list_tools() -> list[Any]:
        return [_tool_model(spec) for spec in resolved.tool_specs()]

    @server.call_tool()
    async def call_tool(tool_name: str, arguments: Mapping[str, Any]
                        ) -> list[Any]:
        envelope = resolved.invoke_tool(tool_name, arguments)
        text = content_blocks(envelope)
        if not envelope.get("ok"):
            raise MCPToolFailure(text)
        return [types.TextContent(type="text", text=text)]

    @server.list_resources()
    async def list_resources() -> list[Any]:
        return [_resource_model(spec) for spec in resolved.resources.static_specs()]

    @server.list_resource_templates()
    async def list_resource_templates() -> list[Any]:
        return [_resource_template_model(spec)
                for spec in resolved.resources.template_specs()]

    @server.read_resource()
    async def read_resource(uri: Any) -> Iterable[Any]:
        from mcp.server.lowlevel.helper_types import ReadResourceContents

        payload = resolved.read_resource(str(uri))
        return [ReadResourceContents(content=payload.content,
                                     mime_type=payload.mime_type)]

    server.dispatcher = resolved          # type: ignore[attr-defined]
    return server


def _tool_model(spec: Any) -> Any:
    annotations = types.ToolAnnotations(
        title=spec.name, readOnlyHint=bool(spec.read_only),
        destructiveHint=bool(spec.destructive),
        idempotentHint=bool(spec.idempotent), openWorldHint=False)
    return types.Tool(name=spec.name, description=spec.description,
                      inputSchema=dict(spec.input_schema), annotations=annotations)


def _resource_model(spec: Any) -> Any:
    return types.Resource(uri=spec.uri, name=spec.name,
                          description=spec.description, mimeType=spec.mime_type)


def _resource_template_model(spec: Any) -> Any:
    return types.ResourceTemplate(uriTemplate=spec.uri, name=spec.name,
                                  description=spec.description,
                                  mimeType=spec.mime_type)


async def run_stdio(server: Any) -> None:  # pragma: no cover - 需要真实 stdio 会话
    _require_sdk()
    options = InitializationOptions(
        server_name=MCP_SERVER_NAME,
        server_version=str(MCP_INTERFACE_VERSION),
        capabilities=server.get_capabilities(notification_options=None,
                                            experimental_capabilities={}),
    )
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, options)


def main(project_root: Path | str | None = None) -> None:  # pragma: no cover
    """`python -m novelforge.interfaces.mcp` 入口（stdio transport）。"""

    import os

    root = Path(project_root or os.environ.get("NOVELFORGE_PROJECT_ROOT", ".")).resolve()
    server = create_mcp_server(root)
    asyncio.run(run_stdio(server))


__all__ = [
    "MCPSdkUnavailable", "MCPToolFailure", "MCP_SDK_AVAILABLE", "create_dispatcher",
    "create_mcp_server", "default_services_factory", "main", "run_stdio",
]
