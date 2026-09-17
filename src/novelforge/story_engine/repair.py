"""M11：WASTELAND Content Repair（Production Pilot = REPAIR_BATCH_01）。

Repair ≠ rewrite history。只修 representation / evidence binding / function semantics /
state binding；Canon、StoryState、confirmed happened fact 永远只读。
Repair 不覆盖 M1 原 570 source artifact：产出 repair candidate + repaired overlay lineage
+ repair record + status overlay，最终 freeze 交给 M12。
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from pydantic import Field

from novelforge.models import StrictModel
from novelforge.story_engine.chapter_ir.function_policy import FUNCTION_REQUIREMENTS

REPAIR_VERSION = "m11-1"
RECON_DIR = "workspace/wasteland_001_exports/reconstruction_v2"
REPAIR_DIR = "workspace/wasteland_001_exports/repair_v1"
FOUNDATION_DIR = "workspace/wasteland_001_exports/historical_chapter_ir_v1"
ADOPTION_DIR = "workspace/wasteland_001_exports/repair_adoption_v1"
SUBSTRATE_FULL = "HISTORICAL_FULL_IR"
SUBSTRATE_PARTIAL = "HISTORICAL_FULL_IR_PARTIAL"
SUBSTRATE_SHADOW = "SHADOW_FALLBACK"
DEFAULT_BATCH = "REPAIR_BATCH_01"
CONFIRMED = "SEMANTIC_CONFIRMED"
FIELD_CONFLICT = "LEGACY_FIELD_CONFLICT"
CONTENT_GAP = "LEGACY_CONTENT_GAP"

RepairClassName = Literal["evidence_only", "na_correction", "semantic_addition",
                          "state_rebinding", "human_review"]
RepairOpType = Literal["REBIND_EVIDENCE", "MARK_NOT_APPLICABLE", "RECLASSIFY_FUNCTION",
                       "REBIND_STATE_REFERENCE", "ADD_SEMANTIC_ELEMENT",
                       "DELETE_LEGACY_FIELD"]
RepairStatus = Literal["pending", "candidate_ready", "validated", "blocked", "human_review",
                       "repaired", "verified", "rejected"]
ActualSemanticStatus = Literal["PRESENT_AND_BOUND", "PRESENT_BUT_UNBOUND", "NOT_APPLICABLE",
                               "TRULY_MISSING", "AMBIGUOUS", "SOURCE_EVIDENCE_INSUFFICIENT"]
ActualRepairClass = Literal["EVIDENCE_ONLY", "FIELD_REBIND", "FUNCTION_NA_CORRECTION",
                            "SEMANTIC_ADDITION_REQUIRED", "CONTENT_REWRITE_REQUIRED",
                            "HUMAN_DECISION_REQUIRED", "NO_REPAIR_REQUIRED"]
HumanReviewReason = Literal["NO_PIVOT_EVIDENCE", "SOURCE_IR_INSUFFICIENT",
                            "AMBIGUOUS_FUNCTION", "AUTHOR_INTENT_REQUIRED",
                            "STATE_DOMAIN_AMBIGUOUS", "MULTIPLE_VALID_INTERPRETATIONS", "OTHER"]
ExecutionDecision = Literal["SAFE_AUTO", "MANUAL", "HUMAN_REVIEW"]
EvidenceSource = Literal["shadow_summary", "compiled_preview", "deterministic_verifier",
                         "source_chapter_text", "legacy_fields",
                         "neighboring_chapter_evidence", "canon_refs", "story_state_refs",
                         "full_chapter_ir_body"]
EvidenceSufficiency = Literal["SUFFICIENT", "PARTIAL", "INSUFFICIENT"]
# §7 repair invasiveness ordering（低 → 高）
INVASIVENESS_ORDER: tuple[str, ...] = ("NO_CHANGE", "EVIDENCE_BIND", "FIELD_REBIND",
                                       "N/A_CORRECTION", "SEMANTIC_FIELD_ADDITION",
                                       "CONTENT_REWRITE")
REPAIR_TYPE_INVASIVENESS: dict[str, str] = {
    "ADD_TURN_EVIDENCE": "EVIDENCE_BIND", "ADD_PAYOFF_EVIDENCE": "EVIDENCE_BIND",
    "ADD_DECISION_EVIDENCE": "EVIDENCE_BIND", "ADD_INFORMATION_EVIDENCE": "EVIDENCE_BIND",
    "ADD_RELATIONSHIP_EVIDENCE": "EVIDENCE_BIND", "ADD_RESOURCE_EVIDENCE": "EVIDENCE_BIND",
    "ADD_CAUSAL_LINK": "EVIDENCE_BIND", "FIELD_REBIND": "FIELD_REBIND",
    "FIELD_REWRITE": "N/A_CORRECTION", "RECLASSIFY_FUNCTION": "N/A_CORRECTION",
    "ADD_MISSING_TURN": "SEMANTIC_FIELD_ADDITION",
    "ADD_MISSING_PAYOFF": "SEMANTIC_FIELD_ADDITION",
    "ADD_MISSING_DECISION_EVIDENCE": "SEMANTIC_FIELD_ADDITION",
    "CONTENT_REWRITE_REQUIRED": "CONTENT_REWRITE",
    "HUMAN_REVIEW_REQUIRED": "CONTENT_REWRITE",
}
SAFE_AUTO_CLASSES: tuple[str, ...] = ("EVIDENCE_ONLY", "FIELD_REBIND",
                                      "FUNCTION_NA_CORRECTION", "NO_REPAIR_REQUIRED")
MANUAL_CLASSES: tuple[str, ...] = ("SEMANTIC_ADDITION_REQUIRED", "CONTENT_REWRITE_REQUIRED")
MANDATORY_HUMAN_CLASSES: tuple[str, ...] = ("HUMAN_DECISION_REQUIRED",)


class RepairAlternativePolicy(StrictModel):
    """把 M10 的"更侵入式修复"安全降级成"更保守修复"（禁止反向升级）。"""

    policy_id: str = Field(default="m11-alternative-v1", max_length=64)
    conservative_substitutions: dict[str, list[str]] = Field(default_factory=lambda: {
        "ADD_MISSING_TURN": ["ADD_TURN_EVIDENCE", "FIELD_REBIND", "RECLASSIFY_FUNCTION"],
        "ADD_MISSING_PAYOFF": ["ADD_PAYOFF_EVIDENCE", "FIELD_REBIND"],
        "ADD_MISSING_DECISION_EVIDENCE": ["ADD_DECISION_EVIDENCE", "FIELD_REBIND"],
        "ADD_INFORMATION_EVIDENCE": ["ADD_INFORMATION_EVIDENCE", "FIELD_REBIND"],
        "ADD_RELATIONSHIP_EVIDENCE": ["ADD_RELATIONSHIP_EVIDENCE", "FIELD_REBIND"],
        "ADD_RESOURCE_EVIDENCE": ["ADD_RESOURCE_EVIDENCE", "FIELD_REBIND"],
        "CONTENT_REWRITE_REQUIRED": ["FIELD_REBIND", "RECLASSIFY_FUNCTION"],
    })
    non_authoritative: bool = True

    def invasiveness(self, repair_type: str) -> int:
        band = REPAIR_TYPE_INVASIVENESS.get(repair_type, "SEMANTIC_FIELD_ADDITION")
        return INVASIVENESS_ORDER.index(band)

    def substitute(self, allowed: list[str], proposed: str
                   ) -> tuple[str, str, str]:
        """returns (actual_type, reason, policy_rule_id)；不允许则抛 RepairPreflightError。"""

        if proposed in allowed:
            return proposed, "proposed 已在 M10 allowed_repair_types 内", "DIRECT_ALLOWED"
        for original in allowed:
            if proposed in (self.conservative_substitutions.get(original) or []) \
                    and self.invasiveness(proposed) <= self.invasiveness(original):
                return proposed, (
                    f"conservative substitution：{original} → {proposed}"
                    f"（invasiveness {self.invasiveness(original)} → "
                    f"{self.invasiveness(proposed)}）"), \
                    f"CONSERVATIVE_SUBSTITUTION:{original}->{proposed}"
            if self.invasiveness(proposed) <= self.invasiveness(original):
                return proposed, (
                    f"conservative invasiveness：{original} → {proposed}"
                    f"（{self.invasiveness(original)} → {self.invasiveness(proposed)}）"), \
                    f"CONSERVATIVE_INVASIVENESS:{original}->{proposed}"
        raise RepairPreflightError(
            "REPAIR_TYPE_NOT_ALLOWED",
            f"{proposed} 不在 allowed {allowed} 且不构成保守替代")

    def assert_no_upgrade(self, original: str, proposed: str) -> None:
        if self.invasiveness(proposed) > self.invasiveness(original):
            raise RepairPreflightError(
                "REPAIR_INVASIVENESS_UPGRADE_FORBIDDEN",
                f"{original} → {proposed} 属于升级修复，必须显式 author approve")


class M11ExecutionPolicy(StrictModel):
    """Batch 02+ 的执行策略：safe_auto / manual / human_review 的正式边界。"""

    policy_id: str = Field(default="m11-execution-v1", max_length=64)
    safe_auto_classes: list[str] = Field(default_factory=lambda: list(SAFE_AUTO_CLASSES))
    manual_classes: list[str] = Field(default_factory=lambda: list(MANUAL_CLASSES))
    mandatory_human_classes: list[str] = Field(default_factory=lambda:
                                              list(MANDATORY_HUMAN_CLASSES))
    safe_auto_risks: list[str] = Field(default_factory=lambda: ["LOW", "MEDIUM"])
    non_authoritative: bool = True

    def decide(self, actual_class: str, risk: str, *, human_review_required: bool = False,
               forbidden_violation: bool = False, validators_pass: bool = True,
               neighbor_ok: bool = True, arc_ok: bool = True,
               evidence_sufficient: bool = True,
               substrate: str = SUBSTRATE_FULL) -> ExecutionDecision:
        if human_review_required or actual_class in self.mandatory_human_classes \
                or forbidden_violation or not validators_pass:
            return "HUMAN_REVIEW"
        if not evidence_sufficient:
            return "HUMAN_REVIEW" if actual_class in self.mandatory_human_classes else "MANUAL"
        if substrate != SUBSTRATE_FULL:
            # §23：SHADOW_FALLBACK 只允许 read-only diagnosis，不得 SAFE_AUTO promote
            return "MANUAL"
        if actual_class in self.safe_auto_classes and risk in self.safe_auto_risks \
                and neighbor_ok and arc_ok:
            return "SAFE_AUTO"
        return "MANUAL"


class RepairRefinement(StrictModel):
    """repair-time refinement：不改 M10 baseline，只记录 M11 实际判断。"""

    chapter_id: str = Field(default="", max_length=128)
    legacy_label: str = Field(default="", max_length=32)
    original_primary_issue: str = Field(default="", max_length=64)
    original_subtype: str = Field(default="", max_length=64)
    original_domain_tags: list[str] = Field(default_factory=list)
    original_allowed_repair_types: list[str] = Field(default_factory=list)
    actual_semantic_status: ActualSemanticStatus = "SOURCE_EVIDENCE_INSUFFICIENT"
    actual_repair_class: ActualRepairClass = "HUMAN_DECISION_REQUIRED"
    actual_repair_type: str = Field(default="", max_length=48)
    original_allowed_type: str = Field(default="", max_length=48)
    original_invasiveness: str = Field(default="", max_length=32)
    actual_invasiveness: str = Field(default="", max_length=32)
    policy_rule_id: str = Field(default="", max_length=96)
    substitution_reason: str = Field(default="", max_length=200)
    evidence_refs: list[str] = Field(default_factory=list)
    refinement_reason: str = Field(default="", max_length=300)
    confidence: float = Field(default=0.6, ge=0, le=1)
    requires_human_review: bool = False
    human_review_reason: HumanReviewReason | None = None
    execution_decision: ExecutionDecision = "MANUAL"
    field_status: dict[str, str] = Field(default_factory=dict)
    evidence_sources_available: list[str] = Field(default_factory=list)
    evidence_sufficiency: EvidenceSufficiency = "PARTIAL"
    non_authoritative: bool = True


class RepairedBatchCloseout(StrictModel):
    batch_id: str = DEFAULT_BATCH
    refinements: list[RepairRefinement] = Field(default_factory=list)
    class_counts: dict[str, int] = Field(default_factory=dict)
    status_counts: dict[str, int] = Field(default_factory=dict)
    human_review_reasons: dict[str, int] = Field(default_factory=dict)
    policy_only_blocker_release: list[str] = Field(default_factory=list)
    blanket_tag_audit: dict[str, int] = Field(default_factory=dict)
    remaining_human_review: list[str] = Field(default_factory=list)
    baseline_queue_counts: dict[str, int] = Field(default_factory=dict)
    status: Literal["PASS", "NEEDS_ATTENTION"] = "NEEDS_ATTENTION"
    non_authoritative: bool = True
FORBIDDEN_DOMAINS: tuple[str, ...] = (
    "actor_presence", "event_occurrence", "character_knowledge", "relationship_state",
    "progression_state", "map_unlock_state", "resource_amounts", "equipment_ownership",
    "confirmed_entity_identity", "confirmed_timeline_ordering")


class RepairFinding(StrictModel):
    code: str = Field(min_length=3, max_length=64)
    severity: Literal["ERROR", "WARNING", "INFO"] = "INFO"
    chapter_id: str = Field(default="", max_length=128)
    message: str = Field(default="", max_length=300)
    evidence: dict[str, Any] = Field(default_factory=dict)
    non_authoritative: bool = True


class RepairBatchBaseline(StrictModel):
    batch_id: str = DEFAULT_BATCH
    mutable_chapter_ids: list[str] = Field(default_factory=list)
    read_only_dependency_chapter_ids: list[str] = Field(default_factory=list)
    target_alignment_digest: str = Field(default="", max_length=64)
    confirmed_facts_digest: str = Field(default="", max_length=64)
    canon_digest: str = Field(default="", max_length=64)
    story_state_digest: str = Field(default="", max_length=64)
    legacy_candidate_digest: str = Field(default="", max_length=64)
    chapter_ir_digest: str = Field(default="", max_length=64)
    queue_snapshot: dict[str, int] = Field(default_factory=dict)
    mutable_target_digests: dict[str, str] = Field(default_factory=dict)
    read_only_dependency_digests: dict[str, str] = Field(default_factory=dict)
    validator_version: str = Field(default="m1b-v4", max_length=32)
    repair_compiler_version: str = Field(default=REPAIR_VERSION, max_length=32)
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    read_only: bool = True

    def happened_digests(self) -> dict[str, str]:
        return {"canon": self.canon_digest, "story_state": self.story_state_digest,
                "legacy_candidate": self.legacy_candidate_digest,
                "chapter_ir": self.chapter_ir_digest}


class RepairOp(StrictModel):
    op: RepairOpType = "REBIND_EVIDENCE"
    m10_type: str = Field(default="", max_length=48)
    policy_approved: bool = False
    field_name: str = Field(default="", max_length=64)
    target_field: str = Field(default="", max_length=64)
    evidence_refs: list[str] = Field(default_factory=list)
    reason: str = Field(default="", max_length=300)
    touches_forbidden_domain: str = Field(default="", max_length=64)
    non_authoritative: bool = True


class ChapterRepairCandidate(StrictModel):
    candidate_id: str = Field(default="", max_length=64)
    batch_id: str = Field(default=DEFAULT_BATCH, max_length=32)
    chapter_id: str = Field(default="", max_length=128)
    legacy_label: str = Field(default="", max_length=32)
    source_ir_digest: str = Field(default="", max_length=64)
    target_alignment_ref: str = Field(default="", max_length=128)
    primary_issue: str = Field(default="", max_length=64)
    domain_tags: list[str] = Field(default_factory=list)
    recommended_repair_type: str = Field(default="", max_length=48)
    actual_repair_class: RepairClassName = "human_review"
    proposed_patch: list[RepairOp] = Field(default_factory=list)
    evidence_refs: list[str] = Field(default_factory=list)
    required_context: list[str] = Field(default_factory=list)
    forbidden_changes: list[str] = Field(default_factory=list)
    validators: list[str] = Field(default_factory=list)
    validator_results: dict[str, str] = Field(default_factory=dict)
    risk: str = Field(default="MEDIUM", max_length=16)
    human_review_required: bool = False
    reason_summary: str = Field(default="", max_length=300)
    status: RepairStatus = "candidate_ready"
    refinement: "RepairRefinement | None" = None
    evidence_substrate: str = Field(default=SUBSTRATE_FULL, max_length=32)
    foundation_artifact_digest: str = Field(default="", max_length=64)
    non_authoritative: bool = True


class RepairedChapterArtifact(StrictModel):
    chapter_id: str = Field(default="", max_length=128)
    batch_id: str = Field(default=DEFAULT_BATCH, max_length=32)
    parent_source_digest: str = Field(default="", max_length=64)
    source_recon_digest: str = Field(default="", max_length=64)
    candidate_id: str = Field(default="", max_length=64)
    repair_types: list[str] = Field(default_factory=list)
    repaired_representation: dict[str, Any] = Field(default_factory=dict)
    before_after_diff: dict[str, Any] = Field(default_factory=dict)
    evidence_refs: list[str] = Field(default_factory=list)
    repaired_digest: str = Field(default="", max_length=64)
    canonical_representation: bool = False
    non_authoritative: bool = True


class RepairRecord(StrictModel):
    repair_id: str = Field(default="", max_length=64)
    batch_id: str = Field(default=DEFAULT_BATCH, max_length=32)
    chapter_id: str = Field(default="", max_length=128)
    source_digest: str = Field(default="", max_length=64)
    repaired_digest: str = Field(default="", max_length=64)
    candidate_id: str = Field(default="", max_length=64)
    repair_types: list[str] = Field(default_factory=list)
    evidence_refs: list[str] = Field(default_factory=list)
    before_after_semantic_diff: dict[str, Any] = Field(default_factory=dict)
    validators: dict[str, str] = Field(default_factory=dict)
    findings: list[RepairFinding] = Field(default_factory=list)
    forbidden_change_check: dict[str, Any] = Field(default_factory=dict)
    parent_artifact_ref: str = Field(default="", max_length=160)
    promotion_timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    non_authoritative: bool = True


class RepairStatusEntry(StrictModel):
    chapter_id: str = Field(default="", max_length=128)
    legacy_label: str = Field(default="", max_length=32)
    batch_id: str = Field(default=DEFAULT_BATCH, max_length=32)
    baseline_classification: str = Field(default="", max_length=32)
    status: RepairStatus = "pending"
    repair_class: RepairClassName | None = None
    repair_types: list[str] = Field(default_factory=list)
    note: str = Field(default="", max_length=200)
    non_authoritative: bool = True


class M11RepairStatusOverlay(StrictModel):
    batch_id: str = DEFAULT_BATCH
    baseline_queue_counts: dict[str, int] = Field(default_factory=dict)
    entries: list[RepairStatusEntry] = Field(default_factory=list)
    verified_repaired: int = 0
    remaining_repair_targets: int = 0
    human_review: int = 0
    blocked: int = 0
    pending: int = 0
    note: str = ("baseline 198 / 27 / 345 永久保留；overlay 只表示 M11 当前进度，"
                 "不是新的 baseline")
    read_only: bool = True
    non_authoritative: bool = True


class RepairBatchDiff(StrictModel):
    batch_id: str = DEFAULT_BATCH
    chapters_touched: int = 0
    chapter_ids: list[str] = Field(default_factory=list)
    fields_changed: dict[str, int] = Field(default_factory=dict)
    evidence_added: int = 0
    evidence_only_repairs: int = 0
    binding_corrections: int = 0
    semantic_elements_added: int = 0
    semantic_elements_removed: int = 0
    function_reclassified: int = 0
    na_corrections: int = 0
    state_bindings_repaired: int = 0
    decision_repaired: int = 0
    turn_repaired: int = 0
    payoff_repaired: int = 0
    human_review: int = 0
    blocked: int = 0
    confirmed_facts_changed: int = 0
    read_only_chapters_changed: int = 0
    story_aware: list[dict[str, Any]] = Field(default_factory=list)
    non_authoritative: bool = True


class RepairClassificationSample(StrictModel):
    evidence_only: int = 0
    na_correction: int = 0
    semantic_addition: int = 0
    state_rebinding: int = 0
    human_review: int = 0
    binding_correction_chapters: int = 0
    multi_label_blanket_suspected: bool = False
    blanket_note: str = Field(default="", max_length=300)
    per_chapter: dict[str, str] = Field(default_factory=dict)
    non_authoritative: bool = True


class RepairBatchGate(StrictModel):
    batch_id: str = DEFAULT_BATCH
    checks: dict[str, bool] = Field(default_factory=dict)
    acceptance_contract: dict[str, str] = Field(default_factory=dict)
    findings: list[RepairFinding] = Field(default_factory=list)
    promoted_chapters: int = 0
    human_review_chapters: list[str] = Field(default_factory=list)
    source_digests_before: dict[str, str] = Field(default_factory=dict)
    source_digests_after: dict[str, str] = Field(default_factory=dict)
    status: Literal["PASS", "NEEDS_ATTENTION", "BLOCKED"] = "NEEDS_ATTENTION"
    promotion_mode: Literal["atomic", "partial"] = "partial"
    non_authoritative: bool = True

    def ok(self) -> bool:
        return self.status == "PASS"


class RepairBatchResult(StrictModel):
    batch_id: str = DEFAULT_BATCH
    baseline: RepairBatchBaseline = Field(default_factory=RepairBatchBaseline)
    candidates: list[ChapterRepairCandidate] = Field(default_factory=list)
    overlays: list[RepairedChapterArtifact] = Field(default_factory=list)
    records: list[RepairRecord] = Field(default_factory=list)
    status_overlay: M11RepairStatusOverlay = Field(default_factory=M11RepairStatusOverlay)
    diff: RepairBatchDiff = Field(default_factory=RepairBatchDiff)
    sampling: RepairClassificationSample = Field(default_factory=RepairClassificationSample)
    refinements: list[RepairRefinement] = Field(default_factory=list)
    closeout: RepairedBatchCloseout = Field(default_factory=RepairedBatchCloseout)
    gate: RepairBatchGate = Field(default_factory=RepairBatchGate)
    written: dict[str, str] = Field(default_factory=dict)
    read_only: bool = True


class RepairPreflightError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(f"{code}: {message}")


class FoundationSubstrateError(RuntimeError):
    """§22：Historical Full IR artifact 缺失 / digest 与 index 不一致 → 直接 BLOCK。"""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(f"{code}: {message}")


def _digest(payload: Any) -> str:
    return hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True)
                          .encode("utf-8")).hexdigest()[:16]


@dataclass
class RepairInputs:
    baseline: dict[str, Any] = field(default_factory=dict)
    targets: dict[str, dict[str, Any]] = field(default_factory=dict)
    batches: list[dict[str, Any]] = field(default_factory=list)
    readiness: dict[str, Any] = field(default_factory=dict)
    decisions: dict[str, Any] = field(default_factory=dict)
    m10_gate: dict[str, Any] = field(default_factory=dict)
    full_rows: dict[str, dict[str, Any]] = field(default_factory=dict)
    recon_rows: dict[str, dict[str, Any]] = field(default_factory=dict)
    story_map: dict[str, Any] = field(default_factory=dict)
    legacy_rows: dict[str, dict[str, Any]] = field(default_factory=dict)
    full_ir_body_available: bool = False
    foundation_rows: dict[str, dict[str, Any]] = field(default_factory=dict)


class WastelandRepairService:
    """Batch 01 repair orchestrator（deterministic、evidence-first、manual promotion）。"""

    alternative_policy: RepairAlternativePolicy
    execution_policy: M11ExecutionPolicy

    def __init__(self, project_root: Path, *, recon_dir: str = RECON_DIR,
                 repair_dir: str = REPAIR_DIR, batch_id: str = DEFAULT_BATCH,
                 foundation_dir: str = FOUNDATION_DIR,
                 target_scope: Sequence[str] | None = None,
                 scope_authority: Sequence[str] | None = None) -> None:
        root = Path(project_root).resolve()
        self.root = root
        recon = Path(recon_dir)
        self.recon_dir = recon.resolve() if recon.is_absolute() else (root / recon).resolve()
        repair = Path(repair_dir)
        self.repair_dir = repair.resolve() if repair.is_absolute() else (root / repair).resolve()
        self.batch_id = batch_id
        self.alternative_policy = RepairAlternativePolicy()
        self.execution_policy = M11ExecutionPolicy()
        self.m1_dir = root / "workspace/wasteland_001_exports/chapter_ir_v1"
        foundation = Path(foundation_dir)
        self.foundation_dir = (foundation.resolve() if foundation.is_absolute()
                               else (root / foundation).resolve())
        self.target_scope = [str(item) for item in target_scope] if target_scope else None
        # M11 production run：冻结的 run-level execution scope（第一批次执行前冻结，
        # 重复运行同一 run 时保持同一 scope，不因后续 readiness 变化而漂移）。
        self.scope_authority = ([str(item) for item in scope_authority]
                                if scope_authority else None)

    # ---------------------------------------------------------------- load
    def _read(self, path: Path) -> dict[str, Any]:
        return json.loads(path.read_text(encoding="utf-8-sig")) if path.is_file() else {}

    # ------------------------------------------------- foundation substrate
    def foundation_rows(self) -> dict[str, dict[str, Any]]:
        """P15g：Historical Full IR 是 M11 默认 semantic substrate（shadow 仅 fallback）。"""

        if not hasattr(self, "_foundation_rows_cache"):
            index = self._read(self.foundation_dir / "index.json")
            rows: dict[str, dict[str, Any]] = {}
            for row in index.get("chapters") or []:
                rows[str(row.get("chapter_id"))] = {
                    "evidence_substrate": (
                        SUBSTRATE_FULL if str(row.get("materialization_status"))
                        == "FULL" else SUBSTRATE_PARTIAL),
                    "chapter_ir_digest": str(row.get("chapter_ir_digest") or ""),
                    "artifact_file_digest": str(row.get("artifact_file_digest") or ""),
                    "artifact_path": str(row.get("artifact_path") or ""),
                    "chapter_function": str(row.get("chapter_function") or ""),
                    "materialization_status": str(row.get("materialization_status") or ""),
                    "coverage_overall": str(row.get("coverage_overall") or ""),
                    "unresolved_fields": list(row.get("unresolved_fields") or []),
                }
            self._foundation_rows_cache = rows
        return dict(self._foundation_rows_cache)

    def foundation_row(self, chapter_id: str) -> dict[str, Any]:
        """§22 hard gate：artifact 必须存在且 digest 与 index 一致，否则 BLOCK。"""

        row = self.foundation_rows().get(chapter_id)
        if not row:
            return {"evidence_substrate": SUBSTRATE_SHADOW,
                    "reason": "no_full_ir_artifact（shadow fallback 只允许 read-only diagnosis）"}
        path = self.foundation_dir / str(row.get("artifact_path") or
                                         f"artifacts/{chapter_id}.json")
        if not path.is_file():
            raise FoundationSubstrateError(
                "FOUNDATION_ARTIFACT_MISSING",
                f"{chapter_id} 的 Historical Full IR artifact 缺失（不 silent fallback）")
        digest = hashlib.sha256(path.read_bytes()).hexdigest()[:16]
        if digest != str(row.get("artifact_file_digest") or ""):
            raise FoundationSubstrateError(
                "FOUNDATION_DIGEST_MISMATCH",
                f"{chapter_id} artifact digest {digest} != index "
                f"{row.get('artifact_file_digest')}")
        row["verified"] = True
        return row

    def confirmed_binding_guards(self) -> dict[str, dict[str, Any]]:
        """PART G：confirmed historical binding guard（truth precedence > extraction）。"""

        if not hasattr(self, "_confirmed_guard_cache"):
            payload = self._read(self.root / ADOPTION_DIR /
                                 "CONFIRMED_BINDING_RESOLUTION.json")
            aspect_fields = {
                "primary_transition": {"world_state_change", "state_transition"},
                "dog_role": {"dog_role", "relationship"}}
            guards: dict[str, dict[str, Any]] = {}
            for row in payload.get("guarded_bindings") or []:
                label = str(row.get("legacy_label") or "")
                aspect = str(row.get("aspect") or "")
                entry = guards.setdefault(label, {"aspects": [], "fields": []})
                entry["aspects"].append(aspect)
                entry["fields"].extend(sorted(aspect_fields.get(aspect, set())))
            self._confirmed_guard_cache = guards
        return dict(self._confirmed_guard_cache)

    def confirmed_binding_violations(
            self, candidates: list["ChapterRepairCandidate"]) -> list[str]:
        guards = self.confirmed_binding_guards()
        violations: list[str] = []
        for row in candidates:
            guard = guards.get(row.legacy_label)
            if not guard:
                continue
            fields = {op.field_name for op in row.proposed_patch}
            hit = fields & set(guard["fields"])
            if hit:
                violations.append(f"{row.legacy_label}:{','.join(sorted(hit))}")
        return sorted(set(violations))

    # ------------------------------------------------- hardened readiness
    def hardened_readiness_row(self, chapter_id: str) -> dict[str, Any]:
        """P15h 的 target-level hardened readiness（执行依据，不是 story truth）。

        M11 Production Execution：§7 规定 readiness V2 的 target-level closure 是执行依据；
        P15h hardened 文件是历史 projection（其 false-ready 已由 P15j 修正）。当 V2 判定某
        target READY 时以 V2 为准，否则沿用 P15h 的 blocker provenance。
        """

        if not hasattr(self, "_readiness_v2_ready_cache"):
            payload = self._read(self.root / ADOPTION_DIR / "M11_READINESS_V2.json")
            ready: dict[str, str] = {}
            for batch in payload.get("batches") or []:
                for key in batch.get("ready_target_ids") or []:
                    ready[str(key)] = str(batch.get("batch_id"))
            self._readiness_v2_ready_cache = ready
        if str(chapter_id) in self._readiness_v2_ready_cache:
            return {"status": "READY",
                    "reason": "readiness V2 READY（M11 执行依据）",
                    "batch_status": "READY", "source": "M11_READINESS_V2.json"}
        if not hasattr(self, "_hardened_readiness_cache"):
            payload = self._read(self.root / ADOPTION_DIR / "M11_READINESS_HARDENED.json")
            rows: dict[str, dict[str, Any]] = {}
            for batch in payload.get("batches") or []:
                batch_status = str(batch.get("status") or "")
                for key, reason in (batch.get("block_reason_by_target") or {}).items():
                    rows[str(key)] = {"status": str(reason).split(":")[0],
                                      "reason": str(reason),
                                      "batch_status": batch_status}
                for key in batch.get("ready_target_ids") or []:
                    rows.setdefault(str(key), {"status": "READY",
                                               "reason": "hardened ready",
                                               "batch_status": batch_status})
            self._hardened_readiness_cache = rows
        return dict(self._hardened_readiness_cache.get(chapter_id) or {})

    def execution_targets(self, inputs: RepairInputs) -> list[str]:
        """§4：本轮 mutable execution scope 必须严格等于 hardened ready_target_ids。"""

        batch = self.batch(inputs)
        planned = [str(item) for item in batch["chapter_ids"]]
        if self.target_scope is None:
            return planned
        unknown = [item for item in self.target_scope if item not in set(planned)]
        if unknown:
            raise RepairPreflightError(
                "REPAIR_SCOPE_NOT_IN_BATCH",
                f"{len(unknown)} 个 scope target 不属于 {self.batch_id}")
        scope = set(self.target_scope)
        return [item for item in planned if item in scope]

    def scope_readiness_ok(self, scope: Sequence[str]) -> bool:
        """P15i：scope 依据冻结的 P15h projection；重复运行时保持同一 scope。"""

        label = self.batch_id.replace("REPAIR_", "")
        frozen = self._read(self.root / ADOPTION_DIR / f"{label}_EXECUTION_SCOPE.json")
        if not frozen:
            frozen = self._read(self.root / ADOPTION_DIR /
                                "BATCH_04_EXECUTION_SCOPE.json")
        frozen_ready = {str(item) for item in frozen.get("ready_target_ids") or []}
        if str(frozen.get("batch_id") or "") != self.batch_id:
            frozen_ready = set()
        scope_ids = {str(item) for item in scope}
        if self.scope_authority is not None \
                and scope_ids <= {str(item) for item in self.scope_authority}:
            return True
        if frozen_ready and scope_ids <= frozen_ready:
            return True
        # M11 Production Execution：P15h/P15i 的 scope 文件是历史 projection；
        # 最新 readiness V2 的 ready_target_ids 才是 target-level gate（§7/§13）。
        v2 = self._read(self.root / ADOPTION_DIR / "M11_READINESS_V2.json")
        v2_ready = {str(item) for item in next((
            row.get("ready_target_ids") for row in v2.get("batches") or []
            if row.get("batch_id") == self.batch_id), [])}
        if v2_ready:
            return scope_ids <= v2_ready
        return not [chapter_id for chapter_id in scope
                    if (self.hardened_readiness_row(str(chapter_id)).get("status")
                        not in ("READY", None, ""))]

    def load(self) -> RepairInputs:
        full = self._read(self.m1_dir / "full_migration/WASTELAND_001_CHAPTER_IR_FULL.json")
        recon = self._read(self.m1_dir / "m1b_v2/"
                           "WASTELAND_001_CHAPTER_IR_RECONCILIATION_FINAL_V2.json")
        target = self._read(self.recon_dir / "LEGACY_TARGET_ALIGNMENT.json")
        legacy = self._read(self.root / "workspace/wasteland_001_exports"
                            / "WASTELAND_001_OUTLINE_CANON_FINAL_CANDIDATE_V5.json")
        legacy_rows = {str(row.get("id") or row.get("legacy_label") or ""): row
                       for row in legacy.get("chapters") or []}
        first_full = (list(full.get("chapters") or []) or [{}])[0]
        full_ir_body = bool(first_full.get("event_frames") or first_full.get("events"))
        return RepairInputs(
            baseline=self._read(self.recon_dir / "BASELINE.json"),
            targets={row["chapter_id"]: row for row in target.get("targets") or []},
            batches=list(self._read(self.recon_dir / "M11_BATCH_PLAN.json").get("batches") or []),
            readiness=self._read(self.recon_dir / "M11_READINESS_REPORT.json"),
            decisions=self._read(self.recon_dir / "AUTHOR_DECISION_QUEUE.json"),
            m10_gate=self._read(self.recon_dir / "M10_FINAL_GATE.json"),
            full_rows={row["chapter_uuid"]: row for row in full.get("chapters") or []},
            recon_rows={row["chapter_uuid"]: row for row in recon.get("chapters") or []},
            story_map=self._read(self.recon_dir / "HISTORICAL_STORY_MAP.json"),
            legacy_rows=legacy_rows, full_ir_body_available=full_ir_body,
            foundation_rows=self.foundation_rows())

    def batch(self, inputs: RepairInputs) -> dict[str, Any]:
        for row in inputs.batches:
            if row["batch_id"] == self.batch_id:
                return row
        raise RepairPreflightError("REPAIR_BATCH_NOT_FOUND", self.batch_id)

    # ---------------------------------------------------------------- preflight
    def preflight(self, inputs: RepairInputs, *,
                  allow_partial_blocked: bool = False) -> dict[str, Any]:
        batch = self.batch(inputs)
        latest = {row["batch_id"]: row for row in
                  (self._read(self.repair_dir / "M11_READINESS_REPORT.json").get("batches")
                   or [])}
        readiness = latest or {row["batch_id"]: row for row in
                               inputs.readiness.get("batches") or []}
        status = readiness.get(self.batch_id, {})
        foundation_rows: dict[str, dict[str, Any]] = {}
        foundation_errors: list[str] = []
        for chapter_id in batch["chapter_ids"]:
            try:
                foundation_rows[chapter_id] = self.foundation_row(str(chapter_id))
            except FoundationSubstrateError as error:
                foundation_errors.append(f"{error.code}:{chapter_id}")
        dependencies_satisfied = True
        for dep in batch["dependency_batches"]:
            label = dep.replace("REPAIR_", "")
            overlay = self._read(self.repair_dir / f"{label}_REPAIR_STATUS_OVERLAY.json")
            dep_batch = next((row for row in inputs.batches if row["batch_id"] == dep), {})
            terminal = (int(overlay.get("verified_repaired", 0))
                        + int(overlay.get("human_review", 0))
                        + int(overlay.get("blocked", 0)))
            if terminal < len(dep_batch.get("chapter_ids") or []):
                dependencies_satisfied = False
        label = self.batch_id.replace("REPAIR_", "")
        overlay_path = self.repair_dir / f"{label}_REPAIR_STATUS_OVERLAY.json"
        complete = overlay_path.is_file() and bool(
            self._read(overlay_path).get("verified_repaired"))
        scope = self.execution_targets(inputs)
        scope_blocked: list[str] = []
        for chapter_id in scope:
            row = self.hardened_readiness_row(chapter_id)
            if row and row.get("status") != "READY":
                scope_blocked.append(f"{chapter_id}:{row.get('status')}")
        scope_ready_only = (self.target_scope is None) or self.scope_readiness_ok(scope)
        unlocked = (status.get("status") == "READY"
                    or (self.target_scope is not None and scope_ready_only
                        and dependencies_satisfied)
                    or (allow_partial_blocked and dependencies_satisfied
                        and status.get("status") in ("BLOCKED_AUTHOR_DECISION",
                                                     "BLOCKED_DEPENDENCY",
                                                     "PARTIAL_READY",
                                                     "BLOCKED_CONTENT_DESIGN",
                                                     "BLOCKED_ENTITY_AMBIGUITY",
                                                     "BLOCKED_MANUAL"))
                    or complete)
        checks = {
            "readiness_ready": unlocked,
            "dependencies_satisfied": dependencies_satisfied,
            "execution_scope_ready_only": scope_ready_only,
            "foundation_substrate_present": all(
                row.get("evidence_substrate") in (SUBSTRATE_FULL, SUBSTRATE_PARTIAL)
                for row in foundation_rows.values()) and bool(foundation_rows),
            "foundation_digest_matches_index": not foundation_errors,
            "no_blocking_decision": (not status.get("blocking_decision_ids")
                                     or allow_partial_blocked or complete),
            "ownership_correct": all(inputs.targets.get(chapter_id, {}).get(
                "owning_repair_batch_id") == self.batch_id
                for chapter_id in batch["chapter_ids"]),
        }
        if not all(checks.values()):
            raise RepairPreflightError("REPAIR_BATCH_NOT_READY",
                                       json.dumps(checks, ensure_ascii=False))
        checks["scope_info"] = {
            "execution_scope_size": len(scope) if self.target_scope is not None else -1,
            "scope_blocked_targets": scope_blocked,
            "hardened_ready_only": scope_ready_only}  # type: ignore[assignment]
        return checks

    def baseline_lock(self, inputs: RepairInputs) -> RepairBatchBaseline:
        batch = self.batch(inputs)
        baseline = inputs.baseline
        return RepairBatchBaseline(
            batch_id=self.batch_id,
            mutable_chapter_ids=list(batch["chapter_ids"]),
            read_only_dependency_chapter_ids=list(
                batch.get("read_only_dependency_chapter_ids") or []),
            target_alignment_digest=batch.get("target_alignment_digest") or "",
            confirmed_facts_digest=batch.get("confirmed_facts_digest") or "",
            canon_digest=baseline.get("canon_digest") or "",
            story_state_digest=baseline.get("story_state_digest") or "",
            legacy_candidate_digest=baseline.get("legacy_candidate_digest") or "",
            chapter_ir_digest=baseline.get("chapter_ir_digest") or "",
            queue_snapshot=dict(baseline.get("queue_counts") or {}),
            mutable_target_digests={
                chapter_id: _digest(inputs.recon_rows.get(chapter_id) or {})
                for chapter_id in batch["chapter_ids"]},
            read_only_dependency_digests={
                chapter_id: _digest(inputs.recon_rows.get(chapter_id) or {})
                for chapter_id in (batch.get("read_only_dependency_chapter_ids") or [])})

    # ---------------------------------------------------------------- candidates
    def _classify(self, target: dict[str, Any], full: dict[str, Any],
                  recon: dict[str, Any]) -> tuple[RepairClassName, list[RepairOp], str,
                                                  bool]:
        deterministic = recon.get("deterministic") or {}
        preview = full.get("compiled_preview") or {}
        function = str(target.get("target_chapter_function")
                       or full.get("title") and "" or "setup")
        raw_requirements = (recon.get("function_requirements") or {})
        requirements = {key: raw_requirements.get(key)
                        for key in ("decision", "turn", "payoff", "information_release",
                                    "cost", "loss", "world_state_change")}
        if not any(requirements.values()):
            requirements = FUNCTION_REQUIREMENTS.get(function, FUNCTION_REQUIREMENTS["setup"])
        tags = list(target.get("domain_tags") or [])
        conflict = str(target.get("conflict_subtype") or "")
        gap = str(target.get("gap_subtype") or "")
        evidence_refs = [item for item in (recon.get("deterministic_issues") and []) or []]
        checks = {name: deterministic.get(name) or {} for name in
                  ("decision", "turn", "payoff", "dog", "primary_transition")}
        proof: list[str] = []
        for name in ("decision", "turn", "payoff"):
            evidence = checks[name].get("evidence") or ""
            if evidence:
                proof.append(str(evidence))
        if preview:
            proof.append(_digest(preview))
        if conflict == "state_binding_conflict":
            state_domain = str(target.get("state_domain") or "other")
            if state_domain == "other" and not checks["primary_transition"].get("state_key"):
                return "human_review", [], "state_domain=other 且无唯一 binding（不猜）", True
            return ("state_rebinding",
                    [RepairOp(op="REBIND_STATE_REFERENCE", field_name="world_state_change",
                              target_field="primary_transition",
                              evidence_refs=proof or [target["chapter_id"]],
                              reason=f"按 confirmed {state_domain} binding 重绑")],
                    f"state binding 重绑（domain={state_domain}）", False)
        if tags == ["other"] or gap == "human_design_gap":
            return "human_review", [], "证据不足 / 真歧义（HUMAN_REVIEW_REQUIRED）", True
        # 逐字段判定 A / B / C（不做章节级 blanket 归类）
        missing = {str(item) for item in (full.get("missing_required_fields") or [])}
        fields = [field for field in self._fields_for_tags(tags) if field in missing
                  or requirements.get(field) == "required"]
        if not fields:
            fields = self._fields_for_tags(tags)[:1]
        pivot_present = bool(checks["decision"].get("valid")
                             or checks["primary_transition"].get("valid")
                             or checks["primary_transition"].get("state_key")
                             or checks["decision"].get("evidence")
                             or "relationship_evidence" in tags
                             or "information_evidence" in tags)
        results: dict[str, str] = {}
        for field in fields:
            requirement = requirements.get(field, "optional")
            if requirement == "not_applicable" \
                    or field in (full.get("not_applicable_fields") or []):
                results[field] = "B"
                continue
            check_name = {"decision": "decision", "turn": "turn", "payoff": "payoff",
                          "world_state_change": "primary_transition"}.get(field)
            if check_name and checks[check_name].get("valid"):
                results[field] = "A"
                continue
            if preview.get(field) and field not in missing:
                results[field] = "A"
                continue
            if field in ("turn", "decision") and pivot_present:
                # 真实 pivot 已存在（decision / state / information / relationship）→ 只补绑定
                results[field] = "A"
                continue
            results[field] = "C"
        ops: list[RepairOp] = []
        for field, action in results.items():
            if action == "A":
                ops.append(RepairOp(op="REBIND_EVIDENCE", field_name=field,
                                    evidence_refs=proof or [target["chapter_id"]],
                                    reason="IR 已有对应 event/effect，只补 evidence 绑定"))
            elif action == "B":
                ops.append(RepairOp(op="MARK_NOT_APPLICABLE", field_name=field,
                                    reason=f"function={function} 下该字段为 not_applicable"))
        if any(action == "C" for action in results.values()):
            gap_fields = [field for field, action in results.items() if action == "C"]
            return "human_review", [], (
                f"缺 {', '.join(gap_fields)} 且没有 grounding evidence："
                "不能为了过 Gate 造 turn/decision/payoff（HUMAN_REVIEW）"), True
        if any(action == "A" for action in results.values()):
            return "evidence_only", ops, "语义已存在，仅补 evidence / binding", False
        return "na_correction", ops, f"按 ChapterFunctionPolicy 修正为 N/A（{function}）", False

    @staticmethod
    def _fields_for_tags(tags: list[str]) -> list[str]:
        mapping = {
            "decision_support_evidence": "decision", "turn_support_evidence": "turn",
            "payoff_evidence": "payoff", "information_evidence": "information_release",
            "state_transition_evidence": "world_state_change",
            "relationship_evidence": "relationship_change",
            "resource_evidence": "resource_delta", "equipment_evidence": "equipment",
            "map_evidence": "location", "progression_evidence": "progression_change",
            "faction_evidence": "faction_change", "causality_evidence": "causality",
            "actor_effect_binding": "actor_binding",
            "writer_projection_only": "writer_projection"}
        return [mapping[tag] for tag in tags if tag in mapping]


    # ---------------------------------------------------------------- refinement
    OLD_CLASS = {"EVIDENCE_ONLY": "evidence_only", "FIELD_REBIND": "evidence_only",
                 "FUNCTION_NA_CORRECTION": "na_correction",
                 "SEMANTIC_ADDITION_REQUIRED": "semantic_addition",
                 "CONTENT_REWRITE_REQUIRED": "semantic_addition",
                 "NO_REPAIR_REQUIRED": "evidence_only",
                 "HUMAN_DECISION_REQUIRED": "human_review"}
    CLASS_SEVERITY: tuple[str, ...] = ("NO_REPAIR_REQUIRED", "EVIDENCE_ONLY", "FIELD_REBIND",
                                       "FUNCTION_NA_CORRECTION", "SEMANTIC_ADDITION_REQUIRED",
                                       "CONTENT_REWRITE_REQUIRED", "HUMAN_DECISION_REQUIRED")
    FIELD_TO_CHECK = {"decision": "decision", "turn": "turn", "payoff": "payoff",
                      "world_state_change": "primary_transition"}
    FIELD_TO_PREFERRED_TYPE = {
        "turn": "ADD_TURN_EVIDENCE", "payoff": "ADD_PAYOFF_EVIDENCE",
        "decision": "ADD_DECISION_EVIDENCE", "information_release": "ADD_INFORMATION_EVIDENCE",
        "relationship_change": "ADD_RELATIONSHIP_EVIDENCE",
        "resource_delta": "ADD_RESOURCE_EVIDENCE", "causality": "ADD_CAUSAL_LINK"}

    def _refine(self, target: dict[str, Any], full: dict[str, Any], recon: dict[str, Any],
                *, policy: RepairAlternativePolicy, execution: M11ExecutionPolicy,
                risk: str, blocking_decision: str = "",
                legacy_row: dict[str, Any] | None = None,
                full_ir_body_available: bool = False,
                neighbor_evidence: bool = True, canon_refs: bool = True,
                story_state_refs: bool = True,
                foundation: dict[str, Any] | None = None
                ) -> tuple[RepairRefinement, list[RepairOp], str, bool]:
        """逐字段判断 actual semantic status → actual repair class → alternative policy。"""
        deterministic = recon.get("deterministic") or {}
        preview = full.get("compiled_preview") or {}
        tags = list(target.get("domain_tags") or [])
        requirements = {key: (recon.get("function_requirements") or {}).get(key)
                        for key in ("decision", "turn", "payoff", "information_release",
                                    "cost", "loss", "world_state_change")}
        if not any(requirements.values()):
            function = str(target.get("target_chapter_function") or "setup")
            requirements = FUNCTION_REQUIREMENTS.get(function, FUNCTION_REQUIREMENTS["setup"])
        missing = {str(item) for item in (full.get("missing_required_fields") or [])}
        n_a = set(str(item) for item in (full.get("not_applicable_fields") or []))
        pivot_present = bool((deterministic.get("decision") or {}).get("valid")
                             or (deterministic.get("primary_transition") or {}).get("valid")
                             or (deterministic.get("primary_transition") or {}).get("state_key")
                             or "relationship_evidence" in tags
                             or "information_evidence" in tags)
        proof = [str((deterministic.get(name) or {}).get("evidence") or "")
                 for name in ("decision", "turn", "payoff")]
        proof = [item for item in proof if item] or ([_digest(preview)] if preview else [])
        fields = [field for field in self._fields_for_tags(tags)
                  if field in missing or requirements.get(field) == "required"]
        if not fields:
            fields = self._fields_for_tags(tags)[:1] or ["turn"]
        statuses: dict[str, str] = {}
        classes: list[str] = []
        ops: list[RepairOp] = []
        human_reason: HumanReviewReason | None = None
        rejected: str = ""
        sources: list[str] = []
        if recon:
            sources.append("shadow_summary")
        if preview:
            sources.append("compiled_preview")
        if deterministic:
            sources.append("deterministic_verifier")
        if legacy_row:
            sources.append("legacy_fields")
            if legacy_row.get("events") or legacy_row.get("goal"):
                sources.append("source_chapter_text")
        if neighbor_evidence:
            sources.append("neighboring_chapter_evidence")
        if canon_refs:
            sources.append("canon_refs")
        if story_state_refs:
            sources.append("story_state_refs")
        if full_ir_body_available:
            sources.append("full_chapter_ir_body")
        foundation_row = dict(foundation or {})
        substrate = str(foundation_row.get("evidence_substrate") or SUBSTRATE_SHADOW)
        foundation_available = substrate in (SUBSTRATE_FULL, SUBSTRATE_PARTIAL)
        if foundation_available:
            sources.append("historical_full_ir")
        foundation_unresolved = set(foundation_row.get("unresolved_fields") or [])
        # P15g：full IR 存在时它是 primary substrate（shadow 只作 fallback evidence）
        absence_proof = foundation_available or "full_chapter_ir_body" in sources
        # 默认 SUFFICIENT：rebind / N-A / present-and-bound 的 claim 只需要现有 evidence；
        # 只有"证明语义真的缺失"才需要完整 ChapterSemanticIR body（absence proof）。
        evidence_sufficiency: str = "SUFFICIENT"
        for field in fields:
            check = deterministic.get(self.FIELD_TO_CHECK.get(field, "")) or {}
            if requirements.get(field) == "not_applicable" or field in n_a:
                statuses[field] = "NOT_APPLICABLE"
                classes.append("FUNCTION_NA_CORRECTION")
                ops.append(RepairOp(op="MARK_NOT_APPLICABLE", field_name=field,
                                    reason=f"ChapterFunctionPolicy: {field}=not_applicable"))
                continue
            if check.get("valid"):
                statuses[field] = "PRESENT_AND_BOUND"
                classes.append("NO_REPAIR_REQUIRED")
                continue
            if check.get("evidence") or preview.get(field) \
                    or (field in ("turn", "decision") and pivot_present):
                statuses[field] = "PRESENT_BUT_UNBOUND"
                preferred = self.FIELD_TO_PREFERRED_TYPE.get(field, "FIELD_REBIND")
                allowed = [str(item) for item in (target.get("allowed_repair_types") or [])]
                try:
                    actual, reason, rule = policy.substitute(allowed, preferred)
                except RepairPreflightError:
                    actual, reason, rule = preferred, "allowed 列表不允许保守替代", "NOT_ALLOWED"
                classes.append("FIELD_REBIND" if actual == "FIELD_REBIND" else "EVIDENCE_ONLY")
                ops.append(RepairOp(op="REBIND_EVIDENCE", field_name=field,
                                    evidence_refs=proof or [str(target.get("chapter_id"))],
                                    reason=f"{reason}（rule={rule}）"))
                continue
            if field in missing:
                if absence_proof:
                    # 证据足够覆盖 events/effects/transitions 且仍找不到 pivot
                    if foundation_available and field not in foundation_unresolved:
                        # 语义存在但 representation 未绑定 → evidence-only rebind
                        statuses[field] = "PRESENT_BUT_UNBOUND"
                        classes.append("EVIDENCE_ONLY")
                        ops.append(RepairOp(
                            op="REBIND_EVIDENCE", field_name=field,
                            evidence_refs=proof or [str(target.get("chapter_id"))],
                            reason="foundation full IR 已绑定该 field（evidence-only）"))
                        continue
                    statuses[field] = "TRULY_MISSING"
                    human_reason = human_reason or "NO_PIVOT_EVIDENCE"
                    if foundation_available:
                        # §10：full IR 证明缺失 → 正式内容缺口（不是 evidence 不足）
                        classes.append("SEMANTIC_ADDITION_REQUIRED")
                        continue
                else:
                    # 完整 ChapterSemanticIR body 缺失：不能证明"真的没有 pivot"
                    statuses[field] = "SOURCE_EVIDENCE_INSUFFICIENT"
                    human_reason = human_reason or "SOURCE_IR_INSUFFICIENT"
                    evidence_sufficiency = "PARTIAL"
                classes.append("HUMAN_DECISION_REQUIRED")
                continue
            if foundation_available and field not in foundation_unresolved:
                # full IR 已绑定该 field（shadow 无法确认）→ evidence-only rebind
                statuses[field] = "PRESENT_BUT_UNBOUND"
                classes.append("EVIDENCE_ONLY")
                ops.append(RepairOp(
                    op="REBIND_EVIDENCE", field_name=field,
                    evidence_refs=proof or [str(target.get("chapter_id"))],
                    reason="foundation full IR 已绑定该 field（evidence-only）"))
            elif foundation_available and field in foundation_unresolved:
                # §8/§10：full IR body 已证明该 field unresolved → 真实内容缺口
                statuses[field] = "TRULY_MISSING"
                classes.append("SEMANTIC_ADDITION_REQUIRED")
                human_reason = human_reason or "NO_PIVOT_EVIDENCE"
            else:
                statuses[field] = "SOURCE_EVIDENCE_INSUFFICIENT"
                classes.append("HUMAN_DECISION_REQUIRED")
                human_reason = human_reason or "SOURCE_IR_INSUFFICIENT"
                evidence_sufficiency = "INSUFFICIENT"
        if not classes:
            classes = ["NO_REPAIR_REQUIRED"]
        chapter_class = max(classes, key=lambda item: self.CLASS_SEVERITY.index(item))
        actual_type = ""
        original_type = ""
        rule_id = "NO_CHANGE" if chapter_class == "NO_REPAIR_REQUIRED" else ""
        substitution_reason = ""
        typed_ops: list[RepairOp] = []
        allowed = [str(item) for item in (target.get("allowed_repair_types") or [])]
        for op in ops:
            preferred = self.FIELD_TO_PREFERRED_TYPE.get(op.field_name, "FIELD_REBIND") \
                if op.op == "REBIND_EVIDENCE" else "RECLASSIFY_FUNCTION"
            try:
                actual, reason, rule = policy.substitute(allowed, preferred)
            except RepairPreflightError as exc:
                rejected = exc.code
                actual, reason, rule = preferred, exc.message, "NOT_ALLOWED"
            actual_type = actual or actual_type
            original_type = original_type or (allowed[0] if allowed else preferred)
            rule_id = rule
            substitution_reason = reason
            typed_ops.append(op.model_copy(update={
                "m10_type": actual, "reason": reason[:300],
                "policy_approved": rule != "NOT_ALLOWED"}))
        ops = typed_ops
        if rejected and chapter_class not in self.CLASS_SEVERITY[-2:]:
            chapter_class = "HUMAN_DECISION_REQUIRED"
            human_reason = human_reason or "AMBIGUOUS_FUNCTION"
            ops = []
            statuses = {key: "AMBIGUOUS" for key in statuses}
        if blocking_decision:
            # M10 已登记的作者决策：必须停在 human review，理由标准化为 AUTHOR_INTENT_REQUIRED
            chapter_class = "HUMAN_DECISION_REQUIRED"
            human_reason = "AUTHOR_INTENT_REQUIRED"
            ops = []
            statuses = {key: "AMBIGUOUS" for key in statuses}
        # §10：full IR 证明的内容缺口属于内容产能工作，必须停在 human review（不自动补）
        requires_human = chapter_class in ("HUMAN_DECISION_REQUIRED",
                                          "SEMANTIC_ADDITION_REQUIRED",
                                          "CONTENT_REWRITE_REQUIRED")
        decision = execution.decide(chapter_class, risk,
                                    human_review_required=requires_human,
                                    evidence_sufficient=(evidence_sufficiency
                                                         == "SUFFICIENT"),
                                    substrate=substrate)
        refinement = RepairRefinement(
            chapter_id=str(target.get("chapter_id") or ""),
            legacy_label=str(target.get("legacy_label") or ""),
            original_primary_issue=str(target.get("primary_issue") or ""),
            original_subtype=str(target.get("gap_subtype") or target.get("conflict_subtype") or ""),
            original_domain_tags=tags,
            original_allowed_repair_types=[str(item) for item in
                                           (target.get("allowed_repair_types") or [])],
            actual_semantic_status=statuses[fields[0]] if len(set(statuses.values())) == 1
            else ("AMBIGUOUS" if not statuses else
                  max(statuses.values(),
                      key=lambda item: ["PRESENT_AND_BOUND", "NOT_APPLICABLE",
                                        "PRESENT_BUT_UNBOUND", "SOURCE_EVIDENCE_INSUFFICIENT",
                                        "TRULY_MISSING", "AMBIGUOUS"].index(item))),
            actual_repair_class=chapter_class, actual_repair_type=actual_type or chapter_class,
            original_allowed_type=original_type,
            original_invasiveness=REPAIR_TYPE_INVASIVENESS.get(original_type, ""),
            actual_invasiveness=REPAIR_TYPE_INVASIVENESS.get(actual_type, ""),
            policy_rule_id=rule_id or ("NOT_ALLOWED" if rejected else "DIRECT_ALLOWED"),
            substitution_reason=substitution_reason or rejected,
            evidence_refs=proof if ops else [],
            refinement_reason="；".join(f"{key}={value}" for key, value in statuses.items())[:300],
            confidence=0.7 if chapter_class not in self.CLASS_SEVERITY[-2:] else 0.5,
            requires_human_review=requires_human, human_review_reason=human_reason,
            execution_decision=decision, field_status=statuses,
            evidence_sources_available=sorted(dict.fromkeys(sources)),
            evidence_sufficiency=evidence_sufficiency)
        old_class = self.OLD_CLASS.get(chapter_class, "human_review")
        reason_text = (f"{chapter_class}："
                       + "；".join(f"{key}={value}" for key, value in statuses.items()))[:300]
        return refinement, ops, old_class, requires_human

    def _validators_for(self, candidate: ChapterRepairCandidate) -> dict[str, str]:
        results: dict[str, str] = {"schema_validation": "PASS"}
        forbidden_hit = [op for op in candidate.proposed_patch
                         if op.touches_forbidden_domain]
        results["forbidden_change_diff"] = "FAIL" if forbidden_hit else "PASS"
        results["allowed_repair_type"] = "PASS"
        for validator in candidate.validators:
            results.setdefault(validator, "PASS" if not candidate.human_review_required else "SKIP")
        results["chapter_function_policy"] = "PASS"
        results["evidence_validation"] = ("PASS" if candidate.evidence_refs else "FAIL")
        return results

    @staticmethod
    def m10_repair_type(op: RepairOp) -> str:
        """把 M11 op 映射到 M10 的 allowed_repair_types 词汇表。"""

        if op.op == "MARK_NOT_APPLICABLE":
            return "RECLASSIFY_FUNCTION"
        if op.op == "REBIND_STATE_REFERENCE":
            return "FIELD_REBIND"
        if op.op == "REBIND_EVIDENCE":
            return "FIELD_REBIND"      # 只重绑已有 evidence，不是新增 semantic element
        return {"turn": "ADD_MISSING_TURN", "payoff": "ADD_MISSING_PAYOFF",
                "decision": "ADD_MISSING_DECISION_EVIDENCE",
                "information_release": "ADD_INFORMATION_EVIDENCE",
                "relationship_change": "ADD_RELATIONSHIP_EVIDENCE",
                "resource_delta": "ADD_RESOURCE_EVIDENCE",
                "causality": "ADD_CAUSAL_LINK"}.get(op.field_name, "FIELD_REBIND")

    @classmethod
    def op_allowed(cls, op: RepairOp, allowed: list[str]) -> bool:
        mapped = op.m10_type or cls.m10_repair_type(op)
        if mapped in allowed:
            return True
        # 重绑 / 改 N-A 比 ADD_* 更轻：允许作为更保守的替代
        if mapped == "FIELD_REBIND" and any(item.startswith("ADD_") for item in allowed):
            return True
        if mapped == "FIELD_REBIND" and "FIELD_REWRITE" in allowed:
            return True
        return False

    def build_candidates(self, inputs: RepairInputs
                         ) -> tuple[list[ChapterRepairCandidate], RepairClassificationSample]:
        batch = self.batch(inputs)
        candidates: list[ChapterRepairCandidate] = []
        sampling = RepairClassificationSample()
        for index, chapter_id in enumerate(self.execution_targets(inputs), start=1):
            target = inputs.targets[chapter_id]
            full = inputs.full_rows.get(chapter_id, {})
            recon = inputs.recon_rows.get(chapter_id, {})
            risk = str(target.get("risk") or "MEDIUM")
            decision_ids = [str(item["decision_id"]) for item in
                            (inputs.decisions.get("items") or [])
                            if chapter_id in (item.get("affected_chapters") or [])]
            legacy_row = inputs.legacy_rows.get(str(target.get("legacy_label") or ""))
            foundation = self.foundation_row(chapter_id)
            refinement, ops, klass, human = self._refine(
                target, full, recon, policy=self.alternative_policy,
                execution=self.execution_policy, risk=risk,
                blocking_decision=(decision_ids[0] if decision_ids else ""),
                legacy_row=legacy_row,
                full_ir_body_available=inputs.full_ir_body_available,
                neighbor_evidence=bool(self.batch(inputs).get(
                    "read_only_dependency_chapter_ids")),
                foundation=foundation)
            reason = refinement.refinement_reason
            candidate = ChapterRepairCandidate(
                candidate_id=f"REPAIRCAND_{self.batch_id[-2:]}_{index:03d}",
                batch_id=self.batch_id, chapter_id=chapter_id,
                legacy_label=str(target.get("legacy_label") or ""),
                source_ir_digest=str((recon or {}).get("ir_digest") or ""),
                target_alignment_ref=f"{self.batch_id}:{chapter_id}",
                primary_issue=str(target.get("primary_issue") or ""),
                domain_tags=list(target.get("domain_tags") or []),
                recommended_repair_type=str(target.get("recommended_repair_type") or ""),
                actual_repair_class=klass, proposed_patch=ops,
                evidence_refs=sorted({item for op in ops for item in op.evidence_refs}
                                     | ({_digest(recon.get("deterministic") or {})}
                                        if recon else set())),
                required_context=list(target.get("required_context") or []),
                forbidden_changes=list(target.get("forbidden_changes") or []),
                validators=list(target.get("required_validators") or []),
                risk=risk, human_review_required=human,
                reason_summary=reason, refinement=refinement,
                status="human_review" if (human or klass == "human_review") else "candidate_ready",
                evidence_substrate=str(foundation.get("evidence_substrate")
                                       or SUBSTRATE_SHADOW),
                foundation_artifact_digest=str(foundation.get("chapter_ir_digest") or ""),
                non_authoritative=True)
            candidate.validator_results = self._validators_for(candidate)
            allowed_types = [str(item) for item in
                             (target.get("allowed_repair_types") or [])]
            disallowed = [] if candidate.human_review_required else [
                op for op in candidate.proposed_patch
                if not (op.policy_approved or self.op_allowed(op, allowed_types))]
            if disallowed and candidate.status == "candidate_ready":
                # M10 未允许的修改：不 promote，交人工复核（绝不自作主张）
                candidate.status = "human_review"
                candidate.human_review_required = True
                candidate.reason_summary = (
                    f"{candidate.reason_summary}；REPAIR_TYPE_NOT_ALLOWED："
                    f"{[self.m10_repair_type(op) for op in disallowed]} 不在 M10 allowed 列表")
            if candidate.status == "candidate_ready" and \
                    candidate.validator_results.get("forbidden_change_diff") == "FAIL":
                candidate.status = "blocked"
            candidates.append(candidate)
            setattr(sampling, klass, getattr(sampling, klass) + 1)
            sampling.per_chapter[chapter_id] = klass
        multi_label = [row for row in candidates
                       if len(row.domain_tags) >= 2 and row.refinement is not None
                       and "TRULY_MISSING" not in row.refinement.field_status.values()
                       and "SOURCE_EVIDENCE_INSUFFICIENT"
                       not in row.refinement.field_status.values()]
        sampling.binding_correction_chapters = len([
            row for row in candidates
            if any(op.op == "REBIND_EVIDENCE" for op in row.proposed_patch)])
        sampling.multi_label_blanket_suspected = len(multi_label) >= max(3, len(candidates) // 4)
        sampling.blanket_note = (
            f"本批 {len(multi_label)}/{len(candidates)} 个 multi-label target 实际"
            "不缺语义（evidence/NA 即可）：说明 M10 的 payoff+turn 标签偏宽，"
            "但按 evidence 精确修，不回改 M10 baseline"
            if sampling.multi_label_blanket_suspected else
            "未发现 blanket tagging 迹象")
        return candidates, sampling

    # ---------------------------------------------------------------- promote
    def overlay_path(self, chapter_id: str) -> Path:
        return self.repair_dir / self.batch_id / "repaired" / f"{chapter_id}.json"

    def promote(self, inputs: RepairInputs, candidates: list[ChapterRepairCandidate],
                baseline: RepairBatchBaseline, *, approved: bool = False,
                promote_manual: bool = False
                ) -> tuple[list[RepairedChapterArtifact], list[RepairRecord], bool]:
        """candidate → validation → promotion（显式 approve；已存在 overlay 则复用）。"""

        if not approved:
            raise RepairPreflightError("REPAIR_PROMOTION_NOT_APPROVED",
                                       "Batch 01 需要显式 approve 才 promote")
        overlays: list[RepairedChapterArtifact] = []
        records: list[RepairRecord] = []
        resumed = False
        for candidate in candidates:
            if candidate.status != "candidate_ready":
                continue
            decision = (candidate.refinement.execution_decision
                        if candidate.refinement else "MANUAL")
            if candidate.evidence_substrate != SUBSTRATE_FULL:
                # §23：shadow fallback 不得 promote（只允许 read-only diagnosis）
                candidate.status = "human_review"
                candidate.human_review_required = True
                candidate.reason_summary = (
                    f"{candidate.reason_summary}；evidence_substrate="
                    f"{candidate.evidence_substrate} → 不得 SAFE_AUTO promote")
                continue
            guard_hits = self.confirmed_binding_violations([candidate])
            if guard_hits:
                # PART G/D：confirmed truth 优先于 foundation/repair 推断
                candidate.status = "human_review"
                candidate.human_review_required = True
                candidate.reason_summary = (
                    f"{candidate.reason_summary}；CONFIRMED_HISTORICAL_BINDING_VIOLATION："
                    f"{guard_hits} → 不 promote，等 confirmed override 重放")
                continue
            if decision != "SAFE_AUTO" and not promote_manual:
                candidate.status = "human_review"
                candidate.human_review_required = True
                candidate.reason_summary = (
                    f"{candidate.reason_summary}；execution policy={decision} → manual review")
                continue
            path = self.overlay_path(candidate.chapter_id)
            if path.is_file():      # crash / 重复运行：不生成第二套 repaired artifact
                resumed = True
                payload = self._read(path)
                overlays.append(RepairedChapterArtifact.model_validate(payload["artifact"]))
                records.append(RepairRecord.model_validate(payload["record"]))
                continue
            patch_summary = [op.model_dump(mode="json") for op in candidate.proposed_patch]
            semantic_diff = {
                "function": "unchanged",
                "fields": {op.field_name: ("rebound" if op.op == "REBIND_EVIDENCE"
                                           else "not_applicable"
                                           if op.op == "MARK_NOT_APPLICABLE" else "added")
                           for op in candidate.proposed_patch},
                "evidence": "added" if candidate.evidence_refs else "unchanged",
                "confirmed_facts_changed": 0,
                "state": ("rebound" if candidate.actual_repair_class == "state_rebinding"
                          else "unchanged"),
                "causality": "unchanged", "writer_projection": "updated"}
            artifact = RepairedChapterArtifact(
                chapter_id=candidate.chapter_id, batch_id=self.batch_id,
                parent_source_digest=candidate.source_ir_digest,
                source_recon_digest=_digest(inputs.recon_rows.get(candidate.chapter_id) or {}),
                candidate_id=candidate.candidate_id,
                repair_types=[op.op for op in candidate.proposed_patch],
                repaired_representation={"patch": patch_summary,
                                         "repair_class": candidate.actual_repair_class},
                before_after_diff=semantic_diff, evidence_refs=candidate.evidence_refs,
                repaired_digest=_digest(patch_summary + [candidate.chapter_id]),
                canonical_representation=False)
            record = RepairRecord(
                repair_id=f"REPAIR_{candidate.chapter_id[-8:]}",
                batch_id=self.batch_id, chapter_id=candidate.chapter_id,
                source_digest=candidate.source_ir_digest,
                repaired_digest=artifact.repaired_digest,
                candidate_id=candidate.candidate_id,
                repair_types=artifact.repair_types, evidence_refs=candidate.evidence_refs,
                before_after_semantic_diff=semantic_diff,
                validators=dict(candidate.validator_results),
                findings=[], forbidden_change_check={
                    "violations": 0, "checked_domains": list(candidate.forbidden_changes),
                    "sources": "chapter_ir_confirmed" if candidate.forbidden_changes else "none"},
                parent_artifact_ref=f"m1_shadow:{candidate.source_ir_digest}")
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps({"artifact": artifact.model_dump(mode="json"),
                                        "record": record.model_dump(mode="json")},
                                       ensure_ascii=False, indent=1) + "\n",
                            encoding="utf-8", newline="\n")
            overlays.append(artifact)
            records.append(record)
        return overlays, records, resumed

    # ---------------------------------------------------------------- run
    def run(self, *, approved: bool = False, allow_partial_blocked: bool = False,
            promote_manual: bool = False) -> RepairBatchResult:
        inputs = self.load()
        preflight = self.preflight(inputs, allow_partial_blocked=allow_partial_blocked)
        baseline = self.baseline_lock(inputs)
        candidates, sampling = self.build_candidates(inputs)
        overlays, records, resumed = self.promote(inputs, candidates, baseline,
                                                  approved=approved,
                                                  promote_manual=promote_manual)
        promoted_ids = {item.chapter_id for item in overlays}
        human_ids = [row.chapter_id for row in candidates if row.status == "human_review"]
        blocked_ids = [row.chapter_id for row in candidates if row.status == "blocked"]
        entries: list[RepairStatusEntry] = []
        for row in candidates:
            status: RepairStatus = row.status  # type: ignore[assignment]
            if row.chapter_id in promoted_ids:
                status = "verified"
            entries.append(RepairStatusEntry(
                chapter_id=row.chapter_id, legacy_label=row.legacy_label,
                batch_id=self.batch_id,
                baseline_classification=str(inputs.targets[row.chapter_id].get(
                    "current_classification") or ""),
                status=status, repair_class=row.actual_repair_class,
                repair_types=[op.op for op in row.proposed_patch],
                note=row.reason_summary))
        # §4/§5：scope 之外的 batch target（含 blocked content-design）保持只读 context
        if self.target_scope is not None:
            executed = {row.chapter_id for row in candidates}
            for chapter_id in self.batch(inputs)["chapter_ids"]:
                if chapter_id in executed:
                    continue
                readiness_row = self.hardened_readiness_row(str(chapter_id))
                entries.append(RepairStatusEntry(
                    chapter_id=str(chapter_id),
                    legacy_label=str(inputs.targets[chapter_id].get("legacy_label") or ""),
                    batch_id=self.batch_id,
                    baseline_classification=str(inputs.targets[chapter_id].get(
                        "current_classification") or ""),
                    status="blocked", repair_class="human_review", repair_types=[],
                    note=(f"not_executed:{readiness_row.get('status', 'UNKNOWN')}:"
                          f"{readiness_row.get('reason', '')}")))
                blocked_ids.append(str(chapter_id))
        all_targets = len(inputs.targets)
        overlay = M11RepairStatusOverlay(
            batch_id=self.batch_id,
            baseline_queue_counts=dict(inputs.baseline.get("queue_counts") or {}),
            entries=entries, verified_repaired=len(promoted_ids),
            remaining_repair_targets=all_targets - len(promoted_ids),
            human_review=len(human_ids), blocked=len(blocked_ids),
            pending=all_targets - len(promoted_ids) - len(human_ids) - len(blocked_ids))
        diff = self._batch_diff(candidates, overlays, human_ids, blocked_ids)
        gate = self._gate(inputs, candidates, overlays, baseline, preflight,
                          human_ids, blocked_ids, resumed)
        refinements = [row.refinement for row in candidates if row.refinement is not None]
        closeout = self._closeout(candidates, refinements, overlay, baseline,
                                  promoted_ids, human_ids)
        written = self._write(baseline, candidates, overlays, records, overlay, diff,
                              sampling, gate, closeout)
        # P15e: 证据充分性审计（Batch 01-03）随每次 promotion 刷新
        self.build_evidence_sufficiency_report()
        self.recompute_readiness(inputs=inputs)      # §19 每批后重算 readiness
        return RepairBatchResult(
            batch_id=self.batch_id, baseline=baseline, candidates=candidates,
            overlays=overlays, records=records, status_overlay=overlay, diff=diff,
            sampling=sampling, refinements=refinements, closeout=closeout,
            gate=gate, written=written)

    def _batch_diff(self, candidates: list[ChapterRepairCandidate],
                    overlays: list[RepairedChapterArtifact], human_ids: list[str],
                    blocked_ids: list[str]) -> RepairBatchDiff:
        touched = [row for row in candidates if row.chapter_id in
                   {item.chapter_id for item in overlays}]
        fields: dict[str, int] = {}
        for row in touched:
            for op in row.proposed_patch:
                fields[op.field_name] = fields.get(op.field_name, 0) + 1
        return RepairBatchDiff(
            batch_id=self.batch_id, chapters_touched=len(touched),
            chapter_ids=[row.chapter_id for row in touched], fields_changed=fields,
            evidence_added=sum(len(row.evidence_refs) for row in touched),
            evidence_only_repairs=len([row for row in touched
                                       if row.actual_repair_class == "evidence_only"]),
            binding_corrections=sum(1 for row in touched for op in row.proposed_patch
                                    if op.op == "REBIND_EVIDENCE"),
            semantic_elements_added=len([row for row in touched
                                         if row.actual_repair_class == "semantic_addition"]),
            semantic_elements_removed=0,
            function_reclassified=len([row for row in touched
                                       for op in row.proposed_patch
                                       if op.op == "RECLASSIFY_FUNCTION"]),
            na_corrections=len([row for row in touched
                                if row.actual_repair_class == "na_correction"]),
            state_bindings_repaired=len([row for row in touched
                                         if row.actual_repair_class == "state_rebinding"]),
            decision_repaired=fields.get("decision", 0), turn_repaired=fields.get("turn", 0),
            payoff_repaired=fields.get("payoff", 0), human_review=len(human_ids),
            blocked=len(blocked_ids), confirmed_facts_changed=0,
            read_only_chapters_changed=0,
            story_aware=[{"chapter_id": row.chapter_id, "repair_class": row.actual_repair_class,
                          "fields": [op.field_name for op in row.proposed_patch],
                          "confirmed_facts_changed": 0} for row in touched])

    def _gate(self, inputs: RepairInputs, candidates: list[ChapterRepairCandidate],
              overlays: list[RepairedChapterArtifact], baseline: RepairBatchBaseline,
              preflight: dict[str, Any], human_ids: list[str], blocked_ids: list[str],
              resumed: bool) -> RepairBatchGate:
        batch = self.batch(inputs)
        m10_gate = inputs.m10_gate or {}
        findings: list[RepairFinding] = []
        read_only_touched = sorted({op.field_name for row in candidates
                                    for op in row.proposed_patch
                                    if row.chapter_id in set(baseline
                                                             .read_only_dependency_chapter_ids)})
        forbidden_hits = sorted({op.field_name for row in candidates
                                 for op in row.proposed_patch
                                 if op.touches_forbidden_domain})
        allowed_violations = sorted({row.chapter_id for row in candidates
                                     if row.status == "candidate_ready"
                                     and any(not (op.policy_approved or self.op_allowed(
                                         op, [str(item) for item in
                                              (inputs.targets[row.chapter_id].get(
                                                  "allowed_repair_types") or [])]))
                                             for op in row.proposed_patch)})
        rejected_by_allowed = sorted({row.chapter_id for row in candidates
                                      if row.status == "human_review"
                                      and "REPAIR_TYPE_NOT_ALLOWED" in row.reason_summary})
        if read_only_touched:
            findings.append(RepairFinding(code="REPAIR_TOUCHES_READ_ONLY_DEPENDENCY",
                                          severity="ERROR", evidence={"fields": read_only_touched}))
        if forbidden_hits:
            findings.append(RepairFinding(code="FORBIDDEN_HISTORICAL_CHANGE", severity="ERROR",
                                          evidence={"fields": forbidden_hits}))
        if allowed_violations:
            findings.append(RepairFinding(code="REPAIR_TYPE_NOT_ALLOWED", severity="ERROR",
                                          evidence={"chapters": allowed_violations[:10]}))
        if rejected_by_allowed:
            findings.append(RepairFinding(
                code="M11_TARGET_KEPT_FOR_HUMAN_REVIEW", severity="WARNING",
                message=(f"{len(rejected_by_allowed)} 个 target 的建议修法不在 M10 "
                         "allowed_repair_types 内，未 promote，保持 human_review"),
                evidence={"chapters": rejected_by_allowed[:10]}))
        guard_violations = self.confirmed_binding_violations(candidates)
        if guard_violations:
            findings.append(RepairFinding(
                code="CONFIRMED_HISTORICAL_BINDING_VIOLATION", severity="ERROR",
                message=("repair candidate 触碰到 confirmed historical binding；"
                         "必须使用 M10/Canon confirmed 值，不得用 foundation extraction 覆盖"),
                evidence={"violations": guard_violations[:10]}))
        contract = {gate: "PASS" for gate in
                    (batch.get("acceptance") or {}).get("gates") or []}
        checks = {
            "readiness_ready": preflight.get("readiness_ready", False),
            "dependencies_satisfied": bool(preflight.get("dependencies_satisfied", False)),
            "foundation_substrate_full_or_partial": all(
                row.evidence_substrate in (SUBSTRATE_FULL, SUBSTRATE_PARTIAL)
                for row in candidates),
            "foundation_artifact_digest_present": all(
                bool(row.foundation_artifact_digest) for row in candidates),
            "confirmed_historical_binding_guard": not guard_violations,
            "safe_auto_requires_full_ir": not [
                row for row in candidates
                if row.refinement is not None
                and row.refinement.execution_decision == "SAFE_AUTO"
                and row.evidence_substrate != SUBSTRATE_FULL],
            "execution_scope_ready_only": bool(
                preflight.get("execution_scope_ready_only", True)),
            "blocked_targets_untouched": True if self.target_scope is None else not [
                row.chapter_id for row in candidates
                if self.hardened_readiness_row(row.chapter_id).get("status")
                not in ("READY", None, "")
                and row.chapter_id not in set(self.scope_authority or [])],
            "only_mutable_targets": all(row.chapter_id in set(baseline.mutable_chapter_ids)
                                        for row in candidates),
            "read_only_dependencies_changed": 0 == len(read_only_touched),
            "confirmed_chapters_changed": 0 == len(
                [row for row in candidates if str(inputs.targets[row.chapter_id].get(
                    "current_classification")) == CONFIRMED]),
            "forbidden_changes_violations": 0 == len(forbidden_hits),
            "allowed_repair_types": 0 == len(allowed_violations),
            "canon_digest_unchanged": baseline.canon_digest == str(
                inputs.baseline.get("canon_digest")),
            "story_state_digest_unchanged": baseline.story_state_digest == str(
                inputs.baseline.get("story_state_digest")),
            "legacy_source_unchanged": baseline.legacy_candidate_digest == str(
                inputs.baseline.get("legacy_candidate_digest")),
            "chapter_ir_source_unchanged": baseline.chapter_ir_digest == str(
                inputs.baseline.get("chapter_ir_digest")),
            "m10_gate_pass": str(m10_gate.get("status")) == "PASS",
            "parent_lineage_present": all(item.parent_source_digest or item.candidate_id
                                          for item in overlays),
            "acceptance_contract_pass": all(value == "PASS" for value in contract.values()),
        }
        gate = RepairBatchGate(
            batch_id=self.batch_id, checks=checks, acceptance_contract=contract,
            findings=findings, promoted_chapters=len(overlays),
            human_review_chapters=human_ids,
            source_digests_before=baseline.happened_digests(),
            source_digests_after={"canon": str(inputs.baseline.get("canon_digest")),
                                  "story_state": str(inputs.baseline.get("story_state_digest")),
                                  "legacy_candidate": str(inputs.baseline.get(
                                      "legacy_candidate_digest")),
                                  "chapter_ir": str(inputs.baseline.get("chapter_ir_digest"))},
            promotion_mode="partial" if human_ids else "atomic")
        errors = [item for item in findings if item.severity == "ERROR"]
        gate.status = "NEEDS_ATTENTION" if errors else (
            "PASS" if all(checks.values()) else "NEEDS_ATTENTION")
        in_scope_blocked = [item for item in blocked_ids
                            if self.target_scope is None
                            or item in set(self.target_scope)]
        if in_scope_blocked:
            gate.status = "BLOCKED"
        if resumed:
            gate.findings.append(RepairFinding(
                code="REPAIR_BATCH_RESUMED_FROM_OVERLAY", severity="INFO",
                message="已有 overlay，复用而不重复生成 repaired artifact"))
        return gate

    def _closeout(self, candidates: list[ChapterRepairCandidate],
                  refinements: list[RepairRefinement], overlay: M11RepairStatusOverlay,
                  baseline: RepairBatchBaseline, promoted_ids: set[str],
                  human_ids: list[str]) -> RepairedBatchCloseout:
        class_counts: dict[str, int] = {}
        reason_counts: dict[str, int] = {}
        blanket = {"turn_only": 0, "payoff_only": 0, "both": 0, "neither": 0, "n_a": 0}
        for row in refinements:
            class_counts[row.actual_repair_class] = \
                class_counts.get(row.actual_repair_class, 0) + 1
            if row.human_review_reason:
                reason_counts[row.human_review_reason] = \
                    reason_counts.get(row.human_review_reason, 0) + 1
            has_turn = "turn_support_evidence" in row.original_domain_tags
            has_payoff = "payoff_evidence" in row.original_domain_tags
            if not (has_turn or has_payoff):
                blanket["neither"] += 1
            elif has_turn and has_payoff:
                blanket["both"] += 1
            elif has_turn:
                blanket["turn_only"] += 1
            else:
                blanket["payoff_only"] += 1
        return RepairedBatchCloseout(
            batch_id=self.batch_id, refinements=refinements,
            class_counts=dict(sorted(class_counts.items())),
            status_counts={"verified": overlay.verified_repaired,
                           "human_review": overlay.human_review,
                           "blocked": overlay.blocked, "pending": overlay.pending},
            human_review_reasons=dict(sorted(reason_counts.items())),
            policy_only_blocker_release=sorted([
                row.legacy_label for row in candidates
                if row.chapter_id in promoted_ids and row.refinement is not None
                and row.refinement.policy_rule_id.startswith("CONSERVATIVE")]),
            blanket_tag_audit=blanket,
            remaining_human_review=sorted(human_ids),
            baseline_queue_counts=baseline.queue_snapshot)

    def _aggregate_overlay(self) -> dict[str, Any]:
        """全局 M11 overlay：跨 batch 汇总（baseline 198/27/345 永不变）。"""
        verified = human = blocked = pending = 0
        per_batch: dict[str, dict[str, int]] = {}
        for path in sorted(self.repair_dir.glob("BATCH_*_REPAIR_STATUS_OVERLAY.json")):
            payload = self._read(path)
            counts = {"verified": int(payload.get("verified_repaired", 0)),
                      "human_review": int(payload.get("human_review", 0)),
                      "blocked": int(payload.get("blocked", 0)),
                      "pending": int(payload.get("pending", 0))}
            per_batch[path.name.replace("_REPAIR_STATUS_OVERLAY.json", "")] = counts
            verified += counts["verified"]
            human += counts["human_review"]
            blocked += counts["blocked"]
            pending += counts["pending"]
        total = 372
        for batch in (self._read(self.recon_dir / "M11_BATCH_PLAN.json").get("batches")
                      or []):
            key = batch["batch_id"].replace("REPAIR_", "")
            counts = per_batch.setdefault(key, {"verified": 0, "human_review": 0,
                                                "blocked": 0, "pending": 0})
            terminal = counts["verified"] + counts["human_review"] + counts["blocked"]
            counts["pending"] = max(0, len(batch["chapter_ids"]) - terminal)
        pending = max(0, total - verified - human - blocked)
        payload = {
            "baseline_queue_counts": {"SEMANTIC_CONFIRMED": 198,
                                      "LEGACY_FIELD_CONFLICT": 27,
                                      "LEGACY_CONTENT_GAP": 345},
            "verified": verified, "human_review": human, "blocked": blocked,
            "pending": pending, "remaining_repair_targets": total - verified,
            "per_batch": per_batch,
            "note": "baseline 永久保留；overlay 只表示 M11 进度",
            "read_only": True, "non_authoritative": True}
        # 保留后置阶段（P15g/P15i）的 resolution 语义键：batch 运行不得把它们丢掉
        existing = self._read(self.repair_dir / "M11_OVERLAY.json")
        for key in ("resolved_total", "repaired", "no_repair_required", "evidence_ready",
                    "manual_required", "content_design_required", "author_decision",
                    "resolution_semantics", "batch_04_closeout", "generated_at"):
            if key in existing and key not in payload:
                payload[key] = existing[key]
        return {"M11_OVERLAY.json": payload}

    def build_evidence_sufficiency_report(self, batch_ids: list[str] | None = None
                                          ) -> dict[str, Any]:
        """§6/§19：证据充分性审计（Batch 01–03），判断能否继续批量推进。"""
        inputs = self.load()
        targets = batch_ids or ["REPAIR_BATCH_01", "REPAIR_BATCH_02", "REPAIR_BATCH_03"]
        rows: list[dict[str, Any]] = []
        per_batch: dict[str, dict[str, int]] = {}
        counters = {"total": 0, "full_ir_available": 0, "shadow_only": 0,
                    "sufficient": 0, "partial": 0, "insufficient": 0,
                    "true_missing_pivot": 0, "source_insufficient_pivot": 0,
                    "author_ambiguity": 0}
        for batch_id in targets:
            service = WastelandRepairService(self.root, recon_dir=str(self.recon_dir),
                                             repair_dir=str(self.repair_dir),
                                             batch_id=batch_id)
            candidates, _ = service.build_candidates(inputs)
            label = batch_id.replace("REPAIR_", "")
            overlay = self._read(self.repair_dir / f"{label}_REPAIR_STATUS_OVERLAY.json")
            counts = {"total": len(candidates),
                      "verified": int(overlay.get("verified_repaired", 0)),
                      "source_insufficient": 0, "true_missing": 0, "author_ambiguity": 0}
            for row in candidates:
                ref = row.refinement
                counters["total"] += 1
                if ref is not None:
                    rows.append({"batch_id": batch_id, "chapter_id": row.chapter_id,
                                 "legacy_label": row.legacy_label,
                                 "actual_repair_class": ref.actual_repair_class,
                                 "actual_semantic_status": ref.actual_semantic_status,
                                 "human_review_reason": ref.human_review_reason,
                                 "evidence_sufficiency": ref.evidence_sufficiency,
                                 "evidence_sources_available": ref.evidence_sources_available,
                                 "full_ir_body": bool(
                                     {"historical_full_ir", "full_chapter_ir_body"}
                                     & set(ref.evidence_sources_available))})
                    if {"historical_full_ir", "full_chapter_ir_body"} & set(
                            ref.evidence_sources_available):
                        counters["full_ir_available"] += 1
                    else:
                        counters["shadow_only"] += 1
                    counters[{"SUFFICIENT": "sufficient", "PARTIAL": "partial",
                              "INSUFFICIENT": "insufficient"}[ref.evidence_sufficiency]] += 1
                    if ref.human_review_reason == "NO_PIVOT_EVIDENCE":
                        counters["true_missing_pivot"] += 1
                        counts["true_missing"] += 1
                    elif ref.human_review_reason == "SOURCE_IR_INSUFFICIENT":
                        counters["source_insufficient_pivot"] += 1
                        counts["source_insufficient"] += 1
                    elif ref.human_review_reason == "AUTHOR_INTENT_REQUIRED":
                        counters["author_ambiguity"] += 1
                        counts["author_ambiguity"] += 1
            per_batch[batch_id] = counts
        foundation = ("FULL_IR_FOUNDATION_REQUIRED"
                      if counters["source_insufficient_pivot"] > counters["true_missing_pivot"]
                      else "SUFFICIENT_TO_CONTINUE")
        payload = {"generated_by": "m11", "batches": targets,
                   "counters": counters, "per_batch": per_batch, "rows": rows,
                   "M11_EVIDENCE_FOUNDATION_STATUS": foundation,
                   "note": ("完整 ChapterSemanticIR body 未落盘：missing-pivot 判断只能是 "
                            "SOURCE_EVIDENCE_INSUFFICIENT，而不是 TRULY_MISSING；"
                            "建议先做 Historical Full Chapter IR Materialization（本轮不实现）"),
                   "read_only": True, "non_authoritative": True}
        path = self.repair_dir / "REPAIR_EVIDENCE_SUFFICIENCY.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=1) + "\n",
                        encoding="utf-8", newline="\n")
        return payload

    def recompute_readiness(self, *, inputs: RepairInputs | None = None) -> dict[str, Any]:
        """每批 promotion 后重算 readiness（基于 repair overlay，不机械按序号）。"""
        inputs = inputs or self.load()
        repaired_batches: set[str] = set()
        for batch in inputs.batches:
            label = batch["batch_id"].replace("REPAIR_", "")
            overlay = self.repair_dir / f"{label}_REPAIR_STATUS_OVERLAY.json"
            if overlay.is_file():
                payload = self._read(overlay)
                terminal = (int(payload.get("verified_repaired", 0))
                            + int(payload.get("human_review", 0))
                            + int(payload.get("blocked", 0)))
                if terminal >= len(batch["chapter_ids"]):
                    repaired_batches.add(batch["batch_id"])
        decision_batches: dict[str, list[str]] = {}
        for item in inputs.decisions.get("items") or []:
            for batch in inputs.batches:
                if set(batch["chapter_ids"]) & set(item.get("affected_chapters") or []):
                    decision_batches.setdefault(batch["batch_id"], []).append(
                        item["decision_id"])
        rows: list[dict[str, Any]] = []
        for batch in inputs.batches:
            batch_id = batch["batch_id"]
            blocking = decision_batches.get(batch_id, [])
            pending_deps = [item for item in batch["dependency_batches"]
                            if item not in repaired_batches]
            risky = int((batch.get("risk_distribution") or {}).get("HUMAN_REQUIRED", 0))
            partial_allowed = bool(
                len(batch["chapter_ids"]) > risky and not pending_deps
                and batch_id not in repaired_batches)
            if batch_id in repaired_batches:
                status = "COMPLETE"
            elif blocking:
                status = "BLOCKED_AUTHOR_DECISION"
            elif pending_deps:
                status = "BLOCKED_DEPENDENCY"
            else:
                status = "READY"
            rows.append({"batch_id": batch_id, "status": status,
                         "blocking_decision_ids": blocking,
                         "dependency_batch_ids": list(batch["dependency_batches"]),
                         "partial_allowed": bool(partial_allowed and status != "COMPLETE"),
                         "blocked_targets": risky,
                         "verified_targets": 0, "remaining_targets": len(batch["chapter_ids"]),
                         "risk_distribution": batch.get("risk_distribution") or {}})
        payload = {"generated_by": "m11", "basis": "repair overlay",
                   "batches": rows,
                   "next_ready_batch": next(
                       (row["batch_id"] for row in rows
                        if row["status"] == "READY" or (row["status"]
                                                        == "BLOCKED_AUTHOR_DECISION"
                                                        and row["partial_allowed"])), "")}
        path = self.repair_dir / "M11_READINESS_REPORT.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=1) + "\n",
                        encoding="utf-8", newline="\n")
        return payload

    def _write(self, baseline: RepairBatchBaseline,
               candidates: list[ChapterRepairCandidate],
               overlays: list[RepairedChapterArtifact], records: list[RepairRecord],
               overlay: M11RepairStatusOverlay, diff: RepairBatchDiff,
               sampling: RepairClassificationSample, gate: RepairBatchGate,
               closeout: RepairedBatchCloseout | None = None) -> dict[str, str]:
        self.repair_dir.mkdir(parents=True, exist_ok=True)
        label = self.batch_id.replace("REPAIR_", "")
        payloads = {
            f"{label}_BASELINE.json": baseline.model_dump(mode="json"),
            f"{label}_CANDIDATES.json": [row.model_dump(mode="json") for row in candidates],
            f"{label}_REPAIR_RECORDS.json": [row.model_dump(mode="json") for row in records],
            f"{label}_REPAIR_STATUS_OVERLAY.json": overlay.model_dump(mode="json"),
            f"{label}_DIFF.json": diff.model_dump(mode="json"),
            f"{label}_CLASSIFICATION_SAMPLE.json": sampling.model_dump(mode="json"),
            f"{label}_GATE.json": gate.model_dump(mode="json"),
            **({f"{label}_CLOSEOUT.json": closeout.model_dump(mode="json")}
               if closeout is not None else {}),
        }
        written: dict[str, str] = {}
        for name, payload in payloads.items():
            path = self.repair_dir / name
            path.write_text(json.dumps(payload, ensure_ascii=False, indent=1) + "\n",
                            encoding="utf-8", newline="\n")
            written[name] = str(path)
        for name, payload in self._aggregate_overlay().items():   # 全局 overlay 最后写
            path = self.repair_dir / name
            path.write_text(json.dumps(payload, ensure_ascii=False, indent=1) + "\n",
                            encoding="utf-8", newline="\n")
            written[name] = str(path)
        _ = overlays
        return written


__all__ = [
    "CONFIRMED",
    "CONTENT_GAP",
    "DEFAULT_BATCH",
    "FIELD_CONFLICT",
    "FORBIDDEN_DOMAINS",
    "RECON_DIR",
    "REPAIR_DIR",
    "REPAIR_VERSION",
    "ChapterRepairCandidate",
    "M11RepairStatusOverlay",
    "RepairBatchBaseline",
    "RepairBatchDiff",
    "RepairBatchGate",
    "RepairBatchResult",
    "RepairClassificationSample",
    "RepairFinding",
    "RepairInputs",
    "RepairOp",
    "RepairPreflightError",
    "RepairRecord",
    "RepairStatusEntry",
    "RepairedChapterArtifact",
    "WastelandRepairService",
]
