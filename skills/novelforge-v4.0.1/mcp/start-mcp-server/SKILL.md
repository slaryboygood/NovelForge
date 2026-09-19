---
name: novelforge-v4.0.1.mcp.start-mcp-server
description: 启动 NovelForge MCP server（stdio），并确认它能按 project_root 惰性构造 per-novel 服务。
---

# start-mcp-server

- **Skill ID**: `novelforge-v4.0.1.mcp.start-mcp-server`
- **Version**: 1（baseline `V4.0.1`）
- **Capability Module**: `mcp`
- **Product owner**: `src/novelforge/interfaces/mcp/server.py` +
  `src/novelforge/interfaces/mcp/__main__.py`

## Purpose

让机器客户端（IDE / Agent 宿主 / 外部工具）接入 NovelForge 的原子能力。

## Use when

- 需要把 NovelForge 接到 MCP 客户端。
- 需要在进程内测试 dispatcher（不走 stdio）。

## Do not use when

- 只需要单次调用 → 直接用 REST / Application（不必起 server）。
- 想通过 MCP 编排多步 → 用 Agent（MCP 明确不暴露编排）。

## Preconditions

```text
· 依赖已安装（mcp>=1.9,<2）
· 项目根路径已知（不做隐式"当前作品"推断）
```

## Required inputs

| 输入 | 必填 | 说明 |
| --- | --- | --- |
| `NOVELFORGE_PROJECT_ROOT` | 是（stdio） | 项目根 |
| `services_factory` / `gateway` / `memory` | 否（in-process） | 注入依赖（测试可注入 stub） |

## Authoritative interfaces

```text
UI           N/A
REST         N/A（MCP 与 REST 平级，不互相调用）
Application  create_mcp_server(project_root, services_factory=…, gateway=…, memory=…)
             create_dispatcher(...) / MCPDispatcher（in-process）
MCP          stdio transport
```

## Procedure

```text
1 设置 NOVELFORGE_PROJECT_ROOT 指向仓库（或测试用 workspace 根）
2 $env:PYTHONPATH="<repo>\src"; .venv\Scripts\python.exe -m novelforge.interfaces.mcp  （stdio）
   注意：仓库未把 novelforge 装成 package（`pip show novelforge` 为空），所以**必须**
   让 `src` 进入 PYTHONPATH，否则直接报 ModuleNotFoundError: No module named 'novelforge'。
   ⚠ 实测（V4.0.1 dogfood，mcp 1.9.4，即 requirements.txt 允许区间内）：stdio 入口当前
   启动即崩：`AttributeError: 'NoneType' object has no attribute 'resources_changed'`
   （`interfaces/mcp/server.py::run_stdio` 把 notification_options=None 传给
   `Server.get_capabilities`）。要在本版本真正跑 MCP，请用下面的 in-process 路径
   （create_dispatcher / MCPDispatcher），或等产品修 stdio 入口。
3 用客户端列出 tools / resources（见 discover-mcp-surface）
4 调用任意 tool 时显式传 novel_id
5 需要真实模型能力时：宿主需注入 gateway 且 provider enabled（否则生成类 tool 返回 MCP_LLM_UNAVAILABLE）
```

## Expected result

server 以 `novelforge` 身份握手成功；tools / resources 列表可枚举；调用返回 Result Envelope。

## Verification

```text
· tools 数量 23、resources 数量 13（Core 基线；插件只追加）
· 未注入 gateway 时生成类 tool → MCP_LLM_UNAVAILABLE（不是崩溃、不是伪造内容）
· resource novelforge://interface 返回接口元数据（版本 / 工具表 / 资源表）
```

## Common failures

| 现象 | 原因 | 处理 |
| --- | --- | --- |
| 启动即报依赖错误 | mcp / starlette 版本不匹配 | 使用 README 的依赖区间 |
| 启动即 ModuleNotFoundError: novelforge | venv 里没有安装该包 | 设 PYTHONPATH=<repo>\src（见 Procedure 步骤 2） |
| 启动即 `'NoneType' object has no attribute 'resources_changed'` | stdio 入口的已知缺陷（mcp 1.9.x） | 用 in-process dispatcher，或修 runtime 后再用 stdio |
| 每次调用都扫盘很慢 | 期望值：应按 novel_id 惰性构造 | 检查是否传了 project_root |
| 生成失败 | provider 未启用 | 配置 provider（不要绕过 Gateway） |

## Safety / invariants

```text
不为 MCP 开副作用通道：所有 mutation 仍走 Application 语义（revision / approval / policy）
不预加载全部作品；不在 import 时扫描项目
```

## Side effects

启动本地 stdio 进程；不修改任何 artifact（除非调用 mutation tool）。

## Related skills

`discover-mcp-surface`、`call-mcp-tool`、`read-mcp-resource`

## Source references

```text
src/novelforge/interfaces/mcp/server.py、__main__.py、dispatch.py
docs/v4/V4_MCP_CONTRACT.md §3、§10
tests/mcp/test_mcp_server.py
```
