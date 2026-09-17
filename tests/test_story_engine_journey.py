"""T08d-02a：JourneyRuntime 与旧 design_scene 的逐字对照。"""

from __future__ import annotations

from pathlib import Path

import pytest

from novelforge.story_builder.adventures import AdventureEngine
from novelforge.story_builder.blueprints import StoryBlueprintRepository
from novelforge.story_engine import (
    JourneyRuntime,
    design_from_blueprint,
    initial_journey_state,
    journey_revision,
    load_content_pack,
    record_choice,
)
from novelforge.story_engine.entities import ResourceStock
from test_story_builder_design_tree import complete_base, make_client, pick


ROOT = Path(__file__).resolve().parents[1]
PACK = load_content_pack(ROOT / "novel" / "config" / "story_engine" / "journey_v1.json")
LEGACY_TO_PACK = {
    "help": "journey_help", "clue": "journey_clue", "supply": "journey_supply",
    "wait": "journey_wait", "ally": "journey_ally", "proof": "journey_proof",
    "pay": "journey_pay", "leave": "journey_leave", "expose": "journey_expose",
    "rescue": "journey_rescue", "continue_trace": "followup_continue_trace",
    "continue_recover": "followup_continue_recover", "settle": "followup_settle",
    "honor_partner": "followup_honor_partner", "negotiate_time": "followup_negotiate_time",
    "go_alone": "followup_go_alone", "seek_receipt": "followup_seek_receipt",
    "accept_private": "followup_accept_private", "verify_order": "followup_verify_order",
    "keep_receipt": "followup_keep_receipt", "record_limits": "followup_record_limits",
    "end_public": "followup_end_public", "end_cooperate": "followup_end_cooperate",
    "end_depart": "followup_end_depart",
}


def pack_ids(scene: dict) -> list[str]:
    # 内容包通过 choice_aliases 对外暴露与旧引擎一致的 choice id。
    return [item['id'] for item in scene['choices']]


def blueprint_for(tmp_path, opening: str):
    client, url = make_client(tmp_path)
    complete_base(client, url)
    for field, option in [("hero_history", "hero_lone_survivor"),
                          ("companion_history", "companion_old_friend"),
                          ("opponent_history", "opponent_climber"),
                          ("opponent_motive", "opponent_monopoly"),
                          ("opponent_temperament", "opponent_trade"),
                          ("opening_pattern", opening)]:
        assert pick(client, url, field, option).status_code == 200
    compiled = client.post(url + '/compile-blueprint').json()['blueprint']
    blueprint_id = compiled['blueprint_id']
    confirmed = client.post('/api/story-builder/blueprints/' + blueprint_id + '/confirm',
                            json={'version': compiled['version']})
    assert confirmed.status_code == 200
    repository = StoryBlueprintRepository(tmp_path)
    blueprint = repository.latest(blueprint_id)
    assert blueprint is not None
    return blueprint, blueprint_id, blueprint.version


def compare(scene: dict, rendered, *, choice_ids: list[str] | None = None) -> None:
    assert rendered.title == scene['title']
    assert rendered.text == scene['text']
    if scene.get('goal'):
        assert rendered.goal == scene['goal']
    assert rendered.completed == scene['completed']
    expected_ids = choice_ids if choice_ids is not None else [item['id'] for item in scene['choices']]
    assert [item.id for item in rendered.choices] == expected_ids
    assert [(item.label, item.cost) for item in rendered.choices] == \
           [(item['label'], item['cost']) for item in scene['choices']]
    assert [item.suggested for item in rendered.choices] == [item.get('suggested', False) for item in scene['choices']]


@pytest.mark.parametrize("opening", ["opening_mystery", "opening_survival", "opening_debt"])
def test_first_scene_matches_legacy_output(tmp_path: Path, opening: str) -> None:
    blueprint, blueprint_id, version = blueprint_for(tmp_path, opening)
    legacy = AdventureEngine(tmp_path).start(blueprint_id, version)
    design = design_from_blueprint(blueprint)
    state = initial_journey_state(PACK, novel_id=blueprint.project_id)
    scene = JourneyRuntime(PACK).scene(state, design, warnings=legacy['warnings'])
    # 旧引擎在 rev0 用 legacy choice id，对照时映射到内容包 action id。
    compare(legacy, scene, choice_ids=pack_ids(legacy))
    assert scene.next_question == legacy['next_question']
    assert scene.success == legacy['success']


def test_second_and_third_scene_match_legacy_output(tmp_path: Path) -> None:
    blueprint, blueprint_id, version = blueprint_for(tmp_path, "opening_debt")
    engine = AdventureEngine(tmp_path)
    runtime = JourneyRuntime(PACK)
    design = design_from_blueprint(blueprint)

    engine.start(blueprint_id, version)
    state = initial_journey_state(PACK, novel_id=blueprint.project_id)

    # 第一关：核对现场痕迹与记录
    legacy_engine_state = engine.choose(blueprint_id, version, 0, 'clue')
    resolved = runtime.choose(state, design, "journey_clue")
    assert resolved.ok
    state = resolved.state
    rendered = runtime.scene(state, design, warnings=legacy_engine_state['warnings'])
    compare(legacy_engine_state, rendered, choice_ids=pack_ids(legacy_engine_state))

    # 第二关：等待一次通行机会
    legacy_engine_state = engine.choose(blueprint_id, version, 1, 'wait')
    resolved = runtime.choose(state, design, "journey_wait")
    state = resolved.state
    rendered = runtime.scene(state, design, warnings=legacy_engine_state['warnings'])
    compare(legacy_engine_state, rendered, choice_ids=pack_ids(legacy_engine_state))

    # 第三关：撤出
    legacy_engine_state = engine.choose(blueprint_id, version, 2, 'leave')
    resolved = runtime.choose(state, design, "journey_leave")
    assert resolved.ok and resolved.state.flags["arc_finished"] is False
    state = resolved.state
    rendered = runtime.scene(state, design, warnings=legacy_engine_state['warnings'])
    assert rendered.title == legacy_engine_state['title']
    assert rendered.text == legacy_engine_state['text']
    assert rendered.completed == legacy_engine_state['completed']
    assert rendered.text == next(item['result'] for item in engine.start(blueprint_id, version)['state']['history']
                                 if item['choice_id'] == 'leave')


def test_runtime_matches_legacy_supply_and_pay_numbers(tmp_path: Path) -> None:
    blueprint, blueprint_id, version = blueprint_for(tmp_path, "opening_debt")
    engine = AdventureEngine(tmp_path)
    runtime = JourneyRuntime(PACK)
    design = design_from_blueprint(blueprint)
    state = initial_journey_state(PACK, novel_id=blueprint.project_id)
    assert state.resources["supplies"].amount == engine.start(blueprint_id, version)['state']['supplies']

    legacy = engine.choose(blueprint_id, version, 0, 'supply')
    resolved = runtime.choose(state, design, "journey_supply")
    assert resolved.ok
    assert resolved.state.resources["supplies"].amount == legacy['state']['supplies']

    legacy = engine.choose(blueprint_id, version, 1, 'pay')
    resolved = runtime.choose(resolved.state, design, "journey_pay")
    assert resolved.ok
    assert resolved.state.resources["supplies"].amount == legacy['state']['supplies']


def test_runtime_matches_legacy_ally_flag_and_cost(tmp_path: Path) -> None:
    blueprint, blueprint_id, version = blueprint_for(tmp_path, "opening_debt")
    engine = AdventureEngine(tmp_path)
    runtime = JourneyRuntime(PACK)
    design = design_from_blueprint(blueprint)
    state = initial_journey_state(PACK, novel_id=blueprint.project_id)
    engine.start(blueprint_id, version)
    legacy = engine.choose(blueprint_id, version, 0, 'help')
    resolved = runtime.choose(state, design, "journey_help")
    assert resolved.ok
    assert resolved.state.flags["ally"] is legacy['state']['ally'] is True
    assert resolved.state.resources["supplies"].amount == legacy['state']['supplies']
    # 帮助之后第二关可以请同行者协助，两边选项一致。
    legacy = engine.choose(blueprint_id, version, 1, 'ally')
    resolved = runtime.choose(resolved.state, design, "journey_ally")
    assert resolved.ok
    rendered = runtime.scene(resolved.state, design, warnings=legacy['warnings'])
    compare(legacy, rendered, choice_ids=pack_ids(legacy))


class Pair:
    """旧引擎与 JourneyRuntime 的并行路线，逐步对照场景与状态。"""

    def __init__(self, tmp_path: Path, opening: str = "opening_debt") -> None:
        blueprint, blueprint_id, version = blueprint_for(tmp_path, opening)
        self.blueprint, self.bp_id, self.version = blueprint, blueprint_id, version
        self.engine = AdventureEngine(tmp_path)
        self.runtime = JourneyRuntime(PACK)
        self.design = design_from_blueprint(blueprint)
        self.legacy = self.engine.start(blueprint_id, version)
        self.state = initial_journey_state(PACK, novel_id=blueprint.project_id)

    def step(self, legacy_id: str, pack_id: str):
        revision = self.legacy['state']['revision']
        self.legacy = self.engine.choose(self.bp_id, self.version, revision, legacy_id)
        resolved = self.runtime.choose(self.state, self.design, pack_id)
        assert resolved.ok, resolved.code + resolved.message
        self.state = resolved.state
        rendered = self.runtime.scene(self.state, self.design, warnings=self.legacy['warnings'])
        return self.legacy, rendered, resolved

    def assert_state_matches(self) -> None:
        legacy = self.legacy['state']
        assert self.state.resources["supplies"].amount == legacy['supplies']
        assert int(self.state.flags.get("trust", 0)) == legacy['trust']
        assert int(self.state.flags.get("debt", 0)) == legacy['debt']
        assert bool(self.state.flags.get("arc_finished")) is legacy['arc_finished']
        assert {item.id for item in self.state.knowledge} == set(legacy['facts'])
        assert journey_revision(self.state) == legacy['revision']


def test_followup_full_path_matches_legacy_output_and_state(tmp_path: Path) -> None:
    pair = Pair(tmp_path)
    for legacy_id, pack_id in [("help", "journey_help"), ("ally", "journey_ally"),
                               ("expose", "journey_expose")]:
        legacy, rendered, _ = pair.step(legacy_id, pack_id)
        compare(legacy, rendered, choice_ids=pack_ids(legacy))
    pair.assert_state_matches()

    # rev3（本段旅程结束）→ continue_trace 进入 rev4
    legacy, rendered, _ = pair.step("continue_trace", "followup_continue_trace")
    assert legacy['title'] == "先兑现谁的承诺" and rendered.title == legacy['title']
    compare(legacy, rendered, choice_ids=pack_ids(legacy))
    assert "同行者还记得你们的约定" in rendered.text
    assert "欠下的交换责任还有 0 份" in rendered.text

    # rev4 → honor_partner：补给 -1，信任 +1，偿还一份责任
    legacy, rendered, _ = pair.step("honor_partner", "followup_honor_partner")
    assert legacy['state']['supplies'] == 0 and pair.state.resources["supplies"].amount == 0
    assert legacy['state']['trust'] == 1 and int(pair.state.flags["trust"]) == 1
    assert legacy['state']['debt'] == 0 and int(pair.state.flags["debt"]) == 0
    assert "关系缓和后" in rendered.text  # trust > 0 分支
    compare(legacy, rendered, choice_ids=pack_ids(legacy))
    pair.assert_state_matches()

    # rev5 → seek_receipt：取得回执
    legacy, rendered, _ = pair.step("seek_receipt", "followup_seek_receipt")
    assert legacy['state']['facts'] == ["receipt"]
    assert {item.id for item in pair.state.knowledge} == {"receipt"}
    assert "交接人拿出了自己的回执" in rendered.text

    # rev6 → verify_order：知识升级为可核验解释
    legacy, rendered, _ = pair.step("verify_order", "followup_verify_order")
    assert set(legacy['state']['facts']) == {"receipt", "diversion_verified"}
    assert {item.id for item in pair.state.knowledge} == {"receipt", "diversion_verified"}
    assert rendered.text == legacy['text']

    # rev7 → end_public：公开证据并收束
    legacy, rendered, _ = pair.step("end_public", "followup_end_public")
    assert legacy['state']['arc_finished'] is True
    assert pair.state.flags["arc_finished"] is True
    assert rendered.completed is True and rendered.choices == []
    assert rendered.title == "篇章已收束" == legacy['title']
    assert rendered.text == legacy['text']
    pair.assert_state_matches()


def test_followup_without_receipt_matches_legacy(tmp_path: Path) -> None:
    pair = Pair(tmp_path)
    for legacy_id, pack_id in [("supply", "journey_supply"), ("wait", "journey_wait"),
                               ("rescue", "journey_rescue")]:
        legacy, rendered, _ = pair.step(legacy_id, pack_id)
        compare(legacy, rendered, choice_ids=pack_ids(legacy))
    # rev3 → continue_recover：补给 +1 并欠下一份责任
    legacy, rendered, _ = pair.step("continue_recover", "followup_continue_recover")
    assert legacy['state']['supplies'] == pair.state.resources["supplies"].amount
    assert legacy['state']['debt'] == 1 == int(pair.state.flags["debt"])
    # rev4 → go_alone：信任下降（floor 0）
    legacy, rendered, _ = pair.step("go_alone", "followup_go_alone")
    assert legacy['state']['trust'] == -1 == int(pair.state.flags["trust"])
    assert "没人主动替你说话" in rendered.text
    # rev5 → accept_private：没有回执
    legacy, rendered, _ = pair.step("accept_private", "followup_accept_private")
    assert rendered.text == legacy['text'] == "你得到了私下通行的机会，却没有拿到回执。眼前的顺利不等于已经知道事情的来由。"
    assert [item.id for item in rendered.choices] == ["record_limits"]
    # rev6 → record_limits → rev7 无 end_public
    legacy, rendered, _ = pair.step("record_limits", "followup_record_limits")
    ids = [item['id'] for item in legacy['choices']]
    assert ids == ["end_depart"] and [item.id for item in rendered.choices] == ["end_depart"]
    # rev7 → end_depart 收束
    legacy, rendered, _ = pair.step("end_depart", "followup_end_depart")
    assert rendered.completed is True and rendered.choices == []
    pair.assert_state_matches()


def test_followup_settle_ends_immediately(tmp_path: Path) -> None:
    pair = Pair(tmp_path)
    pair.step("help", "journey_help")
    pair.step("wait", "journey_wait")
    pair.step("leave", "journey_leave")
    legacy, rendered, resolved = pair.step("settle", "followup_settle")
    assert rendered.completed is True and rendered.choices == []
    assert rendered.title == "篇章已收束"
    assert resolved.state.flags["arc_finished"] is True
    assert rendered.text == legacy['text']
    pair.assert_state_matches()
