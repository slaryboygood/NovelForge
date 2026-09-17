"""BlueprintEditorService（V4-06 §5–§13、§38–§46、§58–§64）。

Editor 只做四件事：**读 revision / 改字段 / 比较 / 记录**。

```text
· canonical truth 仍然是 BlueprintRepository（editor 不持有第二套 store）
· 所有写操作都产生新 revision（append-only）；accepted 不被静默覆盖
· 所有写操作携带 expected_revision（乐观并发）；冲突 → EditorConflictError
· 所有写操作可带 idempotency_key（重放不产生第二个 revision）
· preserve / 结构 identity 是硬约束（patch、rewrite、restore 都遵守）
· 审计写进 editor metadata（不是 Blueprint payload）
```
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from novelforge.blueprint import (
    ALLOWED_PARENT_TYPES,
    PAYLOAD_MODELS,
    BlueprintNode,
    BlueprintNodeNotFound,
    BlueprintRepository,
    BlueprintStatusError,
    BlueprintValidationError,
    STRUCTURAL_IDENTITY_FIELDS,
    require_valid,
)
from novelforge.core.ids import new_request_id
from novelforge.core.revision import RevisionConflict, check_expected_revision
from novelforge.generation.service import task_for_node_type

from .contracts import (
    ApprovalResult,
    BatchEditRequest,
    BatchEditResult,
    DiffRequest,
    EditRequest,
    EditResult,
    EditorOperationRecord,
    EditorSession,
    MoveNodeRequest,
    RestoreResult,
    ReviewDecision,
    RevisionHistory,
    RewriteRequest,
    RewriteResult,
)
from .diff import BlueprintDiff, diff_payloads
from .errors import (
    EditorConflictError,
    EditorNotFoundError,
    EditorOperationRejected,
    EditorOwnershipError,
    EditorPreserveViolation,
    EditorValidationError,
)
from .history import build_history, revision_view
from .impact import compute_impact
from .operations import EditorStore, utc_now
from .patch import (
    build_edited_node,
    editable_fields,
    merge_changes,
    payload_dict,
    validate_changes,
)

#: 与父节点绑定的结构 identity 字段（move 时随 parent 一起更新，保持结构自洽）
PARENT_LINKED_IDENTITY: Mapping[str, str] = {
    "scene": "chapter_id",
    "character_arc": "character_id",
}


class BlueprintEditorService:
    """按 novel_id 绑定的 Blueprint 编辑服务。"""

    def __init__(self, project_root: Path | str, novel_id: str, *,
                 repository: BlueprintRepository | None = None,
                 generation: Any = None, store: EditorStore | None = None) -> None:
        if not str(novel_id or "").strip():
            raise EditorOwnershipError("BlueprintEditorService 需要显式 novel_id")
        self.project_root = Path(project_root)
        self.novel_id = str(novel_id)
        self.repository = repository or BlueprintRepository(self.project_root,
                                                            self.novel_id)
        self.generation = generation
        self.store = store or EditorStore(self.project_root, self.novel_id)
        self._sessions: dict[str, EditorSession] = {}

    # ================================================================= 读取
    def current_revision(self, node_id: str) -> int:
        return self.repository.current_revision(node_id)

    def _require_current(self, node_id: str) -> BlueprintNode:
        node = self.repository.get_current(node_id)
        if node is None:
            raise EditorNotFoundError(f"Blueprint 节点不存在：{node_id}",
                                      details={"node_id": node_id,
                                               "novel_id": self.novel_id})
        return node

    def _require_revision(self, node_id: str, revision: int) -> BlueprintNode:
        node = self.repository.get_revision(node_id, int(revision))
        if node is None:
            raise EditorNotFoundError(
                f"revision 不存在：{node_id}@{revision}",
                details={"node_id": node_id, "revision": int(revision)})
        return node

    def get_node(self, node_id: str, revision: int | None = None) -> dict[str, Any]:
        node = (self._require_current(node_id) if revision is None
                else self._require_revision(node_id, revision))
        review = self.store.review_for(node_id, node.revision)
        view = revision_view(node, is_current=(node.revision
                                               == self.repository.current_revision(node_id)),
                             review=review)
        return {"novel_id": self.novel_id, "node": node.as_dict(),
                "view": view.as_dict(),
                "editable_fields": list(editable_fields(node.node_type)),
                "protected_fields": list(_protected_for(node.node_type)),
                "quality_status": node.quality_status,
                "read_only": False}

    def get_history(self, node_id: str) -> RevisionHistory:
        self._require_current(node_id)
        return build_history(self.repository, node_id,
                             operations=self.store.operations(node_id=node_id),
                             reviews=self.store.reviews(node_id=node_id))

    def list_revisions(self, node_id: str) -> list[int]:
        self._require_current(node_id)
        return self.repository.list_revisions(node_id)

    def operations(self, *, node_id: str = "") -> list[dict[str, Any]]:
        return self.store.operations(node_id=node_id)

    def record_operation(self, **kwargs: Any) -> EditorOperationRecord:
        """公开的审计入口（供 Application 记录 **非** editor 直接产生的操作，
        例如 V4-05 `quality_repair`，§47「是否与某 QualityIssue 关联」）。
        """

        return self._record(**kwargs)

    def review_for(self, node_id: str, revision: int) -> dict[str, Any]:
        return self.store.review_for(node_id, revision)

    def stats(self) -> dict[str, Any]:
        return {"novel_id": self.novel_id,
                "editor": self.store.stats(),
                "blueprint_nodes": len(self.repository.all_nodes())}

    # ================================================================= 比较
    def diff(self, request: DiffRequest) -> BlueprintDiff:
        self._assert_novel(request.novel_id)
        target = request.to_revision or self.repository.current_revision(request.node_id)
        if not target:
            raise EditorNotFoundError(f"Blueprint 节点不存在：{request.node_id}",
                                      details={"node_id": request.node_id})
        return self.compare(request.node_id, request.from_revision,
                            request.node_id, target)

    def compare(self, left_node_id: str, left_revision: int, right_node_id: str,
                right_revision: int) -> BlueprintDiff:
        """同节点跨 revision 比较；跨节点 / 跨作品一律拒绝（§61 / §64）。"""

        if str(left_node_id) != str(right_node_id):
            raise EditorValidationError(
                "不允许跨节点比较 revision",
                details={"left_node_id": left_node_id, "right_node_id": right_node_id})
        left = self._require_revision(left_node_id, left_revision)
        right = self._require_revision(right_node_id, right_revision)
        if left.novel_id != self.novel_id or right.novel_id != self.novel_id:
            raise EditorOwnershipError(
                "不允许跨作品比较 revision",
                details={"novel_id": self.novel_id, "left": left.novel_id,
                         "right": right.novel_id})
        return self._diff_nodes(left, right)

    def _diff_nodes(self, left: BlueprintNode, right: BlueprintNode) -> BlueprintDiff:
        return diff_payloads(node_id=left.node_id, novel_id=self.novel_id,
                             before=payload_dict(left), after=payload_dict(right),
                             revision_before=left.revision,
                             revision_after=right.revision,
                             status_before=str(left.status),
                             status_after=str(right.status),
                             quality_status_before=str(left.quality_status),
                             quality_status_after=str(right.quality_status))

    def change_impact(self, node_id: str, changed_fields: Iterable[str] = (),
                      revision: int | None = None):
        node = self._require_current(node_id)
        return compute_impact(list(self.repository.all_nodes()), node_id=node_id,
                              changed_fields=changed_fields,
                              revision=int(revision or node.revision),
                              novel_id=self.novel_id)

    # ================================================================= 手工编辑
    def patch(self, request: EditRequest) -> EditResult:
        self._assert_novel(request.novel_id)
        replay = self._replay(request.idempotency_key)
        if replay:
            return self._replay_edit_result(replay)
        current = self._require_current(request.node_id)
        changes = validate_changes(current, request.changes)
        merged = merge_changes(current, changes)
        candidate = self._candidate(current, payload_data=merged, operation="manual_patch",
                                    request_id=request.request_id,
                                    actor=request.actor, changes=changes)
        self._assert_valid(candidate, node_id=current.node_id)
        diff = self._diff_nodes(current, candidate)
        impact = compute_impact(list(self.repository.all_nodes()),
                                node_id=current.node_id,
                                changed_fields=diff.all_changed_fields,
                                revision=current.revision, novel_id=self.novel_id)
        if request.dry_run:
            return EditResult(
                node_id=current.node_id, novel_id=self.novel_id, status="dry_run",
                before_revision=current.revision, revision=current.revision,
                changed_fields=diff.all_changed_fields,
                unchanged_fields=diff.unchanged_fields, dry_run=True,
                request_id=request.request_id, diff=diff, impact=impact,
                quality_status="unevaluated",
                notes=("dry run：未写入 revision", f"预计影响 {len(impact.dependent_nodes)} 个下游节点"))
        saved = self._save(current, candidate, expected_revision=request.expected_revision,
                           idempotency_key=request.idempotency_key,
                           conflict_node_id=current.node_id)
        record = self._record(operation="manual_patch", node_id=current.node_id,
                              actor=request.actor, request_id=request.request_id,
                              source_revision=current.revision, result_revision=saved.revision,
                              changed_fields=diff.all_changed_fields, reason=request.reason,
                              idempotency_key=request.idempotency_key,
                              impact=impact.as_dict())
        return EditResult(
            node_id=current.node_id, novel_id=self.novel_id, status="applied",
            before_revision=current.revision, revision=saved.revision,
            changed_fields=diff.all_changed_fields,
            unchanged_fields=diff.unchanged_fields,
            operation_id=record.operation_id, request_id=request.request_id,
            diff=diff, impact=impact, quality_status=saved.quality_status,
            notes=(f"新 revision r{saved.revision}（status=proposed，quality=unevaluated）",))

    def patch_batch(self, request: BatchEditRequest) -> BatchEditResult:
        """§38：先全量校验（零写入），再统一提交。"""

        self._assert_novel(request.novel_id)
        prepared: list[tuple[EditRequest, BlueprintNode, BlueprintNode, BlueprintDiff]] = []
        rejected: list[EditResult] = []
        replayed: list[EditResult] = []
        for row in request.requests:
            replay = self._replay(row.idempotency_key)
            if replay:
                replayed.append(self._replay_edit_result(replay))
                continue
            try:
                current = self._require_current(row.node_id)
                changes = validate_changes(current, row.changes)
                merged = merge_changes(current, changes)
                candidate = self._candidate(current, payload_data=merged,
                                            operation="batch_patch",
                                            request_id=row.request_id,
                                            actor=request.actor, changes=changes)
                self._assert_valid(candidate, node_id=current.node_id)
                prepared.append((row, current, candidate,
                                 self._diff_nodes(current, candidate)))
            except (EditorNotFoundError, EditorValidationError,
                    EditorPreserveViolation) as exc:
                rejected.append(EditResult(
                    node_id=row.node_id, novel_id=self.novel_id, status="rejected",
                    before_revision=self.repository.current_revision(row.node_id),
                    request_id=row.request_id, rejected_reason=exc.message,
                    notes=(exc.code,)))
        if rejected and request.policy == "all_or_rollback":
            return BatchEditResult(
                novel_id=self.novel_id, status="rejected",
                results=tuple([*rejected, *replayed]),
                rejected_node_ids=tuple(row.node_id for row in rejected),
                notes=("all_or_rollback：存在校验失败的节点，未提交任何 revision（§38）",
                       *[f"{row.node_id}: {row.rejected_reason}" for row in rejected]))
        applied: list[EditResult] = []
        conflicts: list[str] = []
        for row, current, candidate, diff in prepared:
            if request.dry_run:
                applied.append(EditResult(
                    node_id=current.node_id, novel_id=self.novel_id, status="dry_run",
                    before_revision=current.revision, revision=current.revision,
                    changed_fields=diff.all_changed_fields, dry_run=True,
                    request_id=row.request_id, diff=diff))
                continue
            try:
                saved = self._save(current, candidate,
                                   expected_revision=row.expected_revision,
                                   idempotency_key=row.idempotency_key,
                                   conflict_node_id=current.node_id)
            except EditorConflictError as exc:
                conflicts.append(current.node_id)
                applied.append(EditResult(
                    node_id=current.node_id, novel_id=self.novel_id, status="conflict",
                    before_revision=current.revision,
                    revision=self.repository.current_revision(current.node_id),
                    request_id=row.request_id, rejected_reason=exc.message))
                continue
            record = self._record(operation="batch_patch", node_id=current.node_id,
                                  actor=request.actor, request_id=row.request_id,
                                  source_revision=current.revision,
                                  result_revision=saved.revision,
                                  changed_fields=diff.all_changed_fields,
                                  reason=request.reason or row.reason,
                                  idempotency_key=row.idempotency_key)
            applied.append(EditResult(
                node_id=current.node_id, novel_id=self.novel_id, status="applied",
                before_revision=current.revision, revision=saved.revision,
                changed_fields=diff.all_changed_fields, diff=diff,
                operation_id=record.operation_id, request_id=row.request_id,
                quality_status=saved.quality_status))
        status = "dry_run" if request.dry_run else (
            "partial" if conflicts else "applied")
        return BatchEditResult(
            novel_id=self.novel_id, status=status,
            results=tuple([*rejected, *replayed, *applied]),
            applied_node_ids=tuple(row.node_id for row in applied
                                   if row.status == "applied"),
            rejected_node_ids=tuple(row.node_id for row in rejected),
            conflict_node_ids=tuple(conflicts),
            notes=(("dry run：未写入 revision",) if request.dry_run else ())
            + (("存在 revision 冲突：append-only revision 无法回滚已提交部分",)
               if conflicts else ()))

    # ================================================================= AI 改写
    def rewrite(self, request: RewriteRequest) -> RewriteResult:
        self._assert_novel(request.novel_id)
        replay = self._replay(request.idempotency_key)
        if replay:
            return self._replay_rewrite_result(replay)
        current = self._require_current(request.node_id)
        allowed = set(editable_fields(current.node_type))
        target = tuple(str(value) for value in request.target_fields if str(value))
        unknown = sorted(set(target) - allowed)
        if unknown:
            raise EditorValidationError(f"这些字段不可改写：{unknown}",
                                        details={"editable_fields": sorted(allowed)})
        preserve = tuple(sorted({str(value) for value in request.preserve_fields if value}))
        overlap = sorted(set(target) & set(preserve))
        if overlap:
            raise EditorValidationError(f"target_fields 与 preserve_fields 冲突：{overlap}")
        structural = tuple(field for field in STRUCTURAL_IDENTITY_FIELDS.get(
            current.node_type, ()) if field in allowed)
        impact = compute_impact(list(self.repository.all_nodes()),
                                node_id=current.node_id, changed_fields=target,
                                revision=current.revision, novel_id=self.novel_id)
        if request.dry_run:
            return RewriteResult(
                node_id=current.node_id, novel_id=self.novel_id, status="dry_run",
                target_fields=target, before_revision=current.revision,
                revision=current.revision, dry_run=True,
                request_id=request.request_id, impact=impact,
                notes=("dry run：未调用模型、未写入 revision",
                       f"preserve={[*preserve, *structural]}",
                       "预计调用 1 次模型任务（改写指定字段）"))
        if self.generation is None:
            raise EditorOperationRejected(
                "AI 改写不可用：未配置 generation（editor 不直接调用模型）",
                details={"code": "EDITOR_AI_UNAVAILABLE", "node_id": current.node_id})
        try:
            result = self.generation.rewrite_fields(
                novel_id=self.novel_id, node_id=current.node_id,
                expected_revision=request.expected_revision, target_fields=target,
                preserve_fields=preserve,
                instruction=request.instruction,
                quality_issue_ids=tuple(request.quality_issue_ids),
                idempotency_key=request.idempotency_key,
                request_id=request.request_id, model_policy=request.model_policy)
        except RevisionConflict as exc:
            raise EditorConflictError(
                str(exc.message), details={**exc.as_dict(),
                                           "node_id": current.node_id}) from exc
        except Exception as exc:  # noqa: BLE001 - 统一映射（§75）
            code = str(getattr(exc, "code", "") or type(exc).__name__)
            if "PRESERVE" in code.upper() or "VIOLATION" in code.upper():
                self._record(operation="ai_rewrite", node_id=current.node_id,
                             actor="ai_rewrite", request_id=request.request_id,
                             source_revision=current.revision, result_revision=0,
                             changed_fields=(), reason=request.instruction,
                             status="rejected", idempotency_key=request.idempotency_key,
                             ai=dict(getattr(exc, "details", {}) or {}))
                raise EditorPreserveViolation(
                    f"AI 改写违反 preserve 约束，未写入任何 revision：{exc}",
                    details=dict(getattr(exc, "details", {}) or {})) from exc
            raise EditorOperationRejected(
                f"AI 改写失败：{exc}",
                details={"code": code, "node_id": current.node_id}) from exc
        after = self._require_current(current.node_id)
        diff = self._diff_nodes(current, after)
        record = self._record(
            operation="ai_rewrite", node_id=current.node_id, actor="ai_rewrite",
            request_id=request.request_id, source_revision=current.revision,
            result_revision=after.revision, changed_fields=diff.all_changed_fields,
            reason=request.instruction, idempotency_key=request.idempotency_key,
            impact=compute_impact(list(self.repository.all_nodes()),
                                  node_id=current.node_id,
                                  changed_fields=diff.all_changed_fields,
                                  revision=after.revision,
                                  novel_id=self.novel_id).as_dict(),
            ai={"contract_id": str(result.contract), "model": str(result.model),
                "provider": str(result.provider),
                "context_digest": str(result.context_digest),
                "source_ids": list(result.source_ids),
                "quality_issue_ids": list(request.quality_issue_ids),
                "target_fields": list(target), "preserve_fields": list(preserve),
                "usage": dict(result.usage or {})})
        return RewriteResult(
            node_id=current.node_id, novel_id=self.novel_id, status="applied",
            target_fields=target, before_revision=current.revision,
            revision=after.revision, changed_fields=diff.all_changed_fields,
            operation_id=record.operation_id, request_id=request.request_id,
            diff=diff, impact=self.change_impact(current.node_id,
                                                 diff.all_changed_fields, after.revision),
            usage=dict(result.usage or {}), model=str(result.model),
            provider=str(result.provider), contract_id=str(result.contract),
            notes=(f"新 revision r{after.revision}（status=proposed，quality=unevaluated）",
                   f"只有 {list(target)} 被允许改动"))

    def regenerate(self, node_id: str, *, task: str | None = None,
                   expected_revision: int | None = None,
                   preserve: Sequence[str] = (), idempotency_key: str = "",
                   actor: str = "ai_generation", reason: str = "",
                   model_policy: Any = None) -> dict[str, Any]:
        """整节点重生成（delegates to generation，§34）。"""

        if self.generation is None:
            raise EditorOperationRejected(
                "AI 重生成不可用：未配置 generation",
                details={"code": "EDITOR_AI_UNAVAILABLE", "node_id": node_id})
        current = self._require_current(node_id)
        resolved_task = task or _task_for(current.node_type)
        try:
            result = self.generation.regenerate(
                task=resolved_task, node_id=node_id,
                expected_revision=expected_revision, preserve=tuple(preserve),
                idempotency_key=idempotency_key, model_policy=model_policy)
        except RevisionConflict as exc:
            raise EditorConflictError(str(exc.message),
                                      details={**exc.as_dict(), "node_id": node_id}) from exc
        except Exception as exc:  # noqa: BLE001
            raise EditorOperationRejected(
                f"重生成失败：{exc}",
                details={"code": str(getattr(exc, "code", "")), "node_id": node_id}) from exc
        self._record(operation="ai_regenerate", node_id=node_id, actor=actor,
                     request_id=str(result.request_id),
                     source_revision=current.revision, result_revision=result.revision,
                     changed_fields=(), reason=reason,
                     idempotency_key=idempotency_key,
                     ai={"contract_id": str(result.contract), "model": str(result.model),
                         "provider": str(result.provider),
                         "context_digest": str(result.context_digest),
                         "source_ids": list(result.source_ids),
                         "usage": dict(result.usage or {})})
        return {**result.as_dict(),
                "editor": {"quality_status": "unevaluated",
                           "note": "重生成结果仍是 proposal，不代表作者已接受（§69）"}}

    # ================================================================= 审批
    def accept(self, node_id: str, *, revision: int | None = None,
               expected_revision: int | None = None, actor: str = "human",
               reason: str = "", idempotency_key: str = "") -> ApprovalResult:
        replay = self._replay(idempotency_key)
        if replay:
            return self._replay_approval(replay)
        current = self._require_current(node_id)
        reviewed = int(revision or current.revision)
        if expected_revision is not None:
            self._check_expected(node_id, expected_revision)
        if current.status == "accepted" and reviewed == current.revision:
            return ApprovalResult(
                node_id=node_id, novel_id=self.novel_id, decision="accepted",
                reviewed_revision=reviewed, revision=current.revision,
                status="recorded", quality_status=str(current.quality_status),
                review_note=reason, idempotent=True, previous_status=str(current.status),
                notes=("该 revision 已是 accepted：不重复产生 revision",))
        previous = str(current.status)
        try:
            saved = self.repository.set_status(node_id, "accepted",
                                               expected_revision=current.revision)
        except BlueprintStatusError as exc:
            raise EditorOperationRejected(
                f"当前状态不允许接受：{previous}",
                details={"code": "EDITOR_STATUS_TRANSITION_INVALID",
                         "node_id": node_id, "status": previous}) from exc
        decision = self._record_review(node_id=node_id, revision=reviewed,
                                       decision="accepted", actor=actor, reason=reason,
                                       resulting_revision=saved.revision)
        record = self._record(operation="accept", node_id=node_id, actor=actor,
                              request_id="", source_revision=current.revision,
                              result_revision=saved.revision,
                              changed_fields=(), reason=reason,
                              idempotency_key=idempotency_key,
                              extra={"reviewed_revision": reviewed},
                              operation_id=decision.operation_id)
        return ApprovalResult(
            node_id=node_id, novel_id=self.novel_id, decision="accepted",
            reviewed_revision=reviewed, revision=saved.revision, status="applied",
            quality_status=str(saved.quality_status), review_note=reason,
            operation_id=record.operation_id, previous_status=previous,
            notes=(f"接受 r{reviewed} → 新 revision r{saved.revision}（append-only）",
                   "quality_status 不是接受条件：quality pass ≠ accepted（§69）"))

    def reject(self, node_id: str, *, revision: int | None = None,
               actor: str = "human", reason: str = "",
               idempotency_key: str = "") -> ApprovalResult:
        """§23：reject 不删除 revision —— 拒绝记录写进 editor metadata。"""

        replay = self._replay(idempotency_key)
        if replay:
            return self._replay_approval(replay)
        current = self._require_current(node_id)
        reviewed = int(revision or current.revision)
        self._require_revision(node_id, reviewed)
        decision = self._record_review(node_id=node_id, revision=reviewed,
                                       decision="rejected", actor=actor, reason=reason,
                                       resulting_revision=0)
        record = self._record(operation="reject", node_id=node_id, actor=actor,
                              request_id="", source_revision=current.revision,
                              result_revision=current.revision, changed_fields=(),
                              reason=reason, status="recorded",
                              idempotency_key=idempotency_key,
                              extra={"reviewed_revision": reviewed},
                              operation_id=decision.operation_id)
        return ApprovalResult(
            node_id=node_id, novel_id=self.novel_id, decision="rejected",
            reviewed_revision=reviewed, revision=current.revision,
            status="recorded", quality_status=str(current.quality_status),
            review_note=reason, operation_id=record.operation_id,
            previous_status=str(current.status),
            notes=(f"拒绝 r{reviewed}：revision 保留，Blueprint status 不变"
                   "（rejection 是 editor metadata，§23）",))

    # ============================================================ 恢复 / 撤销
    def restore(self, node_id: str, *, from_revision: int,
                expected_revision: int | None = None, actor: str = "human",
                reason: str = "", idempotency_key: str = "") -> RestoreResult:
        """§25：restore 不移动 current 指针，而是用旧内容创建新 revision。"""

        replay = self._replay(idempotency_key)
        if replay:
            return self._replay_restore(replay)
        return self._restore(node_id, from_revision=int(from_revision),
                             operation="restore", expected_revision=expected_revision,
                             actor=actor, reason=reason, idempotency_key=idempotency_key)

    def undo(self, node_id: str, *, expected_revision: int | None = None,
             actor: str = "human", reason: str = "",
             idempotency_key: str = "") -> RestoreResult:
        """§26：undo = restore(previous revision)（不是数据库回滚）。"""

        replay = self._replay(idempotency_key)
        if replay:
            return self._replay_restore(replay)
        current = self._require_current(node_id)
        if int(current.parent_revision) <= 0:
            raise EditorOperationRejected(
                "没有可撤销的上一版 revision",
                details={"code": "EDITOR_UNDO_UNAVAILABLE", "node_id": node_id})
        return self._restore(node_id, from_revision=int(current.parent_revision),
                             operation="undo", expected_revision=expected_revision,
                             actor=actor, reason=reason or "undo", idempotency_key=idempotency_key)

    def _restore(self, node_id: str, *, from_revision: int, operation: str,
                 expected_revision: int | None, actor: str, reason: str,
                 idempotency_key: str) -> RestoreResult:
        current = self._require_current(node_id)
        source = self._require_revision(node_id, from_revision)
        if int(source.revision) == int(current.revision):
            raise EditorOperationRejected(
                f"r{from_revision} 就是当前 revision，没有需要恢复的内容",
                details={"code": "EDITOR_RESTORE_NOOP", "node_id": node_id})
        self._assert_structural_identity(current, source)
        candidate = build_edited_node(
            current, payload=source.payload,
            provenance_extra={"operation": operation, "restored_from": int(source.revision),
                              "source_revision": int(current.revision),
                              "actor": actor, "reason": reason})
        self._assert_valid(candidate, node_id=node_id)
        diff = self._diff_nodes(current, candidate)
        saved = self._save(current, candidate, expected_revision=expected_revision,
                           idempotency_key=idempotency_key, conflict_node_id=node_id)
        impact = compute_impact(list(self.repository.all_nodes()), node_id=node_id,
                                changed_fields=diff.all_changed_fields,
                                revision=saved.revision, novel_id=self.novel_id)
        record = self._record(operation=operation, node_id=node_id, actor=actor,
                              request_id="", source_revision=current.revision,
                              result_revision=saved.revision,
                              changed_fields=diff.all_changed_fields, reason=reason,
                              idempotency_key=idempotency_key,
                              impact=impact.as_dict(),
                              extra={"restored_from": int(source.revision)})
        return RestoreResult(
            node_id=node_id, novel_id=self.novel_id, operation=operation,
            restored_from=int(source.revision), before_revision=current.revision,
            revision=saved.revision, status="applied",
            changed_fields=diff.all_changed_fields, operation_id=record.operation_id,
            diff=diff, impact=impact,
            notes=(f"以 r{source.revision} 的内容创建 r{saved.revision}（历史 revision 全部保留）",))

    # ================================================================ 结构移动
    def move(self, request: MoveNodeRequest) -> EditResult:
        """§39：parent / sequence 只能通过本契约修改（patch 一律拒绝）。"""

        self._assert_novel(request.novel_id)
        current = self._require_current(request.node_id)
        new_parent_id = (current.parent_id if request.parent_id is None
                         else str(request.parent_id))
        new_sequence = (current.sequence if request.sequence is None
                        else int(request.sequence))
        if new_parent_id == current.parent_id and new_sequence == current.sequence:
            raise EditorOperationRejected(
                "parent_id / sequence 没有变化",
                details={"code": "EDITOR_MOVE_NOOP", "node_id": current.node_id})
        allowed = ALLOWED_PARENT_TYPES.get(current.node_type, ())
        if new_parent_id == "":
            if allowed and None not in allowed:
                raise EditorValidationError(
                    f"{current.node_type} 必须指定父节点",
                    details={"allowed_parent_types": [str(value) for value in allowed]})
        else:
            parent = self.repository.get_current(new_parent_id)
            if parent is None:
                raise EditorNotFoundError(f"目标父节点不存在：{new_parent_id}",
                                          details={"node_id": new_parent_id})
            if allowed and parent.node_type not in allowed:
                raise EditorValidationError(
                    f"{current.node_type} 不能挂在 {parent.node_type} 下",
                    details={"allowed_parent_types": [str(value) for value in allowed]})
        if new_sequence <= 0:
            raise EditorValidationError("sequence 必须为正整数")
        payload = payload_dict(current)
        linked = PARENT_LINKED_IDENTITY.get(current.node_type)
        if linked and payload.get(linked) != new_parent_id:
            model = PAYLOAD_MODELS[str(current.node_type)]
            payload = model.model_validate({**payload, linked: new_parent_id})
        else:
            payload = current.payload
        moved = BlueprintNode(
            node_id=current.node_id, novel_id=current.novel_id,
            node_type=current.node_type, payload=payload,
            parent_id=new_parent_id, revision=current.revision,
            parent_revision=current.parent_revision, status="proposed",
            source_ids=tuple(current.source_ids), context_digest=current.context_digest,
            created_at=current.created_at,
            generation_contract=current.generation_contract,
            generation_contract_version=current.generation_contract_version,
            provenance={**dict(current.provenance), "operation": "move",
                        "from_parent": current.parent_id,
                        "from_sequence": int(current.sequence)},
            quality_status="unevaluated", schema_version=current.schema_version,
            sequence=new_sequence)
        self._assert_valid(moved, node_id=current.node_id)
        saved = self._save(current, moved, expected_revision=request.expected_revision,
                           idempotency_key=request.idempotency_key,
                           conflict_node_id=current.node_id)
        record = self._record(operation="move", node_id=current.node_id, actor=request.actor,
                              request_id=request.request_id,
                              source_revision=current.revision,
                              result_revision=saved.revision, changed_fields=(),
                              reason=request.reason, idempotency_key=request.idempotency_key,
                              extra={"parent_id": new_parent_id,
                                     "sequence": new_sequence,
                                     "from_parent": current.parent_id,
                                     "from_sequence": int(current.sequence)})
        impact = compute_impact(list(self.repository.all_nodes()),
                                node_id=current.node_id, changed_fields=(),
                                revision=saved.revision, novel_id=self.novel_id)
        return EditResult(
            node_id=current.node_id, novel_id=self.novel_id, status="applied",
            before_revision=current.revision, revision=saved.revision,
            operation_id=record.operation_id, request_id=request.request_id,
            impact=impact, quality_status=saved.quality_status,
            notes=(f"parent {current.parent_id or '（根）'} → {new_parent_id or '（根）'}",
                   f"sequence {current.sequence} → {new_sequence}",
                   f"新 revision r{saved.revision}（status=proposed）"))

    # ============================================================ session（内存）
    def open_session(self, *, actor: str = "human", node_id: str = "") -> EditorSession:
        session = EditorSession(
            session_id=new_request_id("session"), novel_id=self.novel_id, actor=actor,
            opened_node=node_id,
            base_revision=self.repository.current_revision(node_id) if node_id else 0,
            created_at=utc_now())
        self._sessions[session.session_id] = session
        return session

    def get_session(self, session_id: str) -> EditorSession:
        session = self._sessions.get(session_id)
        if session is None:
            raise EditorNotFoundError(f"编辑器会话不存在：{session_id}",
                                      details={"session_id": session_id})
        return session

    def sessions(self) -> list[EditorSession]:
        return list(self._sessions.values())

    # ================================================================== 内部
    def _assert_novel(self, novel_id: str) -> None:
        if str(novel_id) != self.novel_id:
            raise EditorOwnershipError(
                f"拒绝跨作品编辑：{novel_id} != {self.novel_id}",
                details={"novel_id": self.novel_id, "requested": str(novel_id)})

    def _check_expected(self, node_id: str, expected_revision: int | None) -> None:
        try:
            check_expected_revision(
                expected_revision, self.repository.current_revision(node_id) or None,
                artifact_id=node_id)
        except RevisionConflict as exc:
            raise self._conflict(exc, node_id) from exc

    def _conflict(self, exc: RevisionConflict, node_id: str) -> EditorConflictError:
        details = {**exc.as_dict(), "node_id": node_id, "novel_id": self.novel_id}
        expected, actual = exc.expected, exc.actual
        if expected is not None and actual is not None:
            left = self.repository.get_revision(node_id, int(expected))
            right = self.repository.get_revision(node_id, int(actual))
            if left is not None and right is not None:
                details["conflict_diff"] = self._diff_nodes(left, right).as_dict()
        return EditorConflictError(str(exc.message), details=details)

    def _save(self, current: BlueprintNode, candidate: BlueprintNode, *,
              expected_revision: int | None, idempotency_key: str,
              conflict_node_id: str) -> BlueprintNode:
        try:
            return self.repository.save_revision(
                candidate, expected_revision=expected_revision,
                idempotency_key=(f"editor:{idempotency_key}" if idempotency_key else ""))
        except RevisionConflict as exc:
            raise self._conflict(exc, conflict_node_id) from exc
        except BlueprintValidationError as exc:
            raise EditorValidationError(str(exc), details={"issues": exc.issues}) from exc

    def _candidate(self, current: BlueprintNode, *, payload_data: Mapping[str, Any],
                   operation: str, request_id: str, actor: str,
                   changes: Mapping[str, Any]) -> BlueprintNode:
        model = PAYLOAD_MODELS[str(current.node_type)]
        payload = model.model_validate(dict(payload_data))
        return build_edited_node(
            current, payload=payload,
            provenance_extra={"operation": operation, "actor": actor,
                              "request_id": request_id,
                              "source_revision": int(current.revision),
                              "changed_fields": sorted(changes)})

    def _assert_valid(self, candidate: BlueprintNode, *, node_id: str) -> None:
        known = {node.node_id: node for node in self.repository.all_nodes()}
        known[candidate.node_id] = candidate
        parent = known.get(candidate.parent_id) if candidate.parent_id else None
        linked = PARENT_LINKED_IDENTITY.get(candidate.node_type)
        if linked:
            payload = payload_dict(candidate)
            if payload.get(linked) != candidate.parent_id:
                raise EditorValidationError(
                    f"{candidate.node_type} 的 {linked} 必须与 parent_id 一致",
                    details={"node_id": node_id, "field": linked,
                             "value": payload.get(linked),
                             "parent_id": candidate.parent_id,
                             "hint": "结构关系请使用 move_node"})
        try:
            require_valid(candidate, parent=parent, known=known)
        except BlueprintValidationError as exc:
            raise EditorValidationError(
                f"编辑后的节点未通过校验：{exc}", details={"issues": exc.issues,
                                                          "node_id": node_id}) from exc

    def _assert_structural_identity(self, current: BlueprintNode,
                                    source: BlueprintNode) -> None:
        """§63：restore 也必须遵守结构 identity（不能借恢复偷偷改结构）。"""

        fields = STRUCTURAL_IDENTITY_FIELDS.get(current.node_type, ())
        before, after = payload_dict(current), payload_dict(source)
        changed = [field for field in fields if before.get(field) != after.get(field)]
        if changed:
            raise EditorPreserveViolation(
                f"restore 会改动结构 identity 字段：{changed}",
                details={"node_id": current.node_id, "changed_fields": changed,
                         "hint": "结构关系请使用 move_node；restore 只恢复内容字段"})

    def _record(self, *, operation: str, node_id: str, actor: str, request_id: str,
                source_revision: int, result_revision: int,
                changed_fields: Sequence[str] = (), reason: str = "",
                status: str = "applied", idempotency_key: str = "",
                ai: Mapping[str, Any] | None = None,
                impact: Mapping[str, Any] | None = None,
                extra: Mapping[str, Any] | None = None,
                operation_id: str = "") -> EditorOperationRecord:
        record = EditorOperationRecord(
            operation_id=operation_id, novel_id=self.novel_id, operation=operation,
            node_id=node_id, actor=actor, request_id=request_id,
            source_revision=int(source_revision), result_revision=int(result_revision),
            changed_fields=tuple(sorted({str(value) for value in changed_fields
                                         if str(value)})),
            reason=reason, status=status, idempotency_key=idempotency_key,
            created_at=utc_now(), ai=dict(ai or {}), impact=dict(impact or {}),
            extra=dict(extra or {}))
        self.store.record_operation(record)
        return record

    def _record_review(self, *, node_id: str, revision: int, decision: str, actor: str,
                       reason: str, resulting_revision: int) -> ReviewDecision:
        record = ReviewDecision(node_id=node_id, novel_id=self.novel_id,
                                revision=int(revision), decision=decision, actor=actor,
                                reason=reason,
                                operation_id=new_request_id("review"),
                                created_at=utc_now(),
                                resulting_revision=int(resulting_revision))
        self.store.record_review(record)
        return record

    def _replay(self, idempotency_key: str) -> dict[str, Any]:
        if not str(idempotency_key or "").strip():
            return {}
        prior = self.store.find_by_idempotency(idempotency_key)
        if not prior:
            return {}
        if str(prior.get("status") or "") == "rejected":
            # 被拒绝的操作没有产生 revision → 允许用同一 key 重试
            return {}
        return prior

    def _replay_edit_result(self, prior: Mapping[str, Any]) -> EditResult:
        return EditResult(
            node_id=str(prior.get("node_id") or ""), novel_id=self.novel_id,
            status="applied", before_revision=int(prior.get("source_revision") or 0),
            revision=int(prior.get("result_revision") or 0),
            changed_fields=tuple(prior.get("changed_fields") or ()),
            operation_id=str(prior.get("operation_id") or ""),
            request_id=str(prior.get("request_id") or ""),
            notes=("idempotent replay：该 idempotency_key 已执行过，未产生新 revision",))

    def _replay_rewrite_result(self, prior: Mapping[str, Any]) -> RewriteResult:
        ai = dict(prior.get("ai") or {})
        return RewriteResult(
            node_id=str(prior.get("node_id") or ""), novel_id=self.novel_id,
            status="applied",
            target_fields=tuple(ai.get("target_fields") or ()),
            before_revision=int(prior.get("source_revision") or 0),
            revision=int(prior.get("result_revision") or 0),
            changed_fields=tuple(prior.get("changed_fields") or ()),
            operation_id=str(prior.get("operation_id") or ""),
            request_id=str(prior.get("request_id") or ""),
            model=str(ai.get("model") or ""), provider=str(ai.get("provider") or ""),
            contract_id=str(ai.get("contract_id") or ""),
            notes=("idempotent replay：未再次调用模型、未产生新 revision",))

    def _replay_approval(self, prior: Mapping[str, Any]) -> ApprovalResult:
        extra = dict(prior.get("extra") or {})
        decision = "accepted" if prior.get("operation") == "accept" else "rejected"
        return ApprovalResult(
            node_id=str(prior.get("node_id") or ""), novel_id=self.novel_id,
            decision=decision,
            reviewed_revision=int(extra.get("reviewed_revision")
                                  or prior.get("source_revision") or 0),
            revision=int(prior.get("result_revision") or 0),
            status=str(prior.get("status") or "recorded"),
            operation_id=str(prior.get("operation_id") or ""), idempotent=True,
            notes=("idempotent replay：该 idempotency_key 已执行过",))

    def _replay_restore(self, prior: Mapping[str, Any]) -> RestoreResult:
        extra = dict(prior.get("extra") or {})
        return RestoreResult(
            node_id=str(prior.get("node_id") or ""), novel_id=self.novel_id,
            operation=str(prior.get("operation") or "restore"),
            restored_from=int(extra.get("restored_from") or 0),
            before_revision=int(prior.get("source_revision") or 0),
            revision=int(prior.get("result_revision") or 0), status="applied",
            changed_fields=tuple(prior.get("changed_fields") or ()),
            operation_id=str(prior.get("operation_id") or ""),
            notes=("idempotent replay：未产生新 revision",))


def _protected_for(node_type: str) -> tuple[str, ...]:
    from .patch import PROTECTED_FIELDS

    return tuple(sorted({*PROTECTED_FIELDS,
                         *STRUCTURAL_IDENTITY_FIELDS.get(node_type, ())}))


def _task_for(node_type: str) -> str:
    """节点类型 → 生成任务名（复用 generation 的映射，不重复维护）。"""

    try:
        return task_for_node_type(str(node_type))
    except Exception as exc:  # noqa: BLE001 - 统一映射为 editor 错误（§75）
        raise EditorOperationRejected(
            f"{node_type} 没有可用的重生成任务",
            details={"node_type": str(node_type)}) from exc


__all__ = ["BlueprintEditorService"]
