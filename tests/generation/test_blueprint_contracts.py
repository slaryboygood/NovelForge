"""Blueprint 节点契约（V4-04 §5–§12、§47）。"""

from __future__ import annotations

import pytest

from novelforge.blueprint import (
    ALLOWED_STATUS_TRANSITIONS,
    BLUEPRINT_SCHEMA_VERSION,
    NODE_ID_PREFIX,
    PAYLOAD_MODELS,
    BlueprintNode,
    ChapterCardPayload,
    CharacterPayload,
    PremisePayload,
    SceneCardPayload,
    slug,
)
from gen_support import chapter_payload, premise_payload, scene_payload


def test_payload_models_are_strict() -> None:
    with pytest.raises(Exception):
        PremisePayload(premise="x", unexpected_field=1)
    with pytest.raises(Exception):
        ChapterCardPayload(title="")
    with pytest.raises(Exception):
        SceneCardPayload(scene_purpose="", story_function=["invented_function"])


def test_node_carries_revision_and_provenance_fields() -> None:
    node = BlueprintNode(node_id="premise", novel_id="novel_a", node_type="premise",
                         payload=PremisePayload(**premise_payload()))
    payload = node.as_dict()
    for key in ("node_id", "novel_id", "node_type", "parent_id", "revision",
                "parent_revision", "status", "source_ids", "context_digest",
                "created_at", "updated_at", "generation_contract",
                "generation_contract_version", "provenance", "quality_status",
                "schema_version", "sequence"):
        assert key in payload
    assert payload["status"] == "proposed", "生成结果默认是 proposal（ADR-017）"
    assert payload["quality_status"] == "unevaluated"
    assert payload["schema_version"] == BLUEPRINT_SCHEMA_VERSION


def test_node_id_must_be_system_style() -> None:
    for bad in ("Chapter-1", "第一章", "ch 1", ""):
        with pytest.raises(ValueError):
            BlueprintNode(node_id=bad, novel_id="novel_a", node_type="premise",
                          payload=PremisePayload(**premise_payload()))


def test_node_requires_novel_id_and_known_type() -> None:
    with pytest.raises(ValueError):
        BlueprintNode(node_id="premise", novel_id="", node_type="premise",
                      payload=PremisePayload(**premise_payload()))
    with pytest.raises(ValueError):
        BlueprintNode(node_id="x_node", novel_id="novel_a", node_type="mystery",
                      payload=PremisePayload(**premise_payload()))


def test_payload_models_cover_all_node_types() -> None:
    assert set(PAYLOAD_MODELS) == {
        "premise", "theme", "world", "character", "character_arc", "story_arc",
        "structural_unit", "chapter", "scene", "causal_link", "setup", "payoff"}
    assert set(NODE_ID_PREFIX) == set(PAYLOAD_MODELS)


def test_status_transitions_are_bounded() -> None:
    assert ALLOWED_STATUS_TRANSITIONS["proposed"] == ("draft", "accepted",
                                                     "superseded")
    assert ALLOWED_STATUS_TRANSITIONS["accepted"] == ("superseded",)
    assert ALLOWED_STATUS_TRANSITIONS["superseded"] == ()


def test_slug_is_stable_and_ascii_safe() -> None:
    assert slug("Old Crow") == "old_crow"
    assert slug("老鸦") == "item", "纯非 ASCII 名称由调用方补摘要（见 character_node_id）"
    assert slug("A-1", fallback="x") == "a_1"


def test_character_node_id_avoids_placeholder_collisions() -> None:
    from novelforge.generation.tasks.characters import character_node_id

    first = character_node_id(1, "韩彻")
    second = character_node_id(1, "老鸦")
    assert first != second, "不同中文名必须得到不同 id"
    assert first.startswith("char_01_") and len(first) <= 64


def test_node_roundtrip_from_dict() -> None:
    node = BlueprintNode(node_id="ch_001", novel_id="novel_a", node_type="chapter",
                         payload=ChapterCardPayload(**chapter_payload()), sequence=1)
    restored = BlueprintNode.from_dict(node.as_dict())
    assert restored.node_id == node.node_id
    assert isinstance(restored.payload, ChapterCardPayload)
    assert restored.payload.title == node.payload.title

