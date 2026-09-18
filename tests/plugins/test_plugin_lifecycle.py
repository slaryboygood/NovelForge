"""V4-09 §17–§19、§48–§50、§81、§94：生命周期与失败隔离。"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from novelforge.plugins import (
    PluginAuditLog,
    PluginNotApprovedError,
)

from plugins_support import (
    BROKEN_MODULE,
    EXPORTER_MODULE,
    EXPORTER_PLUGIN,
    LEAKY_MODULE,
    MCP_MODULE,
    MCP_PLUGIN,
    active_plugin,
    exporter_manifest,
    install,
    mcp_manifest,
    plugin_host,
    write_manifest,
)

CORE_FORMATS = ("docx", "json", "markdown", "nfpack")


def test_full_lifecycle_discover_approve_enable_disable(tmp_path: Path) -> None:
    host = plugin_host(tmp_path, manifests=[exporter_manifest(tmp_path)])
    rows = host.discover()
    assert rows[0]["status"] == "compatible"
    assert rows[0]["enabled"] is False and rows[0]["active"] is False

    approved = host.service.approve(EXPORTER_PLUGIN)
    assert approved["status"] == "approved"
    assert approved["approved_version"] == "1.0.0"
    assert approved["approved_permissions"] == ["delivery.export"]

    active = host.service.enable(EXPORTER_PLUGIN)
    assert active["status"] == "active"
    assert active["active"] is True and active["loaded"] is True
    assert active["registered_ids"] == [f"plugin.{EXPORTER_PLUGIN}.text-list"]
    assert "tlist" in host.exporter_registry.formats()

    disabled = host.service.disable(EXPORTER_PLUGIN)
    assert disabled["status"] == "disabled"
    assert disabled["enabled"] is False and disabled["active"] is False
    assert disabled["registered_ids"] == []
    assert host.exporter_registry.formats() == CORE_FORMATS   # Core 不受影响
    assert host.service.contributions() == []


def test_enable_requires_approval(tmp_path: Path) -> None:
    sys.modules.pop(EXPORTER_MODULE, None)
    host = plugin_host(tmp_path, manifests=[exporter_manifest(tmp_path)])
    host.discover()
    with pytest.raises(PluginNotApprovedError):
        host.service.enable(EXPORTER_PLUGIN)
    assert EXPORTER_MODULE not in sys.modules        # 未批准 → 绝不 import 插件代码
    assert host.exporter_registry.formats() == CORE_FORMATS


def test_load_before_discovery_is_not_possible(tmp_path: Path) -> None:
    from novelforge.plugins import PluginNotFoundError

    host = plugin_host(tmp_path, manifests=[exporter_manifest(tmp_path)])
    with pytest.raises(PluginNotFoundError):
        host.service.enable(EXPORTER_PLUGIN)


def test_failed_plugin_is_isolated_from_core_and_other_plugins(tmp_path: Path) -> None:
    """§19、§98：一个插件坏掉 → status=failed，Core 与其它插件继续。"""

    broken = write_manifest(tmp_path, "com.example.broken", module=LEAKY_MODULE,
                            capabilities=("exporter",),
                            permissions=("delivery.export",))
    host = plugin_host(tmp_path, manifests=[broken,
                                            exporter_manifest(tmp_path),
                                            mcp_manifest(tmp_path)])
    host.discover()
    failed = install(host, "com.example.broken")
    assert failed["status"] == "active"       # 加载成功（加载期不跑 exporter）
    # 运行期崩溃 → PluginResult 记录，不影响 Core / 其它插件
    result = host.manager.execute("com.example.broken", "leaky")
    assert result.ok is False
    assert result.error_code == "PLUGIN_EXECUTION_FAILED"
    active_plugin(host, EXPORTER_PLUGIN)
    active_plugin(host, MCP_PLUGIN)
    assert host.exporter_registry.formats() == ("docx", "json", "leaky", "markdown",
                                                "nfpack", "tlist")
    assert len(host.mcp_tools) == 24
    assert host.manager.status()["by_status"]["active"] == 3


def test_registration_failure_marks_failed_without_killing_host(tmp_path: Path) -> None:
    broken = write_manifest(tmp_path, "com.example.broken", module=BROKEN_MODULE,
                            capabilities=("exporter",),
                            permissions=("delivery.export",))
    host = plugin_host(tmp_path, manifests=[broken, exporter_manifest(tmp_path)])
    host.discover()
    failed = install(host, "com.example.broken")
    assert failed["status"] == "failed"
    assert failed["error_code"] == "PLUGIN_LOAD_FAILED"
    assert failed["registered_ids"] == []
    assert host.exporter_registry.formats() == CORE_FORMATS
    # 其它插件仍可正常启用（Core 继续）
    active_plugin(host, EXPORTER_PLUGIN)
    by_status = host.manager.status()["by_status"]
    assert by_status["failed"] == 1 and by_status["active"] == 1


def test_disable_unregisters_only_that_plugin(tmp_path: Path) -> None:
    host = plugin_host(tmp_path, manifests=[exporter_manifest(tmp_path),
                                            mcp_manifest(tmp_path)])
    host.discover()
    active_plugin(host, EXPORTER_PLUGIN)
    active_plugin(host, MCP_PLUGIN)
    assert host.exporter_registry.owners()[EXPORTER_PLUGIN] == ("tlist",)
    host.service.disable(EXPORTER_PLUGIN)
    assert host.exporter_registry.formats() == CORE_FORMATS
    # MCP 插件未被连带卸载
    assert f"plugin.{MCP_PLUGIN}.blueprint_stats" in host.mcp_tools.names()
    assert list(host.service.status()["active"]) == [MCP_PLUGIN]


def test_enabled_plugins_reload_after_restart(tmp_path: Path) -> None:
    manifests = [exporter_manifest(tmp_path), mcp_manifest(tmp_path)]
    host = plugin_host(tmp_path, manifests=manifests)
    host.discover()
    active_plugin(host, EXPORTER_PLUGIN)
    active_plugin(host, MCP_PLUGIN)
    host.service.disable(MCP_PLUGIN)

    restarted = plugin_host(tmp_path, manifests=manifests)
    rows = restarted.load_enabled()
    assert [row["plugin_id"] for row in rows] == [EXPORTER_PLUGIN]
    assert rows[0]["status"] == "active"
    assert restarted.exporter_registry.formats()[-1] == "tlist"
    assert len(restarted.mcp_tools) == 23           # disabled 的不会被启用


def test_audit_records_lifecycle_events(tmp_path: Path) -> None:
    host = plugin_host(tmp_path, manifests=[exporter_manifest(tmp_path)])
    host.discover()
    install(host, EXPORTER_PLUGIN)
    host.service.disable(EXPORTER_PLUGIN)
    events = [row["event"] for row in host.service.audit()]
    for expected in ("discovered", "approved", "enabled", "loaded", "disabled"):
        assert expected in events
    assert PluginAuditLog(tmp_path).records()
    assert host.manager.status()["enablement"][EXPORTER_PLUGIN]["enabled"] is False
