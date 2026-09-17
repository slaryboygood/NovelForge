from __future__ import annotations

from pathlib import Path

import pytest

from novelforge.story_builder import (
    STORY_STEP_ORDER,
    BlueprintStatus,
    BuilderStatus,
    DeterministicRecommendationEngine,
    StoryBlueprintCompiler,
    StoryBlueprintError,
    StoryBlueprintRepository,
    StorySessionManager,
    StorySessionRepository,
    load_story_catalog,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def completed_session(tmp_path: Path):
    catalog = load_story_catalog(PROJECT_ROOT)
    sessions = StorySessionRepository(tmp_path)
    manager = StorySessionManager(sessions, catalog)
    rules = DeterministicRecommendationEngine(catalog)
    session = sessions.create("silicon_rise", session_id="session_blueprint_001")
    for step in STORY_STEP_ORDER:
        selected = [item.option_id for item in session.selections if item.option_id]
        custom = {item.step: 1 for item in session.selections if item.custom_text}
        option = rules.recommend(
            step,
            selected,
            custom_selection_counts=custom,
            based_on_version=session.selection_version,
        ).recommendations[0]
        session = manager.set_step_selections(
            session.session_id,
            step,
            option_ids=[option.option_id],
            expected_selection_version=session.selection_version,
        )
    blueprints = StoryBlueprintRepository(tmp_path)
    return catalog, sessions, manager, blueprints, StoryBlueprintCompiler(catalog, sessions, blueprints)


def test_compile_blueprint_preserves_all_selection_sources(tmp_path: Path) -> None:
    _catalog, sessions, _manager, blueprints, compiler = completed_session(tmp_path)

    blueprint = compiler.compile("session_blueprint_001")

    assert blueprint.version == 1
    assert blueprint.status == BlueprintStatus.DRAFT
    assert len(blueprint.sections) == len(STORY_STEP_ORDER)
    assert all(section.source_selection_ids for section in blueprint.sections)
    assert sum(len(section.source_selection_ids) for section in blueprint.sections) == 10
    assert "阅读承诺" in blueprint.premise
    assert blueprints.load(blueprint.blueprint_id, 1) == blueprint
    assert sessions.load("session_blueprint_001").status == BuilderStatus.BLUEPRINT_DRAFT


def test_compile_is_idempotent_and_confirm_updates_session(tmp_path: Path) -> None:
    _catalog, sessions, _manager, _blueprints, compiler = completed_session(tmp_path)
    first = compiler.compile("session_blueprint_001")
    again = compiler.compile("session_blueprint_001")

    assert again == first
    confirmed = compiler.confirm(first.blueprint_id, first.version)

    assert confirmed.status == BlueprintStatus.CONFIRMED
    assert confirmed.confirmed_by_author is True
    assert sessions.load("session_blueprint_001").status == BuilderStatus.BLUEPRINT_CONFIRMED


def test_incomplete_or_changed_session_cannot_confirm_blueprint(tmp_path: Path) -> None:
    catalog = load_story_catalog(PROJECT_ROOT)
    sessions = StorySessionRepository(tmp_path)
    compiler = StoryBlueprintCompiler(catalog, sessions, StoryBlueprintRepository(tmp_path))
    sessions.create("silicon_rise", session_id="session_incomplete")
    with pytest.raises(StoryBlueprintError) as incomplete:
        compiler.compile("session_incomplete")
    assert incomplete.value.code == "BLUEPRINT_STEPS_INCOMPLETE"

    catalog, sessions, manager, _blueprints, compiler = completed_session(tmp_path / "changed")
    blueprint = compiler.compile("session_blueprint_001")
    changed = manager.set_step_selections(
        "session_blueprint_001",
        STORY_STEP_ORDER[0],
        option_ids=["experience_mystery_exploration"],
        expected_selection_version=10,
    )
    assert len(changed.needs_review_steps) == 9

    with pytest.raises(StoryBlueprintError) as stale:
        compiler.confirm(blueprint.blueprint_id, blueprint.version)
    assert stale.value.code == "BLUEPRINT_SOURCE_STALE"

    candidate = compiler.compile("session_blueprint_001")
    assert candidate.version == 2
    assert candidate.unresolved_conflicts
    with pytest.raises(StoryBlueprintError) as conflicts:
        compiler.confirm(candidate.blueprint_id, candidate.version)
    assert conflicts.value.code == "BLUEPRINT_CONFLICTS_UNRESOLVED"
