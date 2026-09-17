"""Q9 Delivery Readiness（V4-05 §21、§72）。

只检查 Blueprint 是否可以进入交付环节（readiness），**不实现导出**（V4-07）。
"""

from __future__ import annotations

from typing import Any, Sequence

from ..contracts import QualityEvidence, QualityIssue, make_issue
from ..contracts import QualityScope
from ..registry import EvaluatorRegistry, EvaluatorSpec
from .base import EvaluationContext
from .style_gate import PLACEHOLDER_PATTERNS

EVALUATOR_ID = "quality.delivery.v1"

REQUIRED_TYPES: tuple[str, ...] = ("premise", "story_arc", "chapter", "scene")


def blueprint_scope(context: EvaluationContext) -> QualityScope:
    """整图 scope（与请求 scope 无关，保证 issue_id 稳定）。"""

    return QualityScope(novel_id=context.novel_id, kind="blueprint")


def evaluate(context: EvaluationContext) -> Sequence[QualityIssue]:
    issues: list[QualityIssue] = []
    # Q9 是**交付就绪度**：对象是整个 Blueprint，不是本次请求的 scope
    # （否则「只复核 changed scope」会把缺少 premise / story_arc 误报为交付缺口）
    nodes = list(context.nodes.values())
    by_type: dict[str, list[Any]] = {}
    for node in nodes:
        by_type.setdefault(node.node_type, []).append(node)

    def add(code: str, reason: str, *, node_ids: Sequence[str] = (),
            explanation: str, kind: str = "graph", extra: dict[str, Any] | None = None,
            suffix: str = "") -> None:
        # issue identity 必须与"本次请求的 scope"无关：图级问题用稳定的 blueprint scope，
        # 有具体节点的用该节点集合（否则修复前后 / 不同 scope 下 issue_id 会漂移）
        scope = (context.scope_for(
            [node for node in nodes if node.node_id in set(node_ids)], kind="nodes")
            if node_ids else blueprint_scope(context))
        evidence = QualityEvidence(
            evidence_id=f"{code}:{'-'.join(node_ids) or 'blueprint'}",
            kind=kind, explanation=explanation, node_ids=tuple(node_ids),
            comparison=dict(extra or {}))
        issues.append(make_issue(code=code, novel_id=context.novel_id, scope=scope,
                                 reason=reason, evidence=[evidence],
                                 evaluator_id=EVALUATOR_ID, suffix=suffix,
                                 provenance=dict(extra or {})))

    # 1. 必需节点
    missing = [value for value in REQUIRED_TYPES if not by_type.get(value)]
    if missing:
        add("DELIVERY_MISSING_REQUIRED_NODE",
            f"缺少交付必需节点类型：{', '.join(missing)}",
            explanation="交付前 Blueprint 必须包含核心节点", extra={"missing": missing})

    # 2. 章节 / 场景
    chapters = by_type.get("chapter") or []
    scenes = by_type.get("scene") or []
    if chapters and not scenes:
        add("DELIVERY_MISSING_CHAPTER_OR_SCENE", "存在章节但没有任何场景",
            node_ids=[node.node_id for node in chapters],
            explanation="章节至少需要一个场景才能交付")
    for chapter in chapters:
        if not context.children(chapter.node_id, "scene"):
            add("DELIVERY_MISSING_CHAPTER_OR_SCENE",
                f"{chapter.node_id} 没有场景",
                node_ids=[chapter.node_id],
                explanation="每个章节至少需要一个场景", suffix=chapter.node_id)

    # 3. 未回收 setup（来自 Blueprint 的 setup / payoff 绑定）
    payoffs = by_type.get("payoff") or []
    bound = {str(value) for node in payoffs
             for value in (context.payload(node).get("resolves_setup_ids") or [])}
    for setup in by_type.get("setup") or []:
        payload = context.payload(setup)
        if setup.node_id in bound or str(payload.get("status")) == "paid":
            continue
        if str(payload.get("status")) == "abandoned":
            continue
        add("DELIVERY_UNPAID_SETUP", f"{setup.node_id} 尚未回收",
            node_ids=[setup.node_id], kind="node_field",
            explanation=str(payload.get("content") or "")[:200],
            suffix=setup.node_id)

    # 4. 孤立节点
    for node in nodes:
        if node.node_type in ("premise", "theme", "world", "story_arc",
                              "causal_link", "setup", "payoff"):
            continue
        if node.parent_id and node.parent_id in context.nodes:
            continue
        if node.node_type in ("character",):
            if any(child.node_type == "character_arc"
                   for child in context.children(node.node_id)):
                continue
        add("DELIVERY_ORPHAN_NODE", f"{node.node_id} 没有父节点",
            node_ids=[node.node_id], explanation="孤立节点无法进入交付结构",
            suffix=node.node_id)

    # 5. 占位内容
    for node in nodes:
        payload = context.payload(node)
        text = " ".join(str(payload.get(field) or "") for field in
                        ("title", "goal", "outcome", "scene_purpose"))
        hits = [pattern for pattern in PLACEHOLDER_PATTERNS
                if pattern.lower() in text.lower()]
        if not hits:
            continue
        add("DELIVERY_PLACEHOLDER", f"{node.node_id} 含占位内容（{'、'.join(hits)}）",
            node_ids=[node.node_id], kind="node_field", explanation=text[:200],
            suffix=node.node_id)

    # 6. 跨作品污染
    foreign = [node.node_id for node in nodes if node.novel_id != context.novel_id]
    if foreign:
        add("DELIVERY_CROSS_NOVEL_CONTAMINATION",
            f"检测到 {len(foreign)} 个其他作品的节点", node_ids=foreign,
            explanation="交付物只允许包含当前作品的数据",
            extra={"foreign": sorted(foreign)})

    # 7. 未处理的 blocker（上游 report 通过 extra 传入）
    prior = [row for row in (context.extra.get("prior_issues") or [])
             if getattr(row, "severity", "") == "blocker"
             and getattr(row, "gate", "") != "Q9"]
    if prior:
        add("DELIVERY_UNRESOLVED_BLOCKER",
            f"仍有 {len(prior)} 个 blocker 未处理",
            node_ids=sorted({node_id for row in prior
                             for node_id in getattr(row, "scope", None).node_ids
                             if node_id} if prior else ()),
            explanation="交付前必须处理所有 blocker",
            extra={"issue_ids": [row.issue_id for row in prior]})
    return issues


def register(registry: EvaluatorRegistry) -> None:
    registry.register(EvaluatorSpec(
        evaluator_id=EVALUATOR_ID, version=1, gate="Q9", kind="deterministic",
        required_context=("blueprint_nodes",),
        description="交付就绪度：必需节点 / 未回收 setup / 孤立节点 / 占位 / 跨作品"),
        evaluate)


__all__ = ["EVALUATOR_ID", "REQUIRED_TYPES", "evaluate", "register"]
