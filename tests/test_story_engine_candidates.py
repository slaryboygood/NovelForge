"""V2-C-01 / C-02 / C-06：状态决定的候选行动、事件连锁、同场景不同选择。"""

from __future__ import annotations

from novelforge.story_engine import (
    ActionCatalog,
    Condition,
    EventCardCatalog,
    KnowledgeEntry,
    ResourceStock,
    StoryState,
    available_actions,
    event_catalog_from_payload,
    filter_llm_action_proposals,
    fire_event_chain,
    generate_candidates,
    upsert_goal,
)


def catalog() -> ActionCatalog:
    return ActionCatalog(actions=[
        {"id": "open_ledger", "name": "调阅账册", "kind": "investigate",
         "requirements": [{"op": "knowledge", "target": "ledger"}],
         "data": {"tags": ["investigate"]}},
        {"id": "bribe_guard", "name": "收买守卫", "kind": "persuade",
         "requirements": [{"op": "resource", "key": "coin", "value": 3, "comparator": ">="}],
         "costs": [{"op": "remove_resource", "target": "coin", "value": 3}]},
        {"id": "force_gate", "name": "强闯闸口", "kind": "force",
         "requirements": [{"op": "identity", "value": "内门弟子"}],
         "risks": [{"id": "alarm", "description": "惊动巡守", "probability": 0.5}]},
        {"id": "wait_here", "name": "原地等待", "kind": "wait"},
    ])


def state(**kwargs) -> StoryState:
    base = dict(characters={"hero": {"id": "hero", "kind": "character", "name": "凌"}},
                resources={"coin": ResourceStock(id="coin", amount=5, holders=["hero"])})
    base.update(kwargs)
    return StoryState(**base)


def test_candidates_follow_state_not_fixed_abc() -> None:
    poor = state()
    poor.resources["coin"] = ResourceStock(id="coin", amount=1, holders=["hero"])
    rows = {item.action_id: item for item in generate_candidates(
        poor, catalog(), ["open_ledger", "bribe_guard", "force_gate", "wait_here"], actor="hero")}
    assert rows["open_ledger"].available is False and "ledger" in rows["open_ledger"].reason
    assert rows["bribe_guard"].available is False
    assert rows["bribe_guard"].code in ("RESOURCE_NEGATIVE", "RESOURCE_NOT_ENOUGH")
    assert rows["force_gate"].available is False and "身份" in rows["force_gate"].reason
    assert rows["wait_here"].available is True
    assert available_actions(list(rows.values())) == ["wait_here"]

    rich = state(knowledge=[KnowledgeEntry(id="ledger", holders=["hero"])])
    rich.identities = {"hero": ["内门弟子"]}
    rich_rows = {item.action_id: item for item in generate_candidates(
        rich, catalog(), ["open_ledger", "bribe_guard", "force_gate", "wait_here"], actor="hero")}
    assert set(available_actions(list(rich_rows.values()))) == {
        "open_ledger", "bribe_guard", "force_gate", "wait_here"}
    assert rich_rows["force_gate"].risks == ["惊动巡守"]
    assert rich_rows["bribe_guard"].costs[0]["op"] == "remove_resource"


def test_candidates_report_goal_and_memory_influence_and_filter_llm() -> None:
    stateful = state(knowledge=[KnowledgeEntry(id="ledger", holders=["hero"])])
    stateful = upsert_goal(stateful, "hero", {"id": "audit", "title": "调阅账册", "priority": 4})
    rows = generate_candidates(stateful, catalog(), ["open_ledger", "wait_here"], actor="hero")
    ledger = next(item for item in rows if item.action_id == "open_ledger")
    assert ledger.available and any("调阅账册" in note for note in ledger.goal_notes)
    assert rows[0].action_id == "open_ledger"  # 与目标一致的行动排在前面
    assert filter_llm_action_proposals(["open_ledger", "invented", "bribe_guard"], rows) == ["open_ledger"]


def test_unavailable_reason_is_machine_readable() -> None:
    rows = generate_candidates(state(), catalog(), ["open_ledger", "force_gate"], actor="hero")
    assert all(item.available is False for item in rows)
    assert {item.code for item in rows} == {"KNOWLEDGE_MISSING", "IDENTITY_MISSING"}
    assert all(item.reason for item in rows)


def test_event_chain_fires_followups_with_limits() -> None:
    cards = event_catalog_from_payload({
        "catalog_id": "chain",
        "cards": [
            {"event_id": "rumor", "priority": 3, "trigger": {"op": "flag", "key": "start", "value": True},
             "followups": ["inquiry"], "consequences": [{"op": "set_flag", "key": "rumor_heard", "value": True}]},
            {"event_id": "inquiry", "priority": 2, "trigger": {"op": "flag", "key": "rumor_heard", "value": True},
             "consequences": [{"op": "update_faction", "target": "guard",
                               "data": {"name": "巡守队", "influence": 3}}]},
        ],
    })
    stateful = state()
    stateful.flags["start"] = True
    result = fire_event_chain(stateful, cards, "rumor", actor="hero")
    assert result.fired == ["rumor", "inquiry"]
    assert result.state.flags["rumor_heard"] is True
    assert result.state.factions["guard"].data["influence"] == 3
    again = fire_event_chain(stateful, cards, "rumor", actor="hero", max_depth=0)
    assert again.fired == ["rumor"]  # 深度受限，不会无限连锁
