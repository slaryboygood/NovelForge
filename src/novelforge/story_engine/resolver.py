"""统一 Action Resolver（主计划 T07d）。

流程：
输入行动 → 校验条件 → 扣除成本 → 执行即时效果 → 写入延迟后果 → 更新 StoryState → 返回可触发事件

事务性：
- 每一步都在副本上执行；任何一步失败都保持原始 StoryState 不变。
- 失败返回明确原因（条件不满足、成本不足、效果非法）。

可扩展结果：
- success：行动完成
- partial：行动完成，但风险触发，产生额外后果
- blocked：条件或成本不满足，行动未执行
- failed：执行中途失败并已回滚
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import Field

from novelforge.models import StrictModel

from .actions import Action, DelayedEffectSpec
from .conditions import evaluate_all
from .effects import apply_effects
from .entities import EffectRecord
from .state import StoryState

ActionOutcome = Literal["success", "partial", "blocked", "failed"]


class ActionResult(StrictModel):
    ok: bool
    outcome: ActionOutcome
    action_id: str = ""
    code: str = ""
    message: str = ""
    state: StoryState
    records: list[EffectRecord] = Field(default_factory=list)
    triggered_events: list[str] = Field(default_factory=list)
    delayed_effect_ids: list[str] = Field(default_factory=list)
    risk_ids: list[str] = Field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "outcome": self.outcome,
            "action_id": self.action_id,
            "code": self.code,
            "message": self.message,
            "records": [item.model_dump(mode="json") for item in self.records],
            "triggered_events": list(self.triggered_events),
            "delayed_effect_ids": list(self.delayed_effect_ids),
            "risk_ids": list(self.risk_ids),
        }


class ActionResolver:
    """同一 resolver 处理任意题材的行动，只需要内容包提供通用结构。"""

    def resolve(self, action: Action, state: StoryState, *, actor: str = "", target: str = "",
                rolls: list[float] | None = None) -> ActionResult:
        actor_id = action.actor or actor
        requirements = evaluate_all(action.requirements, state, actor=actor_id)
        if not requirements.ok:
            return ActionResult(ok=False, outcome="blocked", action_id=action.id,
                                code=requirements.code or "REQUIREMENT_NOT_SATISFIED",
                                message=requirements.message or "条件不满足", state=state)

        paid = apply_effects(state, action.costs, actor=actor_id, source=f"cost:{action.id}")
        if not paid.ok:
            return ActionResult(ok=False, outcome="blocked", action_id=action.id,
                                code=paid.code or "COST_NOT_PAYABLE",
                                message=paid.message or "成本不足", state=state)

        applied = apply_effects(paid.state, action.immediate_effects, actor=actor_id,
                                source=f"action:{action.id}")
        if not applied.ok:
            return ActionResult(ok=False, outcome="failed", action_id=action.id,
                                code=applied.code or "EFFECT_FAILED",
                                message=applied.message or "行动执行失败", state=state)

        working = applied.state
        records = paid.records + applied.records
        triggered = [record.target for record in applied.records if record.op == "trigger_event"]
        risk_ids: list[str] = []
        outcome: ActionOutcome = "success"

        queue = list(rolls or [])
        for risk in action.risks:
            if risk.probability <= 0:
                continue
            roll = queue.pop(0) if queue else None
            if roll is None or roll >= risk.probability:
                continue
            risk_result = apply_effects(working, risk.effects, actor=actor_id,
                                        source=f"risk:{action.id}:{risk.id or 'risk'}")
            if not risk_result.ok:
                return ActionResult(ok=False, outcome="failed", action_id=action.id,
                                    code=risk_result.code, message=risk_result.message, state=state)
            working = risk_result.state
            records = records + risk_result.records
            risk_ids.append(risk.id or "risk")
            triggered.extend(record.target for record in risk_result.records if record.op == "trigger_event")
            outcome = "partial"

        delayed_ids: list[str] = []
        for delayed in action.delayed_effects:
            record = _delayed_record(delayed, action=action, revision=len(working.effect_log))
            working.delayed_effects.append(record)
            delayed_ids.append(delayed.id)

        return ActionResult(ok=True, outcome=outcome, action_id=action.id, state=working,
                            records=records, triggered_events=sorted(set(triggered)),
                            delayed_effect_ids=delayed_ids, risk_ids=risk_ids,
                            message="行动完成" if outcome == "success" else "行动完成，但风险已触发")


def _delayed_record(delayed: DelayedEffectSpec, *, action: Action, revision: int) -> dict[str, Any]:
    return {
        "id": delayed.id,
        "source_action": action.id,
        "source": delayed.source or action.id,
        "description": delayed.description,
        "trigger": delayed.trigger.model_dump(mode="json"),
        "effects": [item.model_dump(mode="json") for item in delayed.effects],
        "created_at_effect_count": revision,
        "data": dict(delayed.data),
    }
