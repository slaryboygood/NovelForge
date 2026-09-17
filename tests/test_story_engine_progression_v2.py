"""V2-F：同一套 Progression Engine 表达七类成长。"""

from __future__ import annotations

from pathlib import Path

from novelforge.story_engine import (
    Condition,
    KnowledgeEntry,
    ProgressionNode,
    ProgressionTree,
    RelationshipState,
    ResourceStock,
    StoryState,
    acquire,
    knows,
    options,
    owned_nodes,
    unlock_state,
)


ROOT = Path(__file__).resolve().parents[1]


def seven_trees() -> dict[str, ProgressionTree]:
    return {
        "progression": ProgressionTree(tree_id="cultivation", nodes=[
            ProgressionNode(id="realm_1", category="progression", level=1, name="一层",
                            effects=[{"op": "add_identity", "value": "一层弟子"}]),
            ProgressionNode(id="realm_2", category="progression", level=2, name="二层",
                            requires=["realm_1"],
                            costs=[{"op": "remove_resource", "target": "energy", "value": 2}],
                            effects=[{"op": "grant_ability", "target": "realm_2",
                                      "data": {"kind": "境界", "name": "二层"}}])]),
        "ability": ProgressionTree(tree_id="cyber", nodes=[
            ProgressionNode(id="grade_1", category="ability", name="民用级",
                            effects=[{"op": "add_identity", "value": "民用权限"}]),
            ProgressionNode(id="grade_2", category="ability", requires=["grade_1"], name="军规义体",
                            costs=[{"op": "remove_resource", "target": "energy", "value": 3}],
                            effects=[{"op": "grant_ability", "target": "military_chassis",
                                      "data": {"kind": "义体", "name": "军规义体"}}])]),
        "identity": ProgressionTree(tree_id="org", nodes=[
            ProgressionNode(id="outer", category="identity", effects=[{"op": "add_identity", "value": "外门"}]),
            ProgressionNode(id="inner", category="identity", requires=["outer"], name="内门",
                            unlock=Condition(op="numeric", key="flags.merit", value=3, comparator=">="),
                            effects=[{"op": "add_identity", "value": "内门"}])]),
        "relationship": ProgressionTree(tree_id="bond", nodes=[
            ProgressionNode(id="stranger", category="relationship", name="陌生",
                            effects=[{"op": "change_relationship", "target": "ally",
                                      "key": "trust", "value": 0, "data": {"stage": "stranger"}}]),
            ProgressionNode(id="partner", category="relationship", requires=["stranger"], name="合作",
                            unlock=Condition(op="numeric", key="flags.coop_count", value=1, comparator=">="),
                            effects=[{"op": "change_relationship", "target": "ally", "key": "trust",
                                      "value": 1, "data": {"stage": "partner"}}])]),
        "faction": ProgressionTree(tree_id="guild", nodes=[
            ProgressionNode(id="member", category="faction", name="成员",
                            effects=[{"op": "add_identity", "value": "行会成员"},
                                     {"op": "update_faction", "target": "guild",
                                      "data": {"name": "行会", "influence": 1}}]),
            ProgressionNode(id="officer", category="faction", requires=["member"], name="执事",
                            effects=[{"op": "update_faction", "target": "guild",
                                      "data": {"influence": 3}}])]),
        "information": ProgressionTree(tree_id="intel", nodes=[
            ProgressionNode(id="clue_1", category="information", name="线索：账册",
                            effects=[{"op": "add_knowledge", "entity": "hero", "target": "ledger_clue"}]),
            ProgressionNode(id="clue_2", category="information", requires=["clue_1"], name="线索：原件",
                            unlock=Condition(op="knowledge", entity="hero", target="ledger_clue"),
                            effects=[{"op": "add_knowledge", "entity": "hero", "target": "ledger_original"}])]),
        "equipment": ProgressionTree(tree_id="gear", nodes=[
            ProgressionNode(id="blade_1", category="equipment", name="旧刀",
                            effects=[{"op": "add_resource", "entity": "hero", "target": "blade",
                                      "value": 1, "unit": "把"}]),
            ProgressionNode(id="blade_2", category="equipment", requires=["blade_1"], name="重铸刀",
                            costs=[{"op": "remove_resource", "entity": "hero", "target": "blade", "value": 1},
                                   {"op": "remove_resource", "entity": "hero", "target": "materials", "value": 2}],
                            effects=[{"op": "add_resource", "entity": "hero", "target": "blade_refined",
                                      "value": 1, "unit": "把"}])]),
        "skill": ProgressionTree(tree_id="skills", nodes=[
            ProgressionNode(id="investigate", category="skill", name="调查",
                            effects=[{"op": "grant_ability", "target": "investigate",
                                      "data": {"kind": "skill", "name": "调查"}}]),
            ProgressionNode(id="negotiate", category="skill", requires=["investigate"], name="谈判",
                            effects=[{"op": "grant_ability", "target": "negotiate",
                                      "data": {"kind": "skill", "name": "谈判"}}])]),
    }


def state() -> StoryState:
    return StoryState(characters={"hero": {"id": "hero", "kind": "character"},
                                  "ally": {"id": "ally", "kind": "character"}},
                      resources={"energy": ResourceStock(id="energy", amount=6, holders=["hero"]),
                                 "materials": ResourceStock(id="materials", amount=2, holders=["hero"])},
                      relationships=[RelationshipState(source_id="hero", target_id="ally")])


def test_one_engine_expresses_seven_growth_categories() -> None:
    trees = seven_trees()
    assert len({type(tree) for tree in trees.values()}) == 1
    current = state()
    # 逐类解锁第一级
    for name, tree in trees.items():
        first = tree.nodes[0]
        result = acquire(tree, current, first.id, actor="hero")
        assert result.ok, name + ":" + result.message
        current = result.state
    assert {"realm_1", "grade_1", "outer", "stranger", "member", "clue_1", "blade_1",
            "investigate"} <= owned_nodes(current)
    assert "hero" in current.identities
    assert knows(current, "ledger_clue", "hero") is True
    assert current.resources["blade"].amount == 1
    stage = current.relationships[0].data["stage"]
    assert stage == "stranger"  # 关系树只写阶段，不替代 trust / hostility
    assert current.resources["energy"].amount == 6  # 未解锁的第二级不会消耗


def test_locked_by_condition_and_prerequisites() -> None:
    trees = seven_trees()
    current = state()
    assert unlock_state(trees["identity"], current, "inner", actor="hero") == "locked"
    assert unlock_state(trees["identity"], current, "outer", actor="hero") == "available"
    current = acquire(trees["identity"], current, "outer", actor="hero").state
    current.flags["merit"] = 3
    assert unlock_state(trees["identity"], current, "inner", actor="hero") == "available"
    inner = acquire(trees["identity"], current, "inner", actor="hero")
    assert inner.ok and unlock_state(trees["identity"], inner.state, "inner", actor="hero") == "owned"
    # 成本不足时保持锁定，且不消耗资源
    poor = state()
    poor.resources["energy"] = ResourceStock(id="energy", amount=1, holders=["hero"])
    poor = acquire(trees["progression"], poor, "realm_1", actor="hero").state
    blocked = acquire(trees["progression"], poor, "realm_2", actor="hero")
    assert blocked.ok is False and poor.resources["energy"].amount == 1


def test_growth_does_not_create_facts_out_of_nothing() -> None:
    trees = seven_trees()
    current = state()
    # 信息树第二级需要已知第一级线索，不能凭空解锁。
    assert unlock_state(trees["information"], current, "clue_2", actor="hero") == "locked"
    # 装备升级需要材料与旧装备：缺一不可。
    current = acquire(trees["equipment"], current, "blade_1", actor="hero").state
    upgraded = acquire(trees["equipment"], current, "blade_2", actor="hero")
    assert upgraded.ok
    assert upgraded.state.resources["blade"].amount == 0
    assert upgraded.state.resources["materials"].amount == 0
    assert upgraded.state.resources["blade_refined"].amount == 1
    # 未获得线索时，信息节点不会让任何角色知道秘密。
    fresh = state()
    assert not knows(fresh, "ledger_original", "hero")
    # 关系树不写死 NPC 行为，也不复制关系事实。
    after = acquire(trees["relationship"], current, "stranger", actor="hero")
    assert after.ok and "stage" in after.state.relationships[0].data
    assert "trust" in after.state.relationships[0].dimensions


def test_progression_layer_has_no_genre_branching() -> None:
    source = (ROOT / "src" / "novelforge" / "story_engine" / "progression.py").read_text(encoding="utf-8")
    # 引擎逻辑不得按题材分支；题材只允许以模板数据形式存在。
    for pattern in ("if genre ==", "if world_type ==", "if novel_id ==", "if tree_id ==",
                    'if "修仙"', 'if "科幻"'):
        assert pattern not in source, pattern
