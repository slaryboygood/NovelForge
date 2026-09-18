# V4-10 STORY STUDIO UI RESULT

> 阶段：**V4-10 Story Studio UI**　状态：**PASS**　日期：2026-09-18
> 分支：`v4-10-story-studio-ui`　契约：[V4_UI_CONTRACT.md](V4_UI_CONTRACT.md)（SSOT）
> 盘点：[V4_10_UI_INVENTORY.md](V4_10_UI_INVENTORY.md)　过程记录：[V4_10_STORY_STUDIO_STATUS.md](V4_10_STORY_STUDIO_STATUS.md)（SUPERSEDED）

## 1. Existing UI inventory

`docs/v4/V4_10_UI_INVENTORY.md`：扫描 `ui/src/**`（55 文件 / ~10.5k LOC）、
`src/novelforge/api/**`（~90 个 legacy 端点 + V4-06/07/08 端点）、
`tests/browser_*.cjs`（20 个门禁）、`ui/package.json`，逐条给出
`Existing UI → Backend → V4 Action → Target`。

## 2. Visual standard analysis

`UI标准.*` **在仓库根目录不存在**（按扩展名检索只命中 `ui/src/assets/defaults/*`；
`docs/CURRENT_PRODUCT_ACCEPTANCE_REVIEW.md` 在 V3 阶段已记录同一事实并裁定：
视觉基准 = 产品 Design System + 6 个 release 默认美术 + 四视口渲染）。
V4-10 因此以既有 Design System（`ui/src/v3/design-system/`，tokens.css 记录了
它来自 `UI标准` 的方向：深色电影感 / 低噪声 / 暖金强调 + 青绿进度）为
PRIMARY VISUAL REFERENCE，并在 UI Contract §2 列出**采用项**（卡片优先、语义图标、
状态=icon+text+shape、ContextPanel、6 默认美术、三态）与**调整项**（导航收敛为 6+3、
Studio 专属版式、场景卡正面突出 story_function、Quality 不显示总分、插件页只读）。
没有建立第二套主题。

## 3. Story Studio architecture

`ui/src/studio/**`：`StudioApp`（壳 / 路由 / 数据加载 / 通知 / 快捷操作）+
`workspaces/*`（Overview / NodeWorkspace 通用工作区 / Quality / Delivery / Plugins）+
`NodeDrawer`（编辑器抽屉）+ `components.tsx`（卡片 / 抽屉 / Diff / issue / 父节点选择 /
通知 / 长操作）+ `design/*`（status / errors / fields / parents）。

## 4. Information architecture

创造 → 世界 → 人物 → 故事 → 场景 → 检查（6 主）+ 交付 / 插件 / 项目设置（辅助）；
一级导航 ≤ 9；每屏突出主按钮 ≤ 3；高级字段（原始字段、诊断码、checksum、provenance）
默认折叠。

## 5. Navigation

hash 深链接：`#/studio`、`#/studio/n/<id>[/<view>[/<entity>]]`，
覆盖 novel / character / chapter / scene / quality issue / delivery snapshot；
Back / Forward / Reload 可用（`nav.test.ts` 冻结解析与往返）。

## 6. Design system

复用 tokens（颜色 / 间距 / 圆角 / 字体 / 动效）+ 语义图标注册表 + primitives
（Card / Button / Badge / EmptyState / LoadingState / ErrorState / Disclosure）；
新增 `studio.css` 只做版式，不引入新主题；无 emoji 主图标。

## 7. Status system

`UI_STATUS_MAP` 单表覆盖 blueprint / quality / review / setup·payoff / delivery /
repair / plugin 状态：同一状态 = 同一图标 + 文案 + 色调 + 形状；
未登记状态原样显示（不猜 PASS/FAIL）；`passed` 与 `accepted` 明确区分
（Quality PASS ≠ Author Accepted）。

## 8. Studio overview

作品名 / Blueprint 计数与接受数 / 质量门禁进度（Q0–Q9，无总分）/ 待处理问题 /
伏笔未回收警告 / 交付状态与最近快照 / 推荐下一步（来自 journey 投影）+ 快捷动作。

## 9. Creation workspace

前提与主题卡片；生成前提 / 主题（proposal → 作者接受）；
字段以作者语言呈现（核心冲突 / 戏剧问题 / 故事承诺 / 约束）。

## 10. World workspace

世界规则 / 地点 / 势力 / 资源 / 技术·魔法 / 与故事相关的历史；
区分「AI 建议（proposed）」与「已接受」状态徽章。

## 11. Character workspace

人物卡（名字 / 身份 / 目标 / 动机 / 冲突 / 缺陷 / 恐惧）+ 人物弧卡
（起点 → 内在冲突 / 外部压力 → 转折 → 危机 → 关键选择 → 终点）。

## 12. Story workspace

故事弧 → 结构单元（幕 / 卷 / 弧由数据决定，不写死三幕）→ 章节卡；
章节卡显示目标 / 冲突 / 转折 / 结果 / 钩子与版本、状态。

## 13. Chapter cards

`NodeCard` 按 `chapter` 字段词典渲染；点击进入编辑器抽屉；卡片显示版本与状态徽章。

## 14. Scene workspace

按章节分组（可折叠），每张 Scene Card **正面**显示「这场戏的作用：推进主线、揭示信息…」
（story_function 不藏在高级字段）；另显示 POV / 地点 / 时间 / 目的 / 冲突 / 转折 /
结果 / 下一个钩子。

## 15. Editor workflow

字段级 patch（只提交改动字段 + `expected_revision`）→ 保存创建新版本 →
Diff（before/after）→ 接受 / 拒绝；历史（revision / 作者 / 操作 / 时间 / 改动字段）+
查看差异 + 恢复此版本（文案明确「以该内容创建新版本，历史不会删除」）。

## 16. Revision / diff

Diff 全部来自 `GET /editor/nodes/{id}/diff`（后端 deterministic diff）；
前端只做展示（before/after 两列），不自行判断业务差异；无差别时显示明确空态。

## 17. AI rewrite

选择字段 + 输入要求 → **生成改写预览（dry-run，不写入）** → 展示 before/after →
「应用这次改写（创建新版本）」/ 放弃；应用后进入待审核状态（proposed），
由作者接受或拒绝。

## 18. Accept / reject

抽屉底部固定「拒绝 / 接受」两个显式动作（非 hover / 右键 / 快捷键）；
接受与质量通过是两件独立的事（文案与徽章均区分）。

## 19. Quality Center

Q0–Q9 门禁面板（点击按 gate 过滤）+ 报告状态 + 问题列表（默认只显示作者关心的信息）；
不显示总分；问题卡 = 人类文案 + 严重度 + 影响节点数 + 诊断码；
issue 详情含 evidence（kind / explanation / excerpt / metric）与可折叠诊断信息
（issue code / evaluator / provenance）。

## 20. Repair workflow

选中问题 → 「修复预览」（dry-run）：将修改哪些节点 / 允许改哪些字段 / 必须保留 /
修复后复核哪些 gate / 预计模型调用 → 确认后执行 → 自动复核；
`needs_human_review` 显示为「需要作者决定」（附原因），不是 crash。

## 21. Delivery UI

选择依据（accepted 默认 / current）+ 接受与质量要求 + 格式（来自
`GET /studio/delivery/formats`，**包含插件 exporter 的 tlist**，前端不写死 4 种）→
preflight → 交付 → manifest / 快照 id / artifact 列表 / 下载（checksum 在高级详情）。
被阻止时展示后端 blocker 原因（含稳定 code）并给出「去检查」导航，不提供正式下载。

## 22. Plugin UI

只读：trust model + 权限人类文案 + 插件列表（name / plugin_id / version /
description / capabilities / permissions / status / compatibility / error /
approved_version）；**不提供** enable / disable / install / marketplace / 配置编辑
（V4-09 operator boundary 未开放）。文案明确「权限控制 NovelForge Host API 能力，
不是操作系统安全沙箱」，且不出现虚假的沙箱承诺。

## 23. Error / conflict UX

`STUDIO_ERROR_MESSAGES` 覆盖 30+ 稳定 code（冲突 / 质量问题 / 插件 / 生成不可用 …）；
框架内部错误文本（ValidationError / traceback / KeyError）一律折叠为通用文案；
绝对路径 / 内部目录被净化；未知状态原样显示。
冲突（409）→ 冲突面板：我的版本 / 当前版本 / 差异 + 查看最新 / 复制我的修改 /
重新编辑，**无 force overwrite**。

## 24. Loading / empty states

每个 panel 独立 loading（不整页白屏）；长操作显示操作名与「关闭面板」（诚实说明
关闭不等于取消后端请求）；空态给出「为什么 + 一个主行动」；通知统一为
success / warning / error / info 并 6 秒自动淡出。

## 25. Responsive / accessibility

1440 / 1280 / 1024 / 390 四视口门禁：无意外横向溢出、导航可用、主内容可读、
抽屉可用、状态可见、主操作可达；≤1023 导航折叠为横向、抽屉变全宽。
按钮有可见 label，icon-only 有 aria-label，抽屉/对话 Esc 可关且焦点返回，
状态不只靠颜色。

## 26. Legacy UI migration

Story Studio 成为默认产品面；V3 与 V2 改为**显式兼容入口**（`?ui=v3` / `?ui=v2`）。
8 个 `tests/browser_v3_*.cjs` 与 4 个 V2/creator 脚本只改启动参数，**断言未改**；
新增可执行兼容门禁 `tests/browser_v4_legacy_entry.cjs`（默认→Studio、?ui=v3→V3、
?ui=v2→V2、无页面错误、无重定向循环）。

## 27. Legacy removal decisions

不删除：V3 工作台 / V2 creator 面板 / legacy writer / outline revision /
legacy export backend endpoints —— 仍有真实兼容消费者；
V4_DELETION_PLAN 记录 `Story Studio primary migration = DONE`、
`Legacy entry = explicit compatibility`、`Legacy backend removal = NOT YET ELIGIBLE`。

## 28. Backend / API changes

```text
src/novelforge/api/studio_routes.py   新增 /studio/*：overview / blueprint / generate /
                                      quality(read·evaluate·repair·verify) /
                                      delivery/formats / plugins（只读）
src/novelforge/api/app.py             create_app(...)：注入 gateway / plugin_host /
                                      registry；UI 构建物来自仓库；legacy catalog 来自仓库
src/novelforge/api/delivery_routes.py 注入 exporter registry（插件格式可选择）；
                                      构造点收敛为唯一 helper
```
只经 `application.services`；不新增业务规则；不修改 Blueprint schema / Canon / StoryState。

## 29. Module boundary verification

V4_MODULE_BOUNDARIES §3.6 明确：UI 只经 HTTP；不得 import / 读取
blueprint storage / quality store / editor store / delivery store / plugin registry /
文件系统产物；不得推导业务事实（ADR-033）。既有守卫全部 PASS
（`tests/v4/isolation/**`，含 delivery 路由「唯一 ExportService 构造点」断言）。

## 30. Frontend tests

```text
runner          vitest 2.1 + @testing-library/react 16 + jsdom（React 18 / Vite 5 / TS 5 未升级）
scripts         "test": "vitest run"、"test:watch": "vitest"
suites（7 文件 / 59 tests，全部 PASS）
  design/parents.test.ts    explicit / missing / resolved / ambiguous / 预选失效 /
                            scene→chapter、chapter→structural_unit|story_arc、
                            character_arc→character；不得按 sequence/顺序取“最新”
  design/errors.test.ts     7 个稳定 code + 未知 fallback；无 traceback / 绝对路径 /
                            raw ValidationError
  nav.test.ts               6 主 + 2 辅导航边界、深链接解析、hash 往返
  components.test.tsx       StatusBadge（图标+文案+形状）、Scene Card（story_function 在正面）、
                            Diff（before/after、无变化、缺失）、IssueCard（人类文案+诊断码）、
                            ParentPrompt（必须显式选择）、Toast（fake timer 自动消失）
  workspaces/delivery.test.tsx  默认 accepted、格式来自后端（含插件 tlist）、
                            blocked preflight、成功 manifest + 下载链接
  workspaces/plugins.test.tsx   name/version/status/capability/permission/error、
                            trust 文案、无任何操作控件
  api/studio.test.ts        mocked HTTP wire contract：expected_revision / parent_id /
                            index / dry_run（preview vs execute）/ 错误码传播
```

## 31. Browser / E2E tests

```text
环境        project-pinned playwright + 本机 Edge（chromium channel），headless
服务        scripts/studio_ui_test_server.py（隔离数据根 + stub 模型 + fixture 插件 +
            可交付种子；0 real network model calls）
golden      tests/browser_v4_studio_golden.cjs = PASS
            landing → create → premise → world → character → story_arc →
            structural_unit → chapter → 多 chapter 父节点选择（不 latest-wins）→ scene →
            drawer → 编辑 → 保存新版本 → Diff → 接受 → 冲突面板 → Quality Center →
            repair preview → Delivery → 三个真实下载 → Plugins → 四视口
legacy      tests/browser_v4_legacy_entry.cjs = PASS
```

## 32. Delivery download browser gate（补齐 V4-07 缺口）

```text
real Playwright/Edge download event
Markdown: blueprint.md          5557 bytes
DOCX:     blueprint.docx        3845 bytes
nfpack:   novelforge-package.nfpack  20712 bytes
filename verified / bytes > 0 / 0 real model network calls
```

## 33. Impact-based backend validation

```text
pytest -q tests/studio tests/plugins tests/v4 tests/editor tests/delivery \
          tests/test_v2_frozen_guard.py tests/test_v3_frozen_guard.py
  → 396 passed
python scripts/validate_project.py → PASS
Full Python regression: NOT REQUIRED — impact-based validation sufficient.
（未改 Python 依赖 / core / Blueprint schema / 共享持久化语义 / 共享测试基础设施）
```

## 34. Frozen boundary

```text
novelforge-product-v3-final = f21464713e4786410e5550a7ad5504692cc644dd（未移动）
novel/authoring frozen digest = 未修改
story_engine/repair.py = 未改
REPAIR_GATE_V1 = 未改
Canon semantics = 未改
StoryState semantics = 未改
```

## 35. Files created

```text
docs/v4/V4_10_UI_INVENTORY.md / V4_UI_CONTRACT.md / V4_10_STORY_STUDIO_REPORT.md
docs/v4/V4_10_STORY_STUDIO_STATUS.md（过程记录，已 SUPERSEDED）
docs/v4/adr/ADR-032-story-studio-is-the-primary-v4-product-surface.md
docs/v4/adr/ADR-033-ui-displays-business-truth-but-does-not-derive-it.md
src/novelforge/api/studio_routes.py
ui/src/api/studio.ts（+ studio.test.ts）
ui/src/studio/**（StudioApp / nav / components / NodeDrawer / design/* / workspaces/*
  + design/parents.ts / *.test.ts(x)）
ui/src/test/setup.ts
tests/studio/**（conftest / studio_support / test_studio_api / test_studio_generate_contract）
tests/browser_v4_studio_golden.cjs / tests/browser_v4_legacy_entry.cjs
scripts/studio_ui_test_server.py
```

## 36. Files modified

```text
src/novelforge/api/app.py（create_app / 注入 / UI dist / legacy catalog）
src/novelforge/api/delivery_routes.py（registry 注入 + 唯一构造点）
ui/src/App.tsx（默认 Story Studio；?ui=v3 / ?ui=v2）
ui/package.json / package-lock.json / vite.config.ts（测试 runner + scripts）
tests/v4/isolation/test_delivery_boundaries.py（构造点收敛断言，比计数更严格）
tests/browser_v3_*.cjs（8 个）+ tests/browser_creator_*.cjs（3 个）+ browser_story_builder.cjs
  （仅入口参数 ?ui=v3 / ?ui=v2，断言未改）
docs/v4/V4_MODULE_BOUNDARIES.md / V4_ARCHITECTURE.md / V4_ARCHITECTURE_RISKS.md /
  V4_DELETION_PLAN.md / V4_BRANCH_STRATEGY.md / adr/README.md
```

## 37. Files deleted

```text
（无）V4-10 只做产品面迁移与验证，未删除任何 UI、后端端点或 release artifact。
```

## 38. Git branch

```text
v4-10-story-studio-ui（integration）
事实记录（不重写历史）：V4-10 的前 5 个提交最初落在 v4-09-plugin-platform，
随后建立本分支指向该 head 并继续提交。
```

## 39. Git commits

```text
（1）docs(v4): freeze story studio ui contract
（2）feat(api): add story studio read and action facades
（3）feat(ui): add story studio shell workspaces and editor
（4）test(browser): add story studio golden workflow gate
（5）docs(v4): record story studio continuation point
（6）fix(ui): resolve generation parent deterministically and unblock scene flow
（7）test(ui): add component and wire-contract coverage（vitest runner）
（8）test(browser): add legacy entry compatibility gate
（9）docs(v4): record v4-10 result
```

## 40. Remaining risks

| 风险 | 状态 | 说明 |
| --- | --- | --- |
| 历史 V3/V2 完整验收未运行 | **明确记录** | 需要作者 acceptance data root；未造假数据、未降低门槛、未宣称 PASS |
| 兼容入口依赖显式参数 | 已知 | `?ui=v3` / `?ui=v2`；忘记参数会进入 Studio（已由门禁覆盖默认行为） |
| 插件页只读 | 设计选择 | operator boundary 未开放；enable/disable 留给后续阶段 |
| in-process 插件无沙箱 | V4-09 遗留 | R-12 状态不变（permission ≠ OS sandbox） |
| UI 未来「顺手推导业务」 | 已缓解 | 单一客户端 + 状态表 + 错误表 + ADR-033；新页面需遵守 UI Contract |
| 交付快照 id 在总览显示 | 有意 | UI Contract §48 要求展示 snapshot id（交付记录标识） |

## 41. V4-11 readiness

```text
[x] Story Studio 是默认产品面；V3/V2 显式兼容入口（ADR-032）
[x] UI 只经 HTTP → Application Services；不推导业务真相（ADR-033）
[x] 生成 / 编辑 / Diff / 冲突安全保存 / 质量 / 修复 / 交付 / 下载全链路浏览器验证
[x] deterministic parent resolution（无 latest-wins）+ index 传播修复 + 回归测试
[x] 前端 component + mocked-HTTP 测试运行器与覆盖
[x] 真实浏览器下载证据（Markdown / DOCX / nfpack）
[x] 四视口门禁 + 视觉截图证据（workspace/studio_ui_review/）
[x] 后端 impact 测试 + frozen guards + validate_project 全绿

V4-11（Agent Mode）可从此继续：PluginService / Studio API / 浏览器门禁设施已就绪。
```

---

```text
V4-10 = PASS
```
