from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from novelforge.story_builder import (
    DeterministicRecommendationEngine,
    RecommendationSource,
    StoryCatalogError,
    StoryCatalogIndex,
    StoryStep,
    load_story_catalog,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def engine() -> DeterministicRecommendationEngine:
    return DeterministicRecommendationEngine(load_story_catalog(PROJECT_ROOT))


def ids(result) -> list[str]:
    return [item.option_id for item in result.recommendations]


def test_first_step_is_available_without_selections(engine: DeterministicRecommendationEngine) -> None:
    result = engine.recommend(StoryStep.READER_EXPERIENCE, based_on_version=0)

    assert ids(result) == [
        "experience_growth_adventure",
        "experience_mystery_exploration",
        "experience_relationship_drama",
    ]
    assert result.unlocked_steps == [StoryStep.READER_EXPERIENCE]
    assert result.can_continue is True
    assert all(item.source == RecommendationSource.RULE for item in result.recommendations)


def test_locked_step_cannot_be_recommended_early(engine: DeterministicRecommendationEngine) -> None:
    result = engine.recommend(StoryStep.WORLDVIEW)

    assert result.recommendations == []
    assert result.can_continue is False
    assert [conflict.code for conflict in result.conflicts] == ["STEP_LOCKED"]


def test_requires_any_filters_worldviews_and_unlocks_rank_first(
    engine: DeterministicRecommendationEngine,
) -> None:
    result = engine.recommend(
        StoryStep.WORLDVIEW,
        ["experience_growth_adventure"],
        based_on_version=1,
    )

    assert ids(result) == ["world_silicon_mmo", "world_cultivation_realms", "world_modern_supernatural"]
    assert "成长冒险" in result.recommendations[0].reason
    assert result.based_on_version == 1


def test_same_input_always_returns_same_result(engine: DeterministicRecommendationEngine) -> None:
    selected = ["experience_mystery_exploration"]

    first = engine.recommend(StoryStep.WORLDVIEW, selected, based_on_version=4)
    second = engine.recommend(StoryStep.WORLDVIEW, reversed(selected), based_on_version=4)

    assert first.model_dump(mode="json") == second.model_dump(mode="json")


def test_complete_silicon_path_unlocks_each_next_step(
    engine: DeterministicRecommendationEngine,
) -> None:
    selected = [
        "experience_growth_adventure",
        "world_silicon_mmo",
        "background_ruined_board",
        "protagonist_nonhuman_awakening",
        "cast_found_family",
        "setting_multi_faction_frontier",
        "events_survival_to_world",
        "progression_rule_discovery",
        "style_light_fast_webnovel",
    ]
    result = engine.recommend(StoryStep.AUTHOR_BOUNDARIES, selected)

    assert result.unlocked_steps == list(StoryStep)
    assert set(ids(result)) == {
        "boundary_no_lecturing",
        "boundary_no_free_power",
        "boundary_character_consistency",
    }
    assert result.can_continue is True


def test_invalid_existing_selection_becomes_blocking_conflict(
    engine: DeterministicRecommendationEngine,
) -> None:
    result = engine.recommend(
        StoryStep.READER_EXPERIENCE,
        ["background_ruined_board"],
    )

    assert result.can_continue is False
    assert "REQUIREMENT_ALL_UNMET" in [conflict.code for conflict in result.conflicts]


def test_step_selection_limit_is_enforced(engine: DeterministicRecommendationEngine) -> None:
    result = engine.recommend(
        StoryStep.WORLDVIEW,
        ["experience_growth_adventure", "experience_mystery_exploration"],
    )

    assert result.can_continue is False
    assert "SELECTION_LIMIT_EXCEEDED" in [conflict.code for conflict in result.conflicts]


def test_custom_selection_unlocks_next_step_without_faking_catalog_match(
    engine: DeterministicRecommendationEngine,
) -> None:
    result = engine.recommend(
        StoryStep.WORLDVIEW,
        custom_selection_counts={StoryStep.READER_EXPERIENCE: 1},
    )

    assert StoryStep.WORLDVIEW in result.unlocked_steps
    assert len(result.recommendations) == 3
    assert result.can_continue is True
    assert result.conflicts == []


def test_unknown_or_duplicate_selection_is_rejected(
    engine: DeterministicRecommendationEngine,
) -> None:
    with pytest.raises(StoryCatalogError) as unknown:
        engine.recommend(StoryStep.WORLDVIEW, ["missing_option"])
    assert unknown.value.code == "OPTION_NOT_FOUND"

    with pytest.raises(StoryCatalogError) as duplicate:
        engine.recommend(
            StoryStep.WORLDVIEW,
            ["experience_growth_adventure", "experience_growth_adventure"],
        )
    assert duplicate.value.code == "SELECTION_DUPLICATE"


def test_recommendation_limit_is_validated(engine: DeterministicRecommendationEngine) -> None:
    with pytest.raises(StoryCatalogError) as caught:
        engine.recommend(StoryStep.READER_EXPERIENCE, limit=6)

    assert caught.value.code == "RECOMMENDATION_LIMIT_INVALID"


def test_returning_to_step_excludes_selected_option_and_keeps_contiguous_ranks(
    engine: DeterministicRecommendationEngine,
) -> None:
    result = engine.recommend(
        StoryStep.WORLDVIEW,
        ["experience_growth_adventure", "world_silicon_mmo"],
    )

    assert ids(result) == ["world_cultivation_realms", "world_modern_supernatural"]
    assert [item.rank for item in result.recommendations] == [1, 2]


def test_excludes_rule_filters_candidate() -> None:
    index = load_story_catalog(PROJECT_ROOT)
    roaming = index.require_option("setting_roaming_world").model_copy(
        update={"excludes": ["experience_growth_adventure"]}
    )
    options_by_id = dict(index.options_by_id)
    options_by_id[roaming.id] = roaming
    options_by_step = dict(index.options_by_step)
    options_by_step[StoryStep.FACTIONS_LOCATIONS] = tuple(
        roaming if option.id == roaming.id else option
        for option in options_by_step[StoryStep.FACTIONS_LOCATIONS]
    )
    modified = replace(
        index,
        options_by_id=options_by_id,
        options_by_step=options_by_step,
    )
    modified_engine = DeterministicRecommendationEngine(modified)
    selected = [
        "experience_growth_adventure",
        "world_silicon_mmo",
        "background_ruined_board",
        "protagonist_nonhuman_awakening",
        "cast_found_family",
    ]

    result = modified_engine.recommend(StoryStep.FACTIONS_LOCATIONS, selected)

    assert "setting_roaming_world" not in ids(result)
