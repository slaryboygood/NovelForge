"""Q7 Narrative（V4-05 §19、§49–§51）：场景功能 / 节奏 / 高潮准备 / 收束完整性。"""

from __future__ import annotations

from typing import Any, Sequence

from ..contracts import QualityEvidence, QualityIssue, make_issue
from ..contracts import QualityScope
from ..registry import EvaluatorRegistry, EvaluatorSpec
from .base import EvaluationContext, stable_scope, text_of

EVALUATOR_ID = "quality.narrative.v1"

PASSIVE_FUNCTIONS = ("transition",)
ESCALATION_FUNCTIONS = ("escalate_conflict", "reversal", "decision", "payoff")
STAGNATION_RUN = 3


def evaluate(context: EvaluationContext) -> Sequence[QualityIssue]:
    issues: list[QualityIssue] = []
    scenes = context.nodes_of_type("scene")

    # 1. SCENE_NO_NARRATIVE_FUNCTION：没有 story_function，或只有 transition，
    #    或声称 advance_plot 但 outcome 没有变化
    for node in scenes:
        payload = context.payload(node)
        functions = [str(value) for value in (payload.get("story_function") or [])]
        outcome = str(payload.get("outcome") or "").strip()
        purpose = str(payload.get("scene_purpose") or "").strip()
        reason = ""
        if not functions:
            reason = "story_function 为空：无法说明这一场为什么存在"
        elif set(functions) <= set(PASSIVE_FUNCTIONS):
            reason = "只有 transition：删掉这一场几乎不损失内容"
        elif "advance_plot" in functions and not outcome:
            reason = "声称 advance_plot，但 outcome 为空（剧情没有实际推进）"
        if not reason:
            continue
        scope = stable_scope(node)
        evidence = QualityEvidence(
            evidence_id=f"{node.node_id}:no-function", kind="node_field",
            explanation=reason, node_ids=(node.node_id,), revision=node.revision,
            excerpt=(purpose or outcome)[:200],
            comparison={"story_function": functions, "outcome_empty": not outcome})
        issues.append(make_issue(
            code="SCENE_NO_NARRATIVE_FUNCTION", novel_id=context.novel_id,
            scope=scope, reason=reason, evidence=[evidence],
            evaluator_id=EVALUATOR_ID))

    # 2. PACING_STAGNATION：连续多场没有升级 / 转折
    run: list[Any] = []
    for node in scenes:
        payload = context.payload(node)
        functions = set(payload.get("story_function") or [])
        has_escalation = bool(functions & set(ESCALATION_FUNCTIONS)) or bool(
            str(payload.get("escalation") or "").strip())
        if has_escalation:
            if len(run) >= STAGNATION_RUN:
                issues.append(_stagnation(context, run))
            run = []
            continue
        run.append(node)
    if len(run) >= STAGNATION_RUN:
        issues.append(_stagnation(context, run))

    # 3. CLIMAX_UNPREPARED / RESOLUTION_INCOMPLETE（依赖 StoryArc）
    for arc in context.nodes_of_type("story_arc"):
        payload = context.payload(arc)
        climax = str(payload.get("climax") or "").strip()
        resolution = str(payload.get("resolution") or "").strip()
        payoff_like = [node for node in scenes
                       if set(context.payload(node).get("story_function") or [])
                       & {"payoff", "decision", "reversal"}]
        if climax and not payoff_like:
            scope = stable_scope(arc)
            evidence = QualityEvidence(
                evidence_id=f"{arc.node_id}:climax", kind="graph",
                explanation="StoryArc 声明了高潮，但场景层没有任何 payoff / decision / "
                            "reversal 作为前置积累",
                node_ids=(arc.node_id,), revision=arc.revision,
                comparison={"scene_count": len(scenes)})
            issues.append(make_issue(
                code="CLIMAX_UNPREPARED", novel_id=context.novel_id, scope=scope,
                reason="高潮缺少前置积累", evidence=[evidence],
                evaluator_id=EVALUATOR_ID))
        if not resolution:
            scope = stable_scope(arc)
            evidence = QualityEvidence(
                evidence_id=f"{arc.node_id}:resolution", kind="node_field",
                explanation="StoryArc.resolution 为空，收束没有覆盖主要冲突",
                node_ids=(arc.node_id,), revision=arc.revision)
            issues.append(make_issue(
                code="RESOLUTION_INCOMPLETE", novel_id=context.novel_id, scope=scope,
                reason="收束不完整", evidence=[evidence], evaluator_id=EVALUATOR_ID))

    # 4. SETUP_PAYOFF_DISTRIBUTION_SKEW
    setup_count = len(context.nodes_of_type("setup"))
    payoff_count = len(context.nodes_of_type("payoff"))
    if setup_count >= 2 and payoff_count * 2 < setup_count:
        # 图级问题：identity 只取决于全部场景集合（与请求 scope 无关）
        scope = QualityScope(novel_id=context.novel_id,
                             node_ids=tuple(sorted(node.node_id for node in scenes)),
                             node_types=("scene",), kind="nodes")
        evidence = QualityEvidence(
            evidence_id="setup-payoff:distribution", kind="metric",
            explanation=f"setup={setup_count}，payoff={payoff_count}：埋设远多于回收",
            metric={"setups": setup_count, "payoffs": payoff_count})
        issues.append(make_issue(
            code="SETUP_PAYOFF_DISTRIBUTION_SKEW", novel_id=context.novel_id,
            scope=scope, reason="setup / payoff 分布严重不均", evidence=[evidence],
            evaluator_id=EVALUATOR_ID))
    return issues


def _stagnation(context: EvaluationContext, run: Sequence[Any]) -> QualityIssue:
    node = run[0]
    scope = stable_scope(node)
    evidence = QualityEvidence(
        evidence_id=f"{node.node_id}:stagnation", kind="metric",
        explanation=f"连续 {len(run)} 场既没有升级功能，也没有 escalation 文本",
        node_ids=tuple(item.node_id for item in run), revision=node.revision,
        metric={"run_length": len(run)})
    return make_issue(
        code="PACING_STAGNATION", novel_id=context.novel_id, scope=scope,
        reason="连续多场没有升级或转折", evidence=[evidence],
        evaluator_id=EVALUATOR_ID)


def register(registry: EvaluatorRegistry) -> None:
    registry.register(EvaluatorSpec(
        evaluator_id=EVALUATOR_ID, version=1, gate="Q7", kind="deterministic",
        supported_node_types=("scene", "story_arc"),
        required_context=("blueprint_nodes",),
        description="场景功能 / 节奏停滞 / 高潮准备 / 收束完整性 / setup-payoff 分布"),
        evaluate)


__all__ = ["EVALUATOR_ID", "STAGNATION_RUN", "evaluate", "register"]
