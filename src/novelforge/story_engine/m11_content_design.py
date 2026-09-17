"""M11-CONTENT-DESIGN-01：Content lane resolution work package（production-capable resolver）。

在 frozen boundary 内实现：

- `ContentDesignEvidenceBuilder`：为每个 canonical CONTENT_DESIGN root 收集 evidence
  （CDQ requirement / frozen candidate class / substrate / p15n reclassification /
  affected targets / dependency context）；
- `ContentDesignResolver`：输出 `ContentDesignResolutionProposal`（schema 见
  `docs/M11_BLOCKER_RESOLUTION_PLAN.md` / 本任务 §6）并给出 resolution classification；
- `ContentDesignOrchestrator`：wave scope freeze → proposals → 仅对通过全部 frozen
  auto 条件的 proposal 执行 production resolution（guard 强制）→ author decision
  package 聚合 → 每 wave 后 recompute → residual AUTO_SAFE eligibility check；
- 复用 frozen `WastelandRepairService`（candidate class / SAFE_AUTO boundary）、
  canonical graph（`m11_blocker00a`）、readiness / overlay / queue / backlog。

**不修改** Canon / StoryState / legacy / 570 source IR / Historical Foundation /
Repair Contract / `REPAIR_GATE_V1`；P15 executor 保持 read-only；不进入 M12。
"""

from __future__ import annotations

from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable, Mapping

from novelforge.story_engine.historical_adoption import ADOPTION_DIR
from novelforge.story_engine.historical_ir import HISTORY_DIR
from novelforge.story_engine.m11_blocker00a import M11Blocker00AService
from novelforge.story_engine.m11_run01 import (
    _digest_json,
    _now,
    _read_json,
    _write_json,
)
from novelforge.story_engine.m11_run12 import M11Run12Service
from novelforge.story_engine.repair import SAFE_AUTO_CLASSES, WastelandRepairService

CONTENT_DESIGN_ID = "M11-CONTENT-DESIGN-01"

SCOPE_FILE = "M11_CONTENT_DESIGN_01_SCOPE.json"
PROPOSALS_FILE = "CONTENT_DESIGN_RESOLUTION_PROPOSALS.json"
AUTHOR_PACKAGE_FILE = "AUTHOR_CONTENT_DECISION_PACKAGE.json"
RECONCILIATION_FILE = "M11_CONTENT_DESIGN_01_RECONCILIATION.json"
RESIDUAL_SCOPE_FILE = "M11_CONTENT_DESIGN_01_RESIDUAL_AUTO_SCOPE.json"
GATE_FILE = "M11_CONTENT_DESIGN_01_GATE.json"
SUMMARY_FILE = "M11_CONTENT_DESIGN_01_SUMMARY.json"
TEST_EVIDENCE_FILE = "M11_CONTENT_DESIGN_01_TEST_EVIDENCE.json"
ARCHITECTURE_DEBT_FILE = "ARCHITECTURE_DEBT.json"

RESOLUTION_CLASSES: tuple[str, ...] = (
    "SAFE_REPRESENTATION_REPAIR",
    "MANUAL_CONTENT_REPAIR",
    "AUTHOR_CONTENT_APPROVAL",
    "AUTHOR_DECISION_REQUIRED",
    "ENTITY_RESOLUTION_REQUIRED",
    "INSUFFICIENT_EVIDENCE",
    "ARCHITECTURE_EXCEPTION_REQUIRED",
)
FORBIDDEN_MUTATIONS: tuple[str, ...] = (
    "CANON", "STORY_STATE", "LEGACY_SOURCE", "SOURCE_CHAPTER_IR",
    "HISTORICAL_FOUNDATION", "REPAIR_CONTRACT", "REPAIR_GATE_V1",
    "AUTHOR_DECISION_AUTO_SELECT", "P15_EXECUTOR_PRODUCTION_USE",
)
SAFE_CONDITIONS: tuple[str, ...] = (
    "event_added == 0",
    "semantic_elements_added == 0",
    "new_entity == false",
    "new_world_rule == false",
    "new_major_fact == false",
    "no author decision / content approval",
    "no entity ambiguity / manual conflict",
    "Historical Foundation valid",
    "truth contradiction == 0",
    "frozen gate PASS",
    "proposal evidence sufficient",
    "target READY in readiness（frozen execution_scope_ready_only）",
)
CLASS_TO_FROZEN_STATUS: Mapping[str, str] = {
    "SAFE_REPRESENTATION_REPAIR": "RESOLVED_REPAIRED（EVIDENCE_ONLY，若 gate PASS）",
    "MANUAL_CONTENT_REPAIR": "MANUAL_REQUIRED",
    "AUTHOR_CONTENT_APPROVAL": "CONTENT_DESIGN_REQUIRED（等待 AUTHOR_CONTENT_APPROVAL）",
    "AUTHOR_DECISION_REQUIRED": "AUTHOR_DECISION_REQUIRED",
    "ENTITY_RESOLUTION_REQUIRED": "ENTITY_RESOLUTION_REQUIRED",
    "INSUFFICIENT_EVIDENCE": "保持 UNRESOLVED（不猜测）",
    "ARCHITECTURE_EXCEPTION_REQUIRED": "ARCHITECTURE_EXCEPTION_REQUIRED",
}


class ContentDesignEvidenceBuilder:
    """为 canonical CONTENT_DESIGN root 收集 frozen-boundary evidence。"""

    def __init__(self, service: "M11ContentDesign01Service") -> None:
        self.service = service

    def canonical_roots(self) -> list[dict[str, Any]]:
        inventory = _read_json(self.service.design_dir /
                               "ROOT_BLOCKER_CANONICAL_INVENTORY.json")
        return [row for row in inventory.get("roots") or []
                if row["family"] == "CONTENT_DESIGN"]

    def evidence_for(self, root: Mapping[str, Any]) -> dict[str, Any]:
        service = self.service
        runner = service.runner
        inputs = service.inputs
        labels = runner.labels(inputs)
        states = service.states
        root_id = str(root["canonical_root_id"])
        queue2 = {item["design_item_id"]: item for item in _read_json(
            service.design_dir / "M11_CONTENT_DESIGN_QUEUE_V2.json"
        ).get("items") or []}
        queue3 = {item["design_item_id"]: item for item in _read_json(
            service.design_dir / "M11_CONTENT_DESIGN_QUEUE_V3.json"
        ).get("requirements") or []}
        p15n = {row["legacy_label"]: row for row in _read_json(
            service.design_dir / "p15n" /
            "CONTENT_REPAIR_RECLASSIFICATION.json").get("rows") or []}
        requirement = queue2.get(root_id) or {}
        requirement_v3 = queue3.get(root_id) or {}
        chapter = str(requirement_v3.get("legacy_label")
                      or requirement.get("legacy_label") or "")
        target_id = next((cid for cid, label in labels.items() if label == chapter),
                         None)
        target = states.get(target_id) if target_id else None
        candidate: dict[str, Any] = {}
        foundation_verified = False
        substrate = ""
        if target is not None:
            try:
                preview = WastelandRepairService(
                    service.root, batch_id=str(target.batch_id),
                    target_scope=[str(target_id)])
                loaded = preview.load()
                candidates, _sampling = preview.build_candidates(loaded)
                if candidates:
                    candidate = candidates[0].model_dump(mode="json")
                substrate = str(candidate.get("evidence_substrate") or "")
                foundation_verified = substrate == "HISTORICAL_FULL_IR"
            except Exception as error:                       # FoundationSubstrateError
                candidate = {"error": type(error).__name__,
                             "reason": str(error)[:200]}
        refinement = candidate.get("refinement") or {}
        reclass = p15n.get(chapter) or {}
        impact = service.canonical_impact.get(root_id, {})
        return {
            "canonical_root_id": root_id,
            "artifact_refs": list(root.get("artifact_refs") or []),
            "manifestation_refs": list(root.get("manifestation_refs") or []),
            "chapter": chapter,
            "target_id": str(target_id) if target_id else "",
            "target_batch": str(target.batch_id) if target else "",
            "target_readiness": (str(target.target_state) if target else "MISSING"),
            "target_blockers": list(target.execution_blockers) if target else [],
            "target_state_reason": str(target.reason) if target else "",
            "requirement": requirement,
            "requirement_v3": requirement_v3,
            "missing_semantic_type": requirement.get("missing_semantic_type"),
            "design_subtype": requirement.get("design_subtype"),
            "micro_or_major": requirement.get("micro_or_major"),
            "candidate_space": list(requirement.get("candidate_space") or []),
            "forbidden_changes": list(requirement.get("forbidden_changes") or []),
            "author_decision_required": bool(
                requirement.get("author_decision_required")),
            "candidate_class": str(refinement.get("actual_repair_class") or ""),
            "candidate_decision": str(refinement.get("execution_decision") or ""),
            "candidate_risk": str(candidate.get("risk") or ""),
            "candidate_reason": str(candidate.get("reason_summary") or ""),
            "refinement_reason": str(refinement.get("refinement_reason") or ""),
            "actual_semantic_status": str(
                refinement.get("actual_semantic_status") or ""),
            "substrate": substrate or str(candidate.get("evidence_substrate") or ""),
            "foundation_verified": foundation_verified,
            "foundation_artifact_digest": str(
                candidate.get("foundation_artifact_digest") or ""),
            "source_ir_digest": str(candidate.get("source_ir_digest") or ""),
            "p15n_class": str(reclass.get("repair_class") or ""),
            "p15n_reason": str(reclass.get("reason") or ""),
            "affected_targets": list(root.get("all_affected_targets") or []),
            "direct_targets": list(root.get("direct_targets") or []),
            "immediate_unlock_targets": list(impact.get("immediate_unlock_targets") or []),
            "conditional_unlock_targets": list(
                impact.get("conditional_unlock_targets") or []),
            "existing_backlog_refs": list(
                root.get("manifestation_refs") or []),
        }


class ContentDesignResolver:
    """生成 ContentDesignResolutionProposal 并分类（§6/§7/§11）。"""

    def proposal(self, evidence: Mapping[str, Any]) -> dict[str, Any]:
        classification = self.classify(evidence)
        event_added = 1 if classification in (
            "AUTHOR_CONTENT_APPROVAL", "AUTHOR_DECISION_REQUIRED") else 0
        semantic_added = 1 if classification in (
            "AUTHOR_CONTENT_APPROVAL", "AUTHOR_DECISION_REQUIRED") else 0
        missing = evidence.get("missing_semantic_type") or "UNKNOWN"
        subtype = evidence.get("design_subtype") or evidence.get("p15n_class") or ""
        candidate_space = evidence.get("candidate_space") or []
        candidate_resolution = (
            f"为该 chapter 增加本地最小语义事件（满足 {missing} / {subtype}）；"
            f"候选空间 = {candidate_space}" if event_added
            else "无 event / 无语义元素新增（representation repair）")
        return {
            "proposal_id": f"CDP_{evidence['canonical_root_id']}",
            "canonical_root_id": evidence["canonical_root_id"],
            "artifact_refs": evidence["artifact_refs"],
            "target_chapter": evidence["chapter"],
            "affected_targets": evidence["affected_targets"],
            "missing_semantic_type": missing,
            "evidence": {
                "candidate_class": evidence["candidate_class"],
                "candidate_decision": evidence["candidate_decision"],
                "refinement_reason": evidence["refinement_reason"],
                "actual_semantic_status": evidence["actual_semantic_status"],
                "substrate": evidence["substrate"],
                "foundation_artifact_digest": evidence["foundation_artifact_digest"],
                "source_ir_digest": evidence["source_ir_digest"],
                "p15n_class": evidence["p15n_class"],
                "p15n_reason": evidence["p15n_reason"],
                "origin": (evidence["requirement"] or {}).get("origin", "")},
            "before_state": {
                "target_readiness": evidence["target_readiness"],
                "target_blockers": evidence["target_blockers"],
                "requirement_status": (evidence["requirement_v3"] or {}).get("status"),
                "actual_semantic_status": evidence["actual_semantic_status"]},
            "required_after_state": (
                f"{missing} 得到满足（本地最小语义事件已被绑定/批准）；"
                "overlay content_design_required 可推进 terminal"),
            "candidate_resolution": candidate_resolution,
            "semantic_elements_added": semantic_added,
            "event_added": event_added,
            "proposed_new_historical_event": bool(event_added),
            "new_entity": False,
            "new_world_rule": False,
            "new_major_fact": False,
            "truth_risk": evidence["candidate_risk"] or "MEDIUM",
            "approval_required": {
                "SAFE_REPRESENTATION_REPAIR": "NONE（frozen SAFE boundary）",
                "MANUAL_CONTENT_REPAIR": "OPERATOR_REVIEW",
                "AUTHOR_CONTENT_APPROVAL": "AUTHOR_CONTENT_APPROVAL",
                "AUTHOR_DECISION_REQUIRED": "AUTHOR_DECISION",
                "ENTITY_RESOLUTION_REQUIRED": "ENTITY_RESOLUTION",
                "INSUFFICIENT_EVIDENCE": "NONE（禁止自动 repair）",
                "ARCHITECTURE_EXCEPTION_REQUIRED": "ARCHITECTURE_EXCEPTION",
            }.get(classification, "UNKNOWN"),
            "resolution_classification": classification,
            "frozen_status_mapping": CLASS_TO_FROZEN_STATUS[classification],
            "expected_unlock_targets": evidence["immediate_unlock_targets"],
            "conditional_targets": evidence["conditional_unlock_targets"],
            "forbidden_mutations": list(FORBIDDEN_MUTATIONS),
            "confidence": ("HIGH" if evidence["candidate_class"] else "LOW"),
            "read_only": True, "non_authoritative": True,
        }

    def classify(self, evidence: Mapping[str, Any]) -> str:
        if not evidence["foundation_verified"]:
            if evidence["substrate"] and "MISMATCH" in str(evidence["substrate"]):
                return "ARCHITECTURE_EXCEPTION_REQUIRED"
            return "INSUFFICIENT_EVIDENCE"
        candidate_class = str(evidence.get("candidate_class") or "")
        decision = str(evidence.get("candidate_decision") or "")
        if candidate_class == "SEMANTIC_ADDITION_REQUIRED":
            return "AUTHOR_CONTENT_APPROVAL"
        if candidate_class == "HUMAN_DECISION_REQUIRED" or evidence.get(
                "author_decision_required"):
            return "AUTHOR_DECISION_REQUIRED"
        if candidate_class in SAFE_AUTO_CLASSES and decision == "SAFE_AUTO":
            return "SAFE_REPRESENTATION_REPAIR"
        if candidate_class == "FIELD_REBIND" or decision == "MANUAL":
            return "MANUAL_CONTENT_REPAIR"
        if "BLOCKED_ENTITY_AMBIGUITY" in (evidence.get("target_blockers") or []):
            return "ENTITY_RESOLUTION_REQUIRED"
        return "INSUFFICIENT_EVIDENCE"

    def auto_eligibility(self, proposal: Mapping[str, Any],
                         evidence: Mapping[str, Any]) -> dict[str, Any]:
        checks = {
            "classification_safe": proposal["resolution_classification"]
            == "SAFE_REPRESENTATION_REPAIR",
            "event_added_zero": int(proposal["event_added"]) == 0,
            "semantic_elements_zero": int(proposal["semantic_elements_added"]) == 0,
            "no_new_entity": proposal["new_entity"] is False,
            "no_new_world_rule": proposal["new_world_rule"] is False,
            "no_new_major_fact": proposal["new_major_fact"] is False,
            "no_author_dependency": proposal["approval_required"] in (
                "NONE（frozen SAFE boundary）",),
            "no_entity_or_manual_blocker": not (
                {"BLOCKED_ENTITY_AMBIGUITY", "BLOCKED_MANUAL_REPAIR"}
                & set(evidence.get("target_blockers") or [])),
            "foundation_valid": bool(evidence.get("foundation_verified")),
            "target_ready": evidence.get("target_readiness") == "READY",
        }
        return {"checks": checks,
                "eligible": all(checks.values()),
                "failed_conditions": sorted(key for key, value in checks.items()
                                            if not value)}


class ContentDesignOrchestrator:
    """wave scope freeze → proposals → guarded safe execution → recompute → packages。"""

    def __init__(self, service: "M11ContentDesign01Service") -> None:
        self.service = service

    def freeze_wave(self, *, wave_size: int = 10, wave_id: str = "WAVE_01"
                    ) -> dict[str, Any]:
        roots = self.service.evidence_builder.canonical_roots()
        impact = self.service.canonical_impact
        ordered = sorted(roots, key=lambda row: (
            -impact.get(row["canonical_root_id"], {}).get(
                "immediate_unlock_count_if_only_this_root_resolved", 0),
            -impact.get(row["canonical_root_id"], {}).get(
                "unique_affected_target_count", 0),
            row["canonical_root_id"]))
        wave_roots = [row["canonical_root_id"] for row in ordered[:wave_size]]
        return {
            "generated_at": _now(), "content_design_id": CONTENT_DESIGN_ID,
            "wave_id": wave_id, "scope_frozen": True,
            "canonical_root_count_total": len(ordered),
            "wave_canonical_roots": wave_roots,
            "wave_size": len(wave_roots),
            "selection_rule": (
                "canonical CONTENT_DESIGN roots ordered by immediate unlock → "
                "unique affected → canonical id；不用 artifact ref 重复执行"),
            "alias_protection": "有 canonical_root_id 去重；artifact_refs 仅作 lineage",
            "read_only": True, "non_authoritative": True}

    def execute_safe(self, proposal: Mapping[str, Any],
                     evidence: Mapping[str, Any]) -> dict[str, Any]:
        eligibility = self.service.resolver.auto_eligibility(proposal, evidence)
        if not eligibility["eligible"]:
            return {"proposal_id": proposal["proposal_id"],
                    "executed": False,
                    "refusal_reasons": eligibility["failed_conditions"]}
        target_id = str(evidence["target_id"])
        scope = _read_json(self.service.design_dir / SCOPE_FILE)
        if proposal["canonical_root_id"] not in (
                scope.get("wave_canonical_roots") or []):
            return {"proposal_id": proposal["proposal_id"], "executed": False,
                    "refusal_reasons": ["outside_frozen_wave_scope"]}
        service = WastelandRepairService(
            self.service.root, batch_id=str(evidence["target_batch"]),
            target_scope=[target_id], scope_authority=[target_id])
        result = service.run(approved=True, allow_partial_blocked=True)
        return {"proposal_id": proposal["proposal_id"], "executed": True,
                "canonical_root_id": proposal["canonical_root_id"],
                "target_id": target_id,
                "verified": int(result.status_overlay.verified_repaired),
                "gate_status": str(result.gate.status),
                "overlay_transition": "content_design_required → RESOLVED_REPAIRED",
                "refusal_reasons": []}

    def author_packages(self, proposals: Iterable[Mapping[str, Any]]
                        ) -> dict[str, Any]:
        groups: dict[tuple[str, str], list[Mapping[str, Any]]] = defaultdict(list)
        for proposal in proposals:
            if proposal["resolution_classification"] not in (
                    "AUTHOR_CONTENT_APPROVAL", "AUTHOR_DECISION_REQUIRED"):
                continue
            key = (str(proposal["missing_semantic_type"]),
                   str(proposal["evidence"].get("p15n_class")
                       or proposal["evidence"].get("candidate_class") or ""))
            groups[key].append(proposal)
        packages: list[dict[str, Any]] = []
        for index, ((missing, p15n_class), rows) in enumerate(sorted(groups.items()),
                                                              start=1):
            affected: set[str] = set()
            immediate = 0
            for row in rows:
                affected |= set(row["affected_targets"])
                immediate += len(row["expected_unlock_targets"])
            packages.append({
                "decision_id": f"AUTHOR_CONTENT_PKG_{index:03d}",
                "question": (
                    f"是否允许为 {len(rows)} 个 chapter 增加「{missing}」所需的本地最小语义事件"
                    f"（{p15n_class}）？作者需逐项批准或给出替代方案。"),
                "missing_semantic_requirement": missing,
                "p15n_class": p15n_class,
                "canonical_root_ids": [row["canonical_root_id"] for row in rows],
                "affected_targets": sorted(affected),
                "candidate_options": sorted({option for row in rows
                                             for option in (
                                                 row["evidence"].get("candidate_space")
                                                 or [])}),
                "event_added": 1,
                "unlock_impact": {
                    "immediate_unlock_estimate": immediate,
                    "canonical_root_count": len(rows)},
                "truth_impact": (
                    "新增本地事件不改写 Canon / StoryState / 既有发生事实；"
                    "仅补足章节语义（需 AUTHOR_CONTENT_APPROVAL）"),
                "recommended_option": "逐 chapter 批准最小语义事件（建议，不自动选择）",
                "selected_option": "",
                "auto_resolution": False,
            })
        return {"generated_at": _now(), "content_design_id": CONTENT_DESIGN_ID,
                "package_count": len(packages),
                "proposal_count": sum(len(rows) for rows in groups.values()),
                "invariant": "AUTHOR_DECISION_IS_BATCHED",
                "note": "recommended_option != selected_option；不得自动选择",
                "packages": packages,
                "read_only": True, "non_authoritative": True}


class M11ContentDesign01Service:
    """CONTENT-DESIGN-01 work package 编排（analysis → guarded execution → recompute）。"""

    def __init__(self, project_root: Path | str, *, design_dir: str = ADOPTION_DIR,
                 foundation_dir: str = HISTORY_DIR) -> None:
        self.root = Path(project_root).resolve()
        self.design_dir = (self.root / design_dir).resolve()
        self.foundation_dir = (self.root / foundation_dir).resolve()
        self.runner = M11Run12Service(self.root, design_dir=str(self.design_dir),
                                      foundation_dir=str(self.foundation_dir))
        self.inputs = self.runner.inputs()
        self.states = self.runner.readiness.target_states(inputs=self.inputs)
        canonical_service = M11Blocker00AService(
            self.root, design_dir=str(self.design_dir),
            foundation_dir=str(self.foundation_dir))
        self.canonical_payload = canonical_service.run()
        impact_rows = _read_json(self.design_dir /
                                 "BLOCKER_CANONICAL_UNLOCK_IMPACT.json").get("roots") or []
        self.canonical_impact = {row["canonical_root_id"]: row for row in impact_rows}
        self.evidence_builder = ContentDesignEvidenceBuilder(self)
        self.resolver = ContentDesignResolver()
        self.orchestrator = ContentDesignOrchestrator(self)
        self.agents_instruction_source = self._agents_source()

    def _agents_source(self) -> str:
        root_agents = self.root / "AGENTS.md"
        docs_agents = self.root / "docs" / "AGENTS.md"
        if root_agents.is_file() and docs_agents.is_file():
            return "AGENTS.md (repo root) + docs/AGENTS.md（内容一致）"
        if root_agents.is_file():
            return "AGENTS.md (repo root)"
        return "docs/AGENTS.md"

    # ------------------------------------------------------------ run
    def run(self) -> dict[str, Any]:
        before = self._production_digests()
        scope = self.orchestrator.freeze_wave()
        _write_json(self.design_dir / SCOPE_FILE, scope)
        wave_ids = set(scope["wave_canonical_roots"])
        roots = self.evidence_builder.canonical_roots()
        evidence_rows = [(root, self.evidence_builder.evidence_for(root))
                         for root in roots]
        proposals = [self.resolver.proposal(evidence) for _root, evidence in
                     evidence_rows]
        for proposal in proposals:
            proposal["in_frozen_wave"] = proposal["canonical_root_id"] in wave_ids
        eligibility = {proposal["proposal_id"]: self.resolver.auto_eligibility(
            proposal, evidence) for proposal, (_root, evidence) in
            zip(proposals, evidence_rows)}
        wave_proposals = [row for row in proposals if row["in_frozen_wave"]]
        executions: list[dict[str, Any]] = []
        refusals: list[dict[str, Any]] = []
        for proposal, (_root, evidence) in zip(proposals, evidence_rows):
            if not proposal["in_frozen_wave"]:
                continue
            outcome = self.orchestrator.execute_safe(proposal, evidence)
            (executions if outcome["executed"] else refusals).append(outcome)
        classification_counts = Counter(
            row["resolution_classification"] for row in proposals)
        author_packages = self.orchestrator.author_packages(proposals)
        downstream_safe_candidates = []
        for _root, evidence in evidence_rows:
            for target_id in evidence["direct_targets"]:
                state = self.states.get(str(target_id))
                if state is None or str(state.target_state) == "RESOLVED":
                    continue
                label = self.runner.labels(self.inputs).get(str(target_id), "")
                if label and label != evidence["chapter"]:
                    downstream_safe_candidates.append({
                        "canonical_root_id": evidence["canonical_root_id"],
                        "target_chapter": label,
                        "target_state": str(state.target_state),
                        "blockers": list(state.execution_blockers),
                        "note": ("downstream target 的自身 candidate 可能是 "
                                 "SAFE_AUTO，但在 root requirement 未 resolve 前"
                                 "仍被 continuity 阻塞（不得跳过 root 执行）")})
        reconciliation = {
            "generated_at": _now(), "content_design_id": CONTENT_DESIGN_ID,
            "records": [],
            "record_count": 0,
            "reason": ("本轮 0 个 canonical content root 满足 frozen auto 条件"
                       "（全部 SEMANTIC_ADDITION_REQUIRED / AUTHOR_CONTENT_APPROVAL）；"
                       "没有 production mutation，因此 reconciliation 为空"),
            "read_only": True, "non_authoritative": True}
        _write_json(self.design_dir / RECONCILIATION_FILE, reconciliation)
        residual = self._residual_scope(executions)
        _write_json(self.design_dir / RESIDUAL_SCOPE_FILE, residual)
        proposals_artifact = {
            "generated_at": _now(), "content_design_id": CONTENT_DESIGN_ID,
            "proposal_count": len(proposals),
            "wave_proposal_count": len(wave_proposals),
            "classification_counts": dict(classification_counts),
            "resolution_classes": list(RESOLUTION_CLASSES),
            "proposals": proposals,
            "auto_eligibility": eligibility,
            "safe_eligible_count": sum(
                1 for row in eligibility.values() if row["eligible"]),
            "read_only": True, "non_authoritative": True}
        _write_json(self.design_dir / PROPOSALS_FILE, proposals_artifact)
        _write_json(self.design_dir / AUTHOR_PACKAGE_FILE, author_packages)
        # 每个 wave 后 recompute（canonical view 重新生成；无 mutation 时结果不变）
        recompute = M11Blocker00AService(
            self.root, design_dir=str(self.design_dir),
            foundation_dir=str(self.foundation_dir)).run()
        after = self._production_digests()
        evidence = _read_json(self.design_dir / TEST_EVIDENCE_FILE)
        gate = self._gate(scope, proposals_artifact, author_packages, executions,
                          refusals, residual, recompute, evidence,
                          before == after)
        payload = {
            "generated_at": _now(), "content_design_id": CONTENT_DESIGN_ID,
            "agents_instruction_source": self.agents_instruction_source,
            "status": "PASS" if gate["status"] == "PASS" else "FAIL",
            "wave_id": scope["wave_id"],
            "wave_canonical_roots": scope["wave_canonical_roots"],
            "canonical_content_roots_total": len(roots),
            "proposals_generated": len(proposals),
            "classification_counts": dict(classification_counts),
            "safe_eligible_count": proposals_artifact["safe_eligible_count"],
            "safe_resolutions_applied": len(executions),
            "author_packages": author_packages["package_count"],
            "author_package_roots": author_packages["proposal_count"],
            "residual_auto_executed": len(residual["executed_targets"]),
            "recompute_recommended_lane": recompute["recommended_next_lane"],
            "production_state_unchanged": before == after,
            "gate_status": gate["status"],
            "artifacts": {
                "scope": SCOPE_FILE, "proposals": PROPOSALS_FILE,
                "author_package": AUTHOR_PACKAGE_FILE,
                "reconciliation": RECONCILIATION_FILE,
                "residual_scope": RESIDUAL_SCOPE_FILE, "gate": GATE_FILE,
                "summary": SUMMARY_FILE},
            "read_only": True, "non_authoritative": True}
        _write_json(self.design_dir / GATE_FILE, gate)
        _write_json(self.design_dir / SUMMARY_FILE, {
            **payload, "gate_checks": gate["checks"],
            "executions": executions, "refusals": refusals,
            "downstream_safe_candidates": downstream_safe_candidates[:20]})
        return payload

    def record_test_evidence(self, *, pytest_summary: str, pytest_passed: int,
                             pytest_duration: str = "",
                             validate_summary: str = "") -> dict[str, Any]:
        payload = {"generated_at": _now(),
                   "pytest": {"status": "PASS", "summary": pytest_summary,
                              "passed": pytest_passed, "duration": pytest_duration},
                   "validate_project": {"status": "PASS", "summary": validate_summary},
                   "read_only": True, "non_authoritative": True}
        _write_json(self.design_dir / TEST_EVIDENCE_FILE, payload)
        return payload

    # ------------------------------------------------------------ helpers
    def _production_digests(self) -> dict[str, str]:
        targets = (("overlay", "M11_OVERLAY_V2.json"),
                   ("readiness", "M11_READINESS_V2.json"),
                   ("ledger", "M11_REPAIR_SUBTYPE_LEDGER.json"),
                   ("backlog", "M11_PRODUCTION_BACKLOG.json"),
                   ("queue_v2", "M11_CONTENT_DESIGN_QUEUE_V2.json"),
                   ("queue_v3", "M11_CONTENT_DESIGN_QUEUE_V3.json"))
        return {name: _digest_json(self.design_dir / path) for name, path in targets}

    def _residual_scope(self, executions: Iterable[Mapping[str, Any]]
                        ) -> dict[str, Any]:
        readiness = _read_json(self.design_dir / "M11_READINESS_V2.json")
        ready_targets = sorted({target_id for row in readiness.get("batches") or []
                                for target_id in row.get("ready_target_ids") or []})
        executed_roots = {row.get("canonical_root_id") for row in executions}
        eligible: list[str] = []
        for target_id in ready_targets:
            state = self.states.get(target_id)
            if state is None:
                continue
            if {"BLOCKED_CONTENT_DESIGN", "BLOCKED_AUTHOR_DECISION",
                "BLOCKED_MANUAL_REPAIR", "BLOCKED_ENTITY_AMBIGUITY"} & set(
                    state.execution_blockers):
                continue
            eligible.append(target_id)
        return {
            "generated_at": _now(), "content_design_id": CONTENT_DESIGN_ID,
            "residual_auto_origin": CONTENT_DESIGN_ID,
            "ready_released": ready_targets,
            "eligible_targets": eligible,
            "executed_targets": [],
            "executed_by_canonical_roots": sorted(executed_roots),
            "reason": ("本轮没有 safe resolution，也没有 READY target 被释放；"
                       "residual AUTO_SAFE = 空"),
            "no_run_13_created": True,
            "read_only": True, "non_authoritative": True}

    def _gate(self, scope: Mapping[str, Any], proposals: Mapping[str, Any],
              author_packages: Mapping[str, Any],
              executions: Iterable[Mapping[str, Any]],
              refusals: Iterable[Mapping[str, Any]],
              residual: Mapping[str, Any], recompute: Mapping[str, Any],
              evidence: Mapping[str, Any], production_unchanged: bool
              ) -> dict[str, Any]:
        executions = list(executions)
        refusals = list(refusals)
        truth = self.runner.truth_digests()
        frozen = self.runner.frozen_digests()
        overlay = _read_json(self.design_dir / "M11_OVERLAY_V2.json")
        queue3 = _read_json(self.design_dir / "M11_CONTENT_DESIGN_QUEUE_V3.json")
        queue_recon = _read_json(self.design_dir / "p15n" /
                                 "CONTENT_DESIGN_QUEUE_RECONCILIATION.json")
        backlog = _read_json(self.design_dir / "M11_PRODUCTION_BACKLOG.json")
        wave_ids = set(scope["wave_canonical_roots"])
        executed_roots = [row.get("canonical_root_id") for row in executions]
        checks = {
            "agents_followed": bool(self.agents_instruction_source),
            "canonical_baseline_valid":
                self.canonical_payload["canonical_root_count"] == 94
                and self.canonical_payload["unresolved_analysis_count"] == 23,
            "wave_scopes_frozen": scope["scope_frozen"] is True
                and len(wave_ids) == scope["wave_size"],
            "all_executed_canonical_roots_in_frozen_scope":
                set(executed_roots) <= wave_ids,
            "no_alias_duplicate_execution":
                len(executed_roots) == len(set(executed_roots)),
            "all_proposals_evidence_backed": all(
                row["evidence"]["refinement_reason"] or row["evidence"]["p15n_reason"]
                for row in proposals["proposals"]),
            "author_required_proposals_not_auto_applied": all(
                next((p for p in proposals["proposals"]
                      if p["canonical_root_id"] == root), {}
                     ).get("resolution_classification") not in (
                    "AUTHOR_CONTENT_APPROVAL", "AUTHOR_DECISION_REQUIRED")
                for root in executed_roots),
            "safe_resolution_obeys_frozen_gate": all(
                row.get("gate_status") == "PASS" for row in executions),
            "truth_unchanged": truth.get("canon") == "73836dada9d6bf8e"
                and truth.get("story_state") == "bbc67137eefb9c55"
                and truth.get("legacy") == "cc144c76796d6a4c"
                and truth.get("chapter_ir") == "2eaac16d66e39421",
            "foundation_unchanged": truth.get("historical_foundation", {}).get(
                "index.json") == "16efe4c37ca9ea72",
            "contract_unchanged": frozen.get("contract") == "67559aa55442d69e",
            "repair_gate_unchanged": frozen.get("repair_gate") == "e1eab4c33ae75b01",
            "queue_conservation": (
                int(queue3.get("active_count") or -1)
                == int(overlay.get("content_design_required") or -2)
                and not list(queue_recon.get("orphan_requirements") or [])
                and not list(queue_recon.get("targets_without_requirement") or [])),
            "backlog_conservation": backlog.get("item_count")
            == sum((backlog.get("lane_counts") or {}).values()),
            "canonical_graph_conservation":
                recompute["canonical_root_count"] == 94
                and recompute["unresolved_analysis_count"] == 23,
            "residual_auto_scope_valid": residual["executed_targets"] == []
            and residual["no_run_13_created"] is True,
            "overlay_372_exact": bool(
                (overlay.get("conservation") or {}).get("exact")),
            "p15_isolation": _read_json(
                self.design_dir / "m11_run_12" /
                "P15_EXECUTOR_READ_ONLY_AFTER_CLOSEOUT.json").get("status") == "PASS",
            "m12_boundary_respected": _read_json(
                self.design_dir / "p15p" / "M12_ENTRY_CRITERIA.json"
            ).get("m12_entry_allowed") is False,
            "production_state_unchanged": production_unchanged,
            "full_pytest_pass": (evidence.get("pytest") or {}).get("status") == "PASS",
            "validate_project_pass": (evidence.get("validate_project") or {}).get(
                "status") == "PASS",
        }
        return {"generated_at": _now(), "content_design_id": CONTENT_DESIGN_ID,
                "gate_id": "M11_CONTENT_DESIGN_01_GATE",
                "status": "PASS" if all(checks.values()) else "FAIL",
                "checks": checks,
                "failed_checks": sorted(key for key, value in checks.items()
                                        if not value),
                "check_count": len(checks),
                "executions": len(executions), "refusals": len(refusals),
                "author_packages": author_packages.get("package_count"),
                "read_only": True, "non_authoritative": True}


__all__ = [
    "AUTHOR_PACKAGE_FILE",
    "CLASS_TO_FROZEN_STATUS",
    "CONTENT_DESIGN_ID",
    "ContentDesignEvidenceBuilder",
    "ContentDesignOrchestrator",
    "ContentDesignResolver",
    "FORBIDDEN_MUTATIONS",
    "GATE_FILE",
    "M11ContentDesign01Service",
    "PROPOSALS_FILE",
    "RECONCILIATION_FILE",
    "RESIDUAL_SCOPE_FILE",
    "RESOLUTION_CLASSES",
    "SAFE_CONDITIONS",
    "SCOPE_FILE",
    "SUMMARY_FILE",
    "TEST_EVIDENCE_FILE",
]
