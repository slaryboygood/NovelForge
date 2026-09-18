"""W1-03 专项：设定自检与起点世界事实（地点可达 / 人物 / 势力 / 关系 / 成长 / 行动 / 事件 / 可初始化）。"""

from __future__ import annotations

import json
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from novelforge.api.story_builder_routes import install_story_builder_api
from novelforge.story_builder import load_story_catalog
from novelforge.story_engine.creative import CreativeBrief, save_creative_brief
from novelforge.story_engine.context import story_state_preview
from novelforge.story_engine.driver import advance_story, runtime_tick
from novelforge.story_engine.profile import NovelProfileRepository
from novelforge.story_engine.settings_check import (
    check_seed,
    repair_and_save,
    repair_pack_draft,
    run_settings_check,
)
from novelforge.story_engine.settings_gen import (
    build_setting_seed,
    load_pack_draft,
    pack_path_for,
    save_setting_seed,
    validate_pack_draft,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
IDEA = "一个普通维修工发现城市其实运行在一套隐藏的修仙操作系统上。"
CRISIS_IDEA = "一名调查记者追查连环失踪案，发现所有证词都指向同一份被篡改的档案。"


def prepare(tmp_path: Path, novel_id: str = "novel_w1", idea: str = IDEA,
            genre: str = "xianxia") -> None:
    save_creative_brief(tmp_path, novel_id,
                        CreativeBrief(original_idea=idea, selected_genre=genre, tone="紧张悬疑"))
    save_setting_seed(tmp_path, novel_id, seed=build_setting_seed(tmp_path, novel_id))


def client_for(tmp_path: Path) -> TestClient:
    app = FastAPI()
    install_story_builder_api(app, tmp_path, catalog=load_story_catalog(PROJECT_ROOT))
    return TestClient(app)


def test_generated_pack_passes_every_check(tmp_path: Path) -> None:
    prepare(tmp_path)
    report = run_settings_check(tmp_path, "novel_w1")
    assert report.ok, [item.as_dict() for item in report.errors()]
    assert not report.errors()
    assert report.pack_id == "novel_w1_pack"
    assert report.available_candidates, "起点必须有可用候选行动"
    # 起点世界事实来自 StoryState（时间 / 地点 / 人物 / 资源 / 支线）。
    assert report.story_state["location"] == "start_place"
    assert report.story_state["tick"] == 0
    assert "protagonist" in report.story_state["characters"]
    assert report.story_state["resources"]
    assert report.story_state["plots"]
    # 被挡住的候选必须给出原因（不是静默隐藏）。
    blocked = {row["action"] for row in report.blocked_candidates}
    assert blocked, "生成的内容包应有需要条件才能执行的行动"
    assert all(row["reason"] or row["code"] for row in report.blocked_candidates)


def test_check_reports_broken_pack_with_readable_findings(tmp_path: Path) -> None:
    prepare(tmp_path)
    path = pack_path_for(tmp_path, "novel_w1_pack")
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["actions"] = []
    payload["events"] = []
    payload["initial_resources"] = {}
    payload["initial_current_location"] = "nowhere"
    payload["initial_plots"] = []
    broken = validate_pack_draft(payload)
    report = run_settings_check(tmp_path, "novel_w1", pack=broken)
    codes = {item.code for item in report.findings}
    assert not report.ok
    assert {"ACTION_EMPTY", "EVENT_EMPTY", "RESOURCE_EMPTY", "START_LOCATION_MISSING",
            "PLOT_EMPTY"} <= codes
    assert all(item.hint for item in report.findings if item.severity == "error")


def test_repair_restores_runnability_without_touching_facts(tmp_path: Path) -> None:
    prepare(tmp_path)
    path = pack_path_for(tmp_path, "novel_w1_pack")
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["actions"] = []
    payload["events"] = []
    payload["initial_resources"] = {}
    payload["initial_current_location"] = "nowhere"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    before = run_settings_check(tmp_path, "novel_w1")
    assert not before.ok
    result = repair_and_save(tmp_path, "novel_w1")
    assert result["fixes"], "修补必须记录改了什么"
    after = run_settings_check(tmp_path, "novel_w1")
    assert after.ok, [item.as_dict() for item in after.errors()]
    assert after.available_candidates, "修补后必须重新出现可用候选"
    # 修补只动内容包（设计态），不写 StoryState 文件。
    assert not (tmp_path / "novel/authoring/story_engine/state").exists()
    repaired = load_pack_draft(tmp_path, "novel_w1_pack")
    assert repaired.initial_current_location in repaired.initial_locations
    # 再次自检幂等：没有缺项时不再改任何东西。
    again = repair_pack_draft(repaired.model_dump(mode="json"))
    assert again[1] == []


def test_initial_relationship_network_is_real_story_state(tmp_path: Path) -> None:
    prepare(tmp_path)
    pack = load_pack_draft(tmp_path, "novel_w1_pack")
    profile = NovelProfileRepository(tmp_path).load("novel_w1")
    state = story_state_preview(profile, pack)
    assert state.relationships, "起点关系网必须真的写进 StoryState"
    character_ids = set(state.characters)
    for row in state.relationships:
        assert row.source_id in character_ids and row.target_id in character_ids
        assert row.dimensions, "关系必须带多维维度"
    npcs = {item.target_id for item in state.relationships}
    assert len(npcs) >= 3, "每个 NPC 至少有一条初始关系"
    # 关系候选里声明的维度被原样带进状态。
    declared = {entry["target_id"]: entry["dimensions"]
                for entry in pack.model_dump(mode="json")["initial_relationships"]}
    for row in state.relationships:
        for dimension, value in declared.get(row.target_id, {}).items():
            assert row.dimensions[dimension] == value


def test_locations_reachable_and_gates_drive_available_set(tmp_path: Path) -> None:
    prepare(tmp_path)
    pack = load_pack_draft(tmp_path, "novel_w1_pack")
    profile = NovelProfileRepository(tmp_path).load("novel_w1")
    state = story_state_preview(profile, pack)
    moved = advance_story(state, pack, action_id="act_go_work", actor="protagonist")
    assert moved.ok and moved.state.location.current == "work_place"
    gated = advance_story(state, pack, action_id="act_go_hidden", actor="protagonist")
    assert gated.ok is False and gated.code == "KNOWLEDGE_MISSING"
    unlocked = advance_story(state, pack, action_id="act_investigate", actor="protagonist")
    assert unlocked.ok
    then_hidden = advance_story(unlocked.state, pack, action_id="act_go_hidden",
                                actor="protagonist")
    assert then_hidden.ok and then_hidden.state.location.current == "hidden_place"
    # 世界推进不依赖主角行动，并且推进后候选仍然非空。
    ticked = runtime_tick(then_hidden.state, pack, actor="protagonist")
    assert ticked.ok and ticked.available_actions


def test_check_api_roundtrip_preview_and_repair(tmp_path: Path) -> None:
    client = client_for(tmp_path)
    assert client.post("/api/story-builder/novels",
                       json={"novel_id": "novel_w1", "title": "自检测试"}).status_code == 201
    # 没有保存设定时自检要明确报错。
    missing = client.get("/api/story-builder/settings/check?novel_id=novel_w1")
    assert missing.status_code == 404
    assert missing.json()["detail"]["code"] == "SETTINGS_PACK_REQUIRED"
    client.put("/api/story-builder/creative/brief?novel_id=novel_w1",
               json={"original_idea": IDEA, "selected_genre": "xianxia", "tone": "紧张悬疑"})
    seed = client.post("/api/story-builder/settings/seed?novel_id=novel_w1", json={}).json()["seed"]
    # 未保存也能先自检（预览）。
    preview = client.post("/api/story-builder/settings/check?novel_id=novel_w1",
                          json={"seed": seed})
    assert preview.status_code == 200, preview.text
    assert preview.json()["available_candidates"]
    saved = client.put("/api/story-builder/settings/seed?novel_id=novel_w1",
                       json={"seed": seed, "selected": seed["selected"]})
    assert saved.status_code == 200
    report = client.get("/api/story-builder/settings/check?novel_id=novel_w1")
    assert report.status_code == 200, report.text
    payload = report.json()
    assert payload["ok"] is True
    assert payload["story_state"]["location"] == "start_place"
    # 打坏内容包 → 自检报错 → 修补后通过。
    path = pack_path_for(tmp_path, "novel_w1_pack")
    broken = json.loads(path.read_text(encoding="utf-8"))
    broken["actions"] = [{"id": "act_locked", "kind": "use", "name": "被锁住的行动",
                          "requirements": [{"op": "identity", "entity": "protagonist",
                                            "value": "ghost_permit"}]}]
    broken["events"] = []
    path.write_text(json.dumps(broken, ensure_ascii=False, indent=2), encoding="utf-8")
    failing = client.get("/api/story-builder/settings/check?novel_id=novel_w1").json()
    assert failing["ok"] is False
    assert "ACTION_NO_AVAILABLE" in {item["code"] for item in failing["findings"]}
    repaired = client.post("/api/story-builder/settings/check?novel_id=novel_w1",
                           json={"repair": True})
    assert repaired.status_code == 200, repaired.text
    assert repaired.json()["applied_fixes"]
    assert repaired.json()["ok"] is True
    assert repaired.json()["available_candidates"]


def test_check_seed_preview_does_not_write(tmp_path: Path) -> None:
    save_creative_brief(tmp_path, "novel_w1", CreativeBrief(original_idea=CRISIS_IDEA,
                                                            selected_genre="modern_mystery"))
    seed = build_setting_seed(tmp_path, "novel_w1")
    report = check_seed(tmp_path, "novel_w1", seed)
    assert report.pack_id == "novel_w1_pack"
    assert report.available_candidates
    assert not pack_path_for(tmp_path, "novel_w1_pack").exists(), "预览自检不得落盘"
    assert "novel_w1_pack" not in json.dumps(
        NovelProfileRepository(tmp_path).load("novel_w1").world_profile, ensure_ascii=False)


def test_check_layer_reuses_engine_and_has_no_hardcoding(tmp_path: Path) -> None:
    source = (PROJECT_ROOT / "src/novelforge/story_engine/settings_check.py").read_text(
        encoding="utf-8")
    for pattern in ("if genre ==", "if world_type ==", "if novel_id ==", "硅基升维", "silicon",
                    "class StoryState(", "class EventCard("):
        assert pattern not in source, f"settings_check.py 违反约束：{pattern}"
    for marker in ("story_state_preview", "candidates_for", "evaluate", "EventCard.model_validate",
                   "validate_pack_draft"):
        assert marker in source, f"settings_check.py 必须复用：{marker}"
    # 检查结果对两本完全不同题材的小说都成立，说明没有题材分支。
    first = tmp_path / "one"
    second = tmp_path / "two"
    prepare(first, "novel_A", IDEA, "xianxia")
    prepare(second, "novel_B", CRISIS_IDEA, "modern_mystery")
    report_a = run_settings_check(first, "novel_A")
    report_b = run_settings_check(second, "novel_B")
    assert report_a.ok and report_b.ok
    assert report_a.available_candidates and report_b.available_candidates
    assert {item.code for item in report_a.errors()} == set()
