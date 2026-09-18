"""Blueprint Editor 工具（V4-08 §18–§21、§33–§36）：
MCP → application.services.editor（revision / preserve / idempotency / dry_run 语义完整保留）。
"""

from __future__ import annotations

from typing import Any, Callable, Mapping, Sequence

from pydantic import Field

from ..contracts import ToolResult
from ..uri import node_uri
from . import MCPInput, build_tool

EDITOR_ERRORS: tuple[str, ...] = (
    "MCP_INVALID_ARGUMENT", "MCP_NODE_NOT_FOUND", "MCP_REVISION_CONFLICT",
    "MCP_OWNERSHIP_MISMATCH", "MCP_PRESERVE_VIOLATION", "MCP_OPERATION_REJECTED",
    "MCP_LLM_UNAVAILABLE",
)


class PatchInput(MCPInput):
    novel_id: str = Field(min_length=1, max_length=96)
    node_id: str = Field(min_length=1, max_length=64)
    expected_revision: int = Field(ge=1)
    changes: dict[str, Any] = Field(min_length=1)
    reason: str = Field(default="", max_length=400)
    idempotency_key: str = Field(default="", max_length=128)
    dry_run: bool = False


class RewriteInput(MCPInput):
    novel_id: str = Field(min_length=1, max_length=96)
    node_id: str = Field(min_length=1, max_length=64)
    expected_revision: int = Field(ge=1)
    target_fields: list[str] = Field(min_length=1, max_length=12)
    instruction: str = Field(min_length=1, max_length=600)
    preserve_fields: list[str] = Field(default_factory=list, max_length=24)
    quality_issue_ids: list[str] = Field(default_factory=list, max_length=24)
    idempotency_key: str = Field(default="", max_length=128)
    dry_run: bool = False


class RegenerateInput(MCPInput):
    novel_id: str = Field(min_length=1, max_length=96)
    node_id: str = Field(min_length=1, max_length=64)
    expected_revision: int = Field(ge=1)
    preserve: list[str] = Field(default_factory=list, max_length=24)
    idempotency_key: str = Field(default="", max_length=128)


class AcceptInput(MCPInput):
    novel_id: str = Field(min_length=1, max_length=96)
    node_id: str = Field(min_length=1, max_length=64)
    expected_revision: int | None = Field(default=None, ge=1)
    revision: int | None = Field(default=None, ge=1)
    reason: str = Field(default="", max_length=400)
    idempotency_key: str = Field(default="", max_length=128)


class RejectInput(MCPInput):
    novel_id: str = Field(min_length=1, max_length=96)
    node_id: str = Field(min_length=1, max_length=64)
    revision: int | None = Field(default=None, ge=1)
    reason: str = Field(default="", max_length=400)
    idempotency_key: str = Field(default="", max_length=128)


class RestoreInput(MCPInput):
    novel_id: str = Field(min_length=1, max_length=96)
    node_id: str = Field(min_length=1, max_length=64)
    from_revision: int = Field(ge=1)
    expected_revision: int | None = Field(default=None, ge=1)
    reason: str = Field(default="", max_length=400)
    idempotency_key: str = Field(default="", max_length=128)


class DiffInput(MCPInput):
    novel_id: str = Field(min_length=1, max_length=96)
    node_id: str = Field(min_length=1, max_length=64)
    from_revision: int = Field(ge=1)
    to_revision: int | None = Field(default=None, ge=1)
    include_quality: bool = True


def _patch(context: Any, payload: PatchInput) -> ToolResult:
    result = context.editor.patch(
        payload.node_id, payload.changes,
        expected_revision=payload.expected_revision, reason=payload.reason,
        idempotency_key=payload.idempotency_key, dry_run=payload.dry_run)
    return ToolResult(
        operation="patch_blueprint_node", novel_id=payload.novel_id,
        ok=bool(result.get("ok")),
        revision=int(result.get("revision") or 0),
        revision_before=int(result.get("before_revision") or 0),
        dry_run=bool(result.get("dry_run")), result=result,
        resources=(node_uri(payload.novel_id, payload.node_id),),
        summary=f"patch {payload.node_id} → revision {result.get('revision')}")


def _rewrite(context: Any, payload: RewriteInput) -> ToolResult:
    result = context.editor.rewrite(
        payload.node_id, payload.target_fields, payload.instruction,
        expected_revision=payload.expected_revision,
        preserve_fields=payload.preserve_fields,
        quality_issue_ids=payload.quality_issue_ids,
        idempotency_key=payload.idempotency_key, dry_run=payload.dry_run)
    return ToolResult(
        operation="rewrite_blueprint_node", novel_id=payload.novel_id,
        ok=bool(result.get("ok")), revision=int(result.get("revision") or 0),
        revision_before=int(result.get("before_revision") or 0),
        dry_run=bool(result.get("dry_run")), result=result,
        usage=dict(result.get("usage") or {}),
        resources=(node_uri(payload.novel_id, payload.node_id),),
        summary=(f"rewrite {payload.target_fields} → revision "
                 f"{result.get('revision')}"))


def _regenerate(context: Any, payload: RegenerateInput) -> ToolResult:
    result = context.editor.regenerate(
        payload.node_id, expected_revision=payload.expected_revision,
        preserve=tuple(payload.preserve), idempotency_key=payload.idempotency_key)
    return ToolResult(
        operation="regenerate_blueprint_node", novel_id=payload.novel_id,
        ok=bool(result.get("ok")), revision=int(result.get("revision") or 0),
        result=result, resources=(node_uri(payload.novel_id, payload.node_id),),
        summary=f"regenerate {payload.node_id} → revision {result.get('revision')}")


def _accept(context: Any, payload: AcceptInput) -> ToolResult:
    result = context.editor.accept(
        payload.node_id, revision=payload.revision,
        expected_revision=payload.expected_revision, reason=payload.reason,
        idempotency_key=payload.idempotency_key)
    return ToolResult(
        operation="accept_revision", novel_id=payload.novel_id,
        ok=bool(result.get("ok")), revision=int(result.get("revision") or 0),
        result=result, resources=(node_uri(payload.novel_id, payload.node_id),),
        summary=(f"accept r{result.get('reviewed_revision')} → "
                 f"r{result.get('revision')}（quality pass ≠ accepted）"))


def _reject(context: Any, payload: RejectInput) -> ToolResult:
    result = context.editor.reject(payload.node_id, revision=payload.revision,
                                   reason=payload.reason,
                                   idempotency_key=payload.idempotency_key)
    return ToolResult(
        operation="reject_revision", novel_id=payload.novel_id,
        ok=bool(result.get("ok")), revision=int(result.get("revision") or 0),
        result=result, summary=(f"reject r{result.get('reviewed_revision')}"
                                "（revision 保留，仅记录评审决定）"))


def _restore(context: Any, payload: RestoreInput) -> ToolResult:
    result = context.editor.restore(
        payload.node_id, from_revision=payload.from_revision,
        expected_revision=payload.expected_revision, reason=payload.reason,
        idempotency_key=payload.idempotency_key)
    return ToolResult(
        operation="restore_revision", novel_id=payload.novel_id,
        ok=bool(result.get("ok")), revision=int(result.get("revision") or 0),
        revision_before=int(result.get("before_revision") or 0), result=result,
        resources=(node_uri(payload.novel_id, payload.node_id),),
        summary=(f"restore r{payload.from_revision} → 新 revision "
                 f"{result.get('revision')}（历史保留）"))


def _diff(context: Any, payload: DiffInput) -> ToolResult:
    result = context.editor.diff(payload.node_id, from_revision=payload.from_revision,
                                 to_revision=payload.to_revision)
    return ToolResult(
        operation="diff_revisions", novel_id=payload.novel_id,
        ok=True, revision=int(result.get("revision_after") or 0),
        revision_before=int(result.get("revision_before") or 0),
        result=dict(result),
        resources=(node_uri(payload.novel_id, payload.node_id),),
        summary=f"diff r{payload.from_revision}..{payload.to_revision}")


def register(registry: Any) -> None:
    tools = (
        dict(name="patch_blueprint_node", description="字段级修改 Blueprint 节点（产生新 revision）",
             dto=PatchInput, impl=_patch, requires_revision=True, supports_dry_run=True,
             service="application.services.editor.patch"),
        dict(name="rewrite_blueprint_node", description="AI 只改指定字段（preserve 硬约束）",
             dto=RewriteInput, impl=_rewrite, requires_revision=True,
             supports_dry_run=True, expensive=True,
             service="application.services.editor.rewrite"),
        dict(name="regenerate_blueprint_node", description="整节点重新生成（proposal）",
             dto=RegenerateInput, impl=_regenerate, requires_revision=True,
             expensive=True, service="application.services.editor.regenerate"),
        dict(name="accept_revision", description="显式接受某个 revision（不自动接受）",
             dto=AcceptInput, impl=_accept, requires_revision=False,
             service="application.services.editor.accept"),
        dict(name="reject_revision", description="拒绝某个 revision（只记录评审决定）",
             dto=RejectInput, impl=_reject, requires_revision=False,
             service="application.services.editor.reject"),
        dict(name="restore_revision", description="用历史 revision 内容创建新 revision",
             dto=RestoreInput, impl=_restore, requires_revision=True,
             service="application.services.editor.restore"),
        dict(name="diff_revisions", description="比较同一节点的两个 revision（只读）",
             dto=DiffInput, impl=_diff, requires_revision=False, read_only=True,
             service="application.services.editor.diff"),
    )
    for row in tools:
        spec, handler = build_tool(
            output_schema={"type": "object"},
            possible_errors=EDITOR_ERRORS, idempotent=True, **row)
        registry.register(spec, handler)


__all__ = [
    "AcceptInput", "DiffInput", "EDITOR_ERRORS", "PatchInput", "RegenerateInput",
    "RejectInput", "RestoreInput", "RewriteInput", "register",
]
