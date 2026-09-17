"""伏笔、悬念与长期因果（主计划 T11）。

- T11a：伏笔生命周期 planned → planted → reinforced → revealed → resolved / abandoned。
- T11b：回收必须有条件；玩家选择可以改变回收方式；伏笔可以失效或转化。
- T11c：悬念生命周期（reader_question / mystery），区分“读者知道、角色不知道”。

作者侧状态与角色知识严格分离：伏笔的 plan 属于作者安排，不会自动下放为角色知识；
只有当效果把知识写进 StoryState.knowledge 的 holders 时，角色才算知道。
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import Field, model_validator

from novelforge.models import StrictModel

from .conditions import Condition, evaluate
from .state import StoryState

ForeshadowStatus = Literal["planned", "planted", "reinforced", "revealed", "resolved", "abandoned"]
ALLOWED_TRANSITIONS: dict[str, tuple[str, ...]] = {
    "planned": ("planted", "abandoned"),
    "planted": ("reinforced", "revealed", "abandoned"),
    "reinforced": ("revealed", "abandoned"),
    "revealed": ("resolved", "abandoned"),
    "resolved": (),
    "abandoned": (),
}


class ForeshadowTransitionError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(message)


class Foreshadow(StrictModel):
    id: str = Field(min_length=1, max_length=128)
    title: str = Field(default="", max_length=120)
    status: ForeshadowStatus = "planned"
    payoff_condition: Condition | None = None
    planted_in: str = Field(default="", max_length=128)
    payoff_in: str = Field(default="", max_length=128)
    payoff_options: dict[str, Condition] = Field(default_factory=dict)
    transformed_into: str = Field(default="", max_length=128)
    author_note: str = Field(default="", max_length=300)
    data: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def payoff_requires_condition(self) -> "Foreshadow":
        if self.status in ("revealed", "resolved") and self.payoff_condition is None and not self.payoff_options:
            raise ValueError("revealed or resolved foreshadow requires a payoff condition")
        return self


class ReaderQuestion(StrictModel):
    id: str = Field(min_length=1, max_length=128)
    question: str = Field(default="", max_length=300)
    answer: str = Field(default="", max_length=300)
    reader_knows: bool = False
    character_knows: list[str] = Field(default_factory=list)
    resolved: bool = False


def transition(foreshadow: Foreshadow, status: ForeshadowStatus, *, note: str = "") -> Foreshadow:
    if status not in ALLOWED_TRANSITIONS[foreshadow.status]:
        raise ForeshadowTransitionError(
            "FORESHADOW_TRANSITION_INVALID",
            f"不能从 {foreshadow.status} 直接变为 {status}")
    return foreshadow.model_copy(update={"status": status,
                                         "author_note": note or foreshadow.author_note})


def payoff_ready(foreshadow: Foreshadow, state: StoryState, *, actor: str = "",
                 choice: str = "") -> tuple[bool, str]:
    """回收条件检查：玩家选择可以改变回收方式。"""

    condition = foreshadow.payoff_options.get(choice) if choice else None
    condition = condition or foreshadow.payoff_condition
    if condition is None:
        return False, "没有回收条件"
    result = evaluate(condition, state, actor=actor)
    return result.ok, result.message


def transform(foreshadow: Foreshadow, *, new_id: str, note: str = "") -> Foreshadow:
    return foreshadow.model_copy(update={"status": "abandoned", "transformed_into": new_id,
                                         "author_note": note or foreshadow.author_note})


def reader_knows(question: ReaderQuestion, character_id: str) -> bool:
    return question.reader_knows and character_id in question.character_knows


def reveal_to_reader(question: ReaderQuestion, *, answer: str = "") -> ReaderQuestion:
    return question.model_copy(update={"reader_knows": True, "answer": answer or question.answer})


def reveal_to_character(question: ReaderQuestion, character_id: str) -> ReaderQuestion:
    """读者知道不等于角色知道：只有显式写进角色列表才算角色获得信息。"""

    holders = list(question.character_knows)
    if character_id not in holders:
        holders.append(character_id)
    return question.model_copy(update={"character_knows": holders})


def foreshadow_timeline(state: StoryState) -> list[dict[str, Any]]:
    """伏笔运行时时间线（W5-02）：每个伏笔的当前状态、埋设 / 收束 tick 与已放置时长。

    状态本身仍然只存在 `StoryState.flags["foreshadows"]`（单一事实来源），这里只做只读整理。
    """

    registry = state.flags.get("foreshadows", {})
    if not isinstance(registry, dict):
        return []
    now = int(state.timeline.tick)
    rows: list[dict[str, Any]] = []
    for foreshadow_id, payload in registry.items():
        entry = dict(payload or {})
        status = str(entry.get("status", "planned") or "planned")
        planted = entry.get("planted_tick")
        closed = entry.get("closed_tick")
        rows.append({
            "id": str(foreshadow_id),
            "status": status,
            "updated_tick": int(entry.get("tick", 0) or 0),
            "planted_tick": int(planted) if isinstance(planted, (int, float)) else None,
            "closed_tick": int(closed) if isinstance(closed, (int, float)) else None,
            "age": max(0, now - int(planted)) if isinstance(planted, (int, float)) else 0,
            "reinforce_count": int(entry.get("reinforce_count", 0) or 0),
            "reason": str(entry.get("reason", "") or ""),
        })
    rows.sort(key=lambda row: (row["planted_tick"] is None, row["planted_tick"] or 0, row["id"]))
    return rows
