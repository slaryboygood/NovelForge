"""NovelForge `quality` —— Quality Closed Loop & Targeted Repair（V4-05）。

Public Contract（**刻意保持精简**，§6 / §79）：

```text
QualityService / quality_service     唯一评估入口（逐 gate，deterministic first）
QualityScope / QualityEvidence       评估范围与一等证据
QualityIssue / QualityGateResult     结构化问题与逐 gate 结果
QualityReport / QualityPolicy        report 与生产策略（策略不写死在 evaluator）
QualityStatus / Severity / decide_status  固定语义（PASS/FAIL 不是平均分）
EvaluatorRegistry / EvaluatorSpec     evaluator 注册表（不硬编码 if gate == ...）
CODE_REGISTRY / code_spec / codes_for_gate / is_registered  稳定 issue code registry
QualityStore                          quality truth（独立于 story truth）
RepairPlanner / RepairExecutor / RepairVerifier  最小范围、可验证的定向修复
RepairContract / RepairPlan / RepairResult / VerificationResult
QualityError 家族
```

内部实现（`quality/evaluators/*`、`quality/aggregation.py`、`quality/repair/*` 的实现细节）
不全部公开：接口层只允许依赖本 `__init__` 导出的符号。

边界（§68）：

```text
quality      → blueprint / memory / ai / core / persistence.paths / domain public contract
quality.repair → generation Public Contract（只允许这一个方向）
禁止         → ai / memory / blueprint / generation / domain 反向 import quality
禁止         → quality import interfaces(api) / ai.providers / HTTP client / 自行拼路径
```

三条铁律：

```text
Quality 评估是只读的（不修改 Blueprint / Canon / StoryState）
Quality Store 是 quality truth，不是 story truth
修复必须产生新 revision；accepted 节点不被静默覆盖
```
"""

from .aggregation import (
    build_usage,
    empty_usage,
    group_by_gate,
    merge_issues,
    merge_usage,
    normalize_usage,
    summarize_gates,
    summarize_report,
    usage_totals,
)
from .codes import (
    CODE_REGISTRY,
    ISSUE_CODES,
    IssueCodeSpec,
    code_spec,
    codes_for_gate,
    is_registered,
)
from .contracts import (
    GATES,
    ISSUE_STATUSES,
    QUALITY_SCHEMA_VERSION,
    QUALITY_STATUSES,
    SEVERITIES,
    SEVERITY_ORDER,
    QualityEvidence,
    QualityGateResult,
    QualityIssue,
    QualityPolicy,
    QualityReport,
    QualityScope,
    decide_status,
    issue_id_for,
    make_issue,
    utc_now,
)
from .errors import (
    QualityError,
    QualityPolicyError,
    QualityScopeError,
    RepairConflictError,
    RepairNotAllowedError,
    RepairPlanError,
    RepairRoundLimitError,
)
from .registry import (
    EvaluatorRegistry,
    EvaluatorSpec,
    build_default_registry,
)
from .repair import (
    RepairBlastRadius,
    RepairContract,
    RepairExecutor,
    RepairPlan,
    RepairPlanner,
    RepairResult,
    RepairStep,
    RepairVerifier,
    VerificationResult,
)
from .service import QualityService, quality_service
from .store import QualityStore

__all__ = [
    # service
    "QualityService", "quality_service", "QualityStore",
    # contracts
    "GATES", "ISSUE_STATUSES", "QUALITY_SCHEMA_VERSION", "QUALITY_STATUSES",
    "SEVERITIES", "SEVERITY_ORDER", "QualityEvidence", "QualityGateResult",
    "QualityIssue", "QualityPolicy", "QualityReport", "QualityScope",
    "decide_status", "issue_id_for", "make_issue", "utc_now",
    # code registry
    "CODE_REGISTRY", "ISSUE_CODES", "IssueCodeSpec", "code_spec",
    "codes_for_gate", "is_registered",
    # registry
    "EvaluatorRegistry", "EvaluatorSpec", "build_default_registry",
    # aggregation
    "build_usage", "empty_usage", "group_by_gate", "merge_issues", "merge_usage",
    "normalize_usage", "summarize_gates", "summarize_report", "usage_totals",
    # repair
    "RepairBlastRadius", "RepairContract", "RepairExecutor", "RepairPlan",
    "RepairPlanner", "RepairResult", "RepairStep", "RepairVerifier",
    "VerificationResult",
    # errors
    "QualityError", "QualityPolicyError", "QualityScopeError",
    "RepairConflictError", "RepairNotAllowedError", "RepairPlanError",
    "RepairRoundLimitError",
]
