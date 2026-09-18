"""V4-09 §28–§30、§99：plugin state 隔离（按 plugin_id + novel_id）且不是 story truth。"""

from __future__ import annotations

from pathlib import Path

import pytest

from novelforge.persistence.paths import ARTIFACT_KINDS, plugin_state_dir
from novelforge.plugins import PluginError, PluginStateStore

from plugins_support import (
    EXPORTER_PLUGIN,
    MCP_PLUGIN,
    NOVEL_ID,
    OTHER_NOVEL_ID,
    active_plugin,
    exporter_manifest,
    plugin_host,
)


def test_state_path_is_namespaced_by_novel_and_plugin(tmp_path: Path) -> None:
    first = plugin_state_dir(tmp_path, NOVEL_ID, EXPORTER_PLUGIN)
    second = plugin_state_dir(tmp_path, NOVEL_ID, MCP_PLUGIN)
    other_novel = plugin_state_dir(tmp_path, OTHER_NOVEL_ID, EXPORTER_PLUGIN)
    assert first != second and first != other_novel and second != other_novel
    relative = first.relative_to(tmp_path.resolve())
    assert relative.parts[-3:] == ("state", NOVEL_ID, EXPORTER_PLUGIN)
    assert "plugin_state" in ARTIFACT_KINDS
    # 插件状态不在 blueprint / canon / quality / delivery 目录下（§30）
    assert not {"blueprint", "canon", "quality", "delivery"} & set(relative.parts)


def test_state_store_requires_explicit_ids(tmp_path: Path) -> None:
    with pytest.raises(PluginError):
        PluginStateStore(tmp_path, "", EXPORTER_PLUGIN)
    with pytest.raises(PluginError):
        PluginStateStore(tmp_path, NOVEL_ID, "")
    with pytest.raises((PluginError, Exception)):
        plugin_state_dir(tmp_path, NOVEL_ID, "")


def test_plugin_cannot_read_other_plugin_or_novel_state(tmp_path: Path) -> None:
    """§29：Plugin A 不能通过 Host API 读到 Plugin B / 其他作品的 state。"""

    a = PluginStateStore(tmp_path, NOVEL_ID, EXPORTER_PLUGIN)
    b = PluginStateStore(tmp_path, NOVEL_ID, MCP_PLUGIN)
    other_novel = PluginStateStore(tmp_path, OTHER_NOVEL_ID, EXPORTER_PLUGIN)
    a.save({"cursor": "A"})
    assert a.load()["values"] == {"cursor": "A"}
    assert b.load() == {}                      # 不同插件互不可见
    assert other_novel.load() == {}            # 不同作品互不可见
    b.update({"cursor": "B"})
    assert a.load()["values"] == {"cursor": "A"}   # 不被覆盖
    assert a.as_dict()["plugin_id"] == EXPORTER_PLUGIN
    assert a.as_dict()["novel_id"] == NOVEL_ID


def test_context_exposes_only_its_own_state(tmp_path: Path) -> None:
    host = plugin_host(tmp_path, manifests=[exporter_manifest(tmp_path)])
    host.discover()
    active_plugin(host, EXPORTER_PLUGIN)
    context = host.manager.context(EXPORTER_PLUGIN)
    assert context is not None
    context._state.save({"k": 1})              # type: ignore[union-attr]
    assert PluginStateStore(tmp_path, NOVEL_ID, EXPORTER_PLUGIN).load()["values"] == \
        {"k": 1}
    assert PluginStateStore(tmp_path, NOVEL_ID, MCP_PLUGIN).load() == {}
    # disable 后 Host 不再保留该插件的上下文
    host.service.disable(EXPORTER_PLUGIN)
    assert host.manager.context(EXPORTER_PLUGIN) is None


def test_state_is_not_story_truth(tmp_path: Path) -> None:
    """§30：plugin state 只是 cache / settings，不进 Blueprint / Canon / Quality。"""

    store = PluginStateStore(tmp_path, NOVEL_ID, EXPORTER_PLUGIN)
    store.save({"last_export": "tlist"})
    payload = store.load()
    assert set(payload) == {"plugin_id", "novel_id", "updated_at", "values"}
    blueprint_dir = tmp_path / "novel" / "authoring" / "story_engine" / "blueprint"
    assert not blueprint_dir.exists()
    # 冷启动后仍可读回（Host 控制路径，插件拿不到 project_root）
    assert PluginStateStore(tmp_path, NOVEL_ID, EXPORTER_PLUGIN).load()["values"] == \
        {"last_export": "tlist"}
