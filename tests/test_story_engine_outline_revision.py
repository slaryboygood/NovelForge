"""W4 专项：大纲修改联动、版本比较 / 回退 / 合并、导出扩展（JSON / DOCX）。"""

from __future__ import annotations

import base64
import io
import json
import zipfile
from pathlib import Path
from xml.dom import minidom

from fastapi import FastAPI
from fastapi.testclient import TestClient

from novelforge.api.story_builder_routes import install_story_builder_api
from novelforge.story_builder import load_story_catalog
from novelforge.story_builder.models import OutlineLevel, OutlineStatus
from novelforge.story_builder.outlines import StoryOutlineRepository
from novelforge.story_engine.outline_revision import (
    RevisionError,
    diff_versions,
    export_docx,
    export_outline,
    export_structured_json,
    impact_of_change,
    list_versions,
    merge_versions,
    restore_version,
    revise_item,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
IDEA = "一个普通维修工发现城市其实运行在一套隐藏的修仙操作系统上。"
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


def forged_novel(tmp_path: Path, novel_id: str = "novel_w4", *, confirm: bool = True) -> TestClient:
    client = client_for(tmp_path)
    assert client.post("/api/story-builder/novels",
                       json={"novel_id": novel_id, "title": novel_id}).status_code == 201
    client.put(f"/api/story-builder/creative/brief?novel_id={novel_id}",
               json={"original_idea": IDEA, "selected_genre": "xianxia", "tone": "紧张悬疑"})
    seed = client.post(f"/api/story-builder/settings/seed?novel_id={novel_id}",
                       json={}).json()["seed"]
    client.put(f"/api/story-builder/settings/seed?novel_id={novel_id}",
               json={"seed": seed, "selected": seed["selected"]})
    client.post(f"/api/story-builder/runtime/start?novel_id={novel_id}", json={})
    for index in range(10):
        state = client.get(f"/api/story-builder/runtime/state?novel_id={novel_id}").json()
        available = [row["action_id"] for row in state["candidates"] if row["available"]]
        if not available:
            break
        moved = client.post(f"/api/story-builder/runtime/advance?novel_id={novel_id}",
                            json={"action_id": available[index % len(available)],
                                  "expected_revision": state["revision"]})
        if moved.status_code != 200:
            break
    forged = client.post(f"/api/story-builder/outline/forge?novel_id={novel_id}",
                         json=STRUCTURE)
    assert forged.status_code == 200, forged.text
    if confirm:
        confirmed = client.post(f"/api/story-builder/outline/confirm?novel_id={novel_id}",
                                json={})
        assert confirmed.status_code == 200, confirmed.text
    return client


def test_impact_lists_downstream_and_protects_happened_facts(tmp_path: Path) -> None:
    client = forged_novel(tmp_path)
    chain = client.get("/api/story-builder/outline/chain?novel_id=novel_w4").json()
    volume = chain["volumes"][0]
    item_id = volume["items"][0]["item_id"]
    impact = impact_of_change(tmp_path, "novel_w4", branch_id="main",
                              package_id=volume["package_id"], item_id=item_id,
                              changes={"summary": "改卷目标"})
    assert impact["level"] == "VOLUME"
    assert impact["affected_downstream"], "改卷目标必须提示下游篇章 / 章节"
    levels = {row["level"] for row in impact["affected_downstream"]}
    assert {"ARC", "CHAPTER"} <= levels
    assert impact["affected_happened"], "必须指出哪些已发生章节被波及（只提示）"
    # 不允许改来源类字段。
    guarded = impact_of_change(tmp_path, "novel_w4", branch_id="main",
                               package_id=volume["package_id"], item_id=item_id,
                               changes={"must_keep": ["伪造来源"]})
    assert guarded["protected_fields"] == ["must_keep"]
    try:
        revise_item(tmp_path, "novel_w4", branch_id="main", package_id=volume["package_id"],
                    item_id=item_id, changes={"must_keep": ["伪造来源"]}, expected_version=1)
    except RevisionError as exc:
        assert exc.code == "OUTLINE_FIELD_NOT_EDITABLE"
    else:  # pragma: no cover - 明确失败路径
        raise AssertionError("来源字段不允许被改写")


def test_revise_creates_new_version_and_reports_impact(tmp_path: Path) -> None:
    client = forged_novel(tmp_path)
    chain = client.get("/api/story-builder/outline/chain?novel_id=novel_w4").json()
    chapter = chain["chapters"][0]
    item_id = chapter["items"][0]["item_id"]
    result = revise_item(tmp_path, "novel_w4", branch_id="main",
                         package_id=chapter["package_id"], item_id=item_id,
                         changes={"ending_hook": "作者改写的钩子"}, expected_version=1)
    assert result["outline"]["version"] == 2
    assert result["outline"]["status"] == OutlineStatus.DRAFT.value
    assert result["outline"]["route_source"] == chain["chapters"][0]["route_source"], \
        "改写写作设计不得改动来源"
    assert result["impact"]["affected_downstream"] == []
    # 旧版本仍然可读，新版本可读。
    repository = StoryOutlineRepository(tmp_path)
    assert repository.load(chapter["package_id"], 1).items[0].ending_hook != "作者改写的钩子"
    assert repository.load(chapter["package_id"], 2).items[0].ending_hook == "作者改写的钩子"


def test_versions_diff_restore_and_merge(tmp_path: Path) -> None:
    client = forged_novel(tmp_path)
    chain = client.get("/api/story-builder/outline/chain?novel_id=novel_w4").json()
    volume = chain["volumes"][0]
    item_id = volume["items"][0]["item_id"]
    revise_item(tmp_path, "novel_w4", branch_id="main", package_id=volume["package_id"],
                item_id=item_id, changes={"summary": "新的卷目标"}, expected_version=1)
    listing = list_versions(tmp_path, "novel_w4", volume["package_id"])
    assert [row["version"] for row in listing["versions"]] == [1, 2]
    # V1 是作者确认过的版本；改写不会覆盖它，而是产生 V2（DRAFT）。
    assert listing["versions"][0]["status"] == "CONFIRMED"
    assert listing["versions"][1]["status"] == "DRAFT"
    diff = diff_versions(tmp_path, "novel_w4", volume["package_id"],
                         from_version=1, to_version=2)
    assert [row.status for row in diff.items] == ["changed"]
    assert "summary" in diff.items[0].changed_fields
    # 回退：生成 V3，内容回到 V1。
    restored = restore_version(tmp_path, "novel_w4", package_id=volume["package_id"], version=1)
    assert restored["outline"]["version"] == 3
    repository = StoryOutlineRepository(tmp_path)
    assert repository.load(volume["package_id"], 3).items[0].summary == \
        repository.load(volume["package_id"], 1).items[0].summary
    # 合并：把 V2 的条目合并到 V1 副本上，生成 V4。
    merged = merge_versions(tmp_path, "novel_w4", package_id=volume["package_id"],
                            base_version=1, source_version=2, item_ids=[item_id])
    assert merged["merged_items"] == [item_id]
    assert merged["outline"]["version"] == 4
    assert repository.load(volume["package_id"], 4).items[0].summary == "新的卷目标"
    assert len(list_versions(tmp_path, "novel_w4", volume["package_id"])["versions"]) == 4


def test_confirmed_version_cannot_be_overwritten(tmp_path: Path) -> None:
    client = forged_novel(tmp_path)  # 整条链已确认
    chain = client.get("/api/story-builder/outline/chain?novel_id=novel_w4").json()
    book = chain["book"]
    repository = StoryOutlineRepository(tmp_path)
    package = repository.load(book["package_id"], book["version"])
    assert package.status == OutlineStatus.CONFIRMED
    tampered = package.model_copy(update={
        "items": [package.items[0].model_copy(update={"summary": "偷偷改历史"})]})
    try:
        repository.save(tampered)
    except Exception as exc:  # noqa: BLE001 - 已确认版本必须不可覆盖
        assert getattr(exc, "code", "") == "OUTLINE_CONFIRMED_IMMUTABLE"
    else:  # pragma: no cover - 明确失败路径
        raise AssertionError("已确认版本不允许被覆盖")
    assert repository.load(book["package_id"], book["version"]).items[0].summary != "偷偷改历史"


def test_structured_json_and_docx_exports(tmp_path: Path) -> None:
    forged_novel(tmp_path)
    structured = export_structured_json(tmp_path, "novel_w4")
    payload = json.loads(structured["content"])
    assert payload["novel_id"] == "novel_w4"
    assert len(payload["levels"]["chapter"]) == 30
    assert len(payload["levels"]["volume"]) == 3
    assert payload["packages"]["book"].startswith("ol_")
    assert payload["route_source"]["branch_id"] == "main"
    docx = export_docx(tmp_path, "novel_w4")
    archive = zipfile.ZipFile(io.BytesIO(docx["content"]))
    assert sorted(archive.namelist()) == ["[Content_Types].xml", "_rels/.rels",
                                          "word/_rels/document.xml.rels", "word/document.xml"]
    document = archive.read("word/document.xml").decode("utf-8")
    minidom.parseString(document)  # XML 必须合法
    assert "不得违反" in document and "结尾钩子" in document
    assert "剧情与大纲" in document
    # 统一入口支持三种格式，未知格式报错。
    assert export_outline(tmp_path, "novel_w4", fmt="json")["format"] == "json"
    assert export_outline(tmp_path, "novel_w4", fmt="markdown")["format"] == "markdown"
    assert export_outline(tmp_path, "novel_w4", fmt="docx")["format"] == "docx"
    try:
        export_outline(tmp_path, "novel_w4", fmt="pdf")
    except RevisionError as exc:
        assert exc.code == "OUTLINE_EXPORT_FORMAT_UNSUPPORTED"
    else:  # pragma: no cover - 明确失败路径
        raise AssertionError("未知导出格式必须被拒绝")


def test_w4_api_roundtrip(tmp_path: Path) -> None:
    client = forged_novel(tmp_path)
    chain = client.get("/api/story-builder/outline/chain?novel_id=novel_w4").json()
    arc = chain["arcs"][0]
    package_id = arc["package_id"]
    item_id = arc["items"][0]["item_id"]
    impact = client.get("/api/story-builder/outline/impact?novel_id=novel_w4"
                        f"&package_id={package_id}&item_id={item_id}")
    assert impact.status_code == 200, impact.text
    assert impact.json()["affected_downstream"]
    revised = client.post("/api/story-builder/outline/revise?novel_id=novel_w4",
                          json={"package_id": package_id, "item_id": item_id,
                                "expected_version": 1,
                                "changes": {"summary": "作者改写的篇章问题"}})
    assert revised.status_code == 200, revised.text
    versions = client.get("/api/story-builder/outline/versions?novel_id=novel_w4"
                          f"&package_id={package_id}").json()
    assert [row["version"] for row in versions["versions"]] == [1, 2]
    diff = client.get("/api/story-builder/outline/version-diff?novel_id=novel_w4"
                      f"&package_id={package_id}&from_version=1&to_version=2").json()
    assert diff["items"] and "summary" in diff["items"][0]["changed_fields"]
    restored = client.post("/api/story-builder/outline/restore?novel_id=novel_w4",
                           json={"package_id": package_id, "version": 1})
    assert restored.status_code == 200 and restored.json()["outline"]["version"] == 3
    merged = client.post("/api/story-builder/outline/merge-versions?novel_id=novel_w4",
                         json={"package_id": package_id, "base_version": 1,
                               "source_version": 2, "item_ids": [item_id]})
    assert merged.status_code == 200 and merged.json()["outline"]["version"] == 4
    # 非法字段被拒绝（422）。
    bad = client.post("/api/story-builder/outline/revise?novel_id=novel_w4",
                      json={"package_id": package_id, "item_id": item_id,
                            "expected_version": 4, "changes": {"must_keep": ["伪造"]}})
    assert bad.status_code == 422
    # 导出格式。
    assert client.get("/api/story-builder/outline/export?novel_id=novel_w4"
                      "&format=json").json()["format"] == "json"
    docx = client.get("/api/story-builder/outline/export?novel_id=novel_w4&format=docx").json()
    assert docx["size"] > 1000
    raw = base64.b64decode(docx["content_base64"])
    assert zipfile.is_zipfile(io.BytesIO(raw))


def test_revision_layer_reuses_versions_and_has_no_hardcoding(tmp_path: Path) -> None:
    source = (PROJECT_ROOT / "src/novelforge/story_engine/outline_revision.py").read_text(
        encoding="utf-8")
    for pattern in ("if genre ==", "if world_type ==", "if novel_id ==", "硅基升维", "silicon",
                    "class OutlineItem(", "class OutlinePackage("):
        assert pattern not in source, f"outline_revision.py 违反约束：{pattern}"
    for marker in ("StoryOutlineRepository", "OutlineStatus", "load_forge_chain",
                   "export_forge_markdown"):
        assert marker in source, f"outline_revision.py 必须复用：{marker}"
    # 版本历史只追加：改写多次后旧版本仍在。
    client = forged_novel(tmp_path)
    chain = client.get("/api/story-builder/outline/chain?novel_id=novel_w4").json()
    chapter = chain["chapters"][0]
    for index in range(3):
        revise_item(tmp_path, "novel_w4", branch_id="main", package_id=chapter["package_id"],
                    item_id=chapter["items"][0]["item_id"],
                    changes={"ending_hook": f"钩子 {index}"}, expected_version=index + 1)
    versions = list_versions(tmp_path, "novel_w4", chapter["package_id"])["versions"]
    assert [row["version"] for row in versions] == [1, 2, 3, 4]
    repository = StoryOutlineRepository(tmp_path)
    assert repository.load(chapter["package_id"], 4).level == OutlineLevel.CHAPTER
