"""S02：Typed State Registry —— future / premature / repeated irreversible。"""

from __future__ import annotations

from novelforge.story_engine.chapter_ir.models import ChapterStateTransition
from novelforge.story_engine.chapter_ir.state import TypedStateRegistry, build_default_registry


def _transition(state_key: str, from_state: str, to_state: str, *, position: int,
                kind: str = "progression") -> ChapterStateTransition:
    return ChapterStateTransition(transition_id="ST_001", state_key=state_key,
                                  from_state=from_state, to_state=to_state,
                                  transition_kind=kind, effective_at=position)


def test_illegal_edge_and_unknown_state() -> None:
    registry = build_default_registry({"salt_route_control": 133})
    findings = registry.validate([_transition("salt_route_control",
                                              "controlled_by_rust_settlement", "uncontrolled",
                                              position=140)])
    assert {item.code for item in findings} == {"ILLEGAL_STATE_EDGE"}
    unknown = registry.validate([_transition("no_such_state", "a", "b", position=1)])
    assert {item.code for item in unknown} == {"UNKNOWN_STATE_KEY"}


def test_premature_and_future_transition() -> None:
    from novelforge.story_engine.chapter_ir.state import TransitionBinding
    registry = build_default_registry({})
    registry.bind(TransitionBinding("common_rules_status", "signed", "uuid_sign", 526))
    premature = registry.validate([_transition("common_rules_status", "approved", "signed",
                                               position=515, kind="irreversible")])
    assert "PREMATURE_STATE_TRANSITION" in {item.code for item in premature}
    on_time = registry.validate([_transition("common_rules_status", "approved", "signed",
                                             position=526, kind="irreversible")])
    assert on_time == []


def test_repeated_irreversible_transition() -> None:
    registry = build_default_registry({"zero_layer_access": 379})
    repeat = registry.validate([_transition("zero_layer_access", "emergency_locked",
                                            "permanently_sealed", position=400,
                                            kind="irreversible")])
    assert "REPEATED_IRREVERSIBLE_TRANSITION" in {item.code for item in repeat}


def test_state_at_replays_transitions() -> None:
    registry = build_default_registry({})
    text = [
        _transition("salt_route_control", "uncontrolled", "contested", position=107),
        _transition("salt_route_control", "contested", "controlled_by_rust_settlement",
                    position=133),
    ]
    assert registry.state_at("salt_route_control", text) == "controlled_by_rust_settlement"
    assert registry.state_at("salt_route_control", text[:1]) == "contested"
