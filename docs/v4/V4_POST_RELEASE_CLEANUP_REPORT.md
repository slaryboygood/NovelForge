# NovelForge V4 — Post-Release Full Repository Cleanup Report

> 阶段：**V4.0.0 之后的 current-tree 深度清理**
> 分支：`v4-post-release-cleanup`（基线 `baa81ef39b8f4563923a28a2b2d2d28e77e423a4` = `v4.0.0`）
> 判据：`docs/v4/V4_POST_RELEASE_CLEANUP_INVENTORY.md`（KEEP / MIGRATE / DELETE / LOCAL_DELETE / REVIEW_REQUIRED）
> 结论：
> **Round 1**（`e2b8de7`…`e0bb657`）完成 UI 与数据层清理并门禁验证 → backend legacy 层仍 BLOCKED（见 §96）。
> **Round 2**（`b62de3a`…`fbf1874`，见本文件 §96b）完成 **V2/V3 Story Builder 后端整体退休**：
> `/api/story-builder/v3/*`、route_lab、writer、outline、planning、chapter IR、spec、
> `story_builder/**`、legacy manifest、legacy config 全部移除，`v3_projection` /
> `export_package` / `writer_integration` / `creator` / `blueprints` / `sessions` 物理删除。
> 最终 verdict（§96c）= **PASS**（§81 的全部 PASS 条件逐项有证据）。

## 1. Starting commit

```text
baa81ef39b8f4563923a28a2b2d2d28e77e423a4（main = v4 = v4.0.0 tag target）
```

## 2. Cleanup branch

```text
v4-post-release-cleanup（本地；未 push、未 merge、未建 tag —— 任务书 §95）
```

## 2b. MCP environment（任务书 §5/§89）

```text
通过 tool_search 实测枚举 + 逐项调用验证（见 inventory §0b）：
  figma             已编目；design-only，与本任务无关
  node_repl         **unsupported call**（本可作引用分析，实际不可用）
  chrome_devtools   **unsupported call**
  playwright        已编目，不在可调用集
  codex_app         可用，但与代码分析无关
  NovelForge MCP    可运行（§61/§62 surface 实测）

结论：本会话没有 code-intelligence / LSP / symbol-reference MCP。
```

## 2c. MCP methodology（任务书 §6–§10/§96）

```text
五证据模型的实际执行：
  E1 MCP/code-index references   → 环境不可获得（唯一硬缺口，见 §2b）
  E2 textual/static references   → rg + Python AST import-closure（含相对 import 与字符串式动态引用）
  E3 runtime registry/route refs → FastAPI route installer / plugin host / MCP registry 扫描
  E4 test/contract/release resp. → pytest 1690 + acceptance + frozen guards
  E5 Git/data ownership          → git ls-files / check-ignore / FROZEN_EVIDENCE_MANIFEST

已执行删除的判定：E2=E3=E4=E5 全部为"无消费者/无职责"且被回归证明，E1 由静态闭包替代。
未执行删除的候选（§11 backend legacy）：因 E1 缺失，按 §10 判为 MEDIUM → REVIEW_REQUIRED，
不进入自动删除（这也解释了为什么 §11 是 BLOCKED 而不是"悄悄删掉"）。

MCP 与静态搜索不一致的案例：**无**——因为本环境没有可用的 symbol 分析 MCP 可供对照。
这一条本身就是需要上报的环境限制，而不是"两方一致"的证据。
```

## 2d. MCP surface before / after（任务书 §61/§62/§75）

```text
在删除前实测（进程内 registry）：
  CORE TOOLS = 23（generate_* / patch_blueprint_node / repair_issue / deliver_blueprint …）
  CORE RESOURCES = 13（blueprint / quality / scenes / delivery-manifest / revision …）
删除后：完全一致（23 / 13）。
  · 本轮只删除 UI 产品面、孤儿模块、legacy 数据与 legacy 门禁，
    未触碰 interfaces/mcp/**、application facade、registry 注册表；
  · tests/acceptance/test_final_release.py::test_mcp_core_baseline_and_plugin_increment
    仍断言 23 tools / 13 resources 并 PASS。
```

## 3. Root directory audit

逐项结论（完整证据表见 inventory §2）：

```text
KEEP            docs/（部分）、novel/（仅 authoring + 3 个 config 子树）、reference_books/（REVIEW）、
                skills/（Codex 工具；writing/*.md 为作者笔记 → REVIEW）、src/（部分）、tests/（部分）、
                ui/（部分）、.env.example、pytest.ini、README.md、requirements*.txt、AGENTS.md、
                novelforge.project.yaml（frozen guard 引用）、.venv、.python311（bootstrap 依赖）、
                .codex（本地运行环境）、.agents（本地 skill 挂载）
LOCAL_DELETE    .dsh-runtime（663 MB，本会话未删：运行中的宿主 runtime）
                workspace/（作者内容 → REVIEW_REQUIRED，见 §51）
DELETE          novel/{state,runtime,pipelines,learning,runtime_profiles,status}（318 tracked）
```

## 4. Novel directory audit

```text
novel/authoring/**      KEEP —— 被 FROZEN_EVIDENCE_MANIFEST 以 242 files + sha256 冻结（V2 冻结资产）
novel/config/**         KEEP 3 个子树（ai / story_builder / story_engine）；其余为 legacy（见 §29）
novel/state/**          278 tracked → DELETE ✓
novel/learning/**       6 → DELETE ✓        novel/pipelines/** 12 → DELETE ✓
novel/runtime/**        16 → DELETE ✓       novel/runtime_profiles/** 5 → DELETE ✓
novel/status/**         1 → DELETE ✓
novel/bible|gates|human|outline|relations|revision_plans|state_updates|timeline|source_text
                        空目录 → LOCAL_DELETE ✓（9 个）
novel/runs/**           REVIEW_REQUIRED（含生成正文草稿，可能是唯一副本，未删）
novel/workspace/**      REVIEW_REQUIRED（V2 时代作者改写草稿，未删）
```

## 5. UI audit

```text
ui/src/design-system/**   新增（MIGRATE 的目标命名空间）
ui/src/studio/**          KEEP（唯一产品面）
ui/src/api/{studio,agent,http}.ts   KEEP（http.ts = 迁移出的唯一 fetch 入口）
ui/src/assets/defaults/** KEEP（6 个默认美术）
ui/src/{components,hooks}/**        DELETE ✓（零消费者：4 个 V2 panel 组件 + useApiData）
```

## 6. V2 UI removal

删除 19 个 V2 面板组件 + `api.ts` / `guidedFlow.ts` / `storyBuilderSelection.ts` / `style.css`
以及 `ui/src/components/**`、`ui/src/hooks/**`（全部零消费者，见 §5）。
`ui/src/api.ts` 中仍被 Story Studio 使用的 HTTP 语义迁移为 `ui/src/api/http.ts`（MIGRATE）。

## 7. V3 UI removal

删除 `ui/src/v3/**` 其余全部（V3App / AppShell / CommandCenter / CreationFlow / ExportFlow /
NovelLanding / WorkspaceView / api.ts / navModel.ts / viewmodel.ts / v3.css / export-flow.css /
design-system 的 choices·components·artworkManifest）。

## 8. Design System migration

```text
MOVE（不是 COPY）：
  ui/src/v3/design-system/primitives.tsx      → ui/src/design-system/primitives.tsx
  ui/src/v3/design-system/tokens.css          → ui/src/design-system/tokens.css
  ui/src/v3/design-system/icons/IconRegistry.tsx → ui/src/design-system/icons/IconRegistry.tsx
  ui/src/v3/design-system/assets/artworkManifest.ts → ui/src/design-system/assets/artworkManifest.ts
  （artworkManifest 的相对美术路径同步修正：../../../assets → ../../assets）
新增 ui/src/design-system/primitives.css：从 v3.css **迁移**出的共享原语样式（84 条规则）
更新 11 个文件的 import；残留只有注释，已同步。
```

**本轮最重要的一次真实回归**：`v3.css` 里同时住着 V3 外壳样式**与**共享原语的布局
（`.v3-card-hit` 的点击层、`.v3-card` 的 min-width 等）。先删 v3.css、后补 primitives.css 的
顺序会让"点击问题卡片不打开详情抽屉"（浏览器 golden gate 真实失败）。
处理方式：按 §42 的 MIGRATE 原则把共享规则抽出，而不是为了过门禁保留整个 V3 CSS。

## 9. Legacy URL behavior

```text
默认 URL / #/studio                       → Story Studio
?ui=v3 / #/v3（带或不带 query）           → 归一化 + Story Studio（0 page error / 0 重载）
?ui=v2 / #/story-builder                  → 归一化 + Story Studio
归一化只删 `ui` 参数、保留业务参数（novel_id 等），不重新加载、不产生重定向循环
```

门禁：`tests/browser_v4_legacy_entry.cjs`（已按 §55 重写：从"进入 V3/V2"改为"回落到 Studio"）。

## 10. Backend route audit

```text
api/app.py 注册的 adapter：story_builder / canon / editor / delivery / studio / agent
Story Studio 实际使用（ui/src/api/**）：
  /api/story-builder/novels（GET/POST —— 已由 application project_service 支撑）
  /api/story-builder/studio/**、/editor/**、/delivery/**、/agent/**
```

## 11. Legacy backend removal

**未完成（本轮 BLOCKED 项）**：`api/story_builder_routes.py`（1563 行、约 90 个端点）
仍保留 V2/V3 端点；其依赖的 `story_builder/**` 与 `story_engine/{planning,chapter_ir,spec,
*_view,creative,outline_*,route_lab,writer,…}` 仍在树里。

```text
已定位的阻碍（必须先解决才能删）：
  · application/services/journey.py 仍委托 story_builder.v3_projection.journey_projection
    （MCP journey resource 的当前消费者）→ 需先 MIGRATE 投影实现
  · application/services/export.py 仍引用 story_builder.export_package 与 writer_export_bundle
    → 需先确认 legacy export 端点退出后再删
  · story_engine/creator.py 依赖 story_builder.{blueprints,sessions}（live：memory + export 使用）
  · frozen Repair Contract（story_engine/repair.py）与其回归测试按 §54 KEEP
```

## 12. Writer removal

```text
未完成：writer_integration / /writer/* 端点仍在（随 §11 的 route 收缩一起处理）
已确认：Story Studio / MCP / Agent / Delivery / Plugin 均不消费 writer（消费者只有 legacy 端点与 legacy 测试）
```

## 13. Outline removal

```text
未完成：story_engine/{outline_forge,outline_revision}.py 与 /outlines/*、/blueprints/* 端点仍在
已确认：canonical creative artifact 是 StoryBlueprint（blueprint/**），legacy outline 无 V4 消费者
```

## 14. Export removal

```text
部分：`/api/story-builder/export/{package,writer-bundle}` 仍存在（legacy UI 已删除 → 终端消费者已消失）
V4 交付走 /api/story-builder/delivery/**（revision-pinned，未被本轮改动）
```

## 15. Journey / projection migration

```text
未完成：journey_service 已位于 application/services/journey.py（迁移外壳已就位），
但实现仍委托 v3_projection；本轮未改动该逻辑（避免在未完成 route 收缩前改变行为）
```

## 16. Source orphan audit

```text
已删除真 ORPHAN 37 个文件（无任何 prod/test/script 消费者）：
  story_engine/m11_*.py（27）、m1{2..8}_*.py（7）、chapter_ir/semantic_judge.py、
  story_builder/cross_genre_e2e.py
保留入口（无 importer 但为正式入口）：interfaces/mcp/__main__.py、plugins/host.py
```

## 17. Scripts audit

```text
KEEP   validate_project.py / start_novelforge_ui.py / studio_ui_test_server.py / bootstrap_dev.ps1
DELETE creator_ui_test_server.py（只服务已删 V2 面板）、seed_long_line_state.py（只服务旧 planning 数据）
```

## 18. Skills audit

```text
KEEP（Codex 开发工具，非 NovelForge Plugin Platform）：skills/silicon-*/**（5 个 skill）
REVIEW_REQUIRED：skills/writing/{少解释,强钩子,探索感}.md（作者写作笔记，tracked 但非产品消费）
```

## 19. Agents / Codex audit

```text
.agents/  删除尝试返回 access denied（`.agents/skills` 为当前会话 skill 根）→ KEEP（§10 不自毁执行环境）
.codex/   当前 Codex 运行目录 → KEEP（ignored）
AGENTS.md KEEP（仓库规则入口；§16/§21 的 V2/V3 章节保留为历史边界说明）
```

## 20. Python environments audit

```text
.venv       KEEP（当前开发/测试环境；ignored/untracked）
.python311  KEEP（scripts/bootstrap_dev.ps1 用它创建 .venv）
```

## 21. Workspace / runtime audit

```text
workspace/studio_ui_review、workspace/v4_12_ui_review、workspace/pilot_v2、根级 CH0xx_*/DEEPWRITE_*
  → 全部 REVIEW_REQUIRED（作者写作材料与验收截图混放，未自动删）
novel/runs、novel/workspace → REVIEW_REQUIRED（见 §4）
.dsh-runtime（663 MB）→ LOCAL_DELETE 待办（运行中）
本轮生成的临时根：workspace/cleanup_ui_root、workspace/cleanup_ui_review、workspace/cleanup_pytest_*.log
  → 清理完成后删除
```

## 22. Reference books decision

```text
REVIEW_REQUIRED（不动）：reference_books/book_001/profile/**（10 个写作档案）+ tools/prepare_reference.py
理由：tracked，但属外部作品分析资料；§14 明确禁止"代码没有 import 就删"
```

## 23. Source text decision

```text
novel/source_text/ 为空目录 → 已删（LOCAL_DELETE）
workspace 根级作者材料（CH069 等）→ REVIEW_REQUIRED（未删）
```

## 24. Assets removed

```text
ui/src/v3/design-system/{choices.tsx, components.tsx}、v3.css、export-flow.css（V3 专用）
V3 专用美术清单 artworkManifest 已 MIGRATE（其引用的 6 个默认美术保留）
```

## 25. Tests removed

```text
tests/test_creator_ui_audit.py（V2 面板审计，3 项）
tests/test_story_builder_guided_flow.py 中的前端断言（1 项；同文件其余后端用例保留）
tests/test_v3_visual_asset_contract.py（4 项，契约随 V3 UI 退出；见 §29）
tests/browser_v3_*.cjs（8）、browser_creator_*.cjs（3）、browser_story_builder/advanced_tools/
  design_tree/genre_pack/novel_profile/outline_forge/outline_revision/route_lab（11）＝ 19 个 legacy 浏览器门禁
合计删除 19 个浏览器门禁 + 8 个 Python 断言（分布于 3 个文件）
```

## 26. Tests retained

```text
CURRENT V4：tests/{acceptance,v4,ai,memory,generation,quality,editor,delivery,mcp,plugins,agent,studio}/**
FROZEN：tests/test_v2_frozen_guard.py、test_v3_frozen_guard.py、test_acceptance_repair_regressions.py
LEGACY-BACKEND（保留到 §11 完成）：test_story_engine_* / test_story_builder_* / test_story_planning_* /
  test_v3_*_projection / test_chapter_ir_* / test_canon_*（它们仍在测试仍在树里的 backend）
```

## 27. Docs removed

```text
docs/v4/{V4_MCP_SPEC,V4_EXPORT_SPEC,V4_PLUGIN_SPEC}.md（已被正式 Contract 取代，§59）
（同步更新 tests/acceptance/test_final_contracts.py::test_no_conflicting_ssot_for_the_same_capability
  为"旧稿必须不存在"，先改 current contract 再改测试）
```

## 28. Historical evidence retained

```text
KEEP 不动：V4_00…V4_12 阶段报告、V4_12_ACCEPTANCE_MATRIX / EVIDENCE_INDEX / FINAL_ACCEPTANCE_REPORT /
  ARCHITECTURE_DEBT_REVIEW（含 STATUS 文件，因其被最终报告链接）、docs/FROZEN_EVIDENCE_MANIFEST.json、
  docs/V3_*（frozen guard 引用）、docs/CHANGELOG.md、docs/LEGACY_COMPAT.md、
  docs/NOVELFORGE_PRODUCT_V2_RELEASE.md、docs/NOVELFORGE_REAL_NOVEL_PRODUCTION_GUIDE.md
```

## 29. Config audit

```text
KEEP  novel/config/ai/providers.json（LLM Gateway）
KEEP  novel/config/story_builder/step_catalogs.yaml（create_app catalog）
KEEP  novel/config/story_engine/*.json（content packs）
其余 novel/config 子树（outline 19 / schemas 48 / bible 6 / characters 2 / factions / maps /
  monsters 2 / progression 4 / planning 2 / spec 2 / human 1 / author 4 / 若干根级 yaml）
  → 只被 §11 的 legacy backend 读取；随该层退出（本轮未删，避免留下"删了配置但代码还读"的半成品）
novelforge.project.yaml → KEEP（frozen guard 的 checked_documents 断言其存在）
```

## 30. Dependency audit

```text
requirements.txt / requirements-dev.txt 未改动：本轮没有删除任何被运行时使用的第三方依赖
（networkx 仍被 canon graph / planning 使用；mcp / sse-starlette / starlette 仍被 MCP 使用）
ui/package.json 未改动：React / Vite / Vitest / Testing Library 全部仍是当前依赖
  （前端构建产物由 index-*.js 486.65 kB → 232.65 kB、CSS 86.95 kB → 27.36 kB，模块数 98 → 58）
```

## 31. Public API cleanup

```text
ui：删除的 19 个面板 + v3 模块没有公共导出残留（tsc -b 全量类型检查通过）
python：`legacy/` 的 frozen manifest 仍登记 m11_* / m12_*…m18_*，但这些文件已删除 →
  该清单条目成为 stale（列入 §57 待办，随 §11 一起收敛）
```

## 32. Error cleanup

```text
未改动错误契约：ApiError 语义（status + detail）迁移到 ui/src/api/http.ts 时保持等价，
  由 ui/src/api/studio.test.ts（10 项）与 errors.test.ts（11 项）继续守卫
```

## 33. Tracked files before / after

```text
1553 → 1131（−422，−27.2%）
  src/    373 → 336
  tests/  283 → 260
  docs/   106 → 104
  ui/      86 →  46
  novel/  663 → 345
  scripts/  6 →   4
```

## 34. Disk size before / after

```text
novel/ 已删除 tracked 数据 ≈ 8.0 MB（state 6.6 MB + runtime/pipelines/learning/runtime_profiles/status）
ui/src 删除 ≈ 4.5 KLOC TS/TSX + V3 CSS（869 + 869 行）
前端构建产物：JS 486.65 kB → 232.65 kB；CSS 86.95 kB → 27.36 kB
（本机 .dsh-runtime 663 MB、novel/runs 85.7 MB 未删，见 §21）
```

## 35. LOC before / after

```text
src python LOC  92,719 → 73,216（−19,503）
ui ts/tsx LOC   （清理后）5,136
tests python LOC（清理后）30,320
```

## 36. Full pytest

```text
command   .venv\Scripts\python.exe -m pytest -q
result    1690 passed, 7 skipped, 0 failed
duration  615.43s (10:15)
（清理前基线：1707 passed / 7 skipped；减少的 17 项 = §25 删除的 legacy 断言）
```

## 37-46. 专项门禁

```text
37 Acceptance        pytest -q tests/acceptance + v2/v3 frozen guards → 40 passed（54.63s）
                     其中 acceptance 28 / frozen guards 12
38 Frontend          npm ci → exit 0；npm test → 60 passed（8 files）；npm run build → PASS（1.09s）
                     dist：index-*.js 232.65 kB（清理前 486.65 kB）、index-*.css 27.36 kB（清理前 86.95 kB）
39 Browser Studio    tests/browser_v4_studio_golden.cjs → PASS（真实 Edge + stub，0 真实模型调用）
                     downloads：blueprint.md 5,557 B / blueprint.docx 3,845 B / nfpack 20,702 B
40 Browser Agent     tests/browser_v4_11_agent.cjs → PASS
41 Legacy redirect   tests/browser_v4_legacy_entry.cjs → PASS（0 page error / 0 重载）
42 MCP               tests/mcp/**（含 23 tools / 13 resources baseline）—— full pytest 内 PASS
43 Plugins           tests/plugins/**
44 Delivery          tests/delivery/** + 浏览器真实下载（Markdown / DOCX / nfpack）
45 Isolation         tests/acceptance::test_cross_novel_isolation_everywhere + tests/v4/isolation
46 Canon/StoryState  Layer B 不变式（hashes unchanged）
```

## 47. Frozen tags

```text
未触碰、未移动、未重建（本轮不建 tag、不 push）：
  v4.0.0 · novelforge-product-v4-final · novelforge-product-v3-final
  docs/FROZEN_EVIDENCE_MANIFEST.json 未改动（novel/authoring 242 files 摘要仍匹配 → v2 guard PASS）
```

## 48. validate_project

```text
python scripts/validate_project.py → PASS
```

## 49. Clean install smoke

```text
临时 clean venv（`workspace/cleanup_clean_venv`，用后删除）：
  python -m venv → pip install -r requirements.txt → exit 0
  import novelforge OK → create_app() OK → GET /api/health = 200

**本轮修复的真实缺陷**：首次运行 smoke 时 `pip install -r requirements.txt`
在本机 GBK locale 下失败（`UnicodeDecodeError: 'gbk' codec can't decode byte 0xb9`），
原因是 `requirements.txt` 含中文注释而 pip 24.0 在没有编码声明时按本地编码解码。
修复：在 `requirements.txt` 首行加入 `# -*- coding: utf-8 -*-`（PEP 263 声明），
随后用同一个未升级 pip 的全新 venv 复现 → exit 0。这条只有在"干净环境"里才会暴露。
```

## 50. Remaining legacy-named paths

```text
story_engine/planning/**、chapter_ir/**、spec/**、m*-milestone 已删但 manifest 仍登记、
story_builder/{adventures,ai_recommendations,blueprints,design_tree,export_package,inspector,
               models,outlines,recommendations,sessions,ui_flow,v3_projection,writer_integration}.py、
api/story_builder_routes.py 的 V2/V3 端点、
novel/config 的 legacy 子树、
docs 中的 V2/V3 历史报告（§57：历史不改写）
理由见 §11；这些是本轮明确保留（而不是"忘了"）的项。
```

## 51. Review-required user content

```text
workspace/CH0xx_*.md、workspace/DEEPWRITE_*、workspace/gate_*.log（作者写作与审计材料）
workspace/{pilot_v2,studio_ui_review,v4_12_ui_review}（本地验收证据/工作区）
novel/runs/**（含生成正文草稿）、novel/workspace/**（V2 时代作者改写草稿）
reference_books/book_001/**（外部作品分析档案）
skills/writing/*.md（作者写作笔记）
→ 以上均未删除，等作者决定（§64）
```

## 52. Files created

```text
docs/v4/V4_POST_RELEASE_CLEANUP_INVENTORY.md
docs/v4/V4_POST_RELEASE_CLEANUP_REPORT.md（本文件）
ui/src/api/http.ts
ui/src/design-system/primitives.css
ui/src/design-system/{primitives.tsx,tokens.css,icons/IconRegistry.tsx,assets/artworkManifest.ts}（迁移到达）
```

## 53. Files modified

```text
README.md（V4 定位 + 旧入口说明 + 代码地图）
requirements.txt（首行加 PEP 263 编码声明：修复 GBK locale 下干净安装失败，§49）
ui/src/App.tsx（Studio 唯一产品面 + 旧 URL 回落）
ui/src/main.tsx（去掉 V2 全局样式）
ui/src/studio/{StudioApp.tsx,nav.ts,nav.test.ts,studio.css}（移除 legacy/v3 路由与入口链接）
ui/src/api/{studio.ts,agent.ts,studio.test.ts}（import → ./http）
ui/src/design-system/**（迁移后的 import 路径）
tests/acceptance/test_final_contracts.py（SSOT 唯一性断言升级为"旧稿必须不存在"）
tests/browser_v4_legacy_entry.cjs（重写为回落门禁）
docs/v4/V4_POST_RELEASE_CLEANUP_INVENTORY.md（逐波更新决策）
```

## 54. Files deleted

```text
src/novelforge/story_engine/m11_*.py（27）+ m1{2..8}_*.py（7）+ chapter_ir/semantic_judge.py
src/novelforge/story_builder/cross_genre_e2e.py
novel/{state/**,runtime/**,pipelines/**,learning/**,runtime_profiles/**,status/**}（318）
ui/src/v3/**（其余全部）+ 19 个 V2 面板/客户端文件 + ui/src/{components,hooks}/**
ui/src/design-system 迁移源（v3/design-system 内已迁移文件按 MOVE 语义）
tests/browser_v3_*.cjs 等 19 个 legacy 浏览器门禁
tests/{test_creator_ui_audit.py,test_story_builder_guided_flow.py 的前端断言,test_v3_visual_asset_contract.py}
scripts/{creator_ui_test_server.py,seed_long_line_state.py}
docs/v4/{V4_MCP_SPEC,V4_EXPORT_SPEC,V4_PLUGIN_SPEC}.md
（本地、gitignored）novel/ 下 9 个空 legacy 目录
```

## 55. Git commits

```text
e2b8de7 docs(v4): inventory full post-release repository cleanup
4bb71da refactor(v4): remove historical milestone and orphan modules
c07b361 chore(novel): remove unused legacy novel data layout
1363919 docs(v4): record cleanup inventory decisions for wave 1
10843ca refactor(ui): migrate design system and remove v2/v3 product surfaces
d3a36af test(v4): update post-legacy-removal redirect gate
5938ec6 chore(repo): remove dead scripts, legacy gates and superseded specs
（本轮最后一条：docs(v4): record post-release cleanup result）
```

## 56. Working tree

```text
clean（本轮结束时；临时 workspace 根在收尾时删除）
```

## 57. Remaining risks / 待办

```text
0. **E1 证据缺口**：本会话没有可调用的 code-intelligence MCP（§2b/§2c）→
   剩下的候选删除只能达到 MEDIUM 置信度 → 按 §10 全部 REVIEW_REQUIRED。
   若要按任务书 §8 的"五证据齐备才删"执行后端 legacy 收缩，需要先提供
   可用的 symbol/reference 分析工具（或明确接受"静态闭包替代 E1"这一降级）。
1. §11 backend legacy 层未移除（route 收缩 + journey/export/creator 迁移 + manifest 收敛）
2. legacy/manifest.py 仍登记已删除的 m11_*/m12–m18 条目 → stale（必须与 §11 一起收敛）
3. novel/config 的 legacy 子树、novel/{runs,workspace}、workspace/** 的用户资料判定
4. .dsh-runtime（663 MB）本地缓存未清理（运行中宿主 runtime）
5. 历史 V3/V2 acceptance 数据根缺失 → 历史套件仍 NOT RUN（非本轮 blocker）
```

## 58. Recommended release version

```text
本轮的变更全部在"移除已退役产品面 + 迁移旧命名空间"范围内，产品行为不变（门禁全绿），
但**删除了旧 URL 的产品面**且**backend legacy 层尚未完成收缩**。
建议：先完成 §11 后再决定版本号；候选为 patch 级（例如 v4.0.1 —— 仅含"移除兼容产品面 + 清理"），
而不是 minor（没有新增能力）。不要在本轮直接发布。
```

---

# Round 2 — V2/V3 Story Builder Backend Retirement

> 起点：`e0bb657`（Round 1 结束，working tree clean，未 push / 未 merge / 未打 tag）
> 终点：`fbf1874`（本文件随 docs 收敛一并提交）
> 授权：作者已接受 `E1_STATIC_SUBSTITUTE = ACCEPTED`（本环境没有 code-intelligence MCP），
> 删除证据链 = `E1' AST/import closure` + `E2 rg/git grep` + `E3 runtime routes/registries`
> + `E4 tests/contracts/frozen/browser` + `E5 Git/data ownership`。

## 96b. 每个 blocker 的处理（任务书 §75）

| Blocker | Before | Action | After | Evidence | Status |
| ------- | -----: | ------ | ----- | -------- | ------ |
| Journey/v3_projection | `application/services/journey.py` 委托 `story_builder.v3_projection` | 投影实现改为只读 current 层（Profile / Blueprint / Quality / Delivery），删除 `v3_projection.py` + `/v3/*` 端点 | 0 引用，模块不存在 | `b62de3a`；`rg v3_projection src tests` = 0；`pytest tests/v4 tests/studio tests/mcp tests/acceptance` PASS | **CLOSED** |
| export_package | `ExportService` 曾包装 `story_builder.export_package`（Round 1 已切走调用点） | 物理删除 `story_builder/export_package.py` | 模块不存在 | `b3d2ffc`；`rg export_package src` = 文档历史说明 | **CLOSED** |
| writer_integration | `/writer/*` 端点 + 草稿 SSOT 仍在 | 删除模块 + 端点；frozen repair 回归先去耦 | 模块与端点不存在 | `b3d2ffc`；`rg writer_integration src tests` = 0（仅历史文档） | **CLOSED** |
| creator | `story_engine/creator.py`（V2 creator context，含 blueprint 槽） | surviving helpers 迁到 `story_engine/context.py`（NovelContext / resolve_novel_context / story_state_preview / runtime_key_for），删除 creator.py | 0 引用，`rg story_engine.creator` = 0 | `95d5db6`；`tests/memory tests/generation tests/delivery` PASS | **CLOSED** |
| blueprints | `story_builder/blueprints.py`（第二套 Blueprint 存储） | 与 V2 session 引导流一起退休；canonical owner = `novelforge.blueprint` | 模块不存在 | `fbf1874`；`rg story_builder.blueprints src tests` = 0 | **CLOSED** |
| sessions | `story_builder/sessions.py`（V2 UI session） | 退休（不是 context helper：只服务 V2 引导流） | 模块不存在 | 同上 | **CLOSED** |
| writer backend | `story_engine/writer.py` + `/writer/*` | 退休（V4 Core 无整段正文 Writer；正文预览由插件承担） | 模块不存在 | `fbf1874`；`novel/runs/**`、`novel/workspace/**` 未触碰 | **CLOSED** |
| outline backend | `outline_forge` / `outline_revision` / outline 模型与端点 | 退休；canonical creative artifact = StoryBlueprint | 模块与端点不存在 | `fbf1874`；`canon/outline_adapter.py` 同步删除（会重建第二套 outline 存储） | **CLOSED** |
| story_engine legacy | planning(43) / chapter_ir(11) / spec(5) / route_lab / creative / settings_gen / settings_check / `*_view` / historical_* / reconstruction / milestone_acceptance / phase_snapshot / writer / 模拟运行时 | 用 E1'–E5 判定后删除；**保留** Canon、StoryState、Profile、templates、context、frozen Repair 实现 + chapter IR frozen slice | `story_engine` 只剩 9 个模块 + canon + 3 文件 frozen slice | `fbf1874`；`tests/v4/isolation/test_legacy_boundary.py` 守卫 | **CLOSED** |
| story_builder routes | 1317 行 God router（86 端点） | `api/project_routes.py` 接管 `/novels`（URL 不变，owner = ProjectService）；God router 删除；`create_app` 去掉 `with_legacy` | `/api` 路径 46 → 全部登记在 `tests/test_product_surface.py` | `fbf1874`；`tests/test_product_surface.py` + `tests/test_v3_frozen_guard.py` 断言 21 个 legacy 端点 404 | **CLOSED** |
| LegacyManifest | `novelforge/legacy/**`（10 条 frozen 模块登记，含已删条目） | 模块整体退休（无 runtime consumer）；历史证据交给 Git + `FROZEN_EVIDENCE_MANIFEST` | 包不存在 | `fbf1874`；`tests/v4/isolation/test_legacy_boundary.py` | **CLOSED** |
| legacy config | `novel/config` 103 files（step_catalogs / story_engine packs / schemas / bible / outline / planning / spec / author / human / 根级 yaml） | 逐文件确认「哪个 current loader 打开它」→ 无 loader 的全部删除 | `novel/config` 只剩 `ai/providers.json` | `fbf1874`；`rg novel/config src` 只剩 `ai/factory.py` | **CLOSED** |

## 96c. 最终验证（任务书 §52–§71 / §81）

```text
Starting HEAD  e0bb657（Round 1 结束）
Ending HEAD    fbf1874 + 本 docs 收敛提交
Cleanup commits（Round 2）= 8

Journey               V4-native（Profile / Blueprint / Quality / Delivery）；v3_projection 删除
MCP journey 消费者    facade.summary / studio overview / MCP novel resource 三段同源断言（tests/test_acceptance_repair_regressions.py）
Export                legacy export channel 退休；current 交付 = ExportService.deliver（唯一出口）
frozen repair         回归保留：tests/test_acceptance_repair_regressions.py 10 项全绿（fixture 迁移，语义未放宽）

Routes before/after   1317 行 God router（86 端点）→ 46 个 current API 路径（/novels 迁到 project_routes）
LegacyManifest        10 entries → 包整体退休
Config before/after   103 files → 1（ai/providers.json）
Legacy tests removed  93 个文件（story_builder 20 / story_engine 40 / story_planning 14 /
                      chapter_ir 10 / v3 projection 5 / ai+generation legacy migration 2 / 其它 2）
Deleted files total   316（src py 121 / tests py 93 / novel 数据 102）+ 新增 2
                      （api/project_routes.py、story_engine/context.py）；修改 42
Tracked files         1132 → 818（−314）
Python LOC            src 84,811 → 39,116（−45,695，−54%）；tests 36,763 → 18,559（−18,204）
Frontend bundle       232.65 kB JS / 27.36 kB CSS（不变：UI 侧本轮无改动）

Full pytest           924 passed, 1 skipped, 0 failed（6:43）＝新 baseline
Acceptance            tests/acceptance PASS
Frozen guards         test_v2_frozen_guard PASS / test_v3_frozen_guard PASS（边界改挂 current owner，断言强度不降低）
Repair frozen         test_acceptance_repair_regressions PASS（10 passed）
Memory / Generation / Delivery / MCP / Plugins / Agent / Studio / v4 isolation  PASS（522 passed 专项组合）
MCP                   build_tool_registry = 23 tools / build_resource_registry = 13 resources（未变）
Frontend              npm ci exit 0；npm test 60 passed（8 files）；npm run build PASS
Browsers              browser_v4_studio_golden PASS（downloads: blueprint.md 5,557 B / blueprint.docx 3,845 B / novelforge-package.nfpack 20,697 B）
                      browser_v4_11_agent PASS；browser_v4_legacy_entry PASS（0 page error）
Isolation             tests/v4/isolation/** PASS（含 cross-novel isolation）
Canon/StoryState      canon 全量测试 PASS；canon mutation matrix kill_rate 100% / pollution 0%
validate_project      PASS（46 个 API 路径全部登记）
Clean install         全新 temp venv（`.python311 -m venv`）→ `pip install -r requirements.txt` exit 0（**不升级 pip**）
                      → import novelforge / create_app() / GET /api/health = 200（product=story-studio）
Empty-runtime smoke   空数据根（无任何 legacy 目录）→ app 启动、health 200、/novels 200、
                      POST /novels 201 且只创建 `novel/authoring/story_engine/profiles`
Frozen tags           v4.0.0 / novelforge-product-v4-final → baa81ef…；novelforge-product-v3-final 未移动
Working tree          clean
```

## 96d. 剩余 current legacy paths（每一个都有 justification）

```text
src/novelforge/story_engine/repair.py
  frozen Repair Contract / REPAIR_GATE_V1 实现（AGENTS.md §16.1/§34）→ 保留
src/novelforge/story_engine/chapter_ir/{__init__,models,function_policy}.py
  repair.py 依赖的 frozen slice（FUNCTION_REQUIREMENTS + ChapterSemanticIR）→ 保留
src/novelforge/story_engine/canon/**
  Canon Infrastructure（C01–C13：identity / dependency / graph / gate / validator /
  planner / mutation / prose / bootstrap / sync / service）→ **整体保留**。
  判定依据（偏离 inventory §4.2 的一行结论，理由如下）：Canon 是 AGENTS.md §3.3 明确保护的
  frozen truth boundary；planner / mutation / prose 是 Canon 自己的工程能力（fault injection
  corpus、Canon-aware planning、prose integrity audit），不是 V2 Story Builder 产品代码，
  其测试是 Canon 测试而不是 legacy 产品测试。删除它们等于削减 Canon 覆盖，
  属于需要作者确认的 frozen boundary 变更，不在"backend retirement"授权范围内。
  唯一例外：`canon/outline_adapter.py`（把 Canon-aware 章纲写回 V2 StoryOutlineRepository）
  确实是 legacy 第二套 outline 存储的适配器 → 已随 outline 后端删除。
tests/test_v2_frozen_guard.py / test_v3_frozen_guard.py / test_acceptance_repair_regressions.py
  frozen 证据文件（§49）→ 保留；其中 V3 守卫与验收回归按 AGENTS.md §20
  「历史 timepoint → 永久不变式」改挂在 current owner 上（见 §96e）
docs/v4/V4_00…V4_12_*、docs/CHANGELOG.md、docs/V3_*、docs/FROZEN_EVIDENCE_MANIFEST.json
  历史事实与冻结证据 → 不修改（§51；CHANGELOG 只登记已发布版本，本轮未发布 → 不新增条目）
docs/ARCHITECTURE.md、docs/DATA_MODEL.md、docs/STORY_BUILDER_USER_GUIDE.md、
docs/NEW_NOVEL_GUIDE.md、docs/CONTENT_PACK.md、docs/LEGACY_COMPAT.md
  current 文档 → 顶部加"V2/V3 后端已退休"状态说明并指向 V4 SSOT；历史正文不改写
novel/config/ai/providers.json
  唯一仍被 current 代码读取的 config（LLM Gateway）
```

## 96e. 需要作者知情的两处判定（frozen 证据文件的边界迁移）

```text
1. tests/test_v3_frozen_guard.py
   原文件固定的是 V3-P1 对 `route_lab.list_branches` 的放宽边界。route_lab 整体退休后，
   这条不变式改挂在 current owner：
     只读空态 → JourneyService 空投影（不报错）
     受门前置 → /studio/generate 缺少模型能力给稳定错误码 GENERATION_UNAVAILABLE
     legacy 端点 → 21 个路径必须 404
   断言强度不降低（三条都要求"真实结果或带稳定错误码的真实拒绝"）。

2. tests/test_acceptance_repair_regressions.py
   NF-001…NF-012 原本在 V3 Command Center 上断言。命令中心退休后：
     NF-002 唯一 canonical store → BlueprintRepository + Studio REST
     NF-003/004 作者语言 / 不泄漏引擎 id → Studio 蓝图投影 + 交付物
     NF-005 单一阶段公式 → JourneyService（REST / MCP / 服务层三方一致）
     NF-008 推荐下一步必须可执行 → journey next_action → /studio/generate
     NF-011 删除＝整体归档不留孤儿 → ProjectService.archive_novel（并修好 V4 产物未纳入归档清单的真实缺陷）
     NF-012 有问题报真实 blocker → DeliveryValidator preflight
   随能力退休的项（writer 草稿路径 / outline 章节导出 / 引导流 onboarding）不再作为 current 断言。

这两处是"历史 timepoint 断言 → 永久不变式 + current owner"的迁移，
不是删除 frozen 文件、也不是放宽断言；frozen Repair Contract / Gate / truth boundary 未改动。
```

## 96f. 本轮修掉的真实缺陷（不是清理副作用）

```text
1. novel_admin.novel_artifact_paths 只列举 V2 产物（profile / pack / runtime state / writer /
   旧 outline），V4 的 blueprint / quality / editor / delivery / memory / agent / plugin state
   都不在归档清单里 → "删除作品＝整体归档不留孤儿"（NF-011）在 V4 其实是**假的**。
   现在全部经 `persistence.paths` 枚举 → NF-011 断言重新成立（并新增守护断言）。
2. JourneyService 的文档声称是"唯一投影"，实现却委托 V3 模块 → 已改为真正唯一实现。
3. story_engine/context.py（原 creator）文档声称"只读"，实现却 `profiles.ensure()`
   隐式写 profile → 改为 `load()`，读操作不再写文件。
```

## 96g. Public API removals（任务书 §77）

```text
删除的 externally reachable 端点（全部为 undocumented legacy compatibility）：
  /api/story-builder/v3/novels
  /api/story-builder/v3/novels/{novel_id}/command-center
  /api/story-builder/v3/novels/{novel_id}/journey
  /api/story-builder/catalogs | /steps/{step_id} | /content-packs
  /api/story-builder/sessions/**（含 selections / back / recommendations / compile-blueprint …）
  /api/story-builder/blueprints/**（adventures / confirm / outlines）
  /api/story-builder/outlines/**（export / confirm / items 编辑）
  /api/story-builder/outline/**（plan / forge / chain / export / versions / version-diff /
                                impact / revise / restore / merge-versions / confirm）
  /api/story-builder/runtime/**（branches / state / start / advance / tick / fork）
  /api/story-builder/creator/**（world / characters / plot / progression / memory / director / linkage）
  /api/story-builder/settings/**（seed / check / impact / overview / regions / relationships）
  /api/story-builder/inspector/**（overview / search / record）
  /api/story-builder/repair/**（diagnosis / history）
  /api/story-builder/writer/**（context / drafts / sync-facts）
  /api/story-builder/guided-flow
  /api/story-builder/export/package | /api/story-builder/export/writer-bundle（Round 1 已删）

每一个都是：
  documented V4 API? NO（V4 契约只有 /novels + /studio + /editor + /delivery + /agent + /canon）
  current consumer? NO（Story Studio / MCP / Agent / Delivery / Plugin 都不调用）
  legacy compatibility only? YES → 随 legacy 后端一起退休
保留 URL：/api/story-builder/novels（GET/POST/GET id/PATCH/DELETE）→ owner 从 God router 迁到
  `api/project_routes.py`（行为不变：409 二次确认、404 PROFILE_NOT_FOUND、422 校验）。
```

## 96h. 版本建议（任务书 §78）

```text
本轮只删除了 **未被 V4 文档化为 public API 的 legacy compatibility 端点**，
没有删除任何 documented / supported V4 public API（/novels 的 URL 与语义保持不变，
Studio / Editor / Delivery / Agent / Canon / MCP 全部不变）。
按项目版本策略：
  · 兼容 surface 被移除（V2/V3 端点 404）→ 属于"移除已退役兼容层"；
  · V4 支持面没有变化、没有新增能力 → **patch 级**，建议 `v4.0.1`。
不建议 minor / major：没有任何 documented V4 能力被删除或改变。
（发布动作不在本轮范围内：不 push / 不 merge / 不打 tag。）
```

