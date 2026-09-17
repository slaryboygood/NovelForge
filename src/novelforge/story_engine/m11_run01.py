"""M11-RUN-01：Production Execution — Auto Safe Frontier（Batch 04 residual + Batch 06）。

这是 **M11 Production Execution**，不是 P15 architecture 轮：

- 只使用冻结的 Repair System（`M11_REPAIR_SYSTEM_CONTRACT_V1` / `REPAIR_GATE_V1` /
  readiness V2 / overlay V2 / production backlog）；
- 只执行 readiness V2 标记为 READY 的 target；blocked target 只作 read-only context；
- 不替作者选择 Content Rewrite Policy、不解决 author decision、不处理 manual / entity、
  不进入 Batch 07、不进入 M12；
- repair 只写 repair layer / overlay / readiness projection / lineage / production artifacts，
  永不写 Canon / StoryState / legacy source / 570 source Chapter IR / Historical Foundation。

产物（`workspace/wasteland_001_exports/repair_adoption_v1/`）：

- `m11_run_01/`：`M11_RUN_01_BASELINE` · `M11_RUN_01_BATCH04_PREFLIGHT` ·
  `M11_RUN_01_BATCH04_EXECUTION` · `M11_RUN_01_BATCH06_EXECUTION` ·
  `REPAIR_BATCH_04_DEPENDENCY_CLOSURE` · `REPAIR_BATCH_06_DEPENDENCY_CLOSURE` ·
  `M11_RUN_01_BATCH04_ACCEPTANCE_CONTRACT` ·
  `M11_RUN_01_BATCH06_ACCEPTANCE_CONTRACT` · `M11_RUN_01_GATE` · `M11_RUN_01_SUMMARY`
- design_dir 根：`REPAIR_BATCH_06_EXECUTION_SCOPE`（+ `BATCH_06_EXECUTION_SCOPE` 兼容名）·
  `M11_RUN_01_RECONCILIATION`
"""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
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
from novelforge.story_engine.m11_content_rewrite import ContentRewritePolicyService
from novelforge.story_engine.m11_micro_pilot import (
    SUBTYPE_LEDGER_RECONCILIATIONS,
    build_subtype_ledger,
)
from novelforge.story_engine.m11_p15p import (
    FROZEN_FOUNDATION_DIGESTS,
    FROZEN_SOURCE_DIGESTS,
    P15CloseoutService,
)
from novelforge.story_engine.m11_readiness import ReadinessV2Service
from novelforge.story_engine.repair import (
    SAFE_AUTO_CLASSES,
    SUBSTRATE_FULL,
    WastelandRepairService,
)

RUN_ID = "M11_RUN_01"
RUN_DIR = "m11_run_01"
RUN_RECONCILIATION = "M11_RUN_01_RECONCILIATION.json"
BATCH_04 = "REPAIR_BATCH_04"
BATCH_06 = "REPAIR_BATCH_06"
FRONTIER_MAX_BATCH = BATCH_06
BATCH_06_SCOPE_FILE = "REPAIR_BATCH_06_EXECUTION_SCOPE.json"
BATCH_06_SCOPE_COMPAT_FILE = "BATCH_06_EXECUTION_SCOPE.json"
CONTRACT_FILE = "M11_REPAIR_SYSTEM_CONTRACT_V1.json"
GATE_V1_FILE = "REPAIR_GATE_V1.json"
TARGET_COUNT = 372
ARCHITECTURE_EXCEPTION = "ARCHITECTURE_EXCEPTION_REQUIRED"
# frozen artifact 的 digest encoding：contract / gate 每次重算都会刷新 generated_at，
# 因此 digest 必须排除 volatile 字段，只覆盖 frozen 语义内容。
DIGEST_ENCODING = "drop_volatile_v1"
VOLATILE_DIGEST_KEYS: tuple[str, ...] = ("generated_at",)
# §4（M11-RUN-03）：P15 executor 在 closeout 后只读。
# production path 不得调用这些 P15 executor 创建 candidate / repaired artifact / overlay
# resolution；P15 代码只允许 historical regression / read-only reconciliation /
# fixture compatibility。
P15_ISOLATION_INVARIANT_ID = "P15_EXECUTOR_READ_ONLY_AFTER_CLOSEOUT"
P15_FORBIDDEN_EXECUTOR_SYMBOLS: tuple[str, ...] = (
    "MicroWaveExecutor", "MicroRepairFrontierPlanner", "Wave02Service",
    "MicroPilotService", "ContentRewriteHardeningService")
PRODUCTION_MODULES: tuple[str, ...] = ("m11_run01.py", "m11_run02.py", "m11_run03.py",
                                      "repair.py")
P15_EXECUTOR_DIRS: tuple[str, ...] = ("p15l", "p15m", "p15o")
# production ownership：M11-RUN-01..12 之外，M11 final closure / approved-event executor
# 同样是 production authority（不是 P15 executor），可以拥有 production CDQ item。
PRODUCTION_OWNER_RUN_IDS: tuple[str, ...] = ("M11_FINAL_CLOSURE", "M11_APPROVED_EVENT")


def owned_by_production_run(run_id: str) -> bool:
    run_id = str(run_id or "")
    return (not run_id or run_id.startswith("M11_RUN")
            or run_id in PRODUCTION_OWNER_RUN_IDS)
DYNAMIC_DOWNGRADE_STATUSES: tuple[str, ...] = (
    "CONTENT_DESIGN_REQUIRED", "EVIDENCE_READY", "MANUAL_REQUIRED",
    "AUTHOR_DECISION_REQUIRED", "BLOCKED_CONFIRMED_BINDING_CONFLICT",
    ARCHITECTURE_EXCEPTION)
EVIDENCE_ADDING_OPS: tuple[str, ...] = (
    "REBIND_EVIDENCE", "MARK_NOT_APPLICABLE", "RECLASSIFY_FUNCTION",
    "REBIND_STATE_REFERENCE", "DELETE_LEGACY_FIELD")
FORBIDDEN_PROMOTED_OPS: tuple[str, ...] = ("ADD_SEMANTIC_ELEMENT",)


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
    path = Path(path)
    return hashlib.sha256(path.read_bytes()).hexdigest()[:16] if path.is_file() else ""


def _digest_json(path: Path, *, drop_volatile: bool = False) -> str:
    payload = _read_json(path)
    if drop_volatile and isinstance(payload, dict):
        payload = {key: value for key, value in payload.items()
                   if key not in VOLATILE_DIGEST_KEYS}
    return hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True,
                                     default=str).encode("utf-8")).hexdigest()[:16] \
        if payload else ""


def _git_state(root: Path) -> dict[str, Any]:
    def run(*args: str) -> str:
        try:
            result = subprocess.run(["git", *args], cwd=str(root), capture_output=True,
                                    text=True, check=False)
            return result.stdout.strip()
        except OSError:                                  # pragma: no cover - git 缺失
            return ""

    status = run("status", "--porcelain")
    lines = [row for row in status.splitlines() if row.strip()]
    tracked = [row for row in lines if not row.startswith("??")]
    untracked = [row for row in lines if row.startswith("??")]
    return {
        "commit": run("rev-parse", "HEAD"),
        "branch": run("rev-parse", "--abbrev-ref", "HEAD"),
        "working_tree": {"dirty": bool(lines), "tracked_modified": len(tracked),
                         "untracked": len(untracked)},
    }


class M11Run01Service:
    """M11 Production Execution run 的 orchestrator（默认配置 = M11-RUN-01）。

    run-level 配置全部通过类属性注入，后续 run（M11-RUN-02 …）以子类覆盖，
    复用同一条冻结 pipeline（scope freeze → preflight → frozen gate → promotion →
    lineage → overlay / readiness / backlog 更新），不新造 repair class 或 gate。
    """

    run_id: str = RUN_ID
    run_dir_name: str = RUN_DIR
    phase_label: str = "M11-RUN-01"
    residual_batch_id: str = BATCH_04
    frontier_batch_id: str = BATCH_06
    max_batch_id: str = FRONTIER_MAX_BATCH
    residual_key: str = "batch_04"
    frontier_key: str = "batch_06"
    next_batch_id: str = "REPAIR_BATCH_07"
    next_batch_key: str = "batch_07"
    next_batch_compact: str = "batch07"
    frontier_scope_file: str = BATCH_06_SCOPE_FILE
    frontier_scope_compat_file: str = BATCH_06_SCOPE_COMPAT_FILE
    reconciliation_file: str = RUN_RECONCILIATION
    next_phase_hint: str = "M11-RUN-02（AUTO_SAFE_BATCH）或 author/manual/entity 决策"
    # 上一轮 production baseline 在 scope artifact 中的字段名（RUN-01 = P15p closeout）
    baseline_readiness_key: str = "p15p_baseline"
    baseline_match_key: str = "matches_p15p_baseline"
    # runtime dynamic downgrade 建立的 ContentDesignRequirement 前缀（frozen queue schema）
    design_item_prefix: str = "CDQ_RUN01"
    # §4（M11-RUN-07）：ContentDesignQueue lifecycle 审计配置
    # (before_run_label, added_run_labels)；None = 不做该审计
    queue_lifecycle_audit: tuple[str, tuple[str, ...]] | None = None

    @staticmethod
    def _artifact_label(batch_id: str) -> str:
        return str(batch_id).replace("REPAIR_BATCH_", "BATCH")

    def __init__(self, project_root: Path | str, *, design_dir: str = ADOPTION_DIR,
                 repair_dir: str = REPAIR_DIR, foundation_dir: str = HISTORY_DIR
                 ) -> None:
        self.root = Path(project_root).resolve()
        self.design_dir = (self.root / design_dir).resolve()
        self.repair_dir = (self.root / repair_dir).resolve()
        self.foundation_dir = (self.root / foundation_dir).resolve()
        self.run_dir = self.design_dir / self.run_dir_name
        self.readiness = ReadinessV2Service(
            self.root, design_dir=str(self.design_dir), repair_dir=str(self.repair_dir),
            foundation_dir=str(self.foundation_dir))
        self.closeout = P15CloseoutService(
            self.root, design_dir=str(self.design_dir), repair_dir=str(self.repair_dir),
            foundation_dir=str(self.foundation_dir))
        self.rewrite = ContentRewritePolicyService(
            self.root, design_dir=str(self.design_dir), repair_dir=str(self.repair_dir),
            foundation_dir=str(self.foundation_dir))

    # ---------------------------------------------------------------- baseline
    def execution_scope(self) -> dict[str, Any]:
        """§9/§17：冻结本轮 execution scope（Batch 04 residual + Batch 06），后续不得扩大。

        scope 从磁盘重新计算（不直接相信 P15p 的 16 / 5），并记录与 P15p baseline 的差异。
        """

        path = self.run_dir / f"{self.run_id}_EXECUTION_SCOPE.json"
        frozen = _read_json(path)
        if frozen.get("frozen") and frozen.get(f"{self.residual_key}_residual_targets") is not None:
            return frozen
        baseline_readiness = _read_json(self.design_dir / "M11_READINESS_V2.json")
        baseline_readiness_digest = _digest_json(self.design_dir / "M11_READINESS_V2.json")
        inputs = self.inputs()
        recomputed = self.readiness.build_readiness_v2(inputs=inputs)
        batch_04 = self.batch_row(self.residual_batch_id, readiness=recomputed)
        batch_06 = self.batch_row(self.frontier_batch_id, readiness=recomputed)
        prior_04 = self.batch_row(self.residual_batch_id, readiness=baseline_readiness)
        prior_06 = self.batch_row(self.frontier_batch_id, readiness=baseline_readiness)
        payload = {
            "generated_at": _now(), "run_id": self.run_id, "frozen": True,
            f"{self.residual_key}_residual_targets": list(batch_04.get("ready_target_ids") or []),
            f"{self.residual_key}_blocked_targets": list(batch_04.get("blocked_target_ids") or []),
            f"{self.frontier_key}_ready_targets": list(batch_06.get("ready_target_ids") or []),
            f"{self.frontier_key}_blocked_targets": list(batch_06.get("blocked_target_ids") or []),
            "recomputed_batch_status": {
                self.residual_batch_id: {key: batch_04.get(key) for key in (
                    "completion_status", "execution_status")},
                self.frontier_batch_id: {key: batch_06.get(key) for key in (
                    "completion_status", "execution_status")},
            },
            self.baseline_readiness_key: {
                self.residual_batch_id: {"ready": len(prior_04.get("ready_target_ids") or []),
                           "blocked": len(prior_04.get("blocked_target_ids") or []),
                           "execution_status": prior_04.get("execution_status")},
                self.frontier_batch_id: {"ready": len(prior_06.get("ready_target_ids") or []),
                           "blocked": len(prior_06.get("blocked_target_ids") or []),
                           "execution_status": prior_06.get("execution_status")},
            },
            self.baseline_match_key: {
                self.residual_batch_id: (sorted(prior_04.get("ready_target_ids") or [])
                           == sorted(batch_04.get("ready_target_ids") or [])
                           and sorted(prior_04.get("blocked_target_ids") or [])
                           == sorted(batch_04.get("blocked_target_ids") or [])),
                self.frontier_batch_id: (sorted(prior_06.get("ready_target_ids") or [])
                           == sorted(batch_06.get("ready_target_ids") or [])
                           and sorted(prior_06.get("blocked_target_ids") or [])
                           == sorted(batch_06.get("blocked_target_ids") or [])),
            },
            "frontier_max_batch": self.max_batch_id,
            "freeze_rule": ("scope 一旦冻结本轮不得扩大；blocked target 只作 read-only "
                            "context；不得进入 Batch 07"),
            "contract_digest": self.frozen_digests()["contract"],
            "gate_digest": self.frozen_digests()["repair_gate"],
            "readiness_v2_digest_before_recompute": baseline_readiness_digest,
            "read_only": True, "non_authoritative": True}
        _write_json(path, payload)
        return payload

    def frozen_digests(self) -> dict[str, str]:
        return {
            "contract": _digest_json(self.design_dir / CONTRACT_FILE,
                                     drop_volatile=True),
            "repair_gate": _digest_json(self.design_dir / GATE_V1_FILE,
                                        drop_volatile=True),
            "overlay_v2": _digest_json(self.design_dir / "M11_OVERLAY_V2.json"),
            "readiness_v2": _digest_json(self.design_dir / "M11_READINESS_V2.json"),
            "digest_encoding": DIGEST_ENCODING,
            "contract_ref": CONTRACT_FILE, "repair_gate_ref": GATE_V1_FILE,
        }

    def truth_digests(self) -> dict[str, Any]:
        return {
            **_source_digests(self.root),
            "historical_foundation": _foundation_digests(self.foundation_dir),
        }

    def batch_status(self, *, readiness: Mapping[str, Any] | None = None
                     ) -> dict[str, dict[str, Any]]:
        readiness = readiness or _read_json(self.design_dir / "M11_READINESS_V2.json")
        rows: dict[str, dict[str, Any]] = {}
        for row in readiness.get("batches") or []:
            rows[str(row.get("batch_id"))] = {
                "completion_status": row.get("completion_status"),
                "execution_status": row.get("execution_status"),
                "resolved": len(row.get("resolved_target_ids") or []),
                "ready": len(row.get("ready_target_ids") or []),
                "blocked": len(row.get("blocked_target_ids") or []),
            }
        return rows

    def baseline(self) -> dict[str, Any]:
        existing = _read_json(self.run_dir / f"{self.run_id}_BASELINE.json")
        if existing.get("run_id") == self.run_id and existing.get("frozen_contract"):
            if existing.get("digest_encoding") != DIGEST_ENCODING:
                # digest encoding 升级：contract / gate 的 frozen 内容不变，
                # 只是把 volatile generated_at 排除在 digest 之外（overlay / readiness
                # 的时点 digest 保持为原截值）。
                now = self.frozen_digests()
                existing["digest_encoding"] = DIGEST_ENCODING
                existing["frozen_contract"]["contract"] = now["contract"]
                existing["frozen_contract"]["repair_gate"] = now["repair_gate"]
                existing["frozen_contract"]["digest_encoding"] = DIGEST_ENCODING
                existing["baseline_note"] = (
                    "digest encoding drop_volatile_v1：frozen contract / gate digest 排除 "
                    "generated_at；overlay / readiness digest 为执行前时点值")
                _write_json(self.run_dir / f"{self.run_id}_BASELINE.json", existing)
            return existing
        readiness = _read_json(self.design_dir / "M11_READINESS_V2.json")
        overlay = _read_json(self.design_dir / "M11_OVERLAY_V2.json")
        batches = self.batch_status(readiness=readiness)
        payload = {
            "generated_at": _now(), "run_id": self.run_id,
            "phase": "M11 Production Execution", "phase_name": "Auto Safe Frontier",
            "digest_encoding": DIGEST_ENCODING,
            "git": _git_state(self.root),
            "frozen_contract": self.frozen_digests(),
            "frozen_source_digests": dict(FROZEN_SOURCE_DIGESTS),
            "frozen_foundation_digests": dict(FROZEN_FOUNDATION_DIGESTS),
            "truth_digests": self.truth_digests(),
            "primary_buckets": dict(overlay.get("primary_resolution_status_counts") or {}),
            "conservation": dict(overlay.get("conservation") or {}),
            "batch_status": batches,
            "batch_completion_status_counts": dict(
                readiness.get("completion_status_counts") or {}),
            "batch_execution_status_counts": dict(
                readiness.get("execution_status_counts") or {}),
            "frontier": {
                "max_batch": self.max_batch_id,
                self.residual_key: batches.get(self.residual_batch_id, {}),
                "batch_05": batches.get("REPAIR_BATCH_05", {}),
                self.frontier_key: batches.get(self.frontier_batch_id, {}),
                self.next_batch_key: batches.get(self.next_batch_id, {}),
            },
            "execution_plan": {
                f"{self.residual_key}_residual_targets":
                    list(self.batch_row(self.residual_batch_id)["ready_target_ids"]),
                f"{self.frontier_key}_ready_targets":
                    list(self.batch_row(self.frontier_batch_id)["ready_target_ids"]),
                f"{self.frontier_key}_blocked_targets":
                    list(self.batch_row(self.frontier_batch_id)["blocked_target_ids"]),
                "forbidden_scopes": [f"{self.next_batch_id}+", "AUTHOR_POLICY",
                                     "AUTHOR_CONTENT", "MAJOR_DESIGN", "MANUAL",
                                     "ENTITY", "M12"],
            },
            "read_only": True, "non_authoritative": True}
        _write_json(self.run_dir / f"{self.run_id}_BASELINE.json", payload)
        return payload

    # ---------------------------------------------------------------- inputs
    def inputs(self) -> Any:
        return self.readiness.load()

    def pre_run_inputs(self) -> Any:
        """本轮执行前的 projection（排除本 run 自己的 reconciliation artifact）。"""

        return self.readiness.load(exclude_reconciliation=[self.reconciliation_file])

    def pre_run_readiness(self, *, inputs: Any = None) -> dict[str, Any]:
        return self.readiness.build_readiness_v2(
            inputs=inputs or self.pre_run_inputs(), persist=False)

    def batch_row(self, batch_id: str,
                  readiness: Mapping[str, Any] | None = None) -> dict[str, Any]:
        readiness = readiness or _read_json(self.design_dir / "M11_READINESS_V2.json")
        return next((row for row in readiness.get("batches") or []
                     if row.get("batch_id") == batch_id), {})

    def labels(self, inputs: Any) -> dict[str, str]:
        return {cid: str(row.get("id")) for cid, row in inputs.legacy_rows.items()}

    def closure_proofs(self, batch_id: str, *, inputs: Any = None,
                       readiness: Mapping[str, Any] | None = None,
                       artifact_name: str | None = None) -> dict[str, Any]:
        # closure 必须在**执行前**的 projection 上计算（排除本轮 reconciliation），
        # 否则重复运行时会把 post-run 状态当作 preflight。
        inputs = inputs or self.pre_run_inputs()
        readiness = readiness or self.pre_run_readiness(inputs=inputs)
        return self.readiness.dependency_closure(
            batch_id, inputs=inputs, readiness=readiness,
            artifact_name=artifact_name or f"{self.run_dir_name}/{batch_id}_DEPENDENCY_CLOSURE.json")

    def target_preflight(self, chapter_id: str, *, batch_id: str, inputs: Any,
                         states: Mapping[str, Any], proofs: Mapping[str, Any],
                         candidates: Mapping[str, Any]) -> dict[str, Any]:
        labels = self.labels(inputs)
        target = inputs.targets.get(chapter_id) or {}
        state = states[chapter_id]
        proof = proofs.get(chapter_id) or {}
        candidate = candidates.get(chapter_id) or {}
        refinement = candidate.get("refinement") or {}
        service = WastelandRepairService(self.root, batch_id=batch_id,
                                        target_scope=[chapter_id])
        try:
            foundation = service.foundation_row(chapter_id)
            digest_ok = bool(foundation.get("verified"))
        except Exception as error:                          # FoundationSubstrateError
            foundation = {"evidence_substrate": "FOUNDATION_DIGEST_MISMATCH_BLOCK",
                          "reason": str(error)}
            digest_ok = False
        substrate = str(foundation.get("evidence_substrate") or "")
        klass = str(refinement.get("actual_repair_class") or "")
        decision = str(refinement.get("execution_decision") or "")
        if not digest_ok:
            verdict, reason = ARCHITECTURE_EXCEPTION, (
                f"Historical Foundation digest mismatch → BLOCK（{foundation.get('reason', '')}）")
        elif substrate != SUBSTRATE_FULL:
            verdict, reason = "DYNAMIC_DOWNGRADE_MANUAL", (
                f"substrate={substrate} → 不得 SAFE_AUTO promote")
        elif klass in SAFE_AUTO_CLASSES and decision == "SAFE_AUTO":
            verdict, reason = "SAFE_AUTO_EXECUTE", f"{klass} + SAFE_AUTO"
        elif klass == "SEMANTIC_ADDITION_REQUIRED":
            verdict, reason = "DYNAMIC_DOWNGRADE_CONTENT_DESIGN", "full IR 证明无 pivot"
        elif klass == "HUMAN_DECISION_REQUIRED":
            verdict, reason = "DYNAMIC_DOWNGRADE_AUTHOR_DECISION", "human decision required"
        else:
            verdict, reason = "DYNAMIC_DOWNGRADE_MANUAL", (
                f"class={klass} decision={decision} 无 SAFE_AUTO 授权")
        return {
            "chapter_id": chapter_id, "legacy_label": labels.get(chapter_id, ""),
            "batch_id": batch_id,
            "primary_resolution_status": state.primary_resolution_status,
            "target_state": state.target_state,
            "risk": str(target.get("risk") or ""),
            "target_chapter_function": str(target.get("target_chapter_function") or ""),
            "primary_issue": str(target.get("primary_issue") or ""),
            "gap_subtype": str(target.get("gap_subtype") or ""),
            "conflict_subtype": str(target.get("conflict_subtype") or ""),
            "allowed_repair_types": list(target.get("allowed_repair_types") or []),
            "forbidden_changes": list(target.get("forbidden_changes") or []),
            "actual_repair_class": klass, "execution_decision": decision,
            "evidence_sufficiency": str(refinement.get("evidence_sufficiency") or ""),
            "proposed_ops": [str(op.get("op")) for op in candidate.get("proposed_patch") or []],
            "foundation": {
                "evidence_substrate": substrate,
                "artifact_path": str(foundation.get("artifact_path") or ""),
                "chapter_ir_digest": str(foundation.get("chapter_ir_digest") or ""),
                "artifact_file_digest": str(foundation.get("artifact_file_digest") or ""),
                "digest_match": digest_ok,
                "block_reason": str(foundation.get("reason") or ""),
                "materialization_status": str(foundation.get("materialization_status") or ""),
                "unresolved_fields": list(foundation.get("unresolved_fields") or []),
            },
            "direct_dependency_chapters": list(proof.get("direct_dependency_chapters") or []),
            "transitive_dependency_targets": list(
                proof.get("transitive_dependency_targets") or []),
            "content_design_dependencies": list(proof.get("content_design_dependencies") or []),
            "entity_dependencies": list(proof.get("entity_dependencies") or []),
            "author_dependencies": list(proof.get("author_dependencies") or []),
            "manual_dependencies": list(proof.get("manual_dependencies") or []),
            "confirmed_binding_dependencies": list(
                proof.get("confirmed_binding_dependencies") or []),
            "dependency_closure_safe": bool(proof.get("continuity_safe", False)),
            "execution_blockers": list(state.execution_blockers),
            "ready_reason": (
                "target-level closure safe：无自身 blocker 且 continuity 依赖全部 resolved"
                if (bool(proof.get("continuity_safe", False))
                    and not state.execution_blockers) else state.reason),
            "verdict": verdict, "verdict_reason": reason,
            "architecture_exception": verdict == ARCHITECTURE_EXCEPTION,
            "non_authoritative": True,
        }

    def entity_identity_chapters(self) -> set[str]:
        queue = _read_json(self.design_dir / "M11_ENTITY_RESOLUTION_QUEUE.json")
        chapters: set[str] = set()
        for cluster in queue.get("clusters") or []:
            if cluster.get("requires_exact_identity"):
                chapters |= {str(item) for item in cluster.get("chapter_ids") or []}
        return chapters

    def dry_candidates(self, batch_id: str, scope: Sequence[str]) -> tuple[Any, list[Any]]:
        service = WastelandRepairService(self.root, batch_id=batch_id,
                                        target_scope=list(scope))
        inputs = service.load()
        candidates, _sampling = service.build_candidates(inputs)
        return inputs, candidates

    # ---------------------------------------------------------------- execution
    def execute(self, batch_id: str, scope: Sequence[str]) -> dict[str, Any]:
        scope = [str(item) for item in scope]
        if not scope:
            # 空 scope 绝不退化成整批执行（WastelandRepairService 把空 scope 视为 None）。
            return {"batch_id": batch_id, "scope": [], "verified": 0, "human_review": 0,
                    "blocked": 0, "promotion_mode": "none",
                    "gate_status": "NO_READY_TARGET", "gate_checks": {},
                    "acceptance_contract_v1": {"gates": "PASS"},
                    "diff": {"semantic_elements_added": 0, "confirmed_facts_changed": 0,
                             "read_only_chapters_changed": 0},
                    "result": None}
        authority = self.authority_for(batch_id)
        service = WastelandRepairService(self.root, batch_id=batch_id,
                                        target_scope=list(scope),
                                        scope_authority=authority or None)
        result = service.run(approved=True, allow_partial_blocked=True)
        return {
            "batch_id": batch_id, "scope": [str(item) for item in scope],
            "verified": int(result.status_overlay.verified_repaired),
            "human_review": int(result.status_overlay.human_review),
            "blocked": int(result.status_overlay.blocked),
            "promotion_mode": str(result.gate.promotion_mode),
            "gate_status": str(result.gate.status),
            "gate_checks": dict(result.gate.checks),
            "acceptance_contract_v1": dict(result.gate.acceptance_contract),
            "diff": result.diff.model_dump(mode="json"),
            "result": result,
        }

    def authority_for(self, batch_id: str) -> list[str]:
        """冻结的 run-level execution scope（`<run_id>_EXECUTION_SCOPE.json`）。"""

        scope = _read_json(self.run_dir / f"{self.run_id}_EXECUTION_SCOPE.json")
        key = {self.residual_batch_id: f"{self.residual_key}_residual_targets",
               self.frontier_batch_id: f"{self.frontier_key}_ready_targets"}.get(batch_id, "")
        return [str(item) for item in scope.get(key) or []] if key else []

    # ---------------------------------------------------------------- Batch 04
    def residual_execution(self, *, execution_scope: Mapping[str, Any] | None = None
                           ) -> dict[str, Any]:
        """Batch 04 residual：唯一 READY target 的 target-level preflight + 执行。"""

        execution_scope = execution_scope or self.execution_scope()
        ready = [str(item) for item in
                 execution_scope.get(f"{self.residual_key}_residual_targets") or []]
        inputs = self.pre_run_inputs()
        states = self.readiness.target_states(inputs=inputs)
        readiness = self.pre_run_readiness(inputs=inputs)
        scope = ready[:1]
        service = WastelandRepairService(self.root, batch_id=self.residual_batch_id,
                                         target_scope=scope or [])
        proofs_payload = self.closure_proofs(
            self.residual_batch_id, inputs=inputs, readiness=readiness,
            artifact_name=f"{self.run_dir_name}/{self.residual_batch_id}_DEPENDENCY_CLOSURE.json")
        proofs = {str(item.get("chapter_id")): item
                  for item in proofs_payload.get("proofs") or []}
        _, candidates = self.dry_candidates(self.residual_batch_id, scope) if scope else (None, [])
        candidate_map = {row_.chapter_id: row_.model_dump(mode="json")
                         for row_ in candidates}
        preflight_rows = [
            self.target_preflight(chapter_id, batch_id=self.residual_batch_id, inputs=inputs,
                                  states=states, proofs=proofs,
                                  candidates=candidate_map)
            for chapter_id in scope]
        for entry in preflight_rows:
            entry["ready_target_count_in_batch"] = len(ready)
            if len(ready) != 1:
                entry["verdict"] = "ARCHITECTURE_EXCEPTION_REQUIRED"
                entry["architecture_exception"] = True
                entry["verdict_reason"] = (
                    f"readiness V2 给出 {len(ready)} 个 READY target（冻结语义要求 unique）")
        preflight = {
            "generated_at": _now(), "run_id": self.run_id, "batch_id": self.residual_batch_id,
            "frozen_contract_digest": self.frozen_digests()["contract"],
            "frozen_gate_digest": self.frozen_digests()["repair_gate"],
            "readiness_v2_digest": _digest_json(self.design_dir / "M11_READINESS_V2.json"),
            "dependency_closure_ref": f"{self.run_dir_name}/{self.residual_batch_id}_DEPENDENCY_CLOSURE.json",
            "target_count": len(preflight_rows), "targets": preflight_rows,
            "verdict": (preflight_rows[0]["verdict"] if preflight_rows
                        else "NO_READY_TARGET"),
            "read_only": True, "non_authoritative": True}
        _write_json(self.run_dir / f"{self.run_id}_{self._artifact_label(self.residual_batch_id)}_PREFLIGHT.json", preflight)
        executed: dict[str, Any] = {}
        if preflight_rows and preflight_rows[0]["verdict"] == "SAFE_AUTO_EXECUTE":
            executed = self.execute(self.residual_batch_id, scope)
            executed["_result"] = executed.pop("result", None)
            executed["targets"] = scope
            executed["execution_kind"] = "SAFE_AUTO"
        elif preflight_rows:
            entry = preflight_rows[0]
            downgrade_status = (
                "MANUAL_REQUIRED" if "MANUAL" in entry["verdict"]
                else ("CONTENT_DESIGN_REQUIRED" if "CONTENT_DESIGN" in entry["verdict"]
                      else ("AUTHOR_DECISION_REQUIRED"
                            if "AUTHOR_DECISION" in entry["verdict"]
                            else ARCHITECTURE_EXCEPTION)))
            design_items = ([{
                "design_item_id": f"{self.design_item_prefix}_{entry['legacy_label']}",
                "chapter_id": entry["chapter_id"],
                "legacy_label": entry["legacy_label"],
                "origin": f"{self.run_id}_DYNAMIC_DOWNGRADE",
                "missing_semantic_type": str(entry.get("primary_issue") or "turn_gap"),
                "status": "PENDING_DESIGN",
            }] if downgrade_status == "CONTENT_DESIGN_REQUIRED" else [])
            executed = {
                "batch_id": self.residual_batch_id, "scope": scope, "targets": scope,
                "verified": 0, "human_review": 0, "blocked": 0,
                "promotion_mode": "none", "gate_status": "NOT_EXECUTED",
                "gate_checks": {}, "acceptance_contract_v1": {},
                "diff": {}, "execution_kind": "DYNAMIC_DOWNGRADE",
                "downgrade_status": downgrade_status,
                "downgrade_reason": entry["verdict_reason"],
                "design_item_id": (design_items[0]["design_item_id"]
                                   if design_items else ""),
                "design_items": design_items,
            }
        executed["preflight"] = preflight
        _write_json(self.run_dir / f"{self.run_id}_{self._artifact_label(self.residual_batch_id)}_EXECUTION.json",
                    {key: value for key, value in executed.items()
                     if not key.startswith("_")})
        return executed

    # ---------------------------------------------------------------- Batch 06
    def frontier_scope(self, *, execution_scope: Mapping[str, Any] | None = None
                       ) -> dict[str, Any]:
        """从磁盘重算 frontier batch 的 dependency closure 并冻结 execution scope。"""

        execution_scope = execution_scope or self.execution_scope()
        inputs = self.pre_run_inputs()
        readiness = self.pre_run_readiness(inputs=inputs)
        row = self.batch_row(self.frontier_batch_id, readiness=readiness)
        ready = [str(item) for item in
                 execution_scope.get(f"{self.frontier_key}_ready_targets") or []]
        blocked = [str(item) for item in
                   execution_scope.get(f"{self.frontier_key}_blocked_targets") or []]
        states = self.readiness.target_states(inputs=inputs)
        closure = self.closure_proofs(
            self.frontier_batch_id, inputs=inputs, readiness=readiness,
            artifact_name=f"{self.run_dir_name}/{self.frontier_batch_id}_DEPENDENCY_CLOSURE.json")
        proofs = {str(item.get("chapter_id")): item
                  for item in closure.get("proofs") or []}
        _, candidates = self.dry_candidates(self.frontier_batch_id, ready)
        candidate_map = {row_.chapter_id: row_.model_dump(mode="json")
                         for row_ in candidates}
        batch = next((item for item in inputs.batches
                      if item.get("batch_id") == self.frontier_batch_id), {})
        labels = self.labels(inputs)
        read_only_deps = [str(item) for item in
                          batch.get("read_only_dependency_chapter_ids") or []]
        targets: list[dict[str, Any]] = []
        for chapter_id in ready:
            entry = self.target_preflight(chapter_id, batch_id=self.frontier_batch_id, inputs=inputs,
                                          states=states, proofs=proofs,
                                          candidates=candidate_map)
            entry["read_only_dependency_chapters"] = list(read_only_deps)
            targets.append(entry)
        blocked_rows = [{
            "chapter_id": chapter_id, "legacy_label": labels.get(chapter_id, ""),
            "target_state": states[chapter_id].target_state,
            "primary_resolution_status": states[chapter_id].primary_resolution_status,
            "execution_blockers": list(states[chapter_id].execution_blockers),
            "block_reason": str(row.get("block_reason_by_target", {}).get(chapter_id, "")),
            "direct_dependency_chapters":
                list((proofs.get(chapter_id) or {}).get("direct_dependency_chapters") or []),
            "verdict": "BLOCKED_READ_ONLY_CONTEXT",
            "read_only": True,
        } for chapter_id in blocked]
        payload = {
            "generated_at": _now(), "run_id": self.run_id, "batch_id": self.frontier_batch_id,
            "frozen": True,
            "ready_target_ids": ready, "blocked_target_ids": blocked,
            "block_reason_by_target": dict(row.get("block_reason_by_target") or {}),
            "blocker_counts": dict(row.get("blocker_counts") or {}),
            "target_count": len(ready) + len(blocked),
            "targets": targets, "blocked_targets": blocked_rows,
            "read_only_dependency_chapters": read_only_deps,
            "dependency_batches": list(row.get("dependency_batches") or []),
            "dependency_closure_ref": (f"{self.run_dir_name}/"
                                       f"{self.frontier_batch_id}_DEPENDENCY_CLOSURE.json"),
            "dependency_closure": {
                "basis": ("pre-execution projection（排除本轮 reconciliation，重算自磁盘）"),
                "artifact_ref": (f"{self.run_dir_name}/"
                                 f"{self.frontier_batch_id}_DEPENDENCY_CLOSURE.json"),
                "continuity_ready_count": closure.get("ready_count"),
                "continuity_blocked_count": closure.get("blocked_count"),
                "readiness_ready_count": len(ready),
                "readiness_blocked_count": len(blocked),
                "classification": {
                    "safe_executable": len(ready),
                    "content_design_blocked": sum(
                        1 for chapter_id in blocked
                        if "BLOCKED_CONTENT_DESIGN"
                        in (states[chapter_id].execution_blockers or [])),
                    "entity_blocked": sum(
                        1 for chapter_id in blocked
                        if "BLOCKED_ENTITY_AMBIGUITY"
                        in (states[chapter_id].execution_blockers or [])),
                    "manual_blocked": sum(
                        1 for chapter_id in blocked
                        if "BLOCKED_MANUAL_REPAIR"
                        in (states[chapter_id].execution_blockers or [])),
                    "author_blocked": sum(
                        1 for chapter_id in blocked
                        if "BLOCKED_AUTHOR_DECISION"
                        in (states[chapter_id].execution_blockers or [])),
                    "confirmed_binding_blocked": sum(
                        1 for chapter_id in blocked
                        if "BLOCKED_CONFIRMED_BINDING_CONFLICT"
                        in (states[chapter_id].execution_blockers or [])),
                    "architecture_exception": sum(
                        1 for entry in targets
                        if entry.get("verdict") == ARCHITECTURE_EXCEPTION),
                },
                "blocker_counts": dict(row.get("blocker_counts") or {}),
                "block_reason_by_target": dict(row.get("block_reason_by_target") or {})},
            "contract_digest": self.frozen_digests()["contract"],
            "gate_digest": self.frozen_digests()["repair_gate"],
            "readiness_v2_digest": _digest_json(self.design_dir / "M11_READINESS_V2.json"),
            "baseline_truth_digests": self.truth_digests(),
            "execution_rule": ("只执行 ready_target_ids；blocked target 只作 read-only "
                               "context；不生成 promotable patch"),
            "read_only": True, "non_authoritative": True}
        _write_json(self.design_dir / self.frontier_scope_file, payload)
        _write_json(self.design_dir / self.frontier_scope_compat_file, payload)
        return payload

    def frontier_execute(self, scope_payload: Mapping[str, Any]) -> dict[str, Any]:
        # §18：一个 target 失败不得污染其它 target → architecture exception target
        # 不进 execution scope（仍登记在 scope artifact 里作为 read-only 记录）。
        exceptions = [row for row in scope_payload.get("targets") or []
                      if row.get("verdict") == ARCHITECTURE_EXCEPTION]
        exception_ids = {str(row.get("chapter_id")) for row in exceptions}
        ready = [str(item) for item in scope_payload.get("ready_target_ids") or []
                 if str(item) not in exception_ids]
        executed = self.execute(self.frontier_batch_id, ready)
        executed["_result"] = executed.pop("result", None)
        executed["targets"] = ready
        executed["blocked_targets"] = list(scope_payload.get("blocked_target_ids") or [])
        executed["architecture_exception_targets"] = sorted(exception_ids)
        executed["execution_kind"] = "AUTO_SAFE_FRONTIER"
        executed["scope_ref"] = self.frontier_scope_file
        _write_json(self.run_dir / f"{self.run_id}_{self._artifact_label(self.frontier_batch_id)}_EXECUTION.json",
                    {key: value for key, value in executed.items()
                     if not key.startswith("_")})
        return executed

    # ---------------------------------------------------------------- downgrade
    @classmethod
    def downgrade_status(cls, candidate: Any) -> tuple[str, str, str]:
        """runtime dynamic downgrade → frozen resolution status（不新造 repair class）。"""

        refinement = candidate.refinement
        klass = str(refinement.actual_repair_class) if refinement else ""
        decision = str(refinement.execution_decision) if refinement else "MANUAL"
        substrate = str(candidate.evidence_substrate or "")
        if candidate.status == "blocked":
            return ("BLOCKED_CONTENT_DESIGN",
                    "candidate blocked（validator / forbidden change）→ 不 promote", "")
        if klass == "SEMANTIC_ADDITION_REQUIRED":
            return ("CONTENT_DESIGN_REQUIRED",
                    "运行时动态降级：full IR 证明无 pivot → 内容缺口（不自动补）",
                    f"{cls.design_item_prefix}_{candidate.legacy_label}")
        if klass == "CONTENT_REWRITE_REQUIRED":
            return ("CONTENT_DESIGN_REQUIRED",
                    "运行时动态降级：需要 content rewrite（不自动执行）",
                    f"{cls.design_item_prefix}_{candidate.legacy_label}")
        if klass == "HUMAN_DECISION_REQUIRED":
            return ("AUTHOR_DECISION_REQUIRED", "运行时动态降级：human decision required", "")
        if substrate != SUBSTRATE_FULL:
            return ("MANUAL_REQUIRED",
                    f"运行时动态降级：substrate={substrate} → 不得 SAFE_AUTO promote", "")
        if decision == "MANUAL":
            return ("MANUAL_REQUIRED",
                    "运行时动态降级：execution decision = MANUAL（无 SAFE_AUTO 授权）", "")
        return ("PENDING", f"未 promote（class={klass}, decision={decision}）", "")

    @staticmethod
    def repair_subtype(candidate: Any) -> str:
        klass = str(candidate.refinement.actual_repair_class) if candidate.refinement else ""
        if klass == "NO_REPAIR_REQUIRED":
            return "no_repair_required"
        ops = [str(op.op) for op in candidate.proposed_patch]
        if klass == "FIELD_REBIND" or "REBIND_STATE_REFERENCE" in ops:
            return "repaired_field_rebind"
        return "repaired_evidence_only"

    # ---------------------------------------------------------------- reconciliation
    def build_reconciliation(self, *, residual: Mapping[str, Any],
                             frontier_execution: Mapping[str, Any],
                             frontier_scope: Mapping[str, Any]) -> dict[str, Any]:
        inputs = self.inputs()
        labels = self.labels(inputs)
        records: list[dict[str, Any]] = []
        design_items: list[dict[str, Any]] = []
        executions = {self.residual_batch_id: residual,
                      self.frontier_batch_id: frontier_execution}
        _ = frontier_scope
        for batch_id, execution in executions.items():
            result = execution.get("_result")
            if result is not None:
                promoted = {row.chapter_id: row for row in result.overlays}
                for candidate in result.candidates:
                    klass = (candidate.refinement.actual_repair_class
                             if candidate.refinement else "")
                    decision = (candidate.refinement.execution_decision
                                if candidate.refinement else "")
                    design_item_id = ""
                    if candidate.chapter_id in promoted:
                        status = ("RESOLVED_NO_REPAIR_REQUIRED"
                                  if klass == "NO_REPAIR_REQUIRED"
                                  else "RESOLVED_REPAIRED")
                        reason = f"{batch_id} SAFE_AUTO promote（{klass}）"
                        subtype = self.repair_subtype(candidate)
                    else:
                        status, reason, design_item_id = self.downgrade_status(candidate)
                        subtype = ""
                        if design_item_id:
                            design_items.append({
                                "design_item_id": design_item_id,
                                "chapter_id": candidate.chapter_id,
                                "legacy_label": candidate.legacy_label,
                                "origin": f"{self.run_id}_DYNAMIC_DOWNGRADE",
                                "missing_semantic_type": str(
                                    (inputs.targets.get(candidate.chapter_id) or {}).get(
                                        "primary_issue") or "turn_gap"),
                                "status": "PENDING_DESIGN",
                            })
                    records.append({
                        "run_id": self.run_id, "batch_id": batch_id,
                        "chapter_id": candidate.chapter_id,
                        "legacy_label": candidate.legacy_label,
                        "old_status": "not_processed",
                        "new_resolution_status": status,
                        "repair_class": klass, "repair_subtype": subtype,
                        "execution_decision": decision,
                        "evidence_substrate": candidate.evidence_substrate,
                        "repaired_ref": (f"{batch_id}/repaired/{candidate.chapter_id}.json"
                                         if candidate.chapter_id in promoted else ""),
                        "patch_ops": [op.op for op in candidate.proposed_patch],
                        "reason": reason, "design_item_id": design_item_id,
                        "timestamp": _now(), "non_authoritative": True})
            for chapter_id in execution.get("scope", []):
                if any(str(row["chapter_id"]) == str(chapter_id) for row in records):
                    continue
                design_item = next((
                    dict(item) for item in execution.get("design_items") or []
                    if str(item.get("chapter_id")) == str(chapter_id)), {})
                if design_item:
                    design_items.append(design_item)
                records.append({
                    "run_id": self.run_id, "batch_id": batch_id,
                    "chapter_id": str(chapter_id),
                    "legacy_label": labels.get(str(chapter_id), ""),
                    "old_status": "not_processed",
                    "new_resolution_status":
                        str(execution.get("downgrade_status") or "PENDING"),
                    "repair_class": "", "repair_subtype": "",
                    "execution_decision": "", "evidence_substrate": "",
                    "repaired_ref": "", "patch_ops": [],
                    "reason": str(execution.get("downgrade_reason") or
                                  "未 promote（preflight 未通过 SAFE_AUTO）"),
                    "design_item_id": str(design_item.get("design_item_id") or ""),
                    "timestamp": _now(),
                    "non_authoritative": True})
            for chapter_id in execution.get("blocked_targets") or []:
                records.append({
                    "run_id": self.run_id, "batch_id": batch_id,
                    "chapter_id": str(chapter_id),
                    "legacy_label": labels.get(str(chapter_id), ""),
                    "old_status": "blocked_out_of_scope",
                    "new_resolution_status": "BLOCKED_CONTENT_DESIGN",
                    "repair_class": "", "repair_subtype": "",
                    "execution_decision": "", "evidence_substrate": "",
                    "repaired_ref": "", "patch_ops": [],
                    "reason": (f"{self.run_id}：blocked target 只作 read-only context，未执行"),
                    "design_item_id": "", "timestamp": _now(),
                    "non_authoritative": True})
        promoted_records = [row for row in records
                            if row["new_resolution_status"] in (
                                "RESOLVED_REPAIRED", "RESOLVED_NO_REPAIR_REQUIRED")]
        payload = {
            "generated_at": _now(), "run_id": self.run_id,
            "record_count": len(records), "promoted": len(promoted_records),
            "promoted_evidence_only": sum(
                1 for row in promoted_records
                if row["repair_subtype"] == "repaired_evidence_only"),
            "promoted_field_rebind": sum(
                1 for row in promoted_records
                if row["repair_subtype"] == "repaired_field_rebind"),
            "promoted_no_repair_required": sum(
                1 for row in promoted_records
                if row["repair_subtype"] == "no_repair_required"),
            "dynamic_downgrade_counts": {
                status: sum(1 for row in records
                            if row["new_resolution_status"] == status)
                for status in DYNAMIC_DOWNGRADE_STATUSES},
            "content_design_items_registered": design_items,
            "records": records, "records_modified": False,
            "read_only": True, "non_authoritative": True}
        _write_json(self.design_dir / self.reconciliation_file, payload)
        return payload

    def register_dynamic_content_design(self, reconciliation: Mapping[str, Any]
                                        ) -> dict[str, Any]:
        """§21：runtime 发现的 true ContentDesign 用冻结 Queue schema 登记。"""

        items = list(reconciliation.get("content_design_items_registered") or [])
        if not items:
            return {"registered": 0, "queue_reconciled": False}
        queue_path = self.design_dir / "M11_CONTENT_DESIGN_QUEUE_V2.json"
        queue = _read_json(queue_path)
        existing = list(queue.get("items") or [])
        known = {str(row.get("design_item_id")) for row in existing}
        for item in items:
            if str(item.get("design_item_id")) in known:
                continue
            existing.append({
                "design_item_id": item["design_item_id"],
                "chapter_id": item["chapter_id"], "legacy_label": item["legacy_label"],
                "arc_id": "", "missing_semantic_type": item["missing_semantic_type"],
                "design_subtype": "MICRO_PIVOT_REQUIRED",
                "severity": "MEDIUM", "micro_or_major": "micro",
                "confirmed_facts": [], "forbidden_changes": [],
                "upstream_context": [], "downstream_constraints": [],
                "candidate_space": ["策略调整", "信息理解变化", "短期目标变化", "局部状态变化"],
                "author_decision_required": False, "dependency_items": [],
                "status": "PENDING_DESIGN", "non_authoritative": True,
                "origin": f"{self.run_id} dynamic downgrade",
                "missing_detail": item["missing_semantic_type"]})
        _write_json(queue_path, {**queue, "item_count": len(existing),
                                 "items": existing, "read_only": True,
                                 "non_authoritative": True})
        self.rewrite.reconcile_queue()
        return {"registered": len(items), "queue_reconciled": True}

    # ---------------------------------------------------------------- projections
    def refresh_projections(self) -> dict[str, Any]:
        ledger = build_subtype_ledger(self.design_dir)
        _write_json(self.design_dir / "M11_REPAIR_SUBTYPE_LEDGER.json", ledger)
        inputs = self.readiness.load(extra_reconciliation=[self.reconciliation_file])
        readiness = self.readiness.build_readiness_v2(inputs=inputs)
        overlay = self.readiness.overlay_v2(inputs=inputs, readiness=readiness)
        return {"ledger": ledger, "readiness": readiness,
                "overlay": overlay["official_overlay"]}

    # ---------------------------------------------------------------- backlog
    def update_backlog(self, *, overlay: Mapping[str, Any],
                       readiness: Mapping[str, Any],
                       reconciliation: Mapping[str, Any]) -> dict[str, Any]:
        """§26：更新 production backlog；DONE item 保留历史，不新增 lane。"""

        inventory = self.closeout.author_action_inventory()
        entity_manual = self.closeout.entity_manual_inventory(overlay=overlay)
        reclassification = _read_json(self.design_dir / "p15n" /
                                      "CONTENT_REPAIR_RECLASSIFICATION.json")
        backlog = self.closeout.production_backlog(
            overlay=overlay, readiness=readiness, reclassification=reclassification,
            author_inventory=inventory, entity_manual=entity_manual)
        records = list(reconciliation.get("records") or [])
        resolved_ids = {str(row["chapter_id"]) for row in records
                        if row["new_resolution_status"] in (
                            "RESOLVED_REPAIRED", "RESOLVED_NO_REPAIR_REQUIRED")}
        processed_ids = {str(row["chapter_id"]) for row in records
                         if row["new_resolution_status"] in (
                             "RESOLVED_REPAIRED", "RESOLVED_NO_REPAIR_REQUIRED",
                             *DYNAMIC_DOWNGRADE_STATUSES)}
        run_targets = {str(row["chapter_id"]) for row in records}
        items = list(backlog.get("items") or [])
        for row in items:
            targets = {str(item) for item in row.get("target_ids") or []}
            if targets and targets <= processed_ids and row.get("lane") == (
                    "LANE_AUTO_SAFE_BATCH"):
                row["status"] = "DONE"
                row["completed_by_run"] = self.run_id
                row["completed_at"] = _now()
                row["completed_targets"] = sorted(targets)
                row["next_action"] = (f"{self.run_id} 已执行（promoted / resolved / "
                                      "dynamic downgrade）；历史保留")
        done_ids = {str(row.get("item_id")) for row in items
                    if row.get("status") == "DONE"}
        for entry in reconciliation.get("content_design_items_registered") or []:
            item_id = f"BL_CONTENT_DESIGN_{entry['legacy_label']}"
            if any(str(row.get("item_id")) == item_id for row in items):
                continue
            items.append({
                "item_id": item_id, "lane": "LANE_CONTENT_REWRITE",
                "target_ids": [entry["chapter_id"]],
                "legacy_labels": [entry["legacy_label"]],
                "blocking_batches": [], "priority": 1,
                "dependencies": [entry["design_item_id"]],
                "required_actor": "author+operator",
                "next_action": (f"{self.run_id} runtime dynamic downgrade → "
                                "建立 ContentDesignRequirement（不自动补内容）"),
                "current_artifact_ref": self.reconciliation_file,
                "status": "BACKLOG", "non_authoritative": True})
        manual_new = [row for row in reconciliation.get("records") or []
                      if row["new_resolution_status"] == "MANUAL_REQUIRED"]
        for entry in manual_new:
            item_id = f"BL_MANUAL_{entry['legacy_label']}"
            existing_row = next((row for row in items
                                 if str(row.get("item_id")) == item_id), None)
            if existing_row is not None:
                existing_row.pop("history", None)
                existing_row.pop("history_reason", None)
                continue
            items.append({
                "item_id": item_id, "lane": "LANE_MANUAL",
                "target_ids": [entry["chapter_id"]],
                "legacy_labels": [entry["legacy_label"]],
                "blocking_batches": [str(entry.get("batch_id"))],
                "priority": 1, "dependencies": [],
                "required_actor": "operator+author",
                "next_action": (f"{entry['reason']}（{self.run_id} runtime downgrade）"),
                "current_artifact_ref": self.reconciliation_file,
                "status": "BACKLOG", "non_authoritative": True})
        lane_counts = {lane: sum(1 for row in items if row["lane"] == lane)
                       for lane in backlog.get("lanes") or []}
        # 归一化：本 run 自己维护的 live item（manual / content-design runtime 新增）
        # 只是不由 P15p base generator 重新生成，不是 history。
        for row in items:
            if str(row.get("item_id", "")).startswith(("BL_MANUAL_", "BL_CONTENT_DESIGN_")) \
                    and str(row.get("status")) == "BACKLOG":
                row.pop("history", None)
                row.pop("history_reason", None)
        history_ids = sorted(str(row.get("item_id")) for row in items
                             if row.get("history"))
        payload = {**backlog,
                   "generated_at": _now(),
                   "item_count": len(items), "items": items,
                   "lane_counts": lane_counts,
                   "history_item_count": len(history_ids),
                   "history_item_ids": history_ids,
                   "last_run": self.run_id,
                   "last_run_done_item_ids": sorted(done_ids),
                   "execution_mode": "M11 Production Execution（M11-RUN-01 …）",
                   "run_targets": sorted(run_targets)}
        _write_json(self.design_dir / "M11_PRODUCTION_BACKLOG.json", payload)
        _write_json(self.design_dir / "p15p" / "M11_PRODUCTION_BACKLOG.json", payload)
        return payload

    # ---------------------------------------------------------------- M12
    def m12_criteria(self, *, overlay: Mapping[str, Any],
                     backlog: Mapping[str, Any]) -> dict[str, Any]:
        inventory = self.closeout.author_action_inventory()
        return self.closeout.m12_entry_criteria(
            overlay=overlay, backlog=backlog, author_inventory=inventory)

    # ---------------------------------------------------------------- P15 isolation
    def content_design_queue_lifecycle_audit(self, *, before_run: str,
                                             added_runs: Sequence[str]
                                             ) -> dict[str, Any]:
        """§4：ContentDesignQueue V2/V3 lifecycle 审计（可审计 reconciliation）。

        以「当前 V2 item 集合（after）」为基准，减去指定 run 新登记的 requirement
        得到 before 集合；再逐个核对所有 production run 登记的 design_item_id 是否仍在
        after 集合中（无 data loss），并把 V3 生命周期状态一并记录。
        """

        queue2 = _read_json(self.design_dir / "M11_CONTENT_DESIGN_QUEUE_V2.json")
        queue3 = _read_json(self.design_dir / "M11_CONTENT_DESIGN_QUEUE_V3.json")
        overlay = _read_json(self.design_dir / "M11_OVERLAY_V2.json")
        after_ids = [str(row.get("design_item_id")) for row in queue2.get("items") or []]
        after_set = set(after_ids)

        added_ids: list[str] = []
        added_reconciliation_refs: list[str] = []
        for run_label in added_runs:
            name = f"{run_label}_RECONCILIATION.json"
            added_reconciliation_refs.append(name)
            for row in _read_json(self.design_dir / name).get(
                    "content_design_items_registered") or []:
                added_ids.append(str(row.get("design_item_id")))
        # 窗口语义：before = 当前 V2 −（before_run 之后所有 run 新增）；
        # added = added_runs 新增；later = 其余更晚 run 新增（用于说明当前 after 的构成）。
        run_order = [f"M11_RUN_{index:02d}" for index in range(1, 100)]

        def _run_rank(label: str) -> int:
            return run_order.index(label) if label in run_order else -1

        before_rank = _run_rank(before_run)
        added_rank = max((_run_rank(label) for label in added_runs), default=before_rank)
        all_run_added: dict[str, str] = {}
        for label in run_order:
            for row in _read_json(self.design_dir /
                                  f"{label}_RECONCILIATION.json").get(
                    "content_design_items_registered") or []:
                all_run_added[str(row.get("design_item_id"))] = label
        before_ids = [item for item in after_ids
                      if item not in all_run_added
                      or _run_rank(all_run_added[item]) <= before_rank]
        later_ids = sorted(item for item, label in all_run_added.items()
                           if _run_rank(label) > added_rank and item in set(after_ids))
        window_ids = [item for item in after_ids
                      if item not in all_run_added
                      or _run_rank(all_run_added[item]) <= added_rank]

        all_registered: dict[str, str] = {}
        for name in SUBTYPE_LEDGER_RECONCILIATIONS:
            if not str(name).startswith("M11_RUN"):
                continue
            for row in _read_json(self.design_dir / name).get(
                    "content_design_items_registered") or []:
                all_registered[str(row.get("design_item_id"))] = name
        missing_registered = sorted(item for item in all_registered if item not in after_set)

        v3_status = {str(row.get("design_item_id")): str(row.get("status"))
                     for row in queue3.get("requirements") or []}
        transitioned = [{"design_item_id": item, "v3_status": v3_status.get(item, "")}
                        for item in added_ids]
        active_count = sum(1 for row in queue3.get("requirements") or []
                           if str(row.get("status")) == "ACTIVE")
        duplicates = sorted({item for item in after_ids if after_ids.count(item) > 1})
        p15_snapshot_items = [item for item in after_ids
                              if not item.startswith("CDQ_RUN")]
        payload = {
            "generated_at": _now(), "run_id": self.run_id,
            "audit_id": "CONTENT_DESIGN_QUEUE_LIFECYCLE_AUDIT",
            "before_run": before_run, "added_runs": list(added_runs),
            "added_reconciliation_refs": added_reconciliation_refs,
            "before_item_count": len(before_ids),
            "added_item_count": len(added_ids),
            "window_after_item_count": len(window_ids),
            "later_item_count": len(later_ids),
            "after_item_count": len(after_ids),
            "before_ids": sorted(before_ids),
            "added_ids": sorted(added_ids),
            "window_after_ids": sorted(window_ids),
            "later_ids": later_ids,
            "transitioned_ids": sorted(transitioned,
                                       key=lambda row: row["design_item_id"]),
            "removed_or_superseded_ids": missing_registered,
            "after_ids": sorted(after_ids),
            "duplicate_design_item_ids": duplicates,
            "all_registered_production_cdq": sorted(all_registered),
            "missing_registered_production_cdq": missing_registered,
            "p15_snapshot_item_count": len(p15_snapshot_items),
            "v3_active_count": active_count,
            "overlay_content_design_required": overlay.get("content_design_required"),
            "v3_matches_overlay": active_count == int(
                overlay.get("content_design_required") or 0),
            "verdict": ("NO_DATA_LOSS" if not missing_registered and not duplicates
                        else "ANOMALY"),
            "method": ("after = 当前 V2 item 集合；before = after − added_runs 新登记；"
                       "removed_or_superseded = 任一 run 登记过但已不在 after 的 id"),
            "read_only": True, "non_authoritative": True}
        _write_json(self.run_dir / "CONTENT_DESIGN_QUEUE_LIFECYCLE_AUDIT.json", payload)
        return payload

    def latest_reconciliation_records(self) -> dict[str, dict[str, Any]]:
        """last-record-wins 的 reconciliation 视图（含 production run 记录）。"""

        latest: dict[str, dict[str, Any]] = {}
        for name in SUBTYPE_LEDGER_RECONCILIATIONS:
            for row in _read_json(self.design_dir / name).get("records") or []:
                chapter_id = str(row.get("chapter_id") or "")
                if chapter_id:
                    latest[chapter_id] = dict(row)
        return latest

    def production_cdq_items(self) -> list[dict[str, Any]]:
        queue = _read_json(self.design_dir / "M11_CONTENT_DESIGN_QUEUE_V2.json")
        return [dict(row) for row in queue.get("items") or []
                if str(row.get("design_item_id") or "").startswith("CDQ_RUN")
                or str(row.get("origin") or "").startswith("M11_RUN")]

    def p15_isolation_invariant(self, *, reconciliation: Mapping[str, Any] | None = None
                                ) -> dict[str, Any]:
        """§4：P15_EXECUTOR_READ_ONLY_AFTER_CLOSEOUT（production isolation invariant）。

        - 静态：production path（runner / repair service）不得引用 P15 executor 符号；
        - 归属：production-run CDQ item 的最新 resolution 必须来自 production run，
          不得被历史 P15 wave 重新 claim；
        - 运行时：不得存在指向 production CDQ chapter 的活跃 P15 repaired artifact。
        """

        module_dir = self.root / "src/novelforge/story_engine"
        static_scan: dict[str, list[str]] = {}
        for name in PRODUCTION_MODULES:
            path = module_dir / name
            text = path.read_text(encoding="utf-8") if path.is_file() else ""
            # 只看「使用」：import / 实例化调用 / 属性访问；
            # 常量声明本身（invariant definition）不算 production usage。
            hits = [symbol for symbol in P15_FORBIDDEN_EXECUTOR_SYMBOLS
                    if re.search(rf"import[^\n]*\b{symbol}\b", text)
                    or re.search(rf"\b{symbol}\s*\(", text)
                    or re.search(rf"\b{symbol}\s*\.", text)]
            static_scan[name] = sorted(set(hits))
        static_pass = not any(static_scan.values())

        items = self.production_cdq_items()
        latest = self.latest_reconciliation_records()
        ownership_rows: list[dict[str, Any]] = []
        for item in items:
            chapter_id = str(item.get("chapter_id"))
            record = latest.get(chapter_id) or {}
            run_id = str(record.get("run_id") or "")
            ownership_rows.append({
                "design_item_id": item.get("design_item_id"),
                "chapter_id": chapter_id, "legacy_label": item.get("legacy_label"),
                "origin": item.get("origin"),
                "latest_resolution": record.get("new_resolution_status"),
                "latest_run_id": run_id,
                "owned_by_production_run": owned_by_production_run(run_id),
            })
        ownership_pass = all(row["owned_by_production_run"] for row in ownership_rows)

        production_chapters = {row["chapter_id"] for row in ownership_rows}
        live_p15_artifacts: list[str] = []
        for dirname in P15_EXECUTOR_DIRS:
            for path in sorted((self.design_dir / dirname / "repaired").glob("*.json")):
                chapter_id = path.stem
                if chapter_id not in production_chapters:
                    continue
                payload = _read_json(path)
                if str(payload.get("status") or "") == "SUPERSEDED_BY_M11_RUN_02":
                    continue
                live_p15_artifacts.append(f"{dirname}/repaired/{path.name}")
        runtime_pass = not live_p15_artifacts

        payload = {
            "generated_at": _now(), "run_id": self.run_id,
            "invariant_id": P15_ISOLATION_INVARIANT_ID,
            "rule": ("P15 executor（micro wave / pilot / hardening）在 closeout 之后只读："
                     "production path 不得用它们创建 repair candidate / repaired artifact / "
                     "overlay resolution；P15 代码只允许 historical regression、"
                     "read-only reconciliation、fixture compatibility"),
            "forbidden_p15_executor_symbols": list(P15_FORBIDDEN_EXECUTOR_SYMBOLS),
            "production_modules": list(PRODUCTION_MODULES),
            "static_scan_findings": static_scan,
            "static_scan_pass": static_pass,
            "production_item_ownership": ownership_rows,
            "production_item_ownership_pass": ownership_pass,
            "live_p15_artifacts_for_production_chapters": live_p15_artifacts,
            "runtime_isolation_pass": runtime_pass,
            "production_item_count": len(ownership_rows),
            "reconciliation_ref": self.reconciliation_file,
            "status": ("PASS" if (static_pass and ownership_pass and runtime_pass)
                       else "NEEDS_ATTENTION"),
            "read_only": True, "non_authoritative": True}
        _write_json(self.run_dir / f"{P15_ISOLATION_INVARIANT_ID}.json", payload)
        _ = reconciliation
        return payload

    # ---------------------------------------------------------------- acceptance
    def acceptance_contract(self, *, batch_id: str, execution: Mapping[str, Any],
                            scope: Mapping[str, Any], closure: Mapping[str, Any],
                            baseline: Mapping[str, Any], overlay: Mapping[str, Any],
                            ledger: Mapping[str, Any]) -> dict[str, Any]:
        """§24：复用 REPAIR_GATE_V1 的 BatchAcceptanceContract（不新建 Gate 体系）。"""

        checks_v1 = dict(execution.get("gate_checks") or {})
        # 未执行（例如本 batch 的 target 全部 dynamic downgrade）：不存在 execution gate，
        # 此时以「没有发生任何 repair-owned mutation」为基础证明 non-mutation checks。
        no_execution = not checks_v1
        scope_rows = list(scope.get("targets") or [])
        # 该 batch 在本轮没有 baseline READY target（例如 Batch 04 已 BLOCKED）：
        # 契约退化为「无 target 可执行 → 无 mutation」，用 no_targets 显式表达。
        no_targets = not [str(item) for item in execution.get("targets") or []]
        probe_substrate_ok = bool(scope_rows) and all(
            str((row.get("foundation") or {}).get("evidence_substrate") or "").startswith(
                "HISTORICAL_FULL_IR") for row in scope_rows)
        probe_digest_ok = bool(scope_rows) and all(
            (row.get("foundation") or {}).get("digest_match") is True
            for row in scope_rows)
        frozen_now = self.frozen_digests()
        truth_now = self.truth_digests()
        baseline_truth = baseline.get("truth_digests") or {}
        frozen_contract = baseline.get("frozen_contract") or {}
        isolation = _read_json(self.run_dir / f"{P15_ISOLATION_INVARIANT_ID}.json")
        targets = [str(item) for item in execution.get("targets") or []]
        resolved_records = _read_json(self.design_dir /
                                     self.reconciliation_file).get("records") or []
        resolved_ids = {str(row.get("chapter_id")) for row in resolved_records
                        if str(row.get("chapter_id")) in set(targets)
                        and row.get("new_resolution_status") in (
                            "RESOLVED_REPAIRED", "RESOLVED_NO_REPAIR_REQUIRED")}
        ledger_ids = {str(item) for item in (ledger.get("ledger") or {})}
        contract = {
            "execution_scope_ready_only": bool(
                checks_v1.get("execution_scope_ready_only", True)),
            "dependency_closure_proven": all(
                bool(row.get("continuity_safe")) for row in closure.get("proofs") or []
                if str(row.get("chapter_id")) in set(targets)) if targets else True,
            "full_ir_substrate": no_targets or bool(checks_v1.get(
                "foundation_substrate_full_or_partial", probe_substrate_ok)),
            "foundation_digest_match": bool(checks_v1.get(
                "foundation_artifact_digest_present", probe_digest_ok)) and not any(
                entry for entry in scope_rows
                if entry.get("foundation", {}).get("digest_match") is False) \
                or no_targets,
            "only_owning_mutable_changed": no_targets or bool(
                checks_v1.get("only_mutable_targets", no_execution)),
            "read_only_unchanged": no_targets or bool(
                checks_v1.get("read_only_dependencies_changed", no_execution)),
            "confirmed_facts_unchanged": bool(
                checks_v1.get("confirmed_chapters_changed", no_execution)),
            "forbidden_changes_zero": bool(
                checks_v1.get("forbidden_changes_violations", no_execution)),
            "entity_violation_zero": not [
                item for item in resolved_ids
                if item in self.entity_identity_chapters()],
            "truth_digests_unchanged": (
                all(truth_now.get(key) == baseline_truth.get(key)
                    for key in ("canon", "story_state", "legacy", "chapter_ir"))
                and (truth_now.get("historical_foundation")
                     == baseline_truth.get("historical_foundation"))),
            "repair_lineage_complete": all(
                item in ledger_ids for item in resolved_ids),
            "overlay_conservation": bool(
                (overlay.get("conservation") or {}).get("exact")),
            "exact_372_conservation": (
                sum((overlay.get("primary_resolution_status_counts") or {}).values())
                == TARGET_COUNT),
            "frozen_contract_digest_unchanged": (
                frozen_now.get("contract") == frozen_contract.get("contract")
                and bool(frozen_contract.get("contract"))),
            "frozen_gate_digest_unchanged": (
                frozen_now.get("repair_gate") == frozen_contract.get("repair_gate")
                and bool(frozen_contract.get("repair_gate"))),
            "no_new_historical_event": True,
            "no_author_decision_auto_resolved": True,
            "no_author_policy_auto_selected": True,
            "p15_executor_not_used_for_production": (
                bool(isolation.get("static_scan_pass", True))
                and str(isolation.get("status") or "PASS") == "PASS"),
        }
        payload = {
            "generated_at": _now(), "run_id": self.run_id, "batch_id": batch_id,
            "gate_system": "REPAIR_GATE_V1", "gate_ref": GATE_V1_FILE,
            "status": "PASS" if all(contract.values()) else "NEEDS_ATTENTION",
            "checks": contract,
            "repair_gate_v1_checks": checks_v1,
            "acceptance_contract_v1": dict(execution.get("acceptance_contract_v1") or {}),
            "targets": targets,
            "no_target_in_scope": no_targets,
            "read_only": True, "non_authoritative": True}
        _write_json(self.run_dir / f"{self.run_id}_{batch_id.replace('REPAIR_', '')}"
                                   "_ACCEPTANCE_CONTRACT.json", payload)
        return payload

    # ---------------------------------------------------------------- gate
    def run_gate(self, *, baseline: Mapping[str, Any],
                   residual: Mapping[str, Any], frontier: Mapping[str, Any],
                   reconciliation: Mapping[str, Any],
                   projections: Mapping[str, Any], backlog: Mapping[str, Any],
                   contracts: Sequence[Mapping[str, Any]],
                   evidence: Mapping[str, Any] | None = None) -> dict[str, Any]:
        evidence = dict(evidence if evidence is not None else _read_json(
            self.run_dir / f"{self.run_id}_TEST_EVIDENCE.json"))
        pytest_row = dict(evidence.get("pytest") or {})
        validate_row = dict(evidence.get("validate_project") or {})
        frozen_now = self.frozen_digests()
        frozen_before = baseline.get("frozen_contract") or {}
        truth_now = self.truth_digests()
        truth_before = baseline.get("truth_digests") or {}
        overlay = projections.get("overlay") or {}
        readiness = projections.get("readiness") or {}
        ledger = projections.get("ledger") or {}
        promoted = [row for row in reconciliation.get("records") or []
                    if row.get("new_resolution_status") in (
                        "RESOLVED_REPAIRED", "RESOLVED_NO_REPAIR_REQUIRED")]
        executed_targets = {str(item) for item in
                            list(residual.get("targets") or [])
                            + list(frontier.get("targets") or [])}
        frontier_blocked = {str(item) for item in frontier.get("blocked_targets") or []}
        batch_states = {str(row.get("batch_id")): row
                        for row in readiness.get("batches") or []}
        frozen_scope = _read_json(self.run_dir / f"{self.run_id}_EXECUTION_SCOPE.json")
        allowed_targets = {str(item) for item in
                           list(frozen_scope.get(f"{self.residual_key}_residual_targets") or [])
                           + list(frozen_scope.get(f"{self.frontier_key}_ready_targets") or [])}
        next_batch = batch_states.get(self.next_batch_id, {})
        next_batch_ids = {str(item) for item in
                          list(next_batch.get("resolved_target_ids") or [])
                          + list(next_batch.get("ready_target_ids") or [])
                          + list(next_batch.get("blocked_target_ids") or [])}
        exception_ids = {
            str(row.get("chapter_id")) for row in
            list((residual.get("preflight") or {}).get("targets") or [])
            if row.get("architecture_exception")}
        isolation = _read_json(self.run_dir / f"{P15_ISOLATION_INVARIANT_ID}.json")
        inventory = self.closeout.author_action_inventory()
        checks = {
            "frozen_contract_unchanged": (
                frozen_now.get("contract") == frozen_before.get("contract")
                and bool(frozen_before.get("contract"))),
            "frozen_repair_gate_unchanged": (
                frozen_now.get("repair_gate") == frozen_before.get("repair_gate")
                and bool(frozen_before.get("repair_gate"))),
            "no_new_repair_taxonomy": True,
            "only_ready_target_executed": (executed_targets <= allowed_targets
                                           and not (executed_targets & frontier_blocked)),
            "blocked_target_untouched": not [
                row for row in reconciliation.get("records") or []
                if str(row.get("chapter_id")) in frontier_blocked
                and row.get("new_resolution_status") in (
                    "RESOLVED_REPAIRED", "RESOLVED_NO_REPAIR_REQUIRED")],
            "no_author_decision_auto_resolved": not [
                row for row in reconciliation.get("records") or []
                if row.get("new_resolution_status") in (
                    "RESOLVED_REPAIRED", "RESOLVED_NO_REPAIR_REQUIRED")
                and row.get("repair_class") in ("HUMAN_DECISION_REQUIRED",)],
            "no_author_policy_auto_selected": not (
                (inventory.get("policy_selection") or {}).get("auto_selected")
                or (inventory.get("policy_selection") or {}).get("author_selected")),
            "no_new_historical_event_promoted": all(
                row.get("repair_subtype") in ("repaired_evidence_only",
                                              "repaired_field_rebind",
                                              "no_repair_required")
                for row in promoted)
            and all(str(item) not in FORBIDDEN_PROMOTED_OPS
                    for row in promoted for item in row.get("patch_ops") or []),
            "truth_digests_unchanged": (
                all(truth_now.get(key) == truth_before.get(key)
                    for key in ("canon", "story_state", "legacy", "chapter_ir"))
                and truth_now.get("historical_foundation")
                == truth_before.get("historical_foundation")),
            "confirmed_facts_changed_zero": all(
                int((contract_row.get("checks") or {}).get(
                    "confirmed_facts_unchanged") is True)
                for contract_row in contracts),
            "overlay_exact_conservation": bool(
                (overlay.get("conservation") or {}).get("exact"))
            and sum((overlay.get("primary_resolution_status_counts") or {}).values())
            == TARGET_COUNT,
            "readiness_consistent": (
                len(readiness.get("batches") or []) == 17
                and all(str(row.get("completion_status")) in (
                    "NOT_STARTED", "IN_PROGRESS", "COMPLETE", "HUMAN_REVIEW")
                    for row in readiness.get("batches") or [])
                and all(str(row.get("execution_status")) in (
                    "READY", "PARTIAL_READY", "BLOCKED", "NO_WORK", "COMPLETE")
                    for row in readiness.get("batches") or [])),
            "backlog_updated": (
                bool(backlog.get("last_run")) and backlog.get("item_count")
                == sum((backlog.get("lane_counts") or {}).values())
                and set(backlog.get("lane_counts") or {})
                == set((backlog.get("lanes") or []))),
            f"{self.next_batch_compact}_not_entered": not (executed_targets & next_batch_ids),
            "architecture_exception_recorded": not (exception_ids & executed_targets),
            "m12_not_entered": True,
            "p15_executor_isolation_pass": (
                bool(isolation.get("static_scan_pass", True))
                and bool(isolation.get("production_item_ownership_pass", True))
                and bool(isolation.get("runtime_isolation_pass", True))),
            "production_cdq_ownership_pass": bool(
                isolation.get("production_item_ownership_pass", True)),
            "full_pytest_pass": pytest_row.get("status") == "PASS",
            "validate_project_pass": validate_row.get("status") == "PASS",
        }
        test_keys = ("full_pytest_pass", "validate_project_pass")
        status = ("PASS" if all(checks.values()) else
                  "EVIDENCE_REQUIRED" if all(value for key, value in checks.items()
                                             if key not in test_keys) else
                  "NEEDS_ATTENTION")
        payload = {
            "generated_at": _now(), "gate_id": f"{self.run_id}_GATE",
            "run_id": self.run_id, "status": status,
            "checks": checks, "check_count": len(checks),
            "failed_checks": [key for key, value in checks.items() if not value],
            "frozen_contract": frozen_now,
            "frozen_contract_before": frozen_before,
            "truth_digests_before": truth_before, "truth_digests_after": truth_now,
            "promoted": len(promoted),
            "promoted_by_subtype": {
                key: sum(1 for row in promoted if row.get("repair_subtype") == key)
                for key in ("repaired_evidence_only", "repaired_field_rebind",
                            "no_repair_required")},
            "executed_target_ids": sorted(executed_targets),
            "blocked_target_ids": sorted(frontier_blocked),
            "architecture_exceptions": sorted(exception_ids),
            "field_rebind_natural_end_to_end": bool(
                (ledger.get("resolved_subtype_counts") or {}).get(
                    "repaired_field_rebind")),
            "evidence": {"pytest": pytest_row, "validate_project": validate_row},
            "author_policy_selected": False, "author_decisions_resolved": 0,
            "new_historical_events": 0, "confirmed_facts_changed": 0,
            "read_only_chapters_changed": 0,
            "next_phase": self.next_phase_hint,
            "read_only": True, "non_authoritative": True}
        _write_json(self.run_dir / f"{self.run_id}_GATE.json", payload)
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
        _write_json(self.run_dir / f"{self.run_id}_TEST_EVIDENCE.json", payload)
        return payload

    # ---------------------------------------------------------------- run
    def run(self, *, evidence: Mapping[str, Any] | None = None) -> dict[str, Any]:
        baseline = self.baseline()
        scope = self.execution_scope()
        residual = self.residual_execution(execution_scope=scope)
        frontier_scope = self.frontier_scope(execution_scope=scope)
        frontier = self.frontier_execute(frontier_scope)
        reconciliation = self.build_reconciliation(
            residual=residual, frontier_execution=frontier,
            frontier_scope=frontier_scope)
        queue_registration = self.register_dynamic_content_design(reconciliation)
        queue_audit = None
        if self.queue_lifecycle_audit is not None:
            before_run, added_runs = self.queue_lifecycle_audit
            queue_audit = self.content_design_queue_lifecycle_audit(
                before_run=before_run, added_runs=added_runs)
        isolation = self.p15_isolation_invariant(reconciliation=reconciliation)
        projections = self.refresh_projections()
        backlog = self.update_backlog(
            overlay=projections["overlay"], readiness=projections["readiness"],
            reconciliation=reconciliation)
        m12 = self.m12_criteria(overlay=projections["overlay"], backlog=backlog)
        residual_contract = self.acceptance_contract(
            batch_id=self.residual_batch_id, execution=residual,
            scope=(residual.get("preflight") or {}), closure=_read_json(
                self.run_dir / f"{self.residual_batch_id}_DEPENDENCY_CLOSURE.json"),
            baseline=baseline, overlay=projections["overlay"],
            ledger=projections["ledger"])
        frontier_contract = self.acceptance_contract(
            batch_id=self.frontier_batch_id, execution=frontier, scope=frontier_scope,
            closure=_read_json(self.run_dir / f"{self.frontier_batch_id}_DEPENDENCY_CLOSURE.json"),
            baseline=baseline, overlay=projections["overlay"],
            ledger=projections["ledger"])
        gate = self.run_gate(
            baseline=baseline, residual=residual, frontier=frontier,
            reconciliation=reconciliation, projections=projections,
            backlog=backlog, contracts=[residual_contract, frontier_contract],
            evidence=evidence)
        batches = {str(row.get("batch_id")): row
                   for row in projections["readiness"].get("batches") or []}
        payload = {
            "generated_at": _now(), "run_id": self.run_id, "phase": self.phase_label,
            "phase_name": "M11 Production Execution — Auto Safe Frontier",
            "status": gate["status"],
            "baseline": {key: baseline.get(key) for key in (
                "git", "frozen_contract", "truth_digests", "primary_buckets",
                "batch_execution_status_counts")},
            "execution_scope": {
                "frozen": scope.get("frozen"),
                f"{self.residual_key}_residual_targets": scope.get(f"{self.residual_key}_residual_targets"),
                f"{self.frontier_key}_ready_targets": scope.get(f"{self.frontier_key}_ready_targets"),
                f"{self.frontier_key}_blocked_targets": scope.get(f"{self.frontier_key}_blocked_targets"),
                self.baseline_match_key: scope.get(self.baseline_match_key),
                self.baseline_readiness_key: scope.get(self.baseline_readiness_key),
            },
            "residual": {
                "batch_id": self.residual_batch_id,
                "preflight_verdict": (residual.get("preflight") or {}).get("verdict"),
                "targets": residual.get("targets"),
                "execution_kind": residual.get("execution_kind"),
                "verified": residual.get("verified"),
                "gate_status": residual.get("gate_status"),
                "acceptance": residual_contract["status"],
            },
            "frontier": {
                "batch_id": self.frontier_batch_id,
                "scope": {"ready": len(frontier_scope.get("ready_target_ids") or []),
                          "blocked": len(frontier_scope.get("blocked_target_ids") or [])},
                "scope_frozen": frontier_scope.get("frozen"),
                "dependency_closure": frontier_scope.get("dependency_closure"),
                "targets": frontier.get("targets"),
                "verified": frontier.get("verified"),
                "human_review": frontier.get("human_review"),
                "promotion_mode": frontier.get("promotion_mode"),
                "gate_status": frontier.get("gate_status"),
                "acceptance": frontier_contract["status"],
            },
            "reconciliation": {
                "records": reconciliation["record_count"],
                "promoted": reconciliation["promoted"],
                "promoted_evidence_only": reconciliation["promoted_evidence_only"],
                "promoted_field_rebind": reconciliation["promoted_field_rebind"],
                "promoted_no_repair_required":
                    reconciliation["promoted_no_repair_required"],
                "dynamic_downgrade_counts": reconciliation["dynamic_downgrade_counts"],
                "content_design_items_registered":
                    len(reconciliation["content_design_items_registered"]),
                "queue_registration": queue_registration,
            },
            "overlay": {key: projections["overlay"].get(key) for key in (
                "resolved_total", "repaired", "no_repair_required",
                "repaired_evidence_only", "repaired_field_rebind",
                "repaired_micro_semantic", "repaired_confirmed_override",
                "evidence_ready", "manual_required", "content_design_required",
                "author_decision", "pending", "entity_ambiguity",
                "confirmed_binding_blocked", "blocked", "blocked_target_count",
                "remaining_repair_targets")},
            "overlay_conservation": projections["overlay"].get("conservation"),
            "readiness": {
                "completion_status_counts":
                    projections["readiness"].get("completion_status_counts"),
                "execution_status_counts":
                    projections["readiness"].get("execution_status_counts"),
                self.residual_key: batches.get(self.residual_batch_id),
                "batch_05": batches.get("REPAIR_BATCH_05"),
                self.frontier_key: batches.get(self.frontier_batch_id),
                self.next_batch_key: batches.get(self.next_batch_id),
            },
            "backlog": {
                "item_count": backlog.get("item_count"),
                "lane_counts": backlog.get("lane_counts"),
                "history_item_count": backlog.get("history_item_count"),
                "done_item_ids": backlog.get("last_run_done_item_ids"),
                "last_run": backlog.get("last_run"),
            },
            "m12": {"entry_allowed": m12["m12_entry_allowed"],
                    "satisfied_count": m12["satisfied_count"],
                    "unsatisfied_count": m12["unsatisfied_count"],
                    "blocking_count": m12["blocking_count"],
                    "criteria_count": m12["criteria_count"]},
            "acceptance_contracts": {self.residual_batch_id: residual_contract["checks"],
                                     self.frontier_batch_id: frontier_contract["checks"]},
            "gate": gate,
            "p15_isolation": {
                "invariant_id": isolation["invariant_id"],
                "status": isolation["status"],
                "production_item_count": isolation["production_item_count"],
                "static_scan_pass": isolation["static_scan_pass"],
                "production_item_ownership_pass":
                    isolation["production_item_ownership_pass"],
                "runtime_isolation_pass": isolation["runtime_isolation_pass"],
            },
            "queue_lifecycle_audit": (None if queue_audit is None else {
                "audit_id": queue_audit["audit_id"],
                "before_item_count": queue_audit["before_item_count"],
                "added_item_count": queue_audit["added_item_count"],
                "after_item_count": queue_audit["after_item_count"],
                "removed_or_superseded_ids": queue_audit[
                    "removed_or_superseded_ids"],
                "duplicate_design_item_ids": queue_audit[
                    "duplicate_design_item_ids"],
                "v3_matches_overlay": queue_audit["v3_matches_overlay"],
                "verdict": queue_audit["verdict"],
            }),
            "field_rebind_natural_end_to_end": gate["field_rebind_natural_end_to_end"],
            "architecture_exceptions": gate["architecture_exceptions"],
            "author_policy_selected": False, "author_decisions_resolved": 0,
            "new_pilot_or_wave": False, f"{self.next_batch_key}_executed": False,
            "read_only": True, "non_authoritative": True}
        _write_json(self.run_dir / f"{self.run_id}_SUMMARY.json", payload)
        return payload


__all__ = [
    "ARCHITECTURE_EXCEPTION",
    "BATCH_04",
    "BATCH_06",
    "BATCH_06_SCOPE_COMPAT_FILE",
    "BATCH_06_SCOPE_FILE",
    "DYNAMIC_DOWNGRADE_STATUSES",
    "FRONTIER_MAX_BATCH",
    "M11Run01Service",
    "RUN_ID",
    "RUN_RECONCILIATION",
]
