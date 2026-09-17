"""Q0 Schema（V4-04 §12）：直接 ADAPT `blueprint.validation`，不复制规则。"""

from __future__ import annotations

from typing import Any, Mapping, Sequence

from novelforge.blueprint import validate_graph, validate_node

from ..contracts import QualityEvidence, QualityIssue, QualityScope, make_issue
from ..registry import EvaluatorRegistry, EvaluatorSpec
from .base import EvaluationContext, stable_scope

EVALUATOR_ID = "quality.schema.v1"

#: blueprint.validation 的 issue code → Quality issue code
CODE_MAP: dict[str, str] = {
    "NODE_ID_INVALID": "SCHEMA_INVALID",
    "NODE_TYPE_UNKNOWN": "SCHEMA_INVALID",
    "PAYLOAD_MODEL_MISMATCH": "SCHEMA_INVALID",
    "TRANSITION_INTENT_INVALID": "SCHEMA_INVALID",
    "SEQUENCE_DUPLICATE": "SEQUENCE_INVALID",
    "SEQUENCE_INVALID": "SEQUENCE_INVALID",
    "PARENT_TYPE_INVALID": "PARENT_TYPE_INVALID",
    "PARENT_NOT_FOUND": "REFERENCE_BROKEN",
    "PARENT_REQUIRED": "REFERENCE_BROKEN",
    "CHARACTER_NOT_FOUND": "REFERENCE_BROKEN",
    "CHAPTER_NOT_FOUND": "REFERENCE_BROKEN",
    "CAUSAL_ENDPOINT_NOT_FOUND": "REFERENCE_BROKEN",
    "SETUP_NOT_FOUND": "REFERENCE_BROKEN",
    "TRANSITION_SCOPE_MISMATCH": "SCHEMA_INVALID",
}

#: 只出现在 `validate_graph`（图级）里的 code 子集：per-node 校验不产生它们
GRAPH_ONLY_CODES: frozenset[str] = frozenset({"SEQUENCE_DUPLICATE",
                                             "SEQUENCE_INVALID"})


def evaluate(context: EvaluationContext) -> Sequence[QualityIssue]:
    issues: list[QualityIssue] = []
    for node in context.scoped():
        parent = context.nodes.get(node.parent_id) if node.parent_id else None
        rows = validate_node(node, parent=parent, known=context.nodes)
        for row in rows:
            mapped = CODE_MAP.get(str(row.get("code")))
            if mapped is None:
                continue
            scope = stable_scope(node)
            evidence = QualityEvidence(
                evidence_id=f"{node.node_id}:{row.get('code')}",
                kind="node_field",
                explanation=str(row.get("message") or row.get("code")),
                source_ids=context.source_ids(node), node_ids=(node.node_id,),
                revision=node.revision, excerpt=str(row.get("reference") or ""),
                comparison={"blueprint_code": row.get("code")})
            issues.append(make_issue(
                code=mapped, novel_id=context.novel_id, scope=scope,
                reason=str(row.get("message") or "Blueprint 结构校验未通过"),
                evidence=[evidence], evaluator_id=EVALUATOR_ID,
                provenance={"blueprint_code": row.get("code")},
                suffix=str(row.get("code"))))
    issues.extend(_graph_level(context))
    return issues


def _graph_level(context: EvaluationContext) -> Sequence[QualityIssue]:
    """sequence 唯一性 / 取值必须按父节点判断，只能由图级校验产出。"""

    nodes = sorted(context.nodes.values(),
                   key=lambda item: (item.node_type, item.sequence, item.node_id))
    report = validate_graph(nodes, novel_id=context.novel_id)
    issues: list[QualityIssue] = []
    for row in report.get("issues", ()):
        code = str(row.get("code") or "")
        if code not in GRAPH_ONLY_CODES:
            continue
        parent = context.nodes.get(str(row.get("node_id") or ""))
        scope = (stable_scope(parent) if parent is not None else
                 QualityScope(novel_id=context.novel_id, kind="blueprint"))
        evidence = QualityEvidence(
            evidence_id=f"{row.get('node_id')}:{code}", kind="graph",
            explanation=str(row.get("message") or code),
            node_ids=((parent.node_id,) if parent is not None else ()),
            revision=(parent.revision if parent is not None else None),
            comparison={"blueprint_code": code})
        issues.append(make_issue(
            code=CODE_MAP[code], novel_id=context.novel_id, scope=scope,
            reason=str(row.get("message") or "子节点 sequence 非法"),
            evidence=[evidence], evaluator_id=EVALUATOR_ID,
            provenance={"blueprint_code": code},
            suffix=str(row.get("node_id") or "")))
    return issues


def register(registry: EvaluatorRegistry) -> None:
    registry.register(EvaluatorSpec(
        evaluator_id=EVALUATOR_ID, version=1, gate="Q0", kind="deterministic",
        supported_node_types=(), required_context=("blueprint_nodes",),
        description="ADAPT blueprint.validation：schema / parent / 引用 / sequence"),
        evaluate)


__all__ = ["CODE_MAP", "EVALUATOR_ID", "GRAPH_ONLY_CODES", "evaluate", "register"]
