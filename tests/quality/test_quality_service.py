"""V4-05 §23、§42–§46、§67：QualityService 的评估 / 缓存 / 跳过 / 隔离 / 存储。"""

from __future__ import annotations

from pathlib import Path

import pytest

from novelforge.quality import (
    GATES,
    EvaluatorSpec,
    QualityEvidence,
    QualityPolicy,
    QualityScope,
    QualityScopeError,
    QualityService,
    make_issue,
)
from novelforge.quality.store import QualityStore

from quality_support import (
    NOVEL_ID,
    build_broken_blueprint,
    build_novel,
    codes,
    quality_stack,
)


def test_full_evaluation_reports_gate_results(tmp_path: Path) -> None:
    stack = quality_stack(tmp_path, script=None)
    report = stack["quality"].evaluate()
    assert [row.gate for row in report.gate_results] == list(GATES)
    assert report.status == "blocked"
    assert report.blockers and report.blockers[0].gate == "Q2"
    assert report.as_dict()["digest"]
    assert {row.gate for row in report.issues} <= set(GATES)


def test_scope_can_be_single_node_or_changed_set(tmp_path: Path) -> None:
    stack = quality_stack(tmp_path, script=None)
    service = stack["quality"]
    report = service.evaluate(
        service.build_scope(node_ids=("sc_001_02",), kind="nodes"),
        gates=("Q7",), policy=QualityPolicy(required_gates=("Q7",)))
    assert codes(report.issues) == ["SCENE_NO_NARRATIVE_FUNCTION"]
    blueprint_scope = service.build_scope(kind="blueprint")
    assert blueprint_scope.kind == "blueprint"
    assert "ch_001" in blueprint_scope.node_ids


def test_cross_novel_evaluation_is_refused(tmp_path: Path) -> None:
    stack = quality_stack(tmp_path, script=None)
    with pytest.raises(QualityScopeError):
        stack["quality"].evaluate(QualityScope(novel_id="novel_beta",
                                               kind="blueprint"))


def test_upstream_blocker_skips_downstream_gates(tmp_path: Path) -> None:
    """§42：Q0/Q1 blocker → 下游昂贵 gate 标记 skipped（可配置）。"""

    stack = quality_stack(tmp_path, script=None)
    service = stack["quality"]

    def blocking(context):  # noqa: ANN001, ARG001
        return [make_issue(
            code="OWNERSHIP_MISMATCH", novel_id=NOVEL_ID,
            scope=QualityScope(novel_id=NOVEL_ID, kind="blueprint"),
            reason="模拟 Q1 blocker", evaluator_id="test.blocker.v1",
            evidence=[QualityEvidence(evidence_id="ev", kind="graph",
                                      explanation="foreign node")])]

    service.registry.register(EvaluatorSpec(
        evaluator_id="test.blocker.v1", version=1, gate="Q1",
        kind="deterministic"), blocking)
    report = service.evaluate(
        gates=("Q1", "Q7"),
        policy=QualityPolicy(required_gates=("Q1", "Q7"), stop_on_blocker=True))
    assert [row.status for row in report.gate_results] == ["blocked", "skipped"]
    assert report.status == "blocked"
    assert report.gate_results[1].skipped_reason
    # 关掉 stop_on_blocker 后仍会继续跑下游
    service.clear_cache()
    report2 = service.evaluate(
        gates=("Q1", "Q7"),
        policy=QualityPolicy(required_gates=("Q1", "Q7"), stop_on_blocker=False))
    assert [row.status for row in report2.gate_results] == ["blocked", "failed"]


def test_incremental_cache_reuses_unchanged_revision(tmp_path: Path) -> None:
    """§44：node revision / evaluator version 未变 → 复用上一轮判断。"""

    stack = quality_stack(tmp_path, script=None)
    service = stack["quality"]
    first = service.evaluate(gates=("Q7",))
    calls = {"n": 0}
    registration = service.registry.get("quality.narrative.v1")
    original = registration.fn

    def counting(context):  # noqa: ANN001
        calls["n"] += 1
        return original(context)

    registration.fn = counting
    second = service.evaluate(gates=("Q7",))
    assert calls["n"] == 0, "revision / evaluator version 未变时必须命中缓存"
    assert [row.issue_id for row in first.issues] == \
        [row.issue_id for row in second.issues]
    service.clear_cache()
    third = service.evaluate(gates=("Q7",), use_cache=False)
    assert calls["n"] == 1
    assert [row.issue_id for row in third.issues] == \
        [row.issue_id for row in first.issues]
    registration.fn = original


def test_store_persists_reports_and_issues(tmp_path: Path) -> None:
    stack = quality_stack(tmp_path, script=None)
    report = stack["quality"].evaluate(gates=("Q7",))
    store = stack["quality"].store
    assert store.latest_report()["report_id"] == report.report_id
    issue_id = report.issues[0].issue_id
    assert store.get_issue(issue_id)["code"] == "SCENE_NO_NARRATIVE_FUNCTION"
    assert store.issue_objects(status="open")[0].code == \
        "SCENE_NO_NARRATIVE_FUNCTION"
    assert store.stats()["open"] >= 1
    updated = store.update_issue_status(issue_id, "resolved", note="test")
    assert updated["status"] == "resolved"
    assert store.list_issues(status="open") == []


def test_quality_status_is_a_projection_not_the_owner(tmp_path: Path) -> None:
    """§46：节点只保存 quality_status 投影，evidence 留在 Quality Store。"""

    stack = quality_stack(tmp_path, script=None)
    service = stack["quality"]
    service.evaluate(gates=("Q7",))
    assert service.project_quality_status(node_ids=("sc_001_02",)) == \
        {"sc_001_02": "failed"}
    node = stack["repository"].get_current("sc_001_02")
    assert node.quality_status == "unevaluated"  # evaluator 只读，不写回节点


def test_ownership_isolation_between_novels(tmp_path: Path) -> None:
    """§67：Novel A 的 Quality 绝不读取 Novel B（即使 node_id / 名称相同）。"""

    build_novel(tmp_path, "novel_alpha", title="阿尔法计划",
                fact_text="主角不会使用枪械")
    build_novel(tmp_path, "novel_beta", title="贝塔计划",
                fact_text="主角不会使用枪械")
    beta_repository = build_broken_blueprint(tmp_path, "novel_beta")
    service = QualityService(tmp_path, "novel_alpha")
    report = service.evaluate(gates=("Q2", "Q7"))
    assert {issue.novel_id for issue in report.issues} <= {"novel_alpha"}
    assert not [issue for issue in report.issues
                if issue.scope.node_ids and
                issue.scope.node_ids[0] in {node.node_id
                                            for node in beta_repository.all_nodes()}
                and issue.code == "SCENE_NO_NARRATIVE_FUNCTION"]
    assert QualityStore(tmp_path, "novel_beta").list_issues() == []
    assert beta_repository.get_current("sc_001_02") is not None
