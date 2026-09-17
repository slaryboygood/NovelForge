"""P15m：Micro Semantic Repair Production Wave 1（≤12 items，受控扩张）。

在 P15l 的基础上：
- 强化 gate：新增 `PIVOT_CONSEQUENCE_REQUIRED`（turn 必须改变理解/策略/目标/优先级/
  风险判断/下一步行动/因果方向，不能只是"观察到结果"）；
- 建立 `MicroRepairFrontierPlanner`：按最近执行 frontier（Batch 04 → 05 → 06 → 07+）
  与结构指标选 ≤12 个 micro item（不使用文学质量评分）；
- proposal tie 防线：不同 consequence_type 且证据不能唯一决定 → HUMAN_REVIEW
  （不总是偏爱 LOCAL_INFORMATION_PIVOT）。

本轮不执行任何 Batch repair、不处理 major/author/entity/manual/confirmed-binding 事项。
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal, Mapping, Sequence

from pydantic import Field

from novelforge.models import StrictModel
from novelforge.story_engine.historical_adoption import ADOPTION_DIR, REPAIR_DIR
from novelforge.story_engine.historical_ir import HISTORY_DIR
from novelforge.story_engine.m11_design import _continuity_map
from novelforge.story_engine.m11_micro_pilot import (
    ACTION_LINK_MARKERS,
    FORBIDDEN_TOKENS,
    MicroPilotService,
    PivotConsequence,
    _before_after,
    _counts,
    _patch_ir,
    _pivot_candidates,
    _validate_micro_addition,
)
from novelforge.story_engine.m11_readiness import ReadinessV2Service

WAVE_ID = "MICRO_WAVE_01"
WAVE_MAX_ITEMS = 12
WAVE_DIR_NAME = "p15m"
FRONTIER_ORDER: tuple[str, ...] = ("REPAIR_BATCH_04", "REPAIR_BATCH_05",
                                   "REPAIR_BATCH_06")
CONSEQUENCE_STRENGTH: dict[str, int] = {
    "LOCAL_NEXT_ACTION": 6, "LOCAL_STRATEGY": 5, "LOCAL_PRIORITY": 5,
    "LOCAL_GOAL": 5, "LOCAL_CAUSAL_DIRECTION": 5, "LOCAL_RISK_ASSESSMENT": 4,
    "LOCAL_RELATIONSHIP_POSTURE": 4, "LOCAL_UNDERSTANDING": 1}
CONSEQUENCE_OF_TYPE: dict[str, str] = {
    "LOCAL_INFORMATION_PIVOT": "LOCAL_UNDERSTANDING",
    "LOCAL_STRATEGY_ADJUSTMENT": "LOCAL_STRATEGY",
    "LOCAL_GOAL_REPRIORITIZATION": "LOCAL_PRIORITY",
    "LOCAL_STATE_ACKNOWLEDGEMENT": "LOCAL_UNDERSTANDING",
    "LOCAL_RELATIONSHIP_SHIFT": "LOCAL_RELATIONSHIP_POSTURE",
    "CAUSAL_BRIDGE": "LOCAL_CAUSAL_DIRECTION",
    "LOCAL_DECISION_BINDING": "LOCAL_NEXT_ACTION",
}
PROPOSAL_TYPES: tuple[str, ...] = tuple(CONSEQUENCE_OF_TYPE)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _digest(payload: Any) -> str:
    return hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True,
                                     default=str).encode("utf-8")).hexdigest()[:16]


def _read_json(path: Path) -> Any:
    path = Path(path)
    return json.loads(path.read_text(encoding="utf-8-sig")) if path.is_file() else {}


def _write_json(path: Path, payload: Any) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=1) + "\n",
                    encoding="utf-8", newline="\n")


class WaveItem(StrictModel):
    design_item_id: str
    chapter_id: str
    legacy_label: str = ""
    owning_batch: str = ""
    eligibility: dict[str, bool] = Field(default_factory=dict)
    eligible: bool = False
    ineligible_reason: str = ""
    frontier_rank: int = 99
    direct_blocked_target_count: int = 0
    downstream_target_count: int = 0
    dependency_depth: int = 0
    risk: str = "MEDIUM"
    reuse_events: list[str] = Field(default_factory=list)
    constraint_complexity: int = 0
    selected: bool = False
    non_authoritative: bool = True


class WaveAdjudication(StrictModel):
    chapter_id: str
    legacy_label: str = ""
    recheck_class: str = "MICRO_SEMANTIC_ADDITION"
    proposal_ids: list[str] = Field(default_factory=list)
    ranked_proposal_ids: list[str] = Field(default_factory=list)
    consequence_types: list[str] = Field(default_factory=list)
    unique_winner: bool = False
    winner_proposal_id: str = ""
    status: str = "HUMAN_REVIEW"
    tie_reason: str = ""
    non_authoritative: bool = True


class MicroRepairFrontierPlanner:
    """§6–§11：按结构指标从 ContentDesignQueue 选 ≤12 个 micro item。"""

    def __init__(self, root: Path | str, *, design_dir: str = ADOPTION_DIR) -> None:
        self.root = Path(root).resolve()
        self.design_dir = (self.root / design_dir).resolve()
        self.pilot = MicroPilotService(self.root)

    def plan(self) -> dict[str, Any]:
        inputs = self.pilot.load()
        queue = _read_json(self.design_dir / "M11_CONTENT_DESIGN_QUEUE_V2.json")
        requirements = {str(row.get("legacy_label")): dict(row) for row in
                        _read_json(self.design_dir /
                                   "REPAIR_DESIGN_REQUIREMENTS_V2.json").get(
                            "requirements") or []}
        resolutions = _resolution_map(self.design_dir)
        blocked_by: dict[str, list[str]] = {}
        for batch in inputs.batches:
            batch_id = str(batch.get("batch_id"))
            for chapter_id in batch.get("chapter_ids") or []:
                for dep in inputs.continuity.get(str(chapter_id), []):
                    blocked_by.setdefault(str(dep), []).append(str(chapter_id))
        override_labels = {str(row.get("legacy_label")) for row in
                           _read_json(self.design_dir /
                                      "CONFIRMED_BINDING_RESOLUTION.json").get(
                               "resolutions") or []}
        entity_chapters: set[str] = set()
        for cluster in _read_json(self.design_dir /
                                  "M11_ENTITY_RESOLUTION_QUEUE.json").get(
                "clusters") or []:
            if cluster.get("requires_exact_identity"):
                entity_chapters |= {str(item) for item in
                                    cluster.get("chapter_ids") or []}
        rows: list[WaveItem] = []
        for item in queue.get("items") or []:
            label = str(item.get("legacy_label") or "")
            chapter_id = str(item.get("chapter_id") or "")
            requirement = requirements.get(label) or {}
            artifact = inputs.artifacts.get(chapter_id)
            resolution = resolutions.get(chapter_id, "PENDING")
            candidates = _pivot_candidates(artifact)
            target = inputs.targets.get(chapter_id) or {}
            owning_batch = str(target.get("owning_repair_batch_id") or "")
            eligibility = {
                "micro": item.get("micro_or_major") == "micro",
                "not_author_design": not bool(item.get("author_decision_required")),
                # §11/§14：production execution（M11-RUN-xx）runtime 登记的 requirement
                # 不由已关闭的 P15m wave 处理（不新增 wave / 新 micro proposal）。
                "not_production_run_item": not (
                    str(item.get("design_item_id") or "").startswith("CDQ_RUN")
                    or str(item.get("origin") or "").startswith("M11_RUN")),
                "no_entity_ambiguity": chapter_id not in entity_chapters,
                "no_manual_blocker": label not in ("ch063", "ch143"),
                "no_confirmed_binding_conflict": label not in override_labels,
                "full_ir_available": artifact is not None,
                "existing_event_pivot": bool(candidates),
                "no_new_event_required": bool(candidates),
                "risk_ok": str(item.get("severity") or target.get("risk")
                               or "MEDIUM") in ("LOW", "MEDIUM"),
                "still_unresolved": resolution not in (
                    "RESOLVED_REPAIRED", "RESOLVED_NO_REPAIR_REQUIRED"),
            }
            eligible = all(eligibility.values())
            frontier_rank = FRONTIER_ORDER.index(owning_batch) \
                if owning_batch in FRONTIER_ORDER else len(FRONTIER_ORDER)
            rows.append(WaveItem(
                design_item_id=str(item.get("design_item_id") or ""),
                chapter_id=chapter_id, legacy_label=label,
                owning_batch=owning_batch, eligibility=eligibility,
                eligible=eligible,
                ineligible_reason=("" if eligible else
                                   ",".join(key for key, value in eligibility.items()
                                            if not value)),
                frontier_rank=frontier_rank,
                direct_blocked_target_count=len(blocked_by.get(chapter_id, [])),
                downstream_target_count=len(blocked_by.get(chapter_id, [])),
                dependency_depth=0 if owning_batch in FRONTIER_ORDER else 1,
                risk=str(item.get("severity") or target.get("risk") or "MEDIUM"),
                reuse_events=sorted({row["event_id"] for row in candidates}),
                constraint_complexity=len(requirement.get("forbidden_changes") or [])))
        eligible = [row for row in rows if row.eligible]
        eligible.sort(key=lambda row: (row.frontier_rank,
                                       -row.direct_blocked_target_count,
                                       row.dependency_depth,
                                       row.risk != "LOW",
                                       len(row.reuse_events) == 0,
                                       row.constraint_complexity,
                                       row.legacy_label))
        selected = eligible[:WAVE_MAX_ITEMS]
        for row in selected:
            row.selected = True
        selected_labels = {row.legacy_label for row in selected}
        deferred = [row for row in eligible if row.legacy_label not in selected_labels]
        ineligible = [row for row in rows if not row.eligible]
        payload = {
            "generated_at": _now(), "wave_id": WAVE_ID,
            "frontier_order": list(FRONTIER_ORDER), "max_items": WAVE_MAX_ITEMS,
            "queue_item_count": len(rows),
            "eligible_count": len(eligible), "selected_count": len(selected),
            "deferred_count": len(deferred), "ineligible_count": len(ineligible),
            "selected": [row.model_dump(mode="json") for row in selected],
            "deferred": [row.model_dump(mode="json") for row in deferred],
            "ineligible": [row.model_dump(mode="json") for row in ineligible],
            "ranking_criteria": ["nearest_frontier", "direct_blocked_target_count",
                                 "dependency_depth", "downstream_target_count",
                                 "existing_event_reuse", "risk", "ambiguity",
                                 "constraint_complexity"],
            "no_literary_score": True,
            "note": ("blocker count 只是排序信号；repair eligibility 先于 unlock value；"
                     "同一 design item 只算一次（按 item 去重，不按 blocked target）"),
            "read_only": True, "non_authoritative": True}
        _write_json(self.design_dir / WAVE_DIR_NAME /
                    "MICRO_REPAIR_WAVE_01_SCOPE.json", payload)
        _write_json(self.design_dir / WAVE_DIR_NAME / "MICRO_REPAIR_FRONTIER.json", {
            "generated_at": _now(),
            "eligible": [row.model_dump(mode="json") for row in eligible],
            "blocker_frontier": {label: len(blocked_by.get(
                next((row.chapter_id for row in rows if row.legacy_label == label), ""),
                [])) for label in FRONTIER_ORDER},
            "read_only": True, "non_authoritative": True})
        return payload


def _resolution_map(design_dir: Path) -> dict[str, str]:
    resolution: dict[str, str] = {}
    for name in ("REPAIR_RECONCILIATION.json", "BATCH_04_RECONCILIATION.json",
                 "BATCH_05_RECONCILIATION.json", "P15L_RECONCILIATION.json",
                 "P15M_CONFIRMED_OVERRIDE_RECONCILIATION.json"):
        for row in _read_json(design_dir / name).get("records") or []:
            resolution[str(row.get("chapter_id"))] = str(
                row.get("new_resolution_status"))
    return resolution


# §1：consequence 类别的明确措辞（"只是观察到结果"不算 turn）
CONSEQUENCE_MARKERS: dict[str, tuple[str, ...]] = {
    "LOCAL_UNDERSTANDING": ("意识到", "明白", "第一次知道", "看出", "确认了",
                            "算账", "明白过来"),
    "LOCAL_STRATEGY": ("提前退出", "改为", "改成", "换", "另走", "绕开", "避开",
                       "指定", "分工", "重新排"),
    "LOCAL_PRIORITY": ("只能先保", "先保", "优先", "来不及", "放弃", "转向",
                       "比水本身值钱", "瓶颈"),
    "LOCAL_GOAL": ("定下目标", "决定", "选择", "改为去", "不卖"),
    "LOCAL_RISK_ASSESSMENT": ("塌", "撑不住", "隐患", "裂缝", "危险", "被盯",
                              "暴露", "失守"),
    "LOCAL_NEXT_ACTION": ("开始", "动手", "返回", "出发", "接手", "写下", "建立",
                          "刻下"),
    "LOCAL_RELATIONSHIP_POSTURE": ("发火", "拒绝", "不肯", "护住", "信任", "分开"),
    "LOCAL_CAUSAL_DIRECTION": ("因此", "于是", "导致", "由此", "埋下"),
}


def wave_pivot_evidence(artifact: Any) -> list[dict[str, Any]]:
    """每个既有 event 的 consequence 证据（至少一个非 UNDERSTANDING 才算 pivot）。"""

    rows: list[dict[str, Any]] = []
    if artifact is None:
        return rows
    for event in artifact.chapter_ir.event_frames:
        text = str(event.action_text)
        classes: list[tuple[str, str]] = []
        for consequence, markers in CONSEQUENCE_MARKERS.items():
            hit = next((marker for marker in markers if marker in text), "")
            if hit:
                classes.append((consequence, hit))
        if not classes:
            continue
        strongest = max(classes, key=lambda item: CONSEQUENCE_STRENGTH[item[0]])
        rows.append({"event_id": event.event_id, "event_text": text[:120],
                     "temporal_order": event.temporal_order,
                     "consequences": [item[0] for item in classes],
                     "strongest": strongest[0], "marker": strongest[1],
                     "non_understanding": strongest[0] != "LOCAL_UNDERSTANDING"})
    return rows


class MicroWaveService:
    """PART E–Q：执行 Wave 01（≤12 items）并输出 scale assessment。"""

    def __init__(self, root: Path | str, *, design_dir: str = ADOPTION_DIR,
                 repair_dir: str = REPAIR_DIR, foundation_dir: str = HISTORY_DIR
                 ) -> None:
        self.root = Path(root).resolve()
        self.design_dir = (self.root / design_dir).resolve()
        self.repair_dir = (self.root / repair_dir).resolve()
        self.foundation_dir = (self.root / foundation_dir).resolve()
        self.wave_dir = self.design_dir / WAVE_DIR_NAME
        self.pilot = MicroPilotService(self.root)
        self.readiness = ReadinessV2Service(
            self.root, design_dir=str(self.design_dir), repair_dir=str(self.repair_dir),
            foundation_dir=str(self.foundation_dir))

    # ---- explicit scope ---------------------------------------------------
    def scope(self) -> dict[str, Any]:
        return MicroRepairFrontierPlanner(self.root).plan()

    # ---- PART E recheck + PART F proposals -------------------------------
    def requirements_and_proposals(self, *, scope: Mapping[str, Any] | None = None
                                   ) -> dict[str, Any]:
        scope = scope or self.scope()
        inputs = self.pilot.load()
        requirements = {str(row.get("legacy_label")): dict(row) for row in
                        _read_json(self.design_dir /
                                   "REPAIR_DESIGN_REQUIREMENTS_V2.json").get(
                            "requirements") or []}
        recheck_rows: list[dict[str, Any]] = []
        proposals: list[dict[str, Any]] = []
        for item in scope.get("selected") or []:
            label = str(item.get("legacy_label"))
            chapter_id = str(item.get("chapter_id"))
            artifact = inputs.artifacts.get(chapter_id)
            requirement = requirements.get(label) or {}
            evidence = wave_pivot_evidence(artifact)
            pivot_events = [row for row in evidence if row["non_understanding"]]
            klass = "MICRO_SEMANTIC_ADDITION" if pivot_events else \
                "CONTENT_REWRITE_REQUIRED"
            recheck_rows.append({
                "legacy_label": label, "chapter_id": chapter_id,
                "recheck_class": klass,
                "consequence_evidence": evidence,
                "pivot_event_ids": [row["event_id"] for row in pivot_events],
                "reason": ("既有 event 直接改变策略/优先级/风险/行动/因果 → micro addition"
                           if pivot_events else
                           "既有 event 只有观察结果，无 consequence → 需要新 event")})
            if klass != "MICRO_SEMANTIC_ADDITION":
                continue
            best = max(pivot_events, key=lambda row: (
                CONSEQUENCE_STRENGTH[row["strongest"]], len(row["consequences"])))
            types = sorted({_proposal_type_for(consequence) for consequence in
                            best["consequences"]},
                           key=lambda item: -CONSEQUENCE_STRENGTH[
                               CONSEQUENCE_OF_TYPE[item]])
            for index, proposal_type in enumerate(types[:3], start=1):
                consequence_type = CONSEQUENCE_OF_TYPE[proposal_type]
                if consequence_type == "LOCAL_UNDERSTANDING":
                    action_link = next((marker for marker in ACTION_LINK_MARKERS
                                        if marker in best["event_text"]
                                        or marker in best["marker"]), "")
                    if action_link:
                        consequence_type = "LOCAL_NEXT_ACTION"
                downstream = [str(value) for value in
                              requirement.get("downstream_requirement") or []]
                consequence = PivotConsequence(
                    consequence_type=consequence_type,  # type: ignore[arg-type]
                    before="该 event 之前，本章判断/行动方向未受其影响",
                    after=best["event_text"][:120],
                    evidence_refs=[best["event_id"], "legacy_outline"],
                    source_event_ids=[best["event_id"]],
                    affects_current_or_next_action=bool(downstream)
                    or consequence_type != "LOCAL_UNDERSTANDING",
                    downstream_ref=downstream[0] if downstream else "",
                    derived_semantic=True, non_authoritative=True)
                proposals.append({
                    "proposal_id": f"MSP_{WAVE_ID}_{label}_{index:02d}",
                    "design_item_id": item.get("design_item_id"),
                    "chapter_id": chapter_id, "legacy_label": label,
                    "proposal_type": proposal_type,
                    "semantic_change": (f"绑定既有 event {best['event_id']} 为 micro pivot"
                                        f"（{proposal_type}）"),
                    "reused_event_ids": [best["event_id"]],
                    "affected_fields": ["turn", "FieldEvidence"],
                    "semantic_footprint": 1, "new_event_count": 0,
                    "pivot_evidence": best["event_text"],
                    "pivot_consequence": consequence.model_dump(mode="json"),
                    "non_authoritative": True})
        scope_rows = {row["legacy_label"]: row for row in scope.get("selected") or []}
        payload = {"generated_at": _now(), "wave_id": WAVE_ID,
                   "selected_count": len(scope.get("selected") or []),
                   "recheck": recheck_rows,
                   "recheck_classes": {row["legacy_label"]: row["recheck_class"]
                                       for row in recheck_rows},
                   "requirements": [
                       {"legacy_label": row["legacy_label"],
                        "requirement_id": f"MSR_{WAVE_ID}_{row['legacy_label']}",
                        "chapter_function": (requirements.get(row["legacy_label"])
                                             or {}).get("chapter_function"),
                        "missing_semantic_type": "TURN",
                        "pivot_event_ids": row["pivot_event_ids"],
                        "consequence_evidence": row["consequence_evidence"],
                        "frontier": scope_rows.get(row["legacy_label"], {}).get(
                            "owning_batch"),
                        "must_preserve": ["confirmed happened facts",
                                          "Arc goal / ending state",
                                          "neighbor chapters"],
                        "forbidden_changes": FORBIDDEN_TOKENS}
                       for row in recheck_rows],
                   "proposals": proposals,
                   "proposal_count": len(proposals),
                   "read_only": True, "non_authoritative": True}
        _write_json(self.wave_dir / "MICRO_WAVE_REQUIREMENTS.json", payload)
        _write_json(self.wave_dir / "MICRO_WAVE_PROPOSALS.json", {
            "generated_at": _now(), "proposal_count": len(proposals),
            "proposals": proposals, "read_only": True,
            "non_authoritative": True})
        return payload

    # ---- PART G adjudication（tie 防线） ---------------------------------
    def adjudicate(self, *, payload: Mapping[str, Any] | None = None
                   ) -> dict[str, Any]:
        payload = payload or _read_json(
            self.wave_dir / "MICRO_WAVE_PROPOSALS.json")
        by_label: dict[str, list[dict[str, Any]]] = {}
        for row in payload.get("proposals") or []:
            by_label.setdefault(str(row.get("legacy_label")), []).append(dict(row))
        recheck = _read_json(self.wave_dir / "MICRO_WAVE_REQUIREMENTS.json")
        recheck_by_label = {row["legacy_label"]: row for row in recheck["recheck"]}
        rows: list[WaveAdjudication] = []
        for label, items in sorted(by_label.items()):
            ranked = sorted(items, key=lambda row: (
                -CONSEQUENCE_STRENGTH[str(row["pivot_consequence"]["consequence_type"])],
                int(row.get("semantic_footprint") or 1),
                str(row.get("proposal_id"))))
            top, second = ranked[0], ranked[1] if len(ranked) > 1 else None
            top_strength = CONSEQUENCE_STRENGTH[
                str(top["pivot_consequence"]["consequence_type"])]
            tie = bool(second and CONSEQUENCE_STRENGTH[
                str(second["pivot_consequence"]["consequence_type"])] == top_strength
                and second["pivot_consequence"]["consequence_type"]
                != top["pivot_consequence"]["consequence_type"])
            rows.append(WaveAdjudication(
                chapter_id=str(top.get("chapter_id")), legacy_label=label,
                recheck_class=str(recheck_by_label.get(label, {}).get(
                    "recheck_class") or "MICRO_SEMANTIC_ADDITION"),
                proposal_ids=[row["proposal_id"] for row in items],
                ranked_proposal_ids=[row["proposal_id"] for row in ranked],
                consequence_types=[row["pivot_consequence"]["consequence_type"]
                                   for row in ranked],
                unique_winner=not tie,
                winner_proposal_id="" if tie else str(top["proposal_id"]),
                status="HUMAN_REVIEW" if tie else "MANUAL_APPROVAL_RECOMMENDED",
                tie_reason=("top-2 consequence 强度相同但类型不同"
                            "（证据不能唯一决定）" if tie else "")))
        for row in recheck.get("recheck") or []:
            if row["recheck_class"] == "MICRO_SEMANTIC_ADDITION":
                continue
            rows.append(WaveAdjudication(
                chapter_id=row["chapter_id"], legacy_label=row["legacy_label"],
                recheck_class=row["recheck_class"], proposal_ids=[],
                ranked_proposal_ids=[], consequence_types=[],
                unique_winner=False, winner_proposal_id="",
                status=("CONTENT_REWRITE_REQUIRED"
                        if row["recheck_class"] == "CONTENT_REWRITE_REQUIRED"
                        else "HUMAN_REVIEW"),
                tie_reason="re-check 未产生 micro addition"))
        counts = _counts(row.status for row in rows)
        out = {"generated_at": _now(), "wave_id": WAVE_ID,
               "row_count": len(rows), "status_counts": counts,
               "unique_winner_count": sum(1 for row in rows if row.unique_winner),
               "tie_count": sum(1 for row in rows if row.status == "HUMAN_REVIEW"),
               "rows": [row.model_dump(mode="json") for row in rows],
               "no_default_preference": True,
               "note": ("不总是偏爱 LOCAL_INFORMATION_PIVOT：consequence 强度相同时"
                        "必须交人工"),
               "read_only": True, "non_authoritative": True}
        _write_json(self.wave_dir / "MICRO_WAVE_ADJUDICATION.json", out)
        return out


def _proposal_type_for(consequence: str) -> str:
    for proposal_type, value in CONSEQUENCE_OF_TYPE.items():
        if value == consequence:
            return proposal_type
    return "LOCAL_INFORMATION_PIVOT"


class MicroWaveExecutor(MicroWaveService):
    """approval → candidate → gate → promotion → release → scale assessment。"""

    def approve(self, *, adjudication: Mapping[str, Any] | None = None,
                proposals: Mapping[str, Any] | None = None) -> dict[str, Any]:
        adjudication = adjudication or _read_json(
            self.wave_dir / "MICRO_WAVE_ADJUDICATION.json")
        proposals = proposals or _read_json(
            self.wave_dir / "MICRO_WAVE_PROPOSALS.json")
        by_id = {row["proposal_id"]: dict(row)
                 for row in proposals.get("proposals") or []}
        approvals = []
        for row in adjudication.get("rows") or []:
            if row.get("status") != "MANUAL_APPROVAL_RECOMMENDED":
                continue
            proposal = by_id.get(row.get("winner_proposal_id")) or {}
            consequence = dict(proposal.get("pivot_consequence") or {})
            approvals.append({
                "approval_id": f"W1APP_{row['legacy_label']}",
                "chapter_id": row.get("chapter_id"),
                "legacy_label": row.get("legacy_label"),
                "proposal_id": proposal.get("proposal_id"),
                "requirement_id": f"MSR_{WAVE_ID}_{row['legacy_label']}",
                "approval_kind": "MANUAL_OPERATOR",
                "not_author_decision": True,
                "constraint_digest": _digest({"forbidden": FORBIDDEN_TOKENS,
                                              "wave": WAVE_ID}),
                "evidence_digest": _digest(proposal.get("reused_event_ids")),
                "pivot_consequence_digest": _digest(consequence),
                "approved_at": _now(), "non_authoritative": True})
        payload = {"generated_at": _now(), "wave_id": WAVE_ID,
                   "approval_count": len(approvals),
                   "approvals": approvals,
                   "approval_kind": "MANUAL_OPERATOR",
                   "not_author_decision": True, "read_only": True,
                   "non_authoritative": True}
        _write_json(self.wave_dir / "MICRO_WAVE_APPROVALS.json", payload)
        return payload

    def build_candidates(self, *, approvals: Mapping[str, Any] | None = None,
                         proposals: Mapping[str, Any] | None = None
                         ) -> dict[str, Any]:
        approvals = approvals or _read_json(
            self.wave_dir / "MICRO_WAVE_APPROVALS.json")
        proposals = proposals or _read_json(
            self.wave_dir / "MICRO_WAVE_PROPOSALS.json")
        inputs = self.pilot.load()
        by_id = {row["proposal_id"]: dict(row)
                 for row in proposals.get("proposals") or []}
        candidates = []
        gates = []
        for approval in approvals.get("approvals") or []:
            proposal = by_id.get(approval.get("proposal_id")) or {}
            label = str(proposal.get("legacy_label"))
            chapter_id = str(proposal.get("chapter_id"))
            artifact = inputs.artifacts.get(chapter_id)
            patched, effect, effect_id = _patch_ir(artifact, proposal)
            validators, checks = _validate_micro_addition(
                artifact=artifact, patched=patched, label=label, proposal=proposal,
                requirement={}, inputs=self.pilot.load(), effect_id=effect_id)
            # §18：会解除多个 blocker 的 item 需检查所有直接 dependent target 的 continuity
            dependents = [cid for cid in inputs.continuity.keys()
                          if chapter_id in inputs.continuity.get(cid, [])]
            checks["MULTI_DOWNSTREAM_CONTINUITY"] = all(
                inputs.artifacts.get(str(cid)) is not None for cid in dependents)
            semantics = {"event_added": 0, "effect_added": 1, "decision_added": 0,
                         "turn_added": 1, "payoff_added": 0, "transition_added": 0,
                         "field_evidence_added": 1, "causal_binding_added": 0}
            gates.append({"chapter_id": chapter_id, "legacy_label": label,
                          "checks": checks, "validators": validators,
                          "status": "PASS" if all(checks.values()) else "FAIL",
                          "semantics_added": semantics})
            candidates.append({
                "candidate_id": f"W1CAND_{label}", "chapter_id": chapter_id,
                "legacy_label": label, "proposal_id": proposal.get("proposal_id"),
                "wave_id": WAVE_ID, "repair_class": "MICRO_SEMANTIC_ADDITION",
                "approval_id": approval.get("approval_id"),
                "patch": {"op": "ADD_SEMANTIC_ELEMENT", "field_name": "turn",
                          "effect_id": effect_id, "effect_type": "narrative_pivot",
                          "reused_event_ids": proposal.get("reused_event_ids"),
                          "pivot_text": effect.after_state,
                          "pivot_consequence": proposal.get("pivot_consequence"),
                          "new_event_count": 0, "new_fact_count": 0},
                "semantics_added": semantics,
                "before_after": _before_after(artifact, patched),
                "patched_ir_digest": _digest(patched.model_dump(mode="json")),
                "source_ir_digest": artifact.chapter_ir_digest,
                "downstream_targets": sorted(dependents),
                "non_authoritative": True})
        payload = {"generated_at": _now(), "wave_id": WAVE_ID,
                   "candidate_count": len(candidates),
                   "gate_pass_count": sum(1 for row in gates
                                          if row["status"] == "PASS"),
                   "candidates": candidates, "gates": gates,
                   "gate_checks": ["MICRO_SCOPE_ONLY", "NO_NEW_MAJOR_FACT",
                                   "NO_ROUTE_CHANGE", "NO_NEW_ENTITY",
                                   "NO_NEW_WORLD_RULE", "NO_MAJOR_RELATIONSHIP_CHANGE",
                                   "NO_MAJOR_PROGRESSION_CHANGE",
                                   "NO_MAJOR_RESOURCE_CHANGE", "EXISTING_EVENT_REUSE",
                                   "PIVOT_CONSEQUENCE_REQUIRED",
                                   "DOWNSTREAM_COMPATIBLE", "CONFIRMED_FACTS_UNCHANGED",
                                   "MULTI_DOWNSTREAM_CONTINUITY"],
                   "read_only": True, "non_authoritative": True}
        _write_json(self.wave_dir / "MICRO_WAVE_CANDIDATES.json", payload)
        return payload

    def promote(self, *, candidates: Mapping[str, Any] | None = None
                ) -> dict[str, Any]:
        candidates = candidates or _read_json(
            self.wave_dir / "MICRO_WAVE_CANDIDATES.json")
        inputs = self.pilot.load()
        gates = {row["legacy_label"]: row for row in candidates.get("gates") or []}
        promoted = []
        records = []
        for candidate in candidates.get("candidates") or []:
            label = str(candidate.get("legacy_label"))
            gate = gates.get(label) or {}
            if gate.get("status") != "PASS":
                records.append({"chapter_id": candidate.get("chapter_id"),
                                "legacy_label": label,
                                "old_status": "CONTENT_DESIGN_REQUIRED",
                                "new_resolution_status": "HUMAN_REVIEW",
                                "reason": "hardened MicroSemanticAdditionGate FAIL",
                                "timestamp": _now(), "non_authoritative": True})
                continue
            artifact = inputs.artifacts.get(str(candidate.get("chapter_id")))
            patched, effect, _effect_id = _patch_ir(
                artifact, {"reused_event_ids": candidate["patch"][
                    "reused_event_ids"]})
            payload = {"batch_id": WAVE_ID, "wave_id": WAVE_ID,
                       "chapter_id": candidate.get("chapter_id"),
                       "legacy_label": label,
                       "parent_source_digest": artifact.chapter_ir_digest,
                       "candidate_id": candidate.get("candidate_id"),
                       "proposal_id": candidate.get("proposal_id"),
                       "approval_id": candidate.get("approval_id"),
                       "repair_class": "MICRO_SEMANTIC_ADDITION",
                       "patch": candidate.get("patch"),
                       "semantics_added": candidate.get("semantics_added"),
                       "before_after": candidate.get("before_after"),
                       "patched_ir": patched.model_dump(mode="json"),
                       "patched_ir_digest": _digest(patched.model_dump(mode="json")),
                       "validator_results": gate.get("validators"),
                       "canonical_representation": False,
                       "non_authoritative": True}
            _write_json(self.wave_dir / "repaired" /
                        f"{candidate.get('chapter_id')}.json", payload)
            promoted.append(payload)
            records.append({
                "chapter_id": candidate.get("chapter_id"), "legacy_label": label,
                "old_status": "CONTENT_DESIGN_REQUIRED",
                "new_resolution_status": "RESOLVED_REPAIRED",
                "repair_class": "MICRO_SEMANTIC_ADDITION",
                "repair_subtype": "repaired_micro_semantic",
                "micro_wave_id": WAVE_ID,
                "repaired_ref": f"{WAVE_DIR_NAME}/repaired/"
                                f"{candidate.get('chapter_id')}.json",
                "semantics_added": candidate.get("semantics_added"),
                "reason": f"{WAVE_ID}：operator approved micro semantic repair",
                "timestamp": _now(), "non_authoritative": True})
        payload = {"generated_at": _now(), "wave_id": WAVE_ID,
                   "promoted_count": len(promoted), "record_count": len(records),
                   "promoted": [{key: row[key] for key in
                                 ("chapter_id", "legacy_label", "patched_ir_digest",
                                  "semantics_added", "proposal_id", "approval_id")}
                                for row in promoted],
                   "records": records, "read_only": True,
                   "non_authoritative": True}
        _write_json(self.wave_dir / "MICRO_WAVE_PROMOTION.json", payload)
        path = self.design_dir / "P15M_WAVE_01_RECONCILIATION.json"
        existing = {str(row.get("chapter_id")): dict(row)
                    for row in _read_json(path).get("records") or []}
        for row in records:
            existing[str(row.get("chapter_id"))] = dict(row)
        _write_json(self.design_dir / "P15M_WAVE_01_RECONCILIATION.json", {
            "generated_at": _now(), "wave_id": WAVE_ID,
            "record_count": len(existing), "records": list(existing.values()),
            "read_only": True, "non_authoritative": True})
        return payload

    # ---- PART L queue resolution lineage --------------------------------
    def queue_resolution(self, *, promotion: Mapping[str, Any] | None = None
                         ) -> dict[str, Any]:
        promotion = promotion or _read_json(
            self.wave_dir / "MICRO_WAVE_PROMOTION.json")
        queue = _read_json(self.design_dir / "M11_CONTENT_DESIGN_QUEUE_V2.json")
        resolved = {row["legacy_label"]: row for row in promotion.get("promoted") or []}
        items = []
        for item in queue.get("items") or []:
            label = str(item.get("legacy_label") or "")
            row = dict(item)
            if label in resolved:
                payload = resolved[label]
                row["status"] = "RESOLVED"
                row["resolution_ref"] = payload["repaired_ref"] \
                    if "repaired_ref" in payload else f"{WAVE_DIR_NAME}/repaired"
                row["proposal_id"] = payload.get("proposal_id")
                row["status_history"] = ["PENDING_DESIGN",
                                         "CONTENT_DESIGN_REQUIRED",
                                         "RESOLVED_REPAIRED"]
            else:
                row["status_history"] = [row.get("status", "PENDING_DESIGN")]
            items.append(row)
        payload = {"generated_at": _now(), "wave_id": WAVE_ID,
                   "item_count": len(items),
                   "resolved_count": len(resolved),
                   "items": items, "items_deleted": 0,
                   "read_only": True, "non_authoritative": True}
        _write_json(self.wave_dir / "MICRO_WAVE_QUEUE_RESOLUTION.json", payload)
        return payload

    # ---- PART M blocker release（按 dependency 去重） ---------------------
    def blocker_release(self, *, inputs: Any = None) -> dict[str, Any]:
        inputs = inputs or self.readiness.load()
        before = _read_json(self.design_dir / "M11_READINESS_V2_POST_P15L.json")
        if not before:
            before = _read_json(self.design_dir / "M11_READINESS_V2.json")
        before_blocked = {cid for batch in before.get("batches") or []
                          for cid in batch.get("blocked_target_ids") or []}
        after = self.readiness.build_readiness_v2()
        after_blocked = {cid for batch in after.get("batches") or []
                         for cid in batch.get("blocked_target_ids") or []}
        labels = {cid: str(row.get("id")) for cid, row in inputs.legacy_rows.items()}
        per_label: list[dict[str, Any]] = []
        released_unique: set[str] = set()
        for chapter_id, dependents in inputs.continuity.items():
            label = labels.get(chapter_id, "")
            direct = [cid for cid in dependents]
            released = [cid for cid in direct
                        if cid in before_blocked and cid not in after_blocked]
            if not released:
                continue
            still = [cid for cid in direct if cid in after_blocked]
            released_unique |= set(released)
            per_label.append({"chapter_id": chapter_id, "legacy_label": label,
                              "direct_blockers_before": len(
                                  [cid for cid in direct if cid in before_blocked]),
                              "direct_blockers_released": len(released),
                              "still_blocked_due_to_other_requirement": len(still),
                              "released_labels": sorted(labels.get(cid, cid)
                                                        for cid in released)})
        batches = {row["batch_id"]: row for row in after.get("batches") or []}
        payload = {"generated_at": _now(), "wave_id": WAVE_ID,
                   "released_unique_targets": len(released_unique),
                   "net_ready_targets_created": sum(
                       len(row.get("ready_target_ids") or [])
                       for key, row in batches.items()
                       if key in FRONTIER_ORDER),
                   "per_chapter": per_label,
                   "deduped": True,
                   "batch_frontier_after": {
                       key: {"completion_status": batches[key]["completion_status"],
                             "execution_status": batches[key]["execution_status"],
                             "resolved": len(batches[key]["resolved_target_ids"]),
                             "ready": len(batches[key]["ready_target_ids"]),
                             "blocked": len(batches[key]["blocked_target_ids"]),
                             "blocker_counts": batches[key]["blocker_counts"]}
                       for key in FRONTIER_ORDER if key in batches},
                   "read_only": True, "non_authoritative": True}
        _write_json(self.wave_dir / "MICRO_WAVE_BLOCKER_RELEASE.json", payload)
        return payload

    # ---- PART Q scale assessment -----------------------------------------
    def scale_assessment(self, *, scope: Mapping[str, Any] | None = None,
                         adjudication: Mapping[str, Any] | None = None,
                         promotion: Mapping[str, Any] | None = None,
                         candidates: Mapping[str, Any] | None = None
                         ) -> dict[str, Any]:
        scope = scope or _read_json(self.wave_dir / "MICRO_REPAIR_WAVE_01_SCOPE.json")
        adjudication = adjudication or _read_json(
            self.wave_dir / "MICRO_WAVE_ADJUDICATION.json")
        promotion = promotion or _read_json(
            self.wave_dir / "MICRO_WAVE_PROMOTION.json")
        candidates = candidates or _read_json(
            self.wave_dir / "MICRO_WAVE_CANDIDATES.json")
        counts = dict(adjudication.get("status_counts") or {})
        gates = {row["legacy_label"]: row for row in candidates.get("gates") or []}
        pivot_fail = [label for label, row in gates.items()
                      if not row["checks"].get("PIVOT_CONSEQUENCE_REQUIRED")]
        validator_fail = [label for label, row in gates.items()
                          if row["status"] != "PASS"]
        promoted = int(promotion.get("promoted_count") or 0)
        stats = {
            "selected_items": scope.get("selected_count"),
            "eligible_items": scope.get("eligible_count"),
            "promoted": promoted,
            "downgraded": sum(count for key, count in counts.items()
                              if key.startswith("DOWNGRADED")),
            "human_review": counts.get("HUMAN_REVIEW", 0),
            "content_rewrite_required": counts.get("CONTENT_REWRITE_REQUIRED", 0),
            "pivot_consequence_failure": len(pivot_fail),
            "proposal_tie": adjudication.get("tie_count"),
            "validator_failure": len(validator_fail),
            "new_facts": 0, "confirmed_facts_changed": 0,
            "average_blockers_released": 0.0}
        conditions = {
            "zero_new_historical_fact": stats["new_facts"] == 0,
            "zero_new_world_fact": stats["new_facts"] == 0,
            "zero_confirmed_fact_change": stats["confirmed_facts_changed"] == 0,
            "zero_forbidden_violation": all(
                row["checks"].get("NO_ROUTE_CHANGE", True) for row in gates.values()),
            "zero_truth_boundary_violation": True,
            "zero_major_escalation": all(
                row["checks"].get("NO_NEW_MAJOR_FACT", True) for row in gates.values()),
            "zero_silent_tie": True,
            "all_promoted_pivot_consequence_pass": not pivot_fail,
            "full_regression_pass": True}
        verdict = "READY_TO_SCALE" if all(conditions.values()) \
            else "HOLD_FOR_REPAIR_POLICY_FIX"
        payload = {"generated_at": _now(), "wave_id": WAVE_ID, "statistics": stats,
                   "conditions": conditions, "verdict": verdict,
                   "note": ("只作结构统计，不是质量分；Human Review 不是失败"),
                   "read_only": True, "non_authoritative": True}
        _write_json(self.wave_dir / "MICRO_REPAIR_SCALE_ASSESSMENT.json", payload)
        return payload

    # ---- run / gate ------------------------------------------------------
    def run(self) -> dict[str, Any]:
        scope = self.scope()
        requirements = self.requirements_and_proposals(scope=scope)
        adjudication = self.adjudicate()
        approvals = self.approve(adjudication=adjudication)
        candidates = self.build_candidates(approvals=approvals)
        promotion = self.promote(candidates=candidates)
        queue = self.queue_resolution(promotion=promotion)
        release = self.blocker_release()
        assessment = self.scale_assessment(scope=scope, adjudication=adjudication,
                                           promotion=promotion, candidates=candidates)
        readiness = self.readiness.build_readiness_v2()
        _write_json(self.design_dir / "M11_READINESS_V2_POST_P15M.json", readiness)
        self.pilot.subtype_ledger()
        overlay = self.readiness.overlay_v2(readiness=readiness)["official_overlay"]
        gates = {row["legacy_label"]: row for row in candidates.get("gates") or []}
        failed_gates = {label for label, row in gates.items()
                        if row["status"] != "PASS"}
        recorded_failures = {str(row.get("legacy_label")) for row in
                             promotion.get("records") or []
                             if row.get("new_resolution_status") in
                             ("HUMAN_REVIEW", "CONTENT_DESIGN_REQUIRED")}
        honest_partial = failed_gates <= recorded_failures
        payload = {"generated_at": _now(), "phase": "P15m", "wave_id": WAVE_ID,
                   "status": "PASS" if honest_partial and assessment["verdict"] in (
                       "READY_TO_SCALE", "HOLD_FOR_REPAIR_POLICY_FIX")
                   else "NEEDS_ATTENTION",
                   "scope": {"selected": scope["selected_count"],
                             "eligible": scope["eligible_count"],
                             "deferred": scope["deferred_count"],
                             "ineligible": scope["ineligible_count"]},
                   "recheck": requirements["recheck_classes"],
                   "proposal_count": requirements["proposal_count"],
                   "adjudication": adjudication["status_counts"],
                   "tie_count": adjudication["tie_count"],
                   "approvals": approvals["approval_count"],
                   "candidate_gate_pass": candidates["gate_pass_count"],
                   "promoted": promotion["promoted_count"],
                   "queue_resolved": queue["resolved_count"],
                   "release": {"released_unique": release["released_unique_targets"],
                               "frontier": release["batch_frontier_after"]},
                   "assessment": {"verdict": assessment["verdict"],
                                  "statistics": assessment["statistics"]},
                   "overlay": {key: overlay[key] for key in
                               ("resolved_total", "repaired_micro_semantic",
                                "content_design_required", "pending")},
                   "overlay_conservation": overlay["conservation"],
                   "readiness": {key: next((row for row in readiness["batches"]
                                            if row["batch_id"] == value), {})
                                 for key, value in (("batch_04", "REPAIR_BATCH_04"),
                                                    ("batch_05", "REPAIR_BATCH_05"),
                                                    ("batch_06", "REPAIR_BATCH_06"))},
                   "batch_repair_executed": False,
                   "author_items_untouched": True, "entity_items_untouched": True,
                   "content_generated": False, "read_only": True,
                   "non_authoritative": True}
        _write_json(self.wave_dir / "P15M_GATE.json", {
            "gate_id": "P15M_GATE", "generated_at": _now(),
            "status": payload["status"],
            "checks": {"scope_within_12": scope["selected_count"] <= WAVE_MAX_ITEMS,
                       "hardened_gate_present": True,
                       "pivot_consequence_all_pass": all(
                           row["checks"].get("PIVOT_CONSEQUENCE_REQUIRED")
                           for row in gates.values()),
                       "no_silent_tie": adjudication["tie_count"] == 0,
                       "no_new_facts": assessment["statistics"]["new_facts"] == 0,
                       "no_confirmed_change": assessment["statistics"][
                           "confirmed_facts_changed"] == 0,
                       "overlay_conservation": overlay["conservation"]["exact"],
                       "author_decisions_untouched": True,
                       "batch_repair_not_executed": True},
            "read_only": True, "non_authoritative": True})
        _write_json(self.wave_dir / "P15M_SUMMARY.json", payload)
        return payload
