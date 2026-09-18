"""V4-08 §15、§29–§31、§44–§46、§51–§54：MCP 契约、注册表、序列化、错误码。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from novelforge.interfaces.mcp import (
    DEFAULT_MIME,
    MCP_ERROR_CODES,
    MCP_INTERFACE_VERSION,
    MCP_SERVER_NAME,
    MCPInvalidArgument,
    MCPToolNotFound,
    ToolResult,
    ToolSpec,
    assert_no_secrets,
    mime_for,
    parse_uri,
    resource_table,
    sanitize,
    tool_table,
)
from novelforge.interfaces.mcp.errors import MCPResourceNotFound
from novelforge.interfaces.mcp.uri import (
    MAX_LIMIT,
    decode_cursor,
    encode_cursor,
    paginate,
)

from mcp_support import mcp_stack


def test_interface_version_is_independent() -> None:
    assert MCP_INTERFACE_VERSION == 1
    assert MCP_SERVER_NAME == "novelforge"
    assert MCP_INTERFACE_VERSION != 0
    assert "MCP_INVALID_ARGUMENT" in MCP_ERROR_CODES
    assert "MCP_REVISION_CONFLICT" in MCP_ERROR_CODES
    assert "MCP_DELIVERY_BLOCKED" in MCP_ERROR_CODES
    assert len(MCP_ERROR_CODES) == len(set(MCP_ERROR_CODES))


def test_tool_spec_rejects_mutation_without_novel_id() -> None:
    with pytest.raises(ValueError):
        ToolSpec(name="bad", description="x",
                 input_schema={"type": "object", "properties": {}},
                 output_schema={}, mutation=True)
    spec = ToolSpec(name="ok", description="x",
                    input_schema={"type": "object",
                                  "properties": {"novel_id": {"type": "string"}}},
                    output_schema={}, mutation=True)
    assert spec.as_dict()["service"] == ""
    with pytest.raises(ValueError):
        ToolSpec(name="both", description="x",
                 input_schema={"type": "object",
                               "properties": {"novel_id": {}}},
                 output_schema={}, read_only=True, mutation=True)


def test_envelope_shape() -> None:
    envelope = ToolResult(operation="evaluate_blueprint", novel_id="novel_alpha",
                          revision=3, result={"a": 1}, summary="ok").as_dict()
    assert set(envelope) >= {"ok", "operation", "request_id", "novel_id", "revision",
                            "revision_before", "dry_run", "result", "issues",
                            "warnings", "resources", "usage", "errors", "summary"}
    assert envelope["ok"] is True and envelope["request_id"].startswith("mcp_")
    failed = ToolResult(operation="x", ok=False,
                        errors=({"code": "MCP_INVALID_ARGUMENT", "message": "bad"},)
                        ).as_dict()
    assert failed["ok"] is False          # errors 非空 → ok 必须为 False


def test_tool_and_resource_tables_cover_metadata(tmp_path: Path) -> None:
    stack = mcp_stack(tmp_path)
    dispatcher = stack["dispatcher"]
    rows = tool_table(dispatcher.tool_specs())
    assert len(rows) >= 20
    assert any(row["dry_run"] for row in rows)
    assert any(row["read_only"] for row in rows)
    assert all("novel_id" in json.dumps(spec.input_schema)
               for spec in dispatcher.tool_specs())
    resources = resource_table(dispatcher.resource_specs())
    assert any(row["pagination"] for row in resources)
    assert all(row["mime"] for row in resources)


def test_sanitize_drops_secrets_and_redacts_paths() -> None:
    payload = {"ok": True, "api_key": "sk-123", "authorization": "Bearer x",
               "provider_config": {"base_url": "http://x"}, "note": "prompt 文本",
               "path_hint": "F:\\AI_小说\\硅基升维\\novel\\x.json",
               "nested": [{"secret": "s"}, {"safe": "C:/Users/me/x"}]}
    cleaned = sanitize(payload)
    assert "api_key" not in cleaned and "authorization" not in cleaned
    assert "provider_config" not in cleaned and "prompt" not in cleaned
    assert "F:\\AI_小说" not in json.dumps(cleaned, ensure_ascii=False)
    assert "[redacted]" in cleaned["path_hint"]
    assert cleaned["nested"][0] == {}
    assert sanitize(b"bytes") == "[redacted]"
    hits = assert_no_secrets({"token": "x", "path": "/home/user/secret.env"})
    assert any(hit.startswith("key:") for hit in hits)
    assert any(hit.startswith("path:") for hit in hits)
    assert assert_no_secrets({"fine": "value"}) == []


def test_mime_types_are_correct_not_all_text_plain() -> None:
    assert mime_for("json") == "application/json"
    assert mime_for("markdown") == "text/markdown"
    assert mime_for("docx").endswith("wordprocessingml.document")
    assert mime_for("nfpack") == "application/zip"
    assert mime_for("unknown") == DEFAULT_MIME


def test_uri_parsing_and_pagination() -> None:
    target = parse_uri("novelforge://novels/novel_alpha/blueprint"
                       "?mode=accepted&limit=5&cursor=" + encode_cursor(10))
    assert target.kind == "blueprint" and target.novel_id == "novel_alpha"
    assert target.mode == "accepted" and target.limit == 5 and target.cursor == 10
    assert decode_cursor(encode_cursor(0)) == 0
    assert decode_cursor("") == 0
    with pytest.raises(MCPInvalidArgument):
        parse_uri("novelforge://novels/n/blueprint?limit=99999")
    with pytest.raises(MCPInvalidArgument):
        parse_uri("novelforge://novels/n/blueprint?mode=whatever")
    with pytest.raises(MCPInvalidArgument):
        decode_cursor("!!!not-base64!!!")
    for uri in ("novelforge://", "novelforge://unknown/x", "http://x/y",
                "novelforge://novels/n/unknown", "novelforge://novels/n/blueprint/x"):
        with pytest.raises(MCPResourceNotFound):
            parse_uri(uri)
    page = paginate(list(range(25)), limit=MAX_LIMIT, cursor=0)
    assert page["count"] == 25 and page["has_more"] is False
    page = paginate(list(range(25)), limit=10, cursor=0)
    assert page["has_more"] is True and page["next_cursor"]
    assert paginate(list(range(25)), limit=10, cursor=page["offset"] + 10)["count"] == 10


def test_dispatcher_reports_unknown_tool_and_records_invocations(tmp_path: Path) -> None:
    stack = mcp_stack(tmp_path)
    dispatcher = stack["dispatcher"]
    envelope = dispatcher.invoke_tool("no_such_tool", {"novel_id": "novel_alpha"})
    assert envelope["ok"] is False
    assert envelope["errors"][0]["code"] == "MCP_TOOL_NOT_FOUND"
    assert envelope["errors"][0]["cause"] == "MCP_TOOL_NOT_FOUND"
    records = dispatcher.invocations()
    assert records and records[-1]["name"] == "no_such_tool"
    assert records[-1]["status"] == "error"
    assert "latency_ms" in records[-1]
    with pytest.raises(MCPToolNotFound):
        dispatcher.tools.get("no_such_tool")


def test_dispatcher_requires_explicit_novel_id(tmp_path: Path) -> None:
    stack = mcp_stack(tmp_path)
    envelope = stack["dispatcher"].invoke_tool("evaluate_blueprint", {})
    assert envelope["ok"] is False
    assert envelope["errors"][0]["code"] == "MCP_INVALID_ARGUMENT"
    envelope = stack["dispatcher"].invoke_tool("evaluate_blueprint",
                                               {"novel_id": ""})
    assert envelope["errors"][0]["code"] == "MCP_INVALID_ARGUMENT"
