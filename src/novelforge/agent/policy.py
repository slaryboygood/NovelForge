"""Agent policy 校验（V4-11 §14–§17、§43–§46、§77）。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from .contracts import AgentPolicy, AgentScope, AgentStep, utc_now
from .errors import AgentBudgetExhausted, AgentPolicyDenied
from .registry import action_spec

#: 高层 / 已接受节点属于 protected（§16、§51）
HIGH_LEVEL_NODE_TYPES: tuple[str, ...] = (
    "premise", "theme", "world", "story_arc", "structural_unit",
)

#: action → policy 开关（accept / deliver 另行处理：见 check_action_allowed）
ACTION_POLICY_FLAG: Mapping[str, str] = {
    "generate_node": "allow_generation",
    "regenerate_node": "allow_generation",
    "patch_node": "allow_edit",
    "rewrite_node": "allow_edit",
    "evaluate": "allow_quality",
    "plan_repair": "allow_quality",
    "repair": "allow_repair",
    "verify_repair": "allow_repair",
}


@dataclass
class AgentBudget:
    """一次 run 的预算账本（§45）：只汇总可用 usage，不发明价格。"""

    steps: int = 0
    mutations: int = 0
    repair_rounds: int = 0
    model_calls: int = 0
    tokens: int = 0
    cost: float = 0.0
    started_at: str = ""
    usage: dict[str, Any] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if not self.started_at:
            self.started_at = utc_now()
        if self.usage is None:
            self.usage = {}

    def as_dict(self) -> dict[str, Any]:
        return {"steps": int(self.steps), "mutations": int(self.mutations),
                "repair_rounds": int(self.repair_rounds),
                "model_calls": int(self.model_calls), "tokens": int(self.tokens),
                "cost": round(float(self.cost), 6),
                "elapsed_s": elapsed_seconds(self.started_at),
                "by_phase": {key: dict(value) for key, value
                             in sorted(((self.usage or {}).get("by_phase") or {}).items())},
                "total": dict((self.usage or {}).get("total") or {})}


def elapsed_seconds(started_at: str) -> float:
    import datetime as _dt

    try:
        started = _dt.datetime.fromisoformat(str(started_at))
    except ValueError:
        return 0.0
    return max(0.0, (_dt.datetime.now(_dt.timezone.utc) - started).total_seconds())


def merge_usage(budget: AgentBudget, phase: str,
                usage: Mapping[str, Any] | None) -> None:
    """把某个 phase 的 usage 汇总进预算（只累加后端给出的数字）。"""

    row = dict(usage or {})
    if not row:
        return
    budget.usage.setdefault("by_phase", {})[phase] = row
    total = budget.usage.setdefault("total", {})
    for key, value in row.items():
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            total[key] = total.get(key, 0) + value
    calls = int(row.get("calls") or row.get("llm_calls") or 0)
    if calls:
        budget.model_calls += calls
    tokens = int(row.get("total_tokens") or row.get("tokens") or 0)
    if tokens:
        budget.tokens += tokens
    cost = float(row.get("cost") or 0.0)
    if cost:
        budget.cost += cost


def check_action_allowed(action: str, policy: AgentPolicy, *,
                         node_type: str = "", node_status: str = "") -> bool:
    """action 是否被 policy 允许；返回是否需要 approval。"""

    spec = action_spec(action)
    # §17 / §71：accept 与 deliver 是 protected，默认必须作者批准；
    # `allow_auto_accept=False` 表示「不得无人值守地接受」，而不是禁止发起审批；
    # `allow_delivery=False` 表示「不得正式交付」（交付必须显式开启）。
    if spec.action == "accept_revision":
        return True
    if spec.action == "deliver":
        if not bool(policy.allow_delivery):
            raise AgentPolicyDenied(
                "policy 不允许正式交付：deliver（allow_delivery=false）",
                details={"action": "deliver", "policy_flag": "allow_delivery"})
        return True
    flag = ACTION_POLICY_FLAG.get(spec.action)
    if flag is not None and not bool(getattr(policy, flag)):
        raise AgentPolicyDenied(
            f"policy 不允许该操作：{spec.action}（{flag}=false）",
            details={"action": spec.action, "policy_flag": flag})
    # protected：显式列为 protected、或目标是已接受的高层节点（§16、§51）
    if spec.protected and spec.action in policy.require_approval_for:
        return True
    if spec.action in policy.require_approval_for:
        return True
    if (spec.mutation and node_status == "accepted"
            and node_type in HIGH_LEVEL_NODE_TYPES):
        return True
    if (spec.action == "regenerate_node" and node_status == "accepted"
            and node_type in HIGH_LEVEL_NODE_TYPES):
        return True
    return False


def check_scope(scope: AgentScope, *, node_id: str = "", node_type: str = "",
                parent_id: str = "", ancestry: Sequence[str] = ()) -> None:
    """目标是否落在作者显式 scope 内（§13、§77）。"""

    if scope.is_whole_novel:
        return
    allowed_ids = set(scope.node_ids)
    if scope.unit_id:
        allowed_ids.add(str(scope.unit_id))
    chain = {str(node_id), str(parent_id), *[str(row) for row in ancestry]}
    if scope.kind == "nodes":
        if not (chain & allowed_ids):
            raise AgentPolicyDenied(
                f"目标超出 goal scope：{node_id or parent_id}",
                details={"scope": scope.as_dict(), "target": node_id or parent_id})
        return
    if scope.kind == "scene" and node_type not in ("scene", "setup", "payoff",
                                                   "causal_link", ""):
        raise AgentPolicyDenied(
            f"scene scope 只能修改场景相关内容（收到 {node_type}）",
            details={"scope": scope.as_dict(), "node_type": node_type})
    if scope.kind == "chapter" and node_type in ("story_arc", "structural_unit",
                                                 "world", "premise", "theme"):
        raise AgentPolicyDenied(
            f"chapter scope 不能修改高层结构（收到 {node_type}）",
            details={"scope": scope.as_dict(), "node_type": node_type})
    if scope.kind == "structural_unit" and node_type in ("world", "premise", "theme"):
        raise AgentPolicyDenied(
            f"structural_unit scope 不能修改更高层内容（收到 {node_type}）",
            details={"scope": scope.as_dict(), "node_type": node_type})
    if allowed_ids and not (chain & allowed_ids):
        raise AgentPolicyDenied(
            f"目标不在 goal scope 内：{node_id or parent_id}",
            details={"scope": scope.as_dict(), "target": node_id or parent_id})


def check_budget(policy: AgentPolicy, budget: AgentBudget, *,
                 next_step: AgentStep | None = None,
                 steps_executed: int = 0) -> None:
    """预算 / 上限硬检查（§43、§46、§86、§87）：达到即 STOP。"""

    if steps_executed >= int(policy.max_steps):
        raise AgentBudgetExhausted(
            f"达到 max_steps={policy.max_steps}（已执行 {steps_executed} 步）",
            details={"kind": "max_steps", "max_steps": int(policy.max_steps)})
    if int(budget.mutations) >= int(policy.max_mutations) and next_step is not None \
            and next_step.mutation:
        raise AgentBudgetExhausted(
            f"达到 max_mutations={policy.max_mutations}",
            details={"kind": "max_mutations",
                     "max_mutations": int(policy.max_mutations)})
    if policy.token_budget is not None and budget.tokens > int(policy.token_budget):
        raise AgentBudgetExhausted(
            f"token 预算用尽：{budget.tokens} > {policy.token_budget}",
            details={"kind": "token_budget", "tokens": int(budget.tokens)})
    if policy.cost_budget is not None and budget.cost > float(policy.cost_budget):
        raise AgentBudgetExhausted(
            f"cost 预算用尽：{budget.cost:.6f} > {policy.cost_budget}",
            details={"kind": "cost_budget", "cost": round(budget.cost, 6)})
    if policy.time_budget_s is not None \
            and elapsed_seconds(budget.started_at) > float(policy.time_budget_s):
        raise AgentBudgetExhausted(
            "time 预算用尽",
            details={"kind": "time_budget",
                     "elapsed_s": round(elapsed_seconds(budget.started_at), 3)})


__all__ = [
    "ACTION_POLICY_FLAG", "AgentBudget", "HIGH_LEVEL_NODE_TYPES",
    "check_action_allowed", "check_budget", "check_scope", "elapsed_seconds",
    "merge_usage",
]
