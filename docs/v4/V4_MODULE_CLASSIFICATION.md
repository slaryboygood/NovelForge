# NovelForge V4 — V3 Module Classification

> 阶段：**V4-00 Architecture**（只分类，不改代码）
> 对齐：**V4-01 作者决策**（2026-09-17）——`novel/final` 与 570 章 historical 判定为废弃并删除；
> canonical creative artifact 改为 **StoryBlueprint**（见 `adr/ADR-011`，ADR-003 已被取代）。
> 输入：`docs/v4/V4_CODEBASE_INVENTORY.md`
> 原则：**数量不是目标，准确分类才是目标。** 每条分类都必须能追到文件、符号或调用点。

### 0.1 V4-01 决策导致的分类变更

| 对象 | V4-00 分类 | V4-01 分类 | 原因 |
| --- | --- | --- | --- |
| `novel/final/**`（69 tracked 正文） | `MIGRATE`（待裁定归属） | **`DELETE`（已执行）** | 作者决策 A |
| `workspace/wasteland_001_exports/**`（570 章 historical / M11 证据 / 旧导出） | `COMPATIBILITY_ONLY` | **`DELETE`（已执行）** | 作者决策 B |
| `story_builder/writer_integration.py` | `REWRITE` → writer service | `REWRITE` → **Blueprint context + 兼容预览** | 作者决策 C |
| `story_engine/writer.py` | `REWRITE`（Writer 边界） | `COMPATIBILITY_ONLY`（预览/降级文本） | 作者决策 C：正文非 V4 Core |
| `ui/src/v3/ExportFlow.tsx` | `REWRITE` → delivery | `REWRITE` → **Blueprint 交付** | 作者决策 C |

---

## 1. 分类定义

| 分类 | 含义 | 判断依据（本项目） |
| --- | --- | --- |
| `KEEP` | V4 架构下仍然成立，可继续使用 | 不依赖具体作品 id、不是创作内容、不承担第二套 ownership |
| `REWRITE` | 概念保留，实现方式不符合 V4 | 职责可保留，但需要换边界（service / port / contract） |
| `REPLACE_BY_LLM` | 当前是硬编码创作逻辑（模板、规则式创作、同义词、固定 fallback） | 证据 = 源码里存在固定文案表 / beat 表 / 原型表 / `第 N 次` 兜底 |
| `DELETE` | V4 中不应继续存在的结构 | 重复实现、重复 truth source、无 owner 的历史加载 |
| `MIGRATE` | 数据或能力需要迁移到新的 canonical model | 所有权缺位（单作品路径硬编码、缺 `novel_id` / `revision`） |
| `COMPATIBILITY_ONLY` | 仅允许 migration / read-only / 旧 import | 冻结历史路径、旧存档格式、legacy bridge |
| `UNKNOWN` | 证据不足 | 已列出所需证据（见 `V4_CODEBASE_INVENTORY.md` §6） |

> ⚠️ 边界提醒（`V4_ARCHITECTURE.md` §2 也会重复）：
> **业务规则 ≠ 创作内容**。`REPLACE_BY_LLM` 只针对创作内容，
> 业务约束（校验、权限、schema gate、所有权、守恒检查、approval boundary）继续保留。

---

## 2. Migration Phase 词表

| 代号 | 对应 V4 阶段 | 含义 |
| --- | --- | --- |
| `P0` | V4-01 Core Cleanup | 边界与重复实现清理，不改变外部行为 |
| `P1` | V4-02 LLM Gateway | 建立模型调用边界，迁移现有 provider 调用 |
| `P2` | V4-03 Memory | 记忆层与 Context Builder |
| `P3` | V4-04 Structured Generation | 结构化生成契约落地 |
| `P4` | V4-05 Quality Loop | 质量契约 / 评估 / 定向修复 |
| `P5` | V4-06 Writer | 正文与 revision |
| `P6` | V4-07 Delivery | ExportService / DeliveryValidator / nfpack |
| `P7` | V4-08 MCP | 对外协议层 |
| `P8` | V4-09 Plugins | 扩展点 |
| `P9` | V4-10 UI | 按稳定后端重构 UI |
| `P10` | V4-11/12 Agent + Acceptance | Agent 模式与最终验收 |
| `FROZEN` | 永不 | frozen truth / contract / gate / 历史证据 |
| `LATE` | 最后 | 只有在替代物上线且验收通过后才允许移除 |

---

## 3. 后端分类总表

| Path | Symbol / Module | Current Role | Classification | Target | Reason | Dependencies | Migration Phase |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `src/novelforge/models.py` | `StrictModel` | 全后端严格模型基类 | KEEP | `core/schema.py` | 3 行、无业务、被所有 DTO 依赖 | pydantic | P0 |
| `src/novelforge/author_language.py` | `label_table` / `translate` | 内部 id → 作者语言唯一映射 | KEEP | `services/labels.py` | 已消除「同一 id 半翻译」问题，是 i18n 种子 | content/profile | P0 |
| `src/novelforge/api/app.py` | FastAPI app | 路由挂载 + 静态资源 | KEEP | 不变（挂载点随路由分层调整） | 22 行，边界清晰 | routes | P0 |
| `src/novelforge/api/story_builder_routes.py` | 全部业务路由（1,545 行） | HTTP + 内联编排 + 部分业务判断 | REWRITE | `api/routes/*` + `services/*` | UI/REST/MCP 要共用 service，路由必须变薄 | 12+ 领域模块 | P0 |
| `src/novelforge/api/canon_routes.py` | Canon 只读 API | facts/events/entities/graph/validate + rebuild | MIGRATE | `api/routes/canon.py` + `CanonService` | `DEFAULT_NOVEL_ID` 与单库路径需按 `novel_id` 参数化 | `story_engine.canon.*` | P0 |
| `story_builder/models.py` | Outline / StoryStep / Blueprint | 四级大纲与十步 DTO | KEEP | `domain/outline.py` | 结构完整，已有 `next_steps` 前向性校验 | pydantic | P0 |
| `story_builder/catalog.py` | `load_story_catalog` | 十步目录载入（YAML） | KEEP | `domain/catalog.py` | 配置不是事实，语义正确 | yaml | P0 |
| `story_builder/sessions.py` | `StorySessionRepository` | 十步会话 + 选择 + 回退 + 历史 | KEEP | `services/design_session.py` | 会话概念在 V4 仍成立（设计态） | catalog/models | P0 |
| `story_builder/blueprints.py` | `StoryBlueprintRepository` | 蓝图版本 + 确认状态 | KEEP | `services/blueprint.py` | **已有 revision 先例**，V4 revision 模型可直接继承 | sessions/models | P0 |
| `story_builder/design_tree.py` | `design_view` / `save_design` | 设计树节点读写 | KEEP | `services/design_session.py` | 65 行 | catalog/sessions | P0 |
| `story_builder/outlines.py` | `StoryOutlineRepository` | 四级大纲存储 + 版本 + 导出 | REWRITE | `persistence/outline_repo.py` + `ExportService` | 导出与 `export_package` 并存 = 两套拼装 | models/storage | P6 |
| `story_builder/adventures.py` | `AdventureEngine` | 旧旅程存档读写（rules 1/2） | COMPATIBILITY_ONLY | `persistence/legacy_adventure.py` | 新旅程已是 `rules_version=3` | journey/storage | FROZEN |
| `story_builder/recommendations.py` | 十步规则推荐 | 模板化候选与理由 | REPLACE_BY_LLM | `generation/design_options.py` | 候选文案为固定模板；调用点 `ui/src/api.ts:1158` | catalog/models | P3 |
| `story_builder/ai_recommendations.py` | `AIRecommendationSupplementer` | provider 补充 + 合并规则候选 | REWRITE | `ai/gateway` 消费者 | 已实现「AI 只能补充，不能新增结构」——把它移到 Gateway 之上 | provider 鸭子类型 | P1 |
| `story_builder/ui_flow.py` | 引导流投影 | 第二套 stage / next step 计算 | MIGRATE | `services/journey.py`（单一投影） | 与 `v3_projection.V3_STAGES` 形成两套 stage 词表 | creator/world_view | P0 |
| `story_builder/inspector.py` | Inspector / 修复诊断 | 跨层只读检索 + provenance | MIGRATE | `services/inspector.py` | `CANON_DB` 硬编码单作品 | canon/historical_ir/repair | P0 |
| `story_builder/export_package.py` | Export projection + serializer | 导出唯一 projection | REWRITE | `application/services/export.py`（V4-01 起）+ `DeliveryValidator` | 曾含 `RECON_DIR` / `PLANNING_INDEX` / `canon/wasteland_001.sqlite` 硬编码与历史分区（NR-002）；**V4-01 已参数化并移除历史分区** | canon/outline/world | P6 |
| `story_builder/writer_integration.py` | WriterContextBuilder + WriterDraftService | 6 层 writer context + 草稿 + fact proposal | REWRITE | `application/services/blueprint.py`（context 装配）+ `persistence/writer_store.py`（兼容预览） | **正文草稿不是 V4 canonical artifact**（ADR-011）；其分层 context / 去重 / 预算设计保留给 Blueprint 上下文 | creator/storage/memory_view | P5 |
| `story_builder/v3_projection.py` | V3 只读投影（1,682 行） | Journey/Objective/NextAction/实体/推演/大纲/检查/导出就绪 | REWRITE | `services/journey.py` + 各 `*_projection.py` | `_journey_projection` 已是唯一 stage/progress 入口（需保留该性质）；其余职责必须拆开 | 8+ 模块 | P0 |
| `story_builder/novel_admin.py` | `rename_novel` / `delete_novel` | 重命名 / 归档式删除 | KEEP | `services/project_admin.py` | 已有可恢复语义 + `ARCHIVE_MANIFEST.json` | profile/packs/outlines | P0 |
| `story_builder/cross_genre_e2e.py` | `CrossGenreE2ERunner` | 13 步跨题材 harness | KEEP | `tests/support/` | 「同一实现只换数据」的现成回归资产 | 各 application | P0 |
| `story_engine/state.py` | `StoryState` | 唯一已发生事实容器 | KEEP | `domain/story_state.py` | Domain 根基，frozen 语义 | pydantic | FROZEN |
| `story_engine/storage.py` | `StoryStateRepository` | 原子写 + 单进程锁 + 版本升级 | KEEP | `persistence/story_state.py` | 单进程事务边界要显式保留为已知限制 | 文件系统 | P0 |
| `story_engine/entities.py` | Character/Faction/Location | 通用实体 | KEEP | `domain/entities.py` | 122 行 | pydantic | P0 |
| `story_engine/actions.py` | Action 模型 | 通用行动模型 | KEEP | `domain/actions.py` | 业务规则 | — | FROZEN |
| `story_engine/conditions.py` | `evaluate` | 条件判定 | KEEP | `domain/conditions.py` | 业务规则 | state | FROZEN |
| `story_engine/effects.py` | 效果执行器 | op 执行 + 失败语义 | KEEP | `domain/effects.py` | 业务规则 | state | FROZEN |
| `story_engine/resolver.py` | `ActionResolver` | 事务化应用 + 回滚 | KEEP | `domain/resolver.py` | 「客户端不能自证」防线 | actions/effects | FROZEN |
| `story_engine/events.py` | EventCard 引擎 | 触发 / 冷却 | KEEP | `domain/events.py` | 业务规则 | state | FROZEN |
| `story_engine/delayed.py` | 延迟后果 | delayed_effects | KEEP | `domain/delayed.py` | 业务规则 | state | FROZEN |
| `story_engine/foreshadow.py` | 伏笔生命周期 | 登记 / 回收条件 | KEEP | `domain/foreshadow.py` | 业务规则 | state | FROZEN |
| `story_engine/progression.py` | 七类成长 | 成长树 | KEEP | `domain/progression.py` | 业务规则 | state | FROZEN |
| `story_engine/driver.py` | Runtime Driver | 推进链 / candidates / revision | KEEP | `services/simulation.py` | V3 已验证 60 周期可执行 | 多方 | P0 |
| `story_engine/candidates.py` | `filter_llm_action_proposals` | 候选生成 + LLM 提议过滤 | KEEP | `domain/candidates.py` | **现成的「LLM 只能提议」实现** | state/actions | P1 |
| `story_engine/director.py` | 导演评分 | 候选池评分 / 节奏 | KEEP | `domain/director.py` | 规则式业务判断（不是创作内容） | state | P0 |
| `story_engine/director_view.py` | 导演快照 | 只读投影 | KEEP | `projections/director.py` | 一致结构 | director | P9 |
| `story_engine/characters.py` | 角色反应 + `sanitize_llm_proposals` | 规则反应 + 提议净化 | KEEP | `domain/characters.py` | 同上 | state | P1 |
| `story_engine/world.py` | 世界运行层 | 时间 / 地点 / 势力 / NPC 行动 | KEEP | `domain/world.py` | 业务规则 | state | FROZEN |
| `story_engine/world_view.py` | `world_snapshot` | 世界只读快照 | KEEP | `projections/world.py` | 被导出与 writer context 共用 | world | P0 |
| `story_engine/character_view.py` | 角色快照 | 只读 | KEEP | `projections/character.py` | | | P9 |
| `story_engine/plot_view.py` | 剧情快照 | 只读 | KEEP | `projections/plot.py` | | | P9 |
| `story_engine/progression_view.py` | 成长快照 | 只读 | KEEP | `projections/progression.py` | | | P9 |
| `story_engine/memory.py` | 三视角知识 | 「谁知道什么」 | KEEP | `domain/knowledge.py`（**必须改名**） | 与 V4 `memory/`（LLM 长期记忆）概念冲突 | state | P2 |
| `story_engine/memory_view.py` | 记忆快照 | 只读 | KEEP | `projections/knowledge.py` | 同上 | memory | P2 |
| `story_engine/linkage.py` | FuturePlan / StageGoal | 大纲联动 | KEEP | `domain/linkage.py` | 规划不是事实，语义正确 | state | P0 |
| `story_engine/linkage_view.py` | 联动快照 | 只读 | KEEP | `projections/linkage.py` | | | P9 |
| `story_engine/narrative.py` | 路线 → 大纲 | RoutePackage / verify_outline_sources | KEEP | `domain/narrative.py` | 来源一致性校验是 V4 需要的 | route_lab | P0 |
| `story_engine/route_lab.py` | 路线实验室 | fork / compare / merge / freeze | KEEP | `services/route_lab.py` | 分支事实独立存储，语义正确 | storage | P0 |
| `story_engine/profile.py` | NovelProfile | 作品身份唯一来源 | KEEP | `domain/novel.py` | `novel_id` 是所有权的根 | 文件系统 | P0 |
| `story_engine/templates.py` | Genre Template | 题材模板 | KEEP | `domain/genre.py` | 引擎无题材分支（有守卫） | yaml | P0 |
| `story_engine/content.py` | ContentPack | 内容包 schema + 校验 | KEEP | `domain/content_pack.py` | 内容包是数据，不是事实 | pydantic | P0 |
| `story_engine/wizard.py` | 新建向导 | 新小说 / 内容包初始化 | KEEP | `services/project.py` | | profile/content | P0 |
| `story_engine/settings_check.py` | `run_settings_check` | 起点可运行性自检（允许数据层修补） | KEEP | `quality/gates/startability.py` | **deterministic 质量门雏形** | driver/conditions | P4 |
| `story_engine/creative.py` | 创意入口 / 题材识别 | `GENRE_KEYWORDS` / `TONE_RULES` / `SELLING_POINT_TEMPLATES` | REPLACE_BY_LLM | `generation/premise.py` + `ai/gateway` | 固定文案表；但 `_catalog()` 校验（候选必须真实存在）**保留为业务规则** | content/templates | P3 |
| `story_engine/settings_gen.py` | 设定候选生成 | `RULE_TEMPLATES` / `PROTAGONIST_ROLES` / `SUPPORT_ROLES` / `FACTION_SHAPES` + `content_pack_draft()` 固定骨架（`起点场所` / `act_ask` / `ev_first_pressure`） | REPLACE_BY_LLM | `generation/settings.py` | 693 行硬编码创作骨架；schema 校验与 id 规则保留 | content/creative | P3 |
| `story_engine/outline_forge.py` | 四级大纲锻造 | `NARRATIVE_BEATS` / `ChapterTitleLedger`（`（第 N 次）`）/ `第{n}章：{body}` | REPLACE_BY_LLM | `generation/outline.py` | NF-003 根因；来源一致性 / 事实分层 / 唯一性门禁保留 | outline_revision/narrative | P3 |
| `story_engine/journey.py` | Journey 场景渲染 | 三原型硬编码行动 + rev1/rev2 固定场景文本 | REPLACE_BY_LLM | `generation/scene.py` | `journey_revision` 状态保留 | content/state | P3 |
| `story_engine/writer.py` | Writer 边界（正文） | `WriterPackage` / `validate_writer_output` + `render_scene` / `fallback_text` | COMPATIBILITY_ONLY | 保留在原位（preview / 降级文本）；校验层可被 Blueprint 复用 | 正文生成不是 V4 Core（ADR-011）；`fallback_text` 永不进入交付物 | state/effects | — |
| `story_engine/outline_revision.py` | 大纲修订 / 版本 / 导出 | 版本比较 + `docx_bytes` | REWRITE | `services/outline_revision.py` + `DeliveryService` | `docx_bytes` 被两处导出复用，必须收敛到 ExportService | outline repo | P6 |
| `story_engine/canon/*`（16 文件） | Canon 基础设施 | 稳定身份 / SQLite 唯一写入口 / 校验器 / 图 / mutation test / prose 防线 | KEEP | `domain/canon/*` + `persistence/canon_repo.py` | 结构成熟；路径需按 `novel_id` 参数化 | networkx/sqlite | P0 |
| `story_engine/chapter_ir/*`（13 文件） | Chapter Semantic IR | IR 模型 + schema gate + evidence + typed state + compiler + 可选 judge/verifier | KEEP | `domain/chapter_ir/*` + `quality/gates/semantic.py` | **V4 结构化生成的最佳现成契约**；NullJudge/NullVerifier 已是「无 LLM 也能跑」的设计 | pydantic | P3 |
| `story_engine/planning/*`（除下两行，38 文件） | Story Planning IR V1–M9 | IR / validator / repository+revision / context / graph / spine / route lab / projections / analyses | KEEP | `domain/planning/*` | 确定性 assembly 与校验，保留 | networkx | P0 |
| `story_engine/planning/chapter_compiler.py` | ArcPlan → Chapter IR（1,254 行） | 确定性渲染章节字段 | REWRITE | `generation/chapter_plan.py` | 字段渲染正属于 V4 的 LLM 结构化生成职责 | chapter_ir | P3 |
| `story_engine/planning/outline_batch.py` + `chapter_batch.py` | 批处理 session / checkpoint / resume | 长线批量推进 | KEEP | `services/batch.py` | 断点续跑是有价值的基础设施 | repository | P0 |
| `story_engine/spec/models.py` / `compiler.py` / `gaps.py` | NOVEL_SPEC | 规格 → 缺口 → 提案 → 作者确认 → Planning IR | KEEP | `domain/spec/*` | 提案/确认门禁与 V4 一致 | planning | P1 |
| `story_engine/spec/llm.py` | `LLMSpecProposalProvider` | **唯一真实外部模型调用**（urllib → DeepSeek，端点/模型/backoff 硬编码） | REWRITE | `ai/providers/deepseek.py` + `ai/gateway.py` | V4 Gateway 的迁移起点，不是重写起点 | urllib | P1 |
| `story_engine/historical_ir.py` | Historical Chapter IR Foundation | 570 章 deterministic materialization + `SOURCE_INVENTORY.json` + `_has_wasteland_entities()` 防串稿启发式 | COMPATIBILITY_ONLY | `persistence/legacy/historical_ir.py` | 冻结历史证据；`HISTORY_DIR` 硬编码 wasteland 导出路径 | workspace 证据 | FROZEN |
| `story_engine/reconstruction.py` | M10 Reconstruction | top-down derived artifacts | COMPATIBILITY_ONLY | `persistence/legacy/reconstruction.py` | 冻结 | 历史数据 | FROZEN |
| `story_engine/historical_adoption.py` | P15g adoption | 历史 foundation 接入 M11 repair | COMPATIBILITY_ONLY | 同上 | 冻结 | repair | FROZEN |
| `story_engine/repair.py` | M11 Content Repair | repair batch / frozen contract 读取 | COMPATIBILITY_ONLY | `persistence/legacy/repair.py` | **frozen contract / gate 不得修改** | m11_* | FROZEN |
| `story_engine/m11_*.py`（18 文件） | M11 production runs / blocker / closeout | 生产执行与验收 | COMPATIBILITY_ONLY | `legacy/m11/*` | 冻结证据；`m11_run02..12`（平均 ~56 行）应合并为「executor + 声明式配置」——**但只能在冻结解除后** | repair | FROZEN |
| `story_engine/m12_*.py` … `m18_*.py`（7 文件） | M12–M18 acceptance | baseline / preflight / acceptance / readiness | COMPATIBILITY_ONLY | `legacy/milestones/*` | 依赖本机历史数据，默认不运行 | 历史数据 | FROZEN |
| `story_engine/phase_snapshot.py` / `milestone_acceptance.py` | write-once snapshot 机制 | 阶段快照 + digest manifest | COMPATIBILITY_ONLY | `observability/phase_snapshot.py`（机制可复用） | 机制值得保留，但当前语义绑定 V2 里程碑 | 文件系统 | P10 |

---

## 4. 前端分类总表

| Path | Symbol / Module | Current Role | Classification | Target | Reason | Dependencies | Migration Phase |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `ui/src/v3/design-system/*` | tokens / Card / Button / Badge / IconRegistry / artworkManifest | 设计系统 + 视觉资源解析链 | KEEP | 不变 | 由 `test_v3_visual_asset_contract.py` + `docs/V3_VISUAL_ASSET_REQUIREMENTS.json` 守卫 | React | P9 |
| `ui/src/v3/viewmodel.ts` | `commandCenterViewModel` 等 | DTO → ViewModel（文案 / 状态语义 / 排序） | KEEP | `ui/src/presentation/*` | 核对结论：**不含业务规则**（仅 label 映射 / 排序 / 展示过滤） | v3/api types | P9 |
| `ui/src/v3/navModel.ts` | `parseRoute` | URL 路由唯一解析入口 | KEEP | 不变 | 单一解析入口（V3 验收要求） | — | P9 |
| `ui/src/v3/api.ts` | `v3Api` / `v3Writes` | 只读端点 + DTO 类型 + 复用既有写端点 | KEEP | `ui/src/api/generated.ts` | 注释明确不做业务判断；但 DTO 与 `ui/src/api.ts` 重复 | `../api` | P9 |
| `ui/src/v3/AppShell.tsx` / `CommandCenter.tsx` / `NovelLanding.tsx` | 框架 / 首页 / 存档选择 | 浏览层 | KEEP | 不变 | 消费同一 journey 投影 | viewmodel | P9 |
| `ui/src/v3/WorkspaceView.tsx` | 11 个工作区视图 | 实体 / 推演 / 大纲 / 检查 / 导出就绪 | REWRITE | `ui/src/workspaces/*` | 774 行单文件；计算仅为展示过滤（无业务规则） | viewmodel | P9 |
| `ui/src/v3/CreationFlow.tsx` | 创作链 | 创意 → 候选 → 设定 → 自检 → 推演 | REWRITE | `ui/src/creation/*` | 与 `SettingSeedPanel` 并行实现同一流程 | v3/api | P9 |
| `ui/src/v3/ExportFlow.tsx` | 导出工作区 | 导出物生成 / 下载 / 草稿列表 | REWRITE | `ui/src/delivery/*` | 直接展示 `export_id`（NR-004）；应展示「作品交付」而不是 planning 包 | v3/api | P6 |
| `ui/src/StoryBuilderPage.tsx` + 14 个 legacy 面板 | 19 页签高级工具 | 完整编辑（世界 / 角色 / 剧情 / 导演 / 路线 / 大纲 / Canon / 修复） | COMPATIBILITY_ONLY | `ui/src/legacy/*`（收敛后删除） | 已由 `LEGACY_COMPAT.md` 定义为 bridge；在 V4 新界面具备同等能力前不得删 | `ui/src/api.ts` | LATE |
| `ui/src/api.ts` | 端点客户端 + 全量 DTO（1,127 行） | legacy 面板的数据层 | DELETE | 由 generated client 取代 | 与 `v3/api.ts` **双份 DTO / 双份端点定义**（重复 truth source） | 无 | LATE |
| `ui/src/guidedFlow.ts` | 深链接 + `TAB_GROUPS` | URL 状态与页签词表 | KEEP | `ui/src/routing/*` | 单一 tab 词表 | — | P9 |
| `ui/src/storyBuilderSelection.ts` | 选择语义 | 多选组 / 单选组规则（展示层） | KEEP | 不变 | 展示层规则，结构合法性仍在后端 | — | P9 |
| `ui/src/components/*` / `hooks/useApiData.tsx` | CandidateCard / TruthLayerBadge / ProvenanceList / PanelBoundary | 共享展示组件 | KEEP | `ui/src/components/*` | 无业务逻辑 | React | P9 |
| `ui/src/style.css` | legacy 样式（341 行） | 高级工具样式 | COMPATIBILITY_ONLY | 随 legacy 面板删除 | 与 `v3/tokens.css` 并存 | — | LATE |

---

## 5. 脚本、数据与文档分类

| Path | Symbol / Module | Current Role | Classification | Target | Reason | Dependencies | Migration Phase |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `scripts/bootstrap_dev.ps1` | 开发引导 | 建 venv / 装依赖 / 跑测试 | KEEP | 不变 | 无 | — | P0 |
| `scripts/start_novelforge_ui.py` | 启动器 | 起后端 + 构建前端 | KEEP | 不变 | 无 | app | P0 |
| `scripts/creator_ui_test_server.py` | 隔离测试服务 | 用隔离数据根起服务 | KEEP | `tests/support/` | 浏览器门禁依赖它 | app | P0 |
| `scripts/validate_project.py` | 工程校验 | 路由边界 + catalog 加载断言 | KEEP | 不变 | 16 行守卫，V4 需扩展而不是替换 | app/catalog | P0 |
| `scripts/wasteland_001_m1b_closure.py` | M1b closeout | 历史 closeout 证据生成 | COMPATIBILITY_ONLY | `legacy/scripts/` | 被 `tests/test_m1b_v2_coverage.py:22` 引用 | story_engine | FROZEN |
| `scripts/seed_long_line_state.py` | 长线测试数据种 | 造浏览器测试所需 StoryState | COMPATIBILITY_ONLY | `tests/support/` | 被 `tests/browser_creator_long_lines.cjs:59` 调用 | storage | P0 |
| `novel/config/**`（103 文件） | 模板 / 内容包 / 目录 / schema | 数据（不是事实） | KEEP | `novel/config/**` + plugin packs | 引擎无题材分支的保证 | — | P0 |
| `novel/authoring/**`（2,381 文件） | 运行期作者数据 | Canon / StoryState / profile / 大纲 / 草稿 | KEEP | 不变（gitignored 边界保持） | 真实作者数据不进版本控制 | — | P0 |
| `novel/final/**`（69 tracked 文件） | 既有正文 | 无 owner 的手稿 | DELETE | — | 作者决策 A（V4-01 已执行）：无产品价值，不迁移 / 不归档 / 不导入 | 仅 `historical_ir`（已隔离） | V4-01 |
| `workspace/wasteland_001_exports/**` | frozen 证据 + 旧导出 | 570 章 historical / M11 证据 / 旧交付物 | DELETE | — | 作者决策 B（V4-01 已执行）：废弃产物，不导入 / 不做 fixture / 不进 legacy | reconstruction / repair / historical_ir（仅历史测试） | V4-01 |
| `workspace/pilot_v2/**` | V2 story-engine pilot 实验 | 与产品代码无引用关系 | UNKNOWN | 待定 | 未在作者决策 A/B 范围内；需单独裁定 | 无 | — |
| `novel/runs/**`、`novel/state/**`、`novel/pipelines/**`、`novel/learning/**`、`novel/status/**` 与 9 个空目录 | 历史内容产物 | 与产品代码无引用关系 | UNKNOWN | 待定 | 证据不足（见 inventory §6） | 无 | — |
| `tests/**`（171 py + 20 cjs + fixtures） | 测试与门禁 | 回归网 + 浏览器验收 | KEEP | 扩展 | V4 迁移的安全网 | 全仓 | P0 |
| `docs/**` | 文档 | 产品 / 架构 / 数据 / 兼容 SSOT | KEEP | 增加 `docs/v4/**` | — | — | P0 |

---

## 6. 数量统计

统计口径 = 上面的表格行数（家族合并行按 1 计）。

| Classification | V4-00 | V4-01（当前） | 变化 |
| --- | --- | --- | --- |
| `KEEP` | 63 | 63 | — |
| `REWRITE` | 13 | 12 | writer_integration 目标改为 Blueprint；writer.py 移出 |
| `REPLACE_BY_LLM` | 5 | 5 | — |
| `DELETE` | 1 | 3 | + `novel/final/**`、`workspace/wasteland_001_exports/**`（V4-01 已执行） |
| `MIGRATE` | 4 | 3 | `novel/final/**` 由 MIGRATE 改为 DELETE |
| `COMPATIBILITY_ONLY` | 13 | 13 | + `story_engine/writer.py`；− wasteland 导出树 |
| `UNKNOWN` | 1 | 2 | + `workspace/pilot_v2/**`（未在作者决策范围内） |
| **合计** | **100** | **101** | 新增 1 行（waseland 树从 workspace 行中拆出） |

> 统计由脚本从本文件表格第 4 列计数得到（见 §7 校验），不是人工估计。

### 6.1 这些数字说明了什么

```text
KEEP 占 63%  → V4 的基本盘是「继承内核」，不是「推倒重来」
冻结/兼容占 13% → 仍有大量 frozen 历史模块原地保留（不为目录整齐搬动）
REPLACE_BY_LLM 只有 5 行 → 硬编码创作逻辑集中在 5 个模块（creative / settings_gen /
    outline_forge / journey / recommendations），而不是「整个引擎」
REWRITE 12 行 → 主要是 application 层边界（routes / export / projection / blueprint context）
DELETE 3 行 → 其中 2 行是 V4-01 已执行的废弃资产删除（正文 + 570 章 historical）
```

### 6.2 全表最重要的三条结论

1. **`story_engine` 内核是资产**：行动-条件-效果、事件、伏笔、成长、路线、Canon、Chapter IR、Planning IR
   全部是确定性业务规则，`KEEP`，V4 要继承而不是重写。
2. **`REPLACE_BY_LLM` 高度集中**：5 个模块就是 NF-003 与「AI 生成质量」的全部现场；
   迁移它们不需要动引擎。
3. **真正的结构债在 application 层**：`story_builder_routes.py`（1,545 行）、`v3_projection.py`（1,682 行）、
   `export_package.py`、`writer_integration.py` —— 它们同时承担编排、读文件、拼路径、算派生状态。

---

## 7. 校验脚本（可复现）

```powershell
# 统计本文件表格里第 4 列的分类数量
$rows = Get-Content docs/v4/V4_MODULE_CLASSIFICATION.md -Encoding UTF8 |
        Where-Object { $_ -match '^\| ' -and $_ -notmatch '^\| ---' }
$rows | ForEach-Object { ($_ -split '\|')[4].Trim() } |
        Where-Object { $_ -in @('KEEP','REWRITE','REPLACE_BY_LLM','DELETE','MIGRATE','COMPATIBILITY_ONLY','UNKNOWN') } |
        Group-Object | Sort-Object Name | Format-Table Name, Count
```
