"""Q4 Character（V4-05 §16）：动机 / 人物弧推进 / 转折支撑（结构化字段 + evidence）。"""

from __future__ import annotations

from typing import Any, Sequence

from ..contracts import QualityEvidence, QualityIssue, make_issue
from ..registry import EvaluatorRegistry, EvaluatorSpec
from .base import EvaluationContext, stable_scope, text_of

EVALUATOR_ID = "quality.character.v1"

DECISION_FUNCTIONS = ("decision", "reversal")
DECISION_MARKERS = ("决定", "选择", "转而", "倒戈", "放弃", "承认", "摊牌")


def evaluate(context: EvaluationContext) -> Sequence[QualityIssue]:
    issues: list[QualityIssue] = []

    # 1. 场景里的关键决定必须有动机（character_goals 或 escalation 提供压力）
    for node in context.nodes_of_type("scene"):
        payload = context.payload(node)
        functions = set(payload.get("story_function") or [])
        text = text_of(payload, "turn", "outcome", "escalation", "conflict")
        is_decision = bool(functions & set(DECISION_FUNCTIONS)) or any(
            marker in text for marker in DECISION_MARKERS)
        if not is_decision:
            continue
        if (payload.get("character_goals") or []) or payload.get("escalation"):
            continue
        scope = stable_scope(node)
        evidence = QualityEvidence(
            evidence_id=f"{node.node_id}:motivation",
            kind="node_field",
            explanation=("本场包含关键决定，但既没有 character_goals，"
                         "也没有 escalation 提供压力"),
            node_ids=(node.node_id,), revision=node.revision, excerpt=text[:200],
            comparison={"story_function": sorted(functions)})
        issues.append(make_issue(
            code="CHARACTER_MOTIVATION_GAP", novel_id=context.novel_id, scope=scope,
            reason="角色行为缺少动机或前置压力", evidence=[evidence],
            evaluator_id=EVALUATOR_ID))

    # 2. 人物弧推进 / 转折支撑（需要场景证据）
    scenes = context.nodes_of_type("scene")
    scene_payloads = [(node, context.payload(node)) for node in scenes]
    for arc in context.nodes_of_type("character_arc"):
        payload = context.payload(arc)
        character_id = str(payload.get("character_id") or "")
        turns = [str(value) for value in (payload.get("key_turns") or []) if str(value)]
        changes = [payload_index for node, payload_index in scene_payloads
                   if character_id and (character_id in str(payload_index.get("character_goals") or [])
                                        or character_id in str(payload_index.get("pov") or "")
                                        or character_id in str(payload_index.get("character_change") or ""))]
        if character_id and not changes:
            scope = stable_scope(arc)
            evidence = QualityEvidence(
                evidence_id=f"{arc.node_id}:arc",
                kind="graph",
                explanation=f"{arc.node_id} 关联角色 {character_id}，"
                            f"但当前场景集合里没有任何推进证据",
                node_ids=(arc.node_id,), revision=arc.revision,
                comparison={"character_id": character_id,
                            "scene_count": len(scenes)})
            issues.append(make_issue(
                code="CHARACTER_ARC_STALL", novel_id=context.novel_id, scope=scope,
                reason="人物弧长时间没有推进", evidence=[evidence],
                evaluator_id=EVALUATOR_ID))
        if turns:
            supported = any(
                any(token and token in text_of(payload_index, "outcome", "turn",
                                               "character_change", "scene_purpose")
                    for token in turns)
                for _node, payload_index in scene_payloads)
            if scene_payloads and not supported:
                scope = stable_scope(arc)
                evidence = QualityEvidence(
                    evidence_id=f"{arc.node_id}:turns",
                    kind="comparison",
                    explanation="人物弧的关键转折在场景 outcome / turn 里找不到支撑",
                    node_ids=(arc.node_id,), revision=arc.revision,
                    comparison={"key_turns": turns[:4]})
                issues.append(make_issue(
                    code="CHARACTER_ARC_UNSUPPORTED_TURN", novel_id=context.novel_id,
                    scope=scope, reason="关键转折没有场景支撑", evidence=[evidence],
                    evaluator_id=EVALUATOR_ID))
    return issues


def register(registry: EvaluatorRegistry) -> None:
    registry.register(EvaluatorSpec(
        evaluator_id=EVALUATOR_ID, version=1, gate="Q4", kind="deterministic",
        supported_node_types=("scene", "character_arc"),
        required_context=("blueprint_nodes",),
        description="动机缺口 / 人物弧停滞 / 转折无场景支撑"),
        evaluate)


__all__ = ["EVALUATOR_ID", "evaluate", "register"]

