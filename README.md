# NovelForge

**NovelForge V4 — Story Blueprint Runtime + Story Studio**

> V4 是一个**故事蓝图（Story Blueprint）运行时与创作工作台**：用于生成、编辑、校验、
> 定向修复、评审、版本化、自动化与交付**结构化长篇故事方案**。
> 它不是「AI 小说正文写作器」——正文写作不是 V4 Core 的职责（见 §Non-goals）。
>
> V3 Final（`novelforge-product-v3-final`）是**冻结的历史基线**：V4 在其边界之上继续开发，
> 不修改其 frozen semantics（Canon / StoryState / legacy 源 / frozen Contract 与 Gate）。
> 旧历史版本（`novelforge-product-v3.0` / `novelforge-product-v2.0` / `story-engine-v2.0`）
> 已归档：**historical / archived / not an active Git ref**，完整恢复由外部 bundle
> `NovelForge_pre_V4_full_history.bundle` 承担，见 `docs/FROZEN_EVIDENCE_MANIFEST.json`。

## V4 核心能力

| 能力 | 说明 |
| --- | --- |
| Structured Story Blueprint | 有序节点图（premise / theme / world / character / arc / story arc / unit / chapter / scene / setup / payoff / causal link），append-only revision |
| LLM Gateway | 唯一模型入口：contract / 路由 / provider / 结构化输出 / retry / timeout / usage / trace / cache / secret 边界 |
| Memory / Context | 派生且可重建的检索与上下文装配（ContextBuilder 是唯一上下文选择系统） |
| Generation | 逐级结构化生成；AI 产出永远是 **proposal**，等待作者接受 |
| Q0–Q9 Quality Closed Loop | Gate-based（Schema / Integrity / Canon / Continuity / Character / Causality / Semantic / Structure / Setup-Payoff / Delivery Readiness）；**没有权威总分** |
| Targeted Repair | 最小范围 + preserve + 新 revision + verifier 确认才算解决；不可安全自动修复 → 需要作者决定 |
| Revisioned Blueprint Editor | 字段级 patch / AI 改写 / deterministic diff / accept / reject / restore（历史永不删除）/ revision 冲突 |
| Delivery / `.nfpack` | revision-pinned 交付：preflight → snapshot → manifest + checksum → 原子发布（JSON / Markdown / DOCX / nfpack，含插件 exporter 格式） |
| MCP | 官方 SDK 的薄适配层：机器端可读 Blueprint、生成 / 编辑 / 检查 / 交付（23 tools / 13 resources 基线） |
| Plugin Platform | 插件只经 Host 明确的扩展点追加能力：manifest → compatibility → approval → permission → contribution → adapter；Core 注册不可覆盖，disable 精确卸载 |
| Story Studio | V4 默认产品面：创造 / 世界 / 人物 / 故事 / 场景 / 检查 + 交付 / 插件 / Agent |
| Bounded Agent Mode | 目标 → 计划预览（0 mutation）→ 有界执行 → 审批 → 检查点 → 恢复；默认不自动接受、不自动交付 |

核心边界：

```text
规划不是事实：设计态（Blueprint proposal）与已发生事实（Canon / StoryState）严格分离。
AI 可以生成，但不能静默覆盖；作者始终掌握 accept / reject / restore。
UI 只展示后端返回的真相，不推导质量、接受状态或交付资格。
```

## Non-goals（V4 Core 不做）

```text
Full prose generation / prose polishing（正文写作与润色）
Untrusted plugin sandbox（进程级隔离；当前是 trusted in-process 模型）
Plugin marketplace / 远程插件安装
Distributed agent workers / 后台常驻自主循环
EPUB-first publishing（可作为未来的插件 exporter）
```

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

关于模型：V4-02 起所有模型调用统一经过 `src/novelforge/ai`（LLM Gateway：contract /
router / provider / 结构化输出 / retry / timeout / usage / trace / cache）。
但**默认不启用任何 provider**（`novel/config/ai/providers.json` 全部 `enabled=false`），
因此开箱行为仍然是「不调用模型」：题材 / 基调 / 卖点候选、设定候选、章纲等生成
依旧是本地确定性流程（响应的 `source` 恒为 `rule`，`notes` 含 `AI_UNAVAILABLE`）。
要接模型，按 `.env.example` 的说明启用 provider 并配置对应环境变量；
boundary 说明见 `docs/v4/V4_LLM_CONTRACT.md` 与 `docs/v4/adr/ADR-012-unified-llm-gateway.md`。

## 启动

```powershell
# 后端 + 已构建前端（首次会构建 UI）
.venv\Scripts\python.exe scripts/start_novelforge_ui.py --rebuild-ui
# 打开 http://127.0.0.1:8000/
```

## 创建小说（V4 Story Studio）

1. 打开 `http://127.0.0.1:8000/` → Story Studio Landing → **新建作品**。
2. **创造**：生成 / 撰写前提与主题（AI 产出为 proposal，需你接受）。
3. **世界 / 人物 / 故事 / 场景**：逐级生成或直接编辑；场景卡正面告诉你「这场戏为什么存在」。
4. **检查**：跑 Q0–Q9 质量门禁 → 看问题与证据 → 修复预览 → 执行 → 复核。
5. **交付**：选择 accepted / current → preflight → 交付 → 下载（JSON / Markdown / DOCX / nfpack）。
6. **Agent**（可选）：给出目标 → 先看计划（不修改任何内容）→ 执行 → 在需要时批准。

更多说明：`docs/NEW_NOVEL_GUIDE.md`、`docs/STORY_BUILDER_USER_GUIDE.md`、
`docs/NOVELFORGE_REAL_NOVEL_PRODUCTION_GUIDE.md`。

旧版界面仍可通过显式入口访问（兼容，不再是默认）：

```text
?ui=v3   → V3 工作台        #/v3… 同样进入 V3
?ui=v2   → V2 / Story Builder 面板（高级工具）
```

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

前端测试与构建（项目真实 scripts）：

```powershell
npm.cmd --prefix ui test        # vitest（组件 / 契约语义 / mocked HTTP）
npm.cmd run build --prefix ui   # tsc -b + vite build
```

V4 浏览器验收（真实 Edge + stub 模型，0 次真实模型网络调用）：

```powershell
.venv\Scripts\python.exe scripts/studio_ui_test_server.py --port 8040 --root workspace/studio_ui_test_root
$env:NODE_PATH = "$PWD\ui\node_modules"
node tests/browser_v4_studio_golden.cjs     # Story Studio golden（含真实下载）
node tests/browser_v4_11_agent.cjs          # Agent（plan → start → approval → complete）
node tests/browser_v4_legacy_entry.cjs      # 默认→Studio，?ui=v3→V3，?ui=v2→V2
```

历史 V3/V2 浏览器验收需要作者 acceptance data root（当前 workspace 不含该数据，
因此 V4-12 记为 **NOT RUN**，未降低任何旧断言）；入口已改为显式
`?ui=v3` / `?ui=v2`（`tests/browser_v3_*.cjs`、`tests/browser_creator_*.cjs`）。

已知依赖提示（非产品缺陷）：`npm.cmd audit --prefix ui` 会报告 2 条 vite / esbuild 相关
advisory（1 moderate、1 high）。它们只影响本地 `vite dev server`；产品以构建产物
（`ui/dist`）+ FastAPI 提供服务，因此不影响运行中的 NovelForge。修复需要 vite 大版本
升级（breaking change），按版本计划单独处理。

如果 Playwright 装在别的位置，用 `NODE_PATH` 指向你自己的 `node_modules` 即可。

## 可选：MCP（机器接口）

```powershell
.venv\Scripts\python.exe -m novelforge.interfaces.mcp    # stdio transport
```

MCP 与 REST 是**平级适配器**：两者都只调用 Application Services；MCP 不拥有业务逻辑，
Agent 也不通过 MCP 调业务。

依赖区间（V4-08 冻结，改动会触发完整回归）：

```text
mcp>=1.9,<2
sse-starlette<2
starlette<0.47
```

原因：MCP 2.x 目前与既有 FastAPI / Starlette 栈冲突。

## 安全模型（要点）

```text
模型 API key    只经环境变量 / 配置边界（ADR-013），不进入 artifact、日志或交付物
交付物          经过 secret scan；不导出 .env / Authorization / 私有绝对路径
插件            当前模型 = Trusted in-process：permission 控制的是 Host API 能力，
                不是 OS 安全沙箱（恶意 in-process 插件仍可直接访问解释器能力）
MCP             作用域受 Application Services 限制；显式 novel scope，跨作品拒绝
Agent           有界自治：默认不自动接受、不自动交付；protected action 需要作者批准
```

## Legacy / Previous Releases

```text
V3 Final — Functional Closure      tag `novelforge-product-v3-final`（V4 的冻结基线：
                                   边界、Canon / StoryState 语义、frozen Repair Contract 与
                                   Gate 均未改动）
V3.0 / V2.0 / Story Engine V2.0    已归档 historical / archived / not an active Git ref

V3 工作台与 V2 面板作为**显式兼容入口**保留（?ui=v3 / ?ui=v2），
其移除条件见 `docs/v4/V4_DELETION_PLAN.md`；
V4 迁移与验收证据见 `docs/v4/V4_12_EVIDENCE_INDEX.md`。
```

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
