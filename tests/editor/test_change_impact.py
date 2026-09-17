"""V4-06 §71–§73、§74：ChangeImpact（依赖感知，只报告不自动改）。"""

from __future__ import annotations

from pathlib import Path

from editor_support import editor_stack, revision


def test_scene_change_affects_chapter_and_sibling_scenes(tmp_path: Path) -> None:
    stack = editor_stack(tmp_path)
    impact = stack["service"].change_impact("sc_001_03", ["turn"])
    assert impact["node_id"] == "sc_001_03"
    assert impact["changed_fields"] == ["turn"]
    assert set(impact["dependent_nodes"]) >= {"ch_001", "sc_001_01", "sc_001_02",
                                              "sc_001_04", "setup_001"}
    assert "same_chapter_scene" in impact["reasons"]["sc_001_02"]
    assert "child_of_changed_node" in impact["reasons"]["setup_001"]
    assert "scene_changed_under_chapter" in impact["reasons"]["ch_001"]
    assert impact["auto_modified"] is False


def test_chapter_change_affects_its_scenes(tmp_path: Path) -> None:
    stack = editor_stack(tmp_path)
    impact = stack["service"].change_impact("ch_001", ["goal"])
    assert set(impact["dependent_nodes"]) >= {"sc_001_01", "sc_001_02", "sc_001_03",
                                              "sc_001_04"}
    assert "child_of_changed_node" in impact["reasons"]["sc_001_01"]


def test_patch_reports_impact_and_quality_invalidation(tmp_path: Path) -> None:
    stack = editor_stack(tmp_path)
    result = stack["service"].patch("ch_001", {"goal": "确认维修队列是否被人为改写"},
                                   expected_revision=1)
    impact = result["impact"]
    assert set(impact["quality_invalidations"]) >= {"ch_001", "sc_001_01"}
    assert result["quality"]["quality_status"] == "unevaluated"
    assert impact["summary"].startswith("改了 1 个字段")


def test_impact_is_computed_without_modifying_other_nodes(tmp_path: Path) -> None:
    stack = editor_stack(tmp_path)
    before = {node.node_id: node.as_dict()
              for node in stack["repository"].all_nodes()}
    stack["service"].change_impact("ch_001", ["goal"])
    after = {node.node_id: node.as_dict()
             for node in stack["repository"].all_nodes()}
    assert before == after
    assert revision(stack, "ch_001") == 1


def test_impact_after_patch_lists_dependent_nodes(tmp_path: Path) -> None:
    stack = editor_stack(tmp_path)
    stack["service"].patch("sc_001_03", {"turn": "新的转折"}, expected_revision=1)
    impact = stack["service"].change_impact("sc_001_03", ["turn"])
    assert "setup_001" in impact["dependent_nodes"]
    assert "cl_002" in impact["dependent_nodes"]


def test_impact_for_character_touches_arc_and_scenes(tmp_path: Path) -> None:
    stack = editor_stack(tmp_path)
    impact = stack["service"].change_impact("char_001", ["goal"])
    assert "arc_001" in impact["dependent_nodes"]     # character_arc 是子节点
    assert set(impact["quality_invalidations"]) >= {"char_001", "arc_001"}
