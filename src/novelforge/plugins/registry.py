"""PluginRegistry（V4-09 §63、§74–§75）。

```text
list_discovered / list_enabled / get / enable / disable / contributions / status
```

注册项带 owner（core | plugin + owner_id），因此 disable 一个插件只影响它自己的
贡献，不影响 Core（§75）。UI / API 不得直接操作 Python entry point，只经本注册表。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping, Sequence

from .contracts import (
    PLUGIN_STATUSES,
    PluginContribution,
    PluginDescriptor,
    PluginManifest,
)
from .errors import PluginConflictError, PluginNotFoundError


@dataclass
class PluginRecord:
    descriptor: PluginDescriptor
    status: str = "discovered"
    enabled: bool = False
    approved_permissions: tuple[str, ...] = ()
    approved_version: str = ""
    contributions: tuple[PluginContribution, ...] = ()
    registered_ids: tuple[str, ...] = ()
    error_code: str = ""
    error_message: str = ""
    loaded: bool = False

    @property
    def plugin_id(self) -> str:
        return self.descriptor.plugin_id

    @property
    def manifest(self) -> PluginManifest:
        return self.descriptor.manifest

    @property
    def active(self) -> bool:
        return self.status in ("loaded", "active")

    def as_dict(self) -> dict[str, Any]:
        return {**self.descriptor.as_dict(), "status": self.status,
                "enabled": bool(self.enabled),
                "approved_version": self.approved_version,
                "approved_permissions": list(self.approved_permissions),
                "contributions": [row.as_dict() for row in self.contributions],
                "registered_ids": list(self.registered_ids),
                "error_code": self.error_code,
                "error_message": self.error_message,
                "active": self.active, "loaded": bool(self.loaded)}


class PluginRegistry:
    """插件清单与状态（内存；持久化由 EnablementStore / AuditLog 负责）。"""

    def __init__(self) -> None:
        self._records: dict[str, PluginRecord] = {}

    # ------------------------------------------------------------------ 注册
    def add(self, descriptor: PluginDescriptor) -> PluginRecord:
        plugin_id = descriptor.plugin_id
        existing = self._records.get(plugin_id)
        if existing is not None:
            if existing.descriptor.manifest.digest == descriptor.manifest.digest:
                return existing
            raise PluginConflictError(
                f"plugin_id 重复且 manifest 不同：{plugin_id}",
                plugin_id=plugin_id,
                details={"existing_version": existing.manifest.version,
                         "incoming_version": descriptor.manifest.version})
        record = PluginRecord(descriptor=descriptor, status=descriptor.status)
        self._records[plugin_id] = record
        return record

    def get(self, plugin_id: str) -> PluginRecord:
        record = self._records.get(str(plugin_id))
        if record is None:
            raise PluginNotFoundError(f"未知插件：{plugin_id}",
                                      plugin_id=str(plugin_id))
        return record

    def find(self, plugin_id: str) -> PluginRecord | None:
        return self._records.get(str(plugin_id))

    # ------------------------------------------------------------------ 查询
    def list_discovered(self) -> list[dict[str, Any]]:
        return [self._records[key].as_dict() for key in sorted(self._records)]

    def list_enabled(self) -> list[dict[str, Any]]:
        return [row.as_dict() for row in
                (self._records[key] for key in sorted(self._records))
                if row.enabled or row.active]

    def status(self) -> dict[str, Any]:
        counts: dict[str, int] = {}
        for record in self._records.values():
            counts[record.status] = counts.get(record.status, 0) + 1
        return {"plugins": len(self._records), "by_status": dict(sorted(counts.items())),
                "active": sorted(record.plugin_id for record in self._records.values()
                                 if record.active)}

    def contributions(self, *, type: str = "", plugin_id: str = ""
                      ) -> list[dict[str, Any]]:  # noqa: D401 - 见 docstring
        """列出贡献（可按 type / plugin_id 过滤）。"""

        rows: list[dict[str, Any]] = []
        for record in self._records.values():
            if plugin_id and record.plugin_id != plugin_id:
                continue
            if not record.active:
                continue
            for contribution in record.contributions:
                if type and contribution.type != type:
                    continue
                rows.append({**contribution.as_dict(), "plugin_id": record.plugin_id,
                             "plugin_version": record.manifest.version})
        return sorted(rows, key=lambda row: (row["plugin_id"], row["contribution_id"]))

    # ------------------------------------------------------------------ 更新
    def set_status(self, plugin_id: str, status: str, **extra: Any) -> PluginRecord:
        if str(status) not in PLUGIN_STATUSES:
            raise PluginConflictError(f"未知插件状态：{status}", plugin_id=str(plugin_id))
        record = self.get(plugin_id)
        record.status = str(status)
        for key, value in extra.items():
            if hasattr(record, key):
                setattr(record, key, value)
        return record

    def owners(self) -> dict[str, tuple[str, ...]]:
        """owner_id → 已注册 contribution id（用于 disable 时精确回滚）。"""

        return {record.plugin_id: record.registered_ids
                for record in self._records.values() if record.registered_ids}

    def __len__(self) -> int:
        return len(self._records)


__all__ = ["PluginRecord", "PluginRegistry"]
