---
name: novelforge-v4.0.1.plugins.approve-plugin
description: 批准一个插件并记录已批准的 permission 集合（operator 操作，无 REST / MCP 入口）。
---

# approve-plugin

- **Skill ID**: `novelforge-v4.0.1.plugins.approve-plugin`
- **Version**: 1（baseline `V4.0.1`）
- **Capability Module**: `plugins`
- **Product owner**: `src/novelforge/plugins/lifecycle.py` +
  `src/novelforge/application/services/plugins.py::PluginService.approve`

## Purpose

把"用户显式同意这个插件在宿主内运行，并且允许它使用这些 Host 能力"记录下来。
批准是启用前的前置条件。

## Use when

- operator（作者）明确要求使用某个插件。
- 插件升级后权限 / 版本变化，需要重新批准。

## Do not use when

- 插件未通过兼容性检查（status=incompatible）→ 不要批准。
- 插件来源不可信 / manifest 未审阅 → 先审阅 manifest。

## Preconditions

```text
插件已 discovered 且 status=compatible（否则批准不应发生）
operator 已阅读 manifest（entry_point / capabilities / permissions / version / digest）
```

## Required inputs

| 输入 | 必填 | 说明 |
| --- | --- | --- |
| `plugin_id` | 是 | 目标插件 |
| `permissions` | 建议 | 显式批准的 permission 子集；缺省 = manifest 声明集 |
| `approved_by` | 否 | 记录批准者（默认 `user`） |
| `note` | 否 | 批准备注 |

## Authoritative interfaces

```text
UI           N/A
REST         N/A（DEFER，见 GAP-005）
Application  PluginService.approve(plugin_id, permissions=…, approved_by=…, note=…)
MCP          N/A
```

## Procedure

```text
1 inspect-plugins → 确认 plugin_id / version / status / declared permissions
2 审阅 manifest：capabilities 与 permissions 是否与它的用途一致（最小权限）
3 PluginService.approve(plugin_id, permissions=<最小集合>, approved_by="author", note="…")
4 复验：status → approved；approved_permissions 已写入 enablement.json
5 升级场景：若版本或权限变化，requires_reapproval 会要求重新批准
6 next：enable-plugin
```

## Expected result

```json
{"plugin_id":"acme.epub","status":"approved",
 "approved_version":"1.2.0","approved_permissions":["delivery.export"]}
```

## Verification

```text
· status == approved；approved_permissions ⊆ manifest.permissions
· 请求未批准的 permission → PLUGIN_PERMISSION_INVALID（必须重新批准，§53）
· 记录落在 novel/authoring/story_engine/plugins/enablement.json（host 级）
```

## Common failures

| 现象 | 原因 | 处理 |
| --- | --- | --- |
| 权限不足报错 | 插件运行需要更多权限 | 重新审阅并获批后才能加 |
| 版本变化后加载失败 | 需要重新批准 | 再次执行 approve（记录新版本与新权限） |
| 未审阅就批准 | 流程错误 | 禁止：必须先读 manifest |

## Safety / invariants

```text
destructive-adjacent：批准 = 授权在宿主进程内运行代码，必须 operator 显式执行
最小权限：只批准用途需要的 permission
升级必须重新批准（不静默继承旧批准）
permission 不是 OS 沙箱：批准前必须理解这一局限
```

## Side effects

写 host 级 enablement 记录 + 审计记录。

## Related skills

`inspect-plugins`、`enable-plugin`、`disable-plugin`

## Source references

```text
src/novelforge/plugins/lifecycle.py、permissions.py（requires_reapproval / check_approval）
tests/plugins/test_plugin_lifecycle.py、tests/plugins/test_plugin_permissions.py
docs/v4/V4_PLUGIN_CONTRACT.md §6–§7
docs/v4/adr/ADR-030-v4-09-executes-only-explicitly-approved-trusted-plugins.md
```
