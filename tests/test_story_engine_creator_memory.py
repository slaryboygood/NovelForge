"""V2-I-05 记忆面板：三视角知识、承诺 / 债务 / 人情、仇恨来源、冲突与伏笔都来自引擎查询层。"""

from __future__ import annotations

import json
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from novelforge.api.story_builder_routes import install_story_builder_api
from novelforge.story_builder import load_story_catalog
from novelforge.story_engine import (
    Character,
    Foreshadow,
    KnowledgeEntry,
    PromiseState,
    StoryStateRepository,
    record_knowledge,
)
from novelforge.story_engine.entities import EffectRecord, RelationshipState

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PACK_ID = "creator_memory_pack"

PACK_PAYLOAD = {
    "pack_id": PACK_ID,
    "title": "记忆面板测试包",
    "initial_flags": {"journey_revision": 0},
    "initial_resources": {"supplies": 1},
    "foreshadows": [
        {"id": "fs_receipt", "title": "缺失的回执", "status": "planted", "planted_in": "第一章",
         "payoff_in": "第三章", "payoff_condition": {"op": "knowledge", "entity": "protagonist",
                                                     "target": "receipt"},
         "data": {"planted_tick": 1}},
        {"id": "fs_done", "title": "已经回收的伏笔", "status": "resolved", "planted_in": "第一章",
         "payoff_in": "第二章",
         "payoff_condition": {"op": "flag", "key": "clue", "value": True}},
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


def seed_memory(tmp_path: Path, blueprint_id: str, novel_id: str) -> None:
    """写入三视角知识与未解决项；全部走既有数据模型，不新建第二套知识库。"""

    states = StoryStateRepository(tmp_path)
    state = states.load_or_migrate(None, blueprint_id, 1, "main", novel_id=novel_id)[0]
    state.characters["protagonist"] = Character(id="protagonist", name="主角", kind="player")
    state.characters["ally"] = Character(id="ally", name="同行者", kind="npc")
    state.timeline.tick = 3
    # 读者也知道的一条事实；只有主角与同行者知道；只有作者知道的计划。
    state = record_knowledge(state, KnowledgeEntry(id="receipt", holders=["protagonist"],
                                                   source="event", reader_visible=True))
    state = record_knowledge(state, KnowledgeEntry(id="secret_route", holders=["protagonist", "ally"],
                                                   source="event", reader_visible=False))
    state = record_knowledge(state, KnowledgeEntry(id="author_plan", holders=[],
                                                   source="author", certainty="plan"))
    state.knowledge[0] = state.knowledge[0].model_copy(update={"tick": 2})
    state.promises = [
        PromiseState(id="promise_receipt", debtor="protagonist", creditor="ally",
                     description="兑现回执", status="open", source="event",
                     created_tick=1, due_tick=2, data={"obligation_type": "promise"}),
        PromiseState(id="debt_supply", debtor="protagonist", creditor="gate_guard",
                     description="欠一份补给", status="open", source="event",
                     created_tick=1, data={"obligation_type": "debt"}),
        PromiseState(id="favor_done", debtor="ally", creditor="protagonist",
                     description="已经还的人情", status="settled", source="event",
                     created_tick=1, settled_tick=3, data={"obligation_type": "favor"}),
    ]
    state.relationships = [
        RelationshipState(source_id="gate_guard", target_id="protagonist",
                          dimensions={"hostility": 2.0}, tags=["conflict"]),
        RelationshipState(source_id="protagonist", target_id="ally",
                          dimensions={"trust": 1.0, "hostility": 0.0}),
    ]
    state.effect_log.extend([
        EffectRecord(id="rel:1", op="change_relationship", entity="gate_guard",
                     target="protagonist", value=-1.0, source="event:gate_check",
                     order=1, data={"reason": "被拒绝通行", "tick": 2}),
        EffectRecord(id="rel:2", op="change_relationship", entity="gate_guard",
                     target="protagonist", value=-1.0, source="event:gate_check",
                     order=2, data={"reason": "再次被拒", "tick": 3}),
    ])
    states.save(state, blueprint_id, 1, "main")


def test_memory_panel_keeps_three_views_separate(tmp_path: Path) -> None:
    novel_id = "novel_alpha"
    client = client_for(tmp_path)
    blueprint_id = make_novel(client, novel_id)
    seed_memory(tmp_path, blueprint_id, novel_id)
    stored = StoryStateRepository(tmp_path).load(blueprint_id, 1, "main")

    payload = client.get("/api/story-builder/creator/memory?novel_id=" + novel_id).json()
    assert payload["meta"]["persisted"] is True
    author_ids = [item["id"] for item in payload["author"]["entries"]]
    reader_ids = [item["id"] for item in payload["reader"]["entries"]]
    assert "author_plan" in author_ids, "作者计划只在作者层"
    assert "secret_route" not in reader_ids, "读者可见性与角色知情分开"
    assert reader_ids == ["receipt"]
    assert "secret_route" in payload["author"]["author_only"]
    holders = payload["holders"]
    assert holders["receipt"] == ["protagonist"]
    assert holders["secret_route"] == ["protagonist", "ally"]
    assert "author_plan" not in holders, "作者计划不进角色知识索引"
    # 谁知道什么：角色层按 holder 隔离。
    assert [item["id"] for item in payload["character_knowledge"]["ally"]] == ["secret_route"]
    assert "receipt" in payload["reader_only"]["ally"]
    assert payload["reader_only"]["protagonist"] == []
    # 读取不改写事实。
    assert StoryStateRepository(tmp_path).load(blueprint_id, 1, "main").model_dump() == stored.model_dump()


def test_memory_panel_tracks_obligations_conflicts_and_hostility(tmp_path: Path) -> None:
    novel_id = "novel_alpha"
    client = client_for(tmp_path)
    blueprint_id = make_novel(client, novel_id)
    seed_memory(tmp_path, blueprint_id, novel_id)
    payload = client.get("/api/story-builder/creator/memory?novel_id=" + novel_id).json()

    all_ids = [item["id"] for item in payload["obligations"]["all"]]
    assert all_ids == ["promise_receipt", "debt_supply", "favor_done"]
    assert [item["id"] for item in payload["obligations"]["by_kind"]["debt"]] == ["debt_supply"]
    assert [item["id"] for item in payload["obligations"]["by_kind"]["favor"]] == ["favor_done"]
    assert [item["id"] for item in payload["obligations"]["outstanding"]] == ["promise_receipt",
                                                                              "debt_supply"]
    overdued = payload["obligations"]["overdue"]
    assert [item["id"] for item in overdued] == ["promise_receipt"]
    assert overdued[0]["overdue"] is True
    # 仇恨来源可追溯到谁在何时因为什么结仇。
    hostility = payload["hostility"][0]
    assert hostility["source_id"] == "gate_guard" and hostility["hostility"] == 2.0
    assert [item["reason"] for item in hostility["sources"]] == ["被拒绝通行", "再次被拒"]
    assert hostility["latest_tick"] == 3
    # 未解决冲突按类型分组。
    kinds = {row["kind"] for row in payload["conflicts"]}
    assert {"promise", "relationship"} <= kinds
    assert kinds == set(payload["conflicts_by_kind"])


def test_memory_panel_open_foreshadows_only(tmp_path: Path) -> None:
    novel_id = "novel_alpha"
    client = client_for(tmp_path)
    blueprint_id = make_novel(client, novel_id)
    seed_memory(tmp_path, blueprint_id, novel_id)
    payload = client.get("/api/story-builder/creator/memory?novel_id=" + novel_id).json()
    assert [item["id"] for item in payload["open_foreshadows"]] == ["fs_receipt"]
    assert [item["id"] for item in payload["foreshadows"]] == ["fs_receipt", "fs_done"]
    open_row = payload["open_foreshadows"][0]
    assert open_row["status"] == "planted"
    assert open_row["has_payoff_condition"] is True
    # 主角已经知道 receipt，因此回收条件满足；但仍必须保持 planted，不能自动算已回收。
    assert open_row["payoff_ready"] is True
    assert open_row["status"] == "planted"
    assert payload["counts"]["open_foreshadows"] == 1


def test_memory_panel_preview_and_isolation(tmp_path: Path) -> None:
    first, second = "novel_one", "novel_two"
    client = client_for(tmp_path)
    first_blueprint = make_novel(client, first)
    make_novel(client, second)
    seed_memory(tmp_path, first_blueprint, first)
    first_payload = client.get("/api/story-builder/creator/memory?novel_id=" + first).json()
    second_payload = client.get("/api/story-builder/creator/memory?novel_id=" + second).json()
    assert first_payload["meta"]["persisted"] is True
    assert second_payload["meta"]["preview"] is True
    assert [item["id"] for item in first_payload["obligations"]["all"]] == [
        "promise_receipt", "debt_supply", "favor_done"]
    assert second_payload["obligations"]["all"] == []
    assert second_payload["hostility"] == []
    # 伏笔定义来自内容包，两本小说都能看到定义，但状态各自独立。
    assert [item["id"] for item in second_payload["foreshadows"]] == ["fs_receipt", "fs_done"]
    assert second_payload["counts"]["character"] == 0


def test_memory_view_has_no_second_state_or_genre_branching() -> None:
    for name in ("memory_view.py", "creator.py", "world_view.py", "character_view.py",
                 "plot_view.py", "progression_view.py"):
        text = (PROJECT_ROOT / "src/novelforge/story_engine" / name).read_text(encoding="utf-8")
        for pattern in ("if genre ==", "if world_type ==", "if novel_id ==", ".save(", "apply_effects("):
            assert pattern not in text, f"{name} 违反约束：{pattern}"
    assert Foreshadow(id="fs", title="t", status="planned").status == "planned"
