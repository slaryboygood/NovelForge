"""C08：SemanticIndex（candidate + 结构化分类；threshold 不直接判 duplicate）。"""

from __future__ import annotations

from novelforge.story_engine.canon.semantic import EventSemanticSignature, LocalSemanticIndex


def _sig(event_id: str, summary: str, **overrides) -> EventSemanticSignature:
    base = dict(event_id=event_id, semantic_summary=summary, subjects=["black_tower", "caravan",
                                                                       "seam_house"],
                action="三方同时递交结盟条件", location="settlement_core", event_type="major")
    base.update(overrides)
    return EventSemanticSignature(**base)


def test_paraphrased_major_event_is_high_candidate() -> None:
    index = LocalSemanticIndex()
    index.index_event(_sig("EVENT_A", "三方同时递来三份结盟书"))
    other = _sig("EVENT_B", "三方同日在聚落提出合作条件")
    candidates = index.candidates(other, top_k=3, threshold=0.3)
    assert candidates and candidates[0].event_id == "EVENT_A"
    assert candidates[0].score >= 0.3
    assert candidates[0].relation in ("duplicate", "uncertain")


def test_explicit_consequence_and_payoff_are_not_duplicates() -> None:
    index = LocalSemanticIndex()
    canonical = _sig("EVENT_CANON", "三方同时递交结盟条件")
    index.index_event(canonical)
    consequence = _sig("EVENT_AFTER", "三方同时递交结盟条件", canonical_event_id="EVENT_CANON",
                       narrative_role="consequence")
    assert index.classify_relation(canonical, consequence) == "consequence"
    payoff = _sig("EVENT_PAYOFF", "三方同时递交结盟条件", canonical_event_id="EVENT_CANON",
                  narrative_role="payoff")
    assert index.classify_relation(canonical, payoff) == "payoff"
    candidates = index.candidates(consequence, top_k=3, threshold=0.3)
    assert all(item.relation != "duplicate" for item in candidates)


def test_repeatable_recurrence_is_not_major_duplicate() -> None:
    index = LocalSemanticIndex()
    index.index_event(_sig("EVENT_PATROL_1", "例行巡逻经过盐路", event_type="patrol",
                           can_repeat=True, action="巡逻", subjects=["patrol_team"]))
    second = _sig("EVENT_PATROL_2", "巡逻队再次经过同一路段", event_type="patrol",
                  can_repeat=True, narrative_role="recurrence", action="巡逻",
                  subjects=["patrol_team"])
    assert index.classify_relation(index.get_event("EVENT_PATROL_1"), second) == \
        "legitimate_recurrence"


def test_same_subject_different_action_is_not_duplicate() -> None:
    index = LocalSemanticIndex()
    a = _sig("EVENT_A", "三方递交结盟条件", action="递交结盟条件")
    b = _sig("EVENT_B", "三方在同一地点开战", action="开战")
    assert index.classify_relation(a, b) != "duplicate"


def test_rebuild_is_deterministic_and_removal_works() -> None:
    rows = [_sig("EVENT_A", "三方同时递来三份结盟书"),
            _sig("EVENT_B", "三方同日在聚落提出合作条件")]
    index = LocalSemanticIndex()
    index.rebuild(rows)
    first = [(c.event_id, c.score, c.relation) for c in index.candidates(rows[1])]
    index.rebuild(list(reversed(rows)))
    second = [(c.event_id, c.score, c.relation) for c in index.candidates(rows[1])]
    assert first == second
    index.remove_event("EVENT_A")
    assert index.get_event("EVENT_A") is None
    assert all(c.event_id != "EVENT_A" for c in index.candidates(rows[1]))


def test_backend_is_local_without_optional_dependencies() -> None:
    index = LocalSemanticIndex()
    assert index.backend == "local"
    index.rebuild([_sig("EVENT_A", "任意事件")])
    assert index.get_event("EVENT_A") is not None
