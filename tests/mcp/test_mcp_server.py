"""V4-08 §39–§41、§54、§62：官方 MCP SDK 适配层（in-process server + client session）
与 Golden MCP 全链路。"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from novelforge.application.services import ExportService
from novelforge.interfaces.mcp import (
    MCP_SDK_AVAILABLE,
    MCPToolFailure,
    create_dispatcher,
    create_mcp_server,
    node_uri,
    parse_uri,
)

from mcp_support import current_payload, envelope, error_code, mcp_stack, scripted


def _require_sdk() -> None:
    if not MCP_SDK_AVAILABLE:  # pragma: no cover - 环境缺依赖时跳过
        pytest.skip("未安装官方 MCP SDK（requirements.txt 记录了版本区间）")


def _services_factory(stack: dict):
    from novelforge.application.services.facade import application_services

    def factory(root: object, novel_id: str, **kwargs: object) -> object:
        return application_services(root, novel_id, gateway=stack["gateway"],
                                    memory=stack["memory"])
    return factory


def test_sdk_is_available_and_pinned() -> None:
    _require_sdk()
    from importlib.metadata import version

    import mcp.types as types

    assert version("mcp")  # 已安装官方 SDK（版本见 requirements.txt）
    assert "Tool" in dir(types)


def test_create_server_registers_tools_and_resources(tmp_path: Path) -> None:
    _require_sdk()
    stack = mcp_stack(tmp_path)
    server = create_mcp_server(tmp_path, services_factory=_services_factory(stack))
    dispatcher = server.dispatcher
    assert len(dispatcher.tools.names()) >= 20
    assert dispatcher.resources.static_specs()
    assert dispatcher.resources.template_specs()


def test_in_process_client_session_roundtrip(tmp_path: Path) -> None:
    """§62：in-process MCP —— 用真实 SDK server + client session 打通资源与 tool。"""

    _require_sdk()
    from mcp.shared.memory import create_connected_server_and_client_session

    stack = mcp_stack(tmp_path)
    server = create_mcp_server(tmp_path, services_factory=_services_factory(stack))

    async def run() -> dict:
        async with create_connected_server_and_client_session(server) as session:
            initialized = await session.initialize()
            tools = await session.list_tools()
            resources = await session.list_resources()
            templates = await session.list_resource_templates()
            resource = await session.read_resource(
                node_uri("novel_alpha", "ch_001"))
            called = await session.call_tool("validate_delivery",
                                             {"novel_id": "novel_alpha",
                                              "formats": ["json"]})
            failed = await session.call_tool("patch_blueprint_node",
                                             {"novel_id": "novel_alpha",
                                              "node_id": "ch_001",
                                              "expected_revision": 1,
                                              "changes": {"hook": "x"}})
            return {"server": initialized.serverInfo.name,
                    "tools": [tool.name for tool in tools.tools],
                    "resources": [row.uri for row in resources.resources],
                    "templates": [row.uriTemplate for row in templates.resourceTemplates],
                    "resource_uri": str(resource.contents[0].uri),
                    "resource_mime": resource.contents[0].mimeType,
                    "called_text": called.content[0].text,
                    "called_error": called.isError,
                    "failed_error": failed.isError,
                    "failed_text": failed.content[0].text}

    result = asyncio.run(run())
    assert result["server"] == "novelforge"
    assert {"generate_scene_plan", "patch_blueprint_node", "deliver_blueprint"} <= \
        set(result["tools"])
    assert "novelforge://interface" in [str(uri) for uri in result["resources"]]
    assert any(uri.startswith("novelforge://novels/{novel_id}")
               for uri in result["templates"])
    assert any("blueprint/nodes" in uri for uri in result["templates"])
    assert result["resource_uri"].endswith("/ch_001")
    assert result["resource_mime"] == "application/json"
    called = json.loads(result["called_text"])
    assert called["ok"] is True and called["operation"] == "validate_delivery"
    assert result["called_error"] is False
    assert result["failed_error"] is True                  # 冲突 → isError=True
    failed = json.loads(result["failed_text"])
    assert failed["ok"] is False
    assert failed["errors"][0]["code"] == "MCP_REVISION_CONFLICT"


def test_tool_failure_marker_keeps_envelope(monkeypatch: pytest.MonkeyPatch) -> None:
    failure = MCPToolFailure('{"ok": false}')
    assert failure.code == "MCP_TOOL_FAILED"


def test_missing_sdk_error_is_explicit(monkeypatch: pytest.MonkeyPatch,
                                      tmp_path: Path) -> None:
    from novelforge.interfaces.mcp import server as server_module

    monkeypatch.setattr(server_module, "MCP_SDK_AVAILABLE", False)
    with pytest.raises(server_module.MCPSdkUnavailable):
        server_module.create_mcp_server(tmp_path)


def test_server_does_not_touch_disk_on_creation(tmp_path: Path) -> None:
    """§41：import / 构造 server 不扫描项目、不打开作品。"""

    _require_sdk()
    stack = mcp_stack(tmp_path)
    before = sorted(path.name for path in tmp_path.iterdir())
    create_mcp_server(tmp_path, services_factory=_services_factory(stack))
    assert sorted(path.name for path in tmp_path.iterdir()) == before


def test_golden_mcp_workflow(tmp_path: Path) -> None:
    """§62 全链路：资源读取 → patch dry-run → patch → 冲突 → 评估 → plan →
    rewrite → accept → delivery validate / snapshot / artifact。"""

    stack = mcp_stack(tmp_path, clean=False, repairable=False)
    dispatcher = stack["dispatcher"]
    novel = "novel_alpha"
    assert dispatcher.read_resource(node_uri(novel, "sc_001_02")).mime_type == \
        "application/json"

    evaluated = envelope(dispatcher, "evaluate_blueprint", novel_id=novel)
    assert evaluated["issues"]
    plan = envelope(dispatcher, "plan_repair", novel_id=novel)
    assert plan["dry_run"] is True and plan["result"]["steps"]

    base = stack["repository"].current_revision("sc_001_02")
    dry = envelope(dispatcher, "patch_blueprint_node", novel_id=novel,
                   node_id="sc_001_02", expected_revision=base,
                   changes={"next_hook": "dry-run 钩子"}, dry_run=True)
    assert dry["ok"] is True and dry["dry_run"] is True
    assert stack["repository"].current_revision("sc_001_02") == base
    applied = envelope(dispatcher, "patch_blueprint_node", novel_id=novel,
                       node_id="sc_001_02", expected_revision=base,
                       changes={"next_hook": "真实钩子"})
    assert applied["ok"] is True and applied["revision"] == base + 1
    conflict = envelope(dispatcher, "patch_blueprint_node", novel_id=novel,
                        node_id="sc_001_02", expected_revision=base,
                        changes={"next_hook": "过期写入"})
    assert error_code(conflict) == "MCP_REVISION_CONFLICT"

    payload = current_payload(stack, "sc_001_02")
    scripted(stack, {**payload, "turn": "MCP 改写后的转折"})
    rewritten = envelope(dispatcher, "rewrite_blueprint_node", novel_id=novel,
                         node_id="sc_001_02",
                         expected_revision=base + 1, target_fields=["turn"],
                         instruction="把转折写得更具体")
    assert rewritten["ok"] is True, rewritten["errors"]
    assert rewritten["result"]["changed_fields"] == ["turn"]

    accepted = envelope(dispatcher, "accept_revision", novel_id=novel,
                        node_id="sc_001_02",
                        expected_revision=stack["repository"].current_revision(
                            "sc_001_02"))
    assert accepted["ok"] is True

    snapshot = envelope(dispatcher, "create_delivery_snapshot", novel_id=novel,
                        formats=["json", "nfpack"])
    assert snapshot["ok"] is True
    delivered = envelope(dispatcher, "deliver_blueprint", novel_id=novel,
                         formats=["json", "nfpack"])
    if delivered["ok"]:
        snapshot_id = delivered["result"]["snapshot_id"]
        assert delivered["result"]["llm_calls"] == 0
        manifest = dispatcher.read_resource(
            f"novelforge://novels/{novel}/delivery/{snapshot_id}/manifest")
        manifest_data = json.loads(manifest.content)
        artifact = manifest_data["manifest"]["artifacts"][0]
        artifact_payload = dispatcher.read_resource(
            f"novelforge://novels/{novel}/delivery/{snapshot_id}"
            f"/artifacts/{artifact['path']}")
        assert artifact_payload.size == artifact["size"]
    else:  # 质量未完全通过时，交付必须显式 blocked（不静默成功）
        assert error_code(delivered) == "MCP_DELIVERY_BLOCKED"
        assert delivered["errors"][0]["cause"] == "DELIVERY_VALIDATION_FAILED"


def test_dispatcher_is_shared_between_inprocess_and_server(tmp_path: Path) -> None:
    _require_sdk()
    stack = mcp_stack(tmp_path)
    dispatcher = create_dispatcher(tmp_path, services_factory=_services_factory(stack))
    server = create_mcp_server(tmp_path, dispatcher=dispatcher)
    assert server.dispatcher is dispatcher
    assert parse_uri("novelforge://interface").kind == "interface"


def test_delivery_through_mcp_is_revision_pinned(tmp_path: Path) -> None:
    """§35/§34：MCP mutation 仍受 expected_revision 与 snapshot pinning 约束。"""

    stack = mcp_stack(tmp_path)
    export = ExportService(tmp_path, "novel_alpha")
    selection = export.delivery_selection(formats=("json",))
    pinned = dict(export.create_snapshot(selection)["node_revisions"])
    base = stack["repository"].current_revision("ch_001")
    envelope(stack["dispatcher"], "patch_blueprint_node", novel_id="novel_alpha",
             node_id="ch_001", expected_revision=base,
             changes={"hook": "MCP 之后的修改"})
    delivered = envelope(stack["dispatcher"], "create_delivery_snapshot",
                         novel_id="novel_alpha", formats=("json",)
                         if False else ["json"])
    assert delivered["ok"] is True
    assert delivered["result"]["node_revisions"] == \
        {str(key): int(value) for key, value in pinned.items()}
