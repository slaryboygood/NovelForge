"""V4-06 §22–§24、§68–§70：accept / reject 语义与「质量通过 ≠ 作者接受」。"""

from __future__ import annotations

from pathlib import Path

import pytest

from novelforge.editor import EditorOperationRejected

from editor_support import editor_stack, revision


def test_accept_appends_revision_and_marks_review(tmp_path: Path) -> None:
    stack = editor_stack(tmp_path)
    result = stack["service"].accept("ch_001", expected_revision=1, reason="接受")
    assert result["decision"] == "accepted" and result["status"] == "applied"
    assert result["reviewed_revision"] == 1 and result["revision"] == 2
    assert result["previous_status"] == "proposed"
    node = stack["repository"].get_current("ch_001")
    assert node.status == "accepted"
    # payload 完全不变（状态流转不产生内容变化）
    before = stack["repository"].get_revision("ch_001", 1).payload.model_dump(mode="json")
    assert node.payload.model_dump(mode="json") == before
    assert stack["store"].review_for("ch_001", 1)["decision"] == "accepted"


def test_accept_is_idempotent_when_already_accepted(tmp_path: Path) -> None:
    stack = editor_stack(tmp_path)
    stack["service"].accept("ch_001", expected_revision=1)
    again = stack["service"].accept("ch_001", expected_revision=2)
    assert again["status"] == "recorded" and again["idempotent"] is True
    assert again["revision"] == 2
    assert revision(stack, "ch_001") == 2


def test_accept_rejects_invalid_status_transition(tmp_path: Path) -> None:
    stack = editor_stack(tmp_path)
    stack["repository"].set_status("ch_001", "draft", expected_revision=1)
    stack["repository"].set_status("ch_001", "accepted", expected_revision=2)
    stack["repository"].set_status("ch_001", "superseded", expected_revision=3)
    with pytest.raises(EditorOperationRejected) as exc:
        stack["service"].accept("ch_001", expected_revision=4)
    assert exc.value.details["code"] == "EDITOR_STATUS_TRANSITION_INVALID"


def test_reject_records_decision_without_touching_revision(tmp_path: Path) -> None:
    stack = editor_stack(tmp_path)
    result = stack["service"].reject("ch_001", revision=1, reason="不采用")
    assert result["decision"] == "rejected" and result["status"] == "recorded"
    assert result["revision"] == 1 and result["reviewed_revision"] == 1
    # revision 未被删除、status 未被改写（§23）
    assert stack["repository"].list_revisions("ch_001") == [1]
    assert stack["repository"].get_current("ch_001").status == "proposed"
    assert stack["store"].review_for("ch_001", 1)["decision"] == "rejected"
    assert "editor metadata" in result["notes"][0]


def test_reject_unknown_revision_is_refused(tmp_path: Path) -> None:
    from novelforge.editor import EditorNotFoundError

    stack = editor_stack(tmp_path)
    with pytest.raises(EditorNotFoundError):
        stack["service"].reject("ch_001", revision=9)


def test_quality_passed_is_not_acceptance(tmp_path: Path) -> None:
    """§69：quality_status = passed ≠ status = accepted。"""

    stack = editor_stack(tmp_path)
    stack["repository"].set_status("ch_001", "draft", expected_revision=1)
    node = stack["repository"].get_current("ch_001")
    assert node.quality_status == "unevaluated"
    stack["service"].patch("ch_001", {"goal": "确认维修队列是否被人为改写"},
                           expected_revision=2)
    current = stack["repository"].get_current("ch_001")
    assert current.quality_status == "unevaluated"   # 编辑后必须重新评估
    assert current.status == "proposed"             # 仍然不是 accepted
    accepted = stack["service"].accept("ch_001", expected_revision=3)
    assert accepted["status"] == "applied"
    assert "quality_status=passed" in accepted["acceptance_note"]


def test_accepted_revision_is_never_silently_overwritten(tmp_path: Path) -> None:
    stack = editor_stack(tmp_path)
    stack["service"].accept("ch_001", expected_revision=1)      # r2 accepted
    stack["service"].patch("ch_001", {"goal": "作者继续修改"},
                           expected_revision=2)                 # r3 proposed
    assert stack["repository"].get_revision("ch_001", 2).status == "accepted"
    assert stack["repository"].get_current("ch_001").status == "proposed"
    assert stack["repository"].get_revision("ch_001", 2).payload.goal == "关系进一步发展"


def test_accept_after_quality_failure_is_still_a_choice(tmp_path: Path) -> None:
    """§68：Accept / Reject 由 Editor/Application 拥有；Quality 只说有没有 issue。"""

    stack = editor_stack(tmp_path, repairable=False)
    report = stack["quality"].evaluate()
    assert report.status in ("blocked", "failed")
    result = stack["service"].accept("ch_001", expected_revision=1,
                                     reason="作者选择接受")
    assert result["status"] == "applied"
    quality = stack["service"].get_quality("ch_001")
    assert quality["quality_status"] in ("unevaluated", "accepted")
