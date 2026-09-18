"""Quality / Review 资源（V4-08 §12、§29、§47）：
质量摘要、issue 列表、编辑与评审摘要（全部只读，质量真相来自 Quality Store）。
"""

from __future__ import annotations

from typing import Any, Mapping

from ..contracts import ResourceSpec
from ..payloads import ResourcePayload, json_payload
from ..registry import MCPResourceRegistry
from ..uri import paginate


def _issues(context: Any) -> list[dict[str, Any]]:
    return [dict(row) for row in context.review.list_issues()]


def register(registry: MCPResourceRegistry, *, spec_source: Any = None) -> None:
    def quality_resource(context: Any, target: Any) -> ResourcePayload:
        report = context.review.latest_report()
        payload = {"novel_id": target.novel_id,
                   "stats": context.review.stats(),
                   "latest_report": {key: report.get(key) for key in
                                     ("report_id", "status", "generated_at",
                                      "digest", "node_revisions")},
                   "issues": [{"issue_id": row.get("issue_id"), "code": row.get("code"),
                               "gate": row.get("gate"), "severity": row.get("severity"),
                               "status": row.get("status")}
                              for row in _issues(context)][:20],
                   "note": "质量真相来自 Quality Store；节点上的 quality_status 只是投影"}
        return json_payload(target.uri, payload)

    def issues_resource(context: Any, target: Any) -> ResourcePayload:
        rows = [{"issue_id": row.get("issue_id"), "code": row.get("code"),
                 "gate": row.get("gate"), "severity": row.get("severity"),
                 "status": row.get("status"), "reason": row.get("reason"),
                 "scope": row.get("scope"), "revision": _issue_revision(row),
                 "evaluator_id": row.get("evaluator_id"),
                 "evidence": [{"kind": item.get("kind"),
                               "node_ids": item.get("node_ids"),
                               "revision": item.get("revision"),
                               "explanation": item.get("explanation")}
                              for item in (row.get("evidence") or [])]}
                for row in _issues(context)]
        page = paginate(rows, limit=target.limit, cursor=target.cursor)
        return json_payload(target.uri, {"novel_id": target.novel_id, **page})

    def review_resource(context: Any, target: Any) -> ResourcePayload:
        history_rows: list[dict[str, Any]] = []
        reviews: list[dict[str, Any]] = []
        for node in context.editor.repository.all_nodes():
            node_id = node.node_id
            reviews.extend(dict(row) for row in context.editor.reviews(
                node_id=node_id))
            history_rows.append({"node_id": node_id, "revision": node.revision,
                                 "status": str(node.status),
                                 "quality_status": str(node.quality_status)})
        operations = [dict(row) for row in context.editor.operations()]
        page = paginate(history_rows, limit=target.limit, cursor=target.cursor)
        payload = {"novel_id": target.novel_id,
                   "review_decisions": reviews[:200],
                   "operations": [{"operation_id": row.get("operation_id"),
                                   "operation": row.get("operation"),
                                   "node_id": row.get("node_id"),
                                   "actor": row.get("actor"),
                                   "source_revision": row.get("source_revision"),
                                   "result_revision": row.get("result_revision"),
                                   "changed_fields": row.get("changed_fields"),
                                   "reason": row.get("reason"),
                                   "status": row.get("status")}
                                  for row in operations][:200],
                   "nodes": page,
                   "note": ("review 决定属于 editor metadata；quality_status 只是投影；"
                            "quality pass ≠ accepted")}
        return json_payload(target.uri, payload)

    registry.register(ResourceSpec(
        uri="novelforge://novels/{novel_id}/quality", name="quality",
        description="质量摘要（最新报告 + issue 统计）", template=True,
        service="application.services.review.stats"),
        kinds=("quality",), handler=quality_resource)
    registry.register(ResourceSpec(
        uri="novelforge://novels/{novel_id}/quality/issues", name="quality-issues",
        description="质量 issue 列表（分页；含 evidence 摘要）", paginated=True,
        template=True,
        service="application.services.review.list_issues"),
        kinds=("issues",), handler=issues_resource)
    registry.register(ResourceSpec(
        uri="novelforge://novels/{novel_id}/review", name="review",
        description="编辑 / 评审摘要（review 决定 + editor operation 审计）",
        paginated=True, template=True,
        service="application.services.editor.get_history"),
        kinds=("review",), handler=review_resource)


def _issue_revision(row: Mapping[str, Any]) -> int:
    scope = dict(row.get("scope") or {})
    revision = int(scope.get("revision") or 0)
    if revision:
        return revision
    revisions = [int(item.get("revision") or 0)
                 for item in (row.get("evidence") or []) if item.get("revision")]
    return max(revisions) if revisions else 0


__all__ = ["register"]
