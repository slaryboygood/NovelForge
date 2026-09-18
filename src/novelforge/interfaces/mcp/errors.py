"""MCP 错误模型与稳定错误码（V4-08 §30–§31、§68）。

客户端只看到稳定 code + message + cause（业务 code）+ 相关字段；
绝不暴露 traceback / pydantic stack / 绝对路径。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

#: 稳定 MCP 错误码（§30）
MCP_ERROR_CODES: tuple[str, ...] = (
    "MCP_INVALID_ARGUMENT",
    "MCP_NOVEL_NOT_FOUND",
    "MCP_NODE_NOT_FOUND",
    "MCP_RESOURCE_NOT_FOUND",
    "MCP_TOOL_NOT_FOUND",
    "MCP_REVISION_CONFLICT",
    "MCP_OWNERSHIP_MISMATCH",
    "MCP_PRESERVE_VIOLATION",
    "MCP_QUALITY_BLOCKED",
    "MCP_DELIVERY_BLOCKED",
    "MCP_OPERATION_REQUIRES_REVIEW",
    "MCP_OPERATION_REJECTED",
    "MCP_LLM_UNAVAILABLE",
    "MCP_INTERNAL_ERROR",
)


class MCPError(RuntimeError):
    """MCP 层错误（业务错误一律映射为稳定 code，并保留 cause）。"""

    code = "MCP_INTERNAL_ERROR"

    def __init__(self, message: str, *, cause: str = "", details: Mapping[str, Any] | None = None,
                 request_id: str = "") -> None:
        self.message = str(message)
        self.cause = str(cause or "")
        self.details = dict(details or {})
        self.request_id = str(request_id or "")
        super().__init__(self.message)

    def as_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {"code": self.code, "message": self.message,
                                   "cause": self.cause, "details": dict(self.details)}
        if self.request_id:
            payload["request_id"] = self.request_id
        return payload


class MCPInvalidArgument(MCPError):
    code = "MCP_INVALID_ARGUMENT"


class MCPNodeNotFound(MCPError):
    code = "MCP_NODE_NOT_FOUND"


class MCPResourceNotFound(MCPError):
    code = "MCP_RESOURCE_NOT_FOUND"


class MCPToolNotFound(MCPError):
    code = "MCP_TOOL_NOT_FOUND"


class MCPRevisionConflict(MCPError):
    code = "MCP_REVISION_CONFLICT"


class MCPOwnershipMismatch(MCPError):
    code = "MCP_OWNERSHIP_MISMATCH"


class MCPPreserveViolation(MCPError):
    code = "MCP_PRESERVE_VIOLATION"


class MCPQualityBlocked(MCPError):
    code = "MCP_QUALITY_BLOCKED"


class MCPDeliveryBlocked(MCPError):
    code = "MCP_DELIVERY_BLOCKED"


class MCPRequiresReview(MCPError):
    code = "MCP_OPERATION_REQUIRES_REVIEW"


class MCPOperationRejected(MCPError):
    code = "MCP_OPERATION_REJECTED"


class MCPLLMUnavailable(MCPError):
    code = "MCP_LLM_UNAVAILABLE"


class MCPInternalError(MCPError):
    """未分类的内部错误（必须带 request_id；不返回 traceback / 路径）。"""

    code = "MCP_INTERNAL_ERROR"


@dataclass(frozen=True)
class InvocationRecord:
    """接口层 observability（§69、§70）：不写业务 store，不含敏感内容。"""

    request_id: str
    kind: str                     # tool | resource
    name: str
    novel_id: str = ""
    operation: str = ""
    status: str = "ok"            # ok | error
    error_code: str = ""
    cause: str = ""
    latency_ms: int = 0
    extra: Mapping[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {"request_id": self.request_id, "kind": self.kind, "name": self.name,
                "novel_id": self.novel_id, "operation": self.operation,
                "status": self.status, "error_code": self.error_code,
                "cause": self.cause, "latency_ms": int(self.latency_ms),
                "extra": dict(self.extra)}


__all__ = [
    "MCP_ERROR_CODES", "MCPDeliveryBlocked", "MCPError", "MCPInvalidArgument",
    "MCPInternalError", "MCPLLMUnavailable", "MCPNodeNotFound", "MCPOperationRejected",
    "MCPOwnershipMismatch", "MCPPreserveViolation", "MCPQualityBlocked",
    "MCPRequiresReview", "MCPResourceNotFound", "MCPRevisionConflict",
    "MCPToolNotFound", "InvocationRecord",
]
