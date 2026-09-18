"""V4-09 §22–§27、§52–§53、§92：permission governance 与升级重新批准。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from novelforge.plugins import (
    PLUGIN_PERMISSIONS,
    PluginManifestError,
    PluginNotApprovedError,
    PluginPermissionError,
    check_approval,
    declared_permissions,
    manifest_from_mapping,
    normalise_permissions,
    permission_diff,
    requires_reapproval,
)

from plugins_support import (
    EXPORTER_MODULE,
    EXPORTER_PLUGIN,
    PERMISSION_MODULE,
    exporter_manifest,
    install,
    plugin_host,
    write_manifest,
)

CORE_FORMATS = ("docx", "json", "markdown", "nfpack")


def _manifest(permissions=("delivery.export",), **overrides):
    payload = {"plugin_id": EXPORTER_PLUGIN, "name": "Example", "version": "1.0.0",
               "entry_point": f"{EXPORTER_MODULE}:register",
               "capabilities": ("exporter",), "permissions": list(permissions)}
    payload.update(overrides)
    return manifest_from_mapping(payload)


def test_normalise_permissions_validates_and_sorts() -> None:
    assert normalise_permissions(["mcp.extend", "delivery.export",
                                  "mcp.extend"]) == ("delivery.export", "mcp.extend")
    assert set(PLUGIN_PERMISSIONS) >= {"delivery.export", "quality.evaluate",
                                       "mcp.extend", "ai.invoke", "blueprint.read",
                                       "editor.mutate", "network.request",
                                       "plugin.state"}
    with pytest.raises(PluginPermissionError):
        normalise_permissions(["root"])


def test_manifest_permissions_are_declared_and_validated() -> None:
    manifest = _manifest()
    assert declared_permissions(manifest) == ("delivery.export",)
    with pytest.raises(PluginManifestError):
        _manifest(permissions=("delivery.export", "kernel.write"))


def test_check_approval_denies_escalation() -> None:
    manifest = _manifest(permissions=("delivery.export", "ai.invoke"))
    with pytest.raises(PluginPermissionError):
        check_approval(manifest, approved_permissions=("delivery.export",),
                       requested=("ai.invoke",))
    assert check_approval(manifest, approved_permissions=("ai.invoke",
                                                          "delivery.export")) == \
        ("ai.invoke", "delivery.export")


def test_requires_reapproval_reasons() -> None:
    needs, diff = requires_reapproval(
        approved_version="1.0.0", current_version="1.0.0",
        approved=("delivery.export",), declared=("delivery.export",),
        approved_digest="d1", current_digest="d1")
    assert needs is False and diff["reasons"] == []
    needs, diff = requires_reapproval(
        approved_version="1.0.0", current_version="2.0.0",
        approved=("delivery.export",), declared=("delivery.export", "ai.invoke"),
        approved_digest="d1", current_digest="d2")
    assert needs is True
    assert set(diff["reasons"]) == {"version_changed", "permission_added",
                                    "package_digest_changed"}
    assert diff["permission_diff"]["added"] == ["ai.invoke"]
    assert permission_diff(approved=("a",), declared=("a", "b"))["added"] == ["b"]


def test_permission_escalation_requires_new_approval(tmp_path: Path) -> None:
    path = exporter_manifest(tmp_path)
    host = plugin_host(tmp_path, manifests=[path])
    host.discover()
    install(host, EXPORTER_PLUGIN)

    # 插件升级：新增 ai.invoke（不得自动继承批准，§53）
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["version"] = "2.0.0"
    payload["permissions"] = ["delivery.export", "ai.invoke"]
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    restarted = plugin_host(tmp_path, manifests=[path])
    restarted.discover()
    with pytest.raises(PluginPermissionError):
        restarted.service.enable(EXPORTER_PLUGIN)
    # 重新批准后可以启用
    restarted.service.approve(EXPORTER_PLUGIN)
    assert restarted.service.enable(EXPORTER_PLUGIN)["status"] == "active"


def test_version_change_without_permission_change_still_needs_reapproval(
        tmp_path: Path) -> None:
    path = exporter_manifest(tmp_path)
    host = plugin_host(tmp_path, manifests=[path])
    host.discover()
    install(host, EXPORTER_PLUGIN)

    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["version"] = "1.0.1"
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    restarted = plugin_host(tmp_path, manifests=[path])
    restarted.discover()
    with pytest.raises(PluginNotApprovedError):
        restarted.service.enable(EXPORTER_PLUGIN)      # 内容变化 → 保守拒绝


def test_contribution_requiring_unapproved_permission_is_denied(
        tmp_path: Path) -> None:
    """§92：manifest 只批准 delivery.export，contribution 却要求 ai.invoke。"""

    path = write_manifest(tmp_path, EXPORTER_PLUGIN, module=PERMISSION_MODULE,
                          capabilities=("exporter",),
                          permissions=("delivery.export",))
    host = plugin_host(tmp_path, manifests=[path])
    host.discover()
    record = install(host, EXPORTER_PLUGIN)
    assert record["status"] == "failed"
    assert record["error_code"] == "PLUGIN_PERMISSION_DENIED"
    assert record["registered_ids"] == []
    assert host.exporter_registry.formats() == CORE_FORMATS


def test_plugin_context_capability_gate(tmp_path: Path) -> None:
    from novelforge.plugins import PluginConfig
    from novelforge.plugins.sdk.context import PluginContext
    from novelforge.plugins.state import PluginStateStore

    context = PluginContext(
        plugin_id=EXPORTER_PLUGIN, plugin_version="1.0.0",
        approved_permissions=("delivery.export", "plugin.state"),
        config=PluginConfig(plugin_id=EXPORTER_PLUGIN, values={"k": 1}),
        _state=PluginStateStore(tmp_path, "alpha", EXPORTER_PLUGIN))
    assert context.has_permission("delivery.export")
    assert context.get_config() == {"k": 1}
    assert context.load_state() == {}
    context.save_state({"cursor": 3})
    assert context.load_state() == {"cursor": 3}
    # 未批准的 capability 一律拒绝（§24）
    for call in (context.blueprint_view, context.ai):
        with pytest.raises(PluginPermissionError):
            call()
    with pytest.raises(PluginPermissionError):
        context.require("ai.invoke")
    assert context.as_dict()["approved_permissions"] == ["delivery.export",
                                                         "plugin.state"]
