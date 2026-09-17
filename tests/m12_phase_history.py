"""M12 phase 历史证据 helper（复用 phase_history 通用能力，不复制实现）。

M12 phase 产物同样 write-once：历史断言读 `phase_snapshots/M12_*`，
live 断言才读 `workspace/.../m12/*.json`。
"""

from __future__ import annotations

from phase_history import (  # noqa: F401  (M12 测试统一从这里 import)
    ROOT,
    assert_doc_records,
    closed,
    load_current_state,
    load_phase_snapshot,
    load_snapshot_manifest,
    phase,
    snapshot_exists,
    verify_phase_snapshot,
    write_phase_snapshot,
)

M12_PHASE_REPORTS: dict[str, str] = {
    "M12_PREFLIGHT": "docs/WASTELAND_001_M12_ACCEPTANCE_REPORT.md",
    "M12_FULL_BOOK_AUDIT": "docs/WASTELAND_001_M12_ACCEPTANCE_REPORT.md",
    "M12_SAMPLE_REVIEW": "docs/WASTELAND_001_M12_ACCEPTANCE_REPORT.md",
    "M12_ACCEPTANCE": "docs/WASTELAND_001_M12_ACCEPTANCE_REPORT.md",
}

PHASE_IDS: tuple[str, ...] = (
    "M12_PREFLIGHT", "M12_FULL_BOOK_AUDIT", "M12_SAMPLE_REVIEW", "M12_ACCEPTANCE")


def report_records(phase_id: str, *needles: str) -> None:
    """M12 历史值必须仍被 freeze / acceptance 报告记录。"""

    assert_doc_records(M12_PHASE_REPORTS[phase_id], *needles, label=phase_id)
