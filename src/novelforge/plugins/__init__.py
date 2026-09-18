"""NovelForge `plugins` —— Plugin Platform（V4-09）。

**PLUGIN_USES_PUBLIC_EXTENSION_POINTS**：插件只能通过 Host 公开的扩展点增加能力，
绝不成为 Core，也不绕过 Application / revision / quality / delivery 边界。

Public Contract（精简，§9）：

```text
PluginManager                    发现 / 批准 / 启用 / 加载 / 禁用（唯一生命周期入口）
PluginRegistry / PluginRecord    插件清单与状态（owner 可追踪）

PluginManifest / PluginDescriptor  结构化 manifest 与发现结果
PluginContribution                贡献（type + id + version + permissions_required + factory）
PluginConfig / PluginResult       配置与执行结果（含 provenance）

PLUGIN_API_VERSION               插件 API 版本（与 MCP / blueprint / delivery 版本分开）
PLUGIN_PERMISSIONS / PLUGIN_STATUSES / PLUGIN_TRANSITIONS / TRUST_MODEL

EnablementStore / PluginStateStore / PluginAuditLog   批准记录 / 插件状态 / 审计
build_adapters                   Host 侧 adapter 装配（exporter / quality / mcp）
PluginError 家族                  稳定错误码
```

插件作者应只依赖 **`novelforge.plugins.sdk`**（稳定最小边界，§8）。

Host（宿主）侧的 composition root 在 `novelforge.plugins.host.PluginHost`：
它把插件贡献装配进既有 registry（delivery / quality / interfaces.mcp）。
**本 `__init__` 不 import `host`**：host 需要同时接触 application 与 interfaces，
而 `novelforge.plugins` 本身只暴露平台契约（避免 application ⇄ plugins 循环依赖）。

Trust model（§20–§21、§60）：

```text
V4-09 只执行**用户显式批准**的 trusted 插件（in-process）。
permission 是 Host API capability governance，**不是** Python / OS sandbox。
untrusted 插件的进程级隔离不在本阶段实现。
```
"""

from .adapters import build_adapters
from .compatibility import CompatibilityResult, check_compatibility
from .contracts import (
    CONTRIBUTION_TYPES,
    PLUGIN_API_VERSION,
    PLUGIN_ENTRY_POINT_GROUP,
    PLUGIN_PERMISSIONS,
    PLUGIN_STATUSES,
    PLUGIN_TRANSITIONS,
    RESERVED_NAMESPACES,
    TRUST_MODEL,
    TRUST_MODEL_NOTE,
    PluginConfig,
    PluginContribution,
    PluginDescriptor,
    PluginManifest,
    PluginResult,
    plugin_namespace,
    validate_plugin_id,
)
from .discovery import (
    annotate_compatibility,
    discover_installed,
    discover_manifest_paths,
    manifest_from_json,
    manifest_from_mapping,
)
from .errors import (
    PluginCompatibilityError,
    PluginConfigError,
    PluginConflictError,
    PluginError,
    PluginExecutionError,
    PluginLoadError,
    PluginManifestError,
    PluginNotFoundError,
    PluginNotApprovedError,
    PluginPermissionError,
    PluginRegistrationError,
)
from .lifecycle import (
    assert_transition,
    can_transition,
    lifecycle_table,
    next_statuses,
)
from .manager import SUPPORTED_CAPABILITIES, PluginManager
from .permissions import (
    check_approval,
    declared_permissions,
    normalise_permissions,
    permission_diff,
    permission_note,
    requires_reapproval,
)
from .registry import PluginRecord, PluginRegistry
from .state import EnablementStore, PluginAuditLog, PluginStateStore

__all__ = [
    # manager / registry
    "PluginManager", "PluginRegistry", "PluginRecord", "SUPPORTED_CAPABILITIES",
    # contracts
    "CONTRIBUTION_TYPES", "PLUGIN_API_VERSION", "PLUGIN_ENTRY_POINT_GROUP",
    "PLUGIN_PERMISSIONS", "PLUGIN_STATUSES", "PLUGIN_TRANSITIONS",
    "RESERVED_NAMESPACES", "TRUST_MODEL", "TRUST_MODEL_NOTE", "PluginConfig",
    "PluginContribution", "PluginDescriptor", "PluginManifest", "PluginResult",
    "plugin_namespace", "validate_plugin_id",
    # discovery / compatibility
    "CompatibilityResult", "annotate_compatibility", "check_compatibility",
    "discover_installed", "discover_manifest_paths", "manifest_from_json",
    "manifest_from_mapping",
    # lifecycle / permissions
    "assert_transition", "can_transition", "lifecycle_table", "next_statuses",
    "check_approval", "declared_permissions", "permission_diff", "permission_note",
    "normalise_permissions", "requires_reapproval",
    # state / adapters
    "EnablementStore", "PluginAuditLog", "PluginStateStore", "build_adapters",
    # errors
    "PluginCompatibilityError", "PluginConfigError", "PluginConflictError",
    "PluginError", "PluginExecutionError", "PluginLoadError", "PluginManifestError",
    "PluginNotFoundError", "PluginNotApprovedError", "PluginPermissionError",
    "PluginRegistrationError",
]
