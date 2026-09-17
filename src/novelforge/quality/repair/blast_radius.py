"""Repair Blast Radius（V4-05 §32）。

改一个 Scene 可能影响：

```text
同一章后续 Scene 的连续性 / setup-payoff 绑定 / 因果链 / 人物弧 / 章节 outcome
```

但**不得**因此重跑整个 Blueprint。Blast radius 只算三件事：

```text
Direct Scope                计划直接改动的节点
Dependent Scope             结构上依赖这些节点、必须一起复核的节点
Required Verification Gates 复核需要重新执行的 gate 集合（确定性有序）
```
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping, Sequence

#: gate 的确定性顺序（Q0 → Q9）
GATE_ORDER: tuple[str, ...] = ("Q0", "Q1", "Q2", "Q3", "Q4", "Q5", "Q6", "Q7",
                               "Q8", "Q9")

#: 节点类型 → 该类型变化后必须复核的 gate（结构事实，不是生产策略）
NODE_TYPE_GATES: Mapping[str, tuple[str, ...]] = {
    "premise": ("Q0", "Q1", "Q2", "Q8"),
    "theme": ("Q0", "Q1", "Q8"),
    "world": ("Q0", "Q1", "Q2", "Q3"),
    "character": ("Q0", "Q1", "Q2", "Q4"),
    "character_arc": ("Q0", "Q1", "Q4", "Q7"),
    "story_arc": ("Q0", "Q1", "Q4", "Q5", "Q7"),
    "structural_unit": ("Q0", "Q1", "Q6", "Q7"),
    "chapter": ("Q0", "Q1", "Q3", "Q6", "Q7", "Q8"),
    "scene": ("Q0", "Q1", "Q3", "Q4", "Q5", "Q6", "Q7", "Q8"),
    "causal_link": ("Q0", "Q1", "Q5"),
    "setup": ("Q0", "Q1", "Q5", "Q7", "Q9"),
    "payoff": ("Q0", "Q1", "Q5", "Q7", "Q9"),
}

#: 任何修复后都必须复核的基线 gate（结构完整性 + 交付就绪度）
BASELINE_GATES: tuple[str, ...] = ("Q0", "Q1", "Q9")

#: 派生结构节点（不属于叙事树，但可能被改动的节点引用）
DERIVED_TYPES: tuple[str, ...] = ("setup", "payoff", "causal_link")


def order_gates(gates: Iterable[str]) -> tuple[str, ...]:
    wanted = {str(gate) for gate in gates}
    return tuple(gate for gate in GATE_ORDER if gate in wanted) + \
        tuple(sorted(wanted - set(GATE_ORDER)))


def _payload(node: Any) -> dict[str, Any]:
    payload = getattr(node, "payload", None)
    if hasattr(payload, "model_dump"):
        return payload.model_dump(mode="json")
    return dict(payload or {})


@dataclass(frozen=True)
class RepairBlastRadius:
    """direct / dependent / verification gates（§32）。"""

    changed: tuple[str, ...] = ()
    dependent: tuple[str, ...] = ()
    gates: tuple[str, ...] = ()
    reasons: Mapping[str, tuple[str, ...]] = field(default_factory=dict)

    @property
    def scope(self) -> tuple[str, ...]:
        return tuple(sorted(set(self.changed) | set(self.dependent)))

    def as_dict(self) -> dict[str, Any]:
        return {"changed": list(self.changed),
                "dependent": list(self.dependent),
                "scope": list(self.scope),
                "gates": list(self.gates),
                "reasons": {key: list(value)
                            for key, value in sorted(self.reasons.items())}}

    @classmethod
    def compute(cls, *, nodes: Sequence[Any], changed: Iterable[str],
                issue_gates: Iterable[str] = (),
                include_dependent: bool = True) -> "RepairBlastRadius":
        """依据 Blueprint 结构关系计算 blast radius（确定性、可解释）。"""

        by_id = {node.node_id: node for node in nodes}
        direct = tuple(sorted({str(value) for value in changed if value}))
        direct_set = set(direct)
        reasons: dict[str, list[str]] = {}

        def mark(node_id: str, reason: str) -> None:
            if node_id in direct_set or node_id not in by_id:
                return
            reasons.setdefault(node_id, []).append(reason)

        if include_dependent:
            changed_chapters = {str(by_id[node_id].parent_id or "")
                                for node_id in direct if node_id in by_id}
            for other in nodes:
                if other.node_id in direct_set:
                    continue
                if other.parent_id and other.parent_id in direct_set:
                    mark(other.node_id, "child_of_changed")
                    continue
                if other.node_type == "scene" and changed_chapters and \
                        str(other.parent_id or "") in changed_chapters:
                    mark(other.node_id, "same_chapter_scene")
                    continue
                if other.node_type in DERIVED_TYPES:
                    payload = _payload(other)
                    if other.node_type == "causal_link":
                        endpoints = {str(payload.get("source_node") or ""),
                                     str(payload.get("target_node") or "")}
                        if endpoints & direct_set:
                            mark(other.node_id, "causal_endpoint_changed")
                    elif other.node_type == "payoff":
                        resolved = {str(value) for value in
                                    (payload.get("resolves_setup_ids") or [])}
                        if resolved & direct_set:
                            mark(other.node_id, "resolves_changed_setup")
                    if str(other.parent_id or "") in direct_set:
                        mark(other.node_id, "attached_to_changed_node")
                    continue
                if other.node_type == "character_arc":
                    payload = _payload(other)
                    linked = {str(value) for value in
                              list(payload.get("linked_scenes") or [])
                              + list(payload.get("linked_chapters") or [])}
                    if linked & direct_set:
                        mark(other.node_id, "arc_links_changed_node")

        dependent = tuple(sorted(reasons))
        gates: set[str] = set(BASELINE_GATES)
        gates.update(str(gate) for gate in issue_gates)
        for node_id in direct + dependent:
            node = by_id.get(node_id)
            if node is None:
                continue
            gates.update(NODE_TYPE_GATES.get(node.node_type, ("Q0", "Q1")))
        return cls(changed=direct, dependent=dependent, gates=order_gates(gates),
                   reasons={key: tuple(sorted(set(value)))
                            for key, value in sorted(reasons.items())})


__all__ = ["BASELINE_GATES", "DERIVED_TYPES", "GATE_ORDER", "NODE_TYPE_GATES",
           "RepairBlastRadius", "order_gates"]
