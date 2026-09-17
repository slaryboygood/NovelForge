"""V2-A-02：地点状态与通行条件。"""

from __future__ import annotations

from novelforge.story_engine import (
    Condition,
    EffectSpec,
    Location,
    StoryState,
    apply_effects,
    evaluate,
)


def test_location_state_can_change_and_be_read_by_conditions() -> None:
    state = StoryState(characters={"hero": {"id": "hero", "kind": "player"}},
                       location={"current": "gate",
                                 "known": {"gate": {"id": "gate", "name": "闸口",
                                                    "access": "自由通行"}}})
    updated = apply_effects(state, [EffectSpec(id="lockdown", op="update_location", target="gate",
                                               data={"access": "需要担保", "control": "巡守队",
                                                     "danger": 2})],
                            actor="hero", source="world:lockdown")
    assert updated.ok
    gate = updated.state.location.known["gate"]
    assert gate.access == "需要担保" and gate.data["control"] == "巡守队"
    assert evaluate(Condition(op="numeric", key="location.known.gate.data.danger",
                              value=2, comparator=">="), updated.state).ok is True
    assert evaluate(Condition(op="location", value="gate"), updated.state).ok is True
    assert evaluate(Condition(op="location", value="market"), updated.state).ok is False


def test_new_location_is_registered_without_inventing_access() -> None:
    state = StoryState(characters={"hero": {"id": "hero"}})
    created = apply_effects(state, [EffectSpec(id="discover", op="update_location", target="ruins",
                                               data={"name": "旧遗址", "control": "无人"})],
                            actor="hero", source="event:discover")
    assert created.ok
    entry = created.state.location.known["ruins"]
    assert isinstance(entry, Location) and entry.name == "旧遗址"
    assert entry.access == "" and entry.data["control"] == "无人"
    visited = apply_effects(created.state, [EffectSpec(id="enter", op="change_location",
                                                       value="ruins")],
                            actor="hero", source="action:enter")
    assert visited.state.location.current == "ruins"
    assert visited.state.location.visited == ["ruins"]
    assert StoryState.model_validate_json(visited.state.model_dump_json()) == visited.state
