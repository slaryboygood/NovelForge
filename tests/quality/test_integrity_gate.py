"""V4-05 §13：Q1 Integrity —— ownership / revision chain / provenance / 必需节点。"""

from __future__ import annotations

from pathlib import Path

from novelforge.blueprint import PremisePayload
from novelforge.persistence.paths import blueprint_node_path

from novelforge.quality.evaluators.integrity_gate import evaluate as integrity_evaluate

from quality_support import (
    NOVEL_ID,
    codes,
    direct_context,
    isolated_gate,
    node,
    scene,
)


def test_foreign_node_is_ownership_mismatch(tmp_path: Path) -> None:
    foreign = scene("sc_001_01")
    object.__setattr__(foreign, "novel_id", "novel_beta")
    context = direct_context([foreign])
    issues = list(integrity_evaluate(context))
    assert "OWNERSHIP_MISMATCH" in codes(issues)
    foreign_issue = [row for row in issues
                     if row.code == "OWNERSHIP_MISMATCH"][0]
    assert foreign_issue.severity == "blocker"


def test_missing_provenance_is_reported(tmp_path: Path) -> None:
    bare = node(NOVEL_ID, "sc_001_01", "scene", scene("sc_001_01").payload,
                parent_id="ch_001", sequence=1, source_ids=(), contract="")
    issues, _quality = isolated_gate(tmp_path, [bare], "Q1", with_novel=False)
    assert "PROVENANCE_INVALID" in codes(issues)


def test_missing_required_node_type(tmp_path: Path) -> None:
    issues, _quality = isolated_gate(
        tmp_path,
        [node(NOVEL_ID, "premise", "premise", PremisePayload(premise="前提"))],
        "Q1", with_novel=False)
    assert "MISSING_REQUIRED_NODE" in codes(issues)


def test_revision_chain_gap_is_reported(tmp_path: Path) -> None:
    """r1 丢失 → revision 链不连续（磁盘损坏模拟）。"""

    issues, quality = isolated_gate(tmp_path, [scene("sc_001_01")], "Q1",
                                    with_novel=False)
    assert "REVISION_CHAIN_BROKEN" not in codes(issues)
    repository = quality.repository
    repository.save_revision(scene("sc_001_01"), expected_revision=1)
    first = blueprint_node_path(tmp_path, NOVEL_ID, "sc_001_01", 1)
    assert first.is_file()
    first.unlink()
    issues, _quality = isolated_gate(tmp_path, [], "Q1", with_novel=False)
    assert "REVISION_CHAIN_BROKEN" in codes(issues)


def test_healthy_broken_fixture_has_no_integrity_issue(tmp_path: Path) -> None:
    from quality_support import quality_stack

    stack = quality_stack(tmp_path, script=None)
    report = stack["quality"].evaluate(gates=("Q1",))
    assert codes(report.issues) == []
