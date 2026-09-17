"""Memory 错误模型（V4-03）。

与 AI 边界一致的要求：稳定 / 结构化 / 可测试 / 不泄露内部路径。
"""

from __future__ import annotations

from typing import Any, Mapping


class MemoryError(RuntimeError):
    code = "MEMORY_ERROR"

    def __init__(self, message: str, *, details: Mapping[str, Any] | None = None) -> None:
        self.message = str(message)
        self.details: dict[str, Any] = dict(details or {})
        super().__init__(self.message)

    def as_dict(self) -> dict[str, Any]:
        return {"code": self.code, "message": self.message, "details": dict(self.details)}


class MemoryIsolationError(MemoryError):
    """跨作品访问被拒绝（V4-03 §31：novel_id 过滤必须早于相关性排序）。"""

    code = "MEMORY_ISOLATION_VIOLATION"


class MemorySourceError(MemoryError):
    """canonical source 不可用（缺失 / 不可读 / 结构不符）。"""

    code = "MEMORY_SOURCE_UNAVAILABLE"


class PreferenceScopeError(MemoryError):
    """作者偏好作用域 / 键值非法。"""

    code = "MEMORY_PREFERENCE_SCOPE_INVALID"


class StaleMemoryError(MemoryError):
    """调用方显式要求使用已失效的派生记忆。"""

    code = "MEMORY_STALE_DERIVED"


__all__ = [
    "MemoryError", "MemoryIsolationError", "MemorySourceError",
    "PreferenceScopeError", "StaleMemoryError",
]

