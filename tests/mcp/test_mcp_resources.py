"""V4-08 §10–§14、§45–§48、§64、§66–§67：MCP Resources（只读、分页、MIME、隔离）。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from novelforge.application.services import ExportService
from novelforge.interfaces.mcp import (
    MCPDispatcher,
    MCPResourceNotFound,
    artifact_uri,
    blueprint_uri,
    issues_uri,
    manifest_uri,
    node_uri,
    novel_uri,
    quality_uri,
    review_uri,
    revision_uri,
    scenes_uri,
)

from mcp_support import mcp_stack


def _json(payload) -> dict:
    return json.loads(payload.content if isinstance(payload.content, str)
                      else payload.content.decode("utf-8"))


def test_novel_summary_resource(tmp_path: Path) -> None:
    stack = mcp_stack(tmp_path)
    payload = stack["dispatcher"].read_resource(novel_uri("novel_alpha"))
    data = _json(payload)
    assert payload.mime_type == "application/json"
    assert data["novel_id"] == "novel_alpha"
    assert data["project_id"] == "novel_alpha"
    assert data["ai_available"] is True
    assert {"profile", "journey", "blueprint", "quality", "delivery"} <= set(data)


def test_blueprint_resource_is_ordered_pinned_and_paginated(tmp_path: Path) -> None:
    stack = mcp_stack(tmp_path)
    payload = stack["dispatcher"].read_resource(blueprint_uri("novel_alpha")
                                                + "?limit=3")
    data = _json(payload)
    assert data["count"] == 3 and data["has_more"] is True
    assert data["next_cursor"]
    assert data["ordering"][0] == "premise"
    second = _json(stack["dispatcher"].read_resource(
        blueprint_uri("novel_alpha") + f"?limit=3&cursor={data['next_cursor']}"))
    assert second["offset"] == 3
    assert {row["node_id"] for row in data["items"]} & \
        {row["node_id"] for row in second["items"]} == set()
    # 每个节点带 revision / status / quality / review_status（§13）
    row = data["items"][0]
    assert {"node_id", "node_type", "revision", "status", "quality",
            "review_status", "payload"} <= set(row)


def test_node_and_revision_resources(tmp_path: Path) -> None:
    stack = mcp_stack(tmp_path)
    dispatcher = stack["dispatcher"]
    node = _json(dispatcher.read_resource(node_uri("novel_alpha", "ch_001")))
    assert node["node"]["node_id"] == "ch_001"
    assert node["resources"][0] == node_uri("novel_alpha", "ch_001")
    revision = int(node["node"]["revision"])
    view = _json(dispatcher.read_resource(
        revision_uri("novel_alpha", "ch_001", revision)))
    assert view["revision"] == revision
    assert view["view"]["revision"] == revision
    assert view["editable_fields"] and "title" in view["editable_fields"]
    with pytest.raises(MCPResourceNotFound):
        dispatcher.read_resource(node_uri("novel_alpha", "ch_999"))
    with pytest.raises(MCPResourceNotFound):
        dispatcher.read_resource(revision_uri("novel_alpha", "ch_001", 99))


def test_scenes_resource_uses_visible_fields(tmp_path: Path) -> None:
    stack = mcp_stack(tmp_path)
    payload = stack["dispatcher"].read_resource(scenes_uri("novel_alpha"))
    data = _json(payload)
    assert data["items"] and all("payload" in row for row in data["items"])
    for row in data["items"]:
        assert "chapter_id" not in row["payload"]      # 结构字段不外显
        assert "scene_purpose" in row["payload"] or row["payload"]


def test_quality_and_issue_resources(tmp_path: Path) -> None:
    stack = mcp_stack(tmp_path, clean=False, repairable=False)
    dispatcher = stack["dispatcher"]
    stack["quality"].evaluate()
    summary = _json(dispatcher.read_resource(quality_uri("novel_alpha")))
    assert summary["stats"]["issues"] >= 1
    assert summary["issues"]
    issues = _json(dispatcher.read_resource(issues_uri("novel_alpha") + "?limit=2"))
    assert issues["count"] <= 2 and issues["total"] >= 1
    row = issues["items"][0]
    assert {"issue_id", "code", "gate", "severity", "scope", "evidence"} <= set(row)
    assert "historical" not in json.dumps(row)         # 资源不返回内部字段名


def test_review_resource_exposes_review_and_operations(tmp_path: Path) -> None:
    stack = mcp_stack(tmp_path)
    stack["service"].reject("ch_001", reason="不满意")
    payload = _json(stack["dispatcher"].read_resource(review_uri("novel_alpha")))
    assert payload["review_decisions"]
    assert payload["review_decisions"][0]["decision"] == "rejected"
    assert payload["operations"]
    assert "quality pass ≠ accepted" in payload["note"]


def test_delivery_resources_manifest_and_artifact_mime(tmp_path: Path) -> None:
    stack = mcp_stack(tmp_path)
    export = ExportService(tmp_path, "novel_alpha")
    selection = export.delivery_selection(formats=("json", "markdown", "nfpack"))
    result = export.deliver(selection)
    snapshot_id = result["snapshot_id"]
    dispatcher = stack["dispatcher"]
    snapshots = _json(dispatcher.read_resource(
        "novelforge://novels/novel_alpha/delivery"))
    assert snapshots["items"] and snapshots["items"][0]["snapshot_id"] == snapshot_id
    snapshot = _json(dispatcher.read_resource(
        f"novelforge://novels/novel_alpha/delivery/{snapshot_id}"))
    assert snapshot["snapshot"]["node_revisions"]
    manifest = _json(dispatcher.read_resource(
        manifest_uri("novel_alpha", snapshot_id)))
    assert manifest["manifest"]["artifacts"]
    by_format = {row["format"]: row for row in result["artifacts"]}
    json_artifact = by_format["json"]
    payload = dispatcher.read_resource(artifact_uri("novel_alpha", snapshot_id,
                                                   json_artifact["path"]))
    assert payload.mime_type == "application/json"
    assert payload.content.decode("utf-8").startswith("{")
    assert any(note.startswith("checksum:") for note in payload.notes)
    nfpack = by_format["nfpack"]
    binary = dispatcher.read_resource(artifact_uri("novel_alpha", snapshot_id,
                                                  nfpack["path"]))
    assert binary.mime_type == "application/zip"
    assert isinstance(binary.content, bytes)


def test_artifact_resource_rejects_unregistered_path(tmp_path: Path) -> None:
    """§67：不接受任意路径，只接受已登记 artifact。"""

    stack = mcp_stack(tmp_path)
    export = ExportService(tmp_path, "novel_alpha")
    result = export.deliver(export.delivery_selection(formats=("json",)))
    dispatcher = stack["dispatcher"]
    for path in ("../../../.env", "exports/../secret.json", "C:/Windows/win.ini"):
        with pytest.raises(MCPResourceNotFound):
            dispatcher.read_resource(artifact_uri("novel_alpha",
                                                  result["snapshot_id"], path))
    with pytest.raises(MCPResourceNotFound):
        dispatcher.read_resource(artifact_uri("novel_alpha", "DS_missing",
                                              "exports/blueprint.json"))


def test_resources_are_novel_isolated(tmp_path: Path) -> None:
    """§66：A 的资源请求读不到 B 的任何数据（node_id 相同）。"""

    from mcp_support import delivery_stack

    mcp_stack(tmp_path)
    delivery_stack(tmp_path, novel_id="novel_beta", clean=True)
    dispatcher = MCPDispatcher(tmp_path)
    from novelforge.application.services.facade import application_services

    dispatcher.services_factory = lambda root, novel_id, **kwargs: \
        application_services(root, novel_id)
    alpha = _json(dispatcher.read_resource(node_uri("novel_alpha", "ch_001")))
    beta = _json(dispatcher.read_resource(node_uri("novel_beta", "ch_001")))
    assert alpha["novel_id"] == "novel_alpha" and beta["novel_id"] == "novel_beta"
    assert "novel_beta" not in json.dumps(alpha)
    assert "novel_alpha" not in json.dumps(beta)
    assert json.dumps(alpha) != json.dumps(beta)      # 两本作品内容不同（title 不同）
    with pytest.raises(MCPResourceNotFound):
        dispatcher.read_resource(node_uri("novel_unknown", "ch_001"))


def test_interface_resource_lists_tools_and_resources(tmp_path: Path) -> None:
    stack = mcp_stack(tmp_path)
    payload = _json(stack["dispatcher"].read_resource("novelforge://interface"))
    assert payload["mcp_interface_version"] == 1
    assert payload["uri_scheme"] == "novelforge://"
    assert len(payload["tools"]) >= 20 and len(payload["resources"]) >= 10
    assert all("api_key" not in json.dumps(row) for row in payload["tools"])
