"""MCP Tool / Resource 注册表（V4-08 §15、§53–§54、§75）。

```text
MCPToolRegistry      工具声明 + 处理器（server.py 不写 if tool_name == ...）
MCPResourceRegistry  资源声明 + 处理器（按 URI 形状分派）
```

只为注册与查表；不包含业务规则。处理器的实现必须是薄封装（调用 Application Service）。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Mapping, Sequence

from .contracts import ResourceSpec, ToolSpec
from .errors import MCPToolNotFound
from .uri import ResourceTarget

#: 工具处理器签名：handle(context, arguments) -> ToolResult
ToolHandler = Callable[[Any, Mapping[str, Any]], Any]
#: 资源处理器签名：handle(context, target) -> ResourcePayload
ResourceHandler = Callable[[Any, ResourceTarget], Any]


@dataclass(frozen=True)
class ToolRegistration:
    spec: ToolSpec
    handler: ToolHandler


@dataclass(frozen=True)
class ResourceRegistration:
    spec: ResourceSpec
    kinds: tuple[str, ...]
    handler: ResourceHandler


class MCPToolRegistry:
    def __init__(self) -> None:
        self._rows: dict[str, ToolRegistration] = {}

    def register(self, spec: ToolSpec, handler: ToolHandler) -> ToolSpec:
        if spec.name in self._rows:
            raise ValueError(f"tool 重复注册：{spec.name}")
        self._rows[spec.name] = ToolRegistration(spec=spec, handler=handler)
        return spec

    def unregister_owner(self, owner_id: str) -> int:
        """按 owner 卸载（Core owner 不允许卸载，V4-09 §74）。"""

        before = len(self._rows)
        self._rows = {key: value for key, value in self._rows.items()
                      if value.spec.owner_id != str(owner_id)
                      or value.spec.owner_type == "core"}
        return before - len(self._rows)

    def core_names(self) -> tuple[str, ...]:
        return tuple(sorted(key for key, value in self._rows.items()
                            if value.spec.owner_type == "core"))

    def owners(self) -> dict[str, tuple[str, ...]]:
        result: dict[str, list[str]] = {}
        for key, value in self._rows.items():
            result.setdefault(value.spec.owner_id, []).append(key)
        return {owner: tuple(sorted(names)) for owner, names in sorted(result.items())}

    def get(self, name: str) -> ToolRegistration:
        row = self._rows.get(str(name))
        if row is None:
            raise MCPToolNotFound(f"未知 tool：{name}",
                                  details={"known": sorted(self._rows)})
        return row

    def names(self) -> tuple[str, ...]:
        return tuple(sorted(self._rows))

    def specs(self) -> tuple[ToolSpec, ...]:
        return tuple(self._rows[name].spec for name in self.names())

    def __len__(self) -> int:
        return len(self._rows)


class MCPResourceRegistry:
    def __init__(self) -> None:
        self._rows: list[ResourceRegistration] = []

    def register(self, spec: ResourceSpec, *, kinds: Sequence[str],
                 handler: ResourceHandler) -> ResourceSpec:
        resolved = tuple(str(kind) for kind in kinds if str(kind))
        if not resolved:
            raise ValueError(f"resource {spec.uri} 必须声明 kind")
        self._rows.append(ResourceRegistration(spec=spec, kinds=resolved,
                                               handler=handler))
        return spec

    def resolve(self, target: ResourceTarget) -> ResourceRegistration:
        for row in self._rows:
            if target.kind in row.kinds:
                return row
        raise MCPToolNotFound(f"没有可处理 {target.kind} 的资源处理器",
                              details={"kind": target.kind})

    def unregister_owner(self, owner_id: str) -> int:
        before = len(self._rows)
        self._rows = [row for row in self._rows
                      if row.spec.owner_id != str(owner_id)
                      or row.spec.owner_type == "core"]
        return before - len(self._rows)

    def core_uris(self) -> tuple[str, ...]:
        return tuple(sorted(row.spec.uri for row in self._rows
                            if row.spec.owner_type == "core"))

    def owners(self) -> dict[str, tuple[str, ...]]:
        result: dict[str, list[str]] = {}
        for row in self._rows:
            result.setdefault(row.spec.owner_id, []).append(row.spec.uri)
        return {owner: tuple(sorted(uris)) for owner, uris in sorted(result.items())}

    def specs(self) -> tuple[ResourceSpec, ...]:
        return tuple(row.spec for row in self._rows)

    def static_specs(self) -> tuple[ResourceSpec, ...]:
        return tuple(row.spec for row in self._rows if not row.spec.template)

    def template_specs(self) -> tuple[ResourceSpec, ...]:
        return tuple(row.spec for row in self._rows if row.spec.template)

    def __len__(self) -> int:
        return len(self._rows)


__all__ = [
    "MCPResourceRegistry", "MCPToolRegistry", "ResourceHandler",
    "ResourceRegistration", "ToolHandler", "ToolRegistration",
]
