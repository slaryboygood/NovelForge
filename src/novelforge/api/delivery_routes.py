"""V4-07：Delivery / Export 最小 REST（thin routes）。

```text
POST /api/story-builder/delivery                     建立交付（可 dry_run）
GET  /api/story-builder/delivery/{snapshot_id}        快照
GET  /api/story-builder/delivery/{snapshot_id}/manifest
GET  /api/story-builder/delivery/{snapshot_id}/artifacts/{artifact_path:path}
GET  /api/story-builder/delivery/snapshots            已交付快照列表
```

Route 只做协议转换与错误码映射；业务能力全部来自
`application.services.export.ExportService`（§84）。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import APIRouter, FastAPI, Query
from fastapi.responses import JSONResponse, Response
from pydantic import Field

from novelforge.application.services.export import ExportService
from novelforge.delivery import (
    DEFAULT_PROFILE,
    DEFAULT_SELECTION_MODE,
    DeliveryError,
    DeliveryExportError,
    DeliveryFormatError,
    DeliveryOwnershipError,
    DeliverySelectionError,
    DeliveryValidationFailed,
    profile_defaults,
)
from novelforge.models import StrictModel


class DeliveryBody(StrictModel):
    novel_id: str = Field(min_length=1, max_length=96)
    selection_mode: str = Field(default=DEFAULT_SELECTION_MODE, max_length=32)
    profile: str = Field(default=DEFAULT_PROFILE, max_length=32)
    formats: list[str] = Field(default_factory=lambda: ["json", "markdown"],
                              max_length=8)
    include_node_types: list[str] = Field(default_factory=list, max_length=16)
    explicit_revisions: dict[str, int] = Field(default_factory=dict)
    require_accepted: bool = True
    require_quality_pass: bool = True
    allow_unevaluated: bool = False
    allow_stale_quality: bool = False
    include_quality_report: bool | None = None
    include_provenance: bool | None = None
    include_revision_history: bool | None = None
    package_includes_node_files: bool = False
    idempotency_key: str = Field(default="", max_length=128)
    dry_run: bool = False


def _status_for(exc: DeliveryError) -> int:
    if isinstance(exc, DeliveryOwnershipError):
        return 403
    if isinstance(exc, DeliveryFormatError):
        return 400
    if isinstance(exc, (DeliverySelectionError, DeliveryValidationFailed)):
        return 422
    if isinstance(exc, DeliveryExportError):
        return 409
    return 400


def install_delivery_api(app: FastAPI, project_root: Path, *,
                         exporter_registry: Any = None) -> None:
    """装配 delivery 路由。

    `exporter_registry` 由宿主注入（V4-10）：注入后交付选择能看到插件 exporter 注册的
    format；未注入时退化为 Core 4 种格式（与 V4-07 行为一致）。
    """

    router = APIRouter(prefix="/api/story-builder/delivery", tags=["delivery"])

    def _export_service(novel_id: str) -> Any:
        return ExportService(project_root, novel_id,
                             exporter_registry=exporter_registry)

    def _selection(body: DeliveryBody) -> Any:
        service = _export_service(body.novel_id)
        from novelforge.delivery import DeliveryPolicy

        policy = DeliveryPolicy(
            require_accepted=body.require_accepted,
            require_quality_pass=body.require_quality_pass,
            allow_unevaluated=body.allow_unevaluated,
            allow_stale_quality=body.allow_stale_quality)
        return service.delivery_selection(
            selection_mode=body.selection_mode, profile=body.profile,
            formats=body.formats, policy=policy,
            explicit_revisions=body.explicit_revisions,
            include_node_types=body.include_node_types,
            include_quality_report=body.include_quality_report,
            include_provenance=body.include_provenance,
            include_revision_history=body.include_revision_history,
            package_includes_node_files=body.package_includes_node_files)

    @router.post("")
    def post_delivery(body: DeliveryBody) -> dict[str, Any]:
        service = _export_service(body.novel_id)
        selection = _selection(body)
        return service.deliver(selection, idempotency_key=body.idempotency_key,
                               dry_run=body.dry_run)

    @router.get("/snapshots")
    def list_snapshots(novel_id: str = Query(min_length=3, max_length=96)
                       ) -> dict[str, Any]:
        return {"novel_id": novel_id,
                "snapshots": _export_service(novel_id).delivery_snapshots()}

    @router.get("/{snapshot_id}")
    def get_snapshot(snapshot_id: str,
                     novel_id: str = Query(min_length=3, max_length=96)
                     ) -> dict[str, Any]:
        return _export_service(novel_id).delivery_snapshot(snapshot_id)

    @router.get("/{snapshot_id}/manifest")
    def get_manifest(snapshot_id: str,
                     novel_id: str = Query(min_length=3, max_length=96)
                     ) -> dict[str, Any]:
        return _export_service(novel_id).delivery_manifest(snapshot_id)

    @router.get("/{snapshot_id}/artifacts/{artifact_path:path}")
    def get_artifact(snapshot_id: str, artifact_path: str,
                     novel_id: str = Query(min_length=3, max_length=96)) -> Response:
        service = _export_service(novel_id)
        data = service.delivery_artifact(snapshot_id, artifact_path)
        manifest = service.delivery_manifest(snapshot_id)
        mime = "application/octet-stream"
        for row in manifest.get("artifacts") or []:
            if str(row.get("path")) == artifact_path:
                mime = str(row.get("mime_type") or mime)
                break
        filename = Path(artifact_path).name
        return Response(content=data, media_type=mime, headers={
            "Content-Disposition": f'attachment; filename="{filename}"'})

    app.include_router(router)

    async def handle_delivery_error(_request, exc: DeliveryError) -> JSONResponse:
        return JSONResponse(status_code=_status_for(exc), content={"detail": exc.as_dict()})

    app.add_exception_handler(DeliveryError, handle_delivery_error)


__all__ = ["install_delivery_api"]
