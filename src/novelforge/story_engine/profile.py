"""Novel Profile：小说实例配置（主计划 T06d）。

分层约定
--------
- Story Engine：通用运行规则，不含任何具体小说的内容。
- Novel Profile（本文件）：一本小说自己的题材标识、基调、人物与内容目录。
- Genre Template（T06e）：某类题材的默认目录，可被 Novel Profile 覆盖。
- Content Pack（T13b）：小说实例的素材文件。

`novel_id` 同时是数据分区键，与现有 session / blueprint / outline 使用的
`project_id` 保持一致，避免出现第二套分区概念。

引擎默认值里不放任何一本具体小说的配置：`DEFAULT_NOVEL_ID` 只用于兼容
旧会话（旧数据默认使用 `novel_project`），不是内容默认值。
"""

from __future__ import annotations

import json
import os
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from pydantic import Field, ValidationError, model_validator

from novelforge.models import StrictModel

from .entities import Ability, Character, Faction, ResourceDefinition

NOVEL_PROFILE_SCHEMA_VERSION = 1
NOVEL_ID_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9_-]{2,95}$"
DEFAULT_NOVEL_ID = "novel_project"
DEFAULT_PROFILES_PATH = Path("novel/authoring/story_engine/profiles")


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class NovelProfileError(ValueError):
    """Novel Profile 读写失败。"""

    def __init__(self, code: str, message: str, *, novel_id: str = "") -> None:
        self.code = code
        self.message = message
        self.novel_id = novel_id
        super().__init__(message)

    def as_dict(self) -> dict[str, str]:
        return {"code": self.code, "message": self.message, "novel_id": self.novel_id}


class NovelProfile(StrictModel):
    """一本小说的实例配置。字段全部题材无关，具体内容由作者或模板填入。"""

    schema_version: Literal[1] = NOVEL_PROFILE_SCHEMA_VERSION
    novel_id: str = Field(pattern=NOVEL_ID_PATTERN)
    title: str = Field(default="", max_length=120)
    genre: str = Field(default="", max_length=64)
    template_id: str = Field(default="", max_length=64)
    content_pack_id: str = Field(default="", max_length=64)
    themes: list[str] = Field(default_factory=list)
    tone: str = Field(default="", max_length=200)
    narrative_style: str = Field(default="", max_length=200)
    world_profile: dict[str, Any] = Field(default_factory=dict)
    cast: dict[str, Character] = Field(default_factory=dict)
    factions: dict[str, Faction] = Field(default_factory=dict)
    resource_catalog: dict[str, ResourceDefinition] = Field(default_factory=dict)
    ability_catalog: dict[str, Ability] = Field(default_factory=dict)
    event_catalog: dict[str, dict[str, Any]] = Field(default_factory=dict)
    story_rules: list[str] = Field(default_factory=list)
    # 导演权重：作者可调，但评分算法仍然只在 director.py 里实现。
    director_weights: dict[str, float] = Field(default_factory=dict)
    # 未来规划：只描述目标阶段，不是已发生事实；重规划只影响未来。
    future_plan: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)

    @model_validator(mode="after")
    def keys_match_ids(self) -> "NovelProfile":
        for name, entries in (("cast", self.cast), ("factions", self.factions),
                              ("resource_catalog", self.resource_catalog),
                              ("ability_catalog", self.ability_catalog)):
            for key, entry in entries.items():
                if key != entry.id:
                    raise ValueError(f"{name} key must match entry id")
        return self


class StoredNovelProfile(StrictModel):
    schema_version: Literal[1] = NOVEL_PROFILE_SCHEMA_VERSION
    profile: NovelProfile


class NovelProfileRepository:
    """每本小说一个独立文件；切换小说只切换 profile，不互相写入。"""

    def __init__(self, project_root: Path, profiles_path: Path | str = DEFAULT_PROFILES_PATH) -> None:
        self.project_root = project_root.resolve()
        relative = Path(profiles_path)
        self.profiles_dir = (
            relative.resolve() if relative.is_absolute() else (self.project_root / relative).resolve()
        )
        try:
            self.profiles_dir.relative_to(self.project_root)
        except ValueError as exc:
            raise NovelProfileError("PROFILE_PATH_OUTSIDE_PROJECT", "小说配置目录超出当前项目范围") from exc

    def path_for(self, novel_id: str) -> Path:
        if not re.fullmatch(NOVEL_ID_PATTERN, novel_id):
            raise NovelProfileError("NOVEL_ID_INVALID", "小说编号格式不正确", novel_id=novel_id)
        return self.profiles_dir / f"{novel_id}.json"

    def exists(self, novel_id: str) -> bool:
        return self.path_for(novel_id).is_file()

    def save(self, profile: NovelProfile) -> NovelProfile:
        target = self.path_for(profile.novel_id)
        stored = StoredNovelProfile(profile=profile.model_copy(update={"updated_at": utc_now()}))
        self._atomic_write(target, stored)
        return stored.profile

    def create(self, novel_id: str, *, title: str = "", genre: str = "", **fields: Any) -> NovelProfile:
        if self.exists(novel_id):
            raise NovelProfileError("PROFILE_EXISTS", "这本小说已经存在", novel_id=novel_id)
        return self.save(NovelProfile(novel_id=novel_id, title=title, genre=genre, **fields))

    def ensure(self, novel_id: str, *, title: str = "") -> NovelProfile:
        """兼容读取：旧会话没有 profile 时按需创建一个最小实例，不迁移旧数据。"""

        if self.exists(novel_id):
            return self.load(novel_id)
        return self.create(novel_id, title=title or novel_id)

    def load(self, novel_id: str) -> NovelProfile:
        path = self.path_for(novel_id)
        if not path.is_file():
            raise NovelProfileError("PROFILE_NOT_FOUND", "找不到这本小说的配置", novel_id=novel_id)
        try:
            stored = StoredNovelProfile.model_validate(json.loads(path.read_text(encoding="utf-8-sig")))
        except (OSError, UnicodeError, json.JSONDecodeError, ValidationError) as exc:
            raise NovelProfileError("PROFILE_READ_FAILED", "无法读取小说配置", novel_id=novel_id) from exc
        if stored.profile.novel_id != novel_id:
            raise NovelProfileError("PROFILE_ID_MISMATCH", "文件名与小说编号不一致", novel_id=novel_id)
        return stored.profile

    def list(self) -> list[NovelProfile]:
        if not self.profiles_dir.exists():
            return []
        profiles = []
        for path in sorted(self.profiles_dir.glob("*.json")):
            try:
                profiles.append(self.load(path.stem))
            except NovelProfileError:
                continue
        return profiles

    @staticmethod
    def _atomic_write(path: Path, stored: StoredNovelProfile) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
        payload = json.dumps(stored.model_dump(mode="json"), ensure_ascii=False, indent=2) + "\n"
        try:
            with temporary.open("w", encoding="utf-8", newline="\n") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, path)
        except Exception:
            temporary.unlink(missing_ok=True)
            raise
