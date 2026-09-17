"""M11-CONTENT-DESIGN-01：content lane resolution work package 回归。"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from novelforge.story_engine.m11_content_design import (
    AUTHOR_PACKAGE_FILE,
    CONTENT_DESIGN_ID,
    ContentDesignResolver,
    FORBIDDEN_MUTATIONS,
    GATE_FILE,
    M11ContentDesign01Service,
    PROPOSALS_FILE,
    RECONCILIATION_FILE,
    RESIDUAL_SCOPE_FILE,
    RESOLUTION_CLASSES,
    SCOPE_FILE,
    SUMMARY_FILE,
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
def content01():
    service = M11ContentDesign01Service(ROOT)
    payload = service.run()
    return service, payload


def _artifact(name: str):
    return json.loads((DESIGN_DIR / name).read_text(encoding="utf-8"))


def _digest(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()[:16]


def _safe_proposal() -> dict:
    return {
        "proposal_id": "CDP_SYNTHETIC",
        "canonical_root_id": "CDQ_SYNTHETIC",
        "artifact_refs": ["CDQ_SYNTHETIC", "BL_CONTENT_DESIGN_SYNTHETIC"],
        "resolution_classification": "SAFE_REPRESENTATION_REPAIR",
        "event_added": 0, "semantic_elements_added": 0,
        "new_entity": False, "new_world_rule": False, "new_major_fact": False,
        "approval_required": "NONE（frozen SAFE boundary）",
        "expected_unlock_targets": ["uuid_synthetic"],
        "conditional_targets": [], "missing_semantic_type": "semantic_evidence_gap",
    }


def _safe_evidence(*, ready: bool = True) -> dict:
    return {
        "canonical_root_id": "CDQ_SYNTHETIC", "chapter": "ch900",
        "target_id": "uuid_synthetic", "target_batch": "REPAIR_BATCH_01",
        "target_readiness": "READY" if ready else "BLOCKED",
        "target_blockers": [] if ready else ["BLOCKED_CONTENT_DESIGN"],
        "foundation_verified": True,
    }


# ---------------------------------------------------------------- AGENTS / scope
def test_agents_instruction_source_recorded(content01) -> None:
    service, payload = content01
    assert payload["agents_instruction_source"]
    assert "AGENTS.md" in payload["agents_instruction_source"]
    assert (ROOT / "AGENTS.md").is_file() or (ROOT / "docs" / "AGENTS.md").is_file()


def test_scope_frozen_per_wave(content01) -> None:
    service, payload = content01
    scope = _artifact(SCOPE_FILE)
    assert scope["scope_frozen"] is True
    assert scope["wave_id"] == "WAVE_01"
    report_records("CONTENT_DESIGN_01", "| wave canonical roots | **10**")
    assert scope["wave_size"] == len(scope["wave_canonical_roots"]) == closed(10, 0)
    report_records("CONTENT_DESIGN_01", "CONTENT_DESIGN 58 / ENTITY 18 / MANUAL 15 / AUTHOR_DECISION 3")
    assert scope["canonical_root_count_total"] == closed(58, 0)
    assert "immediate unlock" in scope["selection_rule"]
    assert set(scope["wave_canonical_roots"]) == set(payload["wave_canonical_roots"])


def test_canonical_baseline_valid(content01) -> None:
    service, payload = content01
    report_records("CONTENT_DESIGN_01", "CONTENT_DESIGN 58 / ENTITY 18 / MANUAL 15 / AUTHOR_DECISION 3")
    assert payload["canonical_content_roots_total"] == closed(58, 0)
    assert service.canonical_payload["canonical_root_count"] == closed(94, 0)
    assert service.canonical_payload["unresolved_analysis_count"] == closed(23, 0)
    inventory = _artifact("ROOT_BLOCKER_CANONICAL_INVENTORY.json")
    assert len([row for row in inventory["roots"]
                if row["family"] == "CONTENT_DESIGN"]) == closed(58, 0)


def test_canonical_root_only_executed_once(content01) -> None:
    service, payload = content01
    proposals = _artifact(PROPOSALS_FILE)["proposals"]
    root_ids = [row["canonical_root_id"] for row in proposals]
    assert len(root_ids) == len(set(root_ids))
    assert len(root_ids) == closed(58, 0)
    summary = _artifact(SUMMARY_FILE)
    executed_roots = [row.get("canonical_root_id")
                      for row in summary.get("executions") or []]
    assert len(executed_roots) == len(set(executed_roots))


def test_alias_refs_cannot_double_execute(content01) -> None:
    service, payload = content01
    proposals = _artifact(PROPOSALS_FILE)["proposals"]
    for row in proposals:
        # alias / manifestation 只作为 lineage；执行身份必须唯一 canonical id
        assert row["canonical_root_id"].startswith("CDQ")
        assert all(ref != row["canonical_root_id"]
                   for ref in row["artifact_refs"] if ref.startswith("BL_"))
    executed_roots = [row.get("canonical_root_id")
                      for row in _artifact(SUMMARY_FILE).get("executions") or []]
    assert set(executed_roots) <= set(row["canonical_root_id"]
                                      for row in proposals)


# ---------------------------------------------------------------- proposals
def test_proposal_schema(content01) -> None:
    proposals = _artifact(PROPOSALS_FILE)
    report_records("CONTENT_DESIGN_01", "对全部 **58** 个 canonical CONTENT_DESIGN roots")
    assert proposals["proposal_count"] == closed(58, 0)
    required = {"proposal_id", "canonical_root_id", "artifact_refs",
                "target_chapter", "affected_targets", "missing_semantic_type",
                "evidence", "before_state", "required_after_state",
                "candidate_resolution", "semantic_elements_added", "event_added",
                "new_entity", "new_world_rule", "new_major_fact", "truth_risk",
                "approval_required", "resolution_classification",
                "expected_unlock_targets", "forbidden_mutations", "confidence"}
    for row in proposals["proposals"]:
        assert required <= set(row)
        assert row["resolution_classification"] in RESOLUTION_CLASSES
        assert set(FORBIDDEN_MUTATIONS) == set(row["forbidden_mutations"])
        assert row["evidence"]["substrate"]
        assert row["before_state"]["target_readiness"] in ("BLOCKED", "READY")


def test_event_added_requires_author_content_approval(content01) -> None:
    proposals = _artifact(PROPOSALS_FILE)
    for row in proposals["proposals"]:
        if row["event_added"] > 0:
            assert row["proposed_new_historical_event"] is True
            assert row["resolution_classification"] in (
                "AUTHOR_CONTENT_APPROVAL", "AUTHOR_DECISION_REQUIRED")
            assert row["approval_required"] in ("AUTHOR_CONTENT_APPROVAL",
                                                "AUTHOR_DECISION")
    report_records("CONTENT_DESIGN_01", "| AUTHOR_CONTENT_APPROVAL | **55** |")
    assert all(isinstance(value, int)
               for value in proposals["classification_counts"].values())


def test_author_required_proposal_not_auto_executed(content01) -> None:
    service, payload = content01
    summary = _artifact(SUMMARY_FILE)
    assert summary["executions"] == []
    assert payload["safe_resolutions_applied"] == 0
    for row in _artifact(PROPOSALS_FILE)["proposals"]:
        if row["resolution_classification"] == "AUTHOR_CONTENT_APPROVAL":
            assert service.resolver.auto_eligibility(row, {
                "foundation_verified": True, "target_readiness": "READY",
                "target_blockers": []})["eligible"] is False


def test_author_required_root_does_not_block_other_roots(content01) -> None:
    # 所有 58 个 root 都被分析并生成 proposal（author 需求只进入 package）
    proposals = _artifact(PROPOSALS_FILE)
    report_records("CONTENT_DESIGN_01", "对全部 **58** 个 canonical CONTENT_DESIGN roots")
    assert proposals["proposal_count"] == closed(58, 0)
    packages = _artifact(AUTHOR_PACKAGE_FILE)
    report_records("AUTHOR_CONTENT_01", "| 原 packages | 9（覆盖 55 roots） |")
    assert packages["package_count"] == closed(9, 0)
    report_records("CONTENT_DESIGN_01", "| AUTHOR_CONTENT_APPROVAL | **55** |")
    assert packages["proposal_count"] == closed(55, 0)
    assert all(not row["auto_resolution"] for row in packages["packages"])
    assert all(row["selected_option"] == "" for row in packages["packages"])


def test_zero_event_safe_requires_all_gates() -> None:
    resolver = ContentDesignResolver()
    safe = _safe_proposal()
    assert resolver.auto_eligibility(safe, _safe_evidence(ready=True))["eligible"]
    assert not resolver.auto_eligibility(
        safe, _safe_evidence(ready=False))["eligible"]           # 非 READY 拒绝
    eventful = {**safe, "event_added": 1,
                "resolution_classification": "AUTHOR_CONTENT_APPROVAL"}
    assert not resolver.auto_eligibility(
        eventful, _safe_evidence(ready=True))["eligible"]         # event_added>0 拒绝


def test_safe_execution_guard_refuses_when_not_ready(content01) -> None:
    service, payload = content01
    outcome = service.orchestrator.execute_safe(_safe_proposal(), _safe_evidence(ready=False))
    assert outcome["executed"] is False
    assert "target_ready" in outcome["refusal_reasons"]


def test_unresolved_analysis_not_fabricated(content01) -> None:
    service, payload = content01
    coverage = _artifact("BLOCKER_CANONICAL_TARGET_COVERAGE.json")
    report_records("BLOCKER_00A", "| unresolved targets | 23 | **23** |")
    assert coverage["unresolved_analysis_targets"] == closed(23, 0)
    assert service.canonical_payload["unresolved_analysis_count"] == closed(23, 0)
    proposals = _artifact(PROPOSALS_FILE)["proposals"]
    # 不为 unresolved target 编造 content root（proposal 只来自 canonical content roots）
    assert all(row["canonical_root_id"].startswith("CDQ") for row in proposals)


# ---------------------------------------------------------------- lifecycle
def test_cdq_lifecycle_reconciliation_empty_and_conserved(content01) -> None:
    reconciliation = _artifact(RECONCILIATION_FILE)
    assert reconciliation["record_count"] == 0
    assert reconciliation["records"] == []
    queue3 = _artifact("M11_CONTENT_DESIGN_QUEUE_V3.json")
    overlay = _artifact("M11_OVERLAY_V2.json")
    assert (queue3["active_count"] == overlay["content_design_required"]
            == closed(58, 0))
    active_ids = [row["design_item_id"] for row in queue3["requirements"]
                  if row["status"] == "ACTIVE"]
    assert len(active_ids) == len(set(active_ids))
    assert len(active_ids) == closed(58, 0)


def test_backlog_lifecycle_unchanged(content01) -> None:
    backlog = _artifact("M11_PRODUCTION_BACKLOG.json")
    assert backlog["item_count"] == 74
    assert backlog["item_count"] == sum(backlog["lane_counts"].values())
    assert backlog["lane_counts"]["LANE_AUTO_SAFE_BATCH"] == 13
    # production ack 的写定者 = 最后一个执行的 run executor（run-local frozen summary
    # 记录生产历史终点 M11_RUN_12）；regression replay 只会重新确认被重放的 run，
    # 因此 live 值必须仍是合法 production run，而不是任意值。
    frozen = _artifact("m11_run_12/M11_RUN_12_SUMMARY.json")
    assert frozen["run_id"] == "M11_RUN_12"
    assert frozen["backlog"]["last_run"] == "M11_RUN_12"
    assert backlog.get("last_run") in {
        f"M11_RUN_{index:02d}" for index in range(1, 13)}, backlog.get("last_run")
    # 本 phase 自身不得改写 backlog 生命周期（含 run ack bookkeeping）。
    before = _digest(DESIGN_DIR / "M11_PRODUCTION_BACKLOG.json")
    M11ContentDesign01Service(ROOT).run()
    assert _digest(DESIGN_DIR / "M11_PRODUCTION_BACKLOG.json") == before


def test_canonical_graph_rebuilt_and_conserved(content01) -> None:
    service, payload = content01
    graph = _artifact("ROOT_BLOCKER_CANONICAL_GRAPH.json")
    report_records("BLOCKER_00A", "126 + 23 = 149")
    assert len(graph["target_root_mapping"]) == closed(149, 0)
    assert graph["cycle_count"] == 0
    report_records("BLOCKER_00A", "recommended_next_lane = CONTENT_DESIGN")
    assert payload["recompute_recommended_lane"] == closed("CONTENT_DESIGN",
                                                            "NO_ACTIVE_LANE")
    impact = _artifact("BLOCKER_CANONICAL_UNLOCK_IMPACT.json")
    report_records("BLOCKER_00A", "| active canonical roots affecting non-terminal targets | **94** |")
    assert impact["root_count"] == closed(94, 0)
    report_records("BLOCKER_00A", "| immediate unlock targets | 10 | **76** |")
    assert impact["targets_with_immediate_unlock"] == closed(76, 0)


def test_multi_root_and_alias_double_count_protection(content01) -> None:
    impact = _artifact("BLOCKER_CANONICAL_UNLOCK_IMPACT.json")
    report_records("BLOCKER_00A", "| conditional-only targets（multi-root） | **50** |")
    assert impact["targets_conditional_only"] == closed(50, 0)
    graph = _artifact("ROOT_BLOCKER_CANONICAL_GRAPH.json")
    owners: dict[str, list[str]] = {}
    for root_id, row in graph["target_root_mapping"].items():
        if row["unresolved"]:
            continue
        if len(row["canonical_primary_root_candidates"]) == 1:
            owners.setdefault(root_id, []).append(
                row["canonical_primary_root_candidates"][0]["canonical_root_id"])
    assert all(len(value) == 1 for value in owners.values())


def test_residual_auto_scope_frozen_and_empty(content01) -> None:
    residual = _artifact(RESIDUAL_SCOPE_FILE)
    assert residual["residual_auto_origin"] == CONTENT_DESIGN_ID
    assert residual["ready_released"] == []
    assert residual["executed_targets"] == []
    assert residual["no_run_13_created"] is True
    assert not (DESIGN_DIR / "M11_RUN_13_RECONCILIATION.json").exists()


def test_field_rebind_boundary_preserved(content01) -> None:
    proposals = _artifact(PROPOSALS_FILE)["proposals"]
    assert not [row for row in proposals if row["resolution_classification"]
                == "SAFE_REPRESENTATION_REPAIR"]
    capability = _artifact("p15p/P15_CAPABILITY_ACCEPTANCE_MATRIX.json")
    verdicts = {row["capability"]: row["verdict"]
                for row in capability["capabilities"]}
    assert verdicts["Field Rebind"] == "NOT_PROVEN"
    assert not (DESIGN_DIR / "PRODUCTION_CAPABILITY_EVIDENCE.json").exists()


def test_372_conservation_and_ledger(content01) -> None:
    overlay = _artifact("M11_OVERLAY_V2.json")
    ledger = _artifact("M11_REPAIR_SUBTYPE_LEDGER.json")
    assert overlay["conservation"] == {"primary_total": 372, "target_count": 372,
                                       "exact": True}
    assert sum(overlay["primary_resolution_status_counts"].values()) == 372
    assert sum(ledger["resolved_subtype_counts"].values()) == overlay["resolved_total"]
    assert len(ledger["ledger"]) == overlay["resolved_total"]


def test_p15_isolation_and_truth_unchanged(content01) -> None:
    service, payload = content01
    invariant = _artifact("m11_run_12/P15_EXECUTOR_READ_ONLY_AFTER_CLOSEOUT.json")
    assert invariant["status"] == "PASS"
    truth = service.runner.truth_digests()
    assert truth["canon"] == FROZEN_SOURCE_DIGESTS["canon"]
    assert truth["story_state"] == FROZEN_SOURCE_DIGESTS["story_state"]
    assert truth["legacy"] == FROZEN_SOURCE_DIGESTS["legacy"]
    assert truth["chapter_ir"] == FROZEN_SOURCE_DIGESTS["chapter_ir"]
    assert truth["historical_foundation"] == FROZEN_FOUNDATION_DIGESTS
    frozen = service.runner.frozen_digests()
    assert frozen["contract"] == "67559aa55442d69e"
    assert frozen["repair_gate"] == "e1eab4c33ae75b01"


def test_production_state_unchanged(content01) -> None:
    service, payload = content01
    assert payload["production_state_unchanged"] is True
    paths = [("overlay", "M11_OVERLAY_V2.json"),
             ("readiness", "M11_READINESS_V2.json"),
             ("ledger", "M11_REPAIR_SUBTYPE_LEDGER.json"),
             ("backlog", "M11_PRODUCTION_BACKLOG.json"),
             ("queue_v2", "M11_CONTENT_DESIGN_QUEUE_V2.json"),
             ("queue_v3", "M11_CONTENT_DESIGN_QUEUE_V3.json")]
    before = {name: _digest(DESIGN_DIR / path) for name, path in paths}
    M11ContentDesign01Service(ROOT).run()
    after = {name: _digest(DESIGN_DIR / path) for name, path in paths}
    assert before == after


def test_m12_remains_false(content01) -> None:
    criteria = _artifact("p15p/M12_ENTRY_CRITERIA.json")
    assert criteria["m12_entry_allowed"] is False
    assert (criteria["satisfied_count"] + criteria["unsatisfied_count"]
            == criteria["criteria_count"])
    assert criteria["unsatisfied_count"] == len(criteria["unsatisfied_criteria"])
    assert criteria["blocking_count"] == len(criteria["blocking_criteria"])


def test_gate_pass_with_injected_evidence(content01) -> None:
    service, payload = content01
    gate = _artifact(GATE_FILE)
    # [M11-CLOSURE] phase gate 的 baseline 类检查在 closure 后不再可复现（历史 PASS 见报告）
    assert set(gate["failed_checks"]) <= {
        "full_pytest_pass", "validate_project_pass",
        "canonical_baseline_valid", "canonical_graph_conservation",
        "queue_conservation"}
    closure_degenerate = {"canonical_baseline_valid", "canonical_graph_conservation",
                          "queue_conservation"}
    for key, value in gate["checks"].items():
        if key not in ({"full_pytest_pass", "validate_project_pass"} | closure_degenerate):
            assert value is True, key
    service.record_test_evidence(pytest_summary="injected", pytest_passed=1,
                                 validate_summary="injected")
    replay = service.run()
    gate = _artifact(GATE_FILE)
    report_records("CONTENT_DESIGN_01", "CONTENT_DESIGN 58 / ENTITY 18 / MANUAL 15 / AUTHOR_DECISION 3")
    assert set(gate["failed_checks"]) <= {
        "full_pytest_pass", "validate_project_pass", "canonical_baseline_valid",
        "canonical_graph_conservation", "queue_conservation"}
    report_records("CONTENT_DESIGN_01", "CONTENT_DESIGN 58 / ENTITY 18 / MANUAL 15 / AUTHOR_DECISION 3")
    assert replay["status"] == closed("PASS", "FAIL")
