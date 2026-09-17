"""C04：Canon 依赖图校验（时序/因果/knowledge/foreshadow/角色状态）。"""

from __future__ import annotations

from novelforge.story_engine.canon.graph import CanonGraph, CanonGraphValidator


def _codes(findings) -> set[str]:
    return {item["code"] for item in findings}


def test_causal_cycle_and_future_dependency() -> None:
    graph = CanonGraph.from_records(
        events=[{"event_id": "EVENT_A", "order": 5}, {"event_id": "EVENT_B", "order": 2}],
        dependencies=[{"from_id": "EVENT_A", "to_id": "EVENT_B", "relation": "CAUSES"},
                      {"from_id": "EVENT_B", "to_id": "EVENT_A", "relation": "REQUIRES"}])
    findings = CanonGraphValidator(graph).run()
    assert "CAUSAL_CYCLE" in _codes(findings)
    assert "FUTURE_FACT_DEPENDENCY" in _codes(findings)


def test_chronology_inversion_uses_tick_not_display_number() -> None:
    graph = CanonGraph.from_records(
        events=[{"event_id": "EVENT_LATE_TICK", "tick": 30, "display_number": 1},
                {"event_id": "EVENT_EARLY_TICK", "tick": 10, "display_number": 99}],
        dependencies=[{"from_id": "EVENT_LATE_TICK", "to_id": "EVENT_EARLY_TICK",
                       "relation": "REQUIRES"}])
    findings = CanonGraphValidator(graph).run()
    assert "FUTURE_FACT_DEPENDENCY" in _codes(findings)
    # display number 重排不会改变结论
    graph.graph.nodes["EVENT_LATE_TICK"]["display_number"] = 500
    graph.graph.nodes["EVENT_EARLY_TICK"]["display_number"] = 1
    assert "FUTURE_FACT_DEPENDENCY" in _codes(CanonGraphValidator(graph).run())


def test_foreshadow_order_and_knowledge_checks() -> None:
    graph = CanonGraph.from_records(
        facts=[{"fact_id": "FACT_PLANT", "order": 5}, {"fact_id": "FACT_REVEAL", "order": 9}],
        events=[{"event_id": "EVENT_RESOLVED", "order": 10, "status": "resolved"},
                {"event_id": "EVENT_REOPENED", "order": 14, "status": "planned",
                 "canonical_event_id": "EVENT_RESOLVED"}],
        knowledge=[{"knowledge_id": "KNW_A", "fact_id": "FACT_REVEAL", "order": 3,
                    "state": "known", "learned_from": ""},
                   {"knowledge_id": "KNW_B", "fact_id": "FACT_REVEAL", "order": 12,
                    "state": "known", "learned_from": "action:probe"}],
        foreshadows=[{"foreshadow_id": "FS_X", "plant_order": 9, "reveal_order": 5,
                      "payoff_order": 4, "plant_fact_id": "FACT_PLANT",
                      "payoff_fact_id": "FACT_REVEAL"}])
    findings = CanonGraphValidator(graph).run()
    codes = _codes(findings)
    assert {"REVEAL_BEFORE_PLANT", "PAYOFF_BEFORE_REVEAL", "KNOWLEDGE_BEFORE_FACT",
            "KNOWLEDGE_LEAK", "RESOLVED_EVENT_REOPENED"} <= codes


def test_prerequisite_and_state_checks() -> None:
    graph = CanonGraph()
    graph.add_node("EVENT_A", "event", order=5, prerequisites=["FACT_MISSING"],
                   requires_abilities=["ABILITY_LATE"], requires_identities=["IDENT_LATE"],
                   location="salt_road", participants=["hero"])
    graph.add_node("ABILITY_LATE", "fact", order=9)
    graph.add_node("IDENT_LATE", "fact", order=9)
    graph.add_node("hero", "entity", order=0, dead_at=3, locations=["camp"])
    graph.add_edge("hero", "EVENT_A", "PARTICIPATES_IN")
    findings = CanonGraphValidator(graph).run()
    codes = _codes(findings)
    assert {"PREREQUISITE_MISSING", "ABILITY_BEFORE_UNLOCK", "IDENTITY_BEFORE_ACQUIRED",
            "DEAD_CHARACTER_ACTION", "LOCATION_IMPOSSIBILITY"} <= codes


def test_clean_graph_has_no_findings() -> None:
    graph = CanonGraph.from_records(
        facts=[{"fact_id": "FACT_1", "order": 1}],
        events=[{"event_id": "EVENT_1", "order": 2, "status": "occurred"}],
        knowledge=[{"knowledge_id": "KNW_1", "fact_id": "FACT_1", "order": 3,
                    "state": "known", "learned_from": "action:probe"}])
    assert CanonGraphValidator(graph).run() == []
