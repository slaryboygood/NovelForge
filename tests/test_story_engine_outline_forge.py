"""W3 专项：剧情路线 → 全书主线 / 卷纲 / 篇章纲 / 详细章纲（含质量评估与来源追溯）。"""

from __future__ import annotations

import json
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from novelforge.api.story_builder_routes import install_story_builder_api
from novelforge.story_builder import load_story_catalog
from novelforge.story_builder.models import OutlineLevel, OutlineStatus
from novelforge.story_builder.outlines import StoryOutlineRepository
from novelforge.story_engine.outline_forge import (
    OutlineForgeError,
    StructureSpec,
    assess_forge_plan,
    build_forge_plan,
    export_forge_markdown,
    forge_outline,
    load_forge_chain,
    state_digest,
    verify_plan_sources,
)
from novelforge.story_engine.profile import NovelProfileRepository
from novelforge.story_engine.storage import StoryStateRepository

PROJECT_ROOT = Path(__file__).resolve().parents[1]
IDEA = "一个普通维修工发现城市其实运行在一套隐藏的修仙操作系统上。"
CRISIS_IDEA = "一名调查记者追查连环失踪案，发现所有证词都指向同一份被篡改的档案。"
STRUCTURE = {"volumes": 3, "arcs_per_volume": 2, "chapters_per_arc": 5}


def client_for(tmp_path: Path) -> TestClient:
    source = PROJECT_ROOT / "novel" / "config" / "story_engine"
    target = tmp_path / "novel" / "config" / "story_engine"
    target.mkdir(parents=True, exist_ok=True)
    for item in source.glob("*.json"):
        target.joinpath(item.name).write_text(item.read_text(encoding="utf-8"), encoding="utf-8")
    app = FastAPI()
    install_story_builder_api(app, tmp_path, catalog=load_story_catalog(PROJECT_ROOT))
    return TestClient(app)


def prepare_route(client: TestClient, novel_id: str, *, idea: str = IDEA,
                  genre: str = "xianxia", turns: int = 12,
                  preferred: list[str] | None = None) -> int:
    """走 W1 引导流程 + 试演若干回合，返回 revision。"""

    assert client.post("/api/story-builder/novels",
                       json={"novel_id": novel_id, "title": novel_id}).status_code == 201
    client.put(f"/api/story-builder/creative/brief?novel_id={novel_id}",
               json={"original_idea": idea, "selected_genre": genre, "tone": "紧张悬疑"})
    seed = client.post(f"/api/story-builder/settings/seed?novel_id={novel_id}",
                       json={}).json()["seed"]
    client.put(f"/api/story-builder/settings/seed?novel_id={novel_id}",
               json={"seed": seed, "selected": seed["selected"]})
    started = client.post(f"/api/story-builder/runtime/start?novel_id={novel_id}", json={})
    assert started.status_code == 200, started.text
    revision = 0
    for index in range(turns):
        state = client.get(f"/api/story-builder/runtime/state?novel_id={novel_id}").json()
        available = [row["action_id"] for row in state["candidates"] if row["available"]]
        if preferred:
            available = [item for item in preferred if item in available] or available
        if not available:
            break
        action = available[index % len(available)]
        moved = client.post(f"/api/story-builder/runtime/advance?novel_id={novel_id}",
                            json={"action_id": action, "expected_revision": state["revision"]})
        assert moved.status_code == 200, moved.text
        revision = moved.json()["revision"]
    return revision


def test_forge_plan_builds_four_levels_with_rich_chapters(tmp_path: Path) -> None:
    client = client_for(tmp_path)
    revision = prepare_route(client, "novel_w3")
    assert revision >= 6
    plan = build_forge_plan(tmp_path, "novel_w3", structure=STRUCTURE)
    assert plan.structure.total_chapters == 30
    assert len(plan.chapters) == 30
    assert len(plan.volumes) == 3 and len(plan.arcs) == 6
    kinds = {item.kind for item in plan.chapters}
    assert "happened" in kinds and "planned" in kinds, "必须区分已发生与规划"
    happened = [item for item in plan.chapters if item.kind == "happened"]
    planned = [item for item in plan.chapters if item.kind == "planned"]
    # 章纲必须能直接支撑写作：目标 / 冲突 / 钩子 / 来源 / 约束都要有。
    for item in plan.chapters:
        assert item.title and item.summary and item.goal and item.conflict and item.hook
        assert item.must_keep and item.must_avoid
        assert item.participants, item.id
    for item in happened:
        assert item.source_ids, "已发生章节必须能追溯到路线记录"
        # NF-004：来源 id 在 source_ids（机器字段）；must_keep 只写作者可读的来源说明。
        assert any(value.startswith("route_") for value in item.source_ids)
        assert not any("route_" in value for value in item.must_keep)
    for item in planned:
        assert item.source_ids, "规划章节必须能追溯到 future_plan 阶段"
        assert any(value.startswith("planned_") for value in item.source_ids)
        assert not any("future_plan:" in value for value in item.must_keep)
        assert "不得把规划写成已经发生的事实" in item.must_avoid
    # 事实细节来自 StoryState：知识获取出现在信息释放里。
    assert any("获知" in row for item in happened for row in item.information_changes)
    # 章节按卷 / 篇章编号连续。
    assert [item.index for item in plan.chapters] == list(range(1, 31))
    assert {item.volume_index for item in plan.chapters} == {1, 2, 3}


def test_quality_report_flags_real_problems(tmp_path: Path) -> None:
    client = client_for(tmp_path)
    prepare_route(client, "novel_w3")
    plan = build_forge_plan(tmp_path, "novel_w3", structure=STRUCTURE)
    report = assess_forge_plan(plan)
    assert report.ok, [item.as_dict() for item in report.findings]
    assert report.counts["chapters"] == 30
    assert report.counts["happened"] >= 6
    assert len(report.pacing) == 30
    # 人为破坏：删掉主线收束 + 制造连续无钩子章节 → 必须报出来。
    broken = plan.model_copy(update={"book_end_state": ""})
    broken = broken.model_copy(update={"chapters": [
        item.model_copy(update={"hook": "", "turn": ""}) if index < 5 else item
        for index, item in enumerate(broken.chapters)]})
    broken_report = assess_forge_plan(broken)
    codes = {item.code for item in broken_report.findings}
    assert not broken_report.ok
    assert "MAIN_LINE_UNCLEAR" in codes
    assert "PACING_FLAT" in codes


def test_forge_persists_chain_and_stays_traceable(tmp_path: Path) -> None:
    client = client_for(tmp_path)
    prepare_route(client, "novel_w3")
    result = forge_outline(tmp_path, "novel_w3", structure=STRUCTURE)
    assert result["counts"]["volumes"] == 3 and result["counts"]["chapters"] == 30
    repository = StoryOutlineRepository(tmp_path)
    book = repository.latest(OutlineLevel.BOOK, result["package_ids"]["book"])
    assert book is not None and book.level == OutlineLevel.BOOK
    assert book.status == OutlineStatus.DRAFT
    assert book.route_source["branch_id"] == "main"
    assert book.design_sections["structure"].startswith("3 卷")
    chapters = [repository.latest(OutlineLevel.CHAPTER, result["package_ids"][f"chapter_{index}"])
                for index in range(1, 31)]
    assert all(item is not None for item in chapters)
    # 每章都有父篇章包（四级链路完整），且都能追溯到路线来源。
    assert all(item.parent_package_id for item in chapters)
    assert all(item.route_source["digest"] for item in chapters)
    structure_types = {item.package_id: item.level for item in chapters}
    assert len(structure_types) == 30
    # 来源摘要与当前状态一致；状态推进后必须变成不一致（提醒重新锻造）。
    chain = load_forge_chain(tmp_path, "novel_w3")
    assert chain["fresh"] is True
    assert chain["quality"]["ok"] is True
    state = StoryStateRepository(tmp_path).load("runtime_novel_w3", 1, "main")
    assert state_digest(state) == book.route_source["digest"]
    verification = verify_plan_sources(build_forge_plan(tmp_path, "novel_w3",
                                                       structure=STRUCTURE), state)
    assert verification["unsourced"] == [], verification


def test_forge_requires_started_route_and_reports_stale(tmp_path: Path) -> None:
    client = client_for(tmp_path)
    assert client.post("/api/story-builder/novels",
                       json={"novel_id": "novel_plain", "title": "x"}).status_code == 201
    try:
        build_forge_plan(tmp_path, "novel_plain", structure=STRUCTURE)
    except OutlineForgeError as exc:
        assert exc.code in ("CONTENT_PACK_REQUIRED", "ROUTE_NOT_STARTED")
    else:  # pragma: no cover - 明确失败路径
        raise AssertionError("没有开始推演时不应该能锻造大纲")


def test_outline_api_roundtrip_confirm_edit_and_export(tmp_path: Path) -> None:
    client = client_for(tmp_path)
    prepare_route(client, "novel_w3")
    plan = client.get("/api/story-builder/outline/plan?novel_id=novel_w3&volumes=3"
                      "&arcs_per_volume=2&chapters_per_arc=5")
    assert plan.status_code == 200, plan.text
    assert len(plan.json()["plan"]["chapters"]) == 30
    assert plan.json()["quality"]["ok"] is True
    forged = client.post("/api/story-builder/outline/forge?novel_id=novel_w3",
                         json=STRUCTURE)
    assert forged.status_code == 200, forged.text
    chain = client.get("/api/story-builder/outline/chain?novel_id=novel_w3").json()
    assert chain["fresh"] is True and len(chain["chapters"]) == 30
    first = chain["chapters"][0]
    # 未确认前不允许改写（沿用既有版本规则）。
    blocked = client.put(
        f"/api/story-builder/outlines/{first['package_id']}/items/"
        f"{first['items'][0]['item_id']}",
        json={"expected_version": first["version"], "changes": {"ending_hook": "提前改写"}})
    assert blocked.status_code == 409
    confirmed = client.post("/api/story-builder/outline/confirm?novel_id=novel_w3", json={})
    assert confirmed.status_code == 200, confirmed.text
    assert confirmed.json()["count"] == 40
    edited = client.put(
        f"/api/story-builder/outlines/{first['package_id']}/items/"
        f"{first['items'][0]['item_id']}",
        json={"expected_version": first["version"], "changes": {"ending_hook": "作者改写的钩子"}})
    assert edited.status_code == 200, edited.text
    assert edited.json()["outline"]["version"] == first["version"] + 1
    assert edited.json()["outline"]["status"] == "DRAFT"
    reloaded = client.get("/api/story-builder/outline/chain?novel_id=novel_w3").json()
    assert reloaded["chapters"][0]["items"][0]["ending_hook"] == "作者改写的钩子"
    export = client.get("/api/story-builder/outline/export?novel_id=novel_w3")
    assert export.status_code == 200
    content = export.json()["content"]
    assert "不得违反" in content and "结尾钩子" in content
    assert content.count("## ") >= 30


def test_forge_output_is_novel_specific_and_genre_neutral(tmp_path: Path) -> None:
    first = tmp_path / "one"
    second = tmp_path / "two"
    client_one = client_for(first)
    prepare_route(client_one, "novel_xianxia", idea=IDEA, genre="xianxia",
                  preferred=["act_investigate", "act_go_hidden", "act_investigate"])
    client_two = client_for(second)
    prepare_route(client_two, "novel_mystery", idea=CRISIS_IDEA, genre="modern_mystery",
                  preferred=["act_go_work", "act_ask", "act_wait"])
    plan_one = build_forge_plan(first, "novel_xianxia", structure=STRUCTURE)
    plan_two = build_forge_plan(second, "novel_mystery", structure=STRUCTURE)
    assert plan_one.book_title == "novel_xianxia" and plan_two.book_title == "novel_mystery"
    # 章纲内容来自各自小说的创意与事实，不是同一套模板句。
    assert plan_one.chapters[0].title != plan_two.chapters[0].title
    assert plan_one.book_goal != plan_two.book_goal
    assert plan_one.chapters[0].goal != plan_two.chapters[0].goal
    assert plan_one.chapters[0].location != plan_two.chapters[0].location
    forge_outline(first, "novel_xianxia", structure=STRUCTURE)
    forge_outline(second, "novel_mystery", structure=STRUCTURE)
    export_one = export_forge_markdown(first, "novel_xianxia")["content"]
    export_two = export_forge_markdown(second, "novel_mystery")["content"]
    assert export_one != export_two
    # 源码守卫：没有题材 / 小说名分支，也不另建大纲模型。
    source = (PROJECT_ROOT / "src/novelforge/story_engine/outline_forge.py").read_text(
        encoding="utf-8")
    for pattern in ("if genre ==", "if world_type ==", "if novel_id ==", "硅基升维", "silicon",
                    "class OutlineItem(", "class OutlinePackage("):
        assert pattern not in source, f"outline_forge.py 违反约束：{pattern}"
    for marker in ("StoryOutlineRepository", "OutlinePackage", "OutlineItem",
                   "build_route", "verify_outline_sources"):
        assert marker in source, f"outline_forge.py 必须复用：{marker}"


def test_forged_outline_marks_stale_after_route_moves(tmp_path: Path) -> None:
    client = client_for(tmp_path)
    prepare_route(client, "novel_w3")
    forge_outline(tmp_path, "novel_w3", structure=STRUCTURE)
    assert load_forge_chain(tmp_path, "novel_w3")["fresh"] is True
    state = client.get("/api/story-builder/runtime/state?novel_id=novel_w3").json()
    available = [row["action_id"] for row in state["candidates"] if row["available"]]
    moved = client.post("/api/story-builder/runtime/advance?novel_id=novel_w3",
                        json={"action_id": available[0], "expected_revision": state["revision"]})
    assert moved.status_code == 200, moved.text
    chain = load_forge_chain(tmp_path, "novel_w3")
    assert chain["fresh"] is False, "路线推进后旧大纲必须标记为来源已变化"
    assert chain["quality"] is None
    # 重新锻造会生成新版本，而不是覆盖旧版本。
    again = forge_outline(tmp_path, "novel_w3", structure=STRUCTURE)
    repository = StoryOutlineRepository(tmp_path)
    book = repository.latest(OutlineLevel.BOOK, again["package_ids"]["book"])
    assert book.version >= 2
    assert load_forge_chain(tmp_path, "novel_w3")["fresh"] is True
    profile = NovelProfileRepository(tmp_path).load("novel_w3")
    assert profile.content_pack_id == "novel_w3_pack"
    assert json.dumps(profile.world_profile, ensure_ascii=False)
