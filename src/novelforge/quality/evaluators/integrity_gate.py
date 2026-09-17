"""Q1 Integrity（V4-04 §13）：ownership / revision 链 / index / provenance / 必需节点。"""

from __future__ import annotations

from typing import Any, Sequence

from ..contracts import QualityEvidence, QualityIssue, make_issue
from ..contracts import QualityScope
from ..registry import EvaluatorRegistry, EvaluatorSpec
from .base import EvaluationContext, stable_scope

EVALUATOR_ID = "quality.integrity.v1"

REQUIRED_NODE_TYPES: tuple[str, ...] = ("premise", "story_arc", "chapter", "scene")


def _graph_scope(context: EvaluationContext):
    return QualityScope(novel_id=context.novel_id, kind="blueprint",
                        node_types=tuple(sorted({node.node_type
                                                 for node in context.nodes.values()})))


def _scope_for(context: EvaluationContext, nodes: Sequence[str]) -> QualityScope:
    """有具体节点 → 该节点集合（稳定 identity）；否则整图 scope。"""

    resolved = tuple(sorted({str(value) for value in nodes if value}))
    return (_graph_scope(context) if not resolved
            else QualityScope(novel_id=context.novel_id, node_ids=resolved,
                               node_types=tuple(sorted({
                                   context.nodes[node_id].node_type
                                   for node_id in resolved
                                   if node_id in context.nodes})), kind="nodes"))


def evaluate(context: EvaluationContext) -> Sequence[QualityIssue]:
    issues: list[QualityIssue] = []

    def add(code: str, reason: str, *, nodes: Sequence[str], evidence_kind: str,
            explanation: str, extra: dict[str, Any] | None = None,
            suffix: str = "") -> None:
        scope = _scope_for(context, nodes)
        evidence = QualityEvidence(
            evidence_id=f"{code}:{'-'.join(nodes) or 'graph'}",
            kind=evidence_kind, explanation=explanation, node_ids=tuple(nodes),
            comparison=dict(extra or {}))
        issues.append(make_issue(code=code, novel_id=context.novel_id, scope=scope,
                                 reason=reason, evidence=[evidence],
                                 evaluator_id=EVALUATOR_ID,
                                 provenance=dict(extra or {}),
                                 suffix=suffix))

    # 1. ownership：目标节点必须属于本作品
    foreign = [node.node_id for node in context.scoped()
               if node.novel_id != context.novel_id]
    if foreign:
        add("OWNERSHIP_MISMATCH",
            f"检测到 {len(foreign)} 个不属于本作品的节点",
            nodes=foreign, evidence_kind="graph",
            explanation="节点 novel_id 与请求作品不一致（禁止跨作品）",
            extra={"foreign_nodes": sorted(foreign)})

    # 2. 重复 node_id（同一 graph 内）
    seen: dict[str, int] = {}
    for node in context.nodes.values():
        seen[node.node_id] = seen.get(node.node_id, 0) + 1
    duplicates = sorted(node_id for node_id, count in seen.items() if count > 1)
    if duplicates:
        add("DUPLICATE_NODE_ID", "同一 node_id 出现多次", nodes=duplicates,
            evidence_kind="graph", explanation="graph 内 node_id 必须唯一")

    # 3. revision 链（借助 repository，只读）
    if context.repository is not None:
        for node in context.scoped():
            revisions = context.repository.list_revisions(node.node_id)
            if revisions and revisions != list(range(1, len(revisions) + 1)):
                add("REVISION_CHAIN_BROKEN",
                    f"{node.node_id} 的 revision 序号不连续", nodes=[node.node_id],
                    evidence_kind="metric",
                    explanation="revision 必须从 1 连续递增（append-only）",
                    extra={"revisions": revisions}, suffix=node.node_id)
            if node.parent_revision and node.parent_revision != node.revision - 1:
                add("REVISION_CHAIN_BROKEN",
                    f"{node.node_id} 的 parent_revision 不指向上一版",
                    nodes=[node.node_id], evidence_kind="metric",
                    explanation=f"parent_revision={node.parent_revision}，"
                                f"revision={node.revision}",
                    suffix=f"{node.node_id}:parent")
        snapshot = context.repository.index_snapshot()
        indexed = {row.node_id for row in context.repository.all_nodes()}
        listed = set((snapshot.get("nodes") or {}).keys())
        missing = sorted(listed - indexed)
        if missing:
            add("INDEX_INCONSISTENT", "index 中的节点缺少可读 revision",
                nodes=missing, evidence_kind="graph",
                explanation="index 记录了节点，但节点文件不可读")

    # 4. provenance / source_ids（生成出来的节点必须可追溯）
    for node in context.scoped():
        if node.node_type in ("causal_link", "setup", "payoff"):
            continue
        if not node.source_ids or not node.generation_contract:
            add("PROVENANCE_INVALID",
                f"{node.node_id} 缺少 provenance（source_ids / contract）",
                nodes=[node.node_id], evidence_kind="node_field",
                explanation="每个生成节点必须带 source_ids 与 generation_contract",
                suffix=node.node_id)

    # 5. 必需节点（只在整图 scope 下检查）
    if context.scope.kind in ("blueprint", "changed"):
        present = {node.node_type for node in context.nodes.values()}
        missing_types = [value for value in REQUIRED_NODE_TYPES if value not in present]
        if missing_types:
            add("MISSING_REQUIRED_NODE",
                f"缺少必需节点类型：{', '.join(missing_types)}", nodes=[],
                evidence_kind="graph",
                explanation="Blueprint 完整性要求", extra={"missing": missing_types})

    # 6. 幂等记录一致性
    if context.repository is not None:
        snapshot = context.repository.index_snapshot()
        for key, row in (snapshot.get("idempotency") or {}).items():
            stored = context.repository.get_revision(str(row.get("node_id")),
                                                     int(row.get("revision")))
            if stored is None:
                add("IDEMPOTENCY_INCONSISTENT",
                    "idempotency 记录指向不存在的 revision",
                    nodes=[str(row.get("node_id"))], evidence_kind="metric",
                    explanation=f"key={key}", suffix=key)
    return issues


def register(registry: EvaluatorRegistry) -> None:
    registry.register(EvaluatorSpec(
        evaluator_id=EVALUATOR_ID, version=1, gate="Q1", kind="deterministic",
        required_context=("blueprint_nodes", "repository"),
        description="ownership / revision / index / provenance / 必需节点"),
        evaluate)


__all__ = ["EVALUATOR_ID", "REQUIRED_NODE_TYPES", "evaluate", "register"]
