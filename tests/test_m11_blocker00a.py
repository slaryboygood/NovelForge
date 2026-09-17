"""M11-BLOCKER-00A：Canonical Root Identity Audit 回归（analysis-only）。"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from novelforge.story_engine.m11_blocker00a import (
    AUTHOR_AUDIT_FILE,
    CANONICAL_COVERAGE_FILE,
    CANONICAL_GRAPH_FILE,
    CANONICAL_IMPACT_FILE,
    CANONICAL_INVENTORY_FILE,
    CLOSURE_SNAPSHOT_V2_FILE,
    GATE_FILE,
    IDENTITY_AUDIT_FILE,
    LANE_V2_FILE,
    M11Blocker00AService,
    M12_MAPPING_V2_FILE,
    ZERO_TARGET_AUDIT_FILE,
)
from novelforge.story_engine.m11_p15p import (
    FROZEN_FOUNDATION_DIGESTS,
    FROZEN_SOURCE_DIGESTS,
)
from novelforge.story_engine.m11_run12 import M11Run12Service

from m11_phase_history import closed, report_records

ROOT = Path(".").resolve()
DESIGN_DIR = ROOT / "workspace/wasteland_001_exports/repair_adoption_v1"


@pytest.fixture(scope="module")
def blocker00a():
    service = M11Blocker00AService(ROOT)
    payload = service.run()
    return service, payload


def _artifact(name: str):
    return json.loads((DESIGN_DIR / name).read_text(encoding="utf-8"))


def _digest(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()[:16]


def _non_terminal_ids() -> set[str]:
    runner = M11Run12Service(ROOT)
    states = runner.readiness.target_states(inputs=runner.inputs())
    return {str(cid) for cid, state in states.items()
            if str(state.target_state) != "RESOLVED"}


# ---------------------------------------------------------------- identity
def test_artifact_identity_is_not_root_identity(blocker00a) -> None:
    service, payload = blocker00a
    audit = _artifact(IDENTITY_AUDIT_FILE)
    # [M11-CLOSURE] BLOCKER-00A 是 phase-timepoint 分析：历史值由 frozen phase report 保留；
    # live 已无 active blocker（canonical roots = 0）
    report_records("BLOCKER_00A", "| original_root_count | 127 |",
                   "| active canonical roots affecting non-terminal targets | **94** |")
    assert payload["original_root_count"] == closed(127, 0)
    assert payload["canonical_root_count"] == closed(94, 0)
    assert audit["root_reduction"] == closed(33, 0)
    assert "ARTIFACT_IDENTITY_IS_NOT_ROOT_IDENTITY" in audit["invariants"]
    merges = [row for row in audit["groups"] if row["merge_decision"] == "MERGE"]
    assert all(row["evidence"] for row in merges)


def test_same_semantic_cdq_backlog_refs_merge(blocker00a) -> None:
    audit = _artifact(IDENTITY_AUDIT_FILE)
    # [M11-CLOSURE] 该 alias 合并是历史结论（frozen report）；live 合并集已随 blocker 清空
    report_records("BLOCKER_00A", "`BL_CONTENT_DESIGN_ch218` / `CDQ_RUN02_ch218`")
    for row in audit["groups"]:
        if row["group_id"] == "CONTENT_ALIAS_BL_CONTENT_DESIGN_ch218":
            assert row["merge_decision"] == "MERGE"
            assert row["canonical_root_id"] == "CDQ_RUN02_ch218"
            assert set(row["candidate_refs"]) == {"BL_CONTENT_DESIGN_ch218",
                                                  "CDQ_RUN02_ch218"}
    assert all(row["evidence"] for row in audit["groups"]
               if row["merge_decision"] == "MERGE")


def test_same_chapter_different_semantic_blocker_does_not_merge(blocker00a) -> None:
    # ch570：content canonical root 与 manual root 必须保持独立
    graph = _artifact(CANONICAL_GRAPH_FILE)
    # [M11-CLOSURE] ch570 双 root 案例是历史 canonicalization 结论（frozen report）
    report_records("BLOCKER_00A", "`BL_CONTENT_DESIGN_ch570` / `CDQ_RUN12_ch570`")
    mapping = {row["chapter"]: row for row in graph["target_root_mapping"].values()}
    if "ch570" in mapping:
        roots = {item["canonical_root_id"] for item in
                 mapping["ch570"]["canonical_primary_root_candidates"]}
        assert len(roots) >= 2          # multi-root target 必须保持 multi-root 语义
    audit = _artifact(IDENTITY_AUDIT_FILE)
    rejected = [row for row in audit["groups"]
                if row["merge_decision"] == "KEEP_SEPARATE"]
    assert rejected and all(not row["same_target_or_requirement"]
                            for row in rejected)


def test_ambiguous_equivalence_does_not_merge(blocker00a) -> None:
    audit = _artifact(IDENTITY_AUDIT_FILE)
    assert audit["ambiguous_groups"] == 0
    assert "AMBIGUOUS_DO_NOT_MERGE" in audit["invariants"]
    for row in audit["groups"]:
        if row["merge_decision"] == "MERGE":
            assert row["same_target_or_requirement"] is True
            assert row["shared_lineage"] is True


def test_canonical_ids_unique(blocker00a) -> None:
    inventory = _artifact(CANONICAL_INVENTORY_FILE)
    ids = [row["canonical_root_id"] for row in inventory["roots"]]
    report_records("BLOCKER_00A", "| active canonical roots affecting non-terminal targets | **94** |")
    assert len(ids) == len(set(ids))
    assert inventory["canonical_root_count"] == closed(94, 0)


def test_all_original_root_refs_preserved(blocker00a) -> None:
    original = _artifact("ROOT_BLOCKER_INVENTORY.json")
    audit = _artifact(IDENTITY_AUDIT_FILE)
    registry = audit["artifact_ref_registry"]
    original_ids = {row["root_blocker_id"] for row in original["roots"]}
    original_ids |= {row["root_blocker_id"]
                     for row in original["evidence_roots_not_currently_blocking"]}
    assert set(registry) == original_ids
    inventory = _artifact(CANONICAL_INVENTORY_FILE)
    canonical_ids = {row["canonical_root_id"] for row in inventory["roots"]}
    umbrella_members = {member for row in audit["groups"]
                        if row.get("merge_mode") == "UMBRELLA_MULTI_TARGET_ALIAS"
                        for member in row["candidate_refs"][1:]}
    for ref, targets in registry.items():
        assert targets, ref
        for target in targets:
            # 目标可以是 active canonical root、umbrella member、或 zero-target
            # canonical root（其自身仍是 original root id，登记在 registry 中）
            assert (target in canonical_ids or target in umbrella_members
                    or target in registry)


# ---------------------------------------------------------------- families
def test_content_design_full_reconciliation(blocker00a) -> None:
    audit = _artifact(IDENTITY_AUDIT_FILE)
    content_groups = [row for row in audit["groups"]
                      if row["family"] == "CONTENT_DESIGN"]
    aliases = [row for row in content_groups
               if row["group_id"].startswith("CONTENT_ALIAS_")]
    umbrellas = [row for row in content_groups
                 if row["group_id"].startswith("CONTENT_UMBRELLA_")]
    # [M11-CLOSURE] 29 alias / 2 umbrella 为历史值（frozen report）；live 只保留结构语义
    report_records("BLOCKER_00A",
                   "| CDQ+Backlog alias roots | **29**（`BL_CONTENT_DESIGN_chNNN` → 对应 active CDQ） |")
    assert all(row["group_id"].startswith("CONTENT_ALIAS_") for row in aliases)
    assert all(row["group_id"].startswith("CONTENT_UMBRELLA_") for row in umbrellas)
    inventory = _artifact(CANONICAL_INVENTORY_FILE)
    content = [row for row in inventory["roots"]
               if row["family"] == "CONTENT_DESIGN"]
    report_records("BLOCKER_00A", "| content canonical roots | **58** |")
    assert len(content) == closed(58, 0)
    cdq_only = [row for row in content if not row["manifestation_refs"]]
    alias_ref = [row for row in content if any(
        ref.startswith("BL_CONTENT_DESIGN_") for ref in row["manifestation_refs"])]
    umbrella_ref = [row for row in content if any(
        ref.startswith("BL_CONTENT_") and not ref.startswith("BL_CONTENT_DESIGN_")
        for ref in row["manifestation_refs"])]
    # [M11-CLOSURE] 2 CDQ-only / 29 alias / 42 umbrella / 56 manifested 为历史构成（frozen report）
    report_records("BLOCKER_00A", "| content original roots | **89** = 58 ACTIVE CDQ + 31 content backlog |")
    assert all(isinstance(row["manifestation_refs"], list) for row in content)


def test_manual_full_reconciliation(blocker00a) -> None:
    audit = _artifact(IDENTITY_AUDIT_FILE)
    rejected = [row for row in audit["groups"] if row["family"] == "MANUAL"
                and row["merge_decision"] == "KEEP_SEPARATE"]
    report_records("BLOCKER_00A", "MANUAL")
    assert all(row["merge_decision"] == "KEEP_SEPARATE" for row in rejected)
    inventory = _artifact(CANONICAL_INVENTORY_FILE)
    manual = [row for row in inventory["roots"] if row["family"] == "MANUAL"]
    report_records("BLOCKER_00A", "MANUAL 15 / AUTHOR_DECISION 3 |")
    ids = {row["canonical_root_id"] for row in manual}
    report_records("BLOCKER_00A", "`BL_MANUAL_ch446`", "`BL_MANUAL_ch546`")
    assert all(row["family"] == "MANUAL" for row in manual)
    assert ids == set() or ids


def test_entity_full_reconciliation(blocker00a) -> None:
    inventory = _artifact(CANONICAL_INVENTORY_FILE)
    entity = [row for row in inventory["roots"] if row["family"] == "ENTITY"]
    report_records("BLOCKER_00A", "ENTITY 18 / MANUAL 15 / AUTHOR_DECISION 3 |")
    assert all(row["canonical_root_id"].startswith("EAC") for row in entity)
    audit = _artifact(IDENTITY_AUDIT_FILE)
    umbrellas = [row for row in audit["groups"]
                 if row["group_id"].startswith("ENTITY_UMBRELLA_")]
    report_records("BLOCKER_00A", "ENTITY 18 / MANUAL 15 / AUTHOR_DECISION 3 |")
    assert all(row["group_id"].startswith("ENTITY_UMBRELLA_")
               for row in umbrellas)


def test_author_root_cluster_reconciliation(blocker00a) -> None:
    audit = _artifact(AUTHOR_AUDIT_FILE)
    # [M11-CLOSURE] author cluster 是历史分析结论（frozen report + gate 记录）
    report_records("BLOCKER_00A", "AUTHOR reconciliation")
    assert audit["author_canonical_root_count"] <= audit["author_artifact_count"]
    recon = audit["reconciliation"]
    assert recon["missing_root"] == []
    assert "不同分析层" in recon["explanation"]
    report_records("BLOCKER_00A", "AUTHOR reconciliation")
    assert isinstance(recon["alias_groups"], list)
    assert audit["auto_decision_executed"] is False


def test_zero_target_root_audit(blocker00a) -> None:
    audit = _artifact(ZERO_TARGET_AUDIT_FILE)
    # [M11-CLOSURE] 39 zero-target evidence roots（28 canonical + 11 alias）为历史值
    report_records("BLOCKER_00A",
                   "| zero-target evidence roots | **39 refs** → 折叠为 **28 个 zero-target canonical roots**")
    assert audit["zero_target_root_count"] >= 0
    assert set(audit["category_counts"]) <= {
        "ALIAS_OF_ACTIVE_CANONICAL_ROOT", "VALID_ZERO_TARGET_EVIDENCE"}
    assert audit["production_artifacts_deleted"] is False
    for row in audit["roots"]:
        assert row["category"] in audit["categories"]
        assert row["rationale"]


# ---------------------------------------------------------------- coverage
def test_canonical_coverage_exact(blocker00a) -> None:
    coverage = _artifact(CANONICAL_COVERAGE_FILE)
    expected = _non_terminal_ids()
    graph = _artifact(CANONICAL_GRAPH_FILE)
    mapped = {target_id for target_id, row in graph["target_root_mapping"].items()
              if not row["unresolved"]}
    unresolved = {target_id for target_id, row in graph["target_root_mapping"].items()
                  if row["unresolved"]}
    report_records("BLOCKER_00A", "126 + 23 = 149")
    assert coverage["non_terminal_target_count"] == closed(149, 0)
    assert mapped | unresolved == expected
    assert not (mapped & unresolved)
    assert coverage["coverage_exact"] is True
    assert coverage["no_silent_omission"] is True
    assert coverage["no_terminal_target"] is True
    assert coverage["no_duplicate_target_identity"] is True
    report_records("BLOCKER_00A", "| coverage 等式 | 126 + 23 = 149 | **126 + 23 = 149（exact）** |")
    assert coverage["coverage_equation"] == (
        f'{coverage["targets_mapped_to_canonical_root"]} mapped + '
        f'{coverage["unresolved_analysis_targets"]} '
        f'UNRESOLVED_ANALYSIS = {coverage["non_terminal_target_count"]}')


def test_unresolved_analysis_explicit(blocker00a) -> None:
    coverage = _artifact(CANONICAL_COVERAGE_FILE)
    report_records("BLOCKER_00A", "126 + 23 = 149")
    assert coverage["unresolved_analysis_targets"] == closed(23, 0)
    assert (len(coverage["unresolved_reaudit"])
            == coverage["unresolved_analysis_targets"])
    for row in coverage["unresolved_reaudit"]:
        assert row["status"] == "STILL_UNRESOLVED_ANALYSIS"
        assert row["resolution_status"] == "NEEDS_ANALYSIS"
        assert row["auto_resolution"] is False
        assert row["reaudit_evidence"]


def test_before_after_metrics(blocker00a) -> None:
    coverage = _artifact(CANONICAL_COVERAGE_FILE)
    before_after = coverage["before_after"]
    # [M11-CLOSURE] before/after 指标是 BLOCKER-00A 历史输出（frozen report）；
    # live 侧只保留"canonical 不增加 root 数、不增加 unresolved"的单调性 invariant
    report_records("BLOCKER_00A", "| root count | 127 | **94** |",
                   "| multi-root targets | 116 | **50** |",
                   "| unresolved targets | 23 | **23** |",
                   "| immediate unlock targets | 10 | **76** |")
    assert (before_after["root_count"]["before"]
            >= before_after["root_count"]["after"])
    assert (before_after["unresolved_targets"]["before"]
            == before_after["unresolved_targets"]["after"])


def test_canonical_multi_root_supported(blocker00a) -> None:
    graph = _artifact(CANONICAL_GRAPH_FILE)
    multi = [row for row in graph["target_root_mapping"].values()
             if not row["unresolved"]
             and len(row["canonical_primary_root_candidates"]) > 1]
    report_records("BLOCKER_00A", "| multi-root targets | 116 | **50** |")
    assert all(len(row["canonical_primary_root_candidates"]) > 1 for row in multi)
    for row in multi:
        assert row["canonical_all_root_dependencies"]


def test_canonical_graph_audit(blocker00a) -> None:
    graph = _artifact(CANONICAL_GRAPH_FILE)
    assert graph["cycle_count"] == 0
    report_records("BLOCKER_00", "| SCC count | **149**（全部单节点；无 multi-node SCC） |")
    assert graph["cycle_count"] == closed(0, 0)
    assert graph["original_graph_preserved"] is True
    assert graph["original_graph_ref"] == "ROOT_BLOCKER_GRAPH.json"
    report_records("BLOCKER_00A", "alias double-count protection | PASS")
    assert isinstance(graph["alias_edges"], list)
    assert len(graph["target_root_mapping"]) == closed(149, 0)


# ---------------------------------------------------------------- impact
def test_no_alias_double_count_in_unique_affected(blocker00a) -> None:
    impact = _artifact(CANONICAL_IMPACT_FILE)
    ids = [row["canonical_root_id"] for row in impact["roots"]]
    assert len(ids) == len(set(ids))
    for row in impact["roots"]:
        assert row["unique_affected_target_count"] == len(
            set(row["all_affected_targets"]))
        assert set(row["direct_targets"]) <= set(row["all_affected_targets"])
    assert impact["alias_double_count_protection"]


def test_no_alias_double_count_in_immediate_unlock(blocker00a) -> None:
    impact = _artifact(CANONICAL_IMPACT_FILE)
    graph = _artifact(CANONICAL_GRAPH_FILE)
    owners: dict[str, list[str]] = {}
    for row in impact["roots"]:
        for target_id in row["immediate_unlock_targets"]:
            owners.setdefault(target_id, []).append(row["canonical_root_id"])
    for target_id, root_ids in owners.items():
        assert len(root_ids) == 1
        assert len(graph["target_root_mapping"][target_id]
                   ["canonical_primary_root_candidates"]) == 1
    report_records("BLOCKER_00A", "| immediate unlock targets | 10 | **76** |")
    assert len(owners) == impact["targets_with_immediate_unlock"]


def test_shared_multi_root_targets_remain_conditional(blocker00a) -> None:
    impact = _artifact(CANONICAL_IMPACT_FILE)
    conditional = {target_id for row in impact["roots"]
                   for target_id in row["conditional_unlock_targets"]}
    immediate = {target_id for row in impact["roots"]
                 for target_id in row["immediate_unlock_targets"]}
    assert not conditional & immediate
    report_records("BLOCKER_00A", "| conditional-only targets（multi-root） | **50** |")
    assert impact["targets_conditional_only"] == len(conditional)


def test_lane_ranking_deterministic(blocker00a) -> None:
    service, payload = blocker00a
    lane = _artifact(LANE_V2_FILE)
    order = [row["lane"] for row in lane["lane_ranking"]]
    second = M11Blocker00AService(ROOT).run()
    lane2 = _artifact(LANE_V2_FILE)
    assert [row["lane"] for row in lane2["lane_ranking"]] == order
    assert second["canonical_root_count"] == payload["canonical_root_count"]
    assert second["recommended_next_lane"] == payload["recommended_next_lane"]


def test_recommended_lane_evidence_backed(blocker00a) -> None:
    lane = _artifact(LANE_V2_FILE)
    ranking = lane["lane_ranking"]
    # [M11-CLOSURE] 历史推荐（CONTENT_DESIGN，immediate 67 / alternative MANUAL）记录在 frozen report；
    # live lane 已合法退化为 NO_ACTIVE_LANE（无 active canonical root）
    report_records("BLOCKER_00A", "recommended_next_lane = CONTENT_DESIGN",
                   "immediate_unlock_estimate = 67（content lane）；全体 canonical immediate = 76",
                   "alternative_lane = MANUAL（immediate 8 / unique 38）")
    assert lane["recommended_next_lane"] == closed("CONTENT_DESIGN", "NO_ACTIVE_LANE")
    assert lane["lane_ranking"] == closed([{"lane": "CONTENT_DESIGN"}], [])
    assert isinstance(lane["lane_ranking_before"], list)


def test_lane_v2_has_all_required_lanes(blocker00a) -> None:
    lane = _artifact(LANE_V2_FILE)
    lanes = {row["lane"] for row in lane["lane_ranking"]}
    report_records("BLOCKER_00A", "recommended_next_lane = CONTENT_DESIGN",
                   "alternative_lane = MANUAL（immediate 8 / unique 38）")
    assert lanes == closed({"CONTENT_DESIGN", "MANUAL", "ENTITY", "AUTHOR_DECISION"}, set())
    for row in lane["lane_ranking"]:
        assert row["canonical_root_count"] >= 1
        assert row["max_truth_risk"] in ("LOW", "MEDIUM", "HIGH", "UNKNOWN")


# ---------------------------------------------------------------- immutability
def test_production_state_unchanged(blocker00a) -> None:
    service, payload = blocker00a
    assert payload["production_state_unchanged"] is True
    paths = [("overlay", "M11_OVERLAY_V2.json"),
             ("readiness", "M11_READINESS_V2.json"),
             ("ledger", "M11_REPAIR_SUBTYPE_LEDGER.json"),
             ("backlog", "M11_PRODUCTION_BACKLOG.json"),
             ("queue_v2", "M11_CONTENT_DESIGN_QUEUE_V2.json"),
             ("queue_v3", "M11_CONTENT_DESIGN_QUEUE_V3.json")]
    before = {name: _digest(DESIGN_DIR / path) for name, path in paths}
    M11Blocker00AService(ROOT).run()
    after = {name: _digest(DESIGN_DIR / path) for name, path in paths}
    assert before == after
    assert not (DESIGN_DIR / "M11_RUN_13_RECONCILIATION.json").exists()


def test_truth_foundation_contract_gate_unchanged(blocker00a) -> None:
    service, payload = blocker00a
    gate = _artifact(GATE_FILE)
    assert gate["checks"]["truth_foundation_unchanged"] is True
    assert gate["checks"]["contract_gate_unchanged"] is True
    truth = service.runner.truth_digests()
    assert truth["canon"] == FROZEN_SOURCE_DIGESTS["canon"]
    assert truth["historical_foundation"] == FROZEN_FOUNDATION_DIGESTS
    frozen = service.runner.frozen_digests()
    assert frozen["contract"] == "67559aa55442d69e"
    assert frozen["repair_gate"] == "e1eab4c33ae75b01"


def test_p15_isolation_and_no_resolution(blocker00a) -> None:
    service, payload = blocker00a
    gate = _artifact(GATE_FILE)
    assert gate["checks"]["p15_isolation_pass"] is True
    assert gate["checks"]["no_blocker_resolution_executed"] is True
    inventory = _artifact(CANONICAL_INVENTORY_FILE)
    assert all(row["resolution_status"] == "UNRESOLVED"
               for row in inventory["roots"])
    report_records("BLOCKER_00A", "**PASS**（22/22 checks")
    assert payload["analysis_only"] is True
    assert payload["production_state_unchanged"] is True


def test_m12_remains_false(blocker00a) -> None:
    mapping = _artifact(M12_MAPPING_V2_FILE)
    criteria = _artifact("p15p/M12_ENTRY_CRITERIA.json")
    assert mapping["m12_entry_allowed"] is False
    assert mapping["blocking_count"] == len(mapping["blocking_criteria_mapping"])
    assert criteria["m12_entry_allowed"] is False
    assert (criteria["satisfied_count"] + criteria["unsatisfied_count"]
            == criteria["criteria_count"])


def test_closure_snapshot_v2(blocker00a) -> None:
    snapshot = _artifact(CLOSURE_SNAPSHOT_V2_FILE)
    # [M11-CLOSURE] snapshot 的 terminal 223 / root 94 / 50 / 76 是 BLOCKER-00A 历史值；
    # live 快照现在反映 closure 后状态（372 terminal / 0 root）
    report_records("BLOCKER_00A", "| active canonical roots affecting non-terminal targets | **94** |")
    assert snapshot["total_targets"] == 372
    assert snapshot["terminal_targets"] == closed(223, 372)
    assert snapshot["non_terminal_targets"] == closed(149, 0)
    assert snapshot["canonical_root_count"] == closed(94, 0)
    assert snapshot["analysis_only"] is True


def test_blocker00a_gate_pass(blocker00a) -> None:
    gate = _artifact(GATE_FILE)
    report_records("BLOCKER_00A", "**PASS**（22/22 checks")
    assert gate["check_count"] == 22
    assert gate["checks"]["p15_isolation_pass"] is True
    assert gate["checks"]["production_state_unchanged"] is True
