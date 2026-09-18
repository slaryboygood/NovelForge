"""MCP 扩展（V4-09 §38–§42、§77、§97）：插件贡献 tool / resource。

```text
· 插件只返回 contribution；注册由 Host adapter 完成（§38、§71）
· 贡献名必须 namespaced：plugin.<plugin_id>.<name>（§39）
· Core 23 tools / 13 resources 不可覆盖、不可修改（§40、§77）
· disable 后新的 lookup 不再返回该贡献（§74）
```
"""

from __future__ import annotations

from typing import Any, Mapping, Sequence

from ..contracts import PluginContribution
from ..errors import PluginRegistrationError
from . import BaseAdapter

def default_narrow_context(*, plugin_id: str, plugin_version: str,
                          approved_permissions: Sequence[str] = (),
                          host: Any = None) -> Any:
    """把 Application 能力束收敛成插件可见的窄上下文（§24–§25、§42）。

    插件**拿不到** `ApplicationServices` 全对象：只有已批准 capability
    （本阶段：`blueprint.read` 对应的只读机器视图）+ 自己的 plugin 元数据。
    """

    from ..contracts import PluginConfig
    from ..sdk.context import PluginContext

    def _blueprint_view() -> Mapping[str, Any]:
        export = getattr(host, "export", None)
        if export is None or not hasattr(export, "blueprint_view"):
            return {}
        return dict(export.blueprint_view())

    return PluginContext(
        plugin_id=str(plugin_id), plugin_version=str(plugin_version),
        approved_permissions=tuple(approved_permissions),
        config=PluginConfig(plugin_id=str(plugin_id), values={}),
        _blueprint_view=_blueprint_view,
        metadata={"source": "mcp", "host": "application_services"})


class McpAdapter(BaseAdapter):
    type = "mcp_tool"
    permission = "mcp.extend"

    def __init__(self, tool_registry: Any = None, resource_registry: Any = None,
                 *, narrow_context: Any = None) -> None:
        # 兼容 BaseAdapter(registry) 的单 registry 形态：默认作为 tool registry
        super().__init__(tool_registry)
        self.tool_registry = tool_registry
        self.resource_registry = resource_registry
        self.narrow_context = narrow_context or default_narrow_context

    def _plugin_context(self, host: Any, *, plugin_id: str, plugin_version: str,
                        approved_permissions: Sequence[str] = ()) -> Any:
        return self.narrow_context(plugin_id=plugin_id, plugin_version=plugin_version,
                                   approved_permissions=tuple(approved_permissions),
                                   host=host)

    # ------------------------------------------------------------------ tools
    def register_tool(self, *, plugin_id: str, plugin_version: str,
                      contribution: PluginContribution,
                      approved_permissions: Sequence[str] = ()) -> str:
        from novelforge.interfaces.mcp.contracts import ToolSpec

        metadata = dict(contribution.metadata or {})
        raw_name = str(metadata.get("name") or contribution.contribution_id)
        self.reject_reserved(plugin_id, raw_name)
        guard = getattr(self.tool_registry, "core_names", None)
        self.check_core_conflict(raw_name, core_ids=tuple(guard() if callable(guard)
                                                         else ()))
        name = self.namespaced(plugin_id, raw_name)
        schema = dict(metadata.get("input_schema") or {"type": "object",
                                                       "properties": {}})
        read_only = bool(metadata.get("read_only", False))
        spec = ToolSpec(
            name=name,
            description=str(metadata.get("description")
                            or f"plugin tool（{plugin_id}@{plugin_version}）"),
            input_schema=schema, output_schema={"type": "object"},
            version=int(contribution.version), read_only=read_only,
            mutation=not read_only,
            supports_dry_run=bool(metadata.get("dry_run", False)),
            permission="author",
            service=f"plugin:{plugin_id}",
            owner_type="plugin", owner_id=plugin_id)
        factory = contribution.factory
        if not callable(factory):
            raise PluginRegistrationError(
                "mcp_tool 贡献的 factory 必须可调用",
                details={"plugin_id": plugin_id, "tool": raw_name})

        def handler(context: Any, arguments: Mapping[str, Any]) -> Any:
            return factory(self._plugin_context(
                context, plugin_id=plugin_id, plugin_version=plugin_version,
                approved_permissions=approved_permissions), dict(arguments or {}))

        self.tool_registry.register(spec, handler)
        return name

    # --------------------------------------------------------------- resources
    def register_resource(self, *, plugin_id: str, plugin_version: str,
                          contribution: PluginContribution,
                          approved_permissions: Sequence[str] = ()) -> str:
        from novelforge.interfaces.mcp.contracts import ResourceSpec

        metadata = dict(contribution.metadata or {})
        raw_uri = str(metadata.get("uri") or contribution.contribution_id)
        from novelforge.interfaces.mcp.uri import (plugin_resource_kind,
                                                   plugin_resource_uri)

        uri = plugin_resource_uri(plugin_id, raw_uri)
        factory = contribution.factory
        if not callable(factory):
            raise PluginRegistrationError(
                "mcp_resource 贡献的 factory 必须可调用",
                details={"plugin_id": plugin_id, "uri": raw_uri})
        spec = ResourceSpec(
            uri=uri, name=str(metadata.get("name") or raw_uri),
            description=str(metadata.get("description")
                            or f"plugin resource（{plugin_id}@{plugin_version}）"),
            mime_type=str(metadata.get("mime_type") or "application/json"),
            template=bool(metadata.get("template", False)),
            service=f"plugin:{plugin_id}",
            owner_type="plugin", owner_id=plugin_id)

        def handler(context: Any, target: Any) -> Any:
            from novelforge.interfaces.mcp.payloads import json_payload

            value = factory(self._plugin_context(
                context, plugin_id=plugin_id, plugin_version=plugin_version,
                approved_permissions=approved_permissions), target)
            if value is None:
                raise PluginRegistrationError(
                    f"plugin resource 返回空值：{uri}", plugin_id=plugin_id)
            if isinstance(value, (str, bytes)):
                return json_payload(target.uri, value if isinstance(value, str)
                                    else value.decode("utf-8", errors="replace"))
            return json_payload(target.uri, value)

        self.resource_registry.register(spec,
                                        kinds=(plugin_resource_kind(plugin_id),),
                                        handler=handler)
        return uri

    # ------------------------------------------------------------------ 通用
    def register(self, *, plugin_id: str, plugin_version: str,
                 contribution: PluginContribution,
                 approved_permissions: Sequence[str] = ()) -> str:
        if contribution.type == "mcp_resource":
            return self.register_resource(plugin_id=plugin_id,
                                          plugin_version=plugin_version,
                                          contribution=contribution,
                                          approved_permissions=approved_permissions)
        return self.register_tool(plugin_id=plugin_id,
                                  plugin_version=plugin_version,
                                  contribution=contribution,
                                  approved_permissions=approved_permissions)

    def unregister(self, *, plugin_id: str) -> int:
        removed = 0
        for registry in (self.tool_registry, self.resource_registry):
            if registry is not None and hasattr(registry, "unregister_owner"):
                removed += int(registry.unregister_owner(str(plugin_id)))
        return removed


__all__ = ["McpAdapter", "default_narrow_context"]
