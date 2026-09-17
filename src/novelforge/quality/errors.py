"""Quality / Repair 错误模型（V4-05）。"""

from __future__ import annotations

from typing import Any, Mapping


class QualityError(RuntimeError):
    code = "QUALITY_ERROR"

    def __init__(self, message: str, *, details: Mapping[str, Any] | None = None) -> None:
        self.message = str(message)
        self.details = dict(details or {})
        super().__init__(self.message)

    def as_dict(self) -> dict[str, Any]:
        return {"code": self.code, "message": self.message, "details": dict(self.details)}


class QualityScopeError(QualityError):
    code = "QUALITY_SCOPE_INVALID"


class QualityPolicyError(QualityError):
    code = "QUALITY_POLICY_INVALID"


class RepairPlanError(QualityError):
    code = "REPAIR_PLAN_INVALID"


class RepairConflictError(QualityError):
    """两个 repair contract 的 preserve / allow_change 互相冲突（§31）。"""

    code = "REPAIR_CONTRACT_CONFLICT"


class RepairNotAllowedError(QualityError):
    """issue 不可自动修（manual_only / 违反 preserve 约束）。"""

    code = "REPAIR_NOT_ALLOWED"


class RepairRoundLimitError(QualityError):
    """达到 max_repair_rounds（§39）。"""

    code = "REPAIR_ROUND_LIMIT"


__all__ = [
    "QualityError", "QualityPolicyError", "QualityScopeError",
    "RepairConflictError", "RepairNotAllowedError", "RepairPlanError",
    "RepairRoundLimitError",
]

