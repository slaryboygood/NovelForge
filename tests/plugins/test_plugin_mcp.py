"""V4-09 §38–§42、§77、§97：MCP tool / resource 扩展（namespaced，不覆盖 Core）。"""

from __future__ import annotations

from pathlib import Path

import pytest

from novelforge.interfaces.mcp.errors import MCPResourceNotFound
from novelforge.interfaces.mcp.uri import parse_uri

from plugins_support import (
    MCP_PLUGIN,
    NOVEL_ID,
    active_plugin,
    delivery_stack,
    mcp_manifest,
    plugin_host,
)

TOOL = f"plugin.{MCP_PLUGIN}.blueprint_stats"
RESOURCE_URI = f"novelforge://plugins/{MCP_PLUGIN}/manifest"


def _host_with_mcp(tmp_path: Path):
    stack = delivery_stack(tmp_path)
    host = plugin_host(tmp_path, manifests=[mcp_manifest(tmp_path)])
    host.discover()
    record = active_plugin(host, MCP_PLUGIN)
    dispatcher = host.mcp_dispatcher(gateway=stack["gateway"],
                                     memory=stack["memory"])
    return stack, host, record, dispatcher


def test_plugin_tool_and_resource_are_namespaced(tmp_path: Path) -> None:
    _stack, host, record, dispatcher = _host_with_mcp(tmp_path)
    assert set(record["registered_ids"]) == {TOOL, RESOURCE_URI}
    names = dispatcher.tools.names()
    assert TOOL in names and len(names) == 24                 # 23 core + 1 plugin
    spec = dispatcher.tools.get(TOOL).spec
    assert spec.owner_type == "plugin" and spec.owner_id == MCP_PLUGIN
    assert spec.read_only is True
    # Core tool 名称未被占用（插件拿不到 generate_scene_plan 等名字）
    assert dispatcher.tools.get("generate_scene_plan").spec.owner_type == "core"
    assert set(dispatcher.tools.core_names()) == set(host.mcp_tools.core_names())
    assert len(dispatcher.tools.core_names()) == 23
    assert RESOURCE_URI in [row.uri for row in dispatcher.resources.specs()]
    # 13 core resources + 1 plugin resource（core 的 13 = 1 static + 12 template）
    assert len(dispatcher.resources) == 14
    assert len(dispatcher.resources.template_specs()) == 12
    assert len(dispatcher.resources.static_specs()) == 2


def test_plugin_tool_invocation_uses_narrow_context(tmp_path: Path) -> None:
    stack, _host, _record, dispatcher = _host_with_mcp(tmp_path)
    envelope = dispatcher.invoke_tool(TOOL, {"novel_id": NOVEL_ID})
    assert envelope["ok"] is True, envelope
    assert envelope["result"]["node_count"] > 0
    assert envelope["tool_version"] == 1
    # 插件看到的是 PluginContext（窄上下文），不是 ApplicationServices
    from novelforge.plugins.sdk.context import PluginContext

    services = dispatcher.services_for(NOVEL_ID)
    assert isinstance(services.blueprint, object) and hasattr(services, "editor")
    assert not isinstance(services, PluginContext)


def test_plugin_resource_is_readable_and_namespaced(tmp_path: Path) -> None:
    _stack, _host, _record, dispatcher = _host_with_mcp(tmp_path)
    target = parse_uri(RESOURCE_URI)
    assert target.kind == f"plugin_resource:{MCP_PLUGIN}"
    assert target.plugin_id == MCP_PLUGIN and target.resource_path == "manifest"
    payload = dispatcher.read_resource(RESOURCE_URI)
    assert payload.mime_type == "application/json"
    assert MCP_PLUGIN in payload.content


def test_core_uris_still_parse(tmp_path: Path) -> None:
    _stack, _host, _record, _dispatcher = _host_with_mcp(tmp_path)
    for uri in ("novelforge://interface",
                f"novelforge://novels/{NOVEL_ID}",
                f"novelforge://novels/{NOVEL_ID}/blueprint",
                f"novelforge://novels/{NOVEL_ID}/quality"):
        assert parse_uri(uri).kind != ""


def test_disable_removes_plugin_tool_and_resource(tmp_path: Path) -> None:
    _stack, host, _record, dispatcher = _host_with_mcp(tmp_path)
    host.service.disable(MCP_PLUGIN)
    assert TOOL not in host.mcp_tools.names()
    assert len(host.mcp_tools) == 23
    assert len(host.mcp_resources) == 13
    assert RESOURCE_URI not in [row.uri for row in host.mcp_resources.specs()]
    # 新的 lookup 不再返回插件贡献（§74）
    with pytest.raises(Exception):
        dispatcher.tools.get(TOOL)
    with pytest.raises(MCPResourceNotFound):
        dispatcher.read_resource(RESOURCE_URI)


def test_unknown_plugin_uri_is_not_found(tmp_path: Path) -> None:
    _stack, _host, _record, dispatcher = _host_with_mcp(tmp_path)
    with pytest.raises(MCPResourceNotFound):
        dispatcher.read_resource("novelforge://plugins/com.example.absent/x")
    with pytest.raises(MCPResourceNotFound):
        parse_uri("novelforge://plugins/only-plugin-id")
