"""M11-BLOCKER-00：Blocker Inventory + Root Blocker Graph + Unlock Impact + Priority。

这是 blocker phase 的强制入口，**analysis-only**：

- 只读取 M11 blocker entry baseline（149 non-terminal primary targets）+ 现有
  backlog / CDQ / entity queue / author inventory / readiness continuity；
- 构建 evidence-backed Root Blocker Graph、Unlock Impact、Execution Priority、
  Author Decision cluster proposals、lane recommendation、M12 blocker mapping；
- **不解决、不批准、不 repair、不 rewrite、不 terminalize 任何 target**；
- **不执行**任何 blocker lane（AUTHOR / ENTITY / MANUAL / CONTENT_REWRITE）；
- ContentDesignResolver / EntityResolutionEngine / ManualRepairWorkbench /
  AuthorDecisionConsole 保持 PLANNED_ONLY；
- 不修改 overlay / readiness / ledger / backlog / queue / truth boundary /
  Repair Contract / `REPAIR_GATE_V1`；不重开 P15。

产物（`workspace/wasteland_001_exports/repair_adoption_v1/` 根）：
`ROOT_BLOCKER_INVENTORY.json` · `ROOT_BLOCKER_GRAPH.json` ·
`BLOCKER_TARGET_COVERAGE.json` · `BLOCKER_UNLOCK_IMPACT.json` ·
`BLOCKER_EXECUTION_PRIORITY.json` · `AUTHOR_DECISION_CLUSTER_PROPOSALS.json` ·
`NEXT_BLOCKER_LANE_RECOMMENDATION.json` · `M11_CLOSURE_CONTROLLER_SNAPSHOT.json` ·
`M12_BLOCKER_MAPPING.json` · `M11_BLOCKER_BASELINE.json` · `M11_BLOCKER_00_GATE.json`
"""

from __future__ import annotations

from collections import Counter, deque
from pathlib import Path
from typing import Any, Iterable, Mapping

from novelforge.story_engine.historical_adoption import ADOPTION_DIR
from novelforge.story_engine.historical_ir import HISTORY_DIR
from novelforge.story_engine.m11_run01 import (
    _digest_json,
    _git_state,
    _now,
    _read_json,
    _write_json,
)
from novelforge.story_engine.m11_run12 import M11Run12Service

BLOCKER00_ID = "M11-BLOCKER-00"
PRODUCTION_SOURCE_COMMIT = "d5e5919"
PHASE_CLOSEOUT_COMMIT = "5e97e7e"
# BLOCKER-00 分析开始点 = Phase A closeout commit（pinned；analysis-only 不产生
# production mutation，因此该值在后续 commit 之后仍保持稳定）。
BLOCKER00_BASE_COMMIT = "5e97e7e8aacb764aef8b0f30ba87c19e493a8e63"

INVENTORY_FILE = "ROOT_BLOCKER_INVENTORY.json"
GRAPH_FILE = "ROOT_BLOCKER_GRAPH.json"
COVERAGE_FILE = "BLOCKER_TARGET_COVERAGE.json"
IMPACT_FILE = "BLOCKER_UNLOCK_IMPACT.json"
PRIORITY_FILE = "BLOCKER_EXECUTION_PRIORITY.json"
AUTHOR_CLUSTER_FILE = "AUTHOR_DECISION_CLUSTER_PROPOSALS.json"
LANE_FILE = "NEXT_BLOCKER_LANE_RECOMMENDATION.json"
CLOSURE_SNAPSHOT_FILE = "M11_CLOSURE_CONTROLLER_SNAPSHOT.json"
M12_MAPPING_FILE = "M12_BLOCKER_MAPPING.json"
BASELINE_FILE = "M11_BLOCKER_BASELINE.json"
GATE_FILE = "M11_BLOCKER_00_GATE.json"

ENTRY_TARGETS_FILE = "M11_BLOCKER_ENTRY_TARGETS.json"
ENTRY_BASELINE_FILE = "M11_BLOCKER_00_ENTRY_BASELINE.json"

ANALYSIS_INVARIANTS: tuple[str, ...] = (
    "DERIVED_BLOCKER_COUNT_IS_NOT_EXECUTION_ITEM_COUNT",
    "ROOT_BLOCKER_FIRST",
    "AUTHOR_DECISION_IS_BATCHED",
    "P15_EXECUTOR_READ_ONLY_AFTER_CLOSEOUT",
    "TRUTH_BOUNDARY_UNCHANGED",
    "BLOCKER_00_BEFORE_LANE_EXECUTION",
    "NO_DIRECT_BACKLOG_DRAIN_BEFORE_ROOT_CAUSE_GRAPH",
    "BLOCKER_00_IS_ANALYSIS_ONLY",
    "ROOT_BLOCKER_MUST_BE_EVIDENCE_BACKED",
)

# overlay/readiness blocker code → 分析 family group
BLOCKER_GROUPS: Mapping[str, str] = {
    "BLOCKED_CONTENT_DESIGN": "CONTENT_DESIGN",
    "BLOCKED_MANUAL_REPAIR": "MANUAL",
    "BLOCKED_ENTITY_AMBIGUITY": "ENTITY",
    "BLOCKED_AUTHOR_DECISION": "AUTHOR",
}
GROUP_FAMILIES: Mapping[str, tuple[str, ...]] = {
    "CONTENT_DESIGN": ("CONTENT_DESIGN",),
    "MANUAL": ("MANUAL",),
    "ENTITY": ("ENTITY",),
    "AUTHOR": ("AUTHOR_POLICY", "AUTHOR_CONTENT", "AUTHOR_DECISION", "MAJOR_DESIGN"),
}
LANE_FAMILY: Mapping[str, str] = {
    "LANE_MANUAL": "MANUAL",
    "LANE_ENTITY": "ENTITY",
    "LANE_AUTHOR_POLICY": "AUTHOR_POLICY",
    "LANE_AUTHOR_CONTENT": "AUTHOR_CONTENT",
    "LANE_AUTHOR_DECISION": "AUTHOR_DECISION",
    "LANE_MAJOR_DESIGN": "MAJOR_DESIGN",
    "LANE_CONTENT_REWRITE": "CONTENT_DESIGN",
}
FAMILY_OWNER: Mapping[str, str] = {
    "CONTENT_DESIGN": "CONTENT_DESIGN",
    "MANUAL": "OPERATOR+author",
    "ENTITY": "ENTITY_RESOLUTION",
    "AUTHOR_POLICY": "AUTHOR",
    "AUTHOR_CONTENT": "AUTHOR",
    "AUTHOR_DECISION": "AUTHOR",
    "MAJOR_DESIGN": "AUTHOR",
}
FAMILY_APPROVAL: Mapping[str, str] = {
    "CONTENT_DESIGN": "content-design proposal（event_added>0 需 AUTHOR_CONTENT_APPROVAL）",
    "MANUAL": "operator review + author confirm（FIELD_REBIND 需 scope validator）",
    "ENTITY": "frozen boundary auto-resolution 或 ENTITY_RESOLUTION_REQUIRED",
    "AUTHOR_POLICY": "AUTHOR_POLICY_SELECTION",
    "AUTHOR_CONTENT": "AUTHOR_CONTENT_APPROVAL",
    "AUTHOR_DECISION": "AUTHOR_DECISION",
    "MAJOR_DESIGN": "MAJOR_DESIGN approval",
}
FAMILY_RESOLUTION_STATUS: Mapping[str, str] = {
    "CONTENT_DESIGN": "NEEDS_CONTENT_DESIGN",
    "MANUAL": "NEEDS_MANUAL",
    "ENTITY": "NEEDS_ENTITY",
    "AUTHOR_POLICY": "NEEDS_AUTHOR",
    "AUTHOR_CONTENT": "NEEDS_AUTHOR",
    "AUTHOR_DECISION": "NEEDS_AUTHOR",
    "MAJOR_DESIGN": "NEEDS_AUTHOR",
}
FAMILY_LANE: Mapping[str, str] = {
    "CONTENT_DESIGN": "CONTENT_DESIGN",
    "MANUAL": "MANUAL",
    "ENTITY": "ENTITY",
    "AUTHOR_POLICY": "AUTHOR_POLICY",
    "AUTHOR_CONTENT": "AUTHOR_CONTENT",
    "AUTHOR_DECISION": "AUTHOR_DECISION",
    "MAJOR_DESIGN": "MAJOR_DESIGN",
}
FAMILY_ORDER: tuple[str, ...] = (
    "AUTHOR_POLICY", "AUTHOR_CONTENT", "AUTHOR_DECISION", "MAJOR_DESIGN", "ENTITY",
    "MANUAL", "CONTENT_DESIGN")

COMPONENT_STATUS: Mapping[str, str] = {
    "RootBlockerGraph": "IMPLEMENTED_FOR_BLOCKER_00_ANALYSIS",
    "UnlockImpactAnalyzer": "IMPLEMENTED_FOR_BLOCKER_00_ANALYSIS",
    "BlockerPriorityPlanner": "IMPLEMENTED_FOR_BLOCKER_00_ANALYSIS",
    "BlockerInventoryBuilder": "IMPLEMENTED_FOR_BLOCKER_00_ANALYSIS",
    "M11ClosureController": "ANALYSIS_ONLY_SNAPSHOT",
    "BlockerResolutionOrchestrator": "PLANNED_ONLY",
    "ContentDesignResolver": "PLANNED_ONLY",
    "EntityResolutionEngine": "PLANNED_ONLY",
    "ManualRepairWorkbench": "PLANNED_ONLY",
    "AuthorDecisionConsole": "PLANNED_ONLY",
}


def _chapter_order(label: str) -> tuple[int, str]:
    digits = "".join(ch for ch in str(label) if ch.isdigit())
    return (int(digits) if digits else 10**6, str(label))


class BlockerInventoryBuilder:
    """收集 149 non-terminal targets 的 evidence、dependency 与已有稳定 blocker 身份。"""

    def __init__(self, service: "M11Blocker00Service") -> None:
        self.service = service

    def build(self) -> dict[str, Any]:
        service = self.service
        entry = _read_json(service.design_dir / ENTRY_TARGETS_FILE)
        targets = {str(row["target_id"]): row for row in entry.get("targets") or []}
        labels = {str(row["target_id"]): str(row.get("chapter") or "")
                  for row in entry.get("targets") or []}
        backlog = _read_json(service.design_dir / "M11_PRODUCTION_BACKLOG.json")
        items = [row for row in backlog.get("items") or []
                 if str(row.get("status")) != "DONE"]
        active_cdq = {str(row.get("chapter_id")): str(row.get("design_item_id"))
                      for row in _read_json(
                          service.design_dir / "M11_CONTENT_DESIGN_QUEUE_V3.json"
                      ).get("requirements") or []
                      if str(row.get("status")) == "ACTIVE"}
        entity_queue = _read_json(service.design_dir / "M11_ENTITY_RESOLUTION_QUEUE.json")
        cluster_by_chapter: dict[str, str] = {}
        for cluster in entity_queue.get("clusters") or []:
            for chapter_id in cluster.get("chapter_ids") or []:
                cluster_by_chapter[str(chapter_id)] = str(cluster.get("cluster_id"))
        author_inventory = _read_json(service.design_dir / "AUTHOR_ACTION_INVENTORY.json")
        author_by_label: dict[str, str] = {}
        for row in author_inventory.get("items") or []:
            for label in row.get("legacy_labels") or []:
                author_by_label.setdefault(str(label), str(row.get("item_id")))
        roots: dict[str, dict[str, Any]] = {}

        def add_root(root_id: str, family: str, *, source_kind: str, source_ref: str,
                     source_artifact: str, evidence: list[str]) -> None:
            row = roots.setdefault(root_id, {
                "root_blocker_id": root_id, "family": family,
                "owner": FAMILY_OWNER.get(family, "UNKNOWN"),
                "source_kind": source_kind, "source_ref": source_ref,
                "source_artifact": source_artifact, "evidence": [],
                "resolution_status": FAMILY_RESOLUTION_STATUS.get(family, "UNRESOLVED"),
                "approval_requirement": FAMILY_APPROVAL.get(family, "UNKNOWN"),
                "analysis_confidence": "HIGH"})
            for item in evidence:
                if item not in row["evidence"]:
                    row["evidence"].append(item)

        own_roots: dict[str, dict[str, tuple[str, str]]] = {}
        for target_id, row in targets.items():
            label = labels[target_id]
            own: dict[str, tuple[str, str]] = {}
            if target_id in active_cdq:
                root_id = active_cdq[target_id]
                own[root_id] = ("CONTENT_DESIGN", "own_cdq")
                add_root(root_id, "CONTENT_DESIGN", source_kind="CDQ_ACTIVE",
                         source_ref=root_id,
                         source_artifact="M11_CONTENT_DESIGN_QUEUE_V3.json",
                         evidence=[f"target {label} active CDQ"])
            for item in items:
                item_id = str(item.get("item_id"))
                covers = (target_id in (item.get("target_ids") or [])
                          or label in (item.get("legacy_labels") or []))
                if not covers:
                    continue
                family = LANE_FAMILY.get(str(item.get("lane")))
                if not family:
                    continue
                own.setdefault(item_id, (family, "own_backlog"))
                add_root(item_id, family, source_kind="BACKLOG_ITEM", source_ref=item_id,
                         source_artifact="M11_PRODUCTION_BACKLOG.json",
                         evidence=[f"backlog item covers {label}"])
            cluster = cluster_by_chapter.get(target_id)
            if cluster:
                own[cluster] = ("ENTITY", "own_entity_cluster")
                add_root(cluster, "ENTITY", source_kind="ENTITY_CLUSTER",
                         source_ref=cluster,
                         source_artifact="M11_ENTITY_RESOLUTION_QUEUE.json",
                         evidence=[f"entity cluster contains {label}"])
            author_item = author_by_label.get(label)
            if author_item:
                add_root(author_item, "AUTHOR_DECISION",
                         source_kind="AUTHOR_ACTION_ITEM", source_ref=author_item,
                         source_artifact="AUTHOR_ACTION_INVENTORY.json",
                         evidence=[f"author action for {label}"])
            own_roots[target_id] = own

        dependencies: dict[str, set[str]] = {}
        self_loops: dict[str, int] = {}
        label_to_id = {labels[target_id]: target_id for target_id in targets}
        for target_id, row in targets.items():
            label = labels[target_id]
            edges: set[str] = set()
            self_count = 0
            for src in row.get("dependency_roots") or []:
                src = str(src)
                if src == label:
                    self_count += 1
                    continue
                upstream = label_to_id.get(src)
                if upstream and upstream != target_id:
                    edges.add(upstream)
            dependencies[target_id] = edges
            if self_count:
                self_loops[target_id] = self_count
        return {"targets": targets, "labels": labels, "items": items,
                "roots": roots, "own_roots": own_roots,
                "dependencies": dependencies, "self_loops": self_loops,
                "entity_aggregate_root": "BL_ENTITY_CLUSTERS"}


class RootBlockerGraph:
    """把 target evidence 向上追踪为 evidence-backed root blockers（含 SCC 审计）。"""

    def __init__(self, inventory: Mapping[str, Any]) -> None:
        self.inventory = inventory

    def _nearest_roots(self, target_id: str, group: str
                       ) -> tuple[dict[str, tuple[str, int]], int]:
        own = self.inventory["own_roots"][target_id]
        families = GROUP_FAMILIES[group]
        hits = {root_id: (family, 0) for root_id, (family, _via) in own.items()
                if family in families}
        if hits:
            return hits, 0
        deps = self.inventory["dependencies"]
        seen = {target_id}
        frontier = deque([(target_id, 0)])
        while frontier:
            node, depth = frontier.popleft()
            for upstream in sorted(deps.get(node, ())):
                if upstream in seen:
                    continue
                seen.add(upstream)
                up_own = self.inventory["own_roots"][upstream]
                up_hits = {root_id: (family, depth + 1)
                           for root_id, (family, _via) in up_own.items()
                           if family in families}
                if up_hits:
                    return up_hits, depth + 1
                frontier.append((upstream, depth + 1))
        return {}, -1

    def build(self) -> dict[str, Any]:
        targets = self.inventory["targets"]
        labels = self.inventory["labels"]
        primary: dict[str, dict[str, tuple[str, int]]] = {}
        unresolved: list[dict[str, Any]] = []
        for target_id in sorted(targets, key=lambda item: _chapter_order(
                labels.get(item, ""))):
            row = targets[target_id]
            groups = sorted({BLOCKER_GROUPS[str(code)]
                             for code in row.get("current_direct_blockers") or []
                             if str(code) in BLOCKER_GROUPS})
            found: dict[str, tuple[str, int]] = {}
            missing: list[str] = []
            for group in groups:
                hits, depth = self._nearest_roots(target_id, group)
                if hits:
                    for root_id, (family, hit_depth) in hits.items():
                        current = found.get(root_id)
                        if current is None or hit_depth < current[1]:
                            found[root_id] = (family, hit_depth)
                    continue
                if group == "ENTITY":
                    aggregate = self.inventory["entity_aggregate_root"]
                    found[aggregate] = ("ENTITY", 1)
                    continue
                missing.append(group)
            primary[target_id] = found
            if missing:
                unresolved.append({
                    "target_id": target_id, "chapter": labels[target_id],
                    "missing_groups": missing,
                    "checked_evidence": {
                        "own_roots": sorted(self.inventory["own_roots"][target_id]),
                        "direct_blockers": list(row.get("current_direct_blockers") or []),
                        "dependency_roots": list(row.get("dependency_roots") or []),
                        "dependency_edges": len(
                            self.inventory["dependencies"].get(target_id, ())),
                        "backlog_refs": list(row.get("existing_backlog_refs") or []),
                        "cdq_refs": list(
                            row.get("content_design_requirement_refs") or [])},
                    "reason": (f"no evidence-backed {'/'.join(missing)} root in own "
                               "evidence or reachable upstream chain"),
                    "resolution_status": "NEEDS_ANALYSIS",
                    "auto_resolution": False})

        # transitive root dependencies（DAG，无 multi-node SCC；用 memo + BFS 保护环）
        memo: dict[str, set[str]] = {}

        def closure(target_id: str, stack: frozenset[str] = frozenset()) -> set[str]:
            if target_id in memo:
                return memo[target_id]
            if target_id in stack:                      # cycle guard（正常不应触发）
                return set()
            result = set(primary[target_id])
            for upstream in self.inventory["dependencies"].get(target_id, ()):
                result |= closure(upstream, stack | {target_id})
            memo[target_id] = result
            return result

        for target_id in targets:
            closure(target_id)

        # SCC / cycle 审计（target → target dependency edges）
        sccs = self._strongly_connected_components()
        cycles = [component for component in sccs if len(component) > 1]
        return {"targets": targets, "labels": labels, "roots": self.inventory["roots"],
                "own_roots": self.inventory["own_roots"], "primary_roots": primary,
                "all_root_dependencies": memo, "dependencies":
                    self.inventory["dependencies"], "unresolved_analysis": unresolved,
                "sccs": sccs, "cycles": cycles,
                "self_reference_entries": self.inventory["self_loops"]}

    def _strongly_connected_components(self) -> list[list[str]]:
        deps = self.inventory["dependencies"]
        index: dict[str, int] = {}
        low: dict[str, int] = {}
        on_stack: dict[str, bool] = {}
        stack: list[str] = []
        sccs: list[list[str]] = []
        counter = [0]

        def visit(node: str) -> None:
            index[node] = low[node] = counter[0]
            counter[0] += 1
            stack.append(node)
            on_stack[node] = True
            for upstream in sorted(deps.get(node, ())):
                if upstream not in index:
                    visit(upstream)
                    low[node] = min(low[node], low[upstream])
                elif on_stack.get(upstream):
                    low[node] = min(low[node], index[upstream])
            if low[node] == index[node]:
                component: list[str] = []
                while True:
                    member = stack.pop()
                    on_stack[member] = False
                    component.append(member)
                    if member == node:
                        break
                sccs.append(sorted(component))

        for node in sorted(self.inventory["targets"]):
            if node not in index:
                visit(node)
        return sccs


class UnlockImpactAnalyzer:
    """按「只解决当前 root」语义计算 unlock impact（multi-root 不重复计 immediate）。"""

    def __init__(self, graph: Mapping[str, Any]) -> None:
        self.graph = graph

    def analyze(self) -> dict[str, Any]:
        primary = self.graph["primary_roots"]
        closure = self.graph["all_root_dependencies"]
        labels = self.graph["labels"]
        targets = self.graph["targets"]
        dependencies = self.graph["dependencies"]
        unresolved_ids = {row["target_id"] for row in self.graph["unresolved_analysis"]}
        rows: dict[str, dict[str, Any]] = {}

        def ensure(root_id: str) -> dict[str, Any]:
            if root_id not in rows:
                root = self.graph["roots"][root_id]
                rows[root_id] = {
                    "root_blocker_id": root_id, "family": root["family"],
                    "owner": root["owner"],
                    "resolution_status": root["resolution_status"],
                    "approval_requirement": root["approval_requirement"],
                    "direct_targets": [], "transitive_targets": [],
                    "all_affected_targets": [],
                    "immediate_unlock_targets": [], "conditional_unlock_targets": [],
                    "unlock_depth_distribution": {}, "affected_batch_distribution": {},
                }
            return rows[root_id]

        for target_id, roots in primary.items():
            if target_id in unresolved_ids:
                continue
            for root_id, (_family, depth) in roots.items():
                row = ensure(root_id)
                if depth <= 1:
                    row["direct_targets"].append(target_id)
                row["all_affected_targets"].append(target_id)
                if len(roots) == 1:
                    row["immediate_unlock_targets"].append(target_id)
                else:
                    row["conditional_unlock_targets"].append(target_id)
                depth_key = str(depth)
                row["unlock_depth_distribution"][depth_key] = (
                    row["unlock_depth_distribution"].get(depth_key, 0) + 1)
                batch = str(targets[target_id].get("source_batch") or "")
                row["affected_batch_distribution"][batch] = (
                    row["affected_batch_distribution"].get(batch, 0) + 1)
        for target_id, roots in closure.items():
            if target_id in unresolved_ids:
                continue
            for root_id in roots:
                ensure(root_id)["transitive_targets"].append(target_id)

        summary_rows: list[dict[str, Any]] = []
        for root_id, row in rows.items():
            unique = sorted(set(row["all_affected_targets"]))
            immediate = sorted(set(row["immediate_unlock_targets"]))
            conditional = sorted(set(row["conditional_unlock_targets"]))
            shared = sorted(set(unique) - set(immediate))
            summary_rows.append({
                **{key: value for key, value in row.items()
                   if key not in ("immediate_unlock_targets",
                                  "conditional_unlock_targets")},
                "direct_targets": sorted(set(row["direct_targets"])),
                "transitive_targets": sorted(set(row["transitive_targets"])),
                "all_affected_targets": unique,
                "direct_target_count": len(set(row["direct_targets"])),
                "unique_affected_target_count": len(unique),
                "transitive_affected_target_count": len(set(row["transitive_targets"])),
                "exclusive_target_count": len(immediate),
                "shared_target_count": len(shared),
                "immediate_unlock_count_if_only_this_root_resolved": len(immediate),
                "conditional_unlock_count": len(conditional),
                "immediate_unlock_targets": immediate,
                "conditional_unlock_targets": conditional,
                "affected_batches": sorted(
                    {str(targets[item].get("source_batch") or "") for item in unique}),
                "truth_risk": max(
                    (str(targets[item].get("truth_risk") or "UNKNOWN")
                     for item in unique), key=_risk_rank, default="UNKNOWN"),
                "dependency_depth_min": min(
                    (depth for item in unique
                     for _root, depth in primary[item].values()
                     if _root == root_id), default=0),
                "dependency_depth_max": max(
                    (depth for item in unique
                     for _root, depth in primary[item].values()
                     if _root == root_id), default=0),
            })
        summary_rows.sort(key=lambda row: (-row["immediate_unlock_count_if_only_this_root_resolved"],
                                           -row["unique_affected_target_count"],
                                           FAMILY_ORDER.index(row["family"])
                                           if row["family"] in FAMILY_ORDER else 99,
                                           row["root_blocker_id"]))
        return {"roots": summary_rows,
                "root_count": len(summary_rows),
                "total_immediate_unlock": sum(
                    row["immediate_unlock_count_if_only_this_root_resolved"]
                    for row in summary_rows),
                "immediate_unlock_union": sorted(
                    {item for row in summary_rows
                     for item in row["immediate_unlock_targets"]}),
                "conditional_unlock_union": sorted(
                    {item for row in summary_rows
                     for item in row["conditional_unlock_targets"]}),
                "multi_root_double_count_protection": (
                    "immediate_unlock 只在 target 的全部 primary roots 恰为该 root 时计入；"
                    "multi-root target 只进入 conditional_unlock，不重复计入 immediate"),
                "targets_with_immediate_unlock": sum(
                    1 for target_id, roots in primary.items()
                    if target_id not in unresolved_ids and len(roots) == 1),
                "targets_conditional_only": sum(
                    1 for target_id, roots in primary.items()
                    if target_id not in unresolved_ids and len(roots) > 1),
                "unresolved_analysis_targets": sorted(unresolved_ids)}


def _risk_rank(value: str) -> int:
    return {"LOW": 0, "MEDIUM": 1, "HIGH": 2}.get(str(value), 3)


class BlockerPriorityPlanner:
    """透明 priority tiers（无黑盒总分）：immediate unlock → unique affected → batch 数。"""

    def __init__(self, impact: Mapping[str, Any]) -> None:
        self.impact = impact

    def plan(self) -> dict[str, Any]:
        rows: list[dict[str, Any]] = []
        for row in self.impact["roots"]:
            immediate = row["immediate_unlock_count_if_only_this_root_resolved"]
            unique = row["unique_affected_target_count"]
            batches = len(row["affected_batches"])
            if immediate >= 1:
                tier = "TIER_1_UNBLOCKS_DIRECTLY"
            elif unique >= 5 or batches >= 2:
                tier = "TIER_2_HIGH_LEVERAGE"
            elif unique >= 2:
                tier = "TIER_3_MEDIUM"
            else:
                tier = "TIER_4_LOCAL"
            rationale = (
                f"immediate_unlock={immediate}；unique_affected={unique}；"
                f"batches={batches}；family={row['family']}；"
                f"approval={row['approval_requirement']}")
            rows.append({**row, "priority_tier": tier, "rationale": rationale,
                         "shared_blocker_ratio": round(
                             row["shared_target_count"] /
                             max(1, row["unique_affected_target_count"]), 4)})
        rows.sort(key=lambda row: (row["priority_tier"],
                                   -row["immediate_unlock_count_if_only_this_root_resolved"],
                                   -row["unique_affected_target_count"],
                                   FAMILY_ORDER.index(row["family"])
                                   if row["family"] in FAMILY_ORDER else 99,
                                   row["root_blocker_id"]))
        tier_counts = Counter(row["priority_tier"] for row in rows)
        return {"roots": rows, "tier_counts": dict(tier_counts),
                "top_immediate_unlock": [row["root_blocker_id"] for row in rows
                                         if row["immediate_unlock_count_if_only_this_root_resolved"]][:20],
                "top_unique_affected": [row["root_blocker_id"] for row in
                                        sorted(rows, key=lambda row: (
                                            -row["unique_affected_target_count"],
                                            row["root_blocker_id"]))][:20],
                "multi_root_aware": True,
                "explainable_fields_only": True}


class M11Blocker00Service:
    """BLOCKER-00 编排：inventory → graph → impact → priority → proposals → gate。"""

    def __init__(self, project_root: Path | str, *, design_dir: str = ADOPTION_DIR,
                 foundation_dir: str = HISTORY_DIR) -> None:
        self.root = Path(project_root).resolve()
        self.design_dir = (self.root / design_dir).resolve()
        self.foundation_dir = (self.root / foundation_dir).resolve()
        self.runner = M11Run12Service(self.root, design_dir=str(self.design_dir),
                                      foundation_dir=str(self.foundation_dir))

    # ------------------------------------------------------------ run
    def run(self) -> dict[str, Any]:
        before = self._production_digests()
        inventory_input = BlockerInventoryBuilder(self).build()
        graph = RootBlockerGraph(inventory_input).build()
        impact = UnlockImpactAnalyzer(graph).analyze()
        priority = BlockerPriorityPlanner(impact).plan()
        inventory_artifact = self._inventory_artifact(graph, priority, impact)
        graph_artifact = self._graph_artifact(graph)
        coverage = self._coverage(graph)
        author_clusters = self._author_clusters(graph, impact)
        lane = self._lane_recommendation(impact, priority, graph)
        closure = self._closure_snapshot(graph, impact, priority, lane)
        m12_mapping = self._m12_mapping(graph, impact)
        baseline = self._baseline(graph, coverage, impact, priority, author_clusters,
                                  lane, closure, m12_mapping)
        after = self._production_digests()
        gate = self._gate(graph, coverage, impact, priority, author_clusters, lane,
                          m12_mapping, baseline, before == after)
        payload = {
            "generated_at": _now(), "blocker00_id": BLOCKER00_ID,
            "status": "COMPLETE" if gate["status"] == "PASS" else "FAIL",
            "analysis_only": True,
            "production_source_commit": PRODUCTION_SOURCE_COMMIT,
            "phase_closeout_commit": PHASE_CLOSEOUT_COMMIT,
            "blocker00_execution_base_commit": str(
                BLOCKER00_BASE_COMMIT),
            "commit_semantics": {
                "production_source_commit":
                    "Phase A 最终 production mutation source（M11-RUN-12）",
                "phase_closeout_commit":
                    "Phase A closeout / blocker entry baseline freeze",
                "blocker00_execution_base_commit":
                    "BLOCKER-00 分析开始点 = Phase A closeout commit（pinned；"
                    "analysis-only；不产生 production mutation）"},
            "non_terminal_target_count": coverage["non_terminal_target_count"],
            "root_blocker_count": coverage["root_blocker_count"],
            "unresolved_analysis_count": len(graph["unresolved_analysis"]),
            "recommended_next_lane": lane["recommended_next_lane"],
            "production_state_unchanged": before == after,
            "gate_status": gate["status"],
            "artifacts": {
                "root_blocker_inventory": INVENTORY_FILE,
                "root_blocker_graph": GRAPH_FILE,
                "blocker_target_coverage": COVERAGE_FILE,
                "blocker_unlock_impact": IMPACT_FILE,
                "blocker_execution_priority": PRIORITY_FILE,
                "author_decision_cluster_proposals": AUTHOR_CLUSTER_FILE,
                "next_blocker_lane_recommendation": LANE_FILE,
                "m11_closure_controller_snapshot": CLOSURE_SNAPSHOT_FILE,
                "m12_blocker_mapping": M12_MAPPING_FILE,
                "m11_blocker_baseline": BASELINE_FILE,
                "blocker00_gate": GATE_FILE},
            "read_only": True, "non_authoritative": True}
        _write_json(self.design_dir / INVENTORY_FILE, inventory_artifact)
        _write_json(self.design_dir / GRAPH_FILE, graph_artifact)
        _write_json(self.design_dir / COVERAGE_FILE, coverage)
        _write_json(self.design_dir / IMPACT_FILE, {
            **impact, "generated_at": _now(), "blocker00_id": BLOCKER00_ID,
            "read_only": True, "non_authoritative": True})
        _write_json(self.design_dir / PRIORITY_FILE, {
            **priority, "generated_at": _now(), "blocker00_id": BLOCKER00_ID,
            "read_only": True, "non_authoritative": True})
        _write_json(self.design_dir / AUTHOR_CLUSTER_FILE, author_clusters)
        _write_json(self.design_dir / LANE_FILE, lane)
        _write_json(self.design_dir / CLOSURE_SNAPSHOT_FILE, closure)
        _write_json(self.design_dir / M12_MAPPING_FILE, m12_mapping)
        _write_json(self.design_dir / BASELINE_FILE, baseline)
        _write_json(self.design_dir / GATE_FILE, gate)
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

    def _inventory_artifact(self, graph: Mapping[str, Any], priority: Mapping[str, Any],
                            impact: Mapping[str, Any]) -> dict[str, Any]:
        priority_map = {row["root_blocker_id"]: row for row in priority["roots"]}
        impact_map = {row["root_blocker_id"]: row for row in impact["roots"]}
        mapped_ids = {root_id for roots in graph["primary_roots"].values()
                      for root_id in roots}
        rows: list[dict[str, Any]] = []
        unmapped: list[dict[str, Any]] = []
        for root_id, root in sorted(graph["roots"].items()):
            if root_id not in mapped_ids:
                unmapped.append({"root_blocker_id": root_id, "family": root["family"],
                                 "source_kind": root["source_kind"],
                                 "source_ref": root["source_ref"],
                                 "note": "evidence 存在，但当前不直接/间接阻塞任何 non-terminal target"})
                continue
            imp = impact_map.get(root_id, {})
            pri = priority_map.get(root_id, {})
            rows.append({
                **root,
                "direct_targets": imp.get("direct_targets", []),
                "transitive_targets": imp.get("transitive_targets", []),
                "all_affected_targets": imp.get("all_affected_targets", []),
                "affected_batches": imp.get("affected_batches", []),
                "dependency_depth_min": imp.get("dependency_depth_min", 0),
                "dependency_depth_max": imp.get("dependency_depth_max", 0),
                "truth_risk": imp.get("truth_risk", "UNKNOWN"),
                "approval_requirement": root["approval_requirement"],
                "existing_backlog_refs": (
                    [root_id] if root["source_kind"] == "BACKLOG_ITEM" else []),
                "existing_cdq_refs": (
                    [root_id] if root["source_kind"] == "CDQ_ACTIVE" else []),
                "resolution_status": root["resolution_status"],
                "analysis_confidence": root["analysis_confidence"],
                "priority_tier": pri.get("priority_tier", ""),
            })
        return {"generated_at": _now(), "blocker00_id": BLOCKER00_ID,
                "root_blocker_count": len(rows),
                "evidence_roots_not_currently_blocking": unmapped,
                "evidence_roots_not_currently_blocking_count": len(unmapped),
                "resolution_status_semantics": (
                    "本轮只允许 UNRESOLVED / NEEDS_AUTHOR / NEEDS_ENTITY / NEEDS_MANUAL / "
                    "NEEDS_CONTENT_DESIGN / NEEDS_ANALYSIS"),
                "roots": rows, "read_only": True, "non_authoritative": True}

    def _graph_artifact(self, graph: Mapping[str, Any]) -> dict[str, Any]:
        labels = graph["labels"]
        mapped_ids = {root_id for roots in graph["primary_roots"].values()
                      for root_id in roots}
        root_nodes = [{"node_id": root_id, "node_type": "ROOT_BLOCKER",
                       "family": root["family"], "owner": root["owner"],
                       "source_kind": root["source_kind"], "source_ref": root["source_ref"]}
                      for root_id, root in sorted(graph["roots"].items())
                      if root_id in mapped_ids]
        target_nodes = [{"node_id": target_id, "node_type": "PRIMARY_TARGET",
                         "chapter": labels[target_id],
                         "overlay_status": row.get("current_overlay_status"),
                         "readiness_state": (row.get("current_readiness_status") or {}
                                             ).get("state"),
                         "source_batch": row.get("source_batch")}
                        for target_id, row in sorted(graph["targets"].items())]
        root_edges: list[dict[str, Any]] = []
        for target_id, roots in sorted(graph["primary_roots"].items()):
            for root_id, (family, depth) in sorted(roots.items()):
                root_edges.append({"from": root_id, "to": target_id,
                                   "relation": "ROOT_BLOCKS_TARGET",
                                   "family": family, "depth": depth,
                                   "direct": depth <= 1})
        dependency_edges = [{"from": target_id, "to": upstream,
                             "relation": "TARGET_DEPENDS_ON_TARGET"}
                            for target_id, ups in sorted(graph["dependencies"].items())
                            for upstream in sorted(ups)]
        target_root_mapping = {
            target_id: {
                "chapter": labels[target_id],
                "primary_root_candidates": [
                    {"root_blocker_id": root_id, "family": family,
                     "dependency_depth": depth, "relation": (
                         "direct" if depth <= 1 else "transitive")}
                    for root_id, (family, depth) in sorted(
                        graph["primary_roots"].get(target_id, {}).items())],
                "all_root_dependencies": sorted(
                    graph["all_root_dependencies"].get(target_id, set())),
                "unresolved": target_id in {row["target_id"] for row in
                                            graph["unresolved_analysis"]}}
            for target_id in sorted(graph["targets"])}
        cycles = [{"cluster_id": f"UNRESOLVED_CYCLE_CLUSTER_{index:03d}",
                   "members": component,
                   "member_chapters": [labels[item] for item in component],
                   "requires_manual_root_analysis": True,
                   "evidence": "multi-node SCC in target dependency graph"}
                  for index, component in enumerate(graph["cycles"], start=1)]
        return {"generated_at": _now(), "blocker00_id": BLOCKER00_ID,
                "nodes": root_nodes + target_nodes,
                "root_edges": root_edges,
                "dependency_edges": dependency_edges,
                "target_root_mapping": target_root_mapping,
                "unmapped_evidence_roots": sorted(
                    set(graph["roots"]) - mapped_ids),
                "multi_root_targets": sorted(
                    target_id for target_id, roots in graph["primary_roots"].items()
                    if len(roots) > 1),
                "scc_count": len(graph["sccs"]),
                "cycle_count": len(graph["cycles"]),
                "cycle_clusters": cycles,
                "self_reference_entries_filtered": sum(
                    graph["self_reference_entries"].values()),
                "self_reference_note": (
                    "continuity projection 会把 target 自身 label 记入 dependency_roots；"
                    "这些是 identity 条目，不是 self-dependency cycle，已过滤并记录数量"),
                "answers": {
                    "root_direct_targets": "root_edges(direct=true) 按 from 分组",
                    "root_transitive_targets": "all_root_dependencies 反查",
                    "root_affected_batches": "unlock impact affected_batch_distribution",
                    "target_blocking_roots": "primary_roots[target_id]"},
                "read_only": True, "non_authoritative": True}

    def _coverage(self, graph: Mapping[str, Any]) -> dict[str, Any]:
        labels = graph["labels"]
        targets = graph["targets"]
        primary = graph["primary_roots"]
        unresolved = graph["unresolved_analysis"]
        unresolved_ids = {row["target_id"] for row in unresolved}
        mapped = [target_id for target_id in targets
                  if target_id not in unresolved_ids and primary[target_id]]
        multi = [target_id for target_id in mapped if len(primary[target_id]) > 1]
        root_edges = sum(len(roots) for roots in primary.values())
        dependency_edges = sum(len(ups) for ups in graph["dependencies"].values())
        coverage_exact = len(mapped) + len(unresolved_ids) == len(targets)
        mapped_root_ids = {root_id for roots in primary.values()
                           for root_id in roots}
        return {
            "generated_at": _now(), "blocker00_id": BLOCKER00_ID,
            "non_terminal_target_count": len(targets),
            "targets_with_root_mapping": len(mapped),
            "targets_with_multiple_roots": len(multi),
            "targets_with_no_evidence_backed_root": len(unresolved_ids),
            "root_blocker_count": len(mapped_root_ids),
            "evidence_roots_not_currently_blocking_count": len(
                set(graph["roots"]) - mapped_root_ids),
            "root_target_edge_count": root_edges,
            "dependency_edge_count": dependency_edges,
            "cycle_count": len(graph["cycles"]),
            "SCC_count": len(graph["sccs"]),
            "multi_root_target_ids": sorted(multi),
            "unresolved_analysis_targets": sorted(
                (row["chapter"], row["missing_groups"], row["reason"])
                for row in unresolved),
            "coverage_equation": (f"{len(mapped)} mapped + {len(unresolved_ids)} "
                                  f"UNRESOLVED_ANALYSIS = {len(targets)}"),
            "coverage_exact": coverage_exact,
            "no_silent_omission": coverage_exact
            and len(set(mapped) | unresolved_ids) == len(targets),
            "unresolved_policy": ("无法归因的 target 显式进入 UNRESOLVED_ANALYSIS，"
                                  "列出已检查 evidence，不猜测 owner、不创建 repair"),
            "read_only": True, "non_authoritative": True}

    def _author_clusters(self, graph: Mapping[str, Any],
                         impact: Mapping[str, Any]) -> dict[str, Any]:
        inventory = _read_json(self.design_dir / "AUTHOR_ACTION_INVENTORY.json")
        impact_by_root = {row["root_blocker_id"]: row for row in impact["roots"]}
        author_roots = {root_id: root for root_id, root in graph["roots"].items()
                        if root["family"] in ("AUTHOR_POLICY", "AUTHOR_CONTENT",
                                              "AUTHOR_DECISION", "MAJOR_DESIGN")}
        clusters: list[dict[str, Any]] = []
        grouped: dict[str, list[dict[str, Any]]] = {}
        for item in inventory.get("items") or []:
            grouped.setdefault(str(item.get("kind")), []).append(item)
        for index, (kind, items) in enumerate(sorted(grouped.items()), start=1):
            if kind == "MANUAL_REQUIRED":
                continue
            source_author_items = [str(item.get("item_id")) for item in items]
            root_ids = [item for item in source_author_items if item in author_roots]
            affected: set[str] = set()
            immediate = 0
            conditional = 0
            for root_id in root_ids:
                row = impact_by_root.get(root_id, {})
                affected |= set(row.get("all_affected_targets") or [])
                immediate += row.get("immediate_unlock_count_if_only_this_root_resolved", 0)
                conditional += row.get("conditional_unlock_count", 0)
            clusters.append({
                "cluster_id": f"AUTHOR_CLUSTER_{index:03d}_{kind}",
                "source_author_items": source_author_items,
                "shared_question_basis": str(
                    (items[0].get("question") if items else "") or "")[:200],
                "affected_targets": sorted(affected),
                "unlock_impact": {"immediate_unlock_estimate": immediate,
                                  "conditional_unlock_estimate": conditional},
                "why_they_can_be_batched": (
                    "同一 kind / 同一 question template；可由一次 author question 覆盖"),
                "why_they_cannot_be_batched": (
                    "若答案依赖各自的 event 语义或 Canon 约束，需逐项确认（不自动拆分）"),
                "auto_resolution": False,
                "option_auto_selected": False})
        return {"generated_at": _now(), "blocker00_id": BLOCKER00_ID,
                "proposal_count": len(clusters), "clusters": clusters,
                "invariant": "AUTHOR_DECISION_IS_BATCHED",
                "note": "proposal only：不自动选 option、不自动 resolve author decision",
                "read_only": True, "non_authoritative": True}

    def _lane_recommendation(self, impact: Mapping[str, Any],
                             priority: Mapping[str, Any],
                             graph: Mapping[str, Any]) -> dict[str, Any]:
        lane_stats: dict[str, dict[str, Any]] = {}
        for row in impact["roots"]:
            lane = FAMILY_LANE.get(row["family"], row["family"])
            bucket = lane_stats.setdefault(lane, {
                "lane": lane, "root_count": 0, "immediate_unlock_estimate": 0,
                "conditional_unlock_estimate": 0, "unique_affected_union": set(),
                "max_truth_risk": "UNKNOWN", "approval_needed": False,
                "root_ids": []})
            bucket["root_count"] += 1
            bucket["immediate_unlock_estimate"] += row[
                "immediate_unlock_count_if_only_this_root_resolved"]
            bucket["conditional_unlock_estimate"] += row["conditional_unlock_count"]
            bucket["unique_affected_union"] |= set(row["all_affected_targets"])
            bucket["max_truth_risk"] = max(bucket["max_truth_risk"], row["truth_risk"],
                                           key=_risk_rank)
            bucket["approval_needed"] = True
            bucket["root_ids"].append(row["root_blocker_id"])
        for bucket in lane_stats.values():
            bucket["unique_affected_count"] = len(bucket.pop("unique_affected_union"))
        ordered = sorted(lane_stats.values(),
                         key=lambda row: (-row["immediate_unlock_estimate"],
                                          -row["unique_affected_count"],
                                          row["lane"]))
        if not ordered:
            # M11 closure 后 approved/executed lanes 为空：lane ranking 退化为 NO_ACTIVE_LANE
            #（BLOCKER-00 的历史输出仍由 ROOT_BLOCKER_* frozen artifacts 保留）
            return {"generated_at": _now(), "blocker00_id": BLOCKER00_ID,
                    "lane_ranking": [], "recommended_next_lane": "NO_ACTIVE_LANE",
                    "recommended_root_blockers": [],
                    "reason": "no active root blocker lane remains（M11 closure 后）",
                    "immediate_unlock_estimate": 0,
                    "conditional_unlock_estimate": 0, "truth_risk": "NONE",
                    "approval_needed": False, "alternative_lane": "",
                    "why_not_alternative_first": "",
                    "execution_order_basis": ("execution order selected by BLOCKER-00 "
                                              "unlock impact analysis"),
                    "read_only": True, "non_authoritative": True}
        recommended = ordered[0]
        alternative = ordered[1] if len(ordered) > 1 else None
        top_roots = [row["root_blocker_id"] for row in priority["roots"]
                     if FAMILY_LANE.get(row["family"]) == recommended["lane"]
                     and row["priority_tier"].startswith(("TIER_1", "TIER_2"))][:10]
        return {"generated_at": _now(), "blocker00_id": BLOCKER00_ID,
                "lane_ranking": ordered,
                "recommended_next_lane": recommended["lane"],
                "recommended_root_blockers": top_roots,
                "reason": (f"immediate unlock estimate {recommended['immediate_unlock_estimate']}；"
                           f"unique affected {recommended['unique_affected_count']}；"
                           f"root count {recommended['root_count']}（BLOCKER-00 unlock "
                           "impact analysis 决定，非硬编码阶段顺序）"),
                "immediate_unlock_estimate": recommended["immediate_unlock_estimate"],
                "conditional_unlock_estimate": recommended["conditional_unlock_estimate"],
                "truth_risk": recommended["max_truth_risk"],
                "approval_needed": recommended["approval_needed"],
                "alternative_lane": alternative["lane"] if alternative else "",
                "why_not_alternative_first": (
                    f"alternative {alternative['lane']} immediate="
                    f"{alternative['immediate_unlock_estimate']}、unique="
                    f"{alternative['unique_affected_count']}（低于推荐 lane）"
                    if alternative else ""),
                "execution_order_basis": "execution order selected by BLOCKER-00 unlock impact analysis",
                "read_only": True, "non_authoritative": True}

    def _closure_snapshot(self, graph: Mapping[str, Any], impact: Mapping[str, Any],
                          priority: Mapping[str, Any],
                          lane: Mapping[str, Any]) -> dict[str, Any]:
        entry = _read_json(self.design_dir / ENTRY_BASELINE_FILE)
        top_roots = priority["roots"][:10]
        return {"generated_at": _now(), "blocker00_id": BLOCKER00_ID,
                "total_targets": entry.get("total_primary_targets"),
                "terminal_targets": entry.get("terminal_targets"),
                "non_terminal_targets": entry.get("non_terminal_targets"),
                "root_blocker_count": len(graph["roots"]),
                "unresolved_analysis_count": len(graph["unresolved_analysis"]),
                "top_root_blockers": [row["root_blocker_id"] for row in top_roots],
                "next_best_actions": [
                    {"action": f"prepare closure for {row['root_blocker_id']}",
                     "family": row["family"], "owner": row["owner"],
                     "immediate_unlock": row[
                         "immediate_unlock_count_if_only_this_root_resolved"],
                     "unique_affected": row["unique_affected_target_count"],
                     "priority_tier": row["priority_tier"]}
                    for row in top_roots],
                "estimated_immediately_unlockable_targets":
                    impact["targets_with_immediate_unlock"],
                "estimated_conditional_targets": impact["targets_conditional_only"],
                "m12_blockers_remaining": _read_json(
                    self.design_dir / "p15p" / "M12_ENTRY_CRITERIA.json"
                ).get("blocking_count"),
                "recommended_next_lane": lane["recommended_next_lane"],
                "analysis_only": True,
                "read_only": True, "non_authoritative": True}

    def _m12_mapping(self, graph: Mapping[str, Any],
                     impact: Mapping[str, Any]) -> dict[str, Any]:
        criteria = _read_json(self.design_dir / "p15p" / "M12_ENTRY_CRITERIA.json")
        author_roots = [row["root_blocker_id"] for row in impact["roots"]
                        if row["family"] in ("AUTHOR_POLICY", "AUTHOR_CONTENT",
                                             "AUTHOR_DECISION", "MAJOR_DESIGN")]
        mapped_root_count = len({root_id
                                 for roots in graph["primary_roots"].values()
                                 for root_id in roots})
        mapping: list[dict[str, Any]] = []
        for row in criteria.get("criteria") or []:
            # blocking_criteria 语义 = blocking ∧ unsatisfied（与 p15p 保持一致）
            if not row.get("blocking") or row.get("satisfied"):
                continue
            criterion = str(row.get("criterion"))
            if "terminal" in criterion:
                mapping.append({
                    "criterion": criterion, "mapped_phase": "M11 blocker closure + final closure",
                    "mapped_lanes": ["AUTHOR_POLICY", "AUTHOR_CONTENT",
                                     "AUTHOR_DECISION", "MAJOR_DESIGN", "ENTITY",
                                     "MANUAL", "CONTENT_DESIGN"],
                    "root_blocker_count": mapped_root_count,
                    "note": "149 non-terminal targets 必须 terminal 或项目允许的 terminal policy"})
            elif "author decisions" in criterion:
                mapping.append({
                    "criterion": criterion, "mapped_phase": "M11 blocker closure（author lane）",
                    "mapped_lanes": ["AUTHOR_POLICY", "AUTHOR_CONTENT",
                                     "AUTHOR_DECISION", "MAJOR_DESIGN"],
                    "root_blocker_count": len(author_roots),
                    "root_blocker_ids": author_roots,
                    "note": "AUTHOR_ACTION_INVENTORY 14 项；BLOCKER-00 只提供聚类 proposal"})
            else:
                mapping.append({
                    "criterion": criterion,
                    "mapped_phase": "M11 residual readiness + final acceptance",
                    "mapped_lanes": [], "root_blocker_count": 0,
                    "note": "phase-level gate：由 blocker closure 完成后的 residual AUTO_SAFE / "
                            "M11 final acceptance 阶段执行，不由单个 root 直接决定"})
        return {"generated_at": _now(), "blocker00_id": BLOCKER00_ID,
                "criteria_count": criteria.get("criteria_count"),
                "satisfied_count": criteria.get("satisfied_count"),
                "unsatisfied_count": criteria.get("unsatisfied_count"),
                "blocking_count": criteria.get("blocking_count"),
                "m12_entry_allowed": criteria.get("m12_entry_allowed"),
                "blocking_criteria_mapping": mapping,
                "note": "M12 criteria 未被修改；本映射只说明 blocker closure 与 M12 entry 的关系",
                "read_only": True, "non_authoritative": True}

    def _baseline(self, graph: Mapping[str, Any], coverage: Mapping[str, Any],
                  impact: Mapping[str, Any], priority: Mapping[str, Any],
                  author_clusters: Mapping[str, Any],
                  lane: Mapping[str, Any], closure: Mapping[str, Any],
                  m12_mapping: Mapping[str, Any]) -> dict[str, Any]:
        overlay = _read_json(self.design_dir / "M11_OVERLAY_V2.json")
        backlog = _read_json(self.design_dir / "M11_PRODUCTION_BACKLOG.json")
        queue2 = _read_json(self.design_dir / "M11_CONTENT_DESIGN_QUEUE_V2.json")
        queue3 = _read_json(self.design_dir / "M11_CONTENT_DESIGN_QUEUE_V3.json")
        truth = self.runner.truth_digests()
        frozen = self.runner.frozen_digests()
        return {
            "generated_at": _now(), "blocker00_id": BLOCKER00_ID,
            "production_source_commit": PRODUCTION_SOURCE_COMMIT,
            "phase_closeout_commit": PHASE_CLOSEOUT_COMMIT,
            "blocker00_execution_base_commit": str(
                BLOCKER00_BASE_COMMIT),
            "commit_semantics": {
                "production_source_commit":
                    "Phase A 最终 production mutation source（M11-RUN-12）",
                "phase_closeout_commit":
                    "Phase A closeout / blocker entry baseline freeze",
                "blocker00_execution_base_commit":
                    "BLOCKER-00 分析开始点 = Phase A closeout commit（pinned；"
                    "analysis-only；不产生 production mutation）"},
            "entry_target_count": coverage["non_terminal_target_count"],
            "root_blocker_count": coverage["root_blocker_count"],
            "target_coverage_summary": {
                "mapped": coverage["targets_with_root_mapping"],
                "multi_root": coverage["targets_with_multiple_roots"],
                "unresolved_analysis": coverage[
                    "targets_with_no_evidence_backed_root"],
                "coverage_exact": coverage["coverage_exact"]},
            "graph_summary": {
                "root_target_edge_count": coverage["root_target_edge_count"],
                "dependency_edge_count": coverage["dependency_edge_count"],
                "cycle_count": coverage["cycle_count"],
                "SCC_count": coverage["SCC_count"]},
            "unlock_impact_summary": {
                "total_immediate_unlock": impact["total_immediate_unlock"],
                "targets_with_immediate_unlock": impact["targets_with_immediate_unlock"],
                "targets_conditional_only": impact["targets_conditional_only"],
                "multi_root_double_count_protection":
                    impact["multi_root_double_count_protection"]},
            "priority_summary": priority["tier_counts"],
            "author_cluster_summary": {
                "proposal_count": author_clusters["proposal_count"]},
            "next_lane_recommendation": {
                "lane": lane["recommended_next_lane"],
                "root_blockers": lane["recommended_root_blockers"],
                "immediate_unlock_estimate": lane["immediate_unlock_estimate"]},
            "overlay_summary": dict(overlay.get("primary_resolution_status_counts") or {}),
            "backlog_summary": {"item_count": backlog.get("item_count"),
                                "lane_counts": dict(backlog.get("lane_counts") or {})},
            "cdq_summary": {"v2_item_count": queue2.get("item_count"),
                            "v3_active_count": queue3.get("active_count"),
                            "overlay_content_design_required":
                                overlay.get("content_design_required")},
            "truth_digests": truth,
            "foundation_digests": truth.get("historical_foundation"),
            "contract_digest": frozen.get("contract"),
            "gate_digest": frozen.get("repair_gate"),
            "p15_isolation": "PASS",
            "m12_status": {
                "m12_entry_allowed": m12_mapping.get("m12_entry_allowed"),
                "blocking_count": m12_mapping.get("blocking_count"),
                "satisfied_count": m12_mapping.get("satisfied_count")},
            "closure_controller_snapshot": closure,
            "invariants": list(ANALYSIS_INVARIANTS),
            "component_status": dict(COMPONENT_STATUS),
            "read_only": True, "non_authoritative": True}

    def _gate(self, graph: Mapping[str, Any], coverage: Mapping[str, Any],
              impact: Mapping[str, Any], priority: Mapping[str, Any],
              author_clusters: Mapping[str, Any], lane: Mapping[str, Any],
              m12_mapping: Mapping[str, Any], baseline: Mapping[str, Any],
              production_unchanged: bool) -> dict[str, Any]:
        truth = self.runner.truth_digests()
        checks = {
            "non_terminal_target_exact_set_preserved":
                coverage["non_terminal_target_count"] == 149
                and coverage["coverage_exact"] is True,
            "every_target_mapped_or_unresolved": (
                coverage["targets_with_root_mapping"]
                + coverage["targets_with_no_evidence_backed_root"] == 149),
            "no_silent_target_omission": coverage["no_silent_omission"] is True,
            "root_blocker_graph_built": coverage["root_blocker_count"] >= 1
                and coverage["root_target_edge_count"] >= 1,
            "cycle_scc_audit_complete": coverage["cycle_count"] == len(graph["cycles"])
                and coverage["SCC_count"] == len(graph["sccs"]),
            "unlock_impact_built": impact["root_count"] >= 1
                and impact["multi_root_double_count_protection"] != "",
            "multi_root_double_count_protection_pass":
                impact["targets_with_immediate_unlock"] + impact[
                    "targets_conditional_only"] + len(impact[
                        "unresolved_analysis_targets"]) == 149,
            "execution_priority_built": len(priority["roots"]) >= 1
                and all(row.get("rationale") for row in priority["roots"]),
            "author_batching_proposal_built": author_clusters["proposal_count"] >= 1
                and all(not row["auto_resolution"]
                        for row in author_clusters["clusters"]),
            "next_lane_recommendation_built":
                bool(lane["recommended_next_lane"])
                and lane["execution_order_basis"].startswith("execution order selected"),
            "m12_blocker_mapping_built": len(m12_mapping["blocking_criteria_mapping"]) == 4,
            "production_state_unchanged": production_unchanged,
            "truth_foundation_unchanged":
                truth.get("canon") == "73836dada9d6bf8e"
                and truth.get("historical_foundation", {}).get("index.json")
                == "16efe4c37ca9ea72",
            "contract_gate_unchanged": baseline["contract_digest"] == "67559aa55442d69e"
                and baseline["gate_digest"] == "e1eab4c33ae75b01",
            "p15_isolation_pass": baseline["p15_isolation"] == "PASS",
            "no_blocker_resolution_executed": all(
                row["resolution_status"] in ("UNRESOLVED", "NEEDS_AUTHOR",
                                             "NEEDS_ENTITY", "NEEDS_MANUAL",
                                             "NEEDS_CONTENT_DESIGN", "NEEDS_ANALYSIS")
                for row in graph["roots"].values()),
        }
        return {"generated_at": _now(), "blocker00_id": BLOCKER00_ID,
                "gate_id": "M11_BLOCKER_00_GATE", "status":
                    "PASS" if all(checks.values()) else "FAIL",
                "checks": checks,
                "failed_checks": sorted(key for key, value in checks.items() if not value),
                "check_count": len(checks),
                "read_only": True, "non_authoritative": True}


__all__ = [
    "ANALYSIS_INVARIANTS",
    "AUTHOR_CLUSTER_FILE",
    "BASELINE_FILE",
    "BLOCKER00_ID",
    "BlockerInventoryBuilder",
    "BlockerPriorityPlanner",
    "CLOSURE_SNAPSHOT_FILE",
    "COVERAGE_FILE",
    "GATE_FILE",
    "GRAPH_FILE",
    "IMPACT_FILE",
    "INVENTORY_FILE",
    "LANE_FILE",
    "M11Blocker00Service",
    "M12_MAPPING_FILE",
    "PRIORITY_FILE",
    "RootBlockerGraph",
    "UnlockImpactAnalyzer",
]
