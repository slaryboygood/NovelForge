"""V2-B-01～B-06：长期目标、记忆、关系、弧与反应可解释性。"""

from __future__ import annotations

from novelforge.story_engine import (
    Action,
    CharacterArc,
    CharacterGoal,
    CharacterMemory,
    Condition,
    RelationshipState,
    StoryState,
    active_goals,
    apply_arc_outcome,
    build_decision_context,
    character_goals,
    character_memories,
    load_arc,
    remember,
    select_goal,
    suggest_reactions,
    suggest_reactions as rank,
    store_arc,
    update_goal_status,
    upsert_goal,
)


ACTIONS = [
    Action(id="guard_gate", name="守住闸口", type="protect", kind="protect", data={"tags": ["battle"]}),
    Action(id="seek_ledger", name="追查账册", type="investigate", kind="investigate",
           data={"tags": ["risk"]}),
]


def state() -> StoryState:
    return StoryState(characters={"hero": {"id": "hero", "kind": "character", "name": "凌"},
                                  "rival": {"id": "rival", "kind": "character", "name": "对手"}},
                      relationships=[RelationshipState(source_id="hero", target_id="rival",
                                                       dimensions={"trust": 0.0})])


def test_multiple_goals_coexist_and_priority_decides() -> None:
    current = state()
    current = upsert_goal(current, "hero", {"id": "protect_town", "scope": "long_term",
                                            "title": "守住闸口", "priority": 2, "weight": 1.0})
    current = upsert_goal(current, "hero", {"id": "find_truth", "scope": "stage",
                                            "title": "追查账册", "priority": 3, "weight": 1.0})
    current.timeline.tick = 5
    current = upsert_goal(current, "hero", {"id": "find_truth", "scope": "stage",
                                            "title": "追查账册", "priority": 3, "weight": 1.0})
    goals = character_goals(current, "hero")
    assert {item.id for item in goals} == {"protect_town", "find_truth"}
    assert next(item for item in goals if item.id == "find_truth").updated_tick == 5
    assert all(item.source == "event" for item in goals)
    assert [item.id for item in active_goals(current, "hero")][0] == "find_truth"
    assert select_goal(current, "hero").id == "find_truth"
    rows = suggest_reactions(build_decision_context(current, "hero"), ACTIONS, current)
    assert rows[0].action_id == "seek_ledger"
    assert any("服务目标" in item.reason for item in rows)


def test_goals_can_be_paused_failed_abandoned_and_reactivated() -> None:
    current = upsert_goal(state(), "hero", {"id": "save_sister", "title": "找回妹妹", "priority": 5})
    paused = update_goal_status(current, "hero", "save_sister", "paused", note="线索断了")
    assert active_goals(paused, "hero") == []
    failed = update_goal_status(paused, "hero", "save_sister", "failed")
    assert character_goals(failed, "hero")[0].status == "failed"
    abandoned = update_goal_status(failed, "hero", "save_sister", "abandoned")
    assert character_goals(abandoned, "hero")[0].status == "abandoned"
    revived = update_goal_status(abandoned, "hero", "save_sister", "active")
    assert active_goals(revived, "hero")[0].id == "save_sister"
    # 条件不满足的目标不会被选中（可以并存，但当前不生效）。
    gated = upsert_goal(revived, "hero", {"id": "cross_border", "priority": 9,
                                          "when": {"op": "flag", "key": "gate_open", "value": True}})
    assert select_goal(gated, "hero").id == "save_sister"
    gated.flags["gate_open"] = True
    assert select_goal(gated, "hero").id == "cross_border"


def test_memories_and_relationship_change_reactions_without_forced_behavior() -> None:
    current = state()
    current = remember(current, "hero", CharacterMemory(id="mem_ambush", holder="hero",
                                                        summary="上次查账时被伏击",
                                                        emotion=["risk"], tick=0))
    assert character_memories(current, "hero")[0].summary.startswith("上次查账")
    rows = {item.action_id: item for item in rank(build_decision_context(current, "hero"), ACTIONS, current)}
    assert rows["seek_ledger"].score < 0 or "记忆影响" in rows["seek_ledger"].reason
    # 记忆只是倾向：行动仍然可选，没有被禁止。
    assert len(rows) == len(ACTIONS)


def test_arc_is_stored_on_character_and_not_forced() -> None:
    current = state()
    arc = CharacterArc(character_id="hero", stages=[{"id": "guarded", "title": "戒备"},
                                                    {"id": "trusting", "title": "愿意合作"}])
    current = store_arc(current, arc)
    assert load_arc(current, "hero").current_index == 0
    advanced = apply_arc_outcome(load_arc(current, "hero"), "advance", note="共同经历危机")
    current = store_arc(current, advanced)
    assert load_arc(current, "hero").current_index == 1
    failed = apply_arc_outcome(load_arc(current, "hero"), "fail", note="合作破裂")
    assert failed.current_index == 1 and failed.outcome == "fail"  # 失败不倒退、也不强制翻转
