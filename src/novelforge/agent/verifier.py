"""AgentVerifier（V4-11 §39–§41）：只验证 step 的 success_criteria 是否成立。

它不是新的 QualityService：故事质量判断仍归 QualityService（§41）；
这里只检查「业务返回是否真的产生了预期效果」。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

from .contracts import AgentStep
from .ports import (
    AgentDeliveryPort,
    AgentEditorPort,
    AgentGenerationPort,
    AgentQualityPort,
    AgentReadPort,
    DeliveryOutcome,
    EditOutcome,
    GenerationOutcome,
    QualityOutcome,
    RepairOutcome,
)


@dataclass(frozen=True)
class VerificationOutcome:
    ok: bool
    criteria: tuple[str, ...] = ()
    failed: tuple[str, ...] = ()
    details: Mapping[str, Any] = field(default_factory=dict)
    notes: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        return {"ok": bool(self.ok), "criteria": list(self.criteria),
                "failed": list(self.failed), "details": dict(self.details),
                "notes": list(self.notes)}


class AgentVerifier:
    """按 action 校验业务结果（不判断故事质量）。"""

    def __init__(self, *, read: AgentReadPort | None = None,
                 editor: AgentEditorPort | None = None,
                 quality: AgentQualityPort | None = None,
                 delivery: AgentDeliveryPort | None = None,
                 generation: AgentGenerationPort | None = None) -> None:
        self.read = read
        self.editor = editor
        self.quality = quality
        self.delivery = delivery
        self.generation = generation

    # ------------------------------------------------------------------ 入口
    def verify(self, step: AgentStep, outcome: Any, *,
               before_revision: int = 0,
               requested_fields: Sequence[str] = ()) -> VerificationOutcome:
        criteria = tuple(step.success_criteria) or ()
        failed: list[str] = []
        details: dict[str, Any] = {}
        for criterion in criteria:
            handler = getattr(self, f"_check_{criterion}", None)
            if handler is None:
                failed.append(criterion)
                details[criterion] = "no verifier for criterion"
                continue
            ok, detail = handler(step, outcome, before_revision=before_revision,
                                 requested_fields=tuple(requested_fields))
            details[criterion] = detail
            if not ok:
                failed.append(criterion)
        return VerificationOutcome(ok=not failed, criteria=criteria,
                                   failed=tuple(failed), details=details)

    # ------------------------------------------------------------- criteria
    def _check_node_exists(self, step: AgentStep, outcome: Any, **_kwargs: Any
                           ) -> tuple[bool, Any]:
        node = self._node_from(outcome) or self._read_node(step)
        return bool(node), {"node": node.as_dict() if node else None}

    def _check_status_proposed(self, step: AgentStep, outcome: Any, **_kwargs: Any
                               ) -> tuple[bool, Any]:
        node = self._node_from(outcome) or self._read_node(step)
        status = str(getattr(node, "status", "") or "")
        return status == "proposed", {"status": status}

    def _check_revision_changed(self, step: AgentStep, outcome: Any, *,
                                before_revision: int = 0, **_kwargs: Any
                                ) -> tuple[bool, Any]:
        after = int(getattr(outcome, "revision", 0) or 0)
        return after > int(before_revision), {"before": int(before_revision),
                                              "after": after}

    def _check_fields_match(self, step: AgentStep, outcome: Any, *,
                            requested_fields: Sequence[str] = (), **_kwargs: Any
                            ) -> tuple[bool, Any]:
        changed = set(getattr(outcome, "changed_fields", ()) or ())
        wanted = set(requested_fields)
        missing = sorted(wanted - changed) if wanted else []
        return not missing, {"changed_fields": sorted(changed), "missing": missing}

    def _check_report_exists(self, step: AgentStep, outcome: Any, **_kwargs: Any
                             ) -> tuple[bool, Any]:
        report_id = str(getattr(outcome, "report_id", "") or "")
        return bool(report_id), {"report_id": report_id}

    def _check_plan_exists(self, step: AgentStep, outcome: Any, **_kwargs: Any
                           ) -> tuple[bool, Any]:
        row = dict(outcome or {}) if isinstance(outcome, Mapping) else {}
        status = str(row.get("status") or "")
        return bool(row), {"status": status, "steps": len(row.get("steps") or [])}

    def _check_verification_status(self, step: AgentStep, outcome: Any,
                                   **_kwargs: Any) -> tuple[bool, Any]:
        if isinstance(outcome, RepairOutcome):
            verification = dict(outcome.verification or {})
        else:
            verification = dict((outcome or {}).get("verification") or {}) \
                if isinstance(outcome, Mapping) else {}
        status = str(verification.get("status") or "")
        needs_human = bool(verification.get("needs_human_review")) or \
            status in ("needs_human_review", "needs_author_decision")
        ok = status in ("resolved", "partial", "repaired", "no_issues", "skipped") \
            or needs_human
        return ok, {"verification_status": status, "needs_human_review": needs_human}

    def _check_verification_recorded(self, step: AgentStep, outcome: Any,
                                     **_kwargs: Any) -> tuple[bool, Any]:
        if isinstance(outcome, RepairOutcome):
            verification = dict(outcome.verification or {})
        else:
            verification = dict((outcome or {}).get("verification") or {}) \
                if isinstance(outcome, Mapping) else {}
        return bool(verification), {"keys": sorted(verification)}

    def _check_approval_recorded(self, step: AgentStep, outcome: Any,
                                 **_kwargs: Any) -> tuple[bool, Any]:
        row = dict(outcome or {}) if isinstance(outcome, Mapping) else {}
        return bool(row.get("approval_id")), {"approval_id": row.get("approval_id", "")}

    def _check_accepted(self, step: AgentStep, outcome: Any, **_kwargs: Any
                        ) -> tuple[bool, Any]:
        status = str(getattr(outcome, "status", "") or "")
        node = self._read_node(step)
        node_status = str(getattr(node, "status", "") or "")
        return status in ("accepted", "recorded") and (not node or node_status == "accepted"), {
            "result_status": status, "node_status": node_status}

    def _check_validation_recorded(self, step: AgentStep, outcome: Any,
                                   **_kwargs: Any) -> tuple[bool, Any]:
        validation = dict(getattr(outcome, "validation", {}) or {})
        return bool(validation), {"status": str(getattr(outcome, "status", ""))}

    def _check_manifest_exists(self, step: AgentStep, outcome: Any, **_kwargs: Any
                               ) -> tuple[bool, Any]:
        manifest_id = str(getattr(outcome, "manifest_id", "") or "")
        snapshot_id = str(getattr(outcome, "snapshot_id", "") or "")
        return bool(manifest_id or snapshot_id), {"manifest_id": manifest_id,
                                                  "snapshot_id": snapshot_id}

    def _check_snapshot_recorded(self, step: AgentStep, outcome: Any, **_kwargs: Any
                                 ) -> tuple[bool, Any]:
        digest = str(getattr(outcome, "digest", "") or "")
        return bool(digest), {"snapshot_digest": digest}

    # ---------------------------------------------------------------- 内部
    @staticmethod
    def _node_from(outcome: Any) -> Any:
        if isinstance(outcome, GenerationOutcome):
            return outcome.node
        return None

    def _read_node(self, step: AgentStep) -> Any:
        node_id = str(step.target.get("node_id") or "")
        if not node_id or self.editor is None:
            return None
        try:
            return self.editor.node(node_id)
        except Exception:  # noqa: BLE001 - 读不到不算失败（由具体 criterion 判定）
            return None


__all__ = ["AgentVerifier", "VerificationOutcome"]
