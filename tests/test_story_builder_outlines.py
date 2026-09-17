from __future__ import annotations

from pathlib import Path

import pytest

from novelforge.story_builder import (
    STORY_STEP_ORDER,
    BlueprintStatus,
    DeterministicRecommendationEngine,
    OutlineLevel,
    OutlineStatus,
    StoryBlueprintCompiler,
    StoryBlueprintRepository,
    StoryOutlineCompiler,
    StoryOutlineError,
    StoryOutlineRepository,
    StorySessionManager,
    StorySessionRepository,
    load_story_catalog,
    outline_id,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def confirmed_blueprint(tmp_path: Path):
    catalog = load_story_catalog(PROJECT_ROOT)
    sessions = StorySessionRepository(tmp_path)
    manager = StorySessionManager(sessions, catalog)
    rules = DeterministicRecommendationEngine(catalog)
    session = sessions.create("silicon_rise", session_id="session_outline_001")
    for step in STORY_STEP_ORDER:
        selected = [item.option_id for item in session.selections if item.option_id]
        option = rules.recommend(step, selected, based_on_version=session.selection_version).recommendations[0]
        session = manager.set_step_selections(
            session.session_id, step, option_ids=[option.option_id],
            expected_selection_version=session.selection_version,
        )
    blueprint_repository = StoryBlueprintRepository(tmp_path)
    blueprint_compiler = StoryBlueprintCompiler(catalog, sessions, blueprint_repository)
    blueprint = blueprint_compiler.compile(session.session_id)
    blueprint = blueprint_compiler.confirm(blueprint.blueprint_id, blueprint.version)
    assert blueprint.status == BlueprintStatus.CONFIRMED
    outlines = StoryOutlineRepository(tmp_path)
    return blueprint, outlines, StoryOutlineCompiler(catalog, blueprint_repository, outlines)


def test_four_outline_levels_require_parent_confirmation(tmp_path: Path) -> None:
    blueprint, _repository, compiler = confirmed_blueprint(tmp_path)

    with pytest.raises(StoryOutlineError) as missing_parent:
        compiler.compile(blueprint.blueprint_id, blueprint.version, OutlineLevel.VOLUME)
    assert missing_parent.value.code == "OUTLINE_PARENT_NOT_CONFIRMED"

    expected = [(OutlineLevel.BOOK, 1), (OutlineLevel.VOLUME, 3), (OutlineLevel.ARC, 6), (OutlineLevel.CHAPTER, 24)]
    packages = []
    for level, item_count in expected:
        package = compiler.compile(blueprint.blueprint_id, blueprint.version, level)
        assert package.status == OutlineStatus.DRAFT
        assert len(package.items) == item_count
        assert all(item.start_state and item.end_state and item.goals and item.ending_hook for item in package.items)
        package = compiler.confirm(package.package_id, package.version)
        assert package.status == OutlineStatus.CONFIRMED
        packages.append(package)

    assert packages[-1].items[1].start_state.startswith("承接上一章")
    assert len(compiler.latest_chain(blueprint.blueprint_id)) == 4


def test_regeneration_preserves_old_version_and_stales_children(tmp_path: Path) -> None:
    blueprint, repository, compiler = confirmed_blueprint(tmp_path)
    book_v1 = compiler.confirm(
        (book := compiler.compile(blueprint.blueprint_id, blueprint.version, OutlineLevel.BOOK)).package_id,
        book.version,
    )
    volume_v1 = compiler.confirm(
        (volume := compiler.compile(blueprint.blueprint_id, blueprint.version, OutlineLevel.VOLUME)).package_id,
        volume.version,
    )
    arc_v1 = compiler.confirm(
        (arc := compiler.compile(blueprint.blueprint_id, blueprint.version, OutlineLevel.ARC)).package_id,
        arc.version,
    )
    chapter_v1 = compiler.confirm(
        (chapter := compiler.compile(blueprint.blueprint_id, blueprint.version, OutlineLevel.CHAPTER)).package_id,
        chapter.version,
    )

    book_v2 = compiler.compile(
        blueprint.blueprint_id, blueprint.version, OutlineLevel.BOOK, regenerate=True
    )
    assert book_v2.version == 2
    compiler.confirm(book_v2.package_id, book_v2.version)

    stale_volume = repository.effective(repository.load(volume_v1.package_id, volume_v1.version))
    assert stale_volume.status == OutlineStatus.NEEDS_REVIEW
    assert repository.effective(arc_v1).status == OutlineStatus.NEEDS_REVIEW
    assert repository.effective(chapter_v1).status == OutlineStatus.NEEDS_REVIEW
    assert repository.load(book_v1.package_id, 1).status == OutlineStatus.CONFIRMED
    with pytest.raises(StoryOutlineError) as stale:
        compiler.confirm(volume_v1.package_id, volume_v1.version)
    assert stale.value.code == "OUTLINE_PARENT_STALE"

    volume_v2 = compiler.compile(blueprint.blueprint_id, blueprint.version, OutlineLevel.VOLUME)
    assert volume_v2.version == 2
    assert volume_v2.source_package_versions == {book_v2.package_id: 2}


def test_same_source_is_idempotent_unless_regeneration_requested(tmp_path: Path) -> None:
    blueprint, repository, compiler = confirmed_blueprint(tmp_path)
    first = compiler.compile(blueprint.blueprint_id, blueprint.version, OutlineLevel.BOOK)
    again = compiler.compile(blueprint.blueprint_id, blueprint.version, OutlineLevel.BOOK)
    regenerated = compiler.compile(
        blueprint.blueprint_id, blueprint.version, OutlineLevel.BOOK, regenerate=True
    )

    assert again == first
    assert regenerated.version == 2
    assert repository.load(outline_id(blueprint.blueprint_id, OutlineLevel.BOOK), 1) == first
