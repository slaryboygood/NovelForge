from __future__ import annotations

from typing import Any, Iterable, Mapping, Protocol, Sequence

from pydantic import Field, field_validator, model_validator

from novelforge.models import StrictModel

from .catalog import StoryCatalogError
from .models import (
    RecommendationItem,
    RecommendationResult,
    RecommendationSource,
    StoryStep,
)
from .recommendations import DeterministicRecommendationEngine


class StructuredRecommendationProvider(Protocol):
    def generate_structured(self, **kwargs: Any) -> tuple[Any, Any]: ...


class AIOptionReason(StrictModel):
    option_id: str
    reason: str = Field(min_length=1, max_length=500)
    fit_tags: list[str] = Field(default_factory=list, max_length=6)
    risks: list[str] = Field(default_factory=list, max_length=4)


class AICustomSuggestion(StrictModel):
    custom_text: str = Field(min_length=1, max_length=500)
    reason: str = Field(min_length=1, max_length=500)
    fit_tags: list[str] = Field(default_factory=list, max_length=6)
    risks: list[str] = Field(default_factory=list, max_length=4)


class AIRecommendationDraft(StrictModel):
    option_reasons: list[AIOptionReason] = Field(default_factory=list, max_length=5)
    custom_suggestions: list[AICustomSuggestion] = Field(default_factory=list, max_length=2)

    @field_validator("option_reasons")
    @classmethod
    def unique_option_ids(cls, value: list[AIOptionReason]) -> list[AIOptionReason]:
        option_ids = [item.option_id for item in value]
        if len(option_ids) != len(set(option_ids)):
            raise ValueError("AI option recommendations must not repeat option IDs")
        return value

    @model_validator(mode="after")
    def unique_custom_suggestions(self) -> "AIRecommendationDraft":
        texts = [item.custom_text.strip().casefold() for item in self.custom_suggestions]
        if len(texts) != len(set(texts)):
            raise ValueError("AI custom suggestions must not repeat")
        return self


class AIRecommendationSupplementer:
    """在确定性候选边界内补充理由；任何失败都原样退回规则结果。"""

    def __init__(
        self,
        rule_engine: DeterministicRecommendationEngine,
        provider: StructuredRecommendationProvider | None,
    ) -> None:
        self.rule_engine = rule_engine
        self.provider = provider if provider is not None else _default_provider()

    def recommend(
        self,
        step: StoryStep | str,
        selected_option_ids: Iterable[str] = (),
        *,
        based_on_version: int = 0,
        custom_selections: Mapping[StoryStep | str, Sequence[str]] | None = None,
        limit: int = 5,
        allow_entry: bool = False,
    ) -> RecommendationResult:
        selected = tuple(selected_option_ids)
        custom = self._normalize_custom_selections(custom_selections or {})
        rule_result = self.rule_engine.recommend(
            step,
            selected,
            based_on_version=based_on_version,
            custom_selection_counts={key: len(values) for key, values in custom.items()},
            limit=limit,
            allow_entry=allow_entry,
        )
        if self.provider is None or not rule_result.can_continue:
            return rule_result

        allowed_ids = {
            item.option_id for item in rule_result.recommendations if item.option_id is not None
        }
        try:
            _, raw_draft = self.provider.generate_structured(
                chapter_id="story_builder",
                stage="story_builder_recommendations",
                skill_name=None,
                prompt=self._prompt(rule_result, selected, custom),
                context=self._public_context(rule_result, selected, custom),
                output_model=AIRecommendationDraft,
                workspace=None,
            )
            draft = (
                raw_draft
                if isinstance(raw_draft, AIRecommendationDraft)
                else AIRecommendationDraft.model_validate(raw_draft)
            )
            if any(item.option_id not in allowed_ids for item in draft.option_reasons):
                raise StoryCatalogError(
                    "AI_RECOMMENDATION_OUTSIDE_RULES",
                    "AI 推荐包含规则未允许的目录选项",
                )
            return self._merge(rule_result, draft, selected, limit)
        except Exception:
            return rule_result

    def _merge(
        self,
        rule_result: RecommendationResult,
        draft: AIRecommendationDraft,
        selected: tuple[str, ...],
        limit: int,
    ) -> RecommendationResult:
        reason_by_id = {item.option_id: item for item in draft.option_reasons}
        merged: list[RecommendationItem] = []
        for rule_item in rule_result.recommendations:
            ai_item = reason_by_id.get(rule_item.option_id)
            if ai_item is None:
                merged.append(rule_item.model_copy(update={"rank": len(merged) + 1}))
                continue
            merged.append(
                RecommendationItem(
                    option_id=rule_item.option_id,
                    reason=ai_item.reason,
                    fit_tags=ai_item.fit_tags or rule_item.fit_tags,
                    risks=ai_item.risks or rule_item.risks,
                    source=RecommendationSource.AI,
                    rank=len(merged) + 1,
                )
            )

        selected_boundaries = any(
            self.rule_engine.catalog.require_option(option_id).step == StoryStep.AUTHOR_BOUNDARIES
            for option_id in selected
        )
        existing_names = {
            self.rule_engine.catalog.require_option(item.option_id).name.strip().casefold()
            for item in rule_result.recommendations
            if item.option_id
        }
        if not selected_boundaries:
            for suggestion in draft.custom_suggestions:
                if len(merged) >= limit:
                    break
                if suggestion.custom_text.strip().casefold() in existing_names:
                    continue
                merged.append(
                    RecommendationItem(
                        custom_text=suggestion.custom_text.strip(),
                        reason=suggestion.reason,
                        fit_tags=suggestion.fit_tags,
                        risks=suggestion.risks,
                        source=RecommendationSource.AI,
                        rank=len(merged) + 1,
                    )
                )

        payload = rule_result.model_dump(mode="python")
        payload["recommendations"] = [item.model_dump(mode="python") for item in merged]
        return RecommendationResult.model_validate(payload)

    def _public_context(
        self,
        rule_result: RecommendationResult,
        selected: tuple[str, ...],
        custom: Mapping[StoryStep, tuple[str, ...]],
    ) -> dict[str, Any]:
        step = self.rule_engine.catalog.require_step(rule_result.step)
        return {
            "step": {"id": step.step.value, "title": step.title, "prompt": step.prompt},
            "selected_options": [
                {
                    "id": option.id,
                    "step": option.step.value,
                    "name": option.name,
                    "summary": option.summary,
                    "tags": option.tags,
                    "effects": option.effects,
                }
                for option in (self.rule_engine.catalog.require_option(item) for item in selected)
            ],
            "custom_selections": {
                key.value: list(values) for key, values in custom.items()
            },
            "allowed_candidates": [
                {
                    "id": item.option_id,
                    "name": self.rule_engine.catalog.require_option(item.option_id).name,
                    "summary": self.rule_engine.catalog.require_option(item.option_id).summary,
                    "rule_reason": item.reason,
                }
                for item in rule_result.recommendations
                if item.option_id
            ],
        }

    def _prompt(
        self,
        rule_result: RecommendationResult,
        selected: tuple[str, ...],
        custom: Mapping[StoryStep, tuple[str, ...]],
    ) -> str:
        context = self._public_context(rule_result, selected, custom)
        allowed = "、".join(
            item["id"] for item in context["allowed_candidates"]
        )
        return (
            "你是作者构筑助手，只补充选择理由，不替作者决定。\n"
            f"当前步骤：{context['step']['title']}。\n"
            f"允许解释的目录选项只有：{allowed}。\n"
            "option_reasons 中不得出现其他 option_id，不得修改、排斥或自动选中任何选项。\n"
            "可提出最多 2 个 custom_suggestions，但它们只是待作者确认的文字方向，不是正式目录选项。\n"
            "不要读取或推测终局秘密、受限作者意图、模型配置和小说正式状态。\n"
            "理由使用简洁中文，说明与当前选择的联系和风险。严格按输出模型返回。"
        )

    def _normalize_custom_selections(
        self,
        values: Mapping[StoryStep | str, Sequence[str]],
    ) -> dict[StoryStep, tuple[str, ...]]:
        normalized: dict[StoryStep, tuple[str, ...]] = {}
        for raw_step, raw_values in values.items():
            step = self.rule_engine.catalog.require_step(raw_step).step
            cleaned = tuple(item.strip() for item in raw_values if item.strip())
            normalized[step] = cleaned
        return normalized


def _default_provider() -> Any | None:
    """V4-04 §14：默认 provider 经 `novelforge.ai` 的 Gateway 桥（函数内惰性 import）。

    未配置 enabled provider 时返回 None，保持 V3 的规则式行为。
    """

    from novelforge.ai import default_structured_provider

    return default_structured_provider()
