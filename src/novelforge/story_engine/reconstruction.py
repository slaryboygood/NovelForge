"""M10：WASTELAND Top-down Reconstruction（derived artifacts；不修任何内容）。

三层时间语义严格分开：

- `happened_historical`：Canon / StoryState / confirmed Chapter IR —— 不可重规划；
- `legacy_representation`：旧大纲 / FuturePlan / legacy 字段 —— 可以错，M11 才能修；
- `future_planning`：Story Planning IR / PlotNode / Volume / Arc / Chapter IR —— 可以规划。

M10 只分析、只建立 target（Historical Story Map / LegacyTargetAlignment / M11 Batch Plan /
AuthorDecisionQueue），绝不修改 Canon / StoryState / 历史章节 / 旧 candidate。
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from pydantic import Field

from novelforge.models import StrictModel

from .planning import (
    ChapterBudgetEstimate,
    CompilationScope,
    OutlineCompiler,
    PlanningRepository,
    PlanningValidator,
    StoryPlanningBuilder,
    validate_planning_ir,
)

RECONSTRUCTION_VERSION = "m10-1"
RECON_DIR = "workspace/wasteland_001_exports/reconstruction_v2"
M1B_V2 = "workspace/wasteland_001_exports/chapter_ir_v1/m1b_v2"
FULL_MIGRATION = "workspace/wasteland_001_exports/chapter_ir_v1/full_migration"
LEGACY_CANDIDATE = ("workspace/wasteland_001_exports/"
                    "WASTELAND_001_OUTLINE_CANON_FINAL_CANDIDATE_V5.json")
CANON_DB = "novel/authoring/story_engine/canon/wasteland_001.sqlite"
STATE_JSON = "novel/authoring/story_engine/state/runtime_wasteland_001/v000001.json"
PROFILE_JSON = "novel/authoring/story_engine/profiles/wasteland_001.json"
PACK_JSON = "novel/config/story_engine/wasteland_001_pack.json"
PLANNING_ROOT = "novel/authoring/story_engine/planning"

TimeLayer = Literal["happened_historical", "legacy_representation", "future_planning"]
RepairRisk = Literal["LOW", "MEDIUM", "HIGH", "HUMAN_REQUIRED"]
GapSubtype = Literal["representation_gap", "semantic_evidence_gap", "causal_gap",
                     "decision_gap", "turn_gap", "payoff_gap", "information_gap",
                     "relationship_gap", "progression_gap", "resource_gap",
                     "continuity_gap", "actual_content_gap", "human_design_gap"]
ConflictSubtype = Literal["function_conflict", "actor_conflict", "decision_conflict",
                          "turn_conflict", "payoff_conflict", "state_binding_conflict",
                          "timeline_conflict", "knowledge_conflict", "resource_conflict",
                          "relationship_conflict", "future_reference_conflict",
                          "other_conflict"]
RepairType = Literal["FIELD_REWRITE", "FIELD_DELETE", "FIELD_REBIND", "ADD_MISSING_TURN",
                     "ADD_MISSING_PAYOFF", "ADD_MISSING_DECISION_EVIDENCE",
                     "ADD_CAUSAL_LINK", "ADD_INFORMATION_EVIDENCE",
                     "ADD_RELATIONSHIP_EVIDENCE", "ADD_RESOURCE_EVIDENCE",
                     "RECLASSIFY_FUNCTION", "CONTENT_REWRITE_REQUIRED",
                     "HUMAN_REVIEW_REQUIRED"]


class ReconstructionFinding(StrictModel):
    """M10 统一 finding（复用 PlanningFinding 的形态 + recommended_action）。"""

    code: str = Field(min_length=3, max_length=64)
    severity: Literal["ERROR", "WARNING", "INFO"] = "INFO"
    domain: str = Field(default="reconstruction", max_length=32)
    source_id: str = Field(default="", max_length=160)
    related_ids: list[str] = Field(default_factory=list)
    message: str = Field(default="", max_length=300)
    evidence: dict[str, Any] = Field(default_factory=dict)
    recommended_action: str = Field(default="", max_length=200)
    non_authoritative: bool = True


class WastelandReconstructionBaseline(StrictModel):
    novel_id: str = "wasteland_001"
    planning_revision: str = Field(default="", max_length=64)
    canon_digest: str = Field(default="", max_length=64)
    story_state_digest: str = Field(default="", max_length=64)
    legacy_candidate_digest: str = Field(default="", max_length=64)
    chapter_ir_digest: str = Field(default="", max_length=64)
    profile_digest: str = Field(default="", max_length=64)
    content_pack_digest: str = Field(default="", max_length=64)
    route_identity: str = Field(default="", max_length=128)
    chapter_count: int = 0
    m1_coverage: int = 0
    queue_counts: dict[str, int] = Field(default_factory=dict)
    m1_gate: dict[str, Any] = Field(default_factory=dict)
    compiler_version: str = RECONSTRUCTION_VERSION
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    read_only: bool = True

    def happened_digests(self) -> dict[str, str]:
        return {"canon": self.canon_digest, "story_state": self.story_state_digest,
                "legacy_candidate": self.legacy_candidate_digest,
                "chapter_ir": self.chapter_ir_digest}


class HistoricalChapterRecord(StrictModel):
    """570 章历史结构（来自 M1 Chapter IR + Canon / StoryState evidence 的只读派生）。"""

    chapter_id: str = Field(default="", max_length=128)
    legacy_label: str = Field(default="", max_length=32)
    display_number: int = 0
    volume: int = 0
    arc: str = Field(default="", max_length=32)
    title: str = Field(default="", max_length=160)
    chapter_function: str = Field(default="", max_length=32)
    classification: str = Field(default="", max_length=32)
    deterministic_issues: list[str] = Field(default_factory=list)
    missing_required_fields: list[str] = Field(default_factory=list)
    blocked_fields: list[str] = Field(default_factory=list)
    leg_conflicts: list[str] = Field(default_factory=list)
    dog_role: str = Field(default="", max_length=32)
    primary_transition: dict[str, Any] = Field(default_factory=dict)
    writer_preview_refs: list[str] = Field(default_factory=list)
    evidence_refs: list[str] = Field(default_factory=list)
    time_layer: TimeLayer = "happened_historical"
    derived_from: list[str] = Field(default_factory=lambda: ["chapter_ir", "reconciliation_v4"])
    non_authoritative: bool = True


class HistoricalVolumeAlignment(StrictModel):
    volume_id: str = Field(default="", max_length=64)
    index: int = 0
    legacy_title: str = Field(default="", max_length=200)
    chapter_range: list[int] = Field(default_factory=list)
    chapter_count: int = 0
    confirmed_chapters: int = 0
    gap_chapters: int = 0
    conflict_chapters: int = 0
    goals: list[str] = Field(default_factory=list)
    major_transitions: list[str] = Field(default_factory=list)
    time_layer: TimeLayer = "legacy_representation"
    evidence_refs: list[str] = Field(default_factory=list)
    non_authoritative: bool = True


class HistoricalArcAlignment(StrictModel):
    arc_id: str = Field(default="", max_length=64)
    volume_index: int = 0
    legacy_arc: str = Field(default="", max_length=32)
    chapter_range: list[int] = Field(default_factory=list)
    chapter_count: int = 0
    goal: str = Field(default="", max_length=300)
    opening_state: str = Field(default="", max_length=200)
    historical_pressure: list[str] = Field(default_factory=list)
    major_anchors: list[str] = Field(default_factory=list)
    decision_chain: list[str] = Field(default_factory=list)
    turns: list[str] = Field(default_factory=list)
    payoff: list[str] = Field(default_factory=list)
    cost: list[str] = Field(default_factory=list)
    ending_state: str = Field(default="", max_length=200)
    time_layer: TimeLayer = "legacy_representation"
    evidence_refs: list[str] = Field(default_factory=list)
    non_authoritative: bool = True


class HistoricalStoryMap(StrictModel):
    novel_id: str = "wasteland_001"
    chapters: list[HistoricalChapterRecord] = Field(default_factory=list)
    volumes: list[HistoricalVolumeAlignment] = Field(default_factory=list)
    arcs: list[HistoricalArcAlignment] = Field(default_factory=list)
    domain_counts: dict[str, int] = Field(default_factory=dict)
    priority_note: str = ("confirmed semantic structure > Canon / StoryState > legacy outline text")
    read_only: bool = True
    non_authoritative: bool = True


class HistoricalCausalSpine(StrictModel):
    nodes: list[str] = Field(default_factory=list)
    edges: list[dict[str, str]] = Field(default_factory=list)
    major_event_refs: list[str] = Field(default_factory=list)
    derived_from: list[str] = Field(default_factory=lambda: ["historical_story_map"])
    read_only: bool = True
    non_authoritative: bool = True


class OpenStoryItem(StrictModel):
    item_id: str = Field(default="", max_length=80)
    domain: str = Field(default="", max_length=32)
    statement: str = Field(default="", max_length=300)
    source: str = Field(default="", max_length=64)
    historical_evidence: list[str] = Field(default_factory=list)
    current_state: str = Field(default="open", max_length=32)
    priority: str = Field(default="medium", max_length=16)
    dependencies: list[str] = Field(default_factory=list)
    time_layer: TimeLayer = "future_planning"
    non_authoritative: bool = True


class WastelandOpenStoryInventory(StrictModel):
    novel_id: str = "wasteland_001"
    items: list[OpenStoryItem] = Field(default_factory=list)
    by_domain: dict[str, int] = Field(default_factory=dict)
    read_only: bool = True
    non_authoritative: bool = True


class StoryHandoffPoint(StrictModel):
    last_happened_anchor: str = Field(default="", max_length=128)
    last_happened_label: str = Field(default="", max_length=32)
    route_identity: str = Field(default="", max_length=128)
    current_character_state: dict[str, Any] = Field(default_factory=dict)
    current_relationship_state: dict[str, Any] = Field(default_factory=dict)
    current_faction_state: dict[str, Any] = Field(default_factory=dict)
    current_location_state: dict[str, Any] = Field(default_factory=dict)
    current_resources: dict[str, Any] = Field(default_factory=dict)
    current_equipment: dict[str, Any] = Field(default_factory=dict)
    current_knowledge: dict[str, Any] = Field(default_factory=dict)
    current_progression: dict[str, Any] = Field(default_factory=dict)
    open_pressures: list[str] = Field(default_factory=list)
    open_foreshadows: list[str] = Field(default_factory=list)
    open_requirements: list[str] = Field(default_factory=list)
    next_feasible_opportunities: list[str] = Field(default_factory=list)
    time_layer: TimeLayer = "happened_historical"
    read_only: bool = True
    non_authoritative: bool = True


class LegacyChapterAlignment(StrictModel):
    chapter_id: str = Field(default="", max_length=128)
    legacy_label: str = Field(default="", max_length=32)
    display_number: int = 0
    m1_classification: str = Field(default="", max_length=32)
    historical_volume: int = 0
    historical_arc: str = Field(default="", max_length=64)
    historical_plot_role: str = Field(default="", max_length=32)
    confirmed_source_refs: list[str] = Field(default_factory=list)
    domain_refs: dict[str, list[str]] = Field(default_factory=dict)
    target_fields: list[str] = Field(default_factory=list)
    legacy_fields: list[str] = Field(default_factory=list)
    difference_classification: list[str] = Field(default_factory=list)
    repairability: str = Field(default="", max_length=32)
    forbidden_changes: list[str] = Field(default_factory=list)
    evidence: list[str] = Field(default_factory=list)
    time_layer: TimeLayer = "legacy_representation"
    non_authoritative: bool = True


class LegacyTargetAlignment(StrictModel):
    """M11 的核心输入：每个待修章节 target（allowed / forbidden / risk / scope）。"""

    primary_issue: str = Field(default="", max_length=64)
    chapter_id: str = Field(default="", max_length=128)
    legacy_label: str = Field(default="", max_length=32)
    current_classification: str = Field(default="", max_length=32)
    historical_arc: str = Field(default="", max_length=64)
    historical_volume: int = 0
    confirmed_facts: list[str] = Field(default_factory=list)
    target_chapter_function: str = Field(default="", max_length=32)
    target_semantic_fields: list[str] = Field(default_factory=list)
    missing_semantic_fields: list[str] = Field(default_factory=list)
    conflicting_legacy_fields: list[str] = Field(default_factory=list)
    gap_subtype: GapSubtype | None = None
    conflict_subtype: ConflictSubtype | None = None
    evidence_gap_subtypes: list[str] = Field(default_factory=list)
    state_domain: str = Field(default="", max_length=32)
    domain_tags: list[str] = Field(default_factory=list)
    recommended_repair_type: str = Field(default="", max_length=48)
    required_validators: list[str] = Field(default_factory=list)
    required_context: list[str] = Field(default_factory=list)
    upstream_dependencies: list[str] = Field(default_factory=list)
    downstream_dependencies: list[str] = Field(default_factory=list)
    allowed_repair_types: list[RepairType] = Field(default_factory=list)
    forbidden_changes: list[str] = Field(default_factory=list)
    recommended_repair_scope: str = Field(default="", max_length=64)
    risk: RepairRisk = "LOW"
    human_review_required: bool = False
    owning_repair_batch_id: str = Field(default="", max_length=32)
    forbidden_change_sources: list[str] = Field(default_factory=list)
    evidence_refs: list[str] = Field(default_factory=list)
    time_layer: TimeLayer = "legacy_representation"
    non_authoritative: bool = True


class BatchAcceptanceContract(StrictModel):
    gates: list[str] = Field(default_factory=lambda: [
        "chapter_ir_validator", "chapter_function_policy", "canon_consistency",
        "story_state_boundary", "resource_continuity", "knowledge_boundary",
        "relationship_continuity", "information_order", "foreshadow_order",
        "causality", "writer_projection", "m1_semantic_gate"])
    non_authoritative: bool = True


class WastelandRepairBatch(StrictModel):
    batch_id: str = Field(default="", max_length=32)
    volume_refs: list[int] = Field(default_factory=list)
    arc_refs: list[str] = Field(default_factory=list)
    chapter_ids: list[str] = Field(default_factory=list)
    legacy_labels: list[str] = Field(default_factory=list)
    field_conflict_ids: list[str] = Field(default_factory=list)
    content_gap_ids: list[str] = Field(default_factory=list)
    dependency_batches: list[str] = Field(default_factory=list)
    confirmed_facts_digest: str = Field(default="", max_length=64)
    target_alignment_digest: str = Field(default="", max_length=64)
    allowed_changes: list[str] = Field(default_factory=list)
    forbidden_changes: list[str] = Field(default_factory=list)
    expected_repair_types: list[RepairType] = Field(default_factory=list)
    risk: RepairRisk = "LOW"
    human_review_items: list[str] = Field(default_factory=list)
    acceptance: BatchAcceptanceContract = Field(default_factory=BatchAcceptanceContract)
    read_only_dependency_chapter_ids: list[str] = Field(default_factory=list)
    risk_distribution: dict[str, int] = Field(default_factory=dict)
    validators: list[str] = Field(default_factory=list)
    mutable_target_count: int = 0
    non_authoritative: bool = True


class WastelandRepairBatchPlan(StrictModel):
    batches: list[WastelandRepairBatch] = Field(default_factory=list)
    recommended_batch_shape: str = "2–4 Arc / 约 20–30 chapter（推荐范围，可按依赖放宽）"
    ordering_note: str = ("顺序由 causal dependency / character arc / relationship / "
                          "information·foreshadow / resource continuity 决定，不做机械切分")
    read_only: bool = True
    non_authoritative: bool = True


class WastelandAuthorDecision(StrictModel):
    decision_id: str = Field(default="", max_length=64)
    question: str = Field(default="", max_length=300)
    affected_chapters: list[str] = Field(default_factory=list)
    affected_arcs: list[str] = Field(default_factory=list)
    evidence: list[str] = Field(default_factory=list)
    option_a: str = Field(default="", max_length=300)
    option_b: str = Field(default="", max_length=300)
    tradeoff: str = Field(default="", max_length=300)
    blocking_scope: list[str] = Field(default_factory=list)
    recommended_default: str = Field(default="", max_length=300)
    recommended_default_is_authoritative: bool = False
    non_authoritative: bool = True


class WastelandAuthorDecisionQueue(StrictModel):
    items: list[WastelandAuthorDecision] = Field(default_factory=list)
    note: str = ("AuthorDecisionQueue 不必为 0：系统只区分'事实无法确定'与"
                 "'作者需要做选择'，绝不让 LLM 代替作者决定")
    read_only: bool = True
    non_authoritative: bool = True


class LegacyTargetAlignmentSet(StrictModel):
    targets: list[LegacyTargetAlignment] = Field(default_factory=list)
    field_conflict_subtypes: dict[str, int] = Field(default_factory=dict)
    content_gap_subtypes: dict[str, int] = Field(default_factory=dict)
    risk_counts: dict[str, int] = Field(default_factory=dict)
    read_only: bool = True
    non_authoritative: bool = True


class ReconstructionFinalGate(StrictModel):
    novel_id: str = "wasteland_001"
    alignment_coverage: int = 0
    chapter_total: int = 0
    queue_counts_before: dict[str, int] = Field(default_factory=dict)
    queue_counts_after: dict[str, int] = Field(default_factory=dict)
    field_conflict_targets: int = 0
    content_gap_targets: int = 0
    confirmed_chapters_in_repair: list[str] = Field(default_factory=list)
    happened_digests_before: dict[str, str] = Field(default_factory=dict)
    happened_digests_after: dict[str, str] = Field(default_factory=dict)
    findings: list[ReconstructionFinding] = Field(default_factory=list)
    repair_ownership_coverage: int = 0
    repair_target_total: int = 0
    batch_dag_valid: bool = False
    legacy_isolation_ok: bool = False
    runways: dict[str, str] = Field(default_factory=dict)
    status: Literal["PASS", "NEEDS_ATTENTION"] = "NEEDS_ATTENTION"
    read_only: bool = True

    def ok(self) -> bool:
        return (self.status == "PASS" and self.alignment_coverage == self.chapter_total
                and not self.confirmed_chapters_in_repair
                and self.happened_digests_before == self.happened_digests_after
                and self.queue_counts_before == self.queue_counts_after
                and self.repair_ownership_coverage == self.repair_target_total
                and self.batch_dag_valid and self.legacy_isolation_ok)


FutureDisposition = Literal["scheduled", "deferred", "intentionally_unresolved",
                            "terminal_resolution", "author_decision_required"]


class FutureItemDisposition(StrictModel):
    """Open Story Inventory 的每一项在未来 spine 里必须有明确去向（禁止无声消失）。"""

    item_id: str = Field(default="", max_length=80)
    domain: str = Field(default="", max_length=32)
    disposition: FutureDisposition = "scheduled"
    anchor_node_ids: list[str] = Field(default_factory=list)
    anchor_volume_ids: list[str] = Field(default_factory=list)
    reason: str = Field(default="", max_length=200)
    non_authoritative: bool = True


class FullBookFutureSpine(StrictModel):
    """整本剩余小说的粗骨架（远期粗 / 近期细；不生成 Chapter IR）。"""

    novel_id: str = "wasteland_001"
    source_revision: str = Field(default="", max_length=64)
    remaining_target_words: int = 0
    remaining_estimate_chapters: int = 0
    plan_node_count: int = 0
    major_node_ids: list[str] = Field(default_factory=list)
    terminal_direction_node_id: str = Field(default="", max_length=64)
    volume_count: int = 0
    arc_count: int = 0
    detail_levels: dict[str, str] = Field(default_factory=dict)
    item_dispositions: list[FutureItemDisposition] = Field(default_factory=list)
    undisposed_item_ids: list[str] = Field(default_factory=list)
    conflict_escalation_chains: list[str] = Field(default_factory=list)
    character_arc_count: int = 0
    relationship_arc_count: int = 0
    faction_arc_count: int = 0
    map_expansion_count: int = 0
    progression_track_count: int = 0
    information_arc_count: int = 0
    foreshadow_path_count: int = 0
    reward_event_count: int = 0
    route_identity: str = Field(default="", max_length=128)
    route_review_required: bool = False
    time_layer: TimeLayer = "future_planning"
    read_only: bool = True
    non_authoritative: bool = True


class FutureVolumeDirection(StrictModel):
    volume_id: str = Field(default="", max_length=64)
    index: int = 0
    detail_level: str = Field(default="spine", max_length=24)
    volume_goal: str = Field(default="", max_length=300)
    macro_pressure: str = Field(default="", max_length=300)
    major_conflict: str = Field(default="", max_length=300)
    major_node_anchors: list[str] = Field(default_factory=list)
    character_arc_movement: str = Field(default="", max_length=200)
    relationship_movement: str = Field(default="", max_length=200)
    faction_movement: str = Field(default="", max_length=200)
    map_expansion: list[str] = Field(default_factory=list)
    progression_direction: str = Field(default="", max_length=200)
    information_obligation: list[str] = Field(default_factory=list)
    foreshadow_obligation: list[str] = Field(default_factory=list)
    major_payoff: str = Field(default="", max_length=200)
    ending_pressure: str = Field(default="", max_length=300)
    time_layer: TimeLayer = "future_planning"
    non_authoritative: bool = True


class StructuralRunway(StrictModel):
    runway: str = Field(default="", max_length=32)
    available_units: int = 0
    required_units: int = 0
    verdict: Literal["sufficient", "insufficient", "unknown"] = "unknown"
    evidence: list[str] = Field(default_factory=list)
    note: str = Field(default="", max_length=200)
    non_authoritative: bool = True


class StructuralRunwayReport(StrictModel):
    novel_id: str = "wasteland_001"
    remaining_target_words: int = 0
    remaining_estimate_chapters: int = 0
    runways: list[StructuralRunway] = Field(default_factory=list)
    insufficient_runways: list[str] = Field(default_factory=list)
    structure_too_thin: bool = False
    findings: list[ReconstructionFinding] = Field(default_factory=list)
    read_only: bool = True
    non_authoritative: bool = True


class M11BatchReadiness(StrictModel):
    batch_id: str = Field(default="", max_length=32)
    status: Literal["READY", "BLOCKED_AUTHOR_DECISION", "BLOCKED_DEPENDENCY",
                    "BLOCKED_STRUCTURE"] = "BLOCKED_DEPENDENCY"
    blocking_decision_ids: list[str] = Field(default_factory=list)
    dependency_batch_ids: list[str] = Field(default_factory=list)
    mutable_target_count: int = 0
    read_only_dependencies: int = 0
    risk_distribution: dict[str, int] = Field(default_factory=dict)
    validators: list[str] = Field(default_factory=list)
    recommended_order: int = 0
    non_authoritative: bool = True


class M11ReadinessReport(StrictModel):
    batches: list[M11BatchReadiness] = Field(default_factory=list)
    topological_order: list[str] = Field(default_factory=list)
    ready_batch_ids: list[str] = Field(default_factory=list)
    blocked_batch_ids: list[str] = Field(default_factory=list)
    note: str = ("M11 不应 Batch 1 → 17 机械执行：按 dependency + readiness 推进，"
                 "作者决策只阻塞相关 batch")
    read_only: bool = True
    non_authoritative: bool = True


# ---------------------------------------------------------------- helpers
CONFIRMED = "SEMANTIC_CONFIRMED"
FIELD_CONFLICT = "LEGACY_FIELD_CONFLICT"
CONTENT_GAP = "LEGACY_CONTENT_GAP"

CONFLICT_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("turn_conflict", ("TURN",)),
    ("decision_conflict", ("DECISION",)),
    ("payoff_conflict", ("PAYOFF",)),
    ("actor_conflict", ("ACTOR", "DOG_")),
    ("state_binding_conflict", ("STATE", "BINDING", "ASSERTION")),
    ("future_reference_conflict", ("FUTURE", "CANON_LEAK")),
    ("knowledge_conflict", ("KNOW", "KNOWLEDGE")),
    ("resource_conflict", ("RESOURCE", "EQUIPMENT")),
    ("relationship_conflict", ("RELATION",)),
    ("timeline_conflict", ("TIMELINE", "ORDER")),
    ("function_conflict", ("FUNCTION",)),
)
GAP_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("decision_gap", ("DECISION",)),
    ("turn_gap", ("TURN",)),
    ("payoff_gap", ("PAYOFF",)),
    ("information_gap", ("INFORMATION",)),
    ("relationship_gap", ("RELATIONSHIP",)),
    ("progression_gap", ("PROGRESSION",)),
    ("resource_gap", ("RESOURCE", "EQUIPMENT")),
    ("causal_gap", ("CAUSAL", "PREREQUISITE", "ORDER")),
    ("continuity_gap", ("CONTINUITY", "TIMELINE")),
    ("human_design_gap", ("AMBIGUOUS", "HUMAN", "DESIGN")),
)
GAP_REPAIRS: dict[str, tuple[str, ...]] = {
    "representation_gap": ("FIELD_REBIND", "FIELD_REWRITE"),
    "semantic_evidence_gap": ("ADD_CAUSAL_LINK", "FIELD_REBIND"),
    "causal_gap": ("ADD_CAUSAL_LINK",),
    "decision_gap": ("ADD_MISSING_DECISION_EVIDENCE",),
    "turn_gap": ("ADD_MISSING_TURN",),
    "payoff_gap": ("ADD_MISSING_PAYOFF",),
    "information_gap": ("ADD_INFORMATION_EVIDENCE",),
    "relationship_gap": ("ADD_RELATIONSHIP_EVIDENCE",),
    "progression_gap": ("FIELD_REBIND", "ADD_CAUSAL_LINK"),
    "resource_gap": ("ADD_RESOURCE_EVIDENCE",),
    "continuity_gap": ("FIELD_REBIND", "ADD_CAUSAL_LINK"),
    "actual_content_gap": ("CONTENT_REWRITE_REQUIRED",),
    "human_design_gap": ("HUMAN_REVIEW_REQUIRED",),
}
FORBIDDEN_BY_DOMAIN: dict[str, str] = {
    "actor": "actor_presence",
    "knowledge": "character_knowledge",
    "relationship": "relationship_state",
    "progression": "progression_state",
    "map": "map_unlock_state",
    "resource": "resource_amounts",
    "equipment": "equipment_ownership",
    "event": "event_occurrence",
    "rule": "rule_enactment",
}
CONFIRMED_SOURCES: tuple[str, ...] = ("chapter_ir_confirmed", "canon", "story_state",
                                      "author_confirmed")
EVIDENCE_GAP_TAG_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("decision_support_evidence", ("DECISION",)),
    ("turn_support_evidence", ("TURN",)),
    ("payoff_evidence", ("PAYOFF",)),
    ("state_transition_evidence", ("STATE", "TRANSITION", "BINDING")),
    ("information_evidence", ("INFORMATION", "TRUTH", "REVEAL", "KNOW")),
    ("foreshadow_evidence", ("FORESHADOW", "PLANT", "FSMOVE", "FSP_")),
    ("relationship_evidence", ("RELATION", "RSTAGE", "RELARC")),
    ("faction_evidence", ("FACTION", "FARC")),
    ("progression_evidence", ("PROGRESSION", "TRACK", "MILESTONE", "ABILITY")),
    ("resource_evidence", ("RESOURCE", "RFLOW", "SUPPLIES")),
    ("equipment_evidence", ("EQUIPMENT", "GEAR", "ITEM_")),
    ("map_evidence", ("MAPMILE", "MAPEXP", "LOCATION", "LOC_")),
    ("causality_evidence", ("CAUSAL", "PREREQUISITE", "ORDER")),
    ("actor_effect_binding", ("ACTOR", "EFFECT", "DOG")),
)
STATE_DOMAIN_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("relationship", ("RELATION", "RELARC", "RSTAGE")),
    ("progression", ("PROGRESSION", "TRACK", "ABILITY")),
    ("knowledge", ("KNOW", "TRUTH", "INFORMATION")),
    ("resource", ("RESOURCE", "SUPPLIES")),
    ("equipment", ("EQUIPMENT", "GEAR", "ITEM_")),
    ("map", ("MAP", "LOCATION", "LOC_")),
    ("faction", ("FACTION",)),
    ("character", ("CHARACTER", "CHAR_", "DOG")),
)
VALIDATORS_BY_TAG: dict[str, list[str]] = {
    "information_evidence": ["knowledge_boundary_gate", "information_order"],
    "foreshadow_evidence": ["foreshadow_order"],
    "relationship_evidence": ["relationship_continuity"],
    "faction_evidence": ["faction_continuity"],
    "progression_evidence": ["progression_continuity"],
    "resource_evidence": ["resource_continuity"],
    "equipment_evidence": ["equipment_continuity"],
    "map_evidence": ["location_continuity"],
    "decision_support_evidence": ["chapter_function_policy", "decision_actor"],
    "turn_support_evidence": ["turn_evidence"],
    "payoff_evidence": ["payoff_evidence"],
    "state_transition_evidence": ["typed_state_transition"],
    "actor_effect_binding": ["evidence_binding"],
    "causality_evidence": ["causality"],
    "writer_projection_only": ["writer_projection"],
    "other": ["human_review"],
}
STATE_DOMAIN_VALIDATORS: dict[str, list[str]] = {
    "relationship": ["relationship_continuity"],
    "progression": ["progression_continuity"],
    "knowledge": ["knowledge_boundary_gate"],
    "resource": ["resource_continuity"],
    "equipment": ["equipment_continuity"],
    "map": ["location_continuity"],
    "faction": ["faction_continuity"],
    "character": ["evidence_binding"],
    "other": ["human_review"],
}
REPAIR_TYPE_BY_TAG: dict[str, str] = {
    "information_evidence": "ADD_INFORMATION_EVIDENCE",
    "foreshadow_evidence": "ADD_CAUSAL_LINK",
    "relationship_evidence": "ADD_RELATIONSHIP_EVIDENCE",
    "resource_evidence": "ADD_RESOURCE_EVIDENCE",
    "equipment_evidence": "ADD_RESOURCE_EVIDENCE",
    "decision_support_evidence": "ADD_MISSING_DECISION_EVIDENCE",
    "turn_support_evidence": "ADD_MISSING_TURN",
    "payoff_evidence": "ADD_MISSING_PAYOFF",
    "causality_evidence": "ADD_CAUSAL_LINK",
    "writer_projection_only": "FIELD_REWRITE",
    "other": "HUMAN_REVIEW_REQUIRED",
}
CONFLICT_DOMAIN_TAG: dict[str, str] = {
    "turn_conflict": "turn_support_evidence",
    "payoff_conflict": "payoff_evidence",
    "decision_conflict": "decision_support_evidence",
    "actor_conflict": "actor_effect_binding",
    "state_binding_conflict": "state_transition_evidence",
    "future_reference_conflict": "information_evidence",
    "knowledge_conflict": "information_evidence",
    "resource_conflict": "resource_evidence",
    "relationship_conflict": "relationship_evidence",
    "timeline_conflict": "causality_evidence",
    "function_conflict": "writer_projection_only",
    "other_conflict": "causality_evidence",
}


def _sha256_bytes(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()[:16] if path.is_file() else ""


def _sha256_json(payload: Any) -> str:
    return hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True)
                          .encode("utf-8")).hexdigest()[:16]


def _keywords(row: dict[str, Any]) -> list[str]:
    rows: list[str] = []
    for key in ("deterministic_issues", "llm_legacy_field_conflicts", "missing_required_fields",
                "blocked_fields", "legacy_conflicts"):
        value = row.get(key) or []
        if isinstance(value, list):
            rows.extend(str(item).upper() for item in value)
    for key in ("category_reason", "disposition", "chapter_function"):
        value = row.get(key)
        if value:
            rows.append(str(value).upper())
    return rows


def _match(rules: tuple[tuple[str, tuple[str, ...]], ...], tokens: list[str],
           default: str) -> str:
    for subtype, needles in rules:
        if any(any(needle in token for token in tokens) for needle in needles):
            return subtype
    return default


def _rows(value: Any) -> list[dict[str, Any]]:
    """把 legacy / pack 里混合形态（dict / str / list）的列表规范化成 dict 行。"""

    rows: list[dict[str, Any]] = []
    for index, item in enumerate(value or []):
        if isinstance(item, dict):
            rows.append(item)
        else:
            rows.append({"id": f"ITEM_{index:02d}", "title": str(item)[:120]})
    return rows


@dataclass
class WastelandInputs:
    profile: dict[str, Any]
    pack: dict[str, Any]
    story_state: dict[str, Any]
    legacy: dict[str, Any]
    reconciliation: dict[str, Any]
    full_migration: dict[str, Any]
    queue: dict[str, Any]
    m1_gate: dict[str, Any]
    chapters: list[dict[str, Any]] = field(default_factory=list)
    full_rows: dict[str, dict[str, Any]] = field(default_factory=dict)
    queue_items: list[dict[str, Any]] = field(default_factory=list)


class WastelandReconstructionService:
    """M10 服务：读真实磁盘状态 → 派生 reconstruction artifacts（只读 + 不修内容）。"""

    novel_id = "wasteland_001"

    def __init__(self, project_root: Path, *,
                 recon_dir: str = RECON_DIR, planning_root: str = PLANNING_ROOT) -> None:
        self.root = Path(project_root).resolve()
        candidate = Path(recon_dir)
        self.recon_dir = candidate.resolve() if candidate.is_absolute() \
            else (self.root / candidate).resolve()
        self.planning_root = planning_root

    # ---------------------------------------------------------------- load
    def _read_json(self, relative: str) -> dict[str, Any]:
        path = self.root / relative
        return json.loads(path.read_text(encoding="utf-8-sig")) if path.is_file() else {}

    def load(self) -> WastelandInputs:
        legacy = self._read_json(LEGACY_CANDIDATE)
        reconciliation = self._read_json(
            f"{M1B_V2}/WASTELAND_001_CHAPTER_IR_RECONCILIATION_FINAL_V2.json")
        full = self._read_json(f"{FULL_MIGRATION}/WASTELAND_001_CHAPTER_IR_FULL.json")
        queue = self._read_json(f"{M1B_V2}/WASTELAND_001_CHAPTER_IR_REPAIR_QUEUE_V4.json")
        gate = self._read_json(f"{M1B_V2}/WASTELAND_001_M1_FINAL_GATE.json")
        state = self._read_json(STATE_JSON)
        chapters = list(reconciliation.get("chapters") or [])
        full_rows = {str(row.get("chapter_uuid")): row for row in full.get("chapters") or []}
        return WastelandInputs(
            profile=self._read_json(PROFILE_JSON), pack=self._read_json(PACK_JSON),
            story_state=dict(state.get("story_state") or {}), legacy=legacy,
            reconciliation=reconciliation, full_migration=full, queue=queue, m1_gate=gate,
            chapters=chapters, full_rows=full_rows,
            queue_items=list(queue.get("items") or []))

    # ---------------------------------------------------------------- baseline
    def baseline(self, inputs: WastelandInputs | None = None) -> WastelandReconstructionBaseline:
        inputs = inputs or self.load()
        counts: dict[str, int] = {CONFIRMED: 0, FIELD_CONFLICT: 0, CONTENT_GAP: 0}
        for row in inputs.chapters:
            key = str(row.get("category_v4") or "")
            if key in counts:
                counts[key] += 1
        return WastelandReconstructionBaseline(
            canon_digest=_sha256_bytes(self.root / CANON_DB),
            story_state_digest=_sha256_bytes(self.root / STATE_JSON),
            legacy_candidate_digest=_sha256_bytes(self.root / LEGACY_CANDIDATE),
            chapter_ir_digest=_sha256_bytes(
                self.root / f"{FULL_MIGRATION}/WASTELAND_001_CHAPTER_IR_FULL.json"),
            profile_digest=_sha256_bytes(self.root / PROFILE_JSON),
            content_pack_digest=_sha256_bytes(self.root / PACK_JSON),
            route_identity=_sha256_bytes(self.root / STATE_JSON),
            chapter_count=len(inputs.chapters),
            m1_coverage=int((inputs.m1_gate.get("statistics") or {}).get(
                "verified_current_digest_count") or 0),
            queue_counts=counts, m1_gate=dict(inputs.m1_gate.get("gate") or {}))

    # ---------------------------------------------------------------- historical
    def build_historical_story_map(self, inputs: WastelandInputs) -> HistoricalStoryMap:
        records: list[HistoricalChapterRecord] = []
        for row in sorted(inputs.chapters, key=lambda item: item.get("display_number") or 0):
            chapter_id = str(row.get("chapter_uuid") or "")
            full = inputs.full_rows.get(chapter_id, {})
            records.append(HistoricalChapterRecord(
                chapter_id=chapter_id, legacy_label=str(row.get("legacy_label") or ""),
                display_number=int(row.get("display_number") or 0),
                volume=int(row.get("volume") or 0), arc=str(row.get("arc") or ""),
                title=str(row.get("title") or "")[:160],
                chapter_function=str(row.get("chapter_function") or ""),
                classification=str(row.get("category_v4") or ""),
                deterministic_issues=[str(item) for item in
                                      (row.get("deterministic_issues") or [])],
                missing_required_fields=[str(item) for item in
                                         (full.get("missing_required_fields") or [])],
                blocked_fields=[str(item) for item in (full.get("blocked_fields") or [])],
                leg_conflicts=[str(item) for item in (full.get("legacy_conflicts") or [])],
                dog_role=str((full.get("dog") or {}).get("role") or ""),
                primary_transition=dict(row.get("primary_transition") or {}),
                writer_preview_refs=sorted((full.get("compiled_preview") or {}).keys()),
                evidence_refs=[item for item in (chapter_id,
                                                 str(row.get("source_digest") or ""),
                                                 str(row.get("ir_digest") or "")) if item]))
        volumes: list[HistoricalVolumeAlignment] = []
        legacy_volumes = inputs.legacy.get("volumes") or []
        for index in sorted({row.volume for row in records if row.volume}):
            rows = [row for row in records if row.volume == index]
            legacy = legacy_volumes[index - 1] if index - 1 < len(legacy_volumes) else {}
            volumes.append(HistoricalVolumeAlignment(
                volume_id=f"WL_VOL_{index:02d}", index=index,
                legacy_title=str(legacy.get("title") or legacy.get("volume_id") or "")[:200],
                chapter_range=[rows[0].display_number, rows[-1].display_number],
                chapter_count=len(rows),
                confirmed_chapters=len([row for row in rows
                                        if row.classification == CONFIRMED]),
                gap_chapters=len([row for row in rows if row.classification == CONTENT_GAP]),
                conflict_chapters=len([row for row in rows
                                       if row.classification == FIELD_CONFLICT]),
                goals=[str(item) for item in (legacy.get("goal") and [legacy.get("goal")]) or []],
                major_transitions=sorted({str(row.primary_transition.get("to_state") or "")
                                          for row in rows
                                          if row.primary_transition.get("to_state")})[:6],
                evidence_refs=[row.chapter_id for row in rows[:3]]))
        arcs: list[HistoricalArcAlignment] = []
        for volume_index in sorted({row.volume for row in records if row.volume}):
            labels = sorted({row.arc for row in records
                             if row.volume == volume_index and row.arc})
            for label in labels:
                rows = [row for row in records
                        if row.volume == volume_index and row.arc == label]
                anchors = [row.chapter_id for row in rows
                           if row.primary_transition or row.classification == CONFIRMED][:6]
                arcs.append(HistoricalArcAlignment(
                    arc_id=f"WL_V{volume_index:02d}_{label}", volume_index=volume_index,
                    legacy_arc=label, chapter_range=[rows[0].display_number,
                                                     rows[-1].display_number],
                    chapter_count=len(rows),
                    goal=(rows[0].title or label)[:300],
                    opening_state=(rows[0].title or "")[:200],
                    historical_pressure=sorted({issue for row in rows
                                                for issue in row.deterministic_issues})[:6],
                    major_anchors=anchors,
                    decision_chain=[row.chapter_id for row in rows if row.leg_conflicts][:6],
                    turns=[str(row.primary_transition.get("to_state") or "") for row in rows
                           if row.primary_transition.get("to_state")][:6],
                    payoff=[row.chapter_id for row in rows
                            if "PAYOFF" not in " ".join(row.deterministic_issues)][:3],
                    cost=[row.chapter_id for row in rows
                          if "COST" in " ".join(row.deterministic_issues)][:3],
                    ending_state=(rows[-1].title or "")[:200],
                    evidence_refs=[row.chapter_id for row in rows[:3]]))
        counts: dict[str, int] = {}
        for row in records:
            for issue in row.deterministic_issues + row.missing_required_fields:
                counts[issue] = counts.get(issue, 0) + 1
        return HistoricalStoryMap(chapters=records, volumes=volumes, arcs=arcs,
                                  domain_counts=dict(sorted(counts.items())))

    def build_causal_spine(self, story_map: HistoricalStoryMap) -> HistoricalCausalSpine:
        nodes = [arc.arc_id for arc in story_map.arcs]
        edges = [{"from": nodes[index], "to": nodes[index + 1], "relation": "causes"}
                 for index in range(len(nodes) - 1)]
        return HistoricalCausalSpine(
            nodes=nodes, edges=edges,
            major_event_refs=[row.chapter_id for row in story_map.chapters
                              if row.primary_transition][:40])

    def build_open_inventory(self, inputs: WastelandInputs) -> WastelandOpenStoryInventory:
        items: list[OpenStoryItem] = []

        def add(item_id: str, domain: str, statement: str, source: str,
                evidence: list[str], priority: str = "medium") -> None:
            items.append(OpenStoryItem(
                item_id=item_id, domain=domain, statement=statement[:300], source=source,
                historical_evidence=[item for item in evidence if item][:4],
                priority=priority))

        for row in inputs.legacy.get("foreshadows") or []:
            add(str(row.get("id") or ""), "foreshadow",
                f"{row.get('title') or row.get('id')}（status={row.get('status')}）",
                "legacy_representation",
                [str(row.get("planted_in") or ""), str(row.get("payoff_in") or "")], "high")
        for row in inputs.pack.get("foreshadows") or []:
            if str(row.get("status") or "") != "paid":
                add(str(row.get("id") or ""), "foreshadow",
                    str(row.get("title") or row.get("id") or ""), "content_pack",
                    [str(row.get("planted_in") or ""), str(row.get("payoff_in") or "")], "high")
        for row in inputs.pack.get("initial_plots") or []:
            add(str(row.get("id") or ""), "mystery",
                f"{row.get('title') or row.get('id')}（progress={row.get('progress')}）",
                "content_pack", [str(row.get("trigger") or "")], "high")
        for row in inputs.legacy.get("threats") or []:
            add(str(row.get("id") or row.get("title") or ""), "conflict",
                str(row.get("title") or row.get("id") or ""), "legacy_representation",
                [str(row.get("volume") or "")])
        for row in inputs.legacy.get("maps") or []:
            add(str(row.get("id") or ""), "map", str(row.get("title") or row.get("id") or ""),
                "legacy_representation", [str(row.get("stage") or "")])
        for index, row in enumerate(_rows(inputs.legacy.get("dog_arc"))):
            add(f"DOG_{row.get('index') or row.get('id') or len(items)}", "relationship",
                str(row.get("title") or row.get("event") or row.get("id") or ""),
                "legacy_representation", [str(row.get("volume") or "")], "high")
        for row in _rows(inputs.legacy.get("abilities")):
            add(str(row.get("id") or ""), "progression",
                str(row.get("title") or row.get("id") or ""), "legacy_representation", [])
        for row in _rows(inputs.legacy.get("resources")):
            add(str(row.get("id") or row.get("name") or ""), "resource",
                str(row.get("title") or row.get("name") or row.get("id") or ""),
                "legacy_representation", [])
        for node in _rows(((inputs.pack.get("progressions") or [{}])[0].get("nodes"))):
            add(str(node.get("id") or node.get("node_id") or ""), "progression",
                str(node.get("name") or node.get("title") or node.get("id") or ""),
                "content_pack", [str(node.get("requirement") or "")])
        for name, count in self._domain_gap_counts(inputs).items():
            add(f"GAP_{name}", "content_gap", f"{name}: {count} 章待处理",
                "repair_queue_v4", [], "high" if count > 50 else "medium")
        by_domain: dict[str, int] = {}
        for item in items:
            by_domain[item.domain] = by_domain.get(item.domain, 0) + 1
        return WastelandOpenStoryInventory(items=[item for item in items if item.item_id],
                                           by_domain=by_domain)

    def _domain_gap_counts(self, inputs: WastelandInputs) -> dict[str, int]:
        counts: dict[str, int] = {}
        for item in inputs.queue_items:
            if str(item.get("category_v4") or item.get("category") or "") != CONTENT_GAP:
                continue
            subtype = self.classify_gap(item)
            counts[subtype] = counts.get(subtype, 0) + 1
        return dict(sorted(counts.items()))

    # ---------------------------------------------------------------- reclassification
    def classify_conflict(self, item: dict[str, Any]) -> ConflictSubtype:  # type: ignore[valid-type]
        tokens = _keywords(item)
        return _match(CONFLICT_RULES, tokens, "other_conflict")  # type: ignore[return-value]

    def classify_gap(self, item: dict[str, Any]) -> str:
        tokens = _keywords(item)
        function = str(item.get("chapter_function") or "")
        requirements = item.get("function_requirements") or {}
        for subtype, needles in GAP_RULES:
            if any(any(needle in token for token in tokens) for needle in needles):
                if subtype == "turn_gap" and (
                        requirements.get("turn") in (None, "micro_turn", "not_applicable")
                        or function in ("setup", "aftermath", "transition", "exploration")):
                    # micro / N/A 章节缺的是 pivot evidence 绑定，不是真的缺一个 turn
                    return "semantic_evidence_gap"
                return subtype
        if not (item.get("missing_required_fields") or []) \
                and str(item.get("category_reason") or "").strip():
            return "actual_content_gap"
        if str(item.get("category_reason") or "").strip():
            return "continuity_gap"
        return "representation_gap" if not (item.get("missing_required_fields") or []) \
            else "semantic_evidence_gap"

    def allowed_repairs(self, subtype: str) -> list[str]:
        return list(GAP_REPAIRS.get(subtype, ("FIELD_REBIND",)))

    def risk_of(self, subtype: str, item: dict[str, Any], neighbours: set[str]) -> str:
        if subtype == "human_design_gap":
            return "HUMAN_REQUIRED"
        if subtype in ("actual_content_gap", "continuity_gap", "causal_gap"):
            return "HIGH"
        allowed = set(self.allowed_repairs(subtype))
        if allowed <= {"FIELD_REBIND", "FIELD_REWRITE", "RECLASSIFY_FUNCTION"}:
            return "LOW" if str(item.get("chapter_uuid")) not in neighbours else "MEDIUM"
        return "MEDIUM"

    def forbidden_changes(self, record: HistoricalChapterRecord,
                          full_row: dict[str, Any]) -> list[str]:
        """forbidden_changes 只能来自 confirmed evidence（绝不来 legacy prose）。

        只有 classification == SEMANTIC_CONFIRMED（或 LLM AGREE + digest 已校验）的章节
        才提供"绝不能改"的事实域；其余章节返回空列表（M11 必须先重建证据）。
        """

        confirmed = record.classification == CONFIRMED or bool(
            full_row.get("current_digest_verified")) and \
            str(full_row.get("llm_verdict_current") or "").upper() == "AGREE"
        if not confirmed:
            return []
        domains: set[str] = {"event"}
        if record.dog_role or (full_row.get("dog") or {}).get("role"):
            domains.add("actor")
        text = " ".join(record.writer_preview_refs + record.missing_required_fields)
        for domain, token in (("knowledge", "KNOW"), ("relationship", "RELATION"),
                              ("progression", "PROGRESSION"), ("map", "MAP"),
                              ("resource", "RESOURCE"), ("equipment", "EQUIPMENT"),
                              ("rule", "RULE")):
            if token in text.upper():
                domains.add(domain)
        return sorted({FORBIDDEN_BY_DOMAIN[domain] for domain in domains})

    def confirm_sources(self, record: HistoricalChapterRecord,
                        full_row: dict[str, Any]) -> list[str]:
        """forbidden_changes 的证据来源（M11 只允许这些来源约束事实）。"""

        if record.classification == CONFIRMED:
            return ["chapter_ir_confirmed"]
        if full_row.get("current_digest_verified") and \
                str(full_row.get("llm_verdict_current") or "").upper() == "AGREE":
            return ["chapter_ir_confirmed", "author_confirmed"]
        return []

    def classify_evidence_gap_tags(self, item: dict[str, Any],
                                   full_row: dict[str, Any]) -> list[str]:
        """229 semantic_evidence_gap 的多标签细分（允许 multi-label，不猜不存在的证据）。"""

        tokens = _keywords(item)
        tags = [tag for tag, needles in EVIDENCE_GAP_TAG_RULES
                if any(any(needle in token for token in tokens) for needle in needles)]
        if not tags:
            preview = full_row.get("compiled_preview") or {}
            tags = ["writer_projection_only"] if preview else ["other"]
        return sorted(dict.fromkeys(tags))

    def classify_state_domain(self, item: dict[str, Any],
                              record: HistoricalChapterRecord | None = None) -> str:
        tokens = _keywords(item)
        if record is not None:
            transition = record.primary_transition or {}
            tokens = tokens + [str(transition.get("state_key") or "").upper(),
                               str(transition.get("to_state") or "").upper(),
                               str(transition.get("transition_kind") or "").upper()]
            # state_key 语义启发（无实例硬编码；只按通用词域）
            key = str(transition.get("state_key") or "").lower()
            for domain, needles in (("map", ("route", "access", "gate", "zone", "place",
                                             "location", "wall", "region")),
                                    ("relationship", ("relation", "bond", "trust", "dog",
                                                      "companion")),
                                    ("knowledge", ("knowledge", "truth", "archive", "record",
                                                   "publication", "secret")),
                                    ("faction", ("faction", "rule", "status", "order",
                                                 "council")),
                                    ("progression", ("progress", "ability", "level", "tier")),
                                    ("resource", ("resource", "supply", "stock", "currency")),
                                    ("equipment", ("equipment", "item", "gear", "tool"))):
                if any(needle in key for needle in needles):
                    return domain
        for domain, needles in STATE_DOMAIN_RULES:
            if any(any(needle in token for token in tokens) for needle in needles):
                return domain
        return "other"

    def required_validators(self, target: LegacyTargetAlignment) -> list[str]:
        validators: list[str] = []
        for tag in target.domain_tags:
            validators.extend(VALIDATORS_BY_TAG.get(tag, []))
        if target.state_domain:
            validators.extend(STATE_DOMAIN_VALIDATORS.get(target.state_domain, []))
        if target.human_review_required:
            validators.append("human_review")
        defaults = ["chapter_ir_validator", "chapter_function_policy", "canon_consistency",
                    "story_state_boundary", "causality", "m1_semantic_gate"]
        return sorted(dict.fromkeys([*validators, *defaults]))

    def recommended_repair_type(self, target: LegacyTargetAlignment) -> str:
        for tag in target.domain_tags:
            if tag in REPAIR_TYPE_BY_TAG:
                return REPAIR_TYPE_BY_TAG[tag]
        if target.allowed_repair_types:
            return target.allowed_repair_types[0]
        return "FIELD_REBIND"

    # ---------------------------------------------------------------- alignments
    def build_chapter_alignments(self, inputs: WastelandInputs,
                                 story_map: HistoricalStoryMap
                                 ) -> list[LegacyChapterAlignment]:
        rows: list[LegacyChapterAlignment] = []
        for record in story_map.chapters:
            full = inputs.full_rows.get(record.chapter_id, {})
            evidence = [item for item in (record.chapter_id, record.legacy_label)
                        if item]
            rows.append(LegacyChapterAlignment(
                chapter_id=record.chapter_id, legacy_label=record.legacy_label,
                display_number=record.display_number,
                m1_classification=record.classification,
                historical_volume=record.volume,
                historical_arc=f"WL_V{record.volume:02d}_{record.arc}",
                historical_plot_role=record.chapter_function,
                confirmed_source_refs=(list(record.evidence_refs)
                                       if record.classification == CONFIRMED else []),
                domain_refs={
                    "writer_preview": list(record.writer_preview_refs),
                    "primary_transition": sorted(str(key) for key in
                                                 record.primary_transition.keys()),
                    "dog": [record.dog_role] if record.dog_role else []},
                target_fields=sorted(set(record.writer_preview_refs)),
                legacy_fields=sorted(set(record.leg_conflicts)),
                difference_classification=sorted(set(record.deterministic_issues
                                                     + record.missing_required_fields)),
                repairability=("CONFIRMED_NO_REPAIR"
                               if record.classification == CONFIRMED else "M11_REPAIR"),
                forbidden_changes=self.forbidden_changes(record, full),
                evidence=evidence))
        return rows

    def build_target_alignment(self, inputs: WastelandInputs,
                               story_map: HistoricalStoryMap
                               ) -> LegacyTargetAlignmentSet:
        records = {row.chapter_id: row for row in story_map.chapters}
        by_arc: dict[str, list[str]] = {}
        for record in story_map.chapters:
            by_arc.setdefault(f"WL_V{record.volume:02d}_{record.arc}", []).append(
                record.chapter_id)
        targets: list[LegacyTargetAlignment] = []
        for item in inputs.queue_items:
            chapter_id = str(item.get("chapter_uuid") or "")
            record = records.get(chapter_id)
            if record is None:
                continue
            arc_id = f"WL_V{record.volume:02d}_{record.arc}"
            siblings = set(by_arc.get(arc_id, []))
            classification = str(item.get("category_v4") or item.get("category") or "")
            if classification == FIELD_CONFLICT:
                subtype = self.classify_conflict(item)
                gap_subtype, conflict_subtype = None, subtype
                allowed = ["FIELD_REBIND", "FIELD_REWRITE"]
                if subtype == "turn_conflict":
                    allowed = ["ADD_MISSING_TURN", "FIELD_REWRITE"]
                elif subtype == "payoff_conflict":
                    allowed = ["ADD_MISSING_PAYOFF", "FIELD_REWRITE"]
                elif subtype == "decision_conflict":
                    allowed = ["ADD_MISSING_DECISION_EVIDENCE", "FIELD_REWRITE"]
                elif subtype == "function_conflict":
                    allowed = ["RECLASSIFY_FUNCTION"]
                risk = "MEDIUM" if subtype in ("turn_conflict", "payoff_conflict",
                                               "decision_conflict") else "LOW"
            else:
                subtype = self.classify_gap(item)
                gap_subtype, conflict_subtype = subtype, None  # type: ignore[assignment]
                allowed = self.allowed_repairs(subtype)
                risk = self.risk_of(subtype, item, siblings)
            full = inputs.full_rows.get(chapter_id, {})
            ambiguous = [str(item) for item in (full.get("ambiguous_entities") or [])]
            blocked = [str(item) for item in (full.get("blocked_fields") or [])]
            evidence_tags = self.classify_evidence_gap_tags(item, full) \
                if gap_subtype else []
            state_domain = self.classify_state_domain(item, record) \
                if conflict_subtype == "state_binding_conflict" else ""
            if evidence_tags == ["other"]:
                risk = "HUMAN_REQUIRED"
                allowed = ["HUMAN_REVIEW_REQUIRED", *allowed]
            if ambiguous:
                # evidence 无法唯一确定（真歧义）→ 交作者决定，不让 LLM 猜
                risk = "HUMAN_REQUIRED"
                if classification != FIELD_CONFLICT and gap_subtype is None:
                    gap_subtype = "human_design_gap"  # type: ignore[assignment]
                allowed = ["HUMAN_REVIEW_REQUIRED", *allowed]
            elif blocked and risk == "LOW":
                risk = "HIGH"      # 字段被 block：影响连续性，但仍可由 evidence 修
            forbidden = self.forbidden_changes(record, full)
            sources = self.confirm_sources(record, full)
            target = LegacyTargetAlignment(
                primary_issue=(gap_subtype or conflict_subtype or "representation_gap"),
                chapter_id=chapter_id, legacy_label=record.legacy_label,
                current_classification=classification,
                historical_arc=arc_id, historical_volume=record.volume,
                confirmed_facts=[item for item in record.evidence_refs if item],
                target_chapter_function=record.chapter_function,
                target_semantic_fields=sorted(set(record.writer_preview_refs)),
                missing_semantic_fields=list(record.missing_required_fields),
                conflicting_legacy_fields=list(record.leg_conflicts)
                or list(record.deterministic_issues),
                gap_subtype=gap_subtype, conflict_subtype=conflict_subtype,
                evidence_gap_subtypes=evidence_tags, state_domain=state_domain,
                domain_tags=sorted(set(evidence_tags)
                                   | ({state_domain} if state_domain else set())
                                   | ({CONFLICT_DOMAIN_TAG.get(conflict_subtype, "")}
                                      if conflict_subtype else set()) - {""}),
                upstream_dependencies=[chapter_id for chapter_id in
                                       by_arc.get(arc_id, [])[:1]],
                downstream_dependencies=[chapter_id for chapter_id in
                                         by_arc.get(arc_id, [])[-1:]],
                allowed_repair_types=allowed,  # type: ignore[arg-type]
                recommended_repair_type="",
                required_context=["planning_context"
                                  if sources else "confirmed_evidence_reconstruction"],
                forbidden_changes=forbidden, forbidden_change_sources=sources,
                recommended_repair_scope="chapter" if risk in ("LOW", "MEDIUM") else "arc",
                risk=risk,  # type: ignore[arg-type]
                human_review_required=risk == "HUMAN_REQUIRED",
                evidence_refs=list(record.evidence_refs))
            targets.append(target.model_copy(update={
                "recommended_repair_type": self.recommended_repair_type(target),
                "required_validators": self.required_validators(target)}))
        conflict_counts: dict[str, int] = {}
        gap_counts: dict[str, int] = {}
        risk_counts: dict[str, int] = {}
        for target in targets:
            if target.conflict_subtype:
                conflict_counts[target.conflict_subtype] = \
                    conflict_counts.get(target.conflict_subtype, 0) + 1
            if target.gap_subtype:
                gap_counts[target.gap_subtype] = gap_counts.get(target.gap_subtype, 0) + 1
            risk_counts[target.risk] = risk_counts.get(target.risk, 0) + 1
        return LegacyTargetAlignmentSet(
            targets=targets, field_conflict_subtypes=dict(sorted(conflict_counts.items())),
            content_gap_subtypes=dict(sorted(gap_counts.items())),
            risk_counts=dict(sorted(risk_counts.items())))

    # ---------------------------------------------------------------- batches
    def build_batch_plan(self, inputs: WastelandInputs, story_map: HistoricalStoryMap,
                         alignment: LegacyTargetAlignmentSet
                         ) -> WastelandRepairBatchPlan:
        order = {row.chapter_id: row.display_number for row in story_map.chapters}
        by_arc: dict[str, list[LegacyTargetAlignment]] = {}
        for target in alignment.targets:
            by_arc.setdefault(target.historical_arc, []).append(target)
        arcs_sorted = sorted(by_arc, key=lambda arc_id: min(
            order.get(target.chapter_id, 10 ** 6) for target in by_arc[arc_id]))
        batches: list[WastelandRepairBatch] = []
        current: list[str] = []
        current_chapters: list[LegacyTargetAlignment] = []

        def flush() -> None:
            if not current_chapters:
                return
            batch_id = f"REPAIR_BATCH_{len(batches) + 1:02d}"
            risk_rank = {"LOW": 0, "MEDIUM": 1, "HIGH": 2, "HUMAN_REQUIRED": 3}
            risk = max((target.risk for target in current_chapters),
                       key=lambda value: risk_rank[value])
            batches.append(WastelandRepairBatch(
                batch_id=batch_id, volume_refs=sorted({target.historical_volume
                                                       for target in current_chapters}),
                arc_refs=list(current),
                chapter_ids=[target.chapter_id for target in current_chapters],
                legacy_labels=[target.legacy_label for target in current_chapters],
                field_conflict_ids=[target.chapter_id for target in current_chapters
                                    if target.current_classification == FIELD_CONFLICT],
                content_gap_ids=[target.chapter_id for target in current_chapters
                                 if target.current_classification == CONTENT_GAP],
                dependency_batches=[f"REPAIR_BATCH_{len(batches):02d}"] if batches else [],
                confirmed_facts_digest=_sha256_json(
                    [target.confirmed_facts for target in current_chapters]),
                target_alignment_digest=_sha256_json(
                    [target.model_dump(mode="json") for target in current_chapters]),
                allowed_changes=sorted({item for target in current_chapters
                                        for item in target.allowed_repair_types}),
                forbidden_changes=sorted({item for target in current_chapters
                                          for item in target.forbidden_changes}),
                expected_repair_types=sorted({item for target in current_chapters
                                              for item in target.allowed_repair_types}),
                risk=risk,
                human_review_items=[target.chapter_id for target in current_chapters
                                    if target.risk == "HUMAN_REQUIRED"]))

        for arc_id in arcs_sorted:
            current.append(arc_id)
            current_chapters.extend(by_arc[arc_id])
            if len(current_chapters) >= 30 or (len(current_chapters) >= 20
                                               and len(current) >= 2):
                flush()
                current, current_chapters = [], []
        flush()
        # owning / read-only 语义 + 风险分布 + validators（exact coverage gate 的基础）
        arc_index = {arc_id: index for index, arc_id in enumerate(arcs_sorted)}
        owner: dict[str, str] = {}
        updated: list[WastelandRepairBatch] = []
        for batch in batches:
            indices = [arc_index[arc_id] for arc_id in batch.arc_refs]
            neighbours: set[str] = set()
            for index in (min(indices) - 1, max(indices) + 1):
                if 0 <= index < len(arcs_sorted):
                    neighbours.add(arcs_sorted[index])
            read_only = sorted({target.chapter_id for arc_id in neighbours
                                for target in by_arc.get(arc_id, [])}
                               - set(batch.chapter_ids))
            risk_dist: dict[str, int] = {}
            targets = [target for arc_id in batch.arc_refs for target in by_arc[arc_id]]
            for target in targets:
                risk_dist[target.risk] = risk_dist.get(target.risk, 0) + 1
                owner[target.chapter_id] = batch.batch_id
            validators = sorted({item for target in targets
                                 for item in target.required_validators})
            updated.append(batch.model_copy(update={
                "read_only_dependency_chapter_ids": read_only,
                "risk_distribution": dict(sorted(risk_dist.items())),
                "validators": validators, "mutable_target_count": len(batch.chapter_ids)}))
        alignment.targets = [target.model_copy(
            update={"owning_repair_batch_id": owner.get(target.chapter_id, "")})
            for target in alignment.targets]
        _ = inputs
        return WastelandRepairBatchPlan(batches=updated)

    def batch_dependency_order(self, plan: WastelandRepairBatchPlan) -> tuple[bool, list[str]]:
        """batch dependency 必须是 DAG；返回 (is_dag, topological_order)。"""

        graph = {batch.batch_id: list(batch.dependency_batches) for batch in plan.batches}
        order: list[str] = []
        visiting: set[str] = set()
        done: set[str] = set()
        cyclic = False

        def visit(node: str) -> None:
            nonlocal cyclic
            if node in done:
                return
            if node in visiting:
                cyclic = True
                return
            visiting.add(node)
            for dependency in graph.get(node, []):
                if dependency in graph:
                    visit(dependency)
            visiting.discard(node)
            done.add(node)
            order.append(node)

        for node in graph:
            visit(node)
        return (not cyclic), order

    def build_readiness(self, plan: WastelandRepairBatchPlan,
                        order: list[str],
                        decisions: WastelandAuthorDecisionQueue,
                        target_set: LegacyTargetAlignmentSet) -> M11ReadinessReport:
        decision_by_arc: dict[str, list[str]] = {}
        for item in decisions.items:
            for arc_id in item.affected_arcs:
                decision_by_arc.setdefault(arc_id, []).append(item.decision_id)
        by_owner = {target.owning_repair_batch_id: target
                    for target in target_set.targets if target.owning_repair_batch_id}
        completed: set[str] = set()
        rows: list[M11BatchReadiness] = []
        blocked: set[str] = set()
        for position, batch_id in enumerate(order, start=1):
            batch = next(item for item in plan.batches if item.batch_id == batch_id)
            blocking_decisions = sorted({decision for arc_id in batch.arc_refs
                                         for decision in decision_by_arc.get(arc_id, [])})
            pending_dependencies = [item for item in batch.dependency_batches
                                    if item not in completed]
            structure_blocked = any(
                target.risk == "HUMAN_REQUIRED" and not blocking_decisions
                for target in target_set.targets
                if target.owning_repair_batch_id == batch_id)
            if blocking_decisions:
                status = "BLOCKED_AUTHOR_DECISION"
            elif structure_blocked:
                status = "BLOCKED_STRUCTURE"
            elif pending_dependencies:
                status = "BLOCKED_DEPENDENCY"
            else:
                status = "READY"
                completed.add(batch_id)
            if status != "READY":
                blocked.add(batch_id)
            rows.append(M11BatchReadiness(
                batch_id=batch_id, status=status,
                blocking_decision_ids=blocking_decisions,
                dependency_batch_ids=list(batch.dependency_batches),
                mutable_target_count=batch.mutable_target_count,
                read_only_dependencies=len(batch.read_only_dependency_chapter_ids),
                risk_distribution=batch.risk_distribution, validators=batch.validators,
                recommended_order=position))
        _ = by_owner
        return M11ReadinessReport(
            batches=rows, topological_order=list(order),
            ready_batch_ids=[row.batch_id for row in rows if row.status == "READY"],
            blocked_batch_ids=sorted(blocked))

    def build_author_decisions(self, story_map: HistoricalStoryMap,
                               alignment: LegacyTargetAlignmentSet
                               ) -> WastelandAuthorDecisionQueue:
        records = {row.chapter_id: row for row in story_map.chapters}
        items: list[WastelandAuthorDecision] = []
        for target in alignment.targets:
            if target.risk != "HUMAN_REQUIRED":
                continue
            record = records.get(target.chapter_id)
            items.append(WastelandAuthorDecision(
                decision_id=f"DECISION_{target.legacy_label or target.chapter_id}",
                question=(f"{target.legacy_label} 的 "
                          f"{target.gap_subtype or target.conflict_subtype} 无法从 evidence 唯一确定："
                          "保留旧表达，还是按历史结构重写语义？"),
                affected_chapters=[target.chapter_id],
                affected_arcs=[target.historical_arc],
                evidence=list(target.evidence_refs),
                option_a="按历史 evidence 重写该章语义表达（不改 happened fact）",
                option_b="保留旧表达并在后续章节补 evidence",
                tradeoff="A 改动集中在单章；B 影响后续连续性",
                blocking_scope=[target.historical_arc],
                recommended_default=(f"先修 {record.legacy_label if record else target.chapter_id}"
                                     " 的 representation，再评估 arc 连续性"),
                recommended_default_is_authoritative=False))
        return WastelandAuthorDecisionQueue(items=items)

    # ---------------------------------------------------------------- future planning
    def build_future_plan_payload(self, inputs: WastelandInputs,
                                  inventory: WastelandOpenStoryInventory) -> dict[str, Any]:
        pack = inputs.pack
        profile = inputs.profile
        characters = []
        for key, seed in (pack.get("initial_characters") or {}).items():
            characters.append({"character_id": f"CHAR_{str(key).upper()}",
                               "display_name": str(seed.get("name") or seed.get("display_name")
                                                   or key)[:60],
                               "entity_ref": str(seed.get("entity_ref") or ""),
                               "external_goal": str(seed.get("goal") or "")[:300],
                               "provenance": "supplied"})
        if not any(str(item["display_name"]).startswith("阿灰") for item in characters):
            characters.insert(1, {"character_id": "CHAR_DOG", "display_name": "阿灰",
                                  "external_goal": "跟着韩彻走完这条路",
                                  "provenance": "supplied"})
        locations = [{"location_id": f"LOC_{str(key).upper()}",
                      "display_name": str(value.get("name") or key)[:60],
                      "story_function": str(value.get("role") or "")[:80],
                      "provenance": "supplied"}
                     for key, value in (pack.get("initial_locations") or {}).items()]
        factions = [{"faction_id": f"FACTION_{str(key).upper()}",
                     "display_name": str(value.get("name") or key)[:60],
                     "provenance": "supplied"}
                    for key, value in (pack.get("initial_factions") or {}).items()]
        remaining_words, remaining_chapters = self.remaining_scale(inputs)
        required_arcs = max(1, -(-remaining_chapters // 6))
        required_volumes = max(1, -(-required_arcs // 5))
        top = [item for item in inventory.items if item.priority == "high"]
        domain_rows: list[OpenStoryItem] = []
        seen_domains: set[str] = set()
        for item in inventory.items:
            if item.domain in seen_domains or item.domain == "content_gap":
                continue
            seen_domains.add(item.domain)
            domain_rows.append(item)
        macro_nodes = max(4, required_arcs * 2 - len(top) - len(domain_rows))
        planned = top + domain_rows
        nodes = []
        edges = []
        for index in range(len(planned) + macro_nodes):
            item = planned[index] if index < len(planned) else None
            node_id = f"NODE_WL_FUTURE_{index:02d}"
            purpose = (item.statement or item.item_id) if item is not None \
                else f"宏观推进 {index - len(planned) + 1}：{['势力宏冲突', '地图前沿', '成长突破', '终局方向'][(index - len(planned)) % 4]}"
            nodes.append({"node_id": node_id, "purpose": purpose[:300],
                          "conflict": (item.domain if item is not None else "macro"),
                          "state_change": "局面推进",
                          "participants": [characters[0]["character_id"]] if characters else [],
                          "location_id": locations[0]["location_id"] if locations else "",
                          "importance": "core" if index < 4 else "major",
                          "must_happen": index < 4,
                          "prerequisites": [] if index == 0
                          else [f"NODE_WL_FUTURE_{index - 1:02d}"],
                          "provenance": "generated"})
            if index:
                edges.append({"from_node_id": f"NODE_WL_FUTURE_{index - 1:02d}",
                              "to_node_id": node_id, "relation": "causes"})
        # 宏观结构：每个计划卷一个 macro conflict stage（hard boundary）+ 成长 / 关系 / 势力 / 地图
        conflict_chains = []
        per_volume = max(1, len(nodes) // required_volumes)
        for index in range(required_volumes):
            anchor = f"NODE_WL_FUTURE_{min(index * per_volume, len(nodes) - 1):02d}"
            conflict_chains.append({
                "conflict_id": f"CONFLICT_WL_V{index + 1:02d}",
                "title": f"第 {index + 1} 阶段宏观冲突",
                "related_node_ids": [anchor],
                "stages": [
                    {"stage_id": f"CSTAGE_WL_V{index + 1:02d}_MACRO",
                     "conflict_id": f"CONFLICT_WL_V{index + 1:02d}", "scope": "macro",
                     "trigger_node_id": anchor, "stakes": "宏观压力升级",
                     "provenance": "generated"},
                    {"stage_id": f"CSTAGE_WL_V{index + 1:02d}_VOLUME",
                     "conflict_id": f"CONFLICT_WL_V{index + 1:02d}", "scope": "volume",
                     "trigger_node_id": f"NODE_WL_FUTURE_{min(index * per_volume + 1, len(nodes) - 1):02d}",
                     "constraint_change": "约束加码", "provenance": "generated"}],
                "provenance": "generated"})
        character_arcs = [
            {"arc_id": "CARCH_WL_HAN", "character_id": characters[0]["character_id"],
             "start_state": "独自求生", "end_state": "承担群体责任",
             "major_choices": [{"node_id": f"NODE_WL_FUTURE_{min(index * 3, len(nodes) - 1):02d}",
                                "choice": "选择承担", "provenance": "generated"}
                               for index in range(3)],
             "provenance": "generated"}]
        if len(characters) > 1:
            character_arcs.append({
                "arc_id": "CARCH_WL_DOG", "character_id": characters[1]["character_id"],
                "start_state": "跟着走", "end_state": "自主选择同行",
                "major_choices": [{"node_id": f"NODE_WL_FUTURE_{min(len(nodes) - 1, 2):02d}",
                                   "choice": "自己决定留下", "provenance": "generated"}],
                "provenance": "generated"})
        relationship_arcs = [{
            "arc_id": "RELARC_WL_HAN_DOG",
            "participants": [characters[0]["character_id"], characters[1]["character_id"]],
            "start_state": "相依为命", "relationship_change": "从依赖到彼此独立",
            "stages": [{"stage_id": "RSTAGE_WL_A", "label": "并肩",
                        "trigger_node_id": f"NODE_WL_FUTURE_{min(2, len(nodes) - 1):02d}",
                        "state": "并肩行动"},
                       {"stage_id": "RSTAGE_WL_B", "label": "分离风险",
                        "trigger_node_id": f"NODE_WL_FUTURE_{min(len(nodes) // 2, len(nodes) - 1):02d}",
                        "state": "分离风险", "irreversible": True},
                       {"stage_id": "RSTAGE_WL_C", "label": "重逢",
                        "trigger_node_id": f"NODE_WL_FUTURE_{len(nodes) - 1:02d}",
                        "state": "自主同行"}],
            "irreversible_node": f"NODE_WL_FUTURE_{min(len(nodes) // 2, len(nodes) - 1):02d}",
            "provenance": "generated"}]
        faction_arcs = [{"arc_id": f"FARC_WL_{index:02d}",
                         "faction_id": row["faction_id"], "start_state": "观察",
                         "end_state": "被迫重新结盟",
                         "stages": [{"stage_id": f"FSTAGE_WL_{index:02d}_A", "label": "施压",
                                     "strategy": "压缩拾荒路线",
                                     "trigger_node_id": f"NODE_WL_FUTURE_{min(index * 2 + 1, len(nodes) - 1):02d}",
                                     "expected_state": "压力上升"}],
                         "provenance": "generated"} for index, row in enumerate(factions)]
        map_expansions = [{
            "expansion_id": "MAPEXP_WL_FUTURE", "scope_note": "剩余地图开放",
            "provenance": "generated",
            "milestones": [{"milestone_id": f"MAPMILE_WL_{index + 1:02d}",
                            "location_ref": row["location_id"], "from_stage": "unknown",
                            "to_stage": "controlled" if index % 2 == 0 else "reachable",
                            "trigger_node_id": f"NODE_WL_FUTURE_{min(index, len(nodes) - 1):02d}",
                            "provenance": "generated"}
                           for index, row in enumerate(locations)]}]
        progression_tracks = [{"track_id": "TRACK_WL_ETHER", "category": "ability",
                               "label": "以太感应", "start_state": "初醒",
                               "milestones": [
                                   {"milestone_id": f"TRACKMILE_WL_{index:02d}",
                                    "label": f"阶段 {index + 1}", "cost": "以太代价",
                                    "node_id": f"NODE_WL_FUTURE_{min(index * 3 + 2, len(nodes) - 1):02d}",
                                    "provenance": "generated"} for index in range(3)],
                               "provenance": "generated"}]
        information_arcs = [{
            "arc_id": "INFO_WL_FUTURE",
            "truths": [{"truth_id": "TRUTH_WL_TIDE", "statement": "以太潮的真正来源",
                        "character_knows": [characters[0]["character_id"]],
                        "provenance": "generated"}],
            "moves": [
                {"move_id": "IMOVE_WL_PLANT", "truth_id": "TRUTH_WL_TIDE",
                 "move_type": "plant", "node_id": "NODE_WL_FUTURE_00",
                 "holder_ids": [characters[0]["character_id"]], "provenance": "generated"},
                {"move_id": "IMOVE_WL_REVEAL", "truth_id": "TRUTH_WL_TIDE",
                 "move_type": "reveal", "node_id": f"NODE_WL_FUTURE_{len(nodes) - 1:02d}",
                 "holder_ids": [characters[0]["character_id"]], "provenance": "generated"}],
            "provenance": "generated"}]
        reward_plans = [{"reward_plan_id": "REWARD_WL_FUTURE", "provenance": "generated",
                         "events": [{"reward_id": f"REWARD_WL_{index:02d}",
                                     "reward_type": "status",
                                     "magnitude": "climax" if index == required_volumes - 1
                                     else "major",
                                     "scope": "volume",
                                     "trigger_node_id": f"NODE_WL_FUTURE_{min(index * per_volume, len(nodes) - 1):02d}",
                                     "recipient_ref": characters[0]["character_id"],
                                     "provenance": "generated"}
                                    for index in range(required_volumes)]}]
        autonomous_actions = [{"action_id": f"ACT_WL_{index:02d}",
                               "actor_ref": row["faction_id"], "goal": "争夺以太资源",
                               "trigger_ref": f"NODE_WL_FUTURE_{min(index + 1, len(nodes) - 1):02d}",
                               "location_ref": locations[min(index, len(locations) - 1)]["location_id"]
                               if locations else "",
                               "target_refs": [characters[0]["character_id"]],
                               "planned_action": "封锁路线",
                               "expected_consequence": "资源压力上升",
                               "visibility": "faction_internal", "provenance": "generated"}
                              for index, row in enumerate(factions)]
        foreshadows = []
        for index, row in enumerate(pack.get("foreshadows") or []):
            plant = f"NODE_WL_FUTURE_{min(index, max(len(nodes) - 1, 0)):02d}" if nodes else ""
            payoff = f"NODE_WL_FUTURE_{min(index + 2, max(len(nodes) - 1, 0)):02d}" if nodes else ""
            foreshadows.append({
                "foreshadow_id": f"FSP_WL_{index:02d}", "subject": str(row.get("title") or ""),
                "intended_payoff": str(row.get("payoff_condition") or "")[:300],
                "moves": ([{"move_id": f"FSMOVE_WL_{index:02d}_PLANT", "move_type": "plant",
                            "node_id": plant, "provenance": "generated"}]
                          + [{"move_id": f"FSMOVE_WL_{index:02d}_PAYOFF",
                              "move_type": "payoff", "node_id": payoff,
                              "provenance": "generated"}] if payoff else []),
                "plant_node_id": plant, "payoff_node_id": payoff, "provenance": "generated"})
        return {
            "planning_id": "PLAN_WASTELAND_001", "novel_id": self.novel_id,
            "title": str(profile.get("title") or "WASTELAND_001"),
            "intent": {"intent_id": "INTENT_WL_001", "novel_id": self.novel_id,
                       "target_words": 2_000_000, "provenance": "supplied"},
            "theme": {"theme_id": "THEME_WL_001",
                      "dramatic_question": str((profile.get("themes") or ["能不能守住"])[0]),
                      "final_answer_direction": "守住但付出代价",
                      "provenance": "supplied"},
            "world": {"world_id": "WORLD_WL_001", "economy": "拾荒与以太",
                      "provenance": "supplied",
                      "world_rules": [{"rule_id": "RULE_WL_ETHERTIDE",
                                       "rule_type": "hard_rule",
                                       "statement": "以太潮会改变废墟的可进入性",
                                       "scope": "全域", "provenance": "supplied"}]},
            "characters": characters, "factions": factions, "locations": locations,
            "plot_nodes": nodes,
            "spine": {"spine_id": "SPINE_WL_FUTURE", "novel_id": self.novel_id,
                      "nodes": [item["node_id"] for item in nodes], "edges": edges,
                      "entry_node_ids": [nodes[0]["node_id"]] if nodes else [],
                      "terminal_node_ids": [nodes[-1]["node_id"]] if nodes else [],
                      "provenance": "generated"},
            "foreshadow_plans": foreshadows,
            "conflict_chains": conflict_chains, "character_arcs": character_arcs,
            "relationship_arcs": relationship_arcs, "faction_arcs": faction_arcs,
            "map_expansions": map_expansions, "progression_tracks": progression_tracks,
            "information_arcs": information_arcs, "reward_plans": reward_plans,
            "autonomous_actions": autonomous_actions,
        }

    def future_spine_projection(self, payload: dict[str, Any]) -> dict[str, Any]:
        """在 formal Planning revision 上跑 M8A compile，得到未来 Volume / Arc target。"""

        plan = validate_planning_ir(payload)
        candidate = OutlineCompiler().compile(plan, revision_id="PREV_WL_M10_FUTURE_1",
                                              scope=CompilationScope(kind="full_book"))
        return {"source_revision": "PREV_WL_M10_FUTURE_1",
                "volume_targets": [item.model_dump(mode="json")
                                   for item in candidate.volume_plans],
                "arc_targets": [item.model_dump(mode="json") for item in candidate.arc_plans],
                "plan_budget": candidate.plan_budget.model_dump(mode="json"),
                "findings": [item.code for item in candidate.validation_findings],
                "read_only": True, "non_authoritative": True}

    # ---------------------------------------------------------------- future full-book
    def remaining_scale(self, inputs: WastelandInputs) -> tuple[int, int]:
        """剩余目标词数 / 估算章节数（历史按 570 章 × 3,000 字估算）。"""

        historical_words = len(inputs.chapters) * 3_000
        remaining_words = max(0, 2_000_000 - historical_words)
        return remaining_words, max(24, remaining_words // 3_000)

    def build_future_full_book_spine(self, inputs: WastelandInputs,
                                     inventory: WastelandOpenStoryInventory,
                                     decisions: WastelandAuthorDecisionQueue,
                                     payload: dict[str, Any],
                                     projection: dict[str, Any],
                                     baseline: WastelandReconstructionBaseline
                                     ) -> tuple[FullBookFutureSpine, dict[str, Any]]:
        """整本剩余小说的粗骨架：远期粗 / 近期细，且每个 open item 有明确去向。"""

        remaining_words, remaining_chapters = self.remaining_scale(inputs)
        required_arcs = max(1, -(-remaining_chapters // 6))
        required_volumes = max(1, -(-required_arcs // 5))
        nodes = payload["plot_nodes"]
        node_ids = [item["node_id"] for item in nodes]
        volumes = projection["volume_targets"]
        arcs = projection["arc_targets"]
        decision_arcs = {arc for item in decisions.items for arc in item.affected_arcs}
        dispositions: list[FutureItemDisposition] = []
        for index, item in enumerate(inventory.items):
            if item.domain == "content_gap" and decision_arcs:
                disposition: FutureDisposition = "author_decision_required"
                anchors: list[str] = []
            elif item.domain == "content_gap":
                disposition = "deferred"
                anchors = []
            elif index < len(node_ids):
                disposition = "scheduled"
                anchors = [node_ids[index]]
            elif item.priority == "high":
                disposition = "terminal_resolution"
                anchors = [node_ids[-1]] if node_ids else []
            else:
                disposition = "intentionally_unresolved"
                anchors = []
            dispositions.append(FutureItemDisposition(
                item_id=item.item_id, domain=item.domain, disposition=disposition,
                anchor_node_ids=anchors, anchor_volume_ids=[],
                reason={"scheduled": "已排入 future PlotNode",
                        "deferred": "M11 完成后重新评估",
                        "intentionally_unresolved": "保留为长期开放压力",
                        "terminal_resolution": "指向终局方向节点",
                        "author_decision_required": "见 AuthorDecisionQueue"}[disposition]))
        undisposed = sorted({item.item_id for item in inventory.items}
                            - {row.item_id for row in dispositions})
        detail_levels = {}
        for index, volume in enumerate(volumes):
            detail_levels[volume["volume_id"]] = "volume" if index == 0 else "spine"
        for index, arc in enumerate(arcs):
            if index < len(volumes) * 2 and index < 2:
                detail_levels[arc["arc_id"]] = "arc"
            else:
                detail_levels[arc["arc_id"]] = "volume"
        route_review = bool(required_volumes > len(volumes)) or bool(required_arcs > len(arcs))
        findings: list[ReconstructionFinding] = []
        if route_review:
            findings.append(ReconstructionFinding(
                code="AUTHOR_ROUTE_REVIEW_REQUIRED", severity="WARNING",
                message="现有 route / 结构不足以支撑剩余目标规模，需要作者复核（不自动换线）",
                evidence={"required_volumes": required_volumes, "planned_volumes": len(volumes),
                          "required_arcs": required_arcs, "planned_arcs": len(arcs)},
                recommended_action="作者确认是否扩展结构或接受更短篇幅"))
        if undisposed:
            findings.append(ReconstructionFinding(
                code="OPEN_ITEM_SILENTLY_LOST", severity="ERROR",
                message="有 open story item 没有 future disposition",
                related_ids=undisposed[:10],
                recommended_action="为每一项指定 scheduled/deferred/… 去向"))
        spine = FullBookFutureSpine(
            source_revision=baseline.planning_revision or "PREV_WL_M10_FUTURE_1",
            remaining_target_words=remaining_words,
            remaining_estimate_chapters=remaining_chapters,
            plan_node_count=len(nodes), major_node_ids=[item["node_id"] for item in nodes
                                                         if item.get("must_happen")],
            terminal_direction_node_id=node_ids[-1] if node_ids else "",
            volume_count=len(volumes), arc_count=len(arcs), detail_levels=detail_levels,
            item_dispositions=dispositions, undisposed_item_ids=undisposed,
            conflict_escalation_chains=[item["conflict_id"]
                                        for item in payload.get("conflict_chains") or []],
            character_arc_count=len(payload.get("character_arcs") or []),
            relationship_arc_count=len(payload.get("relationship_arcs") or []),
            faction_arc_count=len(payload.get("faction_arcs") or []),
            map_expansion_count=len(payload.get("map_expansions") or []),
            progression_track_count=len(payload.get("progression_tracks") or []),
            information_arc_count=len(payload.get("information_arcs") or []),
            foreshadow_path_count=len(payload.get("foreshadow_plans") or []),
            reward_event_count=len([event for row in payload.get("reward_plans") or []
                                    for event in row.get("events") or []]),
            route_identity=baseline.route_identity, route_review_required=route_review)
        return spine, {"required_volumes": required_volumes, "required_arcs": required_arcs,
                       "findings": findings}

    def build_volume_directions(self, payload: dict[str, Any],
                                projection: dict[str, Any]) -> list[FutureVolumeDirection]:
        nodes = payload["plot_nodes"]
        rows: list[FutureVolumeDirection] = []
        volumes = projection["volume_targets"]
        for index, volume in enumerate(volumes):
            anchors = list(volume.get("major_nodes") or [])
            rows.append(FutureVolumeDirection(
                volume_id=volume["volume_id"], index=volume.get("index") or index + 1,
                detail_level="volume" if index == 0 else "spine",
                volume_goal=str(volume.get("volume_goal") or "")[:300],
                macro_pressure=str(volume.get("major_conflict") or "")[:300],
                major_conflict=str(volume.get("major_conflict") or "")[:300],
                major_node_anchors=anchors,
                character_arc_movement=str(volume.get("character_arc_stage") or "")[:200],
                relationship_movement=str(volume.get("faction_state") or "")[:200],
                faction_movement=str(volume.get("faction_state") or "")[:200],
                map_expansion=list(volume.get("location_expansion") or []),
                progression_direction=str(volume.get("progression_goal") or "")[:200],
                information_obligation=[str(volume.get("information_goal") or "")][:1],
                foreshadow_obligation=[str(volume.get("next_volume_pressure") or "")][:1],
                major_payoff=str(volume.get("climax") or "")[:200],
                ending_pressure=str(volume.get("next_volume_pressure") or "")[:300]))
        _ = nodes
        return rows

    def build_runway_report(self, inputs: WastelandInputs,
                            payload: dict[str, Any],
                            spine: FullBookFutureSpine,
                            meta: dict[str, Any]) -> StructuralRunwayReport:
        """§4/§50：告诉作者"缺的是哪一部分 runway"，不强制 STRUCTURE_TOO_THIN 消失。"""

        required_arcs = max(1, meta["required_arcs"])
        required = {"map": -(-required_arcs // 5), "faction": -(-required_arcs // 4),
                    "progression": -(-required_arcs // 5), "mystery": -(-required_arcs // 6),
                    "relationship": -(-required_arcs // 6), "conflict": -(-required_arcs // 4),
                    "information": -(-required_arcs // 6), "foreshadow": -(-required_arcs // 6),
                    "resource": -(-required_arcs // 6), "character": -(-required_arcs // 4)}
        available = {
            "map": spine.map_expansion_count, "faction": spine.faction_arc_count,
            "progression": spine.progression_track_count,
            "mystery": len([item for item in spine.item_dispositions
                            if item.domain == "mystery"]),
            "relationship": spine.relationship_arc_count,
            "conflict": len(spine.conflict_escalation_chains),
            "information": spine.information_arc_count,
            "foreshadow": spine.foreshadow_path_count,
            "resource": len(payload.get("resource_flows") or []),
            "character": spine.character_arc_count}
        runways: list[StructuralRunway] = []
        insufficient: list[str] = []
        for runway, need in required.items():
            have = available.get(runway, 0)
            verdict = "sufficient" if have >= need else "insufficient"
            if verdict == "insufficient":
                insufficient.append(runway)
            runways.append(StructuralRunway(
                runway=runway, available_units=have, required_units=need, verdict=verdict,
                evidence=[f"{runway}: available={have}", f"required={need}"],
                note="" if verdict == "sufficient" else f"{runway} runway insufficient"))
        _ = inputs
        report = StructuralRunwayReport(
            remaining_target_words=spine.remaining_target_words,
            remaining_estimate_chapters=spine.remaining_estimate_chapters,
            runways=runways, insufficient_runways=sorted(insufficient),
            structure_too_thin=bool(insufficient),
            findings=[ReconstructionFinding(
                code="STRUCTURE_TOO_THIN_FOR_REMAINING_TARGET",
                severity="WARNING" if insufficient else "INFO",
                message=(f"剩余目标需要 {spine.remaining_estimate_chapters} 章结构；"
                         f"不足的 runway：{', '.join(sorted(insufficient)) or 'none'}"),
                evidence={"insufficient_runways": sorted(insufficient)},
                recommended_action="按 runway 明细补结构（不自动注水）")])
        if spine.route_review_required:
            report.findings.extend([item for item in meta["findings"]])
        return report

    def promote_future_plan(self, payload: dict[str, Any], *,
                            revision_id: str = "PREV_WL_M10_FUTURE_1") -> str:
        """future Planning 走正式 repository（immutable revision；已存在则复用）。"""

        repo = PlanningRepository(self.root, self.novel_id, root=self.planning_root)
        if not repo.exists(revision_id):
            repo.create(validate_planning_ir(payload), revision_id=revision_id,
                        status="proposed", note="M10 top-down reconstruction future planning")
        return revision_id

    def planning_revision_id(self) -> str:
        repo = PlanningRepository(self.root, self.novel_id, root=self.planning_root)
        head = repo.resolve_branch_head()
        return head.revision_id if head is not None else ""

    # ---------------------------------------------------------------- run / write
    def write(self, artifacts: dict[str, Any]) -> dict[str, str]:
        self.recon_dir.mkdir(parents=True, exist_ok=True)
        written: dict[str, str] = {}
        for name, payload in artifacts.items():
            path = self.recon_dir / name
            body = json.dumps(payload, ensure_ascii=False, indent=1) + "\n"
            path.write_text(body, encoding="utf-8", newline="\n")
            try:
                written[name] = str(path.relative_to(self.root)).replace("\\", "/")
            except ValueError:
                written[name] = str(path).replace("\\", "/")
        return written

    def run(self) -> dict[str, Any]:
        inputs = self.load()
        before = self.baseline(inputs)
        story_map = self.build_historical_story_map(inputs)
        spine = self.build_causal_spine(story_map)
        inventory = self.build_open_inventory(inputs)
        alignments = self.build_chapter_alignments(inputs, story_map)
        target_set = self.build_target_alignment(inputs, story_map)
        handoff = self.build_handoff(inputs, story_map, inventory, before)
        batches = self.build_batch_plan(inputs, story_map, target_set)
        decisions = self.build_author_decisions(story_map, target_set)
        future_payload = self.build_future_plan_payload(inputs, inventory)
        future_projection = self.future_spine_projection(future_payload)
        future_revision = self.promote_future_plan(future_payload)
        full_spine, spine_meta = self.build_future_full_book_spine(
            inputs, inventory, decisions, future_payload, future_projection, before)
        volume_directions = self.build_volume_directions(future_payload, future_projection)
        runway = self.build_runway_report(inputs, future_payload, full_spine, spine_meta)
        dag_ok, topo_order = self.batch_dependency_order(batches)
        readiness = self.build_readiness(batches, topo_order, decisions, target_set)
        after = self.baseline(inputs)
        gate = self.build_final_gate(inputs, story_map, target_set, batches,
                                     before, after, dag_ok, runway, full_spine)
        artifacts = {
            "BASELINE.json": before.model_dump(mode="json"),
            "HISTORICAL_STORY_MAP.json": story_map.model_dump(mode="json"),
            "HISTORICAL_CAUSAL_SPINE.json": spine.model_dump(mode="json"),
            "STORY_HANDOFF_POINT.json": handoff.model_dump(mode="json"),
            "OPEN_STORY_INVENTORY.json": inventory.model_dump(mode="json"),
            "HISTORICAL_VOLUME_ALIGNMENT.json": [item.model_dump(mode="json")
                                                 for item in story_map.volumes],
            "HISTORICAL_ARC_ALIGNMENT.json": [item.model_dump(mode="json")
                                              for item in story_map.arcs],
            "LEGACY_CHAPTER_ALIGNMENT.json": [item.model_dump(mode="json")
                                              for item in alignments],
            "LEGACY_TARGET_ALIGNMENT.json": target_set.model_dump(mode="json"),
            "REPAIR_QUEUE_RECLASSIFIED.json": {
                "field_conflict_subtypes": target_set.field_conflict_subtypes,
                "content_gap_subtypes": target_set.content_gap_subtypes,
                "risk_counts": target_set.risk_counts,
                "counts_preserved": before.queue_counts},
            "M11_BATCH_PLAN.json": batches.model_dump(mode="json"),
            "M11_READINESS_REPORT.json": readiness.model_dump(mode="json"),
            "AUTHOR_DECISION_QUEUE.json": decisions.model_dump(mode="json"),
            "FULL_BOOK_FUTURE_SPINE.json": full_spine.model_dump(mode="json"),
            "FUTURE_VOLUME_DIRECTION.json": [item.model_dump(mode="json")
                                             for item in volume_directions],
            "STRUCTURAL_RUNWAY_REPORT.json": runway.model_dump(mode="json"),
            "WASTELAND_FUTURE_PLANNING_REF.json": {
                "planning_revision": future_revision,
                "planning_head_after": self.planning_revision_id(),
                "read_only": True, "non_authoritative": False},
            "FUTURE_STORY_SPINE_PROJECTION.json": future_projection,
            "M10_FINAL_GATE.json": gate.model_dump(mode="json"),
        }
        written = self.write(artifacts)
        return {"baseline": before, "gate": gate, "written": written,
                "batches": len(batches.batches), "decisions": len(decisions.items),
                "targets": len(target_set.targets), "readiness": readiness,
                "future_spine": full_spine, "runway": runway,
                "topological_order": topo_order}

    def build_handoff(self, inputs: WastelandInputs, story_map: HistoricalStoryMap,
                      inventory: WastelandOpenStoryInventory,
                      baseline: WastelandReconstructionBaseline) -> StoryHandoffPoint:
        state = inputs.story_state
        last = max(story_map.chapters,
                   key=lambda row: row.display_number, default=None)
        open_items = inventory.items
        return StoryHandoffPoint(
            last_happened_anchor=last.chapter_id if last else "",
            last_happened_label=last.legacy_label if last else "",
            route_identity=baseline.route_identity,
            current_character_state=self._summarize(state.get("characters")),
            current_relationship_state=self._summarize(state.get("relationships")),
            current_faction_state=self._summarize(state.get("factions")),
            current_location_state={"location": state.get("location"),
                                    "world": self._summarize(state.get("world"))},
            current_resources=self._summarize(state.get("resources")),
            current_equipment={"flags": self._truthy_keys(
                ((inputs.pack.get("initial_flags") or {}).keys()))},
            current_knowledge=self._summarize(state.get("knowledge") or
                                              state.get("author_knowledge")),
            current_progression=self._summarize(state.get("abilities")),
            open_pressures=[item.item_id for item in open_items
                            if item.domain in ("conflict", "mystery")][:20],
            open_foreshadows=[item.item_id for item in open_items
                              if item.domain == "foreshadow"][:20],
            open_requirements=[item.item_id for item in open_items
                               if item.domain in ("content_gap", "progression")][:20],
            next_feasible_opportunities=[item.statement for item in open_items
                                         if item.priority == "high"][:10])

    @staticmethod
    def _summarize(value: Any) -> dict[str, Any]:
        if isinstance(value, list):
            return {"count": len(value),
                    "sample": [str(item)[:80] for item in value[:5]]}
        if isinstance(value, dict):
            return {"keys": list(value.keys())[:12], "count": len(value)}
        return {"value": value if value is None or isinstance(value, (str, int, float,
                                                                      bool)) else str(value)}

    @staticmethod
    def _truthy_keys(keys: Any) -> list[str]:
        return [str(key) for key in keys][:12]

    def build_final_gate(self, inputs: WastelandInputs, story_map: HistoricalStoryMap,
                         target_set: LegacyTargetAlignmentSet,
                         batches: WastelandRepairBatchPlan,
                         before: WastelandReconstructionBaseline,
                         after: WastelandReconstructionBaseline,
                         dag_ok: bool = True,
                         runway: StructuralRunwayReport | None = None,
                         spine: FullBookFutureSpine | None = None
                         ) -> ReconstructionFinalGate:
        confirmed_in_repair = sorted({target.chapter_id for target in target_set.targets
                                      if target.current_classification == CONFIRMED})
        repair_chapters = {chapter_id for batch in batches.batches
                           for chapter_id in batch.chapter_ids}
        findings: list[ReconstructionFinding] = []
        if confirmed_in_repair or repair_chapters & {row.chapter_id for row in
                                                     story_map.chapters
                                                     if row.classification == CONFIRMED}:
            findings.append(ReconstructionFinding(
                code="CONFIRMED_CHAPTER_IN_REPAIR_BATCH", severity="ERROR",
                message="198 个 confirmed 章节不得进入 M11 repair batch",
                recommended_action="从 batch 中移除 confirmed 章节"))
        if before.happened_digests() != after.happened_digests():
            findings.append(ReconstructionFinding(
                code="HAPPENED_TRUTH_DIGEST_CHANGED", severity="ERROR",
                message="Canon / StoryState / legacy candidate / chapter IR digest 发生变化",
                recommended_action="M10 不得修改 happened truth"))
        if before.queue_counts != after.queue_counts:
            findings.append(ReconstructionFinding(
                code="REPAIR_QUEUE_COUNTS_CHANGED", severity="ERROR",
                message="198 / 27 / 345 队列数量被改动",
                recommended_action="M10 只分析不 repair"))
        owners: dict[str, list[str]] = {}
        for batch in batches.batches:
            for chapter_id in batch.chapter_ids:
                owners.setdefault(chapter_id, []).append(batch.batch_id)
        unassigned = sorted({target.chapter_id for target in target_set.targets}
                            - set(owners))
        multiple = sorted(chapter_id for chapter_id, rows in owners.items() if len(rows) > 1)
        if unassigned:
            findings.append(ReconstructionFinding(
                code="REPAIR_TARGET_UNASSIGNED", severity="ERROR",
                message=f"{len(unassigned)} 个 repair target 没有 owning batch",
                related_ids=unassigned[:10], recommended_action="加入唯一 M11 batch"))
        if multiple:
            findings.append(ReconstructionFinding(
                code="REPAIR_TARGET_MULTIPLE_OWNERS", severity="ERROR",
                message="同一 repair target 出现在多个 batch 的 mutable 列表",
                related_ids=multiple[:10], recommended_action="只保留一个 owner，其余改为 read_only"))
        if not dag_ok:
            findings.append(ReconstructionFinding(
                code="REPAIR_BATCH_DEPENDENCY_CYCLE", severity="ERROR",
                message="M11 batch dependency 出现环", recommended_action="拆环"))
        legacy_ok = all(volume.time_layer == "legacy_representation"
                        for volume in story_map.volumes) and all(
            arc.time_layer == "legacy_representation" for arc in story_map.arcs)
        bad_sources = sorted({source for target in target_set.targets
                              for source in target.forbidden_change_sources
                              if source not in CONFIRMED_SOURCES})
        if not legacy_ok or bad_sources:
            findings.append(ReconstructionFinding(
                code="LEGACY_SOURCE_USED_AS_FACT", severity="ERROR",
                message="legacy prose / 非 confirmed 来源被当成 forbidden fact",
                related_ids=bad_sources[:10],
                recommended_action="forbidden_changes 只能来自 Canon / StoryState / confirmed IR"))
        gate = ReconstructionFinalGate(
            alignment_coverage=len(story_map.chapters),
            chapter_total=len(inputs.chapters),
            queue_counts_before=before.queue_counts, queue_counts_after=after.queue_counts,
            field_conflict_targets=len([target for target in target_set.targets
                                        if target.current_classification == FIELD_CONFLICT]),
            content_gap_targets=len([target for target in target_set.targets
                                     if target.current_classification == CONTENT_GAP]),
            confirmed_chapters_in_repair=confirmed_in_repair,
            happened_digests_before=before.happened_digests(),
            happened_digests_after=after.happened_digests(), findings=findings)
        gate.repair_ownership_coverage = len(owners)
        gate.repair_target_total = len(target_set.targets)
        gate.batch_dag_valid = dag_ok
        gate.legacy_isolation_ok = legacy_ok and not bad_sources
        if runway is not None:
            gate.runways = {row.runway: row.verdict for row in runway.runways}
        gate.status = "PASS" if not findings \
            and gate.alignment_coverage == gate.chapter_total \
            and gate.repair_ownership_coverage == gate.repair_target_total \
            and dag_ok and gate.legacy_isolation_ok else "NEEDS_ATTENTION"
        _ = spine
        return gate
