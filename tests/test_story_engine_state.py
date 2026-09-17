from __future__ import annotations

import pytest
from pydantic import ValidationError

from novelforge.story_engine import (
    ENTITY_MODELS,
    STORY_STATE_SCHEMA_VERSION,
    Ability,
    Character,
    Faction,
    KnowledgeEntry,
    Location,
    LocationState,
    PromiseState,
    RelationshipState,
    ResourceDefinition,
    ResourceStock,
    StoryState,
    StoryStateError,
    WorldState,
    from_legacy_adventure,
    story_state_from_payload,
    upgrade_story_state_payload,
)


REQUIRED_DOMAINS = {"world", "timeline", "location", "characters", "relationships", "knowledge",
                    "resources", "abilities", "factions", "flags", "promises",
                    "active_events", "resolved_events"}


def test_story_state_has_generic_domains_and_no_novel_specific_fields() -> None:
    fields = set(StoryState.model_fields)
    assert REQUIRED_DOMAINS <= fields
    assert {"schema_version", "novel_id", "legacy"} <= fields
    forbidden = {"supplies", "ally", "clue", "trust", "debt", "facts", "cultivation", "silicon",
                 "spirit_stones", "sect"}
    assert not (fields & forbidden)


def test_story_state_serializes_restores_and_compares() -> None:
    state = StoryState(
        novel_id="novel_a",
        characters={"hero": Character(id="hero", kind="character", tags=["player"],
                                       data={"voice": "简短"})},
        relationships=[RelationshipState(source_id="hero", target_id="mentor",
                                         dimensions={"trust": 0.5})],
        knowledge=[KnowledgeEntry(id="receipt_seen", holders=["hero"], source="action_01")],
        resources={"supplies": ResourceStock(id="supplies", amount=2, unit="份", holders=["hero"])},
        abilities={"observe": Ability(id="observe", kind="ability", data={"level": 1})},
        factions={"sect": Faction(id="sect", kind="faction")},
        promises=[PromiseState(id="promise_01", debtor="hero", creditor="mentor", status="open")],
        flags={"met_mentor": True},
        location={"current": "gate", "known": {"gate": {"id": "gate", "name": "山门"}}},
    )
    restored = StoryState.model_validate_json(state.model_dump_json())
    assert restored == state
    assert restored.characters["hero"].data["voice"] == "简短"
    changed = state.model_copy(deep=True)
    changed.flags["met_mentor"] = False
    assert changed != state


def test_story_state_rejects_invalid_resources_and_events() -> None:
    with pytest.raises(ValidationError):
        ResourceStock(id="supplies", amount=-1)
    with pytest.raises(ValidationError):
        StoryState(active_events=[{"id": "event_01", "status": "resolved"}])
    with pytest.raises(ValidationError):
        StoryState(characters={"other_key": Character(id="hero")})
    with pytest.raises(ValidationError):
        RelationshipState(source_id="hero", target_id="hero")


def test_upgrade_payload_fills_sections_and_preserves_unknown_fields() -> None:
    payload = {"schema_version": 1, "novel_id": "novel_a", "flags": {"met_mentor": True},
               "draft_note": {"from": "older_build"}}
    upgraded = upgrade_story_state_payload(payload)
    assert upgraded["schema_version"] == STORY_STATE_SCHEMA_VERSION
    assert upgraded["legacy"]["draft_note"] == {"from": "older_build"}
    assert "draft_note" not in upgraded
    state = story_state_from_payload(payload)
    assert state.flags == {"met_mentor": True}
    assert state.legacy["draft_note"] == {"from": "older_build"}
    assert state.characters == {} and state.resources == {}

    without_version = story_state_from_payload({})
    assert without_version.schema_version == STORY_STATE_SCHEMA_VERSION


def test_upgrade_rejects_future_or_invalid_versions() -> None:
    with pytest.raises(StoryStateError):
        upgrade_story_state_payload({"schema_version": STORY_STATE_SCHEMA_VERSION + 1})
    with pytest.raises(StoryStateError):
        upgrade_story_state_payload({"schema_version": "v1"})
    with pytest.raises(StoryStateError):
        upgrade_story_state_payload(["not", "an", "object"])


def test_legacy_adventure_reads_losslessly_without_inventing_state() -> None:
    legacy = {
        "blueprint_id": "bp_legacy",
        "blueprint_version": 1,
        "revision": 3,
        "rules_version": 2,
        "branch_id": "main",
        "parent_branch": None,
        "fork_revision": None,
        "supplies": 2,
        "ally": True,
        "clue": False,
        "trust": 1,
        "debt": 0,
        "facts": ["receipt", "diversion_verified"],
        "arc_finished": False,
        "history": [{"scene": "第一关", "choice_id": "clue", "choice": "先查线索",
                     "result": "留下证据"}],
    }
    state = from_legacy_adventure(legacy, novel_id="legacy_novel")
    assert state.novel_id == "legacy_novel"
    assert state.resources["supplies"].amount == 2
    assert state.resources["supplies"].source == "legacy_adventure"
    assert {item.id for item in state.knowledge} == {"receipt", "diversion_verified"}
    assert state.knowledge[0].holders == ["protagonist"]
    assert state.flags == {"legacy.ally": True, "legacy.clue": False}
    assert state.legacy["source"] == "legacy_adventure"
    assert state.legacy["adventure"] == legacy
    assert "trust" not in state.flags and "debt" not in state.flags
    assert state.promises == [] and state.active_events == []
    assert StoryState.model_validate_json(state.model_dump_json()) == state


def test_legacy_adventure_rejects_invalid_supplies() -> None:
    with pytest.raises(StoryStateError):
        from_legacy_adventure({"supplies": -3})
    with pytest.raises(StoryStateError):
        from_legacy_adventure({"supplies": "两份"})
    with pytest.raises(StoryStateError):
        from_legacy_adventure(["not", "an", "object"])


def test_same_entity_model_expresses_xianxia_and_science_fiction() -> None:
    xianxia = StoryState(
        novel_id="novel_xianxia",
        world=WorldState(rules=["获得必有交换"], terms={"境界": "修炼阶段"}),
        characters={"ling": Character(id="ling", kind="disciple", name="凌", status="在世",
                                      tags=["宗门弟子"], data={"境界": "炼气三层"})},
        factions={"qingyun": Faction(id="qingyun", kind="sect", name="青云宗",
                                     stance="控制灵脉与配给")},
        abilities={"breath": Ability(id="breath", kind="功法", name="引气诀",
                                     limits=["需要灵石"])},
        resources={"spirit_stone": ResourceStock(id="spirit_stone", amount=12, unit="枚",
                                                 holders=["ling"], source="event_gift")},
        location=LocationState(current="qingyun_gate",
                               known={"qingyun_gate": Location(id="qingyun_gate", kind="sect_gate",
                                                               name="青云山门", access="需弟子身份")}),
    )
    science_fiction = StoryState(
        novel_id="novel_scifi",
        world=WorldState(rules=["能源有配额"], terms={"权限": "访问级别"}),
        characters={"unit_7": Character(id="unit_7", kind="android", name="第七单元", status="在线",
                                        tags=["公司资产"], data={"算力": "受限"})},
        factions={"helix": Faction(id="helix", kind="corporation", name="螺旋公司",
                                   stance="垄断能源网络")},
        abilities={"intrude": Ability(id="intrude", kind="义体功能", name="接口入侵",
                                      limits=["需要通行权限"])},
        resources={"energy": ResourceStock(id="energy", amount=40, unit="kWh",
                                           holders=["unit_7"], source="event_recharge")},
        location=LocationState(current="station_9",
                               known={"station_9": Location(id="station_9", kind="space_station",
                                                            name="九号站", access="需通行权限")}),
    )
    assert set(xianxia.model_dump()) == set(science_fiction.model_dump())
    assert type(xianxia.characters["ling"]) is type(science_fiction.characters["unit_7"]) is Character
    assert type(xianxia.abilities["breath"]) is type(science_fiction.abilities["intrude"]) is Ability
    assert type(xianxia.factions["qingyun"]) is type(science_fiction.factions["helix"]) is Faction
    assert type(xianxia.location.known["qingyun_gate"]) is Location
    assert xianxia.characters["ling"].data["境界"] == "炼气三层"
    assert science_fiction.characters["unit_7"].data["算力"] == "受限"
    assert xianxia.factions["qingyun"].kind == "sect"
    assert science_fiction.factions["helix"].kind == "corporation"
    for state in (xianxia, science_fiction):
        assert StoryState.model_validate_json(state.model_dump_json()) == state


def test_entity_models_do_not_hardcode_genre_fields() -> None:
    generic = {"id", "kind", "tags", "data"}
    genre_specific = {"cultivation", "realm", "mana", "qi", "cyberware", "spirit_stone", "sect"}
    for model in ENTITY_MODELS:
        assert "id" in model.model_fields
        assert not (set(model.model_fields) & genre_specific)
    for model in (Character, Faction, Location, Ability, ResourceDefinition):
        assert generic <= set(model.model_fields)
