"""V2-I-06 导演面板：排序与得分只能来自 director.py，权重调整只改配置。"""

from __future__ import annotations

import json
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from novelforge.api.story_builder_routes import install_story_builder_api
from novelforge.story_builder import load_story_catalog
from novelforge.story_engine import (
    DirectorWeights,
    EventCardCatalog,
    PlotTrack,
    StoryState,
    StoryStateRepository,
    decide,
    event_catalog_from_payload,
    score_events,
    upsert_plot,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PACK_ID = "creator_director_pack"

PACK_PAYLOAD = {
    "pack_id": PACK_ID,
    "title": "导演面板测试包",
    "initial_flags": {"journey_revision": 0, "ready": True},
    "initial_resources": {"supplies": 1},
    "events": [
        {"event_id": "main_battle", "title": "主线对峙", "kind": "main", "priority": 4,
         "once_only": False, "trigger": {"op": "flag", "key": "ready", "value": True},
         "data": {"main_line": True, "pacing": "rise", "event_type": "battle",
                  "crisis": 1, "danger": 1}},
        {"event_id": "ledger_twist", "title": "账册线索", "kind": "mystery", "priority": 2,
         "once_only": False, "trigger": {"op": "flag", "key": "ready", "value": True},
         "data": {"subplot": "ledger", "pacing": "turn", "event_type": "mystery",
                  "foreshadow": 1, "payoff": 1}},
        {"event_id": "sister_step", "title": "妹妹的消息", "kind": "side", "priority": 2,
         "once_only": False, "trigger": {"op": "flag", "key": "ready", "value": True},
         "data": {"subplot": "sister", "character_arc": True, "pacing": "setup",
                  "event_type": "side"}},
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


def seed_director(tmp_path: Path, blueprint_id: str, novel_id: str) -> None:
    from novelforge.story_engine.entities import EffectRecord

    states = StoryStateRepository(tmp_path)
    state = states.load_or_migrate(None, blueprint_id, 1, "main", novel_id=novel_id)[0]
    state.flags["ready"] = True
    state = upsert_plot(state, PlotTrack(id="ledger", title="账册疑云", status="active",
                                         priority=3, progress=0))
    state = upsert_plot(state, PlotTrack(id="sister", title="寻找妹妹", status="active",
                                         priority=2, progress=1))
    state.effect_log.append(EffectRecord(id="choice:1", op="choice", entity="protagonist",
                                         target="followup_settle", order=1,
                                         data={"result": "先留下记录", "tick": 1}))
    states.save(state, blueprint_id, 1, "main")


def engine_catalog() -> EventCardCatalog:
    return event_catalog_from_payload({"catalog_id": PACK_ID, "cards": PACK_PAYLOAD["events"]})


def test_director_panel_matches_engine_scores(tmp_path: Path) -> None:
    novel_id = "novel_alpha"
    client = client_for(tmp_path)
    blueprint_id = make_novel(client, novel_id)
    seed_director(tmp_path, blueprint_id, novel_id)
    stored = StoryStateRepository(tmp_path).load(blueprint_id, 1, "main")

    payload = client.get("/api/story-builder/creator/director?novel_id=" + novel_id).json()
    # 与引擎直接计算结果逐项一致：面板不重新算分。
    expected_scores = score_events(engine_catalog(), stored, weights=DirectorWeights())
    expected_decision = decide(engine_catalog(), stored, weights=DirectorWeights())
    assert [item["event_id"] for item in payload["scored"]] == [item.event_id for item in expected_scores]
    assert [round(item["score"], 6) for item in payload["scored"]] == [
        round(item.score, 6) for item in expected_scores]
    assert payload["chosen"] == expected_decision.chosen
    assert payload["why_chosen"] == expected_decision.why_chosen
    assert {key: value for key, value in payload["why_not"].items()} == dict(expected_decision.why_not)
    # 逐维得分、加分 / 扣分原因必须逐条给出。
    top = payload["ranked"][0]
    assert top["is_chosen"] is True and isinstance(top["dimensions"], dict)
    assert all(item["reasons"] is not None and item["deductions"] is not None
               for item in payload["ranked"])
    # 当前权重来自配置（默认值时等于 DirectorWeights 默认）。
    assert payload["weights"] == DirectorWeights().as_config()
    assert payload["weights_config"] == {}
    # 读取不改写事实。
    assert StoryStateRepository(tmp_path).load(blueprint_id, 1, "main").model_dump() == stored.model_dump()


def test_weight_change_only_updates_config_and_uses_engine(tmp_path: Path) -> None:
    novel_id = "novel_alpha"
    client = client_for(tmp_path)
    blueprint_id = make_novel(client, novel_id)
    seed_director(tmp_path, blueprint_id, novel_id)
    before = client.get("/api/story-builder/creator/director?novel_id=" + novel_id).json()

    updated = client.put("/api/story-builder/creator/director/weights?novel_id=" + novel_id,
                         json={"weights": {"payoff": 8.0, "main_line": 0.1, "subplot": 3.0}})
    assert updated.status_code == 200, updated.text
    payload = updated.json()
    assert payload["novel"]["director_weights"]["payoff"] == 8.0
    # 新的排序仍然由引擎产出，而不是前端。
    stored = StoryStateRepository(tmp_path).load(blueprint_id, 1, "main")
    tuned = DirectorWeights.model_validate({"payoff": 8.0, "main_line": 0.1, "subplot": 3.0})
    expected = score_events(engine_catalog(), stored, weights=tuned)
    assert [item["event_id"] for item in payload["director"]["scored"]] == [
        item.event_id for item in expected]
    assert payload["director"]["scored"][0]["event_id"] == "ledger_twist"
    assert payload["director"]["chosen"] == "ledger_twist"
    assert before["chosen"] != payload["director"]["chosen"]

    # 刷新（重新读取）后权重仍然生效。
    refreshed = client.get("/api/story-builder/creator/director?novel_id=" + novel_id).json()
    assert refreshed["weights_config"]["payoff"] == 8.0
    assert refreshed["chosen"] == payload["director"]["chosen"]
    # 权重只改配置：StoryState 不被触碰。
    assert {"main_battle", "ledger_twist", "sister_step"} == {
        item["event_id"] for item in refreshed["available_events"]}


def test_director_weights_are_isolated_between_novels(tmp_path: Path) -> None:
    first, second = "novel_one", "novel_two"
    client = client_for(tmp_path)
    make_novel(client, first)
    make_novel(client, second)
    updated = client.put("/api/story-builder/creator/director/weights?novel_id=" + first,
                         json={"weights": {"crisis": 4.0}})
    assert updated.status_code == 200
    other = client.get("/api/story-builder/creator/director?novel_id=" + second).json()
    assert other["weights_config"] == {}
    assert other["meta"]["preview"] is True
    # 权重被隔离：第二本小说仍然按默认权重排序，且排序仍由引擎给出。
    assert other["weights"] == DirectorWeights().as_config()
    assert [item["event_id"] for item in other["scored"]] == [
        item.event_id for item in score_events(engine_catalog(), StoryState(
            novel_id=second, flags=dict(PACK_PAYLOAD["initial_flags"])))]


def test_director_rejects_invalid_weights(tmp_path: Path) -> None:
    novel_id = "novel_alpha"
    client = client_for(tmp_path)
    make_novel(client, novel_id)
    empty = client.put("/api/story-builder/creator/director/weights?novel_id=" + novel_id,
                       json={"weights": {}})
    assert empty.status_code == 422
    invalid = client.put("/api/story-builder/creator/director/weights?novel_id=" + novel_id,
                         json={"weights": {"payoff": "高"}})
    assert invalid.status_code == 422
    unknown = client.put("/api/story-builder/creator/director/weights?novel_id=" + novel_id,
                         json={"weights": {"unknown_weight": 1.0}})
    assert unknown.status_code == 422


def test_director_view_has_no_second_scoring_or_genre_branching() -> None:
    for name in ("creator.py", "world_view.py", "character_view.py",
                 "plot_view.py", "progression_view.py", "memory_view.py"):
        text = (PROJECT_ROOT / "src/novelforge/story_engine" / name).read_text(encoding="utf-8")
        for pattern in ("if genre ==", "if world_type ==", "if novel_id ==", ".save(",
                        "apply_effects("):
            assert pattern not in text, f"{name} 违反约束：{pattern}"
    # 导演视图只读取评分结果，不重新实现评分，也不写 StoryState（只写 Node Profile 配置）。
    director = (PROJECT_ROOT / "src/novelforge/story_engine/director_view.py").read_text(encoding="utf-8")
    for pattern in ("if genre ==", "if world_type ==", "if novel_id ==", "def score_events(",
                    "def decide(", "apply_effects(", "StoryStateRepository"):
        assert pattern not in director, f"director_view.py 违反约束：{pattern}"
    assert StoryState().timeline.tick == 0
