"""MCP Tool 定义（V4-08 §15–§27、§49–§52）。

每个 tool 都是**薄封装**：`DTO 校验 → Application Service 调用 → Result Envelope`。
工具表（`docs/v4/V4_MCP_CONTRACT.md` §4）由本模块的注册表产生，是唯一的 tool SSOT。
"""

from __future__ import annotations

from typing import Any, Callable, Mapping

from pydantic import BaseModel, ConfigDict

from ..contracts import ToolSpec
from ..registry import MCPToolRegistry, ToolHandler


class MCPInput(BaseModel):
    """MCP tool 输入基类：严格 schema（§51：不接受额外字段）。"""

    model_config = ConfigDict(extra="forbid")


def build_tool(*, name: str, description: str, dto: type[MCPInput],
               service: str, impl: Callable[[Any, Any], Any],
               read_only: bool = False, requires_revision: bool = False,
               supports_dry_run: bool = False, idempotent: bool = True,
               permission: str = "author", expensive: bool = False,
               destructive: bool = False,
               output_schema: Mapping[str, Any] | None = None,
               possible_errors: tuple[str, ...] = ()) -> tuple[ToolSpec, ToolHandler]:
    """把「DTO + 实现」编译成 (ToolSpec, handler)。"""

    schema = dto.model_json_schema()
    schema["additionalProperties"] = False
    spec = ToolSpec(
        name=name, description=description, input_schema=schema,
        output_schema=dict(output_schema or {"type": "object"}),
        read_only=read_only, mutation=not read_only,
        requires_revision=requires_revision, supports_dry_run=supports_dry_run,
        idempotent=idempotent, permission=permission, expensive=expensive,
        destructive=destructive, possible_errors=possible_errors, service=service)

    def handler(context: Any, arguments: Mapping[str, Any]) -> Any:
        payload = dto.model_validate(dict(arguments or {}))
        return impl(context, payload)

    return spec, handler


def build_tool_registry() -> MCPToolRegistry:
    from . import delivery as delivery_tools
    from . import editor as editor_tools
    from . import generation as generation_tools
    from . import quality as quality_tools

    registry = MCPToolRegistry()
    for module in (generation_tools, editor_tools, quality_tools, delivery_tools):
        module.register(registry)
    return registry


__all__ = ["MCPInput", "build_tool", "build_tool_registry"]
