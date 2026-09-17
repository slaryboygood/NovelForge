"""S01：Chapter Semantic IR 数据模型。

identity 规则：IR 只使用稳定 ID（chapter_uuid / CE_/EF_/ST_/EV_ 前缀），
禁止把 display chapter number（ch142）当 identity。
"""

from __future__ import annotations

import os
import re
from typing import Any, Literal

from pydantic import Field, field_validator

from novelforge.models import StrictModel

SCHEMA_VERSION = 1
LOCAL_ID_PATTERN = re.compile(r"^(?:CE|EF|ST)_[A-Z0-9][A-Z0-9_]{1,40}$")
FORBIDDEN_ID = re.compile(r"^ch\d+$|^chapter[_-]?\d+$", re.I)

Agency = Literal["autonomous", "reactive", "forced", "systemic"]
Polarity = Literal["positive", "negative", "neutral", "mixed"]
TransitionKind = Literal["progression", "regression", "activation", "deactivation",
                         "acquisition", "loss", "resolution", "irreversible"]
EvidenceType = Literal["direct", "derived", "summary"]
Provenance = Literal["imported", "inferred", "confirmed", "generated", "planner"]
DogRole = Literal["involved", "supportive", "independent", "offscreen_effect", "absent"]
AssertionMode = Literal["transition", "observation", "historical_reference", "expectation",
                        "hypothesis", "future_intention"]
Disposition = Literal["READY_TO_COMPILE", "NEEDS_CONTENT_REPAIR", "MIGRATION_AMBIGUOUS",
                      "PRODUCT_RULE_REVIEW"]
CompileStatus = Literal["OK", "NOT_APPLICABLE", "BLOCKED_MISSING_EVIDENCE"]
NarrativeRole = Literal["primary", "secondary", "derived"]
DECISION_ACTIONS: tuple[str, ...] = (
    "choose", "decide", "refuse", "accept", "commit", "defer", "allow", "forbid", "assign",
    "retain", "abandon", "withhold", "prioritize", "trade_off", "sign", "approve", "reject",
    "wait", "withdraw",
)


def _local_id(value: str) -> str:
    if FORBIDDEN_ID.match(value or ""):
        raise ValueError(f"章节号不能作为 IR identity：{value}")
    if not LOCAL_ID_PATTERN.match(value or ""):
        raise ValueError(f"IR local id 形态非法（应为 CE_/EF_/ST_）：{value}")
    return value


class IRFlags(StrictModel):
    """默认全部关闭：legacy outline 行为不变。"""

    chapter_semantic_ir_v1: bool = False
    chapter_semantic_ir_shadow: bool = False

    @classmethod
    def from_env(cls) -> "IRFlags":
        def flag(name: str) -> bool:
            return str(os.environ.get(name, "")).strip().lower() in ("1", "true", "yes")
        return cls(chapter_semantic_ir_v1=flag("CHAPTER_SEMANTIC_IR_V1"),
                   chapter_semantic_ir_shadow=flag("CHAPTER_SEMANTIC_IR_SHADOW"))


class ChapterEventFrame(StrictModel):
    """章节内一个事件的结构化事实（actor / action / effect）。"""

    event_id: str = Field(min_length=3, max_length=48)
    actor_ids: list[str] = Field(default_factory=list)
    mentioned_entity_ids: list[str] = Field(default_factory=list)
    action_type: str = Field(default="action", max_length=48)
    decision_action: str = Field(default="", max_length=32)
    changes_followup_path: bool = False
    has_alternative: bool = False
    action_text: str = Field(default="", max_length=300)
    object_ids: list[str] = Field(default_factory=list)
    target_ids: list[str] = Field(default_factory=list)
    location_ids: list[str] = Field(default_factory=list)
    temporal_order: int = Field(default=0, ge=0)
    agency: Agency = "reactive"
    intent: str = Field(default="", max_length=160)
    prerequisite_fact_ids: list[str] = Field(default_factory=list)
    fact_refs: list[str] = Field(default_factory=list)
    canon_event_refs: list[str] = Field(default_factory=list)
    produced_effect_ids: list[str] = Field(default_factory=list)
    physical_presence: bool = True
    confidence: float = Field(default=0.6, ge=0, le=1)
    provenance: Provenance = "inferred"

    @field_validator("event_id")
    @classmethod
    def _id(cls, value: str) -> str:
        return _local_id(value)


class ChapterEffect(StrictModel):
    """本章发生之后“什么变了”。"""

    effect_id: str = Field(min_length=3, max_length=48)
    effect_type: str = Field(default="state_change", max_length=48)
    target_type: str = Field(default="situation", max_length=32)
    target_id: str = Field(default="", max_length=120)
    before_state: str = Field(default="", max_length=120)
    after_state: str = Field(default="", max_length=120)
    polarity: Polarity = "neutral"
    caused_by_event_ids: list[str] = Field(default_factory=list)
    fact_ids_created: list[str] = Field(default_factory=list)
    fact_ids_updated: list[str] = Field(default_factory=list)
    resource_delta: dict[str, float] = Field(default_factory=dict)
    relationship_delta: dict[str, float] = Field(default_factory=dict)
    knowledge_delta: list[str] = Field(default_factory=list)
    ability_delta: list[str] = Field(default_factory=list)
    identity_delta: list[str] = Field(default_factory=list)
    injury_delta: list[str] = Field(default_factory=list)
    reversible: bool = True
    is_narrative_pivot: bool = False
    confidence: float = Field(default=0.6, ge=0, le=1)

    @field_validator("effect_id")
    @classmethod
    def _id(cls, value: str) -> str:
        return _local_id(value)


class ChapterStateTransition(StrictModel):
    """typed state 的有向迁移；world_state_change 只能引用它。"""

    transition_id: str = Field(min_length=3, max_length=48)
    state_key: str = Field(min_length=3, max_length=64)
    subject_id: str = Field(default="", max_length=120)
    from_state: str = Field(default="", max_length=64)
    to_state: str = Field(default="", max_length=64)
    caused_by_event_ids: list[str] = Field(default_factory=list)
    prerequisite_state: str = Field(default="", max_length=64)
    prerequisite_fact_ids: list[str] = Field(default_factory=list)
    transition_kind: TransitionKind = "progression"
    effective_at: int | None = Field(default=None, ge=0)
    canonical_event_id: str = Field(default="", max_length=160)
    assertion_mode: AssertionMode = "transition"
    narrative_role: NarrativeRole = "derived"

    @field_validator("transition_id")
    @classmethod
    def _id(cls, value: str) -> str:
        return _local_id(value)


class FieldEvidence(StrictModel):
    """Writer-visible 字段与 IR 事实的绑定；没有 evidence 的字段不能进 WriterPackage。"""

    field_name: str = Field(min_length=2, max_length=64)
    event_ids: list[str] = Field(default_factory=list)
    effect_ids: list[str] = Field(default_factory=list)
    transition_ids: list[str] = Field(default_factory=list)
    evidence_type: EvidenceType = "direct"
    confidence: float = Field(default=0.6, ge=0, le=1)


class DogRoleBinding(StrictModel):
    role: DogRole = "absent"
    evidence_event_ids: list[str] = Field(default_factory=list)
    effect_ids: list[str] = Field(default_factory=list)
    physical_presence: bool = False
    autonomous: bool = False
    affects_decision_or_state: bool = False


class CompiledField(StrictModel):
    field_name: str = Field(min_length=2, max_length=64)
    text: str = Field(default="", max_length=400)
    compiled_from_event_ids: list[str] = Field(default_factory=list)
    compiled_from_effect_ids: list[str] = Field(default_factory=list)
    compiled_from_transition_ids: list[str] = Field(default_factory=list)
    render_mode: str = Field(default="deterministic", max_length=32)
    status: CompileStatus = "OK"
    human_label: str = Field(default="", max_length=64)
    writer_text: str = Field(default="", max_length=400)


class CompiledChapter(StrictModel):
    chapter_uuid: str = Field(min_length=3, max_length=128)
    semantic_ir_ref: str = Field(default="", max_length=160)
    semantic_ir_version: int = SCHEMA_VERSION
    fields: list[CompiledField] = Field(default_factory=list)
    dog_role: DogRoleBinding = Field(default_factory=DogRoleBinding)
    dog_payload: CompiledField | None = None
    shadow: bool = True

    def field(self, name: str) -> str:
        for item in self.fields:
            if item.field_name == name:
                return item.text
        return ""

    def writer_preview(self) -> dict[str, str]:
        """Writer-visible preview：只含自然短句（无 debug 模板 / machine token）。"""

        return {item.field_name: item.writer_text for item in self.fields
                if item.status == "OK" and item.writer_text}

    def debug_fields(self) -> dict[str, str]:
        return {item.field_name: item.text for item in self.fields if item.text}

    def provenance(self, name: str) -> CompiledField | None:
        for item in self.fields:
            if item.field_name == name:
                return item
        return None


class ChapterSemanticIR(StrictModel):
    chapter_uuid: str = Field(min_length=3, max_length=128)
    novel_id: str = Field(min_length=1, max_length=96)
    volume_id: str = Field(default="", max_length=64)
    arc_id: str = Field(default="", max_length=64)
    temporal_position: int | None = Field(default=None, ge=0)
    location_ids: list[str] = Field(default_factory=list)
    participant_ids: list[str] = Field(default_factory=list)
    event_frames: list[ChapterEventFrame] = Field(default_factory=list)
    effects: list[ChapterEffect] = Field(default_factory=list)
    state_transitions: list[ChapterStateTransition] = Field(default_factory=list)
    field_evidence: list[FieldEvidence] = Field(default_factory=list)
    dog: DogRoleBinding = Field(default_factory=DogRoleBinding)
    canon_fact_ids: list[str] = Field(default_factory=list)
    canon_event_ids: list[str] = Field(default_factory=list)
    context_manifest_id: str = Field(default="", max_length=80)
    source_refs: list[str] = Field(default_factory=list)
    schema_version: int = SCHEMA_VERSION
    provenance: Provenance = "inferred"
    migration_disposition: Disposition | None = None
    legacy_field_copy_removed: int = 0
    ambiguous_entity_ids: list[str] = Field(default_factory=list)
    not_applicable_fields: list[str] = Field(default_factory=list)
    focal_decision_owner_id: str = Field(default="", max_length=128)
    legacy_chapter_label: str = Field(default="", max_length=32)
    goal: str = Field(default="", max_length=300)

    def event(self, event_id: str) -> ChapterEventFrame | None:
        return next((item for item in self.event_frames if item.event_id == event_id), None)

    def effect(self, effect_id: str) -> ChapterEffect | None:
        return next((item for item in self.effects if item.effect_id == effect_id), None)

    def evidence_for(self, field_name: str) -> FieldEvidence | None:
        return next((item for item in self.field_evidence if item.field_name == field_name), None)


def compile_ir_ref(chapter_uuid: str) -> str:
    """IR 引用（machine-only）：chapter_uuid + schema 版本的稳定引用。"""

    return f"ir://{chapter_uuid}/v{SCHEMA_VERSION}"
