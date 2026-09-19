# Module: `plugins` — 插件平台（Host 扩展点）

```text
Module purpose     通过 Host 明确的扩展点**追加**能力（exporter / evaluator / MCP tool / resource）
Authoritative owner src/novelforge/plugins/{host,manager,lifecycle,permissions,adapters,discovery}.py
Owned skills       inspect-plugins / inspect-plugin-contributions / approve-plugin /
                   enable-plugin / disable-plugin
Truth ownership    插件没有 story truth；插件 state 只能是 cache / settings / metadata
Public interfaces  UI「插件」+ REST GET /studio/plugins（只读）；
                   Application PluginService（approve / enable / disable / discover / contributions / audit）；
                   MCP = N/A（插件可注册 MCP tool，但插件生命周期本身不通过 MCP）
Dependencies       delivery.ExporterRegistry / quality.EvaluatorRegistry / interfaces.mcp registries
Forbidden          插件直接改 Blueprint / Canon / StoryState / Quality Store、直接调 provider、
                   自拼 artifact 路径、覆盖 Core 注册
Related modules    delivery / quality / mcp（被扩展），agent（不经插件）
```

## 事实表

| 项 | 值 |
| --- | --- |
| 状态机 | `discovered → compatible → approved → enabled → loaded → active`（异常 → `incompatible` / `failed` / `disabled`） |
| permission 白名单 | `delivery.export`, `quality.evaluate`, `mcp.extend`, `ai.invoke`, `blueprint.read`, `editor.mutate`, `network.request`, `plugin.state` |
| contribution 类型 | `exporter`, `quality_evaluator`, `mcp_tool`, `mcp_resource` |
| 发现方式 | entry point group `novelforge.plugins` 或显式 manifest 路径 |
| 信任模型 | `trusted_in_process`（permission 是 Host 能力治理，**不是** OS 沙箱） |
| host 元数据 | `novel/authoring/story_engine/plugins/{enablement.json,audit.json,state/<novel_id>/<plugin_id>/}` |

## 不变量

```text
ADDITIVE_ONLY：插件只能追加，不能覆盖 Core 注册（同名冲突直接拒绝）
EXACT_UNLOAD_ON_DISABLE：disable 只卸载该 owner 的注册项
PERMISSION_UPGRADE_NEEDS_REAPPROVAL：版本或权限变化必须重新批准
NO_INTERPRETER_ESCAPE：不承诺拦截 in-process 插件的任意 Python 能力（诚实声明）
```
