"""Repair Planner（V4-05 §31、§54、§58）。

输入 `QualityIssue[]` + 当前 Blueprint 结构，输出 `RepairPlan`：

```text
合并相关 issues → 确定最小 scope → 确定 preserve / allow_change →
检测互相冲突的 repair contract → 确定修复顺序 → 计算 blast radius
```

Planner **不生成任何新内容**、不调用模型、不写 revision（§31 / §58）。

红线（§54）：模型只能提出 candidate issue；`scope expansion / preserve / allow_change`
由本 Planner 依据结构关系决定，避免「最好重写前三章」式的大范围改动。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from novelforge.blueprint import BlueprintRepository
from novelforge.core.ids import digest_payload

from ..contracts import QualityIssue, QualityScope
from ..errors import QualityScopeError, RepairConflictError, RepairNotAllowedError
from .blast_radius import GATE_ORDER, RepairBlastRadius
from .contracts import RepairContract, RepairPlan, RepairStep

#: 节点类型 → 生成任务（generation Public Contract 的任务名）
NODE_TYPE_TASK: Mapping[str, str] = {
    "premise": "premise",
    "theme": "theme",
    "world": "world",
    "character": "character",
    "character_arc": "character_arc",
    "story_arc": "story_arc",
    "structural_unit": "structural_unit",
    "chapter": "chapter",
    "scene": "scene",
}

#: 结构节点本身没有生成任务：修复要落到它们的宿主节点上
DERIVED_NODE_TYPES: tuple[str, ...] = ("setup", "payoff", "causal_link")

#: 步骤排序权重（父节点先于子节点）
_ORDER_RANK: Mapping[str, int] = {
    "premise": 0, "theme": 0, "world": 0, "character": 0, "character_arc": 0,
    "story_arc": 0, "structural_unit": 1, "chapter": 2, "scene": 3,
}

#: 结构 identity 字段：质量修复**永远**不得改动（§30 preserve 是硬约束）
STRUCTURAL_PRESERVE: Mapping[str, tuple[str, ...]] = {
    "scene": ("chapter_id",),
    "chapter": ("characters",),
    "character_arc": ("character_id",),
    "causal_link": ("source_node", "target_node"),
    "payoff": ("resolves_setup_ids",),
}


def payload_fields(node: Any) -> tuple[str, ...]:
    """节点的真实 payload 字段（preserve 只能包含真实存在的字段）。"""

    payload = getattr(node, "payload", None)
    fields = getattr(type(payload), "model_fields", None)
    if isinstance(fields, Mapping):
        return tuple(sorted(str(name) for name in fields))
    if hasattr(payload, "model_dump"):
        return tuple(sorted(str(name) for name in payload.model_dump(mode="json")))
    return tuple(sorted(str(name) for name in dict(payload or {})))


class RepairPlanner:
    """把 QualityIssue 变成可执行（或需人工）的最小修复计划。"""

    def __init__(self, project_root: Path | str, novel_id: str, *,
                 repository: BlueprintRepository | None = None) -> None:
        if not str(novel_id or "").strip():
            raise QualityScopeError("RepairPlanner 需要显式 novel_id")
        self.project_root = Path(project_root)
        self.novel_id = str(novel_id)
        self.repository = repository or BlueprintRepository(self.project_root,
                                                            self.novel_id)

    # ------------------------------------------------------------------ 规划
    def plan(self, issues: Iterable[QualityIssue], *, dry_run: bool = True,
             expected_revisions: Mapping[str, int] | None = None,
             strict: bool = False) -> RepairPlan:
        """产出 RepairPlan；`strict=True` 时把冲突 / 不可修直接升级为异常。"""

        rows = list(issues)
        self._assert_ownership(rows)
        nodes = {node.node_id: node for node in self.repository.all_nodes()}

        human_reasons: list[str] = []
        groups: dict[str, list[QualityIssue]] = {}
        for issue in rows:
            if not issue.repairable:
                human_reasons.append(
                    f"{issue.issue_id}（{issue.code}）不可自动修复，需人工决定")
                continue
            anchor = self._anchor(issue, nodes)
            if not anchor:
                human_reasons.append(
                    f"{issue.issue_id}（{issue.code}）无法定位最小修复节点")
                continue
            groups.setdefault(anchor, []).append(issue)

        contracts: list[RepairContract] = []
        steps: list[RepairStep] = []
        conflicts: list[str] = []
        for index, node_id in enumerate(sorted(
                groups, key=lambda value: self._sort_key(value, nodes)), start=1):
            node = nodes[node_id]
            contract, node_conflicts = self._contract(node, groups[node_id])
            contracts.append(contract)
            conflicts.extend(node_conflicts)
            gates = sorted({issue.gate for issue in groups[node_id]},
                           key=lambda gate: (GATE_ORDER.index(gate)
                                             if gate in GATE_ORDER else 99, gate))
            steps.append(RepairStep(
                step_id=f"RS_{index:02d}_{node_id}", order=index,
                node_id=node_id, node_type=node.node_type,
                task=NODE_TYPE_TASK[node.node_type], gate=gates[0],
                expected_revision=self._expected(node, expected_revisions),
                issue_ids=contract.issue_ids, contract=contract,
                preserve=contract.preserve, allow_change=contract.allow_change,
                constraints=contract.constraints,
                reason="；".join(sorted({issue.reason for issue in groups[node_id]}))))

        blast = RepairBlastRadius.compute(
            nodes=list(nodes.values()),
            changed=[step.node_id for step in steps],
            issue_gates=sorted({issue.gate for issue in rows}))
        scope = self._plan_scope(rows, blast)

        if conflicts:
            status = "conflict"
        elif not steps:
            status = "empty" if not rows else "needs_human_review"
        elif human_reasons:
            status = "needs_human_review"
        else:
            status = "planned"

        plan = RepairPlan(
            plan_id=self._plan_id(rows, steps), novel_id=self.novel_id,
            scope=scope, status=status, steps=tuple(steps),
            contracts=tuple(contracts), blast_radius=blast,
            conflicts=tuple(sorted(set(conflicts))),
            human_review_reasons=tuple(sorted(set(human_reasons))),
            notes=("dry run：未写入任何 revision",) if dry_run else (),
            dry_run=dry_run, issue_ids=tuple(sorted({row.issue_id for row in rows})))

        if strict and conflicts:
            raise RepairConflictError("repair contract 互相冲突",
                                      details={"plan": plan.as_dict()})
        if strict and human_reasons:
            raise RepairNotAllowedError("存在不可自动修复的 issue",
                                      details={"reasons": sorted(set(human_reasons))})
        return plan

    # ------------------------------------------------------------------ 内部
    def _assert_ownership(self, issues: Sequence[QualityIssue]) -> None:
        foreign = sorted({issue.novel_id for issue in issues
                          if issue.novel_id != self.novel_id})
        if foreign:
            raise QualityScopeError(
                f"拒绝跨作品规划：{foreign} != {self.novel_id}",
                details={"foreign_novels": foreign})

    def _anchor(self, issue: QualityIssue, nodes: Mapping[str, Any]) -> str:
        """最小修复锚点：issue scope 里可直接重生成的节点（结构节点回落到宿主）。"""

        candidates = [str(value) for value in issue.scope.node_ids if value]
        if not candidates:
            return ""
        if len(candidates) > 1:
            # multi-root issue（例如图级问题）：不猜测最小 scope（AMBIGUOUS_DO_NOT_MERGE）
            direct = [node_id for node_id in candidates
                      if node_id in nodes
                      and nodes[node_id].node_type in NODE_TYPE_TASK]
            if len(direct) == 1:
                return direct[0]
            return ""
        node_id = candidates[0]
        node = nodes.get(node_id)
        if node is None:
            return ""
        if node.node_type in NODE_TYPE_TASK:
            return node_id
        if node.node_type in DERIVED_NODE_TYPES:
            parent_id = str(getattr(node, "parent_id", "") or "")
            parent = nodes.get(parent_id)
            if parent is not None and parent.node_type in NODE_TYPE_TASK:
                return parent_id
        return ""

    def _contract(self, node: Any,
                  issues: Sequence[QualityIssue]
                  ) -> tuple[RepairContract, list[str]]:
        fields = set(payload_fields(node))
        preserve: set[str] = set()
        allow: set[str] = set()
        constraints: set[str] = set()
        for issue in issues:
            preserve.update(issue.preserve_fields)
            allow.update(issue.allow_change_fields)
            constraints.update(str(value) for value in
                               (issue.repair_contract.get("constraints") or ()))
        # allow_change 只能是真实存在的 payload 字段（否则 generation 无法执行）
        allow &= fields
        preserve |= {"canon", "source_ids", "node_id"}
        preserve |= set(STRUCTURAL_PRESERVE.get(node.node_type, ())) & fields
        # 两个 contract 要求「改」又要求「保留」同一字段 → 必须上报，不静默收窄（§31）
        blocked = sorted(allow & preserve)
        conflicts = [f"{node.node_id}:{field} 同时出现在 preserve 与 allow_change"
                     for field in blocked]
        allow -= set(blocked)
        contract = RepairContract(
            issue_ids=tuple(sorted({issue.issue_id for issue in issues})),
            scope=QualityScope(novel_id=self.novel_id, node_ids=(node.node_id,),
                               node_types=(node.node_type,), kind="nodes"),
            node_ids=(node.node_id,),
            preserve=tuple(sorted(preserve)),
            allow_change=tuple(sorted(allow)),
            must_resolve=tuple(sorted({issue.issue_id for issue in issues})),
            constraints=tuple(sorted(constraints)),
            max_scope=(node.node_id,),
            strategy="targeted",
            reason="；".join(sorted({issue.reason for issue in issues})))
        return contract, conflicts

    def _expected(self, node: Any, expected_revisions: Mapping[str, int] | None) -> int:
        if expected_revisions and node.node_id in expected_revisions:
            return int(expected_revisions[node.node_id])
        return int(getattr(node, "revision", 0) or 0)

    @staticmethod
    def _sort_key(node_id: str, nodes: Mapping[str, Any]) -> tuple[int, int, str]:
        node = nodes[node_id]
        return (_ORDER_RANK.get(node.node_type, 9),
                int(getattr(node, "sequence", 0) or 0), node_id)

    def _plan_scope(self, issues: Sequence[QualityIssue],
                    blast: RepairBlastRadius) -> QualityScope:
        return QualityScope(novel_id=self.novel_id,
                            node_ids=tuple(sorted({node_id for issue in issues
                                                   for node_id in issue.scope.node_ids}
                                                  | set(blast.scope))),
                            node_types=(),
                            kind="changed" if blast.changed else "nodes")

    @staticmethod
    def _plan_id(issues: Sequence[QualityIssue],
                 steps: Sequence[RepairStep]) -> str:
        digest = digest_payload({
            "issues": sorted(row.issue_id for row in issues),
            "steps": [{"node": step.node_id, "expected": step.expected_revision,
                       "task": step.task} for step in steps]})
        return f"RP_{digest[:12]}"


__all__ = ["DERIVED_NODE_TYPES", "NODE_TYPE_TASK", "STRUCTURAL_PRESERVE",
           "RepairPlanner", "payload_fields"]
