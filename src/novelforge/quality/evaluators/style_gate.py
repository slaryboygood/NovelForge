"""Q8 Blueprint Style（V4-05 §20、§52）。

这里评的是 **Blueprint 表达质量**（是否具体 / 是否模板化 / 是否字段标签 /
是否占位符 / 标题是否过于相似），**不是小说 prose 文风**（§1）。
"""

from __future__ import annotations

import re
from typing import Any, Sequence

from ..contracts import QualityEvidence, QualityIssue, make_issue
from .._internal.similarity import similarity
from ..registry import EvaluatorRegistry, EvaluatorSpec
from .base import EvaluationContext, stable_scope, text_of

EVALUATOR_ID = "quality.style.v1"

#: 空洞表达（"如果删掉具体信息，这句话什么也没说"）
VAGUE_PATTERNS: tuple[str, ...] = (
    "发生新的危机", "新的危机", "关系进一步发展", "进一步发展", "主角面临挑战",
    "面临新的挑战", "有所变化", "发生了一些事", "一些事情", "推动剧情",
    "推进故事", "新的进展", "产生冲突", "出现转机", "故事向前推进",
)

#: 字段标签 / 内部枚举（V4-00 记录的 NF-003 同类问题）
FIELD_LABEL_PATTERNS: tuple[str, ...] = (
    "阶段目标", "长期方向", "阶段", "短期目标", "推进主线", "字段", "planned",
    "occurred", "ui_derived", "TODO_",
)

PLACEHOLDER_PATTERNS: tuple[str, ...] = (
    "未命名", "待定", "占位", "placeholder", "xxx", "TBD", "TODO",
)

#: 标题措辞相似阈值（"同一策略 + 后缀"这类模板化应当被抓到）
TITLE_SIMILARITY_THRESHOLD = 0.75

TEXT_FIELDS = ("title", "goal", "conflict", "turn", "outcome", "hook", "next_hook",
               "scene_purpose", "escalation", "resolution", "climax")


def _hits(text: str, patterns: Sequence[str]) -> list[str]:
    return [pattern for pattern in patterns if pattern.lower() in text.lower()]


def evaluate(context: EvaluationContext) -> Sequence[QualityIssue]:
    issues: list[QualityIssue] = []
    titles: list[tuple[str, str]] = []

    for node in context.scoped():
        if node.node_type in ("causal_link", "setup", "payoff"):
            continue
        payload = context.payload(node)
        text = text_of(payload, *TEXT_FIELDS)
        if not text:
            continue
        scope = stable_scope(node)

        vague = _hits(text, VAGUE_PATTERNS)
        if vague:
            evidence = QualityEvidence(
                evidence_id=f"{node.node_id}:vague", kind="node_field",
                explanation="出现无法执行的泛化表达：" + "、".join(vague),
                node_ids=(node.node_id,), revision=node.revision,
                excerpt=text[:200], comparison={"matches": vague})
            issues.append(make_issue(
                code="BLUEPRINT_VAGUE_CONTENT", novel_id=context.novel_id,
                scope=scope, reason="内容过于泛化，无法作为可执行蓝图",
                evidence=[evidence], evaluator_id=EVALUATOR_ID, suffix=str(len(vague))))

        labels = _hits(text, FIELD_LABEL_PATTERNS)
        if labels:
            evidence = QualityEvidence(
                evidence_id=f"{node.node_id}:field-label", kind="node_field",
                explanation="字段标签 / 内部枚举进入了作者可见文本：" + "、".join(labels),
                node_ids=(node.node_id,), revision=node.revision,
                excerpt=text[:200], comparison={"matches": labels})
            issues.append(make_issue(
                code="BLUEPRINT_FIELD_LABEL_TEXT", novel_id=context.novel_id,
                scope=scope, reason="字段标签进入正文", evidence=[evidence],
                evaluator_id=EVALUATOR_ID, suffix=str(len(labels))))

        placeholders = _hits(text, PLACEHOLDER_PATTERNS)
        if placeholders:
            evidence = QualityEvidence(
                evidence_id=f"{node.node_id}:placeholder", kind="node_field",
                explanation="出现占位符：" + "、".join(placeholders),
                node_ids=(node.node_id,), revision=node.revision,
                excerpt=text[:200], comparison={"matches": placeholders})
            issues.append(make_issue(
                code="BLUEPRINT_PLACEHOLDER_TEXT", novel_id=context.novel_id,
                scope=scope, reason="存在占位内容", evidence=[evidence],
                evaluator_id=EVALUATOR_ID, suffix=str(len(placeholders))))

        title = str(payload.get("title") or "").strip()
        if title:
            titles.append((node.node_id, title))

    # 标题措辞相似（与 Q6 的语义重复互补：这里看"措辞模板化"）
    for index, (node_id, title) in enumerate(titles):
        if not title:
            continue
        similar = [(other_id, other) for other_id, other in titles[index + 1:]
                   if similarity(title, other) >= TITLE_SIMILARITY_THRESHOLD]
        if not similar:
            continue
        node = context.nodes[node_id]
        scope = stable_scope(node)
        evidence = QualityEvidence(
            evidence_id=f"{node_id}:title-similar", kind="comparison",
            explanation="标题措辞与后续标题高度相似：" + "、".join(
                other for _other_id, other in similar[:3]),
            node_ids=(node_id, *(other_id for other_id, _ in similar[:3])),
            revision=node.revision,
            comparison={"titles": [title, *[other for _id, other in similar[:3]]]})
        issues.append(make_issue(
            code="BLUEPRINT_TITLE_TOO_SIMILAR", novel_id=context.novel_id, scope=scope,
            reason="标题大量相似", evidence=[evidence], evaluator_id=EVALUATOR_ID,
            suffix=node_id))
    return issues


def register(registry: EvaluatorRegistry) -> None:
    registry.register(EvaluatorSpec(
        evaluator_id=EVALUATOR_ID, version=1, gate="Q8", kind="deterministic",
        supported_node_types=("scene", "chapter", "character", "world", "story_arc",
                              "structural_unit", "premise"),
        required_context=("blueprint_nodes",),
        description="Blueprint 表达质量：泛化 / 字段标签 / 占位符 / 标题相似"),
        evaluate)


__all__ = ["EVALUATOR_ID", "FIELD_LABEL_PATTERNS", "PLACEHOLDER_PATTERNS",
           "VAGUE_PATTERNS", "evaluate", "register"]
