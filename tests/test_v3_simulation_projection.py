"""V3-P3 推演投影回归：Route / Simulation 必须是真实状态的投影。

守卫 P3 的核心规则：

* 候选方向来自引擎 `runtime_candidates`，不新增第二套推演引擎；
* STATE A（不能推演）/ B（条件齐备但未落盘）/ C（可推演）/ D（已推演）在
  objective / next action / simulation 字段上必须真实不同；
* Primary UI 字段必须作者可读：没有 runtime_id / branch_id / raw score。
"""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from novelforge.story_builder.v3_projection import command_center
from test_v3_ui_projection import client_for, new_novel, save_brief, save_seed

CANDIDATE_KEYS = {
    "candidate_id", "title", "kind_label", "reason", "available", "blocked_reason",
    "requirements", "costs", "risks", "related_characters", "goal_notes", "visibility",
    "affected_locations", "affected_factions",
}


def _started(tmp_path: Path, novel_id: str) -> tuple[TestClient, str]:
    client = client_for(tmp_path)
    new_novel(client, novel_id)
    save_brief(client, novel_id)
    save_seed(client, novel_id)
    started = client.post(f"/api/story-builder/runtime/start?novel_id={novel_id}", json={})
    assert started.status_code == 200, started.text
    return client, novel_id


def test_simulation_state_a_cannot_simulate(tmp_path: Path) -> None:
    client = client_for(tmp_path)
    new_novel(client, "novel_v3_sim_a")
    payload = command_center(tmp_path, "novel_v3_sim_a")
    simulation = payload["simulation"]

    assert simulation["available"] is False
    assert simulation["reason"], "不能推演时必须说明真实原因"
    assert simulation["candidates"] == []
    assert payload["next_action"]["deep_link"]["view"] == "creation"


def test_simulation_state_b_ready_but_not_started(tmp_path: Path) -> None:
    client = client_for(tmp_path)
    novel_id = "novel_v3_sim_b"
    new_novel(client, novel_id)
    save_brief(client, novel_id)
    save_seed(client, novel_id)
    payload = command_center(tmp_path, novel_id)

    # 设定已就绪但起点事实还没落盘：仍然不能推演，但下一步必须变了。
    assert payload["simulation"]["available"] is False
    assert payload["next_action"]["deep_link"]["view"] == "simulation"
    assert payload["next_action"]["action_label"] == "开始推演"


def test_simulation_state_c_exposes_real_candidates(tmp_path: Path) -> None:
    _, novel_id = _started(tmp_path, "novel_v3_sim_c")
    simulation = command_center(tmp_path, novel_id)["simulation"]

    assert simulation["available"] is True
    assert simulation["candidates"], "已开始推演必须给出真实候选方向"
    for row in simulation["candidates"]:
        assert set(row) == CANDIDATE_KEYS
        assert row["title"]
        assert row["kind_label"]
        assert isinstance(row["available"], bool)
        # Primary UI 不能出现内部标识。
        assert "runtime_id" not in row and "branch_id" not in row and "score" not in row
    assert simulation["branches"], "至少要能看到当前路线"
    labels = [row["display_label"] for row in simulation["branches"]]
    assert all(label and label != row["branch_id"]
               for label, row in zip(labels, simulation["branches"])), \
        "路线必须使用作者可读标签，而不是 machine id"


def test_simulation_state_d_after_real_advance(tmp_path: Path) -> None:
    client, novel_id = _started(tmp_path, "novel_v3_sim_d")
    before = command_center(tmp_path, novel_id)
    candidate = next(row for row in before["simulation"]["candidates"]
                     if row["available"])

    advanced = client.post(f"/api/story-builder/runtime/advance?novel_id={novel_id}",
                           json={"action_id": candidate["candidate_id"],
                                 "branch_id": before["simulation"]["branch_id"] or "main",
                                 "expected_revision": before["simulation"]["revision"]})
    assert advanced.status_code == 200, advanced.text
    result = advanced.json()
    assert result["executed_action"] == candidate["candidate_id"]
    after = command_center(tmp_path, novel_id)

    # STATE C ≠ STATE D：真实 revision / tick 前进（候选可能合法地保持不变——
    # 如果这次行动没有改变任何前置条件，投影不允许为了"看起来在动"而伪造差异）。
    assert after["simulation"]["revision"] > before["simulation"]["revision"]
    assert after["simulation"]["tick"] > before["simulation"]["tick"]
    assert after["simulation"]["candidates"], "推演后必须重新给出下一轮候选"
    assert after["simulation"]["revision"] > 0


def test_simulation_objective_and_next_action_change_between_states(tmp_path: Path) -> None:
    client = client_for(tmp_path)
    novel_a = "novel_v3_sim_objective_a"
    new_novel(client, novel_a)
    payload_a = command_center(tmp_path, novel_a)

    _, novel_c = _started(tmp_path, "novel_v3_sim_objective_c")
    payload_c = command_center(tmp_path, novel_c)

    assert payload_a["simulation"]["available"] != payload_c["simulation"]["available"]
    assert (payload_a["next_action"]["title"], payload_a["next_action"]["action_label"]) != (
        payload_c["next_action"]["title"], payload_c["next_action"]["action_label"])
    assert payload_a["journey"]["current_stage"] != payload_c["journey"]["current_stage"]


def test_simulation_is_scoped_to_novel_id(tmp_path: Path) -> None:
    _, started = _started(tmp_path, "novel_v3_sim_scope_a")
    client = client_for(tmp_path)
    new_novel(client, "novel_v3_sim_scope_b")

    a = command_center(tmp_path, started)["simulation"]
    b = command_center(tmp_path, "novel_v3_sim_scope_b")["simulation"]

    assert a["available"] is True and a["candidates"]
    assert b["available"] is False and b["candidates"] == []
    assert b["tick"] == 0 and b["revision"] == 0
    assert {row["candidate_id"] for row in a["candidates"]} != set()


# ------------------------------------------------- V3-P3 CLOSEOUT：跨对象状态变化
def test_advance_changes_cross_object_state(tmp_path: Path) -> None:
    """一次真实推演必须改变 P2 的实体世界，而不只是让数字变大。"""

    client, novel_id = _started(tmp_path, "novel_v3_sim_cross_object")
    before = command_center(tmp_path, novel_id)
    move = next((row for row in before["simulation"]["candidates"]
                 if row["kind_label"] == "移动" and row["available"]), None)
    assert move is not None, "推演候选里必须存在可执行的移动方向"
    before_location = (before["world"]["current_location"] or {}).get("location_id", "")

    advanced = client.post(f"/api/story-builder/runtime/advance?novel_id={novel_id}",
                           json={"action_id": move["candidate_id"], "branch_id": "main",
                                 "expected_revision": before["simulation"]["revision"]})
    assert advanced.status_code == 200, advanced.text
    after = command_center(tmp_path, novel_id)
    after_location = (after["world"]["current_location"] or {}).get("location_id", "")

    # 1) 跨对象：主角所在地点真的变了（P2 Visual Entity 会看到）。
    assert after_location and after_location != before_location
    # 2) 推演状态真实前进。
    assert after["simulation"]["tick"] > before["simulation"]["tick"]
    assert after["simulation"]["revision"] > before["simulation"]["revision"]

    # 3) projection 至少一个核心维度必须变化（Objective / NextAction / 世界实体）。
    def objective_signature(payload: dict) -> list[tuple]:
        return [(row["objective_id"], row["status"], row["progress"]["done"])
                for row in payload["objectives"]]

    changed = []
    if objective_signature(after) != objective_signature(before):
        changed.append("objective")
    if after["next_action"] != before["next_action"]:
        changed.append("next_action")
    if after_location != before_location:
        changed.append("world_entity")
    if after["characters"] != before["characters"]:
        changed.append("characters")
    assert changed, "真实推演必须至少在 objective / next_action / 世界实体 / 角色上留下变化"


def test_simulation_candidates_expose_only_real_affected_entities(tmp_path: Path) -> None:
    """受影响对象只允许来自真实 entity id 匹配，不允许关键词猜测。

    自带隔离数据根（tmp_path），不依赖开发机上的历史验收数据。
    """

    _, novel_id = _started(tmp_path, "novel_v3_sim_entities")
    payload = command_center(tmp_path, novel_id)
    world = payload["world"]
    locations = {row["name"] for row in world["locations"]}
    factions = {row["name"] for row in world["factions"]}
    characters = {row["name"] for row in payload["characters"]["items"]}
    assert locations, "起点世界必须至少有一个真实地点"

    for row in payload["simulation"]["candidates"]:
        assert set(row["affected_locations"]) <= locations
        assert set(row["affected_factions"]) <= factions
        assert set(row["related_characters"]) <= characters


def test_simulation_binds_world_entities_only_by_real_id_reference(tmp_path: Path) -> None:
    """P3 CLOSEOUT：地点 / 势力影响必须是真实结构化引用的投影。

    引擎 op 行的形状并不统一（`change_location.value` / `location.value` /
    `update_location.key`），因此这里直接构造两种真实引用形状，确认：

    * 真实 id 被投影成作者可读的地点 / 势力；
    * 不存在的 id（或只是文案里出现的同名子串）不会被猜出来。
    """

    from novelforge.story_engine.settings_gen import (
        load_pack_draft,
        pack_path_for,
        saved_pack_id,
    )

    import json as _json

    client, novel_id = _started(tmp_path, "novel_v3_sim_entity_ref")
    pack_id = saved_pack_id(tmp_path, novel_id)
    pack = load_pack_draft(tmp_path, pack_id)
    assert pack is not None, "推演起点必须已经有真实内容包"

    action = next(row for row in pack.actions if row.id == "act_investigate")
    action.requirements = [
        # 真实地点引用（引擎把地点 id 放在 value）。
        {"op": "location", "entity": "", "key": "", "target": "",
         "value": "start_place", "comparator": "==", "conditions": []},
        # 真实势力引用（引擎把对象 id 放在 target）。
        {"op": "relationship", "entity": "protagonist", "target": "faction_1",
         "key": "influence", "value": 1, "comparator": ">=", "conditions": []},
        # 只是文案里出现的名字，不是真实 id：不允许被猜成受影响实体。
        {"op": "knowledge", "entity": "protagonist", "key": "", "target": "起点场所",
         "value": None, "comparator": "==", "conditions": []},
    ]
    pack_path_for(tmp_path, pack_id).write_text(
        _json.dumps(pack.model_dump(mode="json"), ensure_ascii=False, indent=2),
        encoding="utf-8")

    payload = command_center(tmp_path, novel_id)
    world = payload["world"]
    locations = {row["name"] for row in world["locations"]}
    factions = {row["name"] for row in world["factions"]}
    row = next(item for item in payload["simulation"]["candidates"]
               if item["candidate_id"] == "act_investigate")

    assert row["affected_locations"] == ["起点场所"], row["affected_locations"]
    assert row["affected_factions"] == ["既有秩序·资源控制方"], row["affected_factions"]
    assert set(row["affected_locations"]) <= locations
    assert set(row["affected_factions"]) <= factions


def test_simulation_ignores_unresolved_entity_reference(tmp_path: Path) -> None:
    """不存在的实体 id 不得出现在影响面里（宁可不绑定，也不伪造影响对象）。"""

    from novelforge.story_engine.settings_gen import (
        load_pack_draft,
        pack_path_for,
        saved_pack_id,
    )

    import json as _json

    client, novel_id = _started(tmp_path, "novel_v3_sim_entity_missing")
    pack_id = saved_pack_id(tmp_path, novel_id)
    pack = load_pack_draft(tmp_path, pack_id)
    assert pack is not None

    action = next(row for row in pack.actions if row.id == "act_investigate")
    action.requirements = [
        {"op": "location", "entity": "", "key": "", "target": "",
         "value": "phantom_place", "comparator": "==", "conditions": []},
    ]
    pack_path_for(tmp_path, pack_id).write_text(
        _json.dumps(pack.model_dump(mode="json"), ensure_ascii=False, indent=2),
        encoding="utf-8")

    payload = command_center(tmp_path, novel_id)
    row = next(item for item in payload["simulation"]["candidates"]
               if item["candidate_id"] == "act_investigate")
    assert row["affected_locations"] == []
    assert row["affected_factions"] == []


def test_simulation_candidates_speak_author_language(tmp_path: Path) -> None:
    """P3 CLOSEOUT：条件 / 代价 / 阻塞原因不能把引擎 key 抛给作者。"""

    _, novel_id = _started(tmp_path, "novel_v3_sim_author_language")
    payload = command_center(tmp_path, novel_id)
    candidates = payload["simulation"]["candidates"]
    assert candidates

    engine_keys = ("core_record", "start_place", "work_place", "hidden_place",
                   "protagonist", "npc_1", "act_", "favors", "true", "false")
    for row in candidates:
        text = " ".join([row["reason"], *row["requirements"], *row["costs"], *row["risks"]])
        for key in engine_keys:
            assert key not in text, f"{row['candidate_id']} 泄漏内部标识 {key}：{text}"
    # 真实关系维度必须翻成中文标签，而不是引擎 key。
    relation_rows = [row for row in candidates if any("需要关系" in item for item in row["requirements"])]
    if relation_rows:
        assert any("信任" in item or "亲近" in item or "亏欠" in item
                   for row in relation_rows for item in row["requirements"])
