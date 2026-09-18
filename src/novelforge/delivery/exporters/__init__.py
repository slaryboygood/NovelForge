"""Exporter 注册表（V4-07 §53–§54、§43）。

每个 exporter 声明 `format / exporter_id / version / mime_type / extension /
profiles_supported`；manifest 记录 id + version，便于以后解释格式变化。

本阶段不实现插件平台（V4-09 才做加载与权限），只保证注册接口可扩展。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Mapping, Sequence

from ..errors import DeliveryFormatError

ExporterFn = Callable[[Mapping[str, Any]], bytes]


@dataclass(frozen=True)
class ExporterSpec:
    format: str
    exporter_id: str
    version: int
    mime_type: str
    extension: str
    profiles_supported: tuple[str, ...] = ("reader", "author", "machine", "audit")
    text: bool = True
    description: str = ""
    #: V4-09 §75：注册归属（core | plugin + owner_id），disable 插件时按 owner 卸载
    owner_type: str = "core"
    owner_id: str = "novelforge"

    def as_dict(self) -> dict[str, Any]:
        return {"format": self.format, "exporter_id": self.exporter_id,
                "version": int(self.version), "mime_type": self.mime_type,
                "extension": self.extension,
                "profiles_supported": list(self.profiles_supported),
                "text": bool(self.text), "description": self.description,
                "owner_type": self.owner_type, "owner_id": self.owner_id}


class ExporterRegistry:
    def __init__(self) -> None:
        self._rows: dict[str, tuple[ExporterSpec, ExporterFn]] = {}

    def register(self, spec: ExporterSpec, fn: ExporterFn) -> ExporterSpec:
        if not str(spec.format or "").strip():
            raise DeliveryFormatError("exporter 必须声明 format")
        if int(spec.version) < 1:
            raise DeliveryFormatError("exporter version 必须 >= 1")
        existing = self._rows.get(str(spec.format))
        if existing is not None:
            # §40 / §77：Core 注册不可被覆盖；插件同格式注册视为冲突。
            # owner 相同的重复注册 = 该 owner 更新自己的 handler（core 更新 core /
            # 插件更新插件），这不构成"覆盖 Core"。
            if (existing[0].owner_type != spec.owner_type
                    or existing[0].owner_id != spec.owner_id):
                raise DeliveryFormatError(
                    f"exporter 格式重复注册：{spec.format}",
                    details={"format": str(spec.format),
                             "existing_owner": existing[0].owner_id,
                             "incoming_owner": spec.owner_id})
        self._rows[str(spec.format)] = (spec, fn)
        return spec

    def unregister_owner(self, owner_id: str) -> int:
        """按 owner 卸载（Core owner 不允许卸载，§74–§76）。"""

        rows = {key: value for key, value in self._rows.items()
                if value[0].owner_id != str(owner_id)
                or value[0].owner_type == "core"}
        removed = len(self._rows) - len(rows)
        self._rows = rows
        return removed

    def owners(self) -> dict[str, tuple[str, ...]]:
        result: dict[str, list[str]] = {}
        for spec, _fn in self._rows.values():
            result.setdefault(spec.owner_id, []).append(spec.format)
        return {key: tuple(sorted(value)) for key, value in sorted(result.items())}

    def get(self, fmt: str) -> tuple[ExporterSpec, ExporterFn]:
        row = self._rows.get(str(fmt))
        if row is None:
            raise DeliveryFormatError(
                f"未知导出格式：{fmt}",
                details={"known": sorted(self._rows)})
        return row

    def spec(self, fmt: str) -> ExporterSpec:
        return self.get(fmt)[0]

    def formats(self) -> tuple[str, ...]:
        return tuple(sorted(self._rows))

    def specs(self) -> tuple[ExporterSpec, ...]:
        return tuple(self._rows[key][0] for key in sorted(self._rows))

    def for_profile(self, profile: str) -> tuple[ExporterSpec, ...]:
        return tuple(spec for spec in self.specs() if profile in spec.profiles_supported)

    def __len__(self) -> int:
        return len(self._rows)


def build_default_registry() -> ExporterRegistry:
    from . import docx_exporter, json_exporter, markdown_exporter, package_exporter

    registry = ExporterRegistry()
    for module in (json_exporter, markdown_exporter, docx_exporter, package_exporter):
        module.register(registry)
    return registry


__all__ = ["ExporterFn", "ExporterRegistry", "ExporterSpec", "build_default_registry"]
