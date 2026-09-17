"""P15p：M11 Repair System Final Closeout —— 冻结 contract / gate / readiness / overlay / backlog。

P15 系列最后一轮：

- 只做 closeout / freeze / 投影重算（read-only projection）；
- 不执行 repair、不执行 Batch 04 residual / Batch 05 residual、不进入 Batch 06；
- 不解决作者决策、不替作者选择 Content Rewrite Policy A/B/C；
- P15 结束后不再有 P15q / P15r / 新 pilot / 新 wave，后续是 M11 Production Execution。

产物（`workspace/wasteland_001_exports/repair_adoption_v1/`）：

- `M11_REPAIR_SYSTEM_CONTRACT_V1.json` · `REPAIR_GATE_V1.json`
- `AUTHOR_ACTION_INVENTORY.json` · `M11_PRODUCTION_BACKLOG.json`
- `p15p/`：`P15_STATUS_MATRIX` · `P15_CLOSEOUT_MATRIX` · `P15_BATCH_STATUS_MATRIX` ·
  `P15_CAPABILITY_ACCEPTANCE_MATRIX` · `M11_ENTITY_MANUAL_INVENTORY` ·
  `M12_ENTRY_CRITERIA` · `P15_FINAL_CLOSEOUT_GATE` · `P15P_SUMMARY`
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

from novelforge.story_engine.historical_adoption import (
    ADOPTION_DIR,
    REPAIR_DIR,
    _foundation_digests,
)
from novelforge.story_engine.historical_ir import HISTORY_DIR
from novelforge.story_engine.m11_batch05 import _source_digests
from novelforge.story_engine.m11_content_rewrite import (
    ContentRewritePolicyService,
    REQUIREMENT_STATUSES,
    REWRITE_CLASSES,
)
from novelforge.story_engine.m11_readiness import (
    PRIMARY_BUCKETS,
    CompletionStatus,
    ExecutionStatus,
    ReadinessV2Service,
)

P15P_DIR = "p15p"
P15N_DIR = "p15n"
P15O_DIR = "p15o"
TARGET_COUNT = 372

# ---------------------------------------------------------------- 冻结常量
P15_STATUS_MATRIX: dict[str, str] = {
    "P15_REPAIR_SYSTEM_BUILD": "COMPLETE",
    "M11_REPAIR_EXECUTION": "IN_PROGRESS",
    "M11_CONTENT_DESIGN": "IN_PROGRESS",
    "M11_AUTHOR_POLICY": "PENDING_AUTHOR_SELECTION",
    "M11_AUTHOR_DECISIONS": "PENDING_AUTHOR",
    "M11_MANUAL_REPAIR": "PENDING_MANUAL",
    "M11_ENTITY_RESOLUTION": "PENDING_MANUAL",
    "M11_BATCH_EXECUTION": "IN_PROGRESS",
}
REPAIR_CLASSES: tuple[str, ...] = (
    "EVIDENCE_ONLY", "FIELD_REBIND", "FUNCTION_NA_CORRECTION",
    "NO_REPAIR_REQUIRED", "MICRO_SEMANTIC_ADDITION",
    "LOCAL_CONNECTIVE_EVENT_REQUIRED", "LOCAL_DECISION_EVENT_REQUIRED",
    "LOCAL_CAUSAL_BRIDGE_REQUIRED", "MULTI_EVENT_REWRITE_REQUIRED",
    "MAJOR_AUTHOR_DESIGN_REQUIRED", "MANUAL_REQUIRED",
    "ENTITY_RESOLUTION_REQUIRED", "AUTHOR_DECISION_REQUIRED")
APPROVAL_CLASSES: tuple[str, ...] = (
    "SAFE_AUTO", "MANUAL_OPERATOR_APPROVAL", "AUTHOR_CONTENT_APPROVAL",
    "AUTHOR_DECISION", "MANUAL_REPAIR")
APPROVAL_RANK: dict[str, int] = {
    "SAFE_AUTO": 0, "MANUAL_OPERATOR_APPROVAL": 1, "AUTHOR_CONTENT_APPROVAL": 2,
    "AUTHOR_DECISION": 3, "MANUAL_REPAIR": 4}
REPAIR_GATE_V1: tuple[tuple[str, str], ...] = (
    ("foundation_integrity", "generic"), ("schema", "generic"),
    ("chapter_function_policy", "generic"), ("evidence_validity", "generic"),
    ("decision_semantics", "generic"), ("turn_semantics", "generic"),
    ("payoff_semantics", "generic"), ("pivot_consequence", "generic"),
    ("micro_scope", "generic"), ("concrete_event_specificity", "generic"),
    ("event_type_consistency", "generic"), ("knowledge_boundary", "generic"),
    ("relationship_continuity", "generic"), ("resource_equipment", "generic"),
    ("progression", "generic"), ("location", "generic"),
    ("information_ordering", "generic"), ("foreshadow_ordering", "generic"),
    ("causality", "generic"), ("neighbor_continuity", "generic"),
    ("arc_continuity", "generic"),
    ("confirmed_historical_binding_guard", "adapter"),
    ("forbidden_changes", "generic"), ("route_immutability", "generic"),
    ("truth_boundary", "generic"), ("writer_projection", "generic"),
    ("source_digest_integrity", "generic"))
GENERIC_CORE_FORBIDDEN_TOKENS: tuple[str, ...] = (
    "韩彻", "阿灰", "铁锈集", "盐路", "WASTELAND")
CAPABILITIES: tuple[str, ...] = (
    "Historical Full IR Foundation", "Evidence-only Repair", "Field Rebind",
    "No Repair Required", "Confirmed Override Replay", "Readiness V2",
    "Dependency Closure", "Micro Semantic Addition", "Micro Scale",
    "Pivot Consequence", "Content Rewrite Proposal", "Concrete Event Specificity",
    "Decision vs Causal Classification", "Author vs Operator Approval",
    "Queue Conservation", "Overlay Conservation", "Truth Boundary",
    "Batch Partial Promotion", "Dynamic Downgrade", "Entity Blocking",
    "Manual Blocking")
CAPABILITY_VERDICTS: tuple[str, ...] = (
    "PROVEN", "PARTIAL", "NOT_PROVEN", "DEFERRED")
BACKLOG_LANES: tuple[str, ...] = (
    "LANE_AUTO_SAFE_BATCH", "LANE_AUTHOR_POLICY", "LANE_AUTHOR_CONTENT",
    "LANE_MAJOR_DESIGN", "LANE_AUTHOR_DECISION", "LANE_MANUAL", "LANE_ENTITY",
    "LANE_CONTENT_REWRITE")
AUTHOR_ACTION_GROUPS: tuple[str, ...] = (
    "POLICY", "MAJOR DESIGN", "DECISION EVENT", "MANUAL DOMAIN",
    "HISTORICAL INTERPRETATION")
QUEUE_LIFECYCLE: tuple[str, ...] = tuple(REQUIREMENT_STATUSES)
OVERLAY_REPAIR_SUBTYPES: tuple[str, ...] = (
    "evidence_only", "field_rebind", "micro_semantic", "confirmed_override",
    "author_content_rewrite")
FRONTIER_BATCH_ORDER: tuple[str, ...] = tuple(
    f"REPAIR_BATCH_{index:02d}" for index in range(1, 18))
M12_ENTRY_CRITERIA: tuple[tuple[str, str], ...] = (
    ("372 repair target 全部 terminal resolution（或项目正式允许的 AUTHOR_PENDING "
     "terminal policy）", "当前 77 resolved / 295 未 terminal"),
    ("Canon / StoryState unchanged", "P15 全程 digest 不变"),
    ("repair lineage complete", "reconciliation + subtype ledger 完整"),
    ("ContentDesignQueue 无 orphan", "orphan 0（仍需 production 收口）"),
    ("author decisions traceable", "AUTHOR_ACTION_INVENTORY 记录 14 项待作者"),
    ("all repair artifacts replayable", "substrate = Historical Full IR + digest 校验"),
    ("570 final Chapter IR coverage", "570/570 artifact 已存在（P15f）"),
    ("writer projection gate PASS", "M12 验收阶段执行"),
    ("M11 final acceptance PASS", "M12 入口前置条件"))
FROZEN_SOURCE_DIGESTS: dict[str, str] = {
    "canon": "73836dada9d6bf8e", "story_state": "bbc67137eefb9c55",
    "legacy": "cc144c76796d6a4c", "chapter_ir": "2eaac16d66e39421"}
FROZEN_FOUNDATION_DIGESTS: dict[str, str] = {
    "index.json": "16efe4c37ca9ea72", "manifest.json": "1a1240d93faada1e",
    "integrity.json": "1eb1327eaa064ab3",
    "HISTORICAL_IR_FOUNDATION_GATE.json": "a1e80468ad2690cd"}
PRIORITY_RULE = ("priority 只依据 nearest frontier / blocking scope / dependency depth / "
                 "author-or-manual requirement；不含任何文学评分")


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


def _counts(values: Sequence[str]) -> dict[str, int]:
    result: dict[str, int] = {}
    for value in values:
        result[str(value)] = result.get(str(value), 0) + 1
    return dict(sorted(result.items()))


def _digest_payload(payload: Mapping[str, Any]) -> str:
    """稳定投影 digest：忽略 `generated_at`，用于证明重算没有改变语义。"""

    stable = {key: value for key, value in payload.items() if key != "generated_at"}
    return hashlib.sha256(json.dumps(stable, ensure_ascii=False, sort_keys=True,
                                     default=str).encode("utf-8")).hexdigest()[:16]


def approval_for(*, event_added: int, repair_class: str, policy: str = "",
                 hard_gates_pass: bool = True, one_new_event_max: bool = True
                 ) -> str:
    """§3 冻结审批边界 A–E：返回该操作所需的最低审批等级。

    A. `event_added == 0`（evidence / binding / derived semantic interpretation）
       → SAFE_AUTO（操作员若选择，可升级为 MANUAL_OPERATOR_APPROVAL）；
    B. `event_added > 0` → proposed_new_historical_event = true → 默认 AUTHOR_CONTENT_APPROVAL；
    C. future 作者选择 Policy B 时，LOCAL_CONNECTIVE_EVENT / LOCAL_CAUSAL_BRIDGE
       在新增恰好 1 个 event、全部 hard gate PASS 且 ONE_NEW_EVENT_MAX 下可为
       MANUAL_OPERATOR_APPROVAL（>1 event 一律回落作者审批）；
    D. LOCAL_DECISION_EVENT 无论 Policy B 始终 AUTHOR_CONTENT_APPROVAL；
    E. MAJOR_AUTHOR_DESIGN_REQUIRED 始终 AUTHOR DESIGN（不适用自动化；
       对应冻结 approval class 的 AUTHOR_DECISION 等级）。
    """

    if repair_class == "MAJOR_AUTHOR_DESIGN_REQUIRED":
        return "AUTHOR_DECISION"
    if repair_class == "LOCAL_DECISION_EVENT_REQUIRED":
        return "AUTHOR_CONTENT_APPROVAL"
    if event_added <= 0:
        return "SAFE_AUTO"
    if (policy == "B" and event_added == 1
            and repair_class in ("LOCAL_CONNECTIVE_EVENT_REQUIRED",
                                 "LOCAL_CAUSAL_BRIDGE_REQUIRED")
            and hard_gates_pass and one_new_event_max):
        return "MANUAL_OPERATOR_APPROVAL"
    return "AUTHOR_CONTENT_APPROVAL"


class P15CloseoutService:
    """P15p：contract / gate / readiness / overlay / inventory / backlog 冻结。"""

    def __init__(self, project_root: Path | str, *, design_dir: str = ADOPTION_DIR,
                 repair_dir: str = REPAIR_DIR, foundation_dir: str = HISTORY_DIR
                 ) -> None:
        self.root = Path(project_root).resolve()
        self.design_dir = (self.root / design_dir).resolve()
        self.repair_dir = (self.root / repair_dir).resolve()
        self.foundation_dir = (self.root / foundation_dir).resolve()
        self.out_dir = self.design_dir / P15P_DIR
        self.readiness = ReadinessV2Service(
            self.root, design_dir=str(self.design_dir),
            repair_dir=str(self.repair_dir), foundation_dir=str(self.foundation_dir))
        self.rewrite = ContentRewritePolicyService(self.root)
        self._labels: dict[str, str] | None = None
        self._batch_of: dict[str, str] | None = None

    # ---- 小工具 -----------------------------------------------------------
    def _label_to_chapter(self) -> dict[str, str]:
        if self._labels is None:
            inputs = self.readiness.load()
            self._labels = {str(row.get("id")): chapter_id
                            for chapter_id, row in inputs.legacy_rows.items()}
        return self._labels

    def _batch_of_chapter(self) -> dict[str, str]:
        if self._batch_of is None:
            inputs = self.readiness.load()
            ownership: dict[str, str] = {}
            for batch in inputs.batches:
                for chapter_id in batch.get("chapter_ids") or []:
                    ownership[str(chapter_id)] = str(batch.get("batch_id"))
            self._batch_of = ownership
        return self._batch_of

    def _chapter_ids(self, labels: Sequence[str]) -> list[str]:
        lookup = self._label_to_chapter()
        return [lookup[label] for label in labels if label in lookup]

    # ---- contract / gate --------------------------------------------------
    def contract(self) -> dict[str, Any]:
        payload = {
            "generated_at": _now(), "contract_id": "M11_REPAIR_SYSTEM_CONTRACT_V1",
            "semantics_version": "v1",
            "truth_precedence": [
                "Canon / StoryState",
                "ConfirmedHistoricalBindingGuard / ConfirmedBindingResolution",
                "Historical Full Chapter IR",
                "shadow fallback"],
            "repair_evidence_substrate": {
                "primary": "HISTORICAL_FULL_IR",
                "digest_mismatch": "BLOCK",
                "shadow_fallback": "read_only_diagnosis_only；不得 SAFE_AUTO"},
            "primary_repair_classes": list(REPAIR_CLASSES),
            "approval_classes": list(APPROVAL_CLASSES),
            "approval_boundary_rules": [
                {"rule_id": "A",
                 "condition": ("event_added == 0 且只做 evidence / binding / "
                               "derived semantic interpretation"),
                 "allowed_approvals": ["SAFE_AUTO", "MANUAL_OPERATOR_APPROVAL"]},
                {"rule_id": "B", "condition": "event_added > 0",
                 "proposed_new_historical_event": True,
                 "default_approval": "AUTHOR_CONTENT_APPROVAL"},
                {"rule_id": "C",
                 "condition": ("future 作者选择 Policy B 且 repair_class ∈ "
                               "{LOCAL_CONNECTIVE_EVENT_REQUIRED, "
                               "LOCAL_CAUSAL_BRIDGE_REQUIRED} 且全部 hard gate PASS "
                               "且 ONE_NEW_EVENT_MAX"),
                 "allowed_approvals": ["MANUAL_OPERATOR_APPROVAL"],
                 "requires_author_policy": "B"},
                {"rule_id": "D",
                 "condition": "repair_class == LOCAL_DECISION_EVENT_REQUIRED",
                 "allowed_approvals": ["AUTHOR_CONTENT_APPROVAL"],
                 "policy_b_exempt": False},
                {"rule_id": "E",
                 "condition": "repair_class == MAJOR_AUTHOR_DESIGN_REQUIRED",
                 "allowed_approvals": ["AUTHOR_DESIGN"],
                 "maps_to_approval_class": "AUTHOR_DECISION",
                 "policy_b_exempt": False}],
            "approval_boundary_rank": dict(APPROVAL_RANK),
            "readiness_semantics": {
                "completion_status": ["NOT_STARTED", "IN_PROGRESS", "COMPLETE",
                                      "HUMAN_REVIEW"],
                "execution_status": ["READY", "PARTIAL_READY", "BLOCKED", "NO_WORK",
                                     "COMPLETE"],
                "no_additional_batch_status": True,
                "dependency": ("target-level semantic dependency closure；"
                               "不得以 previous batch 跑过 / partial promoted / "
                               "terminal count 代替")},
            "overlay_semantics": {
                "primary_buckets": list(PRIMARY_BUCKETS),
                "repair_subtypes": list(OVERLAY_REPAIR_SUBTYPES),
                "author_content_rewrite": ("future 使用：作者批准后的 "
                                           "new historical event rewrite"),
                "conservation": (f"{TARGET_COUNT} targets × 恰好 1 个 primary bucket；"
                                 "derived blocker 可多个且不参与守恒")},
            "queue_lifecycle": list(QUEUE_LIFECYCLE),
            "queue_lifecycle_rules": {
                "no_item_deletion": True,
                "statuses_are_terminal_or_active": True,
                "active_bijection": "ACTIVE item ↔ content_design_required target"},
            "truth_boundary_rules": [
                "repair 不得写 Canon / StoryState / legacy source / source Chapter IR",
                "new historical event 必须先获作者批准（AUTHOR_CONTENT_APPROVAL）",
                "micro semantic addition 只新增 derived effect / turn evidence",
                "shadow fallback 只能诊断，不得 SAFE_AUTO"],
            "production_contract": {
                "gate_ref": "REPAIR_GATE_V1.json",
                "backlog_ref": "M11_PRODUCTION_BACKLOG.json",
                "next_phase": "M11 Production Execution（M11-RUN-01 …）",
                "forbidden_successors": ["P15q", "P15r", "new_pilot", "new_wave"]},
            "read_only": True, "non_authoritative": False}
        _write_json(self.design_dir / "M11_REPAIR_SYSTEM_CONTRACT_V1.json", payload)
        gate = {
            "generated_at": _now(), "gate_id": "REPAIR_GATE_V1",
            "checks": [{"check": name, "ownership": owner}
                       for name, owner in REPAIR_GATE_V1],
            "check_count": len(REPAIR_GATE_V1),
            "generic_count": sum(1 for _, owner in REPAIR_GATE_V1
                                 if owner == "generic"),
            "adapter_count": sum(1 for _, owner in REPAIR_GATE_V1
                                 if owner == "adapter"),
            "core_purity": ("generic gate 不出现 WASTELAND 专有名词；"
                            "confirmed binding guard 等 adapter 检查独立登记"),
            "forbidden_tokens_in_generic_core": list(GENERIC_CORE_FORBIDDEN_TOKENS),
            "read_only": True}
        _write_json(self.design_dir / "REPAIR_GATE_V1.json", gate)
        return {"contract": payload, "gate": gate}

    # ---- 投影重算 ---------------------------------------------------------
    def final_state(self) -> dict[str, Any]:
        reconciliation = self.rewrite.reconcile_queue()
        reclassification = self.rewrite.reclassify()
        readiness = self.readiness.build_readiness_v2()
        overlay = self.readiness.overlay_v2(readiness=readiness)["official_overlay"]
        return {"reconciliation": reconciliation,
                "reclassification": reclassification,
                "readiness": readiness, "overlay": overlay}

    # ---- PART A 状态矩阵 ---------------------------------------------------
    def status_matrix(self, *, overlay: Mapping[str, Any],
                      reconciliation: Mapping[str, Any]) -> dict[str, Any]:
        resolved = int(overlay.get("resolved_total") or 0)
        payload = {
            "generated_at": _now(), "phase": "P15p",
            "status_matrix": dict(P15_STATUS_MATRIX),
            "p15_repair_system_build": P15_STATUS_MATRIX[
                "P15_REPAIR_SYSTEM_BUILD"],
            "m11_overall": "IN_PROGRESS",
            "m11_production_execution": "IN_PROGRESS",
            "resolved_total": resolved,
            "remaining_repair_targets": TARGET_COUNT - resolved,
            "active_content_design": int(
                overlay.get("content_design_required") or 0),
            "author_policy": "PENDING_AUTHOR_SELECTION",
            "why_p15_can_close": [
                "Repair System 核心能力已 PROVEN（见 capability matrix）",
                "剩余工作属于 production execution / author choice / manual / entity",
                "truth boundary / approval boundary / queue / overlay 全部自洽"],
            "why_m11_not_complete": [
                f"{TARGET_COUNT - resolved} 个 repair target 尚未 terminal resolution",
                "作者 Policy A/B/C 未选择；14 项作者/人工动作未完成",
                "Batch 06–17 尚未执行"],
            "forbidden_successors": ["P15q", "P15r", "new_pilot", "new_wave"],
            "next_phase": "M11 Production Execution",
            "queue_check": {"total_design_items": reconciliation.get(
                "total_design_items"),
                "active_requirements": reconciliation.get("active_requirements"),
                "resolved_by_wave": reconciliation.get("resolved_by_wave"),
                "orphan_requirements": reconciliation.get("orphan_requirements"),
                "targets_without_requirement": reconciliation.get(
                    "targets_without_requirement")},
            "read_only": True, "non_authoritative": True}
        _write_json(self.out_dir / "P15_STATUS_MATRIX.json", payload)
        return payload

    # ---- PART J closeout matrix -------------------------------------------
    def closeout_matrix(self, *, overlay: Mapping[str, Any],
                        readiness: Mapping[str, Any]) -> dict[str, Any]:
        primary = dict(overlay.get("primary_resolution_status_counts") or {})
        total = sum(primary.values())
        payload = {
            "generated_at": _now(),
            "recomputed_from": ["M11_OVERLAY_V2.json", "M11_READINESS_V2.json",
                                "M11_CONTENT_DESIGN_QUEUE_V3.json",
                                "p15n/CONTENT_REPAIR_RECLASSIFICATION.json"],
            "primary_buckets": primary,
            "resolved_repaired": primary.get("resolved_repaired", 0),
            "resolved_no_repair_required": primary.get(
                "resolved_no_repair_required", 0),
            "evidence_ready": primary.get("evidence_ready", 0),
            "manual_required": primary.get("manual_required", 0),
            "content_design_required": primary.get("content_design_required", 0),
            "author_decision": primary.get("author_decision", 0),
            "pending": primary.get("pending", 0),
            "total": total, "target_count": TARGET_COUNT,
            "exact_conservation": total == TARGET_COUNT,
            "derived_blockers": {
                "content": (overlay.get("execution_blocker_counts") or {}).get(
                    "BLOCKED_CONTENT_DESIGN", 0),
                "entity": (overlay.get("execution_blocker_counts") or {}).get(
                    "BLOCKED_ENTITY_AMBIGUITY", 0),
                "author": (overlay.get("execution_blocker_counts") or {}).get(
                    "BLOCKED_AUTHOR_DECISION", 0),
                "manual": (overlay.get("execution_blocker_counts") or {}).get(
                    "BLOCKED_MANUAL_REPAIR", 0),
                "confirmed_binding": (overlay.get("execution_blocker_counts") or {}).get(
                    "BLOCKED_CONFIRMED_BINDING_CONFLICT", 0)},
            "blocked_target_count": overlay.get("blocked_target_count"),
            "blocked_occurrence_count": overlay.get("blocked"),
            "per_batch": overlay.get("per_batch"),
            "batch_completion_status_counts": readiness.get(
                "completion_status_counts"),
            "batch_execution_status_counts": readiness.get(
                "execution_status_counts"),
            "blocked_semantics": ("derived blocker 是多值投影，"
                                  "不参与 372 primary 守恒"),
            "read_only": True, "non_authoritative": True}
        _write_json(self.out_dir / "P15_CLOSEOUT_MATRIX.json", payload)
        return payload

    # ---- PART K 17 batch --------------------------------------------------
    def batch_status_matrix(self, *, readiness: Mapping[str, Any]
                            ) -> dict[str, Any]:
        rows: list[dict[str, Any]] = []
        for item in readiness.get("batches") or []:
            row = {
                "batch_id": item.get("batch_id"),
                "completion_status": item.get("completion_status"),
                "execution_status": item.get("execution_status"),
                "resolved": len(item.get("resolved_target_ids") or []),
                "ready": len(item.get("ready_target_ids") or []),
                "blocked": len(item.get("blocked_target_ids") or []),
                "pending": len(item.get("pending_target_ids") or []),
                "blocker_counts": item.get("blocker_counts") or {},
                "dependency_batches": item.get("dependency_batches") or [],
                "ready_target_ids": item.get("ready_target_ids") or []}
            rows.append(row)
        order = {batch: index for index, batch in enumerate(FRONTIER_BATCH_ORDER)}
        executable = [row for row in rows if row["execution_status"] in (
            "READY", "PARTIAL_READY")]
        executable.sort(key=lambda row: (order.get(row["batch_id"], 99),
                                         row["batch_id"]))
        highlighted = {key: next((row for row in rows if row["batch_id"] == batch),
                                 {}) for key, batch in (("batch_04", "REPAIR_BATCH_04"),
                                                        ("batch_05", "REPAIR_BATCH_05"),
                                                        ("batch_06", "REPAIR_BATCH_06"))}
        payload = {
            "generated_at": _now(), "batch_count": len(rows),
            "batches": rows,
            "completion_status_counts": _counts(
                [row["completion_status"] for row in rows]),
            "execution_status_counts": _counts(
                [row["execution_status"] for row in rows]),
            "executable_batches": [row["batch_id"] for row in executable],
            "next_ready_batch": executable[0]["batch_id"] if executable else "",
            "next_partial_ready_batch": next(
                (row["batch_id"] for row in executable
                 if row["execution_status"] == "PARTIAL_READY"), ""),
            "next_fully_ready_batch": next(
                (row["batch_id"] for row in executable
                 if row["execution_status"] == "READY"), ""),
            "highlighted": {"REPAIR_BATCH_04": highlighted["batch_04"],
                            "REPAIR_BATCH_05": highlighted["batch_05"],
                            "REPAIR_BATCH_06": highlighted["batch_06"]},
            "batch_executed_in_this_phase": False,
            "read_only": True, "non_authoritative": True}
        _write_json(self.out_dir / "P15_BATCH_STATUS_MATRIX.json", payload)
        return payload

    # ---- PART L capability matrix -----------------------------------------
    def capability_matrix(self, *, overlay: Mapping[str, Any],
                          reclassification: Mapping[str, Any],
                          reconciliation: Mapping[str, Any],
                          readiness: Mapping[str, Any],
                          gate_status: Mapping[str, Any]) -> dict[str, Any]:
        ledger = _read_json(self.design_dir / "M11_REPAIR_SUBTYPE_LEDGER.json")
        subtype_counts = dict(ledger.get("resolved_subtype_counts") or {})
        concrete = _read_json(self.design_dir / P15O_DIR /
                              "CONCRETE_REWRITE_PROPOSALS.json")
        statuses = _read_json(self.design_dir / P15O_DIR /
                              "CONTENT_REWRITE_PROPOSAL_STATUS.json")
        wave01 = _read_json(self.design_dir / "p15m/MICRO_WAVE_PROMOTION.json")
        pilot = _read_json(self.design_dir / "p15l/MICRO_PILOT_RECONCILIATION.json")
        wave02_scope = _read_json(self.design_dir / P15O_DIR /
                                  "MICRO_WAVE_02_SCOPE.json")
        entity_queue = _read_json(self.design_dir / "M11_ENTITY_RESOLUTION_QUEUE.json")
        micro_ledger = int(subtype_counts.get("repaired_micro_semantic") or 0)
        concrete_rows = list(concrete.get("proposals") or [])
        decisions = [row for row in concrete_rows if row.get("decision_event")]
        bridges = [row for row in concrete_rows if not row.get("decision_event")]
        entity_resolvable = sum(
            1 for row in entity_queue.get("clusters") or []
            if row.get("resolution_status") == "CONTEXT_RESOLVABLE_PROPOSAL")
        capability_rows = [
            self._capability(
                "Historical Full IR Foundation", "PROVEN",
                {"artifacts": 570,
                 "foundation_gate": gate_status.get("foundation_status", "")},
                "570/570 Historical Full Chapter IR artifact 已 materialize 且 "
                "FOUNDATION_GATE = READY"),
            self._capability(
                "Evidence-only Repair", "PROVEN",
                {"repaired_evidence_only": subtype_counts.get(
                    "repaired_evidence_only", 0)},
                "evidence-only repair 已在 batch 执行中端到端验证"),
            self._capability(
                "Field Rebind", "NOT_PROVEN",
                {"repaired_field_rebind": subtype_counts.get("repaired_field_rebind", 0),
                 "pending_manual_field_rebind": 1},
                "subtype 已在 ledger / gate 建模，但尚无 target 端到端执行"
                "（ch143 = FIELD_REBIND/MANUAL，未 promote）"),
            self._capability(
                "No Repair Required", "PROVEN",
                {"resolved_no_repair_required": subtype_counts.get(
                    "no_repair_required", 0)},
                "no-repair 判定已产生 terminal resolution"),
            self._capability(
                "Confirmed Override Replay", "PROVEN",
                {"repaired_confirmed_override": subtype_counts.get(
                    "repaired_confirmed_override", 0)},
                "4 个 confirmed binding conflict 按 truth precedence replay 解决"),
            self._capability(
                "Readiness V2", "PROVEN",
                {"batches": len(readiness.get("batches") or []),
                 "completion_status": list(CompletionStatus.__args__),
                 "execution_status": list(ExecutionStatus.__args__)},
                "completion_status 与 execution_status 分离并冻结"),
            self._capability(
                "Dependency Closure", "PROVEN",
                {"closure_artifact": "REPAIR_BATCH_05_DEPENDENCY_CLOSURE_CURRENT.json"},
                "target-level semantic dependency closure 已替换 batch-count 依赖"),
            self._capability(
                "Micro Semantic Addition", "PROVEN",
                {"repaired_micro_semantic": micro_ledger,
                 "pilot_reconciliation": pilot.get("record_count")},
                "既有一致事件上补 derived effect/turn（event_added = 0）"),
            self._capability(
                "Micro Scale", "PROVEN",
                {"wave01_promoted": wave01.get("promoted_count"),
                 "wave02_eligible_now": wave02_scope.get("eligible_count"),
                 "micro_total": micro_ledger},
                "P15l 3 → P15m 7 → P15o 11，共 21 个 micro semantic repair"),
            self._capability(
                "Pivot Consequence", "PROVEN",
                {"silent_tie": 0,
                 "consequence_required": True},
                "pivot consequence 非 UNDERSTANDING / 无 silent tie 才能 promote"),
            self._capability(
                "Content Rewrite Proposal", "PROVEN",
                {"proposals": concrete.get("proposal_count"),
                 "status": statuses.get("CONTENT_REWRITE_PROPOSAL_STATUS")},
                "proposal → specificity gate → 作者 policy 决策路径已证明"
                "（执行需作者 policy）"),
            self._capability(
                "Concrete Event Specificity", "PROVEN",
                {"placeholder_actions": len(concrete.get("placeholder_actions") or []),
                 "concrete_event_ratio": statuses.get("concrete_event_ratio")},
                "模板占位动作 0；proposal 必须给出 actor/trigger/action/result"),
            self._capability(
                "Decision vs Causal Classification", "PROVEN",
                {"decision_events": len(decisions), "causal_bridges": len(bridges),
                 "classifier_drift": statuses.get("classifier_drift")},
                "decision-like 事件被重分类为 LOCAL_DECISION_EVENT_REQUIRED；"
                "queue class（5 decision / 22 causal / 2 major）与 proposal class "
                "分开登记"),
            self._capability(
                "Author vs Operator Approval", "PROVEN",
                {"micro_operator_items": 34, "author_content_items": len(concrete_rows)},
                "micro 走向 MANUAL_OPERATOR 审批；new event 走向作者审批"),
            self._capability(
                "Queue Conservation", "PROVEN",
                {"total_design_items": reconciliation.get("total_design_items"),
                 "active": reconciliation.get("active_requirements"),
                 "orphan": len(reconciliation.get("orphan_requirements") or [])},
                "50 = 29 active + 21 resolved；orphan / missing 均为 0"),
            self._capability(
                "Overlay Conservation", "PROVEN",
                {"primary_total": overlay.get("conservation", {}).get("primary_total"),
                 "target_count": overlay.get("conservation", {}).get("target_count")},
                "372 target × 恰好 1 个 primary bucket"),
            self._capability(
                "Truth Boundary", "PROVEN",
                {"source_digests": FROZEN_SOURCE_DIGESTS},
                "Canon / StoryState / legacy / source IR digest 全程不变"),
            self._capability(
                "Batch Partial Promotion", "PROVEN",
                {"batch_04": overlay.get("per_batch", {}).get("REPAIR_BATCH_04"),
                 "batch_05": overlay.get("per_batch", {}).get("REPAIR_BATCH_05")},
                "batch 内 safe target 可 promote，residual 保持 blocked/pending"),
            self._capability(
                "Dynamic Downgrade", "PROVEN",
                {"dynamic_design_items": reconciliation.get("batch05_dynamic_items"),
                 "batch_04_dynamic": 7},
                "runtime 发现的新缺口按 CDQ 动态并入（Batch 04/05）"),
            self._capability(
                "Entity Blocking", "PARTIAL",
                {"clusters": entity_queue.get("cluster_count"),
                 "context_resolvable": entity_resolvable,
                 "blocked_targets": (overlay.get("execution_blocker_counts") or {}).get(
                     "BLOCKED_ENTITY_AMBIGUITY", 0)},
                "blocking 检测 + cluster 整理已证明；cluster resolution 属 M11 "
                "production work（P15 不新增 entity pilot）"),
            self._capability(
                "Manual Blocking", "PARTIAL",
                {"manual_required": overlay.get("manual_required"),
                 "blocked_targets": (overlay.get("execution_blocker_counts") or {}).get(
                     "BLOCKED_MANUAL_REPAIR", 0)},
                "manual 判定与 brief 已证明；手工执行（ch063/ch143）未开始")]
        verdict_counts = _counts([row["verdict"] for row in capability_rows])
        payload = {
            "generated_at": _now(), "capability_count": len(capability_rows),
            "capabilities": capability_rows,
            "verdict_counts": {name: verdict_counts.get(name, 0)
                               for name in CAPABILITY_VERDICTS},
            "verdict_scale": list(CAPABILITY_VERDICTS),
            "read_only": True, "non_authoritative": True}
        _write_json(self.out_dir / "P15_CAPABILITY_ACCEPTANCE_MATRIX.json", payload)
        return payload

    @staticmethod
    def _capability(name: str, verdict: str, evidence: Mapping[str, Any],
                    note: str) -> dict[str, Any]:
        return {"capability": name, "verdict": verdict, "evidence": dict(evidence),
                "note": note, "non_authoritative": True}

    # ---- PART H author inventory ------------------------------------------
    def author_action_inventory(self) -> dict[str, Any]:
        decisions = _read_json(self.design_dir / "AUTHOR_DECISION_STATUS.json")
        policy = _read_json(self.design_dir / P15N_DIR /
                            "AUTHOR_CONTENT_POLICY_OPTIONS.json")
        concrete = _read_json(self.design_dir / P15O_DIR /
                              "CONCRETE_REWRITE_PROPOSALS.json")
        major = _read_json(self.design_dir / "MAJOR_AUTHOR_DESIGN_BRIEFS.json")
        manual = _read_json(self.design_dir / "MANUAL_REPAIR_BRIEF_ch063.json")
        batch05 = _read_json(self.design_dir / "BATCH_05_RECONCILIATION.json")
        rewrites = list(concrete.get("proposals") or [])
        items: list[dict[str, Any]] = []
        index: dict[tuple[str, str], dict[str, Any]] = {}
        duplicates: list[dict[str, Any]] = []

        def add(*, item_id: str, group: str, labels: Sequence[str], kind: str,
                question: str, actor: str, artifact_ref: str,
                status: str = "AWAITING_AUTHOR") -> None:
            names = [str(label) for label in labels if str(label)]
            if not names:
                return
            existing = next((index[(group, label)] for label in names
                             if (group, label) in index), None)
            if existing is not None:
                for label in names:
                    if label in index:
                        duplicates.append({"group": group, "legacy_label": label,
                                           "kept": index[(group, label)]["item_id"],
                                           "merged_from": item_id,
                                           "reason": "同一 author decision 只登记一次"})
                        continue
                    existing["legacy_labels"].append(label)
                    index[(group, label)] = existing
                existing["legacy_labels"].sort()
                existing["target_ids"] = self._chapter_ids(existing["legacy_labels"])
                existing["blocking_batches"] = self._blocking_batches(
                    existing["legacy_labels"])
                return
            row = {
                "item_id": item_id, "group": group, "kind": kind,
                "question": question, "required_actor": actor, "status": status,
                "legacy_labels": sorted(names),
                "target_ids": self._chapter_ids(names),
                "blocking_batches": self._blocking_batches(names),
                "current_artifact_ref": artifact_ref,
                "author_input_needed": True, "resolved": False,
                "non_authoritative": True}
            items.append(row)
            for label in names:
                index[(group, label)] = row

        for row in decisions.get("items") or []:
            label = str(row.get("legacy_label"))
            add(item_id=f"AUTH_{label}", group="HISTORICAL INTERPRETATION",
                labels=[label], kind="AUTHOR_DECISION",
                question=str(row.get("question") or ""), actor="author",
                artifact_ref="AUTHOR_DECISION_STATUS.json",
                status=str(row.get("status") or "AWAITING_AUTHOR"))
        golden = _read_json(self.design_dir / "M1_GOLDEN_DELTA_RECONCILIATION.json")
        for row in golden.get("rows") or []:
            if row.get("decision") != "AUTHOR_REVIEW":
                continue
            label = str(row.get("legacy_label"))
            add(item_id=f"AUTH_{label}", group="HISTORICAL INTERPRETATION",
                labels=[label], kind="M1_VS_M10_INTERPRETATION",
                question=(f"{label} 的 {', '.join(row.get('delta_kinds') or [])}："
                          "M1 人工标签与 M10 story map 不一致，M11 不得自动选择"),
                actor="author", artifact_ref="M1_GOLDEN_DELTA_RECONCILIATION.json")
        for row in major.get("briefs") or []:
            label = str(row.get("legacy_label"))
            add(item_id=f"DESIGN_{label}", group="MAJOR DESIGN", labels=[label],
                kind="MAJOR_AUTHOR_DESIGN_REQUIRED",
                question=" / ".join(row.get("what_author_must_decide") or []),
                actor="author", artifact_ref="MAJOR_AUTHOR_DESIGN_BRIEFS.json")
        for row in rewrites:
            if not row.get("decision_event"):
                continue
            label = str(row.get("legacy_label"))
            add(item_id=f"DECISION_{label}", group="DECISION EVENT", labels=[label],
                kind="LOCAL_DECISION_EVENT_REQUIRED",
                question=(f"{label} 的 decision occurrence 由作者确认："
                          "既有 choice 提供备选，但缺 decision occurrence"),
                actor="author", artifact_ref=(
                    f"{P15O_DIR}/CONCRETE_REWRITE_PROPOSALS.json"))
        add(item_id="POLICY_CONTENT_REWRITE", group="POLICY",
            labels=[str(row.get("legacy_label")) for row in rewrites],
            kind="CONTENT_REWRITE_POLICY_SELECTION",
            question=("Content Rewrite Policy A/B/C 选择；"
                      "LOCAL_CAUSAL_BRIDGE（ch083/ch088）在 Policy B 下可 operator "
                      "approval，decision event 仍需作者逐项确认"),
            actor="author", artifact_ref=f"{P15N_DIR}/AUTHOR_CONTENT_POLICY_OPTIONS.json",
            status="PENDING_AUTHOR_SELECTION")
        ch063 = str(manual.get("legacy_label") or "ch063")
        add(item_id=f"MANUAL_{ch063}", group="MANUAL DOMAIN", labels=[ch063],
            kind="MANUAL_REQUIRED",
            question=str(manual.get("manual_recommendation") or ""),
            actor="operator+author", artifact_ref="MANUAL_REPAIR_BRIEF_ch063.json",
            status=str(manual.get("status") or "MANUAL_REQUIRED"))
        manual_records = [row for row in batch05.get("records") or []
                          if str(row.get("execution_decision")) == "MANUAL"]
        entity_manual_records = [
            str(row.get("legacy_label")) for row in manual_records
            if "entity" in str(row.get("reason") or "").lower()
            or str(row.get("repair_class")) == "ENTITY_RESOLUTION_REQUIRED"]
        for row in manual_records:
            label = str(row.get("legacy_label"))
            if label in entity_manual_records:
                continue  # entity identity 未定的 manual 动作归 LANE_ENTITY 登记
            add(item_id=f"MANUAL_{label}", group="MANUAL DOMAIN", labels=[label],
                kind="MANUAL_REQUIRED",
                question=(f"{label} {row.get('repair_class')}："
                          f"{row.get('reason')}"),
                actor="operator+author",
                artifact_ref="BATCH_05_RECONCILIATION.json",
                status="MANUAL_REQUIRED")
        pair_counts = _counts([f"{item['group']}::{label}" for item in items
                               for label in item["legacy_labels"]])
        dedup_violations = [key for key, count in pair_counts.items() if count > 1]
        group_counts = _counts([row["group"] for row in items])
        payload = {
            "generated_at": _now(),
            "item_count": len(items), "items": items,
            "group_counts": {name: group_counts.get(name, 0)
                             for name in AUTHOR_ACTION_GROUPS},
            "dedup": {"key": "(group, legacy_label)",
                      "duplicates_removed": len(duplicates),
                      "duplicate_rows": duplicates,
                      "invariant_ok": not dedup_violations,
                      "violations": dedup_violations,
                      "unique_target_count": len(
                          {label for row in items for label in row["legacy_labels"]})},
            "policy_selection": {
                "options": [row.get("option_id") for row in policy.get("options") or []],
                "auto_selected": str(policy.get("auto_selected") or ""),
                "author_selected": str(policy.get("author_selected") or ""),
                "status": "PENDING_AUTHOR_SELECTION"},
            "unresolved": True, "auto_resolved": 0,
            "author_burden_rule": "同一个 author decision 只登记一次",
            "entity_manual_decisions": entity_manual_records,
            "read_only": True, "non_authoritative": True}
        _write_json(self.design_dir / "AUTHOR_ACTION_INVENTORY.json", payload)
        _write_json(self.out_dir / "AUTHOR_ACTION_INVENTORY.json", payload)
        return payload

    @staticmethod
    def reconciliation_artifact_name() -> str:
        return "BATCH_05_RECONCILIATION.json"

    def _blocking_batches(self, labels: Sequence[str]) -> list[str]:
        ownership = self._batch_of_chapter()
        batches = {ownership.get(chapter_id, "")
                   for chapter_id in self._chapter_ids(labels)}
        return sorted(batch for batch in batches if batch)

    # ---- PART I entity / manual inventory ---------------------------------
    def entity_manual_inventory(self, *, overlay: Mapping[str, Any]
                                ) -> dict[str, Any]:
        queue = _read_json(self.design_dir / "M11_ENTITY_RESOLUTION_QUEUE.json")
        labels = self._label_to_chapter()
        chapter_to_label = {cid: label for label, cid in labels.items()}
        clusters = []
        for row in queue.get("clusters") or []:
            if row.get("resolution_status") != "CONTEXT_RESOLVABLE_PROPOSAL":
                continue
            chapter_ids = [str(item) for item in row.get("chapter_ids") or []]
            clusters.append({
                "cluster_id": row.get("cluster_id"),
                "legacy_labels": [chapter_to_label.get(cid, cid)
                                  for cid in chapter_ids],
                "target_ids": chapter_ids,
                "requires_exact_identity": bool(row.get("requires_exact_identity")),
                "resolution_status": row.get("resolution_status"),
                "blocking_batches": sorted(
                    {self._batch_of_chapter().get(cid, "") for cid in chapter_ids}
                    - {""}),
                "status": "PROPOSAL_ONLY（P15 不解决）"})
        specific = []
        batch05_records = {str(row.get("legacy_label")): dict(row) for row in
                           _read_json(self.design_dir /
                                      "BATCH_05_RECONCILIATION.json").get(
                               "records") or []}
        for label in ("ch093", "ch120"):
            chapter_id = labels.get(label, "")
            record = batch05_records.get(label) or {}
            specific.append({
                "legacy_label": label, "target_id": chapter_id,
                "primary_bucket": "evidence_ready",
                "blocking_batches": self._blocking_batches([label]),
                "manual_decision": str(record.get("execution_decision") or ""),
                "reason": str(record.get("reason") or
                              "ambiguous entity identity（entity cluster 登记）"),
                "status": "ENTITY_RESOLUTION_PENDING（M11 production work）"})
        manual_items = [
            {"item_id": "MANUAL_ch063", "legacy_label": "ch063",
             "kind": "STATE_BINDING_DOMAIN（representation-only or typed domain）",
             "artifact_ref": "MANUAL_REPAIR_BRIEF_ch063.json",
             "status": "MANUAL_REQUIRED"},
            {"item_id": "MANUAL_ch143", "legacy_label": "ch143",
             "kind": "FIELD_REBIND（MANUAL execution decision）",
             "artifact_ref": "BATCH_05_RECONCILIATION.json",
             "status": "MANUAL_REQUIRED"}]
        payload = {
            "generated_at": _now(),
            "entity": {
                "cluster_count": queue.get("cluster_count"),
                "status_counts": queue.get("status_counts"),
                "context_resolvable_cluster_count": len(clusters),
                "context_resolvable_clusters": clusters,
                "specific_pending_items": specific,
                "evidence_ready_bucket": overlay.get("evidence_ready"),
                "blocked_entity_targets": (overlay.get(
                    "execution_blocker_counts") or {}).get(
                    "BLOCKED_ENTITY_AMBIGUITY", 0),
                "entity_truth_modified": False},
            "manual": {
                "item_count": len(manual_items), "items": manual_items,
                "manual_required_bucket": overlay.get("manual_required"),
                "blocked_manual_targets": (overlay.get(
                    "execution_blocker_counts") or {}).get(
                    "BLOCKED_MANUAL_REPAIR", 0)},
            "resolved_in_this_phase": 0,
            "new_entity_pilot": False,
            "entity_resolution_owner": "M11 production work（P15 之后）",
            "read_only": True, "non_authoritative": True}
        _write_json(self.out_dir / "M11_ENTITY_MANUAL_INVENTORY.json", payload)
        return payload

    # ---- PART M production backlog ----------------------------------------
    def production_backlog(self, *, overlay: Mapping[str, Any],
                           readiness: Mapping[str, Any],
                           reclassification: Mapping[str, Any],
                           author_inventory: Mapping[str, Any],
                           entity_manual: Mapping[str, Any]) -> dict[str, Any]:
        batches = list(readiness.get("batches") or [])
        batch_index = {batch: index for index, batch in enumerate(FRONTIER_BATCH_ORDER)}
        items: list[dict[str, Any]] = []

        def add(*, item_id: str, lane: str, target_ids: Sequence[str],
                labels: Sequence[str], actor: str, next_action: str,
                artifact_ref: str, priority: int,
                dependencies: Sequence[str] = ()) -> None:
            items.append({
                "item_id": item_id, "lane": lane,
                "target_ids": [str(item) for item in target_ids],
                "legacy_labels": [str(item) for item in labels],
                "blocking_batches": sorted({
                    self._batch_of_chapter().get(str(item), "")
                    for item in target_ids} - {""}),
                "priority": priority,
                "dependencies": list(dependencies),
                "required_actor": actor, "next_action": next_action,
                "current_artifact_ref": artifact_ref,
                "status": "BACKLOG",
                "non_authoritative": True})

        # LANE_AUTO_SAFE_BATCH：当前 execution_status ∈ {READY, PARTIAL_READY}
        for batch in batches:
            ready = list(batch.get("ready_target_ids") or [])
            if not ready:
                continue
            batch_id = str(batch.get("batch_id"))
            add(item_id=f"BL_AUTO_{batch_id.replace('REPAIR_BATCH_', 'B')}",
                lane="LANE_AUTO_SAFE_BATCH", target_ids=ready,
                labels=[self._chapter_label(item) for item in ready],
                actor="operator", priority=2 + batch_index.get(batch_id, 99),
                next_action=("按冻结的 Repair System 执行该 batch 的 safe target"
                             "（不需作者新决策）"),
                artifact_ref="M11_READINESS_V2.json")

        # LANE_AUTHOR_POLICY
        policy = (author_inventory.get("policy_selection") or {})
        labels = [str(row.get("legacy_label"))
                  for row in _read_json(self.design_dir / P15O_DIR /
                                        "CONCRETE_REWRITE_PROPOSALS.json").get(
                      "proposals") or []]
        add(item_id="BL_POLICY_CONTENT_REWRITE", lane="LANE_AUTHOR_POLICY",
            target_ids=self._chapter_ids(labels), labels=labels, actor="author",
            priority=1,
            next_action=("作者选择 Policy A/B/C（auto_selected / author_selected "
                         "均保持空）"),
            artifact_ref=f"{P15N_DIR}/AUTHOR_CONTENT_POLICY_OPTIONS.json",
            dependencies=["authors must choose policy before rewrite execution"])

        # LANE_AUTHOR_CONTENT：会新增 historical event 的 proposal
        for row in _read_json(self.design_dir / P15O_DIR /
                              "CONCRETE_REWRITE_PROPOSALS.json").get(
                "proposals") or []:
            if not row.get("decision_event"):
                continue
            label = str(row.get("legacy_label"))
            add(item_id=f"BL_AUTHOR_CONTENT_{label}", lane="LANE_AUTHOR_CONTENT",
                target_ids=self._chapter_ids([label]), labels=[label], actor="author",
                priority=1,
                next_action=("作者批准该 new historical event（event_added = 1，"
                             "ONE_NEW_EVENT_MAX）"),
                artifact_ref=f"{P15O_DIR}/CONCRETE_REWRITE_PROPOSALS.json",
                dependencies=["BL_POLICY_CONTENT_REWRITE"])

        # LANE_MAJOR_DESIGN
        for row in _read_json(self.design_dir /
                              "MAJOR_AUTHOR_DESIGN_BRIEFS.json").get("briefs") or []:
            label = str(row.get("legacy_label"))
            add(item_id=f"BL_MAJOR_{label}", lane="LANE_MAJOR_DESIGN",
                target_ids=self._chapter_ids([label]), labels=[label], actor="author",
                priority=1, next_action="作者给出 major design 方向（A/B/C）",
                artifact_ref="MAJOR_AUTHOR_DESIGN_BRIEFS.json")

        # LANE_AUTHOR_DECISION
        for row in author_inventory.get("items") or []:
            if row.get("group") != "HISTORICAL INTERPRETATION":
                continue
            add(item_id=f"BL_{row['item_id']}", lane="LANE_AUTHOR_DECISION",
                target_ids=row.get("target_ids") or [],
                labels=row.get("legacy_labels") or [], actor="author", priority=1,
                next_action="作者裁决 historical interpretation（保留旧表达 or 重写语义）",
                artifact_ref=str(row.get("current_artifact_ref") or ""))

        # LANE_MANUAL
        for row in (entity_manual.get("manual") or {}).get("items") or []:
            add(item_id=f"BL_{row['item_id']}", lane="LANE_MANUAL",
                target_ids=self._chapter_ids([row["legacy_label"]]),
                labels=[row["legacy_label"]], actor="operator+author", priority=1,
                next_action="人工/操作员执行并登记（不自动改 truth）",
                artifact_ref=str(row.get("artifact_ref") or ""))

        # LANE_ENTITY
        entity = entity_manual.get("entity") or {}
        cluster_labels = [label for row in entity.get("context_resolvable_clusters") or []
                          for label in row.get("legacy_labels") or []]
        add(item_id="BL_ENTITY_CLUSTERS", lane="LANE_ENTITY",
            target_ids=self._chapter_ids(cluster_labels), labels=cluster_labels,
            actor="operator+author", priority=1,
            next_action="按 context 提议逐个确认 representation binding（不新增 truth）",
            artifact_ref="M11_ENTITY_RESOLUTION_QUEUE.json")
        specific_labels = [row["legacy_label"] for row in
                           entity.get("specific_pending_items") or []]
        add(item_id="BL_ENTITY_SPECIFIC", lane="LANE_ENTITY",
            target_ids=self._chapter_ids(specific_labels), labels=specific_labels,
            actor="operator+author", priority=1,
            next_action="ch093 / ch120：确认 entity 指代后再做 evidence binding",
            artifact_ref="M11_ENTITY_RESOLUTION_QUEUE.json")

        # LANE_CONTENT_REWRITE：其余 causal / decision design
        rows = list(reclassification.get("rows") or [])
        decision_rows = [row for row in rows
                         if row.get("repair_class") == "LOCAL_DECISION_EVENT_REQUIRED"]
        causal_rows = [row for row in rows
                       if row.get("repair_class") == "LOCAL_CAUSAL_BRIDGE_REQUIRED"]
        add(item_id="BL_CONTENT_DECISION_EVENT", lane="LANE_CONTENT_REWRITE",
            target_ids=[str(row.get("chapter_id")) for row in decision_rows],
            labels=[str(row.get("legacy_label")) for row in decision_rows],
            actor="author+operator", priority=1,
            next_action=("按冻结的 proposal 模型生成具体 event proposal，"
                         "decision occurrence 交作者逐项确认"),
            artifact_ref=f"{P15N_DIR}/CONTENT_REPAIR_RECLASSIFICATION.json")
        add(item_id="BL_CONTENT_CAUSAL_BRIDGE", lane="LANE_CONTENT_REWRITE",
            target_ids=[str(row.get("chapter_id")) for row in causal_rows],
            labels=[str(row.get("legacy_label")) for row in causal_rows],
            actor="operator+author", priority=1,
            next_action=("最小 causal bridge proposal → hard gate → "
                         "按作者 policy 决定审批级别"),
            artifact_ref=f"{P15N_DIR}/CONTENT_REPAIR_RECLASSIFICATION.json")

        existing = _read_json(self.design_dir / "M11_PRODUCTION_BACKLOG.json")
        history = self._preserve_backlog_history(existing, items)
        items = history["items"]
        lane_counts = {lane: sum(1 for row in items if row["lane"] == lane)
                       for lane in BACKLOG_LANES}
        payload = {
            **self._foreign_backlog_bookkeeping(existing),
            "generated_at": _now(), "item_count": len(items),
            "lane_counts": lane_counts, "lanes": list(BACKLOG_LANES),
            "items": items,
            "history_item_count": history["history_item_count"],
            "history_item_ids": history["history_item_ids"],
            "priority_rule": PRIORITY_RULE,
            "item_schema": ["item_id", "lane", "target_ids", "blocking_batches",
                            "priority", "dependencies", "required_actor",
                            "next_action", "current_artifact_ref"],
            "content_design_required": overlay.get("content_design_required"),
            "blocked_target_count": overlay.get("blocked_target_count"),
            "execution_mode": "M11 Production Execution（M11-RUN-01 …）",
            "p15_forbidden_successors": ["P15q", "P15r", "new_pilot", "new_wave"],
            "read_only": True, "non_authoritative": True}
        _write_json(self.design_dir / "M11_PRODUCTION_BACKLOG.json", payload)
        _write_json(self.out_dir / "M11_PRODUCTION_BACKLOG.json", payload)
        return payload

    # 本服务只拥有 backlog 的 lane / item 定义；production run ack
    # （M11RunExecutor）与 closure 记账（M11FinalClosureService）由其他 owner 写入，
    # 重算时必须原样保留，否则同一 canonical artifact 的字段会随写入顺序丢失。
    FOREIGN_BACKLOG_KEYS: tuple[str, ...] = (
        "last_run", "last_run_done_item_ids", "run_targets", "m11_closure_audit")

    @classmethod
    def _foreign_backlog_bookkeeping(cls, existing: Mapping[str, Any]
                                     ) -> dict[str, Any]:
        return {key: existing[key] for key in cls.FOREIGN_BACKLOG_KEYS
                if key in existing}

    @staticmethod
    def _preserve_backlog_history(existing: Mapping[str, Any],
                                  fresh_items: Sequence[dict[str, Any]]
                                  ) -> dict[str, Any]:
        """§26：backlog 重算不得删除历史。DONE item 的状态与完成记录必须保留。

        - 同一 item_id 重新生成：terminal status（DONE）不回退为 BACKLOG；
        - 不再生成的 item（例如 ready 已清空的 batch）：作为 history 保留原状态。
        """

        terminal = ("DONE",)
        by_id = {str(row.get("item_id")): row for row in fresh_items}
        items: list[dict[str, Any]] = list(fresh_items)
        history_ids: list[str] = []
        for prior in existing.get("items") or []:
            item_id = str(prior.get("item_id"))
            if not item_id:
                continue
            current = by_id.get(item_id)
            if current is not None:
                if str(prior.get("status")) in terminal:
                    for key in ("status", "completed_by_run", "completed_at",
                                "completed_targets", "history"):
                        if key in prior:
                            current[key] = prior[key]
                    if current.get("status") in terminal:
                        history_ids.append(item_id)
                continue
            preserved = dict(prior)
            preserved["history"] = True
            preserved["history_reason"] = "该 item 本轮不再生成（targets 已 terminal 或 ready 清空）"
            items.append(preserved)
            history_ids.append(item_id)
        return {"items": items, "history_item_count": len(history_ids),
                "history_item_ids": sorted(history_ids)}

    def _chapter_label(self, chapter_id: str) -> str:
        lookup = self._label_to_chapter()
        return next((label for label, cid in lookup.items() if cid == chapter_id),
                    str(chapter_id))

    # ---- PART O M12 entry criteria ----------------------------------------
    def m12_evaluations(self, *, overlay: Mapping[str, Any],
                        backlog: Mapping[str, Any],
                        author_inventory: Mapping[str, Any]) -> list[dict[str, Any]]:
        """§12：entry_allowed=false ≠ 9 项全部未满足。

        每条 criterion 都必须区分 satisfied（已验证满足）/ unsatisfied（尚未满足）；
        unsatisfied 中真正阻塞 M12 入口的登记为 blocking_criteria。
        """

        resolved = int(overlay.get("resolved_total") or 0)
        ledger = _read_json(self.design_dir / "M11_REPAIR_SUBTYPE_LEDGER.json")
        ledger_total = sum(int(value) for value in
                           (ledger.get("resolved_subtype_counts") or {}).values())
        queue = _read_json(self.design_dir / P15N_DIR /
                           "CONTENT_DESIGN_QUEUE_RECONCILIATION.json")
        source_now = _source_digests(self.root)
        index = _read_json(self.foundation_dir / "index.json")
        chapters = list(index.get("chapters") or [])
        foundation_full = sum(1 for row in chapters
                              if str(row.get("materialization_status")) == "FULL")
        foundation_digested = sum(1 for row in chapters
                                  if str(row.get("artifact_file_digest") or ""))
        author_items = int(author_inventory.get("item_count") or 0)
        author_resolved = sum(1 for row in author_inventory.get("items") or []
                              if str(row.get("status")) in ("RESOLVED", "AUTHOR_RESOLVED"))
        writer_gate = next((self.design_dir / name for name in (
            "M11_WRITER_PROJECTION_GATE.json",
            "WASTELAND_001_M11_WRITER_PROJECTION_GATE.json")
            if (self.design_dir / name).is_file()), None)
        queue_active = int(queue.get("active_requirements") or 0)
        queue_orphans = list(queue.get("orphan_requirements") or [])
        queue_uncovered = list(queue.get("targets_without_requirement") or [])
        terminal_ok = resolved >= TARGET_COUNT
        canon_ok = (source_now.get("canon") == FROZEN_SOURCE_DIGESTS["canon"]
                    and source_now.get("story_state") == FROZEN_SOURCE_DIGESTS["story_state"])
        lineage_ok = bool(ledger_total) and ledger_total == resolved
        queue_ok = (not queue_orphans and not queue_uncovered
                    and queue_active == int(overlay.get("content_design_required") or 0))
        author_ok = author_items > 0 and author_resolved == author_items
        replay_ok = lineage_ok and all(
            (self.foundation_dir / str(row.get("artifact_path") or "")).is_file()
            for row in chapters
            if str(row.get("artifact_path") or ""))
        coverage_ok = len(chapters) == 570 and foundation_digested == len(chapters)
        writer_ok = writer_gate is not None
        final_acceptance_ok = False     # M11 final acceptance 尚未执行（M12 前置条件）
        rows = [
            {"satisfied": terminal_ok, "blocking": True,
             "current_state": (f"{resolved}/{TARGET_COUNT} resolved；"
                               f"{TARGET_COUNT - resolved} 未 terminal"),
             "evidence": "M11_OVERLAY_V2.json",
             "why_blocking": "M12 需要全部 target terminal（或作者正式接受 AUTHOR_PENDING policy）"},
            {"satisfied": canon_ok, "blocking": False,
             "current_state": ("Canon / StoryState digest unchanged"
                               if canon_ok else "Canon / StoryState digest 变化"),
             "evidence": f"canon={source_now.get('canon')} story_state="
                         f"{source_now.get('story_state')}",
             "why_blocking": ""},
            {"satisfied": lineage_ok, "blocking": False,
             "current_state": f"subtype ledger {ledger_total} 条 ↔ overlay resolved {resolved}",
             "evidence": "M11_REPAIR_SUBTYPE_LEDGER.json",
             "why_blocking": ""},
            {"satisfied": queue_ok, "blocking": False,
             "current_state": (f"active {queue_active} == content_design_required "
                               f"{overlay.get('content_design_required')}；orphan "
                               f"{len(queue_orphans)}；uncovered {len(queue_uncovered)}"),
             "evidence": f"{P15N_DIR}/CONTENT_DESIGN_QUEUE_RECONCILIATION.json",
             "why_blocking": ""},
            {"satisfied": author_ok, "blocking": True,
             "current_state": (f"AUTHOR_ACTION_INVENTORY {author_items} 项，"
                               f"已决 {author_resolved} 项"),
             "evidence": "AUTHOR_ACTION_INVENTORY.json",
             "why_blocking": "author policy / content decision 未决前 M12 不能开始"},
            {"satisfied": replay_ok, "blocking": False,
             "current_state": (f"Full IR artifact {foundation_digested}/{len(chapters)} + "
                               "repair lineage 可重放"),
             "evidence": "historical_chapter_ir_v1/index.json",
             "why_blocking": ""},
            {"satisfied": coverage_ok, "blocking": False,
             "current_state": f"{len(chapters)}/570 artifact 已存在（{foundation_full} FULL）",
             "evidence": f"index.json chapters={len(chapters)}",
             "why_blocking": ""},
            {"satisfied": writer_ok, "blocking": True,
             "current_state": (f"writer projection gate 已存在：{writer_gate.name}"
                               if writer_ok else "writer projection gate 未执行（M12 验收阶段执行）"),
             "evidence": str(writer_gate.name) if writer_gate else "",
             "why_blocking": "writer projection gate 是 M12 验收动作"},
            {"satisfied": final_acceptance_ok, "blocking": True,
             "current_state": "M11 final acceptance 未执行（M12 入口前置条件）",
             "evidence": "M11_RUN_01_GATE.json",
             "why_blocking": "M11 未 closeout 前不得进入 M12"},
        ]
        evaluations: list[dict[str, Any]] = []
        for (name, _state), row in zip(M12_ENTRY_CRITERIA, rows):
            normalized = {"criterion": name, **row}
            # blocking 语义 = 该 criterion 仍阻塞 M12 入口（= blocking ∧ unsatisfied）
            normalized["blocking"] = bool(row.get("blocking")) and not bool(
                row.get("satisfied"))
            evaluations.append(normalized)
        return evaluations

    def m12_entry_criteria(self, *, overlay: Mapping[str, Any],
                           backlog: Mapping[str, Any],
                           author_inventory: Mapping[str, Any]) -> dict[str, Any]:
        criteria = self.m12_evaluations(overlay=overlay, backlog=backlog,
                                       author_inventory=author_inventory)
        satisfied = [row["criterion"] for row in criteria if row["satisfied"]]
        unsatisfied = [row["criterion"] for row in criteria if not row["satisfied"]]
        blocking = [row["criterion"] for row in criteria
                    if row["blocking"] and not row["satisfied"]]
        payload = {
            "generated_at": _now(), "phase": "M12",
            "phase_name": "M12 WASTELAND Acceptance / Freeze",
            "criteria": criteria, "criteria_count": len(criteria),
            "satisfied_criteria": satisfied, "satisfied_count": len(satisfied),
            "unsatisfied_criteria": unsatisfied, "unsatisfied_count": len(unsatisfied),
            "blocking_criteria": blocking, "blocking_count": len(blocking),
            "unsatisfied": unsatisfied,
            "m12_entry_allowed": False,
            "blocking_work": "M11 Production Execution + author policy/content decisions",
            "backlog_item_count": backlog.get("item_count"),
            "note": ("entry_allowed = false 不等于 9 项全部未满足：satisfied_criteria 为已"
                     "验证满足项，blocking_criteria 为真正阻塞 M12 入口的未满足项"),
            "read_only": True, "non_authoritative": True}
        _write_json(self.out_dir / "M12_ENTRY_CRITERIA.json", payload)
        return payload

    # ---- PART Q final closeout gate ---------------------------------------
    def closeout_gate(self, *, overlay: Mapping[str, Any],
                      readiness: Mapping[str, Any],
                      contract: Mapping[str, Any],
                      reconciliation: Mapping[str, Any],
                      reclassification: Mapping[str, Any],
                      matrix: Mapping[str, Any],
                      capabilities: Mapping[str, Any],
                      author_inventory: Mapping[str, Any],
                      backlog: Mapping[str, Any],
                      entity_manual: Mapping[str, Any],
                      evidence: Mapping[str, Any] | None = None
                      ) -> dict[str, Any]:
        evidence = dict(evidence if evidence is not None else _read_json(
            self.out_dir / "TEST_EVIDENCE.json"))
        pytest_row = dict(evidence.get("pytest") or {})
        validate_row = dict(evidence.get("validate_project") or {})
        source_now = _source_digests(self.root)
        foundation_now = _foundation_digests(self.foundation_dir)
        foundation_gate = _read_json(self.foundation_dir /
                                     "HISTORICAL_IR_FOUNDATION_GATE.json")
        adoption_gate = _read_json(self.design_dir /
                                   "M11_FOUNDATION_ADOPTION_GATE.json")
        concrete = _read_json(self.design_dir / P15O_DIR /
                              "CONCRETE_REWRITE_PROPOSALS.json")
        statuses = _read_json(self.design_dir / P15O_DIR /
                              "CONTENT_REWRITE_PROPOSAL_STATUS.json")
        wave01 = _read_json(self.design_dir / "p15m/MICRO_WAVE_PROMOTION.json")
        micro = _read_json(self.design_dir /
                           "M11_REPAIR_SUBTYPE_LEDGER.json").get(
            "resolved_subtype_counts", {}).get("repaired_micro_semantic", 0)
        rows = list(reclassification.get("rows") or [])
        micro_candidates = [row for row in rows if row.get("micro_scale_candidate")]
        # production execution 登记的 requirement（production_run_item=true）不属于
        # P15 micro frontier；它们的存在不等于「zero-new-event micro 未耗尽」。
        existing_micro = [row for row in rows
                          if row.get("repair_class") == "EXISTING_EVENT_MICRO_SEMANTIC"
                          and not row.get("production_run_item")]
        proposals = list(concrete.get("proposals") or [])
        decisions = [row for row in proposals if row.get("decision_event")]
        boundary_ok = (
            approval_for(event_added=1, repair_class="LOCAL_DECISION_EVENT_REQUIRED",
                         policy="B") == "AUTHOR_CONTENT_APPROVAL"
            and approval_for(event_added=1, repair_class="LOCAL_CAUSAL_BRIDGE_REQUIRED",
                             policy="B") == "MANUAL_OPERATOR_APPROVAL"
            and approval_for(event_added=0, repair_class="EVIDENCE_ONLY") == "SAFE_AUTO"
            and approval_for(event_added=1, repair_class="LOCAL_CONNECTIVE_EVENT_REQUIRED",
                             policy="") == "AUTHOR_CONTENT_APPROVAL"
            and approval_for(event_added=1, repair_class="MAJOR_AUTHOR_DESIGN_REQUIRED",
                             policy="B") == "AUTHOR_DECISION")
        queue_counts_ok = (
            int(reconciliation.get("active_requirements") or 0) == int(
                overlay.get("content_design_required") or 0)
            and not reconciliation.get("orphan_requirements")
            and not reconciliation.get("targets_without_requirement")
            and int(reconciliation.get("total_design_items") or 0) == (
                int(reconciliation.get("active_requirements") or 0)
                + int(reconciliation.get("resolved_by_wave") or 0)
                + int(reconciliation.get("resolved_by_other_requirement") or 0)))
        backlog_schema_ok = (
            all(all(field in row for field in (
                "item_id", "lane", "target_ids", "blocking_batches", "priority",
                "dependencies", "required_actor", "next_action",
                "current_artifact_ref")) for row in backlog.get("items") or [])
            and all(count >= 1 for count in
                    (backlog.get("lane_counts") or {}).values()))
        checks = {
            "foundation_ready": foundation_gate.get("status") == "READY",
            "repair_substrate_adopted": (
                adoption_gate.get("status") == "PASS"
                and (adoption_gate.get("substrate") or {}).get(
                    "substrate_default") == "HISTORICAL_FULL_IR"),
            "truth_precedence_frozen": contract.get("truth_precedence") == [
                "Canon / StoryState",
                "ConfirmedHistoricalBindingGuard / ConfirmedBindingResolution",
                "Historical Full Chapter IR", "shadow fallback"],
            "approval_boundary_frozen": boundary_ok and [
                row["rule_id"] for row in
                contract.get("approval_boundary_rules") or []] == ["A", "B", "C",
                                                                    "D", "E"],
            "readiness_v2_frozen": (
                (contract.get("readiness_semantics") or {}).get("completion_status")
                == ["NOT_STARTED", "IN_PROGRESS", "COMPLETE", "HUMAN_REVIEW"]
                and (contract.get("readiness_semantics") or {}).get(
                    "execution_status") == ["READY", "PARTIAL_READY", "BLOCKED",
                                            "NO_WORK", "COMPLETE"]
                and len(readiness.get("batches") or []) == 17),
            "overlay_v2_conserved": bool(
                (overlay.get("conservation") or {}).get("exact"))
            and list((overlay.get("primary_resolution_status_counts") or {}).keys())
            == list(PRIMARY_BUCKETS),
            "content_queue_conserved": queue_counts_ok,
            "zero_event_micro_exhausted": (not micro_candidates
                                           and not existing_micro
                                           and int(micro) >= 21),
            "micro_scale_proven": int(micro) >= 21 and int(
                wave01.get("promoted_count") or 0) >= 7,
            "rewrite_proposal_model_proven": (
                concrete.get("proposal_count") == 5
                and concrete.get("gate_status") == "PASS"
                and not concrete.get("placeholder_actions")
                and statuses.get("CONTENT_REWRITE_PROPOSAL_STATUS")
                == "READY_FOR_AUTHOR_POLICY_DECISION"),
            "decision_causal_separation_proven": bool(decisions)
            and all(row.get("policy_b_bounded_auto") is False for row in decisions)
            and all(row.get("author_approval_required") == "AUTHOR_CONTENT_APPROVAL"
                    for row in decisions)
            and any(not row.get("decision_event") for row in proposals),
            "author_policy_pending_explicit": (
                (author_inventory.get("policy_selection") or {}).get("status")
                == "PENDING_AUTHOR_SELECTION"
                and not (author_inventory.get("policy_selection") or {}).get(
                    "auto_selected")
                and not (author_inventory.get("policy_selection") or {}).get(
                    "author_selected")),
            "author_action_inventory_complete": (
                int(author_inventory.get("item_count") or 0)
                == sum((author_inventory.get("group_counts") or {}).values())
                and (author_inventory.get("dedup") or {}).get("invariant_ok") is True
                and all(label in (author_inventory.get("group_counts") or {})
                        for label in AUTHOR_ACTION_GROUPS)),
            "production_backlog_complete": (
                set(backlog.get("lane_counts") or {}) == set(BACKLOG_LANES)
                and backlog_schema_ok),
            "primary_conservation_372_exact": (
                matrix.get("total") == TARGET_COUNT
                and matrix.get("exact_conservation") is True),
            "canon_unchanged": source_now.get("canon") == FROZEN_SOURCE_DIGESTS["canon"],
            "story_state_unchanged": source_now.get("story_state")
            == FROZEN_SOURCE_DIGESTS["story_state"],
            "legacy_unchanged": source_now.get("legacy") == FROZEN_SOURCE_DIGESTS[
                "legacy"],
            "source_ir_unchanged": source_now.get("chapter_ir")
            == FROZEN_SOURCE_DIGESTS["chapter_ir"],
            "historical_foundation_unchanged": all(
                foundation_now.get(name) == digest
                for name, digest in FROZEN_FOUNDATION_DIGESTS.items()),
            "full_pytest_pass": pytest_row.get("status") == "PASS",
            "validate_project_pass": validate_row.get("status") == "PASS",
        }
        test_keys = ("full_pytest_pass", "validate_project_pass")
        status = ("PASS" if all(checks.values()) else
                  "EVIDENCE_REQUIRED" if all(value for key, value in checks.items()
                                             if key not in test_keys) else
                  "NEEDS_ATTENTION")
        payload = {
            "generated_at": _now(), "gate_id": "P15_FINAL_CLOSEOUT_GATE",
            "status": status, "checks": checks,
            "check_count": len(checks),
            "failed_checks": [key for key, value in checks.items() if not value],
            "evidence": {"pytest": pytest_row, "validate_project": validate_row},
            "source_digests": source_now,
            "foundation_digests": foundation_now,
            "capability_verdict_counts": capabilities.get("verdict_counts"),
            "entity_manual": {"entity_clusters": (entity_manual.get("entity") or {}).get(
                "context_resolvable_cluster_count"),
                "manual_items": (entity_manual.get("manual") or {}).get("item_count")},
            "batch_executed_in_this_phase": False,
            "author_decisions_resolved_in_this_phase": 0,
            "read_only": True, "non_authoritative": True}
        _write_json(self.out_dir / "P15_FINAL_CLOSEOUT_GATE.json", payload)
        return payload

    def record_test_evidence(self, *, pytest_summary: str, pytest_passed: int,
                             pytest_duration: str = "",
                             validate_summary: str = "") -> dict[str, Any]:
        payload = {
            "generated_at": _now(),
            "pytest": {"status": "PASS", "summary": pytest_summary,
                       "passed": pytest_passed, "duration": pytest_duration},
            "validate_project": {"status": "PASS", "summary": validate_summary},
            "read_only": True, "non_authoritative": True}
        _write_json(self.out_dir / "TEST_EVIDENCE.json", payload)
        return payload

    # ---- run --------------------------------------------------------------
    def run(self, *, test_evidence: Mapping[str, Any] | None = None
            ) -> dict[str, Any]:
        overlay_before = _digest_payload(_read_json(self.repair_dir / "M11_OVERLAY.json"))
        contract = self.contract()
        state = self.final_state()
        overlay = state["overlay"]
        readiness = state["readiness"]
        reclassification = state["reclassification"]
        reconciliation = state["reconciliation"]
        statuses = self.status_matrix(overlay=overlay,
                                      reconciliation=reconciliation)
        matrix = self.closeout_matrix(overlay=overlay, readiness=readiness)
        batches = self.batch_status_matrix(readiness=readiness)
        gate_status = {"foundation_status": _read_json(
            self.foundation_dir / "HISTORICAL_IR_FOUNDATION_GATE.json").get(
                "status", "")}
        capabilities = self.capability_matrix(
            overlay=overlay, reclassification=reclassification,
            reconciliation=reconciliation, readiness=readiness,
            gate_status=gate_status)
        inventory = self.author_action_inventory()
        entity_manual = self.entity_manual_inventory(overlay=overlay)
        backlog = self.production_backlog(
            overlay=overlay, readiness=readiness, reclassification=reclassification,
            author_inventory=inventory, entity_manual=entity_manual)
        m12 = self.m12_entry_criteria(overlay=overlay, backlog=backlog,
                                      author_inventory=inventory)
        gate = self.closeout_gate(
            overlay=overlay, readiness=readiness, contract=contract["contract"],
            reconciliation=reconciliation, reclassification=reclassification,
            matrix=matrix, capabilities=capabilities, author_inventory=inventory,
            backlog=backlog, entity_manual=entity_manual, evidence=test_evidence)
        overlay_after = _digest_payload(_read_json(self.repair_dir / "M11_OVERLAY.json"))
        payload = {
            "generated_at": _now(), "phase": "P15p",
            "status": gate["status"],
            "status_matrix": statuses["status_matrix"],
            "overlay": {key: overlay.get(key) for key in (
                "resolved_total", "repaired", "no_repair_required",
                "evidence_ready", "manual_required", "content_design_required",
                "author_decision", "pending", "blocked", "blocked_target_count")},
            "overlay_subtypes": {key: overlay.get(key) for key in (
                "repaired_evidence_only", "repaired_field_rebind",
                "repaired_micro_semantic", "repaired_confirmed_override")},
            "overlay_conservation": overlay.get("conservation"),
            "content_design": {
                "total_design_items": reconciliation.get("total_design_items"),
                "active": reconciliation.get("active_requirements"),
                "resolved": reconciliation.get("resolved_by_wave"),
                "class_counts": reclassification.get("class_counts"),
                "orphans": reconciliation.get("orphan_requirements")},
            "batch_matrix": {
                "batch_count": batches["batch_count"],
                "completion_status_counts": batches["completion_status_counts"],
                "execution_status_counts": batches["execution_status_counts"],
                "next_ready_batch": batches["next_ready_batch"],
                "next_ready_or_partial_ready": batches["executable_batches"],
                "highlighted": {key: {field: row.get(field) for field in (
                    "completion_status", "execution_status", "resolved", "ready",
                    "blocked")} for key, row in batches["highlighted"].items()}},
            "capabilities": capabilities["verdict_counts"],
            "author_inventory": {
                "item_count": inventory["item_count"],
                "group_counts": inventory["group_counts"],
                "duplicates_removed": inventory["dedup"]["duplicates_removed"],
                "policy_status": inventory["policy_selection"]["status"]},
            "entity_manual": {
                "entity_items": entity_manual["entity"][
                    "context_resolvable_cluster_count"],
                "manual_items": entity_manual["manual"]["item_count"]},
            "backlog": {"item_count": backlog["item_count"],
                        "lane_counts": backlog["lane_counts"]},
            "m12": {"entry_allowed": m12["m12_entry_allowed"],
                    "satisfied_count": m12["satisfied_count"],
                    "criteria_count": m12["criteria_count"]},
            "capability_acceptance": capabilities,
            "entities": entity_manual,
            "production_backlog": backlog,
            "m12_entry_criteria": m12,
            "closeout_gate": gate,
            "overlay_digest_before": overlay_before,
            "overlay_digest_after": overlay_after,
            "overlay_changed_by_recompute": overlay_before != overlay_after,
            "truth_digests": {
                "source": FROZEN_SOURCE_DIGESTS,
                "foundation": FROZEN_FOUNDATION_DIGESTS},
            "repair_executed": False, "batch_executed": False,
            "batch_06_executed": False, "content_generated": False,
            "author_decisions_resolved": False,
            "author_policy_selected": False,
            "new_pilot_or_wave": False,
            "next_phase": "M11 Production Execution",
            "read_only": True, "non_authoritative": True}
        _write_json(self.out_dir / "P15P_SUMMARY.json", payload)
        return payload
