"""V2-D-01～D-05：多维导演评分、可配置权重、长期平衡、节奏与可解释性。"""

from __future__ import annotations

from pathlib import Path

from novelforge.story_engine import (
    DirectorWeights,
    EventCardCatalog,
    PlotTrack,
    StoryState,
    decide,
    event_catalog_from_payload,
    score_events,
    upsert_plot,
    weights_from_config,
)


ROOT = Path(__file__).resolve().parents[1]


def catalog() -> EventCardCatalog:
    return event_catalog_from_payload({
        "catalog_id": "director_v2",
        "cards": [
            {"event_id": "main_battle", "title": "闸口对峙", "kind": "main", "priority": 4, "once_only": False,
             "trigger": {"op": "flag", "key": "ready", "value": True},
             "data": {"main_line": True, "pacing": "rise", "event_type": "battle", "crisis": 1, "danger": 1}},
            {"event_id": "ledger_twist", "title": "账册线索", "kind": "mystery", "priority": 2, "once_only": False,
             "trigger": {"op": "flag", "key": "ready", "value": True},
             "data": {"subplot": "ledger", "pacing": "turn", "event_type": "mystery",
                      "foreshadow": 1, "payoff": 1}},
            {"event_id": "sister_step", "title": "妹妹的消息", "kind": "side", "priority": 2, "once_only": False,
             "trigger": {"op": "flag", "key": "ready", "value": True},
             "data": {"subplot": "sister", "character_arc": True, "pacing": "setup", "event_type": "side"}},
        ],
    })


def state() -> StoryState:
    current = StoryState(characters={"hero": {"id": "hero", "kind": "character"}},
                         flags={"ready": True})
    current = upsert_plot(current, PlotTrack(id="ledger", title="账册疑云", status="active",
                                             priority=3, progress=0))
    current = upsert_plot(current, PlotTrack(id="sister", title="寻找妹妹", status="active",
                                             priority=2, progress=1))
    return current


def test_dimensions_are_independent_and_configurable() -> None:
    rows = {item.event_id: item for item in score_events(catalog(), state())}
    ledger = rows["ledger_twist"]
    assert ledger.dimensions["subplot"] > 0 and ledger.dimensions["foreshadow"] > 0
    assert ledger.dimensions["payoff"] > 0
    assert any("支线长期未推进" in reason for reason in ledger.reasons)  # ledger 进度最低
    assert rows["main_battle"].dimensions["main_line"] > 0
    # 权重来自配置：调高 payoff 后账册事件总分上升。
    tuned = weights_from_config({"payoff": 5.0, "main_line": 0.1})
    tuned_rows = {item.event_id: item for item in score_events(catalog(), state(), weights=tuned)}
    assert tuned_rows["ledger_twist"].score > rows["ledger_twist"].score
    assert tuned_rows["main_battle"].score < rows["main_battle"].score


def test_repetition_penalty_and_explainable_decision() -> None:
    from novelforge.story_engine.entities import EffectRecord

    current = state()
    current.effect_log.append(EffectRecord(id="fire:1", op="fire_event", target="main_battle",
                                           data={"event_type": "battle"}, order=1))
    rows = {item.event_id: item for item in score_events(catalog(), current)}
    assert rows["main_battle"].dimensions["repetition"] < 0
    assert any("重复" in item for item in rows["main_battle"].deductions)
    decision = decide(catalog(), current)
    assert decision.chosen in {"ledger_twist", "sister_step"}
    assert decision.why_chosen
    assert decision.why_not and all(reasons for reasons in decision.why_not.values())


def test_long_term_balance_prefers_starved_subplot_without_mechanical_rotation() -> None:
    fresh = state()
    balance_weights = weights_from_config({"subplot": 3.0, "balance": 3.0})
    ledger_first = decide(catalog(), fresh, weights=balance_weights).chosen
    assert ledger_first == "ledger_twist"  # 进度最低的支线优先
    advanced = fresh.model_copy(deep=True)
    advanced.plots["ledger"]["progress"] = 9
    advanced.plots["sister"]["progress"] = 0
    next_choice = decide(catalog(), advanced, weights=balance_weights).chosen
    assert next_choice == "sister_step"
    # 不是机械轮询：主线危机压力足够大时仍可压过支线。
    crisis_weights = weights_from_config({"crisis": 6.0, "subplot": 0.2, "balance": 0.2})
    heavy = decide(catalog(), advanced, weights=crisis_weights)
    assert heavy.ranked[0].dimensions.get("crisis", 0) > 0


def test_director_only_ranks_legal_events_and_has_no_genre_branching() -> None:
    locked = state()
    locked.flags["ready"] = False
    assert score_events(catalog(), locked) == []
    decision = decide(catalog(), locked)
    assert decision.chosen == "" and decision.ranked == []
    source = "".join((ROOT / "src" / "novelforge" / "story_engine" / name).read_text(encoding="utf-8")
                     for name in ("director.py",))
    for pattern in ("if genre ==", "if world_type ==", "if novel_id ==", "修仙", "科幻"):
        assert pattern not in source, pattern


def test_same_event_frequency_penalty_is_configurable() -> None:
    """P3-04：同一事件在近期反复出现时降权，权重可配置，不含小说专用规则。"""

    from novelforge.story_engine.entities import EffectRecord

    current = state()
    for index in range(3):
        current.effect_log.append(EffectRecord(id=f"fire:{index}", op="fire_event",
                                               target="ledger_twist", order=index + 1,
                                               data={"event_type": "mystery"}))
    tuned = weights_from_config({"event_repetition": 4.0, "event_repetition_window": 4})
    rows = {item.event_id: item for item in score_events(catalog(), current, weights=tuned)}
    assert rows["ledger_twist"].dimensions["event_repetition"] == -12.0
    assert any("同一事件" in item for item in rows["ledger_twist"].deductions)
    # 权重为 0 时关闭该维度。
    off = weights_from_config({"event_repetition": 0.0})
    rows_off = {item.event_id: item for item in score_events(catalog(), current, weights=off)}
    assert "event_repetition" not in rows_off["ledger_twist"].dimensions
