"""M13 phase 历史证据 helper（复用 phase_history 通用能力）。"""

from __future__ import annotations

from phase_history import (  # noqa: F401
    ROOT,
    assert_doc_records,
    closed,
    load_phase_snapshot,
    load_snapshot_manifest,
    phase,
    snapshot_exists,
    verify_phase_snapshot,
    write_phase_snapshot,
)

M13_PHASE_REPORTS: dict[str, str] = {
    "M13_PREFLIGHT": "docs/WASTELAND_001_M13_GAME_UI_P0_REPORT.md",
    "M13_ACCEPTANCE": "docs/WASTELAND_001_M13_GAME_UI_P0_REPORT.md",
}
PHASE_IDS: tuple[str, ...] = ("M13_PREFLIGHT", "M13_ACCEPTANCE")


def report_records(phase_id: str, *needles: str) -> None:
    assert_doc_records(M13_PHASE_REPORTS[phase_id], *needles, label=phase_id)
