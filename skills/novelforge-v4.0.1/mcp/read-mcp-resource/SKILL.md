---
name: novelforge-v4.0.1.mcp.read-mcp-resource
description: 通过 MCP 读取只读资源（作品 / 蓝图 / 场景 / 质量 / 评审 / 交付），含分页与路径安全规则。
---

# read-mcp-resource

- **Skill ID**: `novelforge-v4.0.1.mcp.read-mcp-resource`
- **Version**: 1（baseline `V4.0.1`）
- **Capability Module**: `mcp`
- **Product owner**: `src/novelforge/interfaces/mcp/resources/**` +
  `src/novelforge/interfaces/mcp/uri.py`

## Purpose

用统一的 URI 形状读取状态，不用 HTTP，也不用碰磁盘路径。

## Use when

- 客户端需要蓝图 / 场景 / 质量 / 交付的只读视图。
- 需要 artifact 字节（例如把交付物交给外部系统）。

## Do not use when

- 需要写入 → `call-mcp-tool`。

## Preconditions

```text
已连接 server 或可构造 dispatcher；novel_id 已知
```

## Required inputs

| 输入 | 必填 | 说明 |
| --- | --- | --- |
| `uri` | 是 | 资源 URI |
| `limit` / `cursor` | 否 | 分页（默认 50、上限 200） |

## Authoritative interfaces

```text
UI           N/A
REST         等价（同一 Application service）
Application  MCPDispatcher.read_resource(uri) → ApplicationServices.*
MCP          13 resources（见 discover-mcp-surface）
```

## Procedure

```text
1 选 URI：novelforge://novels/<id> | .../blueprint | .../scenes | .../quality |
  .../quality/issues | .../review | .../delivery | .../delivery/<sid> |
  .../delivery/<sid>/manifest | .../delivery/<sid>/artifacts/<path> |
  .../blueprint/nodes/<node_id> | .../blueprint/nodes/<node_id>/revisions/<n> |
  novelforge://interface
2 read_resource(uri, limit=?) → 读 JSON（或 artifact 字节 + MIME）
3 分页：读 next cursor 直到取完
4 artifact：只用 manifest 里登记的 path（拒绝 ../ / 绝对路径 / 盘符）
5 next：需要写入 → call-mcp-tool（mutation tool）
```

## Expected result

JSON 资源（或文件字节 + 正确 MIME）。资源全部只读。

## Verification

```text
· 返回内容与同参数的 REST 结果语义一致（同一 Application service）
· 分页 limit 默认 50、超过 200 被拒（MCP_INVALID_ARGUMENT）
· 非法 artifact 路径被拒（不返回任何文件）
```

## Common failures

| 现象 | 原因 | 处理 |
| --- | --- | --- |
| `MCP_RESOURCE_NOT_FOUND` | URI 形状 / id 不存在 | 用 discover-mcp-surface 的 URI 表 |
| `MCP_OWNERSHIP_MISMATCH` | novel_id 与资源不一致 | 统一 novel_id |
| 返回被截断 | 分页 | 用 cursor 继续 |

## Safety / invariants

```text
资源只读（read-only by construction）
不提供 novelforge://everything（粒度明确，ADR-027/§48）
不返回内部绝对路径 / secret
```

## Side effects

无。

## Related skills

`discover-mcp-surface`、`call-mcp-tool`、
`novelforge-v4.0.1.delivery.download-delivery-artifact`

## Source references

```text
src/novelforge/interfaces/mcp/resources/*、uri.py、serialization.py
docs/v4/V4_MCP_CONTRACT.md §5、§9
tests/mcp/test_mcp_resources.py
```
