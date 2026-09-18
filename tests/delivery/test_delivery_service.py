"""V4-07 §22–§25、§38、§42、§62–§68、§77–§79：交付服务（快照 / 原子性 / 幂等 / 隔离）。"""

from __future__ import annotations

from pathlib import Path

import pytest

from novelforge.application.services import ExportService
from novelforge.delivery import (
    DEFAULT_SELECTION_MODE,
    DeliveryPolicy,
    DeliveryRequest,
    DeliverySelection,
    DeliveryStore,
)
from novelforge.delivery.errors import DeliveryExportError, DeliveryOwnershipError

from delivery_support import delivery_stack, repaired_scene_payload


def _export(root: Path, novel_id: str) -> ExportService:
    return ExportService(root, novel_id)


def _deliver(stack: dict, **kwargs) -> dict:
    selection = _export(stack["root"], stack["novel_id"]).delivery_selection(**kwargs)
    return stack["delivery"].deliver(DeliveryRequest(selection=selection))


def test_delivery_snapshot_pins_revisions_and_creates_no_blueprint_revision(
        tmp_path: Path) -> None:
    """§23–§25：snapshot 钉 revision，但不为导出创建 Blueprint revision。"""

    stack = delivery_stack(tmp_path)
    before = {node.node_id: node.revision
              for node in stack["repository"].all_nodes()}
    result = _deliver(stack, formats=("json",))
    assert result.status == "delivered"
    after = {node.node_id: node.revision
             for node in stack["repository"].all_nodes()}
    assert before == after                                  # 导出不产生 revision
    snapshot = stack["delivery_store"].get_snapshot(result.snapshot_id)
    assert snapshot["node_revisions"] == {
        str(key): int(value) for key, value in before.items()}
    assert snapshot["schema_version"] == 1
    assert snapshot["created_at"] and snapshot["request_id"]
    assert snapshot["selection_mode"] == DEFAULT_SELECTION_MODE


def test_snapshot_is_stable_and_concurrency_safe(tmp_path: Path) -> None:
    """§77：resolve snapshot 之后产生的新 revision 不影响本次导出。"""

    stack = delivery_stack(tmp_path)
    selection = _export(tmp_path, stack["novel_id"]).delivery_selection(
        formats=("json",))
    snapshot = stack["delivery"].snapshot(selection)
    pinned = dict(snapshot.node_revisions)
    # 导出开始后，另一处继续编辑（产生新 revision + 新内容）
    stack["service"].patch("sc_001_02", {"turn": "AFTER-SNAPSHOT-MARKER"},
                           expected_revision=stack["repository"].current_revision(
                               "sc_001_02"))
    # §14：编辑之后质量结论失效 → 默认 policy 会阻断；这里放宽为警告以验证 pinning
    relaxed = DeliverySelection(novel_id=stack["novel_id"], formats=("json",),
                               policy=DeliveryPolicy(
                                   require_no_pending_invalidation=False))
    result = stack["delivery"].deliver(DeliveryRequest(selection=relaxed))
    assert result.status == "delivered", result.notes
    blob = b"".join(artifact.content for artifact in result.artifacts)
    assert b"AFTER-SNAPSHOT-MARKER" not in blob
    assert result.manifest is not None
    assert result.manifest.as_dict()["selected_revisions"] == {
        str(key): int(value) for key, value in pinned.items()}


def test_atomic_failure_leaves_no_published_package(tmp_path: Path) -> None:
    """§64 / §78：exporter 崩溃 → 无 manifest、无 package、无半成品。"""

    stack = delivery_stack(tmp_path)
    selection = _export(tmp_path, stack["novel_id"]).delivery_selection(
        formats=("json", "docx"))
    store = stack["delivery_store"]
    # 让 docx exporter 抛错（模拟崩溃）
    registry = stack["delivery"].registry
    original = registry.get("docx")[1]

    def broken(context):  # noqa: ANN001, ARG001
        raise RuntimeError("docx exporter crash（模拟）")

    registry.register(registry.spec("docx"), broken)
    try:
        result = stack["delivery"].deliver(DeliveryRequest(selection=selection))
    finally:
        registry.register(registry.spec("docx"), original)
    assert result.status == "blocked"
    assert result.artifacts == ()
    assert result.manifest is None
    assert not store.is_published(result.snapshot_id)
    assert store.get_manifest(result.snapshot_id) == {}
    assert not store.staging_dir(result.snapshot_id).exists()
    assert any("exporter 失败" in note for note in result.notes)


def test_partial_policy_allows_explicit_partial_delivery(tmp_path: Path) -> None:
    """§65：只有明确 partial_allowed 才允许少一个文件，并如实标注。"""

    stack = delivery_stack(tmp_path)
    selection = _export(tmp_path, stack["novel_id"]).delivery_selection(
        formats=("json", "docx"), policy=DeliveryPolicy(partial_allowed=True))
    registry = stack["delivery"].registry
    original = registry.get("docx")[1]
    registry.register(registry.spec("docx"),
                      lambda context: (_ for _ in ()).throw(RuntimeError("boom")))
    try:
        result = stack["delivery"].deliver(DeliveryRequest(selection=selection))
    finally:
        registry.register(registry.spec("docx"), original)
    assert result.status == "partial"
    assert [artifact.format for artifact in result.artifacts] == ["json"]
    assert result.manifest.as_dict()["extra"]["exporter_failures"] == ["docx"]


def test_delivery_idempotency(tmp_path: Path) -> None:
    """§66：同一 idempotency_key 不重复生成 package。"""

    stack = delivery_stack(tmp_path)
    selection = _export(tmp_path, stack["novel_id"]).delivery_selection(
        formats=("json",))
    first = stack["delivery"].deliver(DeliveryRequest(selection=selection,
                                                      idempotency_key="k-1"))
    assert first.status == "delivered" and first.idempotent is False
    second = stack["delivery"].deliver(DeliveryRequest(selection=selection,
                                                       idempotency_key="k-1"))
    assert second.snapshot_id == first.snapshot_id
    assert second.idempotent is True
    assert "replay" in second.notes[0]
    assert stack["delivery_store"].find_request("k-1")["snapshot_id"] == \
        first.snapshot_id


def test_reproducibility_js_and_markdown_digest(tmp_path: Path) -> None:
    """§42 / §79：同 snapshot / policy / exporter version → JSON 与 Markdown 一致。"""

    stack = delivery_stack(tmp_path)
    first = _deliver(stack, formats=("json", "markdown"))
    second = _deliver(stack, formats=("json", "markdown"))
    assert first.snapshot_id == second.snapshot_id
    for fmt in ("json", "markdown"):
        one = [row for row in first.artifacts if row.format == fmt][0]
        two = [row for row in second.artifacts if row.format == fmt][0]
        assert one.checksum == two.checksum
        assert one.content == two.content


def test_delivery_does_not_modify_story_truth(tmp_path: Path) -> None:
    """§50 / §96：交付只读 —— Blueprint / Canon / StoryState 前后一致。"""

    stack = delivery_stack(tmp_path)
    from novelforge.persistence.paths import canon_db_path

    canon_before = canon_db_path(tmp_path, stack["novel_id"]).read_bytes()
    state_dir = (tmp_path / "novel" / "authoring" / "story_engine" / "state")
    state_before = {path.name: path.read_bytes()
                    for path in sorted(state_dir.rglob("*")) if path.is_file()}
    blueprint_before = {node.node_id: node.as_dict()
                        for node in stack["repository"].all_nodes()}
    result = _deliver(stack, formats=("json", "markdown", "docx", "nfpack"))
    assert result.status == "delivered"
    assert canon_db_path(tmp_path, stack["novel_id"]).read_bytes() == canon_before
    state_after = {path.name: path.read_bytes()
                   for path in sorted(state_dir.rglob("*")) if path.is_file()}
    assert state_after == state_before
    assert {node.node_id: node.as_dict()
            for node in stack["repository"].all_nodes()} == blueprint_before


def test_store_paths_and_novel_isolation(tmp_path: Path) -> None:
    """§62 / §68：路径经 persistence；两本作品交付互不污染。"""

    from delivery_support import editor_stack

    stack = delivery_stack(tmp_path)
    result = _deliver(stack, formats=("json",))
    store = stack["delivery_store"]
    assert store.root.as_posix().endswith(
        "novel/authoring/story_engine/delivery/novel_alpha")
    other = editor_stack(tmp_path, novel_id="novel_beta", repairable=True, script=[])
    beta_store = DeliveryStore(tmp_path, "novel_beta")
    assert beta_store.list_snapshots() == []
    assert beta_store.stats()["snapshots"] == 0
    alpha_snapshots = [row["snapshot_id"] for row in store.list_snapshots()]
    assert result.snapshot_id in alpha_snapshots
    with pytest.raises(DeliveryOwnershipError):
        stack["delivery"].deliver(DeliveryRequest(selection=DeliverySelection(
            novel_id="novel_beta", formats=("json",))))
    assert other["repository"].novel_id == "novel_beta"


def test_dry_run_writes_nothing(tmp_path: Path) -> None:
    stack = delivery_stack(tmp_path)
    selection = _export(tmp_path, stack["novel_id"]).delivery_selection(
        formats=("json",))
    result = stack["delivery"].deliver(DeliveryRequest(selection=selection,
                                                       dry_run=True))
    assert result.status == "dry_run" and result.artifacts == ()
    assert stack["delivery_store"].list_snapshots() == []
    assert not stack["delivery_store"].is_published(result.snapshot_id)


def test_blocked_delivery_writes_nothing(tmp_path: Path) -> None:
    stack = delivery_stack(tmp_path, clean=False)
    selection = _export(tmp_path, stack["novel_id"]).delivery_selection(
        formats=("json",), selection_mode="accepted")
    result = stack["delivery"].deliver(DeliveryRequest(selection=selection))
    assert result.status == "blocked"
    assert result.artifacts == () and result.manifest is None
    assert stack["delivery_store"].list_snapshots() == []
    assert "未写入" in result.notes[0]


def test_missing_artifact_read_is_explicit(tmp_path: Path) -> None:
    stack = delivery_stack(tmp_path)
    with pytest.raises(DeliveryExportError):
        stack["delivery_store"].read_artifact("DS_missing", "exports/blueprint.json")
    with pytest.raises(Exception):
        stack["delivery_store"].read_artifact("DS_missing", "../escape.json")


def test_artifacts_are_readable_from_store(tmp_path: Path) -> None:
    stack = delivery_stack(tmp_path)
    result = _deliver(stack, formats=("json", "markdown"))
    for artifact in result.artifacts:
        data = stack["delivery_store"].read_artifact(result.snapshot_id,
                                                    artifact.relative_path)
        assert data == artifact.content
    manifest = stack["delivery_store"].get_manifest(result.snapshot_id)
    assert manifest["snapshot_id"] == result.snapshot_id
    assert manifest["artifacts"]
