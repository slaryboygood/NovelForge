"""Canon Infrastructure V1：稳定身份模型（C01）。

职责边界：

- StoryState 是「已经发生事实」的 runtime truth；
- Canon 是「这个事实是谁、依赖什么、谁知道」的身份与规划层，只做 StoryState → Canon 单向同步；
- Canon 不建立第二套 StoryState 实体，CanonEntity 只是对既有稳定实体身份的引用/索引。
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import Field, field_validator, model_validator

from novelforge.models import StrictModel

from .ids import validate_canon_id, validate_canonical_key

FactStatus = Literal["planned", "happened", "superseded", "invalidated"]
EventStatus = Literal["planned", "occurred", "resolved", "ongoing", "retired"]
NarrativeRole = Literal["canonical", "consequence", "escalation", "reinterpretation",
                        "payoff", "recurrence"]
KnowledgeState = Literal["unknown", "suspected", "known", "confirmed", "false_belief"]
ForeshadowStatus = Literal["planned", "planted", "reinforced", "revealed", "paid_off", "abandoned"]
Provenance = Literal["imported", "inferred", "generated", "confirmed", "story_state", "planner"]
DependencyRelation = Literal["REQUIRES", "CAUSES", "REVEALS", "KNOWS", "AFFECTS", "SUPERSEDES",
                             "PLANTED_BY", "PAID_OFF_BY", "LOCATED_AT", "PARTICIPATES_IN"]
HolderType = Literal["character", "faction", "reader", "public"]


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class CanonSourceRef(StrictModel):
    source_type: str = Field(default="outline", max_length=32)
    source_id: str = Field(default="", max_length=128)
    source_uuid: str = Field(default="", max_length=128)
    chapter_uuid: str = Field(default="", max_length=128)
    claimed_fact_ids: list[str] = Field(default_factory=list)
    temporal_position: int | None = Field(default=None, ge=0)
    provenance: str = Field(default="generated", max_length=32)
    note: str = Field(default="", max_length=200)


class CanonRenderRef(StrictModel):
    """渲染位置：chapter_uuid 稳定，display_number 可随重编号变化。"""

    chapter_uuid: str = Field(min_length=1, max_length=128)
    display_number: int | None = Field(default=None, ge=0)
    field: str = Field(default="", max_length=64)


class CanonDependency(StrictModel):
    from_id: str = Field(min_length=1, max_length=160)
    to_id: str = Field(min_length=1, max_length=160)
    relation: DependencyRelation
    note: str = Field(default="", max_length=200)


class CanonVersion(StrictModel):
    version: int = Field(default=1, ge=1)
    created_at: datetime = Field(default_factory=utc_now)
    note: str = Field(default="", max_length=200)
    digest: str = Field(default="", max_length=128)


class CanonSourceMapping(StrictModel):
    """source → canon identity 的持久映射：重建必须复用，不能重新计算。"""

    novel_id: str = Field(min_length=1, max_length=96)
    source_type: Literal["story_state", "route", "outline", "planner", "imported"]
    source_stable_key: str = Field(min_length=1, max_length=256)
    canon_type: Literal["entity", "fact", "event", "knowledge", "relationship", "foreshadow",
                        "constraint"]
    canon_id: str = Field(min_length=3, max_length=160)
    created_at: datetime = Field(default_factory=utc_now)


class CanonEntity(StrictModel):
    entity_id: str = Field(min_length=3, max_length=160)
    canonical_key: str = Field(min_length=1, max_length=96)
    novel_id: str = Field(min_length=1, max_length=96)
    kind: str = Field(default="character", max_length=32)
    display_name: str = Field(default="", max_length=120)
    aliases: list[str] = Field(default_factory=list)
    source_refs: list[CanonSourceRef] = Field(default_factory=list)
    data: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)

    @field_validator("entity_id")
    @classmethod
    def _id(cls, value: str) -> str:
        return validate_canon_id(value, "entity")

    @field_validator("canonical_key")
    @classmethod
    def _key(cls, value: str) -> str:
        return validate_canonical_key(value)


class CanonFact(StrictModel):
    fact_id: str = Field(min_length=3, max_length=160)
    canonical_key: str = Field(min_length=1, max_length=96)
    novel_id: str = Field(min_length=1, max_length=96)
    category: str = Field(default="event", max_length=32)
    canonical_description: str = Field(default="", max_length=400)
    status: FactStatus = "planned"
    immutable: bool = False
    source_type: Literal["story_state", "route", "planner", "outline", "imported"] = "planner"
    source_refs: list[CanonSourceRef] = Field(default_factory=list)
    subjects: list[str] = Field(default_factory=list)
    objects: list[str] = Field(default_factory=list)
    location_ids: list[str] = Field(default_factory=list)
    prerequisites: list[str] = Field(default_factory=list)
    consequences: list[str] = Field(default_factory=list)
    knowledge_effects: list[str] = Field(default_factory=list)
    first_occurrence_ref: CanonRenderRef | None = None
    current_render_refs: list[CanonRenderRef] = Field(default_factory=list)
    provenance: Provenance = "generated"
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)

    @field_validator("fact_id")
    @classmethod
    def _id(cls, value: str) -> str:
        return validate_canon_id(value, "fact")

    @field_validator("canonical_key")
    @classmethod
    def _key(cls, value: str) -> str:
        return validate_canonical_key(value)

    @model_validator(mode="after")
    def _happened_is_immutable(self) -> "CanonFact":
        if self.status == "happened" and not self.immutable:
            object.__setattr__(self, "immutable", True)
        return self

    def model_copy(self, *, update: dict[str, Any] | None = None,
                   deep: bool = False) -> "CanonFact":
        """model_copy 默认不跑校验；这里强制重新校验，保证 happened 永远 immutable。"""

        payload = self.model_dump()
        payload.update(update or {})
        return type(self).model_validate(payload)


class CanonEvent(StrictModel):
    event_id: str = Field(min_length=3, max_length=160)
    canonical_key: str = Field(min_length=1, max_length=96)
    novel_id: str = Field(min_length=1, max_length=96)
    canonical_name: str = Field(default="", max_length=160)
    semantic_summary: str = Field(default="", max_length=400)
    event_type: str = Field(default="major", max_length=48)
    narrative_role: NarrativeRole = "canonical"
    canonical_event_id: str = Field(default="", max_length=160)
    status: EventStatus = "planned"
    can_repeat: bool = False
    repeat_rule: str = Field(default="", max_length=200)
    subjects: list[str] = Field(default_factory=list)
    objects: list[str] = Field(default_factory=list)
    location: str = Field(default="", max_length=120)
    prerequisites: list[str] = Field(default_factory=list)
    caused_by: list[str] = Field(default_factory=list)
    consequences: list[str] = Field(default_factory=list)
    facts_created: list[str] = Field(default_factory=list)
    facts_changed: list[str] = Field(default_factory=list)
    information_revealed: list[str] = Field(default_factory=list)
    character_effects: list[str] = Field(default_factory=list)
    faction_effects: list[str] = Field(default_factory=list)
    temporal_position: int | None = Field(default=None, ge=0)
    first_occurrence_ref: CanonRenderRef | None = None
    provenance: Provenance = "generated"
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)

    @field_validator("event_id")
    @classmethod
    def _id(cls, value: str) -> str:
        return validate_canon_id(value, "event")

    @field_validator("canonical_key")
    @classmethod
    def _key(cls, value: str) -> str:
        return validate_canonical_key(value)

    @model_validator(mode="after")
    def _role_consistency(self) -> "CanonEvent":
        if self.narrative_role == "canonical":
            if self.canonical_event_id:
                raise ValueError("canonical 事件不能引用其它 canonical_event_id")
        elif not self.canonical_event_id:
            raise ValueError(f"{self.narrative_role} 事件必须指向 canonical_event_id")
        if not self.can_repeat and not self.repeat_rule and self.narrative_role == "recurrence":
            raise ValueError("recurrence 事件必须声明 repeat_rule")
        return self


class CanonKnowledge(StrictModel):
    knowledge_id: str = Field(min_length=3, max_length=160)
    novel_id: str = Field(min_length=1, max_length=96)
    fact_id: str = Field(min_length=3, max_length=160)
    holder_type: HolderType = "character"
    holder_id: str = Field(default="", max_length=128)
    state: KnowledgeState = "known"
    learned_at: int | None = Field(default=None, ge=0)
    learned_from: str = Field(default="", max_length=160)
    source_event_id: str = Field(default="", max_length=160)
    confidence: float = Field(default=1.0, ge=0, le=1)
    public_scope: str = Field(default="", max_length=64)
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)

    @field_validator("knowledge_id")
    @classmethod
    def _id(cls, value: str) -> str:
        return validate_canon_id(value, "knowledge")

    @model_validator(mode="after")
    def _holder_required(self) -> "CanonKnowledge":
        if self.holder_type in ("character", "faction") and not self.holder_id:
            raise ValueError("character / faction 知识的 holder_id 不能为空")
        return self


class CanonRelationship(StrictModel):
    relationship_id: str = Field(min_length=3, max_length=160)
    novel_id: str = Field(min_length=1, max_length=96)
    source_id: str = Field(min_length=1, max_length=128)
    target_id: str = Field(min_length=1, max_length=128)
    kind: str = Field(default="trust", max_length=64)
    state: str = Field(default="", max_length=160)
    since: int | None = Field(default=None, ge=0)
    data: dict[str, Any] = Field(default_factory=dict)

    @field_validator("relationship_id")
    @classmethod
    def _id(cls, value: str) -> str:
        return validate_canon_id(value, "relationship")

    @model_validator(mode="after")
    def _distinct(self) -> "CanonRelationship":
        if self.source_id == self.target_id:
            raise ValueError("关系的两端不能是同一个实体")
        return self


class CanonForeshadow(StrictModel):
    foreshadow_id: str = Field(min_length=3, max_length=160)
    novel_id: str = Field(min_length=1, max_length=96)
    subject: str = Field(default="", max_length=160)
    planted_fact_id: str = Field(default="", max_length=160)
    intended_payoff: str = Field(default="", max_length=300)
    status: ForeshadowStatus = "planned"
    plant_ref: CanonRenderRef | None = None
    reinforce_refs: list[CanonRenderRef] = Field(default_factory=list)
    reveal_ref: CanonRenderRef | None = None
    payoff_ref: CanonRenderRef | None = None
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)

    @field_validator("foreshadow_id")
    @classmethod
    def _id(cls, value: str) -> str:
        return validate_canon_id(value, "foreshadow")

    @model_validator(mode="after")
    def _state_refs(self) -> "CanonForeshadow":
        if self.status in ("reinforced", "revealed", "paid_off") and not self.reinforce_refs:
            object.__setattr__(self, "reinforce_refs", list(self.reinforce_refs))
        if self.status == "paid_off" and self.reveal_ref is None:
            raise ValueError("paid_off 伏笔必须先有 reveal_ref")
        return self


class CanonConstraint(StrictModel):
    constraint_id: str = Field(min_length=3, max_length=160)
    novel_id: str = Field(min_length=1, max_length=96)
    scope: str = Field(default="book", max_length=32)
    description: str = Field(default="", max_length=300)
    severity: Literal["hard", "soft"] = "hard"
    related_ids: list[str] = Field(default_factory=list)

    @field_validator("constraint_id")
    @classmethod
    def _id(cls, value: str) -> str:
        return validate_canon_id(value, "constraint")
