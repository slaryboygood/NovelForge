# NovelForge V4 — Module Boundaries（维护边界 SSOT）

> 状态：**V4-01 Boundary Foundation**
> 依据：`docs/NOVELFORGE_V4_MASTER_PLAN.md` §8–13、§43；`docs/v4/V4_ARCHITECTURE.md` §3–§4
> 定位：本文件是**物理目录与依赖边界的最终依据**。任何新模块、目录改名、跨模块导入都要先改这里，
> 再改代码（Master Plan §13：先 Contract，再适配）。

---

## 1. 一个模块的定义

```text
一个主要能力
  = 一个明确模块
  = 一个独立目录
  = 一组公开 Contract（`__init__.py` 或 `contract.py` 显式导出）
  = 一组独立测试（tests/<module>/ 或 tests/test_<module>_*.py）
  = 可由独立任务分支维护（见 V4_BRANCH_STRATEGY.md）
```

每个模块必须在本文件声明六项：

```text
Public Contract     可被其他模块依赖的符号
Internal            仅模块内可见（外部禁止 import）
Allowed Dependencies
Forbidden Dependencies
State Ownership     该模块拥有 / 不拥有什么状态
Module Tests
```

---

## 2. 模块清单（V4-01 快照）

`State` 含义：`EXISTS`（V3 已有，建立边界即可）/ `NEW`（V4-01 新建）/ `DEFERRED`（后续阶段）。

| Module | Module ID | Current Path | Target Path | State | Owner Phase |
| --- | --- | --- | --- | --- | --- |
| Core Primitives | `core` | `src/novelforge/models.py` | `src/novelforge/core/` | NEW（`revision` / `ids` / `errors`） | V4-01 |
| Application Services | `app-services` | `src/novelforge/story_builder/` | `src/novelforge/application/services/` | NEW（骨架 + 3 个服务） | V4-01 → V4-11 |
| Persistence | `persistence` | 散落于各模块的 `Path(...)` | `src/novelforge/persistence/` | NEW（`paths.py`） | V4-01 |
| Legacy Compatibility | `legacy` | `story_engine/m11_*.py` 等 | `src/novelforge/legacy/` | NEW（adapter + manifest） | V4-01 |
| Story Engine / Domain | `domain` | `src/novelforge/story_engine/` | 保持原位（不整体移动） | EXISTS | — |
| LLM Gateway | `ai` | `src/novelforge/ai/` | 不变（V4-02 已落地） | **EXISTS** | V4-02 ✅ |
| Story Memory | `memory` | `src/novelforge/memory/` | 不变（V4-03 已落地） | **EXISTS** | V4-03 ✅ |
| Blueprint Generation | `generation` | `src/novelforge/generation/` | 不变（V4-04 已落地） | **EXISTS** | V4-04 ✅ |
| Story Blueprint Store | `blueprint` | `src/novelforge/blueprint/` | 不变（V4-04 已落地） | **NEW** | V4-04 ✅ |
| Story Quality | `quality` | 9 处 validator / finding | `src/novelforge/quality/` | **NEW** | V4-05 ✅ |
| Story Repair | `repair` | `story_engine/repair.py`（冻结历史用途，**不复用**） | `src/novelforge/quality/repair/` | **NEW** | V4-05 ✅ |
| Blueprint Editor | `editor` | `story_builder/writer_integration.py`（正文草稿，**不复用**） | `src/novelforge/editor/` | **NEW** | V4-06 ✅ |
| Delivery / Export | `delivery` | `story_builder/export_package.py` 等 4 条路径 | `src/novelforge/delivery/` + `application.services.export`（facade） | **NEW** | V4-07 ✅ |
| MCP Adapter | `mcp` | 无 | `src/novelforge/interfaces/mcp/` | DEFERRED | V4-08 |
| Plugin Platform | `plugins` | 无 | `src/novelforge/plugins/` | DEFERRED | V4-09 |
| Observability | `observability` | `src/novelforge/observability/model_trace.py` | 不变（最小实现） | **NEW** | V4-02 ✅ → V4-07 |
| UI | `ui` | `ui/src/` | `ui/src/` | EXISTS | V4-10 |

> **V4-01 只落地 5 个边界**：`core` / `app-services` / `persistence` / `legacy` +
> 对 `domain`、`ui` 的只读边界声明。其余目录在对应阶段创建，避免"先建空壳"。

---

## 3. 逐模块边界声明

### 3.1 `core` — Core Primitives

```text
Public Contract
  core.ids       : new_id / slug / digest（语义稳定，无业务规则）
  core.errors    : NovelForgeError 基类 + 统一 error envelope
  core.revision  : RevisionRef / RevisionConflict / expected_revision 校验
Internal
  core/_internal/*
Allowed
  python stdlib, pydantic
Forbidden
  任何 story / canon / blueprint 业务规则
  任何 adapter（fastapi / mcp / provider / 文件系统）
State Ownership
  无（纯函数与数据类型）
Module Tests
  tests/test_core_revision.py、tests/test_core_ids.py
```

`core` 不是公共垃圾桶（Master Plan §11）。允许进入的条件：

```text
语义稳定 + 无模块所有权争议 + 不含故事业务规则 + 不依赖具体 Adapter
禁止：core/utils.py、core/helpers.py、core/manager.py
```

### 3.2 `app-services` — Application Services

```text
Public Contract
  application.services.journey : JourneyProjection（唯一进度 / 下一步投影）
  application.services.export  : ExportService（唯一导出出口）
  application.services.project : ProjectService（作品生命周期）
Internal
  application/_legacy_adapters/*（对既有 story_builder 的过渡包装）
Allowed
  domain(story_engine)、persistence、core、legacy（只读）
Forbidden
  interfaces(fastapi / mcp)、ai provider、直接文件路径常量、直接 SQL
State Ownership
  编排状态（会话 / 批次 / agent session），不拥有 story truth
Module Tests
  tests/test_service_journey.py、tests/test_service_export.py、tests/test_service_project.py
```

**边界规则**：接口层（`api/`、未来 `interfaces/mcp/`）只调用 `application.services`；
不得直接 import `story_engine.*`（V4-01 建立守卫测试，存量例外显式白名单）。

### 3.3 `persistence` — Persistence & Ownership

```text
Public Contract
  persistence.paths : ArtifactContext + 全部 artifact 路径解析（唯一来源）
Internal
  persistence/_backends/*
Allowed
  core, domain 模型定义, python stdlib
Forbidden
  interfaces / ai / ui；任何隐式"当前作品"
State Ownership
  物理存储（文件 / SQLite），不拥有业务语义
Module Tests
  tests/v4/isolation/test_ownership_isolation.py
  tests/v4/isolation/test_no_implicit_disk_discovery.py
```

硬规则：

```text
1. 路径解析必须显式携带 project_id / novel_id / artifact_kind
2. 禁止 GLOBAL_CURRENT_NOVEL、默认 wasteland_001、扫描磁盘猜当前作品
3. 禁止"当前作品无数据 → fallback 到其他作品 / 已删除历史数据"
4. 路径常量集中在 persistence.paths；其他模块不得自行拼路径
```

### 3.4 `domain` — Story Engine（原位保留）

```text
Public Contract
  story_engine.__init__ 已导出符号（state / actions / conditions / effects / resolver /
  events / foreshadow / progression / driver / director / canon / chapter_ir / planning /
  profile / templates / content ...）
Internal
  story_engine 内部未导出实现
Allowed
  python stdlib, pydantic, networkx, core
Forbidden
  fastapi, mcp, provider SDK / 任何 HTTP client, ui, persistence 反向依赖
State Ownership
  StoryState / Canon / ChapterIR / PlanningIR 的语义（不是物理存储）
Module Tests
  tests/test_story_engine_*.py、tests/test_story_planning_*.py、
  tests/test_canon_*.py、tests/test_chapter_ir_*.py
```

`domain` 在 V4-01 **不被移动**（Master Plan §40：不为目录整齐搬 frozen 代码）。

### 3.5 `legacy` — Legacy Compatibility Boundary

```text
Public Contract
  legacy.manifest : frozen module inventory（id / path / status / used_by / removal_condition）
  legacy.adapters : 对 frozen 能力的只读包装
Internal
  legacy/_vendor/*（未来真正迁入的 frozen 模块）
Allowed
  core, domain（只读调用）
Forbidden
  被新的写路径依赖；被 interfaces 直接暴露；持有可变业务状态
State Ownership
  无（只读视图）
Module Tests
  tests/v4/isolation/test_legacy_boundary.py
```

规则：

```text
1. frozen 模块在替换完成前原地保留，只通过 adapter 暴露
2. frozen 模块不得被新业务写路径 import（守卫测试）
3. 已删除的废弃数据（novel/final、570 章 historical）不进入 legacy/
4. 只有"仍需要兼容的能力"才进 legacy/；废弃能力直接删除
```

### 3.6 `ui`

```text
Public Contract      仅通过 HTTP API 消费后端能力（ui/src/v3/api.ts）
Allowed              REST API
Forbidden            直接推导业务事实、直接读写文件、复制后端质量 / 进度逻辑
State Ownership      纯展示状态（含 localStorage 设计态参考位）
Module Tests         tests/browser_*.cjs
```

### 3.7 `ai` — LLM Gateway（V4-02 落地）

```text
Public Contract
  LLMGateway / LLMResult
  LLMProvider / LLMRequest / ProviderResponse
  LLMContract / PromptSpec / ValidationPolicy / ContractRegistry / resolve_contract
  ModelPolicy / ModelRoute / ModelRouter
  ProviderConfig / ModelSpec / ProviderRegistry / load_provider_configs /
    resolve_secret / redact_secrets / build_gateway / build_provider
  UsageRecord / ModelPricing / TraceRecord / TraceSink / NullTraceSink
  CacheKey / InMemoryCache / build_cache_key / cache_allowed
  chat_completion_via_gateway / map_legacy_error_code（legacy 桥）
  LLMError 家族（ProviderConfigurationError / AuthenticationError / RateLimitError /
    ProviderUnavailableError / ModelUnavailableError / RequestTimeoutError /
    StructuredOutputError / RetryExhaustedError / InvalidRequestError）
Internal
  ai/providers/*（provider 实现；HTTP client 与 provider SDK 只允许在这里）
Allowed
  core（request_id / digest）、python stdlib、pydantic、provider SDK / HTTP library
Forbidden
  story_engine / story_builder（domain）、application、persistence、api、mcp、ui、
  observability（observability 依赖 ai，而不是反向）
State Ownership
  调用记录（usage / trace / cache），不拥有任何 story truth
Module Tests
  tests/ai/**（90 个离线测试）、tests/v4/isolation/test_module_boundaries.py（边界守卫）
Exceptions（显式登记，只减不增）
  domain 允许在 3 个 legacy 适配器中**函数内惰性** import novelforge.ai：
    story_engine/spec/llm.py
    story_engine/planning/plot_synthesis.py
    story_engine/planning/route_candidates.py
  （登记在 tests/v4/isolation/test_module_boundaries.py 的 DOMAIN_AI_IMPORT_ALLOWLIST；
   移除条件写在 src/novelforge/legacy/manifest.py）
```

### 3.8 `memory` — Story Memory & Context Builder（V4-03 落地）

```text
Public Contract（保持精简，§10）
  MemoryService / build_default_service
  MemoryItem / MemoryQuery / MemoryResult / MemoryScope / MemorySource / RetrievalPolicy
  ContextBuilder / ContextRequest / ContextBundle / ContextBlock
  AuthorPreference / AuthorPreferenceService / PREFERENCE_SCOPE_ORDER
  DeterministicTokenEstimator / TokenEstimator / BLOCK_PRIORITY_ORDER
  DeterministicTruncatingCompressor / GatewayCompressor / NullCompressor
  MEMORY_SCHEMA_VERSION / MemoryError 家族
Internal
  memory/index.py（MemoryIndex）、memory/scoring.py（确定性打分）
  memory/sources/*（Canon / StoryState 只读投影）、memory/episodic/*、memory/semantic/*
  memory/embedding.py（embedding 实现）、memory/retrieval.py（装配辅助）
Allowed
  core、domain（story_engine 只读 Public API）、persistence.paths（唯一路径来源）、
  novelforge.ai（Public Contract：摘要 / extraction / 可选 embedding）
Forbidden
  novelforge.api / novelforge.application、fastapi / mcp、novelforge.ai.providers、
  任何 HTTP client、自行拼 artifact 路径
State Ownership
  只拥有**派生**记忆（可重建、可失效）；不拥有 Canon / StoryState / Blueprint truth
Module Tests
  tests/memory/**（61 个）、tests/v4/isolation/test_memory_ownership.py（跨作品隔离）
Exceptions
  memory 是唯一允许"读取 domain 并投影成派生视图"的能力层；domain / ai 不得反向依赖 memory
```

---

## 4. 依赖矩阵（V4-01 生效部分）

### 3.9 `blueprint` — Story Blueprint canonical store（V4-04 落地）

```text
Public Contract
  BlueprintNode / BlueprintNodeRef / NodeType / NodeStatus / BLUEPRINT_SCHEMA_VERSION
  PAYLOAD_MODELS（12 类 payload：premise…payoff）/ ALLOWED_PARENT_TYPES
  BlueprintRepository（append-only revision + index + idempotency）
  validate_node / validate_graph / require_valid
  ALLOWED_STATUS_TRANSITIONS / assert_can_regenerate / next_status_for_regeneration
  BlueprintError 家族
Internal
  无（repository / validation / lifecycle 本身就是最小实现）
Allowed
  core（revision）、persistence.paths（唯一路径来源）、python stdlib、pydantic
Forbidden
  ai / generation / memory / api / fastapi / mcp / HTTP client / 自行拼路径
State Ownership
  **canonical Story Blueprint**（节点与 revision 历史）；不拥有 Canon / StoryState
Module Tests
  tests/generation/test_blueprint_contracts.py、test_blueprint_repository.py、
  tests/v4/isolation/test_generation_boundaries.py
```

### 3.10 `generation` — Blueprint Generation（V4-04 落地）

```text
Public Contract
  BlueprintGenerationService / GenerationRequest / GenerationResult /
  GenerationPlan / GenerationEvidence / TaskSpec / TaskRegistry /
  DEFAULT_PIPELINE / default_registry / GenerationError 家族
Internal
  generation/tasks/*（premise / world / characters / story / chapter / scene / links）
Allowed
  ai（LLMGateway）、memory（ContextBuilder）、blueprint（节点模型 + repository）、
  core、persistence.paths、domain public contract
Forbidden
  api / interfaces、ai.providers、HTTP client、直接 CanonRepository / StoryState 读取、
  自行拼 artifact 路径
State Ownership
  无 truth；只产出 proposal 节点（写入经 BlueprintRepository）
Module Tests
  tests/generation/**（57 个）
Exceptions
  四处 legacy structured provider（creative / settings_gen / outline_forge /
  ai_recommendations）允许函数内惰性 import novelforge.ai（Gateway 桥）
```

`✓` 允许 / `✗` 禁止 / `△` 仅经显式 Contract。

### 3.11 `quality` — Story Quality Gate（V4-05 落地）

```text
Public Contract（保持精简，§6 / §79）
  QualityService / quality_service      唯一评估入口（deterministic first，逐 gate）
  QualityScope / QualityEvidence        作用域与一等证据
  QualityIssue / QualityGateResult      结构化问题 / 每 gate 结果
  QualityReport / QualityPolicy         report 与生产策略
  QualityStatus / SEVERITIES / decide_status   固定语义（gate-based，非分数）
  EvaluatorRegistry / EvaluatorSpec     evaluator 注册表（不硬编码 if gate == ...）
  CODE_REGISTRY / code_spec / codes_for_gate / is_registered   稳定 issue code
  QualityStore                          quality truth（独立于 story truth）
  RepairPlanner / RepairExecutor / RepairVerifier / RepairPlan / RepairResult /
  RepairContract / RepairStep / VerificationResult / RepairBlastRadius
  QualityError 家族
Internal
  quality/evaluators/*（10 个 gate 模块 + base）、quality/aggregation.py、
  quality/_internal/*（确定性相似度）
Allowed
  blueprint（节点模型 + repository 只读）、memory（只读检索）、ai（LLMGateway，仅 critic）、
  core（ids / revision）、persistence.paths（唯一路径来源）、domain public contract
Forbidden
  novelforge.api / novelforge.application、novelforge.ai.providers、HTTP client、
  自行拼 artifact 路径、写 Canon / StoryState、修改 Blueprint 节点
State Ownership
  **quality truth**（report / issue / evidence / repair history）；不拥有 story truth
Module Tests
  tests/quality/**（122 个）、tests/v4/isolation/test_quality_boundaries.py
```

### 3.12 `quality.repair` — Targeted Repair（V4-05 落地）

```text
Public Contract
  RepairPlanner / RepairBlastRadius / RepairExecutor / RepairVerifier /
  RepairContract / RepairStep / RepairPlan / RepairResult / VerificationResult
Allowed
  quality contracts、blueprint、generation Public Contract（唯一允许的上层依赖）、core
Forbidden
  generation → quality 的反向依赖（形成环）、自行实现 LLM 生成、原地修改节点、
  修改 Canon / StoryState、绕过 expected_revision
State Ownership
  无（产出新 Blueprint revision + repair history）
Module Tests
  tests/quality/repair/**（test_planner / test_blast_radius / test_executor /
  test_verifier / test_loop）
Exceptions
  repair 是**唯一**允许 import generation 的 quality 子模块（显式 allowlist：
  src/novelforge/quality/repair/executor.py，守卫测试登记）
```

| ↓依赖 / 被依赖→ | core | persistence | domain | app-services | legacy | interfaces | ui | ai | memory | quality |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `core` | ✓ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ |
| `persistence` | ✓ | ✓ | ✓ | ✗ | ✓ | ✗ | ✗ | ✗ | ✗ | ✗ |
| `domain` | ✓ | ✗ | ✓ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ |
| `app-services` | ✓ | ✓ | ✓ | ✓ | △ | ✗ | ✗ | ✓ | ✓ | ✓ |
| `legacy` | ✓ | ✓ | ✓ | ✗ | ✓ | ✗ | ✗ | ✗ | ✗ | ✗ |
| `interfaces` | ✓ | ✗ | ✗ | ✓ | ✗ | ✓ | ✗ | ✗ | ✗ | ✗ |
| `ui` | ✗ | ✗ | ✗ | ✗ | ✗ | ✓(HTTP) | ✓ | ✗ | ✗ | ✗ |
| `ai` | ✓ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✓ | ✗ | ✗ |
| `memory` | ✓ | △ | ✓ | ✗ | ✗ | ✗ | ✗ | ✓ | ✓ | ✗ |
| `quality` | ✓ | △ | ✓ | ✗ | ✗ | ✗ | ✗ | ✓ | ✓ | ✓ |

> `quality.repair` 例外：`quality/repair/executor.py` 允许依赖 `generation` 的 Public
> Contract（`regenerate`）；`generation` 仍然**绝不**依赖 quality（守卫测试
> `tests/v4/isolation/test_quality_boundaries.py::test_generation_never_imports_quality_or_repair`）。

### 3.13 `editor` — Blueprint Editor & Revision Workflow（V4-06 落地）

```text
Public Contract（精简，§6）
  BlueprintEditorService / EditorStore
  EditRequest / EditResult / BatchEditRequest / BatchEditResult / MoveNodeRequest
  DiffRequest / BlueprintDiff / FieldChange / ListChange
  RewriteRequest / RewriteResult / ApprovalResult / RestoreResult / ChangeImpact
  RevisionView / RevisionHistory / EditorOperationRecord / ReviewDecision / EditorSession
  EditorError 家族
Internal
  editor/patch.py / diff.py / history.py / impact.py / operations.py 的实现细节
Allowed
  blueprint（唯一 canonical store）、generation（rewrite / regenerate 的 Public Contract）、
  core、persistence.paths
Forbidden
  interfaces(api) / application / ai（gateway 与 provider）/ memory / story_engine /
  quality、任何 HTTP client、自行拼 artifact 路径、写 Canon / StoryState、
  自建第二套 Blueprint store
State Ownership
  **editor metadata**（operation / review / session）；canonical 内容仍属 blueprint
Module Tests
  tests/editor/**、tests/v4/isolation/test_editor_boundaries.py
```

Application 组合（§67）：`application.services.editor.EditorService` 把
`editor` + `quality` + `generation` 组装起来；**editor 模块本身不依赖 quality**，
从而避免 `editor → application` 的循环。

### 3.14 `delivery` — Delivery / Export（V4-07 落地）

```text
Public Contract（精简，§19）
  DeliveryService / delivery_service / DeliveryStore
  DeliveryRequest / DeliveryResult / DeliveryPolicy / DeliverySelection
  DeliverySnapshot / DeliveryManifest / DeliveryValidationResult / DeliveryIssue
  ExportArtifact / NovelForgePackage / ExporterRegistry / ExporterSpec
  DeliveryError 家族
Internal
  delivery/{selection,snapshot,validation,compiler,manifest,store}.py 的实现细节、
  delivery/exporters/*（具体 exporter 模块不导出）
Allowed（只读）
  blueprint（canonical revision graph）、quality（Quality Store：issue / report）、
  editor（EditorStore：review / operation metadata）、core、persistence.paths
Forbidden
  api / application / ai（LLM）/ memory（retrieval）/ story_engine（Canon · StoryState）、
  任何 HTTP client、自行拼 artifact 路径、修改 Blueprint · Canon · StoryState、
  调用 Quality Repair / Editor 写操作（§50、§87–§88）
State Ownership
  **交付快照 / manifest / artifact**（delivery/<novel_id>/…）；不拥有 story truth
Module Tests
  tests/delivery/**、tests/v4/isolation/test_delivery_boundaries.py
```

Application facade（§21、§60）：`application.services.export.ExportService` 是唯一入口 ——
V4 主路径走 `deliver(...)` → `DeliveryService`；legacy `projection / validate / export /
writer_bundle` 保留为 V3 compatibility（移除条件登记在 `V4_DELETION_PLAN.md` §3）。

### 4.1 明文禁令

```text
domain       → 不允许 import fastapi / mcp / httpx / urllib / openai / anthropic
domain       → 不允许 import persistence（路径解析在 domain 之外）
interfaces   → 不允许 import domain（必须经 app-services）
persistence  → 不允许 import app-services / interfaces / ai
legacy       → 不允许被 app-services 之外的模块 import
ui           → 不允许 import 任何 Python 模块（只走 HTTP）
quality      → 不允许 import api / ai.providers / HTTP client，不允许自行拼 artifact 路径
quality      → 不允许修改 Blueprint 节点 / Canon / StoryState
generation   → 不允许 import quality / repair（否则形成依赖环）
editor       → 不允许 import api / application / ai / memory / story_engine / quality
editor       → 不允许自行拼 artifact 路径，不允许写 Canon / StoryState，
               不允许自建第二套 Blueprint store
core / persistence / domain / ai / memory / blueprint / generation / quality
             → 不允许 import editor（Application 可以依赖 editor）
delivery     → 不允许 import api / application / ai / memory / story_engine / HTTP client
               / 自行拼路径 / 修改 Blueprint · Canon · StoryState / 调用 repair 或 editor 写操作
core / domain / ai / memory / blueprint / generation / quality / editor
             → 不允许 import delivery（Application 可以依赖 delivery）
```

### 4.2 守卫测试

```text
tests/v4/isolation/test_module_boundaries.py
  · 扫描 src/ 的 import 图，断言上表禁例
  · 存量例外以显式白名单登记（V4-01 白名单 = 现状快照，后续只减不增）
tests/v4/isolation/test_quality_boundaries.py（V4-05）
  · quality 不 import interface / provider / HTTP client
  · quality 不自行拼 artifact 路径（AST 字符串字面量检查）
  · quality 只经 persistence.paths 取路径
  · evaluator / service 不依赖 generation（allowlist = quality/repair/executor.py）
  · domain / ai / memory / blueprint / generation / core / persistence 不得 import quality
  · quality 不写 Canon / StoryState；Public Contract 精简；顶层不 import generation
tests/v4/isolation/test_editor_boundaries.py（V4-06）
  · editor 不 import interface / application / provider / domain / memory / quality
  · editor 不自行拼 artifact 路径；只经 persistence.paths
  · editor 不写 Canon / StoryState；下层不得反向 import editor
  · editor 顶层不 import application / api / ai / memory / quality
  · Public Contract 精简；REST 路由只调用 application.services.editor（+ 错误模型）
  · editor metadata store 不含 BlueprintNode（不是第二套 truth）
tests/v4/isolation/test_delivery_boundaries.py（V4-07）
  · delivery 不 import interface / application / ai / memory / domain / HTTP client
  · delivery 只依赖 blueprint / quality / editor metadata / core / persistence.paths
  · delivery 不自行拼 artifact 路径；不写 Blueprint · Canon · StoryState；不调用 repair
  · delivery 无模型调用面（gateway / LLMContract / model_policy）
  · 下层不得反向 import delivery；delivery 顶层不 import application / api / ai / memory
  · Public Contract 精简（不导出具体 exporter 模块）；REST 路由只调用 application.services.export
  · Application facade 必须经 DeliveryService / DeliveryRequest
```

---

## 5. 新增模块的申请流程

```text
1. 在本文件登记：Module / Path / Public Contract / Allowed / Forbidden / Tests
2. 先提交 Contract（单独 commit）
3. 再提交实现
4. 补模块测试（Unit / Contract / Integration / E2E 按需）
5. 跨模块变更按 Master Plan §13：先 Contract，再分别适配
```

---

## 6. 与 V4-00 目录提案的差异

| V4-00 提案 | V4-01 实际 | 原因 |
| --- | --- | --- |
| `application/services/*` 一次性搬迁 | 先建骨架 + 3 个服务（journey / export / project） | Strangler：1,545 行路由不一次性重写 |
| `domain/*` 重命名 | 保持 `story_engine/` 不动 | 不为目录整齐移动 frozen 代码（Master Plan §40） |
| `generation/*`（6 模块） | 推迟到 V4-04 | 生成能力尚未接 LLM，先不建空壳 |
| `quality/*`、`memory/*`、`ai/*` | 推迟到 V4-02 / V4-03 / V4-05 | 同上 |
| `legacy/*` 隔离区 | **V4-01 建立** | 需要明确表达"哪些 frozen 代码仍被兼容使用" |
| `persistence/paths.py` | **V4-01 建立** | ownership 是所有后续模块的前提 |
