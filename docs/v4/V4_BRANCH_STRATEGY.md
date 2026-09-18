# NovelForge V4 — Branch Strategy

> 状态：**V4-01 Boundary Foundation**
> 依据：`docs/NOVELFORGE_V4_MASTER_PLAN.md` §12–13、§42、§43；`docs/v4/V4_MODULE_BOUNDARIES.md`

---

## 1. 为什么不用 `v4/...` 层级分支

```text
远端已存在 origin/v4（V4 集成分支，当前与 main 同一 commit）。
Git ref 不能同时存在 refs/heads/v4 与 refs/heads/v4/<name>（文件 / 目录冲突）。

→ V4 全部阶段使用扁平命名：v4-NN-<module>-<topic>
```

历史事实：V4-00 期间曾创建 `v4/00-architecture`（当时通过删除本地 `v4` 引用实现，
`origin/v4` 未受影响）。V4-01 起统一使用扁平命名。

---

## 2. 分支命名表

| 阶段 | 主模块 | 分支 |
| --- | --- | --- |
| V4-01 | Boundary | `v4-01-boundary-foundation`（当前） |
| V4-02 | LLM | `v4-02-llm-gateway` |
| V4-03 | Memory | `v4-03-memory-canon`、`v4-03-memory-context-builder` |
| V4-04 | Blueprint | `v4-04-blueprint-generation` |
| V4-05 | Quality | `v4-05-quality-loop`（integration，单 Agent 顺序执行；§3 允许的方式） |
| V4-06 | Editor | `v4-06-blueprint-editor`（integration，单 Agent 顺序执行） |
| V4-07 | Delivery | `v4-07-delivery-export`（integration，单 Agent 顺序执行） |
| V4-08 | MCP | `v4-08-mcp-server`（integration，单 Agent 顺序执行） |
| V4-09 | Plugins | `v4-09-plugin-platform`（integration，单 Agent 顺序执行） |
| V4-10 | UI | `v4-10-ui` |
| V4-11 | Agent | `v4-11-agent` |

跨模块集成使用短生命周期分支：

```text
v4-int-memory-blueprint
v4-int-quality-repair
v4-int-mcp-services
```

---

## 3. 每个任务分支开始前必须声明

```text
Primary Module        主模块（一个）
Primary Paths         主要维护路径
Allowed Shared Paths  允许同时触碰的共享路径（越少越好）
Forbidden Paths       明确禁止触碰的路径（含 frozen truth）
Required Contracts    依赖 / 需要修改的 Contract
Expected Tests        预期新增或运行的测试
```

模板：

```text
Module   : ai
Primary  : src/novelforge/ai/**
Shared   : docs/v4/V4_LLM_CONTRACT.md
Forbidden: src/novelforge/story_engine/canon/**, tests/test_v2_frozen_guard.py,
           docs/FROZEN_EVIDENCE_MANIFEST.json, novel/authoring/**
Contracts: GenerationContract / ModelPolicy（新增）
Tests    : tests/test_ai_gateway.py, tests/test_ai_provider_offline.py
```

### 3.1 已登记的任务分支声明

| Branch | Module | Primary Paths | Shared / Allowed | Forbidden | Contracts | Tests |
| --- | --- | --- | --- | --- | --- | --- |
| `v4-01-boundary-foundation` | `boundary` | `src/novelforge/{persistence,application,core,legacy}/**` | `api/story_builder_routes.py`、`story_builder/{export_package,writer_integration,inspector,ui_flow,v3_projection,novel_admin}.py`、`tests/**`、`docs/**` | frozen 历史模块内部实现、`novel/authoring/**`、release tag | `ArtifactContext` / `RevisionRef` / `LegacyManifest`（新增） | `tests/v4/**` |
| `v4-02-llm-gateway` | `ai` | `src/novelforge/ai/**` | `core`（revision/ids 复用）、`observability/model_trace.py`、`application/services/utility.py`、`story_engine/spec/llm.py`（仅 compatibility 适配）、`tests/ai/**`、`tests/v4/isolation/test_module_boundaries.py`、`docs/v4/**` | `story_engine` 其余部分、`persistence`、`api`、UI、frozen 模块内部实现 | `LLMContract` / `ModelPolicy` / `LLMProvider` / `LLMResult`（新增） | `tests/ai/**`、`tests/v4/isolation/test_module_boundaries.py` |
| `v4-03-memory-integration` | `memory` | `src/novelforge/memory/**` | `persistence/paths.py`（新增 memory 路径，唯一路径来源）、`tests/memory/**`、`tests/v4/isolation/**`、`docs/v4/**` | `story_engine` 内部实现、`ai`、`api`、UI、`novel/final` 与 570 章 historical（已删除） | `MemoryQuery` / `MemoryResult` / `MemoryItem` / `ContextRequest` / `ContextBundle`（新增） | `tests/memory/**`、`tests/v4/isolation/test_memory_ownership.py` |
| `v4-04-blueprint-generation` | `generation`（+ `blueprint`） | `src/novelforge/generation/**`、`src/novelforge/blueprint/**` | `persistence/paths.py`（新增 blueprint 路径）、`ai/legacy_support.py`（structured 桥）、`application/services/blueprint.py`、四处 legacy provider 接入点、`tests/generation/**`、`tests/v4/isolation/**`、`docs/v4/**` | `story_engine` 内部实现、`api`、UI、frozen 模块、Canon / StoryState 写入 | `BlueprintNode` / `BlueprintRepository` / `GenerationRequest` / `GenerationResult`（新增） | `tests/generation/**`、`tests/v4/isolation/test_generation_boundaries.py` |
| `v4-05-quality-loop` | `quality`（+ `quality.repair`） | `src/novelforge/quality/**` | `persistence/paths.py`（新增 quality 路径）、`persistence/__init__.py`、`application/services/review.py`（+ `__init__` 导出）、`tests/quality/**`、`tests/v4/isolation/**`、`docs/v4/**` | `generation` 反向依赖 quality、`ai` / `memory` / `blueprint` / `domain` 内部实现、`story_engine/repair.py`（M11 frozen）、Canon / StoryState 写入、release tag | `QualityIssue` / `QualityEvidence` / `QualityReport` / `QualityPolicy` / `RepairPlan` / `RepairResult` / `VerificationResult`（新增） | `tests/quality/**`、`tests/v4/isolation/test_quality_boundaries.py` |
| `v4-06-blueprint-editor` | `editor` | `src/novelforge/editor/**` | `persistence/paths.py`（新增 editor 路径）、`generation/{service,errors,rewrite,__init__}.py`（字段级 rewrite）、`blueprint/{contracts,__init__}.py`（结构 identity SSOT）、`application/services/editor.py`、`api/editor_routes.py` + `api/app.py`、`quality/repair/planner.py`（复用 blueprint SSOT）、`tests/editor/**`、`tests/v4/isolation/**`、`docs/v4/**` | `generation` / `quality` / `blueprint` / `ai` / `memory` / `domain` 反向依赖 editor、`story_engine/repair.py`（M11 frozen）、Canon / StoryState 写入、release tag | `EditRequest` / `EditResult` / `BlueprintDiff` / `RevisionView` / `RevisionHistory` / `RewriteRequest` / `RewriteResult` / `ApprovalResult` / `RestoreResult` / `ChangeImpact` / `EditorOperationRecord`（新增） | `tests/editor/**`、`tests/v4/isolation/test_editor_boundaries.py` |
| `v4-07-delivery-export` | `delivery` | `src/novelforge/delivery/**` | `persistence/paths.py`（新增 delivery 路径）、`quality/{contracts,service,store}.py`（报告记录 node_revisions + reports()）、`application/services/export.py`（facade + V4 交付方法）、`api/delivery_routes.py` + `api/app.py`、`tests/delivery/**`、`tests/v4/isolation/**`、`docs/v4/**` | `delivery` 反向依赖、LLM / memory / repair 调用、修改 Blueprint · Canon · StoryState、release tag、`story_engine/repair.py`（M11 frozen） | `DeliveryService` / `DeliverySelection` / `DeliveryPolicy` / `DeliverySnapshot` / `DeliveryManifest` / `DeliveryValidationResult` / `ExportArtifact` / `ExporterRegistry`（新增） | `tests/delivery/**`、`tests/v4/isolation/test_delivery_boundaries.py` |
| `v4-08-mcp-server` | `mcp` | `src/novelforge/interfaces/**` | `application/services/facade.py`（ApplicationServices 能力束 + 新增只读 facade）、`application/services/{editor,export}.py`（reviews / blueprint_view）、`delivery/service.py`（machine_representation，只读）、`requirements.txt`（官方 MCP SDK 与 starlette 兼容区间）、`tests/mcp/**`、`tests/v4/isolation/**`、`docs/v4/**` | 各业务模块反向依赖 `interfaces.mcp`、MCP 直连业务模块 / HTTP / 文件系统、修改 Blueprint · Canon · StoryState、release tag、`story_engine/repair.py`（M11 frozen） | `MCPDispatcher` / `MCPToolRegistry` / `MCPResourceRegistry` / `ToolSpec` / `ResourceSpec` / `ToolResult` / `MCPError` 家族（新增） | `tests/mcp/**`、`tests/v4/isolation/test_mcp_boundaries.py` |
| `v4-09-plugin-platform` | `plugins` | `src/novelforge/plugins/**`、`src/novelforge/application/services/plugins.py` | `persistence/paths.py`（新增 plugin_state 路径 + `plugin_state` artifact kind）、`persistence/__init__.py`、`delivery/exporters/__init__.py`（owner + unregister + 同 owner 更新）、`delivery/contracts.py`（`accepted_formats` 构造期校验）、`delivery/service.py`（插件 artifact 同样过 secret scan）、`quality/{registry,codes,contracts,service}.py`（owner / policy / namespaced code / provenance）、`interfaces/mcp/{contracts,registry,uri}.py`（owner + unregister + `novelforge://plugins/...`）、`application/services/{__init__,facade,export}.py`（registry 注入）、`tests/plugins/**`、`tests/v4/isolation/**`、`docs/v4/**` | 覆盖 Core 注册（exporter format / MCP tool·resource / evaluator / issue code）、Core 反向 import `novelforge.plugins`、插件直连业务模块 / HTTP / 文件系统 / 自拼路径、修改 Blueprint · Canon · StoryState、release tag、`story_engine/repair.py`（M11 frozen） | `PluginManager` / `PluginRegistry` / `PluginManifest` / `PluginDescriptor` / `PluginContribution` / `PluginResult` / `PluginContext` / `PluginError` 家族 / `PluginService` / `PluginHost`（新增） | `tests/plugins/**`、`tests/v4/isolation/test_plugin_boundaries.py` |
| `v4-10-story-studio-ui` | `ui` | `ui/src/studio/**`、`ui/src/api/studio.ts`、`ui/src/App.tsx`、`ui/src/v3/design-system/**`（复用）、`ui/package.json`（vitest/testing-library/jsdom/playwright）、`src/novelforge/api/{studio_routes.py,app.py,delivery_routes.py}`、`tests/studio/**`、`tests/browser_v4_*.cjs`、`scripts/studio_ui_test_server.py`、`tests/browser_v3_*.cjs` + `tests/browser_creator_*.cjs`（仅入口参数）、`docs/v4/**` | UI 直接读文件 / import Python / 推导业务事实、REST 绕过 application services、默认入口仍指向 V3、旧验收断言被削弱、release tag、`story_engine/repair.py`（M11 frozen） | `StudioApp` / `UI_STATUS_MAP` / `studioApi` / `resolveParent` / `StudioHost`（composition）/ `BrowserGate`（新增） | `ui/src/**/*.test.ts(x)`、`tests/studio/**`、`tests/browser_v4_studio_golden.cjs`、`tests/browser_v4_legacy_entry.cjs` |

> V4-09 执行方式：integration branch `v4-09-plugin-platform`（单 Agent 顺序执行）；
> composition root 放在 `novelforge/plugins/host.py` —— `application` 层禁止依赖
> `interfaces`（§3.2），而插件装配必须同时接触两者。

> V4-10 执行方式与分支事实（不重写历史）：integration branch `v4-10-story-studio-ui`。
> 说明：V4-10 的前 5 个提交最初落在 `v4-09-plugin-platform`（分支未先切出），
> 随后建立 `v4-10-story-studio-ui` 指向该 head 并继续提交；历史未被改写。
> 逻辑提交序列：`docs(ui contract)` → `feat(api studio facades)` → `feat(ui studio)` →
> `test(browser golden)` → `fix(parent resolution / index / toast)` →
> `test(frontend component+contract)` → `test(browser legacy entry)` →
> `docs(v4): record v4-10 result`。

> V4-04 执行方式：任务书 §2 允许「单 Agent 顺序执行 → 一个 integration branch + 清晰提交边界」，
> 本阶段即采用该方式（`v4-04-blueprint-generation` = integration branch）。

> V4-03 执行方式：本阶段的任务分支 `v4-03a…v4-03e` 以**线性提交序列**实现在
> integration 分支 `v4-03-memory-integration` 上（单 agent 顺序执行；分叉+合并只会
> 产生无意义的合并提交）。提交边界即模块边界：contracts → stores/views →
> preferences/context/service → tests → guards → report。

> V4-02 的辅助修改理由：
>
> ```text
> core        ：复用 request_id / digest（避免在 ai 内重复实现 id/digest）
> observability：新增最小 model_trace sink（Gateway 需要落 trace；不建 metrics/dashboard）
> application ：新增 utility service 证明「app-services → ai」单向依赖（§25）
> spec/llm.py ：legacy 直接模型调用必须收编（§24），只保留 compatibility 适配
> config      ：新增 provider 配置示例（不含 secret，secret 只从 environment 读取）
> ```

---

## 4. 分支规则

```text
1. 一个分支主要维护一个模块；跨模块必须先改 Contract（单独 commit）
2. 禁止一个分支"顺手"改多个模块内部实现
3. 分支基于 main（或已合入的 V4 集成分支）；基线必须包含 V4-01 边界
4. 分支不得修改：
     refs/tags/novelforge-product-v3-final
     docs/FROZEN_EVIDENCE_MANIFEST.json（除非作者明确要求）
     novel/authoring/**（frozen tracked data）
5. 每个分支结束必须通过：
     pytest（默认套件）
     scripts/validate_project.py
     tests/v4/isolation/**（V4-01 起的永久隔离测试）
     V2 Frozen Guard
6. 不合入 main 之前不得删除其他分支；不 force-push 共享分支
```

---

## 5. 并行开发的最小隔离要求

```text
模块测试不得依赖：
  · 其他模块的内部实现
  · 真实 historical / 旧正文资产（V4-01 起已删除）
  · 本机作者数据（novel/authoring/**、workspace/**）

每个模块的测试根：tests/<module>/
共享 fixture：tests/fixtures/（必须最小、显式归属、可重复生成）
跨模块 E2E：tests/e2e/（单独标记，不阻塞单模块开发）
```

---

## 6. 提交信息约定

```text
docs(v4):     V4 文档 / ADR / 边界声明
chore(v4):    资产删除、仓库卫生
refactor(v4): 边界迁移、参数化、收编（不改变外部行为）
feat(v4):     新能力（带 Contract + 测试）
test(v4):     测试与守卫
fix(v4):      缺陷修复
```

每个提交都必须保持：`pytest` 默认套件可运行、无 frozen boundary 变更。
