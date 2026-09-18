"""Plugin SDK 契约（V4-09 §8–§9、§25、§32、§45）。

第三方插件**只依赖本模块**：它不暴露 repository / store / persistence / provider。

```text
Contribution            声明一个贡献（type + id + version + permissions_required + factory）
ContributionKind        插件可以贡献什么（exporter / quality_evaluator / mcp_tool / mcp_resource）
PluginAIClient          窄 AI 能力（经 Host → LLMGateway；插件不得直接调模型）
PLUGIN_SDK_VERSION      SDK 版本（= PLUGIN_API_VERSION）
```
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Protocol, Sequence

from ..contracts import (
    CONTRIBUTION_TYPES,
    PLUGIN_API_VERSION,
    PLUGIN_PERMISSIONS,
    PluginContribution as _HostContribution,
)

PLUGIN_SDK_VERSION = PLUGIN_API_VERSION

#: 贡献类型（与 Host 的 CONTRIBUTION_TYPES 一致）
CONTRIBUTION_KINDS: tuple[str, ...] = CONTRIBUTION_TYPES
ContributionKind = str

#: 插件作者可见的 permission（与 Host 白名单一致）
PERMISSIONS: tuple[str, ...] = PLUGIN_PERMISSIONS


@dataclass(frozen=True)
class Contribution:
    """插件返回给 Host 的贡献声明（Host 负责验证与注册，§71）。"""

    type: ContributionKind
    contribution_id: str
    factory: Any
    version: int = 1
    permissions_required: tuple[str, ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def as_host_contribution(self) -> _HostContribution:
        return _HostContribution(
            type=str(self.type), contribution_id=str(self.contribution_id),
            factory=self.factory, version=int(self.version),
            permissions_required=tuple(self.permissions_required),
            metadata=dict(self.metadata))


class PluginAIClient(Protocol):
    """Host 提供的窄 AI 能力（§45–§46）：插件不接触 provider / secret。"""

    def complete(self, *, prompt: str, max_tokens: int = 400,
                 operation: str = "") -> Mapping[str, Any]:
        ...


def exporter_contribution(*, exporter_id: str, format: str, mime_type: str,
                          extension: str, factory: Any, version: int = 1,
                          profiles_supported: Sequence[str] = (), **metadata: Any
                          ) -> Contribution:
    """构造 exporter 贡献（数据来自已选定的交付快照，§32–§33）。"""

    return Contribution(
        type="exporter", contribution_id=str(exporter_id), factory=factory,
        version=int(version), permissions_required=("delivery.export",),
        metadata={"format": str(format), "mime_type": str(mime_type),
                  "extension": str(extension),
                  "profiles_supported": list(profiles_supported), **metadata})


def quality_contribution(*, evaluator_id: str, gate: str, factory: Any,
                         version: int = 1, supported_node_types: Sequence[str] = (),
                         **metadata: Any) -> Contribution:
    """构造 quality evaluator 贡献（只读；issue code 必须 namespaced，§35–§37）。"""

    return Contribution(
        type="quality_evaluator", contribution_id=str(evaluator_id),
        factory=factory, version=int(version),
        permissions_required=("quality.evaluate",),
        metadata={"gate": str(gate),
                  "supported_node_types": list(supported_node_types), **metadata})


def mcp_tool_contribution(*, name: str, factory: Any, input_schema: Mapping[str, Any],
                          description: str = "", version: int = 1,
                          read_only: bool = False, dry_run: bool = False,
                          **metadata: Any) -> Contribution:
    return Contribution(
        type="mcp_tool", contribution_id=str(name), factory=factory,
        version=int(version), permissions_required=("mcp.extend",),
        metadata={"description": str(description),
                  "input_schema": dict(input_schema), "read_only": bool(read_only),
                  "dry_run": bool(dry_run), **metadata})


def mcp_resource_contribution(*, uri: str, factory: Any, name: str = "",
                              mime_type: str = "application/json", version: int = 1,
                              **metadata: Any) -> Contribution:
    return Contribution(
        type="mcp_resource", contribution_id=str(uri), factory=factory,
        version=int(version), permissions_required=("mcp.extend",),
        metadata={"uri": str(uri), "name": str(name or uri),
                  "mime_type": str(mime_type), **metadata})


__all__ = [
    "CONTRIBUTION_KINDS", "PERMISSIONS", "PLUGIN_SDK_VERSION", "Contribution",
    "ContributionKind", "PluginAIClient", "exporter_contribution",
    "mcp_resource_contribution", "mcp_tool_contribution", "quality_contribution",
]
