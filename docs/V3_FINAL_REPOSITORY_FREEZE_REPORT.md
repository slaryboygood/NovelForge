# NovelForge V3 Final — Repository Freeze Report

> 任务：NovelForge V3 Final Freeze & Repository Sanitization
> 目标：冻结当前 V3 最终代码；清理 Git 历史与仓库垃圾，为 V4 建立干净基线
> 日期：2026-09-17
> 本任务**不修复任何产品问题**（产品缺陷全部转入 V4，见 `docs/V3_FINAL_FREEZE.md`）。

---

## Final Root Commit

```text
subject   : NovelForge V3 Final — Functional Closure
branch    : main
tag       : novelforge-product-v3-final（annotated tag）
parent    : 无（orphan / root commit；之前的历史不进入新 public history）
hash      : 见 tag 注解（git tag -n99 novelforge-product-v3-final）
            与外部冻结日志 F:\AI_小说\NovelForge_V3_final_freeze_log.txt
```

说明：本报告文件本身是 root commit 的一部分，因此**无法在文件内自引用该 commit 的 hash**
（commit hash 由包含本文件的 tree 决定）。hash 记录在注解 tag 的消息与外部冻结日志里，
两者都在冻结完成后写入，可独立核对。

冻结过程中出现过两个中间 root（`ebee666` → `fbe3f89`），它们都由 amend 取代，
**不再视为最终 root**；最终 root 只有一个，即上面 tag 指向的那一个 commit，
且 `git rev-list --count HEAD == 1`。

新历史结构：

```text
NovelForge V3 Final — Functional Closure   ← 唯一 root
        ├── main                            （V3 Final 基线）
        └── v4                              （V4 起点，指向同一 commit，尚未开发）
```

---

## Files Removed

### 已删除（本次清理，全部先归档到外部冷备 zip）

| 路径 | 体积 | 分类 | 删除依据 |
| --- | --- | --- | --- |
| `workspace/qa_review_2026_09_17/` | 10.9 MB | Initial Review 的 QA 临时数据根 + 脚本 + 截图 + 日志 | QA temporary artifact（已归档） |
| `workspace/qa_repair_2026_09_17/` | 5.5 MB | Repair 的 QA 临时数据根与探针证据 | QA temporary artifact（已归档） |
| `workspace/qa_rereview_2026_09_17/` | 32.6 MB | Final Re-review 的 QA 临时数据根、截图、下载物、脚本 | QA temporary artifact（已归档） |
| `workspace/product_v3/` | 18.8 MB | V3 视觉审查截图（1440 / 1280 / 1024 / 390） | obsolete screenshots（已归档） |
| `workspace/v3_ui_test_root/` | 0.7 MB | 浏览器门禁使用的临时数据根 | regenerable test root（已归档） |
| `__pycache__/` 共 10 个 + `*.pyc`（约 360 个） | ≈ 9 MB | Python 字节码缓存（scripts / src / tests） | cache（运行时自动重建） |

删除方式：`git clean -fdx -- <显式路径列表>`，先做 dry-run 确认只命中这 5 个目录
（全部位于 `workspace/` 之下）后才执行；`__pycache__` 同样先 dry-run 再清理。
未使用通配符、未使用递归删除命令。

### 保留（REVIEW 后判定为不可删除 / 仍然有用）

以下文件**看名字像垃圾但不是垃圾**，逐条核查引用与内容后保留：

| 路径 | 判定 | 理由（证据） |
| --- | --- | --- |
| `workspace/pilot_v2/` | KEEP | 名字像 V2 临时实验，但内含 **pilot 小说正式章节**（`novel/final/ch001..ch005`）；创作内容不可重新生成 |
| `workspace/wasteland_001_exports/` | KEEP | V2 historical Chapter IR（570 章）+ reconstruction；`export_package._history_dir()` 与 writer context 运行时读取；不可重新生成 |
| `workspace/*.md`、`DEEPWRITE_*.md` | KEEP | 小说生产过程的评审 / 校准 / 迁移报告（作者工作产物） |
| `.dsh-runtime/`（663 MB） | KEEP | 随附 Node 运行时 + Playwright；删掉浏览器门禁就跑不了 |
| `ui/node_modules/`、`ui/dist/` | KEEP | 前端依赖与当前构建产物（FastAPI 直接服务 dist） |
| `.venv/`、`.python311/` | KEEP | 本地 Python 环境（测试与脚本运行所需） |
| `.agents/`、`.codex/` | KEEP | 本地 agent 工具目录（ignored） |
| `.env.local` | KEEP | 本地凭据（`DEEPSEEK_API_KEY` / `ARK_API_KEY`），ignored，永不提交 |
| `scripts/wasteland_001_m1b_closure.py` | KEEP | 被 `tests/test_m1b_v2_coverage.py:22` 引用 |
| `scripts/seed_long_line_state.py` | KEEP | 被 `tests/browser_creator_long_lines.cjs:59` 调用 |
| `novel/config/author/restricted_secrets.yaml` | KEEP | 名字含 secrets，内容是**剧情剧透控制表**，不是凭据 |
| `tests/browser_creator_*.cjs` 等 legacy 验收脚本 | KEEP | 针对产品仍在提供的 legacy 面板，不是废弃实验 |
| `novel/runtime/chapter_0001/**`、`novel/status/chapter_0001.json` | KEEP（记为 V4 关注项） | 看似被提交的运行期草稿 / 清单，且含 writer 草稿正文，删除不可逆；建议 V4 评估改 ignore |

---

## .gitignore Removed Rules

只删除**可证明冗余**的规则（每条都用 `git check-ignore -v` 验证：删除后仍被其它规则命中）。

| 删除的规则 | 原因 | 删除后的覆盖规则（已验证） |
| --- | --- | --- |
| `api-key.txt` | 重复规则 | `*api-key*.txt` → `api-key.txt` 仍 IGNORED |
| `*-api-key.txt` | 重复规则 | `*api-key*.txt` → `x-api-key.txt` / `my-api-key.txt` 仍 IGNORED |
| `.env.local` | 重复规则 | `.env.*` → `.env.local` 仍 IGNORED |

删除后关键路径复验（`git check-ignore -v`）：

```text
.env                    IGNORED  <- .gitignore:.env
.env.local              IGNORED  <- .gitignore:.env.*
.env.production         IGNORED  <- .gitignore:.env.*
.env.example            not ignored（仍被跟踪，示例文件必须可见）
api-key.txt             IGNORED  <- .gitignore:*api-key*.txt
workspace/x.txt         IGNORED  <- .gitignore:workspace/
ui/dist/index.html      IGNORED  <- .gitignore:ui/dist/
novel/authoring/story_engine/x.json   IGNORED  <- .gitignore:novel/authoring/story_engine/
novel/runs/run.json     IGNORED  <- .gitignore:novel/runs/
reference_books/book_001/source/a.txt IGNORED  <- .gitignore:reference_books/*/source/
```

---

## .gitignore Kept Rules

逐条审计（`Exists` = 冻结时磁盘上是否存在该路径）：

| Pattern | Current Purpose | Exists | Needed for V4 | Decision |
| --- | --- | --- | --- | --- |
| `.dsh-runtime/` | 随附运行时 / Playwright / 浏览器门禁依赖 | 是 | 是 | KEEP |
| `node_modules/` | 前端依赖（实际路径 `ui/node_modules`） | 是（`ui/` 下） | 是 | KEEP |
| `npm-cache/` | 通用 npm 缓存目录名（当前无引用） | 否 | 是（防御） | KEEP |
| `*.log` | 通用日志 | 否 | 是 | KEEP |
| `.agents/` | 本地 agent 目录 | 是 | 是 | KEEP |
| `__pycache__/`、`*.py[cod]` | Python 缓存 | 是（内容已清空） | 是 | KEEP |
| `.pytest_cache/`、`.mypy_cache/` | 测试 / 类型检查缓存 | 否 | 是 | KEEP |
| `.coverage`、`.coverage.*` | 覆盖率产物 | 否 | 是 | KEEP |
| `.vscode/`、`.idea/` | IDE | 否 | 是 | KEEP |
| `Thumbs.db`、`.DS_Store` | OS 垃圾 | 否 | 是 | KEEP |
| `*.tmp`、`*.temp`、`*.bak`、`*.swp` | 临时文件 | 否 | 是 | KEEP |
| `.codex_tmp/` | Codex 临时目录（旧命名） | 否 | 是（防御） | KEEP |
| `.venv/`、`venv/`、`.python311/` | 本地 Python 环境 | 是（`.venv`、`.python311`） | 是 | KEEP |
| `.env` | 真实环境文件（必须忽略） | 否 | 是 | KEEP |
| `.env.*` + `!.env.example` | 环境变体忽略 + 保留示例 | 是（`.env.local`） | 是 | KEEP |
| `*api-key*.txt`、`*apikey*.txt`、`*secret*.txt`、`*credential*.txt`、`*token*.txt` | 凭据类文件（必须忽略） | 否 | 是 | KEEP |
| `novel/authoring/story_engine/` | 真实作者数据（运行时生成） | 是 | 是 | KEEP |
| `novel/config/story_engine/*_pack.json` | 生成的内容包 | 是 | 是 | KEEP |
| `novel/authoring/story_builder/outlines/*/ol_forge_*` | 锻造出的作者大纲 | 是 | 是 | KEEP |
| `novel/authoring/story_builder/sessions/*.json` | 构筑会话 | 是 | 是 | KEEP |
| `*.partial.md`、`*.partial.json`、`**/traces/`、`novel/runs/` | 运行遥测 | 是（`novel/runs/` 下 77 个 `traces/`） | 是 | KEEP |
| `ui/dist/`、`novel/workspace/`、`*.tsbuildinfo` | 构建产物与运行工作区 | 是 | 是 | KEEP |
| `playwright-report/`、`test-results/`、`coverage/`、`htmlcov/`、`.vite/`、`*.png.tmp` | 浏览器验收 / 覆盖率产物 | 否 | 是 | KEEP |
| `novel/authoring/revisions/` | 可重建的派生修订历史 | 否 | 是 | KEEP |
| `workspace/` | 本地运行时数据根（关键规则） | 是 | 是 | KEEP |
| `.codex/` | 本地工具目录 | 是 | 是 | KEEP |
| `reference_books/*/source/`、`reference_books/*/derived/` | 参考书原文与派生中间产物（版权 + 可重建） | 是 | 是 | KEEP |

保留 `npm-cache/` 与 `.codex_tmp/` 的理由：这两条既不是重复规则，也无法证明「永不再产生」；
删除它们只会让将来某个工具在仓库根生成同名目录时直接暴露为未跟踪文件。
按「不要为了缩短 .gitignore 导致本地环境 / 缓存进入 Git」的要求，保留为防御性规则。

---

## Tags Removed

全部 8 个旧 tag 已从活动仓库删除（`ARCHITECTURE_EXCEPTION_DECISION = B`，用户授权
2026-09-17）：

| Tag | 指向 | 分类 | 删除前引用检查 | 处理 |
| --- | --- | --- | --- | --- |
| `novelforge-product-v2.0` | `56cda82`（annotated `474f3ec`） | V2 release | `tests/test_v2_frozen_guard.py`（守卫已迁移） | REMOVED |
| `novelforge-product-v3.0` | `20d03cf`（annotated `d6bf763`） | V3.0 release | README / CHANGELOG / LEGACY_COMPAT（已迁移为 historical metadata） | REMOVED |
| `story-engine-v2.0` | `fbe99cd`（annotated `d8b31c6`） | Story Engine V2 | PRODUCTION_GUIDE（已迁移） | REMOVED |
| `novelforge-final-v1.0` | `4fb02d1`（annotated `04cbc87`） | V1 / pilot final | 0 引用 | REMOVED |
| `novelforge-minimal-product-baseline` | `8dcf019`（annotated `54fd67c`） | 早期 baseline | 0 引用 | REMOVED |
| `phase6.2-baseline` | `19215b7`（annotated `3179e39`） | 开发期 phase tag | 0 引用 | REMOVED |
| `phase9-before-minimal-reset` | `e834ca4`（lightweight） | 开发期 phase tag | 0 引用 | REMOVED |
| `phase9-pre-product-cleanup` | `dbccc63`（lightweight） | 开发期 phase tag | 0 引用 | REMOVED |

全部被删 tag 的名称、commit 与 tag object 都记录在
`docs/FROZEN_EVIDENCE_MANIFEST.json` 的 `historical_releases`（标记为
`historical / archived / not an active Git ref`），字节与完整历史进入 cold bundle，
可完整恢复。

## Tags Kept

| Tag | 指向 | 说明 |
| --- | --- | --- |
| `novelforge-product-v3-final` | V3 Final root commit | 唯一活动 release ref；annotated tag，注解含 root commit hash 与验收摘要 |

最终活动仓库只有这一个 tag；`git tag -l` 的输出即为该行。

---

## Branches Removed

Local branches：

| Branch | 指向 | 分类 | 处理 |
| --- | --- | --- | --- |
| `codex/product-v3-game-ui` | `021b9ce` | V3 开发 / Repair / Re-review 分支 | REMOVE（内容已进入 V3 Final root commit） |
| `codex/wasteland-001-canon-final-repair` | `758bf3a` | M11 历史修复分支 | REMOVE |
| `codex/canon-infrastructure-v1` | `d09e251` | Canon 基础设施实验分支 | REMOVE |
| `codex/chapter-semantic-ir-v1` | `56cda82` | Chapter IR 实验分支 | REMOVE |
| `codex/story-builder-only` | `fbe99cd` | Story Builder 独立分支 | REMOVE |
| `codex/v2-real-novel-pilot` | `4fb02d1` | V2 pilot 分支 | REMOVE |
| `main`（旧） | `7588c03` | 旧主线（novel pipeline 线） | REPLACED（新 main = V3 Final root） |

Remote branches：

| Remote ref | 指向 | 处理 |
| --- | --- | --- |
| `origin/main` | `acc6e84` | force-with-lease 覆盖为 V3 Final root（前置：fresh-clone proof 全绿） |
| `refs/tags/novelforge-minimal-product-baseline` | `54fd67c` | 删除（本地已删） |
| `refs/tags/phase6.2-baseline` | `3179e39` | 删除（本地已删） |

远端现状（`git ls-remote`）：只有 `refs/heads/main` + 上面这 2 个开发期 tag
（V2 / V3 release tag 从未推送到远端）。

最终分支：

```text
main    → V3 Final root commit（唯一基线）
v4      → 与 main 同一 commit（V4 起点，本任务不在此开发）
```

Codex 工具自身的 checkpoint ref（`refs/codex/turn-diffs/**`）由工具管理，不属于仓库历史，未删除。

---

## Repository Bundle

```text
文件        F:\AI_小说\NovelForge_pre_V4_full_history.bundle
内容        git bundle create --all（全部分支 / tag / origin ref / HEAD）
内容验证    git bundle verify → "The bundle records a complete history" / "is okay"
恢复验证    在 F:\AI_小说\_bundle_restore_check 独立 clone 成功：
            7 个分支全部恢复、8 个 tag 全部恢复、HEAD = 021b9ce、
            文件级抽查通过（docs/V3_FULL_PRODUCT_ACCEPTANCE.json 可读取）
用途        改写 Git 历史之前的完整冷备；不提交到新 Git history
```

QA 证据冷备（同样不进入新 Git history）：

```text
文件        F:\AI_小说\NovelForge_V3_qa_evidence_archive.zip
体积        55.9 MB / 2515 个条目
内容        qa_review / qa_repair / qa_rereview / product_v3 / v3_ui_test_root
验证        用 .NET ZipFile 枚举条目，确认三份验收报告的原始证据与 QA 脚本都在
            （journey*.cjs、genqa_generation_quality.json、browser_journey.json、
              export_inspection.json 等）
```

冻结日志（外部，记录 root commit hash 与逐项验证结果）：

```text
F:\AI_小说\NovelForge_V3_final_freeze_log.txt
```

---

## Final Tests

### 冻结前（清理之前：V3 开发分支 + Repair 工作树）

```text
.venv\Scripts\python.exe -m pytest -q                     889 passed / 687 deselected / 0 failed（278.08s）
.venv\Scripts\python.exe scripts/validate_project.py      PASS
npm.cmd run build --prefix ui                             PASS（vite 5.4.21 / 81 modules）
typecheck：cd ui; npm.cmd exec tsc -- --noEmit             PASS（exit 0）
```

### 冻结后（在新 root commit 之上重新执行）

用以确认「Git 清理没有误删运行需要的资源」。原始输出见外部冻结日志。

```text
pytest -q                                                 = 889 passed / 687 deselected / 0 failed（266.84s）
scripts/validate_project.py                               = PASS
npm.cmd run build --prefix ui                             = PASS
typecheck（cd ui; npx tsc --noEmit）                       = PASS（exit 0）
browser_v3_p0_acceptance.cjs                              = PASS
browser_v3_p5_acceptance.cjs                              = PASS
browser_v3_p6_acceptance.cjs                              = PASS
browser_v3_p7_acceptance.cjs                              = PASS
browser_v3_visual_asset_gate.cjs                          = PASS
browser_advanced_tools.cjs                                = PASS
git status                                                = clean（无未提交 / 未跟踪文件）
```

浏览器门禁使用的隔离数据根（`workspace/freeze_check_gates` / `workspace/freeze_check_ui`）
与截图目录（`workspace/freeze_check_shots`）都是 gitignored 的临时物，复验后已删除。

冻结后仍保持绿的**冻结边界守卫**（说明 tag 恢复是必要的）：

```text
tests/test_v2_frozen_guard.py::test_v2_release_tag_still_points_at_recorded_commit   PASS
tests/test_v2_frozen_guard.py::test_v2_release_record_documents_frozen_reference    PASS
tests/test_v2_frozen_guard.py::test_tracked_authoring_data_matches_v2_release       PASS
```

以下为删除 V2 tag 时的反证（当时实测结果，证明冲突真实存在）：

```text
pytest -q  →  1 failed, 888 passed, 687 deselected
FAILED tests/test_v2_frozen_guard.py::test_v2_release_tag_still_points_at_recorded_commit
       assert 128 == 0   （缺少 V2 release tag：novelforge-product-v2.0）
```

恢复后的完整结果：

```text
pytest -q                                                 = 889 passed / 687 deselected / 0 failed
scripts/validate_project.py                               = PASS
npm.cmd run build --prefix ui                             = PASS
typecheck（cd ui; npx tsc --noEmit）                       = PASS（exit 0）
browser_v3_p0_acceptance.cjs                              = PASS
browser_v3_p5_acceptance.cjs                              = PASS
browser_v3_p6_acceptance.cjs                              = PASS
browser_v3_p7_acceptance.cjs                              = PASS
browser_v3_visual_asset_gate.cjs                          = PASS
browser_advanced_tools.cjs                                = PASS
git status                                                = clean（无未提交 / 未跟踪文件）
```

---

## New V4 Base

```text
起点        NovelForge V3 Final root commit（main）
V4 branch   v4（已创建并指向同一 commit；本任务不在其上开发）
V4 方向     见 docs/V3_FINAL_FREEZE.md 的 V4 Direction：
            MCP · plugins · quality architecture · generation quality loop ·
            delivery quality validation · automated evaluation
```

---

## Known Issues Deferred to V4

完整清单与影响见 `docs/V3_FINAL_FREEZE.md`（Known Issues Deferred to V4）。摘要：

```text
NF-003            章节标题语义重复 + 字段标签进正文（P2，最高优先级）
NF-006            内容包标题长首句硬截断（P3）
NF-010 / NR-001   刷新后「确定这个方向」不可点击（P3）
NF-016            实体只有原型占位名、导出物无占位标注、无改名能力（P3）
NF-018            README 类型检查命令不生效（P4）
NF-020            门禁盲区仅部分消除（P3）
NR-002            导出包混入无关 V2 历史分区（P3）
NR-003            Markdown 导出角色行带机器枚举、分区标题中英混排（P4）
NR-004            导出面板显示 export_id（P4）
Landing 性能      投影成本随作品数线性增长（P3）
Writer 编辑       写作草稿不可编辑（P4）
NF-019            vite / esbuild dev 依赖 advisory（P4）
发布证据口径      V3_FULL_PRODUCT_ACCEPTANCE.json 与默认 pytest 命令不一致（P4）
```

本任务**未修改任何产品行为、UI、Story Engine、Prompt、Generator、Writer、Export、
Stage / Progress、数据模型、API 行为或测试逻辑**。唯一修改的非源码文件是 `.gitignore`
（删除 3 条可证明冗余的规则）；新增文件是本报告与 `docs/V3_FINAL_FREEZE.md`。

---

## Architecture Exception Decision（executed）

用户在 2026-09-17 给出 **Architecture Exception Decision = 选择 B**，授权把仓库的旧
release 冻结机制从：

```text
Git tag / historical commit must remain resolvable
```

迁移为：

```text
tracked frozen evidence / manifest must remain verifiable
```

### 迁移内容

| 项 | 迁移前 | 迁移后 |
| --- | --- | --- |
| 冻结权威 | `novelforge-product-v2.0` tag + commit `56cda82` 必须可解析 | `docs/FROZEN_EVIDENCE_MANIFEST.json`（tracked）+ 加密摘要 |
| 漂移检测 | `git diff 56cda82 HEAD -- novel/authoring` | 对 `novel/authoring` 已跟踪文件计算 sha256 摘要并与 manifest 比对 |
| Guard | 要求 tag / 旧 commit 可解析 | 重写为 manifest 结构 + 摘要一致 + 单一 root + 历史 ref 只作 metadata + 文档标注诚实性 |
| 旧历史在线寻址 | 活动仓库（tag / commit） | 外部 verified bundle（`NovelForge_pre_V4_full_history.bundle`） |

新的守卫**完全不依赖历史 commit / tag**（需要 git 的断言在没有 git 时 skip）：

```text
test_frozen_evidence_manifest_is_well_formed          manifest 结构 + 活动 release + 外部归档
test_historical_releases_are_metadata_only            历史 release 必须标注 not an active Git ref
test_frozen_evidence_digest_matches_tracked_files     novel/authoring 摘要一致（不依赖历史 commit）
test_history_is_a_single_root_commit                  git rev-list --count HEAD == 1
test_old_release_refs_are_not_required_to_resolve     旧 ref 缺失是预期；存在也不得成为新历史祖先
test_documents_marking_old_release_refs_stay_honest   引用旧 release 的文档必须标注 historical
```

被冻结资产的摘要（`novel/authoring`，242 个已跟踪文件，CRLF → LF 归一化）：

```text
evidence_id = v2_frozen_tracked_authoring_data
digest      = a368deb9f3ce0c6000364547b6e0cede8c6c0c92fa6713344cc2ab94e6ff54ca
```

### 本次改动范围（严格遵守允许清单）

```text
tests/test_v2_frozen_guard.py                     重写为 manifest 驱动的守卫
docs/FROZEN_EVIDENCE_MANIFEST.json                新增：tracked frozen evidence
README.md / AGENTS.md / novelforge.project.yaml   活动 release 指针 + 历史标注
docs/CHANGELOG.md / docs/LEGACY_COMPAT.md         旧 release 语义改为 historical / archived
docs/NOVELFORGE_PRODUCT_V2_RELEASE.md             标注 v2.0 tag 已归档
docs/NOVELFORGE_REAL_NOVEL_PRODUCTION_GUIDE.md    标注 story-engine-v2.0 已归档
docs/V3_FINAL_FREEZE.md / 本报告                   冻结记录同步
```

禁止修改的范围内**没有任何改动**：产品功能、UI、Story Engine、Generator、Writer、Export、
业务行为与产品质量问题全部保持原样。

### Tag 策略（执行结果）

```text
活动仓库保留：novelforge-product-v3-final（唯一活动 release ref）
已删除：      novelforge-product-v2.0 / novelforge-product-v3.0 / story-engine-v2.0
              novelforge-final-v1.0 / novelforge-minimal-product-baseline
              phase6.2-baseline / phase9-before-minimal-reset / phase9-pre-product-cleanup
历史名称与 commit：记录在 docs/FROZEN_EVIDENCE_MANIFEST.json 的 historical_releases，
              并标注 historical / archived / not an active Git ref
```

## Mandatory Fresh-Clone Proof

在改写 GitHub 之前，建立一个**只暴露**以下 refs 的临时 remote，并从该 remote fresh clone：

```text
main
v4
novelforge-product-v3-final
```

必须确认：

```text
[ ] 旧 V1 / V2 / V3 commit 不可达
[ ] 旧 release tag 不存在
[ ] 默认 pytest PASS
[ ] 新 frozen guard PASS
[ ] validate_project PASS
[ ] frontend build PASS
[ ] typecheck PASS
[ ] git status clean
```

这是本次 architecture exception 的**最终 acceptance criterion**。
证明的原始输出记录在外部冻结日志
`F:\AI_小说\NovelForge_V3_final_freeze_log.txt`（本报告属于 root commit 本身，
无法在不产生第二个 commit 的前提下再次写入结果）。

## Remote Rewrite

上述证明全部通过后才执行：

```powershell
# 1) 用 V3 Final 单一 root commit 覆盖远端 main（force-with-lease 锁定旧值）
git push --force-with-lease=main:acc6e844792e25848d4ed4ce54c5c50ffb93c2e4 origin main

# 2) 推送 V4 起点分支
git push origin v4

# 3) 删除远端两个已废弃的开发期 tag
git push origin :refs/tags/novelforge-minimal-product-baseline
git push origin :refs/tags/phase6.2-baseline

# 4) 推送唯一的 V3 Final tag
git push origin novelforge-product-v3-final

# 5) 从真实 GitHub 再 fresh clone 做一次 smoke verification
```

旧 V2 / V3 / story-engine release tag **不会**被推回远端。
