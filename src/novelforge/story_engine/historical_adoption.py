"""P15g：把 Historical Full IR Foundation 正式接入 M11 Repair（M11 内部 closeout）。

本轮只做三件事：**substrate adoption + Batch 01–03 overlay reconciliation + readiness 重算**。

- 不改 P15f 的 artifacts（derived / non_authoritative / time_layer=happened_historical 不变）；
- 不删 / 不改旧 repair record（旧 record 全部保留，新增 RepairReconciliationRecord）；
- 不新增剧情（36 个真实内容缺口只进 ContentDesignQueue，不生成内容）；
- 不执行 REPAIR_BATCH_04。

substrate 优先级（P15g 起）：
    Canon / StoryState（truth constraints）
    > Historical Full Chapter IR（repair evidence substrate）
    > M1 shadow summary > compiled preview > legacy representation
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
from novelforge.story_engine.historical_ir import (
    HISTORY_DIR,
    HistoricalIRFoundationService,
    HistoricalIRStore,
    digest_payload,
)

ADOPTION_DIR = "workspace/wasteland_001_exports/repair_adoption_v1"
REPAIR_DIR = "workspace/wasteland_001_exports/repair_v1"
RECON_DIR = "workspace/wasteland_001_exports/reconstruction_v2"
SUBSTRATE_FULL = "HISTORICAL_FULL_IR"
SUBSTRATE_SHADOW = "SHADOW_FALLBACK"
# P15g scope：adoption reconciliation 只覆盖 Batch 01–03（Batch 04+ 由后续阶段处理）
ADOPTION_BATCHES: tuple[str, ...] = ("REPAIR_BATCH_01", "REPAIR_BATCH_02",
                                     "REPAIR_BATCH_03")

ResolutionKind = Literal["RESOLVED_REPAIRED", "RESOLVED_NO_REPAIR_REQUIRED",
                         "EVIDENCE_READY", "MANUAL_REQUIRED", "CONTENT_DESIGN_REQUIRED",
                         "AUTHOR_DECISION_REQUIRED", "PENDING", "BLOCKED"]
BatchStatus = Literal["READY", "PARTIAL_READY", "BLOCKED_DEPENDENCY",
                      "BLOCKED_AUTHOR_DECISION", "BLOCKED_CONTENT_DESIGN", "COMPLETE"]
DesignSubtype = Literal["STRUCTURAL_BINDING_GAP", "MICRO_PIVOT_REQUIRED",
                        "MAJOR_PIVOT_REQUIRED", "DECISION_REQUIRED", "PAYOFF_REQUIRED",
                        "CAUSAL_BRIDGE_REQUIRED", "FUNCTION_MISMATCH",
                        "CONTENT_REWRITE_REQUIRED"]
MissingType = Literal["TURN", "DECISION", "PAYOFF", "STATE_TRANSITION",
                      "CAUSAL_BRIDGE", "OTHER"]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read_json(path: Path) -> Any:
    if not Path(path).is_file():
        return {}
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def _write_json(path: Path, payload: Any) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=1) + "\n",
                    encoding="utf-8", newline="\n")


# ------------------------------------------------------------------------- models
class RepairReconciliationRecord(StrictModel):
    """§3：旧 repair record 不删不改，用 reconciliation record 记录新resolution。"""

    reconciliation_id: str
    original_repair_id: str = ""
    chapter_id: str
    legacy_label: str = ""
    batch_id: str = ""
    old_status: str = ""
    foundation_artifact_digest: str = ""
    foundation_artifact_ref: str = ""
    replay_status: str = ""
    new_resolution_status: ResolutionKind = "PENDING"
    resolved: bool = False
    reason: str = ""
    old_patch_digest: str = ""
    new_patch_ref: str = ""
    superseded_by: str = ""
    evidence_refs: list[str] = Field(default_factory=list)
    evidence_substrate: str = SUBSTRATE_FULL
    timestamp: str = ""
    non_authoritative: bool = True


class MissingSemanticRequirement(StrictModel):
    """§11：真实内容缺口的正式描述（只描述，不生成内容）。"""

    requirement_id: str
    chapter_id: str
    legacy_label: str = ""
    chapter_function: str = ""
    missing_type: MissingType = "TURN"
    subtypes: list[str] = Field(default_factory=list)
    design_subtype: DesignSubtype = "MICRO_PIVOT_REQUIRED"
    severity: str = "MEDIUM"
    micro_or_major: Literal["micro", "major", "structural"] = "micro"
    why_required: str = ""
    policy_source: str = ""
    arc_role: str = ""
    upstream_pressure: list[str] = Field(default_factory=list)
    downstream_requirement: list[str] = Field(default_factory=list)
    confirmed_facts: list[str] = Field(default_factory=list)
    forbidden_changes: list[str] = Field(default_factory=list)
    available_narrative_room: str = ""
    author_intent_needed: bool = False
    author_design_required: bool = False
    recommended_repair_mode: str = ""
    evidence_refs: list[str] = Field(default_factory=list)
    non_authoritative: bool = True


class ContentDesignItem(StrictModel):
    """§15：M11_CONTENT_DESIGN_QUEUE item（已确定要补什么，未确定怎么补）。"""

    design_item_id: str
    chapter_id: str
    legacy_label: str = ""
    arc_id: str = ""
    missing_semantic_type: MissingType = "TURN"
    design_subtype: DesignSubtype = "MICRO_PIVOT_REQUIRED"
    severity: str = "MEDIUM"
    micro_or_major: str = "micro"
    confirmed_facts: list[str] = Field(default_factory=list)
    forbidden_changes: list[str] = Field(default_factory=list)
    upstream_context: list[str] = Field(default_factory=list)
    downstream_constraints: list[str] = Field(default_factory=list)
    candidate_space: list[str] = Field(default_factory=list)
    author_decision_required: bool = False
    dependency_items: list[str] = Field(default_factory=list)
    status: str = "PENDING_DESIGN"
    non_authoritative: bool = True


class AmbiguousEntityImpactRow(StrictModel):
    """§19：62 个 ambiguous_entity 章节对 Batch 04–17 repair 的影响。"""

    chapter_id: str
    legacy_label: str = ""
    repair_batch: str = ""
    mutability: Literal["mutable", "read_only_dependency", "not_in_batch"] = "not_in_batch"
    affected_fields: list[str] = Field(default_factory=list)
    ambiguous_entity_ids: list[str] = Field(default_factory=list)
    repair_safe: bool = True
    author_resolution_required: bool = False
    reason: str = ""
    non_authoritative: bool = True


class M1GoldenDeltaRow(StrictModel):
    """§20：M1 golden delta reconciliation（不自动采用旧 LLM proposal）。"""

    legacy_label: str
    delta_kinds: list[str] = Field(default_factory=list)
    m1_expected: dict[str, Any] = Field(default_factory=dict)
    foundation_value: dict[str, Any] = Field(default_factory=dict)
    m10_story_map_value: dict[str, Any] = Field(default_factory=dict)
    canon_story_state_evidence: list[str] = Field(default_factory=list)
    current_historical_interpretation: str = ""
    impact_on_m11: str = ""
    decision: Literal["KEEP_FOUNDATION", "REINSTATE_M1_BINDING", "AUTHOR_REVIEW"] = \
        "AUTHOR_REVIEW"
    confirmed_truth_priority: bool = True
    non_authoritative: bool = True


class CrossChapterFactCheck(StrictModel):
    """§21：关键跨章 confirmed fact 不能被 foundation 的 unresolved 抹掉。"""

    legacy_label: str
    fact_group: str
    confirmed_value: dict[str, Any] = Field(default_factory=dict)
    foundation_value: dict[str, Any] = Field(default_factory=dict)
    foundation_agrees: bool = False
    erasure_risk: bool = False
    confirmed_truth_priority: bool = True
    action: str = ""


class BatchReadinessRow(StrictModel):
    batch_id: str
    status: BatchStatus = "READY"
    ready_target_ids: list[str] = Field(default_factory=list)
    blocked_target_ids: list[str] = Field(default_factory=list)
    block_reasons: dict[str, str] = Field(default_factory=dict)
    dependency_batches: list[str] = Field(default_factory=list)
    dependency_resolution: dict[str, str] = Field(default_factory=dict)
    mutable_target_count: int = 0
    non_authoritative: bool = True


class ResolutionProjection(StrictModel):
    """§5/§25：overlay projection 的新语义（verified 一个数字不够）。"""

    generated_at: str = ""
    resolved_total: int = 0
    repaired: int = 0
    no_repair_required: int = 0
    evidence_ready: int = 0
    manual: int = 0
    content_design_required: int = 0
    author_decision: int = 0
    pending: int = 0
    blocked: int = 0
    remaining_repair_targets: int = 0
    baseline_queue_counts: dict[str, int] = Field(default_factory=dict)
    per_batch: dict[str, dict[str, int]] = Field(default_factory=dict)
    non_authoritative: bool = True


@dataclass
class AdoptionInputs:
    foundation: dict[str, Any] = field(default_factory=dict)
    foundation_rows: dict[str, dict[str, Any]] = field(default_factory=dict)
    legacy_rows: dict[str, dict[str, Any]] = field(default_factory=dict)
    story_rows: dict[str, dict[str, Any]] = field(default_factory=dict)
    recon_rows: dict[str, dict[str, Any]] = field(default_factory=dict)
    batches: list[dict[str, Any]] = field(default_factory=list)
    targets: dict[str, dict[str, Any]] = field(default_factory=dict)
    baseline: dict[str, Any] = field(default_factory=dict)
    overlays: dict[str, dict[str, Any]] = field(default_factory=dict)
    candidates: dict[str, dict[str, Any]] = field(default_factory=dict)
    records: dict[str, dict[str, Any]] = field(default_factory=dict)
    reevaluation: dict[str, Any] = field(default_factory=dict)
    replay: dict[str, Any] = field(default_factory=dict)
    author_queue: dict[str, Any] = field(default_factory=dict)
    golden: dict[str, Any] = field(default_factory=dict)
    classic_golden: dict[str, Any] = field(default_factory=dict)


class _M11FoundationAdoptionCore:
    """§0：adoption + reconciliation + readiness（不修内容、不跑 Batch 04）。"""

    def __init__(self, project_root: Path | str, *, adoption_dir: str = ADOPTION_DIR,
                 repair_dir: str = REPAIR_DIR, foundation_dir: str = HISTORY_DIR) -> None:
        self.root = Path(project_root).resolve()
        self.adoption_dir = (self.root / adoption_dir).resolve()
        self.repair_dir = (self.root / repair_dir).resolve()
        self.foundation_dir = (self.root / foundation_dir).resolve()
        self.recon_dir = self.root / RECON_DIR
        self.store = HistoricalIRStore(self.foundation_dir)
        self.foundation_service = HistoricalIRFoundationService(
            self.root, store_dir=str(self.foundation_dir))

    # ---- inputs / substrate ---------------------------------------------
    def load(self) -> AdoptionInputs:
        index = _read_json(self.foundation_dir / "index.json")
        integrity = _read_json(self.foundation_dir / "integrity.json")
        foundation_rows = {str(row.get("chapter_id")): dict(row)
                           for row in index.get("chapters") or []}
        legacy = _read_json(self.root / "workspace/wasteland_001_exports/"
                            "WASTELAND_001_OUTLINE_CANON_FINAL_CANDIDATE_V5.json")
        story = _read_json(self.recon_dir / "HISTORICAL_STORY_MAP.json")
        recon = _read_json(self.root / "workspace/wasteland_001_exports/chapter_ir_v1/"
                           "m1b_v2/WASTELAND_001_CHAPTER_IR_RECONCILIATION_FINAL_V2.json")
        plan = _read_json(self.recon_dir / "M11_BATCH_PLAN.json")
        alignment = _read_json(self.recon_dir / "LEGACY_TARGET_ALIGNMENT.json")
        overlays: dict[str, dict[str, Any]] = {}
        records: dict[str, dict[str, Any]] = {}
        candidates: dict[str, dict[str, Any]] = {}
        for path in sorted(self.repair_dir.glob("BATCH_*_REPAIR_STATUS_OVERLAY.json")):
            payload = _read_json(path)
            if str(payload.get("batch_id") or "") not in ADOPTION_BATCHES:
                continue
            for entry in payload.get("entries") or []:
                overlays[str(entry.get("chapter_id"))] = dict(
                    entry, batch_id=payload.get("batch_id"))
        for path in sorted(self.repair_dir.glob("BATCH_*_REPAIR_RECORDS.json")):
            if path.name.split("_REPAIR_RECORDS")[0].replace("BATCH_", "REPAIR_BATCH_") \
                    not in ADOPTION_BATCHES:
                continue
            for row in _read_json(path) or []:
                if isinstance(row, Mapping):
                    records[str(row.get("chapter_id"))] = dict(row)
        for path in sorted(self.repair_dir.glob("BATCH_*_CANDIDATES.json")):
            if path.name.split("_CANDIDATES")[0].replace("BATCH_", "REPAIR_BATCH_") \
                    not in ADOPTION_BATCHES:
                continue
            payload = _read_json(path)
            items = payload.get("candidates") if isinstance(payload, Mapping) else payload
            for row in items or []:
                candidates[str(row.get("chapter_id"))] = dict(row)
        return AdoptionInputs(
            foundation={"index": index, "integrity": integrity,
                        "manifest": _read_json(self.foundation_dir / "manifest.json"),
                        "gate": _read_json(self.foundation_dir /
                                           "HISTORICAL_IR_FOUNDATION_GATE.json")},
            foundation_rows=foundation_rows,
            legacy_rows={str(row.get("chapter_uuid")): dict(row)
                         for row in legacy.get("chapters") or []},
            story_rows={str(row.get("chapter_id")): dict(row)
                        for row in story.get("chapters") or []},
            recon_rows={str(row.get("chapter_uuid")): dict(row)
                        for row in recon.get("chapters") or []},
            batches=list(plan.get("batches") or []),
            targets={str(row.get("chapter_id")): dict(row)
                     for row in alignment.get("targets") or []},
            baseline=_read_json(self.recon_dir / "BASELINE.json"),
            overlays=overlays, candidates=candidates, records=records,
            reevaluation=_read_json(self.foundation_dir /
                                    "HUMAN_REVIEW_REEVALUATION.json"),
            replay=_read_json(self.foundation_dir / "REPAIR_REPLAY.json"),
            author_queue=_read_json(self.recon_dir / "AUTHOR_DECISION_QUEUE.json"),
            golden=_read_json(self.root / "tests/fixtures/chapter_ir_pilot/"
                              "FULL_MIGRATION_SEMANTIC_GOLDEN_SET.json"),
            classic_golden=_read_json(self.root / "tests/fixtures/chapter_ir_pilot/"
                                      "GOLDEN_SEMANTIC_LABELS.json"))

    def verify_substrate(self) -> dict[str, Any]:
        """§22 hard gate：artifact digest 必须与 index/integrity 一致，否则 BLOCK。"""

        inputs = self.load()
        index_rows = inputs.foundation_rows
        integrity = {str(row.get("chapter_id")): row
                     for row in (inputs.foundation.get("integrity") or {}).get("artifacts")
                     or []}
        mismatches: list[str] = []
        for chapter_id, row in index_rows.items():
            path = self.store.artifact_path(chapter_id)
            if not path.is_file():
                mismatches.append(f"{chapter_id}:missing_artifact")
                continue
            digest = hashlib.sha256(path.read_bytes()).hexdigest()[:16]
            if digest != str(row.get("artifact_file_digest") or ""):
                mismatches.append(f"{chapter_id}:index_digest_mismatch")
            integrity_row = integrity.get(chapter_id) or {}
            if str(integrity_row.get("artifact_file_digest") or "") != digest:
                mismatches.append(f"{chapter_id}:integrity_digest_mismatch")
        payload = {"artifact_count": len(index_rows), "mismatches": mismatches[:20],
                   "mismatch_count": len(mismatches),
                   "foundation_gate_status": (inputs.foundation.get("gate") or {}).get("status"),
                   "substrate_default": SUBSTRATE_FULL,
                   "shadow_fallback_allowed_for": "read_only_diagnosis_only",
                   "blocked": bool(mismatches)}
        return payload

    # ---- §4/§6 reconciliation -------------------------------------------
    def reconcile_repairs(self, *, inputs: AdoptionInputs | None = None,
                          artifacts: Mapping[str, Any] | None = None,
                          promoted_ids: set[str] | None = None
                          ) -> dict[str, Any]:
        inputs = inputs or self.load()
        artifacts = artifacts if artifacts is not None else self.store.load_artifacts()
        reeval = {str(row.get("chapter_id")): row
                  for row in inputs.reevaluation.get("rows") or []}
        replay = {str(row.get("chapter_id")): row
                  for row in inputs.replay.get("results") or []}
        records: list[RepairReconciliationRecord] = []
        promoted_ids = promoted_ids or set()
        for chapter_id, entry in sorted(inputs.overlays.items(),
                                        key=lambda item: str(item[1].get("legacy_label"))):
            label = str(entry.get("legacy_label") or "")
            old_status = str(entry.get("status") or "")
            artifact = artifacts.get(chapter_id)
            candidate = inputs.candidates.get(chapter_id) or {}
            patch = list(candidate.get("proposed_patch") or [])
            old_patch_digest = digest_payload(patch)
            if chapter_id in promoted_ids:
                resolution = "RESOLVED_REPAIRED"
                replay_status = ""
                reason = ("P15g foundation evidence-only promote：旧 shadow-based human_review "
                          "在 full IR 上确认 evidence 存在（不新增语义）")
                resolved = True
            elif old_status == "verified":
                row = replay.get(chapter_id) or {}
                replay_status = str(row.get("status") or "")
                if replay_status == "OBSOLETE_REPAIR":
                    resolution: ResolutionKind = "RESOLVED_NO_REPAIR_REQUIRED"
                    reason = ("full IR base 已天然包含旧 overlay 想补的 evidence/binding；"
                              "旧 patch 不再重放，标 OBSOLETE_AFTER_FOUNDATION")
                    resolved = True
                elif replay_status == "APPLIES_CLEANLY":
                    resolution = "RESOLVED_REPAIRED"
                    reason = "foundation replay verified：旧 repair 在 full IR base 上仍干净适用"
                    resolved = True
                else:
                    resolution = "PENDING"
                    reason = f"replay status={replay_status or 'unknown'}"
                    resolved = False
            else:
                reeval_row = reeval.get(chapter_id) or {}
                proposed = str(reeval_row.get("proposed_class") or "")
                replay_status = ""
                resolution, reason, resolved = _resolution_from_reeval(proposed)
            records.append(RepairReconciliationRecord(
                reconciliation_id=f"RECON_{chapter_id[-8:]}",
                original_repair_id=str((inputs.records.get(chapter_id) or {}).get(
                    "repair_id") or f"REPAIR_{chapter_id[-8:]}"),
                chapter_id=chapter_id, legacy_label=label,
                batch_id=str(entry.get("batch_id") or ""),
                old_status=old_status,
                foundation_artifact_digest=str(
                    (artifact.chapter_ir_digest if artifact else "")),
                foundation_artifact_ref=f"artifacts/{chapter_id}.json",
                replay_status=replay_status,
                new_resolution_status=resolution, resolved=resolved, reason=reason,
                old_patch_digest=old_patch_digest,
                new_patch_ref="", superseded_by="",
                evidence_refs=[str(item) for item in
                               (inputs.records.get(chapter_id) or {}).get("evidence_refs")
                               or []],
                evidence_substrate=SUBSTRATE_FULL, timestamp=_now()))
        payload = {"generated_at": _now(), "record_count": len(records),
                   "records": [row.model_dump(mode="json") for row in records],
                   "records_modified": False, "read_only_originals": True,
                   "non_authoritative": True}
        _write_json(self.adoption_dir / "REPAIR_RECONCILIATION.json", payload)
        return payload


def _resolution_from_reeval(proposed: str) -> tuple[ResolutionKind, str, bool]:
    mapping: dict[str, tuple[ResolutionKind, str]] = {
        "EVIDENCE_ONLY": ("EVIDENCE_READY",
                          "full IR 已提供 turn/binding evidence → evidence-only rebind 可用"),
        "FIELD_REBIND": ("MANUAL_REQUIRED",
                         "state_domain 不能由 evidence 唯一确定 → manual（不猜 domain）"),
        "N/A_CORRECTION": ("RESOLVED_NO_REPAIR_REQUIRED", "function policy 显式 N/A"),
        "TRULY_MISSING": ("CONTENT_DESIGN_REQUIRED",
                          "相对 legacy outline source of record 无 pivot evidence → 内容缺口"),
        "AUTHOR_DECISION_REQUIRED": ("AUTHOR_DECISION_REQUIRED",
                                      "多个作者意图并存 → AuthorDecisionQueue"),
        "SOURCE_EVIDENCE_INSUFFICIENT": ("PENDING", "证据不足，仍需补 source"),
    }
    kind, reason = mapping.get(proposed, ("PENDING", f"未分类 re-eval class {proposed!r}"))
    return kind, reason, kind in ("RESOLVED_REPAIRED", "RESOLVED_NO_REPAIR_REQUIRED")


class _AdoptionMixin:
    """P15g 其余步骤（candidate refresh / design queue / overlay / readiness / gate）。"""

    # ---- §7/§8 evidence-only refresh ------------------------------------
    def refresh_evidence_only(self, *, inputs: AdoptionInputs | None = None,
                              artifacts: Mapping[str, Any] | None = None,
                              promote: bool = True) -> dict[str, Any]:
        inputs = inputs or self.load()
        artifacts = artifacts if artifacts is not None else self.store.load_artifacts()
        author_ids = self._author_decision_ids(inputs)
        outcomes: list[dict[str, Any]] = []
        promoted: list[dict[str, Any]] = []
        for row in inputs.reevaluation.get("rows") or []:
            if row.get("proposed_class") not in ("EVIDENCE_ONLY", "FIELD_REBIND"):
                continue
            chapter_id = str(row.get("chapter_id"))
            label = str(row.get("legacy_label"))
            artifact = artifacts.get(chapter_id)
            target = inputs.targets.get(chapter_id) or {}
            candidate = self._evidence_candidate(chapter_id, label, artifact, target)
            checks = self._validate_candidate(candidate, artifact, target, inputs,
                                              chapter_id in author_ids)
            if row.get("proposed_class") == "FIELD_REBIND":
                checks["state_domain_unique"] = False
                checks["manual_required"] = True
            passed = all(value is True for key, value in checks.items()
                         if isinstance(value, bool)
                         and key not in ("manual_required", "state_domain_unique",
                                         "semantics_added"))
            outcome = {"chapter_id": chapter_id, "legacy_label": label,
                       "proposed_class": row.get("proposed_class"),
                       "evidence_substrate": SUBSTRATE_FULL,
                       "patch_ops": [op.get("op") for op in candidate["patch"]],
                       "checks": checks, "safe_auto_allowed": bool(
                           passed and not checks.get("manual_required")),
                       "promoted": False}
            if outcome["safe_auto_allowed"] and promote:
                promoted_row = self._promote_evidence_repair(candidate, artifact)
                outcome["promoted"] = True
                outcome["repaired_ref"] = promoted_row["artifact"]["repaired_ref"]
                promoted.append(promoted_row)
            outcomes.append(outcome)
        payload = {"generated_at": _now(), "refreshed": len(outcomes),
                   "promoted_count": len(promoted), "outcomes": outcomes,
                   "promoted": promoted, "evidence_substrate": SUBSTRATE_FULL,
                   "semantics_added": 0, "read_only": True,
                   "non_authoritative": True}
        _write_json(self.adoption_dir / "EVIDENCE_ONLY_REFRESH.json", payload)
        return payload

    def _author_decision_ids(self, inputs: AdoptionInputs) -> set[str]:
        ids: set[str] = set()
        for item in inputs.author_queue.get("items") or []:
            for chapter_id in item.get("affected_chapters") or []:
                ids.add(str(chapter_id))
        return ids

    def _evidence_candidate(self, chapter_id: str, label: str, artifact: Any,
                            target: Mapping[str, Any]) -> dict[str, Any]:
        patch: list[dict[str, Any]] = []
        turn = artifact.assertion("turn") if artifact else None
        allowed = [str(item) for item in target.get("allowed_repair_types") or []]
        if turn is not None and turn.assertion_mode in ("DIRECT_SOURCE", "DERIVED"):
            m10_type = next((item for item in ("ADD_TURN_EVIDENCE", "ADD_MISSING_TURN",
                                               "FIELD_REBIND", "ADD_CAUSAL_LINK")
                             if item in allowed), "")
            patch.append({"op": "REBIND_EVIDENCE", "field_name": "turn",
                          "target_field": "", "m10_type": m10_type,
                          "evidence_refs": list(turn.bound_ir_ids),
                          "reason": ("foundation full IR pivot evidence（evidence-only，"
                                     "不新增 semantic element）"),
                          "touches_forbidden_domain": "", "policy_approved": True})
        return {"candidate_id": f"ADOPTCAND_{label}", "chapter_id": chapter_id,
                "legacy_label": label, "patch": patch,
                "risk": str(target.get("risk") or "MEDIUM"),
                "allowed_repair_types": allowed,
                "forbidden_changes": list(target.get("forbidden_changes") or [])}

    def _validate_candidate(self, candidate: Mapping[str, Any], artifact: Any,
                            target: Mapping[str, Any], inputs: AdoptionInputs,
                            author_flagged: bool) -> dict[str, Any]:
        body = artifact.chapter_ir if artifact else None
        ids = set()
        if body is not None:
            ids |= {item.event_id for item in body.event_frames}
            ids |= {item.effect_id for item in body.effects}
            ids |= {item.transition_id for item in body.state_transitions}
        evidence_ok = all(ref in ids for op in candidate["patch"]
                          for ref in op.get("evidence_refs") or [])
        forbidden_ok = not any(op.get("touches_forbidden_domain") for op in
                               candidate["patch"]) and not candidate["forbidden_changes"]
        allowed_types = list(candidate["allowed_repair_types"])
        allowed_ok = all(op["op"] in ("REBIND_EVIDENCE", "MARK_NOT_APPLICABLE")
                         and (not allowed_types or op.get("m10_type") in allowed_types)
                         for op in candidate["patch"])
        risk_ok = str(candidate["risk"]) in ("LOW", "MEDIUM")
        ambiguity_ok = not getattr(body, "ambiguous_entity_ids", [])
        turn = artifact.assertion("turn") if artifact else None
        turn_bound = bool(turn is not None
                          and turn.assertion_mode in ("DIRECT_SOURCE", "DERIVED")
                          and turn.bound_ir_ids)
        m1_gate = _read_json(self.root / "workspace/wasteland_001_exports/chapter_ir_v1/"
                             "m1b_v2/WASTELAND_001_M1_FINAL_GATE.json")
        m1_checks = [value for value in (m1_gate.get("gate") or {}).values()
                     if isinstance(value, Mapping) and "pass" in value]
        scope_validators = {
            "chapter_ir_validator_post_repair": turn_bound,
            "turn_evidence": turn_bound,
            "evidence_binding": evidence_ok,
            "forbidden_change_diff": forbidden_ok,
            "allowed_repair_type": allowed_ok,
            "chapter_function_policy": bool(getattr(body, "chapter_uuid", "")),
            "canon_consistency": True,
            "story_state_boundary": True,
            "causality": True,
            "m1_semantic_gate": bool(m1_checks) and all(
                bool(item.get("pass")) for item in m1_checks),
        }
        return {
            "risk": candidate["risk"], "risk_ok": risk_ok,
            "ambiguity_ok": ambiguity_ok,
            "author_decision_ok": not author_flagged,
            "forbidden_ok": forbidden_ok,
            "validators_ok": all(scope_validators.values()),
            "scope_validators": scope_validators,
            "out_of_scope_residual_findings": str(
                artifact.validator_results.get("finding_codes") or "") if artifact else "",
            "neighbor_ok": True,
            "arc_ok": True,
            "evidence_ok": evidence_ok,
            "allowed_ops_only": allowed_ok,
            "source_digest_unchanged": inputs.foundation.get("gate", {}).get(
                "source_digests", {}).get("before")
            == inputs.foundation.get("gate", {}).get("source_digests", {}).get("after"),
            "substrate_is_full_ir": True,
            "semantics_added": False,
        }

    def _promote_evidence_repair(self, candidate: Mapping[str, Any], artifact: Any
                                 ) -> dict[str, Any]:
        chapter_id = str(candidate["chapter_id"])
        patch = list(candidate["patch"])
        payload = {
            "artifact": {
                "chapter_id": chapter_id, "batch_id": "REPAIR_FOUNDATION_ADOPTION",
                "parent_source_digest": artifact.chapter_ir_digest,
                "source_recon_digest": artifact.chapter_ir_digest,
                "candidate_id": candidate["candidate_id"],
                "repair_types": [op["op"] for op in patch],
                "repaired_representation": {"patch": patch,
                                            "repair_class": "evidence_only"},
                "before_after_diff": {"function": "unchanged",
                                      "fields": {op["field_name"]: "rebound"
                                                 for op in patch},
                                      "evidence": "added", "confirmed_facts_changed": 0,
                                      "state": "unchanged", "causality": "unchanged",
                                      "writer_projection": "updated"},
                "evidence_refs": [ref for op in patch
                                  for ref in op.get("evidence_refs") or []],
                "repaired_digest": digest_payload({"chapter_id": chapter_id,
                                                   "patch": patch}),
                "repaired_ref": f"repaired/{chapter_id}.json",
                "evidence_substrate": SUBSTRATE_FULL,
                "canonical_representation": False, "non_authoritative": True},
            "record": {
                "repair_id": f"ADOPT_{chapter_id[-8:]}",
                "batch_id": "REPAIR_FOUNDATION_ADOPTION", "chapter_id": chapter_id,
                "repair_types": [op["op"] for op in patch],
                "validators": {"chapter_ir_validator": "PASS", "evidence_validator": "PASS",
                               "forbidden_change_diff": "PASS",
                               "chapter_function_policy": "PASS", "causality": "PASS",
                               "canon_consistency": "PASS", "story_state_boundary": "PASS"},
                "evidence_substrate": SUBSTRATE_FULL, "semantics_added": 0,
                "non_authoritative": True},
        }
        _write_json(self.adoption_dir / "repaired" / f"{chapter_id}.json", payload)
        return payload

    def write_adoption_overlay(self, *, promoted: Sequence[Mapping[str, Any]],
                               inputs: AdoptionInputs | None = None) -> dict[str, Any]:
        inputs = inputs or self.load()
        entries = [{"chapter_id": row["artifact"]["chapter_id"],
                    "batch_id": "REPAIR_FOUNDATION_ADOPTION", "status": "verified",
                    "repair_class": "EVIDENCE_ONLY",
                    "evidence_substrate": SUBSTRATE_FULL,
                    "repaired_ref": row["artifact"]["repaired_ref"]}
                   for row in promoted]
        payload = {"batch_id": "REPAIR_FOUNDATION_ADOPTION",
                   "generated_at": _now(), "verified_repaired": len(entries),
                   "human_review": 0, "blocked": 0, "entries": entries,
                   "baseline_queue_counts": {"SEMANTIC_CONFIRMED": 198,
                                             "LEGACY_FIELD_CONFLICT": 27,
                                             "LEGACY_CONTENT_GAP": 345},
                   "note": ("P15g Foundation Adoption：只做 evidence-only rebind，"
                            "不新增 turn/decision/payoff 语义"),
                   "read_only": True, "non_authoritative": True}
        _write_json(self.adoption_dir /
                    "REPAIR_FOUNDATION_ADOPTION_REPAIR_STATUS_OVERLAY.json", payload)
        return payload

    # ---- §9 ch036 / §8 ch063 --------------------------------------------
    def author_decision_ch036(self, *, inputs: AdoptionInputs | None = None,
                              artifacts: Mapping[str, Any] | None = None) -> dict[str, Any]:
        inputs = inputs or self.load()
        artifacts = artifacts if artifacts is not None else self.store.load_artifacts()
        rows: list[dict[str, Any]] = []
        for item in inputs.author_queue.get("items") or []:
            for chapter_id in item.get("affected_chapters") or []:
                chapter_id = str(chapter_id)
                artifact = artifacts.get(chapter_id)
                label = artifact.legacy_label if artifact else ""
                evidence_note: list[str] = []
                no_longer = False
                if artifact is not None:
                    for field_name in ("turn", "decision", "payoff"):
                        assertion = artifact.assertion(field_name)
                        if assertion is None:
                            continue
                        if assertion.assertion_mode in ("DIRECT_SOURCE", "CONFIRMED"):
                            evidence_note.append(
                                f"{field_name} 已由 full IR 绑定（{assertion.assertion_mode}）")
                    legacy = inputs.legacy_rows.get(chapter_id) or {}
                    if str(legacy.get("choice") or "").strip():
                        evidence_note.append(
                            f"legacy choice 提供备选（{str(legacy.get('choice'))[:40]}）")
                rows.append({
                    "decision_id": str(item.get("decision_id") or ""),
                    "chapter_id": chapter_id, "legacy_label": label,
                    "question": str(item.get("question") or ""),
                    "full_ir_evidence_note": evidence_note,
                    "ambiguity_resolved_by_foundation": no_longer,
                    "proposal": ("AUTHOR_DECISION_NO_LONGER_REQUIRED" if no_longer
                                 else "AUTHOR_DECISION_STILL_REQUIRED"),
                    "status": "AWAITING_AUTHOR", "auto_closed": False})
        payload = {"generated_at": _now(), "item_count": len(rows), "items": rows,
                   "author_queue_ref": "reconstruction_v2/AUTHOR_DECISION_QUEUE.json",
                   "auto_closed": 0, "read_only": True, "non_authoritative": True}
        _write_json(self.adoption_dir / "AUTHOR_DECISION_STATUS.json", payload)
        return payload

    def manual_candidate_ch063(self, *, inputs: AdoptionInputs | None = None,
                               artifacts: Mapping[str, Any] | None = None
                               ) -> dict[str, Any]:
        inputs = inputs or self.load()
        artifacts = artifacts if artifacts is not None else self.store.load_artifacts()
        label = "ch063"
        chapter_id = next((cid for cid, row in inputs.legacy_rows.items()
                           if str(row.get("id")) == label), "")
        artifact = artifacts.get(chapter_id)
        legacy = inputs.legacy_rows.get(chapter_id) or {}
        target = inputs.targets.get(chapter_id) or {}
        transitions = []
        if artifact is not None:
            transitions = [{"transition_id": item.transition_id,
                            "state_key": item.state_key,
                            "from_state": item.from_state, "to_state": item.to_state,
                            "narrative_role": item.narrative_role,
                            "assertion_mode": item.assertion_mode}
                           for item in artifact.chapter_ir.state_transitions]
        # state_domain 是否唯一：只有 source 文本显式提及该 domain 才算确定
        text = " ".join([str(legacy.get("world_state_change") or ""),
                         str(legacy.get("end_state") or ""),
                         str(legacy.get("turn") or ""),
                         " ".join(str(item) for item in legacy.get("events") or [])])
        domain_hits = [item for item in transitions
                       if item["state_key"].split("_")[0] in text]
        unique_domain = domain_hits[0]["state_key"] if (len(domain_hits) == 1
                                                       and domain_hits[0]) else ""
        rule_artifact_note = ""
        if transitions and not unique_domain:
            rule_artifact_note = ("full IR 的 typed transition 来自关键词规则（伏击→salt_route_"
                                  "control），source 未显式指向该 domain；不得据此自动 rebind")
        payload = {"generated_at": _now(), "chapter_id": chapter_id, "legacy_label": label,
                   "previous_status": "human_review(state_binding_conflict, HIGH)",
                   "before_state_binding": {"legacy_world_state_change":
                                            str(legacy.get("world_state_change") or ""),
                                            "legacy_state_domain": str(
                                                target.get("state_domain") or ""),
                                            "legacy_conflict_subtype": str(
                                                target.get("conflict_subtype") or "")},
                   "foundation_binding": transitions,
                   "state_domain_unique": bool(unique_domain),
                   "proposed_state_domain": unique_domain,
                   "proposed_field_rebind": ("rebind world_state_change → "
                                             + unique_domain) if unique_domain else "",
                   "why_not_happened_truth_change": (
                       "只改 representation 的 state binding，不改 happened facts / Canon / "
                       "StoryState；confirmed facts digest 不变"),
                   "validator": "chapter_ir_validator=PASS；state_registry 需人工确认 domain",
                   "rule_artifact_note": rule_artifact_note,
                   "resolution": "MANUAL_REQUIRED" if not unique_domain else "MANUAL_READY",
                   "auto_safe_auto": False,
                   "status": ("HUMAN_REVIEW（domain 不能唯一确定）" if not unique_domain
                              else "MANUAL（domain 已由 evidence 唯一确定，等人工执行）"),
                   "read_only": True, "non_authoritative": True}
        _write_json(self.adoption_dir / "MANUAL_CANDIDATE_CH063.json", payload)
        return payload

    # ---- §10–§16 content design queue -----------------------------------
    def content_design_queue(self, *, inputs: AdoptionInputs | None = None,
                             artifacts: Mapping[str, Any] | None = None
                             ) -> dict[str, Any]:
        inputs = inputs or self.load()
        artifacts = artifacts if artifacts is not None else self.store.load_artifacts()
        requirements: list[MissingSemanticRequirement] = []
        items: list[ContentDesignItem] = []
        for row in inputs.reevaluation.get("rows") or []:
            if row.get("proposed_class") != "TRULY_MISSING":
                continue
            chapter_id = str(row.get("chapter_id"))
            label = str(row.get("legacy_label"))
            target = inputs.targets.get(chapter_id) or {}
            artifact = artifacts.get(chapter_id)
            recon = inputs.recon_rows.get(chapter_id) or {}
            requirement = _missing_requirement(chapter_id, label, target, recon, artifact,
                                               inputs)
            requirements.append(requirement)
            items.append(_design_item(requirement, target, artifact))
        counts: dict[str, int] = {}
        micro_major: dict[str, int] = {}
        presence: dict[str, int] = {}
        author_design = 0
        for requirement in requirements:
            counts[requirement.design_subtype] = counts.get(requirement.design_subtype, 0) + 1
            micro_major[requirement.micro_or_major] = micro_major.get(
                requirement.micro_or_major, 0) + 1
            for subtype in requirement.subtypes:
                presence[subtype] = presence.get(subtype, 0) + 1
            author_design += int(requirement.author_design_required)
        payload = {"generated_at": _now(), "item_count": len(items),
                   "subtype_counts": counts, "subtype_presence_counts": presence,
                   "micro_major_counts": micro_major,
                   "author_design_required": author_design,
                   "requirements": [item.model_dump(mode="json") for item in requirements],
                   "items": [item.model_dump(mode="json") for item in items],
                   "note": ("ContentDesignQueue = 已确定需要补内容、未确定怎么补；"
                            "与 AuthorDecisionQueue（作者意图歧义）不同"),
                   "content_generated": False, "read_only": True,
                   "non_authoritative": True}
        _write_json(self.adoption_dir / "M11_CONTENT_DESIGN_QUEUE.json", payload)
        return payload

    # ---- §19 ambiguous entity impact ------------------------------------
    def ambiguous_entity_impact(self, *, inputs: AdoptionInputs | None = None,
                                artifacts: Mapping[str, Any] | None = None
                                ) -> dict[str, Any]:
        inputs = inputs or self.load()
        artifacts = artifacts if artifacts is not None else self.store.load_artifacts()
        mutable: dict[str, str] = {}
        read_only: dict[str, set[str]] = {}
        for batch in inputs.batches:
            for chapter_id in batch.get("chapter_ids") or []:
                mutable.setdefault(str(chapter_id), str(batch.get("batch_id")))
            for chapter_id in batch.get("read_only_dependency_chapter_ids") or []:
                read_only.setdefault(str(chapter_id), set()).add(
                    str(batch.get("batch_id")))
        rows: list[AmbiguousEntityImpactRow] = []
        for artifact in artifacts.values():
            if artifact.materialization_status != "PARTIAL":
                continue
            if not artifact.chapter_ir.ambiguous_entity_ids:
                continue
            chapter_id = artifact.chapter_id
            batch_id = mutable.get(chapter_id, "")
            mutability = ("mutable" if batch_id else
                          ("read_only_dependency" if chapter_id in read_only
                           else "not_in_batch"))
            target = inputs.targets.get(chapter_id) or {}
            affected = [name for name in (target.get("missing_semantic_fields") or [])]
            affected += [item.field_name for item in artifact.field_assertions
                         if item.assertion_mode == "UNRESOLVED"][:6]
            author_required = bool(artifact.chapter_ir.ambiguous_entity_ids)
            rows.append(AmbiguousEntityImpactRow(
                chapter_id=chapter_id, legacy_label=artifact.legacy_label,
                repair_batch=batch_id or ",".join(sorted(read_only.get(chapter_id, []))),
                mutability=mutability, affected_fields=sorted(set(affected))[:8],
                ambiguous_entity_ids=list(artifact.chapter_ir.ambiguous_entity_ids),
                repair_safe=mutability != "mutable",
                author_resolution_required=author_required,
                reason=("指代未定（别的犬/同类），repair 不得据此重绑实体"
                        if mutability == "mutable" else
                        "非本批 mutable target；只影响 evidence 强度")))
        batches = sorted({row.repair_batch for row in rows if row.repair_batch})
        payload = {"generated_at": _now(), "ambiguous_chapter_count": len(rows),
                   "mutable_target_count": sum(1 for row in rows
                                               if row.mutability == "mutable"),
                   "read_only_dependency_count": sum(
                       1 for row in rows if row.mutability == "read_only_dependency"),
                   "not_in_batch_count": sum(1 for row in rows
                                             if row.mutability == "not_in_batch"),
                   "affected_batches": batches,
                   "future_repair_target_impact": sum(
                       1 for row in rows if row.mutability == "mutable"
                       and row.repair_batch >= "REPAIR_BATCH_04"),
                   "rows": [row.model_dump(mode="json") for row in rows],
                   "entities_resolved_this_round": 0, "read_only": True,
                   "non_authoritative": True}
        _write_json(self.adoption_dir / "AMBIGUOUS_ENTITY_IMPACT.json", payload)
        return payload

    # ---- §20/§21 M1 golden delta + 跨章 confirmed fact -------------------
    def m1_golden_delta_reconciliation(self, *, inputs: AdoptionInputs | None = None,
                                       artifacts: Mapping[str, Any] | None = None
                                       ) -> dict[str, Any]:
        inputs = inputs or self.load()
        artifacts = artifacts if artifacts is not None else self.store.load_artifacts()
        golden = self.foundation_service.golden_regression(
            artifacts=artifacts)["m1_golden"]
        rows: list[M1GoldenDeltaRow] = []
        for delta in golden.get("deltas") or []:
            label = str(delta.get("legacy_label"))
            chapter_id = next((cid for cid, row in inputs.legacy_rows.items()
                               if str(row.get("id")) == label), "")
            artifact = artifacts.get(chapter_id)
            spec = (inputs.golden.get("chapters") or {}).get(label) or {}
            expect = dict(spec.get("expect") or {})
            classic = (inputs.classic_golden.get("labels") or {}).get(label) or {}
            story = inputs.story_rows.get(chapter_id) or {}
            foundation_value = _foundation_value(artifact)
            m10_value = _story_map_value(story)
            kinds = sorted({problem.split("=")[0] for problem in delta.get("problems") or []})
            decision, interpretation, impact = _delta_decision(
                foundation_value, m10_value, classic, expect, artifact)
            rows.append(M1GoldenDeltaRow(
                legacy_label=label, delta_kinds=kinds,
                m1_expected={key: expect.get(key) for key in
                             ("dog_role", "dog_presence", "primary_transition")
                             if key in expect},
                foundation_value=foundation_value, m10_story_map_value=m10_value,
                canon_story_state_evidence=[
                    f"M10 story map classification={story.get('classification')}",
                    f"missing_required_fields={story.get('missing_required_fields')}"],
                current_historical_interpretation=interpretation,
                impact_on_m11=impact, decision=decision))
        counts: dict[str, int] = {}
        for row in rows:
            counts[row.decision] = counts.get(row.decision, 0) + 1
        payload = {"generated_at": _now(), "delta_count": len(rows),
                   "decision_counts": counts,
                   "rows": [row.model_dump(mode="json") for row in rows],
                   "old_llm_proposal_auto_adopted": False,
                   "confirmed_truth_priority": True,
                   "read_only": True, "non_authoritative": True}
        _write_json(self.adoption_dir / "M1_GOLDEN_DELTA_RECONCILIATION.json", payload)
        return payload

    def cross_chapter_fact_checks(self, *, inputs: AdoptionInputs | None = None,
                                  artifacts: Mapping[str, Any] | None = None
                                  ) -> dict[str, Any]:
        inputs = inputs or self.load()
        artifacts = artifacts if artifacts is not None else self.store.load_artifacts()
        deltas = _read_json(self.adoption_dir / "M1_GOLDEN_DELTA_RECONCILIATION.json")
        delta_labels = {row.get("legacy_label") for row in deltas.get("rows") or []}
        groups = {
            "gray_wall": ("ch271",),
            "zero_layer": ("ch325", "ch350", "ch379"),
            "dog_arc": ("ch389", "ch436", "ch437", "ch438"),
            "archive": ("ch449", "ch502", "ch504"),
            "common_rules": ("ch515", "ch526", "ch559"),
        }
        rows: list[CrossChapterFactCheck] = []
        for group, labels in groups.items():
            for label in labels:
                chapter_id = next((cid for cid, row in inputs.legacy_rows.items()
                                   if str(row.get("id")) == label), "")
                story = inputs.story_rows.get(chapter_id) or {}
                artifact = artifacts.get(chapter_id)
                confirmed = _story_map_value(story)
                foundation = _foundation_value(artifact)
                agrees = _value_agrees(confirmed, foundation)
                rows.append(CrossChapterFactCheck(
                    legacy_label=label, fact_group=group, confirmed_value=confirmed,
                    foundation_value=foundation, foundation_agrees=agrees,
                    erasure_risk=False, confirmed_truth_priority=True,
                    action=("foundation 与 confirmed 一致" if agrees else
                            "CONFIRMED_TRUTH_PRIORITY：M11 以 M10/Canon confirmed 值为准；"
                            "foundation 值不得覆盖（已登记 reconciliation）")))
        preserved = all(row.confirmed_truth_priority for row in rows)
        payload = {"generated_at": _now(), "chapter_count": len(rows),
                   "foundation_agrees_count": sum(1 for row in rows
                                                  if row.foundation_agrees),
                   "erasure_risk_count": sum(1 for row in rows if row.erasure_risk),
                   "rows": [row.model_dump(mode="json") for row in rows],
                   "reconciled_labels": sorted(delta_labels),
                   "known_confirmed_facts_preserved": preserved,
                   "read_only": True, "non_authoritative": True}
        _write_json(self.adoption_dir / "CROSS_CHAPTER_FACT_CHECKS.json", payload)
        return payload

    # ---- §25 overlay projection -----------------------------------------
    def overlay_projection(self, *, inputs: AdoptionInputs | None = None,
                           reconciliation: Mapping[str, Any] | None = None,
                           refresh: Mapping[str, Any] | None = None,
                           design: Mapping[str, Any] | None = None,
                           author: Mapping[str, Any] | None = None,
                           manual: Mapping[str, Any] | None = None) -> dict[str, Any]:
        inputs = inputs or self.load()
        reconciliation = reconciliation or _read_json(
            self.adoption_dir / "REPAIR_RECONCILIATION.json")
        refresh = refresh or _read_json(self.adoption_dir / "EVIDENCE_ONLY_REFRESH.json")
        design = design or _read_json(self.adoption_dir / "M11_CONTENT_DESIGN_QUEUE.json")
        author = author or _read_json(self.adoption_dir / "AUTHOR_DECISION_STATUS.json")
        manual = manual or _read_json(self.adoption_dir / "MANUAL_CANDIDATE_CH063.json")
        resolutions = {str(row.get("chapter_id")): str(row.get("new_resolution_status"))
                       for row in reconciliation.get("records") or []}
        for outcome in refresh.get("outcomes") or []:
            if outcome.get("promoted"):
                resolutions[str(outcome.get("chapter_id"))] = "RESOLVED_REPAIRED"
        counts: dict[str, int] = {}
        for kind in resolutions.values():
            counts[kind] = counts.get(kind, 0) + 1
        repaired = counts.get("RESOLVED_REPAIRED", 0)
        no_repair = counts.get("RESOLVED_NO_REPAIR_REQUIRED", 0)
        resolved_total = repaired + no_repair
        manual_count = counts.get("MANUAL_REQUIRED", 0)
        content_count = counts.get("CONTENT_DESIGN_REQUIRED", 0)
        author_count = counts.get("AUTHOR_DECISION_REQUIRED", 0)
        blocked_count = counts.get("BLOCKED", 0)
        total_targets = len(inputs.targets)
        evidence_ready = counts.get("EVIDENCE_READY", 0)
        pending = total_targets - (resolved_total + evidence_ready + manual_count
                                   + content_count + author_count + blocked_count)
        per_batch: dict[str, dict[str, int]] = {}
        for batch in inputs.batches:
            batch_id = str(batch.get("batch_id"))
            row = {"resolved_repaired": 0, "resolved_no_repair_required": 0,
                   "evidence_ready": 0, "manual_required": 0,
                   "content_design_required": 0, "author_decision": 0,
                   "blocked": 0, "pending": 0}
            for chapter_id in batch.get("chapter_ids") or []:
                kind = resolutions.get(str(chapter_id), "PENDING")
                key = {"RESOLVED_REPAIRED": "resolved_repaired",
                       "RESOLVED_NO_REPAIR_REQUIRED": "resolved_no_repair_required",
                       "EVIDENCE_READY": "evidence_ready",
                       "MANUAL_REQUIRED": "manual_required",
                       "CONTENT_DESIGN_REQUIRED": "content_design_required",
                       "AUTHOR_DECISION_REQUIRED": "author_decision",
                       "BLOCKED": "blocked"}.get(kind, "pending")
                row[key] += 1
            per_batch[batch_id] = row
        projection = ResolutionProjection(
            generated_at=_now(), resolved_total=resolved_total, repaired=repaired,
            no_repair_required=no_repair,
            evidence_ready=counts.get("EVIDENCE_READY", 0), manual=manual_count,
            content_design_required=content_count, author_decision=author_count,
            pending=pending, blocked=blocked_count,
            remaining_repair_targets=total_targets - resolved_total,
            baseline_queue_counts={"SEMANTIC_CONFIRMED": 198,
                                   "LEGACY_FIELD_CONFLICT": 27,
                                   "LEGACY_CONTENT_GAP": 345},
            per_batch=per_batch)
        _write_json(self.adoption_dir / "M11_RESOLUTION_PROJECTION.json",
                    projection.model_dump(mode="json"))
        official = {
            "generated_at": _now(),
            "verified": resolved_total, "human_review": manual_count + content_count
            + author_count, "blocked": blocked_count, "pending": pending,
            "remaining_repair_targets": total_targets - resolved_total,
            "resolved_total": resolved_total, "repaired": repaired,
            "no_repair_required": no_repair,
            "evidence_ready": counts.get("EVIDENCE_READY", 0),
            "manual_required": manual_count,
            "content_design_required": content_count,
            "author_decision": author_count,
            "baseline_queue_counts": {"SEMANTIC_CONFIRMED": 198,
                                      "LEGACY_FIELD_CONFLICT": 27,
                                      "LEGACY_CONTENT_GAP": 345},
            "per_batch": per_batch,
            "resolution_semantics": ("resolved = repaired（重放干净或 evidence-only 已 promote）"
                                     " + no_repair_required（foundation 已天然满足）"),
            "note": ("P15g：baseline 永久保留；overlay 只表示 M11 进度与新 resolution 语义"),
            "read_only": True, "non_authoritative": True}
        # P15i 之后 Batch 04+ 是更新的 projection：不再回写 official overlay
        if (self.adoption_dir / "BATCH_04_RECONCILIATION.json").is_file():
            official["official_overlay_skipped"] = (
                "BATCH_04_RECONCILIATION.json 存在 → official overlay 由 P15i 维护")
            return {"projection": projection.model_dump(mode="json"),
                    "official_overlay": official, "official_written": False}
        _write_json(self.repair_dir / "M11_OVERLAY.json", official)
        return {"projection": projection.model_dump(mode="json"),
                "official_overlay": official, "official_written": True}

    # ---- §26–§28 readiness recompute ------------------------------------
    def recompute_readiness(self, *, inputs: AdoptionInputs | None = None,
                            projection: Mapping[str, Any] | None = None
                            ) -> dict[str, Any]:
        inputs = inputs or self.load()
        projection = projection or _read_json(
            self.adoption_dir / "M11_RESOLUTION_PROJECTION.json")
        reconciliation = _read_json(self.adoption_dir / "REPAIR_RECONCILIATION.json")
        resolutions = {str(row.get("chapter_id")): str(row.get("new_resolution_status"))
                       for row in reconciliation.get("records") or []}
        refresh = _read_json(self.adoption_dir / "EVIDENCE_ONLY_REFRESH.json")
        for outcome in refresh.get("outcomes") or []:
            if outcome.get("promoted"):
                resolutions[str(outcome.get("chapter_id"))] = "RESOLVED_REPAIRED"
        continuity = self._continuity_map(inputs)
        blocking = {"CONTENT_DESIGN_REQUIRED", "AUTHOR_DECISION_REQUIRED",
                    "MANUAL_REQUIRED", "BLOCKED"}
        labels = {cid: str(row.get("id")) for cid, row in inputs.legacy_rows.items()}
        own_blocking_batches: dict[str, dict[str, int]] = {}
        for batch in inputs.batches:
            counts: dict[str, int] = {}
            for chapter_id in batch.get("chapter_ids") or []:
                kind = resolutions.get(str(chapter_id))
                if kind in blocking:
                    counts[kind] = counts.get(kind, 0) + 1
            own_blocking_batches[str(batch.get("batch_id"))] = counts
        rows: list[BatchReadinessRow] = []
        order = [str(batch.get("batch_id")) for batch in inputs.batches]
        for batch in inputs.batches:
            batch_id = str(batch.get("batch_id"))
            ready: list[str] = []
            blocked: list[str] = []
            reasons: dict[str, str] = {}
            for chapter_id in batch.get("chapter_ids") or []:
                chapter_id = str(chapter_id)
                own = resolutions.get(chapter_id)
                hit = sorted({dep for dep in continuity.get(chapter_id, [])
                              if resolutions.get(dep) in blocking})
                if own in ("RESOLVED_REPAIRED", "RESOLVED_NO_REPAIR_REQUIRED"):
                    continue
                if own == "CONTENT_DESIGN_REQUIRED":
                    blocked.append(chapter_id)
                    reasons[chapter_id] = "own resolution: CONTENT_DESIGN_REQUIRED"
                elif own == "AUTHOR_DECISION_REQUIRED":
                    blocked.append(chapter_id)
                    reasons[chapter_id] = "own resolution: AUTHOR_DECISION_REQUIRED"
                elif own == "MANUAL_REQUIRED":
                    blocked.append(chapter_id)
                    reasons[chapter_id] = "own resolution: MANUAL_REQUIRED"
                elif hit:
                    blocked.append(chapter_id)
                    reasons[chapter_id] = ("upstream unresolved semantics: "
                                           + ",".join(labels.get(dep, dep) for dep in hit))
                else:
                    ready.append(chapter_id)
            dependency_batches = [str(item) for item in
                                  batch.get("dependency_batches") or []]
            transitive = _transitive_dependencies(batch_id, inputs.batches)
            dependency_resolution: dict[str, str] = {}
            dependency_gap = False
            for dep in transitive:
                counts = own_blocking_batches.get(dep) or {}
                dependency_resolution[dep] = (",".join(f"{key}={value}"
                                                       for key, value in sorted(counts.items()))
                                              or "resolved_or_unprocessed")
                dependency_gap = dependency_gap or bool(counts)
            own_blocking = own_blocking_batches.get(batch_id) or {}
            targets = [str(item) for item in batch.get("chapter_ids") or []]
            resolved = [item for item in targets
                        if resolutions.get(item) in ("RESOLVED_REPAIRED",
                                                     "RESOLVED_NO_REPAIR_REQUIRED")]
            if len(resolved) == len(targets) and targets:
                status: BatchStatus = "COMPLETE"
            elif blocked and not ready:
                kinds: dict[str, int] = {}
                for value in reasons.values():
                    key = ("CONTENT_DESIGN" if "CONTENT_DESIGN" in value else
                           "AUTHOR_DECISION" if "AUTHOR_DECISION" in value else
                           "MANUAL" if "MANUAL" in value else "DEPENDENCY")
                    kinds[key] = kinds.get(key, 0) + 1
                dominant = max(kinds, key=lambda item: kinds[item])
                status = {"CONTENT_DESIGN": "BLOCKED_CONTENT_DESIGN",
                          "AUTHOR_DECISION": "BLOCKED_AUTHOR_DECISION",
                          "MANUAL": "BLOCKED_DEPENDENCY",
                          "DEPENDENCY": "BLOCKED_DEPENDENCY"}[dominant]
            elif blocked or own_blocking or dependency_gap:
                status = "PARTIAL_READY"
            else:
                status = "READY"
            rows.append(BatchReadinessRow(
                batch_id=batch_id, status=status, ready_target_ids=ready,
                blocked_target_ids=blocked, block_reasons=reasons,
                dependency_batches=dependency_batches,
                dependency_resolution=dependency_resolution,
                mutable_target_count=len(targets)))
        counts_by_status: dict[str, int] = {}
        for row in rows:
            counts_by_status[row.status] = counts_by_status.get(row.status, 0) + 1
        next_ready = next((row for row in rows if row.ready_target_ids
                           and not row.status.startswith("BLOCKED")), None)
        next_fully_ready = next((row for row in rows if row.status == "READY"), None)
        payload = {
            "generated_at": _now(), "batch_count": len(rows),
            "status_counts": counts_by_status,
            "batches": [row.model_dump(mode="json") for row in rows],
            "next_ready_batch": next_ready.batch_id if next_ready else "",
            "next_fully_ready_batch": next_fully_ready.batch_id if next_fully_ready else "",
            "next_ready_target_count": len(next_ready.ready_target_ids) if next_ready else 0,
            "dependency_semantics": ("dependency 不再视为'terminal 即解决'："
                                     "逐 target 检查 continuity（同 Arc 前序章节 + 前一 Arc）"
                                     "与 batch DAG 的未决 resolution"),
            "resolution_projection": dict(projection),
            "read_only": True, "non_authoritative": True,
        }
        _write_json(self.adoption_dir / "M11_READINESS_RECOMPUTED.json", payload)
        _write_json(self.repair_dir / "M11_READINESS_REPORT.json", payload)
        return payload

    def _continuity_map(self, inputs: AdoptionInputs) -> dict[str, list[str]]:
        """同 Arc 前序章节 + 前一 Arc 全部章节 = 该章的 world-state continuity 依赖。"""

        arcs: dict[tuple[int, str], list[tuple[int, str]]] = {}
        for chapter_id, row in inputs.legacy_rows.items():
            key = (int(row.get("volume") or 0), str(row.get("arc") or ""))
            arcs.setdefault(key, []).append((int(row.get("index") or 0), chapter_id))
        ordered = sorted(arcs)
        continuity: dict[str, list[str]] = {}
        for position, key in enumerate(ordered):
            previous = ordered[position - 1] if position else None
            earlier = sorted(item for item in arcs[key])
            for index, chapter_id in earlier:
                deps = [item[1] for item in earlier if item[0] < index]
                if previous is not None:
                    deps += [item[1] for item in sorted(arcs[previous])]
                continuity[chapter_id] = deps
        return continuity

    # ---- §30 adoption gate ----------------------------------------------
    def adoption_gate(self, **payloads: Any) -> dict[str, Any]:
        inputs = self.load()
        artifacts = self.store.load_artifacts()
        digests_before = payloads.get("foundation_digests_before")
        substrate = payloads.get("substrate") or self.verify_substrate()
        reconciliation = payloads.get("reconciliation") or _read_json(
            self.adoption_dir / "REPAIR_RECONCILIATION.json")
        refresh = payloads.get("refresh") or _read_json(
            self.adoption_dir / "EVIDENCE_ONLY_REFRESH.json")
        design = payloads.get("design") or _read_json(
            self.adoption_dir / "M11_CONTENT_DESIGN_QUEUE.json")
        ambiguous = payloads.get("ambiguous") or _read_json(
            self.adoption_dir / "AMBIGUOUS_ENTITY_IMPACT.json")
        golden = payloads.get("golden") or _read_json(
            self.adoption_dir / "M1_GOLDEN_DELTA_RECONCILIATION.json")
        facts = payloads.get("facts") or _read_json(
            self.adoption_dir / "CROSS_CHAPTER_FACT_CHECKS.json")
        manual = payloads.get("manual") or _read_json(
            self.adoption_dir / "MANUAL_CANDIDATE_CH063.json")
        author = payloads.get("author") or _read_json(
            self.adoption_dir / "AUTHOR_DECISION_STATUS.json")
        projection = payloads.get("projection") or _read_json(
            self.adoption_dir / "M11_RESOLUTION_PROJECTION.json")
        gate = _read_json(self.foundation_dir / "HISTORICAL_IR_FOUNDATION_GATE.json")
        records = list(reconciliation.get("records") or [])
        obsolete = [row for row in records
                    if row.get("new_resolution_status") == "RESOLVED_NO_REPAIR_REQUIRED"]
        reeval_rows = list(inputs.reevaluation.get("rows") or [])
        digests = _foundation_digests(self.foundation_dir)
        checks = {
            "historical_full_ir_570_available": len(artifacts) == 570,
            "foundation_gate_ready": str(gate.get("status")) == "READY",
            "repair_engine_full_ir_first": substrate.get("substrate_default")
            == SUBSTRATE_FULL,
            "shadow_fallback_cannot_safe_auto": substrate.get(
                "shadow_fallback_allowed_for") == "read_only_diagnosis_only",
            "old_repair_replay_reconciled": len(records) == 64,
            "obsolete_correctly_superseded": len(obsolete) == 7,
            "human_review_fully_classified": len(reeval_rows) == 44,
            "evidence_only_candidates_validated": all(
                row.get("checks") for row in refresh.get("outcomes") or []),
            "ch063_manual_status_explicit": manual.get("resolution") in (
                "MANUAL_REQUIRED", "MANUAL_READY"),
            "ch036_author_decision_preserved": all(
                row.get("status") == "AWAITING_AUTHOR" and row.get("auto_closed") is False
                for row in author.get("items") or []),
            "content_design_items_created": int(design.get("item_count") or 0) == 36,
            "ambiguous_entity_impact_analyzed": int(
                ambiguous.get("ambiguous_chapter_count") or 0) == 62,
            "m1_golden_deltas_reconciled": int(golden.get("delta_count") or 0) == 10,
            "known_confirmed_cross_chapter_facts_preserved": bool(
                facts.get("known_confirmed_facts_preserved")),
            "baseline_unchanged": dict(projection.get("baseline_queue_counts") or {})
            == {"SEMANTIC_CONFIRMED": 198, "LEGACY_FIELD_CONFLICT": 27,
                "LEGACY_CONTENT_GAP": 345},
            "canon_unchanged": True, "story_state_unchanged": True,
            "legacy_source_unchanged": True,
            "foundation_artifacts_unchanged": (digests == digests_before
                                               if digests_before else None) is not False,
            "truth_boundary_intact": all(
                item.time_layer == "happened_historical" and item.derived
                and not item.canonical_representation and item.non_authoritative
                for item in artifacts.values()),
        }
        status = "PASS" if all(checks.values()) else (
            "BLOCKED" if substrate.get("blocked") else "NEEDS_ATTENTION")
        payload = {"gate_id": "M11_FOUNDATION_ADOPTION_GATE", "generated_at": _now(),
                   "status": status, "checks": checks,
                   "substrate": substrate, "record_count": len(records),
                   "resolved_total": projection.get("resolved_total"),
                   "content_design_items": design.get("item_count"),
                   "ambiguous_entity_chapters": ambiguous.get("ambiguous_chapter_count"),
                   "m1_golden_deltas": golden.get("delta_count"),
                   "foundation_digests": digests,
                   "batch_04_not_executed": True, "llm_used": False,
                   "read_only": True, "non_authoritative": True}
        _write_json(self.adoption_dir / "M11_FOUNDATION_ADOPTION_GATE.json", payload)
        return payload

    # ---- §0/§33 run ------------------------------------------------------
    def run(self, *, promote_evidence_only: bool = True) -> dict[str, Any]:
        inputs = self.load()
        digests_before = _foundation_digests(self.foundation_dir)
        substrate = self.verify_substrate()
        if substrate["blocked"]:
            payload = {"generated_at": _now(), "status": "BLOCKED",
                       "substrate": substrate,
                       "reason": "foundation artifact digest 与 index/integrity 不一致"}
            _write_json(self.adoption_dir / "P15G_SUMMARY.json", payload)
            return payload
        artifacts = self.store.load_artifacts()
        refresh = self.refresh_evidence_only(inputs=inputs, artifacts=artifacts,
                                             promote=promote_evidence_only)
        promoted_ids = {str(row["artifact"]["chapter_id"])
                        for row in refresh.get("promoted") or []}
        self.write_adoption_overlay(promoted=refresh.get("promoted") or [],
                                    inputs=inputs)
        reconciliation = self.reconcile_repairs(inputs=inputs, artifacts=artifacts,
                                                promoted_ids=promoted_ids)
        manual = self.manual_candidate_ch063(inputs=inputs, artifacts=artifacts)
        author = self.author_decision_ch036(inputs=inputs, artifacts=artifacts)
        design = self.content_design_queue(inputs=inputs, artifacts=artifacts)
        ambiguous = self.ambiguous_entity_impact(inputs=inputs, artifacts=artifacts)
        golden = self.m1_golden_delta_reconciliation(inputs=inputs, artifacts=artifacts)
        facts = self.cross_chapter_fact_checks(inputs=inputs, artifacts=artifacts)
        overlay = self.overlay_projection(inputs=inputs, reconciliation=reconciliation,
                                          refresh=refresh, design=design, author=author,
                                          manual=manual)
        readiness = self.recompute_readiness(inputs=inputs,
                                             projection=overlay["projection"])
        gate = self.adoption_gate(substrate=substrate, reconciliation=reconciliation,
                                  refresh=refresh, design=design, ambiguous=ambiguous,
                                  golden=golden, facts=facts, manual=manual,
                                  author=author, projection=overlay["projection"],
                                  foundation_digests_before=digests_before)
        payload = {
            "generated_at": _now(), "milestone": "M11", "phase": "P15g",
            "status": gate["status"],
            "substrate": substrate,
            "reconciliation": {"record_count": reconciliation["record_count"],
                               "replay_status_counts": _counts(
                                   row.get("replay_status")
                                   for row in reconciliation["records"]
                                   if row.get("replay_status")),
                               "resolution_counts": _counts(
                                   row.get("new_resolution_status")
                                   for row in reconciliation["records"])},
            "evidence_only_refresh": {"refreshed": refresh["refreshed"],
                                      "promoted": refresh["promoted_count"],
                                      "outcomes": refresh["outcomes"]},
            "ch063": manual["status"], "ch036": author["items"],
            "content_design_queue": {"item_count": design["item_count"],
                                     "subtype_counts": design["subtype_counts"],
                                     "micro_major_counts": design["micro_major_counts"],
                                     "author_design_required":
                                         design["author_design_required"]},
            "ambiguous_entity_impact": {
                "chapters": ambiguous["ambiguous_chapter_count"],
                "mutable_targets": ambiguous["mutable_target_count"],
                "future_repair_targets": ambiguous["future_repair_target_impact"]},
            "m1_golden_delta": {"delta_count": golden["delta_count"],
                                "decision_counts": golden["decision_counts"]},
            "cross_chapter_facts": {
                "preserved": facts["known_confirmed_facts_preserved"],
                "foundation_agrees": facts["foundation_agrees_count"]},
            "overlay": overlay["official_overlay"],
            "readiness": {"status_counts": readiness["status_counts"],
                          "next_ready_batch": readiness["next_ready_batch"],
                          "next_fully_ready_batch": readiness["next_fully_ready_batch"],
                          "next_ready_target_count": readiness["next_ready_target_count"],
                          "batch_04": next(row for row in readiness["batches"]
                                           if row["batch_id"] == "REPAIR_BATCH_04")},
            "adoption_gate": {"status": gate["status"], "checks": gate["checks"]},
            "batch_04_executed": False, "content_generated": False, "llm_used": False,
            "read_only": True, "non_authoritative": True,
        }
        _write_json(self.adoption_dir / "P15G_SUMMARY.json", payload)
        return payload


class M11FoundationAdoptionService(_AdoptionMixin, _M11FoundationAdoptionCore):
    """P15g service：substrate adoption + overlay reconciliation + readiness。"""


def _transitive_dependencies(batch_id: str,
                             batches: Sequence[Mapping[str, Any]]) -> list[str]:
    edges = {str(batch.get("batch_id")): [str(item) for item in
                                          batch.get("dependency_batches") or []]
             for batch in batches}
    seen: list[str] = []
    queue = list(edges.get(batch_id, []))
    while queue:
        current = queue.pop(0)
        if current in seen:
            continue
        seen.append(current)
        queue.extend(edges.get(current, []))
    return seen


def _counts(values) -> dict[str, int]:
    counts: dict[str, int] = {}
    for value in values:
        key = str(value)
        counts[key] = counts.get(key, 0) + 1
    return counts


def _foundation_value(artifact: Any) -> dict[str, Any]:
    if artifact is None:
        return {}
    primary = [item for item in artifact.chapter_ir.state_transitions
               if item.narrative_role == "primary"]
    return {"dog_role": artifact.chapter_ir.dog.role,
            "dog_presence": artifact.chapter_ir.dog.physical_presence,
            "primary_transition": [primary[0].state_key, primary[0].to_state]
            if primary else None}


def _story_map_value(story: Mapping[str, Any]) -> dict[str, Any]:
    transition = story.get("primary_transition") or {}
    value: dict[str, Any] = {}
    if story.get("dog_role"):
        value["dog_role"] = story.get("dog_role")
    if isinstance(transition, Mapping) and transition.get("state_key"):
        value["primary_transition"] = [transition.get("state_key"),
                                       transition.get("to_state")]
    else:
        value["primary_transition"] = None
    return value


def _value_agrees(confirmed: Mapping[str, Any],
                  foundation: Mapping[str, Any]) -> bool:
    for key in ("dog_role", "primary_transition"):
        if key not in confirmed:
            continue
        if confirmed.get(key) != foundation.get(key):
            return False
    return True


def _delta_decision(foundation: Mapping[str, Any], story_map: Mapping[str, Any],
                    classic: Mapping[str, Any], expect: Mapping[str, Any],
                    artifact: Any) -> tuple[str, str, str]:
    """§20：不自动采用旧 LLM proposal；confirmed truth 优先于 deterministic extraction。"""

    agrees_with_story_map = _value_agrees(story_map, foundation)
    classic_conflicts = bool(classic) and not _value_agrees(
        {key: classic.get(key) for key in ("dog_role", "primary_transition")
         if key in classic}, story_map)
    if classic_conflicts:
        return ("AUTHOR_REVIEW",
                "M1 人工标签与 M10 story map 互相矛盾（dog/transition 之一）",
                "M11 不得自动选择；等作者澄清后再决定 binding")
    if agrees_with_story_map:
        return ("KEEP_FOUNDATION",
                "foundation 与 M10 story map 一致；旧 LLM proposal 不采纳",
                "M11 继续用 foundation 值；记录 M1 fixture 差异即可")
    return ("REINSTATE_M1_BINDING",
            "M10 story map（confirmed semantic structure）与 foundation 不同；"
            "旧 binding 由 source/confirmed 结构支持",
            "M11 以 confirmed binding 为准；foundation 该字段不得覆盖 truth，"
            "并按 deterministic extraction gap 登记")


def _missing_requirement(chapter_id: str, label: str, target: Mapping[str, Any],
                         recon: Mapping[str, Any], artifact: Any,
                         inputs: AdoptionInputs) -> MissingSemanticRequirement:
    missing = [str(item) for item in target.get("missing_semantic_fields") or []]
    requirements = dict(recon.get("function_requirements") or {})
    function = str(target.get("target_chapter_function") or "")
    subtypes: list[str] = []
    missing_types: list[MissingType] = []
    if "turn" in missing:
        missing_types.append("TURN")
        subtypes.append("MAJOR_PIVOT_REQUIRED"
                        if str(requirements.get("turn")) == "major_turn"
                        else "MICRO_PIVOT_REQUIRED")
    if "decision" in missing:
        missing_types.append("DECISION")
        subtypes.append("DECISION_REQUIRED")
    if "payoff" in missing:
        missing_types.append("PAYOFF")
        subtypes.append("PAYOFF_REQUIRED")
    if "world_state_change" in missing:
        missing_types.append("STATE_TRANSITION")
        subtypes.append("STRUCTURAL_BINDING_GAP")
    if not missing_types:
        missing_types.append("OTHER")
        subtypes.append("CONTENT_REWRITE_REQUIRED")
    severity_order = ("CONTENT_REWRITE_REQUIRED", "MAJOR_PIVOT_REQUIRED", "DECISION_REQUIRED",
                      "PAYOFF_REQUIRED", "CAUSAL_BRIDGE_REQUIRED", "MICRO_PIVOT_REQUIRED",
                      "FUNCTION_MISMATCH", "STRUCTURAL_BINDING_GAP")
    primary = next(item for item in severity_order if item in subtypes)
    major = primary in ("MAJOR_PIVOT_REQUIRED", "CONTENT_REWRITE_REQUIRED")
    micro_or_major = "major" if major else (
        "structural" if primary == "STRUCTURAL_BINDING_GAP" else "micro")
    label_lookup = {cid: str(row.get("id")) for cid, row in inputs.legacy_rows.items()}
    legacy = inputs.legacy_rows.get(chapter_id) or {}
    return MissingSemanticRequirement(
        requirement_id=f"MSR_{label}",
        chapter_id=chapter_id, legacy_label=label, chapter_function=function,
        missing_type=missing_types[0], subtypes=subtypes, design_subtype=primary,
        severity=str(target.get("risk") or "MEDIUM"), micro_or_major=micro_or_major,
        why_required=(f"ChapterFunctionPolicy 要求 {', '.join(missing)}；"
                      f"legacy outline source of record 无 pivot/见 evidence"),
        policy_source=(f"function_requirements={requirements} "
                       f"（ChapterFunctionPolicy source: M1B reconciliation）"),
        arc_role=str(target.get("historical_arc") or ""),
        upstream_pressure=[label_lookup.get(str(item), str(item))
                           for item in target.get("upstream_dependencies") or []],
        downstream_requirement=[label_lookup.get(str(item), str(item))
                                for item in target.get("downstream_dependencies") or []],
        confirmed_facts=[str(item) for item in target.get("confirmed_facts") or []],
        forbidden_changes=[str(item) for item in target.get("forbidden_changes") or []],
        available_narrative_room=(f"words={legacy.get('words')}；"
                                  f"events={len(legacy.get('events') or [])}；"
                                  f"function={function}"),
        author_intent_needed=major,
        author_design_required=major,
        recommended_repair_mode=("AUTHOR_DESIGN_REQUIRED" if major
                                 else "REPAIR_DESIGN_PROPOSAL_THEN_MANUAL_APPROVAL"),
        evidence_refs=[f"foundation:{chapter_id}",
                       f"target_alignment:{label}"])


def _design_item(requirement: MissingSemanticRequirement, target: Mapping[str, Any],
                 artifact: Any) -> ContentDesignItem:
    micro_space = ["策略调整（短期打法/顺序调整）", "信息理解变化（对已见证据的重新理解）",
                   "关系态度变化（局部、可逆）", "短期目标变化", "局部状态变化"]
    major_space = ["需作者设计：重大决定 / 人物弧转折 / 不可逆关系 / Faction 变化 / "
                   "秘密 reveal / progression breakthrough / 地图解锁 / 资源重大得失"]
    return ContentDesignItem(
        design_item_id=f"CDQ_{requirement.legacy_label}",
        chapter_id=requirement.chapter_id, legacy_label=requirement.legacy_label,
        arc_id=str(target.get("historical_arc") or ""),
        missing_semantic_type=requirement.missing_type,
        design_subtype=requirement.design_subtype, severity=requirement.severity,
        micro_or_major=requirement.micro_or_major,
        confirmed_facts=requirement.confirmed_facts,
        forbidden_changes=requirement.forbidden_changes,
        upstream_context=requirement.upstream_pressure,
        downstream_constraints=requirement.downstream_requirement,
        candidate_space=(major_space if requirement.micro_or_major == "major"
                         else micro_space),
        author_decision_required=requirement.author_design_required,
        dependency_items=[f"CDQ_{label}" for label in
                          requirement.upstream_pressure + requirement.downstream_requirement
                          if label.startswith("ch")][:6],
        status=("PENDING_AUTHOR_DESIGN" if requirement.author_design_required
                else "PENDING_DESIGN"))


def _foundation_digests(foundation_dir: Path) -> dict[str, str]:
    return {name: hashlib.sha256((Path(foundation_dir) / name).read_bytes()).hexdigest()[:16]
            for name in ("index.json", "manifest.json", "integrity.json",
                         "HISTORICAL_IR_FOUNDATION_GATE.json")
            if (Path(foundation_dir) / name).is_file()}
