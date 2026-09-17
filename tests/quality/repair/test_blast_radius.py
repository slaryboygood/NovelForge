"""V4-05 §32：Blast Radius —— direct / dependent / required verification gates。"""

from __future__ import annotations

from novelforge.quality import RepairBlastRadius

from quality_support import broken_nodes


def _nodes() -> list[object]:
    return broken_nodes()


def test_changed_scene_pulls_in_dependents() -> None:
    nodes = _nodes()
    blast = RepairBlastRadius.compute(nodes=nodes, changed=["sc_001_03"],
                                      issue_gates=["Q3"])
    assert blast.changed == ("sc_001_03",)
    assert set(blast.dependent) == {"sc_001_01", "sc_001_02", "sc_001_04",
                                    "setup_001", "cl_002"}
    assert blast.reasons["setup_001"] == ("child_of_changed",)
    assert "causal_endpoint_changed" in blast.reasons["cl_002"]
    assert "same_chapter_scene" in blast.reasons["sc_001_04"]
    assert "same_chapter_scene" in blast.reasons["sc_001_01"]


def test_gates_include_baseline_and_node_type_gates() -> None:
    from novelforge.quality.repair.blast_radius import GATE_ORDER

    blast = RepairBlastRadius.compute(nodes=_nodes(), changed=["sc_001_03"],
                                      issue_gates=["Q3"])
    assert blast.gates[:2] == ("Q0", "Q1")
    assert blast.gates[-1] == "Q9"
    assert {"Q3", "Q4", "Q5", "Q6", "Q7", "Q8"} <= set(blast.gates)
    assert list(blast.gates) == sorted(blast.gates, key=GATE_ORDER.index)


def test_chapter_change_scopes_its_scenes() -> None:
    blast = RepairBlastRadius.compute(nodes=_nodes(), changed=["ch_001"])
    assert set(blast.dependent) >= {"sc_001_01", "sc_001_02", "sc_001_03",
                                    "sc_001_04"}
    assert "Q6" in blast.gates and "Q8" in blast.gates


def test_dependent_scope_can_be_disabled() -> None:
    blast = RepairBlastRadius.compute(nodes=_nodes(), changed=["sc_001_03"],
                                      include_dependent=False)
    assert blast.dependent == ()
    assert blast.scope == ("sc_001_03",)


def test_unknown_node_is_ignored_for_gate_derivation() -> None:
    blast = RepairBlastRadius.compute(nodes=_nodes(), changed=["does_not_exist"])
    assert blast.changed == ("does_not_exist",)
    assert blast.gates[:2] == ("Q0", "Q1")
    assert blast.as_dict()["scope"] == ["does_not_exist"]
