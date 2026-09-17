"""W5 最终验收：三题材从“一句话创意”跑到“详细章纲导出”，全程只用 API。

验收问题只有一个：

> 一个全新作者，只输入一个小说创意，能不能在不手写 JSON、不修改核心代码的前提下，
> 最终得到一套高质量、完整、可修改、可追溯的整本小说剧情与详细章纲？
"""

from __future__ import annotations

import base64
import io
import json
import zipfile
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from novelforge.api.story_builder_routes import install_story_builder_api
from novelforge.story_builder import load_story_catalog

PROJECT_ROOT = Path(__file__).resolve().parents[1]

NOVELS = (
    ("novel_final_xianxia", "修仙",
     "一个普通维修工发现城市其实运行在一套隐藏的修仙操作系统上，灵石就是它的能源。"),
    ("novel_final_scifi", "科幻",
     "一名被裁员的飞船维修师发现公司用算力在殖民地之间买卖记忆，他的工牌是唯一钥匙。"),
    ("novel_final_mystery", "都市悬疑",
     "一名调查记者追查连环失踪案，所有证词都指向同一份被篡改的档案和她自己的旧报道。"),
)


def client_for(tmp_path: Path) -> TestClient:
    source = PROJECT_ROOT / "novel" / "config" / "story_engine"
    target = tmp_path / "novel" / "config" / "story_engine"
    target.mkdir(parents=True, exist_ok=True)
    for item in source.glob("*.json"):
        target.joinpath(item.name).write_text(item.read_text(encoding="utf-8"), encoding="utf-8")
    app = FastAPI()
    install_story_builder_api(app, tmp_path, catalog=load_story_catalog(PROJECT_ROOT))
    return TestClient(app)


def run_full_flow(client: TestClient, novel_id: str, idea: str, *, turns: int = 12) -> dict:
    """只用 API 走完整条路径；任何一步失败都直接断言失败。"""

    assert client.post("/api/story-builder/novels",
                       json={"novel_id": novel_id, "title": novel_id}).status_code == 201
    suggestion = client.post(f"/api/story-builder/creative/suggest?novel_id={novel_id}",
                             json={"idea": idea, "reader_experience": "紧张、有长期追读感"})
    assert suggestion.status_code == 200, suggestion.text
    body = suggestion.json()
    assert len(body["genre_candidates"]) >= 3
    choice = body["genre_candidates"][0]
    brief = client.put(f"/api/story-builder/creative/brief?novel_id={novel_id}", json={
        "original_idea": idea, "references": [], "reader_experience": "紧张、有长期追读感",
        "selected_genre": choice["genre"], "selected_template_id": choice["template_id"],
        "selected_content_pack_id": choice["content_pack_id"],
        "tone": body["tone_candidates"][0]["tone"],
        "selling_points": [row["text"] for row in body["selling_point_candidates"][:3]],
    })
    assert brief.status_code == 200, brief.text

    seed_payload = client.post(f"/api/story-builder/settings/seed?novel_id={novel_id}",
                               json={}).json()
    seed = seed_payload["seed"]
    for group in ("world_rules", "protagonist", "characters", "factions", "relationships",
                  "progression", "conflicts", "main_line", "foreshadows"):
        assert seed[group], f"{group} 必须有候选"
    saved = client.put(f"/api/story-builder/settings/seed?novel_id={novel_id}",
                       json={"seed": seed, "selected": seed["selected"]})
    assert saved.status_code == 200, saved.text
    check = client.post(f"/api/story-builder/settings/check?novel_id={novel_id}",
                        json={"repair": True}).json()
    assert check["ok"], json.dumps(check["findings"], ensure_ascii=False)
    assert check["available_candidates"]

    started = client.post(f"/api/story-builder/runtime/start?novel_id={novel_id}", json={})
    assert started.status_code == 200, started.text
    revision = 0
    for index in range(turns):
        state = client.get(f"/api/story-builder/runtime/state?novel_id={novel_id}").json()
        available = [row["action_id"] for row in state["candidates"] if row["available"]]
        assert available, "任何时刻都必须有可用候选"
        moved = client.post(f"/api/story-builder/runtime/advance?novel_id={novel_id}",
                            json={"action_id": available[index % len(available)],
                                  "expected_revision": state["revision"]})
        assert moved.status_code == 200, moved.text
        revision = moved.json()["revision"]
    assert revision >= 8

    branch_a = client.post(f"/api/story-builder/runtime/branches/fork?novel_id={novel_id}",
                           json={"source_branch": "main", "label": "A"}).json()["branch_id"]
    branch_b = client.post(f"/api/story-builder/runtime/branches/fork?novel_id={novel_id}",
                           json={"source_branch": "main", "label": "B"}).json()["branch_id"]
    for branch in (branch_a, branch_b):
        branch_state = client.get(
            f"/api/story-builder/runtime/state?novel_id={novel_id}&branch_id={branch}").json()
        available = [row["action_id"] for row in branch_state["candidates"] if row["available"]]
        client.post(f"/api/story-builder/runtime/advance?novel_id={novel_id}",
                    json={"action_id": available[-1], "branch_id": branch,
                          "expected_revision": branch_state["revision"]})
    comparison = client.get(
        f"/api/story-builder/runtime/branches/compare?novel_id={novel_id}"
        f"&base_branch=main&target_branch={branch_a}").json()
    assert comparison["rows"], "两条路线必须存在结构化差异"
    merge = client.post(f"/api/story-builder/runtime/branches/merge?novel_id={novel_id}",
                        json={"target_branch": "main", "source_branches": [branch_a],
                              "item_keys": []}).json()
    assert merge["history_preserved"] is True
    frozen = client.post(f"/api/story-builder/runtime/branches/freeze?novel_id={novel_id}",
                         json={"branch_id": branch_b, "label": "正式路线"}).json()
    assert frozen["official_branch"] == branch_b

    panels = {
        "world": client.get(f"/api/story-builder/creator/world?novel_id={novel_id}").json(),
        "characters": client.get(
            f"/api/story-builder/creator/characters?novel_id={novel_id}"
            f"&character_id=protagonist").json(),
        "plot": client.get(f"/api/story-builder/creator/plot?novel_id={novel_id}").json(),
        "progression": client.get(
            f"/api/story-builder/creator/progression?novel_id={novel_id}").json(),
        "memory": client.get(f"/api/story-builder/creator/memory?novel_id={novel_id}").json(),
        "director": client.get(f"/api/story-builder/creator/director?novel_id={novel_id}").json(),
        "linkage": client.get(f"/api/story-builder/creator/linkage?novel_id={novel_id}").json(),
    }
    assert panels["world"]["meta"]["preview"] is False
    assert panels["characters"]["detail"]["goals"]["long_term"], "人物必须有长期目标"
    assert panels["plot"]["candidates"], "剧情面板必须有候选"
    assert len([row for row in panels["progression"]["categories"] if row["nodes"]]) >= 7
    assert panels["memory"]["foreshadow_timeline"] is not None
    assert panels["director"]["weights"]
    assert panels["linkage"]["counts"]["happened"] >= 1

    forged = client.post(f"/api/story-builder/outline/forge?novel_id={novel_id}",
                         json={"branch_id": "main", "volumes": 3, "arcs_per_volume": 2,
                               "chapters_per_arc": 5})
    assert forged.status_code == 200, forged.text
    counts = forged.json()["counts"]
    assert (counts["volumes"], counts["arcs"], counts["chapters"]) == (3, 6, 30)
    assert forged.json()["quality"]["ok"], forged.json()["quality"]["findings"]
    chain = client.get(f"/api/story-builder/outline/chain?novel_id={novel_id}").json()
    assert chain["fresh"] is True
    chapter = chain["chapters"][0]["items"][0]
    assert chapter["goals"] and chapter["conflicts"] and chapter["ending_hook"]
    # NF-004：可追溯性仍然必须成立，但来源 id 存在机器字段里，
    # 作者可见的 must_keep 不含引擎 id。
    assert any(str(row).startswith("route_") for row in chapter["source_ids"]), \
        "章纲要能追溯到路线事实"
    assert not any("route_" in row for row in chapter["must_keep"]), \
        "作者可见的约束说明里不得出现引擎来源 id"

    confirm = client.post(f"/api/story-builder/outline/confirm?novel_id={novel_id}", json={})
    assert confirm.status_code == 200, confirm.text
    volume = chain["volumes"][0]
    impact = client.get(
        f"/api/story-builder/outline/impact?novel_id={novel_id}"
        f"&package_id={volume['package_id']}&item_id={volume['items'][0]['item_id']}").json()
    assert impact["affected_downstream"]
    revised = client.post(f"/api/story-builder/outline/revise?novel_id={novel_id}",
                          json={"package_id": volume["package_id"],
                                "item_id": volume["items"][0]["item_id"],
                                "expected_version": 1,
                                "changes": {"summary": "作者改写的卷目标"}})
    assert revised.status_code == 200, revised.text
    diff = client.get(
        f"/api/story-builder/outline/version-diff?novel_id={novel_id}"
        f"&package_id={volume['package_id']}&from_version=1&to_version=2").json()
    assert diff["items"] and "summary" in diff["items"][0]["changed_fields"]
    restore = client.post(f"/api/story-builder/outline/restore?novel_id={novel_id}",
                          json={"package_id": volume["package_id"], "version": 1})
    assert restore.status_code == 200
    after_edit = client.get(
        f"/api/story-builder/runtime/state?novel_id={novel_id}&branch_id=main").json()
    assert after_edit["summary"]["effect_log"] >= 1, "改写大纲不得改动已发生事实"

    markdown = client.get(f"/api/story-builder/outline/export?novel_id={novel_id}").json()
    assert "不得违反" in markdown["content"] and "结尾钩子" in markdown["content"]
    structured = json.loads(client.get(
        f"/api/story-builder/outline/export?novel_id={novel_id}&format=json").json()["content"])
    assert len(structured["levels"]["chapter"]) == 30
    docx = client.get(f"/api/story-builder/outline/export?novel_id={novel_id}&format=docx").json()
    raw = base64.b64decode(docx["content_base64"])
    assert zipfile.is_zipfile(io.BytesIO(raw))

    return {"novel_id": novel_id, "genre": choice["genre"], "revision": revision,
            "pack_id": saved.json()["pack_id"], "chapters": counts["chapters"],
            "chapter_titles": [row["items"][0]["title"] for row in chain["chapters"]],
            "chapter_summaries": [row["items"][0]["summary"] for row in chain["chapters"]],
            "book_goal": chain["book"]["items"][0]["summary"],
            "route_rows": len(comparison["rows"]), "merge_merged": len(merge["merged"]),
            "official_branch": frozen["official_branch"],
            "export_length": len(markdown["content"])}


def test_three_genres_complete_the_final_goal_in_one_flow(tmp_path: Path) -> None:
    client = client_for(tmp_path)
    results = {}
    for novel_id, label, idea in NOVELS:
        results[label] = run_full_flow(client, novel_id, idea)
    assert {row["chapters"] for row in results.values()} == {30}
    assert len({row["book_goal"] for row in results.values()}) == 3, "不同题材必须产出不同主线"
    assert len({row["chapter_summaries"][0] for row in results.values()}) == 3, \
        "不同题材的首章必须带着各自小说的前提，而不是同一句话"
    assert len({row["chapter_summaries"][-1] for row in results.values()}) == 3
    assert len({row["export_length"] for row in results.values()}) == 3
    assert len({row["pack_id"] for row in results.values()}) == 3
    assert len({row["official_branch"] for row in results.values()}) == 3
    assert all(row["route_rows"] >= 1 for row in results.values())


def test_final_goal_needs_no_handwritten_json_or_code_change(tmp_path: Path) -> None:
    """最终验收问题的直接回答：不手写 JSON、不改代码，也能拿到剧情与详细章纲。"""

    client = client_for(tmp_path)
    result = run_full_flow(client, "novel_final_single", NOVELS[0][2], turns=10)
    novel_dir = tmp_path / "novel"
    assert (novel_dir / "config" / "story_engine" / f"{result['pack_id']}.json").is_file()
    assert (novel_dir / "authoring" / "story_engine" / "profiles").is_dir()
    assert list((novel_dir / "authoring" / "story_engine" / "state").rglob("*.json"))
    outline_root = novel_dir / "authoring" / "story_builder" / "outlines"
    for level in ("book", "volume", "arc", "chapter"):
        assert list((outline_root / level).rglob("v*.json")), f"缺少 {level} 大纲文件"
    chain = client.get(
        "/api/story-builder/outline/chain?novel_id=novel_final_single").json()
    book_package = chain["book"]["package_id"]
    versions = client.get(
        f"/api/story-builder/outline/versions?novel_id=novel_final_single"
        f"&package_id={book_package}").json()
    assert versions["versions"], "必须能查询版本历史"
    assert versions["versions"][0]["status"] == "CONFIRMED", "已确认版本构成不可改写的历史"
