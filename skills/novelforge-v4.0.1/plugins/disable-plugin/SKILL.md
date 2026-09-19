---
name: novelforge-v4.0.1.plugins.disable-plugin
description: 禁用一个插件并精确卸载它注册的贡献（不影响 Core，也不影响其它插件）。
---

# disable-plugin

- **Skill ID**: `novelforge-v4.0.1.plugins.disable-plugin`
- **Version**: 1（baseline `V4.0.1`）
- **Capability Module**: `plugins`
- **Product owner**: `src/novelforge/plugins/lifecycle.py` +
  `src/novelforge/application/services/plugins.py::PluginService.disable`

## Purpose

安全退出：卸载该插件的 exporter / evaluator / MCP 注册，避免残留能力继续被调用。

## Use when

- 插件行为异常 / 不再需要。
- 需要验证"卸载是否精确"（测试场景）。

## Do not use when

- 想修改插件权限 → 走 approve（重新批准）。
- 想删除插件文件 → 属于环境 / 部署动作，不在 Skill 范围。

## Preconditions

```text
插件当前为 enabled / loaded / active（或 failed → 也可 disable 清理）
```

## Required inputs

| 输入 | 必填 | 说明 |
| --- | --- | --- |
| `plugin_id` | 是 | 目标插件 |
| `reason` | 建议 | 记录原因 |

## Authoritative interfaces

```text
UI           N/A
REST         N/A（DEFER，见 GAP-005）
Application  PluginService.disable(plugin_id, reason=…)
MCP          N/A
```

## Procedure

```text
1 记录 disable 前的贡献清单（inspect-plugin-contributions）
2 PluginService.disable(plugin_id, reason="…")
3 复验 status == disabled
4 复验贡献消失：contributions 不再包含该 owner；交付格式 / MCP tool 表恢复 Core 基线
5 复验其它插件与 Core 注册不受影响
6 需要再次使用时：enable-plugin（批准记录仍在，权限未变时无需重新批准）
```

## Expected result

```json
{"plugin_id":"acme.epub","status":"disabled","unregistered":{"exporter":["epub"]}}
```

## Verification

```text
· 该 owner 的注册项全部移除（unregister_owner 语义，精确卸载）
· Core 基线恢复：MCP 23 tools / 13 resources；Core 4 种交付格式仍在
· 审计记录包含 disable 事件与 reason
```

## Common failures

| 现象 | 原因 | 处理 |
| --- | --- | --- |
| 仍能调用插件格式 | 用了未注入 registry 的旧实例 | 确认宿主注入同一个 registry |
| Core 能力受影响 | 不该发生 → 属缺陷 | 记录到 GAPS；不要手工改 registry |

## Safety / invariants

```text
EXACT_UNLOAD：只卸载该 owner
不删除 Core 注册（unregister_owner 保护 core owner）
禁用的是逻辑启用状态；模块热卸载不在范围内（需重启宿主才彻底释放）
```

## Side effects

卸载注册项、写审计记录。

## Related skills

`approve-plugin`、`enable-plugin`、`inspect-plugin-contributions`

## Source references

```text
src/novelforge/plugins/registry.py（unregister_owner）
src/novelforge/delivery/exporters/__init__.py、quality/registry.py、interfaces/mcp/registry.py
tests/plugins/test_plugin_lifecycle.py、tests/plugins/test_plugin_state.py
docs/v4/V4_PLUGIN_CONTRACT.md §7
```
