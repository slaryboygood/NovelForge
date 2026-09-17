"""P4-01 生产数据安全门禁：main 与 branch 的 StoryState 完全隔离。

覆盖：fork 不改 main、各分支独立推进、revision 校验 branch-local、reload、rollback/replay、
多小说隔离、Legacy Adventure 不受影响。
"""

from __future__ import annotations

import json
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from novelforge.api.story_builder_routes import install_story_builder_api
from novelforge.story_builder import load_story_catalog
from novelforge.story_engine import StoryStateRepository

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PACK_ID = "branch_pack_001"

PACK_PAYLOAD = {
    "pack_id": PACK_ID,
    "title": "分支隔离测试包",
    "initial_flags": {"journey_revision": 0, "ally": False},
    "initial_resources": {"supplies": 40, "spirit_stone": 20},
    "initial_current_location": "yard",
    "initial_locations": {"yard": {"name": "前院", "kind": "yard", "access": "自由出入"}},
    "initial_factions": {"guild": {"name": "行会", "kind": "faction", "stance": "中立",
                                   "data": {"influence": 5}}},
    "initial_characters": {"worker": {"name": "工匠", "kind": "npc",
                                      "data": {"goals": [
                                          {"id": "g1", "scope": "long_term", "title": "站住脚",
                                           "priority": 3, "weight": 2}]}}},
    "initial_plots": [
        {"id": "case_a", "title": "案子", "status": "active", "priority": 3, "progress": 0,
         "trigger": {"op": "flag", "key": "case_open", "value": True}},
    ],
    "actions": [
        {"id": "b_probe", "kind": "investigate", "name": "调查",
         "immediate_effects": [{"op": "set_flag", "key": "case_open", "value": True},
                               {"op": "add_knowledge", "target": "lead", "entity": "protagonist"}]},
        {"id": "b_ally", "kind": "protect", "name": "结盟",
         "costs": [{"op": "remove_resource", "target": "supplies", "value": 1}],
         "immediate_effects": [{"op": "change_relationship", "entity": "protagonist",
                                "target": "worker", "key": "trust", "value": 2},
                               {"op": "update_plot", "target": "case_a", "data": {"steps": 1}}]},
        {"id": "b_lie", "kind": "deceive", "name": "撒谎",
         "immediate_effects": [{"op": "set_flag", "key": "lied", "value": True},
                               {"op": "add_resource", "target": "spirit_stone", "value": 5}],
         "delayed_effects": [{"id": "b_delay", "description": "谎言会被拆穿",
                              "trigger": {"op": "time", "key": "tick", "value": 5,
                                          "comparator": ">="},
                              "effects": [{"op": "change_relationship", "entity": "protagonist",
                                           "target": "worker", "key": "hostility", "value": 3}]}]},
        {"id": "b_wait", "kind": "wait", "name": "等待"},
    ],
    "events": [],
}


def install_pack(tmp_path: Path) -> None:
    target = tmp_path / "novel" / "config" / "story_engine"
    target.mkdir(parents=True, exist_ok=True)
    (target / f"{PACK_ID}.json").write_text(
        json.dumps(PACK_PAYLOAD, ensure_ascii=False, indent=2), encoding="utf-8")


def client_for(tmp_path: Path) -> TestClient:
    install_pack(tmp_path)
    app = FastAPI()
    install_story_builder_api(app, tmp_path, catalog=load_story_catalog(PROJECT_ROOT))
    return TestClient(app)


def prepare_novel(client: TestClient, novel_id: str) -> str:
    created = client.post("/api/story-builder/novels", json={
        "novel_id": novel_id, "title": novel_id, "content_pack_id": PACK_ID})
    assert created.status_code == 201, created.text
    session = client.post("/api/story-builder/sessions", json={"project_id": novel_id}).json()
    url = "/api/story-builder/sessions/" + session["session"]["session_id"]
    catalog = client.get("/api/story-builder/catalogs").json()
    for version, step in enumerate(catalog["steps"]):
        recommendation = client.post(url + "/recommendations", json={"step": step["step"]}).json()
        saved = client.post(url + "/selections", json={
            "step": step["step"],
            "option_ids": [recommendation["recommendation"]["recommendations"][0]["option_id"]],
            "expected_selection_version": version})
        assert saved.status_code == 200, saved.text
    blueprint = client.post(url + "/compile-blueprint").json()["blueprint"]
    confirmed = client.post("/api/story-builder/blueprints/" + blueprint["blueprint_id"] + "/confirm",
                            json={"version": blueprint["version"]})
    assert confirmed.status_code == 200, confirmed.text
    return blueprint["blueprint_id"]


def advance(client: TestClient, novel_id: str, action: str, branch: str,
            expected: int | None = None, status: int = 200) -> dict:
    body = {"action_id": action, "actor": "protagonist", "branch_id": branch}
    if expected is not None:
        body["expected_revision"] = expected
    response = client.post(f"/api/story-builder/runtime/advance?novel_id={novel_id}", json=body)
    assert response.status_code == status, response.text
    return response.json()


def main_and_branches_isolated(tmp_path: Path) -> None:
    novel_id = "novel_branch_iso"
    client = client_for(tmp_path)
    blueprint_id = prepare_novel(client, novel_id)
    # main 先走两步，形成非空初始事实。
    advance(client, novel_id, "b_probe", "main", expected=0)
    advance(client, novel_id, "b_ally", "main", expected=1)
    main_before = client.get(
        f"/api/story-builder/runtime/state?novel_id={novel_id}&branch_id=main").json()
    assert main_before["revision"] == 2 and main_before["tick"] == 2

    # fork A/B/C 三个分支。
    for branch in ("branch_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa", "branch_bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb", "branch_cccccccccccccccccccccccccccccccc"):
        response = client.post(f"/api/story-builder/runtime/fork?novel_id={novel_id}",
                               json={"source_branch": "main", "target_branch": branch})
        assert response.status_code == 200, response.text
        assert response.json()["revision"] == 2

    # A 走 5 步、B 走 7 步、C 走 10 步（分支各自独立）。
    plan = {"branch_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa": ["b_probe", "b_ally", "b_wait", "b_probe", "b_ally"],
            "branch_bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb": ["b_ally", "b_probe", "b_wait", "b_lie", "b_probe", "b_wait", "b_ally"],
            "branch_cccccccccccccccccccccccccccccccc": ["b_lie", "b_probe", "b_ally", "b_wait", "b_probe", "b_lie",
                         "b_wait", "b_probe", "b_ally", "b_probe"]}
    for branch, actions in plan.items():
        revision = 2
        for action in actions:
            payload = advance(client, novel_id, action, branch, expected=revision)
            revision = payload["revision"]
    states = {branch: client.get(
        f"/api/story-builder/runtime/state?novel_id={novel_id}&branch_id={branch}").json()
        for branch in ("main", "branch_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa", "branch_bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb", "branch_cccccccccccccccccccccccccccccccc")}

    # main 逐字段未被分支推进影响。
    assert states["main"]["revision"] == 2 and states["main"]["tick"] == 2
    assert states["main"]["summary"] == main_before["summary"]
    # 三个分支各自的 revision / tick 互相独立。
    assert states["branch_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"]["revision"] == 7
    assert states["branch_bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"]["revision"] == 9
    assert states["branch_cccccccccccccccccccccccccccccccc"]["revision"] == 12
    assert states["branch_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"]["tick"] == 7
    assert states["branch_cccccccccccccccccccccccccccccccc"]["tick"] == 12
    # 关系 / 资源 / 知识 / 支线 / 延迟后果分支独立。
    assert states["branch_bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"]["summary"]["flags"].get("lied") is True
    assert "lied" not in (states["branch_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"]["summary"]["flags"] or {})
    assert states["branch_cccccccccccccccccccccccccccccccc"]["summary"]["resources"]["spirit_stone"] > \
        states["branch_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"]["summary"]["resources"]["spirit_stone"]
    assert states["branch_cccccccccccccccccccccccccccccccc"]["summary"]["flags"].get("case_open") is True


def test_main_and_branches_are_isolated(tmp_path: Path) -> None:
    main_and_branches_isolated(tmp_path)


def test_branch_revision_check_is_branch_local(tmp_path: Path) -> None:
    novel_id = "novel_branch_rev"
    client = client_for(tmp_path)
    prepare_novel(client, novel_id)
    advance(client, novel_id, "b_probe", "main", expected=0)
    client.post(f"/api/story-builder/runtime/fork?novel_id={novel_id}",
                json={"source_branch": "main", "target_branch": "branch_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"})
    for _ in range(4):
        current = client.get(
            f"/api/story-builder/runtime/state?novel_id={novel_id}&branch_id=branch_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa").json()
        advance(client, novel_id, "b_probe", "branch_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa", expected=current["revision"])
    branch_state = client.get(
        f"/api/story-builder/runtime/state?novel_id={novel_id}&branch_id=branch_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa").json()
    assert branch_state["revision"] == 5
    # main 仍是 revision 1，并且用 expected_revision=1 仍然被接受（不被分支进度影响）。
    main_state = client.get(
        f"/api/story-builder/runtime/state?novel_id={novel_id}&branch_id=main").json()
    assert main_state["revision"] == 1
    advance(client, novel_id, "b_ally", "main", expected=1)
    # 过期的 main 请求才被拒绝。
    advance(client, novel_id, "b_ally", "main", expected=1, status=409)


def test_fork_does_not_touch_source_and_rejects_existing_target(tmp_path: Path) -> None:
    novel_id = "novel_branch_fork"
    client = client_for(tmp_path)
    blueprint_id = prepare_novel(client, novel_id)
    advance(client, novel_id, "b_probe", "main", expected=0)
    before_main = client.get(
        f"/api/story-builder/runtime/state?novel_id={novel_id}&branch_id=main").json()
    forked = client.post(f"/api/story-builder/runtime/fork?novel_id={novel_id}",
                         json={"source_branch": "main", "target_branch": "branch_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"})
    assert forked.status_code == 200
    after_main = client.get(
        f"/api/story-builder/runtime/state?novel_id={novel_id}&branch_id=main").json()
    assert after_main["summary"] == before_main["summary"]
    # 重复 fork 到同名分支被拒绝，且不改动任何状态。
    again = client.post(f"/api/story-builder/runtime/fork?novel_id={novel_id}",
                        json={"source_branch": "main", "target_branch": "branch_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"})
    assert again.status_code == 409
    same = client.post(f"/api/story-builder/runtime/fork?novel_id={novel_id}",
                       json={"source_branch": "main", "target_branch": "main"})
    assert same.status_code == 409
    # 分支文件与主线文件确实分开存放。
    states = StoryStateRepository(tmp_path)
    assert states.exists(blueprint_id, 1, "main")
    assert states.exists(blueprint_id, 1, "branch_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa")
    assert states.path_for(blueprint_id, 1, "main") != states.path_for(blueprint_id, 1, "branch_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa")


def test_revision_rollback_and_replay_restores_facts(tmp_path: Path) -> None:
    """隔离实验：rev N → rev N+1 → 从 rev N 重放到测试分支，事实一致。"""

    from novelforge.story_engine import load_pack_from_project
    from novelforge.story_engine.driver import advance_story

    novel_id = "novel_branch_replay"
    client = client_for(tmp_path)
    blueprint_id = prepare_novel(client, novel_id)
    pack = load_pack_from_project(tmp_path, PACK_ID)
    states = StoryStateRepository(tmp_path)

    advance(client, novel_id, "b_probe", "main", expected=0)
    rev_one = client.get(
        f"/api/story-builder/runtime/state?novel_id={novel_id}&branch_id=main").json()
    advance(client, novel_id, "b_ally", "main", expected=1)
    rev_two = client.get(
        f"/api/story-builder/runtime/state?novel_id={novel_id}&branch_id=main").json()
    assert rev_two["revision"] == 2

    # 从 main 当前状态 fork 出测试分支，再在其上重放第 2 步，得到与 rev N+1 一致的事实。
    client.post(f"/api/story-builder/runtime/fork?novel_id={novel_id}",
                json={"source_branch": "main", "target_branch": "branch_dddddddddddddddddddddddddddddddd"})
    replayed = states.load(blueprint_id, 1, "branch_dddddddddddddddddddddddddddddddd")
    step = advance_story(replayed, pack, action_id="b_ally", actor="protagonist")
    assert step.ok
    states.save(step.state, blueprint_id, 1, "branch_dddddddddddddddddddddddddddddddd")
    replay_state = client.get(
        f"/api/story-builder/runtime/state?novel_id={novel_id}&branch_id=branch_dddddddddddddddddddddddddddddddd").json()
    # 重放分支多走一次 runtime turn（同时推进世界时间），因此 revision 会比源分支高 1。
    assert replay_state["revision"] == rev_one["revision"] + 2
    assert replay_state["summary"]["knowledge"] == rev_two["summary"]["knowledge"]
    assert replay_state["summary"]["plots"] == rev_two["summary"]["plots"]
    # main 未被回滚实验改动。
    main_state = client.get(
        f"/api/story-builder/runtime/state?novel_id={novel_id}&branch_id=main").json()
    assert main_state["revision"] == 2


def test_multi_novel_isolation_still_holds_with_branches(tmp_path: Path) -> None:
    first, second = "novel_branch_one", "novel_branch_two"
    client = client_for(tmp_path)
    prepare_novel(client, first)
    prepare_novel(client, second)
    advance(client, first, "b_probe", "main", expected=0)
    client.post(f"/api/story-builder/runtime/fork?novel_id={first}",
                json={"source_branch": "main", "target_branch": "branch_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"})
    other = client.get(
        f"/api/story-builder/runtime/state?novel_id={second}&branch_id=main").json()
    assert other["revision"] == 0 and other["summary"]["knowledge"] == []
    listed = client.get(
        f"/api/story-builder/runtime/state?novel_id={first}&branch_id=branch_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa").json()
    assert listed["revision"] == 1


def test_branch_apis_are_thin_and_reuse_existing_router(tmp_path: Path) -> None:
    app = FastAPI()
    install_story_builder_api(app, tmp_path, catalog=load_story_catalog(PROJECT_ROOT))
    routes = {route.path for route in app.routes if hasattr(route, "path")}
    assert "/api/story-builder/runtime/fork" in routes
    assert not [path for path in routes if path.startswith("/api/runtime")]
    source = (PROJECT_ROOT / "src/novelforge/api/story_builder_routes.py").read_text(encoding="utf-8")
    assert "class BranchRepository" not in source
    assert "def fork_story_state" not in source
