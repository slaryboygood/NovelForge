# NovelForge V4-10 — UI Inventory

> 状态：**V4-10 Story Studio UI 盘点（编码前完成）**
> 依据：任务书 §6 / §75；`docs/v4/V4_UI_CONTRACT.md`（本阶段 SSOT）
> 方法：只读扫描 `ui/src/**`、`src/novelforge/api/**`、`tests/browser_*.cjs`、`ui/package.json`
> 结论：V4 Story Studio（`ui/src/studio/**`）成为主产品路径；V3 工作台降级为兼容入口；
> V2 legacy 面板保持 `COMPATIBILITY_ONLY`。

---

## 0. 环境事实（DISK STATE WINS）

```text
ui/package.json      React 18.3 + TypeScript 5.6 + Vite 5.4；scripts 只有 dev / build / preview
ui/node_modules      存在（39 个包）；无 test runner / 无浏览器自动化依赖
tests/browser_*.cjs  20 个 Playwright 门禁（require('playwright')）—— 依赖当前未安装
node                 本机 v24.19（npm 11.17，registry 可达）；Edge Chromium 已安装
UI标准.*             仓库根目录**不存在**该参考图（也无任何 UI 设计参考图）
```

视觉基准的处置（不是忽略，而是记录）：`docs/CURRENT_PRODUCT_ACCEPTANCE_REVIEW.md`
（V3 验收，作者复核）已裁定：不存在 `UI标准` 参考图，因此视觉验收基准 =
产品自身 Design System（`ui/src/v3/design-system/`）+ 6 个 release 默认美术 +
四视口实际渲染结果。`ui/src/v3/design-system/tokens.css` 记录了该设计系统的来源
（“视觉来源：项目根目录 UI 视觉标准：深色电影感、低噪声、暖金强调 + 青绿进度”）。
V4-10 沿用同一 Design System 作为 PRIMARY VISUAL REFERENCE（见 UI Contract §2）。

---

## 1. 现有 UI → Backend → V4 Action

| Existing UI | Backend | V4 Action | Target |
| --- | --- | --- | --- |
| `ui/src/StoryBuilderPage.tsx` + 12 个 V2 面板（Adventure / Character / CreativeBrief / DesignTree / Director / GuidedFlow / Inspector / Linkage / Memory / OutlineForge / Plot / Progression / RouteLab / SettingSeed / VisualOutput / VisualOverview / World） | `/api/story-builder/**`（~90 个 V3 端点） | **KEEP compatibility**（高级工具入口；不进入 V4 一级导航） | `#/story-builder?...`（保留），Studio 内“高级工具”链接 |
| `ui/src/v3/NovelLanding.tsx` | `GET /api/story-builder/v3/novels`、`GET /novels` | **REPLACE**（作品选择并入 Studio Landing） | `#/studio` 空态 / 作品卡 |
| `ui/src/v3/CommandCenter.tsx` + `viewmodel.ts` | `GET /api/story-builder/v3/novels/{id}/command-center`、`/journey` | **REPLACE**（Studio Overview 换成 Blueprint 真相） | `#/studio/n/{id}` |
| `ui/src/v3/CreationFlow.tsx` | `/creative/*`、`/settings/*`、`/sessions/*`（V3 十步流程） | **REPLACE**（Studio 创造页 = Premise/Theme/Conflict 直编 Blueprint 节点） | `#/studio/n/{id}/creation` |
| `ui/src/v3/WorkspaceView.tsx`（章节 / 角色 / 地点 / 势力 卡片） | `/v3/novels/{id}/command-center` 投影 | **REPLACE**（改读 Blueprint 节点，不再读 V3 投影） | Studio 人物 / 世界 / 故事 / 场景页 |
| `ui/src/v3/ExportFlow.tsx` | `/outline/export`、`/export/package`、`/export/writer-bundle` | **REPLACE**（切到 V4 Delivery） | `#/studio/n/{id}/delivery` |
| `ui/src/v3/AppShell.tsx` + `navModel.ts` + `design-system/*` | —（纯前端） | **ADAPT**（沿用 Design System；新增 Studio 壳与导航模型） | `ui/src/studio/**` |
| `ui/src/v3/export-flow.css` / `v3.css` | — | **KEEP**（Studio 复用 tokens；新增 `studio.css`，不新建第二套主题） | `ui/src/studio/studio.css` |
| `ui/src/components/*`（CandidateCard / PanelBoundary / ProvenanceList / TruthLayerBadge） | — | **ADAPT**（PanelBoundary 的 error boundary 思路被 Studio 复用） | `ui/src/studio/components/` |
| `ui/src/components/*` 中 V2 专用组件 | `/sessions/*` 等 V2 端点 | **KEEP compatibility** | 同处保留 |
| `tests/browser_v3_*.cjs`（8 个 V3 门禁） | V3 投影 | **KEEP**（V3 仍是可进入入口；本阶段不改其断言） | `tests/browser_v3_*.cjs` |
| `tests/browser_creator_*.cjs` / `browser_story_builder.cjs`（V2 门禁） | V2 端点 | **KEEP compatibility** | 同处保留 |
| `GET /api/story-builder/{outline,export,writer}/**`（V3 导出 4 条路径） | `story_builder/outlines.py`、`outline_revision.docx_bytes`、`export_package`、`writer_export_bundle` | **DELETE after migration**（删除条件见 §3，本次只退出主产品入口） | — |

---

## 2. 哪些 UI 重复了 backend truth（必须消除）

| 前端位置 | 重复了什么 | V4-10 处理 |
| --- | --- | --- |
| `v3/viewmodel.ts` 里的 stage / progress 推导 | 进度与“下一步”（V3 有 `journey_service` 投影，但 viewmodel 又做了一层拼装） | Studio 只消费 `/studio/overview` 与 `/journey` 的既有字段，不在前端重算 |
| `ExportFlow.tsx` 的导出格式列表 | 交付格式（真实来源 = exporter registry） | Studio 从 `GET /studio/delivery/formats` 读取（含插件格式） |
| 各面板自带的 `quality` 文案/颜色 | 质量状态（真实来源 = Quality Store / Gate） | 统一 `StatusBadge` + `UI_STATUS_MAP`（UI Contract §3） |
| V3 工作区的“章节数 / 角色数”统计 | Blueprint 节点统计 | Studio 读 `/studio/overview`（服务端算好） |
| V2 `guidedFlow.ts` 的阶段推进规则 | V3 阶段语义 | Studio 不实现任何阶段推进规则（只显示 backend 返回的下一步） |

---

## 3. Removal condition 重新评估（§76–§78、§114）

| Legacy | 现状 | 本阶段结论 | 移除条件 |
| --- | --- | --- | --- |
| V3 导出 UI（`ExportFlow.tsx` + `/outline/export`、`/export/package`、`/export/writer-bundle`） | Studio 交付页已切到 V4 Delivery（含 preflight / manifest / 下载） | **UI 入口退出主路径**；后端 legacy 端点保留（V2 面板与既有隔离测试仍消费） | V2 导出面板退出 + `tests/browser_creator_*.cjs` / legacy 隔离测试不再引用 → 可删后端 4 条路径（V4-07 已登记） |
| 旧正文 Writer（`writer_integration.py` + `/writer/*` 路由 + `Writer` 面板） | 不属于 Story Blueprint 核心；Studio 无正文编辑器（§110） | **KEEP compatibility**；Studio 不提供入口 | 作者确认正文 writer 路径无真实消费者（V4-07 已登记） |
| Outline Revision 旧 UI（`OutlineItemEditor.tsx` / `/outline/revise`、`/outline/restore`） | Studio 使用 Blueprint Editor 的 revision / diff / restore | **KEEP compatibility**（V2 入口） | V2 outline 编辑面板退出 + outline 产品面切到 Blueprint |
| V2 `GuidedFlowPanel` / `CreativeBriefPanel` / `SettingSeedPanel` | V3 十步流程的重复入口 | **KEEP compatibility** | V3 入口整体退出时一并评估 |
| V3 工作台（`ui/src/v3/**`） | Studio 成为主产品面后，V3 仍是可进入入口 | **KEEP compatibility**（`?ui=v3` / `#/v3/...`） | 作者确认 V3 投影（`v3_projection.py`）无消费者 → 连同 `/v3/*` 端点一起退 |

**本次不做删除**：`docs/v4/V4_DELETION_PLAN.md` 记录原因（真实消费者仍在，
V4-10 只完成主路径切换与入口退出）。

---

## 4. 本阶段必须补的 backend facade

Studio 只能经 HTTP 访问 application services（§4、§113）。下表是**确实缺失**的读取 /
动作入口（其余一律复用既有端点）：

| 需求 | 现有 | 缺失 | V4-10 新增 |
| --- | --- | --- | --- |
| Studio 总览（状态 / 计数 / 下一步 / 交付状态） | 只有 V3 `command-center`（V3 投影语义） | Blueprint 真相总览 | `GET /studio/overview` |
| Blueprint 节点列表 / 过滤（人物 / 世界 / 章节 / 场景 / setup-payoff / causal link） | MCP resource `blueprint`；REST 无 | REST 读视图 | `GET /studio/blueprint` |
| 逐级生成（premise / world / character / unit / chapter / scene） | MCP tools；REST 无 | REST 动作 | `POST /studio/generate` |
| 质量中心：整体评估 / 报告 / issue 列表 / 修复预览 / 修复 / 复核 | editor 只有单节点 `/quality`；MCP 有 | REST 读写 | `GET /studio/quality`、`POST /studio/quality/evaluate`、`POST /studio/quality/repair`、`POST /studio/quality/verify` |
| 交付格式（含插件 exporter 格式） | `/delivery` 用无插件 registry 的 ExportService | 插件格式不可见 | `GET /studio/delivery/formats` + delivery 路由注入 registry |
| 插件只读状态（含 trust model） | `PluginService`（无 REST） | REST 只读 | `GET /studio/plugins` |

写操作（patch / rewrite / accept / reject / restore）**不新增**：直接复用
`/api/story-builder/editor/*`（V4-06 已冻结的 wire contract）。

---

## 5. 浏览器门禁盘点

```text
已有 20 个 tests/browser_*.cjs（全部 require('playwright')，当前环境未安装依赖）
V4-10 必须：
  · 恢复运行环境（npm ci + 安装 playwright，指向本机 Edge 或下载 chromium）
  · 保留并运行 V3 门禁（V3 入口仍在）
  · 新增 V4 Studio 门禁（golden / generation / conflict / quality+repair / delivery 下载 / plugins）
```
