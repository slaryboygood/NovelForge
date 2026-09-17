"""M11-RUN-11：Production Execution — Auto Safe Frontier through Batch 16。

**M11 Production Execution**（不是 P15 Repair System Development；M11 Blocker
Resolution Layer 仍为 planning only，本轮不实现、不执行）：

- 复用 M11-RUN-01..10 的 production pipeline（scope freeze → per-target preflight →
  `REPAIR_GATE_V1` → promotion → lineage → overlay / readiness / backlog 更新）；
- Batch 01–15 已全部 BLOCKED，本轮 scope 只含 **Batch 16** readiness 中
  baseline closure-proven 的 READY subset；
- 执行中新解锁的 target 只更新 readiness，**不在本轮执行**（留给 M11-RUN-12）；
- blocked target 只作 read-only context；不进入 Batch 17、不执行 blocker lane、
  不进入 M12；
- 继续执行 production isolation invariant
  **P15_EXECUTOR_READ_ONLY_AFTER_CLOSEOUT**（P15 executor 只读）。

产物：`workspace/wasteland_001_exports/repair_adoption_v1/m11_run_11/`+
design_dir 根 `REPAIR_BATCH_16_EXECUTION_SCOPE`（+ 兼容名）· `M11_RUN_11_RECONCILIATION`。
"""

from __future__ import annotations

from novelforge.story_engine.m11_run01 import M11Run01Service

RUN_ID = "M11_RUN_11"
RUN_DIR = "m11_run_11"
RUN_RECONCILIATION = f"{RUN_ID}_RECONCILIATION.json"
BATCH_16 = "REPAIR_BATCH_16"
FRONTIER_MAX_BATCH = BATCH_16
BATCH_16_SCOPE_FILE = f"{BATCH_16}_EXECUTION_SCOPE.json"
BATCH_16_SCOPE_COMPAT_FILE = "BATCH_16_EXECUTION_SCOPE.json"


class M11Run11Service(M11Run01Service):
    """M11-RUN-11：Batch 16 的 Auto Safe Frontier 执行（Batch 01–15 全 BLOCKED）。"""

    run_id = RUN_ID
    run_dir_name = RUN_DIR
    phase_label = "M11-RUN-11"
    residual_batch_id = "REPAIR_BATCH_04"
    frontier_batch_id = BATCH_16
    max_batch_id = FRONTIER_MAX_BATCH
    residual_key = "batch_04"
    frontier_key = "batch_16"
    next_batch_id = "REPAIR_BATCH_17"
    next_batch_key = "batch_17"
    next_batch_compact = "batch17"
    frontier_scope_file = BATCH_16_SCOPE_FILE
    frontier_scope_compat_file = BATCH_16_SCOPE_COMPAT_FILE
    reconciliation_file = RUN_RECONCILIATION
    next_phase_hint = ("M11-RUN-12（AUTO_SAFE_BATCH）或 "
                       "M11-AUTO-SAFE-SWEEP-CLOSEOUT → M11-BLOCKER-00")
    baseline_readiness_key = "run10_baseline"
    baseline_match_key = "matches_run10_baseline"
    design_item_prefix = "CDQ_RUN11"
    # §7：ContentDesignQueue V2/V3 lifecycle 审计（ID-level reconciliation）：
    # before = RUN-10 结束时的 V2 集合；added = RUN-11 新登记的 production CDQ。
    queue_lifecycle_audit = ("M11_RUN_10", ("M11_RUN_11",))


__all__ = [
    "BATCH_16",
    "BATCH_16_SCOPE_COMPAT_FILE",
    "BATCH_16_SCOPE_FILE",
    "FRONTIER_MAX_BATCH",
    "M11Run11Service",
    "RUN_DIR",
    "RUN_ID",
    "RUN_RECONCILIATION",
]
