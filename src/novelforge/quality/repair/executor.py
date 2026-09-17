"""Repair Executor（V4-05 §33–§36、§58、§65–§66）。

铁律：

```text
Repair → Generation Public Contract（`regenerate`），Executor 不自己造生成逻辑（§33）
任何修复都产生**新 revision**，禁止原地修改（§35）
accepted 节点不被静默覆盖：旧 revision 永久可读（§36）
expected_revision 冲突必须在**调用模型之前**发现 → 0 次模型调用（§35 / §65）
同一 idempotency_key 重放不产生第二个 revision（§66）
```
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping, Sequence

from novelforge.blueprint import BlueprintRepository
from novelforge.core.revision import RevisionConflict, check_expected_revision

from ..aggregation import merge_usage, normalize_usage
from ..errors import QualityError, QualityScopeError
from ..store import QualityStore
from .contracts import RepairPlan, RepairResult
from .planner import payload_fields


class PreserveViolationError(QualityError):
    """模型输出改动了 preserve 字段（§30：preserve 是硬约束）。"""

    code = "REPAIR_PRESERVE_VIOLATION"


class RepairExecutor:
    """执行 RepairPlan（只经 generation 公开契约产生新 revision）。"""

    def __init__(self, project_root: Path | str, novel_id: str, *,
                 generation: Any, repository: BlueprintRepository | None = None,
                 store: QualityStore | None = None) -> None:
        if not str(novel_id or "").strip():
            raise QualityScopeError("RepairExecutor 需要显式 novel_id")
        if generation is None:
            raise QualityScopeError(
                "RepairExecutor 需要 generation（repair 不自行生成内容）")
        self.project_root = Path(project_root)
        self.novel_id = str(novel_id)
        self.generation = generation
        self.repository = repository or BlueprintRepository(self.project_root,
                                                            self.novel_id)
        self.store = store or QualityStore(self.project_root, self.novel_id)

    # ------------------------------------------------------------------ 执行
    def execute(self, plan: RepairPlan, *,
                expected_revisions: Mapping[str, int] | None = None,
                idempotency_key: str = "", model_policy: Any = None,
                dry_run: bool | None = None) -> RepairResult:
        if plan.novel_id != self.novel_id:
            raise QualityScopeError(
                f"拒绝跨作品执行：{plan.novel_id} != {self.novel_id}")
        resolved_dry_run = plan.dry_run if dry_run is None else bool(dry_run)

        if resolved_dry_run:
            return RepairResult(
                plan_id=plan.plan_id, novel_id=self.novel_id, status="planned",
                dry_run=True, resolved_issue_ids=tuple(plan.issue_ids),
                notes=("dry run：未写入任何 revision，也未调用模型（§58）",
                       f"预计模型任务数：{plan.estimated_model_calls}"))

        if plan.status != "planned":
            return RepairResult(
                plan_id=plan.plan_id, novel_id=self.novel_id,
                status="needs_human_review" if plan.steps or plan.needs_human_review
                else "empty",
                notes=tuple([f"plan status = {plan.status}",
                             *plan.conflicts, *plan.human_review_reasons]))

        # ---- 预检（在任何模型调用之前）：replay 优先，其次 revision 冲突 -------
        preflight: list[dict[str, Any]] = []
        for step in plan.steps:
            key = self._step_key(plan, step.step_id, idempotency_key)
            existing = (self.repository.find_by_idempotency(key)
                        if key else None)
            expected = self._expected(step, expected_revisions)
            if existing is None:
                check_expected_revision(
                    expected,
                    self.repository.current_revision(step.node_id) or None,
                    artifact_id=step.node_id)
            preflight.append({"step": step, "key": key, "existing": existing,
                              "expected": expected})

        # ---- 执行 ------------------------------------------------------------
        before_revisions: dict[str, int] = {}
        after_revisions: dict[str, int] = {}
        applied: list[Mapping[str, Any]] = []
        replayed: list[Mapping[str, Any]] = []
        blocked: list[Mapping[str, Any]] = []
        usage = merge_usage()
        resolved: set[str] = set()

        for row in preflight:
            step = row["step"]
            current = self.repository.current_revision(step.node_id) or 0
            before_revisions[step.node_id] = int(row["expected"] or current)
            if row["existing"] is not None:
                node = row["existing"]
                after_revisions[step.node_id] = int(node.revision)
                resolved.update(step.must_resolve)
                replayed.append({"step_id": step.step_id, "node_id": step.node_id,
                                 "task": step.task, "revision": int(node.revision),
                                 "idempotency_key": row["key"],
                                 "reason": "IDEMPOTENT_REPLAY",
                                 "model_calls": 0})
                continue
            try:
                result = self._run_step(plan=plan, step=step, key=row["key"],
                                        model_policy=model_policy)
            except RevisionConflict:
                # §65：并发写入造成的 revision 冲突必须原样暴露（不吞掉）
                raise
            except PreserveViolationError as exc:
                # §30：preserve 是硬约束 —— 违反必须上报，不得静默接受
                blocked.append({"step_id": step.step_id, "node_id": step.node_id,
                                "task": step.task, "error": exc.code,
                                "message": str(exc)[:400],
                                "fields": list(exc.details.get("fields") or ()),
                                "model_calls": 1})
                after_revisions[step.node_id] = int(
                    self.repository.current_revision(step.node_id) or 0)
                continue
            except Exception as exc:  # noqa: BLE001 - 失败必须记录为 blocked step
                blocked.append({"step_id": step.step_id, "node_id": step.node_id,
                                "task": step.task,
                                "error": type(exc).__name__,
                                "message": str(exc)[:400],
                                "model_calls": 0})
                continue
            after_revisions[step.node_id] = int(result.revision)
            step_usage = normalize_usage(dict(result.usage or {}))
            usage = merge_usage(usage, step_usage)
            resolved.update(step.must_resolve)
            applied.append({"step_id": step.step_id, "node_id": step.node_id,
                            "node_type": step.node_type, "task": step.task,
                            "idempotency_key": row["key"],
                            "before_revision": before_revisions[step.node_id],
                            "after_revision": int(result.revision),
                            "contract": result.contract,
                            "request_id": result.request_id,
                            "model": result.model, "provider": result.provider,
                            "source_ids": list(result.source_ids),
                            "usage": step_usage,
                            "model_calls": int(step_usage.get("calls") or 1),
                            "warnings": list(result.warnings)})

        if blocked and not applied and not replayed:
            status = "needs_human_review"
        elif blocked:
            status = "partial"
        elif applied:
            status = "applied"
        elif replayed:
            status = "idempotent_replay"
        else:
            status = "empty"

        result = RepairResult(
            plan_id=plan.plan_id, novel_id=self.novel_id, status=status,
            applied_steps=tuple(applied), replayed_steps=tuple(replayed),
            blocked_steps=tuple(blocked),
            before_revisions=dict(sorted(before_revisions.items())),
            after_revisions=dict(sorted(after_revisions.items())),
            resolved_issue_ids=tuple(sorted(resolved)), usage=usage,
            notes=(f"model_calls={sum(int(row['model_calls']) for row in applied)}",))
        self._record_history(plan, result)
        return result

    # ------------------------------------------------------------------ 内部
    def _run_step(self, *, plan: RepairPlan, step: Any, key: str,
                  model_policy: Any) -> Any:
        node = self.repository.get_current(step.node_id)
        fields = set(payload_fields(node)) if node is not None else set()
        preserve = tuple(field for field in step.preserve if field in fields)
        task_input = {
            "task": step.reason or "修复质量问题",
            "repair": {"plan_id": plan.plan_id, "issue_ids": list(step.issue_ids),
                       "reason": step.reason, "preserve": list(preserve),
                       "allow_change": list(step.allow_change),
                       "constraints": list(step.constraints)},
            "preserve": list(preserve),
            "allow_change": list(step.allow_change),
        }
        result = self.generation.regenerate(
            task=step.task, node_id=step.node_id,
            expected_revision=step.expected_revision, preserve=preserve,
            task_input=task_input, idempotency_key=key, model_policy=model_policy)
        written = (self.repository.get_revision(step.node_id, int(result.revision))
                   if result.revision else None)
        violation = self._preserve_violation(node, written, preserve)
        if violation:
            raise PreserveViolationError(
                f"{step.node_id} 的 preserve 字段被修改：{violation}",
                details={"node_id": step.node_id, "fields": violation,
                         "revision": int(result.revision)})
        return result

    @staticmethod
    def _preserve_violation(before: Any, after: Any,
                            preserve: Sequence[str]) -> list[str]:
        """对比新旧 revision 的 preserve 字段（结构 identity 不得被改写）。"""

        if before is None or not after or not preserve:
            return []

        def payload_of(node: Any) -> dict[str, Any]:
            payload = getattr(node, "payload", None)
            if hasattr(payload, "model_dump"):
                return payload.model_dump(mode="json")
            return dict(payload or {})

        old, new = payload_of(before), payload_of(after)
        return [field for field in preserve
                if old.get(field) != new.get(field)]

    @staticmethod
    def _expected(step: Any, expected_revisions: Mapping[str, int] | None) -> int:
        if expected_revisions and step.node_id in expected_revisions:
            return int(expected_revisions[step.node_id])
        return int(step.expected_revision)

    @staticmethod
    def _step_key(plan: RepairPlan, step_id: str, idempotency_key: str) -> str:
        prefix = str(idempotency_key or f"repair:{plan.plan_id}")
        return f"{prefix}:{step_id}"

    def _record_history(self, plan: RepairPlan, result: RepairResult) -> None:
        self.store.save_repair_history(plan.plan_id, {
            "plan": plan.as_dict(), "result": result.as_dict(),
            "operation": "repair.execute"})


__all__ = ["PreserveViolationError", "RepairExecutor"]
