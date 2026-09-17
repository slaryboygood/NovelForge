"""V4-06 §17–§21、§58、§62：AI 字段级改写（只改 target fields + preserve 硬约束）。"""

from __future__ import annotations

from pathlib import Path

import pytest

from novelforge.editor import (
    EditorConflictError,
    EditorOperationRejected,
    EditorPreserveViolation,
    EditorValidationError,
)

from editor_support import current_payload, editor_stack, revision, scripted


def _stack(tmp_path: Path) -> dict:
    return editor_stack(tmp_path)


def test_rewrite_changes_only_target_fields(tmp_path: Path) -> None:
    stack = _stack(tmp_path)
    payload = current_payload(stack, "ch_001")
    scripted(stack, {**payload, "turn": "备份里保留了一次被移除的维修命令"})
    result = stack["service"].rewrite("ch_001", ["turn"], "把转折写得可验证",
                                      expected_revision=1)
    assert result["status"] == "applied"
    assert result["revision"] == 2
    assert result["changed_fields"] == ["turn"]
    assert result["target_fields"] == ["turn"]
    assert result["diff"]["all_changed_fields"] == ["turn"]
    node = stack["repository"].get_current("ch_001")
    assert node.payload.turn == "备份里保留了一次被移除的维修命令"
    # 其它字段逐字节不变
    others = {key: value for key, value in node.payload.model_dump(mode="json").items()
              if key != "turn"}
    assert others == {key: value for key, value in payload.items() if key != "turn"}
    assert node.quality_status == "unevaluated"      # §32
    assert node.status == "proposed"                 # §21：proposal，不是 accepted


def test_rewrite_uses_generation_contract_not_provider_directly(tmp_path: Path) -> None:
    stack = _stack(tmp_path)
    payload = current_payload(stack, "ch_001")
    scripted(stack, {**payload, "turn": "新的转折"})
    result = stack["service"].rewrite("ch_001", ["turn"], "改写转折",
                                      expected_revision=1)
    assert result["contract_id"] == "blueprint.chapter.rewrite.v1"
    assert result["model"] and result["provider"]
    assert result["usage"]
    assert stack["provider"].calls == 1


def test_rewrite_preserve_violation_is_rejected_without_writing(tmp_path: Path) -> None:
    """§20 / §58：模型改了未授权字段 → 拒绝，不落盘。"""

    stack = _stack(tmp_path)
    payload = current_payload(stack, "ch_001")
    scripted(stack, {**payload, "turn": "新的转折", "title": "模型顺手改的标题"})
    before = revision(stack, "ch_001")
    with pytest.raises(EditorPreserveViolation) as exc:
        stack["service"].rewrite("ch_001", ["turn"], "改写转折",
                                 expected_revision=before)
    assert exc.value.details["violating_fields"] == ["title"]
    assert revision(stack, "ch_001") == before       # 没有新 revision
    assert stack["repository"].get_current("ch_001").payload.title == payload["title"]
    # 被拒绝的操作也留痕（审计）
    rejected = [row for row in stack["service"].operations(node_id="ch_001")
                if row["status"] == "rejected"]
    assert rejected and rejected[0]["operation"] == "ai_rewrite"


def test_rewrite_target_and_preserve_overlap_is_refused(tmp_path: Path) -> None:
    stack = _stack(tmp_path)
    with pytest.raises(EditorValidationError):
        stack["service"].rewrite("ch_001", ["turn"], "改写",
                                 expected_revision=1,
                                 preserve_fields=["turn"])


def test_rewrite_unknown_target_field_is_refused(tmp_path: Path) -> None:
    stack = _stack(tmp_path)
    with pytest.raises(EditorValidationError):
        stack["service"].rewrite("ch_001", ["no_such_field"], "改写",
                                 expected_revision=1)
    assert stack["provider"].calls == 0


def test_rewrite_dry_run_calls_no_model_and_writes_nothing(tmp_path: Path) -> None:
    stack = _stack(tmp_path)
    result = stack["service"].rewrite("ch_001", ["turn"], "预告", expected_revision=1,
                                      dry_run=True)
    assert result["status"] == "dry_run" and result["dry_run"] is True
    assert stack["provider"].calls == 0
    assert revision(stack, "ch_001") == 1
    assert result["notes"][0].startswith("dry run：未调用模型")
    assert any("预计调用 1 次模型任务" in note for note in result["notes"])


def test_rewrite_conflict_is_detected_before_model_call(tmp_path: Path) -> None:
    """§62：revision 冲突 → 0 次 provider 调用。"""

    stack = _stack(tmp_path)
    payload = current_payload(stack, "ch_001")
    scripted(stack, {**payload, "turn": "新的转折"})
    stack["service"].patch("ch_001", {"goal": "别的目标"}, expected_revision=1)
    with pytest.raises(EditorConflictError) as exc:
        stack["service"].rewrite("ch_001", ["turn"], "改写",
                                 expected_revision=1)
    assert exc.value.details["actual_revision"] == 2
    assert stack["provider"].calls == 0
    assert revision(stack, "ch_001") == 2


def test_rewrite_without_generation_is_rejected(tmp_path: Path) -> None:
    stack = _stack(tmp_path)
    stack["editor"].generation = None
    with pytest.raises(EditorOperationRejected) as exc:
        stack["service"].rewrite("ch_001", ["turn"], "改写", expected_revision=1)
    assert exc.value.details["code"] == "EDITOR_AI_UNAVAILABLE"


def test_rewrite_idempotency_does_not_call_model_twice(tmp_path: Path) -> None:
    stack = _stack(tmp_path)
    payload = current_payload(stack, "ch_001")
    scripted(stack, {**payload, "turn": "新的转折"})
    first = stack["service"].rewrite("ch_001", ["turn"], "改写",
                                     expected_revision=1, idempotency_key="rw-1")
    calls = stack["provider"].calls
    second = stack["service"].rewrite("ch_001", ["turn"], "改写",
                                      expected_revision=1, idempotency_key="rw-1")
    assert first["revision"] == second["revision"] == 2
    assert stack["provider"].calls == calls
    assert revision(stack, "ch_001") == 2


def test_rewrite_quality_issue_linkage_is_audited(tmp_path: Path) -> None:
    """§47：审计要能回答「是否与某 QualityIssue 关联」。"""

    stack = _stack(tmp_path)
    report = stack["quality"].evaluate(gates=("Q7",))
    issue_id = report.issues[0].issue_id
    payload = current_payload(stack, "sc_001_02")
    scripted(stack, {**payload, "story_function": ["advance_plot", "decision"]})
    result = stack["service"].rewrite(
        "sc_001_02", ["story_function"], "让这一场真的有推进",
        expected_revision=1, quality_issue_ids=[issue_id])
    row = [item for item in stack["service"].operations(node_id="sc_001_02")
           if item["operation"] == "ai_rewrite"][0]
    assert row["ai"]["quality_issue_ids"] == [issue_id]
    assert row["ai"]["target_fields"] == ["story_function"]
    assert result["status"] == "applied"
