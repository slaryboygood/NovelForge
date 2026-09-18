"""Delivery 资源（V4-08 §25、§45–§47）：
快照列表 / 单个快照 / manifest / artifact（按 snapshot_id + 登记路径读取，不使用任意路径）。
"""

from __future__ import annotations

from typing import Any

from ..contracts import ResourceSpec
from ..errors import MCPResourceNotFound
from ..payloads import ResourcePayload, json_payload
from ..registry import MCPResourceRegistry
from ..serialization import mime_for


def register(registry: MCPResourceRegistry, *, spec_source: Any = None) -> None:
    def snapshots_resource(context: Any, target: Any) -> ResourcePayload:
        from ..uri import paginate

        rows = [{"snapshot_id": row.get("snapshot_id"),
                 "created_at": row.get("created_at"),
                 "selection_mode": row.get("selection_mode"),
                 "profile": row.get("profile"),
                 "formats": row.get("formats"),
                 "node_count": len(row.get("node_revisions") or {}),
                 "input_digest": row.get("input_digest")}
                for row in context.export.delivery_snapshots()]
        page = paginate(rows, limit=target.limit, cursor=target.cursor)
        return json_payload(target.uri, {"novel_id": target.novel_id, **page})

    def snapshot_resource(context: Any, target: Any) -> ResourcePayload:
        row = context.export.delivery_snapshot(target.snapshot_id)
        if not row:
            raise MCPResourceNotFound(
                f"交付快照不存在：{target.snapshot_id}",
                details={"snapshot_id": target.snapshot_id,
                         "novel_id": target.novel_id})
        return json_payload(target.uri, {"novel_id": target.novel_id,
                                         "snapshot": row})

    def manifest_resource(context: Any, target: Any) -> ResourcePayload:
        row = context.export.delivery_manifest(target.snapshot_id)
        if not row:
            raise MCPResourceNotFound(
                f"交付 manifest 不存在：{target.snapshot_id}",
                details={"snapshot_id": target.snapshot_id})
        return json_payload(target.uri, {"novel_id": target.novel_id,
                                         "manifest": row})

    def artifact_resource(context: Any, target: Any) -> ResourcePayload:
        manifest = context.export.delivery_manifest(target.snapshot_id)
        if not manifest:
            raise MCPResourceNotFound(
                f"交付 manifest 不存在：{target.snapshot_id}",
                details={"snapshot_id": target.snapshot_id})
        registered = {str(row.get("path")): row
                      for row in (manifest.get("artifacts") or [])}
        row = registered.get(str(target.artifact_path))
        if row is None:
            raise MCPResourceNotFound(
                f"artifact 未登记：{target.artifact_path}",
                details={"snapshot_id": target.snapshot_id,
                         "known": sorted(registered)})
        data = context.export.delivery_artifact(target.snapshot_id,
                                                str(target.artifact_path))
        mime = str(row.get("mime_type") or mime_for(str(row.get("format") or "json")))
        return ResourcePayload(uri=target.uri, content=data, mime_type=mime,
                               notes=(f"checksum:{row.get('checksum')}",
                                      f"size:{row.get('size')}"))

    registry.register(ResourceSpec(
        uri="novelforge://novels/{novel_id}/delivery", name="delivery",
        description="交付快照列表（分页）", paginated=True, template=True,
        service="application.services.export.delivery_snapshots"),
        kinds=("delivery",), handler=snapshots_resource)
    registry.register(ResourceSpec(
        uri="novelforge://novels/{novel_id}/delivery/{snapshot_id}",
        name="delivery-snapshot", description="单个交付快照（钉住的 revision）",
        template=True, service="application.services.export.delivery_snapshot"),
        kinds=("delivery_snapshot",), handler=snapshot_resource)
    registry.register(ResourceSpec(
        uri="novelforge://novels/{novel_id}/delivery/{snapshot_id}/manifest",
        name="delivery-manifest", description="交付 manifest（artifact / checksum）",
        template=True, service="application.services.export.delivery_manifest"),
        kinds=("manifest",), handler=manifest_resource)
    registry.register(ResourceSpec(
        uri=("novelforge://novels/{novel_id}/delivery/{snapshot_id}"
             "/artifacts/{artifact_path}"),
        name="delivery-artifact",
        description="已登记的交付 artifact（MIME 按格式给出；不接受任意路径）",
        mime_type="application/octet-stream", template=True,
        service="application.services.export.delivery_artifact"),
        kinds=("artifact",), handler=artifact_resource)


__all__ = ["register"]
