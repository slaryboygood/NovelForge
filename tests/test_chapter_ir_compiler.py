"""S03：ChapterFieldCompiler —— 事实来自 IR，渲染确定，不引入 IR 外的事实。"""

from __future__ import annotations

from novelforge.story_engine.chapter_ir.compiler import ChapterFieldCompiler
from novelforge.story_engine.chapter_ir.models import (
    ChapterEffect,
    ChapterEventFrame,
    ChapterSemanticIR,
    ChapterStateTransition,
    FieldEvidence,
)


def _ir() -> ChapterSemanticIR:
    return ChapterSemanticIR(
        chapter_uuid="uuid_y", novel_id="n1", temporal_position=133,
        event_frames=[
            ChapterEventFrame(event_id="CE_001", actor_ids=["hero"], action_type="negotiate",
                              action_text="主角带着新路口条件回桌上谈判", temporal_order=1),
            ChapterEventFrame(event_id="CE_002", actor_ids=["hero"], action_type="decision",
                              decision_action="retain", changes_followup_path=True,
                              action_text="主角不拦商队，坚持按趟结算", temporal_order=2)],
        effects=[ChapterEffect(effect_id="EF_001", effect_type="cost", polarity="negative",
                               target_id="party", after_state="两车货压在路上三日"),
                 ChapterEffect(effect_id="EF_002", effect_type="gain", polarity="positive",
                               target_id="goal", after_state="报备权归本方")],
        state_transitions=[ChapterStateTransition(
            transition_id="ST_001", state_key="salt_route_control", from_state="contested",
            to_state="controlled_by_rust_settlement", transition_kind="acquisition",
            effective_at=133)],
        field_evidence=[FieldEvidence(field_name="decision", event_ids=["CE_002"]),
                        FieldEvidence(field_name="cost", effect_ids=["EF_001"]),
                        FieldEvidence(field_name="payoff", effect_ids=["EF_002"]),
                        FieldEvidence(field_name="turn", transition_ids=["ST_001"]),
                        FieldEvidence(field_name="world_state_change", transition_ids=["ST_001"])],
        )


def test_compile_is_deterministic() -> None:
    compiler = ChapterFieldCompiler(actor_names={"hero": "主角"})
    first = compiler.compile(_ir())
    second = compiler.compile(_ir())
    assert first.model_dump() == second.model_dump()


def test_compiled_fields_carry_provenance() -> None:
    compiled = ChapterFieldCompiler(actor_names={"hero": "主角"}).compile(_ir())
    decision = compiled.provenance("decision")
    assert decision is not None and decision.compiled_from_event_ids == ["CE_002"]
    turn = compiled.provenance("turn")
    assert turn is not None and turn.compiled_from_transition_ids == ["ST_001"]
    assert "controlled_by_rust_settlement" in turn.text
    assert compiled.semantic_ir_ref.startswith("ir://uuid_y/v")


def test_compiler_does_not_invent_facts() -> None:
    compiled = ChapterFieldCompiler(actor_names={"hero": "主角"}).compile(_ir())
    for field in compiled.fields:
        assert field.compiled_from_event_ids or field.compiled_from_effect_ids \
            or field.compiled_from_transition_ids or field.text == ""
    assert "封死" not in compiled.field("world_state_change")


def test_dog_payload_comes_from_evidence_event() -> None:
    ir = _ir()
    ir.event_frames.append(ChapterEventFrame(event_id="CE_003", actor_ids=["dog"],
                                             action_type="search",
                                             action_text="它刨出测绘钉", temporal_order=3))
    from novelforge.story_engine.chapter_ir.models import DogRoleBinding
    ir.dog = DogRoleBinding(role="supportive", physical_presence=True,
                            evidence_event_ids=["CE_003"])
    compiled = ChapterFieldCompiler(dog_id="dog").compile(ir)
    assert compiled.dog_payload is not None
    assert "刨出测绘钉" in compiled.dog_payload.text
    assert compiled.dog_payload.compiled_from_event_ids == ["CE_003"]
