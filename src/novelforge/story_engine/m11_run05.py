"""M11-RUN-05：Production Execution — Auto Safe Frontier through Batch 10。

**M11 Production Execution**（不是 P15 Repair System Development）：

- 复用 M11-RUN-01..04 的 production pipeline（scope freeze → per-target preflight →
  `REPAIR_GATE_V1` → promotion → lineage → overlay / readiness / backlog 更新）；
- 只执行 baseline 时 readiness V2 标记 READY 的 target（Batch 04 residual + Batch 10）；
- 执行中新解锁的 target 只更新 readiness，**不在本轮执行**（留给 M11-RUN-06）；
- blocked target 只作 read-only context；不进入 Batch 11、不处理 author / entity / manual、
  不进入 M12；纯 AUTO_SAFE run；
- 继续执行 production isolation invariant
  **P15_EXECUTOR_READ_ONLY_AFTER_CLOSEOUT**（P15 executor 只读）。

产物：`workspace/wasteland_001_exports/repair_adoption_v1/m11_run_05/`（baseline ·
execution scope · Batch04 preflight/execution · Batch10 execution · dependency closure ·
acceptance contracts · P15 isolation invariant · gate · summary）+
design_dir 根 `REPAIR_BATCH_10_EXECUTION_SCOPE`（+ 兼容名）· `M11_RUN_05_RECONCILIATION`。
"""

from __future__ import annotations

from novelforge.story_engine.m11_run01 import (
    BATCH_04,
    M11Run01Service,
)

RUN_ID = "M11_RUN_05"
RUN_DIR = "m11_run_05"
RUN_RECONCILIATION = f"{RUN_ID}_RECONCILIATION.json"
BATCH_10 = "REPAIR_BATCH_10"
FRONTIER_MAX_BATCH = BATCH_10
BATCH_10_SCOPE_FILE = f"{BATCH_10}_EXECUTION_SCOPE.json"
BATCH_10_SCOPE_COMPAT_FILE = "BATCH_10_EXECUTION_SCOPE.json"


class M11Run05Service(M11Run01Service):
    """M11-RUN-05：Batch 04 residual + Batch 10 的 Auto Safe Frontier 执行。"""

    run_id = RUN_ID
    run_dir_name = RUN_DIR
    phase_label = "M11-RUN-05"
    residual_batch_id = BATCH_04
    frontier_batch_id = BATCH_10
    max_batch_id = FRONTIER_MAX_BATCH
    residual_key = "batch_04"
    frontier_key = "batch_10"
    next_batch_id = "REPAIR_BATCH_11"
    next_batch_key = "batch_11"
    next_batch_compact = "batch11"
    frontier_scope_file = BATCH_10_SCOPE_FILE
    frontier_scope_compat_file = BATCH_10_SCOPE_COMPAT_FILE
    reconciliation_file = RUN_RECONCILIATION
    next_phase_hint = "M11-RUN-06（AUTO_SAFE_BATCH）或 blocker lane（entity / author / manual）"
    baseline_readiness_key = "run04_baseline"
    baseline_match_key = "matches_run04_baseline"
    design_item_prefix = "CDQ_RUN05"


__all__ = [
    "BATCH_10",
    "BATCH_10_SCOPE_COMPAT_FILE",
    "BATCH_10_SCOPE_FILE",
    "FRONTIER_MAX_BATCH",
    "M11Run05Service",
    "RUN_DIR",
    "RUN_ID",
    "RUN_RECONCILIATION",
]
