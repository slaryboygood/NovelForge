from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum
from typing import Any, ClassVar, Literal

from pydantic import Field, field_validator, model_validator

from novelforge.models import StrictModel


ID_PATTERN = r"^[a-z][a-z0-9_]{2,63}$"
PACKAGE_ID_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9_-]{2,95}$"


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class StoryStep(StrEnum):
    READER_EXPERIENCE = "reader_experience"
    WORLDVIEW = "worldview"
    BACKGROUND = "background"
    PROTAGONIST = "protagonist"
    CORE_CHARACTERS = "core_characters"
    FACTIONS_LOCATIONS = "factions_locations"
    MAJOR_EVENTS = "major_events"
    PROGRESSION = "progression"
    STYLE = "style"
    AUTHOR_BOUNDARIES = "author_boundaries"


STORY_STEP_ORDER: tuple[StoryStep, ...] = tuple(StoryStep)


class BuilderStatus(StrEnum):
    CREATED = "CREATED"
    CONFIGURING = "CONFIGURING"
    NEEDS_REVIEW = "NEEDS_REVIEW"
    BLUEPRINT_DRAFT = "BLUEPRINT_DRAFT"
    BLUEPRINT_CONFIRMED = "BLUEPRINT_CONFIRMED"
    OUTLINE_DRAFT = "OUTLINE_DRAFT"
    OUTLINE_REVIEW = "OUTLINE_REVIEW"
    OUTLINE_CONFIRMED = "OUTLINE_CONFIRMED"
    PRODUCTION_READY = "PRODUCTION_READY"


class SelectionSource(StrEnum):
    AUTHOR = "author"
    RECOMMENDED = "recommended"
    CUSTOM = "custom"


class RecommendationSource(StrEnum):
    RULE = "rule"
    AI = "ai"


class BlueprintStatus(StrEnum):
    DRAFT = "DRAFT"
    CONFIRMED = "CONFIRMED"
    SUPERSEDED = "SUPERSEDED"


class OutlineLevel(StrEnum):
    BOOK = "BOOK"
    VOLUME = "VOLUME"
    ARC = "ARC"
    CHAPTER = "CHAPTER"


class OutlineStatus(StrEnum):
    DRAFT = "DRAFT"
    REVIEW = "REVIEW"
    NEEDS_REVIEW = "NEEDS_REVIEW"
    CONFIRMED = "CONFIRMED"
    SUPERSEDED = "SUPERSEDED"


class StoryBuilderStep(StrictModel):
    step: StoryStep
    title: str = Field(min_length=1, max_length=80)
    prompt: str = Field(min_length=1, max_length=500)
    selection_mode: Literal["single", "multiple"] = "single"
    min_selections: int = Field(default=1, ge=0)
    max_selections: int = Field(default=1, ge=1)
    skippable: bool = False
    next_steps: list[StoryStep] = Field(default_factory=list)

    @model_validator(mode="after")
    def valid_selection_limits(self) -> "StoryBuilderStep":
        if self.max_selections < self.min_selections:
            raise ValueError("max_selections must be >= min_selections")
        if self.selection_mode == "single" and self.max_selections != 1:
            raise ValueError("single selection steps must have max_selections=1")
        if not self.skippable and self.min_selections == 0:
            raise ValueError("non-skippable steps must require a selection")
        if len(self.next_steps) != len(set(self.next_steps)):
            raise ValueError("next_steps must not contain duplicates")
        return self


class ChoiceOption(StrictModel):
    id: str = Field(pattern=ID_PATTERN)
    step: StoryStep
    name: str = Field(min_length=1, max_length=80)
    summary: str = Field(min_length=1, max_length=500)
    tags: list[str] = Field(default_factory=list)
    requires_all: list[str] = Field(default_factory=list)
    requires_any: list[str] = Field(default_factory=list)
    excludes: list[str] = Field(default_factory=list)
    unlocks: list[str] = Field(default_factory=list)
    unlocks_steps: list[StoryStep] = Field(default_factory=list)
    effects: dict[str, str] = Field(default_factory=dict)
    source_refs: list[str] = Field(default_factory=list)
    priority: int = Field(default=0, ge=-100, le=100)

    @field_validator(
        "tags",
        "requires_all",
        "requires_any",
        "excludes",
        "unlocks",
        "unlocks_steps",
        "source_refs",
    )
    @classmethod
    def unique_list(cls, value: list) -> list:
        if len(value) != len(set(value)):
            raise ValueError("list values must be unique")
        return value

    @model_validator(mode="after")
    def valid_self_references(self) -> "ChoiceOption":
        required = set(self.requires_all) | set(self.requires_any)
        references = required | set(self.excludes) | set(self.unlocks)
        if self.id in references:
            raise ValueError("an option cannot reference itself")
        if required & set(self.excludes):
            raise ValueError("the same option cannot be both required and excluded")
        return self


class DesignOption(StrictModel):
    id: str = Field(pattern=ID_PATTERN)
    name: str = Field(min_length=1, max_length=80)
    summary: str = Field(min_length=1, max_length=500)
    requires_all: list[str] = Field(default_factory=list)
    requires_any: list[str] = Field(default_factory=list)
    recommended_by: list[str] = Field(default_factory=list)
    examples: list[str] = Field(default_factory=list)
    effects: dict[str, str] = Field(default_factory=dict)


class DesignField(StrictModel):
    id: str = Field(pattern=ID_PATTERN)
    step: StoryStep
    title: str = Field(min_length=1, max_length=80)
    prompt: str = Field(min_length=1, max_length=500)
    depends_on: list[str] = Field(default_factory=list)
    options: list[DesignOption] = Field(min_length=2)


class DesignSelection(StrictModel):
    option_id: str | None = Field(default=None, pattern=ID_PATTERN)
    custom_text: str = Field(default="", max_length=500)
    basis: dict[str, str] = Field(default_factory=dict)
    revision: int = Field(ge=1)

    @model_validator(mode="after")
    def one_value(self):
        if bool(self.option_id) == bool(self.custom_text.strip()):
            raise ValueError("设计选择必须为一个选项或一段自定义内容")
        return self


class StoryChoiceCatalog(StrictModel):
    schema_version: Literal[1] = 1
    catalog_id: str = Field(pattern=ID_PATTERN)
    language: Literal["zh-CN"] = "zh-CN"
    steps: list[StoryBuilderStep] = Field(min_length=1)
    options: list[ChoiceOption] = Field(min_length=1)
    design_fields: list[DesignField] = Field(default_factory=list)

    @model_validator(mode="after")
    def valid_catalog_graph(self) -> "StoryChoiceCatalog":
        step_ids = [item.step for item in self.steps]
        if len(step_ids) != len(set(step_ids)):
            raise ValueError("catalog step IDs must be unique")
        if set(step_ids) != set(STORY_STEP_ORDER):
            raise ValueError("catalog must define every story step exactly once")

        option_ids = [item.id for item in self.options]
        if len(option_ids) != len(set(option_ids)):
            raise ValueError("catalog option IDs must be unique")
        options_by_id = {item.id: item for item in self.options}
        order = {step: index for index, step in enumerate(STORY_STEP_ORDER)}

        for step in self.steps:
            if not any(option.step == step.step for option in self.options):
                raise ValueError(f"story step {step.step} requires at least one option")
            if any(order[next_step] <= order[step.step] for next_step in step.next_steps):
                raise ValueError("next_steps must point forward in the story journey")

        for option in self.options:
            references = (
                option.requires_all
                + option.requires_any
                + option.excludes
                + option.unlocks
            )
            missing = [reference for reference in references if reference not in options_by_id]
            if missing:
                raise ValueError(f"option {option.id} contains unknown references: {missing}")
            required = option.requires_all + option.requires_any
            if any(order[options_by_id[reference].step] >= order[option.step] for reference in required):
                raise ValueError("option requirements must reference earlier story steps")
            if any(order[options_by_id[reference].step] <= order[option.step] for reference in option.unlocks):
                raise ValueError("option unlocks must reference later story steps")
        known_fields = set(step_ids)
        known_options = set(option_ids)
        for node in self.design_fields:
            if node.id in known_fields or not set(node.depends_on) <= known_fields:
                raise ValueError("设计节点重复或依赖未知及后置节点")
            new_ids = [option.id for option in node.options]
            if len(set(new_ids)) != len(new_ids) or set(new_ids) & known_options:
                raise ValueError("设计选项编号必须全局唯一")
            for option in node.options:
                if not set(option.requires_all + option.requires_any + option.recommended_by) <= known_options:
                    raise ValueError("设计选项条件必须引用已有前置选项")
            known_fields.add(node.id)
            known_options.update(new_ids)
        return self


class StorySelection(StrictModel):
    selection_id: str = Field(pattern=PACKAGE_ID_PATTERN)
    step: StoryStep
    option_id: str | None = Field(default=None, pattern=ID_PATTERN)
    custom_text: str = Field(default="", max_length=2000)
    source: SelectionSource = SelectionSource.AUTHOR
    revision: int = Field(ge=1)
    selected_at: datetime = Field(default_factory=utc_now)

    @model_validator(mode="after")
    def has_selection_content(self) -> "StorySelection":
        if not self.option_id and not self.custom_text.strip():
            raise ValueError("option_id or custom_text is required")
        if self.source == SelectionSource.CUSTOM and not self.custom_text.strip():
            raise ValueError("custom selections require custom_text")
        return self


class ChoiceConflict(StrictModel):
    code: str = Field(pattern=r"^[A-Z][A-Z0-9_]{2,63}$")
    message: str = Field(min_length=1, max_length=500)
    option_ids: list[str] = Field(default_factory=list)
    blocking: bool = True

    @field_validator("option_ids")
    @classmethod
    def unique_option_ids(cls, value: list[str]) -> list[str]:
        if len(value) != len(set(value)):
            raise ValueError("option_ids must not contain duplicates")
        return value


class RecommendationItem(StrictModel):
    option_id: str | None = Field(default=None, pattern=ID_PATTERN)
    custom_text: str = Field(default="", max_length=500)
    reason: str = Field(min_length=1, max_length=500)
    fit_tags: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    source: RecommendationSource
    rank: int = Field(ge=1, le=5)

    @model_validator(mode="after")
    def valid_recommendation_target(self) -> "RecommendationItem":
        has_option = self.option_id is not None
        has_custom = bool(self.custom_text.strip())
        if has_option == has_custom:
            raise ValueError("a recommendation requires exactly one option_id or custom_text")
        if self.source == RecommendationSource.RULE and not has_option:
            raise ValueError("rule recommendations must reference a catalog option")
        return self


class RecommendationResult(StrictModel):
    step: StoryStep
    based_on_version: int = Field(ge=0)
    recommendations: list[RecommendationItem] = Field(default_factory=list, max_length=5)
    conflicts: list[ChoiceConflict] = Field(default_factory=list)
    unlocked_steps: list[StoryStep] = Field(default_factory=list)
    can_continue: bool = True

    @model_validator(mode="after")
    def valid_recommendation_set(self) -> "RecommendationResult":
        option_ids = [item.option_id for item in self.recommendations if item.option_id]
        custom_texts = [item.custom_text.strip().casefold() for item in self.recommendations if item.custom_text]
        ranks = [item.rank for item in self.recommendations]
        if len(option_ids) != len(set(option_ids)):
            raise ValueError("recommendations must not repeat an option")
        if len(custom_texts) != len(set(custom_texts)):
            raise ValueError("recommendations must not repeat custom text")
        if len(ranks) != len(set(ranks)):
            raise ValueError("recommendation ranks must be unique")
        if len(self.unlocked_steps) != len(set(self.unlocked_steps)):
            raise ValueError("unlocked_steps must not contain duplicates")
        if any(item.blocking for item in self.conflicts) and self.can_continue:
            raise ValueError("blocking conflicts require can_continue=false")
        return self


class StoryBuilderSession(StrictModel):
    session_id: str = Field(pattern=PACKAGE_ID_PATTERN)
    project_id: str = Field(pattern=PACKAGE_ID_PATTERN)
    status: BuilderStatus = BuilderStatus.CREATED
    current_step: StoryStep = StoryStep.READER_EXPERIENCE
    completed_steps: list[StoryStep] = Field(default_factory=list)
    selections: list[StorySelection] = Field(default_factory=list)
    design_choices: dict[str, DesignSelection] = Field(default_factory=dict)
    needs_review_steps: list[StoryStep] = Field(default_factory=list)
    selection_version: int = Field(default=0, ge=0)
    recommendation_version: int = Field(default=0, ge=0)
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)

    @model_validator(mode="after")
    def valid_versions_and_uniqueness(self) -> "StoryBuilderSession":
        if self.recommendation_version > self.selection_version:
            raise ValueError("recommendation_version cannot exceed selection_version")
        if len(self.completed_steps) != len(set(self.completed_steps)):
            raise ValueError("completed_steps must not contain duplicates")
        if len(self.needs_review_steps) != len(set(self.needs_review_steps)):
            raise ValueError("needs_review_steps must not contain duplicates")
        selection_ids = [item.selection_id for item in self.selections]
        if len(selection_ids) != len(set(selection_ids)):
            raise ValueError("selection_id must be unique within a session")
        option_keys = [(item.step, item.option_id) for item in self.selections if item.option_id]
        if len(option_keys) != len(set(option_keys)):
            raise ValueError("an option can be selected only once per step")
        if self.selections and max(item.revision for item in self.selections) > self.selection_version:
            raise ValueError("selection revision cannot exceed selection_version")
        if any(item.revision > self.selection_version for item in self.design_choices.values()):
            raise ValueError("设计选择版本不能超过会话版本")
        if self.updated_at < self.created_at:
            raise ValueError("updated_at cannot be earlier than created_at")
        return self


class BlueprintSection(StrictModel):
    step: StoryStep
    summary: str = Field(min_length=1, max_length=2000)
    selected_option_ids: list[str] = Field(default_factory=list)
    custom_inputs: list[str] = Field(default_factory=list)
    source_selection_ids: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def has_traceable_source(self) -> "BlueprintSection":
        if not self.selected_option_ids and not self.custom_inputs:
            raise ValueError("a blueprint section must contain a selection or custom input")
        if not self.source_selection_ids:
            raise ValueError("a blueprint section must reference its source selections")
        for values in (self.selected_option_ids, self.custom_inputs, self.source_selection_ids):
            if len(values) != len(set(values)):
                raise ValueError("blueprint section lists must not contain duplicates")
        return self


class StoryBlueprint(StrictModel):
    required_steps: ClassVar[tuple[StoryStep, ...]] = STORY_STEP_ORDER

    blueprint_id: str = Field(pattern=PACKAGE_ID_PATTERN)
    project_id: str = Field(pattern=PACKAGE_ID_PATTERN)
    source_session_id: str = Field(pattern=PACKAGE_ID_PATTERN)
    source_selection_version: int = Field(ge=1)
    version: int = Field(default=1, ge=1)
    status: BlueprintStatus = BlueprintStatus.DRAFT
    premise: str = Field(min_length=1, max_length=2000)
    sections: list[BlueprintSection] = Field(default_factory=list)
    design_choices: dict[str, DesignSelection] = Field(default_factory=dict)
    design_summaries: dict[str, str] = Field(default_factory=dict)
    design_effects: dict[str, dict[str, str]] = Field(default_factory=dict)
    unresolved_conflicts: list[ChoiceConflict] = Field(default_factory=list)
    confirmed_by_author: bool = False
    created_at: datetime = Field(default_factory=utc_now)

    @model_validator(mode="after")
    def valid_confirmation(self) -> "StoryBlueprint":
        section_steps = [section.step for section in self.sections]
        if len(section_steps) != len(set(section_steps)):
            raise ValueError("a blueprint may contain only one section per step")
        if self.status == BlueprintStatus.CONFIRMED:
            missing = set(self.required_steps) - set(section_steps)
            if missing:
                raise ValueError("confirmed blueprints require every story step")
            if self.unresolved_conflicts:
                raise ValueError("confirmed blueprints cannot contain unresolved conflicts")
            if not self.confirmed_by_author:
                raise ValueError("confirmed blueprints require author confirmation")
        return self


class OutlineItem(StrictModel):
    item_id: str = Field(pattern=PACKAGE_ID_PATTERN)
    title: str = Field(min_length=1, max_length=120)
    summary: str = Field(min_length=1, max_length=4000)
    start_state: str = Field(default="", max_length=2000)
    end_state: str = Field(default="", max_length=2000)
    goals: list[str] = Field(default_factory=list)
    conflicts: list[str] = Field(default_factory=list)
    major_turns: list[str] = Field(default_factory=list)
    ending_hook: str = Field(default="", max_length=1000)
    must_keep: list[str] = Field(default_factory=list)
    must_avoid: list[str] = Field(default_factory=list)
    # 机器可追溯的来源 id（route record / planned stage）。作者可见文本里不出现这些 id，
    # 但「这一章能不能追溯到真实来源」必须仍然可验证（NF-004）。
    source_ids: list[str] = Field(default_factory=list)
    child_ids: list[str] = Field(default_factory=list)
    pov: str = Field(default="", max_length=500)
    time: str = Field(default="", max_length=500)
    location: str = Field(default="", max_length=500)
    participants: list[str] = Field(default_factory=list)
    information_changes: list[str] = Field(default_factory=list)
    costs: list[str] = Field(default_factory=list)
    # Canon-aware 增量字段（旧包缺省为空，保持 legacy 兼容）
    chapter_uuid: str = Field(default="", max_length=128)
    canon_fact_ids: list[str] = Field(default_factory=list)
    canon_event_ids: list[str] = Field(default_factory=list)
    canon_source_refs: list[dict[str, Any]] = Field(default_factory=list)
    context_manifest_id: str = Field(default="", max_length=80)
    # Chapter Semantic IR V1（增量、可选；legacy chapter 允许为空）
    semantic_ir_ref: str | None = Field(default=None, max_length=160)
    semantic_ir_version: int | None = None


class OutlinePackage(StrictModel):
    package_id: str = Field(pattern=PACKAGE_ID_PATTERN)
    project_id: str = Field(pattern=PACKAGE_ID_PATTERN)
    blueprint_id: str = Field(pattern=PACKAGE_ID_PATTERN)
    blueprint_version: int = Field(ge=1)
    level: OutlineLevel
    status: OutlineStatus = OutlineStatus.DRAFT
    version: int = Field(default=1, ge=1)
    parent_package_id: str | None = Field(default=None, pattern=PACKAGE_ID_PATTERN)
    items: list[OutlineItem] = Field(default_factory=list)
    source_package_versions: dict[str, int] = Field(default_factory=dict)
    route_source: dict[str, str] = Field(default_factory=dict)
    route_history: list[dict[str, str]] = Field(default_factory=list)
    design_sections: dict[str, str] = Field(default_factory=dict)
    pending_questions: list[str] = Field(default_factory=list)
    confirmed_by_author: bool = False
    created_at: datetime = Field(default_factory=utc_now)

    @model_validator(mode="after")
    def valid_hierarchy_and_confirmation(self) -> "OutlinePackage":
        if self.level == OutlineLevel.BOOK and self.parent_package_id:
            raise ValueError("book outlines cannot have a parent package")
        if self.level != OutlineLevel.BOOK and not self.parent_package_id:
            raise ValueError("non-book outlines require a parent package")
        item_ids = [item.item_id for item in self.items]
        if len(item_ids) != len(set(item_ids)):
            raise ValueError("outline item IDs must be unique")
        if self.status == OutlineStatus.CONFIRMED:
            if not self.items:
                raise ValueError("confirmed outlines require at least one item")
            if not self.confirmed_by_author:
                raise ValueError("confirmed outlines require author confirmation")
        return self
