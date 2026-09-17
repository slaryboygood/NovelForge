"""M11-RUN-03：Production Execution — Auto Safe Frontier through Batch 08。

**M11 Production Execution**（不是 P15 Repair System Development）：

- 复用 M11-RUN-01/RUN-02 的 production pipeline（scope freeze → per-target preflight →
  `REPAIR_GATE_V1` → promotion → lineage → overlay / readiness / backlog 更新）；
- 只执行 baseline 时 readiness V2 标记 READY 的 target（Batch 04 residual + Batch 08）；
- 执行中新解锁的 target 只更新 readiness，**不在本轮执行**（留给 M11-RUN-04）；
- blocked target 只作 read-only context；不进入 Batch 09、不处理 author / manual / entity、
  不进入 M12；
- 本轮新增 production invariant **P15_EXECUTOR_READ_ONLY_AFTER_CLOSEOUT**：
  P15 executor 在 closeout 后只读（不得创建 candidate / repaired artifact / overlay
  resolution，production CDQ item 的 ownership 属于 M11 production run）。

产物：`workspace/wasteland_001_exports/repair_adoption_v1/m11_run_03/`
（baseline · execution scope · Batch04 preflight/execution · Batch08 execution ·
dependency closure · acceptance contracts · P15 isolation invariant · gate · summary）+
design_dir 根 `REPAIR_BATCH_08_EXECUTION_SCOPE`（+ 兼容名）· `M11_RUN_03_RECONCILIATION`。
"""

from __future__ import annotations

from novelforge.story_engine.m11_run01 import (
    BATCH_04,
    M11Run01Service,
)

RUN_ID = "M11_RUN_03"
RUN_DIR = "m11_run_03"
RUN_RECONCILIATION = f"{RUN_ID}_RECONCILIATION.json"
BATCH_08 = "REPAIR_BATCH_08"
FRONTIER_MAX_BATCH = BATCH_08
BATCH_08_SCOPE_FILE = f"{BATCH_08}_EXECUTION_SCOPE.json"
BATCH_08_SCOPE_COMPAT_FILE = "BATCH_08_EXECUTION_SCOPE.json"


class M11Run03Service(M11Run01Service):
    """M11-RUN-03：Batch 04 residual + Batch 08 的 Auto Safe Frontier 执行。"""

    run_id = RUN_ID
    run_dir_name = RUN_DIR
    phase_label = "M11-RUN-03"
    residual_batch_id = BATCH_04
    frontier_batch_id = BATCH_08
    max_batch_id = FRONTIER_MAX_BATCH
    residual_key = "batch_04"
    frontier_key = "batch_08"
    next_batch_id = "REPAIR_BATCH_09"
    next_batch_key = "batch_09"
    next_batch_compact = "batch09"
    frontier_scope_file = BATCH_08_SCOPE_FILE
    frontier_scope_compat_file = BATCH_08_SCOPE_COMPAT_FILE
    reconciliation_file = RUN_RECONCILIATION
    next_phase_hint = "M11-RUN-04（AUTO_SAFE_BATCH）或 author/entity/manual/content lane"
    baseline_readiness_key = "run02_baseline"
    baseline_match_key = "matches_run02_baseline"
    design_item_prefix = "CDQ_RUN03"


__all__ = [
    "BATCH_08",
    "BATCH_08_SCOPE_COMPAT_FILE",
    "BATCH_08_SCOPE_FILE",
    "FRONTIER_MAX_BATCH",
    "M11Run03Service",
    "RUN_DIR",
    "RUN_ID",
    "RUN_RECONCILIATION",
]
