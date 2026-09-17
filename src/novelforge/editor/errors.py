"""Editor 错误模型（V4-06 §75）。

接口层只允许看到这些稳定错误（不得把 `KeyError` / `FileNotFoundError` /
pydantic 原始报错透出去）。
"""

from __future__ import annotations

from typing import Any, Mapping


class EditorError(RuntimeError):
    code = "EDITOR_ERROR"

    def __init__(self, message: str, *, details: Mapping[str, Any] | None = None) -> None:
        self.message = str(message)
        self.details = dict(details or {})
        super().__init__(self.message)

    def as_dict(self) -> dict[str, Any]:
        return {"code": self.code, "message": self.message, "details": dict(self.details)}


class EditorValidationError(EditorError):
    """请求本身不合法（字段不存在 / 受保护字段 / 跨节点比较 …）。"""

    code = "EDITOR_VALIDATION_FAILED"


class EditorOwnershipError(EditorError):
    """跨作品访问（Novel A 的 editor 不得触碰 Novel B）。"""

    code = "EDITOR_OWNERSHIP_MISMATCH"


class EditorNotFoundError(EditorError):
    code = "EDITOR_NODE_NOT_FOUND"


class EditorConflictError(EditorError):
    """乐观并发冲突（expected_revision 不匹配）——不得静默覆盖。"""

    code = "EDITOR_REVISION_CONFLICT"


class EditorPreserveViolation(EditorError):
    """结构 identity / preserve 字段被改动（硬约束）。"""

    code = "EDITOR_PRESERVE_VIOLATION"


class EditorOperationRejected(EditorError):
    """操作被业务规则拒绝（状态流转不允许 / AI 不可用 / 批量策略拒绝 …）。"""

    code = "EDITOR_OPERATION_REJECTED"


__all__ = [
    "EditorConflictError", "EditorError", "EditorNotFoundError",
    "EditorOperationRejected", "EditorOwnershipError", "EditorPreserveViolation",
    "EditorValidationError",
]
