"""V4-05 §17：Q5 Causality —— 因果图上的结构化检测。"""

from __future__ import annotations

from pathlib import Path

from quality_support import (
    causal_node,
    codes,
    isolated_gate,
    payoff_node,
    scene,
    setup_node,
)


def test_causal_gap_when_scene_has_no_reason(tmp_path: Path) -> None:
    issues, _quality = isolated_gate(
        tmp_path,
        [scene("sc_001_01", sequence=1),
         scene("sc_001_02", sequence=2, escalation="", conflict="")],
        "Q5", with_novel=False)
    assert "CAUSAL_GAP" in codes(issues)
    assert [row.scope.node_ids for row in issues if row.code == "CAUSAL_GAP"] == \
        [("sc_001_02",)]


def test_causal_edge_removes_gap(tmp_path: Path) -> None:
    issues, _quality = isolated_gate(
        tmp_path,
        [scene("sc_001_01", sequence=1),
         scene("sc_001_02", sequence=2, escalation="", conflict=""),
         causal_node("sc_001_01", "sc_001_02")],
        "Q5", with_novel=False)
    assert "CAUSAL_GAP" not in codes(issues)


def test_orphan_event_without_incoming_or_outgoing(tmp_path: Path) -> None:
    issues, _quality = isolated_gate(
        tmp_path,
        [scene("sc_001_01", sequence=1),
         scene("sc_001_02", sequence=2),
         causal_node("sc_001_01", "sc_001_02"),
         scene("sc_001_03", sequence=3)],
        "Q5", with_novel=False)
    assert "ORPHAN_EVENT" in codes(issues)
    assert [row.scope.node_ids for row in issues
            if row.code == "ORPHAN_EVENT"] == [("sc_001_03",)]


def test_orphan_event_skipped_when_scene_carries_setup(tmp_path: Path) -> None:
    issues, _quality = isolated_gate(
        tmp_path,
        [scene("sc_001_01", sequence=1, setup=["备用电源曾被破坏"])],
        "Q5", with_novel=False)
    assert "ORPHAN_EVENT" not in codes(issues)


def test_circular_dependency_is_detected(tmp_path: Path) -> None:
    issues, _quality = isolated_gate(
        tmp_path,
        [scene("sc_001_01", sequence=1),
         scene("sc_001_02", sequence=2),
         causal_node("sc_001_01", "sc_001_02", node_id="cl_001", index=1),
         causal_node("sc_001_02", "sc_001_01", node_id="cl_002", index=2)],
        "Q5", with_novel=False)
    assert "CIRCULAR_DEPENDENCY" in codes(issues)
    cycle_issue = [row for row in issues if row.code == "CIRCULAR_DEPENDENCY"][0]
    assert set(cycle_issue.scope.node_ids) == {"sc_001_01", "sc_001_02"}
    assert cycle_issue.repairable is False


def test_unsupported_payoff(tmp_path: Path) -> None:
    issues, _quality = isolated_gate(
        tmp_path,
        [scene("sc_001_01", sequence=1),
         payoff_node("payoff_001", resolves=())],
        "Q5", with_novel=False)
    assert "UNSUPPORTED_PAYOFF" in codes(issues)


def test_bound_payoff_is_supported(tmp_path: Path) -> None:
    issues, _quality = isolated_gate(
        tmp_path,
        [scene("sc_001_01", sequence=1),
         setup_node("setup_001", parent="sc_001_01"),
         payoff_node("payoff_001", resolves=("setup_001",))],
        "Q5", with_novel=False)
    assert "UNSUPPORTED_PAYOFF" not in codes(issues)
    assert "DEAD_BRANCH" not in codes(issues)


def test_unmotivated_decision(tmp_path: Path) -> None:
    issues, _quality = isolated_gate(
        tmp_path,
        [scene("sc_001_01", sequence=1, character_goals=[],
               story_function=["decision"])],
        "Q5", with_novel=False)
    assert "UNMOTIVATED_DECISION" in codes(issues)


def test_decision_with_earlier_goal_is_motivated(tmp_path: Path) -> None:
    issues, _quality = isolated_gate(
        tmp_path,
        [scene("sc_001_01", sequence=1),
         scene("sc_001_02", sequence=2, character_goals=[],
               story_function=["decision"])],
        "Q5", with_novel=False)
    assert "UNMOTIVATED_DECISION" not in codes(issues)


def test_dead_branch_setup_is_reported(tmp_path: Path) -> None:
    issues, _quality = isolated_gate(
        tmp_path,
        [scene("sc_001_01", sequence=1),
         setup_node("setup_001", parent="sc_001_01")],
        "Q5", with_novel=False)
    assert "DEAD_BRANCH" in codes(issues)
    dead = [row for row in issues if row.code == "DEAD_BRANCH"][0]
    assert dead.scope.node_ids == ("setup_001",)
    assert dead.repairable is True
