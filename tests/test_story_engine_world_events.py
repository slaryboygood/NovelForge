"""V2-A-05 / A-06：世界事件层与知识分层。"""

from __future__ import annotations

from pathlib import Path

from novelforge.story_engine import (
    EventCardCatalog,
    KnowledgeEntry,
    ResourceStock,
    StoryState,
    claim_world_knowledge,
    event_catalog_from_payload,
    run_world_events,
)


ROOT = Path(__file__).resolve().parents[1]


def catalog() -> EventCardCatalog:
    return event_catalog_from_payload({
        "catalog_id": "world_events",
        "cards": [
            {"event_id": "guard_reinforce", "title": "巡守队增援", "scope": "world", "priority": 5,
             "trigger": {"op": "time", "key": "tick", "value": 3, "comparator": ">="},
             "knowledge_id": "guard_reinforcement", "reader_visible": True,
             "consequences": [
                 {"op": "update_location", "target": "gate", "data": {"access": "封锁", "danger": 3}},
                 {"op": "update_faction", "target": "guard", "data": {"name": "巡守队", "influence": 4}},
                 {"op": "set_flag", "key": "gate_locked", "value": True}]},
            {"event_id": "scene_only", "title": "场景事件", "scope": "scene",
             "trigger": {"op": "flag", "key": "gate_locked", "value": True}},
        ],
    })


def test_world_event_fires_without_protagonist_and_keeps_knowledge_unclaimed() -> None:
    state = StoryState(characters={"hero": {"id": "hero", "kind": "player"}},
                       resources={"energy": ResourceStock(id="energy", amount=2, holders=["hero"])},
                       location={"current": "gate", "known": {"gate": {"id": "gate"}}})
    early = run_world_events(state, catalog())
    assert early.fired == [] and early.skipped and early.skipped[0]["code"] == "TIME_NOT_REACHED"
    state.timeline.tick = 5
    result = run_world_events(state, catalog(), actor="world")
    assert result.fired == ["guard_reinforce"]
    assert result.state.location.known["gate"].access == "封锁"
    assert result.state.factions["guard"].data["influence"] == 4
    assert result.state.flags["gate_locked"] is True
    assert any(record.op == "world_event" for record in result.state.effect_log)
    # 知识分层：世界事件发生 ≠ 主角知道。
    entry = next(item for item in result.state.knowledge if item.id == "guard_reinforcement")
    assert entry.holders == [] and entry.reader_visible is True
    assert "guard_reinforcement" in result.unclaimed_knowledge
    assert result.state.resources["energy"].amount == 2  # 主角资源不被世界事件改动
    assert all(item.holders == ["hero"] for item in state.knowledge) or state.knowledge == []


def test_protagonist_learns_only_through_a_legal_source() -> None:
    state = StoryState(characters={"hero": {"id": "hero", "kind": "player"}})
    state.timeline.tick = 5
    fired = run_world_events(state, catalog())
    assert fired.state.knowledge[0].holders == []
    learned, changed = claim_world_knowledge(fired.state, "guard_reinforcement", "hero")
    assert changed is True and learned.knowledge[0].holders == ["hero"]
    again, changed_again = claim_world_knowledge(learned, "guard_reinforcement", "hero")
    assert changed_again is False and again == learned
    missing, missing_changed = claim_world_knowledge(fired.state, "unknown_fact", "hero")
    assert missing_changed is False and missing == fired.state
    assert StoryState.model_validate_json(learned.model_dump_json()) == learned


def test_world_event_affects_later_candidate_pool() -> None:
    from novelforge.story_engine import EventTriggerEngine

    state = StoryState(characters={"hero": {"id": "hero", "kind": "player"}})
    state.timeline.tick = 5
    catalog_data = catalog()
    before = {item.event_id for item in EventTriggerEngine(catalog_data).available(state, actor="hero")}
    result = run_world_events(state, catalog_data)
    after = {item.event_id for item in EventTriggerEngine(catalog_data).available(result.state, actor="hero")}
    assert before == {"guard_reinforce"}  # 世界事件本身也是合法事件，只是 scope 不同
    assert "scene_only" in after
    assert "guard_reinforce" not in after  # once_only 已经发生过
    assert result.state.timeline.tick == 5  # 世界事件不偷跑时间


def test_world_event_layer_has_no_genre_branching() -> None:
    source = "".join((ROOT / "src" / "novelforge" / "story_engine" / name).read_text(encoding="utf-8")
                     for name in ("world.py", "events.py"))
    for pattern in ("if genre ==", "if world_type ==", "if novel_id ==", "修仙", "科幻"):
        assert pattern not in source, pattern
