"""T11：伏笔生命周期、回收条件与悬念信息层级。"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from novelforge.story_engine import (
    Condition,
    Foreshadow,
    ForeshadowTransitionError,
    KnowledgeEntry,
    ReaderQuestion,
    ResourceStock,
    StoryState,
    payoff_ready,
    reader_knows,
    reveal_to_character,
    reveal_to_reader,
    transform,
    transition,
)


def state(**kwargs) -> StoryState:
    return StoryState(characters={"hero": {"id": "hero", "kind": "player"}},
                      resources={"energy": ResourceStock(id="energy", amount=2)}, **kwargs)


def test_lifecycle_only_allows_valid_transitions() -> None:
    item = Foreshadow(id="old_ledger", title="旧账册")
    assert item.status == "planned"
    item = transition(item, "planted")
    assert item.status == "planted"
    with pytest.raises(ForeshadowTransitionError):
        transition(item, "resolved")
    item = transition(transition(item, "reinforced"), "revealed",
                      note="需要条件") if False else item
    with pytest.raises(ValidationError):
        Foreshadow(id="needs_condition", status="revealed")
    item = Foreshadow(id="old_ledger", status="revealed",
                      payoff_condition=Condition(op="knowledge", target="ledger"))
    assert transition(item, "resolved").status == "resolved"
    with pytest.raises(ForeshadowTransitionError):
        transition(transition(item, "resolved"), "planted")


def test_payoff_is_conditional_and_player_choice_can_change_it() -> None:
    item = Foreshadow(id="witness", status="planted",
                      payoff_condition=Condition(op="knowledge", target="receipt"),
                      payoff_options={"public": Condition(op="resource", key="energy", value=1,
                                                          comparator=">=")})
    quiet = state()
    ok, reason = payoff_ready(item, quiet, actor="hero")
    assert ok is False and "receipt" in reason
    with_receipt = state(knowledge=[KnowledgeEntry(id="receipt", holders=["hero"])])
    assert payoff_ready(item, with_receipt, actor="hero")[0] is True
    # 玩家选择改变回收方式：public 走另一套条件。
    assert payoff_ready(item, quiet, actor="hero", choice="public")[0] is True
    poor = state()
    poor.resources["energy"] = ResourceStock(id="energy", amount=0)
    assert payoff_ready(item, poor, actor="hero", choice="public")[0] is False
    abandoned = transform(item, new_id="witness_echo")
    assert abandoned.status == "abandoned" and abandoned.transformed_into == "witness_echo"


def test_reader_and_character_knowledge_are_separate() -> None:
    question = ReaderQuestion(id="who_moved", question="是谁改动了记录？", answer="负责人")
    assert reader_knows(question, "hero") is False
    revealed = reveal_to_reader(question)
    assert revealed.reader_knows is True
    assert reader_knows(revealed, "hero") is False
    shared = reveal_to_character(revealed, "hero")
    assert reader_knows(shared, "hero") is True
    assert reader_knows(shared, "other") is False
