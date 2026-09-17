"""V2-A-03 / V2-A-04：势力状态与 NPC 自主行动。"""

from __future__ import annotations

from novelforge.story_engine import (
    AutonomousRule,
    Condition,
    ContentPack,
    EffectSpec,
    EventCard,
    StoryState,
    apply_effects,
    content_pack_from_payload,
    evaluate,
    run_world_tick,
)


def pack() -> ContentPack:
    return content_pack_from_payload({
        "pack_id": "world_demo",
        "initial_flags": {"trade_open": False},
        "actions": [
            {"id": "patrol_lockdown", "name": "巡守队封锁闸口", "kind": "world",
             "immediate_effects": [
                 {"op": "update_location", "target": "gate", "data": {"access": "封锁", "danger": 3}},
                 {"op": "update_faction", "target": "guard", "data": {"name": "巡守队",
                                                                       "stance": "封锁闸口", "influence": 2}}]},
            {"id": "merchant_open", "name": "商会重开市集", "kind": "world",
             "requirements": [{"op": "flag", "key": "trade_allowed", "value": True}],
             "immediate_effects": [
                 {"op": "update_faction", "target": "merchant", "data": {"name": "商会",
                                                                          "influence": 1}},
                 {"op": "set_flag", "key": "trade_open", "value": True},
                 {"op": "advance_time", "value": 1, "data": {"marker": "day_2"}}]},
        ],
        "events": [{"event_id": "market_event", "trigger": {"op": "flag", "key": "trade_open", "value": True},
                    "available_actions": ["merchant_open"]}],
    })


def test_faction_state_change_is_generic_and_queryable() -> None:
    state = StoryState(characters={"hero": {"id": "hero", "kind": "player"}})
    updated = apply_effects(state, [EffectSpec(id="rise", op="update_faction", target="guild",
                                               data={"name": "行会", "stance": "观望", "influence": 3})],
                            actor="hero", source="event:rise")
    assert updated.ok
    guild = updated.state.factions["guild"]
    assert guild.name == "行会" and guild.data["influence"] == 3
    assert evaluate(Condition(op="numeric", key="factions.guild.data.influence", value=3,
                              comparator=">="), updated.state).ok is True
    assert StoryState.model_validate_json(updated.state.model_dump_json()) == updated.state


def test_world_tick_acts_without_protagonist() -> None:
    state = StoryState(characters={"hero": {"id": "hero", "kind": "player"}},
                       location={"current": "gate", "known": {"gate": {"id": "gate"}}})
    rules = [AutonomousRule(actor_id="guard", action_id="patrol_lockdown", label="巡守",
                            priority=10, once=True),
             AutonomousRule(actor_id="merchant", action_id="merchant_open", label="商会",
                            priority=5)]
    first = run_world_tick(state, pack(), rules)
    assert first.acted == ["guard:patrol_lockdown"]
    assert first.state.location.known["gate"].access == "封锁"
    assert first.state.factions["guard"].data["influence"] == 2
    assert first.state.flags.get("trade_open") is not True
    # 条件未满足的规则会被跳过，并给出原因。
    assert first.skipped and first.skipped[0]["action"] == "merchant_open"
    # 主角状态没有被世界 tick 改动
    assert first.state.resources == state.resources and first.state.knowledge == state.knowledge
    allowed = first.state.model_copy(deep=True)
    allowed.flags["trade_allowed"] = True
    second = run_world_tick(allowed, pack(), rules)
    assert second.acted == ["merchant:merchant_open"]
    assert second.state.flags["trade_open"] is True
    assert second.state.timeline.tick == 1 and second.state.timeline.markers == ["day_2"]
    assert any(record.op == "world_action" for record in second.state.effect_log)
    # once 规则不会重复执行。
    assert all("patrol_lockdown" not in item for item in second.acted)


def test_world_tick_is_deterministic_and_reports_skips() -> None:
    state = StoryState()
    rules = [AutonomousRule(actor_id="ghost", action_id="missing_action")]
    result = run_world_tick(state, pack(), rules)
    assert result.acted == []
    assert result.skipped[0]["code"] == "ACTION_NOT_FOUND"
    again = run_world_tick(state, pack(), rules)
    assert again.skipped == result.skipped
