"""V2-A-01：题材无关的世界时钟。"""

from __future__ import annotations

from pathlib import Path

from novelforge.story_engine import (
    Condition,
    EffectSpec,
    StoryState,
    StoryStateRepository,
    TimelineState,
    apply_effects,
    evaluate,
    story_state_from_payload,
)


ROOT = Path(__file__).resolve().parents[1]


def test_advance_time_moves_clock_and_keeps_markers() -> None:
    state = StoryState(characters={"hero": {"id": "hero", "kind": "player"}})
    assert state.timeline.tick == 0
    moved = apply_effects(state, [EffectSpec(id="one_day", op="advance_time", value=1,
                                            key="day_1", data={"marker": "day_1"})],
                          actor="hero", source="event:start")
    assert moved.ok and moved.state.timeline.tick == 1
    assert moved.state.timeline.markers == ["day_1"]
    again = apply_effects(moved.state, [EffectSpec(id="three_days", op="advance_time", value=3,
                                                  data={"marker": "day_4", "current_time": "第四日"})],
                          actor="hero", source="event:travel")
    assert again.state.timeline.tick == 4
    assert again.state.timeline.markers == ["day_1", "day_4"]
    assert again.state.timeline.current_time == "第四日"
    backwards = apply_effects(again.state, [EffectSpec(id="rewind", op="advance_time", value=-1)],
                              actor="hero", source="test")
    assert not backwards.ok and backwards.code == "TIME_BACKWARDS"
    assert backwards.state.timeline.tick == 4


def test_time_conditions_read_tick_and_markers() -> None:
    state = StoryState()
    state.timeline.tick = 5
    state.timeline.markers.extend(["day_1", "day_5"])
    assert evaluate(Condition(op="time", key="tick", value=5, comparator=">="), state).ok is True
    assert evaluate(Condition(op="time", key="tick", value=6, comparator=">="), state).ok is False
    assert evaluate(Condition(op="time", key="markers", value=2, comparator=">="), state).ok is True
    assert evaluate(Condition(op="time", key="current_time", value="第四日"), state).ok is False


def test_world_clock_survives_save_and_reload(tmp_path: Path) -> None:
    repository = StoryStateRepository(tmp_path)
    state = StoryState()
    moved = apply_effects(state, [EffectSpec(id="elapsed", op="advance_time", value=7,
                                             data={"marker": "week_1"})],
                          actor="hero", source="world:tick")
    repository.save(moved.state, "bp_clock", 1)
    loaded = repository.load("bp_clock", 1)
    assert loaded.timeline.tick == 7 and loaded.timeline.markers == ["week_1"]
    assert StoryState.model_validate_json(loaded.model_dump_json()) == loaded


def test_v1_payload_without_tick_still_loads() -> None:
    legacy = StoryState(schema_version=3, timeline=TimelineState(current_time="第一日"))
    upgraded = story_state_from_payload(legacy.model_dump(mode="json"))
    assert upgraded.timeline.tick == 0 and upgraded.timeline.current_time == "第一日"
    assert upgraded.schema_version >= 4


def test_time_layer_has_no_genre_branching() -> None:
    source = "".join((ROOT / "src" / "novelforge" / "story_engine" / name).read_text(encoding="utf-8")
                     for name in ("state.py", "effects.py", "conditions.py"))
    for pattern in ("if genre ==", "if world_type ==", "if novel_id ==", "修仙", "科幻"):
        assert pattern not in source, pattern
