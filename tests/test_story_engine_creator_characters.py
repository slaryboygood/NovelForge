"""V2-I-02 角色面板：目标 / 记忆 / 关系 / 弧 / 自主行动 / 反应理由都来自 StoryState 与引擎评分。"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from novelforge.api.story_builder_routes import install_story_builder_api
from novelforge.story_builder import load_story_catalog
from novelforge.story_engine import (
    Character,
    CharacterMemory,
    StoryStateRepository,
    load_pack_from_project,
    remember,
    set_goals,
    store_arc,
    upsert_goal,
)
from novelforge.story_engine.linkage import CharacterArc, ArcStage

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PACK_ID = "creator_character_pack"
PACK_SOURCE = PROJECT_ROOT / "novel/config/story_engine/journey_v1.json"


def install_pack(tmp_path: Path) -> None:
    target = tmp_path / "novel" / "config" / "story_engine"
    target.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(PACK_SOURCE, target / f"{PACK_ID}.json")
    payload = json.loads((target / f"{PACK_ID}.json").read_text(encoding="utf-8-sig"))
    payload["pack_id"] = PACK_ID
    (target / f"{PACK_ID}.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2),
                                            encoding="utf-8")


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


def seed_character(tmp_path: Path, blueprint_id: str, novel_id: str) -> None:
    """给角色写入目标 / 记忆 / 关系 / 弧；全部走引擎既有写入函数。"""

    states = StoryStateRepository(tmp_path)
    state = states.load_or_migrate(None, blueprint_id, 1, "main", novel_id=novel_id)[0]
    state.characters["protagonist"] = Character(
        id="protagonist", name="主角", kind="player",
        data={"desire": "查清账目", "fear": "连累同伴",
              "personality": ["谨慎"], "bottom_line": ["不弃同伴"]})
    state.characters["ally"] = Character(id="ally", name="同行者", kind="npc")
    state = set_goals(state, "protagonist", [
        {"id": "goal_long", "scope": "long_term", "title": "恢复货路", "priority": 3, "weight": 2},
        {"id": "goal_stage", "scope": "stage", "title": "拿到回执", "priority": 2, "weight": 3},
        {"id": "goal_now", "scope": "current", "title": "核对账目", "priority": 1, "weight": 1},
    ], source="author")
    state = upsert_goal(state, "protagonist",
                        {"id": "goal_now", "scope": "current", "title": "核对账目",
                         "priority": 4, "weight": 2}, source="event")
    state = remember(state, "protagonist", CharacterMemory(
        id="mem_1", holder="protagonist", summary="同行者替他挡下盘查", source="event",
        participants=["ally"], emotion=["感激"]))
    state = store_arc(state, CharacterArc(character_id="protagonist",
                                          stages=[ArcStage(id="s1", title="戒备"),
                                                  ArcStage(id="s2", title="信任")],
                                          current_index=0, outcome="advance", note="开始合作"))
    states.save(state, blueprint_id, 1, "main")


def test_character_panel_matches_state_and_keeps_fields_separate(tmp_path: Path) -> None:
    novel_id = "novel_alpha"
    client = client_for(tmp_path)
    blueprint_id = make_novel(client, novel_id)
    seed_character(tmp_path, blueprint_id, novel_id)
    stored = StoryStateRepository(tmp_path).load(blueprint_id, 1, "main")

    payload = client.get("/api/story-builder/creator/characters?novel_id=" + novel_id).json()
    assert payload["meta"]["persisted"] is True
    ids = [item["id"] for item in payload["characters"]]
    assert ids == ["ally", "protagonist"]
    assert payload["selected"] == "protagonist"
    detail = payload["detail"]
    assert detail["name"] == "主角"
    # 长期 / 阶段 / 当前三类目标分开，且当前目标由 select_goal 决定（不只是分数最高的长期目标）。
    assert [item["id"] for item in detail["goals"]["long_term"]] == ["goal_long"]
    assert [item["id"] for item in detail["goals"]["stage"]] == ["goal_stage"]
    assert [item["id"] for item in detail["goals"]["current"]] == ["goal_now"]
    assert detail["current_goal"]["id"] == "goal_now"
    assert detail["current_goal"]["score"] == 8.0
    # 记忆来自角色自身 data。
    assert [item["id"] for item in detail["memories"]] == ["mem_1"]
    assert detail["memories"][0]["emotion"] == ["感激"]
    # 人物弧来自角色 data，且明确不是强制脚本。
    assert detail["arc"]["stage"] == "戒备" and detail["arc"]["is_forced"] is False
    # 欲望 / 恐惧 / 底线来自角色 data。
    assert detail["drives"]["desire"] == "查清账目"
    assert detail["drives"]["bottom_line"] == ["不弃同伴"]
    # 反应理由是引擎评分，不是前端算分。
    assert detail["reactions"] and all(item["reason"] for item in detail["reactions"])
    # 面板数据与 StoryState 一致，且读取没有改动事实。
    assert stored.characters["protagonist"].data["goals"][2]["id"] == "goal_now"
    assert StoryStateRepository(tmp_path).load(blueprint_id, 1, "main").model_dump() == stored.model_dump()


def test_character_panel_preview_and_isolation(tmp_path: Path) -> None:
    first, second = "novel_one", "novel_two"
    client = client_for(tmp_path)
    first_blueprint = make_novel(client, first)
    make_novel(client, second)
    seed_character(tmp_path, first_blueprint, first)

    first_payload = client.get("/api/story-builder/creator/characters?novel_id=" + first).json()
    second_payload = client.get("/api/story-builder/creator/characters?novel_id=" + second).json()
    assert first_payload["meta"]["persisted"] is True
    assert second_payload["meta"]["preview"] is True
    assert [item["id"] for item in first_payload["characters"]] == ["ally", "protagonist"]
    # 预览小说只有内容包声明的起点角色，不能读到另一本小说的人物。
    assert [item["id"] for item in second_payload["characters"]] == ["protagonist"]
    assert second_payload["detail"]["memories"] == []
    assert StoryStateRepository(tmp_path).load(first_blueprint, 1, "main").characters["ally"].name == "同行者"


def test_character_panel_reactions_can_be_disabled_and_targets_are_isolated(tmp_path: Path) -> None:
    novel_id = "novel_alpha"
    client = client_for(tmp_path)
    blueprint_id = make_novel(client, novel_id)
    seed_character(tmp_path, blueprint_id, novel_id)
    payload = client.get("/api/story-builder/creator/characters?novel_id=" + novel_id
                         + "&character_id=ally&reactions=false").json()
    assert payload["selected"] == "ally"
    assert payload["detail"]["name"] == "同行者"
    assert payload["detail"]["reactions"] == []
    assert payload["detail"]["goals"]["long_term"] == []
    # 未知角色不编造数据。
    missing = client.get("/api/story-builder/creator/characters?novel_id=" + novel_id
                         + "&character_id=ghost").json()
    assert missing["detail"]["exists"] is False
    assert missing["detail"]["memories"] == [] and missing["detail"]["current_goal"] is None


def test_character_view_has_no_second_state_or_genre_branching() -> None:
    for name in ("character_view.py", "creator.py", "world_view.py"):
        text = (PROJECT_ROOT / "src/novelforge/story_engine" / name).read_text(encoding="utf-8")
        for pattern in ("if genre ==", "if world_type ==", "if novel_id ==", ".save(", "apply_effects("):
            assert pattern not in text, f"{name} 违反约束：{pattern}"
    pack = load_pack_from_project(PROJECT_ROOT, "journey_v1")
    assert pack.pack_id == "journey_v1"
