# ADR-029 Plugins Use Explicit Public Extension Points

> 状态：**Accepted**（V4-09 实施完成）
> 日期：2026-09-18
> 阶段：V4-09 Plugin Platform
> 相关：ADR-027（MCP 是 adapter 不是业务层）、ADR-012（统一 LLM Gateway）、
> `docs/v4/V4_PLUGIN_CONTRACT.md`、`docs/v4/V4_09_PLUGIN_EXTENSION_INVENTORY.md`

## 背景

V4-09 前的扩展方式是"改核心代码"：新增导出格式要改 `delivery`，新增质量规则要改
`quality/evaluators`。用户要求"可以增加新能力，但不修改 NovelForge Core"。

把插件实现成"往 `plugins/` 丢 `.py` 然后 import 任意模块"会立刻破坏 V4-01–V4-08
建立的全部模块边界（blueprint / generation / quality / editor / delivery / interfaces），
并且让 Core 必须知道具体插件是谁。

需要决定：插件通过**什么界面**与 Core 交互。

## 决策

```text
插件只能通过 Host 明确开放的扩展点贡献能力；
插件拿到的是"返回 Contribution"的接口，不是 registry、不是 repository、不是 services。
```

具体化：

1. **扩展点 = 已有 registry + Host adapter**，V4-09 开放三个（§31）：

```text
delivery.ExporterRegistry      ← ExporterAdapter
quality.EvaluatorRegistry      ← QualityEvaluatorAdapter
interfaces.mcp tool / resource ← McpAdapter
```

2. **插件只返回声明对象**（`PluginContribution` / SDK `Contribution` + factory）：

```python
def register(context):                 # 插件唯一的入口
    return [sdk.exporter_contribution(...)]
```

3. **Host 负责校验与注册**（§71–§72）：namespace、唯一 id、version、capability、
   permission、reserved name、schema 全部由 `PluginManager` + adapter 验证。
4. **插件不得 import 业务内部模块**（§84、§88）：repository / store / persistence /
   provider / interfaces 一律不可见；SDK（`novelforge.plugins.sdk`）是唯一稳定依赖。
5. **Core 不 import 具体插件**（§7）：装配只发生在 composition root
   （`novelforge/plugins/host.py`）。
6. **状态经 `persistence.paths`**（§28）：插件不得自己拼 story / state 路径。

## 备选方案

| 方案 | 否决理由 |
| --- | --- |
| 直接把 registry / `ApplicationServices` 传给插件 | 一个 exporter 插件会同时获得编辑 / 生成 / repair / delivery 全部业务能力（§24） |
| 让插件直接 import `novelforge.*` 内部模块 | Core 必须知道具体插件；边界（V4-01–V4-08 守卫）立即失效（§7、§88） |
| 用文件约定（`plugins/*.py` + 目录扫描 + 约定函数名） | 隐式加载、不可审计、无法声明权限 / 兼容性（§1、§61） |
| 只做配置扩展（不执行插件代码） | 无法支持第三方 exporter / evaluator（V4-09 的目标能力） |

## 后果

```text
正面
  · Core 保持稳定：新增格式 / 规则 / MCP 能力不需要改 Core 模块
  · 边界可机械验证（tests/v4/isolation/test_plugin_boundaries.py）
  · 贡献可追溯（owner_type + owner_id + contribution_id + version）
  · disable 精确：按 owner 卸载，Core 不受影响
负面 / 约束
  · 插件作者必须学习 SDK 与 manifest（不能"随手写个脚本"）
  · 新扩展点需要 Host adapter（不能自动获得 Core 内部能力）
  · V4-09 只开放 3 类扩展点；generation / provider / memory 仍 DEFER
```

## 验证

```text
tests/plugins/test_plugin_registration.py          插件只返回 contribution / adapter 注册
tests/plugins/test_plugin_exporter.py              §95 golden（仍走 Delivery 管线）
tests/plugins/test_plugin_quality.py               §96 golden（QualityService 仍负责判定）
tests/plugins/test_plugin_mcp.py                   §97 golden（Host adapter 注册 tool / resource）
tests/v4/isolation/test_plugin_boundaries.py       Core ✗ import plugins；插件 ✗ 业务模块
```
