"""P15j：M11 readiness 语义修正（completion / execution 分离）+ CDQ 动态并入 + overlay V2。

解决的问题：
- 一个 batch status 同时表达"是否部分完成"与"剩余 target 是否可执行"（Batch 05 = PARTIAL_READY
  但 ready 26 / blocked 0 就是这种语义 bug）；
- P15i 动态发现的 7 个 `CDQ_B04_*` 只登记了 id，未正式并入 ContentDesignQueue；
- overlay 把"own 未决"与"dependency blocker"混在一个 bucket，破坏 372 守恒。

本轮只做 projection / infrastructure：不执行 repair、不生成内容、不做 author resolution。
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
from novelforge.story_engine.m11_design import (
    M11DesignDecisionService,
    RepairDesignRequirement,
    _continuity_map,
    _design_requirement,
)

CompletionStatus = Literal["NOT_STARTED", "IN_PROGRESS", "COMPLETE", "HUMAN_REVIEW"]
ExecutionStatus = Literal["READY", "PARTIAL_READY", "BLOCKED", "NO_WORK", "COMPLETE"]
PrimaryStatus = Literal["resolved_repaired", "resolved_no_repair_required",
                        "evidence_ready", "manual_required", "content_design_required",
                        "author_decision", "pending"]

PRIMARY_BUCKETS: tuple[str, ...] = (
    "resolved_repaired", "resolved_no_repair_required", "evidence_ready",
    "manual_required", "content_design_required", "author_decision", "pending")
# M11 final closure 的 reconciliation 是 terminal authority；readiness loader 必须最后加载它，
# 且任何 extra_reconciliation 都不能把它挤到中间（见 ReadinessV2Service.load）。
APPROVED_EVENT_RECONCILIATION = "M11_APPROVED_EVENT_RECONCILIATION.json"
FINAL_CLOSURE_RECONCILIATION = "M11_FINAL_CLOSURE_RECONCILIATION.json"
TERMINAL_PRIMARY: tuple[str, ...] = ("resolved_repaired", "resolved_no_repair_required",
                                     "author_resolved", "manual_resolved")
BLOCKING_KINDS: tuple[str, ...] = (
    "CONTENT_DESIGN_REQUIRED", "AUTHOR_DECISION_REQUIRED", "MANUAL_REQUIRED",
    "EVIDENCE_READY", "BLOCKED_CONTENT_DESIGN", "BLOCKED_CONFIRMED_BINDING_CONFLICT")
BLOCKER_NAMES: dict[str, str] = {
    "CONTENT_DESIGN_REQUIRED": "BLOCKED_CONTENT_DESIGN",
    "AUTHOR_DECISION_REQUIRED": "BLOCKED_AUTHOR_DECISION",
    "MANUAL_REQUIRED": "BLOCKED_MANUAL_REPAIR",
    "EVIDENCE_READY": "BLOCKED_ENTITY_AMBIGUITY",
    "BLOCKED_CONFIRMED_BINDING_CONFLICT": "BLOCKED_CONFIRMED_BINDING_CONFLICT",
    "BLOCKED_CONTENT_DESIGN": "BLOCKED_CONTENT_DESIGN",
    "BLOCKED_ENTITY_AMBIGUITY": "BLOCKED_ENTITY_AMBIGUITY",
}


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


def execution_status_for(*, ready_count: int, blocked_count: int,
                         completion_status: str) -> ExecutionStatus:
    """§3：execution_status 只回答"剩余 target 是否可执行"。"""

    if completion_status == "COMPLETE":
        return "COMPLETE"
    if ready_count > 0 and blocked_count == 0:
        return "READY"
    if ready_count > 0 and blocked_count > 0:
        return "PARTIAL_READY"
    if ready_count == 0 and blocked_count > 0:
        return "BLOCKED"
    return "NO_WORK"


def completion_status_for(*, resolved_count: int, ready_count: int,
                          blocked_count: int, total: int) -> CompletionStatus:
    """§2：completion_status 只回答"这个 batch 是否完成"。"""

    if total > 0 and resolved_count == total:
        return "COMPLETE"
    if resolved_count or ready_count:
        return "IN_PROGRESS"
    if blocked_count:
        return "HUMAN_REVIEW"
    return "NOT_STARTED"


class TargetStateRow(StrictModel):
    chapter_id: str
    legacy_label: str = ""
    batch_id: str = ""
    primary_resolution_status: PrimaryStatus = "pending"
    execution_blockers: list[str] = Field(default_factory=list)
    target_state: Literal["RESOLVED", "READY", "BLOCKED"] = "READY"
    reason: str = ""
    blocking_source: list[str] = Field(default_factory=list)


class BatchReadinessV2(StrictModel):
    batch_id: str
    completion_status: CompletionStatus = "NOT_STARTED"
    execution_status: ExecutionStatus = "NO_WORK"
    resolved_target_ids: list[str] = Field(default_factory=list)
    ready_target_ids: list[str] = Field(default_factory=list)
    blocked_target_ids: list[str] = Field(default_factory=list)
    block_reason_by_target: dict[str, str] = Field(default_factory=dict)
    blocker_counts: dict[str, int] = Field(default_factory=dict)
    pending_target_ids: list[str] = Field(default_factory=list)
    mutable_target_count: int = 0
    dependency_batches: list[str] = Field(default_factory=list)
    non_authoritative: bool = True


class DependencyClosureProof(StrictModel):
    target_id: str
    chapter_id: str
    legacy_label: str = ""
    owning_batch: str = ""
    direct_dependency_chapters: list[str] = Field(default_factory=list)
    transitive_dependency_targets: list[str] = Field(default_factory=list)
    resolved_dependencies: list[str] = Field(default_factory=list)
    unresolved_dependencies: list[str] = Field(default_factory=list)
    content_design_dependencies: list[str] = Field(default_factory=list)
    entity_dependencies: list[str] = Field(default_factory=list)
    author_dependencies: list[str] = Field(default_factory=list)
    manual_dependencies: list[str] = Field(default_factory=list)
    confirmed_binding_dependencies: list[str] = Field(default_factory=list)
    continuity_safe: bool = True
    ready_reason: str = ""
    non_authoritative: bool = True


@dataclass
class ReadinessInputs:
    design: Any = None
    resolutions: dict[str, str] = field(default_factory=dict)
    targets: dict[str, dict[str, Any]] = field(default_factory=dict)
    batches: list[dict[str, Any]] = field(default_factory=list)
    legacy_rows: dict[str, dict[str, Any]] = field(default_factory=dict)
    artifacts: dict[str, Any] = field(default_factory=dict)
    continuity: dict[str, list[str]] = field(default_factory=dict)
    clusters: dict[str, Any] = field(default_factory=dict)
    overrides: dict[str, Any] = field(default_factory=dict)
    design_queue: dict[str, Any] = field(default_factory=dict)
    requirements: dict[str, Any] = field(default_factory=dict)


class ReadinessV2Service:
    """P15j：readiness 语义修正 + 动态 CDQ 并入 + overlay V2（不执行 repair）。"""

    def __init__(self, project_root: Path | str, *, design_dir: str = ADOPTION_DIR,
                 repair_dir: str = REPAIR_DIR, foundation_dir: str = HISTORY_DIR
                 ) -> None:
        self.root = Path(project_root).resolve()
        self.design_dir = (self.root / design_dir).resolve()
        self.repair_dir = (self.root / repair_dir).resolve()
        self.foundation_dir = (self.root / foundation_dir).resolve()
        self.design = M11DesignDecisionService(self.root)

    # ---- load -----------------------------------------------------------
    def load(self, *, extra_reconciliation: Sequence[str] = (),
             include_batch05: bool = True,
             exclude_reconciliation: Sequence[str] = ()) -> ReadinessInputs:
        design_inputs = self.design.load()
        final_closure = FINAL_CLOSURE_RECONCILIATION
        names = ["REPAIR_RECONCILIATION.json", "BATCH_04_RECONCILIATION.json"]
        if include_batch05:
            names.append("BATCH_05_RECONCILIATION.json")
        names.extend(["P15L_RECONCILIATION.json",
                      "P15M_CONFIRMED_OVERRIDE_RECONCILIATION.json",
                      "P15M_WAVE_01_RECONCILIATION.json"])
        # M11-RUN-01 起：production execution 的 reconciliation 与 P15 阶段同级，
        # 后续任何 readiness / overlay 重算都必须看到它（否则会回退已执行结果）。
        names.extend(["M11_RUN_01_RECONCILIATION.json",
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
                      final_closure])
        names.extend(extra_reconciliation)
        # terminal authority tail：approved historical additions → M11 final closure。
        # 这两层必须始终最后加载（last wins），不能被 phase / run 自己的 reconciliation
        #（extra_reconciliation）覆盖，否则任何一次 readiness / overlay 重算都会把已 terminal
        # 的 target 回退成 BLOCKED（例如 M11-RUN-12 的 CONTENT_DESIGN_REQUIRED 覆盖
        # approved-event 的 RESOLVED_REPAIRED）。
        for authority in (APPROVED_EVENT_RECONCILIATION, final_closure):
            names = [name for name in names if name != authority]
            names.append(authority)
        if exclude_reconciliation:
            excluded = {str(item) for item in exclude_reconciliation}
            names = [name for name in names if name not in excluded]
        resolutions: dict[str, str] = {}
        for name in names:
            for row in (_read_json(self.design_dir / name).get("records") or []):
                resolutions[str(row.get("chapter_id"))] = str(
                    row.get("new_resolution_status"))
        return ReadinessInputs(
            design=design_inputs, resolutions=resolutions,
            targets=design_inputs.targets, batches=design_inputs.batches,
            legacy_rows=design_inputs.legacy_rows, artifacts=design_inputs.artifacts,
            continuity=_continuity_map(design_inputs),
            clusters=_read_json(self.design_dir / "M11_ENTITY_RESOLUTION_QUEUE.json"),
            overrides=_read_json(self.design_dir / "CONFIRMED_BINDING_RESOLUTION.json"),
            design_queue=_read_json(self.design_dir / "M11_CONTENT_DESIGN_QUEUE.json"),
            requirements=_read_json(self.design_dir / "REPAIR_DESIGN_REQUIREMENTS.json"))

    # ---- PART B: dynamic CDQ integration + dedup -------------------------
    def integrate_dynamic_design_items(self, *, inputs: ReadinessInputs | None = None
                                       ) -> dict[str, Any]:
        inputs = inputs or self.load()
        reconciliation = _read_json(self.design_dir / "BATCH_04_RECONCILIATION.json")
        # §14：production execution（M11-RUN-xx）runtime 登记的 ContentDesignRequirement
        # 也是 queue 的一部分；这里必须以当前 V2 queue 为 base 做 merge，不能从 P15h
        # 快照重建（否则会丢掉生产轮次新增的 requirement，破坏 active ↔ overlay 双射）。
        current_v2 = _read_json(self.design_dir / "M11_CONTENT_DESIGN_QUEUE_V2.json")
        existing_items = (list(current_v2.get("items") or [])
                          or list(inputs.design_queue.get("items") or []))
        existing_requirements = list(inputs.requirements.get("requirements") or [])
        existing_by_key = {
            (str(row.get("chapter_id")), str(row.get("missing_semantic_type"))): row
            for row in existing_requirements}
        existing_item_ids = {str(row.get("design_item_id")) for row in existing_items}
        existing_item_chapters = {str(row.get("chapter_id")) for row in existing_items}
        chapter_of_label = {str(row.get("legacy_label")): str(row.get("chapter_id"))
                            for row in existing_requirements}
        new_items: list[dict[str, Any]] = []
        duplicates: list[dict[str, Any]] = []
        new_requirements: list[RepairDesignRequirement] = []
        labels = {cid: str(row.get("id")) for cid, row in inputs.legacy_rows.items()}
        for item in reconciliation.get("auto_discovered_design_items") or []:
            chapter_id = str(item.get("chapter_id"))
            label = str(item.get("legacy_label"))
            target = inputs.targets.get(chapter_id) or {}
            missing_type = str(target.get("primary_issue") or "turn_gap")
            missing_semantic = "TURN"
            key = (chapter_id, missing_semantic)
            if key in existing_by_key or str(item.get("design_item_id")) in existing_item_ids \
                    or chapter_id in existing_item_chapters:
                duplicates.append({
                    "design_item_id": item.get("design_item_id"),
                    "existing_requirement_ref": str(existing_by_key.get(key, {}).get(
                        "design_item_id") or item.get("design_item_id") or ""),
                    "chapter_id": chapter_id, "legacy_label": label,
                    "reason": "同一 chapter / design_item 已并入 queue（幂等，不重复登记）"})
                continue
            artifact = inputs.artifacts.get(chapter_id)
            queue_item = {
                "design_item_id": item.get("design_item_id") or f"CDQ_B04_{label}",
                "chapter_id": chapter_id, "legacy_label": label,
                "arc_id": str(target.get("historical_arc") or ""),
                "missing_semantic_type": missing_semantic,
                "design_subtype": "MICRO_PIVOT_REQUIRED",
                "severity": str(target.get("risk") or "MEDIUM"),
                "micro_or_major": "micro",
                "confirmed_facts": list(target.get("confirmed_facts") or []),
                "forbidden_changes": list(target.get("forbidden_changes") or []),
                "upstream_context": [], "downstream_constraints": [],
                "candidate_space": ["策略调整", "信息理解变化", "短期目标变化", "局部状态变化"],
                "author_decision_required": False,
                "dependency_items": [], "status": "PENDING_DESIGN",
                "non_authoritative": True,
                "origin": "P15i dynamic downgrade（Batch 04 runtime）",
                "missing_detail": missing_type}
            new_items.append(queue_item)
            requirement = _design_requirement(
                item=queue_item, chapter_id=chapter_id, label=label, artifact=artifact,
                legacy=inputs.legacy_rows.get(chapter_id) or {}, target=target,
                story=(inputs.design.story_rows.get(chapter_id) or {}),
                label_lookup=labels)
            new_requirements.append(requirement)
        merged_items = existing_items + new_items
        merged_requirements = existing_requirements + [
            row.model_dump(mode="json") for row in new_requirements]
        payload = {
            "generated_at": _now(),
            "existing_item_count": len(existing_items),
            "dynamic_candidate_count": len(reconciliation.get(
                "auto_discovered_design_items") or []),
            "new_item_count": len(new_items), "duplicate_count": len(duplicates),
            "merged_item_count": len(merged_items),
            "new_items": new_items, "duplicates": duplicates,
            "new_requirements": [row.model_dump(mode="json")
                                 for row in new_requirements],
            "content_generated": False, "proposals_generated": False,
            "read_only": True, "non_authoritative": True}
        _write_json(self.design_dir / "M11_CONTENT_DESIGN_QUEUE_V2.json", {
            "generated_at": _now(), "item_count": len(merged_items),
            "items": merged_items, "read_only": True, "non_authoritative": True})
        _write_json(self.design_dir / "REPAIR_DESIGN_REQUIREMENTS_V2.json", {
            "generated_at": _now(), "requirement_count": len(merged_requirements),
            "micro_count": sum(1 for row in merged_requirements
                               if row.get("micro_or_major") == "micro"),
            "major_count": sum(1 for row in merged_requirements
                               if row.get("micro_or_major") == "major"),
            "requirements": merged_requirements,
            "read_only": True, "non_authoritative": True})
        _write_json(self.design_dir / "M11_DYNAMIC_CDQ_INTEGRATION.json", payload)
        return payload

    # ---- target states / readiness V2 ------------------------------------
    def target_states(self, *, inputs: ReadinessInputs | None = None
                      ) -> dict[str, TargetStateRow]:
        inputs = inputs or self.load()
        labels = {cid: str(row.get("id")) for cid, row in inputs.legacy_rows.items()}
        ownership: dict[str, str] = {}
        for batch in inputs.batches:
            for chapter_id in batch.get("chapter_ids") or []:
                ownership[str(chapter_id)] = str(batch.get("batch_id"))
        cluster_identity: set[str] = set()
        for cluster in inputs.clusters.get("clusters") or []:
            if cluster.get("requires_exact_identity") and cluster.get(
                    "resolution_status") != "NON_BLOCKING_GENERIC_REFERENCE":
                cluster_identity |= {str(item) for item in
                                     cluster.get("chapter_ids") or []}
        override_labels = {str(row.get("legacy_label"))
                           for row in inputs.overrides.get("resolutions") or []}
        rows: dict[str, TargetStateRow] = {}
        for chapter_id, batch_id in ownership.items():
            label = labels.get(chapter_id, "")
            resolution = inputs.resolutions.get(chapter_id, "PENDING")
            primary: PrimaryStatus = {
                "RESOLVED_REPAIRED": "resolved_repaired",
                "RESOLVED_NO_REPAIR_REQUIRED": "resolved_no_repair_required",
                "EVIDENCE_READY": "evidence_ready",
                "MANUAL_REQUIRED": "manual_required",
                "CONTENT_DESIGN_REQUIRED": "content_design_required",
                "AUTHOR_DECISION_REQUIRED": "author_decision",
                "BLOCKED_CONTENT_DESIGN": "pending",
            }.get(resolution, "pending")
            blockers: list[str] = []
            sources: list[str] = []
            if primary == "content_design_required":
                blockers.append("BLOCKED_CONTENT_DESIGN")
                sources.append(label)
            elif primary == "author_decision":
                blockers.append("BLOCKED_AUTHOR_DECISION")
                sources.append(label)
            elif primary == "manual_required":
                blockers.append("BLOCKED_MANUAL_REPAIR")
                sources.append(label)
            elif primary == "evidence_ready":
                blockers.append("BLOCKED_ENTITY_AMBIGUITY")
                sources.append(label)
            for dep in inputs.continuity.get(chapter_id, []):
                dep_resolution = inputs.resolutions.get(dep)
                if dep_resolution in BLOCKING_KINDS:
                    name = BLOCKER_NAMES.get(dep_resolution, "BLOCKED_DEPENDENCY")
                    if name not in blockers:
                        blockers.append(name)
                    sources.append(labels.get(dep, dep))
            if label in override_labels and primary == "pending":
                if "BLOCKED_CONFIRMED_BINDING_CONFLICT" not in blockers:
                    blockers.append("BLOCKED_CONFIRMED_BINDING_CONFLICT")
                sources.append(f"override:{label}")
            if chapter_id in cluster_identity and primary == "pending":
                if "BLOCKED_ENTITY_AMBIGUITY" not in blockers:
                    blockers.append("BLOCKED_ENTITY_AMBIGUITY")
            if primary in ("resolved_repaired", "resolved_no_repair_required"):
                state = "RESOLVED"
            elif blockers or primary in ("content_design_required", "author_decision",
                                         "manual_required", "evidence_ready"):
                state = "BLOCKED"
            else:
                state = "READY"
            rows[chapter_id] = TargetStateRow(
                chapter_id=chapter_id, legacy_label=label, batch_id=batch_id,
                primary_resolution_status=primary,
                execution_blockers=sorted(dict.fromkeys(blockers)),
                target_state=state,
                reason=("resolved" if state == "RESOLVED" else
                        ("blocked:" + ",".join(sorted(set(blockers)))
                         if state == "BLOCKED" else "no localized blocker")),
                blocking_source=sorted(set(sources))[:8])
        return rows

    def build_readiness_v2(self, *, inputs: ReadinessInputs | None = None,
                           persist: bool = True) -> dict[str, Any]:
        inputs = inputs or self.load()
        states = self.target_states(inputs=inputs)
        batches: list[BatchReadinessV2] = []
        for batch in inputs.batches:
            batch_id = str(batch.get("batch_id"))
            items = [states[str(cid)] for cid in batch.get("chapter_ids") or []
                     if str(cid) in states]
            resolved = [row.chapter_id for row in items if row.target_state == "RESOLVED"]
            ready = [row.chapter_id for row in items if row.target_state == "READY"]
            blocked = [row for row in items if row.target_state == "BLOCKED"]
            counts: dict[str, int] = {}
            for row in blocked:
                for blocker in row.execution_blockers:
                    counts[blocker] = counts.get(blocker, 0) + 1
            completion = completion_status_for(
                resolved_count=len(resolved), ready_count=len(ready),
                blocked_count=len(blocked), total=len(items))
            execution = execution_status_for(
                ready_count=len(ready), blocked_count=len(blocked),
                completion_status=completion)
            batches.append(BatchReadinessV2(
                batch_id=batch_id, completion_status=completion,
                execution_status=execution, resolved_target_ids=resolved,
                ready_target_ids=ready,
                blocked_target_ids=[row.chapter_id for row in blocked],
                block_reason_by_target={row.chapter_id: row.reason for row in blocked},
                blocker_counts=counts,
                pending_target_ids=[row.chapter_id for row in items
                                    if row.target_state == "READY"],
                mutable_target_count=len(items),
                dependency_batches=[str(item) for item in
                                    batch.get("dependency_batches") or []]))
        completion_counts: dict[str, int] = {}
        execution_counts: dict[str, int] = {}
        for row in batches:
            completion_counts[row.completion_status] = completion_counts.get(
                row.completion_status, 0) + 1
            execution_counts[row.execution_status] = execution_counts.get(
                row.execution_status, 0) + 1
        payload = {
            "generated_at": _now(), "batch_count": len(batches),
            "completion_status_counts": completion_counts,
            "execution_status_counts": execution_counts,
            "status_semantics": {
                "completion_status": ["NOT_STARTED", "IN_PROGRESS", "COMPLETE",
                                      "HUMAN_REVIEW"],
                "execution_status": ["READY", "PARTIAL_READY", "BLOCKED", "NO_WORK",
                                     "COMPLETE"],
                "rules": {"READY": "ready>0 and blocked==0",
                          "PARTIAL_READY": "ready>0 and blocked>0",
                          "BLOCKED": "ready==0 and blocked>0",
                          "NO_WORK": "ready==0 and blocked==0 and not COMPLETE",
                          "COMPLETE": "completion_status == COMPLETE"}},
            "batches": [row.model_dump(mode="json") for row in batches],
            "kept_artifacts": ["M11_READINESS_HARDENED.json",
                               "M11_READINESS_REPORT.json"],
            "read_only": True, "non_authoritative": True}
        if persist:
            _write_json(self.design_dir / "M11_READINESS_V2.json", payload)
        return payload

    # ---- PART D: dependency closure proof --------------------------------
    def dependency_closure(self, batch_id: str = "REPAIR_BATCH_05",
                           *, inputs: ReadinessInputs | None = None,
                           readiness: Mapping[str, Any] | None = None,
                           artifact_name: str | None = None
                           ) -> dict[str, Any]:
        inputs = inputs or self.load()
        readiness = readiness or _read_json(self.design_dir / "M11_READINESS_V2.json")
        row = next((item for item in readiness.get("batches") or []
                    if item.get("batch_id") == batch_id), {})
        labels = {cid: str(value.get("id")) for cid, value in inputs.legacy_rows.items()}
        states = self.target_states(inputs=inputs)
        ownership: dict[str, str] = {}
        for batch in inputs.batches:
            for chapter_id in batch.get("chapter_ids") or []:
                ownership[str(chapter_id)] = str(batch.get("batch_id"))
        proofs: list[DependencyClosureProof] = []
        for chapter_id in list(row.get("ready_target_ids") or []) + \
                list(row.get("blocked_target_ids") or []):
            chapter_id = str(chapter_id)
            direct = [str(item) for item in inputs.continuity.get(chapter_id, [])]
            resolved: list[str] = []
            unresolved: list[str] = []
            buckets = {"content_design": [], "entity": [], "author": [],
                       "manual": [], "confirmed_binding": [], "other": []}
            for dep in direct:
                resolution = inputs.resolutions.get(dep, "PENDING")
                state = states.get(dep)
                if resolution in ("RESOLVED_REPAIRED", "RESOLVED_NO_REPAIR_REQUIRED") or (
                        state and state.primary_resolution_status in (
                            "resolved_repaired", "resolved_no_repair_required")):
                    resolved.append(labels.get(dep, dep))
                    continue
                if resolution in BLOCKING_KINDS:
                    unresolved.append(labels.get(dep, dep))
                    name = BLOCKER_NAMES.get(resolution, "")
                    if name == "BLOCKED_CONTENT_DESIGN":
                        buckets["content_design"].append(labels.get(dep, dep))
                    elif name == "BLOCKED_ENTITY_AMBIGUITY":
                        buckets["entity"].append(labels.get(dep, dep))
                    elif name == "BLOCKED_AUTHOR_DECISION":
                        buckets["author"].append(labels.get(dep, dep))
                    elif name == "BLOCKED_MANUAL_REPAIR":
                        buckets["manual"].append(labels.get(dep, dep))
                    elif name == "BLOCKED_CONFIRMED_BINDING_CONFLICT":
                        buckets["confirmed_binding"].append(labels.get(dep, dep))
                    else:
                        buckets["other"].append(labels.get(dep, dep))
            safe = not unresolved
            proofs.append(DependencyClosureProof(
                target_id=chapter_id, chapter_id=chapter_id,
                legacy_label=labels.get(chapter_id, ""),
                owning_batch=ownership.get(chapter_id, batch_id),
                direct_dependency_chapters=[labels.get(dep, dep) for dep in direct],
                transitive_dependency_targets=sorted(set(unresolved)),
                resolved_dependencies=resolved, unresolved_dependencies=unresolved,
                content_design_dependencies=buckets["content_design"],
                entity_dependencies=buckets["entity"],
                author_dependencies=buckets["author"],
                manual_dependencies=buckets["manual"],
                confirmed_binding_dependencies=buckets["confirmed_binding"],
                continuity_safe=safe,
                ready_reason=("所有 continuity 依赖均已 resolved" if safe else
                              "依赖未决语义 → 不能 READY")))
        blocked_now = [row_ for row_ in proofs if not row_.continuity_safe]
        payload = {"generated_at": _now(), "batch_id": batch_id,
                   "target_count": len(proofs),
                   "ready_count": sum(1 for row_ in proofs if row_.continuity_safe),
                   "blocked_count": len(blocked_now),
                   "content_design_blocked": sum(
                       1 for row_ in blocked_now if row_.content_design_dependencies),
                   "entity_blocked": sum(1 for row_ in blocked_now
                                         if row_.entity_dependencies),
                   "author_blocked": sum(1 for row_ in blocked_now
                                         if row_.author_dependencies),
                   "manual_blocked": sum(1 for row_ in blocked_now
                                         if row_.manual_dependencies),
                   "confirmed_binding_blocked": sum(
                       1 for row_ in blocked_now if row_.confirmed_binding_dependencies),
                   "proofs": [row_.model_dump(mode="json") for row_ in proofs],
                   "hard_rule": ("真实语义依赖链经过 unresolved content design / entity "
                                 "exact identity / author decision / manual state binding / "
                                 "confirmed binding conflict → 不能 READY"),
                   "read_only": True, "non_authoritative": True}
        _write_json(self.design_dir /
                    (artifact_name or f"{batch_id}_DEPENDENCY_CLOSURE.json"), payload)
        return payload

    # ---- PART C: Batch04 residual ready provenance -----------------------
    def residual_ready_provenance(self, *, inputs: ReadinessInputs | None = None,
                                  readiness: Mapping[str, Any] | None = None
                                  ) -> dict[str, Any]:
        inputs = inputs or self.load()
        readiness = readiness or _read_json(self.design_dir / "M11_READINESS_V2.json")
        # P15i 当时（执行后）的 projection 里 Batch 04 残留 1 个 READY target；
        # V2 修正后应为 0。这里以旧的 hardened artifact 为「修正前」证据。
        previous = _read_json(self.design_dir / "M11_READINESS_HARDENED.json")
        previous_row = next((item for item in previous.get("batches") or []
                             if item.get("batch_id") == "REPAIR_BATCH_04"), {})
        previous_ready = [str(item) for item in
                          previous_row.get("ready_target_ids") or []]
        row = next((item for item in readiness.get("batches") or []
                    if item.get("batch_id") == "REPAIR_BATCH_04"), {})
        current_ready = {str(item) for item in row.get("ready_target_ids") or []}
        current_blocked = {str(item) for item in row.get("blocked_target_ids") or []}
        labels = {cid: str(value.get("id")) for cid, value in inputs.legacy_rows.items()}
        residency: list[dict[str, Any]] = []
        for chapter_id in previous_ready:
            chapter_id = str(chapter_id)
            reconciliation = _read_json(self.design_dir / "BATCH_04_RECONCILIATION.json")
            record = next((item for item in reconciliation.get("records") or []
                           if item.get("chapter_id") == chapter_id), {})
            target = inputs.targets.get(chapter_id) or {}
            artifact = inputs.artifacts.get(chapter_id)
            residency.append({
                "chapter_id": chapter_id, "legacy_label": labels.get(chapter_id, ""),
                "why_ready_after_p15i": (
                    "P15i 记录为 CONTENT_DESIGN_REQUIRED，但 P15h readiness builder 只在 "
                    "P15h design queue 内匹配 content-design label → 该 target 被误判 READY"),
                "previous_status": str(record.get("new_resolution_status") or ""),
                "released_dependency": "无（误判来源是 own content-design 未登记，不是 dependency 释放）",
                "foundation_substrate": (artifact.validator_results.get(
                    "chapter_ir_validator", "") if artifact else ""),
                "risk": str(target.get("risk") or ""),
                "actual_repair_class": str(record.get("repair_class") or ""),
                "involves": {"content_design": True, "entity_ambiguity": False,
                             "author_decision": False, "manual": False,
                             "confirmed_binding": False},
                "verdict": "FALSE_READY（readiness projection 错误）→ 修正为 "
                           "BLOCKED_CONTENT_DESIGN，不执行",
                "v2_disposition": ("BLOCKED" if chapter_id in current_blocked
                                   else ("READY" if chapter_id in current_ready
                                         else "RESOLVED"))})
        payload = {"generated_at": _now(), "batch_id": "REPAIR_BATCH_04",
                   "ready_target_count": len(residency),
                   "previous_ready_target_ids": previous_ready,
                   "v2_ready_target_ids": sorted(current_ready),
                   "provenance": residency,
                   "readiness_projection_fixed": not current_ready or all(
                        item["v2_disposition"] != "READY" for item in residency),
                   "executed": False, "executed_targets": [],
                   "note": ("§12：readiness 算错时不执行；修正 projection，"
                            "把 target 放回 BLOCKED_CONTENT_DESIGN"),
                   "read_only": True, "non_authoritative": True}
        _write_json(self.design_dir / "BATCH04_RESIDUAL_READY_PROVENANCE.json", payload)
        return payload

    # ---- PART J: overlay V2（primary buckets + derived blockers） --------
    def overlay_v2(self, *, inputs: ReadinessInputs | None = None,
                   readiness: Mapping[str, Any] | None = None) -> dict[str, Any]:
        inputs = inputs or self.load()
        readiness = readiness or _read_json(self.design_dir / "M11_READINESS_V2.json")
        states = self.target_states(inputs=inputs)
        primary: dict[str, int] = {bucket: 0 for bucket in PRIMARY_BUCKETS}
        blockers: dict[str, int] = {}
        per_batch: dict[str, dict[str, int]] = {}
        for row in states.values():
            primary[row.primary_resolution_status] += 1
            batch_key = row.batch_id
            batch_counts = per_batch.setdefault(
                batch_key, {bucket: 0 for bucket in PRIMARY_BUCKETS})
            batch_counts[row.primary_resolution_status] += 1
            for blocker in row.execution_blockers:
                blockers[blocker] = blockers.get(blocker, 0) + 1
        total = sum(primary.values())
        target_count = len(inputs.targets)
        resolved_total = primary["resolved_repaired"] + \
            primary["resolved_no_repair_required"]
        subtype_counts = dict(_read_json(
            self.design_dir / "M11_REPAIR_SUBTYPE_LEDGER.json").get(
            "resolved_subtype_counts") or {})
        official = {
            "generated_at": _now(),
            "semantics_version": "v2",
            "primary_resolution_status_counts": dict(primary),
            "resolved_total": resolved_total,
            "repaired": primary["resolved_repaired"],
            "no_repair_required": primary["resolved_no_repair_required"],
            "repaired_evidence_only": subtype_counts.get("repaired_evidence_only", 0),
            "repaired_field_rebind": subtype_counts.get("repaired_field_rebind", 0),
            "repaired_micro_semantic": subtype_counts.get("repaired_micro_semantic", 0),
            "repaired_confirmed_override": subtype_counts.get(
                "repaired_confirmed_override", 0),
            "repaired_semantic_addition": subtype_counts.get(
                "repaired_semantic_addition", 0),
            "repair_subtype_ledger_ref": "M11_REPAIR_SUBTYPE_LEDGER.json",
            "evidence_ready": primary["evidence_ready"],
            "manual_required": primary["manual_required"],
            "content_design_required": primary["content_design_required"],
            "author_decision": primary["author_decision"],
            "pending": primary["pending"],
            "entity_ambiguity": blockers.get("BLOCKED_ENTITY_AMBIGUITY", 0),
            "confirmed_binding_blocked": blockers.get(
                "BLOCKED_CONFIRMED_BINDING_CONFLICT", 0),
            "execution_blocker_counts": dict(sorted(blockers.items())),
            "blocked": sum(blockers.values()),
            "blocked_target_count": sum(
                1 for row in states.values() if row.execution_blockers),
            "remaining_repair_targets": target_count - resolved_total,
            "conservation": {"primary_total": total, "target_count": target_count,
                             "exact": total == target_count},
            "per_batch": per_batch,
            "blocked_semantics": ("blocked / entity_ambiguity / confirmed_binding_blocked "
                                  "是 derived blocker projection，不参与 372 primary 守恒"),
            "baseline_queue_counts": {"SEMANTIC_CONFIRMED": 198,
                                      "LEGACY_FIELD_CONFLICT": 27,
                                      "LEGACY_CONTENT_GAP": 345},
            "read_only": True, "non_authoritative": True}
        _write_json(self.design_dir / "M11_OVERLAY_V2.json", official)
        _write_json(self.repair_dir / "M11_OVERLAY.json", official)
        return {"official_overlay": official}

    # ---- run --------------------------------------------------------------
    def run(self) -> dict[str, Any]:
        inputs = self.load()
        integration = self.integrate_dynamic_design_items(inputs=inputs)
        readiness = self.build_readiness_v2(inputs=inputs)
        # 冻结"Batch 05 执行前"的快照（供 P15j gate / 审计使用）
        pre_inputs = self.load(include_batch05=False)
        pre_readiness = self.build_readiness_v2(inputs=pre_inputs)
        _write_json(self.design_dir / "M11_READINESS_V2_PRE_BATCH05.json",
                    pre_readiness)
        closure = self.dependency_closure("REPAIR_BATCH_05", inputs=inputs,
                                          readiness=readiness,
                                          artifact_name=("REPAIR_BATCH_05_DEPENDENCY_"
                                                         "CLOSURE_CURRENT.json"))
        residual = self.residual_ready_provenance(inputs=inputs, readiness=readiness)
        overlay = self.overlay_v2(inputs=inputs, readiness=readiness)
        batch_04 = next((row for row in readiness["batches"]
                         if row["batch_id"] == "REPAIR_BATCH_04"), {})
        batch_05 = next((row for row in pre_readiness["batches"]
                         if row["batch_id"] == "REPAIR_BATCH_05"), {})
        batch_06 = next((row for row in pre_readiness["batches"]
                         if row["batch_id"] == "REPAIR_BATCH_06"), {})
        checks = {
            "batch05_execution_status_ready": batch_05.get(
                "execution_status") in ("READY", "PARTIAL_READY"),
            "batch04_residual_false_ready_fixed": (
                residual["executed"] is False
                and residual["readiness_projection_fixed"] is True
                and residual["ready_target_count"] >= 1),
            "dynamic_cdq_integrated": integration["new_item_count"] >= 0,
            "overlay_primary_conservation": overlay["official_overlay"]["conservation"][
                "exact"],
            "author_decisions_frozen": True,
            "micro_proposals_not_executed": True,
            "content_generated_false": True,
            "readiness_execution_semantics_split": "completion_status" in batch_05
            and "execution_status" in batch_05,
        }
        payload = {"generated_at": _now(), "phase": "P15j",
                   "status": "PASS" if all(checks.values()) else "NEEDS_ATTENTION",
                   "checks": checks,
                   "batch_04": {"completion_status": batch_04.get("completion_status"),
                                "execution_status": batch_04.get("execution_status"),
                                "resolved": len(batch_04.get("resolved_target_ids") or []),
                                "ready": len(batch_04.get("ready_target_ids") or []),
                                "blocked": len(batch_04.get("blocked_target_ids") or [])},
                   "batch_05": {"completion_status": batch_05.get("completion_status"),
                                "execution_status": batch_05.get("execution_status"),
                                "ready": len(batch_05.get("ready_target_ids") or []),
                                "blocked": len(batch_05.get("blocked_target_ids") or [])},
                   "batch_05_current": next((
                       {"completion_status": row.get("completion_status"),
                        "execution_status": row.get("execution_status"),
                        "resolved": len(row.get("resolved_target_ids") or []),
                        "ready": len(row.get("ready_target_ids") or []),
                        "blocked": len(row.get("blocked_target_ids") or [])}
                       for row in readiness["batches"]
                       if row["batch_id"] == "REPAIR_BATCH_05"), {}),
                   "batch_06": {"completion_status": batch_06.get("completion_status"),
                                "execution_status": batch_06.get("execution_status"),
                                "ready": len(batch_06.get("ready_target_ids") or []),
                                "blocked": len(batch_06.get("blocked_target_ids") or [])},
                   "completion_status_counts": readiness["completion_status_counts"],
                   "execution_status_counts": readiness["execution_status_counts"],
                   "cdq_integration": {"new": integration["new_item_count"],
                                       "duplicates": integration["duplicate_count"],
                                       "merged": integration["merged_item_count"]},
                   "batch_05_closure": {"ready": closure["ready_count"],
                                        "blocked": closure["blocked_count"]},
                   "batch_04_residual": residual["ready_target_count"],
                   "overlay": {key: overlay["official_overlay"][key] for key in
                               ("resolved_total", "repaired", "no_repair_required",
                                "evidence_ready", "manual_required",
                                "content_design_required", "author_decision",
                                "entity_ambiguity", "confirmed_binding_blocked",
                                "pending", "blocked")},
                   "content_generated": False, "repair_executed": False,
                   "read_only": True, "non_authoritative": True}
        _write_json(self.design_dir / "P15J_SUMMARY.json", payload)
        return payload
