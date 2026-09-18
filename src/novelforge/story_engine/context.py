"""Novel 运行时读取上下文（current domain owner，取代 V2 `story_engine.creator`）。

把「一本小说当前的事实态」解析成一个稳定的读取入口：

```text
novel_id → Novel Profile → 内容包 → StoryState（或只读预览状态）
```

与 V2 creator 的差别（post-release cleanup）：

```text
· 不再读取 V2 引导流 session / story_builder.blueprints（那两套存储已退休）；
  「蓝图槽」概念随之消失，StoryState 只按本作品的运行槽读取；
· 不再隐式创建 profile —— profile 必须已经存在，否则报 PROFILE_NOT_FOUND
  （读操作不得写文件）；
· 只读：解析过程不写回任何文件；写路径属于各自的 canonical store。
```

边界：本模块属于 domain（story_engine），只依赖同层模块；memory 等上层消费者
可以安全地依赖它（依赖方向 memory → domain）。
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from .content import ContentPack, ContentPackError, load_pack_from_project
from .profile import NovelProfile, NovelProfileError, NovelProfileRepository
from .state import StoryState
from .storage import StoryStateRepository, StoryStateStorageError

PREVIEW_FLAG = "ui_preview"
DEFAULT_BRANCH = "main"

#: 小说级运行槽 id 前缀（StoryState 的存储槽，不引入第二套状态）
RUNTIME_KEY_PREFIX = "runtime_"
RUNTIME_VERSION = 1


def runtime_key_for(novel_id: str) -> str:
    """小说级运行槽 id：由 novel_id 规范化而来，满足 StoryState 存储的 id 规则。"""

    slug = re.sub(r"[^A-Za-z0-9_-]+", "_", novel_id or "").strip("_")
    key = f"{RUNTIME_KEY_PREFIX}{slug}" if slug else f"{RUNTIME_KEY_PREFIX}novel"
    if len(key) < 3:
        key = f"{key}_novel"
    return key[:96]


def without_preview_flag(state: StoryState) -> StoryState:
    """去掉只读预览标记：落盘的运行态不得带 `ui_preview`。"""

    if PREVIEW_FLAG not in state.flags:
        return state
    flags = {key: value for key, value in state.flags.items() if key != PREVIEW_FLAG}
    return state.model_copy(update={"flags": flags})


class NovelContextError(ValueError):
    """作品读取上下文解析失败（稳定错误码）。"""

    def __init__(self, code: str, message: str, *, novel_id: str = "") -> None:
        self.code = code
        self.message = message
        self.novel_id = novel_id
        super().__init__(message)

    def as_dict(self) -> dict[str, str]:
        return {"code": self.code, "message": self.message, "novel_id": self.novel_id}


@dataclass(frozen=True)
class NovelContext:
    """一本小说的读取上下文：profile + 内容包 + 当前事实（可能是只读预览）。"""

    novel_id: str
    project_root: Path
    profile: NovelProfile
    pack: ContentPack | None
    state: StoryState
    #: 事实态真正的存储槽（小说级运行槽）
    runtime_id: str = ""
    runtime_version: int = RUNTIME_VERSION
    branch_id: str = DEFAULT_BRANCH
    persisted: bool = False
    pack_error: str = ""

    @property
    def preview(self) -> bool:
        return not self.persisted

    @property
    def title(self) -> str:
        return self.profile.title or self.novel_id

    def meta(self) -> dict[str, object]:
        return {
            "novel_id": self.novel_id,
            "title": self.title,
            "content_pack_id": (self.pack.pack_id if self.pack is not None
                                else self.profile.content_pack_id),
            "content_pack_title": self.pack.title if self.pack is not None else "",
            "branch_id": self.branch_id,
            "persisted": self.persisted,
            "preview": self.preview,
            "pack_error": self.pack_error,
        }


def _load_pack(project_root: Path, pack_id: str) -> tuple[ContentPack | None, str]:
    if not pack_id:
        return None, ""
    try:
        return load_pack_from_project(project_root, pack_id), ""
    except ContentPackError as exc:
        return None, exc.message


def story_state_preview(profile: NovelProfile, pack: ContentPack | None, *,
                        actor: str = "protagonist") -> StoryState:
    """只读预览状态：与引擎首次开始的初始事实同源，但不落盘。"""

    from .entities import Character, Faction, Location
    from .journey import initial_journey_state

    base = (initial_journey_state(pack, novel_id=profile.novel_id, actor=actor)
            if pack is not None else StoryState(novel_id=profile.novel_id))
    working = base.model_copy(deep=True)
    for character_id, entry in profile.cast.items():
        working.characters.setdefault(character_id, entry.model_copy(deep=True))
        if character_id == actor:
            existing = working.characters[character_id]
            working.characters[character_id] = existing.model_copy(
                update={"kind": existing.kind or "player"})
    for faction_id, entry in profile.factions.items():
        working.factions.setdefault(faction_id, entry.model_copy(deep=True))
    locations = profile.world_profile.get("locations", [])
    for location_id in locations if isinstance(locations, list) else []:
        if isinstance(location_id, str) and location_id:
            working.location.known.setdefault(
                location_id, Location(id=location_id, name=location_id))
    for ability_id, entry in profile.ability_catalog.items():
        working.abilities.setdefault(ability_id, entry.model_copy(deep=True))
    if pack is not None:
        for location_id, payload in pack.initial_locations.items():
            working.location.known.setdefault(location_id, Location.model_validate(
                {"id": location_id, **payload}))
        if pack.initial_current_location:
            working.location.current = pack.initial_current_location
        for faction_id, payload in pack.initial_factions.items():
            working.factions.setdefault(faction_id, Faction.model_validate(
                {"id": faction_id, **payload}))
        for character_id, payload in pack.initial_characters.items():
            working.characters.setdefault(character_id, Character.model_validate(
                {"id": character_id, **payload}))
        for track in pack.initial_plots:
            payload = dict(track)
            plot_id = str(payload.pop("id", "")) or str(payload.pop("plot_id", ""))
            if plot_id:
                working.plots.setdefault(plot_id, {"id": plot_id, **payload})
    working.flags[PREVIEW_FLAG] = True
    return working


def resolve_novel_context(project_root: Path | str, novel_id: str) -> NovelContext:
    """解析一本小说的读取上下文（只读；profile 缺失即报 PROFILE_NOT_FOUND）。"""

    root = Path(project_root)
    profiles = NovelProfileRepository(root)
    try:
        profile = profiles.load(novel_id)
    except NovelProfileError as exc:
        raise NovelContextError(exc.code, exc.message, novel_id=novel_id) from exc
    pack, pack_error = _load_pack(root, profile.content_pack_id)

    states = StoryStateRepository(root)
    runtime_id = runtime_key_for(profile.novel_id)
    if states.exists(runtime_id, RUNTIME_VERSION, DEFAULT_BRANCH):
        try:
            return NovelContext(
                novel_id=profile.novel_id, project_root=root, profile=profile,
                pack=pack, state=states.load(runtime_id, RUNTIME_VERSION,
                                             DEFAULT_BRANCH),
                runtime_id=runtime_id, runtime_version=RUNTIME_VERSION,
                branch_id=DEFAULT_BRANCH, persisted=True, pack_error=pack_error)
        except StoryStateStorageError:
            pass
    return NovelContext(novel_id=profile.novel_id, project_root=root, profile=profile,
                        pack=pack, state=story_state_preview(profile, pack),
                        runtime_id=runtime_id, runtime_version=RUNTIME_VERSION,
                        branch_id=DEFAULT_BRANCH, persisted=False,
                        pack_error=pack_error)


__all__ = [
    "DEFAULT_BRANCH", "NovelContext", "NovelContextError", "PREVIEW_FLAG",
    "RUNTIME_KEY_PREFIX", "RUNTIME_VERSION", "resolve_novel_context",
    "runtime_key_for", "story_state_preview", "without_preview_flag",
]
