"""V2-J 三题材长期验证：同一引擎、同一 Progression、同一导演跑三条长线。"""

from __future__ import annotations

import json
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from novelforge.api.story_builder_routes import install_story_builder_api
from novelforge.story_builder import load_story_catalog
from novelforge.story_engine import (
    AutonomousRule,
    Character,
    EventCardCatalog,
    Faction,
    KnowledgeEntry,
    Location,
    PlotTrack,
    ResourceStock,
    StoryState,
    StoryStateRepository,
    build_route,
    plot_snapshot,
    progression_snapshot,
    record_knowledge,
    run_world_events,
    run_world_tick,
    split_long_line,
    upsert_plot,
    world_snapshot,
)
from novelforge.story_engine.creator import CreatorContext
from novelforge.story_engine.entities import EffectRecord
from novelforge.story_engine.narrative import outline_items_from_route, verify_outline_sources

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PACK_IDS = ("xianxia_demo", "sci_fi_demo", "mystery_demo")
LONG_CHAPTERS = 22


def install_pack(tmp_path: Path, pack_id: str) -> None:
    source = json.loads((PROJECT_ROOT / "novel/config/story_engine/genre_packs.json")
                        .read_text(encoding="utf-8-sig"))
    payload = next(item for item in source["packs"] if item["pack_id"] == pack_id)
    target = tmp_path / "novel" / "config" / "story_engine"
    target.mkdir(parents=True, exist_ok=True)
    (target / f"{pack_id}.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def client_for(tmp_path: Path, pack_id: str) -> TestClient:
    install_pack(tmp_path, pack_id)
    app = FastAPI()
    install_story_builder_api(app, tmp_path, catalog=load_story_catalog(PROJECT_ROOT))
    return TestClient(app)


def make_novel(client: TestClient, novel_id: str, pack_id: str) -> str:
    created = client.post("/api/story-builder/novels", json={
        "novel_id": novel_id, "title": novel_id, "content_pack_id": pack_id})
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


def pack_of(pack_id: str):
    source = json.loads((PROJECT_ROOT / "novel/config/story_engine/genre_packs.json")
                        .read_text(encoding="utf-8-sig"))
    payload = next(item for item in source["packs"] if item["pack_id"] == pack_id)
    from novelforge.story_engine import content_pack_from_payload

    return content_pack_from_payload(payload)


def seed_long_line(tmp_path: Path, blueprint_id: str, novel_id: str, pack_id: str) -> StoryState:
    """按内容包声明装载起点世界，跑一段长线并写回 StoryState。"""

    pack = pack_of(pack_id)
    states = StoryStateRepository(tmp_path)
    state = StoryState(novel_id=novel_id, flags=dict(pack.initial_flags))
    state.characters["protagonist"] = Character(id="protagonist", name="主角", kind="player")
    for key, amount in pack.initial_resources.items():
        state.resources[key] = ResourceStock(id=key, amount=float(amount), unit="份",
                                             holders=["protagonist"])
    for location_id, payload in pack.initial_locations.items():
        state.location.known[location_id] = Location.model_validate({"id": location_id, **payload})
    state.location.current = pack.initial_current_location
    state.location.visited = [pack.initial_current_location] if pack.initial_current_location else []
    for faction_id, payload in pack.initial_factions.items():
        state.factions[faction_id] = Faction.model_validate({"id": faction_id, **payload})
    for character_id, payload in pack.initial_characters.items():
        state.characters[character_id] = Character.model_validate({"id": character_id, **payload})
    for track in pack.initial_plots:
        payload = dict(track)
        plot_id = str(payload.pop("id", ""))
        state = upsert_plot(state, PlotTrack(id=plot_id, **payload))
    # 长线：22 次实际选择 + 世界自主行动 + 世界事件。
    state.flags["clue"] = True
    state.flags["ally"] = True
    state.flags["journey_revision"] = 3
    if pack.progressions:
        state.flags["progression"] = [pack.progressions[0].nodes[0].id]
    state = record_knowledge(state, KnowledgeEntry(id=f"{pack_id}_receipt", holders=["protagonist"],
                                                   source="event", reader_visible=True))
    for index in range(1, LONG_CHAPTERS + 1):
        action = pack.actions[index % len(pack.actions)].id if pack.actions else f"action_{index}"
        state.effect_log.append(EffectRecord(
            id=f"choice:{index}", op="choice", entity="protagonist", target=action,
            order=index, data={"result": f"{pack_id} 第 {index} 次选择的结果", "tick": index,
                               "location": state.location.current}))
    rules = [AutonomousRule.model_validate(item) for item in pack.autonomous_rules]
    ticked = run_world_tick(state, pack, rules)
    catalog = EventCardCatalog(catalog_id=pack_id, cards=list(pack.events))
    events = run_world_events(ticked.state, catalog)
    states.save(events.state, blueprint_id, 1, "main")
    return events.state


def context_for(tmp_path: Path, novel_id: str, blueprint_id: str, pack_id: str) -> CreatorContext:
    from novelforge.story_engine import NovelProfileRepository

    state = StoryStateRepository(tmp_path).load(blueprint_id, 1, "main")
    profile = NovelProfileRepository(tmp_path).load(novel_id)
    return CreatorContext(novel_id=novel_id, project_root=tmp_path, profile=profile,
                          pack=pack_of(pack_id), state=state, blueprint_id=blueprint_id,
                          blueprint_version=1, branch_id="main", persisted=True)


def test_three_genres_produce_three_volumes_and_five_arcs(tmp_path: Path) -> None:
    for pack_id in PACK_IDS:
        novel_id = f"novel_long_{pack_id}"
        client = client_for(tmp_path, pack_id)
        blueprint_id = make_novel(client, novel_id, pack_id)
        state = seed_long_line(tmp_path, blueprint_id, novel_id, pack_id)
        # 世界推进：NPC / 势力自主行动 + 世界事件都在主角之外发生。
        assert [item.op for item in state.effect_log].count("world_action") >= 1
        assert [item.op for item in state.effect_log].count("world_event") >= 1
        package = build_route(state)
        plan = split_long_line(package, chapters_per_arc=4, arcs_per_volume=2)
        assert len(plan.chapters) >= 20, f"{pack_id} 长线应至少 20 章"
        assert len(plan.arcs) >= 5, f"{pack_id} 长线应至少 5 篇章"
        assert len(plan.volumes) >= 3, f"{pack_id} 长线应至少 3 卷"
        items = outline_items_from_route(package)
        assert len(verify_outline_sources(items, package).unsourced) == 0
        # 同一引擎的导演与成长：合法事件可排序，七类成长可判定。
        context = context_for(tmp_path, novel_id, blueprint_id, pack_id)
        slots = progression_snapshot(context)
        assert [item["category"] for item in slots["categories"]] == [
            "progression", "ability", "identity", "relationship", "faction",
            "information", "equipment", "skill"]
        assert slots["owned"], f"{pack_id} 应至少有一个 owned 节点"
        assert all(item["nodes"] for item in slots["categories"]), f"{pack_id} 七类成长都应有节点"
        # 世界面板必须显示同一批事实。
        world = world_snapshot(context, feed_limit=5)
        assert world["meta"]["persisted"] is True
        assert world["factions"], f"{pack_id} 应装载势力事实"
        assert world["recent_autonomous_actions"], f"{pack_id} 应有自主行动记录"
        assert world["recent_world_events"], f"{pack_id} 应有世界事件记录"
        assert world["timeline"]["world_ticks"] >= 1


def test_long_lines_share_one_engine_and_one_progression(tmp_path: Path) -> None:
    """J-04 交叉检查：三种题材各自产出长线，引擎与成长树都没有题材分支。"""

    contexts = {}
    for pack_id in PACK_IDS:
        novel_id = f"novel_cross_{pack_id}"
        client = client_for(tmp_path, pack_id)
        blueprint_id = make_novel(client, novel_id, pack_id)
        seed_long_line(tmp_path, blueprint_id, novel_id, pack_id)
        contexts[pack_id] = context_for(tmp_path, novel_id, blueprint_id, pack_id)
    for pack_id, context in contexts.items():
        snapshot = progression_snapshot(context)
        assert snapshot["trees"], f"{pack_id} 应有通用成长树"
        owned = set(snapshot["owned"])
        assert owned, f"{pack_id} 应该已有 owned 节点"
    # 三个题材的成长节点 id 完全一致：同一套 Progression，只是数据不同。
    node_ids = {pack_id: sorted(node["id"] for tree in progression_snapshot(context)["trees"]
                                for node in tree["nodes"])
                for pack_id, context in contexts.items()}
    assert len({tuple(value) for value in node_ids.values()}) == 1
    # 导演与剧情：三个题材产生同样的结构，不做题材分支。
    for pack_id, context in contexts.items():
        plot = plot_snapshot(context)
        assert plot["candidates"], f"{pack_id} 应有候选行动"
        assert plot["active_plots"], f"{pack_id} 应有活跃支线"
        assert plot["event_chain"], f"{pack_id} 应有事件连锁"


def test_long_line_views_stay_consistent_with_api(tmp_path: Path) -> None:
    pack_id = PACK_IDS[0]
    novel_id = f"novel_api_{pack_id}"
    client = client_for(tmp_path, pack_id)
    blueprint_id = make_novel(client, novel_id, pack_id)
    state = seed_long_line(tmp_path, blueprint_id, novel_id, pack_id)
    world = client.get("/api/story-builder/creator/world?novel_id=" + novel_id).json()
    assert world["timeline"]["tick"] == state.timeline.tick
    assert [item["id"] for item in world["factions"]] == sorted(state.factions)
    linkage = client.get("/api/story-builder/creator/linkage?novel_id=" + novel_id).json()
    package = build_route(state)
    assert linkage["counts"]["happened"] == len(package.happened)
    assert linkage["counts"]["happened"] >= LONG_CHAPTERS
    assert len(linkage["long_line"]["volumes"]) >= 3
    memory = client.get("/api/story-builder/creator/memory?novel_id=" + novel_id).json()
    assert memory["meta"]["persisted"] is True
    assert memory["counts"]["character"] >= 1
