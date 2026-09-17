"""V4-05 §29–§31、§54、§58：RepairPlanner —— 合并 / 最小 scope / preserve / 冲突 / dry-run。"""

from __future__ import annotations

from pathlib import Path

import pytest

from novelforge.quality import (
    QualityEvidence,
    QualityScope,
    QualityScopeError,
    RepairConflictError,
    RepairNotAllowedError,
    RepairPlanner,
    make_issue,
)

from quality_support import NOVEL_ID, quality_stack


def _issues(stack: dict) -> list[object]:
    report = stack["quality"].evaluate()
    return list(report.issues)


def test_planner_merges_issues_on_same_node(tmp_path: Path) -> None:
    stack = quality_stack(tmp_path, script=None)
    plan = stack["review"].planner.plan(_issues(stack))
    by_node = {step.node_id: step for step in plan.steps}
    assert set(by_node) == {"ch_001", "sc_001_02", "sc_001_03", "sc_001_04"}
    scene4 = by_node["sc_001_04"]
    assert len(scene4.issue_ids) >= 3  # motivation / causal / unmotivated + orphan
    assert scene4.must_resolve == scene4.issue_ids


def test_planner_uses_minimal_scope_and_host_node_for_derived_nodes(
        tmp_path: Path) -> None:
    stack = quality_stack(tmp_path, script=None)
    plan = stack["review"].planner.plan(_issues(stack))
    by_node = {step.node_id: step for step in plan.steps}
    # setup_001 没有生成任务 → 修复落到宿主场景 sc_001_03
    assert "setup_001" not in by_node
    assert any("QI_DEAD_BRANCH" in issue_id
               for issue_id in by_node["sc_001_03"].issue_ids)
    assert plan.blast_radius.changed == tuple(plan.target_node_ids)


def test_preserve_is_hard_constraint(tmp_path: Path) -> None:
    stack = quality_stack(tmp_path, script=None)
    plan = stack["review"].planner.plan(_issues(stack))
    step = [row for row in plan.steps if row.node_id == "ch_001"][0]
    assert {"node_id", "source_ids", "canon"} <= set(step.preserve)
    assert "characters" in step.preserve      # 章节人物不得被质量修复改写
    assert "parent_id" not in step.allow_change
    assert set(step.allow_change) & set(step.preserve) == set()
    chapter_fields = {"title", "goal", "conflict", "turn", "outcome", "hook"}
    assert set(step.allow_change) <= chapter_fields


def test_allow_change_limited_to_real_payload_fields(tmp_path: Path) -> None:
    stack = quality_stack(tmp_path, script=None)
    plan = stack["review"].planner.plan(_issues(stack))
    for step in plan.steps:
        node = stack["repository"].get_current(step.node_id)
        real = set(type(node.payload).model_fields)
        assert set(step.allow_change) <= real
        assert set(step.allow_change) & set(step.preserve) == set()


def test_conflicting_contracts_are_detected(tmp_path: Path) -> None:
    stack = quality_stack(tmp_path, script=None)
    report = stack["quality"].evaluate()
    target = [row for row in report.issues if row.code == "CAUSAL_GAP"][0]
    scope = QualityScope(novel_id=NOVEL_ID, node_ids=target.scope.node_ids,
                         node_types=("scene",))
    conflicting = [
        make_issue(code="CAUSAL_GAP", novel_id=NOVEL_ID, scope=scope,
                   reason="想改 outcome", evaluator_id="test.a",
                   evidence=[QualityEvidence(evidence_id="a", kind="graph",
                                             explanation="a")],
                   repair_contract={"preserve": ["outcome"],
                                    "allow_change": ["outcome", "turn"]}),
        make_issue(code="CAUSAL_GAP", novel_id=NOVEL_ID, scope=scope,
                   reason="必须保留 outcome", evaluator_id="test.b",
                   evidence=[QualityEvidence(evidence_id="b", kind="graph",
                                             explanation="b")],
                   repair_contract={"preserve": ["outcome"],
                                    "allow_change": ["turn"]}),
    ]
    planner = RepairPlanner(tmp_path, NOVEL_ID,
                            repository=stack["repository"])
    plan = planner.plan(conflicting)
    assert plan.status == "conflict"
    assert plan.conflicts
    with pytest.raises(RepairConflictError):
        planner.plan(conflicting, strict=True)


def test_non_repairable_issue_requires_human_review(tmp_path: Path) -> None:
    stack = quality_stack(tmp_path, script=None)
    report = stack["quality"].evaluate(gates=("Q5",))
    circular = [row for row in report.issues if row.code == "CIRCULAR_DEPENDENCY"]
    if not circular:  # broken fixture 无环 → 用 registry 的不可修 code 构造
        circular = [make_issue(
            code="OWNERSHIP_MISMATCH", novel_id=NOVEL_ID,
            scope=QualityScope(novel_id=NOVEL_ID, node_ids=("sc_001_02",),
                               node_types=("scene",)),
            reason="ownership 问题需人工",
            evidence=[QualityEvidence(evidence_id="x", kind="graph",
                                      explanation="foreign")],
            evaluator_id="test")]
    planner = stack["review"].planner
    plan = planner.plan(circular)
    assert plan.status == "needs_human_review"
    assert plan.steps == ()
    assert plan.human_review_reasons
    with pytest.raises(RepairNotAllowedError):
        planner.plan(circular, strict=True)


def test_multi_node_scope_is_not_guessed(tmp_path: Path) -> None:
    """§5 AMBIGUOUS_DO_NOT_MERGE：多节点 scope 不猜"最小范围"。"""

    stack = quality_stack(tmp_path, script=None)
    ambiguous = make_issue(
        code="CANON_CONTRADICTION", novel_id=NOVEL_ID,
        scope=QualityScope(novel_id=NOVEL_ID,
                           node_ids=("sc_001_02", "sc_001_03"),
                           node_types=("scene",)),
        reason="跨节点冲突", evaluator_id="test",
        evidence=[QualityEvidence(evidence_id="x", kind="comparison",
                                  explanation="两个节点都涉及")])
    plan = stack["review"].planner.plan([ambiguous])
    assert plan.status == "needs_human_review"
    assert not plan.steps


def test_cross_novel_planning_is_refused(tmp_path: Path) -> None:
    stack = quality_stack(tmp_path, script=None)
    foreign = make_issue(
        code="CAUSAL_GAP", novel_id="novel_beta",
        scope=QualityScope(novel_id="novel_beta", node_ids=("sc_001_02",),
                           node_types=("scene",)),
        reason="别的作品", evaluator_id="test",
        evidence=[QualityEvidence(evidence_id="x", kind="graph",
                                  explanation="foreign")])
    with pytest.raises(QualityScopeError):
        stack["review"].planner.plan([foreign])


def test_dry_run_plan_writes_nothing_and_is_stable(tmp_path: Path) -> None:
    stack = quality_stack(tmp_path, script=None)
    issues = _issues(stack)
    before = {node.node_id: node.revision
              for node in stack["repository"].all_nodes()}
    first = stack["review"].planner.plan(issues, dry_run=True)
    second = stack["review"].planner.plan(issues, dry_run=True)
    after = {node.node_id: node.revision
             for node in stack["repository"].all_nodes()}
    assert before == after
    assert first.plan_id == second.plan_id
    assert first.as_dict()["dry_run"] is True
    assert first.estimated_model_calls == len(first.steps)
    assert first.steps[0].as_dict()["preserve"]
