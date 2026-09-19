# Module: `agent` — 有界 Agent Mode（V4.0.2）

> 本文件覆盖（override）`skills/novelforge-v4.0.1/agent/README.md` 的继承版本。
> 差异只在 **approval 的 durable 语义**（PB-2 修复）；其余内容与 V4.0.1 相同。

```text
Module purpose     目标 → 计划预览（0 mutation）→ 有界执行 → 审批 → 检查点 → 恢复 / 取消
Authoritative owner src/novelforge/agent/{contracts,planner,executor,verifier,policy,checkpoint,audit,session}.py
                   + src/novelforge/application/services/agent.py（Ports + AgentService）
Owned skills       plan-agent-goal / start-agent-session / inspect-agent-session /
                   approve-agent-run / resume-agent-session / cancel-agent-session
Truth ownership    无。Agent 只通过 Application Services 的窄 Port 调用既有能力
Public interfaces  UI「Agent」；REST /api/story-builder/agent/*；
                   Application AgentService；MCP = N/A（MCP 明确不暴露编排）
Dependencies       application.services（AgentRead/Generation/Editor/Quality/Delivery Port）
Forbidden          run shell / python / read_file / write_file / execute_sql / import_module /
                   直连 provider / 自建 MCP client / 自动接受 / 自动交付
Related modules    generation、editor、quality、repair、delivery（被编排者）
```

## 状态机与预算

```text
状态：created → planning → awaiting_approval → executing → verifying → completed
      （异常分支：paused / failed / cancelled / needs_human_review）
默认 policy：max_steps=20, max_mutations=10, max_repair_rounds=2, max_batch_steps=8,
             allow_generation/edit/quality/repair=true,
             allow_auto_accept=false, allow_delivery=false,
             require_approval_for=PROTECTED_ACTIONS
```

## approval 是 durable evidence（V4.0.2 起，PB-2 修复）

```text
对某个 protected step 的批准必须可证明到底：
  session.approved_step_approvals() 暴露 step_id → approval_id；
  approve 之后从 **checkpoint 继续**（start_sequence / completed_steps / run_id），
  不重跑已完成步骤；
  该步执行时把 approval_id 写进结果（request_accept 的 success_criteria 就是
  approval_recorded），并进入 result_refs / audit。
仍然成立的安全边界：wrong / stale approval 一律拒绝；approve 只授权该步；
Agent 不会自行批准，也不会自动接受或自动交付。
```

## 不变量

```text
NO_ARBITRARY_ACTION：plan 只能引用已注册 action（13 个）；未注册 / 禁用字符串 → AGENT_PLAN_INVALID
PLAN_IS_ZERO_MUTATION：plan 不修改任何内容
PROTECTED_NEEDS_APPROVAL：request_accept / accept_revision / deliver 需要作者批准
APPROVAL_IS_DURABLE：批准证据（approval_id）在执行到该步时仍可用，且写入结果与审计
APPROVE_RESUMES_FROM_CHECKPOINT：批准后从 checkpoint 继续，不重放已完成步骤
NO_SILENT_ACCEPT / NO_SILENT_DELIVER：默认不允许自动接受与正式交付
AUDITABLE_AND_RESUMABLE：每步有 audit 记录与 checkpoint，可 resume / cancel
REVISION_DRIFT_STOPS：step 执行前检测 revision 漂移 → pause / needs_human_review
```
