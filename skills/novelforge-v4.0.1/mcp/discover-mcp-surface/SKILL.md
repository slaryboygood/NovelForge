---
name: novelforge-v4.0.1.mcp.discover-mcp-surface
description: 枚举真实 MCP 表面：23 个 tool 与 13 个 resource（含各自对应的能力），不要凭名字猜。
---

# discover-mcp-surface

- **Skill ID**: `novelforge-v4.0.1.mcp.discover-mcp-surface`
- **Version**: 1（baseline `V4.0.1`）
- **Capability Module**: `mcp`
- **Product owner**: `src/novelforge/interfaces/mcp/registry.py` +
  `{tools,resources}/__init__.py::build_tool_registry/build_resource_registry`

## Purpose

先读真实 registry，再决定调用什么。MCP 名字可能误导（例如 `deliver_blueprint` 默认只接受
accepted 内容）。

## Use when

- 接入新客户端后的第一步。
- 需要核对当前基线（23 / 13）是否被插件改变。

## Do not use when

- 只是想调一个已知 tool → `call-mcp-tool`。

## Preconditions

```text
能 import novelforge.interfaces.mcp（或已连接 server）
```

## Required inputs

```text
无（可选的 type / 过滤参数）
```

## Authoritative interfaces

```text
UI           N/A
REST         N/A
Application  build_tool_registry() / build_resource_registry()
MCP          resource novelforge://interface（接口元数据）
```

## Procedure

```text
1 from novelforge.interfaces.mcp.tools import build_tool_registry
  from novelforge.interfaces.mcp.resources import build_resource_registry
2 tools = build_tool_registry(); 逐个读 spec.name / description / 对应 Application service
3 resources = build_resource_registry(); 读 spec.uri（static / template）
4 对每个 tool 查 handler → Application Service → 所属 skill module（见 SOURCE_MAP.md）
5 生成类：generate_premise…generate_scene_plan（9）
   编辑类：patch / rewrite / regenerate / accept / reject / restore / diff（7）
   质量修复：evaluate_blueprint / plan_repair / repair_issue / verify_repair（4）
   交付：validate_delivery / create_delivery_snapshot / deliver_blueprint（3）
6 next：按业务模块 skill 的 Procedure 调用对应 tool
```

## Expected result

```text
23 tools / 13 resources
tools: generate_* (9) · patch_blueprint_node · rewrite_blueprint_node ·
       regenerate_blueprint_node · accept_revision · reject_revision · restore_revision ·
       diff_revisions · evaluate_blueprint · plan_repair · repair_issue · verify_repair ·
       validate_delivery · create_delivery_snapshot · deliver_blueprint
resources: interface · novels/{id} · blueprint · blueprint/nodes/{id} ·
       blueprint/nodes/{id}/revisions/{n} · scenes · quality · quality/issues · review ·
       delivery · delivery/{sid} · delivery/{sid}/manifest · delivery/{sid}/artifacts/{path}
```

## Verification

```text
· len(tools) == 23、len(resources) == 13（Core 基线；启用插件后只增不减）
· tool 名称与 spec 一一对应（无未注册名字）
· resource URI 形状与 V4_MCP_CONTRACT §5 一致
```

## Common failures

| 现象 | 原因 | 处理 |
| --- | --- | --- |
| 数量不等于 23 / 13 | 启用了插件（追加）或版本不同 | 用 contributions 区分 owner |
| 想找"正文写作 tool" | 明确不存在 | 见 V4_MCP_CONTRACT §4 的排除清单 |
| 想找 memory / canon tool | 当前 DEFER | 见 V4_0_1_SKILL_GAPS.md |

## Safety / invariants

```text
不根据名字猜功能：必须查 schema + handler + Application service + tests
不把 retired（V2/V3）能力写回 MCP
```

## Side effects

无。

## Related skills

`start-mcp-server`、`call-mcp-tool`、`read-mcp-resource`、`understand-mcp-boundary`

## Source references

```text
src/novelforge/interfaces/mcp/tools/__init__.py、resources/__init__.py、registry.py
docs/v4/V4_MCP_CONTRACT.md §4–§5
tests/mcp/test_mcp_tools.py、tests/mcp/test_mcp_resources.py
```
