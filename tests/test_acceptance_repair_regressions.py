"""V3 验收修复（Repair branch）回归：把 NF-001/002/003/004/005/008/011/012 变成断言。

这些用例对应 `docs/CURRENT_PRODUCT_ACCEPTANCE_REVIEW.md` 里的 P1/P2 问题，
每一条都在修复**之前必然失败**——它们检查的是当时的真实缺陷：

* 写作草稿写入路径与投影读取路径不一致（NF-002）；
* 导出就绪度没有「已有写作草稿」这一步、blocker 与标题自相矛盾（NF-012）；
* 章节标题是字段标签占位、可追溯来源写在作者可见文本里（NF-003 / NF-004）；
* Landing 卡片与 Command Center 有两套阶段 / 进度（NF-005）；
* 投影声称可执行的行动，点下去是 422（NF-008）。
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from novelforge.api.story_builder_routes import install_story_builder_api
from novelforge.story_builder import load_story_catalog
from novelforge.story_builder.v3_projection import command_center, novel_cards
from novelforge.story_builder.writer_integration import (
    WRITER_DIR,
    WriterDraftService,
    writer_index_path,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]

IDEAS = (
    ("novel_repair_scifi", "sci_fi",
     "一名被裁员的飞船维修师发现公司用算力在殖民地之间买卖记忆，他的工牌是唯一的钥匙。"),
    ("novel_repair_cultivation", "xianxia",
     "一个替人抄书的寒门书生被卷进夺嫡之争，他抄过的每一份密诏都在被人灭口。"),
)

FIELD_LABEL_BLACKLIST = ("阶段目标", "长期方向", "（规划）", "（设定草稿）")
INTERNAL_ID_PATTERN = re.compile(
    r"\b(act_[a-z0-9_]+|ev_[a-z0-9_]+|faction_\d+|npc_\d+|location_\d+|character_\d+"
    r"|route_\d+|planned_[a-z0-9_]+|suggested_[a-z0-9_]+|start_place|work_place"
    r"|hidden_place|core_record|protagonist|favors)\b")
# artifact identity / 引用字段：不是作者可见内容。
IDENTITY_KEYS = {"item_id", "package_id", "parent_package_id", "child_ids", "source_ids",
                 "route_source", "canon_fact_ids", "canon_event_ids", "novel_id",
                 "branch_id", "blueprint_id", "chapter_uuid", "participants"}


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


def content_strings(node, skip_identity: bool = False) -> list[str]:
    if isinstance(node, list):
        return [text for value in node for text in content_strings(value, skip_identity)]
    if isinstance(node, dict):
        return [text for key, value in node.items()
                for text in content_strings(value,
                                            skip_identity or key in IDENTITY_KEYS)]
    if isinstance(node, str):
        return [] if skip_identity else [node]
    return []


def build_route_state(client: TestClient, novel_id: str, idea: str, genre: str,
                      *, turns: int = 3) -> None:
    assert client.post("/api/story-builder/novels",
                       json={"novel_id": novel_id, "title": novel_id}).status_code == 201
    assert client.put(f"/api/story-builder/creative/brief?novel_id={novel_id}",
                      json={"original_idea": idea, "selected_genre": genre,
                            "tone": "紧张悬疑"}).status_code == 200
    seed = client.post(f"/api/story-builder/settings/seed?novel_id={novel_id}",
                       json={}).json()["seed"]
    assert client.put(f"/api/story-builder/settings/seed?novel_id={novel_id}",
                      json={"seed": seed, "selected": seed["selected"]}).status_code == 200
    assert client.post(f"/api/story-builder/runtime/start?novel_id={novel_id}",
                       json={}).status_code == 200
    for _ in range(turns):
        state = client.get(f"/api/story-builder/runtime/state?novel_id={novel_id}").json()
        available = [row["action_id"] for row in state["candidates"] if row["available"]]
        if not available:
            break
        moved = client.post(f"/api/story-builder/runtime/advance?novel_id={novel_id}",
                            json={"action_id": available[0],
                                  "expected_revision": state["revision"]})
        if moved.status_code != 200:
            break


def forge_and_confirm(client: TestClient, novel_id: str, *, volumes: int = 3,
                      arcs: int = 2, chapters: int = 5) -> None:
    forged = client.post(f"/api/story-builder/outline/forge?novel_id={novel_id}",
                         json={"branch_id": "main", "volumes": volumes,
                               "arcs_per_volume": arcs, "chapters_per_arc": chapters})
    assert forged.status_code == 200, forged.text
    assert forged.json()["quality"]["ok"], forged.json()["quality"]["findings"]
    confirmed = client.post(f"/api/story-builder/outline/confirm?novel_id={novel_id}",
                            json={"branch_id": "main"})
    assert confirmed.status_code == 200, confirmed.text


# --------------------------------------------------------------- NF-002 writer
def test_writer_draft_store_is_the_projection_source(tmp_path: Path) -> None:
    """service 写入路径 == 投影读取路径（同一个 canonical 常量）。"""

    client = client_for(tmp_path)
    novel_id = "novel_repair_writer"
    build_route_state(client, novel_id, IDEAS[0][2], IDEAS[0][1])

    before = command_center(tmp_path, novel_id)
    assert before["facts"]["writer_drafts"] == 0

    created = client.post("/api/story-builder/writer/drafts",
                          json={"novel_id": novel_id, "branch_id": "main"})
    assert created.status_code == 201, created.text
    draft_id = created.json()["draft_id"]
    # 写入的草稿确实落在 canonical writer store 里（而不是历史 workspace 路径）。
    assert writer_index_path(tmp_path, novel_id).is_file()
    assert writer_index_path(tmp_path, novel_id) == (
        tmp_path / WRITER_DIR / novel_id / "index.json")
    assert (tmp_path / WRITER_DIR / novel_id / "drafts" / f"{draft_id}.json").is_file()

    after = command_center(tmp_path, novel_id)
    assert after["facts"]["writer_drafts"] == 1, "投影必须看到刚写入的草稿"
    step = next(row for row in after["export"]["steps"]
                if row["step_id"] == "writer_drafts")
    assert step["done"] is True
    assert after["export"]["writer_drafts"] == 1

    # 新进程 / 新客户端读同一份数据也必须看到（持久化，不是内存态）。
    fresh = client_for(tmp_path)
    again = command_center(tmp_path, novel_id)
    assert again["facts"]["writer_drafts"] == 1
    listing = fresh.get(
        f"/api/story-builder/writer/drafts?novel_id={novel_id}").json()
    assert [row["draft_id"] for row in listing["drafts"]] == [draft_id]


def test_writer_draft_completes_the_export_stage(tmp_path: Path) -> None:
    client = client_for(tmp_path)
    novel_id = "novel_repair_export_stage"
    build_route_state(client, novel_id, IDEAS[1][2], IDEAS[1][1])
    forge_and_confirm(client, novel_id)

    before = command_center(tmp_path, novel_id)
    assert before["export"]["ready"] is False
    missing = {row["step_id"] for row in before["export"]["missing"]}
    assert missing == {"writer_drafts"}, "确认大纲后只差写作草稿"

    assert client.post("/api/story-builder/writer/drafts",
                       json={"novel_id": novel_id, "branch_id": "main"}).status_code == 201
    after = command_center(tmp_path, novel_id)
    assert after["export"]["ready"] is True
    assert after["progress"]["percent"] > before["progress"]["percent"], (
        "创建写作草稿之后总体进度必须上升（导出阶段真的完成）")
    export_stage = next(row for row in after["journey"]["stages"]
                        if row["stage_id"] == "export")
    assert export_stage["progress"]["done"] == export_stage["progress"]["total"]


def test_writer_draft_service_and_projection_share_writer_dir(tmp_path: Path) -> None:
    """同源常量：修改 canonical 目录时两边一起变（防止再次出现双路径）。"""

    service = WriterDraftService(tmp_path, "novel_repair_shared")
    assert service.dir == tmp_path.resolve() / WRITER_DIR / "novel_repair_shared"
    assert writer_index_path(tmp_path, "novel_repair_shared") == service.dir / "index.json"


# ------------------------------------------------------- NF-005 单一阶段来源
def test_landing_card_matches_command_center_in_three_states(tmp_path: Path) -> None:
    client = client_for(tmp_path)
    brief_only = "novel_repair_card_a"
    started = "novel_repair_card_b"
    rich = "novel_repair_card_c"
    assert client.post("/api/story-builder/novels",
                       json={"novel_id": brief_only, "title": brief_only}).status_code == 201
    assert client.put(f"/api/story-builder/creative/brief?novel_id={brief_only}",
                      json={"original_idea": IDEAS[0][2], "selected_genre": "sci_fi",
                            "tone": "冷峻"}).status_code == 200
    build_route_state(client, started, IDEAS[0][2], IDEAS[0][1])
    build_route_state(client, rich, IDEAS[1][2], IDEAS[1][1])
    forge_and_confirm(client, rich)

    cards = {row["novel_id"]: row for row in novel_cards(tmp_path)["novels"]}
    for novel_id in (brief_only, started, rich):
        card = cards[novel_id]
        inside = command_center(tmp_path, novel_id)
        assert card["stage_id"] == inside["journey"]["current_stage"]
        assert card["stage_label"] == inside["journey"]["current_stage_label"]
        assert card["progress_percent"] == inside["progress"]["percent"]
        assert card["progress_done"] == inside["progress"]["done"]
        assert card["progress_total"] == inside["progress"]["total"]
        assert card["next_action"] == inside["next_action"]["title"]
        assert card["next_action_label"] == inside["next_action"]["action_label"]


# ---------------------------------------------------------- NF-012 导出文案
def test_export_headline_reports_blockers_not_zero_steps(tmp_path: Path) -> None:
    client = client_for(tmp_path)
    novel_id = "novel_repair_blocker"
    build_route_state(client, novel_id, IDEAS[0][2], IDEAS[0][1])
    forge_and_confirm(client, novel_id)
    # 再推演一次：大纲过期，这是真实 blocker（不是缺失步骤）。
    state = client.get(f"/api/story-builder/runtime/state?novel_id={novel_id}").json()
    available = [row["action_id"] for row in state["candidates"] if row["available"]]
    assert available, "必须还有可执行方向"
    moved = client.post(f"/api/story-builder/runtime/advance?novel_id={novel_id}",
                        json={"action_id": available[0],
                              "expected_revision": state["revision"]})
    assert moved.status_code == 200, moved.text

    export = command_center(tmp_path, novel_id)["export"]
    assert export["ready"] is False
    assert export["blockers"], "过期大纲必须成为真实 blocker"
    assert export["headline"] == export["blockers"][0]
    assert "还差 0 步" not in export["headline"]


# ------------------------------------------- NF-003 / NF-004 生成内容与导出
def test_chapter_titles_are_unique_and_content_bearing(tmp_path: Path) -> None:
    client = client_for(tmp_path)
    for novel_id, genre, idea in IDEAS:
        build_route_state(client, novel_id, idea, genre)
        forge_and_confirm(client, novel_id)
        chain = client.get(
            f"/api/story-builder/outline/chain?novel_id={novel_id}&branch_id=main").json()
        items = [row["items"][0] for row in chain["chapters"]]
        assert len(items) == 30
        bodies = [row["title"].split("：", 1)[-1] for row in items]
        assert len(set(bodies)) == len(bodies), f"{novel_id}: 章节标题正文必须唯一"
        for row in items:
            for banned in FIELD_LABEL_BLACKLIST:
                assert banned not in row["title"], f"{novel_id}: 占位标题 {row['title']}"
            assert row["source_ids"], "章节必须保留可追溯来源（结构化字段）"
            assert not any(INTERNAL_ID_PATTERN.search(text) for text in row["must_keep"]), (
                f"{novel_id}: 作者可见的必须保持内容里不得出现引擎 id")


def test_outline_exports_have_no_internal_ids(tmp_path: Path) -> None:
    client = client_for(tmp_path)
    novel_id = "novel_repair_exports"
    build_route_state(client, novel_id, IDEAS[0][2], IDEAS[0][1])
    forge_and_confirm(client, novel_id)

    markdown = client.get(
        f"/api/story-builder/outline/export?novel_id={novel_id}&branch_id=main"
        f"&format=markdown").json()["content"]
    assert "来源：来源：" not in markdown
    leak = INTERNAL_ID_PATTERN.search(markdown)
    assert leak is None, f"markdown 导出泄漏内部 id：{leak and leak.group(0)}"

    structured = json.loads(client.get(
        f"/api/story-builder/outline/export?novel_id={novel_id}&branch_id=main"
        f"&format=json").json()["content"])
    blob = " ".join(content_strings(structured["levels"]))
    leak = INTERNAL_ID_PATTERN.search(blob)
    assert leak is None, f"JSON 导出内容字段泄漏内部 id：{leak and leak.group(0)}"
    assert structured["levels"]["chapter"][0]["participants"], "参与者必须仍然存在"
    for row in structured["levels"]["chapter"]:
        for participant in row["participants"]:
            assert not participant.startswith(("npc_", "character_", "protagonist")), (
                "导出里的参与者必须是作者可读名字，而不是角色 id")


def test_v3_projection_chapters_speak_author_language(tmp_path: Path) -> None:
    client = client_for(tmp_path)
    novel_id = "novel_repair_projection"
    build_route_state(client, novel_id, IDEAS[1][2], IDEAS[1][1])
    forge_and_confirm(client, novel_id)
    payload = command_center(tmp_path, novel_id)
    rows = payload["outline"]["chapters"]
    assert rows
    for row in rows:
        blob = " ".join([row["title"], row["summary"], row["location"], row["time"],
                         *row["goals"], *row["conflicts"], *row["participants"]])
        leak = INTERNAL_ID_PATTERN.search(blob)
        assert leak is None, f"V3 投影泄漏内部 id：{leak and leak.group(0)}"
        assert "tick" not in row["time"], "时间必须是作者语言（第 N 回合）"


def test_content_pack_title_is_readable(tmp_path: Path) -> None:
    client = client_for(tmp_path)
    novel_id = "novel_repair_title"
    build_route_state(client, novel_id, IDEAS[0][2], IDEAS[0][1])
    pack_id = command_center(tmp_path, novel_id)["novel"]["content_pack_id"]
    pack = json.loads(
        (tmp_path / "novel" / "config" / "story_engine" / f"{pack_id}.json")
        .read_text(encoding="utf-8"))
    title = pack["title"]
    assert "（设定草稿）" not in title
    assert not title.endswith(("的", "在", "把", "和", "与", "是"))
    assert len(title) <= 24


# ------------------------------------------------------------- NF-008 推演 CTA
def test_projection_never_recommends_an_unavailable_action(tmp_path: Path) -> None:
    """投影说「可执行」的方向，推进必须真的成功（不再出现点主 CTA 就打 422）。"""

    client = client_for(tmp_path)
    novel_id = "novel_repair_simulation"
    build_route_state(client, novel_id, IDEAS[0][2], IDEAS[0][1], turns=0)
    for _ in range(6):
        payload = command_center(tmp_path, novel_id)
        candidates = payload["simulation"]["candidates"]
        available = [row for row in candidates if row["available"]]
        if not available:
            break
        chosen = available[0]
        moved = client.post(f"/api/story-builder/runtime/advance?novel_id={novel_id}",
                            json={"action_id": chosen["candidate_id"],
                                  "expected_revision": payload["simulation"]["revision"]})
        assert moved.status_code == 200, (
            f"投影推荐的可执行方向必须真的能推演：{chosen['candidate_id']} → "
            f"{moved.status_code} {moved.text[:200]}")
    # 资源耗尽后：要么还有可执行方向，要么明确说明没有（而不是推荐一个必然失败的）。
    final = command_center(tmp_path, novel_id)["simulation"]
    if not any(row["available"] for row in final["candidates"]):
        assert all(row["blocked_reason"] or row["requirements"] or row["risks"]
                   for row in final["candidates"] if not row["available"]), (
            "不可执行方向必须说明缺什么")


def test_simulation_error_message_uses_author_language(tmp_path: Path) -> None:
    """推演失败文案不得出现 protagonist / favors 这类引擎标识。"""

    client = client_for(tmp_path)
    novel_id = "novel_repair_sim_error"
    build_route_state(client, novel_id, IDEAS[0][2], IDEAS[0][1], turns=0)
    last_error = ""
    for _ in range(8):
        payload = command_center(tmp_path, novel_id)
        candidates = payload["simulation"]["candidates"]
        blocked = [row for row in candidates if not row["available"]]
        available = [row for row in candidates if row["available"]]
        if blocked:
            response = client.post(
                f"/api/story-builder/runtime/advance?novel_id={novel_id}",
                json={"action_id": blocked[0]["candidate_id"],
                      "expected_revision": payload["simulation"]["revision"]})
            if response.status_code == 422:
                last_error = str(response.json()["detail"].get("message") or "")
        if not available:
            break
        moved = client.post(f"/api/story-builder/runtime/advance?novel_id={novel_id}",
                            json={"action_id": available[0]["candidate_id"],
                                  "expected_revision": payload["simulation"]["revision"]})
        if moved.status_code != 200:
            break
    if last_error:
        assert "protagonist" not in last_error and "favors" not in last_error, (
            f"错误文案必须翻成作者语言：{last_error}")


# --------------------------------------------------------------- NF-011 作品管理
def test_novel_rename_and_archive_delete_leave_no_orphans(tmp_path: Path) -> None:
    client = client_for(tmp_path)
    novel_id = "novel_repair_admin"
    build_route_state(client, novel_id, IDEAS[0][2], IDEAS[0][1])
    forge_and_confirm(client, novel_id, volumes=1, arcs=1, chapters=2)
    assert client.post("/api/story-builder/writer/drafts",
                       json={"novel_id": novel_id, "branch_id": "main"}).status_code == 201

    renamed = client.patch(f"/api/story-builder/novels/{novel_id}",
                           json={"title": "新的作品名"})
    assert renamed.status_code == 200, renamed.text
    assert renamed.json()["title"] == "新的作品名"

    unconfirmed = client.delete(f"/api/story-builder/novels/{novel_id}")
    assert unconfirmed.status_code == 409, "删除必须二次确认"

    removed = client.delete(f"/api/story-builder/novels/{novel_id}?confirm=true&reason=test")
    assert removed.status_code == 200, removed.text
    manifest = removed.json()
    assert manifest["recoverable"] is True and manifest["moved"]
    assert client.get("/api/story-builder/novels").json()["novels"] == []
    leftovers = [path for path in tmp_path.rglob(f"*{novel_id}*")
                 if "archived_novels" not in path.as_posix()]
    assert leftovers == [], f"删除后不得留下孤儿文件：{leftovers}"


def test_writer_legacy_directory_is_read_only_compatible(tmp_path: Path) -> None:
    """历史 writer 目录（workspace/.../writer_v1）只读兼容：canonical 为空时才使用。"""

    novel_id = "novel_repair_legacy_writer"
    legacy = tmp_path / "workspace" / "wasteland_001_exports" / "writer_v1" / novel_id
    (legacy / "drafts").mkdir(parents=True, exist_ok=True)
    (legacy / "drafts" / "draft_legacy.json").write_text(json.dumps({
        "draft_id": "draft_legacy", "chapter_id": "", "event_id": "",
        "generated_at": "2026-01-01T00:00:00+00:00", "truth_layer": "preview",
        "validation": {"accepted": True}, "fact_sync": {"synced": False},
    }, ensure_ascii=False), encoding="utf-8")
    rows = WriterDraftService(tmp_path, novel_id).list_drafts()
    assert [row["draft_id"] for row in rows] == ["draft_legacy"]

    canonical = tmp_path / WRITER_DIR / novel_id
    (canonical / "drafts").mkdir(parents=True, exist_ok=True)
    (canonical / "drafts" / "draft_new.json").write_text(json.dumps({
        "draft_id": "draft_new", "chapter_id": "", "event_id": "",
        "generated_at": "2026-02-01T00:00:00+00:00", "truth_layer": "preview",
        "validation": {"accepted": True}, "fact_sync": {"synced": False},
    }, ensure_ascii=False), encoding="utf-8")
    rows = WriterDraftService(tmp_path, novel_id).list_drafts()
    assert [row["draft_id"] for row in rows] == ["draft_new"], (
        "canonical 有草稿时不能再把历史目录算一遍（避免同一份草稿被计两次）")
