# NovelForge V4-09 — Plugin Extension Point Inventory

> 状态：**V4-09 Plugin Platform 盘点（编码前完成）**
> 依据：`docs/v4/V4_PLUGIN_SPEC.md`（设计输入）、`docs/v4/V4_MODULE_BOUNDARIES.md` §3.11–§3.15、
> V4-07 `ExporterRegistry` / V4-05 `EvaluatorRegistry` / V4-08 `MCPToolRegistry` / `MCPResourceRegistry`
> 结论：本文件是 `docs/v4/V4_PLUGIN_CONTRACT.md` 的输入；契约以 Contract 为准。

---

## 1. 哪些能力已经存在 Registry

| Registry | 位置 | 注册项 | 已有能力 | V4-09 前的问题 |
| --- | --- | --- | --- | --- |
| `ExporterRegistry` | `src/novelforge/delivery/exporters/__init__.py` | `ExporterSpec` + `ExporterFn` | format 查表 / profile 过滤 / specs / formats | 无 owner 概念；重复注册 `last wins`（会静默覆盖 Core） |
| `EvaluatorRegistry` | `src/novelforge/quality/registry.py` | `EvaluatorSpec` + evaluator fn | `for_gate(gate, policy=)` / gates / evaluators | 无 owner；插件 evaluator 无法与 Core 区分；无 policy 开关 |
| `MCPToolRegistry` | `src/novelforge/interfaces/mcp/registry.py` | `ToolSpec` + handler | name 查表（重复即 `ValueError`）/ names / specs | 无 owner；无按 owner 卸载 |
| `MCPResourceRegistry` | 同上 | `ResourceSpec` + handler（按 `kinds` 分派） | `resolve(target)` / static / template specs | 无 owner；URI 形状表里没有插件 namespace |
| `Generation` task registry | `src/novelforge/generation/` | task id → task 实现 | 结构化任务（premise / world / character / …） | 任务表是代码常量，不是可注册对象 |
| `ApplicationServices` | `src/novelforge/application/services/facade.py` | 能力束 | per-novel 业务入口 | 不是 registry：把它交给插件等于交出全部业务能力 |

---

## 2. 哪些 Registry 可以安全开放

```text
开放（V4-09 落地）
  delivery.ExporterRegistry      → ExporterAdapter（§32–§34）
  quality.EvaluatorRegistry      → QualityEvaluatorAdapter（§35–§37）
  interfaces.mcp.MCPToolRegistry → McpAdapter.register_tool（§38–§42）
  interfaces.mcp.MCPResourceRegistry → McpAdapter.register_resource

开放的前提（全部满足）
  · 只是"追加"：插件不能覆盖 / 修改 Core 注册（§40、§77、§78、§90）
  · 贡献名 namespaced（plugin.<plugin_id>.<id>）
  · 注册项带 owner（owner_type=core|plugin + owner_id）→ 可按插件卸载（§75）
  · 注册是原子的：任一贡献失败 → 整体回滚（§49）
```

---

## 3. 哪些内部能力绝不能作为 Plugin API

```text
✗ BlueprintRepository        （直接写 story truth；必须经 Host 的窄只读视图）
✗ QualityStore               （质量结论属于 Core；插件只能"追加 finding"）
✗ EditorStore / EditorService（append-only revision 语义必须由 Host 保证）
✗ DeliveryStore / DeliveryService（选择 / 校验 / 打包由 Host 决定）
✗ story_engine（frozen domain）、story_builder（legacy 产品面）
✗ ai.providers / 任何 HTTP client（插件不得直接调模型或联网，§45–§47）
✗ persistence.paths.project_root（插件不得自己拼路径，§28）
✗ ApplicationServices 全对象（§24：最小权限，禁止一次性交出全部业务能力）
✗ Canon / StoryState 写入口（§37、§82、§83）
```

---

## 4. 哪些扩展点需要 Adapter

```text
ExporterAdapter          插件返回 contribution → Host 校验 → ExporterRegistry.register(spec, fn)
QualityEvaluatorAdapter  插件返回 contribution → Host 注册 issue code（namespaced）→ EvaluatorRegistry
McpAdapter               tool：插件名 → plugin.<plugin_id>.<name>，Core 名称冲突即拒绝
                         resource：URI → novelforge://plugins/<plugin_id>/<path>，
                         kind = plugin_resource:<plugin_id>（按插件精确分派）
```

Adapter 是**唯一**允许触碰 registry 的地方（§71）：插件只返回 `Contribution`，
不拿 registry、不拿 project_root。

---

## 5. 哪些能力应该 defer

| 能力 | 处理 | 原因 |
| --- | --- | --- |
| Generation / Prose task 插件（`ProseDraftPlugin`） | **DEFER** | 正文写作不是 V4 Core 产品（ADR-011）；V4-09 不开 generation 扩展点 |
| Provider / 模型插件 | **DEFER** | 模型入口唯一 = `ai.gateway`（ADR-012）；插件经 Host `ai.invoke` 窄能力，不直连 |
| Memory / retrieval 插件 | **DEFER** | memory 是派生视图；开放会破坏 truth precedence |
| Editor mutation 插件 | **DEFER**（只声明 `editor.mutate` permission） | append-only + approval 语义必须由 Host 保证（V4-06） |
| 网络代理 / Host HTTP capability | **DEFER**（只声明 `network.request`） | 没有进程级隔离时无法诚实承诺"阻止联网"（§47） |
| Untrusted plugin sandbox | **DEFER** | V4-09 只执行显式批准的 trusted in-process 插件（§21、§60） |
| Plugin marketplace / 自动安装 / 自动升级 | **明确不做**（§16） | 安装属于宿主 / 部署环境 |
| Hot reload / runtime unload Python module | **DEFER** | 逻辑 disable + restart host（§50–§51） |
| REST / MCP 上的 install / enable / disable | **DEFER** | 安全敏感操作先只做 Application Service + operator 显式调用（§65–§67） |

---

## 6. Core ↔ 插件 依赖方向（V4-09 落地前确认）

```text
允许：plugins.host（composition root）→ application.services / delivery registry /
      quality registry / interfaces.mcp registry
允许：plugins → core（ids / errors）、persistence.paths（插件状态路径 SSOT）
禁止：delivery / quality / generation / editor / blueprint / interfaces.mcp
      → novelforge.plugins（Core 不得知道任何具体插件，§7、§88）
禁止：plugins → api / ui / ai.providers / BlueprintRepository / QualityStore /
      DeliveryStore / 自行拼 story artifact 路径（§88）
```

守护测试：`tests/v4/isolation/test_plugin_boundaries.py`（永久）。
