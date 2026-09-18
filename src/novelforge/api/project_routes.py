"""V4：作品生命周期 REST（唯一 owner 是 application ProjectService）。

```text
GET    /api/story-builder/novels                作品列表
POST   /api/story-builder/novels                新建作品（可选题材模板）
GET    /api/story-builder/novels/{novel_id}     作品档案
PATCH  /api/story-builder/novels/{novel_id}     重命名（只改作者可见名字）
DELETE /api/story-builder/novels/{novel_id}     删除＝整体归档（二次确认）
```

URL 与原 Story Builder router 保持一致（`docs/v4/V4_POST_RELEASE_CLEANUP` §40：
删除 legacy owner 不改变对当前 Studio 有价值的 URL）。
Route 只做协议转换与错误码映射，业务能力全部来自
`application.services.project.ProjectService`。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import APIRouter, FastAPI, HTTPException, Query
from fastapi.responses import JSONResponse
from pydantic import Field

from novelforge.application.services.novel_admin import NovelAdminError
from novelforge.application.services.project import (
    DEFAULT_NOVEL_ID,
    NovelProfileError,
    project_service,
)
from novelforge.models import StrictModel


class CreateNovelRequest(StrictModel):
    novel_id: str = Field(default=DEFAULT_NOVEL_ID, min_length=3, max_length=96)
    title: str = Field(default="", max_length=120)
    genre: str = Field(default="", max_length=64)
    template_id: str = Field(default="", max_length=64)
    content_pack_id: str = Field(default="", max_length=64)


class NovelRenameRequest(StrictModel):
    """NF-011：作品重命名（只改作者可见名字）。"""

    title: str = Field(min_length=1, max_length=120)


def install_project_api(app: FastAPI, project_root: Path) -> None:
    """装配作品生命周期路由（含 NovelProfileError / NovelAdminError 的稳定错误码）。"""

    router = APIRouter(prefix="/api/story-builder", tags=["作品管理"])

    @router.get("/novels")
    def list_novels() -> dict[str, Any]:
        return {"novels": project_service(project_root).list_novels()}

    @router.post("/novels", status_code=201)
    def create_novel(body: CreateNovelRequest) -> dict[str, Any]:
        novel = project_service(project_root).create_novel(
            body.novel_id, title=body.title, genre=body.genre,
            content_pack_id=body.content_pack_id, template_id=body.template_id)
        return {"novel": novel}

    @router.get("/novels/{novel_id}")
    def get_novel(novel_id: str) -> dict[str, Any]:
        return {"novel": project_service(project_root).get_novel(novel_id)}

    @router.patch("/novels/{novel_id}")
    def rename_novel_route(novel_id: str, body: NovelRenameRequest) -> dict[str, Any]:
        """NF-011：改作者可见的作品名（只改名字，不动任何事实）。"""

        try:
            return project_service(project_root).rename_novel(novel_id, body.title)
        except NovelAdminError as exc:
            raise HTTPException(status_code=_admin_status(exc),
                                detail=exc.as_dict()) from exc

    @router.delete("/novels/{novel_id}")
    def delete_novel_route(novel_id: str, confirm: bool = Query(default=False),
                           reason: str = Query(default="", max_length=200)
                           ) -> dict[str, Any]:
        """NF-011：删除作品＝整体归档（二次确认 + 可恢复 + 不留孤儿）。"""

        if not confirm:
            raise HTTPException(status_code=409, detail={
                "code": "NOVEL_DELETE_UNCONFIRMED",
                "message": "删除作品需要二次确认：请带上 confirm=true。",
                "novel_id": novel_id})
        try:
            return project_service(project_root).archive_novel(novel_id, reason=reason)
        except NovelAdminError as exc:
            raise HTTPException(status_code=_admin_status(exc),
                                detail=exc.as_dict()) from exc

    app.include_router(router)

    async def handle_profile_error(_request, exc: NovelProfileError):
        status = (404 if exc.code == "PROFILE_NOT_FOUND"
                  else 409 if exc.code == "PROFILE_EXISTS" else 422)
        return JSONResponse(status_code=status, content={"detail": exc.as_dict()})

    async def handle_novel_admin_error(_request, exc: NovelAdminError):
        return JSONResponse(status_code=_admin_status(exc),
                            content={"detail": exc.as_dict()})

    app.add_exception_handler(NovelProfileError, handle_profile_error)
    app.add_exception_handler(NovelAdminError, handle_novel_admin_error)


def _admin_status(exc: NovelAdminError) -> int:
    return 404 if exc.code == "PROFILE_NOT_FOUND" else 422


__all__ = ["CreateNovelRequest", "DEFAULT_NOVEL_ID", "NovelRenameRequest",
           "install_project_api"]
