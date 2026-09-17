"""C02：StoryState → Canon 同步（幂等、稳定 source mapping、effect_log 增长不改变 identity）。"""

from __future__ import annotations

from novelforge.story_engine.canon.repository import CanonRepository
from novelforge.story_engine.canon.service import CanonService
from novelforge.story_engine.canon.sync import StoryStateCanonSync, source_stable_key


def _state() -> dict:
    return {
        "schema_version": 1, "novel_id": "n1",
        "characters": {"protagonist": {"name": "拾荒者"}, "npc_1": {"name": "伙伴"}},
        "factions": {"faction_1": {"name": "聚落"}},
        "relationships": [{"source_id": "protagonist", "target_id": "npc_1",
                           "dimensions": {"trust": 3}}],
        "knowledge": [{"id": "clue_a", "holders": ["protagonist"], "tick": 3,
                       "source": "action:probe", "source_event": ""}],
        "flags": {"foreshadows": {"fs_tag": {"status": "planted", "reason": "旧物"}}},
        "effect_log": [
            {"op": "advance_time", "entity": "protagonist", "target": "timeline", "value": 1,
             "source": "cost:probe", "data": {"tick": 1}},
            {"op": "add_knowledge", "entity": "protagonist", "target": "clue_a", "value": None,
             "source": "action:probe", "data": {"tick": 1}},
            {"op": "fire_event", "entity": "world", "target": "ev_tide", "value": None,
             "source": "event:ev_tide", "data": {"tick": 2}},
            {"op": "world_event", "entity": "world", "target": "ev_tide", "value": None,
             "source": "world_event:ev_tide", "data": {"tick": 2}},
        ],
    }


def test_sync_is_idempotent_and_stable(tmp_path) -> None:
    repo = CanonRepository(tmp_path / "canon.sqlite")
    sync = StoryStateCanonSync(repo)
    state = _state()
    first = sync.sync("n1", state)
    facts_after_first = sorted(f.fact_id for f in repo.facts("n1"))
    second = sync.sync("n1", state)
    facts_after_second = sorted(f.fact_id for f in repo.facts("n1"))
    assert first["facts"] > 0 and second["facts"] == 0
    assert facts_after_first == facts_after_second
    # fire_event 与 world_event 是同一事件：只产生一条事实
    assert len([f for f in repo.facts("n1") if "ev_tide" in f.canonical_description]) == 1
    repo.close()


def test_effect_log_growth_does_not_change_existing_ids(tmp_path) -> None:
    repo = CanonRepository(tmp_path / "canon.sqlite")
    sync = StoryStateCanonSync(repo)
    state = _state()
    sync.sync("n1", state)
    before = {f.canonical_description: f.fact_id for f in repo.facts("n1")}
    state["effect_log"].append({"op": "add_resource", "entity": "protagonist",
                                "target": "salvage", "value": 2, "source": "action:new",
                                "data": {"tick": 9}})
    sync.sync("n1", state)
    after = {f.canonical_description: f.fact_id for f in repo.facts("n1")}
    for key, fact_id in before.items():
        assert after[key] == fact_id
    # 重复同步同一条新记录也不会产生第二个 fact
    sync.sync("n1", state)
    assert len([f for f in repo.facts("n1") if "salvage" in f.canonical_description]) == 1
    repo.close()


def test_stable_key_ignores_order() -> None:
    record = {"op": "add_resource", "entity": "protagonist", "target": "salvage", "value": 2,
              "source": "action:x", "data": {"tick": 4}}
    reordered = {"data": {"tick": 4}, "source": "action:x", "value": 2, "target": "salvage",
                 "entity": "protagonist", "op": "add_resource", "order": 999}
    assert source_stable_key(record) == source_stable_key(reordered)


def test_planned_event_promotion_keeps_id(tmp_path) -> None:
    repo = CanonRepository(tmp_path / "canon.sqlite")
    service = CanonService(repo)
    event = service.new_event(novel_id="n1", name="锈牙第一次收过路费",
                              summary="掠夺队第一次向聚落收费", event_type="major")
    repo.save_event(event)
    promoted = service.promote_event(event.event_id, novel_id="n1")
    assert promoted.event_id == event.event_id
    assert promoted.status == "occurred"
    repo.close()
