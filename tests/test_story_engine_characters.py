"""T09：角色决策上下文、反应规则与 LLM 提议边界。"""

from __future__ import annotations

from novelforge.story_engine import (
    Action,
    Condition,
    KnowledgeEntry,
    RelationshipState,
    StoryState,
    build_decision_context,
    merge_suggestions,
    sanitize_llm_proposals,
    suggest_reactions,
)
from novelforge.story_engine.effects import EffectSpec


ACTIONS = [
    Action(id="guard_others", kind="protect", name="先确保同伴安全", type="protect",
           requirements=[], data={"tags": ["companion"], "serves": "保住同伴"}),
    Action(id="press_forward", kind="push", name="继续追查线索", type="investigate",
           requirements=[Condition(op="knowledge", target="ledger")],
           data={"serves": "查明真相"}),
    Action(id="break_promise", kind="betray", name="抛下约定先走", type="withdraw",
           data={"violates": "背弃承诺", "tags": ["oppose"]}),
]


def state_with(character_id: str, data: dict, *, trust: float = 0.0, knowledge: bool = True):
    return StoryState(
        characters={character_id: {"id": character_id, "kind": "character", "name": character_id,
                                   "data": data}},
        relationships=[RelationshipState(source_id=character_id, target_id="partner",
                                         dimensions={"trust": trust})],
        knowledge=[KnowledgeEntry(id="ledger", holders=[character_id] if knowledge else [])],
    )


def test_same_event_gives_different_reactions_for_different_characters() -> None:
    guardian = state_with("hero", {"goal": "保住同伴", "fear": "重演失去",
                                   "personality": ["protect"], "bottom_line": ["背弃承诺"]})
    seeker = state_with("seeker", {"goal": "查明真相", "desire": "查明真相",
                                   "personality": ["investigate"], "bottom_line": ["背弃承诺"]})
    guard_rows = suggest_reactions(build_decision_context(guardian, "hero"), ACTIONS, guardian,
                                   target_id="partner")
    seek_rows = suggest_reactions(build_decision_context(seeker, "seeker"), ACTIONS, seeker,
                                  target_id="partner")
    assert guard_rows[0].action_id == "guard_others"
    assert seek_rows[0].action_id == "press_forward"
    assert guard_rows[0].action_id != seek_rows[0].action_id
    # 底线对所有人都生效，但只降低优先级，不是把角色写成脚本。
    assert next(item for item in guard_rows if item.action_id == "break_promise").score < 0
    assert len(guard_rows) == len(ACTIONS)


def test_relationship_and_knowledge_change_recommendations() -> None:
    state = state_with("hero", {"goal": "保住同伴", "personality": ["protect"]}, trust=2.0)
    rows = suggest_reactions(build_decision_context(state, "hero"), ACTIONS, state, target_id="partner")
    assert next(item for item in rows if item.action_id == "guard_others").score > 0
    no_knowledge = state_with("seeker", {"goal": "查明真相"}, knowledge=False)
    rows = suggest_reactions(build_decision_context(no_knowledge, "seeker"), ACTIONS, no_knowledge)
    blocked = next(item for item in rows if item.action_id == "press_forward")
    assert blocked.score < 0 and "ledger" in blocked.reason
    assert build_decision_context(no_knowledge, "seeker").knowledge == []


def test_llm_proposals_cannot_create_facts() -> None:
    state = state_with("hero", {"goal": "保住同伴"})
    context = build_decision_context(state, "hero")
    proposals = [
        {"action_id": "guard_others", "score": 0.5, "reason": "他一向先确认同伴安全"},
        {"action_id": "invented_action", "score": 5, "reason": "凭空提出的行动"},
        {"action_id": "press_forward", "score": 5, "reason": "直接知道账册",
         "grants_knowledge": "ledger"},
    ]
    accepted = sanitize_llm_proposals(proposals, ACTIONS, state, context)
    assert [item.action_id for item in accepted] == ["guard_others"]
    merged = merge_suggestions(suggest_reactions(context, ACTIONS, state, target_id="partner"), accepted)
    assert {item.action_id for item in merged} >= {"guard_others", "press_forward"}
    assert len(merged) == len(ACTIONS)
