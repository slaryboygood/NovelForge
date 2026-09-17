# NovelForge Current Product Acceptance Review

> 本次审查性质：**独立产品验收 / QA / UI-UX Review / 生成质量评审**
> 审查对象：当前工作区（branch `codex/product-v3-game-ui`，HEAD `021b9ce`，产品版本 NovelForge Product V3.0）
> 审查日期：2026-09-17
> 审查方式：真实启动 + 真实浏览器操作 + 真实数据落盘检查 + 现有测试与门禁复跑
> **本分支未修改任何业务代码、UI、提示词、生成算法或测试。** 唯一新增文件是这份报告。

---

## 1. Review Summary

NovelForge V3.0 的**界面与基础流程是可用的**：项目能安装、能启动、能创建作品，作者可以完整走完
「一句话创意 → 题材候选 → 设定候选 → 设定自检 → 开始推演 → 推演 → 锻造四级大纲 → 检查」，
全程没有白屏、没有崩溃、没有死循环，刷新与重启后数据都在。视觉方向（游戏化 / 暗色 / 卡片层级 /
主目标 + 主 CTA）与自身 Design System 一致，1440 / 1280 / 1024 / 390 四视口无横向溢出。

但**「从设定到把书交给写作环节」这条核心链路没有被跑通**：

1. 导出工作区的主 CTA「生成导出包」会跳到一个**不存在的高级工具页签，页面空白**，产品里没有任何
   导出面板（NF-001）。
2. 最后一步目标「导出并开始写作 / 已有写作草稿」在 UI 里**没有任何入口**；即使绕过 UI 用 API 创建
   草稿，V3 投影也读不到（读写不是同一个目录），因此总体进度**永远停在 51%（7 / 8 阶段）**（NF-002）。
3. 锻造出来的四级大纲**大面积是内部字段标签占位**（22 / 30、24 / 30 章标题为
   「阶段目标（规划）」「长期方向（规划）」），并把 `ev_world_shift`、`future_plan:main_…`、
   `favors`、`protagonist`、`start_place` 这类内部 id 写进作者可见的大纲与导出文件（NF-003 / NF-004）。
4. 入口页（Novel Landing）与 Command Center 对**同一本作品给出不同的阶段、进度和下一步**（NF-005）。

因此本次结论是 **FAIL**：不是「能用但有小问题」，而是**核心交付物（可写的大纲 + 导出给写作环节）
目前不可用**，与 V3.0 自报的 PASS 验收结论不一致。差异原因之一是现有浏览器门禁存在盲区（NF-020）：
P5 只断言「返回新版工作台」链接存在，不断言导出面板真的渲染；P6 扫描内部 id 泄漏的时机在大纲锻造
之前，因此漏掉了 `start_place`。

---

## 2. Final Verdict

# FAIL

判定依据（按本次验收标准）：

- 存在 **P1 级核心流程断裂**：导出环节是死链（NF-001）、最后一步目标不可达（NF-002）。
- 生成内容**不能作为小说创作素材直接使用**：章节大纲 73%–80% 为重复占位标题（NF-003），
  并把内部实现细节泄漏给作者（NF-004）。
- 核心页面之间**数据不同步**（NF-005）。

不是 P0：项目能启动、能创建作品、能保存、能推演、能锻造大纲，数据不丢。
但 PASS WITH ISSUES 要求「可以正常完成核心工作流」，本版本**不能完成**，
因为核心工作流的终点（导出给写作环节）不可达。

---

## 3. Environment

```text
OS              Windows（PowerShell 7），工作目录 F:\AI_小说\硅基升维
Python          3.11.9（.venv\Scripts\python.exe，已 bootstrap，无需重装依赖）
Node            v24.19.0（系统）+ 项目随附 .dsh-runtime/node-v22（start 脚本优先使用随附运行时）
浏览器          Microsoft Edge（Playwright channel=msedge，headless）
Playwright      开发者自带：.dsh-runtime/.dsh-browsertests/node_modules（通过 NODE_PATH 注入）
依赖安装        npm.cmd --prefix ui install → added 68 packages（此前 ui/node_modules 不存在）
前端构建        npm.cmd run build --prefix ui → PASS（tsc -b && vite build，6 个默认美术指纹化进入 dist/assets）
```

启动命令（真实启动并验证）：

```powershell
# 1) 正式启动（真实数据根 novel/authoring）：验证产品自身启动路径
.venv\Scripts\python.exe scripts/start_novelforge_ui.py --port 8000
#    → GET /api/health = {"status":"ok","product":"story-builder"}，首页可打开

# 2) 隔离数据根（本次 QA 的所有写操作都在这里，避免污染真实作者数据）
.venv\Scripts\python.exe scripts/creator_ui_test_server.py --port 8035 --root workspace\qa_review_2026_09_17\root_fresh
#    → 空白数据根，用于「第一次使用 NovelForge 的普通用户」体验
```

测试命令（真实运行）：

```powershell
.venv\Scripts\python.exe -m pytest -q                 # 876 passed / 687 deselected（historical_acceptance 默认排除）
.venv\Scripts\python.exe scripts/validate_project.py  # PASS
npx.cmd --prefix ui tsc --noEmit                      # 该形式不执行类型检查（见 NF-018）
ui\node_modules\.bin\tsc.cmd --noEmit（cwd=ui）        # PASS
node tests/browser_v3_p6_acceptance.cjs               # PASS
node tests/browser_v3_visual_asset_gate.cjs           # PASS（6/6 required 默认美术）
node tests/browser_advanced_tools.cjs                 # PASS（19 页签 + 8 个 V3 工具入口）
```

说明：

- 仓库根目录**不存在 `UI标准` 参考图目录或任何 UI 设计参考图**（按扩展名检索只命中
  `ui/src/assets/defaults/*` 与构建产物）。因此视觉验收基准是：产品自身 Design System
  （`ui/src/v3/design-system/`）+ 6 个 release 默认美术 + 四视口实际渲染结果。
- 历史里程碑验收（M11–M18 / wasteland）依赖开发机历史数据，按仓库规则默认不运行；本次未运行，
  以免触碰 `novel/authoring` 与 `workspace/` 中的历史产物。
- QA 脚本、截图、隔离数据根全部写在 gitignored 的 `workspace/qa_review_2026_09_17/` 下；
  `git status` 除本报告外无任何改动。

---

## 4. Product User Journey

以下为**实际执行**过的操作（不是计划），全部在隔离数据根上完成。

**旅程 A：空白数据根第一次使用（novel_id = `qa_acceptance_novel`）**

1. 打开 `http://127.0.0.1:8035/` → 空态：「还没有作品 / 作品是这一切的起点… / 创建第一本作品」。
2. 新建小说：空编号 → 提示「作品编号至少 3 个字符」；重复编号 → 提示「这本小说已经存在」；
   超长编号被 `maxLength` 截到 64；合法编号 → 进入 Command Center（URL `#/n/qa_acceptance_novel`）。
3. Command Center：作者旅程 8 阶段（创意/世界/角色/故事/推演/大纲/检查/导出），当前阶段「创意」，
   下一步「确定一句话创意」，其余阶段按状态显示「可以进入 / 尚未开放」。
4. 创作工作区：写入一句话创意 →「生成方向候选」→ 得到题材候选（科幻 / 修仙）、内容包候选
   （默认旅程内容包 / 都市悬疑演示）、基调候选（冷峻写实 / 史诗宏大 / 成长热血 / 温柔治愈）、
   核心卖点（身份反差 / 隐藏规则 / 线索拼合 / 规则升级）→「确定这个方向」保存简报（题材落为 `sci_fi`）。
5. 设定与起点 →「生成设定候选」→ 9 组设定候选（世界规则 / 主角 / 重要角色 / 势力 / 关系 /
   成长 / 冲突 / 主线 / 伏笔）→「保存并检查起点」。
6. 设定自检 →「开始检查」→「自检通过 / 没有任何缺项」→「开始剧情推演」→ 起点事实落盘
   （tick 0 · revision 0）。
7. 推演工作区 →「推演「向身边人打听」」→ 反馈「故事结果：success / 世界变化：世界表层规则的
   分配方式被单方面调整 / 回合 0 → 1 · 修订 0 → 1」。
8. 大纲工作区 →「生成章节大纲」→ 跳到 legacy 高级工具「大纲锻造」→「预览结构」→
   「锻造四级大纲」→「确认整条大纲」→ 回到大纲工作区看到 1 条全书主线 / 3 卷 / 6 篇章 / 30 章。
9. 检查工作区：可读的检查结果（「现在没有需要处理的故事问题」+ Canon 检查器 / 修复中心入口）。
10. 导出工作区：就绪度 5 条全部「已经满足」→「生成导出包」→ **落到空白页**（NF-001）。

**旅程 B：作者真正做选择的第二本书（novel_id = `qa_rich_novel`，修仙方向）**

同样走完 1–6 步，并在 9 组设定里逐组点选候选（世界规则 1 项、主角 1 项、重要角色 2 项、
势力 2 项、关系 1 项、成长 1 项、冲突 1 项、主线 1 项、伏笔 2 项），然后：

7. 推演 4 次：第 1、2 次成功；第 3、4 次返回 422 ——「这次推演没有执行 /
   需要 protagonist 的 favors >= 1份（当前 0.0）」（NF-008）。
8. 锻造并确认 30 章大纲（见第 7 节生成质量）。
9. 重启服务（结束进程后用同一数据根重新启动）→ 数据、进度、30 章大纲全部还在。

**旅程 C：边界与容错**

- 空输入 / 2 字输入 / 1000 字输入 / 极长编号 / 中文编号 / 带空格编号 / `../../` 编号 / emoji /
  HTML 加 `onerror` 注入 / 连点三次「生成方向候选」/ 不存在的小说深链接 / 不存在的 workspace 路由。
- 结论：没有崩溃、没有白屏、没有无限 loading、没有 XSS 执行、没有路径穿越；
  非法编号被后端 `NOVEL_ID_INVALID` 拒绝，错误提示是中文。

---

## 5. UI / UX Review

### 5.1 做得好

- **游戏化方向成立**：暗色 + 金色 CTA + 图标化侧栏 + 阶段轨道（Author Journey），
  「继续创作」永远是主 CTA，符合 ONE SCREEN / ONE PRIMARY GOAL / ONE PRIMARY CTA。
- **层级清楚**：Hero（阶段 + 进度）→ 目标卡 → 下一步卡 → 核心内容卡 → 需要留意。
  1440 视口下不需要滚动就能看到「现在做什么、下一步是什么」。
- **状态语义不依赖颜色**：完成 / 进行中 / 尚未开放同时有图标、文字与禁用态。
- **空态与错误态有作者语言**：找不到作品时是「暂时读不到这一步 / 找不到这本小说的配置 /
  重新读取 / 回到作品列表」，而不是白屏。
- **响应式**：390 / 1024 / 1280 / 1440 抽查 Command Center、大纲、推演、导出四屏，
  scrollWidth 等于 clientWidth，无横向溢出。
- 无障碍基础（由项目自身门禁覆盖）：ContextPanel role=dialog / aria-modal / Esc / 焦点返回。

### 5.2 明显问题（详见第 12 节）

| 观察 | 影响 |
| --- | --- |
| 导出主 CTA → 空白 legacy 页（NF-001） | 用户以为按钮没反应，或以为产品坏了 |
| 「确定这个方向」保存后仍停在创意面板（NF-009） | 主 CTA 没有推进感，需要用户自己发现步骤 2 |
| 推演主 CTA 在资源耗尽后仍推同一个 422 行动（NF-008） | 主路径看起来还能点，实际每次都失败 |
| 可行方向卡片标题被截断成「向身边人...」「查证与「发...」（NF-015） | 主要操作名读不全，只能靠猜 |
| 地点卡「控制方 控制方未知」（NF-013）、「还差 0 步就可以导出」（NF-012） | 文案自相矛盾，降低可信度 |
| 大纲工作区把 `start_place` 直接显示在章节卡副标题（NF-004） | 内部实现泄漏到主界面 |
| 人物/地点/势力只有原型标签，没有名字（NF-016） | 后续写作拿不到「人物是谁」 |

---

## 6. Functional Review

### 6.1 实际存在的页面（以当前实现为准）

V3 工作台（`ui/src/v3/`）：

```text
Novel Landing（作品选择） · Command Center · Creation（创作） · World（世界） · Characters（角色） ·
Story（故事） · Simulation（推演） · Outline（大纲） · Review（检查） · Export（导出） ·
Advanced Tools（高级工具 · legacy bridge）
```

legacy 高级工具（`ui/src/StoryBuilderPage.tsx`）实际有 19 个页签：
引导流 / 故事构筑 / 设定总览 / 风格参考位 / 世界面板 / 角色面板 / 剧情面板 / 成长面板 /
记忆面板 / 导演面板 / 区域卡片 / 关系网 / 路线实验室 / 大纲锻造 / 大纲联动 / 路线对比 /
大纲结构树 / Canon 检查器 / 修复中心。

**没有导出页签。** 这是 NF-001 的直接原因。

### 6.2 按钮逐项结果（要点）

| 位置 | 按钮 | 实际行为 |
| --- | --- | --- |
| Landing | 新建小说 | 打开编号对话框（可取消） |
| Landing | 继续创作 / 作品卡继续创作 | 进入该作品的 Command Center |
| Landing | 创建第一本作品 | 空数据根主 CTA，打开同一个对话框 |
| Creation | 生成方向候选 / 换一批 / 确定这个方向 | 有真实候选、有反馈条；「确定这个方向」保存后不切面板（NF-009） |
| Creation | 生成设定候选 / 换一批 / 保存并检查起点 | 正常，9 组候选可逐组展开勾选 |
| Creation | 开始检查 / 修补缺项并重查 | 正常，返回真实 findings |
| Creation | 开始剧情推演 | 正常，写 StoryState，阶段推进到「大纲」 |
| Simulation | 推演「行动」/ 对比 / 选这条 | 前 2 次正常；资源耗尽后 422（NF-008） |
| Outline | 生成章节大纲 | 跳到 legacy「大纲锻造」面板（可用） |
| Outline | 生成大纲 / 重新锻造大纲 | 同上；上游变更后会正确提示「需要重新锻造」 |
| Review | 去看看 / 打开修复中心 / Canon 检查器 | 可达 |
| Export | 生成导出包 / 打开导出面板 | **落到空白页**（NF-001） |
| 侧栏 | 高级工具 | legacy 页可达（门禁 PASS，19 页签） |
| 侧栏 | 切换作品 | 回到 Landing |

### 6.3 CRUD

| 对象 | CREATE | READ | UPDATE | DELETE |
| --- | --- | --- | --- | --- |
| 作品（novel） | 有（POST /novels + UI） | 有 | 无重命名接口/入口 | 无删除接口/入口（NF-011） |
| 创意简报 | 有 | 有 | 有（重新保存） | 无 |
| 设定候选 | 有 | 有 | 有（重新生成/改选） | 无 |
| 大纲四级 | 有（锻造/确认） | 有 | 有（重锻、版本、确认） | 无 |
| 章节 | 有（由章纲生成） | 有 | 部分（legacy 大纲联动/条目编辑） | 无 |
| 人物 / 地点 / 势力 | 通过设定候选「设计态」创建 | 有 | 通过设定候选改选 | 无 |

删除类操作在本版本**完全不存在**（前端无 DELETE 调用，后端路由无 delete）。
好处是不会误删、不会产生孤儿数据；代价是作品列表只增不减。

---

## 7. AI Generation Review

### 7.1 结论：本版本没有真正的「AI 生成」

1. 生产服务**没有接入任何 LLM provider**：
   `src/novelforge/api/app.py` 调用 `install_story_builder_api(app, ROOT)`，`provider` 恒为 `None`；
   `src/novelforge/story_builder/ai_recommendations.py` 的 `StructuredRecommendationProvider`
   在 `src/` 中**没有任何实现类**（只有测试替身）。
2. 实测证据：`POST /api/story-builder/creative/suggest` 返回
   `"source": "rule"`、`"notes": ["AI_UNAVAILABLE"]`，即使 `.env.local` 里已配置
   `DEEPSEEK_API_KEY` / `ARK_API_KEY`。
3. 而 `README.md` 与 `.env.example` 都写着「模型相关功能（设定候选 / 写作提议）需要 API key」
   「不配置时走本地确定性流程」——实际配置与否**没有任何差别**（NF-007，INCOMPLETE IMPLEMENTATION）。

按当前实现，所有「生成」都是**规则模板 + 内容包**的确定性输出：题材/基调/卖点候选来自
`creative.py` 的关键词匹配，设定候选来自 `settings_gen.py`，章纲来自 `outline_forge.py`。
因此本次「生成质量」评审 = 规则生成质量评审。

### 7.2 生成层级（当前实际支持的）

支持：一句话创意 → 题材/基调/卖点候选 → 9 组设定候选 → 内容包骨架 → 起点事实（StoryState）→
推演结果（行动 / 世界事件）→ 四级大纲（全书 / 卷 / 篇章 / 章节，默认 3×2×5 = 30 章）。

不支持（产品里没有入口）：正文 / 场景文本 / 章节成稿 / 卷内详细场景编排。
导出工作区承诺的「交给写作环节」没有可用的面板（NF-001），写作草稿也没有 UI 入口（NF-002）。

### 7.3 结构性问题（P2 / P3）

以 `qa_rich_novel`（修仙方向、9 组设定全选、推演 3 次）为例，30 章标题分布：

```text
第1章：向身边人打听
第2章：先观察，不急着介入
第3章：先观察，不急着介入
第4章：世界表层规则的分配方式被单方面调整
第5章：世界表层规则的分配方式被单方面调整
第6章：向身边人打听
第7章：先观察，不急着介入
第8章：先观察，不急着介入
第9–30章：阶段目标（规划）        ← 22 章完全同名
```

另一本（`qa_acceptance_novel`，未选任何设定项）为 24 / 30 章在
「阶段目标（规划）」「长期方向（规划）」之间交替。**两本不同题材、不同设定选择的作品，
生成结果的结构病是同一种**，说明这是生成器逻辑问题，不是用户输入问题。

代码定位：

- `src/novelforge/story_engine/outline_forge.py:546`
  `title=f"第{N}章：{stage.title}（规划）"` —— 所有「规划章节」复用同一个 `future_plan` 阶段的
  标题；阶段数=1 时 22 章同名。
- `src/novelforge/story_engine/settings_gen.py:234-235` 把候选标签
  `("阶段目标", …)`、`("长期方向", …)` 直接写成 `future_plan.stages[].title`，
  于是「字段名」变成了「章节名」。
- 同一段代码还把 `（这本小说的前提：{premise}）` 拼进每章 summary。

### 7.4 连贯性 / 重复 / 可用性

| 检查项 | 结果 |
| --- | --- |
| 设定是否被继承 | 是。题材选择（修仙）落为 `genre=xianxia`，设定候选进入世界/角色/故事工作区 |
| 上游变更是否被感知 | 是。推演后大纲工作区正确显示「这个故事已经推进过…需要重新锻造才能与当前事实一致」 |
| 章节是否符合大纲 | 只有 1–8 章成立；9–30 章是同一句占位 |
| 是否利用前文上下文 | 只用到「前提句 + 行动名」，没有用到角色目标 / 记忆 / 关系 |
| 人设 / 情节 / 场景重复 | 严重：`先观察，不急着介入` 出现 3 次、`世界表层规则的分配方式被单方面调整` 2 次、`阶段目标（规划）` 22 次 |
| 是否可作小说素材 | 不可直接使用：没有人物名字、没有场景、没有因果链，只有行动名与字段名 |
| AI 套话 | 没有「作为AI……」类文本；但存在模板占位文案（`（这本小说的前提：…）`、`（规划）`） |

---

## 8. Data Consistency Review

### 8.1 同一本作品两套数字（NF-005）

`GET /api/story-builder/v3/novels`（Landing 存档卡）与
`GET /api/story-builder/v3/novels/{id}/command-center`（作品内）对同一本书给出**不同结论**：

| 作品 | Landing 卡片 | Command Center | 真实状态 |
| --- | --- | --- | --- |
| `qa_rich_novel` | 大纲 · 81% · 下一步「继续生成章节大纲」 | 导出 · 51%（22/43）· 下一步「导出并开始写作」 | 30 章大纲已确认、已推演、只差导出 |
| `qa_acceptance_novel` | 大纲 · 25% · 下一步「继续生成章节大纲」 | 导出 · 44%（19/43）· 下一步「导出并开始写作」 | 同上 |
| `qa_edge_a1` | 世界 · 6% · 下一步「生成设定候选」 | 世界 · 11%（2/19）· 下一步「建立世界规则」 | 简报已存、未生成设定 |

可能原因：`src/novelforge/story_builder/v3_projection.py` 的 `novel_card()` / `_light_stage()`
是**第二套**阶段与进度计算（自定公式 `steps = 4 + 9 + 3`，且一旦存在 book 就把下一步硬编码为
「继续生成章节大纲」），没有复用 `command_center()` 的 objective / journey 计算。
这违反仓库自身的 canonical identity / 单一状态计算入口原则。

### 8.2 数据是否真的连通（正面结论）

- 一句话创意 → `profiles/<novel>.json` 的 `world_profile.creative_brief`；题材 → `profile.genre`
  → Command Center 显示 `xianxia`。成立。
- 设定候选 → 内容包草稿 `novel/config/story_engine/<novel>_pack.json`，世界 / 角色 / 故事工作区
  显示选中的原型。成立。
- 推演 → StoryState（`state/runtime_<novel>/v000001.json`）→ 大纲章纲的「已发生」章节。成立。
- 推演后再看大纲 → 正确标记「需要重新锻造」。成立。
- 但：**写作草稿写入路径与读取路径不一致**（NF-002），这一环是断的。

### 8.3 内部实现泄漏到作者可见内容（NF-004）

实测出现的原文：

```text
第7章：阶段目标（规划）
已发生：向身边人打听（这本小说的前提：一个边陲小城的铸剑学徒）
第1卷 · 篇章1：完成 向身边人打听 · tick 0 · start_place        ← V3 主界面
转折：ev_world_shift                                            ← 导出 markdown
来源：来源：main 路线（revision 1）                              ← 导出 markdown
代价 / 关系变化：favors 消耗 1                                    ← 导出 markdown
must_keep: 来源：future_plan:main_7f2dd4b4（planned，尚未发生）    ← 章纲 JSON
需要 protagonist 的 favors >= 1份（当前 0.0）                     ← 推演失败提示
```

同一屏里 `favors` 既被翻译成「人情 ×1」（候选卡），又原样出现在错误提示里 —— 说明缺一层
统一的「内部标识 → 作者语言」映射。

---

## 9. Persistence Review

| 场景 | 结果 | 证据 |
| --- | --- | --- |
| 页面刷新（Command Center） | 进度 51% → 51%，阶段 / 下一步不变 | journey8 `persistence-refresh` |
| 新浏览器上下文（模拟换设备 / 新会话） | 大纲 30 章仍在（章节卡渲染） | journey8 `persistence-fresh-context` |
| **重启后端服务**（结束进程后同数据根重启） | 进度 51%（22/43）、30 章大纲、3 本作品全部保留 | 重启后重新调用 API 校验 |
| 深链接恢复 | `#/n/<id>/<workspace>` 直接打开对应工作区 | journey3 / journey7 |
| 未保存的创意草稿 | 刷新 / 离开即丢（NF-010，设计如此：只有「确定这个方向」才落盘） | journey1 / journey2 |
| 数据落盘位置 | `novel/authoring/story_engine/profiles/*.json`、`state/runtime_*/v*.json`、`novel/authoring/story_builder/outlines/*/ol_forge_*`、`novel/config/story_engine/*_pack.json` | 隔离数据根文件清单 |

没有观察到数据丢失、覆盖写、半写入文件或脏读。

---

## 10. Error Handling Review

### 10.1 表现良好

| 输入 | 结果 |
| --- | --- |
| 空作品编号 | 界面提示「作品编号至少 3 个字符」，不提交 |
| 2 字作品编号 | 同上 |
| 重复作品编号 | 后端 409 → 界面「这本小说已经存在」 |
| 120 字作品编号 | `maxLength=64` 截断 |
| 中文 / 空格 / `../` / 带点编号 | 后端 `NOVEL_ID_INVALID`（「小说编号格式不正确」），未写任何文件，**无路径穿越** |
| HTML + onerror 注入创意 | 未执行（`window.__xss !== 1`），未生成 `<img src=x>`，候选照常返回 |
| emoji + 中文创意 | 正常 |
| 连点三次「生成方向候选」 | 无报错、无异常卡片、无 console error |
| 不存在的小说深链接 | 优雅错误态 +「重新读取 / 回到作品列表」 |
| 不存在的 workspace 路由 | 回落到 Command Center，不白屏 |
| 服务 / 数据不可读 | 前端显示「暂时读不到这一步」（PanelState 兜底） |

### 10.2 表现不好

- **推演前置条件失败（422）**：错误信息暴露 `protagonist` / `favors`（NF-004 / NF-008）；
  主 CTA 仍指向同一个不可执行行动，用户必须自己去看「可行方向」里别的卡片。
- **导出就绪度文案自相矛盾**：`ready=false` 且存在 blocker 时标题仍写「还差 0 步就可以导出」，
  左侧状态条写「先补上：缺失步骤」（NF-012）。
- **409 / 422 在 DevTools 里表现为 Failed to load resource**（预期内，非缺陷，但会让「零 console error」
  这类门禁在真实冲突路径上无法保持 0 噪声）。

---

## 11. Automated Test Results

```text
pytest（默认套件）                876 passed / 687 deselected（0 failed），357.67s
historical_acceptance            687 项被默认排除（依赖本机历史数据，本次未运行）
validate_project.py              PASS
ui build（tsc -b && vite build）  PASS
ui tsc --noEmit（在 ui/ 下执行）   PASS
README 记录的 tsc 形式             FAIL（打印帮助文本，见 NF-018）
browser_v3_p6_acceptance.cjs     PASS
browser_v3_visual_asset_gate.cjs PASS（6/6 required 默认美术：封面 / Hero / 角色 / 地点 / 势力 / 章节）
browser_advanced_tools.cjs       PASS（19 页签 + 8 个 V3 工具入口 + 4 视口）
页面噪声（真实用户路径）          0 pageerror / 0 requestfailed / 0 预期外 4xx（除人为制造的 409、422）
```

注意：`docs/V3_FULL_PRODUCT_ACCEPTANCE.json` 记录的 `1559 passed / 1 skipped` 在本机无法用仓库默认
命令复现（默认只跑 876 条当前产品测试）；该数字对应「含历史里程碑验收」的发布候选环境。
这不影响本次结论，但意味着**发布验收证据与仓库默认测试命令之间缺少可复现的对应关系**。

---

## 12. Issues

> 排序：P0 → P1 → P2 → P3 → P4。每条按「Issue ID / Severity / Module / Problem / Reproduction /
> Expected / Actual / Evidence / Probable Cause / Suggested Fix / Acceptance Criteria」给出。

### NF-001

**Severity** P1（BLOCKING for acceptance）

**Module** Export Workspace / Advanced Tools bridge

**Problem** 导出工作区的主 CTA「生成导出包」（就绪时）或「打开导出面板」（未就绪时）跳转到
`#/story-builder?...&tab=export`，但 legacy 高级工具**没有 export 页签**，页面只剩外壳 + 页签导航，
内容区完全空白；产品中也不存在任何导出面板。

**Reproduction**

1. 用 `qa_rich_novel`（30 章大纲已确认）打开 `#/n/qa_rich_novel/export`。
2. 点击右栏主 CTA「生成导出包」。
3. 观察跳转后的页面。

**Expected** 打开可用的导出面板（能生成 / 下载 Story Bible、事实、章节结构的导出包），
或在产品内明确说明导出仍处于 API-only 阶段并提供可用替代入口。

**Actual** URL 变为 `#/story-builder?novel_id=qa_rich_novel&tab=export`，页面标题显示
「高级工具 · export」，正文区**没有任何面板内容**（截图中大片空白）。

**Evidence**

- 截图：`workspace/qa_review_2026_09_17/shots/probe_tab_export.png`（空白）、
  `shots/p9_01_export_package.png`。
- DOM 探针：`tab=export` 时 `.story-builder-page` 内文 469 字符，`[data-testid]` 只有
  `legacy-back-to-v3` / `story-builder-new-*` / `creator-stage-bar` / `tab-group-*`；
  对比 `tab=outline` 2976 字符、`tab=tree` 含 `outline-tree-panel`。
- 文案：页头「高级工具 · export」、状态条「我在：export ·」（后半段为空）。

**Probable Cause**

`ui/src/v3/WorkspaceView.tsx:666` 使用 `onClick={() => onOpenLegacy('export')}`，
而 `ui/src/guidedFlow.ts:11-16` 的 `CreatorTab` 联合类型与 `TAB_GROUPS`（同文件 29-72 行）
都没有 `export`；`labelOfTab()` 回退返回原始 key，渲染层没有匹配 `creatorTab === 'export'` 的面板，
于是渲染空内容。`ui/src/v3/WorkspaceView.tsx:659` 的文案「真正的导出包在既有导出面板」描述的
这个面板在仓库中并不存在。

**Suggested Fix**（不要在 Review 分支实施）

二选一，并明确产品边界：

1. 在 legacy 侧新增真正的导出页签（消费 `GET /api/story-builder/export/package` 与
   `GET /export/writer-bundle`），并把 `'export'` 加入 `CreatorTab` 与 `TAB_GROUPS`；
2. 或把导出工作区的主 CTA 改为在产品内直接调用导出 API（下载包），文案同步去掉「既有导出面板」。

**Acceptance Criteria**

- 点击导出工作区主 CTA 后，页面必须渲染可交互的导出面板 / 导出结果，且能看到导出包内容或下载入口；
- `labelOfTab('export')` 不再返回英文 key；
- 新增门禁断言「导出 CTA 之后内容区非空」。

---

### NF-002

**Severity** P1

**Module** Export Workspace / Writer Integration / v3_projection

**Problem** 最后一个目标「导出并开始写作 / 已有写作草稿」在 UI 中**无法完成**：前端没有任何创建写作
草稿的入口；且 `WriterDraftService` 写盘的目录与 V3 投影读取的目录不是同一个，
即使通过 API 创建草稿，投影仍报告 `writer_drafts = 0`，导出阶段永远 `0 / 1`，
总体进度天花板 51%（22 / 43）。

**Reproduction**

1. UI 走完 `qa_rich_novel` 的 Creation → 推演 → 大纲 → 检查；查看 Command Center：51%，7 / 8 阶段，
   导出阶段「进行中 0/1」。
2. 检索 `ui/src` 中的 writer / draft 调用 → 除 `api.ts` 的一个类型字段外没有任何调用（无 UI 入口）。
3. 直接调用 API 创建草稿：
   `POST /api/story-builder/writer/drafts`，body
   `{"novel_id":"qa_rich_novel","branch_id":"main","narration":"…","style":{}}`
   → 201，`draft_id=draft_overview_78ee978eb76e6fd0`。
4. 再次请求 `GET /v3/novels/qa_rich_novel/command-center` → `facts.writer_drafts = 0`，
   export 阶段仍 `0 / 1`。

**Expected** 作者能在产品内产生写作草稿（或明确该能力不在 V3 范围），并让导出阶段真实可完成。

**Actual** 无 UI 入口；API 写入的文件在投影眼里不存在。

**Evidence**

- 写盘位置（真实存在）：
  `workspace/qa_review_2026_09_17/root_fresh/workspace/wasteland_001_exports/writer_v1/qa_rich_novel/index.json`
- 读取位置（不存在）：`workspace/qa_review_2026_09_17/root_fresh/novel/authoring/writer` → `False`
- `facts.writer_drafts = 0`、`export.steps` 中「已有写作草稿」缺项、`progress = 51%`。

**Probable Cause**

- 读取：`src/novelforge/story_builder/v3_projection.py:217-229` `_writer_drafts()` 读
  `novel/authoring/writer/<novel_id>/index.json`。
- 写入：`src/novelforge/story_builder/writer_integration.py:48`
  `WRITER_DIR = "workspace/wasteland_001_exports/writer_v1"`，service 把它拼成
  `<root>/workspace/wasteland_001_exports/writer_v1/<novel_id>/index.json`。
- 同一个语义对象存在两个目录来源，且从未对齐。

**Suggested Fix**

统一 writer draft 的 canonical 存储位置（例如都走
`novel/authoring/story_engine/writer/<novel_id>/index.json`），并提供最小 UI 入口
（导出工作区 → 创建 / 查看草稿）；或把该目标从 V3 目标体系中移除并在 UI 明确说明。

**Acceptance Criteria**

- 在 UI 里创建一次写作草稿后，Command Center 的「已有写作草稿」变为已完成、导出阶段 `1/1`，
  总体进度上升；
- 该草稿在刷新与重启后仍可读；
- 新增测试断言「service 写入路径 == 投影读取路径」（同源常量）。

---

### NF-003

**Severity** P2（生成内容不可用，直接决定产品价值）

**Module** Outline Forge（生成质量）

**Problem** 锻造出的四级大纲中，绝大多数「规划章节」标题是内部字段标签占位：
`第N章：阶段目标（规划）` / `第N章：长期方向（规划）`，且已发生章节之间也高度重复。

**Reproduction**

1. 新作品 → Creation → 生成方向候选 → 确定方向 → 生成设定候选 →（逐组选择或直接）保存 →
   自检 → 开始推演。
2. 推演 1–3 次。
3. 大纲 → 生成章节大纲 → 锻造四级大纲（3 卷 / 2 篇 / 5 章）。
4. 查看 30 章标题，或 `GET /api/story-builder/outline/export?novel_id=<id>&branch_id=main&format=markdown`。

**Expected** 每章标题能表达「这一章要发生什么」（人物 + 目标 + 冲突），同级章节之间不应同名。

**Actual**

```text
qa_rich_novel（修仙、9 组设定全选）：第 9–30 章全部叫「阶段目标（规划）」= 22/30
qa_acceptance_novel（未选设定）：24/30 在「阶段目标（规划）」「长期方向（规划）」之间交替
另外：第 2/3 与第 7/8 章同名「先观察，不急着介入」；第 4/5 章同名「世界表层规则的分配方式被单方面调整」
```

**Evidence**

- 截图：`shots/p7_06_outline.png`、`shots/p11_02_outline_after_change.png`。
- 导出文件：`GET /outline/export?...&format=markdown` → `剧情与大纲_qa_acceptance_novel_main.md`
  （12412 字符，其中 22 章同名段）。
- 章纲 JSON：`novel/authoring/story_builder/outlines/chapter/ol_forge_..._ch007/v000001.json`
  → `"title": "第7章：阶段目标（规划）"`，
  `"must_keep": ["来源：future_plan:main_7f2dd4b4（planned，尚未发生）", …]`。

**Probable Cause**

- `src/novelforge/story_engine/outline_forge.py:546`
  `title=f"第{...}章：{stage.title}（规划）"`：所有规划章节共享 `future_plan` 里同一个 stage 的 title。
- `src/novelforge/story_engine/settings_gen.py:234-235`：主线候选把**字段标签**
  （「阶段目标」「长期方向」）写成了 `future_plan.stages[].title`。
- `outline_forge.py` 同一段：summary 直接拼「阶段名 + goal + 前提句」，形成模板段落。

**Suggested Fix**

把「章节标题」当成需要真实语义的字段：至少组合 `行动 / 事件名 + 目标 + 章节序`，并对同名章节做
差异化（例如按 plot、foreshadow、pacing 生成不同角度的标题）；`future_plan` 的 stage label
不应直接出现在标题里（label 属于 UI 文案，不是内容）。

**Acceptance Criteria**

- 同一作品 30 章中，同名标题为 0（「同名 + 序号」不算重复）；
- 章节标题不得等于「阶段目标」「长期方向」「阶段N」这类字段标签；
- 新增回归断言：`len(set(titles)) == len(titles)`。

---

### NF-004

**Severity** P2

**Module** Outline / Chapter projection / Export serializers

**Problem** 内部实现标识与机械拼装文本泄漏到作者可见内容（V3 主界面 + 导出文件 + 错误提示）。

**Reproduction**

1. 打开 `#/n/qa_rich_novel/outline`，查看章节卡副标题 → 出现 `start_place`。
2. 打开 `GET /api/story-builder/outline/export?...format=markdown` → 出现 `ev_world_shift`、
   「来源：来源：」、「favors 消耗 1」。
3. 推演到资源不足 → 提示「需要 protagonist 的 favors >= 1份（当前 0.0）」。

**Expected** 主界面与导出物只出现作者语言（「起点场所」「人情」「主角」），内部 id 不出现在任何
作者可见文本中；同一 id 的翻译在所有位置一致。

**Actual** 实测命中：

```text
V3 主界面（大纲工作区）：第1卷 · 篇章1：完成 向身边人打听 · tick 0 · start_place
导出 markdown：转折：ev_world_shift / 来源：来源：main 路线（revision 1）/ favors 消耗 1
章纲 must_keep：来源：future_plan:main_7f2dd4b4（planned，尚未发生）
推演提示：需要 protagonist 的 favors >= 1份（当前 0.0）
```

**Evidence**

- DOM 扫描（`journey8_leaks_persistence.cjs`）：8 个工作区中只有 `outline` 命中
  `实体id: ["start_place"]`，其余 7 个为空。
- 导出 markdown 原文节选见第 8.3 节。
- 注意：项目自己的 P6 门禁 `INTERNAL_ID_PATTERN` 已包含 `start_place`，但它只在大纲锻造**之前**
  扫描工作区，因此没有覆盖到已经锻造出章节的状态（NF-020）。

**Probable Cause**

- `outline_forge.py:551` `participants=[next(iter(state.characters), "protagonist")]` 直接把内部
  角色 key 写进章节字段；`must_keep` 直接写 `future_plan:{stage.id}`。
- 章节卡副标题由投影把 location 原样输出（未做名称映射）。
- 导出序列化器把 domain 字段（`turn`、`costs`）直接渲染成作者文本。
- 文案层多处各自加前缀（`已解锁：` + `解锁：`、`来源：` + `来源：`）。

**Suggested Fix**

在应用层建立**唯一的内部标识 → 作者语言映射**（地点 / 角色 / 资源 / 事件 / 来源），
投影与导出都走它；domain 字段进入展示前必须先映射，映射缺失时退化为可读描述而不是原始 id。

**Acceptance Criteria**

- 在「已有 30 章大纲 + 已推演 3 回合」的数据状态下，8 个工作区与 3 种导出格式中内部 id 命中数为 0；
- 同一资源 / 角色在不同位置的显示名一致。

---

### NF-005

**Severity** P2

**Module** Novel Landing（`novel_card` / `_light_stage`）

**Problem** 入口页存档卡与作品内 Command Center 对同一本作品给出不同的阶段、进度与下一步。

**Reproduction**

1. 准备 3 本作品（`qa_rich_novel` 已锻造 30 章、`qa_acceptance_novel` 已锻造 30 章、
   `qa_edge_a1` 仅保存简报）。
2. 对比 `GET /api/story-builder/v3/novels` 与 `GET /api/story-builder/v3/novels/{id}/command-center`。
3. 或直接在 Landing 与 Command Center 界面上对比。

**Expected** 同一本书在任何入口都显示同一阶段、同一进度、同一下一步。

**Actual**

```text
qa_rich_novel        Landing: 大纲 81%   «继续生成章节大纲»   | CC: 导出 51% «导出并开始写作»
qa_acceptance_novel  Landing: 大纲 25%   «继续生成章节大纲»   | CC: 导出 44% «导出并开始写作»
qa_edge_a1           Landing: 世界  6%   «生成设定候选»      | CC: 世界 11% «建立世界规则»
```

**Evidence**

- `shots/p6_06_landing_multi.png`（卡片显示 25% / 继续生成章节大纲）与
  `shots/p7_06_outline.png`（同一本书内 51% / 导出）对比。
- 两次 API 调用输出（见第 8.1 节表格）。

**Probable Cause**

`src/novelforge/story_builder/v3_projection.py` 的 `novel_card()` / `_light_stage()`：

- 用自定分母 `steps = 4 + total_groups + 3` 计算百分比，与 `command_center()` 的 objective 统计
  （43 项）不是同一套；
- 一旦存在 book，就固定输出下一步「继续生成章节大纲」，不考虑「章节已生成 / 已确认」。

**Suggested Fix**

Landing 卡片复用 `command_center()` 的 stage / objective 结果（可做只读裁剪以避免列表页昂贵计算，
但不能有第二套语义），或至少让 `novel_card()` 调用同一个 stage / objective 计算函数。

**Acceptance Criteria**

- 对同一本书，Landing 卡片与 Command Center 的阶段、进度、下一步完全一致
  （覆盖边界状态：只存简报 / 已推演未锻大纲 / 已锻大纲 / 大纲过期）；
- 新增测试：`novel_card(...)["progress_percent"] == command_center(...)["progress"]["percent"]`。

---

### NF-006

**Severity** P2

**Module** Settings seed / Content pack title

**Problem** 作品标题由创意句**截断**生成并追加「（设定草稿）」，截断点落在词中间；
该字符串出现在高级工具的小说下拉、导出内容清单等作者可见位置。

**Reproduction**

1. 用创意「一个边陲小城的铸剑学徒，在师父被杀之后发现剑炉里封印着一条会说话的龙，
   而全城的兵器都要靠这条龙的血脉维持。」创建作品并完成设定。
2. 打开 `#/story-builder?...&tab=outline`（或导出工作区的「会导出什么」）。

**Expected** 标题应为作者可读的短名（例如取创意首句或让作者确认），不应在词中间被切断。

**Actual**

```text
一个边陲小城的铸剑学徒，在师父被杀之后发现剑炉里封印着一条会（设定草稿）
一个在废土上修水管的维修工，发现整座城市其实运行在一套隐藏的（设定草稿）
```

**Evidence** `shots/p9_02_legacy_export.png`、导出工作区「设定与内容包」行、
`novel/config/story_engine/qa_acceptance_novel_pack.json` 的 `title` 字段。

**Probable Cause** `src/novelforge/story_engine/settings_gen.py` 生成 pack 标题时按固定长度
切分 `original_idea` 并拼接「（设定草稿）」。

**Suggested Fix** 用「首句 + 省略号」或让作者确认作品名；标题字段与「设定草稿」状态分离
（状态用 badge 表达，不写进名字）。

**Acceptance Criteria** 内容包标题不以字符中间截断结尾；「（设定草稿）」不再作为名称的一部分。

---

### NF-007

**Severity** P2（INCOMPLETE IMPLEMENTATION）

**Module** AI / Model wiring

**Problem** 文档承诺「配置 API key 可启用模型相关功能（设定候选 / 写作提议）」，但生产服务没有接入
任何 LLM provider，配置与不配置完全一致。

**Reproduction**

1. `.env.local` 中已有 `DEEPSEEK_API_KEY`、`ARK_API_KEY`。
2. `POST /api/story-builder/creative/suggest?novel_id=qa_acceptance_novel`，body 为一句创意。

**Expected** 配置 key 后候选 / 草稿由模型参与生成（或文档明确说明当前版本为纯规则生成）。

**Actual** 响应为 `{"source":"rule","notes":["AI_UNAVAILABLE"],…}`；`src/` 中没有任何实现
`StructuredRecommendationProvider.generate_structured` 的类。

**Evidence** API 响应；`src/novelforge/api/app.py` 中 `install_story_builder_api(app, ROOT)`
（无 provider 参数）；`README.md` 与 `.env.example` 的相关文案。

**Probable Cause** 应用入口从未构造 provider；LLM 只存在于 Protocol、测试替身与离线类
（`spec/llm.py`、`planning/*`），未接入产品路径。

**Suggested Fix** 二选一：
(a) 增加 provider 工厂（读取 `.env.local`，失败时回退规则并记录 note）；
(b) 修改 README / .env.example，明确「当前版本所有生成均为本地规则生成，模型接入是后续版本能力」。

**Acceptance Criteria** 文档描述与实际行为一致；若接入模型，`source` 与 `notes` 能反映真实来源，
且离线 / 无 key 时仍能完整走通流程。

---

### NF-008

**Severity** P2

**Module** Simulation Workspace

**Problem** 资源耗尽后，主 CTA 仍推荐同一个不可执行行动，点击必然 422；错误文案暴露内部键。

**Reproduction**

1. `qa_rich_novel` 推演工作区 → 点主 CTA「推演「向身边人打听」」两次（成功，favors 2 → 0）。
2. 再点同一 CTA。

**Expected** 主 CTA 应切换到当前可执行的方向（其他「可行方向」卡），或在不可执行时禁用并说明原因。

**Actual** 反馈为「这次推演没有执行 / 需要 protagonist 的 favors >= 1份（当前 0.0）/
故事状态没有被修改；可以换一个方向或先补齐前置条件。」，主 CTA 文案不变。

**Evidence** `out_journey7.txt` 的 `simulation-advance-x4` 段（advance 3、4）；
`shots/p7_04_simulation_*.png`；network 422 `POST /runtime/advance?novel_id=qa_rich_novel`。

**Probable Cause** 主 CTA 取自投影候选排序的第一条（未按「当前可执行」过滤），
错误文案由 domain 直接拼装资源键。

**Suggested Fix** 主 CTA 只在「可执行」候选中取第一条；不可执行候选置灰并说明缺什么
（用作者语言「人情」而不是 `favors`）。

**Acceptance Criteria** 主 CTA 点击后不再出现 422；连续推演 5 次仍能持续推进，
或明确提示「当前没有可执行方向」。

---

### NF-009

**Severity** P2

**Module** Creation Journey

**Problem**「确定这个方向」保存成功后仍停留在创意面板，主 CTA 没有推进向导；用户必须自己发现
步骤条上的「2 设定与起点」或右下角目标按钮。

**Reproduction**

1. 创作工作区 → 填创意 → 生成方向候选 → 点「确定这个方向」。
2. 观察面板内容。

**Expected** 保存后自动进入「设定与起点」步骤（或至少在 CTA 位置给出明确的「继续到下一步」按钮）。

**Actual** 仍显示创意卡（创意输入框、候选、「确定这个方向」按钮），只有顶部步骤条变成
「2 设定与起点 当前」，反馈条写「创意已经确定…下一步：建立世界规则」。

**Evidence** `out_journey2.txt` 的 `save-brief` / `settings-step` 段（`v3-flow-settings` 未出现、
`v3-settings-suggest` 定位超时）；`shots/p2_02_brief_saved.png`。
另证：项目自身的 P6 门禁也必须在保存后显式点击 `v3-flow-step-settings` 才能继续，
说明这是产品行为而不是测试脚本特例。

**Probable Cause** `ui/src/v3/CreationFlow.tsx`：保存简报后只更新 draft 与反馈，
`step` 仍为 `'idea'`（步骤推算只在挂载 / 深链接时发生）。

**Suggested Fix** 保存成功后切到设定步骤，或把主 CTA 直接替换为「下一步：设定与起点」。

**Acceptance Criteria** 点击「确定这个方向」后，同屏出现设定步骤的内容与主 CTA。

---

### NF-010

**Severity** P3

**Module** Creation Journey（草稿持久化）

**Problem** 创意文本与候选只在「确定这个方向」之后才落盘；在此之前刷新 / 离开会全部丢失，
且界面没有任何提示。

**Reproduction**

1. 填创意 → 点「生成方向候选」→ 得到候选。
2. 刷新页面，或切换到别的作品再回来。

**Expected** 至少保留草稿（或明确提示「未保存」）。

**Actual** 创意输入框为空、候选消失、「确定这个方向」变灰；服务端
`GET /creative/brief` 返回 `{"brief":null,"suggestion":null}`。

**Evidence** `out_journey1.txt` / `out_journey2.txt` 的 `creation-idea-step`（textarea 值为空）；
API 响应；代码注释「生成一次候选；不写任何内容，保存由 save_creative_brief 负责」。

**Suggested Fix** 前端草稿缓存 + 恢复提示，或服务端增加「未确认候选草稿」层
（与已保存状态区分）。

**Acceptance Criteria** 刷新后创意文本与候选可恢复（或在 UI 上明确「未保存」状态）。

---

### NF-011

**Severity** P3

**Module** Novel management

**Problem** 作品无法重命名、无法删除（Landing 与 API 都没有入口 / 接口）。

**Reproduction** Landing → 任意作品卡；检查前端 DELETE 调用与后端路由列表
（`/api/story-builder` 下无 delete）。

**Expected** 至少提供「删除作品」（带确认）与「重命名」；或明确产品不提供。

**Actual** 只有 `POST /novels`、`GET /novels`、`GET /novels/{id}`；作品列表只增不减。

**Evidence** `out_journey6.txt` 的 `delete-affordances`：`deleteLabels: []`。

**Suggested Fix** 增加删除 / 重命名（软删除 + 确认对话框；避免孤儿数据）。

**Acceptance Criteria** 能删除测试作品且不留下孤儿大纲 / 状态文件；删除有二次确认。

---

### NF-012

**Severity** P3

**Module** Export readiness projection / copy

**Problem** 就绪度文案自相矛盾：存在 blocker 时标题写「还差 0 步就可以导出」，
左侧状态写「先补上：缺失步骤」（实际没有缺失步骤，阻塞项是大纲过期）。

**Reproduction**

1. 锻造并确认大纲。
2. 再推演一次（上游改变）。
3. 打开导出工作区。

**Expected** 文案应说明真正的阻塞：「大纲已过期，需要先重新锻造」。

**Actual**

```text
导出进度 0%
先补上：缺失步骤
能不能交给写作环节 → 还差 0 步就可以导出
（下方：）故事推进过，大纲需要重新锻造后才能导出。
```

**Evidence** `shots/probe_export_stale.png`；`command-center` 的
`export.ready=false`、`missing=[]`、`blockers=["故事推进过，大纲需要重新锻造后才能导出。"]`。

**Probable Cause** headline 只由 `missing` 长度决定，未考虑 `blockers`；
左侧状态标签在 `missing` 为空时仍使用「缺失步骤」文案。

**Suggested Fix** headline 与状态标签优先读 `blockers`。

**Acceptance Criteria** blocked 状态下的标题与状态标签能指出「大纲需要重新锻造」。

---

### NF-013

**Severity** P3

**Module** World Workspace

**Problem** 地点卡重复标签：「控制方 控制方未知」（标签与值都以「控制方」开头）。

**Reproduction** `#/n/qa_rich_novel/world` → 查看「关键地点 → 隐藏节点」。

**Evidence** `out_journey7.txt` 的 `workspace-world` 段；`shots/p7_06_world.png`。

**Suggested Fix** 值层去掉「控制方」前缀（值应为「未知」或具体势力名）。

**Acceptance Criteria** 卡片文案不含重复前缀。

---

### NF-014

**Severity** P3

**Module** Advanced Tools header

**Problem** legacy 高级工具页把内部 tab key 直接展示给作者：「高级工具 · export」、
「我在：export ·」。

**Reproduction** 打开 `#/story-builder?novel_id=<id>&tab=export`（即 NF-001 的落点）。

**Evidence** `shots/probe_tab_export.png`；代码 `ui/src/guidedFlow.ts` 的 `labelOfTab()`
在找不到时返回原始 key，`ui/src/StoryBuilderPage.tsx` 直接拼接显示。

**Suggested Fix** `labelOfTab` 未知 key 时返回「未知工具」或重定向到有效页签。

**Acceptance Criteria** 界面不再出现英文 tab key。

---

### NF-015

**Severity** P3

**Module** Simulation Workspace / candidate cards

**Problem** 「可行方向」卡片标题被截断：显示「向身边人...」「查证与「发...」「先观察， ...」，
类型徽章（交涉 / 调查 / wait）紧贴被截断的标题。

**Reproduction** `#/n/qa_rich_novel/simulation` → 查看「可行方向」。

**Evidence** `shots/p3_20_simulation_after_advance.png`。

**Suggested Fix** 允许标题两行显示，或显示完整行动名并把徽章换行。

**Acceptance Criteria** 主要行动名完整可读。

---

### NF-016

**Severity** P3

**Module** Settings seed / entity naming

**Problem** 人物、地点、势力只有原型标签，没有名字，例如主角叫「普通执行者」、
配角「掌握线索的同行者」、「势力·资源控制方」、「隐藏节点」。

**Reproduction** 任意作品 → 世界 / 角色工作区、大纲章节卡。

**Evidence** `out_journey7.txt` 的 `settings-pick-every-group` 与 `workspace-characters / world` 段；
`shots/p7_06_characters.png`。

**Suggested Fix** 设定候选至少给出一个可编辑的名字（NPC / 地点 / 势力名），或明确标注这些是占位。

**Acceptance Criteria** 角色 / 地点 / 势力在 UI 与导出中有可区分的名字。

---

### NF-017

**Severity** P4

**Module** Feedback copy

**Problem** 重复前缀：「已解锁：解锁：世界与角色候选」「来源：来源：」。

**Evidence** `out_journey1.txt`、导出 markdown 原文。

**Probable Cause** 投影提供「解锁：…」，组件又拼「已解锁：」；
导出序列化器拼「来源：」+ 已含前缀的字段。

**Suggested Fix** 前缀只在展示层加一次。

---

### NF-018

**Severity** P4

**Module** Documentation / tooling

**Problem** README 记录的 `npx.cmd --prefix ui tsc --noEmit` **不执行类型检查**，
而是打印 tsc 帮助（退出码非 0），容易被误认为「通过」。

**Reproduction** 在仓库根执行该命令 → 输出
`tsc: The TypeScript Compiler … COMMON COMMANDS`；在 `ui/` 下执行
`node_modules\.bin\tsc.cmd --noEmit` → PASS（exit 0）。

**Suggested Fix** 文档改为 `npm.cmd --prefix ui exec tsc -- --noEmit` 或 `cd ui; npx tsc --noEmit`。

**Acceptance Criteria** 按文档命令执行能真实得到类型检查结果与正确退出码。

---

### NF-019

**Severity** P4

**Module** Frontend dev dependencies

**Problem** `npm audit` 报告 2 个漏洞（esbuild ≤0.24.2 moderate、vite 相关 high），
仅影响本地 `vite dev server`（产品以构建产物 + FastAPI 提供服务）。

**Evidence** `npm.cmd audit --prefix ui` 输出（自动修复需要 vite@8 破坏性升级）。

**Suggested Fix** 下个版本集中升级 vite；文档说明风险仅限本地 dev server。

---

### NF-020

**Severity** P3

**Module** Acceptance gates（盲区）

**Problem** 现有浏览器门禁全部 PASS，但漏掉了本报告里最严重的几条问题；说明门禁覆盖不足，
修完之后容易再次回归。

**Evidence**

- `tests/browser_v3_p5_acceptance.cjs` 导出 bridge 段只断言 `legacy-back-to-v3` 存在，
  **不断言导出面板渲染** → 漏掉 NF-001。
- `tests/browser_v3_p6_acceptance.cjs` 在「锻造大纲之前」扫描工作区内部 id → 漏掉
  `start_place` 泄漏（NF-004）。
- P6 的 Creation 主链使用显式步骤跳转，掩盖了「确定这个方向不推进」（NF-009）。
- 没有任何门禁比对 Landing 卡片与 Command Center（NF-005），也没有断言章节标题唯一性（NF-003）、
  writer draft 路径一致性（NF-002）。

**Suggested Fix** 按「数据最丰富的状态」重组门禁：先构造含 30 章大纲 + 多次推演的作品，
再扫描每个工作区的 id 泄漏、标题唯一性与跨入口一致性；导出 CTA 必须断言内容非空。

**Acceptance Criteria** 上述断言加入门禁，且在修复前必然 FAIL（能复现本轮问题）。

---

## 13. Incomplete Implementations

| 位置 | 现象 | 关联 |
| --- | --- | --- |
| 导出工作区 →「生成导出包」 | 目标页签不存在，页面空白；「既有导出面板」在仓库中不存在 | NF-001 |
| 写作草稿 / 写作环节 | UI 无入口；API 写入与投影读取路径不一致；最后一步目标不可达 | NF-002 |
| LLM provider | `StructuredRecommendationProvider` 无实现类；服务恒传 `provider=None`；文档承诺与实现不符 | NF-007 |
| 章节标题生成 | 用内部字段标签当作章节名 + 同名占位 | NF-003 |
| 内部标识映射 | 部分位置翻译（`favors → 人情 ×1`），部分位置原样输出（`favors`、`protagonist`、`start_place`） | NF-004 |
| Landing 进度 | 第二套阶段 / 进度计算，且 next action 硬编码 | NF-005 |
| 内容包标题 | 直接截断创意句 +「（设定草稿）」 | NF-006 |

---

## 14. Regression Risks

1. **修 NF-001 / NF-002 会触及产品边界**：导出面板是否存在、写作草稿归谁管，属于 V3 能力边界；
   若上游选择「V3 不提供导出面板」，应同步修改 V3 文案、目标体系与验收 artifact，
   不能只改按钮跳转（否则产生「看起来能导出」的更大误导）。
2. **修 NF-003 / NF-004 会改生成内容**：`outline_forge` 的标题 / 摘要 / 来源字段同时被 legacy 面板、
   V3 投影、导出序列化器与既有测试消费；改动必须同步更新这些测试与相关文档声明。
3. **修 NF-005 会改 Landing 性能特征**：`_light_stage()` 的存在是为了避免列表页做昂贵自检；
   改为复用 `command_center()` 时必须保留「列表页不跑自检」的性能边界（可用缓存 / 轻量裁剪）。
4. **writer draft 目录调整会影响历史数据兼容**：`workspace/wasteland_001_exports/writer_v1`
   是历史路径（gitignored，但可能已被作者使用）；须保留读取兼容或提供迁移。
5. **门禁改造（NF-020）必须在修复之后同步收紧**：否则「修完即回归」的概率很高。
6. `docs/V3_FULL_PRODUCT_ACCEPTANCE.json` 与默认 pytest 命令的数字口径不一致，
   修复工作包结束时需要重新生成一次 release 证据，避免继续引用无法复现的历史数字。

---

## 15. Recommended Fix Order

只按**依赖关系与阻断关系**排序：

```text
NF-002（写作草稿：路径统一 + 产品边界）
   ↓
NF-001（导出面板：实现 or 改 CTA 目标，取决于 NF-002 确定的产品边界）
   ↓
NF-020（门禁补齐：把 NF-001/002/003/004/005 变成可复现断言）
   ↓
NF-003 → NF-004 → NF-006（生成内容 canonical 化：标题语义、id 映射、标题字段）
   ↓
NF-005（Landing 复用同一套 stage / objective 计算）
   ↓
NF-007（模型接线 or 文档降级，二选一并同步 README / .env.example）
   ↓
NF-009 → NF-008（Creation / Simulation 主路径可用性）
   ↓
NF-012 → NF-010 → NF-011 → NF-013 → NF-014 → NF-015 → NF-016（体验与文案）
   ↓
NF-017 → NF-018 → NF-019（文案与工程文档）
```

依赖说明：

- NF-001 依赖 NF-002：先确定「导出 = 产品内面板」还是「导出 = API / 大纲导出」，否则修完仍会返工。
- NF-020 必须在 NF-001–NF-005 修复后立刻做，否则回归无法被拦住。
- NF-003 与 NF-004 属同一层（生成内容 canonical 化），可同一工作包完成；NF-006 紧随其后。
- NF-005 独立，但落地前需要 NF-003 / NF-004 的输出稳定，避免把占位内容判为「已完成」。

---

## 16. Acceptance Checklist

修复分支完成后，必须能重新执行并通过：

**启动与基础**

- [ ] `.venv\Scripts\python.exe scripts/start_novelforge_ui.py --port 8000` 启动成功，`/api/health` 正常
- [ ] `npm.cmd --prefix ui install` 与 `npm.cmd run build --prefix ui` 成功
- [ ] `.venv\Scripts\python.exe -m pytest -q` 全绿（0 failed）
- [ ] `.venv\Scripts\python.exe scripts/validate_project.py` PASS
- [ ] 在 `ui/` 下 `npx tsc --noEmit` PASS（README 文档同步修正）

**核心链路（隔离数据根，真实浏览器）**

- [ ] 空白数据根 → 新建作品 → 创意 → 候选 → 确定方向（**面板自动进入设定步骤**）→ 设定候选 →
      保存 → 自检 → 开始推演
- [ ] 推演 5 次：主 CTA 永远可执行或明确说明缺什么；不再出现 `favors` / `protagonist`
- [ ] 大纲：锻造 30 章 → 确认 → **30 章标题唯一且可读**（无「阶段目标（规划）」类占位）
- [ ] 大纲：再推演一次 → 正确提示「需要重新锻造」，导出就绪度文案与阻塞原因一致
- [ ] 检查工作区可读、无内部 id
- [ ] **导出工作区主 CTA 进入后内容区非空**，能看到导出包内容 / 下载入口
- [ ] **在 UI 内创建写作草稿 →「已有写作草稿」完成 → 总体进度 > 51%，导出阶段 1/1**

**一致性与边界**

- [ ] Landing 卡片 vs Command Center：阶段 / 进度 / 下一步三者一致（4 种边界状态）
- [ ] 刷新 / 新浏览器上下文 / 重启服务后数据一致且不丢
- [ ] 空输入 / 超长 / 中文 / 空格 / `../` / emoji / XSS 输入：不崩、不白屏、不穿越、有中文提示
- [ ] 连点主 CTA：无重复提交、无 console error
- [ ] 4 视口（1440 / 1280 / 1024 / 390）：0 横向溢出、主 CTA 可达

**门禁**

- [ ] P6 门禁在「已锻造大纲 + 已推演」的数据状态下扫描内部 id（0 命中）
- [ ] 导出 CTA 之后断言内容非空（P5 / P6）
- [ ] 新增断言：章节标题唯一、Landing 与 Command Center 数字一致、writer draft 读写路径同源

---

## 17. Final Conclusion

**当前版本还不能被认定为「可以正常使用」的 NovelForge。**

可以肯定的部分：工程状态健康（876 条默认测试全绿、`validate_project` PASS、前端可构建、
启动无报错）、数据结构清晰（设计态 / 已发生事实分层明确）、界面方向成立、数据能落盘能恢复、
非法输入处理稳健。

不能接受的部分：一个普通用户**无法完成一次「从设定到生成内容」的完整创作**——

- 生成的章节大纲 73%–80% 是同名占位，不能拿去写作；
- 大纲里混着引擎内部 id 与模板句；
- 出口（导出给写作环节）是空白页，最后一步目标在 UI 里根本点不到；
- 入口页与作品内对同一本书给出不同的进度与下一步。

也就是说：**这个产品现在可以「演示流程」，但还不能「交付小说素材」**。
建议把 NF-001 / NF-002 当作下一分支的第一优先事项（它们决定 V3 的产品边界），
随后用 NF-003 / NF-004 把生成内容变成真正的章节结构，最后按第 15 节的顺序收拾体验与文档。

---

# REPAIR HANDOFF

## MUST FIX

| ID | 标题 | 关键文件 |
| --- | --- | --- |
| NF-002 | 写作草稿读写路径不一致 + 无 UI 入口，最后一步目标不可达 | `src/novelforge/story_builder/v3_projection.py`、`src/novelforge/story_builder/writer_integration.py`、`ui/src/v3/WorkspaceView.tsx` |
| NF-001 | 导出主 CTA 落到不存在的 legacy 页签，页面空白 | `ui/src/v3/WorkspaceView.tsx:666`、`ui/src/guidedFlow.ts:11-72`、`ui/src/StoryBuilderPage.tsx` |

## SHOULD FIX

| ID | 标题 | 关键文件 |
| --- | --- | --- |
| NF-003 | 章节标题用内部字段标签占位，22–24 / 30 同名 | `src/novelforge/story_engine/outline_forge.py:546`、`settings_gen.py:234-235` |
| NF-004 | 内部 id / 机械拼装文本泄漏到界面与导出 | `outline_forge.py`、`v3_projection.py`、`export_package.py` |
| NF-005 | Landing 与 Command Center 阶段 / 进度 / 下一步不一致 | `src/novelforge/story_builder/v3_projection.py`（`novel_card` / `_light_stage`） |
| NF-006 | 作品标题被截断 +「（设定草稿）」 | `src/novelforge/story_engine/settings_gen.py` |
| NF-007 | 模型能力未接线但文档承诺可用 | `src/novelforge/api/app.py`、`README.md`、`.env.example` |
| NF-008 | 资源耗尽后主 CTA 仍推同一 422 行动 | `ui/src/v3/WorkspaceView.tsx`、v3 投影候选排序 |
| NF-009 | 「确定这个方向」不推进向导 | `ui/src/v3/CreationFlow.tsx` |

## POLISH

NF-010（创意草稿不落盘）· NF-011（无重命名 / 删除）· NF-012（导出文案自相矛盾）·
NF-013（「控制方 控制方未知」）· NF-014（显示裸 tab key）· NF-015（行动名截断）·
NF-016（人物 / 势力无名字）· NF-017（`已解锁：解锁：`）· NF-018（README 的 tsc 命令）·
NF-019（npm audit dev 依赖）· NF-020（门禁盲区，建议与 MUST FIX 同分支完成）

## 推荐修复顺序

```text
NF-002
  ↓  依赖：先确定「导出 / 写作」是否属于 V3 能力边界
NF-001
  ↓  依赖：产品边界确定后，立刻把二者写进门禁，避免回归
NF-020
  ↓  依赖：生成层 canonical 化，按同一批标题 / 命名逻辑一起修
NF-003 → NF-004 → NF-006
  ↓  依赖：内容稳定后再统一入口页语义，避免把占位内容判定为「已完成」
NF-005
  ↓  依赖：模型接线与文档必须二选一同步
NF-007
  ↓
NF-009 → NF-008
  ↓
NF-012 → NF-010 → NF-011 → NF-013 → NF-014 → NF-015 → NF-016
  ↓
NF-017 → NF-018 → NF-019
```

## 复现所需的证据文件

全部位于 gitignored 的 `workspace/qa_review_2026_09_17/`：

```text
out_journey1.txt ~ out_journey12.txt   QA 每一步的页面文本 / 交互元素 / 噪声报告
shots/                                 1440 与 390 视口截图（含 probe_tab_export.png 空白页）
root_fresh/                            本次使用的隔离数据根（profiles / pack / 30 章大纲 / StoryState）
*.cjs                                  本次编写的 QA 脚本（recon / journey* / probe*）
```

> 本报告不修改任何业务代码；上述问题均留给后续 Repair 分支处理。
