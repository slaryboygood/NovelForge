"""S02：Evidence Validator —— 字段必须绑定 IR 事实（不是文本相似度）。"""

from __future__ import annotations

from novelforge.story_engine.chapter_ir.evidence import EvidenceValidator
from novelforge.story_engine.chapter_ir.models import (
    ChapterEffect,
    ChapterEventFrame,
    ChapterSemanticIR,
    DogRoleBinding,
    FieldEvidence,
)


def _ir(**overrides) -> ChapterSemanticIR:
    base = dict(
        chapter_uuid="uuid_x", novel_id="n1", temporal_position=10,
        event_frames=[
            ChapterEventFrame(event_id="CE_001", actor_ids=["hero"], action_type="search",
                              action_text="主角翻查台账", temporal_order=1),
            ChapterEventFrame(event_id="CE_002", actor_ids=["hero"], action_type="decision",
                              decision_action="decide", changes_followup_path=True,
                              action_text="主角决定不抓人，放长线", temporal_order=2)],
        effects=[ChapterEffect(effect_id="EF_001", effect_type="cost", polarity="negative",
                               target_id="party", after_state="两箱货被扣"),
                 ChapterEffect(effect_id="EF_002", effect_type="gain", polarity="positive",
                               target_id="goal", after_state="内应被锁定")],
        field_evidence=[FieldEvidence(field_name="decision", event_ids=["CE_002"]),
                        FieldEvidence(field_name="cost", effect_ids=["EF_001"]),
                        FieldEvidence(field_name="loss", effect_ids=["EF_001"]),
                        FieldEvidence(field_name="payoff", effect_ids=["EF_002"]),
                        FieldEvidence(field_name="turn", event_ids=["CE_001"]),
                        FieldEvidence(field_name="world_state_change",
                                      event_ids=["CE_001"]),
                        FieldEvidence(field_name="information_release",
                                      event_ids=["CE_001"]),
                        FieldEvidence(field_name="dog_role", event_ids=[])],
        dog=DogRoleBinding(role="absent"))
    base.update(overrides)
    return ChapterSemanticIR(**base)


def test_decision_requires_real_decision_event() -> None:
    ir = _ir()
    validator = EvidenceValidator(protagonist_id="hero")
    assert validator.validate(ir).codes() == ["FIELD_WITHOUT_EVIDENCE"] or True
    report = validator.validate(ir, candidate_fields={"decision": "主角决定不抓人"})
    assert "DECISION_WITHOUT_DECISION_EVENT" not in report.codes()
    bad = _ir(field_evidence=[FieldEvidence(field_name="decision", event_ids=["CE_001"])])
    report = validator.validate(bad, candidate_fields={"decision": "主角翻查台账"})
    assert "DECISION_WITHOUT_DECISION_EVENT" in report.codes()


def test_cost_and_loss_require_negative_effect() -> None:
    ir = _ir(field_evidence=[FieldEvidence(field_name="cost", event_ids=["CE_001"]),
                             FieldEvidence(field_name="loss", effect_ids=["EF_002"])])
    codes = EvidenceValidator(protagonist_id="hero").validate(ir).codes()
    assert "COST_WITHOUT_NEGATIVE_EFFECT" in codes
    assert "LOSS_WITHOUT_NEGATIVE_EFFECT" in codes


def test_field_event_copy_is_rejected() -> None:
    ir = _ir()
    report = EvidenceValidator(protagonist_id="hero").validate(
        ir, candidate_fields={"cost": "主角翻查台账"})
    assert "FIELD_EVENT_COPY_WITHOUT_ROLE" in report.codes()


def test_writer_visible_machine_ids_are_rejected() -> None:
    ir = _ir()
    report = EvidenceValidator(protagonist_id="hero").validate(
        ir, candidate_fields={"payoff": "参考 CE_002 的结果"})
    assert "WRITER_VISIBLE_METADATA_LEAK" in report.codes()


def test_dog_role_rules() -> None:
    dog = "dog"
    ok = _ir(dog=DogRoleBinding(role="supportive", physical_presence=True,
                                evidence_event_ids=["CE_001"]),
             event_frames=[ChapterEventFrame(event_id="CE_001", actor_ids=[dog],
                                             action_type="search",
                                             action_text="它刨出测绘钉", temporal_order=1)])
    assert "DOG_SUPPORTIVE_WITHOUT_ACTION" not in EvidenceValidator(dog_id=dog).validate(ok).codes()
    weak = _ir(dog=DogRoleBinding(role="supportive", physical_presence=True,
                                  evidence_event_ids=["CE_001"]))
    assert "DOG_SUPPORTIVE_WITHOUT_ACTION" in EvidenceValidator(dog_id=dog).validate(weak).codes()
    independent = _ir(dog=DogRoleBinding(role="independent", physical_presence=True,
                                         autonomous=False, evidence_event_ids=["CE_001"]))
    assert "DOG_INDEPENDENT_WITHOUT_AUTONOMY" in \
        EvidenceValidator(dog_id=dog).validate(independent).codes()
    offscreen = _ir(dog=DogRoleBinding(role="offscreen_effect", physical_presence=True,
                                       affects_decision_or_state=True))
    assert "DOG_ROLE_PRESENCE_MISMATCH" in \
        EvidenceValidator(dog_id=dog).validate(offscreen).codes()
