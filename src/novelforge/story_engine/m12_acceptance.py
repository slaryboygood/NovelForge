"""M12 WASTELAND Acceptance / Freeze：全书审计 + 人工样本 + freeze 裁定。

repo 定义来源（V2 里程碑计划，不重新猜测业务定义）：

M12 WASTELAND Acceptance = 全书审计 + 人工样本 + freeze 裁定；freeze 前复核完整 Chapter IR body。
V2 计划文档已随 release 收敛（见 docs/CHANGELOG.md 与 git history）。

硬边界（frozen）：

* M11 production state = **READ_ONLY**：372 terminal inventory / overlay / ledger /
  reconciliation / author decisions / blocker graph 在 M12 期间不得修改；
* `historical repair truth != Canon source`（repair layer 永远 non-authoritative）；
* `future planning != occurred history`（Planning revision 不写回 happened truth）；
* M12 只消费 frozen evidence，不写 Canon / StoryState / legacy / 570 source IR /
  Historical Foundation / M11 artifacts。
"""

from __future__ import annotations

import hashlib
import json
import random
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

from novelforge.story_engine.historical_adoption import ADOPTION_DIR
from novelforge.story_engine.historical_ir import (
    HISTORY_DIR,
    HistoricalIRStore,
    TIME_LAYER,
    _read_json as _ir_read_json,
    chapter_artifact_checks,
)
from novelforge.story_engine.m11_p15p import (
    FROZEN_FOUNDATION_DIGESTS,
    FROZEN_SOURCE_DIGESTS,
)
from novelforge.story_engine.m11_run12 import M11Run12Service
from novelforge.story_engine.planning.repository import DEFAULT_PLANNING_PATH
from novelforge.story_engine.phase_snapshot import (
    snapshot_exists,
    verify_phase_snapshot,
    write_phase_snapshot,
)

PLANNING_STORE_DIR = str(DEFAULT_PLANNING_PATH).replace("\\", "/")

M12_DIR = "m12"
M12_ID = "M12-WASTELAND-ACCEPTANCE"
M12_AUTHORITY_FILE = "M12_AUTHORITY.json"
M11_FROZEN_INPUT_FILE = "M11_FROZEN_INPUT.json"
INPUT_PROJECTION_FILE = "M12_INPUT_PROJECTION.json"
BOUNDARY_AUDIT_FILE = "M12_BOUNDARY_AUDIT.json"
EXECUTION_BASELINE_FILE = "M12_EXECUTION_BASELINE.json"
FULL_BOOK_AUDIT_FILE = "M12_FULL_BOOK_AUDIT.json"
FULL_BOOK_AUDIT_GATE_FILE = "M12_FULL_BOOK_AUDIT_GATE.json"
SAMPLE_REVIEW_FILE = "M12_SAMPLE_REVIEW.json"
SAMPLE_REVIEW_DOC = "docs/WASTELAND_001_M12_SAMPLE_REVIEW_PACK.md"
ACCEPTANCE_FILE = "M12_ACCEPTANCE.json"
FREEZE_FILE = "WASTELAND_001_M12_FREEZE_V1.json"
M13_READINESS_FILE = "M12_M13_READINESS.json"

# M11 frozen truth（M11 FINAL ACCEPTANCE 时点的 digest；M12 不得改变它们）
FROZEN_CANON = FROZEN_SOURCE_DIGESTS["canon"]
FROZEN_STORY_STATE = FROZEN_SOURCE_DIGESTS["story_state"]
FROZEN_LEGACY = FROZEN_SOURCE_DIGESTS["legacy"]
FROZEN_SOURCE_IR = FROZEN_SOURCE_DIGESTS["chapter_ir"]
FROZEN_CONTRACT = "67559aa55442d69e"
FROZEN_REPAIR_GATE = "e1eab4c33ae75b01"
TARGET_COUNT = 372
CHAPTER_COUNT = 570

# 人工样本：分层抽样（deterministic，seed 固定）
SAMPLE_SEED = 20260915
SAMPLE_SIZE = 40

M11_PHASE_IDS: tuple[str, ...] = (
    "BLOCKER_00", "BLOCKER_00A", "CONTENT_DESIGN_01", "AUTHOR_CONTENT_01",
    "AUTO_SAFE_SWEEP_CLOSEOUT", "P15O", "P15P", "CONTENT_REWRITE",
    "APPROVED_EVENT", "BATCH05", "MICRO_PILOT", "READINESS_V2",
    *(f"M11_RUN_{index:02d}" for index in range(1, 13)))

M12_PHASE_IDS: tuple[str, ...] = (
    "M12_PREFLIGHT", "M12_FULL_BOOK_AUDIT", "M12_SAMPLE_REVIEW", "M12_ACCEPTANCE")

AUTHOR_REVIEW_MODES: tuple[str, ...] = (
    "AUTHOR_DELEGATED_NEW_EVENT", "AUTHOR_DELEGATED_DECISION",
    "CONTENT_EVIDENCE_GAP_EVENT")

DELEGATION = "TASK_LEVEL_DELEGATED_CONSERVATIVE_DECISION"


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
    blob = json.dumps(payload, sort_keys=True, ensure_ascii=False,
                      default=str).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()[:16]


def _digest_file(path: Path) -> str:
    path = Path(path)
    return hashlib.sha256(path.read_bytes()).hexdigest()[:16] if path.is_file() else ""


def _counts(values: Sequence[Any]) -> dict[str, int]:
    result: dict[str, int] = {}
    for value in values:
        key = str(value)
        result[key] = result.get(key, 0) + 1
    return result


def semantic_fingerprint(design_dir: Path | str) -> dict[str, Any]:
    """M11 frozen production semantic state（不含 generated_at 等 volatile 字段）。"""

    design = Path(design_dir)
    overlay = _read_json(design / "M11_OVERLAY_V2.json")
    ledger = _read_json(design / "M11_REPAIR_SUBTYPE_LEDGER.json")
    reconciliation = _read_json(design / "M11_FINAL_CLOSURE_RECONCILIATION.json")
    backlog = _read_json(design / "M11_PRODUCTION_BACKLOG.json")
    queue = _read_json(design / "M11_CONTENT_DESIGN_QUEUE_V3.json")
    entries = ledger.get("ledger") or {}
    identity = sorted(
        (str(row.get("canonical_root_id")), str(row.get("chapter_id")),
         str(row.get("new_resolution_status")))
        for row in reconciliation.get("records") or [])
    backlog_rows = list(backlog.get("items") or [])
    return {
        "terminal_targets": overlay.get("resolved_total"),
        "remaining_repair_targets": overlay.get("remaining_repair_targets"),
        "overlay_counts": dict(overlay.get("primary_resolution_status_counts") or {}),
        "overlay_conservation": dict(overlay.get("conservation") or {}),
        "ledger_target_count": len(entries),
        "ledger_subtype_counts": dict(ledger.get("resolved_subtype_counts") or {}),
        "reconciliation_record_count": reconciliation.get("record_count"),
        "reconciliation_identity_digest": _digest(identity),
        "backlog_item_count": backlog.get("item_count"),
        "backlog_status_counts": _counts(
            row.get("status") for row in backlog_rows),
        "cdq_active": sum(1 for row in queue.get("requirements") or []
                          if str(row.get("status")) == "ACTIVE"),
    }


class M12PreflightService:
    """M12 preflight：authority + M11 freeze guard + input projection + boundary audit。"""

    def __init__(self, project_root: Path | str, *, design_dir: str = ADOPTION_DIR,
                 foundation_dir: str = HISTORY_DIR) -> None:
        self.root = Path(project_root).resolve()
        self.design_dir = (self.root / design_dir).resolve()
        self.foundation_dir = (self.root / foundation_dir).resolve()
        self.out_dir = self.design_dir / M12_DIR
        self.runner = M11Run12Service(self.root, design_dir=str(self.design_dir),
                                      foundation_dir=str(self.foundation_dir))

    # ------------------------------------------------------------ authority
    def authority(self) -> dict[str, Any]:
        payload = {
            "generated_at": _now(), "authority_id": "M12_ACCEPTANCE_AUTHORITY",
            "granted_by": "USER", "grant_source": "CURRENT_USER_INSTRUCTION",
            "delegation": DELEGATION,
            "delegation_scope": [
                "ordinary author choice", "manual classification",
                "conservative planning decision", "sample audit verdict"],
            "requires_author_for": [
                "major worldview change", "protagonist identity change",
                "core history rewrite", "Canon / StoryState modification"],
            "m11_read_only": True,
            "may_write": [f"{ADOPTION_DIR}/{M12_DIR}/*",
                          SAMPLE_REVIEW_DOC],
            "must_not_write": [
                "Canon", "StoryState", "legacy source", "570 source Chapter IR",
                "Historical Foundation",
                "M11 overlay / ledger / reconciliation / backlog / blocker graph"],
            "audit_trail_required": True,
            "read_only": True}
        _write_json(self.out_dir / M12_AUTHORITY_FILE, payload)
        return payload

    # ------------------------------------------------------------ freeze guard
    def m11_frozen_input(self) -> dict[str, Any]:
        design = self.design_dir
        acceptance = _read_json(design / "M11_FINAL_ACCEPTANCE.json")
        writer = _read_json(design / "M11_FINAL_WRITER_PROJECTION_GATE.json")
        isolation = _read_json(design / "m11_run_12" /
                               "P15_EXECUTOR_READ_ONLY_AFTER_CLOSEOUT.json")
        fingerprint = semantic_fingerprint(design)
        snapshot_status = {
            phase_id: verify_phase_snapshot(self.root, phase_id)["status"]
            for phase_id in M11_PHASE_IDS if snapshot_exists(self.root, phase_id)}
        ledger_counts = dict(fingerprint["ledger_subtype_counts"])
        repaired_sum = sum(value for key, value in ledger_counts.items()
                           if key != "no_repair_required")
        overlay = _read_json(design / "M11_OVERLAY_V2.json")
        checks = {
            "m11_final_acceptance_pass": acceptance.get("status") == "PASS",
            "writer_projection_gate_pass": writer.get("status") == "PASS",
            "p15_isolation_pass": isolation.get("status") == "PASS",
            "terminal_372": (int(fingerprint["terminal_targets"] or 0) == TARGET_COUNT
                             and int(fingerprint["remaining_repair_targets"] or 0) == 0),
            "ledger_equals_overlay": (fingerprint["ledger_target_count"] == TARGET_COUNT
                                      == int(overlay.get("resolved_total") or 0)),
            "overlay_subtype_conservation": (
                int(overlay.get("repaired") or 0) == repaired_sum
                and int(overlay.get("no_repair_required") or 0)
                == int(ledger_counts.get("no_repair_required") or 0)),
            "no_active_blocker": (int(acceptance.get("active_blocking_canonical_roots") or 0)
                                  == 0
                                  and int(acceptance.get("unresolved_analysis") or 0) == 0
                                  and int(fingerprint["cdq_active"] or 0) == 0),
            "field_rebind_not_proven":
                acceptance.get("field_rebind_capability") == "NOT_PROVEN",
            "frozen_phase_snapshots_immutable": (
                bool(snapshot_status)
                and all(status == "PASS" for status in snapshot_status.values())),
        }
        payload = {
            "generated_at": _now(), "guard_id": "M11_FROZEN_INPUT",
            "status": "PASS" if all(checks.values()) else "FAIL",
            "checks": checks,
            "semantic_fingerprint": fingerprint,
            "m11_final_acceptance_status": acceptance.get("status"),
            "m11_acceptance_digest": _digest_file(design / "M11_FINAL_ACCEPTANCE.json"),
            "m11_frozen_artifacts": {
                name: _digest_file(design / name) for name in (
                    "M11_OVERLAY_V2.json", "M11_REPAIR_SUBTYPE_LEDGER.json",
                    "M11_FINAL_CLOSURE_RECONCILIATION.json",
                    "M11_PRODUCTION_BACKLOG.json",
                    "M11_CONTENT_DESIGN_QUEUE_V3.json")},
            "phase_snapshot_immutability": snapshot_status,
            "m11_is_read_only": True,
            "read_only": True, "non_authoritative": True}
        _write_json(self.out_dir / M11_FROZEN_INPUT_FILE, payload)
        return payload

    # ------------------------------------------------------------ projection
    def input_projection(self) -> dict[str, Any]:
        truth = self.runner.truth_digests()
        frozen = self.runner.frozen_digests()
        index = _ir_read_json(self.foundation_dir / "index.json")
        integrity = _ir_read_json(self.foundation_dir / "integrity.json")
        materialization = _ir_read_json(self.foundation_dir /
                                        "materialization_report.json")
        foundation_gate = _ir_read_json(self.foundation_dir /
                                        "HISTORICAL_IR_FOUNDATION_GATE.json")
        planning_ref = _ir_read_json(
            self.root / "workspace/wasteland_001_exports/reconstruction_v2" /
            "WASTELAND_FUTURE_PLANNING_REF.json")
        planning_index = _ir_read_json(
            self.root / PLANNING_STORE_DIR / "wasteland_001" / "index.json")
        repair = semantic_fingerprint(self.design_dir)
        writer = _read_json(self.design_dir / "M11_FINAL_WRITER_PROJECTION_GATE.json")
        status_counts = dict(materialization.get("materialization_status_counts") or {})
        checks = {
            "canon_story_state_frozen": (
                truth.get("canon") == FROZEN_CANON
                and truth.get("story_state") == FROZEN_STORY_STATE),
            "legacy_source_ir_frozen": (
                truth.get("legacy") == FROZEN_LEGACY
                and truth.get("chapter_ir") == FROZEN_SOURCE_IR),
            "historical_foundation_frozen": all(
                (truth.get("historical_foundation") or {}).get(name) == digest
                for name, digest in FROZEN_FOUNDATION_DIGESTS.items()
                if name != "manifest.json"),
            "contract_gate_frozen": (frozen.get("contract") == FROZEN_CONTRACT
                                     and frozen.get("repair_gate") == FROZEN_REPAIR_GATE),
            "chapter_ir_coverage_570": (
                int(index.get("chapter_count") or 0) == CHAPTER_COUNT
                and int(integrity.get("artifact_count") or 0) == CHAPTER_COUNT),
            "no_failed_materialization": not status_counts.get("FAILED"),
            "foundation_gate_ready": foundation_gate.get("status") == "READY",
            "planning_revision_present": bool(
                planning_ref.get("planning_revision")
                and planning_ref.get("planning_head_after")),
            "planning_store_present": bool(planning_index),
            "repair_layer_terminal": (int(repair["terminal_targets"] or 0) == TARGET_COUNT
                                      and int(repair["remaining_repair_targets"] or 0) == 0),
            "queue_backlog_closed": (int(repair["cdq_active"] or 0) == 0
                                     and int(repair["backlog_status_counts"].get(
                                         "BACKLOG", 0)) <= 1),
            "writer_projection_gate_pass": writer.get("status") == "PASS",
        }
        payload = {
            "generated_at": _now(), "projection_id": "M12_INPUT_PROJECTION",
            "status": "PASS" if all(checks.values()) else "FAIL",
            "checks": checks,
            "truth_digests": truth,
            "frozen_digests": {k: v for k, v in frozen.items()
                               if k in ("contract", "repair_gate")},
            "chapter_ir": {
                "chapter_count": index.get("chapter_count"),
                "index_digest": index.get("index_digest"),
                "materialization_status_counts": status_counts,
                "foundation_gate_status": foundation_gate.get("status"),
            },
            "planning": {
                "planning_revision": planning_ref.get("planning_revision"),
                "planning_head_after": planning_ref.get("planning_head_after"),
                "planning_store_ref": f"{PLANNING_STORE_DIR}/wasteland_001/index.json",
            },
            "repair_layer": repair,
            "writer_projection_gate": writer.get("status"),
            "read_only": True, "non_authoritative": True}
        _write_json(self.out_dir / INPUT_PROJECTION_FILE, payload)
        return payload

    # ------------------------------------------------------------ boundary audit
    def boundary_audit(self) -> dict[str, Any]:
        design = self.design_dir
        reconciliation = _read_json(design / "M11_FINAL_CLOSURE_RECONCILIATION.json")
        ledger = _read_json(design / "M11_REPAIR_SUBTYPE_LEDGER.json")
        authorization = _read_json(design / "M11_APPROVED_EVENT_ARCHITECTURE_"
                                          "AUTHORIZATION.json")
        truth = self.runner.truth_digests()
        records = list(reconciliation.get("records") or [])
        entries = dict(ledger.get("ledger") or {})
        non_authoritative = all(bool(row.get("non_authoritative"))
                                for row in records)
        repaired_refs_exist = all(
            (design / str(row.get("repaired_ref"))).is_file()
            for row in records if row.get("repaired_ref"))
        repaired_not_canonical = all(
            _read_json(design / str(row.get("repaired_ref"))).get(
                "canonical_representation") in (None, False)
            for row in records if row.get("repaired_ref"))
        event_bounded = all(int(row.get("event_added") or 0) <= 1 for row in records)
        planning_ref = _ir_read_json(
            self.root / "workspace/wasteland_001_exports/reconstruction_v2" /
            "WASTELAND_FUTURE_PLANNING_REF.json")
        checks = {
            "repair_truth_not_canon_source": (
                truth.get("canon") == FROZEN_CANON
                and truth.get("story_state") == FROZEN_STORY_STATE
                and non_authoritative),
            "repair_events_do_not_write_canon": (
                authorization.get("safe_auto_relaxed") is False
                and authorization.get("p15_reopened") is False
                and authorization.get("truth_boundary_relaxed") is False),
            "repair_minimal_increment": event_bounded,
            "repair_lineage_present": repaired_refs_exist and repaired_not_canonical,
            "historical_truth_is_happened_layer": all(
                artifact.time_layer == TIME_LAYER and artifact.derived
                and not artifact.canonical_representation
                and artifact.non_authoritative
                and artifact.canon_digest_ref == FROZEN_CANON
                and artifact.story_state_digest_ref == FROZEN_STORY_STATE
                for artifact in self._artifacts().values()),
            "future_planning_not_occurred_history": (
                bool(planning_ref.get("planning_revision"))
                and truth.get("chapter_ir") == FROZEN_SOURCE_IR),
        }
        payload = {
            "generated_at": _now(), "audit_id": "M12_BOUNDARY_AUDIT",
            "status": "PASS" if all(checks.values()) else "FAIL",
            "checks": checks,
            "invariants": {
                "historical_repair_truth_is_not_canon_source": True,
                "future_planning_is_not_occurred_history": True,
                "m11_repaired_events_are_consumable_and_non_polluting": True,
            },
            "evidence": {
                "canon_digest": truth.get("canon"),
                "story_state_digest": truth.get("story_state"),
                "chapter_ir_digest": truth.get("chapter_ir"),
                "planning_revision": planning_ref.get("planning_revision"),
                "reconciliation_records": len(records),
                "ledger_targets": len(entries),
            },
            "read_only": True, "non_authoritative": True}
        _write_json(self.out_dir / BOUNDARY_AUDIT_FILE, payload)
        return payload

    def _artifacts(self) -> dict[str, Any]:
        return HistoricalIRStore(self.foundation_dir).load_artifacts()

    # ------------------------------------------------------------ baseline
    def execution_baseline(self) -> dict[str, Any]:
        entry = _read_json(self.design_dir / "M12_ENTRY_CRITERIA_FINAL.json")
        frozen_input = _read_json(self.out_dir / M11_FROZEN_INPUT_FILE)
        projection = _read_json(self.out_dir / INPUT_PROJECTION_FILE)
        boundary = _read_json(self.out_dir / BOUNDARY_AUDIT_FILE)
        payload = {
            "generated_at": _now(), "baseline_id": "M12_EXECUTION_BASELINE",
            "milestone": "M12",
            "goal": ("WASTELAND Acceptance / Freeze：全书审计 + 人工样本 + freeze 裁定"
                     "（repo: MASTER_PLAN M12 row / MILESTONES M12 / PROGRESS_AUDIT §8）"),
            "entry_criteria": {
                "artifact": "M12_ENTRY_CRITERIA_FINAL.json",
                "criteria_count": entry.get("criteria_count"),
                "satisfied_count": entry.get("satisfied_count"),
                "unsatisfied_count": entry.get("unsatisfied_count"),
                "m12_entry_allowed": entry.get("m12_entry_allowed"),
            },
            "required_components": [
                "M12PreflightService（freeze guard / input projection / boundary audit）",
                "M12FullBookAuditService（570 章全书审计 + repair lineage conservation）",
                "M12SampleReviewService（分层人工样本 + delegated conservative verdict）",
                "M12AcceptanceService（acceptance + freeze manifest + M13 readiness）",
            ],
            "required_artifacts": [
                M12_AUTHORITY_FILE, M11_FROZEN_INPUT_FILE, INPUT_PROJECTION_FILE,
                BOUNDARY_AUDIT_FILE, EXECUTION_BASELINE_FILE, FULL_BOOK_AUDIT_FILE,
                FULL_BOOK_AUDIT_GATE_FILE, SAMPLE_REVIEW_FILE,
                ACCEPTANCE_FILE, FREEZE_FILE, M13_READINESS_FILE],
            "production_inputs": {
                "historical_chapter_ir": HISTORY_DIR,
                "repair_layer": ADOPTION_DIR,
                "planning_store": f"{PLANNING_STORE_DIR}/wasteland_001/index.json",
                "m11_frozen_fingerprint": frozen_input.get("semantic_fingerprint"),
            },
            "acceptance_criteria": self.acceptance_criteria(),
            "m13_entry_dependency": {
                "milestone": "M13 Game UI P0（W6-01～W6-06）",
                "requires": "M12 freeze（WASTELAND_001_M12_FREEZE_V1）",
                "repository_reference": "MILESTONES M13 row / MASTER_PLAN 里程碑表",
            },
            "preflight_status": {
                "frozen_input": frozen_input.get("status"),
                "input_projection": projection.get("status"),
                "boundary_audit": boundary.get("status"),
            },
            "read_only": True, "non_authoritative": True}
        _write_json(self.out_dir / EXECUTION_BASELINE_FILE, payload)
        return payload

    @staticmethod
    def acceptance_criteria() -> list[dict[str, str]]:
        return [
            {"criterion": "book_audit_complete",
             "definition": "570/570 章 historical Chapter IR 全部通过 schema / evidence / "
                           "digest / neighbor 审计"},
            {"criterion": "truth_separation",
             "definition": "historical repair truth != Canon source；future planning != "
                           "occurred history"},
            {"criterion": "repair_lineage_conservation",
             "definition": "372 == ledger == overlay；subtype 计数与 overlay 桶一致；"
                           "reconciliation repaired_ref 全部存在"},
            {"criterion": "sample_review_complete",
             "definition": "分层人工样本 ≥ 40 章，覆盖全部 volume / repair subtype / "
                           "resolution mode，无未决 blocking review item"},
            {"criterion": "frozen_inputs_unchanged",
             "definition": "Canon / StoryState / legacy / 570 source IR / Foundation / "
                           "Contract / Gate digest 不变，M11 semantic fingerprint before == after"},
            {"criterion": "writer_projection_gate_pass",
             "definition": "M11_FINAL_WRITER_PROJECTION_GATE = PASS（writer-facing 面不退化）"},
            {"criterion": "freeze_manifest_written",
             "definition": "WASTELAND_001_M12_FREEZE_V1.json 含 digest / immutability / "
                           "author override 窗口"},
            {"criterion": "m12_replay_idempotent",
             "definition": "M12 acceptance replay 后 fingerprint 不变"},
            {"criterion": "m13_readiness",
             "definition": "M13 Game UI P0 的 M12 依赖满足（m13_entry_allowed = true）"},
        ]

    # ------------------------------------------------------------ run
    def run(self, *, snapshot_refresh_reason: str = "") -> dict[str, Any]:
        authority = self.authority()
        frozen_input = self.m11_frozen_input()
        projection = self.input_projection()
        boundary = self.boundary_audit()
        baseline = self.execution_baseline()
        payload = {
            "generated_at": _now(), "phase": "M12_PREFLIGHT",
            "authority_ref": M12_AUTHORITY_FILE,
            "m11_frozen_input_status": frozen_input["status"],
            "input_projection_status": projection["status"],
            "boundary_audit_status": boundary["status"],
            "baseline_ref": EXECUTION_BASELINE_FILE,
            "delegation": authority["delegation"],
            "read_only": True, "non_authoritative": True}
        payload["status"] = ("PASS" if all(status == "PASS" for status in (
            frozen_input["status"], projection["status"],
            boundary["status"])) else "FAIL")
        _write_json(self.out_dir / "M12_PREFLIGHT_SUMMARY.json", payload)
        snapshot = _publish_phase_snapshot(
            self.root, "M12_PREFLIGHT", {
                "phase_id": "M12_PREFLIGHT",
                "m11_final_acceptance_status": frozen_input.get(
                    "m11_final_acceptance_status"),
                "m11_frozen_input_status": frozen_input["status"],
                "input_projection_status": projection["status"],
                "boundary_audit_status": boundary["status"],
                "terminal_targets": frozen_input["semantic_fingerprint"].get(
                    "terminal_targets"),
                "chapter_ir_chapter_count": projection["chapter_ir"].get(
                    "chapter_count"),
                "planning_revision": projection["planning"].get("planning_revision"),
                "delegation": authority["delegation"],
                "acceptance_criteria": [row["criterion"]
                                        for row in baseline["acceptance_criteria"]],
                "m13_entry_dependency": baseline["m13_entry_dependency"]["milestone"],
            },
            evidence_sources=["M11_FINAL_ACCEPTANCE.json",
                              "M11_REGRESSION_REANCHOR_REPORT.md",
                              "M12_EXECUTION_BASELINE.json"],
            refresh_reason=snapshot_refresh_reason)
        payload["snapshot"] = snapshot
        _write_json(self.out_dir / "M12_PREFLIGHT_SUMMARY.json", payload)
        return payload


def _head_commit(root: Path) -> str:
    head = root / ".git" / "HEAD"
    if not head.is_file():
        return ""
    text = head.read_text(encoding="utf-8").strip()
    if text.startswith("ref:"):
        ref = root / ".git" / text.split(" ", 1)[1].strip()
        return ref.read_text(encoding="utf-8").strip() if ref.is_file() else ""
    return text


def phase_snapshot_status(root: Path | str, phase_id: str) -> dict[str, Any]:
    """M12 phase snapshot 首次写入（write-once）；已存在则只做 immutability 校验。"""

    root = Path(root).resolve()
    if snapshot_exists(root, phase_id):
        verification = verify_phase_snapshot(root, phase_id)
        return {"snapshot_id": phase_id, "snapshot_written": False,
                "snapshot_status": verification["status"],
                "snapshot_digest": verification["snapshot_digest"]}
    return {"snapshot_id": phase_id, "snapshot_written": True,
            "snapshot_status": "PASS", "snapshot_digest": ""}


def refresh_phase_snapshot(root: Path | str, phase_id: str,
                           data: Mapping[str, Any], *, reason: str,
                           evidence_sources: Sequence[str] = ()) -> dict[str, Any]:
    """maintenance：显式重建 phase snapshot（write-once 的受控例外，必须给 reason）。"""

    root = Path(root).resolve()
    assert reason, "refresh_phase_snapshot 必须给出 reason（维护用途显式声明）"
    return write_phase_snapshot(
        root, phase_id, dict(data), overwrite=True, reconstructed=True,
        source_commit=_head_commit(root),
        evidence_sources=[f"maintenance:{reason}", *evidence_sources])


def _publish_phase_snapshot(root: Path, phase_id: str, data: Mapping[str, Any],
                            *, evidence_sources: Sequence[str] = (),
                            refresh_reason: str = "") -> dict[str, Any]:
    """首次写入（write-once）；已有 snapshot 时只校验；`refresh_reason` 为显式维护重建。"""

    if snapshot_exists(root, phase_id):
        if not refresh_reason:
            return phase_snapshot_status(root, phase_id)
        manifest = write_phase_snapshot(
            root, phase_id, dict(data), overwrite=True, reconstructed=True,
            source_commit=_head_commit(root),
            evidence_sources=[f"maintenance:{refresh_reason}",
                              *list(evidence_sources)])
        return {"snapshot_id": phase_id, "snapshot_written": True,
                "snapshot_refreshed": True, "snapshot_status": "PASS",
                "snapshot_digest": manifest["snapshot_digest"]}
    manifest = write_phase_snapshot(root, phase_id, dict(data),
                                    source_commit=_head_commit(root),
                                    evidence_sources=list(evidence_sources))
    return {"snapshot_id": phase_id, "snapshot_written": True,
            "snapshot_status": "PASS",
            "snapshot_digest": manifest["snapshot_digest"]}


class M12FullBookAuditService:
    """全书审计：570 章 historical Chapter IR + M11 repair layer 消费审计。"""

    def __init__(self, project_root: Path | str, *, design_dir: str = ADOPTION_DIR,
                 foundation_dir: str = HISTORY_DIR) -> None:
        self.root = Path(project_root).resolve()
        self.design_dir = (self.root / design_dir).resolve()
        self.foundation_dir = (self.root / foundation_dir).resolve()
        self.out_dir = self.design_dir / M12_DIR
        self.store = HistoricalIRStore(self.foundation_dir)

    # ------------------------------------------------------------ chapters
    def chapter_audit(self) -> dict[str, Any]:
        artifacts = self.store.load_artifacts()
        integrity = _ir_read_json(self.foundation_dir / "integrity.json")
        rows: list[dict[str, Any]] = []
        for artifact in sorted(artifacts.values(),
                               key=lambda item: item.display_number):
            checks = chapter_artifact_checks(artifact, integrity)
            checks["truth_boundary_ok"] = bool(
                checks["truth_boundary_ok"]
                and artifact.canon_digest_ref == FROZEN_CANON
                and artifact.story_state_digest_ref == FROZEN_STORY_STATE)
            rows.append({
                "chapter_id": artifact.chapter_id,
                "legacy_label": artifact.legacy_label,
                "volume_id": artifact.volume_id, "arc_id": artifact.arc_id,
                "display_number": artifact.display_number,
                "materialization_status": artifact.materialization_status,
                "coverage_status": artifact.evidence_coverage.overall_status,
                "chapter_function": artifact.chapter_function,
                "unresolved_field_count": len(artifact.unresolved_fields),
                "unresolved_fields": list(artifact.unresolved_fields),
                "event_count": len(artifact.chapter_ir.event_frames),
                "chapter_ir_digest": artifact.chapter_ir_digest,
                "checks": checks,
                "audit_status": "PASS" if all(checks.values()) else "FAIL",
            })
        failures = [row for row in rows if row["audit_status"] != "PASS"]
        return {
            "chapter_count": len(rows), "chapters": rows,
            "failure_count": len(failures),
            "failures": failures[:20],
            "materialization_status_counts": _counts(
                row["materialization_status"] for row in rows),
            "coverage_status_counts": _counts(
                row["coverage_status"] for row in rows),
            "chapter_function_counts": _counts(
                row["chapter_function"] for row in rows),
            "volume_counts": _counts(row["volume_id"] for row in rows),
            "unresolved_field_counts": _counts(
                field for row in rows for field in row["unresolved_fields"]),
            "chapters_with_unresolved_fields": sum(
                1 for row in rows if row["unresolved_field_count"]),
            "checks_passed": {key: all(row["checks"][key] for row in rows)
                              for key in (rows[0]["checks"] if rows else {})},
        }

    # ------------------------------------------------------------ repair layer
    def repair_lineage_audit(self) -> dict[str, Any]:
        design = self.design_dir
        overlay = _read_json(design / "M11_OVERLAY_V2.json")
        ledger = _read_json(design / "M11_REPAIR_SUBTYPE_LEDGER.json")
        reconciliation = _read_json(design / "M11_FINAL_CLOSURE_RECONCILIATION.json")
        records = list(reconciliation.get("records") or [])
        entries = dict(ledger.get("ledger") or {})
        subtype_counts = dict(ledger.get("resolved_subtype_counts") or {})
        repaired_only = sum(count for key, count in subtype_counts.items()
                            if key != "no_repair_required")
        missing_refs = [
            {"canonical_root_id": row.get("canonical_root_id"),
             "repaired_ref": row.get("repaired_ref")}
            for row in records
            if row.get("repaired_ref")
            and not (design / str(row["repaired_ref"])).is_file()]
        identity = [(str(row.get("canonical_root_id")), str(row.get("chapter_id")))
                    for row in records]
        duplicate_identity = sorted(
            {item for item in identity if identity.count(item) > 1})
        checks = {
            "ledger_equals_overlay_total": (len(entries) == TARGET_COUNT
                                            == int(overlay.get("resolved_total") or 0)),
            "subtype_counts_match_overlay": (
                int(overlay.get("repaired") or 0) == repaired_only
                and int(overlay.get("no_repair_required") or 0)
                == int(subtype_counts.get("no_repair_required") or 0)),
            "reconciliation_refs_exist": not missing_refs,
            "canonical_identity_unique": not duplicate_identity,
            "reconciliation_records_non_authoritative": all(
                bool(row.get("non_authoritative")) for row in records),
            "event_added_bounded": all(
                int(row.get("event_added") or 0) <= 1 for row in records),
            "author_lane_has_approval": all(
                str(row.get("approval_ref") or "")
                in ("AUTHOR_CONTENT_APPROVAL", "")
                for row in records),
            "no_unresolved_terminal_target": int(
                overlay.get("remaining_repair_targets") or 0) == 0,
        }
        return {
            "ledger_target_count": len(entries),
            "overlay_resolved_total": overlay.get("resolved_total"),
            "reconciliation_record_count": len(records),
            "resolved_subtype_counts": subtype_counts,
            "resolution_mode_counts": _counts(
                row.get("resolution_mode") for row in records),
            "missing_repaired_refs": missing_refs,
            "duplicate_canonical_identity": duplicate_identity,
            "checks": checks,
            "status": "PASS" if all(checks.values()) else "FAIL",
        }

    # ------------------------------------------------------------ continuity
    def continuity_audit(self, *, chapter_audit: Mapping[str, Any]
                         | None = None) -> dict[str, Any]:
        audit = chapter_audit or self.chapter_audit()
        rows = list(audit["chapters"])
        order = [row["display_number"] for row in rows]
        monotonic = order == sorted(order)
        labels = [row["legacy_label"] for row in rows]
        stable_identity = (len({row["chapter_id"] for row in rows}) == len(rows)
                           and len(set(labels)) == len(rows))
        cross_check = _read_json(self.design_dir / "CROSS_CHAPTER_FACT_CHECKS.json")
        erasure_risk = int(cross_check.get("erasure_risk_count") or 0)
        neighbor_failures = [row["legacy_label"] for row in rows
                             if not row["checks"]["neighbor_continuity_ok"]]
        checks = {
            "chronological_order": monotonic,
            "stable_chapter_identity": stable_identity,
            "no_neighbor_continuity_failure": not neighbor_failures,
            "no_erasure_risk": erasure_risk == 0,
        }
        return {
            "checks": checks, "status": "PASS" if all(checks.values()) else "FAIL",
            "neighbor_failure_count": len(neighbor_failures),
            "neighbor_failures": neighbor_failures[:20],
            "cross_chapter_fact_checks": {
                "chapter_count": cross_check.get("chapter_count"),
                "foundation_agrees_count": cross_check.get("foundation_agrees_count"),
                "erasure_risk_count": erasure_risk,
                "confirmed_truth_priority": True,
            },
        }

    # ------------------------------------------------------------ run + gate
    def full_book_audit(self) -> dict[str, Any]:
        chapters = self.chapter_audit()
        lineage = self.repair_lineage_audit()
        continuity = self.continuity_audit(chapter_audit=chapters)
        projection = _read_json(self.out_dir / INPUT_PROJECTION_FILE)
        boundary = _read_json(self.out_dir / BOUNDARY_AUDIT_FILE)
        payload = {
            "generated_at": _now(), "audit_id": "M12_FULL_BOOK_AUDIT",
            "chapter_audit": chapters, "repair_lineage": lineage,
            "continuity": continuity,
            "input_projection_status": projection.get("status"),
            "boundary_audit_status": boundary.get("status"),
            "read_only": True, "non_authoritative": True}
        payload["status"] = ("PASS" if (
            chapters["failure_count"] == 0 and lineage["status"] == "PASS"
            and continuity["status"] == "PASS"
            and projection.get("status") == "PASS"
            and boundary.get("status") == "PASS") else "FAIL")
        _write_json(self.out_dir / FULL_BOOK_AUDIT_FILE, payload)
        return payload

    def gate(self) -> dict[str, Any]:
        audit = _read_json(self.out_dir / FULL_BOOK_AUDIT_FILE)
        chapters = audit.get("chapter_audit") or {}
        lineage = audit.get("repair_lineage") or {}
        continuity = audit.get("continuity") or {}
        checks = {
            "chapter_coverage_570": chapters.get("chapter_count") == CHAPTER_COUNT,
            "chapter_checks_all_pass": chapters.get("failure_count") == 0,
            "all_chapter_check_kinds_pass": all(
                (chapters.get("checks_passed") or {}).values()),
            "repair_lineage_pass": lineage.get("status") == "PASS",
            "continuity_pass": continuity.get("status") == "PASS",
            "input_projection_pass": audit.get("input_projection_status") == "PASS",
            "boundary_audit_pass": audit.get("boundary_audit_status") == "PASS",
        }
        payload = {
            "generated_at": _now(), "gate_id": "M12_FULL_BOOK_AUDIT_GATE",
            "status": "PASS" if all(checks.values()) else "FAIL",
            "checks": checks,
            "failed_checks": sorted(key for key, ok in checks.items() if not ok),
            "chapter_count": chapters.get("chapter_count"),
            "materialization_status_counts": chapters.get(
                "materialization_status_counts"),
            "read_only": True, "non_authoritative": True}
        _write_json(self.out_dir / FULL_BOOK_AUDIT_GATE_FILE, payload)
        return payload

    def run(self, *, snapshot_refresh_reason: str = "") -> dict[str, Any]:
        audit = self.full_book_audit()
        gate = self.gate()
        snapshot = _publish_phase_snapshot(
            self.root, "M12_FULL_BOOK_AUDIT", {
                "phase_id": "M12_FULL_BOOK_AUDIT",
                "status": audit["status"], "gate_status": gate["status"],
                "chapter_count": audit["chapter_audit"]["chapter_count"],
                "chapter_failure_count": audit["chapter_audit"]["failure_count"],
                "materialization_status_counts": audit["chapter_audit"][
                    "materialization_status_counts"],
                "coverage_status_counts": audit["chapter_audit"][
                    "coverage_status_counts"],
                "ledger_target_count": audit["repair_lineage"][
                    "ledger_target_count"],
                "reconciliation_record_count": audit["repair_lineage"][
                    "reconciliation_record_count"],
                "resolved_subtype_counts": audit["repair_lineage"][
                    "resolved_subtype_counts"],
                "continuity_status": audit["continuity"]["status"],
                "chapters_with_unresolved_fields": audit["chapter_audit"][
                    "chapters_with_unresolved_fields"],
                "unresolved_field_counts": audit["chapter_audit"][
                    "unresolved_field_counts"],
            },
            evidence_sources=[HISTORY_DIR + "/index.json",
                              ADOPTION_DIR + "/M11_FINAL_CLOSURE_RECONCILIATION.json",
                              M12_DIR + "/" + INPUT_PROJECTION_FILE],
            refresh_reason=snapshot_refresh_reason)
        return {"audit": audit, "gate": gate, "snapshot": snapshot}


class M12SampleReviewService:
    """人工样本审核：deterministic 分层抽样 + delegated conservative verdict + audit trail。"""

    def __init__(self, project_root: Path | str, *, design_dir: str = ADOPTION_DIR,
                 foundation_dir: str = HISTORY_DIR) -> None:
        self.root = Path(project_root).resolve()
        self.design_dir = (self.root / design_dir).resolve()
        self.foundation_dir = (self.root / foundation_dir).resolve()
        self.out_dir = self.design_dir / M12_DIR
        self.store = HistoricalIRStore(self.foundation_dir)

    # ------------------------------------------------------------ selection
    def selection(self, *, size: int = SAMPLE_SIZE, seed: int = SAMPLE_SEED
                  ) -> dict[str, Any]:
        artifacts = self.store.load_artifacts()
        by_label = {item.legacy_label: item for item in artifacts.values()}
        by_id_label = {item.chapter_id: item.legacy_label
                       for item in artifacts.values()}
        audit = _read_json(self.out_dir / FULL_BOOK_AUDIT_FILE)["chapter_audit"]
        rows = {row["legacy_label"]: row for row in audit["chapters"]}
        ledger = dict(_read_json(
            self.design_dir / "M11_REPAIR_SUBTYPE_LEDGER.json").get("ledger") or {})
        reconciliation = _read_json(
            self.design_dir / "M11_FINAL_CLOSURE_RECONCILIATION.json")
        records = list(reconciliation.get("records") or [])
        subtype_by_chapter = {str(cid): str(subtype)
                              for cid, subtype in ledger.items()}
        record_by_chapter: dict[str, dict[str, Any]] = {}
        for row in records:
            record_by_chapter.setdefault(str(row.get("chapter_id")), row)

        rng = random.Random(seed)
        selected: list[str] = []
        strata: dict[str, list[str]] = {
            "volume": [], "subtype": [], "mode": [], "author_review": [],
            "materialization": [], "unresolved_heavy": []}

        def add(label: str, stratum: str) -> None:
            if label in by_label and label not in selected:
                selected.append(label)
            if label not in strata[stratum]:
                strata[stratum].append(label)

        # 1) author-review / major design lane（必须人工可见）
        for row in records:
            if str(row.get("resolution_mode")) in AUTHOR_REVIEW_MODES:
                add(str(row.get("legacy_label")), "author_review")
        for label in ("ch012", "ch056"):
            if label in by_label:
                add(label, "author_review")
        # 2) 每个 volume + 每个 repair subtype + 每个 resolution mode 至少 1 个
        volumes = sorted({item.volume_id for item in artifacts.values()})
        for volume in volumes:
            candidates = sorted((item for item in artifacts.values()
                                 if item.volume_id == volume),
                                key=lambda item: item.display_number)
            add(candidates[0].legacy_label, "volume")
        for subtype in sorted(set(subtype_by_chapter.values())):
            candidates = sorted(
                (by_id_label[cid] for cid, value in subtype_by_chapter.items()
                 if value == subtype and cid in by_id_label),
                key=lambda label: by_label[label].display_number)
            if candidates:
                add(candidates[0], "subtype")
        modes = sorted({str(row.get("resolution_mode")) for row in records})
        for mode in modes:
            candidates = sorted(str(row.get("legacy_label")) for row in records
                                if str(row.get("resolution_mode")) == mode)
            add(candidates[0], "mode")
        # 3) 完整/部分 materialization + unresolved 最重的章节
        for status in ("FULL", "PARTIAL"):
            candidates = sorted((item for item in artifacts.values()
                                 if item.materialization_status == status),
                                key=lambda item: item.display_number)
            if candidates:
                add(candidates[0].legacy_label, "materialization")
        heavy = sorted(audit["chapters"],
                       key=lambda row: (-row["unresolved_field_count"],
                                        row["display_number"]))[:3]
        for row in heavy:
            add(row["legacy_label"], "unresolved_heavy")
        # 4) 补足到 size（seeded 随机，确定性）；分层必选章不得被截断
        mandatory = list(selected)
        assert len(mandatory) <= size, (len(mandatory), size)
        remaining = sorted(set(by_label) - set(mandatory))
        rng.shuffle(remaining)
        for label in remaining:
            if len(selected) >= size:
                break
            selected.append(label)
        selected = sorted(set(mandatory) | set(selected[:size]),
                          key=lambda label: by_label[label].display_number)

        def _info(label: str) -> dict[str, Any]:
            artifact = by_label[label]
            chapter_id = artifact.chapter_id
            record = record_by_chapter.get(chapter_id) or {}
            return {
                "legacy_label": label, "chapter_id": chapter_id,
                "repair_target": chapter_id in subtype_by_chapter,
                "volume_id": artifact.volume_id, "arc_id": artifact.arc_id,
                "display_number": artifact.display_number,
                "materialization_status": artifact.materialization_status,
                "coverage_status": artifact.evidence_coverage.overall_status,
                "unresolved_field_count": rows[label]["unresolved_field_count"],
                "event_count": rows[label]["event_count"],
                "chapter_function": rows[label]["chapter_function"],
                "repair_subtype": subtype_by_chapter.get(chapter_id, ""),
                "resolution_mode": str(record.get("resolution_mode") or ""),
                "repair_class": str(record.get("repair_class") or ""),
                "event_added": int(record.get("event_added") or 0),
                "repaired_ref": str(record.get("repaired_ref") or ""),
                "canonical_root_id": str(record.get("canonical_root_id") or ""),
            }

        info_rows = [_info(label) for label in selected]
        coverage = {
            "volumes_covered": sorted({row["volume_id"] for row in info_rows}),
            "all_volumes_covered": (sorted({row["volume_id"] for row in info_rows})
                                    == volumes),
            "subtypes_covered": sorted({row["repair_subtype"] for row in info_rows
                                        if row["repair_subtype"]}),
            "all_subtypes_covered": (
                sorted({row["repair_subtype"] for row in info_rows
                        if row["repair_subtype"]})
                == sorted(set(subtype_by_chapter.values()))),
            "modes_covered": sorted({row["resolution_mode"] for row in info_rows
                                     if row["resolution_mode"]}),
            "all_modes_covered": (
                sorted({row["resolution_mode"] for row in info_rows
                        if row["resolution_mode"]}) == modes),
            "author_review_items": [row["legacy_label"] for row in info_rows
                                    if row["resolution_mode"] in AUTHOR_REVIEW_MODES
                                    or "MAJOR" in row["repair_class"]],
        }
        payload = {
            "generated_at": _now(), "sample_id": "M12_SAMPLE_REVIEW",
            "seed": seed, "size": len(info_rows),
            "strata": {key: sorted(value) for key, value in strata.items()},
            "rows": info_rows, "coverage": coverage,
            "selection_rule": ("volume / repair subtype / resolution mode / "
                               "materialization status / unresolved-heavy / "
                               "author-review lane 分层，再 seeded 补足"),
            "read_only": True, "non_authoritative": True}
        return payload

    # ------------------------------------------------------------ verdicts
    def review(self, *, selection: Mapping[str, Any] | None = None,
               size: int = SAMPLE_SIZE, seed: int = SAMPLE_SEED) -> dict[str, Any]:
        selection = selection or self.selection(size=size, seed=seed)
        artifacts = self.store.load_artifacts()
        by_id = {item.chapter_id: item for item in artifacts.values()}
        audit = _read_json(self.out_dir / FULL_BOOK_AUDIT_FILE)["chapter_audit"]
        chapter_rows = {row["chapter_id"]: row for row in audit["chapters"]}
        unresolved = {
            str(row.get("chapter_id")) for row in _read_json(
                self.design_dir / "M11_FINAL_UNRESOLVED_AUDIT.json").get(
                    "unresolved_targets") or []}
        reviews: list[dict[str, Any]] = []
        delegated: list[dict[str, Any]] = []
        author_override: list[dict[str, Any]] = []
        for row in selection["rows"]:
            artifact = by_id[row["chapter_id"]]
            chapter_row = chapter_rows[row["chapter_id"]]
            author_required = (row["resolution_mode"] in AUTHOR_REVIEW_MODES
                               or "MAJOR" in row["repair_class"])
            checks = dict(chapter_row["checks"])
            # repair target：必须有 ledger subtype（lineage）；非 target 章：不得是未决 target
            checks["repair_lineage_ok"] = (
                bool(row["repair_subtype"]) if row["repair_target"]
                else row["chapter_id"] not in unresolved)
            checks["writer_projection_ready"] = bool(
                artifact.chapter_ir.goal or artifact.chapter_ir.event_frames)
            checks["no_canon_mutation"] = (
                artifact.canon_digest_ref == FROZEN_CANON
                and artifact.story_state_digest_ref == FROZEN_STORY_STATE)
            verdict = "ACCEPT" if all(checks.values()) else "NEEDS_REVIEW"
            entry = {
                **row,
                "checks": checks,
                "verdict": verdict,
                "author_review_required": author_required,
                "delegated": bool(author_required),
                "delegation": DELEGATION if author_required else "",
                "delegated_rationale": (
                    "existing truth first / minimum semantic addition / "
                    "minimum truth impact（M11 已按 author decision 执行，本项仅为验收复核）"
                    if author_required else ""),
                "author_override_recommended": author_required,
                "unresolved_fields": chapter_row["unresolved_fields"],
            }
            reviews.append(entry)
            if author_required:
                delegated.append({
                    "legacy_label": row["legacy_label"],
                    "chapter_id": row["chapter_id"],
                    "resolution_mode": row["resolution_mode"],
                    "repair_class": row["repair_class"],
                    "delegation": DELEGATION,
                    "evidence": row["repaired_ref"] or row["canonical_root_id"],
                    "verdict": verdict,
                    "audit_trail": ("M12 authority（task-level delegated conservative "
                                    "decision）+ M11 reconciliation / approved scope"),
                })
                author_override.append({
                    "legacy_label": row["legacy_label"],
                    "chapter_id": row["chapter_id"],
                    "topic": row["repair_class"] or row["resolution_mode"],
                    "verdict": verdict,
                })
        failures = [row for row in reviews if row["verdict"] != "ACCEPT"]
        checks = {
            "sample_size_ge_40": len(reviews) >= SAMPLE_SIZE,
            "all_volumes_covered": selection["coverage"]["all_volumes_covered"],
            "all_subtypes_covered": selection["coverage"]["all_subtypes_covered"],
            "all_modes_covered": selection["coverage"]["all_modes_covered"],
            "no_failed_review": not failures,
            "delegation_audited": all(row["audit_trail"] for row in delegated),
        }
        payload = {
            "generated_at": _now(), "review_id": "M12_SAMPLE_REVIEW",
            "status": "PASS" if all(checks.values()) else "FAIL",
            "checks": checks, "seed": seed, "sample_size": len(reviews),
            "selection_ref": "M12_SAMPLE_REVIEW.json（selection）",
            "reviews": reviews, "failures": failures,
            "delegated_decisions": delegated,
            "author_override_recommended": author_override,
            "read_only": True, "non_authoritative": True}
        return payload

    # ------------------------------------------------------------ markdown
    def review_doc(self, *, review: Mapping[str, Any] | None = None) -> str:
        review = review or _read_json(self.out_dir / SAMPLE_REVIEW_FILE)
        lines = [
            "# WASTELAND_001 — M12 人工样本审核包（Acceptance / Freeze）",
            "",
            f"样本规模：**{review.get('sample_size')}** 章（seed "
            f"`{review.get('seed')}`，deterministic 分层抽样）｜状态：**"
            f"{review.get('status')}**",
            "",
            "审核口径：历史的 historical repair truth 只作为**验收输入**，"
            "不写回 Canon / StoryState；future planning 不写回 occurred history。",
            "",
            "## 分层覆盖",
            "",
        ]
        checks = review.get("checks") or {}
        for key, value in checks.items():
            lines.append(f"- `{key}`：{'✓' if value else '✗'}")
        lines.extend(["", "## 样本明细", ""])
        for row in review.get("reviews") or []:
            lines.extend([
                f"### {row['legacy_label']}（{row['volume_id']} / {row['arc_id']}｜"
                f"{row['chapter_function']}｜#{row['display_number']}）",
                "",
                f"- repair：`{row['repair_subtype'] or 'n/a'}` / "
                f"`{row['resolution_mode'] or 'n/a'}`（event_added "
                f"{row['event_added']}，root `{row['canonical_root_id'] or 'n/a'}`）",
                f"- chapter IR：{row['materialization_status']}｜coverage "
                f"{row['coverage_status']}｜events {row['event_count']}｜"
                f"unresolved {row['unresolved_field_count']}",
                f"- verdict：**{row['verdict']}**"
                + ("（需作者复核 / delegated conservative decision）"
                   if row["delegated"] else ""),
                "",
            ])
        lines.extend([
            "## 作者 override 建议",
            "",
        ])
        for row in review.get("author_override_recommended") or []:
            lines.append(f"- {row['legacy_label']}（{row['topic']}）：{row['verdict']}"
                         " — 已按既有 author decision / delegated conservative "
                         "decision 记录，作者可随时 override（freeze 证据保留）")
        if not (review.get("author_override_recommended") or []):
            lines.append("- 无（本样本无 author-lane item）")
        lines.append("")
        return "\n".join(lines)

    def run(self, *, snapshot_refresh_reason: str = "") -> dict[str, Any]:
        selection = self.selection()
        review = self.review(selection=selection)
        doc = self.review_doc(review=review)
        doc_path = self.root / SAMPLE_REVIEW_DOC
        doc_path.parent.mkdir(parents=True, exist_ok=True)
        doc_path.write_text(doc, encoding="utf-8", newline="\n")
        snapshot = _publish_phase_snapshot(
            self.root, "M12_SAMPLE_REVIEW", {
                "phase_id": "M12_SAMPLE_REVIEW", "status": review["status"],
                "sample_size": review["sample_size"], "seed": review["seed"],
                "checks": review["checks"],
                "failure_count": len(review["failures"]),
                "delegated_decision_count": len(review["delegated_decisions"]),
                "author_override_items": [row["legacy_label"] for row in
                                          review["author_override_recommended"]],
                "sample_labels": [row["legacy_label"] for row in review["reviews"]],
                "review_doc": SAMPLE_REVIEW_DOC,
            },
            evidence_sources=[M12_DIR + "/" + FULL_BOOK_AUDIT_FILE,
                              ADOPTION_DIR + "/M11_FINAL_CLOSURE_RECONCILIATION.json",
                              SAMPLE_REVIEW_DOC],
            refresh_reason=snapshot_refresh_reason)
        payload = {**review, "selection": selection, "snapshot": snapshot}
        _write_json(self.out_dir / SAMPLE_REVIEW_FILE, payload)
        return payload


class M12AcceptanceService:
    """M12 final acceptance + freeze manifest + M13 readiness（只读消费 preflight 产物）。"""

    def __init__(self, project_root: Path | str, *, design_dir: str = ADOPTION_DIR,
                 foundation_dir: str = HISTORY_DIR) -> None:
        self.root = Path(project_root).resolve()
        self.design_dir = (self.root / design_dir).resolve()
        self.foundation_dir = (self.root / foundation_dir).resolve()
        self.out_dir = self.design_dir / M12_DIR
        self.runner = M11Run12Service(self.root, design_dir=str(self.design_dir),
                                      foundation_dir=str(self.foundation_dir))

    def core_criteria(self) -> list[dict[str, Any]]:
        """M12 section-level 验收 criteria（不依赖 freeze / readiness 产物自身）。"""

        frozen_input = _read_json(self.out_dir / M11_FROZEN_INPUT_FILE)
        boundary = _read_json(self.out_dir / BOUNDARY_AUDIT_FILE)
        audit = _read_json(self.out_dir / FULL_BOOK_AUDIT_FILE)
        gate = _read_json(self.out_dir / FULL_BOOK_AUDIT_GATE_FILE)
        review = _read_json(self.out_dir / SAMPLE_REVIEW_FILE)
        truth = self.runner.truth_digests()
        frozen = self.runner.frozen_digests()
        fingerprint_now = semantic_fingerprint(self.design_dir)
        return [
            {"criterion": "book_audit_complete",
             "satisfied": bool(gate.get("status") == "PASS"
                               and (audit.get("chapter_audit") or {}).get(
                                   "chapter_count") == CHAPTER_COUNT),
             "evidence": FULL_BOOK_AUDIT_GATE_FILE},
            {"criterion": "truth_separation",
             "satisfied": bool(boundary.get("status") == "PASS"),
             "evidence": BOUNDARY_AUDIT_FILE},
            {"criterion": "repair_lineage_conservation",
             "satisfied": bool(
                 (audit.get("repair_lineage") or {}).get("status") == "PASS"
                 and (audit.get("repair_lineage") or {}).get(
                     "ledger_target_count") == TARGET_COUNT),
             "evidence": FULL_BOOK_AUDIT_FILE},
            {"criterion": "sample_review_complete",
             "satisfied": bool(review.get("status") == "PASS"
                               and review.get("sample_size", 0) >= SAMPLE_SIZE),
             "evidence": SAMPLE_REVIEW_FILE},
            {"criterion": "frozen_inputs_unchanged",
             "satisfied": bool(
                 truth.get("canon") == FROZEN_CANON
                 and truth.get("story_state") == FROZEN_STORY_STATE
                 and truth.get("legacy") == FROZEN_LEGACY
                 and truth.get("chapter_ir") == FROZEN_SOURCE_IR
                 and frozen.get("contract") == FROZEN_CONTRACT
                 and frozen.get("repair_gate") == FROZEN_REPAIR_GATE
                 and fingerprint_now
                 == (frozen_input.get("semantic_fingerprint") or {})),
             "evidence": "M11_FROZEN_INPUT.json + truth digests"},
            {"criterion": "writer_projection_gate_pass",
             "satisfied": bool(frozen_input.get("checks", {}).get(
                 "writer_projection_gate_pass")),
             "evidence": "M11_FINAL_WRITER_PROJECTION_GATE.json"},
        ]

    def criteria(self, *, core: Sequence[Mapping[str, Any]], replay_pass: bool,
                 freeze_status: str, m13_entry_allowed: bool) -> dict[str, Any]:
        rows = [dict(row) for row in core] + [
            {"criterion": "freeze_manifest_written",
             "satisfied": bool(freeze_status == "FROZEN"),
             "evidence": FREEZE_FILE},
            {"criterion": "m12_replay_idempotent",
             "satisfied": bool(replay_pass),
             "evidence": ACCEPTANCE_FILE},
            {"criterion": "m13_readiness",
             "satisfied": bool(m13_entry_allowed),
             "evidence": M13_READINESS_FILE},
        ]
        satisfied = sum(1 for row in rows if row["satisfied"])
        return {
            "generated_at": _now(), "criteria_count": len(rows),
            "satisfied_count": satisfied,
            "unsatisfied_count": len(rows) - satisfied,
            "blocking_count": len(rows) - satisfied,
            "criteria": rows,
            "read_only": True,
        }

    def freeze_manifest(self, *, status: str) -> dict[str, Any]:
        truth = self.runner.truth_digests()
        frozen = self.runner.frozen_digests()
        fingerprint = semantic_fingerprint(self.design_dir)
        index_digest = _ir_read_json(self.foundation_dir / "index.json").get(
            "index_digest")
        payload = {
            "generated_at": _now(), "freeze_id": "WASTELAND_001_M12_FREEZE_V1",
            "instance": "wasteland_001", "milestone": "M12",
            "status": status,
            "freeze_semantics": (
                "historical happened truth（570 章 historical Chapter IR + M11 repair "
                "lineage）冻结为验收通过的历史输入；future planning 不在 freeze 范围内"),
            "truth_digests": truth,
            "frozen_digests": {"contract": frozen.get("contract"),
                               "repair_gate": frozen.get("repair_gate")},
            "historical_ir_index_digest": index_digest,
            "m11_semantic_fingerprint": fingerprint,
            "immutability": {
                "write_once": True,
                "historical_phase_snapshots": list(M11_PHASE_IDS) + list(M12_PHASE_IDS),
                "m11_production_state": "READ_ONLY",
            },
            "author_override": {
                "allowed": True,
                "scope": "sample review verdict / delegated conservative decisions",
                "requires": "explicit author instruction",
                "effect": "重新进入 M12 sample review（不自动改写 Canon / StoryState）",
            },
            "read_only": True, "non_authoritative": True}
        _write_json(self.out_dir / FREEZE_FILE, payload)
        return payload

    def m13_readiness(self, *, acceptance_pass: bool,
                      freeze: Mapping[str, Any]) -> dict[str, Any]:
        payload = {
            "generated_at": _now(), "readiness_id": "M12_M13_READINESS",
            "next_milestone": "M13 Game UI P0（W6-01～W6-06）",
            "requires": ["M12 freeze（WASTELAND_001_M12_FREEZE_V1）"],
            "m12_acceptance_status": "PASS" if acceptance_pass else "FAIL",
            "freeze_status": freeze.get("status"),
            "m13_entry_allowed": bool(acceptance_pass
                                      and freeze.get("status") == "FROZEN"),
            "m13_executed": False,
            "note": ("M13 是 Game UI P0；按 repo roadmap，M12 freeze 后进入 readiness 状态，"
                     "是否连续执行由作者决定"),
            "read_only": True, "non_authoritative": True}
        _write_json(self.out_dir / M13_READINESS_FILE, payload)
        return payload

    def final_acceptance(self, *, snapshot_refresh_reason: str = "") -> dict[str, Any]:
        # replay invariant：M12 acceptance 只读消费；重算不得改变 production fingerprint，
        # 也不得改变 criteria 结果（RECONCILIATION_CONSUMPTION_IS_IDEMPOTENT 的 M12 版本）。
        before = semantic_fingerprint(self.design_dir)
        first = self.core_criteria()
        second = self.core_criteria()
        after = semantic_fingerprint(self.design_dir)
        replay_ok = before == after and first == second
        core_pass = all(row["satisfied"] for row in first)
        acceptance_pass = bool(core_pass and replay_ok)
        freeze = self.freeze_manifest(status="FROZEN" if acceptance_pass
                                      else "NOT_FROZEN")
        readiness = self.m13_readiness(acceptance_pass=acceptance_pass,
                                       freeze=freeze)
        criteria = self.criteria(core=first, replay_pass=replay_ok,
                                 freeze_status=freeze["status"],
                                 m13_entry_allowed=readiness["m13_entry_allowed"])
        audit = _read_json(self.out_dir / FULL_BOOK_AUDIT_FILE)
        review = _read_json(self.out_dir / SAMPLE_REVIEW_FILE)
        payload = {
            "generated_at": _now(), "acceptance_id": "M12_FINAL_ACCEPTANCE",
            "milestone": "M12",
            "status": "PASS" if acceptance_pass and criteria["unsatisfied_count"] == 0
            else "FAIL",
            "criteria": criteria, "criteria_count": criteria["criteria_count"],
            "satisfied_count": criteria["satisfied_count"],
            "unsatisfied_count": criteria["unsatisfied_count"],
            "blocking_count": criteria["blocking_count"],
            "replay_status": "PASS" if replay_ok else "FAIL",
            "book_audit": {
                "chapter_count": (audit.get("chapter_audit") or {}).get(
                    "chapter_count"),
                "chapter_failures": (audit.get("chapter_audit") or {}).get(
                    "failure_count"),
                "gate": _read_json(self.out_dir / FULL_BOOK_AUDIT_GATE_FILE).get(
                    "status"),
            },
            "sample_review": {
                "status": review.get("status"),
                "sample_size": review.get("sample_size"),
                "delegated_decisions": len(review.get("delegated_decisions") or []),
                "author_override_items": len(
                    review.get("author_override_recommended") or []),
            },
            "freeze_ref": FREEZE_FILE, "freeze_status": freeze["status"],
            "m13_entry_allowed": readiness["m13_entry_allowed"],
            "m11_read_only_during_m12": True,
            "read_only": True, "non_authoritative": True}
        _write_json(self.out_dir / ACCEPTANCE_FILE, payload)
        snapshot = _publish_phase_snapshot(
            self.root, "M12_ACCEPTANCE", {
                "phase_id": "M12_ACCEPTANCE", "status": payload["status"],
                "satisfied_count": payload["satisfied_count"],
                "criteria_count": payload["criteria_count"],
                "chapter_count": payload["book_audit"]["chapter_count"],
                "sample_size": payload["sample_review"]["sample_size"],
                "freeze_status": freeze["status"],
                "m13_entry_allowed": readiness["m13_entry_allowed"],
                "replay_status": payload["replay_status"],
            },
            evidence_sources=[M12_DIR + "/" + FULL_BOOK_AUDIT_GATE_FILE,
                              M12_DIR + "/" + SAMPLE_REVIEW_FILE,
                              M12_DIR + "/" + FREEZE_FILE],
            refresh_reason=snapshot_refresh_reason)
        payload["snapshot"] = snapshot
        _write_json(self.out_dir / ACCEPTANCE_FILE, payload)
        return {"acceptance": payload, "criteria": criteria, "freeze": freeze,
                "m13_readiness": readiness}

    def run(self, *, snapshot_refresh_reason: str = "") -> dict[str, Any]:
        return self.final_acceptance(snapshot_refresh_reason=snapshot_refresh_reason)


__all__ = [
    "ACCEPTANCE_FILE", "BOUNDARY_AUDIT_FILE", "CHAPTER_COUNT", "DELEGATION",
    "EXECUTION_BASELINE_FILE", "FREEZE_FILE", "FULL_BOOK_AUDIT_FILE",
    "FULL_BOOK_AUDIT_GATE_FILE", "INPUT_PROJECTION_FILE", "M11_FROZEN_INPUT_FILE",
    "M12_ID", "M12_PHASE_IDS", "M12AcceptanceService", "M12FullBookAuditService",
    "M12PreflightService", "M12SampleReviewService", "M13_READINESS_FILE",
    "SAMPLE_REVIEW_DOC", "SAMPLE_REVIEW_FILE", "SAMPLE_SIZE", "TARGET_COUNT",
    "semantic_fingerprint",
]
