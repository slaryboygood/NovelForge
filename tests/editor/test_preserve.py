"""V4-06 §20、§63：preserve / 结构 identity 是硬约束（patch / rewrite / repair / restore）。"""

from __future__ import annotations

from pathlib import Path

import pytest

from novelforge.editor import EditorPreserveViolation

from editor_support import current_payload, editor_stack, revision, scripted


def test_manual_patch_cannot_alter_structural_identity(tmp_path: Path) -> None:
    stack = editor_stack(tmp_path)
    with pytest.raises(EditorPreserveViolation) as exc:
        stack["service"].patch("sc_001_02", {"chapter_id": "ch_002"},
                               expected_revision=1)
    assert exc.value.details["structural_fields"] == ["chapter_id"]
    assert "move_node" in exc.value.details["hint"]
    assert revision(stack, "sc_001_02") == 1


def test_ai_rewrite_cannot_alter_preserve_field(tmp_path: Path) -> None:
    stack = editor_stack(tmp_path)
    payload = current_payload(stack, "sc_001_02")
    scripted(stack, {**payload, "conflict": "新的冲突", "chapter_id": "ch_002"})
    with pytest.raises(EditorPreserveViolation) as exc:
        stack["service"].rewrite("sc_001_02", ["conflict"], "加强冲突",
                                 expected_revision=1, preserve_fields=["chapter_id"])
    assert exc.value.details["violating_fields"] == ["chapter_id"]
    assert revision(stack, "sc_001_02") == 1


def test_quality_repair_cannot_alter_preserve_field(tmp_path: Path) -> None:
    """V4-05 repair 的 preserve 语义在 V4-06 继续生效（同一 SSOT）。"""

    from novelforge.blueprint import STRUCTURAL_IDENTITY_FIELDS
    from novelforge.quality.repair.planner import STRUCTURAL_PRESERVE

    assert STRUCTURAL_PRESERVE is STRUCTURAL_IDENTITY_FIELDS
    stack = editor_stack(tmp_path)
    stack["service"].evaluate("sc_001_02")
    plan = stack["service"].plan_repair(node_id="sc_001_02")
    assert plan is not None and plan["steps"]
    step = [row for row in plan["steps"] if row["node_id"] == "sc_001_02"][0]
    assert "chapter_id" in step["preserve"]
    assert set(step["allow_change"]) & set(step["preserve"]) == set()


def test_restore_obeys_structural_identity_rules(tmp_path: Path) -> None:
    stack = editor_stack(tmp_path)
    stack["service"].patch("ch_001", {"title": "改标题"}, expected_revision=1)
    result = stack["service"].restore("ch_001", from_revision=1, expected_revision=2)
    assert result["status"] == "applied"
    node = stack["repository"].get_current("ch_001")
    assert node.node_id == "ch_001" and node.novel_id == "novel_alpha"
    assert node.parent_id == "unit_01" and node.sequence == 1
    assert node.payload.characters == ["char_001"]     # 结构 identity 保持


def test_protected_metadata_cannot_be_patched_through_batch(tmp_path: Path) -> None:
    stack = editor_stack(tmp_path)
    result = stack["service"].patch_batch([
        {"node_id": "ch_001", "expected_revision": 1,
         "changes": {"goal": "新目标"}},
        {"node_id": "sc_001_02", "expected_revision": 1,
         "changes": {"parent_id": "ch_002"}},
    ])
    assert result["status"] == "rejected"
    assert result["applied_node_ids"] == []
    assert result["rejected_node_ids"] == ["sc_001_02"]
    assert revision(stack, "ch_001") == 1        # all_or_rollback：一个都没写
