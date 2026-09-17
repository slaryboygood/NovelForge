"""Generation 错误模型（V4-04）。"""

from __future__ import annotations

from typing import Any, Mapping


class GenerationError(RuntimeError):
    code = "GENERATION_ERROR"

    def __init__(self, message: str, *, details: Mapping[str, Any] | None = None) -> None:
        self.message = str(message)
        self.details = dict(details or {})
        super().__init__(self.message)

    def as_dict(self) -> dict[str, Any]:
        return {"code": self.code, "message": self.message, "details": dict(self.details)}


class GenerationUnavailableError(GenerationError):
    """provider / context 不可用（明确失败，不生成低质量硬编码创意，§42）。"""

    code = "GENERATION_UNAVAILABLE"


class GenerationValidationError(GenerationError):
    """生成结果未通过 schema / 结构 / 引用校验（§33）。"""

    code = "GENERATION_VALIDATION_FAILED"

    def __init__(self, message: str, *, issues: list[dict[str, Any]] | None = None,
                 details: Mapping[str, Any] | None = None) -> None:
        super().__init__(message, details=details)
        self.issues = list(issues or [])
        self.details.setdefault("issues", self.issues)


class RewriteViolationError(GenerationError):
    """字段级改写违反了 target / preserve 约束（V4-06 §20、§58）。

    违反时**不写入任何 revision**（不是"先保存再提醒"）。
    """

    code = "REWRITE_PRESERVE_VIOLATION"

    def __init__(self, message: str, *, fields: list[str] | None = None,
                 details: Mapping[str, Any] | None = None) -> None:
        super().__init__(message, details=details)
        self.fields = list(fields or [])
        self.details.setdefault("violating_fields", self.fields)


__all__ = ["GenerationError", "GenerationUnavailableError",
           "GenerationValidationError", "RewriteViolationError"]
