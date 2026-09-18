"""Blueprint / 节点 / revision / 场景资源（V4-08 §11–§14、§47–§48）。

数据来源：`application.services.export.blueprint_view`（机器视图，只读）
与 `application.services.editor`（revision 视图）。
"""

from __future__ import annotations

from typing import Any, Iterable, Mapping

from ..contracts import ResourceSpec
from ..errors import MCPNodeNotFound
from ..payloads import ResourcePayload, json_payload
from ..registry import MCPResourceRegistry
from ..uri import node_uri, revision_uri


def _view(context: Any, *, mode: str, include_types: Iterable[str] = ()) -> dict[str, Any]:
    return context.export.blueprint_view(selection_mode=mode,
                                         include_node_types=tuple(include_types))


def _nodes(view: Mapping[str, Any]) -> list[dict[str, Any]]:
    return [dict(row) for row in (view.get("blueprint") or {}).get("nodes") or []]


def _node_row(view: Mapping[str, Any], node_id: str) -> dict[str, Any]:
    for row in _nodes(view):
        if str(row.get("node_id")) == str(node_id):
            return row
    raise MCPNodeNotFound(f"Blueprint 节点不存在：{node_id}",
                          details={"node_id": node_id})


def _page(target: Any, rows: list[dict[str, Any]]) -> dict[str, Any]:
    from ..uri import paginate

    return paginate(rows, limit=target.limit, cursor=target.cursor)


def register(registry: MCPResourceRegistry, *, spec_source: Any = None) -> None:
    def novel_resource(context: Any, target: Any) -> ResourcePayload:
        return json_payload(target.uri, context.summary())

    def blueprint_resource(context: Any, target: Any) -> ResourcePayload:
        view = _view(context, mode=target.mode)
        page = _page(target, _nodes(view))
        payload = {"novel_id": view.get("novel_id"),
                   "schema_version": (view.get("snapshot") or {}).get("schema_version"),
                   "selection_mode": target.mode,
                   "ordering": (view.get("blueprint") or {}).get("ordering"),
                   "quality_summary": view.get("quality_summary"),
                   "excluded": view.get("excluded"),
                   **page}
        return json_payload(target.uri, payload)

    def node_resource(context: Any, target: Any) -> ResourcePayload:
        row = _node_row(_view(context, mode=target.mode), target.node_id)
        payload = {"novel_id": target.novel_id, "node": row,
                   "resources": [node_uri(target.novel_id, target.node_id),
                                 revision_uri(target.novel_id, target.node_id,
                                              int(row.get("revision") or 0))],
                   "note": ("payload 为 Blueprint 节点内容；provenance 为安全子集"
                            "（不含 prompt / secret / 本地路径）")}
        return json_payload(target.uri, payload)

    def revision_resource(context: Any, target: Any) -> ResourcePayload:
        node = context.editor.get_node(target.node_id, target.revision)
        payload = {"novel_id": target.novel_id, "node_id": target.node_id,
                   "revision": int(target.revision),
                   "view": dict(node.get("view") or {}),
                   "editable_fields": list(node.get("editable_fields") or []),
                   "protected_fields": list(node.get("protected_fields") or []),
                   "node": dict(node.get("node") or {}),
                   "review": context.editor.review_for(target.node_id,
                                                       int(target.revision))}
        return json_payload(target.uri, payload)

    def scenes_resource(context: Any, target: Any) -> ResourcePayload:
        view = _view(context, mode=target.mode, include_types=("scene",))
        rows = [{"node_id": row.get("node_id"), "revision": row.get("revision"),
                 "status": row.get("status"), "review_status": row.get("review_status"),
                 "quality": row.get("quality"),
                 "payload": {key: value for key, value in
                             (row.get("visible") or {}).items()}}
                for row in _nodes(view)]
        page = _page(target, rows)
        return json_payload(target.uri, {"novel_id": target.novel_id,
                                         "selection_mode": target.mode, **page})

    registry.register(ResourceSpec(
        uri="novelforge://novels/{novel_id}", name="novel",
        description="作品摘要（元数据 / 进度 / 计数）", template=True,
        service="application.services.facade.ApplicationServices.summary"),
        kinds=("novel",), handler=novel_resource)
    registry.register(ResourceSpec(
        uri="novelforge://novels/{novel_id}/blueprint", name="blueprint",
        description="有序 Story Blueprint（分页；每节点 revision / status / quality）",
        paginated=True, template=True,
        service="application.services.export.blueprint_view"),
        kinds=("blueprint",), handler=blueprint_resource)
    registry.register(ResourceSpec(
        uri="novelforge://novels/{novel_id}/blueprint/nodes/{node_id}", name="node",
        description="单个 Blueprint 节点（含 revision / status / quality / review）",
        template=True, service="application.services.export.blueprint_view"),
        kinds=("node",), handler=node_resource)
    registry.register(ResourceSpec(
        uri="novelforge://novels/{novel_id}/blueprint/nodes/{node_id}/revisions/{revision}",
        name="revision", description="某个 revision 的视图（可编辑 / 受保护字段）",
        template=True, service="application.services.editor.get_node"),
        kinds=("revision",), handler=revision_resource)
    registry.register(ResourceSpec(
        uri="novelforge://novels/{novel_id}/scenes", name="scenes",
        description="场景列表（分页；visible 字段）", paginated=True, template=True,
        service="application.services.export.blueprint_view"),
        kinds=("scenes",), handler=scenes_resource)


__all__ = ["register"]
