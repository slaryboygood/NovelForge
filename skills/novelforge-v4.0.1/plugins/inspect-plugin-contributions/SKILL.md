---
name: novelforge-v4.0.1.plugins.inspect-plugin-contributions
description: 查看插件实际注册的贡献（exporter / quality evaluator / MCP tool / MCP resource）与审计记录。
---

# inspect-plugin-contributions

- **Skill ID**: `novelforge-v4.0.1.plugins.inspect-plugin-contributions`
- **Version**: 1（baseline `V4.0.1`）
- **Capability Module**: `plugins`
- **Product owner**: `src/novelforge/application/services/plugins.py::PluginService.contributions/audit`

## Purpose

确认"插件到底加了什么"，避免把插件贡献误认为 Core 能力，或反过来漏掉插件格式。

## Use when

- 交付格式里出现未知 format → 查 owner。
- 需要审计某插件的加载 / 失败 / 卸载记录。

## Do not use when

- 只是列插件 → `inspect-plugins`。

## Preconditions

```text
宿主已装配插件平台；插件已 enable / load（未启用则没有贡献）
```

## Required inputs

| 输入 | 必填 | 说明 |
| --- | --- | --- |
| `type` | 否 | `exporter` / `quality_evaluator` / `mcp_tool` / `mcp_resource` |

## Authoritative interfaces

```text
UI           「插件」页（插件行内含 contributions）
REST         N/A（contributions 目前只有 Application 入口）
Application  PluginService.contributions(type=…) / audit()
MCP          N/A
```

## Procedure

```text
1 PluginService.contributions(type="exporter") → 看 format / owner_type / owner_id
2 PluginService.contributions(type="quality_evaluator") → 看 evaluator_id / gate / owner
3 PluginService.contributions(type="mcp_tool" | "mcp_resource") → 看 namespaced 名称
4 PluginService.audit() → discover / approve / enable / load / failed / disable 时间线
5 交叉核对：交付格式的 owner_type=plugin 时，必须能在 contributions 里找到
6 next：需要卸载 → disable-plugin（只卸载该插件的东西）
```

## Expected result

```json
[{"type":"exporter","format":"epub","owner_type":"plugin","owner_id":"acme.epub"},
 {"type":"mcp_tool","name":"plugin_acme.epub_export_epub","owner_id":"acme.epub"}]
```

## Verification

```text
· 插件贡献名必须 namespaced：MCP tool `plugin.<plugin_id>.<name>`、
  resource `novelforge://plugins/<plugin_id>/<path>`、issue code `plugin.<plugin_id>.<CODE>`
· Core 注册不出现在插件 contributions 里
· disable 之后该 owner 的贡献全部消失（不残留）
```

## Common failures

| 现象 | 原因 | 处理 |
| --- | --- | --- |
| 贡献为空 | 插件未 enabled / 加载失败 | 查看 status 与 audit 的失败原因 |
| 与交付格式不一致 | 用了不同的 registry 实例 | 交付侧应注入同一 ExporterRegistry（宿主装配） |
| disable 之后 `get_plugin().contributions` 仍非空 | 该字段是 manifest **声明**；**已注册**贡献看 `contributions(type=...)` | 以 registered_ids / contributions(type) 为准，声明列表不会随 disable 清空 |

## Safety / invariants

```text
只读；不注册 / 不卸载
插件贡献必须带 owner，便于精确卸载（ADDITIVE_ONLY 的可逆性）
```

## Side effects

无。

## Related skills

`inspect-plugins`、`disable-plugin`、`novelforge-v4.0.1.delivery.deliver-blueprint`

## Source references

```text
src/novelforge/plugins/adapters/{exporter,quality,mcp}.py
src/novelforge/plugins/discovery.py、registry.py
tests/plugins/test_plugin_registration.py、tests/plugins/test_plugin_exporter.py
docs/v4/V4_PLUGIN_CONTRACT.md §8–§11
```
