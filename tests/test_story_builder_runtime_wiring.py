"""T08d-02b-2：新旅程走 JourneyRuntime，旧旅程继续走兼容路径。"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from test_story_builder_design_tree import complete_base, make_client, pick


ROOT = Path(__file__).resolve().parents[1]
PACK_SOURCE = ROOT / "novel" / "config" / "story_engine" / "journey_v1.json"
LEGACY_FIELDS = {"blueprint_id", "blueprint_version", "revision", "rules_version", "branch_id",
                 "parent_branch", "fork_revision", "supplies", "ally", "clue", "trust", "debt",
                 "facts", "arc_finished", "history"}


def install_pack(tmp_path: Path) -> None:
    target = tmp_path / "novel" / "config" / "story_engine"
    target.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(PACK_SOURCE, target / "journey_v1.json")


def start_journey(tmp_path: Path, *, with_pack: bool = True):
    if with_pack:
        install_pack(tmp_path)
    client, url = make_client(tmp_path)
    complete_base(client, url)
    for field, option in [("hero_history", "hero_lone_survivor"),
                          ("companion_history", "companion_old_friend"),
                          ("opponent_history", "opponent_climber"),
                          ("opponent_motive", "opponent_monopoly"),
                          ("opening_pattern", "opening_debt")]:
        assert pick(client, url, field, option).status_code == 200
    blueprint = client.post(url + '/compile-blueprint').json()['blueprint']
    bp_id = blueprint['blueprint_id']
    assert client.post('/api/story-builder/blueprints/' + bp_id + '/confirm',
                       json={'version': blueprint['version']}).status_code == 200
    base = '/api/story-builder/blueprints/' + bp_id + '/adventures/' + str(blueprint['version'])
    scene = client.post(base).json()
    return client, base, bp_id, scene


def choose(client, base: str, scene: dict, choice_id: str) -> dict:
    result = client.post(base + '/choices', json={'revision': scene['state']['revision'],
                                                 'choice_id': choice_id})
    assert result.status_code == 200, result.text
    return result.json()


def test_new_journey_runs_on_story_engine_without_new_adventure_fields(tmp_path: Path) -> None:
    client, base, bp_id, scene = start_journey(tmp_path)
    assert scene['state']['rules_version'] == 3
    assert scene['state']['supplies'] == 2 and scene['state']['revision'] == 0
    assert scene['title'] == "期限之前"
    state_file = tmp_path / "novel" / "authoring" / "story_engine" / "state" / bp_id / "v000001.json"
    assert state_file.is_file()
    payload = json.loads(state_file.read_text(encoding='utf-8'))
    assert payload['story_state']['flags']['journey_revision'] == 0

    adventure_file = (tmp_path / "novel" / "authoring" / "story_builder" / "adventures"
                      / bp_id / "v000001.json")
    mirrored = json.loads(adventure_file.read_text(encoding='utf-8'))
    assert set(mirrored) == LEGACY_FIELDS

    scene = choose(client, base, scene, 'help')
    assert scene['state']['ally'] is True and scene['state']['supplies'] == 1
    scene = choose(client, base, scene, 'ally')
    scene = choose(client, base, scene, 'expose')
    assert scene['state']['revision'] == 3 and scene['completed'] is True
    scene = choose(client, base, scene, 'continue_trace')
    assert scene['title'] == "先兑现谁的承诺"
    scene = choose(client, base, scene, 'honor_partner')
    assert scene['state']['trust'] == 1 and scene['state']['debt'] == 0
    scene = choose(client, base, scene, 'seek_receipt')
    assert scene['state']['facts'] == ['receipt']
    scene = choose(client, base, scene, 'verify_order')
    assert scene['state']['facts'] == ['receipt', 'diversion_verified']
    scene = choose(client, base, scene, 'end_public')
    assert scene['completed'] is True and scene['choices'] == []
    assert scene['state']['arc_finished'] is True
    assert scene['title'] == "篇章已收束"
    # 旧形状镜像同步更新，旧读者仍可读取。
    mirrored = json.loads(adventure_file.read_text(encoding='utf-8'))
    assert set(mirrored) == LEGACY_FIELDS
    assert mirrored['revision'] == 8 and mirrored['arc_finished'] is True
    assert mirrored['facts'] == ['receipt', 'diversion_verified']
    final_state = json.loads(state_file.read_text(encoding='utf-8'))['story_state']
    assert final_state['effect_log'][-1]['op'] == 'choice'
    assert final_state['scheduled_events'] if 'scheduled_events' in final_state else True


def test_existing_adventure_save_keeps_legacy_path(tmp_path: Path) -> None:
    # 先在没有内容包的项目里创建旧规则旅程（rules_version 2）。
    client, base, bp_id, scene = start_journey(tmp_path, with_pack=False)
    assert scene['state']['rules_version'] == 2
    legacy_scene = choose(client, base, scene, 'clue')
    assert set(json.loads((tmp_path / "novel" / "authoring" / "story_builder" / "adventures"
                           / bp_id / "v000001.json").read_text(encoding='utf-8'))) == LEGACY_FIELDS
    # 之后即使加入内容包，既有存档仍走兼容路径，不被新引擎改写。
    install_pack(tmp_path)
    resumed = client.post(base).json()
    assert resumed['state']['rules_version'] == 2
    assert resumed['state']['clue'] is True
    assert resumed['state']['revision'] == 1
    assert resumed['text'] == legacy_scene['text']
    # 旧存档不会被新引擎接管：不会为它创建 StoryState 文件。
    assert not (tmp_path / "novel" / "authoring" / "story_engine" / "state" / bp_id).exists()


def test_branch_replays_through_story_engine(tmp_path: Path) -> None:
    from uuid import uuid4
    client, base, bp_id, scene = start_journey(tmp_path)
    scene = choose(client, base, scene, 'help')
    scene = choose(client, base, scene, 'wait')
    fork = client.post(base + '/branches', json={'at_revision': 1, 'expected_revision': 2,
                                                'request_id': str(uuid4())})
    assert fork.status_code == 200, fork.text
    branch = fork.json()
    assert branch['state']['revision'] == 1 and branch['state']['ally'] is True
    branch_base = base + '/branches/' + branch['state']['branch_id']
    assert client.post(branch_base).json()['state']['revision'] == 1
    branch_state = (tmp_path / "novel" / "authoring" / "story_engine" / "state" / bp_id
                    / f"v000001_{branch['state']['branch_id']}.json")
    assert branch_state.is_file()
    # 分支推进不影响主干。
    moved = choose(client, branch_base, branch, 'ally')
    assert moved['state']['revision'] == 2
    assert client.post(base).json()['state']['revision'] == 2
