"""剧情导演系统（主计划 T10）。

- T10a 候选事件池：只把 StoryState 判定合法的事件交给后续环节。
- T10b 事件评分：主线推进、人物弧、关系变化、未回收伏笔、危险度、节奏、
  最近事件重复度、玩家最近选择，权重可配置。
- T10c 节奏约束：铺垫 / 升压 / 转折 / 爆发 / 回落，避免连续同类型事件。
- T10d LLM Writer 边界：引擎先确定事实，再交给 LLM 表现；输出要过事实一致性检查。
"""

from __future__ import annotations

from typing import Any

from pydantic import Field

from novelforge.models import StrictModel

from .events import EventAvailability, EventCard, EventCardCatalog, EventTriggerEngine
from .state import StoryState

PACING_LABELS = ("setup", "rise", "turn", "climax", "fall")


class DirectorWeights(StrictModel):
    main_line: float = 1.0
    subplot: float = 1.0
    character_arc: float = 1.0
    character_goal: float = 0.8
    relationship: float = 0.8
    foreshadow: float = 1.2
    conflict: float = 1.0
    payoff: float = 1.0
    crisis: float = 0.8
    danger: float = 0.6
    pacing: float = 0.8
    repetition: float = 1.5
    balance: float = 1.0
    world: float = 0.8
    player_choice: float = 1.0
    # 同一事件在最近窗口内反复出现时的额外扣分权重（0 表示关闭）。
    event_repetition: float = 2.0
    event_repetition_window: float = 4.0

    def as_config(self) -> dict[str, float]:
        """权重配置快照：只有数据，不含任何评分算法。"""

        return {name: float(getattr(self, name)) for name in
                ("main_line", "subplot", "character_arc", "character_goal", "relationship",
                 "foreshadow", "conflict", "payoff", "crisis", "danger", "pacing",
                 "repetition", "balance", "world", "player_choice",
                 "event_repetition", "event_repetition_window")}


class EventScore(StrictModel):
    event_id: str
    score: float
    dimensions: dict[str, float] = Field(default_factory=dict)
    reasons: list[str] = Field(default_factory=list)
    deductions: list[str] = Field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json")


def candidate_events(catalog: EventCardCatalog, state: StoryState, *, actor: str = "") -> list[EventAvailability]:
    """T10a：只返回合法事件；不合法事件不进入候选池。"""

    return EventTriggerEngine(catalog).available(state, actor=actor)


def _recent_types(state: StoryState, key: str = "event_type") -> list[str]:
    return [str((record.data or {}).get(key, "")) for record in state.effect_log
            if record.op == "fire_event" and (record.data or {}).get(key)]


def _recent_event_ids(state: StoryState) -> list[str]:
    """最近触发的事件 id（按顺序），用于同一事件的频率扣分。"""

    return [str(record.target) for record in state.effect_log
            if record.op in ("fire_event", "world_event") and record.target]


def score_events(catalog: EventCardCatalog, state: StoryState, *, weights: DirectorWeights | None = None,
                 actor: str = "", last_choice: str = "") -> list[EventScore]:
    """V2-D-01：对合法事件按多维度评分，每一维独立计算并可解释。"""

    config = weights or DirectorWeights()
    recent = _recent_types(state)
    recent_ids = _recent_event_ids(state)
    plots = {item.id: item for item in _plot_tracks(state)}
    active_plots = [item for item in plots.values() if item.status == "active"]
    # 只补偿「最饥饿」的支线，避免所有支线都拿到平衡加成（防止机械轮询）。
    starved_plots = sorted(active_plots, key=lambda item: (item.progress, -item.priority))[:1]
    goal_titles = _goal_titles(state, actor)
    scores: list[EventScore] = []
    for availability in candidate_events(catalog, state, actor=actor):
        try:
            card = catalog.by_id(availability.event_id)
        except KeyError:
            continue
        data = card.data or {}
        dims: dict[str, float] = {}
        reasons: list[str] = []
        deductions: list[str] = []
        dims["base"] = float(card.priority)
        if data.get("main_line"):
            dims["main_line"] = config.main_line
            reasons.append("推进主线")
        plot_id = str(data.get("subplot", ""))
        if plot_id and plot_id in plots:
            bonus = config.subplot
            if any(plot_id == item.id for item in starved_plots):
                bonus += config.balance
                reasons.append(f"支线长期未推进：{plots[plot_id].title or plot_id}")
            dims["subplot"] = bonus
            reasons.append(f"调度支线：{plots[plot_id].title or plot_id}")
        if data.get("character_arc"):
            dims["character_arc"] = config.character_arc
            reasons.append("推动人物弧")
        if goal_titles and any(title and (title in card.title or title in str(data.get("serves", "")))
                               for title in goal_titles):
            dims["character_goal"] = config.character_goal
            reasons.append("符合角色当前目标")
        if data.get("relationship"):
            dims["relationship"] = config.relationship
            reasons.append("改变关系")
        if data.get("foreshadow"):
            dims["foreshadow"] = config.foreshadow * float(data.get("foreshadow_weight", 1))
            reasons.append("涉及未回收伏笔")
        if data.get("conflict"):
            dims["conflict"] = config.conflict
            reasons.append("回应未解决冲突")
        if data.get("payoff"):
            dims["payoff"] = config.payoff * float(data.get("payoff", 1))
            reasons.append("提供一次有效回报")
        if data.get("crisis"):
            dims["crisis"] = config.crisis * float(data.get("crisis", 1))
            reasons.append("提高当前矛盾与代价")
        if data.get("world_event"):
            dims["world"] = config.world
            reasons.append("受世界变化影响")
        dims["danger"] = config.danger * float(data.get("danger", 0))
        if data.get("pacing") in PACING_LABELS:
            dims["pacing"] = config.pacing * _pacing_bonus(str(data["pacing"]), recent)
            reasons.append(f"节奏：{data['pacing']}")
        kind = str(data.get("event_type", card.kind))
        if kind and recent and recent[-1] == kind:
            dims["repetition"] = -config.repetition
            deductions.append("与最近事件类型重复")
        window = max(0, int(config.event_repetition_window))
        if config.event_repetition > 0 and window:
            occurrences = recent_ids[-window:].count(card.event_id)
            if occurrences:
                dims["event_repetition"] = -config.event_repetition * occurrences
                deductions.append(f"同一事件在最近 {window} 次里已出现 {occurrences} 次")
        if last_choice and last_choice in (data.get("follows_choices") or []):
            dims["player_choice"] = config.player_choice
            reasons.append("承接玩家最近的选择")
        total = sum(dims.values())
        scores.append(EventScore(event_id=card.event_id, score=total, dimensions=dims,
                                 reasons=reasons, deductions=deductions))
    return sorted(scores, key=lambda item: (-item.score, item.event_id))


def _plot_tracks(state: StoryState):
    from .linkage import plot_tracks

    return plot_tracks(state)


def _goal_titles(state: StoryState, actor: str) -> list[str]:
    if not actor or actor not in state.characters:
        return []
    from .characters import active_goals

    return [item.title for item in active_goals(state, actor) if item.title]


class DirectorDecision(StrictModel):
    """V2-D-05：可解释的导演结果。"""

    chosen: str = ""
    ranked: list[EventScore] = Field(default_factory=list)
    why_chosen: list[str] = Field(default_factory=list)
    why_not: dict[str, list[str]] = Field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {"chosen": self.chosen,
                "ranked": [item.model_dump(mode="json") for item in self.ranked],
                "why_chosen": list(self.why_chosen), "why_not": dict(self.why_not)}


def decide(catalog: EventCardCatalog, state: StoryState, *, weights: DirectorWeights | None = None,
           actor: str = "", last_choice: str = "", limit: int = 3) -> DirectorDecision:
    """选出当前最值得发生的事件，并解释为什么选它、为什么暂不选其他高分事件。"""

    ranked = score_events(catalog, state, weights=weights, actor=actor, last_choice=last_choice)
    if not ranked:
        return DirectorDecision()
    top = ranked[0]
    why_not: dict[str, list[str]] = {}
    for item in ranked[1:limit]:
        gaps = [f"{top.event_id} 更高：{key}" for key, value in item.dimensions.items()
                if top.dimensions.get(key, 0) > value]
        why_not[item.event_id] = (["总分较低"] + item.deductions + gaps)[:4]
    return DirectorDecision(chosen=top.event_id, ranked=ranked[:limit],
                            why_chosen=top.reasons + top.deductions, why_not=why_not)


def weights_from_config(payload: dict[str, Any] | None) -> DirectorWeights:
    """V2-D-02：权重来自配置 / Novel Profile / Content Pack，不写死小说偏好。"""

    return DirectorWeights.model_validate(payload or {})


def _pacing_bonus(pacing: str, recent: list[str]) -> float:
    if not recent:
        return 1.0 if pacing in ("setup", "rise") else 0.0
    previous = recent[-1]
    preferred = {"setup": ("setup", "rise"), "rise": ("rise", "turn"),
                 "turn": ("climax", "rise"), "climax": ("fall", "turn"),
                 "fall": ("setup", "rise")}
    if pacing in preferred.get(previous, ()):
        return 1.0
    if pacing == previous:
        return -1.0
    return 0.0


class WriterBrief(StrictModel):
    """交给 LLM 的事实清单：只允许表现，不允许改写。"""

    event_id: str
    scene_goal: str = ""
    conflict: str = ""
    must_keep: list[str] = Field(default_factory=list)
    must_not: list[str] = Field(default_factory=list)
    state_digest: dict[str, Any] = Field(default_factory=dict)


def writer_brief(card: EventCard, state: StoryState, *, actor: str = "") -> WriterBrief:
    must_keep = [f"参与者：{item}" for item in card.participants]
    must_keep.append(f"资源：{ {key: value.amount for key, value in state.resources.items()} }")
    must_keep.append(f"位置：{state.location.current or '未指明'}")
    must_not = ["不得让角色知道未获得的知识", "不得凭空增加资源或能力",
                "不得改写已经发生的事件", "不得替引擎决定事实"]
    return WriterBrief(event_id=card.event_id, scene_goal=card.scene_goal, conflict=card.conflict,
                       must_keep=must_keep, must_not=must_not,
                       state_digest={"knowledge": [item.id for item in state.knowledge],
                                     "active_events": [item.id for item in state.active_events]})


def check_writer_output(text: str, brief: WriterBrief) -> list[str]:
    """T10d：输出与事实清单的一致性检查，返回问题列表。"""

    problems: list[str] = []
    for forbidden in ("凭空获得", "突然拥有", "所有人都知道"):
        if forbidden in text:
            problems.append(f"可能改写事实：{forbidden}")
    if not text.strip():
        problems.append("输出为空")
    return problems
