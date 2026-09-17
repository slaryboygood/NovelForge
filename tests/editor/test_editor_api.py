"""V4-06 §52：最小 REST 链路（thin routes → application.services.editor）。"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from novelforge.api.editor_routes import install_editor_api

from editor_support import current_payload, editor_stack, scripted

BASE = "/api/story-builder/editor"


def _client(stack: dict, *, gateway: object = ...) -> TestClient:
    app = FastAPI()
    install_editor_api(app, stack["root"],
                       gateway=stack["gateway"] if gateway is ... else gateway,
                       memory=stack["memory"])
    return TestClient(app)


def test_get_node_and_revisions(tmp_path: Path) -> None:
    stack = editor_stack(tmp_path)
    client = _client(stack)
    node = client.get(f"{BASE}/nodes/ch_001", params={"novel_id": "novel_alpha"})
    assert node.status_code == 200
    assert node.json()["node"]["node_id"] == "ch_001"
    assert node.json()["editable_fields"]
    revisions = client.get(f"{BASE}/nodes/ch_001/revisions",
                           params={"novel_id": "novel_alpha"})
    assert revisions.status_code == 200
    assert revisions.json()["current_revision"] == 1


def test_unknown_node_returns_404_without_traceback(tmp_path: Path) -> None:
    stack = editor_stack(tmp_path)
    response = _client(stack).get(f"{BASE}/nodes/ch_999",
                                  params={"novel_id": "novel_alpha"})
    assert response.status_code == 404
    detail = response.json()["detail"]
    assert detail["code"] == "EDITOR_NODE_NOT_FOUND"
    assert "traceback" not in str(detail).lower()


def test_patch_then_conflict(tmp_path: Path) -> None:
    stack = editor_stack(tmp_path)
    client = _client(stack)
    patched = client.patch(f"{BASE}/nodes/ch_001", json={
        "novel_id": "novel_alpha", "expected_revision": 1,
        "changes": {"goal": "确认维修队列是否被人为改写"}, "reason": "作者修改"})
    assert patched.status_code == 200
    assert patched.json()["status"] == "applied"
    assert patched.json()["revision"] == 2
    conflict = client.patch(f"{BASE}/nodes/ch_001", json={
        "novel_id": "novel_alpha", "expected_revision": 1,
        "changes": {"goal": "基于旧版本的修改"}})
    assert conflict.status_code == 409
    assert conflict.json()["detail"]["code"] == "EDITOR_REVISION_CONFLICT"
    assert conflict.json()["detail"]["details"]["actual_revision"] == 2


def test_protected_field_returns_409(tmp_path: Path) -> None:
    stack = editor_stack(tmp_path)
    response = _client(stack).patch(f"{BASE}/nodes/sc_001_02", json={
        "novel_id": "novel_alpha", "expected_revision": 1,
        "changes": {"chapter_id": "ch_002"}})
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "EDITOR_PRESERVE_VIOLATION"


def test_diff_accept_reject_restore_endpoints(tmp_path: Path) -> None:
    stack = editor_stack(tmp_path)
    client = _client(stack)
    client.patch(f"{BASE}/nodes/ch_001", json={
        "novel_id": "novel_alpha", "expected_revision": 1,
        "changes": {"title": "标题二"}})
    diff = client.get(f"{BASE}/nodes/ch_001/diff",
                      params={"novel_id": "novel_alpha", "from_revision": 1,
                              "to_revision": 2})
    assert diff.status_code == 200
    assert diff.json()["changed_fields"] == ["title"]
    rejected = client.post(f"{BASE}/nodes/ch_001/reject",
                           json={"novel_id": "novel_alpha", "revision": 2,
                                 "reason": "先不要"})
    assert rejected.status_code == 200
    assert rejected.json()["status"] == "recorded"
    accepted = client.post(f"{BASE}/nodes/ch_001/accept",
                           json={"novel_id": "novel_alpha", "expected_revision": 2,
                                 "reason": "采用"})
    assert accepted.status_code == 200
    assert accepted.json()["decision"] == "accepted"
    restored = client.post(f"{BASE}/nodes/ch_001/restore",
                           json={"novel_id": "novel_alpha", "from_revision": 1,
                                 "expected_revision": 3})
    assert restored.status_code == 200
    assert restored.json()["restored_from"] == 1
    assert restored.json()["revision"] == 4


def test_rewrite_endpoint_uses_injected_gateway(tmp_path: Path) -> None:
    stack = editor_stack(tmp_path)
    scripted(stack, {**current_payload(stack, "ch_001"), "turn": "接口改写的转折"})
    client = _client(stack)
    response = client.post(f"{BASE}/nodes/ch_001/rewrite", json={
        "novel_id": "novel_alpha", "expected_revision": 1,
        "target_fields": ["turn"], "instruction": "把转折写具体"})
    assert response.status_code == 200
    assert response.json()["changed_fields"] == ["turn"]
    assert response.json()["target_fields"] == ["turn"]


def test_rewrite_without_gateway_is_rejected(tmp_path: Path) -> None:
    stack = editor_stack(tmp_path)
    response = _client(stack, gateway=None).post(
        f"{BASE}/nodes/ch_001/rewrite",
        json={"novel_id": "novel_alpha", "expected_revision": 1,
              "target_fields": ["turn"], "instruction": "改写"})
    assert response.status_code == 422
    assert response.json()["detail"]["details"]["code"] == "EDITOR_AI_UNAVAILABLE"


def test_quality_endpoint_marks_historical(tmp_path: Path) -> None:
    stack = editor_stack(tmp_path)
    stack["service"].evaluate("sc_001_02")
    stack["service"].patch("sc_001_02", {"story_function": ["advance_plot", "decision"]},
                           expected_revision=1)
    response = _client(stack).get(f"{BASE}/nodes/sc_001_02/quality",
                                  params={"novel_id": "novel_alpha"})
    assert response.status_code == 200
    payload = response.json()
    assert payload["current_revision"] == 2
    assert payload["historical_issues"]
    assert all(row["historical"] for row in payload["historical_issues"])


def test_same_node_ids_in_two_novels_stay_isolated(tmp_path: Path) -> None:
    """§64：两本作品 node_id 完全相同，也必须完全隔离。"""

    from editor_support import build_broken_blueprint, build_novel, WEAPON_RULE_TEXT

    stack = editor_stack(tmp_path)
    build_novel(tmp_path, "novel_beta", title="贝塔", fact_text=WEAPON_RULE_TEXT)
    build_broken_blueprint(tmp_path, "novel_beta")
    client = _client(stack)
    patched = client.patch(f"{BASE}/nodes/ch_001", json={
        "novel_id": "novel_alpha", "expected_revision": 1,
        "changes": {"goal": "阿尔法自己的目标"}})
    assert patched.status_code == 200 and patched.json()["revision"] == 2
    beta = client.get(f"{BASE}/nodes/ch_001", params={"novel_id": "novel_beta"})
    assert beta.status_code == 200
    assert beta.json()["node"]["payload"]["goal"] == "关系进一步发展"
    assert beta.json()["view"]["revision"] == 1
    beta_revisions = client.get(f"{BASE}/nodes/ch_001/revisions",
                               params={"novel_id": "novel_beta"})
    assert beta_revisions.json()["current_revision"] == 1
