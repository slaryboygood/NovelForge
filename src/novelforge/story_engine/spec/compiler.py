"""M3：NovelSpecCompiler —— NOVEL_SPEC → Story Planning IR（确定性编译 + 确认门禁）。

流程：

    一句话创意 → NovelSpec → find_spec_gaps → SpecProposal → SpecConfirmation
    → compile() → StoryPlanningIR（strict gate + PlanningValidator）→ repository revision

硬规则：

- 提案字段**未经作者确认不得进入**编译（只会出现在 `ignored_proposal_fields`）；
- 编译只生成 intent / theme / world / characters / factions / locations；
  StorySpine / PlotNode / Volume / Arc 属于 M6 / M8，M3 不生成；
- LLM 只产出 proposal（`spec/llm.py`），所有输出必须过 strict schema。
"""

from __future__ import annotations

from typing import Any, Iterable

from novelforge.story_engine.planning.builder import StoryPlanningBuilder
from novelforge.story_engine.planning.models import (
    CharacterPlan,
    FactionPlan,
    LocationPlan,
    NovelIntent,
    PacingPlan,
    ThemePlan,
    WorldPlan,
    WorldRule,
    new_planning_id,
)
from novelforge.story_engine.planning.repository import (
    PlanningRepository,
    PlanningRevisionRecord,
)
from novelforge.story_engine.planning.validation_service import (
    PlanningValidationReport,
    PlanningValidationService,
)

from .gaps import find_spec_gaps
from .models import NovelSpec, SpecCompileResult, SpecConfirmation, SpecProposal

CONFIRMABLE_FIELDS: tuple[str, ...] = (
    "logline", "genre", "subgenres", "target_words", "target_reader", "commercial_promise",
    "reader_experience", "tone", "pace_strategy", "template_id", "themes", "world_seed",
    "characters_seed", "factions_seed", "locations_seed", "constraints",
)


class SpecGateError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(f"{code}: {message}")


class NovelSpecCompiler:
    """确定性编译：同一份 spec + 同一份确认记录 → 同一份 Planning IR。"""

    def __init__(self, *, novel_id: str, canon_snapshot_digest: str = "",
                 known_entity_ids: Iterable[str] = (),
                 known_canon_ids: Iterable[str] = ()) -> None:
        self.novel_id = novel_id
        self.canon_snapshot_digest = canon_snapshot_digest
        self.known_entity_ids = list(known_entity_ids)
        self.known_canon_ids = list(known_canon_ids)

    # ---------------------------------------------------------------- 确认
    def confirm(self, spec: NovelSpec, proposal: SpecProposal,
                confirmed_fields: dict[str, Any], *, confirmation_id: str,
                note: str = "") -> tuple[NovelSpec, SpecConfirmation]:
        """作者确认：只接受提案里真实存在、且属于可确认字段的值。"""

        if proposal.spec_id != spec.spec_id:
            raise SpecGateError("SPEC_ID_MISMATCH",
                                f"proposal.spec_id={proposal.spec_id} != {spec.spec_id}")
        applied: dict[str, Any] = {}
        updated = spec
        for field, value in confirmed_fields.items():
            if field not in CONFIRMABLE_FIELDS:
                raise SpecGateError("SPEC_FIELD_NOT_CONFIRMABLE", f"字段不可确认：{field}")
            entry = proposal.field(field)
            if entry is None:
                raise SpecGateError("SPEC_FIELD_NOT_IN_PROPOSAL",
                                    f"提案里没有字段：{field}")
            applied[field] = value if value is not None else entry.value
            updated = updated.with_field(field, applied[field], "supplied",
                                         source=f"author_confirmation:{confirmation_id}")
        confirmation = SpecConfirmation(confirmation_id=confirmation_id, spec_id=spec.spec_id,
                                        proposal_id=proposal.proposal_id,
                                        confirmed_fields=applied, note=note)
        return updated, confirmation

    # ---------------------------------------------------------------- 编译
    def compile(self, spec: NovelSpec, *, proposal: SpecProposal | None = None
                ) -> SpecCompileResult:
        if spec.novel_id != self.novel_id:
            raise SpecGateError("SPEC_NOVEL_ID_MISMATCH",
                                f"{spec.novel_id} != {self.novel_id}")
        ignored = sorted(set(proposal.field_names())) if proposal else []
        builder = StoryPlanningBuilder(
            novel_id=self.novel_id, title=spec.logline[:120], logline=spec.logline,
            canon_snapshot_digest=self.canon_snapshot_digest, source="novel_spec_compiler")
        builder.with_intent(self._intent(spec)).with_theme(self._theme(spec)) \
            .with_world(self._world(spec)).with_pacing(self._pacing(spec))
        builder.with_characters(self._characters(spec))
        builder.with_factions(self._factions(spec))
        builder.with_locations(self._locations(spec))
        plan = builder.build()
        report: PlanningValidationReport = self._validate(plan)
        result = SpecCompileResult(
            spec_id=spec.spec_id, novel_id=self.novel_id, planning_id=plan.planning_id,
            plan=plan, applied_fields=sorted(spec.field_provenance),
            ignored_proposal_fields=ignored, gaps=find_spec_gaps(spec),
            validation_ok=report.ok(), validation_codes=report.codes())
        return result

    def compile_into_repository(self, spec: NovelSpec, repository: PlanningRepository, *,
                                proposal: SpecProposal | None = None, note: str = ""
                                ) -> tuple[PlanningRevisionRecord, SpecCompileResult]:
        result = self.compile(spec, proposal=proposal)
        if not result.validation_ok or result.plan is None:
            raise SpecGateError("SPEC_COMPILE_INVALID",
                                f"编译结果未通过 Planning gate：{result.validation_codes}")
        record = repository.create(result.plan, status="draft",
                                   source="author", note=note or f"spec {spec.spec_id}")
        return record, result.model_copy(update={"revision_id": record.revision_id})

    # ---------------------------------------------------------------- 组件
    def _validate(self, plan) -> PlanningValidationReport:
        service = PlanningValidationService(
            known_entity_ids=self.known_entity_ids, known_canon_ids=self.known_canon_ids)
        return service.validate_plan(plan)

    def _intent(self, spec: NovelSpec) -> NovelIntent:
        return NovelIntent(
            intent_id=new_planning_id("intent", "MAIN"), novel_id=self.novel_id,
            genre=spec.genre, subgenres=list(spec.subgenres), target_words=spec.target_words,
            target_reader=spec.target_reader, commercial_promise=spec.commercial_promise,
            reader_experience=list(spec.reader_experience), tone=spec.tone,
            pace_strategy=spec.pace_strategy, template_id=spec.template_id,
            provenance=spec.provenance_of("logline"), source=spec.source)

    def _theme(self, spec: NovelSpec) -> ThemePlan:
        themes = list(spec.themes)
        return ThemePlan(
            theme_id=new_planning_id("theme", "MAIN"),
            central_theme=themes[0] if themes else "",
            dramatic_question=self._dramatic_question(spec),
            value_conflicts=themes[1:],
            protagonist_internal_question=self._protagonist_need(spec),
            final_answer_direction="", provenance=spec.provenance_of("themes"),
            source=spec.source)

    def _world(self, spec: NovelSpec) -> WorldPlan:
        rules = [WorldRule(rule_id=new_planning_id("rule", _key(seed.seed_id)),
                           rule_type=seed.rule_type, statement=seed.statement,
                           scope=seed.scope,
                           provenance=spec.provenance_of("world_seed"),
                           source=spec.source)
                 for seed in spec.world_seed]
        return WorldPlan(world_id=new_planning_id("world", "MAIN"), world_rules=rules,
                         history="", hazards=[], taboos=list(spec.constraints),
                         provenance=spec.provenance_of("logline"), source=spec.source)

    def _pacing(self, spec: NovelSpec) -> PacingPlan:
        return PacingPlan(pacing_id=new_planning_id("pacing", "MAIN"),
                          template_id=spec.template_id, strategy=spec.pace_strategy,
                          provenance=spec.provenance_of("pace_strategy"), source=spec.source)

    def _characters(self, spec: NovelSpec) -> list[CharacterPlan]:
        rows: list[CharacterPlan] = []
        for seed in spec.characters_seed:
            character_id = _character_id(seed.seed_id)
            rows.append(CharacterPlan(
                character_id=character_id, entity_ref=seed.entity_ref,
                display_name=seed.display_name, external_goal=seed.external_goal,
                internal_need=seed.internal_need, fear=seed.fear, story_function=seed.role,
                provenance=spec.provenance_of("characters_seed"), source=spec.source))
        return rows

    def _factions(self, spec: NovelSpec) -> list[FactionPlan]:
        return [FactionPlan(faction_id=new_planning_id("faction", _key(seed.seed_id)),
                            display_name=seed.display_name, goal=seed.goal,
                            provenance=spec.provenance_of("factions_seed"),
                            source=spec.source)
                for seed in spec.factions_seed]

    def _locations(self, spec: NovelSpec) -> list[LocationPlan]:
        return [LocationPlan(location_id=new_planning_id("location", _key(seed.seed_id)),
                             display_name=seed.display_name,
                             story_function=seed.story_function,
                             provenance=spec.provenance_of("locations_seed"),
                             source=spec.source)
                for seed in spec.locations_seed]

    # ---------------------------------------------------------------- 文本
    def _dramatic_question(self, spec: NovelSpec) -> str:
        logline = spec.logline.strip()
        if not logline:
            return ""
        return f"{logline}——这件事最终该不该成立？"

    def _protagonist_need(self, spec: NovelSpec) -> str:
        for seed in spec.characters_seed:
            if seed.internal_need:
                return f"{seed.display_name or seed.seed_id}：{seed.internal_need}"
        return ""


def _key(value: str) -> str:
    cleaned = "".join(char if char.isalnum() else "_" for char in value).upper()
    return cleaned[:40] or "MAIN"


def _character_id(seed_id: str) -> str:
    return f"CHAR_{_key(seed_id)}"


__all__ = ["CONFIRMABLE_FIELDS", "NovelSpecCompiler", "SpecGateError"]
