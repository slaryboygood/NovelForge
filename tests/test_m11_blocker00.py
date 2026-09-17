"""M11-BLOCKER-00：Root Blocker Graph / Unlock Impact / Priority 分析回归（analysis-only）。"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from novelforge.story_engine.m11_blocker00 import (
    ANALYSIS_INVARIANTS,
    AUTHOR_CLUSTER_FILE,
    BASELINE_FILE,
    COVERAGE_FILE,
    GATE_FILE,
    GRAPH_FILE,
    IMPACT_FILE,
    INVENTORY_FILE,
    LANE_FILE,
    M12_MAPPING_FILE,
    PRIORITY_FILE,
    BlockerPriorityPlanner,
    M11Blocker00Service,
    RootBlockerGraph,
    UnlockImpactAnalyzer,
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
def blocker00():
    service = M11Blocker00Service(ROOT)
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


def _synthetic_inventory(*, cycle: bool = False) -> dict:
    deps = {"tA": {"tB"}, "tB": {"tA"} if cycle else set()}
    return {
        "targets": {"tA": {"current_direct_blockers": ["BLOCKED_MANUAL_REPAIR"]},
                    "tB": {"current_direct_blockers": ["BLOCKED_MANUAL_REPAIR"]}},
        "labels": {"tA": "ch901", "tB": "ch902"},
        "roots": {"ROOT_R": {"root_blocker_id": "ROOT_R", "family": "MANUAL",
                             "owner": "OPERATOR+author", "source_kind": "BACKLOG_ITEM",
                             "source_ref": "ROOT_R",
                             "source_artifact": "synthetic",
                             "evidence": ["synthetic"],
                             "resolution_status": "NEEDS_MANUAL",
                             "approval_requirement": "synthetic",
                             "analysis_confidence": "HIGH"}},
        "own_roots": {"tA": {}, "tB": {"ROOT_R": ("MANUAL", "own_backlog")}},
        "dependencies": deps,
        "self_loops": {},
        "entity_aggregate_root": "BL_ENTITY_CLUSTERS",
    }


# ---------------------------------------------------------------- entry set
def test_entry_baseline_exact_set(blocker00) -> None:
    service, payload = blocker00
    graph = _artifact(GRAPH_FILE)
    expected = _non_terminal_ids()
    graph_targets = {row["node_id"] for row in graph["nodes"]
                     if row["node_type"] == "PRIMARY_TARGET"}
    # [M11-CLOSURE] entry set（149 non-terminal）是 BLOCKER-00 历史证据：
    # live non-terminal 现在为 0（372/372 terminal），历史值由 frozen phase report 保留
    report_records("BLOCKER_00", "| non-terminal | 149 | ✓ |",
                   "| non-terminal targets | **149** |")
    assert len(expected) == closed(149, 0)
    assert graph_targets == expected
    assert len(graph["target_root_mapping"]) == closed(149, 0)
    assert payload["non_terminal_target_count"] == closed(149, 0)
    assert _artifact(INVENTORY_FILE)["root_blocker_count"] == closed(
        127, payload["root_blocker_count"])


def test_no_terminal_target_in_scope() -> None:
    runner = M11Run12Service(ROOT)
    states = runner.readiness.target_states(inputs=runner.inputs())
    resolved = {str(cid) for cid, state in states.items()
                if str(state.target_state) == "RESOLVED"}
    graph = _artifact(GRAPH_FILE)
    graph_targets = {row["node_id"] for row in graph["nodes"]
                     if row["node_type"] == "PRIMARY_TARGET"}
    assert not (graph_targets & resolved)


def test_no_non_terminal_target_omitted(blocker00) -> None:
    coverage = _artifact(COVERAGE_FILE)
    graph = _artifact(GRAPH_FILE)
    expected = _non_terminal_ids()
    mapped = {row["node_id"] for row in graph["nodes"]
              if row["node_type"] == "PRIMARY_TARGET"
              and not graph["target_root_mapping"][row["node_id"]]["unresolved"]}
    unresolved = {target_id for target_id, row in graph["target_root_mapping"].items()
                  if row["unresolved"]}
    assert mapped | unresolved == expected
    assert not (mapped & unresolved)
    assert coverage["coverage_exact"] is True
    assert coverage["no_silent_omission"] is True


# ---------------------------------------------------------------- roots
def test_root_ids_unique_and_evidence_backed(blocker00) -> None:
    inventory = _artifact(INVENTORY_FILE)
    ids = [row["root_blocker_id"] for row in inventory["roots"]]
    assert len(ids) == len(set(ids)) == inventory["root_blocker_count"]
    for row in inventory["roots"]:
        assert row["source_kind"] and row["source_ref"] and row["source_artifact"]
        assert row["evidence"]
        assert row["resolution_status"] in (
            "UNRESOLVED", "NEEDS_AUTHOR", "NEEDS_ENTITY", "NEEDS_MANUAL",
            "NEEDS_CONTENT_DESIGN", "NEEDS_ANALYSIS")
        assert row["analysis_confidence"] in ("HIGH", "MEDIUM", "LOW")


def test_multi_root_target_supported(blocker00) -> None:
    graph = _artifact(GRAPH_FILE)
    # coverage 只统计 mapped targets（partial mapping 的 UNRESOLVED_ANALYSIS 不计入）
    multi = [row for row in graph["target_root_mapping"].values()
             if not row["unresolved"] and len(row["primary_root_candidates"]) > 1]
    coverage = _artifact(COVERAGE_FILE)
    # [M11-CLOSURE] 历史 116 pseudo multi-root → 50 canonical multi-root（frozen report）
    report_records("BLOCKER_00A", "| multi-root targets | 116 | **50** |",
                   "multi-root targets")
    assert len(multi) == coverage["targets_with_multiple_roots"] == closed(50, 0)
    for row in multi:
        assert row["all_root_dependencies"]


def test_dependency_traversal_works() -> None:
    graph = RootBlockerGraph(_synthetic_inventory()).build()
    assert graph["primary_roots"]["tB"] == {"ROOT_R": ("MANUAL", 0)}
    assert graph["primary_roots"]["tA"] == {"ROOT_R": ("MANUAL", 1)}
    assert graph["all_root_dependencies"]["tA"] == {"ROOT_R"}


def test_transitive_target_mapping_works() -> None:
    graph = RootBlockerGraph(_synthetic_inventory()).build()
    impact = UnlockImpactAnalyzer(graph).analyze()
    row = next(item for item in impact["roots"]
               if item["root_blocker_id"] == "ROOT_R")
    assert row["direct_target_count"] == 2
    assert row["unique_affected_target_count"] == 2


def test_cycle_detection_works() -> None:
    graph = RootBlockerGraph(_synthetic_inventory(cycle=True)).build()
    assert len(graph["cycles"]) == 1
    assert set(graph["cycles"][0]) == {"tA", "tB"}
    assert any(len(component) == 2 for component in graph["sccs"])


def test_scc_does_not_fabricate_root() -> None:
    inventory = _synthetic_inventory(cycle=True)
    graph = RootBlockerGraph(inventory).build()
    assert set(graph["roots"]) == {"ROOT_R"}
    assert all(root_id == "ROOT_R" for roots in graph["primary_roots"].values()
               for root_id in roots)


def test_unresolved_analysis_explicit(blocker00) -> None:
    graph = _artifact(GRAPH_FILE)
    coverage = _artifact(COVERAGE_FILE)
    unresolved = [(target_id, row) for target_id, row in
                  graph["target_root_mapping"].items() if row["unresolved"]]
    report_records("BLOCKER_00", "| UNRESOLVED_ANALYSIS（无法归因） | **23**")
    assert len(unresolved) == coverage["targets_with_no_evidence_backed_root"] == closed(23, 0)
    entries = {row[0]: row for row in coverage["unresolved_analysis_targets"]}
    assert len(entries) == len(unresolved)
    for chapter, missing, reason in coverage["unresolved_analysis_targets"]:
        assert missing and reason.startswith("no evidence-backed")
        assert chapter in entries
    assert "不猜测 owner" in coverage["unresolved_policy"]


def test_root_coverage_accounting_exact(blocker00) -> None:
    coverage = _artifact(COVERAGE_FILE)
    report_records("BLOCKER_00", "126 mapped + 23 UNRESOLVED_ANALYSIS = 149")
    assert coverage["non_terminal_target_count"] == closed(149, 0)
    assert (coverage["targets_with_root_mapping"]
            + coverage["targets_with_no_evidence_backed_root"]) == closed(149, 0)
    assert coverage["coverage_exact"] is True
    assert coverage["no_silent_omission"] is True


def test_derived_blocker_not_used_as_execution_item(blocker00) -> None:
    baseline = _artifact(BASELINE_FILE)
    inventory = _artifact(INVENTORY_FILE)
    assert "DERIVED_BLOCKER_COUNT_IS_NOT_EXECUTION_ITEM_COUNT" in baseline["invariants"]
    assert "DERIVED_BLOCKER_COUNT_IS_NOT_EXECUTION_ITEM_COUNT" in ANALYSIS_INVARIANTS
    report_records("BLOCKER_00", "471", "74 backlog items", "**127**")
    assert inventory["root_blocker_count"] == closed(127, 0)


# ---------------------------------------------------------------- impact
def test_unlock_impact_unique_counting(blocker00) -> None:
    impact = _artifact(IMPACT_FILE)
    for row in impact["roots"]:
        assert row["unique_affected_target_count"] == len(
            set(row["all_affected_targets"]))
        assert set(row["direct_targets"]) <= set(row["all_affected_targets"])
        assert set(row["all_affected_targets"]) <= set(row["transitive_targets"])
        assert row["transitive_affected_target_count"] == len(
            set(row["transitive_targets"]))
    assert impact["total_immediate_unlock"] == sum(
        row["immediate_unlock_count_if_only_this_root_resolved"]
        for row in impact["roots"])


def test_immediate_unlock_no_shared_double_count(blocker00) -> None:
    impact = _artifact(IMPACT_FILE)
    graph = _artifact(GRAPH_FILE)
    immediate_owners: dict[str, list[str]] = {}
    for row in impact["roots"]:
        for target_id in row["immediate_unlock_targets"]:
            immediate_owners.setdefault(target_id, []).append(
                row["root_blocker_id"])
    for target_id, owners in immediate_owners.items():
        assert len(owners) == 1
        assert len(graph["target_root_mapping"][target_id]
                   ["primary_root_candidates"]) == 1
    mapped_single = [target_id for target_id, row in
                     graph["target_root_mapping"].items()
                     if not row["unresolved"]
                     and len(row["primary_root_candidates"]) == 1]
    assert len(immediate_owners) == impact["targets_with_immediate_unlock"] \
        == len(mapped_single)


def test_conditional_unlock_separated(blocker00) -> None:
    impact = _artifact(IMPACT_FILE)
    graph = _artifact(GRAPH_FILE)
    conditional_ids = {target_id for row in impact["roots"]
                       for target_id in row["conditional_unlock_targets"]}
    assert not conditional_ids & {target_id for row in impact["roots"]
                                  for target_id in row["immediate_unlock_targets"]}
    for target_id in conditional_ids:
        assert len(graph["target_root_mapping"][target_id]
                   ["primary_root_candidates"]) > 1
    assert impact["targets_conditional_only"] == len(conditional_ids)


# ---------------------------------------------------------------- priority
def test_priority_ordering_deterministic(blocker00) -> None:
    service, payload = blocker00
    priority = _artifact(PRIORITY_FILE)
    orders = [row["root_blocker_id"] for row in priority["roots"]]
    family_order = ("AUTHOR_POLICY", "AUTHOR_CONTENT", "AUTHOR_DECISION",
                    "MAJOR_DESIGN", "ENTITY", "MANUAL", "CONTENT_DESIGN")
    expected = [row["root_blocker_id"] for row in sorted(
        priority["roots"],
        key=lambda row: (row["priority_tier"],
                         -row["immediate_unlock_count_if_only_this_root_resolved"],
                         -row["unique_affected_target_count"],
                         family_order.index(row["family"])
                         if row["family"] in family_order else 99,
                         row["root_blocker_id"]))]
    assert orders == expected
    second = M11Blocker00Service(ROOT).run()
    assert second["root_blocker_count"] == payload["root_blocker_count"]
    priority2 = _artifact(PRIORITY_FILE)
    assert [row["root_blocker_id"] for row in priority2["roots"]] == orders
    assert priority["tier_counts"] == priority2["tier_counts"]


def test_priority_rationale_present(blocker00) -> None:
    priority = _artifact(PRIORITY_FILE)
    for row in priority["roots"]:
        assert row["rationale"]
        assert row["priority_tier"] in (
            "TIER_1_UNBLOCKS_DIRECTLY", "TIER_2_HIGH_LEVERAGE",
            "TIER_3_MEDIUM", "TIER_4_LOCAL")
        assert 0.0 <= row["shared_blocker_ratio"] <= 1.0
    assert priority["explainable_fields_only"] is True


def test_author_clusters_do_not_resolve(blocker00) -> None:
    clusters = _artifact(AUTHOR_CLUSTER_FILE)
    assert clusters["proposal_count"] >= 1
    for row in clusters["clusters"]:
        assert row["auto_resolution"] is False
        assert row["option_auto_selected"] is False
        assert row["source_author_items"]
        assert row["why_they_can_be_batched"]
    assert clusters["invariant"] == "AUTHOR_DECISION_IS_BATCHED"


def test_next_lane_recommendation_evidence_backed(blocker00) -> None:
    lane = _artifact(LANE_FILE)
    ranking = lane["lane_ranking"]
    # [M11-CLOSURE] 已无 active root blocker：lane ranking 合法退化为空 + NO_ACTIVE_LANE
    report_records("BLOCKER_00A", "recommended_next_lane = CONTENT_DESIGN",
                   "immediate_unlock_estimate = 67（content lane）；全体 canonical immediate = 76")
    assert ranking == closed("CONTENT_DESIGN ranking", [])
    assert lane["recommended_next_lane"] == closed("CONTENT_DESIGN", "NO_ACTIVE_LANE")
    assert lane["reason"]
    assert lane["execution_order_basis"] == (
        "execution order selected by BLOCKER-00 unlock impact analysis")
    if lane["alternative_lane"]:
        assert lane["why_not_alternative_first"]


# ---------------------------------------------------------------- immutability
def test_production_state_unchanged(blocker00) -> None:
    service, payload = blocker00
    assert payload["production_state_unchanged"] is True
    paths = [("overlay", "M11_OVERLAY_V2.json"),
             ("readiness", "M11_READINESS_V2.json"),
             ("ledger", "M11_REPAIR_SUBTYPE_LEDGER.json"),
             ("backlog", "M11_PRODUCTION_BACKLOG.json"),
             ("queue_v2", "M11_CONTENT_DESIGN_QUEUE_V2.json"),
             ("queue_v3", "M11_CONTENT_DESIGN_QUEUE_V3.json")]
    before = {name: _digest(DESIGN_DIR / path) for name, path in paths}
    M11Blocker00Service(ROOT).run()
    after = {name: _digest(DESIGN_DIR / path) for name, path in paths}
    assert before == after
    assert not (DESIGN_DIR / "M11_RUN_13_RECONCILIATION.json").exists()


def test_truth_foundation_contract_gate_unchanged(blocker00) -> None:
    baseline = _artifact(BASELINE_FILE)
    truth = baseline["truth_digests"]
    assert truth["canon"] == FROZEN_SOURCE_DIGESTS["canon"]
    assert truth["story_state"] == FROZEN_SOURCE_DIGESTS["story_state"]
    assert truth["legacy"] == FROZEN_SOURCE_DIGESTS["legacy"]
    assert truth["chapter_ir"] == FROZEN_SOURCE_DIGESTS["chapter_ir"]
    assert baseline["foundation_digests"] == FROZEN_FOUNDATION_DIGESTS
    assert baseline["contract_digest"] == "67559aa55442d69e"
    assert baseline["gate_digest"] == "e1eab4c33ae75b01"


def test_p15_isolation_pass(blocker00) -> None:
    baseline = _artifact(BASELINE_FILE)
    assert baseline["p15_isolation"] == "PASS"
    invariant = _artifact("m11_run_12/P15_EXECUTOR_READ_ONLY_AFTER_CLOSEOUT.json")
    assert invariant["status"] == "PASS"
    assert invariant["static_scan_pass"] is True
    assert invariant["runtime_isolation_pass"] is True


def test_execution_components_remain_planned_only(blocker00) -> None:
    baseline = _artifact(BASELINE_FILE)
    status = baseline["component_status"]
    assert status["RootBlockerGraph"] == "IMPLEMENTED_FOR_BLOCKER_00_ANALYSIS"
    assert status["UnlockImpactAnalyzer"] == "IMPLEMENTED_FOR_BLOCKER_00_ANALYSIS"
    assert status["BlockerPriorityPlanner"] == "IMPLEMENTED_FOR_BLOCKER_00_ANALYSIS"
    assert status["M11ClosureController"] == "ANALYSIS_ONLY_SNAPSHOT"
    for name in ("ContentDesignResolver", "EntityResolutionEngine",
                 "ManualRepairWorkbench", "AuthorDecisionConsole",
                 "BlockerResolutionOrchestrator"):
        assert status[name] == "PLANNED_ONLY"


def test_no_blocker_resolution_executed(blocker00) -> None:
    payload = blocker00[1]
    inventory = _artifact(INVENTORY_FILE)
    for row in inventory["roots"]:
        assert row["resolution_status"] not in ("RESOLVED", "APPROVED", "REPAIRED")
    # [M11-CLOSURE] BLOCKER-00 gate 是 phase-timepoint 检查（149/127/23），
    # closure 后只能保证 analysis-only + production state unchanged；历史 PASS 记录在报告
    report_records("BLOCKER_00", "M11_BLOCKER_00_GATE.json`：**PASS**（16/16 checks")
    assert payload["analysis_only"] is True
    assert payload["production_state_unchanged"] is True
    assert not (DESIGN_DIR / "MANUAL_REPAIR_BRIEF_ch546.json").exists()


def test_m12_remains_not_allowed(blocker00) -> None:
    mapping = _artifact(M12_MAPPING_FILE)
    criteria = _artifact("p15p/M12_ENTRY_CRITERIA.json")
    # [M11-CLOSURE] BLOCKER-00 时代的 M12 映射是历史 projection；
    # 权威值现在来自 M12_ENTRY_CRITERIA_FINAL.json（见 test_m11_final_closure.py）
    assert mapping["m12_entry_allowed"] is False
    assert mapping["blocking_count"] == len(mapping["blocking_criteria_mapping"])
    assert criteria["m12_entry_allowed"] is False
    assert (criteria["satisfied_count"] + criteria["unsatisfied_count"]
            == criteria["criteria_count"])


def test_blocker00_gate_pass(blocker00) -> None:
    gate = _artifact(GATE_FILE)
    report_records("BLOCKER_00", "**PASS**（16/16 checks")
    assert gate["check_count"] == 16   # [M11-CLOSURE] phase-timepoint gate 现为 post-closure 重算
    baseline = _artifact(BASELINE_FILE)
    assert baseline["production_source_commit"] == "d5e5919"
    assert baseline["phase_closeout_commit"] == "5e97e7e"
    # analysis 起点 = closeout commit（pinned full SHA）；不与 production source 混写
    assert baseline["blocker00_execution_base_commit"].startswith("5e97e7e")
    assert baseline["blocker00_execution_base_commit"] != \
        baseline["production_source_commit"]
    assert baseline["commit_semantics"]["production_source_commit"]
    assert baseline["commit_semantics"]["blocker00_execution_base_commit"].startswith(
        "BLOCKER-00 分析开始点")
    snapshot = _artifact("M11_CLOSURE_CONTROLLER_SNAPSHOT.json")
    assert snapshot["analysis_only"] is True
    assert snapshot["recommended_next_lane"]
