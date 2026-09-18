"""W1-02 专项：creative_brief → 设定候选（世界 / 人物 / 势力 / 关系 / 成长 / 矛盾 / 主线 / 伏笔）。"""

from __future__ import annotations

import json
import re
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from novelforge.api.story_builder_routes import install_story_builder_api
from novelforge.story_builder import load_story_catalog
from novelforge.story_engine.content import list_packs_from_project
from novelforge.story_engine.creative import CreativeBrief, save_creative_brief
from novelforge.story_engine.context import story_state_preview
from novelforge.story_engine.driver import advance_story
from novelforge.story_engine.profile import NovelProfileRepository
from novelforge.story_engine.settings_gen import (
    ID_PATTERN,
    SELECTABLE_GROUPS,
    SettingSeed,
    SettingsProvider,
    SettingsGenError,
    apply_selection,
    build_setting_seed,
    content_pack_draft,
    load_pack_draft,
    load_setting_seed,
    save_setting_seed,
    validate_pack_draft,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
IDEA = "一个普通维修工发现城市其实运行在一套隐藏的修仙操作系统上。"

BASE_PACK = {
    "pack_id": "settings_base_001",
    "title": "设定测试基础包",
    "genre": "xianxia",
    "initial_flags": {"journey_revision": 0},
    "initial_resources": {"supplies": 2},
    "actions": [{"id": "s_probe", "kind": "investigate", "name": "调查"}],
}


class FailingProvider:
    def generate_structured(self, **kwargs):  # noqa: ANN003
        raise RuntimeError("provider offline")


class HallucinatingProvider:
    """只允许改写既有 id：越界 id 必须被丢弃。"""

    def generate_structured(self, **kwargs):  # noqa: ANN003
        return None, {
            "world_rules": [{"id": "ghost_rule", "label": "虚构规则", "summary": "越界",
                             "reason": "编造"}],
            "protagonist": [{"id": "hero_ghost", "label": "虚构主角", "summary": "越界",
                             "reason": "编造"}],
        }


class RenamingProvider:
    """在合法 id 上补充文案：必须被采纳。"""

    def __init__(self, target_id: str) -> None:
        self.target_id = target_id

    def generate_structured(self, **kwargs):  # noqa: ANN003
        return None, {"protagonist": [{"id": self.target_id, "label": "被 AI 改写的角色定位",
                                       "summary": "AI 补充的专属描述",
                                       "reason": "AI 理由"}]}


def install_pack(tmp_path: Path) -> None:
    target = tmp_path / "novel" / "config" / "story_engine"
    target.mkdir(parents=True, exist_ok=True)
    (target / "settings_base_001.json").write_text(
        json.dumps(BASE_PACK, ensure_ascii=False, indent=2), encoding="utf-8")


def seed_for(tmp_path: Path, novel_id: str = "novel_w1", **kwargs) -> SettingSeed:
    install_pack(tmp_path)
    save_creative_brief(tmp_path, novel_id,
                        CreativeBrief(original_idea=IDEA, tone="紧张悬疑", selected_genre="xianxia",
                                      selling_points=["隐藏规则", "代价交换"]))
    return build_setting_seed(tmp_path, novel_id, **kwargs)


def client_for(tmp_path: Path) -> TestClient:
    install_pack(tmp_path)
    app = FastAPI()
    install_story_builder_api(app, tmp_path, catalog=load_story_catalog(PROJECT_ROOT))
    return TestClient(app)


def test_seed_covers_every_group_with_stable_unique_ids(tmp_path: Path) -> None:
    first = seed_for(tmp_path)
    second = build_setting_seed(tmp_path, "novel_w1")
    for group in SELECTABLE_GROUPS:
        rows = getattr(first, group)
        assert rows, f"{group} 不应为空"
        ids = [item.id for item in rows]
        assert len(ids) == len(set(ids)), f"{group} 候选 id 必须唯一"
        assert all(ID_PATTERN.match(item) for item in ids), f"{group} 候选 id 必须是稳定 slug"
        assert all(item.label and item.summary and item.reason for item in rows), \
            f"{group} 候选必须带标签 / 摘要 / 推荐理由"
        assert ids == [item.id for item in getattr(second, group)], f"{group} 重复生成应保持稳定 id"
    # 数量要求：角色 2～4、势力 ≥3、伏笔 ≥3。
    assert 2 <= len(first.characters) <= 4
    assert len(first.factions) >= 3
    assert len(first.foreshadows) >= 3
    assert len(first.progression) == 7, "七类成长必须齐全"
    categories = {item.data.get("category") for item in first.progression}
    assert categories == {"ability", "identity", "relationship", "faction", "information",
                          "equipment", "skill"}
    # 候选要引用这本小说自己的创意片段，而不是纯模板句。
    focus = "隐藏的修仙操作系统" in first.main_line[0].summary or \
        "隐藏" in first.main_line[0].summary or "运行" in first.main_line[0].summary
    assert focus, first.main_line[0].summary


def test_pack_draft_passes_engine_schema_and_can_be_reloaded(tmp_path: Path) -> None:
    seed = seed_for(tmp_path)
    brief = save_creative_brief(tmp_path, "novel_w1", CreativeBrief(original_idea=IDEA,
                                                                   selected_genre="xianxia"))[1]
    payload = content_pack_draft(seed, pack_id="novel_w1_pack", brief=brief)
    pack = validate_pack_draft(payload)
    assert pack.pack_id == "novel_w1_pack"
    assert pack.actions and pack.events and pack.progressions and pack.foreshadows
    assert pack.initial_current_location in pack.initial_locations
    saved = save_setting_seed(tmp_path, "novel_w1", seed=seed)
    assert saved["pack_id"] == "novel_w1_pack"
    on_disk = load_pack_draft(tmp_path, "novel_w1_pack")
    assert on_disk is not None and on_disk.pack_id == "novel_w1_pack"
    # 生成的内容包能被项目目录发现（Runtime 通过 pack_id 直接载入）。
    assert "novel_w1_pack" in {item.pack_id for item in list_packs_from_project(tmp_path)}
    # 设计态落点：NovelProfile（含设定种子与内容包 id），不是 StoryState。
    profile = NovelProfileRepository(tmp_path).load("novel_w1")
    assert profile.content_pack_id == "novel_w1_pack"
    assert profile.world_profile["setting_seed"]["seed"]["original_idea"] == IDEA
    assert profile.story_rules and profile.cast and profile.factions
    assert profile.future_plan["stages"], "主线方向要写进 FuturePlan"
    assert load_setting_seed(tmp_path, "novel_w1") is not None


def test_author_selection_drives_pack_and_survives_regeneration(tmp_path: Path) -> None:
    seed = seed_for(tmp_path)
    chosen_protagonist = seed.protagonist[1].id
    chosen_npc = seed.characters[2].id
    seed, _ = apply_selection(seed, {"protagonist": [chosen_protagonist],
                                     "characters": [chosen_npc]})
    saved = save_setting_seed(tmp_path, "novel_w1", seed=seed)
    pack = saved["pack"]
    assert pack.initial_characters["protagonist"]["name"] == \
        next(item.label for item in seed.protagonist if item.id == chosen_protagonist)
    assert pack.initial_characters["npc_1"]["name"] == \
        next(item.label for item in seed.characters if item.id == chosen_npc)
    # 换一批：作者已确认的候选仍然保留在同组里（不会被覆盖掉）。
    regenerated = build_setting_seed(tmp_path, "novel_w1", regenerate=True)
    assert regenerated.selected["protagonist"] == [chosen_protagonist]
    assert regenerated.selected["characters"] == [chosen_npc]
    assert chosen_protagonist in {item.id for item in regenerated.protagonist}
    assert chosen_npc in {item.id for item in regenerated.characters}
    # 越界选择被丢弃并记录，不影响保存。
    filtered, notes = apply_selection(regenerated, {"protagonist": ["ghost_id"],
                                                    "unknown_group": ["x"]})
    assert filtered.selected["protagonist"] == []
    assert any(note.startswith("SELECTION_OUTSIDE_CATALOG") for note in notes)
    assert any(note.startswith("SELECTION_GROUP_UNKNOWN") for note in notes)


def test_settings_seed_can_enter_runtime_and_candidates_follow_state(tmp_path: Path) -> None:
    seed = seed_for(tmp_path)
    save_setting_seed(tmp_path, "novel_w1", seed=seed)
    pack = load_pack_draft(tmp_path, "novel_w1_pack")
    profile = NovelProfileRepository(tmp_path).load("novel_w1")
    state = story_state_preview(profile, pack)
    opening = advance_story(state, pack, action_id="", actor="protagonist")
    assert opening.ok is False and opening.blocked == "action_required"
    available = [row["action_id"] for row in opening.next_candidates if row["available"]]
    blocked = {row["action_id"]: row["code"] for row in opening.next_candidates
               if not row["available"]}
    assert "act_investigate" in available and "act_wait" in available
    assert blocked["act_use_permit"] == "IDENTITY_MISSING"
    assert blocked["act_call_favor"] == "RELATIONSHIP_NOT_SATISFIED"
    # 执行一次调查后：知识到手 → 原本锁定的行动变得可执行（候选集合确实由状态决定）。
    result = advance_story(state, pack, action_id="act_investigate", actor="protagonist")
    assert result.ok
    after = {row["action_id"] for row in result.next_candidates if row["available"]}
    assert "act_open_hidden" in after, "获得情报后应解锁需要知识的行动"
    assert result.world_actions, "NPC / 势力自主行动必须真的发生"
    assert result.state.timeline.tick > state.timeline.tick


def test_ai_enrichment_only_updates_existing_candidates(tmp_path: Path) -> None:
    seed = seed_for(tmp_path)
    enriched, notes = SettingsProvider(HallucinatingProvider()).enrich(seed)
    assert "ghost_rule" not in {item.id for item in enriched.world_rules}
    assert "hero_ghost" not in {item.id for item in enriched.protagonist}
    assert any(item.startswith("AI_CANDIDATE_OUTSIDE_CATALOG") for item in notes)
    assert [item.id for item in enriched.world_rules] == [item.id for item in seed.world_rules]
    target = seed.protagonist[0].id
    renamed, _ = SettingsProvider(RenamingProvider(target)).enrich(seed)
    assert renamed.protagonist[0].label == "被 AI 改写的角色定位"
    assert renamed.source == "ai"
    # AI 不可用时退回确定性候选，流程不阻塞。
    offline = build_setting_seed(tmp_path, "novel_w1", provider=FailingProvider())
    assert offline.source == "rule"
    assert any(item.startswith("AI_ERROR") for item in offline.notes)
    assert offline.world_rules and offline.main_line
    plain = build_setting_seed(tmp_path, "novel_w1")
    assert "AI_UNAVAILABLE" in plain.notes


def test_setting_seed_requires_creative_brief(tmp_path: Path) -> None:
    install_pack(tmp_path)
    try:
        build_setting_seed(tmp_path, "novel_w1")
    except SettingsGenError as exc:
        assert exc.code == "CREATIVE_BRIEF_REQUIRED"
    else:  # pragma: no cover - 明确失败路径
        raise AssertionError("没有创意简报时必须拒绝生成设定候选")


def test_settings_seed_is_isolated_between_novels(tmp_path: Path) -> None:
    install_pack(tmp_path)
    save_creative_brief(tmp_path, "novel_one",
                        CreativeBrief(original_idea="一个现代都市里的悬疑案件，线索指向旧档案",
                                      selected_genre="modern_mystery"))
    save_creative_brief(tmp_path, "novel_two",
                        CreativeBrief(original_idea="一个修士在宗门里查账，发现灵石去向不明",
                                      selected_genre="xianxia"))
    save_setting_seed(tmp_path, "novel_one", seed=build_setting_seed(tmp_path, "novel_one"))
    save_setting_seed(tmp_path, "novel_two", seed=build_setting_seed(tmp_path, "novel_two"))
    one = load_setting_seed(tmp_path, "novel_one")
    two = load_setting_seed(tmp_path, "novel_two")
    assert one.original_idea != two.original_idea
    assert load_pack_draft(tmp_path, "novel_one_pack").pack_id == "novel_one_pack"
    assert load_pack_draft(tmp_path, "novel_two_pack").pack_id == "novel_two_pack"
    assert load_pack_draft(tmp_path, "novel_one_pack").title != \
        load_pack_draft(tmp_path, "novel_two_pack").title
    # 覆盖保存一本小说不会改动另一本。
    save_setting_seed(tmp_path, "novel_one",
                      seed=build_setting_seed(tmp_path, "novel_one", regenerate=True))
    assert load_setting_seed(tmp_path, "novel_two").original_idea == two.original_idea


def test_settings_api_roundtrip_and_reload(tmp_path: Path) -> None:
    client = client_for(tmp_path)
    created = client.post("/api/story-builder/novels",
                          json={"novel_id": "novel_w1", "title": "设定测试"})
    assert created.status_code == 201
    # 没有创意简报时生成设定候选 → 明确错误。
    missing = client.post("/api/story-builder/settings/seed?novel_id=novel_w1", json={})
    assert missing.status_code == 404
    assert missing.json()["detail"]["code"] == "CREATIVE_BRIEF_REQUIRED"
    saved_brief = client.put("/api/story-builder/creative/brief?novel_id=novel_w1",
                             json={"original_idea": IDEA, "tone": "紧张悬疑",
                                   "selected_genre": "xianxia",
                                   "selling_points": ["隐藏规则"]})
    assert saved_brief.status_code == 200

    suggested = client.post("/api/story-builder/settings/seed?novel_id=novel_w1", json={})
    assert suggested.status_code == 200, suggested.text
    payload = suggested.json()
    seed = payload["seed"]
    for group in SELECTABLE_GROUPS:
        assert seed[group], group
    assert payload["pack_preview"]["pack_id"] == "novel_w1_pack"

    choice = {"protagonist": [seed["protagonist"][2]["id"]],
              "characters": [seed["characters"][0]["id"], seed["characters"][1]["id"]]}
    saved = client.put("/api/story-builder/settings/seed?novel_id=novel_w1",
                       json={"seed": seed, "selected": choice})
    assert saved.status_code == 200, saved.text
    assert saved.json()["pack_id"] == "novel_w1_pack"
    assert saved.json()["pack"]["initial_characters"]["protagonist"]["name"] == \
        seed["protagonist"][2]["label"]

    reloaded = client.get("/api/story-builder/settings/seed?novel_id=novel_w1")
    assert reloaded.status_code == 200
    state = reloaded.json()
    assert state["saved"] is True
    assert state["seed"]["selected"] == choice
    assert state["pack"]["pack_id"] == "novel_w1_pack"
    # 作者改写后保存：改写内容被落库。
    edited = json.loads(json.dumps(state["seed"]))
    edited["characters"][0]["label"] = "作者改写的角色名"
    edited["selected"]["characters"] = [edited["characters"][0]["id"],
                                        edited["characters"][1]["id"]]
    again = client.put("/api/story-builder/settings/seed?novel_id=novel_w1",
                       json={"seed": edited, "selected": edited["selected"]})
    assert again.status_code == 200, again.text
    assert again.json()["pack"]["initial_characters"]["npc_1"]["name"] == "作者改写的角色名"
    # 非法候选 id 被拒绝。
    broken = json.loads(json.dumps(edited))
    broken["characters"][0]["id"] = "Bad-Id"
    rejected = client.put("/api/story-builder/settings/seed?novel_id=novel_w1",
                          json={"seed": broken, "selected": {}})
    assert rejected.status_code == 422


def test_settings_layer_has_no_genre_or_novel_hardcoding(tmp_path: Path) -> None:
    source = (PROJECT_ROOT / "src/novelforge/story_engine/settings_gen.py").read_text(
        encoding="utf-8")
    for pattern in ("if genre ==", "if world_type ==", "if novel_id ==", "硅基升维", "silicon",
                    "StoryStateRepository"):
        assert pattern not in source, f"settings_gen.py 违反约束：{pattern}"
    # 复用既有分层，不新建配置 / 成长 / 伏笔体系。
    for marker in ("ContentPack", "progression", "foreshadow", "load_creative_brief",
                   "NovelProfileRepository"):
        assert marker in source, f"settings_gen.py 必须复用：{marker}"
    assert not re.search(r"class\s+StoryState\b", source)
