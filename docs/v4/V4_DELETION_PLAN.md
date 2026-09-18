# NovelForge V4 — Deletion Plan

> 状态：**V4-00 Architecture — 只登记，不删除**
> 铁律：**禁止「看起来没用，所以删」。** 每条删除必须有证据、替代物、移除阶段与验证方式。
> 与 `V4_MIGRATION_PLAN.md` 的关系：迁移计划定义「怎么换」，本文件定义「什么时候可以删」。

---

## 1. 删除的四个前置条件

任何一条进入「可执行删除」必须**同时**满足：

```text
C1  存在替代实现（同名能力已由新边界提供，且已通过验收）
C2  所有调用点已迁移（代码级证据：rg 结果为空，或只剩 legacy 适配器）
C3  数据兼容已完成（旧数据仍可读，或已明确不再需要）
C4  有验证手段（测试 / 源码守卫 / 验收脚本）能证明删除后系统仍正确
```

不满足任一条 → 该条只能是 `PENDING`（登记，不执行）。

---

## 2. 删除清单

### 2.1 V4-01 已执行删除（作者决策 A / B）

#### A. `novel/final/**`（旧正文）

```text
Exact Path      : F:/AI_小说/硅基升维/novel/final/（69 个 .md 文件，含 1 个含引号的畸形文件名）
File Count      : 69
Tracked         : 69 / 69（全部已跟踪，删除进入版本控制）
Size            : ~1.9 MB
Code References : 1 处 —— src/novelforge/story_engine/historical_ir.py
                  （source_inventory L527、prose_availability L927、_has_wasteland_entities L1822 防串稿启发式）
Test References : 0（没有任何测试直接断言这些文件）
Config Refs     : novelforge.project.yaml 的 protected_paths 列出 novel/final（V4-01 同步更新）
Decision        : 作者决策 A —— DELETE / NO MIGRATION / NO ARCHIVE / NO IMPORT
```

#### B. `workspace/wasteland_001_exports/**`（570 章 historical + 旧导出证据）

```text
Exact Path      : F:/AI_小说/硅基升维/workspace/wasteland_001_exports/
File Count      : 1918
Tracked         : 0（整个 workspace/ 在 .gitignore 中，磁盘删除不进版本控制）
Size            : ~62 MB
子目录           : chapter_ir_v1(31) / historical_chapter_ir_v1(581) / plan_v2(2) / plan_v3(122) /
                  reconstruction_v2(19) / repair_adoption_v1(709) / repair_v1(365) / writer_v1(6)
                  + 根级 WASTELAND_001_* 报告 / 大纲 / 审计产物
Code References : 47 个 src/scripts 文件（含 historical_ir / repair / reconstruction /
                  historical_adoption / m11_* 18 个 / m12..m18 7 个 / export_package /
                  inspector / writer_integration / novel_admin / canon_routes / phase_snapshot /
                  scripts/wasteland_001_m1b_closure.py）
Test References : 53 个测试文件
Config Refs     : novelforge.project.yaml（local_only_paths.workspace）、docs/DATA_MODEL.md、
                  docs/LEGACY_COMPAT.md
Decision        : 作者决策 B —— DELETE / NO IMPORT / NO FIXTURE / NO legacy/
```

> 删除执行后，产品运行时不再有任何路径指向这两类资产；
> 仍引用它们的 frozen 模块（historical_ir / repair / reconstruction / m11_* / m12–m18）
> **原地保留但脱离产品写路径**，并纳入 `legacy/manifest`（见 §4）。

| Path | Symbol | Why Delete | Replacement | Dependency Impact | Migration Dependency | Safe Removal Phase | Verification |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `ui/src/api.ts` | 全量端点客户端 + 全量 DTO（1,127 行） | **双份 DTO / 双份端点定义**：与 `ui/src/v3/api.ts`（426 行）重复声明同一批后端契约，属于重复 truth source（`AGENTS.md` §5） | `ui/src/api/generated.ts`（从后端 schema 生成）+ 各 feature client | 被 `StoryBuilderPage.tsx`、`guidedFlow.ts`、14 个 legacy 面板引用 | 必须先完成：新 UI 覆盖 legacy 面板全部能力（V4-10） | `LATE` | 删除后 `tsc --noEmit` PASS + 浏览器门禁 P0–P7 + advanced tools 全通过 |
| `ui/src/style.css` | legacy 面板样式（341 行） | 随 legacy 面板消失即无宿主；与 `v3/design-system/tokens.css` 体系并存 | design-system tokens | 被 `StoryBuilderPage.tsx` 与 14 面板引用（class 名） | 同上一行 | `LATE` | 同上 + 视觉资源契约测试 PASS |
| `ui/src/GuidedFlowPanel.tsx` | 引导流旧面板（166 行） | 与 `ui/src/v3/CreationFlow.tsx`（580 行）实现**同一流程的两套 UI** | CreationFlow（V3 原生） | `StoryBuilderPage` 的 `guided` 页签 | 新 UI 覆盖「引导流」能力 | `V4-10` | 浏览器：创作链从创意到开始推演全通过（含未保存草稿恢复） |
| `ui/src/CreativeBriefPanel.tsx`、`ui/src/SettingSeedPanel.tsx` | 创意 / 设定候选旧面板（191 + 261 行） | 与 `CreationFlow.tsx` 的创意与设定步骤重复 | CreationFlow | `StoryBuilderPage` 的 `builder` 等页签 | 同上 | `V4-10` | 同上（含 9 组设定候选逐组选择） |
| `story_builder/recommendations.py` | 十步规则推荐模板表 | 规则式**创作**推荐（模板化候选与理由） | `generation/design_options.py`（经 `ai/gateway`，候选仍受真实目录校验） | `api` 的 `POST /sessions/{id}/recommendations`；UI 调用点 `ui/src/api.ts:1158` | 必须先有 gateway（V4-02）+ 结构化生成（V4-04） | `V4-04` | 生成候选仍 100% 指向真实模板 / 内容包（沿用 `creative._catalog()` 断言）+ API 测试 |
| `story_engine/creative.py` | `GENRE_KEYWORDS`、`TONE_RULES`、`SELLING_POINT_TEMPLATES`、`REASON_BY_GENRE` | 硬编码创作文案表（题材关键词 / 基调理由 / 固定卖点） | `generation/premise.py` + prompt contract | 被 `suggest_creative_brief` 使用；API `/creative/suggest` | V4-02 gateway + V4-04 生成器 | `V4-04` | 候选仍必须指向真实模板 / 内容包（保留 `_catalog()` 校验测试）；NF-003 类质量问题在样本中消失 |
| `story_engine/settings_gen.py` | `RULE_TEMPLATES`、`PROTAGONIST_ROLES`、`SUPPORT_ROLES`、`FACTION_SHAPES`、`CONFLICT_MARKERS`、`RESOURCE_MARKERS`、`FACTION_MARKERS`、`RELATION_MARKERS` | 硬编码创作骨架（世界规则 / 主角原型 / 势力形态 / 标记词表） | `generation/settings.py` + prompt contract | `content_pack_draft()` 依赖这些表生成候选文案 | V4-02 + V4-04 | `V4-04` | `settings_check.run_settings_check()` 仍 0 error（起点可运行性不下降）+ 内容包 schema 校验通过 |
| `story_engine/settings_gen.py` | `content_pack_draft()` 中的固定骨架文案（`起点场所` / `工作场所` / `隐藏节点` / `act_investigate` 等 8 个固定行动 / `ev_first_pressure` / `ev_world_shift`） | 固定剧情与行动模板 = 假创作引擎；V3 已知缺陷 NF-016（占位名）的直接来源 | `generation/settings.py`（结构与 id 规则保留，文案由 LLM 产出） | 被 `settings_check`、`save_setting_seed` 使用 | V4-04 | `V4-04` | 生成内容包仍通过 `ContentPack.model_validate` + 起点自检；占位名不出现在导出物中（DeliveryValidator 检查项） |
| `story_engine/outline_forge.py` | `NARRATIVE_BEATS`（8 个固定 beat） | 固定 beat 表决定章节叙事功能 = 模板化章节 | `generation/outline.py`（beat 由 LLM 结合剧情产出） | `_planned_chapters` / `forge_outline` 使用 | V4-04 | `V4-04` | 章节标题不含字段标签（`FIELD_LABEL_BLACKLIST` 断言保留）+ 来源一致性通过 |
| `story_engine/outline_forge.py` | `ChapterTitleLedger` 的 `f"{base}（第 {count} 次）"` 兜底 | **NF-003 的直接实现**：字符串唯一但语义重复 | LLM 生成真实不同标题 + Q6 语义重复门禁 | `allocate()` 被章节标题分配调用；`used` / `counts` 状态无其他消费者 | V4-04 + V4-05（Q6） | `V4-05` | Q6 语义重复门禁上线后：样本 30 章标题无语义重复（人工 + LLM 双确认），且无「（第 N 次）」形式 |
| `story_engine/journey.py` | `suggestions_for()` 三原型固定行动映射 + `scene()` 的 `rev1/rev2` 固定场景文本 | 硬编码的场景与建议文案（同一场景反复出现同样文字） | `generation/scene.py` + prompt contract（`journey_revision` 状态保留） | `JourneyRuntime.scene()` 被 `adventures.py` / legacy 面板消费 | V4-04；注意 `adventures` 属 COMPATIBILITY_ONLY，需保留读旧存档能力 | `V4-04` | 旧存档仍可读（`test_story_builder_adventures.py` PASS）+ 新推演场景不再文本重复 |
| `story_engine/writer.py` | `fallback_text()` 作为**可接受输出**的路径 | 用确定性文本掩盖 LLM 失败（`LLM_UNAVAILABLE` 时仍产出被接受文本） | 显式降级：fallback 只作为 `warnings: ["FALLBACK_USED"]`，且不得进入交付物 | `WriterDraftService.create_draft` 使用；导出不直接消费 | V4-02（错误分类）+ V4-05（Q9） | `V4-06` | 交付物扫描：不存在 fallback 文本；Result Envelope 出现 `FALLBACK_USED` 时导出被拒 |
| `story_engine/{creative,settings_gen,outline_forge,journey}.py` | 固定创意内容表（`TONE_RULES` / `SELLING_POINT_TEMPLATES` / `RULE_TEMPLATES` / `PROTAGONIST_ROLES` / `SUPPORT_ROLES` / `FACTION_SHAPES` / `NARRATIVE_BEATS` / `content_pack_draft` 固定骨架 / journey 三原型场景文本） | V4-04 起不再是唯一创作来源（`generation` + `blueprint` 是结构化路径），但**仍是未配置模型时的 V3 产品默认行为** | `generation/tasks/*` 结构化生成 | V3 创作链（UI / 浏览器门禁 / 900+ 测试） | V4-04 已把 provider 迁到 Gateway；表本身待 V4-05/V4-10 决定 | `V4-10`（或作者明确要求时） | 新路径成为默认 + 浏览器门禁改走新路径 + 作者确认；`legacy/manifest.py` 已登记 removal condition |
| `story_engine/outline_forge.py` | `ChapterTitleLedger` 的「（第 N 次）」兜底 | NF-003 根因；新路径标题由 `generation/tasks/chapter.py` 生成 | `generation` + V4-05 Q6 语义重复门禁 | 旧大纲路径 | V4-04 起新路径不使用它 | `V4-05` | Q6 门禁上线 + 30 章样本无「（第 N 次）」 |
| `story_builder/outlines.py` | `export()` / docx / markdown 拼装函数 | 与 `export_package` 并存的第二套导出拼装 | `ExportService` | `api` 的 `/outlines/{package_id}/export`、`/outline/export` | V4-07 | `V4-07` | 只允许 `ExportService` 产生导出物（源码守卫）+ 导出物文本扫描 |
| `story_engine/outline_revision.py` | `docx_bytes()` 在 domain 层的实现 | 交付格式细节属于 Delivery，不属于 Domain | `DeliveryService`（`interfaces`/`application` 层） | 被 `export_package` 与 `outlines` 复用 | V4-07 | `V4-07` | 依赖矩阵守卫：domain 不 import docx 序列化器 |
| `story_builder/export_package.py` | `RECON_DIR` / `PLANNING_INDEX` / 内联 `canon/wasteland_001.sqlite` | 单作品路径硬编码（ownership 违规）+ NR-002 根因 | `persistence/paths.py` + `persistence.canon_repo(novel_id)` | 影响所有作品导出 | V4-01（paths）+ V4-07（ExportService） | `V4-07` | 非 wasteland_001 作品导出：`excluded` 列出 legacy 分区、无历史数据混入（新增测试） |
| `story_builder/writer_integration.py` | `CANON_DB` 常量 | 单作品路径硬编码 | `persistence.canon_repo(novel_id)` | `WriterContextBuilder._canon_block()` | V4-01 | `V4-01` | 任意 novel_id 都能取到自己的 Canon（有测试） |
| `story_builder/inspector.py` | `CANON_DB` 常量 | 同上 | 同上 | Inspector / Repair 诊断 | V4-01 | `V4-01` | 同上 |
| `story_builder/ui_flow.py` | 第二套 stage / next-step 计算 | 与 `journey_service` 形成两套状态推导（V3 曾修过同类问题 NF-005） | `journey_service`（单一投影） | `api` 的 `/guided-flow`、`/settings/*`、legacy 面板 | V4-01 | `V4-01` | 同一小说在 Landing / Command Center / guided-flow 得到同一 stage + progress（新增一致性测试） |
| `api/story_builder_routes.py` | 内联编排逻辑（路由体内的业务判断） | 路由承担业务规则 → UI/REST/MCP 无法共用 | `application/services/*` | 全部 UI 调用点 | V4-01 起逐段迁移 | `V4-10` | 每个路由函数 ≤ 参数映射 + service 调用（源码守卫：路由文件不 import domain 模块） |
| `novel/authoring/story_engine/writer/*/drafts/*.json` | preview 草稿（无 revision） | 无法回答「改了什么」；且**正文不再是 V4 canonical artifact**（ADR-011） | Blueprint 节点 revision（非正文） | UI 草稿列表、导出 | V4-06 | **不删除**（只读兼容保留） | 保留为只读 preview；作者确认无数据后可删 |
| `novel/final/**` | 无 owner 旧正文 | **已执行删除**（V4-01，证据见 §2.1 A） | — | — | V4-01 | ✅ done | `git ls-files novel/final` 为空 |
| `workspace/wasteland_001_exports/**` | 570 章 historical / M11 证据 | **已执行删除**（V4-01，证据见 §2.1 B） | — | — | V4-01 | ✅ done | 目录不存在；`rg wasteland_001_exports src` 无产品侧引用 |

---

## 3. 明确**不**删除的清单（防止误删）

| Path | 为什么看起来「可以删」 | 为什么不删 |
| --- | --- | --- |
| `story_engine/m11_*.py`（18 文件）、`m12_*`…`m18_*`（7 文件） | 其中 `m11_run02.py`…`m11_run12.py` 平均仅 56 行，形似复制脚本 | 属 **frozen 验收证据**，由 `tests/test_v2_frozen_guard.py` 与 `docs/FROZEN_EVIDENCE_MANIFEST.json` 守卫（`AGENTS.md` §16/§20）。重复问题记入 Architecture Debt，**冻结解除前不得合并** |
| `story_engine/repair.py`、`historical_ir.py`、`reconstruction.py`、`historical_adoption.py` | 体量大、只服务历史作品 | frozen Repair Contract / Gate / 570 章 IR 证据；`AGENTS.md` §16.1 禁止自动修改 |
| `story_builder/adventures.py` | 新旅程已用 `rules_version = 3` | 旧存档只读兼容（`docs/LEGACY_COMPAT.md`）；删除会让旧作品打不开 |
| ~~`workspace/wasteland_001_exports/**`~~ | — | **已删除（V4-01，作者决策 B）**；`workspace/pilot_v2/**` 仍保留、待裁定 |
| ~~`novel/final/**`~~ | — | **已删除（V4-01，作者决策 A）**；不再是「不删除清单」成员 |
| `novel/runs/**`、`novel/state/**`、`novel/pipelines/**`、`novel/learning/**`、`novel/status/**`、9 个空目录 | 产品代码无引用 | 证据不足（`V4_CODEBASE_INVENTORY.md` §6）；需先确认是否为外部写作流程产物 |
| ~~`scripts/wasteland_001_m1b_closure.py`~~ | — | **已删除（V4-01，作者决策 B）**：只服务 570 章 historical 的 M1b closeout；其唯一调用方 `tests/test_m1b_v2_coverage.py` 同时删除 |
| `scripts/seed_long_line_state.py` | 一次性脚本观感 | 被 `tests/browser_creator_long_lines.cjs:59` 引用（浏览器门禁仍需要），保留 |
| `ui/src/StoryBuilderPage.tsx` + 14 个 legacy 面板 | 与 V3 工作台功能重叠 | 它们是**唯一**的完整编辑入口（角色 / 地点 / 势力 / 路线 / Canon / 修复）。删除前必须由新 UI 提供同等能力（`docs/LEGACY_COMPAT.md` 的 bridge 定义） |
| `story_builder/ai_recommendations.py` | 目前 provider 恒为 None（`AI_UNAVAILABLE`） | 它实现了「AI 只能补充、不能新增结构」的合并与校验逻辑，是 V4 Gateway 的良好输入（分类 = REWRITE，不是 DELETE） |
| `story_builder/cross_genre_e2e.py` | 看起来像测试代码 | 它是 3 题材 13 步的回归 harness，V4 迁移的主要安全网 |
| `story_builder/writer_integration.py`（`WriterDraftService` / `WriterContextBuilder` / `writer_export_bundle`） | 正文草稿能力，V4 的 canonical artifact 已改为 StoryBlueprint（ADR-011） | **V4-06 已评估（docs/v4/V4_06_EDITOR_INVENTORY.md）**：它是正文 preview 能力，仍被 `/api/story-builder/writer/*` 路由与 legacy 产品面使用；Blueprint Editor **不复用**它。移除条件：V4-10 UI 不再依赖 writer 草稿入口 + legacy 测试退出。当前保留 = compatibility |
| `story_engine/outline_revision.py`（`revise_item` / `restore_version` / `impact_of_change`） | 与 Blueprint Editor 的编辑 / 恢复 / 影响面功能重叠 | **V4-06 已评估**：它们服务 outline package（V3 大纲产品面，UI 与测试仍在使用），只是**思路**被 ADAPT（append-only restore / 结构 diff / 受影响下游列表）。移除条件：V4 产品路径完全切到 Blueprint Editor 且 V4-10 不再渲染 outline 编辑 |
| `story_builder/export_package.py`（planning export）+ `/export/package` 路由 | V4 交付物已改为 Story Blueprint Package（Delivery） | **V4-07 已评估**：仍被 V3 导出 UI / 既有隔离测试使用，且 `ExportService.projection()` 仍是 legacy 兼容面。移除条件：V4-10 导出 UI 切到 `/api/story-builder/delivery/**` + legacy 浏览器门禁退出 → `DELETE after V4-10 UI switch` |
| `story_builder/outlines.py` / `story_engine/outline_revision.py` 的导出入口（`/outline/export`、`/outlines/{id}/export`） | Delivery 已提供 JSON / Markdown / DOCX | **V4-07 已评估**：服务 V3 大纲产品面。移除条件同上一行（`DELETE after V4-10 UI switch`） |
| `story_builder/writer_integration.py::writer_export_bundle` + `/export/writer-bundle` | 交付链已改为 Delivery | **V4-07 已评估（§58）**：只服务旧正文 Writer 的联合入口 → `COMPATIBILITY_ONLY`。移除条件：正文 writer 路径随 V4-10 退出 |
| 重复的 DOCX 生成路径（`outline_revision.docx_bytes` vs `delivery/exporters/docx_exporter.py`） | 看起来可以合并 | **保留两条**：前者服务 outline 产品面（V3），后者是 Blueprint 交付物；数据源不同、生命周期不同。移除条件随 outline 导出路径一并退出 |
| V4-09 无删除项 | — | **V4-09 评估结论**：插件平台只做 additive 扩展，不删除任何既有路径。它把 V4-07/V4-05/V4-08 的注册表从「无 owner / last wins」升级为「owner + 不可覆盖 Core + 可按插件卸载」（见 `V4_PLUGIN_CONTRACT.md` §8）。`story_builder` / `story_engine` 的 legacy 面随 V4-10 UI 切换后按本表既有条件退出 |

---

## 4. 删除顺序（依赖图）

```text
V4-01  ownership 参数化
   ├─ writer_integration.CANON_DB        （先删常量，改 repository 调用）
   ├─ inspector.CANON_DB
   ├─ export_package 路径常量            （保留函数，先换数据源）
   └─ ui_flow 第二套 stage 公式

V4-02  LLM Gateway
   └─ （无直接删除；为 V4-04 铺路）

V4-04  Structured Generation
   ├─ creative 文案表
   ├─ settings_gen 文案表 + content_pack_draft 固定骨架
   ├─ outline_forge NARRATIVE_BEATS
   ├─ journey 三原型 / rev 场景文本
   └─ recommendations 模板表

V4-05  Quality Loop
   └─ ChapterTitleLedger「（第 N 次）」兜底

V4-06  Writer
   └─ writer.fallback_text 作为可接受输出的路径

V4-07  Delivery
   ├─ outlines 导出拼装
   ├─ outline_revision.docx_bytes 的 domain 位置
   └─ export_package 的 legacy 分区混入

V4-09  Plugins
   └─ （无删除；只新增扩展点贡献模型 + ownership/unregister 语义）

V4-10  UI
   ├─ ui/src/api.ts（双份 DTO）
   ├─ ui/src/style.css
   └─ GuidedFlowPanel / CreativeBriefPanel / SettingSeedPanel（重复流程）

LATE（最终）
   └─ StoryBuilderPage + 剩余 legacy 面板 + adventures（需作者确认旧存档）
```

---

## 5. 每条删除的验证模板

```text
1. rg 调用点为空（或只剩显式 legacy 适配器）— 记录命令与输出
2. targeted tests PASS
3. full pytest PASS（默认套件）
4. historical_acceptance 仍可运行（不因删除而 import error）
5. scripts/validate_project.py PASS
6. production state before == after
7. 涉及导出 → 导出物文本扫描 + 人工可读性检查
8. 涉及 UI → 浏览器门禁 P0–P7 + advanced tools
9. frozen guard（tests/test_v2_frozen_guard.py）PASS
```

---

## 6. Architecture Debt（不是删除对象，但必须记录）

以下结构问题**不能**通过删除解决，登记为债务以便后续阶段处理：

| Debt ID | Location | Problem | Impact | Recommended Fix | Blocking Future Phase | Safe To Defer |
| --- | --- | --- | --- | --- | --- | --- |
| AD-001 | `story_engine/m11_run02.py` … `m11_run12.py`（11 个文件，平均 56 行） | run executor 复制（`AGENTS.md` §8 的典型案例） | 维护成本、易漂移 | 抽象为「generic production-run executor + 声明式配置」 | 否 | 是（frozen 期间不可动） |
| AD-002 | `story_engine/m12_acceptance.py`（1,240 行）、`m11_*` 大文件 | milestone 逻辑与业务逻辑混居 | 冻结边界模糊 | 迁入 `legacy/milestones/` 并加只读标记 | 否 | 是 |
| AD-003 | `src/novelforge/api/story_builder_routes.py`（1,545 行） | 路由 / 编排 / 业务判断混居 | UI/REST/MCP 无法共用（V4 核心阻塞） | V4-01 拆 service | **是** | 否 |
| AD-004 | `story_builder/v3_projection.py`（1,682 行） | 单一模块承载 7 类投影 | 修改风险高、测试粒度粗 | 按投影拆分（journey / entities / simulation / outline / review / export） | 否 | 是（V4-01 部分处理） |
| AD-005 | `ui/src/api.ts` ↔ `ui/src/v3/api.ts` | 双份 DTO | 契约漂移风险 | 生成式 client | 否 | 是 |
| AD-006 | `project_id` / `novel_id` 双名同值 | 所有权命名歧义 | MCP / 导出 / 多作品支持受影响 | 统一命名 + 兼容读取 | **是**（V4-01） | 否 |
| AD-007 | `history` 形态散落（`blueprints` / `outlines` / `planning` / `StoryState` 各自版本实现） | 四套版本语义并存 | revision 统一成本高 | `core/revision.py` 统一语义 | 否 | 是 |
| AD-008 | `novel/` 下 9 个空目录 + 1108 文件 `novel/runs/` | 仓库语义不明 | 仓库卫生与「什么算产品」的边界模糊 | 需要作者裁定（BLOCKER-02） | 否 | 是 |
