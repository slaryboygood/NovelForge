"""插件发现（V4-09 §14–§16、§61）：**manifest only，绝不执行插件代码**。

```text
discover()  → PluginDescriptor（manifest + 来源 + digest + 兼容性判定）
load(...)   → 由 PluginManager 显式执行（见 manager.py）
```

发现来源（只这两种，不扫描目录）：

```text
1. importlib.metadata.entry_points(group="novelforge.plugins")   ← 已安装 distribution
2. host 显式提供的 manifest 路径（extra_manifest_paths）        ← 项目内/本地显式路径
```

**不**递归扫描 `project/plugins/*.py`（§61）；也不做远程 marketplace / 自动安装（§16）。
"""

from __future__ import annotations

import json
from importlib import metadata
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from novelforge.core.ids import digest_payload

from .compatibility import check_compatibility
from .contracts import (
    PLUGIN_API_VERSION,
    PLUGIN_ENTRY_POINT_GROUP,
    PluginDescriptor,
    PluginManifest,
)
from .errors import PluginManifestError


def manifest_from_mapping(raw: Mapping[str, Any]) -> PluginManifest:
    return PluginManifest.from_dict(raw)


def manifest_from_json(text: str) -> PluginManifest:
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise PluginManifestError(f"manifest JSON 无法解析：{exc}") from exc
    if not isinstance(payload, Mapping):
        raise PluginManifestError("manifest 必须是 JSON 对象")
    return manifest_from_mapping(payload)


def discover_installed(*, group: str = PLUGIN_ENTRY_POINT_GROUP,
                       entries: Sequence[Any] | None = None) -> list[PluginDescriptor]:
    """从已安装 distribution 的 entry points 读取 manifest（不 import 插件模块）。"""

    rows = list(entries) if entries is not None else list(
        metadata.entry_points(group=group))
    descriptors: list[PluginDescriptor] = []
    for entry in rows:
        manifest_map = _entry_manifest(entry)
        if manifest_map is None:
            continue
        manifest = manifest_from_mapping(manifest_map)
        descriptors.append(PluginDescriptor(
            manifest=manifest, source="entry_point",
            locator=str(getattr(entry, "value", "")) or str(getattr(entry, "name", "")),
            manifest_digest=manifest.digest))
    return descriptors


def _entry_manifest(entry: Any) -> Mapping[str, Any] | None:
    """entry point 的 manifest 来源：优先 `.dist` metadata，其次 `.value` 指向 JSON。"""

    dist = getattr(entry, "dist", None)
    if dist is not None:
        try:
            text = dist.read_text("novelforge-plugin.json")
        except Exception:  # noqa: BLE001 - metadata 不可读时不视为插件
            text = None
        if text:
            return dict(json.loads(text))
    value = str(getattr(entry, "value", "") or "")
    if value.endswith(".json"):
        path = Path(value)
        if path.is_file():
            return dict(json.loads(path.read_text(encoding="utf-8")))
    return None


def discover_manifest_paths(paths: Iterable[Path | str]) -> list[PluginDescriptor]:
    """host 显式提供的 manifest 路径（§61：显式路径，不扫描目录）。"""

    descriptors: list[PluginDescriptor] = []
    for raw in paths:
        path = Path(raw)
        if not path.is_file():
            raise PluginManifestError(f"manifest 文件不存在：{path.name}",
                                      details={"path": path.name})
        manifest = manifest_from_json(path.read_text(encoding="utf-8"))
        descriptors.append(PluginDescriptor(
            manifest=manifest, source="manifest_path", locator=path.name,
            manifest_digest=manifest.digest))
    return descriptors


def dedupe_descriptors(descriptors: Sequence[PluginDescriptor]
                       ) -> list[PluginDescriptor]:
    """同一 plugin_id 只保留第一个（重复 discovery → 冲突由 manager 显式报告）。"""

    seen: dict[str, PluginDescriptor] = {}
    for row in descriptors:
        seen.setdefault(row.plugin_id, row)
    return [seen[key] for key in sorted(seen)]


def annotate_compatibility(descriptors: Sequence[PluginDescriptor], *,
                           host_api_version: int = PLUGIN_API_VERSION,
                           host_version: str = "",
                           supported_capabilities: Sequence[str] | None = None
                           ) -> list[PluginDescriptor]:
    """发现阶段就标注兼容性（§13）：不兼容的插件不会进入 load。"""

    rows: list[PluginDescriptor] = []
    for row in descriptors:
        result = check_compatibility(
            row.manifest, host_api_version=host_api_version,
            host_version=host_version, supported_capabilities=supported_capabilities)
        rows.append(PluginDescriptor(
            manifest=row.manifest, source=row.source, locator=row.locator,
            status="compatible" if result.ok else "incompatible",
            manifest_digest=row.manifest_digest or row.manifest.digest,
            compatibility=result.as_dict()))
    return rows


def package_digest(payloads: Mapping[str, Any]) -> str:
    """插件包摘要（§62）：用于识别"批准之后代码被替换"。"""

    return digest_payload(dict(payloads))


__all__ = [
    "annotate_compatibility", "dedupe_descriptors", "discover_installed",
    "discover_manifest_paths", "manifest_from_json", "manifest_from_mapping",
    "package_digest",
]
