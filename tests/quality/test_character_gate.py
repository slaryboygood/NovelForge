"""V4-05 §16、§50：Q4 Character —— 动机 / 人物弧推进 / 转折支撑（结构化证据）。"""

from __future__ import annotations

from pathlib import Path

from novelforge.blueprint import CharacterArcPayload

from quality_support import NOVEL_ID, codes, isolated_gate, node, scene


def test_decision_without_motivation(tmp_path: Path) -> None:
    issues, _quality = isolated_gate(
        tmp_path,
        [scene("sc_001_01", sequence=1, story_function=["decision"],
               character_goals=[], escalation="")],
        "Q4", with_novel=False)
    assert codes(issues) == ["CHARACTER_MOTIVATION_GAP"]
    assert issues[0].evidence[0].node_ids == ("sc_001_01",)


def test_decision_with_motivation_is_allowed(tmp_path: Path) -> None:
    issues, _quality = isolated_gate(
        tmp_path,
        [scene("sc_001_01", sequence=1, story_function=["decision"])],
        "Q4", with_novel=False)
    assert codes(issues) == []


def test_decision_marker_in_text_is_detected(tmp_path: Path) -> None:
    issues, _quality = isolated_gate(
        tmp_path,
        [scene("sc_001_01", sequence=1, story_function=["advance_plot"],
               character_goals=[], escalation="",
               outcome="主角决定放弃调查")],
        "Q4", with_novel=False)
    assert "CHARACTER_MOTIVATION_GAP" in codes(issues)


def _arc(character_id: str = "char_001", **fields: object) -> object:
    payload = {"character_id": character_id, "start_state": "独自扛下所有维修工作",
               "key_turns": ["第一次开口求助"], "midpoint_change": "承认自己修不好全部",
               "crisis": "保人或保电只能选一个", "climax_choice": "把机会交给对手",
               "end_state": "学会与人共同承担"}
    payload.update(fields)
    return node(NOVEL_ID, f"arc_{character_id}", "character_arc",
                CharacterArcPayload(**payload),
                parent_id=character_id, sequence=1,
                source_ids=("char_001",), contract="blueprint.character_arc.v1")


def test_character_arc_without_scene_support_stalls(tmp_path: Path) -> None:
    issues, _quality = isolated_gate(
        tmp_path,
        [_arc(key_turns=[]), scene("sc_001_01", sequence=1,
                                   pov="other_character")],
        "Q4", with_novel=False)
    assert codes(issues) == ["CHARACTER_ARC_STALL"]


def test_character_arc_with_scene_support_does_not_stall(tmp_path: Path) -> None:
    issues, _quality = isolated_gate(
        tmp_path,
        [_arc(), scene("sc_001_01", sequence=1, pov="char_001",
                       character_change="主角完成第一次开口求助")],
        "Q4", with_novel=False)
    assert "CHARACTER_ARC_STALL" not in codes(issues)


def test_key_turn_without_scene_support(tmp_path: Path) -> None:
    issues, _quality = isolated_gate(
        tmp_path,
        [_arc(), scene("sc_001_01", sequence=1, pov="char_001")],
        "Q4", with_novel=False)
    assert "CHARACTER_ARC_UNSUPPORTED_TURN" in codes(issues)
