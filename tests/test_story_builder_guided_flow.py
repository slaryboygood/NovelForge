"""W1-04 专项：一句创意 → 题材 → 卖点 → 设定候选 → 自检 → 可运行（并进入动态推演）。"""

from __future__ import annotations

import json
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from novelforge.api.story_builder_routes import install_story_builder_api
from novelforge.story_builder import load_story_catalog
from novelforge.story_engine.creator import RUNTIME_VERSION, runtime_key_for
from novelforge.story_engine.storage import StoryStateRepository

PROJECT_ROOT = Path(__file__).resolve().parents[1]
IDEA = "一个普通维修工发现城市其实运行在一套隐藏的修仙操作系统上。"


def client_for(tmp_path: Path) -> TestClient:
    # 用项目真实内容目录（含三题材演示包）建立隔离数据根，流程与生产一致。
    source = PROJECT_ROOT / "novel" / "config" / "story_engine"
    target = tmp_path / "novel" / "config" / "story_engine"
    target.mkdir(parents=True, exist_ok=True)
    for item in source.glob("*.json"):
        target.joinpath(item.name).write_text(item.read_text(encoding="utf-8"),
                                              encoding="utf-8")
    app = FastAPI()
    install_story_builder_api(app, tmp_path, catalog=load_story_catalog(PROJECT_ROOT))
    return TestClient(app)


def guided_novel(client: TestClient, novel_id: str, idea: str = IDEA,
                 genre: str = "xianxia") -> dict:
    """走完整条引导路径：创意 → 候选 → 保存 → 设定种子 → 保存 → 自检。"""

    assert client.post("/api/story-builder/novels",
                       json={"novel_id": novel_id, "title": novel_id}).status_code == 201
    return guide_existing(client, novel_id, idea=idea, genre=genre)


def guide_existing(client: TestClient, novel_id: str, idea: str = IDEA,
                   genre: str = "xianxia") -> dict:
    """在已存在的小说上走引导路径（不重复创建）。"""

    creative = client.post(f"/api/story-builder/creative/suggest?novel_id={novel_id}",
                           json={"idea": idea})
    assert creative.status_code == 200, creative.text
    suggestion = creative.json()
    assert len(suggestion["genre_candidates"]) >= 3
    brief = client.put(f"/api/story-builder/creative/brief?novel_id={novel_id}", json={
        "original_idea": idea,
        "references": suggestion["references"],
        "reader_experience": "紧张、有推理快感",
        "selected_genre": genre,
        "selected_template_id": "",
        "selected_content_pack_id": "",
        "tone": suggestion["tone_candidates"][0]["tone"],
        "selling_points": [item["text"] for item in suggestion["selling_point_candidates"][:3]],
    })
    assert brief.status_code == 200, brief.text
    seed = client.post(f"/api/story-builder/settings/seed?novel_id={novel_id}", json={}).json()
    saved = client.put(f"/api/story-builder/settings/seed?novel_id={novel_id}",
                       json={"seed": seed["seed"], "selected": seed["seed"]["selected"]})
    assert saved.status_code == 200, saved.text
    report = client.get(f"/api/story-builder/settings/check?novel_id={novel_id}")
    assert report.status_code == 200, report.text
    return {"suggestion": suggestion, "seed": seed, "pack_id": saved.json()["pack_id"],
            "check": report.json()}


def test_guided_flow_reaches_runnable_state_without_handwritten_json(tmp_path: Path) -> None:
    client = client_for(tmp_path)
    flow = guided_novel(client, "novel_guided")
    assert flow["check"]["ok"] is True
    assert flow["check"]["available_candidates"]
    started = client.post("/api/story-builder/runtime/start?novel_id=novel_guided", json={})
    assert started.status_code == 200, started.text
    payload = started.json()
    assert payload["created"] is True and payload["started"] is True
    assert payload["revision"] == 0 and payload["tick"] == 0
    assert payload["available"], "开始推演后第一批候选行动必须非空"
    # 事实真的落盘：小说级运行槽里出现了 StoryState。
    states = StoryStateRepository(tmp_path)
    runtime_id = runtime_key_for("novel_guided")
    assert states.exists(runtime_id, RUNTIME_VERSION, "main")
    state = states.load(runtime_id, RUNTIME_VERSION, "main")
    assert state.characters and state.location.current == "start_place"
    assert state.relationships, "起点关系网必须在事实态里"
    assert "ui_preview" not in state.flags, "落盘事实不得带只读预览标记"
    # 幂等：再次开始不会重置事实。
    again = client.post("/api/story-builder/runtime/start?novel_id=novel_guided", json={})
    assert again.status_code == 200
    assert again.json()["created"] is False
    assert again.json()["revision"] == 0


def test_start_is_gated_by_settings_check(tmp_path: Path) -> None:
    client = client_for(tmp_path)
    client.post("/api/story-builder/novels", json={"novel_id": "novel_gate", "title": "x"})
    missing = client.post("/api/story-builder/runtime/start?novel_id=novel_gate", json={})
    assert missing.status_code == 422
    assert missing.json()["detail"]["code"] == "CONTENT_PACK_REQUIRED"
    guide_existing(client, "novel_gate")
    pack_path = tmp_path / "novel" / "config" / "story_engine" / "novel_gate_pack.json"
    broken = json.loads(pack_path.read_text(encoding="utf-8"))
    broken["actions"] = []
    broken["events"] = []  # 事件引用必须指向真实行动，因此一起清空才仍是合法 schema
    pack_path.write_text(json.dumps(broken, ensure_ascii=False), encoding="utf-8")
    blocked = client.post("/api/story-builder/runtime/start?novel_id=novel_gate", json={})
    assert blocked.status_code == 422
    assert blocked.json()["detail"]["code"] == "SETTINGS_NOT_RUNNABLE"
    assert {item["code"] for item in blocked.json()["detail"]["findings"]} >= {"ACTION_EMPTY"}
    # 修补后可以开始。
    assert client.post("/api/story-builder/settings/check?novel_id=novel_gate",
                       json={"repair": True}).status_code == 200
    assert client.post("/api/story-builder/runtime/start?novel_id=novel_gate",
                       json={}).status_code == 200


def test_runtime_state_and_advance_use_the_persisted_slot(tmp_path: Path) -> None:
    client = client_for(tmp_path)
    guided_novel(client, "novel_run")
    client.post("/api/story-builder/runtime/start?novel_id=novel_run", json={})
    # 没开始时是预览；开始之后 started=true 且来自事实槽。
    state = client.get("/api/story-builder/runtime/state?novel_id=novel_run").json()
    assert state["started"] is True
    assert state["runtime_id"] == runtime_key_for("novel_run")
    assert state["tick"] == 0
    moved = client.post("/api/story-builder/runtime/advance?novel_id=novel_run",
                        json={"action_id": "act_go_work", "expected_revision": 0})
    assert moved.status_code == 200, moved.text
    after = client.get("/api/story-builder/runtime/state?novel_id=novel_run").json()
    assert after["revision"] == 1
    assert after["summary"]["location"] == "work_place"
    # 世界推进（主角不行动）同样写回同一份事实。
    ticked = client.post("/api/story-builder/runtime/tick?novel_id=novel_run",
                         json={"expected_revision": 1})
    assert ticked.status_code == 200, ticked.text
    final = client.get("/api/story-builder/runtime/state?novel_id=novel_run").json()
    assert final["tick"] >= 1
    assert final["available"], "世界推进后候选仍然非空"


def test_seven_creator_panels_read_the_started_facts(tmp_path: Path) -> None:
    client = client_for(tmp_path)
    guided_novel(client, "novel_panels")
    client.post("/api/story-builder/runtime/start?novel_id=novel_panels", json={})
    client.post("/api/story-builder/runtime/advance?novel_id=novel_panels",
                json={"action_id": "act_investigate", "expected_revision": 0})
    state = client.get("/api/story-builder/runtime/state?novel_id=novel_panels").json()
    assert state["started"] is True

    world = client.get("/api/story-builder/creator/world?novel_id=novel_panels")
    assert world.status_code == 200, world.text
    world_data = world.json()
    assert world_data["meta"]["preview"] is False, "面板必须读真实事实，不是预览"
    assert world_data["timeline"]["tick"] == state["summary"]["tick"]
    assert world_data["location"]["current"] == state["summary"]["location"]
    assert world_data["factions"], "势力状态必须来自 StoryState"
    assert world_data["recent_autonomous_actions"], "世界面板必须展示 NPC / 势力自主行动"

    characters = client.get(
        "/api/story-builder/creator/characters?novel_id=novel_panels&character_id=protagonist")
    assert characters.status_code == 200
    character_payload = characters.json()
    rows = character_payload["characters"]
    assert {row["id"] for row in rows} >= {"protagonist", "npc_1"}
    detail = character_payload["detail"]
    assert detail["goals"]["long_term"] and detail["goals"]["stage"] \
        and detail["goals"]["current"], "角色面板必须展示长期 / 阶段 / 当前目标"
    assert detail["relationships"], "角色面板必须展示多维关系"
    assert all(row["dimensions"] for row in detail["relationships"])

    plot = client.get("/api/story-builder/creator/plot?novel_id=novel_panels")
    assert plot.status_code == 200
    plot_data = plot.json()
    assert plot_data["candidates"], "剧情面板必须展示由状态生成的候选行动"
    assert plot_data["unavailable"], "剧情面板必须区分 available / unavailable"
    unavailable_rows = [row for row in plot_data["candidates"] if not row["available"]]
    assert unavailable_rows and all(row["reason"] or row["code"] for row in unavailable_rows), \
        "不可用候选必须给出原因"
    assert plot_data["plots"], "剧情面板必须展示支线"
    assert plot_data["current_events"] is not None

    progression = client.get("/api/story-builder/creator/progression?novel_id=novel_panels")
    assert progression.status_code == 200
    categories = progression.json()["categories"]
    seven = {"ability", "identity", "relationship", "faction", "information", "equipment",
             "skill"}
    assert {row["category"] for row in categories if row["nodes"]} >= seven, \
        "成长面板必须覆盖七类 Progression"

    memory = client.get("/api/story-builder/creator/memory?novel_id=novel_panels")
    assert memory.status_code == 200
    memory_data = memory.json()
    assert memory_data["character_knowledge"]["protagonist"], "记忆面板必须展示角色知识"
    assert {"author", "reader", "character_knowledge"} <= set(memory_data), \
        "记忆面板必须分 author / reader / character 三视角"
    assert memory_data["foreshadows"], "记忆面板必须展示未回收伏笔"
    assert memory_data["open_foreshadows"]

    director = client.get("/api/story-builder/creator/director?novel_id=novel_panels")
    assert director.status_code == 200
    director_data = director.json()
    assert director_data["ranked"], "导演面板必须给出候选事件排序"
    assert director_data["weights"], "导演面板必须展示当前权重"
    assert director_data["why_chosen"] or director_data["note"]

    linkage = client.get("/api/story-builder/creator/linkage?novel_id=novel_panels")
    assert linkage.status_code == 200
    linkage_data = linkage.json()
    assert linkage_data["story_state"]["tick"] == state["summary"]["tick"]
    assert linkage_data["counts"]["happened"] >= 1, "大纲联动必须包含已发生事实"
    assert linkage_data["counts"]["planned"] >= 1, "大纲联动必须包含未来规划"
    assert linkage_data["history_immutable"] is not None


def test_guided_flow_keeps_v1_and_v2_behaviour_intact(tmp_path: Path) -> None:
    """引导流程不能改变「有确认蓝图的小说」原先的存储位置与行为。"""

    client = client_for(tmp_path)
    guided_novel(client, "novel_keep")
    # 没有蓝图时用小说级运行槽。
    client.post("/api/story-builder/runtime/start?novel_id=novel_keep", json={})
    states = StoryStateRepository(tmp_path)
    assert states.exists(runtime_key_for("novel_keep"), RUNTIME_VERSION, "main")
    # 其他小说不受影响：第二本小说有自己的槽，互不覆盖。
    guided_novel(client, "novel_other", idea="一名调查记者追查连环失踪案，发现证词都指向同一份被篡改的档案。",
                 genre="modern_mystery")
    other_state = client.get("/api/story-builder/runtime/state?novel_id=novel_other").json()
    assert other_state["started"] is False, "另一本小说不会因为第一本开始而被动开始"
    assert other_state["revision"] == 0
    assert other_state["summary"]["location"] == "start_place"


def test_guided_flow_frontend_has_no_second_state_or_genre_logic(tmp_path: Path) -> None:
    source = (PROJECT_ROOT / "ui/src/SettingSeedPanel.tsx").read_text(encoding="utf-8")
    for pattern in ("if genre", "if world_type", "xianxia", "sci_fi", "modern_mystery",
                    "硅基升维"):
        assert pattern not in source, f"SettingSeedPanel.tsx 违反约束：{pattern}"
    # 面板只调用 API，不自己算世界状态。
    for marker in ("api.settingSeed", "api.suggestSettingSeed", "api.runSettingsCheck",
                   "api.startRuntime"):
        assert marker in source, f"面板必须通过 API 取数：{marker}"
    routes = (PROJECT_ROOT / "src/novelforge/api/story_builder_routes.py").read_text(
        encoding="utf-8")
    assert '"/runtime/start"' in routes
    assert '"/settings/check"' in routes
