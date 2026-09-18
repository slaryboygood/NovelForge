"""Delivery 工具（V4-08 §25–§27、§72）：
MCP → application.services.export → DeliveryService（不暴露 legacy 导出路径）。
"""

from __future__ import annotations

from typing import Any, Callable, Mapping, Sequence

from pydantic import Field

from ..contracts import ToolResult
from ..errors import MCPDeliveryBlocked
from ..uri import delivery_uri, manifest_uri
from . import MCPInput, build_tool

DELIVERY_ERRORS: tuple[str, ...] = (
    "MCP_INVALID_ARGUMENT", "MCP_OWNERSHIP_MISMATCH", "MCP_DELIVERY_BLOCKED",
)


class SelectionInput(MCPInput):
    novel_id: str = Field(min_length=1, max_length=96)
    selection_mode: str = Field(default="accepted", max_length=32)
    profile: str = Field(default="author", max_length=32)
    formats: list[str] = Field(default_factory=lambda: ["json"], max_length=4)
    include_node_types: list[str] = Field(default_factory=list, max_length=16)
    require_accepted: bool = True
    require_quality_pass: bool = True
    include_quality_report: bool | None = None
    include_provenance: bool | None = None


class ValidateDeliveryInput(SelectionInput):
    pass


class SnapshotInput(SelectionInput):
    idempotency_key: str = Field(default="", max_length=128)


class DeliverInput(SelectionInput):
    idempotency_key: str = Field(default="", max_length=128)
    dry_run: bool = False


def _selection(context: Any, payload: SelectionInput) -> Any:
    """DeliverySelection 由 Application 层组装（MCP 不 import delivery，§7）。"""

    return context.delivery_selection(
        selection_mode=payload.selection_mode, profile=payload.profile,
        formats=tuple(payload.formats),
        include_node_types=tuple(payload.include_node_types),
        require_accepted=payload.require_accepted,
        require_quality_pass=payload.require_quality_pass,
        include_quality_report=payload.include_quality_report,
        include_provenance=payload.include_provenance)


def _validate(context: Any, payload: ValidateDeliveryInput) -> ToolResult:
    selection = _selection(context, payload)
    result = context.export.validate_delivery(selection)
    validation = dict(result.get("validation") or {})
    return ToolResult(
        operation="validate_delivery", novel_id=payload.novel_id,
        ok=bool(validation.get("ok")),
        result={"validation": validation, "snapshot": dict(result.get("snapshot") or {})},
        resources=(delivery_uri(payload.novel_id),),
        summary=(f"delivery validation ok={validation.get('ok')}，"
                 f"blockers={len(validation.get('issues') or [])}"))


def _snapshot(context: Any, payload: SnapshotInput) -> ToolResult:
    selection = _selection(context, payload)
    snapshot = context.export.create_snapshot(selection)
    return ToolResult(
        operation="create_delivery_snapshot", novel_id=payload.novel_id, ok=True,
        revision=0, result=snapshot,
        resources=(delivery_uri(payload.novel_id),
                   manifest_uri(payload.novel_id, str(snapshot.get("snapshot_id")))),
        summary=(f"delivery snapshot {snapshot.get('snapshot_id')}（"
                 f"{len(snapshot.get('node_revisions') or {})} 个 revision）"))


def _deliver(context: Any, payload: DeliverInput) -> ToolResult:
    selection = _selection(context, payload)
    result = context.export.deliver(selection,
                                    idempotency_key=payload.idempotency_key,
                                    dry_run=payload.dry_run)
    status = str(result.get("status") or "")
    if status == "blocked":
        validation = dict(result.get("validation") or {})
        raise MCPDeliveryBlocked(
            str(validation.get("blocking_reason")
                or "交付被阻止（未写入任何 artifact）"),
            cause="DELIVERY_VALIDATION_FAILED",
            details={"issues": [row.get("code") for row
                                in (validation.get("issues") or [])][:10],
                     "novel_id": payload.novel_id,
                     "snapshot_id": str(result.get("snapshot_id") or "")})
    snapshot_id = str(result.get("snapshot_id") or "")
    return ToolResult(
        operation="deliver_blueprint", novel_id=payload.novel_id,
        ok=status in ("delivered", "dry_run"), dry_run=bool(result.get("dry_run")),
        revision=0, result=result,
        resources=(delivery_uri(payload.novel_id),
                   manifest_uri(payload.novel_id, snapshot_id)) if snapshot_id else (),
        usage=dict(result.get("usage") or {}),
        summary=(f"delivery status={status}，artifacts="
                 f"{len(result.get('artifacts') or [])}"))


def register(registry: Any) -> None:
    rows = (
        dict(name="validate_delivery", description="交付前校验（只读，不写文件）",
             dto=ValidateDeliveryInput, impl=_validate, read_only=True,
             supports_dry_run=True,
             service="application.services.export.validate_delivery"),
        dict(name="create_delivery_snapshot",
             description="钉住交付 revision 快照（不生成 artifact）",
             dto=SnapshotInput, impl=_snapshot, read_only=False,
             service="application.services.export.create_snapshot"),
        dict(name="deliver_blueprint",
             description="生成交付物（默认 accepted；原子发布 + manifest + checksum）",
             dto=DeliverInput, impl=_deliver, expensive=False, supports_dry_run=True,
             service="application.services.export.deliver"),
    )
    for row in rows:
        spec, handler = build_tool(output_schema={"type": "object"},
                                   possible_errors=DELIVERY_ERRORS, idempotent=True,
                                   **row)
        registry.register(spec, handler)


__all__ = ["DELIVERY_ERRORS", "DeliverInput", "SelectionInput", "SnapshotInput",
           "ValidateDeliveryInput", "register"]
