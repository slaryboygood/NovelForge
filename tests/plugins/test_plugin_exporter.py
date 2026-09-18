"""V4-09 §32–§34、§95：plugin exporter 仍走正常 Delivery 管线（golden test）。"""

from __future__ import annotations

from pathlib import Path

from novelforge.delivery import DeliveryRequest
from novelforge.delivery.manifest import sha256_hex
from novelforge.delivery.store import DeliveryStore

from plugins_support import (
    EXPORTER_PLUGIN,
    NOVEL_ID,
    active_plugin,
    delivery_stack,
    exporter_manifest,
    plugin_host,
)

CORE_FORMATS = ("docx", "json", "markdown", "nfpack")


def _host_with_exporter(tmp_path: Path):
    stack = delivery_stack(tmp_path)
    host = plugin_host(tmp_path, manifests=[exporter_manifest(tmp_path)])
    host.discover()
    record = active_plugin(host, EXPORTER_PLUGIN)
    services = host.services(NOVEL_ID, gateway=stack["gateway"],
                             memory=stack["memory"])
    return stack, host, record, services


def test_plugin_exporter_delivers_through_normal_pipeline(tmp_path: Path) -> None:
    stack, host, record, services = _host_with_exporter(tmp_path)
    assert record["registered_ids"] == [f"plugin.{EXPORTER_PLUGIN}.text-list"]
    assert host.exporter_registry.spec("tlist").owner_type == "plugin"
    assert host.exporter_registry.spec("tlist").owner_id == EXPORTER_PLUGIN

    selection = services.export.delivery_selection(
        selection_mode="accepted", profile="author", formats=("tlist",))
    result = services.export.delivery().deliver(DeliveryRequest(selection=selection))

    assert result.status == "delivered", result.notes
    artifact = next(row for row in result.artifacts if row.format == "tlist")
    # 插件身份记录在 artifact 上（可追溯 plugin_id + version）
    assert artifact.exporter_id == f"plugin.{EXPORTER_PLUGIN}.text-list"
    assert artifact.exporter_version == 1
    assert artifact.mime_type == "text/plain"
    assert artifact.filename == "blueprint.tlist"
    assert b"plugin export" in artifact.content
    assert artifact.checksum == sha256_hex(artifact.content)
    # 仍然经过 post-build 校验（§34）
    assert result.post_validation is not None and result.post_validation.ok
    manifest = result.manifest.as_dict()
    assert any(row["owner_type"] == "plugin" for row in manifest["exporters"])
    assert result.checksums[artifact.relative_path] == artifact.checksum

    # manifest.json 落盘 + 校验和一致（§95）
    store = DeliveryStore(tmp_path, NOVEL_ID)
    stored = store.get_manifest(result.snapshot_id)
    assert stored is not None
    assert stored["artifacts"][0]["checksum"] == artifact.checksum


def test_plugin_exporter_does_not_decide_selection(tmp_path: Path) -> None:
    """§33：exporter 只接收已选定内容，不参与 accepted / quality 决策。"""

    _stack, _host, _record, services = _host_with_exporter(tmp_path)
    view = services.export.blueprint_view()
    assert view["read_only"] is True
    assert view["artifacts"] == []
    selection = services.export.delivery_selection(
        selection_mode="accepted", profile="author", formats=("tlist",))
    assert selection.selection_mode == "accepted"
    assert selection.formats == ("tlist",)


def test_plugin_exporter_output_is_secret_scanned(tmp_path: Path) -> None:
    """§34：插件不能因为是插件就绕过 post-build secret scan。"""

    from plugins_support import write_manifest

    stack = delivery_stack(tmp_path)
    manifest = write_manifest(tmp_path, "com.example.leaky", module="secret_export_plugin",
                              capabilities=("exporter",),
                              permissions=("delivery.export",))
    host = plugin_host(tmp_path, manifests=[manifest])
    host.discover()
    active_plugin(host, "com.example.leaky")
    services = host.services(NOVEL_ID, gateway=stack["gateway"],
                             memory=stack["memory"])
    selection = services.export.delivery_selection(
        selection_mode="accepted", profile="author", formats=("leak",))
    result = services.export.delivery().deliver(DeliveryRequest(selection=selection))
    assert result.status == "blocked"
    assert any("敏感内容" in note for note in result.notes), result.notes
    assert result.artifacts == ()


def test_disable_removes_plugin_format(tmp_path: Path) -> None:
    import pytest

    from novelforge.delivery import DeliveryFormatError

    _stack, host, _record, services = _host_with_exporter(tmp_path)
    host.service.disable(EXPORTER_PLUGIN)
    assert host.exporter_registry.formats() == CORE_FORMATS
    # disable 后该 format 不再是合法选择（不会残留半可用能力）
    with pytest.raises(DeliveryFormatError):
        services.export.delivery_selection(
            selection_mode="accepted", profile="author", formats=("tlist",))
