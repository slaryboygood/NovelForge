"""Planner（V4-11 §24–§31、§75–§77）。

```text
goal + snapshot + policy  →  bounded AgentPlan（结构化、可验证）
```

两条路径，**同一套校验**：

```text
HeuristicPlanner   确定性指令解析（默认；不依赖模型，测试可复现）
ModelPlanner       可选：agent.plan.v1 structured output（经 AgentPlannerModel port）
```

Planner **不执行**任何操作；输出必须经过 §77 的安全校验才能进入 Executor。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, replace
from typing import Any, Mapping, Sequence

from .contracts import (
    AgentContextSnapshot,
    AgentGoal,
    AgentPlan,
    AgentPolicy,
    AgentStep,
    utc_now,
)
from .errors import AgentPlanInvalid, AgentRevisionConflict
from .policy import HIGH_LEVEL_NODE_TYPES, check_action_allowed, check_scope
from .ports import AgentPlannerModel
from .registry import ACTION_REGISTRY, action_spec

PLANNER_VERSION = "deterministic-v1"
MODEL_PLANNER_VERSION = "model-v1"
MODEL_PLAN_CONTRACT = "agent.plan.v1"


@dataclass(frozen=True)
class AgentIntent:
    """从作者目标解析出的明确意图（确定性部分）。"""

    unit_id: str = ""
    target_chapters: int = 0
    min_scenes_per_chapter: int = 0
    run_quality: bool = False
    repair: bool = False
    request_accept: bool = False
    delivery: bool = False
    rewrite_node_id: str = ""
    rewrite_fields: tuple[str, ...] = ()
    rewrite_instruction: str = ""
    scope_kind: str = "novel"

    def as_dict(self) -> dict[str, Any]:
        return {"unit_id": self.unit_id, "target_chapters": self.target_chapters,
                "min_scenes_per_chapter": self.min_scenes_per_chapter,
                "run_quality": self.run_quality, "repair": self.repair,
                "request_accept": self.request_accept, "delivery": self.delivery,
                "rewrite_node_id": self.rewrite_node_id,
                "rewrite_fields": list(self.rewrite_fields),
                "scope_kind": self.scope_kind}


_CN_NUMBERS = {"一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5, "六": 6,
               "七": 7, "八": 8, "九": 9, "十": 10}


def _number(text: str, match: str) -> int:
    if not match:
        return 0
    if match.isdigit():
        return int(match)
    return _CN_NUMBERS.get(match, 0)


def parse_intent(goal: AgentGoal, snapshot: AgentContextSnapshot) -> AgentIntent:
    """确定性解析作者指令中的**数量 / 动作开关**（§75）。

    只识别明确写出的数量与动作；不含创意判断（创意内容仍由 generation contract 产生）。
    """

    text = str(goal.instruction or "")
    scope = goal.scope

    chapters = 0
    match = re.search(r"(\d+|[一二两三四五六七八九十]+)\s*个?\s*章节?", text)
    if match:
        chapters = _number(text, match.group(1))
    per_chapter = 0
    match = re.search(
        r"每章\s*(?:至少|最少)?\s*(?:有|要|需)?\s*(\d+|[一二两三四五六七八九十]+)"
        r"\s*个?\s*场景", text)
    if match:
        per_chapter = _number(text, match.group(1))

    run_quality = any(word in text for word in ("质量检查", "质量", "检查", "evaluate"))
    repair = any(word in text for word in ("修复", "repair"))
    no_accept = any(word in text for word in ("不要自动接受", "不要接受", "先不接受",
                                              "不自动接受"))
    # 「已接受 / 被接受」是状态描述，不是要求 Agent 去接受
    neutralised = text.replace("已接受", " ").replace("被接受", " ")
    want_accept = (not no_accept) and any(word in neutralised for word in
                                          ("接受", "采纳", "accept"))
    delivery = any(word in text for word in ("交付", "导出", "deliver", "export"))

    rewrite_node_id = ""
    rewrite_fields: tuple[str, ...] = ()
    rewrite_instruction = ""
    if "重写" in text or "改写" in text:
        # 目标节点：指令里提到的类型优先（例如「重写 Story Arc 高潮」），
        # 其次才是 scope 指定的具体节点。
        lowered = text.lower()
        mentioned = ""
        for keyword, node_type in (("故事弧", "story_arc"), ("story arc", "story_arc"),
                                   ("高潮", "story_arc"), ("climax", "story_arc"),
                                   ("章节", "chapter"), ("场景", "scene"),
                                   ("人物弧", "character_arc"), ("世界", "world"),
                                   ("前提", "premise"), ("主题", "theme")):
            if keyword in lowered:
                mentioned = node_type
                break
        if mentioned:
            candidates = snapshot.nodes_of_type(mentioned)
            rewrite_node_id = candidates[0] if candidates else ""
        elif scope.kind == "nodes" and scope.node_ids:
            rewrite_node_id = scope.node_ids[0]
        elif scope.kind in ("scene", "chapter", "structural_unit") and scope.unit_id:
            rewrite_node_id = scope.unit_id
        if "climax" in text or "高潮" in text:
            rewrite_fields = ("climax",)
        rewrite_instruction = text

    unit_id = scope.unit_id
    if not unit_id and scope.kind == "novel":
        units = snapshot.nodes_of_type("structural_unit")
        if units:
            unit_id = units[0]
    return AgentIntent(unit_id=unit_id, target_chapters=chapters,
                       min_scenes_per_chapter=per_chapter, run_quality=run_quality,
                       repair=repair, request_accept=want_accept, delivery=delivery,
                       rewrite_node_id=rewrite_node_id, rewrite_fields=rewrite_fields,
                       rewrite_instruction=rewrite_instruction,
                       scope_kind=scope.kind)


def _step(action: str, *, target: Mapping[str, Any], inputs: Mapping[str, Any] | None = None,
          sequence: int, expected_revision: int | None = None,
          requires_approval: bool = False, node_status: str = "",
          node_type: str = "") -> AgentStep:
    spec = action_spec(action)
    return AgentStep(action=spec.action, target=dict(target),
                     inputs=dict(inputs or {}), sequence=int(sequence),
                     expected_revision=expected_revision,
                     mutation=spec.mutation, requires_approval=requires_approval,
                     success_criteria=_success_criteria(spec.action))


def _success_criteria(action: str) -> tuple[str, ...]:
    return {
        "generate_node": ("node_exists", "status_proposed"),
        "regenerate_node": ("revision_changed",),
        "patch_node": ("revision_changed", "fields_match"),
        "rewrite_node": ("revision_changed", "fields_match"),
        "evaluate": ("report_exists",),
        "plan_repair": ("plan_exists",),
        "repair": ("verification_status",),
        "verify_repair": ("verification_recorded",),
        "request_accept": ("approval_recorded",),
        "accept_revision": ("accepted",),
        "validate_delivery": ("validation_recorded",),
        "deliver": ("manifest_exists",),
        "inspect_blueprint": ("snapshot_recorded",),
    }.get(action, ())


class HeuristicPlanner:
    """确定性 Planner（默认）：指令 → 有界计划；不做创意生成。"""

    version = PLANNER_VERSION

    def plan(self, goal: AgentGoal, snapshot: AgentContextSnapshot,
             policy: AgentPolicy) -> AgentPlan:
        intent = parse_intent(goal, snapshot)
        steps: list[AgentStep] = []
        policy_notes: list[str] = []
        sequence = 0
        protected_nodes: list[str] = []

        def add(action: str, *, target: Mapping[str, Any],
                inputs: Mapping[str, Any] | None = None,
                expected_revision: int | None = None, node_status: str = "",
                node_type: str = "") -> None:
            nonlocal sequence
            sequence += 1
            approval = check_action_allowed(action, policy, node_type=node_type,
                                            node_status=node_status)
            if approval and (target.get("node_id") or target.get("parent_id")):
                protected_nodes.append(str(target.get("node_id")
                                           or target.get("parent_id")))
            steps.append(_step(action, target=target, inputs=inputs,
                               sequence=sequence, expected_revision=expected_revision,
                               requires_approval=approval, node_status=node_status,
                               node_type=node_type))

        add("inspect_blueprint", target={"kind": "novel", "novel_id": goal.novel_id})

        unit_id = intent.unit_id
        if intent.target_chapters > 0 and unit_id:
            existing = [node_id for node_id in snapshot.children_of(unit_id, "chapter")]
            for index in range(len(existing) + 1, int(intent.target_chapters) + 1):
                add("generate_node",
                    target={"kind": "parent", "parent_id": unit_id,
                            "node_type": "chapter"},
                    inputs={"task": "chapter", "parent_id": unit_id, "index": index})

        if intent.min_scenes_per_chapter > 0:
            chapter_ids = ([node_id for node_id in snapshot.children_of(unit_id, "chapter")]
                           if unit_id else list(snapshot.nodes_of_type("chapter")))
            for chapter_id in chapter_ids:
                existing = snapshot.children_of(chapter_id, "scene")
                for seq in range(len(existing) + 1,
                                 int(intent.min_scenes_per_chapter) + 1):
                    add("generate_node",
                        target={"kind": "parent", "parent_id": chapter_id,
                                "node_type": "scene"},
                        inputs={"task": "scene", "parent_id": chapter_id,
                                "sequence": seq})

        if intent.rewrite_node_id:
            revision = snapshot.revision_of(intent.rewrite_node_id) or None
            node_type = str(dict(snapshot.node_types).get(intent.rewrite_node_id) or "")
            node_status = str(dict(snapshot.node_status).get(intent.rewrite_node_id) or "")
            inputs: dict[str, Any] = {"instruction": intent.rewrite_instruction}
            if intent.rewrite_fields:
                inputs["target_fields"] = list(intent.rewrite_fields)
            add("rewrite_node",
                target={"kind": "node", "node_id": intent.rewrite_node_id,
                        "node_type": node_type},
                inputs=inputs, expected_revision=revision, node_status=node_status,
                node_type=node_type)

        if intent.run_quality:
            add("evaluate", target={"kind": "novel", "novel_id": goal.novel_id})
        if intent.repair and policy.allow_repair:
            add("plan_repair", target={"kind": "novel", "novel_id": goal.novel_id},
                inputs={"issue_ids": []})
            add("repair", target={"kind": "issues"},
                inputs={"issue_ids": []})
            add("verify_repair", target={"kind": "issues"},
                inputs={"issue_ids": []})
        if intent.request_accept:
            targets = sorted(set(snapshot.nodes_of_type("chapter"))
                             | set(snapshot.nodes_of_type("scene")))
            if targets:
                node_id = targets[-1]
                revision = snapshot.revision_of(node_id)
                add("request_accept",
                    target={"kind": "node", "node_id": node_id,
                            "node_type": str(dict(snapshot.node_types).get(node_id) or "")},
                    inputs={"revision": revision},
                    expected_revision=revision,
                    node_status=str(dict(snapshot.node_status).get(node_id) or ""),
                    node_type=str(dict(snapshot.node_types).get(node_id) or ""))
                add("accept_revision",
                    target={"kind": "node", "node_id": node_id,
                            "node_type": str(dict(snapshot.node_types).get(node_id) or "")},
                    inputs={"revision": revision},
                    expected_revision=revision,
                    node_status=str(dict(snapshot.node_status).get(node_id) or ""),
                    node_type=str(dict(snapshot.node_types).get(node_id) or ""))
        if intent.delivery and policy.allow_delivery:
            add("validate_delivery", target={"kind": "novel", "novel_id": goal.novel_id})
            add("deliver", target={"kind": "novel", "novel_id": goal.novel_id},
                inputs={"formats": ["json"]})
        elif intent.delivery:
            policy_notes.append(
                "作者要求交付，但 policy.allow_delivery=false：本计划不包含正式交付"
                "（交付需要显式开启的策略 + 作者批准）")
            add("validate_delivery", target={"kind": "novel", "novel_id": goal.novel_id})

        plan = AgentPlan(
            novel_id=goal.novel_id, goal_id=goal.goal_id, steps=tuple(steps),
            estimated_mutations=sum(1 for step in steps if step.mutation),
            estimated_model_calls=sum(1 for step in steps
                                      if step.action in ("generate_node",
                                                         "regenerate_node",
                                                         "rewrite_node")),
            affected_nodes=tuple(sorted({str(step.target.get("node_id") or
                                             step.target.get("parent_id") or "")
                                         for step in steps} - {""})),
            protected_nodes=tuple(sorted(set(protected_nodes))),
            required_approvals=tuple(step.step_id for step in steps
                                     if step.requires_approval),
            budget_estimate={"steps": len(steps),
                             "mutations": sum(1 for step in steps if step.mutation),
                             "token_budget": policy.token_budget,
                             "cost_budget": policy.cost_budget,
                             "policy_notes": list(policy_notes)},
            planner_version=self.version, snapshot_digest=snapshot.digest)
        validate_plan(plan, goal=goal, policy=policy, snapshot=snapshot)
        return plan


class ModelPlanner:
    """可选模型 Planner（§25、§76）：structured output + 同一套校验。

    模型只能**选择**注册 action 与已定义参数；输出经 `validate_plan` 后
    与 HeuristicPlanner 走完全相同的执行路径。
    """

    version = MODEL_PLANNER_VERSION

    def __init__(self, model: AgentPlannerModel) -> None:
        self.model = model

    def plan(self, goal: AgentGoal, snapshot: AgentContextSnapshot,
             policy: AgentPolicy) -> AgentPlan:
        proposal = dict(self.model.propose_plan(
            goal=goal.as_dict(), snapshot=snapshot.as_dict(), policy=policy.as_dict(),
            action_catalog=tuple(sorted(ACTION_REGISTRY))) or {})
        raw_steps = proposal.get("steps") or []
        if not isinstance(raw_steps, (list, tuple)):
            raise AgentPlanInvalid("agent.plan.v1 输出必须是 {steps: [...]}")
        steps: list[AgentStep] = []
        for index, row in enumerate(raw_steps, start=1):
            if not isinstance(row, Mapping):
                raise AgentPlanInvalid("step 必须是对象")
            spec = action_spec(str(row.get("action") or ""))
            unknown = sorted(set(row.get("inputs") or {}) - set(spec.allowed_inputs))
            if unknown:
                raise AgentPlanInvalid(
                    f"step 参数不在契约内：{unknown}",
                    details={"action": spec.action, "unknown": unknown})
            steps.append(AgentStep(
                action=spec.action, target=dict(row.get("target") or {}),
                inputs=dict(row.get("inputs") or {}), sequence=int(row.get("sequence")
                                                                  or index),
                expected_revision=(int(row["expected_revision"])
                                   if row.get("expected_revision") is not None else None),
                mutation=spec.mutation, success_criteria=_success_criteria(spec.action)))
        plan = AgentPlan(
            novel_id=goal.novel_id, goal_id=goal.goal_id, steps=tuple(steps),
            estimated_mutations=sum(1 for step in steps if step.mutation),
            estimated_model_calls=int(proposal.get("estimated_model_calls")
                                      or sum(1 for step in steps if step.mutation)),
            affected_nodes=tuple(sorted({str(step.target.get("node_id") or
                                             step.target.get("parent_id") or "")
                                         for step in steps} - {""})),
            budget_estimate={"steps": len(steps),
                             "mutations": sum(1 for step in steps if step.mutation)},
            planner_version=self.version, snapshot_digest=snapshot.digest)
        validate_plan(plan, goal=goal, policy=policy, snapshot=snapshot)
        return plan


def validate_plan(plan: AgentPlan, *, goal: AgentGoal, policy: AgentPolicy,
                  snapshot: AgentContextSnapshot) -> AgentPlan:
    """§77 安全校验：action / scope / target / revision / policy / approval / budget。"""

    if str(plan.novel_id) != str(goal.novel_id):
        raise AgentPlanInvalid("plan.novel_id 与 goal 不一致")
    if len(plan.steps) > int(policy.max_steps):
        raise AgentPlanInvalid(
            f"计划步骤数 {len(plan.steps)} 超过 max_steps={policy.max_steps}")
    if plan.mutations > int(policy.max_mutations):
        raise AgentPlanInvalid(
            f"计划 mutation 数 {plan.mutations} 超过 max_mutations={policy.max_mutations}")

    seen_sequences: set[int] = set()
    created_nodes: set[str] = set()
    for step in plan.steps:
        spec = action_spec(step.action)         # 未知 / 禁止的 action → AGENT_PLAN_INVALID
        if spec.mutation != bool(step.mutation):
            raise AgentPlanInvalid(
                f"step.mutation 与 action 契约不一致：{spec.action}")
        unknown_inputs = sorted(set(step.inputs) - set(spec.allowed_inputs))
        if unknown_inputs:
            raise AgentPlanInvalid(
                f"step 参数不在契约内：{unknown_inputs}",
                details={"action": spec.action, "unknown": unknown_inputs})
        if spec.target_kinds and step.target.get("kind") not in spec.target_kinds:
            raise AgentPlanInvalid(
                f"step target.kind 不被支持：{step.target.get('kind')}",
                details={"action": spec.action, "target_kinds": list(spec.target_kinds)})
        if int(step.sequence) in seen_sequences:
            raise AgentPlanInvalid(f"step sequence 重复：{step.sequence}")
        seen_sequences.add(int(step.sequence))

        node_id = str(step.target.get("node_id") or "")
        parent_id = str(step.target.get("parent_id") or "")
        node_type = str(step.target.get("node_type")
                        or dict(snapshot.node_types).get(node_id) or "")
        node_status = str(dict(snapshot.node_status).get(node_id) or "")

        # scope（§13）
        if spec.action not in ("inspect_blueprint", "evaluate", "plan_repair", "repair",
                               "verify_repair", "validate_delivery", "deliver"):
            chain = []
            # 从目标节点沿 snapshot.parent_ids 向上走（结构在 snapshot 里，不在 step 上）
            cursor = str(dict(snapshot.parent_ids).get(node_id) or parent_id)
            for _ in range(6):
                if not cursor:
                    break
                chain.append(cursor)
                cursor = str(dict(snapshot.parent_ids).get(cursor) or "")
            check_scope(goal.scope, node_id=node_id, node_type=node_type,
                        parent_id=parent_id, ancestry=chain)

        # target 存在性（新节点由本 plan 更早的 step 创建时视为存在）
        if spec.action in ("regenerate_node", "patch_node", "rewrite_node",
                           "accept_revision", "request_accept"):
            if node_id and node_id not in dict(snapshot.node_types) \
                    and node_id not in created_nodes:
                raise AgentPlanInvalid(f"目标节点不存在：{node_id}")
        if spec.action == "generate_node" and parent_id:
            exists = (parent_id in dict(snapshot.node_types)
                      or parent_id in created_nodes)
            if not exists:
                raise AgentPlanInvalid(f"父节点不存在：{parent_id}")

        # revision（§34）
        if spec.requires_revision or (step.mutation and node_id):
            if step.expected_revision is None:
                raise AgentPlanInvalid(
                    f"修改已有节点的 step 必须携带 expected_revision：{spec.action}")
            current = snapshot.revision_of(node_id) if node_id else 0
            if current and int(step.expected_revision) != current:
                raise AgentRevisionConflict(
                    f"计划基于 r{step.expected_revision}，当前是 r{current}",
                    details={"node_id": node_id, "expected_revision":
                             int(step.expected_revision), "current_revision": current})

        # policy / approval（§16、§77）
        approval = check_action_allowed(spec.action, policy, node_type=node_type,
                                       node_status=node_status)
        if approval and not step.requires_approval:
            raise AgentPlanInvalid(
                f"protected action 必须标记 requires_approval：{spec.action}")
        if spec.action == "generate_node" and str(
                step.inputs.get("task") or "") in ("scene", "chapter"):
            created_nodes.add(str(step.inputs.get("task")))

    return plan


def default_planner() -> HeuristicPlanner:
    return HeuristicPlanner()


__all__ = [
    "AgentIntent", "HeuristicPlanner", "MODEL_PLAN_CONTRACT", "MODEL_PLANNER_VERSION",
    "ModelPlanner", "PLANNER_VERSION", "default_planner", "parse_intent",
    "validate_plan",
]
