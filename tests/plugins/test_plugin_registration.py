"""V4-09 §39–§42、§48–§49、§71–§75、§90：原子注册与 Core 不可覆盖。"""

from __future__ import annotations

from pathlib import Path

import pytest

from novelforge.delivery.exporters import ExporterRegistry, ExporterSpec
from novelforge.delivery import DeliveryFormatError
from novelforge.plugins import (
    PluginConflictError,
    PluginContribution,
    PluginRegistrationError,
)
from novelforge.plugins.adapters.exporter import ExporterAdapter
from novelforge.plugins.adapters.mcp import McpAdapter
from novelforge.interfaces.mcp.tools import build_tool_registry

from plugins_support import (
    CONFLICT_MODULE,
    EXPORTER_PLUGIN,
    PARTIAL_MODULE,
    install,
    plugin_host,
    write_manifest,
)

CORE_FORMATS = ("docx", "json", "markdown", "nfpack")


def _plugin_manifest(tmp_path: Path, module: str, plugin_id: str,
                     capabilities, permissions) -> Path:
    return write_manifest(tmp_path, plugin_id, module=module,
                          capabilities=capabilities, permissions=permissions)


def test_plugin_cannot_override_core_tool_or_exporter(tmp_path: Path) -> None:
    path = _plugin_manifest(tmp_path, CONFLICT_MODULE, "com.example.conflict",
                            ("mcp_tool", "exporter"), ("mcp.extend",
                                                       "delivery.export"))
    host = plugin_host(tmp_path, manifests=[path])
    host.discover()
    record = install(host, "com.example.conflict")
    assert record["status"] == "failed"
    assert record["error_code"] == "PLUGIN_REGISTRATION_CONFLICT"
    assert len(host.mcp_tools) == 23                # Core tool 未被覆盖
    assert host.exporter_registry.formats() == CORE_FORMATS
    assert host.exporter_registry.spec("json").owner_type == "core"


def test_duplicate_format_registration_is_rejected() -> None:
    registry = ExporterRegistry()
    spec = ExporterSpec(format="x", exporter_id="core.x", version=1,
                        mime_type="text/plain", extension="x")
    registry.register(spec, lambda ctx: b"")
    with pytest.raises(DeliveryFormatError):
        registry.register(ExporterSpec(format="x", exporter_id="plugin.x", version=1,
                                       mime_type="text/plain", extension="x",
                                       owner_type="plugin", owner_id="com.example.p"),
                          lambda ctx: b"")


def test_registration_is_atomic_when_second_contribution_conflicts(
        tmp_path: Path) -> None:
    """§49：第 1 个贡献合法、第 2 个冲突 → 整个插件注册回滚。"""

    path = _plugin_manifest(tmp_path, PARTIAL_MODULE, "com.example.partial",
                            ("exporter", "mcp_tool"),
                            ("delivery.export", "mcp.extend"))
    host = plugin_host(tmp_path, manifests=[path])
    host.discover()
    record = install(host, "com.example.partial")
    assert record["status"] == "failed"
    assert record["error_code"] == "PLUGIN_REGISTRATION_CONFLICT"
    assert host.exporter_registry.formats() == CORE_FORMATS   # 回滚，无半注册
    assert host.exporter_registry.owners() == {"novelforge": CORE_FORMATS}
    assert len(host.mcp_tools) == 23


def test_reserved_namespace_is_rejected_by_adapters() -> None:
    exporters = ExporterRegistry()
    adapter = ExporterAdapter(exporters)
    with pytest.raises(PluginConflictError):
        adapter.register(
            plugin_id=EXPORTER_PLUGIN, plugin_version="1.0.0",
            contribution=PluginContribution(
                type="exporter", contribution_id="core-export",
                factory=lambda ctx: b"", metadata={"format": "core.export"}))
    tools = build_tool_registry()
    mcp = McpAdapter(tools, None)
    with pytest.raises(PluginConflictError):
        mcp.register(plugin_id=EXPORTER_PLUGIN, plugin_version="1.0.0",
                     contribution=PluginContribution(
                         type="mcp_tool", contribution_id="x",
                         factory=lambda c, a: {},
                         metadata={"name": "novelforge.sneaky"}))


def test_contribution_requires_declared_metadata() -> None:
    exporters = ExporterRegistry()
    adapter = ExporterAdapter(exporters)
    with pytest.raises(PluginRegistrationError):
        adapter.register(plugin_id=EXPORTER_PLUGIN, plugin_version="1.0.0",
                         contribution=PluginContribution(
                             type="exporter", contribution_id="no-format",
                             factory=lambda ctx: b""))


def test_unregister_owner_never_removes_core(tmp_path: Path) -> None:
    from novelforge.plugins.host import PluginHost

    host = PluginHost(tmp_path, novel_id="alpha", entry_points=[])
    assert host.exporter_registry.unregister_owner("novelforge") == 0
    assert host.exporter_registry.formats() == CORE_FORMATS
    assert host.mcp_tools.unregister_owner("novelforge") == 0
    assert len(host.mcp_tools) == 23
    assert host.mcp_resources.unregister_owner("novelforge") == 0
    assert len(host.mcp_resources) == 13
