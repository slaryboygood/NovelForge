"""V2 Runtime API 集成测试：API → driver → persistence → next candidates 完整闭环。"""

from __future__ import annotations

import json
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from novelforge.api.story_builder_routes import install_story_builder_api
from novelforge.story_builder import load_story_catalog
from novelforge.story_engine import StoryStateRepository

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PACK_ID = "runtime_pack_001"

PACK_PAYLOAD = {
    "pack_id": PACK_ID,
    "title": "运行态测试包",
    "initial_flags": {"journey_revision": 0, "ally": False},
    "initial_resources": {"supplies": 30, "spirit_stone": 4},
    "initial_current_location": "yard",
    "initial_locations": {"yard": {"name": "前院", "kind": "yard", "access": "自由出入",
                                   "data": {"control": "guild", "danger": 0}}},
    "initial_factions": {"guild": {"name": "行会", "kind": "faction", "stance": "中立",
                                   "data": {"influence": 5, "resources": ["人手"],
                                            "internal_conflicts": ["分成争议"]}}},
    "initial_characters": {
        "worker": {"name": "工匠", "kind": "npc",
                   "data": {"role": "手艺人", "desire": "完成订单", "fear": "被追责",
                            "bottom_line": ["不偷工减料"],
                            "goals": [{"id": "goal_long", "scope": "long_term", "title": "站稳脚跟",
                                       "priority": 3, "weight": 2}]}},
    },
    "initial_plots": [
        {"id": "main_case", "title": "订单疑云", "status": "active", "priority": 3, "progress": 0,
         "factions": ["guild"], "locations": ["yard"]},
    ],
    "progressions": [{"tree_id": "rt_tree", "name": "运行态成长", "nodes": [
        {"id": "rt_node", "tree_id": "rt_tree", "kind": "ability", "category": "ability",
         "name": "起步", "summary": "", "story_impact": ""},
    ]}],
    "foreshadows": [
        {"id": "rt_fs", "title": "未结的订单", "status": "planned", "planted_in": "开篇",
         "payoff_in": "收束", "data": {"level": "book"}},
    ],
    "autonomous_rules": [
        {"actor_id": "worker", "action_id": "rt_help", "label": "工匠主动搭手",
         "priority": 3, "once": True},
    ],
    "actions": [
        {"id": "rt_probe", "kind": "investigate", "name": "核对登记",
         "data": {"weight": 2, "cost_text": "不消耗资源"}},
        {"id": "rt_help", "kind": "protect", "name": "帮助工匠",
         "costs": [{"op": "remove_resource", "target": "supplies", "value": 1}],
         "immediate_effects": [{"op": "set_flag", "key": "ally", "value": True}],
         "data": {"weight": 1, "cost_text": "消耗 1 补给"}},
    ],
    "events": [
        {"event_id": "rt_world", "title": "行会点名", "kind": "world", "priority": 4,
         "once_only": False, "scope": "world", "knowledge_id": "rt_rumor", "reader_visible": True,
         "trigger": {"op": "flag", "key": "ally", "value": True},
         "consequences": [{"op": "update_faction", "target": "guild",
                           "data": {"influence": 3}}],
         "data": {"world_event": True, "pacing": "turn", "event_type": "call"}},
    ],
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


def test_runtime_api_advances_twelve_turns(tmp_path: Path) -> None:
    """正式 API 连续推进 12 回合，验证完整闭环。"""

    novel_id = "novel_runtime_api"
    client = client_for(tmp_path)
    blueprint_id = prepare_novel(client, novel_id)

    # 尚未推进过运行时：先做一次明确的 world tick，让初始 StoryState 正式落盘。
    ticked = client.post(f"/api/story-builder/runtime/tick?novel_id={novel_id}",
                         json={"expected_revision": 0})
    assert ticked.status_code == 200, ticked.text
    assert ticked.json()["world_actions"], "世界 tick 应产生 NPC 自主行动"

    state = client.get("/api/story-builder/runtime/state?novel_id=" + novel_id)
    assert state.status_code == 200, state.text
    first = state.json()
    assert first["meta"]["persisted"] is True
    assert first["revision"] == 0 and first["tick"] == 1
    assert set(first["available"]) == {"rt_probe", "rt_help"}
    assert first["blocked"] == []

    revisions, ticks = [], []
    for turn in range(1, 13):
        current = client.get("/api/story-builder/runtime/state?novel_id=" + novel_id).json()
        action = "rt_probe" if turn % 2 else "rt_help"
        assert action in current["available"], (turn, current["available"])
        advanced = client.post(f"/api/story-builder/runtime/advance?novel_id={novel_id}",
                               json={"action_id": action, "actor": "protagonist",
                                     "expected_revision": current["revision"]})
        assert advanced.status_code == 200, advanced.text
        payload = advanced.json()
        assert payload["ok"] is True
        assert payload["executed_action"] == action
        assert payload["next_candidates"], f"第 {turn} 轮必须返回下一轮候选"
        assert payload["available_actions"], f"第 {turn} 轮必须有可用行动"
        assert payload["current_state_summary"]["revision"] == turn
        revisions.append(payload["revision"])
        ticks.append(payload["tick"])
    assert revisions == list(range(1, 13)), revisions
    assert ticks == list(range(2, 14)), ticks

    stored = StoryStateRepository(tmp_path).load(blueprint_id, 1, "main")
    assert stored.timeline.tick == 13
    assert len([item for item in stored.effect_log if item.op == "runtime_action"]) == 12


def test_runtime_api_blocks_illegal_and_stale_actions(tmp_path: Path) -> None:
    novel_id = "novel_runtime_api"
    client = client_for(tmp_path)
    prepare_novel(client, novel_id)

    unknown = client.post(f"/api/story-builder/runtime/advance?novel_id={novel_id}",
                          json={"action_id": "no_such_action", "expected_revision": 0})
    assert unknown.status_code == 422
    assert unknown.json()["detail"]["code"] == "action_not_in_catalog"

    locked = client.post(f"/api/story-builder/runtime/advance?novel_id={novel_id}",
                         json={"action_id": "rt_missing", "expected_revision": 0})
    assert locked.status_code == 422

    first = client.post(f"/api/story-builder/runtime/advance?novel_id={novel_id}",
                        json={"action_id": "rt_probe", "expected_revision": 0})
    assert first.status_code == 200
    stale = client.post(f"/api/story-builder/runtime/advance?novel_id={novel_id}",
                        json={"action_id": "rt_probe", "expected_revision": 0})
    assert stale.status_code == 409
    assert stale.json()["detail"]["code"] == "stale_revision"
    # 过期请求不得产生第二次效果。
    state = client.get("/api/story-builder/runtime/state?novel_id=" + novel_id).json()
    assert state["revision"] == 1
    assert len([item for item in state["summary"]["flags"]]) >= 1


def test_runtime_tick_advances_world_without_hero_action(tmp_path: Path) -> None:
    novel_id = "novel_runtime_api"
    client = client_for(tmp_path)
    prepare_novel(client, novel_id)

    ticked = client.post(f"/api/story-builder/runtime/tick?novel_id={novel_id}",
                         json={"expected_revision": 0})
    assert ticked.status_code == 200, ticked.text
    payload = ticked.json()
    assert payload["outcome"] == "world_tick"
    assert payload["world_actions"] and payload["world_actions"][0]["actor"] == "worker"
    assert payload["next_candidates"]
    # 世界 tick 不产生主角行动记录。
    assert all(item["action_id"] != "runtime_action" for item in payload["next_candidates"])
    state = client.get("/api/story-builder/runtime/state?novel_id=" + novel_id).json()
    assert state["revision"] == 0 and state["tick"] == 1
    assert state["summary"]["flags"]["ally"] is True


def test_runtime_api_requires_confirmed_blueprint_or_explicit_start(tmp_path: Path) -> None:
    novel_id = "novel_runtime_noblueprint"
    client = client_for(tmp_path)
    created = client.post("/api/story-builder/novels", json={
        "novel_id": novel_id, "title": novel_id, "content_pack_id": PACK_ID})
    assert created.status_code == 201
    missing = client.post(f"/api/story-builder/runtime/advance?novel_id={novel_id}",
                          json={"action_id": "rt_probe"})
    assert missing.status_code == 409
    # W1-04：没有蓝图的小说必须先显式开始推演，不能靠一次推进隐式建立事实。
    assert missing.json()["detail"]["code"] == "STORY_NOT_STARTED"
    started = client.post(f"/api/story-builder/runtime/start?novel_id={novel_id}", json={})
    # 这个演示包只有“满足条件才会触发”的世界事件，起点自检会要求作者先让事件可触发。
    assert started.status_code == 422, started.text
    assert started.json()["detail"]["code"] == "SETTINGS_NOT_RUNNABLE"
    assert {item["code"] for item in started.json()["detail"]["findings"]} >= {
        "EVENT_NOT_TRIGGERABLE"}


def test_runtime_apis_are_thin_and_isolated(tmp_path: Path) -> None:
    """运行态接口属于现有 Story Builder router；不同小说互不影响。"""

    first, second = "novel_runtime_one", "novel_runtime_two"
    client = client_for(tmp_path)
    prepare_novel(client, first)
    prepare_novel(client, second)
    client.post(f"/api/story-builder/runtime/advance?novel_id={first}",
                json={"action_id": "rt_probe", "expected_revision": 0})
    first_state = client.get("/api/story-builder/runtime/state?novel_id=" + first).json()
    second_state = client.get("/api/story-builder/runtime/state?novel_id=" + second).json()
    assert first_state["revision"] == 1
    assert second_state["revision"] == 0 and second_state["tick"] == 0
    routes = {route.path for route in client.app.routes if hasattr(route, "path")}
    assert "/api/story-builder/runtime/state" in routes
    assert "/api/story-builder/runtime/advance" in routes
    assert "/api/story-builder/runtime/tick" in routes
    assert not [path for path in routes if path.startswith("/api/runtime")]
