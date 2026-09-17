"""EditorService —— Blueprint Editor 的业务入口（V4-06 §7、§28–§33、§51、§67）。

Application 层负责**组合**：

```text
application.services.editor
        ├── novelforge.editor         （编辑 / diff / restore / audit）
        ├── novelforge.generation     （AI rewrite / regenerate）
        └── novelforge.quality + repair（评估 / issue / repair / verify）
```

接口层（REST / MCP / UI / Agent）只调用本服务；不得 import editor internals、
BlueprintRepository internals、generation internals 或 quality evaluator。

质量归属（§68）：Quality 只说「有没有 issue」；**是否接受某个 revision 由作者决定**
（`EditorService.accept` / `reject`），两者不得互相替代（§69）。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from novelforge.blueprint import BlueprintRepository
from novelforge.editor import (
    BatchEditRequest,
    BlueprintEditorService,
    DiffRequest,
    EditRequest,
    EditorStore,
    RewriteRequest,
)
from novelforge.generation import BlueprintGenerationService
from novelforge.quality import QualityPolicy, QualityService
from novelforge.quality.repair import RepairPlan

from .review import QualityLoopService, ReviewService

#: 质量 issue 关联到 revision 时的标记（§29）
HISTORICAL_FLAG = "historical"


class EditorService:
    """编辑 + 质量的门面（接口层的唯一入口）。"""

    def __init__(self, project_root: Path | str, novel_id: str, *,
                 editor: BlueprintEditorService,
                 quality: QualityService | None = None,
                 review: ReviewService | None = None,
                 generation: BlueprintGenerationService | None = None,
                 repository: BlueprintRepository | None = None,
                 policy: QualityPolicy | None = None) -> None:
        self.project_root = Path(project_root)
        self.novel_id = str(novel_id)
        self.editor = editor
        self.repository = repository or editor.repository
        self.generation = generation
        self.policy = policy or QualityPolicy()
        self.quality = quality
        self.review = review

    # ================================================================= 读取
    def get_node(self, node_id: str, revision: int | None = None) -> dict[str, Any]:
        payload = self.editor.get_node(node_id, revision)
        payload["quality"] = self.get_quality(node_id, revision=revision)
        return payload

    def get_history(self, node_id: str) -> dict[str, Any]:
        history = self.editor.get_history(node_id).as_dict()
        history["quality"] = self.get_quality(node_id)
        history["repair_preview"] = self.plan_repair(node_id=node_id)
        return history

    def list_revisions(self, node_id: str) -> list[int]:
        return self.editor.list_revisions(node_id)

    def diff(self, node_id: str, *, from_revision: int, to_revision: int | None = None,
             include_quality: bool = True) -> dict[str, Any]:
        """结构化 diff；可选关联前后 issue 集合（§33：issue 来自 Quality Store）。"""

        payload = self.editor.diff(DiffRequest(
            novel_id=self.novel_id, node_id=node_id, from_revision=from_revision,
            to_revision=to_revision)).as_dict()
        if include_quality:
            payload["quality"] = self._diff_quality(node_id, payload["revision_before"],
                                                    payload["revision_after"])
        return payload

    def change_impact(self, node_id: str,
                      changed_fields: Iterable[str] = ()) -> dict[str, Any]:
        return self.editor.change_impact(node_id, changed_fields).as_dict()

    def operations(self, *, node_id: str = "") -> list[dict[str, Any]]:
        return self.editor.operations(node_id=node_id)

    def stats(self) -> dict[str, Any]:
        payload = self.editor.stats()
        if self.quality is not None:
            payload["quality"] = self.quality.stats()
        return payload

    # ================================================================= 编辑
    def patch(self, node_id: str, changes: Mapping[str, Any], *,
              expected_revision: int | None = None, actor: str = "human",
              reason: str = "", idempotency_key: str = "",
              dry_run: bool = False) -> dict[str, Any]:
        result = self.editor.patch(EditRequest(
            novel_id=self.novel_id, node_id=node_id,
            expected_revision=expected_revision, changes=changes, actor=actor,
            reason=reason, idempotency_key=idempotency_key, dry_run=dry_run))
        payload = result.as_dict()
        payload["quality"] = self.get_quality(node_id)
        return payload

    def patch_batch(self, requests: Sequence[Mapping[str, Any]], *,
                    actor: str = "human", reason: str = "",
                    policy: str = "all_or_rollback",
                    dry_run: bool = False) -> dict[str, Any]:
        rows = tuple(EditRequest(
            novel_id=self.novel_id, node_id=str(row.get("node_id") or ""),
            expected_revision=row.get("expected_revision"),
            changes=dict(row.get("changes") or {}), actor=actor,
            reason=str(row.get("reason") or reason),
            idempotency_key=str(row.get("idempotency_key") or "")) for row in requests)
        result = self.editor.patch_batch(BatchEditRequest(
            novel_id=self.novel_id, requests=rows, actor=actor, reason=reason,
            policy=policy, dry_run=dry_run))
        return result.as_dict()

    def rewrite(self, node_id: str, target_fields: Sequence[str], instruction: str, *,
                expected_revision: int | None = None,
                preserve_fields: Sequence[str] = (),
                quality_issue_ids: Sequence[str] = (),
                idempotency_key: str = "", dry_run: bool = False,
                model_policy: Any = None) -> dict[str, Any]:
        result = self.editor.rewrite(RewriteRequest(
            novel_id=self.novel_id, node_id=node_id,
            expected_revision=expected_revision,
            target_fields=tuple(target_fields), instruction=instruction,
            preserve_fields=tuple(preserve_fields),
            quality_issue_ids=tuple(quality_issue_ids),
            idempotency_key=idempotency_key, dry_run=dry_run,
            model_policy=model_policy))
        payload = result.as_dict()
        if result.ok and not dry_run:
            payload["quality"] = self.get_quality(node_id)
        return payload

    def regenerate(self, node_id: str, *, task: str | None = None,
                   expected_revision: int | None = None,
                   preserve: Sequence[str] = (), idempotency_key: str = "",
                   model_policy: Any = None) -> dict[str, Any]:
        payload = self.editor.regenerate(
            node_id, task=task, expected_revision=expected_revision,
            preserve=tuple(preserve), idempotency_key=idempotency_key,
            model_policy=model_policy)
        payload["quality"] = self.get_quality(node_id)
        return payload

    def accept(self, node_id: str, *, revision: int | None = None,
               expected_revision: int | None = None, actor: str = "human",
               reason: str = "", idempotency_key: str = "") -> dict[str, Any]:
        result = self.editor.accept(node_id, revision=revision,
                                    expected_revision=expected_revision, actor=actor,
                                    reason=reason, idempotency_key=idempotency_key)
        payload = result.as_dict()
        payload["quality"] = self.get_quality(node_id)
        payload["acceptance_note"] = (
            "接受与质量相互独立：quality_status=passed 不代表已接受，"
            "accepted 也不代表质量永久通过（§69 / §70）")
        return payload

    def reject(self, node_id: str, *, revision: int | None = None,
               actor: str = "human", reason: str = "",
               idempotency_key: str = "") -> dict[str, Any]:
        return self.editor.reject(node_id, revision=revision, actor=actor,
                                  reason=reason, idempotency_key=idempotency_key).as_dict()

    def restore(self, node_id: str, *, from_revision: int,
                expected_revision: int | None = None, actor: str = "human",
                reason: str = "", idempotency_key: str = "") -> dict[str, Any]:
        result = self.editor.restore(node_id, from_revision=from_revision,
                                     expected_revision=expected_revision, actor=actor,
                                     reason=reason, idempotency_key=idempotency_key)
        payload = result.as_dict()
        payload["quality"] = self.get_quality(node_id)
        return payload

    def undo(self, node_id: str, *, expected_revision: int | None = None,
             actor: str = "human", reason: str = "",
             idempotency_key: str = "") -> dict[str, Any]:
        result = self.editor.undo(node_id, expected_revision=expected_revision,
                                  actor=actor, reason=reason,
                                  idempotency_key=idempotency_key)
        payload = result.as_dict()
        payload["quality"] = self.get_quality(node_id)
        return payload

    def move(self, node_id: str, *, expected_revision: int | None = None,
             parent_id: str | None = None, sequence: int | None = None,
             actor: str = "human", reason: str = "") -> dict[str, Any]:
        from novelforge.editor import MoveNodeRequest

        result = self.editor.move(MoveNodeRequest(
            novel_id=self.novel_id, node_id=node_id,
            expected_revision=expected_revision, parent_id=parent_id,
            sequence=sequence, actor=actor, reason=reason))
        return result.as_dict()

    # ================================================================= 质量
    def get_quality(self, node_id: str, *, revision: int | None = None) -> dict[str, Any]:
        """当前 revision 的 issue 列表；旧 revision 的 issue 明确标记 historical（§29）。"""

        current = self.repository.current_revision(node_id)
        asked = int(revision or current)
        node = self.repository.get_revision(node_id, asked) if asked else None
        issues: list[dict[str, Any]] = []
        historical: list[dict[str, Any]] = []
        if self.quality is not None:
            for row in self.quality.issues_for_node(node_id):
                entry = {**row, "revision": self._issue_revision(row),
                         "historical": False}
                if entry["revision"] and int(entry["revision"]) != asked:
                    entry["historical"] = True
                    historical.append(entry)
                else:
                    issues.append(entry)
        blocking = sorted(row.get("code") for row in issues
                          if row.get("severity") in ("blocker", "major"))
        return {"node_id": node_id, "requested_revision": asked,
                "current_revision": current,
                "quality_status": str(node.quality_status) if node else "",
                "issues": issues, "historical_issues": historical,
                "blocking_codes": blocking,
                "evaluated": bool(issues or historical),
                "note": ("historical issue 属于旧 revision，不代表当前问题（§29）"
                         if historical else "")}

    def evaluate(self, node_id: str, *, gates: Sequence[str] | None = None,
                 policy: QualityPolicy | None = None) -> dict[str, Any]:
        if self.quality is None:
            raise RuntimeError("EditorService 未配置 quality")
        scope = self.quality.build_scope(node_ids=(node_id,), kind="nodes")
        report = self.quality.evaluate(scope, policy=policy or self.policy, gates=gates)
        payload = report.as_dict()
        payload["summary"] = {"status": report.status,
                              "issues": len(report.issues),
                              "blockers": len(report.blockers)}
        payload["issues_for_node"] = sorted(
            row.issue_id for row in report.issues if node_id in row.scope.node_ids)
        return payload

    def plan_repair(self, *, node_id: str = "", issue_ids: Sequence[str] = (),
                    dry_run: bool = True, policy: QualityPolicy | None = None
                    ) -> dict[str, Any] | None:
        """§30 repair preview：问题是什么 / 改哪些节点 / 允许改什么 / 保留什么 / 复核哪些 gate。"""

        if self.quality is None:
            return None
        wanted = {str(value) for value in issue_ids if value}
        open_issues = [row for row in self.quality.store.issue_objects(status="open")
                       if (not wanted or row.issue_id in wanted)
                       and (not node_id or node_id in row.scope.node_ids)]
        if not open_issues:
            return {"status": "empty", "steps": [], "issue_ids": [],
                    "note": ("该节点还没有可修复的 open issue："
                             "请先 evaluate 生成质量结论（§29）")}
        plan = self.editor_planner().plan(open_issues, dry_run=dry_run)
        payload = plan.as_dict()
        payload["preview"] = {
            "issues": [row.issue_id for row in open_issues],
            "target_nodes": list(plan.target_node_ids),
            "allowed_fields": sorted({field for step in plan.steps
                                      for field in step.allow_change}),
            "preserve_fields": sorted({field for step in plan.steps
                                       for field in step.preserve}),
            "verification_gates": (list(plan.blast_radius.gates)
                                   if plan.blast_radius else []),
            "estimated_model_calls": plan.estimated_model_calls}
        return payload

    def repair(self, issue_ids: Sequence[str], *, dry_run: bool = False,
               idempotency_key: str = "", policy: QualityPolicy | None = None
               ) -> dict[str, Any]:
        """执行 V4-05 repair（经 ReviewService），并把结果记入 editor audit（§47）。"""

        if self.review is None:
            raise RuntimeError("EditorService 未配置 review（repair 需要 Quality 闭环）")
        outcome = self.review.repair_issue(list(issue_ids), dry_run=dry_run,
                                           policy=policy or self.policy,
                                           idempotency_key=idempotency_key)
        payload = outcome.as_dict()
        if outcome.result is not None and outcome.result.after_revisions:
            for node_id, revision in outcome.result.after_revisions.items():
                self.editor.record_operation(
                    operation="quality_repair", node_id=node_id, actor="ai_repair",
                    request_id=idempotency_key, source_revision=0,
                    result_revision=int(revision),
                    changed_fields=tuple(self._repaired_fields(outcome.plan, node_id)),
                    reason="V4-05 targeted repair", status="applied",
                    idempotency_key=idempotency_key,
                    ai={"issue_ids": list(issue_ids)},
                    extra={"verification": (outcome.verification.as_dict()
                                            if outcome.verification else None)})
        return payload

    def verify_repair(self, *, issue_ids: Sequence[str] = (),
                      policy: QualityPolicy | None = None) -> dict[str, Any]:
        if self.review is None:
            raise RuntimeError("EditorService 未配置 review")
        report = self.quality.evaluate(policy=policy or self.policy)
        verification = self.editor_verifier().verify(
            before_report=report, issue_ids=tuple(issue_ids),
            policy=policy or self.policy)
        return verification.as_dict()

    # ---------------------------------------------------------------- 内部
    def editor_planner(self):
        if self.review is not None:
            return self.review.planner
        from novelforge.quality.repair import RepairPlanner

        return RepairPlanner(self.project_root, self.novel_id,
                             repository=self.repository)

    def editor_verifier(self):
        if self.review is not None:
            return self.review.verifier
        from novelforge.quality.repair import RepairVerifier

        return RepairVerifier(self.quality, project_root=self.project_root,
                              novel_id=self.novel_id, repository=self.repository)

    @staticmethod
    def _repaired_fields(plan: RepairPlan, node_id: str) -> tuple[str, ...]:
        for step in plan.steps:
            if step.node_id == node_id:
                return tuple(step.allow_change)
        return ()

    def _issue_revision(self, issue: Mapping[str, Any]) -> int:
        scope = dict(issue.get("scope") or {})
        revision = int(scope.get("revision") or 0)
        if revision:
            return revision
        revisions = [int(row.get("revision") or 0)
                     for row in (issue.get("evidence") or [])
                     if row.get("revision")]
        return max(revisions) if revisions else 0

    def _diff_quality(self, node_id: str, before_revision: int,
                      after_revision: int) -> dict[str, Any]:
        if self.quality is None:
            return {}
        rows = self.quality.issues_for_node(node_id)
        before = {str(row.get("issue_id")) for row in rows
                  if self._issue_revision(row) == int(before_revision)}
        after = {str(row.get("issue_id")) for row in rows
                 if self._issue_revision(row) == int(after_revision)}
        return {"before_issue_ids": sorted(before), "after_issue_ids": sorted(after),
                "resolved_issue_ids": sorted(before - after),
                "new_issue_ids": sorted(after - before),
                "source": "quality store"}

    # ----------------------------------------------------------- 闭环（§57）
    def evaluate_and_repair(self, *, node_id: str = "", policy: QualityPolicy | None = None,
                            dry_run: bool = False, issue_ids: Sequence[str] = (),
                            max_rounds: int | None = None) -> dict[str, Any]:
        if self.review is None:
            raise RuntimeError("EditorService 未配置 review")
        loop = QualityLoopService(self.review, policy=policy or self.policy)
        scope = (self.quality.build_scope(node_ids=(node_id,), kind="nodes")
                 if node_id else None)
        result = loop.run(scope, policy=policy, dry_run=dry_run,
                          issue_ids=tuple(issue_ids), max_rounds=max_rounds)
        payload = result.as_dict()
        if node_id:
            payload["quality"] = self.get_quality(node_id)
        return payload


def editor_service(project_root: Path | str, novel_id: str, *,
                   gateway: Any = None, memory: Any = None,
                   repository: BlueprintRepository | None = None,
                   store: EditorStore | None = None,
                   quality: QualityService | None = None,
                   review: ReviewService | None = None,
                   policy: QualityPolicy | None = None) -> EditorService:
    """装配 EditorService（Application 层负责组合，接口层只调用本工厂）。"""

    repository = repository or BlueprintRepository(project_root, novel_id)
    generation = None
    if gateway is not None:
        resolved_memory = memory
        if resolved_memory is None:
            try:  # 只有存在作者数据时才装配生成能力；失败 → AI 不可用（明确报错）
                from novelforge.memory import build_default_service

                resolved_memory = build_default_service(novel_id, project_root)
            except Exception:  # noqa: BLE001
                resolved_memory = None
        if resolved_memory is not None:
            generation = BlueprintGenerationService(
                project_root, novel_id, gateway=gateway, memory=resolved_memory,
                repository=repository)
    editor = BlueprintEditorService(project_root, novel_id, repository=repository,
                                    generation=generation, store=store)
    resolved_quality = quality or QualityService(project_root, novel_id,
                                                 repository=repository,
                                                 memory=memory)
    resolved_review = review or ReviewService(
        project_root, novel_id, quality=resolved_quality, generation=generation,
        repository=repository, policy=policy)
    return EditorService(project_root, novel_id, editor=editor,
                         quality=resolved_quality, review=resolved_review,
                         generation=generation, repository=repository, policy=policy)


__all__ = ["EditorService", "editor_service"]
