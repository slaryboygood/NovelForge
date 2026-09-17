"""C07：章节稳定身份与 lineage（chapter_uuid 稳定，display_number 可变）。"""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from novelforge.models import StrictModel

from .ids import new_random_key
from .repository import CanonRepository

ChapterStatus = Literal["active", "superseded", "merged"]


class ChapterLineage(StrictModel):
    chapter_uuid: str = Field(min_length=3, max_length=128)
    novel_id: str = Field(min_length=1, max_length=96)
    display_number: int | None = Field(default=None, ge=0)
    status: ChapterStatus = "active"
    superseded_by: list[str] = Field(default_factory=list)
    merged_into: str = Field(default="", max_length=128)
    context_manifest_id: str = Field(default="", max_length=80)
    title: str = Field(default="", max_length=160)


class ChapterLineageStore:
    """把 lineage 存在既有 Canon DB 内（schema v3 增加 canon_chapter_lineage），不另建存储。"""

    def __init__(self, repository: CanonRepository) -> None:
        self.repository = repository

    @staticmethod
    def new_uuid() -> str:
        return f"uuid_{new_random_key().lower()}"

    def register(self, chapter: ChapterLineage) -> None:
        with self.repository.transaction() as connection:
            connection.execute(
                "INSERT INTO canon_chapter_lineage(chapter_uuid, novel_id, display_number, "
                "status, superseded_by, merged_into, context_manifest_id, title) "
                "VALUES (?,?,?,?,?,?,?,?) "
                "ON CONFLICT(chapter_uuid) DO UPDATE SET display_number=excluded.display_number, "
                "status=excluded.status, superseded_by=excluded.superseded_by, "
                "merged_into=excluded.merged_into, "
                "context_manifest_id=excluded.context_manifest_id, title=excluded.title",
                (chapter.chapter_uuid, chapter.novel_id, chapter.display_number, chapter.status,
                 ",".join(chapter.superseded_by), chapter.merged_into,
                 chapter.context_manifest_id, chapter.title))

    def get(self, chapter_uuid: str) -> ChapterLineage | None:
        row = self.repository._connection.execute(
            "SELECT * FROM canon_chapter_lineage WHERE chapter_uuid = ?",
            (chapter_uuid,)).fetchone()
        if row is None:
            return None
        return ChapterLineage(
            chapter_uuid=row["chapter_uuid"], novel_id=row["novel_id"],
            display_number=row["display_number"], status=row["status"],
            superseded_by=[item for item in (row["superseded_by"] or "").split(",") if item],
            merged_into=row["merged_into"], context_manifest_id=row["context_manifest_id"],
            title=row["title"])

    def renumber(self, novel_id: str, mapping: dict[str, int]) -> int:
        """只改 display_number；chapter_uuid 不变。"""

        changed = 0
        with self.repository.transaction() as connection:
            for chapter_uuid, display_number in mapping.items():
                cursor = connection.execute(
                    "UPDATE canon_chapter_lineage SET display_number = ? "
                    "WHERE chapter_uuid = ? AND novel_id = ?",
                    (display_number, chapter_uuid, novel_id))
                changed += cursor.rowcount
        return changed

    def split(self, chapter_uuid: str, *, novel_id: str) -> tuple[str, str]:
        """拆章：旧 uuid 标记 superseded_by，生成两个新 uuid。"""

        old = self.get(chapter_uuid)
        if old is None:
            raise KeyError(chapter_uuid)
        first, second = self.new_uuid(), self.new_uuid()
        self.register(old.model_copy(update={"status": "superseded",
                                             "superseded_by": [first, second]}))
        self.register(ChapterLineage(chapter_uuid=first, novel_id=novel_id,
                                     title=f"{old.title}（上）"))
        self.register(ChapterLineage(chapter_uuid=second, novel_id=novel_id,
                                     title=f"{old.title}（下）"))
        return first, second

    def merge(self, chapter_uuids: list[str], *, novel_id: str, title: str = "") -> str:
        """合章：旧 uuid 标记 merged_into，生成一个新 uuid。"""

        merged_uuid = self.new_uuid()
        for chapter_uuid in chapter_uuids:
            old = self.get(chapter_uuid)
            if old is None:
                raise KeyError(chapter_uuid)
            self.register(old.model_copy(update={"status": "merged",
                                                 "merged_into": merged_uuid}))
        self.register(ChapterLineage(chapter_uuid=merged_uuid, novel_id=novel_id, title=title))
        return merged_uuid
