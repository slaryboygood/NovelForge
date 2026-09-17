"""Product V3 UI Foundation：作者旅程 / 目标 / 下一步 应用层投影的回归。

这些用例同时守卫 V3 的三条硬边界：

* 投影只读（不产生 StoryState / 内容包文件）；
* 每个 stage / objective / risk 都有 evidence，不出现演示数字；
* 同一个真实状态下重复调用得到完全一致的结果（确定性）。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from novelforge.api.story_builder_routes import install_story_builder_api
from novelforge.story_builder import load_story_catalog
from novelforge.story_builder.v3_projection import (
    STAGE_INDEX,
    V3_STAGES,
    command_center,
    novel_cards,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
IDEA = "一个普通维修工发现城市其实运行在一套隐藏的修仙操作系统上。"

# V3-P1 统一阶段状态词表。WARNING 允许出现（「可以进入但需要留意」），
# 但当前投影只会在有真实证据时才产出，不允许凭空造状态。
STAGE_STATUSES = {"LOCKED", "AVAILABLE", "CURRENT", "IN_PROGRESS", "COMPLETE",
                  "WARNING", "BLOCKED"}
OBJECTIVE_STATUSES = {"locked", "available", "active", "blocked", "complete",
                      "optional"}


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


def new_novel(client: TestClient, novel_id: str) -> None:
    created = client.post("/api/story-builder/novels",
                          json={"novel_id": novel_id, "title": novel_id})
    assert created.status_code in (201, 409), created.text


def save_brief(client: TestClient, novel_id: str) -> None:
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


def save_seed(client: TestClient, novel_id: str) -> None:
    seed = client.post(f"/api/story-builder/settings/seed?novel_id={novel_id}",
                       json={}).json()
    saved = client.put(f"/api/story-builder/settings/seed?novel_id={novel_id}",
                       json={"seed": seed["seed"], "selected": seed["seed"]["selected"]})
    assert saved.status_code == 200, saved.text


# ------------------------------------------------------------------ skeleton
def test_empty_novel_reports_zero_state_without_fake_numbers(tmp_path: Path) -> None:
    client = client_for(tmp_path)
    new_novel(client, "novel_v3_empty")
    data = client.get(
        "/api/story-builder/v3/novels/novel_v3_empty/command-center").json()

    assert data["progress"]["percent"] == 0
    assert all(row["count"] == 0 for row in data["content"])
    assert data["journey"]["current_stage"] == "creation"
    assert data["journey"]["completed_stages"] == 0
    assert data["facts"]["creative_brief_saved"] is False
    assert data["facts"]["runtime_started"] is False
    assert data["risks"] == []
    assert data["read_only"] is True


def test_landing_cards_are_derived_from_real_profiles(tmp_path: Path) -> None:
    client = client_for(tmp_path)
    new_novel(client, "novel_v3_landing")
    payload = client.get("/api/story-builder/v3/novels").json()
    card = next(row for row in payload["novels"] if row["novel_id"] == "novel_v3_landing")
    assert card["stage_label"] == "创意"
    assert card["progress_percent"] == 0
    # NF-005：Landing 卡片与 Command Center 必须同源（同一阶段 / 进度 / 下一步）。
    inside = command_center(tmp_path, "novel_v3_landing")
    assert card["stage_id"] == inside["journey"]["current_stage"]
    assert card["stage_label"] == inside["journey"]["current_stage_label"]
    assert card["progress_percent"] == inside["progress"]["percent"]
    assert card["next_action"] == inside["next_action"]["title"]
    assert card["next_action_label"] == inside["next_action"]["action_label"]
    assert card["runtime_started"] is False


# ------------------------------------------------------------------- journey
def test_journey_progresses_with_real_state(tmp_path: Path) -> None:
    client = client_for(tmp_path)
    novel_id = "novel_v3_journey"
    new_novel(client, novel_id)

    first = command_center(tmp_path, novel_id)
    assert first["journey"]["current_stage"] == "creation"
    assert first["next_action"]["deep_link"]["view"] == "creation"
    assert first["next_action"]["action_label"] == "开始一句创意"

    save_brief(client, novel_id)
    second = command_center(tmp_path, novel_id)
    assert second["journey"]["current_stage"] == "world"
    assert second["facts"]["creative_brief_saved"] is True
    assert second["next_action"]["title"] == "建立世界规则"
    assert second["next_action"]["action_label"] == "开始设定"
    assert second["progress"]["percent"] > first["progress"]["percent"]

    save_seed(client, novel_id)
    third = command_center(tmp_path, novel_id)
    assert third["facts"]["setting_seed_saved"] is True
    assert third["facts"]["content_pack_ready"] is True
    assert third["journey"]["current_stage"] in ("characters", "story", "simulation")
    assert third["journey"]["completed_stages"] >= second["journey"]["completed_stages"]

    started = client.post(f"/api/story-builder/runtime/start?novel_id={novel_id}",
                          json={})
    assert started.status_code == 200, started.text
    fourth = command_center(tmp_path, novel_id)
    assert fourth["facts"]["runtime_started"] is True
    assert fourth["journey"]["current_stage"] in ("outline", "review", "export")
    assert fourth["next_action"]["title"] in ("生成大纲", "检查故事一致性",
                                              "导出并开始写作")


def test_stage_and_objective_status_vocabulary_is_stable(tmp_path: Path) -> None:
    client = client_for(tmp_path)
    novel_id = "novel_v3_status"
    new_novel(client, novel_id)
    save_brief(client, novel_id)
    save_seed(client, novel_id)
    data = command_center(tmp_path, novel_id)

    stages = data["journey"]["stages"]
    assert [row["stage_id"] for row in stages] == [row["stage_id"] for row in V3_STAGES]
    for row in stages:
        assert row["status"] in STAGE_STATUSES
        assert row["progress"]["total"] >= 1
        assert 0 <= row["progress"]["percent"] <= 100
    current = [row for row in stages if row["current"]]
    assert len(current) == 1
    assert data["journey"]["current_stage"] == current[0]["stage_id"]
    for objective in data["objectives"]:
        assert objective["status"] in OBJECTIVE_STATUSES
        assert objective["completion_evidence"], objective["objective_id"]
        assert objective["truth_layer"] == "ui_derived"
        assert objective["read_only"] is True
        assert objective["progress"]["total"] >= 1
        assert STAGE_INDEX[objective["stage_id"]] >= 0


def test_optional_objective_never_becomes_the_next_action(tmp_path: Path) -> None:
    client = client_for(tmp_path)
    novel_id = "novel_v3_optional"
    new_novel(client, novel_id)
    save_brief(client, novel_id)
    save_seed(client, novel_id)
    data = command_center(tmp_path, novel_id)
    optional = {row["objective_id"] for row in data["objectives"] if row["optional"]}
    assert optional == {"obj_foreshadows"}
    assert data["next_action"]["objective_id"] not in optional
    assert data["next_action"]["truth_layer"] == "ui_derived"
    # 未解决的阻塞风险必须优先于任何“推荐但可跳过”的目标。
    blocking = [row for row in data["risks"] if row["level"] == "BLOCKING"]
    if blocking:
        assert data["next_action"]["action_label"] == "去修补"
        assert data["next_action"]["deep_link"] == blocking[0]["deep_link"]
    else:
        current = next(row for row in data["objectives"]
                       if row["objective_id"] == data["next_action"]["objective_id"])
        assert current["stage_id"] in {row["stage_id"] for row in data["journey"]["stages"]
                                       if row["status"] in ("CURRENT", "IN_PROGRESS",
                                                            "AVAILABLE", "BLOCKED")}


def test_projection_is_deterministic(tmp_path: Path) -> None:
    client = client_for(tmp_path)
    novel_id = "novel_v3_deterministic"
    new_novel(client, novel_id)
    save_brief(client, novel_id)
    first = json.dumps(command_center(tmp_path, novel_id), ensure_ascii=False,
                       sort_keys=True)
    second = json.dumps(command_center(tmp_path, novel_id), ensure_ascii=False,
                        sort_keys=True)
    assert first == second


def test_projection_is_read_only(tmp_path: Path) -> None:
    client = client_for(tmp_path)
    novel_id = "novel_v3_readonly"
    new_novel(client, novel_id)
    save_brief(client, novel_id)
    before = {path.relative_to(tmp_path).as_posix()
              for path in tmp_path.rglob("*") if path.is_file()}
    command_center(tmp_path, novel_id)
    novel_cards(tmp_path)
    after = {path.relative_to(tmp_path).as_posix()
             for path in tmp_path.rglob("*") if path.is_file()}
    assert before == after
    assert not (tmp_path / "novel" / "authoring" / "story_engine" / "state").exists()


def test_risk_presentation_maps_engine_findings_to_author_language(
        tmp_path: Path) -> None:
    client = client_for(tmp_path)
    novel_id = "novel_v3_risks"
    new_novel(client, novel_id)
    save_brief(client, novel_id)
    save_seed(client, novel_id)
    data = command_center(tmp_path, novel_id)
    for risk in data["risks"]:
        assert risk["level"] in ("INFO", "WARNING", "BLOCKING")
        assert risk["evidence"]
        assert risk["source"] in ("settings_check", "repair_diagnosis",
                                  "setting_seed", "outline_chain")
        # 作者语言：标题里不出现内部 finding code / 字段名。
        assert "_" not in risk["title"]
        assert "kind=" not in risk["title"]


def test_blocking_risk_has_priority_over_recommendation(tmp_path: Path) -> None:
    client = client_for(tmp_path)
    novel_id = "novel_v3_blocking"
    new_novel(client, novel_id)
    save_brief(client, novel_id)
    # 只保存一个空内容包骨架：自检必然产生阻塞项。
    seed = client.post(f"/api/story-builder/settings/seed?novel_id={novel_id}",
                       json={}).json()["seed"]
    for group in ("world_rules", "protagonist", "characters", "factions",
                  "relationships", "progression", "conflicts", "main_line",
                  "foreshadows"):
        seed[group] = []
    seed["selected"] = {group: [] for group in seed["selected"]}
    saved = client.put(f"/api/story-builder/settings/seed?novel_id={novel_id}",
                       json={"seed": seed, "selected": seed["selected"]})
    assert saved.status_code == 200, saved.text
    data = command_center(tmp_path, novel_id)
    blocking = [row for row in data["risks"] if row["level"] == "BLOCKING"]
    assert blocking, "空内容包必须产生阻塞风险"
    assert all(row["source"] == "settings_check" for row in blocking)
    assert all(row["deep_link"]["view"] in {
        "world", "characters", "story", "creation"} for row in blocking)
    assert data["next_action"]["title"].startswith(("补齐", "让起点"))
    assert data["next_action"]["blocking"] is True
    assert data["next_action"]["action_label"] == "去修补"
    assert data["next_action"]["deep_link"]["step"] == "settings"


def test_unknown_novel_returns_404(tmp_path: Path) -> None:
    client = client_for(tmp_path)
    response = client.get(
        "/api/story-builder/v3/novels/novel_missing_here/command-center")
    assert response.status_code == 404


@pytest.mark.parametrize("stage_id", [row["stage_id"] for row in V3_STAGES])
def test_stage_definition_has_author_facing_goal(stage_id: str) -> None:
    row = next(item for item in V3_STAGES if item["stage_id"] == stage_id)
    assert row["label"]
    assert row["goal"]
    assert row["icon"]


# ------------------------------------------------- V3-P1 AuthorJourney 契约
def test_journey_covers_every_stage_in_fixed_order(tmp_path: Path) -> None:
    """Stage Visualizer 必须能回答「我在哪 / 做了什么 / 还缺什么」。"""

    client = client_for(tmp_path)
    novel_id = "novel_v3_stage_order"
    new_novel(client, novel_id)
    journey = command_center(tmp_path, novel_id)["journey"]

    assert [row["stage_id"] for row in journey["stages"]] == [
        row["stage_id"] for row in V3_STAGES]
    assert journey["stage_count"] == len(V3_STAGES)
    for row in journey["stages"]:
        assert row["goal"], f"{row['stage_id']} 缺少作者可读目标"
        assert row["objective_ids"], f"{row['stage_id']} 没有归属 objective"
        assert 0 <= row["progress"]["done"] <= row["progress"]["total"]
        assert row["status"] in STAGE_STATUSES
        if row["status"] in {"COMPLETE", "CURRENT", "IN_PROGRESS", "AVAILABLE"}:
            assert row["reachable"] is True
        if row["status"] == "LOCKED":
            assert row["reachable"] is False


def test_recommended_next_stage_is_the_adjacent_stage(tmp_path: Path) -> None:
    """recommended_next_stage 必须由真实 stage 顺序推导，而不是硬编码。"""

    client = client_for(tmp_path)
    novel_id = "novel_v3_next_stage"
    new_novel(client, novel_id)
    journey = command_center(tmp_path, novel_id)["journey"]
    ids = [row["stage_id"] for row in journey["stages"]]
    index = ids.index(journey["current_stage"])
    expected = ids[index + 1] if index + 1 < len(ids) else ""
    assert journey["recommended_next_stage"] == expected

    # 真实状态推进后，当前阶段与推荐阶段一起前进。
    save_brief(client, novel_id)
    advanced = command_center(tmp_path, novel_id)["journey"]
    assert advanced["current_stage"] == "world"
    assert advanced["recommended_next_stage"] == "characters"
