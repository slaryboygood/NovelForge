"""V4-09 §14–§16、§61–§62、§91、§93：discovery ≠ load（且不执行插件代码）。"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from novelforge.plugins import (
    PluginConflictError,
    PluginDescriptor,
    PluginManifest,
    PluginManifestError,
    PluginRegistry,
    discover_manifest_paths,
    manifest_from_json,
)
from novelforge.plugins.discovery import dedupe_descriptors, package_digest

from plugins_support import (
    EXPORTER_MODULE,
    EXPORTER_PLUGIN,
    MANIFEST_FILE_NAME,
    FakeDist,
    FakeEntryPoint,
    entry_point,
    exporter_manifest,
    manifest_payload,
    plugin_host,
    write_manifest,
)


def _payload(**overrides) -> dict:
    base = manifest_payload(EXPORTER_PLUGIN, module=EXPORTER_MODULE,
                            capabilities=("exporter",),
                            permissions=("delivery.export",))
    base.update(overrides)
    return base


# ------------------------------------------------------------------- manifest
def test_manifest_from_json_rejects_broken_payloads() -> None:
    with pytest.raises(PluginManifestError):
        manifest_from_json("{ not json")
    with pytest.raises(PluginManifestError):
        manifest_from_json("[1, 2, 3]")
    manifest = manifest_from_json(json.dumps(_payload()))
    assert manifest.plugin_id == EXPORTER_PLUGIN


def test_manifest_path_is_explicit_and_must_exist(tmp_path: Path) -> None:
    with pytest.raises(PluginManifestError):
        discover_manifest_paths([tmp_path / "missing.json"])
    path = exporter_manifest(tmp_path)
    descriptors = discover_manifest_paths([path])
    assert len(descriptors) == 1
    assert descriptors[0].source == "manifest_path"
    assert descriptors[0].locator == path.name          # 不泄漏本机绝对路径
    assert ":" not in descriptors[0].locator


def test_package_digest_detects_replaced_content() -> None:
    first = package_digest({"module": "a", "source": "print(1)"})
    assert first == package_digest({"module": "a", "source": "print(1)"})
    assert first != package_digest({"module": "a", "source": "print(2)"})


# ----------------------------------------------------------------- discovery
def test_discovery_does_not_execute_plugin_code(tmp_path: Path) -> None:
    sys.modules.pop(EXPORTER_MODULE, None)
    host = plugin_host(tmp_path, manifests=[exporter_manifest(tmp_path)])
    rows = host.discover()
    assert [row["plugin_id"] for row in rows] == [EXPORTER_PLUGIN]
    assert rows[0]["status"] == "compatible"
    # discovery 只读 manifest：插件模块**没有**被 import（§14）
    assert EXPORTER_MODULE not in sys.modules
    # 也没有注册任何贡献（registry 仍然只有 core）
    assert host.exporter_registry.formats() == ("docx", "json", "markdown", "nfpack")
    assert host.service.contributions() == []


def test_discovery_reads_distribution_metadata_only(tmp_path: Path) -> None:
    host = plugin_host(tmp_path, entries=[entry_point(EXPORTER_PLUGIN,
                                                      EXPORTER_MODULE)])
    rows = host.discover()
    assert rows[0]["source"] == "entry_point"
    assert EXPORTER_MODULE not in sys.modules          # 仍未执行插件代码
    assert rows[0]["manifest_digest"]


def test_entry_point_without_manifest_is_ignored(tmp_path: Path) -> None:
    class Broken:
        name = "com.example.nomanifest"
        value = "nope:register"

        class dist:  # noqa: N801 - 模拟 distribution metadata 读到空
            @staticmethod
            def read_text(_name: str) -> str | None:
                return None

    host = plugin_host(tmp_path, entries=[Broken()])
    assert host.discover() == []
    assert host.manager.registry.status()["plugins"] == 0


def test_entry_point_json_value_is_supported(tmp_path: Path) -> None:
    manifest_path = write_manifest(tmp_path, EXPORTER_PLUGIN,
                                   module=EXPORTER_MODULE,
                                   capabilities=("exporter",),
                                   permissions=("delivery.export",))
    entry = FakeEntryPoint(name=EXPORTER_PLUGIN, value=str(manifest_path),
                           dist=FakeDist())
    host = plugin_host(tmp_path / "root", entries=[entry])
    assert host.discover()[0]["plugin_id"] == EXPORTER_PLUGIN


def test_duplicate_distribution_metadata_is_deduped(tmp_path: Path) -> None:
    manifest = PluginManifest.from_dict(_payload())
    rows = [PluginDescriptor(manifest=manifest, source="entry_point", locator="a"),
            PluginDescriptor(manifest=manifest, source="entry_point", locator="b")]
    assert len(dedupe_descriptors(rows)) == 1
    entry_text = json.dumps(_payload())
    host = plugin_host(tmp_path, entries=[
        FakeEntryPoint(name=EXPORTER_PLUGIN, value="a:register",
                       dist=FakeDist(files={MANIFEST_FILE_NAME: entry_text})),
        FakeEntryPoint(name=EXPORTER_PLUGIN, value="b:register",
                       dist=FakeDist(files={MANIFEST_FILE_NAME: entry_text}))])
    assert len(host.discover()) == 1


def test_same_plugin_id_with_different_manifest_conflicts() -> None:
    registry = PluginRegistry()
    first = PluginManifest.from_dict(_payload(version="1.0.0"))
    second = PluginManifest.from_dict(_payload(version="2.0.0"))
    registry.add(PluginDescriptor(manifest=first))
    with pytest.raises(PluginConflictError):
        registry.add(PluginDescriptor(manifest=second))
    # 相同 manifest 重复发现是幂等的
    assert registry.add(PluginDescriptor(manifest=first)).plugin_id == EXPORTER_PLUGIN


# ------------------------------------------------------- 不扫描任意目录（§61）
def test_no_directory_scan_for_project_plugins(tmp_path: Path) -> None:
    plugins_dir = tmp_path / "plugins"
    plugins_dir.mkdir()
    (plugins_dir / "evil_plugin.py").write_text(
        "import sys\nsys.modules['EVIL_LOADED'] = True\nRAISED = 1 / 0\n",
        encoding="utf-8")
    host = plugin_host(tmp_path)          # 未提供 manifest / entry point
    assert host.discover() == []
    assert "evil_plugin" not in sys.modules
    assert "EVIL_LOADED" not in sys.modules
    assert host.manager.registry.status()["plugins"] == 0


# ------------------------------------------- import 不触发 discovery（§91）
def test_importing_plugins_never_discovers_or_touches_disk(tmp_path: Path,
                                                          monkeypatch) -> None:
    from importlib import metadata

    def boom(*_args, **_kwargs):
        raise AssertionError("import novelforge.plugins 不得扫描 distribution（§91）")

    monkeypatch.setattr(metadata, "entry_points", boom)
    for name in [key for key in list(sys.modules)
                 if key == "novelforge.plugins"
                 or key.startswith("novelforge.plugins.")]:
        monkeypatch.delitem(sys.modules, name, raising=False)
    import importlib

    module = importlib.import_module("novelforge.plugins")
    assert module.PLUGIN_API_VERSION == 1
    assert EXPORTER_MODULE not in sys.modules
    assert list(tmp_path.iterdir()) == []              # import 不写磁盘状态
