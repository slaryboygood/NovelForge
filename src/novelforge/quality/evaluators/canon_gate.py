"""Q2 Canon（V4-05 §14）：deterministic 结构化比较 + 可选 critic。

deterministic 层覆盖"显式禁制/不会/已死亡"这类**结构化可判**的冲突；
隐含语义冲突交给 critic（经 `novelforge.ai`，capability=critic），且默认关闭。
"""

from __future__ import annotations

import re
from typing import Any, Iterable, Sequence

from novelforge.ai import LLMContract, PromptSpec, ValidationPolicy
from novelforge.core.ids import digest_payload
from pydantic import ConfigDict, Field

from novelforge.models import StrictModel

from ..contracts import QualityEvidence, QualityIssue, make_issue
from ..registry import EvaluatorRegistry, EvaluatorSpec
from .base import EvaluationContext, stable_scope, text_of

EVALUATOR_ID = "quality.canon.v1"
CRITIC_EVALUATOR_ID = "quality.canon.critic.v1"

#: 关键词字符类：中文/ASCII 词字符，**排除**标点与全角括号
#: （canon 投影会在事实文本后追加「（event，happened）」这类元数据，不能被当成关键词）
CHARS: str = (r"[^\s，。；：、（）()\[\]{}《》〈〉!！?？…·|/\\\"'“”‘’`~@#$%^&*+=<>\-]")

#: 显式禁制模式：canon 事实里出现这些表述 → 对应关键词不得在蓝图里被"执行"
PROHIBITION_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(rf"(?P<subject>{CHARS}{{1,12}})不会(?P<object>{CHARS}{{1,12}})"),
    re.compile(rf"(?P<subject>{CHARS}{{1,12}})不能(?P<object>{CHARS}{{1,12}})"),
    re.compile(rf"(?P<subject>{CHARS}{{1,12}})从不(?P<object>{CHARS}{{1,12}})"),
    re.compile(rf"禁止(?P<object>{CHARS}{{1,12}})"),
)

DEATH_MARKERS = ("已经死亡", "已死亡", "死亡状态", "已经死去")
USAGE_VERBS = ("使用", "拿出", "拔出", "开枪", "动用", "直接使用", "携带并使用")
TEXT_FIELDS = ("goal", "conflict", "turn", "outcome", "scene_purpose", "escalation",
               "hook", "next_hook", "information_reveal", "character_goals",
               "title", "resolution", "climax", "crisis")


class CriticIssueCandidate(StrictModel):
    """critic 只能提出候选（code 必须来自 registry）。"""

    model_config = ConfigDict(extra="forbid")

    code: str = Field(default="CANON_CONTRADICTION")
    node_id: str = Field(default="")
    reason: str = Field(default="", max_length=600)
    excerpt: str = Field(default="", max_length=300)


class CriticCanonReport(StrictModel):
    model_config = ConfigDict(extra="forbid")

    candidates: list[CriticIssueCandidate] = Field(default_factory=list)


def _prohibition_keywords(canon_text: str) -> list[str]:
    keywords: list[str] = []
    for pattern in PROHIBITION_PATTERNS:
        for match in pattern.finditer(canon_text):
            value = (match.groupdict().get("object") or "").strip(
                " 　的，。；：、（）()[]{}《》")
            if value and len(value) >= 2:
                keywords.append(value)
    return keywords


def _node_text(payload: dict[str, Any]) -> str:
    return text_of(payload, *TEXT_FIELDS)


def _deterministic(context: EvaluationContext) -> Sequence[QualityIssue]:
    issues: list[QualityIssue] = []
    targets = [node for node in context.scoped()
               if node.node_type in ("scene", "chapter", "character", "world",
                                     "character_arc", "story_arc")]
    if not targets:
        return issues

    entities = sorted({str(value) for node in targets
                       for value in (context.payload(node).get("characters") or [])} |
                      {str(value) for node in targets
                       for value in (context.payload(node).get("character_goals") or [])})
    facts = context.canon_items(entities=entities, task=" ".join(
        _node_text(context.payload(node)) for node in targets)[:200], top_k=12)

    for fact in facts:
        canon_text = str(getattr(fact, "text", "") or "")
        for keyword in _prohibition_keywords(canon_text):
            for node in targets:
                payload = context.payload(node)
                node_text = _node_text(payload)
                if keyword not in node_text:
                    continue
                if not any(verb in node_text for verb in USAGE_VERBS):
                    continue
                scope = stable_scope(node)
                evidence = QualityEvidence(
                    evidence_id=f"{node.node_id}:canon:{keyword}",
                    kind="comparison",
                    explanation=(f"Canon 事实声明禁止/不会「{keyword}」，"
                                 f"但 {node.node_id} 描述了对其的使用"),
                    source_ids=tuple(getattr(fact, "source_ids", ()) or ()),
                    node_ids=(node.node_id,), revision=node.revision,
                    excerpt=node_text[:200],
                    comparison={"canon_text": canon_text, "keyword": keyword,
                                "node_text": node_text[:200]})
                issues.append(make_issue(
                    code="CANON_CONTRADICTION", novel_id=context.novel_id,
                    scope=scope,
                    reason=f"与 Canon 事实冲突：{canon_text[:80]}",
                    evidence=[evidence], evaluator_id=EVALUATOR_ID,
                    provenance={"canon_source_ids": list(
                        getattr(fact, "source_ids", ()) or ())},
                    suffix=keyword))

    for fact in facts:
        canon_text = str(getattr(fact, "text", "") or "")
        if not any(marker in canon_text for marker in DEATH_MARKERS):
            continue
        subject = canon_text.split("已经")[0].split("已")[0].strip(" 　，。；")[:12]
        if not subject:
            continue
        for node in targets:
            payload = context.payload(node)
            node_text = _node_text(payload)
            participants = [str(value) for value in
                            (payload.get("characters") or []) +
                            (payload.get("character_goals") or [])]
            if subject not in node_text and subject not in participants:
                continue
            if any(verb in node_text for verb in ("行动", "出场", "决定", "选择", "回应")):
                scope = stable_scope(node)
                evidence = QualityEvidence(
                    evidence_id=f"{node.node_id}:canon:death",
                    kind="comparison",
                    explanation=f"Canon 记录「{subject}」已死亡，但该节点仍让其行动",
                    source_ids=tuple(getattr(fact, "source_ids", ()) or ()),
                    node_ids=(node.node_id,), revision=node.revision,
                    excerpt=node_text[:200],
                    comparison={"canon_text": canon_text, "subject": subject})
                issues.append(make_issue(
                    code="CANON_CHARACTER_IDENTITY_CONFLICT",
                    novel_id=context.novel_id, scope=scope,
                    reason=f"与人物状态冲突：{canon_text[:80]}", evidence=[evidence],
                    evaluator_id=EVALUATOR_ID, suffix="death"))
    return issues


def evaluate(context: EvaluationContext) -> Sequence[QualityIssue]:
    return _deterministic(context)


def _critic_contract() -> LLMContract:
    return LLMContract(
        contract_id="quality.canon.critic.v1", version=1,
        prompt=PromptSpec(
            system=("你是故事一致性审阅者。只判断给定蓝图节点是否与给定 Canon 事实冲突；"
                    "只允许使用 code=CANON_CONTRADICTION 或 "
                    "CANON_CHARACTER_IDENTITY_CONFLICT；必须给出 node_id / reason / excerpt。"
                    "没有把握时返回空 candidates。只输出 JSON。"),
            user_template="Canon 事实：\n{canon}\n\n蓝图节点：\n{nodes}\n"),
        output_model=CriticCanonReport, generation_mode="structured_json",
        temperature_policy="deterministic", max_output_tokens=800, timeout_s=60.0,
        max_attempts=2, cacheable=False, required_capabilities=("critic",),
        validation=ValidationPolicy(require_json=True, strict=False))


def evaluate_with_critic(context: EvaluationContext) -> Sequence[QualityIssue]:
    """LLM-assisted 层：critic 只提候选；scope / preserve 由 planner 决定（§54）。"""

    critic = context.critic
    if critic is None:
        return []
    from novelforge.ai import ModelPolicy

    targets = [node for node in context.scoped()
               if node.node_type in ("scene", "chapter", "character", "story_arc")]
    if not targets:
        return []
    canon_lines: list[str] = []
    for fact in context.canon_items(entities=(), task="一致性", top_k=12):
        canon_lines.append(f"- {getattr(fact, 'text', '')}")
    node_lines = [f"- {node.node_id}（{node.node_type}）："
                  f"{_node_text(context.payload(node))[:300]}" for node in targets]
    critic_context = {"canon": "\n".join(canon_lines) or "（无 Canon 事实）",
                      "nodes": "\n".join(node_lines)}
    context_digest = digest_payload(critic_context)
    result = critic.generate(
        contract=_critic_contract(),
        context=critic_context,
        model_policy=ModelPolicy(profile="quality_first",
                                 required_capabilities=("critic",)),
        operation="quality.canon.critic")
    context.record_usage(getattr(result, "usage", None),
                         operation="quality.canon.critic")
    report = result.output
    issues: list[QualityIssue] = []
    by_id = {node.node_id: node for node in targets}
    for candidate in getattr(report, "candidates", []) or []:
        node = by_id.get(str(candidate.node_id))
        if node is None:
            continue
        scope = stable_scope(node)
        evidence = QualityEvidence(
            evidence_id=f"{node.node_id}:critic:{candidate.code}",
            kind="comparison", explanation=str(candidate.reason)[:400],
            node_ids=(node.node_id,), revision=node.revision,
            excerpt=str(candidate.excerpt)[:300],
            comparison={"model": str(result.model), "request_id": str(result.request_id)})
        issues.append(make_issue(
            code=str(candidate.code), novel_id=context.novel_id, scope=scope,
            reason=str(candidate.reason)[:400], evidence=[evidence],
            evaluator_id=CRITIC_EVALUATOR_ID,
            provenance={"model": str(result.model),
                        "contract_id": "quality.canon.critic.v1",
                        "contract_version": 1,
                        "context_digest": context_digest,
                        "request_id": str(result.request_id)},
            suffix="critic"))
    return issues


def register(registry: EvaluatorRegistry) -> None:
    registry.register(EvaluatorSpec(
        evaluator_id=EVALUATOR_ID, version=1, gate="Q2", kind="deterministic",
        supported_node_types=("scene", "chapter", "character", "world", "character_arc",
                              "story_arc"),
        required_context=("canon_memory",),
        description="显式禁制 / 死亡状态与蓝图的确定性冲突"),
        evaluate)
    registry.register(EvaluatorSpec(
        evaluator_id=CRITIC_EVALUATOR_ID, version=1, gate="Q2", kind="llm_assisted",
        supported_node_types=("scene", "chapter", "character", "story_arc"),
        required_context=("canon_memory", "critic"),
        description="critic 判定隐含语义冲突（candidate only）"),
        evaluate_with_critic)


__all__ = ["CRITIC_EVALUATOR_ID", "EVALUATOR_ID", "CriticCanonReport", "evaluate",
           "evaluate_with_critic", "register"]
