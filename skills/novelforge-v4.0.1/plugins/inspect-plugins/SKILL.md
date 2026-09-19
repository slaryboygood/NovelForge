---
name: novelforge-v4.0.1.plugins.inspect-plugins
description: 只读查看插件清单与状态（含 trust model、permission 模型与启用情况）。
---

# inspect-plugins

- **Skill ID**: `novelforge-v4.0.1.plugins.inspect-plugins`
- **Version**: 1（baseline `V4.0.1`）
- **Capability Module**: `plugins`
- **Product owner**: `src/novelforge/application/services/plugins.py::PluginService.list_plugins/status/permission_model`

## Purpose

在启用任何插件之前，先看清"有哪些插件、它们声明了什么、宿主当前是什么信任模型"。

## Use when

- 需要确认某格式 / evaluator / MCP tool 来自插件还是 Core。
- 需要向作者解释信任模型（permission ≠ OS 沙箱）。

## Do not use when

- 要启用 / 禁用 → `enable-plugin` / `disable-plugin`（Application-only）。

## Preconditions

```text
宿主已装配插件平台（未装配时 REST 返回 available=false + hint，属正常）
```

## Required inputs

| 输入 | 必填 | 说明 |
| --- | --- | --- |
| — | — | 无参数（列出全部） |

## Authoritative interfaces

```text
UI           「插件」页（只读）
REST         GET /api/story-builder/studio/plugins
Application  PluginService.list_plugins() / status() / permission_model() / get_plugin(id)
MCP          N/A
```

## Procedure

```text
1 GET /studio/plugins
2 读 available：false 表示宿主未装配（页面上是只读提示，不是错误）
3 对每个 plugin 读 plugin_id / name / version / status / capabilities / permissions /
  compatibility / approved_version / approved_permissions / error_code
4 读 trust_model 与 note（必须原样呈现给作者）
5 读 permissions（Host 支持的 permission 全集）
6 next：需要看贡献 → inspect-plugin-contributions；需要变更 → approve/enable/disable
```

## Expected result

```json
{"available":true,"trust_model":"trusted_in_process","note":"permission 是 Host API …",
 "permissions":["delivery.export","quality.evaluate","mcp.extend","ai.invoke",
                "blueprint.read","editor.mutate","network.request","plugin.state"],
 "plugins":[{"plugin_id":"acme.epub","version":"1.2.0","status":"approved",
             "capabilities":["exporter"],"permissions":["delivery.export"]}],
 "read_only":true}
```

## Verification

```text
· trust_model 文案与 plugins.permissions.permission_note() 完全一致（有测试断言）
· status ∈ 状态机枚举（discovered/compatible/approved/enabled/loaded/active/
  incompatible/disabled/failed）
· 页面 / API 都不提供 install / enable / disable（当前 DEFER）
```

## Common failures

| 现象 | 原因 | 处理 |
| --- | --- | --- |
| available=false | 宿主未注入 plugin_service | 正常；插件平台由宿主在 composition 处装配 |
| 插件 status=incompatible | 兼容性检查未通过 | 不要强启；查看 compatibility 详情 |

## Safety / invariants

```text
只读；不触发加载 / 启用
如实呈现 trusted in-process 的局限（不夸大隔离能力）
```

## Side effects

无。

## Related skills

`inspect-plugin-contributions`、`approve-plugin`、`enable-plugin`、`disable-plugin`

## Source references

```text
src/novelforge/application/services/plugins.py
src/novelforge/api/studio_routes.py::plugins（TRUST_MODEL / TRUST_MODEL_NOTE）
src/novelforge/plugins/permissions.py::permission_note
tests/plugins/test_plugin_security.py
docs/v4/V4_PLUGIN_CONTRACT.md
```
