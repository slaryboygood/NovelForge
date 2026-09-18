"""Agent 错误模型（V4-11 §72）：稳定 code，绝不向接口层返回 raw exception。"""

from __future__ import annotations

from typing import Any, Mapping


class AgentError(RuntimeError):
    code = "AGENT_ERROR"

    def __init__(self, message: str, *, details: Mapping[str, Any] | None = None,
                 session_id: str = "", step_id: str = "") -> None:
        self.message = str(message)
        self.details = dict(details or {})
        self.session_id = str(session_id or self.details.get("session_id") or "")
        self.step_id = str(step_id or self.details.get("step_id") or "")
        super().__init__(self.message)

    def as_dict(self) -> dict[str, Any]:
        return {"code": self.code, "message": self.message,
                "session_id": self.session_id, "step_id": self.step_id,
                "details": dict(self.details)}


class AgentPlanInvalid(AgentError):
    code = "AGENT_PLAN_INVALID"


class AgentPolicyDenied(AgentError):
    code = "AGENT_POLICY_DENIED"


class AgentStepFailed(AgentError):
    code = "AGENT_STEP_FAILED"


class AgentRevisionConflict(AgentError):
    code = "AGENT_REVISION_CONFLICT"


class AgentApprovalRequired(AgentError):
    code = "AGENT_APPROVAL_REQUIRED"


class AgentApprovalStale(AgentError):
    code = "AGENT_APPROVAL_STALE"


class AgentBudgetExhausted(AgentError):
    code = "AGENT_BUDGET_EXHAUSTED"


class AgentMaxStepsReached(AgentError):
    code = "AGENT_MAX_STEPS_REACHED"


class AgentCancelled(AgentError):
    code = "AGENT_CANCELLED"


class AgentNeedsHumanReview(AgentError):
    code = "AGENT_NEEDS_HUMAN_REVIEW"


class AgentNotFound(AgentError):
    code = "AGENT_NOT_FOUND"


__all__ = [
    "AgentApprovalRequired", "AgentApprovalStale", "AgentBudgetExhausted",
    "AgentCancelled", "AgentError", "AgentMaxStepsReached", "AgentNeedsHumanReview",
    "AgentNotFound", "AgentPlanInvalid", "AgentPolicyDenied",
    "AgentRevisionConflict", "AgentStepFailed",
]
