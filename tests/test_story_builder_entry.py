from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from novelforge.api.story_builder_routes import install_story_builder_api
from novelforge.story_builder import load_story_catalog


@pytest.fixture
def client(tmp_path):
    app = FastAPI()
    install_story_builder_api(app, tmp_path, catalog=load_story_catalog(Path(__file__).resolve().parents[1]))
    return TestClient(app)


@pytest.mark.parametrize('entry', ['worldview', 'protagonist', 'major_events'])
def test_free_entry_keeps_seed_through_blueprint(client, entry):
    response = client.post('/api/story-builder/sessions', json={'entry_step': entry})
    assert response.status_code == 201
    state = response.json()['session']
    assert state['current_step'] == entry
    url = '/api/story-builder/sessions/' + state['session_id']
    rec = client.post(url + '/recommendations', json={}).json()['recommendation']
    assert rec['can_continue']
    assert not any(c['code'] == 'STEP_LOCKED' for c in rec['conflicts'])
    seed = '追索失落家书的渡口记录员，在封港当天发现自己的署名'
    selection = {'option_ids': ['world_cultivation_realms']} if entry == 'worldview' else {'custom_texts': [seed]}
    response = client.post(url + '/selections', json={'step': entry, 'expected_selection_version': 0, **selection})
    assert response.status_code == 200, response.text
    assert response.json()['session']['current_step'] == 'reader_experience'
    for _ in range(12):
        state = client.get(url).json()['session']
        if len(state['completed_steps']) == 10 and not state['needs_review_steps']:
            break
        step = state['current_step']
        if step == entry:
            values = selection
        else:
            rec = client.post(url + '/recommendations', json={}).json()['recommendation']
            options = [r['option_id'] for r in rec['recommendations'] if r['option_id']]
            values = {'option_ids': options[:1]} if options else {'custom_texts': ['沿既定线索继续调查']}
        response = client.post(url + '/selections', json={'step': step, 'expected_selection_version': state['selection_version'], **values})
        assert response.status_code == 200, response.text
    else:
        pytest.fail('自由起点未能回到完整设定流程')
    blueprint = client.post(url + '/compile-blueprint')
    assert blueprint.status_code == 200, blueprint.text
    assert not blueprint.json()['blueprint']['unresolved_conflicts']
    if entry != 'worldview':
        assert seed in blueprint.text


def test_entry_does_not_bypass_option_requirements_or_other_steps(client):
    state = client.post('/api/story-builder/sessions', json={'entry_step': 'protagonist'}).json()['session']
    url = '/api/story-builder/sessions/' + state['session_id']
    for step, option in [('protagonist', 'protagonist_nonhuman_awakening'), ('background', 'background_ruined_board')]:
        response = client.post(url + '/selections', json={'step': step, 'option_ids': [option], 'expected_selection_version': 0})
        assert response.status_code == (409 if step == 'protagonist' else 422), response.text
    assert client.get(url).json()['session']['selection_version'] == 0
    assert client.post('/api/story-builder/sessions', json={'entry_step': 'author_boundaries'}).status_code == 422
