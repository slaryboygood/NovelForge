# NovelForge Acceptance Repair Report

> 分支：`codex/product-v3-game-ui`
> 修复对象：`docs/CURRENT_PRODUCT_ACCEPTANCE_REVIEW.md`（独立验收，结论 **FAIL**）
> 修复日期：2026-09-17
> 本分支不修改产品版本号、不移动任何 release tag / release commit。

## 1. Original Verdict

**FAIL**

独立验收判定：V3.0 的界面与基础流程可用，但**核心交付闭环没有跑通**——

1. 导出工作区主 CTA 跳到一个不存在的 legacy 页签，页面空白（NF-001）；
2. 写作草稿没有 UI 入口，且写入路径与投影读取路径不一致，进度天花板 51%（NF-002）；
3. 锻造出的章节大纲 22–24 / 30 章标题是字段标签占位，并把内部 id 写进作者可见内容
   （NF-003 / NF-004）；
4. Landing 与 Command Center 对同一本书给出不同阶段 / 进度 / 下一步（NF-005）。

## 2. Repair Scope

本轮处理验收报告中的**全部 20 条 Issue**（NF-001 … NF-020），按报告第 15 节的依赖顺序执行：

```text
NF-002（写作草稿 SSOT）→ NF-001（导出能力进入 V3）→ NF-020（门禁收紧）
  → NF-003 / NF-004 / NF-006（生成内容 canonical 化）
  → NF-005（stage / progress 单一来源）
  → NF-007（模型能力与文档对齐）
  → NF-009 / NF-008（Creation / Simulation 主路径可用）
  → NF-010 / NF-011 / NF-012 / NF-013 / NF-014 / NF-015 / NF-016 / NF-017
  → NF-018 / NF-019（工程文档）
```

不在本轮范围：新增产品功能、重排 roadmap、修改任何 frozen boundary
（Canon / StoryState / legacy 源 / Repair Contract / Gate / truth precedence / approval boundary）。

## 3. Issue Status

| Issue | 严重度 | 状态 |
| --- | --- | --- |
| NF-001 导出主 CTA 落到不存在的 legacy 页签，页面空白 | P1 | RESOLVED |
| NF-002 写作草稿读写路径不一致 + 无 UI 入口，最后一步目标不可达 | P1 | RESOLVED |
| NF-003 章节标题用内部字段标签占位（22–24 / 30 同名） | P2 | RESOLVED |
| NF-004 内部 id / 机械拼装文本泄漏到界面与导出 | P2 | RESOLVED |
| NF-005 Landing 与 Command Center 阶段 / 进度 / 下一步不一致 | P2 | RESOLVED |
| NF-006 内容包标题被截断 +「（设定草稿）」 | P2 | RESOLVED |
| NF-007 模型能力未接线但文档承诺可用 | P2 | RESOLVED（明确降级承诺，见 §5） |
| NF-008 资源耗尽后主 CTA 仍推同一 422 行动 | P2 | RESOLVED |
| NF-009「确定这个方向」不推进向导 | P2 | RESOLVED |
| NF-010 创意草稿不落盘、无未保存提示 | P3 | RESOLVED |
| NF-011 作品无法重命名 / 删除 | P3 | RESOLVED（删除＝整体归档，可恢复） |
| NF-012 导出文案自相矛盾（「还差 0 步」） | P3 | RESOLVED |
| NF-013「控制方 控制方未知」 | P3 | RESOLVED |
| NF-014 高级工具显示裸 tab key | P3 | RESOLVED |
| NF-015 行动名被截断成「向身边人...」 | P3 | RESOLVED |
| NF-016 角色 / 地点 / 势力只有原型名 | P3 | RESOLVED（显式占位标注，见 §9） |
| NF-017「已解锁：解锁：」「来源：来源：」 | P4 | RESOLVED |
| NF-018 README 的 tsc 命令不执行类型检查 | P4 | RESOLVED |
| NF-019 npm audit（vite / esbuild）dev-only advisory | P4 | RESOLVED（文档说明，升级留版本计划） |
| NF-020 浏览器门禁盲区 | P3 | RESOLVED（新增 P7 + 收紧 P5 / P6） |

## 4. Root Cause and Fix

### NF-001

**Original Problem** 导出工作区主 CTA「生成导出包」跳 `#/story-builder?...&tab=export`，
而 `CreatorTab` / `TAB_GROUPS` 里没有 `export`，页面只剩外壳与页签导航。

**Root Cause** CTA 指向一个**不存在的能力**：V3 文案承诺「既有导出面板」，但仓库里
从来没有这个面板；`labelOfTab()` 对未知 key 直接返回原始 key，渲染层没有匹配分支，
于是渲染空内容（不是崩溃，而是静默空壳）。

**Files Changed** `ui/src/v3/WorkspaceView.tsx`、`ui/src/v3/ExportFlow.tsx`（新增）、
`ui/src/v3/api.ts`、`ui/src/v3/v3.css`、`ui/src/v3/export-flow.css`（新增）、
`ui/src/guidedFlow.ts`、`ui/src/StoryBuilderPage.tsx`

**Implementation** 选择报告的方案 A：**在 V3 工作区内正式实现导出能力**（不新建导出子系统，
只消费既有 `GET /api/story-builder/export/package`）：

* 导出格式选择（Markdown / JSON / Word）+「生成导出包」→ 真实 `export_id` / 文件名 /
  内容预览 / 下载入口（Blob 下载，docx 走 base64）；
* 导出工作区只有一个 Primary CTA，且它随真实状态变化（就绪 → 生成；只差草稿 → 建草稿；
  有缺失 → 跳到缺的那一步；有 blocker → 说明阻塞）；
* 去掉「真正的导出包在既有导出面板」这句不存在的承诺；
* 未知 legacy 页签不再渲染空壳（回落默认面板 + `labelOfTab` 返回「未知工具」）。

**Tests Added** `tests/browser_v3_p7_acceptance.cjs`（导出 CTA 之后内容非空 / 产物存在 /
下载入口存在）、`tests/browser_v3_p5_acceptance.cjs`（导出产物断言）。

**Manual Verification** P5 / P7 门禁 + 修复前后对比探针（§6）。

**Acceptance Criteria Result** 通过：点击主 CTA 后页面渲染真实导出面板与产物；
`labelOfTab('export')` 不再返回英文 key；门禁断言「导出 CTA 之后内容区非空」。

**Status** RESOLVED

### NF-002

**Original Problem** UI 无写作草稿入口；API 创建草稿成功（201）但 V3 投影
`facts.writer_drafts` 恒为 0，导出阶段永远 0/1，总体进度停在 51%。

**Root Cause** 同一个语义对象存在两个目录来源：写入在
`workspace/wasteland_001_exports/writer_v1/<novel>/`（`writer_integration.WRITER_DIR`），
读取在 `novel/authoring/writer/<novel_id>/index.json`（`v3_projection._writer_drafts`）；
而且写入方从来没有生成过 `index.json`，读取方却只认 index。

**Files Changed** `src/novelforge/story_builder/writer_integration.py`、
`src/novelforge/story_builder/v3_projection.py`、`ui/src/v3/ExportFlow.tsx`

**Implementation** 建立**唯一 canonical writer store**（§5）：

```text
canonical  : novel/authoring/story_engine/writer/<novel_id>/index.json + drafts/*.json
legacy     : workspace/wasteland_001_exports/writer_v1/<novel_id>/  （只读兼容，
             仅当 canonical 完全没有草稿时读取，避免同一份草稿被计两次）
```

`WriterDraftService` 写入草稿后立即维护 `index.json`；`v3_projection` 与导出通过
`read_writer_drafts()` 读同一个函数；`WRITER_DIR` 成为两侧共用的同一常量。
导出就绪度新增「已有写作草稿」步骤，UI 在导出工作区提供「创建写作草稿」入口。
在 UI 里创建草稿后：投影 `writer_drafts = 1`、导出阶段 1/1、总体进度上升、
刷新与重启后仍然存在。

**Tests Added** `tests/test_acceptance_repair_regressions.py::
test_writer_draft_store_is_the_projection_source` / `..._completes_the_export_stage` /
`..._share_writer_dir` / `test_writer_legacy_directory_is_read_only_compatible`；
P7 门禁的 Writer Gate。

**Acceptance Criteria Result** 通过：service 写入路径 == 投影读取路径（同源常量）。

**Status** RESOLVED

### NF-003

**Original Problem** 30 章里 22–24 章标题是「阶段目标（规划）」「长期方向（规划）」，
已发生章节之间也大量同名（`先观察，不急着介入` ×3、`世界表层规则的分配方式被单方面调整` ×2）。

**Root Cause** 两处生成逻辑把**字段标签当内容**：

* `settings_gen` 的主线候选 label 直接写成 `future_plan.stages[].title`（「阶段目标」/「长期方向」）；
* `outline_forge._planned_chapters` 用 `f"第N章：{stage.title}（规划）"` 给所有规划章节命名，
  阶段只有 1–2 个时必然大面积同名。

**Files Changed** `src/novelforge/story_engine/outline_forge.py`、
`src/novelforge/story_engine/settings_gen.py`

**Implementation**

* 主线候选改成**内容性**阶段名（例如「查清{核心短语}」「在{势力}中立足」）；
* 新增 `ChapterTitleLedger`：一本书一个分配器，**同一标题正文只能出现一次**；
  规划章节标题 = 该章真实素材（要推进的支线 / 要埋设的伏笔 / 人物目标 / 阶段目标）
  + 这一章承担的叙事功能（试探 / 布局 / 交涉 / 受阻 / 代价 / 转机 / 决断 / 收束），
  素材用尽时才使用「（第 N 次）」这类仍然表达语义的序数；
* 已发生章节标题优先用行动 / 事件名，重复时用本章真实变化（代价、转折、信息释放）区分；
* 新增质量门禁：`CHAPTER_TITLE_PLACEHOLDER`（字段标签 / 模板后缀）、
  `CHAPTER_TITLE_DUPLICATE`（正文重名），进入 `assess_forge_plan` 的 findings。

**Tests Added** `tests/test_acceptance_repair_regressions.py::
test_chapter_titles_are_unique_and_content_bearing`（两题材 × 30 章）、P7 / P6 门禁。

**Acceptance Criteria Result** 通过：两本不同题材作品各 30 章，标题正文唯一、
无字段标签占位（见 §7 Generation QA）。

**Status** RESOLVED

### NF-004

**Original Problem** `start_place`（大纲工作区）、`ev_world_shift` / `来源：来源：` /
`favors 消耗 1`（导出 markdown）、`future_plan:main_…`（章纲）、`protagonist` / `favors`
（推演错误提示）出现在作者可见内容里。

**Root Cause** 缺一层统一的「内部标识 → 作者语言」映射：部分位置翻译（候选卡把
`favors` 写成「人情 ×1」），部分位置原样透出；`must_keep` 把（机器用）来源 id 写成了
作者文本；错误文案由引擎直接拼装资源键。

**Files Changed** `src/novelforge/author_language.py`（新增）、
`src/novelforge/story_builder/v3_projection.py`、`src/novelforge/story_engine/outline_forge.py`、
`src/novelforge/story_engine/outline_revision.py`、`src/novelforge/story_engine/narrative.py`、
`src/novelforge/story_builder/models.py`、`src/novelforge/story_builder/export_package.py`、
`src/novelforge/api/story_builder_routes.py`

**Implementation**

* 新增唯一映射层 `novelforge/author_language.py`（角色 / 地点 / 支线 / 伏笔 / 资源 /
  关系维度 / 知识线索 / 身份 / 行动类别 / 条件 op），引擎生成文案、V3 投影、导出与 API
  错误文案全部走它（`label_table()` + `translate()`）；
* 章纲效果行（信息 / 关系 / 成长 / 支线 / 伏笔 / 代价）在**生成时**就翻译成作者语言，
  翻不出来时退化为可读描述，不回落原始 id；
* 机器可追溯来源移到结构化字段 `OutlineItem.source_ids`（`must_keep` 只保留作者可读说明），
  `verify_outline_sources` / `_item_kind` 优先读结构化来源，旧包继续按文本特征兼容；
* 章节 `location` / `time` 在投影里统一翻译（`第 N 回合`）；
* `participants` 在领域存储里保持角色 id（写作与校验需要），导出时翻成角色名；
* 推演失败文案在 API 边界翻译（`author_message()`），因此 legacy UI 与 V3 UI 都拿到作者语言。
* 导出包（markdown / docx）的 `truth_layer` 与 section 来源改成作者语言
  （原先是 `occurred` / `NovelProfile + ContentPack` / `canon/wasteland_001.sqlite`），
  机器可读来源保留在 JSON manifest。

**Tests Added** `tests/test_acceptance_repair_regressions.py::
test_outline_exports_have_no_internal_ids` / `test_v3_projection_chapters_speak_author_language`；
P6（锻造后扫描）/ P7（8 工作区 + 2 种导出格式）门禁。

**Acceptance Criteria Result** 通过：`已锻造 30 章 + 已推演 + 已写作草稿` 状态下，
8 个工作区、markdown / json 导出的**作者可见内容**内部 id 命中数为 0（§7）。

**Status** RESOLVED

### NF-005

**Original Problem** `qa_rich_novel` Landing 卡片显示「大纲 · 81% · 继续生成章节大纲」，
作品内 Command Center 显示「导出 · 51% · 导出并开始写作」。

**Root Cause** `novel_card()` / `_light_stage()` 是第二套 stage / progress 计算
（自定分母 `steps = 4 + 9 + 3`，且一旦有 book 就把下一步硬编码为「继续生成章节大纲」）。

**Files Changed** `src/novelforge/story_builder/v3_projection.py`

**Implementation** 抽出唯一计算入口 `_journey_projection()`（加载 profile / brief / seed /
pack / check / runtime / outline / repair / drafts → objectives → stages → progress →
next action → risks）。`command_center()` 在它之上补充实体级投影；`novel_card()`
**只裁剪**它的结果（阶段 / 阶段名 / 进度 / 下一步 / 下一步动作），`_light_stage()` 删除。
卡片刻意不包含 simulation / 实体渲染等重活，保留列表页性能边界。

**Tests Added** `tests/test_v3_ui_projection.py::test_landing_cards_are_derived_from_real_profiles`
（改为强制与 Command Center 同源）、`tests/test_acceptance_repair_regressions.py::
test_landing_card_matches_command_center_in_three_states`（3 种边界状态）、P7 门禁。

**Acceptance Criteria Result** 通过：3 本书（只存简报 / 已推演 / 已锻大纲）阶段、进度、
下一步逐字段一致。

**Status** RESOLVED

### NF-006

**Original Problem** 内容包标题是创意句固定长度截断 +「（设定草稿）」，截断点落在词中间。

**Root Cause** `settings_gen` 用 `brief.original_idea[:30]` 拼后缀。

**Files Changed** `src/novelforge/story_engine/settings_gen.py`

**Implementation** 新增 `_short_title()`：取创意**首个完整短句**、去掉状态后缀、
超长时在标点处收尾（不切断词）；状态由界面 badge / 就绪度表达，不写进名字。

**Tests Added** `tests/test_acceptance_repair_regressions.py::test_content_pack_title_is_readable`。

**Acceptance Criteria Result** 通过（例：「一个替人抄书的寒门书生被卷进夺嫡之争」，
不再出现「…买卖记忆，他（设定草稿）」）。

**Status** RESOLVED

### NF-007

**Original Problem** README / `.env.example` 承诺配置 API key 后可启用模型能力，
但服务恒传 `provider=None`，响应恒为 `source=rule` + `notes=["AI_UNAVAILABLE"]`。

**Root Cause** 产品路径从未构造 provider；文档承诺与实现不一致（INCOMPLETE IMPLEMENTATION）。

**Files Changed** `README.md`、`.env.example`

**Implementation** 选择报告的方案 (b)：**明确降级承诺**，让文档与真实行为一致——
说明当前版本所有生成都是本地确定性流程、产品路径没有接入任何 LLM provider、
配置 key 与不配置行为完全一致，模型接入属于后续版本能力（届时同步更新
README / `.env.example` / UI 文案）。UI 侧来源标注保持真实的「规则」语义。

未选择方案 (a)（实现完整 provider path）：那会把「新增模型能力」引入冻结的 V3.0，
并且需要真实外部依赖与 key 管理，属于新版本范围。

**Tests Added** 无自动化断言（属文档一致性）；由 README 校对与门禁「0 内部概念」覆盖。

**Acceptance Criteria Result** 通过：文档描述与实际行为一致；离线 / 无 key 时流程完整可走通。

**Status** RESOLVED

### NF-008

**Original Problem** 资源耗尽后主 CTA 仍推同一个不可执行行动，点一次 422 一次；
错误文案暴露 `protagonist` / `favors`。

**Root Cause** 三个原因：(1) 投影用 `runtime_candidates(state, pack, actor="")` 计算可用性，
而 `POST /runtime/advance` 用 `actor = next(iter(state.characters))`，
两边 actor 不同 → 投影说可执行、推进却拒绝；(2) UI 直接用「选中的候选」渲染主 CTA，
不做可用性过滤；(3) 错误文案由引擎直接拼装资源键。

**Files Changed** `src/novelforge/story_builder/v3_projection.py`、
`src/novelforge/api/story_builder_routes.py`、`ui/src/v3/WorkspaceView.tsx`、
`ui/src/v3/V3App.tsx`

**Implementation** 投影与推进使用**同一个默认 actor**；主 CTA 只在当前真正可执行的候选中选择
（选中的方向失效时自动退回第一条可执行方向，没有可执行方向时显示明确说明而不是假按钮）；
错误文案在 API 边界走作者语言映射。

**Tests Added** `tests/test_acceptance_repair_regressions.py::
test_projection_never_recommends_an_unavailable_action` /
`test_simulation_error_message_uses_author_language`。

**Acceptance Criteria Result** 通过：连续推演 6 次，投影推荐的每一步都返回 200；
错误文案不含 `protagonist` / `favors`。

**Status** RESOLVED

### NF-009

**Original Problem**「确定这个方向」保存成功后仍停留在创意面板。

**Root Cause** `CreationFlow.saveBrief()` 只更新 draft 与反馈，`step` 仍为 `'idea'`。

**Files Changed** `ui/src/v3/CreationFlow.tsx`、`tests/browser_v3_p6_acceptance.cjs`

**Implementation** 保存成功后直接 `setStep('settings')`；P6 门禁删掉「手动点步骤条」这一步，
改为断言保存后设定面板**自己**出现（旧代码在这里必然失败）。

**Acceptance Criteria Result** 通过：点击「确定这个方向」后同屏出现设定步骤与其主 CTA。

**Status** RESOLVED

### NF-010

**Original Problem** 创意与候选只在「确定这个方向」之后才落盘，刷新即丢且无提示。

**Root Cause** 设计如此（只有保存才写服务端），但界面没有说明「还没有保存」。

**Files Changed** `ui/src/v3/CreationFlow.tsx`

**Implementation** 本机缓存（`localStorage`，按 novel 分键）保存创意 / 参考 / 读者体验 / 候选；
刷新后恢复；界面在存在未保存内容时明确提示「这份创意还没有保存：它只缓存在本机，
刷新不会丢，但只有点『确定这个方向』才会写进作品。」；保存成功后清掉本机缓存。
服务端语义不变（仍然只有保存才写作品数据）。

**Acceptance Criteria Result** 通过：刷新后创意文本与候选可恢复，且未保存状态有明确提示。

**Status** RESOLVED

### NF-011

**Original Problem** 作品无法重命名、无法删除。

**Root Cause** 前端无入口，后端 `novels` 只有 create / list / get。

**Files Changed** `src/novelforge/story_builder/novel_admin.py`（新增）、
`src/novelforge/api/story_builder_routes.py`、`ui/src/v3/api.ts`、`ui/src/v3/NovelLanding.tsx`、
`ui/src/v3/V3App.tsx`

**Implementation**

* 重命名：`PATCH /api/novels/{id}`，只改 `NovelProfile.title`（不动任何事实）；
* 删除：`DELETE /api/novels/{id}?confirm=true` = **整体归档**——
  profile / 内容包 / StoryState / 大纲链 / 写作草稿（含历史 writer 目录）一起移动进
  gitignored 的 `workspace/archived_novels/<id>_<UTC>/` 并写 `ARCHIVE_MANIFEST.json`。
  没有二次确认返回 409；归档可恢复；不留下孤儿文件；
* UI：作品卡「管理」→ 改名输入 + 需要重新输入作品编号才能删除（二次确认）。

**Tests Added** `tests/test_acceptance_repair_regressions.py::
test_novel_rename_and_archive_delete_leave_no_orphans`（含「无孤儿」断言）。

**Acceptance Criteria Result** 通过：能删除测试作品、不存在孤儿大纲 / 状态文件、
删除需要二次确认。**未做硬删除**（不可恢复）是刻意的：归档式删除对作者数据更安全。

**Status** RESOLVED

### NF-012

**Original Problem** 有 blocker 时标题写「还差 0 步就可以导出」，左侧状态写「先补上：缺失步骤」。

**Root Cause** headline 只由 `len(missing)` 决定，完全不看 `blockers`；
另外「大纲质量」类问题被当作**阻塞导出的** blocker（见 §5 附带修复）。

**Files Changed** `src/novelforge/story_builder/v3_projection.py`、`ui/src/v3/ExportFlow.tsx`

**Implementation** 有 blocker 时标题直接给出第一条阻塞原因；只有没有 blocker 时才用
「还差 N 步」；导出工作区的主 CTA 也按 blocker / 缺失步骤 / 草稿三种情形给出对应动作。
附带修正：规划层面的质量问题（例如「还没有已发生章节」）不再阻塞导出——
只回答「会不会改变已经发生的事实」。

**Tests Added** `tests/test_acceptance_repair_regressions.py::
test_export_headline_reports_blockers_not_zero_steps`、P5 / P7 门禁。

**Acceptance Criteria Result** 通过：blocked 状态下标题与状态标签都指出真实阻塞
（`export.headline == export.blockers[0]`）。

**Status** RESOLVED

### NF-013

**Original Problem** 地点卡显示「控制方 控制方未知」。

**Root Cause** `_location_control_label()` 返回值自带「控制方」前缀，UI 又加了一次。

**Files Changed** `src/novelforge/story_builder/v3_projection.py`

**Implementation** 值层只返回「谁在控制」（未知 → 「未知」；真实势力 → 势力名；
无法解析的引擎 id 不再原样抛给作者）。

**Status** RESOLVED

### NF-014

**Original Problem** 高级工具页把内部 tab key 展示给作者（「高级工具 · export」「我在：exp…」）。

**Root Cause** `labelOfTab()` 未知 key 时返回原始 key，且渲染层没有匹配分支 → 空壳。

**Files Changed** `ui/src/guidedFlow.ts`、`ui/src/StoryBuilderPage.tsx`

**Implementation** 新增 `isKnownTab()`；未知页签在进入时回落到默认面板（不再渲染空壳）；
`labelOfTab` / `hintOfTab` 返回作者可读文案而不是 key。

**Status** RESOLVED

### NF-015

**Original Problem**「可行方向」卡片标题被截断成「向身边人...」。

**Root Cause** `.v3-character-head b` 全局 `nowrap + ellipsis`，路线卡沿用同一结构。

**Files Changed** `ui/src/v3/v3.css`

**Implementation** 路线卡标题允许两行、徽章允许换行（只影响路线卡，不改变其它实体卡）。

**Status** RESOLVED

### NF-016

**Original Problem** 人物 / 地点 / 势力只有原型标签（「普通执行者」「隐藏节点」…），没有名字。

**Root Cause** 设定候选给的是**定位**（archetype），没有任何地方标记它还是占位。

**Files Changed** `src/novelforge/story_builder/v3_projection.py`、`ui/src/v3/api.ts`、
`ui/src/v3/viewmodel.ts`、`ui/src/v3/design-system/components.tsx`、`ui/src/v3/V3App.tsx`

**Implementation** 投影给每个实体增加 `name_placeholder`；卡片显示「占位名」badge，
ContextPanel 明确说明「这是设定候选给的原型占位名，不是已经命名好的角色名」。
实体之间仍然可区分（定位名不同），并且作者一眼能看出还没命名。

**Tests Added** `tests/test_v3_entity_projection.py` 的 key 集合断言更新为包含
`name_placeholder`（断言变严，不是放宽）。

**Acceptance Criteria Result** 部分通过（选择报告允许的「明确标注占位」路径）：
实体可区分 + 占位状态显式。**编辑真实姓名**仍未实现（见 §9 Remaining）。

**Status** RESOLVED（按报告的「或明确标注这些是占位」分支）

### NF-017

**Original Problem**「已解锁：解锁：世界与角色候选」「来源：来源：main 路线」。

**Root Cause** 前缀在数据层与展示层各加了一次。

**Files Changed** `src/novelforge/story_engine/outline_forge.py`、
`src/novelforge/story_engine/outline_revision.py`、`ui/src/v3/design-system/choices.tsx`

**Implementation** 新增 `_strip_source_prefix()`：markdown / docx 导出与反馈卡在渲染前
去掉条目自带的「来源：」/「解锁：」前缀，保证前缀只出现一次。

**Tests Added** `test_outline_exports_have_no_internal_ids` 中显式断言
`来源：来源：` 出现次数为 0；P6 / P7 也对导出与工作区做同样断言。

**Status** RESOLVED

### NF-018

**Original Problem** README 记录的 `npx.cmd --prefix ui tsc --noEmit` 只打印帮助文本。

**Files Changed** `README.md`

**Implementation** 改为 `npm.cmd --prefix ui exec tsc -- --noEmit`，并注明原因。
本次门禁记录的真实命令仍是「在 `ui/` 下执行 `node_modules\.bin\tsc.cmd --noEmit`」。

**Status** RESOLVED

### NF-019

**Original Problem** `npm audit` 报告 2 条 vite / esbuild advisory。

**Files Changed** `README.md`

**Implementation** 说明风险范围（只影响本地 `vite dev server`；产品以构建产物 +
FastAPI 提供服务），修复需要 vite 大版本升级（breaking change），按版本计划单独处理。

**Status** RESOLVED（文档说明；依赖升级不在冻结版本的缺陷修复范围内）

### NF-020

**Original Problem** 现有门禁全部 PASS，却漏掉了本轮最严重的问题。

**Root Cause** 门禁覆盖不足：P5 只断言「返回新版工作台」链接存在；P6 在锻造**之前**
扫描内部 id；P6 的 Creation 主链用显式步骤跳转掩盖了「保存不推进」；没有任何门禁比对
Landing 与 Command Center、章节标题唯一性、writer 路径一致性。

**Files Changed** `tests/browser_v3_p7_acceptance.cjs`（新增）、
`tests/browser_v3_p5_acceptance.cjs`、`tests/browser_v3_p6_acceptance.cjs`、
`tests/test_acceptance_repair_regressions.py`（新增）

**Implementation**

* 新增 **P7 Regression Gate**：在「已锻造 30 章 + 已推演 + 已写作草稿」的最丰富状态下，
  断言 Export（内容非空 / 真实产物 / 下载入口）、Writer（UI 创建 → 投影可见 → 刷新仍在 →
  阶段完成 → 进度上升）、Title（30 章正文唯一 + 无字段占位）、Internal-ID（8 工作区 +
  markdown/json 导出 0 命中）、Consistency（Landing vs Command Center，3 本不同状态作品）、
  Export Copy（blocker 不再自相矛盾）、4 视口无横向溢出、0 console/pageerror/4xx；
* P5 增加「导出产物 + 写作草稿闭环」断言（替换原来的 legacy bridge 断言）；
* P6 在锻造后重扫 8 个工作区 + 2 种导出格式，并断言标题唯一；
* 新增 13 条 pytest 级回归（`tests/test_acceptance_repair_regressions.py`）。

**Acceptance Criteria Result** 通过：修复前这些断言**必然 FAIL**（§6 给出真实 before 证据）。

**Status** RESOLVED

## 5. Architecture Decisions

### Writer canonical storage

```text
canonical = novel/authoring/story_engine/writer/<novel_id>/index.json
            novel/authoring/story_engine/writer/<novel_id>/drafts/*.json
legacy    = workspace/wasteland_001_exports/writer_v1/<novel_id>/   （只读兼容）
```

选择理由：`novel/authoring/` 是产品数据的既有根（profiles / state / outlines 都在这里），
写作产物与其它 authoring 数据同生命周期；`WRITER_DIR` 是写入方与读取方共用的**同一常量**
（`test_writer_draft_service_and_projection_share_writer_dir` 守卫）。
历史路径保留只读回退：`canonical 为空 → 读 legacy`，canonical 一旦有草稿就不再读 legacy
（避免同一份草稿被计两次）。没有任何写入再指向 legacy 路径。

### Stage / Progress SSOT

唯一入口是 `v3_projection._journey_projection()`：

```text
Landing 卡片（novel_card）  → 裁剪 _journey_projection（不含实体级重活）
Command Center              → _journey_projection + 实体 / 推演 / 导出视图
Guided Flow / CTA / 进度条  → 消费同一份 stage / objective / next_action
```

`_light_stage()`（第二套公式）已删除。列表页性能边界通过「card 只取裁剪结果、
不做 simulation / entity 渲染」保留。

### Export capability

V3 最终**在产品内实现导出**（选择报告的方案 A），但不新建导出子系统：

```text
ui/src/v3/ExportFlow.tsx  →  GET /api/story-builder/export/package（既有 M16A 出口）
                          →  文件名 / export_id / 内容预览 / 下载（Blob；docx 走 base64）
                          →  写作草稿（既有 M16B writer draft API）
```

README / UI 文案不再引用「既有导出面板」；legacy 侧仍保持 19 个页签不变
（没有新增 export 页签，避免与 V3 原生导出形成第二套入口）。

### AI Provider

选择**明确移除承诺**（报告方案 b）：README 与 `.env.example` 明确说明当前版本
所有生成为本地确定性流程、provider 未接入、配置 key 与不配置行为一致。
未在冻结版本内新增模型能力。

### 附带结构决策（属当前任务正确性所需）

* **作者语言映射层**：新增 `novelforge/author_language.py`，把原先散落在
  `v3_projection` 的 SIMULATION_* 表上收为唯一来源，并让引擎生成文案 / 导出 / 错误文案共用它；
* **导出 blocker 语义**：只有「会改变已经发生事实」的修复问题才阻塞导出；
  规划层面的质量问题（大纲质量 findings）不再伪造阻塞（这正是 NF-012 的深层原因）；
* **作品删除 = 整体归档**：可恢复、无孤儿，避免 P3 功能引入数据丢失风险。

## 6. Test Results

### 修复前（HEAD `021b9ce`）——证明门禁能复现本轮问题

用同一个 P7 门禁 + 同一份探针在**修复前**的代码上运行：

```text
P7 Regression Gate（修复前）     FAIL
  → 章节标题正文重复：['先观察，不急着介入', '世界表层规则的分配方式被单方面调整',
                       '向身边人打听', '阶段目标（规划）', '长期方向（规划）']

probe_prefix_evidence.cjs（修复前，workspace/qa_repair_2026_09_17/probe_prefix_evidence.json）
  • 导出主 CTA 点击后：URL = #/story-builder?novel_id=...&tab=export
    legacy 面板容器正文长度 539、可见面板 0 个、无 v3-export-artifact
    → NF-001（空白 shell）+ NF-014（「我在：exp…」裸 key）
  • 导出标题「还差 0 步就可以导出」但存在 blocker → NF-012
  • POST /writer/drafts = 201，但投影 writer_drafts = 0、导出步骤缺 writer_drafts → NF-002
  • 内容包标题「…买卖记忆，他（设定草稿）」→ NF-006
```

### 修复后

```text
pytest -q                              889 passed / 687 deselected / 0 failed   （基线 876 passed）
                                       其中新增 tests/test_acceptance_repair_regressions.py = 13 passed
validate_project.py                    PASS
ui build (tsc -b && vite build)        PASS
tsc --noEmit（cwd=ui）                  PASS（exit 0）
node tests/browser_v3_p0_acceptance.cjs           PASS
node tests/browser_v3_p2_acceptance.cjs           PASS
node tests/browser_v3_p3_acceptance.cjs           PASS
node tests/browser_v3_p4_acceptance.cjs           PASS
node tests/browser_v3_p5_acceptance.cjs           PASS（含导出产物 + 写作草稿闭环）
node tests/browser_v3_p6_acceptance.cjs           PASS（含锻造后内部 id 扫描 + 标题唯一）
node tests/browser_v3_p7_acceptance.cjs           PASS（新增）
node tests/browser_v3_ui_foundation.cjs           PASS
node tests/browser_v3_visual_asset_gate.cjs       PASS（6/6 默认美术）
node tests/browser_advanced_tools.cjs             PASS（19 页签）
页面噪声（真实用户路径）                0 pageerror / 0 requestfailed / 0 console error / 0 非预期 4xx
```

修复后探针（`probe_postfix_evidence.json`）：

```text
导出工作区：不离开 V3（legacy host 不出现）、导出面板存在、步骤含 writer_drafts
写作草稿：POST 201 → 投影 writer_drafts = 1 → 导出步骤 writer_drafts done → 进度 42% → 44%
导出标题：「还差 1 步就可以导出」（与真实状态一致）
```

## 7. Generation QA

脚本：`workspace/qa_repair_2026_09_17/genqa_generation_quality.py`
结果：`workspace/qa_repair_2026_09_17/genqa_generation_quality.json`（status = PASS）
隔离数据根：`workspace/qa_repair_2026_09_17/root_repair/`

| 作品 | 题材 | 章节 | 重复标题 | 占位标题 | 内容字段内部 id | 导出内部 id | 投影内部 id | 可追溯来源 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `qa_repair_scifi` | 科幻 / 悬疑（sci_fi） | 30 | 0 | 0 | 0 | 0 | 0 | 30/30 |
| `qa_repair_court` | 古代 / 权谋（xianxia 内容包） | 30 | 0 | 0 | 0 | 0 | 0 | 30/30 |

标题样例（`qa_repair_scifi`）：

```text
第1章：向身边人打听
第4章：向身边人打听 · 人情 消耗 1
第6章：去工作场所
第27章：受阻：在公司中立足
第30章：决断：在公司中立足
```

摘要样例（含本作自己的阶段目的，不再是通用模板句）：

```text
已发生：向身边人打听；这一步服务于「在公司中立足」
```

对比修复前：`qa_acceptance_novel` 24/30 章为「阶段目标（规划）」/「长期方向（规划）」，
`qa_rich_novel` 22/30 章同名（见验收报告 §7.3）。

## 8. End-to-End Verification

真实浏览器（Edge / Playwright headless），隔离数据根，全部在修复后的代码上执行：

**A. 普通用户完整旅程（P6 门禁，全程 UI）**

```text
Landing → 新建作品 → Command Center → 创作（一句话创意 → 候选 → 确定这个方向
→ 设定候选 → 保存并检查起点 → 开始检查 → 开始推演）→ 阶段 / 目标 / 下一步真实变化
→ 8 个工作区（作者语言 / 无内部 id）→ 推演 → 锻造四级大纲 → 检查 → 导出
→ 锻造后门禁（标题唯一 / 8 工作区 + 2 种导出 0 内部 id）
→ 刷新 / 深链接 / 浏览器 Back / 切换作品 → 高级工具 19 页签 → 4 视口
```

（截图目录：`workspace/qa_repair_2026_09_17/shots/` 与
`workspace/product_v3/visual_review/audit/`）

**B. 写作 → 导出闭环（P7 门禁 + P5 门禁）**

```text
导出工作区：真实就绪度（6 步）→ 创建写作草稿 → 「已有写作草稿」完成
→ 总体进度上升 → 生成导出包（文件名 / export_id / 内容预览 / 下载）
→ 真实下载文件（`workspace/qa_repair_2026_09_17/shots/p7_downloaded_planning_export_*.md`，
  9159 字节，内容 0 内部 id）
→ 刷新页面：草稿与产物状态仍然成立
```

导出包 markdown / docx 也不再暴露内部组件名（`NovelProfile + ContentPack` /
`StoryState.characters` / `canon sqlite`）：文档里只出现作者语言
（「已经发生的事实」「还在计划里」…），机器可读的内部来源保留在 JSON manifest 里。

**C. 三本不同状态作品一致性（P7）**

```text
只存简报 / 已推演未锻大纲 / 已锻 30 章大纲并写作草稿
→ Landing 卡片与 Command Center 的阶段 / 阶段名 / 进度 / 下一步逐字段一致
→ 作品内页面确实显示投影给出的阶段名与下一步
```

**D. 作品管理（API + pytest 验证）**

```text
重命名 → profile.title 更新；删除（未确认）→ 409；删除（确认）→ 8 个产物整体归档、
作品列表清空、磁盘无孤儿文件、归档目录含 ARCHIVE_MANIFEST.json
```

**E. 视觉 / 响应式**

```text
Visual Asset Gate：6/6 required 默认美术真实渲染，0 broken image
1440 / 1280 / 1024 / 390：0 横向溢出；导出工作区与作品卡管理区在四视口均可操作
```

## 9. Remaining Issues

1. **NF-016 的真实姓名编辑未实现**：本轮按报告的「或明确标注这些是占位」分支完成
   （实体可区分 + 显式「占位名」标注）。让作者在 UI 里直接给角色 / 地点 / 势力改名
   需要内容包编辑写入口，属于新能力，建议进下一版计划。
2. **删除是归档语义**：`DELETE /novels/{id}` 把产物整体移入
   `workspace/archived_novels/`（可恢复），不做不可恢复的硬删除。归档目录只增不减，
   后续版本可提供「归档管理 / 彻底清除」入口。
3. **Landing 列表成本**：卡片现在复用同一套 journey 计算（含 settings_check 与 repair
   诊断），作品很多时列表加载会比旧的「轻量估算」慢。这是「一致性优先于估算」的取舍；
   如需要可后续加投影缓存（不影响语义）。
4. **NF-019 依赖升级未做**：vite / esbuild advisory 需要 vite 大版本升级（breaking），
   按版本计划单独处理。
5. **`docs/V3_FULL_PRODUCT_ACCEPTANCE.json` 与默认 pytest 口径不一致**（验收报告 §11 提到）：
   本轮没有重新生成 release 证据文件（它属于已发布 V3.0 的冻结 artifact）；
   本报告 §6 记录了本轮可复现的真实数字。

## 10. Final Verdict

# READY FOR RE-REVIEW

判定依据：

* **所有 P1 已解决**：NF-001（导出真实可用）、NF-002（写作草稿 SSOT + UI 入口 +
  导出阶段可完成）都有浏览器门禁与 pytest 回归；
* **核心闭环实际完成**：真实 UI 旅程从新建作品一路走到「生成导出包并下载」，
  并在刷新后仍然成立；
* **没有新的 blocker**：`pytest` 889 passed / 0 failed（基线 876 + 新增 13），`validate_project` PASS，
  UI build / tsc PASS，全部浏览器门禁（P0–P7 + foundation + visual + advanced）PASS；
  frozen boundary（Canon / StoryState / legacy 源 / Repair Contract / Gate /
  approval boundary）未被修改，release tag / release commit 未移动；
* **生成内容可用**：两本不同题材作品各 30 章，标题唯一、无字段占位、无内部 id；
* **遗留项全部是 P3/P4 级别的产品增强**（见 §9），且已明确记录，不隐藏。

本分支不宣布 PASS —— 最终判定由独立 Re-review 给出。

---

# RE-REVIEW ENTRY POINT

## 1. 原 FAIL 原因

* NF-001 导出主 CTA 落到不存在的 legacy 页签（空白页）；
* NF-002 写作草稿读写路径不一致 + 无 UI 入口，最后一步目标不可达（进度天花板 51%）；
* NF-003 章节标题 73%–80% 为字段标签占位；NF-004 内部 id 进入作者可见内容；
* NF-005 入口页与作品内对同一本书给出不同阶段 / 进度 / 下一步。

## 2. 已修复 Issue

NF-001 … NF-020 全部处理完毕，逐条根因 / 改动 / 测试见 §4，状态表见 §3。

## 3. 最重要复测路径

```text
1) 新建作品 → 创作主链 → 推演 → 锻造 30 章大纲 → 确认 → 检查
2) 导出工作区：创建写作草稿 →「已有写作草稿」完成 → 总体进度上升 → 生成导出包 → 下载
3) 刷新页面 / 重启服务 → 草稿与大纲仍在，导出步骤仍为完成
4) 大纲工作区：30 章标题唯一、无「阶段目标（规划）」类占位、无内部 id
5) Landing 卡片与 Command Center 对同一本书的阶段 / 进度 / 下一步逐字段一致
```

## 4. 新增 regression gates

```text
tests/browser_v3_p7_acceptance.cjs           新增（Export / Writer / Title / Internal-ID /
                                             Consistency / Export Copy / 4 视口）
tests/browser_v3_p5_acceptance.cjs           收紧（导出产物 + 写作草稿闭环）
tests/browser_v3_p6_acceptance.cjs           收紧（保存自动推进 + 锻造后内部 id 扫描 + 标题唯一）
tests/test_acceptance_repair_regressions.py  新增（13 条 pytest 级回归）
```

修复前的失败证据（同一门禁 + 探针）：§6「修复前」小节。

## 5. QA 数据位置

```text
workspace/qa_review_2026_09_17/        独立验收原始证据（未删除、未修改）
workspace/qa_repair_2026_09_17/        本轮修复的 QA 证据区
  ├─ genqa_generation_quality.py/.json 两本作品 × 30 章生成质量
  ├─ probe_prefix_evidence.cjs         修复前 / 修复后对比探针
  ├─ probe_prefix_evidence.json        （修复前）
  ├─ probe_postfix_evidence.json       （修复后）
  ├─ root_repair/ · root_ui/ · root_gates/ · root_prefix/   隔离数据根
  └─ shots/                            本轮截图
```

## 6. 新隔离测试数据位置

```text
workspace/qa_repair_2026_09_17/root_ui/        P7 门禁使用的隔离数据根
workspace/qa_repair_2026_09_17/root_gates/     P5 / P6 门禁使用的隔离数据根
workspace/qa_repair_2026_09_17/root_repair/    生成质量 QA 的隔离数据根
```

（真实作者数据 `novel/authoring/**`、`workspace/**` 全部未进入版本控制，也未被打包提交。）

## 7. 启动命令

```powershell
# 产品启动（真实数据根）
.venv\Scripts\python.exe scripts/start_novelforge_ui.py --port 8000

# 隔离数据根（复核用；先构建前端再启动）
npm.cmd run build --prefix ui
.venv\Scripts\python.exe scripts/creator_ui_test_server.py --port 8035 --root workspace/qa_repair_2026_09_17/root_ui
```

## 8. 测试命令

```powershell
.venv\Scripts\python.exe -m pytest -q
.venv\Scripts\python.exe scripts/validate_project.py
npm.cmd --prefix ui exec tsc -- --noEmit
npm.cmd run build --prefix ui

# 浏览器门禁（Playwright 由开发者环境提供）
node tests/browser_v3_p5_acceptance.cjs        # 需 8030 数据根
node tests/browser_v3_p6_acceptance.cjs        # 需 8030 数据根
node tests/browser_v3_p7_acceptance.cjs        # 需 8035 数据根
node tests/browser_v3_visual_asset_gate.cjs
node tests/browser_advanced_tools.cjs
```
