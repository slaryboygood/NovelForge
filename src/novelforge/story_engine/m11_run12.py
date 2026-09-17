"""M11-RUN-12：Production Execution — Auto Safe Frontier through Batch 17。

**M11 Production Execution**（不是 P15 Repair System Development；M11 Blocker
Resolution Layer 仍为 planning only，本轮不实现、不执行）：

- 这是当前**最终计划 AUTO_SAFE frontier run**：Batch 17 是 readiness 中最后一个
  AUTO_SAFE batch（总共 17 batch，不存在 Batch 18）；
- 复用 M11-RUN-01..11 的 production pipeline（scope freeze → per-target preflight →
  `REPAIR_GATE_V1` → promotion → lineage → overlay / readiness / backlog 更新）；
- 本轮 scope 只含 **Batch 17** readiness 中 baseline closure-proven 的 READY subset；
  baseline blocked target 只作 read-only context（不得顺手修 manual blocker）；
- 执行中新解锁的 target 只更新 readiness，**不在本轮执行**；是否需要 residual
  AUTO_SAFE 交由 M11-AUTO-SAFE-SWEEP-CLOSEOUT 统一判断，不自动创建 RUN-13；
- 不进入 M11-AUTO-SAFE-SWEEP-CLOSEOUT / M11-BLOCKER-00 / blocker lane / M12；
- 继续执行 production isolation invariant
  **P15_EXECUTOR_READ_ONLY_AFTER_CLOSEOUT**（P15 executor 只读）。

产物：`workspace/wasteland_001_exports/repair_adoption_v1/m11_run_12/`+
design_dir 根 `REPAIR_BATCH_17_EXECUTION_SCOPE`（+ 兼容名）· `M11_RUN_12_RECONCILIATION`。
"""

from __future__ import annotations

from novelforge.story_engine.m11_run01 import M11Run01Service

RUN_ID = "M11_RUN_12"
RUN_DIR = "m11_run_12"
RUN_RECONCILIATION = f"{RUN_ID}_RECONCILIATION.json"
BATCH_17 = "REPAIR_BATCH_17"
FRONTIER_MAX_BATCH = BATCH_17
BATCH_17_SCOPE_FILE = f"{BATCH_17}_EXECUTION_SCOPE.json"
BATCH_17_SCOPE_COMPAT_FILE = "BATCH_17_EXECUTION_SCOPE.json"
# Batch 18 不存在（17 batch 已全部进入执行）；该 id 仅用于 "no hidden Batch18" 防护，
# gate 的 batch18_not_entered 在 readiness 中查不到该 batch 时恒为 True。
NEXT_BATCH_ID = "REPAIR_BATCH_18"


class M11Run12Service(M11Run01Service):
    """M11-RUN-12：Batch 17 的 Auto Safe Frontier 执行（最终计划 frontier）。"""

    run_id = RUN_ID
    run_dir_name = RUN_DIR
    phase_label = "M11-RUN-12"
    residual_batch_id = "REPAIR_BATCH_04"
    frontier_batch_id = BATCH_17
    max_batch_id = FRONTIER_MAX_BATCH
    residual_key = "batch_04"
    frontier_key = "batch_17"
    next_batch_id = NEXT_BATCH_ID
    next_batch_key = "batch_18"
    next_batch_compact = "batch18"
    frontier_scope_file = BATCH_17_SCOPE_FILE
    frontier_scope_compat_file = BATCH_17_SCOPE_COMPAT_FILE
    reconciliation_file = RUN_RECONCILIATION
    next_phase_hint = ("M11-AUTO-SAFE-SWEEP-CLOSEOUT → M11-BLOCKER-00"
                       "（blocker layer 仍 planning only）")
    baseline_readiness_key = "run11_baseline"
    baseline_match_key = "matches_run11_baseline"
    design_item_prefix = "CDQ_RUN12"
    # §8：ContentDesignQueue V2/V3 lifecycle 审计（ID-level reconciliation）：
    # before = RUN-11 结束时的 V2 集合；added = RUN-12 新登记的 production CDQ。
    queue_lifecycle_audit = ("M11_RUN_11", ("M11_RUN_12",))


__all__ = [
    "BATCH_17",
    "BATCH_17_SCOPE_COMPAT_FILE",
    "BATCH_17_SCOPE_FILE",
    "FRONTIER_MAX_BATCH",
    "M11Run12Service",
    "NEXT_BATCH_ID",
    "RUN_DIR",
    "RUN_ID",
    "RUN_RECONCILIATION",
]
