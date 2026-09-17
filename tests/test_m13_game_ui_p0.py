"""M13 Game UI P0：W6-01 / W6-03 / W6-04 / W6-05 的只读投影与边界回归。"""

from __future__ import annotations

import json
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from novelforge.api.story_builder_routes import install_story_builder_api
from novelforge.story_builder import load_story_catalog
from novelforge.story_builder.ui_flow import (
    FINDING_GROUPS,
    GROUP_PACK_SECTIONS,
    GROUP_PROFILE_FIELDS,
    GUIDED_STEPS,
    guided_flow_state,
    setting_impact,
)
from novelforge.story_engine.settings_check import run_settings_check
from novelforge.story_engine.settings_gen import SELECTABLE_GROUPS

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


def guide(client: TestClient, novel_id: str) -> dict:
    """走到「设定已保存 + 自检」：W6-01 的前三步。"""

    created = client.post("/api/story-builder/novels",
                          json={"novel_id": novel_id, "title": novel_id})
    assert created.status_code in (201, 409), created.text
    suggestion = client.post(f"/api/story-builder/creative/suggest?novel_id={novel_id}",
                             json={"idea": IDEA}).json()
    brief = client.put(f"/api/story-builder/creative/brief?novel_id={novel_id}", json={
        "original_idea": IDEA, "references": suggestion["references"],
        "reader_experience": "紧张、有推理快感", "selected_genre": "xianxia",
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
    return {"suggestion": suggestion, "seed": seed, "pack_id": saved.json()["pack_id"]}


# ---------------------------------------------------------------- W6-01
def test_guided_flow_steps_and_next_step(tmp_path: Path) -> None:
    client = client_for(tmp_path)
    novel_id = "m13_guided_probe"
    assert client.post("/api/story-builder/novels",
                       json={"novel_id": novel_id, "title": novel_id}).status_code == 201

    fresh = client.get(f"/api/story-builder/guided-flow?novel_id={novel_id}").json()
    assert [row["step_id"] for row in fresh["steps"]] == [row["step_id"]
                                                          for row in GUIDED_STEPS]
    assert fresh["current_step"] == "idea"
    assert fresh["next_step"]["step_id"] == "idea"
    assert fresh["current_stage"] == "design"
    assert fresh["facts"]["creative_brief_saved"] is False
    assert fresh["fact_layers"]["occurred"] and fresh["fact_layers"]["planned"]
    assert fresh["read_only"] is True

    guide(client, novel_id)
    after_settings = client.get(
        f"/api/story-builder/guided-flow?novel_id={novel_id}").json()
    statuses = {row["step_id"]: row["status"] for row in after_settings["steps"]}
    assert statuses["idea"] == "done" and statuses["settings"] == "done"
    assert after_settings["facts"]["content_pack_ready"] is True
    assert after_settings["next_step"]["step_id"] in ("check", "runtime")

    started = client.post(f"/api/story-builder/runtime/start?novel_id={novel_id}",
                          json={})
    assert started.status_code == 200, started.text
    done = client.get(f"/api/story-builder/guided-flow?novel_id={novel_id}").json()
    assert all(row["status"] == "done" for row in done["steps"])
    assert done["facts"]["runtime_started"] is True
    assert done["next_step"]["stage"] == "output"
    assert done["context"]["novel_id"] == novel_id


def test_guided_flow_blocked_check_points_at_candidate_group(tmp_path: Path) -> None:
    """W6-05：自检失败 → 对应候选组（深链接目标来自 API，不靠文案）。"""

    client = client_for(tmp_path)
    novel_id = "m13_guided_blocked"
    guide(client, novel_id)
    pack_id = client.get(
        f"/api/story-builder/settings/seed?novel_id={novel_id}").json()["pack_id"]
    pack_path = (tmp_path / "novel" / "authoring" / "story_engine" / "content_packs"
                 / f"{pack_id}.json")
    if not pack_path.is_file():
        candidates = list((tmp_path / "novel").rglob(f"{pack_id}.json"))
        assert candidates, "内容包文件必须存在"
        pack_path = candidates[0]
    payload = json.loads(pack_path.read_text(encoding="utf-8"))
    payload["initial_resources"] = {}
    pack_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    report = run_settings_check(tmp_path, novel_id)
    assert report.ok is False
    codes = {row.code for row in report.findings}
    assert codes & set(FINDING_GROUPS), codes
    flow = client.get(f"/api/story-builder/guided-flow?novel_id={novel_id}").json()
    statuses = {row["step_id"]: row["status"] for row in flow["steps"]}
    assert statuses["check"] == "blocked"
    check_step = next(row for row in flow["steps"] if row["step_id"] == "check")
    assert check_step["deep_link"]["panel"] == "builder"
    assert check_step["deep_link"]["group"] in SELECTABLE_GROUPS
    assert check_step["deep_link"]["group"] == FINDING_GROUPS[
        next(row.code for row in report.findings
             if row.code in FINDING_GROUPS and row.severity == "error")]


# ---------------------------------------------------------------- W6-04
def test_setting_impact_matches_pack_structure(tmp_path: Path) -> None:
    client = client_for(tmp_path)
    novel_id = "m13_impact_probe"
    guide(client, novel_id)
    payload = client.get(
        f"/api/story-builder/settings/impact?novel_id={novel_id}").json()
    assert payload["pack_ready"] is True
    assert [row["group"] for row in payload["groups"]] == list(SELECTABLE_GROUPS)
    pack = client.get(
        f"/api/story-builder/settings/seed?novel_id={novel_id}").json()["pack"]
    for row in payload["groups"]:
        assert row["profile_fields"] == list(GROUP_PROFILE_FIELDS[row["group"]])
        assert row["pack_sections"] == list(GROUP_PACK_SECTIONS[row["group"]])
        assert set(row["section_presence"]) == set(row["pack_sections"])
        for section, present in row["section_presence"].items():
            assert present is bool(pack.get(section)), section
        for candidate in row["candidates"]:
            assert set(candidate) >= {"id", "label", "summary", "reason", "selected",
                                      "impact"}
            assert candidate["impact"]["profile_fields"] == row["profile_fields"]
            assert candidate["impact"]["pack_sections"] == row["pack_sections"]
            assert candidate["impact"]["unlock_action_ids"] == [
                item["action_id"] for item in row["unlocks"]]
        for unlock in row["unlocks"]:
            assert unlock["requirement_ops"]
            assert set(unlock["matched_ops"]) <= set(row["unlock_ops"])
            assert unlock["action_id"] in {action["id"] for action in pack["actions"]}


def test_setting_impact_group_filter_and_unknown_group(tmp_path: Path) -> None:
    client = client_for(tmp_path)
    novel_id = "m13_impact_filter"
    guide(client, novel_id)
    one = client.get(
        f"/api/story-builder/settings/impact?novel_id={novel_id}&group=world_rules").json()
    assert [row["group"] for row in one["groups"]] == ["world_rules"]
    bad = client.get(
        f"/api/story-builder/settings/impact?novel_id={novel_id}&group=nope")
    assert bad.status_code == 422
    assert bad.json()["detail"]["code"] == "SETTINGS_GROUP_UNKNOWN"


def test_setting_impact_before_pack_saved(tmp_path: Path) -> None:
    client = client_for(tmp_path)
    novel_id = "m13_impact_empty"
    assert client.post("/api/story-builder/novels",
                       json={"novel_id": novel_id, "title": novel_id}).status_code == 201
    payload = client.get(
        f"/api/story-builder/settings/impact?novel_id={novel_id}").json()
    assert payload["pack_ready"] is False
    assert payload["note"]
    for row in payload["groups"]:
        assert row["unlocks"] == []
        assert all(value is False for value in row["section_presence"].values())


# ---------------------------------------------------------------- 只读边界
def test_projections_are_read_only(tmp_path: Path) -> None:
    """W6-01/03/04/05 的投影不得写入 NovelProfile / StoryState。"""

    client = client_for(tmp_path)
    novel_id = "m13_read_only_probe"
    guide(client, novel_id)
    profile = (tmp_path / "novel" / "authoring" / "story_engine" / "profiles"
               / f"{novel_id}.json")
    state_root = tmp_path / "novel" / "authoring" / "story_engine" / "state"
    before_profile = profile.read_bytes() if profile.is_file() else b""
    before_state = sorted(p.name for p in state_root.rglob("*")) if state_root.is_dir() else []
    for url in (f"/api/story-builder/guided-flow?novel_id={novel_id}",
                f"/api/story-builder/settings/impact?novel_id={novel_id}",
                f"/api/story-builder/settings/impact?novel_id={novel_id}&group=progression"):
        assert client.get(url).status_code == 200, url
    after_profile = profile.read_bytes() if profile.is_file() else b""
    after_state = sorted(p.name for p in state_root.rglob("*")) if state_root.is_dir() else []
    assert before_profile == after_profile
    assert before_state == after_state


def test_finding_group_mapping_covers_checker_codes() -> None:
    """W6-05：自检 finder 的每个 code 都必须能定位到一个候选组。"""

    source = (PROJECT_ROOT / "src" / "novelforge" / "story_engine"
              / "settings_check.py").read_text(encoding="utf-8")
    codes = set()
    marker = '_finding("'
    index = source.find(marker)
    while index != -1:
        end = source.find('"', index + len(marker))
        codes.add(source[index + len(marker):end])
        index = source.find(marker, end)
    assert codes
    assert codes <= set(FINDING_GROUPS), sorted(codes - set(FINDING_GROUPS))
    assert set(FINDING_GROUPS.values()) <= set(SELECTABLE_GROUPS)


def test_guided_flow_projection_direct_call(tmp_path: Path) -> None:
    client = client_for(tmp_path)
    novel_id = "m13_direct_probe"
    guide(client, novel_id)
    flow = guided_flow_state(tmp_path, novel_id)
    impact = setting_impact(tmp_path, novel_id)
    assert flow["current_step"] in {"check", "runtime"}
    assert impact["finding_groups"] == FINDING_GROUPS
    assert impact["read_only"] is True and flow["read_only"] is True
