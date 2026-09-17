"""候选行动生成（V2-C-01 / C-02 / C-06）。

行动是否合法只由 Condition 与 ActionResolver 的可用性判断决定；
LLM 只能提议 action_id，最终仍要经过这里过滤。
同一场景在不同 StoryState 下会得到不同的可行动作集合。
"""

from __future__ import annotations

from typing import Any

from pydantic import Field

from novelforge.models import StrictModel

from .actions import Action, ActionCatalog
from .characters import active_goals, character_memories, select_goal
from .conditions import evaluate
from .effects import apply_effects
from .events import EventCardCatalog, EventTriggerEngine
from .state import StoryState


class ActionCandidate(StrictModel):
    action_id: str
    name: str = ""
    kind: str = ""
    available: bool
    code: str = ""
    reason: str = ""
    requirements: list[dict[str, Any]] = Field(default_factory=list)
    costs: list[dict[str, Any]] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    visibility: str = "private"
    related_characters: list[str] = Field(default_factory=list)
    goal_notes: list[str] = Field(default_factory=list)
    memory_notes: list[str] = Field(default_factory=list)
    sort_key: float = 0.0

    def as_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json")


def _goal_notes(state: StoryState, actor: str, action: Action) -> tuple[list[str], float]:
    if not actor or actor not in state.characters:
        return [], 0.0
    notes: list[str] = []
    score = 0.0
    goal = select_goal(state, actor)
    if goal is not None and goal.title and (goal.title in action.name
                                            or goal.title in str(action.data.get("serves", ""))):
        score += goal.score()
        notes.append(f"服务当前目标：{goal.title}")
    for item in active_goals(state, actor):
        if item.id != (goal.id if goal else "") and item.title in action.name:
            score += 0.3 * item.score()
            notes.append(f"同时推进：{item.title}")
    return notes, score


def _memory_notes(state: StoryState, actor: str, action: Action) -> list[str]:
    if not actor or actor not in state.characters:
        return []
    tags = [str(item) for item in action.data.get("tags", [])]
    notes = []
    for memory in character_memories(state, actor):
        if memory.emotion and any(tag in tags for tag in memory.emotion):
            notes.append(f"记忆影响（{memory.id}）：{memory.summary}")
    return notes


def generate_candidates(state: StoryState, catalog: ActionCatalog, action_ids: list[str], *,
                        actor: str = "", target: str = "") -> list[ActionCandidate]:
    """按当前状态生成候选行动，含可用性、原因、成本、风险与角色/目标影响。"""

    rows: list[ActionCandidate] = []
    for action_id in action_ids:
        try:
            action = catalog.by_id(action_id)
        except KeyError:
            rows.append(ActionCandidate(action_id=action_id, available=False,
                                        code="ACTION_NOT_FOUND", reason="内容包里没有这个行动"))
            continue
        reason = ""
        code = ""
        for requirement in action.requirements:
            result = evaluate(requirement, state, actor=actor)
            if not result.ok:
                code, reason = result.code or "REQUIREMENT_NOT_SATISFIED", result.message
                break
        if not code:
            paid = apply_effects(state, action.costs, actor=actor, source=f"check:{action_id}")
            if not paid.ok:
                code, reason = paid.code, paid.message
        goal_notes, goal_score = _goal_notes(state, actor, action)
        memory_notes = _memory_notes(state, actor, action)
        rows.append(ActionCandidate(
            action_id=action.id, name=action.name, kind=action.kind, available=not code,
            code=code, reason=reason,
            requirements=[item.model_dump(mode="json") for item in action.requirements],
            costs=[item.model_dump(mode="json") for item in action.costs],
            risks=[item.description or item.id for item in action.risks],
            visibility=action.visibility,
            related_characters=[item for item in (action.actor, action.target, actor, target) if item],
            goal_notes=goal_notes, memory_notes=memory_notes,
            sort_key=goal_score + float(action.data.get("weight", 0) or 0)))
    return sorted(rows, key=lambda item: (not item.available, -item.sort_key, item.action_id))


def available_actions(rows: list[ActionCandidate]) -> list[str]:
    return [item.action_id for item in rows if item.available]


def filter_llm_action_proposals(proposals: list[str], rows: list[ActionCandidate]) -> list[str]:
    """LLM 提议的 action_id 必须已经通过规则判定，否则丢弃。"""

    allowed = set(available_actions(rows))
    return [item for item in proposals if item in allowed]


class EventChainResult(StrictModel):
    fired: list[str] = Field(default_factory=list)
    depth: int = 0
    state: StoryState


def fire_event_chain(state: StoryState, catalog: EventCardCatalog, event_id: str, *,
                     actor: str = "", max_depth: int = 5) -> EventChainResult:
    """事件连锁：一个事件可以触发它的 followups，深度受限，不产生第二套事件系统。"""

    engine = EventTriggerEngine(catalog)
    working = state.model_copy(deep=True)
    fired: list[str] = []
    queue = [(event_id, 0)]
    while queue:
        current, depth = queue.pop(0)
        if depth > max_depth:
            continue
        outcome = engine.fire(working, current, actor=actor)
        if not outcome.ok:
            continue
        working = outcome.state
        fired.append(current)
        for followup in outcome.activated_followups:
            queue.append((followup, depth + 1))
    return EventChainResult(fired=fired, depth=min(max_depth, len(fired)), state=working)
