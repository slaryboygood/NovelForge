"""PluginHost（V4-09 §7、§64、§81、§85）：插件平台与既有 registry 的 **composition root**。

```text
PluginManager.registry/contributions
        ↓  build_adapters（Host 侧适配器）
既有 registry（delivery.exporter / quality.evaluator / interfaces.mcp tool & resource）
        ↓
既有业务管线（DeliveryService / QualityService / MCP dispatcher）
```

位置说明（边界）：

```text
· application 层禁止依赖 interfaces（`V4_MODULE_BOUNDARIES.md` §3.2），
  而本模块必须同时接触 application 与 interfaces；因此 composition root 放在
  `plugins`（而非 `application.services`）。
· `application.services.plugins.PluginService` 只持有 PluginManager，不接触 interfaces。
· 既有业务模块（delivery / quality / interfaces.mcp）永远不 import concrete plugin。
```
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable, Sequence

from novelforge.application.services.facade import (
    ApplicationServices,
    application_services,
)
from novelforge.application.services.plugins import PluginService

from .adapters import build_adapters
from .contracts import PLUGIN_API_VERSION
from .errors import PluginError
from .manager import PluginManager


class PluginHost:
    """插件平台与既有 registry 的组合根（Core 不依赖 concrete plugin，§7）。"""

    def __init__(self, project_root: Path | str, *, novel_id: str = "",
                 host_version: str = "4.9",
                 plugin_api_version: int = PLUGIN_API_VERSION,
                 entry_points: Sequence[Any] | None = None,
                 manifest_paths: Iterable[Path | str] = (),
                 with_exporters: bool = True, with_quality: bool = True,
                 with_mcp: bool = True) -> None:
        from novelforge.delivery import build_default_registry as build_exporters
        from novelforge.interfaces.mcp.resources import build_resource_registry
        from novelforge.interfaces.mcp.tools import build_tool_registry
        from novelforge.quality import build_default_registry as build_evaluators

        self.project_root = Path(project_root)
        self.novel_id = str(novel_id)
        self.exporter_registry = build_exporters() if with_exporters else None
        self.evaluator_registry = build_evaluators() if with_quality else None
        self.mcp_tools = build_tool_registry() if with_mcp else None
        if with_mcp:
            self.mcp_resources = build_resource_registry(
                spec_source=lambda: {"tools": self.mcp_tools.specs(),
                                     "resources": self.mcp_resources.specs()})
        else:
            self.mcp_resources = None
        self.adapters = build_adapters(
            exporter_registry=self.exporter_registry,
            evaluator_registry=self.evaluator_registry,
            mcp_tool_registry=self.mcp_tools,
            mcp_resource_registry=self.mcp_resources)
        self.manager = PluginManager(
            self.project_root, adapters=self.adapters, host_version=host_version,
            plugin_api_version=plugin_api_version, novel_id=self.novel_id,
            entry_points=entry_points, manifest_paths=manifest_paths)
        self.service = PluginService(self.manager)

    # ------------------------------------------------------------------ 编排
    def discover(self) -> list[dict[str, Any]]:
        """发现插件（manifest only，不执行插件代码，§14）。"""

        return self.manager.discover()

    def load_enabled(self) -> list[dict[str, Any]]:
        """加载所有已 enable 的插件（宿主启动时调用；失败不影响 Core，§81）。"""

        enabled_ids = [plugin_id for plugin_id, row
                       in sorted(self.manager.enablement.records().items())
                       if row.get("enabled")]
        if not enabled_ids:
            return []
        if any(self.manager.registry.find(plugin_id) is None
               for plugin_id in enabled_ids):
            self.manager.discover()          # discovery 不执行插件代码（§14）
        rows: list[dict[str, Any]] = []
        for plugin_id in enabled_ids:
            record = self.manager.registry.find(plugin_id)
            if record is None:
                self.manager.audit.record("failed", plugin_id=plugin_id,
                                          status="failed",
                                          error_code="PLUGIN_NOT_FOUND",
                                          extra={"reason": "enabled 但未发现"})
                continue
            try:
                rows.append(self.manager.enable(plugin_id))
            except PluginError as exc:       # §19 / §81：降级启动，Core 继续
                record.status = "failed"
                record.enabled = True
                record.error_code = exc.code
                record.error_message = exc.message[:300]
                self.manager.audit.record("failed", plugin_id=plugin_id,
                                          version=record.manifest.version,
                                          status="failed", error_code=exc.code,
                                          extra={"message": exc.message[:200]})
                rows.append(record.as_dict())
        return rows

    def services(self, novel_id: str = "", **kwargs: Any) -> ApplicationServices:
        """构造已接入插件贡献的 ApplicationServices（同一 registry）。"""

        return application_services(
            self.project_root, novel_id or self.novel_id,
            exporter_registry=self.exporter_registry,
            evaluator_registry=self.evaluator_registry, **kwargs)

    def mcp_dispatcher(self, *, services_factory: Any = None,
                       gateway: Any = None, memory: Any = None,
                       **kwargs: Any) -> Any:
        """构造使用同一 registry 的 MCP dispatcher（插件工具 / 资源随之可见，§97）。"""

        from novelforge.interfaces.mcp.dispatch import MCPDispatcher

        if services_factory is None:
            def services_factory(root: Any, novel_id: str, **extra: Any) -> Any:
                return self.services(novel_id, gateway=gateway, memory=memory,
                                     **extra)
        return MCPDispatcher(self.project_root, services_factory=services_factory,
                             tools=self.mcp_tools, resources=self.mcp_resources,
                             **kwargs)

    def status(self) -> dict[str, Any]:
        return {**self.manager.status(),
                "exporters": (self.exporter_registry.formats()
                              if self.exporter_registry is not None else ()),
                "export_registry_owners": (self.exporter_registry.owners()
                                           if self.exporter_registry is not None else {}),
                "evaluator_owners": (self.evaluator_registry.owners()
                                     if self.evaluator_registry is not None else {}),
                "mcp_tool_count": (len(self.mcp_tools)
                                   if self.mcp_tools is not None else 0),
                "mcp_resource_count": (len(self.mcp_resources)
                                       if self.mcp_resources is not None else 0)}
__all__ = ["PluginHost", "PluginService"]
