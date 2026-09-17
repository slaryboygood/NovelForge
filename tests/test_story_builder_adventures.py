from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from novelforge.api.story_builder_routes import install_story_builder_api
from novelforge.story_builder import load_story_catalog, STORY_STEP_ORDER


def setup_game(root: Path):
    app = FastAPI()
    install_story_builder_api(app, root, catalog=load_story_catalog(Path(__file__).resolve().parents[1]))
    client = TestClient(app)
    prefix = "/api/story-builder"
    session = client.post(prefix + "/sessions", json={"project_id": "test_game"}).json()["session"]["session_id"]
    for version, step in enumerate(STORY_STEP_ORDER):
        options = client.post(f"{prefix}/sessions/{session}/recommendations", json={"step": step}).json()
        option = options["recommendation"]["recommendations"][0]["option_id"]
        response = client.post(f"{prefix}/sessions/{session}/selections", json={"step": step, "option_ids": [option], "expected_selection_version": version})
        assert response.status_code == 200
    blueprint = client.post(f"{prefix}/sessions/{session}/compile-blueprint").json()["blueprint"]
    base = f"{prefix}/blueprints/{blueprint['blueprint_id']}"
    assert client.post(base + "/adventures/1").status_code == 409
    assert client.post(base + "/confirm", json={"version": 1}).status_code == 200
    return client, base + "/adventures/1", session


def test_branch_resume_and_double_click(tmp_path):
    client, url, session = setup_game(tmp_path)
    assert client.post(url).json()["state"]["revision"] == 0
    body = {"revision": 0, "choice_id": "help"}
    first = client.post(url + "/choices", json=body).json()
    assert first["state"]["supplies"] == 1
    assert "ally" in [c["id"] for c in first["choices"]]
    assert "pay" not in [c["id"] for c in first["choices"]]
    assert client.post(url + "/choices", json=body).status_code == 409
    assert client.post(url).json() == first
    assert client.post(url + "/choices", json={"revision": 1, "choice_id": "pay"}).status_code == 422
    client.post(url + "/choices", json={"revision": 1, "choice_id": "ally"})
    result = client.post(url + "/choices", json={"revision": 2, "choice_id": "expose"}).json()
    assert result["completed"] and len(result["state"]["history"]) == 3
    assert client.post(url + "/choices", json={"revision": 3, "choice_id": "leave"}).status_code == 422
    assert client.post(url).json() == result
    # 更改源设定后不得继续旧旅程。
    changed = client.post(f"/api/story-builder/sessions/{session}/selections", json={"step": "author_boundaries", "custom_texts": ["禁止死亡"], "expected_selection_version": 10})
    assert changed.status_code == 200
    assert client.post(url).status_code == 409


def test_supplies_branch_does_not_invent_ally(tmp_path):
    client, url, _ = setup_game(tmp_path)
    result = client.post(url + "/choices", json={"revision": 0, "choice_id": "supply"}).json()
    assert result["state"]["supplies"] == 4
    assert "ally" not in [c["id"] for c in result["choices"]]
    client.post(url + "/choices", json={"revision": 1, "choice_id": "pay"})
    result = client.post(url).json()
    assert "expose" not in [c["id"] for c in result["choices"]]
    assert "rescue" in [c["id"] for c in result["choices"]]


def test_fork_replays_inventory_without_overwriting_main(tmp_path):
    from uuid import uuid4
    client, url, _ = setup_game(tmp_path)
    client.post(url + '/choices', json={'revision': 0, 'choice_id': 'help'})
    client.post(url + '/choices', json={'revision': 1, 'choice_id': 'ally'})
    original = client.post(url).json()
    body = {'at_revision': 0, 'expected_revision': 2, 'request_id': str(uuid4())}
    branch = client.post(url + '/branches', json=body)
    assert branch.status_code == 200
    state = branch.json()['state']
    assert state['supplies'] == 2 and not state['ally'] and not state['history']
    branch_url = url + '/branches/' + state['branch_id']
    assert client.post(branch_url + '/choices', json={'revision': 0, 'choice_id': 'supply'}).status_code == 200
    assert client.post(branch_url).json()['state']['supplies'] == 4
    assert client.post(url).json() == original
    assert client.post(url + '/branches', json=body).json()['state']['revision'] == 1
    assert client.post(url + '/branches', json={**body, 'at_revision': 1}).status_code == 409
    assert client.post(url + '/branches', json={**body, 'request_id': str(uuid4()), 'at_revision': 3}).status_code == 422
    listed = client.get(url + '/branches').json()['branches']
    assert {item['branch_id'] for item in listed} == {'main', state['branch_id']}
    assert client.post(url + '/branches/not_valid').status_code == 422
