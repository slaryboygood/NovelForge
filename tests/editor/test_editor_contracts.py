"""V4-06 §6、§9、§12、§19、§75：Editor 契约对象与错误模型。"""

from __future__ import annotations

import pytest

from novelforge.editor import (
    AUTHOR_KINDS,
    BATCH_POLICIES,
    EDIT_STATUSES,
    OPERATION_KINDS,
    REVIEW_DECISIONS,
    ApprovalResult,
    BatchEditRequest,
    ChangeImpact,
    DiffRequest,
    EditRequest,
    EditResult,
    EditorOperationRecord,
    EditorSession,
    EditorValidationError,
    MoveNodeRequest,
    RestoreResult,
    ReviewDecision,
    RevisionHistory,
    RevisionView,
    RewriteRequest,
    RewriteResult,
)


def test_edit_request_requires_fields_and_changes() -> None:
    with pytest.raises(EditorValidationError):
        EditRequest(novel_id="", node_id="ch_001", expected_revision=1,
                    changes={"goal": "x"})
    with pytest.raises(EditorValidationError):
        EditRequest(novel_id="novel_alpha", node_id="ch_001", expected_revision=1,
                    changes={})
    with pytest.raises(EditorValidationError):
        EditRequest(novel_id="novel_alpha", node_id="ch_001", expected_revision=1,
                    changes={"goal": "x"}, actor="robot")
    request = EditRequest(novel_id="novel_alpha", node_id="ch_001",
                          expected_revision=1, changes={"goal": "x"})
    assert request.request_id.startswith("edit_")
    assert request.as_dict()["changes"] == {"goal": "x"}


def test_rewrite_request_requires_target_fields_and_instruction() -> None:
    with pytest.raises(EditorValidationError):
        RewriteRequest(novel_id="novel_alpha", node_id="ch_001",
                       expected_revision=1, target_fields=(), instruction="x")
    with pytest.raises(EditorValidationError):
        RewriteRequest(novel_id="novel_alpha", node_id="ch_001",
                       expected_revision=1, target_fields=("goal",), instruction=" ")
    request = RewriteRequest(novel_id="novel_alpha", node_id="ch_001",
                             expected_revision=1, target_fields=("goal",),
                             instruction="更具体")
    assert request.actor == "ai_rewrite"
    assert request.as_dict()["target_fields"] == ["goal"]


def test_batch_request_guards_ownership_and_policy() -> None:
    rows = (EditRequest(novel_id="novel_alpha", node_id="ch_001",
                        expected_revision=1, changes={"goal": "x"}),)
    with pytest.raises(EditorValidationError):
        BatchEditRequest(novel_id="novel_alpha", requests=(), policy="all_or_rollback")
    with pytest.raises(EditorValidationError):
        BatchEditRequest(novel_id="novel_alpha", requests=rows, policy="whatever")
    with pytest.raises(EditorValidationError):
        BatchEditRequest(
            novel_id="novel_beta",
            requests=(EditRequest(novel_id="novel_alpha", node_id="ch_001",
                                  expected_revision=1, changes={"goal": "x"}),))
    assert BATCH_POLICIES == ("all_or_rollback", "partial")


def test_result_statuses_are_closed_sets() -> None:
    assert EDIT_STATUSES == ("applied", "dry_run", "rejected", "conflict", "partial")
    assert REVIEW_DECISIONS == ("accepted", "rejected")
    with pytest.raises(EditorValidationError):
        EditResult(node_id="ch_001", novel_id="novel_alpha", status="maybe")
    with pytest.raises(EditorValidationError):
        ApprovalResult(node_id="ch_001", novel_id="novel_alpha", decision="maybe")
    with pytest.raises(EditorValidationError):
        ReviewDecision(node_id="ch_001", novel_id="novel_alpha", revision=1,
                       decision="maybe")


def test_operation_record_validates_operation_kind_and_assigns_id() -> None:
    record = EditorOperationRecord(novel_id="novel_alpha", operation="manual_patch",
                                   node_id="ch_001", source_revision=1,
                                   result_revision=2, changed_fields=("goal",))
    assert record.operation_id.startswith("EO_")
    assert record.as_dict()["changed_fields"] == ["goal"]
    with pytest.raises(EditorValidationError):
        EditorOperationRecord(novel_id="novel_alpha", operation="rewrite_everything",
                              node_id="ch_001")
    assert "manual_patch" in OPERATION_KINDS and "quality_repair" in OPERATION_KINDS
    assert "ai_rewrite" in AUTHOR_KINDS and "restore" in AUTHOR_KINDS


def test_move_request_requires_a_real_change() -> None:
    with pytest.raises(EditorValidationError):
        MoveNodeRequest(novel_id="novel_alpha", node_id="sc_001_01",
                        expected_revision=1)
    request = MoveNodeRequest(novel_id="novel_alpha", node_id="sc_001_01",
                              expected_revision=1, parent_id="ch_001")
    assert request.request_id.startswith("move_")


def test_diff_request_validation() -> None:
    with pytest.raises(EditorValidationError):
        DiffRequest(novel_id="novel_alpha", node_id="ch_001", from_revision=0)
    assert DiffRequest(novel_id="novel_alpha", node_id="ch_001",
                       from_revision=1).to_revision is None


def test_view_contracts_serialize_without_internals() -> None:
    view = RevisionView(node_id="ch_001", novel_id="novel_alpha", node_type="chapter",
                        revision=2, author="human", operation="manual_patch",
                        changed_fields=("goal",), is_current=True)
    payload = view.as_dict()
    assert payload["changed_fields"] == ["goal"] and payload["is_current"] is True
    history = RevisionHistory(novel_id="novel_alpha", node_id="ch_001",
                              current_revision=2, revisions=(view,))
    assert history.as_dict()["revision_count"] == 1
    session = EditorSession(session_id="s1", novel_id="novel_alpha",
                            opened_node="ch_001", base_revision=2)
    assert session.as_dict()["persisted"] is False
    impact = ChangeImpact(novel_id="novel_alpha", node_id="ch_001", revision=2,
                          changed_fields=("goal",), dependent_nodes=("sc_001_01",),
                          quality_invalidations=("ch_001", "sc_001_01"))
    assert impact.as_dict()["auto_modified"] is False
    restore = RestoreResult(node_id="ch_001", novel_id="novel_alpha",
                            operation="restore", restored_from=1, before_revision=3,
                            revision=4, status="applied")
    assert restore.ok is True
    rewrite = RewriteResult(node_id="ch_001", novel_id="novel_alpha", status="dry_run",
                            target_fields=("turn",), dry_run=True)
    assert rewrite.ok is True and rewrite.as_dict()["dry_run"] is True


def test_editor_public_contract_is_small() -> None:
    import novelforge.editor as editor

    exported = set(editor.__all__)
    assert {"BlueprintEditorService", "EditorStore", "EditRequest", "EditResult",
            "BlueprintDiff", "RevisionView", "RevisionHistory", "RewriteRequest",
            "RewriteResult", "ApprovalResult", "RestoreResult", "ChangeImpact",
            "EditorOperationRecord", "ReviewDecision"} <= exported
    # 内部实现不导出
    assert not [name for name in exported if name.startswith("_")]
    assert "PatchApplier" not in exported and "DiffWalker" not in exported
