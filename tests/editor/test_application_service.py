"""V4-06 §7、§50、§51、§64：Application Service 与持久化边界。"""

from __future__ import annotations

from pathlib import Path

import pytest

from novelforge.application.services import EditorService, editor_service
from novelforge.editor import EditorOwnershipError, EditorStore
from novelforge.editor.operations import utc_now
from novelforge.persistence.paths import (
    editor_dir,
    editor_manifest_path,
    editor_operations_dir,
    editor_reviews_dir,
)

from editor_support import editor_stack, revision


def test_paths_come_from_persistence_paths(tmp_path: Path) -> None:
    assert editor_dir(tmp_path, "novel_alpha").as_posix().endswith(
        "novel/authoring/story_engine/editor/novel_alpha")
    assert editor_operations_dir(tmp_path, "novel_alpha").name == "operations"
    assert editor_reviews_dir(tmp_path, "novel_alpha").name == "reviews"
    assert editor_manifest_path(tmp_path, "novel_alpha").name == "MANIFEST.json"


def test_editor_store_is_metadata_only(tmp_path: Path) -> None:
    """§49：editor 不建立第二套 Blueprint truth。"""

    stack = editor_stack(tmp_path)
    stack["service"].patch("ch_001", {"goal": "新目标"}, expected_revision=1)
    store = EditorStore(tmp_path, "novel_alpha")
    stats = store.stats()
    assert stats["operations"] == 1
    manifest = editor_manifest_path(tmp_path, "novel_alpha").read_text(encoding="utf-8")
    assert "editor 不持有第二套 truth" in manifest
    # canonical 内容只在 blueprint store
    blueprint_dir = tmp_path / "novel" / "authoring" / "story_engine" / "blueprint"
    assert (blueprint_dir / "novel_alpha" / "nodes" / "ch_001").is_dir()
    editor_files = list(editor_dir(tmp_path, "novel_alpha").rglob("*.json"))
    assert editor_files and all(
        path.name.startswith(("EO_", "ch_", "sc_", "MANIFEST"))
        for path in editor_files)


def test_editor_store_rejects_cross_novel_writes(tmp_path: Path) -> None:
    from novelforge.editor import EditorOperationRecord

    store = EditorStore(tmp_path, "novel_alpha")
    with pytest.raises(EditorOwnershipError):
        store.record_operation(EditorOperationRecord(
            novel_id="novel_beta", operation="manual_patch", node_id="ch_001"))


def test_application_service_surface(tmp_path: Path) -> None:
    stack = editor_stack(tmp_path)
    service = stack["service"]
    assert isinstance(service, EditorService)
    node = service.get_node("ch_001")
    assert node["entity_hint"] if "entity_hint" in node else True
    assert set(node) >= {"novel_id", "node", "view", "editable_fields",
                         "protected_fields", "quality"}
    history = service.get_history("ch_001")
    assert history["current_revision"] == 1
    assert history["repair_preview"] is not None
    assert service.list_revisions("ch_001") == [1]
    assert service.stats()["editor"]["operations"] == 0


def test_editor_service_factory_wires_offline_stack(tmp_path: Path) -> None:
    stack = editor_stack(tmp_path)
    service = editor_service(tmp_path, "novel_alpha", gateway=stack["gateway"],
                             memory=stack["memory"])
    assert isinstance(service, EditorService)
    assert service.editor.generation is not None
    payload = stack["memory"] and service.get_node("ch_001")
    assert payload["node"]["node_id"] == "ch_001"


def test_ownership_isolation_between_novels(tmp_path: Path) -> None:
    """§64：Novel A 的 editor 不能读 / 改 / diff / restore Novel B。"""

    from novelforge.blueprint import BlueprintRepository

    from editor_support import build_novel, build_broken_blueprint, WEAPON_RULE_TEXT

    build_novel(tmp_path, "novel_alpha", title="阿尔法", fact_text=WEAPON_RULE_TEXT)
    build_novel(tmp_path, "novel_beta", title="贝塔", fact_text=WEAPON_RULE_TEXT)
    build_broken_blueprint(tmp_path, "novel_beta")
    alpha = editor_stack(tmp_path)["service"] if False else None
    # alpha 与 beta 的 node_id 完全相同 → 必须仍然隔离
    from novelforge.editor import BlueprintEditorService

    alpha_editor = BlueprintEditorService(tmp_path, "novel_alpha",
                                          repository=BlueprintRepository(
                                              tmp_path, "novel_alpha"))
    with pytest.raises(EditorOwnershipError):
        alpha_editor._assert_novel("novel_beta")      # noqa: SLF001
    beta_repo = BlueprintRepository(tmp_path, "novel_beta")
    assert beta_repo.get_current("sc_001_02") is not None
    # alpha 侧看不到 beta 的节点（同 id 也不会读到）
    assert alpha_editor.repository.get_current("sc_001_02") is None


def test_operations_are_isolated_per_novel(tmp_path: Path) -> None:
    from novelforge.blueprint import BlueprintRepository

    from editor_support import build_novel, build_broken_blueprint, WEAPON_RULE_TEXT

    build_novel(tmp_path, "novel_alpha", title="阿尔法", fact_text=WEAPON_RULE_TEXT)
    build_novel(tmp_path, "novel_beta", title="贝塔", fact_text=WEAPON_RULE_TEXT)
    build_broken_blueprint(tmp_path, "novel_beta")
    from novelforge.editor import BlueprintEditorService
    from novelforge.editor.contracts import EditRequest

    beta = BlueprintEditorService(tmp_path, "novel_beta",
                                 repository=BlueprintRepository(tmp_path, "novel_beta"))
    beta.patch(EditRequest(novel_id="novel_beta", node_id="ch_001",
                           expected_revision=1, changes={"goal": "贝塔的目标"}))
    assert len(beta.operations()) == 1
    alpha_store = EditorStore(tmp_path, "novel_alpha")
    assert alpha_store.operations() == []


def test_audit_records_are_not_inside_blueprint_payload(tmp_path: Path) -> None:
    """§48：历史操作不得塞进 SceneCard / ChapterCard。"""

    stack = editor_stack(tmp_path)
    stack["service"].patch("ch_001", {"goal": "新目标"}, expected_revision=1)
    node = stack["repository"].get_current("ch_001")
    payload = node.payload.model_dump(mode="json")
    assert "operations" not in payload and "history" not in payload
    assert "operation" in dict(node.provenance)      # provenance 只留指针


def test_move_contract_updates_structure_only(tmp_path: Path) -> None:
    from novelforge.blueprint import ChapterCardPayload, BlueprintNode

    stack = editor_stack(tmp_path)
    stack["repository"].save_revision(
        BlueprintNode(node_id="ch_002", novel_id="novel_alpha", node_type="chapter",
                      payload=ChapterCardPayload(title="第二章",
                                                 characters=["char_001"]),
                      parent_id="unit_01", sequence=2),
        expected_revision=None)
    result = stack["service"].move("sc_001_02", expected_revision=1,
                                   parent_id="ch_002", sequence=1)
    assert result["status"] == "applied"
    node = stack["repository"].get_current("sc_001_02")
    assert node.parent_id == "ch_002" and node.sequence == 1
    assert node.payload.chapter_id == "ch_002"
    assert node.quality_status == "unevaluated"
    operations = stack["service"].operations(node_id="sc_001_02")
    assert operations[-1]["operation"] == "move"
    assert operations[-1]["extra"]["parent_id"] == "ch_002"


def test_move_rejects_invalid_parent_and_noop(tmp_path: Path) -> None:
    from novelforge.editor import (
        EditorNotFoundError,
        EditorOperationRejected,
        EditorValidationError,
    )

    stack = editor_stack(tmp_path)
    with pytest.raises(EditorOperationRejected):
        stack["service"].move("sc_001_02", expected_revision=1, sequence=2)
    with pytest.raises(EditorNotFoundError):
        stack["service"].move("sc_001_02", expected_revision=1, parent_id="ch_999")
    with pytest.raises(EditorValidationError):
        stack["service"].move("sc_001_02", expected_revision=1, parent_id="ch_001",
                              sequence=0)
    with pytest.raises(EditorValidationError):
        # premise 不能直接挂到 chapter 下
        stack["service"].move("premise", expected_revision=1, parent_id="ch_001")
    assert revision(stack, "sc_001_02") == 1


def test_editor_session_is_in_memory_only(tmp_path: Path) -> None:
    stack = editor_stack(tmp_path)
    service = stack["service"]
    session = None
    from novelforge.editor import BlueprintEditorService

    editor: BlueprintEditorService = stack["editor"]
    session = editor.open_session(actor="author", node_id="ch_001")
    assert session.base_revision == 1
    assert editor.get_session(session.session_id).opened_node == "ch_001"
    assert editor.sessions()
    # 不持久化：换一个服务实例看不到 session
    fresh = BlueprintEditorService(tmp_path, "novel_alpha",
                                   repository=stack["repository"])
    assert fresh.sessions() == []
