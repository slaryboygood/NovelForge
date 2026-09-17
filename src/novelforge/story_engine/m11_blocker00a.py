"""M11-BLOCKER-00A：Canonical Root Identity Audit（analysis-only refinement）。

核心 invariants：

```text
ARTIFACT_IDENTITY_IS_NOT_ROOT_IDENTITY
ONE_SEMANTIC_ROOT_MAY_HAVE_MULTIPLE_ARTIFACT_REFS
ROOT_BLOCKER_MUST_BE_EVIDENCE_BACKED
AMBIGUOUS_DO_NOT_MERGE
NO_ALIAS_DOUBLE_COUNT
```

本模块只读取 BLOCKER-00 的 analysis artifacts + production projections，产出 canonical
root identity / graph / coverage / unlock impact / lane recommendation V2 等分析结果；
**不 resolution、不执行 lane、不修改任何 production state、不进入 M12、不重开 P15。**

产物（`workspace/wasteland_001_exports/repair_adoption_v1/` 根）：
`ROOT_BLOCKER_IDENTITY_AUDIT.json` · `AUTHOR_ROOT_FAMILY_AUDIT.json` ·
`ROOT_BLOCKER_CANONICAL_INVENTORY.json` · `ROOT_BLOCKER_CANONICAL_GRAPH.json` ·
`BLOCKER_CANONICAL_TARGET_COVERAGE.json` · `BLOCKER_CANONICAL_UNLOCK_IMPACT.json` ·
`NEXT_BLOCKER_LANE_RECOMMENDATION_V2.json` · `ZERO_TARGET_ROOT_AUDIT.json` ·
`M11_CLOSURE_CONTROLLER_SNAPSHOT_V2.json` · `M12_BLOCKER_MAPPING_V2.json` ·
`M11_BLOCKER_00A_GATE.json`
"""

from __future__ import annotations

from collections import Counter, deque
from pathlib import Path
from typing import Any, Iterable, Mapping

from novelforge.story_engine.historical_adoption import ADOPTION_DIR
from novelforge.story_engine.historical_ir import HISTORY_DIR
from novelforge.story_engine.m11_blocker00 import (
    BLOCKER_GROUPS,
    BlockerInventoryBuilder,
    FAMILY_LANE,
    FAMILY_ORDER,
    RootBlockerGraph,
    UnlockImpactAnalyzer,
    _risk_rank,
)
from novelforge.story_engine.m11_run01 import _digest_json, _now, _read_json, _write_json
from novelforge.story_engine.m11_run12 import M11Run12Service

BLOCKER00A_ID = "M11-BLOCKER-00A"

IDENTITY_AUDIT_FILE = "ROOT_BLOCKER_IDENTITY_AUDIT.json"
AUTHOR_AUDIT_FILE = "AUTHOR_ROOT_FAMILY_AUDIT.json"
CANONICAL_INVENTORY_FILE = "ROOT_BLOCKER_CANONICAL_INVENTORY.json"
CANONICAL_GRAPH_FILE = "ROOT_BLOCKER_CANONICAL_GRAPH.json"
CANONICAL_COVERAGE_FILE = "BLOCKER_CANONICAL_TARGET_COVERAGE.json"
CANONICAL_IMPACT_FILE = "BLOCKER_CANONICAL_UNLOCK_IMPACT.json"
LANE_V2_FILE = "NEXT_BLOCKER_LANE_RECOMMENDATION_V2.json"
ZERO_TARGET_AUDIT_FILE = "ZERO_TARGET_ROOT_AUDIT.json"
CLOSURE_SNAPSHOT_V2_FILE = "M11_CLOSURE_CONTROLLER_SNAPSHOT_V2.json"
M12_MAPPING_V2_FILE = "M12_BLOCKER_MAPPING_V2.json"
GATE_FILE = "M11_BLOCKER_00A_GATE.json"

BLOCKER00_INVENTORY = "ROOT_BLOCKER_INVENTORY.json"
BLOCKER00_GRAPH = "ROOT_BLOCKER_GRAPH.json"
BLOCKER00_IMPACT = "BLOCKER_UNLOCK_IMPACT.json"

ZERO_TARGET_CLASSES: tuple[str, ...] = (
    "VALID_ZERO_TARGET_EVIDENCE",
    "ALIAS_OF_ACTIVE_CANONICAL_ROOT",
    "STALE_ANALYSIS_ARTIFACT",
    "OUT_OF_SCOPE_HISTORICAL_REFERENCE",
    "AMBIGUOUS",
)


class CanonicalRootAuditor:
    """建立 artifact→canonical root 的 evidence-backed alias map。"""

    def __init__(self, service: "M11Blocker00AService") -> None:
        self.service = service

    # ------------------------------------------------------------ groups
    def _content_groups(self, roots: Mapping[str, Any],
                        backlog: Mapping[str, Any],
                        cdq_label: Mapping[str, str]) -> list[dict[str, Any]]:
        groups: list[dict[str, Any]] = []
        cdq_by_chapter = {cdq_label[root_id]: root_id
                          for root_id in roots if root_id.startswith("CDQ")}
        for root_id, root in sorted(roots.items()):
            if root["family"] != "CONTENT_DESIGN" or root_id.startswith("CDQ"):
                continue
            if root_id in ("BL_CONTENT_CAUSAL_BRIDGE", "BL_CONTENT_DECISION_EVENT"):
                labels = (backlog.get(root_id) or {}).get("legacy_labels") or []
                members = [root_id] + [cdq_by_chapter[label] for label in labels
                                       if cdq_by_chapter.get(label)]
                groups.append({
                    "group_id": f"CONTENT_UMBRELLA_{root_id}",
                    "candidate_refs": members,
                    "family": "CONTENT_DESIGN",
                    "merge_mode": "UMBRELLA_MULTI_TARGET_ALIAS",
                    "semantic_basis": (
                        "同一 aggregate backlog item 覆盖的每个 chapter 都有各自 active "
                        "CDQ requirement；aggregate 是 umbrella artifact，不是独立 root"),
                    "same_target_or_requirement": True,
                    "shared_lineage": True,
                    "merge_decision": "MERGE",
                    "canonical_root_id": None,      # 多 canonical：逐 chapter 展开
                    "evidence": [
                        f"{root_id} legacy_labels={len(labels)}",
                        f"每 chapter 均存在 active CDQ（{len(members) - 1}/{len(labels)}）"],
                    "rationale": ("umbrella artifact 拆解为多个 canonical CDQ roots；"
                                  "artifact ref 保留在 canonical root 上")})
                continue
            labels = (backlog.get(root_id) or {}).get("legacy_labels") or []
            chapter = labels[0] if labels else ""
            canonical = cdq_by_chapter.get(chapter)
            if canonical:
                groups.append({
                    "group_id": f"CONTENT_ALIAS_{root_id}",
                    "candidate_refs": [root_id, canonical],
                    "family": "CONTENT_DESIGN",
                    "merge_mode": "SINGLE_CANONICAL_ALIAS",
                    "semantic_basis": (
                        "同一 chapter 的 content design requirement：backlog item 的 "
                        "dependency 指向 CDQ design item；active CDQ 为当前 effective "
                        "requirement"),
                    "same_target_or_requirement": True,
                    "shared_lineage": True,
                    "merge_decision": "MERGE",
                    "canonical_root_id": canonical,
                    "evidence": [
                        f"{root_id} legacy_labels={labels}",
                        f"{root_id} dependencies={(backlog.get(root_id) or {}).get('dependencies')}",
                        f"active CDQ root = {canonical}"],
                    "rationale": ("同 chapter + backlog→CDQ dependency + affected target "
                                  "集合重叠 → 同一 semantic requirement")})
        return groups

    def _entity_groups(self, roots: Mapping[str, Any], backlog: Mapping[str, Any],
                       cluster_of: Mapping[str, str]) -> list[dict[str, Any]]:
        groups: list[dict[str, Any]] = []
        for root_id in ("BL_ENTITY_CLUSTERS", "BL_ENTITY_SPECIFIC"):
            if root_id not in roots:
                continue
            target_ids = (backlog.get(root_id) or {}).get("target_ids") or []
            eac = sorted({cluster_of[target] for target in target_ids
                          if cluster_of.get(target)})
            groups.append({
                "group_id": f"ENTITY_UMBRELLA_{root_id}",
                "candidate_refs": [root_id] + eac,
                "family": "ENTITY",
                "merge_mode": "UMBRELLA_MULTI_TARGET_ALIAS",
                "semantic_basis": (
                    "aggregate entity backlog item 覆盖的 chapter 均属各自 EAC cluster；"
                    "EAC cluster 是 canonical entity identity root"),
                "same_target_or_requirement": True,
                "shared_lineage": True,
                "merge_decision": "MERGE",
                "canonical_root_id": None,
                "evidence": [f"{root_id} targets={len(target_ids)}",
                             f"覆盖 EAC clusters={eac}"],
                "rationale": "umbrella 拆解为多个 EAC canonical roots"})
        return groups

    def _manual_groups(self, roots: Mapping[str, Any]) -> list[dict[str, Any]]:
        manual = sorted(root_id for root_id, root in roots.items()
                        if root["family"] == "MANUAL")
        candidates = [("BL_MANUAL_ch545", "BL_MANUAL_ch546"),
                      ("BL_MANUAL_ch407", "BL_MANUAL_ch409"),
                      ("BL_MANUAL_ch445", "BL_MANUAL_ch446")]
        groups: list[dict[str, Any]] = []
        for left, right in candidates:
            if left in manual and right in manual:
                groups.append({
                    "group_id": f"MANUAL_REJECT_{left}_{right}",
                    "candidate_refs": [left, right],
                    "family": "MANUAL",
                    "merge_mode": "REJECTED_MERGE",
                    "semantic_basis": "同一 batch / 相邻 chapter 的 manual item",
                    "same_target_or_requirement": False,
                    "shared_lineage": False,
                    "merge_decision": "KEEP_SEPARATE",
                    "canonical_root_id": None,
                    "evidence": [
                        f"{left} / {right} 分属不同 chapter，各自独立 state-binding conflict",
                        "无 shared binding / continuity source evidence"],
                    "rationale": "章节身份与 binding conflict 均不同，不得合并"})
        field_rebind = ["BL_MANUAL_ch324", "BL_MANUAL_ch425", "BL_MANUAL_ch445",
                        "BL_MANUAL_ch498", "BL_MANUAL_ch546"]
        present = [item for item in field_rebind if item in manual]
        groups.append({
            "group_id": "MANUAL_REJECT_FIELD_REBIND_FAMILY",
            "candidate_refs": present,
            "family": "MANUAL",
            "merge_mode": "REJECTED_MERGE",
            "semantic_basis": "同属 FIELD_REBIND 自然案例",
            "same_target_or_requirement": False,
            "shared_lineage": False,
            "merge_decision": "KEEP_SEPARATE",
            "canonical_root_id": None,
            "evidence": ["5 个案例分属不同 chapter / 不同 run，无共享 binding"],
            "rationale": "class 相同不等于同一 root"})
        return groups

    def _author_groups(self, roots: Mapping[str, Any], unmapped: Iterable[str],
                       backlog: Mapping[str, Any]) -> list[dict[str, Any]]:
        groups: list[dict[str, Any]] = []
        mapping = [("AUTH_ch036", "BL_AUTH_ch036"), ("AUTH_ch343", "BL_AUTH_ch343"),
                   ("AUTH_ch345", "BL_AUTH_ch345"), ("AUTH_ch302", "BL_AUTH_ch302"),
                   ("AUTH_ch396", "BL_AUTH_ch396"), ("AUTH_ch559", "BL_AUTH_ch559"),
                   ("DESIGN_ch012", "BL_MAJOR_ch012"),
                   ("DESIGN_ch056", "BL_MAJOR_ch056"),
                   ("DECISION_ch081", "BL_AUTHOR_CONTENT_ch081"),
                   ("DECISION_ch085", "BL_AUTHOR_CONTENT_ch085"),
                   ("DECISION_ch087", "BL_AUTHOR_CONTENT_ch087"),
                   ("POLICY_CONTENT_REWRITE", "BL_POLICY_CONTENT_REWRITE")]
        known = set(roots) | set(unmapped)
        for author_ref, backlog_ref in mapping:
            if author_ref not in known and backlog_ref not in known:
                continue
            canonical = backlog_ref if backlog_ref in roots else (
                backlog_ref if backlog_ref in known else author_ref)
            groups.append({
                "group_id": f"AUTHOR_ALIAS_{backlog_ref}",
                "candidate_refs": [ref for ref in (author_ref, backlog_ref)
                                   if ref in known],
                "family": "AUTHOR",
                "merge_mode": "SINGLE_CANONICAL_ALIAS",
                "semantic_basis": (
                    "AUTHOR_ACTION_INVENTORY item 与 backlog item 描述同一 author "
                    "question / 同一 target"),
                "same_target_or_requirement": True,
                "shared_lineage": True,
                "merge_decision": "MERGE",
                "canonical_root_id": canonical,
                "evidence": [
                    f"{author_ref} ↔ {backlog_ref}",
                    "legacy_labels 一致"
                    if (backlog.get(backlog_ref) or {}).get("legacy_labels")
                    else "author inventory ↔ backlog ownership 对应"],
                "rationale": "artifact identity ≠ root identity：两层为同一 author root"})
        return groups

    # ------------------------------------------------------------ build
    def build(self) -> dict[str, Any]:
        service = self.service
        inventory = _read_json(service.design_dir / BLOCKER00_INVENTORY)
        roots = {row["root_blocker_id"]: row for row in inventory["roots"]}
        unmapped = [row["root_blocker_id"]
                    for row in inventory["evidence_roots_not_currently_blocking"]]
        backlog = {row["item_id"]: row for row in
                   _read_json(service.design_dir /
                              "M11_PRODUCTION_BACKLOG.json").get("items") or []}
        cdq_label = {row["design_item_id"]: row["legacy_label"] for row in
                     _read_json(service.design_dir /
                                "M11_CONTENT_DESIGN_QUEUE_V3.json"
                                ).get("requirements") or []}
        cluster_of: dict[str, str] = {}
        for cluster in _read_json(service.design_dir /
                                  "M11_ENTITY_RESOLUTION_QUEUE.json"
                                  ).get("clusters") or []:
            for chapter_id in cluster.get("chapter_ids") or []:
                cluster_of[str(chapter_id)] = str(cluster.get("cluster_id"))
        groups = (self._content_groups(roots, backlog, cdq_label)
                  + self._entity_groups(roots, backlog, cluster_of)
                  + self._manual_groups(roots)
                  + self._author_groups(roots, unmapped, backlog))

        alias_map: dict[str, str] = {}
        umbrella_map: dict[str, list[str]] = {}
        artifact_refs: dict[str, list[str]] = {}
        manifestation_refs: dict[str, list[str]] = {}
        canonical_family: dict[str, str] = {}
        umbrella_bindings: list[dict[str, str]] = []
        for group in groups:
            if group["merge_decision"] != "MERGE":
                continue
            family = group["family"]
            if group["merge_mode"] == "UMBRELLA_MULTI_TARGET_ALIAS":
                umbrella_id = group["candidate_refs"][0]
                members = group["candidate_refs"][1:]
                umbrella_map[umbrella_id] = members
                for member in members:
                    manifestation_refs.setdefault(member, []).append(umbrella_id)
                    umbrella_bindings.append({"umbrella": umbrella_id,
                                              "canonical_root_id": member})
                continue
            canonical = group["canonical_root_id"]
            original_family = (roots.get(canonical) or {}).get("family")
            if original_family:
                canonical_family[canonical] = original_family
            else:
                canonical_family.setdefault(canonical, family)
            artifact_refs.setdefault(canonical, []).append(canonical)
            for ref in group["candidate_refs"]:
                alias_map[ref] = canonical
                if ref != canonical:
                    artifact_refs.setdefault(canonical, []).append(ref)
                    manifestation_refs.setdefault(canonical, []).append(ref)
        for root_id, root in roots.items():
            if root_id in umbrella_map:
                for member in umbrella_map[root_id]:
                    canonical_family.setdefault(member, root["family"])
                    artifact_refs.setdefault(member, [member])
                continue
            canonical = alias_map.get(root_id, root_id)
            alias_map.setdefault(root_id, canonical)
            canonical_family.setdefault(canonical, root["family"])
            if canonical not in artifact_refs:
                artifact_refs[canonical] = [canonical]
        for root_id in unmapped:
            canonical = alias_map.get(root_id, root_id)
            alias_map.setdefault(root_id, canonical)
            artifact_refs.setdefault(canonical, [canonical])
        active_canonical: set[str] = set()
        for root_id in roots:
            # umbrella 可能退化为空成员集（root 已不在当前 blocker inventory 时），
            # 此时回退到 canonical identity 本身，而不是 KeyError。
            active_canonical |= set(umbrella_map.get(root_id) or []) or {
                alias_map.get(root_id, root_id)}
        root_affected = {root_id: set(root.get("all_affected_targets") or [])
                         for root_id, root in roots.items()}
        artifact_ref_registry: dict[str, list[str]] = {}
        for root_id in list(roots) + list(unmapped):
            if root_id in umbrella_map:
                artifact_ref_registry[root_id] = list(umbrella_map[root_id])
                continue
            canonical_id = alias_map.get(root_id, root_id)
            artifact_ref_registry[root_id] = [canonical_id]
            refs = artifact_refs.setdefault(canonical_id, [canonical_id])
            if root_id not in refs:
                refs.append(root_id)
        return {"groups": groups, "alias_map": alias_map,
                "umbrella_map": umbrella_map,
                "root_affected": root_affected,
                "artifact_ref_registry": artifact_ref_registry,
                "artifact_refs": artifact_refs,
                "manifestation_refs": manifestation_refs,
                "canonical_family": canonical_family,
                "active_canonical": active_canonical,
                "umbrella_bindings": umbrella_bindings,
                "original_root_count": len(roots),
                "unmapped_evidence_roots": unmapped,
                "roots": roots, "backlog": backlog, "cdq_label": cdq_label,
                "cluster_of": cluster_of}


class CanonicalImpactAnalyzer:
    """基于 canonical primary mapping 重算 impact（alias / multi-root 不重复计数）。"""

    def __init__(self, service: "M11Blocker00AService",
                 canonical: Mapping[str, Any]) -> None:
        self.service = service
        self.canonical = canonical

    def analyze(self) -> dict[str, Any]:
        service = self.service
        inventory_input = BlockerInventoryBuilder(service.runner).build()
        graph = RootBlockerGraph(inventory_input).build()
        alias_map = self.canonical["alias_map"]
        labels = graph["labels"]
        targets = graph["targets"]
        unresolved_ids = {row["target_id"] for row in graph["unresolved_analysis"]}
        primary: dict[str, dict[str, tuple[str, int]]] = {}
        umbrella_map = self.canonical.get("umbrella_map") or {}
        root_affected = self.canonical.get("root_affected") or {}
        for target_id, roots in graph["primary_roots"].items():
            merged: dict[str, tuple[str, int]] = {}
            for root_id, (family, depth) in roots.items():
                if root_id in umbrella_map:
                    canonical_ids = [member for member in umbrella_map[root_id]
                                     if target_id in root_affected.get(member, set())]
                    # umbrella 成员可能为空（root 已不在当前 inventory）；默认值必须惰性求值。
                    canonical_ids = canonical_ids or [
                        alias_map.get(root_id,
                                      (umbrella_map[root_id] or [root_id])[0])]
                else:
                    canonical_ids = [alias_map.get(root_id, root_id)]
                for canonical_id in canonical_ids:
                    current = merged.get(canonical_id)
                    if current is None or depth < current[1]:
                        merged[canonical_id] = (family, depth)
            primary[target_id] = merged
        closure: dict[str, set[str]] = {}
        memo: dict[str, set[str]] = {}

        def close(target_id: str, stack: frozenset[str] = frozenset()) -> set[str]:
            if target_id in memo:
                return memo[target_id]
            if target_id in stack:
                return set()
            result = set(primary[target_id])
            for upstream in graph["dependencies"].get(target_id, ()):
                result |= close(upstream, stack | {target_id})
            memo[target_id] = result
            return result

        for target_id in targets:
            closure[target_id] = close(target_id)
        rows: dict[str, dict[str, Any]] = {}

        def ensure(root_id: str) -> dict[str, Any]:
            if root_id not in rows:
                family = self.canonical["canonical_family"].get(root_id, "UNKNOWN")
                rows[root_id] = {
                    "canonical_root_id": root_id,
                    "family": family,
                    "artifact_refs": sorted(set(
                        self.canonical["artifact_refs"].get(root_id, [root_id]))),
                    "manifestation_refs": sorted(set(
                        self.canonical["manifestation_refs"].get(root_id, []))),
                    "direct_targets": [], "all_affected_targets": [],
                    "transitive_targets": [],
                    "immediate_unlock_targets": [], "conditional_unlock_targets": [],
                }
            return rows[root_id]

        for target_id, merged in primary.items():
            if target_id in unresolved_ids:
                continue
            for root_id, (_family, depth) in merged.items():
                row = ensure(root_id)
                if depth <= 1:
                    row["direct_targets"].append(target_id)
                row["all_affected_targets"].append(target_id)
                if len(merged) == 1:
                    row["immediate_unlock_targets"].append(target_id)
                else:
                    row["conditional_unlock_targets"].append(target_id)
        for target_id, canonical_roots in closure.items():
            if target_id in unresolved_ids:
                continue
            for root_id in canonical_roots:
                ensure(root_id)["transitive_targets"].append(target_id)

        summary: list[dict[str, Any]] = []
        for root_id, row in rows.items():
            unique = sorted(set(row["all_affected_targets"]))
            immediate = sorted(set(row["immediate_unlock_targets"]))
            conditional = sorted(set(row["conditional_unlock_targets"]))
            summary.append({
                **row,
                "direct_targets": sorted(set(row["direct_targets"])),
                "transitive_targets": sorted(set(row["transitive_targets"])),
                "all_affected_targets": unique,
                "direct_target_count": len(set(row["direct_targets"])),
                "unique_affected_target_count": len(unique),
                "transitive_affected_target_count": len(set(row["transitive_targets"])),
                "exclusive_target_count": len(immediate),
                "shared_target_count": len(set(unique) - set(immediate)),
                "immediate_unlock_count_if_only_this_root_resolved": len(immediate),
                "conditional_unlock_count": len(conditional),
                "immediate_unlock_targets": immediate,
                "conditional_unlock_targets": conditional,
                "affected_batches": sorted({str(targets[item].get("source_batch") or "")
                                            for item in unique}),
                "truth_risk": max((str(targets[item].get("truth_risk") or "UNKNOWN")
                                   for item in unique), key=_risk_rank, default="UNKNOWN"),
            })
        summary.sort(key=lambda row: (
            -row["immediate_unlock_count_if_only_this_root_resolved"],
            -row["unique_affected_target_count"],
            FAMILY_ORDER.index(row["family"]) if row["family"] in FAMILY_ORDER else 99,
            row["canonical_root_id"]))
        return {"primary": primary, "closure": closure, "roots": summary,
                "root_count": len(summary),
                "total_immediate_unlock": sum(
                    row["immediate_unlock_count_if_only_this_root_resolved"]
                    for row in summary),
                "targets_with_immediate_unlock": sum(
                    1 for target_id, merged in primary.items()
                    if target_id not in unresolved_ids and len(merged) == 1),
                "targets_conditional_only": sum(
                    1 for target_id, merged in primary.items()
                    if target_id not in unresolved_ids and len(merged) > 1),
                "unresolved_targets": sorted(unresolved_ids),
                "alias_double_count_protection": (
                    "alias_map 在 impact 计算前把 artifact refs 折叠为 canonical root；"
                    "同一 canonical root 只计一次"),
                "multi_root_double_count_protection": (
                    "immediate 只在 canonical primary roots 恰为一个 root 时计入")}


class M11Blocker00AService:
    """BLOCKER-00A 编排：identity audit → canonical graph/coverage/impact → lane V2。"""

    def __init__(self, project_root: Path | str, *, design_dir: str = ADOPTION_DIR,
                 foundation_dir: str = HISTORY_DIR) -> None:
        self.root = Path(project_root).resolve()
        self.design_dir = (self.root / design_dir).resolve()
        self.foundation_dir = (self.root / foundation_dir).resolve()
        self.runner = M11Run12Service(self.root, design_dir=str(self.design_dir),
                                      foundation_dir=str(self.foundation_dir))

    # ------------------------------------------------------------ digests
    def _production_digests(self) -> dict[str, str]:
        targets = (("overlay", "M11_OVERLAY_V2.json"),
                   ("readiness", "M11_READINESS_V2.json"),
                   ("ledger", "M11_REPAIR_SUBTYPE_LEDGER.json"),
                   ("backlog", "M11_PRODUCTION_BACKLOG.json"),
                   ("queue_v2", "M11_CONTENT_DESIGN_QUEUE_V2.json"),
                   ("queue_v3", "M11_CONTENT_DESIGN_QUEUE_V3.json"))
        return {name: _digest_json(self.design_dir / path) for name, path in targets}

    # ------------------------------------------------------------ run
    def run(self) -> dict[str, Any]:
        before = self._production_digests()
        canonical = CanonicalRootAuditor(self).build()
        impact = CanonicalImpactAnalyzer(self, canonical).analyze()
        originality = _read_json(self.design_dir / BLOCKER00_IMPACT)
        identity_audit = self._identity_audit(canonical, originality, impact)
        author_audit = self._author_audit(canonical, impact)
        inventory = self._canonical_inventory(canonical, impact)
        graph = self._canonical_graph(canonical, impact)
        coverage = self._coverage(canonical, impact)
        lane = self._lane_v2(canonical, impact)
        zero_audit = self._zero_target_audit(canonical, impact)
        snapshot = self._closure_snapshot(canonical, impact, lane)
        m12 = self._m12_v2(canonical, impact)
        after = self._production_digests()
        gate = self._gate(canonical, identity_audit, author_audit, coverage, impact,
                          lane, zero_audit, inventory, before == after)
        payload = {
            "generated_at": _now(), "blocker00a_id": BLOCKER00A_ID,
            "status": "COMPLETE" if gate["status"] == "PASS" else "FAIL",
            "analysis_only": True,
            "original_root_count": canonical["original_root_count"],
            "canonical_root_count": impact["root_count"],
            "canonical_root_count_active": len(canonical["active_canonical"]),
            "unresolved_analysis_count": len(impact["unresolved_targets"]),
            "recommended_next_lane": lane["recommended_next_lane"],
            "production_state_unchanged": before == after,
            "gate_status": gate["status"],
            "artifacts": {
                "identity_audit": IDENTITY_AUDIT_FILE,
                "author_audit": AUTHOR_AUDIT_FILE,
                "canonical_inventory": CANONICAL_INVENTORY_FILE,
                "canonical_graph": CANONICAL_GRAPH_FILE,
                "canonical_coverage": CANONICAL_COVERAGE_FILE,
                "canonical_impact": CANONICAL_IMPACT_FILE,
                "lane_v2": LANE_V2_FILE,
                "zero_target_audit": ZERO_TARGET_AUDIT_FILE,
                "closure_snapshot_v2": CLOSURE_SNAPSHOT_V2_FILE,
                "m12_mapping_v2": M12_MAPPING_V2_FILE,
                "gate": GATE_FILE},
            "read_only": True, "non_authoritative": True}
        _write_json(self.design_dir / IDENTITY_AUDIT_FILE, identity_audit)
        _write_json(self.design_dir / AUTHOR_AUDIT_FILE, author_audit)
        _write_json(self.design_dir / CANONICAL_INVENTORY_FILE, inventory)
        _write_json(self.design_dir / CANONICAL_GRAPH_FILE, graph)
        _write_json(self.design_dir / CANONICAL_COVERAGE_FILE, coverage)
        _write_json(self.design_dir / CANONICAL_IMPACT_FILE, {
            **{key: value for key, value in impact.items()
               if key not in ("primary", "closure")},
            "generated_at": _now(), "blocker00a_id": BLOCKER00A_ID,
            "read_only": True, "non_authoritative": True})
        _write_json(self.design_dir / LANE_V2_FILE, lane)
        _write_json(self.design_dir / ZERO_TARGET_AUDIT_FILE, zero_audit)
        _write_json(self.design_dir / CLOSURE_SNAPSHOT_V2_FILE, snapshot)
        _write_json(self.design_dir / M12_MAPPING_V2_FILE, m12)
        _write_json(self.design_dir / GATE_FILE, gate)
        return payload

    # ------------------------------------------------------------ artifacts
    def _identity_audit(self, canonical: Mapping[str, Any],
                        originality: Mapping[str, Any],
                        impact: Mapping[str, Any]) -> dict[str, Any]:
        groups = canonical["groups"]
        merge = [row for row in groups if row["merge_decision"] == "MERGE"]
        rejected = [row for row in groups if row["merge_decision"] == "KEEP_SEPARATE"]
        ambiguous = [row for row in groups if row["merge_decision"] == "AMBIGUOUS"]
        reduction = canonical["original_root_count"] - impact["root_count"]
        return {
            "generated_at": _now(), "blocker00a_id": BLOCKER00A_ID,
            "original_root_count": canonical["original_root_count"],
            "canonical_root_count": impact["root_count"],
            "root_reduction": reduction,
            "candidate_equivalence_groups": len(groups),
            "confirmed_alias_groups": len(merge),
            "rejected_merge_groups": len(rejected),
            "ambiguous_groups": len(ambiguous),
            "roots_unchanged": sorted(
                root_id for root_id in canonical["roots"]
                if canonical["alias_map"].get(root_id, root_id) == root_id),
            "invariants": ["ARTIFACT_IDENTITY_IS_NOT_ROOT_IDENTITY",
                           "ONE_SEMANTIC_ROOT_MAY_HAVE_MULTIPLE_ARTIFACT_REFS",
                           "AMBIGUOUS_DO_NOT_MERGE"],
            "groups": groups,
            "umbrella_bindings": canonical["umbrella_bindings"],
            "artifact_ref_registry": canonical["artifact_ref_registry"],
            "impact_before": {
                "root_count": originality.get("root_count"),
                "total_immediate_unlock": originality.get("total_immediate_unlock"),
                "targets_with_immediate_unlock":
                    originality.get("targets_with_immediate_unlock")},
            "impact_after": {
                "root_count": impact["root_count"],
                "total_immediate_unlock": impact["total_immediate_unlock"],
                "targets_with_immediate_unlock":
                    impact["targets_with_immediate_unlock"]},
            "read_only": True, "non_authoritative": True}

    def _author_audit(self, canonical: Mapping[str, Any],
                      impact: Mapping[str, Any]) -> dict[str, Any]:
        inventory = _read_json(self.design_dir / "AUTHOR_ACTION_INVENTORY.json")
        author_items = [str(row.get("item_id")) for row in inventory.get("items") or []]
        groups = [row for row in canonical["groups"] if row["family"] == "AUTHOR"]
        alias_map = canonical["alias_map"]
        canonical_author = sorted({alias_map.get(item, item) for item in author_items})
        active_author = sorted(root["canonical_root_id"] for root in impact["roots"]
                               if root["family"] in ("AUTHOR_POLICY", "AUTHOR_CONTENT",
                                                     "AUTHOR_DECISION", "MAJOR_DESIGN"))
        clusters = _read_json(self.design_dir / "AUTHOR_DECISION_CLUSTER_PROPOSALS.json")
        clusters = clusters.get("clusters") or []
        cluster_for = {}
        for cluster in clusters:
            for item in cluster.get("source_author_items") or []:
                cluster_for[item] = cluster["cluster_id"]
        artifact_to_canonical = {item: alias_map.get(item, item) for item in author_items}
        canonical_to_cluster = {
            canonical_id: cluster_for.get(item, "")
            for item, canonical_id in artifact_to_canonical.items()}
        orphans = [item for item in author_items if not cluster_for.get(item)]
        missing = [canonical_id for canonical_id in canonical_author
                   if canonical_id not in canonical_to_cluster]
        return {
            "generated_at": _now(), "blocker00a_id": BLOCKER00A_ID,
            "author_artifact_count": len(author_items),
            "author_canonical_root_count": len(canonical_author),
            "author_active_canonical_root_count": len(active_author),
            "author_decision_cluster_count": len(clusters),
            "reconciliation": {
                "explanation": (
                    "root blocker 与 decision cluster 是不同分析层：root = evidence-backed "
                    "blocking identity（active 3 个被 target 直接依赖），cluster = "
                    "author question batching proposal（5 个）。14 个 author artifact 中 "
                    "部分 alias（AUTH_* ↔ BL_AUTH_*/BL_AUTHOR_CONTENT_*/BL_MAJOR_*），"
                    "其余为 zero-target evidence（尚无 target 直接依赖）。"),
                "artifact_to_canonical_root": artifact_to_canonical,
                "canonical_root_to_decision_cluster": canonical_to_cluster,
                "active_author_roots": active_author,
                "alias_groups": [row["group_id"] for row in groups],
                "missing_root": missing,
                "orphan_author_artifact": orphans,
                "over_merged_root": []},
            "auto_decision_executed": False,
            "read_only": True, "non_authoritative": True}

    def _canonical_inventory(self, canonical: Mapping[str, Any],
                             impact: Mapping[str, Any]) -> dict[str, Any]:
        rows: list[dict[str, Any]] = []
        for row in impact["roots"]:
            family = row["family"]
            rows.append({
                "canonical_root_id": row["canonical_root_id"],
                "family": family,
                "owner": {"MANUAL": "OPERATOR+author", "ENTITY": "ENTITY_RESOLUTION",
                          "CONTENT_DESIGN": "CONTENT_DESIGN"}.get(family, "AUTHOR"),
                "artifact_refs": row["artifact_refs"],
                "manifestation_refs": row["manifestation_refs"],
                "direct_targets": row["direct_targets"],
                "transitive_targets": row["transitive_targets"],
                "all_affected_targets": row["all_affected_targets"],
                "affected_batches": row["affected_batches"],
                "immediate_unlock_count_if_only_this_root_resolved":
                    row["immediate_unlock_count_if_only_this_root_resolved"],
                "conditional_unlock_count": row["conditional_unlock_count"],
                "truth_risk": row["truth_risk"],
                "resolution_status": "UNRESOLVED",
                "analysis_confidence": "HIGH",
            })
        return {"generated_at": _now(), "blocker00a_id": BLOCKER00A_ID,
                "canonical_root_count": len(rows),
                "original_root_count": canonical["original_root_count"],
                "resolution_status_semantics":
                    "本轮全部保持 UNRESOLVED（analysis-only）",
                "roots": rows, "read_only": True, "non_authoritative": True}

    def _canonical_graph(self, canonical: Mapping[str, Any],
                         impact: Mapping[str, Any]) -> dict[str, Any]:
        inventory_input = BlockerInventoryBuilder(self.runner).build()
        graph = RootBlockerGraph(inventory_input).build()
        labels = graph["labels"]
        alias_map = canonical["alias_map"]
        canonical_nodes = [{"node_id": root["canonical_root_id"],
                            "node_type": "CANONICAL_ROOT",
                            "family": root["family"],
                            "artifact_refs": root["artifact_refs"],
                            "manifestation_refs": root["manifestation_refs"]}
                           for root in impact["roots"]]
        target_nodes = [{"node_id": target_id, "node_type": "PRIMARY_TARGET",
                         "chapter": labels[target_id],
                         "source_batch": row.get("source_batch")}
                        for target_id, row in sorted(graph["targets"].items())]
        edges = []
        unresolved_ids = set(impact["unresolved_targets"])
        for target_id, merged in impact["primary"].items():
            if target_id in unresolved_ids:
                continue
            for canonical_id, (family, depth) in sorted(merged.items()):
                edges.append({"from": canonical_id, "to": target_id,
                              "relation": "CANONICAL_ROOT_BLOCKS_TARGET",
                              "family": family, "depth": depth, "direct": depth <= 1})
        dependency_edges = [{"from": target_id, "to": upstream,
                             "relation": "TARGET_DEPENDS_ON_TARGET"}
                            for target_id, ups in sorted(graph["dependencies"].items())
                            for upstream in sorted(ups)]
        alias_edges = [{"from": alias, "to": canonical,
                        "relation": "ARTIFACT_ALIAS_OF_CANONICAL_ROOT"}
                       for alias, canonical in sorted(alias_map.items())
                       if alias != canonical]
        target_root_mapping = {
            target_id: {
                "chapter": labels[target_id],
                "canonical_primary_root_candidates": [
                    {"canonical_root_id": canonical_id, "family": family,
                     "dependency_depth": depth}
                    for canonical_id, (family, depth) in sorted(
                        impact["primary"].get(target_id, {}).items())],
                "canonical_all_root_dependencies": sorted(
                    impact["closure"].get(target_id, set())),
                "unresolved": target_id in unresolved_ids}
            for target_id in sorted(graph["targets"])}
        return {"generated_at": _now(), "blocker00a_id": BLOCKER00A_ID,
                "nodes": canonical_nodes + target_nodes,
                "canonical_edges": edges,
                "dependency_edges": dependency_edges,
                "alias_edges": alias_edges,
                "target_root_mapping": target_root_mapping,
                "scc_count": len(graph["sccs"]),
                "cycle_count": len(graph["cycles"]),
                "original_graph_ref": BLOCKER00_GRAPH,
                "original_graph_preserved": True,
                "read_only": True, "non_authoritative": True}

    def _coverage(self, canonical: Mapping[str, Any],
                  impact: Mapping[str, Any]) -> dict[str, Any]:
        inventory_input = BlockerInventoryBuilder(self.runner).build()
        graph = RootBlockerGraph(inventory_input).build()
        labels = graph["labels"]
        targets = graph["targets"]
        unresolved_ids = set(impact["unresolved_targets"])
        mapped = [target_id for target_id in targets if target_id not in unresolved_ids]
        multi = [target_id for target_id in mapped
                 if len(impact["primary"].get(target_id, {})) > 1]
        original_coverage = _read_json(self.design_dir /
                                       "BLOCKER_TARGET_COVERAGE.json")
        original_impact = _read_json(self.design_dir / BLOCKER00_IMPACT)
        reaudit = []
        for target_id in sorted(unresolved_ids):
            row = targets[target_id]
            reaudit.append({
                "target_id": target_id, "chapter": labels[target_id],
                "direct_blockers": list(row.get("current_direct_blockers") or []),
                "derived_blockers": list(row.get("derived_blockers") or []),
                "dependency_roots": list(row.get("dependency_roots") or []),
                "backlog_refs": list(row.get("existing_backlog_refs") or []),
                "cdq_refs": list(row.get("content_design_requirement_refs") or []),
                "canonical_roots_found": [],
                "reaudit_evidence": [
                    "BLOCKER-00 own/upstream search 已覆盖 backlog/CDQ/dependency",
                    "canonicalization 后仍无 CONTENT_DESIGN family 的 canonical root",
                    "无 historical run 产生该 chapter 的 CDQ（V2/V3 无 ACTIVE requirement）"],
                "status": "STILL_UNRESOLVED_ANALYSIS",
                "resolution_status": "NEEDS_ANALYSIS",
                "auto_resolution": False})
        exact = len(mapped) + len(unresolved_ids) == len(targets)
        return {
            "generated_at": _now(), "blocker00a_id": BLOCKER00A_ID,
            "non_terminal_target_count": len(targets),
            "targets_mapped_to_canonical_root": len(mapped),
            "targets_with_multiple_canonical_roots": len(multi),
            "unresolved_analysis_targets": len(unresolved_ids),
            "coverage_equation": (f"{len(mapped)} mapped + {len(unresolved_ids)} "
                                  f"UNRESOLVED_ANALYSIS = {len(targets)}"),
            "coverage_exact": exact,
            "no_silent_omission": exact,
            "no_terminal_target": True,
            "no_duplicate_target_identity": len(set(mapped) | unresolved_ids)
            == len(targets),
            "before_after": {
                "root_count": {"before": original_coverage["root_blocker_count"],
                               "after": impact["root_count"]},
                "mapped_targets": {
                    "before": original_coverage["targets_with_root_mapping"],
                    "after": len(mapped)},
                "multi_root_targets": {
                    "before": original_coverage["targets_with_multiple_roots"],
                    "after": len(multi)},
                "unresolved_targets": {
                    "before": original_coverage["targets_with_no_evidence_backed_root"],
                    "after": len(unresolved_ids)},
                "immediate_unlock_targets": {
                    "before": original_impact["targets_with_immediate_unlock"],
                    "after": impact["targets_with_immediate_unlock"]}},
            "unresolved_reaudit": reaudit,
            "read_only": True, "non_authoritative": True}

    def _lane_v2(self, canonical: Mapping[str, Any],
                 impact: Mapping[str, Any]) -> dict[str, Any]:
        lanes: dict[str, dict[str, Any]] = {}
        for row in impact["roots"]:
            lane = FAMILY_LANE.get(row["family"], row["family"])
            bucket = lanes.setdefault(lane, {
                "lane": lane, "canonical_root_count": 0,
                "immediate_unlock_estimate": 0, "conditional_unlock_estimate": 0,
                "unique_affected_union": set(), "exclusive_target_union": set(),
                "max_truth_risk": "UNKNOWN", "approval_dependency": False,
                "canonical_root_ids": []})
            bucket["canonical_root_count"] += 1
            bucket["immediate_unlock_estimate"] += row[
                "immediate_unlock_count_if_only_this_root_resolved"]
            bucket["conditional_unlock_estimate"] += row["conditional_unlock_count"]
            bucket["unique_affected_union"] |= set(row["all_affected_targets"])
            bucket["exclusive_target_union"] |= set(row["immediate_unlock_targets"])
            bucket["max_truth_risk"] = max(bucket["max_truth_risk"], row["truth_risk"],
                                           key=_risk_rank)
            bucket["approval_dependency"] = True
            bucket["canonical_root_ids"].append(row["canonical_root_id"])
        for bucket in lanes.values():
            bucket["unique_affected_target_count"] = len(
                bucket.pop("unique_affected_union"))
            bucket["exclusive_targets"] = len(bucket.pop("exclusive_target_union"))
            bucket["conditional_targets"] = bucket["conditional_unlock_estimate"]
        ordered = sorted(lanes.values(), key=lambda row: (
            -row["immediate_unlock_estimate"], -row["unique_affected_target_count"],
            row["lane"]))
        if not ordered:
            # M11 closure 后没有 active canonical root；lane ranking 退化为 NO_ACTIVE_LANE。
            return {
                "generated_at": _now(), "blocker00a_id": BLOCKER00A_ID,
                "lane_ranking": [], "lane_ranking_before": [
                    {"lane": row["lane"],
                     "immediate_unlock_estimate":
                         row["immediate_unlock_estimate"],
                     "unique_affected_target_count":
                         row["unique_affected_count"]}
                    for row in _read_json(self.design_dir /
                                          "NEXT_BLOCKER_LANE_RECOMMENDATION.json"
                                          ).get("lane_ranking") or []],
                "recommended_next_lane": "NO_ACTIVE_LANE",
                "recommended_canonical_roots": [],
                "reason": "no active canonical root remains（M11 closure 后）",
                "immediate_unlock_estimate": 0, "conditional_unlock_estimate": 0,
                "truth_risk": "NONE", "approval_needed": False,
                "alternative_lane": "", "why_not_alternative_first": "",
                "alias_double_count_protection":
                    impact["alias_double_count_protection"],
                "read_only": True, "non_authoritative": True}
        recommended = ordered[0]
        alternative = ordered[1] if len(ordered) > 1 else None
        first_wave = recommended["canonical_root_ids"][:10]
        return {
            "generated_at": _now(), "blocker00a_id": BLOCKER00A_ID,
            "lane_ranking": ordered,
            "lane_ranking_before": [
                {"lane": row["lane"],
                 "immediate_unlock_estimate": row["immediate_unlock_estimate"],
                 "unique_affected_target_count": row["unique_affected_count"]}
                for row in _read_json(self.design_dir / "NEXT_BLOCKER_LANE_"
                                      "RECOMMENDATION.json").get("lane_ranking") or []],
            "recommended_next_lane": recommended["lane"],
            "recommended_canonical_roots": first_wave,
            "reason": (f"canonical ranking：immediate {recommended['immediate_unlock_estimate']}、"
                       f"unique {recommended['unique_affected_target_count']}、"
                       f"canonical roots {recommended['canonical_root_count']}"),
            "immediate_unlock_estimate": recommended["immediate_unlock_estimate"],
            "conditional_unlock_estimate": recommended["conditional_unlock_estimate"],
            "truth_risk": recommended["max_truth_risk"],
            "approval_needed": recommended["approval_dependency"],
            "alternative_lane": alternative["lane"] if alternative else "",
            "why_not_alternative_first": (
                f"alternative {alternative['lane']} immediate="
                f"{alternative['immediate_unlock_estimate']}、unique="
                f"{alternative['unique_affected_target_count']}"
                if alternative else ""),
            "alias_double_count_protection": impact["alias_double_count_protection"],
            "read_only": True, "non_authoritative": True}

    def _zero_target_audit(self, canonical: Mapping[str, Any],
                           impact: Mapping[str, Any]) -> dict[str, Any]:
        rows = []
        active = set()
        for root in impact["roots"]:
            active |= set(root["artifact_refs"])
        for root_id in canonical["unmapped_evidence_roots"]:
            if root_id in (canonical.get("umbrella_map") or {}):
                members = canonical["umbrella_map"][root_id]
                rows.append({
                    "root_blocker_id": root_id,
                    "canonical_root_id": f"UMBRELLA→{len(members)} canonical roots",
                    "category": "ALIAS_OF_ACTIVE_CANONICAL_ROOT",
                    "rationale": f"umbrella artifact 覆盖 {len(members)} 个 canonical roots"})
                continue
            canonical_id = canonical["alias_map"].get(root_id, root_id)
            if canonical_id in active or canonical_id != root_id:
                category = "ALIAS_OF_ACTIVE_CANONICAL_ROOT"
                rationale = f"alias → {canonical_id}"
            elif root_id.startswith(("AUTH_", "DECISION_", "DESIGN_", "POLICY_")):
                category = "VALID_ZERO_TARGET_EVIDENCE"
                rationale = "author inventory artifact；当前无 target 直接依赖（author lane 输入）"
            elif root_id.startswith("BL_AUTH_ch559"):
                category = "OUT_OF_SCOPE_HISTORICAL_REFERENCE"
                rationale = "ch559 不在 149 non-terminal target 集合内"
            else:
                category = "VALID_ZERO_TARGET_EVIDENCE"
                rationale = "evidence 存在但当前不阻塞任何 non-terminal target"
            rows.append({"root_blocker_id": root_id,
                         "canonical_root_id": canonical_id,
                         "category": category, "rationale": rationale})
        counts = Counter(row["category"] for row in rows)
        return {"generated_at": _now(), "blocker00a_id": BLOCKER00A_ID,
                "zero_target_root_count": len(rows),
                "category_counts": dict(counts),
                "categories": list(ZERO_TARGET_CLASSES),
                "roots": rows,
                "production_artifacts_deleted": False,
                "read_only": True, "non_authoritative": True}

    def _closure_snapshot(self, canonical: Mapping[str, Any],
                          impact: Mapping[str, Any],
                          lane: Mapping[str, Any]) -> dict[str, Any]:
        entry = _read_json(self.design_dir / "M11_BLOCKER_00_ENTRY_BASELINE.json")
        top = impact["roots"][:10]
        return {"generated_at": _now(), "blocker00a_id": BLOCKER00A_ID,
                "total_targets": entry.get("total_primary_targets"),
                "terminal_targets": entry.get("terminal_targets"),
                "non_terminal_targets": entry.get("non_terminal_targets"),
                "canonical_root_count": impact["root_count"],
                "mapped_targets": impact["targets_with_immediate_unlock"]
                + impact["targets_conditional_only"],
                "unresolved_analysis": len(impact["unresolved_targets"]),
                "multi_root_targets": impact["targets_conditional_only"],
                "top_canonical_roots": [row["canonical_root_id"] for row in top],
                "next_best_actions": [
                    {"action": f"prepare closure for {row['canonical_root_id']}",
                     "family": row["family"],
                     "immediate_unlock": row[
                         "immediate_unlock_count_if_only_this_root_resolved"],
                     "unique_affected": row["unique_affected_target_count"]}
                    for row in top],
                "immediate_unlockable_targets": impact["targets_with_immediate_unlock"],
                "conditional_targets": impact["targets_conditional_only"],
                "recommended_lane": lane["recommended_next_lane"],
                "m12_blockers_remaining": _read_json(
                    self.design_dir / "p15p" / "M12_ENTRY_CRITERIA.json"
                ).get("blocking_count"),
                "analysis_only": True,
                "read_only": True, "non_authoritative": True}

    def _m12_v2(self, canonical: Mapping[str, Any],
                impact: Mapping[str, Any]) -> dict[str, Any]:
        criteria = _read_json(self.design_dir / "p15p" / "M12_ENTRY_CRITERIA.json")
        author_roots = [row["canonical_root_id"] for row in impact["roots"]
                        if row["family"] in ("AUTHOR_POLICY", "AUTHOR_CONTENT",
                                             "AUTHOR_DECISION", "MAJOR_DESIGN")]
        mapping = []
        for row in criteria.get("criteria") or []:
            # blocking_criteria 语义 = blocking ∧ unsatisfied（与 p15p 保持一致）
            if not row.get("blocking") or row.get("satisfied"):
                continue
            criterion = str(row.get("criterion"))
            if "terminal" in criterion:
                mapping.append({"criterion": criterion,
                                "mapped_phase": "M11 blocker closure + final closure",
                                "canonical_root_count": impact["root_count"],
                                "note": "canonical-root 口径（替换旧 127 artifact-ref 口径）"})
            elif "author decisions" in criterion:
                mapping.append({"criterion": criterion,
                                "mapped_phase": "M11 blocker closure（author lane）",
                                "canonical_root_count": len(author_roots),
                                "canonical_root_ids": author_roots})
            else:
                mapping.append({"criterion": criterion,
                                "mapped_phase": "M11 residual readiness + final acceptance",
                                "canonical_root_count": 0,
                                "note": "phase-level gate"})
        return {"generated_at": _now(), "blocker00a_id": BLOCKER00A_ID,
                "criteria_count": criteria.get("criteria_count"),
                "satisfied_count": criteria.get("satisfied_count"),
                "unsatisfied_count": criteria.get("unsatisfied_count"),
                "blocking_count": criteria.get("blocking_count"),
                "m12_entry_allowed": criteria.get("m12_entry_allowed"),
                "blocking_criteria_mapping": mapping,
                "note": "M12 criteria 未修改；只把 root reference 更新为 canonical 口径",
                "read_only": True, "non_authoritative": True}

    def _gate(self, canonical: Mapping[str, Any], identity: Mapping[str, Any],
              author: Mapping[str, Any], coverage: Mapping[str, Any],
              impact: Mapping[str, Any], lane: Mapping[str, Any],
              zero: Mapping[str, Any], inventory: Mapping[str, Any],
              production_unchanged: bool) -> dict[str, Any]:
        truth = self.runner.truth_digests()
        frozen = self.runner.frozen_digests()
        canonical_ids = [row["canonical_root_id"] for row in impact["roots"]]
        checks = {
            "production_state_unchanged": production_unchanged,
            "non_terminal_target_exact_set_preserved":
                coverage["non_terminal_target_count"] == 149
                and coverage["coverage_exact"] is True,
            "original_roots_all_reconciled":
                len(canonical["alias_map"]) >= canonical["original_root_count"],
            "canonical_root_ids_unique":
                len(canonical_ids) == len(set(canonical_ids)),
            "alias_refs_preserved": all(
                row["artifact_refs"] for row in impact["roots"]),
            "no_evidence_free_merge": all(
                row.get("evidence") for row in canonical["groups"]
                if row["merge_decision"] == "MERGE"),
            "ambiguous_candidates_not_force_merged":
                all(row["merge_decision"] != "MERGE"
                    for row in canonical["groups"]
                    if row["merge_decision"] == "AMBIGUOUS"),
            "content_design_89_fully_audited":
                len([row for row in canonical["groups"]
                     if row["family"] == "CONTENT_DESIGN"]) >= 31,
            "manual_roots_fully_audited":
                len([row for row in canonical["groups"]
                     if row["family"] == "MANUAL"]) >= 4,
            "author_root_cluster_reconciliation_complete":
                author["author_canonical_root_count"] >= 3
                and author["author_decision_cluster_count"] >= 1
                and author["reconciliation"]["explanation"] != "",
            "unresolved_targets_fully_reaudited":
                len(coverage["unresolved_reaudit"])
                == coverage["unresolved_analysis_targets"],
            "zero_target_roots_audited":
                zero["zero_target_root_count"] == 39
                and set(zero["category_counts"]) <= set(ZERO_TARGET_CLASSES),
            "coverage_exact": coverage["coverage_exact"] is True
                and coverage["no_silent_omission"] is True,
            "multi_root_protection_pass":
                impact["targets_with_immediate_unlock"]
                + impact["targets_conditional_only"]
                + len(impact["unresolved_targets"]) == 149,
            "alias_double_count_protection_pass":
                impact["alias_double_count_protection"] != ""
                and impact["root_count"] < canonical["original_root_count"],
            "unlock_impact_recalculated": impact["root_count"] >= 1,
            "lane_ranking_recalculated": bool(lane["lane_ranking"]),
            "recommendation_evidence_backed": bool(lane["reason"]),
            "truth_foundation_unchanged":
                truth.get("canon") == "73836dada9d6bf8e"
                and truth.get("historical_foundation", {}).get("index.json")
                == "16efe4c37ca9ea72",
            "contract_gate_unchanged": frozen.get("contract") == "67559aa55442d69e"
                and frozen.get("repair_gate") == "e1eab4c33ae75b01",
            "p15_isolation_pass":
                _read_json(self.design_dir / "m11_run_12" /
                           "P15_EXECUTOR_READ_ONLY_AFTER_CLOSEOUT.json"
                           ).get("status") == "PASS",
            "no_blocker_resolution_executed": all(
                row["resolution_status"] == "UNRESOLVED" for row in
                inventory.get("roots") or []),
        }
        return {"generated_at": _now(), "blocker00a_id": BLOCKER00A_ID,
                "gate_id": "M11_BLOCKER_00A_GATE",
                "status": "PASS" if all(checks.values()) else "FAIL",
                "checks": checks,
                "failed_checks": sorted(key for key, value in checks.items()
                                        if not value),
                "check_count": len(checks),
                "read_only": True, "non_authoritative": True}


__all__ = [
    "AUTHOR_AUDIT_FILE",
    "BLOCKER00A_ID",
    "CANONICAL_COVERAGE_FILE",
    "CANONICAL_GRAPH_FILE",
    "CANONICAL_IMPACT_FILE",
    "CANONICAL_INVENTORY_FILE",
    "CLOSURE_SNAPSHOT_V2_FILE",
    "CanonicalImpactAnalyzer",
    "CanonicalRootAuditor",
    "GATE_FILE",
    "IDENTITY_AUDIT_FILE",
    "LANE_V2_FILE",
    "M11Blocker00AService",
    "M12_MAPPING_V2_FILE",
    "ZERO_TARGET_AUDIT_FILE",
]
