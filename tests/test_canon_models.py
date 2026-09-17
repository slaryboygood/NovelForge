"""C01：Canon 稳定身份模型与 Planner schema 测试。"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from novelforge.story_engine.canon import (
    CanonEvent,
    CanonFact,
    CanonForeshadow,
    CanonRenderRef,
    ChapterPlan,
    new_canon_id,
    validate_canon_id,
)


def test_stable_fact_id_and_immutable_happened() -> None:
    fact = CanonFact(fact_id="FACT_ZERO_LAYER_GATE_FIRST_OPEN",
                     canonical_key="ZERO_LAYER_GATE_FIRST_OPEN", novel_id="n1",
                     status="happened", canonical_description="第一次打开第零层门禁")
    assert fact.immutable is True
    assert fact.fact_id == "FACT_ZERO_LAYER_GATE_FIRST_OPEN"


def test_chapter_number_cannot_be_identity() -> None:
    for bad in ("ch142", "chapter_142", "volume3_ch20", "route0008"):
        with pytest.raises(ValueError):
            validate_canon_id(bad)
        with pytest.raises(ValidationError):
            CanonFact(fact_id=bad, canonical_key="X_KEY", novel_id="n1")


def test_random_key_is_persistable_and_not_recomputed() -> None:
    first = new_canon_id("fact")
    second = new_canon_id("fact")
    assert first != second
    assert first.startswith("FACT_")


def test_planned_fact_is_mutable_but_happened_is_not_replaced() -> None:
    planned = CanonFact(fact_id="FACT_RAIDER_FIRST_TOLL", canonical_key="RAIDER_FIRST_TOLL",
                        novel_id="n1", status="planned", canonical_description="锈牙第一次收过路费")
    updated = planned.model_copy(update={"canonical_description": "锈牙第一次收过路费（改写）"})
    assert updated.canonical_description.endswith("（改写）")
    happened = planned.model_copy(update={"status": "happened"})
    assert happened.immutable is True


def test_event_narrative_role_requires_canonical_anchor() -> None:
    consequence = CanonEvent(event_id="EVENT_RAIDER_RETALIATION", canonical_key="RAIDER_RETALIATION",
                             novel_id="n1", narrative_role="consequence",
                             canonical_event_id="EVENT_RAIDER_FIRST_TOLL")
    assert consequence.narrative_role == "consequence"
    with pytest.raises(ValidationError):
        CanonEvent(event_id="EVENT_RAIDER_RETALIATION", canonical_key="RAIDER_RETALIATION",
                   novel_id="n1", narrative_role="consequence")
    with pytest.raises(ValidationError):
        CanonEvent(event_id="EVENT_DUP", canonical_key="DUP", novel_id="n1",
                   narrative_role="canonical", canonical_event_id="EVENT_OTHER")


def test_foreshadow_requires_reveal_before_payoff() -> None:
    with pytest.raises(ValidationError):
        CanonForeshadow(foreshadow_id="FS_DOG_TAG", novel_id="n1", status="paid_off")
    ok = CanonForeshadow(foreshadow_id="FS_DOG_TAG", novel_id="n1", status="paid_off",
                         reveal_ref=CanonRenderRef(chapter_uuid="uuid-a", display_number=325))
    assert ok.status == "paid_off"


def _chapter(**overrides) -> dict:
    base = {
        "chapter_uuid": "uuid-a", "display_number": 1, "title": "断粮的清晨",
        "concrete_events": ["韩彻数出剩下的干粮只够一天", "阿灰用鼻子把水壶顶到他脚边",
                            "营地的人议论井已经见底"],
        "dog_role": "involved", "dog_action": "阿灰用鼻子把水壶顶到他脚边",
    }
    base.update(overrides)
    return base


def test_string_concrete_events_is_rejected() -> None:
    with pytest.raises(ValidationError) as excinfo:
        ChapterPlan(**_chapter(concrete_events="韩彻利用场域挡住灰暴"))
    assert "list[str]" in str(excinfo.value)


def test_duplicate_or_fragment_events_are_rejected() -> None:
    with pytest.raises(ValidationError):
        ChapterPlan(**_chapter(concrete_events=["韩彻拆掉最后一辆废车"] * 4))
    with pytest.raises(ValidationError):
        ChapterPlan(**_chapter(concrete_events=["韩", "彻", "利", "用"]))
    with pytest.raises(ValidationError):
        ChapterPlan(**_chapter(concrete_events=["拆车", "翻墙", "点灯"]))


def test_dog_role_alignment_and_visible_text_guard() -> None:
    with pytest.raises(ValidationError):
        ChapterPlan(**_chapter(dog_role="independent", dog_action=None))
    with pytest.raises(ValidationError):
        ChapterPlan(**_chapter(dog_role="absent", dog_action="阿灰跟着"))
    with pytest.raises(ValidationError):
        ChapterPlan(**_chapter(hook="与 ch142 的开门相同"))
    ok = ChapterPlan(**_chapter(dog_role="absent", dog_action=None))
    assert ok.dog_role == "absent"
