"""M11-RUN-06：Production Execution — Auto Safe Frontier through Batch 11。

**M11 Production Execution**（不是 P15 Repair System Development）：

- 复用 M11-RUN-01..05 的 production pipeline（scope freeze → per-target preflight →
  `REPAIR_GATE_V1` → promotion → lineage → overlay / readiness / backlog 更新）；
- 只执行 baseline 时 readiness V2 标记 READY 的 target（Batch 04 residual + Batch 11）；
- 执行中新解锁的 target 只更新 readiness，**不在本轮执行**（留给 M11-RUN-07）；
- blocked target 只作 read-only context；不进入 Batch 12、不处理 author / entity / manual、
  不进入 M12；纯 AUTO_SAFE run；
- 继续执行 production isolation invariant
  **P15_EXECUTOR_READ_ONLY_AFTER_CLOSEOUT**（P15 executor 只读）。

产物：`workspace/wasteland_001_exports/repair_adoption_v1/m11_run_06/`+
design_dir 根 `REPAIR_BATCH_11_EXECUTION_SCOPE`（+ 兼容名）· `M11_RUN_06_RECONCILIATION`。
"""

from __future__ import annotations

from novelforge.story_engine.m11_run01 import (
    BATCH_04,
    M11Run01Service,
)

RUN_ID = "M11_RUN_06"
RUN_DIR = "m11_run_06"
RUN_RECONCILIATION = f"{RUN_ID}_RECONCILIATION.json"
BATCH_11 = "REPAIR_BATCH_11"
FRONTIER_MAX_BATCH = BATCH_11
BATCH_11_SCOPE_FILE = f"{BATCH_11}_EXECUTION_SCOPE.json"
BATCH_11_SCOPE_COMPAT_FILE = "BATCH_11_EXECUTION_SCOPE.json"


class M11Run06Service(M11Run01Service):
    """M11-RUN-06：Batch 04 residual + Batch 11 的 Auto Safe Frontier 执行。"""

    run_id = RUN_ID
    run_dir_name = RUN_DIR
    phase_label = "M11-RUN-06"
    residual_batch_id = BATCH_04
    frontier_batch_id = BATCH_11
    max_batch_id = FRONTIER_MAX_BATCH
    residual_key = "batch_04"
    frontier_key = "batch_11"
    next_batch_id = "REPAIR_BATCH_12"
    next_batch_key = "batch_12"
    next_batch_compact = "batch12"
    frontier_scope_file = BATCH_11_SCOPE_FILE
    frontier_scope_compat_file = BATCH_11_SCOPE_COMPAT_FILE
    reconciliation_file = RUN_RECONCILIATION
    next_phase_hint = "M11-RUN-07（AUTO_SAFE_BATCH）或 blocker lane（entity / author / manual）"
    baseline_readiness_key = "run05_baseline"
    baseline_match_key = "matches_run05_baseline"
    design_item_prefix = "CDQ_RUN06"


__all__ = [
    "BATCH_11",
    "BATCH_11_SCOPE_COMPAT_FILE",
    "BATCH_11_SCOPE_FILE",
    "FRONTIER_MAX_BATCH",
    "M11Run06Service",
    "RUN_DIR",
    "RUN_ID",
    "RUN_RECONCILIATION",
]
