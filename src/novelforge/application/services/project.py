"""ProjectService —— 作品生命周期（V4-01，ADR-001）。

收编 interface 层里关于作品本身的编排：
列表 / 读取 / 创建 / 重命名 / 归档（= 删除）。

注意：这里**不**做作品个数、当前作品一类的隐式推断；每个方法都必须显式给出 novel_id
（除列表方法外）。任何"磁盘上有别的作品就混进当前操作"的行为都是被禁止的。

接口层只 import 本模块（含 `NovelProfileError` / `DEFAULT_NOVEL_ID` 的重导出），
不直接依赖 domain ——这是 `tests/v4/isolation/test_module_boundaries.py` 守卫的边界。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from novelforge.story_engine.profile import (
    DEFAULT_NOVEL_ID,
    NovelProfile,
    NovelProfileError,
    NovelProfileRepository,
)
from novelforge.story_engine.templates import apply_template

from .novel_admin import archive_novel, rename_novel


class ProjectService:
    """作品（novel）生命周期的唯一服务入口。"""

    def __init__(self, project_root: Path | str) -> None:
        self.project_root = Path(project_root)
        self.profiles = NovelProfileRepository(self.project_root)

    # ------------------------------------------------------------------ 读
    def list_novels(self) -> list[dict[str, Any]]:
        return [self.summary(item) for item in self.profiles.list()]

    @staticmethod
    def summary(profile: NovelProfile) -> dict[str, Any]:
        return {"novel_id": profile.novel_id, "title": profile.title,
                "genre": profile.genre,
                "updated_at": profile.updated_at.isoformat(),
                "cast": len(profile.cast), "factions": len(profile.factions)}

    def get_novel(self, novel_id: str) -> dict[str, Any]:
        return self.profiles.load(novel_id).model_dump(mode="json")

    # ------------------------------------------------------------------ 写
    def create_novel(self, novel_id: str, *, title: str = "", genre: str = "",
                     content_pack_id: str = "", template_id: str = ""
                     ) -> dict[str, Any]:
        profile = self.profiles.create(novel_id, title=title, genre=genre,
                                       content_pack_id=content_pack_id)
        if template_id:
            profile = self.profiles.save(apply_template(profile, template_id))
        return profile.model_dump(mode="json")

    def rename_novel(self, novel_id: str, title: str) -> dict[str, Any]:
        return rename_novel(self.project_root, novel_id, title)

    def archive_novel(self, novel_id: str, *, reason: str = "") -> dict[str, Any]:
        return archive_novel(self.project_root, novel_id, reason=reason)


def project_service(project_root: Path | str) -> ProjectService:
    return ProjectService(project_root)


__all__ = ["DEFAULT_NOVEL_ID", "NovelProfileError", "ProjectService",
           "project_service"]

