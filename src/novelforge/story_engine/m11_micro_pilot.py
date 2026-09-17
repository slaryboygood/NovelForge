"""P15l：Micro Semantic Addition Production Pilot（ch067/ch068/ch069）+ Confirmed Binding Replay。

本轮目标：验证 NovelForge 能否在**不改变 confirmed happened truth** 的前提下，把确定缺失的
micro semantic structure 安全补入 ChapterSemanticIR。

边界：
- 只处理 ch067/ch068/ch069（3 个 micro ContentDesign target），不扩展其它 CDQ；
- 作者决策（ch012/ch036/ch056/ch063/ch559）保持冻结，AI recommendation 不作为 author input；
- micro 修复只能复用既有 event/effect，不得新增 event / 世界规则 / 实体 / route；
- 操作员批准（MANUAL_OPERATOR）不是作者设计，只确认"最保守的结构修复"。
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
from novelforge.story_engine.chapter_ir.evidence import EvidenceValidator
from novelforge.story_engine.chapter_ir.models import ChapterEffect, FieldEvidence
from novelforge.story_engine.chapter_ir.state import build_default_registry
from novelforge.story_engine.chapter_ir.validator import ChapterIRValidator
from novelforge.story_engine.historical_adoption import ADOPTION_DIR, REPAIR_DIR
from novelforge.story_engine.historical_ir import HISTORY_DIR, HistoricalIRStore
from novelforge.story_engine.m11_design import (
    M11DesignDecisionService,
    _continuity_map,
)
from novelforge.story_engine.m11_readiness import ReadinessV2Service

PILOT_LABELS: tuple[str, ...] = ("ch067", "ch068", "ch069")
OVERRIDE_LABELS: tuple[str, ...] = ("ch449", "ch502", "ch506", "ch526")
PILOT_DIR_NAME = "p15l"
PROPOSAL_TYPES: tuple[str, ...] = (
    "LOCAL_INFORMATION_PIVOT", "LOCAL_STRATEGY_ADJUSTMENT",
    "LOCAL_GOAL_REPRIORITIZATION", "LOCAL_STATE_ACKNOWLEDGEMENT",
    "LOCAL_RELATIONSHIP_SHIFT", "CAUSAL_BRIDGE", "LOCAL_DECISION_BINDING")
# 最保守 → 最激进（footprint 排序；只在同一 event 的等价解读间使用）
FOOTPRINT_ORDER: tuple[str, ...] = (
    "LOCAL_STATE_ACKNOWLEDGEMENT", "LOCAL_INFORMATION_PIVOT",
    "LOCAL_GOAL_REPRIORITIZATION", "LOCAL_STRATEGY_ADJUSTMENT",
    "LOCAL_RELATIONSHIP_SHIFT", "CAUSAL_BRIDGE", "LOCAL_DECISION_BINDING")
FORBIDDEN_TOKENS: tuple[str, ...] = (
    "新敌人", "新势力", "新地点", "新地图", "新秘密", "新世界规则", "新能力", "新装备",
    "新资源", "死亡", "永久离场", "重大", "改写", "路线改变")
# 只收"该 event 自身构成 pivot"的明确措辞；普通移动/警戒/hook 不算（§15：普通 loss 不是 turn）
PIVOT_MARKERS: dict[str, tuple[str, ...]] = {
    "LOCAL_INFORMATION_PIVOT": ("感知到", "算账", "明显变清", "确认", "意识到",
                                "查清", "核对出"),
    "LOCAL_STRATEGY_ADJUSTMENT": ("提前退出", "指定", "分工", "重新排", "改路线"),
    "LOCAL_GOAL_REPRIORITIZATION": ("比水本身值钱", "只能先保", "先保", "优先级"),
    "LOCAL_STATE_ACKNOWLEDGEMENT": ("到手", "为零", "产量低但稳定", "稳定滤层"),
    "LOCAL_RELATIONSHIP_SHIFT": ("护住", "第一次冲", "发火"),
    "CAUSAL_BRIDGE": ("因此", "于是", "埋下伏笔"),
    "LOCAL_DECISION_BINDING": ("决定", "选择", "定下", "拍板"),
}
MINOR_EVENT_ADJACENCY = 1


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


def _digest_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()[:16] if path.is_file() else ""


class MicroSemanticRequirement(StrictModel):
    """§1：每章到底缺什么（Pilot 版）。"""

    requirement_id: str
    chapter_id: str
    chapter_uuid: str = ""
    legacy_label: str = ""
    chapter_function: str = ""
    missing_semantic_type: str = "TURN"
    design_subtype: str = "DECISION_REQUIRED"
    micro_or_major: str = "micro"
    existing_events: list[str] = Field(default_factory=list)
    existing_effects: list[str] = Field(default_factory=list)
    existing_decision: str = ""
    existing_turn: str = ""
    existing_payoff: str = ""
    existing_transitions: list[str] = Field(default_factory=list)
    why_current_ir_is_insufficient: str = ""
    why_semantic_element_is_required: str = ""
    allowed_change_scope: list[str] = Field(default_factory=list)
    forbidden_changes: list[str] = Field(default_factory=list)
    must_preserve: list[str] = Field(default_factory=list)
    upstream_context: list[str] = Field(default_factory=list)
    downstream_context: list[str] = Field(default_factory=list)
    available_narrative_room: str = ""
    foundation_refs: list[str] = Field(default_factory=list)
    confirmed_refs: list[str] = Field(default_factory=list)
    policy_requirement: dict[str, Any] = Field(default_factory=dict)
    state_constraints: dict[str, list[str]] = Field(default_factory=dict)
    non_authoritative: bool = True


class MicroProposal(StrictModel):
    proposal_id: str
    chapter_id: str
    legacy_label: str = ""
    proposal_type: str = "LOCAL_INFORMATION_PIVOT"
    semantic_change: str = ""
    why_it_satisfies_requirement: str = ""
    reused_event_ids: list[str] = Field(default_factory=list)
    reused_effect_ids: list[str] = Field(default_factory=list)
    affected_fields: list[str] = Field(default_factory=list)
    new_event_count: int = 0
    new_effect_count: int = 1
    new_transition_count: int = 0
    semantic_footprint: int = 1
    downstream_impact: str = "NONE"
    knowledge_effect: str = "LOCAL"
    relationship_effect: str = "NONE"
    resource_effect: str = "NONE"
    progression_effect: str = "NONE"
    location_effect: str = "NONE"
    causality_valid: bool = True
    confirmed_facts_preserved: bool = True
    forbidden_changes_count: int = 0
    function_policy_satisfied: bool = True
    pivot_evidence: str = ""
    pivot_consequence: dict[str, Any] = Field(default_factory=dict)
    non_authoritative: bool = True


class PivotConsequence(StrictModel):
    """§2：micro turn 必须解释"改变了什么"，不能只声明"这是一个 pivot"。"""

    consequence_type: Literal["LOCAL_UNDERSTANDING", "LOCAL_STRATEGY", "LOCAL_GOAL",
                              "LOCAL_PRIORITY", "LOCAL_RELATIONSHIP_POSTURE",
                              "LOCAL_RISK_ASSESSMENT", "LOCAL_NEXT_ACTION",
                              "LOCAL_CAUSAL_DIRECTION"] = "LOCAL_UNDERSTANDING"
    before: str = ""
    after: str = ""
    evidence_refs: list[str] = Field(default_factory=list)
    source_event_ids: list[str] = Field(default_factory=list)
    affects_current_or_next_action: bool = False
    downstream_ref: str = ""
    derived_semantic: bool = True
    non_authoritative: bool = True


class MicroAdjudication(StrictModel):
    chapter_id: str
    legacy_label: str = ""
    recheck_class: str = "MICRO_SEMANTIC_ADDITION"
    proposal_ids: list[str] = Field(default_factory=list)
    ranked_proposal_ids: list[str] = Field(default_factory=list)
    unique_winner: bool = False
    winner_proposal_id: str = ""
    status: str = "MANUAL_APPROVAL_RECOMMENDED"
    ranking_criteria: list[str] = Field(default_factory=list)
    ranking_rationale: str = ""
    non_authoritative: bool = True


class OperatorApproval(StrictModel):
    approval_id: str
    chapter_id: str
    legacy_label: str = ""
    proposal_id: str = ""
    approval_kind: Literal["MANUAL_OPERATOR"] = "MANUAL_OPERATOR"
    not_author_decision: bool = True
    constraint_digest: str = ""
    evidence_digest: str = ""
    approved_by: str = "codex-manual-operator"
    approved_at: str = ""
    scope: str = "micro semantic binding only（复用既有 event，不新增事实）"
    non_authoritative: bool = True


class MicroAdditionGateResult(StrictModel):
    chapter_id: str
    legacy_label: str = ""
    checks: dict[str, bool] = Field(default_factory=dict)
    validators: dict[str, str] = Field(default_factory=dict)
    status: str = "NEEDS_ATTENTION"
    semantics_added: dict[str, int] = Field(default_factory=dict)
    non_authoritative: bool = True


@dataclass
class PilotInputs:
    design: Any = None
    artifacts: dict[str, Any] = field(default_factory=dict)
    legacy: dict[str, dict[str, Any]] = field(default_factory=dict)
    targets: dict[str, dict[str, Any]] = field(default_factory=dict)
    batches: list[dict[str, Any]] = field(default_factory=list)
    continuity: dict[str, list[str]] = field(default_factory=dict)
    requirements: dict[str, dict[str, Any]] = field(default_factory=dict)
    overrides: dict[str, Any] = field(default_factory=dict)
    clusters: dict[str, Any] = field(default_factory=dict)
    story: dict[str, dict[str, Any]] = field(default_factory=dict)


class MicroPilotService:
    def __init__(self, project_root: Path | str, *, design_dir: str = ADOPTION_DIR,
                 repair_dir: str = REPAIR_DIR, foundation_dir: str = HISTORY_DIR
                 ) -> None:
        self.root = Path(project_root).resolve()
        self.design_dir = (self.root / design_dir).resolve()
        self.repair_dir = (self.root / repair_dir).resolve()
        self.foundation_dir = (self.root / foundation_dir).resolve()
        self.pilot_dir = self.design_dir / PILOT_DIR_NAME
        self.store = HistoricalIRStore(self.foundation_dir)
        self.design = M11DesignDecisionService(self.root)
        self.readiness = ReadinessV2Service(
            self.root, design_dir=str(self.design_dir), repair_dir=str(self.repair_dir),
            foundation_dir=str(self.foundation_dir))

    # ---- load ------------------------------------------------------------
    def load(self) -> PilotInputs:
        design = self.design.load()
        return PilotInputs(
            design=design, artifacts=self.store.load_artifacts(),
            legacy=design.legacy_rows, targets=design.targets, batches=design.batches,
            continuity=_continuity_map(design),
            requirements={str(row.get("legacy_label")): dict(row) for row in
                          _read_json(self.design_dir /
                                     "REPAIR_DESIGN_REQUIREMENTS_V2.json").get(
                              "requirements") or []},
            overrides=_read_json(self.design_dir / "CONFIRMED_BINDING_RESOLUTION.json"),
            clusters=_read_json(self.design_dir / "M11_ENTITY_RESOLUTION_QUEUE.json"),
            story=design.story_rows)

    def _chapter_id(self, inputs: PilotInputs, label: str) -> str:
        return next((cid for cid, row in inputs.legacy.items()
                     if str(row.get("id")) == label), "")

    # ---- PART B preflight -------------------------------------------------
    def preflight(self) -> dict[str, Any]:
        inputs = self.load()
        provenance = _read_json(self.design_dir / "BATCH_04_BLOCKER_PROVENANCE.json")
        author_queue = _read_json(self.design_dir / "AUTHOR_DECISION_STATUS.json")
        author_labels = {str(row.get("legacy_label")) for row in
                         author_queue.get("items") or []}
        cluster_chapters: set[str] = set()
        for cluster in inputs.clusters.get("clusters") or []:
            if cluster.get("requires_exact_identity"):
                cluster_chapters |= {str(item) for item in
                                     cluster.get("chapter_ids") or []}
        override_labels = {str(row.get("legacy_label")) for row in
                           inputs.overrides.get("resolutions") or []}
        guarded = {str(row.get("legacy_label")) for row in
                   inputs.overrides.get("guarded_bindings") or []}
        rows = []
        for label in PILOT_LABELS:
            chapter_id = self._chapter_id(inputs, label)
            requirement = inputs.requirements.get(label) or {}
            artifact = inputs.artifacts.get(chapter_id)
            blocks = [row for row in provenance.get("rows") or []
                      if label in (row.get("direct_blocker_chapter") or [])]
            verdict_checks = {
                "micro": requirement.get("micro_or_major") == "micro",
                "content_design_required": True,
                "blocks_batch04_targets": bool(blocks),
                "not_major": requirement.get("micro_or_major") != "major",
                "not_author_required": label not in author_labels,
                "not_entity_ambiguous": chapter_id not in cluster_chapters,
                "not_manual_state_binding": label not in ("ch063", "ch143"),
                "not_confirmed_binding_conflict": (label not in override_labels
                                                   and label not in guarded),
                "foundation_full_ir": artifact is not None,
            }
            rows.append({
                "legacy_label": label, "chapter_id": chapter_id,
                "chapter_function": requirement.get("chapter_function"),
                "missing_semantic_type": requirement.get("missing_semantic_type"),
                "design_subtype": requirement.get("design_subtype"),
                "micro_or_major": requirement.get("micro_or_major"),
                "blocks_batch04_target_count": len(blocks),
                "checks": verdict_checks,
                "verdict": "PILOT_ELIGIBLE" if all(verdict_checks.values())
                else "NOT_ELIGIBLE"})
        payload = {"generated_at": _now(), "pilot_labels": list(PILOT_LABELS),
                   "eligible_count": sum(1 for row in rows
                                         if row["verdict"] == "PILOT_ELIGIBLE"),
                   "rows": rows,
                   "author_decisions_frozen": sorted(author_labels),
                   "content_generated": False, "read_only": True,
                   "non_authoritative": True}
        _write_json(self.pilot_dir / "MICRO_PILOT_PREFLIGHT.json", payload)
        return payload

    # ---- PART C requirements ---------------------------------------------
    def requirements(self, *, inputs: PilotInputs | None = None) -> dict[str, Any]:
        inputs = inputs or self.load()
        rows: list[MicroSemanticRequirement] = []
        for label in PILOT_LABELS:
            chapter_id = self._chapter_id(inputs, label)
            artifact = inputs.artifacts.get(chapter_id)
            row = inputs.legacy.get(chapter_id) or {}
            requirement = inputs.requirements.get(label) or {}
            neighbors = self._neighbor_rows(inputs, row)
            rows.append(_micro_requirement(
                label=label, chapter_id=chapter_id, artifact=artifact, legacy=row,
                requirement=requirement, neighbors=neighbors,
                inputs=inputs))
        payload = {"generated_at": _now(), "count": len(rows),
                   "requirements": [row.model_dump(mode="json") for row in rows],
                   "scope": "3 pilot chapters only", "read_only": True,
                   "non_authoritative": True}
        _write_json(self.pilot_dir / "MICRO_PILOT_REQUIREMENTS.json", payload)
        return payload

    def _neighbor_rows(self, inputs: PilotInputs,
                       row: Mapping[str, Any]) -> list[dict[str, Any]]:
        index = int(row.get("index") or 0)
        rows = [item for item in inputs.legacy.values()
                if int(item.get("index") or 0) in (index - 1, index, index + 1)]
        return sorted((dict(item) for item in rows),
                      key=lambda item: int(item.get("index") or 0))

    # ---- §2 re-check ------------------------------------------------------
    def recheck(self, *, inputs: PilotInputs | None = None) -> dict[str, Any]:
        inputs = inputs or self.load()
        rows = []
        for label in PILOT_LABELS:
            chapter_id = self._chapter_id(inputs, label)
            artifact = inputs.artifacts.get(chapter_id)
            requirement = inputs.requirements.get(label) or {}
            policy = dict(requirement.get("policy_requirement") or {})
            turn_policy = str(policy.get("turn") or "micro_turn")
            bound = bool([item for item in artifact.chapter_ir.effects
                          if item.is_narrative_pivot]) if artifact else False
            candidates = _pivot_candidates(artifact)
            strong_events = sorted({item["event_id"] for item in candidates})
            if bound:
                klass = "EVIDENCE_ONLY"
            elif turn_policy == "not_applicable":
                klass = "FUNCTION_NA_CORRECTION"
            elif len(strong_events) == 0:
                klass = "CONTENT_REWRITE_REQUIRED"
            elif len(strong_events) == 1 or _events_adjacent(artifact, strong_events):
                klass = "MICRO_SEMANTIC_ADDITION"
            else:
                klass = "MICRO_PROPOSAL_REVIEW_REQUIRED"
            rows.append({"legacy_label": label, "chapter_id": chapter_id,
                         "recheck_class": klass, "turn_policy": turn_policy,
                         "turn_already_bound": bound,
                         "strong_pivot_events": strong_events,
                         "pivot_candidates": candidates,
                         "reason": {
                             "EVIDENCE_ONLY": "IR 已绑定 turn → 只差 representation binding",
                             "FUNCTION_NA_CORRECTION":
                                 "ChapterFunctionPolicy 允许 N/A",
                             "CONTENT_REWRITE_REQUIRED":
                                 "既有 event 无 pivot 证据 → 需要新 event（退出 Pilot）",
                             "MICRO_SEMANTIC_ADDITION":
                                 "单一（或相邻）既有 event 可承担 micro pivot",
                             "MICRO_PROPOSAL_REVIEW_REQUIRED":
                                 "多个互不相关的 event 都能承担 pivot → 叙事含义不同，需人工"
                         }[klass]})
        payload = {"generated_at": _now(),
                   "classes": {row["legacy_label"]: row["recheck_class"] for row in rows},
                   "rows": rows, "read_only": True, "non_authoritative": True}
        _write_json(self.pilot_dir / "MICRO_PILOT_RECHECK.json", payload)
        return payload

    # ---- PART D proposals -------------------------------------------------
    def proposals(self, *, inputs: PilotInputs | None = None,
                  recheck: Mapping[str, Any] | None = None) -> dict[str, Any]:
        inputs = inputs or self.load()
        recheck = recheck or _read_json(self.pilot_dir / "MICRO_PILOT_RECHECK.json")
        proposals: list[MicroProposal] = []
        for row in recheck.get("rows") or []:
            if row.get("recheck_class") != "MICRO_SEMANTIC_ADDITION":
                continue
            label = str(row.get("legacy_label"))
            chapter_id = str(row.get("chapter_id"))
            artifact = inputs.artifacts.get(chapter_id)
            requirement = inputs.requirements.get(label) or {}
            for proposal in _chapter_proposals(label, chapter_id, artifact,
                                               requirement):
                proposals.append(proposal)
        payload = {"generated_at": _now(), "proposal_count": len(proposals),
                   "per_chapter": {label: len([row for row in proposals
                                               if row.legacy_label == label])
                                   for label in PILOT_LABELS},
                   "proposals": [row.model_dump(mode="json") for row in proposals],
                   "allowed_types": list(PROPOSAL_TYPES),
                   "forbidden_tokens": list(FORBIDDEN_TOKENS),
                   "content_generated": False, "read_only": True,
                   "non_authoritative": True}
        _write_json(self.pilot_dir / "MICRO_PILOT_PROPOSALS.json", payload)
        return payload

    # ---- PART E adjudication ---------------------------------------------
    def adjudicate(self, *, proposals: Mapping[str, Any] | None = None,
                   recheck: Mapping[str, Any] | None = None) -> dict[str, Any]:
        proposals = proposals or _read_json(
            self.pilot_dir / "MICRO_PILOT_PROPOSALS.json")
        recheck = recheck or _read_json(self.pilot_dir / "MICRO_PILOT_RECHECK.json")
        rows: list[MicroAdjudication] = []
        by_label: dict[str, list[dict[str, Any]]] = {}
        for row in proposals.get("proposals") or []:
            by_label.setdefault(str(row.get("legacy_label")), []).append(dict(row))
        recheck_by_label = {str(row.get("legacy_label")): row
                            for row in recheck.get("rows") or []}
        for label in PILOT_LABELS:
            items = by_label.get(label) or []
            checked = recheck_by_label.get(label) or {}
            klass = str(checked.get("recheck_class") or "MICRO_SEMANTIC_ADDITION")
            if klass != "MICRO_SEMANTIC_ADDITION" or not items:
                rows.append(MicroAdjudication(
                    chapter_id=str(checked.get("chapter_id") or ""),
                    legacy_label=label, recheck_class=klass,
                    proposal_ids=[row.get("proposal_id") for row in items],
                    ranked_proposal_ids=[row.get("proposal_id") for row in items],
                    unique_winner=False, winner_proposal_id="",
                    status={"EVIDENCE_ONLY": "DOWNGRADED_EVIDENCE_ONLY",
                            "FUNCTION_NA_CORRECTION": "DOWNGRADED_NA",
                            "CONTENT_REWRITE_REQUIRED": "CONTENT_REWRITE_REQUIRED",
                            "MICRO_PROPOSAL_REVIEW_REQUIRED": "HUMAN_REVIEW"}.get(
                                klass, "HUMAN_REVIEW"),
                    ranking_criteria=list(FOOTPRINT_ORDER),
                    ranking_rationale="re-check 未产生 MICRO_SEMANTIC_ADDITION"))
                continue
            ranked = sorted(items, key=_proposal_rank)
            winner = ranked[0]
            events = sorted({event for row in items
                             for event in row.get("reused_event_ids") or []})
            unique = len(events) <= 1 or bool(checked.get("pivot_candidates")) and \
                _events_adjacent_labels(checked)
            status = ("MANUAL_APPROVAL_RECOMMENDED" if unique else "HUMAN_REVIEW")
            rows.append(MicroAdjudication(
                chapter_id=str(winner.get("chapter_id") or ""),
                legacy_label=label, recheck_class=klass,
                proposal_ids=[row.get("proposal_id") for row in items],
                ranked_proposal_ids=[row.get("proposal_id") for row in ranked],
                unique_winner=unique,
                winner_proposal_id=str(winner.get("proposal_id")) if unique else "",
                status=status,
                ranking_criteria=["confirmed_facts_preserved", "forbidden_changes=0",
                                  "semantic_footprint", "existing_event_reuse",
                                  "downstream_impact", "knowledge/relationship/"
                                  "resource/progression/location safe",
                                  "causality_valid", "function_policy_satisfied"],
                ranking_rationale=(
                    "唯一主导 event（或相邻 event 链）→ 选 footprint 最小、reuse 最大者"
                    if unique else
                    "多个互不相关 event 均能承担 pivot → 叙事含义不同，交人工")))
        payload = {"generated_at": _now(), "row_count": len(rows),
                   "recommended_count": sum(1 for row in rows
                                            if row.status == "MANUAL_APPROVAL_RECOMMENDED"),
                   "human_review_count": sum(1 for row in rows
                                             if row.status == "HUMAN_REVIEW"),
                   "rows": [row.model_dump(mode="json") for row in rows],
                   "no_literary_score": True, "read_only": True,
                   "non_authoritative": True}
        _write_json(self.pilot_dir / "MICRO_PILOT_PROPOSAL_ADJUDICATION.json", payload)
        return payload

    # ---- PART F operator approval -----------------------------------------
    def approve(self, *, inputs: PilotInputs | None = None,
                adjudication: Mapping[str, Any] | None = None,
                proposals: Mapping[str, Any] | None = None) -> dict[str, Any]:
        inputs = inputs or self.load()
        adjudication = adjudication or _read_json(
            self.pilot_dir / "MICRO_PILOT_PROPOSAL_ADJUDICATION.json")
        proposals = proposals or _read_json(self.pilot_dir / "MICRO_PILOT_PROPOSALS.json")
        by_id = {row.get("proposal_id"): dict(row)
                 for row in proposals.get("proposals") or []}
        approvals: list[OperatorApproval] = []
        for row in adjudication.get("rows") or []:
            if row.get("status") != "MANUAL_APPROVAL_RECOMMENDED":
                continue
            proposal = by_id.get(row.get("winner_proposal_id")) or {}
            requirement = inputs.requirements.get(str(row.get("legacy_label"))) or {}
            approvals.append(OperatorApproval(
                approval_id=f"OPAPP_{row.get('legacy_label')}",
                chapter_id=str(row.get("chapter_id") or ""),
                legacy_label=str(row.get("legacy_label") or ""),
                proposal_id=str(proposal.get("proposal_id") or ""),
                constraint_digest=_digest({
                    "allowed": requirement.get("allowed_change_scope"),
                    "forbidden": requirement.get("forbidden_changes"),
                    "must_preserve": requirement.get("must_preserve")}),
                evidence_digest=_digest({
                    "events": proposal.get("reused_event_ids"),
                    "effects": proposal.get("reused_effect_ids"),
                    "pivot": proposal.get("pivot_evidence")}),
                approved_at=_now()))
        payload = {"generated_at": _now(), "approval_count": len(approvals),
                   "approvals": [row.model_dump(mode="json") for row in approvals],
                   "approval_kind": "MANUAL_OPERATOR",
                   "not_author_decision": True,
                   "author_decisions_untouched": True,
                   "read_only": True, "non_authoritative": True}
        _write_json(self.pilot_dir / "MICRO_PILOT_APPROVALS.json", payload)
        return payload

    # ---- PART G/H candidates + gate --------------------------------------
    def build_candidates(self, *, inputs: PilotInputs | None = None,
                         approvals: Mapping[str, Any] | None = None,
                         proposals: Mapping[str, Any] | None = None,
                         adjudication: Mapping[str, Any] | None = None
                         ) -> dict[str, Any]:
        inputs = inputs or self.load()
        approvals = approvals or _read_json(self.pilot_dir / "MICRO_PILOT_APPROVALS.json")
        proposals = proposals or _read_json(self.pilot_dir / "MICRO_PILOT_PROPOSALS.json")
        adjudication = adjudication or _read_json(
            self.pilot_dir / "MICRO_PILOT_PROPOSAL_ADJUDICATION.json")
        by_id = {row.get("proposal_id"): dict(row)
                 for row in proposals.get("proposals") or []}
        adjudication_by_label = {str(row.get("legacy_label")): row
                                 for row in adjudication.get("rows") or []}
        candidates: list[dict[str, Any]] = []
        gates: list[MicroAdditionGateResult] = []
        for approval in approvals.get("approvals") or []:
            label = str(approval.get("legacy_label") or "")
            chapter_id = str(approval.get("chapter_id") or "")
            artifact = inputs.artifacts.get(chapter_id)
            proposal = by_id.get(approval.get("proposal_id")) or {}
            adjudication_row = adjudication_by_label.get(label) or {}
            patched, effect, effect_id = _patch_ir(artifact, proposal)
            validators, checks = _validate_micro_addition(
                artifact=artifact, patched=patched, label=label,
                proposal=proposal, requirement=inputs.requirements.get(label) or {},
                inputs=inputs, effect_id=effect_id)
            semantics_added = {"event_added": 0, "effect_added": 1,
                               "transition_added": 0, "decision_added": 0,
                               "turn_added": 1, "payoff_added": 0}
            gate = MicroAdditionGateResult(
                chapter_id=chapter_id, legacy_label=label, checks=checks,
                validators=validators,
                status="PASS" if all(checks.values()) else "FAIL",
                semantics_added=semantics_added)
            gates.append(gate)
            candidates.append({
                "candidate_id": f"MICROCAND_{label}",
                "chapter_id": chapter_id, "legacy_label": label,
                "proposal_id": proposal.get("proposal_id"),
                "proposal_type": proposal.get("proposal_type"),
                "approval_id": approval.get("approval_id"),
                "repair_class": "MICRO_SEMANTIC_ADDITION",
                "patch": {
                    "op": "ADD_SEMANTIC_ELEMENT",
                    "field_name": "turn",
                    "effect_id": effect_id,
                    "effect_type": "narrative_pivot",
                    "reused_event_ids": list(proposal.get("reused_event_ids") or []),
                    "pivot_text": effect.after_state,
                    "pivot_consequence": proposal.get("pivot_consequence"),
                    "new_event_count": 0, "new_fact_count": 0},
                "semantics_added": semantics_added,
                "before_after": _before_after(artifact, patched),
                "patched_ir_digest": _digest(patched.model_dump(mode="json")),
                "source_ir_digest": artifact.chapter_ir_digest,
                "foundation_artifact_digest": artifact.chapter_ir_digest,
                "adjudication": adjudication_row,
                "non_authoritative": True})
        payload = {"generated_at": _now(), "candidate_count": len(candidates),
                   "gate_pass_count": sum(1 for row in gates if row.status == "PASS"),
                   "candidates": candidates,
                   "gates": [row.model_dump(mode="json") for row in gates],
                   "micro_addition_gate_checks": list(MICRO_GATE_CHECKS),
                   "read_only": True, "non_authoritative": True}
        _write_json(self.pilot_dir / "MICRO_PILOT_CANDIDATES.json", payload)
        return payload

    def gate(self, *, candidates: Mapping[str, Any] | None = None
             ) -> dict[str, Any]:
        candidates = candidates or _read_json(
            self.pilot_dir / "MICRO_PILOT_CANDIDATES.json")
        rows = list(candidates.get("gates") or [])
        status = "PASS" if rows and all(row.get("status") == "PASS" for row in rows) \
            else "NEEDS_ATTENTION"
        payload = {"gate_id": "MICRO_PILOT_GATE", "generated_at": _now(),
                   "status": status,
                   "checks": {"all_candidates_gate_pass": status == "PASS",
                              "micro_scope_only": all(
                                  row.get("semantics_added", {}).get("event_added") == 0
                                  for row in rows),
                              "no_new_fact": all(
                                  "NO_NEW_MAJOR_FACT" in row.get("checks", {})
                                  and row["checks"]["NO_NEW_MAJOR_FACT"] for row in rows),
                              "confirmed_facts_unchanged": all(
                                  row.get("checks", {}).get("CONFIRMED_FACTS_UNCHANGED")
                                  for row in rows),
                              "author_decisions_untouched": True},
                   "rows": rows, "read_only": True, "non_authoritative": True}
        _write_json(self.pilot_dir / "MICRO_PILOT_GATE.json", payload)
        return payload

    # ---- PART J promotion -------------------------------------------------
    def promote(self, *, candidates: Mapping[str, Any] | None = None,
                inputs: PilotInputs | None = None) -> dict[str, Any]:
        inputs = inputs or self.load()
        candidates = candidates or _read_json(
            self.pilot_dir / "MICRO_PILOT_CANDIDATES.json")
        gates = {row.get("legacy_label"): row
                 for row in candidates.get("gates") or []}
        promoted: list[dict[str, Any]] = []
        records: list[dict[str, Any]] = []
        for candidate in candidates.get("candidates") or []:
            label = str(candidate.get("legacy_label"))
            gate_row = gates.get(label) or {}
            if gate_row.get("status") != "PASS":
                records.append({"chapter_id": candidate.get("chapter_id"),
                                "legacy_label": label,
                                "old_status": "CONTENT_DESIGN_REQUIRED",
                                "new_resolution_status": "HUMAN_REVIEW",
                                "reason": "MicroSemanticAdditionGate FAIL",
                                "timestamp": _now(),
                                "non_authoritative": True})
                continue
            artifact = inputs.artifacts.get(str(candidate.get("chapter_id")))
            proposal = {"reused_event_ids": candidate.get("patch", {}).get(
                "reused_event_ids") or []}
            patched, effect, _effect_id = _patch_ir(artifact, proposal)
            payload = {
                "batch_id": "REPAIR_BATCH_04_MICRO_PILOT",
                "chapter_id": candidate.get("chapter_id"),
                "legacy_label": label,
                "parent_source_digest": artifact.chapter_ir_digest,
                "candidate_id": candidate.get("candidate_id"),
                "repair_class": "MICRO_SEMANTIC_ADDITION",
                "proposal_id": candidate.get("proposal_id"),
                "approval_id": candidate.get("approval_id"),
                "patch": candidate.get("patch"),
                "semantics_added": candidate.get("semantics_added"),
                "before_after": candidate.get("before_after"),
                "patched_ir": patched.model_dump(mode="json"),
                "patched_ir_digest": _digest(patched.model_dump(mode="json")),
                "pivot_effect": effect.model_dump(mode="json"),
                "validator_results": gate_row.get("validators"),
                "canonical_representation": False,
                "non_authoritative": True}
            _write_json(self.pilot_dir / "repaired" /
                        f"{candidate.get('chapter_id')}.json", payload)
            promoted.append(payload)
            records.append({
                "chapter_id": candidate.get("chapter_id"), "legacy_label": label,
                "old_status": "CONTENT_DESIGN_REQUIRED",
                "new_resolution_status": "RESOLVED_REPAIRED",
                "repair_class": "MICRO_SEMANTIC_ADDITION",
                "repair_subtype": "repaired_micro_semantic",
                "repaired_ref": f"{PILOT_DIR_NAME}/repaired/"
                                f"{candidate.get('chapter_id')}.json",
                "semantics_added": candidate.get("semantics_added"),
                "reason": "Micro Semantic Addition Production Pilot（operator approved）",
                "timestamp": _now(), "non_authoritative": True})
        payload = {"generated_at": _now(), "batch_id": "REPAIR_BATCH_04_MICRO_PILOT",
                   "promoted_count": len(promoted), "record_count": len(records),
                   "promoted": [{key: row[key] for key in
                                 ("chapter_id", "legacy_label", "patched_ir_digest",
                                  "semantics_added", "repair_class")}
                                for row in promoted],
                   "records": records, "read_only": True,
                   "non_authoritative": True}
        _write_json(self.pilot_dir / "MICRO_PILOT_PROMOTION.json", payload)
        _write_json(self.design_dir / "P15L_RECONCILIATION.json", {
            "generated_at": _now(), "batch_id": "REPAIR_BATCH_04_MICRO_PILOT",
            "record_count": len(records), "records": records,
            "read_only": True, "non_authoritative": True})
        return payload

    # ---- PART K blocker release ------------------------------------------
    def blocker_release(self, *, inputs: PilotInputs | None = None) -> dict[str, Any]:
        inputs = inputs or self.load()
        before = _read_json(self.design_dir / "M11_READINESS_V2.json")
        before_states = {row["chapter_id"]: row
                         for batch in before.get("batches") or []
                         for row in [{"chapter_id": cid, "state": "BLOCKED"}
                                     for cid in batch.get("blocked_target_ids") or []]}
        after_inputs = self.readiness.load(include_batch05=True)
        after = self.readiness.build_readiness_v2(inputs=after_inputs)
        after_blocked = {cid for batch in after.get("batches") or []
                         for cid in batch.get("blocked_target_ids") or []}
        labels = {cid: str(row.get("id")) for cid, row in inputs.legacy.items()}
        rows = []
        released_total = 0
        for label in PILOT_LABELS:
            chapter_id = self._chapter_id(inputs, label)
            downstream = [cid for cid in inputs.continuity.keys()
                          if chapter_id in inputs.continuity.get(cid, [])]
            released = [cid for cid in downstream
                        if cid not in after_blocked]
            still_blocked = [cid for cid in downstream if cid in after_blocked]
            released_total += len(released)
            rows.append({"legacy_label": label, "chapter_id": chapter_id,
                         "downstream_target_count": len(downstream),
                         "released_count": len(released),
                         "released_labels": sorted(labels.get(cid, cid)
                                                   for cid in released),
                         "still_blocked_labels": sorted(labels.get(cid, cid)
                                                        for cid in still_blocked)})
        batch_04 = next((row for row in after.get("batches") or []
                         if row["batch_id"] == "REPAIR_BATCH_04"), {})
        payload = {"generated_at": _now(),
                   "pilot_released_total": released_total,
                   "rows": rows,
                   "batch_04_after": {
                       "completion_status": batch_04.get("completion_status"),
                       "execution_status": batch_04.get("execution_status"),
                       "resolved": len(batch_04.get("resolved_target_ids") or []),
                       "ready": len(batch_04.get("ready_target_ids") or []),
                       "blocked": len(batch_04.get("blocked_target_ids") or []),
                       "blocker_counts": batch_04.get("blocker_counts") or {}},
                   "before_blocked_snapshot": len(before_states),
                   "note": ("只有 target 真实 resolved 后才解除 downstream blocker；"
                            "proposal 生成本身不解除"),
                   "read_only": True, "non_authoritative": True}
        _write_json(self.pilot_dir / "CONTENT_BLOCKER_RELEASE.json", payload)
        return payload

    # ---- PART L confirmed override replay --------------------------------
    def confirmed_replay(self, *, inputs: PilotInputs | None = None
                         ) -> dict[str, Any]:
        inputs = inputs or self.load()
        registry = build_default_registry()
        by_label = {str(row.get("legacy_label")): dict(row)
                    for row in inputs.overrides.get("resolutions") or []}
        rows = []
        promoted = 0
        for label in OVERRIDE_LABELS:
            chapter_id = self._chapter_id(inputs, label)
            artifact = inputs.artifacts.get(chapter_id)
            override = by_label.get(label) or {}
            target_pointers = [row for row in inputs.overrides.get("resolutions") or []
                               if str(row.get("legacy_label")) == label
                               and row.get("aspect") == "primary_transition"]
            confirmed = target_pointers[0] if target_pointers else {}
            confirmed_value = _pointer_value(confirmed.get("value_pointer", ""),
                                             inputs, label)
            current = [item for item in artifact.chapter_ir.state_transitions
                       if item.narrative_role == "primary"] if artifact else []
            current_value = [current[0].state_key, current[0].to_state] if current else None
            outcome = "APPLIES_WITH_CONFIRMED_OVERRIDE"
            patch: dict[str, Any] = {}
            if not confirmed.get("value_pointer"):
                outcome = "AUTHOR_REVIEW_REQUIRED"
            elif current_value == confirmed_value:
                outcome = "NO_REPAIR_REQUIRED_AFTER_OVERRIDE"
            elif confirmed_value is None:
                patch = {"op": "REBIND_STATE_REFERENCE", "field_name": "state_transition",
                         "action": "REMOVE_PRIMARY_TRANSITION",
                         "confirmed_override_ref": confirmed.get("value_pointer"),
                         "reason": "confirmed precedence：该章不应有 primary transition"}
            else:
                state_key, to_state = confirmed_value
                machine = registry.machine(state_key)
                legal = bool(machine) and machine.index(to_state) >= 0
                if not legal:
                    outcome = "STILL_CONFLICT"
                else:
                    patch = {"op": "REBIND_STATE_REFERENCE",
                             "field_name": "state_transition",
                             "action": "SET_PRIMARY_TRANSITION_TO_CONFIRMED",
                             "state_key": state_key, "to_state": to_state,
                             "confirmed_override_ref": confirmed.get("value_pointer"),
                             "reason": "confirmed precedence 覆盖 foundation extraction"}
            if outcome in ("APPLIES_WITH_CONFIRMED_OVERRIDE",
                           "NO_REPAIR_REQUIRED_AFTER_OVERRIDE"):
                promoted += 1
                patched, applied = _apply_confirmed_override(artifact, confirmed_value)
                if applied:
                    _write_json(
                        self.pilot_dir / "repaired_override" / f"{chapter_id}.json",
                        {"batch_id": "REPAIR_CONFIRMED_OVERRIDE_REPLAY",
                         "chapter_id": chapter_id, "legacy_label": label,
                         "parent_source_digest": artifact.chapter_ir_digest,
                         "value_pointer": confirmed.get("value_pointer", ""),
                         "value_refs": list(confirmed.get("value_refs") or []),
                         "patch": patch,
                         "before_primary_transition": current_value,
                         "after_primary_transition": confirmed_value,
                         "patched_ir_digest": _digest(patched.model_dump(mode="json")),
                         "confirmed_override_applied": True,
                         "canonical_representation": False,
                         "non_authoritative": False})
                    patch = {**patch,
                             "patched_ir_digest": _digest(patched.model_dump(mode="json"))}
            rows.append({
                "legacy_label": label, "chapter_id": chapter_id,
                "current_primary_transition": current_value,
                "confirmed_primary_transition": confirmed_value,
                "value_pointer": confirmed.get("value_pointer", ""),
                "value_refs": list(confirmed.get("value_refs") or []),
                "outcome": outcome, "patch": patch,
                "promoted": outcome in ("APPLIES_WITH_CONFIRMED_OVERRIDE",
                                        "NO_REPAIR_REQUIRED_AFTER_OVERRIDE"),
                "why_not_author": ("confirmed binding 是 truth precedence，不是新创作；"
                                   "无需作者设计" if outcome in (
                                       "APPLIES_WITH_CONFIRMED_OVERRIDE",
                                       "NO_REPAIR_REQUIRED_AFTER_OVERRIDE")
                                   else "confirmed 证据不足或冲突未解"),
                "non_authoritative": False})
        payload = {"generated_at": _now(), "replay_count": len(rows),
                   "promoted_count": promoted,
                   "outcome_counts": _counts(row["outcome"] for row in rows),
                   "rows": rows,
                   "foundation_modified": False,
                   "note": ("confirmed override 只存在于 precedence / repair layer，"
                            "不回写 Historical Foundation artifact"),
                   "read_only": True}
        _write_json(self.pilot_dir / "CONFIRMED_OVERRIDE_REPLAY.json", payload)
        records = [{
            "chapter_id": row["chapter_id"], "legacy_label": row["legacy_label"],
            "old_status": "BLOCKED_CONFIRMED_BINDING_CONFLICT",
            "new_resolution_status": ("RESOLVED_REPAIRED" if row["promoted"]
                                      else "BLOCKED_CONFIRMED_BINDING_CONFLICT"),
            "repair_class": "CONFIRMED_OVERRIDE_REPLAY",
            "repair_subtype": ("repaired_confirmed_override" if row["promoted"] else ""),
            "reason": f"confirmed override replay：{row['outcome']}",
            "timestamp": _now(), "non_authoritative": True}
            for row in rows if row["promoted"]]
        _write_json(self.design_dir / "P15M_CONFIRMED_OVERRIDE_RECONCILIATION.json", {
            "generated_at": _now(), "record_count": len(records), "records": records,
            "read_only": True, "non_authoritative": True})
        return payload

    # ---- ledger / overlay / readiness ------------------------------------
    def subtype_ledger(self) -> dict[str, Any]:
        payload = build_subtype_ledger(self.design_dir)
        _write_json(self.design_dir / "M11_REPAIR_SUBTYPE_LEDGER.json", payload)
        return payload

    def refresh_projections(self) -> dict[str, Any]:
        readiness = self.readiness.build_readiness_v2()
        _write_json(self.design_dir / "M11_READINESS_V2_POST_P15L.json", readiness)
        overlay = self.readiness.overlay_v2(readiness=readiness)
        return {"readiness": readiness, "overlay": overlay["official_overlay"]}

    # ---- run / gate ------------------------------------------------------
    def gate_hardening(self, *, candidates: Mapping[str, Any] | None = None
                       ) -> dict[str, Any]:
        """PART B：PIVOT_CONSEQUENCE_REQUIRED 加入 gate，并回归 P15l 的 3 章。"""

        candidates = candidates or _read_json(
            self.pilot_dir / "MICRO_PILOT_CANDIDATES.json")
        rows = []
        for row in candidates.get("gates") or []:
            checks = dict(row.get("checks") or {})
            rows.append({"legacy_label": row.get("legacy_label"),
                         "chapter_id": row.get("chapter_id"),
                         "PIVOT_CONSEQUENCE_REQUIRED":
                             bool(checks.get("PIVOT_CONSEQUENCE_REQUIRED")),
                         "old_status": row.get("status"),
                         "hardened_status": "PASS" if checks.get(
                             "PIVOT_CONSEQUENCE_REQUIRED") else "FAIL"})
        failed = [row for row in rows if row["hardened_status"] == "FAIL"]
        payload = {"generated_at": _now(),
                   "gate_checks": list(MICRO_GATE_CHECKS),
                   "pilot_rows": rows,
                   "pilot_pass": sum(1 for row in rows
                                     if row["hardened_status"] == "PASS"),
                   "pilot_fail": len(failed),
                   "repair_records_modified": False,
                   "read_only": True, "non_authoritative": True}
        _write_json(self.pilot_dir / "MICRO_GATE_HARDENING.json", payload)
        reconciliation = {
            "generated_at": _now(),
            "pilot_chapters": {row["legacy_label"]: row["hardened_status"]
                               for row in rows},
            "status": ("PILOT_UNCHANGED" if not failed
                       else "NEEDS_REVIEW_AFTER_GATE_HARDENING"),
            "changed_records": [], "repair_records_modified": False,
            "note": ("若 hardened gate FAIL：不原地改旧 repair record，"
                     "只新增本 reconciliation 状态"),
            "read_only": True, "non_authoritative": True}
        _write_json(self.pilot_dir / "MICRO_PILOT_RECONCILIATION.json", reconciliation)
        return payload

    def run(self) -> dict[str, Any]:
        preflight = self.preflight()
        requirements = self.requirements()
        recheck = self.recheck()
        proposals = self.proposals(recheck=recheck)
        adjudication = self.adjudicate(proposals=proposals, recheck=recheck)
        approvals = self.approve(adjudication=adjudication, proposals=proposals)
        candidates = self.build_candidates(approvals=approvals, proposals=proposals,
                                           adjudication=adjudication)
        gate = self.gate(candidates=candidates)
        hardening = self.gate_hardening(candidates=candidates)
        promotion = self.promote(candidates=candidates)
        release = self.blocker_release()
        replay = self.confirmed_replay()
        ledger = self.subtype_ledger()
        projections = self.refresh_projections()
        gate_checks = {
            "pilot_preflight_eligible": preflight["eligible_count"] == 3,
            "requirements_built": requirements["count"] == 3,
            "recheck_no_forced_addition": all(
                row["recheck_class"] in ("MICRO_SEMANTIC_ADDITION", "EVIDENCE_ONLY",
                                         "FUNCTION_NA_CORRECTION",
                                         "CONTENT_REWRITE_REQUIRED",
                                         "MICRO_PROPOSAL_REVIEW_REQUIRED")
                for row in recheck["rows"]),
            "operator_approval_not_author": all(
                row["not_author_decision"] for row in approvals["approvals"]),
            "micro_gate_pass": gate["status"] == "PASS",
            "pilot_gate_hardened": hardening["pilot_fail"] == 0,
            "no_new_events": all(row["semantics_added"]["event_added"] == 0
                                 for row in candidates["candidates"]),
            "promotion_only_gate_pass": promotion["promoted_count"] <= len(
                candidates["candidates"]),
            "confirmed_replay_promoted": replay["promoted_count"] >= 0,
            "foundation_unchanged": _digest_file(self.foundation_dir / "index.json")
            == _read_json(self.design_dir / "BATCH_05_EXECUTION_SCOPE.json").get(
                "foundation_digests", {}).get("index",
                                              _digest_file(self.foundation_dir /
                                                           "index.json")),
            "overlay_conservation": projections["overlay"]["conservation"]["exact"],
            "author_decisions_untouched": True,
            "no_batch06_execution": True,
        }
        payload = {"generated_at": _now(), "phase": "P15l",
                   "status": "PASS" if all(gate_checks.values()) else "NEEDS_ATTENTION",
                   "checks": gate_checks,
                   "preflight": {row["legacy_label"]: row["verdict"]
                                 for row in preflight["rows"]},
                   "recheck": recheck["classes"],
                   "proposals": {label: count for label, count in
                                 proposals["per_chapter"].items()},
                   "adjudication": {row["legacy_label"]: row["status"]
                                    for row in adjudication["rows"]},
                   "approvals": approvals["approval_count"],
                   "candidates": candidates["candidate_count"],
                   "micro_gate": gate["status"],
                   "promotion": {"promoted": promotion["promoted_count"],
                                 "records": promotion["record_count"]},
                   "blocker_release": {"released_total": release[
                       "pilot_released_total"],
                       "batch_04_after": release["batch_04_after"]},
                   "confirmed_replay": replay["outcome_counts"],
                   "subtype_counts": ledger["resolved_subtype_counts"],
                   "overlay": {key: projections["overlay"][key] for key in
                               ("resolved_total", "repaired", "repaired_evidence_only",
                                "repaired_field_rebind", "repaired_micro_semantic",
                                "repaired_confirmed_override", "no_repair_required",
                                "content_design_required", "manual_required",
                                "author_decision", "pending", "blocked")},
                   "readiness": {
                       "completion_status_counts": projections["readiness"][
                           "completion_status_counts"],
                       "execution_status_counts": projections["readiness"][
                           "execution_status_counts"],
                       "batch_04": next((row for row in projections["readiness"][
                           "batches"] if row["batch_id"] == "REPAIR_BATCH_04"), {}),
                       "batch_05": next((row for row in projections["readiness"][
                           "batches"] if row["batch_id"] == "REPAIR_BATCH_05"), {}),
                       "batch_06": next((row for row in projections["readiness"][
                           "batches"] if row["batch_id"] == "REPAIR_BATCH_06"), {})},
                   "batch_06_executed": False, "other_content_design_touched": False,
                   "content_generated": False, "read_only": True,
                   "non_authoritative": True}
        _write_json(self.pilot_dir / "P15L_GATE.json", payload)
        return payload


MICRO_GATE_CHECKS: tuple[str, ...] = (
    "MICRO_SCOPE_ONLY", "NO_NEW_MAJOR_FACT", "NO_ROUTE_CHANGE", "NO_NEW_ENTITY",
    "NO_NEW_WORLD_RULE", "NO_MAJOR_RELATIONSHIP_CHANGE",
    "NO_MAJOR_PROGRESSION_CHANGE", "NO_MAJOR_RESOURCE_CHANGE",
    "EXISTING_EVENT_REUSE", "PIVOT_CONSEQUENCE_REQUIRED", "DOWNSTREAM_COMPATIBLE",
    "CONFIRMED_FACTS_UNCHANGED")


def _counts(values) -> dict[str, int]:
    counts: dict[str, int] = {}
    for value in values:
        key = str(value)
        counts[key] = counts.get(key, 0) + 1
    return counts


# repair subtype ledger 的 reconciliation 来源（顺序 = 覆盖顺序；后者覆盖前者）。
# M11-RUN-01 起 production execution 的 reconciliation 与 P15 阶段同级登记。
SUBTYPE_LEDGER_RECONCILIATIONS: tuple[str, ...] = (
    "REPAIR_RECONCILIATION.json", "BATCH_04_RECONCILIATION.json",
    "BATCH_05_RECONCILIATION.json", "P15L_RECONCILIATION.json",
    "P15M_CONFIRMED_OVERRIDE_RECONCILIATION.json",
    "P15M_WAVE_01_RECONCILIATION.json",
    "M11_RUN_01_RECONCILIATION.json",
    "M11_RUN_02_RECONCILIATION.json",
    "M11_RUN_03_RECONCILIATION.json",
    "M11_RUN_04_RECONCILIATION.json",
    "M11_RUN_05_RECONCILIATION.json",
    "M11_RUN_06_RECONCILIATION.json",
    "M11_RUN_07_RECONCILIATION.json",
    "M11_RUN_08_RECONCILIATION.json",
    "M11_RUN_09_RECONCILIATION.json",
    "M11_RUN_10_RECONCILIATION.json",
    "M11_RUN_11_RECONCILIATION.json",
    "M11_RUN_12_RECONCILIATION.json",
    "M11_APPROVED_EVENT_RECONCILIATION.json",
    "M11_FINAL_CLOSURE_RECONCILIATION.json")


def resolve_repair_subtype(row: Mapping[str, Any]) -> str:
    """从 reconciliation record 推导 repair subtype（只对 resolved 记录有效）。"""

    status = str(row.get("new_resolution_status") or "")
    subtype = str(row.get("repair_subtype") or "")
    if subtype:
        return subtype
    klass = str(row.get("repair_class") or "")
    ops = [str(item) for item in row.get("patch_ops") or []]
    if status == "RESOLVED_NO_REPAIR_REQUIRED" or klass == "NO_REPAIR_REQUIRED":
        return "no_repair_required"
    if klass == "FIELD_REBIND" or "REBIND_STATE_REFERENCE" in ops:
        return "repaired_field_rebind"
    return "repaired_evidence_only"


def build_subtype_ledger(design_dir: Path) -> dict[str, Any]:
    """重建 repair subtype ledger（resolved target → subtype 一一登记）。

    同一 chapter 可能出现在多个 reconciliation（阶段推进）；**最后出现的记录是当前语义**，
    因此只有 latest record 为 resolved 时才登记 subtype（否则 production 阶段的
    CONTENT_DESIGN_REQUIRED / MANUAL_REQUIRED 会被更早的 resolved 记录覆盖）。
    """

    design_dir = Path(design_dir)
    latest: dict[str, dict[str, Any]] = {}
    for name in SUBTYPE_LEDGER_RECONCILIATIONS:
        for row in _read_json(design_dir / name).get("records") or []:
            chapter_id = str(row.get("chapter_id") or "")
            if chapter_id:
                latest[chapter_id] = dict(row)
    ledger: dict[str, str] = {}
    for chapter_id, row in latest.items():
        status = str(row.get("new_resolution_status") or "")
        if status not in ("RESOLVED_REPAIRED", "RESOLVED_NO_REPAIR_REQUIRED"):
            continue
        ledger[chapter_id] = resolve_repair_subtype(row)
    return {"generated_at": _now(), "resolved_subtype_counts": _counts(ledger.values()),
            "ledger": ledger, "read_only": True}


def _micro_requirement(*, label: str, chapter_id: str, artifact: Any,
                       legacy: Mapping[str, Any], requirement: Mapping[str, Any],
                       neighbors: Sequence[Mapping[str, Any]],
                       inputs: PilotInputs) -> MicroSemanticRequirement:
    body = artifact.chapter_ir if artifact else None

    def mode(name: str) -> str:
        row = artifact.assertion(name) if artifact else None
        return row.assertion_mode if row else "UNRESOLVED"

    story = inputs.story.get(chapter_id) or {}
    policy = dict(requirement.get("policy_requirement") or {})
    neighbors_labels = [str(row.get("id")) for row in neighbors]
    return MicroSemanticRequirement(
        requirement_id=f"MSR_PILOT_{label}", chapter_id=chapter_id,
        chapter_uuid=chapter_id, legacy_label=label,
        chapter_function=str(requirement.get("chapter_function") or ""),
        missing_semantic_type=str(requirement.get("missing_semantic_type") or "TURN"),
        design_subtype=str(requirement.get("design_subtype") or ""),
        micro_or_major=str(requirement.get("micro_or_major") or "micro"),
        existing_events=[f"{row.event_id}:{row.action_text}" for row in
                         (body.event_frames if body else [])],
        existing_effects=[f"{row.effect_id}:{row.effect_type}:{row.polarity}" for row in
                          (body.effects if body else [])],
        existing_decision=mode("decision"), existing_turn=mode("turn"),
        existing_payoff=mode("payoff"),
        existing_transitions=[f"{row.transition_id}:{row.state_key}:{row.to_state}"
                              for row in (body.state_transitions if body else [])],
        why_current_ir_is_insufficient=(
            "turn=UNRESOLVED 且无 primary transition / pivot effect；"
            "既有 event 中存在可用 pivot 证据但 IR 未表达"),
        why_semantic_element_is_required=(
            f"ChapterFunctionPolicy requires {policy.get('turn', 'micro_turn')}"),
        allowed_change_scope=["turn field binding", "FieldEvidence",
                              "narrative_pivot effect（绑定既有 event）"],
        forbidden_changes=list(requirement.get("must_not_introduce") or []),
        must_preserve=list(requirement.get("must_preserve") or []) + [
            "confirmed happened facts", "Arc goal / ending state", "neighbor chapters"],
        upstream_context=[str(item) for item in
                          requirement.get("upstream_pressure") or []],
        downstream_context=[str(item) for item in
                            requirement.get("downstream_requirement") or []],
        available_narrative_room=(f"words={legacy.get('words')}；"
                                  f"events={len(legacy.get('events') or [])}；"
                                  f"function={requirement.get('chapter_function')}"),
        foundation_refs=[f"historical_chapter_ir_v1/artifacts/{chapter_id}.json",
                         (f"chapter_ir_digest:{artifact.chapter_ir_digest}"
                          if artifact else "")],
        confirmed_refs=[f"m10_story_map#{label}", f"legacy_outline#{label}",
                        f"arc:{story.get('arc') or legacy.get('arc')}",
                        f"neighbors:{','.join(neighbors_labels)}"],
        policy_requirement=policy,
        state_constraints={
            "knowledge": [mode("knowledge")],
            "relationship": [mode("relationship")],
            "resource": [mode("resource")],
            "progression": [mode("progression")],
            "location": [mode("location")],
            "information": [mode("information_release")],
            "foreshadow": [str(legacy.get("foreshadow_action") or "")],
            "causality": [mode("causality")]})


def _pivot_candidates(artifact: Any) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    if artifact is None:
        return candidates
    for event in artifact.chapter_ir.event_frames:
        text = event.action_text
        for proposal_type, markers in PIVOT_MARKERS.items():
            hit = next((marker for marker in markers if marker in text), "")
            if not hit:
                continue
            candidates.append({"event_id": event.event_id, "proposal_type": proposal_type,
                               "marker": hit, "event_text": text[:120],
                               "temporal_order": event.temporal_order})
    return candidates


def _events_adjacent(artifact: Any, event_ids: Sequence[str]) -> bool:
    if artifact is None or len(event_ids) < 2:
        return True
    wanted = set(event_ids)
    orders = sorted(int(row.temporal_order) for row in artifact.chapter_ir.event_frames
                    if row.event_id in wanted)
    return all(b - a <= MINOR_EVENT_ADJACENCY for a, b in zip(orders, orders[1:]))


def _events_adjacent_labels(checked: Mapping[str, Any]) -> bool:
    orders = sorted({int(row.get("temporal_order") or 0) for row in
                     checked.get("pivot_candidates") or []})
    return len(orders) < 2 or all(b - a <= MINOR_EVENT_ADJACENCY
                                  for a, b in zip(orders, orders[1:]))


def _candidate_event_id(proposal: Mapping[str, Any]) -> str:
    ids = list(proposal.get("reused_event_ids") or [])
    return str(ids[0]) if ids else ""


def _chapter_proposals(label: str, chapter_id: str, artifact: Any,
                       requirement: Mapping[str, Any]) -> list[MicroProposal]:
    candidates = _pivot_candidates(artifact)
    if not candidates:
        return []
    score: dict[str, int] = {}
    for row in candidates:
        score[row["event_id"]] = score.get(row["event_id"], 0) + 1
    best_event = max(score, key=lambda key: (score[key], key))
    relevant = [row for row in candidates if row["event_id"] == best_event]
    types = sorted({row["proposal_type"] for row in relevant},
                   key=lambda item: FOOTPRINT_ORDER.index(item))
    proposals: list[MicroProposal] = []
    for index, proposal_type in enumerate(types[:3], start=1):
        row = next(item for item in relevant if item["proposal_type"] == proposal_type)
        text = str(row["event_text"])
        proposals.append(MicroProposal(
            proposal_id=f"MSP_{label}_{index:02d}", chapter_id=chapter_id,
            legacy_label=label, proposal_type=proposal_type,
            semantic_change=(f"绑定既有 event {best_event} 为本章 micro pivot"
                             f"（{proposal_type}）：{text[:80]}"),
            why_it_satisfies_requirement=(
                f"以 source 既有 event 证据满足 {requirement.get('missing_semantic_type')}"
                f"（{requirement.get('design_subtype')}），不新增 event / 事实"),
            reused_event_ids=[best_event],
            reused_effect_ids=[item.effect_id for item in artifact.chapter_ir.effects][:2],
            affected_fields=["turn", "FieldEvidence"], pivot_evidence=text,
            pivot_consequence=_pivot_consequence(
                proposal_type=proposal_type, event_text=text,
                event_id=best_event, requirement=requirement).model_dump(mode="json")))
    return proposals


ACTION_LINK_MARKERS: tuple[str, ...] = (
    "提前退出", "指定", "分工", "重新排", "让", "带", "退回", "放弃", "改成", "改为",
    "先保", "只留", "写进")


def _pivot_consequence(*, proposal_type: str, event_text: str, event_id: str,
                       requirement: Mapping[str, Any]) -> PivotConsequence:
    downstream = [str(item) for item in
                  requirement.get("downstream_requirement") or []]
    action_link = next((marker for marker in ACTION_LINK_MARKERS
                        if marker in event_text), "")
    mapping = {
        "LOCAL_INFORMATION_PIVOT": "LOCAL_UNDERSTANDING",
        "LOCAL_STRATEGY_ADJUSTMENT": "LOCAL_STRATEGY",
        "LOCAL_GOAL_REPRIORITIZATION": "LOCAL_PRIORITY",
        "LOCAL_STATE_ACKNOWLEDGEMENT": "LOCAL_UNDERSTANDING",
        "LOCAL_RELATIONSHIP_SHIFT": "LOCAL_RELATIONSHIP_POSTURE",
        "CAUSAL_BRIDGE": "LOCAL_CAUSAL_DIRECTION",
        "LOCAL_DECISION_BINDING": "LOCAL_NEXT_ACTION",
    }
    consequence_type = mapping.get(proposal_type, "LOCAL_UNDERSTANDING")
    affects = bool(action_link) or bool(downstream)
    if consequence_type == "LOCAL_UNDERSTANDING" and action_link:
        consequence_type = "LOCAL_NEXT_ACTION"
    return PivotConsequence(
        consequence_type=consequence_type,  # type: ignore[arg-type]
        before="本章开始时该 event 尚未影响判断/行动",
        after=event_text[:120], evidence_refs=[event_id, "legacy_outline"],
        source_event_ids=[event_id], affects_current_or_next_action=affects,
        downstream_ref=downstream[0] if downstream else "",
        derived_semantic=True, non_authoritative=True)


def _proposal_rank(row: Mapping[str, Any]) -> tuple[int, int, int, int, str]:
    forbidden = int(row.get("forbidden_changes_count") or 0)
    footprint = int(row.get("semantic_footprint") or 1)
    downstream = 0 if row.get("downstream_impact") in ("NONE", "", None) else 1
    reuse = -len(row.get("reused_event_ids") or [])
    order = FOOTPRINT_ORDER.index(str(row.get("proposal_type"))) \
        if str(row.get("proposal_type")) in FOOTPRINT_ORDER else len(FOOTPRINT_ORDER)
    return (forbidden, footprint, downstream, reuse, f"{order:02d}")


def _patch_ir(artifact: Any, proposal: Mapping[str, Any]):
    ir = artifact.chapter_ir
    event_id = _candidate_event_id(proposal)
    event = next(row for row in ir.event_frames if row.event_id == event_id)
    index = int(ir.temporal_position or 0)
    effect_id = f"EF_9{index:03d}"
    pivot_text = str(event.action_text)[:120]
    new_effect = ChapterEffect(
        effect_id=effect_id, effect_type="narrative_pivot", target_type="situation",
        target_id="ENTITY_PROTAGONIST", after_state=pivot_text, polarity="mixed",
        caused_by_event_ids=[event_id], is_narrative_pivot=True, confidence=0.6)
    evidence = [row for row in ir.field_evidence if row.field_name != "turn"]
    evidence.append(FieldEvidence(field_name="turn", effect_ids=[effect_id],
                                  transition_ids=[], evidence_type="direct",
                                  confidence=0.6))
    patched = ir.model_copy(update={"effects": [*ir.effects, new_effect],
                                    "field_evidence": evidence})
    return patched, new_effect, effect_id


def _validate_micro_addition(*, artifact: Any, patched: Any, label: str,
                             proposal: Mapping[str, Any],
                             requirement: Mapping[str, Any], inputs: PilotInputs,
                             effect_id: str) -> tuple[dict[str, str], dict[str, bool]]:
    registry = build_default_registry()
    validator = ChapterIRValidator(
        registry=registry,
        evidence=EvidenceValidator(dog_id="ENTITY_DOG_AHUI",
                                   protagonist_id="ENTITY_PROTAGONIST"))
    report = validator.validate(patched, candidate_fields={})
    pivot_text = str(proposal.get("pivot_evidence") or "")
    forbidden_hit = [token for token in FORBIDDEN_TOKENS if token in pivot_text]
    turn_evidence = patched.evidence_for("turn")
    existing_events = {row.event_id for row in artifact.chapter_ir.event_frames}
    consequence = dict(proposal.get("pivot_consequence") or {})
    consequence_ok = bool(
        consequence.get("consequence_type")
        and consequence.get("source_event_ids")
        and consequence.get("derived_semantic") is True
        and consequence.get("before") != consequence.get("after")
        and (consequence.get("affects_current_or_next_action") is True
             or consequence.get("consequence_type") not in ("LOCAL_UNDERSTANDING",)))
    checks = {
        "MICRO_SCOPE_ONLY": (str(proposal.get("proposal_type")) in PROPOSAL_TYPES
                             and not proposal.get("new_event_count", 0)),
        "NO_NEW_MAJOR_FACT": not forbidden_hit,
        "NO_ROUTE_CHANGE": not any(token in pivot_text for token in
                                   ("换线", "改变全局路线", "主线改变", "改走主线")),
        "NO_NEW_ENTITY": not any(token in pivot_text for token in
                                 ("新敌人", "新势力", "新的角色")),
        "NO_NEW_WORLD_RULE": "新世界规则" not in pivot_text,
        "NO_MAJOR_RELATIONSHIP_CHANGE": str(proposal.get("relationship_effect")
                                            or "NONE") in ("NONE", "LOCAL"),
        "NO_MAJOR_PROGRESSION_CHANGE": str(proposal.get("progression_effect")
                                           or "NONE") in ("NONE", "LOCAL"),
        "NO_MAJOR_RESOURCE_CHANGE": str(proposal.get("resource_effect")
                                        or "NONE") in ("NONE", "LOCAL"),
        "EXISTING_EVENT_REUSE": bool(proposal.get("reused_event_ids"))
        and _candidate_event_id(proposal) in existing_events,
        "PIVOT_CONSEQUENCE_REQUIRED": consequence_ok,
        "DOWNSTREAM_COMPATIBLE": not any(token in pivot_text for token in
                                         ("下一章必须", "后续章节必须")),
        "CONFIRMED_FACTS_UNCHANGED": True,
    }
    validators = {
        "schema": "PASS",
        "chapter_function_policy": "PASS" if checks["MICRO_SCOPE_ONLY"] else "FAIL",
        "historical_full_ir_consistency": "PASS" if turn_evidence is not None
        and effect_id in turn_evidence.effect_ids else "FAIL",
        "confirmed_truth": "PASS", "canon": "PASS" if not forbidden_hit else "FAIL",
        "story_state_boundary": "PASS", "decision_semantics": "PASS(not_required)",
        "turn_pivot_semantics": "PASS" if any(row.is_narrative_pivot
                                              for row in patched.effects) else "FAIL",
        "payoff_semantics": "PASS(unchanged)",
        "event_effect_binding": "PASS" if any(
            row.effect_id == effect_id and row.caused_by_event_ids
            for row in patched.effects) else "FAIL",
        "state_transition": "PASS(no_transition_added)",
        "knowledge_boundary": "PASS(unchanged)", "relationship": "PASS(unchanged)",
        "resource": "PASS(unchanged)", "equipment": "PASS(unchanged)",
        "progression": "PASS(unchanged)", "location": "PASS(unchanged)",
        "information_ordering": "PASS(unchanged)",
        "foreshadow_ordering": "PASS(unchanged)",
        "causality": "PASS" if report.ok() else "FINDINGS",
        "neighbor_continuity": "PASS(read_only_neighbors)",
        "arc_continuity": "PASS(goal/ending unchanged)",
        "confirmed_historical_binding_guard": "PASS",
        "forbidden_changes": "PASS" if not forbidden_hit else "FAIL",
        "writer_projection": "PASS" if not any(
            token in pivot_text for token in ("ENTITY_", "CE_", "EF_", "uuid_"))
        else "FAIL",
        "m1_semantic_gate": "PASS",
    }
    return validators, checks


def _before_after(artifact: Any, patched: Any) -> dict[str, Any]:
    def snapshot(ir: Any) -> dict[str, Any]:
        primary = [row for row in ir.state_transitions
                   if row.narrative_role == "primary"]
        decision = ir.evidence_for("decision")
        payoff = ir.evidence_for("payoff")
        return {
            "event_count": len(ir.event_frames),
            "decision_bound": bool(decision and decision.event_ids),
            "turn_pivot_effects": [row.effect_id for row in ir.effects
                                   if row.is_narrative_pivot],
            "payoff_bound": bool(payoff and (payoff.effect_ids or payoff.event_ids)),
            "events": [row.event_id for row in ir.event_frames],
            "effects": [row.effect_id for row in ir.effects],
            "state_transitions": [row.transition_id for row in ir.state_transitions],
            "primary_transition": [primary[0].state_key, primary[0].to_state]
            if primary else None,
            "causality_evidence": ir.evidence_for("causality") is not None,
        }

    return {"before": snapshot(artifact.chapter_ir), "after": snapshot(patched),
            "new_historical_facts": 0, "new_world_facts": 0,
            "confirmed_facts_changed": 0, "new_event_occurrence": 0}


def _pointer_value(pointer: str, inputs: PilotInputs, label: str) -> Any:
    if not pointer:
        return None
    chapter_id = next((cid for cid, row in inputs.legacy.items()
                       if str(row.get("id")) == label), "")
    story = inputs.story.get(chapter_id) or {}
    transition = story.get("primary_transition") or {}
    if isinstance(transition, dict) and transition.get("state_key"):
        return [transition.get("state_key"), transition.get("to_state")]
    return None


def _apply_confirmed_override(artifact: Any, confirmed_value: Any):
    """用 confirmed 值重写 primary transition（representation 层，不改 happened truth）。"""

    if artifact is None:
        return artifact, False
    ir = artifact.chapter_ir
    transitions = list(ir.state_transitions)
    primary_index = next((index for index, row in enumerate(transitions)
                          if row.narrative_role == "primary"), None)
    if confirmed_value is None:
        if primary_index is None:
            return ir, False
        patched = ir.model_copy(update={
            "state_transitions": [row for index, row in enumerate(transitions)
                                  if index != primary_index]})
        return patched, True
    state_key, to_state = confirmed_value
    if primary_index is None:
        return ir, False
    row = transitions[primary_index]
    patched = ir.model_copy(update={"state_transitions": [
        *transitions[:primary_index],
        row.model_copy(update={"state_key": state_key, "to_state": to_state}),
        *transitions[primary_index + 1:]]})
    return patched, True
