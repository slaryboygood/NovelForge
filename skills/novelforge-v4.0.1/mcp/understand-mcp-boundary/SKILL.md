---
name: novelforge-v4.0.1.mcp.understand-mcp-boundary
description: 掌握 MCP 层边界：它是接口适配器，不是业务层；REST 与它平级，Agent 不经过它。
---

# understand-mcp-boundary

- **Skill ID**: `novelforge-v4.0.1.mcp.understand-mcp-boundary`
- **Version**: 1（baseline `V4.0.1`）
- **Capability Module**: `mcp`
- **Product owner**: `src/novelforge/interfaces/mcp/__init__.py` + ADR-027 / ADR-028

## Purpose

避免把业务逻辑写进接口层，或让 Agent 通过 MCP 自调用绕开 Application 语义。

## Use when

- 需要扩展 MCP surface（Core 或插件）。
- 需要解释"为什么 MCP 里没有某个 tool"。

## Do not use when

- 只是调用 tool → `call-mcp-tool`。

## Preconditions

```text
无
```

## Required inputs

```text
无
```

## Authoritative interfaces

```text
UI           N/A
REST         N/A
Application  application.services.facade.ApplicationServices（唯一入口）
MCP          MCPDispatcher / create_mcp_server / registries
```

## Procedure（判断顺序）

```text
1 MCP 只做：协议解析 / 参数校验 / novel scope / 调 Application / 错误映射 / 序列化
2 MCP 不做：生成逻辑 / memory retrieval / 质量判断 / repair planning / blueprint mutation /
  delivery selection / 任何 mutation 决策
3 REST 与 MCP 平级：都只调 Application；MCP 不走 HTTP，REST 不调 MCP
4 Agent 与 MCP 平级：Agent 只调 Application / Ports（不启动 MCP client）
5 模块边界：interfaces.mcp → application.services / core；反向 import 一律禁止
6 新增 tool / resource 只能经申请（Core）或插件 adapter（Host），不能绕过 registry
```

## Expected result

能正确回答：

```text
· 能不能在 MCP tool 里直接调 LLMGateway？（不能；生成经 Application → generation → gateway）
· 能不能让 MCP 走内部 HTTP 调 REST？（不能；平级适配器）
· 插件 MCP tool 的名字长什么样？（plugin.<plugin_id>.<name>）
```

## Verification

```text
· 交叉核对 tests/v4/isolation/test_mcp_boundaries.py（import 守卫）
· 交叉核对 docs/v4/adr/ADR-027-mcp-is-an-interface-adapter-not-a-business-layer.md
· 交叉核对 docs/v4/adr/ADR-028-mcp-mutations-preserve-revision-and-approval-semantics.md
```

## Common failures

| 现象 | 原因 | 处理 |
| --- | --- | --- |
| tool 里出现业务判断 | 职责错位 | 移回 Application / 业务模块 |
| REST 与 MCP 结果不一致 | 有一方没走 Application | 修接口层，不改业务语义 |

## Safety / invariants

```text
状态与业务语义只在 Application / 业务模块中表达
接口层不持有 truth、不做 approval 决定
```

## Side effects

无。

## Related skills

`discover-mcp-surface`、`call-mcp-tool`、`read-mcp-resource`

## Source references

```text
src/novelforge/interfaces/mcp/__init__.py
docs/v4/V4_MCP_CONTRACT.md §1–§2、§10
tests/v4/isolation/test_mcp_boundaries.py
```
