"""C11：fault injection 集成层 —— P0 从真实入口注入 + 正式状态零污染 + 文档一致性。"""

from __future__ import annotations

from pathlib import Path

from novelforge.story_engine.canon.mutation import (
    P0_INTEGRATION_MUTATIONS,
    build_mutation_cases,
    run_mutation_suite,
)

MATRIX_DOC = Path("docs/CANON_DEFENSE_COVERAGE_MATRIX.md")
GUARDED_FILES = (Path("workspace/wasteland_001_exports/WASTELAND_001_OUTLINE_V3_CANONICAL_CANDIDATE.json"),
                 Path("novel/config/story_engine/wasteland_001_pack.json"))


def _fingerprint(path: Path) -> tuple[int, int] | None:
    if not path.is_file():
        return None
    stat = path.stat()
    return (stat.st_size, stat.st_mtime_ns)


def test_p0_integration_mutations_are_real_entrypoints(tmp_path) -> None:
    cases = [case for case in build_mutation_cases() if case.integration]
    assert set(P0_INTEGRATION_MUTATIONS) <= {case.mutation_id for case in cases}
    report = run_mutation_suite(root=tmp_path / "integration", cases=cases)
    failed = [result.mutation_id for result in report.results if not result.passed]
    assert report.ok(), f"未通过的集成 mutation：{failed}"
    assert report.blocked == 0
    for case in cases:
        result = next(item for item in report.results if item.mutation_id == case.mutation_id)
        assert result.integration is True
        assert result.detected is True
        assert result.detector == case.expected_detector
        assert set(result.codes) & set(case.expected_codes)


def test_full_suite_kill_rate_and_zero_pollution(tmp_path) -> None:
    before = {path: _fingerprint(path) for path in GUARDED_FILES}
    report = run_mutation_suite(root=tmp_path / "full")
    assert report.total == 51
    assert report.mutation_kill_rate == 1.0
    assert report.state_pollution_rate == 0.0
    assert report.undetected_mutations == []
    assert report.state_pollution_failures == []
    assert report.expected_detector_mismatch == []
    assert report.blocked_mutations == []
    for result in report.results:
        assert result.digest_checks["story_state"] == "unchanged"
        assert result.digest_checks["outline"] == "unchanged"
    assert {path: _fingerprint(path) for path in GUARDED_FILES} == before


def test_committed_defense_matrix_matches_live_run(tmp_path) -> None:
    report = run_mutation_suite(root=tmp_path / "matrix")
    assert MATRIX_DOC.is_file(), "缺少 docs/CANON_DEFENSE_COVERAGE_MATRIX.md"
    committed = MATRIX_DOC.read_text(encoding="utf-8")
    assert committed == report.to_markdown(), (
        "覆盖矩阵与真实运行不一致；请运行 "
        "`python -m novelforge.story_engine.canon.mutation --output "
        "docs/CANON_DEFENSE_COVERAGE_MATRIX.md` 重新生成")
