"""PluginService（V4-09 §64–§66、§85、§87）：接口层的插件门面。

```text
application.services.plugins.PluginService
```

接口层（REST / MCP / UI / Agent）只调用本门面，**不直接**调用 `PluginManager`，
也不接触 Python entry point。本模块属于 application 层，因此**不 import interfaces**
（MCP 装配在 `novelforge.plugins.host.PluginHost`，见 `V4_MODULE_BOUNDARIES.md` §3.16）。

安全说明：enable / disable 属于安全敏感操作；V4-09 只提供 Application 层门面
（§65–§67：不为了 REST 扩大权限模型，也不自动安装远程插件）。
"""

from __future__ import annotations

from typing import Any, Sequence

from novelforge.plugins import (
    PLUGIN_PERMISSIONS,
    TRUST_MODEL,
    PluginManager,
    permission_note,
)


class PluginService:
    """插件管理门面（只读查询 + 显式 approve / enable / disable）。"""

    def __init__(self, manager: PluginManager) -> None:
        self.manager = manager

    # ------------------------------------------------------------------ 只读
    def list_plugins(self) -> list[dict[str, Any]]:
        """UI / Agent 需要的清单（§87：name / id / version / status / capability）。"""

        return self.manager.list_discovered()

    def get_plugin(self, plugin_id: str) -> dict[str, Any]:
        return self.manager.get(plugin_id)

    def status(self) -> dict[str, Any]:
        return self.manager.status()

    def contributions(self, *, type: str = "") -> list[dict[str, Any]]:
        return self.manager.contributions(type=type)

    def audit(self) -> list[dict[str, Any]]:
        return self.manager.audit_records()

    def permission_model(self) -> dict[str, Any]:
        """公开 permission 模型（含"permission ≠ OS sandbox"的诚实说明，§23、§60）。"""

        return {"trust_model": TRUST_MODEL, "permissions": list(PLUGIN_PERMISSIONS),
                "note": permission_note()}

    # ------------------------------------------------------------------ 操作
    def discover(self) -> list[dict[str, Any]]:
        """显式发现（唯一的 discovery 入口，§91）。"""

        return self.manager.discover()

    def approve(self, plugin_id: str, *, permissions: Sequence[str] | None = None,
                approved_by: str = "user", note: str = "") -> dict[str, Any]:
        return self.manager.approve(plugin_id, permissions=permissions,
                                    approved_by=approved_by, note=note)

    def enable(self, plugin_id: str) -> dict[str, Any]:
        return self.manager.enable(plugin_id)

    def disable(self, plugin_id: str, *, reason: str = "") -> dict[str, Any]:
        return self.manager.disable(plugin_id, reason=reason)


__all__ = ["PluginService"]
