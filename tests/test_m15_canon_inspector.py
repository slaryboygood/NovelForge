"""M15 Canon Inspector / Repair Center：只读检查 + 修复工作流安全边界回归。"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from novelforge.api.story_builder_routes import install_story_builder_api
from novelforge.story_builder import load_story_catalog
from novelforge.story_builder.inspector import (
    inspector_overview,
    inspector_record,
    inspector_search,
    repair_diagnosis,
    repair_history,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
IDEA = "一个普通维修工发现城市其实运行在一套隐藏的修仙操作系统上。"
CANON_DB = PROJECT_ROOT / "novel/authoring/story_engine/canon/wasteland_001.sqlite"


def client_for(tmp_path: Path, *, with_canon: bool = False) -> TestClient:
    source = PROJECT_ROOT / "novel" / "config" / "story_engine"
    target = tmp_path / "novel" / "config" / "story_engine"
    target.mkdir(parents=True, exist_ok=True)
    for item in source.glob("*.json"):
        target.joinpath(item.name).write_text(item.read_text(encoding="utf-8"),
                                              encoding="utf-8")
    if with_canon:
        canon_dir = tmp_path / "novel" / "authoring" / "story_engine" / "canon"
        canon_dir.mkdir(parents=True, exist_ok=True)
        canon_dir.joinpath(CANON_DB.name).write_bytes(CANON_DB.read_bytes())
    app = FastAPI()
    install_story_builder_api(app, tmp_path, catalog=load_story_catalog(PROJECT_ROOT))
    return TestClient(app)


def guide(client: TestClient, novel_id: str) -> dict:
    created = client.post("/api/story-builder/novels",
                          json={"novel_id": novel_id, "title": novel_id})
    assert created.status_code in (201, 409), created.text
    suggestion = client.post(f"/api/story-builder/creative/suggest?novel_id={novel_id}",
                             json={"idea": IDEA}).json()
    client.put(f"/api/story-builder/creative/brief?novel_id={novel_id}", json={
        "original_idea": IDEA, "references": suggestion["references"],
        "reader_experience": "紧张", "selected_genre": "xianxia",
        "selected_template_id": "", "selected_content_pack_id": "",
        "tone": suggestion["tone_candidates"][0]["tone"],
        "selling_points": [row["text"] for row in suggestion["selling_point_candidates"][:2]],
    })
    seed = client.post(f"/api/story-builder/settings/seed?novel_id={novel_id}",
                       json={}).json()
    saved = client.put(f"/api/story-builder/settings/seed?novel_id={novel_id}",
                       json={"seed": seed["seed"], "selected": seed["seed"]["selected"]}).json()
    client.post(f"/api/story-builder/runtime/start?novel_id={novel_id}", json={})
    return saved


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()[:16]


def _probe_state(tmp_path: Path, novel_id: str) -> dict[str, str]:
    """正式数据指纹：Canon DB / StoryState / novel profile。"""

    canon = tmp_path / "novel/authoring/story_engine/canon/wasteland_001.sqlite"
    state_dir = (tmp_path / "novel" / "authoring" / "story_engine" / "state"
                 / f"runtime_{novel_id}")
    profile = (tmp_path / "novel" / "authoring" / "story_engine" / "profiles"
               / f"{novel_id}.json")
    return {
        "canon": _digest(canon) if canon.is_file() else "",
        "state": hashlib.sha256("|".join(sorted(
            f"{p.name}:{_digest(p)}" for p in state_dir.glob("*.json"))
        ).encode()).hexdigest()[:16] if state_dir.is_dir() else "",
        "profile": _digest(profile) if profile.is_file() else "",
    }


def _pack_path(tmp_path: Path, pack_id: str) -> Path:
    matches = list((tmp_path / "novel").rglob(f"{pack_id}.json"))
    assert matches, f"内容包文件必须存在：{pack_id}"
    return matches[0]


# ---------------------------------------------------------------- Inspector（真实数据根，只读）
def repo_client() -> TestClient:
    """只读检查使用仓库数据根（canon + 570 章 historical IR 都在这里）。"""

    app = FastAPI()
    install_story_builder_api(app, PROJECT_ROOT,
                              catalog=load_story_catalog(PROJECT_ROOT))
    return TestClient(app)


def test_inspector_overview_layers_and_refs() -> None:
    client = repo_client()
    novel_id = "wasteland_001"
    payload = client.get(
        f"/api/story-builder/inspector/overview?novel_id={novel_id}").json()
    assert payload["canon"]["available"] is True
    assert payload["canon"]["fact_count"] > 0 and payload["canon"]["entity_count"] > 0
    assert payload["canon"]["db_ref"].endswith("wasteland_001.sqlite")
    assert payload["chapter_ir"]["chapter_count"] == 570
    assert payload["chapter_ir"]["index_digest"]
    assert payload["layers"] == ["occurred", "planned", "historical_repair", "ui_derived"]
    assert payload["read_only"] is True


def test_inspector_search_filters_and_identity() -> None:
    client = repo_client()
    novel_id = "wasteland_001"
    everything = client.get(
        f"/api/story-builder/inspector/search?novel_id={novel_id}&limit=200").json()
    kinds = set(everything["kinds"])
    assert {"canon_fact", "canon_entity", "chapter_ir"} <= kinds
    assert everything["total"] == len(everything["rows"]) or everything["total"] > 200

    chapter_only = client.get(
        f"/api/story-builder/inspector/search?novel_id={novel_id}"
        "&record_kind=chapter_ir&limit=200").json()
    assert chapter_only["total"] == 570
    assert all(row["record_kind"] == "chapter_ir" for row in chapter_only["rows"])
    assert all(row["truth_layer"] == "historical_repair" for row in chapter_only["rows"])

    canon_only = client.get(
        f"/api/story-builder/inspector/search?novel_id={novel_id}"
        "&layer=occurred&record_kind=canon_fact&limit=5").json()
    assert canon_only["rows"] and all(row["truth_layer"] == "occurred"
                                      for row in canon_only["rows"])

    # 稳定 identity：同一查询两次结果一致；不同记录 ref_id 唯一
    again = client.get(f"/api/story-builder/inspector/search?novel_id={novel_id}"
                       "&record_kind=chapter_ir&limit=200").json()
    assert [row["ref_id"] for row in again["rows"]] == [
        row["ref_id"] for row in chapter_only["rows"]]
    refs = [(row["record_kind"], row["ref_id"]) for row in everything["rows"]]
    assert len(refs) == len(set(refs))

    empty = client.get(f"/api/story-builder/inspector/search?novel_id={novel_id}"
                       "&query=__no_such_record__").json()
    assert empty["total"] == 0 and empty["rows"] == []
    unknown_kind = client.get(f"/api/story-builder/inspector/search?novel_id={novel_id}"
                              "&record_kind=__nope__").json()
    assert unknown_kind["total"] == 0 and unknown_kind["rows"] == []


def test_inspector_record_provenance_and_not_found(tmp_path: Path) -> None:
    client = repo_client()
    novel_id = "wasteland_001"
    chapters = client.get(
        f"/api/story-builder/inspector/search?novel_id={novel_id}"
        "&record_kind=chapter_ir&limit=1").json()["rows"]
    chapter_ref = chapters[0]["ref_id"]
    record = client.get(
        f"/api/story-builder/inspector/record?novel_id={novel_id}"
        f"&ref_id={chapter_ref}").json()
    assert record["found"] is True
    assert record["truth_layer"] == "historical_repair"
    kinds = {row["kind"] for row in record["provenance"]}
    assert {"source", "repair_replay", "reconciliation"} <= kinds
    assert any("REPAIR_REPLAY.json" in row["ref"] for row in record["provenance"])
    assert any("M11_FINAL_CLOSURE_RECONCILIATION.json" in row["ref"]
               for row in record["provenance"])

    missing = client.get(
        f"/api/story-builder/inspector/record?novel_id={novel_id}&ref_id=__nope__").json()
    assert missing["found"] is False and missing["note"]

    with_facts = inspector_search(PROJECT_ROOT, novel_id, record_kind="canon_fact",
                                  limit=1)
    fact_id = with_facts["rows"][0]["ref_id"]
    fact = inspector_record(PROJECT_ROOT, novel_id, ref_id=fact_id)
    assert fact["found"] is True and fact["record"]["record_kind"] == "canon_fact"


# ---------------------------------------------------------------- Repair Center
def test_repair_diagnosis_shape_and_no_auto_execution(tmp_path: Path) -> None:
    client = client_for(tmp_path, with_canon=True)
    novel_id = "m15_diagnosis"
    pack = guide(client, novel_id)
    before = _probe_state(tmp_path, novel_id)

    ok = client.get(f"/api/story-builder/repair/diagnosis?novel_id={novel_id}").json()
    # 健康内容包不应产生 settings 类问题（大纲质量提示属规划层，允许存在）
    assert not [row for row in ok["issues"] if row["source"] == "settings_check"]
    assert ok["execution_boundary"]
    assert ok["read_only"] is True

    # 打坏内容包 → 诊断出现 issue（含证据 / 影响 / 审批要求 / 执行目标）
    pack_path = _pack_path(tmp_path, pack["pack_id"])
    payload = json.loads(pack_path.read_text(encoding="utf-8"))
    payload["initial_resources"] = {}
    pack_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    after_break = _probe_state(tmp_path, novel_id)
    broken = client.get(f"/api/story-builder/repair/diagnosis?novel_id={novel_id}").json()
    assert broken["issue_count"] > 0
    issue = broken["issues"][0]
    assert set(issue) >= {"issue_id", "source", "severity", "message", "hint", "target",
                          "proposed_action", "execution_api", "requires_approval",
                          "approval_note", "impact", "truth_layer", "evidence"}
    assert issue["evidence"]
    assert issue["proposed_action"]
    # diagnosis 只读：不产生 mutation
    assert _probe_state(tmp_path, novel_id) == after_break
    assert before["state"] == after_break["state"]


def test_repair_execution_uses_official_api_and_is_traceable(tmp_path: Path) -> None:
    client = client_for(tmp_path, with_canon=True)
    novel_id = "m15_execution"
    pack = guide(client, novel_id)
    pack_path = _pack_path(tmp_path, pack["pack_id"])
    payload = json.loads(pack_path.read_text(encoding="utf-8"))
    payload["initial_resources"] = {}
    pack_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    diagnosis = repair_diagnosis(tmp_path, novel_id)
    assert diagnosis["issue_count"] > 0

    # 执行必须走既有正式 API（settings/check repair=true），并在结果里报告 applied_fixes
    response = client.post(f"/api/story-builder/settings/check?novel_id={novel_id}",
                           json={"repair": True})
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["repaired"] is True and result["applied_fixes"]
    assert result["ok"] is True
    cleaned = repair_diagnosis(tmp_path, novel_id)
    assert not [row for row in cleaned["issues"]
                if row["source"] == "settings_check" and row["severity"] == "error"]

    history = client.get(f"/api/story-builder/repair/history?novel_id={novel_id}").json()
    assert "outline_versions_ref" in history
    assert isinstance(history["effect_log"], list)
    if history["effect_log"]:
        orders = [row["order"] for row in history["effect_log"]]
        assert orders == sorted(orders), "effect log 必须按 order 稳定排序"
        assert all(row["truth_layer"] == "occurred" for row in history["effect_log"])


def test_repair_execution_failure_is_not_masked(tmp_path: Path) -> None:
    client = client_for(tmp_path, with_canon=True)
    novel_id = "m15_failure"
    assert client.post("/api/story-builder/novels",
                       json={"novel_id": novel_id, "title": novel_id}).status_code == 201
    # 没有内容包时自检失败必须显式报错，而不是伪装成功
    response = client.post(f"/api/story-builder/settings/check?novel_id={novel_id}",
                           json={"repair": True})
    assert response.status_code >= 400
    history = repair_history(tmp_path, novel_id)
    assert history["effect_log"] == []


# ---------------------------------------------------------------- 只读边界
def test_inspector_and_diagnosis_are_read_only(tmp_path: Path) -> None:
    client = client_for(tmp_path, with_canon=True)
    novel_id = "m15_read_only"
    guide(client, novel_id)
    before = _probe_state(tmp_path, novel_id)
    canon_before = _digest(tmp_path / "novel/authoring/story_engine/canon/"
                           "wasteland_001.sqlite")
    for url in (f"/api/story-builder/inspector/overview?novel_id={novel_id}",
                f"/api/story-builder/inspector/search?novel_id={novel_id}&limit=200",
                f"/api/story-builder/inspector/record?novel_id={novel_id}&ref_id=x",
                f"/api/story-builder/repair/diagnosis?novel_id={novel_id}",
                f"/api/story-builder/repair/history?novel_id={novel_id}"):
        assert client.get(url).status_code == 200, url
    after = _probe_state(tmp_path, novel_id)
    assert after == before, (before, after)
    assert _digest(tmp_path / "novel/authoring/story_engine/canon/"
                   "wasteland_001.sqlite") == canon_before
    assert inspector_overview(tmp_path, novel_id)["read_only"] is True
    assert repair_history(tmp_path, novel_id)["read_only"] is True
