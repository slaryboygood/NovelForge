"""大纲与动态剧情联动（主计划 T14）。

- T14a：已发生事实只来自实际路线（choice / effect 记录），未来规划不能覆盖。
- T14b：主线阶段是“目标”，不是强制结果；玩家选择改变后可以重新规划未来，历史不可逆。
- T14c：人物弧定义目标阶段，实际经历可以推进、延迟、反转或失败，不强迫机械发展。
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import Field, model_validator

from novelforge.models import StrictModel

from .conditions import Condition, evaluate
from .state import StoryState

ArcOutcome = Literal["advance", "delay", "reverse", "fail"]
PlotStatus = Literal["inactive", "active", "paused", "completed", "failed", "abandoned"]


class RouteFact(StrictModel):
    order: int
    action_id: str
    result: str = ""
    source: str = ""


def route_facts(state: StoryState) -> list[RouteFact]:
    """T14a：只把真实发生过的选择与结果作为事实。"""

    facts: list[RouteFact] = []
    for record in state.effect_log:
        if record.op != "choice":
            continue
        facts.append(RouteFact(order=record.order, action_id=record.target,
                               result=str((record.data or {}).get("result", "")),
                               source=record.source))
    return facts


class StageGoal(StrictModel):
    id: str = Field(min_length=1, max_length=64)
    title: str = Field(default="", max_length=120)
    goal: str = Field(default="", max_length=300)
    status: Literal["planned", "active", "done", "changed"] = "planned"
    is_goal: bool = True
    note: str = Field(default="", max_length=300)


class FuturePlan(StrictModel):
    """未来规划：只描述目标，不写入已发生事实。"""

    plan_id: str = Field(default="plan", max_length=64)
    stages: list[StageGoal] = Field(default_factory=list)
    revision: int = Field(default=0, ge=0)

    @model_validator(mode="after")
    def stages_are_goals(self) -> "FuturePlan":
        if any(not item.is_goal for item in self.stages):
            raise ValueError("future plan stages must be goals, not facts")
        return self


class HistoryImmutableError(ValueError):
    def __init__(self, message: str) -> None:
        self.code = "HISTORY_IMMUTABLE"
        self.message = message
        super().__init__(message)


class PlotTrack(StrictModel):
    """支线轨道：只描述当前状态与目标，不强制后续一定发生什么。"""

    id: str = Field(min_length=1, max_length=64)
    title: str = Field(default="", max_length=120)
    status: PlotStatus = "inactive"
    progress: int = Field(default=0, ge=0, le=999)
    priority: float = Field(default=1.0, ge=0, le=100)
    trigger: Condition | None = None
    source: str = Field(default="", max_length=128)
    updated_tick: int = Field(default=0, ge=0)
    characters: list[str] = Field(default_factory=list)
    factions: list[str] = Field(default_factory=list)
    locations: list[str] = Field(default_factory=list)
    foreshadows: list[str] = Field(default_factory=list)
    data: dict[str, Any] = Field(default_factory=dict)


def plot_tracks(state: StoryState) -> list[PlotTrack]:
    return [PlotTrack.model_validate(item) for item in state.plots.values()]


def _store_tracks(state: StoryState, tracks: list[PlotTrack]) -> StoryState:
    """写入支线轨道。

    采用原地写入：调用方通常在 `apply_effects` / Driver 的副本上工作，
    并且历史代码都是 `state = set_plot_status(state, ...)` 的写法——
    原地写入让两种写法都成立，不会出现“返回了新状态、传入状态没变”的静默丢失。
    """

    state.plots = {item.id: item.model_dump(mode="json") for item in tracks}
    return state


def upsert_plot(state: StoryState, track: PlotTrack | dict, *, source: str = "event") -> StoryState:
    candidate = track if isinstance(track, PlotTrack) else PlotTrack.model_validate(track)
    candidate = candidate.model_copy(update={"source": source or candidate.source,
                                             "updated_tick": state.timeline.tick})
    tracks = [item for item in plot_tracks(state) if item.id != candidate.id]
    tracks.append(candidate)
    return _store_tracks(state, tracks)


def advance_plot(state: StoryState, plot_id: str, *, steps: int = 1) -> StoryState:
    """只推进指定支线，不影响其他支线。"""

    tracks = []
    for item in plot_tracks(state):
        if item.id == plot_id:
            item = item.model_copy(update={"progress": item.progress + steps,
                                           "status": "completed" if item.status == "active"
                                           and item.progress + steps >= 3 else item.status,
                                           "updated_tick": state.timeline.tick})
        tracks.append(item)
    return _store_tracks(state, tracks)


def set_plot_status(state: StoryState, plot_id: str, status: PlotStatus, *, note: str = "") -> StoryState:
    tracks = []
    for item in plot_tracks(state):
        if item.id == plot_id:
            data = dict(item.data)
            if note:
                data["note"] = note
            item = item.model_copy(update={"status": status, "data": data,
                                           "updated_tick": state.timeline.tick})
        tracks.append(item)
    return _store_tracks(state, tracks)


def sync_plots(state: StoryState) -> StoryState:
    """世界变化驱动的自动激活：触发条件满足的 inactive 支线转为 active。"""

    tracks = []
    for item in plot_tracks(state):
        if item.status == "inactive" and item.trigger is not None \
                and evaluate(item.trigger, state, actor="").ok:
            item = item.model_copy(update={"status": "active", "updated_tick": state.timeline.tick})
        tracks.append(item)
    return _store_tracks(state, tracks)


def schedule_plots(state: StoryState, *, max_active: int = 3) -> tuple[StoryState, list[str]]:
    """防止支线无限堆积：超出上限时，从优先级最低的 active 支线开始暂停。"""

    tracks = sorted(plot_tracks(state), key=lambda item: (-item.priority, item.id))
    active = [item for item in tracks if item.status == "active"]
    demoted: list[str] = []
    if len(active) > max_active:
        for item in active[max_active:]:
            item = item.model_copy(update={"status": "paused"})
            demoted.append(item.id)
        tracks = [item if item.id not in demoted else
                  item.model_copy(update={"status": "paused"}) for item in tracks]
    return _store_tracks(state, tracks), demoted


def replan_with_plots(plan: FuturePlan, state: StoryState, *, changed_stage: str = "",
                      note: str = "") -> FuturePlan:
    """C-05：世界事件与支线可以影响未来主线；已发生历史不受影响。"""

    before = state
    updated = advance_stages(replan(plan, state, changed_stage=changed_stage, note=note), state)
    affected = [item.id for item in plot_tracks(state) if item.status == "active"
                and item.priority >= 1.0]
    stages = []
    for stage in updated.stages:
        extra = stage.note
        if affected and stage.status == "active" and not extra:
            extra = "受支线影响：" + "、".join(affected[:3])
        stages.append(stage.model_copy(update={"note": extra}))
    result = updated.model_copy(update={"stages": stages})
    assert_history_immutable(before, state)
    return result


def advance_stages(plan: FuturePlan, state: StoryState) -> FuturePlan:
    """W5-01：按已发生进度自动推进阶段状态。

    规则（只读事实，不改历史）：

    - 支线 completed 且标题出现在阶段目标 / 标题里 → 该阶段 `done`；
    - 没有任何阶段处于 active 时，把第一个 planned 阶段标记为 `active`；
    - 不把已经 active 的阶段降回 planned（重规划激活的阶段保持生效）；
    - `changed` 状态保留（作者显式改过的阶段不被覆盖）。
    """

    completed_titles = [item.title for item in plot_tracks(state) if item.status == "completed"
                        and item.title]
    stages: list[StageGoal] = []
    for stage in plan.stages:
        status = stage.status
        text = f"{stage.title} {stage.goal}"
        if status != "changed" and any(title in text for title in completed_titles):
            status = "done"
        stages.append(stage.model_copy(update={"status": status}))
    if stages and not any(row.status in ("active", "done", "changed") for row in stages):
        stages[0] = stages[0].model_copy(update={"status": "active"})
    elif stages and not any(row.status == "active" for row in stages):
        # 没有进行中的阶段时，把紧随其后的第一个 planned 阶段推进上来。
        for index, row in enumerate(stages):
            if row.status == "planned":
                stages[index] = row.model_copy(update={"status": "active"})
                break
    return plan.model_copy(update={"stages": stages})


def assert_history_immutable(before: StoryState, after: StoryState) -> None:
    """T14a：已发生事实不能被后续规划改写。"""

    old = [(item.order, item.action_id, item.result) for item in route_facts(before)]
    new = [(item.order, item.action_id, item.result) for item in route_facts(after)]
    if new[:len(old)] != old:
        raise HistoryImmutableError("已发生的路线事实被改写")


def replan(plan: FuturePlan, state: StoryState, *, changed_stage: str = "",
           note: str = "") -> FuturePlan:
    """T14b：玩家选择改变后重新规划未来；不触碰历史。"""

    stages = []
    for stage in plan.stages:
        if stage.id == changed_stage:
            stages.append(stage.model_copy(update={"status": "changed", "note": note or stage.note}))
        elif stage.status == "planned":
            stages.append(stage.model_copy(update={"status": "active"}))
        else:
            stages.append(stage)
    return plan.model_copy(update={"stages": stages, "revision": plan.revision + 1})


class ArcStage(StrictModel):
    id: str = Field(min_length=1, max_length=64)
    title: str = Field(default="", max_length=120)
    description: str = Field(default="", max_length=300)


class CharacterArc(StrictModel):
    character_id: str = Field(min_length=1, max_length=128)
    stages: list[ArcStage] = Field(default_factory=list)
    current_index: int = Field(default=0, ge=0)
    outcome: ArcOutcome = "advance"
    note: str = Field(default="", max_length=300)

    def current(self) -> ArcStage | None:
        return self.stages[self.current_index] if self.stages else None


def apply_arc_outcome(arc: CharacterArc, outcome: ArcOutcome, *, note: str = "") -> CharacterArc:
    """T14c：推进/延迟/反转/失败都只是目标状态，不强迫角色按剧本成长。"""

    index = arc.current_index
    if outcome == "advance":
        index = min(len(arc.stages) - 1, index + 1) if arc.stages else 0
    elif outcome == "reverse":
        index = max(0, index - 1)
    # delay / fail 保持阶段不变，只记录说明。
    return arc.model_copy(update={"current_index": index, "outcome": outcome,
                                  "note": note or arc.note})


def arc_summary(arc: CharacterArc) -> dict[str, Any]:
    current = arc.current()
    return {"character_id": arc.character_id, "stage": current.title if current else "",
            "stage_id": current.id if current else "", "outcome": arc.outcome,
            "is_forced": False, "note": arc.note}
