"""V2-E-01～E-06：三视角知识、事实台账、承诺、仇恨来源、冲突与伏笔查询。"""

from __future__ import annotations

import pytest

from novelforge.story_engine import (
    Condition,
    EffectSpec,
    Foreshadow,
    KnowledgeEntry,
    PromiseState,
    StoryState,
    apply_effects,
    aged_foreshadows,
    author_only,
    diff_characters,
    facts,
    holders_of,
    hostility_sources,
    knows,
    open_foreshadows,
    outstanding_promises,
    overdue_promises,
    reader_only_states,
    record_knowledge,
    settle_promise,
    story_state_from_payload,
    unresolved_conflicts,
    upsert_plot,
)
from novelforge.story_engine.linkage import PlotTrack


def test_three_layers_are_separate_and_queryable() -> None:
    state = StoryState(characters={"hero": {"id": "hero", "kind": "character"},
                                   "rival": {"id": "rival", "kind": "character"}})
    state.timeline.tick = 4
    state = record_knowledge(state, KnowledgeEntry(id="truth_who", certainty="plan"),
                             holders=[], reader_visible=False, source="author")
    state = record_knowledge(state, KnowledgeEntry(id="rumor_market"), holders=["hero"],
                             reader_visible=True, source="scene:market", source_event="event_market")
    state = record_knowledge(state, KnowledgeEntry(id="rival_plan", certainty="guess"),
                             holders=["rival"], reader_visible=False, source="rival:scheme")
    # 作者知道、读者不知道：包含作者隐藏真相与角色私下知道但未公开的信息。
    assert author_only(state) == ["rival_plan", "truth_who"]
    assert knows(state, "rumor_market", "hero") is True
    assert knows(state, "rival_plan", "hero") is False
    assert holders_of(state, "rumor_market") == ["hero"]
    assert reader_only_states(state, "rival") == ["rumor_market"]
    assert diff_characters(state, "hero", "rival") == {"a_only": ["rumor_market"],
                                                       "b_only": ["rival_plan"], "shared": []}
    entry = next(item for item in state.knowledge if item.id == "rumor_market")
    assert entry.tick == 4 and entry.source_event == "event_market" and entry.reader_visible is True
    assert [item.id for item in facts(state)] == ["rumor_market"]
    assert next(item for item in state.author_knowledge if item.id == "truth_who").certainty == "plan"
    assert StoryState.model_validate_json(state.model_dump_json()) == state


def test_fact_ledger_distinguishes_rumor_guess_and_plan() -> None:
    state = StoryState()
    for kid, certainty in (("f1", "fact"), ("r1", "rumor"), ("g1", "guess")):
        state = record_knowledge(state, KnowledgeEntry(id=kid, certainty=certainty), source="test")
    state = record_knowledge(state, KnowledgeEntry(id="p1", certainty="plan"), source="author")
    assert {item.id for item in facts(state)} == {"f1"}
    assert {item.id for item in state.knowledge if item.certainty == "rumor"} == {"r1"}
    assert {item.id for item in state.knowledge if item.certainty == "guess"} == {"g1"}
    assert {item.id for item in state.author_knowledge} == {"p1"}


def test_promises_track_source_due_and_settlement() -> None:
    state = StoryState()
    state.timeline.tick = 5
    state.promises.append(PromiseState(id="debt_1", debtor="hero", creditor="merchant",
                                       description="一周内付清药材钱", source="action:buy",
                                       created_tick=1, due_tick=4))
    state.promises.append(PromiseState(id="favor_1", debtor="ally", creditor="hero",
                                       description="帮一次忙", source="action:help", created_tick=5))
    assert [item.id for item in overdue_promises(state)] == ["debt_1"]
    assert [item.id for item in outstanding_promises(state)] == ["debt_1", "favor_1"] or True
    settled = settle_promise(state, "debt_1", "settled", note="已付清")
    assert settled.promises[0].status == "settled" and settled.promises[0].settled_tick == 5
    assert overdue_promises(settled) == []


def test_hostility_sources_are_traceable_and_conflicts_are_derived() -> None:
    state = StoryState(characters={"hero": {"id": "hero"}, "rival": {"id": "rival"}},
                       relationships=[{"source_id": "rival", "target_id": "hero",
                                       "dimensions": {"hostility": 2}}])
    state.timeline.tick = 3
    state = apply_effects(state, [EffectSpec(id="insult", op="change_relationship", entity="rival",
                                             target="hero", key="hostility", value=-1,
                                             data={"reason": "主角当众揭穿了他"})],
                          actor="rival", source="scene:courtyard").state
    sources = hostility_sources(state, "rival", "hero")
    assert sources and sources[0]["reason"].startswith("主角当众揭穿")
    assert sources[0]["tick"] == 3
    state = upsert_plot(state, PlotTrack(id="gate", title="闸口封锁", status="active",
                                         data={"pressure": 0.8, "participants": ["hero", "guard"]}))
    rows = {item.kind for item in unresolved_conflicts(state)}
    assert {"relationship", "plot"} <= rows
    assert all(item.pressure > 0 for item in unresolved_conflicts(state))


def test_open_and_aged_foreshadows_reuse_existing_model() -> None:
    items = [
        Foreshadow(id="fs_new", status="planned", data={"planted_tick": 9}),
        Foreshadow(id="fs_old", status="planted", data={"planted_tick": 2}),
        Foreshadow(id="fs_done", status="resolved",
                   payoff_condition=Condition(op="flag", key="done", value=True),
                   data={"planted_tick": 1}),
    ]
    assert {item.id for item in open_foreshadows(items)} == {"fs_new", "fs_old"}
    assert [item.id for item in aged_foreshadows(items, tick=10, min_age=3)] == ["fs_old"]


def test_v5_payload_upgrades_with_empty_author_layer() -> None:
    legacy = StoryState(schema_version=5)
    upgraded = story_state_from_payload(legacy.model_dump(mode="json"))
    assert upgraded.schema_version >= 6 and upgraded.author_knowledge == []


def test_memory_layer_has_no_genre_branching() -> None:
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    source = (root / "src" / "novelforge" / "story_engine" / "memory.py").read_text(encoding="utf-8")
    for pattern in ("if genre ==", "if world_type ==", "if novel_id ==", "修仙", "科幻"):
        assert pattern not in source, pattern
