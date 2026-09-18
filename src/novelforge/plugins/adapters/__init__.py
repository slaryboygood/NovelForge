"""Host adapters（V4-09 §31–§42、§70–§72）：把插件贡献注册进既有 registry。

```text
ExporterAdapter          → delivery.ExporterRegistry
QualityEvaluatorAdapter  → quality.EvaluatorRegistry
McpAdapter               → interfaces.mcp 的 Tool / Resource registry
```

规则：

```text
· 只有 Host adapter 能触碰 registry（插件拿到的是"返回 contribution"的接口，§71）
· 贡献 id 必须 namespaced（plugin.<plugin_id>.<id>），不得覆盖 Core（§39–§40、§73）
· 注册是原子的：任一贡献失败 → 整体回滚（§49）
· 每个注册项带 owner（owner_type=plugin, owner_id=plugin_id），disable 只影响自己（§75）
```
"""

from __future__ import annotations

from typing import Any, Callable, Mapping, Protocol, Sequence

from ..contracts import PluginContribution, plugin_namespace
from ..errors import PluginConflictError, PluginRegistrationError


class ContributionAdapter(Protocol):
    """一种 contribution type 的 Host adapter。"""

    type: str
    permission: str

    def register(self, *, plugin_id: str, plugin_version: str,
                 contribution: PluginContribution,
                 approved_permissions: Sequence[str] = ()) -> str: ...

    def unregister(self, *, plugin_id: str) -> int: ...


class BaseAdapter:
    type: str = ""
    permission: str = ""

    def __init__(self, registry: Any) -> None:
        self.registry = registry

    # ------------------------------------------------------------------ 工具
    def namespaced(self, plugin_id: str, contribution_id: str) -> str:
        return f"{plugin_namespace(plugin_id)}.{contribution_id}"

    def check_core_conflict(self, candidate_id: str, *,
                            core_ids: Sequence[str]) -> None:
        if str(candidate_id) in set(core_ids):
            raise PluginConflictError(
                f"贡献 id 与 Core 冲突：{candidate_id}",
                details={"contribution_id": str(candidate_id),
                         "hint": "插件贡献必须 namespaced（plugin.<plugin_id>.<id>）"})

    def reject_reserved(self, plugin_id: str, contribution_id: str) -> None:
        raw = str(contribution_id or "")
        if raw.startswith(("novelforge.", "core.")):
            raise PluginConflictError(
                f"贡献 id 使用保留 namespace：{raw}",
                details={"plugin_id": plugin_id,
                         "reserved": ["novelforge.*", "core.*"]})

    def unregister(self, *, plugin_id: str) -> int:
        if hasattr(self.registry, "unregister_owner"):
            return int(self.registry.unregister_owner(str(plugin_id)))
        return 0

    # ------------------------------------------------------------- 抽象方法
    def register(self, *, plugin_id: str, plugin_version: str,
                 contribution: PluginContribution,
                 approved_permissions: Sequence[str] = ()) -> str:
        raise NotImplementedError


def build_adapters(*, exporter_registry: Any = None, evaluator_registry: Any = None,
                   mcp_tool_registry: Any = None, mcp_resource_registry: Any = None,
                   narrow_context: Any = None) -> dict[str, Any]:
    """装配 Host adapter（由 composition 调用；Core 本身不依赖具体插件）。"""

    from .exporter import ExporterAdapter
    from .mcp import McpAdapter
    from .quality import QualityEvaluatorAdapter

    adapters: dict[str, Any] = {}
    if exporter_registry is not None:
        adapters["exporter"] = ExporterAdapter(exporter_registry)
    if evaluator_registry is not None:
        adapters["quality_evaluator"] = QualityEvaluatorAdapter(evaluator_registry)
    if mcp_tool_registry is not None or mcp_resource_registry is not None:
        adapter = McpAdapter(mcp_tool_registry, mcp_resource_registry,
                             narrow_context=narrow_context)
        if mcp_tool_registry is not None:
            adapters["mcp_tool"] = adapter
        if mcp_resource_registry is not None:
            adapters["mcp_resource"] = adapter
    return adapters


__all__ = ["BaseAdapter", "ContributionAdapter", "build_adapters"]
