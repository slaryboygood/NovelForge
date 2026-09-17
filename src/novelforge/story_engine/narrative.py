"""StoryState → 路线 → 大纲（V2-H）。

只有已实际发生的记录（happened）可以成为历史事实；作者计划（planned）与导演建议（suggested）
单独存放，不混入事实。长线拆分复用既有四级大纲的字段结构，不复制第二套 outline 模型。
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import Field

from novelforge.models import StrictModel

from .linkage import FuturePlan, PlotTrack, assert_history_immutable, plot_tracks, replan_with_plots
from .state import StoryState

RecordKind = Literal["happened", "planned", "suggested"]
Origin = Literal["action", "event", "world_event", "effect", "plot"]


class RouteRecord(StrictModel):
    id: str
    kind: RecordKind = "happened"
    origin: Origin = "action"
    source: str = ""
    tick: int = 0
    participants: list[str] = Field(default_factory=list)
    location: str = ""
    result: str = ""
    data: dict[str, Any] = Field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json")


class RoutePackage(StrictModel):
    happened: list[RouteRecord] = Field(default_factory=list)
    planned: list[RouteRecord] = Field(default_factory=list)
    suggested: list[RouteRecord] = Field(default_factory=list)

    def by_kind(self, kind: RecordKind) -> list[RouteRecord]:
        return list(getattr(self, kind))


def build_route(state: StoryState, *, plan: FuturePlan | None = None,
                suggested_events: list[str] | None = None) -> RoutePackage:
    """H-01：路线只能来自已发生事实；计划与建议单独列出。"""

    happened: list[RouteRecord] = []
    for record in state.effect_log:
        origin: Origin | None = None
        if record.op == "choice":
            origin = "action"
        elif record.op == "runtime_action":
            # V2 运行态里主角的每一次选择；它和 V1 的 choice 一样是已发生事实。
            origin = "action"
        elif record.op == "world_action":
            origin = "world_event"
        elif record.op in ("fire_event", "world_event"):
            origin = "event"
        if origin is None:
            continue
        data = record.data or {}
        happened.append(RouteRecord(id=f"route_{record.order:04d}", kind="happened", origin=origin,
                                    source=record.source or record.op, tick=int(data.get("tick", 0) or 0),
                                    participants=[record.entity] if record.entity else [],
                                    location=str(data.get("location", "")),
                                    result=str(data.get("result", "") or record.target),
                                    data={"target": record.target, "op": record.op}))
    for track in plot_tracks(state):
        if track.status in ("completed", "failed") and track.progress:
            happened.append(RouteRecord(id=f"plot_{track.id}", kind="happened", origin="plot",
                                        source=track.source or "plot", tick=track.updated_tick,
                                        participants=list(track.characters), location="",
                                        result=f"{track.title}:{track.status}",
                                        data={"plot_id": track.id, "progress": track.progress}))
    planned = [RouteRecord(id=f"planned_{stage.id}", kind="planned", origin="effect",
                           source="future_plan", result=stage.goal,
                           data={"stage": stage.id, "status": stage.status})
               for stage in (plan.stages if plan else [])]
    suggested = [RouteRecord(id=f"suggested_{event_id}", kind="suggested", origin="event",
                             source="director", result=event_id)
                 for event_id in (suggested_events or [])]
    return RoutePackage(happened=happened, planned=planned, suggested=suggested)


def outline_items_from_route(package: RoutePackage) -> list[dict[str, Any]]:
    """把 happened 记录映射为既有四级大纲的条目字段（不新增 outline 模型）。"""

    items = []
    for index, record in enumerate(package.happened, 1):
        items.append({
            "item_id": f"route_item_{index:03d}",
            "title": record.result[:40] or record.id,
            "summary": record.result,
            "start_state": record.source,
            "end_state": record.result,
            "goals": [record.result] if record.result else [],
            "conflicts": [],
            "major_turns": [record.result] if record.result else [],
            "must_keep": [f"来源：{record.origin}；tick={record.tick}；{record.source}"],
            "must_avoid": ["不得混入 planned / suggested 记录"],
            "child_ids": [],
            "pov": "", "time": "", "location": record.location, "participants": record.participants,
            "information_changes": [], "costs": [], "ending_hook": "",
        })
    return items


class LongLinePlan(StrictModel):
    """长线拆分：卷 / 篇章 / 章节，全部可追溯到 happened 记录。"""

    volumes: list[dict[str, Any]] = Field(default_factory=list)
    arcs: list[dict[str, Any]] = Field(default_factory=list)
    chapters: list[dict[str, Any]] = Field(default_factory=list)
    unresolved: list[str] = Field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json")


def split_long_line(package: RoutePackage, *, chapters_per_arc: int = 4,
                    arcs_per_volume: int = 2) -> LongLinePlan:
    """把已发生路线拆成卷 / 篇章 / 章节；不伪造尚未发生的事实。"""

    records = package.happened
    chapters: list[dict[str, Any]] = []
    for index, record in enumerate(records, 1):
        chapters.append({"id": f"ch_{index:03d}", "title": record.result[:30] or record.id,
                         "source": record.id, "origin": record.origin, "tick": record.tick})
    arcs: list[dict[str, Any]] = []
    for index in range(0, len(chapters), max(1, chapters_per_arc)):
        group = chapters[index:index + chapters_per_arc]
        arcs.append({"id": f"arc_{len(arcs) + 1:02d}", "chapters": [item["id"] for item in group],
                     "sources": [item["source"] for item in group]})
    volumes: list[dict[str, Any]] = []
    for index in range(0, len(arcs), max(1, arcs_per_volume)):
        group = arcs[index:index + arcs_per_volume]
        volumes.append({"id": f"vol_{len(volumes) + 1:02d}", "arcs": [item["id"] for item in group],
                        "sources": [source for item in group for source in item["sources"]]})
    unresolved = [item.id for item in package.planned] + [item.id for item in package.suggested]
    return LongLinePlan(volumes=volumes, arcs=arcs, chapters=chapters, unresolved=unresolved)


class TraceResult(StrictModel):
    verified: list[str] = Field(default_factory=list)
    unsourced: list[dict[str, str]] = Field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json")


def verify_outline_sources(items: list[dict[str, Any]], package: RoutePackage) -> TraceResult:
    """H-05：大纲里的“已发生事实”必须能在路线 / StoryState 找到来源。"""

    known = {record.id for record in package.happened} | {record.source for record in package.happened}
    verified: list[str] = []
    unsourced: list[dict[str, str]] = []
    for item in items:
        item_id = str(item.get("item_id", ""))
        notes = " ".join(str(value) for value in item.get("must_keep", []))
        # 结构化来源优先（source_ids 是机器字段）；旧包没有该字段时回落到 must_keep 文本，
        # 保证 legacy 大纲仍然可以验证。
        refs = [str(value) for value in item.get("source_ids", [])]
        if any(ref in known for ref in refs) or any(key in notes for key in known) \
                or item_id in known:
            verified.append(item_id)
        else:
            unsourced.append({"item_id": item_id, "mark": "unresolved",
                              "reason": "找不到已发生来源，不能当作事实"})
    return TraceResult(verified=verified, unsourced=unsourced)


def replan_long_line(plan: FuturePlan, state: StoryState, package: RoutePackage, *,
                     changed_stage: str = "", note: str = "") -> tuple[FuturePlan, RoutePackage]:
    """H-04：只重规划未来；已发生路线保持不变。"""

    assert_history_immutable(state, state)
    updated_plan = replan_with_plots(plan, state, changed_stage=changed_stage, note=note)
    replanned = build_route(state, plan=updated_plan,
                            suggested_events=[item.result for item in package.suggested])
    if replanned.happened != package.happened:
        raise ValueError("HISTORY_IMMUTABLE：重规划不得修改已发生路线")
    return updated_plan, replanned
