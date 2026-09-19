# Module: `mcp` — MCP 机器接口（薄适配层）

```text
Module purpose     把 Application Services 暴露给 MCP 客户端：23 tools / 13 resources
Authoritative owner src/novelforge/interfaces/mcp/**（server / registry / dispatch / tools / resources）
Owned skills       start-mcp-server / discover-mcp-surface / read-mcp-resource /
                   call-mcp-tool / understand-mcp-boundary
Truth ownership    无。MCP 是接口适配层，不做业务判断（ADR-027）
Public interfaces  stdio transport（python -m novelforge.interfaces.mcp）；
                   in-process：create_mcp_server / create_dispatcher / MCPDispatcher
Dependencies       application.services.facade.ApplicationServices、core（ids/errors）、MCP SDK
Forbidden          调 LLM / 读 memory / 做质量判断 / 规划修复 / 改 Blueprint / 走 HTTP 调 REST
Related modules    所有业务模块（作为被暴露者），agent 与它平级（agent 不通过 MCP 调业务）
```

## 事实表

| 项 | 值 |
| --- | --- |
| server 名 | `novelforge` |
| 启动 | `NOVELFORGE_PROJECT_ROOT=<root> python -m novelforge.interfaces.mcp`（stdio） |
| 接口版本 | `MCP_INTERFACE_VERSION = 1`（独立于 blueprint / delivery schema 版本） |
| 基线 | 23 tools / 13 resources（1 static + 12 template） |
| 分页 | `limit` 默认 50、上限 200，`cursor` 不透明 |
| 依赖区间 | `mcp>=1.9,<2`、`sse-starlette<2`、`starlette<0.47` |

## 不变量

```text
MCP_IS_NOT_THE_BUSINESS_LAYER：只做协议解析 / 参数校验 / novel scope / 错误映射 / 序列化
NOVEL_SCOPE_EXPLICIT：每个 tool / resource 显式 novel_id；跨作品 → MCP_OWNERSHIP_MISMATCH
RESULT_ENVELOPE：errors 非空 ⇒ ok=false（不允许"部分失败但 ok=true"）
NO_LEAK：返回值不含 secret / Authorization / 完整 prompt / 绝对内部路径
REVISION_SEMANTICS_PRESERVED：expected_revision / idempotency_key / dry_run / preserve 全部透传
```
