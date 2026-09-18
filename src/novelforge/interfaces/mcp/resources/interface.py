"""接口自描述资源（V4-08 §54、§78）：`novelforge://interface`。

只包含接口元数据（版本 / 工具表 / 资源表），**不含任何作品数据**。
"""

from __future__ import annotations

from typing import Any

from ..contracts import (
    MCP_INTERFACE_VERSION,
    MCP_SERVER_NAME,
    ResourceSpec,
    resource_table,
    tool_table,
)
from ..payloads import json_payload
from ..registry import MCPResourceRegistry


def register(registry: MCPResourceRegistry, *,
             spec_source: Any = None) -> ResourceSpec:
    def handler(_context: Any, target: Any) -> Any:
        tables = dict(spec_source() if callable(spec_source) else {})
        payload = {
            "server": MCP_SERVER_NAME,
            "mcp_interface_version": MCP_INTERFACE_VERSION,
            "uri_scheme": "novelforge://",
            "tools": tool_table(tables.get("tools", ())),
            "resources": resource_table(tables.get("resources", ())),
            "notes": ["Resources 只读；mutation 只能通过 Tools",
                      "每个 tool / resource 都要求显式 novel_id（interface 除外）",
                      "工具结果统一 Result Envelope；错误码稳定且保留 cause"],
        }
        return json_payload(target.uri, payload)

    return registry.register(ResourceSpec(
        uri="novelforge://interface", name="interface",
        description="MCP 接口元数据（版本 / 工具表 / 资源表）",
        mime_type="application/json", service="interfaces.mcp"), kinds=("interface",),
        handler=handler)


__all__ = ["register"]
