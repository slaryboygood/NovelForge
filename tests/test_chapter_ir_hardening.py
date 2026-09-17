"""S07：Pilot Hardening —— decision taxonomy / assertion mode / pivot turn / dog plumbing /
compile blocked / disposition / transition-level binding。"""

from __future__ import annotations

from novelforge.story_engine.chapter_ir.builder import ChapterIRBuilder
from novelforge.story_engine.chapter_ir.compiler import ChapterFieldCompiler
from novelforge.story_engine.chapter_ir.evidence import EvidenceValidator
from novelforge.story_engine.chapter_ir.models import (
    ChapterEffect,
    ChapterEventFrame,
    ChapterSemanticIR,
    ChapterStateTransition,
    DogRoleBinding,
    FieldEvidence,
)
from novelforge.story_engine.chapter_ir.state import (
    TransitionBinding,
    build_default_registry,
)
from novelforge.story_engine.chapter_ir.validator import ChapterIRValidator

NAMES = {"主角": "hero", "阿灰": "dog"}


def _chapter(**overrides) -> dict:
    base = {
        "id": "ch500", "chapter_uuid": "uuid_500", "display_number": 500, "volume": 9, "arc": "A1",
        "goal": "在谈判桌前定下走哪条路",
        "events": ["主角把两条路线摆上桌", "主角拒绝按对方条件签字",
                   "主角决定改走慢路并把药留给伤员"],
        "decision": "主角改走慢路", "cost": "两车货压在道上", "loss": "失去一车补给",
        "turn": "对方先松口", "payoff": "拿到通行条件", "world_state_change": "通道开通",
        "dog_role": "supportive", "dog_note": "阿灰刨出测绘钉",
    }
    base.update(overrides)
    return base


def _ir(**overrides) -> ChapterSemanticIR:
    base = dict(
        chapter_uuid="uuid_h", novel_id="n1", temporal_position=100,
        event_frames=[
            ChapterEventFrame(event_id="CE_001", actor_ids=["hero"], action_type="decision",
                              decision_action="decide", changes_followup_path=True,
                              action_text="主角改走慢路", temporal_order=1)],
        effects=[ChapterEffect(effect_id="EF_001", effect_type="cost", polarity="negative",
                               after_state="两车货压在道上"),
                 ChapterEffect(effect_id="EF_002", effect_type="gain", polarity="positive",
                               after_state="拿到通行条件")],
        field_evidence=[FieldEvidence(field_name="decision", event_ids=["CE_001"]),
                        FieldEvidence(field_name="cost", effect_ids=["EF_001"]),
                        FieldEvidence(field_name="loss", effect_ids=["EF_001"]),
                        FieldEvidence(field_name="payoff", effect_ids=["EF_002"])],
    )
    base.update(overrides)
    return ChapterSemanticIR(**base)


def test_decision_taxonomy_positive_and_false_positive() -> None:
    ok = _ir()
    assert "DECISION_WITHOUT_DECISION_EVENT" not in \
        EvidenceValidator(protagonist_id="hero").validate(ok).codes()
    # 「阿灰低吼」型：actor 不是主角且没有 choice/commitment
    weak = _ir(event_frames=[ChapterEventFrame(event_id="CE_001", actor_ids=["dog"],
                                               action_text="阿灰低吼了一声", temporal_order=1)],
               field_evidence=[FieldEvidence(field_name="decision", event_ids=["CE_001"])])
    assert "DECISION_WITHOUT_DECISION_EVENT" in \
        EvidenceValidator(protagonist_id="hero").validate(weak).codes()


def test_historical_reference_does_not_drive_registry() -> None:
    registry = build_default_registry({})
    registry.bind(TransitionBinding("zero_layer_access", "permanently_sealed",
                                    "uuid_seal", 379))
    historical = ChapterStateTransition(
        transition_id="ST_001", state_key="zero_layer_access", from_state="emergency_locked",
        to_state="permanently_sealed", transition_kind="irreversible", effective_at=400,
        assertion_mode="historical_reference")
    assert registry.validate([historical], chapter_position=400) == []
    live = historical.model_copy(update={"assertion_mode": "transition"})
    assert "REPEATED_IRREVERSIBLE_TRANSITION" in \
        {item.code for item in registry.validate([live], chapter_position=400)}


def test_turn_from_major_effect() -> None:
    ir = _ir(effects=[ChapterEffect(effect_id="EF_003", effect_type="narrative_pivot",
                                    polarity="mixed", is_narrative_pivot=True,
                                    after_state="局势翻转"),
                      ChapterEffect(effect_id="EF_001", effect_type="cost",
                                    polarity="negative", after_state="代价")],
             field_evidence=[FieldEvidence(field_name="turn", effect_ids=["EF_003"])])
    assert "TURN_WITHOUT_TRANSITION" not in \
        EvidenceValidator(protagonist_id="hero").validate(ir).codes()
    plain = _ir(field_evidence=[FieldEvidence(field_name="turn", effect_ids=["EF_001"])])
    assert "TURN_WITHOUT_TRANSITION" in \
        EvidenceValidator(protagonist_id="hero").validate(plain).codes()


def test_dog_binding_plumbing_and_absent_presence() -> None:
    ir = _ir(dog=DogRoleBinding(role="supportive", physical_presence=True,
                                evidence_event_ids=["CE_001"]),
             field_evidence=[FieldEvidence(field_name="dog_role", event_ids=[])])
    codes = EvidenceValidator(dog_id="dog").validate(ir).codes()
    assert "DOG_BINDING_PLUMBING_ERROR" in codes
    absent_bad = _ir(dog=DogRoleBinding(role="absent", physical_presence=True))
    assert "DOG_ROLE_PRESENCE_MISMATCH" in \
        EvidenceValidator(dog_id="dog").validate(absent_bad).codes()
    absent_ok = _ir(dog=DogRoleBinding(role="absent", physical_presence=False))
    assert "DOG_ROLE_PRESENCE_MISMATCH" not in \
        EvidenceValidator(dog_id="dog").validate(absent_ok).codes()


def test_compiler_blocks_when_evidence_missing() -> None:
    ir = _ir(field_evidence=[FieldEvidence(field_name="decision", event_ids=[]),
                             FieldEvidence(field_name="cost", effect_ids=[])])
    compiled = ChapterFieldCompiler(actor_names={"hero": "主角"}).compile(ir)
    assert compiled.provenance("decision").status == "BLOCKED_MISSING_EVIDENCE"
    assert compiled.provenance("cost").status == "BLOCKED_MISSING_EVIDENCE"
    assert compiled.provenance("decision").text == ""


def test_migration_disposition_and_field_copy_removed() -> None:
    builder = ChapterIRBuilder(novel_id="n1", dog_id="dog", dog_name="阿灰",
                               protagonist_id="hero", actor_names=NAMES)
    chapter = _chapter(decision="主角把两条路线摆上桌",
                       cost="主角把两条路线摆上桌")
    ir = builder.from_legacy(chapter, name_to_id=NAMES, index=500)
    ir = builder.migration.finalize(ir, chapter, ["DECISION_WITHOUT_DECISION_EVENT"])
    assert ir.migration_disposition == "NEEDS_CONTENT_REPAIR"
    assert ir.legacy_field_copy_removed >= 1
    ready = builder.from_legacy(_chapter(), name_to_id=NAMES, index=500)
    ready = builder.migration.finalize(ready, _chapter(), [])
    assert ready.migration_disposition == "READY_TO_COMPILE"


def test_decision_taxonomy_is_recorded_by_migration() -> None:
    builder = ChapterIRBuilder(novel_id="n1", dog_id="dog", dog_name="阿灰",
                               protagonist_id="hero", actor_names=NAMES)
    ir = builder.from_legacy(_chapter(), name_to_id=NAMES, index=500)
    assert any(event.decision_action for event in ir.event_frames)
    assert all(event.decision_action in
               ("", "choose", "decide", "refuse", "accept", "commit", "defer", "allow",
                "forbid", "assign", "retain", "abandon", "withhold", "prioritize", "trade_off",
                "sign", "approve", "reject", "wait", "withdraw")
               for event in ir.event_frames)
