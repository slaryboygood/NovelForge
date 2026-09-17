"""M5：Long-form Planning Systems 回归。

覆盖：Requirement 系统、ResourceLedger、Equipment lifecycle、Base / Map expansion、
Progression / Information / Foreshadow 分析、RewardCadence、Autonomous action、
FactionRelation、PlanningHealthReport、projection 与跨题材中立性。
"""

from __future__ import annotations

import copy
import json
from pathlib import Path

from novelforge.story_engine.planning import (
    PlanningGraphValidator,
    StoryPlanningContextBuilder,
    analyze_autonomous_actions,
    analyze_base_progression,
    analyze_equipment,
    analyze_faction_relations,
    analyze_foreshadow,
    analyze_information,
    analyze_map_expansion,
    analyze_planning_health,
    analyze_progression,
    analyze_reward_cadence,
    base_stage_order,
    build_planning_graphs,
    build_resource_ledger,
    equipment_lifecycle_order,
    evaluate_requirements,
    faction_relation_edges,
    legacy_requirement_group,
    planning_digest,
    pressure_report,
    reward_cadence_rows,
    stage_trigger_node,
    summarize_longform,
    summarize_plan,
    validate_planning_ir,
    validate_requirements,
    validate_resources,
)

FIXTURES = Path("tests/fixtures/planning_ir")
URBAN = "URBAN_GROWTH_EXAMPLE.json"
BASE = "ONE_SENTENCE_EXAMPLE.json"
LONGFORM_DIR = Path("src/novelforge/story_engine/planning")


def _raw(name: str = URBAN) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def _plan(name: str = URBAN):
    return validate_planning_ir(_raw(name))


def _mutated(mutator, name: str = URBAN):
    raw = _raw(name)
    mutator(raw)
    return validate_planning_ir(raw)


def _codes(report) -> set[str]:
    return set(report.codes())


def _severity(report, code: str) -> list[str]:
    return [item.severity for item in report.findings if item.code == code]


# ---------------------------------------------------------------- requirements
def test_requirement_refs_and_group_semantics() -> None:
    plan = _plan()
    report = validate_requirements(plan, revision_id="PREV_REQ")
    assert report.ok(), report.findings
    location = next(item for item in plan.locations if item.location_id == "LOC_MARKET")
    group = location.entry_requirement_group
    assert group is not None and group.operator == "all"
    assert evaluate_requirements(group, available=["RULE_PERMIT"]).satisfied is True
    missing = evaluate_requirements(group, available=[])
    assert missing.satisfied is False and missing.missing()
    assert evaluate_requirements(None, available=[]).satisfied is True
    assert evaluate_requirements(group, available=[]).context_source == "supplied"


def test_requirement_unknown_ref_and_legacy_conversion() -> None:
    def mutate(data):
        data["locations"][1]["entry_requirement_group"] = {
            "operator": "all",
            "requirements": [{"requirement_id": "REQ_GHOST", "kind": "world_rule",
                              "ref_id": "RULE_GHOST"}]}
    report = validate_requirements(_mutated(mutate))
    assert "REQUIREMENT_UNKNOWN_REF" in _codes(report)
    assert _severity(report, "REQUIREMENT_UNKNOWN_REF") == ["ERROR"]
    plain = legacy_requirement_group("需要镇务会放行")
    assert plain is not None and plain.requirements[0].ref_id == ""
    token = legacy_requirement_group("必须先满足 RULE_PERMIT 才能接单")
    assert token is not None and token.requirements[0].ref_id == "RULE_PERMIT"
    assert token.requirements[0].kind == "world_rule"
    assert legacy_requirement_group("") is None


def test_explicit_trigger_node_wins_over_legacy_text() -> None:
    plan = _plan()
    stage = plan.relationship_arcs[0].stages[0]
    assert stage_trigger_node(stage) == "NODE_OPEN"
    text_only = stage.model_copy(update={"trigger_node_id": "", "trigger": "在 NODE_STOCK 谈判"})
    assert stage_trigger_node(text_only) == "NODE_STOCK"

    def mutate(data):
        data["relationship_arcs"][0]["stages"][0]["trigger_node_id"] = "NODE_GHOST"
    report = PlanningGraphValidator(known_entity_ids=["ENTITY_PROTAGONIST"]).validate(
        _mutated(mutate))
    assert _severity(report, "STAGE_TRIGGER_NODE_UNKNOWN") == ["ERROR"]


# ---------------------------------------------------------------- resources
def test_resource_ledger_conservation_and_units() -> None:
    plan = _plan()
    ledger = build_resource_ledger(plan, revision_id="PREV_RES")
    assert ledger.read_only is True and ledger.non_authoritative is True
    material = ledger.row("PLANNED_MATERIAL_1")
    assert material is not None
    assert material.produced == 140 and material.consumed == 40
    assert material.planned_balance == 100
    assert material.planning_only is True
    credit = ledger.row("RES_CREDIT")
    assert credit is not None and credit.produced == 3000
    report = validate_resources(plan, revision_id="PREV_RES")
    assert report.ok(), report.findings
    assert _severity(report, "RESOURCE_PLANNING_ONLY_IDENTITY") == ["INFO"]


def test_resource_unit_mismatch_and_unknown_resource() -> None:
    def mutate(data):
        data["resource_flows"][0]["unit_id"] = "UNIT_COUNT"
    report = validate_resources(_mutated(mutate))
    assert _severity(report, "RESOURCE_UNIT_MISMATCH") == ["ERROR"]

    def unknown(data):
        data["resource_flows"].append({"flow_id": "RFLOW_GHOST", "resource_id": "RES_GHOST",
                                       "flow_type": "acquire", "amount": 1,
                                       "unit_id": "UNIT_COUNT"})
    assert "RESOURCE_UNKNOWN" in _codes(validate_resources(_mutated(unknown)))


def test_resource_consume_before_acquire_and_negative_balance() -> None:
    def mutate(data):
        data["resource_flows"] = [flow for flow in data["resource_flows"]
                                  if flow["flow_id"] not in ("RFLOW_BUY", "RFLOW_REFILL",
                                                             "RFLOW_STORE", "RFLOW_USE")]
        data["resource_flows"].append({"flow_id": "RFLOW_LATE",
                                       "planned_resource_id": "PLANNED_MATERIAL_1",
                                       "flow_type": "acquire", "amount": 10,
                                       "unit_id": "UNIT_COUNT",
                                       "trigger_node_id": "NODE_BRANCH"})
        data["resource_flows"].append({"flow_id": "RFLOW_EARLY_USE",
                                       "planned_resource_id": "PLANNED_MATERIAL_1",
                                       "flow_type": "consume", "amount": 40,
                                       "unit_id": "UNIT_COUNT",
                                       "trigger_node_id": "NODE_OPEN"})
    report = validate_resources(_mutated(mutate))
    assert "RESOURCE_CONSUME_BEFORE_ACQUIRE" in _codes(report)
    assert _severity(report, "RESOURCE_NEGATIVE_BALANCE") == ["ERROR"]


def test_resource_storage_overflow_duplicate_and_nonrenewable() -> None:
    def overflow(data):
        data["resource_flows"] = [flow for flow in data["resource_flows"]
                                  if flow["flow_id"] != "RFLOW_STORE"]
        data["resource_flows"].append({"flow_id": "RFLOW_STORE_BIG",
                                       "planned_resource_id": "PLANNED_MATERIAL_1",
                                       "flow_type": "store", "amount": 500,
                                       "unit_id": "UNIT_COUNT",
                                       "trigger_node_id": "NODE_STOCK"})
    assert "RESOURCE_STORAGE_OVERFLOW" in _codes(validate_resources(_mutated(overflow)))

    def duplicate(data):
        data["resource_flows"].append({"flow_id": "RFLOW_USE2",
                                       "planned_resource_id": "PLANNED_MATERIAL_1",
                                       "flow_type": "consume", "amount": 5,
                                       "unit_id": "UNIT_COUNT",
                                       "trigger_node_id": "NODE_BRANCH",
                                       "irreversible": True})
    assert "RESOURCE_DUPLICATE_IRREVERSIBLE" in _codes(
        validate_resources(_mutated(duplicate)))

    def infinite(data):
        data["resource_flows"].append({"flow_id": "RFLOW_INF",
                                       "planned_resource_id": "PLANNED_MATERIAL_1",
                                       "flow_type": "produce", "amount": 10,
                                       "unit_id": "UNIT_COUNT",
                                       "trigger_node_id": "NODE_STOCK",
                                       "repeatability": "unbounded"})
    assert "RESOURCE_NONRENEWABLE_INFINITE" in _codes(
        validate_resources(_mutated(infinite)))


# ---------------------------------------------------------------- equipment
def test_equipment_lifecycle_is_clean_and_read_only() -> None:
    plan = _plan()
    assert analyze_equipment(plan, revision_id="PREV_EQ").ok()
    caliper = next(item for item in plan.equipment_plans
                   if item.equipment_id == "EQ_CALIPER")
    rows = equipment_lifecycle_order(caliper, plan)
    assert [row["state"] for row in rows] == ["acquired", "damaged", "repaired"]
    assert all(row["order"] is not None for row in rows)


def test_equipment_upgrade_before_acquire_and_use_after_loss() -> None:
    def upgrade_first(data):
        plan = data["equipment_plans"][0]
        plan["upgrade_nodes"] = ["NODE_OPEN"]
        plan["acquisition_node"] = "NODE_BRANCH"
    assert _severity(analyze_equipment(_mutated(upgrade_first)),
                     "EQUIPMENT_UPGRADE_BEFORE_ACQUIRE") == ["ERROR"]

    def use_after_loss(data):
        plan = data["equipment_plans"][0]
        plan["loss_node"] = "NODE_OPEN"
        plan["repair_nodes"] = ["NODE_BRANCH"]
    assert "EQUIPMENT_USE_AFTER_LOSS" in _codes(analyze_equipment(_mutated(use_after_loss)))


def test_equipment_repair_before_damage_and_transfer_without_owner() -> None:
    def no_damage(data):
        data["equipment_plans"][0]["damage_nodes"] = []
    assert "EQUIPMENT_REPAIR_BEFORE_DAMAGE" in _codes(
        analyze_equipment(_mutated(no_damage)))

    def transfer(data):
        plan = data["equipment_plans"][0]
        plan["transfer_nodes"] = ["NODE_BRANCH"]
        plan["owner_ref"] = ""
    assert "EQUIPMENT_TRANSFER_WITHOUT_OWNERSHIP" in _codes(
        analyze_equipment(_mutated(transfer)))


def test_equipment_double_ownership_and_duplicate_unique() -> None:
    def duplicate(data):
        clone = copy.deepcopy(data["equipment_plans"][0])
        clone["equipment_id"] = "EQ_CALIPER_B"
        clone["owner_ref"] = "CHAR_YAO"
        data["equipment_plans"].append(clone)
    report = analyze_equipment(_mutated(duplicate))
    assert "EQUIPMENT_DOUBLE_OWNERSHIP" in _codes(report)
    assert "EQUIPMENT_DUPLICATE_UNIQUE" in _codes(report)


def test_consumable_consume_then_reuse_is_an_error() -> None:
    def mutate(data):
        plan = data["equipment_plans"][1]
        plan["upgrade_nodes"] = ["NODE_BRANCH"]
        plan["consume_node"] = "NODE_STOCK"
    assert "EQUIPMENT_CONSUME_THEN_REUSE" in _codes(analyze_equipment(_mutated(mutate)))


# ---------------------------------------------------------------- base / map
def test_base_progression_ordering_and_requirements() -> None:
    plan = _plan()
    assert analyze_base_progression(plan, revision_id="PREV_BASE").ok()
    rows = base_stage_order(plan, "BASE_STUDIO")
    assert [row["stage_id"] for row in rows] == ["BASESTAGE_ONE", "BASESTAGE_TWO"]

    def duplicate(data):
        data["base_progressions"][0]["stages"][1]["label"] = "单工位"
    assert "BASE_STAGE_ORDER" in _codes(analyze_base_progression(_mutated(duplicate)))

    def dangling(data):
        data["base_progressions"][0]["stages"][1]["territory"] = ["LOC_GHOST"]
    assert "BASE_TERRITORY_DANGLING" in _codes(
        analyze_base_progression(_mutated(dangling)))


def test_map_expansion_reachability_and_stage_rules() -> None:
    plan = _plan()
    report = analyze_map_expansion(plan, revision_id="PREV_MAP")
    assert report.ok(), report.findings
    assert _severity(report, "MAP_EXPANSION_UNSATISFIED_REQUIREMENT") == ["WARNING"]

    def stage_order(data):
        data["map_expansions"][0]["milestones"][0]["to_stage"] = "unknown"
    assert "MAP_EXPANSION_STAGE_ORDER" in _codes(
        analyze_map_expansion(_mutated(stage_order)))

    def controlled_first(data):
        milestones = data["map_expansions"][0]["milestones"]
        data["map_expansions"][0]["milestones"] = [
            item for item in milestones if item["location_ref"] != "LOC_BRANCH"]
        data["map_expansions"][0]["milestones"].append(
            {"milestone_id": "MAPMILE_BRANCH_CTRL", "location_ref": "LOC_BRANCH",
             "from_stage": "unknown", "to_stage": "controlled",
             "trigger_node_id": "NODE_BRANCH"})
    assert "MAP_EXPANSION_CONTROLLED_BEFORE_REACHABLE" in _codes(
        analyze_map_expansion(_mutated(controlled_first)))


def test_map_expansion_structural_path_and_unknown_location() -> None:
    def no_path(data):
        data["location_graph"]["edges"] = [
            edge for edge in data["location_graph"]["edges"]
            if edge["to_location_id"] != "LOC_BRANCH"]
    assert _severity(analyze_map_expansion(_mutated(no_path)),
                     "MAP_EXPANSION_NO_STRUCTURAL_PATH") == ["ERROR"]

    def unknown(data):
        data["map_expansions"][0]["milestones"].append(
            {"milestone_id": "MAPMILE_GHOST", "location_ref": "LOC_GHOST",
             "from_stage": "unknown", "to_stage": "known"})
    assert "MAP_EXPANSION_UNKNOWN_LOCATION" in _codes(
        analyze_map_expansion(_mutated(unknown)))


def test_map_expansion_rate_anomaly_is_warning() -> None:
    def busy_trigger(data):
        for index in range(3):
            data["map_expansions"][0]["milestones"].append(
                {"milestone_id": f"MAPMILE_EXTRA_{index}", "location_ref": "LOC_GARAGE",
                 "from_stage": "known", "to_stage": "reachable",
                 "trigger_node_id": "NODE_OPEN"})
    assert _severity(analyze_map_expansion(_mutated(busy_trigger)),
                     "MAP_EXPANSION_RATE_ANOMALY") == ["WARNING"]


# ---------------------------------------------------------------- progression / information / foreshadow
def test_progression_ordering_and_major_without_cost() -> None:
    assert analyze_progression(_plan(), revision_id="PREV_PROG").codes() == []

    def no_cost(data):
        milestone = data["progression_tracks"][0]["milestones"][0]
        milestone["cost"] = ""
        milestone["requirement"] = ""
    report = analyze_progression(_mutated(no_cost))
    assert _severity(report, "PROGRESSION_MAJOR_WITHOUT_COST") == ["WARNING"]


def test_progression_duplicate_upgrade_regression_and_plateau() -> None:
    def duplicate(data):
        data["progression_tracks"][0]["milestones"][1]["node_id"] = "NODE_OPEN"
    assert "PROGRESSION_DUPLICATE_UPGRADE" in _codes(
        analyze_progression(_mutated(duplicate)))

    def regression(data):
        data["timeline"]["story_timeline"][0]["sequence_order"] = 5
    assert "PROGRESSION_ORDER_REGRESSION" in _codes(
        analyze_progression(_mutated(regression)))

    def plateau(data):
        for milestone in data["progression_tracks"][0]["milestones"]:
            milestone["cost"] = ""
            milestone["requirement"] = ""
    assert "PROGRESSION_PLATEAU" in _codes(analyze_progression(_mutated(plateau)))


def test_information_reveal_order_and_knowledge_leak() -> None:
    plan = _plan()
    assert analyze_information(plan, revision_id="PREV_INFO").codes() == []

    def reveal_first(data):
        data["information_arcs"][0]["moves"][0]["move_type"] = "reveal"
        data["information_arcs"][0]["moves"][2]["move_type"] = "plant"
    assert _severity(analyze_information(_mutated(reveal_first)),
                     "INFORMATION_REVEAL_BEFORE_PLANT") == ["ERROR"]

    def leak(data):
        data["information_arcs"][0]["moves"] = []
    assert "INFORMATION_KNOWLEDGE_LEAK" in _codes(
        analyze_information(_mutated(leak)))

    def false_belief(data):
        data["information_arcs"][0]["moves"][2]["node_id"] = "NODE_STOCK"
        data["information_arcs"][0]["moves"].append(
            {"move_id": "IMOVE_FALSE", "truth_id": "TRUTH_COST",
             "move_type": "false_belief", "node_id": "NODE_BRANCH",
             "holder_ids": ["CHAR_CHEN"]})
    assert "INFORMATION_FALSE_BELIEF_WITHOUT_REVEAL" in _codes(
        analyze_information(_mutated(false_belief)))


def test_foreshadow_lifecycle_rules() -> None:
    assert analyze_foreshadow(_plan(), revision_id="PREV_FS").ok()

    def no_plant(data):
        moves = data["foreshadow_plans"][0]["moves"]
        data["foreshadow_plans"][0]["moves"] = [move for move in moves
                                                if move["move_type"] != "plant"]
    assert "FORESHADOW_REVEAL_WITHOUT_PLANT" in _codes(
        analyze_foreshadow(_mutated(no_plant)))

    def duplicate_payoff(data):
        clone = copy.deepcopy(data["foreshadow_plans"][0]["moves"][-1])
        clone["move_id"] = "FSMOVE_PAYOFF_2"
        data["foreshadow_plans"][0]["moves"].append(clone)
    report = analyze_foreshadow(_mutated(duplicate_payoff))
    assert _severity(report, "FORESHADOW_DUPLICATE_PAYOFF") == ["ERROR"]
    assert "FORESHADOW_DENSE_HINTS" in report.codes()


def test_foreshadow_payoff_without_reveal_is_configurable() -> None:
    def drop_reveal(data):
        moves = data["foreshadow_plans"][0]["moves"]
        data["foreshadow_plans"][0]["moves"] = [move for move in moves
                                                if move["move_type"] != "reveal"]
    default = analyze_foreshadow(_mutated(drop_reveal))
    assert _severity(default, "FORESHADOW_PAYOFF_WITHOUT_REVEAL") == ["WARNING"]
    strict = analyze_foreshadow(_mutated(drop_reveal), require_reveal_before_payoff=True)
    assert _severity(strict, "FORESHADOW_PAYOFF_WITHOUT_REVEAL") == ["ERROR"]


# ---------------------------------------------------------------- rewards
def test_reward_cadence_rows_and_clean_plan() -> None:
    plan = _plan()
    rows = reward_cadence_rows(plan)
    assert [row["reward_id"] for row in rows] == [
        "REWARD_FIRST_ORDER", "REWARD_TOOL_SAVED", "REWARD_BRANCH_OPEN"]
    report = analyze_reward_cadence(plan, revision_id="PREV_RW")
    assert report.ok(), report.findings
    assert report.codes() == []


def test_reward_drought_and_clustering() -> None:
    def drought(data):
        data["reward_plans"][0]["events"] = data["reward_plans"][0]["events"][:1]
        data["timeline"]["story_timeline"].append(
            {"entry_id": "TLE_FAR", "label": "很久以后", "sequence_order": 30,
             "anchor_node_id": "NODE_BRANCH", "provenance": "generated"})
    assert "REWARD_LONG_DROUGHT" in _codes(analyze_reward_cadence(_mutated(drought)))

    def cluster(data):
        events = data["reward_plans"][0]["events"]
        clone = copy.deepcopy(events[0])
        clone["reward_id"] = "REWARD_FIRST_ORDER_B"
        events.append(clone)
    assert "REWARD_CLUSTERING" in _codes(analyze_reward_cadence(_mutated(cluster)))


def test_reward_repetition_major_without_setup_and_climax_missing() -> None:
    def repeat(data):
        for event in data["reward_plans"][0]["events"]:
            event["reward_type"] = "status"
    assert "REPETITIVE_REWARD_TYPE" in _codes(analyze_reward_cadence(_mutated(repeat)))

    def bare_major(data):
        event = data["reward_plans"][0]["events"][2]
        event["payoff_ref"] = ""
        event["cost_ref"] = ""
        event["description"] = ""
        event["delayed"] = False
    report = analyze_reward_cadence(_mutated(bare_major))
    assert "MAJOR_REWARD_WITHOUT_SETUP" in _codes(report)
    assert "REWARD_WITHOUT_COST_OR_PRESSURE" in _codes(report)

    def drop_climax(data):
        data["reward_plans"][0]["events"] = [
            item for item in data["reward_plans"][0]["events"]
            if item["reward_id"] != "REWARD_BRANCH_OPEN"]
    assert "CLIMAX_REWARD_MISSING" in _codes(
        analyze_reward_cadence(_mutated(drop_climax)))


def test_reward_domain_unused_is_not_an_error() -> None:
    assert analyze_reward_cadence(_plan(BASE)).codes() == []


# ---------------------------------------------------------------- autonomous / faction relation
def test_autonomous_actions_do_not_require_protagonist() -> None:
    plan = _plan()
    report = analyze_autonomous_actions(plan, revision_id="PREV_ACT")
    assert report.ok(), report.findings
    assert all(not item.requires_protagonist_presence for item in plan.autonomous_actions)
    assert "AUTONOMOUS_ALWAYS_PROTAGONIST_DEPENDENT" not in _codes(report)

    def dependent(data):
        for action in data["autonomous_actions"]:
            action["requires_protagonist_presence"] = True
    assert "AUTONOMOUS_ALWAYS_PROTAGONIST_DEPENDENT" in _codes(
        analyze_autonomous_actions(_mutated(dependent)))


def test_autonomous_actor_trigger_and_information_dependency() -> None:
    def unknown_actor(data):
        data["autonomous_actions"][0]["actor_ref"] = "FACTION_GHOST"
    assert "AUTONOMOUS_ACTOR_UNKNOWN" in _codes(
        analyze_autonomous_actions(_mutated(unknown_actor)))

    def unknown_trigger(data):
        data["autonomous_actions"][0]["trigger_ref"] = "NODE_GHOST"
    assert "AUTONOMOUS_TRIGGER_UNKNOWN" in _codes(
        analyze_autonomous_actions(_mutated(unknown_trigger)))

    def not_informed(data):
        data["autonomous_actions"][1]["information_dependency"] = ["TRUTH_COST"]
    assert _severity(analyze_autonomous_actions(_mutated(not_informed)),
                     "AUTONOMOUS_ACTOR_NOT_INFORMED") == ["ERROR"]

    def dependency(data):
        data["autonomous_actions"][0]["information_dependency"] = ["TRUTH_GHOST"]
    assert "AUTONOMOUS_INFORMATION_DEPENDENCY_UNKNOWN" in _codes(
        analyze_autonomous_actions(_mutated(dependency)))


def test_autonomous_location_reachability_and_pressure_report() -> None:
    def unreachable(data):
        data["autonomous_actions"][0]["location_ref"] = "LOC_GHOST"
    assert "AUTONOMOUS_LOCATION_UNKNOWN" in _codes(
        analyze_autonomous_actions(_mutated(unreachable)))
    rows = pressure_report(_plan(), "BASE_STUDIO")
    assert any(row["faction_id"] == "FACTION_CHAIN" for row in rows)
    assert all(row["non_authoritative"] is True for row in rows)


def test_faction_relations_validation_and_projection() -> None:
    plan = _plan()
    assert analyze_faction_relations(plan, revision_id="PREV_FREL").ok()
    edges = faction_relation_edges(plan)
    assert {edge["kind"] for edge in edges} == {"dependency", "competition"}
    assert all(edge["non_authoritative"] is True for edge in edges)
    bundle = build_planning_graphs(plan)
    assert any(edge.metadata.get("relation_type") == "dependency"
               for edge in bundle.faction.edges)

    def contradiction(data):
        data["factions"][0]["allies"] = ["FACTION_SUPPLIER"]
        data["faction_relations"].append(
            {"relation_id": "FREL_CONFLICT", "relation_type": "hostility",
             "from_faction_id": "FACTION_CHAIN", "to_faction_id": "FACTION_SUPPLIER"})
    assert "FACTION_RELATION_CONTRADICTION" in _codes(
        analyze_faction_relations(_mutated(contradiction)))

    def duplicate(data):
        data["faction_relations"].append(copy.deepcopy(data["faction_relations"][0]))
    assert "FACTION_RELATION_DUPLICATE" in _codes(
        analyze_faction_relations(_mutated(duplicate)))


# ---------------------------------------------------------------- health / projection / context
def test_planning_health_report_states_and_domains() -> None:
    plan = _plan()
    health = analyze_planning_health(plan, revision_id="PREV_HEALTH",
                                     known_entity_ids=("ENTITY_PROTAGONIST",))
    assert health.read_only is True
    names = {item.domain for item in health.domains}
    assert {"progression", "resource", "equipment", "base", "map", "information",
            "foreshadow", "reward", "autonomous", "faction_relation", "graph"} <= names
    assert health.content_digest == planning_digest(plan)

    def break_resources(data):
        data["resource_flows"][0]["unit_id"] = "UNIT_COUNT"
    blocked = analyze_planning_health(_mutated(break_resources))
    assert blocked.overall_state == "blocked"
    assert blocked.domain("resource").state == "blocked"


def test_longform_projection_is_read_only_and_complete() -> None:
    plan = _plan()
    before = planning_digest(plan)
    summaries = summarize_longform(plan, revision_id="PREV_LF")
    assert planning_digest(plan) == before
    assert summaries.read_only is True and summaries.non_authoritative is True
    assert summaries.resources.resource_count == 2
    assert summaries.resources.deficits == []
    assert summaries.equipment.equipment_count == 2
    assert summaries.base.base_count == 1
    assert summaries.map_expansion.milestone_count == 6
    assert summaries.information.truth_count == 1
    assert summaries.reward.reward_count == 3
    assert summaries.autonomous.action_count == 2
    assert summaries.faction_relation.relation_count == 2
    assert summaries.progression.track_count == 1
    assert summarize_plan(plan, with_graph=True).graph is not None


def test_context_slices_for_longform_purposes() -> None:
    plan = _plan()
    bundle = build_planning_graphs(plan, revision_id="PREV_CTX")
    builder = StoryPlanningContextBuilder(plan, revision_id="PREV_CTX", graphs=bundle)
    assert set(builder.build("resource").payload) == {
        "unit_defs", "resource_plans", "resource_flows"}
    assert len(builder.build("equipment").payload["equipment_plans"]) == 2
    assert builder.build("base").payload["base_progressions"][0]["base_id"] == "BASE_STUDIO"
    map_context = builder.build("map")
    assert map_context.payload["map_expansions"] and map_context.payload["graph"]
    autonomous = builder.build("autonomous_action")
    assert len(autonomous.payload["autonomous_actions"]) == 2
    assert autonomous.payload["faction_relations"]
    assert builder.build("reward").payload["reward_plans"][0]["events"]


def test_longform_modules_have_no_genre_or_fixed_cadence_hardcoding() -> None:
    offenders: list[str] = []
    for name in ("requirements.py", "resource_planning.py", "equipment_planning.py",
                 "base_map.py", "narrative_analysis.py", "rewards.py",
                 "autonomous_actions.py", "health.py", "longform_projection.py"):
        text = (LONGFORM_DIR / name).read_text(encoding="utf-8")
        for term in ("wasteland", "废土", "xianxia", "修仙", "爽文", "每 5 章", "每章必须"):
            if term in text:
                offenders.append(f"{name}: {term}")
    assert offenders == []


def test_cross_genre_fixtures_pass_longform_analyzers() -> None:
    """现实 / 都市 / 奇幻共用同一套 long-form engine；未使用某 domain 不算错误。"""

    for name in (BASE, "MODERN_CITY_EXAMPLE.json", URBAN, "FANTASY_EXAMPLE.json"):
        plan = _plan(name)
        health = analyze_planning_health(plan, known_entity_ids=("ENTITY_PROTAGONIST",))
        errors = [item.code for item in health.findings if item.severity == "ERROR"]
        assert errors == [], (name, errors)
        first = summarize_longform(plan).model_dump_json()
        assert summarize_longform(plan).model_dump_json() == first
