"""MCP 接口契约（V4-08 §15、§29–§30、§51–§54）。

```text
MCP_INTERFACE_VERSION   本接口的版本（与 blueprint / delivery schema 版本无关）
ToolSpec                工具声明（name / version / input schema / read_only / mutation /
                        requires_revision / supports_dry_run / annotations）
ResourceSpec            资源声明（uri / name / mime_type / template）
ResultEnvelope          统一工具结果（ok / request_id / novel_id / operation / result /
                        revision / issues / warnings / resources）
```

**MCP IS NOT THE BUSINESS LAYER**：这里只声明协议形状，不含任何业务规则。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

from novelforge.core.ids import digest_payload, new_request_id

#: MCP 接口版本（§53：与 BLUEPRINT_SCHEMA_VERSION / DELIVERY_SCHEMA_VERSION 相互独立）
MCP_INTERFACE_VERSION = 1
MCP_SERVER_NAME = "novelforge"

#: 权限级别（与 V4_MCP_SPEC §4.3 对齐；本阶段只做 reader / author 两档声明）
PERMISSIONS: tuple[str, ...] = ("reader", "author", "operator")


@dataclass(frozen=True)
class ToolSpec:
    """一个 MCP tool 的声明（§15）。"""

    name: str
    description: str
    input_schema: Mapping[str, Any]
    output_schema: Mapping[str, Any]
    version: int = MCP_INTERFACE_VERSION
    read_only: bool = False
    mutation: bool = True
    requires_revision: bool = False
    supports_dry_run: bool = False
    idempotent: bool = True
    permission: str = "author"
    expensive: bool = False
    destructive: bool = False
    possible_errors: tuple[str, ...] = ()
    #: 实现必须是薄封装：这里记录它调用的 Application Service 方法（供审计与守卫）
    service: str = ""
    #: V4-09 §75：注册归属（core | plugin + owner_id）
    owner_type: str = "core"
    owner_id: str = "novelforge"

    def __post_init__(self) -> None:
        if not str(self.name or "").strip():
            raise ValueError("ToolSpec 需要 name")
        if not isinstance(self.input_schema, Mapping):
            raise ValueError("ToolSpec.input_schema 必须是 JSON Schema 对象")
        if self.permission not in PERMISSIONS:
            raise ValueError(f"未知 permission：{self.permission}")
        if self.read_only and self.mutation:
            raise ValueError(f"tool {self.name} 不能同时是 read_only 与 mutation")
        if self.mutation and not self.input_schema.get("properties", {}).get(
                "novel_id"):
            raise ValueError(f"mutation tool {self.name} 必须显式声明 novel_id 参数")

    @property
    def digest(self) -> str:
        return digest_payload({"name": self.name, "version": self.version,
                               "input": dict(self.input_schema),
                               "read_only": self.read_only,
                               "dry_run": self.supports_dry_run})

    def as_dict(self) -> dict[str, Any]:
        return {"name": self.name, "version": self.version,
                "description": self.description,
                "input_schema": dict(self.input_schema),
                "output_schema": dict(self.output_schema),
                "read_only": self.read_only, "mutation": self.mutation,
                "requires_revision": self.requires_revision,
                "supports_dry_run": self.supports_dry_run,
                "idempotent": self.idempotent, "permission": self.permission,
                "expensive": self.expensive, "destructive": self.destructive,
                "possible_errors": list(self.possible_errors),
                "service": self.service,
                "owner_type": self.owner_type, "owner_id": self.owner_id}


@dataclass(frozen=True)
class ResourceSpec:
    """一个 MCP resource（或 resource template）的声明（§11、§78）。"""

    uri: str
    name: str
    description: str = ""
    mime_type: str = "application/json"
    paginated: bool = False
    template: bool = False
    service: str = ""
    owner_type: str = "core"
    owner_id: str = "novelforge"

    def as_dict(self) -> dict[str, Any]:
        return {"uri": self.uri, "name": self.name,
                "description": self.description, "mime_type": self.mime_type,
                "paginated": self.paginated, "template": self.template,
                "service": self.service,
                "owner_type": self.owner_type, "owner_id": self.owner_id}


@dataclass(frozen=True)
class ToolResult:
    """统一 Result Envelope（§29）。"""

    operation: str
    ok: bool = True
    request_id: str = ""
    novel_id: str = ""
    result: Mapping[str, Any] = field(default_factory=dict)
    revision: int = 0
    revision_before: int = 0
    issues: tuple[Mapping[str, Any], ...] = ()
    warnings: tuple[str, ...] = ()
    resources: tuple[str, ...] = ()
    usage: Mapping[str, Any] = field(default_factory=dict)
    errors: tuple[Mapping[str, Any], ...] = ()
    dry_run: bool = False
    summary: str = ""

    def __post_init__(self) -> None:
        if not self.request_id:
            object.__setattr__(self, "request_id", new_request_id("mcp"))

    def as_dict(self) -> dict[str, Any]:
        return {"ok": bool(self.ok) and not self.errors,
                "operation": self.operation, "request_id": self.request_id,
                "novel_id": self.novel_id,
                "revision": int(self.revision),
                "revision_before": int(self.revision_before),
                "dry_run": bool(self.dry_run),
                "result": dict(self.result),
                "issues": [dict(row) for row in self.issues],
                "warnings": list(self.warnings),
                "resources": list(self.resources),
                "usage": dict(self.usage),
                "errors": [dict(row) for row in self.errors],
                "summary": self.summary}


def envelope_json(envelope: Mapping[str, Any]) -> str:
    import json

    return json.dumps(dict(envelope), ensure_ascii=False, indent=1, sort_keys=True)


def tool_table(specs: Sequence[ToolSpec]) -> list[dict[str, Any]]:
    """SSOT 用的工具表（§78）。"""

    return [{"tool": spec.name, "mutation": spec.mutation,
             "service": spec.service, "revision": spec.requires_revision,
             "idempotency": spec.idempotent, "dry_run": spec.supports_dry_run,
             "read_only": spec.read_only}
            for spec in sorted(specs, key=lambda row: row.name)]


def resource_table(specs: Sequence[ResourceSpec]) -> list[dict[str, Any]]:
    return [{"resource": spec.uri, "service": spec.service,
             "pagination": spec.paginated, "mime": spec.mime_type,
             "template": spec.template}
            for spec in sorted(specs, key=lambda row: row.uri)]


__all__ = [
    "MCP_INTERFACE_VERSION", "MCP_SERVER_NAME", "PERMISSIONS", "ResourceSpec",
    "ToolResult", "ToolSpec", "envelope_json", "resource_table", "tool_table",
]
