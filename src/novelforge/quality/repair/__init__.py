"""Repair 子模块（V4-05 §2、§29–§38）：最小范围、可验证、产生新 revision 的修复。

Public Contract：

```text
RepairPlanner       issues → RepairPlan（不写 revision、不调模型）
RepairBlastRadius   direct / dependent / required verification gates
RepairExecutor      RepairPlan → 新 Blueprint revision（经 generation Public Contract）
RepairVerifier      新 revision → 只复核受影响 gate
RepairContract / RepairStep / RepairPlan / RepairResult / VerificationResult
```

边界（§34）：`quality.repair → quality contracts + blueprint + generation Public Contract
+ core`；**禁止** `generation → quality`。
"""

from .blast_radius import GATE_ORDER, NODE_TYPE_GATES, RepairBlastRadius
from .contracts import (
    PLAN_STATUSES,
    REPAIR_STRATEGIES,
    RESULT_STATUSES,
    VERIFICATION_STATUSES,
    RepairContract,
    RepairPlan,
    RepairResult,
    RepairStep,
    VerificationResult,
)
from .executor import PreserveViolationError, RepairExecutor
from .planner import NODE_TYPE_TASK, RepairPlanner, payload_fields
from .verifier import RepairVerifier

__all__ = [
    "GATE_ORDER", "NODE_TYPE_GATES", "NODE_TYPE_TASK", "PLAN_STATUSES",
    "REPAIR_STRATEGIES", "RESULT_STATUSES", "VERIFICATION_STATUSES",
    "RepairBlastRadius", "RepairContract", "RepairExecutor", "RepairPlan",
    "PreserveViolationError", "RepairPlanner", "RepairResult", "RepairStep",
    "RepairVerifier", "VerificationResult", "payload_fields",
]
