"""M2A：Story Planning IR Validator 回归（引用 / DAG / 时间线 / 边界 / provenance）。"""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from novelforge.story_engine.planning import (
    RelationshipArc,
    PlanningValidator,
    StoryPlanningIR,
    validate_planning_ir,
)

FIXTURE = Path("tests/fixtures/planning_ir/ONE_SENTENCE_EXAMPLE.json")
KNOWN_ENTITIES = ["ENTITY_PROTAGONIST"]


def _raw() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def _plan(**mutations) -> StoryPlanningIR:
    return validate_planning_ir(_raw())


def _codes(raw: dict, *, previous: StoryPlanningIR | None = None,
           allow_external_refs: bool = True) -> list[str]:
    plan = validate_planning_ir(raw)
    validator = PlanningValidator(known_entity_ids=KNOWN_ENTITIES,
                                  allow_external_refs=allow_external_refs)
    return validator.validate(plan, previous=previous).codes()


def test_clean_example_has_no_findings() -> None:
    report = PlanningValidator(known_entity_ids=KNOWN_ENTITIES).validate(_plan())
    assert report.findings == []


def test_duplicate_stable_ids_are_rejected() -> None:
    raw = _raw()
    raw["plot_nodes"].append(copy.deepcopy(raw["plot_nodes"][0]))
    assert "DUPLICATE_PLANNING_ID" in _codes(raw)


def test_unknown_plot_node_reference_is_reported() -> None:
    raw = _raw()
    raw["arcs"][0]["plot_nodes"].append("NODE_GHOST")
    assert "PLANNING_REF_UNKNOWN" in _codes(raw)


def test_plot_node_dependency_and_self_reference() -> None:
    raw = _raw()
    raw["plot_nodes"][1]["prerequisites"] = ["NODE_GHOST"]
    assert "PLANNING_REF_UNKNOWN" in _codes(raw)
    raw = _raw()
    raw["plot_nodes"][1]["prerequisites"] = ["NODE_FAIL"]
    assert "PLANNING_SELF_REFERENCE" in _codes(raw)


def test_unknown_location_and_participant_references() -> None:
    raw = _raw()
    raw["plot_nodes"][1]["location_id"] = "LOC_GHOST"
    assert "PLANNING_REF_UNKNOWN" in _codes(raw)
    raw = _raw()
    raw["plot_nodes"][1]["participants"] = ["CHAR_GHOST"]
    assert "PLANNING_REF_UNKNOWN" in _codes(raw)
    raw = _raw()
    raw["characters"][0]["entity_ref"] = "ENTITY_GHOST"
    assert "PLANNING_REF_UNKNOWN" in _codes(raw, allow_external_refs=False)
    assert "PLANNING_REF_UNKNOWN" not in _codes(raw, allow_external_refs=True)


def test_relationship_arc_requires_two_distinct_participants() -> None:
    with pytest.raises(ValidationError):
        RelationshipArc(arc_id="RELARC_LIN", participants=["CHAR_LIN"])
    with pytest.raises(ValidationError):
        RelationshipArc(arc_id="RELARC_LIN", participants=["CHAR_LIN", "CHAR_LIN"])
    raw = _raw()
    raw["relationship_arcs"][0]["participants"] = ["CHAR_LIN", "CHAR_GHOST"]
    assert "PLANNING_REF_UNKNOWN" in _codes(raw)


def test_volume_and_arc_references_must_match() -> None:
    raw = _raw()
    raw["volumes"][0]["arc_ids"] = ["ARC_GHOST"]
    codes = _codes(raw)
    assert "PLANNING_REF_UNKNOWN" in codes
    assert "VOLUME_ARC_LIST_MISMATCH" in codes
    raw = _raw()
    raw["volumes"][0]["chapter_budget"] = 80
    assert "VOLUME_ARC_BUDGET_MISMATCH" in _codes(raw)
    raw = _raw()
    raw["arcs"][0]["chapter_budget"] = 0
    assert "ARC_BUDGET_MISSING" in _codes(raw)


def test_spine_must_be_causal_dag() -> None:
    raw = _raw()
    raw["spine"]["edges"].append({"from_node_id": "NODE_CLIMAX", "to_node_id": "NODE_ACCEPT",
                                  "relation": "causes"})
    assert "SPINE_CYCLE" in _codes(raw)
    raw = _raw()
    raw["spine"]["edges"] = raw["spine"]["edges"][1:]
    assert "SPINE_NODE_WITHOUT_CAUSE" in _codes(raw)
    raw = _raw()
    raw["spine"]["edges"] = []
    codes = _codes(raw)
    assert "SPINE_IS_BEAT_LADDER" in codes
    raw = _raw()
    raw["spine"]["edges"].append({"from_node_id": "NODE_ACCEPT", "to_node_id": "NODE_GHOST",
                                  "relation": "causes"})
    assert "SPINE_EDGE_NODE_NOT_IN_SPINE" in _codes(raw)


def test_empty_beat_node_is_reported() -> None:
    raw = _raw()
    raw["plot_nodes"].append({"node_id": "NODE_PADDING", "purpose": "第 4 个节拍"})
    assert "PLOT_NODE_EMPTY_BEAT" in _codes(raw)


def test_timeline_cannot_use_chapter_number_as_truth() -> None:
    raw = _raw()
    raw["timeline"]["story_timeline"][1]["anchor_node_id"] = ""
    raw["timeline"]["story_timeline"][1]["relative_to"] = []
    assert "TIMELINE_CHAPTER_AS_TRUTH" in _codes(raw)
    raw = _raw()
    raw["timeline"]["story_timeline"][1]["relative_to"] = ["TLE_GHOST"]
    assert "PLANNING_REF_UNKNOWN" in _codes(raw)
    raw = _raw()
    raw["timeline"]["story_timeline"][1]["anchor_node_id"] = "NODE_GHOST"
    assert "PLANNING_REF_UNKNOWN" in _codes(raw)


def test_timeline_confirmed_history_must_reference_canon() -> None:
    """裁决 2：已确认历史引用 Canon；假说 / 传说留在 Planning。"""

    raw = _raw()
    entry = raw["timeline"]["world_history"][0]
    entry["status"] = "confirmed"
    entry["provenance"] = "confirmed"
    entry["confirmation_ref"] = "svc://canon/confirm/9"
    assert "CONFIRMED_TIMELINE_WITHOUT_CANON_REF" in _codes(raw)
    entry["canon_event_ref"] = "EVENT_OLD_BRIDGE"
    assert "CONFIRMED_TIMELINE_WITHOUT_CANON_REF" not in _codes(raw)
    raw = _raw()
    legend = raw["timeline"]["world_history"][0]
    legend["status"] = "legend"
    legend["canon_event_ref"] = "EVENT_OLD_BRIDGE"
    assert "NON_FACT_TIMELINE_AS_CANON" in _codes(raw)
    legend["canon_event_ref"] = ""
    legend["provenance"] = "confirmed"
    legend["confirmation_ref"] = "svc://canon/confirm/9"
    assert "NON_FACT_TIMELINE_AS_CANON" in _codes(raw)


def test_information_moves_need_holders_and_known_truth() -> None:
    raw = _raw()
    raw["information_arcs"][0]["moves"][1]["holder_ids"] = []
    assert "INFORMATION_REVEAL_WITHOUT_HOLDER" in _codes(raw)
    raw = _raw()
    raw["information_arcs"][0]["moves"][1]["truth_id"] = "TRUTH_GHOST"
    assert "PLANNING_REF_UNKNOWN" in _codes(raw)


def test_foreshadow_plan_stays_planned() -> None:
    raw = _raw()
    raw["foreshadow_plans"][0]["moves"] = [move for move in raw["foreshadow_plans"][0]["moves"]
                                           if move["move_type"] != "plant"]
    assert "FORESHADOW_WITHOUT_PLANT" in _codes(raw)
    raw = _raw()
    raw["foreshadow_plans"][0]["payoff_node_id"] = "NODE_GHOST"
    assert "PLANNING_REF_UNKNOWN" in _codes(raw)


def test_progression_milestone_needs_node_and_price() -> None:
    raw = _raw()
    raw["progression_tracks"][0]["milestones"][0]["node_id"] = "NODE_GHOST"
    assert "PLANNING_REF_UNKNOWN" in _codes(raw)
    raw = _raw()
    raw["progression_tracks"][0]["milestones"][0]["requirement"] = ""
    raw["progression_tracks"][0]["milestones"][0]["cost"] = ""
    assert "PROGRESSION_MILESTONE_WITHOUT_PRICE" in _codes(raw)


def test_belief_and_rumor_cannot_become_canon_fact() -> None:
    raw = _raw()
    raw["world"]["world_rules"][1]["canon_fact_ref"] = "FACT_GHOST_1"
    assert "BELIEF_AS_CANON_FACT" in _codes(raw)


def test_planning_cannot_write_truth_status_in_raw_payload() -> None:
    report = PlanningValidator().validate_raw({"novel_id": "demo_001",
                                               "canon_status": "happened",
                                               "world": {"fact_status": "occurred"}})
    assert "PLANNING_WRITES_TRUTH_STATUS" in report.codes()
    assert report.ok() is False


def test_happened_claim_is_flagged() -> None:
    raw = _raw()
    raw["plot_nodes"][0]["state_change"] = "主角已经发生改变"
    assert "HAPPENED_CLAIM_IN_PLANNING" in _codes(raw)


def test_supplied_content_is_not_overwritten_by_generated() -> None:
    base = _plan()
    raw = _raw()
    raw["characters"][0]["external_goal"] = "换成别的目标"
    raw["characters"][0]["provenance"] = "generated"
    current = validate_planning_ir(raw)
    report = PlanningValidator(known_entity_ids=KNOWN_ENTITIES).validate(
        current, previous=base)
    assert "PROVENANCE_SUPPLIED_OVERWRITTEN" in report.codes()
    raw = _raw()
    raw["characters"][0]["external_goal"] = "作者自己改的目标"
    report = PlanningValidator(known_entity_ids=KNOWN_ENTITIES).validate(
        validate_planning_ir(raw), previous=base)
    assert "PROVENANCE_SUPPLIED_OVERWRITTEN" not in report.codes()


def test_pacing_weights_require_genre_template() -> None:
    raw = _raw()
    raw["pacing"]["intensity"] = {"tension": 0.5, "reward": 0.2}
    assert "PACING_TEMPLATE_NOT_DECLARED" in _codes(raw)
    raw = _raw()
    raw["pacing"]["intensity"] = {"tension": 0.5}
    raw["pacing"]["template_id"] = "external_template"
    assert "PACING_TEMPLATE_NOT_DECLARED" not in _codes(raw)


def test_detail_level_requires_the_structure_it_claims() -> None:
    """裁决 1：深度只声明自己真的具备的结构；不强制远期对象提前细化。"""

    raw = _raw()
    raw["arcs"][0]["detail_level"] = "chapter_ready"
    raw["arcs"][0]["decision_chain"] = []
    assert "ARC_DETAIL_LEVEL_INCOMPLETE" in _codes(raw)
    raw = _raw()
    raw["arcs"][0]["detail_level"] = "chapter_ready"
    assert "ARC_DETAIL_LEVEL_INCOMPLETE" not in _codes(raw)
    raw = _raw()
    raw["volumes"][0]["detail_level"] = "arc"
    raw["volumes"][0]["arc_ids"] = []
    assert "VOLUME_DETAIL_LEVEL_INCOMPLETE" in _codes(raw)
    raw = _raw()
    raw["volumes"][0]["detail_level"] = "spine"
    raw["volumes"][0]["arc_ids"] = []
    assert "VOLUME_DETAIL_LEVEL_INCOMPLETE" not in _codes(raw)


def test_plot_node_execution_volume_is_unique_after_scheduling() -> None:
    """裁决 5：排期后 execution volume 唯一；其它卷只能引用。"""

    raw = _raw()
    raw["plot_nodes"][1]["scheduled_volume_id"] = "VOL_GHOST"
    assert "SCHEDULED_NODE_UNKNOWN_VOLUME" in _codes(raw)
    raw = _raw()
    raw["volumes"].append({"volume_id": "VOL_TWO", "index": 2, "title": "第二卷",
                           "major_nodes": ["NODE_FAIL"], "chapter_budget": 40})
    raw["plot_nodes"][1]["scheduled_volume_id"] = "VOL_BRIDGE"
    assert "PLOT_NODE_EXECUTION_VOLUME_AMBIGUOUS" in _codes(raw)
    raw["plot_nodes"][1]["scheduled_volume_id"] = ""
    assert "PLOT_NODE_UNSCHEDULED_MULTI_VOLUME" in _codes(raw)
    raw = _raw()
    raw["plot_nodes"].append({"node_id": "NODE_LATE", "purpose": "尚未进入任何 arc",
                              "conflict": "远期冲突", "payoff": "远期回收",
                              "scheduled_volume_id": "VOL_BRIDGE"})
    assert "SCHEDULED_NODE_NOT_IN_VOLUME" in _codes(raw)


def test_cross_volume_reference_is_allowed_as_warning() -> None:
    raw = _raw()
    raw["volumes"].append({"volume_id": "VOL_TWO", "index": 2, "title": "第二卷",
                           "major_nodes": ["NODE_ACCEPT"], "chapter_budget": 40})
    raw["arcs"].append({"arc_id": "ARC_TWO", "volume_id": "VOL_TWO", "index": 1,
                        "plot_nodes": ["NODE_CLIMAX"], "chapter_budget": 40})
    codes = _codes(raw)
    assert "PLOT_NODE_CROSS_VOLUME_REFERENCE" in codes


def test_relationship_numeric_payload_is_rejected() -> None:
    """裁决 3：数值只能出现在 derived / analysis 层，不能成为关系真相。"""

    report = PlanningValidator().validate_raw({
        "novel_id": "demo_001",
        "relationship_arcs": [{"arc_id": "RELARC_A", "participants": ["CHAR_A", "CHAR_B"],
                               "trust": 78, "affection": 65.5,
                               "tension_score_derived": 0.4}]})
    assert "RELATIONSHIP_NUMERIC_AUTHORITATIVE" in report.codes()
    assert report.ok() is False
