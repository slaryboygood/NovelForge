"""通用 Action 模型（主计划 T07a）。

Action 只描述结构：谁对谁做什么、需要什么条件、付出什么成本、冒什么风险、
产生什么即时与延迟效果、对外是否可见。

引擎不认识“闭关”“炼丹”“黑客入侵”这类具体行为；具体行为由内容包
（ActionCatalog / 内容目录）提供，底层只识别通用字段。
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Literal

from pydantic import Field, model_validator

from novelforge.models import StrictModel

from .conditions import Condition
from .effects import EffectSpec

Visibility = Literal["public", "private", "hidden", "secret"]


class RiskSpec(StrictModel):
    id: str = Field(default="", max_length=128)
    description: str = Field(default="", max_length=300)
    probability: float = Field(default=0, ge=0, le=1)
    effects: list[EffectSpec] = Field(default_factory=list)
    data: dict[str, Any] = Field(default_factory=dict)


class DelayedEffectSpec(StrictModel):
    """现在发生，未来生效：保存来源行动与触发条件。"""

    id: str = Field(min_length=1, max_length=128)
    trigger: Condition
    effects: list[EffectSpec] = Field(default_factory=list)
    source: str = Field(default="", max_length=128)
    description: str = Field(default="", max_length=300)
    data: dict[str, Any] = Field(default_factory=dict)


class Action(StrictModel):
    id: str = Field(pattern=r"^[a-z][a-z0-9_]{2,95}$")
    kind: str = Field(default="", max_length=64)
    name: str = Field(default="", max_length=80)
    actor: str = Field(default="", max_length=128)
    target: str = Field(default="", max_length=128)
    type: str = Field(default="", max_length=64)
    requirements: list[Condition] = Field(default_factory=list)
    costs: list[EffectSpec] = Field(default_factory=list)
    risks: list[RiskSpec] = Field(default_factory=list)
    immediate_effects: list[EffectSpec] = Field(default_factory=list)
    delayed_effects: list[DelayedEffectSpec] = Field(default_factory=list)
    visibility: Visibility = "private"
    data: dict[str, Any] = Field(default_factory=dict)


class ActionCatalog(StrictModel):
    schema_version: Literal[1] = 1
    catalog_id: str = Field(default="actions", max_length=96)
    actions: list[Action] = Field(default_factory=list)

    @model_validator(mode="after")
    def unique_action_ids(self) -> "ActionCatalog":
        ids = [item.id for item in self.actions]
        if len(ids) != len(set(ids)):
            raise ValueError("action ids must be unique")
        return self

    def by_id(self, action_id: str) -> Action:
        for item in self.actions:
            if item.id == action_id:
                return item
        raise KeyError(action_id)


def action_catalog_from_payload(payload: Mapping[str, Any]) -> ActionCatalog:
    return ActionCatalog.model_validate(dict(payload))
