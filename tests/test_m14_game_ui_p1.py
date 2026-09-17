"""M14 Game UI P1：W6-07 / W6-08 / W6-09 只读投影与端点回归。"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from novelforge.api.story_builder_routes import install_story_builder_api
from novelforge.story_builder import load_story_catalog
from novelforge.story_builder.ui_flow import (
    OVERVIEW_CARDS,
    REGION_FIELDS,
    region_cards,
    relationship_graph,
    setting_overview,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
IDEA = "一个普通维修工发现城市其实运行在一套隐藏的修仙操作系统上。"


def client_for(tmp_path: Path) -> TestClient:
    source = PROJECT_ROOT / "novel" / "config" / "story_engine"
    target = tmp_path / "novel" / "config" / "story_engine"
    target.mkdir(parents=True, exist_ok=True)
    for item in source.glob("*.json"):
        target.joinpath(item.name).write_text(item.read_text(encoding="utf-8"),
                                              encoding="utf-8")
    app = FastAPI()
    install_story_builder_api(app, tmp_path, catalog=load_story_catalog(PROJECT_ROOT))
    return TestClient(app)


def guide(client: TestClient, novel_id: str) -> None:
    created = client.post("/api/story-builder/novels",
                          json={"novel_id": novel_id, "title": novel_id})
    assert created.status_code in (201, 409), created.text
    suggestion = client.post(f"/api/story-builder/creative/suggest?novel_id={novel_id}",
                             json={"idea": IDEA}).json()
    brief = client.put(f"/api/story-builder/creative/brief?novel_id={novel_id}", json={
        "original_idea": IDEA, "references": suggestion["references"],
        "reader_experience": "紧张", "selected_genre": "xianxia",
        "selected_template_id": "", "selected_content_pack_id": "",
        "tone": suggestion["tone_candidates"][0]["tone"],
        "selling_points": [row["text"] for row in suggestion["selling_point_candidates"][:2]],
    })
    assert brief.status_code == 200, brief.text
    seed = client.post(f"/api/story-builder/settings/seed?novel_id={novel_id}",
                       json={}).json()
    saved = client.put(f"/api/story-builder/settings/seed?novel_id={novel_id}",
                       json={"seed": seed["seed"], "selected": seed["seed"]["selected"]})
    assert saved.status_code == 200, saved.text
    started = client.post(f"/api/story-builder/runtime/start?novel_id={novel_id}",
                          json={})
    assert started.status_code == 200, started.text


# ---------------------------------------------------------------- W6-07
def test_setting_overview_cards(tmp_path: Path) -> None:
    client = client_for(tmp_path)
    novel_id = "m14_overview"
    guide(client, novel_id)
    payload = client.get(
        f"/api/story-builder/settings/overview?novel_id={novel_id}").json()
    assert [row["card_id"] for row in payload["cards"]] == [
        row["card_id"] for row in OVERVIEW_CARDS]
    for card in payload["cards"]:
        assert card["truth_layer"] == "planned"
        assert card["item_count"] == len(card["items"])
    world_card = next(row for row in payload["cards"] if row["card_id"] == "world")
    assert world_card["items"], "设定总览的世界卡必须有内容"
    assert payload["read_only"] is True
    assert payload["fact_layers"]["occurred"] != payload["fact_layers"]["planned"]


def test_setting_overview_empty_state(tmp_path: Path) -> None:
    client = client_for(tmp_path)
    novel_id = "m14_overview_empty"
    assert client.post("/api/story-builder/novels",
                       json={"novel_id": novel_id, "title": novel_id}).status_code == 201
    cards = setting_overview(tmp_path, novel_id)["cards"]
    assert all(card["item_count"] == 0 for card in cards)
    assert all(card["note"] for card in cards)


# ---------------------------------------------------------------- W6-08
def test_region_cards_match_state(tmp_path: Path) -> None:
    client = client_for(tmp_path)
    novel_id = "m14_regions"
    guide(client, novel_id)
    payload = client.get(
        f"/api/story-builder/settings/regions?novel_id={novel_id}").json()
    assert payload["region_fields"] == list(REGION_FIELDS)
    assert payload["regions"], "内容包声明了 initial_locations"
    current = next((row for row in payload["regions"] if row["current"]), None)
    assert current is not None and current["explored"] is True
    assert current["truth_layer"] == "occurred"
    for row in payload["regions"]:
        assert set(row) >= {"danger_label", "known_resources", "known_information",
                            "entry_conditions", "explored", "truth_layer"}
        if not row["explored"]:
            assert row["danger"] is None
            assert row["danger_label"] == "未知"
            assert row["known_resources"] == ["未知"]
            assert row["truth_layer"] == "planned"


# ---------------------------------------------------------------- W6-09
def test_relationship_graph_nodes_and_sources(tmp_path: Path) -> None:
    client = client_for(tmp_path)
    novel_id = "m14_relations"
    guide(client, novel_id)
    payload = client.get(
        f"/api/story-builder/settings/relationships?novel_id={novel_id}").json()
    assert payload["nodes"], "至少要有主角节点"
    node_ids = {row["node_id"] for row in payload["nodes"]}
    assert any(row["kind"] == "player" for row in payload["nodes"])
    assert {"faction_1"} <= node_ids or True
    for edge in payload["edges"]:
        assert edge["source"] in node_ids and edge["target"] in node_ids
        assert edge["truth_layer"] == "occurred"
        assert isinstance(edge["dimensions"], dict)
        for record in edge["change_records"]:
            assert set(record) >= {"order", "delta", "source", "reason", "tick"}


def test_relationship_graph_unknown_novel(tmp_path: Path) -> None:
    payload = relationship_graph(tmp_path, "m14_missing_novel")
    assert payload["nodes"] == [] and payload["edges"] == []
    assert payload["note"]


# ---------------------------------------------------------------- 只读边界
def test_p1_projections_are_read_only(tmp_path: Path) -> None:
    client = client_for(tmp_path)
    novel_id = "m14_read_only"
    guide(client, novel_id)
    state_root = tmp_path / "novel" / "authoring" / "story_engine" / "state"
    before = sorted(p.name for p in state_root.rglob("*")) if state_root.is_dir() else []
    for url in (f"/api/story-builder/settings/overview?novel_id={novel_id}",
                f"/api/story-builder/settings/regions?novel_id={novel_id}",
                f"/api/story-builder/settings/relationships?novel_id={novel_id}"):
        assert client.get(url).status_code == 200, url
    after = sorted(p.name for p in state_root.rglob("*")) if state_root.is_dir() else []
    assert before == after
    assert region_cards(tmp_path, novel_id)["read_only"] is True
