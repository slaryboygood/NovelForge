# 变更记录（Release History）

本文件只记录**已发布的版本**。开发过程（每日提交、里程碑执行记录、中间状态）保存在
Git history 中，不再在仓库里保留副本。

---

## NovelForge V3 Final — Functional Closure

```text
release_date   = 2026-09-17
release_tag    = novelforge-product-v3-final
history_shape  = 单一 root commit（main = v4 = V3 Final root）
acceptance     = PASS WITH ISSUES（docs/CURRENT_PRODUCT_FINAL_REREVIEW.md）
```

V3 的**功能开发到此冻结**：Creation / Settings / Simulation / Outline / Writer / Export
主链可用，核心闭环有真实浏览器与真实导出物证据。

冻结同时完成一次仓库基线迁移：

- 活动仓库只保留一个 release ref（`novelforge-product-v3-final`），
  V3 Final 成为 V4 的唯一历史起点；
- 旧 release（`novelforge-product-v3.0` / `novelforge-product-v2.0` / `story-engine-v2.0`
  及其他开发期 tag）已归档：**historical / archived / not an active Git ref**，
  完整历史由外部 bundle `NovelForge_pre_V4_full_history.bundle` 承载；
- 冻结机制由「Git tag / historical commit 必须可解析」迁移为
  「tracked frozen evidence + 加密摘要 manifest」（`docs/FROZEN_EVIDENCE_MANIFEST.json`，
  守卫 `tests/test_v2_frozen_guard.py`）。

遗留的生成质量与质量闭环问题全部转入 V4，清单见 `docs/V3_FINAL_FREEZE.md`。

---

## NovelForge Product V3.0

```text
release_date   = 2026-09-16
release_tag    = novelforge-product-v3.0   （historical / archived / not an active Git ref）
release_commit = 20d03cfa78b458e18e385fdaf58a04e3f2bde1c3
V2 base        = novelforge-product-v2.0（56cda829d812d95f65cb282e0c85328792f6d9cd；
                 historical / archived / not an active Git ref）
```

### 产品能力

- **Novel Landing**：游戏式存档选择。继续创作为主 CTA；作品卡显示真实封面、阶段、进度与下一步。
- **Command Center**：作品视觉名片（Hero）+ 作者旅程（Stage Track）+ 当前目标 + 下一步 + 风险，
  全部来自应用层投影，不含硬编码数字。
- **Creation Journey**：一句话创意 → 候选 → 选择 → 设定候选 → 设定自检 → 开始推演；
  可前进、可回退、可补设定。
- **Objective / Next Action**：应用层派生状态；完成度只来自真实 state / validation /
  deterministic rules，LLM 不决定完成与否。
- **Character / World Workspace**：角色、地点、势力实体工作区（视觉 + 定位 + 关系 + 空态）。
  完整编辑仍通过既有面板（accepted bridge）。
- **Simulation Workspace**：STATE A/B/C/D 差异化；真实候选方向；V3 Native 路线比较；
  世界影响只认真实实体引用（不做关键词猜测）。
- **Outline & Chapter Workspace**：四级结构（全书 / 卷 / 篇章 / 章纲）+ 缺口 + 警告 +
  大纲过期重锻；章节卡带视觉与所属篇章。
- **Review / Repair / Export**：INFO / WARNING / BLOCKING 分级；修复用作者语言说明
  「问题 → 为什么重要 → 能否自动修 → 是否可逆」；导出就绪度说明「还缺什么 / 会导出什么」。
- **Advanced Tools**：既有能力保留为 contextual / advanced bridge（19 页签，含 legacy 面板）。

### 架构

- 严格分层：**Domain → Application → ViewModel → UI**。UI 不解析 StoryState / Canon，
  不计算 stage 或 objective 完成度。
- V3 UI（`ui/src/v3/`）通过应用层只读投影（`src/novelforge/story_builder/v3_projection.py`）取数；
  没有第二套 Route / Simulation / Outline / Relationship Domain。
- 单一解析入口：URL 路由、EntityVisual、Objective / NextAction / EmptyState / ContextPanel
  各自只有一个实现。
- 风险模型统一为 INFO / WARNING / BLOCKING，只有真正阻止继续的问题才升级为 BLOCKING。

### Visual Asset System

- 解析链固定为 **real story asset → product default artwork → semantic icon**，
  由 `artworkManifest.ts` 单一入口管理，组件不保存图片路径。
- 6 个 required 默认美术随 release 发布（封面 / Hero / 角色 / 地点 / 势力 / 章节），
  容器尺寸由布局决定（无 CLS）；图片失败回退语义图标（无 broken image / 无空白卡）。

### Responsive / Accessibility

- 1440 / 1280 / 1024 / 390：0 横向溢出，Primary CTA 可达。
- ContextPanel：`role="dialog"` / `aria-modal` / Esc 关闭 / 焦点进入与返回 / Tab 焦点陷阱；
  重要状态不只依赖颜色。

### 测试与验收

```text
pytest                1559 passed / 1 skipped（release candidate 快照）
validate_project      PASS
tsc --noEmit          PASS
UI build              PASS
browser acceptance    P0 / P2 / P3 / P4 / P5 / P6 + advanced tools + Visual Asset Gate 全部 PASS
四视口                1440 / 1280 / 1024 / 390；0 pageerror / 0 requestfailed / 0 console error /
                      0 非预期 4xx / 0 横向溢出 / 0 broken image
```

证据（SSOT）：`docs/V3_FULL_PRODUCT_ACCEPTANCE.json`。

### Known issues / Known Debt（非阻塞，属后续版本候选）

```text
V3-DEBT-01  V2 里程碑验收（M11–M18 / wasteland）依赖本机历史数据，默认不运行
            （pytest -m historical_acceptance 显式运行）
V3-DEBT-02  默认美术整体偏 Dark Fantasy；建议后续按题材提供 fallback pack
V3-DEBT-03  Character / World 完整编辑仍通过既有面板（accepted bridge）
V3-DEBT-04  relationship change history 尚未进入 Primary UI
V3-DEBT-05  合成 id（core_record / 资源 / 身份）的展示名由应用层显式表提供
V3-DEBT-06  Story-specific artwork generation 尚未实现（Domain 尚无 artwork 字段）
```

### 仓库清理（2026-09-17，release hygiene）

发布之后做了一次仓库整理（不改产品行为）：删除开发期 milestone 报告与一次性迁移脚本、
清理浏览器验收截图与本地测试数据根、把历史里程碑验收以 `historical_acceptance` 标记隔离、
新增自包含 `V2 Frozen Guard`（`tests/test_v2_frozen_guard.py`）、把本文件收敛为 release history。
产品代码、6 个正式视觉资源与全部当前产品测试保持不变；release tag 未移动。

### V3 Acceptance Repair（2026-09-17，分支 `codex/product-v3-game-ui`）

独立产品验收（`docs/CURRENT_PRODUCT_ACCEPTANCE_REVIEW.md`）判定 V3.0 **FAIL**：
核心闭环（导出给写作环节）不可达、生成内容大面积字段占位、入口页与作品内状态不一致。
本分支按验收报告的依赖顺序修复，**不新增产品功能版本**，release tag / release commit 未移动。
完整修复记录见 `docs/CURRENT_PRODUCT_ACCEPTANCE_REPAIR_REPORT.md`。

```text
NF-001 导出工作区主 CTA 落到不存在的 legacy 页签（空白页）
       → 导出能力进入 V3 工作区本身（真实产物：文件名 / 内容预览 / 下载）
NF-002 写作草稿写入路径与投影读取路径不一致（writer_drafts 恒为 0）
       → 统一 canonical writer store；UI 可创建草稿；导出阶段可完成
NF-003 章节标题是字段标签占位（22–24 / 30 同名）→ 内容化标题 + 唯一性质量门禁
NF-004 内部 id（start_place / ev_* / future_plan:* / favors / protagonist）进入作者内容
       → 唯一「内部标识 → 作者语言」映射层（引擎生成 / 投影 / 导出 / 错误文案共用）
NF-005 Landing 卡片与 Command Center 有两套阶段 / 进度 → 单一 journey 投影
NF-006 内容包标题被截断并带「（设定草稿）」→ 取创意首个完整短句
NF-007 文档承诺模型能力但产品路径未接入 provider → 文档与行为对齐（本地规则生成）
NF-008 资源耗尽后主 CTA 仍推同一 422 行动 → 只推荐可执行方向 + 作者语言错误文案
NF-009「确定这个方向」不推进向导 → 保存后自动进入设定步骤
NF-010 创意草稿不落盘 → 本机缓存 + 明确的「还没有保存」提示
NF-011 作品无法重命名 / 删除 → 重命名 + 整体归档式删除（二次确认、可恢复、无孤儿）
NF-012 导出文案自相矛盾（「还差 0 步」）→ blocker 优先文案
NF-013「控制方 控制方未知」→ 值层去掉重复前缀
NF-014 高级工具显示裸 tab key → 未知页签回落到默认面板
NF-015 方向名被截断 → 允许两行显示
NF-016 角色 / 地点 / 势力只有原型名 → 显式标注「占位名」
NF-017「已解锁：解锁：」→ 前缀只加一次
NF-018 README 的 tsc 命令不执行类型检查 → 改为 `npm --prefix ui exec tsc -- --noEmit`
NF-019 vite / esbuild advisory 只影响本地 dev server → README 说明
NF-020 浏览器门禁盲区 → 新增 P7 回归门禁 + P5/P6 收紧（锻造后扫描 / 导出产物 / 草稿闭环
       / 入口一致性 / 标题唯一性）
```

测试与浏览器门禁全部保持 PASS，并新增 `tests/browser_v3_p7_acceptance.cjs` 与
`tests/test_acceptance_repair_regressions.py`。修复前，这些断言在旧代码上必然 FAIL
（见修复报告第 6 节的 before / after 证据）。

---

## NovelForge Product V2.0

```text
release_date   = 2026-09-15
release_tag    = novelforge-product-v2.0   （historical / archived / not an active Git ref）
release_commit = 56cda829d812d95f65cb282e0c85328792f6d9cd
M0–M18         = COMPLETE
```

通用小说创作产品链：**创意 → 设定 → 设定自检 → 推演（StoryState）→ 路线试演 → 四级大纲 →
导出（Planning Export）→ Writer context / 草稿 / 事实提议**，外加 2D 可视化、
Canon 检查器、修复中心，以及跨题材复用（3 题材验证）。

数据权威分层（`occurred` / `planned` / `historical_repair` / `preview` / `ui_derived`）
与 frozen boundary（Canon、StoryState 基线、M11/M12 repair freeze、Contract、Gate）在本版本冻结。

详见 `docs/NOVELFORGE_PRODUCT_V2_RELEASE.md` 与 `docs/LEGACY_COMPAT.md`；
V2 的字节级验收证据在本机 `workspace/wasteland_001_exports/repair_adoption_v1/m18/`（不进版本控制）。

---

## Story Engine / V1（历史摘要）

V2 之前完成了 Story Engine 的领域基础：StoryState 与 action / condition / effect 模型、
事件与伏笔、成长树、路线（route）与分支、四级大纲、Canon 基础设施与冲突防御、
Planning IR / Chapter IR、以及真实长篇（WASTELAND_001 / 570 章）的迁移与历史修复。

这些阶段的执行报告、逐日进度与中间结论不再保留在仓库中，需要时通过 Git history 查阅。
