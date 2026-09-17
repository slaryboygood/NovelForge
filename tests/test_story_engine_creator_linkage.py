"""V2-I-07 大纲联动面板：StoryState → 路线 → 全书 / 卷 / 篇章 / 章节，历史不可被重规划改写。"""

from __future__ import annotations

import json
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from novelforge.api.story_builder_routes import install_story_builder_api
from novelforge.story_builder import load_story_catalog
from novelforge.story_engine import (
    PlotTrack,
    StoryStateRepository,
    upsert_plot,
)
from novelforge.story_engine.entities import EffectRecord

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PACK_ID = "creator_linkage_pack"

PACK_PAYLOAD = {
    "pack_id": PACK_ID,
    "title": "大纲联动测试包",
    "initial_flags": {"journey_revision": 0},
    "initial_resources": {"supplies": 1},
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


def seed_long_line(tmp_path: Path, blueprint_id: str, novel_id: str, *,
                   chapters: int = 20) -> None:
    """写入足够长的已发生路线：22 章 → 5 篇章 → 3 卷。"""

    from novelforge.story_engine import Character

    states = StoryStateRepository(tmp_path)
    state = states.load_or_migrate(None, blueprint_id, 1, "main", novel_id=novel_id)[0]
    state.characters["protagonist"] = Character(id="protagonist", name="主角", kind="player")
    for index in range(1, chapters + 3):
        state.effect_log.append(EffectRecord(
            id=f"choice:{index}", op="choice", entity="protagonist",
            target=f"action_{index:02d}", order=index,
            data={"result": f"第 {index} 次选择的结果", "tick": index}))
    state = upsert_plot(state, PlotTrack(id="ledger", title="账册疑云", status="active",
                                         priority=3, progress=1))
    states.save(state, blueprint_id, 1, "main")


def add_future_plan(tmp_path: Path, novel_id: str) -> None:
    profiles = tmp_path / "novel" / "authoring" / "story_engine" / "profiles"
    path = profiles / f"{novel_id}.json"
    payload = json.loads(path.read_text(encoding="utf-8-sig"))
    payload["profile"]["future_plan"] = {
        "plan_id": "plan", "revision": 1,
        "stages": [
            {"id": "stage_1", "title": "第一阶段", "goal": "查清账目", "status": "active",
             "is_goal": True},
            {"id": "stage_2", "title": "第二阶段", "goal": "恢复货路", "status": "planned",
             "is_goal": True},
        ],
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def test_linkage_panel_separates_happened_planned_suggested(tmp_path: Path) -> None:
    novel_id = "novel_alpha"
    client = client_for(tmp_path)
    blueprint_id = make_novel(client, novel_id)
    seed_long_line(tmp_path, blueprint_id, novel_id)
    add_future_plan(tmp_path, novel_id)
    stored = StoryStateRepository(tmp_path).load(blueprint_id, 1, "main")

    payload = client.get("/api/story-builder/creator/linkage?novel_id=" + novel_id).json()
    assert payload["meta"]["persisted"] is True
    assert payload["counts"]["happened"] == len(stored.effect_log)
    assert all(item["kind"] == "happened" for item in payload["route"]["happened"])
    # 未收束的支线只是当前状态，不算已发生路线条目；历史只包含实际选择。
    assert {item["origin"] for item in payload["route"]["happened"]} == {"action"}
    assert payload["long_line"]["unresolved"], "计划阶段必须留在 unresolved，而不是历史"
    assert all(item["kind"] == "planned" for item in payload["route"]["planned"])
    # 计划与建议不能混进已发生事实。
    assert payload["route"]["suggested"] == []
    assert all(item["kind"] != "happened" for item in payload["route"]["planned"])
    # StoryState → 路线 → 全书 / 卷 / 篇章 / 章节。
    assert payload["story_state"]["effect_log"] == len(stored.effect_log)
    assert payload["long_line"]["volumes"] and payload["long_line"]["arcs"] \
        and payload["long_line"]["chapters"]
    assert len(payload["long_line"]["chapters"]) == len(payload["route"]["happened"])
    # 大纲预览条目全部可溯源；无来源条目保持 unresolved。
    assert payload["outline_preview"], "已发生路线应能生成大纲条目"
    assert payload["unresolved"] == []
    assert len(payload["trace"]["verified"]) == len(payload["outline_preview"])
    # 计划阶段只出现在 plans 与 planned，不进入 happened。
    assert [item["id"] for item in payload["plans"]] == ["stage_1", "stage_2"]
    assert payload["history_immutable"] is True
    # 读取不改写事实。
    assert StoryStateRepository(tmp_path).load(blueprint_id, 1, "main").model_dump() == stored.model_dump()


def test_replan_preview_never_touches_history(tmp_path: Path) -> None:
    novel_id = "novel_alpha"
    client = client_for(tmp_path)
    blueprint_id = make_novel(client, novel_id)
    seed_long_line(tmp_path, blueprint_id, novel_id)
    add_future_plan(tmp_path, novel_id)
    before = client.get("/api/story-builder/creator/linkage?novel_id=" + novel_id).json()
    preview = client.get("/api/story-builder/creator/linkage?novel_id=" + novel_id
                         + "&preview=true&changed_stage=stage_1&note=玩家改了选择").json()
    assert preview["replan_preview"]["happened_unchanged"] is True
    assert preview["route"]["happened"] == before["route"]["happened"]
    assert preview["replan_preview"]["plan_revision"] == 2
    stage = next(item for item in preview["replan_preview"]["plan"] if item["id"] == "stage_1")
    assert stage["status"] == "changed" and stage["note"] == "玩家改了选择"
    # 预览不落盘：再次读取没有 future plan 改动，也没有新的 StoryState。
    after = client.get("/api/story-builder/creator/linkage?novel_id=" + novel_id).json()
    assert after["route"]["happened"] == before["route"]["happened"]
    assert "replan_preview" not in after
    stored = StoryStateRepository(tmp_path).load(blueprint_id, 1, "main")
    assert len(stored.effect_log) == before["counts"]["happened"]


def test_linkage_marks_unsourced_items_as_unresolved(tmp_path: Path) -> None:
    from novelforge.story_engine import FuturePlan, StoryState, build_route, verify_outline_sources

    package = build_route(StoryState(novel_id="novel_x"),
                          plan=FuturePlan(stages=[{"id": "s1", "goal": "未来目标"}]))
    trace = verify_outline_sources([{"item_id": "manual_item", "must_keep": ["来源：无"]}], package)
    assert trace.verified == []
    assert trace.unsourced[0]["item_id"] == "manual_item"
    assert trace.unsourced[0]["mark"] == "unresolved"
    # 计划也留在 planned 里，不会被当成已发生条目。
    assert package.happened == [] and [item.id for item in package.planned] == ["planned_s1"]


def test_linkage_panel_preview_and_isolation(tmp_path: Path) -> None:
    first, second = "novel_one", "novel_two"
    client = client_for(tmp_path)
    first_blueprint = make_novel(client, first)
    make_novel(client, second)
    seed_long_line(tmp_path, first_blueprint, first)
    first_payload = client.get("/api/story-builder/creator/linkage?novel_id=" + first).json()
    second_payload = client.get("/api/story-builder/creator/linkage?novel_id=" + second).json()
    assert first_payload["counts"]["happened"] > 0
    assert second_payload["meta"]["preview"] is True
    assert second_payload["counts"]["happened"] == 0
    assert second_payload["outline_preview"] == []
    assert second_payload["long_line"]["chapters"] == []


def test_linkage_view_has_no_second_state_or_genre_branching() -> None:
    for name in ("linkage_view.py", "creator.py", "world_view.py", "character_view.py",
                 "plot_view.py", "progression_view.py", "memory_view.py"):
        text = (PROJECT_ROOT / "src/novelforge/story_engine" / name).read_text(encoding="utf-8")
        for pattern in ("if genre ==", "if world_type ==", "if novel_id ==", "apply_effects(",
                        ".save("):
            assert pattern not in text, f"{name} 违反约束：{pattern}"
