"""V4-09 §12–§13、§81、§93：兼容性（加载之前判定，不兼容不执行）。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from novelforge.plugins import (
    PLUGIN_API_VERSION,
    PluginCompatibilityError,
    PluginManifest,
    PluginManifestError,
    check_compatibility,
    manifest_from_mapping,
)

from plugins_support import (
    EXPORTER_MODULE,
    EXPORTER_PLUGIN,
    manifest_payload,
    plugin_host,
    write_manifest,
)


def _manifest(**overrides) -> PluginManifest:
    payload = manifest_payload(EXPORTER_PLUGIN, module=EXPORTER_MODULE,
                               capabilities=("exporter",),
                               permissions=("delivery.export",))
    payload.update(overrides)
    return manifest_from_mapping(payload)


def test_same_and_older_api_versions_are_compatible() -> None:
    assert check_compatibility(_manifest(plugin_api_version=1),
                               host_api_version=1).ok
    assert check_compatibility(_manifest(plugin_api_version=1),
                               host_api_version=2).ok          # 旧插件仍可用
    result = check_compatibility(_manifest(plugin_api_version=1))
    assert result.as_dict()["plugin_api_version"] == 1
    assert result.as_dict()["host_api_version"] == PLUGIN_API_VERSION


def test_future_api_version_is_incompatible() -> None:
    result = check_compatibility(_manifest(plugin_api_version=2),
                                host_api_version=1)
    assert result.ok is False
    assert result.as_dict()["ok"] is False
    assert "API" in result.reason


def test_unsupported_capability_is_incompatible() -> None:
    result = check_compatibility(_manifest(capabilities=("mcp_tool",)),
                                supported_capabilities=("exporter",))
    assert result.ok is False
    assert result.details["unsupported"] == ["mcp_tool"]


def test_min_host_version_is_enforced() -> None:
    manifest = _manifest(host_compatibility={"min_host_version": "5.0"})
    assert check_compatibility(manifest, host_version="4.9").ok is False
    assert check_compatibility(manifest, host_version="5.1").ok is True
    # host_version 未提供时不臆测
    assert check_compatibility(manifest).ok is True


def test_invalid_version_is_manifest_error() -> None:
    with pytest.raises(PluginManifestError):
        _manifest(plugin_api_version=0)


def test_incompatible_plugin_is_never_approved_or_loaded(tmp_path: Path) -> None:
    import sys

    sys.modules.pop(EXPORTER_MODULE, None)
    path = write_manifest(tmp_path, EXPORTER_PLUGIN, module=EXPORTER_MODULE,
                          plugin_api_version=PLUGIN_API_VERSION + 1,
                          capabilities=("exporter",),
                          permissions=("delivery.export",))
    host = plugin_host(tmp_path, manifests=[path])
    rows = host.discover()
    assert rows[0]["status"] == "incompatible"
    assert rows[0]["compatibility"]["ok"] is False
    with pytest.raises(PluginCompatibilityError):
        host.service.approve(EXPORTER_PLUGIN)
    # 直接 enable 也必须被拒绝（§13 / §81），且不执行插件代码
    with pytest.raises(PluginCompatibilityError):
        host.service.enable(EXPORTER_PLUGIN)
    assert EXPORTER_MODULE not in sys.modules
    assert host.exporter_registry.formats() == ("docx", "json", "markdown", "nfpack")


def test_degraded_startup_when_enabled_plugin_becomes_incompatible(
        tmp_path: Path) -> None:
    """§81：已 enable 的插件升级后不兼容 → plugin failed，Core 仍可启动。"""

    path = write_manifest(tmp_path, EXPORTER_PLUGIN, module=EXPORTER_MODULE,
                          capabilities=("exporter",),
                          permissions=("delivery.export",))
    host = plugin_host(tmp_path, manifests=[path])
    host.discover()
    host.service.approve(EXPORTER_PLUGIN)
    host.service.enable(EXPORTER_PLUGIN)
    assert host.exporter_registry.formats()[-1] == "tlist"

    # 宿主升级后插件要求更高 API → 重新发现为 incompatible
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["plugin_api_version"] = PLUGIN_API_VERSION + 1
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    restarted = plugin_host(tmp_path, manifests=[path])
    rows = restarted.load_enabled()
    assert rows[0]["status"] == "failed"
    assert rows[0]["error_code"] == "PLUGIN_INCOMPATIBLE"
    assert restarted.exporter_registry.formats() == ("docx", "json", "markdown",
                                                     "nfpack")
