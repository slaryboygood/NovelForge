---
name: novelforge-v4.0.1.workflows.use-novelforge-through-mcp
description: 端到端流程：用 MCP 客户端接入 NovelForge——发现表面 → 只读资源 → 原子工具 → 结果校验。
---

# use-novelforge-through-mcp

- **Skill ID**: `novelforge-v4.0.1.workflows.use-novelforge-through-mcp`
- **Version**: 1（baseline `V4.0.1`）
- **Capability Module**: `workflows`（组合层）
- **Product owner**: 无

## Purpose

让机器客户端以正确姿势使用 NovelForge：先发现、再只读、最后才写入，并且不做编排。

## Use when

- 把 NovelForge 接入 MCP 客户端 / IDE / 其它 Agent 宿主。

## Do not use when

- 需要多步自主编排 → 用 Agent（`operate-with-agent`），不要自己拼 MCP 序列。

## Preconditions

```text
· 依赖满足（mcp>=1.9,<2）；project_root 已知
· novel_id 已知（MCP 不支持"当前作品"推断）
```

## Required inputs

| 输入 | 必填 | 说明 |
| --- | --- | --- |
| `project_root` | 是 | 通过 `NOVELFORGE_PROJECT_ROOT` 或注入 |
| `novel_id` | 是 | 目标作品 |
| tool / resource URI | 是 | 由 Step 2 决定 |

## Authoritative interfaces

```text
见各步骤 skill（MCP 与 REST 平级，结果语义一致）
```

## Procedure（只引用 skill ID）

```text
Step 1 novelforge-v4.0.1.mcp.start-mcp-server              → 启动 server（stdio）
Step 2 novelforge-v4.0.1.mcp.discover-mcp-surface          → 23 tools / 13 resources
Step 3 novelforge-v4.0.1.mcp.understand-mcp-boundary       → 明确边界（不做业务判断）
Step 4 novelforge-v4.0.1.mcp.read-mcp-resource             → 读 blueprint / quality / delivery
Step 5 需要生成 → novelforge-v4.0.1.generation.*（对应 tool）
      需要编辑 → novelforge-v4.0.1.editor.*
      需要质量 → novelforge-v4.0.1.quality.*
      需要修复 → novelforge-v4.0.1.repair.*
      需要交付 → novelforge-v4.0.1.delivery.*
Step 6 novelforge-v4.0.1.mcp.call-mcp-tool                 → 解读 envelope 与稳定错误码
Step 7 多步编排需求 → 转 novelforge-v4.0.1.workflows.operate-with-agent（不要自己编排）
```

## Expected result

客户端以原子能力完成一次任务；失败时能按稳定 code 程序化处理。

## Verification

```text
· 同一输入下 MCP 结果与 REST 结果语义一致（同一 Application service）
· 每个调用都显式带 novel_id；跨作品被拒
· mutation 调用带 expected_revision + idempotency_key；失败不含 traceback / 绝对路径
```

## Common failures

| 现象 | 原因 | 处理 |
| --- | --- | --- |
| 找不到"写入正文"的 tool | 明确不存在 | 见 MCP Contract §4 排除清单 |
| 生成失败 `MCP_LLM_UNAVAILABLE` | provider 未启用 | 配置 provider |
| 期望 MCP 帮你串流程 | 不是 MCP 职责 | 用 Agent |

## Safety / invariants

```text
MCP 只是适配器：approval / revision / policy 语义全部保留
不通过 MCP 绕过质量、修复或交付前置条件
```

## Side effects

与所调用的 tool 相同。

## Related skills

`operate-with-agent`、`prepare-final-delivery`

## Source references

```text
skills/novelforge-v4.0.1/{mcp,generation,editor,quality,repair,delivery}/*
docs/v4/V4_MCP_CONTRACT.md §2、§4–§5
```
