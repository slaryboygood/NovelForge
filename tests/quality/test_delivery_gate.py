"""V4-05 §21、§72：Q9 Delivery Readiness —— 只检查可交付性，不做导出。"""

from __future__ import annotations

from pathlib import Path

from novelforge.quality import QualityPolicy, QualityService, make_issue
from novelforge.quality.contracts import QualityEvidence, QualityScope

from quality_support import (
    NOVEL_ID,
    build_novel,
    chapter,
    codes,
    isolated_gate,
    scene,
    setup_node,
)


def test_missing_required_node_is_blocker(tmp_path: Path) -> None:
    issues, _quality = isolated_gate(tmp_path, [scene("sc_001_01")], "Q9",
                                     with_novel=False)
    missing = [row for row in issues
               if row.code == "DELIVERY_MISSING_REQUIRED_NODE"]
    assert missing and missing[0].severity == "blocker"


def test_unpaid_setup_blocks_delivery(tmp_path: Path) -> None:
    issues, _quality = isolated_gate(
        tmp_path,
        [scene("sc_001_01", sequence=1),
         setup_node("setup_001", parent="sc_001_01")],
        "Q9", with_novel=False)
    assert [row.scope.node_ids for row in issues
            if row.code == "DELIVERY_UNPAID_SETUP"] == [("setup_001",)]


def test_chapter_without_scene_is_incomplete(tmp_path: Path) -> None:
    issues, _quality = isolated_gate(tmp_path, [chapter("ch_001")], "Q9",
                                     with_novel=False)
    assert "DELIVERY_MISSING_CHAPTER_OR_SCENE" in codes(issues)


def test_placeholder_blocks_delivery(tmp_path: Path) -> None:
    issues, _quality = isolated_gate(
        tmp_path,
        [scene("sc_001_01", sequence=1, outcome="主角拿到（待定）记录")],
        "Q9", with_novel=False)
    assert "DELIVERY_PLACEHOLDER" in codes(issues)


def test_cross_novel_contamination_is_blocker(tmp_path: Path) -> None:
    from novelforge.quality.evaluators.delivery_gate import (
        evaluate as delivery_evaluate,
    )
    from quality_support import direct_context

    foreign = scene("sc_001_01")
    object.__setattr__(foreign, "novel_id", "novel_beta")
    issues = list(delivery_evaluate(direct_context([foreign])))
    contamination = [row for row in issues
                     if row.code == "DELIVERY_CROSS_NOVEL_CONTAMINATION"]
    assert contamination and contamination[0].severity == "blocker"


def test_unresolved_blocker_is_reported_from_prior_issues(tmp_path: Path) -> None:
    build_novel(tmp_path, NOVEL_ID, title="阿尔法计划", fact_text="主角不会使用枪械")
    from novelforge.blueprint import BlueprintRepository

    repository = BlueprintRepository(tmp_path, NOVEL_ID)
    repository.save_revision(scene("sc_001_01"), expected_revision=None)
    service = QualityService(tmp_path, NOVEL_ID, repository=repository)
    blocker = make_issue(
        code="CANON_CONTRADICTION", novel_id=NOVEL_ID,
        scope=QualityScope(novel_id=NOVEL_ID, node_ids=("sc_001_01",),
                           node_types=("scene",)),
        reason="canon", evaluator_id="test",
        evidence=[QualityEvidence(evidence_id="e1", kind="comparison",
                                  explanation="canon 冲突")])
    report = service.evaluate(gates=("Q9",),
                              policy=QualityPolicy(required_gates=("Q9",)),
                              prior_issues=[blocker])
    assert "DELIVERY_UNRESOLVED_BLOCKER" in codes(report.issues)


def test_delivery_gate_is_global_not_scope_limited(tmp_path: Path) -> None:
    """只复核 changed scope 时不得把缺少 premise 误报成交付缺口（§43 vs §21）。"""

    from quality_support import quality_stack

    stack = quality_stack(tmp_path, script=None)
    report = stack["quality"].evaluate(
        stack["quality"].build_scope(node_ids=("sc_001_02",), kind="changed"),
        gates=("Q9",), policy=QualityPolicy(required_gates=("Q9",)))
    assert "DELIVERY_MISSING_REQUIRED_NODE" not in codes(report.issues)
