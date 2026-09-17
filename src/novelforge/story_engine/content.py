"""内容包加载（主计划 T08d-01）。

把原先写死在 `story_builder/adventures.py` 的地点名、choice_id 文案与数值表
迁移为内容包数据：

- `actions`：通用 Action（成本、效果、可见性），引擎不认识“先帮同行者”这类具体行为。
- `events`：EventCard（触发条件、场景目标、冲突、可用行动、后续事件）。
- `text`：场景文本片段（标题模板、开场档案、追加句），属于内容而不是引擎逻辑。

引擎只按通用结构消费这些数据；新增题材或新旅程只需要新增内容包。
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from pydantic import Field, ValidationError, model_validator

from novelforge.models import StrictModel

from .actions import Action
from .events import EventCard
from .foreshadow import Foreshadow
from .progression import ProgressionTree

DEFAULT_CONTENT_DIR = Path("novel/config/story_engine")


class ContentPackError(ValueError):
    def __init__(self, code: str, message: str, *, pack_id: str = "") -> None:
        self.code = code
        self.message = message
        self.pack_id = pack_id
        super().__init__(message)

    def as_dict(self) -> dict[str, str]:
        return {"code": self.code, "message": self.message, "pack_id": self.pack_id}


class PlaceFallback(StrictModel):
    when_option: str = Field(default="", max_length=95)
    place: str = Field(default="", max_length=80)


class OpeningProfile(StrictModel):
    title: str = Field(default="", max_length=120)
    incident: str = Field(default="", max_length=300)
    success: str = Field(default="", max_length=200)
    question: str = Field(default="", max_length=200)


class JourneyText(StrictModel):
    place_fallbacks: list[PlaceFallback] = Field(default_factory=list)
    crisis_default_opening: dict[str, str] = Field(default_factory=dict)
    crisis_success: dict[str, str] = Field(default_factory=dict)
    opening_profiles: dict[str, OpeningProfile] = Field(default_factory=dict)
    hero_memories: dict[str, str] = Field(default_factory=dict)
    companion_lines: dict[str, str] = Field(default_factory=dict)
    opponent_pressure: dict[str, str] = Field(default_factory=dict)
    scene_titles: dict[str, str] = Field(default_factory=dict)
    scene_texts: dict[str, str] = Field(default_factory=dict)
    followup_titles: dict[str, str] = Field(default_factory=dict)
    followup_texts: dict[str, str] = Field(default_factory=dict)

    def place_for(self, selected_option_ids: list[str]) -> str:
        for item in self.place_fallbacks:
            if item.when_option and item.when_option in selected_option_ids:
                return item.place
        for item in self.place_fallbacks:
            if not item.when_option:
                return item.place
        return ""


class CounterRule(StrictModel):
    """从选择历史重新计算计数器（trust / debt 等），而不是简单累加。"""

    counter: str = Field(min_length=1, max_length=64)
    delta: float = 0
    when_choice: list[str] = Field(default_factory=list)


class RecomputeRules(StrictModel):
    counters: list[CounterRule] = Field(default_factory=list)
    floors: dict[str, float] = Field(default_factory=dict)
    arc_finished_choices: list[str] = Field(default_factory=list)
    knowledge_choices: dict[str, str] = Field(default_factory=dict)


class ChoiceRule(StrictModel):
    """场景可选行动规则：由内容包声明顺序与适用条件，引擎不认识具体行动。"""

    action_id: str = Field(min_length=1, max_length=128)
    order: int = Field(default=0, ge=0, le=999)
    when_patterns: list[str] = Field(default_factory=list)
    unless_patterns: list[str] = Field(default_factory=list)


class ContentPack(StrictModel):
    schema_version: int = 1
    pack_id: str = Field(default="pack", max_length=96)
    title: str = Field(default="", max_length=120)
    genre: str = Field(default="", max_length=64)
    # 旅程初始状态：内容包声明起点，引擎不写死任何题材默认值。
    initial_flags: dict[str, Any] = Field(default_factory=dict)
    initial_resources: dict[str, float] = Field(default_factory=dict)
    text: JourneyText = Field(default_factory=JourneyText)
    recompute: RecomputeRules = Field(default_factory=RecomputeRules)
    actions: list[Action] = Field(default_factory=list)
    events: list[EventCard] = Field(default_factory=list)
    # 通用成长树：七类成长（progression / ability / identity / relationship / faction /
    # information / equipment / skill）由内容包声明，引擎不写死任何题材节点。
    progressions: list[ProgressionTree] = Field(default_factory=list)
    # 作者安排的伏笔：只描述回收条件与位置，不代表已经发生，也不自动下放给角色。
    foreshadows: list[Foreshadow] = Field(default_factory=list)
    # 起点世界事实：地点 / 势力 / 角色 / 支线 / NPC 自主规则。全部是数据，
    # 引擎只按“声明 → 初始 StoryState”装载，不做任何题材判断。
    initial_locations: dict[str, dict[str, Any]] = Field(default_factory=dict)
    initial_current_location: str = Field(default="", max_length=128)
    initial_factions: dict[str, dict[str, Any]] = Field(default_factory=dict)
    initial_characters: dict[str, dict[str, Any]] = Field(default_factory=dict)
    # 起点关系网：声明 source → target 的多维初始关系；与其它 initial_* 一样是数据，不是计算结果。
    initial_relationships: list[dict[str, Any]] = Field(default_factory=list)
    initial_plots: list[dict[str, Any]] = Field(default_factory=list)
    autonomous_rules: list[dict[str, Any]] = Field(default_factory=list)
    # 世界事件密度：两次世界事件之间至少间隔多少个 tick（0 = 不限制，只看事件自身冷却）。
    world_event_gap: int = Field(default=0, ge=0, le=100)
    # 对外编号：内容包声明 action id → 客户端可见的 choice id（兼容既有存档与前端）。
    choice_aliases: dict[str, str] = Field(default_factory=dict)
    choice_sets: dict[str, list[ChoiceRule]] = Field(default_factory=dict)

    @model_validator(mode="after")
    def unique_ids(self) -> "ContentPack":
        action_ids = [item.id for item in self.actions]
        event_ids = [item.event_id for item in self.events]
        tree_ids = [item.tree_id for item in self.progressions]
        foreshadow_ids = [item.id for item in self.foreshadows]
        if len(action_ids) != len(set(action_ids)):
            raise ValueError("content pack action ids must be unique")
        if len(event_ids) != len(set(event_ids)):
            raise ValueError("content pack event ids must be unique")
        if len(tree_ids) != len(set(tree_ids)):
            raise ValueError("content pack progression tree ids must be unique")
        if len(foreshadow_ids) != len(set(foreshadow_ids)):
            raise ValueError("content pack foreshadow ids must be unique")
        known = set(action_ids)
        for event in self.events:
            missing = [item for item in event.available_actions if item not in known]
            if missing:
                raise ValueError(f"event {event.event_id} references unknown actions: {missing}")
        return self

    def action(self, action_id: str) -> Action:
        for item in self.actions:
            if item.id == action_id:
                return item
        raise ContentPackError("ACTION_NOT_FOUND", "内容包里没有这个行动", pack_id=self.pack_id)

    def public_choice_id(self, action_id: str) -> str:
        return self.choice_aliases.get(action_id, action_id)

    def action_id_for_choice(self, choice_id: str) -> str:
        if any(item.id == choice_id for item in self.actions):
            return choice_id
        for action_id, public_id in self.choice_aliases.items():
            if public_id == choice_id:
                return action_id
        raise ContentPackError("ACTION_NOT_FOUND", "内容包里没有这个行动", pack_id=self.pack_id)


def content_pack_from_payload(payload: Mapping[str, Any]) -> ContentPack:
    try:
        return ContentPack.model_validate(dict(payload))
    except ValidationError as exc:
        raise ContentPackError("CONTENT_PACK_INVALID", f"内容包格式不正确：{exc.error_count()} 处问题") from exc


def load_content_pack(path: Path | str) -> ContentPack:
    target = Path(path)
    if not target.is_file():
        raise ContentPackError("CONTENT_PACK_NOT_FOUND", "找不到内容包文件")
    try:
        payload = json.loads(target.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ContentPackError("CONTENT_PACK_UNREADABLE", "无法读取内容包") from exc
    return content_pack_from_payload(payload)


def load_pack_from_project(project_root: Path, pack_name: str) -> ContentPack:
    direct = project_root / DEFAULT_CONTENT_DIR / f"{pack_name}.json"
    if direct.is_file():
        return load_content_pack(direct)
    for pack in list_packs_from_project(project_root):
        if pack.pack_id == pack_name:
            return pack
    raise ContentPackError("CONTENT_PACK_NOT_FOUND", f"找不到内容包：{pack_name}")


def list_packs_from_project(project_root: Path) -> list[ContentPack]:
    """列出项目内的内容包：单包文件 + 合集文件；顺序稳定，供 UI 或 API 选择。"""

    directory = project_root / DEFAULT_CONTENT_DIR
    packs: list[ContentPack] = []
    if not directory.is_dir():
        return packs
    for path in sorted(directory.glob("*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8-sig"))
        except (OSError, UnicodeError, json.JSONDecodeError):
            continue
        if isinstance(payload, Mapping) and isinstance(payload.get("packs"), list):
            for item in payload["packs"]:
                try:
                    packs.append(content_pack_from_payload(item))
                except ContentPackError:
                    continue
        elif isinstance(payload, Mapping) and payload.get("pack_id"):
            try:
                packs.append(content_pack_from_payload(payload))
            except ContentPackError:
                continue
    return packs
