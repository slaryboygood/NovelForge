"""V4-05 §20：Q8 Blueprint Style —— 表达是否具体 / 是否模板化（不是小说文笔）。"""

from __future__ import annotations

from pathlib import Path

from quality_support import codes, isolated_gate, scene


def test_vague_content_is_reported(tmp_path: Path) -> None:
    issues, _quality = isolated_gate(
        tmp_path, [scene("sc_001_01", sequence=1, outcome="关系进一步发展")],
        "Q8", with_novel=False)
    assert codes(issues) == ["BLUEPRINT_VAGUE_CONTENT"]
    assert issues[0].severity == "major"
    assert issues[0].repairable is True
    assert "allow_change" in issues[0].repair_contract


def test_specific_content_is_clean(tmp_path: Path) -> None:
    issues, _quality = isolated_gate(
        tmp_path,
        [scene("sc_001_01", sequence=1,
               outcome="主角拿到主管签字的封存清单副本")],
        "Q8", with_novel=False)
    assert codes(issues) == []


def test_field_label_leak_into_visible_text(tmp_path: Path) -> None:
    issues, _quality = isolated_gate(
        tmp_path,
        [scene("sc_001_01", sequence=1, outcome="阶段目标：拿到封存清单")],
        "Q8", with_novel=False)
    assert "BLUEPRINT_FIELD_LABEL_TEXT" in codes(issues)


def test_placeholder_text_is_reported(tmp_path: Path) -> None:
    issues, _quality = isolated_gate(
        tmp_path,
        [scene("sc_001_01", sequence=1, outcome="主角拿到（待定）的维修记录")],
        "Q8", with_novel=False)
    assert "BLUEPRINT_PLACEHOLDER_TEXT" in codes(issues)


def test_title_too_similar(tmp_path: Path) -> None:
    from quality_support import chapter

    issues, _quality = isolated_gate(
        tmp_path,
        [chapter("ch_001", sequence=1, title="被删除的维修日志"),
         chapter("ch_002", sequence=2, title="被删除的维修日志副本")],
        "Q8", with_novel=False)
    assert "BLUEPRINT_TITLE_TOO_SIMILAR" in codes(issues)


def test_style_gate_is_deterministic_and_blueprint_scoped() -> None:
    """§1 / §22：Q8 = Blueprint clarity，deterministic；不评小说文笔。"""

    from novelforge.quality import QualityPolicy, build_default_registry

    registry = build_default_registry()
    rows = registry.for_gate("Q8", policy=QualityPolicy())
    assert rows and all(row.spec.kind == "deterministic" for row in rows)
    assert "Blueprint" in rows[0].spec.description
