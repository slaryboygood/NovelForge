from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from novelforge.story_engine import (
    ActionResolver,
    Action,
    Condition,
    DelayedEffectSpec,
    EventCard,
    EventCardCatalog,
    EventTriggerEngine,
    ResourceStock,
    StoryState,
    cancel_delayed,
    event_catalog_from_payload,
    replace_delayed,
    settle_delayed,
)
from novelforge.story_engine.effects import EffectSpec


ROOT = Path(__file__).resolve().parents[1]


def catalog_payload() -> dict:
    return {
        "catalog_id": "test_events",
        "cards": [
            {"event_id": "sect_inquiry", "title": "宗门调查", "priority": 5,
             "trigger": {"op": "flag", "key": "sect_notice", "value": True},
             "participants": ["hero", "master"], "scene_goal": "查清材料来源",
             "conflict": "主角不能说出真实来源",
             "available_actions": ["explain", "hide"], "followups": ["inner_discipline"],
             "consequences": [{"op": "change_relationship", "entity": "master",
                               "target": "hero", "key": "trust", "value": -1}]},
            {"event_id": "market_offer", "title": "黑市开价", "priority": 3, "cooldown": 2, "once_only": False,
             "trigger": {"op": "resource", "entity": "hero", "key": "spirit_stone",
                         "value": 2, "comparator": ">="},
             "participants": ["hero"], "scene_goal": "决定是否交易",
             "conflict": "价格与风险不对等",
             "available_actions": ["trade", "refuse"]},
            {"event_id": "hidden_truth", "title": "真相浮现", "priority": 9,
             "trigger": {"op": "all", "conditions": [
                 {"op": "knowledge", "entity": "hero", "target": "ledger"},
                 {"op": "prior_event", "target": "sect_inquiry"}]},
             "scene_goal": "面对已经核实的证据", "conflict": "公开会伤害盟友"},
        ],
    }


def state_with_stones(amount: float = 5, **kwargs) -> StoryState:
    return StoryState(
        characters={"hero": {"id": "hero", "kind": "disciple", "name": "凌"},
                    "master": {"id": "master", "kind": "elder", "name": "师"}},
        resources={"spirit_stone": ResourceStock(id="spirit_stone", amount=amount, unit="枚",
                                                 holders=["hero"])},
        **kwargs,
    )


def test_event_card_model_and_pure_config_catalog() -> None:
    assert set(EventCard.model_fields) >= {"event_id", "title", "trigger", "participants", "scene_goal",
                                           "conflict", "available_actions", "consequences", "followups",
                                           "priority", "cooldown", "once_only"}
    catalog = event_catalog_from_payload(catalog_payload())
    assert [item.event_id for item in catalog.cards] == ["sect_inquiry", "market_offer", "hidden_truth"]
    # 纯配置新增事件：不改动引擎代码即可出现在目录里。
    payload = catalog_payload()
    payload["cards"].append({"event_id": "extra_rumor", "title": "流言",
                             "trigger": {"op": "flag", "key": "rumor", "value": True}})
    assert event_catalog_from_payload(payload).by_id("extra_rumor").title == "流言"
    with pytest.raises(ValidationError):
        EventCardCatalog(cards=[catalog.cards[0], catalog.cards[0]])
    with pytest.raises(ValidationError):
        EventCard(event_id="bad", trigger={"op": "all", "conditions": []})


def test_trigger_pool_changes_with_state_and_respects_once_only() -> None:
    engine = EventTriggerEngine(event_catalog_from_payload(catalog_payload()))
    quiet = state_with_stones()
    assert [item.event_id for item in engine.available(quiet, actor="hero")] == ["market_offer"]
    noticed = state_with_stones(flags={"sect_notice": True})
    assert [item.event_id for item in engine.available(noticed, actor="hero")] == ["sect_inquiry", "market_offer"]
    rows = {item.event_id: item for item in engine.availability(noticed, actor="hero")}
    assert rows["hidden_truth"].code == "KNOWLEDGE_MISSING"
    assert "ledger" in rows["hidden_truth"].reason

    fired = engine.fire(noticed, "sect_inquiry", actor="hero")
    assert fired.ok and fired.activated_followups == ["inner_discipline"]
    again = engine.availability(fired.state, actor="hero")
    assert {item.event_id for item in again if item.available} == {"market_offer"}
    assert next(item for item in again if item.event_id == "sect_inquiry").code == "EVENT_ALREADY_FIRED"
    assert engine.fire(fired.state, "sect_inquiry").ok is False


def test_trigger_respects_cooldown_progress() -> None:
    engine = EventTriggerEngine(event_catalog_from_payload(catalog_payload()))
    state = state_with_stones()
    first = engine.fire(state, "market_offer", actor="hero")
    assert first.ok
    blocked = {item.event_id: item for item in engine.availability(first.state, actor="hero")}
    assert blocked["market_offer"].code == "EVENT_COOLDOWN"
    # 推进两次记录后冷却结束，可以再次触发。
    progressed = first.state.model_copy(deep=True)
    from novelforge.story_engine.entities import EffectRecord
    for _ in range(2):
        progressed.effect_log.append(EffectRecord(id=f"tick_{len(progressed.effect_log) + 1}", op="tick",
                                                  order=len(progressed.effect_log) + 1))
    assert "market_offer" in [item.event_id for item in engine.available(progressed, actor="hero")]


def test_delayed_consequence_survives_round_trip_and_can_be_managed() -> None:
    action = Action(
        id="take_loan",
        actor="hero",
        requirements=[],
        immediate_effects=[EffectSpec(id="gain", op="add_resource", entity="hero",
                                      target="spirit_stone", value=3),
                           EffectSpec(id="mark", op="set_flag", key="loan_open", value=True)],
        delayed_effects=[DelayedEffectSpec(
            id="debt_due", source="take_loan", description="债主上门",
            trigger=Condition(op="time", key="markers", value=1, comparator=">="),
            effects=[EffectSpec(id="penalty", op="change_relationship", entity="hero",
                                target="master", key="trust", value=-1)])],
    )
    result = ActionResolver().resolve(action, state_with_stones())
    assert result.ok and result.delayed_effect_ids == ["debt_due"]
    reloaded = StoryState.model_validate_json(result.state.model_dump_json())
    assert reloaded.delayed_effects[0]["source_action"] == "take_loan"
    assert reloaded.delayed_effects[0]["trigger"]["op"] == "time"

    not_ready = settle_delayed(reloaded, actor="hero")
    assert not_ready.settled == [] and not_ready.pending == ["debt_due"]
    assert len(not_ready.state.delayed_effects) == 1

    ready = reloaded.model_copy(deep=True)
    ready.timeline.markers.append("day_2")
    settled = settle_delayed(ready, actor="hero")
    assert settled.settled == ["debt_due"] and settled.state.delayed_effects == []
    assert settled.state.effect_log[-1].op == "settle_delayed"

    forced = settle_delayed(reloaded, actor="hero", force=True)
    assert forced.settled == ["debt_due"]
    cancelled = cancel_delayed(reloaded, "debt_due")
    assert cancelled.ok and cancelled.state.delayed_effects == []
    replaced = replace_delayed(reloaded, "debt_due", DelayedEffectSpec(
        id="debt_due", source="renegotiated",
        trigger=Condition(op="flag", key="loan_open", value=False),
        effects=[EffectSpec(id="penalty", op="set_flag", key="debt_clear", value=True)]))
    assert replaced.ok and replaced.state.delayed_effects[0]["source"] == "renegotiated"
    assert cancel_delayed(reloaded, "missing_debt").ok is False


def test_event_layer_has_no_prose_or_genre_branching() -> None:
    source = "".join((ROOT / "src" / "novelforge" / "story_engine" / name).read_text(encoding="utf-8")
                     for name in ("events.py", "delayed.py"))
    for pattern in ("if genre ==", "if world_type ==", "if template_id ==",
                    "if event_id ==", "story_builder"):
        assert pattern not in source, pattern
