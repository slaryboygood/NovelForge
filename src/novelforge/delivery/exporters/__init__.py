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

    def as_dict(self) -> dict[str, Any]:
        return {"format": self.format, "exporter_id": self.exporter_id,
                "version": int(self.version), "mime_type": self.mime_type,
                "extension": self.extension,
                "profiles_supported": list(self.profiles_supported),
                "text": bool(self.text), "description": self.description}


class ExporterRegistry:
    def __init__(self) -> None:
        self._rows: dict[str, tuple[ExporterSpec, ExporterFn]] = {}

    def register(self, spec: ExporterSpec, fn: ExporterFn) -> ExporterSpec:
        if not str(spec.format or "").strip():
            raise DeliveryFormatError("exporter 必须声明 format")
        if int(spec.version) < 1:
            raise DeliveryFormatError("exporter version 必须 >= 1")
        self._rows[str(spec.format)] = (spec, fn)
        return spec

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
