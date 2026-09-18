"""MCP Resource 定义（V4-08 §10–§14、§45–§48）。

Resources 一律只读；数据全部来自 Application Service；URI 由 `..uri` 解析。
"""

from __future__ import annotations

from typing import Any, Callable, Mapping

from ..registry import MCPResourceRegistry

SpecSource = Callable[[], Mapping[str, Any]]


def build_resource_registry(*, spec_source: SpecSource | None = None
                            ) -> MCPResourceRegistry:
    from . import blueprint as blueprint_resources
    from . import delivery as delivery_resources
    from . import interface as interface_resources
    from . import quality as quality_resources

    registry = MCPResourceRegistry()
    for module in (interface_resources, blueprint_resources, quality_resources,
                   delivery_resources):
        module.register(registry, spec_source=spec_source)
    return registry


__all__ = ["SpecSource", "build_resource_registry"]
