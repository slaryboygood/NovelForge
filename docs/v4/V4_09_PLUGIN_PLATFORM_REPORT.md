# NovelForge V4-09 PLUGIN PLATFORM RESULT

> 阶段：**V4-09 Plugin Platform**
> 状态：**PASS**
> 日期：2026-09-18
> 契约：`docs/v4/V4_PLUGIN_CONTRACT.md`（SSOT）；盘点：`docs/v4/V4_09_PLUGIN_EXTENSION_INVENTORY.md`
> 分支：`v4-09-plugin-platform`（integration；基线 = V4-08 头 `30d909e`）

---

## 1. Extension point inventory

编码前完成 `docs/v4/V4_09_PLUGIN_EXTENSION_INVENTORY.md`：盘点 6 个 registry /
extension-like 机制，判定 3 类可安全开放（exporter / quality evaluator / MCP tool·resource）、
4 类必须 DEFER（generation / provider / memory / editor mutation）、
8 项内部能力绝不能作为 Plugin API（repository / store / provider / persistence /
ApplicationServices 等）。

```text
开放     delivery.ExporterRegistry / quality.EvaluatorRegistry /
         interfaces.mcp MCPToolRegistry / MCPResourceRegistry
需要 Adapter  4 个（ExporterAdapter / QualityEvaluatorAdapter / McpAdapter(tool, resource)）
DEFER   generation task 扩展、provider 插件、memory 插件、editor mutation、
        网络代理、untrusted sandbox、marketplace、hot reload、REST/MCP 上的 enable 端点
```

## 2. Plugin architecture

```text
Plugin Package → Manifest → Compatibility → Approval → Permission → Contribution
→ Host Adapter → Existing Registry → Existing Business Pipeline
```

```text
src/novelforge/plugins/
├── __init__.py          Public Contract（52 symbols，只有契约，无 composition）
├── contracts.py         PLUGIN_API_VERSION / statuses / transitions / permissions /
│                        PluginManifest / PluginDescriptor / PluginContribution /
│                        PluginConfig / PluginResult
├── errors.py            PluginError 家族（稳定 code）+ redact_message
├── discovery.py         entry_points / 显式 manifest 路径（manifest only，不执行代码）
├── compatibility.py     API 版本 / capability / min_host_version 判定
├── permissions.py       白名单 / 批准 / 权限差异 / 重新批准判定
├── registry.py          PluginRecord / PluginRegistry（owner 可追踪、状态机查询）
├── lifecycle.py         状态机唯一 SSOT（can_transition / lifecycle_table）
├── state.py             EnablementStore / PluginStateStore / PluginAuditLog
├── manager.py           PluginManager（发现 / 批准 / 启用 / 加载 / 执行 / 禁用）
├── host.py              PluginHost（composition root；唯一接触 application + interfaces）
├── sdk/                 插件作者唯一稳定依赖（contracts / context / quality）
└── adapters/            exporter / quality / mcp（Host 侧注册）
```

## 3. Public Plugin SDK

`novelforge.plugins.sdk`（= `PLUGIN_SDK_VERSION` 1）：

```text
Contribution / exporter_contribution / quality_contribution /
mcp_tool_contribution / mcp_resource_contribution / quality_issue /
PluginContext / PluginAIClient / PLUGIN_SDK_VERSION / PERMISSIONS / CONTRIBUTION_KINDS
```

`PluginContext` 是 capability-scoped least privilege：`require()` 门禁 +
`get_config()` / `load_state()` / `save_state()` / `blueprint_view()` / `ai()`；
**不暴露** repository / store / persistence / provider / ApplicationServices。
守护：`test_sdk_is_the_stable_plugin_boundary` + `test_fixture_plugins_only_import_sdk_and_stdlib`。

## 4. Plugin manifest

`PluginManifest`（13 字段）：plugin_id / name / version / plugin_api_version /
description / entry_point / capabilities / permissions / configuration_schema /
host_compatibility / author / homepage / package_digest；`digest` 用于识别内容变化。
XML-free 结构化 JSON（`novelforge-plugin.json` distribution metadata 或显式 manifest 路径）。

## 5. Plugin API version

```text
PLUGIN_API_VERSION = 1（独立于 MCP_INTERFACE_VERSION=1 / BLUEPRINT_SCHEMA_VERSION /
DELIVERY_SCHEMA_VERSION）
plugin_api_version <  host → 兼容（旧插件仍可用）
plugin_api_version == host → 兼容
plugin_api_version >  host → PLUGIN_INCOMPATIBLE（不执行）
显式 0 / 非法值 → PLUGIN_MANIFEST_INVALID（不被默认值静默替换）
```

## 6. Discovery

```text
来源 ① importlib.metadata.entry_points(group="novelforge.plugins")（读 .dist metadata）
来源 ② host 显式 manifest 路径（extra）
discover() 只产出 PluginDescriptor（manifest + source + locator + digest + compatibility）
不执行插件代码（测试断言 fixture 模块未被 import）
不扫描 project/plugins/*.py（测试放置 evil_plugin.py 验证不被加载）
不做远程 marketplace / 自动安装（源码守卫：无 urllib / httpx / requests / subprocess / pip）
```

## 7. Compatibility

`check_compatibility`：API 版本 + capability 支持 + `min_host_version`；
发现阶段即标注 status = compatible / incompatible；不兼容插件既不能 approve
也不能 enable，且已 enable 的插件在宿主升级后**降级启动**（plugin failed，应用不崩）。

## 8. Trust model

```text
TRUST_MODEL = trusted_in_process
V4-09 只执行用户显式批准的 trusted 插件（in-process）；
permission = Host API capability governance，**不是** Python / OS sandbox；
untrusted 插件的进程级隔离（sandbox）不在本阶段实现。
```

`TRUST_MODEL_NOTE` / `permission_note()` / `PluginService.permission_model()` 三处
对 UI / MCP / 运维公开同一诚实声明（ADR-030）。

## 9. Permission model

```text
白名单（8）：delivery.export ✅ / quality.evaluate ✅ / mcp.extend ✅ / plugin.state ✅ /
             blueprint.read ✅（MCP 上下文）/ ai.invoke（声明 + 门禁）/
             editor.mutate（仅声明）/ network.request（仅声明）
```

`PluginContext.require()` 拒绝未批准 capability；manifest 声明未知 permission →
`PLUGIN_MANIFEST_INVALID`；contribution 要求超出批准集合 → `PLUGIN_PERMISSION_DENIED`（§92 fixture）。

## 10. Approval / enablement

`EnablementStore`（`plugins/enablement.json`）记录 plugin_id / approved_version /
approved_permissions / package_digest / approved_by / approved_at / enabled。
只保存 `enabled=true` 不足以审计，因此 version + permission 集合 + digest 一并落盘。

## 11. Lifecycle

9 个状态（`discovered / compatible / incompatible / approved / enabled / loaded /
active / disabled / failed`），流转表 = `PLUGIN_TRANSITIONS`（唯一 SSOT，测试核对
`lifecycle_table()`）；未引入 `quarantined`（不做过度设计）。

```text
discover → approve → enable(=enable+load) → active → disable（逻辑禁用 + 卸载贡献）
失败 → failed（error_code 记录，可再次 approve / enable）
```

## 12. Plugin registry

`PluginRegistry`：`list_discovered` / `list_enabled` / `get` / `find` / `status` /
`contributions(type=, plugin_id=)` / `set_status` / `owners`；重复 plugin_id 且 manifest
不同 → `PLUGIN_REGISTRATION_CONFLICT`；相同 manifest 重复发现幂等。

## 13. Contribution model

```text
PluginContribution：type / contribution_id / version / permissions_required / factory / metadata
SDK Contribution.as_host_contribution() 完成转换（插件不接触 Host 类型）
4 种 type：exporter / quality_evaluator / mcp_tool / mcp_resource
namespaced id：plugin.<plugin_id>.<contribution_id>
```

## 14. Atomic registration

`PluginManager._register` 顺序注册 + 异常回滚（`_unregister` 调用所有 adapter 的
`unregister_owner`）。测试用「第 1 个贡献合法（format=poly）+ 第 2 个与 Core MCP tool
同名」的插件验证：`error_code=PLUGIN_REGISTRATION_CONFLICT`、exporter registry 回到
Core 4 项、MCP 仍 23 tool —— **不留半激活**（§49）。

## 15. Exporter extension

```text
插件注册 ExporterSpec(owner_type="plugin", owner_id=plugin_id)；
format 与 Core 不同（Core 不可覆盖）；同 owner 重复注册 = 更新自己的 handler
输入 = 已选定交付上下文（compiled blueprint），不参与 selection / quality / review 决策
仍经过 Delivery preflight → post-build 校验 → secret scan → path validation →
manifest → checksum（插件不能绕过 DeliveryValidator）
DeliverySelection.accepted_formats（构造期校验）允许选择插件 format，不参与 digest
```

Golden 测试（§95）覆盖：discover → approve → enable → load → DeliveryService 交付
`tlist` → artifact bytes + `exporter_id=plugin.com.example.exporter.text-list` +
checksum 与 `sha256_hex(content)` 一致 + manifest 记录 `owner_type=plugin` +
post-validation ok + `manifest.json` 落盘的 checksum 与 artifact 一致。
另测：插件输出 `API_KEY=…` / `Authorization: Bearer …` → **交付被阻断、不发布 artifact**。

## 16. Quality evaluator extension

```text
插件贡献 EvaluatorSpec（gate 由贡献声明）；执行顺序 / policy / gate / evidence / report
仍由 QualityService 负责；插件 issue code 必须 plugin.<plugin_id>.CODE（禁止 Core code）
默认不参与：QualityPolicy.plugin_evaluator_ids 显式列出才运行
默认 non-blocking：QualityPolicy.plugin_blocking=False → 只出现在 report，不改判定
provenance：owner_type=plugin + plugin_id + plugin_evaluator_version
只读：不修改 Blueprint / Canon / StoryState，不调用 RepairExecutor
disable → unregister_plugin_codes（namespaced code 注销，Core code 不受影响）
```

Golden 测试（§96）：policy 未启用 → 插件 evaluator 不运行；启用 → Q8 出现
`plugin.com.example.qualitycheck.CHAPTER_MISSING_POV`、Q8 status 仍 passed、
report.status = passed（non-blocking），issue 带 plugin provenance 且已持久化。

## 17. MCP extension

```text
tool      name → plugin.<plugin_id>.<name>；与 Core 名称冲突即拒绝
resource  URI → novelforge://plugins/<plugin_id>/<path>；kind = plugin_resource:<plugin_id>
插件 handler 收到的是 PluginContext（窄上下文），不是 ApplicationServices
Core 基线：23 tools / 13 resources（1 static + 12 template）不受影响
disable → 卸载 tool + resource；新 lookup 不再命中（read_resource → MCP_RESOURCE_NOT_FOUND）
```

Golden 测试（§97）：`dispatcher.tools.names()` 出现 namespaced tool（24）、
`invoke_tool` 成功且返回 `node_count`、`read_resource` 读到插件资源、
`parse_uri` 解析新 URI、disable 后 tool / resource 消失且 Core 计数不变。

## 18. AI / network capability policy

```text
ai.invoke     声明式 permission + PluginContext.ai() 门禁；Host 未注入能力时
              PLUGIN_PERMISSION_DENIED（不会静默返回空）。插件不得直接 import
              ai.providers（边界守卫禁止），不得绕 Gateway（ADR-012）
network.request  仅声明（DEFER）：没有进程隔离时不承诺"阻止联网"
```

## 19. Plugin config

`PluginConfig(plugin_id, values)`：按 plugin_id 隔离，`PluginContext.get_config()`
提供只读视图（可注入 validator）；插件不能把字段写进 NovelForge 全局 namespace。
本轮不提供 config 写入 API（避免在没有 UI / 审批的情况下扩大面），保留契约位。

## 20. Plugin state

```text
路径    novel/authoring/story_engine/plugins/state/<novel_id>/<plugin_id>/state.json
        （经 persistence.paths.plugin_state_dir；ARTIFACT_KINDS += plugin_state）
隔离    跨插件不可见 / 跨作品不可见（测试验证）
语义    只存 cache / settings / plugin metadata，永远不是 Canon / StoryState /
        Blueprint / Quality truth（测试断言路径不含 blueprint/canon/quality/delivery）
权限    读写需要 plugin.state；未批准 → PLUGIN_PERMISSION_DENIED
```

## 21. Provenance / audit

```text
provenance  PluginResult.provenance = plugin_id + plugin_version +
            plugin_api_version + contribution_id
            plugin QualityIssue.provenance 另带 owner_type / plugin_id /
            plugin_evaluator_version（历史结果不被新版本冒名）
audit       plugins/audit.json：discovered / approved / enabled / loaded / failed /
            execution_failed / disabled（含 plugin_id / version / status /
            error_code / timestamp / extra；永不写 secret）
```

## 22. Failure isolation

```text
加载失败（register 抛错）    → status=failed / PLUGIN_LOAD_FAILED；Core 与其他插件继续
注册冲突                   → PLUGIN_REGISTRATION_CONFLICT（原子回滚）
运行期崩溃                 → PluginResult(ok=False, PLUGIN_EXECUTION_FAILED)
宿主启动时 enabled 不兼容   → 降级启动：该 plugin failed，应用 / MCP / Delivery 正常
```

## 23. Disable / upgrade semantics

```text
disable      逻辑禁用 + 按 owner 卸载贡献 + enablement.enabled=false +
             restart_required=false（不 unload Python module；不做 hot reload）
upgrade      不自动升级 package；检测 manifest version / permission / package_digest 变化
             → 需要重新批准（PLUGIN_PERMISSION_DENIED / PLUGIN_NOT_APPROVED）
restart      宿主重启时 load_enabled() 重新加载 enabled 插件（重新 discovery + enable）
```

## 24. Security model

```text
· 默认不执行未批准插件（未批准 → 不 import，测试断言模块不在 sys.modules）
· 不扫描任意 project 目录、不递归找 *.py、不自动 pip install / 下载 / 升级
· 错误信息净化：绝对路径 → <path>，secret 形态 → <redacted>，截断 300 字符，
  不返回 traceback
· 交付物 secret scan 同样作用于插件 artifact（§34）
· permission ≠ OS sandbox（三处 API + 文档明确）
```

## 25. Ownership isolation

```text
state / operation 按 (novel_id, plugin_id) 隔离；Plugin A 读不到 Plugin B 的 state，
也读不到其他作品的 state（测试验证）
registry 项带 owner（core|plugin + owner_id）→ disable 只影响该插件
plugin state 写盘后不影响任何 story truth 文件（测试断言）
```

## 26. Application PluginService

```text
application.services.plugins.PluginService（接口层唯一入口；不接触 entry point）
  list_plugins / get_plugin / status / contributions / audit / permission_model
  discover / approve / enable / disable
plugins.host.PluginHost（宿主侧 composition root）
  discover / load_enabled / services(novel_id) / mcp_dispatcher / status
```

修正的结构问题：composition root 不能放在 `application`（该层禁止 import
`interfaces`），因此 PluginHost 落在 `plugins/host.py`，
`application.services.plugins` 只保留纯门面（边界测试验证）。

## 27. Module boundary verification

`tests/v4/isolation/test_plugin_boundaries.py`（12 项，永久）：plugins ✗ api / ui /
ai.providers / repository / store / 自拼路径 / HTTP client；只有 `plugins/host.py`
可接触 application 层且不构造业务对象；core / domain / ai / memory / blueprint /
generation / quality / editor / delivery / api / interfaces ✗ import `novelforge.plugins`；
plugins 顶层只 import 协议契约；fixture 插件只依赖 SDK；SDK 不暴露 Repository / Store /
Provider / ApplicationServices / PluginManager / PluginHost。

## 28. Tests

```text
tests/plugins/**                    87 tests
  test_plugin_contracts.py           17
  test_plugin_discovery.py           11
  test_plugin_compatibility.py        7
  test_plugin_lifecycle.py            8
  test_plugin_permissions.py          8
  test_plugin_registration.py         6
  test_plugin_exporter.py             4   §95 golden
  test_plugin_quality.py              6   §96 golden
  test_plugin_mcp.py                  6   §97 golden
  test_plugin_state.py                6
  test_plugin_security.py             4   §100
  test_application_plugin_service.py  7
tests/v4/isolation/test_plugin_boundaries.py  12
合计 +99
```

结果：

```text
pytest -q tests/plugins tests/v4                                     199 passed
pytest -q tests/plugins tests/v4/isolation/test_plugin_boundaries.py  99 passed
pytest -q tests/mcp tests/editor                                     158 passed
pytest -q tests/delivery tests/quality                               182 passed
pytest -q tests/test_v2_frozen_guard.py tests/test_v3_frozen_guard.py  12 passed
python scripts/validate_project.py                                   PASS
```

## 29. Impact-based validation

```text
§101 影响面测试（默认，不跑完整 pytest）
  · tests/plugins + tests/v4                 ✅ 199 passed
  · 修改 MCP registry        → tests/mcp     ✅ 158 passed（与 editor 同批）
  · 修改 ExporterRegistry    → tests/delivery ✅ 182 passed（与 quality 同批）
  · 修改 Quality Registry    → tests/quality  ✅ 同批
  · frozen guards + validate_project          ✅

§102 Full regression gate
  Full regression: NOT REQUIRED — impact-based validation sufficient.
  理由：未改 requirements / 依赖环境（MCP SDK 区间保持 V4-08 冻结值），
        未改 core / Blueprint schema / shared persistence semantics / 测试基础设施。
        改动集中在 plugins（新模块）+ 三个 registry 的 additive ownership 语义，
        已由对应套件逐个覆盖。
```

## 30. Frozen boundary

```text
novelforge-product-v3-final tag        未移动（f21464713e4786410e5550a7ad5504692cc644dd）
novel/authoring frozen digest          未修改（插件数据目录默认 gitignored）
story_engine/repair.py                 未改
REPAIR_GATE_V1 / Repair Contract       未改
Canon / StoryState 语义                未改（plugins 无写入口，守卫覆盖）
novel/final/** 与 wasteland exports    未恢复
冻结的 V4-07/V4-05/V4-08 契约          只做 additive 扩展（已在契约文件登记）
```

## 31. Files created

```text
src/novelforge/plugins/__init__.py
src/novelforge/plugins/contracts.py
src/novelforge/plugins/errors.py
src/novelforge/plugins/discovery.py
src/novelforge/plugins/compatibility.py
src/novelforge/plugins/permissions.py
src/novelforge/plugins/registry.py
src/novelforge/plugins/lifecycle.py
src/novelforge/plugins/state.py
src/novelforge/plugins/manager.py
src/novelforge/plugins/host.py
src/novelforge/plugins/sdk/__init__.py
src/novelforge/plugins/sdk/contracts.py
src/novelforge/plugins/sdk/context.py
src/novelforge/plugins/sdk/quality.py
src/novelforge/plugins/adapters/__init__.py
src/novelforge/plugins/adapters/exporter.py
src/novelforge/plugins/adapters/quality.py
src/novelforge/plugins/adapters/mcp.py
src/novelforge/application/services/plugins.py
tests/plugins/conftest.py
tests/plugins/plugins_support.py
tests/plugins/test_plugin_contracts.py
tests/plugins/test_plugin_discovery.py
tests/plugins/test_plugin_compatibility.py
tests/plugins/test_plugin_lifecycle.py
tests/plugins/test_plugin_permissions.py
tests/plugins/test_plugin_registration.py
tests/plugins/test_plugin_exporter.py
tests/plugins/test_plugin_quality.py
tests/plugins/test_plugin_mcp.py
tests/plugins/test_plugin_state.py
tests/plugins/test_plugin_security.py
tests/plugins/test_application_plugin_service.py
tests/plugins/fixtures/example_exporter_plugin.py
tests/plugins/fixtures/example_quality_plugin.py
tests/plugins/fixtures/example_mcp_plugin.py
tests/plugins/fixtures/broken_plugin.py
tests/plugins/fixtures/conflict_plugin.py
tests/plugins/fixtures/partial_conflict_plugin.py
tests/plugins/fixtures/permission_plugin.py
tests/plugins/fixtures/crashing_export_plugin.py
tests/plugins/fixtures/leaky_plugin.py
tests/plugins/fixtures/secret_export_plugin.py
tests/v4/isolation/test_plugin_boundaries.py
docs/v4/V4_09_PLUGIN_EXTENSION_INVENTORY.md
docs/v4/V4_PLUGIN_CONTRACT.md
docs/v4/V4_09_PLUGIN_PLATFORM_REPORT.md
docs/v4/adr/ADR-029-plugins-use-explicit-public-extension-points.md
docs/v4/adr/ADR-030-v4-09-executes-only-explicitly-approved-trusted-plugins.md
docs/v4/adr/ADR-031-plugin-contributions-cannot-override-core-registrations.md
```

## 32. Files modified

```text
src/novelforge/persistence/paths.py            plugin_state 路径 + ARTIFACT_KINDS
src/novelforge/persistence/__init__.py         导出 plugin 路径函数
src/novelforge/delivery/exporters/__init__.py  ExporterSpec owner + 不可覆盖 + unregister_owner
src/novelforge/delivery/contracts.py           DeliverySelection.accepted_formats（构造期校验）
src/novelforge/delivery/service.py             插件 artifact 同样过 secret scan
src/novelforge/quality/registry.py             EvaluatorSpec owner + owner 冲突 + unregister_owner
src/novelforge/quality/codes.py                plugin issue code 注册表（namespaced）
src/novelforge/quality/contracts.py            QualityPolicy.plugin_evaluator_ids / plugin_blocking
src/novelforge/quality/service.py              plugin provenance + 默认 non-blocking 判定
src/novelforge/interfaces/mcp/contracts.py     ToolSpec / ResourceSpec owner
src/novelforge/interfaces/mcp/registry.py      unregister_owner / core_names / core_uris / owners
src/novelforge/interfaces/mcp/uri.py           novelforge://plugins/... + plugin_resource kind
src/novelforge/application/services/facade.py  application_services(exporter_registry=, evaluator_registry=)
src/novelforge/application/services/export.py  ExportService(exporter_registry=) + accepted_formats
src/novelforge/application/services/__init__.py  导出 PluginService
docs/v4/V4_PLUGIN_SPEC.md                      降级为设计输入
docs/v4/V4_MODULE_BOUNDARIES.md                plugins 模块 + §3.16 + 明文禁令
docs/v4/V4_ARCHITECTURE.md                     plugins 行 / 依赖矩阵 / 明文禁令
docs/v4/V4_BRANCH_STRATEGY.md                  V4-09 任务分支行
docs/v4/V4_DELETION_PLAN.md                    V4-09 评估（无删除）
docs/v4/V4_ARCHITECTURE_RISKS.md               R-12 缓解状态
docs/v4/V4_MCP_CONTRACT.md                     V4-09 additive 扩展说明
docs/v4/V4_DELIVERY_CONTRACT.md                V4-09 additive 扩展说明
docs/v4/adr/README.md                          ADR-029/030/031 登记
```

## 33. Files deleted

```text
（无）插件平台为纯 additive 扩展；未删除任何既有文件与 release artifact。
```

## 34. Git branch

```text
v4-09-plugin-platform（integration branch，单 Agent 顺序执行）
基线：v4-08-mcp-server = 30d909e（V4-08 head）
附带修正：V4-08 的提交此前落在 v4-07-delivery-export（分支未切出），
已建立 v4-08-mcp-server 指向 30d909e，V4-09 从该点开始。
```

## 35. Git commits

```text
（1）docs(v4): freeze plugin platform contracts
（2）feat(plugins): add manifest discovery and compatibility
（3）feat(plugins): add approval lifecycle permissions and state
（4）feat(plugins): add contribution registry and host adapters
（5）feat(plugins): add exporter quality and mcp extension points
（6）feat(application): expose plugin management service
（7）test(plugins): add lifecycle permission and isolation coverage
（8）test(v4): enforce plugin module boundaries
（9）docs(v4): record v4-09 result
```

## 36. Remaining risks

| 风险 | 状态 | 说明 |
| --- | --- | --- |
| in-process trusted 插件仍可绕过 permission | **设计约束（已声明）** | permission 是 Host API capability governance；进程级 sandbox 未实现（ADR-030、契约 §6） |
| 无进程级 timeout / 强杀 | 已知 | heavy exporter / AI 调用可能长时间占用；文档明确限制（§59），不假装具备隔离 |
| restart 后不做热重载 | 已知 | enablement 记录 enabled 的插件在宿主启动时重新加载；版本变化需重新批准 |
| 插件 config 写入 API 未提供 | DEFER | 契约位保留（`PluginConfig` + validator）；等 UI / 审批面（V4-10） |
| `accepted_formats` 的注入面 | 已知 | 只有注入 registry 的 `ExportService` 能选择插件 format；直接用 `DeliverySelection` 的调用方仍只见 Core 格式 |
| 插件 MCP tool 的 AI / 网络能力 | DEFER | `ai.invoke` / `network.request` 只声明；Host 能力接入留给后续阶段 |
| 外部插件包（真实第三方 distribution）联调 | 未执行 | 本环境没有已安装第三方插件 distribution；discovery 用 FakeEntryPoint + `.dist.read_text` 元数据 + 显式 manifest 路径全覆盖 |
| UI / REST 暴露插件管理 | 本阶段不做 | §65–§67：enable / disable 是安全敏感操作，先只给 Application 门面 + operator |

## 37. V4-10 readiness

```text
[x] plugins 是独立模块（Public Contract + 独立测试 + 独立任务分支 + 契约文档）
[x] Plugin SDK 是稳定最小边界（fixture 插件只依赖 SDK + stdlib，有守卫）
[x] Core 不依赖 concrete plugins（core/domain/ai/memory/blueprint/generation/quality/
    editor/delivery/api/interfaces 全部 guard）
[x] discovery ≠ load；不执行插件代码；不扫描目录；无隐式加载；无远程安装
[x] 生命周期 / 原子注册 / 失败隔离 / 降级启动完整
[x] permission 白名单 + 批准记录 + 升级重新批准 + 最小权限上下文
[x] 三类扩展点（exporter / quality evaluator / MCP tool·resource）golden 测试通过
[x] Core 注册不可覆盖；disable 后贡献不再暴露
[x] plugin state 按 (novel, plugin) 隔离，且非 story truth
[x] 无 secret / traceback / 私有路径泄漏；错误码稳定
[x] PluginService 已为 UI 提供 §87 所需字段（name / id / version / capabilities /
    permissions / status / compatibility / error）
[x] 浏览器 / 外部插件联调留给部署环境（本阶段无第三方 distribution 可装）

V4-10（UI）可直接消费：
  PluginService.list_plugins() / get_plugin() / status() / permission_model()
  PluginHost.status()（registry owners / MCP 计数 / trust model）
```

---

```text
V4-09 = PASS
```
