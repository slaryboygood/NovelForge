# NovelForge V4 — Migration Plan（设计稿）

> 状态：**V4-00 Architecture / Proposed**，已按 **V4-01 作者决策**对齐（2026-09-17）
> 铁律：**V3 → V4 不做 Big Bang Rewrite。**
> 每个阶段都必须满足：外部行为可验证、旧数据仍可读、随时可回滚、frozen boundary 不动。

### 0.1 V4-01 作者决策（覆盖本文件以下相关段落）

```text
Decision A  novel/final/*.md        → DELETE（不迁移 / 不归档 / 不导入）
Decision B  570 章 historical 数据  → DELETE（不导入 / 不做 fixture / 不进 legacy/）
Decision C  canonical creative artifact = StoryBlueprint；Writer → Blueprint Editor
```

| 位置 | V4-00 原计划 | V4-01 修正 |
| --- | --- | --- |
| §2「Writer（正文）」行 | 建立 `ChapterRevision` 正文链，导入 `novel/final` | **删除正文资产**；Blueprint Editor 取代 Writer；正文 draft 仅兼容预览 |
| §3 V4-06 Writer | 正文编辑 / 保存 / diff / restore | **Blueprint Editor / Story Studio**（结构节点编辑） |
| §4.1 Writer 专项 | W1–W5 正文 revision 步骤 | 作废；改由 `docs/v4/V4_MODULE_BOUNDARIES.md` 的 Blueprint 服务承担 |
| §6 BLOCKER-01 / 03 | 待作者裁定 `novel/final` 与 historical 归属 | **已裁定并执行删除**（V4-01） |
| §6 BLOCKER-02 / 04 | `novel/runs` 等与多作品支持 | 仍未定（不阻塞 V4-01，见 BLOCKER 表） |

---

## 1. 迁移原则

```text
1. Strangler（绞杀式）：新 service 逐步接管旧调用点，旧实现保留到移除点
2. Adapter-first：先加适配器让新旧共存，再删除旧路径（不先删再补）
3. 数据不动：V3 数据格式在 V4 全程可读；只有显式迁移阶段才产生新副本
4. 单点切换：每个对象的 ownership 只能在一个阶段内切换，避免两处同时写
5. 每阶段可回滚：回滚 = 切回旧调用点（数据未迁移时零成本）
6. frozen 不动：Canon / StoryState 基线 / 570 章 IR / Repair Contract / Gate / release tag
7. 每个阶段产出 acceptance 证据（pytest + validate_project + 必要时浏览器）
```

---

## 2. 总览：current state → target state

| 对象 | Current State（V3） | Target State（V4） | Adapter | Compatibility Period | Rollback | Removal Point |
| --- | --- | --- | --- | --- | --- | --- |
| **Service 层** | `api/story_builder_routes.py`（1,545 行内联编排） | `application/services/*` 薄路由 | 路由内保留旧实现，逐步改为调用 service | V4-01 → V4-10 | 路由 revert 到内联实现 | 最后一个 UI 调用点迁移后 |
| **Writer / Blueprint Editor** | 无正文 owner；`writer/<novel>/drafts/*.json` 是 preview；`novel/final/*.md` 已于 V4-01 删除 | **Blueprint Editor**：结构节点 edit / revision / diff / restore（正文非核心） | 旧 draft 保留为只读 preview 视图（不迁移） | V4-06 → V4-10 | 关闭 Blueprint Editor，回到只读投影 | bridge 面板删除时 |
| **Export** | 4 条拼装路径 + 3 个硬编码单作品路径 | 唯一 `ExportService` + `DeliveryValidator` + nfpack | `export_package.export_package()` 保留为薄 wrapper 调用新 service | V4-07 → V4-10 | wrapper 回退到旧实现 | 验收通过后（LATE） |
| **Project / Novel 数据** | `novel_id` 与 `project_id` 双名同值；profile / pack / state / canon 各自路径 | 单一 `project_id` → `novel_id` 层级 + `persistence/paths.py` 统一 | 读取时按 novel_id 推导 project_id（同值映射） | V4-01 起 | 保留旧字段名读取兼容 | 所有 artifact 带 project_id 后 |
| **Historical works（570 章 IR / M11 证据）** | 散落在 `story_engine/*.py` 顶层 + `workspace/wasteland_001_exports/**` | `legacy/` 命名空间，只读；导出默认排除 | `legacy` 包提供只读 API（原 API 签名不变） | 全程 | 直接 revert import 路径 | 永不删除（frozen） |
| **Generation pipeline** | 5 个硬编码创作模块（creative / settings_gen / outline_forge / journey / recommendations） | `generation/*` 经 `ai/gateway` 产出既有模型 | 旧函数保留签名，内部改为调用新生成器（feature flag 切换） | V4-03 → V4-04 | flag 关闭即回到确定性路径 | 新生成器通过质量门 + 浏览器验收后 |
| **Blueprint 生成（V4-04）** | 无（V3 只有规则式大纲） | `blueprint` 节点图 + `generation` 逐级生成（premise→…→scene→links） | `BlueprintRepository` 独立于 V3 大纲；四处 legacy structured provider 经 Gateway 桥 | V4-04 起与 V3 路径并行 | 删除 blueprint 目录即回到 V3（Blueprint 不写 Canon） | V4-05/V4-06 消费后由作者决定 V3 生成器去留 |
| **Progress / Journey** | `v3_projection._journey_projection()`（V3）+ `ui_flow.py`（第二套 stage/next-step） | `application/services/journey_service`（唯一投影） | `ui_flow` 改为调用 journey_service 取 stage/next step | V4-01 | 恢复 `ui_flow` 自算 | `ui_flow` 第二套公式删除时 |
| **LLM 调用** | `spec/llm.py` 直接 HTTP；三处鸭子类型 provider | `ai/gateway` + provider adapter | `LLMSpecProposalProvider` 保留类名，内部委托 gateway | V4-02 | 恢复直连实现 | provider adapter 单测完备后 |
| **Quality** | 9 处独立 validator / finding 形态 | 统一 `QualityIssue` + Q0–Q9 + Repair 循环 | 各 validator 加 adapter 输出 QualityIssue | V4-05 | 关闭 QualityService 编排，保留原 validator | repair 循环上线并验收后 |
| **UI** | V3 工作台 + 19 页签 legacy bridge | 稳定后端上的新界面 | bridge 继续存在直到同等能力可用 | V4-09 → V4-10 | 保留 bridge | bridge 功能被新 UI 覆盖 + 验收后（LATE） |

---

## 3. 阶段计划

### V4-01 Core Cleanup（Foundation）

```text
目标：让「一个业务入口 + 一个状态投影 + 一个所有权模型」成立，不改变任何生成结果。

动作：
  1. 建立 application/services 骨架，把路由里的编排搬进 service（先不改逻辑）
  2. journey_service 收编 _journey_projection；ui_flow 改为消费它
  3. persistence/paths.py：所有路径常量唯一来源；canon 路径按 novel_id 参数化
  4. core/revision.py：统一 revision / expected_revision 语义（先用于 writer 与 outline）
  5. legacy/ 命名空间建立（只移动 frozen 模块的 import 归属，不改语义）

验收：
  - pytest 全绿（892 + historical 仍可显式运行）
  - validate_project PASS
  - 同一 novel 在 Landing / Command Center / API 得到同一 stage + progress
  - 非 wasteland_001 作品导出不再混入历史数据（新增测试）
  - production state before == after
```

### V4-02 LLM Gateway

```text
动作：ai/gateway + contracts + router + policy + usage + trace + cache；
      收编 spec/llm.py 为 providers/deepseek.py；业务模块不再持有 prompt。
兼容：SPEC provider 类名与签名保留（内部委托 gateway）。
验收：见 V4_LLM_CONTRACT.md §12。无 key 时行为与 V3 一致（可读错误 + 无半成品）。
```

### V4-03 Memory

```text
动作：memory/{store,retrieval,context_builder,episodic,semantic,preferences}；
      先把 story_engine/memory.py 改名 domain/knowledge.py（消除命名冲突）。
兼容：WriterContextBuilder 的 6 层 block 语义保留，逐步改为调用 context_builder。
验收：见 V4_MEMORY_ARCHITECTURE.md §9（含「删除 memory 层不丢事实」）。
```

### V4-04 Structured Generation

```text
动作：generation/* 经 gateway 产出既有模型（ContentPack / ChapterIR / PlanningIR / OutlinePackage）；
      先做 NF-003：章节标题与字段标签不再由模板兜底。
兼容：feature flag；关闭时回到 V3 确定性路径。
验收：生成结果 100% 通过既有 validator；NF-003 缺陷在验收样本中消失。
```

### V4-05 Quality Loop

```text
动作：quality/{contracts,service,gates,repair}；既有 validator 注册进 Q0–Q9。
兼容：旧 findings 形态保留（adapter）。
验收：见 V4_QUALITY_CONTRACT.md §9。
```

### V4-06 Blueprint Editor & Revision Workflow（已按 V4-01 决策 C 重定义）

```text
V4-00 原计划：ChapterRevision 模型 + writer_store（canonical），服务于"正文 revision"。
V4-01 决策 C 覆盖：canonical creative artifact = StoryBlueprint；正文不属 V4 Core。

V4-06 实际交付（docs/v4/V4_EDITOR_CONTRACT.md）：
  动作：novelforge.editor（patch / diff / history / rewrite / accept / reject /
        restore / undo / move / audit）+ application.services.EditorService
        （组合 editor + quality + generation）+ 最小 REST（/api/story-builder/editor/**）
  数据：Blueprint 节点的 append-only revision（BlueprintRepository 仍是唯一 truth）；
        editor 只额外保存 operation / review metadata（novel/authoring/story_engine/editor/**）
  兼容：WriterDraftService / writer 路由保持只读兼容（正文能力），不作为 Editor 底层
  验收：任何编辑产生新 revision；AI 改写只改 target fields；accepted 不被静默覆盖；
        冲突不覆盖、不自动 merge；删除 quality / editor metadata 不影响 Blueprint truth
```

### V4-07 Delivery / Export

```text
动作：ExportService + ExportPlan + DeliveryValidator(Q9) + nfpack；移除跨作品分区。
兼容：export_package.export_package() 变为 wrapper（返回结构保持向后兼容一段时间）。
验收：见 V4_EXPORT_SPEC.md §8（特别是「无其他 novel 数据」与「无内部字段」）。
```

### V4-08 MCP / V4-09 Plugins / V4-10 UI

```text
MCP      ：tool 实现 ≤ 3 行；与 REST 同 service；见 V4_MCP_SPEC.md §10
Plugins  ：3 类最小集合；见 V4_PLUGIN_SPEC.md §9
UI       ：按稳定 service 重构；legacy bridge 保留到功能对齐
```

---

## 4. 专项迁移设计

### 4.1 Writer / Blueprint Editor（V4-01 已重定义）

> ### ⚠️ V4-01 决策：本节原「正文 revision 迁移」方案作废
>
> 作者判定 `novel/final/**` 与 570 章 historical 为废弃资产并直接删除；
> **V4 不建立 canonical prose writer store**，正文 draft 不再是核心 artifact。
> 取而代之的目标：
>
> ```text
> StoryBlueprint = canonical creative artifact（Premise / Characters / Arcs /
>                  Chapter Cards / Scene Cards / Causal Graph / Setup-Payoff / Revision）
> Writer         → Blueprint Editor / Story Studio（结构节点编辑器）
> 正文生成        → Plugin / 下游 Agent（非 V4 Core）
> ```
>
> 仍然继承的实现原则：唯一写入点、append-only revision、AI 产出默认 `proposed`、
> 作者 accept 后才 canonical、旧存储只读不迁移。
>
> 细节见 `adr/ADR-011`、`docs/v4/V4_MODULE_BOUNDARIES.md` §3.2。

以下为 V4-00 原文（仅作记录）：

**问题**：V3 里「正文」不存在。`writer/<novel>/drafts/*.json` 是 preview，
`novel/final/*.md` 是无主手稿，`novel/source_text/` 为空。

**迁移步骤**：

```text
W1  定义 ChapterRevision：
       chapter_id, revision, text, status(proposed|accepted|published),
       source_ids, author_accepted_at, model_usage_ref, parent_revision
    location: novel/authoring/<novel_id>/writer/<chapter_id>/r%06d.json
    （沿用 writer 目录族，避免第三套存储；legacy writer_v1 保持只读）

W2  canonical writer store 单点：写入与读取共用 repository（沿用 V3 已做到的单一常量做法）

W3  旧 artifacts 只读导入视图：
      drafts/*.json  → 显示为 "draft（未修订）" 只读条目
      不迁移、不重写、不重复计数（沿用 V3 legacy 规则）

W4  AI 修订通道：
      AI 产出 revision(status=proposed) → 作者 accept → status=accepted
      禁止 in-place 修改（append-only）

W5  novel/final/**：**必须由作者决定**（见 §6 BLOCKER-01）
```

**回滚**：关闭 writer service，UI 回到 draft-only 列表（V3 行为）。

### 4.2 Export

```text
E1  ExportPlan 先上线（只读、无副作用）→ 让 author 看到「会导出什么 / 排除了什么」
E2  新 ExportService 接管一个格式（JSON，风险最低）
E3  再接管 Markdown / DOCX（同步删除内部字段）
E4  最后接管 UI / MCP 调用点；旧 wrapper 保留一个版本
E5  nfpack（新能力，无兼容负担）
```

### 4.3 Project data

```text
P1  只读兼容期：读取时同时接受 novel_id / project_id（同值），并在 metadata 中记录来源
P2  新写入统一使用单一命名（建议：project 为根，novel 为其下作品实体）
P3  旧 artifact 不重写；通过 adapter 在读取时补齐字段
P4  当所有写入点统一后，移除双名兼容
```

> 现状证据：`sessions.py` / `models.py` 用 `project_id`，`profile.py` / `canon` / `writer` 用 `novel_id`；
V3 通过同值约定工作（`resolve_creator_context` 用 novel_id 去匹配 session.project_id）。

### 4.4 Historical works

```text
H1  legacy/ 命名空间建立；原模块签名不变（只是 import 路径改变）
H2  冻结守卫扩展：legacy 模块不得被新写路径 import（源码守卫测试）
H3  历史证据路径（workspace/wasteland_001_exports/**）只在 legacy 导出中出现
H4  永不删除；永不 promote；永不与当前创作的质量/修复流程混合
```

### 4.5 Generation pipeline

```text
G1  gateway 就位后，逐模块迁移（一次一个，feature flag）
      顺序建议：outline（NF-003 收益最大）→ settings → premise → journey → draft
G2  每个模块迁移后必须通过：既有 schema gate + 质量门 + 浏览器验收
G3  迁移完成的模块删除硬编码文案表（删除点见 V4_DELETION_PLAN.md）
G4  未迁移模块保持 V3 行为（AI_UNAVAILABLE 路径），不得半迁移
```

### 4.6 Progress / Journey

```text
J1  journey_service 成为唯一投影（Landing / Command Center / API / MCP）
J2  ui_flow 的 stage / next-step 改为委托调用（不改变返回值形状）
J3  删除 ui_flow 里的第二套公式（removal point = J2 验收通过）
J4  新增性能预算：作品数 N 时列表投影成本必须线性可控（V3 已知问题：53 本 1.8s）
```

---

## 5. 兼容期与移除点汇总

| 兼容对象 | 兼容期 | 移除条件 |
| --- | --- | --- |
| `legacy_writer_v1`（`workspace/wasteland_001_exports/writer_v1`） | 全程 | 永不（只读；除非作者确认无数据） |
| `adventures`（rules 1/2） | 全程 → LATE | 旧存档无引用 + 作者确认 |
| `ui/src/api.ts` 双份 DTO | V4-09 → LATE | legacy bridge 面板被新 UI 覆盖 |
| `ui_flow` 第二套 stage 公式 | V4-01 起 | journey_service 验收通过 |
| `export_package.export_package()` wrapper | V4-07 起 | 所有调用点迁移 + 一个版本稳定 |
| 5 个硬编码创作模块的文案表 | 各自迁移后 | 新生成器通过质量门 + 验收 |
| `novel_id` / `project_id` 双名 | V4-01 起 | 所有写入点统一 |

---

## 6. BLOCKERS（必须由作者决定，不能自行假设）

| ID | 阻塞点 | 为什么必须作者决定 | 影响范围 |
| --- | --- | --- | --- |
| **~~BLOCKER-01~~（已解除）** | `novel/final/**` 的归属 | **作者已裁定：DELETE（不迁移 / 不归档 / 不导入）** | V4-01 已执行；V4-06 不再建正文 revision 链 |
| **BLOCKER-02** | `novel/runs/**`（1,108 文件）、`novel/state/**`（278）、`novel/pipelines/**`（12）、`novel/learning/**`（6）与产品的关系 | 可能是外部写作流程产物，删除或忽略都可能丢失作者工作 | 仓库卫生、V4-10 UI（是否展示） |
| **~~BLOCKER-03~~（已解除）** | Historical 570 章（wasteland_001）是否进入 V4 | **作者已裁定：DELETE（不导入 / 不做 fixture / 不进 legacy）** | V4-01 已执行删除 + 移除产品侧引用 |
| **BLOCKER-04** | 是否保留「wasteland_001 之外的第二部作品」的长期支持目标 | 决定 ownership 参数化的彻底程度（单作品 vs 多作品平台） | V4-01…V4-07 全部 |

> 除上述 4 项外，本轮审计没有发现必须停下来等作者的问题。
> 其余工作（service 拆分、gateway、quality 契约、export 收敛）都可以在作者不介入的情况下推进。

---

## 7. 每阶段统一 acceptance 模板

```text
[ ] targeted tests PASS
[ ] full pytest PASS（默认套件）
[ ] historical_acceptance 仍可显式运行（不因迁移而失效）
[ ] scripts/validate_project.py PASS
[ ] production state before == after（除非该阶段声明预期 mutation）
[ ] frozen truth / contract / gate 未变化（V2 Frozen Guard PASS）
[ ] release tag 未移动
[ ] 文档同步（README / ARCHITECTURE / DATA_MODEL / CHANGELOG 对应章节）
[ ] 涉及 UI → 真实浏览器验证（1440 / 1280 / 1024 / 390）
[ ] 涉及生成 → 质量门报告（Q0–Q9 结果）
```

---

## 8. 风险登记

本文件的迁移风险详细评估见 `V4_ARCHITECTURE_RISKS.md`；其中与迁移直接相关的关键项：

```text
Big Bang Rewrite          → 由 §1 原则 + §3 阶段拆分防止
Writer overwrite          → 由 §4.1 append-only revision 防止
Export contamination      → 由 §4.2 ExportPlan(excluded) 防止
Canon drift               → 由 gateway + quality 双层门禁防止
Historical data leakage   → 由 §4.4 legacy 隔离 + ownership 校验防止
Schema version drift      → 由 §5 兼容期表 + revision 统一防止
```
