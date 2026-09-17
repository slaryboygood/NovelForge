"""Change Impact / Quality Invalidation（V4-06 §71–§73）。

Blueprint 是图：改一个节点可能影响下游。本模块**只报告**，永远不自动修改下游节点。

```text
direct_node           被改的节点
changed_fields        改了哪些字段
dependent_nodes       结构上受影响的节点（确定性遍历）
quality_invalidations 质量结论需要重新确认的节点（= direct + dependent）
reasons               为什么算受影响（可解释）
```
"""

from __future__ import annotations

from typing import Any, Iterable, Sequence

from novelforge.blueprint import BlueprintNode

from .contracts import ChangeImpact


def _payload(node: BlueprintNode) -> dict[str, Any]:
    payload = getattr(node, "payload", None)
    if hasattr(payload, "model_dump"):
        return payload.model_dump(mode="json")
    return dict(payload or {})


def compute_impact(nodes: Sequence[BlueprintNode], *, node_id: str,
                   changed_fields: Iterable[str] = (), revision: int = 0,
                   novel_id: str = "") -> ChangeImpact:
    """确定性影响面（只读；调用方决定是否重新评估 / 重新生成）。"""

    by_id = {node.node_id: node for node in nodes}
    changed = tuple(sorted({str(value) for value in changed_fields if value}))
    target = by_id.get(node_id)
    reasons: dict[str, set[str]] = {}

    def mark(other: str, reason: str) -> None:
        if not other or other == node_id or other not in by_id:
            return
        reasons.setdefault(other, set()).add(reason)

    if target is not None:
        chapter_id = str(target.parent_id or "")
        for other in nodes:
            if other.node_id == node_id:
                continue
            if other.parent_id == node_id:
                mark(other.node_id, "child_of_changed_node")
                continue
            payload = _payload(other)
            if other.node_type == "scene":
                if chapter_id and str(other.parent_id or "") == chapter_id:
                    mark(other.node_id, "same_chapter_scene")
                continue
            if other.node_type == "causal_link":
                endpoints = {str(payload.get("source_node") or ""),
                             str(payload.get("target_node") or "")}
                if node_id in endpoints:
                    mark(other.node_id, "causal_endpoint_changed")
                continue
            if other.node_type == "payoff":
                resolved = {str(value) for value in
                            (payload.get("resolves_setup_ids") or [])}
                if node_id in resolved:
                    mark(other.node_id, "resolves_changed_setup")
                continue
            if other.node_type == "character_arc":
                linked = {str(value) for value in
                          list(payload.get("linked_scenes") or [])
                          + list(payload.get("linked_chapters") or [])}
                if node_id in linked:
                    mark(other.node_id, "arc_links_changed_node")
        if target.node_type == "scene" and chapter_id:
            mark(chapter_id, "scene_changed_under_chapter")

    dependent = tuple(sorted(reasons))
    invalidations = tuple(sorted({node_id, *dependent}))
    summary = (f"改了 {len(changed)} 个字段，可能影响 {len(dependent)} 个下游节点"
               if changed else f"可能影响 {len(dependent)} 个下游节点")
    return ChangeImpact(novel_id=novel_id or getattr(target, "novel_id", ""),
                        node_id=node_id, revision=int(revision),
                        changed_fields=changed, dependent_nodes=dependent,
                        quality_invalidations=invalidations,
                        reasons={key: tuple(sorted(value))
                                 for key, value in sorted(reasons.items())},
                        summary=summary)


__all__ = ["compute_impact"]
