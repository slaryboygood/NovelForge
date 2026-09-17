from test_story_builder_followup import opening, act
from test_story_builder_design_tree import make_client, complete_base, pick


def test_narrative_design_reaches_outline_without_rewriting_events(tmp_path):
    client, url = make_client(tmp_path)
    complete_base(client, url)
    choices = [('story_scope', 'scope_serial'), ('theme_question', 'theme_truth'),
               ('hero_history', 'hero_lone_survivor'), ('hero_motive', 'hero_belong'),
               ('hero_false_belief', 'belief_alone'), ('narrative_pov', 'pov_first'),
               ('narrative_order', 'order_flashforward'), ('ending_direction', 'ending_reframe'),
               ('opening_pattern', 'opening_mystery')]
    for field, option in choices:
        response = pick(client, url, field, option)
        assert response.status_code == 200, response.text
    bp = client.post(url + '/compile-blueprint').json()['blueprint']
    base = '/api/story-builder/blueprints/' + bp['blueprint_id']
    assert client.post(base + '/confirm', json={'version': bp['version']}).status_code == 200
    game = base + '/adventures/' + str(bp['version'])
    for choice in ['clue', 'proof', 'expose']:
        assert act(client, game, choice).status_code == 200
    before = client.post(game).json()['state']
    package = client.post(game + '/outline', json={'expected_revision': 3}).json()['outline']
    assert package['route_history'] == before['history']
    assert '第一人称限知' in package['items'][0]['pov']
    assert any('结果前置' in note for note in package['items'][0]['must_keep'])
    assert any('放下原目标' in note for note in package['pending_questions'])
    assert client.post(game).json()['state'] == before
    for level in ['VOLUME', 'ARC', 'CHAPTER']:
        assert client.post('/api/story-builder/outlines/' + package['package_id'] + '/confirm', json={'version': package['version']}).status_code == 200
        package = client.post(base + '/outlines/' + level, json={'blueprint_version': bp['version']}).json()['outline']
        assert all('第一人称限知' in item['pov'] for item in package['items'])
    exported = client.get('/api/story-builder/outlines/' + package['package_id'] + '/export?version=1').json()['content']
    assert '真相与安稳' in exported and '结果前置' in exported and '非已发生事实' in exported


def test_route_compiles_four_levels_without_other_branch(tmp_path):
    from uuid import uuid4
    client, game = opening(tmp_path)
    fork = client.post(game + '/branches', json={'at_revision': 0, 'expected_revision': 3, 'request_id': str(uuid4())}).json()
    branch = game + '/branches/' + fork['state']['branch_id']
    for choice in ['help', 'ally', 'leave']:
        assert act(client, branch, choice).status_code == 200
    source = client.post(game + '/outline', json={'branch_id': fork['state']['branch_id'], 'expected_revision': 3})
    assert source.status_code == 200
    book = source.json()['outline']
    assert [item['choice_id'] for item in book['route_history']] == ['help', 'ally', 'leave']
    assert book['pending_questions'] and book['design_sections']
    assert client.post('/api/story-builder/outlines/' + book['package_id'] + '/confirm', json={'version': book['version']}).status_code == 200
    base = '/api/story-builder/blueprints/' + book['blueprint_id']
    for level in ['VOLUME', 'ARC', 'CHAPTER']:
        result = client.post(base + '/outlines/' + level, json={'blueprint_version': book['blueprint_version']})
        assert result.status_code == 200
        package = result.json()['outline']
        assert package['route_source'] == book['route_source']
        assert package['route_history'] == book['route_history']
        assert client.post('/api/story-builder/outlines/' + package['package_id'] + '/confirm', json={'version': package['version']}).status_code == 200
    assert len(package['items']) == 3
    assert package['items'][1]['start_state'] == book['route_history'][0]['result']
    assert package['items'][-1]['end_state'] == book['route_history'][-1]['result']
    assert 'expose' not in str(package['items'])
    act(client, branch, 'continue_trace')
    chain = client.get(base + '/outlines').json()['outlines']
    assert all(item['status'] == 'NEEDS_REVIEW' for item in chain)
    assert client.post('/api/story-builder/outlines/' + package['package_id'] + '/confirm', json={'version': package['version']}).status_code == 409


def test_route_requires_current_completed_stage(tmp_path):
    client, game = opening(tmp_path)
    assert client.post(game + '/outline', json={'expected_revision': 2}).status_code == 409
    act(client, game, 'continue_recover')
    assert client.post(game + '/outline', json={'expected_revision': 4}).status_code == 422


def test_outline_edit_is_versioned_and_exportable(tmp_path):
    client, game = opening(tmp_path)
    package = client.post(game + '/outline', json={'expected_revision': 3}).json()['outline']
    base = '/api/story-builder/outlines/' + package['package_id']
    assert client.post(base + '/confirm', json={'version': 1}).status_code == 200
    item = package['items'][0]['item_id']
    updated = client.put(base + '/items/' + item, json={'expected_version': 1, 'changes': {'title': '作者修改的主线', 'pov': '第一人称'}})
    assert updated.status_code == 200
    updated = updated.json()['outline']
    assert updated['version'] == 2 and updated['status'] == 'DRAFT'
    assert updated['route_source'] == package['route_source']
    assert updated['route_history'] == package['route_history']
    assert client.put(base + '/items/' + item, json={'expected_version': 1, 'changes': {'title': '过期改动'}}).status_code == 409
    assert client.put(base + '/items/' + item, json={'expected_version': 2, 'changes': {'route_source': {}}}).status_code == 422
    assert client.put(base + '/items/' + item, json={'expected_version': 2, 'changes': {'title': ''}}).status_code == 422
    assert client.post(base + '/confirm', json={'version': 1}).status_code == 409
    assert client.post(base + '/confirm', json={'version': 2}).status_code == 200
    exported = client.get(base + '/export?version=2').json()
    assert '作者修改的主线' in exported['content'] and '第一人称' in exported['content']
    assert '状态：已确认' in exported['content']
    old = client.get(base + '/export?version=1').json()
    assert '作者修改的主线' not in old['content']
    next_package = client.post('/api/story-builder/blueprints/' + package['blueprint_id'] + '/outlines/VOLUME', json={'blueprint_version': 1}).json()['outline']
    assert any('作者修改的主线' in value for value in next_package['items'][0]['must_keep'])


def test_long_term_planning_reaches_outline_as_future_plan_only(tmp_path):
    client, url = make_client(tmp_path)
    complete_base(client, url)
    for field, option in [('story_scope', 'scope_serial'), ('main_thread', 'thread_consequences'),
                          ('subplot_role', 'subplot_character'), ('opening_pattern', 'opening_mystery'),
                          ('information_release', 'reveal_layers'), ('payoff_schedule', 'payoff_end'),
                          ('ending_direction', 'ending_open')]:
        assert pick(client, url, field, option).status_code == 200, field
    bp = client.post(url + '/compile-blueprint').json()['blueprint']
    effects = bp['design_effects']['main_thread']
    assert effects['phase_1'] and effects['phase_2'] and effects['phase_3']
    base = '/api/story-builder/blueprints/' + bp['blueprint_id']
    assert client.post(base + '/confirm', json={'version': bp['version']}).status_code == 200
    game = base + '/adventures/' + str(bp['version'])
    for revision, choice in enumerate(['clue', 'proof', 'expose']):
        assert client.post(game + '/choices', json={'revision': revision, 'choice_id': choice}).status_code == 200
    before = client.post(game).json()['state']
    package = client.post(game + '/outline', json={'expected_revision': 3}).json()['outline']
    assert package['route_history'] == before['history']
    assert any(item.startswith('未来阶段建议（未发生，待安排）：') for item in package['pending_questions'])
    assert any('当前路线只覆盖实际推演的阶段' in item for item in package['pending_questions'])
    assert any(item.startswith('作者方向与实际路线的衔接待核对：') for item in package['pending_questions'])
    notes = ' '.join(package['items'][0]['must_keep'])
    assert '长期 · 主线推进' in notes and '长期 · 支线职责' in notes and '长期 · 伏笔回收' in notes
    assert all('非已发生事实' in note for note in package['items'][0]['must_keep'] if '作者设计要求' in note)
    assert not any('阶段之间以结果连接' in entry['result'] for entry in package['route_history'])
    assert before['facts'] == []
    assert client.post(game).json()['state'] == before
