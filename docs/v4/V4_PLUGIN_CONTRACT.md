# NovelForge V4 — Plugin Contract（V4-09 冻结，SSOT）

> 状态：**V4-09 Plugin Platform 冻结**
> 依据：`docs/v4/V4_09_PLUGIN_EXTENSION_INVENTORY.md`、`docs/v4/V4_PLUGIN_SPEC.md`（设计输入）、
> `V4_DELIVERY_CONTRACT.md`（V4-07）、`V4_QUALITY_CONTRACT.md`（V4-05）、`V4_MCP_CONTRACT.md`（V4-08）
> 定位：**插件平台的唯一 SSOT**。改插件行为先改本文件，再改代码。

---

## 1. 一句话定义

```text
第三方可以扩展 NovelForge，但 Core 不需要知道它是谁。
Plugin Package → Manifest → Compatibility → Approval → Permission →
Contribution → Host Adapter → Existing Registry → Existing Business Pipeline
```

铁律（§1）：

```text
PLUGIN_USES_PUBLIC_EXTENSION_POINTS
PLUGIN_NEVER_BECOMES_CORE
PLUGIN_CANNOT_BYPASS_APPLICATION_BOUNDARY
PLUGIN_LOADING_IS_EXPLICIT
PLUGIN_ENABLEMENT_IS_EXPLICIT
PLUGIN_PERMISSIONS_ARE_DECLARED
PLUGIN_FAILURE_IS_ISOLATED
```

---

## 2. Public Contract（`novelforge.plugins`）

```text
生命周期           PluginManager / PluginRegistry / PluginRecord / PluginStatus
结构化声明         PluginManifest / PluginDescriptor
贡献               PluginContribution（type + contribution_id + version +
                   permissions_required + factory + metadata）
配置 / 结果        PluginConfig / PluginResult（含 .provenance）
版本 / 白名单      PLUGIN_API_VERSION / PLUGIN_PERMISSIONS / PLUGIN_STATUSES /
                   PLUGIN_TRANSITIONS / CONTRIBUTION_TYPES / RESERVED_NAMESPACES
信任模型           TRUST_MODEL / TRUST_MODEL_NOTE
发现 / 兼容        discover_installed / discover_manifest_paths / check_compatibility
状态 / 审计        EnablementStore / PluginStateStore / PluginAuditLog
装配               build_adapters（Host 侧 adapter）
错误               PluginError 家族（稳定 code）
```

不在 Public Contract 内（内部实现）：`adapters.*` 细节、`sdk.*`（对插件作者的**唯一**稳定依赖）、
`plugins.host.PluginHost`（composition root，宿主侧）。

---

## 3. Plugin SDK（`novelforge.plugins.sdk`）

```text
Contribution                 声明一个贡献（Host 负责验证与注册）
exporter_contribution / quality_contribution /
mcp_tool_contribution / mcp_resource_contribution
quality_issue(context, ...)  构造 namespaced QualityIssue（须先在 contribution 声明 issue_codes）
PluginContext                窄上下文（least privilege）
PluginAIClient               窄 AI 能力协议（Host 注入；插件不得直接调模型）
PLUGIN_SDK_VERSION / PERMISSIONS / CONTRIBUTION_KINDS
```

**SDK 是插件作者的稳定边界**（§8）：插件只允许依赖 `novelforge.plugins.sdk` + Python stdlib
（`tests/v4/isolation/test_plugin_boundaries.py::test_fixture_plugins_only_import_sdk_and_stdlib`）。
SDK **不暴露** repository / store / provider / persistence / ApplicationServices。

---

## 4. Manifest（§10–§12）

```text
plugin_id            全局唯一 + 稳定 + 反向域名 namespace（com.example.myplugin）
name / version
plugin_api_version   默认 PLUGIN_API_VERSION（= 1）
description / author / homepage
entry_point          `module:attribute`（callable）或 `module`（模块暴露 register(context)）
capabilities         exporter | quality_evaluator | mcp_tool | mcp_resource
permissions          §6 白名单子集
configuration_schema
host_compatibility   min_host_version（可选）
package_digest       识别"批准之后代码被替换"
```

规则：

```text
· plugin_id 不得是 plugin1 / test / new_plugin 之类的裸名字（PLUGIN_MANIFEST_INVALID）
· 保留 namespace：novelforge.* / core.*（第三方禁止）
· PLUGIN_API_VERSION 与 MCP_INTERFACE_VERSION / BLUEPRINT_SCHEMA_VERSION /
  DELIVERY_SCHEMA_VERSION 相互独立
```

---

## 5. Discovery（§14–§16、§61、§62）

```text
discovery ≠ load
  discover  只读 metadata / manifest + 兼容性判定，**绝不执行插件代码**
  来源      ① importlib.metadata.entry_points(group="novelforge.plugins")
            ② host 显式提供的 manifest 路径（extra）
  禁止      递归扫描 project/plugins/*.py；不 import 任意模块
  禁止      marketplace / 在线下载 / 自动 pip install / Git 自动安装 / 自动升级
```

`import novelforge.plugins` 本身**不扫描 distribution、不读磁盘、不加载插件**（§91，有测试）。

---

## 6. Permission 模型（§22–§27）

| Permission | 含义 | V4-09 落地 |
| --- | --- | --- |
| `delivery.export` | 注册 delivery exporter | ✅ |
| `quality.evaluate` | 注册 quality evaluator | ✅ |
| `mcp.extend` | 注册 MCP tool / resource | ✅ |
| `ai.invoke` | 经 Host 窄 AI 能力调用模型 | 声明 + 上下文门禁（Host 能力待接入） |
| `blueprint.read` | 经 `PluginContext` 读只读 Blueprint 视图 | ✅（MCP 工具 / 资源上下文） |
| `editor.mutate` | 经 Host 的窄 mutation 能力 | 仅声明（DEFER） |
| `network.request` | Host 中介的网络能力 | 仅声明（DEFER） |
| `plugin.state` | 读写本插件 namespaced state | ✅ |

```text
permission = Host API capability governance
permission ≠ Python interpreter sandbox
permission ≠ OS security sandbox

恶意 in-process 插件仍可能直接 `import os` / 打开文件 / 建立 socket；
进程级隔离（untrusted sandbox）不在 V4-09 实现。
```

升级语义：

```text
插件新增 permission → 不自动继承批准 → PLUGIN_PERMISSION_DENIED，
必须重新 approve（EnablementStore 记录 approved_version + approved_permissions + package_digest）
manifest version / package_digest 变化 → 同样要求重新批准
```

---

## 7. Lifecycle（§17–§19、§48–§53）

```text
discovered → compatible → approved → enabled → loaded → active
                 ↘ incompatible                 ↘ failed
任意已加载状态 → disabled（逻辑禁用 + 卸载贡献）
```

| 状态 | 含义 |
| --- | --- |
| `discovered` | 已发现 metadata（未判定） |
| `compatible` | 兼容当前 Host（可 approve） |
| `incompatible` | API / capability / host 版本不匹配 → 不执行 |
| `approved` | 用户显式批准（记录 version + permissions + digest） |
| `enabled` | 已启用（enablement 记录 enabled=true） |
| `loaded` | 已 import 且贡献已注册 |
| `active` | 可被调用（= loaded + 启用） |
| `disabled` | 逻辑禁用（贡献已卸载，Core 不受影响） |
| `failed` | 加载/注册/执行失败（错误已记录，Core 继续） |

流转表唯一 SSOT：`novelforge.plugins.contracts.PLUGIN_TRANSITIONS`
（测试核对 `lifecycle_table()`；`quarantined` 未引入 = 不做过度设计）。

失败隔离（§19、§81）：

```text
一个插件失败 → 该插件 status=failed / error_code 记录；
Core（exporter / quality / MCP）与其它插件继续；
宿主启动时 enabled 插件不兼容 → 降级启动（plugin failed，应用不崩）
```

原子注册（§49）：插件声明 N 个贡献时，任一贡献冲突 → **整体回滚**，不留半激活状态。

---

## 8. Contribution 与 Host Adapter（§70–§75）

| contribution type | Adapter | 注册目标 | namespaced 形式 |
| --- | --- | --- | --- |
| `exporter` | `ExporterAdapter` | `delivery.ExporterRegistry` | `plugin.<plugin_id>.<exporter_id>`（format 不得与 Core 相同） |
| `quality_evaluator` | `QualityEvaluatorAdapter` | `quality.EvaluatorRegistry` | `plugin.<plugin_id>.<evaluator_id>`；issue code = `plugin.<plugin_id>.<CODE>` |
| `mcp_tool` | `McpAdapter` | `MCPToolRegistry` | `plugin.<plugin_id>.<name>` |
| `mcp_resource` | `McpAdapter` | `MCPResourceRegistry` | `novelforge://plugins/<plugin_id>/<path>`，kind = `plugin_resource:<plugin_id>` |

```text
每个注册项记录 owner_type（core|plugin）+ owner_id → disable 一个插件只卸载它自己的贡献（§75）
Core 注册不可覆盖 / 不可修改：
  · 同 format exporter 由不同 owner 注册 → DELIVERY_FORMAT_DUPLICATE（PLUGIN_REGISTRATION_CONFLICT）
  · 与 Core MCP tool 同名 → PLUGIN_REGISTRATION_CONFLICT
  · 插件 evaluator id / issue code 不得与 Core 冲突
同一 owner 可更新自己的注册（core 更新 core；插件更新自己的插件），这不构成覆盖 Core
```

---

## 9. Exporter 扩展（§32–§34）

```text
输入   已选定内容（compiled blueprint / delivery context），不是 repository / store
输出   artifact bytes + metadata
禁止   选择 accepted/current revision、读 QualityStore / EditorStore、决定 selection
仍然经过 Delivery 的 preflight → post-build 校验 → secret scan → path validation →
        manifest → checksum（插件不能绕过 DeliveryValidator）
DELIVERY selection 允许的格式 = EXPORT_FORMATS ∪ Host 注入 registry 的 formats
```

## 10. Quality evaluator 扩展（§35–§37、§78–§80）

```text
执行顺序 / policy / gate / evidence / report 仍由 QualityService 负责（插件不是第二个 QualityService）
插件 evaluator 默认不参与（QualityPolicy.plugin_evaluator_ids 显式列出才运行）
默认 non-blocking（QualityPolicy.plugin_blocking=False）→ 安装插件不会让所有项目突然无法交付
issue code 必须 namespaced（plugin.<plugin_id>.CODE），禁止覆盖 Core code
issue provenance 保留 plugin_id + evaluator version（历史结果不被新版本冒名）
插件 evaluator 只读：不得修改 Blueprint / Canon / StoryState，不得调用 RepairExecutor
```

## 11. MCP 扩展（§38–§42、§77）

```text
插件只返回 contribution；注册由 Host adapter 完成（插件不 import interfaces.mcp）
Core 基线不变：23 tools / 13 resources（1 static + 12 template）
disabled 插件的新 lookup 不再返回其贡献
插件工具 / 资源通过 PluginContext（窄上下文）读取数据，不拿 ApplicationServices
```

---

## 12. Plugin config / state / provenance / audit（§26–§30、§54–§56）

```text
config        按 plugin_id 隔离；不得写入 NovelForge 全局 namespace
state         plugins/state/<novel_id>/<plugin_id>/state.json（经 persistence.paths）
              · 只能存 cache / settings / plugin metadata
              · 永远不是 Canon / StoryState / Blueprint / Quality truth
              · 跨插件 / 跨作品不可见
enablement    plugins/enablement.json（approved_version / approved_permissions /
              package_digest / enabled / approved_at）
audit         plugins/audit.json（discovered / approved / enabled / loaded /
              registration failed / disabled / execution_failed）
provenance    plugin_id + plugin_version + plugin_api_version + contribution_id
```

---

## 13. 错误模型（§57–§59）

| 类 | code |
| --- | --- |
| `PluginManifestError` | `PLUGIN_MANIFEST_INVALID` |
| `PluginCompatibilityError` | `PLUGIN_INCOMPATIBLE` |
| `PluginPermissionError` | `PLUGIN_PERMISSION_DENIED` |
| `PluginNotApprovedError` | `PLUGIN_NOT_APPROVED` |
| `PluginLoadError` | `PLUGIN_LOAD_FAILED` |
| `PluginRegistrationError` | `PLUGIN_REGISTRATION_FAILED` |
| `PluginConflictError` | `PLUGIN_REGISTRATION_CONFLICT` |
| `PluginExecutionError` | `PLUGIN_EXECUTION_FAILED` |
| `PluginNotFoundError` | `PLUGIN_NOT_FOUND` |
| `PluginConfigError` | `PLUGIN_CONFIG_INVALID` |

```text
· 运行期异常 → PLUGIN_EXECUTION_FAILED（PluginResult，含 plugin_id + contribution_id）
· 错误信息净化：绝对路径 → <path>，secret 形态 token → <redacted>，绝不返回 traceback
· timeout：in-process 无法安全强杀；V4-09 不假装具备进程级超时隔离（文档明确）
```

---

## 14. Module boundary（§7、§88、§89、§90、§91）

```text
plugins（Platform）
  Allowed    core / persistence.paths（state 路径）/ quality·delivery registry 契约 /
             interfaces.mcp registry 契约；plugins.host 另允许 application.services
  Forbidden  api / ui / ai.providers / BlueprintRepository / QualityStore / DeliveryStore /
             自行拼 story artifact path / fastapi / httpx
core / domain / ai / memory / blueprint / generation / quality / editor / delivery / api
  Forbidden  import novelforge.plugins（Core 不依赖具体插件）
interfaces（api / mcp）
  Forbidden  import novelforge.plugins（只使用注入的 registry）
```

守护测试：`tests/v4/isolation/test_plugin_boundaries.py`（永久）。

---

## 15. Application 门面（§64–§67、§85、§87）

```text
application.services.plugins.PluginService   （接口层唯一入口，不接触 entry point）
  list_plugins / get_plugin / status / contributions / audit / permission_model
  discover / approve / enable / disable

plugins.host.PluginHost                      （composition root；宿主侧）
  discover / load_enabled / services(novel_id) / mcp_dispatcher / status

V4-09 不提供：REST / MCP 的 install / enable / disable 端点、CLI 框架、marketplace
```

---

## 16. 测试与验收

```text
tests/plugins/test_plugin_contracts.py        契约 / 状态机 / 错误码 / Public Contract
tests/plugins/test_plugin_discovery.py        discovery ≠ load / 不扫描目录 / 无隐式加载
tests/plugins/test_plugin_compatibility.py    兼容性 / 不兼容不执行 / 降级启动
tests/plugins/test_plugin_lifecycle.py        生命周期 / 失败隔离 / 重启恢复
tests/plugins/test_plugin_permissions.py      权限升级 / 越权贡献 / 最小权限上下文
tests/plugins/test_plugin_registration.py     原子注册 / Core 不可覆盖 / reserved namespace
tests/plugins/test_plugin_exporter.py         §95 golden（仍走 Delivery 安全链）
tests/plugins/test_plugin_quality.py          §96 golden（namespaced + 默认 non-blocking）
tests/plugins/test_plugin_mcp.py              §97 golden（23 tools / 13 resources 不受影响）
tests/plugins/test_plugin_state.py            §29 / §30 / §99（隔离 / 非 story truth）
tests/plugins/test_plugin_security.py         §100（无 secret / 无 traceback / 无私有路径）
tests/plugins/test_application_plugin_service.py   应用门面
tests/v4/isolation/test_plugin_boundaries.py  永久模块边界守卫
```
