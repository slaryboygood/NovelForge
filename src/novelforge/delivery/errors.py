"""Delivery 错误模型（V4-07 §75 的交付侧对应物）。"""

from __future__ import annotations

from typing import Any, Mapping


class DeliveryError(RuntimeError):
    code = "DELIVERY_ERROR"

    def __init__(self, message: str, *, details: Mapping[str, Any] | None = None) -> None:
        self.message = str(message)
        self.details = dict(details or {})
        super().__init__(self.message)

    def as_dict(self) -> dict[str, Any]:
        return {"code": self.code, "message": self.message, "details": dict(self.details)}


class DeliveryValidationFailed(DeliveryError):
    """preflight / post-build 校验失败（交付被阻止）。"""

    code = "DELIVERY_VALIDATION_FAILED"

    def __init__(self, message: str, *, issues: list[dict[str, Any]] | None = None,
                 details: Mapping[str, Any] | None = None) -> None:
        super().__init__(message, details=details)
        self.issues = list(issues or [])
        self.details.setdefault("issues", self.issues)


class DeliveryOwnershipError(DeliveryError):
    """跨作品读取 / 打包。"""

    code = "DELIVERY_OWNERSHIP_MISMATCH"


class DeliverySelectionError(DeliveryError):
    """selection / revision 解析失败。"""

    code = "DELIVERY_SELECTION_INVALID"


class DeliveryFormatError(DeliveryError):
    """未知格式 / 不支持该 profile。"""

    code = "DELIVERY_FORMAT_UNSUPPORTED"


class DeliveryExportError(DeliveryError):
    """exporter 构建失败（不留下伪成功 package）。"""

    code = "DELIVERY_EXPORT_FAILED"


__all__ = [
    "DeliveryError", "DeliveryExportError", "DeliveryFormatError",
    "DeliveryOwnershipError", "DeliverySelectionError", "DeliveryValidationFailed",
]
