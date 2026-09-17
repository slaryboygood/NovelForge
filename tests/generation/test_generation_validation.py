"""生成结果校验：schema / 引用 / ownership（V4-04 §33–§34、§47）。"""

from __future__ import annotations

from pathlib import Path

import pytest

from novelforge.blueprint import validate_graph, validate_node
from novelforge.generation import GenerationUnavailableError
from gen_support import (
    blueprint_service,
    build_novel,
    build_two_novels,
    chapter_payload,
    character_arc_payload,
    character_payload,
    premise_payload,
    scene_payload,
    story_arc_payload,
    unit_payload,
)


def test_invalid_payload_is_rejected_before_save(tmp_path: Path) -> None:
    build_novel(tmp_path, "novel_alpha", title="A", fact_text="规则")
    service, _provider = blueprint_service(tmp_path, "novel_alpha", [
        {"premise": "", "central_conflict": "x"}])  # premise 为空 → schema 拒绝
    with pytest.raises(GenerationUnavailableError):
        service.generate_task("premise")
    assert service.tree()["node_count"] == 0, "校验失败的节点不得落盘"


def test_unknown_character_reference_is_rejected(tmp_path: Path) -> None:
    build_novel(tmp_path, "novel_alpha", title="A", fact_text="规则")
    service, _provider = blueprint_service(tmp_path, "novel_alpha", [
        premise_payload(), story_arc_payload(), unit_payload("act"),
        chapter_payload(characters=["not_a_real_character"])])
    service.generate_task("premise")
    service.generate_task("story_arc")
    unit = service.generate_task("structural_unit",
                                 task_input={"index": 1, "unit_type": "act", "total": 1})
    with pytest.raises(Exception) as exc:
        service.generate_task("chapter", parent_id=unit.node["node_id"],
                              task_input={"index": 1, "total": 1})
    codes = [row["code"] for row in getattr(exc.value, "issues", [])]
    assert "CHARACTER_NOT_FOUND" in codes


def test_scene_requires_existing_chapter(tmp_path: Path) -> None:
    build_novel(tmp_path, "novel_alpha", title="A", fact_text="规则")
    service, _provider = blueprint_service(tmp_path, "novel_alpha", [
        premise_payload(), story_arc_payload(), unit_payload("act"),
        chapter_payload(), scene_payload("system-assigned")])
    service.generate_task("premise")
    service.generate_task("story_arc")
    unit = service.generate_task("structural_unit",
                                 task_input={"index": 1, "unit_type": "act", "total": 1})
    service.generate_task("chapter", parent_id=unit.node["node_id"],
                          task_input={"index": 1, "total": 1})
    scene = service.generate_task("scene", parent_id="ch_001",
                                  task_input={"sequence": 1, "total": 1,
                                              "chapter_index": 1})
    assert scene.node["payload"]["chapter_id"] == "ch_001"


def test_task_requiring_parent_fails_without_parent(tmp_path: Path) -> None:
    build_novel(tmp_path, "novel_alpha", title="A", fact_text="规则")
    service, _provider = blueprint_service(tmp_path, "novel_alpha",
                                           [character_arc_payload("x")])
    with pytest.raises(Exception) as exc:
        service.generate_task("character_arc", task_input={})
    assert "父节点" in str(exc.value)


def test_cross_novel_nodes_are_rejected_by_validation(tmp_path: Path) -> None:
    build_two_novels(tmp_path)
    alpha, _provider = blueprint_service(tmp_path, "novel_alpha", [premise_payload()])
    alpha.generate_task("premise")
    beta, _provider2 = blueprint_service(tmp_path, "novel_beta", [premise_payload()])
    beta.generate_task("premise")
    report = validate_graph(beta.repository.all_nodes(), novel_id="novel_alpha")
    assert report["ok"] is False
    assert any(row["code"] == "OWNERSHIP_MISMATCH" for row in report["issues"])
    assert beta.repository.get_current("premise").novel_id == "novel_beta"


def test_validate_node_reports_parent_type_mismatch(tmp_path: Path) -> None:
    build_novel(tmp_path, "novel_alpha", title="A", fact_text="规则")
    service, _provider = blueprint_service(tmp_path, "novel_alpha", [
        premise_payload(), chapter_payload()])
    premise = service.generate_task("premise")
    # chapter 的父节点类型不允许是 premise
    chapter = service.generate(service.generation.registry.get("chapter"),
                               ) if False else None
    from novelforge.blueprint import BlueprintNode, ChapterCardPayload

    node = BlueprintNode(node_id="ch_001", novel_id="novel_alpha", node_type="chapter",
                         parent_id=premise.node["node_id"],
                         payload=ChapterCardPayload(**chapter_payload()), sequence=1)
    issues = validate_node(node, parent=service.generation.repository.get_current(
        premise.node["node_id"]), known={premise.node["node_id"]: None})
    assert any(row["code"] == "PARENT_TYPE_INVALID" for row in issues)
