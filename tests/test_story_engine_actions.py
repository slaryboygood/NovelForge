from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from novelforge.story_engine import (
    Action,
    ActionCatalog,
    ActionResolver,
    Condition,
    EffectRecord,
    KnowledgeEntry,
    RelationshipState,
    ResourceStock,
    StoryState,
    apply_effects,
    evaluate,
    evaluate_all,
    resolve_path,
)
from novelforge.story_engine.effects import EffectSpec


ROOT = Path(__file__).resolve().parents[1]


def xianxia_state() -> StoryState:
    return StoryState(
        novel_id="novel_xianxia",
        characters={"hero": {"id": "hero", "kind": "disciple", "name": "凌"}},
        resources={"spirit_stone": ResourceStock(id="spirit_stone", amount=5, unit="枚",
                                                 holders=["hero"])},
        relationships=[RelationshipState(source_id="hero", target_id="master",
                                         dimensions={"trust": 1})],
        knowledge=[KnowledgeEntry(id="secret_cave", holders=["hero"])],
        flags={"sect_notice": False},
        identities={"hero": ["外门弟子"]},
        location={"current": "qingyun_gate"},
        resolved_events=[{"id": "event_first_test", "status": "resolved"}],
    )


def scifi_state() -> StoryState:
    return StoryState(
        novel_id="novel_scifi",
        characters={"unit_7": {"id": "unit_7", "kind": "android", "name": "第七单元"}},
        resources={"energy": ResourceStock(id="energy", amount=50, unit="kWh", holders=["unit_7"])},
        flags={"alarm": False},
        identities={"unit_7": ["civil_level"]},
        location={"current": "station_9"},
    )


BREAKTHROUGH = Action(
    id="cultivate_breakthrough",
    kind="progression",
    name="突破境界",
    actor="hero",
    type="cultivate",
    requirements=[Condition(op="resource", entity="hero", key="spirit_stone", value=3, comparator=">="),
                  Condition(op="identity", entity="hero", value="外门弟子")],
    costs=[EffectSpec(id="pay_stones", op="remove_resource", entity="hero", target="spirit_stone", value=3)],
    risks=[{"id": "backlash", "description": "根基不稳", "probability": 0.4,
            "effects": [{"op": "change_relationship", "entity": "hero", "target": "master",
                         "key": "trust", "value": -1}]}],
    immediate_effects=[
        EffectSpec(id="gain_rank", op="add_identity", entity="hero", value="内门弟子"),
        EffectSpec(id="gain_art", op="grant_ability", entity="hero", target="qi_art",
                   data={"kind": "功法", "name": "引气诀"}),
        EffectSpec(id="notice", op="set_flag", key="sect_notice", value=True),
        EffectSpec(id="event", op="trigger_event", target="sect_notice_event"),
    ],
    delayed_effects=[{"id": "sect_inquiry", "source": "cultivate_breakthrough",
                      "description": "宗门调查突破材料来源",
                      "trigger": {"op": "flag", "key": "sect_notice", "value": True},
                      "effects": [{"op": "change_relationship", "entity": "hero",
                                   "target": "master", "key": "trust", "value": -1}]}],
    visibility="hidden",
)

NEURAL_UPGRADE = Action(
    id="neural_upgrade",
    kind="progression",
    name="神经升级",
    actor="unit_7",
    type="upgrade",
    requirements=[Condition(op="resource", entity="unit_7", key="energy", value=30, comparator=">="),
                  Condition(op="identity", entity="unit_7", value="civil_level")],
    costs=[EffectSpec(id="pay_energy", op="remove_resource", entity="unit_7", target="energy", value=30)],
    risks=[{"id": "overheat", "description": "过热", "probability": 0.4,
            "effects": [{"op": "set_flag", "key": "alarm", "value": True}]}],
    immediate_effects=[
        EffectSpec(id="gain_level", op="add_identity", entity="unit_7", value="level_3"),
        EffectSpec(id="gain_module", op="grant_ability", entity="unit_7", target="neural_boost",
                   data={"kind": "义体功能", "name": "神经加速"}),
        EffectSpec(id="event", op="trigger_event", target="corp_audit_event"),
    ],
    delayed_effects=[{"id": "corp_audit", "source": "neural_upgrade",
                      "description": "公司审计能源去向",
                      "trigger": {"op": "time", "key": "markers", "value": 1, "comparator": ">="},
                      "effects": [{"op": "set_flag", "key": "audited", "value": True}]}],
    visibility="hidden",
)


def test_action_model_is_generic_and_catalog_rejects_duplicates() -> None:
    assert set(Action.model_fields) == {"id", "kind", "name", "actor", "target", "type",
                                        "requirements", "costs", "risks", "immediate_effects",
                                        "delayed_effects", "visibility", "data"}
    assert set(BREAKTHROUGH.model_dump()) == set(NEURAL_UPGRADE.model_dump())
    assert type(BREAKTHROUGH.requirements[0]) is type(NEURAL_UPGRADE.requirements[0])
    assert ActionCatalog(actions=[BREAKTHROUGH, NEURAL_UPGRADE]).by_id("neural_upgrade").name == "神经升级"
    with pytest.raises(ValidationError):
        ActionCatalog(actions=[BREAKTHROUGH, BREAKTHROUGH])
    with pytest.raises(ValidationError):
        Action(id="Bad-Action", name="编号必须是小写标识")
    with pytest.raises(ValidationError):
        Action(id="extra_field_action", unknown=True)


def test_conditions_give_clear_reasons_for_every_supported_kind() -> None:
    state = xianxia_state()
    state.timeline.markers.append("day_1")
    cases = [
        (Condition(op="resource", entity="hero", key="spirit_stone", value=5, comparator=">="), True),
        (Condition(op="resource", entity="hero", key="spirit_stone", value=99, comparator=">="), False),
        (Condition(op="flag", key="sect_notice", value=False), True),
        (Condition(op="knowledge", entity="hero", target="secret_cave"), True),
        (Condition(op="knowledge", entity="master", target="secret_cave"), False),
        (Condition(op="relationship", entity="hero", target="master", key="trust", value=1, comparator=">="), True),
        (Condition(op="identity", entity="hero", value="外门弟子"), True),
        (Condition(op="identity", entity="hero", value="内门弟子"), False),
        (Condition(op="location", value="qingyun_gate"), True),
        (Condition(op="time", key="markers", value=1, comparator=">="), True),
        (Condition(op="prior_event", target="event_first_test"), True),
        (Condition(op="numeric", key="flags.sect_notice", value=False), True),
        (Condition(op="all", conditions=[Condition(op="flag", key="sect_notice", value=False),
                                         Condition(op="identity", entity="hero", value="外门弟子")]), True),
        (Condition(op="any", conditions=[Condition(op="identity", entity="hero", value="内门弟子"),
                                         Condition(op="identity", entity="hero", value="外门弟子")]), True),
        (Condition(op="not", conditions=[Condition(op="identity", entity="hero", value="内门弟子")]), True),
    ]
    for condition, expected in cases:
        result = evaluate(condition, state, actor="hero")
        assert result.ok is expected, (condition.op, result.message)
        if not expected:
            assert result.message
    assert resolve_path(state, "resources.spirit_stone.amount") == 5
    assert resolve_path(state, "missing.path") is None
    assert evaluate_all([Condition(op="flag", key="sect_notice", value=False)], state).ok


def test_effects_are_atomic_traceable_and_prevent_negative_stock() -> None:
    state = xianxia_state()
    ok = apply_effects(state, [EffectSpec(id="gain_stones", op="add_resource", entity="hero",
                                         target="spirit_stone", value=2)], actor="hero", source="event_gift")
    assert ok.ok and ok.state.resources["spirit_stone"].amount == 7
    assert ok.state.effect_log[-1].source == "event_gift"
    again = apply_effects(ok.state, [EffectSpec(id="gain_stones", op="add_resource", entity="hero",
                                               target="spirit_stone", value=2)], actor="hero", source="event_gift")
    assert again.state.resources["spirit_stone"].amount == 7
    broken = apply_effects(state, [EffectSpec(id="overdraw", op="remove_resource", entity="hero",
                                             target="spirit_stone", value=99)], actor="hero", source="test")
    assert not broken.ok and broken.code == "RESOURCE_NEGATIVE"
    assert broken.state.resources["spirit_stone"].amount == 5
    assert broken.records == []
    knowledge = apply_effects(state, [EffectSpec(id="share", op="add_knowledge", entity="master",
                                                target="secret_cave")], actor="master", source="test")
    holders = {item.id: item.holders for item in knowledge.state.knowledge}
    assert sorted(holders["secret_cave"]) == ["hero", "master"]
    events = apply_effects(state, [EffectSpec(id="fire", op="trigger_event", target="event_second")],
                           actor="hero", source="test")
    assert [item.id for item in events.state.active_events] == ["event_second"]
    resolved = apply_effects(events.state, [EffectSpec(id="close", op="resolve_event", target="event_second")],
                             actor="hero", source="test")
    assert resolved.state.active_events == []
    assert [item.id for item in resolved.state.resolved_events][-1] == "event_second"
    assert EffectRecord.model_fields.keys() >= {"id", "op", "target", "value", "source", "order"}


def test_same_resolver_runs_xianxia_breakthrough_and_scifi_upgrade() -> None:
    resolver = ActionResolver()
    xianxia = resolver.resolve(BREAKTHROUGH, xianxia_state(), rolls=[0.9])
    scifi = resolver.resolve(NEURAL_UPGRADE, scifi_state(), rolls=[0.9])
    for result, actor, resource_id, expected_amount, identity, ability in (
            (xianxia, "hero", "spirit_stone", 2, "内门弟子", "qi_art"),
            (scifi, "unit_7", "energy", 20, "level_3", "neural_boost")):
        assert result.ok and result.outcome == "success"
        assert result.state.resources[resource_id].amount == expected_amount
        assert identity in result.state.identities[actor]
        assert ability in result.state.abilities
        assert result.triggered_events
        assert result.delayed_effect_ids
        assert result.state.delayed_effects[0]["source_action"] == result.action_id
        assert all(record.source for record in result.records)
        assert StoryState.model_validate_json(result.state.model_dump_json()) == result.state
    assert xianxia.state.flags["sect_notice"] is True
    assert scifi.state.flags["alarm"] is False


def test_resolver_blocks_and_rolls_back_when_requirements_or_costs_fail() -> None:
    resolver = ActionResolver()
    poor = xianxia_state()
    poor.resources["spirit_stone"] = poor.resources["spirit_stone"].model_copy(update={"amount": 1})
    blocked = resolver.resolve(BREAKTHROUGH, poor)
    assert blocked.outcome == "blocked" and blocked.code == "RESOURCE_NOT_ENOUGH"
    assert "spirit_stone" in blocked.message
    assert blocked.state.resources["spirit_stone"].amount == 1
    outsider = xianxia_state()
    outsider.identities = {}
    blocked = resolver.resolve(BREAKTHROUGH, outsider)
    assert blocked.outcome == "blocked" and "身份" in blocked.message
    assert outsider.abilities == {}


def test_resolver_reports_partial_when_risk_triggers() -> None:
    resolver = ActionResolver()
    partial = resolver.resolve(BREAKTHROUGH, xianxia_state(), rolls=[0.1])
    assert partial.outcome == "partial" and partial.risk_ids == ["backlash"]
    trust = next(item for item in partial.state.relationships
                 if item.source_id == "hero" and item.target_id == "master")
    assert trust.dimensions["trust"] == 0
    clean = resolver.resolve(BREAKTHROUGH, xianxia_state(), rolls=[0.9])
    assert clean.outcome == "success" and clean.risk_ids == []


def test_action_layer_has_no_genre_branching() -> None:
    source = "".join(
        (ROOT / "src" / "novelforge" / "story_engine" / name).read_text(encoding="utf-8")
        for name in ("actions.py", "conditions.py", "effects.py", "resolver.py")
    )
    for pattern in ("if genre ==", "if world_type ==", "if template_id ==", "if novel_id ==",
                    "if action_id ==", "story_builder"):
        assert pattern not in source, pattern
