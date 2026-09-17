from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from novelforge.story_builder import (
    BlueprintSection,
    BlueprintStatus,
    ChoiceConflict,
    ChoiceOption,
    OutlineItem,
    OutlineLevel,
    OutlinePackage,
    OutlineStatus,
    RecommendationItem,
    RecommendationResult,
    RecommendationSource,
    SelectionSource,
    StoryBlueprint,
    StoryBuilderSession,
    StoryBuilderStep,
    StoryChoiceCatalog,
    StorySelection,
    StoryStep,
)


def selection(step: StoryStep, revision: int = 1) -> StorySelection:
    return StorySelection(
        selection_id=f"sel_{step.value}_{revision}",
        step=step,
        option_id=f"opt_{step.value}",
        source=SelectionSource.AUTHOR,
        revision=revision,
    )


def blueprint_sections() -> list[BlueprintSection]:
    return [
        BlueprintSection(
            step=step,
            summary=f"{step.value} summary",
            selected_option_ids=[f"opt_{step.value}"],
            source_selection_ids=[f"sel_{step.value}_1"],
        )
        for step in StoryStep
    ]


def test_story_builder_step_rejects_invalid_single_selection_limit() -> None:
    with pytest.raises(ValidationError):
        StoryBuilderStep(
            step=StoryStep.WORLDVIEW,
            title="世界观",
            prompt="选择世界的运行方式",
            selection_mode="single",
            max_selections=2,
        )


def test_choice_option_rejects_self_reference_and_conflicting_rules() -> None:
    with pytest.raises(ValidationError):
        ChoiceOption(
            id="world_silicon",
            step=StoryStep.WORLDVIEW,
            name="硅基世界",
            summary="硅基生命主导的世界",
            requires_all=["world_silicon"],
        )

    with pytest.raises(ValidationError):
        ChoiceOption(
            id="world_silicon",
            step=StoryStep.WORLDVIEW,
            name="硅基世界",
            summary="硅基生命主导的世界",
            requires_all=["tone_light"],
            excludes=["tone_light"],
        )


def test_custom_selection_requires_custom_text() -> None:
    with pytest.raises(ValidationError):
        StorySelection(
            selection_id="sel_custom_001",
            step=StoryStep.BACKGROUND,
            source=SelectionSource.CUSTOM,
            revision=1,
        )


def test_blocking_recommendation_conflict_stops_progress() -> None:
    conflict = ChoiceConflict(
        code="STYLE_CONFLICT",
        message="写实与纯喜剧方向冲突",
        option_ids=["style_realistic", "style_pure_comedy"],
    )
    with pytest.raises(ValidationError):
        RecommendationResult(
            step=StoryStep.STYLE,
            based_on_version=2,
            conflicts=[conflict],
            can_continue=True,
        )

    result = RecommendationResult(
        step=StoryStep.STYLE,
        based_on_version=2,
        recommendations=[
            RecommendationItem(
                option_id="style_light_adventure",
                reason="与已选探索成长方向一致",
                source=RecommendationSource.RULE,
                rank=1,
            )
        ],
        conflicts=[conflict],
        can_continue=False,
    )
    assert result.recommendations[0].source == RecommendationSource.RULE


def test_recommendation_item_requires_exactly_one_target() -> None:
    with pytest.raises(ValidationError):
        RecommendationItem(
            reason="缺少推荐目标",
            source=RecommendationSource.AI,
            rank=1,
        )

    with pytest.raises(ValidationError):
        RecommendationItem(
            option_id="style_light_adventure",
            custom_text="另一个方向",
            reason="目标冲突",
            source=RecommendationSource.AI,
            rank=1,
        )

    with pytest.raises(ValidationError):
        RecommendationItem(
            custom_text="规则不能创建自定义项",
            reason="来源错误",
            source=RecommendationSource.RULE,
            rank=1,
        )


def test_session_enforces_versions_and_unique_selections() -> None:
    now = datetime.now(timezone.utc)
    valid = StoryBuilderSession(
        session_id="session_001",
        project_id="silicon_rise",
        selections=[selection(StoryStep.WORLDVIEW)],
        selection_version=1,
        recommendation_version=1,
        created_at=now,
        updated_at=now,
    )
    restored = StoryBuilderSession.model_validate_json(valid.model_dump_json())
    assert restored == valid

    with pytest.raises(ValidationError):
        StoryBuilderSession(
            session_id="session_002",
            project_id="silicon_rise",
            selections=[selection(StoryStep.WORLDVIEW), selection(StoryStep.WORLDVIEW, 2)],
            selection_version=2,
        )

    with pytest.raises(ValidationError):
        StoryBuilderSession(
            session_id="session_003",
            project_id="silicon_rise",
            selection_version=1,
            recommendation_version=2,
        )


def test_confirmed_blueprint_requires_all_steps_and_author_confirmation() -> None:
    with pytest.raises(ValidationError):
        StoryBlueprint(
            blueprint_id="blueprint_001",
            project_id="silicon_rise",
            source_session_id="session_001",
            source_selection_version=1,
            status=BlueprintStatus.CONFIRMED,
            premise="一粒硅尘在废墟中醒来",
            sections=blueprint_sections()[:-1],
            confirmed_by_author=True,
        )

    blueprint = StoryBlueprint(
        blueprint_id="blueprint_001",
        project_id="silicon_rise",
        source_session_id="session_001",
        source_selection_version=1,
        status=BlueprintStatus.CONFIRMED,
        premise="一粒硅尘在废墟中醒来",
        sections=blueprint_sections(),
        confirmed_by_author=True,
    )
    assert len(blueprint.sections) == len(StoryStep)


def test_confirmed_blueprint_rejects_unresolved_conflicts() -> None:
    with pytest.raises(ValidationError):
        StoryBlueprint(
            blueprint_id="blueprint_002",
            project_id="silicon_rise",
            source_session_id="session_001",
            source_selection_version=1,
            status=BlueprintStatus.CONFIRMED,
            premise="一粒硅尘在废墟中醒来",
            sections=blueprint_sections(),
            unresolved_conflicts=[
                ChoiceConflict(code="WORLD_CONFLICT", message="世界规则冲突")
            ],
            confirmed_by_author=True,
        )


def test_outline_package_enforces_hierarchy_and_confirmation() -> None:
    item = OutlineItem(
        item_id="book_main",
        title="全书主线",
        summary="主角从求生走向自主选择",
    )
    package = OutlinePackage(
        package_id="outline_book_v1",
        project_id="silicon_rise",
        blueprint_id="blueprint_001",
        blueprint_version=1,
        level=OutlineLevel.BOOK,
        status=OutlineStatus.CONFIRMED,
        items=[item],
        confirmed_by_author=True,
    )
    restored = OutlinePackage.model_validate_json(package.model_dump_json())
    assert restored == package

    with pytest.raises(ValidationError):
        OutlinePackage(
            package_id="outline_volume_v1",
            project_id="silicon_rise",
            blueprint_id="blueprint_001",
            blueprint_version=1,
            level=OutlineLevel.VOLUME,
            items=[item],
        )

    with pytest.raises(ValidationError):
        OutlinePackage(
            package_id="outline_empty_v1",
            project_id="silicon_rise",
            blueprint_id="blueprint_001",
            blueprint_version=1,
            level=OutlineLevel.BOOK,
            status=OutlineStatus.CONFIRMED,
            confirmed_by_author=True,
        )


def test_minimal_contract_fixture_validates() -> None:
    fixture_path = Path(__file__).parent / "fixtures" / "story_builder" / "minimal_contracts.yaml"
    data = yaml.safe_load(fixture_path.read_text(encoding="utf-8"))

    assert StoryBuilderSession.model_validate(data["session"]).selection_version == 1
    assert StoryBlueprint.model_validate(data["blueprint"]).status == BlueprintStatus.DRAFT
    assert OutlinePackage.model_validate(data["outline"]).level == OutlineLevel.BOOK


def test_catalog_rejects_unknown_or_backward_references() -> None:
    steps = [
        StoryBuilderStep(
            step=step,
            title=step.value,
            prompt=f"选择 {step.value}",
            skippable=True,
            min_selections=0,
        )
        for step in StoryStep
    ]
    options = [
        ChoiceOption(
            id=f"opt_{step.value}",
            step=step,
            name=step.value,
            summary=step.value,
        )
        for step in StoryStep
    ]
    options[0] = options[0].model_copy(update={"requires_any": [options[-1].id]})

    with pytest.raises(ValidationError):
        StoryChoiceCatalog(catalog_id="catalog_test", steps=steps, options=options)
