"""V4-01：core revision primitive 测试（ADR-006）。

注意：revision 服务的对象是 Story Blueprint / StoryState / Quality-Repair / Agent mutation，
不是"小说正文版本历史"（ADR-011 已取代 ADR-003）。
"""

from __future__ import annotations

import pytest

from novelforge.core import (
    OperationContext,
    RevisionConflict,
    RevisionRef,
    check_expected_revision,
    digest_payload,
    new_request_id,
    new_revision,
)


def test_new_revision_is_append_only_and_parent_linked() -> None:
    ref = new_revision(artifact_id="bp_demo", kind="story_blueprint",
                       current_revision=3, expected_revision=3,
                       operation="edit_scene", actor="author",
                       source_ids=["story_state:runtime_demo@7"],
                       changed_nodes=["sc_004"], payload={"goal": "x"})

    assert ref.revision == 4, "必须产生新 revision，而不是覆盖"
    assert ref.parent_revision == 3
    assert ref.artifact_id == "bp_demo"
    assert ref.source_ids == ("story_state:runtime_demo@7",)
    assert ref.changed_nodes == ("sc_004",)
    assert ref.digest and len(ref.digest) == 16
    assert ref.request_id.startswith("op_edit_scene_")
    assert ref.created_at


def test_first_revision_starts_at_one_without_parent() -> None:
    ref = new_revision(artifact_id="bp_new", current_revision=None,
                       operation="create_blueprint", kind="story_blueprint")
    assert ref.revision == 1
    assert ref.parent_revision is None


def test_expected_revision_conflict_is_explicit() -> None:
    with pytest.raises(RevisionConflict) as exc:
        check_expected_revision(3, 5, artifact_id="bp_demo")
    payload = exc.value.as_dict()
    assert payload["code"] == "REVISION_CONFLICT"
    assert payload["expected_revision"] == 3
    assert payload["actual_revision"] == 5
    assert payload["artifact_id"] == "bp_demo"


def test_expected_revision_none_is_compatibility_mode() -> None:
    check_expected_revision(None, 9, artifact_id="bp_demo")  # 不抛异常


def test_conflict_when_artifact_does_not_exist_yet() -> None:
    with pytest.raises(RevisionConflict):
        check_expected_revision(2, None, artifact_id="bp_missing")


def test_operation_context_generates_request_id() -> None:
    context = OperationContext(operation="repair_scene", actor="agent")
    assert context.request_id.startswith("op_repair_scene_")
    assert context.as_dict()["actor"] == "agent"
    with pytest.raises(ValueError):
        OperationContext(operation="")


def test_revision_ref_validates_input() -> None:
    with pytest.raises(ValueError):
        RevisionRef(artifact_id="", revision=1)
    with pytest.raises(ValueError):
        RevisionRef(artifact_id="bp", revision=-1)


def test_digest_and_request_id_are_stable_and_unique() -> None:
    assert digest_payload({"b": 1, "a": 2}) == digest_payload({"a": 2, "b": 1})
    assert digest_payload({"a": 1}) != digest_payload({"a": 2})
    assert new_request_id("req") != new_request_id("req")

