"""V4-05 §12：Q0 Schema —— ADAPT `blueprint.validate_node`，不复制规则。"""

from __future__ import annotations

from pathlib import Path

from novelforge.blueprint import (
    ChapterCardPayload,
    PremisePayload,
    StoryArcPayload,
    StructuralUnitPayload,
)

from quality_support import NOVEL_ID, codes, isolated_gate, node, scene


def test_valid_nodes_produce_no_schema_issue(tmp_path: Path) -> None:
    issues, _quality = isolated_gate(
        tmp_path,
        [node(NOVEL_ID, "premise", "premise", PremisePayload(premise="前提")),
         node(NOVEL_ID, "story_arc", "story_arc", StoryArcPayload(),
              parent_id="premise", sequence=1),
         node(NOVEL_ID, "unit_01", "structural_unit",
              StructuralUnitPayload(unit_type="act", title="第一幕"),
              parent_id="story_arc", sequence=1),
         node(NOVEL_ID, "ch_001", "chapter",
              ChapterCardPayload(title="被删除的维修日志"),
              parent_id="unit_01", sequence=1),
         scene("sc_001_01", parent="ch_001", sequence=1)],
        "Q0", with_novel=False)
    assert codes(issues) == []


def test_missing_parent_and_reference_are_reported(tmp_path: Path) -> None:
    issues, _quality = isolated_gate(
        tmp_path,
        [scene("sc_001_01", parent="ch_missing"),
         node(NOVEL_ID, "ch_002", "chapter",
              ChapterCardPayload(title="孤儿章节", characters=["char_missing"]),
              parent_id="unit_missing", sequence=1)],
        "Q0", with_novel=False)
    reported = codes(issues)
    assert "REFERENCE_BROKEN" in reported
    assert "PARENT_TYPE_INVALID" not in reported  # 父不存在 ≠ 父类型错误
    assert any(issue.severity == "blocker" for issue in issues)


def test_parent_type_mismatch_is_reported(tmp_path: Path) -> None:
    issues, _quality = isolated_gate(
        tmp_path,
        [node(NOVEL_ID, "premise", "premise", PremisePayload(premise="前提")),
         node(NOVEL_ID, "ch_001", "chapter",
              ChapterCardPayload(title="错层级章节"),
              parent_id="premise", sequence=1)],
        "Q0", with_novel=False)
    assert "PARENT_TYPE_INVALID" in codes(issues)


def test_duplicate_sequence_under_same_parent(tmp_path: Path) -> None:
    issues, _quality = isolated_gate(
        tmp_path,
        [node(NOVEL_ID, "story_arc", "story_arc", StoryArcPayload(),
              sequence=0),
         node(NOVEL_ID, "unit_01", "structural_unit",
              StructuralUnitPayload(unit_type="act", title="第一幕"),
              parent_id="story_arc", sequence=1),
         node(NOVEL_ID, "unit_02", "structural_unit",
              StructuralUnitPayload(unit_type="act", title="第二幕"),
              parent_id="story_arc", sequence=1)],
        "Q0", with_novel=False)
    assert "SEQUENCE_INVALID" in codes(issues)


def test_schema_gate_does_not_own_q1_codes() -> None:
    """ownership / provenance 属于 Q1：Q0 映射表不得包含它们（避免重复 issue）。"""

    from novelforge.quality.evaluators.schema_gate import CODE_MAP

    mapped = set(CODE_MAP.values())
    assert "OWNERSHIP_MISMATCH" not in mapped
    assert "PROVENANCE_INVALID" not in mapped
