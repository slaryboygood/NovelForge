# NovelForge V4 — UI Contract（V4-10 冻结，SSOT）

> 状态：**V4-10 Story Studio UI 冻结**
> 依据：任务书 §1–§120；`docs/v4/V4_10_UI_INVENTORY.md`；V4-04→V4-09 各 Contract
> 定位：V4 UI 的**信息架构 / 状态语义 / backend 映射 / 主流程 / 视觉规则**唯一来源。
> 任何 UI 改动先改本文件，再改代码。

---

## 1. 铁律

```text
UI DOES NOT INVENT BUSINESS TRUTH.
UI 只能：展示 backend 返回的真相、调用 backend 能力、组织作者的操作顺序。
UI 不得：判断质量 PASS、推断 accepted、计算 StoryState、拼 Canon、决定 revision、
        决定 repair scope、选择 delivery revision、扫描插件。
```

```text
· UI 只经 HTTP（`ui/src/api/studio.ts` 统一客户端）访问 `/api/story-builder/*`
· UI 不 import Python 模块、不读文件、不访问 MCP（REST 与 MCP 平级，均调 Application）
· UI 不拥有任何 truth；唯一真相来源是 Blueprint / Quality / Editor / Delivery 的 API 响应
```

---

## 2. Primary Visual Reference

```text
Primary Visual Reference：产品自身 Design System
  ui/src/v3/design-system/tokens.css        颜色 / 间距 / 圆角 / 字体 / 动效 token
  ui/src/v3/design-system/icons/IconRegistry.tsx  语义图标（一个概念 = 一个 icon id）
  ui/src/v3/design-system/primitives.tsx    Card / Button / Badge / EmptyState / Disclosure …
  ui/src/v3/design-system/components.tsx    EntityVisual / ContextPanel / StatusPill …
  ui/src/assets/defaults/*.webp             6 个 release 默认美术（作者提供，V3 Visual Gate 通过）
```

**关于 `UI标准.*`（必须诚实的记录）**：任务书要求以项目根目录 `UI标准.*` 为
PRIMARY VISUAL REFERENCE。按磁盘检索，仓库根目录**不存在**该文件，也没有任何 UI 设计
参考图（只命中 `ui/src/assets/defaults/*` 与构建产物）。这不是 V4-10 的新发现：
`docs/CURRENT_PRODUCT_ACCEPTANCE_REVIEW.md`（V3 验收，作者复核）已就此裁定——
视觉验收基准改为「产品自身 Design System + 6 个 release 默认美术 + 四视口实际渲染」。
`tokens.css` 同时记录了该设计系统与 `UI标准` 的关系：

```text
视觉来源：项目根目录 UI 视觉标准（深色电影感、低噪声、暖金强调 + 青绿进度）。
```

因此 V4-10 的做法是：**沿用同一套作者确认过的 Design System**（不新建第二套主题），
并把 Studio 的视觉语言建立在它之上。

### 2.1 采用（ADOPT）

| 视觉元素 | 来源 | Studio 用法 |
| --- | --- | --- |
| 深色电影感底色 + 暖金强调 + 青绿进度 | `tokens.css` | 全局唯一 token 来源；Studio 不硬编码颜色 |
| 卡片 = 主要信息容器（> 表格） | V3 `Card` / `ChapterCard` / `CharacterCard` | 人物 / 章节 / 场景 / 世界 / 插件全部用卡片 |
| 语义图标（24×24、1.7 描边） | `IconRegistry` | 一级导航、状态、动作按钮；不使用 emoji 作主图标 |
| 状态 = 图标 + 文案 + 形状（不只靠颜色） | `StatusPill` + `STATUS_ICON` | 统一 `StatusBadge`（§4） |
| ContextPanel（右侧上下文抽屉，Esc/焦点陷阱） | `components.tsx` | 节点详情、issue 详情、修复预览 |
| 6 个默认美术（封面 / hero / 角色 / 地点 / 势力 / 章节） | `assets/defaults` | 卡片视觉 fallback（真实 story asset 优先） |
| 空态 / 加载 / 错误三态 | `EmptyState` / `LoadingState` / `ErrorState` | 每个 panel 独立三态 |

### 2.2 调整（ADAPT，因可用性）

| 决策 | 原因 |
| --- | --- |
| 一级导航从 V3 的 9 项收敛为 6 主 + 3 辅助（§3） | 任务书 §7：不要让作者在 20 个菜单里找东西 |
| Studio 新增 `studio.css`（复用 tokens，不新增主题） | Studio 版式（左侧栏 + 主区 + 右抽屉）比 V3 工作区更密 |
| 场景页以“故事功能”为主标签，字段折叠 | §25：Scene Card 必须回答“这场戏为什么存在” |
| Quality 页不显示任何总分 | §38：当前契约是 gate-based，没有总分 |
| 插件页不提供 enable / disable 按钮 | §53：V4-09 未开放 operator 边界，默认只读 |

---

## 3. 信息架构与导航

```text
主（从左到右 = 从概念到交付）
  创造  creation     Premise / Theme / 核心冲突 / 戏剧问题 / 故事承诺 / genre / tone / 约束
  世界  world        World rules / Locations / Factions / Resources / 技术·魔法 / 历史
  人物  characters   角色卡 + 人物弧 + 关系
  故事  story        Story Arc / Structural Units / Chapter Cards
  场景  scenes       Scene Cards（按章节分组）
  检查  quality      Quality Center（Q0–Q9 / issue / 修复 / 复核）

辅助
  交付  delivery     Delivery（selection / preflight / manifest / 下载）
  插件  plugins      插件只读状态 + trust model
  设置  settings     作品设置（作品名/编号/题材提示；只读或经既有 novel API）
```

导航规则：

```text
· 一级导航 ≤ 9 项；当前页高亮 + 图标 + 文案
· 每屏突出主按钮 ≤ 3 个；危险操作视觉权重最低
· 高级字段 / provenance / revision metadata 默认折叠（Disclosure）
```

### 3.1 路由与深链接（hash 路由，刷新不丢位置）

```text
#/studio                                      Studio Landing（作品选择 / 新建）
#/studio/n/{novelId}                           Overview
#/studio/n/{novelId}/creation|world|characters|story|scenes|quality|delivery|plugins|settings
#/studio/n/{novelId}/characters/{nodeId}       人物详情（深链接）
#/studio/n/{novelId}/story/{nodeId}            章节 / 结构单元详情
#/studio/n/{novelId}/scenes/{nodeId}           场景详情
#/studio/n/{novelId}/quality/{issueId}         issue 详情
#/studio/n/{novelId}/delivery/{snapshotId}     交付详情
#/v3/...                                       V3 兼容入口（保留）
#/story-builder?...                            V2 legacy（高级工具，保留）
```

要求：Back / Forward / Reload 均可用；`novel / character / chapter / scene /
quality issue / delivery snapshot` 全部可深链接（§60–§61）。

---

## 4. UI_STATUS_MAP（唯一状态语义表）

同一状态在**任何页面**必须使用同一图标 + 文案 + 色调 + 形状。实现：
`ui/src/studio/design/status.ts`（`UI_STATUS_MAP` + `StatusBadge`）。

| 状态 key | 来源（backend 字段） | 文案 | 图标 | tone | 形状 |
| --- | --- | --- | --- | --- | --- |
| `proposed` | Blueprint 节点 `status` | AI 建议（待接受） | `creation` | `info` | 虚线徽章 + 角标点 |
| `draft` | 同上 | 草稿 | `outline` | `neutral` | 实线徽章 |
| `accepted` | 同上 | 已接受 | `complete` | `success` | 实心徽章 + 勾 |
| `superseded` | 同上 | 已被取代 | `back` | `muted` | 灰度徽章（斜纹） |
| `unevaluated` | 质量 / 节点 `quality_status` | 尚未检查 | `current` | `muted` | 空心圆 |
| `passed` | 质量 `status` | 检查通过 | `complete` | `success` | 实心圆 + 勾 |
| `failed` | 质量 `status` | 未通过 | `warning` | `warning` | 三角 |
| `blocked` | 质量 `status` | 被阻止 | `warning` | `danger` | 三角 + 竖条 |
| `needs_human_review` | 质量 / 闭环 `status` | 需要作者决定 | `conflict` | `warning` | 三角 + 问号点 |
| `review_accepted` | editor review `decision` | 已评审接受 | `complete` | `success` | 勾 + 边框 |
| `review_rejected` | editor review `decision` | 已评审拒绝 | `close` | `danger` | 叉 + 边框 |
| `open` | setup `status` | 未回收 | `foreshadow` | `info` | 空心环 |
| `partially_paid` | 同上 | 部分回收 | `foreshadow` | `warning` | 半环 |
| `paid` | 同上 | 已回收 | `complete` | `success` | 实心环 + 勾 |
| `abandoned` | setup / payoff `status` | 已放弃 | `close` | `muted` | 灰度 |
| `delivered` | delivery `status` | 已交付 | `export` | `success` | 实心徽章 |
| `dry_run` | 同上 | 预演（未发布） | `foreshadow` | `info` | 虚线徽章 |
| `partial` | 同上 | 部分交付 | `warning` | `warning` | 半实心 |
| `disabled` | 插件 `status` | 已停用 | `locked` | `muted` | 灰度徽章 |
| `failed_plugin` | 插件 `status=failed` | 加载失败 | `warning` | `danger` | 三角 |
| `incompatible` | 插件 `status` | 与当前版本不兼容 | `warning` | `warning` | 三角 |
| `ask` | 通用（信息缺失） | 需要补充 | `objective` | `info` | 空心点 |

规则（§14）：

```text
· 颜色永远不是唯一信号：必须同时有图标 + 文案（形状/徽章）
· 未在本表登记的 backend 状态 → 原样显示字符串 + `ask` 图标（不猜、不翻译成 PASS/FAIL）
· Quality PASS ≠ Accepted（不同徽章、不同文案、不同列；§34）
```

---

## 5. Backend 映射（UI 只能经这些端点）

### 5.1 读

| UI 需求 | Endpoint | Application Service |
| --- | --- | --- |
| 作品列表 / 新建作品 | `GET/POST /api/story-builder/novels` | `ProjectService` |
| Studio 总览（状态 / 计数 / 下一步 / 交付状态） | `GET /api/story-builder/studio/overview?novel_id=` | `BlueprintService` + `ReviewService` + `ExportService` + `JourneyService` |
| Blueprint 节点（人物 / 世界 / 章节 / 场景 / setup / payoff / 因果） | `GET /api/story-builder/studio/blueprint?novel_id=&node_type=&mode=` | `ExportService.blueprint_view()` |
| 节点详情（含质量） | `GET /api/story-builder/editor/nodes/{node_id}?novel_id=` | `EditorService.get_node` |
| revision 历史 | `GET /api/story-builder/editor/nodes/{node_id}/revisions?novel_id=` | `EditorService.get_history` |
| 结构化 diff | `GET /api/story-builder/editor/nodes/{node_id}/diff?novel_id=&from_revision=` | `EditorService.diff` |
| 节点质量 | `GET /api/story-builder/editor/nodes/{node_id}/quality?novel_id=` | `EditorService.get_quality` |
| 质量中心（gates / 报告 / issue 列表） | `GET /api/story-builder/studio/quality?novel_id=&gate=&status=` | `ReviewService` |
| 交付格式（含插件 exporter） | `GET /api/story-builder/studio/delivery/formats?novel_id=` | `ExportService` + exporter registry |
| 交付快照 / manifest / artifact | `GET /api/story-builder/delivery/...` | `ExportService` |
| 插件列表（含 trust model） | `GET /api/story-builder/studio/plugins` | `PluginService` |
| 下一步建议 | `GET /api/story-builder/v3/novels/{id}/journey` | `JourneyService` |

### 5.2 写（全部复用既有冻结契约 + V4-10 新增的 studio 动作）

| 动作 | Endpoint | 语义 |
| --- | --- | --- |
| 字段级编辑 | `PATCH /editor/nodes/{id}` | 必带 `expected_revision`；409 = revision conflict |
| AI 改写 | `POST /editor/nodes/{id}/rewrite` | 产出新 revision（proposal），UI 显示 before/after |
| 接受 / 拒绝 | `POST /editor/nodes/{id}/accept|reject` | 作者决定，与质量独立 |
| 恢复版本 | `POST /editor/nodes/{id}/restore` | 以旧内容创建**新** revision（不删除历史） |
| 排序 / 移动 | （复用 editor move 契约；本阶段 UI 仅在场景页暴露“上移/下移”） | 结构操作必须走 Editor API，禁止本地改数组 |
| 逐级生成 | `POST /api/story-builder/studio/generate` | `task` = premise/world/character/unit/chapter/scene |
| 整体质量评估 | `POST /api/story-builder/studio/quality/evaluate` | 生成新的 QualityReport（gate-based） |
| 修复预览（dry-run） | `POST /api/story-builder/studio/quality/repair`（`dry_run=true`） | 改动范围 / 允许改 / 保留 / 复核 gate |
| 执行修复 | 同上（`dry_run=false`） | 写入 revision + 结果 |
| 复核修复 | `POST /api/story-builder/studio/quality/verify` | verification（resolved / partial / needs_human_review） |
| 交付 | `POST /api/story-builder/delivery` | accepted / current / explicit；preflight 阻止 → 不可下载 |

---

## 6. 主流程（UI 必须能走通）

```text
A 首次使用          Studio Landing（空态）→ 新建作品 → Overview（下一步卡片）
B 逐级生成          Creation → World → Characters → Story → Scenes（每步 generate → proposal → accept）
C 编辑与冲突        Scenes 打开场景 → 改字段 → 保存新版本 → 查看 Diff
                    （若后台已更新：409 → 冲突面板：我的版本 / 当前版本 / 差异 → 查看最新 / 复制我的修改 / 重新编辑）
D AI 改写           选中字段 + 要求 → 预览 → before/after diff → 接受 / 拒绝
E 质量闭环          Quality Center → issue 卡片（人类文案 + code）→ evidence → 修复预览 → 执行 → 复核
F 交付              Delivery → selection（accepted 默认）→ preflight → 阻止则“去检查” → 成功 → manifest → 下载
G 插件              插件页 → trust model → 列表（status / capabilities / permissions）
```

---

## 7. 错误映射（stable code → 作者语言）

实现：`ui/src/studio/design/errors.ts`（`STUDIO_ERROR_MESSAGES`）。

| Backend code | UI 文案 | 建议动作 |
| --- | --- | --- |
| `EDITOR_REVISION_CONFLICT` / `REVISION_CONFLICT` | 内容已经被更新，请比较最新版本后再保存。 | 打开 Diff |
| `EDITOR_PRESERVE_VIOLATION` | 这次修改碰到了不应改动的字段。 | 查看受保护字段 |
| `EDITOR_NODE_NOT_FOUND` | 这个节点已经不存在（可能被取代）。 | 返回列表 |
| `DELIVERY_QUALITY_STALE` | 当前版本还没有最新质量检查。 | 去检查 |
| `DELIVERY_QUALITY_FAILED` | 质量检查未通过，暂不能交付。 | 查看问题 |
| `DELIVERY_QUALITY_UNEVALUATED` | 还没有做过质量检查。 | 运行检查 |
| `DELIVERY_UNPAID_REQUIRED_SETUP` | 有必回收的伏笔还没回收。 | 查看伏笔 |
| `DELIVERY_NO_ACCEPTED_REVISION` | 还有内容没有被接受。 | 去接受 |
| `DELIVERY_MISSING_REQUIRED_NODE` | 结构不完整（缺少必需节点）。 | 查看结构 |
| `DELIVERY_FORMAT_UNSUPPORTED` | 该交付格式不可用（可能对应插件已停用）。 | 刷新格式列表 |
| `PLUGIN_PERMISSION_DENIED` / `PLUGIN_NOT_APPROVED` | 插件未获得该权限 / 未批准。 | 插件页查看 |
| `GENERATION_UNAVAILABLE` | 当前未配置模型，无法生成。 | 配置后重试 |
| `*`（未登记） | 操作失败：<短消息> | 重试；不显示 traceback / 路径 |

禁止向作者展示：HTTP 状态码原文、traceback、`ValidationError`、`KeyError`、
绝对路径、`request_id`、provider base url、raw JSON（§58、§92）。

---

## 8. 交互规则

```text
Loading   每个 panel 独立 loading（不整页白屏）；长操作显示操作名 + 可关闭等待面板
          （关闭 ≠ 取消后端请求，文案必须诚实）
Empty     每个列表都有 empty state（图标 + 一句为什么 + 一个主行动）
Save      append-only：文案是“保存修改 / 已保存新版本”，不写“覆盖成功”
Autosave  本阶段不做逐字 autosave（避免每字符一个 revision）；显式保存
Optimistic update  涉及 revision 的写操作**不做**乐观更新：等 backend 返回新 revision
Notification  统一 toast：success / warning / error（同一套样式与位置）
Modal     简单编辑用 drawer / panel；重要审查用整页；破坏性操作才用 dialog
ErrorBoundary  单个 feature 崩溃不拖垮整个 Studio（PanelBoundary）
```

---

## 9. 响应式 / 可访问性 / 支持矩阵

```text
Desktop  全功能（≥1280px 三栏：导航 + 主区 + 抽屉）
Tablet   1024–1279px 支持（抽屉变全宽面板，导航可折叠）
Mobile   ≤768px 只读 + 基础操作（列表 / 详情 / 接受 / 拒绝 / 查看质量）

至少 1024px 不出现横向溢出；1440 / 1280 / 1024 / 390 四视口纳入门禁
按钮有 visible label；icon-only 按钮必须有 aria-label
表单字段有 label；dialog / drawer 可 Esc 关闭 + 焦点返回触发元素
focus 可见；状态不只靠颜色
```

---

## 10. 插件信任模型（UI 必须原样表达）

```text
当前插件模型：Trusted in-process
权限控制的是 NovelForge Host API 能力，不是操作系统安全沙箱。
```

允许的权限人类文案：

| permission | UI 文案 |
| --- | --- |
| `delivery.export` | 添加新的交付格式 |
| `quality.evaluate` | 添加质量检查器 |
| `mcp.extend` | 添加 MCP 工具或资源 |
| `ai.invoke` | 使用宿主提供的模型能力 |
| `blueprint.read` | 读取蓝图内容（只读） |
| `editor.mutate` | 修改蓝图内容（需作者批准） |
| `network.request` | 使用宿主中介的网络能力 |
| `plugin.state` | 保存插件自己的状态 |

禁止文案：“此插件已被安全沙箱隔离”“插件无法访问系统”之类的虚假安全承诺。
插件页**只读**：不提供 enable / disable / 安装 / 配置编辑（V4-09 §65–§67 + 本阶段 §53–§54）。

---

## 11. DTO 与客户端纪律

```text
· 一个 HTTP 客户端模块：ui/src/api/studio.ts（+ 既有 ui/src/api.ts 的 requestJson）
· feature 组件不得直接 fetch：全部经 studio 客户端
· 一个实体一个 DTO：禁止 SceneLike / SceneInfo / SceneDto2 平行结构
· DTO 只描述 wire 形状；任何派生显示值由组件用纯函数计算（例如 diff 行高亮）
· 不在前端拼接业务判断（例如“有 critical issue ⇒ 不能交付”必须读 preflight 结果）
```

---

## 12. 测试要求

```text
Unit / component（vitest + @testing-library/react）
  StatusBadge / error mapping / nav model / card 渲染 / diff 渲染 / delivery 表单 / plugin 状态
Integration（vitest，mock HTTP）
  studio 客户端 ↔ DTO 形状：patch / rewrite / accept / reject / restore / quality / repair / delivery / plugins
Browser / E2E（Playwright）
  golden workflow / generation / conflict / quality+repair / delivery download（Markdown·DOCX·nfpack）
  / plugins 只读 / 四视口无横向溢出
```
