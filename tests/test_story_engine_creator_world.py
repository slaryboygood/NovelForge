"""V2-I-01 世界面板：数据必须来自 StoryState / Engine API，不出现第二套世界状态。"""

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
    Condition,
    ContentPack,
    EventCardCatalog,
    Faction,
    Location,
    ResourceStock,
    StoryStateRepository,
    load_pack_from_project,
    run_world_events,
    run_world_tick,
)
from novelforge.story_engine.world_view import world_snapshot

PROJECT_ROOT = Path(__file__).resolve().parents[1]
NEW_ACTION = "inspect_ledger"
PACK_ID = "creator_ui_pack"
EVENT_TITLE = "闸口盘查"

# 测试内容包：只声明通用结构，不绑定任何题材或小说。
PACK_PAYLOAD = {
    "pack_id": PACK_ID,
    "title": "创作者 UI 测试包",
    "initial_flags": {"journey_revision": 0, "clue": False},
    "initial_resources": {"supplies": 2},
    "actions": [
        {"id": "guard_probe", "kind": "investigate", "name": "核对记录",
         "requirements": [{"op": "resource", "key": "supplies", "value": 1, "comparator": ">="}],
         "costs": [{"op": "remove_resource", "target": "supplies", "value": 1}]},
    ],
    "events": [
        {"event_id": "gate_check", "title": EVENT_TITLE, "kind": "main", "priority": 3,
         "once_only": False, "trigger": {"op": "flag", "key": "clue", "value": True}},
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


def world_pack(pack_id: str) -> ContentPack:
    pack = ContentPack.model_validate(PACK_PAYLOAD)
    event = pack.events[0].model_copy(update={
        "scope": "world", "once_only": False, "knowledge_id": "world_secret",
        "reader_visible": True,
        "trigger": Condition(op="flag", key="clue", value=True)})
    action = pack.actions[0].model_copy(update={"id": NEW_ACTION, "name": "例行盘点"})
    return pack.model_copy(update={"actions": list(pack.actions) + [action],
                                   "events": [event] + list(pack.events[1:])})


def seed_world(tmp_path: Path, blueprint_id: str, novel_id: str) -> tuple[str, str]:
    """写入世界事实：地点、势力、NPC 自主行动、世界事件；返回所用到的事件与行动 id。"""

    pack = world_pack(PACK_ID)
    states = StoryStateRepository(tmp_path)
    state = states.load_or_migrate(None, blueprint_id, 1, "main", novel_id=novel_id)[0]
    state.flags["clue"] = True
    state.resources["supplies"] = ResourceStock(id="supplies", amount=2, unit="份", holders=["warden"])
    state.location.current = "dock"
    state.location.known["dock"] = Location(id="dock", name="北码头", kind="harbor",
                                            access="需要通行证",
                                            data={"control": "gate_guard", "danger": 2})
    state.location.visited = ["dock"]
    state.factions["gate_guard"] = Faction(id="gate_guard", name="闸口守卫", kind="faction",
                                           stance="中立", data={"influence": 4,
                                                                "internal_conflicts": ["换班纠纷"]})
    state.characters["warden"] = Character(id="warden", name="老看守", kind="npc")
    event_id = pack.events[0].event_id
    ticked = run_world_tick(state, pack, [AutonomousRule(actor_id="warden", action_id=NEW_ACTION,
                                                         label="例行检查", once=True)])
    events = run_world_events(ticked.state, _catalog(pack))
    states.save(events.state, blueprint_id, 1, "main")
    return event_id, NEW_ACTION


def _catalog(pack: ContentPack) -> EventCardCatalog:
    return EventCardCatalog(catalog_id="test", cards=list(pack.events))


def test_world_panel_matches_story_state_and_does_not_write(tmp_path: Path) -> None:
    novel_id = "novel_alpha"
    client = client_for(tmp_path)
    blueprint_id = make_novel(client, novel_id)
    event_id, action_id = seed_world(tmp_path, blueprint_id, novel_id)

    payload = client.get("/api/story-builder/creator/world?novel_id=" + novel_id).json()
    stored = StoryStateRepository(tmp_path).load(blueprint_id, 1, "main")
    # 预览/落盘标志与实际存档一致。
    assert payload["meta"]["persisted"] is True and payload["meta"]["preview"] is False
    assert payload["meta"]["blueprint_id"] == blueprint_id
    assert payload["timeline"] == {"tick": stored.timeline.tick, "current_time": stored.timeline.current_time,
                                   "elapsed": stored.timeline.elapsed, "markers": list(stored.timeline.markers),
                                   "world_ticks": sum(1 for item in stored.effect_log if item.op == "world_tick")}
    assert payload["location"]["current"] == stored.location.current == "dock"
    assert payload["location"]["name"] == "北码头"
    assert payload["location"]["control"] == "gate_guard" and payload["location"]["danger"] == 2
    assert [item["id"] for item in payload["factions"]] == ["gate_guard"]
    assert payload["factions"][0]["influence"] == 4
    assert payload["factions"][0]["internal_conflicts"] == ["换班纠纷"]
    assert [item["event_id"] for item in payload["recent_world_events"]] == [event_id]
    assert payload["recent_world_events"][0]["title"] == EVENT_TITLE
    # NPC 自主行动来自 world_action，主角不参与也会出现。
    actions = payload["recent_autonomous_actions"]
    assert [item["action_id"] for item in actions] == [action_id]
    assert actions[0]["actor_id"] == "warden" and actions[0]["actor_label"] == "老看守"
    # 读取接口不修改事实。
    assert StoryStateRepository(tmp_path).load(blueprint_id, 1, "main").model_dump() == stored.model_dump()


def test_preview_state_is_read_only_and_not_persisted(tmp_path: Path) -> None:
    novel_id = "novel_beta"
    client = client_for(tmp_path)
    blueprint_id = make_novel(client, novel_id)
    payload = client.get("/api/story-builder/creator/world?novel_id=" + novel_id).json()
    assert payload["meta"]["preview"] is True and payload["meta"]["persisted"] is False
    assert payload["meta"]["blueprint_id"] == blueprint_id
    assert StoryStateRepository(tmp_path).exists(blueprint_id, 1, "main") is False
    # 预览也要与内容包声明的初始事实一致，不能凭空造数据。
    pack = load_pack_from_project(tmp_path, PACK_ID)
    assert {item["id"] for item in payload["resources"]} == set(pack.initial_resources)
    assert set(payload["world_flags"]) == {"clue"}
    assert [item["amount"] for item in payload["resources"]] == [pack.initial_resources["supplies"]]


def test_reading_does_not_pollute_other_novels(tmp_path: Path) -> None:
    first, second = "novel_one", "novel_two"
    client = client_for(tmp_path)
    first_blueprint = make_novel(client, first)
    make_novel(client, second)
    seed_world(tmp_path, first_blueprint, first)
    first_payload = client.get("/api/story-builder/creator/world?novel_id=" + first).json()
    second_payload = client.get("/api/story-builder/creator/world?novel_id=" + second).json()
    assert first_payload["meta"]["novel_id"] == first and first_payload["meta"]["persisted"] is True
    assert second_payload["meta"]["novel_id"] == second and second_payload["meta"]["persisted"] is False
    assert second_payload["recent_autonomous_actions"] == []
    assert [item["id"] for item in first_payload["factions"]] == ["gate_guard"]
    assert second_payload["factions"] == []
    # 读第二本小说不会给第一本写任何东西。
    stored = StoryStateRepository(tmp_path).load(first_blueprint, 1, "main")
    assert list(stored.factions) == ["gate_guard"]
    assert StoryStateRepository(tmp_path).exists(first_blueprint, 1, "main") is True


def test_world_view_has_no_second_state_or_genre_branching() -> None:
    source = "".join((PROJECT_ROOT / "src/novelforge/story_engine" / name).read_text(encoding="utf-8")
                     for name in ("creator.py", "world_view.py"))
    for pattern in ("if genre ==", "if world_type ==", "if novel_id ==", "world_state =", "class WorldState("):
        assert pattern not in source, pattern
    # 视图是只读投影：模块里没有写状态的调用。
    for name in ("creator.py", "world_view.py"):
        text = (PROJECT_ROOT / "src/novelforge/story_engine" / name).read_text(encoding="utf-8")
        for forbidden in (".save(", "apply_effects(", "StoryStateRepository."):
            assert forbidden not in text, f"{name} 不应写入状态：{forbidden}"


def test_legacy_saves_still_open_in_creator_panels(tmp_path: Path) -> None:
    """V2-J-06：旧存档（V1 StoryState 载荷 / 旧 Adventure 载荷）仍能被创作者面板读取。"""

    from novelforge.story_engine import from_legacy_adventure, story_state_from_payload

    novel_id = "novel_legacy"
    client = client_for(tmp_path)
    blueprint_id = make_novel(client, novel_id)
    legacy_adventure = {"blueprint_id": blueprint_id, "blueprint_version": 1, "revision": 3,
                        "rules_version": 2, "supplies": 1, "ally": True, "clue": True,
                        "trust": 1, "debt": 0, "facts": ["receipt"],
                        "history": [{"scene": "第一关", "choice": "帮助同行者",
                                     "result": "同行者愿意协助"}]}
    state = from_legacy_adventure(legacy_adventure, novel_id=novel_id)
    # 旧存档缺字段的载荷也要能升级读取，而不是被拒绝。
    upgraded = story_state_from_payload({"schema_version": 1, "novel_id": novel_id})
    assert upgraded.schema_version >= 6
    StoryStateRepository(tmp_path).save(state, blueprint_id, 1, "main")

    world = client.get("/api/story-builder/creator/world?novel_id=" + novel_id).json()
    assert world["meta"]["persisted"] is True
    # 旧 Adventure 的 facts 在迁移后属于主角持有的知识，不会变成“所有人知道”。
    memory = client.get("/api/story-builder/creator/memory?novel_id=" + novel_id).json()
    assert [item["id"] for item in memory["reader"]["entries"]] == ["receipt"]
    assert memory["holders"]["receipt"] == ["protagonist"]
    assert memory["character_knowledge"]["protagonist"]
    # 旧存档没有支线 / 成长树时不编造内容。
    plot = client.get("/api/story-builder/creator/plot?novel_id=" + novel_id).json()
    assert plot["active_plots"] == []
    growth = client.get("/api/story-builder/creator/progression?novel_id=" + novel_id).json()
    assert growth["counts"]["owned"] == 0
