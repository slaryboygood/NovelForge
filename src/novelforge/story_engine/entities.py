"""通用实体模型（主计划 T06c）。

这些实体只定义“引擎认识的共同结构”，不定义“修仙有境界、科幻有义体”。
题材差异通过 `kind` / `tags` / `data` 表达：

- 修仙：Character.data["境界"]、Faction.kind = "sect"、Ability.kind = "功法"
- 科幻：Character.data["算力"]、Faction.kind = "corporation"、Ability.kind = "义体功能"

因此同一 Resolver / 同一 StoryState 可以表达两种题材，不需要在核心代码里写题材分支。

实体与“定义”严格分开：

- `ResourceDefinition` 描述某种资源是什么（内容包里的目录项）。
- `ResourceStock` 描述当前实际拥有多少（StoryState 里的库存）。
拥有目录项不等于拥有库存。

核心规则：
- 背景设定 ≠ 当前事实；“学过剑术” ≠ “当前有剑”。
- “某人知道秘密” ≠ “主角也知道秘密”；KnowledgeEntry 用 holders 区分。
- “家境富裕” ≠ “当前库存无限”；库存只能由事件或效果写入。
- “作者知道” ≠ “角色知道”；reader_visible 与 holders 分开。
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import Field, model_validator

from novelforge.models import StrictModel


class StateEntry(StrictModel):
    """通用实体条目：所有题材实体共用的最小外壳。"""

    id: str = Field(min_length=1, max_length=128)
    kind: str = Field(default="", max_length=64)
    tags: list[str] = Field(default_factory=list)
    data: dict[str, Any] = Field(default_factory=dict)


class Character(StateEntry):
    """角色。性格、目标、底线、声音等题材相关字段放进 data。"""

    name: str = Field(default="", max_length=80)
    status: str = Field(default="", max_length=64)


class Faction(StateEntry):
    name: str = Field(default="", max_length=80)
    stance: str = Field(default="", max_length=200)


class Location(StateEntry):
    name: str = Field(default="", max_length=80)
    access: str = Field(default="", max_length=200)


class Ability(StateEntry):
    """能力定义或角色已掌握的能力条目；是否已拥有由 StoryState 决定。"""

    name: str = Field(default="", max_length=80)
    limits: list[str] = Field(default_factory=list)


class ResourceDefinition(StateEntry):
    """资源目录项：描述资源是什么，不代表当前库存。"""

    name: str = Field(default="", max_length=80)
    unit: str = Field(default="", max_length=32)


class ResourceStock(StrictModel):
    """资源库存。只能由事件或效果写入，不允许负库存。"""

    id: str = Field(min_length=1, max_length=128)
    amount: float = Field(default=0, ge=0)
    unit: str = Field(default="", max_length=32)
    holders: list[str] = Field(default_factory=list)
    source: str = Field(default="", max_length=256)
    data: dict[str, Any] = Field(default_factory=dict)


class RelationshipState(StrictModel):
    """关系不是单一好感度；维度由题材内容包给出，可只启用其中一部分。"""

    source_id: str = Field(min_length=1, max_length=128)
    target_id: str = Field(min_length=1, max_length=128)
    dimensions: dict[str, float] = Field(default_factory=dict)
    tags: list[str] = Field(default_factory=list)
    data: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def distinct_endpoints(self) -> "RelationshipState":
        if self.source_id == self.target_id:
            raise ValueError("relationship endpoints must be different entities")
        return self


class KnowledgeEntry(StrictModel):
    """信息与持有者分离：作者知道 ≠ 角色知道。"""

    id: str = Field(min_length=1, max_length=128)
    holders: list[str] = Field(default_factory=list)
    source: str = Field(default="", max_length=256)
    source_event: str = Field(default="", max_length=128)
    tick: int = Field(default=0, ge=0)
    certainty: Literal["fact", "rumor", "guess", "plan"] = "fact"
    reader_visible: bool = False
    data: dict[str, Any] = Field(default_factory=dict)


class PromiseState(StrictModel):
    """承诺 / 债务 / 义务共用结构。"""

    id: str = Field(min_length=1, max_length=128)
    debtor: str = Field(default="", max_length=128)
    creditor: str = Field(default="", max_length=128)
    description: str = Field(default="", max_length=500)
    status: Literal["open", "settled", "broken", "cancelled"] = "open"
    source: str = Field(default="", max_length=256)
    created_tick: int = Field(default=0, ge=0)
    due_tick: int = Field(default=0, ge=0)
    settled_tick: int = Field(default=0, ge=0)
    data: dict[str, Any] = Field(default_factory=dict)


class Obligation(PromiseState):
    """承诺 / 债务 / 义务；具体类型放进 data["obligation_type"]。"""


class EventRecord(StrictModel):
    """已发生或待结算的事件引用。事件结构由 T08 EventCard 定义。"""

    id: str = Field(min_length=1, max_length=128)
    status: Literal["active", "resolved"] = "active"
    source: str = Field(default="", max_length=256)
    participants: list[str] = Field(default_factory=list)
    data: dict[str, Any] = Field(default_factory=dict)


class EffectRecord(StrictModel):
    """一次状态变化的来源记录：谁、因为什么、改了什么。"""

    id: str = Field(min_length=1, max_length=192)
    op: str = Field(default="", max_length=64)
    entity: str = Field(default="", max_length=128)
    target: str = Field(default="", max_length=128)
    value: Any = None
    source: str = Field(default="", max_length=128)
    order: int = Field(default=0, ge=0)
    data: dict[str, Any] = Field(default_factory=dict)


ENTITY_MODELS = (Character, Faction, Location, Ability, ResourceDefinition, Obligation)

__all__ = [
    "Ability",
    "Character",
    "ENTITY_MODELS",
    "EffectRecord",
    "EventRecord",
    "Faction",
    "KnowledgeEntry",
    "Location",
    "Obligation",
    "PromiseState",
    "RelationshipState",
    "ResourceDefinition",
    "ResourceStock",
    "StateEntry",
]
