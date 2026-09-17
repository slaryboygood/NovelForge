"""M11-RUN-10：Production Execution — Auto Safe Frontier through Batch 15。

**M11 Production Execution**（不是 P15 Repair System Development）：

- 复用 M11-RUN-01..09 的 production pipeline（scope freeze → per-target preflight →
  `REPAIR_GATE_V1` → promotion → lineage → overlay / readiness / backlog 更新）；
- Batch 01–14 已全部 BLOCKED，本轮 scope 只含 **Batch 15**；
- 执行中新解锁的 target 只更新 readiness，**不在本轮执行**（留给 M11-RUN-11）；
- blocked target（本轮 7 个全部为 content design）只作 read-only context；
  不进入 Batch 16、不处理 blocker lanes、不进入 M12；
- 继续执行 production isolation invariant
  **P15_EXECUTOR_READ_ONLY_AFTER_CLOSEOUT**（P15 executor 只读）。

产物：`workspace/wasteland_001_exports/repair_adoption_v1/m11_run_10/`+
design_dir 根 `REPAIR_BATCH_15_EXECUTION_SCOPE`（+ 兼容名）· `M11_RUN_10_RECONCILIATION`。
"""

from __future__ import annotations

from novelforge.story_engine.m11_run01 import M11Run01Service

RUN_ID = "M11_RUN_10"
RUN_DIR = "m11_run_10"
RUN_RECONCILIATION = f"{RUN_ID}_RECONCILIATION.json"
BATCH_15 = "REPAIR_BATCH_15"
FRONTIER_MAX_BATCH = BATCH_15
BATCH_15_SCOPE_FILE = f"{BATCH_15}_EXECUTION_SCOPE.json"
BATCH_15_SCOPE_COMPAT_FILE = "BATCH_15_EXECUTION_SCOPE.json"


class M11Run10Service(M11Run01Service):
    """M11-RUN-10：Batch 15 的 Auto Safe Frontier 执行（Batch 01–14 全 BLOCKED）。"""

    run_id = RUN_ID
    run_dir_name = RUN_DIR
    phase_label = "M11-RUN-10"
    residual_batch_id = "REPAIR_BATCH_04"
    frontier_batch_id = BATCH_15
    max_batch_id = FRONTIER_MAX_BATCH
    residual_key = "batch_04"
    frontier_key = "batch_15"
    next_batch_id = "REPAIR_BATCH_16"
    next_batch_key = "batch_16"
    next_batch_compact = "batch16"
    frontier_scope_file = BATCH_15_SCOPE_FILE
    frontier_scope_compat_file = BATCH_15_SCOPE_COMPAT_FILE
    reconciliation_file = RUN_RECONCILIATION
    next_phase_hint = "M11-RUN-11（AUTO_SAFE_BATCH）或 blocker lane（content rewrite / manual）"
    baseline_readiness_key = "run09_baseline"
    baseline_match_key = "matches_run09_baseline"
    design_item_prefix = "CDQ_RUN10"


__all__ = [
    "BATCH_15",
    "BATCH_15_SCOPE_COMPAT_FILE",
    "BATCH_15_SCOPE_FILE",
    "FRONTIER_MAX_BATCH",
    "M11Run10Service",
    "RUN_DIR",
    "RUN_ID",
    "RUN_RECONCILIATION",
]
