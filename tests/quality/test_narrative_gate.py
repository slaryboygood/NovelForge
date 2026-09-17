"""V4-05 §19、§49、§51：Q7 Narrative —— 场景功能 / 节奏 / 高潮准备 / 收束完整性。"""

from __future__ import annotations

from pathlib import Path

from novelforge.blueprint import StoryArcPayload

from quality_support import NOVEL_ID, codes, isolated_gate, node, scene


def test_scene_with_only_transition_has_no_function(tmp_path: Path) -> None:
    issues, _quality = isolated_gate(
        tmp_path,
        [scene("sc_001_01", sequence=1, story_function=["transition"])],
        "Q7", with_novel=False)
    assert [row.code for row in issues] == ["SCENE_NO_NARRATIVE_FUNCTION"]
    assert issues[0].severity == "major"
    assert issues[0].repairable is True


def test_advance_plot_without_outcome_has_no_function(tmp_path: Path) -> None:
    issues, _quality = isolated_gate(
        tmp_path,
        [scene("sc_001_01", sequence=1, outcome="",
               story_function=["advance_plot"])],
        "Q7", with_novel=False)
    assert "SCENE_NO_NARRATIVE_FUNCTION" in codes(issues)


def test_scene_with_function_is_kept(tmp_path: Path) -> None:
    issues, _quality = isolated_gate(tmp_path, [scene("sc_001_01", sequence=1)],
                                     "Q7", with_novel=False)
    assert codes(issues) == []


def test_pacing_stagnation_after_three_flat_scenes(tmp_path: Path) -> None:
    flat = {"story_function": ["reveal_information"], "escalation": ""}
    issues, _quality = isolated_gate(
        tmp_path,
        [scene("sc_001_01", sequence=1, **flat),
         scene("sc_001_02", sequence=2, **flat),
         scene("sc_001_03", sequence=3, **flat)],
        "Q7", with_novel=False)
    assert "PACING_STAGNATION" in codes(issues)


def test_escalation_breaks_stagnation(tmp_path: Path) -> None:
    flat = {"story_function": ["reveal_information"], "escalation": ""}
    issues, _quality = isolated_gate(
        tmp_path,
        [scene("sc_001_01", sequence=1, **flat),
         scene("sc_001_02", sequence=2, escalation="许可被撤回",
               story_function=["escalate_conflict"]),
         scene("sc_001_03", sequence=3, **flat)],
        "Q7", with_novel=False)
    assert "PACING_STAGNATION" not in codes(issues)


def test_climax_unprepared_without_accumulation(tmp_path: Path) -> None:
    issues, _quality = isolated_gate(
        tmp_path,
        [node(NOVEL_ID, "story_arc", "story_arc",
              StoryArcPayload(climax="主角把修复权交给对手共同完成",
                              resolution="据点通电"),
              sequence=0),
         scene("sc_001_01", sequence=1, story_function=["advance_plot"])],
        "Q7", with_novel=False)
    assert "CLIMAX_UNPREPARED" in codes(issues)


def test_resolution_incomplete_when_missing(tmp_path: Path) -> None:
    issues, _quality = isolated_gate(
        tmp_path,
        [node(NOVEL_ID, "story_arc", "story_arc",
              StoryArcPayload(climax="", resolution=""), sequence=0),
         scene("sc_001_01", sequence=1, story_function=["payoff"])],
        "Q7", with_novel=False)
    assert "RESOLUTION_INCOMPLETE" in codes(issues)
