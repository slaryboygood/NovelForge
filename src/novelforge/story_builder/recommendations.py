from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Mapping

from .catalog import StoryCatalogError, StoryCatalogIndex
from .models import (
    STORY_STEP_ORDER,
    ChoiceConflict,
    ChoiceOption,
    RecommendationItem,
    RecommendationResult,
    RecommendationSource,
    StoryStep,
)


@dataclass(frozen=True, slots=True)
class OptionEligibility:
    option_id: str
    eligible: bool
    missing_all: tuple[str, ...] = ()
    missing_any: tuple[str, ...] = ()
    excluded_by: tuple[str, ...] = ()


class DeterministicRecommendationEngine:
    """只依据目录和作者选择计算候选，不调用模型、不修改会话。"""

    def __init__(self, catalog: StoryCatalogIndex) -> None:
        self.catalog = catalog

    def recommend(
        self,
        step: StoryStep | str,
        selected_option_ids: Iterable[str] = (),
        *,
        based_on_version: int = 0,
        custom_selection_counts: Mapping[StoryStep | str, int] | None = None,
        limit: int = 5,
        allow_entry: bool = False,
    ) -> RecommendationResult:
        if not 1 <= limit <= 5:
            raise StoryCatalogError("RECOMMENDATION_LIMIT_INVALID", "推荐数量必须在 1 到 5 之间")

        target = self.catalog.require_step(step).step
        selected = self._normalize_selected(selected_option_ids)
        custom_counts = self._normalize_custom_counts(custom_selection_counts or {})
        conflicts = self.find_conflicts(selected, custom_counts)
        unlocked = self.unlocked_steps(selected, custom_counts)

        if target not in unlocked and not allow_entry:
            conflicts.append(
                ChoiceConflict(
                    code="STEP_LOCKED",
                    message=f"步骤“{self.catalog.require_step(target).title}”尚未解锁，请先完成前一步。",
                )
            )
            return RecommendationResult(
                step=target,
                based_on_version=based_on_version,
                conflicts=self._sort_conflicts(conflicts),
                unlocked_steps=list(unlocked),
                can_continue=False,
            )

        candidates = [
            option
            for option in self.catalog.options_for_step(target)
            if self.evaluate_option(option, selected).eligible
        ]
        available_candidates = [option for option in candidates if option.id not in selected]
        recommendations = [
            self._recommendation_item(option, rank, selected)
            for rank, option in enumerate(
                sorted(
                    available_candidates,
                    key=lambda item: self._candidate_sort_key(item, selected),
                )[:limit],
                start=1,
            )
        ]

        if not candidates:
            conflicts.append(
                ChoiceConflict(
                    code="NO_ELIGIBLE_OPTIONS",
                    message="当前选择没有匹配的目录推荐，你仍可填写自定义内容继续。",
                    blocking=False,
                )
            )

        conflicts = self._sort_conflicts(conflicts)
        return RecommendationResult(
            step=target,
            based_on_version=based_on_version,
            recommendations=recommendations,
            conflicts=conflicts,
            unlocked_steps=list(unlocked),
            can_continue=not any(conflict.blocking for conflict in conflicts),
        )

    def evaluate_option(
        self,
        option: ChoiceOption | str,
        selected_option_ids: Iterable[str],
    ) -> OptionEligibility:
        candidate = self.catalog.require_option(option) if isinstance(option, str) else option
        selected = set(selected_option_ids)
        missing_all = tuple(sorted(set(candidate.requires_all) - selected))
        missing_any = (
            tuple(sorted(candidate.requires_any))
            if candidate.requires_any and not selected.intersection(candidate.requires_any)
            else ()
        )
        excluded_by = tuple(sorted(selected.intersection(candidate.excludes)))
        return OptionEligibility(
            option_id=candidate.id,
            eligible=not missing_all and not missing_any and not excluded_by,
            missing_all=missing_all,
            missing_any=missing_any,
            excluded_by=excluded_by,
        )

    def find_conflicts(
        self,
        selected_option_ids: Iterable[str],
        custom_selection_counts: Mapping[StoryStep, int] | None = None,
    ) -> list[ChoiceConflict]:
        selected = self._normalize_selected(selected_option_ids)
        custom_counts = custom_selection_counts or {}
        conflicts: list[ChoiceConflict] = []
        exclusion_pairs: set[tuple[str, str]] = set()

        for option_id in selected:
            option = self.catalog.require_option(option_id)
            decision = self.evaluate_option(option, selected)
            if decision.missing_all:
                conflicts.append(
                    ChoiceConflict(
                        code="REQUIREMENT_ALL_UNMET",
                        message=f"选项“{option.name}”缺少必须同时满足的前置选择。",
                        option_ids=[option.id, *decision.missing_all],
                    )
                )
            if decision.missing_any:
                conflicts.append(
                    ChoiceConflict(
                        code="REQUIREMENT_ANY_UNMET",
                        message=f"选项“{option.name}”需要至少满足一个前置选择。",
                        option_ids=[option.id, *decision.missing_any],
                    )
                )
            for excluded_id in decision.excluded_by:
                pair = tuple(sorted((option.id, excluded_id)))
                if pair in exclusion_pairs:
                    continue
                exclusion_pairs.add(pair)
                conflicts.append(
                    ChoiceConflict(
                        code="OPTION_EXCLUSION_CONFLICT",
                        message=(
                            f"选项“{option.name}”与“{self.catalog.require_option(excluded_id).name}”不能同时选择。"
                        ),
                        option_ids=list(pair),
                    )
                )

        for step in STORY_STEP_ORDER:
            step_config = self.catalog.require_step(step)
            selected_count = sum(
                self.catalog.require_option(option_id).step == step for option_id in selected
            ) + int(custom_counts.get(step, 0))
            if selected_count > step_config.max_selections:
                option_ids = [
                    option_id
                    for option_id in selected
                    if self.catalog.require_option(option_id).step == step
                ]
                conflicts.append(
                    ChoiceConflict(
                        code="SELECTION_LIMIT_EXCEEDED",
                        message=f"步骤“{step_config.title}”最多选择 {step_config.max_selections} 项。",
                        option_ids=option_ids,
                    )
                )
        return self._sort_conflicts(conflicts)

    def unlocked_steps(
        self,
        selected_option_ids: Iterable[str],
        custom_selection_counts: Mapping[StoryStep, int] | None = None,
    ) -> tuple[StoryStep, ...]:
        selected = self._normalize_selected(selected_option_ids)
        custom_counts = custom_selection_counts or {}
        individually_valid = {
            option_id
            for option_id in selected
            if self.evaluate_option(option_id, selected).eligible
        }
        unlocked = {STORY_STEP_ORDER[0]}

        for step in STORY_STEP_ORDER:
            if step not in unlocked:
                continue
            config = self.catalog.require_step(step)
            count = sum(
                self.catalog.require_option(option_id).step == step
                for option_id in individually_valid
            ) + int(custom_counts.get(step, 0))
            if config.min_selections <= count <= config.max_selections:
                unlocked.update(config.next_steps)
        return tuple(step for step in STORY_STEP_ORDER if step in unlocked)

    def _normalize_selected(self, selected_option_ids: Iterable[str]) -> tuple[str, ...]:
        selected = tuple(selected_option_ids)
        if len(selected) != len(set(selected)):
            raise StoryCatalogError("SELECTION_DUPLICATE", "作者选择中存在重复选项")
        for option_id in selected:
            self.catalog.require_option(option_id)
        return tuple(
            sorted(
                selected,
                key=lambda option_id: (
                    STORY_STEP_ORDER.index(self.catalog.require_option(option_id).step),
                    option_id,
                ),
            )
        )

    def _normalize_custom_counts(
        self,
        values: Mapping[StoryStep | str, int],
    ) -> dict[StoryStep, int]:
        normalized: dict[StoryStep, int] = {}
        for raw_step, count in values.items():
            step = self.catalog.require_step(raw_step).step
            if not isinstance(count, int) or isinstance(count, bool) or count < 0:
                raise StoryCatalogError("CUSTOM_SELECTION_COUNT_INVALID", "自定义选择数量必须是非负整数")
            normalized[step] = count
        return normalized

    def _candidate_sort_key(self, option: ChoiceOption, selected: tuple[str, ...]) -> tuple[int, int, str]:
        unlock_count = sum(
            option.id in self.catalog.require_option(option_id).unlocks for option_id in selected
        )
        return (-unlock_count, -option.priority, option.id)

    def _recommendation_item(
        self,
        option: ChoiceOption,
        rank: int,
        selected: tuple[str, ...],
    ) -> RecommendationItem:
        unlockers = [
            self.catalog.require_option(option_id).name
            for option_id in selected
            if option.id in self.catalog.require_option(option_id).unlocks
        ]
        if unlockers:
            reason = f"由已选“{'、'.join(unlockers)}”明确解锁，与当前故事方向直接衔接。"
        elif option.requires_all or option.requires_any:
            reason = "当前选择已满足该方向的前置条件，可作为下一步组合。"
        else:
            reason = "这是当前步骤的基础方向，可与已有选择继续组合。"
        risks = [option.effects["risk"]] if option.effects.get("risk") else []
        return RecommendationItem(
            option_id=option.id,
            reason=reason,
            fit_tags=option.tags,
            risks=risks,
            source=RecommendationSource.RULE,
            rank=rank,
        )

    @staticmethod
    def _sort_conflicts(conflicts: Iterable[ChoiceConflict]) -> list[ChoiceConflict]:
        return sorted(
            conflicts,
            key=lambda conflict: (
                not conflict.blocking,
                conflict.code,
                tuple(conflict.option_ids),
            ),
        )
