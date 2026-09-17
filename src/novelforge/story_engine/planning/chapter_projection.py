"""M9：Chapter IR 只读 projection（M13 UI / M16 Export / Writer-ready context）。

全部 `read_only=True` + `non_authoritative=True`：Detailed Outline 只是 Chapter Semantic IR
的 writer-visible projection（structure is fact, prose is projection）；作者在 UI 上改文本
不能绕过 Chapter IR edit/service。
"""

from __future__ import annotations

from typing import Any, Literal, Mapping, Sequence

from pydantic import Field

from novelforge.models import StrictModel
from novelforge.story_engine.chapter_ir.models import ChapterSemanticIR

from .chapter_compiler import (
    ArcExecutionCoverageReport,
    ChapterAllocation,
    ChapterCompilationCandidate,
)
from .chapter_units import ChapterSemanticUnit
from .findings import PlanningFinding
from .models import StoryPlanningIR

PACING_DIMENSIONS: tuple[str, ...] = ("tension", "mystery", "exploration", "combat",
                                      "relationship", "reveal", "progression", "reward",
                                      "climax")


class ChapterOutlineEntry(StrictModel):
    """Detailed Chapter Outline 的单字段（带 source refs，writer-ready）。"""

    field_name: str = Field(min_length=2, max_length=48)
    text: str = Field(default="", max_length=400)
    source_refs: list[str] = Field(default_factory=list)
    status: str = Field(default="OK", max_length=24)
    non_authoritative: bool = True


class DetailedChapterOutlineProjection(StrictModel):
    """一章的 Detailed Outline（Chapter IR 的 projection，不是 truth）。"""

    chapter_id: str = Field(min_length=3, max_length=128)
    arc_id: str = Field(default="", max_length=64)
    volume_id: str = Field(default="", max_length=64)
    order_index: int = 0
    display_number: int = 0
    title: str = Field(default="", max_length=120)
    chapter_function: str = Field(default="setup", max_length=24)
    goal: str = Field(default="", max_length=300)
    start_state: dict[str, str] = Field(default_factory=dict)
    end_state: dict[str, str] = Field(default_factory=dict)
    participants: list[str] = Field(default_factory=list)
    location_ids: list[str] = Field(default_factory=list)
    events: list[dict[str, Any]] = Field(default_factory=list)
    fields: list[ChapterOutlineEntry] = Field(default_factory=list)
    information_release: list[str] = Field(default_factory=list)
    foreshadow: list[str] = Field(default_factory=list)
    relationships: list[str] = Field(default_factory=list)
    faction_actions: list[str] = Field(default_factory=list)
    progression: list[str] = Field(default_factory=list)
    resource_equipment: list[str] = Field(default_factory=list)
    reward: list[str] = Field(default_factory=list)
    map_changes: list[str] = Field(default_factory=list)
    world_change: list[str] = Field(default_factory=list)
    hook: list[str] = Field(default_factory=list)
    causality: dict[str, list[str]] = Field(default_factory=dict)
    constraints: list[str] = Field(default_factory=list)
    source_refs: list[str] = Field(default_factory=list)
    evidence_refs: list[str] = Field(default_factory=list)
    read_only: Literal[True] = True
    non_authoritative: Literal[True] = True


class ChapterWriterContextProjection(StrictModel):
    """M16 Writer Integration 的结构化上下文（M9 只提供数据，不写正文）。"""

    novel_id: str = Field(default="", max_length=96)
    planning_revision_id: str = Field(default="", max_length=64)
    arc_id: str = Field(default="", max_length=64)
    chapter_ids: list[str] = Field(default_factory=list)
    outlines: list[DetailedChapterOutlineProjection] = Field(default_factory=list)
    knowledge_boundaries: dict[str, list[str]] = Field(default_factory=dict)
    forbidden_reveals: list[str] = Field(default_factory=list)
    read_only: Literal[True] = True
    non_authoritative: Literal[True] = True


class ChapterIRInspectorProjection(StrictModel):
    chapter_id: str = Field(default="", max_length=128)
    arc_id: str = Field(default="", max_length=64)
    function: str = Field(default="", max_length=24)
    event_ids: list[str] = Field(default_factory=list)
    effect_ids: list[str] = Field(default_factory=list)
    transition_ids: list[str] = Field(default_factory=list)
    evidence_fields: list[str] = Field(default_factory=list)
    not_applicable_fields: list[str] = Field(default_factory=list)
    findings: list[dict[str, str]] = Field(default_factory=list)
    machine_token_clean: bool = True
    read_only: Literal[True] = True
    non_authoritative: Literal[True] = True


class ArcCompilationProjection(StrictModel):
    arc_id: str = Field(default="", max_length=64)
    volume_id: str = Field(default="", max_length=64)
    status: str = Field(default="pending", max_length=24)
    budget_min: int = 0
    budget_preferred: int = 0
    budget_max: int = 0
    planned_chapter_count: int = 0
    chapter_ids: list[str] = Field(default_factory=list)
    coverage: ArcExecutionCoverageReport = Field(default_factory=ArcExecutionCoverageReport)
    warning_codes: list[str] = Field(default_factory=list)
    blocking_codes: list[str] = Field(default_factory=list)
    resume_required: bool = False
    read_only: Literal[True] = True
    non_authoritative: Literal[True] = True


class ChapterCompilationProgressProjection(StrictModel):
    """M13 Compile Center：Volume / Arc / 预算 / 计划章数 / 当前进度 / blocker / resume。"""

    session_id: str = Field(default="", max_length=64)
    status: str = Field(default="pending", max_length=24)
    scope_complete: bool = False
    arcs_completed: int = 0
    arcs_total: int = 0
    current_arc_id: str = Field(default="", max_length=64)
    current_chapter_id: str = Field(default="", max_length=128)
    current_chapter_title: str = Field(default="", max_length=120)
    chapters_written: int = 0
    chapters_planned: int = 0
    blocked_batch_ids: list[str] = Field(default_factory=list)
    human_review_batch_ids: list[str] = Field(default_factory=list)
    retrying_batch_ids: list[str] = Field(default_factory=list)
    arcs: list[ArcCompilationProjection] = Field(default_factory=list)
    read_only: Literal[True] = True
    non_authoritative: Literal[True] = True


class ChapterTreeChapter(StrictModel):
    chapter_id: str = Field(default="", max_length=128)
    display_number: int = 0
    order_index: int = 0
    title: str = Field(default="", max_length=120)
    function: str = Field(default="", max_length=24)
    read_only: Literal[True] = True


class ChapterTreeArc(StrictModel):
    arc_id: str = Field(default="", max_length=64)
    index: int = 0
    title: str = Field(default="", max_length=120)
    detail_level: str = Field(default="", max_length=24)
    chapters: list[ChapterTreeChapter] = Field(default_factory=list)
    read_only: Literal[True] = True


class ChapterTreeVolume(StrictModel):
    volume_id: str = Field(default="", max_length=64)
    index: int = 0
    title: str = Field(default="", max_length=120)
    arcs: list[ChapterTreeArc] = Field(default_factory=list)
    read_only: Literal[True] = True


class ChapterTreeProjection(StrictModel):
    novel_id: str = Field(default="", max_length=96)
    planning_revision_id: str = Field(default="", max_length=64)
    volumes: list[ChapterTreeVolume] = Field(default_factory=list)
    chapter_total: int = 0
    read_only: Literal[True] = True
    non_authoritative: Literal[True] = True


class ArcChapterPacingProjection(StrictModel):
    """从 Chapter IR 派生的 arc pacing（不是新的 Pacing truth）。"""

    arc_id: str = Field(default="", max_length=64)
    dimensions: list[str] = Field(default_factory=lambda: list(PACING_DIMENSIONS))
    values: dict[str, list[float]] = Field(default_factory=dict)
    function_counts: dict[str, int] = Field(default_factory=dict)
    read_only: Literal[True] = True
    non_authoritative: Literal[True] = True


def _plan_lookup(plan: StoryPlanningIR) -> dict[str, Any]:
    truths = {truth.truth_id: truth for arc in plan.information_arcs for truth in arc.truths}
    foreshadows = {item.foreshadow_id: item for item in plan.foreshadow_plans}
    return {"truths": truths, "foreshadows": foreshadows}


def render_chapter_fields(ir: ChapterSemanticIR, plan: StoryPlanningIR,
                          allocation: ChapterAllocation | None = None
                          ) -> list[ChapterOutlineEntry]:
    """确定性 writer-visible 渲染（不引入 IR 之外的事实，不写 prose）。"""

    lookup = _plan_lookup(plan)
    rows: list[ChapterOutlineEntry] = []
    evidence = {item.field_name: item for item in ir.field_evidence}
    not_applicable = set(ir.not_applicable_fields)

    def add(field_name: str, text: str, refs: Sequence[str] = ()) -> None:
        if not text:
            status = "NOT_APPLICABLE" if field_name in not_applicable else "NO_EVIDENCE"
            rows.append(ChapterOutlineEntry(field_name=field_name, text="", status=status))
            return
        rows.append(ChapterOutlineEntry(field_name=field_name, text=text[:400],
                                        source_refs=[item for item in refs if item]))

    binding = evidence.get("decision")
    decision_text = ""
    if binding:
        event = next((item for item in ir.event_frames
                      if item.event_id in binding.event_ids and item.decision_action), None)
        if event is not None:
            decision_text = (event.action_text or "做出选择")[:200]
    add("decision", decision_text, (binding.event_ids if binding else []))
    cost_effect = None
    for effect_id in (evidence.get("cost").effect_ids if evidence.get("cost") else []):
        cost_effect = ir.effect(effect_id)
    add("cost", (cost_effect.after_state if cost_effect else ""),
        [cost_effect.effect_id] if cost_effect else [])
    loss_effect = None
    for effect_id in (evidence.get("loss").effect_ids if evidence.get("loss") else []):
        loss_effect = ir.effect(effect_id)
    add("loss", (loss_effect.after_state if loss_effect else ""),
        [loss_effect.effect_id] if loss_effect else [])
    turn_text = ""
    turn_refs: list[str] = []
    if evidence.get("turn"):
        for transition_id in evidence["turn"].transition_ids:
            transition = next((item for item in ir.state_transitions
                               if item.transition_id == transition_id), None)
            if transition is not None:
                turn_text = f"{transition.from_state}→{transition.to_state}"
                turn_refs.append(transition.transition_id)
                break
        if not turn_text:
            for effect_id in evidence["turn"].effect_ids:
                effect = ir.effect(effect_id)
                if effect is not None and effect.is_narrative_pivot:
                    turn_text = effect.after_state or effect.effect_type
                    turn_refs.append(effect.effect_id)
    add("turn", turn_text, turn_refs)
    payoff_effect = None
    for effect_id in (evidence.get("payoff").effect_ids if evidence.get("payoff") else []):
        payoff_effect = ir.effect(effect_id)
    add("payoff", (payoff_effect.after_state if payoff_effect else ""),
        [payoff_effect.effect_id] if payoff_effect else [])
    world_text = ""
    world_refs: list[str] = []
    if evidence.get("world_state_change"):
        for transition_id in evidence["world_state_change"].transition_ids:
            transition = next((item for item in ir.state_transitions
                               if item.transition_id == transition_id), None)
            if transition is not None:
                world_text = f"{transition.from_state}→{transition.to_state}"
                world_refs.append(transition.transition_id)
    add("world_state_change", world_text, world_refs)
    info_truths: list[str] = []
    info_refs: list[str] = []
    for effect in ir.effects:
        for truth_id in effect.knowledge_delta:
            truth = lookup["truths"].get(truth_id)
            info_truths.append(truth.statement[:200] if truth is not None else truth_id)
            info_refs.append(truth_id)
    add("information_release", "；".join(info_truths[:3]), info_refs)
    if allocation is not None:
        foreshadow_text = []
        for foreshadow_id in allocation.source_planning_ids:
            row = lookup["foreshadows"].get(foreshadow_id)
            if row is not None:
                foreshadow_text.append(row.intended_payoff[:120] or row.subject[:120])
        add("foreshadow", "；".join(foreshadow_text[:3]),
            [item for item in allocation.source_planning_ids
             if item in lookup["foreshadows"]])
    return rows


def project_detailed_outline(candidate: ChapterCompilationCandidate, plan: StoryPlanningIR,
                             *, revision_id: str = ""
                             ) -> list[DetailedChapterOutlineProjection]:
    """Chapter Allocation + Chapter IR → Detailed Chapter Outline（只读）。"""

    allocations = {item.chapter_id: item for item in candidate.chapter_allocations}
    rows: list[DetailedChapterOutlineProjection] = []
    for ir in sorted(candidate.chapter_irs, key=lambda item: item.temporal_position or 0):
        allocation = allocations.get(ir.chapter_uuid)
        fields = render_chapter_fields(ir, plan, allocation)
        by_name = {item.field_name: item for item in fields}
        events = [{"event_id": event.event_id, "action": event.action_text,
                   "action_type": event.action_type, "actor_ids": list(event.actor_ids),
                   "intent": event.intent, "opposition": "",
                   "source_refs": list(event.fact_refs)} for event in ir.event_frames]
        rows.append(DetailedChapterOutlineProjection(
            chapter_id=ir.chapter_uuid, arc_id=ir.arc_id, volume_id=ir.volume_id,
            order_index=allocation.order_index if allocation else 0,
            display_number=ir.temporal_position or 0,
            title=_title(ir, allocation),
            chapter_function=allocation.chapter_function if allocation else "setup",
            goal=ir.goal, start_state=dict(allocation.planned_start_state) if allocation else {},
            end_state=dict(allocation.planned_end_state) if allocation else {},
            participants=list(ir.participant_ids), location_ids=list(ir.location_ids),
            events=events, fields=fields,
            information_release=list(allocation.reader_release) if allocation else [],
            foreshadow=[item for item in (by_name.get("foreshadow").source_refs
                                          if by_name.get("foreshadow") else [])],
            relationships=list(allocation.unit_ids) if allocation else [],
            faction_actions=[item for item in ir.source_refs if item.startswith("FACTION")],
            progression=[item for item in ir.source_refs
                         if item.startswith("TRACKMILE") or item.startswith("TRACK_")],
            resource_equipment=[item for item in ir.source_refs
                                if item.startswith("RFLOW") or item.startswith("EQ")],
            reward=[item for item in ir.source_refs if item.startswith("REWARD")],
            map_changes=[item for item in ir.source_refs if item.startswith("MAPMILE")],
            world_change=[item.text for item in fields
                          if item.field_name == "world_state_change" and item.text],
            hook=list((allocation.causality.get("next_pressure") if allocation else []) or []),
            causality=dict(allocation.causality) if allocation else {},
            constraints=sorted(set(ir.canon_fact_ids) | {revision_id} - {""}),
            source_refs=list(ir.source_refs),
            evidence_refs=sorted({item for item in ir.field_evidence
                                  for item in [*item.event_ids, *item.effect_ids,
                                               *item.transition_ids]})))
    return rows


def _title(ir: ChapterSemanticIR, allocation: ChapterAllocation | None) -> str:
    function = allocation.chapter_function if allocation else "setup"
    primary = allocation.primary_plot_node_id if allocation else ""
    return f"{function}·{primary}"[:120] if primary else (ir.goal or ir.chapter_uuid)[:120]


def project_chapter_ir(ir: ChapterSemanticIR,
                       findings: Sequence[PlanningFinding] = (),
                       allocation: ChapterAllocation | None = None
                       ) -> ChapterIRInspectorProjection:
    related = [item for item in findings if ir.chapter_uuid in item.related_ids
               or item.source_id == ir.chapter_uuid]
    return ChapterIRInspectorProjection(
        chapter_id=ir.chapter_uuid, arc_id=ir.arc_id,
        function=allocation.chapter_function if allocation else "",
        event_ids=[item.event_id for item in ir.event_frames],
        effect_ids=[item.effect_id for item in ir.effects],
        transition_ids=[item.transition_id for item in ir.state_transitions],
        evidence_fields=sorted(item.field_name for item in ir.field_evidence),
        not_applicable_fields=list(ir.not_applicable_fields),
        findings=[{"code": item.code, "severity": item.severity,
                   "message": item.message} for item in related])


def project_arc_compilation(candidate: ChapterCompilationCandidate, *,
                            status: str = "valid", resume_required: bool = False
                            ) -> ArcCompilationProjection:
    return ArcCompilationProjection(
        arc_id=candidate.arc_id, volume_id=candidate.volume_id, status=status,
        budget_min=candidate.decomposition.budget_range.minimum,
        budget_preferred=candidate.decomposition.budget_range.preferred,
        budget_max=candidate.decomposition.budget_range.maximum,
        planned_chapter_count=len(candidate.chapter_irs),
        chapter_ids=[item.chapter_uuid for item in candidate.chapter_irs],
        coverage=candidate.coverage,
        warning_codes=sorted({item.code for item in candidate.validation_findings
                              if item.severity == "WARNING"}),
        blocking_codes=sorted({item.code for item in candidate.validation_findings
                               if item.severity == "ERROR"}),
        resume_required=resume_required)


def project_compilation_progress(session: Any, *,
                                 candidates: Mapping[str, ChapterCompilationCandidate] | None = None,
                                 titles: Mapping[str, str] | None = None
                                 ) -> ChapterCompilationProgressProjection:
    candidates = dict(candidates or {})
    arcs: list[ArcCompilationProjection] = []
    chapters_planned = 0
    for task in sorted(getattr(session, "tasks", []), key=lambda item: item.sequence):
        candidate = candidates.get(task.batch_id)
        if candidate is None:
            arcs.append(ArcCompilationProjection(
                arc_id=task.scope.note, status=task.status,
                resume_required=task.status in ("retryable_failed", "human_review", "blocked")))
            continue
        chapters_planned += len(candidate.chapter_irs)
        arcs.append(project_arc_compilation(
            candidate, status=task.status,
            resume_required=task.status in ("retryable_failed", "human_review", "blocked")))
    completed = [task for task in getattr(session, "tasks", [])
                 if task.status in ("promoted", "skipped")]
    running = next((task for task in getattr(session, "tasks", [])
                    if task.status in ("running", "compiled", "validated")), None)
    current = candidates.get(running.batch_id) if running is not None else None
    return ChapterCompilationProgressProjection(
        session_id=getattr(session, "session_id", ""),
        status=getattr(session, "status", "pending"),
        scope_complete=bool(getattr(session, "scope_complete", False)),
        arcs_completed=len(completed), arcs_total=len(getattr(session, "tasks", [])),
        current_arc_id=(running.scope.note if running is not None else ""),
        current_chapter_id=(current.chapter_irs[-1].chapter_uuid
                            if current and current.chapter_irs else ""),
        current_chapter_title=((titles or {}).get(current.chapter_irs[-1].chapter_uuid, "")
                               if current and current.chapter_irs else ""),
        chapters_written=chapters_planned, chapters_planned=chapters_planned,
        blocked_batch_ids=[task.batch_id for task in getattr(session, "tasks", [])
                           if task.status == "blocked"],
        human_review_batch_ids=[task.batch_id for task in getattr(session, "tasks", [])
                                if task.status == "human_review"],
        retrying_batch_ids=[task.batch_id for task in getattr(session, "tasks", [])
                            if task.status == "retryable_failed"],
        arcs=arcs)


def project_chapter_tree(plan: StoryPlanningIR, *, revision_id: str = "",
                         titles: Mapping[str, str] | None = None) -> ChapterTreeProjection:
    titles = titles or {}
    volumes = []
    total = 0
    for volume in sorted(plan.volumes, key=lambda item: item.index):
        arcs = []
        for arc in sorted([item for item in plan.arcs if item.volume_id == volume.volume_id],
                          key=lambda item: item.index):
            chapters = []
            for order, chapter_id in enumerate(arc.chapter_refs, start=1):
                chapters.append(ChapterTreeChapter(
                    chapter_id=chapter_id, display_number=order, order_index=order,
                    title=titles.get(chapter_id, f"{arc.arc_id}#{order}"),
                    function=titles.get(f"{chapter_id}:function", "")))
                total += 1
            arcs.append(ChapterTreeArc(arc_id=arc.arc_id, index=arc.index, title=arc.title,
                                       detail_level=arc.detail_level, chapters=chapters))
        volumes.append(ChapterTreeVolume(volume_id=volume.volume_id, index=volume.index,
                                         title=volume.title, arcs=arcs))
    return ChapterTreeProjection(novel_id=plan.novel_id, planning_revision_id=revision_id,
                                 volumes=volumes, chapter_total=total)


def project_writer_context(candidate: ChapterCompilationCandidate, plan: StoryPlanningIR,
                           *, revision_id: str = "") -> ChapterWriterContextProjection:
    outlines = project_detailed_outline(candidate, plan, revision_id=revision_id)
    knowledge: dict[str, list[str]] = {}
    for allocation in candidate.chapter_allocations:
        for actor, truths in allocation.character_knowledge_granted.items():
            knowledge.setdefault(actor, [])
            knowledge[actor] = sorted(set(knowledge[actor]) | set(truths))
    forbidden = sorted({truth.truth_id for arc in plan.information_arcs for truth in arc.truths}
                       - {item for allocation in candidate.chapter_allocations
                          for item in allocation.reader_release})
    return ChapterWriterContextProjection(
        novel_id=plan.novel_id, planning_revision_id=revision_id, arc_id=candidate.arc_id,
        chapter_ids=[item.chapter_id for item in outlines], outlines=outlines,
        knowledge_boundaries=knowledge, forbidden_reveals=forbidden)


def project_arc_pacing(candidate: ChapterCompilationCandidate) -> ArcChapterPacingProjection:
    values: dict[str, list[float]] = {name: [] for name in PACING_DIMENSIONS}
    for allocation, ir in zip(candidate.chapter_allocations, candidate.chapter_irs):
        signals = {
            "tension": float(len(ir.state_transitions) + len(ir.effects)),
            "mystery": float(len(allocation.source_planning_ids) if any(
                item.startswith("FSP") for item in allocation.source_planning_ids) else 0),
            "exploration": float(len([item for item in allocation.plot_node_refs]) if any(
                item.startswith("MAPMILE") for item in ir.source_refs) else 0),
            "combat": float(len([event for event in ir.event_frames
                                 if event.action_type in ("fight", "confront", "negotiate")])),
            "relationship": float(len([item for item in ir.source_refs
                                       if item.startswith("RSTAGE") or item.startswith("RELARC")])),
            "reveal": float(len([event for event in ir.event_frames
                                 if event.action_type == "discover"])),
            "progression": float(len([item for item in ir.source_refs
                                      if item.startswith("TRACK")])),
            "reward": float(len([item for item in ir.source_refs
                                 if item.startswith("REWARD")])),
            "climax": float(len([effect for effect in ir.effects
                                 if effect.is_narrative_pivot])
                            + (1.0 if allocation.is_climax else 0.0)),
        }
        for name in PACING_DIMENSIONS:
            values[name].append(round(signals[name], 3))
    counts: dict[str, int] = {}
    for allocation in candidate.chapter_allocations:
        counts[allocation.chapter_function] = counts.get(allocation.chapter_function, 0) + 1
    return ArcChapterPacingProjection(arc_id=candidate.arc_id, values=values,
                                      function_counts=counts)


__all__ = [
    "PACING_DIMENSIONS",
    "ArcChapterPacingProjection",
    "ArcCompilationProjection",
    "ChapterCompilationProgressProjection",
    "ChapterIRInspectorProjection",
    "ChapterOutlineEntry",
    "ChapterTreeArc",
    "ChapterTreeChapter",
    "ChapterTreeProjection",
    "ChapterTreeVolume",
    "ChapterWriterContextProjection",
    "DetailedChapterOutlineProjection",
    "project_arc_compilation",
    "project_arc_pacing",
    "project_chapter_ir",
    "project_chapter_tree",
    "project_compilation_progress",
    "project_detailed_outline",
    "project_writer_context",
    "render_chapter_fields",
]
