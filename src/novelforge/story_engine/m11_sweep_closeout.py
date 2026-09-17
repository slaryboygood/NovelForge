"""M11-AUTO-SAFE-SWEEP-CLOSEOUT：Phase A closeout / phase transition。

这是 **closeout / phase-transition task**，不是 production repair run：

- 只做三件事：验证 Phase A AUTO_SAFE sweep 已结束、冻结 blocker phase 入口 baseline、
  更新 roadmap / milestone / audit（把 NEXT 从 RUN-12 切换为 M11-BLOCKER-00）；
- **不执行 repair / residual AUTO_SAFE / blocker lane / M11-BLOCKER-00 clustering**；
- **不实现** M11ClosureController / BlockerResolutionOrchestrator / RootBlockerGraph /
  ContentDesignResolver / EntityResolutionEngine / ManualRepairWorkbench /
  AuthorDecisionConsole（保持 PLANNED_ONLY）；
- 只写 closeout artifacts（新的只读快照），不修改 overlay / readiness / ledger /
  production backlog / queue / repair layer / truth boundary。

产物（`workspace/wasteland_001_exports/repair_adoption_v1/` 根）：

- `M11_AUTO_SAFE_SWEEP_FINAL_SNAPSHOT.json`
- `M11_BLOCKER_ENTRY_TARGETS.json`（149 non-terminal primary targets inventory）
- `M11_BLOCKER_ENTRY_BACKLOG_SNAPSHOT.json`
- `M11_BLOCKER_ENTRY_CDQ_SNAPSHOT.json`
- `M11_BLOCKER_00_ENTRY_BASELINE.json`
- `M11_AUTO_SAFE_SWEEP_CLOSEOUT.json`（verdict + exit checks + production digests）
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from novelforge.story_engine.historical_adoption import ADOPTION_DIR
from novelforge.story_engine.historical_ir import HISTORY_DIR
from novelforge.story_engine.m11_content_rewrite import ContentRewritePolicyService
from novelforge.story_engine.m11_micro_wave import MicroRepairFrontierPlanner
from novelforge.story_engine.m11_p15o import Wave02Service
from novelforge.story_engine.m11_p15p import (
    FROZEN_FOUNDATION_DIGESTS,
    FROZEN_SOURCE_DIGESTS,
)
from novelforge.story_engine.m11_run01 import (
    CONTRACT_FILE,
    DIGEST_ENCODING,
    GATE_V1_FILE,
    P15_ISOLATION_INVARIANT_ID,
    TARGET_COUNT,
    _digest_json,
    _git_state,
    _now,
    _read_json,
    _write_json,
)
from novelforge.story_engine.m11_run12 import M11Run12Service

CLOSEOUT_ID = "M11-AUTO-SAFE-SWEEP-CLOSEOUT"
PHASE_STATUS = "AUTO_SAFE_SWEEP_COMPLETE"
SNAPSHOT_FILE = "M11_AUTO_SAFE_SWEEP_FINAL_SNAPSHOT.json"
TARGETS_FILE = "M11_BLOCKER_ENTRY_TARGETS.json"
BACKLOG_FILE = "M11_BLOCKER_ENTRY_BACKLOG_SNAPSHOT.json"
CDQ_FILE = "M11_BLOCKER_ENTRY_CDQ_SNAPSHOT.json"
ENTRY_BASELINE_FILE = "M11_BLOCKER_00_ENTRY_BASELINE.json"
CLOSEOUT_FILE = "M11_AUTO_SAFE_SWEEP_CLOSEOUT.json"

AUTO_SAFE_RUN_IDS: tuple[str, ...] = tuple(f"M11_RUN_{index:02d}"
                                           for index in range(1, 13))
EXPECTED_BATCH_IDS: tuple[str, ...] = tuple(f"REPAIR_BATCH_{index:02d}"
                                            for index in range(1, 18))
BLOCKER_ENTRY_INVARIANTS: tuple[str, ...] = (
    "DERIVED_BLOCKER_COUNT_IS_NOT_EXECUTION_ITEM_COUNT",
    "ROOT_BLOCKER_FIRST",
    "AUTHOR_DECISION_IS_BATCHED",
    "P15_EXECUTOR_READ_ONLY_AFTER_CLOSEOUT",
    "TRUTH_BOUNDARY_UNCHANGED",
    "BLOCKER_00_BEFORE_LANE_EXECUTION",
    "NO_DIRECT_BACKLOG_DRAIN_BEFORE_ROOT_CAUSE_GRAPH",
)
BLOCKER_TO_DERIVED: Mapping[str, str] = {
    "BLOCKED_CONTENT_DESIGN": "content",
    "BLOCKED_ENTITY_AMBIGUITY": "entity",
    "BLOCKED_MANUAL_REPAIR": "manual",
    "BLOCKED_AUTHOR_DECISION": "author",
    "BLOCKED_CONFIRMED_BINDING_CONFLICT": "confirmed_binding",
}
OWNER_HINTS: Mapping[str, str] = {
    "content_design_required": "CONTENT_DESIGN",
    "manual_required": "MANUAL",
    "author_decision": "AUTHOR_DECISION",
    "evidence_ready": "AUTO_SAFE_RESIDUAL_CANDIDATE",
    "pending": "TRIAGE_REQUIRED",
    "entity_ambiguity": "ENTITY",
    "confirmed_binding_blocked": "CONFIRMED_BINDING",
}
TRUTH_RISK_HINTS: Mapping[str, str] = {
    "manual_required": "HIGH",
    "author_decision": "HIGH",
    "confirmed_binding_blocked": "HIGH",
    "content_design_required": "MEDIUM",
    "entity_ambiguity": "MEDIUM",
    "evidence_ready": "LOW",
    "pending": "UNKNOWN",
}


def _run_classes() -> list[type]:
    from novelforge.story_engine import (  # noqa: PLC0415 - 延迟 import 以避免环
        m11_run01, m11_run02, m11_run03, m11_run04, m11_run05, m11_run06,
        m11_run07, m11_run08, m11_run09, m11_run10, m11_run11, m11_run12,
    )
    return [m11_run01.M11Run01Service, m11_run02.M11Run02Service,
            m11_run03.M11Run03Service, m11_run04.M11Run04Service,
            m11_run05.M11Run05Service, m11_run06.M11Run06Service,
            m11_run07.M11Run07Service, m11_run08.M11Run08Service,
            m11_run09.M11Run09Service, m11_run10.M11Run10Service,
            m11_run11.M11Run11Service, m11_run12.M11Run12Service]


class M11SweepCloseoutService:
    """Phase A AUTO_SAFE sweep closeout（只读验证 + entry baseline 冻结）。"""

    def __init__(self, project_root: Path | str, *, design_dir: str = ADOPTION_DIR,
                 foundation_dir: str = HISTORY_DIR) -> None:
        self.root = Path(project_root).resolve()
        self.design_dir = (self.root / design_dir).resolve()
        self.foundation_dir = (self.root / foundation_dir).resolve()
        self.runner = M11Run12Service(self.root, design_dir=str(self.design_dir),
                                      foundation_dir=str(self.foundation_dir))

    # ------------------------------------------------------------ loaders
    def _overlay(self) -> dict[str, Any]:
        return _read_json(self.design_dir / "M11_OVERLAY_V2.json")

    def _readiness(self) -> dict[str, Any]:
        return _read_json(self.design_dir / "M11_READINESS_V2.json")

    def _ledger(self) -> dict[str, Any]:
        return _read_json(self.design_dir / "M11_REPAIR_SUBTYPE_LEDGER.json")

    def _backlog(self) -> dict[str, Any]:
        return _read_json(self.design_dir / "M11_PRODUCTION_BACKLOG.json")

    def _queue2(self) -> dict[str, Any]:
        return _read_json(self.design_dir / "M11_CONTENT_DESIGN_QUEUE_V2.json")

    def _queue3(self) -> dict[str, Any]:
        return _read_json(self.design_dir / "M11_CONTENT_DESIGN_QUEUE_V3.json")

    def _queue_recon(self) -> dict[str, Any]:
        return _read_json(self.design_dir / "p15n" /
                          "CONTENT_DESIGN_QUEUE_RECONCILIATION.json")

    def _m12_criteria(self) -> dict[str, Any]:
        return _read_json(self.design_dir / "p15p" / "M12_ENTRY_CRITERIA.json")

    def _states(self) -> tuple[Any, dict[str, str], dict[str, Any], dict[str, Any]]:
        inputs = self.runner.inputs()
        labels = self.runner.labels(inputs)
        states = self.runner.readiness.target_states(inputs=inputs)
        readiness = self.runner.readiness.build_readiness_v2(inputs=inputs,
                                                             persist=False)
        return inputs, labels, states, readiness

    # ------------------------------------------------------------ checks
    def auto_safe_runs_closed(self) -> dict[str, Any]:
        rows: list[dict[str, Any]] = []
        all_closed = True
        for klass in _run_classes():
            run_id = str(klass.run_id)
            run_dir = self.design_dir / klass.run_dir_name
            scope = _read_json(run_dir / f"{run_id}_EXECUTION_SCOPE.json")
            reconciliation = _read_json(self.design_dir / klass.reconciliation_file)
            gate = _read_json(run_dir / f"{run_id}_GATE.json")
            allowed = {str(item) for item in
                       list(scope.get(f"{klass.residual_key}_residual_targets") or [])
                       + list(scope.get(f"{klass.frontier_key}_ready_targets") or [])}
            executed = {str(row.get("chapter_id")) for row in
                        reconciliation.get("records") or []
                        if str(row.get("old_status")) == "not_processed"
                        and not str(row.get("new_resolution_status")
                                    ).startswith("BLOCKED_")}
            frontier_batch = str(klass.frontier_batch_id)
            frontier = next((row for row in
                             self._readiness().get("batches") or []
                             if row.get("batch_id") == frontier_batch), {})
            closed = (bool(scope.get("frozen")) and bool(reconciliation)
                      and str(gate.get("status")) == "PASS"
                      and not list(gate.get("failed_checks") or [])
                      and executed <= allowed
                      and not list(frontier.get("ready_target_ids") or []))
            all_closed = all_closed and closed
            rows.append({
                "run_id": run_id, "frontier_batch": frontier_batch,
                "scope_ready": len(scope.get(f"{klass.frontier_key}_ready_targets") or []),
                "scope_blocked": len(scope.get(f"{klass.frontier_key}_blocked_targets") or []),
                "executed": len(executed), "gate_status": gate.get("status"),
                "frontier_ready_now": len(frontier.get("ready_target_ids") or []),
                "scope_closed": closed})
        return {"runs": rows, "count": len(rows), "all_closed": all_closed}

    def p15_isolation_check(self) -> dict[str, Any]:
        overlay = self.design_dir / "M11_OVERLAY_V2.json"
        readiness = self.design_dir / "M11_READINESS_V2.json"
        ledger = self.design_dir / "M11_REPAIR_SUBTYPE_LEDGER.json"
        recon = self.design_dir / "M11_RUN_12_RECONCILIATION.json"
        targets = (("overlay", overlay), ("readiness", readiness),
                   ("ledger", ledger), ("recon", recon))
        before = {name: _digest_json(path) for name, path in targets}
        ContentRewritePolicyService(self.root).reclassify()
        MicroRepairFrontierPlanner(self.root).plan()
        Wave02Service(self.root).scope()
        after = {name: _digest_json(path) for name, path in targets}
        invariant = _read_json(self.design_dir / "m11_run_12" /
                               f"{P15_ISOLATION_INVARIANT_ID}.json")
        unchanged = before == after
        return {
            "invariant_id": P15_ISOLATION_INVARIANT_ID,
            "invariant_status": str(invariant.get("status") or ""),
            "static_scan_pass": bool(invariant.get("static_scan_pass")),
            "runtime_isolation_pass": bool(invariant.get("runtime_isolation_pass")),
            "production_item_ownership_pass": bool(
                invariant.get("production_item_ownership_pass")),
            "regression_digests_unchanged": unchanged,
            "digests": after,
            "contamination_regression": ["reclassify", "frontier planner",
                                        "wave-02 scope"],
            "status": ("PASS" if unchanged
                       and str(invariant.get("status")) == "PASS" else "FAIL"),
        }

    def exit_checks(self, *, p15: Mapping[str, Any] | None = None) -> dict[str, Any]:
        overlay = self._overlay()
        readiness = self._readiness()
        ledger = self._ledger()
        backlog = self._backlog()
        queue3 = self._queue3()
        queue_recon = self._queue_recon()
        p15 = dict(p15 or self.p15_isolation_check())
        batch_ids = [str(row.get("batch_id")) for row in readiness.get("batches") or []]
        batch_rows = {str(row.get("batch_id")): row
                      for row in readiness.get("batches") or []}
        classified = all(
            len(row.get("resolved_target_ids") or [])
            + len(row.get("blocked_target_ids") or [])
            == int(row.get("mutable_target_count") or 0)
            and len(row.get("resolved_target_ids") or [])
            + len(row.get("blocked_target_ids") or []) >= 1
            for row in readiness.get("batches") or [])
        status_counts = dict(readiness.get("execution_status_counts") or {})
        runs = self.auto_safe_runs_closed()
        final_scope = _read_json(self.design_dir / "m11_run_12" /
                                 "M11_RUN_12_EXECUTION_SCOPE.json")
        final_recon = _read_json(self.design_dir /
                                 "M11_RUN_12_RECONCILIATION.json")
        final_scope_ids = {str(item) for item in
                           list(final_scope.get("batch_17_ready_targets") or [])
                           + list(final_scope.get("batch_17_blocked_targets") or [])}
        final_recon_ids = {str(row.get("chapter_id")) for row in
                           final_recon.get("records") or []}
        ledger_counts = dict(ledger.get("resolved_subtype_counts") or {})
        ledger_resolved = sum(ledger_counts.values())
        v3_active_ids = {str(row.get("design_item_id")) for row in
                         queue3.get("requirements") or []
                         if str(row.get("status")) == "ACTIVE"}
        _, _, states, _ = self._states()
        overlay_cdr_ids = {cid for cid, state in states.items()
                           if str(state.primary_resolution_status)
                           == "content_design_required"}
        v3_active_chapters = {str(row.get("chapter_id")) for row in
                              queue3.get("requirements") or []
                              if str(row.get("status")) == "ACTIVE"}
        queue2 = self._queue2()
        queue_ids = [str(row.get("design_item_id")) for row in
                     queue2.get("items") or []]
        duplicates = sorted({item for item in queue_ids
                             if queue_ids.count(item) > 1})
        truth = self.runner.truth_digests()
        frozen = self.runner.frozen_digests()
        checks = {
            "all_17_batches_entered_production_execution": (
                sorted(batch_ids) == sorted(EXPECTED_BATCH_IDS) and classified),
            "no_repair_batch_18": "REPAIR_BATCH_18" not in batch_ids,
            "no_ready_or_partial_ready_batch": (
                sum(len(row.get("ready_target_ids") or [])
                    for row in readiness.get("batches") or []) == 0
                and not ({"READY", "PARTIAL_READY"} & set(status_counts))),
            "all_auto_safe_run_scopes_closed": bool(runs["all_closed"]),
            "final_frontier_scope_fully_processed": (
                final_scope_ids and final_scope_ids == final_recon_ids
                and len(final_scope.get("batch_17_ready_targets") or []) == 9),
            "no_scope_outside_execution": all(
                row["scope_closed"] for row in runs["runs"]),
            "p15_isolation_pass": str(p15.get("status")) == "PASS",
            "source_digests_unchanged": (
                truth.get("canon") == FROZEN_SOURCE_DIGESTS["canon"]
                and truth.get("story_state") == FROZEN_SOURCE_DIGESTS["story_state"]
                and truth.get("legacy") == FROZEN_SOURCE_DIGESTS["legacy"]
                and truth.get("chapter_ir") == FROZEN_SOURCE_DIGESTS["chapter_ir"]),
            "historical_foundation_unchanged": (
                truth.get("historical_foundation") == FROZEN_FOUNDATION_DIGESTS),
            "repair_contract_digest_unchanged":
                frozen.get("contract") == "67559aa55442d69e",
            "repair_gate_digest_unchanged":
                frozen.get("repair_gate") == "e1eab4c33ae75b01",
            "overlay_372_exact_conservation": bool(
                (overlay.get("conservation") or {}).get("exact"))
                and sum(dict(overlay.get("primary_resolution_status_counts") or {}
                             ).values()) == TARGET_COUNT,
            "subtype_ledger_resolved_matches_overlay": (
                ledger_resolved == int(overlay.get("resolved_total") or -1)
                and len(ledger.get("ledger") or []) == ledger_resolved),
            "queue_conservation_pass": (
                str(queue_recon.get("verdict") or "NO_DATA_LOSS") == "NO_DATA_LOSS"),
            "active_cdq_matches_overlay": (
                len(v3_active_ids) == len(v3_active_chapters)
                == int(overlay.get("content_design_required") or -1)
                and v3_active_chapters == overlay_cdr_ids
                and int(queue3.get("active_count") or -1)
                == int(overlay.get("content_design_required") or -2)),
            "queue_no_orphan_uncovered_duplicate": (
                not list(queue_recon.get("orphan_requirements") or [])
                and not list(queue_recon.get("targets_without_requirement") or [])
                and not duplicates),
        }
        return {
            "checks": checks,
            "failed_checks": sorted(key for key, value in checks.items() if not value),
            "verdict": "PASS" if all(checks.values()) else "FAIL",
            "auto_safe_runs": runs,
            "p15_isolation": p15,
            "backlog_auto_lane_all_done": all(
                str(row.get("status")) == "DONE" for row in backlog.get("items") or []
                if str(row.get("lane")) == "LANE_AUTO_SAFE_BATCH"),
        }

    # ------------------------------------------------------------ artifacts
    def final_snapshot(self, *, checks: Mapping[str, Any],
                       p15: Mapping[str, Any]) -> dict[str, Any]:
        overlay = self._overlay()
        readiness = self._readiness()
        ledger = self._ledger()
        backlog = self._backlog()
        queue2 = self._queue2()
        queue3 = self._queue3()
        queue_recon = self._queue_recon()
        batches = readiness.get("batches") or []
        remaining_ready = sum(len(row.get("ready_target_ids") or []) for row in batches)
        remaining_blocked = sum(len(row.get("blocked_target_ids") or [])
                                for row in batches)
        resolved_total = int(overlay.get("resolved_total") or 0)
        truth = self.runner.truth_digests()
        frozen = self.runner.frozen_digests()
        return {
            "generated_at": _now(), "closeout_id": CLOSEOUT_ID,
            "phase_status": PHASE_STATUS,
            "total_primary_targets": TARGET_COUNT,
            "resolved_total": resolved_total,
            "resolved_repaired": overlay.get("repaired"),
            "resolved_no_repair_required": overlay.get("no_repair_required"),
            "evidence_ready": overlay.get("evidence_ready"),
            "manual_required": overlay.get("manual_required"),
            "content_design_required": overlay.get("content_design_required"),
            "author_decision": overlay.get("author_decision"),
            "pending": overlay.get("pending"),
            "remaining_non_terminal": TARGET_COUNT - resolved_total,
            "batch_count": len(batches),
            "batch_execution_status_summary": dict(
                readiness.get("execution_status_counts") or {}),
            "batch_execution_status_matrix": {
                str(row.get("batch_id")): str(row.get("execution_status"))
                for row in batches},
            "remaining_ready_targets": remaining_ready,
            "remaining_blocked_targets": remaining_blocked,
            "subtype_ledger_summary": {
                "entry_count": len(ledger.get("ledger") or []),
                "resolved_subtype_counts": dict(ledger.get("resolved_subtype_counts") or {})},
            "production_backlog_summary": {
                "item_count": backlog.get("item_count"),
                "lane_counts": dict(backlog.get("lane_counts") or {}),
                "done_item_count": sum(1 for row in backlog.get("items") or []
                                       if str(row.get("status")) == "DONE")},
            "content_design_queue_summary": {
                "v2_item_count": queue2.get("item_count"),
                "v3_active_count": queue3.get("active_count"),
                "overlay_content_design_required": overlay.get("content_design_required"),
                "orphan_requirements": list(
                    queue_recon.get("orphan_requirements") or []),
                "uncovered": list(
                    queue_recon.get("targets_without_requirement") or [])},
            "truth_digests": truth,
            "historical_foundation_digests": truth.get("historical_foundation"),
            "repair_contract_digest": frozen.get("contract"),
            "repair_gate_digest": frozen.get("repair_gate"),
            "p15_isolation_status": p15.get("status"),
            "auto_safe_runs_completed": list(AUTO_SAFE_RUN_IDS),
            "auto_safe_runs_detail": checks.get("auto_safe_runs", {}).get("runs"),
            "closeout_checks": dict(checks.get("checks") or {}),
            "verdict": checks.get("verdict"),
            "read_only": True, "non_authoritative": True,
        }

    def blocker_entry_targets(self) -> dict[str, Any]:
        overlay = self._overlay()
        backlog = self._backlog()
        queue2 = self._queue2()
        inputs, labels, states, _ = self._states()
        backlog_refs: dict[str, list[str]] = {}
        backlog_ref_status: dict[str, dict[str, str]] = {}
        for row in backlog.get("items") or []:
            item_id = str(row.get("item_id"))
            item_status = str(row.get("status"))
            for target in row.get("target_ids") or []:
                backlog_refs.setdefault(str(target), []).append(item_id)
                backlog_ref_status.setdefault(str(target), {})[item_id] = item_status
        cdq_refs: dict[str, list[str]] = {}
        for row in queue2.get("items") or []:
            cdq_refs.setdefault(str(row.get("chapter_id")), []).append(
                str(row.get("design_item_id")))
        resolved_total = int(overlay.get("resolved_total") or 0)
        targets: list[dict[str, Any]] = []
        for chapter_id, state in sorted(states.items(),
                                        key=lambda item: str(labels.get(item[0])
                                                             or item[0])):
            if str(state.target_state) == "RESOLVED":
                continue
            status = str(state.primary_resolution_status)
            direct = [str(item) for item in state.execution_blockers]
            derived = sorted({BLOCKER_TO_DERIVED[item] for item in direct
                              if item in BLOCKER_TO_DERIVED})
            truth_risk = TRUTH_RISK_HINTS.get(status, "UNKNOWN")
            if "manual" in derived and truth_risk != "HIGH":
                truth_risk = "HIGH"
            targets.append({
                "target_id": str(chapter_id),
                "chapter": labels.get(str(chapter_id), ""),
                "source_batch": str(state.batch_id),
                "current_overlay_status": status,
                "current_readiness_status": {
                    "state": str(state.target_state), "reason": str(state.reason)},
                "current_direct_blockers": direct,
                "derived_blockers": derived,
                "existing_backlog_refs": sorted(backlog_refs.get(str(chapter_id), [])),
                "existing_backlog_ref_statuses": dict(
                    backlog_ref_status.get(str(chapter_id), {})),
                "content_design_requirement_refs": sorted(
                    cdq_refs.get(str(chapter_id), [])),
                "dependency_roots": [str(item) for item in state.blocking_source],
                "truth_risk": truth_risk,
                "current_owner_hint": OWNER_HINTS.get(status, "TRIAGE_REQUIRED"),
            })
        return {
            "generated_at": _now(), "closeout_id": CLOSEOUT_ID,
            "total_primary_targets": TARGET_COUNT,
            "terminal_targets": resolved_total,
            "non_terminal_targets": TARGET_COUNT - resolved_total,
            "count": len(targets),
            "basis": f"{TARGET_COUNT} primary targets − {resolved_total} terminal "
                     f"= {TARGET_COUNT - resolved_total} non-terminal",
            "owner_hint_semantics": ("current_owner_hint 只是 M11-BLOCKER-00 聚类输入，"
                                     "不是最终 Root Blocker owner 判定"),
            "targets": targets,
            "read_only": True, "non_authoritative": True,
        }

    def backlog_snapshot(self) -> dict[str, Any]:
        backlog = self._backlog()
        items = list(backlog.get("items") or [])
        auto_items = [row for row in items
                      if str(row.get("lane")) == "LANE_AUTO_SAFE_BATCH"]
        auto_all_done = all(str(row.get("status")) == "DONE" for row in auto_items)
        lane_status: dict[str, dict[str, int]] = {}
        for row in items:
            lane = str(row.get("lane"))
            bucket = lane_status.setdefault(lane, {"total": 0, "active": 0, "done": 0})
            bucket["total"] += 1
            if str(row.get("status")) == "DONE":
                bucket["done"] += 1
            else:
                bucket["active"] += 1
        return {
            "generated_at": _now(), "closeout_id": CLOSEOUT_ID,
            "item_count": backlog.get("item_count"),
            "lane_counts": dict(backlog.get("lane_counts") or {}),
            "lane_snapshot": lane_status,
            "done_item_count": sum(1 for row in items
                                   if str(row.get("status")) == "DONE"),
            "active_item_count": sum(1 for row in items
                                     if str(row.get("status")) != "DONE"),
            "done_item_ids": sorted(str(row.get("item_id")) for row in items
                                    if str(row.get("status")) == "DONE"),
            "auto_safe_lane": {
                "lane": "LANE_AUTO_SAFE_BATCH",
                "item_count": len(auto_items),
                "all_done": auto_all_done,
                "items": [{"item_id": str(row.get("item_id")),
                           "status": str(row.get("status")),
                           "completed_by_run": row.get("completed_by_run")}
                          for row in auto_items],
                "phase_status": "PHASE_A_COMPLETE"},
            "auto_safe_lane_rule": (
                "Phase A closeout 后 LANE_AUTO_SAFE_BATCH 不再作为新的 primary "
                "execution source；仅当 blocker resolution → readiness recompute → "
                "residual AUTO_SAFE 重新释放 target 时才恢复。"),
            "verdict": "PASS" if auto_all_done else "FAIL",
            "read_only": True, "non_authoritative": True,
        }

    def cdq_snapshot(self) -> dict[str, Any]:
        overlay = self._overlay()
        queue2 = self._queue2()
        queue3 = self._queue3()
        queue_recon = self._queue_recon()
        active = [row for row in queue3.get("requirements") or []
                  if str(row.get("status")) == "ACTIVE"]
        active_chapters = {str(row.get("chapter_id")) for row in active}
        _, _, states, _ = self._states()
        overlay_cdr = {cid for cid, state in states.items()
                       if str(state.primary_resolution_status)
                       == "content_design_required"}
        queue_ids = [str(row.get("design_item_id")) for row in
                     queue2.get("items") or []]
        duplicates = sorted({item for item in queue_ids
                             if queue_ids.count(item) > 1})
        return {
            "generated_at": _now(), "closeout_id": CLOSEOUT_ID,
            "v2_item_count": queue2.get("item_count"),
            "v2_item_ids": sorted(queue_ids),
            "v3_requirement_count": queue3.get("requirement_count"),
            "v3_active_count": len(active),
            "overlay_content_design_required": overlay.get("content_design_required"),
            "active_matches_overlay": active_chapters == overlay_cdr,
            "active_ids": sorted(str(row.get("design_item_id")) for row in active),
            "orphan_requirements": list(queue_recon.get("orphan_requirements") or []),
            "uncovered": list(queue_recon.get("targets_without_requirement") or []),
            "duplicate_design_item_ids": duplicates,
            "duplicate_ownership": duplicates,
            "resolved_by_closeout": 0,
            "verdict": ("PASS" if active_chapters == overlay_cdr
                        and not list(queue_recon.get("orphan_requirements") or [])
                        and not list(queue_recon.get("targets_without_requirement") or [])
                        else "FAIL"),
            "read_only": True, "non_authoritative": True,
        }

    def field_rebind_status(self) -> dict[str, Any]:
        cases: list[dict[str, str]] = []
        promoted = 0
        for run_id in AUTO_SAFE_RUN_IDS:
            path = self.design_dir / f"{run_id}_RECONCILIATION.json"
            for row in _read_json(path).get("records") or []:
                if str(row.get("repair_class")) != "FIELD_REBIND":
                    continue
                status = str(row.get("new_resolution_status"))
                cases.append({"chapter": str(row.get("legacy_label")),
                              "run_id": run_id, "resolution": status})
                if status == "RESOLVED_REPAIRED":
                    promoted += 1
        return {
            "capability": "NOT_PROVEN",
            "classification_seen": bool(cases),
            "safe_auto_production_promotion_proven": promoted > 0,
            "safe_auto_promotions": promoted,
            "natural_cases": cases,
        }

    def blocker_00_entry_baseline(self, *, snapshot: Mapping[str, Any],
                                  targets: Mapping[str, Any],
                                  backlog: Mapping[str, Any],
                                  cdq: Mapping[str, Any],
                                  checks: Mapping[str, Any],
                                  p15: Mapping[str, Any]) -> dict[str, Any]:
        overlay = self._overlay()
        criteria = self._m12_criteria()
        truth = self.runner.truth_digests()
        frozen = self.runner.frozen_digests()
        return {
            "generated_at": _now(), "baseline_id": "M11_BLOCKER_00_ENTRY_BASELINE",
            "source_commit": str((_git_state(self.root) or {}).get("commit") or ""),
            "auto_safe_sweep_status": "COMPLETE",
            "closeout_status": checks.get("verdict"),
            "total_primary_targets": TARGET_COUNT,
            "terminal_targets": snapshot.get("resolved_total"),
            "non_terminal_targets": snapshot.get("remaining_non_terminal"),
            "non_terminal_target_ids": sorted(
                str(row.get("target_id")) for row in targets.get("targets") or []),
            "overlay_summary": {
                "primary_resolution_status_counts": dict(
                    overlay.get("primary_resolution_status_counts") or {}),
                "resolved_total": overlay.get("resolved_total"),
                "remaining_repair_targets": overlay.get("remaining_repair_targets"),
                "conservation": dict(overlay.get("conservation") or {})},
            "backlog_summary": {
                "item_count": backlog.get("item_count"),
                "lane_counts": dict(backlog.get("lane_counts") or {}),
                "auto_lane_all_done": (backlog.get("auto_safe_lane") or {}).get(
                    "all_done")},
            "cdq_summary": {
                "v2_item_count": cdq.get("v2_item_count"),
                "v3_active_count": cdq.get("v3_active_count"),
                "overlay_content_design_required": cdq.get(
                    "overlay_content_design_required"),
                "active_matches_overlay": cdq.get("active_matches_overlay")},
            "batch_summary": {
                "batch_count": snapshot.get("batch_count"),
                "execution_status_counts": dict(
                    snapshot.get("batch_execution_status_summary") or {}),
                "remaining_ready_targets": snapshot.get("remaining_ready_targets"),
                "remaining_blocked_targets": snapshot.get("remaining_blocked_targets")},
            "derived_blocker_projection": {
                "occurrence_counts": dict(overlay.get("execution_blocker_counts") or {}),
                "blocked_occurrence_count": overlay.get("blocked"),
                "blocked_target_count": overlay.get("blocked_target_count"),
                "note": ("multi-value derived projection；"
                         "DERIVED_BLOCKER_COUNT_IS_NOT_EXECUTION_ITEM_COUNT")},
            "truth_digests": truth,
            "historical_foundation_digests": truth.get("historical_foundation"),
            "contract_digest": frozen.get("contract"),
            "gate_digest": frozen.get("repair_gate"),
            "p15_isolation_status": p15.get("status"),
            "m12_entry_status": {
                "m12_entry_allowed": bool(criteria.get("m12_entry_allowed")),
                "satisfied_count": criteria.get("satisfied_count"),
                "unsatisfied_count": criteria.get("unsatisfied_count"),
                "blocking_count": criteria.get("blocking_count"),
                "criteria_count": criteria.get("criteria_count")},
            "blocker_layer_status": "PLANNED_ONLY",
            "blocker_layer_phase_status": "NEXT_PHASE_PLANNED",
            "field_rebind_status": self.field_rebind_status(),
            "entry_invariants": list(BLOCKER_ENTRY_INVARIANTS),
            "entry_invariant_semantics": {
                "BLOCKER_00_BEFORE_LANE_EXECUTION": (
                    "在 M11-BLOCKER-00 完成 Root Blocker Inventory / Graph / Unlock "
                    "Impact 之前，禁止直接执行 AUTHOR / ENTITY / MANUAL / "
                    "CONTENT_REWRITE lane"),
                "NO_DIRECT_BACKLOG_DRAIN_BEFORE_ROOT_CAUSE_GRAPH": (
                    "不允许因为 backlog 已有 16 Manual / 31 Content Rewrite 就直接按 "
                    "backlog 顺序逐项处理")},
            "read_only": True, "non_authoritative": True,
        }

    # ------------------------------------------------------------ run
    def run(self) -> dict[str, Any]:
        overlay_path = self.design_dir / "M11_OVERLAY_V2.json"
        readiness_path = self.design_dir / "M11_READINESS_V2.json"
        ledger_path = self.design_dir / "M11_REPAIR_SUBTYPE_LEDGER.json"
        backlog_path = self.design_dir / "M11_PRODUCTION_BACKLOG.json"
        before = {name: _digest_json(path) for name, path in (
            ("overlay", overlay_path), ("readiness", readiness_path),
            ("ledger", ledger_path), ("backlog", backlog_path))}
        p15 = self.p15_isolation_check()
        checks = self.exit_checks(p15=p15)
        snapshot = self.final_snapshot(checks=checks, p15=p15)
        targets = self.blocker_entry_targets()
        backlog = self.backlog_snapshot()
        cdq = self.cdq_snapshot()
        baseline = self.blocker_00_entry_baseline(
            snapshot=snapshot, targets=targets, backlog=backlog, cdq=cdq,
            checks=checks, p15=p15)
        after = {name: _digest_json(path) for name, path in (
            ("overlay", overlay_path), ("readiness", readiness_path),
            ("ledger", ledger_path), ("backlog", backlog_path))}
        production_unchanged = before == after
        payload = {
            "generated_at": _now(), "closeout_id": CLOSEOUT_ID,
            "phase": "M11 Phase A — AUTO_SAFE Sweep closeout",
            "phase_status": PHASE_STATUS,
            "status": "PASS" if checks["verdict"] == "PASS" and production_unchanged
                      and backlog["verdict"] == "PASS" and cdq["verdict"] == "PASS"
                      else "FAIL",
            "closeout_checks": dict(checks["checks"]),
            "failed_checks": list(checks["failed_checks"]),
            "auto_safe_runs": checks["auto_safe_runs"],
            "p15_isolation": p15,
            "production_state_digests_before": before,
            "production_state_digests_after": after,
            "production_state_unchanged": production_unchanged,
            "artifacts": {
                "final_snapshot": SNAPSHOT_FILE,
                "blocker_entry_targets": TARGETS_FILE,
                "backlog_snapshot": BACKLOG_FILE,
                "cdq_snapshot": CDQ_FILE,
                "blocker_00_entry_baseline": ENTRY_BASELINE_FILE,
                "closeout_summary": CLOSEOUT_FILE},
            "entry_invariants": list(BLOCKER_ENTRY_INVARIANTS),
            "blocker_layer_status": "PLANNED_ONLY",
            "blocker_layer_phase_status": "NEXT_PHASE_PLANNED",
            "next_phase": "M11-BLOCKER-00",
            "m12_entry_allowed": False,
            "read_only": True, "non_authoritative": True,
        }
        _write_json(self.design_dir / SNAPSHOT_FILE, snapshot)
        _write_json(self.design_dir / TARGETS_FILE, targets)
        _write_json(self.design_dir / BACKLOG_FILE, backlog)
        _write_json(self.design_dir / CDQ_FILE, cdq)
        _write_json(self.design_dir / ENTRY_BASELINE_FILE, baseline)
        _write_json(self.design_dir / CLOSEOUT_FILE, payload)
        return payload


__all__ = [
    "AUTO_SAFE_RUN_IDS",
    "BACKLOG_FILE",
    "BLOCKER_ENTRY_INVARIANTS",
    "CDQ_FILE",
    "CLOSEOUT_FILE",
    "CLOSEOUT_ID",
    "ENTRY_BASELINE_FILE",
    "EXPECTED_BATCH_IDS",
    "M11SweepCloseoutService",
    "PHASE_STATUS",
    "SNAPSHOT_FILE",
    "TARGETS_FILE",
]
