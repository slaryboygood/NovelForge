"""T12：通用成长树、能力/身份树与非战斗技能。"""

from __future__ import annotations

import pytest

from novelforge.story_engine import (
    SCI_FI_TREE,
    XIANXIA_TREE,
    Action,
    Condition,
    ProgressionNode,
    ProgressionTree,
    ResourceStock,
    StoryState,
    acquire,
    options,
    owned_nodes,
)
from novelforge.story_engine.effects import EffectSpec


def xianxia_state() -> StoryState:
    return StoryState(characters={"hero": {"id": "hero", "kind": "player"}},
                      resources={"spirit_stone": ResourceStock(id="spirit_stone", amount=5,
                                                               holders=["hero"])})


def scifi_state() -> StoryState:
    return StoryState(characters={"unit_7": {"id": "unit_7", "kind": "android"}},
                      resources={"energy": ResourceStock(id="energy", amount=40, holders=["unit_7"])})


def test_same_interface_expresses_two_genres() -> None:
    assert set(ProgressionNode.model_fields) == set(ProgressionNode.model_fields)
    assert type(XIANXIA_TREE.nodes[0]) is type(SCI_FI_TREE.nodes[0]) is ProgressionNode
    rows = {item.node_id: item for item in options(XIANXIA_TREE, xianxia_state(), actor="hero")}
    assert rows["qi_gathering"].available is True
    assert rows["foundation"].available is False and "qi_gathering" in rows["foundation"].reason
    scifi_rows = {item.node_id: item for item in options(SCI_FI_TREE, scifi_state(), actor="unit_7")}
    assert scifi_rows["civil_grade"].available is True
    assert scifi_rows["neural_boost"].available is False


def test_prerequisites_costs_and_effects_are_enforced() -> None:
    state = xianxia_state()
    first = acquire(XIANXIA_TREE, state, "qi_gathering", actor="hero")
    assert first.ok and "qi_gathering" in owned_nodes(first.state)
    assert "炼气弟子" in first.state.identities["hero"]
    blocked = acquire(XIANXIA_TREE, state, "foundation", actor="hero")
    assert not blocked.ok and blocked.code == "PROGRESSION_LOCKED"
    second = acquire(XIANXIA_TREE, first.state, "foundation", actor="hero")
    assert second.ok and second.state.resources["spirit_stone"].amount == 2
    assert "flying_sword" in second.state.abilities
    poor = first.state.model_copy(deep=True)
    poor.resources["spirit_stone"] = ResourceStock(id="spirit_stone", amount=1, holders=["hero"])
    failed = acquire(XIANXIA_TREE, poor, "foundation", actor="hero")
    assert not failed.ok and failed.state.resources["spirit_stone"].amount == 1


def test_exclusive_choice_and_identity_gates_action() -> None:
    tree = ProgressionTree(tree_id="identity", nodes=[
        ProgressionNode(id="inner_disciple", kind="identity", exclusive_group="rank",
                        effects=[{"op": "add_identity", "value": "内门弟子"}]),
        ProgressionNode(id="outer_disciple", kind="identity", exclusive_group="rank",
                        effects=[{"op": "add_identity", "value": "外门弟子"}]),
    ])
    state = StoryState(characters={"hero": {"id": "hero", "kind": "player"}})
    first = acquire(tree, state, "inner_disciple", actor="hero")
    assert first.ok
    rows = {item.node_id: item for item in options(tree, first.state, actor="hero")}
    assert rows["outer_disciple"].available is False
    assert rows["outer_disciple"].exclusive_blocked_by == "inner_disciple"
    gated = Action(id="enter_secret_realm", name="进入内门秘境",
                   requirements=[Condition(op="identity", entity="hero", value="内门弟子")])
    from novelforge.story_engine import evaluate
    assert evaluate(gated.requirements[0], first.state, actor="hero").ok is True
    assert evaluate(gated.requirements[0], state, actor="hero").ok is False


def test_narrative_skills_use_the_same_interface() -> None:
    tree = ProgressionTree(tree_id="skills", nodes=[
        ProgressionNode(id="investigation", kind="skill", level=1, name="调查",
                        effects=[EffectSpec(op="grant_ability", target="investigation",
                                            data={"kind": "skill", "name": "调查"})]),
        ProgressionNode(id="negotiation", kind="skill", level=1, name="交涉",
                        requires=["investigation"],
                        costs=[EffectSpec(op="remove_resource", target="energy", value=1)],
                        effects=[EffectSpec(op="grant_ability", target="negotiation",
                                            data={"kind": "skill", "name": "交涉"})]),
    ])
    state = StoryState(characters={"hero": {"id": "hero"}},
                       resources={"energy": ResourceStock(id="energy", amount=2)})
    after_first = acquire(tree, state, "investigation", actor="hero")
    after_second = acquire(tree, after_first.state, "negotiation", actor="hero")
    assert after_second.ok and "negotiation" in after_second.state.abilities
    assert after_second.state.resources["energy"].amount == 1
