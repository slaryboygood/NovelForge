"""V4-06 §11–§13、§41、§47：revision history / RevisionView / provenance / 审计。"""

from __future__ import annotations

from pathlib import Path

from editor_support import editor_stack, revision, scripted, current_payload, \
    repaired_chapter_payload


def test_history_lists_revisions_with_author_and_operation(tmp_path: Path) -> None:
    stack = editor_stack(tmp_path)
    service = stack["service"]
    service.patch("ch_001", {"goal": "确认维修队列是否被人为改写"},
                  expected_revision=1, reason="作者改目标")
    service.accept("ch_001", expected_revision=2, reason="接受")
    history = service.get_history("ch_001")
    rows = history["revisions"]
    assert [row["revision"] for row in rows] == [1, 2, 3]
    assert rows[0]["author"] == "ai_generation"      # V4-04 生成的原始内容
    assert rows[1]["author"] == "human"              # 手工 patch
    assert rows[1]["operation"] == "manual_patch"
    assert rows[2]["status"] == "accepted"
    assert rows[2]["is_current"] is True
    assert history["current_revision"] == 3
    assert {row["operation"] for row in history["operations"]} >= {"manual_patch",
                                                                   "accept"}


def test_revision_view_exposes_required_fields(tmp_path: Path) -> None:
    stack = editor_stack(tmp_path)
    view = stack["service"].get_node("ch_001")["view"]
    for field in ("node_id", "revision", "parent_revision", "status", "created_at",
                  "updated_at", "source", "author", "operation", "request_id",
                  "summary"):
        assert field in view
    assert view["revision"] == 1 and view["parent_revision"] == 0
    assert view["source"].startswith("blueprint.")
    assert view["generation_contract"].startswith("blueprint.")


def test_author_classification_for_ai_operations(tmp_path: Path) -> None:
    """§12：至少可区分 human / ai_generation / ai_repair / ai_rewrite / restore。"""

    from novelforge.blueprint import BlueprintNode

    from novelforge.editor.history import author_for

    base = {"node_id": "ch_001", "novel_id": "novel_alpha", "node_type": "chapter",
            "payload": current_payload_for_chapter(), "generation_contract":
            "blueprint.chapter.v1", "provenance": {}}
    assert author_for(BlueprintNode(**base)) == "ai_generation"
    assert author_for(BlueprintNode(**{**base, "provenance":
                                       {"task_input_keys": ["repair", "task"]}})) == \
        "ai_repair"
    assert author_for(BlueprintNode(**{**base, "generation_contract":
                                       "blueprint.chapter.rewrite.v1",
                                       "provenance": {"operation": "ai_rewrite"}})) == \
        "ai_rewrite"
    assert author_for(BlueprintNode(**{**base, "provenance":
                                       {"operation": "restore", "restored_from": 1}})) == \
        "restore"
    assert author_for(BlueprintNode(**{**base, "generation_contract": ""})) == "system"
    assert author_for(BlueprintNode(**base), operation="manual_patch") == "human"


def current_payload_for_chapter() -> dict:
    from novelforge.blueprint import ChapterCardPayload

    return ChapterCardPayload(title="t", goal="g").model_dump(mode="json")


def test_revisions_are_append_only_and_old_content_stays_readable(tmp_path: Path) -> None:
    stack = editor_stack(tmp_path)
    service = stack["service"]
    original = stack["repository"].get_revision("ch_001", 1).payload.title
    service.patch("ch_001", {"title": "新标题 A"}, expected_revision=1)
    service.patch("ch_001", {"title": "新标题 B"}, expected_revision=2)
    assert stack["repository"].list_revisions("ch_001") == [1, 2, 3]
    assert stack["repository"].get_revision("ch_001", 1).payload.title == original
    assert stack["repository"].get_revision("ch_001", 2).payload.title == "新标题 A"
    assert stack["repository"].get_revision("ch_001", 3).payload.title == "新标题 B"


def test_revision_provenance_records_source_and_changed_fields(tmp_path: Path) -> None:
    stack = editor_stack(tmp_path)
    stack["service"].patch("ch_001", {"hook": "新的钩子"}, expected_revision=1)
    node = stack["repository"].get_current("ch_001")
    provenance = dict(node.provenance)
    assert provenance["operation"] == "manual_patch"
    assert provenance["source_revision"] == 1
    assert provenance["changed_fields"] == ["hook"]
    assert node.parent_revision == 1 and node.revision == 2


def test_ai_rewrite_provenance_carries_contract_and_model(tmp_path: Path) -> None:
    stack = editor_stack(tmp_path)
    payload = current_payload(stack, "ch_001")
    scripted(stack, {**payload, "turn": "新的转折"})
    stack["service"].rewrite("ch_001", ["turn"], "把转折写具体",
                             expected_revision=revision(stack, "ch_001"))
    node = stack["repository"].get_current("ch_001")
    provenance = dict(node.provenance)
    assert provenance["operation"] == "ai_rewrite"
    assert provenance["contract_id"] == "blueprint.chapter.rewrite.v1"
    assert provenance["target_fields"] == ["turn"]
    assert provenance["model"] and provenance["provider"]
    assert provenance["context_digest"]
    assert "prompt" not in provenance          # §13：不保存完整敏感 prompt
    assert node.generation_contract == "blueprint.chapter.rewrite.v1"


def test_get_node_supports_historical_revision(tmp_path: Path) -> None:
    stack = editor_stack(tmp_path)
    stack["service"].patch("ch_001", {"goal": "新目标"}, expected_revision=1)
    old = stack["service"].get_node("ch_001", 1)
    assert old["node"]["payload"]["goal"] == "关系进一步发展"
    assert old["view"]["is_current"] is False
    current = stack["service"].get_node("ch_001")
    assert current["node"]["payload"]["goal"] == "新目标"


def test_history_includes_operations_and_reviews(tmp_path: Path) -> None:
    stack = editor_stack(tmp_path)
    stack["service"].patch("ch_001", {"goal": "新目标"}, expected_revision=1)
    stack["service"].reject("ch_001", revision=2, reason="不满意")
    history = stack["service"].get_history("ch_001")
    row = [item for item in history["revisions"] if item["revision"] == 2][0]
    assert row["review_status"] == "rejected"
    assert row["review_note"] == "不满意"


def test_operations_are_per_novel_and_queryable(tmp_path: Path) -> None:
    stack = editor_stack(tmp_path)
    stack["service"].patch("ch_001", {"goal": "新目标"}, expected_revision=1)
    stack["service"].patch("sc_001_02", {"story_function": ["advance_plot"]},
                           expected_revision=1)
    assert len(stack["service"].operations()) == 2
    assert len(stack["service"].operations(node_id="ch_001")) == 1
    stats = stack["service"].stats()
    assert stats["editor"]["operations"] == 2
    assert stats["editor"]["by_operation"] == {"manual_patch": 2}
