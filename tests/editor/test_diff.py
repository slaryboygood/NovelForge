"""V4-06 §14–§16、§33、§61：结构化 diff（零模型、确定性、拒绝跨节点 / 跨作品）。"""

from __future__ import annotations

from pathlib import Path

import pytest

from novelforge.editor import EditorOwnershipError, EditorValidationError, diff_payloads

from editor_support import editor_stack


def _diff(stack: dict, node_id: str, before: int, after: int) -> dict:
    return stack["service"].diff(node_id, from_revision=before, to_revision=after)


def test_scalar_field_change(tmp_path: Path) -> None:
    stack = editor_stack(tmp_path)
    stack["service"].patch("ch_001", {"goal": "确认维修队列是否被人为改写"},
                           expected_revision=1)
    payload = _diff(stack, "ch_001", 1, 2)
    assert payload["changed_fields"] == ["goal"]
    assert payload["added_fields"] == [] and payload["removed_fields"] == []
    assert payload["before"]["goal"] == "关系进一步发展"
    assert payload["after"]["goal"] == "确认维修队列是否被人为改写"
    assert payload["digest"]
    assert "title" in payload["unchanged_fields"]
    assert payload["changed"] is True


def test_no_change_between_identical_revisions(tmp_path: Path) -> None:
    stack = editor_stack(tmp_path)
    stack["service"].accept("ch_001", expected_revision=1)   # r2：payload 相同，status 不同
    payload = _diff(stack, "ch_001", 1, 2)
    assert payload["changed"] is False
    assert payload["field_changes"] == []
    assert payload["status"] == {"before": "proposed", "after": "accepted"}


def test_list_add_remove_and_reorder(tmp_path: Path) -> None:
    stack = editor_stack(tmp_path)
    stack["service"].patch("ch_001", {"setup": ["A", "B"]}, expected_revision=1)
    payload = _diff(stack, "ch_001", 1, 2)
    change = [row for row in payload["list_changes"] if row["field"] == "setup"][0]
    assert change["added"] == ["A", "B"] and change["removed"] == []
    assert change["reordered"] is False

    stack["service"].patch("ch_001", {"setup": ["B", "A"]}, expected_revision=2)
    reordered = _diff(stack, "ch_001", 2, 3)
    change = [row for row in reordered["list_changes"] if row["field"] == "setup"][0]
    assert change["reordered"] is True
    assert change["added"] == [] and change["removed"] == []

    stack["service"].patch("ch_001", {"setup": ["A"]}, expected_revision=3)
    removed = _diff(stack, "ch_001", 3, 4)
    change = [row for row in removed["list_changes"] if row["field"] == "setup"][0]
    assert change["removed"] == ["B"] and change["added"] == []


def test_nested_state_transition_change(tmp_path: Path) -> None:
    stack = editor_stack(tmp_path)
    stack["service"].patch("ch_001", {"state_change_intent": [
        {"kind": "knowledge", "actor": "char_001", "target": "core_record",
         "value": "known", "scope": "novel"},
        {"kind": "relationship", "actor": "char_001", "target": "char_002",
         "value": "distrust", "scope": "novel"}]}, expected_revision=1)
    payload = _diff(stack, "ch_001", 1, 2)
    assert payload["changed_fields"] == ["state_change_intent"]
    change = payload["list_changes"][0]
    assert change["field"] == "state_change_intent"
    assert len(change["added"]) == 1 and change["removed"] == []
    assert change["before"][0]["kind"] == "knowledge"
    assert change["after"][1]["kind"] == "relationship"
    assert payload["field_changes"][0]["kind"] == "changed"


def test_cross_node_and_cross_novel_are_rejected(tmp_path: Path) -> None:
    stack = editor_stack(tmp_path)
    with pytest.raises(EditorValidationError) as exc:
        stack["editor"].compare("ch_001", 1, "sc_001_02", 1)
    assert "跨节点" in exc.value.message
    with pytest.raises(EditorOwnershipError):
        stack["editor"]._assert_novel("novel_beta")  # noqa: SLF001 - 归属守卫


def test_diff_request_cross_novel_is_refused(tmp_path: Path) -> None:
    from novelforge.editor import DiffRequest

    stack = editor_stack(tmp_path)
    with pytest.raises(EditorOwnershipError):
        stack["editor"].diff(DiffRequest(novel_id="novel_beta", node_id="ch_001",
                                         from_revision=1))


def test_diff_is_deterministic_and_model_free() -> None:
    """§15 / §16：哪些字段变了必须由确定性算法决定。"""

    before = {"a": 1, "b": ["x"], "c": {"k": 1}}
    after = {"a": 2, "b": ["x", "y"], "c": {"k": 2}}
    first = diff_payloads(node_id="n", novel_id="novel", before=before, after=after,
                          revision_before=1, revision_after=2)
    second = diff_payloads(node_id="n", novel_id="novel", before=before, after=after,
                           revision_before=1, revision_after=2)
    assert first.digest == second.digest
    assert first.changed_fields == ("a", "b", "c")
    assert "c.k" in first.field_changes[2].nested
    import inspect

    from novelforge.editor import diff as diff_module

    source = inspect.getsource(diff_module)
    assert "novelforge.ai" not in source and "gateway" not in source


def test_diff_with_quality_association(tmp_path: Path) -> None:
    """§33：diff 可以关联 before/after issue 集合（来源是 Quality Store）。"""

    stack = editor_stack(tmp_path)
    stack["quality"].evaluate(gates=("Q7",))
    stack["service"].patch("sc_001_02", {"story_function": ["advance_plot", "decision"]},
                           expected_revision=1)
    payload = _diff(stack, "sc_001_02", 1, 2)
    assert payload["quality"]["source"] == "quality store"
    assert payload["quality"]["before_issue_ids"]
