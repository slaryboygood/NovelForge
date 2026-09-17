"""V2-G：Writer 事实包、结构化事实校验、提议边界与降级路径。"""

from __future__ import annotations

from pathlib import Path

from novelforge.story_engine import (
    ActionCatalog,
    Condition,
    EventCard,
    KnowledgeEntry,
    ResourceStock,
    StoryState,
    WriterClaim,
    WriterOutput,
    build_writer_package,
    event_catalog_from_payload,
    render_scene,
    validate_writer_output,
)


ROOT = Path(__file__).resolve().parents[1]


def make_state() -> StoryState:
    state = StoryState(
        characters={"hero": {"id": "hero", "kind": "character", "name": "凌"},
                    "ally": {"id": "ally", "kind": "character", "name": "同行者"}},
        resources={"coin": ResourceStock(id="coin", amount=3, holders=["hero"])},
        knowledge=[KnowledgeEntry(id="ledger", holders=["hero"], reader_visible=False,
                                  certainty="fact", source="scene:study")],
        abilities={"observe": {"id": "observe", "kind": "skill", "name": "观察"}},
        identities={"hero": ["外门弟子"]},
        location={"current": "gate"},
    )
    state.author_knowledge = [KnowledgeEntry(id="hidden_truth", certainty="plan", source="author")]
    state.timeline.tick = 7
    return state


def card() -> EventCard:
    return EventCard(event_id="gate_scene", trigger=Condition(op="flag", key="ready", value=True),
                     participants=["hero", "ally"], scene_goal="守住闸口")


def test_package_isolates_character_knowledge_and_carries_structure() -> None:
    package = build_writer_package(make_state(), card(), required_results=["守住闸口"],
                                   style={"pov": "第三人称限知"})
    assert package.time["tick"] == 7 and package.location == "gate"
    assert set(package.characters) == {"hero", "ally"}
    assert "ledger" in package.characters["hero"].knowledge
    assert "ledger" not in package.characters["ally"].knowledge
    assert "hidden_truth" not in str(package.characters)
    assert package.required_results == ["守住闸口"] and package.forbidden and package.creative_space
    assert package.style["pov"] == "第三人称限知"
    assert any("作者计划" in note for note in package.author_notes)
    assert package.facts == ["ledger"]


def test_structured_claims_are_validated_against_state() -> None:
    state = make_state()
    package = build_writer_package(state, card(), required_results=["守住闸口"])
    good = WriterOutput(narration="凌按住闸门，没有多说什么。",
                        claims=[WriterClaim(kind="resource", id="coin", value=3),
                                WriterClaim(kind="knowledge", id="ledger", holder="hero"),
                                WriterClaim(kind="ability", id="observe", holder="hero"),
                                WriterClaim(kind="identity", id="外门弟子", holder="hero"),
                                WriterClaim(kind="location", id="gate")])
    result = validate_writer_output(state, package, good, actor="hero")
    assert result.accepted and not result.problems

    bad = WriterOutput(narration="...", claims=[
        WriterClaim(kind="resource", id="coin", value=1003),
        WriterClaim(kind="knowledge", id="hidden_truth", holder="hero"),
        WriterClaim(kind="ability", id="teleport", holder="hero"),
        WriterClaim(kind="location", id="palace"),
        WriterClaim(kind="fact", id="hidden_truth"),
        WriterClaim(kind="history", id="never_happened"),
    ])
    blocked = validate_writer_output(state, package, bad, actor="hero")
    assert blocked.accepted is False
    codes = " ".join(blocked.problems)
    for expected in ("RESOURCE_MISMATCH", "KNOWLEDGE_LEAK", "ABILITY_NOT_OWNED",
                     "LOCATION_MISMATCH", "PLAN_AS_FACT", "HISTORY_REWRITE"):
        assert expected in codes


def test_proposals_are_filtered_by_registry_and_conditions() -> None:
    state = make_state()
    package = build_writer_package(state, card(), required_results=["守住闸口"])
    actions = ActionCatalog(actions=[
        {"id": "hold_gate", "name": "守住闸口"},
        {"id": "use_ledger", "name": "出示账册",
         "requirements": [{"op": "knowledge", "target": "ledger"}]},
        {"id": "sealed_move", "name": "禁术",
         "requirements": [{"op": "identity", "value": "核心弟子"}]},
    ])
    events = event_catalog_from_payload({"catalog_id": "t", "cards": [
        {"event_id": "gate_scene", "trigger": {"op": "flag", "key": "ready", "value": True}}]})
    output = WriterOutput(narration="...",
                          proposed_actions=["hold_gate", "use_ledger", "sealed_move", "invented_move"],
                          proposed_events=["gate_scene", "invented_event"])
    result = validate_writer_output(state, package, output, catalog=actions, event_catalog=events,
                                    actor="ally")
    assert result.accepted_actions == ["hold_gate"]
    assert result.accepted_events == ["gate_scene"]
    codes = {item["code"] for item in result.dropped_actions}
    assert "ACTION_NOT_REGISTERED" in codes and "REQUIREMENT_NOT_SATISFIED" in codes
    assert {item["code"] for item in result.dropped_events} == {"EVENT_NOT_REGISTERED"}


def test_fallback_keeps_pipeline_alive_when_llm_fails() -> None:
    state = make_state()
    package = build_writer_package(state, card(), required_results=["守住闸口"])

    def boom(_package):
        raise RuntimeError("timeout")

    result = render_scene(state, package, boom)
    assert result.accepted is False and result.fallback_used is True
    assert "降级表现" in result.text and "守住闸口" in result.text
    assert any(item.startswith("LLM_ERROR") for item in result.problems)
    plain = render_scene(state, package, None)
    assert plain.fallback_used and plain.problems == ["LLM_UNAVAILABLE"]

    def lying(_package):
        return WriterOutput(narration="凭空多出一千枚钱。",
                            claims=[WriterClaim(kind="resource", id="coin", value=1003)])

    rejected = render_scene(state, package, lying)
    assert rejected.accepted is False and rejected.fallback_used is True
    assert any("RESOURCE_MISMATCH" in item for item in rejected.problems)
    assert state.resources["coin"].amount == 3 and state.location.current == "gate"


def test_accepted_narration_can_change_style_but_not_facts() -> None:
    state = make_state()
    package = build_writer_package(state, card(), required_results=["守住闸口"])

    def calm(_package):
        return WriterOutput(narration="雨声压住了脚步，凌只是把门闩推紧。")

    def loud(_package):
        return WriterOutput(narration="雷声炸响！凌一脚踹上闸门，吼声压过雨幕！")

    assert render_scene(state, package, calm).text != render_scene(state, package, loud).text
    assert render_scene(state, package, calm).accepted is True
    assert render_scene(state, package, loud).accepted is True
    assert state.resources["coin"].amount == 3 and state.location.current == "gate"


def test_location_claim_accepts_state_display_name() -> None:
    """地点声明既可以用 id，也可以用 StoryState 里的显示名（真实小说的地点名是中文显示名）。"""

    state = make_state()
    from novelforge.story_engine import Location

    state.location.known["gate"] = Location(id="gate", kind="gate", name="北闸口")
    package = build_writer_package(state, card(), required_results=["守住闸口"])

    def by_id(_package):
        return WriterOutput(narration="风从闸口灌进来。",
                            claims=[WriterClaim(kind="location", id="gate")])

    def by_name(_package):
        return WriterOutput(narration="北闸口的风更硬了。",
                            claims=[WriterClaim(kind="location", id="北闸口")])

    def wrong_place(_package):
        return WriterOutput(narration="他站在别处。",
                            claims=[WriterClaim(kind="location", id="palace")])

    assert render_scene(state, package, by_id).accepted is True
    assert render_scene(state, package, by_name).accepted is True
    rejected = render_scene(state, package, wrong_place)
    assert rejected.accepted is False and rejected.fallback_used is True
    assert any("LOCATION_MISMATCH" in item for item in rejected.problems)


def test_relationship_and_event_claims_follow_state_facts() -> None:
    """关系可以用维度名 / 数值 / 角色名 / 关系阶段声明；已触发事件属于已发生历史。"""

    from novelforge.story_engine import RelationshipState
    from novelforge.story_engine.entities import EffectRecord

    state = make_state()
    state.relationships.append(RelationshipState(source_id="hero", target_id="ally",
                                                 dimensions={"trust": 2.0},
                                                 data={"stage": "协作"}))
    state.effect_log.append(EffectRecord(id="fire:gate_scene:1", op="fire_event",
                                         target="gate_scene", order=1))
    # 事实包必须在关系写入之后重建（生产流程里每章都是重新构建事实包）。
    package = build_writer_package(state, card(), required_results=["守住闸口"])
    assert "gate_scene" in package.occurred_events

    def claims_for(note: str):
        return WriterOutput(narration="两人并肩守门。",
                            claims=[WriterClaim(kind="relationship", id="ally", note=note),
                                    WriterClaim(kind="history", id="gate_scene")])

    for legal in ("trust", "2.0", "同行者", "协作"):
        result = render_scene(state, package, lambda _p, legal=legal: claims_for(legal),
                              actor="hero")
        assert result.accepted is True, (legal, result.problems)
    wrong = render_scene(state, package, lambda _p: claims_for("生死之交"), actor="hero")
    assert wrong.accepted is False
    assert any("RELATIONSHIP_UNKNOWN" in item for item in wrong.problems)
    never = render_scene(state, package, lambda _p: WriterOutput(
        narration="他回忆起从未发生的事。",
        claims=[WriterClaim(kind="history", id="never_happened")]), actor="hero")
    assert never.accepted is False
    assert any("HISTORY_REWRITE" in item for item in never.problems)


def test_persistent_character_details_are_proposals_not_facts() -> None:
    """P2-08：长期人物事实必须作为提议返回；结构化校验只认声明，不解析正文。"""

    state = make_state()
    state.characters["ally"] = state.characters["ally"].model_copy(
        update={"data": {"role": "同行者"}})
    package = build_writer_package(state, card(), required_results=["守住闸口"])
    assert any(item["character_id"] == "ally" for item in package.persistent_character_facts)
    assert package.creative_details and package.known_facts == ["ledger"]

    def with_proposal(_package):
        return WriterOutput(narration="同行者皱眉，把账册往前推了一寸。",
                            proposed_new_facts=[{"character_id": "ally", "kind": "age",
                                                 "detail": "十三岁", "source": "llm_proposal"}])

    def malformed_proposal(_package):
        return WriterOutput(narration="同行者皱眉。",
                            proposed_new_facts=[{"kind": "age", "detail": "十三岁"}])

    accepted = render_scene(state, package, with_proposal)
    assert accepted.accepted is True, accepted.problems
    # 提议仍留在结构化结果里，但没有写进 StoryState。
    assert "age" not in (state.characters["ally"].data or {})
    rejected = render_scene(state, package, malformed_proposal)
    assert rejected.accepted is False
    assert any("PERSISTENT_DETAIL_INVALID" in item for item in rejected.problems)


def test_writer_layer_has_no_genre_branching() -> None:
    source = (ROOT / "src" / "novelforge" / "story_engine" / "writer.py").read_text(encoding="utf-8")
    for pattern in ("if genre ==", "if world_type ==", "if novel_id ==", "修仙", "科幻"):
        assert pattern not in source, pattern
