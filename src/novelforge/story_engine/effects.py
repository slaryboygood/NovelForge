"""通用效果执行器（主计划 T07c）。

效果是数据：增减资源、改变关系、增删知识、设置 flag、改变地点、改变身份、
获得或失去能力、创建承诺、触发或结算事件。引擎只识别这些通用结构。

安全规则：
- 不允许负库存：扣减超过持有量直接失败，并回滚整个效果组。
- 防重复奖励：带 id 的效果只生效一次，写入 `effect_log` 后可查。
- 每一次变化都写入 `effect_log`，记录来源（行动 / 事件）。
- 作者配置不会自动变成库存或能力：资源与能力只能由效果写入。
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import Field, model_validator

from novelforge.models import StrictModel

from .entities import Ability, EventRecord, EffectRecord, KnowledgeEntry, PromiseState, ResourceStock
from .state import StoryState

EffectOp = Literal["add_resource", "remove_resource", "set_resource", "change_relationship",
                   "add_knowledge", "remove_knowledge", "set_flag", "remove_flag",
                   "increment_flag",
                   "advance_time",
                   "update_location",
                   "update_faction",
                   "update_plot",
                   "acquire_progression",
                   "update_foreshadow",
                   "change_location", "add_identity", "remove_identity", "grant_ability",
                   "revoke_ability", "create_promise", "resolve_promise", "trigger_event",
                   "resolve_event"]

# 伏笔生命周期允许的状态（与 foreshadow.ALLOWED_TRANSITIONS 的终点保持一致）。
ALLOWED_FORESHADOW_STATUSES = ("planned", "planted", "reinforced", "revealed", "resolved",
                               "abandoned")


class EffectError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(message)

    def as_dict(self) -> dict[str, str]:
        return {"code": self.code, "message": self.message}


class EffectSpec(StrictModel):
    """一条效果。id 可选；带 id 的效果只会生效一次。"""

    id: str = Field(default="", max_length=128)
    op: EffectOp
    entity: str = Field(default="", max_length=128)
    target: str = Field(default="", max_length=128)
    key: str = Field(default="", max_length=128)
    value: Any = None
    unit: str = Field(default="", max_length=32)
    source: str = Field(default="", max_length=128)
    data: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def valid_shape(self) -> "EffectSpec":
        if self.op in ("change_relationship",) and not self.key:
            raise ValueError("change_relationship requires key")
        if self.op in ("set_flag", "remove_flag", "change_location", "add_identity",
                       "remove_identity") and not self.key and self.value is None:
            raise ValueError(f"{self.op} requires key or value")
        if self.op in ("add_knowledge", "remove_knowledge", "grant_ability", "revoke_ability",
                       "trigger_event", "resolve_event") and not self.target and not self.key:
            raise ValueError(f"{self.op} requires target")
        if self.op in ("create_promise",) and not self.value:
            raise ValueError("create_promise requires value description")
        return self


class EffectOutcome(StrictModel):
    ok: bool
    code: str = ""
    message: str = ""
    state: StoryState
    records: list[EffectRecord] = Field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {"ok": self.ok, "code": self.code, "message": self.message,
                "records": [item.model_dump(mode="json") for item in self.records]}


def _effect_key(effect: EffectSpec, source: str) -> str:
    return "|".join((effect.id or f"{effect.op}:{effect.entity}:{effect.target or effect.key}",
                     source or effect.source))


def _relationship_dimensions(state: StoryState, source_id: str, target_id: str
                             ) -> tuple[int, dict[str, float], dict[str, Any]]:
    for index, item in enumerate(state.relationships):
        if item.source_id == source_id and item.target_id == target_id:
            return index, dict(item.dimensions), dict(item.data)
    return -1, {}, {}


def _apply_one(state: StoryState, effect: EffectSpec, *, actor: str, source: str) -> tuple[bool, str, str, str]:
    """在给定状态上原地执行一条效果；返回 (ok, code, message, target)。"""

    entity = effect.entity or actor
    op = effect.op
    value = effect.value
    if op in ("add_resource", "remove_resource", "set_resource"):
        resource_id = effect.target or effect.key
        stock = state.resources.get(resource_id)
        current = stock.amount if stock else 0.0
        unit = effect.unit or (stock.unit if stock else "")
        if op == "set_resource":
            amount = float(value if value is not None else 0)
        elif op == "add_resource":
            amount = current + float(value or 0)
        else:
            amount = current - float(value or 0)
        if amount < 0:
            return False, "RESOURCE_NEGATIVE", f"{resource_id} 数量不足：当前 {current}{unit}", resource_id
        holders = stock.holders if stock and stock.holders else ([entity] if entity else [])
        state.resources[resource_id] = ResourceStock(id=resource_id, amount=amount, unit=unit,
                                                     holders=holders,
                                                     source=source or effect.source,
                                                     data=dict(stock.data) if stock else {})
        return True, "", "", resource_id
    if op == "change_relationship":
        target = effect.target
        index, dimensions, entry_data = _relationship_dimensions(state, entity, target)
        dimensions[effect.key] = dimensions.get(effect.key, 0) + float(value or 0)
        from .entities import RelationshipState
        entry_data.update({key: item for key, item in (effect.data or {}).items() if key != "reason"})
        entry = RelationshipState(source_id=entity, target_id=target, dimensions=dimensions,
                                  data=entry_data)
        if index >= 0:
            state.relationships[index] = entry
        else:
            state.relationships.append(entry)
        return True, "", "", target
    if op == "add_knowledge":
        knowledge_id = effect.target or effect.key
        for item in state.knowledge:
            if item.id == knowledge_id:
                if entity and entity not in item.holders:
                    item.holders.append(entity)
                return True, "", "", knowledge_id
        state.knowledge.append(KnowledgeEntry(id=knowledge_id, holders=[entity] if entity else [],
                                              source=source or effect.source,
                                              reader_visible=bool(effect.data.get("reader_visible"))))
        return True, "", "", knowledge_id
    if op == "remove_knowledge":
        knowledge_id = effect.target or effect.key
        remaining = []
        for item in state.knowledge:
            if item.id == knowledge_id:
                holders = [holder for holder in item.holders if holder != entity]
                if holders:
                    remaining.append(item.model_copy(update={"holders": holders}))
                continue
            remaining.append(item)
        state.knowledge = remaining
        return True, "", "", knowledge_id
    if op in ("set_flag", "remove_flag"):
        flag = effect.key or effect.target
        if op == "set_flag":
            state.flags[flag] = True if value is None else value
        else:
            state.flags.pop(flag, None)
        return True, "", "", flag
    if op == "increment_flag":
        flag = effect.key or effect.target
        current = state.flags.get(flag, 0)
        if isinstance(current, bool) or not isinstance(current, (int, float)):
            current = 0
        state.flags[flag] = current + (float(value) if value is not None else 1)
        return True, "", "", flag
    if op == "advance_time":
        ticks = int(value or 0)
        if ticks < 0:
            return False, "TIME_BACKWARDS", "时间不能倒退", "timeline"
        state.timeline.tick += ticks
        label = str(effect.data.get("marker", "") or effect.key or "")
        if label:
            state.timeline.markers.append(label)
        if effect.data.get("current_time"):
            state.timeline.current_time = str(effect.data["current_time"])
        return True, "", "", "timeline"
    if op == "change_location":
        target = effect.value or effect.key
        state.location.current = str(target)
        if target not in state.location.visited:
            state.location.visited.append(str(target))
        return True, "", "", str(target)
    if op == "update_location":
        from .entities import Location

        location_id = effect.target or effect.key
        if not location_id:
            return False, "LOCATION_INVALID", "缺少地点编号", ""
        entry = state.location.known.get(location_id) or Location(id=location_id)
        updates = {key: value for key, value in (effect.data or {}).items() if key != "source"}
        data = dict(entry.data)
        data.update({key: value for key, value in updates.items()
                     if key not in ("name", "access")})
        entry = entry.model_copy(update={
            "name": str(updates.get("name", entry.name)),
            "access": str(updates.get("access", entry.access)),
            "data": data,
        })
        state.location.known[location_id] = entry
        return True, "", "", location_id
    if op == "update_faction":
        from .entities import Faction

        faction_id = effect.target or effect.key
        if not faction_id:
            return False, "FACTION_INVALID", "缺少势力编号", ""
        entry = state.factions.get(faction_id) or Faction(id=faction_id)
        updates = {key: value for key, value in (effect.data or {}).items() if key != "source"}
        data = dict(entry.data)
        data.update({key: value for key, value in updates.items()
                     if key not in ("name", "stance")})
        entry = entry.model_copy(update={
            "name": str(updates.get("name", entry.name)),
            "stance": str(updates.get("stance", entry.stance)),
            "data": data,
        })
        state.factions[faction_id] = entry
        return True, "", "", faction_id
    if op == "update_plot":
        from .linkage import PlotTrack, advance_plot, set_plot_status, upsert_plot

        plot_id = effect.target or effect.key
        if not plot_id:
            return False, "PLOT_INVALID", "缺少支线编号", ""
        data = dict(effect.data or {})
        existing = state.plots.get(plot_id)
        if existing is None:
            payload = {"id": plot_id, "source": effect.source or "effect"}
            payload.update({key: value for key, value in data.items()
                            if key not in ("steps", "status", "note", "source")})
            upsert_plot(state, PlotTrack.model_validate(payload), source=effect.source or "effect")
        steps = int(data.get("steps", 0) or 0)
        if steps:
            advance_plot(state, plot_id, steps=steps)
        else:
            # 没给 steps 也要刷新 updated_tick，便于观察支线是否被处理过。
            advance_plot(state, plot_id, steps=0)
        status = str(data.get("status", "") or "")
        if status:
            set_plot_status(state, plot_id, status, note=str(data.get("note", "") or ""))
        for key, value in data.items():
            if key in ("steps", "status", "note", "source"):
                continue
            if key in state.plots.get(plot_id, {}):
                state.plots[plot_id][key] = value
        return True, "", "", plot_id
    if op == "acquire_progression":
        from .progression import ProgressionTree, acquire, owned_nodes

        payload = (effect.data or {}).get("tree")
        if not payload:
            return False, "PROGRESSION_TREE_MISSING", "缺少成长树定义", ""
        try:
            tree = ProgressionTree.model_validate(payload)
        except Exception as exc:  # noqa: BLE001 - 树数据错误按失败处理
            return False, "PROGRESSION_TREE_INVALID", f"成长树数据不正确：{exc}", ""
        node_id = str(effect.target or effect.key or (effect.data or {}).get("node_id", ""))
        if not node_id:
            return False, "PROGRESSION_NODE_MISSING", "缺少成长节点编号", ""
        actor_id = effect.entity or actor
        if node_id in owned_nodes(state):
            return True, "", "", node_id
        outcome = acquire(tree, state, node_id, actor=actor_id)
        if not outcome.ok:
            return False, outcome.code or "PROGRESSION_LOCKED", outcome.message, node_id
        # acquire 返回的是新状态；把结果写回当前副本（与其它 effect 一致的原地语义）。
        state.flags = outcome.state.flags
        state.abilities = outcome.state.abilities
        state.identities = outcome.state.identities
        state.resources = outcome.state.resources
        state.knowledge = outcome.state.knowledge
        state.relationships = outcome.state.relationships
        state.promises = outcome.state.promises
        return True, "", "", node_id
    if op == "update_foreshadow":
        # 伏笔状态是运行时事实，存放在 StoryState.flags（单一事实来源），
        # 定义本身仍在内容包；这里只写“这个伏笔现在处于什么状态”。
        foreshadow_id = str(effect.target or effect.key or "")
        if not foreshadow_id:
            return False, "FORESHADOW_INVALID", "缺少伏笔编号", ""
        data = dict(effect.data or {})
        status = str(data.get("status", "") or "")
        if status and status not in ALLOWED_FORESHADOW_STATUSES:
            return False, "FORESHADOW_STATUS_INVALID", f"未知的伏笔状态：{status}", foreshadow_id
        registry = dict(state.flags.get("foreshadows", {}) or {})
        entry = dict(registry.get(foreshadow_id, {}) or {})
        tick = int(state.timeline.tick)
        if status:
            entry["status"] = status
            entry["tick"] = tick
            if status == "planted":
                entry.setdefault("planted_tick", tick)
            elif status in ("revealed", "resolved", "abandoned"):
                entry["closed_tick"] = tick
        planted_tick = int(entry.get("planted_tick", tick) or tick)
        entry["age"] = max(0, tick - planted_tick) if entry.get("planted_tick") is not None \
            else 0
        if data.get("reinforce"):
            entry["reinforce_count"] = int(entry.get("reinforce_count", 0) or 0) + 1
        if data.get("reason"):
            entry["reason"] = str(data["reason"])
        entry["source"] = str(data.get("source", "") or source or "")
        entry["tick"] = state.timeline.tick
        registry[foreshadow_id] = entry
        state.flags["foreshadows"] = registry
        return True, "", "", foreshadow_id
    if op in ("add_identity", "remove_identity"):
        identity = str(value or effect.key)
        owned = list(state.identities.get(entity, []))
        if op == "add_identity":
            if identity not in owned:
                owned.append(identity)
        else:
            owned = [item for item in owned if item != identity]
        if owned:
            state.identities[entity] = owned
        else:
            state.identities.pop(entity, None)
        return True, "", "", identity
    if op in ("grant_ability", "revoke_ability"):
        ability_id = effect.target or effect.key
        if op == "revoke_ability":
            state.abilities.pop(ability_id, None)
            return True, "", "", ability_id
        existing = state.abilities.get(ability_id)
        if existing is not None:
            return True, "", "", ability_id
        state.abilities[ability_id] = Ability(id=ability_id, kind=effect.data.get("kind", ""),
                                              name=effect.data.get("name", ""),
                                              limits=list(effect.data.get("limits", [])),
                                              data={"source": source or effect.source})
        return True, "", "", ability_id
    if op == "create_promise":
        promise_id = effect.id or effect.target or f"promise_{len(state.promises) + 1}"
        if all(item.id != promise_id for item in state.promises):
            state.promises.append(PromiseState(id=promise_id, debtor=entity,
                                               creditor=effect.target if effect.target != promise_id else "",
                                               description=str(value), source=source or effect.source,
                                               data=dict(effect.data)))
        return True, "", "", promise_id
    if op == "resolve_promise":
        promise_id = effect.target or effect.key
        status = effect.data.get("status", "settled")
        state.promises = [item.model_copy(update={"status": status}) if item.id == promise_id else item
                          for item in state.promises]
        return True, "", "", promise_id
    if op == "trigger_event":
        event_id = effect.target or effect.key
        if all(item.id != event_id for item in state.active_events + state.resolved_events):
            state.active_events.append(EventRecord(id=event_id, status="active",
                                                   source=source or effect.source,
                                                   participants=[entity] if entity else []))
        return True, "", "", event_id
    if op == "resolve_event":
        event_id = effect.target or effect.key
        state.active_events = [item for item in state.active_events if item.id != event_id]
        if all(item.id != event_id for item in state.resolved_events):
            state.resolved_events.append(EventRecord(id=event_id, status="resolved",
                                                     source=source or effect.source,
                                                     participants=[entity] if entity else []))
        return True, "", "", event_id
    return False, "EFFECT_UNKNOWN", f"未知效果类型 {op}", ""


def apply_effects(state: StoryState, effects: list[EffectSpec], *, actor: str = "",
                  source: str = "") -> EffectOutcome:
    """在一份副本上执行效果组；任何一条失败就整体回滚。"""

    working = state.model_copy(deep=True)
    records: list[EffectRecord] = []
    applied = {item.id for item in working.effect_log}
    order = len(working.effect_log)
    for effect in effects:
        key = _effect_key(effect, source)
        if effect.id and key in applied:
            continue
        ok, code, message, target = _apply_one(working, effect, actor=actor, source=source)
        if not ok:
            return EffectOutcome(ok=False, code=code, message=message, state=state, records=[])
        order += 1
        record = EffectRecord(id=key, op=effect.op, entity=effect.entity or actor, target=target,
                              value=effect.value, source=source or effect.source, order=order,
                              data={**(effect.data or {}), "key": effect.key,
                                    "tick": working.timeline.tick})
        working.effect_log.append(record)
        records.append(record)
        applied.add(key)
    return EffectOutcome(ok=True, state=working, records=records)
