"""Plugin 契约（V4-09 §9–§18、§22、§26、§54、§70）。

```text
PLUGIN_API_VERSION     插件 API 版本（与 MCP / blueprint / delivery schema 版本分开）
PluginManifest         插件的结构化声明（唯一身份 = plugin_id，不是模块名）
PluginDescriptor       发现结果（manifest + 来源 + digest + 兼容性）
PluginContribution     插件贡献（type + id + 需要的权限 + 工厂/处理器）
PluginStatus           生命周期状态
PluginPermission       Host capability 白名单
PluginConfig           插件配置（namespaced by plugin_id）
PluginResult           插件执行结果（含 provenance）
```

**Trusted Plugin Model**（§20–§21、§60）：V4-09 只执行用户显式批准的 trusted 插件；
permission 是 **Host API capability governance**，不是 OS / interpreter sandbox。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

from novelforge.core.ids import digest_payload

from .errors import PluginManifestError

#: 插件 API 版本（§12：与 MCP_INTERFACE_VERSION / BLUEPRINT_SCHEMA_VERSION /
#: DELIVERY_SCHEMA_VERSION 相互独立）
PLUGIN_API_VERSION = 1

#: entry point group（§15）
PLUGIN_ENTRY_POINT_GROUP = "novelforge.plugins"

#: 生命周期状态（§18）
PLUGIN_STATUSES: tuple[str, ...] = (
    "discovered", "compatible", "incompatible", "approved", "enabled", "loaded",
    "active", "disabled", "failed",
)

#: 状态流转（lifecycle 唯一 SSOT）
PLUGIN_TRANSITIONS: Mapping[str, tuple[str, ...]] = {
    "discovered": ("compatible", "incompatible", "failed", "disabled"),
    "compatible": ("approved", "disabled", "failed"),
    "incompatible": ("disabled",),
    "approved": ("enabled", "disabled", "failed"),
    "enabled": ("loaded", "disabled", "failed"),
    "loaded": ("active", "disabled", "failed"),
    "active": ("disabled", "failed"),
    "disabled": ("enabled",),
    "failed": ("disabled",),
}

#: Host capability 白名单（§22）：permission 只控制"Host 主动提供什么"
PLUGIN_PERMISSIONS: tuple[str, ...] = (
    "delivery.export",      # 注册 delivery exporter
    "quality.evaluate",     # 注册 quality evaluator
    "mcp.extend",           # 注册 MCP tool / resource
    "ai.invoke",            # 经 Host 提供的 AI capability 调用模型
    "blueprint.read",       # 经 PluginContext 读取已选定的 Blueprint 视图
    "editor.mutate",        # 经 Host 提供的 narrow mutation capability（本阶段仅声明）
    "network.request",      # 经 Host 中介的网络能力（本阶段仅声明）
    "plugin.state",         # 读写本插件自己的 namespaced state
)

#: 保留 namespace（§73）：第三方禁止使用
RESERVED_NAMESPACES: tuple[str, ...] = ("novelforge", "core")

#: 贡献类型（§70）
CONTRIBUTION_TYPES: tuple[str, ...] = (
    "exporter", "quality_evaluator", "mcp_tool", "mcp_resource",
)

#: 信任模型（§20–§21）
TRUST_MODEL = "trusted_in_process"
TRUST_MODEL_NOTE = (
    "V4-09 只执行用户显式批准的 trusted 插件（in-process）。"
    "permission 是 Host API capability governance，不是 Python / OS sandbox："
    "恶意插件仍可能直接 import os / 打开文件 / 建立 socket。"
    "untrusted 插件的进程级隔离（sandbox）不在本阶段实现。")

#: `plugin_id` 形态：反向域名风格 namespace
_PLUGIN_ID_PARTS_MIN = 2


def validate_plugin_id(plugin_id: str) -> str:
    """plugin_id 必须全局唯一、稳定、带 namespace（§11）。"""

    value = str(plugin_id or "").strip()
    if not value:
        raise PluginManifestError("manifest 缺少 plugin_id")
    parts = value.split(".")
    if len(parts) < _PLUGIN_ID_PARTS_MIN:
        raise PluginManifestError(
            "plugin_id 必须使用 namespace 形式（例如 com.example.myplugin）",
            details={"plugin_id": value})
    for part in parts:
        if not part or not all(ch.islower() or ch.isdigit() or ch in "_-"
                               for ch in part):
            raise PluginManifestError(
                "plugin_id 段落只能使用小写字母 / 数字 / _ / -",
                details={"plugin_id": value, "segment": part})
    if parts[0] in RESERVED_NAMESPACES:
        raise PluginManifestError(
            f"plugin_id 不得使用保留 namespace：{parts[0]}",
            details={"plugin_id": value, "reserved": list(RESERVED_NAMESPACES)})
    return value


def plugin_namespace(plugin_id: str) -> str:
    """贡献 id / issue code 的 namespace 前缀（§36、§39、§72）。"""

    return f"plugin.{validate_plugin_id(plugin_id)}"


@dataclass(frozen=True)
class PluginManifest:
    """插件的结构化声明（§10）。"""

    plugin_id: str
    name: str
    version: str
    plugin_api_version: int = PLUGIN_API_VERSION
    description: str = ""
    entry_point: str = ""
    capabilities: tuple[str, ...] = ()
    permissions: tuple[str, ...] = ()
    configuration_schema: Mapping[str, Any] = field(default_factory=dict)
    host_compatibility: Mapping[str, Any] = field(default_factory=dict)
    author: str = ""
    homepage: str = ""
    package_digest: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "plugin_id", validate_plugin_id(self.plugin_id))
        if not str(self.name or "").strip():
            raise PluginManifestError("manifest 缺少 name",
                                      details={"plugin_id": self.plugin_id})
        if not str(self.version or "").strip():
            raise PluginManifestError("manifest 缺少 version",
                                      details={"plugin_id": self.plugin_id})
        if int(self.plugin_api_version) < 1:
            raise PluginManifestError("plugin_api_version 必须 >= 1",
                                      details={"plugin_id": self.plugin_id})
        unknown = sorted(set(self.permissions) - set(PLUGIN_PERMISSIONS))
        if unknown:
            raise PluginManifestError(
                f"manifest 声明了未知 permission：{unknown}",
                details={"plugin_id": self.plugin_id, "unknown": unknown,
                         "known": list(PLUGIN_PERMISSIONS)})
        unknown_caps = sorted(set(self.capabilities) - set(CONTRIBUTION_TYPES))
        if unknown_caps:
            raise PluginManifestError(
                f"manifest 声明了未知 capability：{unknown_caps}",
                details={"plugin_id": self.plugin_id, "unknown": unknown_caps,
                         "known": list(CONTRIBUTION_TYPES)})
        if not str(self.entry_point or "").strip():
            raise PluginManifestError("manifest 缺少 entry_point",
                                      details={"plugin_id": self.plugin_id})

    @property
    def namespace(self) -> str:
        return plugin_namespace(self.plugin_id)

    @property
    def digest(self) -> str:
        return digest_payload(self.as_dict())

    def as_dict(self) -> dict[str, Any]:
        return {"plugin_id": self.plugin_id, "name": self.name, "version": self.version,
                "plugin_api_version": int(self.plugin_api_version),
                "description": self.description, "entry_point": self.entry_point,
                "capabilities": list(self.capabilities),
                "permissions": list(self.permissions),
                "configuration_schema": dict(self.configuration_schema),
                "host_compatibility": dict(self.host_compatibility),
                "author": self.author, "homepage": self.homepage,
                "package_digest": self.package_digest}

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> "PluginManifest":
        row = dict(raw or {})
        raw_api = row.get("plugin_api_version", PLUGIN_API_VERSION)
        # 显式 0 不能被 `or` 静默替换成默认值（必须报 PLUGIN_MANIFEST_INVALID）
        resolved_api = (PLUGIN_API_VERSION if raw_api is None or raw_api == ""
                        else int(raw_api))
        return cls(
            plugin_id=str(row.get("plugin_id") or ""),
            name=str(row.get("name") or ""),
            version=str(row.get("version") or ""),
            plugin_api_version=resolved_api,
            description=str(row.get("description") or ""),
            entry_point=str(row.get("entry_point") or ""),
            capabilities=tuple(str(value) for value in (row.get("capabilities") or ())),
            permissions=tuple(str(value) for value in (row.get("permissions") or ())),
            configuration_schema=dict(row.get("configuration_schema") or {}),
            host_compatibility=dict(row.get("host_compatibility") or {}),
            author=str(row.get("author") or ""), homepage=str(row.get("homepage") or ""),
            package_digest=str(row.get("package_digest") or ""))


@dataclass(frozen=True)
class PluginDescriptor:
    """发现结果（§14：discovery 只产出 descriptor，不执行插件代码）。"""

    manifest: PluginManifest
    source: str = "entry_point"        # entry_point | manifest_path
    locator: str = ""                  # entry point value / manifest 文件路径（相对化）
    status: str = "discovered"
    manifest_digest: str = ""
    compatibility: Mapping[str, Any] = field(default_factory=dict)

    @property
    def plugin_id(self) -> str:
        return self.manifest.plugin_id

    @property
    def version(self) -> str:
        return self.manifest.version

    def as_dict(self) -> dict[str, Any]:
        return {"plugin_id": self.plugin_id, "name": self.manifest.name,
                "version": self.version,
                "plugin_api_version": int(self.manifest.plugin_api_version),
                "description": self.manifest.description,
                "capabilities": list(self.manifest.capabilities),
                "permissions": list(self.manifest.permissions),
                "author": self.manifest.author, "homepage": self.manifest.homepage,
                "entry_point": self.manifest.entry_point,
                "package_digest": self.manifest.package_digest,
                "source": self.source, "locator": self.locator,
                "status": self.status, "manifest_digest": self.manifest_digest,
                "compatibility": dict(self.compatibility)}


@dataclass(frozen=True)
class PluginContribution:
    """插件贡献（§70）：由 host adapter 验证后注册到既有 registry。"""

    type: str
    contribution_id: str
    factory: Any
    version: int = 1
    permissions_required: tuple[str, ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.type not in CONTRIBUTION_TYPES:
            raise PluginManifestError(f"未知 contribution type：{self.type}")
        if not str(self.contribution_id or "").strip():
            raise PluginManifestError("contribution 缺少 contribution_id")
        if self.factory is None:
            raise PluginManifestError("contribution 缺少 factory")
        unknown = sorted(set(self.permissions_required) - set(PLUGIN_PERMISSIONS))
        if unknown:
            raise PluginManifestError(
                f"contribution 声明了未知 permission：{unknown}",
                details={"contribution_id": self.contribution_id,
                         "unknown": unknown})

    def namespaced_id(self, plugin_id: str) -> str:
        return f"{plugin_namespace(plugin_id)}.{self.contribution_id}"

    def as_dict(self) -> dict[str, Any]:
        return {"type": self.type, "contribution_id": self.contribution_id,
                "version": int(self.version),
                "permissions_required": list(self.permissions_required),
                "metadata": dict(self.metadata)}


@dataclass(frozen=True)
class PluginConfig:
    """插件配置（§26）：严格 schema + 按 plugin_id 隔离。"""

    plugin_id: str
    values: Mapping[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {"plugin_id": self.plugin_id, "values": dict(self.values)}


@dataclass(frozen=True)
class PluginResult:
    """插件执行结果（§55：携带 provenance，可追溯 plugin_id + version）。"""

    plugin_id: str
    plugin_version: str
    contribution_id: str = ""
    plugin_api_version: int = PLUGIN_API_VERSION
    ok: bool = True
    value: Any = None
    error_code: str = ""
    message: str = ""

    @property
    def provenance(self) -> dict[str, Any]:
        return {"plugin_id": self.plugin_id, "plugin_version": self.plugin_version,
                "plugin_api_version": int(self.plugin_api_version),
                "contribution_id": self.contribution_id}

    def as_dict(self) -> dict[str, Any]:
        return {"ok": bool(self.ok), "value": self.value,
                "error_code": self.error_code, "message": self.message,
                "provenance": self.provenance}


def contribution_error(plugin_id: str, version: str, contribution_id: str,
                       exc: BaseException) -> PluginResult:
    """把插件运行期异常转成 PluginResult（§58：不泄漏 traceback / 路径）。"""

    from .errors import redact_message

    return PluginResult(plugin_id=plugin_id, plugin_version=version,
                        contribution_id=contribution_id, ok=False,
                        error_code="PLUGIN_EXECUTION_FAILED",
                        message=redact_message(f"{type(exc).__name__}: {exc}"))


__all__ = [
    "CONTRIBUTION_TYPES", "PLUGIN_API_VERSION", "PLUGIN_ENTRY_POINT_GROUP",
    "PLUGIN_PERMISSIONS", "PLUGIN_STATUSES", "PLUGIN_TRANSITIONS",
    "RESERVED_NAMESPACES", "TRUST_MODEL", "TRUST_MODEL_NOTE", "PluginConfig",
    "PluginContribution", "PluginDescriptor", "PluginManifest", "PluginResult",
    "contribution_error", "plugin_namespace", "validate_plugin_id",
]
