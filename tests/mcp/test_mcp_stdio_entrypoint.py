"""V4.0.2 PB-3 回归：**真实 stdio 入口**必须能启动并完成 MCP 握手。

Dogfood 复现（`docs/v4/V4_0_1_SKILL_DOGFOOD_REPORT.md` §8 PB-3）：

```text
PYTHONPATH=src NOVELFORGE_PROJECT_ROOT=<root> python -m novelforge.interfaces.mcp
  → AttributeError: 'NoneType' object has no attribute 'resources_changed'
    （server.get_capabilities(notification_options=None) 在 mcp 1.9.x 不被接受）
```

既有 `tests/mcp/**` 只覆盖 in-process dispatcher / SDK 会话，因此这个缺陷从未被门禁发现。
本文件用**正式 entrypoint**（`python -m novelforge.interfaces.mcp`）起子进程，
按 MCP stdio framing（换行分隔 JSON-RPC）走完整握手，并核对 Core 基线表面。
"""

from __future__ import annotations

import json
import os
import queue
import subprocess
import sys
import threading
from pathlib import Path
from typing import Any

import pytest

from novelforge.interfaces.mcp import MCP_SDK_AVAILABLE

ROOT = Path(__file__).resolve().parents[2]
TIMEOUT_S = 45.0


def _require_sdk() -> None:
    if not MCP_SDK_AVAILABLE:  # pragma: no cover - 环境缺依赖时跳过
        pytest.skip("未安装官方 MCP SDK（requirements.txt 记录了版本区间）")


class _StdioClient:
    """极简 stdio 客户端：换行分隔 JSON-RPC（与 SDK stdio transport 一致）。"""

    def __init__(self, project_root: Path) -> None:
        env = {**os.environ,
               "PYTHONPATH": str(ROOT / "src"),
               "NOVELFORGE_PROJECT_ROOT": str(project_root),
               "PYTHONIOENCODING": "utf-8"}
        self.proc = subprocess.Popen(
            [sys.executable, "-m", "novelforge.interfaces.mcp"],
            cwd=str(ROOT), env=env, text=True, encoding="utf-8", bufsize=1,
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        self._inbox: queue.Queue[dict[str, Any]] = queue.Queue()
        self.stderr_lines: list[str] = []
        threading.Thread(target=self._pump_stdout, daemon=True).start()
        threading.Thread(target=self._pump_stderr, daemon=True).start()

    # ------------------------------------------------------------------ 线程
    def _pump_stdout(self) -> None:
        for line in self.proc.stdout or ():
            text = line.strip()
            if not text:
                continue
            try:
                self._inbox.put(json.loads(text))
            except json.JSONDecodeError:
                continue

    def _pump_stderr(self) -> None:
        for line in self.proc.stderr or ():
            self.stderr_lines.append(line.rstrip())

    # ------------------------------------------------------------------ 协议
    def send(self, payload: dict[str, Any]) -> None:
        assert self.proc.stdin is not None
        self.proc.stdin.write(json.dumps(payload, ensure_ascii=False) + "\n")
        self.proc.stdin.flush()

    def response(self, request_id: int) -> dict[str, Any]:
        while True:
            try:
                row = self._inbox.get(timeout=TIMEOUT_S)
            except queue.Empty:  # pragma: no cover - 只在真正卡死时触发
                raise AssertionError(
                    f"等待 id={request_id} 的响应超时；stderr=\n"
                    + "\n".join(self.stderr_lines[-20:])) from None
            if row.get("id") == request_id:
                return row
            if "id" in row:
                continue                     # 其它响应（不会出现，保留防御）
            continue                         # notification

    def close(self) -> int:
        if self.proc.stdin is not None and not self.proc.stdin.closed:
            self.proc.stdin.close()
        try:
            return self.proc.wait(timeout=15)
        except subprocess.TimeoutExpired:  # pragma: no cover
            self.proc.kill()
            raise AssertionError("stdio server 关闭 stdin 后未退出") from None


@pytest.fixture()
def stdio_client(tmp_path: Path):
    _require_sdk()
    client = _StdioClient(tmp_path)
    try:
        yield client
    finally:
        if client.proc.poll() is None:
            client.proc.kill()


def _initialize(client: _StdioClient) -> dict[str, Any]:
    from mcp.types import LATEST_PROTOCOL_VERSION

    client.send({"jsonrpc": "2.0", "id": 1, "method": "initialize",
                 "params": {"protocolVersion": LATEST_PROTOCOL_VERSION,
                            "capabilities": {},
                            "clientInfo": {"name": "novelforge-gate",
                                           "version": "1"}}})
    response = client.response(1)
    assert "error" not in response, response
    client.send({"jsonrpc": "2.0", "method": "notifications/initialized"})
    return dict(response["result"])


def test_stdio_entrypoint_initializes_and_lists_surface(stdio_client: _StdioClient,
                                                        tmp_path: Path) -> None:
    """§32：initialize → tools/list（23）→ resources/list → templates/list → 干净退出。"""

    result = _initialize(stdio_client)
    assert result["serverInfo"]["name"] == "novelforge"
    capabilities = dict(result.get("capabilities") or {})
    assert "tools" in capabilities and "resources" in capabilities
    assert capabilities["tools"].get("listChanged") is False
    assert capabilities["resources"].get("listChanged") is False

    stdio_client.send({"jsonrpc": "2.0", "id": 2, "method": "tools/list",
                       "params": {}})
    tools = stdio_client.response(2)
    assert "error" not in tools, tools
    names = sorted(row["name"] for row in tools["result"]["tools"])
    assert len(names) == 23, names
    assert "generate_scene_plan" in names and "deliver_blueprint" in names

    stdio_client.send({"jsonrpc": "2.0", "id": 3, "method": "resources/list",
                       "params": {}})
    resources = stdio_client.response(3)
    static_uris = sorted(str(row["uri"]) for row in resources["result"]["resources"])
    assert static_uris == ["novelforge://interface"], static_uris

    stdio_client.send({"jsonrpc": "2.0", "id": 4,
                       "method": "resources/templates/list", "params": {}})
    templates = stdio_client.response(4)
    template_uris = sorted(str(row["uriTemplate"])
                           for row in templates["result"]["resourceTemplates"])
    assert len(template_uris) == 12, template_uris
    assert "novelforge://novels/{novel_id}/blueprint" in template_uris

    stdio_client.send({"jsonrpc": "2.0", "id": 5, "method": "resources/read",
                       "params": {"uri": "novelforge://interface"}})
    interface = stdio_client.response(5)
    assert "error" not in interface, interface
    payload = json.loads(interface["result"]["contents"][0]["text"])
    assert payload["mcp_interface_version"] == 1
    assert len(payload["tools"]) == 23

    exit_code = stdio_client.close()
    assert exit_code == 0, stdio_client.stderr_lines[-20:]
    assert not any("AttributeError" in line for line in stdio_client.stderr_lines), \
        stdio_client.stderr_lines[-20:]


def test_stdio_entrypoint_reports_startup_failures_on_stderr(stdio_client: _StdioClient
                                                             ) -> None:
    """守卫：崩溃必须体现在 stderr（而不是静默超时）。"""

    _initialize(stdio_client)
    assert stdio_client.proc.poll() is None, (
        "stdio server 在 initialize 之后不应自行退出；stderr=\n"
        + "\n".join(stdio_client.stderr_lines[-20:]))
