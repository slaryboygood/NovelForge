"""W2 专项：路线试演、结构化对比、合并与正式路线冻结。"""

from __future__ import annotations

import json
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from novelforge.api.story_builder_routes import install_story_builder_api
from novelforge.story_builder import load_story_catalog
from novelforge.story_engine.route_lab import (
    ROUTE_LAB_KEY,
    compare_branches,
    compare_states,
    freeze_branch,
    list_branches,
    merge_branches,
    merge_preview,
)
from novelforge.story_engine.context import runtime_key_for
from novelforge.story_engine.profile import NovelProfileRepository
from novelforge.story_engine.storage import StoryStateRepository

PROJECT_ROOT = Path(__file__).resolve().parents[1]
IDEA = "一个普通维修工发现城市其实运行在一套隐藏的修仙操作系统上。"
RUNTIME_VERSION = 1


def client_for(tmp_path: Path) -> TestClient:
    source = PROJECT_ROOT / "novel" / "config" / "story_engine"
    target = tmp_path / "novel" / "config" / "story_engine"
    target.mkdir(parents=True, exist_ok=True)
    for item in source.glob("*.json"):
        target.joinpath(item.name).write_text(item.read_text(encoding="utf-8"), encoding="utf-8")
    app = FastAPI()
    install_story_builder_api(app, tmp_path, catalog=load_story_catalog(PROJECT_ROOT))
    return TestClient(app)


def started_novel(client: TestClient, novel_id: str = "novel_route") -> str:
    assert client.post("/api/story-builder/novels",
                       json={"novel_id": novel_id, "title": novel_id}).status_code == 201
    client.put(f"/api/story-builder/creative/brief?novel_id={novel_id}",
               json={"original_idea": IDEA, "selected_genre": "xianxia", "tone": "紧张悬疑"})
    seed = client.post(f"/api/story-builder/settings/seed?novel_id={novel_id}",
                       json={}).json()["seed"]
    client.put(f"/api/story-builder/settings/seed?novel_id={novel_id}",
               json={"seed": seed, "selected": seed["selected"]})
    started = client.post(f"/api/story-builder/runtime/start?novel_id={novel_id}", json={})
    assert started.status_code == 200, started.text
    return novel_id


def fork(client: TestClient, novel_id: str, source: str, label: str) -> str:
    response = client.post(f"/api/story-builder/runtime/branches/fork?novel_id={novel_id}",
                           json={"source_branch": source, "label": label})
    assert response.status_code == 200, response.text
    return response.json()["branch_id"]


def advance(client: TestClient, novel_id: str, branch: str, action_id: str,
            revision: int | None = None) -> dict:
    body: dict[str, object] = {"action_id": action_id, "branch_id": branch}
    if revision is not None:
        body["expected_revision"] = revision
    response = client.post(f"/api/story-builder/runtime/advance?novel_id={novel_id}", json=body)
    assert response.status_code == 200, response.text
    return response.json()


def test_three_branches_keep_structured_differences(tmp_path: Path) -> None:
    client = client_for(tmp_path)
    novel_id = started_novel(client)
    branch_a = fork(client, novel_id, "main", "A 合作")
    branch_b = fork(client, novel_id, "main", "B 拒绝")
    branch_c = fork(client, novel_id, "main", "C 欺骗")
    advance(client, novel_id, branch_a, "act_investigate")
    advance(client, novel_id, branch_a, "act_go_hidden")
    advance(client, novel_id, branch_b, "act_go_work")
    advance(client, novel_id, branch_b, "act_wait")
    advance(client, novel_id, branch_c, "act_ask")
    advance(client, novel_id, branch_c, "act_investigate")

    listing = client.get(f"/api/story-builder/runtime/branches?novel_id={novel_id}").json()
    rows = {row["branch_id"]: row for row in listing["branches"]}
    assert {"main", branch_a, branch_b, branch_c} <= set(rows)
    assert rows[branch_a]["location"] == "hidden_place"
    assert rows[branch_b]["location"] == "work_place"
    assert rows[branch_c]["location"] == "start_place"
    assert rows[branch_a]["knowledge"] >= 1
    assert rows[branch_c]["knowledge"] >= 1
    assert rows[branch_b]["knowledge"] == 0
    assert listing["official_branch"] == ""

    comparison = client.get(
        f"/api/story-builder/runtime/branches/compare?novel_id={novel_id}"
        f"&base_branch=main&target_branch={branch_a}").json()
    kinds = {row["kind"] for row in comparison["rows"]}
    assert {"knowledge", "location"} <= kinds
    knowledge_rows = [row for row in comparison["rows"] if row["kind"] == "knowledge"]
    assert any(row["mergeable"] and row["effect"] for row in knowledge_rows)
    assert comparison["base_revision"] == 0 and comparison["target_revision"] == 2

    # 三条路线不是只换文本：当前地点、知识、资源至少各有一处真实差异。
    a_vs_b = client.get(
        f"/api/story-builder/runtime/branches/compare?novel_id={novel_id}"
        f"&base_branch={branch_a}&target_branch={branch_b}").json()
    assert {row["kind"] for row in a_vs_b["rows"]} >= {"knowledge", "location"}
    c_vs_b = client.get(
        f"/api/story-builder/runtime/branches/compare?novel_id={novel_id}"
        f"&base_branch={branch_b}&target_branch={branch_c}").json()
    assert {row["kind"] for row in c_vs_b["rows"]} >= {"knowledge", "resource"}


def test_merge_brings_selected_facts_without_rewriting_history(tmp_path: Path) -> None:
    client = client_for(tmp_path)
    novel_id = started_novel(client)
    branch_a = fork(client, novel_id, "main", "A 合作")
    branch_c = fork(client, novel_id, "main", "C 欺骗")
    advance(client, novel_id, branch_a, "act_investigate")
    advance(client, novel_id, branch_c, "act_ask")

    preview = client.post(
        f"/api/story-builder/runtime/branches/merge/preview?novel_id={novel_id}",
        json={"target_branch": "main", "source_branches": [branch_a, branch_c]}).json()
    assert len(preview["sources"]) == 2
    assert any(item["kind"] == "knowledge" for item in preview["sources"][0]["mergeable"])

    states = StoryStateRepository(tmp_path)
    slot = runtime_key_for(novel_id)
    before = states.load(slot, RUNTIME_VERSION, "main")
    assert not before.knowledge and before.timeline.tick == 0

    merged = client.post(
        f"/api/story-builder/runtime/branches/merge?novel_id={novel_id}",
        json={"target_branch": "main", "source_branches": [branch_a, branch_c],
              "item_keys": ["knowledge:core_record", "resource:favors"]}).json()
    assert merged["history_preserved"] is True
    assert any(item["kind"] == "knowledge" for item in merged["merged"])
    after = states.load(slot, RUNTIME_VERSION, "main")
    assert after.effect_log[:len(before.effect_log)] == before.effect_log, "历史必须原样保留"
    assert any(item.id == "core_record" and "protagonist" in item.holders for item in after.knowledge)
    assert any("merge:" in item.source for item in after.effect_log), "合并必须留下可追溯来源"
    assert after.model_dump(mode="json") != before.model_dump(mode="json")
    # 来源分支完全不受影响。
    source_state = states.load(slot, RUNTIME_VERSION, branch_c)
    assert source_state.resources["favors"].amount == 1, "合并只能修改目标分支"


def test_merge_reports_conflicts_without_overwriting(tmp_path: Path) -> None:
    client = client_for(tmp_path)
    novel_id = started_novel(client)
    branch_a = fork(client, novel_id, "main", "A")
    branch_b = fork(client, novel_id, "main", "B")
    advance(client, novel_id, branch_a, "act_wait")   # favors 保持 2
    advance(client, novel_id, branch_b, "act_ask")    # favors 2 → 1

    states = StoryStateRepository(tmp_path)
    slot = runtime_key_for(novel_id)
    # 目标分支更少 = 损失 → 冲突，不生成效果。
    loss = compare_branches(tmp_path, novel_id, base_branch=branch_a, target_branch=branch_b)
    loss_rows = [row for row in loss.rows if row.kind == "resource" and row.item_id == "favors"]
    assert loss_rows and loss_rows[0].conflict is True, "资源变少属于冲突，不能被自动合并"
    assert loss_rows[0].effect is None
    # 反过来看就是收益：可以合并（作者可以决定要不要把这份资源捞回来）。
    gain = compare_branches(tmp_path, novel_id, base_branch=branch_b, target_branch=branch_a)
    gain_rows = [row for row in gain.rows if row.kind == "resource" and row.item_id == "favors"]
    assert gain_rows and gain_rows[0].mergeable is True and gain_rows[0].conflict is False
    assert gain_rows[0].effect and gain_rows[0].effect["op"] == "add_resource"
    merged = merge_branches(tmp_path, novel_id, target_branch=branch_a,
                            source_branches=[branch_b])
    assert all(item["kind"] != "resource" for item in merged.merged), "损失不能被搬进来"
    assert any(item["reason"] == "CONFLICT" and item["item"] == "favors"
               for item in merged.skipped)
    assert states.load(slot, RUNTIME_VERSION, branch_a).resources["favors"].amount == 2
    assert states.load(slot, RUNTIME_VERSION, branch_b).resources["favors"].amount == 1


def test_freeze_marks_official_route_and_keeps_experiments_isolated(tmp_path: Path) -> None:
    client = client_for(tmp_path)
    novel_id = started_novel(client)
    branch_a = fork(client, novel_id, "main", "A 合作")
    advance(client, novel_id, branch_a, "act_investigate")
    frozen = client.post(f"/api/story-builder/runtime/branches/freeze?novel_id={novel_id}",
                         json={"branch_id": branch_a, "label": "正式路线"}).json()
    assert frozen["official_branch"] == branch_a
    assert frozen["frozen_revision"] == 1
    snapshot_id = frozen["frozen_branch"]

    listing = client.get(f"/api/story-builder/runtime/branches?novel_id={novel_id}").json()
    rows = {row["branch_id"]: row for row in listing["branches"]}
    assert rows[branch_a]["official"] is True
    assert rows[branch_a]["frozen_revision"] == 1
    assert snapshot_id in rows
    assert rows["main"]["official"] is False

    # 冻结后再推进其他分支，正式路线与快照都不变。
    advance(client, novel_id, "main", "act_go_work")
    states = StoryStateRepository(tmp_path)
    slot = runtime_key_for(novel_id)
    official = states.load(slot, RUNTIME_VERSION, branch_a)
    snapshot = states.load(slot, RUNTIME_VERSION, snapshot_id)
    assert official.timeline.tick == snapshot.timeline.tick
    assert snapshot.flags["frozen_from"] == branch_a
    assert official.location.current == "start_place"
    profile = NovelProfileRepository(tmp_path).load(novel_id)
    assert profile.world_profile[ROUTE_LAB_KEY]["official_branch"] == branch_a
    assert profile.world_profile[ROUTE_LAB_KEY]["frozen_revision"] == 1


def test_compare_is_pure_and_branch_list_is_isolated_per_novel(tmp_path: Path) -> None:
    client = client_for(tmp_path)
    first = started_novel(client, "novel_first")
    branch = fork(client, first, "main", "A")
    advance(client, first, branch, "act_investigate")
    states = StoryStateRepository(tmp_path)
    slot = runtime_key_for(first)
    before = states.load(slot, RUNTIME_VERSION, "main").model_dump(mode="json")
    compare_states(states.load(slot, RUNTIME_VERSION, "main"),
                   states.load(slot, RUNTIME_VERSION, branch))
    after = states.load(slot, RUNTIME_VERSION, "main").model_dump(mode="json")
    assert before == after, "对比必须只读"

    second = started_novel(client, "novel_second")
    listing = list_branches(tmp_path, second)
    assert [row["branch_id"] for row in listing["branches"]] == ["main"]
    assert listing["official_branch"] == ""
    assert merge_preview(tmp_path, first, target_branch="main",
                         source_branches=[branch])["sources"][0]["mergeable"]
    frozen_other = freeze_branch(tmp_path, second, branch_id="main", label="第二本")
    assert frozen_other["official_branch"] == "main"
    assert list_branches(tmp_path, first)["official_branch"] == ""


def test_branch_lab_layer_has_no_second_state_or_genre_logic(tmp_path: Path) -> None:
    source = (PROJECT_ROOT / "src/novelforge/story_engine/route_lab.py").read_text(
        encoding="utf-8")
    for pattern in ("class StoryState(", "class EventCard(", "if genre ==", "if world_type ==",
                    "硅基升维", "silicon"):
        assert pattern not in source, f"route_lab.py 违反约束：{pattern}"
    for marker in ("StoryStateRepository", "apply_effects", "EffectSpec", "resolve_novel_context",
                   "plot_tracks"):
        assert marker in source, f"route_lab.py 必须复用：{marker}"
    routes = (PROJECT_ROOT / "src/novelforge/api/story_builder_routes.py").read_text(
        encoding="utf-8")
    for route in ('"/runtime/branches"', '"/runtime/branches/fork"',
                  '"/runtime/branches/compare"', '"/runtime/branches/merge"',
                  '"/runtime/branches/freeze"'):
        assert route in routes, f"缺少路线实验室接口：{route}"
    # 路线实验室不写第二套状态文件：仍然只有 novel/authoring/story_engine/state 一个目录。
    client = client_for(tmp_path)
    novel_id = started_novel(client)
    fork(client, novel_id, "main", "A")
    state_dirs = {path.parent.name for path in
                  (tmp_path / "novel" / "authoring" / "story_engine" / "state").rglob("*.json")}
    assert state_dirs <= {runtime_key_for(novel_id)}
