"""Exporter 扩展（V4-09 §32–§34、§95）：插件注册 delivery exporter。

插件 exporter 只接收**已选定**的交付上下文（compiled blueprint / snapshot view），
不参与 selection / quality / review 决策（§33），并且仍然经过 Delivery 的
post-build validation / secret scan / path validation / manifest / checksum（§34）。
"""

from __future__ import annotations

from typing import Any, Mapping, Sequence

from ..contracts import PluginContribution
from ..errors import PluginRegistrationError
from . import BaseAdapter


class ExporterAdapter(BaseAdapter):
    type = "exporter"
    permission = "delivery.export"

    def core_ids(self) -> tuple[str, ...]:
        if hasattr(self.registry, "formats"):
            return tuple(str(value) for value in self.registry.formats())
        return ()

    def register(self, *, plugin_id: str, plugin_version: str,
                 contribution: PluginContribution,
                 approved_permissions: Sequence[str] = ()) -> str:
        metadata = dict(contribution.metadata or {})
        fmt = str(metadata.get("format") or "").strip()
        if not fmt:
            raise PluginRegistrationError(
                "exporter 贡献缺少 format",
                details={"plugin_id": plugin_id,
                         "contribution_id": contribution.contribution_id})
        self.reject_reserved(plugin_id, fmt)
        self.check_core_conflict(fmt, core_ids=self.core_ids())
        factory = contribution.factory
        if not callable(factory):
            raise PluginRegistrationError(
                "exporter 贡献的 factory 必须可调用",
                details={"plugin_id": plugin_id, "format": fmt})

        from novelforge.delivery.exporters import ExporterSpec

        exporter_id = self.namespaced(plugin_id, contribution.contribution_id)
        spec = ExporterSpec(
            format=fmt, exporter_id=exporter_id,
            version=int(contribution.version),
            mime_type=str(metadata.get("mime_type") or "application/octet-stream"),
            extension=str(metadata.get("extension") or fmt),
            profiles_supported=tuple(str(value) for value in
                                     (metadata.get("profiles_supported")
                                      or ("reader", "author", "machine", "audit"))),
            text=bool(metadata.get("text", False)),
            description=str(metadata.get("description")
                            or f"plugin exporter（{plugin_id}@{plugin_version}）"),
            owner_type="plugin", owner_id=plugin_id)
        self.registry.register(spec, factory)
        return exporter_id

    def unregister(self, *, plugin_id: str) -> int:
        return super().unregister(plugin_id=plugin_id)


__all__ = ["ExporterAdapter"]
