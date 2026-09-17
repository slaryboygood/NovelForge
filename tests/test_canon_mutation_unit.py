"""C11：fault injection 单元层 —— 组件级防线 + 「去掉防线必须变红」的反向自检。"""

from __future__ import annotations

from novelforge.story_engine.canon import context as context_module
from novelforge.story_engine.canon import planner as planner_module
from novelforge.story_engine.canon.graph import CanonGraphValidator
from novelforge.story_engine.canon.mutation import (
    DIGEST_KEYS,
    P0_INTEGRATION_MUTATIONS,
    TARGET_LAYERS,
    build_mutation_cases,
    run_mutation_suite,
)


def test_mutation_catalog_is_complete_and_layered() -> None:
    cases = build_mutation_cases()
    ids = [case.mutation_id for case in cases]
    assert ids == [f"MUT-{index:03d}" for index in range(1, 52)]
    assert len(set(ids)) == 51
    assert {case.target_layer for case in cases} <= set(TARGET_LAYERS)
    assert {"schema", "context", "canon", "source_ref", "graph", "semantic", "planner",
            "outline", "bootstrap", "repository", "writer"} <= {case.target_layer
                                                                for case in cases}
    for case in cases:
        assert case.description and case.expected_detector
        assert case.expected_codes and case.expected_severity
        assert callable(case.setup) and callable(case.mutation)
    integration = {case.mutation_id for case in cases if case.integration}
    assert set(P0_INTEGRATION_MUTATIONS) <= integration


def test_unit_mutation_suite_passes_without_pollution(tmp_path) -> None:
    cases = [case for case in build_mutation_cases() if not case.integration]
    report = run_mutation_suite(root=tmp_path / "unit", cases=cases)
    failed = [result.mutation_id for result in report.results if not result.passed]
    assert report.ok(), f"未通过的 mutation：{failed}"
    assert report.mutation_kill_rate == 1.0
    assert report.state_pollution_rate == 0.0
    assert report.undetected_mutations == []
    assert report.state_pollution_failures == []
    assert report.expected_detector_mismatch == []
    assert report.blocked == 0
    for result in report.results:
        assert set(result.digest_checks) == set(DIGEST_KEYS)
        assert result.digest_checks["story_state"] == "unchanged"


def test_suite_is_not_vacuous_when_defense_is_removed(tmp_path, monkeypatch) -> None:
    """反向自检：拆掉防线后对应 mutation 必须变红（否则 suite 只是自证）。"""

    monkeypatch.setattr(CanonGraphValidator, "knowledge_leak", lambda self: [])
    knowledge = run_mutation_suite(root=tmp_path / "no-knowledge", only=["MUT-007"])
    assert knowledge.results[0].status == "failed"
    assert "UNDETECTED" in knowledge.results[0].violations

    monkeypatch.setattr(planner_module, "WRITER_VISIBLE_FIELDS",
                        ("title", "goal", "start_state", "concrete_events", "hook", "turn",
                         "payoff", "end_state"))
    writer = run_mutation_suite(root=tmp_path / "narrow-writer-scan", only=["MUT-023"])
    assert writer.results[0].status == "failed"
    assert "UNDETECTED" in writer.results[0].violations

    monkeypatch.setattr(context_module, "NEVER_TRIM", set())
    budget = run_mutation_suite(root=tmp_path / "trim-everything", only=["MUT-037"])
    assert budget.results[0].status == "failed"
    assert "UNDETECTED" in budget.results[0].violations


def test_report_exposes_defense_coverage_fields(tmp_path) -> None:
    report = run_mutation_suite(root=tmp_path / "report", only=["MUT-001", "MUT-026"])
    assert report.total == 2 and report.passed == 2
    assert report.by_layer["source_ref"]["total"] == 1
    assert report.by_layer["semantic"]["total"] == 1
    assert "SemanticIndex.classify_relation" in report.by_detector
    assert report.undetected_mutations == []
    assert report.expected_detector_mismatch == []
    assert report.blocked_mutations == []
    text = report.to_markdown()
    assert "Canon Defense Coverage Matrix" in text
    assert "mutation_kill_rate" in text
    assert "| MUT-001 |" in text
