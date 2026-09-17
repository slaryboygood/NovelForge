"""Q6 Semantic（V4-05 §18、§52）：三层检查的 deterministic + 结构化相似度层。

第三层（LLM-assisted 语义比较）由 critic 提供，默认关闭；**不使用
LocalHashEmbedding 做真实质量判定**（§18）。
"""

from __future__ import annotations

from typing import Any, Iterable, Sequence

from ..contracts import QualityEvidence, QualityIssue, make_issue
from .._internal.similarity import jaccard, normalize_text, similarity, token_set
from ..registry import EvaluatorRegistry, EvaluatorSpec
from .base import EvaluationContext, stable_scope, text_of

EVALUATOR_ID = "quality.semantic.v1"

SIMILARITY_THRESHOLD = 0.6
#: 标题更短 → 更容易因模板后缀而"看起来不同"，阈值取得更高
TITLE_SIMILARITY_THRESHOLD = 0.8
HOLLOW_MIN_CHARS = 12

SCENE_FIELDS = ("scene_purpose", "conflict", "escalation", "turn", "outcome")
CHAPTER_FIELDS = ("goal", "conflict", "turn", "hook", "title")


def _jaccard(left: str, right: str) -> float:
    """词级相似度（保留语义：结构字段措辞的 token 重叠）。"""

    return jaccard(token_set(left), token_set(right))


def _normalized(text: str) -> str:
    return normalize_text(text)


def _pairs(nodes: Sequence[Any], context: EvaluationContext,
           fields: Sequence[str]) -> Iterable[tuple[Any, Any, str, str]]:
    for prev, current in zip(nodes, nodes[1:]):
        prev_payload, current_payload = context.payload(prev), context.payload(current)
        for field in fields:
            left = _normalized(str(prev_payload.get(field) or ""))
            right = _normalized(str(current_payload.get(field) or ""))
            if left and right:
                yield prev, current, field, ""


def evaluate(context: EvaluationContext) -> Sequence[QualityIssue]:
    issues: list[QualityIssue] = []

    scenes = context.nodes_of_type("scene")
    # 1. 相邻场景的逐字段重复（normalized 精确 + 结构化相似度）
    for prev, current, _field, _ in _pairs(scenes, context, SCENE_FIELDS):
        prev_payload, current_payload = context.payload(prev), context.payload(current)
        matches: list[tuple[str, str, float]] = []
        for field in SCENE_FIELDS:
            left = str(prev_payload.get(field) or "").strip()
            right = str(current_payload.get(field) or "").strip()
            if not left or not right:
                continue
            if _normalized(left) == _normalized(right):
                matches.append((field, right, 1.0))
                continue
            field_score = _jaccard(left, right)
            if field_score >= SIMILARITY_THRESHOLD:
                matches.append((field, right, field_score))
        if len(matches) < 2:
            continue
        scope = stable_scope(current)
        evidence = QualityEvidence(
            evidence_id=f"{current.node_id}:repetition",
            kind="comparison",
            explanation=("与上一场在多个结构字段上重复："
                         + "，".join(f"{field}({score})" for field, _text, score in matches)),
            node_ids=(prev.node_id, current.node_id), revision=current.revision,
            comparison={"fields": [{"field": field, "similarity": score,
                                    "text": text[:120]}
                                   for field, text, score in matches]})
        issues.append(make_issue(
            code="SCENE_SEMANTIC_REPETITION", novel_id=context.novel_id, scope=scope,
            reason="连续场景承担相同叙事动作", evidence=[evidence],
            evaluator_id=EVALUATOR_ID, suffix=str(len(matches))))

    # 2. 章节目标重复
    chapters = context.nodes_of_type("chapter")
    for prev, current, _field, _ in _pairs(chapters, context, ("goal",)):
        prev_text = str(context.payload(prev).get("goal") or "")
        current_text = str(context.payload(current).get("goal") or "")
        score = _jaccard(prev_text, current_text)
        if _normalized(prev_text) != _normalized(current_text) and \
                score < SIMILARITY_THRESHOLD:
            continue
        scope = stable_scope(current)
        evidence = QualityEvidence(
            evidence_id=f"{current.node_id}:goal-repetition",
            kind="comparison",
            explanation=f"与 {prev.node_id} 的章节目标重复（相似度 {score}）",
            node_ids=(prev.node_id, current.node_id), revision=current.revision,
            comparison={"prev_goal": prev_text[:160], "current_goal": current_text[:160],
                        "similarity": score})
        issues.append(make_issue(
            code="CHAPTER_GOAL_REPETITION", novel_id=context.novel_id, scope=scope,
            reason="章节目标重复", evidence=[evidence], evaluator_id=EVALUATOR_ID))

    # 3. 标题语义重复（字符串唯一但结构 / 措辞相似，含「加后缀」模板化）
    for prev, current, _field, _ in _pairs(chapters + scenes, context, ("title",)):
        prev_text = str(context.payload(prev).get("title") or "")
        current_text = str(context.payload(current).get("title") or "")
        score = similarity(prev_text, current_text)
        if score < TITLE_SIMILARITY_THRESHOLD:
            continue
        scope = stable_scope(current)
        evidence = QualityEvidence(
            evidence_id=f"{current.node_id}:title-repetition",
            kind="comparison",
            explanation=f"标题与 {prev.node_id} 高度相似（{score}）",
            node_ids=(prev.node_id, current.node_id), revision=current.revision,
            comparison={"prev_title": prev_text, "current_title": current_text,
                        "similarity": score})
        issues.append(make_issue(
            code="TITLE_SEMANTIC_REPETITION", novel_id=context.novel_id, scope=scope,
            reason="标题语义重复", evidence=[evidence], evaluator_id=EVALUATOR_ID))

    # 4. 冲突模式重复（连续 3 场以上同冲突文本）
    conflicts = [str(context.payload(node).get("conflict") or "").strip()
                 for node in scenes]
    run_start = 0
    for index in range(1, len(conflicts) + 1):
        same = (index < len(conflicts) and conflicts[index]
                and _normalized(conflicts[index]) == _normalized(conflicts[run_start]))
        if same:
            continue
        if index - run_start >= 3:
            node = scenes[run_start]
            scope = stable_scope(node)
            evidence = QualityEvidence(
                evidence_id=f"{node.node_id}:conflict-pattern",
                kind="metric",
                explanation=f"连续 {index - run_start} 场使用同一种冲突模式",
                node_ids=tuple(row.node_id for row in scenes[run_start:index]),
                revision=node.revision, metric={"run_length": index - run_start})
            issues.append(make_issue(
                code="CONFLICT_PATTERN_REPETITION", novel_id=context.novel_id,
                scope=scope, reason="冲突模式重复", evidence=[evidence],
                evaluator_id=EVALUATOR_ID))
        run_start = index

    # 5. 空洞节点
    for node in context.scoped():
        text = text_of(context.payload(node), "goal", "conflict", "turn", "outcome",
                       "scene_purpose", "title")
        text_node_types = ("scene", "chapter", "character", "structural_unit")
        if node.node_type not in text_node_types:
            continue
        if len(text.strip()) >= HOLLOW_MIN_CHARS:
            continue
        scope = stable_scope(node)
        evidence = QualityEvidence(
            evidence_id=f"{node.node_id}:hollow", kind="metric",
            explanation=f"结构字段总长度仅 {len(text.strip())} 字，缺少具体信息",
            node_ids=(node.node_id,), revision=node.revision, excerpt=text,
            metric={"chars": len(text.strip())})
        issues.append(make_issue(
            code="HOLLOW_NODE", novel_id=context.novel_id, scope=scope,
            reason="节点内容空洞", evidence=[evidence], evaluator_id=EVALUATOR_ID))
    return issues


def register(registry: EvaluatorRegistry) -> None:
    registry.register(EvaluatorSpec(
        evaluator_id=EVALUATOR_ID, version=1, gate="Q6", kind="deterministic",
        supported_node_types=("scene", "chapter", "character", "structural_unit"),
        required_context=("blueprint_nodes",),
        description="normalized 精确 + 结构化相似度重复检测（不含 embedding）"),
        evaluate)


__all__ = ["EVALUATOR_ID", "SIMILARITY_THRESHOLD", "evaluate", "register"]
