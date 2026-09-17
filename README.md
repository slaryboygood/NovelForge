# NovelForge

**当前版本：NovelForge V3 Final — Functional Closure**（tag `novelforge-product-v3-final`）

> 历史版本（`novelforge-product-v3.0` / `novelforge-product-v2.0` / `story-engine-v2.0`）
> 已归档：**historical / archived / not an active Git ref**。
> 活动仓库是 V3 Final 的单一 root commit；旧历史的完整恢复由外部 bundle
> `NovelForge_pre_V4_full_history.bundle` 承担，见 `docs/FROZEN_EVIDENCE_MANIFEST.json`。

NovelForge 是一款**游戏化的长篇小说创作工作台**：作者从一句创意出发，做出设定、推演剧情、
比较路线、锻造四级大纲、检查一致性，最后把作品交给写作环节。

它不是一个「后台管理系统」，而是一个持续推进创作的流程：

```text
当前目标 → 下一步动作 → 状态变化 → 解锁下一阶段
```

## 能做什么

| 工作区 | 做什么 |
| --- | --- |
| 首页 / Command Center | 看作品当前状态、当前目标、下一步、需要留意的问题 |
| 创作 | 一句话创意 → 候选 → 设定 → 设定自检 → 开始推演 |
| 世界 | 关键地点与势力（含冲突、危险度、控制方） |
| 角色 | 主角与重要角色（定位、目标、关系） |
| 故事 | 剧情线、事件、伏笔与成长 |
| 推演 | 让故事往前走：真实候选方向、路线比较、世界影响 |
| 大纲 | 全书 / 卷 / 篇章 / 章节四级结构、缺口与警告、章节详情 |
| 检查 | 故事冲突与不一致；哪些需要处理、能否自动修、是否可逆 |
| 导出 | 还能不能交给写作环节、会导出什么、下一步 |
| 高级工具 | 既有面板（世界 / 角色 / 剧情 / 导演 / 路线实验室 / 大纲锻造 / Canon 检查 / 修复中心） |

核心边界：**规划不是事实**。设定、路线、大纲都是设计态；只有已经发生的
StoryState / Canon 才是事实。UI 只展示真实数据，不编造进度、风险或评分。

## 安装

需要 Python 3.11（64 位）与 Node.js 18+。

```powershell
# 一次性：创建 .venv、安装依赖、跑测试与项目校验
powershell -File scripts/bootstrap_dev.ps1

# 只装依赖
powershell -File scripts/bootstrap_dev.ps1 -SkipTests

# 前端依赖（构建 / 类型检查前需要）
npm.cmd --prefix ui install
```

关于模型：当前版本（NovelForge Product V3.0）**所有生成都是本地确定性流程**
（题材 / 基调 / 卖点候选、设定候选、章纲），产品路径没有接入任何 LLM provider。
`.env.example` 里的 `DEEPSEEK_API_KEY` / `ARK_API_KEY` 目前不会被使用——配置它们
与不配置**行为完全一致**（响应里的 `source` 恒为 `rule`，`notes` 含 `AI_UNAVAILABLE`）。
模型接入属于后续版本能力，届时会同时更新 README、`.env.example` 与 UI 文案。

## 启动

```powershell
# 后端 + 已构建前端（首次会构建 UI）
.venv\Scripts\python.exe scripts/start_novelforge_ui.py --rebuild-ui
# 打开 http://127.0.0.1:8000/
```

## 创建小说

1. 打开首页 → **新建小说** → 填作品编号。
2. 进入 **创作**：写一句话创意 → 选择候选 → 保存设定。
3. **设定自检** → 通过后 **开始推演**（起点事实写入 StoryState）。
4. 到 **推演** 推进故事，到 **大纲** 锻造四级大纲与章节。
5. 在 **检查** 看冲突，在 **导出** 生成给写作环节的包。

更多说明：`docs/NEW_NOVEL_GUIDE.md`、`docs/STORY_BUILDER_USER_GUIDE.md`、
`docs/NOVELFORGE_REAL_NOVEL_PRODUCTION_GUIDE.md`。

## 运行测试

```powershell
# 默认套件：当前产品测试（不需要任何本机作者数据）
.venv\Scripts\python.exe -m pytest -q

# 项目结构 / 目录校验
.venv\Scripts\python.exe scripts/validate_project.py

# 前端类型检查与构建
npm.cmd --prefix ui install
# 注意：类型检查要在 ui 目录里执行；`npx.cmd --prefix ui tsc` 只会打印 tsc 帮助文本
npm.cmd --prefix ui exec tsc -- --noEmit
npm.cmd run build --prefix ui
```

浏览器验收（Edge / Chromium；Playwright 由你自行安装，例如 `npm.cmd i -D playwright`）：

```powershell
.venv\Scripts\python.exe scripts/creator_ui_test_server.py --port 8030 --root workspace/v3_ui_test_root
node tests/browser_v3_p6_acceptance.cjs          # 全产品端到端
node tests/browser_v3_p7_acceptance.cjs          # 导出 / 写作草稿 / 内部 id / 入口一致性（Repair 新增）
node tests/browser_v3_visual_asset_gate.cjs      # 视觉资源契约
node tests/browser_advanced_tools.cjs            # 高级工具可达性
```

已知依赖提示（非产品缺陷）：`npm.cmd audit --prefix ui` 会报告 2 条 vite / esbuild 相关
advisory（1 moderate、1 high）。它们只影响本地 `vite dev server`；产品以构建产物
（`ui/dist`）+ FastAPI 提供服务，因此不影响运行中的 NovelForge。修复需要 vite 大版本
升级（breaking change），按版本计划单独处理。

如果 Playwright 装在别的位置，用 `NODE_PATH` 指向你自己的 `node_modules` 即可。

历史里程碑验收（V2 M11–M18 / wasteland / 570 章 historical）**已在 V4-01 随废弃资产一并删除**：
作者判定那批历史数据与旧正文没有保留价值，因此仓库里不再保留对应的数据、脚本与测试
（详见 `docs/v4/V4_DELETION_PLAN.md` §2.1 与 `docs/v4/V4_01_BOUNDARY_FOUNDATION_REPORT.md`）。
`historical_acceptance` marker 仍注册在 `pytest.ini`，留给 V4 里程碑验收复用。

V4 边界守卫（跨作品污染 / 废弃资产 / 模块依赖）现在默认运行：

```powershell
.venv\Scripts\python.exe -m pytest -q tests/v4 -q
```

## 文档

| 主题 | 位置 |
| --- | --- |
| 架构（Domain / Application / ViewModel / UI） | `docs/ARCHITECTURE.md` |
| 数据模型与 truth 分层 | `docs/DATA_MODEL.md` |
| 内容包 / 题材模板规范 | `docs/CONTENT_PACK.md`、`docs/GENRE_TEMPLATE.md` |
| 界面使用与新建作品 | `docs/STORY_BUILDER_USER_GUIDE.md`、`docs/NEW_NOVEL_GUIDE.md` |
| 真实长篇生产流程 | `docs/NOVELFORGE_REAL_NOVEL_PRODUCTION_GUIDE.md` |
| 兼容与 legacy 边界 | `docs/LEGACY_COMPAT.md` |
| 变更记录（release history） | `docs/CHANGELOG.md` |
| V3.0 验收结果 | `docs/V3_FULL_PRODUCT_ACCEPTANCE.json` |
| 视觉资源契约 | `docs/V3_VISUAL_ASSET_REQUIREMENTS.json` |

开发规则与发布边界见 `AGENTS.md`。

## 代码地图

```text
src/novelforge/story_engine/     领域层：StoryState / 行动-条件-效果 / 事件 / 伏笔 / 路线 / 大纲 / Canon / 修复
src/novelforge/story_builder/    应用层：创意与设定 / 会话与蓝图 / 导出 / Writer 集成 / Inspector / V3 投影
src/novelforge/api/              业务 API（FastAPI，唯一入口 /api/story-builder/*）
ui/src/v3/                       V3 工作台（Novel Landing / Command Center / 工作区 / Design System）
ui/src/                          既有面板（高级工具 bridge）
novel/config/                    题材模板、内容包、十步目录（数据，不是事实）
novel/authoring/                 作者产物（profiles / StoryState / 会话 / 大纲）——本地运行数据
scripts/                         启动、校验、隔离测试服务
tests/                           应用层测试 + 浏览器验收脚本
```
