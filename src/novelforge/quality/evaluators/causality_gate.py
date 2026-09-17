"""Q5 Causality（V4-05 §17）：因果图上的结构化检测。

检测：CAUSAL_GAP / ORPHAN_EVENT / CIRCULAR_DEPENDENCY / UNSUPPORTED_PAYOFF /
UNMOTIVATED_DECISION / DEAD_BRANCH。
"""

from __future__ import annotations

from typing import Any, Sequence

from ..contracts import QualityEvidence, QualityIssue, make_issue
from ..contracts import QualityScope
from ..registry import EvaluatorRegistry, EvaluatorSpec
from .base import EvaluationContext, stable_scope, text_of

EVALUATOR_ID = "quality.causality.v1"


def _causal_edges(context: EvaluationContext) -> list[tuple[str, str, str]]:
    edges: list[tuple[str, str, str]] = []
    for node in context.nodes_of_type("causal_link"):
        payload = context.payload(node)
        source = str(payload.get("source_node") or "")
        target = str(payload.get("target_node") or "")
        if source and target:
            edges.append((source, target, str(payload.get("relation") or "causes")))
    return edges


def _find_cycle(edges: Sequence[tuple[str, str, str]]) -> list[str] | None:
    graph: dict[str, list[str]] = {}
    for source, target, _relation in edges:
        graph.setdefault(source, []).append(target)
    visited: set[str] = set()
    stack: set[str] = set()
    path: list[str] = []

    def walk(node_id: str) -> list[str] | None:
        if node_id in stack:
            index = path.index(node_id) if node_id in path else 0
            return path[index:] + [node_id]
        if node_id in visited:
            return None
        visited.add(node_id)
        stack.add(node_id)
        path.append(node_id)
        for neighbour in sorted(graph.get(node_id, [])):
            cycle = walk(neighbour)
            if cycle:
                return cycle
        stack.discard(node_id)
        path.pop()
        return None

    for node_id in sorted(graph):
        cycle = walk(node_id)
        if cycle:
            return cycle
    return None


def evaluate(context: EvaluationContext) -> Sequence[QualityIssue]:
    issues: list[QualityIssue] = []
    scenes = context.nodes_of_type("scene")
    if not scenes:
        return issues
    edges = _causal_edges(context)
    incoming = {target for _source, target, _relation in edges}
    outgoing = {source for source, _target, _relation in edges}

    # 1. CAUSAL_GAP：非首场场景没有 incoming，且不是由上一场 outcome 自然衔接
    for index, node in enumerate(scenes):
        if index == 0 or node.node_id in incoming:
            continue
        payload = context.payload(node)
        has_reason = bool(str(payload.get("escalation") or "").strip()) and bool(
            str(payload.get("conflict") or "").strip())
        if has_reason:
            continue
        scope = stable_scope(node)
        evidence = QualityEvidence(
            evidence_id=f"{node.node_id}:causal-gap",
            kind="graph",
            explanation=("本场既没有因果链入边，也没有 escalation+conflict 作为原因，"
                         "事件显得突然发生"),
            node_ids=(node.node_id,), revision=node.revision,
            comparison={"index": index, "incoming_edges": len(incoming)})
        issues.append(make_issue(
            code="CAUSAL_GAP", novel_id=context.novel_id, scope=scope,
            reason="关键结果缺少原因", evidence=[evidence],
            evaluator_id=EVALUATOR_ID))

    # 2. ORPHAN_EVENT：没有入边也没有出边，且没有 setup / payoff
    for node in scenes:
        payload = context.payload(node)
        if node.node_id in incoming or node.node_id in outgoing:
            continue
        if (payload.get("setup") or []) or (payload.get("payoff") or []):
            continue
        scope = stable_scope(node)
        evidence = QualityEvidence(
            evidence_id=f"{node.node_id}:orphan",
            kind="graph",
            explanation="本场既不由前因产生，也不产生后果，且没有 setup / payoff",
            node_ids=(node.node_id,), revision=node.revision)
        issues.append(make_issue(
            code="ORPHAN_EVENT", novel_id=context.novel_id, scope=scope,
            reason="孤立事件（无因果邻居）", evidence=[evidence],
            evaluator_id=EVALUATOR_ID))

    # 3. CIRCULAR_DEPENDENCY
    cycle = _find_cycle(edges)
    if cycle:
        # identity 只取决于环本身（与请求 scope 无关）
        scope = QualityScope(novel_id=context.novel_id,
                             node_ids=tuple(sorted(set(cycle))), kind="nodes")
        evidence = QualityEvidence(
            evidence_id="causal:cycle", kind="graph",
            explanation="因果链出现环：" + " → ".join(cycle),
            node_ids=tuple(cycle), comparison={"cycle": cycle})
        issues.append(make_issue(
            code="CIRCULAR_DEPENDENCY", novel_id=context.novel_id, scope=scope,
            reason="因果链存在循环依赖", evidence=[evidence],
            evaluator_id=EVALUATOR_ID))

    # 4. UNSUPPORTED_PAYOFF：payoff 没有绑定 setup
    for node in context.nodes_of_type("payoff"):
        payload = context.payload(node)
        if payload.get("resolves_setup_ids"):
            continue
        scope = stable_scope(node)
        evidence = QualityEvidence(
            evidence_id=f"{node.node_id}:unsupported",
            kind="node_field",
            explanation="payoff 的 resolves_setup_ids 为空：回收没有前置埋设",
            node_ids=(node.node_id,), revision=node.revision,
            excerpt=str(payload.get("result") or "")[:200])
        issues.append(make_issue(
            code="UNSUPPORTED_PAYOFF", novel_id=context.novel_id, scope=scope,
            reason="回收没有前置埋设支撑", evidence=[evidence],
            evaluator_id=EVALUATOR_ID))

    # 5. UNMOTIVATED_DECISION：决定场景没有前置目标
    previous_goals: set[str] = set()
    for node in scenes:
        payload = context.payload(node)
        functions = set(payload.get("story_function") or [])
        goals = {str(value) for value in (payload.get("character_goals") or [])}
        if "decision" in functions and not (goals or previous_goals):
            scope = stable_scope(node)
            evidence = QualityEvidence(
                evidence_id=f"{node.node_id}:decision",
                kind="graph",
                explanation="标记为 decision 的场景没有任何前置目标作为动机来源",
                node_ids=(node.node_id,), revision=node.revision)
            issues.append(make_issue(
                code="UNMOTIVATED_DECISION", novel_id=context.novel_id, scope=scope,
                reason="关键决定缺少动机", evidence=[evidence],
                evaluator_id=EVALUATOR_ID))
        previous_goals |= goals

    # 6. DEAD_BRANCH：setup 既没有 payoff 也没有在后续场景被引用
    payoffs = context.nodes_of_type("payoff")
    bound = {str(value) for node in payoffs
             for value in (context.payload(node).get("resolves_setup_ids") or [])}
    later_text = " ".join(text_of(context.payload(node), "scene_purpose", "outcome",
                                  "turn", "next_hook")
                          for node in scenes[1:])
    for node in context.nodes_of_type("setup"):
        payload = context.payload(node)
        content = str(payload.get("content") or "")
        if node.node_id in bound or (content and content in later_text):
            continue
        scope = stable_scope(node)
        evidence = QualityEvidence(
            evidence_id=f"{node.node_id}:dead-branch",
            kind="graph",
            explanation="setup 没有被任何 payoff 绑定，也没有在后续场景被引用",
            node_ids=(node.node_id,), revision=node.revision,
            excerpt=content[:200])
        issues.append(make_issue(
            code="DEAD_BRANCH", novel_id=context.novel_id, scope=scope,
            reason="线索此后不再被使用", evidence=[evidence],
            evaluator_id=EVALUATOR_ID))
    return issues


def register(registry: EvaluatorRegistry) -> None:
    registry.register(EvaluatorSpec(
        evaluator_id=EVALUATOR_ID, version=1, gate="Q5", kind="deterministic",
        supported_node_types=("scene", "chapter", "setup", "payoff", "causal_link"),
        required_context=("blueprint_nodes",),
        description="因果图：gap / orphan / cycle / 未支撑回收 / 无动机决定 / 死线"),
        evaluate)


__all__ = ["EVALUATOR_ID", "evaluate", "register"]
