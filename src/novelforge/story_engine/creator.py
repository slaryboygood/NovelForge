"""创作者 UI 运行上下文（V2-I-01）。

把「一本小说当前的事实态」解析成一个稳定的读取入口，供 UI 面板使用：

    novel_id → Novel Profile → 内容包 → 最新已确认蓝图 → StoryState（或只读预览状态）

约束：

- 事实来源仍然是 StoryState；这里不复制状态、不建立第二套存储。
- 只读：解析过程不会写回任何文件；只有用户明确执行合法操作时才会由 Engine 写入。
- 题材无关：内容包按 Novel Profile 的 `content_pack_id` 选择，不做题材判断。
- 没有旅程存档时给出 `preview` 状态：它与引擎首次开始的初始事实完全一致，
  但只用于展示，不落盘，避免“UI 看起来已经发生、StoryState 其实没有”。
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from .content import ContentPack, ContentPackError, load_pack_from_project
from .profile import NovelProfile, NovelProfileRepository
from .state import StoryState
from .storage import StoryStateRepository, StoryStateStorageError

PREVIEW_FLAG = "ui_preview"
DEFAULT_BRANCH = "main"

# 没有确认蓝图的小说（W1 引导流程）也要能进入动态推演：
# 用「小说级运行槽」持久化 StoryState，仍然是一套存储、一套事实。
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


class CreatorContextError(ValueError):
    """创作者上下文解析失败。"""

    def __init__(self, code: str, message: str, *, novel_id: str = "") -> None:
        self.code = code
        self.message = message
        self.novel_id = novel_id
        super().__init__(message)

    def as_dict(self) -> dict[str, str]:
        return {"code": self.code, "message": self.message, "novel_id": self.novel_id}


@dataclass(frozen=True)
class CreatorContext:
    """一本小说的读取上下文：profile + 内容包 + 当前事实（可能是预览）。"""

    novel_id: str
    project_root: Path
    profile: NovelProfile
    pack: ContentPack | None
    state: StoryState
    blueprint_id: str = ""
    blueprint_version: int = 0
    # 事实态真正的存储槽：有确认蓝图时等于蓝图槽，W1 引导流程里等于小说级运行槽。
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
            "content_pack_id": self.pack.pack_id if self.pack is not None else self.profile.content_pack_id,
            "content_pack_title": self.pack.title if self.pack is not None else "",
            "blueprint_id": self.blueprint_id,
            "blueprint_version": self.blueprint_version,
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


def preview_state(profile: NovelProfile, pack: ContentPack | None, *,
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
            working.characters[character_id] = existing.model_copy(update={"kind": existing.kind or "player"})
    for faction_id, entry in profile.factions.items():
        working.factions.setdefault(faction_id, entry.model_copy(deep=True))
    for location_id in profile.world_profile.get("locations", []) if isinstance(
            profile.world_profile.get("locations", []), list) else []:
        if isinstance(location_id, str) and location_id:
            working.location.known.setdefault(location_id, Location(id=location_id, name=location_id))
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


def _blueprint_for_session(project_root: Path, session_ids: list[str]) -> tuple[str, int, str]:
    """最新一个已确认蓝图；没有确认蓝图时退回最新蓝图（未确认只影响展示）。"""

    from novelforge.story_builder.blueprints import StoryBlueprintRepository
    from novelforge.story_builder.blueprints import blueprint_id_for_session

    repository = StoryBlueprintRepository(project_root)
    candidates: list[tuple[int, int, str, int, str]] = []
    for index, session_id in enumerate(session_ids):
        blueprint_id = blueprint_id_for_session(session_id)
        try:
            blueprint = repository.latest(blueprint_id)
        except Exception:  # noqa: BLE001 - 读取失败的蓝图跳过，不影响其他小说
            continue
        if blueprint is None:
            continue
        status = getattr(blueprint.status, "value", blueprint.status)
        confirmed = 1 if status == "CONFIRMED" else 0
        candidates.append((confirmed, index, blueprint.blueprint_id, blueprint.version, status))
    if not candidates:
        return "", 0, ""
    _, _, blueprint_id, version, status = max(
        candidates, key=lambda item: (item[0], item[1], item[2], item[3]))
    return blueprint_id, version, status


def resolve_creator_context(project_root: Path, novel_id: str) -> CreatorContext:
    """解析一本小说的读取上下文；不写任何文件。"""

    profiles = NovelProfileRepository(project_root)
    profile = profiles.ensure(novel_id)
    pack, pack_error = _load_pack(project_root, profile.content_pack_id)

    session_ids: list[str] = []
    blueprint_id, version, blueprint_status = "", 0, ""
    try:
        from novelforge.story_builder.sessions import StorySessionRepository

        session_ids = [item.session_id for item in StorySessionRepository(project_root).list_for_project(novel_id)]
    except Exception:  # noqa: BLE001 - 旧数据读取失败不影响其他小说
        session_ids = []
    try:
        blueprint_id, version, blueprint_status = _blueprint_for_session(project_root, session_ids)
    except Exception:  # noqa: BLE001 - 蓝图目录不可读时退回预览
        blueprint_id, version, blueprint_status = "", 0, ""

    branch_id, blueprint = DEFAULT_BRANCH, None
    if blueprint_id:
        try:
            from novelforge.story_builder.blueprints import StoryBlueprintRepository

            blueprint = StoryBlueprintRepository(project_root).load(blueprint_id, version)
            branch_id = getattr(blueprint, "branch_id", "") or DEFAULT_BRANCH
        except Exception:  # noqa: BLE001
            blueprint = None

    states = StoryStateRepository(project_root)
    runtime_id = runtime_key_for(novel_id)
    if blueprint is not None and blueprint_status == "CONFIRMED" and states.exists(blueprint_id, version, branch_id):
        try:
            return CreatorContext(novel_id=novel_id, project_root=project_root,
                                  profile=profile, pack=pack,
                                  state=states.load(blueprint_id, version, branch_id),
                                  blueprint_id=blueprint_id, blueprint_version=version,
                                  runtime_id=blueprint_id, runtime_version=version,
                                  branch_id=branch_id, persisted=True, pack_error=pack_error)
        except StoryStateStorageError:
            pass
    # W1 引导流程：没有确认蓝图的小说，只要作者已显式开始推演，
    # 就从小说的运行槽读取真实事实（同一套 StoryState 存储，不是第二套状态）。
    if states.exists(runtime_id, RUNTIME_VERSION, branch_id):
        try:
            return CreatorContext(novel_id=novel_id, project_root=project_root,
                                  profile=profile, pack=pack,
                                  state=states.load(runtime_id, RUNTIME_VERSION, branch_id),
                                  blueprint_id=blueprint_id, blueprint_version=version,
                                  runtime_id=runtime_id, runtime_version=RUNTIME_VERSION,
                                  branch_id=branch_id, persisted=True, pack_error=pack_error)
        except StoryStateStorageError:
            pass
    return CreatorContext(novel_id=novel_id, project_root=project_root,
                          profile=profile, pack=pack,
                          state=preview_state(profile, pack),
                          blueprint_id=blueprint_id, blueprint_version=version,
                          runtime_id=blueprint_id or runtime_id,
                          runtime_version=version if blueprint_id else RUNTIME_VERSION,
                          branch_id=branch_id, persisted=False, pack_error=pack_error)
