"""Revision history / RevisionView（V4-06 §11–§13）。

History 来源是 **BlueprintRepository**（唯一 truth），editor 不再复制一份 history store：

```text
list revisions / get revision / current revision   ← repository
author / operation / request_id / review_status    ← editor metadata（若有）+ provenance 推断
```
"""

from __future__ import annotations

from typing import Any, Iterable, Mapping, Sequence

from novelforge.blueprint import BlueprintNode, BlueprintRepository

from .contracts import RevisionHistory, RevisionView

#: provenance.operation → author（§12）
OPERATION_AUTHOR: Mapping[str, str] = {
    "ai_rewrite": "ai_rewrite",
    "ai_regenerate": "ai_generation",
    "quality_repair": "ai_repair",
    "manual_patch": "human",
    "batch_patch": "human",
    "accept": "human",
    "reject": "human",
    "restore": "restore",
    "undo": "restore",
    "move": "human",
}


def author_for(node: BlueprintNode, *, operation: str = "") -> str:
    """判定该 revision 的来源（§12：human / ai_generation / ai_repair / ai_rewrite /
    restore / system）。"""

    if operation and operation in OPERATION_AUTHOR:
        return OPERATION_AUTHOR[operation]
    provenance = dict(node.provenance or {})
    recorded = str(provenance.get("operation") or "")
    if recorded in OPERATION_AUTHOR:
        return OPERATION_AUTHOR[recorded]
    if provenance.get("restored_from"):
        return "restore"
    keys = {str(value) for value in (provenance.get("task_input_keys") or ())}
    if "repair" in keys:
        return "ai_repair"
    if str(node.generation_contract or "").startswith("blueprint."):
        return "ai_generation"
    return "system"


def revision_view(node: BlueprintNode, *, is_current: bool, operation: str = "",
                  request_id: str = "", summary: str = "",
                  changed_fields: Sequence[str] = (),
                  review: Mapping[str, Any] | None = None) -> RevisionView:
    provenance = dict(node.provenance or {})
    restored_from = provenance.get("restored_from")
    decision = dict(review or {})
    return RevisionView(
        node_id=node.node_id, novel_id=node.novel_id, node_type=node.node_type,
        revision=int(node.revision), parent_revision=int(node.parent_revision),
        status=str(node.status), quality_status=str(node.quality_status),
        created_at=str(node.created_at), updated_at=str(node.updated_at),
        source=str(node.generation_contract or ""),
        author=author_for(node, operation=operation or str(decision.get("operation") or "")),
        operation=operation or str(provenance.get("operation") or ""),
        request_id=request_id or str(provenance.get("request_id") or ""),
        summary=summary or str(provenance.get("summary") or ""),
        changed_fields=tuple(sorted({str(value) for value in changed_fields
                                     if str(value)}))
        or tuple(str(value) for value in (provenance.get("changed_fields") or ())),
        source_ids=tuple(node.source_ids),
        generation_contract=str(node.generation_contract or ""),
        restored_from=(int(restored_from) if restored_from else None),
        review_status=str(decision.get("decision") or "pending"),
        review_note=str(decision.get("reason") or ""),
        is_current=bool(is_current))


def build_history(repository: BlueprintRepository, node_id: str, *,
                  operations: Iterable[Mapping[str, Any]] = (),
                  reviews: Iterable[Mapping[str, Any]] = ()) -> RevisionHistory:
    """按 revision 顺序构造 history（只读 repository + editor metadata）。"""

    by_revision: dict[int, dict[str, Any]] = {}
    for row in operations:
        if str(row.get("node_id") or "") != node_id:
            continue
        revision = int(row.get("result_revision") or 0)
        if revision:
            by_revision[revision] = dict(row)
    review_by_revision: dict[int, dict[str, Any]] = {}
    for row in reviews:
        if str(row.get("node_id") or "") != node_id:
            continue
        review_by_revision[int(row.get("revision") or 0)] = dict(row)

    current = repository.current_revision(node_id)
    views: list[RevisionView] = []
    for revision in repository.list_revisions(node_id):
        node = repository.get_revision(node_id, revision)
        if node is None:
            continue
        operation_row = by_revision.get(revision, {})
        view = revision_view(
            node, is_current=(revision == current),
            operation=str(operation_row.get("operation") or ""),
            request_id=str(operation_row.get("request_id") or ""),
            summary=str(operation_row.get("reason") or ""),
            changed_fields=tuple(operation_row.get("changed_fields") or ()),
            review=review_by_revision.get(revision))
        views.append(view)
    return RevisionHistory(novel_id=repository.novel_id, node_id=node_id,
                           current_revision=current, revisions=tuple(views),
                           operations=tuple(dict(row) for row in operations
                                            if str(row.get("node_id") or "") == node_id))


__all__ = ["OPERATION_AUTHOR", "author_for", "build_history", "revision_view"]
