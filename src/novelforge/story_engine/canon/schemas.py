"""Planner / LLM 输出 schema（C01 结构 + C03 语义安全校验共用）。

结构正确由 Pydantic 负责；事实正确交给 Canon Validator；时序/因果交给 Graph；
重复候选交给 SemanticIndex —— 不在这里做巨型校验。
"""

from __future__ import annotations

import re
from typing import Annotated, Any, Literal

from pydantic import Field, Strict, field_validator, model_validator

from novelforge.models import StrictModel

from .models import CanonDependency, CanonSourceRef, NarrativeRole

DogRole = Literal["involved", "supportive", "independent", "offscreen_effect", "absent"]


def _unique_events(values: list[str]) -> list[str]:
    cleaned: list[str] = []
    for raw in values:
        text = str(raw).strip()
        if len(text) <= 1:
            raise ValueError(f"具体事件不能是单字或空串：{raw!r}")
        if len(text) <= 4:
            raise ValueError(f"具体事件过短，疑似字段碎片：{raw!r}")
        if text in cleaned:
            raise ValueError(f"同章事件不得完全重复：{text!r}")
        cleaned.append(text)
    return cleaned


class CanonProposal(StrictModel):
    fact_id: str = Field(default="", max_length=160)
    canonical_key: str = Field(default="", max_length=96)
    category: str = Field(default="event", max_length=32)
    canonical_description: str = Field(default="", max_length=400)
    status: Literal["planned", "happened", "superseded", "invalidated"] = "planned"
    source_refs: list[CanonSourceRef] = Field(default_factory=list)
    subjects: list[str] = Field(default_factory=list)
    objects: list[str] = Field(default_factory=list)
    location_ids: list[str] = Field(default_factory=list)
    prerequisites: list[str] = Field(default_factory=list)
    consequences: list[str] = Field(default_factory=list)
    data: dict[str, Any] = Field(default_factory=dict)


class KnowledgeProposal(StrictModel):
    knowledge_id: str = Field(default="", max_length=160)
    fact_id: str = Field(min_length=3, max_length=160)
    holder_type: Literal["character", "faction", "reader", "public"] = "character"
    holder_id: str = Field(default="", max_length=128)
    state: Literal["unknown", "suspected", "known", "confirmed", "false_belief"] = "known"
    learned_at: int | None = Field(default=None, ge=0)
    learned_from: str = Field(default="", max_length=160)
    source_event_id: str = Field(default="", max_length=160)


class EventProposal(StrictModel):
    event_id: str = Field(default="", max_length=160)
    canonical_key: str = Field(default="", max_length=96)
    canonical_name: str = Field(default="", max_length=160)
    semantic_summary: str = Field(default="", max_length=400)
    event_type: str = Field(default="major", max_length=48)
    narrative_role: NarrativeRole = "canonical"
    canonical_event_id: str = Field(default="", max_length=160)
    status: Literal["planned", "occurred", "resolved", "ongoing", "retired"] = "planned"
    can_repeat: bool = False
    repeat_rule: str = Field(default="", max_length=200)
    subjects: list[str] = Field(default_factory=list)
    objects: list[str] = Field(default_factory=list)
    location: str = Field(default="", max_length=120)
    facts_created: list[str] = Field(default_factory=list)
    information_revealed: list[str] = Field(default_factory=list)


class NarrativeBeat(StrictModel):
    beat_id: str = Field(min_length=3, max_length=160)
    goal: str = Field(min_length=1, max_length=300)
    event_ids: list[str] = Field(default_factory=list)
    fact_ids: list[str] = Field(default_factory=list)
    participant_ids: list[str] = Field(default_factory=list)
    location_ids: list[str] = Field(default_factory=list)
    knowledge_changes: list[str] = Field(default_factory=list)
    relationship_changes: list[str] = Field(default_factory=list)
    resource_changes: dict[str, float] = Field(default_factory=dict)
    foreshadow_actions: list[str] = Field(default_factory=list)
    semantic_summary: str = Field(default="", max_length=300)


class SceneGroup(StrictModel):
    scene_id: str = Field(min_length=3, max_length=160)
    location_id: str = Field(default="", max_length=128)
    participant_ids: list[str] = Field(default_factory=list)
    beat_ids: list[str] = Field(default_factory=list)
    summary: str = Field(default="", max_length=300)


class ChapterPlan(StrictModel):
    """LLM 章纲输出。`concrete_events` 必须是 list[str]，且 ≥3 条互不相同的完整事件。"""

    chapter_uuid: str = Field(min_length=3, max_length=128)
    display_number: int | None = Field(default=None, ge=0)
    title: str = Field(default="", max_length=160)
    volume_ref: str = Field(default="", max_length=64)
    arc_ref: str = Field(default="", max_length=64)
    estimated_words: int = Field(default=3000, ge=300, le=20000)
    timeline_position: int | None = Field(default=None, ge=0)
    temporal_position: int | None = Field(default=None, ge=0)
    location: str = Field(default="", max_length=120)
    goal: str = Field(default="", max_length=300)
    start_state: str = Field(default="", max_length=400)
    concrete_events: Annotated[list[str], Strict()]
    trigger: str = Field(default="", max_length=300)
    protagonist_action: str = Field(default="", max_length=300)
    opposition: str = Field(default="", max_length=300)
    escalation: str = Field(default="", max_length=300)
    decision: str | None = Field(default=None, max_length=300)
    decision_result: str | None = Field(default=None, max_length=300)
    turn: str = Field(default="", max_length=300)
    payoff: str = Field(default="", max_length=300)
    cost: str = Field(default="", max_length=300)
    loss: str = Field(default="", max_length=300)
    dog_role: DogRole = "absent"
    dog_action: str | None = Field(default=None, max_length=300)
    npc_autonomous_action: str = Field(default="", max_length=300)
    world_state_change: str = Field(default="", max_length=300)
    information_release: str = Field(default="", max_length=300)
    foreshadow_action: str = Field(default="", max_length=200)
    end_state: str = Field(default="", max_length=400)
    hook: str = Field(default="", max_length=300)
    next_chapter_causality: str = Field(default="", max_length=300)
    source_refs: list[str] = Field(default_factory=list)
    canon_source_refs: list[CanonSourceRef] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)
    # Canon-aware path 的 graph metadata（默认存在；canon path 要求调用方显式提供 key）
    participants: list[str] = Field(default_factory=list)
    locations: list[str] = Field(default_factory=list)
    prerequisites: list[str] = Field(default_factory=list)
    requires_abilities: list[str] = Field(default_factory=list)
    grants_abilities: list[str] = Field(default_factory=list)
    requires_identities: list[str] = Field(default_factory=list)
    grants_identities: list[str] = Field(default_factory=list)
    character_state_effects: list[str] = Field(default_factory=list)
    knowledge_changes: list[str] = Field(default_factory=list)
    relationship_changes: list[str] = Field(default_factory=list)
    resource_changes: dict[str, float] = Field(default_factory=dict)
    ability_changes: list[str] = Field(default_factory=list)
    identity_changes: list[str] = Field(default_factory=list)
    foreshadow_actions: list[str] = Field(default_factory=list)
    context_manifest_id: str = Field(default="", max_length=80)
    canon_fact_ids: list[str] = Field(default_factory=list)
    canon_event_ids: list[str] = Field(default_factory=list)

    @field_validator("concrete_events", mode="before")
    @classmethod
    def _reject_string(cls, value: Any) -> Any:
        if isinstance(value, str):
            raise ValueError("concrete_events 必须是 list[str]，收到 str（禁止逐字符展开）")
        return value

    @field_validator("concrete_events")
    @classmethod
    def _semantic_events(cls, value: list[str]) -> list[str]:
        cleaned = _unique_events(value)
        if len(cleaned) < 3:
            raise ValueError("每章至少需要 3 条互不相同的具体事件")
        return cleaned

    @model_validator(mode="after")
    def _dog_role_alignment(self) -> "ChapterPlan":
        if self.dog_role == "independent" and not self.dog_action:
            raise ValueError("dog_role=independent 必须提供 dog_action")
        if self.dog_role == "absent" and self.dog_action:
            raise ValueError("dog_role=absent 时不应提供 dog_action")
        if self.decision and not self.decision_result:
            raise ValueError("存在 decision 时必须立即给出 decision_result")
        visible = " ".join([self.title, self.goal, *self.concrete_events, self.hook,
                            self.start_state, self.turn, self.payoff, self.end_state])
        if re.search(r"ch\d{3}", visible):
            raise ValueError(f"writer-visible 文本不得出现章节号引用：{visible[:60]}")
        if re.search(r"\b(FACT|EVENT|KNW|FS)_[A-Z0-9_]+", visible):
            raise ValueError(f"writer-visible 文本不得出现 canon 元数据 ID：{visible[:60]}")
        return self


class CanonProposalBundle(StrictModel):
    """一次 Planner 输出可以同时提议事实 / 事件 / 知识 / 依赖。"""

    facts: list[CanonProposal] = Field(default_factory=list)
    events: list[EventProposal] = Field(default_factory=list)
    knowledge: list[KnowledgeProposal] = Field(default_factory=list)
    dependencies: list[CanonDependency] = Field(default_factory=list)
    chapters: list[ChapterPlan] = Field(default_factory=list)
