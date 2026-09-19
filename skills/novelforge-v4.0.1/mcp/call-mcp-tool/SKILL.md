---
name: novelforge-v4.0.1.mcp.call-mcp-tool
description: 通过 MCP 调用工具（生成 / 编辑 / 质量 / 修复 / 交付），并正确解读 Result Envelope 与稳定错误码。
---

# call-mcp-tool

- **Skill ID**: `novelforge-v4.0.1.mcp.call-mcp-tool`
- **Version**: 1（baseline `V4.0.1`）
- **Capability Module**: `mcp`
- **Product owner**: `src/novelforge/interfaces/mcp/tools/**` +
  `src/novelforge/interfaces/mcp/errors.py`

## Purpose

安全地执行写入类调用：透传 revision / idempotency / dry_run / preserve 语义，
并按 envelope + 稳定 code 处理失败。

## Use when

- 需要生成 / 编辑 / 评估 / 修复 / 交付。
- 需要把失败原因程序化处理（而不是解析人类文案）。

## Do not use when

- 需要多步编排 → 用 Agent（MCP 不编排）。
- 需要返回自由文本 → 不存在（结构化字段才是 contract）。

## Preconditions

```text
已确定 tool（discover-mcp-surface）；novel_id / node_id / issue_ids 等参数齐备
```

## Required inputs

| 输入 | 必填 | 说明 |
| --- | --- | --- |
| `tool` | 是 | 23 个注册 tool 之一 |
| tool 专属参数 | 是 | 例如 `novel_id`、`node_id`、`expected_revision`、`idempotency_key` |
| `dry_run` | 否 | patch / rewrite / plan_repair / repair / validate / deliver 支持 |

## Authoritative interfaces

```text
UI           N/A
REST         等价（同一 Application service）
Application  MCPDispatcher.call_tool(name, arguments) → ApplicationServices
MCP          23 tools
```

## Procedure

```text
1 选 tool 并读它的业务 skill（例如生成 → generation/*，编辑 → editor/*）
2 传参：显式 novel_id；mutation 带 expected_revision + idempotency_key
3 调 call_tool → 先读 envelope.ok
4 ok=true → 用结构化字段（revision / node / result / issues / resources）
5 ok=false → 读 errors[].code（稳定码）+ cause（底层业务 code）+ details（白名单键）
6 重试策略：revision 冲突 → 重新读后重试；preserve 冲突 → 停下（不要放宽）
7 next：按所属模块 skill 继续（例如 repair → verify-repair）
```

## Expected result

```json
{"ok":true,"operation":"patch_blueprint_node","request_id":"mcp_…",
 "novel_id":"novel_alpha","revision":4,"revision_before":3,"dry_run":false,
 "result":{"changed_fields":["goal"]},"issues":[],"warnings":[],"read_only":false}
```

## Verification

```text
· errors 非空 ⇒ ok=false（不存在"部分失败但 ok=true"）
· 同一 idempotency_key 重试不产生第二个 revision / 第二个 snapshot
· dry_run=true 时 0 mutation（按业务契约）
· 失败返回体不含 traceback / 绝对路径 / secret
```

## Common failures

| code | 含义 | 处理 |
| --- | --- | --- |
| `MCP_REVISION_CONFLICT` | expected_revision 过期（cause 常为 EDITOR_REVISION_CONFLICT） | 重新读 revision 后重试 |
| `MCP_PRESERVE_VIOLATION` | 触及 preserve 字段 | 停下，不要放宽约束 |
| `MCP_QUALITY_BLOCKED` | 有 blocker issue | 先 `plan_repair` |
| `MCP_DELIVERY_BLOCKED` | preflight 未通过 | `validate_delivery` 看 blocking_reason |
| `MCP_OPERATION_REQUIRES_REVIEW` | 需要作者决定 | 转人工，不扩大 repair scope |
| `MCP_LLM_UNAVAILABLE` | 模型不可用 / 未启用 | 配置 provider |
| `MCP_OWNERSHIP_MISMATCH` | 跨作品 | 统一 novel_id |
| `MCP_INVALID_ARGUMENT` | 参数非法（含分页越界） | 修正参数 |

## Safety / invariants

```text
approval 语义保留：accept / reject 必须显式调用；不自动接受
delivery 默认 selection_mode=accepted
工具输入不接受 filesystem path / provider base_url / API key / shell 命令
```

## Side effects

与对应业务 skill 相同（写 revision / 质量结论 / 交付物）。

## Related skills

`read-mcp-resource`、`understand-mcp-boundary`、以及被调用工具所属模块的 skill

## Source references

```text
src/novelforge/interfaces/mcp/tools/*、dispatch.py、errors.py、payloads.py
docs/v4/V4_MCP_CONTRACT.md §6–§9
tests/mcp/test_mcp_tools.py、tests/mcp/test_mcp_contracts.py
```
