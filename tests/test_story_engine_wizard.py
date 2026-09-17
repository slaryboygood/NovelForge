"""T13：新建小说向导、内容包导出导入与题材案例库。"""

from __future__ import annotations

from pathlib import Path

import pytest

from novelforge.story_engine import (
    CASE_CATEGORIES,
    NovelPackError,
    NovelPackRepository,
    NovelProfileRepository,
    create_novel,
    export_pack,
    import_pack,
    load_case_library,
    pack_from_profile,
)


ROOT = Path(__file__).resolve().parents[1]


def test_create_novel_with_template_and_entry_step(tmp_path: Path) -> None:
    repository = NovelProfileRepository(tmp_path)
    profile, entry = create_novel(repository, "novel_wizard", title="丙书", genre="xianxia",
                                  template_id="xianxia", entry_step="protagonist")
    assert entry == "protagonist"
    assert profile.template_id == "xianxia"
    assert "spirit_stone" in profile.resource_catalog
    assert repository.load("novel_wizard").template_id == "xianxia"
    with pytest.raises(NovelPackError):
        create_novel(repository, "novel_bad_entry", entry_step="nowhere")
    custom, _ = create_novel(repository, "novel_custom_wizard", title="自定义题材")
    assert custom.template_id == "" and custom.resource_catalog == {}


def test_content_pack_round_trip_and_export_import(tmp_path: Path) -> None:
    profiles = NovelProfileRepository(tmp_path)
    profile, _ = create_novel(profiles, "novel_pack", title="丁书", template_id="sci_fi")
    pack = pack_from_profile(profile)
    assert "energy" in pack.resources and pack.style["narrative_style"] == ""
    repository = NovelPackRepository(tmp_path)
    assert not repository.exists("novel_pack")
    repository.save(pack)
    assert repository.load("novel_pack") == pack
    payload = export_pack(pack)
    assert isinstance(payload, dict) and payload["novel_id"] == "novel_pack"
    imported = import_pack(payload, novel_id="novel_other")
    assert imported.novel_id == "novel_other"
    assert set(imported.resources) == set(pack.resources)
    with pytest.raises(NovelPackError):
        import_pack({"novel_id": "novel_bad", "characters": {"x": {"bad": 1}}})
    with pytest.raises(NovelPackError):
        NovelPackRepository(tmp_path, tmp_path.parent / "outside_packs")


def test_case_library_is_original_reference_only() -> None:
    library = load_case_library(ROOT / "novel" / "config" / "story_engine" / "cases.json")
    assert "不作为固定剧情模板" in library.notice
    assert {item.category for item in library.cases} >= set(CASE_CATEGORIES)
    examples = [item.example for item in library.cases]
    assert len(examples) == len(set(examples))
    for item in library.cases:
        assert item.structure and item.authoring_note and item.genres
    with pytest.raises(NovelPackError):
        load_case_library(ROOT / "novel" / "config" / "story_engine" / "missing_cases.json")

