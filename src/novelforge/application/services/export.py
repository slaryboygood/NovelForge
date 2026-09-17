"""ExportService —— 唯一导出出口（V4-01，ADR-007 / V4_EXPORT_SPEC）。

为什么存在：V3 的导出能力分散在四处（`export_package` / `outlines` /
`outline_revision.docx_bytes` / `writer_export_bundle`），UI、API、未来的 MCP 各自调用，
导致「导出内容由谁拼装」无法回答，也导致历史数据混入导出（NR-002）。

迁移策略（Strangler）：V4-01 的服务层包装既有 `export_package`（已完成历史分区与
单作品路径的清除），并把**调用点**收敛到服务层；真正的 Story Blueprint Package
与 DeliveryValidator 属于 V4-07。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from novelforge.story_builder import export_package as _legacy_export
from novelforge.story_engine.creator import DEFAULT_BRANCH


class ExportService:
    """按 (project_root, novel_id, branch) 生成只读导出物。"""

    SUPPORTED_FORMATS: tuple[str, ...] = ("json", "markdown", "docx")

    def __init__(self, project_root: Path | str, novel_id: str, *,
                 branch_id: str = DEFAULT_BRANCH) -> None:
        self.project_root = Path(project_root)
        self.novel_id = str(novel_id or "").strip()
        if not self.novel_id:
            raise ValueError("ExportService 需要显式 novel_id（不允许隐式当前作品）")
        self.branch_id = branch_id or DEFAULT_BRANCH

    def projection(self) -> dict[str, Any]:
        """只读导出投影（不含序列化产物）。"""

        return _legacy_export.build_export_projection(
            self.project_root, self.novel_id, branch_id=self.branch_id)

    def validate(self, projection: dict[str, Any] | None = None) -> dict[str, Any]:
        """导出校验（schema / identity / provenance / truth separation / stability）。"""

        return _legacy_export.validate_export_package(projection or self.projection())

    def export(self, *, fmt: str = "json", include_projection: bool = False
               ) -> dict[str, Any]:
        """唯一导出出口：projection → validation → serializer。"""

        return _legacy_export.export_package(
            self.project_root, self.novel_id, branch_id=self.branch_id, fmt=fmt,
            include_projection=include_projection)

    def writer_bundle(self) -> dict[str, Any]:
        """Writer-ready 联合入口（导出 projection + 分层上下文）。"""

        from novelforge.story_builder.writer_integration import writer_export_bundle

        return writer_export_bundle(self.project_root, self.novel_id,
                                    branch_id=self.branch_id)


def export_service(project_root: Path | str, novel_id: str, *,
                   branch_id: str = DEFAULT_BRANCH) -> ExportService:
    return ExportService(project_root, novel_id, branch_id=branch_id)


__all__ = ["ExportService", "export_service"]

