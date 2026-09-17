"""S02：ChapterIRValidator —— 合并 evidence + state + writer-visible 三层。"""

from __future__ import annotations

from novelforge.story_engine.chapter_ir.models import (
    ChapterEffect,
    ChapterEventFrame,
    ChapterSemanticIR,
    ChapterStateTransition,
    FieldEvidence,
)
from novelforge.story_engine.chapter_ir.state import build_default_registry
from novelforge.story_engine.chapter_ir.validator import ChapterIRValidator


def test_world_state_change_without_transition_fails() -> None:
    ir = ChapterSemanticIR(
        chapter_uuid="uuid_z", novel_id="n1", temporal_position=107,
        event_frames=[ChapterEventFrame(event_id="CE_001", actor_ids=["hero"],
                                        action_text="主角押货走旧道", temporal_order=1)],
        effects=[ChapterEffect(effect_id="EF_001", polarity="negative",
                               after_state="半车货被夺")],
        field_evidence=[FieldEvidence(field_name="world_state_change", event_ids=["CE_001"])],
    )
    report = ChapterIRValidator(registry=build_default_registry({})).validate(
        ir, candidate_fields={"world_state_change": "盐路正式受控制"})
    assert "WORLD_STATE_WITHOUT_TRANSITION" in report.codes()


def test_premature_transition_surfaces_in_validator() -> None:
    ir = ChapterSemanticIR(
        chapter_uuid="uuid_w", novel_id="n1", temporal_position=107,
        state_transitions=[ChapterStateTransition(
            transition_id="ST_001", state_key="salt_route_control", from_state="contested",
            to_state="controlled_by_rust_settlement", transition_kind="acquisition",
            effective_at=107)],
        field_evidence=[FieldEvidence(field_name="world_state_change",
                                      transition_ids=["ST_001"])],
    )
    registry = build_default_registry({"salt_route_control": 133})
    report = ChapterIRValidator(registry=registry).validate(
        ir, candidate_fields={"world_state_change": "盐路控制权归本方"})
    assert "PREMATURE_STATE_TRANSITION" in report.codes()


def test_missing_field_evidence_fails() -> None:
    ir = ChapterSemanticIR(chapter_uuid="uuid_v", novel_id="n1", temporal_position=10)
    report = ChapterIRValidator().validate(ir)
    assert "FIELD_WITHOUT_EVIDENCE" in report.codes()
