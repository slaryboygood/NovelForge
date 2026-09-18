"""ExportService —— 唯一导出出口（V4-01，ADR-007 / V4_EXPORT_SPEC）。

为什么存在：V3 的导出能力分散在四处（`export_package` / `outlines` /
`outline_revision.docx_bytes` / `writer_export_bundle`），UI、API、未来的 MCP 各自调用，
导致「导出内容由谁拼装」无法回答，也导致历史数据混入导出（NR-002）。

迁移策略（Strangler）：V4-01 的服务层包装既有 `export_package`（已完成历史分区与
单作品路径的清除），并把**调用点**收敛到服务层；真正的 Story Blueprint Package
与 DeliveryValidator 属于 V4-07。

V4-07 落地：

```text
Application ExportService（唯一 facade）
        ├── deliver(...)          → novelforge.delivery.DeliveryService（V4 主路径）
        └── projection()/export() legacy 方法（V3 planning export，compatibility）
```

legacy 方法保留是为了 V3 UI / 既有测试兼容；**不得**成为新交付物的底层
（`docs/v4/V4_07_DELIVERY_INVENTORY.md` §3）。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping, Sequence

from novelforge.blueprint import BlueprintRepository
from novelforge.delivery import (
    DEFAULT_PROFILE,
    DeliveryPolicy,
    DeliveryRequest,
    DeliverySelection,
    DeliveryService,
    DeliveryStore,
)
from novelforge.editor import EditorStore
from novelforge.quality import QualityStore
from novelforge.story_builder import export_package as _legacy_export
from novelforge.story_engine.creator import DEFAULT_BRANCH


class ExportService:
    """按 (project_root, novel_id, branch) 生成只读导出物。"""

    SUPPORTED_FORMATS: tuple[str, ...] = ("json", "markdown", "docx")
    #: V4 Story Blueprint 交付格式（`deliver`）
    DELIVERY_FORMATS: tuple[str, ...] = ("json", "markdown", "docx", "nfpack")

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

    # ------------------------------------------------- V4 交付路径（V4-07）
    def delivery(self, *, store: DeliveryStore | None = None,
                 title: str = "") -> DeliveryService:
        """构造 DeliveryService（只读 quality / editor metadata，0 LLM 调用）。"""

        return DeliveryService(
            self.project_root, self.novel_id,
            repository=BlueprintRepository(self.project_root, self.novel_id),
            quality_store=QualityStore(self.project_root, self.novel_id),
            editor_store=EditorStore(self.project_root, self.novel_id),
            store=store, title=title)

    def delivery_selection(self, *, selection_mode: str = "accepted",
                           profile: str = DEFAULT_PROFILE,
                           formats: Sequence[str] = ("json", "markdown"),
                           explicit_revisions: Mapping[str, int] | None = None,
                           include_node_types: Sequence[str] = (),
                           policy: DeliveryPolicy | None = None,
                           created_by: str = "author",
                           **overrides: Any) -> DeliverySelection:
        """构造 DeliverySelection（默认 accepted + 不可放宽的 policy）。"""

        return DeliverySelection(
            novel_id=self.novel_id, selection_mode=selection_mode,
            explicit_revisions=dict(explicit_revisions or {}),
            include_node_types=tuple(str(value) for value in include_node_types
                                     if str(value)),
            formats=tuple(str(value) for value in formats),
            profile=profile, created_by=created_by,
            policy=policy or DeliveryPolicy(), **overrides)

    def describe_delivery(self, selection: DeliverySelection) -> dict[str, Any]:
        return self.delivery().describe(selection)

    def validate_delivery(self, selection: DeliverySelection) -> dict[str, Any]:
        return self.delivery().validate(selection)

    def create_snapshot(self, selection: DeliverySelection, *,
                        persist: bool = True) -> dict[str, Any]:
        return self.delivery().snapshot(selection, persist=persist).as_dict()

    def deliver(self, selection: DeliverySelection, *, idempotency_key: str = "",
                dry_run: bool = False, with_content: bool = True) -> dict[str, Any]:
        """V4 唯一交付出口：selection → snapshot → validate → export → manifest。"""

        result = self.delivery().deliver(DeliveryRequest(
            selection=selection, idempotency_key=idempotency_key, dry_run=dry_run))
        return result.as_dict(with_content=with_content)

    def delivery_snapshot(self, snapshot_id: str) -> dict[str, Any]:
        return self.delivery().get_snapshot(snapshot_id)

    def delivery_manifest(self, snapshot_id: str) -> dict[str, Any]:
        return self.delivery().get_manifest(snapshot_id)

    def delivery_artifact(self, snapshot_id: str, relative_path: str) -> bytes:
        return self.delivery().read_artifact(snapshot_id, relative_path)

    def delivery_snapshots(self) -> list[dict[str, Any]]:
        return self.delivery().list_snapshots()


def export_service(project_root: Path | str, novel_id: str, *,
                   branch_id: str = DEFAULT_BRANCH) -> ExportService:
    return ExportService(project_root, novel_id, branch_id=branch_id)


__all__ = ["ExportService", "export_service"]
