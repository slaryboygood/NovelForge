"""V4-06 §8–§10、§59、§63：字段级手工编辑（append-only + schema/reference 校验）。"""

from __future__ import annotations

from pathlib import Path

import pytest

from novelforge.editor import EditRequest, EditorPreserveViolation, EditorValidationError

from editor_support import editor_stack, revision


def _stack(tmp_path: Path) -> dict:
    return editor_stack(tmp_path)


def test_patch_creates_new_revision_with_only_changed_fields(tmp_path: Path) -> None:
    stack = _stack(tmp_path)
    service = stack["service"]
    before = stack["repository"].get_current("ch_001")
    result = service.patch("ch_001", {"title": "维修队列里的异常编号", "hook": "新的钩子"},
                           expected_revision=before.revision, reason="作者改标题")
    assert result["status"] == "applied"
    assert result["revision"] == before.revision + 1
    assert set(result["changed_fields"]) == {"title", "hook"}
    after = stack["repository"].get_current("ch_001")
    # 其它字段完全一致（§59）
    before_payload = before.payload.model_dump(mode="json")
    after_payload = after.payload.model_dump(mode="json")
    assert {key: value for key, value in after_payload.items()
            if key not in ("title", "hook")} == \
        {key: value for key, value in before_payload.items()
         if key not in ("title", "hook")}
    # 旧 revision 永久可读，新 revision 是 proposal + unevaluated
    assert stack["repository"].get_revision("ch_001", 1).payload.title == "被删除的维修日志"
    assert after.status == "proposed"
    assert after.quality_status == "unevaluated"
    assert result["quality_status"] == "unevaluated"


def test_patch_rejects_protected_structural_fields(tmp_path: Path) -> None:
    stack = _stack(tmp_path)
    service = stack["service"]
    for field, value in (("node_id", "ch_999"), ("novel_id", "novel_beta"),
                         ("parent_id", "unit_01"), ("sequence", 5),
                         ("revision", 99), ("schema_version", 2),
                         ("generation_contract", "hacked"),
                         ("provenance", {}), ("source_ids", ["x"]),
                         ("quality_status", "passed"), ("status", "accepted")):
        with pytest.raises(EditorPreserveViolation) as exc:
            service.patch("ch_001", {field: value}, expected_revision=1)
        assert exc.value.code == "EDITOR_PRESERVE_VIOLATION"
        assert field in exc.value.details["protected_fields"]
    assert revision(stack, "ch_001") == 1


def test_patch_rejects_unknown_and_ill_typed_fields(tmp_path: Path) -> None:
    stack = _stack(tmp_path)
    service = stack["service"]
    with pytest.raises(EditorValidationError) as exc:
        service.patch("ch_001", {"no_such_field": "x"}, expected_revision=1)
    assert exc.value.details["unknown_fields"] == ["no_such_field"]
    # schema 校验：setup 必须是 list；title 不能为空
    with pytest.raises(EditorValidationError):
        service.patch("ch_001", {"setup": "not-a-list"}, expected_revision=1)
    with pytest.raises(EditorValidationError):
        service.patch("ch_001", {"title": ""}, expected_revision=1)
    # 引用 / scope 完整性：state intent 的 scope 指向其他作品
    with pytest.raises(EditorValidationError):
        service.patch("ch_001", {"state_change_intent": [
            {"kind": "knowledge", "actor": "char_001", "target": "core_record",
             "value": "known", "scope": "novel:novel_beta"}]}, expected_revision=1)
    assert revision(stack, "ch_001") == 1


def test_patch_reference_integrity_for_scene_chapter(tmp_path: Path) -> None:
    stack = _stack(tmp_path)
    service = stack["service"]
    with pytest.raises(EditorPreserveViolation) as exc:
        service.patch("sc_001_02", {"chapter_id": "ch_999"}, expected_revision=1)
    assert exc.value.details["structural_fields"] == ["chapter_id"]
    assert "move_node" in exc.value.details["hint"]
    assert revision(stack, "sc_001_02") == 1


def test_patch_rejects_structural_identity_for_other_node_types(tmp_path: Path) -> None:
    stack = _stack(tmp_path)
    service = stack["service"]
    for node_id, field, value in (("ch_001", "characters", ["char_999"]),
                                  ("arc_001", "character_id", "char_999"),
                                  ("setup_001", "content", "ok")):
        if field == "content":  # content 是可编辑字段 → 不应被拒绝
            result = service.patch(node_id, {field: value}, expected_revision=1)
            assert result["status"] == "applied"
            continue
        with pytest.raises(EditorPreserveViolation):
            service.patch(node_id, {field: value}, expected_revision=1)


def test_dry_run_writes_nothing(tmp_path: Path) -> None:
    stack = _stack(tmp_path)
    result = stack["service"].patch("ch_001", {"goal": "新的目标"},
                                    expected_revision=1, dry_run=True)
    assert result["status"] == "dry_run" and result["dry_run"] is True
    assert revision(stack, "ch_001") == 1
    assert stack["repository"].get_current("ch_001").payload.goal == "关系进一步发展"
    assert result["impact"]["dependent_nodes"]


def test_patch_records_audit_operation(tmp_path: Path) -> None:
    stack = _stack(tmp_path)
    stack["service"].patch("ch_001", {"goal": "新的目标"}, expected_revision=1,
                           reason="作者决定")
    operations = stack["service"].operations(node_id="ch_001")
    assert len(operations) == 1
    row = operations[0]
    assert row["operation"] == "manual_patch" and row["actor"] == "human"
    assert row["source_revision"] == 1 and row["result_revision"] == 2
    assert row["changed_fields"] == ["goal"] and row["reason"] == "作者决定"
    assert row["created_at"]


def test_editor_domain_patch_api_matches_application_service(tmp_path: Path) -> None:
    stack = _stack(tmp_path)
    result = stack["editor"].patch(EditRequest(
        novel_id="novel_alpha", node_id="sc_001_02", expected_revision=1,
        changes={"story_function": ["advance_plot", "escalate_conflict"]}))
    assert result.status == "applied"
    assert result.changed_fields == ("story_function",)
    assert result.as_dict()["diff"]["changed_fields"] == ["story_function"]


def test_patch_cannot_target_missing_node(tmp_path: Path) -> None:
    from novelforge.editor import EditorNotFoundError

    stack = _stack(tmp_path)
    with pytest.raises(EditorNotFoundError):
        stack["service"].patch("ch_999", {"goal": "x"}, expected_revision=1)
