"""M14 Game UI P1 acceptance 回归：scope / freeze guard / acceptance / M15 readiness。"""

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
from novelforge.story_engine.m14_game_ui import (
    ACCEPTANCE_FILE,
    BASELINE_FILE,
    FREEZE_GUARD_FILE,
    M14GameUIService,
    M15_READINESS_FILE,
    W6_EVIDENCE,
    W6_ITEMS,
    w6_p1_scope_from_roadmap,
)

from phase_history import (
    load_phase_snapshot,
    snapshot_exists,
    verify_phase_snapshot,
)

ROOT = Path(".").resolve()
DESIGN_DIR = ROOT / "workspace/wasteland_001_exports/repair_adoption_v1"
M14_DIR = DESIGN_DIR / "m14"


@pytest.fixture(scope="module")
def m14():
    service = M14GameUIService(ROOT)
    preflight = service.run_preflight()
    service.record_test_evidence(
        pytest={"status": "PASS", "summary": "M13/M14 targeted suites passed"},
        validate_project={"status": "PASS"},
        ui_build={"status": "PASS", "summary": "tsc -b && vite build"},
        browser={"status": "PASS",
                 "summary": "tests/browser_m14_game_ui_p1.cjs（W6-07..12 + 390px）"})
    result = service.acceptance()
    return service, preflight, result


def _artifact(name: str) -> dict:
    return json.loads((M14_DIR / name).read_text(encoding="utf-8"))


def test_scope_from_roadmap() -> None:
    rows = w6_p1_scope_from_roadmap(ROOT)
    assert [row["item"] for row in rows] == list(W6_ITEMS)
    for row in rows:
        assert row["title"] and row["content"] and row["note"]
    assert "设定总览卡" in rows[0]["title"]
    assert "moodboard" in rows[5]["title"]


def test_preflight_and_baseline(m14) -> None:
    _service, preflight, _result = m14
    guard = _artifact(FREEZE_GUARD_FILE)
    baseline = _artifact(BASELINE_FILE)
    assert preflight["status"] == "PASS"
    assert guard["status"] == "PASS" and all(guard["checks"].values())
    assert [row["item"] for row in baseline["w6_scope"]] == list(W6_ITEMS)
    assert all(row["evidence"]["files"] for row in baseline["w6_scope"])
    assert baseline["next_milestone_dependency"]["milestone"].startswith("M15")


def test_acceptance_pass(m14) -> None:
    _service, _preflight, result = m14
    acceptance = result["acceptance"]
    assert acceptance["status"] == "PASS"
    assert acceptance["satisfied_count"] == acceptance["criteria_count"] == 6
    assert all(row["satisfied"] for row in acceptance["criteria"])
    assert set(acceptance["w6_status"]) == set(W6_ITEMS)
    assert _artifact(ACCEPTANCE_FILE)["status"] == "PASS"


def test_w6_evidence_files_exist() -> None:
    for item, row in W6_EVIDENCE.items():
        for path in row["files"]:
            assert (ROOT / path).is_file(), f"{item} 缺少实现文件 {path}"
    assert (ROOT / "tests/browser_m14_game_ui_p1.cjs").is_file()
    assert (ROOT / "tests/test_m14_game_ui_p1.py").is_file()


def test_frozen_truth_unchanged(m14) -> None:
    service, _preflight, _result = m14
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


def test_m15_readiness_and_snapshots(m14) -> None:
    _service, _preflight, result = m14
    readiness = result["m15_readiness"]
    assert readiness["m15_entry_allowed"] is True
    assert readiness["m15_executed"] is False
    assert _artifact(M15_READINESS_FILE)["m15_entry_allowed"] is True
    for phase_id in ("M14_PREFLIGHT", "M14_ACCEPTANCE"):
        assert snapshot_exists(phase_id)
        assert verify_phase_snapshot(phase_id)["status"] == "PASS"
    snapshot = load_phase_snapshot("M14_ACCEPTANCE")
    assert snapshot["status"] == "PASS"
    assert snapshot["satisfied_count"] == 6
    assert snapshot["w6_items"] == list(W6_ITEMS)
    assert snapshot["m15_entry_allowed"] is True
