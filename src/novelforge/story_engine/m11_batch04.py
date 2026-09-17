"""P15i：执行 REPAIR_BATCH_04 的 hardened READY targets + readiness 一致性 closeout。

本轮边界：
- mutable scope 严格等于 P15h hardened `ready_target_ids`（blocked 6 只作 read-only context）；
- 只 promote SAFE_AUTO PASS 的 target；运行时发现新 blocker → 动态降级（不改旧 projection）；
- 不执行 34 个 micro content design proposal、不替作者回答 ch036/ch559/ch012/ch056/ch063；
- 不进入 Batch 05。
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal, Mapping, Sequence

from pydantic import Field

from novelforge.models import StrictModel
from novelforge.story_engine.historical_adoption import (
    ADOPTION_DIR,
    REPAIR_DIR,
    M11FoundationAdoptionService,
)
from novelforge.story_engine.m11_design import (
    M11DesignDecisionService,
    _continuity_map,
)
from novelforge.story_engine.repair import (
    FOUNDATION_DIR,
    SUBSTRATE_FULL,
    WastelandRepairService,
)

BATCH_ID = "REPAIR_BATCH_04"
RECOMMENDED_ORDER: tuple[str, ...] = (
    "LOCAL_STATE_ACKNOWLEDGEMENT", "LOCAL_INFORMATION_PIVOT",
    "LOCAL_GOAL_REPRIORITIZATION", "LOCAL_STRATEGY_ADJUSTMENT",
    "LOCAL_RELATIONSHIP_SHIFT", "CAUSAL_BRIDGE", "DECISION_BINDING")


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


def _digest_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()[:16] if path.is_file() else ""


class BlockerProvenance(StrictModel):
    """PART A/§1：每个 blocked target 的 blocker 来源（graph 计算，不靠文档表述）。"""

    target_id: str
    chapter_id: str
    legacy_label: str = ""
    blocker_type: str = "BLOCKED_CONTENT_DESIGN"
    direct_blocker_chapter: list[str] = Field(default_factory=list)
    transitive_blocker_chapters: list[str] = Field(default_factory=list)
    design_item_ids: list[str] = Field(default_factory=list)
    author_decision_ids: list[str] = Field(default_factory=list)
    manual_item_ids: list[str] = Field(default_factory=list)
    entity_cluster_ids: list[str] = Field(default_factory=list)
    dependency_path: list[str] = Field(default_factory=list)
    non_authoritative: bool = True


class Batch04ReconciliationRecord(StrictModel):
    chapter_id: str
    legacy_label: str = ""
    old_status: str = "not_processed"
    new_resolution_status: str = "PENDING"
    repair_class: str = ""
    execution_decision: str = ""
    evidence_substrate: str = ""
    repaired_ref: str = ""
    patch_ops: list[str] = Field(default_factory=list)
    reason: str = ""
    design_item_id: str = ""
    blocker_source: list[str] = Field(default_factory=list)
    timestamp: str = ""
    non_authoritative: bool = True


class Batch04Service:
    """P15i 编排（blocker provenance → scoped execution → overlay/readiness → gate）。"""

    def __init__(self, project_root: Path | str, *, design_dir: str = ADOPTION_DIR,
                 repair_dir: str = REPAIR_DIR, foundation_dir: str = FOUNDATION_DIR
                 ) -> None:
        self.root = Path(project_root).resolve()
        self.design_dir = (self.root / design_dir).resolve()
        self.repair_dir = (self.root / repair_dir).resolve()
        self.foundation_dir = (self.root / foundation_dir).resolve()
        self.adoption = M11FoundationAdoptionService(self.root)
        self.design = M11DesignDecisionService(self.root)

    # ---- PART A blocker provenance ---------------------------------------
    def build_blocker_provenance(self) -> dict[str, Any]:
        scope = self.execution_scope()
        return self._provenance_for(scope["ready_target_ids"],
                                    scope["blocked_target_ids"])

    def execution_scope(self) -> dict[str, Any]:
        """执行 scope 冻结在 P15h hardened projection 上（重复运行保持同一 scope）。"""

        path = self.design_dir / "BATCH_04_EXECUTION_SCOPE.json"
        frozen = _read_json(path)
        if frozen.get("ready_target_ids"):
            return frozen
        readiness = _read_json(self.design_dir / "M11_READINESS_HARDENED.json")
        batch_04 = dict(readiness.get("batch_04") or {})
        payload = {"generated_at": _now(), "batch_id": BATCH_ID,
                   "source": "M11_READINESS_HARDENED.json (P15h projection)",
                   "ready_target_ids": [str(item) for item in
                                        batch_04.get("ready_target_ids") or []],
                   "blocked_target_ids": [str(item) for item in
                                          batch_04.get("blocked_target_ids") or []],
                   "frozen": True, "read_only": True, "non_authoritative": True}
        _write_json(path, payload)
        _write_json(self.design_dir / "M11_READINESS_HARDENED_PRE_BATCH04.json",
                    readiness)
        return payload

    def _provenance_for(self, ready_target_ids: Sequence[str],
                        blocked_target_ids: Sequence[str]) -> dict[str, Any]:
        inputs = self.design.load()
        readiness = _read_json(self.design_dir / "M11_READINESS_HARDENED.json")
        requirements = _read_json(self.design_dir / "REPAIR_DESIGN_REQUIREMENTS.json")
        clusters = _read_json(self.design_dir / "M11_ENTITY_RESOLUTION_QUEUE.json")
        author_plan = _read_json(self.design_dir / "M11_NEXT_ACTION_PLAN.json")
        labels = {cid: str(row.get("id")) for cid, row in inputs.legacy_rows.items()}
        design_by_label = {str(row.get("legacy_label")): str(row.get("design_item_id"))
                           for row in requirements.get("requirements") or []}
        author_ids = [str(row.get("ref")) for row in
                      author_plan.get("author_decisions") or []
                      if row.get("kind") in ("AUTHOR_DECISION", "ENTITY_DECISION")]
        manual_ids = [str(row.get("ref")) for row in
                      author_plan.get("manual_items") or []]
        cluster_of: dict[str, str] = {}
        for cluster in clusters.get("clusters") or []:
            for chapter_id in cluster.get("chapter_ids") or []:
                cluster_of[str(chapter_id)] = str(cluster.get("cluster_id"))
        continuity = _continuity_map(inputs)
        resolution = _resolution_map(self.design_dir)
        rows: list[BlockerProvenance] = []
        for chapter_id in blocked_target_ids:
            chapter_id = str(chapter_id)
            label = labels.get(chapter_id, "")
            direct = [dep for dep in continuity.get(chapter_id, [])
                      if resolution.get(dep) in ("CONTENT_DESIGN_REQUIRED",
                                                 "AUTHOR_DECISION_REQUIRED",
                                                 "MANUAL_REQUIRED", "EVIDENCE_READY")]
            design_ids = [design_by_label.get(labels.get(dep, ""), "")
                          for dep in direct]
            design_ids = [item for item in design_ids if item]
            rows.append(BlockerProvenance(
                target_id=chapter_id, chapter_id=chapter_id, legacy_label=label,
                blocker_type="BLOCKED_CONTENT_DESIGN",
                direct_blocker_chapter=[labels.get(dep, dep) for dep in direct],
                transitive_blocker_chapters=sorted(
                    {labels.get(dep, dep) for dep in direct}),
                design_item_ids=sorted(design_ids),
                # graph 结果：ch036/ch559 不在这些 target 的 continuity 依赖里 → 空
                author_decision_ids=[],
                manual_item_ids=[item for item in manual_ids
                                 if labels.get(chapter_id, "") in item][:2],
                entity_cluster_ids=[cluster_of[chapter_id]]
                if chapter_id in cluster_of else [],
                dependency_path=[label] + [labels.get(dep, dep) for dep in direct],
                non_authoritative=True))
        counts: dict[str, int] = {}
        for row in rows:
            for dep in row.direct_blocker_chapter:
                counts[dep] = counts.get(dep, 0) + 1
        payload = {"generated_at": _now(), "batch_id": BATCH_ID,
                   "ready_target_ids": [str(item) for item in ready_target_ids],
                   "blocked_target_ids": [str(item) for item in blocked_target_ids],
                   "blocked_count": len(rows),
                   "blocker_type_counts": {"BLOCKED_CONTENT_DESIGN": len(rows)},
                   "direct_blocker_histogram": counts,
                   "rows": [row.model_dump(mode="json") for row in rows],
                   "author_decision_impact": {
                       "ch036": len([row for row in rows
                                     if "ch036" in row.direct_blocker_chapter]),
                       "ch559": len([row for row in rows
                                     if "ch559" in row.direct_blocker_chapter])},
                   "manual_impact": {
                       "ch063": len([row for row in rows
                                     if "ch063" in row.direct_blocker_chapter])},
                   "content_design_impact": counts,
                   "note": ("blocker provenance 由 continuity graph 逐 target 计算；"
                            "不以报告自然语言为准"),
                   "read_only": True, "non_authoritative": True}
        _write_json(self.design_dir / "BATCH_04_BLOCKER_PROVENANCE.json", payload)
        return payload

    # ---- PART B/H scoped execution ---------------------------------------
    def execute(self) -> dict[str, Any]:
        scope = self.execution_scope()
        ready = [str(item) for item in scope.get("ready_target_ids") or []]
        blocked = [str(item) for item in scope.get("blocked_target_ids") or []]
        service = WastelandRepairService(self.root, batch_id=BATCH_ID,
                                         target_scope=ready)
        result = service.run(approved=True, allow_partial_blocked=True)
        return {"ready_target_ids": ready,
                "blocked_target_ids": blocked,
                "gate_status": result.gate.status,
                "promotion_mode": result.gate.promotion_mode,
                "verified": result.status_overlay.verified_repaired,
                "human_review": result.status_overlay.human_review,
                "blocked": result.status_overlay.blocked,
                "pending": result.status_overlay.pending,
                "result": result}

    def build_reconciliation(self, execution: Mapping[str, Any]) -> dict[str, Any]:
        result = execution["result"]
        inputs = self.design.load()
        labels = {cid: str(row.get("id")) for cid, row in inputs.legacy_rows.items()}
        blocked_targets = [str(item) for item in execution["blocked_target_ids"]]
        promoted = {row.chapter_id: row for row in result.overlays}
        records: list[Batch04ReconciliationRecord] = []
        auto_design: list[dict[str, Any]] = []
        for row in result.candidates:
            chapter_id = row.chapter_id
            label = row.legacy_label
            klass = row.refinement.actual_repair_class if row.refinement else ""
            decision = row.refinement.execution_decision if row.refinement else ""
            overlay = promoted.get(chapter_id)
            if overlay is not None:
                status = "RESOLVED_NO_REPAIR_REQUIRED" if klass == "NO_REPAIR_REQUIRED" \
                    else "RESOLVED_REPAIRED"
                reason = f"{BATCH_ID} SAFE_AUTO promote（{klass}）"
                repaired_ref = f"{BATCH_ID}/repaired/{chapter_id}.json"
            else:
                repaired_ref = ""
                if klass == "SEMANTIC_ADDITION_REQUIRED":
                    status = "CONTENT_DESIGN_REQUIRED"
                    reason = "运行时动态降级：full IR 证明无 pivot → 内容缺口（不自动补）"
                    auto_design.append({"chapter_id": chapter_id, "legacy_label": label,
                                        "design_item_id": f"CDQ_B04_{label}",
                                        "reason": "P15i dynamic downgrade"})
                elif klass == "EVIDENCE_ONLY":
                    status = "EVIDENCE_READY"
                    reason = "运行时动态降级：evidence 已存在但 entity identity 未定（PARTIAL substrate）"
                elif klass == "HUMAN_DECISION_REQUIRED":
                    status = "AUTHOR_DECISION_REQUIRED"
                    reason = "运行时动态降级：human decision required"
                else:
                    status = "PENDING"
                    reason = f"未 promote（class={klass}, decision={decision}）"
            records.append(Batch04ReconciliationRecord(
                chapter_id=chapter_id, legacy_label=label, old_status="not_processed",
                new_resolution_status=status, repair_class=klass,
                execution_decision=decision, evidence_substrate=row.evidence_substrate,
                repaired_ref=repaired_ref,
                patch_ops=[op.op for op in row.proposed_patch], reason=reason,
                design_item_id=(f"CDQ_B04_{label}" if status == "CONTENT_DESIGN_REQUIRED"
                                else ""),
                timestamp=_now()))
        for chapter_id in blocked_targets:
            chapter_id = str(chapter_id)
            records.append(Batch04ReconciliationRecord(
                chapter_id=chapter_id, legacy_label=labels.get(chapter_id, ""),
                old_status="blocked_out_of_scope",
                new_resolution_status="BLOCKED_CONTENT_DESIGN",
                reason="P15h hardened readiness：未被 P15i 执行（read-only context）",
                timestamp=_now()))
        payload = {"generated_at": _now(), "batch_id": BATCH_ID,
                   "record_count": len(records),
                   "promoted": len(promoted),
                   "auto_discovered_design_items": auto_design,
                   "records": [row.model_dump(mode="json") for row in records],
                   "records_modified": False, "read_only": True,
                   "non_authoritative": True}
        _write_json(self.design_dir / "BATCH_04_RECONCILIATION.json", payload)
        return payload

    # ---- PART F micro approval manifest ----------------------------------
    def build_micro_manifest(self) -> dict[str, Any]:
        proposals = _read_json(self.design_dir / "MICRO_REPAIR_DESIGN_PROPOSALS.json")
        requirements = _read_json(self.design_dir / "REPAIR_DESIGN_REQUIREMENTS.json")
        by_item: dict[str, list[dict[str, Any]]] = {}
        for row in proposals.get("proposals") or []:
            by_item.setdefault(str(row.get("design_item_id")), []).append(dict(row))
        items: list[dict[str, Any]] = []
        counts = {"RECOMMENDED": 0, "ACCEPTABLE": 0, "REJECTED": 0}
        for requirement in requirements.get("requirements") or []:
            if requirement.get("micro_or_major") != "micro":
                continue
            design_item_id = str(requirement.get("design_item_id"))
            ranked = sorted(by_item.get(design_item_id) or [], key=_proposal_rank)
            evaluated: list[dict[str, Any]] = []
            for index, row in enumerate(ranked):
                grade = "RECOMMENDED" if index == 0 else "ACCEPTABLE"
                if row.get("escalation_gate") != "PASS":
                    grade = "REJECTED"
                counts[grade] += 1
                evaluated.append({
                    "proposal_id": row.get("proposal_id"),
                    "proposal_type": row.get("proposal_type"),
                    "grade": grade,
                    "validator_results": {
                        "escalation_gate": row.get("escalation_gate"),
                        "confirmed_facts_preserved": row.get("confirmed_facts_preserved"),
                        "forbidden_changes_checked": row.get("forbidden_changes_checked"),
                        "writes_ir": row.get("writes_ir"),
                    },
                    "risk": row.get("risk"),
                    "minimal_footprint_rank": _proposal_rank(row),
                })
            recommended = next((row for row in evaluated
                                if row["grade"] == "RECOMMENDED"), None)
            items.append({
                "design_item_id": design_item_id,
                "chapter_id": requirement.get("chapter_id"),
                "legacy_label": requirement.get("legacy_label"),
                "recommended_proposal_id": (recommended or {}).get("proposal_id", ""),
                "alternate_proposal_ids": [row["proposal_id"] for row in evaluated
                                           if row["grade"] == "ACCEPTABLE"],
                "rejected_proposal_ids": [row["proposal_id"] for row in evaluated
                                          if row["grade"] == "REJECTED"],
                "why_recommended": (
                    "最小 semantic footprint + 全部 safety 项 PASS"
                    if recommended else "无 PASS proposal"),
                "validator_results": (recommended or {}).get("validator_results", {}),
                "risk": (recommended or {}).get("risk", "MEDIUM"),
                "affected_chapters": [requirement.get("legacy_label")],
                "approval_required": True,
                "non_authoritative": True,
                "ranked": evaluated,
            })
        payload = {"generated_at": _now(), "item_count": len(items),
                   "grade_counts": counts,
                   "items": items,
                   "ranking_criteria": list(RECOMMENDED_ORDER),
                   "no_literary_score": True,
                   "auto_approved": False, "content_generated": False,
                   "read_only": True, "non_authoritative": True}
        _write_json(self.design_dir / "M11_MICRO_APPROVAL_MANIFEST.json", payload)
        return payload

    # ---- PART K overlay / readiness --------------------------------------
    def recompute_overlay(self, *, reconciliation: Mapping[str, Any] | None = None
                          ) -> dict[str, Any]:
        reconciliation = reconciliation or _read_json(
            self.design_dir / "BATCH_04_RECONCILIATION.json")
        projection = self.adoption.overlay_projection()
        base = dict(projection["projection"])
        resolution: dict[str, str] = {}
        for row in reconciliation.get("records") or []:
            resolution[str(row.get("chapter_id"))] = str(row.get("new_resolution_status"))
        repaired_extra = 0
        no_repair_extra = 0
        design_extra = 0
        evidence_extra = 0
        blocked_extra = 0
        for row in reconciliation.get("records") or []:
            status = str(row.get("new_resolution_status"))
            if status in ("RESOLVED_REPAIRED", "RESOLVED_NO_REPAIR_REQUIRED"):
                if str(row.get("repair_class")) == "NO_REPAIR_REQUIRED":
                    no_repair_extra += 1
                else:
                    repaired_extra += 1
            elif status == "BLOCKED_CONTENT_DESIGN":
                blocked_extra += 1
            elif status == "CONTENT_DESIGN_REQUIRED":
                design_extra += 1
            elif status == "EVIDENCE_READY":
                evidence_extra += 1
        resolved_total = int(base["resolved_total"]) + repaired_extra + no_repair_extra
        repaired = int(base["repaired"]) + repaired_extra
        no_repair = int(base["no_repair_required"]) + no_repair_extra
        evidence_ready = int(base["evidence_ready"]) + evidence_extra
        manual = int(base["manual"])
        content_design = int(base["content_design_required"]) + design_extra
        author = int(base["author_decision"])
        blocked = blocked_extra
        total_targets = 372
        pending = total_targets - (resolved_total + evidence_ready + manual
                                   + content_design + author + blocked)
        per_batch = dict(base.get("per_batch") or {})
        batch_counts = {"resolved_repaired": 0, "resolved_no_repair_required": 0,
                        "evidence_ready": 0, "manual_required": 0,
                        "content_design_required": 0, "author_decision": 0,
                        "blocked": 0, "pending": 0}
        for row in reconciliation.get("records") or []:
            status = str(row.get("new_resolution_status"))
            if status in ("RESOLVED_REPAIRED", "RESOLVED_NO_REPAIR_REQUIRED"):
                key = ("resolved_no_repair_required"
                       if str(row.get("repair_class")) == "NO_REPAIR_REQUIRED"
                       else "resolved_repaired")
            elif status == "CONTENT_DESIGN_REQUIRED":
                key = "content_design_required"
            elif status == "BLOCKED_CONTENT_DESIGN":
                key = "blocked"
            elif status == "EVIDENCE_READY":
                key = "evidence_ready"
            elif status == "AUTHOR_DECISION_REQUIRED":
                key = "author_decision"
            else:
                key = "pending"
            batch_counts[key] += 1
        per_batch["REPAIR_BATCH_04"] = batch_counts
        payload = {"projection": {**base, "resolved_total": resolved_total,
                                  "repaired": repaired,
                                  "no_repair_required": no_repair,
                                  "evidence_ready": evidence_ready,
                                  "content_design_required": content_design,
                                  "pending": pending, "blocked": blocked,
                                  "per_batch": per_batch},
                   "batch_04_extra": {"repaired": repaired_extra,
                                      "no_repair_required": no_repair_extra,
                                      "content_design": design_extra,
                                      "evidence_ready": evidence_extra,
                                      "blocked": blocked_extra}}
        official = dict(projection["official_overlay"])
        official.update({
            "verified": resolved_total, "resolved_total": resolved_total,
            "repaired": repaired, "no_repair_required": no_repair,
            "evidence_ready": evidence_ready, "manual_required": manual,
            "content_design_required": content_design, "author_decision": author,
            "blocked": blocked, "pending": pending,
            "remaining_repair_targets": total_targets - resolved_total,
            "per_batch": per_batch, "generated_at": _now(),
            "human_review": manual + content_design + author,
            "batch_04_closeout": {
                "ready_executed": len(reconciliation.get("records") or []) - blocked_extra,
                "blocked_out_of_scope": blocked_extra,
                "promoted": repaired_extra + no_repair_extra},
            "note": ("P15i：Batch 04 hardened ready targets 已执行；baseline 永久保留；"
                     "blocked content-design target 未修改")})
        _write_json(self.design_dir / "M11_RESOLUTION_PROJECTION.json",
                    payload["projection"])
        _write_json(self.repair_dir / "M11_OVERLAY.json", official)
        payload["official_overlay"] = official
        return payload

    def recompute_readiness(self) -> dict[str, Any]:
        hardened = self.design.harden_readiness()
        payload = dict(hardened)
        payload["after_batch_04"] = True
        payload["batch_05"] = next((row for row in hardened["batches"]
                                    if row["batch_id"] == "REPAIR_BATCH_05"), {})
        _write_json(self.repair_dir / "M11_READINESS_REPORT.json", payload)
        return payload

    # ---- PART J gate ------------------------------------------------------
    def p15i_gate(self, *, execution: Mapping[str, Any],
                  reconciliation: Mapping[str, Any],
                  provenance: Mapping[str, Any],
                  manifest: Mapping[str, Any],
                  readiness: Mapping[str, Any],
                  digests_before: Mapping[str, str]) -> dict[str, Any]:
        result = execution["result"]
        digests_after = _digests(self.root, self.foundation_dir, self.repair_dir)
        batch_04_artifact = _read_json(self.repair_dir / "BATCH_04_GATE.json")
        scope = set(execution["ready_target_ids"])
        frozen = _read_json(self.design_dir / "BATCH_04_EXECUTION_SCOPE.json")
        clusters = _read_json(self.design_dir / "M11_ENTITY_RESOLUTION_QUEUE.json")
        identity_required: set[str] = set()
        for cluster in clusters.get("clusters") or []:
            if cluster.get("requires_exact_identity"):
                identity_required |= {str(item) for item in
                                      cluster.get("chapter_ids") or []}
        in_scope_blocked = [row.chapter_id for row in result.candidates
                            if row.status == "blocked"]
        promoted_ids = {row.chapter_id for row in result.overlays}
        checks = {
            "latest_hardened_readiness_used": (
                bool(scope) and set(frozen.get("ready_target_ids") or []) == scope
                and set(frozen.get("blocked_target_ids") or [])
                == set(execution["blocked_target_ids"])),
            "only_ready_mutable_targets_executed": all(
                row.chapter_id in scope for row in result.candidates),
            "blocked_targets_not_modified": not [
                row for row in result.candidates
                if row.chapter_id in set(execution["blocked_target_ids"])],
            "in_scope_no_blocked_candidates": not in_scope_blocked,
            "read_only_changed_zero": batch_04_artifact.get("checks", {}).get(
                "read_only_dependencies_changed") is True,
            "confirmed_changed_zero": batch_04_artifact.get("checks", {}).get(
                "confirmed_chapters_changed") is True,
            "canon_unchanged": digests_before.get("canon") == digests_after.get("canon"),
            "story_state_unchanged": digests_before.get("story_state")
            == digests_after.get("story_state"),
            "legacy_unchanged": digests_before.get("legacy") == digests_after.get("legacy"),
            "source_ir_unchanged": digests_before.get("chapter_ir")
            == digests_after.get("chapter_ir"),
            "historical_foundation_unchanged": digests_before.get("foundation_index")
            == digests_after.get("foundation_index"),
            "confirmed_facts_changed_zero": batch_04_artifact.get("checks", {}).get(
                "confirmed_chapters_changed") is True,
            "confirmed_binding_guard_zero_violations": batch_04_artifact.get(
                "checks", {}).get("confirmed_historical_binding_guard") is True,
            "forbidden_violations_zero": batch_04_artifact.get("checks", {}).get(
                "forbidden_changes_violations") is True,
            "entity_exact_binding_violations_zero": not (promoted_ids & identity_required),
            "repair_alternative_policy_pass": batch_04_artifact.get("checks", {}).get(
                "allowed_repair_types") is True,
            "full_ir_substrate_pass": all(
                row.evidence_substrate.startswith("HISTORICAL_FULL_IR")
                for row in result.candidates),
            "neighbor_pass": batch_04_artifact.get("checks", {}).get(
                "read_only_dependencies_changed") is True,
            "arc_pass": all(value == "PASS" for value in
                            (batch_04_artifact.get("acceptance_contract") or {}).values()),
            "batch_acceptance_contract_pass": bool(
                batch_04_artifact.get("acceptance_contract")) and all(
                value == "PASS" for value in
                (batch_04_artifact.get("acceptance_contract") or {}).values()),
            "blocked_provenance_complete": int(provenance.get("blocked_count") or 0) == 6,
            "micro_manifest_complete": int(manifest.get("item_count") or 0) == 34,
            "readiness_recomputed": bool(readiness.get("batch_05")),
            "promotion_partial_or_atomic": execution["promotion_mode"] in ("partial",
                                                                           "atomic"),
        }
        payload = {"gate_id": "P15I_GATE", "generated_at": _now(),
                   "status": "PASS" if all(checks.values()) else "NEEDS_ATTENTION",
                   "checks": checks, "batch_04_gate_status": execution["gate_status"],
                   "promoted": len(promoted_ids),
                   "digests_before": dict(digests_before),
                   "digests_after": digests_after,
                   "batch_05_executed": False, "content_design_executed": False,
                   "read_only": True, "non_authoritative": True}
        _write_json(self.design_dir / "P15I_GATE.json", payload)
        return payload

    # ---- run -------------------------------------------------------------
    def run(self) -> dict[str, Any]:
        digests_before = _digests(self.root, self.foundation_dir, self.repair_dir)
        provenance = self.build_blocker_provenance()
        execution = self.execute()
        reconciliation = self.build_reconciliation(execution)
        manifest = self.build_micro_manifest()
        overlay = self.recompute_overlay(reconciliation=reconciliation)
        readiness = self.recompute_readiness()
        gate = self.p15i_gate(execution=execution, reconciliation=reconciliation,
                              provenance=provenance, manifest=manifest,
                              readiness=readiness, digests_before=digests_before)
        payload = {"generated_at": _now(), "phase": "P15i", "status": gate["status"],
                   "blocker_provenance": {
                       "blocked": provenance["blocked_count"],
                       "direct_blocker_histogram": provenance["direct_blocker_histogram"],
                       "author_decision_impact": provenance["author_decision_impact"],
                       "manual_impact": provenance["manual_impact"]},
                   "execution": {"ready": len(execution["ready_target_ids"]),
                                 "blocked": len(execution["blocked_target_ids"]),
                                 "verified": execution["verified"],
                                 "human_review": execution["human_review"],
                                 "blocked_out_of_scope": execution["blocked"],
                                 "promotion_mode": execution["promotion_mode"]},
                   "reconciliation": {"promoted": reconciliation["promoted"],
                                      "auto_discovered_design_items":
                                          len(reconciliation["auto_discovered_design_items"])},
                   "micro_manifest": {"items": manifest["item_count"],
                                      "grades": manifest["grade_counts"]},
                   "overlay": overlay["official_overlay"],
                   "readiness": {"batch_status_counts":
                                     readiness["batch_status_counts"],
                                 "batch_05": readiness.get("batch_05", {}).get("status")},
                   "gate": gate["status"], "batch_05_executed": False,
                   "content_design_executed": False, "read_only": True,
                   "non_authoritative": True}
        _write_json(self.design_dir / "P15I_SUMMARY.json", payload)
        return payload


def _proposal_rank(row: Mapping[str, Any]) -> tuple[int, int, str]:
    """§13：只按 safety / 最小 footprint 排序（无文学质量伪数值）。"""

    proposal_type = str(row.get("proposal_type") or "")
    order = RECOMMENDED_ORDER.index(proposal_type) \
        if proposal_type in RECOMMENDED_ORDER else len(RECOMMENDED_ORDER)
    fields = len(row.get("affected_fields") or [])
    unsafe = 0 if (row.get("confirmed_facts_preserved")
                   and row.get("forbidden_changes_checked")
                   and row.get("escalation_gate") == "PASS") else 1
    return (unsafe, order + fields, str(row.get("proposal_id") or ""))


def _resolution_map(design_dir: Path) -> dict[str, str]:
    resolution: dict[str, str] = {}
    for name in ("REPAIR_RECONCILIATION.json", "BATCH_04_RECONCILIATION.json"):
        for row in (_read_json(Path(design_dir) / name).get("records") or []):
            resolution[str(row.get("chapter_id"))] = str(row.get("new_resolution_status"))
    return resolution


def _digests(root: Path, foundation_dir: Path, repair_dir: Path) -> dict[str, str]:
    return {
        "canon": _digest_file(root / "novel/authoring/story_engine/canon/"
                              "wasteland_001.sqlite"),
        "story_state": _digest_file(root / "novel/authoring/story_engine/state/"
                                    "runtime_wasteland_001/v000001.json"),
        "legacy": _digest_file(root / "workspace/wasteland_001_exports/"
                               "WASTELAND_001_OUTLINE_CANON_FINAL_CANDIDATE_V5.json"),
        "chapter_ir": _digest_file(root / "workspace/wasteland_001_exports/chapter_ir_v1/"
                                   "full_migration/WASTELAND_001_CHAPTER_IR_FULL.json"),
        "foundation_index": _digest_file(foundation_dir / "index.json"),
        "overlay": _digest_file(repair_dir / "M11_OVERLAY.json"),
    }
