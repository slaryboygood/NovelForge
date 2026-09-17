"""Blueprint 错误模型（V4-04）。"""

from __future__ import annotations

from typing import Any, Mapping


class BlueprintError(RuntimeError):
    code = "BLUEPRINT_ERROR"

    def __init__(self, message: str, *, details: Mapping[str, Any] | None = None) -> None:
        self.message = str(message)
        self.details: dict[str, Any] = dict(details or {})
        super().__init__(self.message)

    def as_dict(self) -> dict[str, Any]:
        return {"code": self.code, "message": self.message, "details": dict(self.details)}


class BlueprintNodeNotFound(BlueprintError):
    code = "BLUEPRINT_NODE_NOT_FOUND"


class BlueprintValidationError(BlueprintError):
    """结构与引用校验失败（V4-04 只做 schema / 结构 / ownership / 引用完整性）。"""

    code = "BLUEPRINT_VALIDATION_FAILED"

    def __init__(self, message: str, *, issues: list[dict[str, Any]] | None = None,
                 details: Mapping[str, Any] | None = None) -> None:
        super().__init__(message, details=details)
        self.issues = list(issues or [])
        self.details.setdefault("issues", self.issues)


class BlueprintStatusError(BlueprintError):
    code = "BLUEPRINT_STATUS_INVALID"


class BlueprintOwnershipError(BlueprintError):
    code = "BLUEPRINT_OWNERSHIP_VIOLATION"


__all__ = [
    "BlueprintError", "BlueprintNodeNotFound", "BlueprintOwnershipError",
    "BlueprintStatusError", "BlueprintValidationError",
]

