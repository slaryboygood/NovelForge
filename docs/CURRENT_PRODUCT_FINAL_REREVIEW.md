# NovelForge V3 Final Independent Re-review

> 本次审查性质：**最终独立验收 / Release QA / Product Acceptance Re-review**
> 审查对象：当前工作区（branch `codex/product-v3-game-ui`，HEAD `021b9ce`，产品版本 NovelForge Product V3.0）
> 前置文档：`docs/CURRENT_PRODUCT_ACCEPTANCE_REVIEW.md`（Initial Review = FAIL）、
> `docs/CURRENT_PRODUCT_ACCEPTANCE_REPAIR_REPORT.md`（Repair = READY FOR RE-REVIEW）
> 审查日期：2026-09-17
> 审查方式：真实启动 + 全新隔离数据根 + 真实浏览器操作 + 真实文件下载与阅读 + 全量测试复跑
> **本分支未修改任何业务代码、UI、提示词、生成算法、测试或既有 QA 证据。**
> 唯一新增的仓库文件是本报告；全部 QA 证据写在 gitignored 的 `workspace/qa_rereview_2026_09_17/`。

---

## 1. Executive Summary

Repair 分支声明修复的 20 条问题，我逐条重新验证（不依赖 Repair 的测试与结论）：

- **核心闭环这次真的通了**：在一个全新的隔离数据根上，我从 Landing 开始，用真实浏览器走完
  `新建作品 → 一句话创意 → 候选 → 确定这个方向 → 设定候选 → 保存 → 自检 → 开始推演 →
  连续推演 → 锻造并确认 30 章大纲 → 检查 → 创建写作草稿 → 生成并下载 Markdown / JSON / Word →
  刷新 → 重开作品 → 重启后端`，全程 0 失败、0 白屏、0 非预期 4xx、0 pageerror。
- **NF-001 / NF-002 没有回归，并且是真修**：导出工作区现在渲染真实面板并产出可下载的真实文件；
  写作草稿写入 canonical 目录 `novel/authoring/story_engine/writer/<novel_id>/`，
  投影看得到（导出阶段 1/1，总体进度 44% → 47%），刷新、重启后仍然成立；
  磁盘上**完全没有**再创建 `workspace/.../writer_v1/`。
- **NF-005 一致**：4 种边界状态（仅创建 / 已存设定 / 已推演 / 已锻造+草稿）下，
  Landing 卡片与 Command Center 的 `stage / stage_label / progress / next_action / CTA` 逐字段一致。
- **但生成质量没有修到位**：30 章标题字符串唯一（`len(set(titles)) == len(titles)` 成立），
  可**语义重复仍然严重**——我独立跑的 3 本 × 30 章里，分别有 **15 / 7 / 7 章**是
  「去工作场所（第 N 次）」这种同一素材 + 序号的形式；主链作品导出的 Word 文档里是
  **19 / 30 章**（第 2–20 章连续同名 + 序号）；导出物里还稳定出现
  `阶段目标：…` / `长期方向（前提：…）` 这类**字段标签被当成内容**的模板文本。
  这正是 Initial Review §13 明确要求「不能因为 duplicate = 0 就认定质量正常」的那种情况。
- **文档类修复有一条没生效**：Repair 把 README 的类型检查命令改成了
  `npm.cmd --prefix ui exec tsc -- --noEmit`，但该命令在仓库根执行**仍然只打印 tsc 帮助文本**
  （exit 1），和修改前的错误行为一样。

因此结论是 **PASS WITH ISSUES**：产品现在**可以**被普通用户用来完成一次从创意到真实导出文件的
创作流程；但导出物仍是「结构蓝图」而不是「可以照着写的章节素材」，并且存在若干新发现的
可用性问题（刷新后无法直接确定方向；导出物混入无关的 V2 历史分区）。

---

## 2. Final Verdict

# PASS WITH ISSUES

判定依据：

| 维度 | 结果 |
| --- | --- |
| 是否有 P0 | 无 |
| 是否有核心 P1 | 无。NF-001 / NF-002 复验通过：Writer 可达、Export 产出真实可用文件、数据可持久化、主链可完成 |
| 核心 E2E | 通过（72 个检查点，0 失败） |
| Writer | 通过 |
| Export | 通过（Markdown / JSON / Word 三种格式均生成、下载、可读、非 0 字节） |
| 持久化 | 通过（刷新 / 新上下文 / 切换作品 / 重启后端，状态完全一致） |
| 剩余问题 | NF-003（P2，生成质量语义重复 + 字段标签进正文）、NF-006 / NF-016 / NF-020（P3 部分解决）、NF-018（P4 未解决）、NR-001…NR-004 |

按本分支的验收规则：

- 允许 PASS 的条件之一「没有足以影响主要创作 / 交付质量的 P2」**未满足**（NF-003 残留），
  因此不能给 PASS；
- 但不存在任何 P0 / 核心 P1，核心流程完整可跑，因此也不是 FAIL。

---

## 3. Review Environment

```text
OS              Windows（PowerShell 7），工作目录 F:\AI_小说\硅基升维
Python          3.11.9（.venv\Scripts\python.exe，已 bootstrap）
Node            v24.19.0（系统）
浏览器          Microsoft Edge（Playwright channel=msedge，headless）
Playwright      开发者自带 .dsh-runtime/.dsh-browsertests/node_modules（NODE_PATH 注入）
前端构建        npm.cmd run build --prefix ui → PASS（vite 5.4.21，81 modules，6 个默认美术指纹化）
隔离数据根      workspace/qa_rereview_2026_09_17/root_final2（用户主链，port 8048）
                workspace/qa_rereview_2026_09_17/root_genqa（生成质量，port 8050）
                workspace/qa_rereview_2026_09_17/root_extra（边界/一致性/性能，port 8051）
                workspace/qa_rereview_2026_09_17/root_gates · root_ui（浏览器门禁，port 8030 / 8035）
```

本轮**没有**使用 `qa_review_2026_09_17/` 或 `qa_repair_2026_09_17/` 里的测试小说作为 PASS 证据；
它们只用于对照（例如确认 Repair 的旧证据确实存在）。所有结论来自新 novel id、新隔离根、
新截图、新下载文件。

---

## 4. Git / Scope Verification

```text
branch                      codex/product-v3-game-ui
HEAD                        021b9ce（Repair 未提交工作，未产生新 commit）
release commit              20d03cfa78b458e18e385fdaf58a04e3f2bde1c3  ← 未被修改
tag novelforge-product-v3.0 指向 20d03cfa…（未移动）
tag novelforge-product-v2.0 指向 56cda829…（未移动）
工作区改动                   32 modified + 8 untracked（与 Repair 报告范围一致，无新增）
```

核对结果：

- **未触碰 frozen boundary**：`git status` 中没有任何 Canon / StoryState / legacy source /
  source Chapter IR / Repair Contract / Gate / truth precedence / approval boundary 文件
  （按 `canon` / `wasteland_001.sqlite` / `repair_contract` / `REPAIR_GATE` / `legacy` 检索为空）。
- **未修改 release artifact**：`docs/V3_FULL_PRODUCT_ACCEPTANCE.json` 无改动。
- **未修改任何 release tag / release commit**。
- **无 QA 数据进版本控制**：本轮全部证据在 gitignored 的 `workspace/qa_rereview_2026_09_17/`；
  `git status` 与本轮开始时完全一致（40 条），没有出现新的仓库内文件。
- 新增源码文件只有 Repair Report 声明的两个（`src/novelforge/author_language.py`、
  `src/novelforge/story_builder/novel_admin.py`）与两个 UI 文件（`ExportFlow.tsx`、`export-flow.css`），
  **没有发现「未经报告说明的文件」**。

---

## 5. Automated Test Results

```text
.venv\Scripts\python.exe -m pytest -q
    889 passed / 687 deselected / 0 failed / 0 error     （307.46s）
    ↔ Repair 报告声明 889 / 0 failed —— 复现一致

.venv\Scripts\python.exe scripts/validate_project.py
    NovelForge story-builder: PASS

cd ui; npm.cmd exec tsc -- --noEmit                 → PASS（exit 0）
npm.cmd --prefix ui exec tsc -- --noEmit            → FAIL（exit 1，只打印 tsc 帮助文本）
                                                      ↑ 这就是 NF-018：README 现在的写法仍然不生效
npm.cmd run build --prefix ui                        → PASS

浏览器门禁（隔离数据根 / 新截图目录）
    node tests/browser_v3_p0_acceptance.cjs          PASS
    node tests/browser_v3_p2_acceptance.cjs          PASS
    node tests/browser_v3_p3_acceptance.cjs          PASS
    node tests/browser_v3_p4_acceptance.cjs          PASS
    node tests/browser_v3_p5_acceptance.cjs          PASS
    node tests/browser_v3_p6_acceptance.cjs          PASS
    node tests/browser_v3_p7_acceptance.cjs          PASS（新增门禁）
    node tests/browser_v3_ui_foundation.cjs          PASS
    node tests/browser_v3_visual_asset_gate.cjs      PASS（6/6 required 默认美术）
    node tests/browser_advanced_tools.cjs            PASS（19 页签 + 8 个 V3 工具入口 + 4 视口）
```

门禁说明（重要）：`browser_advanced_tools.cjs` 的默认作品 `audit_fmt_55126` 在本机任何数据根里都
不存在，本次在我自己的隔离根里用 API 预置了同名作品（`novel_v3_accept_783716` / `audit_fmt_55126`）
才让它跑通——这说明**门禁依赖一个未随仓库提供的数据根**，属于验收可复现性风险（见 §18）。

页面噪声（真实用户路径）：

```text
console.error      2（均为 §22 刻意触发的异常路径：非法编号 422、不存在作品 404）
pageerror          0
requestfailed      0
非预期 4xx/5xx      0
```

---

## 6. Original Issue Regression Matrix

| Issue | Original Severity | Repair Claimed | Re-review Result |
| --- | --- | --- | --- |
| NF-001 导出主 CTA 落到不存在的 legacy 页签 | P1 | RESOLVED | **VERIFIED RESOLVED** |
| NF-002 写作草稿读写路径不一致 + 无 UI 入口 | P1 | RESOLVED | **VERIFIED RESOLVED** |
| NF-003 章节标题用内部字段标签占位 | P2 | RESOLVED | **PARTIALLY RESOLVED**（字符串唯一，但语义重复 + 字段标签仍进正文/导出） |
| NF-004 内部 id 泄漏到作者可见内容 | P2 | RESOLVED | **VERIFIED RESOLVED**（实体 id 命中 0；新发现的枚举/英文分区另记 NR-003） |
| NF-005 Landing 与 Command Center 不一致 | P2 | RESOLVED | **VERIFIED RESOLVED**（4 种边界状态逐字段一致） |
| NF-006 内容包标题被截断 +「（设定草稿）」 | P2 | RESOLVED | **PARTIALLY RESOLVED**（后缀已去掉；长首句仍被硬截断） |
| NF-007 模型能力未接线但文档承诺可用 | P2 | RESOLVED | **VERIFIED RESOLVED**（README / .env.example 已明确降级） |
| NF-008 资源耗尽后主 CTA 仍推 422 行动 | P2 | RESOLVED | **VERIFIED RESOLVED**（60 步连续推演，全部 200） |
| NF-009「确定这个方向」不推进向导 | P2 | RESOLVED | **VERIFIED RESOLVED** |
| NF-010 创意草稿不落盘、无未保存提示 | P3 | RESOLVED | **PARTIALLY RESOLVED**（文本+候选+提示齐备，但刷新后主 CTA 禁用 → NR-001） |
| NF-011 作品无法重命名 / 删除 | P3 | RESOLVED | **VERIFIED RESOLVED** |
| NF-012 导出文案自相矛盾（「还差 0 步」） | P3 | RESOLVED | **VERIFIED RESOLVED** |
| NF-013「控制方 控制方未知」 | P3 | RESOLVED | **VERIFIED RESOLVED** |
| NF-014 高级工具显示裸 tab key | P3 | RESOLVED | **VERIFIED RESOLVED** |
| NF-015 行动名被截断成「向身边人…」 | P3 | RESOLVED | **VERIFIED RESOLVED** |
| NF-016 角色 / 地点 / 势力只有原型名 | P3 | RESOLVED（显式占位标注） | **PARTIALLY RESOLVED**（UI 有「占位名」；导出物仍是原型名且无占位标注） |
| NF-017「已解锁：解锁：」「来源：来源：」 | P4 | RESOLVED | **VERIFIED RESOLVED** |
| NF-018 README 的 tsc 命令不执行类型检查 | P4 | RESOLVED | **NOT RESOLVED**（改后的命令仍然只打印帮助，exit 1） |
| NF-019 npm audit（vite / esbuild） | P4 | RESOLVED（文档说明） | **VERIFIED RESOLVED**（advisory 仍在，文档已如实说明） |
| NF-020 浏览器门禁盲区 | P3 | RESOLVED | **PARTIALLY RESOLVED**（P7 新增 + P5/P6 收紧，实际可拦住本轮问题；但 P6 大纲仍是 API 直造，非 UI） |

### 关键复验证据（逐条）

- **NF-001**：导出工作区点击主 CTA 后不再离开 V3；渲染 `v3-export-panel`（正文长度远超空壳），
  产出 `planning_export_rr_final_403297_main.md`（3,186 字符）、`.json`（37,116 字符）、
  `.docx`（2,390 字节，`PK` zip 容器），三者都能真实下载并打开。
  旧链接 `#/story-builder?...&tab=export` 现在渲染 791 字符的真实面板、16 个 testid，**不再空白**，
  也不再出现「我在：export」裸 key。
- **NF-002**：UI 创建草稿后 `facts.writer_drafts` 0 → 1，导出步骤 `writer_drafts: false → true`，
  总体进度 44% → 47%；磁盘上只见
  `root_final2/novel/authoring/story_engine/writer/rr_final_403297/{index.json,drafts/*.json}`，
  `workspace/.../writer_v1/` **根本不存在**。
  另外单独构造了「只有 legacy writer 数据」的作品：投影读到 1 份（只读回退生效），
  创建 canonical 草稿后计数仍是 1（不叠加），legacy 两个文件哈希前后完全一致（不迁移、不重写）。
- **NF-003**：见 §12（结论 PARTIALLY RESOLVED）。
- **NF-004**：8 个 V3 工作区、outline markdown/json 导出、导出包 markdown 正文
  对 `start_place / work_place / hidden_place / ev_* / act_* / faction_\d+ / npc_\d+ /
  protagonist / favors / source_ids / future_plan:` 的命中数全部为 **0**。
  JSON 里仍保留 `route_0003`、`StoryState.characters` 这类结构化来源——这是 §15 明确允许的
  「export JSON 的结构化来源仍存在」，不计为缺陷。
- **NF-005**：见 §11。
- **NF-008**：投影推荐的每一步都真的可执行——浏览器连续 40 次点击主 CTA，全部 200；
  API 连续 60 次推演（`probe_exhaustion.py`）状态码集合 = `{200}`，0 次失败；
  投影在推演充分后自动把主目标切到「生成大纲」，不是死循环推同一个失败动作。
- **NF-011**：UI 改名 → Landing 立即显示新名字，`novel_id` 不变，大纲数据不丢；
  未确认删除返回 **409**，管理面板文案明确写着「删除＝把这本作品的全部产物整体归档…
  （可恢复），不会留下孤儿文件」，输入作品编号后才允许删除，删除后作品从列表消失。
  **UI 没有把归档说成「永久删除」，§17 的 UX 顾虑不成立。**
- **NF-012**：制造「已确认大纲 → 再推演 → 大纲过期」后，
  `headline = 故事推进过，大纲需要重新锻造后才能导出。`，`blockers` 与之一致，
  面板主 CTA 变成「先处理阻塞：大纲与冲突」，**没有**再出现「还差 0 步就可以导出」。
- **NF-013 / NF-017**：世界 / 推演 / 创作工作区文本中
  `控制方 控制方`、`已解锁：解锁：`、`来源：来源：` 命中数均为 0。
- **NF-015**：`v3.css` 新增 `.v3-route .v3-character-head b { white-space: normal; … }`；
  1440 视口实测「查证与「一个替人抄书的寒门书生」有关的记录」等长标题**完整两行显示**。
- **NF-018**：见 §5 与 §16（NR 相关判定：NOT RESOLVED）。

---

## 7. Fresh End-to-End Journey

全新隔离数据根 `root_final2`，全新作品 `rr_final_403297`，全程真实浏览器点击
（脚本：`workspace/qa_rereview_2026_09_17/rereview_journey.cjs`；
数据：`browser_journey.json`，72 个检查点，**failures = 0**）。

```text
Landing（空数据根空态「还没有作品」）
  → 新建作品（UI 对话框）→ Command Center（阶段=创意，进度 0%）
  → 创作：中文一句话创意 → 生成方向候选 → 真实候选（题材 / 内容包 / 基调 / 卖点）→ 点选题材
  → 刷新：创意文本恢复、候选恢复、明确显示「这份创意还没有保存：它只缓存在本机…」
  → 确定这个方向 → **同屏自动进入「设定与起点」**（本地缓存已清除）
  → 设定候选（9 组）→ 逐组勾选 → 保存并检查起点
  → 自检通过（「自检通过 / 没有任何缺项。」）→ 开始剧情推演（起点事实落盘）
  → 推演：连续 40 次主 CTA，全部 200，主 CTA 根据真实可用性切换
  → 大纲：生成章节大纲 → legacy 大纲锻造（3 卷 × 2 篇章 × 5 章）→ 预览结构 → 锻造四级大纲
         → 确认整条大纲（「已按顺序确认 40 个大纲层」）→ 回到 V3 大纲工作区看到 4 级结构 + 30 章
  → 检查工作区（作者语言，无内部 id）
  → 导出：创建写作草稿 → 投影 writer_drafts = 1、导出阶段 1/1、进度 44% → 47%
  → 生成导出包：Markdown / JSON / Word 三种格式各自生成 → 下载 → 文件落盘
  → 刷新 / 新浏览器上下文 / 切换作品再回来：草稿、大纲、进度全部还在
  → 四视口（1440 / 1280 / 1024 / 390）× 5 个页面 = 20 次测量，0 横向溢出
```

对本次要回答的问题：

> **一个第一次使用 NovelForge 的普通用户，现在是否真的可以独立完成一次从创意到可交付文件的
> 小说创作流程？**

**可以完成流程**——从空数据根到下载到 Markdown / JSON / Word 文件，全程没有阻塞、没有白屏、
没有需要绕过 UI 的步骤（连大纲锻造都是在 legacy 面板里真实点击出来的）。
但「可交付文件」目前是**结构蓝图**：章节标题大面积是同一素材 + 序号，正文里带模板标签，
人物/地点/势力仍是原型名。见 §12 与 §17。

---

## 8. Writer Verification

| 检查项 | 结果 | 证据 |
| --- | --- | --- |
| UI 有创建写作草稿入口 | 通过（导出工作区「创建写作草稿」按钮） | `browser_journey.json` `nf002-writer` |
| API 成功 | 通过（POST `/writer/drafts` → 201） | `export-after-draft` |
| 投影 `writer_drafts = 1` | 通过 | 0 → 1 |
| 导出 readiness 中 writer step = completed | 通过（`writer_drafts: true`） | `export.步骤` |
| 总体 progress 真实变化 | 通过（44% → 47%，阶段 7/8） | `export-before-draft` / `export-after-draft` |
| 刷新 / 留开 / 返回 / 关闭上下文 | 通过（草稿数量不变） | `persistence-after-refresh` / `persistence-new-context` |
| 重启 backend | 通过（重启前后 command-center 快照完全一致） | `logs/restart_before.json` vs 重启后对比 |
| canonical store 只写一处 | 通过：`novel/authoring/story_engine/writer/rr_final_403297/{index.json,drafts/draft_overview_25ae5cf95065ba9c.json}`，**没有** `workspace/.../writer_v1/` | 磁盘清单 |
| legacy 只读兼容 | 通过：只有 legacy 数据时投影读到 1 份；创建 canonical 后计数仍为 1；legacy 两文件哈希前后一致 | `extra_probes.json` `legacy_writer` |
| 草稿能否编辑 | **不能**（产品无编辑入口，草稿由引擎生成 preview 文本） | 见 §17 限制说明 |

`legacy_writer` 探针原始结果：

```json
{"legacy_read_visible": 1, "legacy_list_endpoint": 1, "canonical_create_status": 201,
 "after_canonical_draft_count": 1, "legacy_files_unchanged": true,
 "canonical_index_written": true, "no_double_count": true}
```

---

## 9. Export Verification

全部走 V3 UI 的导出工作区（不是直接调 API 代替）：

| 格式 | 面板文件名 | 面板预览 | 下载文件 | 字节数 | 内容校验 |
| --- | --- | --- | --- | --- | --- |
| Markdown | `planning_export_rr_final_403297_main.md` | 3,186 字符 | 可下载 | 3,186 | 无内部实体 id；无「来源：来源：」 |
| JSON | `planning_export_rr_final_403297_main.json` | 4,017 字符 | 可下载 | 37,116 | 可 `json.loads`；作者字段无实体 id（结构化 `source` 保留，按设计允许） |
| Word | `planning_export_rr_final_403297_main.docx` | 无文本预览（base64） | 可下载 | 2,390 | `PK` zip 容器，可解压出 `word/document.xml`，69 段正文 |

补充核对：

- 三种格式的 `filename` / `export_id` / `content` / `preview` / `download` 都真实存在，
  **不是只断言 HTTP 200**：文件都落到磁盘、都能读、都不是 0 字节、内容都属于当前测试作品
  （文件名与内容里都带 `rr_final_403297`）。
- 退出重进、重启后端后重新生成，产物仍可重新得到；Writer-ready 步骤不再缺失。
- **旧链接 `tab=export` 不再空白**（791 字符正文 / 16 个 testid），也不再显示裸 tab key。
- 目录：`workspace/qa_rereview_2026_09_17/downloads/`；内容审查见 §13 与 §23 相关小节（§17 限制）。

---

## 10. Persistence Verification

| 场景 | 结果 |
| --- | --- |
| 页面刷新（Command Center / 导出） | 进度 47%、阶段「导出」、30 章、草稿 1 份 —— 完全一致 |
| 新浏览器上下文（模拟新会话） | 大纲 30 章仍渲染 |
| 切换作品再回来 | 作品卡「继续创作」→ 阶段 / 进度 / 下一步与之前一致 |
| **重启后端进程**（`Stop-Process` 后同一 root 重启） | 重启前后 command-center 快照 `before == after`（阶段、进度、writer_drafts、章节数、export ready、6 个就绪步骤全部一致） |
| 深链接 | `#/n/<id>/<workspace>` 直接打开对应工作区 |
| 不存在作品 / 未知 workspace | 优雅错误态或回落 Command Center，无白屏 |

没有观察到数据丢失、覆盖写、半写入或脏读。

---

## 11. Stage / Progress Consistency

用 4 本不同状态作品逐字段比较 Landing 卡片与 Command Center（`extra_probes.json` `consistency`）：

| 作品（状态） | stage | stage_label | progress | next_action | CTA label | 全部一致 |
| --- | --- | --- | --- | --- | --- | --- |
| `rr_state_a`（刚创建） | creation | 创意 | 0 | 确定一句话创意 | 开始一句创意 | ✅ |
| `rr_state_b`（已有设定，未推演） | simulation | 推演 | 35 | 开始剧情推演 | 开始推演 | ✅ |
| `rr_state_c`（已推演，未锻造） | outline | 大纲 | 37 | 生成大纲 | 生成大纲 | ✅ |
| `rr_state_d`（30 章 + 草稿 + 可导出） | export | 导出 | 47 | 这一步已经完成 | 继续创作 | ✅ |

主链作品 `rr_final_403297`：Landing 卡片与 Command Center 都是 `export / 导出 / 47% / 这一步已经完成`。
**NF-005 结论：单一状态计算入口的修复是真实的。**

---

## 12. Generation Quality（3 本 × 30 章，独立重建）

不复用 Repair 的 `qa_repair_scifi` / `qa_repair_court`；在 `root_genqa` 里新建 3 本不同题材作品
（科幻悬疑 `sci_fi` / 古代权谋 `xianxia` / 现代犯罪 `modern_crime`），每本 9 组设定逐组点选、
推演、锻造 3 卷 × 2 篇章 × 5 章并确认。

| 作品 | 章节 | 标题字符串重复 | 占位标题（字段标签） | 作者字段内部 id | 导出内部 id | 可追溯来源 |
| --- | --- | --- | --- | --- | --- | --- |
| `rr_genqa_scifi` | 30 | 0 | `阶段目标` 24 次 / `长期方向` 30 次 | 0 | markdown 0 | 30/30 章有 `source_ids`（84 条） |
| `rr_genqa_court` | 30 | 0 | `阶段目标` 36 次 / `长期方向` 30 次 | 0 | markdown 0 | 30/30（42 条） |
| `rr_genqa_crime` | 30 | 0 | `阶段目标` 36 次 / `长期方向` 30 次 | 0 | markdown 0 | 30/30（42 条） |

**字符串唯一性成立，但语义质量不成立。** 逐本统计「同一素材 + 序号」：

| 作品 | 含「（第 N 次）」的标题 | 最大同名基底 | 摘要里出现字段标签的章节 |
| --- | --- | --- | --- |
| `rr_genqa_scifi` | 15 / 30 | 「去工作场所」×16 | 12 / 30 |
| `rr_genqa_court` | 7 / 30 | 「去工作场所」×4 | 18 / 30 |
| `rr_genqa_crime` | 7 / 30 | 「去工作场所」×4 | 18 / 30 |

主链作品（`rr_final_403297`）导出的 Word 文档里，第 2–20 章的标题是：

```text
第2章：去工作场所
第3章：去工作场所（第 2 次）
第4章：去工作场所（第 3 次）
...
第20章：去工作场所（第 19 次）
```

即 **19 / 30 章是同一素材 + 序号**。Initial Review 的 §13 明确写过：
「如果 30 章虽然字符串唯一，但 20 章只是『布局（第1次）』『布局（第2次）』…这种形式，
不能因为 duplicate = 0 就认定质量正常。」本轮实测正是这种形式。

字段标签仍然进入正文（不是标题，而是摘要 / 目标 / 导出小节标题）：

```text
已发生：向身边人打听；这一步服务于「长期方向」
计划：试探「表层问题」；阶段目标：查清「…」并把证据整理到可呈报的程度
长期方向（前提：一名被裁员的飞船维修师发现公司在殖民地之间买卖记忆）
- 目标：长期方向（前提：…）
```

定位（只读诊断，未修改）：`settings_gen.py:475/478` 在作者只选 1 条主线方向时
把 `string "长期方向" / "阶段目标"` 直接写成主角 `goal_long / goal_stage` 的 title；
`outline_forge.py` 把这些 goal title 拼进章节 summary/goals，并被导出序列化器原样写出。
「作者只选一项」是 UI 明确允许的操作（「每一组都可以只选一项，也可以先跳过」），
因此这条路径是**正常用户操作就能走到的**，不是构造出来的边缘输入。

**结论：NF-003 = PARTIALLY RESOLVED（P2 残留）。**
可追溯性没有被牺牲：30/30 章都有结构化 `source_ids`，作者可见文本里 0 命中（§15 要求同时满足）。

---

## 13. Internal-ID / Author-Language Review

扫描方式：**8 个工作区的 DOM 扫描**由我自己重建并执行 P6 / P7 门禁（在「已锻造 30 章 + 已推演」
状态下运行）；**章节字段 / 3 本生成质量作品 / 三种导出产物**的扫描由本轮自写脚本完成
（`genqa_rereview.py`、`inspect_exports.py`、`rereview_journey.cjs`），不依赖 Repair 的结论。

扫描面：Landing / Command Center / Creation / Settings / Simulation / Characters / Locations /
Factions / Outline / Writer（导出工作区）/ Export preview / Markdown 导出 / JSON 作者字段 / DOCX。

| 目标串 | 作者可见内容命中 |
| --- | --- |
| `start_place` / `work_place` / `hidden_place` / `core_record` | 0 |
| `ev_*` / `act_*` / `faction_\d+` / `npc_\d+` / `location_\d+` | 0 |
| `protagonist` / `favors` | 0（提示语已是「人情」「主角」） |
| `future_plan:` / `source_ids`（作者文本中） | 0 |
| `来源：来源：` / `已解锁：解锁：` | 0 |
| `StoryState` / `NovelProfile` / `ContentPack`（markdown / docx 正文） | 0 |
| `StoryState` 等（JSON 的 `source` / `manifest` 字段） | 2 处（`/manifest/truth_layer_legend/occurred`、`/sections[*]/source`）——**按 §15 允许保留** |

新发现（详见 §16 NR-003）：Markdown 导出包的**角色行**仍然带着机器枚举
`（player）` / `（npc）`（势力 / 地点行没有），并且分区标题中英混排
（`Story Bible` / `Timeline` / `StorySpine` / `StoryPlanningIR`）。

来源可追溯性没有被为「0 命中」牺牲：30/30 章保留结构化 `source_ids`，
JSON manifest 保留完整结构化来源，markdown / docx 不暴露机器字段。

---

## 14. UI / UX Review

四个视口 × 5 个页面（Landing / Command Center / Creation / Outline / Export）= 20 次测量，
`scrollWidth <= clientWidth + 1` 全部成立，**0 横向溢出**；截图见
`workspace/qa_rereview_2026_09_17/shots/rr_12_viewport_*.png`。

实际观察到的好：

- 阶段轨道 + 主目标 + 唯一 Primary CTA 的「一屏一目标」结构在 1440 / 1280 / 1024 都成立；
  390 视口下侧栏变底部导航，主 CTA 仍可点。
- 状态语义不依赖颜色（完成 / 进行中 / 未开放都有图标与文字）。
- 空态、错误态、非法输入提示全部是作者语言。
- 导出工作区：格式切换（Markdown / JSON / Word）、生成、预览、下载在四视口都能操作，
  产物预览区可滚动、下载按钮可见。
- 归档确认面板在 390 视口未超屏；必须输入作品编号才能删除。
- 推演「可行方向」卡片标题已经可以完整换行（NF-015 复验）。

实际观察到的不足：

- 刷新后「确定这个方向」保持禁用（NR-001）。
- Word 产物没有内容预览（只有文件名 + 下载），与 Markdown / JSON 体验不一致（P4，见 §17）。
- 导出面板正文直接显示 `export_id：export_rr_final_…`（机器 id 出现在作者可读面板，P4）。
- 导出物分区标题中英混排（NR-003）。

---

## 15. Error / Console / Network Review

整轮真实用户旅程记录（`console_network.json`）：

```text
console.error    2
  - edge-cases: 422 POST /api/story-builder/novels        （刻意输入 `../evil` 作品编号）
  - edge-cases: 404 GET  /v3/novels/does_not_exist_at_all/command-center（刻意深链接不存在作品）
pageerror        0
requestfailed    0
其他 4xx / 5xx    0
```

两条都属于 §22 要求刻意触发的异常路径，UI 分别给出「小说编号格式不正确」与
「暂时读不到这一步 / 找不到这本小说的配置」的中文提示，**不是缺陷**。

异常路径复验结果：

| 场景 | 结果 |
| --- | --- |
| 空创意 / 空作品编号 | 前端拦截，提示「作品编号至少 3 个字符」 |
| 超长创意（1000 字上限）/ 中文 / emoji / 特殊字符 | 正常 |
| `../evil` 路径穿越编号 | 后端 422「小说编号格式不正确」，未写任何文件 |
| 双击 / 连续快速推进主 CTA | 无重复提交、无 console error |
| 伪造/清空状态下刷新（生成中刷新） | 无白屏，回到可恢复状态 |
| 直链 `tab=export`（旧链接） | **不再空白**：渲染真实面板，无裸 key |
| 不存在的作品深链接 | 优雅错误态 + 重新读取 / 回到作品列表 |
| 不存在的 workspace 路由 | 回落 Command Center |
| 不支持的 tab key | 不再显示裸 key（回落到默认面板） |

---

## 16. New Issues

> 新问题不复用 NF 编号。

### NR-001（P3 MINOR）刷新后「确定这个方向」不可点击，§10 规定的恢复流程走不通

**Module** Creation Journey / 未保存草稿（NF-010 的实现）

**Reproduction**

1. 创作工作区 → 填入一句话创意 → 点「生成方向候选」→ 得到候选（**不要**点保存）。
2. 刷新页面。
3. 观察：创意文本恢复、候选恢复、「未保存」提示出现 —— 这些都对；
   但主 CTA「确定这个方向」**是禁用状态**。

**Expected**（按本分支 §10）刷新后应当可以直接点「确定这个方向」，完成服务端保存 →
清除本地缓存 → 自动进入下一阶段。

**Actual** 本机缓存只恢复了 `idea / reference / readerExperience / suggestion`，
没有恢复 `draft.selection`；`saveBrief` 依赖 `draft`，因此按钮 `disabled`。
用户必须先点「生成方向候选 / 换一批」才能继续（`browser_journey.json`：
`{"saveDisabled": true, "selectedCandidates": 0}`，`warnings[0]`）。

**证据** `browser_journey.json` 的 `after-reload-primary-cta` 与 `warnings`；
`ui/src/v3/CreationFlow.tsx:104-117`（恢复逻辑未写入 `setDraft`）。

**影响** 不阻断主链（重新生成候选即可继续），但「刷新后直接确定方向」这条明确要求的行为失败，
并且用户会看到候选却按不了主按钮。

**建议修复方向**（本轮不修）：恢复缓存时用 `cached.suggestion.selection` 回填 `setDraft`，
或在候选已存在而 `draft` 为空时从 `suggestion.selection` 派生。

### NR-002（P3 MINOR）导出物混入与当前作品无关的 V2 历史来源分区

**Module** Export package（M16A 导出序列化 + V3 导出入口）

**Reproduction** 任意新建作品的导出工作区 → 生成 Markdown / JSON。

**Actual** 导出包固定包含 4 个与当前作品无关的分区：

```text
StorySpine        ← workspace/wasteland_001_exports/reconstruction_v2
StoryPlanningIR   ← novel/authoring/story_engine/planning/wasteland_001/index.json
Canon 事实（只读引用） ← canon/wasteland_001.sqlite
570 章 historical IR ← workspace/wasteland_001_exports/historical_chapter_ir_v1/index.json
```

并且 `historical_ir` 分区在「隔离根里并不存在这些文件」的情况下仍然有 1 条数据
（`{"chapter_count": 570, "index_digest": "89b74bfe…"}`），说明
`export_package._history_dir()` 在隔离根找不到时会回退到**仓库根**的历史数据。

**Expected** 新作者的导出物只包含这本作品自己的内容；历史 / Canon 引用分区要么不出现，
要么明确标注「本作品没有历史基础」。

**证据** `export_inspection.json`（`section_titles` 含 `StorySpine` / `StoryPlanningIR` /
`Canon 事实（只读引用）` / `570 章 historical IR`）、`json.machine_source_paths`、
markdown 正文中 `570` / `historical` / `StorySpine` / `StoryPlanningIR` 各 1 次；
`src/novelforge/story_builder/export_package.py:158-198`。

**影响** 属于交付物内容正确性问题：作者把文件交给别人时会看到另一个作品（V2 wasteland_001）
的章节计数与摘要。没有泄漏正文，也没有写入任何数据，因此定级 P3 而不是 P2。

### NR-003（P4 POLISH）导出物出现机器枚举与中英混排分区标题

**Module** Export serializer

**Actual**

- Markdown 导出包的**角色行**带着机器枚举（只有角色行有；势力 / 地点行没有）：
  `- 普通执行者（player）`、`- 掌握线索的同行者（npc）`、`- 立场摇摆的上位者（npc）`、
  `- 利益冲突的旧识（npc）`；DOCX 序列化器**没有**这个问题（同一份数据在 docx 里只输出名字）。
- 分区标题中英混排：`Story Bible` / `Timeline` / `StorySpine` / `StoryPlanningIR`
  与「角色卡片」「势力卡片」「地点卡片」并列。

**证据** `workspace/qa_rereview_2026_09_17/logs/deliverable_markdown_excerpt.txt`、
`export_inspection.json`（`raw_enum_hits: ["npc","player"]`）。

### NR-004（P4 POLISH）导出面板直接显示 `export_id`

**Actual** 导出面板产物行显示 `export_id：export_rr_final_…`（作者可见面板）。
它是合法产物标识、可用于报障，因此只作为体验项记录，是否隐藏由产品决定。

---

## 17. Remaining Product Limitations（独立判断，不照抄 Repair Report）

1. **实体真实姓名编辑（对应 NF-016）**：本轮确认 UI 侧确实给了「占位名」badge 与说明，
   但**导出物里没有这个标注**——Markdown / DOCX / JSON 的角色卡仍是
   「普通执行者 / 掌握线索的同行者 / 势力·资源控制方 / 隐藏节点」这类原型名，
   作者拿到文件后无法判断这些是不是正式名字，也无法在 UI 里改名。
   独立判断：**PARTIALLY RESOLVED（P3）**。它不影响文件生成，但影响「生成物可交付」的最后一公里。
2. **删除＝归档（对应 NF-011）**：独立核对管理面板文案为
   「删除＝把这本作品的全部产物整体归档：大纲、事实、内容包与写作草稿一起移入归档目录
   （可恢复），不会留下孤儿文件。」→ **没有**把归档伪装成永久删除，§17 的 UX 顾虑不成立。
   仍缺「归档管理 / 彻底清除」入口（产品增强，P4）。
3. **Landing 性能（对应 NF-005 的取舍）**：我把作品加到 **53 本**后实测
   （`landing_performance.json`、`extra_probes.json`）：

   ```text
   GET /api/story-builder/v3/novels   53 本 → 1,826 ms（单次请求）
   浏览器 Landing 打开（networkidle + 首卡出现）  3,106 / 2,601 / 2,482 ms
   网络调用次数   1 次 /v3/novels，0 次 command-center（没有 N+1，也没有重复昂贵投影）
   ```

   结论：**没有重复调用**，但单个列表接口承担了「全部作品的完整 journey 投影」，
   成本随作品数线性增长；53 本时打开作品列表约 2.5–3 s。这已接近「明显影响正常使用」的门槛
   （不是超时、不是卡死），我把它重新定级为 **P3（而非 Repair 报告的「可后续优化」）**，
   建议下一版加投影缓存。
4. **vite / esbuild advisory（对应 NF-019）**：`npm audit` 仍报 2 条
   （1 moderate esbuild ≤0.24.2、1 high vite ≤6.4.2），修复需要 vite@8 破坏性升级。
   README 已如实说明「只影响本地 dev server，产品以构建产物 + FastAPI 提供服务」→ 可接受。
5. **写作草稿不可编辑**：主链里「创建草稿 → 编辑 / 保存」的后半段产品没有实现
   （没有 PATCH / 编辑入口），草稿是引擎生成的 preview 文本。这是**能力边界**而非缺陷，
   但会让「作家在 V3 里写作」的预期落空，应在版本计划里明确。
6. **Word 产物没有内容预览**（Markdown / JSON 有）：体验不一致，P4。
7. **`docs/V3_FULL_PRODUCT_ACCEPTANCE.json` 与默认 pytest 口径仍不一致**（Initial Review §11 提出），
   Repair 未重新生成（它属于已发布 V3.0 的冻结 artifact）。本轮不要求，但发布证据与默认命令
   之间仍缺可复现对应关系。

---

## 18. Release Risk Assessment

（只列真实风险，不给主观分数。）

1. **生成质量风险（最高）**：章节标题虽然在字符串层唯一，但约 1/4–2/3 的章节来自同一素材 + 序号；
   摘要 / 目标里仍会写入「阶段目标」「长期方向」这类字段标签。
   由于 `settings_gen` 与 `outline_forge` 的输出同时被 legacy 面板、V3 投影、导出序列化器与
   既有测试消费，**任何后续修都会跨多个消费方**——这是下一轮最需要限制范围的地方。
2. **验收可复现性风险**：`browser_advanced_tools.cjs` 默认依赖本机不存在的作品
   `audit_fmt_55126`；`browser_v3_p0/p2/p3` 默认依赖 `novel_v3_accept_783716`。
   如果按 README 直接跑，门禁会因为「数据根里没有前置作品」而 FAIL，而不是因为产品缺陷。
   需要把这些前置作品显式化（seed 脚本或门禁自造）。
3. **门禁盲区残留（NF-020 未完全消除）**：P6 的「Creation 主链」在锻造大纲时用的是
   **内部 HTTP API**（`POST /outline/forge` + `/outline/confirm`），而不是 UI；
   因此「legacy 大纲锻造面板在 V3 里真的可点」这件事只有本轮的人工复验覆盖，
   自动化门禁里仍然没有断言。这与 Initial Review 「门禁 PASS 但产品 FAIL」的模式是同一类风险。
4. **导出物来源污染风险（NR-002）**：导出包会引用 `wasteland_001` 的历史 / Canon 分区，
   在开发机上会带上 570 章的计数与摘要。产品若被真实作者使用，交付物里会出现别人的作品元数据。
5. **测试与文档口径风险（NF-018）**：README 的类型检查命令不生效，
   意味着「照文档做发布检查」会得到假阴性；这类问题容易在后续版本继续被复制。
6. **Landing 线性增长风险（§17.3）**：作品数继续增长时列表页耗时线性上升，目前无缓存。
7. **数据安全风险：无**。本轮所有写操作都在隔离根；legacy writer 目录未被改写；
   归档删除可恢复并写 manifest；未发现路径穿越、XSS、孤儿文件。

---

## 19. Final Acceptance Checklist

**启动与基础**

| 项 | 结果 |
| --- | --- |
| 服务启动 + `/api/health` | PASS |
| `npm.cmd --prefix ui install` / `npm.cmd run build --prefix ui` | PASS |
| `.venv\Scripts\python.exe -m pytest -q` 全绿 | PASS（889 / 0 failed） |
| `scripts/validate_project.py` | PASS |
| README 文档命令 `npm.cmd --prefix ui exec tsc -- --noEmit` | **FAIL**（exit 1，只打印帮助） |
| 在 `ui/` 下 `npm exec tsc -- --noEmit` | PASS |

**核心链路（全新隔离数据根，真实浏览器）**

| 项 | 结果 |
| --- | --- |
| 空数据根 → 新建作品 → 创意 → 候选 → 确定方向 → **面板自动进入设定** | PASS |
| 设定候选 → 保存 → 自检（通过）→ 开始推演 | PASS |
| 推演 60 次：主 CTA 永远可执行；不再出现 `favors` / `protagonist` | PASS（60 次全 200） |
| 大纲：锻造 30 章 → 确认 | PASS（走 legacy 面板真实点击） |
| 大纲：30 章标题字符串唯一 | PASS |
| 大纲：30 章标题不含「阶段目标 / 长期方向 / （规划）」字段标签 | PASS |
| 大纲：**语义不重复**（§13 要求） | **FAIL**（19/30 为同一素材 + 序号） |
| 大纲：再推演一次 → 正确提示「需要重新锻造」，导出文案一致 | PASS |
| 检查工作区可读、无内部 id | PASS |
| 导出工作区主 CTA 进入后内容非空 | PASS |
| UI 内创建写作草稿 →「已有写作草稿」完成 → 进度 > 44% | PASS（47%，1/1） |
| Markdown / JSON / Word 真实生成 + 真实下载 + 可读 + 非 0 字节 | PASS |
| 导出物作者可见内容 0 内部实体 id | PASS |
| 导出物无「来源：来源：」等重复前缀 | PASS |

**一致性与边界**

| 项 | 结果 |
| --- | --- |
| Landing 卡片 vs Command Center：阶段 / 阶段名 / 进度 / 下一步 / CTA（4 状态） | PASS |
| 刷新 / 新上下文 / 重启服务后数据一致 | PASS |
| 空输入 / 超长 / 中文 / 空格 / `../` / emoji：不崩、不白屏、不穿越、有中文提示 | PASS |
| 连点主 CTA：无重复提交、无 console error | PASS |
| 4 视口（1440 / 1280 / 1024 / 390）：0 横向溢出、主 CTA 可达 | PASS（20 次测量） |
| 旧链接 `tab=export` 不再空白 | PASS |
| 刷新后可直接点「确定这个方向」（§10） | **FAIL**（NR-001） |

**门禁**

| 项 | 结果 |
| --- | --- |
| P0 / P2 / P3 / P4 / P5 / P6 / P7 / foundation / visual / advanced 全 PASS | PASS |
| P6 在「已锻造大纲 + 已推演」状态下扫描内部 id | PASS |
| 导出 CTA 之后断言内容非空 | PASS（P5 / P7） |
| 新增断言：章节标题唯一、Landing 与 Command Center 一致、writer 读写同源 | PASS |
| 门禁可脱离本机历史数据独立复现 | **PARTIAL**（P0–P3 需要预置作品；见 §18.2） |

---

## 20. Final Conclusion

> **NovelForge V3 当前版本是否已经能够让普通用户稳定地完成从创意到写作，再到真实导出文件的
> 完整创作过程？**

**能完成，但不是全程「可交付质量」。**

- 流程层面：**可以**。全新数据根、真实浏览器、真实下载，从 Landing 到 Markdown / JSON / Word
  文件全部跑通；Writer 与 Export 两条曾经的 P1 断链都已打通并有磁盘证据；
  刷新、切换、新上下文、重启后端都不丢数据；4 视口无溢出；异常输入不崩不穿越。
- 交付层面：**还不够**。30 章里约 19 章是「同一个行动名 +（第 N 次）」，
  摘要里写的是「阶段目标：…」「这一步服务于「长期方向」」这类字段标签，
  人物 / 地点 / 势力在导出物里仍是原型名，导出包还会带上与这本作品无关的 V2 历史分区。
  也就是说：**现在可以交付一份结构清晰的大纲蓝图，还不能交付一份可以直接照着写的章节素材。**

因此最终判定为 **PASS WITH ISSUES**，并且明确列出：

- REGRESSED：**无**（没有任何原问题比 Initial Review 时更差）。
- PARTIALLY RESOLVED：**NF-003（P2）**、**NF-006（P3）**、**NF-010（P3，见 NR-001）**、
  **NF-016（P3）**、**NF-020（P3）**。
- NOT RESOLVED：**NF-018（P4）**。
- 新增问题：**NR-001（P3）**、**NR-002（P3）**、**NR-003（P4）**、**NR-004（P4）**。

下一轮如果只允许做一件事，建议做 **NF-003 的语义化收尾**：
让章节标题真正由「人物 / 目标 / 冲突 / 转折」派生，而不是「同一素材 + 序号」，
并让 `阶段目标` / `长期方向` 这类标签退出作者可见正文。

---

## 附：QA Evidence

```text
workspace/qa_rereview_2026_09_17/
├─ root_gates/ · root_ui/                 浏览器门禁用的隔离数据根（port 8030 / 8035）
├─ root_final2/                           用户主链隔离数据根（port 8048，含 30 章大纲与写作草稿）
├─ root_genqa/                            生成质量隔离数据根（3 本 × 30 章，port 8050）
├─ root_extra/                            一致性 / 性能隔离数据根（53 本作品，port 8051）
├─ root_journey…root_journey7/            主链脚本迭代过程中的中间数据根
├─ logs/
│   ├─ pytest_baseline.txt                889 passed / 687 deselected
│   ├─ validate_project.txt               PASS
│   ├─ ui_build.txt                       vite build PASS
│   ├─ probe_outline_labels.txt           字段标签复现（1 条 / 2 条主线方向两种情况）
│   ├─ exhaustion_probe.txt               60 次推演全部 200
│   ├─ extra_probes.txt                   legacy fallback / 4 状态一致性 / Landing 性能
│   ├─ export_inspection.txt              markdown / json / docx 产物内容检查
│   ├─ deliverable_markdown_excerpt.txt   导出 Markdown 前 70 行（人工阅读）
│   ├─ deliverable_docx_excerpt.txt       导出 Word 正文前 70 行（人工阅读）
│   └─ restart_before.json                重启后端前的状态快照
├─ shots/                                 rr_01…rr_14 全流程截图（含四视口与失败态）
├─ downloads/                             真实下载的 Markdown / JSON / Word 产物
├─ browser_journey.json                   72 个检查点（0 失败）+ 新问题记录
├─ console_network.json                   console / pageerror / requestfailed / 4xx
├─ generation_quality.json                3 本 × 30 章生成质量统计
├─ probes_report.json                     NF-011/012/013/015/017 复验
├─ extra_probes.json                      legacy writer / 4 状态一致性 / Landing 性能
├─ export_inspection.json                 产物分区、英文标题、枚举、编号统计
├─ exhaustion_probe.json                  推演可执行性（60 周期）
├─ landing_performance.json               Landing 浏览器加载成本（53 本作品）
└─ *.py / *.cjs                           本轮全部复验脚本（只读产品，不修改产品）
```

未覆盖 / 本轮未运行：

- `pytest -m historical_acceptance`（687 项）按仓库规则默认不运行，本轮同样未运行，
  以免触碰本机历史验收数据；
- 真实 LLM provider 路径（产品未接入，NF-007 已按「明确降级承诺」处理）。

> 本报告不修改任何业务代码、UI、提示词、生成算法或测试；发现的全部问题都留给下一个分支处理。
