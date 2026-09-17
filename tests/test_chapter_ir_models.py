"""S01：Chapter Semantic IR 模型与严格 Gate。"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from novelforge.story_engine.chapter_ir.models import (
    IRFlags,
    ChapterEventFrame,
    ChapterSemanticIR,
    compile_ir_ref,
)
from novelforge.story_engine.chapter_ir.schemas import IRGateError, validate_ir


def test_event_frame_rejects_chapter_number_identity() -> None:
    with pytest.raises(ValidationError):
        ChapterEventFrame(event_id="ch142")
    with pytest.raises(ValidationError):
        ChapterEventFrame(event_id="chapter_142")
    assert ChapterEventFrame(event_id="CE_001").event_id == "CE_001"


def test_flags_default_off_and_env_override(monkeypatch) -> None:
    assert IRFlags().chapter_semantic_ir_v1 is False
    assert IRFlags().chapter_semantic_ir_shadow is False
    monkeypatch.setenv("CHAPTER_SEMANTIC_IR_V1", "true")
    assert IRFlags.from_env().chapter_semantic_ir_v1 is True


def test_ir_identity_has_no_display_number() -> None:
    ir = ChapterSemanticIR(chapter_uuid="uuid_ch_1", novel_id="n1", temporal_position=325)
    assert "ch325" not in ir.chapter_uuid
    assert compile_ir_ref(ir.chapter_uuid).startswith("ir://uuid_ch_1/v")
    payload = ir.model_dump(mode="json")
    assert "display_number" not in payload
    assert payload["schema_version"] == 1


def test_strict_gate_rejects_string_events() -> None:
    raw = {"chapter_uuid": "uuid_a", "novel_id": "n1", "event_frames": "CE_001"}
    with pytest.raises(IRGateError) as exc:
        validate_ir(raw)
    assert exc.value.code == "CHAPTER_IR_SCHEMA_INVALID"
