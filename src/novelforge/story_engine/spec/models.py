"""M3：NOVEL_SPEC V2 数据模型（一句话创意 → 规格 → 缺口 → 提案 → 作者确认）。

边界：

- NovelSpec 是**作者输入规格**，不是 Planning truth，也不是 Canon / StoryState；
- SpecProposal 只能"建议"，只有作者确认（SpecConfirmation）后才进入编译；
- 编译产物是 `StoryPlanningIR`（future planning truth），必须过 Planning strict gate 与
  PlanningValidator；M3 不生成 StorySpine / PlotNode / Volume / Arc。
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import Field, field_validator

from novelforge.models import StrictModel
from novelforge.story_engine.planning.enums import PLANNING_SCHEMA_VERSION, Provenance
from novelforge.story_engine.planning.models import StoryPlanningIR

SPEC_ID_PREFIX = "SPEC"
FORBIDDEN_SPEC_ID = re.compile(r"^(ch\d+|chapter[_-]?\d+|volume\d+[_-]?ch\d+)$", re.I)
SPEC_KEY_PATTERN = re.compile(r"^[A-Z0-9][A-Z0-9_]{0,63}$")

GapSeverity = Literal["blocking", "important", "optional"]


def spec_id(value: str) -> str:
    if FORBIDDEN_SPEC_ID.match(value or ""):
        raise ValueError(f"章节号 / 序号不能作为 spec identity：{value}")
    if not (value or "").startswith(SPEC_ID_PREFIX + "_"):
        raise ValueError(f"spec id 前缀必须是 {SPEC_ID_PREFIX}_：{value}")
    key = value[len(SPEC_ID_PREFIX) + 1:]
    if not SPEC_KEY_PATTERN.match(key):
        raise ValueError(f"spec key 形态非法（A-Z0-9_）：{key}")
    return value


def new_spec_id(key: str) -> str:
    return f"{SPEC_ID_PREFIX}_{key.upper()}"


class SpecWorldSeed(StrictModel):
    seed_id: str = Field(min_length=3, max_length=48)
    statement: str = Field(default="", max_length=400)
    rule_type: Literal["hard_rule", "soft_rule", "belief", "rumor", "unknown"] = "hard_rule"
    scope: str = Field(default="", max_length=120)


class SpecCharacterSeed(StrictModel):
    seed_id: str = Field(min_length=2, max_length=48)
    display_name: str = Field(default="", max_length=80)
    role: str = Field(default="", max_length=64)
    entity_ref: str = Field(default="", max_length=160)
    external_goal: str = Field(default="", max_length=300)
    internal_need: str = Field(default="", max_length=300)
    fear: str = Field(default="", max_length=300)


class SpecFactionSeed(StrictModel):
    seed_id: str = Field(min_length=2, max_length=48)
    display_name: str = Field(default="", max_length=80)
    goal: str = Field(default="", max_length=300)


class SpecLocationSeed(StrictModel):
    seed_id: str = Field(min_length=2, max_length=48)
    display_name: str = Field(default="", max_length=80)
    story_function: str = Field(default="", max_length=200)


class NovelSpec(StrictModel):
    """作者规格：允许留空；留白由 gaps + proposal + confirmation 处理。"""

    spec_id: str = Field(min_length=6, max_length=64)
    novel_id: str = Field(min_length=1, max_length=96)
    schema_version: int = Field(default=1, ge=1)
    logline: str = Field(default="", max_length=400)
    genre: str = Field(default="", max_length=64)
    subgenres: list[str] = Field(default_factory=list)
    target_words: int = Field(default=0, ge=0, le=20_000_000)
    target_reader: str = Field(default="", max_length=200)
    commercial_promise: str = Field(default="", max_length=300)
    reader_experience: list[str] = Field(default_factory=list)
    tone: str = Field(default="", max_length=200)
    pace_strategy: str = Field(default="", max_length=200)
    template_id: str = Field(default="", max_length=64)
    themes: list[str] = Field(default_factory=list)
    world_seed: list[SpecWorldSeed] = Field(default_factory=list)
    characters_seed: list[SpecCharacterSeed] = Field(default_factory=list)
    factions_seed: list[SpecFactionSeed] = Field(default_factory=list)
    locations_seed: list[SpecLocationSeed] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)
    field_provenance: dict[str, Provenance] = Field(default_factory=dict)
    source: str = Field(default="author", max_length=96)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @field_validator("spec_id")
    @classmethod
    def _id(cls, value: str) -> str:
        return spec_id(value)

    def provenance_of(self, field: str) -> Provenance:
        return self.field_provenance.get(field, "supplied")

    def field_value(self, field: str) -> Any:
        return getattr(self, field, None)

    def with_field(self, field: str, value: Any, provenance: Provenance,
                   *, source: str = "") -> "NovelSpec":
        if not hasattr(self, field):
            raise KeyError(field)
        payload = self.model_dump(mode="json")
        payload[field] = value
        payload.setdefault("field_provenance", {})[field] = provenance
        if source:
            payload["source"] = source
        return NovelSpec.model_validate(payload)


class SpecGap(StrictModel):
    field: str = Field(min_length=2, max_length=64)
    domain: str = Field(default="intent", max_length=32)
    severity: GapSeverity = "important"
    why: str = Field(default="", max_length=200)
    suggestion: str = Field(default="", max_length=200)


class SpecFieldProposal(StrictModel):
    field: str = Field(min_length=2, max_length=64)
    value: Any = None
    rationale: str = Field(default="", max_length=300)
    provenance: Provenance = "generated"
    source: str = Field(default="planner", max_length=96)
    confidence: float = Field(default=0.6, ge=0, le=1)


class SpecProposal(StrictModel):
    """LLM / 规则产出的**提案**：只有经作者确认才能进入编译。"""

    proposal_id: str = Field(min_length=6, max_length=64)
    spec_id: str = Field(min_length=6, max_length=64)
    novel_id: str = Field(min_length=1, max_length=96)
    provider: str = Field(default="planner", max_length=64)
    model: str = Field(default="", max_length=64)
    fields: list[SpecFieldProposal] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @field_validator("spec_id")
    @classmethod
    def _spec(cls, value: str) -> str:
        return spec_id(value)

    def field(self, name: str) -> SpecFieldProposal | None:
        return next((item for item in self.fields if item.field == name), None)

    def field_names(self) -> list[str]:
        return [item.field for item in self.fields]


class SpecConfirmation(StrictModel):
    """作者确认：只有这里列出的字段会以 supplied 身份进入 Planning IR。"""

    confirmation_id: str = Field(min_length=6, max_length=64)
    spec_id: str = Field(min_length=6, max_length=64)
    proposal_id: str = Field(default="", max_length=64)
    confirmed_fields: dict[str, Any] = Field(default_factory=dict)
    confirmed_by: Literal["author"] = "author"
    confirmed_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    note: str = Field(default="", max_length=300)

    @field_validator("spec_id")
    @classmethod
    def _spec(cls, value: str) -> str:
        return spec_id(value)


class SpecCompileResult(StrictModel):
    spec_id: str = Field(min_length=6, max_length=64)
    novel_id: str = Field(min_length=1, max_length=96)
    planning_id: str = Field(default="", max_length=64)
    planning_schema_version: int = PLANNING_SCHEMA_VERSION
    plan: StoryPlanningIR | None = None
    applied_fields: list[str] = Field(default_factory=list)
    ignored_proposal_fields: list[str] = Field(default_factory=list)
    gaps: list[SpecGap] = Field(default_factory=list)
    validation_ok: bool = False
    validation_codes: list[str] = Field(default_factory=list)
    revision_id: str = Field(default="", max_length=64)


__all__ = [
    "GapSeverity",
    "NovelSpec",
    "SPEC_ID_PREFIX",
    "SpecCharacterSeed",
    "SpecCompileResult",
    "SpecConfirmation",
    "SpecFactionSeed",
    "SpecFieldProposal",
    "SpecGap",
    "SpecLocationSeed",
    "SpecProposal",
    "SpecWorldSeed",
    "new_spec_id",
    "spec_id",
]
