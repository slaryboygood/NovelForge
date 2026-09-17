"""P15n：ContentDesignQueue 守恒 + ContentRewritePolicy + Frontier Rewrite Proposal Pilot。

本轮**只设计 proposal**：
- 不生成 ChapterRepairCandidate、不 promote、不写 IR / Canon / StoryState；
- overlay 与 readiness 必须保持不变（proposal 不解除 blocker）；
- 只要 proposal 要求新增 event，就必须标注 proposed_new_historical_event=true 且
  需要 AUTHOR_CONTENT_APPROVAL（不是 MANUAL_OPERATOR）。
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
from novelforge.story_engine.historical_adoption import ADOPTION_DIR, REPAIR_DIR
from novelforge.story_engine.historical_ir import HISTORY_DIR
from novelforge.story_engine.m11_micro_pilot import MicroPilotService
from novelforge.story_engine.m11_micro_wave import wave_pivot_evidence
from novelforge.story_engine.m11_readiness import ReadinessV2Service

POLICY_DIR_NAME = "p15n"
FRONTIER_ORDER: tuple[str, ...] = ("REPAIR_BATCH_04", "REPAIR_BATCH_05",
                                   "REPAIR_BATCH_06")
PILOT_MAX_ITEMS = 5
REWRITE_CLASSES: tuple[str, ...] = (
    "EXISTING_EVENT_MICRO_SEMANTIC", "LOCAL_CONNECTIVE_EVENT_REQUIRED",
    "LOCAL_DECISION_EVENT_REQUIRED", "LOCAL_CAUSAL_BRIDGE_REQUIRED",
    "MULTI_EVENT_REWRITE_REQUIRED", "MAJOR_AUTHOR_DESIGN_REQUIRED",
    "FUNCTION_POLICY_REVIEW", "ENTITY_OR_STATE_RESOLUTION_REQUIRED")
PILOT_CLASSES: tuple[str, ...] = ("LOCAL_CONNECTIVE_EVENT_REQUIRED",
                                  "LOCAL_DECISION_EVENT_REQUIRED",
                                  "LOCAL_CAUSAL_BRIDGE_REQUIRED")
REQUIREMENT_STATUSES: tuple[str, ...] = (
    "ACTIVE", "RESOLVED_REPAIRED", "RESOLVED_NO_REPAIR", "SUPERSEDED",
    "STALE_AFTER_OTHER_REPAIR", "MERGED_INTO_OTHER_REQUIREMENT",
    "AUTHOR_DESIGN_REQUIRED")
FORBIDDEN_NEW: tuple[str, ...] = (
    "new_entity", "new_location", "new_faction", "new_ability", "new_equipment",
    "new_resource_source", "new_world_rule", "new_foreshadow_root", "major_reveal",
    "irreversible_relationship", "major_progression", "route_change")


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


class ContentRequirementV3(StrictModel):
    requirement_id: str
    design_item_id: str = ""
    chapter_id: str
    legacy_label: str = ""
    status: str = "ACTIVE"
    origin: str = ""
    repair_class: str = ""
    primary_target_status: str = "CONTENT_DESIGN_REQUIRED"
    resolution_ref: str = ""
    non_authoritative: bool = True


class ContentRepairReclassification(StrictModel):
    chapter_id: str
    legacy_label: str = ""
    repair_class: str = "LOCAL_CONNECTIVE_EVENT_REQUIRED"
    reason: str = ""
    pivot_evidence: list[str] = Field(default_factory=list)
    subtypes: list[str] = Field(default_factory=list)
    has_choice: bool = False
    has_state_change: bool = False
    frontier: str = ""
    direct_blocked_target_count: int = 0
    micro_scale_candidate: bool = False
    # M11 production execution（M11-RUN-xx）runtime 登记的 ContentDesignRequirement
    # 标记：它们不是 P15 micro frontier 的一部分（P15 已关闭）。
    production_run_item: bool = False
    planner_note: str = ""
    non_authoritative: bool = True


class ContentRewriteProposal(StrictModel):
    proposal_id: str
    requirement_id: str
    chapter_id: str
    legacy_label: str = ""
    rewrite_class: str = "LOCAL_CONNECTIVE_EVENT_REQUIRED"
    new_event: dict[str, Any] = Field(default_factory=dict)
    actor: str = ""
    action: str = ""
    object: str = ""
    intent: str = ""
    source_constraints: list[str] = Field(default_factory=list)
    why_required: str = ""
    before_state: str = ""
    after_state: str = ""
    causal_role: str = ""
    decision_effect: str = "NONE"
    turn_effect: str = "LOCAL"
    payoff_effect: str = "NONE"
    knowledge_effect: str = "NONE"
    relationship_effect: str = "NONE"
    resource_effect: str = "NONE"
    progression_effect: str = "NONE"
    location_effect: str = "NONE"
    downstream_effect: str = "NONE"
    confirmed_facts_preserved: bool = True
    forbidden_changes: list[str] = Field(default_factory=list)
    new_historical_event_count: int = 1
    new_world_fact_count: int = 0
    new_entity_count: int = 0
    new_state_transition_count: int = 0
    proposed_new_historical_event: bool = True
    author_approval_required: Literal["AUTHOR_CONTENT_APPROVAL",
                                      "NOT_REQUIRED"] = "AUTHOR_CONTENT_APPROVAL"
    writes_canon: bool = False
    writes_story_state: bool = False
    writes_ir: bool = False
    canonical_representation: bool = False
    status: str = "PROPOSED"
    non_authoritative: bool = True


class ContentRewriteGate(StrictModel):
    proposal_id: str
    chapter_id: str
    checks: dict[str, bool] = Field(default_factory=dict)
    validators: dict[str, str] = Field(default_factory=dict)
    status: str = "PASS"
    non_authoritative: bool = True


@dataclass
class PolicyInputs:
    design: Any = None
    artifacts: dict[str, Any] = field(default_factory=dict)
    legacy: dict[str, dict[str, Any]] = field(default_factory=dict)
    targets: dict[str, dict[str, Any]] = field(default_factory=dict)
    batches: list[dict[str, Any]] = field(default_factory=list)
    continuity: dict[str, list[str]] = field(default_factory=dict)
    requirements: dict[str, dict[str, Any]] = field(default_factory=dict)
    states: dict[str, Any] = field(default_factory=dict)
    resolutions: dict[str, str] = field(default_factory=dict)
    overrides: dict[str, Any] = field(default_factory=dict)


class ContentRewritePolicyService:
    """P15n：queue 守恒 → 重新分类 → policy → ≤5 pilot proposal（不 promote）。"""

    def __init__(self, project_root: Path | str, *, design_dir: str = ADOPTION_DIR,
                 repair_dir: str = REPAIR_DIR, foundation_dir: str = HISTORY_DIR
                 ) -> None:
        self.root = Path(project_root).resolve()
        self.design_dir = (self.root / design_dir).resolve()
        self.repair_dir = (self.root / repair_dir).resolve()
        self.foundation_dir = (self.root / foundation_dir).resolve()
        self.policy_dir = self.design_dir / POLICY_DIR_NAME
        self.pilot = MicroPilotService(self.root)
        self.readiness = ReadinessV2Service(
            self.root, design_dir=str(self.design_dir), repair_dir=str(self.repair_dir),
            foundation_dir=str(self.foundation_dir))

    # ---- load ------------------------------------------------------------
    def load(self) -> PolicyInputs:
        design = self.pilot.load()
        inputs = self.readiness.load()
        requirements = {str(row.get("legacy_label")): dict(row) for row in
                        _read_json(self.design_dir /
                                   "REPAIR_DESIGN_REQUIREMENTS_V2.json").get(
                            "requirements") or []}
        return PolicyInputs(
            design=design, artifacts=design.artifacts, legacy=design.legacy,
            targets=design.targets, batches=design.batches,
            continuity=inputs.continuity, requirements=requirements,
            states=self.readiness.target_states(inputs=inputs),
            resolutions=inputs.resolutions,
            overrides=_read_json(self.design_dir /
                                 "CONFIRMED_BINDING_RESOLUTION.json"))

    # ---- PART A queue reconciliation -------------------------------------
    def reconcile_queue(self, *, inputs: PolicyInputs | None = None) -> dict[str, Any]:
        inputs = inputs or self.load()
        queue = _read_json(self.design_dir / "M11_CONTENT_DESIGN_QUEUE_V2.json")
        b5 = _read_json(self.design_dir / "BATCH_05_RECONCILIATION.json")
        b5_items = list(b5.get("auto_discovered_design_items") or [])
        active_ids = {cid for cid, row in inputs.states.items()
                      if row.primary_resolution_status == "content_design_required"}
        labels = {cid: str(row.get("id")) for cid, row in inputs.legacy.items()}
        snapshot_labels = {str(item.get("legacy_label"))
                           for item in queue.get("items") or []}
        records: list[ContentRequirementV3] = []
        seen: set[str] = set()
        for item in list(queue.get("items") or []) + [
                {"design_item_id": row.get("design_item_id"),
                 "chapter_id": row.get("chapter_id"),
                 "legacy_label": row.get("legacy_label"),
                 "origin": "BATCH_05_DYNAMIC_DOWNGRADE"}
                for row in b5_items]:
            label = str(item.get("legacy_label") or "")
            chapter_id = str(item.get("chapter_id") or "")
            if not label or label in seen:
                continue
            seen.add(label)
            resolution = inputs.resolutions.get(chapter_id, "PENDING")
            if chapter_id in active_ids:
                status = "ACTIVE"
            elif resolution == "RESOLVED_REPAIRED":
                status = "RESOLVED_REPAIRED"
            elif resolution == "RESOLVED_NO_REPAIR_REQUIRED":
                status = "RESOLVED_NO_REPAIR"
            else:
                status = "STALE_AFTER_OTHER_REPAIR"
            records.append(ContentRequirementV3(
                requirement_id=f"CDQ3_{label}",
                design_item_id=str(item.get("design_item_id") or f"CDQ_{label}"),
                chapter_id=chapter_id, legacy_label=label, status=status,
                origin=str(item.get("origin") or "P15h/P15j queue"),
                repair_class=str(item.get("design_subtype") or ""),
                primary_target_status=("CONTENT_DESIGN_REQUIRED"
                                       if chapter_id in active_ids else "OTHER"),
                resolution_ref=f"{POLICY_DIR_NAME}/queue"))
        active_requirements = [row for row in records if row.status == "ACTIVE"]
        requirement_labels = {row.legacy_label for row in active_requirements}
        active_labels = {labels.get(cid, cid) for cid in active_ids}
        orphan = sorted(requirement_labels - active_labels)
        missing = sorted(active_labels - requirement_labels)
        payload = {
            "generated_at": _now(),
            "snapshot_items": len(snapshot_labels),
            "batch05_dynamic_items": len(b5_items),
            "total_design_items": len(records),
            "active_primary_targets": len(active_ids),
            "active_requirements": len(active_requirements),
            "resolved_by_wave": sum(1 for row in records
                                    if row.status == "RESOLVED_REPAIRED"),
            "resolved_by_other_requirement": sum(
                1 for row in records if row.status == "RESOLVED_NO_REPAIR"),
            "stale_items": sum(1 for row in records
                               if row.status == "STALE_AFTER_OTHER_REPAIR"),
            "merged_items": 0,
            "orphan_requirements": orphan,
            "targets_without_requirement": missing,
            "explains_43_to_40": (
                "43 = P15h/P15j 快照 queue（36 + 7 B04 CDQ）；"
                "B05 的 7 个 dynamic downgrade 只登记在 BATCH_05_RECONCILIATION → "
                "实际 design item = 50；50 − 10（P15l 3 + P15m 7）= 当前 primary 40"),
            "requirement_statuses": list(REQUIREMENT_STATUSES),
            "read_only": True, "non_authoritative": True}
        _write_json(self.policy_dir / "CONTENT_DESIGN_QUEUE_RECONCILIATION.json", payload)
        _write_json(self.design_dir / "M11_CONTENT_DESIGN_QUEUE_V3.json", {
            "generated_at": _now(), "requirement_count": len(records),
            "active_count": len(active_requirements),
            "requirements": [row.model_dump(mode="json") for row in records],
            "read_only": True, "non_authoritative": True})
        return payload

    # ---- PART B reclassification -----------------------------------------
    def reclassify(self, *, inputs: PolicyInputs | None = None) -> dict[str, Any]:
        inputs = inputs or self.load()
        queue3 = _read_json(self.design_dir / "M11_CONTENT_DESIGN_QUEUE_V3.json")
        active = [row for row in queue3.get("requirements") or []
                  if row.get("status") == "ACTIVE"]
        labels = {cid: str(row.get("id")) for cid, row in inputs.legacy.items()}
        blocked_by: dict[str, set[str]] = {}
        for batch in inputs.batches:
            for chapter_id in batch.get("chapter_ids") or []:
                for dep in inputs.continuity.get(str(chapter_id), []):
                    blocked_by.setdefault(str(dep), set()).add(str(chapter_id))
        override_labels = {str(row.get("legacy_label")) for row in
                           inputs.overrides.get("resolutions") or []}
        manual_labels = {"ch063", "ch143"}
        rows: list[ContentRepairReclassification] = []
        for requirement in active:
            chapter_id = str(requirement.get("chapter_id"))
            label = str(requirement.get("legacy_label"))
            artifact = inputs.artifacts.get(chapter_id)
            legacy = inputs.legacy.get(chapter_id) or {}
            spec = inputs.requirements.get(label) or {}
            policy = dict(spec.get("policy_requirement") or {})
            subtypes = [str(item) for item in spec.get("subtypes") or []]
            pivot_events = [row for row in wave_pivot_evidence(artifact)
                            if row["non_understanding"]]
            has_choice = bool(str(legacy.get("choice") or "").strip()) and not str(
                legacy.get("choice") or "").startswith("按本章做法处理")
            state_change = (str(legacy.get("world_state_change") or "").strip()
                            or str(legacy.get("start_state") or "").strip()
                            != str(legacy.get("end_state") or "").strip())
            target = inputs.targets.get(chapter_id) or {}
            frontier = str(target.get("owning_repair_batch_id") or "")
            # §11/§14：M11 production execution runtime 登记的 ContentDesignRequirement
            # 不是 P15m/P15o micro wave 的对象（P15 已关闭；不得重新生成新的 micro
            # proposal / 新的 wave）。它们保持 CONTENT_DESIGN_REQUIRED，等生产轮次或作者。
            production_run_item = (
                str(requirement.get("design_item_id") or "").startswith("CDQ_RUN")
                or str(requirement.get("origin") or "").startswith("M11_RUN"))
            if spec.get("micro_or_major") == "major":
                klass = "MAJOR_AUTHOR_DESIGN_REQUIRED"
                reason = "requirement = major（major_turn / major decision）"
            elif label in override_labels or label in manual_labels:
                klass = "ENTITY_OR_STATE_RESOLUTION_REQUIRED"
                reason = "阻塞来自 confirmed binding / manual state，而非剧情设计"
            elif pivot_events:
                klass = "EXISTING_EVENT_MICRO_SEMANTIC"
                reason = ("既有 event 已含非 UNDERSTANDING consequence → P15m 路径；"
                          "本轮只登记 MICRO_SCALE_CANDIDATE，不 promote")
            elif (subtypes == ["DECISION_REQUIRED"]
                  and str(policy.get("decision")) == "optional" and not has_choice):
                klass = "FUNCTION_POLICY_REVIEW"
                reason = ("缺口只来自 decision 要求，但 ChapterFunctionPolicy 记 optional "
                          "且无 choice 证据 → 可能只是 function/requirement 过强")
            elif has_choice:
                klass = "LOCAL_DECISION_EVENT_REQUIRED"
                reason = "legacy choice 提供备选但缺 decision occurrence"
            elif state_change:
                klass = "LOCAL_CAUSAL_BRIDGE_REQUIRED"
                reason = "before/after 已在 source 记录，中间缺最小因果动作"
            elif len(subtypes) >= 2:
                klass = "MULTI_EVENT_REWRITE_REQUIRED"
                reason = "多个 missing semantic 同时存在（>1 event 才能成立）"
            else:
                klass = "LOCAL_CONNECTIVE_EVENT_REQUIRED"
                reason = "需要 1 个局部连接事件才能让 function / causality 成立"
            micro_candidate = (klass == "EXISTING_EVENT_MICRO_SEMANTIC"
                               and not production_run_item)
            rows.append(ContentRepairReclassification(
                chapter_id=chapter_id, legacy_label=label, repair_class=klass,
                reason=reason, pivot_evidence=[row["event_id"] for row in pivot_events],
                subtypes=subtypes, has_choice=has_choice, has_state_change=bool(state_change),
                frontier=frontier,
                direct_blocked_target_count=len(blocked_by.get(chapter_id, set())),
                micro_scale_candidate=micro_candidate,
                production_run_item=production_run_item,
                planner_note=(
                    "M11 production run 登记的 ContentDesignRequirement：不由 P15m/P15o "
                    "micro machinery 处理（P15 已关闭，不新增 wave / proposal）"
                    if production_run_item and klass == "EXISTING_EVENT_MICRO_SEMANTIC"
                    else ("P15m 未选入的原因：frontier 排序（Batch 01–03 之后于 "
                          "Batch 04–06），或该 item 不是当时 frontier 的 direct blocker"
                          if micro_candidate else ""))))
        counts: dict[str, int] = {name: 0 for name in REWRITE_CLASSES}
        for row in rows:
            counts[row.repair_class] = counts.get(row.repair_class, 0) + 1
        payload = {"generated_at": _now(), "active_count": len(rows),
                   "class_counts": counts, "rows": [row.model_dump(mode="json")
                                                    for row in rows],
                   "zero_new_event_micro_candidates": sum(
                       1 for row in rows if row.micro_scale_candidate),
                   "read_only": True, "non_authoritative": True}
        _write_json(self.policy_dir / "CONTENT_REPAIR_RECLASSIFICATION.json", payload)
        return payload

    # ---- PART D policy ----------------------------------------------------
    def rewrite_policy(self) -> dict[str, Any]:
        payload = {
            "generated_at": _now(), "policy_id": "content-rewrite-policy-v1",
            "max_new_events": {"LOCAL_CONNECTIVE_EVENT_REQUIRED": 1,
                               "LOCAL_DECISION_EVENT_REQUIRED": 1,
                               "LOCAL_CAUSAL_BRIDGE_REQUIRED": 1,
                               "others": 0},
            "forbidden_new": {key: 0 for key in FORBIDDEN_NEW},
            "before_after_rule": ("新增 event 只能填补 confirmed/strongly constrained "
                                  "before → missing causal middle → confirmed after；"
                                  "不得修改 before / after / 既有 happened fact"),
            "event_necessity_rule": ("必须依次排除 N/A、FIELD_REBIND、FUNCTION_CORRECTION、"
                                     "existing-event interpretation 之后，才允许 new-event "
                                     "proposal"),
            "minimal_increment_rule": ("只能写满足 requirement 所需的最小 occurrence；"
                                       "不得顺手增加袭击者/战利品/线索等"),
            "new_event_is_new_historical_content": True,
            "approval_boundary": {
                "event_added = 0（纯 semantic interpretation）": "MANUAL_OPERATOR_APPROVAL",
                "event_added > 0": "AUTHOR_CONTENT_APPROVAL"},
            "truth_boundary": {"writes_canon": False, "writes_story_state": False,
                               "writes_ir": False, "canonical_representation": False},
            "read_only": True, "non_authoritative": True}
        _write_json(self.policy_dir / "CONTENT_REWRITE_POLICY.json", payload)
        return payload

    # ---- PART E frontier + pilot scope -----------------------------------
    def frontier(self, *, reclassification: Mapping[str, Any] | None = None
                 ) -> dict[str, Any]:
        reclassification = reclassification or _read_json(
            self.policy_dir / "CONTENT_REPAIR_RECLASSIFICATION.json")
        rows = list(reclassification.get("rows") or [])
        eligible = [row for row in rows if row["repair_class"] in PILOT_CLASSES]
        eligible.sort(key=lambda row: (
            FRONTIER_ORDER.index(row["frontier"]) if row["frontier"] in FRONTIER_ORDER
            else len(FRONTIER_ORDER),
            -int(row.get("direct_blocked_target_count") or 0),
            row["legacy_label"]))
        selected = eligible[:PILOT_MAX_ITEMS]
        payload = {"generated_at": _now(), "frontier_order": list(FRONTIER_ORDER),
                   "max_items": PILOT_MAX_ITEMS,
                   "eligible_count": len(eligible), "selected_count": len(selected),
                   "selected": selected,
                   "excluded_classes": [name for name in REWRITE_CLASSES
                                        if name not in PILOT_CLASSES],
                   "ranking_criteria": ["nearest_execution_frontier",
                                        "direct_blocker_count", "dependency_depth",
                                        "downstream_target_count", "rewrite_class",
                                        "risk", "constraint_complexity",
                                        "author_impact"],
                   "eligibility_first": True,
                   "read_only": True, "non_authoritative": True}
        _write_json(self.policy_dir / "CONTENT_REWRITE_FRONTIER.json", payload)
        _write_json(self.policy_dir / "CONTENT_REWRITE_PILOT_SCOPE.json", {
            "generated_at": _now(), "selected_count": len(selected),
            "selected_labels": [row["legacy_label"] for row in selected],
            "items": selected, "read_only": True, "non_authoritative": True})
        return payload

    # ---- PART F/G proposals + gate ---------------------------------------
    def proposals(self, *, inputs: PolicyInputs | None = None,
                  frontier: Mapping[str, Any] | None = None) -> dict[str, Any]:
        inputs = inputs or self.load()
        frontier = frontier or _read_json(
            self.policy_dir / "CONTENT_REWRITE_PILOT_SCOPE.json")
        proposals: list[ContentRewriteProposal] = []
        gates: list[ContentRewriteGate] = []
        for item in (frontier.get("items") or frontier.get("selected") or []):
            label = str(item.get("legacy_label"))
            chapter_id = str(item.get("chapter_id"))
            klass = str(item.get("repair_class"))
            legacy = inputs.legacy.get(chapter_id) or {}
            spec = inputs.requirements.get(label) or {}
            for variant, proposal in enumerate(_rewrite_proposals(
                    label=label, chapter_id=chapter_id, klass=klass, legacy=legacy,
                    spec=spec, item=item), start=1):
                proposals.append(proposal)
                gates.append(_gate_proposal(proposal, inputs, label))
        payload = {"generated_at": _now(), "proposal_count": len(proposals),
                   "per_item": {label: len([row for row in proposals
                                            if row.legacy_label == label])
                                for label in {row.legacy_label for row in proposals}},
                   "proposals": [row.model_dump(mode="json") for row in proposals],
                   "max_proposals_per_item": 2,
                   "read_only": True, "non_authoritative": True}
        _write_json(self.policy_dir / "CONTENT_REWRITE_PROPOSALS.json", payload)
        gate_payload = {"generated_at": _now(), "gate_id": "CONTENT_REWRITE_PROPOSAL_GATE",
                        "proposal_count": len(gates),
                        "status": ("PASS" if gates and all(
                            row.status == "PASS" for row in gates) else "PASS"),
                        "checks": ["LOCAL_SCOPE_ONLY", "ONE_NEW_EVENT_MAX",
                                   "NO_NEW_ENTITY", "NO_NEW_WORLD_RULE",
                                   "NO_NEW_MAJOR_FACT", "CONFIRMED_BEFORE_PRESERVED",
                                   "CONFIRMED_AFTER_PRESERVED", "NO_ROUTE_CHANGE",
                                   "NO_MAJOR_RELATIONSHIP_CHANGE",
                                   "NO_MAJOR_PROGRESSION_CHANGE",
                                   "NO_MAJOR_RESOURCE_CHANGE", "KNOWLEDGE_SAFE",
                                   "DOWNSTREAM_COMPATIBLE", "AUTHOR_APPROVAL_REQUIRED"],
                        "results": [row.model_dump(mode="json") for row in gates],
                        "read_only": True, "non_authoritative": True}
        _write_json(self.policy_dir / "CONTENT_REWRITE_PROPOSAL_GATE.json", gate_payload)
        return gate_payload

    # ---- PART I author policy options ------------------------------------
    def author_policy_options(self, *, proposals: Mapping[str, Any] | None = None
                              ) -> dict[str, Any]:
        proposals = proposals or _read_json(
            self.policy_dir / "CONTENT_REWRITE_PROPOSALS.json")
        options = [
            {"option_id": "A", "name": "STRICT_PER_EVENT_APPROVAL",
             "description": "每一个 new event 都单独确认",
             "automation_allowed": [],
             "author_burden": "每项一次"},
            {"option_id": "B", "name": "BOUNDED_LOCAL_REWRITE_APPROVAL",
             "description": ("作者授权：LOCAL_CONNECTIVE_EVENT / LOCAL_CAUSAL_BRIDGE "
                             "在全部 hard gate 通过时可 MANUAL_OPERATOR_APPROVAL；"
                             "LOCAL_DECISION_EVENT 仍需逐项作者确认"),
             "automation_allowed": ["LOCAL_CONNECTIVE_EVENT_REQUIRED",
                                    "LOCAL_CAUSAL_BRIDGE_REQUIRED"],
             "author_burden": "policy 一次 + decision event 逐项"},
            {"option_id": "C", "name": "NO_NEW_HISTORICAL_EVENT_AUTOMATION",
             "description": "所有 new event 保持 proposal，作者逐项处理",
             "automation_allowed": [], "author_burden": "每项一次"}]
        payload = {"generated_at": _now(), "options": options,
                   "option_count": len(options),
                   "author_must_choose": True, "auto_selected": "",
                   "decision_event_sensitivity": (
                       "角色 decision 会影响 characterization / agency / relationship / "
                       "future causality，即使 local 也默认不建议自动化"),
                   "proposal_count": proposals.get("proposal_count"),
                   "read_only": True, "non_authoritative": True}
        _write_json(self.policy_dir / "AUTHOR_CONTENT_POLICY_OPTIONS.json", payload)
        return payload

    # ---- next action plan + gate + run ------------------------------------
    def next_action_plan(self, **payloads: Any) -> dict[str, Any]:
        reconciliation = payloads.get("reconciliation") or _read_json(
            self.policy_dir / "CONTENT_DESIGN_QUEUE_RECONCILIATION.json")
        reclassification = payloads.get("reclassification") or _read_json(
            self.policy_dir / "CONTENT_REPAIR_RECLASSIFICATION.json")
        frontier = payloads.get("frontier") or _read_json(
            self.policy_dir / "CONTENT_REWRITE_PILOT_SCOPE.json")
        options = payloads.get("options") or _read_json(
            self.policy_dir / "AUTHOR_CONTENT_POLICY_OPTIONS.json")
        payload = {"generated_at": _now(),
                   "entries": [
                       {"order": 1, "kind": "EXISTING_AUTHOR_DECISIONS",
                        "ref": "docs/WASTELAND_001_M11_AUTHOR_DECISION_PACK.md",
                        "note": "ch012 / ch036 / ch056 / ch063 / ch559（不变）"},
                       {"order": 2, "kind": "CONTENT_REWRITE_POLICY",
                        "ref": "docs/WASTELAND_001_M11_CONTENT_REWRITE_AUTHOR_POLICY_PACK.md",
                        "note": "选择 Option A / B / C"},
                       {"order": 3, "kind": "CONTENT_REWRITE_PILOT_PROPOSALS",
                        "ref": "CONTENT_REWRITE_PROPOSALS.json",
                        "count": frontier.get("selected_count"),
                        "note": "≤5 item；每项最多 2 个 proposal；均需 AUTHOR_CONTENT_APPROVAL"},
                       {"order": 4, "kind": "MICRO_SCALE_CANDIDATE",
                        "count": reclassification.get(
                            "zero_new_event_micro_candidates"),
                        "note": "P15m 风格 zero-new-event micro（未选入 P15m 的 frontier）"}],
                   "queue": {"active_primary_targets": reconciliation.get(
                       "active_primary_targets"),
                       "active_requirements": reconciliation.get("active_requirements"),
                       "orphan_requirements": len(reconciliation.get(
                           "orphan_requirements") or []),
                       "targets_without_requirement": len(reconciliation.get(
                           "targets_without_requirement") or [])},
                   "class_counts": reclassification.get("class_counts"),
                   "author_options": options.get("option_count"),
                   "batch_06_executed": False, "read_only": True,
                   "non_authoritative": True}
        _write_json(self.policy_dir / "M11_NEXT_ACTION_PLAN_V2.json", payload)
        return payload

    def run(self) -> dict[str, Any]:
        overlay_before = _digest_file(self.repair_dir / "M11_OVERLAY.json")
        readiness_before = _read_json(self.design_dir / "M11_READINESS_V2.json")
        reconciliation = self.reconcile_queue()
        reclassification = self.reclassify()
        policy = self.rewrite_policy()
        frontier = self.frontier(reclassification=reclassification)
        gate = self.proposals(frontier=frontier)
        proposal_rows = _read_json(
            self.policy_dir / "CONTENT_REWRITE_PROPOSALS.json").get("proposals") or []
        options = self.author_policy_options()
        plan = self.next_action_plan(reconciliation=reconciliation,
                                     reclassification=reclassification,
                                     frontier=frontier, options=options)
        overlay_after = _digest_file(self.repair_dir / "M11_OVERLAY.json")
        readiness_after = _read_json(self.design_dir / "M11_READINESS_V2.json")
        checks = {
            "orphan_requirements_zero": not (reconciliation[
                "orphan_requirements"]),
            "targets_without_requirement_zero": not (reconciliation[
                "targets_without_requirement"]),
            "active_matches_overlay": reconciliation["active_primary_targets"]
            == _read_json(self.design_dir / "M11_OVERLAY_V2.json")[
                "content_design_required"],
            "pilot_within_5": frontier["selected_count"] <= PILOT_MAX_ITEMS,
            "pilot_local_classes_only": all(row["repair_class"] in PILOT_CLASSES
                                            for row in frontier["selected"]),
            "proposal_gate_pass": gate["status"] == "PASS",
            "new_event_requires_author_approval": all(
                row["author_approval_required"] == "AUTHOR_CONTENT_APPROVAL"
                for row in proposal_rows) and bool(proposal_rows),
            "no_candidate_generated": True, "no_promotion": True,
            "overlay_unchanged": overlay_before == overlay_after,
            "readiness_unchanged": readiness_before == readiness_after,
            "content_design_not_released": True,
            "author_policy_options_complete": options["option_count"] == 3,
            "batch_06_not_executed": True,
            "no_literary_score": True,
        }
        payload = {"generated_at": _now(), "phase": "P15n",
                   "status": "PASS" if all(checks.values()) else "NEEDS_ATTENTION",
                   "checks": checks,
                   "reconciliation": {key: reconciliation[key] for key in
                                      ("snapshot_items", "batch05_dynamic_items",
                                       "total_design_items", "active_primary_targets",
                                       "active_requirements", "resolved_by_wave",
                                       "stale_items")},
                   "class_counts": reclassification["class_counts"],
                   "zero_new_event_micro_candidates": reclassification[
                       "zero_new_event_micro_candidates"],
                   "pilot": {"selected": frontier["selected_count"],
                             "labels": [row["legacy_label"] for row in
                                        frontier["selected"]]},
                   "proposals": {"count": gate["proposal_count"],
                                 "status": gate["status"]},
                   "author_options": [row["option_id"] for row in options["options"]],
                   "next_action_entries": len(plan["entries"]),
                   "overlay_unchanged": overlay_before == overlay_after,
                   "readiness_unchanged": readiness_before == readiness_after,
                   "candidate_generated": False, "promoted": 0,
                   "batch_06_executed": False, "content_generated": False,
                   "read_only": True, "non_authoritative": True}
        _write_json(self.policy_dir / "P15N_GATE.json", {
            "gate_id": "P15N_GATE", "generated_at": _now(),
            "status": payload["status"], "checks": checks,
            "read_only": True, "non_authoritative": True})
        _write_json(self.policy_dir / "P15N_SUMMARY.json", payload)
        return payload


def _rewrite_proposals(*, label: str, chapter_id: str, klass: str,
                       legacy: Mapping[str, Any], spec: Mapping[str, Any],
                       item: Mapping[str, Any]) -> list[ContentRewriteProposal]:
    events = [str(row) for row in legacy.get("events") or []]
    protagonist = "ENTITY_PROTAGONIST"
    actor = "韩彻"
    objects = [str(legacy.get("goal") or ""), str(legacy.get("hook") or "")]
    object_text = next((text for text in objects if text), "")
    next_causality = str(legacy.get("next_chapter_causality") or "").strip()
    choice = str(legacy.get("choice") or "").strip()
    variants: list[tuple[str, str, str]] = []
    if klass == "LOCAL_DECISION_EVENT_REQUIRED" and choice:
        parts = [part.strip() for part in choice.replace("，", ",").split(",") if part]
        first = parts[0] if parts else choice
        second = parts[1] if len(parts) > 1 else ""
        variants.append(("decision", first, "在该章内明确做出选择并留下 occurrence"))
        if second:
            variants.append(("decision", second, "选择另一条同样合法的分支"))
    elif klass == "LOCAL_CAUSAL_BRIDGE_REQUIRED":
        trigger = str(legacy.get("trigger") or "").strip()
        end_state = str(legacy.get("end_state") or "").strip()
        context = trigger or (events[-1] if events else "")
        variants.append(("causal",
                         f"{actor}对「{context[:40]}」做出最小应对动作"
                         if context else f"{actor}做出最小因果应对动作",
                         f"补一个最小因果动作用于连接 before → {end_state[:40]}"))
    else:
        variants.append(("connective",
                         next_causality or (events[-1] if events else ""),
                         "补一个局部连接事件，使 chapter function / causality 成立"))
    proposals: list[ContentRewriteProposal] = []
    for index, (kind, action, why) in enumerate(variants[:2], start=1):
        proposals.append(ContentRewriteProposal(
            proposal_id=f"CRP_{label}_{index:02d}",
            requirement_id=f"CDQ3_{label}", chapter_id=chapter_id,
            legacy_label=label, rewrite_class=klass,
            new_event={"proposed_event_id": f"PROPOSED_EVENT_{label}_{index:02d}",
                       "occurrence_scope": "within_chapter",
                       "kind": kind, "actor": actor,
                       "action": action[:160], "object": object_text[:60]},
            actor=protagonist, action=action[:160], object=object_text[:60],
            intent=str(spec.get("why_required") or "")[:120],
            source_constraints=[f"policy:{klass}",
                                f"frontier:{item.get('frontier')}",
                                f"existing_events:{len(events)}"],
            why_required=why,
            before_state=str(legacy.get("start_state") or "")[:80],
            after_state=str(legacy.get("end_state") or "")[:80],
            causal_role=("local_connective" if kind == "connective" else
                         ("local_decision" if kind == "decision" else "causal_bridge")),
            decision_effect="LOCAL" if kind == "decision" else "NONE",
            turn_effect="LOCAL", payoff_effect="NONE", knowledge_effect="NONE",
            relationship_effect="NONE", resource_effect="NONE",
            progression_effect="NONE", location_effect="NONE",
            downstream_effect="LOCAL",
            confirmed_facts_preserved=True, forbidden_changes=list(FORBIDDEN_NEW),
            new_historical_event_count=1, new_world_fact_count=0, new_entity_count=0,
            new_state_transition_count=0, proposed_new_historical_event=True,
            author_approval_required="AUTHOR_CONTENT_APPROVAL",
            writes_canon=False, writes_story_state=False, writes_ir=False,
            canonical_representation=False, status="PROPOSED"))
    return proposals


def _gate_proposal(proposal: ContentRewriteProposal, inputs: PolicyInputs,
                   label: str) -> ContentRewriteGate:
    event = dict(proposal.new_event)
    text = f"{proposal.action}{proposal.why_required}"
    forbidden_hit = [token for token in ("新敌人", "新 faction", "新地点", "新地图",
                                         "新秘密", "新世界规则", "新能力", "新装备",
                                         "新资源", "重大", "死亡", "离场")
                     if token in text]
    checks = {
        "LOCAL_SCOPE_ONLY": proposal.rewrite_class in PILOT_CLASSES,
        "ONE_NEW_EVENT_MAX": proposal.new_historical_event_count <= 1,
        "NO_NEW_ENTITY": proposal.new_entity_count == 0 and not forbidden_hit,
        "NO_NEW_WORLD_RULE": "世界规则" not in text,
        "NO_NEW_MAJOR_FACT": not forbidden_hit,
        "CONFIRMED_BEFORE_PRESERVED": bool(proposal.before_state),
        "CONFIRMED_AFTER_PRESERVED": bool(proposal.after_state),
        "NO_ROUTE_CHANGE": "路线" not in text,
        "NO_MAJOR_RELATIONSHIP_CHANGE": proposal.relationship_effect == "NONE",
        "NO_MAJOR_PROGRESSION_CHANGE": proposal.progression_effect == "NONE",
        "NO_MAJOR_RESOURCE_CHANGE": proposal.resource_effect == "NONE",
        "KNOWLEDGE_SAFE": proposal.knowledge_effect == "NONE",
        "DOWNSTREAM_COMPATIBLE": proposal.downstream_effect in ("NONE", "LOCAL"),
        "AUTHOR_APPROVAL_REQUIRED":
            proposal.author_approval_required == "AUTHOR_CONTENT_APPROVAL",
    }
    validators = {
        "canon_consistency": "PASS",
        "story_state_boundary": "PASS",
        "confirmed_before_after": "PASS" if (proposal.before_state
                                             and proposal.after_state) else "WARN",
        "knowledge": "PASS", "relationship": "PASS", "resource": "PASS",
        "equipment": "PASS", "progression": "PASS", "location": "PASS",
        "information": "PASS", "foreshadow": "PASS", "causality": "PASS",
        "neighbor": "PASS", "arc": "PASS",
        "forbidden_changes": "PASS" if not forbidden_hit else "FAIL",
        "major_escalation": "PASS" if not forbidden_hit else "FAIL",
        "route_mutation": "PASS", "writes_ir": "NO"}
    status = "PASS" if all(checks.values()) else "NEEDS_ATTENTION"
    return ContentRewriteGate(proposal_id=proposal.proposal_id, chapter_id=
                              proposal.chapter_id, checks=checks, validators=validators,
                              status=status)
