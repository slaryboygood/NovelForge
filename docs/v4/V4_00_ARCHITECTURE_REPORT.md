# V4-00 ARCHITECTURE RESULT

> ⚠️ **V4-01 更新说明（2026-09-17）**：本报告是 **V4-00 的历史记录**，部分结论已被作者决策取代：
>
> ```text
> · canonical creative artifact  由「正文 ChapterRevision」改为「StoryBlueprint」（ADR-011，取代 ADR-003）
> · novel/final/*.md（69 个 tracked 正文）→ 已删除（V4-01）
> · 570 章 historical（workspace/wasteland_001_exports，1918 文件）→ 已删除（V4-01）
> · §6「正文 source of truth」一行、§10「V4-01 recommended scope」的正文相关项已作废
> ```
>
> V4-01 的对齐结果见 `docs/v4/V4_MODULE_BOUNDARIES.md`、`docs/v4/adr/ADR-011-*.md`
> 与 `docs/v4/V4_01_BOUNDARY_FOUNDATION_REPORT.md`。**本报告其余内容（扫描事实 / 分类统计 /
> 结构问题 / 风险）仍然有效。**

> 阶段：**V4-00 Architecture Audit & Architecture Freeze**
> 分支：`v4/00-architecture`
> 基线：`novelforge-product-v3-final`（commit `f02ca8c`）
> 业务代码改动：**0 个文件**
> 结论：**V4-00 = PASS**

---

## 1. Repository scan summary

| 区域 | 文件数 | 行数 | 说明 |
| --- | --- | --- | --- |
| `src/`（Python） | 188 | 68,038 | 含 40+ 冻结历史模块（`m11_*`…`m18_*`、`historical_ir`、`repair`…） |
| `ui/src/`（TS/TSX） | 45 | 10,482 | `v3/`（V3 工作台）+ legacy 高级工具面板 |
| `tests/*.py` | 171 | 31,118 | 默认套件 892 passed / 687 deselected |
| `tests/*.cjs` | 20 | — | 真实浏览器门禁（Playwright） |
| `novel/config/**` | 103 | — | 题材模板 / 内容包 / 十步目录 / schema |
| `scripts/` | 6 | 677 | 启动 / 校验 / 隔离测试服务 / 历史 closeout |
| `workspace/**`（gitignored） | 254 | — | frozen 证据：570 章 IR / M11 overlay / contract / gate |
| `novel/authoring/**` | 2,381 | — | 运行期作者数据（gitignored 主体） |
| `novel/final/*.md`（tracked） | 69 | — | **无 owner 的既有正文** |

扫描覆盖：入口 / 配置 / API routes / service / utility / generator / exporter / writer /
测试 / 脚本 / 兼容代码 / 数据目录 / 前端 / 非 `src` 目录。

基线验证（扫描时执行；因本轮未改动任何代码文件，结论持续有效）：

```text
pytest -q        892 passed / 687 deselected / 0 failed（280s）
git tag          novelforge-product-v3-final（未移动）
git status       仅 docs/ 改动（0 个业务代码文件）
```

---

## 2. Current V3 architecture summary

```text
UI（ui/src/v3 + ui/src legacy bridge）
   ↓ HTTP
api/story_builder_routes.py（1,545 行，唯一业务入口，含内联编排）
   ↓ 直接函数调用（无 service 层）
story_builder/*（application：projection / export / writer / inspector / admin / sessions）
   ↓
story_engine/*（domain：StoryState / Action-Condition-Effect / 事件 / 伏笔 / 成长 / 路线 /
                Canon / Chapter IR / Planning IR / 规则式创作内容）
   ↓
文件系统（JSON）+ Canon SQLite
```

三条与 V4 直接相关的现状事实：

1. **质量能力已经存在但不统一**：9 处 deterministic validator / finding 形态各自为政。
2. **结构化契约已经成熟**：`ChapterSemanticIR` / `StoryPlanningIR` / `ContentPack` /
   `OutlinePackage` 都带严格 gate —— V4 不需要新造模型。
3. **所有权缺失**：产品代码存在按作品写死的路径（`wasteland_001`），
   且 `novel/final/*.md`（另一部手稿）没有任何 owner。

---

## 3. Top 10 structural problems

| # | 问题 | 证据 | 影响 |
| --- | --- | --- | --- |
| 1 | **单作品路径硬编码** | `export_package.py` 的 `RECON_DIR` / `PLANNING_INDEX` / `canon/wasteland_001.sqlite`；`writer_integration.CANON_DB`；`inspector.CANON_DB`；`historical_ir.HISTORY_DIR` | 任意作品导出混入 WASTELAND 数据（NR-002）；多作品支持不成立 |
| 2 | **正文没有 owner** | `novel/final/*.md`（69 tracked 文件）无产品代码写入；`WriterDraftService` 只有 create / list / get / sync，无 update | 无法回答「正文 source of truth 是什么」；事实上无法写作 |
| 3 | **硬编码创作内容集中在 5 个模块** | `creative.py`（`TONE_RULES` / `SELLING_POINT_TEMPLATES`）、`settings_gen.py`（`RULE_TEMPLATES` / `PROTAGONIST_ROLES` / `content_pack_draft` 固定骨架）、`outline_forge.py`（`NARRATIVE_BEATS` / `（第 N 次）`）、`journey.py`（三原型 / rev 场景文本）、`recommendations.py` | NF-003 与生成质量问题的根因 |
| 4 | **路由承担业务** | `api/story_builder_routes.py` 1,545 行，含内联编排与业务判断 | UI / REST / MCP 无法共用一个业务层（V4 核心阻塞） |
| 5 | **导出存在四套拼装** | `export_package` / `outlines` / `outline_revision.docx_bytes` / `writer_export_bundle` | 交付一致性无法保证（NR-003 / NR-004） |
| 6 | **状态推导两套** | `v3_projection._journey_projection()`（唯一入口）vs `ui_flow.py` 独立 stage / next_step | 同一作品在不同入口可能显示不同阶段（NF-005 同类风险） |
| 7 | **所有权命名歧义** | sessions / blueprints 用 `project_id`；profile / canon / writer 用 `novel_id`，同值不同名 | MCP resource 树 / 导出结构 / 多作品支持全部受影响 |
| 8 | **质量对象不统一** | `CheckFinding` / `GraphFinding` / `Verdict` / findings / 就绪度 6 步，共 5 种形态 | UI / 修复 / 导出无法复用同一语义 |
| 9 | **LLM 边界不存在** | `spec/llm.py` 直接 `urllib` 调 DeepSeek（端点 / 模型 / backoff 硬编码）；三处业务模块鸭子类型 provider | 换 provider / 成本控制 / trace / 缓存全部缺失 |
| 10 | **冻结历史代码体量大且不可删** | 40+ 模块（`m11_*` 18 个、`m12..m18` 7 个、`historical_ir` / `reconstruction` / `repair` / `historical_adoption`），约 12,000+ 行 | 新结构容易被历史代码污染；需要显式 `legacy/` 通道（Master Plan 未规划） |

---

## 4. KEEP / REWRITE / REPLACE_BY_LLM / DELETE statistics

统计口径：`V4_MODULE_CLASSIFICATION.md` 的表格行（家族按 1 行计，共 100 行）。

| Classification | Count |
| --- | --- |
| `KEEP` | 63 |
| `REWRITE` | 13 |
| `REPLACE_BY_LLM` | 5 |
| `DELETE` | 1 |
| `MIGRATE` | 4 |
| `COMPATIBILITY_ONLY` | 13 |
| `UNKNOWN` | 1 |

读法：**V4 的基本盘是继承内核（63%），不是推倒重来**；硬编码创作逻辑只集中在 5 个模块；
真正需要消失的结构只有 1 处（重复的 UI DTO / 端点层）。

---

## 5. V4 proposed architecture

```text
interfaces/ { api, mcp }         ← 协议转换，无业务规则
        ↓
application/ { services, projections }  ← 用例编排（原 story_builder/）
        ↓
domain/ { story, knowledge, canon, chapter_ir, planning, outline, route }  ← 原 story_engine/ 主体
        ↓
persistence/ { *_repo, writer_store, paths }   ← 唯一碰文件系统 / SQLite 的地方

横切（不反向依赖 domain）：
ai/ { gateway, contracts, router, policy, providers, usage, trace, cache }
memory/ { store, retrieval, context_builder, episodic, semantic, preferences }   ← 派生层，非 truth
generation/ { premise, settings, outline, chapter_plan, scene, draft }
quality/ { contracts, service, gates, repair }
plugins/ { base, registry, loader, permissions, builtin }
observability/ { logging, metrics, audit, token_usage }
legacy/ { m11, milestones, historical_ir, repair, reconstruction }   ← 冻结隔离区（新增）
```

目录决策依据（与 Master Plan 的差异）见 `V4_ARCHITECTURE.md` §3.1；
暂时**不建**的抽象见 §3.2（`persistence/migrations/`、事件总线、向量库、插件市场、CLI）。

---

## 6. Canonical sources of truth

| 对象 | Owner（V4） | 现状 |
| --- | --- | --- |
| 正文 | `persistence.writer_store` 的 append-only `ChapterRevision` | ❌ 不存在（`novel/final/*.md` 无 owner） |
| StoryState | `persistence.story_state`（唯一写入口 ActionResolver） | ✅ 已成立 |
| Canon | `persistence.canon_repo` + `CanonService`（唯一写 SQL 处） | ✅ 已成立，路径需按 novel_id 参数化 |
| Journey | `application.services.journey_service`（唯一 JourneyProjection） | ⚠️ 已收敛到 `_journey_projection`，但 `ui_flow` 另有第二套 |
| Export | `ExportService`（只从 repository 读） | ⚠️ 四套拼装 + 单作品硬编码 |
| 章节语义 | `domain.chapter_ir`（ChapterSemanticIR） | ✅ 已成立 |
| 规划 | `domain.planning`（StoryPlanningIR，不可变 revision） | ✅ 已成立 |
| 记忆（派生） | `memory/*`（可重建、永不权威） | ❌ 不存在（episodic / preferences 完全缺失） |

---

## 7. Major architecture decisions

| ADR | 决策 | Status |
| --- | --- | --- |
| ADR-001 | `application/services` 为唯一业务入口（UI / REST / MCP 共用） | Proposed |
| ADR-002 | `ai/gateway` 为唯一模型入口；provider 不认识业务概念 | Proposed |
| ADR-003 | 唯一 canonical writer store = append-only `ChapterRevision` | Proposed（含作者待决项） |
| ADR-004 | JourneyProjection 是唯一进度 / 下一步来源 | Proposed |
| ADR-005 | 统一 Quality Contract + Q0–Q9（适配既有 validator，不重写） | Proposed |
| ADR-006 | 统一 revision 语义 + `expected_revision` 写入协议 | Proposed |
| ADR-007 | 每个 artifact 都有 `project_id` / `novel_id` / `revision` / `source_ids` | Proposed（含命名待决项） |
| ADR-008 | MCP 是接口层，tool 实现 ≤ 3 行，V4-08 才暴露 | Proposed |
| ADR-009 | 插件只能拿 PluginHost，不得触达 DB / 文件 / gateway override | Proposed |
| ADR-010 | 结构化生成指向既有模型（不新造 schema） | Proposed |

---

## 8. Master Plan assumptions challenged

| # | 原假设 | 代码事实 | 建议 |
| --- | --- | --- | --- |
| CHALLENGE-01 | 需要新建 `domain/` | `story_engine/` 已是成熟领域层，63% 分类为 KEEP | 原地收敛命名，**不建平行模型** |
| CHALLENGE-02 | 新增 `memory/` | `story_engine/memory.py` 已是「谁知道什么」（知识事实） | 旧模块改名 `domain/knowledge.py`，`memory/` 留给派生检索层 |
| CHALLENGE-03 | 新增 `repair/` | M11 frozen `repair.py`（1,695 行）不可改 | 新能力命名 `quality/repair/`，历史路径入 `legacy/` |
| CHALLENGE-04 | 目录清单无 frozen 位置 | 40+ 冻结模块约 12,000+ 行 | 新增 `legacy/` 显式隔离 |
| CHALLENGE-05 | V4-02…V4-05 是全新实现 | 已有 `spec/llm.py`（真实调用）、ChapterIR/PlanningIR（结构化契约）、9 处质量门、WriterContextBuilder（分层上下文） | 定位改为「把既有孤立能力提升为边界层」 |
| CHALLENGE-06 | `persistence/migrations/` | 当前是 JSON + 单 SQLite，且 StoryState 已有 `schema_version` 升级路径 | migrations 标记 Deferred，先统一 revision 语义 |
| CHALLENGE-07 | `generation/` 新模块清单 | 输出模型已存在（ContentPack / ChapterIR / PlanningIR / OutlinePackage / WriterPackage） | 生成器只产出既有模型，不新增 schema |
| CHALLENGE-08 | Q0–Q9 作为新层 | Q0/Q2/Q3/Q5 已由既有 validator 实现 | Gate 作为统一编号 + issue 契约，显式声明实现来源 |

---

## 9. Migration risks（Top 6）

| 风险 | 现状概率 / 影响 | 缓解 |
| --- | --- | --- |
| Historical data leakage | **H / H（已发生）** | 路径参数化（V4-01）+ ExportPlan.excluded + DeliveryValidator blocker（V4-07） |
| Export contamination | **H / H（已发生 NR-002/3/4）** | 唯一 ExportService + 内部字段与正文分离 + 文本扫描测试 |
| Writer overwrite | M / H | append-only revision + AI 结果默认 proposed（V4-06） |
| Revision race / Agent duplicate writes | M–H / H | `expected_revision` + `idempotency_key`（V4-06 / V4-08） |
| Big Bang Rewrite | M / H | Strangler + Adapter-first + 每阶段可回滚（V4-01…V4-10） |
| Over-abstraction | **H / M** | §3.2「暂时不建」清单 + 每层必须有真实消费者 |

完整 18 条见 `V4_ARCHITECTURE_RISKS.md`。

---

## 10. V4-01 recommended scope

```text
V4-01 Core Cleanup（不改任何生成结果）
  1. 建立 application/services 骨架，把路由编排搬进 service（行为不变）
  2. journey_service 收编 _journey_projection；ui_flow 改为消费它
  3. persistence/paths.py：路径常量唯一来源；canon 路径按 novel_id 参数化
  4. core/revision.py：统一 revision / expected_revision 语义
  5. legacy/ 命名空间建立（只移动 import 归属，不改语义）

验收：
  · full pytest PASS（默认套件）+ historical_acceptance 仍可运行
  · validate_project PASS + frozen guard PASS + release tag 未移动
  · 同一作品在 Landing / Command Center / guided-flow 显示同一 stage + progress
  · 非 wasteland_001 作品导出不再混入历史数据（新增测试）
  · production state before == after
```

**V4-01 不应包含**：LLM 接入、Memory、Quality 循环、MCP、插件、UI 重构
（这些分别在 V4-02 / V4-03 / V4-05 / V4-08 / V4-09 / V4-10）。

---

## 11. Files created

```text
docs/v4/V4_CODEBASE_INVENTORY.md
docs/v4/V4_MODULE_CLASSIFICATION.md
docs/v4/V4_ARCHITECTURE.md
docs/v4/V4_LLM_CONTRACT.md
docs/v4/V4_MCP_SPEC.md
docs/v4/V4_PLUGIN_SPEC.md
docs/v4/V4_QUALITY_CONTRACT.md
docs/v4/V4_MEMORY_ARCHITECTURE.md
docs/v4/V4_EXPORT_SPEC.md
docs/v4/V4_MIGRATION_PLAN.md
docs/v4/V4_DELETION_PLAN.md
docs/v4/V4_ARCHITECTURE_RISKS.md
docs/v4/V4_00_ARCHITECTURE_REPORT.md
docs/v4/adr/README.md
docs/v4/adr/ADR-001-canonical-service-layer.md
docs/v4/adr/ADR-002-llm-gateway-boundary.md
docs/v4/adr/ADR-003-canonical-writer-store.md
docs/v4/adr/ADR-004-journey-projection.md
docs/v4/adr/ADR-005-quality-contract.md
docs/v4/adr/ADR-006-revision-model.md
docs/v4/adr/ADR-007-artifact-ownership.md
docs/v4/adr/ADR-008-mcp-as-interface.md
docs/v4/adr/ADR-009-plugin-db-isolation.md
docs/v4/adr/ADR-010-structured-generation.md
```

## 12. Files modified

```text
无业务代码文件被修改。
唯一非 docs/v4 的改动 = 把已有的未跟踪规划稿 docs/NOVELFORGE_V4_MASTER_PLAN.md 纳入本次提交
（它是本阶段 CHALLENGE 分析的输入）。
```

---

## 13. Architecture Review Checklist（§27）

```text
[x] 是否扫描完整 repository                    → §1（含 scripts / tests / config / data / ui）
[x] 是否找到所有主要 generation 路径           → creative / settings_gen / outline_forge / journey /
                                                 writer / planning.chapter_compiler / spec
[x] 是否找到所有 Writer stores                 → canonical + legacy 只读；novel/final 无 owner
[x] 是否找到所有 Export 路径                   → export_package / outlines / outline_revision.docx_bytes /
                                                 writer_export_bundle
[x] 是否找到所有 progress / journey 逻辑       → _journey_projection（唯一）+ ui_flow 第二套
[x] 是否检查 legacy data 自动加载              → workspace 证据 / novel/final / writer_v1 / frozen manifest
[x] 是否检查 UI business logic                 → 结论：viewmodel 仅展示层；重复 DTO 与重复流程存在
[x] 是否检查 persistence ownership             → §4 五类存储 + §4.5 无 owner 数据
[x] 是否标记 creative hardcoding               → 5 个模块 + 具体符号 + 行号
[x] 是否有明确 module dependency rule          → §4.2 依赖矩阵 + §4.3 明文禁令
[x] 是否定义 canonical state ownership         → §6
[x] 是否定义 revision boundary                 → §7 + ADR-006
[x] 是否定义 LLM boundary                      → V4_LLM_CONTRACT.md + ADR-002
[x] 是否定义 MCP boundary                      → V4_MCP_SPEC.md + ADR-008
[x] 是否定义 Plugin boundary                   → V4_PLUGIN_SPEC.md + ADR-009
[x] 是否定义 Quality boundary                  → V4_QUALITY_CONTRACT.md + ADR-005
[x] 是否定义 Memory boundary                   → V4_MEMORY_ARCHITECTURE.md + CHALLENGE-02
[x] 是否定义 Export ownership                  → V4_EXPORT_SPEC.md + ADR-007
[x] 是否形成 Migration Plan                    → V4_MIGRATION_PLAN.md（含 4 个 BLOCKER）
[x] 是否形成 Deletion Plan                     → V4_DELETION_PLAN.md（含「明确不删除」与 8 条 debt）
[x] 是否列出 UNKNOWN                           → V4_CODEBASE_INVENTORY.md §6
```

---

## 14. BLOCKED 检查

```text
V4-00 = PASS

原因：12 份正式文档 + 10 份 ADR 全部产出；所有重大结论都有文件 / 符号级证据；
      业务代码 0 改动；frozen boundary 未触碰；release tag 未移动；
      默认测试套件基线 green（892 passed）。

前置未决项（不阻塞 V4-00，但阻塞后续阶段的开工）：
  BLOCKER-01  novel/final/** 归属（作者决定）        → 阻塞 V4-06 / V4-07
  BLOCKER-02  novel/runs | state | pipelines | learning 与产品关系（作者决定） → 影响仓库卫生
  BLOCKER-03  historical 570 章是否作为一等作品     → 影响 V4-01 ownership 设计
  BLOCKER-04  是否长期支持多作品                    → 影响 V4-01…V4-07 的彻底程度
```
