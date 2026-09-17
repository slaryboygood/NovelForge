"""S02：Evidence Validator —— Writer-visible 字段必须由 IR 事实支撑。

这不是文本相似度检查：每个字段要么绑定 event / effect / transition，要么直接失败。
"""

from __future__ import annotations

import re
from typing import Iterable

from pydantic import Field

from novelforge.models import StrictModel

from .models import DECISION_ACTIONS, ChapterSemanticIR

REQUIRED_EVIDENCE_FIELDS = ("decision", "cost", "turn", "payoff", "loss",
                            "information_release", "world_state_change", "dog_role")

NEGATIVE_POLARITY = ("negative", "mixed")
POSITIVE_POLARITY = ("positive", "mixed")
DECISION_ACTION_TYPES = ("choice", "decision", "commit", "refuse", "accept", "order", "trade")
TURN_TRANSITION_KINDS = ("progression", "activation", "acquisition", "regression", "loss",
                         "resolution", "irreversible", "deactivation")
MACHINE_ID_PATTERN = re.compile(r"\b(?:CE|EF|ST)_[A-Z0-9_]{2,}\b|ir://[^\s]+|\bstate_key\b")


class EvidenceFinding(StrictModel):
    code: str
    field_name: str = Field(default="", max_length=64)
    detail: str = Field(default="", max_length=300)
    severity: str = Field(default="error", max_length=16)


class EvidenceReport(StrictModel):
    chapter_uuid: str = ""
    findings: list[EvidenceFinding] = Field(default_factory=list)

    def ok(self) -> bool:
        return not [item for item in self.findings if item.severity == "error"]

    def codes(self) -> list[str]:
        return sorted({item.code for item in self.findings})


class EvidenceValidator:
    """规则：字段 → 需要的 IR 事实类型。"""

    def __init__(self, *, dog_id: str = "", protagonist_id: str = "") -> None:
        self.dog_id = dog_id
        self.protagonist_id = protagonist_id

    # ---- 入口 -------------------------------------------------------------
    def validate(self, ir: ChapterSemanticIR, *,
                 candidate_fields: dict[str, str] | None = None) -> EvidenceReport:
        report = EvidenceReport(chapter_uuid=ir.chapter_uuid)
        fields = dict(candidate_fields or {})
        for field_name in REQUIRED_EVIDENCE_FIELDS:
            evidence = ir.evidence_for(field_name)
            if evidence is None:
                if field_name == "dog_role":
                    # dog 规则即使在缺 evidence 时也要跑（absent / presence 语义独立）
                    self._check_dog_role(ir, report)
                else:
                    report.findings.append(EvidenceFinding(
                        code="FIELD_WITHOUT_EVIDENCE", field_name=field_name,
                        detail="Writer-visible 字段没有 FieldEvidence 绑定"))
                continue
            if field_name == "decision":
                self._check_decision(ir, evidence.event_ids, report)
            elif field_name in ("cost", "loss"):
                self._check_negative_effect(ir, field_name, evidence.effect_ids, report)
            elif field_name == "turn":
                self._check_turn(ir, evidence, report)
            elif field_name == "payoff":
                self._check_payoff(ir, evidence.effect_ids, report)
            elif field_name == "world_state_change":
                self._check_world_state(ir, evidence.transition_ids, report)
            elif field_name == "dog_role":
                self._check_dog_role(ir, report)
        # 字段文本不得是 event 原句的机械复制
        for field_name, text in fields.items():
            if not text:
                continue
            if MACHINE_ID_PATTERN.search(text):
                report.findings.append(EvidenceFinding(
                    code="WRITER_VISIBLE_METADATA_LEAK", field_name=field_name,
                    detail="writer-visible 文本出现 machine-only id"))
            for event in ir.event_frames:
                if event.action_text and text.strip().rstrip("。") == \
                        event.action_text.strip().rstrip("。"):
                    if field_name not in ("turn",):
                        report.findings.append(EvidenceFinding(
                            code="FIELD_EVENT_COPY_WITHOUT_ROLE", field_name=field_name,
                            detail=f"{field_name} 直接复制了 {event.event_id} 的原句"))
        return report

    # ---- 各字段规则 -------------------------------------------------------
    def _check_decision(self, ir: ChapterSemanticIR, event_ids: Iterable[str],
                        report: EvidenceReport) -> None:
        actors = {self.protagonist_id} - {""}
        found = False
        for event_id in event_ids:
            event = ir.event(event_id)
            if event is None:
                continue
            acts = set(event.actor_ids) & actors if actors else set(event.actor_ids)
            typed = event.decision_action in DECISION_ACTIONS
            is_decision = (typed and event.changes_followup_path) or \
                (event.action_type in DECISION_ACTION_TYPES and event.changes_followup_path)
            if acts and is_decision:
                found = True
                break
        if not found:
            report.findings.append(EvidenceFinding(
                code="DECISION_WITHOUT_DECISION_EVENT", field_name="decision",
                detail="decision 没有绑定主角真正做出的选择事件"))

    def _check_negative_effect(self, ir: ChapterSemanticIR, field_name: str,
                               effect_ids: Iterable[str], report: EvidenceReport) -> None:
        for effect_id in effect_ids:
            effect = ir.effect(effect_id)
            if effect is not None and effect.polarity in NEGATIVE_POLARITY:
                return
        report.findings.append(EvidenceFinding(
            code="COST_WITHOUT_NEGATIVE_EFFECT" if field_name == "cost"
            else "LOSS_WITHOUT_NEGATIVE_EFFECT", field_name=field_name,
            detail=f"{field_name} 没有绑定 negative / mixed effect"))

    def _check_turn(self, ir: ChapterSemanticIR, evidence, report: EvidenceReport) -> None:
        for transition_id in evidence.transition_ids:
            transition = next((item for item in ir.state_transitions
                               if item.transition_id == transition_id), None)
            if transition is not None and transition.assertion_mode == "transition" and \
                    transition.transition_kind in TURN_TRANSITION_KINDS:
                return
        # 叙事 turn 也可以来自 major effect（is_narrative_pivot）
        for effect_id in evidence.effect_ids:
            effect = ir.effect(effect_id)
            if effect is not None and effect.is_narrative_pivot:
                return
        report.findings.append(EvidenceFinding(
            code="TURN_WITHOUT_TRANSITION", field_name="turn",
            detail="turn 没有绑定 state transition 或 is_narrative_pivot effect"))

    def _check_payoff(self, ir: ChapterSemanticIR, effect_ids: Iterable[str],
                      report: EvidenceReport) -> None:
        for effect_id in effect_ids:
            effect = ir.effect(effect_id)
            if effect is not None and effect.polarity in POSITIVE_POLARITY:
                return
        report.findings.append(EvidenceFinding(
            code="PAYOFF_WITHOUT_EFFECT", field_name="payoff",
            detail="payoff 没有绑定 positive effect 或 goal resolution"))

    def _check_world_state(self, ir: ChapterSemanticIR, transition_ids: Iterable[str],
                           report: EvidenceReport) -> None:
        if any(ir.state_transitions and item in {t.transition_id for t in ir.state_transitions}
               for item in transition_ids if item):
            return
        report.findings.append(EvidenceFinding(
            code="WORLD_STATE_WITHOUT_TRANSITION", field_name="world_state_change",
            detail="world_state_change 没有绑定 ChapterStateTransition"))

    def _check_dog_role(self, ir: ChapterSemanticIR, report: EvidenceReport) -> None:
        dog = ir.dog
        evidence_events = [ir.event(item) for item in dog.evidence_event_ids]
        evidence_events = [item for item in evidence_events if item is not None]
        field_evidence = ir.evidence_for("dog_role")
        if dog.evidence_event_ids and field_evidence is not None and \
                not set(dog.evidence_event_ids) <= set(field_evidence.event_ids):
            report.findings.append(EvidenceFinding(
                code="DOG_BINDING_PLUMBING_ERROR", field_name="dog_role",
                detail="DogRoleBinding 有 CE id，但 FieldEvidence(dog_role) 未同步绑定"))
        if not evidence_events and dog.role not in ("absent", "offscreen_effect"):
            report.findings.append(EvidenceFinding(
                code="DOG_ROLE_WITHOUT_EVIDENCE", field_name="dog_role",
                detail=f"role={dog.role} 没有任何 evidence event"))
        if dog.role == "offscreen_effect" and not (dog.effect_ids or
                                                   dog.affects_decision_or_state):
            report.findings.append(EvidenceFinding(
                code="DOG_ROLE_WITHOUT_EVIDENCE", field_name="dog_role",
                detail="offscreen_effect 需要 absence effect 或明确的决策影响"))
        if dog.role == "absent":
            # absent 必须有 presence evidence：physical_presence=false 且无当前场景 dog effect
            if dog.physical_presence or dog.effect_ids:
                report.findings.append(EvidenceFinding(
                    code="DOG_ROLE_PRESENCE_MISMATCH", field_name="dog_role",
                    detail="absent 要求 physical_presence=false 且没有 dog effect"))
        if dog.role == "offscreen_effect" and dog.physical_presence:
            report.findings.append(EvidenceFinding(
                code="DOG_ROLE_PRESENCE_MISMATCH", field_name="dog_role",
                detail="offscreen_effect 要求 physical_presence=false"))
        if dog.role in ("supportive", "involved", "independent") and not dog.physical_presence:
            report.findings.append(EvidenceFinding(
                code="DOG_ROLE_PRESENCE_MISMATCH", field_name="dog_role",
                detail=f"{dog.role} 要求 physical_presence=true"))
        if dog.role == "supportive":
            acts = any(self.dog_id and self.dog_id in event.actor_ids
                       and event.action_type not in ("observe", "passive")
                       for event in evidence_events)
            if not acts:
                report.findings.append(EvidenceFinding(
                    code="DOG_SUPPORTIVE_WITHOUT_ACTION", field_name="dog_role",
                    detail="supportive 需要 actor=dog 的主动帮助动作"))
        if dog.role == "independent" and not dog.autonomous:
            report.findings.append(EvidenceFinding(
                code="DOG_INDEPENDENT_WITHOUT_AUTONOMY", field_name="dog_role",
                detail="independent 需要 agency=autonomous 的 dog 事件"))
        if dog.role == "offscreen_effect" and not dog.affects_decision_or_state:
            report.findings.append(EvidenceFinding(
                code="DOG_OFFSCREEN_WITHOUT_EFFECT", field_name="dog_role",
                detail="offscreen_effect 必须影响当前决策 / 状态"))
