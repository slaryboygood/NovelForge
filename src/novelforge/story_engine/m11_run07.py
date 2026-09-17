"""M11-RUN-07：Production Execution — Auto Safe Frontier through Batch 12。

**M11 Production Execution**（不是 P15 Repair System Development）：

- 复用 M11-RUN-01..06 的 production pipeline（scope freeze → per-target preflight →
  `REPAIR_GATE_V1` → promotion → lineage → overlay / readiness / backlog 更新）；
- 本轮 Batch 04 已 BLOCKED（无 residual READY），因此 scope 只含 **Batch 12**；
- 执行中新解锁的 target 只更新 readiness，**不在本轮执行**（留给 M11-RUN-08）；
- blocked target 只作 read-only context；不进入 Batch 13、不处理 blocker lanes、不进入 M12；
- 本轮额外执行 **ContentDesignQueue lifecycle 审计**（RUN-05 → RUN-06 delta 可审计
  reconciliation，用于核对报告中的 58 → 56 说法）；
- 继续执行 production isolation invariant
  **P15_EXECUTOR_READ_ONLY_AFTER_CLOSEOUT**（P15 executor 只读）。

产物：`workspace/wasteland_001_exports/repair_adoption_v1/m11_run_07/`（baseline ·
execution scope · Batch12 execution · dependency closure · acceptance contracts ·
queue lifecycle audit · P15 isolation invariant · gate · summary）+
design_dir 根 `REPAIR_BATCH_12_EXECUTION_SCOPE`（+ 兼容名）· `M11_RUN_07_RECONCILIATION`。
"""

from __future__ import annotations

from novelforge.story_engine.m11_run01 import M11Run01Service

RUN_ID = "M11_RUN_07"
RUN_DIR = "m11_run_07"
RUN_RECONCILIATION = f"{RUN_ID}_RECONCILIATION.json"
BATCH_12 = "REPAIR_BATCH_12"
FRONTIER_MAX_BATCH = BATCH_12
BATCH_12_SCOPE_FILE = f"{BATCH_12}_EXECUTION_SCOPE.json"
BATCH_12_SCOPE_COMPAT_FILE = "BATCH_12_EXECUTION_SCOPE.json"


class M11Run07Service(M11Run01Service):
    """M11-RUN-07：Batch 12 的 Auto Safe Frontier 执行（Batch 04 已 BLOCKED）。"""

    run_id = RUN_ID
    run_dir_name = RUN_DIR
    phase_label = "M11-RUN-07"
    residual_batch_id = "REPAIR_BATCH_04"
    frontier_batch_id = BATCH_12
    max_batch_id = FRONTIER_MAX_BATCH
    residual_key = "batch_04"
    frontier_key = "batch_12"
    next_batch_id = "REPAIR_BATCH_13"
    next_batch_key = "batch_13"
    next_batch_compact = "batch13"
    frontier_scope_file = BATCH_12_SCOPE_FILE
    frontier_scope_compat_file = BATCH_12_SCOPE_COMPAT_FILE
    reconciliation_file = RUN_RECONCILIATION
    next_phase_hint = "M11-RUN-08（AUTO_SAFE_BATCH）或 blocker lane（entity / author / manual）"
    baseline_readiness_key = "run06_baseline"
    baseline_match_key = "matches_run06_baseline"
    design_item_prefix = "CDQ_RUN07"
    # §4：审计 RUN-05 → RUN-06 的 ContentDesignQueue lifecycle delta
    queue_lifecycle_audit = ("M11_RUN_05", ("M11_RUN_06",))


__all__ = [
    "BATCH_12",
    "BATCH_12_SCOPE_COMPAT_FILE",
    "BATCH_12_SCOPE_FILE",
    "FRONTIER_MAX_BATCH",
    "M11Run07Service",
    "RUN_DIR",
    "RUN_ID",
    "RUN_RECONCILIATION",
]
