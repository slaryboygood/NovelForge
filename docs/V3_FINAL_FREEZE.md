# NovelForge V3 Final — Freeze Manifest

## Version

NovelForge V3 Final

## Status

Functional Closure

> V3 的**功能开发到此冻结**。从这一刻起，V3 代码只接受缺陷修复级变更；
> 任何新能力、生成质量改造、质量闭环、工具集成都进入 V4。

## Acceptance

PASS WITH ISSUES

依据（本仓库内三份独立记录）：

| 阶段 | 文档 | 结论 |
| --- | --- | --- |
| Initial Acceptance Review | `docs/CURRENT_PRODUCT_ACCEPTANCE_REVIEW.md` | **FAIL** |
| Repair | `docs/CURRENT_PRODUCT_ACCEPTANCE_REPAIR_REPORT.md` | READY FOR RE-REVIEW |
| Final Independent Re-review | `docs/CURRENT_PRODUCT_FINAL_REREVIEW.md` | **PASS WITH ISSUES** |

冻结时的验收事实（最终独立复验，详见 `docs/CURRENT_PRODUCT_FINAL_REREVIEW.md`）：

```text
核心 E2E（全新隔离数据根 / 全新作品 / 真实浏览器）      通过（72 个检查点，0 失败）
Writer（草稿创建 → 投影可见 → 导出阶段完成 → 进度上升）  通过
Export（Markdown / JSON / Word 真实生成 + 下载 + 可读）  通过
持久化（刷新 / 新上下文 / 切换作品 / 重启后端）          通过
Landing 与 Command Center 一致性（4 种边界状态）          通过
四视口（1440 / 1280 / 1024 / 390）                        0 横向溢出
pytest -q                                                 889 passed / 687 deselected / 0 failed
validate_project.py                                       PASS
ui build（tsc -b && vite build）                          PASS
typecheck（`cd ui; npx tsc --noEmit`）                    PASS
浏览器门禁 P0/P2/P3/P4/P5/P6/P7 + foundation + visual + advanced  PASS
```

## Core Capabilities

以下能力在冻结版本中**可用并已被真实浏览器验证**：

**作品与流程**

- 作品创建（Landing → 新建作品）、作品列表、作品切换
- 作品重命名（PATCH，只改 `NovelProfile.title`，不动事实）
- 作品删除＝整体归档（二次确认 + `ARCHIVE_MANIFEST.json`，可恢复、不留孤儿）
- Author Journey 8 阶段单一状态源：Landing 卡片与 Command Center 完全一致
- 主目标 / 下一步 / 唯一 Primary CTA 的「一屏一目标」工作台

**创作链（Creation）**

- 一句话创意 → 题材 / 内容包 / 基调 / 卖点候选（本地确定性规则生成）
- 未保存草稿的本机缓存 + 明确「还没有保存」提示
- 「确定这个方向」服务端保存并自动推进到设定步骤
- 9 组设定候选（世界规则 / 主角 / 重要角色 / 势力 / 关系 / 成长 / 矛盾 / 主线 / 伏笔）逐组选择
- 设定自检（起点可运行性检查）

**推演（Simulation）**

- 起点事实落盘（StoryState，tick 0 / revision 0）
- 行动候选可用性判定与主 CTA 推荐同源
- 连续推演（实测 60 个周期全部可执行）、推演反馈、世界变化与关系 / 代价记录

**大纲（Outline）**

- 四级大纲锻造：全书主线 → 卷纲 → 篇章纲 → 详细章纲（3 卷 × 2 篇章 × 5 章 = 30 章）
- 大纲预览 / 重新锻造 / 整条确认 / 来源一致性（stale）检测
- 章节标题唯一性 + 质量门禁 findings
- 大纲导出（Markdown / JSON / DOCX）与结构树 / 联动面板

**检查与修复（Review）**

- 故事问题清单（作者语言、INFO / WARNING / BLOCKING）
- Canon 检查器、修复中心入口
- 导出就绪度 6 步（内容包 / 起点事实 / 自检 / 大纲确认 / 章纲就绪 / 写作草稿）

**写作与导出（Writer / Export）**

- 写作草稿创建（canonical 存储 `novel/authoring/story_engine/writer/<novel_id>/`）
- 写作草稿投影可见、导出阶段可完成、刷新与重启后仍在
- legacy writer 目录只读兼容（不迁移、不重写、不重复计数）
- 导出包生成与真实下载：Markdown / JSON / Word（文件名 + export_id + 预览 + 下载）
- 作者语言层：`src/novelforge/author_language.py` 统一内部标识 → 作者语言映射

**工程与验收**

- 全量 pytest 套件（889 默认 / 687 historical_acceptance 隔离）
- `scripts/validate_project.py` 工程校验
- 浏览器验收门禁 P0–P7 + UI foundation + Visual Asset Gate + Advanced Tools
- 隔离数据根启动脚本 `scripts/creator_ui_test_server.py`

## Known Issues Deferred to V4

以下问题**在 V3 Final 中不修**，整体转入 V4。它们不影响「功能闭环」，影响的是
生成质量与质量闭环。

| 编号 | 级别 | 问题 | 影响 |
| --- | --- | --- | --- |
| NF-003 | P2 | 章节标题字符串唯一但语义重复：同一素材 + 「（第 N 次）」；`阶段目标` / `长期方向` 字段标签仍进入摘要与导出正文 | 导出物是结构蓝图，不是可直接照写的章节素材 |
| NF-006 | P3 | 内容包标题在长首句时仍被硬截断（不在标点处收尾） | 作品名可读性 |
| NF-010 / NR-001 | P3 | 刷新后恢复了创意与候选，但没有恢复已选方向，「确定这个方向」保持禁用 | 未保存草稿的恢复流程不完整 |
| NF-016 | P3 | 角色 / 地点 / 势力只有原型占位名，且导出物没有「占位」标注；无真实姓名编辑 | 交付物最后一公里的可用性 |
| NF-018 | P4 | README 记录的 `npm.cmd --prefix ui exec tsc -- --noEmit` 不执行类型检查（只打印帮助，exit 1） | 发布检查会得到假阴性 |
| NF-020 | P3 | 门禁盲区仅部分消除：P6 的大纲锻造仍走内部 API，不是 UI；门禁依赖未随仓库提供的前置作品数据根 | 可能再次出现「门禁全绿但产品有问题」 |
| NR-002 | P3 | 导出包固定包含与当前作品无关的 V2 分区（StorySpine / StoryPlanningIR / Canon 事实 / 570 章 historical IR） | 交付物内容正确性与可信度 |
| NR-003 | P4 | Markdown 导出包角色行带机器枚举 `（player）` / `（npc）`；分区标题中英混排 | 交付物文案一致性 |
| NR-004 | P4 | 导出面板正文直接显示 `export_id` | 作者可读性 |
| — | P3 | Landing 复用完整 journey 投影后列表成本随作品数线性增长（53 本实测：单接口 1.8 s，浏览器打开 2.5–3.1 s） | 作品多时的入口体验 |
| — | P4 | 写作草稿不可编辑（无 PATCH / 编辑入口），草稿由引擎生成 preview 文本 | 「在 V3 里写作」的预期落空 |
| NF-019 | P4 | vite / esbuild dev 依赖 advisory（1 moderate / 1 high），需 vite@8 破坏性升级 | 仅本地 dev server |
| — | P4 | `docs/V3_FULL_PRODUCT_ACCEPTANCE.json` 的测试口径与仓库默认 pytest 命令不一致 | 发布证据可复现性 |

### 明确说明

- 这些是**已知且已记录**的缺陷，不是未知风险；V3 Final 以「功能闭环」交付，而不是以
  「生成质量闭环」交付。
- 本轮冻结**不修**任何上述问题（用户指令：V4 再处理）。
- V3 Final 的验收结论就是 **PASS WITH ISSUES**，任何后续发布说明不得把它改写成 PASS。

## V4 Direction

V4 在 V3 Final 的 clean root 之上开始，方向明确：

1. **MCP**：把 NovelForge 的能力以 MCP 形式对外暴露（工具 / 资源 / 提示），
   让外部 agent 可以驱动创作流程。
2. **plugins**：插件化扩展点（内容包 / 题材模板 / 生成器 / 校验器 / 导出器），
   避免把新能力硬编码进核心。
3. **quality architecture**：把「生成质量」从散落的门禁升级为架构级能力
   （质量层、质量契约、质量证据链）。
4. **generation quality loop**：生成 → 评估 → 反馈 → 重生成的闭环，
   首先是 NF-003 的语义化章节标题与字段标签退出正文。
5. **delivery quality validation**：交付物（Markdown / Word / JSON）的独立质量校验，
   包含来源归属性（NR-002）、语言一致性（NR-003）、可追溯性。
6. **automated evaluation**：自动化评估体系，使「门禁全绿但产品有问题」（NF-020）不再可能，
   并覆盖 Writer 草稿编辑、Landing 投影性能等能力边界。

## Freeze Reference

```text
版本冻结文档     docs/V3_FINAL_FREEZE.md（本文件）
仓库冻结报告     docs/V3_FINAL_REPOSITORY_FREEZE_REPORT.md
验收记录         CURRENT_PRODUCT_ACCEPTANCE_REVIEW / REPAIR_REPORT / FINAL_REREVIEW
新历史起点       NovelForge V3 Final — Functional Closure（单一 root commit）
唯一活动 tag     novelforge-product-v3-final
冻结机制         tracked frozen evidence + 加密摘要 manifest
                 （docs/FROZEN_EVIDENCE_MANIFEST.json；守卫 tests/test_v2_frozen_guard.py）
已归档 release   novelforge-product-v3.0 / novelforge-product-v2.0 / story-engine-v2.0
                 → historical / archived / not an active Git ref
                 完整历史：外部 bundle NovelForge_pre_V4_full_history.bundle
```

> 本清单只描述 V3 Final 的冻结状态与遗留项，不修改任何产品行为。
