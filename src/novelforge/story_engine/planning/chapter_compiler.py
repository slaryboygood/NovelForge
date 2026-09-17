"""M9：ArcPlan → Chapter Semantic IR（复用 M1 正式模型，不建第二套）。

流程：ArcPlan → semantic units → chapter decomposition → ChapterAllocation →
ChapterSemanticIR（M1 模型）→ coverage / knowledge / ordering / budget 校验 →
ChapterCompilationCandidate（proposal，不能直接写 official IR）。

structure is fact, prose is projection：M9 只产出结构化的 Chapter IR；
Detailed Outline 是它的 writer-visible projection（见 chapter_projection.py）。
"""

from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import Field

from novelforge.models import StrictModel
from novelforge.story_engine.chapter_ir.evidence import EvidenceValidator
from novelforge.story_engine.chapter_ir.function_policy import (
    FUNCTION_REQUIREMENTS,
    ChapterFunctionPolicy,
    FunctionFinding,
)
from novelforge.story_engine.chapter_ir.models import (
    ChapterEffect,
    ChapterEventFrame,
    ChapterSemanticIR,
    ChapterStateTransition,
    FieldEvidence,
)
from novelforge.story_engine.chapter_ir.state import StateMachine, TypedStateRegistry
from novelforge.story_engine.chapter_ir.validator import ChapterIRValidator
from novelforge.story_engine.chapter_ir.verifier import DeterministicSemanticVerifier

from .chapter_units import (
    ChapterDecompositionPlan,
    ChapterSemanticUnit,
    arc_budget_range,
    plan_chapter_decomposition,
)
from .findings import PlanningFinding, add_finding
from .models import ArcPlan, InformationTruth, PlotNode, StoryPlanningIR
from .outline_budget import ChapterBudgetEstimate, StructuralBudgetEstimator
from .plot_pressure import build_plot_pressure_inventory
from .spine_analysis import topological_order
from .versioning import planning_digest

CHAPTER_COMPILER_VERSION = "m9-1"
ChapterFunctionName = Literal["setup", "exploration", "investigation", "negotiation",
                              "conflict", "combat", "reveal", "relationship", "progression",
                              "aftermath", "transition", "climax", "resolution"]
# 这些情况必须停下来找作者（不是 compiler bug）
M9_HUMAN_REVIEW_CODES: tuple[str, ...] = (
    "ARC_GOAL_UNANCHORED", "ARC_ENDING_STATE_UNREACHABLE", "ARC_DECOMPOSITION_INVALID",
    "CHARACTER_ARC_CHOICE_UNPLACED", "FORESHADOW_ORDER_BROKEN", "INFORMATION_REVEAL_MISSING",
    "RESOURCE_UNSOURCED_CONSUMPTION", "EQUIPMENT_SEQUENCE_INFEASIBLE",
    "RELATIONSHIP_IRREVERSIBLE_REGRESSION",
    # 严重预算不匹配：不压缩、不注水，交回作者决定（略超只是 WARNING）
    "ARC_TOO_DENSE_FOR_CHAPTER_BUDGET", "ARC_TOO_THIN_FOR_CHAPTER_BUDGET",
)
OPTIONAL_DEFER_CODES: tuple[str, ...] = ("OPTIONAL_NODE_DROPPED_WITHOUT_REASON",)
TURN_KINDS: tuple[str, ...] = ("progression", "activation", "acquisition", "regression",
                               "loss", "resolution", "irreversible", "deactivation")
_TAG = re.compile(r"[^A-Z0-9]")
_MAP_STAGES: tuple[str, ...] = ("unknown", "known", "reachable", "surveyed", "controlled",
                                "secured")
_EQUIPMENT_STATES: tuple[str, ...] = ("unacquired", "acquired", "damaged", "repaired",
                                      "consumed", "lost")


def _tag(text: str, length: int = 18) -> str:
    value = _TAG.sub("", (text or "X").upper())
    return (value or "X")[:length]


def stable_chapter_id(arc_id: str, unit: ChapterSemanticUnit) -> str:
    """稳定 chapter identity：只由 arc + PlotNode anchor + 语义 role 决定。

    不用 order / slot_index / display number：在 Arc 前部插入新 unit 不会洗掉既有 ID。
    """

    key = "|".join([arc_id, unit.primary_plot_node_id, unit.unit_kind])
    return "CHIR_" + hashlib.sha256(key.encode("utf-8")).hexdigest()[:16].upper()


UNIT_KIND_PRIORITY: tuple[str, ...] = ("consequence", "choice", "aftermath", "escalation",
                                       "setup", "bridge", "execution")


def chapter_anchor_unit(units: list[ChapterSemanticUnit]) -> ChapterSemanticUnit:
    """chapter identity 的 anchor：本章**最终完成**的 execution unit，否则按 unit role。

    取最后一个 completion（而不是第一个）：在 Arc 前部插入新 unit 时，
    既有章节的 anchor 不会因为"前面多了一个 completion"而改变。
    """

    completing = [unit for unit in units if unit.completes_plot_node_ids]
    if completing:
        return completing[-1]

    def priority(unit: ChapterSemanticUnit) -> int:
        return (UNIT_KIND_PRIORITY.index(unit.unit_kind)
                if unit.unit_kind in UNIT_KIND_PRIORITY else len(UNIT_KIND_PRIORITY))

    best = min(units, key=priority)
    same_rank = [unit for unit in units if priority(unit) == priority(best)]
    return same_rank[-1]


class ChapterDecompositionPolicy(StrictModel):
    """章数 mismatch 的 review 容忍度（Core 中性默认；Genre Template / author config 可覆写）。

    结构 mismatch 只看 `ChapterBudgetEstimate` 的 min / max：within range = OK，
    超出 range = WARNING；超出容忍带（由本 policy 给出）才升级成 review-required。
    `preferred` 始终只是 hint，不是 quota，也不参与 severity 判定。
    """

    policy_id: str = Field(default="neutral", max_length=64)
    dense_review_tolerance: float = Field(default=0.5, ge=0, le=5)
    thin_review_tolerance: float = Field(default=0.5, ge=0, le=1)
    non_authoritative: bool = True


class ChapterCompilationProfile(StrictModel):
    """M9 编译参数（Core 中性默认；author / genre template 可覆写）。"""

    profile_id: str = Field(default="neutral", max_length=64)
    policy: ChapterDecompositionPolicy = Field(default_factory=ChapterDecompositionPolicy)
    require_arc_goal_anchor: bool = True
    non_authoritative: bool = True


class ChapterAllocation(StrictModel):
    """Chapter ↔ PlotNode 的 many-to-many projection + 本批编译归因。"""

    chapter_id: str = Field(min_length=5, max_length=128)
    arc_id: str = Field(default="", max_length=64)
    order_index: int = Field(default=1, ge=1)
    display_number: int = Field(default=1, ge=1)
    primary_plot_node_id: str = Field(default="", max_length=64)
    plot_node_refs: list[str] = Field(default_factory=list)
    completed_plot_node_ids: list[str] = Field(default_factory=list)
    setup_node_refs: list[str] = Field(default_factory=list)
    foreshadow_node_refs: list[str] = Field(default_factory=list)
    consequence_node_refs: list[str] = Field(default_factory=list)
    pressure_refs: list[str] = Field(default_factory=list)
    unit_ids: list[str] = Field(default_factory=list)
    chapter_function: ChapterFunctionName = "setup"
    budget_source: str = Field(default="", max_length=120)
    allocation_reason: str = Field(default="", max_length=300)
    source_planning_ids: list[str] = Field(default_factory=list)
    is_bridge: bool = False
    is_climax: bool = False
    planned_start_state: dict[str, str] = Field(default_factory=dict)
    planned_end_state: dict[str, str] = Field(default_factory=dict)
    causality: dict[str, list[str]] = Field(default_factory=dict)
    reader_release: list[str] = Field(default_factory=list)
    character_knowledge_granted: dict[str, list[str]] = Field(default_factory=dict)
    not_applicable_fields: list[str] = Field(default_factory=list)
    non_authoritative: bool = True


class ArcExecutionCoverageReport(StrictModel):
    """Arc execution contract 是否真的落到章节（§13-§15, §31-§39）。"""

    arc_id: str = Field(default="", max_length=64)
    chapter_count: int = 0
    goal_anchored: bool = False
    goal_chapter_ids: list[str] = Field(default_factory=list)
    plot_nodes_total: int = 0
    plot_nodes_anchored: int = 0
    plot_nodes_unanchored: list[str] = Field(default_factory=list)
    plot_nodes_duplicated: list[str] = Field(default_factory=list)
    must_happen_unanchored: list[str] = Field(default_factory=list)
    optional_deferred: list[str] = Field(default_factory=list)
    decision_anchored: list[str] = Field(default_factory=list)
    turn_chapter_ids: list[str] = Field(default_factory=list)
    payoff_chapter_ids: list[str] = Field(default_factory=list)
    information_anchored: list[str] = Field(default_factory=list)
    information_missing: list[str] = Field(default_factory=list)
    foreshadow_anchored: list[str] = Field(default_factory=list)
    foreshadow_missing: list[str] = Field(default_factory=list)
    relationship_anchored: list[str] = Field(default_factory=list)
    faction_anchored: list[str] = Field(default_factory=list)
    progression_anchored: list[str] = Field(default_factory=list)
    resource_anchored: list[str] = Field(default_factory=list)
    equipment_anchored: list[str] = Field(default_factory=list)
    map_anchored: list[str] = Field(default_factory=list)
    reward_anchored: list[str] = Field(default_factory=list)
    autonomous_anchored: list[str] = Field(default_factory=list)
    pressure_anchored: list[str] = Field(default_factory=list)
    knowledge_gate_pass: bool = True
    budget_range: ChapterBudgetEstimate = Field(default_factory=ChapterBudgetEstimate)
    budget_status: str = Field(default="in_range", max_length=32)
    function_counts: dict[str, int] = Field(default_factory=dict)
    status: Literal["valid", "needs_attention", "blocked"] = "valid"
    read_only: bool = True


class ChapterCompilationCandidate(StrictModel):
    candidate_id: str = Field(default="", max_length=64)
    source_revision_id: str = Field(default="", max_length=64)
    source_digest: str = Field(default="", max_length=64)
    arc_id: str = Field(default="", max_length=64)
    volume_id: str = Field(default="", max_length=64)
    scope: Any = Field(default=None)
    compiler_version: str = Field(default=CHAPTER_COMPILER_VERSION, max_length=32)
    decomposition: ChapterDecompositionPlan = Field(default_factory=ChapterDecompositionPlan)
    chapter_allocations: list[ChapterAllocation] = Field(default_factory=list)
    chapter_irs: list[ChapterSemanticIR] = Field(default_factory=list)
    deferred_optional_node_ids: list[str] = Field(default_factory=list)
    ignored_pressure_ids: list[str] = Field(default_factory=list)
    coverage: ArcExecutionCoverageReport = Field(default_factory=ArcExecutionCoverageReport)
    validation_findings: list[PlanningFinding] = Field(default_factory=list)
    route_provenance: dict[str, Any] = Field(default_factory=dict)
    status: str = Field(default="valid", max_length=24)
    non_authoritative: bool = True

    def blocking(self) -> bool:
        return any(item.severity == "ERROR" for item in self.validation_findings)

    def chapter(self, chapter_id: str) -> ChapterSemanticIR | None:
        return next((item for item in self.chapter_irs if item.chapter_uuid == chapter_id), None)


class ChapterCompilationRecord(StrictModel):
    """promotion 记录：candidate → 新 revision + official chapter artifact refs。"""

    source_revision: str = Field(default="", max_length=64)
    source_digest: str = Field(default="", max_length=64)
    compiler_version: str = Field(default=CHAPTER_COMPILER_VERSION, max_length=32)
    arc_id: str = Field(default="", max_length=64)
    candidate_id: str = Field(default="", max_length=64)
    promoted_revision_id: str = Field(default="", max_length=64)
    chapter_ids: list[str] = Field(default_factory=list)
    chapter_ir_digest: str = Field(default="", max_length=64)
    validation_digest: str = Field(default="", max_length=64)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    non_authoritative: bool = True


def build_planning_state_registry(plan: StoryPlanningIR) -> TypedStateRegistry:
    """从 Planning 自身声明建立 typed state machines（Core 无题材 / 无实例硬编码）。"""

    registry = TypedStateRegistry()

    def dedupe(values: list[str]) -> tuple[str, ...]:
        rows: list[str] = []
        for value in values:
            if value and value not in rows:
                rows.append(value)
        return tuple(rows)

    for arc in plan.relationship_arcs:
        stages = [stage.state or stage.label or stage.stage_id for stage in arc.stages]
        irreversible = [stage.state or stage.label or stage.stage_id for stage in arc.stages
                        if stage.irreversible]
        registry.register(StateMachine(f"relationship_{arc.arc_id}",
                                       dedupe([arc.start_state or "start"] + stages),
                                       irreversible_states=tuple(irreversible)))
    for track in plan.progression_tracks:
        stages = [milestone.label or milestone.milestone_id for milestone in track.milestones]
        registry.register(StateMachine(f"progression_{track.track_id}",
                                       dedupe([track.start_state or "start"] + stages)))
    for expansion in plan.map_expansions:
        registry.register(StateMachine(f"map_{expansion.expansion_id}", _MAP_STAGES))
    for equipment in plan.equipment_plans:
        registry.register(StateMachine(f"equipment_{equipment.equipment_id}", _EQUIPMENT_STATES))
    return registry


class _KnowledgeCursor:
    """author / reader / character / faction knowledge 的 chapter 级推演（只读、不落盘）。"""

    def __init__(self, plan: StoryPlanningIR) -> None:
        self.plan = plan
        self.truths: dict[str, InformationTruth] = {
            truth.truth_id: truth for arc in plan.information_arcs for truth in arc.truths}
        self.moves: dict[str, list[Any]] = {}
        for arc in plan.information_arcs:
            for move in arc.moves:
                self.moves.setdefault(move.node_id, []).append(move)
        self.knows: dict[str, set[str]] = {}
        self.reader_knows: set[str] = set()
        self.revealed_at: dict[str, int] = {}
        for truth in self.truths.values():
            for actor in list(truth.character_knows) + list(truth.faction_knows):
                self.knows.setdefault(actor, set()).add(truth.truth_id)
            if truth.protagonist_knows and plan.characters:
                owner = plan.characters[0].entity_ref or plan.characters[0].character_id
                self.knows.setdefault(owner, set()).add(truth.truth_id)

    def apply(self, node_id: str, position: int) -> dict[str, list[str]]:
        """把某个节点上的信息移动推进到 cursor，返回本章 granted（actor → truth）。"""

        granted: dict[str, list[str]] = {}
        for move in self.moves.get(node_id, []):
            holders = list(move.holder_ids) or sorted(self._default_holders(move.truth_id))
            if move.move_type in ("plant", "hint", "reinforce"):
                for actor in holders:
                    self.knows.setdefault(actor, set()).add(move.truth_id)
            elif move.move_type in ("reveal", "payoff", "reinterpretation"):
                self.reader_knows.add(move.truth_id)
                self.revealed_at.setdefault(move.truth_id, position)
                for actor in holders:
                    self.knows.setdefault(actor, set()).add(move.truth_id)
                    granted.setdefault(actor, []).append(move.truth_id)
        return granted

    def _default_holders(self, truth_id: str) -> set[str]:
        truth = self.truths.get(truth_id)
        if truth is None:
            return set()
        rows = set(truth.character_knows) | set(truth.faction_knows)
        if truth.protagonist_knows and self.plan.characters:
            rows.add(self.plan.characters[0].entity_ref or self.plan.characters[0].character_id)
        return rows

    def knows_truth(self, actor_id: str, truth_id: str) -> bool:
        return truth_id in self.knows.get(actor_id, set())


class ChapterCompiler:
    """确定性 Arc → Chapter 编译器（同输入必然同 chapter ids / 同 IR digest）。"""

    def __init__(self, *, estimator: StructuralBudgetEstimator | None = None,
                 profile: ChapterCompilationProfile | None = None) -> None:
        self.estimator = estimator or StructuralBudgetEstimator()
        self.profile = profile or ChapterCompilationProfile()

    # ---------------------------------------------------------------- 入口
    def compile(self, plan: StoryPlanningIR, *, revision_id: str = "",
                scope: Any | None = None, arc_id: str = "",
                budget: ChapterBudgetEstimate | None = None,
                deferred_optional_node_ids: list[str] | None = None,
                ignored_pressure_ids: list[str] | None = None,
                route_provenance: dict[str, Any] | None = None
                ) -> ChapterCompilationCandidate:
        arc = self._resolve_arc(plan, arc_id=arc_id, scope=scope)
        inventory = build_plot_pressure_inventory(plan, revision_id=revision_id)
        decomposition = plan_chapter_decomposition(
            plan, arc, revision_id=revision_id, estimator=self.estimator, inventory=inventory,
            budget=budget)
        units = {unit.unit_id: unit for unit in decomposition.chapter_units}
        nodes = {node.node_id: node for node in plan.plot_nodes}
        registry = build_planning_state_registry(plan)
        knowledge = _KnowledgeCursor(plan)
        arc_chapters = self._arc_positions(plan)
        base_position = arc_chapters.get(arc.arc_id, (0, 0))[0]
        cursor: dict[str, str] = {}
        allocations: list[ChapterAllocation] = []
        chapter_irs: list[ChapterSemanticIR] = []
        chapter_count = len(decomposition.chapter_groups)
        for index, group in enumerate(decomposition.chapter_groups, start=1):
            group_units = [units[unit_id] for unit_id in group]
            allocation, ir = self._build_chapter(
                plan, arc, group_units, index=index,
                chapter_count=chapter_count, display_number=base_position + index,
                nodes=nodes, registry=registry, cursor=cursor, knowledge=knowledge)
            allocations.append(allocation)
            chapter_irs.append(ir)
        deferred = list(deferred_optional_node_ids or [])
        ignored = list(ignored_pressure_ids or [])
        candidate = ChapterCompilationCandidate(
            candidate_id=self._candidate_id(plan, arc, revision_id, decomposition, scope),
            source_revision_id=revision_id, source_digest=planning_digest(plan),
            arc_id=arc.arc_id, volume_id=arc.volume_id,
            scope=scope, decomposition=decomposition,
            chapter_allocations=allocations, chapter_irs=chapter_irs,
            deferred_optional_node_ids=deferred, ignored_pressure_ids=ignored,
            route_provenance=dict(route_provenance or {}))
        findings = self.validate(plan, candidate, inventory=inventory)
        coverage = self._coverage(plan, candidate, inventory=inventory, findings=findings)
        candidate = candidate.model_copy(update={
            "validation_findings": findings, "coverage": coverage,
            "status": coverage.status})
        return candidate

    def _resolve_arc(self, plan: StoryPlanningIR, *, arc_id: str, scope: Any | None) -> ArcPlan:
        wanted = arc_id or (getattr(scope, "note", "") if scope is not None else "")
        if wanted:
            arc = next((item for item in plan.arcs if item.arc_id == wanted), None)
            if arc is None:
                raise ValueError(f"ARC_NOT_FOUND: {wanted}")
            return arc
        if len(plan.arcs) == 1:
            return plan.arcs[0]
        raise ValueError("ARC_ID_REQUIRED: plan 有多个 Arc，必须显式指定 arc_id")

    def _arc_positions(self, plan: StoryPlanningIR) -> dict[str, tuple[int, int]]:
        """arc → (全局 chapter 起始位置, arc 内的序位偏移)。"""

        volume_index = {volume.volume_id: volume.index for volume in plan.volumes}
        rows = sorted(plan.arcs, key=lambda item: (volume_index.get(item.volume_id, 0), item.index))
        positions: dict[str, tuple[int, int]] = {}
        running = 0
        for arc in rows:
            count = int(arc.chapter_budget or 0)
            count = max(count, len(arc.plot_nodes))
            positions[arc.arc_id] = (running, 0)
            running += count
        return positions

    def _candidate_id(self, plan: StoryPlanningIR, arc: ArcPlan, revision_id: str,
                      decomposition: ChapterDecompositionPlan, scope: Any | None) -> str:
        seed = "|".join([revision_id, arc.arc_id, planning_digest(plan),
                         str(decomposition.proposed_chapter_count),
                         str(sorted(getattr(scope, "node_ids", []) or []))])
        digest = hashlib.sha256(seed.encode("utf-8")).hexdigest()[:12].upper()
        return f"CAND_CHAPTER_{_tag(arc.arc_id, 12)}_{digest}"

    # ---------------------------------------------------------------- 单章
    def _build_chapter(self, plan: StoryPlanningIR, arc: ArcPlan,
                       units: list[ChapterSemanticUnit], *, index: int, chapter_count: int,
                       display_number: int,
                       nodes: dict[str, PlotNode], registry: TypedStateRegistry,
                       cursor: dict[str, str], knowledge: _KnowledgeCursor
                       ) -> tuple[ChapterAllocation, ChapterSemanticIR]:
        tag = _tag(arc.arc_id)
        move_by_id = {move.move_id: move for arc_row in plan.information_arcs
                      for move in arc_row.moves}
        chapter_id = stable_chapter_id(arc.arc_id, chapter_anchor_unit(units))
        start_state = dict(cursor)
        events: list[ChapterEventFrame] = []
        effects: list[ChapterEffect] = []
        transitions: list[ChapterStateTransition] = []
        granted: dict[str, list[str]] = {}
        reader_release: list[str] = []
        not_applicable: list[str] = []
        for unit_index, unit in enumerate(units, start=1):
            node = nodes.get(unit.primary_plot_node_id)
            if node is None:
                continue
            event_id = f"CE_{tag}_{index:02d}{unit_index:02d}"
            focal = self._focal_owner(plan, node)
            decisions = unit.decision_refs if unit.unit_kind == "choice" else []
            actors = sorted({focal} | set(node.participants)) if focal else list(node.participants)
            info_events: list[ChapterEventFrame] = []
            for offset, move_id in enumerate(sorted(unit.information_refs), start=1):
                move = move_by_id.get(move_id)
                if move is None or move.node_id != node.node_id:
                    continue
                holders = sorted(move.holder_ids) or ([focal] if focal else [])
                info_events.append(ChapterEventFrame(
                    event_id=f"{event_id}{offset:02d}",
                    actor_ids=holders,
                    mentioned_entity_ids=sorted(set(node.participants) - set(holders)),
                    action_type=("discover" if move.move_type in ("reveal", "payoff",
                                                                 "reinterpretation")
                                 else "observe"),
                    action_text=f"{move.move_type}：{node.purpose or node.node_id}"[:300],
                    temporal_order=unit_index, agency="reactive",
                    intent=node.purpose[:160], fact_refs=[move_id],
                    location_ids=[node.location_id] if node.location_id else [],
                    provenance="planner"))
            events.extend(info_events)
            anchor_event_id = info_events[0].event_id if info_events else event_id
            main_event = ChapterEventFrame(
                event_id=event_id, actor_ids=actors,
                mentioned_entity_ids=sorted(set(node.participants) - set(actors)
                                            - ({focal} if focal else set())),
                action_type=self._action_type(unit, node),
                decision_action=("decide" if decisions else ""),
                changes_followup_path=bool(decisions),
                has_alternative=bool(decisions),
                action_text=self._action_text(unit, node),
                location_ids=[node.location_id] if node.location_id else [],
                temporal_order=unit_index, agency="reactive",
                intent=node.purpose[:160], fact_refs=[],
                provenance="planner")
            if not info_events or decisions:
                events.append(main_event)
            effect_id = f"EF_{tag}_{index:02d}{unit_index:02d}"
            polarity, effect_type = self._polarity(unit, node)
            effects.append(ChapterEffect(
                effect_id=effect_id, effect_type=effect_type, target_type="situation",
                target_id=node.node_id, before_state="", after_state=node.state_change[:120],
                polarity=polarity, caused_by_event_ids=[anchor_event_id],
                knowledge_delta=list(unit.information_refs),
                resource_delta=self._resource_delta(plan, unit),
                reversible=not bool(unit.relationship_refs or unit.decision_refs),
                is_narrative_pivot=bool(unit.unit_kind == "choice" and node.major_choice),
                confidence=0.6))
            for transition in self._transitions(plan, arc, unit, node, anchor_event_id,
                                                registry, cursor, display_number):
                transitions.append(transition)
            granted = self._merge_granted(granted, knowledge.apply(node.node_id,
                                                                    display_number))
            for truth_id, position in knowledge.revealed_at.items():
                if position == display_number and truth_id not in reader_release:
                    reader_release.append(truth_id)
        function = self._pick_function(plan, arc, units, index, chapter_count, events,
                                       effects, transitions)
        allocation = ChapterAllocation(
            chapter_id=chapter_id, arc_id=arc.arc_id, order_index=index,
            display_number=display_number,
            primary_plot_node_id=units[0].primary_plot_node_id,
            plot_node_refs=sorted({item for unit in units for item in unit.plot_node_refs}),
            completed_plot_node_ids=sorted({item for unit in units
                                            for item in unit.completes_plot_node_ids}),
            setup_node_refs=sorted({item for unit in units for item in unit.setup_node_refs}),
            foreshadow_node_refs=sorted({item for unit in units
                                         for item in unit.foreshadow_node_refs}),
            consequence_node_refs=sorted({item for unit in units
                                          for item in unit.consequence_node_refs}),
            pressure_refs=sorted({item for unit in units for item in unit.pressure_refs}),
            unit_ids=[unit.unit_id for unit in units], chapter_function=function,
            budget_source=f"{arc.arc_id}:budget_range",
            allocation_reason="; ".join(f"{unit.unit_id}:{unit.unit_kind}" for unit in units)[:300],
            source_planning_ids=sorted({item for unit in units for item in unit.source_ids}),
            is_bridge=all(unit.is_bridge for unit in units),
            is_climax=bool(function in ("climax", "resolution")),
            planned_start_state=start_state, planned_end_state=dict(cursor),
            causality=self._causality(plan, units),
            reader_release=sorted(reader_release), character_knowledge_granted=granted,
            not_applicable_fields=not_applicable)
        ir = self._chapter_ir(plan, arc, allocation, events, effects, transitions,
                             function, not_applicable)
        return allocation, ir

    def _merge_granted(self, left: dict[str, list[str]],
                       right: dict[str, list[str]]) -> dict[str, list[str]]:
        rows = {key: list(value) for key, value in left.items()}
        for actor, truths in right.items():
            rows.setdefault(actor, [])
            rows[actor] = sorted(set(rows[actor]) | set(truths))
        return rows

    def _focal_owner(self, plan: StoryPlanningIR, node: PlotNode) -> str:
        if node.decision_owner_ref:
            return node.decision_owner_ref
        for character in plan.characters:
            if character.entity_ref:
                return character.entity_ref
        return plan.characters[0].character_id if plan.characters else ""

    def _action_type(self, unit: ChapterSemanticUnit, node: PlotNode) -> str:
        if unit.unit_kind == "choice" or node.major_choice:
            return "decision"
        if unit.is_bridge or unit.unit_kind == "bridge":
            return "depart"
        if unit.conflict_refs and node.conflict:
            conflict = node.conflict
            if "谈" in conflict or "条件" in conflict:
                return "negotiate"
            if any(word in conflict for word in ("交火", "伏击", "打", "突")):
                return "fight"
            return "confront"
        if unit.information_refs:
            return "discover"
        if unit.resource_refs or unit.equipment_refs:
            return "acquire"
        if unit.map_refs:
            return "explore"
        return "act"

    def _action_text(self, unit: ChapterSemanticUnit, node: PlotNode) -> str:
        head = node.purpose or node.conflict or node.node_id
        if unit.unit_kind == "setup":
            return f"铺垫：{head}"[:300]
        if unit.unit_kind == "escalation":
            return f"升级：{node.conflict or head}"[:300]
        if unit.unit_kind == "choice":
            return f"抉择：{node.major_choice or head}"[:300]
        if unit.unit_kind == "consequence":
            return f"结果：{node.payoff or node.cost or head}"[:300]
        if unit.is_bridge:
            return f"移动：{unit.bridge_reason or head}"[:300]
        return head[:300]

    def _polarity(self, unit: ChapterSemanticUnit, node: PlotNode) -> tuple[str, str]:
        if node.payoff and node.cost:
            return "mixed", "trade_off"
        if node.payoff or unit.reward_refs:
            return "positive", "goal_resolution"
        if node.cost or unit.resource_refs and unit.unit_kind != "setup":
            return "negative", "cost"
        return "neutral", "state_change"

    def _resource_delta(self, plan: StoryPlanningIR, unit: ChapterSemanticUnit
                        ) -> dict[str, float]:
        rows: dict[str, float] = {}
        for flow in plan.resource_flows:
            if not unit.resource_refs or flow.identity() not in set(unit.resource_refs):
                continue
            key = flow.resource_id or flow.planned_resource_id
            sign = -1.0 if flow.flow_type in ("consume", "lost") else 1.0
            rows[key] = rows.get(key, 0.0) + sign * float(flow.amount or 0)
        return rows

    def _transitions(self, plan: StoryPlanningIR, arc: ArcPlan, unit: ChapterSemanticUnit,
                     node: PlotNode, event_id: str, registry: TypedStateRegistry,
                     cursor: dict[str, str], display_number: int
                     ) -> list[ChapterStateTransition]:
        rows: list[ChapterStateTransition] = []
        primary_used = False

        def add(state_key: str, to_state: str, kind: str, detail_id: str) -> None:
            nonlocal primary_used
            machine = registry.machine(state_key)
            if machine is None or not to_state:
                return
            from_state = cursor.get(state_key) or (machine.states[0] if machine.states else "")
            if machine.index(to_state) < machine.index(from_state):
                return
            cursor[state_key] = to_state
            role = "primary" if not primary_used else "secondary"
            primary_used = True
            rows.append(ChapterStateTransition(
                transition_id=f"ST_{_tag(arc.arc_id)}_{display_number:03d}{len(rows) + 1}",
                state_key=state_key, subject_id=detail_id, from_state=from_state,
                to_state=to_state, caused_by_event_ids=[event_id],
                transition_kind=kind, effective_at=display_number,
                assertion_mode="transition", narrative_role=role))

        for arc_row in plan.relationship_arcs:
            for stage in arc_row.stages:
                if stage.trigger_node_id != node.node_id:
                    continue
                if stage.stage_id and stage.stage_id not in unit.relationship_refs \
                        and f"{arc_row.arc_id}_stage" not in unit.relationship_refs:
                    continue
                add(f"relationship_{arc_row.arc_id}", stage.state or stage.label or stage.stage_id,
                    "irreversible" if stage.irreversible else "progression", arc_row.arc_id)
        for track in plan.progression_tracks:
            for milestone in track.milestones:
                if milestone.node_id != node.node_id:
                    continue
                add(f"progression_{track.track_id}",
                    milestone.label or milestone.milestone_id, "progression",
                    milestone.milestone_id)
        for expansion in plan.map_expansions:
            for milestone in expansion.milestones:
                if milestone.trigger_node_id != node.node_id:
                    continue
                add(f"map_{expansion.expansion_id}", milestone.to_stage, "activation",
                    milestone.milestone_id)
        for equipment in plan.equipment_plans:
            for step in equipment.lifecycle:
                if step.node_id != node.node_id:
                    continue
                kind = {"acquired": "acquisition", "damaged": "regression",
                        "repaired": "resolution", "consumed": "loss", "lost": "loss"}.get(
                    step.state, "progression")
                add(f"equipment_{equipment.equipment_id}", step.state, kind,
                    equipment.equipment_id)
        return rows

    def _causality(self, plan: StoryPlanningIR, units: list[ChapterSemanticUnit]
                   ) -> dict[str, list[str]]:
        node_ids = sorted({item for unit in units for item in unit.plot_node_refs})
        edges = plan.spine.edges if plan.spine else []
        caused_by = sorted({edge.from_node_id for edge in edges
                            if edge.to_node_id in node_ids})
        enables = sorted({edge.to_node_id for edge in edges if edge.from_node_id in node_ids})
        return {"why_now": node_ids, "caused_by": caused_by, "enables": enables,
                "blocks": [], "pays_off": sorted({item for unit in units
                                                  for item in unit.foreshadow_refs}),
                "next_pressure": sorted({item for unit in units for item in unit.pressure_refs})}

    def _pick_function(self, plan: StoryPlanningIR, arc: ArcPlan,
                       units: list[ChapterSemanticUnit], index: int, chapter_count: int,
                       events: list[ChapterEventFrame], effects: list[ChapterEffect],
                       transitions: list[ChapterStateTransition]) -> ChapterFunctionName:
        action_types = {self._action_type(unit, PlotNode(node_id="NODE_X", purpose=""))
                        for unit in units}
        facts = {
            "has_decision": any(event.decision_action for event in events),
            "has_positive": any(effect.polarity in ("positive", "mixed") for effect in effects),
            "has_negative": any(effect.polarity in ("negative", "mixed") for effect in effects),
            "has_info": any(unit.information_refs for unit in units),
            "has_relationship": any(unit.relationship_refs for unit in units),
            "has_faction": any(unit.faction_refs for unit in units),
            "has_progression": any(unit.progression_refs for unit in units),
            "has_map": any(unit.map_refs for unit in units),
            "has_combat": "fight" in action_types,
            "has_transition": bool(transitions),
        }
        is_bridge = all(unit.is_bridge for unit in units)
        is_last_chapter = index == chapter_count
        last_arc = plan.arcs and plan.arcs[-1].arc_id == arc.arc_id
        if is_bridge:
            return "transition"
        if is_last_chapter and last_arc and facts["has_positive"] and facts["has_transition"]:
            return "resolution"
        if is_last_chapter and facts["has_positive"] and facts["has_decision"] \
                and facts["has_negative"]:
            return "climax"
        candidates: list[tuple[ChapterFunctionName, bool]] = [
            ("progression", facts["has_progression"] and facts["has_positive"]
             and facts["has_negative"]),
            ("reveal", facts["has_info"] and facts["has_positive"]),
            ("relationship", facts["has_relationship"]),
            ("combat", facts["has_combat"] and facts["has_positive"]
             and facts["has_negative"]),
            ("conflict", facts["has_decision"] and facts["has_positive"]
             and facts["has_negative"]),
            ("investigation", facts["has_info"] and facts["has_positive"]),
            ("exploration", facts["has_map"]),
            ("aftermath", facts["has_negative"]),
            ("setup", True),
        ]
        for function, allowed in candidates:
            if not allowed:
                continue
            requirements = FUNCTION_REQUIREMENTS[function]
            if requirements["decision"] == "required" and not facts["has_decision"]:
                continue
            if requirements["payoff"] == "required" and not facts["has_positive"]:
                continue
            if requirements["cost"] == "required" and not facts["has_negative"]:
                continue
            if requirements["loss"] == "required" and not facts["has_negative"]:
                continue
            if requirements["information_release"] == "required" and not facts["has_info"]:
                continue
            if requirements["world_state_change"] == "required" and not facts["has_transition"]:
                continue
            return function
        return "setup"

    def _chapter_ir(self, plan: StoryPlanningIR, arc: ArcPlan, allocation: ChapterAllocation,
                    events: list[ChapterEventFrame], effects: list[ChapterEffect],
                    transitions: list[ChapterStateTransition], function: str,
                    not_applicable: list[str]) -> ChapterSemanticIR:
        requirements = FUNCTION_REQUIREMENTS[function]
        evidence: list[FieldEvidence] = []
        na_fields: list[str] = []
        positive = next((effect for effect in effects
                         if effect.polarity in ("positive", "mixed")), None)
        negative = next((effect for effect in effects
                         if effect.polarity in ("negative", "mixed")), None)
        decision_event = next((event for event in events if event.decision_action), None)
        transition_ids = [item.transition_id for item in transitions]

        def bind(field_name: str, *, event_ids: list[str] | None = None,
                 effect_ids: list[str] | None = None, transition_ids_: list[str] | None = None,
                 required: bool) -> None:
            has = bool(event_ids or effect_ids or transition_ids_)
            if not has:
                if not required:
                    na_fields.append(field_name)
                return
            evidence.append(FieldEvidence(
                field_name=field_name, event_ids=list(event_ids or []),
                effect_ids=list(effect_ids or []), transition_ids=list(transition_ids_ or []),
                evidence_type="derived", confidence=0.6))

        pivot_effect = next((effect for effect in effects if effect.effect_type != "cost"), None)
        turn_required = requirements["turn"] in ("major_turn", "micro_turn")
        turn_transition = next((item for item in transitions
                                if item.transition_kind in TURN_KINDS), None)
        if turn_required and turn_transition is None and pivot_effect is not None \
                and pivot_effect.effect_type not in ("cost", "loss"):
            pivot_effect = pivot_effect.model_copy(update={"is_narrative_pivot": True})
            effects = [pivot_effect if item.effect_id == pivot_effect.effect_id else item
                       for item in effects]
        elif turn_required and turn_transition is None:
            # 功能要求 micro/major turn：用本章真实的 state_change 造一条 neutral pivot
            # （不是凭空的重大转折；只声明"这里发生了状态变化"）
            pivot_effect = ChapterEffect(
                effect_id=f"EF_TURN_{allocation.chapter_id[-8:]}",
                effect_type="state_change", target_type="situation",
                target_id=allocation.primary_plot_node_id, after_state="状态变化",
                polarity="neutral", is_narrative_pivot=True, confidence=0.5)
            effects = [*effects, pivot_effect]
        bind("decision",
             event_ids=([decision_event.event_id] if decision_event else []),
             required=requirements["decision"] == "required")
        bind("cost", effect_ids=([negative.effect_id] if negative else []),
             required=requirements["cost"] == "required")
        bind("loss", effect_ids=([negative.effect_id] if negative else []),
             required=requirements["loss"] == "required")
        bind("turn",
             transition_ids_=([turn_transition.transition_id] if turn_transition else []),
             effect_ids=([pivot_effect.effect_id] if turn_transition is None
                         and pivot_effect is not None else []),
             required=turn_required)
        bind("payoff", effect_ids=([positive.effect_id] if positive else []),
             required=requirements["payoff"] == "required")
        bind("world_state_change", transition_ids_=transition_ids,
             required=requirements["world_state_change"] in ("required", "optional"))
        info_events = [event.event_id for event in events if event.fact_refs]
        bind("information_release", event_ids=info_events,
             required=requirements["information_release"] == "required")
        return ChapterSemanticIR(
            chapter_uuid=allocation.chapter_id, novel_id=plan.novel_id,
            volume_id=arc.volume_id, arc_id=arc.arc_id,
            temporal_position=allocation.display_number,
            location_ids=self._chapter_locations(allocation, events),
            participant_ids=sorted({actor for event in events for actor in event.actor_ids}),
            event_frames=events, effects=effects, state_transitions=transitions,
            field_evidence=evidence, canon_fact_ids=[],
            source_refs=sorted(set(allocation.source_planning_ids)
                               | set(allocation.plot_node_refs) | {arc.arc_id}),
            provenance="planner",
            not_applicable_fields=sorted(set(not_applicable) | set(na_fields)),
            focal_decision_owner_id=(decision_event.actor_ids[0] if decision_event
                                     and decision_event.actor_ids else ""),
            goal=self._goal(allocation, function))

    def _chapter_locations(self, allocation: ChapterAllocation,
                           events: list[ChapterEventFrame]) -> list[str]:
        rows = sorted({item for event in events for item in event.location_ids})
        return rows or []

    def _goal(self, allocation: ChapterAllocation, function: str) -> str:
        return (f"{function}：{allocation.primary_plot_node_id} "
                f"({len(allocation.completed_plot_node_ids)} completion)")[:300]

    # ---------------------------------------------------------------- validate
    def validate(self, plan: StoryPlanningIR, candidate: ChapterCompilationCandidate,
                 *, inventory: Any | None = None) -> list[PlanningFinding]:
        findings: list[PlanningFinding] = []
        inventory = inventory or build_plot_pressure_inventory(plan)
        self._check_decomposition(plan, candidate, findings)
        self._check_arc_contract(plan, candidate, findings)
        self._check_chapter_ir(plan, candidate, findings)
        self._check_knowledge(plan, candidate, findings)
        self._check_ordering_and_continuity(plan, candidate, findings, inventory)
        self._check_distribution(plan, candidate, findings)
        return findings

    def _check_decomposition(self, plan: StoryPlanningIR, candidate: ChapterCompilationCandidate,
                             findings: list[PlanningFinding]) -> None:
        decomposition = candidate.decomposition
        budget = decomposition.budget_range
        count = decomposition.proposed_chapter_count
        policy = self.profile.policy
        if not candidate.chapter_allocations or not candidate.chapter_irs:
            add_finding(findings, "ARC_DECOMPOSITION_INVALID", "ERROR", "chapter",
                        candidate.arc_id, "Arc 没有被分解出任何 chapter", related=(candidate.arc_id,))
            return
        minimum = max(1, budget.minimum)
        maximum = max(minimum, budget.maximum)
        if count > maximum:
            # 只在超出 max 的容忍带时才升级成 review（容忍度来自 policy，不是 Core 魔数）
            severity = "ERROR" if count > maximum * (1 + policy.dense_review_tolerance) \
                else "WARNING"
            add_finding(findings, "ARC_TOO_DENSE_FOR_CHAPTER_BUDGET", severity, "chapter",
                        candidate.arc_id,
                        "语义需要的章节数超出 budget max（不压缩成 filler / 不删剧情）",
                        related=(candidate.arc_id,), chapters=count,
                        budget_max=maximum, policy_id=policy.policy_id,
                        dense_review_tolerance=policy.dense_review_tolerance)
        elif count < minimum:
            severity = "ERROR" if count < minimum * (1 - policy.thin_review_tolerance) \
                else "WARNING"
            add_finding(findings, "ARC_TOO_THIN_FOR_CHAPTER_BUDGET", severity, "chapter",
                        candidate.arc_id, "语义只需要更少的章节（不注水凑 budget）",
                        related=(candidate.arc_id,), chapters=count, budget_min=minimum,
                        policy_id=policy.policy_id,
                        thin_review_tolerance=policy.thin_review_tolerance)
        elif count != budget.preferred:
            add_finding(findings, "CHAPTER_COUNT_DIFFERS_FROM_PREFERRED_HINT", "INFO", "chapter",
                        candidate.arc_id,
                        "章数与 budget preferred 不同（preferred 只是 hint，不是 quota）",
                        related=(candidate.arc_id,), chapters=count,
                        budget_preferred=budget.preferred)

    def _arc(self, plan: StoryPlanningIR, arc_id: str) -> ArcPlan | None:
        return next((item for item in plan.arcs if item.arc_id == arc_id), None)

    def _plan_protagonist(self, plan: StoryPlanningIR) -> str:
        for character in plan.characters:
            if character.entity_ref:
                return character.entity_ref
        return plan.characters[0].character_id if plan.characters else ""

    def _check_arc_contract(self, plan: StoryPlanningIR,
                            candidate: ChapterCompilationCandidate,
                            findings: list[PlanningFinding]) -> None:
        arc = self._arc(plan, candidate.arc_id)
        if arc is None:
            add_finding(findings, "ARC_DECOMPOSITION_INVALID", "ERROR", "chapter",
                        candidate.arc_id, "candidate 的 arc_id 不在 plan 里")
            return
        arc_nodes = [node for node in plan.plot_nodes if node.node_id in set(arc.plot_nodes)]
        completed: dict[str, list[str]] = {}
        for allocation in candidate.chapter_allocations:
            for node_id in allocation.completed_plot_node_ids:
                completed.setdefault(node_id, []).append(allocation.chapter_id)
        duplicated = sorted(node_id for node_id, rows in completed.items() if len(rows) > 1)
        if duplicated:
            add_finding(findings, "PLOT_NODE_DUPLICATE_COMPLETION", "ERROR", "chapter",
                        candidate.arc_id, "同一个 PlotNode 在多个章节被标记 completion",
                        related=tuple(duplicated[:10]))
        must_unanchored = [node.node_id for node in arc_nodes
                           if node.must_happen and node.node_id not in completed]
        other_unanchored = [node.node_id for node in arc_nodes
                            if not node.must_happen and not node.optional
                            and node.node_id not in completed]
        optional_unanchored = [node.node_id for node in arc_nodes
                               if node.optional and node.node_id not in completed]
        if must_unanchored:
            add_finding(findings, "PLOT_NODE_WITHOUT_CHAPTER_ANCHOR", "ERROR", "chapter",
                        candidate.arc_id, "must_happen PlotNode 没有 execution anchor chapter",
                        related=tuple(must_unanchored[:10]))
        if other_unanchored:
            add_finding(findings, "PLOT_NODE_WITHOUT_CHAPTER_ANCHOR", "WARNING", "chapter",
                        candidate.arc_id, "有 PlotNode 没有 execution anchor chapter",
                        related=tuple(other_unanchored[:10]))
        unexplained = sorted(set(optional_unanchored) - set(candidate.deferred_optional_node_ids))
        if unexplained:
            add_finding(findings, "OPTIONAL_NODE_DROPPED_WITHOUT_REASON", "WARNING", "chapter",
                        candidate.arc_id, "optional node 被跳过但没有显式理由",
                        related=tuple(unexplained[:10]))
        payoff_nodes = {node.node_id for node in arc_nodes if node.payoff}
        order = {node_id: index for index, node_id in enumerate(topological_order(plan))}
        terminal_node = max(arc_nodes, key=lambda item: order.get(item.node_id, 0),
                            default=None)
        goal_chapters: list[str] = []
        for allocation, ir in zip(candidate.chapter_allocations, candidate.chapter_irs):
            if set(allocation.completed_plot_node_ids) & payoff_nodes \
                    or allocation.is_climax or any(effect.polarity in ("positive", "mixed")
                                                   for effect in ir.effects) \
                    or ir.state_transitions \
                    or (terminal_node is not None
                        and terminal_node.node_id in allocation.completed_plot_node_ids):
                goal_chapters.append(allocation.chapter_id)
        if self.profile.require_arc_goal_anchor and not goal_chapters:
            add_finding(findings, "ARC_GOAL_UNANCHORED", "ERROR", "chapter", arc.arc_id,
                        "ArcPlan 的核心目标 / payoff 没有任何章节真正执行", related=(arc.arc_id,))
        decision_nodes = {step.node_id for step in arc.decision_chain if step.node_id}
        decision_nodes |= {node.node_id for node in arc_nodes if node.major_choice}
        placed = {node_id for allocation in candidate.chapter_allocations
                  for node_id in allocation.completed_plot_node_ids}
        unplaced = sorted(decision_nodes - placed)
        if unplaced:
            add_finding(findings, "CHARACTER_ARC_CHOICE_UNPLACED", "ERROR", "chapter",
                        arc.arc_id, "重大角色抉择 / decision chain 无法落章",
                        related=tuple(unplaced[:10]))
        produces_state = any(ir.state_transitions for ir in candidate.chapter_irs) or any(
            effect.after_state for ir in candidate.chapter_irs for effect in ir.effects)
        if arc.ending_state and not produces_state:
            add_finding(findings, "ARC_ENDING_STATE_UNREACHABLE", "ERROR", "chapter",
                        arc.arc_id, "ending_state 无法由现有节点得到（需要新增 PlotNode / 重切 Arc）",
                        related=(arc.arc_id,))

    def _check_chapter_ir(self, plan: StoryPlanningIR,
                          candidate: ChapterCompilationCandidate,
                          findings: list[PlanningFinding]) -> None:
        registry = build_planning_state_registry(plan)
        validator = ChapterIRValidator(registry=registry)
        verifier = DeterministicSemanticVerifier(protagonist_id=self._plan_protagonist(plan),
                                                 dog_id="")
        policy = ChapterFunctionPolicy()
        allocations = {item.chapter_id: item for item in candidate.chapter_allocations}
        for ir in candidate.chapter_irs:
            allocation = allocations.get(ir.chapter_uuid)
            function = allocation.chapter_function if allocation else "setup"
            requirements = FUNCTION_REQUIREMENTS.get(function, FUNCTION_REQUIREMENTS["setup"])
            report = validator.validate(ir)
            for finding in report.findings:
                required = requirements.get(finding.field_name, "required") == "required"
                if finding.field_name and not required:
                    # optional / not_applicable 字段不强造剧情（§12）：缺证据不是 finding
                    continue
                severity = "ERROR" if finding.severity == "error" else "INFO"
                add_finding(findings, finding.code, severity, "chapter", ir.chapter_uuid,
                            finding.detail or finding.code,
                            related=(ir.chapter_uuid, finding.field_name))
            for finding in report.state_findings:
                add_finding(findings, finding.code, "ERROR", "chapter", ir.chapter_uuid,
                            finding.detail or finding.code,
                            related=(ir.chapter_uuid, finding.transition_id))
            semantic = verifier.verify(
                ir, {"goal": ir.goal}, registry=registry,
                function_finding=FunctionFinding(
                    chapter_function=function, decision=requirements["decision"],
                    turn=requirements["turn"], payoff=requirements["payoff"],
                    world_state_change=requirements["world_state_change"],
                    information_release=requirements["information_release"],
                    cost=requirements["cost"], loss=requirements["loss"],
                    evidence="M9 structured function（由 Planning 信号决定）"))
            for issue in semantic.issues:
                add_finding(findings, issue, "ERROR", "chapter", ir.chapter_uuid,
                            f"semantic verifier: {issue}", related=(ir.chapter_uuid,))
            if semantic.verdict != "AGREE" and not semantic.issues:
                add_finding(findings, "CHAPTER_SEMANTIC_VERIFICATION_FAILED", "WARNING",
                            "chapter", ir.chapter_uuid,
                            f"semantic verifier verdict={semantic.verdict}",
                            related=(ir.chapter_uuid,))
            policy_finding = policy.classify(ir, {"goal": ir.goal})
            if policy_finding.chapter_function != function:
                add_finding(findings, "CHAPTER_FUNCTION_POLICY_DIVERGENCE", "INFO", "chapter",
                            ir.chapter_uuid,
                            f"M9 function={function}，keyword policy={policy_finding.chapter_function}",
                            related=(ir.chapter_uuid,))

    def _reveal_positions(self, plan: StoryPlanningIR) -> dict[str, int]:
        order = {node_id: index for index, node_id in enumerate(topological_order(plan))}
        rows: dict[str, int] = {}
        for arc in plan.information_arcs:
            for move in arc.moves:
                if move.move_type in ("reveal", "payoff") and move.node_id:
                    rows[move.truth_id] = min(rows.get(move.truth_id, 10 ** 9),
                                              order.get(move.node_id, 10 ** 9))
        return rows

    def _check_knowledge(self, plan: StoryPlanningIR,
                         candidate: ChapterCompilationCandidate,
                         findings: list[PlanningFinding]) -> None:
        positions = self._reveal_positions(plan)
        order = {node_id: index for index, node_id in enumerate(topological_order(plan))}
        moves_by_node: dict[str, list[Any]] = {}
        truth_by_move: dict[str, str] = {}
        for arc in plan.information_arcs:
            for move in arc.moves:
                moves_by_node.setdefault(move.node_id, []).append(move)
                truth_by_move[move.move_id] = move.truth_id
        released_anywhere = {truth_id for allocation in candidate.chapter_allocations
                             for truth_id in allocation.reader_release}
        for allocation, ir in zip(candidate.chapter_allocations, candidate.chapter_irs):
            chapter_order = min([order.get(node_id, len(order))
                                 for node_id in allocation.plot_node_refs] or [len(order)])
            for truth_id in allocation.reader_release:
                expected = positions.get(truth_id, len(order))
                if chapter_order < expected:
                    add_finding(findings, "READER_REVEAL_TOO_EARLY", "ERROR", "chapter",
                                allocation.chapter_id,
                                "读者在本章提前知道了一个计划更晚才揭示的真相",
                                related=(allocation.chapter_id, truth_id))
            for node_id in allocation.plot_node_refs:
                for move in moves_by_node.get(node_id, []):
                    if move.move_type in ("reveal", "payoff") \
                            and move.truth_id not in released_anywhere:
                        add_finding(findings, "INFORMATION_REVEAL_MISSING", "ERROR", "chapter",
                                    allocation.chapter_id, "计划中的信息揭示没有进入任何章节",
                                    related=(move.move_id, move.truth_id))
            known = self._known_actors(plan, allocation, positions)
            for event in ir.event_frames:
                truths = sorted({truth_by_move[item] for item in event.fact_refs
                                 if item in truth_by_move})
                if event.decision_action or not truths:
                    continue
                speaker = event.actor_ids[0] if event.actor_ids else ""
                for truth_id in truths:
                    if speaker and truth_id not in known.get(speaker, set()):
                        add_finding(findings, "CHARACTER_KNOWLEDGE_LEAK", "ERROR", "chapter",
                                    allocation.chapter_id,
                                    "角色说出了自己还不该知道的真相",
                                    related=(allocation.chapter_id, speaker, truth_id))

    def _known_actors(self, plan: StoryPlanningIR, allocation: ChapterAllocation,
                      positions: dict[str, int]) -> dict[str, set[str]]:
        """到本章为止，谁（按 Planning 推演）知道哪些 truth。"""

        order = {node_id: index for index, node_id in enumerate(topological_order(plan))}
        chapter_order = min([order.get(node_id, len(order))
                             for node_id in allocation.plot_node_refs] or [len(order)])
        rows: dict[str, set[str]] = {}
        for arc in plan.information_arcs:
            for truth in arc.truths:
                holders = set(truth.character_knows) | set(truth.faction_knows)
                if truth.protagonist_knows and plan.characters:
                    holders.add(plan.characters[0].entity_ref or plan.characters[0].character_id)
                for move in arc.moves:
                    if move.truth_id != truth.truth_id or not move.node_id:
                        continue
                    if order.get(move.node_id, len(order)) <= chapter_order:
                        holders.update(move.holder_ids)
                for actor in holders:
                    rows.setdefault(actor, set()).add(truth.truth_id)
        _ = positions
        return rows

    def _check_ordering_and_continuity(self, plan: StoryPlanningIR,
                                       candidate: ChapterCompilationCandidate,
                                       findings: list[PlanningFinding],
                                       inventory: Any | None = None) -> None:
        allocations = candidate.chapter_allocations
        chapter_of_node: dict[str, int] = {}
        for allocation in allocations:
            for node_id in allocation.plot_node_refs:
                chapter_of_node.setdefault(node_id, allocation.order_index)
        for node in plan.plot_nodes:
            if node.node_id not in chapter_of_node or node.requirements is None:
                continue
            for ref in node.requirements.requirements:
                for satisfier in ref.satisfied_by:
                    if satisfier not in chapter_of_node:
                        continue
                    if chapter_of_node[satisfier] > chapter_of_node[node.node_id]:
                        add_finding(findings, "CHAPTER_REQUIREMENT_FROM_FUTURE", "ERROR",
                                    "chapter", allocation_id(candidate, node.node_id),
                                    "未来章节被用来满足过去章节的 requirement",
                                    related=(satisfier, node.node_id))
        moves_by_node: dict[str, list[Any]] = {}
        for arc in plan.information_arcs:
            for move in arc.moves:
                moves_by_node.setdefault(move.node_id, []).append(move)
        for plan_row in plan.foreshadow_plans:
            payload_chapters = [chapter_of_node.get(move.node_id) for move in plan_row.moves
                                if move.move_type == "payoff"]
            payload_chapters = [value for value in payload_chapters if value]
            plant_chapters = [chapter_of_node.get(move.node_id) for move in plan_row.moves
                              if move.move_type in ("plant", "reinforce", "reveal", "misdirect")]
            plant_chapters = [value for value in plant_chapters if value]
            if payload_chapters and plant_chapters \
                    and min(payload_chapters) < max(plant_chapters):
                add_finding(findings, "FORESHADOW_ORDER_BROKEN", "ERROR", "chapter",
                            plan_row.foreshadow_id, "伏笔回收被安排在埋设 / 强化之前",
                            related=(plan_row.foreshadow_id,))
        resource_cursor: dict[str, float] = {}
        for allocation, ir in zip(allocations, candidate.chapter_irs):
            for effect in ir.effects:
                for resource_id, delta in effect.resource_delta.items():
                    value = resource_cursor.get(resource_id, 0.0) + float(delta)
                    if value < 0:
                        add_finding(findings, "RESOURCE_UNSOURCED_CONSUMPTION", "ERROR",
                                    "chapter", allocation.chapter_id,
                                    "本章消费没有 Planning 来源（M5 ResourceFlow 不足）",
                                    related=(allocation.chapter_id, resource_id))
                    resource_cursor[resource_id] = value
        lifecycle_order = {equipment.equipment_id: [step.state for step in equipment.lifecycle]
                           for equipment in plan.equipment_plans}
        seen_states: dict[str, int] = {}
        for allocation, ir in zip(allocations, candidate.chapter_irs):
            for transition in ir.state_transitions:
                if not transition.state_key.startswith("equipment_"):
                    continue
                equipment_id = transition.state_key[len("equipment_"):]
                states = lifecycle_order.get(equipment_id, [])
                if transition.to_state not in states:
                    continue
                index = states.index(transition.to_state)
                if index < seen_states.get(equipment_id, 0):
                    add_finding(findings, "EQUIPMENT_SEQUENCE_INFEASIBLE", "ERROR", "chapter",
                                allocation.chapter_id, "装备状态回退到已越过的阶段",
                                related=(equipment_id, transition.to_state))
                seen_states[equipment_id] = max(seen_states.get(equipment_id, 0), index)
        for arc in plan.relationship_arcs:
            for stage in arc.stages:
                if stage.trigger_node_id in chapter_of_node \
                        and not any(stage.stage_id in allocation.source_planning_ids
                                    or stage.stage_id in (
                                        transition.subject_id
                                        for transition in candidate.chapter_irs[
                                            index].state_transitions)
                                    for index, allocation in enumerate(allocations)):
                    add_finding(findings, "RELATIONSHIP_CHANGE_WITHOUT_CHAPTER", "WARNING",
                                "chapter", stage.stage_id, "关系阶段没有落到章节",
                                related=(stage.stage_id,))
        for track in plan.progression_tracks:
            for milestone in track.milestones:
                if milestone.node_id in chapter_of_node:
                    if not any(milestone.milestone_id in ir.source_refs
                               or milestone.milestone_id in (
                                   transition.subject_id for transition in ir.state_transitions)
                               for ir in candidate.chapter_irs):
                        add_finding(findings, "PROGRESSION_WITHOUT_CHAPTER", "WARNING",
                                    "chapter", milestone.milestone_id,
                                    "成长里程碑没有落到章节", related=(milestone.milestone_id,))
        for expansion in plan.map_expansions:
            for milestone in expansion.milestones:
                if milestone.trigger_node_id in chapter_of_node \
                        and not any(milestone.milestone_id in ir.source_refs or
                                    any(transition.subject_id == milestone.milestone_id
                                        for transition in ir.state_transitions)
                                    for ir in candidate.chapter_irs):
                    add_finding(findings, "MAP_EXPANSION_WITHOUT_CHAPTER", "WARNING", "chapter",
                                milestone.milestone_id, "地图推进没有落到章节",
                                related=(milestone.milestone_id,))
        for arc in plan.faction_arcs:
            for stage in arc.stages:
                if stage.trigger_node_id in chapter_of_node \
                        and not any(stage.stage_id in allocation.source_planning_ids
                                    for allocation in allocations):
                    add_finding(findings, "FACTION_CHANGE_WITHOUT_CHAPTER", "WARNING",
                                "chapter", stage.stage_id, "势力阶段没有落到章节",
                                related=(stage.stage_id,))

    def _check_distribution(self, plan: StoryPlanningIR,
                            candidate: ChapterCompilationCandidate,
                            findings: list[PlanningFinding]) -> None:
        functions = [allocation.chapter_function for allocation in candidate.chapter_allocations]
        for index in range(len(functions) - 2):
            window = functions[index:index + 3]
            if len(set(window)) == 1 and window[0] not in ("aftermath", "transition"):
                add_finding(findings, "CHAPTER_FUNCTION_REPETITION", "WARNING", "chapter",
                            candidate.arc_id, f"连续三个章节功能相同：{window[0]}",
                            related=(candidate.arc_id,))
        arc = self._arc(plan, candidate.arc_id)
        if arc is not None and plan.arcs and arc.arc_id == plan.arcs[-1].arc_id:
            if not any(item.is_climax for item in candidate.chapter_allocations):
                add_finding(findings, "CLIMAX_ARC_WITHOUT_CLIMAX_CHAPTER", "WARNING", "chapter",
                            candidate.arc_id, "收束 Arc 没有 climax / resolution 章节",
                            related=(candidate.arc_id,))
        if arc is not None and not plan.arcs:
            add_finding(findings, "ARC_DECOMPOSITION_INVALID", "ERROR", "chapter",
                        candidate.arc_id, "plan 没有任何 arc")

    # ---------------------------------------------------------------- coverage
    def _coverage(self, plan: StoryPlanningIR, candidate: ChapterCompilationCandidate, *,
                  inventory: Any | None = None,
                  findings: list[PlanningFinding]) -> ArcExecutionCoverageReport:
        arc = self._arc(plan, candidate.arc_id)
        arc_nodes = [node for node in plan.plot_nodes
                     if arc is not None and node.node_id in set(arc.plot_nodes)]
        completed: dict[str, list[str]] = {}
        for allocation in candidate.chapter_allocations:
            for node_id in allocation.completed_plot_node_ids:
                completed.setdefault(node_id, []).append(allocation.chapter_id)
        info_moves = [move for arc_row in plan.information_arcs for move in arc_row.moves
                      if arc is not None and move.node_id in set(arc.plot_nodes)]
        info_reveals = [move for move in info_moves if move.move_type in ("reveal", "payoff")]
        released = {truth for allocation in candidate.chapter_allocations
                    for truth in allocation.reader_release}
        foreshadow_moves = [move for plan_row in plan.foreshadow_plans for move in plan_row.moves
                            if arc is not None and move.node_id in set(arc.plot_nodes)]
        relationships = [stage.stage_id for arc_row in plan.relationship_arcs
                         for stage in arc_row.stages
                         if arc is not None and stage.trigger_node_id in set(arc.plot_nodes)]
        progression = [milestone.milestone_id for track in plan.progression_tracks
                       for milestone in track.milestones
                       if arc is not None and milestone.node_id in set(arc.plot_nodes)]
        map_rows = [milestone.milestone_id for expansion in plan.map_expansions
                    for milestone in expansion.milestones
                    if arc is not None and milestone.trigger_node_id in set(arc.plot_nodes)]
        reward_rows = [event.reward_id for plan_row in plan.reward_plans for event in plan_row.events
                       if arc is not None and event.trigger_node_id in set(arc.plot_nodes)]
        resource_rows = [flow.identity() for flow in plan.resource_flows
                         if arc is not None and flow.trigger_node_id in set(arc.plot_nodes)]
        equipment_rows = [equipment.equipment_id for equipment in plan.equipment_plans
                          if arc is not None and set(equipment.nodes()) & set(arc.plot_nodes)]
        faction_rows = [stage.stage_id for arc_row in plan.faction_arcs for stage in arc_row.stages
                        if arc is not None and stage.trigger_node_id in set(arc.plot_nodes)]
        autonomous_rows = [action.action_id for action in plan.autonomous_actions
                           if arc is not None and action.trigger_ref in set(arc.plot_nodes)]
        pressure_ids = sorted({item for allocation in candidate.chapter_allocations
                               for item in allocation.pressure_refs})
        source_refs = {item for ir in candidate.chapter_irs for item in ir.source_refs}
        function_counts: dict[str, int] = {}
        for allocation in candidate.chapter_allocations:
            function_counts[allocation.chapter_function] = \
                function_counts.get(allocation.chapter_function, 0) + 1
        errors = [item for item in findings if item.severity == "ERROR"]
        warnings = [item for item in findings if item.severity == "WARNING"]
        return ArcExecutionCoverageReport(
            arc_id=candidate.arc_id, chapter_count=len(candidate.chapter_irs),
            goal_anchored=bool([allocation for allocation in candidate.chapter_allocations
                                if allocation.is_climax or allocation.consequence_node_refs]),
            goal_chapter_ids=[allocation.chapter_id for allocation in candidate.chapter_allocations
                              if allocation.is_climax or allocation.consequence_node_refs],
            plot_nodes_total=len(arc_nodes),
            plot_nodes_anchored=len([node for node in arc_nodes if node.node_id in completed]),
            plot_nodes_unanchored=sorted(node.node_id for node in arc_nodes
                                         if node.node_id not in completed),
            plot_nodes_duplicated=sorted(node_id for node_id, rows in completed.items()
                                         if len(rows) > 1),
            must_happen_unanchored=sorted(node.node_id for node in arc_nodes
                                          if node.must_happen and node.node_id not in completed),
            optional_deferred=sorted(node.node_id for node in arc_nodes
                                     if node.optional and node.node_id not in completed),
            decision_anchored=[allocation.chapter_id for allocation, ir in
                               zip(candidate.chapter_allocations, candidate.chapter_irs)
                               if any(event.decision_action for event in ir.event_frames)],
            turn_chapter_ids=[allocation.chapter_id for allocation, ir in
                              zip(candidate.chapter_allocations, candidate.chapter_irs)
                              if any(item.transition_kind in TURN_KINDS
                                     for item in ir.state_transitions)
                              or any(effect.is_narrative_pivot for effect in ir.effects)],
            payoff_chapter_ids=[allocation.chapter_id for allocation, ir in
                                zip(candidate.chapter_allocations, candidate.chapter_irs)
                                if any(effect.polarity in ("positive", "mixed")
                                       for effect in ir.effects)],
            information_anchored=sorted({move.truth_id for move in info_reveals} & released),
            information_missing=sorted({move.truth_id for move in info_reveals} - released),
            foreshadow_anchored=sorted({move.move_id for move in foreshadow_moves
                                        if move.move_id in source_refs}),
            foreshadow_missing=sorted({move.move_id for move in foreshadow_moves
                                       if move.move_id not in source_refs}),
            relationship_anchored=sorted(set(relationships) & source_refs),
            faction_anchored=sorted(set(faction_rows) & source_refs),
            progression_anchored=sorted(set(progression) & source_refs),
            resource_anchored=sorted(set(resource_rows) & source_refs),
            equipment_anchored=sorted(set(equipment_rows) & source_refs),
            map_anchored=sorted(set(map_rows) & source_refs),
            reward_anchored=sorted(set(reward_rows) & source_refs),
            autonomous_anchored=sorted(set(autonomous_rows) & source_refs),
            pressure_anchored=pressure_ids,
            knowledge_gate_pass=not [item for item in errors
                                     if item.code in ("CHARACTER_KNOWLEDGE_LEAK",
                                                      "READER_REVEAL_TOO_EARLY",
                                                      "INFORMATION_REVEAL_MISSING")],
            budget_range=candidate.decomposition.budget_range,
            budget_status=("in_range" if candidate.decomposition.budget_range.minimum
                           <= len(candidate.chapter_irs)
                           <= candidate.decomposition.budget_range.maximum else "out_of_range"),
            function_counts=function_counts,
            status=("blocked" if errors else "needs_attention" if warnings else "valid"))

    # ---------------------------------------------------------------- promotion
    def promote(self, repository: Any, store: Any,
                candidate: ChapterCompilationCandidate, *, approved: bool = False,
                revision_id: str = "", note: str = ""
                ) -> tuple[ChapterCompilationRecord, Any]:
        return promote_chapter_candidate(repository, store, candidate, approved=approved,
                                         revision_id=revision_id, note=note)


def allocation_id(candidate: ChapterCompilationCandidate, node_id: str) -> str:
    for allocation in candidate.chapter_allocations:
        if node_id in allocation.plot_node_refs:
            return allocation.chapter_id
    return candidate.arc_id


def promote_chapter_candidate(repository: Any, store: Any,
                              candidate: ChapterCompilationCandidate, *,
                              approved: bool = False, revision_id: str = "",
                              note: str = ""
                              ) -> tuple[ChapterCompilationRecord, Any]:
    """candidate → staging → 新 immutable revision（arc.detail_level=chapter_ready）→
    正式 chapter artifact refs。任何一步失败都不留"孤儿 official chapter IR"。
    """

    if not approved:
        raise ValueError("CHAPTER_CANDIDATE_NOT_APPROVED: promote 需要显式 approve")
    if candidate.blocking():
        raise ValueError("CHAPTER_CANDIDATE_BLOCKED: 存在 blocking ERROR，不能 promote")
    staged_digest = store.stage_candidate(candidate)
    base = repository.load(candidate.source_revision_id)
    payload = base.plan.model_dump(mode="json")
    chapter_ids = [ir.chapter_uuid for ir in candidate.chapter_irs]
    for row in payload.get("arcs") or []:
        if row.get("arc_id") != candidate.arc_id:
            continue
        row["detail_level"] = "chapter_ready"
        row["chapter_refs"] = chapter_ids
        row["chapter_ir_digest"] = staged_digest
    plan = StoryPlanningIR.model_validate(payload)
    record = repository.create(
        plan, branch_id=base.branch_id, status="proposed",
        note=note or f"M9 {candidate.candidate_id} arc {candidate.arc_id}",
        parent_revision_id=base.revision_id, source_revision=base.revision_id,
        revision_id=revision_id)
    committed = store.commit_candidate(candidate, planning_revision_id=record.revision_id,
                                       chapter_ir_digest_value=staged_digest)
    _ = committed
    compilation = ChapterCompilationRecord(
        source_revision=base.revision_id, source_digest=base.content_digest,
        arc_id=candidate.arc_id, candidate_id=candidate.candidate_id,
        promoted_revision_id=record.revision_id, chapter_ids=chapter_ids,
        chapter_ir_digest=staged_digest,
        validation_digest=planning_digest(
            [item.model_dump(mode="json") for item in candidate.validation_findings]))
    return compilation, record
