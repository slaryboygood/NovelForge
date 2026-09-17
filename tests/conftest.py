from __future__ import annotations

import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


# ---------------------------------------------------------------------------
# Historical V2 acceptance isolation
#
# M11–M18 / wasteland 里程碑验收是在开发机上跑的：它们读取本机历史验收数据
# （novel/authoring/story_engine、wasteland_001 forge chain、gitignored workspace 产物）。
# 这些数据不属于产品仓库内容，因此这些测试默认不运行（见 pytest.ini），
# 需要时显式运行：pytest -m historical_acceptance
#
# 判定依据（2026-09-17 cleanup）：在「只保留版本控制内容」的等价环境里跑默认 suite，
# 失败集合精确等于下面这些文件；V2 Frozen Guard 与全部当前产品测试保持默认运行。
# ---------------------------------------------------------------------------
HISTORICAL_ACCEPTANCE_FILES = frozenset({
    "test_historical_adoption.py",
    "test_historical_ir_foundation.py",
    "test_m11_approved_event_execution.py",
    "test_m11_author_content_01.py",
    "test_m11_auto_safe_sweep_closeout.py",
    "test_m11_batch04.py",
    "test_m11_batch05.py",
    "test_m11_blocker00.py",
    "test_m11_blocker00a.py",
    "test_m11_content_design_01.py",
    "test_m11_content_rewrite.py",
    "test_m11_design.py",
    "test_m11_final_closure.py",
    "test_m11_micro_pilot.py",
    "test_m11_micro_wave.py",
    "test_m11_p15o.py",
    "test_m11_p15p.py",
    "test_m11_phase_snapshot.py",
    "test_m11_readiness_v2.py",
    "test_m11_run01.py",
    "test_m11_run02.py",
    "test_m11_run03.py",
    "test_m11_run04.py",
    "test_m11_run05.py",
    "test_m11_run06.py",
    "test_m11_run07.py",
    "test_m11_run08.py",
    "test_m11_run09.py",
    "test_m11_run10.py",
    "test_m11_run11.py",
    "test_m11_run12.py",
    "test_m12_acceptance.py",
    "test_m12_full_book_audit.py",
    "test_m12_preflight.py",
    "test_m12_sample_review.py",
    "test_m13_acceptance.py",
    "test_m13_game_ui_p0.py",
    "test_m14_acceptance.py",
    "test_m14_game_ui_p1.py",
    "test_m15_acceptance.py",
    "test_m15_canon_inspector.py",
    "test_m16_acceptance.py",
    "test_m16a_planning_export.py",
    "test_m16b_writer_integration.py",
    "test_m17_acceptance.py",
    "test_m17_cross_genre_e2e.py",
    "test_m18_final_acceptance.py",
    "test_wasteland_reconstruction.py",
    "test_wasteland_repair_batch01.py",
    "test_wasteland_repair_batch02.py",
    "test_wasteland_repair_batch03.py",
    "test_wasteland_repair_policy.py",
})


def pytest_collection_modifyitems(config, items):
    """把历史里程碑验收标记出来（供 `-m historical_acceptance` 选择/排除）。"""

    for item in items:
        if Path(str(item.fspath)).name in HISTORICAL_ACCEPTANCE_FILES:
            item.add_marker(pytest.mark.historical_acceptance)
