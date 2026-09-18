# ADR-031 Plugin Contributions Cannot Override Core Registrations

> 状态：**Accepted**（V4-09 实施完成）
> 日期：2026-09-18
> 阶段：V4-09 Plugin Platform
> 相关：ADR-026（Package 是选定产物）、ADR-018（Quality 是门禁）、
> `docs/v4/V4_PLUGIN_CONTRACT.md` §8

## 背景

V4-07 / V4-05 / V4-08 的 registry 在 V4-09 前没有 owner 概念：

```text
ExporterRegistry.register()          → 同 format 重复注册会静默 last-wins
EvaluatorRegistry.register()         → 同 evaluator_id 直接覆盖
MCPToolRegistry.register()           → 重复 name 抛 ValueError（无 owner 可卸载）
```

一旦开放给第三方，这些语义就会变成安全漏洞：

```text
插件注册 format="json"       → 覆盖 Core exporter，所有交付物由插件产生
插件注册 generate_scene_plan → 假冒 Core MCP tool
插件注册 Core issue code     → 改写质量含义 / 绕过门禁
```

## 决策

```text
插件贡献永远无法覆盖 / 修改 Core 注册；冲突时显式失败，不采用 last-wins。
每个注册项带 owner（owner_type = core | plugin，owner_id），因此 disable 插件
只能卸载它自己的贡献。
```

落地规则：

1. `ExporterRegistry.register`：同 format 且 **owner 不同** → `DeliveryFormatError`
   （插件侧映射为 `PLUGIN_REGISTRATION_CONFLICT`）；同 owner 重复注册 = 该 owner 更新
   自己的 handler（Core 更新 Core 是既有行为）。
2. `EvaluatorRegistry.register`：同 evaluator_id 且 owner 不同 → `QualityPolicyError`。
3. `MCPToolRegistry`：插件 tool 名必须是 `plugin.<plugin_id>.<name>`；与 Core 名称
   冲突（`core_names()`）→ `PLUGIN_REGISTRATION_CONFLICT`。
4. `MCPResourceRegistry`：插件资源 URI = `novelforge://plugins/<plugin_id>/<path>`，
   kind = `plugin_resource:<plugin_id>`（每插件独立分派）。
5. quality issue code：`register_plugin_code` 只接受 `plugin.<plugin_id>.` 前缀，
   且拒绝与 Core code 冲突（`PLUGIN_...`）；disable 时 `unregister_plugin_codes`。
6. `unregister_owner(owner_id)`：**永远不删除 `owner_type == "core"` 的注册项**。
7. 注册是原子的（§49）：任一贡献失败 → 整体回滚（`tests/plugins/test_plugin_registration.py`
   用"第 1 个合法 + 第 2 个冲突"的插件验证不留半注册）。

## 备选方案

| 方案 | 否决理由 |
| --- | --- |
| last-wins（现状） | 插件可静默替换 Core exporter / tool，交付物与质量含义被改写 |
| 冲突时跳过该贡献、保留其它贡献 | 半激活状态：插件说"我提供了 X"，实际没生效（§49） |
| 允许插件注册到 Core namespace 但标记 warning | 警告会被忽略；Core 语义必须不可协商 |
| disable 时清空整个 registry 再重建 | 会牵连其它插件与 Core；owner 卸载是精确解 |

## 后果

```text
正面
  · Core 能力不可被第三方替换（交付 / 质量 / MCP 语义稳定）
  · 冲突可解释：错误码 + existing_owner / incoming_owner
  · disable 精确：只卸载该插件的贡献
负面 / 约束
  · 插件必须使用 namespaced 名称（不能抢占好名字）
  · 插件不能"改进"Core exporter；只能新增 format
  · 同 owner 重复注册仍是更新语义（文档需要写清，避免误解为"可覆盖他人"）
```

## 验证

```text
tests/plugins/test_plugin_registration.py（Core tool / exporter 覆盖被拒；原子回滚）
tests/plugins/test_plugin_mcp.py          （23 tools / 13 resources 不受影响；disable 后消失）
tests/plugins/test_plugin_quality.py      （namespaced code；disable 后 code 注销）
tests/delivery/test_exporters.py          （Core exporter 行为不变）
tests/mcp/**                              （Core 工具 / 资源基线不变）
```
