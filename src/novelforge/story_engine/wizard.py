"""新建小说与内容包（主计划 T13）。

- T13a 新建小说向导：创建 NovelProfile（可选题材模板），随后进入同一个 Story Builder。
- T13b 内容包：每本小说一个独立 bundles，包含角色/势力/地点/资源/能力/事件/主线/支线/伏笔/文风，可导出导入。
- T13c 题材案例库：原创案例只作参考，不作为固定剧情模板。
"""

from __future__ import annotations

import json
import os
import uuid
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from pydantic import Field, ValidationError

from novelforge.models import StrictModel

from .entities import Ability, Character, Faction, Location, ResourceDefinition
from .profile import NovelProfile, NovelProfileError, NovelProfileRepository
from .templates import apply_template

DEFAULT_PACKS_PATH = Path("novel/authoring/story_engine/packs")
DEFAULT_CASES_PATH = Path("novel/config/story_engine/cases.json")
ENTRY_STEPS = ("reader_experience", "worldview", "protagonist", "major_events")
CASE_CATEGORIES = ("opening", "turn", "conflict", "escalation", "comeback", "reversal", "climax",
                   "lowpoint", "relationship", "foreshadow", "payoff", "volume_end", "ending")


class NovelPackError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(message)


class NovelContentPack(StrictModel):
    schema_version: int = 1
    novel_id: str = Field(min_length=3, max_length=96)
    characters: dict[str, Character] = Field(default_factory=dict)
    factions: dict[str, Faction] = Field(default_factory=dict)
    locations: dict[str, Location] = Field(default_factory=dict)
    resources: dict[str, ResourceDefinition] = Field(default_factory=dict)
    abilities: dict[str, Ability] = Field(default_factory=dict)
    events: dict[str, dict[str, Any]] = Field(default_factory=dict)
    main_plot: list[str] = Field(default_factory=list)
    side_plots: list[str] = Field(default_factory=list)
    foreshadowing: list[str] = Field(default_factory=list)
    style: dict[str, Any] = Field(default_factory=dict)


class CaseExample(StrictModel):
    id: str = Field(min_length=1, max_length=96)
    category: str = Field(min_length=1, max_length=32)
    title: str = Field(default="", max_length=120)
    structure: str = Field(default="", max_length=300)
    example: str = Field(default="", max_length=500)
    genres: list[str] = Field(default_factory=list)
    authoring_note: str = Field(default="", max_length=300)


class CaseLibrary(StrictModel):
    schema_version: int = 1
    library_id: str = Field(default="cases", max_length=96)
    notice: str = Field(default="案例为原创参考，不作为固定剧情模板。", max_length=300)
    cases: list[CaseExample] = Field(default_factory=list)


def create_novel(repository: NovelProfileRepository, novel_id: str, *, title: str = "",
                 genre: str = "", template_id: str = "", entry_step: str = "reader_experience",
                 **fields: Any) -> tuple[NovelProfile, str]:
    """T13a：创建小说实例并返回建议的起始步骤；不写任何故事事实。"""

    if entry_step not in ENTRY_STEPS:
        raise NovelPackError("ENTRY_STEP_INVALID", "起始步骤不在允许范围内")
    profile = repository.create(novel_id, title=title, genre=genre, **fields)
    if template_id:
        profile = repository.save(apply_template(profile, template_id))
    return profile, entry_step


def pack_from_profile(profile: NovelProfile, *, novel_id: str = "") -> NovelContentPack:
    return NovelContentPack(novel_id=novel_id or profile.novel_id,
                            characters=dict(profile.cast), factions=dict(profile.factions),
                            resources=dict(profile.resource_catalog),
                            abilities=dict(profile.ability_catalog),
                            events=dict(profile.event_catalog),
                            style={"tone": profile.tone, "narrative_style": profile.narrative_style},
                            main_plot=list(profile.story_rules)[:1])


def export_pack(pack: NovelContentPack) -> dict[str, Any]:
    return pack.model_dump(mode="json")


def import_pack(payload: Mapping[str, Any], *, novel_id: str = "") -> NovelContentPack:
    try:
        pack = NovelContentPack.model_validate(dict(payload))
    except ValidationError as exc:
        raise NovelPackError("NOVEL_PACK_INVALID", f"内容包格式不正确：{exc.error_count()} 处问题") from exc
    return pack.model_copy(update={"novel_id": novel_id}) if novel_id else pack


class NovelPackRepository:
    def __init__(self, project_root: Path, packs_path: Path | str = DEFAULT_PACKS_PATH) -> None:
        self.project_root = project_root.resolve()
        relative = Path(packs_path)
        self.packs_dir = (relative.resolve() if relative.is_absolute()
                          else (self.project_root / relative).resolve())
        try:
            self.packs_dir.relative_to(self.project_root)
        except ValueError as exc:
            raise NovelPackError("PACK_PATH_OUTSIDE_PROJECT", "内容包目录超出当前项目范围") from exc

    def path_for(self, novel_id: str) -> Path:
        try:
            NovelProfileRepository(self.project_root).path_for(novel_id)
        except NovelProfileError as exc:
            raise NovelPackError("NOVEL_ID_INVALID", exc.message) from exc
        return self.packs_dir / f"{novel_id}.json"

    def save(self, pack: NovelContentPack) -> NovelContentPack:
        path = self.path_for(pack.novel_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
        payload = json.dumps(pack.model_dump(mode="json"), ensure_ascii=False, indent=2) + "\n"
        try:
            with temporary.open("w", encoding="utf-8", newline="\n") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, path)
        finally:
            temporary.unlink(missing_ok=True)
        return pack

    def load(self, novel_id: str) -> NovelContentPack:
        path = self.path_for(novel_id)
        if not path.is_file():
            raise NovelPackError("PACK_NOT_FOUND", "找不到这本小说的内容包")
        try:
            return import_pack(json.loads(path.read_text(encoding="utf-8-sig")), novel_id=novel_id)
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise NovelPackError("PACK_UNREADABLE", "无法读取内容包") from exc

    def exists(self, novel_id: str) -> bool:
        return self.path_for(novel_id).is_file()


def load_case_library(path: Path | str) -> CaseLibrary:
    target = Path(path)
    if not target.is_file():
        raise NovelPackError("CASES_NOT_FOUND", "找不到案例库文件")
    try:
        library = CaseLibrary.model_validate(json.loads(target.read_text(encoding="utf-8-sig")))
    except (OSError, UnicodeError, json.JSONDecodeError, ValidationError) as exc:
        raise NovelPackError("CASES_UNREADABLE", "无法读取案例库") from exc
    unknown = [item.category for item in library.cases if item.category not in CASE_CATEGORIES]
    if unknown:
        raise NovelPackError("CASES_CATEGORY_INVALID", f"存在未知案例分类：{sorted(set(unknown))}")
    return library
