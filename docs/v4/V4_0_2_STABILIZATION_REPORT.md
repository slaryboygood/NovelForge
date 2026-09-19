# NovelForge V4.0.2 — P0 Stabilization & Dogfood Closure Report

> 阶段：**V4.0.2 STABILIZATION（bugfix only，无新功能）**。
> 本报告不覆盖历史：V4.0.1 的 dogfood 结果保留在 `docs/v4/V4_0_1_SKILL_DOGFOOD_REPORT.md`（历史判定 `BLOCKED` 不改写）。
> 本文件记录这轮 P0 修复的复现、根因、修复、回归与 closure。

## 0. 结果摘要

```text
DOGFOOD P0 CLOSURE = PASS

PB-1 Delivery preflight historical issue bug   → CLOSED
PB-2 Agent approval execution bug              → CLOSED
PB-3 MCP stdio startup bug                     → CLOSED

被阻塞的三个 workflow 全部走通（只用正式产品接口，无 workaround）：
  workflow.prepare-final-delivery       PASS（默认/严格 preflight）
  workflow.operate-with-agent           PASS（protected approval 闭环）
  workflow.use-novelforge-through-mcp   PASS（真实 stdio subprocess 握手）

产品性质：bugfix（无新增 major capability）；候选版本号 v4.0.2。
本报告完成后未 merge main / 未更新 v4 / 未创建 tag / 未发布。
```

## 1. 基线与分支

```text
Starting HEAD            fa3d748e5b0c4d2a33b91abe7a9ba1915ea4af31
                         （dogfood 最终 HEAD，branch v4-401-skill-dogfood，working tree clean）
Integration branch       v4-402-stabilization
Task branches（已 FF 合并并删除）
  v4-402-pb1-delivery        → fix(delivery) 395482d
  v4-402-pb2-agent-approval  → fix(agent)    ce892b4
  v4-402-pb3-mcp-stdio       → fix(mcp)      fd40c77
Frozen tags              未移动（novelforge-product-v3-final / novelforge-product-v4-final / v4.0.0 / v4.0.1）
```

## 2. P0 Closure Table（§62）

| Bug | Reproduction | Root Cause | Fix | Regression | Status |
| --- | --- | --- | --- | --- | --- |
| **PB-1** Delivery | 缺陷 → evaluate（Q9/Q8 blocker）→ 修好 → 重新 evaluate（passed）→ verify(resolved) → 默认 preflight 仍 blocked（只能靠 explicit_revisions 绕过） | `delivery/validation.py::_q9_issues` / `_placeholder_issues` 只按 gate/severity/code/scope 过滤 `quality_store.list_issues()`，**不看 issue.status**，也不看该 issue 是否仍在最新报告里；`delivery/selection.py::_quality_state` 同样把已 resolved 的 issue 算作 `blocking_codes` | Quality Store 新增 `latest_coverage()` / `live_issues()`（issue 生命周期唯一 owner：status ∈ {open, repairing} ∧ 仍在最新覆盖报告里 ∧ revision 匹配）；delivery 三处消费点改用它 | `tests/delivery/test_delivery_historical_quality.py`（4）、`tests/quality/test_quality_issue_lifecycle.py`（6） | **CLOSED** |
| **PB-2** Agent approval | plan（含「接受」）→ start → awaiting_approval → approve → `status=failed`、`AGENT_STEP_FAILED`、`stop_reason="验证未通过：approval_recorded"`、`result_refs.approval_id=""` | ① 批准证据在验证前丢失（`request_accept` 的 dispatch 返回空 `approval_id`，而它的 success_criteria 就是 `approval_recorded`）；② approve 后从 sequence 0 重跑而非从 checkpoint 继续；③ `ApplicationEditorPort.patch/rewrite/accept/reject` 对返回 dict 的 EditorService 结果调用 `.as_dict()` → `AttributeError`（所有 editor 类 Agent 步骤都会失败） | ① `AgentSessionRecord.approved_step_approvals()`（step_id → approval_id）+ executor 把批准证据写进结果 / result_refs；② approve / resume 从 checkpoint 继续；③ port 用 `_outcome_payload()` 归一化 dict / dataclass | `tests/agent/test_agent_approval_lifecycle.py`（6）、`tests/browser_v4_11_agent.cjs`（真实 protected approval，approvals >= 1） | **CLOSED** |
| **PB-3** MCP stdio | `PYTHONPATH=src NOVELFORGE_PROJECT_ROOT=<root> python -m novelforge.interfaces.mcp`（mcp 1.9.4）→ `AttributeError: 'NoneType' object has no attribute 'resources_changed'` | `interfaces/mcp/server.py::run_stdio` 把 `notification_options=None` 传给 `Server.get_capabilities`，而 mcp 1.9.x 的签名要求 `NotificationOptions` 实例 | import `NotificationOptions` 并在 `get_capabilities` 传实例（三个 listChanged 都 False：本 server 不推送通知）；SDK 缺该符号时给显式 `MCPSdkUnavailable` | `tests/mcp/test_mcp_stdio_entrypoint.py`（真实 subprocess 握手，2） | **CLOSED** |

## 3. PB-1 详情（preflight 绑定当前真相）

### 复现（修复前，官方 fixture + 公开 API）

```text
场景卡植入占位内容（patch scene_purpose="TODO…"）→ accept
→ POST /studio/quality/evaluate  → failed（DELIVERY_PLACEHOLDER / BLUEPRINT_PLACEHOLDER_TEXT）
→ POST /delivery {dry_run:true}  → blocked
  codes = [DELIVERY_PLACEHOLDER_CONTENT, DELIVERY_Q9_BLOCKER, DELIVERY_QUALITY_FAILED]
改回内容 → accept → evaluate（passed, issues=0）→ POST /studio/quality/verify（resolved=2）
→ POST /delivery {dry_run:true}  → 修复前仍然 blocked
```

### 语义（修复后）

```text
Delivery preflight 回答的是"当前要交付的 Blueprint 现在是否仍有阻塞问题"，
而不是"这个作品历史上是否出现过阻塞问题"。

live issue = status ∈ {open, repairing}
             ∧ 仍出现在最新一份覆盖其 scope 节点的质量报告里
             ∧ （按被选 revision）该报告评估的正是这个 revision
```

### 修改

```text
src/novelforge/quality/store.py       latest_coverage() / live_issues()（唯一 owner）
src/novelforge/delivery/selection.py  _quality_state 改用 live_issues
src/novelforge/delivery/validation.py _q9_issues / _placeholder_issues 改用 live_issues（evidence 附 live_report_id）
```

Quality 侧改动是本修复的最小依赖：issue 生命周期判定必须只有一个 owner，否则 delivery 会形成第二套 truth（AGENTS.md §5 / §6）。

### 回归（先复现后修复）

```text
tests/delivery/test_delivery_historical_quality.py
  · 缺陷仍在（最新报告包含它）→ 默认 preflight 必须 blocked（真实 blocker 仍拦截）
  · 修好 + 重新 evaluate + verify(resolved) → 默认 preflight PASS（PB-1 主复现）
  · 仅靠新报告取代（不依赖 verify）→ 也必须解除阻塞
  · 放宽 policy（relaxed）→ 不能放过当前仍存在的占位内容
tests/quality/test_quality_issue_lifecycle.py
  · live_issues / latest_coverage 语义：resolved 不算 live；被新报告取代不算 live；revision 过滤；gate / code 过滤
```

## 4. PB-2 详情（approval 必须是 durable evidence）

### 复现（修复前）

```text
plan("…接受结果") → 计划含 request_accept / accept_revision（均 protected）
start   → awaiting_approval + approval_id
approve → ok=false, status=failed, error_code=AGENT_STEP_FAILED,
          stop_reason="验证未通过：approval_recorded"；该步 result_refs.approval_id=""
reject  → status=paused（正常，与 dogfood 一致）
```

### 根因（3 个，同属一条 protected-approval 生命周期）

```text
R1 批准证据丢失：request_accept 的 dispatch 返回 {"approval_id": ""}，而该 step 的 success_criteria 正是 approval_recorded → 永远不可能成立。
R2 批准后重放：approve 走 _execute(fresh_run=False) 但 start_sequence=0 / completed=()，已完成的步骤被重新执行（checkpoint 没有被使用）。
R3 Agent 的 EditorPort 对所有 EditorService 结果调用 .as_dict()，而 patch / rewrite / accept / reject 返回普通 dict → AttributeError → AGENT_STEP_FAILED（accept_revision 等 editor 步骤从未真正跑通过）。
   说明：R3 在 dogfood 中没有单独上报，但属于同一个"审批后执行必定失败"的缺陷面；既有 tests/agent/test_agent_approval.py 的断言过宽（status 允许 "failed"），所以门禁没有发现它。
```

### 修改

```text
src/novelforge/agent/session.py        approved_step_approvals() → step_id → approval_id
src/novelforge/agent/executor.py       execute(..., approval_ids=…)：批准证据进入 request_accept 结果 + 所有 approved step 的 result_refs
src/novelforge/application/services/agent.py
                                       · approve 后从 checkpoint 继续（start_sequence / completed_steps / run_id）
                                       · resume 同样携带 approval_ids
                                       · _outcome_payload() 归一化 dict / dataclass 结果
```

安全边界未放宽：wrong / stale approval 仍被拒绝；approve 只授权该步；Agent 仍不自动接受、不自动交付。

### 回归

```text
tests/agent/test_agent_approval_lifecycle.py（6）
  · approve 之后 protected step completed，且 result_refs.approval_id == 被批准的 id
  · 完整链条：request_accept → accept_revision → completed，目标节点 accepted
  · 批准不重放已完成步骤（审计里每个 step_id 只执行一次）
  · 未知 approval_id → 报错且 session 仍在 awaiting_approval
  · 重复 approve 同一个 id 安全（不绕过闸门、不重复 mutation）
  · reject 不执行 protected step
tests/browser_v4_11_agent.cjs（真实 Edge）
  · 阶段 1（"不要自动接受"）→ approvals=0，completed
  · 阶段 2（"接受…"）→ 真实 protected approval：approvals >= 1 → completed，且 0 error
  · 新增 driveAgent：处理 bounded batch 的 paused → 继续执行（避免把"暂停"误判为失败）
```

## 5. PB-3 详情（stdio 入口在支持区间内可用）

### 复现（修复前）

```text
PYTHONPATH=src; NOVELFORGE_PROJECT_ROOT=<root>; python -m novelforge.interfaces.mcp
  → server.py:156 get_capabilities(notification_options=None …)
    AttributeError: 'NoneType' object has no attribute 'resources_changed'
环境：mcp==1.9.4（requirements.txt: mcp>=1.9,<2，属正式支持区间）
```

### 修复（最小、无重写）

```text
· 在 SDK 守卫 import 中引入 mcp.server.lowlevel.NotificationOptions
· run_stdio: get_capabilities(notification_options=NotificationOptions(), …)：prompts / resources / tools 的 listChanged 全部 false
· SDK 缺该符号时抛显式 MCPSdkUnavailable（而不是运行期 AttributeError）
· requirements.txt 不变（仍 mcp>=1.9,<2）：API 依据来自本地安装的包签名，不是记忆
```

### 回归与实测

```text
tests/mcp/test_mcp_stdio_entrypoint.py（新，2 tests）
  · 以正式 entrypoint 起子进程，按换行分隔 JSON-RPC 走：
    initialize → notifications/initialized → tools/list（23）→ resources/list（1 static）
    → resources/templates/list（12）→ resources/read novelforge://interface
    → 关闭 stdin → 退出码 0
  · 第二个测试守卫：initialize 之后进程不应自行退出（崩溃必须体现在 stderr）
手工冒烟（正式入口）：initialize → server=novelforge v1、capabilities.tools/resources 存在；tools/list → 23；退出码 0
MCP 表面不变：23 tools / 13 resources（1 static + 12 template）
```

## 6. 被阻塞 workflow 的 closure（§43–§46、§59）

三个 workflow 都在隔离测试根 + stub 模型（0 真实模型调用）上，只用公开接口重跑。

### 6.1 workflow.prepare-final-delivery（默认/严格路径）

```text
1 scene sc_001_04 r3
2 defect accepted -> r5
3 evaluate -> failed issues=2
4 preflight with LIVE defect -> ok=False
  codes=[DELIVERY_PLACEHOLDER_CONTENT, DELIVERY_Q9_BLOCKER, DELIVERY_QUALITY_FAILED]
5 fixed + accepted -> r7; re-evaluate -> passed issues=0
6 verify -> resolved resolved=2
7 default preflight AFTER fix -> ok=True codes=[]        ← PB-1 closure（无 explicit_revisions）
8 deliver -> delivered snapshot=DS_97505c467619 formats=['docx','markdown','nfpack']
9 manifest -> artifacts=3 first=markdown size=5557 checksum=f422cd6406d8…
```

浏览器真实下载（`browser_v4_studio_golden.cjs`，真实 Edge）：

```text
[download] markdown: blueprint.md (5557 bytes)
[download] docx: blueprint.docx (3845 bytes)
[download] nfpack: novelforge-package.nfpack (20702 bytes)
V4-10 Story Studio browser gate: PASS
```

### 6.2 workflow.operate-with-agent（protected approval）

```text
1 plan -> steps=3 protected=['request_accept','accept_revision']
2 start -> awaiting_approval
3.1 approve request_accept -> status=awaiting_approval（下一步需要单独批准），errors=[AGENT_APPROVAL_REQUIRED: accept_revision]
3.2 approve accept_revision -> status=completed errors=[]
4 session -> completed approvals=2 decisions=2
5 accepted scenes = ['sc_001_01','sc_001_02','sc_001_03','sc_001_04']
```

### 6.3 workflow.use-novelforge-through-mcp（真实 stdio + 真实数据）

```text
1 initialize -> novelforge v1
2 surface -> 23 tools / 12 resource templates
3 read novelforge://novels/studio_clean -> novel_id=studio_clean
4 read .../blueprint -> count=16 items=16 has_more=False（分页 envelope）
5 tools/call validate_delivery -> envelope ok=true read_only=true tool_version=1
6 clean shutdown -> exit=0
```

## 7. 验证记录（§52–§58）

```text
full pytest             990 passed, 1 skipped（550.48s；在最终 HEAD 上重跑；P0 新增回归全在其中）
targeted gates          366 passed（tests/delivery + tests/agent + tests/mcp + tests/v4/isolation
                         + tests/acceptance + tests/v4/skills + V2/V3 frozen guards +
                         repair regression + product surface，在最终 HEAD 上重跑）
tests/acceptance/**     PASS（含 frozen guards：V2 frozen / V3 frozen / repair frozen）
tests/delivery/**       PASS（含 4 个新回归）
tests/quality/**        PASS（含 6 个 issue 生命周期回归）
tests/agent/**          PASS（含 6 个 approval 生命周期回归）
tests/mcp/**            PASS（50；含 2 个真实 stdio subprocess 回归）
tests/v4/isolation/**   PASS（模块边界与反向依赖未被破坏）
tests/v4/skills/**      PASS（V4.0.1 baseline 守卫 + V4.0.2 delta 守卫）
browser golden          browser_v4_studio_golden.cjs PASS（真实下载 md/docx/nfpack）
browser agent           browser_v4_11_agent.cjs PASS（approvals >= 1 且完成）
validate_project.py     PASS（46 个 API 路径）
validate_v4_0_1_skills  PASS（77 skills / 16 modules / 23 tools / 13 resources）
validate_v4_0_2_skills  PASS（6 override skills / 11 files / base=V4.0.1 unchanged）
product diff gate       git diff fa3d748..HEAD -- src ui novel → 仅 P0 修复涉及的源文件
```

## 8. Skill baseline 状态

```text
V4.0.1 baseline（历史）  未修改：SKILL_MANIFEST.json 98 文件哈希仍全部一致（dogfood 的 18 项 skill 修正留在 V4.0.1 内）
V4.0.2 baseline（新增）  skills/novelforge-v4.0.2/**：继承 V4.0.1，只覆盖 P0 影响的 11 个文件
  覆盖内容
    delivery/README.md + delivery/validate-delivery      → live issue 语义（PB-1）
    agent/README.md + agent/approve-agent-run            → approval durable（PB-2）
    mcp/README.md + mcp/start-mcp-server                 → stdio 可用（PB-3）
    workflows/{prepare-final-delivery, operate-with-agent, use-novelforge-through-mcp} → closure 实测记录
    README.md / manifest.yaml / SKILL_MANIFEST.json       → 继承机制与哈希基线
  继承机制（不引入框架）
    生效集合 = V4.0.1 全部文件 ∪ V4.0.2 同路径覆盖；覆盖路径必须已存在于 V4.0.1
    ID 命名空间：override 用 novelforge-v4.0.2.*；继承文件保持 novelforge-v4.0.1.*
  校验工具  python scripts/validate_v4_0_2_skills.py（含 V4.0.1 未被改动的哈希校验）
```

## 9. Backlog 状态（§63：不因只修 P0 而删除）

| 项 | 状态 | 说明 |
| --- | --- | --- |
| PB-1 / PB-2 / PB-3 | **CLOSED** | 本报告 §2–§5 |
| PB-4（单例节点 sequence=0 → Q0 SEQUENCE_INVALID） | OPEN（P1） | 本轮刻意不动；skill 保留警告 |
| PB-5（Q9 gate 行 blockers 计数与 issues 不一致） | OPEN（P2） | 未改 `_gate_rows` 语义 |
| PB-6（MCP envelope `ok=false` 但 `errors=[]`） | OPEN（P3） | MCP Contract §6 语义未变；skill 已注明 |
| GAP-001（`/studio/generate` dry_run 未实现） | DEFERRED | 非 P0；skill 保留警告 |
| GAP-002（`build_links` 无对外入口） | DEFERRED（P1） | 影响 Q5/Q7/Q9；属新能力（任务书 §38 暂缓） |
| GAP-003（Canon REST 不经 Application / 无 MCP） | OPEN | 未动 |
| GAP-004（Memory 无 facade/REST/MCP） | OPEN | 未动 |
| GAP-005（插件生命周期 Application-only） | OPEN（有意 DEFER） | 未动 |
| GAP-006（Editor advanced ops 无 wire 入口） | OPEN | 未动 |
| GAP-007（Delivery explicit_revisions UI 无入口） | OPEN | PB-1 修好后不再是唯一绕路口径，优先级下降 |
| GAP-008（StoryState 无产品级入口） | OPEN（只读足够） | 未动 |
| GAP-009（REST/UI 无法指定隔离 root） | OPEN（P1） | 本轮 closure 用 `studio_ui_test_server.py --root` 隔离 |
| GAP-010（issue 生命周期无"随最新报告自动关闭"） | **SUPERSEDED** | 由 PB-1 的 `live_issues()` 语义解决（delivery 侧不再被历史 issue 卡住） |
| GAP-011（`GENERATION_UNAVAILABLE` 一个 code 表示两类原因） | OPEN | 未动 |
| GAP-012（snapshot 与 deliver 共用 POST /delivery） | OPEN（认知成本） | 未动 |
| Canon 目标发现性歧义（Q2 vs canon.validate） | OPEN | 属文档改进项，未动 |

## 10. 提交与改动清单

```text
branch  v4-402-stabilization
commits
  395482d fix(delivery): ignore resolved historical quality blockers
  ce892b4 fix(agent): preserve approval state through protected step execution
  fd40c77 fix(mcp): restore supported stdio server startup
  99b6629 docs(skills): add v4.0.2 skill baseline delta and closure report
  9fb886d docs(v4): refresh v4.0.2 verification numbers on the final HEAD
  （下一提交）docs(v4): record exact commit list in the stabilization report

product files changed
  src/novelforge/quality/store.py
  src/novelforge/delivery/selection.py
  src/novelforge/delivery/validation.py
  src/novelforge/agent/session.py
  src/novelforge/agent/executor.py
  src/novelforge/application/services/agent.py
  src/novelforge/interfaces/mcp/server.py
tests created
  tests/delivery/test_delivery_historical_quality.py
  tests/quality/test_quality_issue_lifecycle.py
  tests/agent/test_agent_approval_lifecycle.py
  tests/mcp/test_mcp_stdio_entrypoint.py
tests modified
  tests/browser_v4_11_agent.cjs（真实 protected approval + batch pause 处理）
skill baseline
  skills/novelforge-v4.0.2/**（新增，11 文件）+ scripts/validate_v4_0_2_skills.py
  tests/v4/skills/test_v4_0_2_delta.py
docs
  docs/v4/V4_0_2_STABILIZATION_REPORT.md（本文件）
```

## 11. 版本建议与发布边界

```text
Recommended release version   v4.0.2（patch：三个 P0 bugfix，无新增 major capability）
发布动作                      本轮不执行：不 merge main、不更新 v4、不创建 tag、不做 Release
下一步（建议，由作者决定）
  1 复核本报告与 4 个新增 test 文件，确认修复语义符合预期
  2 决定是否发布 v4.0.2（合并到 main/v4 + 打 tag + CHANGELOG 同步）
  3 之后按优先级处理 P1：PB-4（sequence）、GAP-002（build_links 对外入口）、GAP-009（--root）
```

## 12. 最终判定

```text
[x] PB-1 reproduced before fix / fixed / stale issue no longer blocks / real blocker still blocks
[x] PB-2 reproduced before fix / fixed / protected approval completes / reject path correct /
    wrong & duplicate approval safe / browser approval path covered（approvals >= 1）
[x] PB-3 reproduced before fix / fixed / real stdio subprocess handshake PASS /
    MCP 23 tools / 13 resources unchanged
[x] prepare-final-delivery / operate-with-agent / use-novelforge-through-mcp workflow PASS
[x] full pytest 0 failed（982 passed, 1 skipped）
[x] acceptance / frozen guards / delivery / agent / MCP / isolation / browser PASS
[x] skill delta updated（V4.0.2 覆盖 + 继承）且 original V4.0.1 evidence preserved
[x] no unrelated P1/P2/P3 implementation（PB-4 / GAP-002 / GAP-009 等原样保留）
[x] working tree clean

NOVELFORGE V4.0.2 P0 STABILIZATION = PASS
```
