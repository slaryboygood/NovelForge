"""Plugin 错误模型（V4-09 §57–§58）：稳定 code + 不泄漏内部细节。"""

from __future__ import annotations

import re
from typing import Any, Mapping

_ABSOLUTE_PATH_RE = re.compile(
    r"(?:[A-Za-z]:[\\/][^\s\"']*|/(?:home|users|var|tmp|mnt|opt|root|etc)/[^\s\"']*)",
    re.IGNORECASE)

#: 错误信息里永不外传的 key（§58：不把 secret / 凭据带到 UI / MCP）
_SECRET_TOKENS = ("api_key", "apikey", "authorization", "bearer ", "sk-",
                  "secret_key", "password", "token=")


def redact_message(message: str, *, limit: int = 300) -> str:
    """净化插件错误信息（V4-09 §58、§100）。

    ```text
    · 绝对路径 → <path>
    · secret 类 token → <redacted>
    · 截断到 limit（不把完整 traceback / 大段内部状态带出去）
    ```
    """

    text = str(message or "")
    text = _ABSOLUTE_PATH_RE.sub("<path>", text)
    lowered = text.lower()
    for token in _SECRET_TOKENS:
        if token in lowered:
            start = lowered.index(token)
            end = text.find(" ", start)
            end = len(text) if end == -1 else end
            text = f"{text[:start]}<redacted>{text[end:]}"
            lowered = text.lower()
    return text[:limit]


class PluginError(RuntimeError):
    code = "PLUGIN_ERROR"

    def __init__(self, message: str, *, details: Mapping[str, Any] | None = None,
                 plugin_id: str = "") -> None:
        self.message = str(message)
        self.details = dict(details or {})
        self.plugin_id = str(plugin_id or self.details.get("plugin_id") or "")
        super().__init__(self.message)

    def as_dict(self) -> dict[str, Any]:
        return {"code": self.code, "message": self.message,
                "plugin_id": self.plugin_id, "details": dict(self.details)}


class PluginManifestError(PluginError):
    code = "PLUGIN_MANIFEST_INVALID"


class PluginCompatibilityError(PluginError):
    code = "PLUGIN_INCOMPATIBLE"


class PluginPermissionError(PluginError):
    code = "PLUGIN_PERMISSION_DENIED"


class PluginNotApprovedError(PluginError):
    code = "PLUGIN_NOT_APPROVED"


class PluginLoadError(PluginError):
    code = "PLUGIN_LOAD_FAILED"


class PluginRegistrationError(PluginError):
    code = "PLUGIN_REGISTRATION_FAILED"


class PluginConflictError(PluginError):
    """与 Core 或其它插件注册冲突（§40、§49、§90）。"""

    code = "PLUGIN_REGISTRATION_CONFLICT"


class PluginExecutionError(PluginError):
    code = "PLUGIN_EXECUTION_FAILED"


class PluginNotFoundError(PluginError):
    code = "PLUGIN_NOT_FOUND"


class PluginConfigError(PluginError):
    code = "PLUGIN_CONFIG_INVALID"


__all__ = [
    "PluginCompatibilityError", "PluginConfigError", "PluginConflictError",
    "PluginError", "PluginExecutionError", "PluginLoadError", "PluginManifestError",
    "PluginNotFoundError", "PluginNotApprovedError", "PluginPermissionError",
    "PluginRegistrationError", "redact_message",
]
