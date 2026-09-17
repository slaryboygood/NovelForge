"""V4-05 §15：Q3 Continuity —— 时间 / 地点 / 信息 / 关系的结构化连续性。"""

from __future__ import annotations

from pathlib import Path

from quality_support import codes, isolated_gate, scene


def test_time_regression_is_reported(tmp_path: Path) -> None:
    issues, _quality = isolated_gate(
        tmp_path,
        [scene("sc_001_01", sequence=1, time="第3天清晨"),
         scene("sc_001_02", sequence=2, time="第2天傍晚")],
        "Q3", with_novel=False)
    assert codes(issues) == ["CONTINUITY_TIME_CONFLICT"]


def test_time_is_monotonic_within_same_day(tmp_path: Path) -> None:
    issues, _quality = isolated_gate(
        tmp_path,
        [scene("sc_001_01", sequence=1, time="第3天清晨"),
         scene("sc_001_02", sequence=2, time="第3天傍晚"),
         scene("sc_001_03", sequence=3, time="第4天清晨")],
        "Q3", with_novel=False)
    assert codes(issues) == []


def test_location_jump_without_transition(tmp_path: Path) -> None:
    issues, _quality = isolated_gate(
        tmp_path,
        [scene("sc_001_01", sequence=1, location="station"),
         scene("sc_001_02", sequence=2, location="colony")],
        "Q3", with_novel=False)
    assert codes(issues) == ["CONTINUITY_LOCATION_CONFLICT"]


def test_location_jump_with_transition_is_allowed(tmp_path: Path) -> None:
    issues, _quality = isolated_gate(
        tmp_path,
        [scene("sc_001_01", sequence=1, location="station"),
         scene("sc_001_02", sequence=2, location="colony",
               scene_purpose="主角前往殖民区核对记录")],
        "Q3", with_novel=False)
    assert codes(issues) == []


def test_knowledge_used_before_it_is_revealed(tmp_path: Path) -> None:
    issues, _quality = isolated_gate(
        tmp_path,
        [scene("sc_001_01", sequence=1,
               state_transition_intent=[{"kind": "knowledge",
                                         "target": "hidden_truth",
                                         "value": "known"}]),
         scene("sc_001_02", sequence=2)],
        "Q3", with_novel=False)
    assert codes(issues) == ["CONTINUITY_KNOWLEDGE_LEAK"]
    assert issues[0].severity == "major"


def test_knowledge_revealed_in_earlier_scene_is_allowed(tmp_path: Path) -> None:
    issues, _quality = isolated_gate(
        tmp_path,
        [scene("sc_001_01", sequence=1,
               information_reveal=["hidden_truth 藏在维修队列备份里"]),
         scene("sc_001_02", sequence=2,
               state_transition_intent=[{"kind": "knowledge",
                                         "target": "hidden_truth",
                                         "value": "known"}]),
         scene("sc_001_03", sequence=3)],
        "Q3", with_novel=False)
    assert codes(issues) == []


def test_relationship_change_without_structural_support(tmp_path: Path) -> None:
    issues, _quality = isolated_gate(
        tmp_path,
        [scene("sc_001_01", sequence=1,
               relationship_change="主角与主管彻底决裂"),
         scene("sc_001_02", sequence=2)],
        "Q3", with_novel=False)
    assert codes(issues) == ["CONTINUITY_RELATIONSHIP_CONFLICT"]
