"""AgentService（V4-11 §9、§32、§64）：Agent 与已有 Application 能力的组合根。

```text
agent core（contracts/planner/executor/verifier/registry）
        ↓ 只认识 agent.ports 的窄 Protocol
application.services.agent（本模块）
        ↓ Application-backed Port Adapters
BlueprintService / EditorService / ReviewService / ExportService
```

因此：

```text
· agent 不 import application；application 的**本模块**依赖 agent public contract
· REST / MCP / UI 只调用 AgentService（接口层不接触 planner / executor internals）
· Agent 数据（session / run / plan / checkpoint / audit）是 orchestration metadata
```
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

from novelforge.agent import (
    AgentApprovalDecision,
    AgentApprovalStale,
    AgentCancelled,
    AgentBudget,
    AgentContextSnapshot,
    AgentExecutor,
    AgentGoal,
    AgentNotFound,
    AgentPlan,
    AgentPlanInvalid,
    AgentPolicy,
    AgentResult,
    AgentRun,
    AgentSessionRecord,
    AgentSessionStore,
    AgentStep,
    AgentVerifier,
    CheckpointStore,
    HeuristicPlanner,
    ModelPlanner,
    default_planner,
    validate_plan,
)
from novelforge.agent.audit import AgentAuditLog
from novelforge.agent.ports import (
    DeliveryOutcome,
    EditOutcome,
    GenerationOutcome,
    NodeRef,
    QualityOutcome,
    RepairOutcome,
)

from .facade import ApplicationServices, application_services


def _node_ref(payload: Mapping[str, Any]) -> NodeRef:
    node = dict(payload.get("node") or payload or {})
    return NodeRef(node_id=str(node.get("node_id") or ""),
                   node_type=str(node.get("node_type") or ""),
                   revision=int(node.get("revision") or 0),
                   status=str(node.get("status") or ""),
                   parent_id=str(node.get("parent_id") or ""),
                   quality_status=str(node.get("quality_status") or ""))


# --------------------------------------------------------------------- Ports
class ApplicationReadPort:
    """只读状态快照（§27）：不暴露 repository / 文件路径。"""

    def __init__(self, services: ApplicationServices) -> None:
        self.services = services

    def snapshot(self, novel_id: str) -> AgentContextSnapshot:
        services = self.services
        view = services.export.blueprint_view(selection_mode="current")
        nodes = [dict(row) for row in ((view.get("blueprint") or {}).get("nodes") or [])]
        revisions = {str(row.get("node_id")): int(row.get("revision") or 0)
                     for row in nodes}
        node_types = {str(row.get("node_id")): str(row.get("node_type") or "")
                      for row in nodes}
        node_status = {str(row.get("node_id")): str(row.get("status") or "")
                       for row in nodes}
        parents = {str(row.get("node_id")): str(row.get("parent_id") or "")
                   for row in nodes}
        accepted = tuple(sorted(node_id for node_id, status in node_status.items()
                                if status == "accepted"))
        report = dict(services.review.latest_report() or {})
        issues = tuple(dict(row) for row in services.review.list_issues(status="open"))
        return AgentContextSnapshot(
            novel_id=novel_id, blueprint_revisions=revisions, node_types=node_types,
            node_status=node_status, parent_ids=parents, accepted_nodes=accepted,
            quality_summary={"status": str(report.get("status") or "unevaluated"),
                             "issues": len(issues),
                             **dict(services.review.stats() or {})},
            open_issues=issues,
            delivery_readiness={"snapshots":
                                len(services.export.delivery_snapshots() or [])},
            review_state={"reviews": len(services.editor.reviews() or [])})

    def node(self, node_id: str) -> NodeRef | None:
        try:
            payload = self.services.editor.get_node(node_id)
        except Exception:  # noqa: BLE001 - 不存在即 None（调用方按 code 处理）
            return None
        return _node_ref(payload)


class ApplicationGenerationPort:
    """生成能力（§32）：只经 BlueprintService。"""

    def __init__(self, services: ApplicationServices) -> None:
        self.services = services

    def generate(self, *, task: str, parent_id: str = "", index: int = 0,
                 sequence: int = 0, instruction: str = "", unit_type: str = "",
                 idempotency_key: str = "") -> GenerationOutcome:
        if self.services.blueprint is None:
            raise AgentPlanInvalid("当前未配置模型能力（GENERATION_UNAVAILABLE）")
        task_input: dict[str, Any] = {}
        if instruction:
            task_input["task"] = instruction
        if unit_type:
            task_input["unit_type"] = unit_type
        if index:
            task_input["index"] = int(index)
        if sequence:
            task_input["sequence"] = int(sequence)
        result = self.services.blueprint.generate_task(
            task, parent_id=parent_id, idempotency_key=idempotency_key,
            sequence=int(sequence or 0), task_input=task_input)
        payload = result.as_dict()
        node = payload.get("node")
        return GenerationOutcome(
            node=_node_ref({"node": node}) if node else None,
            usage=dict(payload.get("usage") or {}), contract=str(payload.get("contract") or ""),
            warnings=tuple(str(value) for value in (payload.get("warnings") or ())))

    def regenerate(self, *, node_id: str, task: str = "",
                   expected_revision: int | None = None, instruction: str = "",
                   preserve: Sequence[str] = (),
                   idempotency_key: str = "") -> GenerationOutcome:
        if self.services.blueprint is None:
            raise AgentPlanInvalid("当前未配置模型能力（GENERATION_UNAVAILABLE）")
        resolved_task = str(task or "")
        if not resolved_task:
            # 任务名 = 节点类型（generation task 与 node_type 同名）
            node = self.node(node_id)
            resolved_task = str(node.node_type if node is not None else "")
        if not resolved_task:
            raise AgentPlanInvalid("regenerate 需要 task 或可解析的节点类型")
        payload = self.services.blueprint.regenerate(
            task=resolved_task, node_id=node_id, expected_revision=expected_revision,
            preserve=tuple(preserve), idempotency_key=idempotency_key).as_dict()
        node = payload.get("node")
        return GenerationOutcome(node=_node_ref({"node": node}) if node else None,
                                 usage=dict(payload.get("usage") or {}))


class ApplicationEditorPort:
    """编辑能力（§32–§34）：只经 EditorService（append-only revision）。"""

    def __init__(self, services: ApplicationServices) -> None:
        self.services = services

    def node(self, node_id: str) -> NodeRef | None:
        try:
            payload = self.services.editor.get_node(node_id)
        except Exception:  # noqa: BLE001
            return None
        return _node_ref(payload)

    def children(self, parent_id: str, node_type: str = "") -> tuple[NodeRef, ...]:
        try:
            payload = self.services.editor.get_node(parent_id)
        except Exception:  # noqa: BLE001
            return ()
        nodes = ((payload.get("node") or {}).get("payload") or {})
        rows: list[NodeRef] = []
        for child_id in (nodes.get("child_units") or ()):
            child = self.node(str(child_id))
            if child is not None and (not node_type or child.node_type == node_type):
                rows.append(child)
        return tuple(rows)

    def patch(self, *, node_id: str, changes: Mapping[str, Any],
              expected_revision: int | None, idempotency_key: str = "",
              reason: str = "") -> EditOutcome:
        payload = self.services.editor.patch(
            node_id, dict(changes), expected_revision=expected_revision,
            reason=reason, idempotency_key=idempotency_key).as_dict()
        return EditOutcome(node_id=node_id, revision=int(payload.get("revision") or 0),
                           status=str(payload.get("status") or ""),
                           changed_fields=tuple(str(value) for value in
                                                (payload.get("changed_fields") or ())),
                           quality_status=str(payload.get("quality_status") or ""),
                           warnings=tuple(str(value) for value in
                                          (payload.get("notes") or ())))

    def rewrite(self, *, node_id: str, target_fields: Sequence[str], instruction: str,
                expected_revision: int | None, preserve_fields: Sequence[str] = (),
                idempotency_key: str = "") -> EditOutcome:
        payload = self.services.editor.rewrite(
            node_id, tuple(target_fields), instruction,
            expected_revision=expected_revision,
            preserve_fields=tuple(preserve_fields),
            idempotency_key=idempotency_key).as_dict()
        return EditOutcome(node_id=node_id, revision=int(payload.get("revision") or 0),
                           status=str(payload.get("status") or ""),
                           changed_fields=tuple(str(value) for value in
                                                (payload.get("changed_fields") or ())),
                           quality_status=str(payload.get("quality_status") or ""),
                           usage=dict(payload.get("usage") or {}),
                           warnings=tuple(str(value) for value in
                                          (payload.get("violations") or ())))

    def accept(self, *, node_id: str, revision: int | None,
               expected_revision: int | None = None, idempotency_key: str = "",
               reason: str = "") -> EditOutcome:
        payload = self.services.editor.accept(
            node_id, revision=revision, expected_revision=expected_revision,
            reason=reason, idempotency_key=idempotency_key).as_dict()
        return EditOutcome(node_id=node_id, revision=int(payload.get("revision") or 0),
                           status=str(payload.get("decision") or
                                      payload.get("status") or ""),
                           changed_fields=("status",))

    def reject(self, *, node_id: str, revision: int | None = None, reason: str = "",
               idempotency_key: str = "") -> EditOutcome:
        payload = self.services.editor.reject(node_id, revision=revision, reason=reason,
                                              idempotency_key=idempotency_key).as_dict()
        return EditOutcome(node_id=node_id, revision=int(payload.get("revision") or 0),
                           status=str(payload.get("decision") or "rejected"),
                           changed_fields=("review_status",))


class ApplicationQualityPort:
    """质量 / 修复能力（§41–§42）：只经 ReviewService / EditorService。"""

    def __init__(self, services: ApplicationServices) -> None:
        self.services = services

    def evaluate(self, *, gates: Sequence[str] = (),
                 node_ids: Sequence[str] = ()) -> QualityOutcome:
        report = self.services.review.evaluate(
            gates=tuple(gates) or None, node_ids=tuple(node_ids))
        payload = report.as_dict()
        return QualityOutcome(status=str(payload.get("status") or ""),
                              report_id=str(payload.get("report_id") or ""),
                              issues=tuple(dict(row) for row in
                                           (payload.get("issues") or ())),
                              blocker_count=len(report.blockers),
                              needs_human_review=str(payload.get("status"))
                              == "needs_human_review",
                              usage=dict(payload.get("usage") or {}))

    def plan_repair(self, *, issue_ids: Sequence[str]) -> Mapping[str, Any]:
        return dict(self.services.editor.plan_repair(
            issue_ids=tuple(issue_ids), dry_run=True) or {})

    def repair(self, *, issue_ids: Sequence[str],
               idempotency_key: str = "") -> RepairOutcome:
        payload = self.services.editor.repair(tuple(issue_ids), dry_run=False,
                                              idempotency_key=idempotency_key)
        return RepairOutcome(status=str(payload.get("status") or ""),
                             plan=dict(payload.get("plan") or {}),
                             result=dict(payload.get("result") or {}),
                             verification=dict(payload.get("verification") or {}))

    def verify(self, *, issue_ids: Sequence[str]) -> RepairOutcome:
        payload = self.services.editor.verify_repair(issue_ids=tuple(issue_ids))
        return RepairOutcome(status=str(payload.get("status") or ""),
                             verification=dict(payload))


class ApplicationDeliveryPort:
    """交付能力（§71）：只经 ExportService；默认 policy 不允许调用。"""

    def __init__(self, services: ApplicationServices) -> None:
        self.services = services

    def formats(self) -> tuple[Mapping[str, Any], ...]:
        registry = getattr(self.services.export, "exporter_registry", None)
        if registry is None:
            return ()
        return tuple(spec.as_dict() for spec in registry.specs())

    def _selection(self, selection_mode: str, profile: str,
                   formats: Sequence[str]) -> Any:
        return self.services.delivery_selection(
            selection_mode=selection_mode, profile=profile,
            formats=tuple(formats) or ("json",))

    def validate(self, *, selection_mode: str = "accepted", profile: str = "author",
                 formats: Sequence[str] = ("json",)) -> DeliveryOutcome:
        selection = self._selection(selection_mode, profile, formats)
        payload = dict(self.services.export.validate_delivery(selection) or {})
        return DeliveryOutcome(status="validated" if payload.get("ok") else "blocked",
                               validation=payload)

    def deliver(self, *, selection_mode: str = "accepted", profile: str = "author",
                formats: Sequence[str] = ("json",),
                idempotency_key: str = "") -> DeliveryOutcome:
        selection = self._selection(selection_mode, profile, formats)
        payload = self.services.export.deliver(selection,
                                              idempotency_key=idempotency_key)
        manifest = dict(payload.get("manifest") or {})
        return DeliveryOutcome(
            status=str(payload.get("status") or ""),
            snapshot_id=str(payload.get("snapshot_id") or ""),
            manifest_id=str(manifest.get("manifest_id") or ""),
            validation=dict(payload.get("validation") or {}),
            artifacts=tuple(dict(row) for row in (payload.get("artifacts") or ())),
            notes=tuple(str(value) for value in (payload.get("notes") or ())))


# ------------------------------------------------------------------ Service
@dataclass
class _AgentRuntime:
    """一次服务实例持有的 Port / 执行器（构造一次，多次运行复用）。"""

    read: ApplicationReadPort
    generation: ApplicationGenerationPort
    editor: ApplicationEditorPort
    quality: ApplicationQualityPort
    delivery: ApplicationDeliveryPort
    executor: AgentExecutor


class AgentService:
    """Agent Mode 的唯一 Application 入口（§64）。"""

    def __init__(self, project_root: Path | str, novel_id: str, *,
                 services: ApplicationServices | None = None,
                 gateway: Any = None, memory: Any = None,
                 planner: Any = None, planner_model: Any = None) -> None:
        self.project_root = Path(project_root)
        self.novel_id = str(novel_id or "").strip()
        if not self.novel_id:
            raise AgentPlanInvalid("AgentService 需要显式 novel_id")
        self.services = services or application_services(
            self.project_root, self.novel_id, gateway=gateway, memory=memory)
        self.store = AgentSessionStore(self.project_root)
        self.checkpoints = CheckpointStore(self.project_root, self.novel_id)
        self.planner = planner or (ModelPlanner(planner_model) if planner_model
                                   else default_planner())
        read = ApplicationReadPort(self.services)
        generation = ApplicationGenerationPort(self.services)
        editor = ApplicationEditorPort(self.services)
        quality = ApplicationQualityPort(self.services)
        delivery = ApplicationDeliveryPort(self.services)
        self.runtime = _AgentRuntime(
            read=read, generation=generation, editor=editor, quality=quality,
            delivery=delivery,
            executor=AgentExecutor(
                read=read, generation=generation, editor=editor, quality=quality,
                delivery=delivery,
                verifier=AgentVerifier(read=read, editor=editor, quality=quality,
                                       delivery=delivery, generation=generation),
                audit_factory=lambda novel_id, session_id:
                    AgentAuditLog(self.project_root, novel_id, session_id),
                checkpoints=self.checkpoints))

    # --------------------------------------------------------------- 规划
    def plan(self, goal: AgentGoal | Mapping[str, Any], *,
             policy: AgentPolicy | Mapping[str, Any] | None = None,
             dry_run: bool = True) -> dict[str, Any]:
        """生成有界计划（§29 plan preview：dry_run 时 0 mutation）。"""

        resolved_goal = goal if isinstance(goal, AgentGoal) else AgentGoal.from_dict(goal)
        if str(resolved_goal.novel_id) != self.novel_id:
            raise AgentPlanInvalid(
                f"goal.novel_id({resolved_goal.novel_id}) 与 AgentService({self.novel_id}) 不一致")
        resolved_policy = (policy if isinstance(policy, AgentPolicy)
                           else AgentPolicy.from_dict(policy))
        snapshot = self.runtime.read.snapshot(self.novel_id)
        plan = self.planner.plan(resolved_goal, snapshot, resolved_policy)
        validate_plan(plan, goal=resolved_goal, policy=resolved_policy,
                      snapshot=snapshot)
        session = AgentSessionRecord(
            novel_id=self.novel_id, goal=resolved_goal.as_dict(),
            policy=resolved_policy.as_dict(), status="planning")
        session.set_plan(plan)
        session.checkpoint = {"snapshot_digest": snapshot.digest,
                              "plan_revision": plan.plan_revision}
        self.store.save_session(session)
        self._audit(session.session_id).record_entry(
            session_id=session.session_id, operation="plan_created",
            goal_id=resolved_goal.goal_id, plan_id=plan.plan_id,
            plan_revision=plan.plan_revision, status="planning",
            business_result_refs={"steps": len(plan.steps),
                                  "mutations": plan.mutations})
        return {"session_id": session.session_id, "status": "planning",
                "dry_run": bool(dry_run), "mutations": 0,
                "plan": plan.as_dict(), "policy": resolved_policy.as_dict(),
                "snapshot": {"digest": snapshot.digest,
                             "nodes": len(snapshot.blueprint_revisions),
                             "quality": dict(snapshot.quality_summary)},
                "preview": self._preview(plan)}

    # --------------------------------------------------------------- 执行
    def start(self, session_id: str, *, max_batch_steps: int | None = None,
              policy: AgentPolicy | Mapping[str, Any] | None = None
              ) -> dict[str, Any]:
        return self._execute(session_id, approved_steps=(),
                             max_batch_steps=max_batch_steps, fresh_run=True,
                             policy_override=policy)

    def resume(self, session_id: str, *, max_batch_steps: int | None = None
               ) -> dict[str, Any]:
        """续跑（§56、§84–§85）：先校验 revision drift，再继续未完成步骤。"""

        session = self.store.load_session(self.novel_id, session_id)
        if session.status == "cancelled":
            # §61：取消是终态；继续执行必须重新规划（resume 不会悄悄复活）
            raise AgentCancelled(
                "该 session 已取消：如需继续请基于当前状态重新 plan",
                session_id=session_id, details={"status": session.status})
        plan = session.plan_obj
        if plan is None:
            raise AgentPlanInvalid("session 还没有计划")
        checkpoint = self.checkpoints.load(session_id)
        if checkpoint is None:
            return self._execute(session_id, approved_steps=session.approved_step_ids(),
                                 max_batch_steps=max_batch_steps, fresh_run=True)
        drift = self._revision_drift(checkpoint.revision_refs)
        if drift:
            session.status = "paused"
            session.stop_reason = "revision drift detected on resume"
            session.error_code = "AGENT_REVISION_CONFLICT"
            session.checkpoint = checkpoint.as_dict()
            self.store.save_session(session)
            return self._result(session, status="paused", stop_reason=session.stop_reason,
                               error_code="AGENT_REVISION_CONFLICT",
                               details={"drift": drift})
        return self._execute(session_id, approved_steps=session.approved_step_ids(),
                             max_batch_steps=max_batch_steps, fresh_run=False,
                             start_sequence=checkpoint.next_step_sequence,
                             completed=checkpoint.completed_steps,
                             existing_run_id=checkpoint.run_id)

    def run_next_step(self, session_id: str) -> dict[str, Any]:
        """§99：一次只跑一步（长流程用；每步之后 checkpoint）。"""

        return self._execute(session_id, approved_steps=(), max_batch_steps=1,
                             fresh_run=False, reuse_run=True)

    # -------------------------------------------------------------- 审批
    def approve(self, session_id: str, approval_id: str, *, actor: str = "author",
                reason: str = "", decision: str = "approved"
                ) -> dict[str, Any]:
        return self._decide(session_id, approval_id, decision=decision, actor=actor,
                            reason=reason)

    def reject(self, session_id: str, approval_id: str, *, actor: str = "author",
               reason: str = "") -> dict[str, Any]:
        return self._decide(session_id, approval_id, decision="rejected", actor=actor,
                            reason=reason)

    def cancel(self, session_id: str, *, reason: str = "author cancel"
               ) -> dict[str, Any]:
        """§61：诚实语义 —— 标记 cancel requested，并在下一个步骤前停止。"""

        session = self.store.load_session(self.novel_id, session_id)
        session.status = "cancelled"
        session.stop_reason = (f"cancel requested（将在当前步骤结束后停止，"
                               f"不会中断已经发出的请求）：{reason}")
        session.error_code = "AGENT_CANCELLED"
        checkpoint = self.checkpoints.load(session_id)
        if checkpoint is not None:
            session.checkpoint = checkpoint.as_dict()
        self.store.save_session(session)
        self._audit(session_id).record_entry(
            session_id=session_id, operation="cancel_requested",
            goal_id=str(dict(session.goal).get("goal_id") or ""),
            status="cancelled", business_result_refs={"reason": reason})
        return {"session_id": session_id, "status": "cancelled",
                "stop_reason": session.stop_reason,
                "semantics": "将在当前步骤结束后停止（不会中断已经发出的模型请求）"}

    # --------------------------------------------------------------- 查询
    def status(self, session_id: str) -> dict[str, Any]:
        session = self.store.load_session(self.novel_id, session_id)
        runs = [run.as_dict() for run in
                self.store.runs_for(self.novel_id, session_id)]
        checkpoint = self.checkpoints.load(session_id)
        return {"session": session.as_dict(), "runs": runs,
                "checkpoint": checkpoint.as_dict() if checkpoint else {},
                "pending_approvals": session.pending_approvals,
                "audit": self._audit(session_id).records()}

    def history(self, *, limit: int = 20) -> list[dict[str, Any]]:
        return self.store.list_sessions(self.novel_id)[: max(1, int(limit))]

    def audit_records(self, session_id: str) -> list[dict[str, Any]]:
        return self._audit(session_id).records()

    # ---------------------------------------------------------------- 内部
    def _execute(self, session_id: str, *, approved_steps: Sequence[str],
                 max_batch_steps: int | None, fresh_run: bool,
                 start_sequence: int = 0, completed: Sequence[str] = (),
                 existing_run_id: str = "", reuse_run: bool = False,
                 policy_override: AgentPolicy | Mapping[str, Any] | None = None
                 ) -> dict[str, Any]:
        session = self.store.load_session(self.novel_id, session_id)
        plan = session.plan_obj
        if plan is None:
            raise AgentPlanInvalid("session 还没有计划")
        goal = session.goal_obj
        policy = (policy_override if isinstance(policy_override, AgentPolicy)
                  else AgentPolicy.from_dict(policy_override)
                  if policy_override is not None else session.policy_obj)
        snapshot = self.runtime.read.snapshot(self.novel_id)
        # 计划按其**规划时**的策略校验；运行期 policy override 只影响预算 / 审批边界
        validate_plan(plan, goal=goal, policy=session.policy_obj, snapshot=snapshot)

        if reuse_run and existing_run_id:
            run = self.store.load_run(self.novel_id, session_id, existing_run_id)
        else:
            run = AgentRun(session_id=session_id, plan_id=plan.plan_id,
                           plan_revision=plan.plan_revision)
        budget = AgentBudget()
        session.status = "executing"
        outcome = self.runtime.executor.execute(
            goal=goal, policy=policy, plan=plan, run=run, budget=budget,
            approved_steps=approved_steps, start_sequence=start_sequence,
            completed_steps=completed, max_batch_steps=max_batch_steps)
        self.store.save_run(self.novel_id, outcome.run)
        session.status = outcome.status
        session.stop_reason = outcome.stop_reason
        session.error_code = str(dict(outcome.error).get("code") or "")
        session.budget = budget.as_dict()
        session.checkpoint = outcome.checkpoint.as_dict()
        for request in outcome.approvals:
            session.add_approval(request)
        if outcome.run.run_id not in session.run_ids:
            session.run_ids.append(outcome.run.run_id)
        self.store.save_session(session)
        return self._result(session, status=outcome.status,
                            stop_reason=outcome.stop_reason,
                            error_code=session.error_code,
                            run=outcome.run, approvals=outcome.approvals,
                            needs_human_review=outcome.needs_human_review,
                            budget=budget)

    def _decide(self, session_id: str, approval_id: str, *, decision: str,
                actor: str, reason: str) -> dict[str, Any]:
        session = self.store.load_session(self.novel_id, session_id)
        request_row = next((row for row in session.approvals
                           if str(row.get("approval_id")) == str(approval_id)), None)
        if request_row is None:
            raise AgentNotFound(f"未知 approval：{approval_id}", session_id=session_id)
        drift = self._revision_drift({str(key): int(value) for key, value in
                                      dict(request_row.get("revision_refs") or {}).items()})
        if drift and bool(request_row.get("expires_if_revision_changes", True)):
            session.status = "needs_human_review"
            session.error_code = "AGENT_APPROVAL_STALE"
            session.stop_reason = "approval 已过期（绑定的 revision 已变化）"
            self.store.save_session(session)
            self._audit(session_id).record_entry(
                session_id=session_id, operation="approval_stale",
                step_id=str(request_row.get("step_id") or ""), status="stale",
                error_code="AGENT_APPROVAL_STALE",
                business_result_refs={"drift": drift})
            raise AgentApprovalStale(
                "approval 已过期：绑定的 revision 已经变化，请基于最新状态重新规划",
                session_id=session_id, step_id=str(request_row.get("step_id") or ""),
                details={"drift": drift})
        record = AgentApprovalDecision(approval_id=approval_id, decision=decision,
                                       actor=actor, reason=reason)
        session.add_decision(record.as_dict())
        self.store.save_session(session)
        self._audit(session_id).record_entry(
            session_id=session_id, operation=f"approval_{decision}",
            step_id=str(request_row.get("step_id") or ""), status=decision,
            business_result_refs={"approval_id": approval_id, "reason": reason})
        if decision != "approved":
            session.status = "paused"
            session.stop_reason = f"approval {decision}"
            self.store.save_session(session)
            return self._result(session, status="paused",
                               stop_reason=session.stop_reason,
                               error_code="AGENT_APPROVAL_REJECTED")
        return self._execute(session_id, approved_steps=session.approved_step_ids(),
                             max_batch_steps=None, fresh_run=False)

    def _revision_drift(self, revision_refs: Mapping[str, int]
                        ) -> dict[str, dict[str, int]]:
        drift: dict[str, dict[str, int]] = {}
        for node_id, expected in dict(revision_refs or {}).items():
            node = self.runtime.editor.node(str(node_id))
            current = int(node.revision) if node is not None else 0
            if current != int(expected):
                drift[str(node_id)] = {"expected": int(expected), "current": current}
        return drift

    def _result(self, session: AgentSessionRecord, *, status: str, stop_reason: str,
                error_code: str = "", run: AgentRun | None = None,
                approvals: Sequence[Any] = (), needs_human_review: bool = False,
                budget: AgentBudget | None = None,
                details: Mapping[str, Any] | None = None) -> dict[str, Any]:
        plan = session.plan_obj
        steps = [row.as_dict() for row in (run.step_results if run else [])]
        completed = tuple(row["step_id"] for row in steps
                          if row.get("status") == "completed")
        pending = tuple(step.step_id for step in (plan.steps if plan else ())
                        if step.step_id not in set(completed))
        changed = tuple(sorted({node for row in steps
                                for node in (row.get("changed_nodes") or ())}))
        revisions: dict[str, int] = {}
        for row in steps:
            if not row.get("revision_after"):
                continue
            for node_id in (row.get("changed_nodes") or ()):
                revisions[str(node_id)] = int(row["revision_after"])
        quality: dict[str, Any] = {}
        for row in steps:
            refs = dict(row.get("result_refs") or {})
            if row.get("action") == "evaluate" and refs.get("report_id"):
                quality = {"report_id": refs.get("report_id"),
                           "status": refs.get("status", "")}
        errors = ([{"code": error_code, "message": stop_reason}]
                  if error_code else [])
        result = AgentResult(
            session_id=session.session_id,
            run_id=run.run_id if run else "",
            status=status, ok=status == "completed",
            goal=dict(session.goal), plan=dict(session.plan),
            completed_steps=completed, pending_steps=pending,
            changed_nodes=changed, new_revisions=revisions,
            quality_summary=quality,
            approvals_required=tuple(row.as_dict() if hasattr(row, "as_dict")
                                     else dict(row) for row in approvals),
            usage=(budget.as_dict() if budget is not None else dict(session.budget)),
            warnings=tuple(str(row.get("message") or "") for row in steps
                           if row.get("status") == "needs_human_review"),
            errors=tuple(errors), stop_reason=stop_reason,
            needs_human_review=bool(needs_human_review
                                    or status == "needs_human_review"),
            step_results=tuple(steps))
        payload = result.as_dict()
        payload["pending_approvals"] = session.pending_approvals
        if details:
            payload["details"] = dict(details)
        return payload

    @staticmethod
    def _preview(plan: AgentPlan) -> list[dict[str, Any]]:
        return [{"step_id": step.step_id, "sequence": step.sequence,
                 "action": step.action, "target": dict(step.target),
                 "mutation": step.mutation,
                 "requires_approval": step.requires_approval,
                 "expected_revision": step.expected_revision,
                 "success_criteria": list(step.success_criteria)}
                for step in plan.steps]

    def _audit(self, session_id: str) -> "_AuditWriter":
        return _AuditWriter(self.project_root, self.novel_id, session_id)


class _AuditWriter:
    """小适配器：让 AgentService 用关键字参数写审计（保持调用点简洁）。"""

    def __init__(self, project_root: Path | str, novel_id: str, session_id: str) -> None:
        self.log = AgentAuditLog(project_root, novel_id, session_id)
        self.session_id = session_id

    def record_entry(self, *, session_id: str = "", operation: str = "",
                     goal_id: str = "", run_id: str = "", plan_id: str = "",
                     plan_revision: int = 1, step_id: str = "",
                     target: Mapping[str, Any] | None = None, status: str = "",
                     request_id: str = "", error_code: str = "",
                     business_result_refs: Mapping[str, Any] | None = None
                     ) -> dict[str, Any]:
        from novelforge.agent.audit import AgentAuditRecord

        return self.log.record(AgentAuditRecord(
            session_id=session_id or self.session_id, operation=operation,
            goal_id=goal_id, run_id=run_id, plan_id=plan_id,
            plan_revision=plan_revision, step_id=step_id, target=dict(target or {}),
            status=status, request_id=request_id, error_code=error_code,
            business_result_refs=dict(business_result_refs or {})))

    def records(self) -> list[dict[str, Any]]:
        return self.log.records()


def agent_service(project_root: Path | str, novel_id: str, *, gateway: Any = None,
                  memory: Any = None, planner: Any = None,
                  planner_model: Any = None,
                  services: ApplicationServices | None = None) -> AgentService:
    return AgentService(project_root, novel_id, gateway=gateway, memory=memory,
                        planner=planner, planner_model=planner_model, services=services)


def session_novel_id(project_root: Path | str, session_id: str) -> str:
    """从已存 session 解析 novel_id（接口层不拼路径、不猜“当前作品”，§97）。"""

    from novelforge.persistence.paths import agent_sessions_root

    path = agent_sessions_root(project_root) / f"{session_id}.json"
    if not path.is_file():
        return ""
    row = json.loads(path.read_text(encoding="utf-8"))
    return str(row.get("novel_id") or "")


__all__ = [
    "AgentService", "ApplicationDeliveryPort", "ApplicationEditorPort",
    "ApplicationGenerationPort", "ApplicationQualityPort", "ApplicationReadPort",
    "HeuristicPlanner", "agent_service",
]
