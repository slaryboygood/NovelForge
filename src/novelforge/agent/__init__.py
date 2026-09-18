"""NovelForge `agent` —— Agent Mode / Bounded Autonomous Orchestration（V4-11）。

```text
AGENT_ORCHESTRATES_EXISTING_CAPABILITIES
AGENT_DOES_NOT_REIMPLEMENT_BUSINESS_LOGIC
AGENT_MUTATIONS_ARE_REVISIONED
AGENT_ACTIONS_ARE_IDEMPOTENT
AGENT_AUTONOMY_IS_BOUNDED
AGENT_ACCEPTANCE_REQUIRES_EXPLICIT_POLICY
AGENT_DELIVERY_REQUIRES_EXPLICIT_POLICY
AGENT_ALWAYS_LEAVES_AN_AUDIT_TRAIL
```

Public Contract（精简，§11）：

```text
AgentService 在 application 层（application.services.agent）
AgentGoal / AgentScope / AgentPolicy / AgentPlan / AgentStep / AgentResult
AgentSession（记录）/ AgentRun / AgentCheckpoint / AgentApprovalRequest / Decision
AgentError 家族（稳定 code）
```

Agent core 只依赖 `agent.ports` 的窄 Protocol；底层能力由 application composition 注入。
"""

from .audit import AgentAuditLog, AgentAuditRecord
from .checkpoint import AgentCheckpoint, CheckpointStore
from .contracts import (
    AGENT_SCHEMA_VERSION,
    AGENT_STATUSES,
    AGENT_TRANSITIONS,
    PROTECTED_ACTIONS,
    SCOPE_KINDS,
    STEP_STATUSES,
    AgentApprovalDecision,
    AgentApprovalRequest,
    AgentContextSnapshot,
    AgentGoal,
    AgentPlan,
    AgentPolicy,
    AgentResult,
    AgentRun,
    AgentScope,
    AgentStep,
    AgentStepResult,
)
from .errors import (
    AgentApprovalRequired,
    AgentApprovalStale,
    AgentBudgetExhausted,
    AgentCancelled,
    AgentError,
    AgentMaxStepsReached,
    AgentNeedsHumanReview,
    AgentNotFound,
    AgentPlanInvalid,
    AgentPolicyDenied,
    AgentRevisionConflict,
    AgentStepFailed,
)
from .executor import AgentExecutor, ExecutionOutcome
from .planner import (
    MODEL_PLAN_CONTRACT,
    HeuristicPlanner,
    ModelPlanner,
    default_planner,
    parse_intent,
    validate_plan,
)
from .policy import AgentBudget, check_action_allowed, check_budget, check_scope
from .registry import ACTION_REGISTRY, FORBIDDEN_ACTIONS, action_spec, allowlisted_actions
from .session import AgentSessionRecord, AgentSessionStore
from .verifier import AgentVerifier, VerificationOutcome

__all__ = [
    # contracts
    "AGENT_SCHEMA_VERSION", "AGENT_STATUSES", "AGENT_TRANSITIONS", "PROTECTED_ACTIONS",
    "SCOPE_KINDS", "STEP_STATUSES", "AgentApprovalDecision", "AgentApprovalRequest",
    "AgentContextSnapshot", "AgentGoal", "AgentPlan", "AgentPolicy", "AgentResult",
    "AgentRun", "AgentScope", "AgentStep", "AgentStepResult",
    # runtime
    "AgentAuditLog", "AgentAuditRecord", "AgentBudget", "AgentCheckpoint",
    "AgentExecutor", "AgentSessionRecord", "AgentSessionStore", "AgentVerifier",
    "CheckpointStore", "ExecutionOutcome", "HeuristicPlanner", "ModelPlanner",
    "VerificationOutcome",
    # planner / registry / policy
    "ACTION_REGISTRY", "FORBIDDEN_ACTIONS", "MODEL_PLAN_CONTRACT", "action_spec",
    "allowlisted_actions", "check_action_allowed", "check_budget", "check_scope",
    "default_planner", "parse_intent", "validate_plan",
    # errors
    "AgentApprovalRequired", "AgentApprovalStale", "AgentBudgetExhausted",
    "AgentCancelled", "AgentError", "AgentMaxStepsReached", "AgentNeedsHumanReview",
    "AgentNotFound", "AgentPlanInvalid", "AgentPolicyDenied",
    "AgentRevisionConflict", "AgentStepFailed",
]
