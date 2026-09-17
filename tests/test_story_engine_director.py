"""T10：候选事件池、可配置评分、节奏约束与 LLM Writer 边界。"""

from __future__ import annotations

from novelforge.story_engine import (
    DirectorWeights,
    EventCardCatalog,
    ResourceStock,
    StoryState,
    candidate_events,
    check_writer_output,
    event_catalog_from_payload,
    score_events,
    writer_brief,
)


def catalog() -> EventCardCatalog:
    return event_catalog_from_payload({
        "catalog_id": "director_test",
        "cards": [
            {"event_id": "main_push", "priority": 5, "once_only": False,
             "trigger": {"op": "flag", "key": "ready", "value": True},
             "kind": "main", "participants": ["hero"], "scene_goal": "推进主线", "conflict": "代价",
             "data": {"main_line": True, "character_arc": True, "pacing": "rise", "event_type": "main",
                      "danger": 1}},
            {"event_id": "side_rest", "priority": 2, "trigger": {"op": "resource", "key": "energy",
                                                                "value": 1, "comparator": ">="},
             "kind": "side", "data": {"pacing": "setup", "event_type": "side"}},
            {"event_id": "locked_event", "priority": 9,
             "trigger": {"op": "knowledge", "target": "secret"}, "kind": "secret",
             "data": {"main_line": True, "pacing": "climax", "event_type": "secret"}},
        ],
    })


def state() -> StoryState:
    return StoryState(characters={"hero": {"id": "hero", "kind": "player"}},
                      resources={"energy": ResourceStock(id="energy", amount=3)},
                      flags={"ready": True})


def test_candidate_pool_excludes_illegal_events() -> None:
    rows = candidate_events(catalog(), state(), actor="hero")
    assert {item.event_id for item in rows} == {"main_push", "side_rest"}
    assert "locked_event" not in {item.event_id for item in rows}


def test_score_order_follows_configurable_weights() -> None:
    default = score_events(catalog(), state())
    assert default[0].event_id == "main_push"
    assert "推进主线" in default[0].reasons
    # 调高节奏权重后，空历史下的铺垫类事件得分上升。
    default_side = next(item for item in default if item.event_id == "side_rest").score
    tuned = score_events(catalog(), state(), weights=DirectorWeights(main_line=0, character_arc=0,
                                                                    pacing=10))
    assert next(item for item in tuned if item.event_id == "side_rest").score > default_side
    # 玩家最近选择可直接提升对应事件。
    payload = catalog().model_dump()
    payload["cards"][1]["data"]["follows_choices"] = ["ask_help"]
    followed = score_events(event_catalog_from_payload(payload), state(), last_choice="ask_help")
    followed_side = next(item for item in followed if item.event_id == "side_rest")
    assert followed_side.score > default_side
    assert any("玩家最近的选择" in reason for reason in followed_side.reasons)


def test_pacing_penalises_repeats_and_writer_boundary_holds() -> None:
    state_with_history = state().model_copy(deep=True)
    from novelforge.story_engine.entities import EffectRecord
    state_with_history.effect_log.append(EffectRecord(id="fire:1", op="fire_event", target="main_push",
                                                      data={"event_type": "main"}, order=1))
    rows = {item.event_id: item for item in score_events(catalog(), state_with_history)}
    assert any("重复" in reason for reason in rows["main_push"].deductions)
    card = catalog().by_id("main_push")
    brief = writer_brief(card, state_with_history, actor="hero")
    assert brief.must_keep and any("资源" in item for item in brief.must_keep)
    assert "不得凭空增加资源或能力" in brief.must_not
    assert check_writer_output("主角凭空获得了一把剑。", brief)
    assert check_writer_output("主角按计划推进，代价是消耗了一份物资。", brief) == []
