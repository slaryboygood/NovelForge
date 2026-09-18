"""ExportService —— 唯一导出出口（V4-01，ADR-007 / V4_EXPORT_SPEC）。

为什么存在：V3 的导出能力分散在四处（`export_package` / `outlines` /
`outline_revision.docx_bytes` / `writer_export_bundle`），UI、API、未来的 MCP 各自调用，
导致「导出内容由谁拼装」无法回答，也导致历史数据混入导出（NR-002）。

迁移历史（Strangler 已完成）：V4-01 先把调用点收敛到服务层，V4-07 落地 Story
Blueprint Package 与 DeliveryValidator；post-release cleanup 之后，那四个 legacy
导出通道（`export_package` / `outlines` 导出 / `outline_revision` / `writer_export_bundle`）
已随 V2/V3 后端整体删除，本模块只剩 `deliver()` 一条路径。

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

#: Story Blueprint 只有一条主线（V4-01 起不再有分支存档产品面）；
#: 该常量原属 legacy creator，post-release cleanup 后由 application 自己持有。
DEFAULT_BRANCH = "main"


class ExportService:
    """V4 交付 facade：只经 `novelforge.delivery` 生成交付物。

    post-release cleanup：legacy `export_package` / `writer_export_bundle` 通道
    （`projection()` / `validate()` / `export()` / `writer_bundle()`）已随 V2/V3
    产品面退休。当前唯一交付出口是 `deliver()`（revision-pinned + manifest + checksum）。
    """

    SUPPORTED_FORMATS: tuple[str, ...] = ("json", "markdown", "docx")
    #: V4 Story Blueprint 交付格式（`deliver`）
    DELIVERY_FORMATS: tuple[str, ...] = ("json", "markdown", "docx", "nfpack")

    def __init__(self, project_root: Path | str, novel_id: str, *,
                 branch_id: str = DEFAULT_BRANCH,
                 exporter_registry: Any = None) -> None:
        self.project_root = Path(project_root)
        self.novel_id = str(novel_id or "").strip()
        if not self.novel_id:
            raise ValueError("ExportService 需要显式 novel_id（不允许隐式当前作品）")
        self.branch_id = branch_id or DEFAULT_BRANCH
        #: V4-09：插件 exporter 通过 composition 注入的 exporter registry
        self.exporter_registry = exporter_registry

    # ------------------------------------------------- V4 交付路径（V4-07）
    def delivery(self, *, store: DeliveryStore | None = None,
                 title: str = "") -> DeliveryService:
        """构造 DeliveryService（只读 quality / editor metadata，0 LLM 调用）。"""

        return DeliveryService(
            self.project_root, self.novel_id,
            repository=BlueprintRepository(self.project_root, self.novel_id),
            quality_store=QualityStore(self.project_root, self.novel_id),
            editor_store=EditorStore(self.project_root, self.novel_id),
            store=store, title=title, registry=self.exporter_registry)

    def delivery_selection(self, *, selection_mode: str = "accepted",
                           profile: str = DEFAULT_PROFILE,
                           formats: Sequence[str] = ("json", "markdown"),
                           explicit_revisions: Mapping[str, int] | None = None,
                           include_node_types: Sequence[str] = (),
                           policy: DeliveryPolicy | None = None,
                           created_by: str = "author",
                           **overrides: Any) -> DeliverySelection:
        """构造 DeliverySelection（默认 accepted + 不可放宽的 policy）。"""

        #: V4-09 §32：插件 exporter 注册的 format 也允许被选择（Host 注入的 registry）
        accepted = (tuple(self.exporter_registry.formats())
                    if self.exporter_registry is not None else ())
        return DeliverySelection(
            novel_id=self.novel_id, selection_mode=selection_mode,
            explicit_revisions=dict(explicit_revisions or {}),
            include_node_types=tuple(str(value) for value in include_node_types
                                     if str(value)),
            formats=tuple(str(value) for value in formats),
            profile=profile, created_by=created_by,
            policy=policy or DeliveryPolicy(), accepted_formats=accepted,
            **overrides)

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

    def blueprint_view(self, *, selection_mode: str = "current",
                       profile: str = "machine",
                       include_node_types: Sequence[str] = (),
                       policy: DeliveryPolicy | None = None,
                       with_content: bool = False) -> dict[str, Any]:
        """只读机器视图（V4-08 §14）：有序 Blueprint + 每节点 status / review / quality。

        默认 `selection_mode="current"`（读工作态），交付仍默认 `accepted`。
        """

        selection = self.delivery_selection(
            selection_mode=selection_mode, profile=profile,
            formats=("json",), include_node_types=include_node_types,
            policy=policy or (DeliveryPolicy() if selection_mode == "accepted"
                              else DeliveryPolicy.relaxed()))
        return self.delivery().machine_representation(selection)


def export_service(project_root: Path | str, novel_id: str, *,
                   branch_id: str = DEFAULT_BRANCH,
                   exporter_registry: Any = None) -> ExportService:
    return ExportService(project_root, novel_id, branch_id=branch_id,
                         exporter_registry=exporter_registry)


__all__ = ["ExportService", "export_service"]
