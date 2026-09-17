"""V2-I-03 剧情面板：候选行动与事件链必须由 StoryState 与内容包算出，前端不参与判定。"""

from __future__ import annotations

import json
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from novelforge.api.story_builder_routes import install_story_builder_api
from novelforge.story_builder import load_story_catalog
from novelforge.story_engine import (
    EventRecord,
    PlotTrack,
    ResourceStock,
    StoryStateRepository,
    event_catalog_from_payload,
    fire_event_chain,
    load_pack_from_project,
    upsert_plot,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PACK_ID = "creator_plot_pack"
PACK_SOURCE = PROJECT_ROOT / "novel/config/story_engine/journey_v1.json"
GATED_ACTION = "journey_pay"
OPEN_ACTION = "journey_leave"


def install_pack(tmp_path: Path) -> None:
    target = tmp_path / "novel" / "config" / "story_engine"
    target.mkdir(parents=True, exist_ok=True)
    source = json.loads(PACK_SOURCE.read_text(encoding="utf-8-sig"))
    source["pack_id"] = PACK_ID
    # 起点不给补给：同一组候选行动必须出现 available / unavailable 两种结果。
    source["initial_resources"] = {"supplies": 0}
    (target / f"{PACK_ID}.json").write_text(json.dumps(source, ensure_ascii=False, indent=2),
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


def seed_plot(tmp_path: Path, blueprint_id: str, novel_id: str, *, supplies: float = 0,
              reset: bool = False) -> None:
    """写入支线、事件与资源事实；行动可用性由引擎在读取时重新判定。"""

    from novelforge.story_engine import StoryState

    states = StoryStateRepository(tmp_path)
    state = (StoryState(novel_id=novel_id) if reset
             else states.load_or_migrate(None, blueprint_id, 1, "main", novel_id=novel_id)[0])
    state = upsert_plot(state, PlotTrack(id="ledger", title="账册疑云", status="active", priority=3,
                                         progress=1, factions=["gate_guard"], locations=["dock"]))
    state = upsert_plot(state, PlotTrack(id="old_case", title="旧案", status="completed",
                                         priority=1, progress=3))
    if supplies:
        state.resources["supplies"] = ResourceStock(id="supplies", amount=supplies, unit="份",
                                                    holders=["protagonist"])
    state.flags["clue"] = True
    state.flags["ally"] = True
    state.flags["journey_revision"] = 0
    pack = load_pack_from_project(tmp_path, PACK_ID)
    catalog = event_catalog_from_payload({"catalog_id": PACK_ID,
                                          "cards": [item.model_dump(mode="json") for item in pack.events]})
    card = next((item for item in catalog.cards
                 if item.event_id not in [entry.id for entry in state.active_events + state.resolved_events]),
                None)
    if card is not None:
        state = fire_event_chain(state, catalog, card.event_id, actor="protagonist").state
    if not state.active_events and not state.resolved_events:
        state.active_events.append(EventRecord(id="unregistered_event", status="active",
                                               source="test", participants=["protagonist"]))
    states.save(state, blueprint_id, 1, "main")


def test_plot_panel_reports_available_and_unavailable_with_reasons(tmp_path: Path) -> None:
    novel_id = "novel_alpha"
    client = client_for(tmp_path)
    blueprint_id = make_novel(client, novel_id)
    seed_plot(tmp_path, blueprint_id, novel_id)
    stored = StoryStateRepository(tmp_path).load(blueprint_id, 1, "main")

    payload = client.get("/api/story-builder/creator/plot?novel_id=" + novel_id).json()
    candidates = {item["action_id"]: item for item in payload["candidates"]}
    assert payload["meta"]["persisted"] is True
    assert payload["actor"] == "protagonist"
    blocked = candidates[GATED_ACTION]
    assert blocked["available"] is False
    assert blocked["code"] and blocked["reason"], "不可用行动必须给出原因"
    assert OPEN_ACTION in payload["available"], "无前置行动必须可用"
    # 世界影响：行动条件引用了哪些世界状态，以及是否真的改变了可用性。
    keys = {item["key"]: item for item in payload["world_impacts"]}
    assert "supplies" in keys
    assert GATED_ACTION in keys["supplies"]["unavailable_actions"]
    assert keys["supplies"]["impacts_availability"] is True
    # 世界标记与候选行动的条件对应，前端只展示不计算。
    flags = {item["key"]: item for item in payload["world_flags"]}
    assert flags["clue"]["value"] is True
    # 支线：活跃与已发生的分开；面板只把 active / paused 当作活跃支线。
    active = [item for item in payload["active_plots"] if item["status"] in ("active", "paused")]
    assert [item["id"] for item in active] == ["ledger"]
    assert payload["active_plots"][0]["progress"] == 1
    assert [item["id"] for item in payload["resolved_plots"]] == ["old_case"]
    # 事件链与当前事件来自 effect_log。
    assert payload["event_chain"], "事件链应记录已发生的事件"
    assert payload["current_events"], "应给出进行中或最近事件"
    assert payload["triggerable_events"], "应给出可触发 / 不可触发事件及原因"
    # 读取不改写事实。
    assert StoryStateRepository(tmp_path).load(blueprint_id, 1, "main").model_dump() == stored.model_dump()


def test_same_scene_changes_candidates_when_state_changes(tmp_path: Path) -> None:
    novel_id = "novel_alpha"
    client = client_for(tmp_path)
    blueprint_id = make_novel(client, novel_id)
    seed_plot(tmp_path, blueprint_id, novel_id, supplies=0)
    before = client.get("/api/story-builder/creator/plot?novel_id=" + novel_id).json()
    seed_plot(tmp_path, blueprint_id, novel_id, supplies=5, reset=True)
    after = client.get("/api/story-builder/creator/plot?novel_id=" + novel_id).json()
    candidates = {item["action_id"]: item for item in after["candidates"]}
    assert GATED_ACTION not in before["available"]
    assert GATED_ACTION in after["available"]
    assert candidates[GATED_ACTION]["available"] is True
    assert before["available"] != after["available"]


def test_plot_panel_preview_and_isolation(tmp_path: Path) -> None:
    first, second = "novel_one", "novel_two"
    client = client_for(tmp_path)
    first_blueprint = make_novel(client, first)
    make_novel(client, second)
    seed_plot(tmp_path, first_blueprint, first)
    first_payload = client.get("/api/story-builder/creator/plot?novel_id=" + first).json()
    second_payload = client.get("/api/story-builder/creator/plot?novel_id=" + second).json()
    assert first_payload["meta"]["persisted"] is True
    assert second_payload["meta"]["preview"] is True
    assert [item["id"] for item in first_payload["active_plots"]] == ["ledger"]
    assert second_payload["active_plots"] == [] and second_payload["event_chain"] == []
    assert StoryStateRepository(tmp_path).load(first_blueprint, 1, "main").plots["ledger"]["progress"] == 1


def test_plot_view_has_no_second_state_or_genre_branching() -> None:
    for name in ("plot_view.py", "creator.py", "world_view.py", "character_view.py"):
        text = (PROJECT_ROOT / "src/novelforge/story_engine" / name).read_text(encoding="utf-8")
        for pattern in ("if genre ==", "if world_type ==", "if novel_id ==", ".save(", "apply_effects("):
            assert pattern not in text, f"{name} 违反约束：{pattern}"
