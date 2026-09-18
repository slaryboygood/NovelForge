"""BlueprintCompiler（V4-07 §26–§31）：canonical Blueprint → 有序交付表示。

```text
唯一顺序（§27）：node_type order → parent → sequence → node_id tie-break
唯一可见字段（§30）：visible story content 与 internal metadata 分离
```

所有 exporter 都消费本模块的输出，**不各自决定排序或字段可见性**。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from novelforge.blueprint import BlueprintNode
from novelforge.core.ids import digest_payload

#: 交付表示里的节点类型顺序（§26）
NODE_TYPE_ORDER: tuple[str, ...] = (
    "premise", "theme", "world", "character", "character_arc", "story_arc",
    "structural_unit", "chapter", "scene", "setup", "payoff", "causal_link",
)

_TYPE_RANK: Mapping[str, int] = {name: index
                                 for index, name in enumerate(NODE_TYPE_ORDER)}

#: 作者 / 读者可见字段（§30）：Markdown / DOCX 只允许出现这些字段的内容
VISIBLE_FIELDS: Mapping[str, tuple[str, ...]] = {
    "premise": ("premise", "central_conflict", "protagonist_goal", "stakes",
                "dramatic_question", "story_promise", "genre", "tone", "constraints"),
    "theme": ("theme", "statement", "counter_theme", "motifs"),
    "world": ("rules", "locations", "factions", "resources", "technology_or_magic",
              "social_constraints", "conflict_sources", "story_relevant_history"),
    "character": ("name", "role", "kind", "goal", "motivation", "need", "fear",
                  "misbelief", "strength", "flaw", "conflict_source",
                  "relationships", "story_function", "constraints"),
    "character_arc": ("start_state", "internal_conflict", "external_pressure",
                      "key_turns", "midpoint_change", "crisis", "climax_choice",
                      "end_state"),
    "story_arc": ("initial_state", "inciting_incident", "progressive_complications",
                  "major_turns", "midpoint", "crisis", "climax", "resolution"),
    "structural_unit": ("unit_type", "title", "goal", "conflict", "turn", "outcome"),
    "chapter": ("title", "goal", "conflict", "turn", "outcome", "hook", "location"),
    "scene": ("scene_purpose", "location", "time", "conflict", "escalation", "turn",
              "outcome", "information_reveal", "character_change",
              "relationship_change", "next_hook", "story_function"),
    "setup": ("content", "expected_payoff", "status"),
    "payoff": ("result", "status"),
    "causal_link": ("relation", "reason"),
}

#: 内部 metadata（§30）：绝不出现在 Markdown / DOCX
INTERNAL_FIELDS: tuple[str, ...] = (
    "node_id", "novel_id", "parent_id", "revision", "parent_revision", "status",
    "quality_status", "source_ids", "context_digest", "generation_contract",
    "generation_contract_version", "provenance", "schema_version", "sequence",
    "created_at", "updated_at", "request_id", "model", "provider", "cache_key",
)

#: 引用型内部字段（例如 scene.chapter_id / character_arc.character_id）
INTERNAL_REFERENCE_FIELDS: tuple[str, ...] = (
    "chapter_id", "character_id", "source_node", "target_node", "resolves_setup_ids",
)


def payload_of(node: BlueprintNode) -> dict[str, Any]:
    payload = getattr(node, "payload", None)
    if hasattr(payload, "model_dump"):
        return payload.model_dump(mode="json")
    return dict(payload or {})


def visible_payload(node_type: str, payload: Mapping[str, Any]) -> dict[str, Any]:
    """只保留作者 / 读者可见字段（字段顺序固定，便于 deterministic 输出）。"""

    fields = VISIBLE_FIELDS.get(str(node_type), tuple(sorted(payload)))
    return {name: payload[name] for name in fields if name in payload}


@dataclass(frozen=True)
class CompiledNode:
    node_id: str
    node_type: str
    revision: int
    parent_id: str
    sequence: int
    status: str
    payload: Mapping[str, Any]
    visible: Mapping[str, Any]
    provenance: Mapping[str, Any] = field(default_factory=dict)
    source_ids: tuple[str, ...] = ()

    def as_dict(self, *, include_internal: bool = True) -> dict[str, Any]:
        row: dict[str, Any] = {"node_id": self.node_id, "node_type": self.node_type,
                               "revision": int(self.revision),
                               "payload": dict(self.payload),
                               "visible": dict(self.visible)}
        if include_internal:
            row.update({"parent_id": self.parent_id,
                        "sequence": int(self.sequence), "status": self.status,
                        "source_ids": list(self.source_ids),
                        "provenance": dict(self.provenance)})
        return row


@dataclass(frozen=True)
class CompiledBlueprint:
    novel_id: str
    nodes: tuple[CompiledNode, ...] = ()
    ordering: tuple[str, ...] = NODE_TYPE_ORDER
    node_revisions: Mapping[str, int] = field(default_factory=dict)
    digest: str = ""

    def __post_init__(self) -> None:
        if not self.digest:
            object.__setattr__(self, "digest", digest_payload(
                {"novel": self.novel_id,
                 "nodes": [{"id": node.node_id, "r": node.revision,
                            "payload": dict(node.payload)} for node in self.nodes]}))

    def by_type(self, node_type: str) -> tuple[CompiledNode, ...]:
        return tuple(node for node in self.nodes if node.node_type == node_type)

    def node(self, node_id: str) -> CompiledNode | None:
        return next((row for row in self.nodes if row.node_id == node_id), None)

    @property
    def node_count(self) -> int:
        return len(self.nodes)

    def as_dict(self, *, include_internal: bool = True) -> dict[str, Any]:
        return {"novel_id": self.novel_id, "node_count": self.node_count,
                "ordering": list(self.ordering),
                "node_revisions": {str(key): int(value) for key, value
                                   in sorted(self.node_revisions.items())},
                "nodes": [node.as_dict(include_internal=include_internal)
                          for node in self.nodes],
                "digest": self.digest}


class BlueprintCompiler:
    """把（已钉住 revision 的）Blueprint 节点编译成交付表示。"""

    def __init__(self, repository: Any) -> None:
        self.repository = repository

    @staticmethod
    def order_key(node: CompiledNode) -> tuple[int, int, str, str]:
        type_rank = _TYPE_RANK.get(node.node_type, len(NODE_TYPE_ORDER))
        return (type_rank, int(node.sequence), str(node.parent_id), node.node_id)

    def materialize(self, node_id: str, revision: int) -> CompiledNode:
        stored = self.repository.get_revision(node_id, int(revision))
        if stored is None:
            raise KeyError(f"revision 不存在：{node_id}@{revision}")
        payload = payload_of(stored)
        return CompiledNode(node_id=stored.node_id, node_type=stored.node_type,
                            revision=int(stored.revision),
                            parent_id=stored.parent_id,
                            sequence=int(stored.sequence), status=str(stored.status),
                            payload=payload,
                            visible=visible_payload(stored.node_type, payload),
                            provenance=dict(stored.provenance),
                            source_ids=tuple(stored.source_ids))

    def compile(self, node_revisions: Mapping[str, int]) -> CompiledBlueprint:
        """按 snapshot 钉住的 revision 编译（顺序唯一，§27）。"""

        materialized = [self.materialize(node_id, revision)
                        for node_id, revision in sorted(node_revisions.items())]
        ordered = tuple(sorted(materialized, key=self.order_key))
        return CompiledBlueprint(
            novel_id=self.repository.novel_id, nodes=ordered,
            node_revisions={node.node_id: node.revision for node in ordered})


__all__ = [
    "INTERNAL_FIELDS", "INTERNAL_REFERENCE_FIELDS", "NODE_TYPE_ORDER",
    "VISIBLE_FIELDS", "BlueprintCompiler", "CompiledBlueprint", "CompiledNode",
    "payload_of", "visible_payload",
]
