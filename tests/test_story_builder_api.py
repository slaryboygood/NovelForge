from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from novelforge.api.story_builder_routes import install_story_builder_api
from novelforge.story_builder import load_story_catalog
from novelforge.story_builder import STORY_STEP_ORDER, DeterministicRecommendationEngine


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def client_for(tmp_path: Path) -> TestClient:
    app = FastAPI()
    install_story_builder_api(
        app,
        tmp_path,
        catalog=load_story_catalog(PROJECT_ROOT),
    )
    return TestClient(app)


def test_catalog_and_step_endpoints_are_chinese(tmp_path: Path) -> None:
    client = client_for(tmp_path)

    catalog = client.get("/api/story-builder/catalogs")
    step = client.get("/api/story-builder/steps/worldview")

    assert catalog.status_code == 200
    assert catalog.json()["language"] == "zh-CN"
    assert len(catalog.json()["steps"]) == 10
    assert step.status_code == 200
    assert step.json()["step"]["title"] == "世界观"
    assert len(step.json()["options"]) == 3


def test_saved_stories_are_isolated_and_listed(tmp_path):
    client = client_for(tmp_path)
    first = client.post('/api/story-builder/sessions', json={'project_id': 'novel_project'}).json()['session']['session_id']
    second = client.post('/api/story-builder/sessions', json={'project_id': 'novel_project'}).json()['session']['session_id']
    client.post('/api/story-builder/sessions', json={'project_id': 'another_project'})
    listed = client.get('/api/story-builder/sessions?project_id=novel_project').json()['sessions']
    assert {item['session_id'] for item in listed} == {first, second}
    assert client.get('/api/story-builder/sessions/' + first).json()['session']['selection_version'] == 0


def test_session_api_runs_create_recommend_select_back_and_resume(tmp_path: Path) -> None:
    client = client_for(tmp_path)
    created = client.post(
        "/api/story-builder/sessions",
        json={"project_id": "silicon_rise", "session_id": "session_api_001"},
    )
    assert created.status_code == 201
    assert created.json()["session"]["current_step"] == "reader_experience"

    first_recommendation = client.post(
        "/api/story-builder/sessions/session_api_001/recommendations",
        json={},
    )
    assert first_recommendation.status_code == 200
    assert len(first_recommendation.json()["recommendation"]["recommendations"]) == 3

    selected = client.post(
        "/api/story-builder/sessions/session_api_001/selections",
        json={
            "step": "reader_experience",
            "option_ids": ["experience_growth_adventure"],
            "expected_selection_version": 0,
        },
    )
    assert selected.status_code == 200
    assert selected.json()["session"]["current_step"] == "worldview"
    assert selected.json()["selected"][0]["display_name"] == "成长冒险"

    worldview = client.post(
        "/api/story-builder/sessions/session_api_001/recommendations",
        json={},
    )
    ids = [
        item["option_id"]
        for item in worldview.json()["recommendation"]["recommendations"]
    ]
    assert ids == ["world_silicon_mmo", "world_cultivation_realms", "world_modern_supernatural"]

    returned = client.post(
        "/api/story-builder/sessions/session_api_001/back",
        json={"target_step": "reader_experience", "expected_selection_version": 1},
    )
    assert returned.status_code == 200
    assert returned.json()["session"]["current_step"] == "reader_experience"

    resumed = client.get(
        "/api/story-builder/sessions/latest",
        params={"project_id": "silicon_rise"},
    )
    assert resumed.status_code == 200
    assert resumed.json()["session"]["session_id"] == "session_api_001"


def test_api_persists_across_router_recreation(tmp_path: Path) -> None:
    first = client_for(tmp_path)
    first.post(
        "/api/story-builder/sessions",
        json={"project_id": "silicon_rise", "session_id": "session_api_001"},
    )

    second = client_for(tmp_path)
    loaded = second.get("/api/story-builder/sessions/session_api_001")

    assert loaded.status_code == 200
    assert loaded.json()["session"]["project_id"] == "silicon_rise"


def test_api_returns_chinese_conflict_without_traceback(tmp_path: Path) -> None:
    client = client_for(tmp_path)
    client.post(
        "/api/story-builder/sessions",
        json={"project_id": "silicon_rise", "session_id": "session_api_001"},
    )
    client.post(
        "/api/story-builder/sessions/session_api_001/selections",
        json={
            "step": "reader_experience",
            "option_ids": ["experience_growth_adventure"],
            "expected_selection_version": 0,
        },
    )

    client.post('/api/story-builder/sessions/session_api_001/selections', json={
        'step': 'worldview', 'option_ids': ['world_modern_supernatural'], 'expected_selection_version': 1,
    })
    conflict = client.post(
        "/api/story-builder/sessions/session_api_001/selections",
        json={
            "step": "background",
            "option_ids": ["background_ruined_board"],
            "expected_selection_version": 2,
        },
    )

    assert conflict.status_code == 409
    payload = conflict.json()["detail"]
    assert payload["code"] == "SELECTION_CONFLICT"
    assert "当前选择" in payload["message"]
    assert "traceback" not in str(payload).lower()


def test_api_stale_version_and_unknown_session_are_safe(tmp_path: Path) -> None:
    client = client_for(tmp_path)
    client.post(
        "/api/story-builder/sessions",
        json={"project_id": "silicon_rise", "session_id": "session_api_001"},
    )

    stale = client.post(
        "/api/story-builder/sessions/session_api_001/save",
        json={"expected_selection_version": 2},
    )
    missing = client.get("/api/story-builder/sessions/session_missing")

    assert stale.status_code == 409
    assert stale.json()["detail"]["code"] == "SESSION_VERSION_CONFLICT"
    assert missing.status_code == 404
    assert missing.json()["detail"]["code"] == "SESSION_NOT_FOUND"


def test_history_endpoint_keeps_previous_selection(tmp_path: Path) -> None:
    client = client_for(tmp_path)
    client.post(
        "/api/story-builder/sessions",
        json={"project_id": "silicon_rise", "session_id": "session_api_001"},
    )
    client.post(
        "/api/story-builder/sessions/session_api_001/selections",
        json={
            "step": "reader_experience",
            "option_ids": ["experience_growth_adventure"],
            "expected_selection_version": 0,
        },
    )

    history = client.get("/api/story-builder/sessions/session_api_001/history")

    assert history.status_code == 200
    assert [item["selection_version"] for item in history.json()["versions"]] == [0, 1]


def test_api_compiles_and_confirms_traceable_blueprint(tmp_path: Path) -> None:
    client = client_for(tmp_path)
    catalog = load_story_catalog(PROJECT_ROOT)
    rules = DeterministicRecommendationEngine(catalog)
    session_id = "session_api_blueprint"
    client.post("/api/story-builder/sessions", json={"project_id": "silicon_rise", "session_id": session_id})
    selected_ids: list[str] = []
    for version, step in enumerate(STORY_STEP_ORDER):
        result = rules.recommend(
            step,
            selected_ids,
            custom_selection_counts={},
            based_on_version=version,
        )
        option_id = result.recommendations[0].option_id
        selected_ids.append(option_id)
        response = client.post(
            f"/api/story-builder/sessions/{session_id}/selections",
            json={"step": step, "option_ids": [option_id], "expected_selection_version": version},
        )
        assert response.status_code == 200

    compiled = client.post(f"/api/story-builder/sessions/{session_id}/compile-blueprint")
    assert compiled.status_code == 200
    blueprint = compiled.json()["blueprint"]
    assert len(blueprint["sections"]) == 10
    assert all(item["source_selection_ids"] for item in blueprint["sections"])

    confirmed = client.post(
        f"/api/story-builder/blueprints/{blueprint['blueprint_id']}/confirm",
        json={"version": blueprint["version"]},
    )
    assert confirmed.status_code == 200
    assert confirmed.json()["blueprint"]["status"] == "CONFIRMED"

    expected = [("BOOK", 1), ("VOLUME", 3), ("ARC", 6), ("CHAPTER", 24)]
    for level, count in expected:
        drafted = client.post(
            f"/api/story-builder/blueprints/{blueprint['blueprint_id']}/outlines/{level}",
            json={"blueprint_version": blueprint["version"]},
        )
        assert drafted.status_code == 200
        package = drafted.json()["outline"]
        assert len(package["items"]) == count
        accepted = client.post(
            f"/api/story-builder/outlines/{package['package_id']}/confirm",
            json={"version": package["version"]},
        )
        assert accepted.status_code == 200

    chain = client.get(f"/api/story-builder/blueprints/{blueprint['blueprint_id']}/outlines")
    assert [item["status"] for item in chain.json()["outlines"]] == ["CONFIRMED"] * 4
