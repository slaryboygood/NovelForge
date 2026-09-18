"""权限模型（V4-09 §22–§25、§92）。

**Permission ≠ Python / OS sandbox**：它只控制 Host 主动向插件提供哪些 capability。
未批准 / 未声明 / 升级后新增的 permission 一律拒绝。
"""

from __future__ import annotations

from typing import Any, Iterable, Mapping, Sequence

from .contracts import PLUGIN_PERMISSIONS, PluginManifest
from .errors import PluginPermissionError


def normalise_permissions(values: Iterable[str]) -> tuple[str, ...]:
    unknown = sorted({str(value) for value in values} - set(PLUGIN_PERMISSIONS))
    if unknown:
        raise PluginPermissionError(
            f"未知 permission：{unknown}",
            details={"unknown": unknown, "known": list(PLUGIN_PERMISSIONS)})
    return tuple(sorted({str(value) for value in values if str(value)}))


def declared_permissions(manifest: PluginManifest) -> tuple[str, ...]:
    return normalise_permissions(manifest.permissions)


def check_approval(manifest: PluginManifest, *,
                   approved_permissions: Sequence[str],
                   requested: Sequence[str] = ()) -> tuple[str, ...]:
    """插件要求的 permission 必须都在已批准集合内（§53、§92）。"""

    approved = set(normalise_permissions(approved_permissions))
    wanted = set(str(value) for value in requested) | set(declared_permissions(manifest))
    missing = sorted(wanted - approved)
    if missing:
        raise PluginPermissionError(
            f"插件需要未批准的 permission：{missing}",
            details={"plugin_id": manifest.plugin_id, "missing": missing,
                     "approved": sorted(approved),
                     "note": "permission 升级必须重新批准（§53）"})
    return tuple(sorted(wanted))


def permission_diff(*, approved: Sequence[str], declared: Sequence[str]
                    ) -> dict[str, list[str]]:
    """批准记录与当前 manifest 的权限差异（升级检测，§52）。"""

    approved_set = set(str(value) for value in approved)
    declared_set = set(str(value) for value in declared)
    return {"added": sorted(declared_set - approved_set),
            "removed": sorted(approved_set - declared_set)}


def requires_reapproval(*, approved_version: str, current_version: str,
                        approved: Sequence[str], declared: Sequence[str],
                        approved_digest: str = "", current_digest: str = ""
                        ) -> tuple[bool, Mapping[str, Any]]:
    """判断插件升级后是否必须重新批准（§52–§53、§62）。"""

    diff = permission_diff(approved=approved, declared=declared)
    reasons: list[str] = []
    if str(approved_version) != str(current_version):
        reasons.append("version_changed")
    if diff["added"]:
        reasons.append("permission_added")
    if approved_digest and current_digest and approved_digest != current_digest:
        reasons.append("package_digest_changed")
    return bool(reasons), {"reasons": reasons, "permission_diff": diff}


def permission_note() -> str:
    return ("permission 是 Host API capability governance，不是 Python / OS sandbox；"
            "恶意 in-process 插件仍可直接访问解释器能力")


__all__ = [
    "check_approval", "declared_permissions", "normalise_permissions",
    "permission_diff", "permission_note", "requires_reapproval",
]
