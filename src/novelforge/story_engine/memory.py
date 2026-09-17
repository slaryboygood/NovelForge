"""长期记忆与三视角知识（V2-E）。

查询层，不复制数据：
- author  ：StoryState.author_knowledge（作者设定、真相、未来安排、隐藏事实）
- reader  ：StoryState.knowledge 中 reader_visible=True 的条目
- character：StoryState.knowledge 中 holders 含该角色的条目

事实 / 传言 / 推测 / 计划由 KnowledgeEntry.certainty 区分，不建立第二套知识系统。
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import Field

from novelforge.models import StrictModel

from .entities import KnowledgeEntry, PromiseState
from .foreshadow import Foreshadow
from .state import StoryState

Certainty = Literal["fact", "rumor", "guess", "plan"]


class ConflictRow(StrictModel):
    """未解决冲突：从支线 / 承诺 / 关系推导，不新存一份。"""

    kind: str
    id: str
    title: str = ""
    participants: list[str] = Field(default_factory=list)
    pressure: float = 0.0
    status: str = ""
    source: str = ""
    tick: int = 0

    def as_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json")


def record_knowledge(state: StoryState, entry: KnowledgeEntry | dict, *, holders: list[str] | None = None,
                     reader_visible: bool | None = None, source: str = "",
                     source_event: str = "") -> StoryState:
    """唯一写入入口：保留 source / tick / holder / reader_visible / 来源事件。"""

    item = entry if isinstance(entry, KnowledgeEntry) else KnowledgeEntry.model_validate(entry)
    item = item.model_copy(update={
        "holders": list(holders if holders is not None else item.holders),
        "reader_visible": item.reader_visible if reader_visible is None else reader_visible,
        "source": source or item.source,
        "source_event": source_event or item.source_event,
        "tick": item.tick or state.timeline.tick,
    })
    working = state.model_copy(deep=True)
    layer = working.author_knowledge if item.certainty == "plan" else working.knowledge
    others = working.knowledge if item.certainty == "plan" else working.author_knowledge
    others[:] = [existing for existing in others if existing.id != item.id]
    layer[:] = [existing for existing in layer if existing.id != item.id]
    layer.append(item)
    return working


def knows(state: StoryState, knowledge_id: str, holder: str) -> bool:
    return any(item.id == knowledge_id and holder in item.holders for item in state.knowledge)


def holders_of(state: StoryState, knowledge_id: str) -> list[str]:
    for item in state.knowledge:
        if item.id == knowledge_id:
            return list(item.holders)
    return []


def author_knows(state: StoryState, knowledge_id: str) -> bool:
    return any(item.id == knowledge_id for item in state.author_knowledge + state.knowledge)


def reader_knows_fact(state: StoryState, knowledge_id: str) -> bool:
    """读者是否已经看到过这条信息（与 foreshadow.reader_knows 区分，后者针对悬念问题）。"""

    return any(item.id == knowledge_id and item.reader_visible for item in state.knowledge)


def author_only(state: StoryState) -> list[str]:
    """作者知道、读者还不知道。"""

    reader_ids = {item.id for item in state.knowledge if item.reader_visible}
    author_ids = {item.id for item in state.author_knowledge}
    author_ids |= {item.id for item in state.knowledge}
    return sorted(author_ids - reader_ids)


def reader_only_states(state: StoryState, holder: str) -> list[str]:
    """读者知道、但某个角色不知道。"""

    return sorted(item.id for item in state.knowledge
                  if item.reader_visible and holder not in item.holders)


def diff_characters(state: StoryState, a: str, b: str) -> dict[str, list[str]]:
    a_ids = {item.id for item in state.knowledge if a in item.holders}
    b_ids = {item.id for item in state.knowledge if b in item.holders}
    return {"a_only": sorted(a_ids - b_ids), "b_only": sorted(b_ids - a_ids),
            "shared": sorted(a_ids & b_ids)}


def by_certainty(state: StoryState, certainty: Certainty) -> list[KnowledgeEntry]:
    source = state.author_knowledge if certainty == "plan" else state.knowledge
    return [item for item in source if item.certainty == certainty]


def facts(state: StoryState) -> list[KnowledgeEntry]:
    return by_certainty(state, "fact")


def assert_facts_immutable(before: StoryState, after: StoryState) -> None:
    old = [(item.id, item.tick, item.source) for item in facts(before)]
    new = [(item.id, item.tick, item.source) for item in facts(after)]
    if new[:len(old)] != old:
        raise ValueError("FACT_HISTORY_IMMUTABLE：已确认事实被改写")


# ---- E-03 承诺 / 债务 / 人情 -------------------------------------------------


def outstanding_promises(state: StoryState) -> list[PromiseState]:
    return sorted((item for item in state.promises if item.status == "open"),
                  key=lambda item: (item.due_tick or 10 ** 6, item.created_tick, item.id))


def overdue_promises(state: StoryState) -> list[PromiseState]:
    return [item for item in outstanding_promises(state)
            if item.due_tick and item.due_tick <= state.timeline.tick]


def settle_promise(state: StoryState, promise_id: str, status: str = "settled",
                   *, note: str = "") -> StoryState:
    working = state.model_copy(deep=True)
    working.promises = [item.model_copy(update={"status": status, "settled_tick": working.timeline.tick,
                                                "data": {**item.data, **({"note": note} if note else {})}})
                        if item.id == promise_id else item for item in working.promises]
    return working


# ---- E-04 仇恨来源 ----------------------------------------------------------


def hostility_sources(state: StoryState, source_id: str, target_id: str) -> list[dict[str, Any]]:
    """从 effect_log 追溯敌意来源：数值变化保留历史原因。"""

    rows = []
    for record in state.effect_log:
        if record.op != "change_relationship" or record.entity != source_id or record.target != target_id:
            continue
        delta = record.value if isinstance(record.value, (int, float)) else 0
        if delta >= 0:
            continue
        rows.append({"order": record.order, "delta": delta, "source": record.source,
                     "reason": (record.data or {}).get("reason", ""),
                     "tick": (record.data or {}).get("tick", 0)})
    return rows


# ---- E-05 未解决冲突 --------------------------------------------------------


def unresolved_conflicts(state: StoryState) -> list[ConflictRow]:
    rows: list[ConflictRow] = []
    for plot in state.plots.values():
        if plot.get("status") in ("active", "paused"):
            data = plot.get("data") or {}
            rows.append(ConflictRow(kind="plot", id=str(plot.get("id", "")), title=str(plot.get("title", "")),
                                    participants=list(data.get("participants", [])),
                                    pressure=float(data.get("pressure", 0)),
                                    status=str(plot.get("status", "")), source=str(plot.get("source", "")),
                                    tick=int(plot.get("updated_tick", 0))))
    for promise in outstanding_promises(state):
        rows.append(ConflictRow(kind="promise", id=promise.id, title=promise.description,
                                participants=[item for item in (promise.debtor, promise.creditor) if item],
                                pressure=1.0 if promise.due_tick and promise.due_tick <= state.timeline.tick else 0.5,
                                status=promise.status, source=promise.source,
                                tick=promise.created_tick))
    for item in state.relationships:
        hostility = item.dimensions.get("hostility", 0)
        if hostility > 0:
            rows.append(ConflictRow(kind="relationship", id=f"{item.source_id}->{item.target_id}",
                                    title="敌意", participants=[item.source_id, item.target_id],
                                    pressure=float(hostility), status="open",
                                    source="relationship", tick=0))
    return sorted(rows, key=lambda item: (-item.pressure, item.kind, item.id))


# ---- E-06 未回收伏笔 --------------------------------------------------------


def open_foreshadows(foreshadows: list[Foreshadow]) -> list[Foreshadow]:
    return [item for item in foreshadows if item.status not in ("resolved", "abandoned")]


def aged_foreshadows(foreshadows: list[Foreshadow], *, tick: int, min_age: int = 1) -> list[Foreshadow]:
    rows = []
    for item in open_foreshadows(foreshadows):
        planted = int(item.data.get("planted_tick", 0) or 0)
        if planted and tick - planted >= min_age:
            rows.append(item)
    return sorted(rows, key=lambda item: (int(item.data.get("planted_tick", 0) or 0), item.id))
