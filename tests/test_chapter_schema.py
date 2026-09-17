"""C03：严格 Schema Gate（类型安全 + 语义安全 + 修复回路）。"""

from __future__ import annotations

import pytest

from novelforge.story_engine.canon.gate import (
    SchemaGateError,
    validate_bundle,
    validate_chapter_plan,
    validate_chapters,
)


def _plan(**overrides) -> dict:
    base = {
        "chapter_uuid": "uuid-a", "display_number": 12, "title": "断粮的清晨",
        "estimated_words": 3000,
        "concrete_events": ["韩彻数出干粮只够一天", "阿灰把水壶顶到他脚边",
                            "营地的人议论井已经见底"],
        "dog_role": "involved", "dog_action": "阿灰把水壶顶到他脚边",
    }
    base.update(overrides)
    return base


def test_string_events_are_blocked_not_iterated() -> None:
    with pytest.raises(SchemaGateError) as excinfo:
        validate_chapter_plan(_plan(concrete_events="韩彻利用场域挡住灰暴"))
    assert excinfo.value.code == "CHAPTER_PLAN_SCHEMA_INVALID"
    assert any("list[str]" in issue for issue in excinfo.value.issues)


def test_numeric_string_is_not_coerced_in_strict_mode() -> None:
    with pytest.raises(SchemaGateError):
        validate_chapter_plan(_plan(estimated_words="3000"))


def test_duplicate_and_fragment_events_are_blocked() -> None:
    with pytest.raises(SchemaGateError):
        validate_chapter_plan(_plan(concrete_events=["韩彻拆掉最后一辆废车"] * 4))
    with pytest.raises(SchemaGateError):
        validate_chapter_plan(_plan(concrete_events=["韩", "彻", "利", "用"]))


def test_dog_role_enum_and_alignment() -> None:
    with pytest.raises(SchemaGateError):
        validate_chapter_plan(_plan(dog_role="telepathic"))
    with pytest.raises(SchemaGateError):
        validate_chapter_plan(_plan(dog_role="independent", dog_action=None))
    assert validate_chapter_plan(_plan()).dog_role == "involved"


def test_writer_visible_metadata_is_blocked() -> None:
    with pytest.raises(SchemaGateError):
        validate_chapter_plan(_plan(hook="与 ch142 那章相同"))
    with pytest.raises(SchemaGateError):
        validate_chapter_plan(_plan(start_state="承接 FACT_RADIO_FIRST_RESPONSE"))


def test_repair_prompt_contains_issues_and_batch_validation() -> None:
    with pytest.raises(SchemaGateError) as excinfo:
        validate_chapters([_plan(), _plan(concrete_events="一句话")])
    assert "第2章" in excinfo.value.repair_prompt()
    assert validate_chapters([_plan()])[0].chapter_uuid == "uuid-a"


def test_bundle_validation() -> None:
    bundle = validate_bundle({
        "facts": [{"canonical_description": "旧收音机第一次回应", "status": "planned"}],
        "events": [{"canonical_name": "锈牙第一次收过路费", "narrative_role": "canonical"}],
        "chapters": [_plan()],
    })
    assert bundle.facts and bundle.events and bundle.chapters
