# V4-11 AGENT MODE RESULT

> 阶段：**V4-11 Agent Mode & Bounded Autonomous Orchestration**　状态：**PASS**
> 日期：2026-09-18　分支：`v4-11-agent-mode`
> 契约：[V4_AGENT_CONTRACT.md](V4_AGENT_CONTRACT.md)（SSOT）　盘点：[V4_11_AGENT_CAPABILITY_INVENTORY.md](V4_11_AGENT_CAPABILITY_INVENTORY.md)

## 1. Capability inventory

`docs/v4/V4_11_AGENT_CAPABILITY_INVENTORY.md`：把 13 项原子能力映射到已有 Application
Service（Mutation / Approval / Revision / Idempotency / Agent Action），列出
「只是 MCP 包装」「需要 Port」「绝不能开放给 Agent」四类，以及第一批 13 个 action 与
永不存在的 action（shell / python / file / sql / import）。

## 2. Agent architecture

```text
User Goal → Planner → AgentPlan → Executor → Agent Ports → Existing Application Services
（planner 不执行；executor 只执行已验证步骤；不新增步骤、不偷偷 replan）
```

## 3. Public contracts

`novelforge.agent`（52 symbols）：AgentGoal / AgentScope / AgentPolicy /
AgentContextSnapshot / AgentStep / AgentPlan / AgentApprovalRequest /
AgentApprovalDecision / AgentStepResult / AgentResult / AgentRun / AgentCheckpoint /
AgentStatuses+Transitions / ActionRegistry / Planner / Executor / Verifier /
AgentBudget / SessionStore / error 家族。`AgentService` 在 application 层。

## 4. Port architecture

`agent/ports`：ReadPort / GenerationPort / EditorPort / QualityPort / DeliveryPort /
（可选）PlannerModel，全部窄 Protocol + 只读结果 dataclass（NodeRef / GenerationOutcome /
EditOutcome / QualityOutcome / RepairOutcome / DeliveryOutcome）。实现位于
`application.services.agent`（composition），因此 agent 与 application 无循环依赖。

## 5. Goal model

`AgentGoal(goal_id, novel_id, instruction, scope, constraints, success_criteria,
request_id)`；scope 必须显式（novel / structural_unit / chapter / scene / nodes），
否则拒绝或在规划阶段要求补充。

## 6. Policy

`AgentPolicy`：max_steps=20 / max_mutations=10 / max_repair_rounds=2 / max_batch_steps=8 /
token·cost·time 预算 / allow_generation·edit·quality·repair /
**allow_auto_accept=False** / **allow_delivery=False** / require_approval_for=PROTECTED_ACTIONS。

## 7. Plan

`AgentPlan`：plan_id / goal_id / novel_id / plan_revision / steps /
estimated_mutations / estimated_model_calls / affected_nodes / protected_nodes /
required_approvals / budget_estimate（含 policy_notes）/ planner_version / snapshot_digest。

## 8. Step registry

13 个注册 action（inspect / generate / regenerate / patch / rewrite / evaluate /
plan_repair / repair / verify_repair / request_accept / accept_revision /
validate_delivery / deliver）；未知或禁止的 action → `AGENT_PLAN_INVALID`。

## 9. Planner

`HeuristicPlanner`（默认，确定性指令解析：章节数 / 每章场景数 / 质量 / 修复 / 接受 /
交付 / 重写目标）+ `ModelPlanner`（`agent.plan.v1`，可选模型，输出经同一套校验）。

## 10. Plan validation

`validate_plan`：action allowlist → target_kinds → scope（含祖先链）→ target 存在性 →
expected_revision（不符 → `AGENT_REVISION_CONFLICT`）→ policy / approval 标记 →
max_steps / max_mutations。

## 11. Execution engine

`AgentExecutor.execute`：按 sequence 执行；batch limit；每步 budget 检查 →
approval gate → revision precondition → port 调用（携带 idempotency_key）→
verification → audit → checkpoint。停止后返回 ExecutionOutcome（run / checkpoint /
status / stop_reason / approvals / error）。

## 12. Verification

`AgentVerifier` 只校验 step 的 success_criteria（node_exists / status_proposed /
revision_changed / fields_match / report_exists / plan_exists / verification_status /
acceptance / validation_recorded / manifest_exists）——不判断故事质量（质量归 QualityService）。

## 13. Revision semantics

任何修改已有节点的步骤必须带 `expected_revision`（规划期与执行期各校验一次）；
不符 → step 标记 `stale` + `AGENT_REVISION_CONFLICT` + session paused，0 mutation。

## 14. Idempotency

step 携带固定 `idempotency_key`（executor 保证同一 key 重放不产生重复）；
完成步骤记录在 run / checkpoint 中，resume 与重放跳过已完成步骤（测试断言章节数不增加）。

## 15. Approval model

`AgentApprovalRequest`（approval_id / action / target / before / proposed_after /
affected_nodes / quality_summary / risk / revision_refs / expires_if_revision_changes）+
`AgentApprovalDecision`（approved / rejected / modified）。未批准 → awaiting_approval（0 mutation）。

## 16. Protected actions

accept_revision / deliver / request_accept；以及"重写已接受的高层节点"
（premise / theme / world / story_arc / structural_unit）自动升级为 protected。

## 17. Budget

`AgentBudget` 汇总 steps / mutations / repair_rounds / model_calls / tokens / cost /
by_phase / total（只累加后端给出的 usage，不发明价格）。达到上限 → paused +
`AGENT_BUDGET_EXHAUSTED`（max_steps → `AGENT_MAX_STEPS_REACHED`）。

## 18. Stop conditions

goal achieved / approval required / revision conflict / budget exhausted / max steps /
needs_human_review / unsupported action / fatal business error / user cancel —— 全部映射到
稳定 code 与状态。

## 19. Quality integration

`evaluate` 调用 `ReviewService.evaluate`（gate-based）；报告 / issue 来自 Quality Store；
Agent 不产生第二套质量结论。

## 20. Repair integration

`plan_repair` → `repair` → `verify_repair` 全部走既有 Repair Loop（`max_repair_rounds`）；
没有可修复的 open issue → 步骤 `skipped`（附原因），不是失败，也不循环。

## 21. Human review

`needs_human_review`（例如 unpaid required setup / 修复契约冲突）→ 状态
`needs_human_review` + `AGENT_NEEDS_HUMAN_REVIEW`；Agent 不自动创建剧情性 payoff。

## 22. Checkpoint

每步之后写 `AgentCheckpoint`（session / plan / plan_revision / next_step_sequence /
completed_steps / budget_used / revision_refs / stop_reason）。

## 23. Resume

`AgentService.resume`：读 checkpoint → 重新校验 revision drift → 无 drift 则从
`next_step_sequence` 继续（新 AgentService 实例也可恢复，有测试）。

## 24. Revision drift handling

drift（checkpoint 记录 r3，现在 r5）→ 不继续执行，状态 paused +
`AGENT_REVISION_CONFLICT`，并返回 drift 明细（expected / current）。

## 25. Cancellation

`cancel` 标记 cancel requested 并在下一个步骤前停止；文案明确
「将在当前步骤结束后停止（不会中断已经发出的模型请求）」；取消是终态，
resume 会抛 `AGENT_CANCELLED`（必须重新 plan）。

## 26. Audit

`AgentAuditRecord`（session / run / plan / plan_revision / step / goal / operation /
target / status / request_id / idempotency_key / business_result_refs / timestamp），
与 EditorOperationRecord 分开存储、通过 request_id / step_id 关联；不写 prompt / secret。

## 27. Persistence

`novel/authoring/story_engine/agent/{sessions,runs,checkpoints,audit}`，全部经
`persistence.paths`（新增 `agent_runtime` artifact kind + 6 个 path helper）；
Agent 数据是 orchestration metadata，不是 story truth。

## 28. Application AgentService

`application.services.agent.AgentService`：plan / start / status / resume / approve /
reject / cancel / history / audit_records（+ `run_next_step` 的 bounded 等价物：
`start(max_batch_steps=1)`）；`session_novel_id` 供接口层做 session → novel 反查。

## 29. REST / MCP exposure

REST（thin，`api/agent_routes.py`）：POST plan / start / {id}/approve / {id}/reject /
{id}/resume / {id}/cancel；GET {id} / sessions —— 稳定错误码映射（403/404/409/422）。
MCP：本阶段不新增 agent tool（§63、§102，非 PASS 必须项）。

## 30. Agent UI

Story Studio 新增辅助入口 **Agent**（不改 V4-10 其它工作区）：
目标输入 + 范围选择（含具体幕 / 章选择）→ 计划预览（步骤 / 是否修改 / 是否需确认 /
预计模型调用 / policy 说明）→ 执行进度（步骤状态 + 错误码 + 审计折叠）→
审批面板（做什么 / 为什么 / 影响节点 / 基于版本 / 建议内容 + 批准 / 拒绝）→
完成摘要（改动节点 / 新版本 / 质量结论 / 需作者决定）+ 取消（诚实文案）。

## 31. Browser workflow

`tests/browser_v4_11_agent.cjs` = **PASS**：打开 Agent → 输入目标 → 计划预览（0 mutation）→
开始执行 → （如出现）审批 → 继续 → 完成摘要 → 断言新章节仍为 `proposed` →
取消文案诚实检查。真实 Edge + stub 模型，0 real model calls；截图
`workspace/studio_ui_review/13-agent-goal.png` … `16-agent-complete.png`。

## 32. Module boundaries

`tests/v4/isolation/test_agent_boundaries.py`（9 tests，永久）：
agent ✗ api / interfaces / repository / store / provider / HTTP / shell / SQL /
自行拼路径；agent 只依赖 core + persistence.paths；业务模块 ✗ import agent
（只有 application.services.agent 可以）；interfaces ✗ import agent internals；
public contract 只含 contracts/runtime，不含 AgentService 内部实现。

## 33. Tests

```text
tests/agent/**                                35 passed
  test_agent_contracts.py                     契约 / 状态机 / action registry / 错误码
  test_agent_planner.py                       intent 解析 / 计划结构 / 校验 / 模型 Planner
  test_agent_execution.py                     golden goal / 幂等重放 / 不自动接受 / 不自动交付
  test_agent_approval.py                      protected / stale / reject / accept 需批准
  test_agent_resume_budget.py                 max steps / cancel / resume / drift / 预算
  test_agent_human_review.py                  needs_human_review / 交付保护（port-level）
  test_agent_budget_ports.py                  预算与上限（port-level，确定性）
tests/v4/isolation/test_agent_boundaries.py    9 passed
ui/src/**/*.test.ts(x)                        60 passed（含 Agent 面板 + 导航边界）
tests/browser_v4_11_agent.cjs                 PASS
```

## 34. Impact-based validation

```text
pytest -q tests/agent tests/plugins tests/v4 tests/editor tests/quality \
          tests/generation tests/delivery tests/test_v2_frozen_guard.py \
          tests/test_v3_frozen_guard.py            → PASS
python scripts/validate_project.py                  → PASS
前端：npm test（60 passed）+ npm run build          → PASS
Full regression: NOT REQUIRED — impact-based validation sufficient.
（未改 Python 依赖 / core / Blueprint schema / 共享持久化语义 / 共享测试基础设施）
```

## 35. Frozen boundary

```text
novelforge-product-v3-final = f21464713e4786410e5550a7ad5504692cc644dd（未移动）
novel/authoring frozen digest = 未修改（Agent 数据在 gitignored 路径下）
story_engine/repair.py = 未改；REPAIR_GATE_V1 = 未改
Canon / StoryState 语义 = 未改
```

## 36. Architecture risks

```text
R-10 Agent duplicate writes（H/H）→ **已缓解（V4-11）**：稳定 step_id + 固定
  idempotency_key + expected_revision + checkpoint 跳过已完成步骤 + 幂等重放测试。
R-09 Revision race（M/H）→ Agent 面新增两道检查（规划期 + 执行期），冲突即 pause，
  不覆盖；仍保留"冲突需要作者重新规划"的诚实语义。
R-13 Cost explosion / R-14 Infinite repair loop → Agent 侧新增 max_steps /
  max_mutations / token·cost·time 预算 + max_repair_rounds + batch limit；
  budget 达到即停止且不再调用模型（有测试）。
新增观察项：Agent 编排元数据增长（checkpoint / audit 单文件，当前上限 1000 条记录）
  → 记入 V4-12 前的观察项，不阻塞本阶段。
```

## 37. Files created

```text
src/novelforge/agent/{__init__,contracts,errors,policy,registry,planner,executor,
                     verifier,session,checkpoint,audit}.py
src/novelforge/agent/ports/__init__.py
src/novelforge/application/services/agent.py
src/novelforge/api/agent_routes.py
ui/src/api/agent.ts、ui/src/studio/workspaces/Agent.tsx、.../agent.test.tsx
tests/agent/**（conftest / agent_support / port_harness / 7 个测试文件）
tests/v4/isolation/test_agent_boundaries.py
tests/browser_v4_11_agent.cjs
docs/v4/V4_AGENT_CONTRACT.md、V4_11_AGENT_CAPABILITY_INVENTORY.md、
  V4_11_AGENT_MODE_REPORT.md
docs/v4/adr/ADR-034|035|036-*.md
```

## 38. Files modified

```text
src/novelforge/persistence/{paths,__init__}.py（agent_* 路径 + agent_runtime kind）
src/novelforge/api/app.py（install_agent_api）
ui/src/studio/nav.ts、StudioApp.tsx、design/status.tsx（Agent 入口 + 状态语义）
ui/src/studio/nav.test.ts、workspaces/agent.test.tsx
docs/v4/V4_MODULE_BOUNDARIES.md、V4_ARCHITECTURE.md、V4_ARCHITECTURE_RISKS.md、
  V4_BRANCH_STRATEGY.md、adr/README.md
```

## 39. Files deleted

```text
（无）
```

## 40. Git branch

```text
v4-11-agent-mode（从 V4-10 head 7273e18 切出）
```

## 41. Git commits

```text
（1）docs(v4): freeze agent mode contracts
（2）feat(agent): add goal plan session and policy contracts
（3）feat(agent): add planner and bounded execution engine
（4）feat(application): expose agent orchestration service
（5）feat(agent): add approval checkpoint resume and audit
（6）feat(ui): add story studio agent workflow
（7）test(agent): add planning execution revision and budget coverage
（8）test(browser): add agent approval workflow gate
（9）test(v4): enforce agent module boundaries
（10）docs(v4): record v4-11 result
```

## 42. Remaining risks

| 风险 | 状态 | 说明 |
| --- | --- | --- |
| Planner 是启发式解析（非模型） | 已知 | 默认确定性解析；模型 Planner（`agent.plan.v1`）已实现但需注入；复杂自然语言目标建议由模型 Planner 承担 |
| Agent 编排元数据增长 | 观察项 | audit 上限 1000 条；session / checkpoint 单文件，长期会话需要归档策略 |
| MCP 未暴露 agent tool | 有意 DEFER | Application AgentService 先稳定（§63、§102） |
| cancel 不中止在途请求 | 设计约束 | 与 Gateway 能力一致；文案已诚实说明 |
| 插件能力未接入 Agent | DEFER | 仅可用已 approved + enabled 的 plugin capability，本阶段不做 |

## 43. V4-12 readiness

```text
[x] agent 独立模块 + 窄 Port + AgentService facade + 边界守卫
[x] Goal / Policy / Plan / Step / Result 契约与结构化 schema
[x] 确定性 Planner + 可选模型 Planner（同一套校验）
[x] bounded 执行（steps / mutations / batch / token·cost·time）
[x] revision-aware（expected_revision + drift + stale approval）
[x] idempotency + checkpoint + resume + audit
[x] protected action 审批流（默认不自动接受 / 不自动交付）
[x] Quality / Repair 复用既有能力，needs_human_review 保留
[x] REST + Story Studio Agent UI + 浏览器门禁
[x] Agent 测试 35 + 边界 9 + 前端 60 + browser gate PASS

V4-12 可从此继续：AgentService / Ports / 审计与 checkpoint 均可作为上层
（例如更强的模型 Planner、MCP agent tool、插件 capability 接入）的稳定基座。
```

---

```text
V4-11 = PASS
```
