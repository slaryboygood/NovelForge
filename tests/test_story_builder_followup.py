from test_story_builder_design_tree import make_client, complete_base, pick


def opening(tmp_path):
    client, url = make_client(tmp_path)
    complete_base(client, url)
    pick(client, url, 'opening_pattern', 'opening_mystery')
    bp = client.post(url + '/compile-blueprint').json()['blueprint']
    base = '/api/story-builder/blueprints/' + bp['blueprint_id']
    client.post(base + '/confirm', json={'version': 1})
    game = base + '/adventures/1'
    for revision, choice in enumerate(['clue', 'proof', 'expose']):
        assert client.post(game + '/choices', json={'revision': revision, 'choice_id': choice}).status_code == 200
    return client, game


def act(client, game, choice):
    scene = client.post(game).json()
    return client.post(game + '/choices', json={'revision': scene['state']['revision'], 'choice_id': choice})


def test_followup_preserves_resources_and_supports_ending(tmp_path):
    client, game = opening(tmp_path)
    assert client.post(game).json()['state']['supplies'] == 2
    result = act(client, game, 'continue_recover').json()
    assert result['state']['supplies'] == 3 and result['state']['debt'] == 1
    result = act(client, game, 'honor_partner').json()
    assert result['state']['supplies'] == 2 and result['state']['trust'] == 1 and result['state']['debt'] == 0
    assert act(client, game, 'verify_order').status_code == 422
    result = act(client, game, 'seek_receipt').json()
    assert result['state']['facts'] == ['receipt']
    assert 'diversion_verified' not in result['state']['facts']
    result = act(client, game, 'verify_order').json()
    assert 'diversion_verified' in result['state']['facts']
    result = act(client, game, 'end_public').json()
    assert result['completed'] and result['choices'] == []
    assert result['state']['revision'] == 8
    assert act(client, game, 'continue_recover').status_code == 422


def test_no_evidence_no_reveal_and_relation_consequences(tmp_path):
    client, game = opening(tmp_path)
    before = client.post(game).json()
    assert '没有同步公开记录' not in str(before)
    assert '没有同步公开记录' in client.get(game + '/author-plan').json()['truth']
    assert client.post(game).json() == before
    act(client, game, 'continue_trace')
    result = act(client, game, 'go_alone').json()
    assert result['state']['trust'] == -1
    act(client, game, 'accept_private')
    assert act(client, game, 'verify_order').status_code == 422
    result = act(client, game, 'record_limits').json()
    assert 'end_public' not in [choice['id'] for choice in result['choices']]
    assert 'end_cooperate' not in [choice['id'] for choice in result['choices']]
    assert result['state']['facts'] == []
    assert act(client, game, 'end_depart').json()['completed']


def test_early_settle_and_fork_restore_followup_facts(tmp_path):
    from uuid import uuid4
    client, game = opening(tmp_path)
    original = act(client, game, 'settle').json()
    assert original['completed'] and not original['choices']
    fork = client.post(game + '/branches', json={'at_revision': 3, 'expected_revision': 4, 'request_id': str(uuid4())}).json()
    branch = game + '/branches/' + fork['state']['branch_id']
    assert not fork['state']['arc_finished']
    for choice in ['continue_recover', 'honor_partner', 'seek_receipt', 'verify_order', 'end_public']:
        assert act(client, branch, choice).status_code == 200
    fork2 = client.post(game + '/branches', json={'parent_branch': fork['state']['branch_id'], 'at_revision': 6, 'expected_revision': 8, 'request_id': str(uuid4())}).json()
    assert fork2['state']['facts'] == ['receipt']
    assert fork2['state']['trust'] == 1 and fork2['state']['debt'] == 0
    assert not fork2['state']['arc_finished']
    assert client.post(game).json() == original
