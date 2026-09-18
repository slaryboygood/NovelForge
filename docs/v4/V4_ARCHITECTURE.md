# NovelForge V4 — Target Architecture

> 状态：**V4-00 Architecture / Proposed**，已按 **V4-01 作者决策**对齐（2026-09-17）
> 基线：`novelforge-product-v3-final`（commit `f02ca8c`）
> 输入证据：`docs/v4/V4_CODEBASE_INVENTORY.md`、`docs/v4/V4_MODULE_CLASSIFICATION.md`
> 本文只定义架构。**不含任何业务代码改动**；`Status: Proposed` 的部分明确标注。

---

## 0.A V4-01 作者决策对齐（覆盖本文以下相关段落）

作者在 V4-01 冻结了三项决策，**优先级高于本文 V4-00 的对应假设**：

```text
Decision A  novel/final/*.md        → DELETE（不迁移 / 不归档 / 不导入）
Decision B  570 章 historical 数据  → DELETE（不导入 / 不做 fixture / 不进 legacy/）
Decision C  canonical creative artifact = StoryBlueprint（不是正文 draft）
            Writer → Blueprint Editor / Story Studio
            Draft 不再是核心 artifact；完整正文生成非 V4 Core
```

受影响段落（阅读时以本节为准）：

| 位置 | V4-00 原假设 | V4-01 修正 |
| --- | --- | --- |
| §3 目录树 `persistence/writer_store.py` | canonical writer store（正文） | canonical **Blueprint** store；正文 draft 仅为兼容层 |
| §3 目录树 `application/services/writer_service.py` | 写作 / 草稿 / revision | **Blueprint Editor** 服务（结构节点编辑，非正文） |
| §6 ownership 表「正文的 source of truth」 | `ChapterRevision` 正文链 | **StoryBlueprint** 是 canonical creative artifact；正文不再有 owner 概念 |
| §6 ownership 表「Export 从哪里读取」 | 含 writer revision | 只读 Blueprint / Canon / StoryState（无正文分区） |
| §7 revision 模型 | 主要服务正文 | 服务 Blueprint 节点 / StoryState / Quality-Repair / Agent mutation |
| §9 DoD「正文 source of truth」 | 待建 ChapterRevision | 改为「Blueprint 的来源与版本」；正文问题作废 |

详见 `docs/v4/adr/ADR-011-story-blueprint-primary-artifact.md`（ADR-003 已被其取代）。

---

## 0. 一句话目标

```text
V3：带 UI 的小说生成工具（Domain + Application + UI，全部在同一进程、同一批文件里）
V4：Novel Creation Runtime —— 一个由 service 层统一驱动，可被 UI / REST / MCP / Agent / 插件
    共用的小说创作系统
```

V4 的架构承诺只有一条：

```text
UI / REST / MCP / Agent / Plugin
    → 调用同一批 Application Service
    → Service 使用同一批 Domain 规则与同一批 Ports
    → 没有第二条业务路径
```

---

## 1. Architecture Principles

以下 10 条是 V4 的正式原则。每条都附上**当前代码事实**，避免变成口号。

### 1.1 LLM is not the database

模型生成内容，NovelForge 保存事实。

* 现有事实：`story_engine/state.py`（StoryState）与 `story_engine/canon/*`（Canon）是唯一 occurred truth；
  模型只允许走「提案」通道（`story_engine/candidates.py:filter_llm_action_proposals`、
  `characters.sanitize_llm_proposals`、`writer_integration.sync_facts` 产生 `PROPOSED`）。
* V4 要求：任何 LLM 输出进入事实之前必须过 **Schema + Domain + Approval** 三层；
  不允许「模型直接写 StoryState / Canon」。

### 1.2 MCP is not the business layer

MCP 只是协议入口。所有 MCP tool 必须调用与 REST/UI 相同的 Application Service。

* 现有事实：业务路径只有一条 —— `api/story_builder_routes.py` → application/domain 模块。
* V4 要求：MCP 不得直接 import `story_engine.*` 或读写文件；只允许 import `services.*`。

### 1.3 Quality is a business capability, not a test script

质量不是「跑一次 pytest」，而是每一次生成的必经环节，并且有证据对象。

* 现有事实（分散的 deterministic 质量能力，全部 `KEEP`）：
  `settings_check.run_settings_check()`、`canon/validator.py`、`canon/prose.py`、
  `chapter_ir/validator.py`、`chapter_ir/evidence.py`、`chapter_ir/verifier.py`、
  `planning/validator.py`、`planning/graph_validator.py`、`outline_forge` 标题质量门禁。
* V4 要求：这些能力**被统一到 Quality Contract**（`V4_QUALITY_CONTRACT.md`），
  而不是被新写一套取代。
* V4-05 实现事实：统一为 `QualityIssue` / `QualityEvidence` / `QualityReport`；
  Q0–Q9 由 `EvaluatorRegistry` 装配（不硬编码 `if gate == ...`）；
  severity / status / issue code 全部固定语义；判定由 Gate + Severity + Policy 决定
  （`decide_status`，绝不使用平均分 —— ADR-018）；证据与 issue 存在独立的
  Quality Store（ADR-020），节点只保留 `quality_status` 投影。

### 1.4 UI / REST / MCP share the same services

* 现有事实：UI 有两条数据路径 —— `ui/src/v3/api.ts`（V3）与 `ui/src/api.ts`（legacy bridge）。
  两者最终都打到同一批端点，但 DTO 定义重复（1,127 vs 426 行）。
* V4 要求：统一 service 层 + 单一 client schema 来源；legacy client 在 bridge 移除时删除。

### 1.5 Creative content should not be heavily hardcoded

* 现有事实：`creative.py`（`TONE_RULES` / `SELLING_POINT_TEMPLATES`）、
  `settings_gen.py`（`RULE_TEMPLATES` / `PROTAGONIST_ROLES` / `content_pack_draft()` 固定骨架）、
  `outline_forge.py`（`NARRATIVE_BEATS` / `（第 N 次）` 兜底）、`journey.py`（三原型固定场景）。
  → 5 个模块，见 `V4_MODULE_CLASSIFICATION.md` §6.1。
* V4 要求：**创作内容**交 LLM；**业务规则**（候选必须真实存在、来源一致性、事实分层、
  唯一性、守恒、审批）继续 deterministic。

### 1.6 Every artifact has ownership

* 现有事实（违反项）：`export_package.py` 的 `RECON_DIR` / `PLANNING_INDEX` /
  `canon/wasteland_001.sqlite`、`writer_integration.CANON_DB`、`inspector.CANON_DB`、
  `historical_ir.HISTORY_DIR` —— 全部硬编码 `wasteland_001`。
  还有 `novel/final/*.md`（69 个 tracked 正文文件）**没有任何 owner**。
* V4 要求：每个 artifact 都必须携带 `project_id` / `novel_id` / `revision` / `created_at` /
  `source_ids`（见 §7）。

### 1.7 Every mutation is revision-aware

* 现有事实：已有先例 —— `blueprints`（`v*.json` 版本）、`outlines`（版本 + restore + merge）、
  `planning`（不可变 revision + index）、`StoryState`（`v%06d` + branch）、
  `phase_snapshot`（write-once + digest）。
* V4 要求：把「版本」升级为统一 `revision` 语义，写操作携带 `expected_revision`，
  冲突返回 conflict 而不是覆盖（见 §7.3）。

### 1.8 AI modifications never silently overwrite author text

* 现有事实：`WriterDraftService` 把 writer 输出隔离在 `preview` 层，**不写 StoryState / Canon**
  （`truth_layer: "preview"`、`wrote_story_state: False`）。
* V4 要求：正文修改必须产生 `Revision`，AI 修改默认 `status = proposed`，
  作者 accept 后才成为 canonical。
* V4-06 实现事实：`novelforge.editor` 把这条原则落到 Blueprint：
  patch / rewrite / restore / move 全部产生**新 revision**（append-only），
  写操作携带 `expected_revision`（冲突不覆盖、不自动 merge）；
  `accept` 是唯一进入 accepted 的显式动作，且 `quality_status = passed ≠ accepted`（ADR-022）。

### 1.9 Generated machine-consumed content is structured

* 现有事实：已经有成熟的结构化契约 —— `ChapterSemanticIR`（`story_engine/chapter_ir/models.py`）、
  `StoryPlanningIR`（`planning/models.py`）、`ContentPack`（`content.py`）、
  `OutlinePackage`（`story_builder/models.py`），并且有严格 gate（`canon/gate.py`、
  `chapter_ir/schemas.py`、`planning/schemas.py`）。
* V4 要求：模型输出禁止「自由文本 + 正则猜测」；必须先 JSON → Schema → Domain → Quality。

### 1.10 Every generation can enter a quality loop

* 现有事实：目前是 `Generate → Save`（外加事后检查）。
* V4 要求：`Generate → Evaluate → (Repair → Verify)* → Save`，且每次循环有 cost / token 记录
  （见 `V4_QUALITY_CONTRACT.md` §7 与 `V4_ARCHITECTURE_RISKS.md` 的 `Quality infinite repair loop`）。
* V4-05 实现事实：`application.services.ReviewService.evaluate_and_repair()` 实现该闭环
  （evaluate → plan → execute → verify，受 `max_repair_rounds` / token / cost 预算限制）；
  `RepairPlanner` 支持 `dry_run`（只回答改哪些节点 / 允许改什么 / 复核哪些 gate / 预计几次模型调用）；
  复核范围是 blast radius（direct + dependent），不是整个 Blueprint。

---

## 2. MASTER PLAN ASSUMPTION CHALLENGE

> 依据 `AGENTS.md` §23：Master Plan 是架构方向，不是不可修改的技术圣经。
> V4 Master Plan（`docs/NOVELFORGE_V4_MASTER_PLAN.md`）提出的目录与阶段**总体上成立**，
> 但有 8 处与代码事实不符或过度设计。以下逐条给出证据与建议。

### CHALLENGE-01：V4 不是 greenfield —— `domain/` 已存在，只是叫 `story_engine/`

* **Original Assumption**：V4 需要新建 `domain/`（novel/character/location/faction/canon/
  story_state/outline/chapter/scene/draft/revision）。
* **Codebase Evidence**：`story_engine/` 已有 68,038 行中的绝大部分，且分类结果 63% 为 `KEEP`
  （`V4_MODULE_CLASSIFICATION.md` §6）。最关键的领域模型（StoryState / Action-Condition-Effect /
  Chapter IR / Planning IR / Canon）**已经在生产使用并被 892 个测试覆盖**。
* **Problem**：若按计划新建 `domain/` 并逐步替换，会立刻产生「两套领域模型」，正是
  `AGENTS.md` §5 明令禁止的 canonical identity 混淆。
* **Recommended Change**：保留 `story_engine/` 作为 Domain 实现，**原地收敛命名**
  （`domain/story/*`、`domain/canon/*`、`domain/chapter_ir/*`、`domain/planning/*`）
  由 V4-01 以「移动 + 保持 import 兼容」的方式完成，禁止新建平行模型。
* **Impact**：V4-01 的工作量从「设计领域层」变为「边界清理 + 命名收敛」；风险显著下降。

### CHALLENGE-02：`memory/` 与现有 `story_engine/memory.py` 同名不同义

* **Original Assumption**：新增 `memory/`（canon memory / story state memory / episodic /
  semantic / author preferences / context builder）。
* **Codebase Evidence**：`story_engine/memory.py`（146 行）+ `memory_view.py`（167 行）已经是
  「谁知道什么」的三视角知识层，并被 `WriterContextBuilder._state_block()` 消费。
* **Problem**：两个 `memory` 会让「事实」「派生索引」在同一命名空间下混淆，
  未来必然出现「memory 是 truth 还是 cache」的 PR 级争论。
* **Recommended Change**：现有模块改名 `domain/knowledge.py`（语义：故事内知识事实），
  V4 新层命名为 `memory/`（语义：**派生检索层**，永远不是 truth）。
* **Impact**：需要一次重命名（含测试引用），但消除长期歧义。

### CHALLENGE-03：`repair/` 与冻结的 M11 `repair.py` 冲突

* **Original Assumption**：新增 `repair/`（planner / executor / contracts / verifier）。
* **Codebase Evidence**：`story_engine/repair.py`（1,695 行）是 **M11 frozen Repair**，
  其 contract / gate digest 被 `m11_p15p.FROZEN_*_DIGESTS` 与 `export_package` 引用，
  且由 `tests/test_v2_frozen_guard.py` 守卫。
* **Problem**：新 `repair/` 会被误认为「M11 repair 的新版本」，而 M11 repair 是
  **历史内容修复流程**（修复 570 章历史 IR），与 V4 的「生成质量定向修复」不是同一业务对象。
* **Recommended Change**：新能力命名为 `quality/repair/`（Quality 的子能力），
  历史路径显式隔离到 `legacy/`（见 CHALLENGE-04）。
* **Impact**：命名一次到位，避免 frozen 语义被稀释。

### CHALLENGE-04：Master Plan 没有给 frozen 历史代码安排位置

* **Original Assumption**：目录只有 core/domain/ai/memory/generation/quality/repair/services/
  plugins/mcp/api/persistence/observability。
* **Codebase Evidence**：源码里有 **40+ 个冻结模块**（`m11_*.py` 18 个、`m12_*`…`m18_*` 7 个、
  `historical_ir.py` / `reconstruction.py` / `historical_adoption.py` / `repair.py`），
  合计约 12,000+ 行，且**不可删除**（frozen evidence + digest guard）。
* **Problem**：没有 `legacy/` 通道时，这些模块会长期散落在新目录里，
  使「哪些代码是 V4 的一部分」永远说不清；也让 `AGENTS.md` §11 的架构审计无法收敛。
* **Recommended Change**：新增顶层 `legacy/`（或 `persistence/legacy/` + `services/legacy/`），
  冻结模块整体迁入并**只允许只读调用**；`api` 层不再直接暴露 legacy 路由。
* **Impact**：V4 新目录保持干净；frozen 语义被显式表达。

### CHALLENGE-05：V4 的 AI / Quality / Structured Output 已有相当多现成资产

* **Original Assumption**：V4-02…V4-05 是「实现 LLM Gateway / Memory / Structured
  Generation / Quality Loop」。
* **Codebase Evidence**：
  * 真实模型调用已存在：`spec/llm.py`（DeepSeek，含 backoff、strict schema、作者确认门禁）；
  * 结构化输出契约已存在：`chapter_ir`（13 文件）+ `planning`（40 文件）+ `canon/schemas.py`；
  * 质量门已存在：9 处 deterministic validator / verifier（见 Principle 1.3）；
  * 上下文装配已存在：`WriterContextBuilder`（6 层 block + 跨块去重 + 预算 40）。
* **Problem**：把这些当 greenfield 重做，会浪费已验证资产，并与「不得为漂亮结构突破 frozen boundary」
  的原则冲突。
* **Recommended Change**：V4-02…V4-05 的定位改为
  **「把既有孤立能力提升为边界层（boundary layer）」**：LLM Gateway 收编 `spec/llm.py`
  并删除硬编码端点；Structured Generation 复用 ChapterIR/PlanningIR；
  Quality Loop 复用既有 validator 并补 Evaluator/Repair 编排。
* **Impact**：阶段目标不变，但实现路径从「新建」变「收编 + 补边界」，风险与工时都下降。

### CHALLENGE-06：`persistence/migrations/` 现在就引入数据库迁移框架为时过早

* **Original Assumption**：`persistence/{repositories,migrations,storage.py}`。
* **Codebase Evidence**：当前持久化是 **JSON 文件 + 单一 SQLite（Canon）**：
  `storage.py`（原子替换 + 单进程锁）、`profiles/`、`sessions/`、`outlines/`、`planning/`、
  `writer/`、`canon/*.sqlite`；`StoryState` 已有 `schema_version` + `upgrade_story_state_payload` 升级路径。
* **Problem**：在没有换存储引擎之前引入 migration 框架，会产生「第二套版本机制」，
  与既有 `schema_version` / `revision` 语义重复。
* **Recommended Change**：V4 只建立 **repository 层 + ownership 校验**，
  把 `migrations/` 标记为 `Deferred`；先统一 schema_version 与 revision 语义。
* **Impact**：V4-07（Delivery）之前不需要 DB 迁移能力。

### CHALLENGE-07：`generation/` 的模块清单与既有模块 1:1 重叠，必须复用既有模型

* **Original Assumption**：`generation/{premise,world,characters,story_arc,outline,
  chapter_plan,scene_plan,draft}.py`。
* **Codebase Evidence**：这些能力目前分布在 `creative.py`、`settings_gen.py`、
  `outline_forge.py`、`journey.py`、`planning/chapter_compiler.py`、`writer.py`；
  其输出模型已经存在（ContentPack / OutlinePackage / ChapterSemanticIR / StoryPlanningIR / WriterPackage）。
* **Problem**：新模块若重新定义输出模型，会与既有 canonical model 冲突。
* **Recommended Change**：`generation/` 只负责「调用 LLM → 产出既有模型」，
  不新增模型；每个 generator 的契约直接指向既有 pydantic 类。
* **Impact**：结构化生成的验收标准变成「能否通过既有 validator」，而不是「新 schema 好不好看」。

### CHALLENGE-08：Q0–Q9 不能取代既有 deterministic 防线

* **Original Assumption**：Q0 Schema / Q1 Safety / Q2 Canon / Q3 Continuity / Q4 Character /
  Q5 Causality / Q6 Semantic / Q7 Narrative / Q8 Style / Q9 Delivery。
* **Codebase Evidence**：现状里 Q0/Q2/Q3/Q5 已经分别由 `chapter_ir/schemas.py`、
  `canon/validator.py`、`canon/graph.py`、`planning/spine_analysis.py`、
  `chapter_ir/evidence.py` 等实现（deterministic）。
* **Problem**：如果 Q0–Q9 作为新层重写，会造成「同一质量结论两个来源」。
* **Recommended Change**：Q0–Q9 作为**统一门禁编号 + 统一 issue 契约**，
  每个 Gate 显式声明其实现来源（deterministic / llm / hybrid），既有 validator 直接注册进对应 Gate。
* **Impact**：见 `V4_QUALITY_CONTRACT.md` §4 的 Gate → 实现映射表。

---

## 3. Proposed Directory Tree

> 规则：**只保留真的需要的目录**；每个目录都有 owner；不引入暂时用不到的抽象。
> 标记 `[已存在]` 的表示该目录/文件在 V3 中已存在（迁移而非新建）。

```text
src/novelforge/
│
├── core/                       # 跨层基础件（无业务语义）
│   ├── ids.py                  # 统一 id / slug / digest 工具（吸收 _slug / runtime_key_for 等重复实现）
│   ├── errors.py               # 统一错误基类（吸收各模块 *Error 的重复 as_dict）
│   ├── result.py               # Result Envelope（REST / MCP 共用，见 V4_MCP_SPEC.md §5）
│   ├── revision.py             # revision / expected_revision / conflict 语义
│   └── schema.py               # [已存在] StrictModel 基类（现 src/novelforge/models.py）
│
├── domain/                     # 纯业务规则：不依赖 fastapi / mcp / provider / 文件系统
│   ├── story/                  # [已存在] story_engine 内核：state/actions/conditions/effects/
│   │                           #   resolver/events/delayed/foreshadow/progression/driver/
│   │                           #   director/characters/world/entities/profile/templates/content
│   ├── knowledge.py            # [已存在 story_engine/memory.py] 三视角知识（改名，见 CHALLENGE-02）
│   ├── canon/                  # [已存在] 稳定身份 / 图 / 校验 / 唯一写入口
│   ├── chapter_ir/             # [已存在] Chapter Semantic IR（V4 结构化生成的落点）
│   ├── planning/               # [已存在] Story Planning IR
│   ├── outline.py              # [已存在 story_builder/models.py + outlines.py 的模型部分]
│   └── route.py                # [已存在 story_engine/route_lab.py]
│
├── application/                # 用例编排（原 story_builder/）
│   ├── services/
│   │   ├── project_service.py      # 新建 / 重命名 / 归档（现 novel_admin + wizard）
│   │   ├── creation_service.py     # 创意 / 设定 / 自检（现 creative + settings_gen + settings_check）
│   │   ├── simulation_service.py   # 推演（现 driver + candidates + director）
│   │   ├── outline_service.py      # 四级大纲（现 outline_forge + outline_revision）
│   │   ├── blueprint_service.py    # Blueprint 节点编辑 / revision（原 writer_integration；
│   │   │                           #   正文 draft 仅保留为兼容预览，非核心 artifact）
│   │   ├── review_service.py       # 检查 / 修复（现 inspector + 新 Quality）
│   │   ├── export_service.py       # 唯一导出出口（现 export_package）
│   │   ├── journey_service.py      # JourneyProjection 唯一计算入口（现 v3_projection._journey_projection）
│   │   └── agent_service.py        # Agent 会话状态（V4-11 新增）
│   └── projections/                # [已存在 *_view.py / v3_projection 拆分] 只读 DTO
│
├── ai/                         # 模型调用边界（业务层唯一入口）
│   ├── gateway.py              # llm.generate(contract, context, model_policy)
│   ├── contracts.py            # GenerationContract / StructuredOutput
│   ├── router.py               # Creative / Critic / Repair / Utility 模型选择
│   ├── policy.py               # ModelPolicy（质量优先 / 成本优先 / 本地优先 / 预算）
│   ├── usage.py / trace.py     # token / cost / latency / prompt_contract 记录
│   ├── cache.py                # 安全缓存（embeddings / summaries / immutable 描述）
│   └── providers/
│       ├── base.py             # LLMProvider 协议
│       └── deepseek.py         # [已存在能力] 收编 spec/llm.py 的 HTTP 实现
│
├── memory/                     # 派生检索层：**永远不是 truth**（见 V4_MEMORY_ARCHITECTURE.md）
│   ├── store.py                # 记忆条目存储（novel_id + revision 归属）
│   ├── retrieval.py            # 检索 API
│   ├── context_builder.py      # 按任务构建上下文（收编 WriterContextBuilder 的分层/去重/预算设计）
│   ├── episodic.py / semantic.py
│   ├── author_preferences.py
│   └── compressor.py           # 摘要 / 压缩（可缓存产物）
│
├── generation/                 # 生成编排：调用 ai/gateway，产出**既有**模型
│   ├── premise.py              # 收编 creative.py
│   ├── settings.py             # 收编 settings_gen.py
│   ├── outline.py              # 收编 outline_forge.py
│   ├── chapter_plan.py         # 收编 planning/chapter_compiler.py
│   ├── scene.py                # 收编 journey.py
│   └── draft.py                # 收编 writer.render_scene / fallback_text（fallback 不进入交付物）
│
├── quality/                    # 质量能力（业务能力，不是测试脚本）
│   ├── contracts.py            # QualityIssue / Evidence / Status / Severity / Scope / RepairContract
│   ├── service.py              # 评估编排（Q0–Q9）
│   ├── gates/                  # 每个 Gate 的实现归属（含既有 validator 的注册）
│   │   ├── schema.py           # 复用 chapter_ir/schemas.py + canon/gate.py
│   │   ├── canon.py            # 复用 canon/validator.py + canon/graph.py
│   │   ├── continuity.py       # 复用 canon/graph.py + planning/narrative_analysis.py
│   │   ├── semantic.py         # 复用 chapter_ir/verifier.py + semantic_judge.py
│   │   └── delivery.py         # 新：交付物校验（见 V4_EXPORT_SPEC.md §4）
│   └── repair/                 # 定向修复（与 frozen M11 repair 明确区分）
│       ├── planner.py / executor.py / verifier.py
│
├── plugins/                    # 扩展点（V4-09）
│   ├── base.py / registry.py / loader.py / permissions.py
│   └── builtin/
│
├── interfaces/                 # 契约入口：只做协议转换，不含业务规则
│   ├── api/                    # [已存在 src/novelforge/api] FastAPI 路由（薄）
│   ├── mcp/                    # resources/ tools/ prompts/ schemas/
│   └── cli/                    # 可选：批处理入口（Deferred，暂不建）

V4-10 产品面（已落地）：

```text
Story Studio（ui/src/studio/**，默认产品面）
        ↓  HTTP（ui/src/api/studio.ts，唯一客户端）
REST Adapter（src/novelforge/api/{studio,editor,delivery,canon}_routes.py，薄路由）
        ↓
Application Services（application.services.**）
        ↓
V4 modules（blueprint / quality / editor / delivery / plugins）

并行 adapter：MCP（interfaces/mcp）与 REST 平级；UI 不得经 MCP 调自己的后端。
兼容入口：?ui=v3（V3 工作台）/ ?ui=v2（V2 面板）—— 见 ADR-032。
```
│
├── persistence/                # 基础设施：唯一允许碰文件系统 / SQLite 的地方
│   ├── story_state.py          # [已存在 storage.py]
│   ├── profile.py / content_pack.py / session.py / blueprint.py / outline.py
│   ├── blueprint_store.py      # canonical Story Blueprint store（唯一）
│   ├── writer_store.py         # 兼容层：既有 writer draft（preview，不再作为 canonical artifact）
│   ├── canon_repo.py           # [已存在 canon/repository.py]
│   ├── planning_repo.py        # [已存在 planning/repository.py]
│   └── paths.py                # 所有路径常量的唯一来源（消灭模块级硬编码单作品路径）
│
├── observability/
│   ├── logging.py / metrics.py / audit.py / token_usage.py
│
└── legacy/                     # 冻结历史隔离区（新增，见 CHALLENGE-04）
    ├── m11/                    # m11_*.py
    ├── milestones/             # m12_*…m18_*、milestone_acceptance、phase_snapshot
    ├── historical_ir.py / reconstruction.py / historical_adoption.py / repair.py
    └── README.md               # 「只读、不可改、不可扩展」
```

### 3.1 与 Master Plan 的差异（逐项）

| Master Plan 目录 | V4 决定 | 原因 |
| --- | --- | --- |
| `core/` | **保留**（收编 `models.py`、`_slug`、错误类、revision） | 现在这些散落在 8+ 模块 |
| `domain/` | **保留但原地迁移** | 见 CHALLENGE-01；不新建平行模型 |
| `ai/` | **保留**（`spec/llm.py` 收编为一个 provider） | 已有真实 HTTP 调用需要归位 |
| `memory/` | **保留，但先给 `story_engine/memory.py` 改名** | 见 CHALLENGE-02 |
| `generation/` | **保留，模块数量减少**（6 个而非 8 个） | `world/characters/story_arc` 由 outline/settings 覆盖，无需独立模块 |
| `quality/` | **保留**，新增 `gates/`（映射既有 validator） | 见 CHALLENGE-08 |
| `repair/` | **降级为 `quality/repair/`** | 见 CHALLENGE-03 |
| `services/` | **改名 `application/services/`** | 与 `mcp/tools`、`plugins` 区分「业务服务」与「协议工具」 |
| `plugins/` | **V4-09 已落地**（`src/novelforge/plugins/`，DEFERRED → NEW） | 扩展点从"必须改核心代码"变为"注册贡献"；契约见 `V4_PLUGIN_CONTRACT.md` |
| `mcp/` | **改名 `interfaces/mcp/`**，与 `api/` 同级 | MCP 是接口层，不是独立能力层 |
| `api/` | **改名 `interfaces/api/`** | 同上 |
| `persistence/` | **保留**，`migrations/` 标记 Deferred | 见 CHALLENGE-06 |
| `observability/` | **保留但初期只做 logging + token_usage** | 现在没有任何 trace/cost 基础设施，一次做全必然过度设计 |
| `legacy/`（新增） | **必须存在** | 见 CHALLENGE-04 |

### 3.2 暂时**不**建的抽象（避免过度设计）

| 抽象 | 为什么现在不建 | 何时重新评估 |
| --- | --- | --- |
| `persistence/migrations/` | 存储仍是文件 + 单 SQLite；已有 `schema_version` 升级路径 | 真正更换存储引擎时 |
| 事件总线 / message queue | 单进程、单用户、无并发写需求（`storage.py` 明确单进程锁） | 出现多进程 / 云端部署需求时 |
| 分布式锁 / 多租户 | 同上 | 同上 |
| 向量数据库 | `memory/retrieval.py` 先做结构化检索（实体 / 章节 / 伏笔索引）即可满足第 N 章上下文需求 | 结构化检索命中率经测证实不足时 |
| Plugin 市场 / 版本仓库 | 先只支持本地 `novel/config` 与已声明 capability | 出现第二个第三方扩展者时 |
| `interfaces/cli/` | REST + UI 已覆盖所有用例 | 出现批处理交付需求时 |

---

## 4. 分层职责与依赖规则

### 4.1 每层的 Responsibility / Allowed / Forbidden / State Ownership

| 层 | Responsibility | Allowed Dependencies | Forbidden Dependencies | State Ownership |
| --- | --- | --- | --- | --- |
| `interfaces/api` | HTTP 协议转换、参数校验、错误码映射 | `application.services`、`core.result` | `domain.*` 直接调用、`persistence.*`、文件路径、`ai.*`、`mcp.*` | 无（不持有状态） |
| `interfaces/mcp` | MCP resource / tool 协议转换、参数校验、ownership 绑定、错误映射 | `application.services`、`core`（ids / errors）、官方 MCP SDK | `domain.*` / `persistence.*` / `ai.*` / 文件路径 / HTTP client / 自建业务规则 | 无（per-novel service 缓存 + invocation 记录） |
| `application.services` | 用例编排、事务边界、权限判断、事件顺序、质量循环触发 | `domain.*`、`persistence.*`、`ai.gateway`、`memory.*`、`quality.service` | `interfaces.*`、`fastapi`、React、provider SDK | **编排状态**（会话、批次、agent session） |
| `application.projections` | 只读 DTO（视图模型后端侧） | `domain.*`、`persistence.*` | 写操作、provider 调用 | 无（纯派生） |
| `domain.*` | 业务规则与不变量 | 标准库、`pydantic`、`core.*`、同层 domain | `fastapi`、`mcp`、`openai`/SDK、`persistence`、文件系统、React、网络 | StoryState / Canon / ChapterIR / PlanningIR 的**语义** |
| `ai.gateway` | 模型调用唯一入口：contract / context / policy / retry / timeout / usage / trace / cache | `core.*`、`ai.providers` | `domain.*`、`application.*`、`persistence.*` | 调用记录（usage / trace / cache key） |
| `ai.providers` | 具体厂商适配 | `core.*` | 知道 NovelForge 的任何业务概念 | 无 |
| `memory.*` | 派生检索与上下文装配 | `persistence.*`（只读）、`ai.gateway`（embedding/summary） | 写 StoryState / Canon | 派生索引（**可重建**，非 truth） |
| `generation.*` | 生成编排 → 既有 domain 模型 | `ai.gateway`、`memory.*`、`domain.*`（模型定义） | 直接读写文件、直接写 StoryState | 无（产出 proposal） |
| `quality.*` | 评估 / 门禁 / 定向修复编排 | `blueprint`（只读）、`ai.gateway`（critic）、`memory.*`（只读）、`core`、`persistence.paths`；`quality/repair` 另允许 `generation` Public Contract | 直接写 truth（Canon / StoryState）、修改 Blueprint 节点、绕过 approval、被下层反向依赖 | Quality Store（report / issue / evidence / repair history）；不拥有 story truth |
| `editor.*` | 作者编辑 / 比较 / 审批 / 恢复 / 审计（Blueprint revision 工作流） | `blueprint`、`generation` Public Contract、`core`、`persistence.paths`；Quality 由 Application 层组合 | 自建 Blueprint store、写 Canon / StoryState、自动语义 merge、被下层反向依赖 | editor metadata（operation / review / session）；不拥有 story truth |
| `delivery.*` | 交付编排：选择 revision → 快照 → 校验 → 编译 → 导出 → manifest | `blueprint`、`quality`（Quality Store 只读）、`editor`（metadata 只读）、`core`、`persistence.paths` | 调用 LLM、修 Quality issue、修改 Blueprint / Canon / StoryState、自行拼路径、被下层反向依赖 | 交付快照 / manifest / artifact；不拥有 story truth |
| `plugins.*` | 插件发现 / 批准 / 启用 / 贡献注册（exporter · quality evaluator · MCP tool·resource） | `core`、`persistence.paths`、`quality` / `delivery` registry 契约、`interfaces.mcp` registry 契约；`plugins.host`（composition root）另允许 `application.services` | **直接操作数据库 / 文件系统 / 绕过 service**、覆盖 Core 注册、import api / ui / ai.providers / repository / store | Plugin state（按 novel+plugin 隔离，非 story truth）+ enablement / audit（host 级） |
| `persistence.*` | 唯一物理存储访问点 | `core.*`、`domain.*`（模型定义） | `interfaces.*`、`ai.*`、`application.services`（反向依赖） | 物理存储 |
| `observability.*` | 日志 / 指标 / 审计 / token 用量 | `core.*` | 业务规则 | 遥测数据 |
| `legacy.*` | 冻结历史能力的只读封装 | 只读访问历史证据 | 被新业务路径写入依赖 | frozen 证据（不可变） |

### 4.2 Allowed Dependency Matrix

行 = 依赖方，列 = 被依赖方。`✓` 允许，`✗` 禁止，`△` 仅通过显式 Port。

| ↓依赖 / 被依赖→ | core | domain | application | ai | memory | generation | quality | plugins | interfaces | persistence | observability | legacy |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `core` | ✓ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ |
| `domain` | ✓ | ✓ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ |
| `application` | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | △ | ✗ | ✓ | ✓ | △ |
| `ai` | ✓ | ✗ | ✗ | ✓ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✓ | ✗ |
| `memory` | ✓ | ✓ | ✗ | ✓ | ✓ | ✗ | ✗ | ✗ | ✗ | △ | ✓ | ✗ |
| `generation` | ✓ | ✓ | ✗ | ✓ | ✓ | ✓ | ✗ | ✗ | ✗ | ✗ | ✓ | ✗ |
| `quality` | ✓ | ✓ | ✗ | ✓ | ✓ | ✗ | ✓ | ✗ | ✗ | △ | ✓ | ✗ |
| `plugins` | ✓ | ✗ | △ | △ | ✗ | ✗ | △ | ✓ | △ | ✓ | ✗ | ✗ |
| `interfaces` | ✓ | ✗ | ✓ | ✗ | ✗ | ✗ | ✗ | ✓ | ✓ | ✗ | ✓ | ✗ |
| `persistence` | ✓ | ✓ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✓ | ✓ | ✓ |
| `observability` | ✓ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✓ | ✗ |
| `legacy` | ✓ | ✓ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✓ | ✓ | ✓ |

### 4.3 明文禁令（对应 Master Plan §9 的举例）

```text
Domain       → 不允许依赖 MCP
Domain       → 不允许依赖 FastAPI
Domain       → 不允许依赖 React
Domain       → 不允许依赖 OpenAI / DeepSeek SDK 或任何 HTTP client
Domain       → 不允许直接读写文件（必须经 persistence Port）
MCP          → 只允许依赖 application service interface
UI           → 只允许通过 API / approved client 调用业务能力
LLM Provider → 不允许知道 NovelForge 的任何业务概念（只认 messages / 模型 / 参数）
Plugin       → 不允许直接修改核心数据库 / 文件系统
Legacy       → 不允许被新的写路径依赖
UI（Story Studio）→ 只经 HTTP：UI → REST Adapter → Application Services；
               REST 与 MCP 是**平级 adapter**（UI 不得走 MCP 调自己的后端）
UI           → 不推导业务事实（ADR-033）；默认产品面 = Story Studio，
               V3/V2 为显式兼容入口（?ui=v3 / ?ui=v2，ADR-032）
Plugin       → 不允许覆盖 Core 注册（exporter format / MCP tool / MCP resource /
               quality evaluator / issue code）
Plugin       → 不允许 import api / ui / ai.providers / BlueprintRepository /
               QualityStore / DeliveryStore，不允许自拼 story artifact 路径
Core / 业务模块 → 不允许 import novelforge.plugins（Core 不依赖具体插件）
interfaces   → 不允许 import novelforge.plugins（只消费注入的 registry）
```

**验收方式（V4-01 起）**：新增 import 边界测试（类似现有
`tests/test_story_engine_cross_genre.py` 的源码守卫写法），把上表转成可执行断言。

---

## 5. 九条边界的正式定义

| 边界 | 正式定义 | 当前实现 | V4 动作 |
| --- | --- | --- | --- |
| **Service 边界** | 唯一业务入口是 `application.services`；路由 / MCP / UI 一律薄 | `api/story_builder_routes.py` 1,545 行含内联编排 | V4-01 拆薄 |
| **LLM 边界** | `ai.gateway.llm.generate(contract, context, model_policy)`；业务层禁止直接调 SDK | ✅ V4-02 已收编：`novelforge.ai` 是唯一入口；3 个 legacy 调用点（spec / plot / route）改为经 `ai.legacy_support` 调用，全仓再无自带 HTTP 的模型调用 | V4-02 完成 |
| **Memory 边界** | Canon / StoryState 是 truth；`memory/*` 是派生、可重建、非权威 | ✅ V4-03 已落地：`novelforge.memory`（检索契约 + 四类视图 + 偏好 + ContextBuilder），条目带 source_ids / revision / stale 语义；`story_engine/memory.py` 保持原义不改名 | V4-03 完成 |
| **Quality 边界** | 每次生成经过 QualityService；issue 是业务对象 | ✅ V4-05 已落地：`novelforge.quality`（Q0–Q9 evaluator + code registry + Quality Store）、`quality/repair`（minimal-scope / revisioned repair）、`application.services.ReviewService`（闭环编排）；判定是 gate-based，不是分数（ADR-018） | V4-05 完成 |
| **Editor 边界** | 作者通过 Editor 掌握生成结果；Editor 不拥有 story truth | ✅ V4-06 已落地：`novelforge.editor`（patch / diff / history / rewrite / accept / reject / restore / move / audit）+ `application.services.EditorService`（组合 editor + quality + generation）；全部 mutation 是 append-only revision（ADR-021） | V4-06 完成 |
| **Export 边界** | 唯一 `ExportService`；不允许 UI / API 各自拼产物 | ✅ V4-07 已落地：`novelforge.delivery`（selection → snapshot → validator → compiler → exporters → manifest）+ `application.services.export.ExportService` 作为唯一 facade；交付 revision-pinned、只读、0 LLM 调用（ADR-024/025/026） | V4-07 完成 |
| **Blueprint 边界** | canonical Story Blueprint = `blueprint` 节点图 + repository；生成只产出 proposal | ✅ V4-04 已落地：`novelforge.blueprint` + `novelforge.generation`（逐级生成 / 局部重生成 / revision / 幂等 / 结构校验） | V4-04 完成 |
| **MCP 边界** | MCP 只是协议；tool 调 service；统一 Result Envelope | ✅ V4-08 已落地：`interfaces/mcp`（MCPDispatcher + Tool/Resource 注册表 + 稳定错误映射 + 分页 + 净化），只依赖 `application.services`；官方 MCP SDK 提供 stdio transport（ADR-027/028） | V4-08 完成 |
| **Plugin 边界** | 插件通过 Registry 注册，声明 capability，经 Port 访问核心 | 不存在 | V4-09 新建 |
| **Revision 边界** | 每个 artifact 带 `revision`；写操作带 `expected_revision` | blueprints / outlines / planning / StoryState 各自实现 | V4-01 统一语义 |
| **Ownership 边界** | 每个 artifact 带 `project_id` / `novel_id` / `revision` / `created_at` / `source_ids` | `wasteland_001` 曾硬编码于 4 个模块；`novel/final/*.md` 与 570 章 historical 已由 V4-01 删除 | V4-01（已落地路径边界）+ V4-07 |

---

## 6. Canonical Sources of Truth（回答 DoD 的 Ownership 问题）

| 问题 | 答案（V4） | 当前 V3 事实 | 迁移动作 |
| --- | --- | --- | --- |
| **canonical creative artifact 是什么？** | **`StoryBlueprint`**（Premise / Characters / Arcs / Scene Cards / Causal Graph / Setup-Payoff / Quality / Revision）。正文不是 canonical artifact（V4-01 决策 C） | 当前没有 Blueprint 模型；最接近的是 `OutlinePackage`（四级大纲）+ `ChapterSemanticIR` + `StoryPlanningIR` | V4-04 建立 Blueprint contract；V4-06 Blueprint Editor |
| **正文还归谁管？** | **不属于 V4 Core**。`WriterDraftService` 的 preview 草稿仅作兼容保留；`novel/final/*.md` 已删除 | `novel/final/*.md`（69 个 tracked 文件）已由 V4-01 删除；`writer/<novel_id>/drafts/*.json` 保留为 preview | 无（正文能力若需要，走 Plugin / 下游 Agent） |
| **StoryState 谁拥有？** | `persistence.story_state`（现 `story_engine/storage.py`），唯一写入口 `ActionResolver` | 已成立 | 保持；补 `expected_revision` |
| **Canon 谁拥有？** | `persistence.canon_repo`（现 `canon/repository.py`），唯一允许写 SQL 处；`CanonService` 管稳定身份生命周期 | 已成立，但 DB 路径按作品硬编码 | V4-01 参数化 `novel_id` |
| **Journey 谁计算？** | `application.services.journey_service` 的**唯一** `JourneyProjection`；Landing / Command Center / API / MCP 全部消费它 | `v3_projection._journey_projection()` 已是唯一入口；但 `ui_flow.py` 另有一套 stage / next-step | V4-01 收敛为 1 个投影 |
| **Export 从哪里读取？** | `ExportService` 只通过 repository 读：profile / content pack / StoryState / outline / canon（按 `novel_id`）/ Blueprint 节点；**不再有全局 hardcode 路径，也不含历史分区** | `export_package.build_export_projection()` 曾混用 5 类来源 + 3 个硬编码路径（V4-01 已移除历史分区与单作品路径） | V4-07 重构为 Story Blueprint Package |
| **What does the model see?** | `memory.context_builder` 按 contract 构建上下文（对应第 N 章：chapter plan + 最近 3 章 episodic + 相关角色/地点 + 当前 StoryState + 相关 Canon + 未完成伏笔 + 作者偏好） | `WriterContextBuilder` 的 6 层 block + 去重 + 预算 40 已经很接近 | V4-03 提升并参数化 |

### 6.1 Canonical 与非 canonical 对照

```text
canonical（唯一）
  StoryBlueprint      → 核心创作产物（V4 目标；承载 Premise / Arc / Scene / Setup-Payoff）
  StoryState          → 已发生事实
  Canon (sqlite)      → 稳定事实身份 + lineage
  ChapterSemanticIR   → 章节机器语义（Blueprint 的结构子集）
  StoryPlanningIR     → 规划 revision
  OutlinePackage      → 四级大纲
  ContentPack         → 起点世界事实声明

derived（可重建，永远不是 truth）
  JourneyProjection / 所有 *_view / Command Center DTO
  ExportProjection / nfpack
  memory/*（episodic / semantic / embeddings）
  QualityResult / 报告 / 统计

compatibility-only（非核心，保留但不再扩展）
  writer/<novel_id>/drafts/*.json（预览草稿；非 canonical artifact）

V4-01 已删除（作者判定为废弃资产）
  novel/final/**（69 个 tracked 正文文件）
  workspace/wasteland_001_exports/**（570 章 historical / M11 证据 / 旧导出）
```

---

## 7. Revision 与 Ownership 模型

### 7.1 每个 artifact 的最小字段

```json
{
  "project_id": "…",
  "novel_id": "…",
  "revision": 42,
  "created_at": "2026-09-17T00:00:00Z",
  "source_ids": ["story_state:runtime_novel_project@12", "chapter_ir:ch_018@3"]
}
```

### 7.2 现有版本机制（可直接继承，不必重造）

| 对象 | 现状 | V4 语义 |
| --- | --- | --- |
| StoryState | `v%06d[_branch].json` | revision = 文件序号；branch 独立 |
| Blueprint | `v*.json` + `story_revision` | revision + 来源 session |
| Outline | `v*.json` + version diff / restore / merge | revision + 父 revision |
| Planning IR | 不可变 revision + index | 已是「append-only revision」范式 |
| Phase snapshot | write-once + digest manifest | 冻结证据的 revision 先例 |
| WriterDraft | 无 revision，仅 `draft_id` 哈希 | **V4 必须补**（当前无法回答「改了什么」） |

### 7.3 写入协议

```text
写请求
  → 携带 expected_revision
  → service 校验 current_revision == expected_revision
  → 不等 → conflict（不覆盖、不合并）
  → 相等 → 产生新 revision（append-only）+ source_ids
```

对 Agent / MCP 额外要求 `request_id` + `idempotency_key`（`V4_MCP_SPEC.md` §4）。

---

## 8. 事件与执行顺序（V4 主链）

```text
作者 / Agent / UI
   │  Command（带 expected_revision）
   ▼
application.services.<domain>_service
   │
   ├─▶ memory.context_builder      （要哪些上下文？）
   ├─▶ ai.gateway.llm.generate     （contract + context + policy）
   ├─▶ domain validators           （schema / 业务不变量）
   ├─▶ quality.service.evaluate    （Q0–Q9）
   │        └─ FAIL → quality.repair.planner → 定向修复 → 重新 evaluate
   ├─▶ persistence.<repo>          （写入新 revision，append-only）
   └─▶ observability               （request_id / tokens / cost / trace）
   ▼
Result Envelope（REST / MCP 同构）
```

---

## 9. V4-00 的 Architecture Definition of Done

| DoD 问题 | 答案所在 |
| --- | --- |
| V4 每一层负责什么？ | 本文 §3、§4.1 |
| canonical artifact（StoryBlueprint）/ StoryState / Canon / Journey / Export 归属？ | 本文 §6 + §0.A |
| 业务代码如何用模型但不依赖 provider？ | 本文 §4.1 + `V4_LLM_CONTRACT.md` |
| 生成第 N 章时上下文从哪来？ | `V4_MEMORY_ARCHITECTURE.md` §5 |
| 失败后谁发现 / 计划 / 执行 / 验证？ | `V4_QUALITY_CONTRACT.md` §7 |
| Agent 如何操作但 MCP 不成为业务层？ | `V4_MCP_SPEC.md` §2 |
| V3 如何一步步迁移？ | `V4_MIGRATION_PLAN.md` |
| 哪些 V3 代码会消失、何时可安全删除？ | `V4_DELETION_PLAN.md` |

---

## 10. 本文件的 Status 说明

```text
已确定（可执行）：
  §1 原则、§4 依赖规则、§5 九条边界、§6 ownership、§7 revision 模型
  —— 这些与 V3 事实一致，且不触碰 frozen boundary

Proposed（需要作者确认后才开工）：
  §3 目录树的目录重命名与迁入 legacy/（CHALLENGE-01/03/04）
  §6 「正文 owner = ChapterRevision」的具体形态（依赖作者对 novel/final 的裁定）
  §3.2 中标记 Deferred 的抽象

不得在 V4-00 期间执行：
  任何代码移动、重命名、删除、migration
```
