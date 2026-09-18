# NovelForge V4 — Post-Release Full Repository Cleanup Inventory

> 状态：**V4_RELEASE（v4.0.0）之后的 Current-Tree 清理盘点**
> 分支：`v4-post-release-cleanup`　基线：`baa81ef39b8f4563923a28a2b2d2d28e77e423a4`
> 规则：**只整理 current tree**；不改 Git history、不移动 tag、不 force push（任务书 §2）。
> Decision 取值：`KEEP` / `MIGRATE` / `DELETE` / `LOCAL_DELETE` / `REVIEW_REQUIRED`
> 证据方法：`git ls-files` / `git check-ignore` / 静态 import-closure 扫描 / 运行期回归（pytest + 浏览器门禁）

## 0. 判定标准（任务书 §7/§97）

```text
DELETE 需要同时成立：
  没有 V4 runtime consumer
  没有 V4 test responsibility（保留的测试）
  没有 build / release responsibility
  没有 Contract / frozen evidence responsibility
  没有 active developer-tool responsibility
  不是唯一用户资料
  不是当前 story truth / config / persistence path
否则：KEEP（当前仍需） / MIGRATE（能力有用但 owner 属旧版本） / REVIEW_REQUIRED（可能是唯一用户资料）
```

名称不是证据：`v2` / `v3` / `legacy` / `runtime` 只是路径，不构成删除或保留理由（§8）。

## 0b. MCP Analysis Environment（任务书 §5/§89）

通过 `tool_search` 实测枚举本会话真实可用的 MCP，并逐一验证**是否可调用**：

| MCP server | capability | scope | read/write | used for | 实际可用性（实测） |
| ---------- | ---------- | ----- | ---------- | -------- | ------------------ |
| `figma` | 设计文件读取 / 设计系统搜索 / Code Connect | Figma 文件 | read + write | 不适用（本任务无 Figma 文件） | 已编目（design-only，与代码分析无关） |
| `node_repl` | JS 执行（可做文件/符号扫描） | 本地 | read + write | **本可作 E1 替代** | **`unsupported call`** —— 已编目但本会话不可调用 |
| `chrome_devtools` | 页面 console / network 检查 | 浏览器 | read | 不适用（无浏览器自动化需求） | **`unsupported call`** |
| `playwright` | `browser_navigate` | 浏览器 | read | 不适用 | 已编目但不在可调用集 |
| `codex_app`（内置） | 线程 / 项目 / 自动化 / 屏幕上下文 | Codex 应用 | read + write | 与本清理无关 | 可用（非代码分析工具） |
| `context7`（按 AGENTS.md） | 第三方库文档 | 文档 | read | 不适用（本任务无库 API 变更） | 未使用 |
| NovelForge 自身 MCP（`python -m novelforge.interfaces.mcp`） | 产品 machine-facing surface | 本仓库 | read + write | **§61/§62 surface before/after** | 可运行（进程内 registry 实测） |

```text
关键限制（必须显式记录，§89"cases where MCP disagreed with static search"）：
  本会话 **不存在 code-intelligence / language-server / symbol-reference MCP**。
  唯一与"引用分析"沾边的 node_repl/chrome_devtools 在本会话返回 `unsupported call`，
  因此 **E1（MCP/code-index references）在本环境不可获得**。

  按任务书 §7（"MCP 不足时必须补静态分析"）执行替代证据链：
    E1 → 由 Python AST import-closure（含相对 import 解析与字符串式动态引用）替代
    E2 → rg / git grep 全文引用
    E3 → 运行时 registry / FastAPI route installer / MCP registry 扫描
    E4 → pytest 套件 + acceptance contract + frozen guard
    E5 → git ls-files / check-ignore / FROZEN_EVIDENCE_MANIFEST

  因此：本环境 **E1 恒不可满足**；按 §10（HIGH 需要 E1+E2+E3+E4+E5 一致）
  剩余未执行删除的候选一律 **MEDIUM → REVIEW_REQUIRED**，不自动删除。
  已执行的两波删除（§3/§4/§5）的全部对象都满足：
    AST 闭包 = 0 消费者 ∧ rg = 0 消费者 ∧ 运行时 registry = 0 消费者
    ∧ 全套 pytest（1690 passed）+ 3 个浏览器门禁 + tsc/build 全绿 ∧ 无唯一用户数据
  —— 即 E2–E5 全部为空且被回归证明，E1 因环境缺失由闭包替代。
```

## 0c. MCP Surface Before / After（任务书 §61/§62/§75）

```text
NovelForge core MCP surface（进程内 registry 实测）：
  CORE TOOLS     = 23
  CORE RESOURCES = 13

tools：accept_revision, create_delivery_snapshot, deliver_blueprint, diff_revisions,
       evaluate_blueprint, generate_chapter_plan, generate_character, generate_character_arc,
       generate_premise, generate_scene_plan, generate_story_arc, generate_structural_unit,
       generate_theme, generate_world, patch_blueprint_node, plan_repair,
       regenerate_blueprint_node, reject_revision, repair_issue, restore_revision,
       rewrite_blueprint_node, validate_delivery, verify_repair
resources：blueprint, delivery, delivery-artifact, delivery-manifest, delivery-snapshot,
       interface, node, novel, quality, quality-issues, review, revision, scenes

after：与 before 完全一致（本轮未触碰 MCP adapter / registry / application facade；
       `pytest -q tests/acceptance` 中的 MCP baseline 断言 23/13 仍 PASS）。
```

## 1. 当前 V4 的真实消费面（先确定“谁是消费者”）

```text
运行时根（persistence/paths.py 的 ARTIFACT_KINDS + 唯一路径来源）：
  novel/authoring/story_engine/{profiles,state,canon,writer,planning,memory,blueprint,
                               quality,editor,delivery,plugins/state,agent/<novel_id>}
配置：
  novel/config/ai/providers.json                 LLM Gateway provider 配置
  novel/config/story_builder/step_catalogs.yaml   Story Builder catalog（create_app 读取）
  novel/config/story_engine/*.json                content pack（创作链）
入口：
  scripts/start_novelforge_ui.py、scripts/studio_ui_test_server.py、
  scripts/validate_project.py、scripts/bootstrap_dev.ps1
产品面：ui/src/studio/**（Story Studio），REST /api/story-builder/{studio,editor,delivery,agent}
```

## 2. Root audit（任务书 §5/§89）

| Path | Git state | Size | Current owner | Consumer（证据） | Regenerable | Unique data | Decision | Evidence |
| ---- | --------- | ---: | ------------- | ---------------- | ----------- | ----------- | -------- | -------- |
| `.agents/` | IGNORED | — | 本地 Codex skill 挂载点（`.agents/skills`） | 当前会话的 skill 根；删除会被权限拒绝且破坏工具链 | 是 | 否 | KEEP（本地） | 删除尝试返回 access denied → 属当前执行环境，不自毁（§10） |
| `.codex/` | IGNORED | — | 本地 Codex 运行目录 | 当前执行环境使用 | 是 | 否 | KEEP（本地，不入库） | 任务执行依赖；ignored |
| `.dsh-runtime/` | IGNORED | 663 MB | 本地工具运行时缓存（pnpm store） | 无 V4 runtime 读取；但当前 Codex 运行环境正在使用 | 是 | 否 | LOCAL_DELETE（本会话未执行） | 663 MB 可再生成缓存；**运行中的宿主 runtime，删除有破坏当前会话风险**（§10），留待环境空闲时清理 |
| `.python311/` | IGNORED | 63.7 MB | embedded Python 3.11 | `scripts/bootstrap_dev.ps1` 用它创建 `.venv` | 是 | 否 | KEEP（本地） | 脚本第 8/28/36 行硬编码 `.python311\python.exe` |
| `.venv/` | IGNORED | — | 当前开发/测试 Python 环境 | pytest / scripts / clean-install smoke | 是 | 否 | KEEP（本地） | 全流程验证依赖 |
| `docs/` | TRACKED(106) | — | 文档 | Contracts / ADR / 报告 / 证据 | 否 | 否 | KEEP（部分 SUPERSEDED/DEAD 见 §6） | 见 §6 |
| `novel/` | TRACKED(663) | — | 数据 | 只有 `authoring/story_engine/**`、`config/{ai,story_builder,story_engine}` 被消费 | 部分 | 否 | 见 §3 | 逐目录证据见 §3 |
| `reference_books/` | TRACKED(11) | — | 写作参考档案 | 无 V4 runtime 读取（`reference_books/*/source` 已 ignored） | 否 | **是（外部作品档案）** | REVIEW_REQUIRED | 任务书 §14/§64：不自动删用户资料 |
| `scripts/` | TRACKED(6) | — | 开发/验收工具 | 见 §5 | 否 | 否 | 部分 DELETE | 见 §5 |
| `skills/` | TRACKED(17) | — | Codex 开发 skill（非 NovelForge Plugin Platform） | V4 runtime 零消费；Codex 会话使用 | 否 | 部分（`skills/writing/*.md` 为作者笔记） | 部分 KEEP / 部分 REVIEW_REQUIRED | §16：两类概念不同 |
| `src/` | TRACKED(373) | — | 产品实现 | 见 §4 | 否 | 否 | 部分 DELETE | import-closure + 回归 |
| `tests/` | TRACKED(283) | — | 测试 | 见 §7 | 否 | 否 | 部分 DELETE | 分类见 §7 |
| `ui/` | TRACKED(86) | — | 前端 | Story Studio 为唯一当前产品面 | 否 | 否 | 部分 DELETE + MIGRATE | §8 |
| `workspace/` | IGNORED | — | 本地验收证据 + **作者写作材料** | 无 runtime 读取 | 部分 | **是（CH069/DEEPWRITE 等写作包）** | REVIEW_REQUIRED | 除 `studio_ui_review/`、`v4_12_ui_review/`、`pilot_v2/` 外的根级 `CH0xx_*` / `DEEPWRITE_*` 属作者内容 → §64 不自动删 |
| `.env.example` | TRACKED(1) | — | 环境变量示例 | README / provider 配置说明 | 否 | 否 | KEEP | 当前 LLM Gateway 需要 |
| `.env.local` | IGNORED | — | 本机覆盖配置 | `create_app` 不读取（仅 provider 环境变量） | 是 | 否 | LOCAL_DELETE | `.gitignore: .env.local` |
| `AGENTS.md` | TRACKED(1) | — | 仓库执行规则 | Codex 会话读取 | 否 | 否 | KEEP（精简 V2/V3 专属内容） | §17 |
| `novelforge.project.yaml` | TRACKED(1) | — | V2/V3 项目边界配置 | 零 src/scripts/tests consumer（仅历史报告提及） | 否 | 否 | **KEEP**（frozen） | 表面零消费者，但 `docs/FROZEN_EVIDENCE_MANIFEST.json:historical_reference_policy.checked_documents` 列出它，且 `tests/test_v2_frozen_guard.py::test_documents_marking_old_release_refs_stay_honest` 断言该文件**存在** → 删除需改 frozen evidence（AGENTS.md §3.3） |
| `pytest.ini` | TRACKED(1) | — | 测试配置 | pytest | 否 | 否 | KEEP | 当前 testpaths/markers |
| `README.md` | TRACKED(1) | — | 产品入口文档 | 用户 | 否 | 否 | KEEP（去掉 V2/V3 入口教学） | §87 |
| `requirements.txt` / `requirements-dev.txt` | TRACKED(2) | — | Python 依赖 | 见 §9 | 否 | 否 | KEEP（按 §60 审计） | §9 |

## 3. Novel Tree Audit（任务书 §19–§39/§90）

Data class：`STORY_TRUTH` / `CURRENT_CONFIG` / `CURRENT_RUNTIME` / `DERIVED` / `LEGACY` / `USER_SOURCE` / `GENERATED` / `UNKNOWN`

| Directory | Tracked files | Current V4 consumer | Data class | Regenerable | Decision | Evidence |
| --------- | ------------: | ------------------- | ---------- | ----------- | -------- | -------- |
| `novel/authoring/` | 242 | 无（V4 只用 `authoring/story_engine/**`，该子树 ignored） | **FROZEN EVIDENCE**（V2 冻结资产） | 否（历史数据） | **KEEP**（frozen） | `docs/FROZEN_EVIDENCE_MANIFEST.json:frozen_evidence[0]` 记录 `paths=["novel/authoring"]`、`file_count=242`、sha256 摘要；`tests/test_v2_frozen_guard.py::test_frozen_evidence_digest_matches_tracked_files` 断言文件数与摘要。删除 = 需改 frozen evidence（AGENTS.md §3.3 需 ARCHITECTURE_EXCEPTION）→ 本阶段不动 |
| `novel/bible/` | 0（空目录） | 无 | LEGACY | — | LOCAL_DELETE ✓（已删） | 目录为空、未 tracked |
| `novel/config/` | 103 | 部分（`ai/providers.json`、`story_builder/step_catalogs.yaml`、`story_engine/*.json`） | CURRENT_CONFIG + LEGACY | 部分 | KEEP 3 个子树 / DELETE 其余 | §22、per-file 扫描 |
| `novel/gates/` | 0（空） | 无 | LEGACY | — | LOCAL_DELETE ✓（已删） | 空目录；V4 Quality owner 是 `src/novelforge/quality/**` |
| `novel/human/` | 0（空） | 无 | LEGACY | — | LOCAL_DELETE ✓（已删） | 空目录 |
| `novel/learning/` | 6 | 无（V4 Memory 是派生检索层，非旧 learning loop） | LEGACY | 否 | DELETE ✓（已删） | import-closure 零引用 |
| `novel/outline/` | 0（空） | 无（canonical creative artifact = StoryBlueprint） | LEGACY | — | LOCAL_DELETE ✓（已删） | 空目录；蓝图 owner 是 `src/novelforge/blueprint/**` |
| `novel/pipelines/` | 12 | 无（V4 orchestration = Application Services / Agent / Quality Repair） | LEGACY | 否 | DELETE ✓（已删） | import-closure 零引用 |
| `novel/relations/` | 0（空） | 无 | LEGACY | — | LOCAL_DELETE ✓（已删） | 空目录 |
| `novel/revision_plans/` | 0（空） | 无（Editor / Repair / Agent 有正式 owner） | LEGACY | — | LOCAL_DELETE ✓（已删） | 空目录 |
| `novel/runs/` | 0 | 无 | GENERATED（含生成正文草稿） | 是 | **REVIEW_REQUIRED** | 750 json / 221 md / 69 txt；抽样 `A_draft_raw.md`、`B_candidate.md`、`CH001_candidate.txt` = 生成正文候选，可能是唯一副本 → §64 不自动删 |
| `novel/runtime/` | 16 | 无（被 `novel/authoring/story_engine/**` 取代） | LEGACY | 否 | DELETE ✓（已删） | import-closure 零引用 |
| `novel/runtime_profiles/` | 5 | 无 | LEGACY | 否 | DELETE ✓（已删） | 无 profile loader 引用 |
| `novel/source_text/` | 0（空） | 无 | USER_SOURCE（潜在） | — | LOCAL_DELETE ✓（已删空目录） | 空目录且未 tracked |
| `novel/state/` | 278 | 无（V4 StoryState = `authoring/story_engine/state`） | LEGACY（V2/V3 state 快照） | 否 | DELETE ✓（已删） | paths.py 指向 `authoring/story_engine/state`；`tests/test_v2_frozen_guard.py` 通过（frozen 只锁 authoring） |
| `novel/state_updates/` | 0（空） | 无 | LEGACY | — | LOCAL_DELETE ✓（已删） | 空目录 |
| `novel/status/` | 1 | 无 | LEGACY | 否 | DELETE ✓（已删） | 无 src 引用 |
| `novel/timeline/` | 0（空） | 无 | LEGACY | — | LOCAL_DELETE ✓（已删） | 空目录 |
| `novel/workspace/` | 0 | 无 | GENERATED + 作者 scratch | 部分 | **REVIEW_REQUIRED** | `_edit*_out.txt` / `_fix_ch030.py` / `_cards*.txt` = V2 时代作者改写草稿，未 tracked → §64 不自动删 |

## 4. src audit（任务书 §50/§51）

```text
当前能力 owner（保留）：core / domain(story_engine 的 canon+profile+state 边界) / application /
                        persistence / ai / memory / blueprint / generation / quality / editor /
                        delivery / interfaces/mcp / plugins / agent / observability / api
```

### 4.1 真 ORPHAN（无任何 prod/test/script consumer）

```text
story_engine/m11_*.py                    27 个（M11 production runs / blocker / content design / closeout）
story_engine/m1{2..8}_*.py                7 个（M12–M18 milestone acceptance）
story_engine/chapter_ir/semantic_judge.py
story_builder/cross_genre_e2e.py
```

→ `DELETE`（`legacy/manifest.py` 已把它们登记为 `historical_milestone`，removal condition 为“不再需要时整体退役”；Git history 保留）。

### 4.2 仅被旧产品层/旧测试消费

```text
story_engine/planning/**（43）  story_engine/chapter_ir/**（14）  story_engine/spec/**（5）
story_engine/{historical_ir,historical_adoption,reconstruction,milestone_acceptance,phase_snapshot}.py
story_engine/canon/{context,mutation,outline_adapter,planner,prose}.py
story_engine/{creative,settings_gen,settings_check,outline_forge,outline_revision,route_lab,
               writer,storage,content,driver,characters,conditions,effects,entities,events,
               delayed,director,foreshadow,journey,linkage,narrative,progression,resolver,
               templates,world,*_view}.py
story_builder/{adventures,ai_recommendations,blueprints,catalog,design_tree,export_package,
                inspector,models,outlines,recommendations,sessions,ui_flow,v3_projection,
                writer_integration}.py
legacy/{manifest,adapters}.py（V4-01 的 frozen 模块清单机制；旧模块删除后清单失去对象）
```

→ `DELETE`，前提：**同批删除只服务旧产品行为的测试**（§53），并保持 frozen Repair Contract 证据链（§54）。

### 4.3 Frozen boundary（不删）

```text
story_engine/repair.py        frozen Repair Contract / REPAIR_GATE_V1 实现（AGENTS.md §16.1/§3.3）
tests/test_acceptance_repair_regressions.py  frozen repair 回归证据
tests/test_v2_frozen_guard.py / test_v3_frozen_guard.py  frozen 守卫
docs/FROZEN_EVIDENCE_MANIFEST.json           冻结证据 manifest
```

→ `KEEP`（若删除需 ARCHITECTURE_EXCEPTION_REQUIRED；本阶段不做）。

### 4.4 入口/组合根（无 importer 但不删）

```text
interfaces/mcp/__main__.py   `python -m novelforge.interfaces.mcp` 入口（README 记录）
plugins/host.py              composition root（V4_MODULE_BOUNDARIES §3.16 已登记）
```

→ `KEEP`。

## 5. scripts audit（任务书 §52）

| Script | Consumer | Decision |
| ------ | -------- | -------- |
| `scripts/validate_project.py` | 验收（§83） | KEEP |
| `scripts/start_novelforge_ui.py` | README 启动路径 | KEEP |
| `scripts/studio_ui_test_server.py` | V4 浏览器门禁 | KEEP |
| `scripts/bootstrap_dev.ps1` | README 安装 | KEEP |
| `scripts/creator_ui_test_server.py` | 只服务已删除 V2 creator 面板 | DELETE |
| `scripts/seed_long_line_state.py` | 只服务旧 long-line / planning 数据 | DELETE |

## 6. docs audit（任务书 §56–§59）

```text
KEEP（current SSOT）：docs/v4/V4_*CONTRACT.md、ADR、V4_ARCHITECTURE.md、V4_MODULE_BOUNDARIES.md、
                     V4_DATA_MODEL.md、V4_CODEBASE_INVENTORY.md、V4_12_*（验收/证据/债务/报告）、
                     docs/FROZEN_EVIDENCE_MANIFEST.json、README.md、AGENTS.md
KEEP（historical evidence，不重写）：V4_00…V4_12 阶段报告、V3/V2 冻结记录
DELETE（superseded 临时状态）：V4_10_STORY_STUDIO_STATUS.md、V4_12_STATUS.md
DELETE（已被正式 Contract 取代的设计稿）：*_SPEC（V4_MCP_SPEC / V4_EXPORT_SPEC / V4_PLUGIN_SPEC）
REVIEW：docs/ 中只描述 V2/V3 产品的手册（STORY_BUILDER_USER_GUIDE / LEGACY_COMPAT 等）
```

## 7. tests audit（任务书 §53）

```text
CURRENT V4 CONTRACT        tests/{acceptance,v4,ai,memory,blueprint? generation,quality,editor,
                           delivery,mcp,plugins,agent,studio}/**
FROZEN                     tests/test_v2_frozen_guard.py、test_v3_frozen_guard.py、
                           test_acceptance_repair_regressions.py
LEGACY PRODUCT TEST        tests/test_story_engine_*、test_story_builder_*、test_story_planning_*、
                           test_v3_*_projection、test_chapter_ir_*、test_canon_*（除 V4 使用项）、
                           browser_v3_*、browser_creator_*、browser_story_builder、browser_outline_*、
                           browser_advanced_tools/design_tree/genre_pack/novel_profile、browser_route_lab
```

`LEGACY PRODUCT TEST` → 随对应产品能力删除（§53），但 frozen 三项保留（§54）。

## 8. UI audit（任务书 §41–§44）

```text
MIGRATE  ui/src/v3/design-system/**  → ui/src/design-system/**（MOVE，不是 COPY），并更新 import
KEEP     ui/src/studio/**、ui/src/api/{studio,agent}.ts、ui/src/components/**、ui/src/hooks/**、
         ui/src/assets/defaults/**、ui/src/test/setup.ts
DELETE   ui/src/v3/** 其余（V3App / AppShell / CommandCenter / CreationFlow / ExportFlow /
         NovelLanding / WorkspaceView / api.ts / navModel.ts / viewmodel.ts / v3.css / export-flow.css）
DELETE   ui/src 顶层 V2 面板（StoryBuilderPage、AdventurePanel、CharacterPanel、CreativeBriefPanel、
         DesignTreePanel、DirectorPanel、GuidedFlowPanel、InspectorPanels、LinkagePanel、MemoryPanel、
         OutlineForgePanel、OutlineItemEditor、PlotPanel、ProgressionPanel、RouteLabPanel、
         SettingSeedPanel、VisualOutputPanels、VisualOverviewPanels、WorldPanel、api.ts、
         guidedFlow.ts、storyBuilderSelection.ts、style.css）
REWRITE  ui/src/App.tsx → Story Studio 唯一产品面；`?ui=v2` / `?ui=v3` / `#/v3…` / `#/story-builder…`
         → 重定向到 Story Studio（不加载旧 bundle）
```

## 9. 依赖审计基线（任务书 §60/§61）

```text
requirements.txt       fastapi / uvicorn / pydantic / httpx / PyYAML / networkx / mcp / sse-starlette / starlette
requirements-dev.txt   -r requirements.txt + pytest>=8.0
ui/package.json        react / react-dom / vite / vitest / testing-library / jsdom？（Story Studio 依赖）
```

清理后必须重跑 `npm ci` + `npm test` + `npm run build` + clean-install smoke。

## 10. 基线指标（清理前，任务书 §65）

```text
tracked files            1553
src/                     373 files（92719 LOC python）
tests/                   283 files
docs/                    106 files
ui/                      86 files
novel/                   663 files（authoring 242 / state 278 / config 103 / runtime 16 / pipelines 12 /
                                    learning 6 / runtime_profiles 5 / status 1）
scripts/                 6 files
skills/                  17 files
reference_books/         11 files
```
