"""M13 Game UI P0 acceptance 回归：scope / freeze guard / acceptance / M14 readiness。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from novelforge.story_engine.m11_p15p import (
    FROZEN_FOUNDATION_DIGESTS,
    FROZEN_SOURCE_DIGESTS,
)
from novelforge.story_engine.m11_run12 import M11Run12Service
from novelforge.story_engine.m12_acceptance import semantic_fingerprint
from novelforge.story_engine.m13_game_ui import (
    ACCEPTANCE_FILE,
    BASELINE_FILE,
    FREEZE_GUARD_FILE,
    M13GameUIService,
    M14_READINESS_FILE,
    W6_EVIDENCE,
    W6_ITEMS,
    w6_scope_from_roadmap,
)

from m13_phase_history import (
    PHASE_IDS,
    load_phase_snapshot,
    report_records,
    snapshot_exists,
    verify_phase_snapshot,
)

ROOT = Path(".").resolve()
DESIGN_DIR = ROOT / "workspace/wasteland_001_exports/repair_adoption_v1"
M13_DIR = DESIGN_DIR / "m13"


@pytest.fixture(scope="module")
def m13():
    service = M13GameUIService(ROOT)
    preflight = service.run_preflight()
    service.record_test_evidence(
        pytest={"status": "PASS", "summary": "tests/test_m13_game_ui_p0.py 8 passed"},
        validate_project={"status": "PASS"},
        ui_build={"status": "PASS", "summary": "tsc -b && vite build"},
        browser={"status": "PASS",
                 "summary": "tests/browser_m13_game_ui_p0.cjs（W6-01..06 + 390px）"})
    result = service.acceptance()
    return service, preflight, result


def _artifact(name: str) -> dict:
    return json.loads((M13_DIR / name).read_text(encoding="utf-8"))


# ---------------------------------------------------------------- scope
def test_w6_scope_comes_from_roadmap() -> None:
    rows = w6_scope_from_roadmap(ROOT)
    assert [row["item"] for row in rows] == list(W6_ITEMS)
    for row in rows:
        assert row["title"] and row["content"] and row["completion"]
    assert "单页引导式创作流" in rows[0]["title"]
    assert "小屏必须可用清单" in rows[5]["title"]


def test_execution_baseline(m13) -> None:
    _service, _preflight, _result = m13
    baseline = _artifact(BASELINE_FILE)
    assert baseline["milestone"] == "M13"
    assert [row["item"] for row in baseline["w6_scope"]] == list(W6_ITEMS)
    for row in baseline["w6_scope"]:
        assert row["evidence"]["files"], row["item"]
    assert baseline["entry_criteria"]["requires"].startswith("M12 freeze")
    assert baseline["next_milestone_dependency"]["milestone"].startswith("M14")
    assert len(baseline["acceptance_criteria"]) == 6


def test_preflight_freeze_guard(m13) -> None:
    _service, preflight, _result = m13
    guard = _artifact(FREEZE_GUARD_FILE)
    assert preflight["status"] == "PASS"
    assert guard["status"] == "PASS"
    assert all(guard["checks"].values()), guard["checks"]
    assert guard["freeze_status"] == "FROZEN"
    assert all(status == "PASS" for status in guard["phase_snapshots"].values())


# ---------------------------------------------------------------- acceptance
def test_m13_acceptance_pass(m13) -> None:
    _service, _preflight, result = m13
    acceptance = result["acceptance"]
    assert acceptance["status"] == "PASS"
    assert acceptance["criteria_count"] == 6
    assert acceptance["satisfied_count"] == 6
    assert acceptance["unsatisfied_count"] == 0
    assert all(row["satisfied"] for row in acceptance["criteria"])
    assert set(acceptance["w6_status"]) == set(W6_ITEMS)
    assert all(value == "COMPLETE" for value in acceptance["w6_status"].values())
    assert _artifact(ACCEPTANCE_FILE)["status"] == "PASS"


def test_w6_evidence_files_exist() -> None:
    for item, row in W6_EVIDENCE.items():
        assert row["title"], item
        for path in row["files"]:
            assert (ROOT / path).is_file(), f"{item} 缺少实现文件 {path}"
        for test in row["python_tests"]:
            file_name = test.split("::")[0]
            assert (ROOT / file_name).is_file(), f"{item} 缺少测试 {file_name}"
    assert (ROOT / "tests/browser_m13_game_ui_p0.cjs").is_file()


def test_m12_freeze_and_truth_unchanged(m13) -> None:
    service, _preflight, _result = m13
    runner = M11Run12Service(ROOT)
    truth = runner.truth_digests()
    assert truth["canon"] == FROZEN_SOURCE_DIGESTS["canon"]
    assert truth["story_state"] == FROZEN_SOURCE_DIGESTS["story_state"]
    assert truth["legacy"] == FROZEN_SOURCE_DIGESTS["legacy"]
    assert truth["chapter_ir"] == FROZEN_SOURCE_DIGESTS["chapter_ir"]
    assert truth["historical_foundation"] == FROZEN_FOUNDATION_DIGESTS
    frozen = runner.frozen_digests()
    assert frozen["contract"] == "67559aa55442d69e"
    assert frozen["repair_gate"] == "e1eab4c33ae75b01"
    guard = _artifact(FREEZE_GUARD_FILE)
    assert semantic_fingerprint(service.design_dir) == guard["m11_semantic_fingerprint"]
    m12 = json.loads((DESIGN_DIR / "m12" /
                      "WASTELAND_001_M12_FREEZE_V1.json").read_text(encoding="utf-8"))
    assert m12["status"] == "FROZEN"


def test_m14_readiness(m13) -> None:
    _service, _preflight, result = m13
    readiness = result["m14_readiness"]
    assert readiness["m14_entry_allowed"] is True
    assert readiness["m14_executed"] is False
    assert readiness["m13_acceptance_status"] == "PASS"
    assert readiness["next_milestone"].startswith("M14")
    assert _artifact(M14_READINESS_FILE)["m14_entry_allowed"] is True


# ---------------------------------------------------------------- snapshots + report
def test_m13_phase_snapshots_frozen(m13) -> None:
    _service, _preflight, result = m13
    for phase_id in PHASE_IDS:
        assert snapshot_exists(phase_id), phase_id
        assert verify_phase_snapshot(phase_id)["status"] == "PASS", phase_id
    snapshot = load_phase_snapshot("M13_ACCEPTANCE")
    assert snapshot["status"] == "PASS"
    assert snapshot["satisfied_count"] == 6
    assert snapshot["m12_freeze_status"] == "FROZEN"
    assert snapshot["m14_entry_allowed"] is True
    assert snapshot["w6_items"] == list(W6_ITEMS)
    assert result["acceptance"]["status"] == "PASS"


def test_m13_report_records_scope_and_result() -> None:
    report_records("M13_PREFLIGHT", "W6-01", "W6-06", "M12 freeze")
    report_records("M13_ACCEPTANCE", "W6-01 ～ W6-06", "M13 Final Acceptance = PASS",
                   "M14 Game UI P1")
