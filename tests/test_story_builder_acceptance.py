import pytest

from test_story_builder_design_tree import make_client, complete_base, pick
from novelforge.story_builder.adventures import Adventure, AdventureEngine


@pytest.mark.parametrize('world,experience,pattern', [
    ('world_silicon_mmo', 'experience_growth_adventure', 'opening_survival'),
    ('world_cultivation_realms', 'experience_mystery_exploration', 'opening_mystery'),
    ('world_modern_supernatural', 'experience_relationship_drama', 'opening_debt'),
])
def test_reachable_story_states_have_no_dead_end_or_free_reveal(tmp_path, world, experience, pattern):
    client, url = make_client(tmp_path, world, experience)
    complete_base(client, url)
    pick(client, url, 'opening_pattern', pattern)
    bp = client.post(url + '/compile-blueprint').json()['blueprint']
    base = '/api/story-builder/blueprints/' + bp['blueprint_id']
    assert client.post(base + '/confirm', json={'version': 1}).status_code == 200
    engine = AdventureEngine(tmp_path)
    # 只枚举规则状态，不把每个测试分支写入作者文件。
    engine._save = lambda state: None
    queue = [Adventure(blueprint_id=bp['blueprint_id'], blueprint_version=1, rules_version=2)]
    seen, endings = set(), set()
    while queue:
        state = queue.pop()
        key = (state.revision, state.supplies, state.ally, state.clue, state.trust, state.debt, tuple(state.facts), state.arc_finished,
               state.history[-1]['choice_id'] if state.history else '')
        if key in seen:
            continue
        seen.add(key)
        scene = engine.view(state)
        assert scene['text'] and state.supplies >= 0 and state.debt >= 0
        assert state.revision == len(state.history) <= 8
        if not scene['choices']:
            assert scene['completed'] and state.arc_finished
            endings.add(state.history[-1]['choice_id'])
        for choice in scene['choices']:
            if choice['id'] == 'end_public':
                assert 'diversion_verified' in state.facts
            if choice['id'] == 'verify_order':
                assert 'receipt' in state.facts
            if choice['id'] == 'end_cooperate':
                assert state.trust > 0
            successor = Adventure.model_validate(engine.choose_design(state.model_copy(deep=True), scene, choice)['state'])
            assert successor.revision == state.revision + 1
            queue.append(successor)
    assert {'settle', 'end_public', 'end_depart', 'end_cooperate'} <= endings
    assert len(seen) >= 50
