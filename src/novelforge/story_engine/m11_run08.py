"""M11-RUN-08：Production Execution — Auto Safe Frontier through Batch 13。

**M11 Production Execution**（不是 P15 Repair System Development）：

- 复用 M11-RUN-01..07 的 production pipeline（scope freeze → per-target preflight →
  `REPAIR_GATE_V1` → promotion → lineage → overlay / readiness / backlog 更新）；
- Batch 01–12 已全部 BLOCKED，本轮 scope 只含 **Batch 13**；
- 执行中新解锁的 target 只更新 readiness，**不在本轮执行**（留给 M11-RUN-09）；
- blocked target 只作 read-only context；不进入 Batch 14、不处理 blocker lanes、不进入 M12；
- 继续执行 production isolation invariant
  **P15_EXECUTOR_READ_ONLY_AFTER_CLOSEOUT**（P15 executor 只读）；
- FIELD_REBIND 只有自然出现且全部 gate 真实 PASS 时才能成为 production proof
  （本轮 `ch425`/`ch445` 为 HIGH risk → 诚实 MANUAL 降级，capability 保持 NOT_PROVEN）。

产物：`workspace/wasteland_001_exports/repair_adoption_v1/m11_run_08/`+
design_dir 根 `REPAIR_BATCH_13_EXECUTION_SCOPE`（+ 兼容名）· `M11_RUN_08_RECONCILIATION`。
"""

from __future__ import annotations

from novelforge.story_engine.m11_run01 import M11Run01Service

RUN_ID = "M11_RUN_08"
RUN_DIR = "m11_run_08"
RUN_RECONCILIATION = f"{RUN_ID}_RECONCILIATION.json"
BATCH_13 = "REPAIR_BATCH_13"
FRONTIER_MAX_BATCH = BATCH_13
BATCH_13_SCOPE_FILE = f"{BATCH_13}_EXECUTION_SCOPE.json"
BATCH_13_SCOPE_COMPAT_FILE = "BATCH_13_EXECUTION_SCOPE.json"


class M11Run08Service(M11Run01Service):
    """M11-RUN-08：Batch 13 的 Auto Safe Frontier 执行（Batch 01–12 全 BLOCKED）。"""

    run_id = RUN_ID
    run_dir_name = RUN_DIR
    phase_label = "M11-RUN-08"
    residual_batch_id = "REPAIR_BATCH_04"
    frontier_batch_id = BATCH_13
    max_batch_id = FRONTIER_MAX_BATCH
    residual_key = "batch_04"
    frontier_key = "batch_13"
    next_batch_id = "REPAIR_BATCH_14"
    next_batch_key = "batch_14"
    next_batch_compact = "batch14"
    frontier_scope_file = BATCH_13_SCOPE_FILE
    frontier_scope_compat_file = BATCH_13_SCOPE_COMPAT_FILE
    reconciliation_file = RUN_RECONCILIATION
    next_phase_hint = "M11-RUN-09（AUTO_SAFE_BATCH）或 blocker lane（entity / manual / author）"
    baseline_readiness_key = "run07_baseline"
    baseline_match_key = "matches_run07_baseline"
    design_item_prefix = "CDQ_RUN08"


__all__ = [
    "BATCH_13",
    "BATCH_13_SCOPE_COMPAT_FILE",
    "BATCH_13_SCOPE_FILE",
    "FRONTIER_MAX_BATCH",
    "M11Run08Service",
    "RUN_DIR",
    "RUN_ID",
    "RUN_RECONCILIATION",
]
