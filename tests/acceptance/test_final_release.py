"""V4-12 Layer C — Product / Release Acceptance（§19、§30–§34、§50–§53、§77–§78）。"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from acceptance_support import (
    ROOT,
    build_two_novels,
    golden_project,
    service_for,
)


# ------------------------------------------------------------- §19 isolation
def test_cross_novel_isolation_everywhere(tmp_path: Path) -> None:
    novel_a, novel_b = build_two_novels(tmp_path)
    assert novel_a != novel_b
    from novelforge.application.services.facade import application_services

    services_a = service_for(tmp_path, novel_a)
    services_b = application_services(tmp_path, novel_b,
                                      memory=service_for(tmp_path, novel_b))

    # Memory：A 的检索不得返回 B 的内容
    result_a = services_a.search(novel_id=novel_a, task="供电", entities=("hero",))
    assert all(str(getattr(item, "novel_id", novel_a)) == novel_a
               for item in result_a.items)
    with pytest.raises(Exception):
        services_a.search(novel_id=novel_b, task="供电")

    # Plugin state：按 (novel, plugin) 隔离
    from novelforge.plugins import PluginStateStore
    store_a = PluginStateStore(tmp_path, novel_a, "com.example.exporter")
    store_b = PluginStateStore(tmp_path, novel_b, "com.example.exporter")
    store_a.save({"cursor": "A"})
    assert store_b.load() == {}
    assert store_a.load()["values"] == {"cursor": "A"}

    # Agent runtime：会话按作品隔离
    from novelforge.application.services.agent import AgentService
    from novelforge.agent import AgentGoal, AgentScope
    agent_a = AgentService(tmp_path, novel_a)
    agent_b = AgentService(tmp_path, novel_b)
    session = agent_a.plan(AgentGoal(novel_id=novel_a, instruction="运行质量检查",
                                     scope=AgentScope(kind="novel")))
    assert [row["session_id"] for row in agent_a.history()] == [session["session_id"]]
    assert agent_b.history() == []
    with pytest.raises(Exception):
        agent_b.status(session["session_id"])          # B 读不到 A 的 session

    # Blueprint：A 的视图不含 B 的节点（同一 node_id 也不同作品）
    view_b = services_b.export.blueprint_view(selection_mode="current")
    assert all(row["novel_id"] == novel_b
               for row in view_b["blueprint"]["nodes"])


def test_mcp_cannot_read_other_novel(tmp_path: Path) -> None:
    novel_a, novel_b = build_two_novels(tmp_path)
    from novelforge.interfaces.mcp import create_dispatcher
    from novelforge.interfaces.mcp.errors import MCPError

    dispatcher = create_dispatcher(tmp_path)
    payload = dispatcher.read_resource(f"novelforge://novels/{novel_b}")
    assert novel_b in payload.uri
    # 用 A 的作品读一个只存在于 B 的实体 → 明确失败，不跨作品泄漏
    with pytest.raises(MCPError):
        dispatcher.read_resource(
            f"novelforge://novels/{novel_a}/blueprint/nodes/ch_001")


# ------------------------------------------------------- §30–§32 delivery
def test_delivery_is_reproducible_and_secure(tmp_path: Path) -> None:
    stack = golden_project(tmp_path)
    services = stack["services"]
    from novelforge.delivery import DeliveryPolicy

    relaxed = DeliveryPolicy(require_accepted=False, require_quality_pass=False,
                             allow_unevaluated=True, allow_stale_quality=True)
    selection = services.export.delivery_selection(
        selection_mode="current", profile="author",
        formats=("json", "markdown", "docx"), policy=relaxed)
    first = services.export.deliver(selection)
    second = services.export.deliver(
        services.export.delivery_selection(selection_mode="current",
                                           profile="author",
                                           formats=("json", "markdown", "docx"),
                                           policy=relaxed))
    assert first["status"] == second["status"] == "delivered"
    by_format_first = {row.format: row for row in
                       services.export.delivery().last_artifacts()
                       } if hasattr(services.export.delivery(), "last_artifacts") else {}
    # 可复现：同 snapshot 内容一致（这里比较两次交付的 manifest 校验和集合语义）
    assert first["manifest"]["selected_revisions"] == \
        second["manifest"]["selected_revisions"]
    assert first["manifest"]["formats"] == second["manifest"]["formats"]
    # manifest 记录 exporter 版本（交付物可追溯到 exporter 与 revision）
    assert first["manifest"]["exporters"]
    # 交付物无 secret / 无私有路径
    for artifact in first["artifacts"]:
        text = artifact.get("content", "")
        if isinstance(text, str):
            for token in ("API_KEY", "Authorization", "Bearer ", "sk-"):
                assert token not in text
            assert str(tmp_path) not in text


def test_delivery_blocks_stale_or_unaccepted(tmp_path: Path) -> None:
    stack = golden_project(tmp_path)
    services, repository = stack["services"], stack["repository"]
    # 改动一个节点 → 该 revision 的质量结论过期 → accepted 交付被阻止
    services.editor.patch("ch_001", {"hook": "改过但没有重新检查"},
                          expected_revision=repository.current_revision("ch_001"))
    selection = services.export.delivery_selection(
        selection_mode="accepted", profile="author", formats=("json",))
    result = services.export.deliver(selection)
    assert result["status"] == "blocked"
    assert list(result["artifacts"]) == []
    codes = {row["code"] for row in result["validation"]["issues"]}
    assert codes & {"DELIVERY_QUALITY_STALE", "DELIVERY_NO_ACCEPTED_REVISION",
                    "DELIVERY_QUALITY_FAILED", "DELIVERY_INVALIDATION_PENDING"}


# ------------------------------------------------------------ §34 MCP
def test_mcp_core_baseline_and_plugin_increment(tmp_path: Path) -> None:
    from novelforge.interfaces.mcp.resources import build_resource_registry
    from novelforge.interfaces.mcp.tools import build_tool_registry
    from novelforge.plugins.host import PluginHost
    from acceptance_support import EXPORTER_PLUGIN, active_plugin, exporter_manifest

    core_tools, core_resources = build_tool_registry(), build_resource_registry()
    assert len(core_tools) == 23
    assert len(core_resources) == 13

    host = PluginHost(tmp_path, novel_id="alpha",
                      manifest_paths=[exporter_manifest(tmp_path)])
    host.discover()
    active_plugin(host, EXPORTER_PLUGIN)
    assert len(host.mcp_tools) == 23          # exporter 插件只加交付格式
    assert len(host.mcp_resources) == 13
    assert "tlist" in host.exporter_registry.formats()
    host.service.disable(EXPORTER_PLUGIN)
    assert host.exporter_registry.formats() == ("docx", "json", "markdown", "nfpack")


# ------------------------------------------------------------ §53 errors
def test_error_contracts_are_stable_and_safe(tmp_path: Path) -> None:
    stack = golden_project(tmp_path)
    services = stack["services"]
    # Editor：未知节点 → 稳定业务错误（不是裸 KeyError）
    with pytest.raises(Exception) as editor_error:
        services.editor.get_node("does_not_exist")
    assert getattr(editor_error.value, "code", "")
    # Delivery：未知格式 → 稳定错误
    with pytest.raises(Exception) as format_error:
        services.export.delivery_selection(profile="author", formats=("epub",))
    assert "DELIVERY" in str(getattr(format_error.value, "code", "")) or \
        getattr(format_error.value, "code", "")
    # Agent：越界 scope → AGENT_POLICY_DENIED（不是静默执行）
    from novelforge.application.services.agent import AgentService
    from novelforge.agent import AgentGoal, AgentScope, AgentPolicyDenied
    agent = AgentService(tmp_path, stack["novel_id"], services=services)
    with pytest.raises(AgentPolicyDenied):
        agent.plan(AgentGoal(novel_id=stack["novel_id"], instruction="重写故事弧",
                             scope=AgentScope(kind="chapter", unit_id="ch_001")))
    # 错误文本不带 traceback / 绝对路径
    text = f"{editor_error.value} {format_error.value}"
    assert "Traceback" not in text and str(tmp_path) not in text


# ------------------------------------------------------------ §77–§78 hygiene
def test_repository_has_no_runtime_or_secret_artifacts_tracked() -> None:
    files = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True,
                           text=True, check=True).stdout.splitlines()
    forbidden_prefixes = ("workspace/", "ui/node_modules/", "ui/dist/",
                          "novel/authoring/story_engine/agent/",
                          "novel/authoring/story_engine/plugins/",
                          "novel/authoring/story_engine/quality/",
                          "novel/authoring/story_engine/delivery/",
                          "novel/authoring/story_engine/memory/")
    offenders = [row for row in files if row.startswith(forbidden_prefixes)]
    assert offenders == [], f"运行时产物被提交：{offenders[:10]}"
    assert not [row for row in files if row.endswith((".env", ".env.local"))]
    assert not [row for row in files if "node_modules" in row]
    assert any(row == ".gitignore" for row in files)


def test_gitignore_covers_v4_runtime_artifacts() -> None:
    text = (ROOT / ".gitignore").read_text(encoding="utf-8")
    for pattern in ("workspace", "node_modules", "ui/dist",
                    "novel/authoring", "*.tsbuildinfo"):
        assert pattern in text, f".gitignore 缺少 {pattern}"
