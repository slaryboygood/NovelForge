"""V4-05 §37–§38：RepairVerifier —— 复核受影响 gate，确认 issue 真的消失。"""

from __future__ import annotations

from pathlib import Path

from quality_support import (
    quality_stack,
    repaired_chapter_payload,
    repaired_scene_payload,
)


def _stack(tmp_path: Path, script=None):
    script = script if script is not None else [
        repaired_chapter_payload(), repaired_scene_payload(sequence=1),
        repaired_scene_payload(sequence=2), repaired_scene_payload(sequence=3)]
    return quality_stack(tmp_path, script=script, repairable=True)


def _planned(stack):
    report = stack["review"].evaluate()
    return report, stack["review"].planner.plan(report.issues, dry_run=True)


def test_verification_confirms_resolution(tmp_path: Path) -> None:
    stack = _stack(tmp_path)
    report, plan = _planned(stack)
    result = stack["review"].execute_repair(plan, dry_run=False)
    verification = stack["review"].verify_repair(before_report=report, plan=plan,
                                                before_revisions=result.before_revisions)
    assert verification.status == "resolved"
    assert set(verification.original_issue_ids) == set(plan.issue_ids)
    assert verification.remaining_issue_ids == ()
    assert verification.new_issue_ids == ()
    assert verification.quality_status == "passed"
    assert verification.report is not None
    assert verification.as_dict()["revisions_changed"]["sc_001_02"] == \
        {"before": 1, "after": 2}
    assert {"Q0", "Q1", "Q9", "Q7"} <= set(verification.gates_rechecked)


def test_verification_marks_resolved_issues_in_store(tmp_path: Path) -> None:
    stack = _stack(tmp_path)
    report, plan = _planned(stack)
    stack["review"].execute_repair(plan, dry_run=False)
    verification = stack["review"].verify_repair(before_report=report, plan=plan)
    store = stack["quality"].store
    assert all(store.get_issue(issue_id)["status"] == "resolved"
               for issue_id in verification.resolved_issue_ids)
    assert store.stats()["open"] == 0


def test_verification_reports_partial_when_issue_survives(tmp_path: Path) -> None:
    from novelforge.quality import QualityPolicy

    # 计划只覆盖 sc_001_04；stub 返回的仍是"缺少动机 / 因果"的版本
    survivor = dict(repaired_scene_payload(sequence=3))
    survivor["character_goals"] = []
    survivor["escalation"] = ""
    survivor["conflict"] = ""
    stack = _stack(tmp_path, [survivor])
    report = stack["review"].evaluate()
    plan = stack["review"].planner.plan(
        [row for row in report.issues if row.scope.node_ids == ("sc_001_04",)],
        dry_run=True)
    assert [step.node_id for step in plan.steps] == ["sc_001_04"]
    stack["review"].execute_repair(plan, dry_run=False)
    verification = stack["review"].verify_repair(
        before_report=report, plan=plan,
        policy=QualityPolicy(required_gates=("Q4", "Q5")))
    assert verification.status == "partial"
    assert verification.remaining_issue_ids
    assert "QI_ORPHAN_EVENT" in " ".join(verification.resolved_issue_ids)
    assert set(verification.remaining_issue_ids) <= set(plan.issue_ids)


def test_verification_detects_regression(tmp_path: Path) -> None:
    """修复引入新的 blocker（Canon 冲突出现在另一个节点）→ regression。"""

    regressed = dict(repaired_scene_payload(sequence=1))
    regressed["outcome"] = "主角直接使用枪械压住现场的混乱"
    script = [repaired_chapter_payload(), regressed,
              repaired_scene_payload(sequence=2), repaired_scene_payload(sequence=3)]
    stack = _stack(tmp_path, script)
    report = stack["review"].evaluate()
    target = [row for row in report.issues
              if row.scope.node_ids == ("sc_001_02",)]
    plan = stack["review"].planner.plan(target, dry_run=True)
    stack["review"].execute_repair(plan, dry_run=False)
    verification = stack["review"].verify_repair(before_report=report, plan=plan)
    assert verification.status == "regression"
    assert verification.new_issue_ids
    assert verification.notes and "new_blocking" in verification.notes[0]


def test_verification_refuses_cross_novel_report(tmp_path: Path) -> None:
    import pytest

    from novelforge.quality import QualityReport, QualityScope, QualityScopeError

    stack = _stack(tmp_path)
    foreign = QualityReport(report_id="QR_x", novel_id="novel_beta",
                            scope=QualityScope(novel_id="novel_beta",
                                               kind="blueprint"),
                            status="failed")
    with pytest.raises(QualityScopeError):
        stack["review"].verify_repair(before_report=foreign)
