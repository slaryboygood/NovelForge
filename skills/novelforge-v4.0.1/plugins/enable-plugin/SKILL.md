---
name: novelforge-v4.0.1.plugins.enable-plugin
description: 启用一个已批准插件：加载它并注册其贡献（exporter / evaluator / MCP），原子生效。
---

# enable-plugin

- **Skill ID**: `novelforge-v4.0.1.plugins.enable-plugin`
- **Version**: 1（baseline `V4.0.1`）
- **Capability Module**: `plugins`
- **Product owner**: `src/novelforge/plugins/lifecycle.py` +
  `src/novelforge/application/services/plugins.py::PluginService.enable`

## Purpose

让插件的贡献真正在宿主里可用（例如新增交付格式），同时保证"要么全部注册成功，要么全部回滚"。

## Use when

- 已批准，需要开始使用它的能力。
- 之前 disabled，需要重新启用。

## Do not use when

- 还没批准 → `approve-plugin`。
- 需要立即卸载 → `disable-plugin`。

## Preconditions

```text
插件 status == approved（或 disabled → 可重新启用）
宿主已装配相应 registry（delivery exporter / quality evaluator / MCP）
```

## Required inputs

| 输入 | 必填 | 说明 |
| --- | --- | --- |
| `plugin_id` | 是 | 目标插件 |

## Authoritative interfaces

```text
UI           N/A
REST         N/A（DEFER，见 GAP-005）
Application  PluginService.enable(plugin_id)
MCP          N/A
```

## Procedure

```text
1 inspect-plugins → 确认 status=approved 且 approved_permissions 覆盖用途
2 PluginService.enable(plugin_id)
3 复验 status：enabled → loaded → active
4 inspect-plugin-contributions → 确认贡献已注册且 namespaced
5 若是 exporter：GET /studio/delivery/formats 应出现新 format（owner_type=plugin）
6 next：实际使用（例如交付时选择该格式）
```

## Expected result

```json
{"plugin_id":"acme.epub","status":"active",
 "contributions":[{"type":"exporter","format":"epub"}]}
```

## Verification

```text
· 全部贡献注册成功；任一失败 → 整体回滚（不留半套注册）
· 与 Core 同名 / 同格式冲突 → 直接拒绝（Core 永远优先）
· 加载失败 → status=failed 且审计记录含原因
```

## Common failures

| 现象 | 原因 | 处理 |
| --- | --- | --- |
| `PLUGIN_PERMISSION_INVALID` | 需要的权限未批准 | 重新 approve（显式） |
| 注册冲突 | 插件试图覆盖 Core / 其它插件注册 | 拒绝；改插件命名空间 |
| status=failed | 入口点导入异常 | 查看 audit；修插件后重试 |

## Safety / invariants

```text
插件代码在宿主进程内运行（trusted in-process）：启用是 operator 决定
只能追加，不能覆盖 Core 注册（ADR-031）
原子注册：失败不留半套贡献
```

## Side effects

加载插件模块、注册贡献、写审计记录。

## Related skills

`approve-plugin`、`disable-plugin`、`inspect-plugin-contributions`

## Source references

```text
src/novelforge/plugins/host.py、manager.py、registry.py
tests/plugins/test_plugin_lifecycle.py、tests/plugins/test_plugin_registration.py
docs/v4/adr/ADR-031-plugin-contributions-cannot-override-core-registrations.md
```
