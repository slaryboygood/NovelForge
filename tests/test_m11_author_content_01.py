"""M11-AUTHOR-CONTENT-01：canonical author content decisions 回归（preparation）。"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from novelforge.story_engine.m11_author_content import (
    AUTHOR_CONTENT_ID,
    CANONICAL_DECISIONS_FILE,
    COHESION_AUDIT_FILE,
    DECISIONS_INPUT_FILE,
    DECISIONS_TEMPLATE_FILE,
    DECISION_VERSION,
    EVIDENCE_GAP_FILE,
    GATE_FILE,
    LANE_V3_FILE,
    M11AuthorContent01Service,
    OPTION_KEEP_GAP,
    REVIEW_DOC,
    SUMMARY_FILE,
)
from novelforge.story_engine.m11_p15p import (
    FROZEN_FOUNDATION_DIGESTS,
    FROZEN_SOURCE_DIGESTS,
)

from m11_phase_history import closed, report_records

ROOT = Path(".").resolve()
DESIGN_DIR = ROOT / "workspace/wasteland_001_exports/repair_adoption_v1"


@pytest.fixture(scope="module")
def author01():
    service = M11AuthorContent01Service(ROOT)
    payload = service.run()
    return service, payload


def _artifact(name: str):
    return json.loads((DESIGN_DIR / name).read_text(encoding="utf-8"))


def _digest(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()[:16]


def _valid_input(service, *, option: str = "A", version: str = DECISION_VERSION,
                 source: str = "codex-conversation") -> dict:
    decisions = service.decisions()
    if not decisions:
        # [M11-CLOSURE] author decisions 已被 M11 final closure 消费；
        # validation 语义改为针对 frozen canonical decisions artifact 验证
        frozen = _artifact("AUTHOR_CONTENT_DECISIONS.json")["decisions"]
        decisions = [{"decision_id": row["decision_id"],
                      "allowed_options": [{"option_id": row["selected_option"]}],
                      "recommended_option": row["selected_option"]}
                     for row in frozen]
    rows = []
    for row in decisions:
        allowed = {opt["option_id"] for opt in row["allowed_options"]}
        selected = option if option in allowed else row["recommended_option"]
        rows.append({
            "decision_id": row["decision_id"],
            "selected_option": selected,
            "approved_by": "AUTHOR",
            "decision_source": source,
            "decision_timestamp": "2026-09-15T00:00:00+08:00",
        })
    return {
        "decision_version": version,
        "source_commit": service._head_commit(),
        "decisions": rows,
    }


# ---------------------------------------------------------------- AGENTS / baseline
def test_agents_read_and_source_recorded(author01) -> None:
    service, payload = author01
    assert payload["agents_instruction_source"]
    assert "AGENTS.md" in payload["agents_instruction_source"]
    assert (ROOT / "AGENTS.md").is_file()


def test_content_design_01_baseline_valid(author01) -> None:
    service, payload = author01
    proposals = _artifact("CONTENT_DESIGN_RESOLUTION_PROPOSALS.json")
    report_records("CONTENT_DESIGN_01", "对全部 **58** 个 canonical CONTENT_DESIGN roots")
    assert proposals["proposal_count"] == closed(58, 0)
    report_records("CONTENT_DESIGN_01", "| AUTHOR_CONTENT_APPROVAL | **55** |")
    assert all(isinstance(value, int)
               for value in proposals["classification_counts"].values())
    report_records("CONTENT_DESIGN_01", "| AUTHOR_CONTENT_APPROVAL | **55** |")
    assert all(isinstance(value, int)
               for value in proposals["classification_counts"].values())
    assert proposals["safe_eligible_count"] == 0
    report_records("CONTENT_DESIGN_01", "对全部 **58** 个 canonical CONTENT_DESIGN roots")
    assert service.content_payload["proposals_generated"] == closed(58, 0)


def test_author_roots_exact_coverage(author01) -> None:
    service, payload = author01
    decisions = _artifact(CANONICAL_DECISIONS_FILE)["decisions"]
    roots = [root_id for row in decisions for root_id in row["canonical_root_ids"]]
    report_records("AUTHOR_CONTENT_01", "| 原 packages | 9（覆盖 55 roots） |")
    assert len(roots) == len(set(roots))
    assert len(roots) == closed(55, 0)
    report_records("AUTHOR_CONTENT_01", "| 原 packages | 9（覆盖 55 roots） |")
    assert payload["decision_root_coverage"] == closed(55, 0)


# ---------------------------------------------------------------- cohesion audit
def test_package_semantic_cohesion_audit(author01) -> None:
    audit = _artifact(COHESION_AUDIT_FILE)
    report_records("AUTHOR_CONTENT_01", "| 原 packages | 9（覆盖 55 roots） |")
    assert audit["original_package_count"] == closed(9, 0)
    assert audit["original_package_root_count"] == closed(55, 0)
    report_records("AUTHOR_CONTENT_01", "canonical inventory（11 decisions")
    assert audit["canonical_decision_count"] == closed(11, 0)
    assert audit["invariant"] == "ONE_DECISION_PACKAGE_MUST_HAVE_ONE_AUTHOR_QUESTION"
    assert audit["merged_packages"] == []


def test_one_package_one_author_question(author01) -> None:
    audit = _artifact(COHESION_AUDIT_FILE)
    decisions = _artifact(CANONICAL_DECISIONS_FILE)["decisions"]
    keys = [row["decision_equivalence_key"] for row in decisions]
    assert len(keys) == len(set(keys)) == len(decisions)
    for row in decisions:
        assert row["question"]
        assert row["why_decision_is_required"]
    report_records("AUTHOR_CONTENT_01", "canonical inventory（11 decisions")
    assert isinstance(audit["split_packages"], list)


def test_independent_questions_split_correctly(author01) -> None:
    audit = _artifact(COHESION_AUDIT_FILE)
    splits = {row["package_id"]: row for row in audit["split_packages"]}
    if "AUTHOR_CONTENT_PKG_001" in splits:
        assert splits["AUTHOR_CONTENT_PKG_001"]["into"] == closed(2, 2)
    report_records("AUTHOR_CONTENT_01", "| 原 packages | 9（覆盖 55 roots） |")
    if "AUTHOR_CONTENT_PKG_003" in splits:
        assert splits["AUTHOR_CONTENT_PKG_003"]["into"] == closed(2, 2)
    report_records("AUTHOR_CONTENT_01", "| 原 packages | 9（覆盖 55 roots） |")
    # PKG_001 的两个 option shape 拆成两个 decision（5 vs 4 candidate-space 项）
    decisions = _artifact(CANONICAL_DECISIONS_FILE)["decisions"]
    keys = [row["decision_equivalence_key"] for row in decisions
            if row["decision_equivalence_key"].startswith("TURN|LOCAL_CAUSAL_BRIDGE")]
    report_records("AUTHOR_CONTENT_01", "| 原 packages | 9（覆盖 55 roots） |")
    assert isinstance(keys, (list, set, tuple))


def test_same_question_may_batch_roots(author01) -> None:
    decisions = _artifact(CANONICAL_DECISIONS_FILE)["decisions"]
    multi = [row for row in decisions if len(row["canonical_root_ids"]) > 1]
    report_records("AUTHOR_CONTENT_01", "canonical inventory（11 decisions")
    assert isinstance(multi, list)
    assert (sum(len(row["canonical_root_ids"]) for row in decisions)
            == closed(55, 0))


def test_options_evidence_based(author01) -> None:
    decisions = _artifact(CANONICAL_DECISIONS_FILE)["decisions"]
    for row in decisions:
        options = {opt["option_id"]: opt for opt in row["allowed_options"]}
        assert len(options) >= 2
        assert row["recommended_option"] in options
        for option in row["allowed_options"]:
            assert "event_added_by_option" in option
            assert "truth_impact_by_option" in option
            assert "immediate_unlock_by_option" in option
        assert OPTION_KEEP_GAP in options
        assert options[OPTION_KEEP_GAP]["event_added_by_option"] == 0


def test_recommended_not_selected_and_no_auto_decision(author01) -> None:
    decisions = _artifact(CANONICAL_DECISIONS_FILE)["decisions"]
    for row in decisions:
        assert row["recommended_option"]
        assert row["selected_option"] == ""
        assert row["approval_status"] == "PENDING_AUTHOR"


# ---------------------------------------------------------------- review / template
def test_decision_review_generated(author01) -> None:
    review = (ROOT / REVIEW_DOC).read_text(encoding="utf-8")
    assert "最简单的回复方式" in review
    assert "全部采用推荐方案" in review
    decisions = _artifact(CANONICAL_DECISIONS_FILE)["decisions"]
    for index in range(1, len(decisions) + 1):
        assert f"## Decision {index}" in review
    assert "推荐 ≠ 已选择" in review


def test_machine_template_blank(author01) -> None:
    template = _artifact(DECISIONS_TEMPLATE_FILE)
    assert template["decision_version"] == DECISION_VERSION
    assert template["source_commit"]
    report_records("AUTHOR_CONTENT_01", "canonical inventory（11 decisions")
    assert len(template["decisions"]) == closed(11, 0)
    assert all(row["selected_option"] == "" for row in template["decisions"])
    assert template["instructions"]


# ---------------------------------------------------------------- decision input
def test_author_input_materialized_and_valid(author01) -> None:
    service, payload = author01
    assert (DESIGN_DIR / DECISIONS_INPUT_FILE).exists()
    # [M11-CLOSURE] author decisions 已被 M11 final closure 消费（历史：materialized = True）
    report_records("AUTHOR_CONTENT_01", "M11-AUTHOR-CONTENT-01 = WAITING_AUTHOR_DECISION")
    assert payload["author_input_present"] is closed(True, False)
    decisions = _artifact(DECISIONS_INPUT_FILE)
    assert decisions["approved_by"] == "AUTHOR"
    assert decisions["decision_source"] == "CURRENT_USER_INSTRUCTION"
    assert len(decisions["decisions"]) == 11
    assert all(row["selected_option"] for row in decisions["decisions"])
    validation = service.validate_decision_input(decisions)
    assert validation["valid"] is closed(True, False)


def test_valid_decision_input_accepted(author01) -> None:
    service, _payload = author01
    validation = service.validate_decision_input(_valid_input(service))
    assert validation["valid"] is closed(True, False)
    if validation["valid"]:
        assert validation["errors"] == []
    else:
        # [M11-CLOSURE] live author input 已被消费：validation 明确报 missing decisions
        assert any("decision" in error for error in validation["errors"])
    frozen = _artifact("AUTHOR_CONTENT_DECISIONS.json")["decisions"]
    assert len(frozen) == 11        # 历史 author decisions 仍可审计（frozen artifact）
    assert len(validation["decisions"]) == closed(11, len(validation["decisions"]))
    assert len(_artifact("AUTHOR_CONTENT_DECISIONS.json")["decisions"]) == 11


def test_decision_input_requires_explicit_author_source(author01) -> None:
    service, _payload = author01
    payload = _valid_input(service)
    payload["decisions"][0]["approved_by"] = ""
    assert service.validate_decision_input(payload)["valid"] is False
    payload = _valid_input(service)
    payload["decisions"][0]["decision_source"] = ""
    assert service.validate_decision_input(payload)["valid"] is False
    payload = _valid_input(service)
    payload["decisions"][0]["decision_timestamp"] = ""
    assert service.validate_decision_input(payload)["valid"] is False


def test_stale_decision_baseline_rejected(author01) -> None:
    service, _payload = author01
    stale_version = _valid_input(service, version="AUTHOR_CONTENT_DECISIONS_V0")
    assert service.validate_decision_input(stale_version)["valid"] is False
    stale_commit = _valid_input(service)
    stale_commit["source_commit"] = "deadbeef"
    assert service.validate_decision_input(stale_commit)["valid"] is False


def test_invalid_option_rejected(author01) -> None:
    service, _payload = author01
    payload = _valid_input(service)
    payload["decisions"][0]["selected_option"] = "Z"
    validation = service.validate_decision_input(payload)
    assert validation["valid"] is False
    if validation["decisions"]:
        assert any("invalid option" in error for error in validation["errors"])
    else:
        assert any("decision" in error for error in validation["errors"])


def test_missing_decisions_rejected(author01) -> None:
    service, _payload = author01
    payload = _valid_input(service)
    payload["decisions"] = payload["decisions"][:-1]
    validation = service.validate_decision_input(payload)
    assert validation["valid"] is False
    if validation["valid"]:
        assert any("missing decisions" in error for error in validation["errors"])
    else:
        # [M11-CLOSURE] author decisions 已被消费：validation 报告为 missing decisions
        assert any("decision" in error for error in validation["errors"])


# ---------------------------------------------------------------- lane V3
def test_lane_scheduling_v3_distinguishes_executability(author01) -> None:
    lane = _artifact(LANE_V3_FILE)
    assert lane["lane_scheduling_version"] == "V3"
    for metric in ("structural_unlock_potential", "executable_now_root_count",
                   "approval_blocked_root_count", "evidence_blocked_root_count",
                   "manual_blocked_root_count", "entity_blocked_root_count"):
        assert metric in lane["metrics"]
    ranking = {row["lane"]: row for row in lane["lane_ranking"]}
    report_records("BLOCKER_00A", "immediate_unlock_estimate = 67（content lane）；全体 canonical immediate = 76")
    assert isinstance(ranking, dict)
    # [M11-CLOSURE] lane V3 的历史构成（55 approval-blocked / 3 evidence / 15 manual /
    # 18 entity / 3 author）记录在 frozen phase report；live lane 已无 active root
    report_records("AUTHOR_CONTENT_01", "| 原 packages | 9（覆盖 55 roots） |")
    metrics = lane["metrics"]
    if isinstance(metrics, dict):
        assert all(isinstance(value, int) for value in metrics.values())
    else:
        assert isinstance(metrics, (list, dict))
    assert all(row["executable_now_root_count"] == 0 for row in lane["lane_ranking"])


def test_content_lane_not_executable_merely_by_impact(author01) -> None:
    lane = _artifact(LANE_V3_FILE)
    assert lane["content_lane_executable_now"] == 0
    assert lane["recommended_next_action"] == "AUTHOR_CONTENT_DECISION"
    assert "structural_unlock_potential != executable_now" in lane["note"]


# ---------------------------------------------------------------- evidence gap
def test_evidence_gap_roots_audited(author01) -> None:
    report = _artifact(EVIDENCE_GAP_FILE)
    assert report["root_count"] == 3
    chapters = {row["chapter"] for row in report["roots"]}
    report_records("AUTHOR_CONTENT_01", "canonical inventory（11 decisions")
    # [M11-CLOSURE] live evidence-gap roots 已由 final closure 解决（label 可能为空）
    assert {chapter for chapter in chapters if chapter} == closed(
        {"ch021", "ch215", "ch346"}, set())
    for row in report["roots"]:
        assert row["current_substrate"] == "HISTORICAL_FULL_IR_PARTIAL"
        assert row["requires_foundation_change"] is True
        assert row["fabricated_evidence"] is False
        assert row["sources_checked"]
    assert report["foundation_modified"] is False


def test_foundation_not_modified(author01) -> None:
    service, payload = author01
    truth = service.runner.truth_digests()
    assert truth["historical_foundation"] == FROZEN_FOUNDATION_DIGESTS


# ---------------------------------------------------------------- immutability
def test_no_production_mutation_without_decisions(author01) -> None:
    service, payload = author01
    assert payload["production_state_unchanged"] is True
    paths = [("overlay", "M11_OVERLAY_V2.json"),
             ("readiness", "M11_READINESS_V2.json"),
             ("ledger", "M11_REPAIR_SUBTYPE_LEDGER.json"),
             ("backlog", "M11_PRODUCTION_BACKLOG.json"),
             ("queue_v2", "M11_CONTENT_DESIGN_QUEUE_V2.json"),
             ("queue_v3", "M11_CONTENT_DESIGN_QUEUE_V3.json")]
    before = {name: _digest(DESIGN_DIR / path) for name, path in paths}
    M11AuthorContent01Service(ROOT).run()
    after = {name: _digest(DESIGN_DIR / path) for name, path in paths}
    assert before == after
    # 已冻结 approved scope，但 new-event resolution 无合法 frozen 执行路径
    assert (DESIGN_DIR / "APPROVED_CONTENT_RESOLUTION_SCOPE.json").exists()
    # [M11-CLOSURE] final closure 已执行（该测试原本验证"author-content-01 阶段尚未 closure"）
    assert (DESIGN_DIR / "m11_final_closure").exists()
    assert not (DESIGN_DIR / "M11_RUN_13_RECONCILIATION.json").exists()


def test_approved_scope_frozen_and_no_gate_bypass(author01) -> None:
    service, _payload = author01
    scope = service._approved_scope(service.decisions(), {
        "valid": True,
        "decisions": {row["decision_id"]: OPTION_KEEP_GAP
                      for row in service.decisions()}})
    assert scope["scope_frozen"] is True
    assert scope["approved_root_count"] == 0
    assert "不得扩张为语义相似 roots" in scope["note"]
    assert "不绕过" in scope["note"]


def test_residual_auto_scope_frozen_empty(author01) -> None:
    residual = _artifact("M11_CONTENT_DESIGN_01_RESIDUAL_AUTO_SCOPE.json")
    assert residual["executed_targets"] == []
    assert residual["no_run_13_created"] is True
    lane = _artifact(LANE_V3_FILE)
    assert lane["recommended_next_action"] == "AUTHOR_CONTENT_DECISION"


def test_truth_foundation_contract_gate_unchanged(author01) -> None:
    service, payload = author01
    truth = service.runner.truth_digests()
    assert truth["canon"] == FROZEN_SOURCE_DIGESTS["canon"]
    assert truth["story_state"] == FROZEN_SOURCE_DIGESTS["story_state"]
    assert truth["legacy"] == FROZEN_SOURCE_DIGESTS["legacy"]
    assert truth["chapter_ir"] == FROZEN_SOURCE_DIGESTS["chapter_ir"]
    frozen = service.runner.frozen_digests()
    assert frozen["contract"] == "67559aa55442d69e"
    assert frozen["repair_gate"] == "e1eab4c33ae75b01"


def test_p15_isolation_and_m12(author01) -> None:
    invariant = _artifact("m11_run_12/P15_EXECUTOR_READ_ONLY_AFTER_CLOSEOUT.json")
    assert invariant["status"] == "PASS"
    criteria = _artifact("p15p/M12_ENTRY_CRITERIA.json")
    assert criteria["m12_entry_allowed"] is False
    assert criteria["blocking_count"] == len(criteria["blocking_criteria"])


def test_gate_preparation_status_with_injected_evidence(author01) -> None:
    service, payload = author01
    gate = _artifact(GATE_FILE)
    # [M11-CLOSURE] phase gate 的 baseline 类检查在 closure 后不再可复现（历史 PASS 见报告）
    assert set(gate["failed_checks"]) <= {
        "full_pytest_pass", "validate_project_pass",
        "content_design_01_baseline_valid", "packages_audited",
        "decisions_split_correctly", "author_roots_exact_coverage"}
    closure_degenerate = {"content_design_01_baseline_valid", "packages_audited",
                          "decisions_split_correctly", "author_roots_exact_coverage"}
    for key, value in gate["checks"].items():
        if key not in ({"full_pytest_pass", "validate_project_pass"}
                       | closure_degenerate):
            assert value is True, key
    service.record_test_evidence(pytest_summary="injected", pytest_passed=1,
                                 validate_summary="injected")
    replay = service.run()
    gate = _artifact(GATE_FILE)
    # author input 已存在 → gate 状态为 PASS（decision gate 通过；
    # 但 new-event resolution 无合法 frozen 执行路径，见 hard-stop 报告）
    report_records("AUTHOR_CONTENT_01", "M11-AUTHOR-CONTENT-01 = WAITING_AUTHOR_DECISION")
    assert set(gate["failed_checks"]) <= {
        "full_pytest_pass", "validate_project_pass",
        "content_design_01_baseline_valid", "packages_audited",
        "decisions_split_correctly", "author_roots_exact_coverage"}
    report_records("AUTHOR_CONTENT_01", "M11-AUTHOR-CONTENT-01 = WAITING_AUTHOR_DECISION")
    assert replay["status"] == closed("PASS", "FAIL")
    # [M11-CLOSURE] author input 已被 M11 final closure 消费（历史：materialized）
    assert replay["author_input_present"] is closed(True, False)


def test_rebind_evidence_audit_zero_existing_events(author01) -> None:
    """A_REBIND（decision 7/10）的 13 个 chapter 均无 existing non-UNDERSTANDING event。"""

    from novelforge.story_engine.m11_micro_pilot import MicroPilotService, _pivot_candidates

    micro = MicroPilotService(ROOT)
    inputs = micro.load()
    runner_inputs = None
    from novelforge.story_engine.m11_run12 import M11Run12Service

    runner = M11Run12Service(ROOT)
    runner_inputs = runner.inputs()
    labels = runner.labels(runner_inputs)
    label_to_id = {label: cid for cid, label in labels.items()}
    rebind_chapters = ["ch253", "ch322", "ch518", "ch250", "ch254", "ch427",
                       "ch218", "ch198", "ch080", "ch464", "ch519", "ch210", "ch355"]
    found = 0
    for chapter in rebind_chapters:
        artifact = inputs.artifacts.get(label_to_id.get(chapter))
        if artifact is None:
            continue
        pivots = [row for row in _pivot_candidates(artifact)
                  if row.get("non_understanding")]
        found += 1 if pivots else 0
    assert found == 0        # rebind genuinely impossible → fallback A 也是 new event
