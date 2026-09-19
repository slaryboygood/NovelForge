# NovelForge V4.0.1 — Skill Dogfood / Operator Acceptance Report

> 本报告由「新 Codex 只拿 `skills/novelforge-v4.0.1/**` + 公开产品接口」的真实会话产出。
> 目的不是改产品，而是回答：**这批 skill 是否足以让新操作者正确使用 V4.0.1。**
> 方法论纪律：先只读 skill / README / `docs/v4/V4_0_1_*.md`；不主动读 `src/**`、
> `ui/src/**`、`tests/**`；`SKILL_GAP` 与 `SOURCE_ESCAPE` 全部逐条记录（见 §5–§6）。

## 0. 结果摘要

```text
NOVELFORGE V4.0.1 SKILL DOGFOOD & OPERATOR ACCEPTANCE = BLOCKED
（理由：4 个核心 workflow 中 Delivery(strict) 与 Agent(approval) 存在产品级阻塞；
   MCP stdio 入口无法启动；这些不是"skill 没写清楚"能绕过的，必须回产品修）

但：UI/REST 侧的 create → blueprint → generate → quality → repair → editor →
    delivery(explicit_revisions) → plugins 全链路**只靠 skill + 公开接口**跑通；
    77/77 skill 完成 review；skill 缺陷 18 项（24 个文件）已修复并重建 baseline。
```

| 项目 | 值 |
| --- | --- |
| Starting HEAD | `4cf4d1ae05257b4cb2e3887929e38b1f3b5b3a5a` |
| Branch | `v4-401-feature-skills` → `v4-401-skill-dogfood` |
| Dogfood root（隔离） | `%TEMP%\nf_dogfood_401_root2`（`scripts/studio_ui_test_server.py --root`） |
| Test novel | `NF_SKILL_DOGFOOD_401`（+ 控制组 `studio_clean`、探针 `NF_DOGFOOD_PROBE` / `NF_NOPROVIDER_PROBE`） |
| 模型 | 仅 stub（deterministic provider，0 真实模型调用） |
| Skills reviewed | 77 / 77 |
| Source escape count | 4 |
| Manual guess count | 5 |
| Product code changed | 否（`src/` / `ui/` / `novel/` diff 为空） |

## 1. 环境与基线

```text
git status --short        clean（开始与结束都为 clean）
git branch --show-current v4-401-feature-skills（开始）→ v4-401-skill-dogfood
git rev-parse HEAD        4cf4d1a…（与任务给定 expected HEAD 一致）
git tag --list            novelforge-product-v3-final / novelforge-product-v4-final /
                          v4.0.0 / v4.0.1（未改动任何一个）
```

启动产品的两条路径（skill 里只写了第一条，dogfood 用的是第二条）：

```text
scripts/start_novelforge_ui.py                  → 无 --root，永远用仓库根
scripts/studio_ui_test_server.py --root <dir>   → 隔离根 + stub 模型 + fixture 插件（本 dogfood 使用）
```

## 2. Workflow 结果表（§45）

| Workflow | Skills used | Result | Skill defects | Product gaps | Product bugs |
| -------- | ----------- | ------ | ------------- | ------------ | ------------ |
| A Project/Studio | `project.*`(4)、`studio.open-story-studio` | **PASS**（create 201 / 重复 409 / rename 200 / 空标题 422；Studio golden gate PASS） | `studio.open-story-studio` 写了不存在的 `--root` | — | — |
| B Create Blueprint | `workflows.create-new-story-blueprint` + `generation.*`(9) | **PASS（含 1 个产品陷阱）** | `generate-character-arc` 缺必填字段；`generate-structural-unit` id 形式错；`generate-chapter-plan` / `generate-scene-plan` 示例 id 错；generation README 未写 `GENERATION_UNAVAILABLE` 复用语义 | GAP-001 dry_run；GAP-002 setup/payoff | **`SEQUENCE_INVALID`**：给 theme/world/story_arc 传 `parent_id` 必产生 Q0 major（未列为 gap） |
| C Editor | `editor.*`(6) | **PASS**（dry_run 0 mutation；越界 rewrite 被拒；restore 后 diff 为空；accept→accepted；reject 只记 metadata） | `accept-revision` 的幂等声明与实测不符 | GAP-006（advanced ops 无 wire 入口，本次未受阻） | — |
| D Quality | `quality.evaluate-blueprint` / `inspect-quality-report` / `list-quality-issues` | **PASS**（Q0–Q9 gate 行 + severity + evidence + repairable 都可读） | `inspect-quality-report` 的 summary / blockers 口径写错 | — | **gate blockers 计数不一致**（Q9 blocked 但 blockers=0） |
| E Repair | `repair.*`(4) | **PASS**（plan 0 mutation；apply 2 次模型调用产生新 revision；verifier 诚实报 `partial` 而非宣称 resolved） | — | GAP-002（`CLIMAX_UNPREPARED` 直接来自缺少 payoff/decision） | — |
| F Delivery | `delivery.*`(6) | **PARTIAL → 经 explicit_revisions 完成**（4 格式全部下载；bytes/checksum/MIME/文件名全部校验通过；路径穿越/跨作品/非法路径被拒；同 key 幂等） | `validate-delivery` 文档的顶层 `excluded[]` 不存在；policy 放宽语义未写清 | GAP-007（UI 无 explicit_revisions 入口——这次正是靠 REST 参数才交付成功） | **历史 quality issue 不按 status 过滤，永久阻塞 preflight**（P0，见 §8） |
| G Canon | `canon.*`(5) | **PASS（修正文档后）** | `novel_id` 是 query 参数（两个 skill 写成 body）；chapter plan schema 未写 | GAP-003（REST 直连 canon，无 Application/MCP） | — |
| H Memory | `memory.inspect-derived-memory` / `build-generation-context` | **PASS（修正文档后）** | `MemoryQuery(text=…)` 不存在 | GAP-004（无 UI/REST/MCP；无法回答"这次生成读了什么"） | — |
| I StoryState | `story-state.*`(2) | **PASS（只读）** | 字段清单不全（`timeline.current_time`） | GAP-008（无产品级入口；只读够用） | — |
| J Plugins | `plugins.*`(5) | **PASS**（approve→enable→active；disable 精确卸载；REST 只读状态与 trust_model 文案一致） | `inspect-plugin-contributions` 未区分"声明"与"已注册" | GAP-005（生命周期 Application-only） | — |
| K Agent | `agent.*`(6) | **BLOCKED（approval）/ PASS（plan-start-inspect-reject-resume-cancel）** | `plan/start/inspect` 响应字段与文档不一致（已修） | — | **approve 一个 protected step 之后 session 直接 failed**（P0，见 §8） |
| L MCP | `mcp.*`(5) | **BLOCKED（stdio）/ PASS（in-process）** | 未写 `PYTHONPATH=src` 前置 | — | **stdio 入口在 mcp 1.9.4 启动即崩**（P0，见 §8） |
| M AI Provider | `ai.*`(4) | **PASS**（默认 enabled=[]；无 provider 时 422 `GENERATION_UNAVAILABLE` + 0 mutation；只读路径仍可用） | — | — | — |

5 个 workflow skill 全部真实执行（§49）：`create-new-story-blueprint`、
`review-and-repair-blueprint`、`prepare-final-delivery`、`operate-with-agent`、
`use-novelforge-through-mcp`。

## 3. 分领域实测要点

### 3.1 Project / Studio

```text
POST /novels（NF_SKILL_DOGFOOD_401）      → 201，profile 可读，novel_id 稳定
POST /novels（重复）                      → 409 PROFILE_EXISTS
PATCH /novels/{id} {"title": "…"}         → 200；title 变，genre / created_at 不变
PATCH /novels/{id} {"title": "   "}       → 422
GET /                                     → 200（ui/dist 正常服务）
tests/browser_v4_studio_golden.cjs        → PASS（真实 Edge + stub：generate → 下载 md/docx/nfpack）
```

### 3.2 Blueprint / Generation（9 个 atomic 全跑）

```text
premise → theme → world → character×2 → character_arc×2 → story_arc →
act_01 → ch_001 → sc_001_01
每一步都验证：node 存在 / revision 存在 / novel_id 一致 / node_type 正确 / status=proposed
idempotency replay（同 key）              → 返回同一 revision + warnings=[IDEMPOTENT_REPLAY]
regenerate（带 node_id + expected_revision）→ r2（不新增节点）
stale expected_revision                   → 409 REVISION_CONFLICT（0 model call）
```

**关键发现（新，未在 GAP 文档里）**：`POST /studio/generate` 给单例类型
（`theme` / `world` / `story_arc`）传 `parent_id` 时，生成节点 `sequence=0`。
Q0 把"非根节点 sequence=0"判为 `SEQUENCE_INVALID`（major，`repairable=false`），
而且之后对同一父节点再生成可能直接 422 `BLUEPRINT_VALIDATION_FAILED`。
对照实验（控制组 `NF_DOGFOOD_PROBE`）：

```text
premise + world(parent='') + story_arc(parent='')  → 无 SEQUENCE_INVALID
world 改为 parent=premise                          → 立刻出现 SEQUENCE_INVALID
```

官方 fixture（`studio_clean`）刻意把 theme/world/character/story_arc 都挂在根，
所以这条路径从没被门禁覆盖；而 skill 的 REST 示例写的正是 `parent_id:"premise"`。

### 3.3 Quality / Repair

```text
POST /studio/quality/evaluate        → report + gates(Q0–Q9) + issues（code/gate/severity/
                                       scope/evidence/repairable/repair_contract）
POST /studio/quality/repair(dry)     → planned，0 mutation，含 allow_change / preserve /
                                       blast_radius / estimated_model_calls
POST /studio/quality/repair(apply)   → applied，2 次模型调用，ch_001 r5→r6 / ch_002 r1→r2
POST /studio/quality/verify          → partial（resolved=[]），没有谎报 resolved
```

### 3.4 Editor

```text
patch dry_run            → 0 mutation，changed_fields 精确
patch 受保护字段         → protected_fields 含 sequence / status / node_id（无法用来修 3.2 的 sequence）
rewrite（改 hook 却动了 turn）→ 409 EDITOR_PRESERVE_VIOLATION，未写入任何 revision：ONLY_TARGET_FIELDS_CHANGE 实测成立
restore r1（当前 r2）    → r3，diff(r1→r3) 空：RESTORE_CREATES_NEW_REVISION 实测成立
accept r4                → reviewed=4, revision=5, node.status=accepted
再次 accept 同一 revision → 422 EDITOR_OPERATION_REJECTED（文档说 idempotent=true）
reject theme r2          → decision=rejected，revision 不变，status 仍 proposed
```

### 3.5 Delivery

```text
默认 policy preflight    → blocked（DELIVERY_NO_ACCEPTED_REVISION / QUALITY_STALE /
                           MISSING_REQUIRED_NODE / ORPHAN / REFERENCE_BROKEN）
放宽 policy 后 preflight → 仍被 DELIVERY_Q9_BLOCKER / DELIVERY_REJECTED_REVISION /
                           DELIVERY_PLACEHOLDER_CONTENT 拦住（这三类不被 policy 放宽）
explicit_revisions 交付  → delivered，snapshot DS_d349f70e5e25，4 个格式
manifest                  → selected_revisions 与请求一致；checksum/size/mime 齐全
download（4 个）          → bytes == manifest.size，sha256 == manifest.checksum，Content-Disposition 正确
markdown 内容扫描          → 不含 node_id / status / provenance / quality_status / parent_id
负路径                    → `../` 404、跨作品 409、未登记路径 409
同 idempotency_key 重放   → 同一 snapshot，idempotent=true
```

### 3.6 Canon / Memory / StoryState

```text
GET /canon/{facts,events,entities,knowledge,foreshadows} → 200（空 Canon 返回空列表，不报错）
GET /canon/graph        → node_count/edge_count
GET /canon/validate     → ok=true, findings=[], promotion_conflicts=[]
POST /canon/validate-outline?novel_id=… → ok=false + CHAPTER_SCHEMA_INVALID（示例 payload 缺必填）
POST /canon/rebuild?novel_id=…          → report（fact/event/knowledge/foreshadow coverage）
MemoryService.search + ContextBuilder.build → 0 items（该书无 Canon/StoryState，属预期）；digest 可复现
resolve_novel_context → StoryState（timeline.current_time / characters / resources …）
```

### 3.7 Plugins / Agent / MCP / AI

```text
GET /studio/plugins        → available=true, trust_model=trusted_in_process, read_only=true, 8 permissions
Application approve/enable → status=approved → active，注册 `plugin.com.example.exporter.text-list`
Application disable        → status=disabled，registered_ids=[]，contributions(type) 清空（Core 4 格式不受影响）
agent plan                 → 5 步、mutations=0、allow_auto_accept=false、allow_delivery=false
agent start                → completed（repair 步骤因 issue_ids 为空被 skipped）
agent approve（protected） → ok=false, status=failed, AGENT_STEP_FAILED（见 §8）
agent reject（protected）  → status=paused, stop_reason="approval rejected"（正常）
mcp in-process             → 23 tools / 13 resources（与 catalog 一致）；11 个 resource 读取成功；
                             generate_world / patch / evaluate / plan_repair / validate_delivery / diff 全部返回 envelope
mcp stdio                  → 启动即崩（见 §8）
ai（无 provider）          → 422 GENERATION_UNAVAILABLE + 0 mutation；只读路径不受影响
```

## 4. Skill 可用性与发现性

详见 `docs/v4/V4_0_1_SKILL_USABILITY_MATRIX.md`（77 行逐 skill 结论 + 发现性测试）。

```text
skills reviewed    77 / 77
executed           63
simulated          9（Application 直调 / legacy gate / 只读边界类）
review-only        2
blocked            3（mcp.start-mcp-server、agent.approve-agent-run、跨 A/L/K 的 workflow 部分）
```

发现性：`SKILL_CATALOG → module README → SKILL.md` 通常 1–2 跳即可定位；
唯一真实歧义是 **Canon 相关目标**（"检查 Canon 冲突"可能指
`canon.validate-canon-integrity`（Canon 自洽）或 `quality.evaluate-blueprint` 的 Q2
（蓝图↔Canon 对照）），catalog 与 DEPENDENCY_MAP 都没有分流说明。

## 5. Source escape（`SOURCE_ESCAPE_COUNT = 4`）

```text
1 src/novelforge/blueprint/contracts.py      ← CharacterArcPayload 必填字段（skill 没写，
                                                两次 422 schema 失败后被迫读源码）
2 src/novelforge/delivery/validation.py      ← 解释为什么"已 resolved 的 Q9 issue"仍阻塞
                                                preflight（preflight 阻塞后被迫读源码）
3 src/novelforge/interfaces/mcp/server.py    ← 解释 stdio 入口崩溃（stack trace 指向此处）
4 `rg NOVELFORGE_PROJECT_ROOT src`           ← skill 只写了 MCP 的 root 机制；REST/UI 侧
                                                如何指定隔离根没有任何文档，必须查源码
```

`tests/browser_v4_11_agent.cjs`、`scripts/studio_ui_test_server.py` 的阅读不计入
source escape（前者由 skill 的 Verification 明确引用，后者是 skill 指出的 stub 服务）。

## 6. Manual guess（`MANUAL_GUESS_COUNT = 5`）

```text
1 theme payload 字段（猜 → 422 schema 失败 → 再修）
2 character_arc payload 字段（猜 → 422 → 读 contract 才补齐 character_id）
3 以为 manifest 响应嵌在 `manifest` 字段下（实际是顶层）
4 explicit_revisions 的参数形状（node_id → revision 映射，猜对了但无文档示例）
5 MCP initialize 的 protocolVersion 字符串（猜 "2025-06-18" 才握手）
   （附：reject body 里多带 session_id → 422 extra_forbidden；skill 里的写法才是对的）
```

## 7. Skill defects（`SKILL_DEFECT`）——已修复

本任务允许改 `skills/**` / `docs/**` / `tests/v4/skills/**`，因此按
`SKILL_BASELINE_UPDATE` 流程修复并重建哈希（原因：dogfood 实测与文档不一致，
会直接让新操作者失败或误判；不改任何 runtime 语义）。

| # | Skill | 缺陷 | 修复 |
| --- | --- | --- | --- |
| D1 | `generation.generate-character-arc` | 未写 contract 必填 `character_id` | Procedure + Common failures 补说明 |
| D2 | `generation.generate-structural-unit` | node_id 形式写错（`unit_<type>_<i>`） | 改为 `<unit_type>_<NN>`（`act_01`） |
| D3 | `generation.generate-chapter-plan` | 示例父 id `unit_act_1` 不存在 | 改为 `act_01` |
| D4 | `generation.generate-scene-plan` | 示例 `sc_007_2` 与补零规则 | 改为 `sc_007_02` |
| D5 | `generation/README.md` | 未说明 `GENERATION_UNAVAILABLE` 被复用、sequence 陷阱 | 增加"实测补充"段 |
| D6 | `canon.validate-planning-against-canon` | `novel_id` 位置错；chapter schema 未写 | query 参数 + `chapter_uuid`/≥3 `concrete_events` |
| D7 | `canon.rebuild-canon` | `novel_id` 位置错 | query 参数 |
| D8 | `memory.inspect-derived-memory` | `MemoryQuery(text=…)` 不存在 | 改为 task/entities/locations/source_types |
| D9 | `editor.accept-revision` | 重复 accept 的幂等描述错 | 改为 422 `EDITOR_OPERATION_REJECTED` |
| D10 | `quality.inspect-quality-report` | `summary.open_blockers` 不存在；blockers 口径 | 写实测字段 + 以 issues[] 为准 |
| D11 | `delivery.validate-delivery` | 顶层 `excluded[]` 不存在；policy 放宽语义 | 写实际字段 + 不可放宽的 blocker 清单 |
| D12 | `agent.plan-agent-goal` | 字段名 / status | `requires_approval`、`status=planning` |
| D13 | `agent.start-agent-session` | 响应字段不存在；repair 可能 skipped | 写实测字段 |
| D14 | `agent.inspect-agent-session` | 响应形状（嵌套） | 写 `{session,runs,checkpoint,pending_approvals,audit}` |
| D15 | `agent.approve-agent-run` | 未警告 approve 当前会失败 | 加显式警告 + reject 对照 |
| D16 | `mcp.start-mcp-server` | 未写 `PYTHONPATH=src`；未警告 stdio 崩溃 | 加前置与 in-process 兜底 |
| D17 | `studio.open-story-studio` | 写了不存在的 `--root` | 改说明 + 指向 test server |
| D18 | `plugins.inspect-plugin-contributions` | 未区分"声明"与"已注册" | 加失败表一行 |

Skill baseline：`python scripts/validate_v4_0_1_skills.py --write-manifest`
（`SKILL_MANIFEST.json` 重建为 98 个文件哈希），随后 validator PASS。

## 8. Product bugs（`PRODUCT_BUG`，本任务不修 runtime）

### PB-1（P0）Delivery preflight 不按 issue status 过滤 → 已修好的问题永久阻塞交付

```text
复现：ch_002 缺场景 → Q9 blocker DELIVERY_MISSING_CHAPTER_OR_SCENE 入库
      → 生成 sc_002_01（问题已不存在）→ 重新 evaluate（Q9 passed, issue_count=0）
      → preflight 仍报 "Q9 交付就绪度问题：DELIVERY_MISSING_CHAPTER_OR_SCENE"
      → POST /studio/quality/verify 把该 issue 标为 resolved → preflight 依旧报同一条
根因：src/novelforge/delivery/validation.py::_q9_issues / _placeholder_issues
      遍历 quality_store.list_issues() 时只按 gate / severity / code 过滤，**从不检查
      issue.status**，也不检查该 issue 是否仍在最新 report 里。
影响：凡是历史上出现过 Q9 blocker 或 placeholder（HOLLOW_NODE 等）节点，该作品
      就再也无法通过默认 policy 交付；官方 happy-path 门禁覆盖不到（fixture 不产生这类 issue）。
绕过：当前只有把受影响节点排除（explicit_revisions）或换新作品。
```

### PB-2（P0）Agent protected step 批准后必然失败

```text
复现：plan（goal 含"接受…交付"）→ step2 request_accept(requires_approval) →
      start → awaiting_approval + approval_id →
      POST /agent/{sid}/approve {approval_id} →
      ok=false, status=failed, error_code=AGENT_STEP_FAILED,
      stop_reason="验证未通过：approval_recorded"，
      该步 result_refs.approval_id=""（批准已被 consume，checkpoint 又重跑该步）
对照：同一 session 的 reject 路径正常（status=paused, stop_reason="approval rejected"）
影响：官方 browser_v4_11_agent.cjs 的计划从不进入 approval 分支（实测 approvals=0、
      session completed），所以门禁 PASS 但审批路径其实没被覆盖。
```

### PB-3（P0）MCP stdio 入口无法启动

```text
复现：PYTHONPATH=<repo>\src; $env:NOVELFORGE_PROJECT_ROOT=<root>;
      python -m novelforge.interfaces.mcp
结果：AttributeError: 'NoneType' object has no attribute 'resources_changed'
      （src/novelforge/interfaces/mcp/server.py::run_stdio → Server.get_capabilities(
        notification_options=None, …)；mcp 1.9.4 要求 NotificationOptions 实例）
环境：mcp==1.9.4，落在 requirements.txt 的 mcp>=1.9,<2 区间内
影响：skill 首推的 stdio 接入方式在本版本不可用；只能退到 in-process dispatcher
```

### PB-4（P1）Q0 `SEQUENCE_INVALID`：单例节点挂父节点即非法

```text
复现：POST /studio/generate {task:"world", parent_id:"premise"} → 200，node.sequence=0
      → evaluate → Q0 SEQUENCE_INVALID（major, repairable=false，scope=premise）
      → 之后再对同一父节点生成 → 422 BLUEPRINT_VALIDATION_FAILED
对照：parent 留空（根节点）则完全没有该 issue
影响：skill 的 REST 示例正是 parent_id:"premise"；照做的新操作者会拿到一个
      patch / repair 都改不了（sequence 属 protected）的 major issue。
```

### PB-5（P2）Q9 gate 行的 blockers 计数与 issues 不一致

```text
实测：GET /studio/quality → Q9 {status:"blocked", issues:1, blockers:0}
      同时 issues[] 里有 severity="blocker" 且 status="open" 的 Q9 issue
影响：只看 gate 行会以为"有 blocker 但计数为 0"，与 skill 的 Verification
      （summary.open_blockers 与 gate blockers 口径一致）同时冲突
```

### PB-6（P3）MCP envelope：`ok=false` 但 `errors=[]`

```text
实测：evaluate_blueprint（report.status=failed）与 validate_delivery（preflight blocked）
      都返回 ok=false + errors=[]；真实原因只在 result 里
影响：按 skill 的 "ok=false → 读 errors[].code" 操作会读到空数组
```

## 9. Product gaps（`PRODUCT_GAP`）——已知 8 项 + 新增 4 项

### 9.1 GAP-001 … GAP-008 实测观察

| Gap | 实测结论 | 影响程度 |
| --- | --- | --- |
| GAP-001 `/studio/generate` dry_run 未实现 | **确认**：`dry_run:true` 仍把 theme 从 r1 推到 r2 | 中：skill 已明确警告，新操作者不会被误导 → 记录，不阻塞 |
| GAP-002 `build_links` 无对外入口 | **确认且影响 Q5/Q7/Q9**：场景 `setup=[] / payoff=[]` → Q5 `ORPHAN_EVENT`（evidence 直说"没有 setup / payoff"）、Q7 `CLIMAX_UNPREPARED`（major）；只有 premise+arc+章的作品还会 Q9 直接 `blocked` | 高：正式接口内无法补齐因果链，只能手写 patch |
| GAP-003 Canon 无 Application facade / MCP | **确认但可承受**：5 个 REST 端点可用且结构清晰；`validate-outline` / `rebuild` 的 `novel_id` 位置与 skill 不符（skill 已修） | 低-中：Canon 是唯一"REST 直连模块"，MCP 客户端够不到 Canon |
| GAP-004 Memory 无产品接口 | **确认**：Python API 可用（`MemoryService` / `ContextBuilder`）；没有 UI/REST 就无法回答"某次生成读了哪些 memory" | 中：可解释性缺口，不阻塞创作链 |
| GAP-005 Plugin 生命周期 Application-only | **确认且 Skill 足够**：approve/enable/disable 用 Application 直调全部成功；REST/MCP = N/A 已写明；只读 REST 与 trust_model 文案一致 | 低：operator 边界清晰（有意 DEFER） |
| GAP-006 Editor advanced ops 未 wired | **确认，本次未受阻**：`patch_batch` / `move` / `undo` / `change_impact` / `evaluate_and_repair` 均无 wire 入口，但 patch/rewrite/restore + repair loop 足以完成全部编辑 | 低：按需再开 |
| GAP-007 Delivery `explicit_revisions` / `include_node_types` UI 无入口 | **确认且实际关键**：本次交付正是因为 PB-1，只能靠 REST `explicit_revisions` 才成功；UI 用户遇到同样情况会完全卡死 | 高：建议与 PB-1 同批处理，或先补 UI 高级选项 |
| GAP-008 StoryState 无产品级入口 | **确认，只读足够**：`resolve_novel_context` 可读出 state；V4 生成不写 StoryState，符合 `PLANNING != OCCURRED TRUTH` | 低：保持只读 |

### 9.2 Dogfood 新发现

```text
GAP-009  REST/UI 服务无法指定隔离 project root
         start_novelforge_ui.py 无 --root；只有浏览器门禁的 test server 支持 --root，
         而 skill 曾写成 --root 可传（已修）。新操作者想在不碰作者数据的前提下演练，
         只能自己拼 composition。

GAP-010  quality issue 生命周期没有"随最新报告自动关闭"的语义
         /studio/quality 的 gate 过滤视图会把历史 issue（含已 resolved 的）继续列出，
         与 skill 的 "report 与 issue 列表一致" 期望冲突（PB-1 / PB-5 的共同背景）。

GAP-011  `GENERATION_UNAVAILABLE` 一个 code 同时表示"无 provider"和"结构化输出不合法"
         message 不同、code 相同；调用方无法程序化区分（skill 已补充说明）。

GAP-012  create-delivery-snapshot 与 deliver-blueprint 共用 POST /delivery
         行为差异只由参数决定；skill 写清了，但 catalog 层面看不出"快照"与"交付"同端点。
```

## 10. V4.0.2 candidate backlog（仅候选，本任务不改 runtime）

| 优先级 | 项 | 依据 | 处理建议 |
| --- | --- | --- | --- |
| **P0** | 修 PB-1：delivery preflight 按 issue status / 最新 report 过滤 | 已修好的问题永久阻塞交付，官方 happy-path 覆盖不到 | `_q9_issues` / `_placeholder_issues` 增加 status（仅 open 才计）与 latest-report 交集；补"修好→重评→可交付"回归测试 |
| **P0** | 修 PB-2：Agent approval 后不得失败 | 审批是 Agent 唯一人工闸门，坏了等于 Agent 不可托管 | 修 approval consume / checkpoint 重跑顺序；把 approval 分支纳入 `browser_v4_11_agent.cjs`（断言 approvals ≥ 1 且最终 completed） |
| **P0** | 修 PB-3：MCP stdio 入口 | 首推接入方式直接崩溃 | `run_stdio` 传 `NotificationOptions(...)`；补 stdio 握手测试（当前测试只覆盖 dispatcher） |
| **P1** | 修 PB-4：单例节点 sequence 赋值 | 会让 Q0 major 且 `repairable=false` | 给 theme/world/story_arc 分配唯一 sequence，或把根节点语义写进 Q0 规则 |
| **P1** | GAP-009：隔离 root 一等公民 | 没有它就无法在不碰作者数据的前提下演练 / 验收 | 给 `start_novelforge_ui.py --root`，或把 test server 提升为正式"演练模式" |
| **P1** | GAP-002：links 对外入口 | Q5/Q7/Q9 直接受影响 | 把 `build_links` 暴露为显式确定性动作（REST + MCP，无 LLM） |
| **P2** | PB-5：gate blockers 计数 | 门禁可见性 | 统一为"该 gate 内 blocker 严重度 issue 数" |
| **P2** | GAP-007：交付高级选择 UI | 结合 PB-1 会成为唯一绕路 | Studio 交付页增加 explicit_revisions / include_node_types 高级选项 |
| **P2** | GAP-003 / GAP-004 | 可解释性与机器接口一致性 | 补 `application/services/canon.py`；memory 只读 summary resource（带预算参数） |
| **P2** | PB-6：envelope 语义 | 客户端错误处理 | `ok=false` 必须有 errors[]，或文档明确"业务失败不产生 errors" |
| **P3** | GAP-006 / GAP-008 | 本次未受阻 | 保持 DEFER，按真实需求逐个开 |
| **P3** | GAP-010 / GAP-011 / GAP-012 | 认知成本 | 产品侧统一 code 语义与 issue 生命周期；文档层已缓解 |
| **P3** | Catalog 发现性：Canon 目标歧义 | §4 发现性测试 | 在 `SKILL_CATALOG.md` / `DEPENDENCY_MAP.md` 加一句 Q2 vs `canon.validate` 的分流说明 |

## 11. 验收与验证记录（§59–§61）

```text
Skill validator     python scripts/validate_v4_0_1_skills.py            → PASS
                    （77 skills / 16 modules / 23 MCP tools / 13 MCP resources）
Skill baseline      --write-manifest 重建（98 files）+ 显式 SKILL_BASELINE_UPDATE 原因
Targeted tests      python -m pytest -q tests/v4/skills                 → PASS
Acceptance          python -m pytest -q tests/acceptance                → PASS
Isolation           python -m pytest -q tests/v4/isolation              → PASS
Product diff gate   git diff 4cf4d1a..HEAD -- src ui novel              → 空
Browser（真实 Edge）browser_v4_studio_golden.cjs / browser_v4_11_agent.cjs → PASS
Full suite          python -m pytest -q                                 → PASS
```

## 12. Test novel 清理（§58）

```text
DELETE /novels/NF_SKILL_DOGFOOD_401?confirm=true&reason=dogfood cleanup
  → archive_dir（workspace/archived_novels/NF_SKILL_DOGFOOD_401_<UTC>/）+ ARCHIVE_MANIFEST.json
  → GET /novels 不再包含该 id；原作用域目录不再残留
探针作品 NF_DOGFOOD_PROBE / NF_NOPROVIDER_PROBE 同样按 skill 的归档流程清理。
未直接删目录（遵守 §58）。
```

## 13. PASS 标准对照（§65）

| PASS 条件 | 实测 | 结论 |
| --- | --- | --- |
| all 5 workflow skills actually exercised | 5/5 执行（2 个被产品缺陷部分阻塞） | ✅ |
| all 77 skills reviewed | 77/77（矩阵） | ✅ |
| core atomic skills successfully exercised | 63 executed / 9 simulated / 2 review-only | ✅ |
| no unsupported V2/V3 behavior required | 未使用任何 retired 能力 | ✅ |
| Skill instructions match actual interfaces | 起点**不匹配**（24 个文件错/缺）；修复后 validator PASS | ✅（修复后） |
| new Codex can complete core workflows without reverse-engineering `src/**` | **否**：4 次 source escape；Delivery / Agent / MCP 核心路径被产品缺陷阻塞 | ❌ |
| all discovered product limitations honestly recorded as gaps | 是（§8 / §9） | ✅ |
| product code unchanged | `src/ui/novel` diff 为空 | ✅ |

→ 最终判定：**BLOCKED**。不是 skill 不够，而是 PB-1 / PB-2 / PB-3 属产品级阻塞：
按 §67，Delivery 与 Agent 两个核心 workflow 无法只靠正式接口完整走完，
必须作为 V4.0.2 的 P0 候选处理。

## 14. 提交与改动清单

```text
branch      v4-401-skill-dogfood
commits     见 git log（test(skills) / docs(skills) / docs(v4) 三段式）
files       skills/novelforge-v4.0.1/**（18 个 SKILL/README + SKILL_MANIFEST.json）
            docs/v4/V4_0_1_SKILL_DOGFOOD_REPORT.md（本文件）
            docs/v4/V4_0_1_SKILL_USABILITY_MATRIX.md
            tests/v4/skills/dogfood_401_stub_server.py（dogfood 专用确定性 stub fixture）
            tests/v4/skills/test_dogfood_skill_findings.py（把本次修复的接口事实固化成守卫）
product     src/ ui/ novel/ 未改动
```

## 15. 本轮未能覆盖的部分（诚实声明）

```text
· 未使用真实 LLM provider（§10 禁止真实付费调用）：GAP-001 / GAP-004 的真实模型侧影响
  只能在启用 provider 后复验。
· repair 的"真正修好"没被验证：stub 返回确定性内容，verifier 报 partial 属预期；
  也正因为它没有谎报 resolved，才判 PASS。
· StoryState 只做只读检查（§28 禁止写）。
· 未在作者真实作品上做任何 mutation（§9）。
```
