"""M11-RUN-02：Production Execution — Auto Safe Frontier（Batch 04 residual + Batch 07）。

这是 **M11 Production Execution**，不是 P15 Repair System Development：

- 复用 M11-RUN-01 冻结的 production pipeline（scope freeze → per-target preflight →
  `REPAIR_GATE_V1` → promotion → lineage → overlay / readiness / backlog 更新）；
- 只执行 baseline 时 readiness V2 标记 READY 的 target（Batch 04 residual + Batch 07）；
- 执行中由 upstream 释放的新 target 只更新 readiness，**不在本轮执行**（留给 M11-RUN-03）；
- blocked target 只作 read-only context；不处理 author policy / author content /
  major design / manual / entity；不进入 Batch 08、不进入 M12；
- 不新增 repair class / gate / readiness / overlay semantics。

产物（`workspace/wasteland_001_exports/repair_adoption_v1/`）：

- `m11_run_02/`：`M11_RUN_02_BASELINE` · `M11_RUN_02_EXECUTION_SCOPE` ·
  `M11_RUN_02_BATCH04_PREFLIGHT` · `M11_RUN_02_BATCH04_EXECUTION` ·
  `M11_RUN_02_BATCH07_EXECUTION` · `REPAIR_BATCH_04_DEPENDENCY_CLOSURE` ·
  `REPAIR_BATCH_07_DEPENDENCY_CLOSURE` ·
  `M11_RUN_02_BATCH_04_ACCEPTANCE_CONTRACT` ·
  `M11_RUN_02_BATCH_07_ACCEPTANCE_CONTRACT` · `M11_RUN_02_GATE` · `M11_RUN_02_SUMMARY`
- design_dir 根：`REPAIR_BATCH_07_EXECUTION_SCOPE`（+ `BATCH_07_EXECUTION_SCOPE` 兼容名）·
  `M11_RUN_02_RECONCILIATION`
"""

from __future__ import annotations

from novelforge.story_engine.m11_run01 import (
    BATCH_04,
    M11Run01Service,
)

RUN_ID = "M11_RUN_02"
RUN_DIR = "m11_run_02"
RUN_RECONCILIATION = f"{RUN_ID}_RECONCILIATION.json"
BATCH_07 = "REPAIR_BATCH_07"
FRONTIER_MAX_BATCH = BATCH_07
BATCH_07_SCOPE_FILE = f"{BATCH_07}_EXECUTION_SCOPE.json"
BATCH_07_SCOPE_COMPAT_FILE = "BATCH_07_EXECUTION_SCOPE.json"


class M11Run02Service(M11Run01Service):
    """M11-RUN-02：Batch 04 residual + Batch 07 的 Auto Safe Frontier 执行。"""

    run_id = RUN_ID
    run_dir_name = RUN_DIR
    phase_label = "M11-RUN-02"
    residual_batch_id = BATCH_04
    frontier_batch_id = BATCH_07
    max_batch_id = FRONTIER_MAX_BATCH
    residual_key = "batch_04"
    frontier_key = "batch_07"
    next_batch_id = "REPAIR_BATCH_08"
    next_batch_key = "batch_08"
    next_batch_compact = "batch08"
    frontier_scope_file = BATCH_07_SCOPE_FILE
    frontier_scope_compat_file = BATCH_07_SCOPE_COMPAT_FILE
    reconciliation_file = RUN_RECONCILIATION
    next_phase_hint = ("M11-RUN-03（AUTO_SAFE_BATCH）或 author/manual/entity 决策")
    baseline_readiness_key = "run01_baseline"
    baseline_match_key = "matches_run01_baseline"
    design_item_prefix = "CDQ_RUN02"


__all__ = [
    "BATCH_07",
    "BATCH_07_SCOPE_COMPAT_FILE",
    "BATCH_07_SCOPE_FILE",
    "FRONTIER_MAX_BATCH",
    "M11Run02Service",
    "RUN_DIR",
    "RUN_ID",
    "RUN_RECONCILIATION",
]
