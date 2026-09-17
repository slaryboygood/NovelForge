"""延迟后果（主计划 T08c）。

“现在选择，未来生效”：行动把延迟后果写入 `StoryState.delayed_effects`，
包含来源行动、触发条件、效果与创建顺序；刷新或重新进入后不会丢失。

支持结算、取消、替换与提前触发；结算过程在副本上执行，失败不落盘。
"""

from __future__ import annotations

from typing import Any

from pydantic import Field

from novelforge.models import StrictModel

from .actions import DelayedEffectSpec
from .conditions import Condition, evaluate
from .effects import EffectSpec, apply_effects
from .entities import EffectRecord
from .state import StoryState


class DelayedSettleResult(StrictModel):
    ok: bool = True
    state: StoryState
    settled: list[str] = Field(default_factory=list)
    pending: list[str] = Field(default_factory=list)
    records: list[EffectRecord] = Field(default_factory=list)
    failures: list[dict[str, Any]] = Field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {"ok": self.ok, "settled": list(self.settled), "pending": list(self.pending),
                "records": [item.model_dump(mode="json") for item in self.records],
                "failures": list(self.failures)}


def _log(state: StoryState, op: str, target: str, *, actor: str, source: str) -> None:
    state.effect_log.append(EffectRecord(id=f"{op}:{target}:{len(state.effect_log) + 1}", op=op,
                                         entity=actor, target=target, source=source,
                                         order=len(state.effect_log) + 1))


def settle_delayed(state: StoryState, *, actor: str = "", only: str = "",
                   force: bool = False) -> DelayedSettleResult:
    """结算所有满足触发条件的延迟后果；force=True 时提前触发指定/全部后果。"""

    working = state.model_copy(deep=True)
    settled: list[str] = []
    pending: list[str] = []
    records: list[EffectRecord] = []
    failures: list[dict[str, Any]] = []
    remaining: list[dict[str, Any]] = []
    for raw in working.delayed_effects:
        delayed_id = str(raw.get("id", ""))
        if only and delayed_id != only:
            remaining.append(raw)
            continue
        try:
            trigger = Condition.model_validate(raw.get("trigger", {}))
            effects = [EffectSpec.model_validate(item) for item in raw.get("effects", [])]
        except Exception as exc:  # noqa: BLE001 - 记录坏数据而不是崩溃
            failures.append({"id": delayed_id, "code": "DELAYED_INVALID", "message": str(exc)})
            remaining.append(raw)
            continue
        ready = force or evaluate(trigger, working, actor=actor).ok
        if not ready:
            pending.append(delayed_id)
            remaining.append(raw)
            continue
        applied = apply_effects(working, effects, actor=actor,
                                source=str(raw.get("source") or raw.get("source_action") or delayed_id))
        if not applied.ok:
            failures.append({"id": delayed_id, "code": applied.code, "message": applied.message})
            remaining.append(raw)
            continue
        working = applied.state
        records.extend(applied.records)
        _log(working, "settle_delayed", delayed_id, actor=actor,
             source=str(raw.get("source_action") or "delayed"))
        settled.append(delayed_id)
    working.delayed_effects = remaining
    return DelayedSettleResult(ok=not failures, state=working, settled=settled, pending=pending,
                               records=records, failures=failures)


def cancel_delayed(state: StoryState, delayed_id: str, *, actor: str = "",
                   reason: str = "") -> DelayedSettleResult:
    working = state.model_copy(deep=True)
    before = len(working.delayed_effects)
    working.delayed_effects = [item for item in working.delayed_effects if item.get("id") != delayed_id]
    if len(working.delayed_effects) == before:
        return DelayedSettleResult(ok=False, state=state, pending=[delayed_id],
                                   failures=[{"id": delayed_id, "code": "DELAYED_NOT_FOUND",
                                              "message": "找不到这个延迟后果"}])
    _log(working, "cancel_delayed", delayed_id, actor=actor, source=reason or "cancel")
    return DelayedSettleResult(ok=True, state=working, settled=[delayed_id])


def replace_delayed(state: StoryState, delayed_id: str, spec: DelayedEffectSpec) -> DelayedSettleResult:
    working = state.model_copy(deep=True)
    replaced = False
    for index, item in enumerate(working.delayed_effects):
        if item.get("id") == delayed_id:
            working.delayed_effects[index] = {
                **spec.model_dump(mode="json"),
                "replaced_from": delayed_id,
            }
            replaced = True
            break
    if not replaced:
        return DelayedSettleResult(ok=False, state=state, pending=[delayed_id],
                                   failures=[{"id": delayed_id, "code": "DELAYED_NOT_FOUND",
                                              "message": "找不到这个延迟后果"}])
    _log(working, "replace_delayed", delayed_id, actor="", source=spec.source or "replace")
    return DelayedSettleResult(ok=True, state=working, settled=[delayed_id])
