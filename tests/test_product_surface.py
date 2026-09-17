from fastapi.testclient import TestClient

from novelforge.api.app import app


def test_only_story_builder_api_is_exposed():
    paths = [route.path for route in app.routes if route.path.startswith('/api/')]
    assert all(path == '/api/health' or path.startswith('/api/story-builder/') for path in paths)
    assert not any('handoffs' in path for path in paths)
    client = TestClient(app)
    for path in ['/api/chapters', '/api/project', '/api/production', '/api/skills', '/api/promotion']:
        assert client.get(path).status_code == 404
        assert client.post(path, json={}).status_code == 404
    assert client.get('/api/story-builder/catalogs').status_code == 200
