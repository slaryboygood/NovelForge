"""Evaluator 运行上下文（V4-05 §23–§26）。

Evaluator 只读：拿到 `EvaluationContext`（目标节点 + 相关节点 + 只读 memory / repository 访问），
产出 `QualityIssue` 列表。不得修改 Blueprint / Canon / StoryState，也不得调用 Repair。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

from novelforge.blueprint import BlueprintNode
from novelforge.memory import RetrievalPolicy

from ..contracts import QualityPolicy, QualityScope


@dataclass(frozen=True)
class EvaluationContext:
    novel_id: str
    scope: QualityScope
    nodes: Mapping[str, BlueprintNode]
    policy: QualityPolicy
    repository: Any = None
    memory: Any = None
    context_builder: Any = None
    critic: Any = None
    extra: Mapping[str, Any] = field(default_factory=dict)
    usage: dict[str, Any] = field(default_factory=dict)

    # ------------------------------------------------------------------ usage
    def record_usage(self, raw: Mapping[str, Any] | None, *,
                     operation: str = "") -> None:
        """记录一次模型调用的 usage（§41：评估成本必须可汇总）。

        只累加 token / cost / calls，**不**保存 prompt 原文（§60）。
        """

        from ..aggregation import merge_usage, normalize_usage

        merged = merge_usage(self.usage.get("total"), normalize_usage(raw))
        self.usage["total"] = merged
        if operation:
            per_operation = self.usage.setdefault("by_operation", {})
            per_operation[operation] = merge_usage(per_operation.get(operation),
                                                   normalize_usage(raw))

    # ------------------------------------------------------------------ 便捷
    def payload(self, node: BlueprintNode | str) -> dict[str, Any]:
        if isinstance(node, str):
            node = self.nodes[node]
        payload = node.payload
        return (payload.model_dump(mode="json")
                if hasattr(payload, "model_dump") else dict(payload))

    def nodes_of_type(self, node_type: str) -> list[BlueprintNode]:
        return sorted((node for node in self.nodes.values()
                       if node.node_type == node_type and node.novel_id == self.novel_id),
                      key=lambda item: (item.sequence, item.node_id))

    def children(self, parent_id: str, node_type: str = "") -> list[BlueprintNode]:
        rows = [node for node in self.nodes.values() if node.parent_id == parent_id]
        if node_type:
            rows = [node for node in rows if node.node_type == node_type]
        return sorted(rows, key=lambda item: (item.sequence, item.node_id))

    def scoped(self) -> list[BlueprintNode]:
        """本次评估的"目标节点"（scope.node_ids 为空时= 全部节点）。"""

        if not self.scope.node_ids:
            return sorted(self.nodes.values(),
                          key=lambda item: (item.node_type, item.sequence, item.node_id))
        return [self.nodes[node_id] for node_id in self.scope.node_ids
                if node_id in self.nodes]

    def source_ids(self, node: BlueprintNode) -> tuple[str, ...]:
        return tuple(node.source_ids)

    def canon_items(self, *, entities: Sequence[str] = (), task: str = "",
                    top_k: int = 12) -> list[Any]:
        """经 MemoryService 只读检索 Canon（evaluator 不直接扫数据库，§14）。"""

        if self.memory is None:
            return []
        result = self.memory.search(novel_id=self.novel_id, entities=tuple(entities),
                                    task=task, source_types=("canon_fact", "canon_entity"),
                                    policy=RetrievalPolicy(top_k=top_k))
        return list(result.items)

    def episodes(self, *, entities: Sequence[str] = (), top_k: int = 8) -> list[Any]:
        if self.memory is None:
            return []
        result = self.memory.search(novel_id=self.novel_id, entities=tuple(entities),
                                    source_types=("episode",),
                                    policy=RetrievalPolicy(top_k=top_k))
        return list(result.items)

    def scope_for(self, nodes: Sequence[BlueprintNode], *, kind: str = "nodes"
                  ) -> QualityScope:
        return QualityScope(novel_id=self.novel_id,
                            node_ids=tuple(sorted(node.node_id for node in nodes)),
                            node_types=tuple(sorted({node.node_type for node in nodes})),
                            revision=self.scope.revision, kind=kind)


def stable_scope(node: BlueprintNode) -> QualityScope:
    return QualityScope(novel_id=node.novel_id, node_ids=(node.node_id,),
                        node_types=(node.node_type,), revision=node.revision,
                        kind="nodes")


def text_of(payload: Mapping[str, Any], *fields: str) -> str:
    parts: list[str] = []
    for key in fields:
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            parts.append(value.strip())
        elif isinstance(value, list):
            parts.extend(str(item) for item in value if str(item).strip())
    return "；".join(parts)


__all__ = ["EvaluationContext", "stable_scope", "text_of"]
