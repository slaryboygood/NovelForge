"""V4-09 §64–§67、§85、§87：application.services 只暴露 PluginService 门面。"""

from __future__ import annotations

from pathlib import Path

import pytest

from novelforge.application.services import PluginService
from novelforge.plugins.manager import PluginManager

from plugins_support import (
    EXPORTER_PLUGIN,
    active_plugin,
    exporter_manifest,
    install,
    plugin_host,
)


def test_application_layer_exposes_only_the_facade(tmp_path: Path) -> None:
    import novelforge.application.services as services

    assert "PluginService" in services.__all__
    # PluginHost（composition root）不属于 application 层（见 V4_MODULE_BOUNDARIES §3.16）
    assert "PluginHost" not in services.__all__
    source = (Path(services.__file__).resolve().parent / "plugins.py").read_text(
        encoding="utf-8")
    assert "novelforge.interfaces" not in source
    assert "PluginManager" in source


def test_plugin_service_is_a_facade_over_the_manager(tmp_path: Path) -> None:
    host = plugin_host(tmp_path, manifests=[exporter_manifest(tmp_path)])
    service = host.service
    assert isinstance(service, PluginService)
    assert isinstance(service.manager, PluginManager)
    assert service.manager is host.manager


def test_plugin_service_read_only_contract(tmp_path: Path) -> None:
    """§87：UI / Agent 需要的字段（name / id / version / capability / status / error）。"""

    host = plugin_host(tmp_path, manifests=[exporter_manifest(tmp_path)])
    host.discover()
    rows = host.service.list_plugins()
    assert len(rows) == 1
    row = rows[0]
    for key in ("plugin_id", "name", "version", "description", "capabilities",
                "permissions", "status", "compatibility", "error_code",
                "approved_permissions", "active"):
        assert key in row
    assert host.service.get_plugin(EXPORTER_PLUGIN)["plugin_id"] == EXPORTER_PLUGIN
    assert host.service.status()["plugins"] == 1
    assert host.service.contributions() == []
    assert host.service.audit()                     # discover 至少有一条审计


def test_permission_model_is_exposed_honestly() -> None:
    from novelforge.plugins import PluginManager

    service = PluginService(PluginManager("."))
    model = service.permission_model()
    assert model["trust_model"] == "trusted_in_process"
    assert "sandbox" in model["note"]
    assert set(model["permissions"]) >= {"delivery.export", "quality.evaluate",
                                         "mcp.extend", "ai.invoke"}


def test_plugin_service_drives_lifecycle(tmp_path: Path) -> None:
    host = plugin_host(tmp_path, manifests=[exporter_manifest(tmp_path)])
    host.service.discover()
    assert host.service.approve(EXPORTER_PLUGIN)["status"] == "approved"
    assert host.service.enable(EXPORTER_PLUGIN)["status"] == "active"
    assert [row["plugin_id"] for row in host.service.contributions(
        type="exporter")] == [EXPORTER_PLUGIN]
    assert host.service.disable(EXPORTER_PLUGIN, reason="test")["status"] == "disabled"


def test_enable_and_disable_are_operator_operations_not_remote(tmp_path: Path) -> None:
    """§65–§67：enable / disable 属于 operator 操作，不通过远程安装自动化。"""

    host = plugin_host(tmp_path, manifests=[exporter_manifest(tmp_path)])
    host.discover()
    active_plugin(host, EXPORTER_PLUGIN)
    events = {row["event"] for row in host.service.audit()}
    assert {"discovered", "approved", "enabled", "loaded"} <= events
    # 没有 install / download 之类事件
    assert not {event for event in events
                if any(token in event for token in ("install", "download", "fetch"))}


def test_unknown_plugin_raises_not_found(tmp_path: Path) -> None:
    from novelforge.plugins import PluginNotFoundError

    host = plugin_host(tmp_path, manifests=[exporter_manifest(tmp_path)])
    with pytest.raises(PluginNotFoundError):
        host.service.get_plugin("com.example.absent")
    with pytest.raises(PluginNotFoundError):
        host.service.approve("com.example.absent")
    with pytest.raises(PluginNotFoundError):
        install(host, "com.example.absent")
