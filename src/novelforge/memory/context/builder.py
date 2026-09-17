"""ContextBuilder —— 模型上下文选择（V4-03 §17–§20、§29、§35）。

ContextBuilder 负责：选择什么信息 / 排序 / 去重 / 压缩 / token budget / provenance。
**不负责**：写故事、决定 Story Blueprint、调用 provider、质量评分、修改 Canon/StoryState。

输出是结构化的 `ContextBundle`，**不是最终 prompt**（prompt 属于 LLMContract.PromptSpec）。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

from novelforge.core.ids import digest_payload

from ..contracts import (
    MEMORY_SCHEMA_VERSION,
    MemoryItem,
    MemorySource,
    RetrievalPolicy,
    memory_id_for,
    utc_now,
)
from ..errors import MemoryError
from .budget import BLOCK_PRIORITY_ORDER, TokenEstimator, block_priority, item_tokens
from .compression import Compressor

CONTEXT_BUNDLE_SCHEMA_VERSION = 1

#: 请求的 memory type → 目标 block
REQUESTED_TYPE_BLOCKS: dict[str, str] = {
    "canon": "required.canon",
    "story_state": "required.story_state",
    "blueprint": "required.target",
    "episodic": "recent.episodes",
    "semantic": "relevant.semantic",
}


@dataclass(frozen=True)
class ContextRequest:
    novel_id: str
    revision: int | None = None
    operation: str = ""
    target_kind: str = ""
    target_id: str = ""
    task: str = ""
    characters: tuple[str, ...] = ()
    locations: tuple[str, ...] = ()
    time_position: str = ""
    memory_types: tuple[str, ...] = ()
    token_budget: int = 1200
    required_source_ids: tuple[str, ...] = ()
    include_preferences: bool = True
    top_k: int = 8

    def __post_init__(self) -> None:
        if not str(self.novel_id or "").strip():
            raise MemoryError("ContextRequest 必须显式携带 novel_id")
        if int(self.token_budget) <= 0:
            raise MemoryError("ContextRequest.token_budget 必须 > 0")

    def as_dict(self) -> dict[str, Any]:
        return {"novel_id": self.novel_id, "revision": self.revision,
                "operation": self.operation, "target_kind": self.target_kind,
                "target_id": self.target_id, "task": self.task,
                "characters": list(self.characters),
                "locations": list(self.locations),
                "time_position": self.time_position,
                "memory_types": list(self.memory_types),
                "token_budget": self.token_budget,
                "required_source_ids": list(self.required_source_ids),
                "include_preferences": self.include_preferences,
                "top_k": self.top_k}


@dataclass(frozen=True)
class ContextBlock:
    block_id: str
    kind: str                       # required | recent | relevant | preference
    items: tuple[MemoryItem, ...] = ()
    importance: int = 99
    selection_reason: str = ""
    revision: int | None = None
    token_estimate: int = 0
    dropped_count: int = 0

    @property
    def source_ids(self) -> tuple[str, ...]:
        seen: list[str] = []
        for item in self.items:
            ref = item.source.ref
            if ref not in seen:
                seen.append(ref)
        return tuple(seen)

    def as_dict(self) -> dict[str, Any]:
        return {"block_id": self.block_id, "kind": self.kind,
                "items": [item.as_dict() for item in self.items],
                "source_ids": list(self.source_ids),
                "importance": self.importance,
                "selection_reason": self.selection_reason,
                "revision": self.revision,
                "token_estimate": self.token_estimate,
                "dropped_count": self.dropped_count}


@dataclass(frozen=True)
class ContextBundle:
    """结构化上下文包（§20）：不是 huge_prompt_string。"""

    novel_id: str
    revision: int | None = None
    operation: str = ""
    target: Mapping[str, Any] = field(default_factory=dict)
    blocks: Mapping[str, ContextBlock] = field(default_factory=dict)
    order: tuple[str, ...] = ()
    preferences: tuple[Mapping[str, Any], ...] = ()
    provenance: tuple[Mapping[str, Any], ...] = ()
    dropped: tuple[Mapping[str, Any], ...] = ()
    budget: Mapping[str, Any] = field(default_factory=dict)
    digest: str = ""
    context_schema_version: int = CONTEXT_BUNDLE_SCHEMA_VERSION
    memory_schema_version: int = MEMORY_SCHEMA_VERSION
    built_at: str = ""

    def __post_init__(self) -> None:
        if not self.built_at:
            object.__setattr__(self, "built_at", utc_now())

    @property
    def items(self) -> tuple[MemoryItem, ...]:
        rows: list[MemoryItem] = []
        for block_id in self.order:
            rows.extend(self.blocks[block_id].items)
        return tuple(rows)

    def source_ids(self) -> tuple[str, ...]:
        seen: list[str] = []
        for item in self.items:
            ref = item.source.ref
            if ref not in seen:
                seen.append(ref)
        return tuple(seen)

    def to_memory_context(self) -> dict[str, Any]:
        """给 LLMContract 的 context（结构化、可 digest、可追溯）。"""

        return {"blocks": {block_id: [item.text for item in self.blocks[block_id].items]
                           for block_id in self.order},
                "preferences": [row.get("value") for row in self.preferences],
                "budget": dict(self.budget)}

    def as_dict(self) -> dict[str, Any]:
        return {"novel_id": self.novel_id, "revision": self.revision,
                "operation": self.operation, "target": dict(self.target),
                "order": list(self.order),
                "blocks": {block_id: self.blocks[block_id].as_dict()
                           for block_id in self.order},
                "preferences": [dict(row) for row in self.preferences],
                "provenance": [dict(row) for row in self.provenance],
                "dropped": [dict(row) for row in self.dropped],
                "budget": dict(self.budget), "digest": self.digest,
                "context_schema_version": self.context_schema_version,
                "memory_schema_version": self.memory_schema_version,
                "built_at": self.built_at}


__all__ = [
    "CONTEXT_BUNDLE_SCHEMA_VERSION", "ContextBlock", "ContextBundle",
    "ContextRequest", "REQUESTED_TYPE_BLOCKS",
]


class ContextBuilder:
    """按 ContextRequest 组装 ContextBundle（唯一上下文选择入口）。"""

    def __init__(self, memory: Any, *, preferences: Any | None = None,
                 compressor: Compressor | None = None,
                 estimator: TokenEstimator | None = None) -> None:
        self.memory = memory
        self.preferences = preferences
        self.compressor = compressor
        self.estimator = estimator

    # ------------------------------------------------------------------ 内部
    def _search(self, request: ContextRequest, *, source_types: Sequence[str],
                task: str = "", entities: Sequence[str] = (),
                locations: Sequence[str] = (), top_k: int | None = None,
                required_source_ids: Sequence[str] = ()) -> list[MemoryItem]:
        policy = RetrievalPolicy(top_k=int(top_k or request.top_k))
        result = self.memory.search(novel_id=request.novel_id,
                                    revision=request.revision,
                                    task=task or request.task,
                                    entities=tuple(entities),
                                    locations=tuple(locations),
                                    source_types=tuple(source_types),
                                    policy=policy,
                                    required_source_ids=tuple(required_source_ids))
        return list(result.items)

    def _preference_block(self, request: ContextRequest) -> ContextBlock:
        if self.preferences is None or not request.include_preferences:
            return ContextBlock(block_id="preferences", kind="preference",
                                items=(), importance=block_priority("preferences"),
                                selection_reason="author_preference",
                                revision=request.revision)
        rows = self.preferences.as_items(operation=request.operation)
        items: list[MemoryItem] = []
        for row in rows:
            text = f"{row['key']} = {row['value']}（scope={row['scope']}"
            text += "，inferred）" if row.get("inferred") else "）"
            items.append(MemoryItem(
                memory_id=memory_id_for("preference", str(row["key"])),
                memory_type="preference", text=text,
                source=MemorySource(source_type="preference",
                                    source_id=str(row["key"]), revision=None,
                                    label=str(row["scope"]),
                                    metadata={"inferred": bool(row.get("inferred")),
                                              "scope": row["scope"]}),
                selection_reason="author_preference"))
        return ContextBlock(block_id="preferences", kind="preference",
                            items=tuple(items),
                            importance=block_priority("preferences"),
                            selection_reason="author_preference",
                            revision=request.revision)

    def _raw_blocks(self, request: ContextRequest) -> list[ContextBlock]:
        requested = {value for value in request.memory_types}
        canon_types = ("canon_fact", "canon_entity") if not requested else tuple(
            key for key in ("canon",) if key in requested) and (
            "canon_fact", "canon_entity") or ()
        canon_items = self._search(request,
                                   source_types=canon_types or ("canon_fact",
                                                                "canon_entity"),
                                   entities=request.characters,
                                   required_source_ids=request.required_source_ids,
                                   top_k=request.top_k + 2)
        state_items_all = self._search(
            request, source_types=("story_state",), entities=request.characters,
            required_source_ids=request.required_source_ids,
            top_k=request.top_k + 4)
        open_kinds = ("promise", "conflict")
        # 当前状态块只放"状态"，未回收 setup / promise / conflict 归 setup_payoff 块
        state_items = [row for row in state_items_all
                       if str(row.metadata.get("kind")) not in open_kinds]
        target_items = self._search(
            request,
            source_types=("blueprint_node", "chapter_ir", "planning_ir", "outline"),
            entities=tuple(value for value in (request.target_id,) if value),
            task=request.target_id or request.task)
        episode_items = self._search(request, source_types=("episode",),
                                     entities=request.characters, top_k=3)
        # 语义块只接收语义索引的**命中**条目（避免无关条目进入上下文）
        semantic_items = self.memory.search_semantic(
            task=request.task, entities=request.characters + request.locations,
            top_k=request.top_k)
        character_items = [row for row in canon_items
                           if row.source.source_type == "canon_entity"]
        location_items = [row for row in state_items_all
                          if str(row.metadata.get("kind")) == "location"]
        setup_items = [row for row in state_items_all + episode_items
                       if row.metadata.get("open")
                       or str(row.metadata.get("kind")) in open_kinds]

        def block(block_id: str, kind: str, items: Sequence[MemoryItem],
                  reason: str) -> ContextBlock:
            rows = tuple(items)
            return ContextBlock(block_id=block_id, kind=kind, items=rows,
                                importance=block_priority(block_id),
                                selection_reason=reason, revision=request.revision,
                                token_estimate=sum(
                                    item_tokens(item, estimator=self.estimator)
                                    for item in rows))

        return [
            block("required.canon", "required", canon_items, "required_canon"),
            block("required.story_state", "required", state_items, "current_state"),
            block("required.target", "required", target_items, "target_node"),
            block("relevant.characters", "relevant", character_items,
                  "entity_match"),
            block("recent.episodes", "recent", episode_items, "recent_episode"),
            block("relevant.setup_payoff", "relevant", setup_items, "open_setup"),
            block("relevant.locations", "relevant", location_items,
                  "location_match"),
            block("relevant.semantic", "relevant", semantic_items,
                  "semantic_match"),
            self._preference_block(request),
        ]

    @staticmethod
    def _dedupe(blocks: Sequence[ContextBlock]) -> tuple[list[ContextBlock],
                                                         list[dict[str, Any]]]:
        """跨 block 去重：同一 memory_id 只保留优先级最高的 block。"""

        seen: dict[str, str] = {}
        deduped: list[ContextBlock] = []
        dropped: list[dict[str, Any]] = []
        for block in sorted(blocks, key=lambda row: (row.importance, row.block_id)):
            kept: list[MemoryItem] = []
            for item in block.items:
                if item.memory_id in seen:
                    dropped.append({"block_id": block.block_id,
                                    "memory_id": item.memory_id,
                                    "reason": f"duplicate_of:{seen[item.memory_id]}"})
                    continue
                seen[item.memory_id] = block.block_id
                kept.append(item)
            deduped.append(ContextBlock(
                block_id=block.block_id, kind=block.kind, items=tuple(kept),
                importance=block.importance,
                selection_reason=block.selection_reason, revision=block.revision,
                token_estimate=sum(item_tokens(item) for item in kept),
                dropped_count=block.dropped_count))
        return deduped, dropped

    # ------------------------------------------------------------------ 入口
    def build(self, request: ContextRequest) -> ContextBundle:
        from .budget import trim_to_budget
        from .compression import compress_items

        blocks, duplicate_drops = self._dedupe(self._raw_blocks(request))
        kept, budget_drops, budget_report = trim_to_budget(
            [(block.block_id, block.items) for block in blocks],
            budget=request.token_budget, estimator=self.estimator)

        final_blocks: dict[str, ContextBlock] = {}
        for block in blocks:
            items = kept.get(block.block_id, [])
            dropped_count = sum(1 for row in budget_drops
                                if row["block_id"] == block.block_id)
            if self.compressor is not None and items:
                remaining = max(1, request.token_budget
                                - budget_report["protected_tokens"])
                items = compress_items(items, compressor=self.compressor,
                                       target_tokens=remaining)
            final_blocks[block.block_id] = ContextBlock(
                block_id=block.block_id, kind=block.kind, items=tuple(items),
                importance=block.importance,
                selection_reason=block.selection_reason, revision=block.revision,
                token_estimate=sum(item_tokens(item, estimator=self.estimator)
                                   for item in items),
                dropped_count=dropped_count)

        order = tuple(sorted((block.block_id for block in blocks),
                             key=lambda value: (block_priority(value), value)))
        provenance = [
            {"memory_id": item.memory_id, "source_id": item.source.source_id,
             "source_type": item.source.source_type,
             "revision": item.source.revision, "block_id": block_id,
             "selection_reason": item.selection_reason,
             "relevance": item.relevance}
            for block_id in order
            for item in final_blocks[block_id].items
        ]
        dropped = [*duplicate_drops, *budget_drops]
        preferences = tuple(
            self.preferences.as_items(operation=request.operation)
            if (self.preferences is not None and request.include_preferences)
            else ())
        digest = digest_payload({
            "novel_id": request.novel_id, "revision": request.revision,
            "operation": request.operation, "order": list(order),
            "items": [{"id": item.memory_id, "reason": item.selection_reason}
                      for block_id in order
                      for item in final_blocks[block_id].items],
            "budget": budget_report})
        return ContextBundle(
            novel_id=request.novel_id, revision=request.revision,
            operation=request.operation,
            target={"kind": request.target_kind, "id": request.target_id},
            blocks=final_blocks, order=order, preferences=preferences,
            provenance=tuple(provenance), dropped=tuple(dropped),
            budget={**budget_report, "block_order": list(BLOCK_PRIORITY_ORDER)},
            digest=digest)


__all__ = [
    "CONTEXT_BUNDLE_SCHEMA_VERSION", "ContextBlock", "ContextBuilder",
    "ContextBundle", "ContextRequest", "REQUESTED_TYPE_BLOCKS",
]
