"""PluginContext（V4-09 §24–§25、§29–§30、§45）：capability-scoped least privilege。

```text
PluginContext.config          本插件配置（namespaced）
PluginContext.state           本插件状态（按 novel_id + plugin_id 隔离）
PluginContext.blueprint_view  只读机器视图（需 blueprint.read）
PluginContext.ai              Host 窄 AI 能力（需 ai.invoke）
```

**不给**插件：`ApplicationServices` 全对象 / repository / store / persistence / provider。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Mapping

from ..contracts import PluginConfig
from ..errors import PluginPermissionError


@dataclass(frozen=True)
class PluginContext:
    """Host 注入给插件的窄上下文（least privilege，§24）。"""

    plugin_id: str
    plugin_version: str
    approved_permissions: tuple[str, ...] = ()
    config: PluginConfig = field(default_factory=lambda: PluginConfig("", {}))
    _state: Any = None
    _blueprint_view: Callable[[], Mapping[str, Any]] | None = None
    _ai: Any = None
    _config_validator: Callable[[Mapping[str, Any]], Mapping[str, Any]] | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    # ------------------------------------------------------------------ 权限
    def has_permission(self, permission: str) -> bool:
        return str(permission) in set(self.approved_permissions)

    def require(self, permission: str) -> None:
        if not self.has_permission(permission):
            raise PluginPermissionError(
                f"插件 {self.plugin_id} 未获得 permission：{permission}",
                plugin_id=self.plugin_id,
                details={"permission": str(permission),
                         "approved": sorted(self.approved_permissions)})

    # ------------------------------------------------------------ 窄能力 API
    def get_config(self) -> dict[str, Any]:
        values = dict(self.config.values)
        if self._config_validator is not None:
            return dict(self._config_validator(values))
        return values

    def load_state(self) -> dict[str, Any]:
        self.require("plugin.state")
        if self._state is None:
            return {}
        return dict(self._state.load().get("values") or {})

    def save_state(self, values: Mapping[str, Any]) -> dict[str, Any]:
        self.require("plugin.state")
        if self._state is None:
            return {}
        self._state.save(values)
        return dict(values)

    def blueprint_view(self) -> Mapping[str, Any]:
        """只读机器视图（不暴露 repository / project_root，§25）。"""

        self.require("blueprint.read")
        if self._blueprint_view is None:
            return {}
        return dict(self._blueprint_view())

    def ai(self) -> Any:
        """Host 窄 AI 能力（§45–§46）：插件不得直接 import provider / httpx。"""

        self.require("ai.invoke")
        if self._ai is None:
            raise PluginPermissionError(
                "Host 未提供 AI capability", plugin_id=self.plugin_id,
                details={"permission": "ai.invoke"})
        return self._ai

    def as_dict(self) -> dict[str, Any]:
        return {"plugin_id": self.plugin_id, "plugin_version": self.plugin_version,
                "approved_permissions": sorted(self.approved_permissions),
                "config_keys": sorted(dict(self.config.values)),
                "metadata": dict(self.metadata)}


__all__ = ["PluginContext"]
