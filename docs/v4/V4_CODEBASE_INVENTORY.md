# NovelForge V4 — V3 Codebase Inventory

> 阶段：**V4-00 Architecture**（analysis / design only）
> 基线：`novelforge-product-v3-final`（commit `f02ca8c`）
> 分支：`v4/00-architecture`
> 本文件是 V3 代码库的事实清单。**它不是计划，不是愿望，也不是评分。**
> 所有条目都以磁盘真实状态为准（2026-09-17 扫描）。

---

## 0. 扫描范围与方法

### 0.1 扫描命令（可复现）

```powershell
git status --porcelain=v1 --branch ; git branch -a ; git tag ; git log --oneline -5
Get-ChildItem -Path src -Recurse -File -Include *.py | measure
Get-ChildItem -Path ui/src -Recurse -File -Include *.ts,*.tsx | measure
.venv\Scripts\python.exe -m pytest -q          # 基线：892 passed / 687 deselected
.venv\Scripts\python.exe scripts/validate_project.py
```

### 0.2 规模事实

| 区域 | 文件数 | 行数 | 说明 |
| --- | --- | --- | --- |
| `src/`（Python） | 188 | 68,038 | 后端全部代码（含 frozen 历史路径） |
| `ui/src/`（TS/TSX） | 45 | 10,482 | V3 工作台 + 既有高级工具面板 |
| `tests/*.py` | 171 | 31,118 | 默认 892 通过 / 687 为 `historical_acceptance` |
| `tests/*.cjs` | 20 | — | 真实浏览器门禁（Playwright） |
| `novel/config/**` | 103 | — | 题材模板 / 内容包 / 十步目录 / schema（数据） |
| `scripts/` | 6 | 677 | 启动 / 校验 / 隔离测试服务 / 历史 closeout |
| `novel/final/*.md` | 69 | — | **已在版本控制中的既有正文**（无产品代码读取） |
| `novel/authoring/**` | 2,381 | — | 运行期作者数据（Canon / StoryState / 大纲 / 草稿） |
| `workspace/**` | 254 | — | gitignored 历史导出与 frozen 证据（含 570 章 IR） |

### 0.3 粒度策略（重要）

同类重复模块（例如 `m11_run02.py` … `m11_run12.py`，`m13_*` … `m18_*`，`*_view.py` 面板投影）在
本清单中**按家族合并成一行**，并在 `Notes` 中给出成员文件与行数范围。目的：

```text
准确分类 > 行数漂亮
```

任何单独列出的一行都经过实际阅读（docstring / 关键函数 / 关键调用点），未读到的细节写
`UNKNOWN` 并说明还缺什么证据，不猜测。

---

## 1. 顶层仓库地图

| Path | 类型 | 内容 | 状态 |
| --- | --- | --- | --- |
| `AGENTS.md` | 仓库规则 | 执行约束 SSOT | KEEP |
| `README.md` / `docs/*.md` | 文档 | 产品入口 / 架构 / 数据模型 / 兼容边界 | KEEP |
| `src/novelforge/` | 后端代码 | `api` / `story_builder` / `story_engine` | 见 §2 |
| `ui/` | 前端 | `ui/src/v3/`（V3 工作台）+ `ui/src/`（高级工具） | 见 §6 |
| `novel/config/` | 数据 | 模板 / 内容包 / 目录 / schema | KEEP |
| `novel/authoring/` | 运行数据 | 作者产物（大部分 gitignored） | KEEP（boundary） |
| `novel/final/`、`novel/state/`、`novel/pipelines/`、`novel/learning/`、`novel/runs/`、`novel/workspace/` | 历史内容数据 | 正文 / 状态 / 生产管线产物 | 见 §7 |
| `workspace/` | gitignored | 历史导出 / frozen 证据 / 归档作品 | 见 §4.4 |
| `scripts/` | 工具 | 启动 / 校验 / 测试服务 | 见 §8 |
| `tests/` | 测试 | 默认套件 + historical 隔离套件 + 浏览器门禁 | KEEP |

---

## 2. 后端 Inventory

字段含义：`Class` = 本文件给出的 V4 分类（定义见 `V4_MODULE_CLASSIFICATION.md`）。

### 2.1 入口与 API

| Path | Module | Current Responsibility | Inputs → Outputs | Deps | State Ownership / Persistence | External Side Effects | Used By | Tests | Class | Notes |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `src/novelforge/api/app.py` | FastAPI app | 组装 app；挂 `/api/story-builder/*`、`/api/canon/*`、`/api/health`、`index.html`、`/assets` | — → ASGI app | story_builder_routes / canon_routes / StaticFiles | 无 | 读 `ui/dist` | `scripts/start_novelforge_ui.py`、`scripts/validate_project.py` | `test_product_surface.py` | KEEP | 22 行；路由前缀断言在 `validate_project.py` |
| `src/novelforge/api/story_builder_routes.py` | 路由 + 内联编排 | **唯一业务入口**：novels CRUD、creative、settings、runtime、outline、route lab、inspector、repair、export、writer、V3 投影、sessions/blueprints | HTTP → JSON | 直接 import 12+ 业务模块（`story_engine.*`、`story_builder.*`） | 通过被调模块间接写 profile / pack / StoryState / outline / drafts | 写文件（经 domain）、生成 docx | UI 全部 | `test_story_builder_api.py`、`test_story_builder_runtime_api.py` 等 | REWRITE | 1,545 行；**必须**拆成 service + thin routes（V4 边界成立的前提） |
| `src/novelforge/api/canon_routes.py` | Canon API | 只读 facts/events/entities/knowledge/foreshadows/graph/validate + `POST rebuild` / `validate-outline` | HTTP → JSON | `story_engine.canon.*` | 读 `canon/wasteland_001.sqlite`（硬编码路径） | 写 SQLite（rebuild） | UI Canon 检查器、修复中心 | `test_canon_*`（14 个） | MIGRATE | `DEFAULT_NOVEL_ID` 默认值 + 单库路径需按 `novel_id` 参数化 |
| `src/novelforge/models.py` | 共享基类 | `StrictModel`（strict + frozen 配置） | — | pydantic | 无 | 无 | 全后端 | 间接 | KEEP | 3 行，价值高 |
| `src/novelforge/author_language.py` | 展示映射 | 内部 id → 作者语言的唯一映射表（角色 / 地点 / 支线 / 伏笔 / 资源 / 状态 / 行动类别） | pack / profile → label | `content` | 无 | 无 | API 文案、V3 投影、导出、错误文案 | 间接（多个 v3 测试） | KEEP | V4 应升级为 i18n/label service 的种子 |

### 2.2 story_builder（Application 层）

| Path | Module | Current Responsibility | Inputs → Outputs | Deps | State / Persistence | Side Effects | Used By | Tests | Class | Notes |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `story_builder/models.py` | DTO | Outline 四级模型 / `StoryStep` 十步 / Blueprint / RouteSource 约束 | dict → pydantic 模型 | pydantic | 无 | 无效 | sessions / blueprints / outlines / api | `test_story_builder_models.py` | KEEP | 399 行，结构清晰 |
| `story_builder/catalog.py` | 目录 | 从 `novel/config/story_builder/step_catalogs.yaml` 载入十步目录 | YAML → catalog | yaml | 只读 | 无 | api `/catalogs`、`/steps/{id}` | `test_story_builder_catalog.py` | KEEP | 配置不是事实（§15 AGENTS.md） |
| `story_builder/sessions.py` | 会话 | 十步会话、选择、回退、历史、保存 | HTTP → session JSON | config/catalog/models | 写 `novel/authoring/story_builder/sessions/` | 写 JSON | api、creator_context | `test_story_builder_sessions.py`（747 行） | KEEP | 无 `novel_id` 之外的 revision 语义 |
| `story_builder/blueprints.py` | 蓝图 | 蓝图版本、确认状态、按 session 派生 blueprint_id | session → blueprint | sessions/models | 写 `.../blueprints/<id>/v*.json` | 写 JSON | creator / outline | `test_story_builder_blueprints.py` | KEEP | 已有版本机制，是 V4 revision 模型的可复用先例 |
| `story_builder/design_tree.py` | 设计树 | 设计节点视图与保存 | HTTP → design view | catalog/sessions | 经 sessions 写 | 写 JSON | api、UI DesignTreePanel | `test_story_builder_design_tree.py` | KEEP | 65 行 |
| `story_builder/outlines.py` | 大纲仓库 | 四级大纲包存储 / 版本 / 编译 / 导出（md/json/docx） | package → artifact | models/storage | 写 `novel/authoring/story_builder/outlines/<level>/` | 写 JSON、生成 docx | api、outline_forge、export | `test_story_builder_outlines.py`（+ forge/revision 测试） | REWRITE | **导出能力分散点之一**（与 `export_package` 并存） |
| `story_builder/adventures.py` | legacy 旅程适配 | 旧 `JourneyRuntime` 存档读 / fork / 选择（rules_version 1/2） | HTTP → adventure JSON | journey/storage | 写 `.../adventures/` | 写 JSON | api（branch 路由）、`ui/src/*` legacy | `test_story_builder_adventures.py`、`test_story_builder_branch_isolation.py` | COMPATIBILITY_ONLY | 新旅程为 `rules_version = 3`，Adventure 已降级为镜像 |
| `story_builder/recommendations.py` | 规则推荐 | 十步设计节点的**规则式**候选 / 推荐理由 | catalog + session → 候选 | catalog/models | 无 | 无 | api `/sessions/{id}/recommendations` | `test_story_builder_recommendations.py` | REPLACE_BY_LLM | 候选文案为模板化规则，无 LLM |
| `story_builder/ai_recommendations.py` | AI 补充 | `AIRecommendationSupplementer`：provider 鸭子类型调用 `generate_structured`，把 AI 输出**合并**进规则候选（越界 id 丢弃） | provider → 合并候选 | recommendations | 无持久化（由 session 承载） | 潜在网络调用（provider 注入） | api（recommendations 路由） | `test_story_builder_ai_recommendations.py` | REWRITE | 已有「AI 只能补充、不能新增结构」的边界意识 → 是 V4 `LLM Contract` 的良好输入 |
| `story_builder/ui_flow.py` | 引导流投影 | 引导流状态 / 下一步 / 影响范围 / 总览 / 区域 / 关系（只读） | profile+state → DTO | creator/world_view | 无 | 无 | api `/guided-flow`、`/settings/*`、旧面板 | `test_story_builder_guided_flow.py` | MIGRATE | **第二套 stage 词表**（`design/occurred/output/governance`）与 `v3_projection.V3_STAGES` 并存 |
| `story_builder/inspector.py` | 跨层检查 | Canon / StoryState / 历史 IR 的只读检索与修复诊断 + provenance | novel_id → records | canon / historical_ir / repair | 只读 | 无 | api `/inspector/*`、`/repair/diagnosis|history` | `test_m15_canon_inspector.py`(historical) | MIGRATE | `CANON_DB = ".../canon/wasteland_001.sqlite"` **硬编码单作品路径** |
| `story_builder/export_package.py` | **Export projection** | Story Bible / 卡片 / Timeline / Spine / Outline / Planning / canon_refs / historical_ir 单一 projection + json/markdown/docx serializer + validation | novel_id, branch → artifact | canon / historical_ir / outline_forge / world_view / m11_p15p | 只读（写由 API 层下载） | 生成 docx/md/json 字节 | api `/export/package`、`/export/writer-bundle`、UI ExportFlow | `test_m16a_planning_export.py`(historical)、`test_v3_review_export_projection.py` | REWRITE | **NR-002 根因**：`RECON_DIR` / `PLANNING_INDEX` / `canon/wasteland_001.sqlite` 写死在产品代码里 |
| `story_builder/writer_integration.py` | **Writer 集成 + 草稿 SSOT** | `WriterContextBuilder`（6 层 block + 去重 + 预算）、`WriterDraftService`（create/list/get/sync-facts）、`writer_export_bundle` | novel_id, chapter → context / draft | creator / storage / writer / memory_view / outline_forge | **写 `novel/authoring/story_engine/writer/<novel_id>/`**（唯一 canonical 草稿存储） | 写 JSON | api `/writer/*`、`/export/writer-bundle`、v3_projection | `test_m16b_writer_integration.py`(historical)、`test_v3_*` | REWRITE | 只有 create/read/sync，**没有 update/PATCH**（草稿不可编辑）；`CANON_DB` 亦硬编码 |
| `story_builder/v3_projection.py` | **V3 只读投影（最大模块）** | AuthorJourney / Objective / NextAction / Command Center / 实体 / 推演 / 大纲章节 / 检查修复 / 导出就绪度 | novel_id → 全部 V3 DTO | creator / settings_* / outline_forge / repair_diagnosis / writer_integration / world_view | 只读 | 无 | api `/v3/*`、`/command-center`、UI `ui/src/v3/*` | `test_v3_ui_projection.py`、`test_v3_*`（6 个文件） | REWRITE | 1,682 行；`_journey_projection()` 是 stage/progress 的唯一入口（NF-005 已修），但模块本身承载过多职责 |
| `story_builder/novel_admin.py` | 作品管理 | 重命名（只改 `title`）；删除＝整体归档到 `workspace/archived_novels/` | HTTP → archive | profile/packs/outlines/writer | 移动目录 + `ARCHIVE_MANIFEST.json` | 文件移动 | api `PATCH/DELETE /novels/{id}` | `test_story_builder_*` | KEEP | 已具备「可恢复、不留孤儿」语义，V4 可直接复用 |
| `story_builder/cross_genre_e2e.py` | 跨题材 harness | 3 题材 13 步产品链 Runner（测试基础设施） | case → report | 各 application 模块 | 隔离数据根 | 写临时根 | `test_story_builder_*`、M17 | `test_m17_cross_genre_e2e.py`(historical) | KEEP | 是「同一实现只换数据」的现成回归资产 |

### 2.3 story_engine — 通用运行内核（KEEP 主体）

| Path | Module | Responsibility | Inputs → Outputs | State / Persistence | Side Effects | Used By | Tests | Class | Notes |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `story_engine/state.py` | StoryState | 唯一「已发生事实」容器（world / timeline / location / characters / relationships / knowledge / resources / abilities / factions / flags / identities / promises / events / plots / effect_log / delayed_effects） | dict ↔ StoryState | 由 storage 持久化 | 无 | 全后端 | `test_story_engine_state.py` | KEEP | Domain 根基，V4 不得改变语义 |
| `story_engine/storage.py` | 状态持久化 | 原子写 + 单进程锁；路径 `novel/authoring/story_engine/state/<id>/v%06d[_branch].json` | StoryState → 文件 | **写文件** | 写 JSON | creator / driver / api | `test_story_engine_storage.py` | KEEP | 单进程事务边界，V4 需在文档中保持该限制 |
| `story_engine/entities.py` | 通用实体 | Character / Faction / Location 基础模型 | — | 无 | 无 | 多模块 | 间接 | KEEP | 122 行 |
| `story_engine/actions.py` / `conditions.py` / `effects.py` / `resolver.py` | 行动-条件-效果 | 合法性判定、效果执行、事务与回滚 | Action ↔ State | 经 storage | 无 | driver / director / api | `test_story_engine_actions.py` | KEEP | 「客户端不能自证」的核心防线 |
| `story_engine/events.py` / `delayed.py` | 事件引擎 | 事件卡触发、冷却、延迟后果 | state + card | 经 storage | 无 | driver / world | `test_story_engine_events.py` | KEEP | |
| `story_engine/foreshadow.py` / `progression.py` | 伏笔 / 成长 | 生命周期、七类 progression | state | 经 storage | 无 | views / api | `test_story_engine_foreshadow.py` | KEEP | |
| `story_engine/driver.py` | 运行驱动 | 把引擎能力串成可循环推进的链（runtime candidates / advance） | state → 结果 | 经 storage | 无 | api `/runtime/*` | `test_story_engine_driver.py`（398 行） | KEEP | |
| `story_engine/candidates.py` | 候选行动 | 候选生成 + **过滤 LLM 提议**（只接受已过规则判定的 action_id） | state → candidates | 无 | 无 | driver / director | `test_story_engine_candidates.py` | KEEP | 现成的「LLM 只能提议」边界实现 |
| `story_engine/director.py` / `director_view.py` | 导演 | 候选池评分 / 节奏 / 权重 | state + weights → snapshot | 权重写 profile | 无 | api `/creator/director*` | `test_story_engine_director*.py` | KEEP | 规则式，属于业务规则而非创作内容 |
| `story_engine/characters.py` | 角色自主反应 | 规则反应 + `sanitize_llm_proposals`（LLM 不能创造知识/资源/关系） | state → reactions | 经 storage | 无 | api | `test_story_engine_characters.py` | KEEP | |
| `story_engine/world.py` / `world_view.py` | 世界运行 / 视图 | 时间、地点、势力、NPC 自主行动 + 只读快照 | state → snapshot | 经 storage | 无 | api、export、writer | `test_story_engine_world*.py` | KEEP | `world_snapshot` 是导出与 writer context 的共同输入 |
| `story_engine/character_view.py` / `plot_view.py` / `progression_view.py` / `memory_view.py` / `linkage_view.py` | 面板视图 | 6 个只读面板快照（角色 / 剧情 / 成长 / 记忆 / 联动） | context → snapshot | 只读 | 无 | api `/creator/*` | `test_story_engine_creator_*.py` | KEEP | 结构一致，可统一为 projection 协议 |
| `story_engine/memory.py` | 三视角知识 | 「谁知道什么」的长期记忆（知识 / 伏笔 / 义务） | state → index | 经 storage | 无 | memory_view / writer context | `test_story_engine_memory.py` | KEEP | ⚠️ **命名冲突**：与 V4 `memory/`（LLM 长期记忆）不是同一概念，V4 必须改名或明确分层 |
| `story_engine/linkage.py` / `narrative.py` / `route_lab.py` | 大纲联动 / 路线 | FuturePlan、StageGoal、路线 fork/compare/merge/freeze | state → route facts | 写分支事实文件 | 写 JSON | api route 路由 | `test_story_engine_*` | KEEP | 路线分支事实独立存储，语义正确 |
| `story_engine/profile.py` | 小说档案 | NovelProfile CRUD；`DEFAULT_NOVEL_ID = "novel_project"` | novel_id → profile | 写 `.../profiles/<novel_id>.json` | 写 JSON | 全后端 | `test_story_engine_profile.py` | KEEP | 唯一「作品身份」来源，V4 的 `project_id` 应从这里长出来 |
| `story_engine/templates.py` / `content.py` / `wizard.py` | 题材 / 内容包 | 模板载入、内容包 schema 与校验、新建小说向导 | yaml/json → pack | 读 config；向导写包 | 写 JSON | creative / settings | `test_story_engine_templates.py` | KEEP | 引擎无题材分支（有源码守卫） |
| `story_engine/settings_check.py` | 起点自检 | 用真实引擎跑一遍内容包，回答「能不能开局」；允许数据层修补 | pack → report | 修补写内容包 | 写 JSON（repair=yes） | api `/settings/check`、V3 投影 | `test_story_builder_settings_check.py` | KEEP | 已是「deterministic 质量门」的雏形 → V4 Quality Q0/Q1 的种子 |
| `story_engine/spec/*`（6 文件） | NOVEL_SPEC | 一句话创意 → 规格 → 缺口 → 提案 → 作者确认 → Planning IR | spec → proposal | 提案不落 truth | **`spec/llm.py` 直接 HTTP 调 DeepSeek** | `test_novel_spec_compiler.py` | REWRITE | ⚠️ 产品路径未接线，但**已存在真实 LLM client**（端点 / 模型 / backoff 硬编码）→ V4 Gateway 的迁移起点 |

### 2.4 story_engine — 规则式创作内容（V4 将被 LLM 取代）

| Path | Module | Responsibility | 证据（硬编码创作内容） | Class | Notes |
| --- | --- | --- | --- | --- | --- |
| `story_engine/creative.py` | 创意入口 / 题材识别 | `GENRE_KEYWORDS`（题材→关键词表）、`TONE_RULES`（6 条基调规则）、`SELLING_POINT_TEMPLATES`（7 条固定卖点文案）、`REASON_BY_GENRE` 固定理由；`CreativeIdeaProvider.enrich()` 用 provider 补文案 | REPLACE_BY_LLM | **真实业务规则须保留**：候选必须指向真实模板 / 内容包（`_catalog()` 校验、越界 id 丢弃） |
| `story_engine/settings_gen.py` | 设定候选生成 | `RULE_TEMPLATES`（5 条世界规则）、`PROTAGONIST_ROLES`（5）、`SUPPORT_ROLES`（4）、`FACTION_SHAPES`（3）、`CONFLICT_MARKERS`；`content_pack_draft()` 生成固定骨架：地点 `起点场所/工作场所/隐藏节点`、行动 `act_investigate/act_ask/act_wait/act_open_hidden/act_call_favor/act_use_permit/act_go_work/act_go_hidden`、事件 `ev_first_pressure/ev_world_shift` | REPLACE_BY_LLM | 693 行；骨架 id / schema 校验属于业务规则须保留 |
| `story_engine/outline_forge.py` | 四级大纲锻造 | `NARRATIVE_BEATS = ("试探","布局","交涉","受阻","代价","转机","决断","收束")`；`ChapterTitleLedger.allocate()` 兜底 `f"{base}（第 N 次）"`；标题格式 `f"第{number}章：{body}"`；`StageGoal(id="stage_default", title="推进主线")`；`FIELD_LABEL_BLACKLIST` 收 `阶段目标/长期方向/主线` | REPLACE_BY_LLM | **NF-003 根因**；1,139 行；`FIELD_LABEL_BLACKLIST` 本身就是「标题该由内容决定」的证据 |
| `story_engine/journey.py` | Journey 场景渲染 | `suggestions_for()` 按 `hero_cautious/hero_bargainer/hero_impulsive` 三原型硬编码行动；`scene()` 用 `rev1/rev2` 分支拼接固定场景文本；`_success()` fallback 文案 | REPLACE_BY_LLM | 401 行；`journey_revision` flag 是状态，须保留 |
| `story_engine/writer.py` | Writer 边界 | `WriterPackage` / `validate_writer_output`（事实校验，KEEP）+ `fallback_text()`/`render_scene()`（确定性文本，REPLACE_BY_LLM） | REWRITE | 285 行；**校验层是 V4 的既有资产**，表现层应由 LLM 承担 |

### 2.5 story_engine — 稳定性基础设施（Canon / Chapter IR / Planning）

| Path | Module | Responsibility | Deps | Persistence | Tests | Class | Notes |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `story_engine/canon/*`（16 文件，~3.5k 行） | Canon 基础设施 | 稳定事实身份、依赖图、SQLite 唯一写入口、source reference 校验、mutation test、prose 完整性防线 | networkx / sqlite | **写 `novel/authoring/story_engine/canon/<novel>.sqlite`** | `test_canon_*`（14 文件） | KEEP | 路径需按 `novel_id` 参数化（`canon_routes` / `export_package` / `writer_integration` / `inspector` 均硬编码 `wasteland_001`） |
| `story_engine/chapter_ir/*`（13 文件，~2.5k 行） | 章节语义 IR | IR 模型 + 严格 schema gate + evidence validator + typed state + compiler + 可选 semantic judge/verifier（无 LLM 时 Null 实现） | pydantic | 由 planner 存储 | `test_chapter_ir_*`（11 文件） | KEEP | **V4 结构化生成的最佳现成契约**：`ChapterSemanticIR` 已经是「机器可读章节事实」 |
| `story_engine/planning/*`（40 文件，~14k 行） | Story Planning IR V1–M9 | IR 模型 / 严格 validator / repository+revision / context builder / graph / spine / route lab V2 / outline compiler / chapter batch（session/checkpoint/resume） | networkx | 写 `novel/authoring/story_engine/planning/<novel_id>/` | `test_story_planning_*`（14 文件） | KEEP → REWRITE(局部) | 大部分是确定性 assembly 与校验（KEEP）；`chapter_compiler.py`（1,254 行）确定性渲染章节字段 → V4 应由 LLM 结构化产出取代 |
| `story_engine/memory.py`+`_view` | 见 §2.3 | — | — | — | — | KEEP | 与 V4 memory 概念区分 |

### 2.6 历史 / 冻结路径（不可删，只能隔离）

| Path | 成员 | Responsibility | Class | Notes |
| --- | --- | --- | --- | --- |
| `story_engine/historical_ir.py`（1,709 行）、`reconstruction.py`（1,845 行）、`historical_adoption.py`（1,409 行） | 3 | 570 章 Historical Chapter IR foundation、M10 top-down reconstruction、P15g adoption（`llm_used: False`，deterministic-only） | COMPATIBILITY_ONLY | `HISTORY_DIR = "workspace/wasteland_001_exports/historical_chapter_ir_v1"`（gitignored 运行时证据） |
| `story_engine/repair.py`（1,695 行） | 1 | M11 Content Repair、REPAIR_BATCH_01…、frozen contract / gate 读取 | COMPATIBILITY_ONLY | 被 `m11_p15p.FROZEN_*_DIGESTS` 与 `export_package` 引用 |
| `story_engine/m11_*.py` | 18 文件（`run01` 1,560 行 → `run12` 64 行，其余 52–1,444 行） | M11 production runs / blocker / content design / micro pilot / closeout | COMPATIBILITY_ONLY | **`m11_run02..12` 平均 ~56 行**：典型「run executor 复制」模式（AGENTS.md §8 的实例） |
| `story_engine/m12_*` … `m18_*` | 7 文件（1,240 / 359 / 305 / 358 / 349 / 371 / 619 行） | M12–M18 milestone acceptance + readiness | COMPATIBILITY_ONLY | 依赖本机历史数据，默认不运行（`-m historical_acceptance`） |
| `story_engine/phase_snapshot.py` / `milestone_acceptance.py` | 2 | write-once phase snapshot + digest manifest；milestone 公共件 | COMPATIBILITY_ONLY（机制 KEEP） | 机制本身可用于 V4 acceptance，但当前语义绑定 V2 里程碑 |

---

## 3. 副作用与外部依赖总表

| 类别 | 位置 | 事实 |
| --- | --- | --- |
| 网络调用 | `story_engine/spec/llm.py`（`DEFAULT_ENDPOINT = "https://api.deepseek.com/chat/completions"`） | **唯一**真实外部网络调用点；产品路由未接线 |
| 网络调用（注入式） | `story_engine/creative.py` / `settings_gen.py` / `ai_recommendations.py` | `provider.generate_structured(...)` 鸭子类型；产品路径 provider=None → `AI_UNAVAILABLE` |
| 依赖包 | `requirements.txt` | fastapi / uvicorn / pydantic / httpx / PyYAML / networkx — **无任何 LLM SDK** |
| 环境变量 | `.env.example` | `DEEPSEEK_API_KEY` / `ARK_API_KEY`（当前版本不生效）；`spec/llm.py:load_env()` 会读 `.env.local` |
| 文件写入 | `profile` / `content pack` / `StoryState` / `outline` / `session` / `blueprint` / `writer draft` / `planning` / `canon.sqlite` | 全部为本地文件系统；原子替换 + 单进程锁 |
| 文件移动 | `story_builder/novel_admin.py` → `workspace/archived_novels/` | 删除作品＝归档 |
| 静态服务 | `api/app.py` → `ui/dist` | 无 CDN、无外部资源 |
| 前端持久化 | `localStorage`（moodboard：`novelforge.moodboard.<novel_id>`） | 唯一 UI 侧持久化（设计态参考位） |

---

## 4. 持久化所有权（Canonical Ownership）

### 4.1 设计态

| 对象 | 路径 | 写入者 | 读取者 |
| --- | --- | --- | --- |
| NovelProfile | `novel/authoring/story_engine/profiles/<novel_id>.json` | `NovelProfileRepository` | 全后端 |
| ContentPack | `novel/config/story_engine/<pack_id>.json` | `settings_gen.write_content_pack` | `creator._load_pack` |
| Session | `novel/authoring/story_builder/sessions/*.json` | `StorySessionRepository` | api / creator |
| Blueprint | `novel/authoring/story_builder/blueprints/<id>/v*.json` | `StoryBlueprintRepository` | creator / outline |
| Outline（四级） | `novel/authoring/story_builder/outlines/<level>/<package_id>/v*.json` | `StoryOutlineRepository` | api / export / writer |
| Planning IR | `novel/authoring/story_engine/planning/<novel_id>/` | `PlanningRepository` | export / M13 投影 |

### 4.2 运行态（occurred）

| 对象 | 路径 | 写入者 | 读取者 |
| --- | --- | --- | --- |
| StoryState | `novel/authoring/story_engine/state/<runtime_id>/v%06d[_branch].json` | `StoryStateRepository`（经 ActionResolver） | 全后端 |
| Canon | `novel/authoring/story_engine/canon/wasteland_001.sqlite` | `CanonRepository`（唯一允许写 SQL 处） | inspector / export / writer / canon_routes |

### 4.3 preview / derived

| 对象 | 路径 | 写入者 | 读取者 |
| --- | --- | --- | --- |
| WriterDraft（canonical） | `novel/authoring/story_engine/writer/<novel_id>/index.json` + `drafts/*.json` | `WriterDraftService` | `read_writer_drafts` / v3_projection / export |
| WriterDraft（legacy 只读） | `workspace/wasteland_001_exports/writer_v1/<novel>/drafts/` | 无（历史） | 仅当 canonical 为空时读取 |
| FactProposal | 同目录 `proposals/` | `sync_facts` | UI / 修复流程 |
| 归档作品 | `workspace/archived_novels/<novel_id>_<UTC>/` | `novel_admin` | 人工恢复 |

### 4.4 frozen 证据（只读）

| 对象 | 路径 |
| --- | --- |
| 570 章 Historical IR | `workspace/wasteland_001_exports/historical_chapter_ir_v1/` |
| source Chapter IR | `workspace/wasteland_001_exports/chapter_ir_v1/` |
| M11 overlay / reconciliation / contract / gate | `workspace/wasteland_001_exports/repair_adoption_v1/M11_*.json` |
| Reconstruction spine | `workspace/wasteland_001_exports/reconstruction_v2/{FULL_BOOK_FUTURE_SPINE.json, HISTORICAL_CAUSAL_SPINE.json}` |
| Phase snapshots | `workspace/wasteland_001_exports/phase_snapshots/<phase_id>/` |
| 冻结 manifest | `docs/FROZEN_EVIDENCE_MANIFEST.json`（守卫 `tests/test_v2_frozen_guard.py`） |

### 4.5 仍然无人拥有的对象（V4 必须解决）

| 对象 | 路径 | 事实 |
| --- | --- | --- |
| **既有正文** | `novel/final/chapter_XXXX_final.md`（69 个 tracked 文件）、`novel/final/硅基升维_重构版_前40章.md` | 已在版本控制中。产品链路**不写**它；唯一读取点是冻结历史模块 `story_engine/historical_ir.py`（`source_inventory()` L527、`prose_availability()` L927），且用文本启发式 `_has_wasteland_entities()`（L1822）**否定**它属于 WASTELAND_001（L580 明确写「novel/final/*.md 属另一部手稿」）。结论：它既不是 canonical writer store，也不是任何作品的导出源，**归属完全缺失** |
| 历史内容产物 | `novel/runs/`（1,108 文件）、`novel/workspace/`（254）、`novel/state/`（278）、`novel/pipelines/`（12）、`novel/learning/`（6）、`novel/status/`（1） | 版本控制内存在，产品代码不读取（除 `novel/state` 未验证）→ `UNKNOWN`，见 §6 |
| 空目录 | `novel/{bible,gates,human,outline,relations,revision_plans,source_text,state_updates,timeline}/` | 0 文件；`UNKNOWN`：是刻意占位还是历史残留（缺少创建者证据） |

---

## 5. 前端 Inventory

### 5.1 V3 工作台（`ui/src/v3/`）

| Path | 行数 | Responsibility | Deps | Class | Notes |
| --- | --- | --- | --- | --- | --- |
| `V3App.tsx` | 680 | URL 路由唯一解析入口 + 各 view 组装 + 写操作调用 | navModel / api / viewmodel / components | KEEP | 已明确「页面 Shell 与 tab 状态必须照常渲染」的降级策略 |
| `navModel.ts` | 109 | 路由 parse/serialize | — | KEEP | 单一解析入口 |
| `viewmodel.ts` | 873 | DTO → ViewModel：文案 / 状态语义 / 排序 | api.ts (types) | KEEP | 检查结论：**未发现业务规则**（只有 label 映射、排序、`filter` 展示过滤） |
| `api.ts` | 426 | V3 DTO 类型 + 只读端点 + 复用既有写端点 | `../api` | KEEP | 注释明确「只做 HTTP 与 DTO，不做业务判断」 |
| `AppShell.tsx` / `CommandCenter.tsx` / `NovelLanding.tsx` | 146 / 182 / 207 | 框架 / 首页 / 存档选择 | viewmodel | KEEP | |
| `WorkspaceView.tsx` | 774 | 11 个工作区视图（实体 / 推演 / 大纲 / 检查 / 导出就绪度） | viewmodel | KEEP → REWRITE | 唯一计算为展示过滤（`model.objectives.filter`、`comparisonRows.filter`） |
| `CreationFlow.tsx` | 580 | 创意 → 候选 → 设定 → 自检 → 开始推演 | api / selection | REWRITE | 与 `SettingSeedPanel` 存在**并行实现**（同一流程两套 UI） |
| `ExportFlow.tsx` | 246 | 导出包生成 / 下载 / writer 草稿列表 | api | REWRITE | 直接展示 `export_id`（NR-004） |
| `design-system/*`（components 567 / primitives 208 / icons 98 / tokens.css 89 / choices 78 / artworkManifest 117） | ~1,150 | 设计系统 + 视觉资源解析（real asset → default artwork → icon） | — | KEEP | 由 `test_v3_visual_asset_contract.py` + `docs/V3_VISUAL_ASSET_REQUIREMENTS.json` 守卫 |
| `v3.css` / `export-flow.css` | 869 / 56 | 样式 | tokens | KEEP | |

### 5.2 既有面板（高级工具 bridge，`ui/src/`）

| Path | 行数 | Responsibility | Class | Notes |
| --- | --- | --- | --- | --- |
| `StoryBuilderPage.tsx` | 661 | 19 页签桥接：`TAB_GROUPS`（design 4 / occurred 8 / output 5 / governance 2） | COMPATIBILITY_ONLY | `guidedFlow.TAB_GROUPS` 是页面签的唯一词表 |
| `api.ts` | 1,127 | 全量端点客户端 + 全量 DTO 类型（**与 `v3/api.ts` 重复定义 DTO**） | DELETE / MIGRATE | 双份 DTO 是明确的重复 truth source |
| `GuidedFlowPanel.tsx` / `CreativeBriefPanel.tsx` / `SettingSeedPanel.tsx` / `DesignTreePanel.tsx` | 166 / 191 / 261 / 60 | 引导流与创作链旧面板 | COMPATIBILITY_ONLY | 与 `CreationFlow.tsx` 流程重叠 |
| `WorldPanel` / `CharacterPanel` / `PlotPanel` / `ProgressionPanel` / `MemoryPanel` / `DirectorPanel` / `LinkagePanel` / `OutlineForgePanel` / `OutlineItemEditor` / `RouteLabPanel` / `AdventurePanel` / `InspectorPanels` / `VisualOverviewPanels` / `VisualOutputPanels` | 135 / 149 / 142 / 83 / 137 / 127 / 161 / 462 / 34 / 278 / 73 / 180 / 116 / 192 | 实体编辑 / 路线 / 大纲 / Canon 检查 / 修复中心（完整编辑能力所在） | COMPATIBILITY_ONLY | `LEGACY_COMPAT.md` 已把它定义为 bridge，不是第二套业务规则 |
| `components/{CandidateCard,TruthLayerBadge,ProvenanceList,PanelBoundary}`、`hooks/useApiData.tsx`、`guidedFlow.ts`、`storyBuilderSelection.ts`、`style.css`、`main.tsx`、`App.tsx` | 106 / 18 / 20 / 42 / 36 / 135 / 30 / 341 / 9 / 55 | 共享组件 / 深链接 / 选择语义 | KEEP | `storyBuilderSelection.ts` 的 `MULTIPLE_SELECTION_GROUPS` 是展示层规则（可接受） |

---

## 6. UNKNOWN 清单（证据不足，不猜）

| 项 | 需要什么证据才能确定 |
| --- | --- |
| `novel/runs/`（1,108 文件）、`novel/workspace/`（254）、`novel/state/`（278）、`novel/timeline`、`novel/bible`、`novel/gates`、`novel/human`、`novel/outline`、`novel/relations`、`novel/revision_plans`、`novel/source_text`、`novel/state_updates` 与产品代码的关系 | 需要：`git log --follow` 找到创建者提交 + 全仓 `rg` 确认无读取者 + 与作者确认是否为外部写作流程（DEEPWRITE 系列文档在 `workspace/` 中提到过生产系统）。当前证据：**产品代码不读取**，但不等于「无用途」 |
| `novel/final/*.md` 是否应成为 V4 canonical writer store 的初始内容 | 需要作者决定：这 69 章是否要作为「已出版正文」进入 V4 Canon / revision 历史，还是仅作只读参考。**当前证据**：只有 `historical_ir._has_wasteland_entities()` 这个关键词启发式在防止跨作品误用 |
| M11/M12 的 `REPAIR_REPLAY` / `M11_FINAL_CLOSURE_RECONCILIATION.json` 是否为 V4 所需 | 需要 `docs/FROZEN_EVIDENCE_MANIFEST.json` 的 digest 与 `tests/test_v2_frozen_guard.py` 断言范围逐条核对 |
| `ui/src/*` 19 个高级工具页签中哪些在 V3 浏览器验收中被真实覆盖 | 需要：逐页签对照 `tests/browser_*.cjs` 的断言（本轮只确认 `browser_advanced_tools.cjs` 存在，未逐页签核对） |

> 已消除的 UNKNOWN：`story_builder/recommendations.py` + `ai_recommendations.py` 仍在使用中 ——
> 调用点 `ui/src/api.ts:1158`（`POST /api/story-builder/sessions/{session_id}/recommendations`），
> 即 legacy 高级工具面板仍在消费规则式推荐。

---

## 7. 测试与验收资产 Inventory

| Path | 内容 | Class | Notes |
| --- | --- | --- | --- |
| `tests/conftest.py` | `HISTORICAL_ACCEPTANCE_FILES`（53 个文件）+ 自动 marker | KEEP | 历史隔离机制 |
| `pytest.ini` | `-m "not historical_acceptance"`、无 cache provider | KEEP | |
| `tests/test_v2_frozen_guard.py` / `test_v3_frozen_guard.py` | 冻结证据 digest 守卫 / route_lab 只读放宽 | KEEP | **V4 不得削弱** |
| `tests/test_v3_*`（7 文件） | V3 投影 / 实体 / 章节 / 模拟 / 检查导出 / 视觉契约 | KEEP | V4 迁移时的主要回归网 |
| `tests/test_story_engine_*`（30+ 文件） | 引擎内核 | KEEP | |
| `tests/test_story_planning_*`（14 文件） | Planning IR / graph / spine / route / outline batch | KEEP | |
| `tests/browser_v3_p0..p7_acceptance.cjs` | 真实浏览器门禁 | KEEP | NF-020：部分门禁走内部 API、依赖未随仓库提供的数据根 |
| `tests/browser_advanced_tools.cjs` | 高级工具可达性 | KEEP | |
| `scripts/validate_project.py` | 路由边界 + catalog 加载校验 | KEEP | 16 行，断言只有 `/api/story-builder/*` 与 `/api/health` |

---

## 8. 关键调用关系（V4 需要继承的事实）

```text
UI (ui/src/v3 + ui/src)
   │  HTTP
   ▼
api/story_builder_routes.py  ← 唯一业务入口（1,545 行，含内联编排）
   │  直接函数调用（无 service 层）
   ▼
story_builder/*（application：projection / export / writer / inspector / admin）
   │
   ▼
story_engine/*（domain：state / actions / conditions / effects / storage）
   │
   ▼
文件系统 + Canon SQLite
```

已知偏差：

1. `story_builder/*` 既做投影又直接拼路径读文件（`v3_projection` / `export_package` / `writer_integration`
   都直接 `Path(...)/常量`），没有显式 repository port。
2. 导出与写作草稿的**单作品路径硬编码**（`wasteland_001`）破坏了「所有 artifact 都有 novel_id 所有权」的
   V4 前提，也是 NR-002 的直接根因。
3. 正文（`novel/final/`）在产品链路中**完全缺席**：V3 没有「写作 → 正文 → 交付」这一段的所有权。

---

## 9. 本清单的完成判据

| 检查项 | 结果 |
| --- | --- |
| 是否扫描完整 repository（含 scripts / tests / config / 非 src 目录） | 是（§0.2、§1、§7、§8） |
| 是否找到所有主要 generation 路径 | 是（creative / settings_gen / outline_forge / journey / writer / planning.chapter_compiler / spec） |
| 是否找到所有 Writer store | 是（canonical + legacy 只读；正文目录无 owner，见 §4.5） |
| 是否找到所有 Export 路径 | 是（`export_package`、`outlines` 导出、`outline_revision.docx_bytes`、writer bundle） |
| 是否找到所有 progress / journey 逻辑 | 是（`v3_projection._journey_projection` 唯一；`ui_flow` 第二套 stage 词表） |
| 是否检查 legacy 数据自动加载 | 是（§4.4、§4.5、`tests/test_v2_frozen_guard.py`） |
| 是否检查 UI business logic | 是（§5；结论：viewmodel 仅展示层，无业务规则；重复 DTO / 重复流程存在） |
