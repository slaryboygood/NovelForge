"""V3-P2 角色 / 世界实体投影回归。

这些用例守卫 P2 的三条硬规则：

* 实体来自既有 Domain（StoryState / 内容包），不建立第二套角色或世界模型；
* 只输出作者可读字段，内部 id 只作主键，不出现 provenance / raw state；
* 没有真实数据时是明确空结果，而不是伪造实体或假进度。
"""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from novelforge.story_builder.v3_projection import characters_view, world_view
from novelforge.story_builder.v3_projection import (
    command_center,
    relationship_edges,
    relationships_view,
)
from novelforge.story_engine.settings_gen import (
    load_pack_draft,
    saved_pack_id,
    write_content_pack,
)
from test_v3_ui_projection import client_for, new_novel, save_brief, save_seed

CHARACTER_KEYS = {
    "character_id", "name", "role_label", "kind", "is_protagonist", "status_label",
    "tags", "active_goals", "memories", "relationship_count", "has_relationships",
    "key_relationships",
    # NF-016：原型占位名必须显式标记，作者才知道它还不是姓名。
    "name_placeholder",
}
LOCATION_KEYS = {
    "location_id", "name", "kind_label", "access_label", "control_label", "danger",
    "current", "visited", "name_placeholder",
}
FACTION_KEYS = {
    "faction_id", "name", "stance_label", "influence", "active_plot_count",
    "conflict_count", "name_placeholder",
}


def started_novel(tmp_path: Path, novel_id: str = "novel_v3_entities"
                  ) -> tuple[TestClient, str]:
    """走真实引导路径到「已开始推演」，让角色 / 世界有真实已发生事实。"""

    client = client_for(tmp_path)
    new_novel(client, novel_id)
    save_brief(client, novel_id)
    save_seed(client, novel_id)
    started = client.post(f"/api/story-builder/runtime/start?novel_id={novel_id}",
                          json={})
    assert started.status_code == 200, started.text
    return client, novel_id


def test_character_projection_is_author_readable(tmp_path: Path) -> None:
    client, novel_id = started_novel(tmp_path)
    view = characters_view(tmp_path, novel_id)

    assert view["available"] is True
    assert view["count"] == len(view["items"]) > 0
    for row in view["items"]:
        assert set(row) == CHARACTER_KEYS
        assert row["name"]
        assert row["role_label"] in {"主角", "核心伙伴", "配角", "对手", "伙伴", "角色"}
        # 不泄漏内部结构。
        assert "data" not in row and "memories_detail" not in row
    protagonist = view["protagonist"]
    assert protagonist is not None and protagonist["is_protagonist"] is True
    # 主角必须在列表最前（Stage/Workspace 的首屏顺序稳定）。
    assert view["items"][0]["character_id"] == protagonist["character_id"]
    assert client.get(f"/api/story-builder/v3/novels/{novel_id}/command-center"
                      ).status_code == 200


def test_character_projection_is_empty_without_runtime(tmp_path: Path) -> None:
    client = client_for(tmp_path)
    new_novel(client, "novel_v3_entities_empty")
    view = characters_view(tmp_path, "novel_v3_entities_empty")

    assert view["count"] == 0
    assert view["items"] == []
    assert view["protagonist"] is None


def test_world_projection_uses_real_locations_and_factions(tmp_path: Path) -> None:
    client, novel_id = started_novel(tmp_path, "novel_v3_world")
    view = world_view(tmp_path, novel_id)

    assert view["available"] is True
    assert view["location_count"] == len(view["locations"]) > 0
    assert view["faction_count"] == len(view["factions"]) > 0
    for row in view["locations"]:
        assert set(row) == LOCATION_KEYS
        assert row["name"]
        assert row["kind_label"]
    for row in view["factions"]:
        assert set(row) == FACTION_KEYS
        assert row["name"]
    assert view["current_location"] is not None
    assert view["current_location"]["name"]


def test_world_projection_is_empty_without_runtime(tmp_path: Path) -> None:
    client = client_for(tmp_path)
    new_novel(client, "novel_v3_world_empty")
    view = world_view(tmp_path, "novel_v3_world_empty")

    assert view["locations"] == []
    assert view["factions"] == []
    assert view["current_location"] is None
    assert view["location_count"] == 0 and view["faction_count"] == 0


def test_entity_projection_is_scoped_to_novel_id(tmp_path: Path) -> None:
    _, started = started_novel(tmp_path, "novel_v3_entity_scope_a")
    client = client_for(tmp_path)
    new_novel(client, "novel_v3_entity_scope_b")

    a = characters_view(tmp_path, started)
    b = characters_view(tmp_path, "novel_v3_entity_scope_b")

    assert a["count"] > 0
    assert b["count"] == 0
    assert not ({row["character_id"] for row in a["items"]}
                & {row["character_id"] for row in b["items"]})


# ------------------------------------------- V3-P2 CLOSEOUT：关系投影与状态变化
def test_relationship_projection_uses_real_sources(tmp_path: Path) -> None:
    """关系来自 StoryState（已发生）与内容包（设计中），不是 UI 推导。"""

    _, novel_id = started_novel(tmp_path, "novel_v3_relations")
    view = relationships_view(tmp_path, novel_id)
    edges = relationship_edges(tmp_path, novel_id)

    assert view["available"] is True
    assert view["edge_count"] == len(edges) > 0
    assert view["occurred_count"] > 0
    for row in edges:
        assert row["source_id"] and row["target_id"]
        assert row["source_label"] and row["target_label"]
        assert row["truth_label"] in {"已发生", "设计中"}
        # 维度是 Domain 真实值，只做标签翻译，不做阈值换算。
        assert all(set(item) == {"label", "value"} for item in row["dimension_rows"])

    characters = characters_view(tmp_path, novel_id, edges)
    protagonist = characters["protagonist"]
    assert protagonist is not None
    assert protagonist["has_relationships"] is True
    assert protagonist["relationship_count"] > 0
    assert 0 < len(protagonist["key_relationships"]) <= 3


def test_character_relationship_objective_changes_with_real_state(tmp_path: Path) -> None:
    """STATE A（角色存在但没有关系）≠ STATE B（存在真实关系）。"""

    client, novel_id = started_novel(tmp_path, "novel_v3_relation_state")
    pack_id = saved_pack_id(tmp_path, novel_id)
    pack = load_pack_draft(tmp_path, pack_id)
    assert pack is not None

    # STATE A：真实领域状态 = 有角色、没有关系（通过既有 pack 写入口构造）。
    without = pack.model_copy(update={"initial_relationships": []})
    write_content_pack(tmp_path, without)
    state_a = command_center(tmp_path, novel_id)
    objective_a = next(row for row in state_a["objectives"]
                       if row["objective_id"] == "obj_relationships")

    # STATE B：恢复真实关系。
    write_content_pack(tmp_path, pack)
    state_b = command_center(tmp_path, novel_id)
    objective_b = next(row for row in state_b["objectives"]
                       if row["objective_id"] == "obj_relationships")

    assert objective_a["status"] != "complete"
    assert objective_b["status"] == "complete"
    # 至少一个核心维度发生真实变化：objective 状态 + 关联 checklist 完成度。
    assert (objective_a["status"], objective_a["progress"]["done"]) != (
        objective_b["status"], objective_b["progress"]["done"])
    assert state_a["facts"]["content_pack_ready"] is True


def test_world_objective_changes_with_real_state(tmp_path: Path) -> None:
    """世界目标必须由真实状态驱动：没有内容包 vs 有内容包。"""

    client = client_for(tmp_path)
    novel_id = "novel_v3_world_state"
    new_novel(client, novel_id)

    empty_state = command_center(tmp_path, novel_id)
    empty_world = [row for row in empty_state["objectives"]
                   if row["stage_id"] == "world"]
    assert empty_world, "世界阶段必须有自己的 objective"

    save_brief(client, novel_id)
    save_seed(client, novel_id)
    ready_state = command_center(tmp_path, novel_id)
    ready_world = [row for row in ready_state["objectives"]
                   if row["stage_id"] == "world"]

    empty_signature = [(row["objective_id"], row["status"], row["progress"]["done"])
                       for row in empty_world]
    ready_signature = [(row["objective_id"], row["status"], row["progress"]["done"])
                       for row in ready_world]
    assert empty_signature != ready_signature, "世界 objective 不允许是写死的固定文案/状态"
    assert all(row["status"] == "complete" for row in ready_world)
    assert empty_state["next_action"]["deep_link"]["view"] != "outline"
    assert ready_state["journey"]["current_stage"] != empty_state["journey"]["current_stage"]
