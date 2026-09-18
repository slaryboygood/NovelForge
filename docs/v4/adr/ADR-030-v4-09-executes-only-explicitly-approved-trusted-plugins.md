# ADR-030 V4-09 Executes Only Explicitly Approved Trusted Plugins

> 状态：**Accepted**（V4-09 实施完成）
> 日期：2026-09-18
> 阶段：V4-09 Plugin Platform
> 相关：ADR-013（Provider 配置与 secret 边界）、`docs/v4/V4_PLUGIN_CONTRACT.md` §5–§7、§13

## 背景

插件平台有两种可能的信任模型：

```text
A. trusted in-process：插件代码与主进程同权运行（Python plugin）
B. untrusted sandbox：进程 / 容器 / WASM 隔离 + capability 系统强制
```

只有 A 可以在 V4-09 的成本内实现；B 需要真正的进程隔离与资源限制。
如果按 A 实现却对外声称"权限系统阻止插件读文件 / 联网"，就是**不诚实的安全承诺**：
in-process Python 插件随时可以 `import os` / `open()` / `socket()`。

## 决策

```text
V4-09 只执行**用户显式批准**的 trusted 插件（in-process）。
permission = Host API capability governance（Host 主动提供什么），
不是 Python / OS sandbox。
untrusted 插件的进程级隔离（sandbox）不在本阶段实现。
```

可执行规则：

1. `discovered` 不能直接 `active`：必须 `compatible → approved → enabled → loaded`（§17）。
2. `PluginManager.load()` 只对显式 enable 的插件执行 import（§91：`import novelforge.plugins`
   不扫描 distribution、不加载插件、不读磁盘）。
3. 未批准 → `PLUGIN_NOT_APPROVED`（不执行插件代码，测试断言模块未被 import）。
4. 不兼容 → `PLUGIN_INCOMPATIBLE`（不执行；已 enable 的插件在宿主升级后降级启动）。
5. permission 只控制 Host 提供给插件的 capability：

```text
delivery.export / quality.evaluate / mcp.extend / plugin.state / blueprint.read  ✅ 落地
ai.invoke                                                                     声明 + 上下文门禁
editor.mutate / network.request                                               仅声明（DEFER）
```

6. 升级不继承批准：新增 permission / version 变化 / package_digest 变化 → 必须重新 approve
   （`PLUGIN_PERMISSION_DENIED` 或 `PLUGIN_NOT_APPROVED`，§52–§53、§62）。
7. 文档与门面必须写明"permission ≠ OS sandbox"（`TRUST_MODEL_NOTE`、`permission_note()`、
   `PluginService.permission_model()`）。

## 备选方案

| 方案 | 否决理由 |
| --- | --- |
| 声称 permission 是安全沙箱 | 错误的安全承诺；in-process 插件可绕过（§20、§23） |
| V4-09 就实现进程隔离 / WASM | 远超本阶段范围；且没有真实需求驱动（§21） |
| 允许未批准插件"仅加载不执行" | import 本身就执行模块顶层代码（副作用 / 攻击面），必须显式批准 |
| 全自动启用已安装插件 | 违反"新发现插件默认不启用"（§17） |

## 后果

```text
正面
  · 安全语义诚实：作者与运维知道边界在哪里
  · 默认安全：未批准的代码永不执行
  · 可审计：approve / enable / load / failed 全进 audit.json
负面 / 约束
  · 安装 / 批准 / 启用是 operator 动作（V4-09 不做 marketplace / 自动安装）
  · 无进程级 timeout / 强杀（文档明确限制，§59）
  · 真正 untrusted 插件市场需要先做 sandbox（未来阶段）
```

## 验证

```text
tests/plugins/test_plugin_lifecycle.py::test_enable_requires_approval
tests/plugins/test_plugin_discovery.py::test_importing_plugins_never_discovers_or_touches_disk
tests/plugins/test_plugin_compatibility.py::test_incompatible_plugin_is_never_approved_or_loaded
tests/plugins/test_plugin_permissions.py          升级 / 越权 / 最小权限
tests/plugins/test_application_plugin_service.py::test_permission_model_is_exposed_honestly
```
