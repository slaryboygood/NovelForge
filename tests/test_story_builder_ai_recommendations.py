from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from novelforge.story_builder import (
    AICustomSuggestion,
    AIOptionReason,
    AIRecommendationDraft,
    AIRecommendationSupplementer,
    DeterministicRecommendationEngine,
    RecommendationSource,
    StoryStep,
    load_story_catalog,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class StubStructuredProvider:
    def __init__(self, payload: object = None, error: Exception | None = None) -> None:
        self.payload = payload
        self.error = error
        self.calls: list[dict[str, Any]] = []

    def generate_structured(self, **kwargs: Any):
        self.calls.append(kwargs)
        if self.error:
            raise self.error
        model = kwargs["output_model"].model_validate(self.payload)
        return object(), model


@pytest.fixture
def rule_engine() -> DeterministicRecommendationEngine:
    return DeterministicRecommendationEngine(load_story_catalog(PROJECT_ROOT))


def recommendation_ids(result) -> list[str]:
    return [item.option_id for item in result.recommendations if item.option_id]


def test_ai_can_refine_allowed_reason_and_add_custom_suggestion(
    rule_engine: DeterministicRecommendationEngine,
) -> None:
    provider = StubStructuredProvider(
        {
            "option_reasons": [
                {
                    "option_id": "world_silicon_mmo",
                    "reason": "与成长冒险相连，能把升级反馈落实到探索行动。",
                    "fit_tags": ["非人文明"],
                    "risks": ["早期术语需要克制"],
                }
            ],
            "custom_suggestions": [
                {
                    "custom_text": "漂流星舰中的微型机械文明",
                    "reason": "保留非人探索，同时换成封闭航行压力。",
                    "fit_tags": ["探索"],
                    "risks": ["需要明确空间边界"],
                }
            ],
        }
    )
    service = AIRecommendationSupplementer(rule_engine, provider)

    result = service.recommend(
        StoryStep.WORLDVIEW,
        ["experience_growth_adventure"],
        based_on_version=1,
    )

    assert recommendation_ids(result) == ["world_silicon_mmo", "world_cultivation_realms", "world_modern_supernatural"]
    assert result.recommendations[0].source == RecommendationSource.AI
    assert result.recommendations[0].reason.startswith("与成长冒险")
    assert result.recommendations[-1].option_id is None
    assert result.recommendations[-1].custom_text == "漂流星舰中的微型机械文明"
    assert [item.rank for item in result.recommendations] == [1, 2, 3, 4]
    assert len(provider.calls) == 1


def test_provider_receives_only_public_choice_context(
    rule_engine: DeterministicRecommendationEngine,
) -> None:
    provider = StubStructuredProvider({"option_reasons": [], "custom_suggestions": []})
    service = AIRecommendationSupplementer(rule_engine, provider)

    service.recommend(StoryStep.WORLDVIEW, ["experience_growth_adventure"])

    context = provider.calls[0]["context"]
    assert set(context) == {"step", "selected_options", "custom_selections", "allowed_candidates"}
    serialized = str(context).lower()
    assert "restricted" not in serialized
    assert "endgame" not in serialized
    assert "provider" not in serialized


@pytest.mark.parametrize(
    "payload",
    [
        {"option_reasons": [{"option_id": "background_hidden_city", "reason": "不是本步骤的选项"}]},
        {"option_reasons": "不是列表"},
        {"unexpected": "field"},
    ],
)
def test_invalid_or_out_of_rule_ai_output_falls_back_unchanged(
    rule_engine: DeterministicRecommendationEngine,
    payload: object,
) -> None:
    provider = StubStructuredProvider(payload)
    service = AIRecommendationSupplementer(rule_engine, provider)
    expected = rule_engine.recommend(StoryStep.WORLDVIEW, ["experience_growth_adventure"])

    result = service.recommend(StoryStep.WORLDVIEW, ["experience_growth_adventure"])

    assert result == expected


def test_provider_exception_falls_back_without_blocking(
    rule_engine: DeterministicRecommendationEngine,
) -> None:
    provider = StubStructuredProvider(error=TimeoutError("模型超时"))
    service = AIRecommendationSupplementer(rule_engine, provider)
    expected = rule_engine.recommend(StoryStep.WORLDVIEW, ["experience_growth_adventure"])

    result = service.recommend(StoryStep.WORLDVIEW, ["experience_growth_adventure"])

    assert result == expected
    assert result.can_continue is True


def test_no_provider_returns_rule_result(rule_engine: DeterministicRecommendationEngine) -> None:
    service = AIRecommendationSupplementer(rule_engine, None)

    result = service.recommend(StoryStep.WORLDVIEW, ["experience_growth_adventure"])

    assert result == rule_engine.recommend(
        StoryStep.WORLDVIEW,
        ["experience_growth_adventure"],
    )


def test_blocking_rule_conflict_skips_ai(rule_engine: DeterministicRecommendationEngine) -> None:
    provider = StubStructuredProvider({"option_reasons": [], "custom_suggestions": []})
    service = AIRecommendationSupplementer(rule_engine, provider)

    result = service.recommend(
        StoryStep.WORLDVIEW,
        ["experience_growth_adventure", "experience_mystery_exploration"],
    )

    assert result.can_continue is False
    assert provider.calls == []


def test_selected_author_boundary_disables_ai_custom_suggestions(
    rule_engine: DeterministicRecommendationEngine,
) -> None:
    provider = StubStructuredProvider(
        AIRecommendationDraft(
            option_reasons=[
                AIOptionReason(
                    option_id="world_cultivation_realms",
                    reason="保留成长方向并转入宗门秩序。",
                )
            ],
            custom_suggestions=[
                AICustomSuggestion(
                    custom_text="让主角突然获得无代价神力",
                    reason="制造即时爽点。",
                )
            ],
        )
    )
    service = AIRecommendationSupplementer(rule_engine, provider)
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
        "boundary_no_free_power",
    ]

    result = service.recommend(StoryStep.WORLDVIEW, selected)

    assert all(not item.custom_text for item in result.recommendations)


def test_custom_input_is_visible_to_ai_but_not_promoted_to_catalog_requirement(
    rule_engine: DeterministicRecommendationEngine,
) -> None:
    provider = StubStructuredProvider(
        {
            "option_reasons": [],
            "custom_suggestions": [
                {
                    "custom_text": "失重档案馆中的记忆生命",
                    "reason": "响应作者自定义的冷峻探索感。",
                }
            ],
        }
    )
    service = AIRecommendationSupplementer(rule_engine, provider)

    result = service.recommend(
        StoryStep.WORLDVIEW,
        custom_selections={StoryStep.READER_EXPERIENCE: ["冷峻但有希望的探索感"]},
    )

    assert len(result.recommendations) == 4
    assert result.recommendations[-1].option_id is None
    assert result.recommendations[-1].custom_text == "失重档案馆中的记忆生命"
    assert result.can_continue is True
    assert provider.calls[0]["context"]["custom_selections"] == {
        "reader_experience": ["冷峻但有希望的探索感"]
    }
