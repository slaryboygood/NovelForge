"""Agent action registry（V4-11 §22–§23、§76）：step action 不允许任意字符串。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from .errors import AgentPlanInvalid


@dataclass(frozen=True)
class ActionSpec:
    action: str
    mutation: bool
    protected: bool = False
    target_kinds: tuple[str, ...] = ()
    allowed_inputs: tuple[str, ...] = ()
    requires_revision: bool = False
    description: str = ""


ACTION_REGISTRY: Mapping[str, ActionSpec] = {
    "inspect_blueprint": ActionSpec(
        action="inspect_blueprint", mutation=False, target_kinds=("novel",),
        description="读取 Blueprint / 质量 / 交付状态的只读快照"),
    "generate_node": ActionSpec(
        action="generate_node", mutation=True,
        target_kinds=("novel", "parent"),
        allowed_inputs=("task", "node_type", "parent_id", "index", "sequence",
                        "instruction", "unit_type"),
        description="用既有 generation contract 生成一个新节点（proposed）"),
    "regenerate_node": ActionSpec(
        action="regenerate_node", mutation=True, target_kinds=("node",),
        allowed_inputs=("task", "instruction", "preserve"),
        requires_revision=True,
        description="重生成已有节点（新 revision）"),
    "patch_node": ActionSpec(
        action="patch_node", mutation=True, target_kinds=("node",),
        allowed_inputs=("changes", "reason"), requires_revision=True,
        description="字段级修改（append-only revision）"),
    "rewrite_node": ActionSpec(
        action="rewrite_node", mutation=True, target_kinds=("node",),
        allowed_inputs=("target_fields", "instruction", "preserve_fields",
                        "quality_issue_ids"),
        requires_revision=True, description="AI 字段级改写（proposal）"),
    "evaluate": ActionSpec(
        action="evaluate", mutation=True, target_kinds=("novel", "nodes"),
        allowed_inputs=("gates", "node_ids"),
        description="运行既有 QualityService（gate-based）"),
    "plan_repair": ActionSpec(
        action="plan_repair", mutation=False, target_kinds=("novel", "issues"),
        allowed_inputs=("issue_ids", "node_ids"), description="修复计划（dry-run）"),
    "repair": ActionSpec(
        action="repair", mutation=True, target_kinds=("issues",),
        allowed_inputs=("issue_ids",), description="执行既有 Repair Loop"),
    "verify_repair": ActionSpec(
        action="verify_repair", mutation=False, target_kinds=("issues",),
        allowed_inputs=("issue_ids",), description="修复复核（RepairVerifier）"),
    "request_accept": ActionSpec(
        action="request_accept", mutation=False, protected=True,
        target_kinds=("node",), allowed_inputs=("revision", "reason"),
        description="请求作者接受某个 revision（Agent 不替作者决定）"),
    "accept_revision": ActionSpec(
        action="accept_revision", mutation=True, protected=True,
        target_kinds=("node",), allowed_inputs=("revision", "reason"),
        requires_revision=True, description="接受 revision（需显式批准）"),
    "validate_delivery": ActionSpec(
        action="validate_delivery", mutation=False, target_kinds=("novel",),
        allowed_inputs=("selection_mode", "profile", "formats"),
        description="交付预检（不产生 snapshot）"),
    "deliver": ActionSpec(
        action="deliver", mutation=True, protected=True, target_kinds=("novel",),
        allowed_inputs=("selection_mode", "profile", "formats"),
        description="正式交付（默认禁止，需显式 policy + 批准）"),
}

#: 永不存在的 action（§23）：出现在 plan 里即 AGENT_PLAN_INVALID
FORBIDDEN_ACTIONS: tuple[str, ...] = (
    "run_shell", "run_python", "read_file", "write_file", "execute_sql",
    "import_module", "network_request", "install_plugin",
)


def action_spec(action: str) -> ActionSpec:
    value = str(action or "")
    if value in FORBIDDEN_ACTIONS:
        raise AgentPlanInvalid(f"禁止的 Agent action：{value}",
                               details={"action": value, "forbidden": True})
    spec = ACTION_REGISTRY.get(value)
    if spec is None:
        raise AgentPlanInvalid(f"未注册的 Agent action：{value}",
                               details={"action": value,
                                        "known": sorted(ACTION_REGISTRY)})
    return spec


def is_registered(action: str) -> bool:
    return str(action) in ACTION_REGISTRY


def allowlisted_actions() -> tuple[str, ...]:
    return tuple(sorted(ACTION_REGISTRY))


__all__ = ["ACTION_REGISTRY", "FORBIDDEN_ACTIONS", "ActionSpec", "action_spec",
           "allowlisted_actions", "is_registered"]
