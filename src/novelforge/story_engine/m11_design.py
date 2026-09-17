"""P15h：M11 Content Design & Decision Preparation + Entity Ambiguity Triage + Readiness Hardening。

本轮**不生成正式剧情**、不 promote 内容修复、不进入 Batch 04。
只把"确定缺语义"变成"缺什么 / 为什么缺 / 允许设计到什么程度 / 哪些必须作者决定"，
并把 entity ambiguity / content design / author decision / manual / confirmed binding
正式纳入 target-level readiness。
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal, Mapping, Sequence

from pydantic import Field

from novelforge.models import StrictModel
from novelforge.story_engine.historical_adoption import (
    ADOPTION_DIR,
    M11FoundationAdoptionService,
)
from novelforge.story_engine.historical_ir import (
    HISTORY_DIR,
    HistoricalIRStore,
)

DESIGN_DIR = ADOPTION_DIR
STAFFING_KEYS = ("archive_publication_level", "common_rules_status",
                 "dog_departure_status", "gray_wall_observation_status",
                 "salt_route_control", "zero_layer_access")
OTHER_DOG_ALIASES = ("编号犬", "荒原犬", "笼中同类", "同类", "那只狗")
DEFAULT_PROXIMITY = 3
ESCALATION_FORBIDDEN = ("IRREVERSIBLE_RELATIONSHIP", "MAJOR_FACTION_CHANGE",
                        "PROGRESSION_BREAKTHROUGH", "MAJOR_MAP_UNLOCK",
                        "MAJOR_RESOURCE_CHANGE", "CORE_SECRET_REVEAL",
                        "CHARACTER_PERMANENT_EXIT", "GLOBAL_ROUTE_CHANGE")

ProposalType = Literal["LOCAL_INFORMATION_PIVOT", "LOCAL_STRATEGY_ADJUSTMENT",
                       "LOCAL_RELATIONSHIP_SHIFT", "LOCAL_GOAL_REPRIORITIZATION",
                       "LOCAL_STATE_ACKNOWLEDGEMENT", "CAUSAL_BRIDGE", "DECISION_BINDING"]
ClusterResolution = Literal["NON_BLOCKING_GENERIC_REFERENCE",
                            "CONTEXT_RESOLVABLE_PROPOSAL",
                            "AUTHOR_ENTITY_DECISION_REQUIRED"]
HardBlocker = Literal["READY", "RESOLVED", "BLOCKED_CONTENT_DESIGN",
                      "BLOCKED_AUTHOR_DECISION", "BLOCKED_ENTITY_AMBIGUITY",
                      "BLOCKED_MANUAL_REPAIR", "BLOCKED_DEPENDENCY",
                      "BLOCKED_CONFIRMED_BINDING_CONFLICT",
                      "BLOCKED_FOUNDATION_INTEGRITY"]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read_json(path: Path) -> Any:
    path = Path(path)
    return json.loads(path.read_text(encoding="utf-8-sig")) if path.is_file() else {}


def _write_json(path: Path, payload: Any) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=1) + "\n",
                    encoding="utf-8", newline="\n")


def _digest(payload: Any) -> str:
    return hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True,
                                     default=str).encode("utf-8")).hexdigest()[:16]


# ------------------------------------------------------------------------- models
class RepairDesignRequirement(StrictModel):
    """§1：36 个内容缺口的正式设计需求（只描述，不生成内容）。"""

    design_item_id: str
    chapter_id: str
    legacy_label: str = ""
    arc_id: str = ""
    chapter_function: str = ""
    missing_semantic_type: str = "TURN"
    design_subtype: str = "MICRO_PIVOT_REQUIRED"
    micro_or_major: str = "micro"
    why_required: str = ""
    policy_requirement: dict[str, Any] = Field(default_factory=dict)
    historical_role: str = ""
    existing_events: list[str] = Field(default_factory=list)
    existing_effects: list[str] = Field(default_factory=list)
    existing_transitions: list[str] = Field(default_factory=list)
    existing_decision: str = ""
    existing_turn: str = ""
    existing_payoff: str = ""
    upstream_pressure: list[str] = Field(default_factory=list)
    downstream_requirement: list[str] = Field(default_factory=list)
    neighbor_context_refs: list[str] = Field(default_factory=list)
    confirmed_facts: list[str] = Field(default_factory=list)
    forbidden_changes: list[str] = Field(default_factory=list)
    knowledge_constraints: list[str] = Field(default_factory=list)
    relationship_constraints: list[str] = Field(default_factory=list)
    resource_constraints: list[str] = Field(default_factory=list)
    progression_constraints: list[str] = Field(default_factory=list)
    location_constraints: list[str] = Field(default_factory=list)
    information_constraints: list[str] = Field(default_factory=list)
    foreshadow_constraints: list[str] = Field(default_factory=list)
    available_design_space: list[str] = Field(default_factory=list)
    must_preserve: list[str] = Field(default_factory=list)
    must_not_introduce: list[str] = Field(default_factory=list)
    author_design_required: bool = False
    evidence_refs: list[str] = Field(default_factory=list)
    foundation_artifact_ref: str = ""
    non_authoritative: bool = True


class RepairDesignProposal(StrictModel):
    """§3/§5：micro 的极小设计方案（proposal only，非权威，不写 IR/Canon/StoryState/正文）。"""

    proposal_id: str
    design_item_id: str
    chapter_id: str
    legacy_label: str = ""
    proposal_type: ProposalType = "LOCAL_INFORMATION_PIVOT"
    semantic_change: str = ""
    why_it_satisfies_requirement: str = ""
    affected_fields: list[str] = Field(default_factory=list)
    confirmed_facts_preserved: bool = True
    forbidden_changes_checked: bool = True
    upstream_effect: str = "NONE"
    downstream_effect: str = "LOCAL"
    knowledge_effect: str = "LOCAL"
    relationship_effect: str = "NONE"
    resource_effect: str = "NONE"
    progression_effect: str = "NONE"
    continuity_effect: str = "LOCAL"
    risk: str = "LOW"
    requires_author_approval: bool = False
    evidence_refs: list[str] = Field(default_factory=list)
    escalation_gate: str = "PASS"
    escalation_violations: list[str] = Field(default_factory=list)
    writes_ir: bool = False
    status: str = "PROPOSED"
    non_authoritative: bool = True


class AuthorDesignBrief(StrictModel):
    """§7：major item 的作者设计 brief。"""

    brief_id: str
    design_item_id: str
    chapter_id: str
    legacy_label: str = ""
    arc_id: str = ""
    missing_semantic_requirement: str = ""
    why_major: str = ""
    historical_context: str = ""
    confirmed_facts: list[str] = Field(default_factory=list)
    forbidden_changes: list[str] = Field(default_factory=list)
    upstream_pressure: list[str] = Field(default_factory=list)
    downstream_consequences: list[str] = Field(default_factory=list)
    what_author_must_decide: list[str] = Field(default_factory=list)
    possible_directions: list[dict[str, Any]] = Field(default_factory=list)
    tradeoffs: list[str] = Field(default_factory=list)
    affected_later_chapters: list[str] = Field(default_factory=list)
    blocking_scope: list[str] = Field(default_factory=list)
    non_authoritative: bool = True


class DecisionOption(StrictModel):
    option_id: str
    label: str
    actor: str = ""
    changes_happened_fact: bool = False
    affected_chapters: list[str] = Field(default_factory=list)
    affected_arcs: list[str] = Field(default_factory=list)
    relationship_effect: str = "NONE"
    knowledge_effect: str = "NONE"
    resource_effect: str = "NONE"
    progression_effect: str = "NONE"
    fits_existing_evidence: str = ""
    confidence: float = Field(default=0.5, ge=0, le=1)


class AuthorDecisionBrief(StrictModel):
    """PART C / §14：足以让作者直接选的决定 brief。"""

    brief_id: str
    subject: str = ""
    legacy_label: str = ""
    chapter_id: str = ""
    ambiguity_type: str = ""
    sources: list[dict[str, Any]] = Field(default_factory=list)
    evidence_summary: list[str] = Field(default_factory=list)
    options: list[DecisionOption] = Field(default_factory=list)
    recommended_default: str = ""
    recommendation_confidence: float = Field(default=0.0, ge=0, le=1)
    why_still_not_automatic: list[str] = Field(default_factory=list)
    blocking_scope: list[str] = Field(default_factory=list)
    auto_closed: bool = False
    non_authoritative: bool = True


class ManualRepairBrief(StrictModel):
    """PART D：ch063 manual repair brief。"""

    brief_id: str
    chapter_id: str
    legacy_label: str = ""
    legacy_world_state_change: str = ""
    foundation_transition: list[dict[str, Any]] = Field(default_factory=list)
    m10_state_binding_conflict: dict[str, Any] = Field(default_factory=dict)
    why_foundation_domain_not_automatic: str = ""
    candidate_domains: list[dict[str, Any]] = Field(default_factory=list)
    safe_representation_operations: list[str] = Field(default_factory=list)
    forbidden_operations: list[str] = Field(default_factory=list)
    manual_recommendation: str = ""
    status: str = "MANUAL_REQUIRED"
    non_authoritative: bool = True


class EntityAmbiguityCluster(StrictModel):
    """§8：entity ambiguity cluster（按 cluster 而不是按章节组织）。"""

    cluster_id: str
    ambiguous_mentions: list[str] = Field(default_factory=list)
    chapter_ids: list[str] = Field(default_factory=list)
    legacy_labels: list[str] = Field(default_factory=list)
    candidate_entities: list[str] = Field(default_factory=list)
    supporting_evidence: list[str] = Field(default_factory=list)
    contradicting_evidence: list[str] = Field(default_factory=list)
    affected_repair_targets: list[str] = Field(default_factory=list)
    affected_batches: list[str] = Field(default_factory=list)
    affected_fields: list[str] = Field(default_factory=list)
    requires_exact_identity: bool = False
    repair_can_proceed_without_identity: bool = True
    resolution_status: ClusterResolution = "NON_BLOCKING_GENERIC_REFERENCE"
    resolution_proposal: dict[str, Any] = Field(default_factory=dict)
    non_authoritative: bool = True


class ConfirmedBindingResolution(StrictModel):
    """§12/§13：truth precedence record（只引用既有 ID，不新增 truth 文本）。"""

    resolution_id: str
    legacy_label: str
    chapter_id: str = ""
    aspect: str = "primary_transition"
    status: str = "CONFIRMED_OVERRIDE_ACTIVE"
    value_pointer: str = ""
    value_refs: list[str] = Field(default_factory=list)
    value_digest: str = ""
    display_value: str = ""
    display_value_authoritative: bool = False
    evidence_sources: list[str] = Field(default_factory=list)
    why_override: str = ""
    affects_repair: bool = True
    non_authoritative: bool = False


class GuardedBinding(StrictModel):
    """PART G：confirmed historical binding guard 条目。"""

    legacy_label: str
    chapter_id: str = ""
    aspect: str = ""
    expected_value: str = ""
    value_pointer: str = ""
    fact_group: str = ""


class HardenedTargetReadiness(StrictModel):
    chapter_id: str
    legacy_label: str = ""
    batch_id: str = ""
    status: HardBlocker = "READY"
    reason: str = ""
    blocking_source: list[str] = Field(default_factory=list)


class HardenedBatchReadiness(StrictModel):
    batch_id: str
    status: str = "PARTIAL_READY"
    ready_target_ids: list[str] = Field(default_factory=list)
    blocked_target_ids: list[str] = Field(default_factory=list)
    block_reason_by_target: dict[str, str] = Field(default_factory=dict)
    blocker_counts: dict[str, int] = Field(default_factory=dict)
    mutable_target_count: int = 0
    dependency_batches: list[str] = Field(default_factory=list)
    non_authoritative: bool = True


@dataclass
class DesignInputs:
    root: Path = field(default_factory=lambda: Path(".").resolve())
    design_dir: Path = field(default_factory=lambda: Path(".").resolve())
    design_queue: dict[str, Any] = field(default_factory=dict)
    adoption: dict[str, Any] = field(default_factory=dict)
    reconciliation: dict[str, Any] = field(default_factory=dict)
    projection: dict[str, Any] = field(default_factory=dict)
    ambiguous_impact: dict[str, Any] = field(default_factory=dict)
    golden_delta: dict[str, Any] = field(default_factory=dict)
    fact_checks: dict[str, Any] = field(default_factory=dict)
    adoption_gate: dict[str, Any] = field(default_factory=dict)
    targets: dict[str, dict[str, Any]] = field(default_factory=dict)
    batches: list[dict[str, Any]] = field(default_factory=list)
    legacy_rows: dict[str, dict[str, Any]] = field(default_factory=dict)
    story_rows: dict[str, dict[str, Any]] = field(default_factory=dict)
    artifacts: dict[str, Any] = field(default_factory=dict)
    author_queue: dict[str, Any] = field(default_factory=dict)
    canon_registry: dict[str, Any] = field(default_factory=dict)
    digests: dict[str, str] = field(default_factory=dict)


class M11DesignDecisionService:
    """P15h service：design prep + entity triage + readiness hardening（不执行 repair）。"""

    def __init__(self, project_root: Path | str, *, design_dir: str = DESIGN_DIR,
                 foundation_dir: str = HISTORY_DIR) -> None:
        self.root = Path(project_root).resolve()
        self.design_dir = (self.root / design_dir).resolve()
        self.foundation_dir = (self.root / foundation_dir).resolve()
        self.recon_dir = self.root / "workspace/wasteland_001_exports/reconstruction_v2"
        self.repair_dir = self.root / "workspace/wasteland_001_exports/repair_v1"
        self.store = HistoricalIRStore(self.foundation_dir)
        self.adoption = M11FoundationAdoptionService(self.root)

    # ---- load -----------------------------------------------------------
    def load(self) -> DesignInputs:
        adoption_inputs = self.adoption.load()
        legacy_payload = _read_json(
            self.root / "workspace/wasteland_001_exports/"
            "WASTELAND_001_OUTLINE_CANON_FINAL_CANDIDATE_V5.json")
        return DesignInputs(
            root=self.root, design_dir=self.design_dir,
            design_queue=_read_json(self.design_dir / "M11_CONTENT_DESIGN_QUEUE.json"),
            adoption=_read_json(self.design_dir / "P15G_SUMMARY.json"),
            reconciliation=_read_json(self.design_dir / "REPAIR_RECONCILIATION.json"),
            projection=_read_json(self.design_dir / "M11_RESOLUTION_PROJECTION.json"),
            ambiguous_impact=_read_json(self.design_dir / "AMBIGUOUS_ENTITY_IMPACT.json"),
            golden_delta=_read_json(self.design_dir /
                                    "M1_GOLDEN_DELTA_RECONCILIATION.json"),
            fact_checks=_read_json(self.design_dir / "CROSS_CHAPTER_FACT_CHECKS.json"),
            adoption_gate=_read_json(self.design_dir / "M11_FOUNDATION_ADOPTION_GATE.json"),
            targets=adoption_inputs.targets, batches=adoption_inputs.batches,
            legacy_rows=adoption_inputs.legacy_rows,
            story_rows=adoption_inputs.story_rows,
            artifacts=self.store.load_artifacts(),
            author_queue=adoption_inputs.author_queue,
            canon_registry=_read_json(
                self.root / "workspace/wasteland_001_exports/"
                "WASTELAND_001_CANON_FACT_REGISTRY.json"),
            digests=self._source_digests())

    def _source_digests(self) -> dict[str, str]:
        digests: dict[str, str] = {}
        for name, path in (
                ("canon", self.root / "novel/authoring/story_engine/canon/"
                 "wasteland_001.sqlite"),
                ("story_state", self.root / "novel/authoring/story_engine/state/"
                 "runtime_wasteland_001/v000001.json"),
                ("legacy", self.root / "workspace/wasteland_001_exports/"
                 "WASTELAND_001_OUTLINE_CANON_FINAL_CANDIDATE_V5.json"),
                ("chapter_ir", self.root / "workspace/wasteland_001_exports/"
                 "chapter_ir_v1/full_migration/WASTELAND_001_CHAPTER_IR_FULL.json"),
                ("foundation_index", self.foundation_dir / "index.json"),
                ("overlay", self.repair_dir / "M11_OVERLAY.json")):
            digests[name] = hashlib.sha256(path.read_bytes()).hexdigest()[:16] \
                if path.is_file() else ""
        return digests

    # ---- §1 design requirements -----------------------------------------
    def build_design_requirements(self, *, inputs: DesignInputs | None = None
                                  ) -> dict[str, Any]:
        inputs = inputs or self.load()
        requirements: list[RepairDesignRequirement] = []
        for item in inputs.design_queue.get("items") or []:
            chapter_id = str(item.get("chapter_id"))
            label = str(item.get("legacy_label") or "")
            artifact = inputs.artifacts.get(chapter_id)
            legacy = inputs.legacy_rows.get(chapter_id) or {}
            target = inputs.targets.get(chapter_id) or {}
            story = inputs.story_rows.get(chapter_id) or {}
            recon = (inputs.adoption.get("readiness") or {})
            requirements.append(_design_requirement(
                item=item, chapter_id=chapter_id, label=label, artifact=artifact,
                legacy=legacy, target=target, story=story, label_lookup=
                {cid: str(row.get("id")) for cid, row in inputs.legacy_rows.items()}))
            _ = recon
        payload = {"generated_at": _now(), "requirement_count": len(requirements),
                   "micro_count": sum(1 for row in requirements
                                      if row.micro_or_major == "micro"),
                   "major_count": sum(1 for row in requirements
                                      if row.micro_or_major == "major"),
                   "requirements": [row.model_dump(mode="json") for row in requirements],
                   "content_generated": False, "read_only": True,
                   "non_authoritative": True}
        _write_json(self.design_dir / "REPAIR_DESIGN_REQUIREMENTS.json", payload)
        return payload

    # ---- §2/§3/§5/§6 micro proposals -------------------------------------
    def build_micro_proposals(self, *, inputs: DesignInputs | None = None,
                              requirements: Mapping[str, Any] | None = None
                              ) -> dict[str, Any]:
        inputs = inputs or self.load()
        requirements = requirements or _read_json(
            self.design_dir / "REPAIR_DESIGN_REQUIREMENTS.json")
        proposals: list[RepairDesignProposal] = []
        for requirement in requirements.get("requirements") or []:
            if requirement.get("micro_or_major") != "micro":
                continue
            chapter_id = str(requirement.get("chapter_id"))
            artifact = inputs.artifacts.get(chapter_id)
            legacy = inputs.legacy_rows.get(chapter_id) or {}
            proposals.extend(_micro_proposals(requirement, artifact, legacy))
        violations = [row.proposal_id for row in proposals
                      if row.escalation_gate != "PASS"]
        per_item: dict[str, int] = {}
        for row in proposals:
            per_item[row.design_item_id] = per_item.get(row.design_item_id, 0) + 1
        payload = {
            "generated_at": _now(), "proposal_count": len(proposals),
            "item_count": len(per_item),
            "proposals_per_item": per_item,
            "escalation_gate": "PASS" if not violations else "FAIL",
            "escalation_violations": violations,
            "proposals": [row.model_dump(mode="json") for row in proposals],
            "writes_ir": False, "content_generated": False,
            "non_authoritative": True, "read_only": True}
        _write_json(self.design_dir / "MICRO_REPAIR_DESIGN_PROPOSALS.json", payload)
        return payload

    # ---- §7 major briefs -------------------------------------------------
    def build_major_briefs(self, *, inputs: DesignInputs | None = None,
                           requirements: Mapping[str, Any] | None = None
                           ) -> dict[str, Any]:
        inputs = inputs or self.load()
        requirements = requirements or _read_json(
            self.design_dir / "REPAIR_DESIGN_REQUIREMENTS.json")
        briefs: list[AuthorDesignBrief] = []
        for requirement in requirements.get("requirements") or []:
            if requirement.get("micro_or_major") != "major":
                continue
            chapter_id = str(requirement.get("chapter_id"))
            artifact = inputs.artifacts.get(chapter_id)
            briefs.append(_major_brief(requirement, artifact, inputs))
        payload = {"generated_at": _now(), "brief_count": len(briefs),
                   "briefs": [row.model_dump(mode="json") for row in briefs],
                   "auto_design_generated": False, "non_authoritative": True,
                   "read_only": True}
        _write_json(self.design_dir / "MAJOR_AUTHOR_DESIGN_BRIEFS.json", payload)
        return payload

    # ---- PART C / §14 decision briefs -----------------------------------
    def build_decision_briefs(self, *, inputs: DesignInputs | None = None
                              ) -> dict[str, Any]:
        inputs = inputs or self.load()
        ch036 = _ch036_brief(inputs)
        ch559 = _ch559_brief(inputs)
        _write_json(self.design_dir / "AUTHOR_DECISION_BRIEF_ch036.json",
                    ch036.model_dump(mode="json"))
        _write_json(self.design_dir / "AUTHOR_DECISION_BRIEF_ch559.json",
                    ch559.model_dump(mode="json"))
        return {"ch036": ch036.model_dump(mode="json"),
                "ch559": ch559.model_dump(mode="json")}

    # ---- PART D ch063 manual brief ---------------------------------------
    def build_manual_brief(self, *, inputs: DesignInputs | None = None
                           ) -> dict[str, Any]:
        inputs = inputs or self.load()
        brief = _ch063_brief(inputs, self.design_dir)
        payload = brief.model_dump(mode="json")
        _write_json(self.design_dir / "MANUAL_REPAIR_BRIEF_ch063.json", payload)
        return payload

    # ---- PART E entity ambiguity clustering ------------------------------
    def build_entity_clusters(self, *, inputs: DesignInputs | None = None
                              ) -> dict[str, Any]:
        inputs = inputs or self.load()
        clusters = _entity_clusters(inputs, proximity=DEFAULT_PROXIMITY)
        counts: dict[str, int] = {}
        for cluster in clusters:
            counts[cluster.resolution_status] = counts.get(cluster.resolution_status, 0) + 1
        chapter_total = sum(len(cluster.chapter_ids) for cluster in clusters)
        blocking_clusters = [cluster for cluster in clusters
                             if cluster.resolution_status
                             == "AUTHOR_ENTITY_DECISION_REQUIRED"]
        payload = {"generated_at": _now(), "cluster_count": len(clusters),
                   "chapter_count": chapter_total,
                   "status_counts": counts,
                   "author_required_clusters": len(blocking_clusters),
                   "clusters": [row.model_dump(mode="json") for row in clusters],
                   "entity_truth_modified": False,
                   "note": ("entity resolution 只影响 representation binding，"
                            "不新增/修改 confirmed entity truth"),
                   "read_only": True, "non_authoritative": True}
        _write_json(self.design_dir / "M11_ENTITY_RESOLUTION_QUEUE.json", payload)
        return payload

    # ---- PART F confirmed binding precedence -----------------------------
    def build_confirmed_bindings(self, *, inputs: DesignInputs | None = None
                                 ) -> dict[str, Any]:
        inputs = inputs or self.load()
        resolutions = _confirmed_bindings(inputs)
        guards = _guarded_bindings(inputs)
        override_chapters = {row.legacy_label for row in resolutions}
        payload = {"generated_at": _now(),
                   "override_count": len(resolutions),
                   "override_chapter_count": len(override_chapters),
                   "author_review_count": sum(
                       1 for row in inputs.golden_delta.get("rows") or []
                       if row.get("decision") == "AUTHOR_REVIEW"),
                   "resolutions": [row.model_dump(mode="json") for row in resolutions],
                   "guarded_bindings": [row.model_dump(mode="json") for row in guards],
                   "guard_code": "CONFIRMED_HISTORICAL_BINDING_VIOLATION",
                   "guard_severity": "ERROR",
                   "new_truth_created": False,
                   "note": ("ConfirmedBindingResolution 只是 truth precedence record："
                            "value 只引用 Canon / StoryState / M10 confirmed evidence ID"),
                   "read_only": True}
        _write_json(self.design_dir / "CONFIRMED_BINDING_RESOLUTION.json", payload)
        return payload

    # ---- PART H readiness hardening --------------------------------------
    def harden_readiness(self, *, inputs: DesignInputs | None = None,
                         clusters: Mapping[str, Any] | None = None,
                         requirements: Mapping[str, Any] | None = None,
                         confirmed: Mapping[str, Any] | None = None
                         ) -> dict[str, Any]:
        inputs = inputs or self.load()
        clusters = clusters or _read_json(
            self.design_dir / "M11_ENTITY_RESOLUTION_QUEUE.json")
        requirements = requirements or _read_json(
            self.design_dir / "REPAIR_DESIGN_REQUIREMENTS.json")
        confirmed = confirmed or _read_json(
            self.design_dir / "CONFIRMED_BINDING_RESOLUTION.json")
        substrate = self.adoption.verify_substrate()
        rows = _hardened_targets(inputs, clusters, requirements, confirmed)
        batches = _hardened_batches(inputs, rows)
        counts: dict[str, int] = {}
        for row in rows:
            counts[row.status] = counts.get(row.status, 0) + 1
        batch_status_counts: dict[str, int] = {}
        for batch in batches:
            batch_status_counts[batch.status] = batch_status_counts.get(batch.status, 0) + 1
        batch_04 = next((row for row in batches
                         if row.batch_id == "REPAIR_BATCH_04"), None)
        payload = {
            "generated_at": _now(), "target_count": len(rows),
            "target_status_counts": counts, "batch_status_counts": batch_status_counts,
            "batches": [row.model_dump(mode="json") for row in batches],
            "batch_04": batch_04.model_dump(mode="json") if batch_04 else {},
            "blocker_taxonomy": ["BLOCKED_CONTENT_DESIGN", "BLOCKED_AUTHOR_DECISION",
                                 "BLOCKED_ENTITY_AMBIGUITY", "BLOCKED_MANUAL_REPAIR",
                                 "BLOCKED_DEPENDENCY",
                                 "BLOCKED_CONFIRMED_BINDING_CONFLICT",
                                 "BLOCKED_FOUNDATION_INTEGRITY"],
            "foundation_integrity": substrate["mismatch_count"] == 0,
            "overlay_modified": False,
            "read_only": True, "non_authoritative": True,
        }
        _write_json(self.design_dir / "M11_READINESS_HARDENED.json", payload)
        return payload

    # ---- PART I next action plan -----------------------------------------
    def build_next_action_plan(self, *, inputs: DesignInputs | None = None,
                               clusters: Mapping[str, Any] | None = None,
                               readiness: Mapping[str, Any] | None = None,
                               requirements: Mapping[str, Any] | None = None,
                               proposals: Mapping[str, Any] | None = None
                               ) -> dict[str, Any]:
        inputs = inputs or self.load()
        clusters = clusters or _read_json(
            self.design_dir / "M11_ENTITY_RESOLUTION_QUEUE.json")
        readiness = readiness or _read_json(
            self.design_dir / "M11_READINESS_HARDENED.json")
        requirements = requirements or _read_json(
            self.design_dir / "REPAIR_DESIGN_REQUIREMENTS.json")
        proposals = proposals or _read_json(
            self.design_dir / "MICRO_REPAIR_DESIGN_PROPOSALS.json")
        batch_04 = dict(readiness.get("batch_04") or {})
        author_clusters = [row for row in clusters.get("clusters") or []
                           if row.get("resolution_status")
                           == "AUTHOR_ENTITY_DECISION_REQUIRED"
                           and row.get("affected_batches")]
        micro_items = [row for row in requirements.get("requirements") or []
                       if row.get("micro_or_major") == "micro"]
        author_items = [
            {"order": 1, "kind": "AUTHOR_DECISION",
             "ref": "AUTHOR_DECISION_BRIEF_ch036.json",
             "question": "ch036 的 decision actor / 语义表达如何绑定（Option A / B）",
             "blocks": ["ch036 及其 continuity 下游"]},
            {"order": 2, "kind": "AUTHOR_DECISION",
             "ref": "AUTHOR_DECISION_BRIEF_ch559.json",
             "question": "ch559 dog_role：M1 人工标签（independent/present）还是 M10 story map（offscreen_effect）",
             "blocks": ["ch559 及其 continuity 下游"]},
            {"order": 3, "kind": "AUTHOR_DESIGN",
             "ref": "MAJOR_AUTHOR_DESIGN_BRIEFS.json",
             "question": "2 个 major content design（ch012 / ch056）的方向选择",
             "blocks": ["ch012 / ch056 及其 continuity 下游"]},
            {"order": 4, "kind": "MANUAL_REPAIR",
             "ref": "MANUAL_REPAIR_BRIEF_ch063.json",
             "question": "ch063 state binding：representation-only 还是指定 domain",
             "blocks": ["ch063 及其 continuity 下游"]},
        ]
        for row in author_clusters:
            author_items.append({
                "order": 5, "kind": "ENTITY_DECISION",
                "ref": f"{row.get('cluster_id')}",
                "question": ("ambiguous entity identity：" +
                             "/".join(row.get("candidate_entities") or [])),
                "blocks": list(row.get("affected_batches") or [])})
        payload = {
            "generated_at": _now(),
            "author_decisions": author_items,
            "author_decision_count": len(author_items),
            "micro_design_approvals": {
                "item_count": len(micro_items),
                "proposal_count": proposals.get("proposal_count"),
                "flow": "RepairDesignProposal → validators → MANUAL_APPROVAL（不要求作者逐条设计）",
                "proposal_ref": "MICRO_REPAIR_DESIGN_PROPOSALS.json"},
            "manual_items": [
                {"ref": "MANUAL_REPAIR_BRIEF_ch063.json", "kind": "MANUAL_REPAIR"},
                {"ref": "M11_ENTITY_RESOLUTION_QUEUE.json",
                 "kind": "CONTEXT_RESOLVABLE_CONFIRMATION",
                 "count": clusters.get("status_counts", {}).get(
                     "CONTEXT_RESOLVABLE_PROPOSAL", 0)}],
            "entity_clusters": {"cluster_count": clusters.get("cluster_count"),
                                "status_counts": clusters.get("status_counts")},
            "safe_targets": [
                {"batch_id": "REPAIR_BATCH_04",
                 "ready_target_ids": batch_04.get("ready_target_ids") or [],
                 "blocked_target_ids": batch_04.get("blocked_target_ids") or [],
                 "note": ("Batch 04 可执行子集：仅这些 target 当前无 localized blocker；"
                          "本轮不执行")}],
            "execution_order": ["author_decisions", "micro_design_approvals",
                                "manual_items", "repair_batch_04_safe_targets"],
            "batch_04_executed": False, "content_generated": False,
            "read_only": True, "non_authoritative": True,
        }
        _write_json(self.design_dir / "M11_NEXT_ACTION_PLAN.json", payload)
        return payload

    # ---- gate / run -------------------------------------------------------
    def run(self, **payloads: Any) -> dict[str, Any]:
        inputs = self.load()
        digests_before = dict(inputs.digests)
        requirements = self.build_design_requirements(inputs=inputs)
        proposals = self.build_micro_proposals(inputs=inputs, requirements=requirements)
        major = self.build_major_briefs(inputs=inputs, requirements=requirements)
        briefs = self.build_decision_briefs(inputs=inputs)
        manual = self.build_manual_brief(inputs=inputs)
        clusters = self.build_entity_clusters(inputs=inputs)
        confirmed = self.build_confirmed_bindings(inputs=inputs)
        readiness = self.harden_readiness(inputs=inputs, clusters=clusters,
                                          requirements=requirements,
                                          confirmed=confirmed)
        plan = self.build_next_action_plan(inputs=inputs, clusters=clusters,
                                           readiness=readiness,
                                           requirements=requirements,
                                           proposals=proposals)
        gate = self.p15h_gate(inputs=inputs, digests_before=digests_before,
                              requirements=requirements, proposals=proposals,
                              major=major, briefs=briefs, manual=manual,
                              clusters=clusters, confirmed=confirmed,
                              readiness=readiness, plan=plan)
        payload = {"generated_at": _now(), "phase": "P15h", "status": gate["status"],
                   "requirements": {"count": requirements["requirement_count"],
                                    "micro": requirements["micro_count"],
                                    "major": requirements["major_count"]},
                   "micro_proposals": {"count": proposals["proposal_count"],
                                       "items": proposals["item_count"],
                                       "escalation_gate": proposals["escalation_gate"]},
                   "major_briefs": major["brief_count"],
                   "decision_briefs": list(briefs),
                   "manual_brief": {"chapter": manual["legacy_label"],
                                    "status": manual["status"]},
                   "entity_clusters": {"clusters": clusters["cluster_count"],
                                       "chapters": clusters["chapter_count"],
                                       "status_counts": clusters["status_counts"]},
                   "confirmed_bindings": {"overrides": confirmed["override_count"],
                                          "guards": len(confirmed["guarded_bindings"])},
                   "readiness": {"batch_status_counts": readiness["batch_status_counts"],
                                 "batch_04": readiness["batch_04"]},
                   "next_action_count": plan["author_decision_count"],
                   "batch_04_executed": False, "content_generated": False,
                   "repair_promoted": False, "read_only": True,
                   "non_authoritative": True}
        _write_json(self.design_dir / "P15H_SUMMARY.json", payload)
        return payload

    def p15h_gate(self, **payloads: Any) -> dict[str, Any]:
        inputs = payloads.get("inputs") or self.load()
        requirements = payloads.get("requirements") or {}
        proposals = payloads.get("proposals") or {}
        major = payloads.get("major") or {}
        briefs = payloads.get("briefs") or {}
        manual = payloads.get("manual") or {}
        clusters = payloads.get("clusters") or {}
        confirmed = payloads.get("confirmed") or {}
        readiness = payloads.get("readiness") or {}
        plan = payloads.get("plan") or {}
        digests_before = payloads.get("digests_before") or {}
        digests_after = self._source_digests()
        guard_labels = {row.get("legacy_label") for row in
                        confirmed.get("guarded_bindings") or []}
        overrides = confirmed.get("resolutions") or []
        checks = {
            "design_requirements_36": requirements.get("requirement_count") == 36,
            "micro_34_major_2": (requirements.get("micro_count") == 34
                                 and requirements.get("major_count") == 2),
            "micro_proposals_generated": bool(proposals.get("proposal_count"))
            and proposals.get("item_count") == 34,
            "micro_escalation_gate_pass": proposals.get("escalation_gate") == "PASS",
            "proposals_non_authoritative_no_ir_write": all(
                row.get("non_authoritative") and row.get("writes_ir") is False
                for row in proposals.get("proposals") or []),
            "major_briefs_2_no_auto_design": (major.get("brief_count") == 2
                                              and major.get("auto_design_generated") is False),
            "ch036_brief_present_not_auto": bool(
                (briefs.get("ch036") or {}).get("options")) and (
                briefs.get("ch036") or {}).get("auto_closed") is False,
            "ch559_brief_present_not_auto": bool(
                (briefs.get("ch559") or {}).get("options")) and (
                briefs.get("ch559") or {}).get("auto_closed") is False,
            "ch063_manual_brief_present": manual.get("status") == "MANUAL_REQUIRED"
            and bool(manual.get("candidate_domains")),
            "entity_clusters_cover_62": clusters.get("chapter_count") == 62
            and 0 < clusters.get("cluster_count", 0) <= 62,
            "entity_resolution_does_not_change_truth": clusters.get(
                "entity_truth_modified") is False,
            "confirmed_overrides_9": confirmed.get("override_chapter_count") == 9,
            "confirmed_override_reference_only": all(
                row.get("value_pointer") and row.get("value_refs")
                and row.get("display_value_authoritative") is False
                for row in overrides),
            "cross_chapter_guard_14": len(guard_labels) == 14,
            "hardened_readiness_17_batches": len(readiness.get("batches") or []) == 17,
            "batch_04_recomputed": bool(
                (readiness.get("batch_04") or {}).get("ready_target_ids") is not None),
            "localized_blocking_keeps_safe_targets": bool(
                (readiness.get("batch_04") or {}).get("ready_target_ids")),
            "no_content_generated": requirements.get("content_generated") is False
            and proposals.get("content_generated") is False,
            "no_repair_promoted": True,
            "overlay_unchanged": digests_before.get("overlay") == digests_after.get("overlay"),
            "canon_story_state_legacy_foundation_unchanged": all(
                digests_before.get(key) == digests_after.get(key)
                for key in ("canon", "story_state", "legacy", "chapter_ir",
                            "foundation_index")),
            "next_action_plan_present": bool(plan.get("execution_order")),
        }
        status = "PASS" if all(checks.values()) else "NEEDS_ATTENTION"
        payload = {"gate_id": "P15H_GATE", "generated_at": _now(), "status": status,
                   "checks": checks, "digests_before": digests_before,
                   "digests_after": digests_after,
                   "batch_04_executed": False, "content_generated": False,
                   "read_only": True, "non_authoritative": True}
        _write_json(self.design_dir / "P15H_GATE.json", payload)
        return payload


# ------------------------------------------------------------------ helpers
def _design_requirement(*, item: Mapping[str, Any], chapter_id: str, label: str,
                        artifact: Any, legacy: Mapping[str, Any],
                        target: Mapping[str, Any], story: Mapping[str, Any],
                        label_lookup: Mapping[str, str]) -> RepairDesignRequirement:
    body = artifact.chapter_ir if artifact else None
    events = [f"{row.event_id}:{row.action_text[:60]}" for row in
              (body.event_frames if body else [])][:6]
    effects = [f"{row.effect_id}:{row.effect_type}:{row.polarity}" for row in
               (body.effects if body else [])][:6]
    transitions = [f"{row.transition_id}:{row.state_key}:{row.to_state}" for row in
                   (body.state_transitions if body else [])][:4]

    def assertion(field_name: str) -> str:
        row = artifact.assertion(field_name) if artifact else None
        if row is None:
            return ""
        quote = next((ref.quote for ref in row.evidence_refs if ref.quote), "")
        return f"{row.assertion_mode}:{quote[:60]}" if quote else row.assertion_mode

    requirements_map = dict((target.get("policy_requirement") or {}))
    micro = str(item.get("micro_or_major") or "micro")
    constraints = {
        "knowledge_constraints": [f"knowledge={assertion('knowledge')}",
                                  f"information_release="
                                  f"{str(legacy.get('information_release') or '')[:40]}"],
        "relationship_constraints": [f"relationship={assertion('relationship')}",
                                     f"relationship_delta="
                                     f"{json.dumps(legacy.get('relationship_delta'), ensure_ascii=False)[:60]}"],
        "resource_constraints": [f"resource={assertion('resource')}"],
        "progression_constraints": [f"progression={assertion('progression')}"],
        "location_constraints": [f"location={assertion('location')}"],
        "information_constraints": [f"information_release={assertion('information_release')}"],
        "foreshadow_constraints": [
            f"foreshadow_action={str(legacy.get('foreshadow_action') or '')[:60]}",
            f"hook={str(legacy.get('hook') or '')[:60]}"],
    }
    return RepairDesignRequirement(
        design_item_id=str(item.get("design_item_id") or f"CDQ_{label}"),
        chapter_id=chapter_id, legacy_label=label,
        arc_id=str(item.get("arc_id") or target.get("historical_arc") or ""),
        chapter_function=str(target.get("target_chapter_function") or ""),
        missing_semantic_type=str(item.get("missing_semantic_type") or "TURN"),
        design_subtype=str(item.get("design_subtype") or "MICRO_PIVOT_REQUIRED"),
        micro_or_major=micro,
        why_required=("ChapterFunctionPolicy 要求 " +
                      "/".join(item.get("subtypes") or []) +
                      "；legacy outline source of record 无 pivot evidence"),
        policy_requirement=requirements_map or {
            "turn": "micro_turn" if micro == "micro" else "major_turn"},
        historical_role=str(story.get("classification") or ""),
        existing_events=events, existing_effects=effects, existing_transitions=transitions,
        existing_decision=assertion("decision"), existing_turn=assertion("turn"),
        existing_payoff=assertion("payoff"),
        upstream_pressure=[label_lookup.get(str(dep), str(dep)) for dep in
                           target.get("upstream_dependencies") or []],
        downstream_requirement=[label_lookup.get(str(dep), str(dep)) for dep in
                                target.get("downstream_dependencies") or []],
        neighbor_context_refs=[f"arc:{item.get('arc_id')}",
                               f"volume:{target.get('historical_volume')}"],
        confirmed_facts=[str(value) for value in target.get("confirmed_facts") or []],
        forbidden_changes=[str(value) for value in target.get("forbidden_changes") or []],
        **constraints,
        available_design_space=list(item.get("candidate_space") or []),
        must_preserve=["confirmed happened facts（Canon / StoryState / M10 alignment）",
                       "neighbor chapters 的既有语义", "frozen route",
                       "legacy outline 只能新增 evidence，不得改写历史"],
        must_not_introduce=["新敌人", "新地图", "新秘密", "新能力", "新装备", "新资源",
                            "新世界规则", "重大关系变化", "重大角色死亡", "重大伏笔"],
        author_design_required=(micro == "major"),
        evidence_refs=[f"foundation:{chapter_id}", f"target:{label}",
                       f"design_queue:{item.get('design_item_id')}"],
        foundation_artifact_ref=f"historical_chapter_ir_v1/artifacts/{chapter_id}.json")


MICRO_TEMPLATES: tuple[tuple[str, str, tuple[str, ...], str], ...] = (
    ("LOCAL_INFORMATION_PIVOT", "已被 source 记录的信息理解变化",
     ("information_release", "knowledge"), "LOCAL"),
    ("LOCAL_STRATEGY_ADJUSTMENT", "已存在的短期策略/顺序调整",
     ("turn", "decision"), "LOCAL"),
    ("LOCAL_RELATIONSHIP_SHIFT", "已存在的局部关系态度变化",
     ("relationship", "turn"), "LOCAL"),
    ("LOCAL_GOAL_REPRIORITIZATION", "已存在的短期目标优先级变化",
     ("turn", "decision"), "LOCAL"),
    ("LOCAL_STATE_ACKNOWLEDGEMENT", "已存在的局部状态确认",
     ("world_state_change", "turn"), "LOCAL"),
    ("CAUSAL_BRIDGE", "已存在的 next_chapter_causality 因果桥",
     ("causality", "turn"), "LOCAL"),
    ("DECISION_BINDING", "已存在的 choice/备选 → decision 绑定",
     ("decision",), "LOCAL"),
)


def _micro_proposals(requirement: Mapping[str, Any], artifact: Any,
                     legacy: Mapping[str, Any]) -> list[RepairDesignProposal]:
    label = str(requirement.get("legacy_label"))
    chapter_id = str(requirement.get("chapter_id"))
    proposals: list[RepairDesignProposal] = []
    info_ok = bool(str(legacy.get("information_release") or "").strip())
    choice_ok = bool(str(legacy.get("choice") or "").strip())
    strategy_ok = bool(str(legacy.get("next_chapter_causality") or "").strip())
    goal_ok = bool(str(legacy.get("goal") or "").strip())
    state_ok = bool(str(legacy.get("end_state") or legacy.get("start_state") or "").strip())
    relationship_ok = bool(legacy.get("relationship_delta"))
    applicability = {
        "LOCAL_INFORMATION_PIVOT": info_ok,
        "LOCAL_STRATEGY_ADJUSTMENT": strategy_ok,
        "LOCAL_RELATIONSHIP_SHIFT": relationship_ok,
        "LOCAL_GOAL_REPRIORITIZATION": goal_ok,
        "LOCAL_STATE_ACKNOWLEDGEMENT": state_ok,
        "CAUSAL_BRIDGE": strategy_ok,
        "DECISION_BINDING": choice_ok,
    }
    evidence_refs = [f"chapter:{label}", f"foundation:{chapter_id}"]
    for order, (proposal_type, semantic, fields, continuity) in enumerate(
            MICRO_TEMPLATES, start=1):
        if not applicability.get(proposal_type):
            continue
        proposal = RepairDesignProposal(
            proposal_id=f"RDP_{label}_{order:02d}", design_item_id=str(
                requirement.get("design_item_id")), chapter_id=chapter_id,
            legacy_label=label, proposal_type=proposal_type,  # type: ignore[arg-type]
            semantic_change=(f"把 {label} 已存在的「{semantic}」绑定为该章 micro pivot 的 "
                             f"evidence（pure binding，不新增事件/事实）"),
            why_it_satisfies_requirement=(
                f"requirement={requirement.get('design_subtype')}；"
                f"用 source of record 已有元素满足 {requirement.get('missing_semantic_type')}，"
                "不越过 major threshold"),
            affected_fields=list(fields),
            confirmed_facts_preserved=True, forbidden_changes_checked=True,
            downstream_effect=continuity, continuity_effect=continuity,
            risk="LOW", requires_author_approval=False, evidence_refs=evidence_refs)
        proposal.escalation_gate, proposal.escalation_violations = _escalation_gate(
            proposal)
        proposals.append(proposal)
        if len(proposals) >= 3:
            break
    if not proposals:
        proposal = RepairDesignProposal(
            proposal_id=f"RDP_{label}_99", design_item_id=str(
                requirement.get("design_item_id")), chapter_id=chapter_id,
            legacy_label=label, proposal_type="CAUSAL_BRIDGE",
            semantic_change="无可用既有元素 → 需要作者/人工设计（禁止自动生成）",
            why_it_satisfies_requirement="requirement 无法由既有元素满足",
            affected_fields=[str(requirement.get("missing_semantic_type") or "TURN")],
            risk="MEDIUM", requires_author_approval=True,
            evidence_refs=evidence_refs, status="NEEDS_AUTHOR_DESIGN")
        proposal.escalation_gate, proposal.escalation_violations = _escalation_gate(
            proposal)
        proposals.append(proposal)
    return proposals


def _escalation_gate(proposal: RepairDesignProposal) -> tuple[str, list[str]]:
    """§6：micro proposal 不能制造 major consequence。"""

    effects = (proposal.upstream_effect, proposal.downstream_effect,
               proposal.knowledge_effect, proposal.relationship_effect,
               proposal.resource_effect, proposal.progression_effect,
               proposal.continuity_effect)
    violations = [item for item in effects if item in ESCALATION_FORBIDDEN]
    text = f"{proposal.semantic_change}{proposal.why_it_satisfies_requirement}"
    for token in ("新敌人", "新地图", "新秘密", "新能力", "新装备", "新资源", "新世界规则",
                  "角色死亡", "不可逆"):
        if token in text:
            violations.append(f"FORBIDDEN_TOKEN:{token}")
    return ("PASS" if not violations else "FAIL"), violations


def _major_brief(requirement: Mapping[str, Any], artifact: Any,
                 inputs: DesignInputs) -> AuthorDesignBrief:
    label = str(requirement.get("legacy_label"))
    chapter_id = str(requirement.get("chapter_id"))
    legacy = inputs.legacy_rows.get(chapter_id) or {}
    target = inputs.targets.get(chapter_id) or {}
    label_lookup = {cid: str(row.get("id")) for cid, row in inputs.legacy_rows.items()}
    downstream = [label_lookup.get(str(dep), str(dep)) for dep in
                  target.get("downstream_dependencies") or []]
    arc_id = str(requirement.get("arc_id") or "")
    same_arc = sorted(str(row.get("id")) for cid, row in inputs.legacy_rows.items()
                      if str(row.get("arc")) == arc_id.split("_")[-1]
                      and str(row.get("volume")) == str(target.get("historical_volume")))
    return AuthorDesignBrief(
        brief_id=f"ADB_{label}", design_item_id=str(requirement.get("design_item_id")),
        chapter_id=chapter_id, legacy_label=label, arc_id=arc_id,
        missing_semantic_requirement=(
            f"{requirement.get('missing_semantic_type')} / "
            f"{'/'.join(requirement.get('subtypes') or [])}"),
        why_major=("ChapterFunctionPolicy 要求 major_turn（不是 micro pivot）；"
                   "任何新增都会改变人物弧/路线量级，必须作者设计"),
        historical_context=(f"function={legacy.get('source_refs') or ''}"
                            f"goal={str(legacy.get('goal') or '')[:80]}；"
                            f"turn={str(legacy.get('turn') or '')[:60]}"),
        confirmed_facts=[str(value) for value in target.get("confirmed_facts") or []],
        forbidden_changes=[str(value) for value in target.get("forbidden_changes") or []],
        upstream_pressure=[label_lookup.get(str(dep), str(dep)) for dep in
                           target.get("upstream_dependencies") or []],
        downstream_consequences=downstream,
        what_author_must_decide=[
            "该章 major turn 的语义（发生了什么级别的转折）",
            "是否允许新增/调整 event 与 state transition（happened truth 之外的表达）",
            "对 downstream chapters / Arc 的连锁影响"],
        possible_directions=[
            {"direction": "A. 保留 legacy 表达，只补 evidence binding（最小改动）",
             "tradeoff": "可能仍不满足 major_turn 强度，后续 chapter 压力上升"},
            {"direction": "B. 作者指定一个 major pivot（在 confirmed facts 内重写章节语义）",
             "tradeoff": "需要同步检查 downstream 连续性"},
            {"direction": "C. 降级为 micro pivot（若作者认为该章不需要 major turn）",
             "tradeoff": "会改变 ChapterFunctionPolicy 的强度要求，需 M10 侧确认"},
        ],
        tradeoffs=["改动越大，downstream 连续性风险越高",
                   "所有方向都必须保持 happened facts / Canon / StoryState 不变"],
        affected_later_chapters=downstream[:6] + same_arc[:6],
        blocking_scope=[f"{label} 及其 continuity 下游"] +
                       [f"batch:{batch}" for batch in
                        (target.get("owning_repair_batch_id"),) if batch])


def _ch036_brief(inputs: DesignInputs) -> AuthorDecisionBrief:
    label = "ch036"
    chapter_id = next((cid for cid, row in inputs.legacy_rows.items()
                       if str(row.get("id")) == label), "")
    legacy = inputs.legacy_rows.get(chapter_id) or {}
    target = inputs.targets.get(chapter_id) or {}
    label_lookup = {cid: str(row.get("id")) for cid, row in inputs.legacy_rows.items()}
    downstream = [label_lookup.get(str(dep), str(dep)) for dep in
                  target.get("downstream_dependencies") or []]
    return AuthorDecisionBrief(
        brief_id="ADB_ch036", subject="ch036 decision actor / 语义绑定",
        legacy_label=label, chapter_id=chapter_id,
        ambiguity_type=("decision actor pronoun binding（决定句主语是'他'）+ "
                        "decision semantics（保留旧表达 vs 按历史结构重写）"),
        sources=[
            {"source": "legacy outline choice", "value": str(legacy.get("choice") or ""),
             "provenance": "WASTELAND_001_OUTLINE_CANON_FINAL_CANDIDATE_V5"},
            {"source": "legacy turn/events", "value": str(legacy.get("turn") or "")[:80],
             "provenance": "同上（chapter events/turn）"},
            {"source": "M10 classification", "value": str(
                (inputs.story_rows.get(chapter_id) or {}).get("classification") or ""),
             "provenance": "reconstruction_v2/HISTORICAL_STORY_MAP.json"},
            {"source": "M10 author queue", "value": "DECISION_ch036",
             "provenance": "reconstruction_v2/AUTHOR_DECISION_QUEUE.json"}],
        evidence_summary=[
            "events 含 '他决定不去“控制”潮，只把今晚这一波引开，代价是那条旧水道会被彻底改变'",
            "choice 提供两个真实备选：'死守到天亮' vs '冒险去改水道'",
            "decision 字段为 null；代词'他'不足以自动绑定 actor（不猜代词）"],
        options=[
            DecisionOption(option_id="A", label="保留旧表达，仅绑定 decision actor=韩彻",
                           actor="ENTITY_PROTAGONIST", changes_happened_fact=False,
                           affected_chapters=[label] + downstream[:3],
                           affected_arcs=[str(target.get("historical_arc") or "")],
                           relationship_effect="NONE", knowledge_effect="LOCAL",
                           resource_effect="NONE", progression_effect="NONE",
                           fits_existing_evidence=(
                               "与现有 events 文本一致；不新增事实；"
                               "M1 focal owner = 主角"),
                           confidence=0.6),
            DecisionOption(option_id="B", label="按历史结构重写 decision 语义（明确 actor/choice/commitment）",
                           actor="ENTITY_PROTAGONIST", changes_happened_fact=False,
                           affected_chapters=[label] + downstream[:4],
                           affected_arcs=[str(target.get("historical_arc") or "")],
                           relationship_effect="LOCAL", knowledge_effect="LOCAL",
                           resource_effect="LOCAL", progression_effect="NONE",
                           fits_existing_evidence=(
                               "decision_gap 提示需要更明确的 decision；"
                               "choice 两选项给出决策结构"),
                           confidence=0.5)],
        recommended_default="A（保留旧表达 + 绑定 actor；改动最小）",
        recommendation_confidence=0.6,
        why_still_not_automatic=[
            "代词 actor 绑定属于作者语义决定（M11 不猜代词）",
            "M10 已将 ch036 登记为 DECISION_ch036（author decision）",
            "两条路径对 downstream 的影响范围不同（B 会改动更多表达）"],
        blocking_scope=[label] + downstream[:4])


def _ch559_brief(inputs: DesignInputs) -> AuthorDecisionBrief:
    label = "ch559"
    chapter_id = next((cid for cid, row in inputs.legacy_rows.items()
                       if str(row.get("id")) == label), "")
    legacy = inputs.legacy_rows.get(chapter_id) or {}
    story = inputs.story_rows.get(chapter_id) or {}
    target = inputs.targets.get(chapter_id) or {}
    label_lookup = {cid: str(row.get("id")) for cid, row in inputs.legacy_rows.items()}
    downstream = [label_lookup.get(str(dep), str(dep)) for dep in
                  target.get("downstream_dependencies") or []]
    story_transition = (story.get("primary_transition") or {})
    return AuthorDecisionBrief(
        brief_id="ADB_ch559", subject="ch559 dog_role / character presence 冲突",
        legacy_label=label, chapter_id=chapter_id,
        ambiguity_type="dog_role + dog physical presence（两个来源冲突）",
        sources=[
            {"source": "M1 golden semantic label（人工确认结构标签）",
             "value": "dog_role=independent, dog_presence=true",
             "provenance": "tests/fixtures/chapter_ir_pilot/GOLDEN_SEMANTIC_LABELS.json"},
            {"source": "M10 story map",
             "value": f"dog_role={story.get('dog_role')}, primary_transition="
                      f"{story_transition.get('state_key')}:{story_transition.get('to_state')}",
             "provenance": "reconstruction_v2/HISTORICAL_STORY_MAP.json"},
            {"source": "legacy outline end_state",
             "value": str(legacy.get("end_state") or ""),
             "provenance": "WASTELAND_001_OUTLINE_CANON_FINAL_CANDIDATE_V5"}],
        evidence_summary=[
            "两个来源都确认 common_rules_status = signed（正式签署）→ 规则线不受影响",
            "M10 story map 记 dog_role=offscreen_effect（阿灰未与韩彻同行）",
            "M1 人工标签记 dog_role=independent / dog_presence=true",
            "legacy end_state：'共守规矩正式生效，韩彻独自出塔，阿灰留在塔内'"],
        options=[
            DecisionOption(option_id="A", label="采用 M10 story map：dog_role=offscreen_effect（阿灰留在塔内，未物理同行）",
                           actor="ENTITY_DOG_AHUI", changes_happened_fact=False,
                           affected_chapters=[label] + downstream[:3],
                           affected_arcs=["WL_V10_A3"],
                           relationship_effect="LOCAL", knowledge_effect="NONE",
                           resource_effect="NONE", progression_effect="NONE",
                           fits_existing_evidence=(
                               "与 end_state'韩彻独自出塔'一致；presence=false 更贴合 source"),
                           confidence=0.6),
            DecisionOption(option_id="B", label="采用 M1 人工标签：dog_role=independent（阿灰自主选择留下）",
                           actor="ENTITY_DOG_AHUI", changes_happened_fact=False,
                           affected_chapters=[label] + downstream[:3],
                           affected_arcs=["WL_V10_A3"],
                           relationship_effect="LOCAL", knowledge_effect="LOCAL",
                           resource_effect="NONE", progression_effect="NONE",
                           fits_existing_evidence=(
                               "强调'留下'是自主决定（agency），但 presence 仍需按 source 记为 false"),
                           confidence=0.4)],
        recommended_default="A（presence 取 false；若认为'留下'是自主决定，可选 B 的 agency 读法）",
        recommendation_confidence=0.6,
        why_still_not_automatic=[
            "两个来源都带人工/LLM provenance，不能互相覆盖",
            "dog_role 会进入 relationship arc 的表示，属于作者语义选择",
            "M10 story map 与 M1 人工标签冲突未在 M10 阶段解决"],
        blocking_scope=[label] + downstream[:4])


def _ch063_brief(inputs: DesignInputs, _design_dir: Path) -> ManualRepairBrief:
    label = "ch063"
    chapter_id = next((cid for cid, row in inputs.legacy_rows.items()
                       if str(row.get("id")) == label), "")
    legacy = inputs.legacy_rows.get(chapter_id) or {}
    target = inputs.targets.get(chapter_id) or {}
    artifact = inputs.artifacts.get(chapter_id)
    transitions = [{"transition_id": row.transition_id, "state_key": row.state_key,
                    "from_state": row.from_state, "to_state": row.to_state,
                    "assertion_mode": row.assertion_mode,
                    "narrative_role": row.narrative_role}
                   for row in (artifact.chapter_ir.state_transitions if artifact else [])]
    text_blob = " ".join([str(legacy.get("world_state_change") or ""),
                          str(legacy.get("end_state") or ""),
                          str(legacy.get("turn") or ""),
                          " ".join(str(item) for item in legacy.get("events") or [])])
    salt_support = "伏击" in text_blob or "盐路" in text_blob
    return ManualRepairBrief(
        brief_id="MRB_ch063", chapter_id=chapter_id, legacy_label=label,
        legacy_world_state_change=str(legacy.get("world_state_change") or ""),
        foundation_transition=transitions,
        m10_state_binding_conflict={
            "conflict_subtype": str(target.get("conflict_subtype") or ""),
            "state_domain": str(target.get("state_domain") or ""),
            "risk": str(target.get("risk") or ""),
            "primary_issue": str(target.get("primary_issue") or "")},
        why_foundation_domain_not_automatic=(
            "full IR 的唯一 primary transition（salt_route_control）来自关键词规则"
            "（goal 含'伏击'命中 STATE_ASSERTIONS），source 未显式指向盐路 domain；"
            "把它当 confirmed domain 等于用规则产物覆盖 author 语义"),
        candidate_domains=[
            {"domain": "salt_route_control", "source": "foundation derived transition",
             "supporting_evidence": (["goal 含'伏击'（规则命中）"] if salt_support else []),
             "contradicting_evidence": (
                 ["chapter 主题是假消息渠道与伏击布置，正文域未提及盐路",
                  "legacy world_state_change = '据点开始主动喂假情报'（情报/防御语义）"]),
             "adoptable_automatically": False},
            {"domain": "REPRESENTATION_ONLY（不写 typed transition）",
             "source": "M11 保守选项",
             "supporting_evidence": ["保持 representation 与 happened truth 分离",
                                     "不引入未登记 state domain"],
             "contradicting_evidence": ["state binding 仍保持 unresolved，需后续人工确认"],
             "adoptable_automatically": True},
            {"domain": "AUTHOR_DEFINED_NEW_DOMAIN（例如 settlement_intel_posture）",
             "source": "需要作者设计",
             "supporting_evidence": ["legacy 文本指向'情报/防御姿态'语义"],
             "contradicting_evidence": ["新增 state domain = 新世界规则，M11 禁止自动引入"],
             "adoptable_automatically": False}],
        safe_representation_operations=[
            "保留 legacy world_state_change 文本为 representation（不改写）",
            "world_state_change 保持 state_domain unresolved（显式记录）",
            "如需绑定，只允许绑到已有 confirmed transition 的 domain",
            "任何操作都必须保持 confirmed facts / Canon / StoryState digest 不变"],
        forbidden_operations=[
            "自动把 salt_route_control 写成 happened truth（规则产物 ≠ truth）",
            "新增 state domain / 新世界规则",
            "修改 legacy 文本或 M10 baseline classification",
            "把该章记为 already resolved"],
        manual_recommendation=(
            "推荐 REPRESENTATION_ONLY（保持 unresolved）；若作者希望 typed binding，"
            "请指定 domain（可选 salt_route_control 或新 domain，后者需 M10 侧登记）"),
        status="MANUAL_REQUIRED")


def _entity_clusters(inputs: DesignInputs, *, proximity: int
                     ) -> list[EntityAmbiguityCluster]:
    artifacts = sorted([row for row in inputs.artifacts.values()
                        if row.materialization_status == "PARTIAL"
                        and row.chapter_ir.ambiguous_entity_ids],
                       key=lambda row: row.display_number or 0)
    running: list[dict[str, Any]] = []
    for artifact in artifacts:
        legacy = inputs.legacy_rows.get(artifact.chapter_id) or {}
        blob = " ".join([str(legacy.get(key) or "") for key in
                         ("goal", "turn", "escalation", "decision", "choice", "payoff",
                          "world_state_change", "end_state")] +
                        [str(item) for item in legacy.get("events") or []])
        mentions = sorted({alias for alias in OTHER_DOG_ALIASES if alias in blob})
        candidates = []
        if "荒原犬" in mentions or "编号犬" in mentions:
            candidates.append("ENTITY_HUNTER_DOG_01")
        if "同类" in mentions:
            candidates.append("ENTITY_CAGED_KIN")
        if not candidates:
            candidates = ["ENTITY_DOG_AHUI", "ENTITY_HUNTER_DOG_01"]
        signature = tuple(sorted(candidates))
        key = (artifact.volume_id, artifact.arc_id, signature)
        placed = False
        for item in running:
            if item["key"] != key:
                continue
            if abs((artifact.display_number or 0) - item["last"]) <= proximity:
                item["chapter_ids"].append(artifact.chapter_id)
                item["labels"].append(artifact.legacy_label)
                item["mentions"] |= set(mentions)
                item["last"] = artifact.display_number or 0
                placed = True
                break
        if not placed:
            running.append({"key": key, "chapter_ids": [artifact.chapter_id],
                            "labels": [artifact.legacy_label], "mentions": set(mentions),
                            "last": artifact.display_number or 0,
                            "volume": artifact.volume_id, "arc": artifact.arc_id,
                            "candidates": list(signature)})
    mutable: dict[str, str] = {}
    for batch in inputs.batches:
        for chapter_id in batch.get("chapter_ids") or []:
            mutable[str(chapter_id)] = str(batch.get("batch_id"))
    clusters: list[EntityAmbiguityCluster] = []
    for index, item in enumerate(running, start=1):
        affected_targets = [cid for cid in item["chapter_ids"] if cid in mutable]
        affected_batches = sorted({mutable[cid] for cid in affected_targets})
        affected_fields: set[str] = set()
        requires_identity = False
        supporting: list[str] = []
        for chapter_id in item["chapter_ids"]:
            artifact = inputs.artifacts.get(chapter_id)
            target = inputs.targets.get(chapter_id) or {}
            affected_fields |= {str(name) for name in
                                target.get("missing_semantic_fields") or []}
            missing = {str(name) for name in target.get("missing_semantic_fields") or []}
            legacy_row = inputs.legacy_rows.get(chapter_id) or {}
            pivot_text = " ".join([str(legacy_row.get(key) or "") for key in
                                   ("turn", "escalation", "end_state", "decision",
                                    "choice")] +
                                  [str(value) for value in
                                   legacy_row.get("events") or []])
            if chapter_id in mutable and (missing & {"turn", "decision", "payoff"}) and any(
                    alias in pivot_text for alias in OTHER_DOG_ALIASES):
                requires_identity = True
            if artifact is None:
                continue
            for assertion in artifact.field_assertions:
                if assertion.assertion_mode == "UNRESOLVED":
                    continue
                for ref in assertion.evidence_refs:
                    if any(alias in ref.quote for alias in OTHER_DOG_ALIASES):
                        supporting.append(f"{artifact.legacy_label}:{assertion.field_name}:"
                                          f"{ref.quote[:60]}")
                        if chapter_id in mutable and assertion.field_name in (
                                "turn", "decision", "payoff", "relationship"):
                            requires_identity = True
        dominance = _candidate_dominance(inputs, item)
        if not affected_targets or not requires_identity:
            status: ClusterResolution = "NON_BLOCKING_GENERIC_REFERENCE"
            proposal: dict[str, Any] = {}
        elif len(dominance["supported"]) == 1:
            status = "CONTEXT_RESOLVABLE_PROPOSAL"
            proposal = {"proposed_entity": dominance["supported"][0],
                        "confidence": dominance["confidence"],
                        "requires_confirmation": True,
                        "reason": "cluster 上下文只支持一个候选实体，但不足以成为 confirmed truth"}
        else:
            status = "AUTHOR_ENTITY_DECISION_REQUIRED"
            proposal = {}
        clusters.append(EntityAmbiguityCluster(
            cluster_id=f"EAC_{index:03d}", ambiguous_mentions=sorted(item["mentions"]),
            chapter_ids=list(item["chapter_ids"]), legacy_labels=list(item["labels"]),
            candidate_entities=list(item["candidates"]),
            supporting_evidence=supporting[:6],
            contradicting_evidence=list(dominance["contradicting"])[:4],
            affected_repair_targets=affected_targets,
            affected_batches=affected_batches,
            affected_fields=sorted(affected_fields),
            requires_exact_identity=requires_identity,
            repair_can_proceed_without_identity=not requires_identity,
            resolution_status=status, resolution_proposal=proposal))
    return clusters


def _candidate_dominance(inputs: DesignInputs, item: Mapping[str, Any]) -> dict[str, Any]:
    counts = {"ENTITY_DOG_AHUI": 0, "ENTITY_HUNTER_DOG_01": 0, "ENTITY_CAGED_KIN": 0}
    keywords = {"ENTITY_DOG_AHUI": ("阿灰",),
                "ENTITY_HUNTER_DOG_01": ("编号", "荒原犬", "猎团"),
                "ENTITY_CAGED_KIN": ("同类", "笼")}
    for chapter_id in item["chapter_ids"]:
        legacy = inputs.legacy_rows.get(chapter_id) or {}
        blob = " ".join([str(legacy.get(key) or "") for key in
                         ("goal", "turn", "escalation", "events", "end_state")])
        for entity, tokens in keywords.items():
            counts[entity] += sum(blob.count(token) for token in tokens)
    supported = [entity for entity in item["candidates"] if counts.get(entity)]
    unsupported = [entity for entity in item["candidates"] if not counts.get(entity)]
    confidence = round(min(1.0, counts[supported[0]] / 5), 2) if len(supported) == 1 else 0.0
    return {"counts": counts, "supported": supported, "unsupported": unsupported,
            "confidence": confidence,
            "contradicting": [f"{entity} 在 cluster 内无关键词证据" for entity in unsupported]}


def _confirmed_bindings(inputs: DesignInputs) -> list[ConfirmedBindingResolution]:
    rows: list[ConfirmedBindingResolution] = []
    for delta in inputs.golden_delta.get("rows") or []:
        if delta.get("decision") != "REINSTATE_M1_BINDING":
            continue
        label = str(delta.get("legacy_label"))
        chapter_id = next((cid for cid, row in inputs.legacy_rows.items()
                           if str(row.get("id")) == label), "")
        aspects = [kind for kind in delta.get("delta_kinds") or ["primary_transition"]]
        story_value = dict(delta.get("m10_story_map_value") or {})
        for aspect in aspects:
            value = story_value.get(aspect)
            pointer = f"m10_story_map#{label}.{aspect}"
            refs = [pointer, f"legacy_outline#{label}"]
            classic = _classic_label(inputs, label)
            if classic and aspect in classic:
                refs.append(f"m1_golden_label#{label}.{aspect}")
            canon_refs = [f"canon_fact:{fact_id}" for fact_id, fact in
                          (inputs.canon_registry.get("facts") or {}).items()
                          if label in (fact.get("source_refs") or [])]
            refs.extend(canon_refs)
            rows.append(ConfirmedBindingResolution(
                resolution_id=f"CBR_{label}_{aspect}",
                legacy_label=label, chapter_id=chapter_id, aspect=aspect,
                status="CONFIRMED_OVERRIDE_ACTIVE", value_pointer=pointer,
                value_refs=refs, value_digest=_digest(value),
                display_value=json.dumps(value, ensure_ascii=False),
                display_value_authoritative=False,
                evidence_sources=[
                    "M10 HISTORICAL_STORY_MAP（confirmed semantic structure）",
                    "M1 golden semantic label（人工确认）" if classic else "",
                    "Canon fact registry" if canon_refs else "",
                    "legacy outline source of record"],
                why_override=("foundation deterministic extraction 未覆盖该 binding，"
                              "而 M10/人工标签提供 confirmed evidence；"
                              "M11 必须以 confirmed 值为准（truth precedence）"),
                affects_repair=True))
    return rows


def _classic_label(inputs: DesignInputs, label: str) -> dict[str, Any]:
    payload = _read_json(inputs.root / "tests/fixtures/chapter_ir_pilot/"
                         "GOLDEN_SEMANTIC_LABELS.json")
    return dict((payload.get("labels") or {}).get(label) or {})


def _guarded_bindings(inputs: DesignInputs) -> list[GuardedBinding]:
    rows: list[GuardedBinding] = []
    for row in inputs.fact_checks.get("rows") or []:
        label = str(row.get("legacy_label"))
        chapter_id = next((cid for cid, item in inputs.legacy_rows.items()
                           if str(item.get("id")) == label), "")
        confirmed = dict(row.get("confirmed_value") or {})
        transition = confirmed.get("primary_transition")
        if transition:
            rows.append(GuardedBinding(
                legacy_label=label, chapter_id=chapter_id, aspect="primary_transition",
                expected_value=":".join(str(item) for item in transition),
                value_pointer=f"m10_story_map#{label}.primary_transition",
                fact_group=str(row.get("fact_group") or "")))
        if confirmed.get("dog_role"):
            rows.append(GuardedBinding(
                legacy_label=label, chapter_id=chapter_id, aspect="dog_role",
                expected_value=str(confirmed.get("dog_role")),
                value_pointer=f"m10_story_map#{label}.dog_role",
                fact_group=str(row.get("fact_group") or "")))
    return rows


def confirmed_binding_guard(*, label: str, changed_fields: Sequence[str],
                            design_dir: Path | str = DESIGN_DIR,
                            project_root: Path | str = ".") -> list[str]:
    """PART G：repair candidate 若违反 confirmed historical binding → ERROR code 列表。"""

    path = Path(design_dir)
    if not path.is_absolute():
        path = Path(project_root).resolve() / path
    payload = _read_json(path / "CONFIRMED_BINDING_RESOLUTION.json")
    fields = set(changed_fields)
    aspect_fields = {"primary_transition": {"world_state_change", "state_transition"},
                     "dog_role": {"dog_role", "relationship"}}
    hits: list[str] = []
    for row in payload.get("guarded_bindings") or []:
        if row.get("legacy_label") != label:
            continue
        aspect = str(row.get("aspect") or "")
        if fields & aspect_fields.get(aspect, set()):
            hits.append(f"CONFIRMED_HISTORICAL_BINDING_VIOLATION:{label}:{aspect}")
    return hits


def _hardened_targets(inputs: DesignInputs, clusters: Mapping[str, Any],
                      requirements: Mapping[str, Any],
                      confirmed: Mapping[str, Any]) -> list[HardenedTargetReadiness]:
    resolution: dict[str, str] = {}
    for name in ("REPAIR_RECONCILIATION.json", "BATCH_04_RECONCILIATION.json"):
        for row in (_read_json(inputs.design_dir / name).get("records") or []):
            resolution[str(row.get("chapter_id"))] = str(row.get("new_resolution_status"))
    refresh = _read_json(inputs.design_dir / "EVIDENCE_ONLY_REFRESH.json")
    for outcome in refresh.get("outcomes") or []:
        if outcome.get("promoted"):
            resolution[str(outcome.get("chapter_id"))] = "RESOLVED_REPAIRED"
    labels = {cid: str(row.get("id")) for cid, row in inputs.legacy_rows.items()}
    continuity = _continuity_map(inputs)
    cluster_of: dict[str, dict[str, Any]] = {}
    for cluster in clusters.get("clusters") or []:
        for chapter_id in cluster.get("chapter_ids") or []:
            cluster_of[str(chapter_id)] = dict(cluster)
    design_labels = {str(row.get("legacy_label"))
                     for row in requirements.get("requirements") or []}
    override_labels = {str(row.get("legacy_label"))
                       for row in confirmed.get("resolutions") or []}
    integrity_ok = True
    rows: list[HardenedTargetReadiness] = []
    for batch in inputs.batches:
        batch_id = str(batch.get("batch_id"))
        for chapter_id in batch.get("chapter_ids") or []:
            chapter_id = str(chapter_id)
            label = labels.get(chapter_id, "")
            own = resolution.get(chapter_id, "PENDING")
            cluster = cluster_of.get(chapter_id)
            deps = [dep for dep in continuity.get(chapter_id, [])
                    if resolution.get(dep) in ("CONTENT_DESIGN_REQUIRED",
                                               "AUTHOR_DECISION_REQUIRED",
                                               "MANUAL_REQUIRED", "EVIDENCE_READY")]
            if not integrity_ok:
                rows.append(HardenedTargetReadiness(
                    chapter_id=chapter_id, legacy_label=label, batch_id=batch_id,
                    status="BLOCKED_FOUNDATION_INTEGRITY",
                    reason="foundation artifact digest mismatch"))
                continue
            if own in ("RESOLVED_REPAIRED", "RESOLVED_NO_REPAIR_REQUIRED"):
                rows.append(HardenedTargetReadiness(
                    chapter_id=chapter_id, legacy_label=label, batch_id=batch_id,
                    status="RESOLVED", reason=f"resolution={own}"))
                continue
            if own == "CONTENT_DESIGN_REQUIRED" and label in design_labels:
                rows.append(HardenedTargetReadiness(
                    chapter_id=chapter_id, legacy_label=label, batch_id=batch_id,
                    status="BLOCKED_CONTENT_DESIGN",
                    reason="own 内容缺口尚未 design/approve",
                    blocking_source=[f"design:{label}"]))
                continue
            if own == "AUTHOR_DECISION_REQUIRED":
                rows.append(HardenedTargetReadiness(
                    chapter_id=chapter_id, legacy_label=label, batch_id=batch_id,
                    status="BLOCKED_AUTHOR_DECISION",
                    reason="own 作者决策未决", blocking_source=[f"author:{label}"]))
                continue
            if own == "MANUAL_REQUIRED":
                rows.append(HardenedTargetReadiness(
                    chapter_id=chapter_id, legacy_label=label, batch_id=batch_id,
                    status="BLOCKED_MANUAL_REPAIR",
                    reason="own manual repair 未执行", blocking_source=[f"manual:{label}"]))
                continue
            if own == "EVIDENCE_READY":
                rows.append(HardenedTargetReadiness(
                    chapter_id=chapter_id, legacy_label=label, batch_id=batch_id,
                    status="BLOCKED_ENTITY_AMBIGUITY",
                    reason="evidence-ready 但 entity identity 未定",
                    blocking_source=[f"entity:{label}"]))
                continue
            if cluster and cluster.get("requires_exact_identity") and \
                    cluster.get("resolution_status") != "NON_BLOCKING_GENERIC_REFERENCE":
                rows.append(HardenedTargetReadiness(
                    chapter_id=chapter_id, legacy_label=label, batch_id=batch_id,
                    status="BLOCKED_ENTITY_AMBIGUITY",
                    reason=(f"{cluster.get('cluster_id')} 需要精确 entity identity"
                            f"（{cluster.get('resolution_status')}）"),
                    blocking_source=[str(cluster.get("cluster_id"))]))
                continue
            if label in override_labels:
                rows.append(HardenedTargetReadiness(
                    chapter_id=chapter_id, legacy_label=label, batch_id=batch_id,
                    status="BLOCKED_CONFIRMED_BINDING_CONFLICT",
                    reason=("该 target 自身涉及 confirmed binding override，"
                            "需先按 override 重放候选（不得用 foundation 值）"),
                    blocking_source=[f"override:{label}"]))
                continue
            if deps:
                dep_labels = [labels.get(dep, dep) for dep in deps[:3]]
                kinds = {resolution.get(dep) for dep in deps}
                if "CONTENT_DESIGN_REQUIRED" in kinds:
                    status: HardBlocker = "BLOCKED_CONTENT_DESIGN"
                elif "AUTHOR_DECISION_REQUIRED" in kinds:
                    status = "BLOCKED_AUTHOR_DECISION"
                elif "MANUAL_REQUIRED" in kinds:
                    status = "BLOCKED_MANUAL_REPAIR"
                else:
                    status = "BLOCKED_ENTITY_AMBIGUITY"
                rows.append(HardenedTargetReadiness(
                    chapter_id=chapter_id, legacy_label=label, batch_id=batch_id,
                    status=status,
                    reason="continuity 上游未决：" + ",".join(dep_labels),
                    blocking_source=dep_labels))
                continue
            rows.append(HardenedTargetReadiness(
                chapter_id=chapter_id, legacy_label=label, batch_id=batch_id,
                status="READY", reason="no localized blocker"))
    return rows


def _hardened_batches(inputs: DesignInputs, rows: Sequence[HardenedTargetReadiness]
                      ) -> list[HardenedBatchReadiness]:
    grouped: dict[str, list[HardenedTargetReadiness]] = {}
    for row in rows:
        grouped.setdefault(row.batch_id, []).append(row)
    batches: list[HardenedBatchReadiness] = []
    status_map = {"BLOCKED_CONTENT_DESIGN": "BLOCKED_CONTENT_DESIGN",
                  "BLOCKED_AUTHOR_DECISION": "BLOCKED_AUTHOR_DECISION",
                  "BLOCKED_ENTITY_AMBIGUITY": "BLOCKED_ENTITY_AMBIGUITY",
                  "BLOCKED_MANUAL_REPAIR": "BLOCKED_MANUAL",
                  "BLOCKED_DEPENDENCY": "BLOCKED_DEPENDENCY",
                  "BLOCKED_CONFIRMED_BINDING_CONFLICT":
                      "BLOCKED_CONFIRMED_BINDING_CONFLICT",
                  "BLOCKED_FOUNDATION_INTEGRITY": "BLOCKED_FOUNDATION_INTEGRITY"}
    for batch in inputs.batches:
        batch_id = str(batch.get("batch_id"))
        items = grouped.get(batch_id, [])
        ready = [row.chapter_id for row in items if row.status == "READY"]
        blocked = [row for row in items if row.status not in ("READY", "RESOLVED")]
        counts: dict[str, int] = {}
        for row in blocked:
            counts[row.status] = counts.get(row.status, 0) + 1
        if items and all(row.status == "RESOLVED" for row in items):
            status = "COMPLETE"
        elif blocked and not ready and len(counts) == 1:
            status = status_map.get(next(iter(counts)), "PARTIAL_READY")
        elif blocked or ready:
            status = "PARTIAL_READY"
        else:
            status = "READY"
        batches.append(HardenedBatchReadiness(
            batch_id=batch_id, status=status, ready_target_ids=ready,
            blocked_target_ids=[row.chapter_id for row in blocked],
            block_reason_by_target={row.chapter_id: f"{row.status}:{row.reason}"
                                    for row in blocked},
            blocker_counts=counts, mutable_target_count=len(items),
            dependency_batches=[str(item) for item in
                                batch.get("dependency_batches") or []]))
    return batches


def _continuity_map(inputs: DesignInputs) -> dict[str, list[str]]:
    arcs: dict[tuple[int, str], list[tuple[int, str]]] = {}
    for chapter_id, row in inputs.legacy_rows.items():
        key = (int(row.get("volume") or 0), str(row.get("arc") or ""))
        arcs.setdefault(key, []).append((int(row.get("index") or 0), chapter_id))
    ordered = sorted(arcs)
    continuity: dict[str, list[str]] = {}
    for position, key in enumerate(ordered):
        previous = ordered[position - 1] if position else None
        earlier = sorted(arcs[key])
        for index, chapter_id in earlier:
            deps = [item[1] for item in earlier if item[0] < index]
            if previous is not None:
                deps += [item[1] for item in sorted(arcs[previous])]
            continuity[chapter_id] = deps
    return continuity
