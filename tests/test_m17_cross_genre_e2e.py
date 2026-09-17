"""M17 Cross-genre E2E：同一产品链 + 3 题材数据（参数化 harness 回归）。"""

from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

import pytest

from novelforge.story_builder.cross_genre_e2e import (
    DEFAULT_CHAIN,
    default_cases,
    run_cross_genre_e2e,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def e2e(tmp_path_factory: pytest.TempPathFactory) -> dict:
    work = tmp_path_factory.mktemp("m17_e2e")
    return run_cross_genre_e2e(PROJECT_ROOT, work_root=work)


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()[:16]


def test_three_genre_cases_exist() -> None:
    cases = default_cases(PROJECT_ROOT)
    assert len(cases) == 3
    assert {case.genre for case in cases} == {"xianxia", "sci_fi", "modern_mystery"}
    for case in cases:
        assert case.pack_id and case.idea and case.content_markers
        assert case.chain == DEFAULT_CHAIN


def test_all_cases_share_one_chain(e2e: dict) -> None:
    assert e2e["status"] == "PASS"
    assert e2e["case_count"] == 3
    steps = {tuple(row["step"] for row in result["steps"]) for result in e2e["results"]}
    assert steps == {DEFAULT_CHAIN}
    assert e2e["same_engine"]["chain_steps_identical"] is True
    assert e2e["same_engine"]["export_sections_identical"] is True
    assert e2e["same_engine"]["writer_blocks_identical"] is True


@pytest.mark.parametrize("index", [0, 1, 2])
def test_case_e2e_pass(e2e: dict, index: int) -> None:
    result = e2e["results"][index]
    assert result["status"] == "PASS", result["errors"]
    assert result["step_count"] == len(DEFAULT_CHAIN)
    assert not result["errors"]
    invariants = result["invariants"]
    assert invariants["settings_check_passed"] is True
    assert invariants["runtime_started"] is True
    assert invariants["state_changed"] is True
    assert invariants["branch_isolated"] is True
    assert invariants["outline_four_levels"] is True
    assert invariants["export_validation_pass"] is True
    assert invariants["writer_context_pass"] is True
    assert invariants["draft_is_preview"] is True
    assert invariants["fact_sync_proposal_only"] is True
    assert invariants["state_unchanged_after_sync"] is True
    assert invariants["resume_export_identity_stable"] is True
    assert invariants["content_markers_present"] is True
    assert all(result["negative_checks"].values()), result["negative_checks"]


def test_content_differs_but_structure_isomorphic(e2e: dict) -> None:
    iso = e2e["structural_isomorphism"]
    assert iso["content_differs"] is True
    assert iso["markers_all_present"] is True
    fingerprints = e2e["genre_content_fingerprints"]
    assert len({row["genre"] for row in fingerprints.values()}) == 3
    assert len({row["pack_id"] for row in fingerprints.values()}) == 3
    marker_sets = {tuple(row["content_markers"]) for row in fingerprints.values()}
    assert len(marker_sets) == 3


def test_negative_checks_common_to_all_cases(e2e: dict) -> None:
    for result in e2e["results"]:
        checks = result["negative_checks"]
        assert checks["export_tampering_blocked"] is True
        assert checks["writer_fact_not_in_state"] is True
        assert checks["invalid_action_rejected"] is True
        assert checks["invalid_action_no_mutation"] is True
        assert result["state_mutation"] == {"story_state_written_by_writer": False,
                                            "frozen_truth_written": False}


def test_shared_chain_has_no_genre_branches() -> None:
    """通用链路不得出现题材 / 小说名分支（差异只能来自数据）。"""

    targets = [PROJECT_ROOT / "src" / "novelforge" / "story_builder" /
               "cross_genre_e2e.py",
               PROJECT_ROOT / "src" / "novelforge" / "story_builder" /
               "export_package.py",
               PROJECT_ROOT / "src" / "novelforge" / "story_builder" /
               "writer_integration.py"]
    patterns = ("if genre ==", "if pack_id ==", "if novel_id ==",
                "if world_type ==", "genre == \"xianxia\"", "genre == 'xianxia'")
    for path in targets:
        text = path.read_text(encoding="utf-8")
        for pattern in patterns:
            assert pattern not in text, f"{path.name} 含题材分支：{pattern}"


def test_frozen_truth_untouched_by_e2e() -> None:
    """M17 E2E 使用隔离数据根：wasteland_001 frozen truth 不变。"""

    canon = PROJECT_ROOT / "novel/authoring/story_engine/canon/wasteland_001.sqlite"
    state_dir = PROJECT_ROOT / "novel/authoring/story_engine/state"
    before_canon = _digest(canon)
    before_state = hashlib.sha256("|".join(sorted(
        f"{p.name}:{_digest(p)}" for p in state_dir.rglob("*.json"))).encode()
    ).hexdigest()[:16]
    work = PROJECT_ROOT / "workspace" / "m17_isolated_probe"
    run_cross_genre_e2e(PROJECT_ROOT, work_root=work,
                        cases=default_cases(PROJECT_ROOT)[:1])
    assert _digest(canon) == before_canon
    assert hashlib.sha256("|".join(sorted(
        f"{p.name}:{_digest(p)}" for p in state_dir.rglob("*.json"))).encode()
    ).hexdigest()[:16] == before_state


def test_crash_resume_stability_regression(tmp_path: Path) -> None:
    """M17 crash/resume 稳定性：同一 crash→repair→resume 循环重复执行必须稳定。

    已知编译器 crash/resume 用例曾在全量运行中出现 1 次偶发失败（无法稳定复现）；
    这里用重复循环把潜在的顺序 / 累积状态问题变成确定性失败信号。
    """

    spec = importlib.util.spec_from_file_location(
        "chapter_compiler_suite",
        PROJECT_ROOT / "tests" / "test_story_planning_chapter_compiler.py")
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    for index in range(3):
        case_dir = tmp_path / f"resume_round_{index}"
        case_dir.mkdir(parents=True, exist_ok=True)
        module.test_arc_batch_promotes_each_arc_and_survives_crash(case_dir)


def test_e2e_results_are_serializable(e2e: dict) -> None:
    blob = json.dumps(e2e, ensure_ascii=False)
    assert "case_xianxia" in blob and "case_sci_fi" in blob
    restored = json.loads(blob)
    assert restored["case_count"] == e2e["case_count"]
