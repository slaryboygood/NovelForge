"""V4-06 §25–§26、§60、§63：restore / undo（用旧内容创建新 revision）。"""

from __future__ import annotations

from pathlib import Path

import pytest

from novelforge.editor import EditorOperationRejected, EditorPreserveViolation

from editor_support import editor_stack, revision


def _three_revisions(tmp_path: Path) -> dict:
    stack = editor_stack(tmp_path)
    service = stack["service"]
    service.patch("ch_001", {"title": "标题二"}, expected_revision=1)
    service.patch("ch_001", {"title": "标题三"}, expected_revision=2)
    return stack


def test_restore_creates_new_revision_and_keeps_history(tmp_path: Path) -> None:
    stack = _three_revisions(tmp_path)
    service = stack["service"]
    result = service.restore("ch_001", from_revision=1, expected_revision=3,
                             reason="回到原始目标")
    assert result["status"] == "applied"
    assert result["restored_from"] == 1 and result["revision"] == 4
    assert result["changed_fields"] == ["title"]
    # r1 / r2 / r3 全部仍可读，且 r4 内容 == r1 可恢复字段（§60）
    assert stack["repository"].list_revisions("ch_001") == [1, 2, 3, 4]
    first = stack["repository"].get_revision("ch_001", 1).payload
    fourth = stack["repository"].get_revision("ch_001", 4).payload
    assert fourth.model_dump(mode="json") == first.model_dump(mode="json")
    node = stack["repository"].get_current("ch_001")
    assert node.provenance["restored_from"] == 1
    assert node.provenance["operation"] == "restore"
    assert node.status == "proposed" and node.quality_status == "unevaluated"


def test_restore_does_not_move_the_current_pointer_backwards(tmp_path: Path) -> None:
    stack = _three_revisions(tmp_path)
    stack["service"].restore("ch_001", from_revision=1, expected_revision=3)
    assert stack["repository"].current_revision("ch_001") == 4
    history = stack["service"].get_history("ch_001")
    assert history["revisions"][-1]["revision"] == 4
    assert history["revisions"][-1]["restored_from"] == 1


def test_undo_restores_previous_revision(tmp_path: Path) -> None:
    stack = _three_revisions(tmp_path)
    result = stack["service"].undo("ch_001", expected_revision=3)
    assert result["operation"] == "undo" and result["restored_from"] == 2
    assert stack["repository"].get_current("ch_001").payload.title == "标题二"
    assert stack["repository"].current_revision("ch_001") == 4


def test_undo_without_parent_is_rejected(tmp_path: Path) -> None:
    stack = editor_stack(tmp_path)
    with pytest.raises(EditorOperationRejected) as exc:
        stack["service"].undo("ch_001", expected_revision=1)
    assert exc.value.details["code"] == "EDITOR_UNDO_UNAVAILABLE"
    assert revision(stack, "ch_001") == 1


def test_restore_of_current_revision_is_rejected(tmp_path: Path) -> None:
    stack = editor_stack(tmp_path)
    with pytest.raises(EditorOperationRejected) as exc:
        stack["service"].restore("ch_001", from_revision=1, expected_revision=1)
    assert exc.value.details["code"] == "EDITOR_RESTORE_NOOP"


def test_restore_obeys_structural_identity(tmp_path: Path) -> None:
    """§63：restore 只恢复内容字段；结构性 payload 字段不一致时拒绝。"""

    stack = editor_stack(tmp_path)
    service = stack["service"]
    # 通过 move_node 把场景移到另一章（合法路径），再尝试 restore 旧 revision
    stack["repository"].save_revision(
        __import__("novelforge.blueprint", fromlist=["BlueprintNode"]).BlueprintNode(
            node_id="ch_002", novel_id="novel_alpha", node_type="chapter",
            payload=__import__("novelforge.blueprint",
                               fromlist=["ChapterCardPayload"]).ChapterCardPayload(
                title="第二章", characters=["char_001"]),
            parent_id="unit_01", sequence=2),
        expected_revision=None)
    move = stack["editor"].move(
        __import__("novelforge.editor", fromlist=["MoveNodeRequest"]).MoveNodeRequest(
            novel_id="novel_alpha", node_id="sc_001_02", expected_revision=1,
            parent_id="ch_002"))
    assert move.status == "applied"
    # move 会同步结构 identity 字段（场景的 chapter_id 跟随 parent_id）
    assert stack["repository"].get_current("sc_001_02").payload.chapter_id == "ch_002"
    with pytest.raises(EditorPreserveViolation) as exc:
        service.restore("sc_001_02", from_revision=1, expected_revision=2)
    assert exc.value.details["changed_fields"] == ["chapter_id"]


def test_restore_conflict_is_reported(tmp_path: Path) -> None:
    from novelforge.editor import EditorConflictError

    stack = _three_revisions(tmp_path)
    with pytest.raises(EditorConflictError) as exc:
        stack["service"].restore("ch_001", from_revision=1, expected_revision=1)
    assert exc.value.details["expected_revision"] == 1
    assert exc.value.details["actual_revision"] == 3
    assert revision(stack, "ch_001") == 3
