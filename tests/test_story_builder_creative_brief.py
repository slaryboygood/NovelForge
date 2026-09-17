"""W1-01 专项：一句创意 → 题材 / 基调 / 卖点候选 → 作者确认 → creative_brief 保存与读取。"""

from __future__ import annotations

import json
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from novelforge.api.story_builder_routes import install_story_builder_api
from novelforge.story_builder import load_story_catalog
from novelforge.story_engine import NovelProfileRepository, list_templates
from novelforge.story_engine.content import list_packs_from_project
from novelforge.story_engine.creative import (
    CreativeBriefError,
    load_creative_brief,
    save_creative_brief,
    suggest_creative_brief,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PACK_ID = "creative_pack_001"
IDEA = "一个普通维修工发现城市其实运行在一套隐藏的修仙操作系统上。"

PACK_PAYLOAD = {
    "pack_id": PACK_ID,
    "title": "创意测试包",
    "genre": "xianxia",
    "initial_flags": {"journey_revision": 0},
    "initial_resources": {"supplies": 2},
    "actions": [{"id": "c_probe", "kind": "investigate", "name": "调查"}],
}

EXTRA_PACKS = (
    {"pack_id": "creative_scifi_001", "title": "科幻创意包", "genre": "sci_fi",
     "initial_flags": {"journey_revision": 0}, "initial_resources": {"energy": 10},
     "actions": [{"id": "c_scan", "kind": "investigate", "name": "扫描"}]},
    {"pack_id": "creative_mystery_001", "title": "悬疑创意包", "genre": "modern_mystery",
     "initial_flags": {"journey_revision": 0}, "initial_resources": {"supplies": 5},
     "actions": [{"id": "c_ask", "kind": "investigate", "name": "走访"}]},
)


class FailingProvider:
    """模拟 AI 不可用：generate_structured 直接抛错。"""

    def generate_structured(self, **kwargs):  # noqa: ANN003
        raise RuntimeError("provider offline")


class HallucinatingProvider:
    """模拟模型编造不存在的模板 / 内容包，以及越界基调与卖点。"""

    def generate_structured(self, **kwargs):  # noqa: ANN003
        return None, {
            "genre_candidates": [
                {"template_id": "not_a_template", "content_pack_id": "not_a_pack",
                 "label": "虚构题材", "reason": "凭空编造"},
                {"template_id": "sci_fi", "content_pack_id": "creative_scifi_001",
                 "label": "科幻", "reason": "AI 给出的理由"},
            ],
            "tone_candidates": [{"tone": "不存在的基调", "reason": "越界"},
                                {"tone": "紧张悬疑", "reason": "AI 基调理由"}],
            "selling_point_candidates": [{"text": "不存在的卖点", "reason": "越界"}],
        }


def install_pack(tmp_path: Path) -> None:
    target = tmp_path / "novel" / "config" / "story_engine"
    target.mkdir(parents=True, exist_ok=True)
    (target / f"{PACK_ID}.json").write_text(
        json.dumps(PACK_PAYLOAD, ensure_ascii=False, indent=2), encoding="utf-8")
    for pack in EXTRA_PACKS:
        (target / f"{pack['pack_id']}.json").write_text(
            json.dumps(pack, ensure_ascii=False, indent=2), encoding="utf-8")


def client_for(tmp_path: Path) -> TestClient:
    install_pack(tmp_path)
    app = FastAPI()
    install_story_builder_api(app, tmp_path, catalog=load_story_catalog(PROJECT_ROOT))
    return TestClient(app)


def test_idea_produces_at_least_three_catalog_backed_candidates(tmp_path: Path) -> None:
    install_pack(tmp_path)
    suggestion = suggest_creative_brief(tmp_path, "novel_w1", idea=IDEA)
    assert len(suggestion.genre_candidates) >= 3
    assert suggestion.tone_candidates, "必须给出基调候选"
    assert 3 <= len(suggestion.selling_point_candidates) <= 5, "卖点候选应是 3～5 条"
    assert all(item.reason for item in suggestion.genre_candidates), "每个题材候选都要有理由"
    assert all(item.reason for item in suggestion.selling_point_candidates)
    # 候选只能指向真实存在的模板 / 内容包（本测试根目录里只有 creative_pack_001）。
    templates = {item.template_id for item in list_templates()}
    packs = {item.pack_id for item in list_packs_from_project(tmp_path)}
    for item in suggestion.genre_candidates:
        if item.template_id:
            assert item.template_id in templates, item.template_id
        if item.content_pack_id:
            assert item.content_pack_id in packs, item.content_pack_id
        assert item.template_id or item.content_pack_id, "候选必须至少指向一个真实资源"
    # 作者选择默认取第一个候选。
    assert suggestion.selection.original_idea == IDEA
    assert suggestion.selection.selected_content_pack_id == \
        suggestion.genre_candidates[0].content_pack_id


def test_brief_save_and_reload_and_author_edit(tmp_path: Path) -> None:
    install_pack(tmp_path)
    client = client_for(tmp_path)
    created = client.post("/api/story-builder/novels",
                          json={"novel_id": "novel_w1", "title": "创意测试"})
    assert created.status_code == 201
    suggested = client.post("/api/story-builder/creative/suggest?novel_id=novel_w1",
                            json={"idea": IDEA, "reader_experience": "紧张、有推理快感"})
    assert suggested.status_code == 200, suggested.text
    payload = suggested.json()
    assert len(payload["genre_candidates"]) >= 3

    choice = payload["genre_candidates"][0]
    brief = {
        "original_idea": IDEA,
        "references": ["某部参考作品"],
        "reader_experience": "紧张、有推理快感",
        "selected_genre": choice["genre"],
        "selected_template_id": choice["template_id"],
        "selected_content_pack_id": choice["content_pack_id"],
        "tone": payload["tone_candidates"][0]["tone"],
        "selling_points": [item["text"] for item in payload["selling_point_candidates"][:3]],
    }
    saved = client.put("/api/story-builder/creative/brief?novel_id=novel_w1", json=brief)
    assert saved.status_code == 200, saved.text
    assert saved.json()["brief"]["original_idea"] == IDEA

    # 刷新后可读取，且内容一致。
    reloaded = client.get("/api/story-builder/creative/brief?novel_id=novel_w1")
    assert reloaded.status_code == 200
    assert reloaded.json()["brief"] == saved.json()["brief"]
    assert reloaded.json()["suggestion"]["selection"]["tone"] == brief["tone"]

    # 作者修改后再次保存（改基调 + 改卖点 + 补参考作品）。
    edited = {**brief, "tone": "冷峻写实", "selling_points": ["代价交换"],
              "references": ["某部参考作品", "另一部参考作品"]}
    saved_again = client.put("/api/story-builder/creative/brief?novel_id=novel_w1", json=edited)
    assert saved_again.status_code == 200
    assert saved_again.json()["brief"]["tone"] == "冷峻写实"
    assert saved_again.json()["brief"]["selling_points"] == ["代价交换"]
    assert saved_again.json()["brief"]["references"] == edited["references"]
    # 落库位置在 NovelProfile（设计态），不是 StoryState。
    profile = NovelProfileRepository(tmp_path).load("novel_w1")
    assert profile.world_profile["creative_brief"]["original_idea"] == IDEA
    assert profile.tone == "冷峻写实"


def test_reject_unknown_template_or_pack(tmp_path: Path) -> None:
    install_pack(tmp_path)
    client = client_for(tmp_path)
    client.post("/api/story-builder/novels", json={"novel_id": "novel_w1", "title": "创意测试"})
    base = {"original_idea": IDEA}
    bad_template = client.put("/api/story-builder/creative/brief?novel_id=novel_w1",
                              json={**base, "selected_template_id": "ghost_template"})
    assert bad_template.status_code == 404
    assert bad_template.json()["detail"]["code"] == "TEMPLATE_NOT_FOUND"
    bad_pack = client.put("/api/story-builder/creative/brief?novel_id=novel_w1",
                          json={**base, "selected_content_pack_id": "ghost_pack"})
    assert bad_pack.status_code == 404
    assert bad_pack.json()["detail"]["code"] == "CONTENT_PACK_NOT_FOUND"
    # 拒绝后不落库。
    assert load_creative_brief(tmp_path, "novel_w1") is None
    # 空创意被拒绝。
    short = client.post("/api/story-builder/creative/suggest?novel_id=novel_w1", json={"idea": "短"})
    assert short.status_code == 422
    assert short.json()["detail"]["code"] == "IDEA_TOO_SHORT"


def test_ai_unavailable_falls_back_to_deterministic_candidates(tmp_path: Path) -> None:
    install_pack(tmp_path)
    offline = suggest_creative_brief(tmp_path, "novel_w1", idea=IDEA, provider=FailingProvider())
    assert len(offline.genre_candidates) >= 3
    assert offline.source == "rule"
    assert any(item.startswith("AI_ERROR") for item in offline.notes)
    assert offline.selling_point_candidates and offline.tone_candidates
    # 没有 provider 时同样可用。
    plain = suggest_creative_brief(tmp_path, "novel_w1", idea=IDEA)
    assert plain.source == "rule" and "AI_UNAVAILABLE" in plain.notes
    assert len(plain.genre_candidates) >= 3


def test_hallucinated_candidates_are_dropped(tmp_path: Path) -> None:
    install_pack(tmp_path)
    result = suggest_creative_brief(tmp_path, "novel_w1", idea=IDEA,
                                    provider=HallucinatingProvider())
    pairs = {(item.template_id, item.content_pack_id) for item in result.genre_candidates}
    assert ("not_a_template", "not_a_pack") not in pairs
    assert any(item.startswith("AI_TEMPLATE_NOT_FOUND") or
               item.startswith("AI_CANDIDATE_OUTSIDE_CATALOG") for item in result.notes)
    assert all(item.tone != "不存在的基调" for item in result.tone_candidates)
    assert all(item.text != "不存在的卖点" for item in result.selling_point_candidates)
    # 合法的建议仍然生效。
    enriched = next((item for item in result.genre_candidates
                     if item.template_id == "sci_fi"), None)
    assert enriched is not None and enriched.reason == "AI 给出的理由"
    assert result.source == "ai"


def test_creative_brief_is_isolated_between_novels(tmp_path: Path) -> None:
    install_pack(tmp_path)
    client = client_for(tmp_path)
    for novel_id, idea in (("novel_one", "一个现代都市里的悬疑案件"),
                           ("novel_two", "一个修士在宗门里查账")):
        client.post("/api/story-builder/novels", json={"novel_id": novel_id, "title": novel_id})
        client.put(f"/api/story-builder/creative/brief?novel_id={novel_id}",
                   json={"original_idea": idea, "selling_points": [idea[:4]]})
    first = client.get("/api/story-builder/creative/brief?novel_id=novel_one").json()
    second = client.get("/api/story-builder/creative/brief?novel_id=novel_two").json()
    assert first["brief"]["original_idea"] != second["brief"]["original_idea"]
    assert first["brief"]["selling_points"] != second["brief"]["selling_points"]
    assert load_creative_brief(tmp_path, "novel_one").original_idea == "一个现代都市里的悬疑案件"


def test_creative_layer_has_no_hardcoded_novel_or_genre_branching(tmp_path: Path) -> None:
    source = (PROJECT_ROOT / "src/novelforge/story_engine/creative.py").read_text(encoding="utf-8")
    for pattern in ("if genre ==", "if world_type ==", "if novel_id ==", "class StoryState(",
                    "StoryStateRepository", "硅基升维", "silicon"):
        assert pattern not in source, f"creative.py 违反约束：{pattern}"
    # 复用既有分层，不新建配置系统。
    for marker in ("NovelProfileRepository", "list_templates", "list_packs_from_project"):
        assert marker in source, f"creative.py 必须复用：{marker}"
    # 关键词表只用于打分，不参与分支判断；确认候选仍来自真实目录。
    install_pack(tmp_path)
    suggestion = suggest_creative_brief(tmp_path, "novel_w1", idea=IDEA)
    packs = {item.pack_id for item in list_packs_from_project(tmp_path)}
    assert {item.content_pack_id for item in suggestion.genre_candidates} <= packs


def test_save_creative_brief_requires_idea(tmp_path: Path) -> None:
    install_pack(tmp_path)
    try:
        save_creative_brief(tmp_path, "novel_w1", {"original_idea": " "})
    except CreativeBriefError as exc:
        assert exc.code == "IDEA_REQUIRED"
    else:  # pragma: no cover - 明确失败路径
        raise AssertionError("空创意必须被拒绝")
