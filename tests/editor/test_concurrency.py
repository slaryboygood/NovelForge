"""V4-06 §43–§45、§62：乐观并发（expected_revision）不得静默覆盖。"""

from __future__ import annotations

from pathlib import Path

import pytest

from novelforge.editor import EditorConflictError

from editor_support import current_payload, editor_stack, revision, scripted


def test_stale_save_is_rejected_without_new_revision(tmp_path: Path) -> None:
    stack = editor_stack(tmp_path)
    service = stack["service"]
    base = revision(stack, "ch_001")                    # 作者打开 r1
    service.patch("ch_001", {"goal": "Agent 改的目标"},
                  expected_revision=base)               # 别人先提交 r2
    with pytest.raises(EditorConflictError) as exc:
        service.patch("ch_001", {"goal": "作者基于 r1 的修改"},
                      expected_revision=base)
    details = exc.value.details
    assert details["expected_revision"] == 1 and details["actual_revision"] == 2
    assert details["node_id"] == "ch_001"
    assert "conflict_diff" in details                  # §44：可提供 current vs base
    assert revision(stack, "ch_001") == 2              # 没有 r3
    assert stack["repository"].get_current("ch_001").payload.goal == "Agent 改的目标"


def test_conflict_diff_shows_what_changed_elsewhere(tmp_path: Path) -> None:
    stack = editor_stack(tmp_path)
    service = stack["service"]
    service.patch("ch_001", {"title": "别人改的标题"}, expected_revision=1)
    with pytest.raises(EditorConflictError) as exc:
        service.patch("ch_001", {"goal": "作者改的目标"}, expected_revision=1)
    conflict_diff = exc.value.details["conflict_diff"]
    assert conflict_diff["changed_fields"] == ["title"]
    assert conflict_diff["revision_before"] == 1
    assert conflict_diff["revision_after"] == 2


def test_no_auto_merge_of_creative_fields(tmp_path: Path) -> None:
    """§45：禁止自动语义 merge —— 冲突就是冲突。"""

    stack = editor_stack(tmp_path)
    service = stack["service"]
    service.patch("ch_001", {"conflict": "别人写的冲突"}, expected_revision=1)
    with pytest.raises(EditorConflictError):
        service.patch("ch_001", {"conflict": "作者写的冲突"}, expected_revision=1)
    assert stack["repository"].get_current("ch_001").payload.conflict == "别人写的冲突"


def test_rewrite_conflict_before_model_call(tmp_path: Path) -> None:
    stack = editor_stack(tmp_path)
    payload = current_payload(stack, "ch_001")
    scripted(stack, {**payload, "turn": "新的转折"})
    stack["service"].patch("ch_001", {"goal": "先改一次"}, expected_revision=1)
    with pytest.raises(EditorConflictError):
        stack["service"].rewrite("ch_001", ["turn"], "改写", expected_revision=1)
    assert stack["provider"].calls == 0


def test_batch_conflict_reports_partial_explicitly(tmp_path: Path) -> None:
    """§38：一半成功必须显式说明（append-only revision 无法回滚已提交部分）。"""

    stack = editor_stack(tmp_path)
    stack["repository"].save_revision(
        stack["repository"].get_current("ch_001"), expected_revision=1)   # r2
    result = stack["service"].patch_batch([
        {"node_id": "ch_001", "expected_revision": 1,
         "changes": {"goal": "基于旧版本的修改"}},
    ])
    assert result["status"] == "partial"
    assert result["conflict_node_ids"] == ["ch_001"]
    assert result["applied_node_ids"] == []
    assert any("无法回滚" in note for note in result["notes"])
    assert revision(stack, "ch_001") == 2


def test_concurrent_nodes_do_not_interfere(tmp_path: Path) -> None:
    stack = editor_stack(tmp_path)
    a = stack["service"].patch("ch_001", {"goal": "目标 A"}, expected_revision=1)
    b = stack["service"].patch("sc_001_02", {"story_function": ["advance_plot"]},
                               expected_revision=1)
    assert a["revision"] == 2 and b["revision"] == 2
    assert stack["repository"].current_revision("ch_001") == 2
    assert stack["repository"].current_revision("sc_001_02") == 2
