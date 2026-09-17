"""V2-I-04 成长面板：七类 Progression 共用一套判定，前端不做解锁计算。"""

from __future__ import annotations

import json
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from novelforge.api.story_builder_routes import install_story_builder_api
from novelforge.story_builder import load_story_catalog
from novelforge.story_engine import (
    CATEGORY_ORDER,
    ResourceStock,
    StoryStateRepository,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PACK_ID = "creator_progression_pack"


def node_payload(node_id: str, category: str, *, requires=None, costs=None, effects=None,
                 unlock=None, recommendation: str = "", story_impact: str = "") -> dict:
    # kind 只表达通用节点类型（progression / ability / identity / skill），
    # 七类成长由 category 区分。
    kind = {"ability": "ability", "equipment": "ability", "identity": "identity",
            "skill": "skill"}.get(category, "progression")
    payload: dict = {
        "id": node_id, "tree_id": "growth", "category": category, "kind": kind,
        "name": node_id, "summary": f"{category} 节点",
        "recommendation": recommendation or f"推荐原因：{category}",
        "story_impact": story_impact or f"剧情影响：{category}",
    }
    if requires:
        payload["requires"] = requires
    if costs:
        payload["costs"] = costs
    if effects:
        payload["effects"] = effects
    if unlock:
        payload["unlock"] = unlock
    return payload


PACK_PAYLOAD = {
    "pack_id": PACK_ID,
    "title": "成长面板测试包",
    "initial_flags": {"journey_revision": 0, "clue": True},
    "initial_resources": {"supplies": 1},
    "progressions": [{
        "tree_id": "growth",
        "name": "通用成长",
        "nodes": [
            node_payload("stage_one", "progression"),
            node_payload("stage_two", "progression", requires=["stage_one"],
                         costs=[{"op": "remove_resource", "target": "supplies", "value": 1}]),
            node_payload("stage_three", "progression", requires=["stage_two"]),
            node_payload("ability_one", "ability"),
            node_payload("identity_one", "identity", requires=["stage_one"],
                         effects=[{"op": "add_identity", "value": "identity_one"}]),
            node_payload("relationship_one", "relationship",
                         unlock={"op": "flag", "key": "clue", "value": True},
                         effects=[{"op": "change_relationship", "entity": "protagonist",
                                   "target": "ally", "key": "trust", "value": 1}]),
            node_payload("faction_one", "faction", requires=["stage_one"]),
            node_payload("information_one", "information",
                         unlock={"op": "knowledge", "entity": "protagonist", "target": "missing"}),
            node_payload("equipment_one", "equipment", requires=["stage_one"],
                         costs=[{"op": "remove_resource", "target": "supplies", "value": 1}]),
            node_payload("skill_one", "skill"),
        ],
    }],
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


def make_novel(client: TestClient, novel_id: str) -> str:
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


def seed_growth(tmp_path: Path, blueprint_id: str, novel_id: str) -> None:
    states = StoryStateRepository(tmp_path)
    state = states.load_or_migrate(None, blueprint_id, 1, "main", novel_id=novel_id)[0]
    state.flags["progression"] = ["stage_one"]
    state.resources["supplies"] = ResourceStock(id="supplies", amount=1, unit="份",
                                                holders=["protagonist"])
    states.save(state, blueprint_id, 1, "main")


def test_progression_panel_covers_seven_categories_with_states(tmp_path: Path) -> None:
    novel_id = "novel_alpha"
    client = client_for(tmp_path)
    blueprint_id = make_novel(client, novel_id)
    seed_growth(tmp_path, blueprint_id, novel_id)
    stored = StoryStateRepository(tmp_path).load(blueprint_id, 1, "main")

    payload = client.get("/api/story-builder/creator/progression?novel_id=" + novel_id).json()
    assert payload["meta"]["persisted"] is True
    nodes = {node["id"]: node for tree in payload["trees"] for node in tree["nodes"]}
    # 七类成长都在同一份数据里，且分类齐全。
    assert [item["category"] for item in payload["categories"]] == list(CATEGORY_ORDER)
    for category in CATEGORY_ORDER:
        assert [node["id"] for node in payload["categories"][
            list(CATEGORY_ORDER).index(category)]["nodes"]]
    # owned / available / locked 由引擎判定。
    assert nodes["stage_one"]["status"] == "owned"
    assert nodes["ability_one"]["status"] == "available"
    assert nodes["stage_two"]["status"] == "available", "前置与成本都满足时应可用"
    assert nodes["skill_one"]["status"] == "available"
    # 前置满足 → available（成长判定与真实解锁走同一套 Condition）。
    assert nodes["faction_one"]["status"] == "available"
    assert nodes["identity_one"]["status"] == "available"
    # 前置不满足 → locked，并给出缺失前置（前端不需要自己推导）。
    assert nodes["stage_three"]["status"] == "locked"
    assert nodes["stage_three"]["missing_requires"] == ["stage_two"]
    assert nodes["stage_three"]["reason"]
    # 条件不满足 → locked，并给出原因（不是前端判断）。
    assert nodes["information_one"]["status"] == "locked"
    assert nodes["information_one"]["reason"]
    # 成本、推荐理由、剧情影响都要给前端展示。
    assert nodes["stage_two"]["costs"] and nodes["stage_two"]["costs"][0]["target"] == "supplies"
    assert nodes["stage_two"]["recommendation"] and nodes["stage_two"]["story_impact"]
    # 读取不改写事实。
    assert StoryStateRepository(tmp_path).load(blueprint_id, 1, "main").model_dump() == stored.model_dump()


def test_progression_state_changes_when_facts_change(tmp_path: Path) -> None:
    novel_id = "novel_alpha"
    client = client_for(tmp_path)
    blueprint_id = make_novel(client, novel_id)
    seed_growth(tmp_path, blueprint_id, novel_id)
    before = client.get("/api/story-builder/creator/progression?novel_id=" + novel_id).json()
    before_nodes = {node["id"]: node for tree in before["trees"] for node in tree["nodes"]}

    states = StoryStateRepository(tmp_path)
    state = states.load(blueprint_id, 1, "main")
    # 拥有前置后，原先 locked 的内容会变成 available —— 判定完全由 StoryState 驱动。
    state.flags["progression"] = ["stage_one", "stage_two"]
    states.save(state, blueprint_id, 1, "main")
    after = client.get("/api/story-builder/creator/progression?novel_id=" + novel_id).json()
    after_nodes = {node["id"]: node for tree in after["trees"] for node in tree["nodes"]}
    assert before_nodes["stage_two"]["status"] == "available"
    assert after_nodes["stage_two"]["status"] == "owned"
    assert before["counts"]["owned"] != after["counts"]["owned"]


def test_progression_panel_filters_and_isolation(tmp_path: Path) -> None:
    first, second = "novel_one", "novel_two"
    client = client_for(tmp_path)
    first_blueprint = make_novel(client, first)
    make_novel(client, second)
    seed_growth(tmp_path, first_blueprint, first)
    filtered = client.get("/api/story-builder/creator/progression?novel_id=" + first
                          + "&category=equipment").json()
    assert [item["category"] for item in filtered["categories"]] == ["equipment"]
    assert all(node["category"] == "equipment"
               for tree in filtered["trees"] for node in tree["nodes"])
    second_payload = client.get("/api/story-builder/creator/progression?novel_id=" + second).json()
    assert second_payload["meta"]["preview"] is True
    second_nodes = {node["id"]: node for tree in second_payload["trees"] for node in tree["nodes"]}
    assert second_nodes["stage_one"]["status"] == "available"
    assert second_nodes["stage_two"]["status"] == "locked", "预览状态的节点不能假装已拥有"


def test_progression_without_trees_is_empty_not_invented(tmp_path: Path) -> None:
    novel_id = "novel_plain"
    client = client_for(tmp_path)
    make_novel(client, novel_id)
    (tmp_path / "novel" / "config" / "story_engine" / f"{PACK_ID}.json").write_text(
        json.dumps({**PACK_PAYLOAD, "progressions": []}, ensure_ascii=False, indent=2),
        encoding="utf-8")
    payload = client.get("/api/story-builder/creator/progression?novel_id=" + novel_id).json()
    assert payload["trees"] == []
    assert payload["note"], "没有成长树时必须明确说明，而不是编造节点"


def test_progression_view_has_no_second_state_or_genre_branching() -> None:
    for name in ("progression_view.py", "creator.py", "world_view.py", "character_view.py",
                 "plot_view.py"):
        text = (PROJECT_ROOT / "src/novelforge/story_engine" / name).read_text(encoding="utf-8")
        for pattern in ("if genre ==", "if world_type ==", "if novel_id ==", ".save(", "apply_effects("):
            assert pattern not in text, f"{name} 违反约束：{pattern}"
