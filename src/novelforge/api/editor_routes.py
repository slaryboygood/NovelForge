"""V4-06：Blueprint Editor 最小 API（thin routes）。

Router 只做协议转换与错误码映射；业务能力全部来自
`application.services.editor`（§7 / §52）。**不**直接 import
editor internals / BlueprintRepository / generation / quality evaluator。

```text
GET   /api/story-builder/editor/nodes/{node_id}            节点 + 质量摘要
GET   /api/story-builder/editor/nodes/{node_id}/revisions  revision history
GET   /api/story-builder/editor/nodes/{node_id}/diff       结构化 diff
PATCH /api/story-builder/editor/nodes/{node_id}            字段级 patch
POST  /api/story-builder/editor/nodes/{node_id}/rewrite    AI 字段级改写
POST  /api/story-builder/editor/nodes/{node_id}/accept     接受
POST  /api/story-builder/editor/nodes/{node_id}/reject     拒绝（只记录）
POST  /api/story-builder/editor/nodes/{node_id}/restore    恢复到新 revision
GET   /api/story-builder/editor/nodes/{node_id}/quality    当前 revision 的 issue
```

`novel_id` 必须显式传入（服务端不做磁盘推断，V4-01 ownership）。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import APIRouter, FastAPI, Query
from fastapi.responses import JSONResponse
from pydantic import Field

from novelforge.application.services.editor import editor_service
from novelforge.editor.errors import (
    EditorConflictError,
    EditorError,
    EditorNotFoundError,
    EditorOperationRejected,
    EditorOwnershipError,
    EditorPreserveViolation,
    EditorValidationError,
)
from novelforge.models import StrictModel


class PatchBody(StrictModel):
    novel_id: str = Field(min_length=1, max_length=96)
    changes: dict[str, Any] = Field(default_factory=dict)
    expected_revision: int | None = Field(default=None, ge=1)
    reason: str = Field(default="", max_length=400)
    idempotency_key: str = Field(default="", max_length=128)
    dry_run: bool = False


class RewriteBody(StrictModel):
    novel_id: str = Field(min_length=1, max_length=96)
    target_fields: list[str] = Field(min_length=1, max_length=12)
    instruction: str = Field(min_length=1, max_length=600)
    expected_revision: int | None = Field(default=None, ge=1)
    preserve_fields: list[str] = Field(default_factory=list, max_length=24)
    quality_issue_ids: list[str] = Field(default_factory=list, max_length=24)
    idempotency_key: str = Field(default="", max_length=128)
    dry_run: bool = False


class ReviewBody(StrictModel):
    novel_id: str = Field(min_length=1, max_length=96)
    revision: int | None = Field(default=None, ge=1)
    expected_revision: int | None = Field(default=None, ge=1)
    reason: str = Field(default="", max_length=400)
    idempotency_key: str = Field(default="", max_length=128)


class RestoreBody(StrictModel):
    novel_id: str = Field(min_length=1, max_length=96)
    from_revision: int = Field(ge=1)
    expected_revision: int | None = Field(default=None, ge=1)
    reason: str = Field(default="", max_length=400)
    idempotency_key: str = Field(default="", max_length=128)


def _status_for(exc: EditorError) -> int:
    if isinstance(exc, EditorNotFoundError):
        return 404
    if isinstance(exc, EditorOwnershipError):
        return 403
    if isinstance(exc, EditorConflictError):
        return 409
    if isinstance(exc, EditorPreserveViolation):
        return 409
    if isinstance(exc, (EditorValidationError, EditorOperationRejected)):
        return 422
    return 400


def install_editor_api(app: FastAPI, project_root: Path, *,
                       gateway: Any = None, memory: Any = None) -> None:
    """装配 editor 路由（`gateway` / `memory` 由宿主注入；不配置时 AI 改写返回 422）。"""

    router = APIRouter(prefix="/api/story-builder/editor", tags=["editor"])

    def service_for(novel_id: str):
        return editor_service(project_root, novel_id, gateway=gateway, memory=memory)

    @router.get("/nodes/{node_id}")
    def get_node(node_id: str, novel_id: str = Query(min_length=3, max_length=96),
                 revision: int | None = Query(default=None, ge=1)) -> dict[str, Any]:
        return service_for(novel_id).get_node(node_id, revision)

    @router.get("/nodes/{node_id}/revisions")
    def get_revisions(node_id: str,
                      novel_id: str = Query(min_length=3, max_length=96)
                      ) -> dict[str, Any]:
        return service_for(novel_id).get_history(node_id)

    @router.get("/nodes/{node_id}/diff")
    def get_diff(node_id: str, novel_id: str = Query(min_length=3, max_length=96),
                 from_revision: int = Query(ge=1),
                 to_revision: int | None = Query(default=None, ge=1)
                 ) -> dict[str, Any]:
        return service_for(novel_id).diff(node_id, from_revision=from_revision,
                                         to_revision=to_revision)

    @router.get("/nodes/{node_id}/quality")
    def get_quality(node_id: str,
                    novel_id: str = Query(min_length=3, max_length=96),
                    revision: int | None = Query(default=None, ge=1)
                    ) -> dict[str, Any]:
        return service_for(novel_id).get_quality(node_id, revision=revision)

    @router.patch("/nodes/{node_id}")
    def patch_node(node_id: str, body: PatchBody) -> dict[str, Any]:
        return service_for(body.novel_id).patch(
            node_id, body.changes, expected_revision=body.expected_revision,
            reason=body.reason, idempotency_key=body.idempotency_key,
            dry_run=body.dry_run)

    @router.post("/nodes/{node_id}/rewrite")
    def rewrite_node(node_id: str, body: RewriteBody) -> dict[str, Any]:
        return service_for(body.novel_id).rewrite(
            node_id, body.target_fields, body.instruction,
            expected_revision=body.expected_revision,
            preserve_fields=body.preserve_fields,
            quality_issue_ids=body.quality_issue_ids,
            idempotency_key=body.idempotency_key, dry_run=body.dry_run)

    @router.post("/nodes/{node_id}/accept")
    def accept_node(node_id: str, body: ReviewBody) -> dict[str, Any]:
        return service_for(body.novel_id).accept(
            node_id, revision=body.revision, expected_revision=body.expected_revision,
            reason=body.reason, idempotency_key=body.idempotency_key)

    @router.post("/nodes/{node_id}/reject")
    def reject_node(node_id: str, body: ReviewBody) -> dict[str, Any]:
        return service_for(body.novel_id).reject(
            node_id, revision=body.revision, reason=body.reason,
            idempotency_key=body.idempotency_key)

    @router.post("/nodes/{node_id}/restore")
    def restore_node(node_id: str, body: RestoreBody) -> dict[str, Any]:
        return service_for(body.novel_id).restore(
            node_id, from_revision=body.from_revision,
            expected_revision=body.expected_revision, reason=body.reason,
            idempotency_key=body.idempotency_key)

    app.include_router(router)

    async def handle_editor_error(_request, exc: EditorError) -> JSONResponse:
        return JSONResponse(status_code=_status_for(exc), content={"detail": exc.as_dict()})

    app.add_exception_handler(EditorError, handle_editor_error)


__all__ = ["install_editor_api"]
