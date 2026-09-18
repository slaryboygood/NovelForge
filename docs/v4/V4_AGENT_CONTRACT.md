# NovelForge V4 — Agent Contract（V4-11 冻结，SSOT）

> 状态：**V4-11 Agent Mode & Bounded Autonomous Orchestration（2026-09-18 实施完成）**
> 依据：`docs/v4/V4_11_AGENT_CAPABILITY_INVENTORY.md`、V4-01→V4-10 各 Contract；ADR-034/035/036

## 1. 铁律

```text
AGENT_ORCHESTRATES_EXISTING_CAPABILITIES   Agent 只编排已有能力
AGENT_DOES_NOT_REIMPLEMENT_BUSINESS_LOGIC  不重新实现 Generation/Quality/Editor/Delivery
AGENT_MUTATIONS_ARE_REVISIONED             全部 mutation 走 append-only revision
AGENT_ACTIONS_ARE_IDEMPOTENT               每步携带固定 idempotency_key
AGENT_AUTONOMY_IS_BOUNDED                  max_steps / max_mutations / budget
AGENT_ACCEPTANCE_REQUIRES_EXPLICIT_POLICY  默认不自动接受
AGENT_DELIVERY_REQUIRES_EXPLICIT_POLICY    默认不自动交付
AGENT_ALWAYS_LEAVES_AN_AUDIT_TRAIL         goal → plan → step → mutation → verification
```

```text
Agent core（agent/*）→ 只认识 agent.ports 的窄 Protocol
application.services.agent（composition）→ Application-backed Port Adapters
REST / MCP / UI → 只调用 AgentService
MCP 与 Agent 是平级消费者：Agent 不通过 MCP 调业务
```

## 2. Public Contract

```text
agent.contracts   AgentGoal / AgentScope / AgentPolicy / AgentContextSnapshot /
                  AgentStep / AgentPlan / AgentApprovalRequest / AgentApprovalDecision /
                  AgentStepResult / AgentResult / AgentRun / AgentCheckpoint /
                  AGENT_STATUSES / AGENT_TRANSITIONS / PROTECTED_ACTIONS
agent.registry    ACTION_REGISTRY / action_spec / allowlisted_actions / FORBIDDEN_ACTIONS
agent.planner     HeuristicPlanner（默认，确定性）/ ModelPlanner（agent.plan.v1）/ validate_plan
agent.executor    AgentExecutor（bounded，不新增步骤）/ ExecutionOutcome
agent.verifier    AgentVerifier（只验证 success_criteria，不判断故事质量）
agent.policy      AgentBudget / check_action_allowed / check_scope / check_budget
agent.session     AgentSessionRecord / AgentSessionStore（JSON，经 persistence.paths）
agent.errors      AGENT_PLAN_INVALID / AGENT_POLICY_DENIED / AGENT_STEP_FAILED /
                  AGENT_REVISION_CONFLICT / AGENT_APPROVAL_REQUIRED / AGENT_APPROVAL_STALE /
                  AGENT_BUDGET_EXHAUSTED / AGENT_MAX_STEPS_REACHED / AGENT_CANCELLED /
                  AGENT_NEEDS_HUMAN_REVIEW / AGENT_NOT_FOUND
application.services.agent   AgentService / session_novel_id / agent_service
```

## 3. 状态机（唯一 SSOT）

```text
created → planning → {awaiting_approval | executing | paused | needs_human_review}
executing → {verifying | awaiting_approval | paused | completed | failed | cancelled}
paused → {executing | planning | cancelled | failed}
completed / cancelled 为终态；needs_human_review 需要作者决定
```

## 4. Action Registry（不允许任意字符串，§22–§23、§76）

| action | mutation | protected | 底层能力 |
| --- | --- | --- | --- |
| `inspect_blueprint` | 否 | 否 | ReadPort |
| `generate_node` / `regenerate_node` | 是 | 否 | GenerationPort（BlueprintService） |
| `patch_node` / `rewrite_node` | 是 | 否* | EditorPort（EditorService） |
| `evaluate` / `plan_repair` / `repair` / `verify_repair` | 是* / 否 / 是 / 否 | 否 | QualityPort（ReviewService / EditorService） |
| `request_accept` | 否 | **是** | EditorPort（只产生 approval 请求） |
| `accept_revision` | 是 | **是** | EditorPort.accept |
| `validate_delivery` | 否 | 否 | DeliveryPort.validate |
| `deliver` | 是 | **是** | DeliveryPort.deliver |

`*` patch/rewrite/regenerate 目标是**已接受的高层节点**（premise/theme/world/story_arc/
structural_unit）时自动升级为 protected（§16、§51）。禁止的 action：
`run_shell` / `run_python` / `read_file` / `write_file` / `execute_sql` /
`import_module` / `install_plugin` / 任何未注册字符串。

## 5. Policy（默认保守）

```text
max_steps=20  max_mutations=10  max_repair_rounds=2  max_batch_steps=8
allow_generation/edit/quality/repair = True
allow_auto_accept = False        （接受必须作者批准）
allow_delivery = False           （正式交付必须显式开启）
require_approval_for = PROTECTED_ACTIONS
token_budget / cost_budget / time_budget_s（可选；只汇总可用 usage，不发明价格）
```

## 6. 计划与校验

```text
plan(goal, dry_run=True) → AgentPlan（0 mutation）+ preview（步骤 / 是否修改 / 是否需确认）
validate_plan: action allowlist → target_kinds → scope → target 存在性 →
               expected_revision → policy/approval → max_steps / max_mutations
LLM Planner（agent.plan.v1）输出必须通过同一套校验；模型不能输出任意 executable JSON
replan 产生新 plan_revision；旧 plan 保存在 plan_history（不偷偷修改，§31、§74）
```

## 7. 执行语义

```text
bounded: max_steps / max_mutations / batch limit / token·cost·time 预算
approval: protected step 未批准 → awaiting_approval（0 mutation）
revision: 修改已有节点必须 expected_revision；不符 → AGENT_REVISION_CONFLICT + step stale（pause）
idempotency: step.idempotency_key 固定；重放不产生重复 revision / delivery / node
verification: 每步按 success_criteria 复核（node_exists / revision_changed / accepted /
              report_exists / verification_status / manifest_exists）——不判断故事质量
repair: 复用既有 Repair Loop（max_repair_rounds），无 open issue → 步骤 skipped（不是失败）
cancel: 标记 cancel_requested 并在下一个步骤前停止（不声称已物理中止模型调用，§61）
stop conditions: goal achieved / approval required / revision conflict / budget exhausted /
                 max steps / needs_human_review / unsupported action / fatal error / cancel
```

## 8. Approval / Checkpoint / Audit

```text
AgentApprovalRequest: approval_id / action / target / before / proposed_after /
                      affected_nodes / quality_summary / risk / revision_refs /
                      expires_if_revision_changes（revision 变了即 stale → 必须重新规划）
AgentCheckpoint: session / plan revision / next step / completed steps / budget used /
                 revision refs（resume 前必须重新校验 revision drift）
AgentAuditRecord: session → run → plan → step → operation → business result refs
                  与 EditorOperationRecord 分开存储，通过 request_id / step_id 关联
持久化：novel/authoring/story_engine/agent/{sessions,runs,checkpoints,audit}（经 persistence.paths）
       Agent 数据是 orchestration metadata，永远不是 Canon / StoryState / Blueprint / Quality truth
```

## 9. 接口面

```text
REST（thin）：POST /api/story-builder/agent/plan | start | {id}/approve | {id}/reject |
              {id}/resume | {id}/cancel ；GET /agent/{id} | /agent/sessions
UI：Story Studio → Agent 辅助入口（goal → plan → steps → approval → result）
MCP：V4-11 不新增 agent tool（Application AgentService 稳定优先，§63、§102）
```

## 10. 测试

```text
tests/agent/**                           35 tests（契约 / 规划 / 执行 / 审批 / 预算 / resume / drift）
tests/v4/isolation/test_agent_boundaries.py  9 tests（模块边界与反向依赖）
ui/src/studio/**/*.test.ts(x)            60 tests（含 Agent 面板与导航）
tests/browser_v4_11_agent.cjs            Agent 浏览器门禁（plan → start → approval → complete）
```
