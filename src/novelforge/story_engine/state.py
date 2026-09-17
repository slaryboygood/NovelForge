"""通用 Story State（主计划 T06b）。

设计目的
--------
把“作者的设计意图”和“故事世界已经发生的事实”分开：

- session / blueprint / outline 保存的是作者选择与计划，属于设计态。
- StoryState 保存的是剧情运行后真实存在的世界、人物、知识、资源、承诺与事件，
  属于事实态。

结构约束
--------
- StoryState 不出现任何一本小说或某个题材的专属字段。
- 所有实体都用稳定 id 引用，题材差异放进 `kind` / `tags` / `data` 扩展袋。
- 未迁移的旧数据原样保留在 `legacy`，不参与规则计算，也不被丢弃。

版本策略
--------
- 当前 `STORY_STATE_SCHEMA_VERSION = 2`。
- 读取时由 `upgrade_story_state_payload` 补齐缺失分节，不要求一次性迁移历史数据。
- 高于当前版本的存档拒绝读取，避免用旧代码解释新格式。

T06b-01 现有存档字段盘点（本轮只读，不修改旧数据）
------------------------------------------------
- StoryBuilderSession：session_id、project_id、status、current_step、completed_steps、
  selections、design_choices、needs_review_steps、selection_version、
  recommendation_version、created_at、updated_at。（设计态）
- StoryBlueprint：blueprint_id、project_id、source_session_id、source_selection_version、
  version、status、premise、sections、unresolved_conflicts、design_choices、
  design_effects、design_summaries。（设计态）
- OutlinePackage：package_id、blueprint_id、blueprint_version、level、version、status、
  route_source、route_history、design_sections、pending_questions、items。（设计态）
- Adventure：blueprint_id、blueprint_version、revision、rules_version、branch_id、
  parent_branch、fork_revision、supplies、ally、clue、trust、debt、facts、
  arc_finished、history。（事实态，当前唯一的状态存档，因此需要兼容读取）
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from pydantic import Field, field_validator, model_validator

from novelforge.models import StrictModel

from .entities import (
    Ability,
    Character,
    EffectRecord,
    EventRecord,
    Faction,
    KnowledgeEntry,
    Location,
    PromiseState,
    RelationshipState,
    ResourceStock,
)

STORY_STATE_SCHEMA_VERSION = 6


class StoryStateError(ValueError):
    """StoryState 读取或升级失败。"""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(message)

    def as_dict(self) -> dict[str, str]:
        return {"code": self.code, "message": self.message}


class TimelineState(StrictModel):
    """题材无关的世界时间：tick 是唯一单调推进单位，markers 记录节点标签。"""

    tick: int = Field(default=0, ge=0)
    current_time: str = Field(default="", max_length=128)
    elapsed: str = Field(default="", max_length=128)
    markers: list[str] = Field(default_factory=list)


class LocationState(StrictModel):
    """当前位置、去过的地方，以及故事世界里已知的地点。"""

    current: str = Field(default="", max_length=128)
    visited: list[str] = Field(default_factory=list)
    known: dict[str, Location] = Field(default_factory=dict)
    data: dict[str, Any] = Field(default_factory=dict)


class WorldState(StrictModel):
    """世界共同约束与术语。规则是事实，不是角色已知信息。"""

    rules: list[str] = Field(default_factory=list)
    terms: dict[str, str] = Field(default_factory=dict)
    data: dict[str, Any] = Field(default_factory=dict)


class StoryState(StrictModel):
    """题材无关的故事事实状态。"""

    schema_version: int = Field(default=STORY_STATE_SCHEMA_VERSION, ge=1)
    novel_id: str = Field(default="", max_length=128)
    world: WorldState = Field(default_factory=WorldState)
    timeline: TimelineState = Field(default_factory=TimelineState)
    location: LocationState = Field(default_factory=LocationState)
    characters: dict[str, Character] = Field(default_factory=dict)
    relationships: list[RelationshipState] = Field(default_factory=list)
    knowledge: list[KnowledgeEntry] = Field(default_factory=list)
    author_knowledge: list[KnowledgeEntry] = Field(default_factory=list)
    resources: dict[str, ResourceStock] = Field(default_factory=dict)
    abilities: dict[str, Ability] = Field(default_factory=dict)
    factions: dict[str, Faction] = Field(default_factory=dict)
    flags: dict[str, Any] = Field(default_factory=dict)
    identities: dict[str, list[str]] = Field(default_factory=dict)
    promises: list[PromiseState] = Field(default_factory=list)
    active_events: list[EventRecord] = Field(default_factory=list)
    resolved_events: list[EventRecord] = Field(default_factory=list)
    effect_log: list[EffectRecord] = Field(default_factory=list)
    delayed_effects: list[dict[str, Any]] = Field(default_factory=list)
    plots: dict[str, dict[str, Any]] = Field(default_factory=dict)
    legacy: dict[str, Any] = Field(default_factory=dict)

    @field_validator("schema_version")
    @classmethod
    def supported_version(cls, value: int) -> int:
        if value < 1 or value > STORY_STATE_SCHEMA_VERSION:
            raise ValueError("unsupported story state schema version")
        return value

    @model_validator(mode="after")
    def valid_structure(self) -> "StoryState":
        if self.schema_version > STORY_STATE_SCHEMA_VERSION:
            raise ValueError("story state schema is newer than this engine supports")
        for name, entries in (("characters", self.characters), ("resources", self.resources),
                              ("abilities", self.abilities), ("factions", self.factions),
                              ("location.known", self.location.known)):
            for key, entry in entries.items():
                if key != entry.id:
                    raise ValueError(f"{name} key must match entry id")
        for name, ids in (("knowledge", [item.id for item in self.knowledge]),
                          ("author_knowledge", [item.id for item in self.author_knowledge]),
                          ("promises", [item.id for item in self.promises])):
            if len(ids) != len(set(ids)):
                raise ValueError(f"{name} ids must be unique")
        pairs = [(item.source_id, item.target_id) for item in self.relationships]
        if len(pairs) != len(set(pairs)):
            raise ValueError("relationship pairs must be unique")
        if any(item.status != "active" for item in self.active_events):
            raise ValueError("active_events may only contain active events")
        if any(item.status != "resolved" for item in self.resolved_events):
            raise ValueError("resolved_events may only contain resolved events")
        event_ids = [item.id for item in self.active_events + self.resolved_events]
        if len(event_ids) != len(set(event_ids)):
            raise ValueError("an event cannot be active and resolved at the same time")
        return self


_SECTIONS = ("world", "timeline", "location", "characters", "relationships",
             "knowledge", "author_knowledge", "resources", "abilities", "factions", "flags", "identities", "promises",
             "active_events", "resolved_events", "effect_log", "delayed_effects", "plots", "legacy")
_TOP_LEVEL_KEYS = _SECTIONS + ("schema_version", "novel_id")


def upgrade_story_state_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
    """把历史/缺字段的 StoryState 载荷补齐到当前版本，未知顶层字段移入 legacy。"""

    if not isinstance(payload, Mapping):
        raise StoryStateError("STORY_STATE_PAYLOAD_INVALID", "故事状态必须是对象")
    upgraded = dict(payload)
    version = upgraded.get("schema_version", 1)
    if isinstance(version, bool) or not isinstance(version, int) or version < 1:
        raise StoryStateError("STORY_STATE_VERSION_INVALID", "故事状态版本号无效")
    if version > STORY_STATE_SCHEMA_VERSION:
        raise StoryStateError("STORY_STATE_VERSION_UNSUPPORTED", "故事状态版本高于当前引擎可读取范围")
    legacy = dict(upgraded.get("legacy") or {})
    for key in list(upgraded):
        if key not in _TOP_LEVEL_KEYS:
            legacy.setdefault(key, upgraded.pop(key))
    upgraded["legacy"] = legacy
    upgraded["schema_version"] = STORY_STATE_SCHEMA_VERSION
    return upgraded


def story_state_from_payload(payload: Mapping[str, Any]) -> StoryState:
    """兼容读取入口：先升级再校验，旧存档不需要一次性重写。"""

    return StoryState.model_validate(upgrade_story_state_payload(payload))


def from_legacy_adventure(adventure: Mapping[str, Any], *, novel_id: str = "") -> StoryState:
    """把旧版 Adventure 存档读成 StoryState。

    只映射语义明确的字段；无法无损映射的（trust / debt / history / 分支信息等）
    连同原始载荷一起保存在 `legacy["adventure"]`，不猜测含义、不伪造事实。
    `facts` 在旧存档里是主角在旅程中已经核实的事实，因此兼容读取时登记为主角持有；
    如果后续旧存档表达了其他持有人，以原始 `legacy` 载荷为准。
    """

    if not isinstance(adventure, Mapping):
        raise StoryStateError("LEGACY_ADVENTURE_INVALID", "旧旅程存档必须是对象")
    resources: dict[str, ResourceStock] = {}
    if "supplies" in adventure:
        amount = adventure.get("supplies", 0)
        if isinstance(amount, bool) or not isinstance(amount, (int, float)) or amount < 0:
            raise StoryStateError("LEGACY_ADVENTURE_INVALID", "旧旅程补给不是有效的非负数量")
        resources["supplies"] = ResourceStock(id="supplies", amount=float(amount), unit="份",
                                              source="legacy_adventure")
    knowledge = [KnowledgeEntry(id=str(item), holders=["protagonist"], source="legacy_adventure",
                                reader_visible=True)
                 for item in adventure.get("facts", []) if isinstance(item, str) and item]
    flags: dict[str, Any] = {}
    for key in ("ally", "clue"):
        if key in adventure:
            flags[f"legacy.{key}"] = bool(adventure[key])
    timeline = TimelineState(markers=[f"legacy_revision:{adventure.get('revision', 0)}"])
    characters: dict[str, Character] = {}
    holders = {holder for item in knowledge for holder in item.holders}
    for holder in sorted(holders):
        characters[holder] = Character(id=holder, kind="player" if holder == "protagonist" else "")
    return StoryState(
        novel_id=novel_id,
        characters=characters,
        resources=resources,
        knowledge=knowledge,
        flags=flags,
        timeline=timeline,
        legacy={"source": "legacy_adventure", "adventure": dict(adventure)},
    )
