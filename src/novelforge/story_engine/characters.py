"""角色自主反应（主计划 T09）。

- T09a：CharacterDecisionContext 把角色的 goal / desire / fear / personality /
  bottom_line / relationship / knowledge / current_pressure 组合成决策上下文。
- T09b：规则型反应 + LLM 提议边界（LLM 只能提议，不能创造知识、资源或关系）。
- T09c：关系不是单一好感度，按维度参与反应评分。

原则：性格是倾向，不是强制脚本。评分只调整优先级，除非角色明确给出底线，
否则不会因为“性格不符”直接禁止某个行动。
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import Field

from novelforge.models import StrictModel

from .actions import Action
from .conditions import Condition, evaluate
from .state import StoryState

GoalScope = Literal["long_term", "stage", "current"]
GoalStatus = Literal["active", "paused", "completed", "failed", "abandoned"]


class CharacterGoal(StrictModel):
    """角色目标：只影响倾向与权重，不是必须发生的剧情。"""

    id: str = Field(min_length=1, max_length=64)
    scope: GoalScope = "current"
    title: str = Field(default="", max_length=120)
    description: str = Field(default="", max_length=300)
    priority: float = Field(default=1.0, ge=0, le=100)
    weight: float = Field(default=1.0, ge=0, le=100)
    status: GoalStatus = "active"
    source: str = Field(default="", max_length=128)
    updated_tick: int = Field(default=0, ge=0)
    when: Condition | None = None
    data: dict[str, Any] = Field(default_factory=dict)

    def score(self) -> float:
        return self.priority * self.weight


class CharacterMemory(StrictModel):
    id: str = Field(min_length=1, max_length=64)
    holder: str = Field(min_length=1, max_length=128)
    summary: str = Field(default="", max_length=300)
    source: str = Field(default="", max_length=128)
    tick: int = Field(default=0, ge=0)
    participants: list[str] = Field(default_factory=list)
    emotion: list[str] = Field(default_factory=list)
    data: dict[str, Any] = Field(default_factory=dict)


def _character_data(state: StoryState, character_id: str) -> tuple[Any, dict[str, Any]]:
    from .entities import Character

    entry = state.characters.get(character_id) or Character(id=character_id, kind="character")
    return entry, dict(entry.data)


def _write_character_data(state: StoryState, character_id: str, data: dict[str, Any]) -> StoryState:
    from .entities import Character

    working = state.model_copy(deep=True)
    entry = working.characters.get(character_id) or Character(id=character_id, kind="character")
    working.characters[character_id] = entry.model_copy(update={"data": data})
    return working


def character_goals(state: StoryState, character_id: str) -> list[CharacterGoal]:
    """读取角色目标；多个目标可以并存，全部存在角色自己的 data 里。"""

    _, data = _character_data(state, character_id)
    return [CharacterGoal.model_validate(item) for item in data.get("goals", [])]


def set_goals(state: StoryState, character_id: str, goals: list[CharacterGoal | dict],
              *, source: str = "author") -> StoryState:
    _, data = _character_data(state, character_id)
    data["goals"] = [item.model_dump(mode="json") if isinstance(item, CharacterGoal)
                     else CharacterGoal.model_validate(item).model_dump(mode="json")
                     for item in goals]
    return _write_character_data(state, character_id, data)


def upsert_goal(state: StoryState, character_id: str, goal: CharacterGoal | dict, *,
                source: str = "event") -> StoryState:
    """新增或更新目标；同时写入来源与当前世界时间，便于追溯。"""

    candidate = goal if isinstance(goal, CharacterGoal) else CharacterGoal.model_validate(goal)
    candidate = candidate.model_copy(update={"source": source or candidate.source,
                                             "updated_tick": state.timeline.tick})
    goals = [item for item in character_goals(state, character_id) if item.id != candidate.id]
    goals.append(candidate)
    return set_goals(state, character_id, goals, source=source)


def update_goal_status(state: StoryState, character_id: str, goal_id: str, status: GoalStatus, *,
                       note: str = "") -> StoryState:
    """改变目标状态：完成 / 失败 / 暂停 / 放弃；target 不是强制脚本。"""

    goals = []
    for item in character_goals(state, character_id):
        if item.id == goal_id:
            data = dict(item.data)
            if note:
                data["note"] = note
            item = item.model_copy(update={"status": status, "data": data,
                                           "updated_tick": state.timeline.tick})
        goals.append(item)
    return set_goals(state, character_id, goals, source="status_change")


def active_goals(state: StoryState, character_id: str, *, scope: GoalScope | None = None
                 ) -> list[CharacterGoal]:
    rows = [item for item in character_goals(state, character_id) if item.status == "active"]
    if scope:
        rows = [item for item in rows if item.scope == scope]
    return sorted(rows, key=lambda item: (-item.score(), item.id))


def select_goal(state: StoryState, character_id: str, *, scope: GoalScope | None = None
                ) -> CharacterGoal | None:
    """按当前条件动态选择目标：条件不满足、或优先级更低的目标不会中选。"""

    for goal in active_goals(state, character_id, scope=scope):
        if goal.when is not None and not evaluate(goal.when, state, actor=character_id).ok:
            continue
        return goal
    return None


def remember(state: StoryState, character_id: str, memory: CharacterMemory | dict) -> StoryState:
    """写入角色记忆；只有实际经历/被合法告知的事件才应该写进来。"""

    item = memory if isinstance(memory, CharacterMemory) else CharacterMemory.model_validate(memory)
    if item.holder != character_id:
        item = item.model_copy(update={"holder": character_id})
    _, data = _character_data(state, character_id)
    memories = [entry for entry in data.get("memories", []) if entry.get("id") != item.id]
    memories.append(item.model_dump(mode="json"))
    data["memories"] = memories
    return _write_character_data(state, character_id, data)


def character_memories(state: StoryState, character_id: str) -> list[CharacterMemory]:
    _, data = _character_data(state, character_id)
    return [CharacterMemory.model_validate(item) for item in data.get("memories", [])]


def store_arc(state: StoryState, arc: "CharacterArc") -> StoryState:
    _, data = _character_data(state, arc.character_id)
    data["arc"] = arc.model_dump(mode="json")
    return _write_character_data(state, arc.character_id, data)


def load_arc(state: StoryState, character_id: str):
    from .linkage import CharacterArc

    _, data = _character_data(state, character_id)
    return CharacterArc.model_validate(data["arc"]) if data.get("arc") else None


class RelationshipSnapshot(StrictModel):
    target_id: str
    dimensions: dict[str, float] = Field(default_factory=dict)
    tags: list[str] = Field(default_factory=list)


class CharacterDecisionContext(StrictModel):
    """角色做决定时“自己知道、自己在意”的全部输入。"""

    character_id: str
    goal: str = ""
    desire: str = ""
    fear: str = ""
    personality: list[str] = Field(default_factory=list)
    bottom_line: list[str] = Field(default_factory=list)
    relationships: list[RelationshipSnapshot] = Field(default_factory=list)
    knowledge: list[str] = Field(default_factory=list)
    goals: list[CharacterGoal] = Field(default_factory=list)
    memories: list[CharacterMemory] = Field(default_factory=list)
    current_pressure: str = ""
    data: dict[str, Any] = Field(default_factory=dict)

    def relationship(self, target_id: str) -> RelationshipSnapshot | None:
        return next((item for item in self.relationships if item.target_id == target_id), None)


class ReactionSuggestion(StrictModel):
    action_id: str
    score: float
    reason: str = ""
    source: str = "rule"


def build_decision_context(state: StoryState, character_id: str) -> CharacterDecisionContext:
    """从 StoryState 的实体数据组装上下文；没有数据时给出空上下文，不编造。"""

    entry = state.characters.get(character_id)
    data = dict(entry.data) if entry else {}
    relationships = [RelationshipSnapshot(target_id=item.target_id, dimensions=dict(item.dimensions),
                                          tags=list(item.tags))
                     for item in state.relationships if item.source_id == character_id]
    knowledge = [item.id for item in state.knowledge if character_id in item.holders]
    return CharacterDecisionContext(
        character_id=character_id,
        goal=str(data.get("goal", "")),
        desire=str(data.get("desire", "")),
        fear=str(data.get("fear", "")),
        personality=[str(item) for item in data.get("personality", [])],
        bottom_line=[str(item) for item in data.get("bottom_line", [])],
        relationships=relationships,
        knowledge=knowledge,
        goals=character_goals(state, character_id),
        memories=character_memories(state, character_id),
        current_pressure=str(data.get("current_pressure", "")),
        data=data,
    )


def _matches(text: str, keywords: list[str]) -> bool:
    return any(keyword and keyword in text for keyword in keywords)


def suggest_reactions(context: CharacterDecisionContext, actions: list[Action], state: StoryState,
                      *, target_id: str = "") -> list[ReactionSuggestion]:
    """按上下文给行动打分排序；性格只调整权重，不强制选择。"""

    relationship = context.relationship(target_id) if target_id else None
    suggestions: list[ReactionSuggestion] = []
    for action in actions:
        tags = [str(item) for item in action.data.get("tags", [])]
        score = 0.0
        reasons: list[str] = []
        if _matches(action.type, context.personality) or _matches(action.kind, context.personality):
            score += 1.0
            reasons.append("符合平时的做法")
        if context.goal and (context.goal in action.name or context.goal in action.type):
            score += 1.5
            reasons.append("接近当前目标")
        goal = select_goal(state, context.character_id)
        if goal is not None and (goal.title and goal.title in action.name
                                 or goal.title and goal.title in action.data.get("serves", "")):
            score += 0.5 * goal.score()
            reasons.append(f"服务目标：{goal.title}")
        for memory in context.memories:
            if memory.emotion and any(tag in (action.data.get("tags") or []) for tag in memory.emotion):
                score -= 0.5
                reasons.append(f"记忆影响：{memory.summary[:20]}")
        if context.desire and context.desire in action.data.get("serves", ""):
            score += 1.0
            reasons.append("满足自己的愿望")
        if context.fear and context.fear in action.data.get("risk", ""):
            score -= 1.5
            reasons.append("可能触及最担心的事")
        blocked = [line for line in context.bottom_line if line and line in action.data.get("violates", "")]
        if blocked:
            return_stub = ReactionSuggestion(action_id=action.id, score=-10.0,
                                             reason="触碰底线：" + "、".join(blocked))
            suggestions.append(return_stub)
            continue
        if relationship:
            trust = relationship.dimensions.get("trust", 0)
            if "companion" in tags or "partner" in tags:
                score += trust
                if trust:
                    reasons.append("顾及双方关系")
            hostility = relationship.dimensions.get("hostility", 0)
            if "oppose" in tags:
                score += hostility
        unmet = [item for item in action.requirements
                 if item.op in ("knowledge", "resource", "identity")
                 and not evaluate(item, state, actor=context.character_id).ok]
        if unmet:
            reason = evaluate(unmet[0], state, actor=context.character_id).message
            suggestions.append(ReactionSuggestion(action_id=action.id, score=-5.0,
                                                  reason="缺少依据：" + reason))
            continue
        suggestions.append(ReactionSuggestion(action_id=action.id, score=score,
                                              reason="；".join(reasons) or "没有明显偏好"))
    return sorted(suggestions, key=lambda item: (-item.score, item.action_id))


def sanitize_llm_proposals(proposals: list[dict], actions: list[Action], state: StoryState,
                           context: CharacterDecisionContext) -> list[ReactionSuggestion]:
    """LLM 只能提议候选行动与理由，不能创造行动、知识、资源或关系。"""

    allowed = {item.id for item in actions}
    accepted: list[ReactionSuggestion] = []
    for raw in proposals:
        action_id = str(raw.get("action_id", ""))
        if action_id not in allowed:
            continue
        if raw.get("grants_knowledge") or raw.get("grants_resource") or raw.get("grants_ability"):
            continue
        reason = str(raw.get("reason", ""))[:200]
        accepted.append(ReactionSuggestion(action_id=action_id, score=float(raw.get("score", 0.5)),
                                           reason=reason, source="llm_proposal"))
    return accepted


def merge_suggestions(rule_based: list[ReactionSuggestion],
                      proposals: list[ReactionSuggestion]) -> list[ReactionSuggestion]:
    """LLM 提议只能补充或微调规则结果，不能删除规则结论。"""

    by_id = {item.action_id: item for item in rule_based}
    order = [item.action_id for item in rule_based]
    for item in proposals:
        if item.action_id in by_id:
            current = by_id[item.action_id]
            by_id[item.action_id] = current.model_copy(
                update={"score": current.score + item.score, "reason": current.reason or item.reason})
        else:
            by_id[item.action_id] = item
            order.append(item.action_id)
    return sorted((by_id[key] for key in order), key=lambda item: (-item.score, item.action_id))
