from __future__ import annotations

from pathlib import Path

import pytest

from novelforge.story_engine import (
    Condition,
    EffectSpec,
    StoryState,
    apply_effects,
    load_content_pack,
)
from novelforge.story_engine.content import ContentPackError, content_pack_from_payload


ROOT = Path(__file__).resolve().parents[1]
PACK_PATH = ROOT / "novel" / "config" / "story_engine" / "journey_v1.json"


def test_journey_pack_loads_and_references_resolve() -> None:
    pack = load_content_pack(PACK_PATH)
    assert pack.pack_id == "journey_v1"
    assert len(pack.text.opening_profiles) == 12
    assert len(pack.events) == 4
    assert len(pack.actions) >= 20
    assert pack.initial_resources == {"supplies": 2}
    assert pack.initial_flags["journey_revision"] == 0
    for event in pack.events:
        assert event.available_actions, event.event_id
        for action_id in event.available_actions:
            assert pack.action(action_id).id == action_id


def test_pack_migrates_legacy_texts_and_numbers() -> None:
    pack = load_content_pack(PACK_PATH)
    text = pack.text
    assert text.place_for(["world_cultivation_realms"]) == "山门驿站"
    assert text.place_for(["world_silicon_mmo"]) == "旧能源站"
    assert text.place_for([]) == "街区办事处"
    assert text.crisis_default_opening["crisis_missing"] == "opening_mystery"
    assert text.crisis_success["crisis_quota"] == "争取到重新核查扣押物资的机会"
    mystery = text.opening_profiles["opening_mystery"]
    assert (mystery.title, mystery.success) == ("对不上的记录", "证实异常并非记忆错误")
    assert text.hero_memories["hero_lone_survivor"].startswith("独自谋生")
    assert text.companion_lines["companion_old_friend"].startswith("旧友")
    assert text.opponent_pressure["opponent_procedure"].startswith("负责人把书面程序")
    assert text.scene_titles["rev2"] == "带着什么离开"
    assert text.scene_texts["rev1_supply"].startswith("收集物资耽误了时间")

    help_action = pack.action("journey_help")
    assert help_action.data["cost_text"] == "消耗 1 补给，换来具体协助"
    assert help_action.costs[0].op == "remove_resource" and help_action.costs[0].value == 1
    assert {item.op for item in help_action.immediate_effects} == {"set_flag"}
    supply = pack.action("journey_supply")
    assert supply.immediate_effects[0].value == 2
    pay = pack.action("journey_pay")
    assert pay.requirements[0].value == 2 and pay.costs[0].value == 2
    rescue = pack.action("journey_rescue")
    assert rescue.costs[0].value == 1
    assert pack.action("followup_continue_recover").immediate_effects[0].value == 1
    assert pack.action("followup_honor_partner").costs[0].value == 1
    assert pack.recompute.floors == {"debt": 0}
    assert {"counter": "debt", "delta": 1, "when_choice": ["followup_continue_recover", "followup_negotiate_time"]} in \
           [rule.model_dump() for rule in pack.recompute.counters]
    assert pack.recompute.knowledge_choices["followup_verify_order"] == "diversion_verified"
    assert pack.recompute.arc_finished_choices == ["followup_settle", "followup_end_public",
                                                   "followup_end_cooperate", "followup_end_depart"]
    assert pack.action("followup_end_public").requirements[0].op == "knowledge"


def test_pack_actions_execute_on_story_state_with_legacy_numbers() -> None:
    pack = load_content_pack(PACK_PATH)
    state = StoryState(
        characters={"protagonist": {"id": "protagonist", "kind": "player"}},
        resources={"supplies": {"id": "supplies", "amount": 2, "unit": "份",
                                "holders": ["protagonist"]}},
        flags=dict(pack.initial_flags),
    )
    helped = apply_effects(state, pack.action("journey_help").costs + pack.action("journey_help").immediate_effects,
                           actor="protagonist", source="action:journey_help")
    assert helped.ok
    assert helped.state.resources["supplies"].amount == 1
    assert helped.state.flags["ally"] is True
    # 场景进度由运行时在每次选择后推进，不由内容包逐条声明。
    assert helped.state.flags["journey_revision"] == 0
    gathered = apply_effects(helped.state, pack.action("journey_supply").immediate_effects,
                             actor="protagonist", source="action:journey_supply")
    assert gathered.state.resources["supplies"].amount == 3
    blocked = apply_effects(gathered.state, [EffectSpec(id="too_much", op="remove_resource",
                                                       entity="protagonist", target="supplies",
                                                       value=99)],
                            actor="protagonist", source="test")
    assert not blocked.ok and blocked.state.resources["supplies"].amount == 3


def test_pack_validation_rejects_unknown_action_reference() -> None:
    payload = {
        "pack_id": "broken",
        "events": [{"event_id": "broken_event", "trigger": {"op": "flag", "key": "x", "value": True},
                    "available_actions": ["missing_action"]}],
    }
    with pytest.raises(ContentPackError):
        content_pack_from_payload(payload)
    with pytest.raises(ContentPackError):
        load_content_pack(ROOT / "novel" / "config" / "story_engine" / "missing_pack.json")


def test_content_layer_has_no_genre_branching() -> None:
    source = (ROOT / "src" / "novelforge" / "story_engine" / "content.py").read_text(encoding="utf-8")
    for pattern in ("if genre ==", "if world_type ==", "if template_id ==",
                    "from novelforge.story_builder", "import novelforge.story_builder"):
        assert pattern not in source, pattern
    # 条件与效果仍然只走通用模型。
    pack = load_content_pack(PACK_PATH)
    assert isinstance(pack.text.opening_profiles["opening_debt"], type(pack.text.opening_profiles["opening_mystery"]))
    assert isinstance(pack.events[0].trigger, Condition)
