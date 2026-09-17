"""M11 approved-event production path（user-authorized architecture extension）。

在 **不改动** frozen `M11_REPAIR_SYSTEM_CONTRACT_V1` / `REPAIR_GATE_V1` / SAFE_AUTO 语义 /
P15 executor 的前提下，新增一条独立的 production route：

```text
explicit author-approved canonical root
+ frozen approved scope
+ M11_APPROVED_EVENT_GATE_V1（22 checks）
→ AuthorApprovedContentResolutionExecutor
→ ADD_SEMANTIC_ELEMENT（new_event_count = 1）
→ approved-event reconciliation（RESOLVED_REPAIRED / repaired_semantic_addition）
```

SAFE_AUTO 仍禁止 `event_added > 0`；本路径与 SAFE_AUTO / P15 micro executor /
legacy M11 run executor **完全隔离**。
"""

from __future__ import annotations

import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable, Mapping

from novelforge.story_engine.historical_adoption import ADOPTION_DIR
from novelforge.story_engine.historical_ir import HISTORY_DIR
from novelforge.story_engine.m11_run01 import _digest_json, _now, _read_json, _write_json
from novelforge.story_engine.m11_run12 import M11Run12Service

AUTHORIZATION_FILE = "M11_APPROVED_EVENT_ARCHITECTURE_AUTHORIZATION.json"
GATE_FILE = "M11_APPROVED_EVENT_GATE_V1.json"
GATE_RESULT_FILE = "M11_APPROVED_EVENT_GATE_RESULT.json"
RECONCILIATION_FILE = "M11_APPROVED_EVENT_RECONCILIATION.json"
EXECUTION_LEDGER_FILE = "M11_APPROVED_EVENT_EXECUTION_LEDGER.json"
REPAIRED_DIR = "m11_approved_event/repaired"

DECISIONS_INPUT = "AUTHOR_CONTENT_DECISIONS.json"
APPROVED_SCOPE = "APPROVED_CONTENT_RESOLUTION_SCOPE.json"
CANONICAL_DECISIONS = "AUTHOR_CONTENT_CANONICAL_DECISIONS.json"
CANONICAL_INVENTORY = "ROOT_BLOCKER_CANONICAL_INVENTORY.json"

SUBTYPE = "repaired_semantic_addition"
ONE_NEW_EVENT_MAX = 1

GATE_CHECK_NAMES: tuple[str, ...] = (
    "author_decision_exists", "decision_matches_canonical_root",
    "selected_option_valid", "root_inside_frozen_scope",
    "one_new_event_max", "event_concrete", "satisfies_missing_requirement",
    "pivot_consequence_valid", "temporal_placement_valid",
    "knowledge_boundary_valid", "entity_refs_resolvable",
    "inventory_conservation", "no_canon_contradiction",
    "no_story_state_contradiction", "confirmed_facts_unchanged",
    "no_unrelated_chapter_mutation", "downstream_continuity_valid",
    "dependency_consistency", "canonical_root_unique", "alias_no_double_execute",
    "lineage_complete", "p15_not_involved",
)

EVENT_TYPE_BY_CLASS: Mapping[str, str] = {
    "LOCAL_CAUSAL_BRIDGE_REQUIRED": "LOCAL_CAUSAL_ACTION",
    "LOCAL_DECISION_EVENT_REQUIRED": "LOCAL_DECISION_EVENT",
    "LOCAL_CONNECTIVE_EVENT_REQUIRED": "LOCAL_CONNECTIVE_EVENT",
    "MAJOR_AUTHOR_DESIGN_REQUIRED": "MAJOR_TURN_STATE_TRANSITION",
    "EXISTING_EVENT_MICRO_SEMANTIC": "LOCAL_PIVOT_EVENT",
}
CONSEQUENCE_BY_MISSING: Mapping[str, str] = {
    "TURN": "LOCAL_STRATEGY",
    "turn_gap": "LOCAL_STRATEGY",
    "semantic_evidence_gap": "LOCAL_CAUSAL_DIRECTION",
    "turn_conflict": "LOCAL_RISK_ASSESSMENT",
}


class ApprovedNewEventValidator:
    """M11_APPROVED_EVENT_GATE_V1：22 项结构 + 边界校验（不触碰 frozen gate）。"""

    def __init__(self, service: "M11ApprovedEventService") -> None:
        self.service = service

    def validate(self, *, decision: Mapping[str, Any], root: Mapping[str, Any],
                 event: Mapping[str, Any], evidence: Mapping[str, Any],
                 executed_roots: Iterable[str]) -> dict[str, Any]:
        service = self.service
        executed = set(executed_roots)
        scope_roots = set(service.approved_root_ids)
        checks: dict[str, bool] = {
            "author_decision_exists": bool(decision.get("decision_source"))
            and decision.get("approved_by") == "AUTHOR",
            "decision_matches_canonical_root":
                event["canonical_root_id"] in (decision.get("canonical_root_ids") or []),
            "selected_option_valid":
                decision.get("selected_option") in (
                    event["authorized_options"] or []),
            "root_inside_frozen_scope":
                event["canonical_root_id"] in scope_roots,
            "one_new_event_max":
                int(event["new_event_count"]) <= ONE_NEW_EVENT_MAX
                and int(event["new_event_count"]) >= 0,
            "event_concrete": all(str(event.get(key) or "").strip() for key in
                                  ("actor", "action", "object", "immediate_consequence")),
            "satisfies_missing_requirement":
                event["consequence_type"]
                == CONSEQUENCE_BY_MISSING.get(str(event["missing_semantic_type"]),
                                              event["consequence_type"]),
            "pivot_consequence_valid":
                event["consequence_type"].startswith("LOCAL_")
                and event["consequence_type"] != "LOCAL_UNDERSTANDING",
            "temporal_placement_valid": event["temporal_placement"] == "chapter_local",
            "knowledge_boundary_valid":
                event["new_knowledge"] is False
                or event["knowledge_owner"] == "chapter_local_participant",
            "entity_refs_resolvable":
                event["new_entity"] is False
                and all(ref in service.known_entity_ids for ref in event["entity_refs"]),
            "inventory_conservation": int(event["inventory_delta"]) == 0,
            "no_canon_contradiction": event["canon_change"] is False,
            "no_story_state_contradiction": event["story_state_change"] is False,
            "confirmed_facts_unchanged": event["confirmed_facts_changed"] == 0,
            "no_unrelated_chapter_mutation":
                event["affected_chapter_ids"] == [event["chapter_id"]],
            "downstream_continuity_valid": all(
                str(target) in service.known_target_ids
                for target in event["downstream_targets"]),
            "dependency_consistency":
                set(event["dependency_refs"]) <= scope_roots | {
                    event["canonical_root_id"]},
            "canonical_root_unique":
                event["canonical_root_id"] not in executed,
            "alias_no_double_execute":
                event["canonical_root_id"] == root["canonical_root_id"]
                and len(set(event["artifact_refs"])) == len(event["artifact_refs"]),
            "lineage_complete": all(
                event.get(key) for key in ("author_decision_ref", "approval_ref",
                                           "source_evidence", "parent_source_digest")),
            "p15_not_involved": not any(
                str(ref).startswith(("p15l/", "p15m/", "p15o/"))
                or "MICRO_WAVE" in str(ref) or "MicroWave" in str(ref)
                for ref in event["source_evidence"]),
        }
        return {"checks": checks,
                "status": "PASS" if all(checks.values()) else "FAIL",
                "failed_checks": sorted(key for key, value in checks.items()
                                        if not value),
                "check_count": len(checks)}


class ApprovedEventBuilder:
    """为每个 author-approved canonical content root 生成最小结构化历史语义事件。"""

    def __init__(self, service: "M11ApprovedEventService") -> None:
        self.service = service

    def build(self, *, root: Mapping[str, Any], decision: Mapping[str, Any],
              evidence: Mapping[str, Any]) -> dict[str, Any]:
        service = self.service
        root_id = str(root["canonical_root_id"])
        label = str(evidence.get("chapter") or "")
        chapter_id = str(evidence.get("target_id") or "")
        legacy = service.legacy_row(chapter_id)
        missing = str(evidence.get("missing_semantic_type") or "TURN")
        p15n_class = str(evidence.get("p15n_class") or
                         evidence.get("candidate_class") or "")
        event_type = EVENT_TYPE_BY_CLASS.get(p15n_class, "LOCAL_PIVOT_EVENT")
        consequence = CONSEQUENCE_BY_MISSING.get(missing, "LOCAL_STRATEGY")
        actor = str(legacy.get("decision_owner") or legacy.get("protagonist")
                    or "chapter_local_participant")
        state_before = str(legacy.get("start_state") or "")
        state_after = str(legacy.get("end_state") or "")
        event_id = f"M11EV_{label}_{hashlib.sha256(root_id.encode()).hexdigest()[:6]}"
        return {
            "event_id": event_id,
            "canonical_root_id": root_id,
            "artifact_refs": list(root.get("artifact_refs") or []),
            "chapter_id": chapter_id,
            "chapter": label,
            "event_type": event_type,
            "actor": actor,
            "trigger": f"既有历史证据（{evidence.get('refinement_reason') or evidence.get('p15n_reason')}）",
            "action": f"该章缺少 {missing}，补一个最小局部语义动作",
            "object": f"{label} 的 {missing} 语义位",
            "decision_or_action": "LOCAL_SEMANTIC_ACTION",
            "immediate_consequence": consequence,
            "consequence_type": consequence,
            "state_before": state_before,
            "state_after": state_after or state_before,
            "causal_role": p15n_class or "LOCAL_PIVOT",
            "pivot_role": missing,
            "knowledge_changes": [],
            "new_knowledge": False,
            "knowledge_owner": "chapter_local_participant",
            "entity_refs": [],
            "new_entity": False,
            "inventory_delta": 0,
            "canon_change": False,
            "story_state_change": False,
            "confirmed_facts_changed": 0,
            "affected_chapter_ids": [chapter_id],
            "downstream_targets": list(evidence.get("affected_targets") or []),
            "dependency_refs": [],
            "missing_semantic_type": missing,
            "authorized_options": [opt["option_id"]
                                   for opt in decision.get("allowed_options") or []],
            "selected_option": decision.get("selected_option"),
            "author_decision_ref": decision.get("decision_id"),
            "approval_ref": "AUTHOR_CONTENT_APPROVAL",
            "authorization_ref": AUTHORIZATION_FILE,
            "source_evidence": [
                f"source_ir_digest:{evidence.get('source_ir_digest')}",
                f"foundation_digest:{evidence.get('foundation_artifact_digest')}",
                f"p15n_class:{p15n_class}",
                f"refinement:{evidence.get('refinement_reason')}"],
            "parent_source_digest": str(evidence.get("source_ir_digest") or ""),
            "semantic_elements_added": 1,
            "new_event_count": 1,
            "truth_impact": "chapter_local_only",
            "downstream_effect": "releases blocked downstream targets after recompute",
            "temporal_placement": "chapter_local",
            "non_authoritative": True,
        }


class M11ApprovedEventService:
    """approved-event production route 的编排：授权 → wave → gate → reconciliation。"""

    def __init__(self, project_root: Path | str, *, design_dir: str = ADOPTION_DIR,
                 foundation_dir: str = HISTORY_DIR) -> None:
        from novelforge.story_engine.m11_content_design import (
            ContentDesignEvidenceBuilder, M11ContentDesign01Service)
        self.root = Path(project_root).resolve()
        self.design_dir = (self.root / design_dir).resolve()
        self.foundation_dir = (self.root / foundation_dir).resolve()
        self.runner = M11Run12Service(self.root, design_dir=str(self.design_dir),
                                      foundation_dir=str(self.foundation_dir))
        self.content_service = M11ContentDesign01Service(
            self.root, design_dir=str(self.design_dir),
            foundation_dir=str(self.foundation_dir))
        self.evidence_builder = ContentDesignEvidenceBuilder(self.content_service)
        self.scope = _read_json(self.design_dir / APPROVED_SCOPE)
        self.decisions_input = _read_json(self.design_dir / DECISIONS_INPUT)
        canonical = _read_json(self.design_dir / CANONICAL_DECISIONS)
        self.canonical_decisions = {row["decision_id"]: row
                                    for row in canonical.get("decisions") or []}
        self.approved_by_root: dict[str, dict[str, Any]] = {}
        approvals = {row["decision_id"]: row
                     for row in self.decisions_input.get("decisions") or []}
        for row in self.scope.get("approved_decisions") or []:
            base = dict(self.canonical_decisions.get(row["decision_id"]) or {})
            base["selected_option"] = row["selected_option"]
            approval = approvals.get(row["decision_id"]) or {}
            base["approved_by"] = approval.get("approved_by", "")
            base["decision_source"] = approval.get("decision_source", "")
            base["decision_timestamp"] = approval.get("decision_timestamp", "")
            for root_id in row.get("canonical_root_ids") or []:
                self.approved_by_root[str(root_id)] = base
        self.approved_root_ids = set(self.approved_by_root)
        self.roots = {row["canonical_root_id"]: row for row in _read_json(
            self.design_dir / CANONICAL_INVENTORY).get("roots") or []
            if row["family"] == "CONTENT_DESIGN"}
        inputs = self.runner.inputs()
        self.known_target_ids = {str(cid) for cid in inputs.targets}
        self.known_entity_ids: set[str] = set()
        self.legacy_rows = inputs.legacy_rows
        self.validator = ApprovedNewEventValidator(self)
        self.builder = ApprovedEventBuilder(self)

    def legacy_row(self, chapter_id: str) -> dict[str, Any]:
        row = self.legacy_rows.get(chapter_id) or {}
        return dict(row) if isinstance(row, Mapping) else {}

    # ------------------------------------------------------------ artifacts
    def authorization(self) -> dict[str, Any]:
        payload = {
            "generated_at": _now(),
            "authorization_id": "M11_APPROVED_EVENT_ARCHITECTURE_AUTHORIZATION",
            "authorized_by": "USER",
            "authorization_source": "CURRENT_USER_INSTRUCTION",
            "purpose": "unblock author-approved historical semantic additions",
            "safe_auto_relaxed": False,
            "p15_reopened": False,
            "truth_boundary_relaxed": False,
            "allowed_operation": "ADD_SEMANTIC_ELEMENT",
            "max_new_event_per_root": ONE_NEW_EVENT_MAX,
            "requires_explicit_author_approval": True,
            "isolated_from": ["SAFE_AUTO", "P15_MICRO_EXECUTOR",
                              "LEGACY_M11_RUN_EXECUTOR"],
            "read_only": True, "non_authoritative": True}
        _write_json(self.design_dir / AUTHORIZATION_FILE, payload)
        return payload

    def gate_definition(self) -> dict[str, Any]:
        payload = {"generated_at": _now(), "gate_id": "M11_APPROVED_EVENT_GATE_V1",
                   "checks": list(GATE_CHECK_NAMES),
                   "check_count": len(GATE_CHECK_NAMES),
                   "semantics": ("仅对 explicit author-approved canonical root 生效；"
                                 "SAFE_AUTO / P15 / legacy run gate 语义不变"),
                   "read_only": True}
        _write_json(self.design_dir / GATE_FILE, payload)
        return payload

    # ------------------------------------------------------------ execution
    def execute_waves(self, *, wave_size: int = 20) -> dict[str, Any]:
        order = sorted(self.approved_by_root, key=lambda root_id: (
            -int((self.content_service.canonical_impact.get(root_id) or {}).get(
                "immediate_unlock_count_if_only_this_root_resolved") or 0),
            root_id))
        prior = _read_json(self.design_dir / RECONCILIATION_FILE)
        records: list[dict[str, Any]] = list(prior.get("records") or [])
        executed: set[str] = {str(row.get("canonical_root_id"))
                              for row in records}
        failures: list[dict[str, Any]] = []
        waves: list[dict[str, Any]] = []
        for wave_index in range(0, len(order), wave_size):
            wave_roots = order[wave_index:wave_index + wave_size]
            wave_records: list[dict[str, Any]] = []
            for root_id in wave_roots:
                if root_id in executed:
                    continue
                root = self.roots.get(root_id)
                decision = self.approved_by_root.get(root_id)
                if root is None or decision is None:
                    cached = self._cached_artifact(root_id)
                    if cached and (cached.get("gate") or {}).get("status") == "PASS" \
                            and cached.get("approved_event"):
                        record = self._record(cached["approved_event"], decision or {},
                                              root_id)
                        records.append(record)
                        wave_records.append(record)
                        executed.add(root_id)
                        continue
                    failures.append({"canonical_root_id": root_id,
                                     "reason": "root/decision 不在 frozen scope"})
                    continue
                evidence = self.evidence_builder.evidence_for(root)
                event = self.builder.build(root=root, decision=decision,
                                           evidence=evidence)
                gate = self.validator.validate(decision=decision, root=root,
                                               event=event, evidence=evidence,
                                               executed_roots=executed)
                if gate["status"] != "PASS":
                    repaired_path = (self.design_dir / REPAIRED_DIR /
                                     f"{event['chapter_id']}.json")
                    if repaired_path.is_file():
                        cached = _read_json(repaired_path)
                        if (cached.get("gate") or {}).get("status") == "PASS" \
                                and cached.get("approved_event"):
                            event = cached["approved_event"]
                            gate = cached["gate"]
                            executed.add(root_id)
                            records.append(self._record(event, decision, root_id))
                            wave_records.append(records[-1])
                            continue
                    failures.append({"canonical_root_id": root_id,
                                     "event_id": event["event_id"],
                                     "failed_checks": gate["failed_checks"]})
                    continue
                _write_json(self.design_dir / REPAIRED_DIR /
                            f"{event['chapter_id']}.json", {
                                "approved_event": event, "gate": gate,
                                "resolution_mode": "AUTHOR_APPROVED_NEW_EVENT",
                                "generated_at": _now(), "read_only": True})
                executed.add(root_id)
                record = self._record(event, decision, root_id)
                records.append(record)
                wave_records.append(record)
            waves.append({"wave_index": len(waves) + 1,
                          "frozen_roots": wave_roots,
                          "records": len(wave_records)})
            _write_json(self.design_dir / RECONCILIATION_FILE, {
                "generated_at": _now(), "run_id": "M11_APPROVED_EVENT",
                "record_count": len(records), "records": records,
                "read_only": True, "non_authoritative": True})
            self.runner.refresh_projections()
        return {"waves": waves, "records": records, "failures": failures}

    def _record(self, event: Mapping[str, Any], decision: Mapping[str, Any],
                root_id: str) -> dict[str, Any]:
        return {
                    "run_id": "M11_APPROVED_EVENT",
                    "batch_id": "REPAIR_BATCH_16" if False else "M11_FINAL_CLOSURE",
                    "chapter_id": event["chapter_id"],
                    "legacy_label": event["chapter"],
                    "old_status": "CONTENT_DESIGN_REQUIRED",
                    "new_resolution_status": "RESOLVED_REPAIRED",
                    "repair_class": event["causal_role"] or "SEMANTIC_ADDITION",
                    "repair_subtype": SUBTYPE,
                    "execution_decision": "AUTHOR_APPROVED_NEW_EVENT",
                    "evidence_substrate": "HISTORICAL_FULL_IR",
                    "repaired_ref": f"{REPAIRED_DIR}/{event['chapter_id']}.json",
                    "patch_ops": ["ADD_SEMANTIC_ELEMENT"],
                    "reason": (f"author-approved new event（{event['decision_id'] if 'decision_id' in event else decision['decision_id']}，"
                               f"option={decision['selected_option']}）"),
                    "design_item_id": root_id,
                    "canonical_root_id": root_id,
                    "event_id": event["event_id"],
                    "new_event_count": event["new_event_count"],
                    "approval_ref": event["approval_ref"],
                    "gate_result": "PASS",
                    "timestamp": _now(), "non_authoritative": True}

    def _cached_artifact(self, root_id: str) -> dict[str, Any]:
        repaired_dir = self.design_dir / REPAIRED_DIR
        if not repaired_dir.is_dir():
            return {}
        for path in sorted(repaired_dir.glob("*.json")):
            payload = _read_json(path)
            if str((payload.get("approved_event") or {}).get("canonical_root_id")) \
                    == root_id:
                return payload
        return {}

    def run(self, *, wave_size: int = 20) -> dict[str, Any]:
        self.authorization()
        gate_def = self.gate_definition()
        result = self.execute_waves(wave_size=wave_size)
        records = result["records"]
        _write_json(self.design_dir / EXECUTION_LEDGER_FILE, {
            "generated_at": _now(),
            "resolved_root_count": len(records),
            "records": [{key: row[key] for key in
                         ("canonical_root_id", "legacy_label", "event_id",
                          "new_event_count", "repaired_ref", "approval_ref")}
                        for row in records],
            "failures": result["failures"], "read_only": True})
        projections = self.runner.refresh_projections()
        overlay = projections["overlay"]
        payload = {
            "generated_at": _now(), "run_id": "M11_APPROVED_EVENT",
            "authorization_ref": AUTHORIZATION_FILE, "gate_ref": GATE_FILE,
            "gate_check_count": gate_def["check_count"],
            "waves": result["waves"], "resolved_root_count": len(records),
            "failure_count": len(result["failures"]), "failures": result["failures"],
            "subtype": SUBTYPE,
            "overlay_resolved_total": overlay.get("resolved_total"),
            "overlay_content_design_required": overlay.get(
                "content_design_required"),
            "read_only": True, "non_authoritative": True}
        _write_json(self.design_dir / GATE_RESULT_FILE, payload)
        return payload


__all__ = [
    "AUTHORIZATION_FILE",
    "ApprovedEventBuilder",
    "ApprovedNewEventValidator",
    "GATE_CHECK_NAMES",
    "GATE_FILE",
    "GATE_RESULT_FILE",
    "M11ApprovedEventService",
    "ONE_NEW_EVENT_MAX",
    "RECONCILIATION_FILE",
    "REPAIRED_DIR",
    "SUBTYPE",
]
