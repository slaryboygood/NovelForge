"""Bounded Agent Executor（V4-11 §30–§36、§38–§46、§74）。

只执行**已验证**的 `AgentStep`：不新增步骤、不偷偷 replan、不绕过 revision /
idempotency / approval / budget 约束。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Mapping, Sequence

from .audit import AgentAuditLog, AgentAuditRecord
from .checkpoint import AgentCheckpoint, CheckpointStore
from .contracts import (
    AgentApprovalRequest,
    AgentGoal,
    AgentPlan,
    AgentPolicy,
    AgentRun,
    AgentStep,
    AgentStepResult,
    utc_now,
)
from .errors import (
    AgentBudgetExhausted,
    AgentError,
    AgentNeedsHumanReview,
    AgentPlanInvalid,
    AgentPolicyDenied,
    AgentRevisionConflict,
    AgentStepFailed,
)
from .policy import AgentBudget, check_budget, merge_usage
from .ports import (
    AgentDeliveryPort,
    AgentEditorPort,
    AgentGenerationPort,
    AgentQualityPort,
    AgentReadPort,
    RepairOutcome,
)
from .verifier import AgentVerifier

#: 业务错误 code → Agent stop 语义
REVISION_CONFLICT_CODES: tuple[str, ...] = (
    "REVISION_CONFLICT", "EDITOR_REVISION_CONFLICT", "AGENT_REVISION_CONFLICT",
)
HUMAN_REVIEW_CODES: tuple[str, ...] = (
    "REPAIR_CONTRACT_CONFLICT", "REPAIR_NOT_ALLOWED", "REPAIR_ROUND_LIMIT",
    "AGENT_NEEDS_HUMAN_REVIEW",
)


@dataclass
class ExecutionOutcome:
    run: AgentRun
    checkpoint: AgentCheckpoint
    status: str
    stop_reason: str
    approvals: list[AgentApprovalRequest] = field(default_factory=list)
    error: Mapping[str, Any] = field(default_factory=dict)
    needs_human_review: bool = False


class AgentExecutor:
    """按 step 顺序执行，受 policy / budget / approval / revision 约束。"""

    def __init__(self, *, read: AgentReadPort, generation: AgentGenerationPort,
                 editor: AgentEditorPort, quality: AgentQualityPort,
                 delivery: AgentDeliveryPort, verifier: AgentVerifier,
                 audit_factory: Callable[[str, str], AgentAuditLog],
                 checkpoints: CheckpointStore) -> None:
        self.read = read
        self.generation = generation
        self.editor = editor
        self.quality = quality
        self.delivery = delivery
        self.verifier = verifier
        self.audit_factory = audit_factory
        self.checkpoints = checkpoints

    # ------------------------------------------------------------------ 入口
    def execute(self, *, goal: AgentGoal, policy: AgentPolicy, plan: AgentPlan,
                run: AgentRun, budget: AgentBudget,
                approved_steps: Sequence[str] = (), start_sequence: int = 0,
                completed_steps: Sequence[str] = (),
                approval_ids: Mapping[str, str] | None = None,
                max_batch_steps: int | None = None) -> ExecutionOutcome:
        audit = self.audit_factory(goal.novel_id, run.session_id)
        approvals: list[AgentApprovalRequest] = []
        completed = set(str(value) for value in completed_steps)
        # V4.0.2 PB-2：`step_id → approval_id`（durable approval）
        approved_approval_ids = {str(key): str(value)
                                 for key, value in dict(approval_ids or {}).items()}
        batch_limit = int(max_batch_steps if max_batch_steps is not None
                          else policy.max_batch_steps)
        executed_in_batch = 0

        steps = sorted(plan.steps, key=lambda row: int(row.sequence))
        for step in steps:
            if int(step.sequence) < int(start_sequence):
                continue
            if step.step_id in completed:
                continue
            if run.cancel_requested:
                return self._stop(run, plan, step, budget, status="cancelled",
                                  reason="user cancel requested",
                                  error_code="AGENT_CANCELLED", approvals=approvals)
            if executed_in_batch >= batch_limit:
                return self._stop(run, plan, step, budget, status="paused",
                                  reason=f"reached batch limit {batch_limit}",
                                  error_code="", approvals=approvals)
            # budget / 上限（§43–§46）
            try:
                check_budget(policy, budget, next_step=step,
                             steps_executed=len(run.step_results))
            except AgentBudgetExhausted as exc:
                code = ("AGENT_MAX_STEPS_REACHED"
                        if dict(exc.details).get("kind") == "max_steps" else exc.code)
                return self._stop(run, plan, step, budget, status="paused",
                                  reason=exc.message, error_code=code,
                                  approvals=approvals)

            # approval gate（§16、§45–§50）
            if step.requires_approval and step.step_id not in set(approved_steps):
                request = self._approval_request(goal, plan, step, run)
                approvals.append(request)
                run.status = "awaiting_approval"
                run.step_results.append(AgentStepResult(
                    step_id=step.step_id, status="awaiting_approval",
                    action=step.action, started_at=utc_now(),
                    idempotency_key=step.idempotency_key,
                    result_refs={"approval_id": request.approval_id},
                    warnings=(f"需要作者批准：{step.action}",)))
                audit.record(AgentAuditRecord(
                    session_id=run.session_id, run_id=run.run_id,
                    plan_id=plan.plan_id, plan_revision=plan.plan_revision,
                    step_id=step.step_id, goal_id=goal.goal_id,
                    operation="approval_required", target=dict(step.target),
                    status="awaiting_approval",
                    business_result_refs={"approval_id": request.approval_id}))
                return ExecutionOutcome(
                    run=run, checkpoint=self._checkpoint(run, plan, step, budget,
                                                         completed),
                    status="awaiting_approval",
                    stop_reason=f"approval required for {step.action}",
                    approvals=approvals,
                    error={"code": "AGENT_APPROVAL_REQUIRED",
                           "message": f"需要作者批准：{step.action}"})

            # revision precondition（§34–§35）
            conflict = self._revision_conflict(step)
            if conflict is not None:
                run.step_results.append(AgentStepResult(
                    step_id=step.step_id, status="stale", action=step.action,
                    started_at=utc_now(), idempotency_key=step.idempotency_key,
                    revision_before=int(step.expected_revision or 0),
                    error_code="AGENT_REVISION_CONFLICT",
                    message=conflict.message))
                audit.record(AgentAuditRecord(
                    session_id=run.session_id, run_id=run.run_id,
                    plan_id=plan.plan_id, plan_revision=plan.plan_revision,
                    step_id=step.step_id, goal_id=goal.goal_id,
                    operation=step.action, target=dict(step.target),
                    status="stale", error_code=conflict.code,
                    business_result_refs=dict(conflict.details)))
                return self._stop(run, plan, step, budget, status="paused",
                                  reason=conflict.message,
                                  error_code=conflict.code, approvals=approvals)

            # 执行
            result, outcome = self._run_step(step=step, goal=goal, plan=plan,
                                             run=run, budget=budget,
                                             approved_approval_ids=approved_approval_ids)
            run.step_results.append(result)
            executed_in_batch += 1
            if result.status == "completed":
                completed.add(step.step_id)
                if step.mutation:
                    budget.mutations += 1
            audit.record(AgentAuditRecord(
                session_id=run.session_id, run_id=run.run_id, plan_id=plan.plan_id,
                plan_revision=plan.plan_revision, step_id=step.step_id,
                goal_id=goal.goal_id, operation=step.action,
                target=dict(step.target), status=result.status,
                request_id=result.request_id,
                idempotency_key=step.idempotency_key,
                business_result_refs=dict(result.result_refs),
                error_code=result.error_code))
            self.checkpoints.save(self._checkpoint(run, plan, step, budget, completed))
            if result.status == "failed":
                return self._stop(run, plan, step, budget, status="failed",
                                  reason=result.message or "step failed",
                                  error_code=result.error_code or "AGENT_STEP_FAILED",
                                  approvals=approvals)
            if result.status == "needs_human_review":
                return self._stop(run, plan, step, budget,
                                  status="needs_human_review",
                                  reason=result.message or "needs author decision",
                                  error_code="AGENT_NEEDS_HUMAN_REVIEW",
                                  approvals=approvals)

        run.status = "completed"
        run.finished_at = utc_now()
        run.stop_reason = "goal achieved"
        run.usage = budget.as_dict()
        checkpoint = self._checkpoint(run, plan, None, budget, completed)
        self.checkpoints.save(checkpoint)
        audit.record(AgentAuditRecord(
            session_id=run.session_id, run_id=run.run_id, plan_id=plan.plan_id,
            plan_revision=plan.plan_revision, goal_id=goal.goal_id,
            operation="run_completed", status="completed",
            business_result_refs={"changed_nodes": list(run.changed_nodes)}))
        return ExecutionOutcome(run=run, checkpoint=checkpoint, status="completed",
                                stop_reason="goal achieved")

    # --------------------------------------------------------------- 单步执行
    def _run_step(self, *, step: AgentStep, goal: AgentGoal, plan: AgentPlan,
                  run: AgentRun, budget: AgentBudget,
                  approved_approval_ids: Mapping[str, str] | None = None
                  ) -> tuple[AgentStepResult, Any]:
        started = utc_now()
        approved_ids = dict(approved_approval_ids or {})
        before = self._current_revision(step)
        skip_reason = self._skip_reason(step, goal)
        if skip_reason:
            return (AgentStepResult(
                step_id=step.step_id, status="skipped", action=step.action,
                started_at=started, finished_at=utc_now(),
                idempotency_key=step.idempotency_key, revision_before=before,
                warnings=(skip_reason,),
                message=skip_reason), None)
        try:
            outcome, phase, usage = self._dispatch(
                step, goal, approved_approval_ids=approved_ids)
        except AgentError as exc:
            code = exc.code
            status = "needs_human_review" if code in HUMAN_REVIEW_CODES else "failed"
            if code in REVISION_CONFLICT_CODES:
                status = "stale"
            message = exc.message
            run.status = status
            return (AgentStepResult(step_id=step.step_id, status=status,
                                    action=step.action, started_at=started,
                                    finished_at=utc_now(),
                                    idempotency_key=step.idempotency_key,
                                    revision_before=before, error_code=code,
                                    message=message), None)
        except Exception as exc:  # noqa: BLE001 - 不泄漏 traceback，映射为稳定 code
            wrapped = AgentStepFailed(
                f"{step.action} 执行失败：{type(exc).__name__}",
                step_id=step.step_id,
                details={"action": step.action})
            return (AgentStepResult(step_id=step.step_id, status="failed",
                                    action=step.action, started_at=started,
                                    finished_at=utc_now(),
                                    idempotency_key=step.idempotency_key,
                                    revision_before=before,
                                    error_code=wrapped.code,
                                    message=wrapped.message), None)

        merge_usage(budget, phase, usage)
        # §42 / §52：修复类步骤若「没有可执行内容」，跳过而不是失败
        if step.action in ("repair", "verify_repair") and isinstance(outcome, RepairOutcome):
            if not dict(outcome.verification or {}) and not dict(outcome.result or {}):
                plan_status = str(dict(outcome.plan or {}).get("status") or "")
                reason = ("没有需要修复的问题（修复计划为空）"
                          if plan_status in ("", "empty") else
                          f"修复未产生可复核结果（plan status={plan_status}）")
                return (AgentStepResult(
                    step_id=step.step_id, status="skipped", action=step.action,
                    started_at=started, finished_at=utc_now(),
                    idempotency_key=step.idempotency_key,
                    revision_before=before, result_refs=self._result_refs(outcome),
                    warnings=(reason,), message=reason), outcome)
        if step.action == "plan_repair" and isinstance(outcome, Mapping):
            if str(outcome.get("status") or "") == "empty":
                reason = "没有需要修复的问题（修复计划为空）"
                return (AgentStepResult(
                    step_id=step.step_id, status="skipped", action=step.action,
                    started_at=started, finished_at=utc_now(),
                    idempotency_key=step.idempotency_key,
                    revision_before=before, result_refs=self._result_refs(outcome),
                    warnings=(reason,), message=reason), outcome)
        requested_fields = self._requested_fields(step)
        verification = self.verifier.verify(step, outcome, before_revision=before,
                                           requested_fields=requested_fields)
        produced_node = str(getattr(getattr(outcome, "node", None), "node_id", "") or "")
        if produced_node:
            # 新生成节点：revision 来自业务返回的节点本身
            after = int(getattr(getattr(outcome, "node", None), "revision", 0) or 0)
        else:
            after = self._current_revision(step, fallback=int(
                getattr(outcome, "revision", 0) or 0))
        changed_ids: set[str] = set(getattr(outcome, "changed_fields", ()) or ())
        if produced_node:
            changed_ids.add(produced_node)
        if step.mutation and step.target.get("node_id") and after != before:
            changed_ids.add(str(step.target.get("node_id")))
        changed = tuple(sorted(changed_ids))
        status = "completed" if verification.ok else "failed"
        needs_review = (isinstance(getattr(outcome, "verification", None), Mapping)
                       and bool(dict(outcome.verification or {})
                                .get("needs_human_review")))
        if needs_review:
            status = "needs_human_review"
        result_refs = self._result_refs(outcome)
        # V4.0.2 PB-2：把「这一步是被哪个 approval 批准的」写进结果与审计
        if step.step_id in approved_ids:
            result_refs.setdefault("approval_id", approved_ids[step.step_id])
        result = AgentStepResult(
            step_id=step.step_id, status=status, action=step.action,
            started_at=started, finished_at=utc_now(),
            idempotency_key=step.idempotency_key,
            revision_before=before, revision_after=after,
            result_refs=result_refs,
            issues=tuple(str(value) for value in verification.failed),
            warnings=tuple(getattr(outcome, "warnings", ()) or ()),
            usage=dict(usage or {}), changed_nodes=changed,
            error_code="" if status == "completed" else (
                "AGENT_NEEDS_HUMAN_REVIEW" if status == "needs_human_review"
                else "AGENT_STEP_FAILED"),
            message="" if status == "completed" else (
                "需要作者决定" if status == "needs_human_review"
                else f"验证未通过：{', '.join(verification.failed)}"))
        run.usage = budget.as_dict()
        return result, outcome

    # ---------------------------------------------------------------- 分发
    def _dispatch(self, step: AgentStep, goal: AgentGoal, *,
                  approved_approval_ids: Mapping[str, str] | None = None
                  ) -> tuple[Any, str, Mapping[str, Any]]:
        action = step.action
        target = dict(step.target)
        inputs = dict(step.inputs)
        approved_ids = dict(approved_approval_ids or {})
        node_id = str(target.get("node_id") or "")
        parent_id = str(target.get("parent_id") or "")
        if action == "inspect_blueprint":
            snapshot = self.read.snapshot(goal.novel_id)
            return snapshot, "read", {}
        if action == "generate_node":
            outcome = self.generation.generate(
                task=str(inputs.get("task") or ""), parent_id=parent_id,
                index=int(inputs.get("index") or 0),
                sequence=int(inputs.get("sequence") or 0),
                instruction=str(inputs.get("instruction") or ""),
                unit_type=str(inputs.get("unit_type") or ""),
                idempotency_key=step.idempotency_key)
            return outcome, "generation", outcome.usage
        if action == "regenerate_node":
            outcome = self.generation.regenerate(
                node_id=node_id, task=str(inputs.get("task") or ""),
                expected_revision=step.expected_revision,
                instruction=str(inputs.get("instruction") or ""),
                preserve=tuple(str(value) for value in (inputs.get("preserve") or ())),
                idempotency_key=step.idempotency_key)
            return outcome, "generation", outcome.usage
        if action == "patch_node":
            outcome = self.editor.patch(
                node_id=node_id, changes=dict(inputs.get("changes") or {}),
                expected_revision=step.expected_revision,
                idempotency_key=step.idempotency_key,
                reason=str(inputs.get("reason") or "agent patch"))
            return outcome, "edit", outcome.usage
        if action == "rewrite_node":
            outcome = self.editor.rewrite(
                node_id=node_id,
                target_fields=tuple(str(value) for value in
                                    (inputs.get("target_fields") or ())),
                instruction=str(inputs.get("instruction") or ""),
                expected_revision=step.expected_revision,
                preserve_fields=tuple(str(value) for value in
                                      (inputs.get("preserve_fields") or ())),
                idempotency_key=step.idempotency_key)
            return outcome, "edit", outcome.usage
        if action == "evaluate":
            outcome = self.quality.evaluate(
                gates=tuple(str(value) for value in (inputs.get("gates") or ())),
                node_ids=tuple(str(value) for value in (inputs.get("node_ids") or ())))
            return outcome, "quality", outcome.usage
        if action == "plan_repair":
            issue_ids = tuple(str(value) for value in (inputs.get("issue_ids") or ()))
            if not issue_ids:
                issue_ids = self._open_issue_ids(goal.novel_id)
            plan = dict(self.quality.plan_repair(issue_ids=issue_ids) or {})
            plan["issue_ids"] = list(issue_ids)
            return plan, "quality", {}
        if action == "repair":
            issue_ids = tuple(str(value) for value in (inputs.get("issue_ids") or ()))
            if not issue_ids:
                issue_ids = self._open_issue_ids(goal.novel_id)
            outcome = self.quality.repair(issue_ids=issue_ids,
                                          idempotency_key=step.idempotency_key)
            return outcome, "repair", outcome.usage
        if action == "verify_repair":
            issue_ids = tuple(str(value) for value in (inputs.get("issue_ids") or ()))
            if not issue_ids:
                issue_ids = self._open_issue_ids(goal.novel_id)
            outcome = self.quality.verify(issue_ids=issue_ids)
            return outcome, "verification", outcome.usage
        if action == "request_accept":
            # Agent 只产生 approval 请求；实际接受必须由作者批准后的 accept_revision 执行。
            # V4.0.2 PB-2：作者批准后这一步才真正执行，此时必须记录**被批准的 approval_id**
            # （success_criteria = approval_recorded；批准证据在验证之前不得丢失）。
            return {"approval_id": str(approved_ids.get(step.step_id) or ""),
                    "action": "request_accept", "node_id": node_id,
                    "step_id": step.step_id}, "approval", {}
        if action == "accept_revision":
            outcome = self.editor.accept(
                node_id=node_id, revision=int(inputs.get("revision") or 0) or None,
                expected_revision=step.expected_revision,
                idempotency_key=step.idempotency_key,
                reason=str(inputs.get("reason") or "agent approved accept"))
            return outcome, "edit", outcome.usage
        if action == "validate_delivery":
            outcome = self.delivery.validate(
                selection_mode=str(inputs.get("selection_mode") or "accepted"),
                profile=str(inputs.get("profile") or "author"),
                formats=tuple(str(value) for value in
                              (inputs.get("formats") or ("json",))))
            return outcome, "delivery", {}
        if action == "deliver":
            outcome = self.delivery.deliver(
                selection_mode=str(inputs.get("selection_mode") or "accepted"),
                profile=str(inputs.get("profile") or "author"),
                formats=tuple(str(value) for value in
                              (inputs.get("formats") or ("json",))),
                idempotency_key=step.idempotency_key)
            return outcome, "delivery", {}
        raise AgentPlanInvalid(f"未实现的分发：{action}")

    # ---------------------------------------------------------------- 辅助
    def _open_issue_ids(self, novel_id: str) -> tuple[str, ...]:
        snapshot = self.read.snapshot(novel_id)
        return tuple(str(row.get("issue_id") or "")
                     for row in snapshot.open_issues if row.get("issue_id"))

    def _skip_reason(self, step: AgentStep, goal: AgentGoal) -> str:
        """§42 / §52：没有可修复的 open issue 时，修复类步骤跳过（不是失败）。"""

        if step.action not in ("plan_repair", "repair", "verify_repair"):
            return ""
        issue_ids = tuple(str(value) for value in (step.inputs.get("issue_ids") or ()))
        if issue_ids:
            return ""
        if self._open_issue_ids(goal.novel_id):
            return ""
        return "没有可自动修复的 open issue（质量结论为空或已通过）"

    def _approval_request(self, goal: AgentGoal, plan: AgentPlan, step: AgentStep,
                          run: AgentRun) -> AgentApprovalRequest:
        node_id = str(step.target.get("node_id") or step.target.get("parent_id") or "")
        before: dict[str, Any] = {}
        node = self.editor.node(node_id) if node_id else None
        if node is not None:
            before = node.as_dict()
        snapshot = self.read.snapshot(goal.novel_id)
        revisions = {node_id: snapshot.revision_of(node_id)} if node_id else {}
        return AgentApprovalRequest(
            action=step.action, target=dict(step.target),
            reason=f"Agent 计划执行 protected action：{step.action}",
            before=before, proposed_after=dict(step.inputs),
            affected_nodes=tuple(sorted({node_id} - {""})),
            quality_summary=dict(snapshot.quality_summary),
            risk="structural" if str(step.target.get("node_type") or "")
            in ("story_arc", "structural_unit", "world", "premise", "theme")
            else "content",
            revision_refs=revisions, session_id=run.session_id,
            plan_id=plan.plan_id, plan_revision=plan.plan_revision,
            step_id=step.step_id)

    def _revision_conflict(self, step: AgentStep) -> AgentRevisionConflict | None:
        node_id = str(step.target.get("node_id") or "")
        if not node_id or step.expected_revision is None:
            return None
        node = self.editor.node(node_id)
        if node is None:
            return AgentRevisionConflict(f"目标节点不存在：{node_id}",
                                         step_id=step.step_id,
                                         details={"node_id": node_id})
        if int(node.revision) != int(step.expected_revision):
            return AgentRevisionConflict(
                f"计划基于 r{step.expected_revision}，当前是 r{node.revision}",
                step_id=step.step_id,
                details={"node_id": node_id,
                         "expected_revision": int(step.expected_revision),
                         "current_revision": int(node.revision)})
        return None

    def _current_revision(self, step: AgentStep, *, fallback: int = 0) -> int:
        node_id = str(step.target.get("node_id") or "")
        if not node_id:
            return int(fallback)
        node = self.editor.node(node_id)
        if node is not None:
            return int(node.revision)
        return int(fallback)

    @staticmethod
    def _requested_fields(step: AgentStep) -> tuple[str, ...]:
        inputs = dict(step.inputs or {})
        if step.action == "patch_node":
            return tuple(sorted(str(key) for key in (inputs.get("changes") or {})))
        if step.action == "rewrite_node":
            return tuple(str(value) for value in (inputs.get("target_fields") or ()))
        return ()

    @staticmethod
    def _result_refs(outcome: Any) -> dict[str, Any]:
        refs: dict[str, Any] = {}
        node = getattr(outcome, "node", None)
        if node is not None:
            refs["node"] = node.as_dict()
        for key in ("node_id", "revision", "report_id", "status", "snapshot_id",
                    "manifest_id"):
            value = getattr(outcome, key, None)
            if value not in (None, "", 0):
                refs[key] = value
        verification = getattr(outcome, "verification", None)
        if isinstance(verification, Mapping) and verification:
            refs["verification"] = dict(verification)
        if isinstance(outcome, Mapping):
            for key in ("approval_id", "status", "steps", "issue_ids", "target_nodes"):
                if key in outcome:
                    refs[key] = outcome[key]
        return refs

    def _checkpoint(self, run: AgentRun, plan: AgentPlan, step: AgentStep | None,
                    budget: AgentBudget, completed: set[str]) -> AgentCheckpoint:
        next_sequence = int(step.sequence) if step is not None else len(plan.steps) + 1
        revisions: dict[str, int] = {}
        for result in run.step_results:
            if result.changed_nodes and result.revision_after:
                for node_id in result.changed_nodes:
                    revisions[node_id] = int(result.revision_after)
        return AgentCheckpoint(session_id=run.session_id, plan_id=plan.plan_id,
                               plan_revision=plan.plan_revision, run_id=run.run_id,
                               status=run.status,
                               next_step_sequence=next_sequence,
                               completed_steps=tuple(sorted(completed)),
                               approved_steps=tuple(sorted(completed)),
                               budget_used=budget.as_dict(), revision_refs=revisions,
                               stop_reason=run.stop_reason)

    def _stop(self, run: AgentRun, plan: AgentPlan, step: AgentStep | None,
              budget: AgentBudget, *, status: str, reason: str, error_code: str,
              approvals: list[AgentApprovalRequest]) -> ExecutionOutcome:
        run.status = status
        run.finished_at = utc_now()
        run.stop_reason = reason
        run.usage = budget.as_dict()
        completed = {row.step_id for row in run.step_results
                     if row.status == "completed"}
        checkpoint = self._checkpoint(run, plan, step, budget, completed)
        self.checkpoints.save(checkpoint)
        return ExecutionOutcome(
            run=run, checkpoint=checkpoint, status=status, stop_reason=reason,
            approvals=approvals,
            error=({"code": error_code, "message": reason} if error_code else {}),
            needs_human_review=status == "needs_human_review")


__all__ = ["AgentExecutor", "ExecutionOutcome", "HUMAN_REVIEW_CODES",
           "REVISION_CONFLICT_CODES"]
