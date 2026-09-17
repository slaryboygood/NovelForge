from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError

from novelforge.api.story_builder_routes import install_story_builder_api
from novelforge.story_builder import load_story_catalog
from novelforge.story_builder.models import StoryChoiceCatalog
from novelforge.story_builder import STORY_STEP_ORDER


ROOT = Path(__file__).resolve().parents[1]


def make_client(tmp_path, world="world_cultivation_realms", experience="experience_growth_adventure"):
    app = FastAPI()
    install_story_builder_api(app, tmp_path, catalog=load_story_catalog(ROOT))
    client = TestClient(app)
    result = client.post('/api/story-builder/sessions', json={"project_id": "tree_test"}).json()
    url = '/api/story-builder/sessions/' + result['session']['session_id']
    for step, option, version in [("reader_experience", experience, 0), ("worldview", world, 1)]:
        result = client.post(url + '/selections', json={"step": step, "option_ids": [option], "expected_selection_version": version})
        assert result.status_code == 200
    return client, url


def pick(client, url, field, option=None, text=""):
    revision = client.get(url).json()['session']['selection_version']
    return client.post(url + '/design/' + field, json={"option_id": option, "custom_text": text, "expected_selection_version": revision})


def node(result, key):
    return next(item for item in result['design_tree'] if item['id'] == key)


@pytest.mark.parametrize('world,society,region,crisis', [
    ('world_cultivation_realms', 'society_sect', 'region_medicine', 'crisis_quota'),
    ('world_cultivation_realms', 'society_frontier', 'region_ferry', 'crisis_missing'),
    ('world_silicon_mmo', 'society_grid', 'region_cooling', 'crisis_failure'),
    ('world_silicon_mmo', 'society_salvage', 'region_scrap', 'crisis_missing'),
])
def test_four_background_paths(tmp_path, world, society, region, crisis):
    client, url = make_client(tmp_path, world)
    assert pick(client, url, 'home_region', region).status_code == 422
    for field, option in [('society', society), ('home_region', region), ('social_position', 'position_worker'), ('present_crisis', crisis)]:
        result = pick(client, url, field, option)
        assert result.status_code == 200
        assert not node(result.json(), field)['needs_review']
    assert len(client.get(url).json()['session']['design_choices']) == 4


def test_review_is_targeted_and_preserves_old_values(tmp_path):
    client, url = make_client(tmp_path)
    pick(client, url, 'society', 'society_sect')
    pick(client, url, 'home_region', 'region_medicine')
    pick(client, url, 'social_position', 'position_worker')
    pick(client, url, 'present_crisis', 'crisis_missing')
    result = pick(client, url, 'social_position', 'position_keeper').json()
    assert not node(result, 'home_region')['needs_review']
    assert node(result, 'present_crisis')['needs_review']
    assert node(result, 'present_crisis')['selection']['option_id'] == 'crisis_missing'
    assert not node(pick(client, url, 'present_crisis', 'crisis_missing').json(), 'present_crisis')['needs_review']
    result = pick(client, url, 'society').json()
    assert node(result, 'home_region')['needs_review']
    assert node(result, 'present_crisis')['needs_review']


def test_invalid_choice_stale_revision_and_custom(tmp_path):
    client, url = make_client(tmp_path)
    assert pick(client, url, 'society', 'society_grid').status_code == 422
    result = pick(client, url, 'society', text='作者自己的秩序').json()
    assert node(result, 'society')['selection']['custom_text'] == '作者自己的秩序'
    assert client.post(url + '/design/society', json={"expected_selection_version": 2, "option_id": 'society_sect'}).status_code == 409
    assert pick(client, url, 'society', 'society_sect', '两个值').status_code == 422


def test_catalog_rejects_unknown_dependencies():
    data = load_story_catalog(ROOT).catalog.model_dump()
    data['design_fields'][0]['depends_on'] = ['made_up_field']
    with pytest.raises(ValidationError):
        StoryChoiceCatalog.model_validate(data)


def test_background_reaches_blueprint_and_event(tmp_path):
    client, url = make_client(tmp_path, 'world_silicon_mmo')
    for field, option in [('society', 'society_grid'), ('home_region', 'region_cooling'), ('social_position', 'position_worker'), ('present_crisis', 'crisis_failure')]:
        assert pick(client, url, field, option).status_code == 200
    for step in STORY_STEP_ORDER[2:]:
        recommendation = client.post(url + '/recommendations', json={"step": step}).json()
        option = recommendation['recommendation']['recommendations'][0]['option_id']
        version = client.get(url).json()['session']['selection_version']
        assert client.post(url + '/selections', json={"step": step, "option_ids": [option], "expected_selection_version": version}).status_code == 200
    bp = client.post(url + '/compile-blueprint').json()['blueprint']
    assert '冷却塔' in bp['design_summaries']['home_region']
    base = '/api/story-builder/blueprints/' + bp['blueprint_id']
    assert client.post(base + '/confirm', json={"version": bp['version']}).status_code == 200
    scene = client.post(base + '/adventures/1').json()
    assert '冷却塔闸口' in scene['text']
    assert scene['title'] == '出口即将关闭'
    assert scene['goal'] == '保住住处与居民'
    assert 'clue' not in [item['id'] for item in scene['choices']]
    pick(client, url, 'social_position', 'position_keeper')
    bp2 = client.post(url + '/compile-blueprint').json()['blueprint']
    assert any(item['code'] == 'DESIGN_NEEDS_REVIEW' for item in bp2['unresolved_conflicts'])
    assert client.post(base + '/confirm', json={"version": bp2['version']}).status_code == 422


def complete_base(client, url):
    for step in STORY_STEP_ORDER[2:]:
        option = client.post(url + '/recommendations', json={"step": step}).json()['recommendation']['recommendations'][0]['option_id']
        version = client.get(url).json()['session']['selection_version']
        assert client.post(url + '/selections', json={"step": step, "option_ids": [option], "expected_selection_version": version}).status_code == 200


def test_resource_design_does_not_grant_inventory_and_reviews_only_dependents(tmp_path):
    client, url = make_client(tmp_path)
    complete_base(client, url)
    assert pick(client, url, 'ability_cost', 'cost_material').status_code == 422
    assert pick(client, url, 'world_rule', 'rule_exchange').status_code == 200
    assert pick(client, url, 'location_access', 'access_window').status_code == 200
    assert pick(client, url, 'ability_learning', 'learn_practice').status_code == 200
    assert pick(client, url, 'ability_cost', 'cost_material').status_code == 200
    changed = pick(client, url, 'ability_learning', 'learn_mentor').json()
    assert node(changed, 'ability_cost')['needs_review']
    assert not node(changed, 'location_access')['needs_review']
    assert not node(changed, 'world_rule')['needs_review']
    assert pick(client, url, 'ability_cost', 'cost_material').status_code == 200
    bp = client.post(url + '/compile-blueprint').json()['blueprint']
    base = '/api/story-builder/blueprints/' + bp['blueprint_id']
    assert client.post(base + '/confirm', json={'version': bp['version']}).status_code == 200
    game = client.post(base + '/adventures/' + str(bp['version'])).json()['state']
    assert game['supplies'] == 2 and game['facts'] == []
    book = client.post(base + '/outlines/BOOK', json={'blueprint_version': bp['version']}).json()['outline']
    assert '通行' in book['design_sections']['location_access']
    assert any('未确认数量' in note for note in book['items'][0]['must_keep'])


def test_relation_design_preserves_independent_roles_and_unknown_information(tmp_path):
    client, url = make_client(tmp_path)
    complete_base(client, url)
    values = [('companion_history', 'companion_old_friend'), ('companion_motive', 'companion_restore'),
              ('companion_boundary', 'boundary_consent'), ('relationship_tension', 'tension_methods'),
              ('opponent_history', 'opponent_order'), ('opponent_motive', 'opponent_control'),
              ('opponent_boundary', 'opponent_legitimacy'), ('opening_pattern', 'opening_mystery'),
              ('information_release', 'reveal_layers')]
    for field, option in values:
        assert pick(client, url, field, option).status_code == 200
    changed = pick(client, url, 'companion_motive', 'companion_gain').json()
    assert node(changed, 'companion_boundary')['needs_review']
    assert node(changed, 'relationship_tension')['needs_review']
    assert not node(changed, 'opponent_boundary')['needs_review']
    assert not node(changed, 'information_release')['needs_review']
    pick(client, url, 'companion_boundary', 'boundary_consent')
    pick(client, url, 'relationship_tension', 'tension_methods')
    bp = client.post(url + '/compile-blueprint').json()['blueprint']
    base = '/api/story-builder/blueprints/' + bp['blueprint_id']
    client.post(base + '/confirm', json={'version': bp['version']})
    game = base + '/adventures/' + str(bp['version'])
    scene = client.post(game).json()
    assert '旧友' in scene['text'] and '不能替自己答应风险' in scene['text']
    assert scene['state']['facts'] == []
    assert 'end_public' not in [choice['id'] for choice in scene['choices']]


def test_character_history_changes_soft_recommendations(tmp_path):
    client, url = make_client(tmp_path)
    complete_base(client, url)
    result = pick(client, url, 'hero_history', 'hero_failed_rescue').json()
    motives = node(result, 'hero_motive')['options']
    assert next(item for item in motives if item['id'] == 'hero_protect')['recommendation']
    assert all(item['available'] for item in motives)
    pick(client, url, 'hero_motive', 'hero_protect')
    pick(client, url, 'hero_temperament', 'hero_impulsive')
    result = pick(client, url, 'hero_history', 'hero_lone_survivor').json()
    assert node(result, 'hero_temperament')['needs_review']
    assert next(item for item in node(result, 'hero_motive')['options'] if item['id'] == 'hero_belong')['recommendation']
    assert node(result, 'hero_temperament')['selection']['option_id'] == 'hero_impulsive'


def test_roles_keep_independent_histories(tmp_path):
    client, url = make_client(tmp_path)
    complete_base(client, url)
    for field, option in [('companion_history', 'companion_partner'), ('companion_motive', 'companion_gain'), ('companion_temperament', 'companion_reserved'), ('opponent_history', 'opponent_order'), ('opponent_motive', 'opponent_control'), ('opponent_temperament', 'opponent_procedure')]:
        assert pick(client, url, field, option).status_code == 200
    result = pick(client, url, 'companion_history', 'companion_old_friend').json()
    assert node(result, 'companion_motive')['needs_review']
    assert not node(result, 'opponent_temperament')['needs_review']


def test_opening_library_has_examples_and_causal_fields(tmp_path):
    catalog = load_story_catalog(ROOT).catalog
    openings = next(field for field in catalog.design_fields if field.id == 'opening_pattern')
    assert len(openings.options) >= 12
    examples = []
    for option in openings.options:
        assert len(option.examples) >= 2
        assert {'goal', 'cost', 'hook', 'next_a', 'next_b', 'risk'} <= option.effects.keys()
        examples.extend(option.examples)
    assert len(examples) == len(set(examples))
    client, url = make_client(tmp_path)
    assert pick(client, url, 'opening_pattern', 'opening_mystery').status_code == 422
    complete_base(client, url)
    result = pick(client, url, 'opening_pattern', 'opening_mystery')
    assert result.status_code == 200
    bp = client.post(url + '/compile-blueprint').json()['blueprint']
    assert bp['design_effects']['opening_pattern']['goal'] == '验证异常是否真实'
    assert 'opening_survival' not in str(bp['design_choices'])


@pytest.mark.parametrize('world', ['world_cultivation_realms', 'world_silicon_mmo'])
@pytest.mark.parametrize('opening', ['opening_mystery', 'opening_debt', 'opening_survival'])
def test_design_drives_scene_and_preserves_consequences(tmp_path, world, opening):
    client, url = make_client(tmp_path, world)
    complete_base(client, url)
    for field, option in [('hero_history', 'hero_lone_survivor'), ('hero_motive', 'hero_belong'), ('hero_temperament', 'hero_bargainer'), ('opening_pattern', opening)]:
        assert pick(client, url, field, option).status_code == 200
    bp = client.post(url + '/compile-blueprint').json()['blueprint']
    base = '/api/story-builder/blueprints/' + bp['blueprint_id']
    assert client.post(base + '/confirm', json={'version': 1}).status_code == 200
    game = base + '/adventures/1'
    scene = client.post(game).json()
    assert '独自谋生' in scene['text']
    assert ('山门驿站' if world == 'world_cultivation_realms' else '旧能源站') in scene['text']
    assert scene['goal'] == bp['design_effects']['opening_pattern']['goal']
    if opening == 'opening_mystery':
        assert 'supply' not in [item['id'] for item in scene['choices']]
    else:
        assert next(item for item in scene['choices'] if item['id'] == 'supply')['suggested']
    for revision, choice in enumerate(['help', 'ally', 'expose']):
        result = client.post(game + '/choices', json={'revision': revision, 'choice_id': choice})
        assert result.status_code == 200
    result = result.json()
    assert result['completed'] and result['state']['supplies'] == 1
    assert result['success'] in result['text']
    assert client.post(game).json() == result


def test_custom_design_is_not_claimed_as_understood(tmp_path):
    client, url = make_client(tmp_path)
    complete_base(client, url)
    pick(client, url, 'hero_history', text='自定义经历：没有记忆')
    bp = client.post(url + '/compile-blueprint').json()['blueprint']
    base = '/api/story-builder/blueprints/' + bp['blueprint_id']
    client.post(base + '/confirm', json={'version': 1})
    scene = client.post(base + '/adventures/1').json()
    assert any('尚未被事件规则理解' in item for item in scene['warnings'])
    assert '独自谋生' not in scene['text']


def test_concurrent_design_updates_only_one_wins(tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    client, url = make_client(tmp_path)
    def save(option):
        return client.post(url + '/design/society', json={'expected_selection_version': 2, 'option_id': option}).status_code
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(save, ['society_sect', 'society_frontier']))
    assert sorted(results) == [200, 409]
    assert client.get(url).json()['session']['selection_version'] == 3


def test_recommendation_does_not_write_session(tmp_path):
    client, url = make_client(tmp_path)
    before = client.get(url).json()['session']
    assert client.post(url + '/recommendations', json={}).status_code == 200
    assert client.get(url).json()['session'] == before


def test_long_term_planning_unlocks_in_order_and_reviews_only_dependents(tmp_path):
    catalog = load_story_catalog(ROOT).catalog
    # 文档（README、使用说明、数据模型）与实际目录保持同一数量：新增节点时必须同步更新。
    assert len(catalog.design_fields) == 32
    long_term = {field.id for field in catalog.design_fields} & {'main_thread', 'subplot_role', 'payoff_schedule'}
    assert long_term == {'main_thread', 'subplot_role', 'payoff_schedule'}
    options = {option.id for field in catalog.design_fields if field.id in long_term for option in field.options}
    assert {'thread_consequences', 'subplot_character', 'payoff_end'} <= options
    client, url = make_client(tmp_path)
    complete_base(client, url)
    assert pick(client, url, 'main_thread', 'thread_consequences').status_code == 422
    assert pick(client, url, 'story_scope', 'scope_serial').status_code == 200
    assert pick(client, url, 'main_thread', 'thread_consequences').status_code == 200
    assert pick(client, url, 'subplot_role', 'subplot_character').status_code == 200
    assert pick(client, url, 'information_release', 'reveal_layers').status_code == 422
    assert pick(client, url, 'opening_pattern', 'opening_mystery').status_code == 200
    assert pick(client, url, 'information_release', 'reveal_layers').status_code == 200
    assert pick(client, url, 'payoff_schedule', 'payoff_end').status_code == 200
    changed = pick(client, url, 'main_thread', 'thread_inquiry').json()
    assert node(changed, 'subplot_role')['needs_review']
    assert node(changed, 'payoff_schedule')['needs_review']
    assert not node(changed, 'information_release')['needs_review']
    assert not node(changed, 'story_scope')['needs_review']
    assert pick(client, url, 'subplot_role', 'subplot_counterpoint').status_code == 200
    assert pick(client, url, 'payoff_schedule', 'payoff_echo').status_code == 200
    result = client.get(url).json()
    assert not node(result, 'subplot_role')['needs_review']
    assert not node(result, 'payoff_schedule')['needs_review']
    assert result['session']['design_choices']['main_thread']['option_id'] == 'thread_inquiry'
