"""兼容性检查（V4-09 §13）：加载之前判定，绝不"import 一半才发现"。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from .contracts import PLUGIN_API_VERSION, PluginManifest


@dataclass(frozen=True)
class CompatibilityResult:
    ok: bool
    plugin_id: str
    plugin_api_version: int
    host_api_version: int
    reason: str = ""
    details: Mapping[str, Any] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.details is None:
            object.__setattr__(self, "details", {})

    def as_dict(self) -> dict[str, Any]:
        return {"ok": bool(self.ok), "plugin_id": self.plugin_id,
                "plugin_api_version": int(self.plugin_api_version),
                "host_api_version": int(self.host_api_version),
                "reason": self.reason, "details": dict(self.details)}


def check_compatibility(manifest: PluginManifest, *,
                        host_api_version: int = PLUGIN_API_VERSION,
                        host_version: str = "",
                        supported_capabilities: Sequence[str] | None = None
                        ) -> CompatibilityResult:
    """判定插件是否可在当前 Host 上加载（§13）。

    规则（保守、可解释）：

    ```text
    plugin_api_version <  host  → 兼容（向后兼容旧插件）
    plugin_api_version == host  → 兼容
    plugin_api_version >  host  → 不兼容（PLUGIN_INCOMPATIBLE）
    host_compatibility.min_host_version 声明 → 与 host_version 比较（字符串比较，缺失则跳过）
    插件声明的 capability 必须被 Host 支持
    ```
    """

    caps = tuple(supported_capabilities) if supported_capabilities is not None else None
    if int(manifest.plugin_api_version) > int(host_api_version):
        return CompatibilityResult(
            ok=False, plugin_id=manifest.plugin_id,
            plugin_api_version=int(manifest.plugin_api_version),
            host_api_version=int(host_api_version),
            reason="插件要求的 API 版本高于当前 Host",
            details={"hint": "升级 NovelForge 或使用兼容版本的插件"})
    if caps is not None:
        unsupported = sorted(set(manifest.capabilities) - set(caps))
        if unsupported:
            return CompatibilityResult(
                ok=False, plugin_id=manifest.plugin_id,
                plugin_api_version=int(manifest.plugin_api_version),
                host_api_version=int(host_api_version),
                reason=f"Host 不支持插件声明的 capability：{unsupported}",
                details={"unsupported": unsupported, "supported": sorted(caps)})
    declared = dict(manifest.host_compatibility or {})
    min_version = str(declared.get("min_host_version") or "")
    if min_version and host_version and host_version < min_version:
        return CompatibilityResult(
            ok=False, plugin_id=manifest.plugin_id,
            plugin_api_version=int(manifest.plugin_api_version),
            host_api_version=int(host_api_version),
            reason=f"宿主版本 {host_version} 低于插件要求 {min_version}",
            details={"min_host_version": min_version, "host_version": host_version})
    return CompatibilityResult(ok=True, plugin_id=manifest.plugin_id,
                               plugin_api_version=int(manifest.plugin_api_version),
                               host_api_version=int(host_api_version),
                               reason="compatible")


__all__ = ["CompatibilityResult", "check_compatibility"]
