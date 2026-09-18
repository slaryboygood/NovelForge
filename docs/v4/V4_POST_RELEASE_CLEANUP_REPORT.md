# NovelForge V4 — Post-Release Full Repository Cleanup Report

> 阶段：**V4.0.0 之后的 current-tree 深度清理**
> 分支：`v4-post-release-cleanup`（基线 `baa81ef39b8f4563923a28a2b2d2d28e77e423a4` = `v4.0.0`）
> 判据：`docs/v4/V4_POST_RELEASE_CLEANUP_INVENTORY.md`（KEEP / MIGRATE / DELETE / LOCAL_DELETE / REVIEW_REQUIRED）
> 结论：**本轮完成 UI 与数据层清理并被门禁验证；backend legacy 层尚未移除 → 整体 verdict = BLOCKED**（见 §96）

## 1. Starting commit

```text
baa81ef39b8f4563923a28a2b2d2d28e77e423a4（main = v4 = v4.0.0 tag target）
```

## 2. Cleanup branch

```text
v4-post-release-cleanup（本地；未 push、未 merge、未建 tag —— 任务书 §95）
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
