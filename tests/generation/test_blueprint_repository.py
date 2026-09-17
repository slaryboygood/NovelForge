"""Blueprint canonical store（V4-04 §10–§11、§30–§32、§39）。"""

from __future__ import annotations

from pathlib import Path

import pytest

from novelforge.blueprint import (
    BlueprintNode,
    BlueprintOwnershipError,
    BlueprintRepository,
    BlueprintStatusError,
    PremisePayload,
    ThemePayload,
    validate_graph,
)
from novelforge.core.revision import RevisionConflict
from novelforge.persistence.paths import blueprint_dir, blueprint_index_path


def _premise(node_id: str = "premise") -> BlueprintNode:
    return BlueprintNode(node_id=node_id, novel_id="novel_a", node_type="premise",
                         payload=PremisePayload(premise="前提", central_conflict="冲突"))


def test_save_and_read_current(tmp_path: Path) -> None:
    repository = BlueprintRepository(tmp_path, "novel_a")
    saved = repository.save_revision(_premise(), expected_revision=None)
    assert saved.revision == 1
    assert repository.current_revision("premise") == 1
    assert repository.get_current("premise").payload.premise == "前提"
    assert blueprint_dir(tmp_path, "novel_a").is_dir()
    assert blueprint_index_path(tmp_path, "novel_a").is_file()


def test_revisions_are_append_only(tmp_path: Path) -> None:
    repository = BlueprintRepository(tmp_path, "novel_a")
    repository.save_revision(_premise(), expected_revision=None)
    second = repository.save_revision(
        BlueprintNode(node_id="premise", novel_id="novel_a", node_type="premise",
                      payload=PremisePayload(premise="第二个前提")),
        expected_revision=1)
    assert second.revision == 2
    assert second.parent_revision == 1
    assert repository.list_revisions("premise") == [1, 2]
    assert repository.get_revision("premise", 1).payload.premise == "前提"
    assert repository.get_current("premise").payload.premise == "第二个前提"


def test_expected_revision_conflict_is_explicit(tmp_path: Path) -> None:
    repository = BlueprintRepository(tmp_path, "novel_a")
    repository.save_revision(_premise(), expected_revision=None)
    with pytest.raises(RevisionConflict) as exc:
        repository.save_revision(_premise(), expected_revision=7)
    assert exc.value.as_dict()["expected_revision"] == 7
    assert exc.value.as_dict()["actual_revision"] == 1


def test_idempotency_key_prevents_duplicate_revision(tmp_path: Path) -> None:
    repository = BlueprintRepository(tmp_path, "novel_a")
    first = repository.save_revision(_premise(), expected_revision=None,
                                     idempotency_key="key_1")
    repeat = repository.save_revision(_premise(), expected_revision=None,
                                      idempotency_key="key_1")
    assert repeat.revision == first.revision == 1
    assert repository.list_revisions("premise") == [1]

    other = repository.save_revision(_premise(), expected_revision=None,
                                     idempotency_key="key_2")
    assert other.revision == 2


def test_cross_novel_write_is_rejected(tmp_path: Path) -> None:
    repository = BlueprintRepository(tmp_path, "novel_a")
    with pytest.raises(BlueprintOwnershipError):
        repository.save_revision(
            BlueprintNode(node_id="premise", novel_id="novel_b", node_type="premise",
                          payload=PremisePayload(premise="别的作品")),
            expected_revision=None)


def test_status_transitions_follow_lifecycle(tmp_path: Path) -> None:
    repository = BlueprintRepository(tmp_path, "novel_a")
    repository.save_revision(_premise(), expected_revision=None)
    accepted = repository.set_status("premise", "accepted", expected_revision=1)
    assert accepted.status == "accepted" and accepted.revision == 2
    with pytest.raises(BlueprintStatusError):
        repository.set_status("premise", "draft", expected_revision=2)
    superseded = repository.set_status("premise", "superseded", expected_revision=2)
    assert superseded.status == "superseded"


def test_children_are_ordered_by_sequence(tmp_path: Path) -> None:
    repository = BlueprintRepository(tmp_path, "novel_a")
    parent = BlueprintNode(node_id="unit_01", novel_id="novel_a",
                           node_type="structural_unit",
                           payload=__import__("novelforge.blueprint",
                                              fromlist=["StructuralUnitPayload"]
                                              ).StructuralUnitPayload(
                               unit_type="act", title="第一幕"), sequence=1)
    repository.save_revision(parent, expected_revision=None)
    for index, title in ((2, "第二章"), (1, "第一章")):
        node = BlueprintNode(
            node_id=f"ch_{index:03d}", novel_id="novel_a", node_type="chapter",
            parent_id="unit_01",
            payload=__import__("novelforge.blueprint", fromlist=["ChapterCardPayload"]
                               ).ChapterCardPayload(title=title, goal="g"),
            sequence=index)
        repository.save_revision(node, expected_revision=None)
    children = repository.list_children("unit_01", node_type="chapter")
    assert [row.node_id for row in children] == ["ch_001", "ch_002"]


def test_index_records_schema_version_and_manifest(tmp_path: Path) -> None:
    repository = BlueprintRepository(tmp_path, "novel_a")
    repository.save_revision(_premise(), expected_revision=None)
    snapshot = repository.index_snapshot()
    assert snapshot["schema_version"] >= 1
    assert snapshot["nodes"]["premise"]["revision"] == 1
    manifest = blueprint_dir(tmp_path, "novel_a") / "MANIFEST.json"
    assert manifest.is_file()


def test_graph_validation_reports_orphan_parent(tmp_path: Path) -> None:
    repository = BlueprintRepository(tmp_path, "novel_a")
    repository.save_revision(
        BlueprintNode(node_id="ch_001", novel_id="novel_a", node_type="chapter",
                      parent_id="unit_missing",
                      payload=__import__("novelforge.blueprint",
                                         fromlist=["ChapterCardPayload"]
                                         ).ChapterCardPayload(title="孤儿章节"),
                      sequence=1),
        expected_revision=None)
    report = validate_graph(repository.all_nodes(), novel_id="novel_a")
    assert report["ok"] is False
    assert any(row["code"] == "PARENT_NOT_FOUND" for row in report["issues"])

