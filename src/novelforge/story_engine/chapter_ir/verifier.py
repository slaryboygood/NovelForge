"""S09：Semantic Verification —— 抓 schema/validator 都过但语义错的 IR。

两层：

- DeterministicSemanticVerifier：规则验证（actor / decision owner / dog evidence /
  payoff 与 trigger·hook 重合 / turn 是否只是普通损失 / authoritative state binding 冲突）
- FixtureSemanticVerifier（LLM verifier 的落地点）：只读取结构化 verification 结果，
  不修改 IR；无 LLM 时保持 NullVerifier。

verdict 只用于 reconciliation 分类，不直接改内容、不创建 Canon。
"""

from __future__ import annotations

import re
from typing import Literal, Mapping, Protocol, Sequence

from pydantic import Field

from novelforge.models import StrictModel

from .models import ChapterSemanticIR
from .state import TypedStateRegistry

Verdict = Literal["AGREE", "DISAGREE", "AMBIGUOUS"]
Category = Literal["SEMANTIC_CONFIRMED", "EXTRACTION_REPAIR", "LEGACY_CONTENT_GAP",
                   "LEGACY_FIELD_CONFLICT", "HUMAN_CANON_DECISION"]

PAYOFF_IS_TRIGGER = "PAYOFF_IS_TRIGGER"
PAYOFF_IS_HOOK = "PAYOFF_IS_HOOK"
PAYOFF_NO_GOAL_RESOLUTION = "PAYOFF_NO_GOAL_RESOLUTION"
DECISION_WRONG_ACTOR = "DECISION_WRONG_ACTOR"
DOG_WRONG_ACTOR = "DOG_WRONG_ACTOR"
DOG_MENTION_AS_ACTION = "DOG_MENTION_AS_ACTION"
TURN_FROM_ORDINARY_LOSS = "TURN_FROM_ORDINARY_LOSS"
DOG_PASSIVE_AS_SUPPORTIVE = "DOG_PASSIVE_AS_SUPPORTIVE"
AUTHORITATIVE_BINDING_CONFLICT = "AUTHORITATIVE_BINDING_CONFLICT"
TURN_NOT_APPLICABLE = "TURN_NOT_APPLICABLE"
LEGACY_PAYOFF_FIELD_CONFLICT = "LEGACY_PAYOFF_FIELD_CONFLICT"
LEGACY_DECISION_FIELD_CONFLICT = "LEGACY_DECISION_FIELD_CONFLICT"
FUTURE_CANON_LEAK = "FUTURE_CANON_LEAK"
HISTORICAL_REFERENCE = "HISTORICAL_REFERENCE"
CURRENT_FACT = "CURRENT_FACT"


def classify_reference(text: str, *, current_position: int | None = None,
                       binding_position: int | None = None) -> str:
    """把重要引用分成 current_fact / historical_fact / future_plan / future_canon_leak /
    belief / rumor / unknown。"""

    value = text or ""
    completed = re.search(r"(?:已经|已完成|正式|生效|落定|确立)", value) and re.search(
        r"(?:表决|投票|签署|署名|封死|封层|永久封闭|按趟结算|第三份档案公开|"
        r"自己回来|整体东移|第二份档案)", value)
    if re.search(r"(?:将在|将要|以后|之后会|准备|即将|下一步|未来)", value):
        return "future_plan"
    if completed and binding_position is not None and current_position is not None \
            and current_position < binding_position:
        return FUTURE_CANON_LEAK
    if completed:
        return "historical_fact"
    if re.search(r"(?:此前|已经|早已|当年|后来|留下的|记录里)", value):
        return "historical_fact"
    if re.search(r"(?:据说|听说|传闻|人说)", value):
        return "rumor"
    if re.search(r"(?:怀疑|可能|也许|似乎|认为)", value):
        return "belief"
    if current_position is not None:
        return CURRENT_FACT
    return "unknown"


REFERENCE_BINDING_KEYWORDS: tuple[tuple[str, str, int], ...] = (
    ("表决", "common_rules_status", 526), ("投票", "common_rules_status", 526),
    ("签署", "common_rules_status", 559), ("署名", "common_rules_status", 559),
    ("正式生效", "common_rules_status", 559),
    ("封死", "zero_layer_access", 379), ("封层", "zero_layer_access", 379),
    ("永久封闭", "zero_layer_access", 379),
    ("按趟结算", "salt_route_control", 133),
    ("第三份档案公开", "archive_publication_level", 504),
    ("第二份档案", "archive_publication_level", 502),
    ("自己回来", "dog_departure_status", 438),
    ("整体东移", "gray_wall_observation_status", 271),
)


def reference_leak_check(text: str, chapter_position: int | None) -> str:
    """只在该章早于该状态的 canonical 章、且文本声称已完成时判 future_canon_leak。"""

    value = text or ""
    if not value or chapter_position is None:
        return "unknown"
    if not re.search(r"(?:已经|已完成|正式|生效|落定|确立)", value):
        return "unknown"
    for keyword, _state_key, binding_position in REFERENCE_BINDING_KEYWORDS:
        if keyword in value and chapter_position < binding_position:
            return FUTURE_CANON_LEAK
    return "unknown"


def _tokens(text: str) -> set[str]:
    clean = re.sub(r"[^\w\u4e00-\u9fff]+", " ", (text or "").lower())
    words = {word for word in clean.split() if len(word) > 1}
    grams = {clean[index:index + 2].strip() for index in range(max(0, len(clean) - 1))}
    return {token for token in words | grams if token}


def _overlap(left: str, right: str) -> float:
    a, b = _tokens(left), _tokens(right)
    return round(len(a & b) / len(a | b), 4) if a and b else 0.0


class DecisionCheck(StrictModel):
    exists: bool = False
    actor_id: str = ""
    evidence_event: str = ""
    valid: bool = False
    issue: str = ""


class TurnCheck(StrictModel):
    turn_type: str = ""
    evidence: str = ""
    valid: bool = False


class PayoffCheck(StrictModel):
    evidence: str = ""
    valid: bool = False
    issues: list[str] = Field(default_factory=list)


class DogCheck(StrictModel):
    physical_presence: bool = False
    role: str = "absent"
    evidence_actor_id: str = ""
    evidence_valid: bool = False
    issues: list[str] = Field(default_factory=list)


class TransitionCheck(StrictModel):
    state_key: str = ""
    from_state: str = ""
    to_state: str = ""
    assertion_mode: str = ""
    valid: bool = False
    issue: str = ""


class SemanticVerificationResult(StrictModel):
    chapter_uuid: str = Field(min_length=3, max_length=128)
    event_actor_checks: dict[str, str] = Field(default_factory=dict)
    decision: DecisionCheck = Field(default_factory=DecisionCheck)
    turn: TurnCheck = Field(default_factory=TurnCheck)
    payoff: PayoffCheck = Field(default_factory=PayoffCheck)
    dog: DogCheck = Field(default_factory=DogCheck)
    primary_transition: TransitionCheck = Field(default_factory=TransitionCheck)
    legacy_field_conflicts: list[str] = Field(default_factory=list)
    verdict: Verdict = "AMBIGUOUS"
    confidence: float = Field(default=0.6, ge=0, le=1)
    verifier: str = Field(default="deterministic", max_length=32)
    issues: list[str] = Field(default_factory=list)
    chapter_function: str = Field(default="", max_length=32)
    function_requirements: dict[str, str] = Field(default_factory=dict)
    reference_classification: dict[str, str] = Field(default_factory=dict)
    reference_evidence_valid: bool = True


class SemanticVerifier(Protocol):  # pragma: no cover - 接口
    def verify(self, ir: ChapterSemanticIR, chapter: Mapping[str, object] | None = None,
               registry: TypedStateRegistry | None = None) -> SemanticVerificationResult: ...


class DeterministicSemanticVerifier:
    """规则验证：覆盖人工报告的 silent semantic errors。"""

    name = "deterministic"

    def __init__(self, *, protagonist_id: str = "ENTITY_PROTAGONIST",
                 dog_id: str = "ENTITY_DOG_AHUI") -> None:
        self.protagonist_id = protagonist_id
        self.dog_id = dog_id

    def verify(self, ir: ChapterSemanticIR, chapter: Mapping[str, object] | None = None,
               registry: TypedStateRegistry | None = None,
               function_finding: object | None = None) -> SemanticVerificationResult:
        chapter = dict(chapter or {})
        if function_finding is None:
            from .function_policy import ChapterFunctionPolicy
            function_finding = ChapterFunctionPolicy().classify(ir, chapter)
        requirements = {"decision": function_finding.decision, "turn": function_finding.turn,
                        "payoff": function_finding.payoff,
                        "world_state_change": function_finding.world_state_change,
                        "information_release": function_finding.information_release,
                        "cost": function_finding.cost, "loss": function_finding.loss}
        issues: list[str] = []
        # 1) event actor 检查
        actor_checks: dict[str, str] = {}
        for event in ir.event_frames:
            if not event.actor_ids:
                actor_checks[event.event_id] = "NO_ACTOR"
            elif self.dog_id in event.mentioned_entity_ids \
                    and self.dog_id not in event.actor_ids:
                # mention ≠ actor 是正常写法；只有 dog role 绑到这种事件才算错（见 DOG_WRONG_ACTOR）
                actor_checks[event.event_id] = "DOG_MENTION_ONLY"
        # 2) decision owner
        evidence = ir.evidence_for("decision")
        decision = DecisionCheck(exists=bool(evidence and evidence.event_ids))
        if evidence and evidence.event_ids:
            event = ir.event(evidence.event_ids[0])
            decision.evidence_event = evidence.event_ids[0]
            if event is not None:
                decision.actor_id = event.actor_ids[0] if event.actor_ids else ""
                focal = ir.focal_decision_owner_id or self.protagonist_id
                if event.decision_action and focal not in event.actor_ids:
                    decision.issue = DECISION_WRONG_ACTOR
                    issues.append(DECISION_WRONG_ACTOR)
                elif not event.decision_action:
                    decision.issue = "DECISION_WITHOUT_ACTION"
                else:
                    decision.valid = True
        # 3) turn
        turn_evidence = ir.evidence_for("turn")
        turn = TurnCheck()
        if turn_evidence:
            primary = next((item for item in ir.state_transitions
                            if item.narrative_role == "primary"
                            and item.assertion_mode == "transition"), None)
            pivot = next((item for item in ir.effects if item.is_narrative_pivot), None)
            if primary is not None:
                turn = TurnCheck(turn_type="state_transition", evidence=primary.transition_id,
                                 valid=True)
            elif pivot is not None and pivot.effect_type not in ("cost", "loss"):
                turn = TurnCheck(turn_type="strategic_reversal", evidence=pivot.effect_id,
                                 valid=True)
            else:
                if requirements["turn"] == "not_applicable":
                    turn = TurnCheck(turn_type="not_applicable", evidence="", valid=True)
                else:
                    turn = TurnCheck(turn_type="missing", evidence="", valid=False)
                    issues.append("MISSING_REQUIRED_TURN")
        # 4) payoff（不得等于 trigger / hook / 无 goal resolution）
        payoff_text = str(chapter.get("payoff") or "")
        trigger_text = str(chapter.get("trigger") or "")
        hook_text = str(chapter.get("hook") or "")
        goal_text = str(chapter.get("goal") or "")
        payoff = PayoffCheck()
        if payoff_text:
            if trigger_text and _overlap(payoff_text, trigger_text) >= 0.5:
                payoff.issues.append(LEGACY_PAYOFF_FIELD_CONFLICT)
            if hook_text and _overlap(payoff_text, hook_text) >= 0.5:
                payoff.issues.append(LEGACY_PAYOFF_FIELD_CONFLICT)
            positive = [effect for effect in ir.effects
                        if effect.polarity in ("positive", "mixed")]
            if positive:
                payoff.evidence = positive[0].effect_id
                payoff.valid = not payoff.issues
            elif requirements["payoff"] == "required":
                payoff.issues.append(PAYOFF_NO_GOAL_RESOLUTION)
            else:
                payoff.valid = True
            issues.extend(sorted(set(payoff.issues)))
        # 5) dog
        dog = DogCheck(physical_presence=ir.dog.physical_presence, role=ir.dog.role)
        if ir.dog.role in ("supportive", "involved", "independent"):
            evidence_event = next((ir.event(item) for item in ir.dog.evidence_event_ids
                                   if ir.event(item)), None)
            if evidence_event is None or self.dog_id not in evidence_event.actor_ids:
                dog.issues.append(DOG_WRONG_ACTOR)
                issues.append(DOG_WRONG_ACTOR)
            else:
                dog.evidence_actor_id = self.dog_id
                dog.evidence_valid = True
                active_verb = re.search(r"(?:扑|护|拖|拉|咬|顶|守|叼|刨|嗅|找|挖|挡|拦|送)",
                                        evidence_event.action_text)
                if ir.dog.role == "supportive" and not active_verb and re.search(
                        r"(?:被困|被救|受伤|被讨论|被拿来|被交易|被识别)",
                        evidence_event.action_text):
                    dog.issues.append(DOG_PASSIVE_AS_SUPPORTIVE)
                    issues.append(DOG_PASSIVE_AS_SUPPORTIVE)
        elif ir.dog.role == "offscreen_effect":
            if ir.dog.physical_presence:
                dog.issues.append(DOG_WRONG_ACTOR)
            else:
                dog.evidence_valid = bool(ir.dog.effect_ids or
                                          ir.dog.affects_decision_or_state)
        else:
            dog.evidence_valid = not ir.dog.physical_presence
        # 6) primary transition vs authoritative binding
        primary = next((item for item in ir.state_transitions
                        if item.narrative_role == "primary"), None)
        transition_check = TransitionCheck()
        if primary is not None:
            transition_check = TransitionCheck(
                state_key=primary.state_key, from_state=primary.from_state,
                to_state=primary.to_state, assertion_mode=primary.assertion_mode)
            if registry is not None:
                binding = registry.binding_for(primary.state_key, primary.to_state)
                if binding is not None and primary.assertion_mode == "transition" and \
                        ir.temporal_position is not None and \
                        ir.temporal_position != binding.display_number:
                    transition_check.issue = AUTHORITATIVE_BINDING_CONFLICT
                    issues.append(AUTHORITATIVE_BINDING_CONFLICT)
                else:
                    transition_check.valid = True
            else:
                transition_check.valid = True
        # 7) legacy field conflicts
        conflicts: list[str] = []
        for field_name in ("cost", "loss", "information_release", "world_state_change"):
            legacy = str(chapter.get(field_name) or "").strip()
            evidence = ir.evidence_for(field_name)
            has_evidence = bool(evidence and (evidence.effect_ids or evidence.transition_ids
                                              or evidence.event_ids))
            if legacy and not has_evidence:
                conflicts.append(field_name)
        verdict: Verdict = "AGREE" if not issues else "DISAGREE"
        if not ir.event_frames:
            verdict = "AMBIGUOUS"
        reference_classification: dict[str, str] = {}
        for field_name in ("world_state_change", "information_release", "end_state"):
            text = str(chapter.get(field_name) or "")
            if not text:
                continue
            binding_position = None
            if registry is not None and ir.temporal_position is not None:
                candidates = [binding.display_number for binding in registry.bindings.values()
                              if binding.display_number > ir.temporal_position]
                binding_position = min(candidates) if candidates else None
            leak = reference_leak_check(text, ir.temporal_position)
            reference_classification[field_name] = (
                leak if leak == FUTURE_CANON_LEAK
                else classify_reference(text, current_position=ir.temporal_position,
                                        binding_position=binding_position))
            if leak == FUTURE_CANON_LEAK:
                issues.append(FUTURE_CANON_LEAK)
        return SemanticVerificationResult(
            chapter_uuid=ir.chapter_uuid, event_actor_checks=actor_checks, decision=decision,
            turn=turn, payoff=payoff, dog=dog, primary_transition=transition_check,
            legacy_field_conflicts=conflicts, verdict=verdict, confidence=0.7,
            verifier=self.name, issues=sorted(set(issues)),
            chapter_function=function_finding.chapter_function,
            function_requirements=requirements,
            reference_classification=reference_classification)


class NullVerifier:
    name = "null"
    enabled = False

    def verify(self, ir: ChapterSemanticIR, chapter: Mapping[str, object] | None = None,
               registry: TypedStateRegistry | None = None) -> SemanticVerificationResult:
        return SemanticVerificationResult(chapter_uuid=ir.chapter_uuid, verdict="AMBIGUOUS",
                                          confidence=0.0, verifier=self.name)


def reconcile_verdicts(deterministic: SemanticVerificationResult,
                       llm: SemanticVerificationResult | None) -> tuple[Verdict, list[str]]:
    """§7：AGREE → 语义确认；DISAGREE → 需要 full LLM IR；AMBIGUOUS → 人工队列。"""

    notes: list[str] = []
    if llm is None:
        return deterministic.verdict, ["NO_LLM_VERIFIER"]
    if deterministic.verdict == "DISAGREE" and llm.verdict == "AGREE":
        notes.append("LLM_VERIFIER_AGREES_WITH_DETERMINISTIC_DISAGREE")
        return "DISAGREE", notes
    if deterministic.verdict == "AMBIGUOUS" or llm.verdict == "AMBIGUOUS":
        return "AMBIGUOUS", notes
    return "AGREE", notes


def categorize(*, verified: Verdict, deterministic_ok: bool, conflicts: Sequence[str],
               wrong_actor: bool, ambiguous: bool) -> Category:
    if ambiguous:
        return "HUMAN_CANON_DECISION"
    if wrong_actor:
        return "EXTRACTION_REPAIR"
    if conflicts:
        return "LEGACY_FIELD_CONFLICT"
    if verified == "AGREE" and deterministic_ok:
        return "SEMANTIC_CONFIRMED"
    return "EXTRACTION_REPAIR" if verified == "DISAGREE" else "LEGACY_CONTENT_GAP"
